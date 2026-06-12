"""
utils/price_history.py — leitura centralizada de histórico de preços.

Tenta primeiro o cache Supabase (price_history populado pelo sync_price_history).
Se vazio (ETL ainda não rodou ou ticker não está no screener), cai para
yfinance ao vivo. Isso desacopla o app dos rate-limits de yfinance assim que
o cache estiver populado, mantendo compatibilidade enquanto isso.

A função principal é `obter_close_carteira(tickers, periodo)`. Retorna
DataFrame com índice de datas (DatetimeIndex naive) e uma coluna por ticker
contendo Close ajustado.
"""

from __future__ import annotations
from typing import Sequence
import pandas as pd
import streamlit as st

from utils.logger import get_logger
logger = get_logger(__name__)


_PERIODO_PARA_DIAS = {
    "1mo": 22, "3mo": 66, "6mo": 132,
    "1y": 252, "2y": 504, "3y": 756,
    "5y": 1260, "10y": 2520,
}


@st.cache_data(ttl=900, show_spinner=False)
def obter_close_carteira(
    tickers_tuple: tuple,
    periodo: str = "1y",
) -> pd.DataFrame:
    """
    Retorna DataFrame de Close ajustado (índice=data, colunas=tickers) para o
    conjunto de tickers solicitado. Tenta cache Supabase primeiro; cai para
    yfinance se cache vazio.

    `tickers_tuple` é tuple (não list) por causa do @st.cache_data — listas
    não são hasháveis.
    """
    tickers = list(tickers_tuple)
    if not tickers:
        return pd.DataFrame()

    dias = _PERIODO_PARA_DIAS.get(periodo, 252)

    # 1ª tentativa: cache Supabase
    df_cache = _buscar_do_cache(tickers, dias)
    cobertura = _calcular_cobertura(df_cache, tickers, dias)

    # Se cobertura razoável (>=70% dos tickers e >=70% dos dias), usa cache
    if cobertura >= 0.7:
        return df_cache

    # 2ª tentativa: yfinance ao vivo. Junta com o que conseguiu do cache.
    logger.info(
        f"[price_history] cobertura cache {cobertura:.0%} insuficiente — "
        f"complementando com yfinance ao vivo"
    )
    df_yf = _baixar_do_yfinance(tickers, periodo)

    if df_cache.empty:
        return df_yf
    if df_yf.empty:
        return df_cache

    # Combina: preenche colunas faltantes do cache com yfinance
    df = df_cache.combine_first(df_yf)
    return df


def _buscar_do_cache(tickers: list[str], dias: int) -> pd.DataFrame:
    """Lê do Supabase price_history. Retorna DataFrame ou vazio se erro."""
    try:
        from database.db import get_price_history_batch
        # Para mapear adequadamente: o cache guarda os tickers exatamente como
        # vieram do screener (PETR4.SA, AAPL, etc.). Usa-os direto.
        df = get_price_history_batch(tickers, dias=dias)
        if df is None or df.empty:
            return pd.DataFrame()
        # Normaliza timezone do índice
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)
        return df
    except Exception as e:
        logger.debug(f"[price_history] cache indisponível: {e}")
        return pd.DataFrame()


def _calcular_cobertura(df: pd.DataFrame, tickers: list[str], dias_alvo: int) -> float:
    """Retorna a fração [0,1] de cobertura do DataFrame em relação ao esperado."""
    if df is None or df.empty:
        return 0.0
    tickers_set = set(tickers)
    presentes = sum(1 for t in tickers_set if t in df.columns)
    cob_tickers = presentes / max(len(tickers_set), 1)
    cob_dias = min(len(df), dias_alvo) / max(dias_alvo, 1)
    # Penaliza o pior dos dois (multiplicação aproxima geom. mean)
    return cob_tickers * cob_dias


@st.cache_data(ttl=900, show_spinner=False)
def obter_ohlcv_ativo(ticker: str, periodo: str = "10y") -> pd.DataFrame:
    """
    Retorna DataFrame OHLCV de um único ticker (colunas: Open/High/Low/Close/Volume,
    índice de datas). Tenta cache Supabase price_history; cai para yfinance se vazio.

    Mantém o formato esperado pelo Research/Charts: colunas com capitalização
    Open/High/Low/Close/Volume (compat yfinance).
    """
    dias = _PERIODO_PARA_DIAS.get(periodo, 2520)

    # 1ª tentativa: cache
    try:
        from database.db import get_price_history
        df = get_price_history(ticker, dias=dias)
    except Exception as e:
        logger.debug(f"[price_history] cache ohlcv {ticker}: {e}")
        df = pd.DataFrame()

    # Renomeia colunas para o padrão yfinance (capitalizado) — facilita drop-in
    if not df.empty:
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)
        # Considera cobertura aceitável se tem >= 60% dos dias esperados
        if len(df) >= max(int(dias * 0.6), 30):
            return df

    # 2ª tentativa: yfinance
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=periodo, auto_adjust=True)
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        if not hist.empty and getattr(hist.index, "tz", None) is not None:
            hist.index = hist.index.tz_localize(None)
        return hist
    except Exception as e:
        logger.warning(f"[price_history] yfinance ohlcv {ticker} falhou: {e}")
        return df  # devolve o pouco que tinha do cache (ou vazio)


def _baixar_do_yfinance(tickers: list[str], periodo: str) -> pd.DataFrame:
    """Fallback yfinance ao vivo. Retorna DataFrame ou vazio se falhar."""
    try:
        import yfinance as yf
        hist = yf.download(tickers, period=periodo, auto_adjust=True, progress=False)
        if hist is None or hist.empty:
            return pd.DataFrame()
        # MultiIndex (multi-ticker) vs Index simples (single-ticker)
        if isinstance(hist.columns, pd.MultiIndex):
            try:
                close = hist.xs("Close", axis=1, level=0)
            except KeyError:
                close = hist.xs("Close", axis=1, level=1)
        else:
            close = hist["Close"] if "Close" in hist else hist
            if isinstance(close, pd.Series):
                close = close.to_frame(name=tickers[0])
        if getattr(close.index, "tz", None) is not None:
            close.index = close.index.tz_localize(None)
        return close
    except Exception as e:
        logger.warning(f"[price_history] yfinance fallback falhou: {e}")
        return pd.DataFrame()
