"""Testes de utils/divergencia_setorial — matriz de quadrantes (PLANO_MACRO M2-1/M2-2)."""
import pandas as pd

from utils.divergencia_setorial import (
    classificar_quadrante, matriz_divergencia, dias_em_quadrante,
    CONFIRMA_BULL, CONFIRMA_BEAR, DIVERG_A, DIVERG_B, CATCH_UP, NEUTRO,
)


# ── classificação ─────────────────────────────────────────────────────────────

def test_quadrantes_basicos():
    assert classificar_quadrante(2, 0.05) == CONFIRMA_BULL     # favorecido & forte
    assert classificar_quadrante(2, -0.05) == DIVERG_A         # favorecido & fraco
    assert classificar_quadrante(2, 0.0) == CATCH_UP           # favorecido & neutro
    assert classificar_quadrante(-2, -0.05) == CONFIRMA_BEAR   # penalizado & fraco
    assert classificar_quadrante(-2, 0.05) == DIVERG_B         # penalizado & forte
    assert classificar_quadrante(0, 0.05) == NEUTRO            # tilt neutro


def test_limiares_configuraveis():
    # rs 0.015 abaixo do limiar default 0.02 → não conta como forte
    assert classificar_quadrante(2, 0.015) == CATCH_UP
    assert classificar_quadrante(2, 0.015, limiar_rs=0.01) == CONFIRMA_BULL


def test_none_e_nan_viram_neutro():
    assert classificar_quadrante(None, 0.05) == NEUTRO
    assert classificar_quadrante(2, None) == NEUTRO
    assert classificar_quadrante(float("nan"), 0.05) == NEUTRO


# ── matriz ────────────────────────────────────────────────────────────────────

def test_matriz_so_setores_em_ambos():
    tilts = {"a": 2, "b": -2, "c": 1}
    rs = {"a": -0.05, "b": 0.05}          # c só em tilts → ignorado
    m = matriz_divergencia(tilts, rs)
    assert {i["setor"] for i in m} == {"a", "b"}


def test_matriz_marca_divergencias():
    tilts = {"a": 2, "b": -2}
    rs = {"a": -0.06, "b": 0.06}          # ambos divergência
    m = matriz_divergencia(tilts, rs)
    assert all(i["is_divergencia"] for i in m)
    quads = {i["setor"]: i["quadrante"] for i in m}
    assert quads["a"] == DIVERG_A and quads["b"] == DIVERG_B


def test_apenas_divergencias_filtra():
    tilts = {"a": 2, "b": 2}
    rs = {"a": -0.06, "b": 0.06}          # a=DIVERG_A, b=CONFIRMA_BULL
    m = matriz_divergencia(tilts, rs, apenas_divergencias=True)
    assert [i["setor"] for i in m] == ["a"]


def test_ordena_por_magnitude_desc():
    tilts = {"forte": 4, "leve": 1}
    rs = {"forte": -0.10, "leve": -0.03}  # forte diverge mais
    m = matriz_divergencia(tilts, rs)
    assert m[0]["setor"] == "forte"
    assert m[0]["magnitude"] > m[1]["magnitude"]


def test_leitura_presente():
    m = matriz_divergencia({"a": 2}, {"a": -0.05})
    assert m[0]["leitura"] and "checar micro" in m[0]["leitura"]


# ── persistência ──────────────────────────────────────────────────────────────

def test_dias_em_quadrante_conta_streak_recente():
    s = pd.Series([NEUTRO, DIVERG_A, DIVERG_A, DIVERG_A])
    assert dias_em_quadrante(s) == 3


def test_dias_em_quadrante_reset_ao_trocar():
    s = pd.Series([DIVERG_A, DIVERG_A, CONFIRMA_BULL])
    assert dias_em_quadrante(s) == 1


def test_dias_em_quadrante_vazio():
    assert dias_em_quadrante(pd.Series([], dtype=object)) == 0
    assert dias_em_quadrante(None) == 0
