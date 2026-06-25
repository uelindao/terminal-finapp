"""
Testes dos indicadores canônicos (utils/indicators) — garantem que a versão
consolidada reproduz EXATAMENTE a fórmula inline antiga.
"""
import numpy as np
import pandas as pd

from utils.indicators import rsi, rsi_last, momentum_12_1, beta


def _close():
    rng = np.random.default_rng(7)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.015, 300))))


def test_rsi_igual_a_formula_inline():
    s = _close()
    # fórmula inline antiga (health_engine/radar/sync)
    delta = s.diff()
    ganho = delta.clip(lower=0).rolling(14).mean()
    perda = (-delta.clip(upper=0)).rolling(14).mean()
    rs = ganho / perda.replace(0, float("nan"))
    esperado = (100 - (100 / (1 + rs)))
    obtido = rsi(s, 14)
    pd.testing.assert_series_equal(obtido, esperado, check_names=False)
    # rsi_last bate com o último valor
    assert abs(rsi_last(s) - float(esperado.iloc[-1])) < 1e-9


def test_rsi_last_fallback():
    assert rsi_last(pd.Series([1, 2, 3]), 14, default=50.0) == 50.0
    assert rsi_last(pd.Series([], dtype=float)) == 50.0


def test_momentum_12_1():
    s = _close()
    esperado = (float(s.iloc[-21]) / float(s.iloc[-252])) - 1.0
    assert abs(momentum_12_1(s) - esperado) < 1e-12
    assert momentum_12_1(pd.Series(range(100))) is None   # insuficiente


def test_beta():
    rng = np.random.default_rng(3)
    bench = pd.Series(rng.normal(0, 0.01, 200))
    # ativo = 1.5*bench + ruído → beta ~1.5
    ativo = 1.5 * bench + pd.Series(rng.normal(0, 0.002, 200))
    b = beta(ativo, bench)
    assert b is not None and 1.3 < b < 1.7
    # var(bench)=0 → None
    assert beta(pd.Series([0.01] * 50), pd.Series([0.0] * 50)) is None
