"""Scorecard setorial com dimensões independentes e cobertura explícita.

Fundamento usa apenas ROE, margem líquida, P/L e P/VP observados no cache.
Não reutiliza o health score, que já contém momentum e cenário macro.
O técnico é uma posição de momentum entre setores, não RS de um benchmark.
Os limites e pesos são heurísticos; o composto não é retorno previsto.
"""
from __future__ import annotations

import math

from utils.st_fallback import st
from utils.logger import get_logger
from utils.setores import normalizar_setor, LABEL_SETOR as _LABEL_SETOR

logger = get_logger(__name__)

_W_FUND, _W_TEC, _W_MAC = 0.45, 0.25, 0.30
_COBERTURA_MINIMA = 50.0

# Mesmos limites absolutos já declarados no health_engine, organizados pela
# taxonomia canônica. Apenas a regra de valuation é compartilhada: nenhum
# score, penalidade técnica, ROIC/WACC ou ajuste macro é reaproveitado.
_LIMITES_MULTIPLOS = {
    "tecnologia": (30, 50, 6.0, 12.0),
    "financeiro": (12, 20, 1.5, 3.0),
    "utilities": (18, 28, 1.5, 2.5),
    "consumo_defensivo": (22, 35, 3.0, 6.0),
    "consumo_ciclico": (20, 35, 3.0, 7.0),
    "saude": (22, 38, 4.0, 8.0),
    "energia": (12, 20, 1.5, 3.0),
    "materiais": (12, 22, 1.5, 3.0),
    "industria": (20, 32, 3.0, 6.0),
    "imobiliario": (20, 35, 1.5, 3.0),
    "comunicacao": (22, 38, 4.0, 8.0),
}


def _numero(v) -> float | None:
    """Zero é observação válida; NaN, infinito, booleanos e strings ruins não."""
    if v is None or isinstance(v, bool):
        return None
    try:
        out = float(v)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _media(valores, casas: int | None = 1) -> float | None:
    validos = [v for v in valores if v is not None]
    if not validos:
        return None
    media = sum(validos) / len(validos)
    return round(media, casas) if casas is not None else media


def _ponderado_observado(pares) -> float | None:
    """Normaliza somente métricas observadas; não preenche ausências."""
    validos = [(v, peso) for v, peso in pares if v is not None]
    den = sum(peso for _, peso in validos)
    return round(sum(v * peso for v, peso in validos) / den, 1) if den else None


def _fundamento_ativo(dados: dict, setor: str) -> dict:
    roe = _numero(dados.get("roe%"))
    margem = _numero(dados.get("margem%"))
    pl = _numero(dados.get("p/l"))
    pvp = _numero(dados.get("p/vp"))
    pe_bom, pe_medio, pb_bom, pb_medio = _LIMITES_MULTIPLOS[setor]

    score_roe = (100 if roe > 20 else 62.5 if roe > 10 else 25 if roe > 0 else 0) if roe is not None else None
    score_margem = (100 if margem > 15 else 100 * 5 / 7 if margem > 5 else 0) if margem is not None else None

    def _multiplo(valor, bom, medio, pontos_medio):
        if valor is None:
            return None
        return 100.0 if 0 < valor <= bom else pontos_medio if bom < valor <= medio else 0.0

    qualidade = _ponderado_observado([(score_roe, 8), (score_margem, 7)])
    valuation = _ponderado_observado([
        (_multiplo(pl, pe_bom, pe_medio, 62.5), 8),
        (_multiplo(pvp, pb_bom, pb_medio, 100 * 5 / 7), 7),
    ])
    # Qualidade e valuation têm pesos iguais. Exigir as duas impede que só
    # um múltiplo barato se transforme em uma nota fundamental completa.
    fundamento = _media([qualidade, valuation]) if qualidade is not None and valuation is not None else None
    campos = {"roe%": roe, "margem%": margem, "p/l": pl, "p/vp": pvp}
    return {"qualidade": qualidade, "valuation": valuation,
            "fundamento": fundamento, "campos": campos}


def _macro_para_0_100(pontos: int) -> float:
    return _clamp(50 + pontos * 6.25, 0, 100)


def _composto(fund: float | None, tec: float | None, mac: float | None) -> float | None:
    if any(v is None for v in (fund, tec, mac)):
        return None
    return round(_W_FUND * fund + _W_TEC * tec + _W_MAC * mac, 1)


def _veredicto(composto: float | None, mac_pontos: int | None = None) -> tuple[str, str]:
    if composto is None:
        return "dados insuficientes", "#808890"
    if composto >= 62:
        return "overweight", "#00C853"
    if composto >= 48:
        return "neutro", "#FF9900"
    return "underweight", "#FF1744"


def calcular_scorecard_dados(fund_all: dict, price_all: dict,
                            macro_por_setor: dict | None = None,
                            universo: str = "BR") -> list[dict]:
    """Núcleo puro: dados recebidos, sem banco, rede ou estado de sessão.

    Preserva as chaves do ranking anterior. Dimensões ausentes são None;
    composto exige as três e cobertura de pelo menos metade dos ativos em
    fundamentos e momentum. A cobertura não é uma probabilidade de acerto.
    """
    is_br = str(universo).upper() == "BR"
    grupos: dict[str, list[dict]] = {}
    for ticker, dados in (fund_all or {}).items():
        if ticker.endswith(".SA") != is_br or not isinstance(dados, dict):
            continue
        canon = normalizar_setor(dados.get("setor"))
        if canon not in _LABEL_SETOR:
            continue
        grupos.setdefault(canon, []).append({
            "ticker": ticker,
            **_fundamento_ativo(dados, canon),
            "momentum": _numero(((price_all or {}).get(ticker) or {}).get("var_12m")),
        })

    moms = {c: _media((a["momentum"] for a in ativos), casas=None) for c, ativos in grupos.items()}
    observados = [m for m in moms.values() if m is not None]
    banda = max(observados) - min(observados) if len(observados) >= 2 else 0
    resultado = []
    for canon, ativos in grupos.items():
        n = len(ativos)
        fundamento = _media(a["fundamento"] for a in ativos)
        qualidade = _media(a["qualidade"] for a in ativos)
        valuation = _media(a["valuation"] for a in ativos)
        n_fund = sum(a["fundamento"] is not None for a in ativos)
        n_tec = sum(a["momentum"] is not None for a in ativos)
        cob_fund = round(100 * n_fund / n, 1)
        cob_tec = round(100 * n_tec / n, 1)
        cobertura_campos = {
            campo: round(100 * sum(a["campos"][campo] is not None for a in ativos) / n, 1)
            for campo in ("roe%", "margem%", "p/l", "p/vp")
        }
        m = moms[canon]
        tecnico = round((m - min(observados)) / banda * 100, 1) if m is not None and banda > 0 else None
        macro_det = (macro_por_setor or {}).get(canon) or {}
        pts = _numero(macro_det.get("pontos"))
        macro = round(_macro_para_0_100(pts), 1) if pts is not None else None
        alertas = []
        if cob_fund < 100 or min(cobertura_campos.values()) < 100:
            alertas.append("Fundamentos parciais: confira a cobertura por campo e por ativo.")
        if cob_tec < 100:
            alertas.append("Momentum parcial: a média usa apenas retornos observados.")
        if m is not None and banda == 0:
            alertas.append("Sem comparação técnica: menos de dois setores com momentum distinto.")
        if macro is not None and "fontes" in macro_det and "inflacao_setorial" not in macro_det["fontes"]:
            alertas.append("Macro usa apenas regime: inflação setorial indisponível.")
        if macro is None:
            alertas.append("Cenário macro indisponível; nenhum valor neutro foi imputado.")
        composto = _composto(fundamento, tecnico, macro)
        if cob_fund < _COBERTURA_MINIMA or cob_tec < _COBERTURA_MINIMA:
            composto = None
            alertas.append("Composto suspenso: cobertura inferior a 50% dos ativos em uma dimensão.")
        veredicto, cor = _veredicto(composto, pts)
        resultado.append({
            "setor": canon, "label": _LABEL_SETOR[canon], "n_ativos": n,
            "fundamento": fundamento, "qualidade": qualidade, "valuation": valuation,
            "tecnico": tecnico, "momentum_12m": round(m, 1) if m is not None else None,
            "macro": macro, "macro_pontos": int(pts) if pts is not None else None,
            "macro_detalhes": macro_det.get("breakdown", {}),
            "macro_fontes": macro_det.get("fontes", []),
            "composto": composto, "veredicto": veredicto, "cor": cor,
            "n_fundamento": n_fund, "n_tecnico": n_tec,
            "cobertura_fundamento": cob_fund, "cobertura_tecnico": cob_tec,
            "cobertura_por_campo": cobertura_campos,
            "metricas_medias": {campo: _media(a["campos"][campo] for a in ativos) for campo in cobertura_campos},
            "tickers": [a["ticker"].removesuffix(".SA") for a in ativos[:6]],
            "alertas": alertas,
            "metodologia": {
                "versao": "2.0-independente",
                "fundamento": "ROE e margem líquida (qualidade) + P/L e P/VP (valuation); métricas observadas; pesos 50/50.",
                "tecnico": "Média simples de retorno 12m dos ativos; min-max entre setores disponíveis; não é RS contra benchmark.",
                "macro": "Regra de regime e inflação setorial; escala heurística de -8/+8 para 0/100.",
                "composto": "Fundamento 45%, técnico 25%, macro 30%; exige as três dimensões e cobertura mínima de 50% por dimensão.",
                "limites_valuation": _LIMITES_MULTIPLOS[canon],
                "calibrado": False,
            },
        })
    return sorted(resultado, key=lambda r: (r["composto"] is not None, r["composto"] or 0), reverse=True)


@st.cache_data(ttl=1800, show_spinner=False)
def _calcular_scorecard_cache(universo: str, macro_context: dict) -> list[dict]:
    from database.db import get_todos_fundamentos_cache, get_all_price_cache
    from utils.inflation_sectoral import pilar_macro_setorial, get_inflacao_atual

    fund_all = get_todos_fundamentos_cache() or {}
    price_all = get_all_price_cache() or {}
    market = "BR" if str(universo).upper() == "BR" else "US"
    juro_chave = "selic" if market == "BR" else "treasury_10y"
    entradas = (juro_chave, "vix")
    qualidade = macro_context.get("qualidade") or {}
    entradas_validas = all(
        _numero(macro_context.get(k)) is not None
        and (qualidade.get(k) or {}).get("observado", True) is not False
        for k in entradas
    )
    macro_por_setor = {}
    if entradas_validas:
        try:
            inflacao = get_inflacao_atual(market) or {}
        except Exception as exc:
            logger.debug(f"[scorecard] inflação setorial indisponível: {exc}")
            inflacao = {}
        setores = {normalizar_setor(d.get("setor")) for t, d in fund_all.items()
                   if isinstance(d, dict) and t.endswith(".SA") == (market == "BR")}
        for canon in setores.intersection(_LABEL_SETOR):
            try:
                pilar = dict(pilar_macro_setorial(canon, market, macro_context))
                pilar["fontes"] = ["regime"] + (["inflacao_setorial"] if inflacao else [])
                macro_por_setor[canon] = pilar
            except Exception as exc:
                logger.debug(f"[scorecard] macro setor '{canon}' falhou: {exc}")
    return calcular_scorecard_dados(fund_all, price_all, macro_por_setor, market)


def calcular_scorecard_setorial(universo: str = "BR", macro_context: dict | None = None) -> list[dict]:
    """Ranking a partir de caches; cenário explícito integra a chave do cache."""
    contexto = macro_context if macro_context is not None else (st.session_state.get("macro_context", {}) or {})
    return _calcular_scorecard_cache(universo, contexto)
