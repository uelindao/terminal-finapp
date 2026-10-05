"""Rotação descritiva com preços ajustados, moeda e janela explícitos.

Núcleo puro; loader limita leituras a 15 proxies do cache. Não baixa preços.
Retornos são decimais. Nenhum fundamento é imputado a títulos ou ouro.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from utils.st_fallback import st

HORIZONTES_MESES = (3, 6, 12, 24)
FX_TICKER = "BRL=X"
MAX_PROXIES = 15


def _proxy(ticker, label, moeda, mercado, classe, risco, fonte, **extra):
    return dict(ticker=ticker, label=label, moeda=moeda, mercado=mercado,
                tipo="classe", classe=classe, risco=risco, fonte=fonte,
                ajustado=True, **extra)


PROXIES_CLASSES = [
    _proxy("BOVV11.SA", "Ações Brasil", "BRL", "BR", "acoes", "Lucros, atividade e prêmio de risco das ações do Ibovespa.", "https://www.itnow.com.br/bovv11/"),
    _proxy("LFTS11.SA", "Pós-fixado Selic", "BRL", "BR", "pos_fixado", "Carregamento ligado à Selic; cotas e custos próprios.", "https://www.investoetf.com/etf/lfts11/"),
    _proxy("IRFM11.SA", "Prefixados", "BRL", "BR", "juros_nominais", "Marcação depende da curva nominal e do prazo dos títulos.", "https://www.itnow.com.br/irfm11/documentos/"),
    _proxy("B5P211.SA", "IPCA até 5 anos", "BRL", "BR", "juros_reais", "NTN-Bs abaixo de 5 anos: juros reais e inflação.", "https://www.itnow.com.br/b5p211/"),
    _proxy("IMAB11.SA", "IPCA amplo", "BRL", "BR", "juros_reais", "Carteira IMA-B: mudanças na curva real e duration.", "https://www.itnow.com.br/imab11/"),
    _proxy("GOLD11.SA", "Ouro em reais", "BRL", "BR", "ouro", "Ouro e exposição cambial do produto já entram na cota em reais.", "https://www.xpasset.com.br/fundos/gold11/"),
    _proxy("XFIX11.SA", "Fundos imobiliários", "BRL", "BR", "imobiliario", "Proxy IFIX-L: juros, crédito, liquidez e renda imobiliária.", "https://www.xpasset.com.br/fundos-etfs/"),
    _proxy("SPY", "Ações EUA", "USD", "US", "acoes", "Lucros, atividade, valuation e composição do S&P 500.", "https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy"),
    _proxy("IEF", "Treasury 7–10 anos", "USD", "US", "juros_nominais", "Curva nominal de Treasuries e prazo dos títulos.", "https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf"),
    _proxy("TIP", "Treasury indexado", "USD", "US", "juros_reais", "Juros reais, inflação realizada e prazo dos TIPS.", "https://www.ishares.com/us/products/239467/ishares-tips-bond-etf"),
    _proxy("LQD", "Crédito investment grade", "USD", "US", "credito", "Curva nominal, spreads e risco dos emissores corporativos.", "https://www.ishares.com/us/product_info/fund/overview/LQD.htm"),
    _proxy("HYG", "Crédito high yield", "USD", "US", "credito", "Spreads, inadimplência, recuperação e liquidez.", "https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf"),
    _proxy("GLD", "Ouro em dólares", "USD", "US", "ouro", "Preço do ouro em dólares e despesas; sem valuation de lucros.", "https://www.ssga.com/us/en/individual/etfs/spdr-gold-shares-gld"),
]
_ETFS_US = {
    "tecnologia": ("XLK", "Tecnologia"), "financeiro": ("XLF", "Financeiro"),
    "energia": ("XLE", "Energia"), "saude": ("XLV", "Saúde"),
    "industria": ("XLI", "Indústria"), "consumo_ciclico": ("XLY", "Consumo cíclico"),
    "consumo_defensivo": ("XLP", "Consumo defensivo"), "utilities": ("XLU", "Utilities"),
    "imobiliario": ("XLRE", "Imobiliário"), "materiais": ("XLB", "Materiais"),
    "comunicacao": ("XLC", "Comunicação"),
}


def metadata_padrao(mercado="BR", tipo="Classes"):
    if str(tipo).lower().startswith("setor") and mercado == "US":
        rows = []
        for setor, (ticker, label) in _ETFS_US.items():
            meta = _proxy(ticker, label, "USD", "US", "acoes",
                          "Concentração e risco das empresas do setor representado pelo ETF.",
                          "https://www.ssga.com/us/en/individual/etfs")
            meta.update(tipo="setor", setor=setor)
            rows.append(meta)
        return rows
    return [dict(m) for m in PROXIES_CLASSES if m["mercado"] == mercado]


def normalizar_precos(precos):
    """Observações não positivas e datas duplicadas são inválidas; gaps ficam."""
    if precos is None or not isinstance(precos, pd.DataFrame) or precos.empty:
        return pd.DataFrame()
    if not precos.columns.is_unique or isinstance(precos.columns, pd.MultiIndex):
        raise ValueError("As colunas devem identificar proxies únicos.")
    frame = precos.copy()
    datas = pd.to_datetime(frame.index, utc=True, errors="coerce")
    frame.index = datas.tz_convert(None).normalize()
    frame = frame.loc[~frame.index.isna()]
    frame = frame.loc[~frame.index.duplicated(keep=False)].sort_index()
    for coluna in frame:
        serie = frame[coluna].map(lambda v: np.nan if isinstance(v, (bool, np.bool_)) else v)
        frame[coluna] = pd.to_numeric(serie, errors="coerce")
    return frame.replace([np.inf, -np.inf], np.nan).where(frame > 0)


def converter_retorno_usd_brl(retorno_ativo, retorno_fx):
    """(1+r ativo)*(1+r FX)-1; ambas as entradas nas mesmas duas datas."""
    try:
        ativo, fx = float(retorno_ativo), float(retorno_fx)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(ativo) or not math.isfinite(fx) or ativo <= -1 or fx <= -1:
        return None
    return (1 + ativo) * (1 + fx) - 1


def _janela_referencia(frame, benchmark, meses, final, max_defasagem, min_cobertura):
    if benchmark not in frame:
        return None, None, pd.DatetimeIndex([]), "Benchmark ausente no histórico."
    ref = frame[benchmark].dropna()
    ref = ref.loc[ref.index <= final]
    if len(ref) < 2:
        return None, None, pd.DatetimeIndex([]), "Benchmark sem observações suficientes."
    fim = ref.index[-1]
    if (final - fim).days > max_defasagem:
        return None, None, pd.DatetimeIndex([]), "Benchmark desatualizado."
    alvo = fim - pd.DateOffset(months=meses)
    candidatos = ref.loc[ref.index >= alvo]
    inicio = candidatos.index[0]
    if (inicio - alvo).days > max_defasagem or inicio == fim:
        return None, None, pd.DatetimeIndex([]), "Histórico não cobre o horizonte selecionado."
    calendario = ref.loc[inicio:fim].index
    esperadas = len(pd.bdate_range(inicio, fim))
    if esperadas and len(calendario) / esperadas < min_cobertura:
        return inicio, fim, calendario, "Benchmark sem cobertura diária suficiente para a janela."
    return inicio, fim, calendario, ""


def calcular_matriz_rotacao(precos, metadata, horizonte_meses=6, moeda="nativa",
                           benchmark=None, benchmark_moeda=None, data_final=None,
                           min_cobertura=0.8, max_defasagem_dias=7, scorecards=None):
    """Comparação na mesma moeda e extremidades observadas do benchmark.

    RS=(1+r ativo)/(1+r benchmark)-1. Gaps internos não são preenchidos.
    USD/BRL usa BRL por USD; BRL/USD usa a cotação inversa. Volatilidade
    descritiva anualizada requer 20 retornos válidos. Sem data_final, a janela
    precisa terminar em cotação recente em relação à data atual; estudos
    históricos devem informar sua data de corte explicitamente.
    """
    if horizonte_meses not in HORIZONTES_MESES:
        raise ValueError("Horizonte deve ser 3, 6, 12 ou 24 meses.")
    if moeda not in ("nativa", "BRL", "USD"):
        raise ValueError("Moeda deve ser nativa, BRL ou USD.")
    if not 0 <= min_cobertura <= 1:
        raise ValueError("Cobertura deve estar entre zero e um.")
    frame = normalizar_precos(precos)
    final = pd.Timestamp(data_final) if data_final is not None else pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None).normalize()
    if final.tzinfo is not None:
        final = final.tz_convert(None)
    final = final.normalize()
    frame = frame.loc[frame.index <= final]
    rows = []
    for meta in metadata:
        ticker, origem = meta["ticker"], meta.get("moeda")
        destino = origem if moeda == "nativa" else moeda
        bmk = benchmark or meta.get("benchmark") or ("BOVA11.SA" if origem == "BRL" else "SPY")
        unidades = {m["ticker"]: m.get("moeda") for m in PROXIES_CLASSES + list(metadata)}
        unidades["BOVA11.SA"] = "BRL"
        unidade_bmk = benchmark_moeda or meta.get("benchmark_moeda") or unidades.get(bmk)
        row = dict(meta, moeda_origem=origem, moeda_exibicao=destino, benchmark=bmk,
                   benchmark_moeda=unidade_bmk, horizonte_meses=horizonte_meses,
                   inicio=None, fim=None, retorno_nativo=None, retorno=None,
                   retorno_benchmark=None, relativo=None, retorno_fx=None,
                   contribuicao_fx=None, volatilidade=None, cobertura=0.0,
                   n_observacoes=0, status="indisponível", motivo="",
                   fundamento=None, valuation=None, macro=None, scorecard={})
        if any(m not in ("BRL", "USD") for m in (origem, destino, unidade_bmk)):
            row["motivo"] = "Moeda do ativo ou benchmark não identificada."
            rows.append(row)
            continue
        inicio, fim, calendario, motivo = _janela_referencia(frame, bmk, horizonte_meses, final, max_defasagem_dias, min_cobertura)
        row.update(inicio=inicio, fim=fim)
        if motivo:
            row["motivo"] = motivo
            rows.append(row)
            continue
        if ticker not in frame:
            row["motivo"] = "Proxy ausente no cache."
            rows.append(row)
            continue
        cols = list(dict.fromkeys([ticker, bmk] + ([FX_TICKER] if origem != destino or unidade_bmk != destino else [])))
        if any(c not in frame for c in cols):
            row["motivo"] = "Câmbio ausente: conversão exige BRL por USD nas mesmas datas."
            rows.append(row)
            continue
        pares = frame.loc[calendario, cols]
        validos = pares.notna().all(axis=1)
        row.update(n_observacoes=int(validos.sum()),
                   cobertura=float(validos.mean()) if len(validos) else 0.0)
        if not validos.loc[inicio] or not validos.loc[fim]:
            row["motivo"] = "Observação ausente ou inválida em uma extremidade comum."
            rows.append(row)
            continue
        if row["cobertura"] < min_cobertura:
            row["motivo"] = "Cobertura abaixo do mínimo; retorno suspenso."
            rows.append(row)
            continue
        if meta.get("ajustado") is not True:
            row["motivo"] = "Série sem confirmação de preços ajustados."
            rows.append(row)
            continue
        ativo, ref = pares[ticker], pares[bmk]
        nativo = float(ativo.loc[fim] / ativo.loc[inicio] - 1)
        fx = pares[FX_TICKER] if FX_TICKER in pares else None

        def convertida(serie, unidade):
            if unidade == destino:
                return serie
            return serie * fx if unidade == "USD" else serie / fx

        convertido, bmk_convertido = convertida(ativo, origem), convertida(ref, unidade_bmk)
        r = float(convertido.loc[fim] / convertido.loc[inicio] - 1)
        r_bmk = float(bmk_convertido.loc[fim] / bmk_convertido.loc[inicio] - 1)
        row.update(retorno_nativo=nativo, retorno=r, retorno_benchmark=r_bmk,
                   relativo=(1 + r) / (1 + r_bmk) - 1, status="observado")
        if origem != destino:
            r_fx = float(fx.loc[fim] / fx.loc[inicio] - 1)
            if origem == "BRL":
                r_fx = 1 / (1 + r_fx) - 1
            row.update(retorno_fx=r_fx, contribuicao_fx=(1 + nativo) * r_fx)
        rets = convertido.pct_change(fill_method=None).dropna()
        if len(rets) >= 20:
            row["volatilidade"] = float(rets.std(ddof=1) * np.sqrt(252))
        sc = (scorecards or {}).get(meta.get("setor"), {}) if meta.get("tipo") == "setor" else {}
        row.update(fundamento=sc.get("fundamento"), valuation=sc.get("valuation"),
                   macro=sc.get("macro"), scorecard=sc)
        rows.append(row)
    return pd.DataFrame(rows)


def trajetoria_comparada(precos, row):
    """Patrimônio normalizado a 100; gaps preservados no traçado."""
    if row.get("status") != "observado" or row.get("inicio") is None:
        return pd.DataFrame()
    sub = normalizar_precos(precos).loc[row["inicio"]:row["fim"]]
    fx = sub.get(FX_TICKER)
    destino = row["moeda_exibicao"]

    def serie(ticker, unidade):
        s = sub[ticker]
        if unidade != destino:
            s = s * fx if unidade == "USD" else s / fx
        return s / s.loc[row["inicio"]] * 100

    return pd.DataFrame({"Ativo": serie(row["ticker"], row["moeda_origem"]),
                         "Benchmark": serie(row["benchmark"], row["benchmark_moeda"])})


def matriz_setores_snapshot(snapshot, scorecards, horizonte_meses=3):
    """Legacy BR tem só RS 3m versus mediana EW. Outros horizontes ficam vazios."""
    from utils.setores import LABEL_SETOR
    dados = snapshot or {}
    horizontes = dados.get("rs_por_horizonte") or {}
    rs = horizontes.get(str(horizonte_meses), horizontes.get(horizonte_meses))
    if rs is None:
        rs = dados.get("rs", {}) if horizonte_meses == 3 else {}
    out = []
    for sc in scorecards:
        setor = sc["setor"]
        value = (rs or {}).get(setor)
        try:
            value = float(value) if value is not None and not isinstance(value, bool) and math.isfinite(float(value)) else None
        except (TypeError, ValueError):
            value = None
        out.append(dict(sc, label=LABEL_SETOR.get(setor, setor), relativo=value,
                        horizonte_meses=horizonte_meses, moeda_exibicao="BRL",
                        benchmark="Mediana dos setores BR (equal-weight)",
                        metodo_relativo="Diferença do retorno acumulado do setor e da mediana; unidade: pontos percentuais.",
                        data_snapshot=dados.get("data"), retorno=None,
                        fonte="Snapshot semanal de universo atual; viés de survivorship.",
                        status="observado" if value is not None else "indisponível"))
    return pd.DataFrame(out)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_precos_matriz(tickers: tuple[str, ...], dias=550):
    """Leitura limitada do cache. Não baixa preços nem usa fallback live."""
    if len(set(tickers)) > MAX_PROXIES:
        raise ValueError("No máximo 15 proxies por leitura.")
    from database.db import get_price_history_batch
    return get_price_history_batch(list(dict.fromkeys(tickers)), dias=dias)
