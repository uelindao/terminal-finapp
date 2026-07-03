"""
utils/derive_multiples.py
=========================
Deriva múltiplos fundamentalistas AUSENTES (p/l, p/vp, roe%, margem%, ev/ebitda,
market_cap) a partir do que JÁ existe no cache: `historico_trimestral`
(CVM/yfinance) + preço + market_cap do provedor.

Motivação (P2-1): com o plano atual da BRAPI o campo `fundamentalData` vem vazio,
então p/vp, roe, dy, margem e ev/ebitda dependem inteiramente do enriquecimento
via yfinance.info — que falha/rate-limita em muitos tickers BR. Resultado: muitas
empresas ficam sem esses múltiplos. Mas os componentes para calculá-los já estão
no `historico_trimestral` (receita, lucro, patrimônio, ativos, dívida, caixa,
ebitda) + preço. Este módulo preenche as lacunas por cálculo.

SEMÂNTICA DE ANUALIZAÇÃO (crítico):
  - CVM (registro com `_fonte == "cvm"`): os fluxos (receita/lucro/ebit/cfo) já
    vêm ANUALIZADOS por período (ver cvm_client: Q1×4, Q2×2, Q3×4/3). Logo o
    valor anual = T0 diretamente (NÃO somar 4 trimestres).
  - yfinance (sem `_fonte`): os fluxos são POR TRIMESTRE → anual = soma dos 4
    últimos trimestres (exige ≥4; senão não deriva, para não inventar número).

PRECEDÊNCIA: só preenche campos que estão None. Valores do provedor (BRAPI/FMP)
e do yfinance.info têm prioridade — a derivação é o último recurso. Cada campo
derivado é registrado em data['_field_source'][campo] = 'derivado' para auditoria.

Robusto: nunca levanta. Aplica ranges de sanidade (utils/scrapers.RANGES_VALIDOS).
"""
from __future__ import annotations

# Ranges de sanidade reutilizados da validação de fundamentos.
try:
    from utils.scrapers import RANGES_VALIDOS
except Exception:  # pragma: no cover - fallback se import de scrapers falhar
    RANGES_VALIDOS = {
        'p/l': (-50.0, 500.0), 'p/vp': (0.0, 50.0), 'roe%': (-100.0, 300.0),
        'dy%': (0.0, 30.0), 'ev/ebitda': (-10.0, 100.0), 'margem%': (-200.0, 100.0),
    }

_BANK_KEYWORDS = (
    'financ', 'bank', 'banc', 'insur', 'seguro', 'crédito', 'credito',
    'previd', 'intermediários financeiros',
)


def _num(v):
    """float seguro; None/str/NaN/inf → None."""
    if v is None:
        return None
    try:
        f = float(v)
        if f != f or f in (float('inf'), float('-inf')):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _sane(campo: str, valor: float) -> bool:
    """True se o valor está dentro do range realista do campo (ou sem range)."""
    rng = RANGES_VALIDOS.get(campo)
    if rng is None:
        return True
    lo, hi = rng
    return lo <= valor <= hi


def _is_bank(data: dict) -> bool:
    setor = str(data.get('setor') or '').lower()
    nome = str(data.get('nome') or '').lower()
    return any(k in setor or k in nome for k in _BANK_KEYWORDS)


def _fonte_cvm(historico: list[dict]) -> bool:
    return bool(historico) and str(historico[0].get('_fonte') or '').lower() == 'cvm'


def _valor_anual(historico: list[dict], key: str) -> float | None:
    """
    Valor ANUAL de uma métrica de fluxo (receita/lucro/ebitda/ebit/cfo).
    CVM: já anualizado → T0. yfinance: soma dos 4 últimos trimestres (exige ≥4).
    """
    if not historico:
        return None
    if _fonte_cvm(historico):
        return _num(historico[0].get(key))
    vals = [_num(h.get(key)) for h in historico[:4]]
    vals = [v for v in vals if v is not None]
    if len(vals) >= 4:
        return sum(vals)
    return None  # <4 trimestres yfinance: não anualiza (evita número inventado)


def _snapshot(historico: list[dict], key: str) -> float | None:
    """Métrica de estoque (balanço) no período mais recente T0."""
    if not historico:
        return None
    return _num(historico[0].get(key))


def derivar_multiplos(data: dict, historico: list[dict] | None, logger=None) -> dict:
    """
    Preenche múltiplos ausentes em `data` a partir do `historico_trimestral`.
    Muta `data` in-place e retorna (conveniência). Só toca campos que são None.

    `data` deve conter (quando disponível): 'preco', 'market_cap', 'setor',
    'nome', e opcionalmente 'shares_out' (do yfinance.info).
    """
    if not historico:
        return data

    src = data.setdefault('_field_source', {})
    flags = data.setdefault('_flags', {})

    def _fill(campo: str, valor, origem: str = 'derivado') -> None:
        if data.get(campo) is not None:
            return  # provedor/yfinance têm prioridade
        v = _num(valor)
        if v is None or not _sane(campo, v):
            return
        data[campo] = round(v, 2)
        src[campo] = origem

    try:
        preco   = _num(data.get('preco'))
        shares  = _snapshot(historico, 'shares') or _num(data.get('shares_out'))
        pl_pat  = _snapshot(historico, 'patrimonio')
        if pl_pat is None:
            at = _snapshot(historico, 'ativos_totais')
            pt = _snapshot(historico, 'passivos_totais')
            if at is not None and pt is not None:
                pl_pat = at - pt

        divida = _snapshot(historico, 'divida_total')
        cash   = _snapshot(historico, 'cash')

        lucro_a   = _valor_anual(historico, 'lucro')
        receita_a = _valor_anual(historico, 'receita')
        ebitda_a  = _valor_anual(historico, 'ebitda')
        if ebitda_a is None or ebitda_a <= 0:
            ebitda_a = _valor_anual(historico, 'ebit')  # fallback conservador

        # market_cap: preço × ações quando o provedor não trouxe
        mcap = _num(data.get('market_cap'))
        if mcap is None and preco and shares:
            mcap = preco * shares
            data['market_cap'] = round(mcap, 2)
            src['market_cap'] = 'derivado'

        # p/l = market_cap / lucro anual (None se prejuízo; sinaliza a UI)
        if mcap and lucro_a is not None:
            if lucro_a > 0:
                _fill('p/l', mcap / lucro_a)
            else:
                flags['prejuizo'] = True

        # p/vp = market_cap / patrimônio líquido
        if mcap and pl_pat and pl_pat > 0:
            _fill('p/vp', mcap / pl_pat)

        # roe% = lucro anual / patrimônio líquido
        if lucro_a is not None and pl_pat and pl_pat > 0:
            _fill('roe%', lucro_a / pl_pat * 100)

        # margem% = lucro anual / receita anual
        if lucro_a is not None and receita_a and receita_a > 0:
            _fill('margem%', lucro_a / receita_a * 100)

        # ev/ebitda = (market_cap + dívida − caixa) / ebitda anual — não p/ bancos
        if not _is_bank(data) and mcap and ebitda_a and ebitda_a > 0:
            ev = mcap + (divida or 0.0) - (cash or 0.0)
            _fill('ev/ebitda', ev / ebitda_a)

    except Exception as e:
        if logger:
            logger.debug(f"[derive_multiples] falha ao derivar p/ {data.get('ticker')}: {e}")

    return data


def derivar_dy(data: dict, dividendos_12m: float | None, logger=None) -> dict:
    """
    Deriva dy% = dividendos pagos nos últimos 12m / preço × 100, quando ausente.
    `dividendos_12m` é a SOMA (por cota/ação) dos proventos dos últimos 12 meses.
    """
    if data.get('dy%') is not None:
        return data
    preco = _num(data.get('preco'))
    dv = _num(dividendos_12m)
    if preco and preco > 0 and dv is not None and dv >= 0:
        dy = dv / preco * 100
        if _sane('dy%', dy):
            data['dy%'] = round(dy, 2)
            data.setdefault('_field_source', {})['dy%'] = 'derivado'
    return data
