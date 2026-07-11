"""Testes de utils/setor_series — séries de retorno setorial (PLANO_MACRO M0-1).

Núcleo puro: sem rede, sem Streamlit, fixtures sintéticas.
"""
import numpy as np
import pandas as pd

from utils.setor_series import (
    retorno_diario_setorial,
    retorno_acumulado,
    rs_setorial,
    rs_setorial_atual,
)


def _precos(dias=10):
    idx = pd.date_range("2026-01-01", periods=dias, freq="B")
    # setor X: A1,A2,A3 sobem 1%/dia; setor Y: B1,B2,B3 caem 1%/dia
    dados = {}
    for tk in ("A1", "A2", "A3"):
        dados[tk] = 100.0 * (1.01 ** np.arange(dias))
    for tk in ("B1", "B2", "B3"):
        dados[tk] = 100.0 * (0.99 ** np.arange(dias))
    return pd.DataFrame(dados, index=idx)


_SETOR = {"A1": "x", "A2": "x", "A3": "x", "B1": "y", "B2": "y", "B3": "y"}


def test_retorno_diario_equal_weight():
    r = retorno_diario_setorial(_precos(), _SETOR)
    assert set(r.columns) == {"x", "y"}
    # 1º dia é NaN (pct_change), 2º dia: setor x ~ +1%, setor y ~ -1%
    assert abs(r["x"].iloc[1] - 0.01) < 1e-9
    assert abs(r["y"].iloc[1] + 0.01) < 1e-9


def test_min_tickers_exclui_dia():
    # setor y com só 2 tickers e min_tickers=3 → NaN
    precos = _precos()[["A1", "A2", "A3", "B1", "B2"]]
    setor = {k: _SETOR[k] for k in precos.columns}
    r = retorno_diario_setorial(precos, setor, min_tickers=3)
    assert r["y"].isna().all()          # y nunca atinge 3 válidos
    assert not r["x"].iloc[1:].isna().all()


def test_equal_weight_media_de_tickers_divergentes():
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    precos = pd.DataFrame({
        "A1": [100, 110, 110],   # +10%, 0%
        "A2": [100, 100, 100],   # 0%, 0%
        "A3": [100, 90, 90],     # -10%, 0%
    }, index=idx)
    setor = {"A1": "x", "A2": "x", "A3": "x"}
    r = retorno_diario_setorial(precos, setor)
    # EW do dia 2 = média(+10%,0%,-10%) = 0
    assert abs(r["x"].iloc[1]) < 1e-9


def test_retorno_acumulado_janela():
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    rets = pd.DataFrame({"x": [np.nan, 0.10, 0.10, 0.10, 0.10]}, index=idx)
    cum = retorno_acumulado(rets, janela=2, min_cobertura=0.5)
    # janela 2 terminando no dia 3: (1.1*1.1)-1 = 0.21
    assert abs(cum["x"].iloc[2] - 0.21) < 1e-9


def test_retorno_acumulado_exige_cobertura():
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    rets = pd.DataFrame({"x": [0.01, np.nan, np.nan, np.nan, 0.01]}, index=idx)
    cum = retorno_acumulado(rets, janela=3, min_cobertura=0.8)
    # nenhuma janela de 3 tem >=80% (2.4) de dias válidos → tudo NaN
    assert cum["x"].isna().all()


def test_rs_setorial_subtrai_mediana():
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    rets = pd.DataFrame({
        "x": [np.nan, 0.10, 0.10, 0.10],   # forte
        "y": [np.nan, 0.00, 0.00, 0.00],   # mediana
        "z": [np.nan, -0.10, -0.10, -0.10],  # fraco
    }, index=idx)
    rs = rs_setorial(rets, janela=2, min_cobertura=0.5)
    ult = rs.dropna(how="all").iloc[-1]
    # mediana transversal é o setor y (~0) → x positivo, z negativo, y ~0
    assert ult["x"] > 0 and ult["z"] < 0
    assert abs(ult["y"]) < 1e-9


def test_rs_setorial_atual_dict():
    r = retorno_diario_setorial(_precos(20), _SETOR)
    atual = rs_setorial_atual(r, janela=5)
    assert isinstance(atual, dict) and "x" in atual and "y" in atual
    assert atual["x"] > atual["y"]      # x subiu, y caiu


def test_vazio_nao_quebra():
    assert retorno_diario_setorial(pd.DataFrame(), {}).empty
    assert retorno_acumulado(pd.DataFrame()).empty
    assert rs_setorial(pd.DataFrame()).empty
    assert rs_setorial_atual(pd.DataFrame()) == {}


def test_setor_sem_mapeamento_ignorado():
    precos = _precos()
    setor = {"A1": "x", "A2": "x", "A3": "x"}   # B* sem setor
    r = retorno_diario_setorial(precos, setor)
    assert list(r.columns) == ["x"]
