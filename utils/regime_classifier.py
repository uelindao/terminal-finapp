"""
utils/regime_classifier.py
Classificador automático de regime macro: expansão / pico / contração / vale.

Lógica: 4 sinais binários (yield curve invertida, VIX alto, CPI acelerando,
momentum negativo). Soma → fase. Probabilidade é heurística.

Não substitui análise discricionária — é um termômetro top-down auxiliar.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RegimeResult:
    fase: str            # "expansao" | "pico" | "contracao" | "vale"
    probabilidade: float  # 0.0-1.0
    score_sinais: int     # 0-4
    sinais: dict          # {"yield_invertida": True, ...}
    leitura: str          # texto curto explicativo


# Momentum 12-1 consolidado em utils/indicators (era duplicado aqui e no
# health_engine). Recebe ~13 meses de dados diários (~252 pregões).
from utils.indicators import momentum_12_1 as _momentum_12_1


def classificar_regime(
    t10y: Optional[float],
    t2y: Optional[float],
    vix: Optional[float],
    cpi_yoy_serie: Optional[list[float]],  # últimos 3+ valores mensais
    spy_serie: Optional[list[float]],       # ~252 dias
    ibov_serie: Optional[list[float]],      # ~252 dias
) -> RegimeResult:
    """
    Recebe leituras macro atuais + séries curtas para classificar a fase do ciclo.

    Tolera entradas None — sinais com input None contam como False mas a
    probabilidade é descontada.
    """
    sinais: dict[str, Optional[bool]] = {}

    # S1: yield curve invertida (T10Y - T2Y < 0)
    if t10y is not None and t2y is not None:
        sinais["yield_invertida"] = (t10y - t2y) < 0.0
    else:
        sinais["yield_invertida"] = None

    # S2: VIX alto (> 20)
    sinais["vix_alto"] = (vix is not None and vix > 20.0)

    # S3: CPI YoY acelerando últimos 3 valores
    if cpi_yoy_serie and len(cpi_yoy_serie) >= 3:
        a, b, c = cpi_yoy_serie[-3], cpi_yoy_serie[-2], cpi_yoy_serie[-1]
        sinais["cpi_acelerando"] = (c > b > a)
    else:
        sinais["cpi_acelerando"] = None

    # S4: momentum 12-1 SPY E IBOV ambos negativos
    mom_spy = _momentum_12_1(spy_serie or [])
    mom_ibov = _momentum_12_1(ibov_serie or [])
    if mom_spy is not None and mom_ibov is not None:
        sinais["momentum_negativo"] = (mom_spy < 0) and (mom_ibov < 0)
    else:
        sinais["momentum_negativo"] = None

    # Score: True = 1, False = 0, None = 0 (não conta)
    score = sum(1 for v in sinais.values() if v is True)
    sinais_validos = sum(1 for v in sinais.values() if v is not None)

    # Classificação
    if score <= 1:
        fase = "expansao"
    elif score == 2:
        fase = "pico"
    elif score == 3:
        fase = "contracao"
    else:
        fase = "vale"

    # Probabilidade heurística: base 0.55, +0.10 por sinal ativo, desconto por None
    prob = 0.55 + 0.10 * score
    if sinais_validos < 4:
        prob -= 0.05 * (4 - sinais_validos)
    prob = max(0.40, min(0.95, prob))

    leitura_map = {
        "expansao":  "Sinais consistentes com expansão. Risco-on tende a performar.",
        "pico":      "Sinais mistos. Atenção: cíclicos podem estar precificando próximos meses ruins.",
        "contracao": "Maioria dos sinais negativos. Posicionamento defensivo prudente.",
        "vale":      "Todos os sinais negativos. Final de ciclo provável — montagem gradual de cíclicos pode fazer sentido para horizonte longo.",
    }

    return RegimeResult(
        fase=fase,
        probabilidade=round(prob, 2),
        score_sinais=score,
        sinais=sinais,
        leitura=leitura_map[fase],
    )


def classificar_regime_do_macro_context() -> RegimeResult:
    """
    Wrapper: busca os inputs do macro_context + yfinance e classifica.

    Fonte de T2Y: yfinance ^IRX (13-week Treasury bill, proxy já usada em
    ciclo_economico.py). T10Y via ^TNX. VIX via ^VIX. CPI YoY via FRED
    (CPIAUCSL) com fallback a snapshot Supabase. SPY/IBOV via yfinance.
    """
    import yfinance as yf

    # T10Y e VIX do macro_context
    try:
        from utils.macro_context import _fetch_macro_rapido
        macro = _fetch_macro_rapido()
    except Exception:
        logger.error("falha ao buscar macro rápido", exc_info=True)
        macro = {}

    t10y = macro.get("treasury_10y") or macro.get("t10y")
    vix = macro.get("vix")

    # T2Y: yfinance ^IRX (13-week) — proxy consistente com ciclo_economico.py
    t2y = None
    try:
        hist_irx = yf.Ticker("^IRX").history(period="5d")
        if hist_irx is not None and not hist_irx.empty:
            t2y = float(hist_irx["Close"].dropna().iloc[-1])
    except Exception:
        logger.warning("falha ao buscar T2Y via ^IRX", exc_info=True)

    # CPI YoY: tenta FRED snapshot, senão calcula de CPIAUCSL via yfinance
    cpi_serie = None
    try:
        from utils.macro_supabase import carregar_snapshot
        df_global = carregar_snapshot("fred_global", max_age_days=7)
        if (
            df_global is not None
            and not df_global.empty
            and "CPI_YOY" in df_global.columns
        ):
            cpi_yoy = df_global["CPI_YOY"].dropna()
            if len(cpi_yoy) >= 3:
                cpi_serie = cpi_yoy.tail(6).tolist()
    except Exception:
        logger.debug("CPI YoY indisponível via snapshot", exc_info=True)

    # Nota: removido fallback de yf.Ticker("CPIAUCSL") — CPIAUCSL é série FRED,
    # não ticker yfinance; chamada nunca retornaria dado. Se snapshot estiver
    # vazio o sinal cpi_acelerando vira None e a probabilidade do regime já
    # se ajusta (desconto por sinal indisponível).

    # SPY e IBOV séries (~14 meses para momentum 12-1)
    spy = None
    try:
        spy_hist = yf.Ticker("SPY").history(period="14mo")
        if spy_hist is not None and not spy_hist.empty:
            spy = spy_hist["Close"].dropna().tolist()
    except Exception:
        logger.warning("falha ao buscar SPY", exc_info=True)

    ibov = None
    try:
        ibov_hist = yf.Ticker("^BVSP").history(period="14mo")
        if ibov_hist is not None and not ibov_hist.empty:
            ibov = ibov_hist["Close"].dropna().tolist()
    except Exception:
        logger.warning("falha ao buscar IBOV", exc_info=True)

    return classificar_regime(t10y, t2y, vix, cpi_serie, spy, ibov)
