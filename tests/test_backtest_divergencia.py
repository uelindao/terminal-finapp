"""Testes de utils/backtest_divergencia — resultado prático (PLANO_MACRO M3-1)."""
import numpy as np
import pandas as pd

from utils.backtest_divergencia import (
    forward_ret, forward_rs, matriz_quadrantes, extrair_episodios,
    estatistica_por_quadrante, rodar_backtest,
)
from utils.divergencia_setorial import DIVERG_A, CONFIRMA_BULL, NEUTRO


def test_forward_ret_horizonte():
    idx = pd.date_range("2026-01-01", periods=5, freq="W-FRI")
    r = pd.DataFrame({"x": [0.0, 0.10, 0.10, 0.0, 0.0]}, index=idx)
    fr = forward_ret(r, 2)
    # de t0: (1.10*1.10)-1 = 0.21 sobre (t1,t2)
    assert abs(fr["x"].iloc[0] - 0.21) < 1e-9
    # últimas linhas sem futuro suficiente → NaN
    assert np.isnan(fr["x"].iloc[-1])


def test_forward_rs_subtrai_mediana():
    idx = pd.date_range("2026-01-01", periods=4, freq="W-FRI")
    r = pd.DataFrame({
        "x": [0.0, 0.10, 0.0, 0.0],
        "y": [0.0, 0.00, 0.0, 0.0],
        "z": [0.0, -0.10, 0.0, 0.0],
    }, index=idx)
    fr = forward_rs(r, 1)
    # em t0, forward 1 semana: x=+10%, y=0, z=-10% → mediana 0 → RS x>0, z<0
    assert fr["x"].iloc[0] > 0 and fr["z"].iloc[0] < 0


def test_matriz_quadrantes_alinha_e_classifica():
    idx = pd.date_range("2026-01-01", periods=2, freq="W-FRI")
    tilt = pd.DataFrame({"tilt_a": [2, 2], "tilt_b": [-2, -2]}, index=idx)
    rs = pd.DataFrame({"a": [-0.05, -0.05], "b": [-0.05, -0.05]}, index=idx)
    q = matriz_quadrantes(tilt, rs)
    assert q["a"].iloc[0] == DIVERG_A          # favorecido & fraco
    assert list(q.columns) == ["a", "b"]


def test_extrair_episodios_contiguos():
    idx = pd.date_range("2026-01-01", periods=5, freq="W-FRI")
    q = pd.DataFrame({"a": [NEUTRO, DIVERG_A, DIVERG_A, NEUTRO, DIVERG_A]}, index=idx)
    eps = extrair_episodios(q)
    # 3 episódios: neutro(1), diverg_a(2), neutro(1), diverg_a(1)
    quads = [e["quadrante"] for e in eps]
    assert quads == [NEUTRO, DIVERG_A, NEUTRO, DIVERG_A]
    diverg = [e for e in eps if e["quadrante"] == DIVERG_A]
    assert diverg[0]["comprimento"] == 2 and diverg[0]["data"] == idx[1]


def test_estatistica_agrega_por_quadrante_e_horizonte():
    idx = pd.date_range("2026-01-01", periods=3, freq="W-FRI")
    eps = [
        {"setor": "a", "data": idx[0], "quadrante": DIVERG_A, "comprimento": 2},
        {"setor": "b", "data": idx[0], "quadrante": DIVERG_A, "comprimento": 1},
    ]
    fwd = {13: pd.DataFrame({"a": [0.05, np.nan, np.nan],
                             "b": [-0.03, np.nan, np.nan]}, index=idx)}
    stats = estatistica_por_quadrante(eps, fwd)
    s = stats[DIVERG_A][13]
    assert s["n"] == 2
    assert abs(s["media"] - 0.01) < 1e-9       # média(0.05, -0.03)
    assert s["hit_rate"] == 0.5                # 1 de 2 positivos


def test_estatistica_filtra_min_persistencia():
    idx = pd.date_range("2026-01-01", periods=2, freq="W-FRI")
    eps = [
        {"setor": "a", "data": idx[0], "quadrante": DIVERG_A, "comprimento": 1},
        {"setor": "b", "data": idx[0], "quadrante": DIVERG_A, "comprimento": 4},
    ]
    fwd = {13: pd.DataFrame({"a": [0.05, np.nan], "b": [0.05, np.nan]}, index=idx)}
    stats = estatistica_por_quadrante(eps, fwd, min_persistencia=4)
    assert stats[DIVERG_A][13]["n"] == 1       # só o episódio com comprimento>=4


def test_rodar_backtest_pipeline_completo():
    # 30 semanas: setor "fav" favorecido mas fraco no início (DIVERG_A) que depois
    # sobe forte → forward RS positivo; universo com setores neutros de referência.
    idx = pd.date_range("2025-01-03", periods=30, freq="W-FRI")
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.01, size=(30, 3))
    ret = pd.DataFrame(base, index=idx, columns=["fav", "med", "wk"])
    # tilt: fav sempre favorecido (+2), outros neutros
    tilt = pd.DataFrame({"tilt_fav": 2, "tilt_med": 0, "tilt_wk": 0}, index=idx)
    out = rodar_backtest(ret, tilt, janela_rs=4, horizontes=(4,))
    assert "estatistica" in out and out["n_episodios"] >= 1
    assert isinstance(out["horizontes"], list)


def test_vazio_nao_quebra():
    assert forward_ret(pd.DataFrame(), 4).empty
    assert matriz_quadrantes(pd.DataFrame(), pd.DataFrame()).empty
    assert extrair_episodios(pd.DataFrame()) == []
    assert estatistica_por_quadrante([], {}) == {}
