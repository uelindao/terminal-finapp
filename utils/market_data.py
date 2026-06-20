"""
Helper centralizada de dados de mercado — yfinance + cache.

Por que existir?
  - Várias páginas baixam yf.download(tickers, period="5d") múltiplas vezes
    por render (Home, Dashboard, Watchlists, Portfolio).
  - Cada chamada vai pra rede mesmo com tickers iguais (cache_data por
    closure não compartilha entre módulos).
  - Aqui: uma helper @st.cache_data global, batches grandes, TTL único.

Uso:
    from utils.market_data import bulk_close_history

    series = bulk_close_history(tuple(["WEGE3.SA","PETR4.SA"]), period="1mo")
    # series = {"WEGE3.SA": [12.3, 12.4, ...], "PETR4.SA": [...]}

Garantias:
  - Argumentos hashable (tuple) — st.cache_data exige.
  - Período padrão "1mo" cobre sparkline 30d com folga.
  - TTL 300s (5min) — alinhado com taxa de atualização do mercado intraday.
  - Tickers já com sufixo .SA (mapeamento upstream).
  - Falhas silenciosas: ticker sem dado retorna [] (não None).
"""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st
import yfinance as yf

logger = logging.getLogger(__name__)
logging.getLogger('yfinance').setLevel(logging.CRITICAL)


@st.cache_data(ttl=300, show_spinner=False)
def bulk_close_history(
    tickers: tuple[str, ...],
    period: str = "1mo",
) -> dict[str, list[float]]:
    """
    Baixa séries de Close para múltiplos tickers em UMA chamada batch.

    Args:
        tickers: tuple de tickers (e.g. ("WEGE3.SA", "AAPL"))
        period: período yfinance ("5d","1mo","3mo","1y", etc.)

    Returns:
        dict {ticker: [floats ordenados cronologicamente]}
        Tickers sem dado retornam [].
    """
    if not tickers:
        return {}

    out: dict[str, list[float]] = {t: [] for t in tickers}
    try:
        raw = yf.download(
            list(tickers),
            period      = period,
            auto_adjust = True,
            progress    = False,
            threads     = True,
        )
        if raw is None or raw.empty:
            return out

        # Extrai os Close
        if isinstance(raw.columns, pd.MultiIndex):
            try:
                close = raw.xs('Close', axis=1, level=0)
            except KeyError:
                close = raw.xs('Close', axis=1, level=1)
        else:
            close = raw.get('Close', raw)

        if isinstance(close, pd.Series):
            # single ticker case
            close = close.to_frame(name=tickers[0])
        close = close.ffill()

        for t in tickers:
            if t in close.columns:
                s = close[t].dropna()
                if len(s) > 0:
                    out[t] = [float(x) for x in s.tolist()]
    except Exception as e:
        logger.warning(f"[market_data] bulk_close_history({len(tickers)}) falhou: {e}")

    return out


@st.cache_data(ttl=300, show_spinner=False)
def bulk_var_dia(
    tickers: tuple[str, ...],
) -> dict[str, dict]:
    """
    Wrapper otimizado para o caso muito comum de "preço atual + var dia".
    Roda bulk_close_history(period="5d") e calcula derivadas.

    Returns:
        {ticker: {"preco": float, "var_1d": float}}
    """
    series = bulk_close_history(tickers, period="5d")
    out: dict[str, dict] = {}
    for t, s in series.items():
        if len(s) >= 2:
            p_atual = s[-1]
            p_ontem = s[-2]
            try:
                var = ((p_atual / p_ontem) - 1) * 100 if p_ontem > 0 else 0.0
            except Exception:
                var = 0.0
            out[t] = {"preco": p_atual, "var_1d": var}
    return out


@st.cache_data(ttl=300, show_spinner=False)
def bulk_var_periodo(
    tickers: tuple[str, ...],
    period: str = "1mo",
) -> dict[str, dict]:
    """
    Wrapper completo: preço, var dia, var período e série 30d em uma chamada.

    Returns:
        {ticker: {"preco","var_1d","var_periodo","serie"}}
    """
    series = bulk_close_history(tickers, period=period)
    out: dict[str, dict] = {}
    for t, s in series.items():
        if len(s) >= 2:
            p_atual    = s[-1]
            p_ontem    = s[-2]
            p_inicial  = s[0]
            try:
                v_1d = ((p_atual / p_ontem)   - 1) * 100 if p_ontem > 0 else 0.0
                v_pd = ((p_atual / p_inicial) - 1) * 100 if p_inicial > 0 else 0.0
            except Exception:
                v_1d, v_pd = 0.0, 0.0
            out[t] = {
                "preco":       p_atual,
                "var_1d":      v_1d,
                "var_periodo": v_pd,
                "serie":       s[-30:],
            }
    return out
