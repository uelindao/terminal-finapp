"""
utils/setor_rs.py
Relative Strength (RS) line setorial — calcula performance relativa de ETFs setoriais
vs benchmark, normalizada a 100. RS subindo = setor outperforming.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)

ETFS_SETORIAIS_US = {
    "Tecnologia":        "XLK",
    "Financeiro":        "XLF",
    "Energia":           "XLE",
    "Saúde":             "XLV",
    "Industrial":        "XLI",
    "Cons. Discricion.": "XLY",
    "Cons. Básico":      "XLP",
    "Utilities":         "XLU",
    "Real Estate":       "XLRE",
    "Materiais":         "XLB",
    "Comunicação":       "XLC",
}


@dataclass
class RSResult:
    df_rs: "pd.DataFrame"
    ranking_3m: "pd.DataFrame"
    ranking_6m: "pd.DataFrame"
    ranking_12m: "pd.DataFrame"


def calcular_rs_setorial(
    etfs: dict[str, str] = None,
    benchmark: str = "SPY",
    periodo: str = "13mo",
) -> Optional[RSResult]:
    """
    Baixa preços de ETFs setoriais + benchmark via yfinance.
    Calcula RS = setor / benchmark, normalizado a 100 no início.
    Retorna DataFrame de RS + 3 rankings (3m, 6m, 12m).
    """
    import pandas as pd
    import yfinance as yf

    etfs = etfs or ETFS_SETORIAIS_US
    tickers = list(etfs.values()) + [benchmark]
    try:
        df = yf.download(tickers, period=periodo, progress=False, auto_adjust=True)["Close"]
    except Exception:
        logger.error("falha download yfinance RS setorial", exc_info=True)
        return None
    if df is None or df.empty:
        return None
    df = df.dropna(how="all")
    if benchmark not in df.columns:
        return None

    df_rs = pd.DataFrame(index=df.index)
    for nome, tkr in etfs.items():
        if tkr not in df.columns:
            continue
        rs = df[tkr] / df[benchmark]
        rs0 = rs.iloc[0]
        if rs0 == 0 or pd.isna(rs0):
            continue
        df_rs[nome] = 100 * rs / rs0

    if df_rs.empty:
        return None

    def _ranking(df_in, dias):
        if len(df_in) < dias + 1:
            return None
        ini = df_in.iloc[-dias]
        fim = df_in.iloc[-1]
        delta = (fim / ini - 1) * 100
        out = delta.sort_values(ascending=False).reset_index()
        out.columns = ["Setor", "Δ RS (%)"]
        out["Δ RS (%)"] = out["Δ RS (%)"].round(2)
        return out

    return RSResult(
        df_rs=df_rs,
        ranking_3m=_ranking(df_rs, 63),
        ranking_6m=_ranking(df_rs, 126),
        ranking_12m=_ranking(df_rs, 252),
    )
