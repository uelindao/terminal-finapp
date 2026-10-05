import pandas as pd
from utils.fiscal import calcular_semaforo_fiscal


def base():
    return pd.DataFrame({"Divida_Bruta_PIB": [85.,86.,87.,88.,89.,90.,91.],
                         "Saldo_Primario_PIB": [-4.] * 7},
                        index=pd.date_range("2026-01-01", periods=7, freq="MS"))


def test_saldo_deficit_e_tendencia_exatos_em_seis_meses():
    r = calcular_semaforo_fiscal(base())
    assert r["tendencia_divida"] == 6.
    assert r["result_primario"] == -4.
    assert r["status"] == "critico" and r["cobertura"] == 1.


def test_lacuna_nao_vira_comparacao_de_seis_observacoes():
    f = base().drop(base().index[3])
    r = calcular_semaforo_fiscal(f)
    assert r["tendencia_divida"] is None
    assert r["status"] == "neutro"


def test_seis_referencias_nao_sao_seis_meses_de_variacao():
    assert calcular_semaforo_fiscal(base().iloc[1:])["tendencia_divida"] is None


def test_sem_dados_ou_sinal_legado_nao_afirma_estabilidade():
    assert calcular_semaforo_fiscal(pd.DataFrame())["status"] == "neutro"
    legacy = base().rename(columns={"Saldo_Primario_PIB": "Result_Primario"})
    assert calcular_semaforo_fiscal(legacy)["result_primario"] is None
    assert calcular_semaforo_fiscal(legacy)["status"] == "neutro"


def test_zero_e_superavit_preservados_e_nao_rotulados_deficit():
    f = base()
    f["Divida_Bruta_PIB"] = 60.
    f["Saldo_Primario_PIB"] = 0.
    r = calcular_semaforo_fiscal(f)
    assert r["result_primario"] == 0. and r["status"] == "saudavel"
