"""
utils/indicators.py
===================
Indicadores técnicos canônicos — antes copiados inline em vários arquivos
(RSI em 6 lugares, beta em 3, momentum 12-1 em 2+).

Mantêm EXATAMENTE a fórmula que já era usada no terminal:
  - RSI: média simples (rolling) das altas/baixas — NÃO o Wilder EMA — com
    guarda de divisão por zero (loss==0 → NaN).
  - momentum 12-1: preço há 1 mês / preço há 13 meses − 1 (decimal).
  - beta: cov(ativo, bench) / var(bench) sobre retornos alinhados.
"""
from __future__ import annotations

import math

import pandas as pd


def _as_series(x) -> pd.Series:
    if isinstance(x, pd.Series):
        return x.dropna()
    return pd.Series(list(x)).dropna()


def rsi(close, period: int = 14) -> pd.Series:
    """
    RSI (média simples de altas/baixas). Retorna uma Series alinhada a `close`
    (PRESERVA o índice — não faz dropna, p/ quem combina o RSI com outras
    séries); os primeiros `period` pontos são NaN. loss==0 vira NaN (evita inf).
    """
    s = close if isinstance(close, pd.Series) else pd.Series(list(close))
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def rsi_last(close, period: int = 14, default: float = 50.0) -> float:
    """Último valor de RSI como float, com fallback quando indisponível."""
    try:
        s = _as_series(close)
        if len(s) < period + 1:
            return default
        v = rsi(s, period).iloc[-1]
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def momentum_12_1(close) -> float | None:
    """
    Retorno momentum 12-1: preço há 1 mês / preço há 13 meses − 1 (decimal).
    Precisa de ~252 pregões. Retorna None se insuficiente ou preço base ≤ 0.
    Tolera None / entradas vazias (devolve None).
    """
    if close is None:
        return None
    try:
        s = _as_series(close)
    except (TypeError, ValueError):
        return None
    if len(s) < 252:
        return None
    p_antigo = float(s.iloc[-252])
    p_recente = float(s.iloc[-21])
    if p_antigo <= 0:
        return None
    return (p_recente / p_antigo) - 1.0


def beta(asset_rets: pd.Series, bench_rets: pd.Series) -> float | None:
    """
    Beta = cov(ativo, bench) / var(bench) sobre retornos diários alinhados.
    Recebe Series de RETORNOS (não preços). Retorna None se dados insuficientes
    ou var(bench) ≤ 0.
    """
    try:
        df = pd.concat([asset_rets, bench_rets], axis=1).dropna()
        if len(df) < 2:
            return None
        cov = df.cov().iloc[0, 1]
        var = df.iloc[:, 1].var()
        if not var or var <= 0:
            return None
        return float(cov / var)
    except Exception:
        return None
