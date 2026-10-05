import numpy as np
import pandas as pd
from utils.rotation_backtest import simular_rotacao


def dados():
    idx = pd.bdate_range("2018-01-01", "2022-06-30")
    px = pd.DataFrame({"A": 100., "B": 100., "SPY": 100.}, index=idx)
    sinais = pd.DataFrame({"referencia_em": ["2017-11-30"], "disponivel_em": ["2017-12-15"],
        "quadrante": ["q"], "confirmado": [True]})
    return px, sinais, {"q": {"A": .5, "B": .5}}


def test_custo_inicial_e_total_coerente():
    px, sinais, pesos = dados()
    out = simular_rotacao(px, sinais, pesos, "SPY", custo_bps=10)
    assert out["ok"]
    assert np.isclose(out["curvas"]["estrategia"].iloc[-1], .999)
    assert np.isclose(out["resumo"]["estrategia"]["retorno_total"], -.001)
    assert out["rebalanceamentos"]["turnover"].iloc[0] == 1
    assert (out["rebalanceamentos"]["turnover"].iloc[1:] < 1e-12).all()
    assert out["metodologia"]["point_in_time"] is False
    assert out["avaliacao"]["corte"] < px.index[-1]
    assert np.isclose(out["avaliacao"]["construcao"]["estrategia"]["retorno_total"], -.001)
    assert out["avaliacao"]["reservado"]["estrategia"]["retorno_total"] == 0.


def test_disponibilidade_estrita_execucao_proximo_primeiro_pregao():
    px, sinais, pesos = dados()
    sinais.loc[0, "referencia_em"] = "2018-01-31"
    sinais.loc[0, "disponivel_em"] = "2018-02-01"
    out = simular_rotacao(px, sinais, pesos, "SPY", custo_bps=0)
    assert out["ok"]
    assert out["rebalanceamentos"]["data"].iloc[0] == pd.Timestamp("2018-03-01")
    assert (out["rebalanceamentos"]["sinal_disponivel"] < out["rebalanceamentos"]["data"]).all()


def test_sinal_nao_confirmado_nao_entra():
    px, sinais, pesos = dados()
    sinais["confirmado"] = False
    assert not simular_rotacao(px, sinais, pesos, "SPY")["ok"]
    sinais["confirmado"] = "False"
    assert not simular_rotacao(px, sinais, pesos, "SPY")["ok"]


def test_rebalanceamento_respeita_deriva_e_retorno_antes_execucao():
    px, sinais, pesos = dados()
    px.loc["2018-02-01":, "A"] = 200.
    out = simular_rotacao(px, sinais, pesos, "SPY", custo_bps=0)
    segundo = out["rebalanceamentos"].iloc[1]
    assert np.isclose(out["curvas"].loc["2018-02-01", "estrategia"], 1.5)
    assert np.isclose(segundo["turnover"], 1/3)
    assert np.isclose(out["curvas"]["estrategia"].iloc[-1], 1.5)
    pago = simular_rotacao(px, sinais, pesos, "SPY", custo_bps=10)
    assert np.isclose(pago["rebalanceamentos"]["custo_fracao"].iloc[1], .001/3)


def test_futuro_nao_muda_carteira_anterior():
    px, sinais, pesos = dados()
    out = simular_rotacao(px, sinais, pesos, "SPY", custo_bps=0)
    curto = simular_rotacao(px.loc[:"2021-01-01"], sinais, pesos, "SPY", custo_bps=0)
    pd.testing.assert_frame_equal(out["curvas"].loc[curto["curvas"].index], curto["curvas"])
    futuro = pd.DataFrame({"referencia_em": ["2021-01-31"], "disponivel_em": ["2021-02-20"], "quadrante": ["r"], "confirmado": [True]})
    alterado = simular_rotacao(px, pd.concat([sinais, futuro]), dict(pesos, r={"A": 1.}), "SPY", custo_bps=0)
    pd.testing.assert_frame_equal(out["curvas"].loc[:"2021-02-28"], alterado["curvas"].loc[:"2021-02-28"])


def test_gaps_rejeitam_sem_retorno_zero():
    px, sinais, pesos = dados()
    px.loc["2019-06-03", "A"] = np.nan
    out = simular_rotacao(px, sinais, pesos, "SPY")
    assert not out["ok"] and "lacunas" in out["motivo"]
    assert out["curvas"].empty
    assert out["cobertura"].set_index("ticker").loc["A", "cobertura"] < 1


def test_benchmark_gap_rejeita():
    px, sinais, pesos = dados()
    px.loc["2019-06-03", "SPY"] = np.nan
    assert not simular_rotacao(px, sinais, pesos, "SPY")["ok"]


def test_peso_negativo_escondido_e_soma_invalida_rejeitam():
    px, sinais, pesos = dados()
    for modelo in ({"q": {"A": 1., "B": -.1}}, {"q": {"A": .4}}, {"q": {"A": np.nan}}):
        assert not simular_rotacao(px, sinais, modelo, "SPY")["ok"]


def test_minimo_24_meses_conta_apos_execucao():
    px, sinais, pesos = dados()
    sinais["disponivel_em"] = "2021-01-01"
    assert not simular_rotacao(px, sinais, pesos, "SPY")["ok"]


def test_mesma_serie_benchmark_e_ativo_sem_custo():
    px, sinais, _ = dados()
    px["A"] = np.linspace(100, 180, len(px))
    out = simular_rotacao(px, sinais, {"q": {"A": 1.}}, px["A"], custo_bps=0)
    assert out["ok"]
    np.testing.assert_allclose(out["curvas"]["estrategia"], out["curvas"]["benchmark"])


def test_duplicatas_conflitantes_rejeitadas():
    px, sinais, pesos = dados()
    copia = px.iloc[[20]].copy()
    copia["A"] = 200.
    assert not simular_rotacao(pd.concat([px, copia]), sinais, pesos, "SPY")["ok"]
    assert simular_rotacao(pd.concat([px, px.iloc[[20]]]), sinais, pesos, "SPY")["ok"]


def test_precos_invalidos_em_todos_nao_apagam_dia():
    px, sinais, pesos = dados()
    px.loc["2019-06-03"] = 0.
    out = simular_rotacao(px, sinais, pesos, "SPY")
    assert not out["ok"] and "lacunas" in out["motivo"]
