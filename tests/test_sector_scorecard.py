"""Testes offline das dimensões independentes do scorecard setorial."""
from unittest.mock import patch

import pytest

import utils.sector_scorecard as sc


def _fake_caches():
    # O health total propositalmente contradiz parte dos fundamentos.
    health = [
        {"ticker": "ITUB4.SA", "score": 10},
        {"ticker": "BBAS3.SA", "score": 10},
        {"ticker": "MGLU3.SA", "score": 95},
        {"ticker": "LREN3.SA", "score": 95},
    ]
    fund = {
        "ITUB4.SA": {"setor": "Financial Services", "roe%": 22, "margem%": 20, "p/l": 10, "p/vp": 1.2},
        "BBAS3.SA": {"setor": "Financial Services", "roe%": 25, "margem%": 25, "p/l": 8, "p/vp": 1.0},
        "MGLU3.SA": {"setor": "Consumer Cyclical", "roe%": -5, "margem%": -2, "p/l": 60, "p/vp": 8},
        "LREN3.SA": {"setor": "Consumer Cyclical", "roe%": 8, "margem%": 4, "p/l": 40, "p/vp": 8},
    }
    price = {
        "ITUB4.SA": {"var_12m": 25.0}, "BBAS3.SA": {"var_12m": 20.0},
        "MGLU3.SA": {"var_12m": -40.0}, "LREN3.SA": {"var_12m": -10.0},
    }
    return health, fund, price


def _by_sector(rows):
    return {row["setor"]: row for row in rows}


def _macro():
    return {"financeiro": {"pontos": 2}, "consumo_ciclico": {"pontos": -2}}


def test_helpers_puros_e_ausencias():
    assert sc._macro_para_0_100(0) == 50
    assert sc._macro_para_0_100(8) == 100
    assert sc._macro_para_0_100(-8) == 0
    assert sc._composto(100, 100, 100) == 100.0
    assert sc._composto(0, 0, 0) == 0.0
    assert sc._composto(100, None, 100) is None
    assert sc._veredicto(70, 2)[0] == "overweight"
    assert sc._veredicto(30, -2)[0] == "underweight"
    assert sc._veredicto(None)[0] == "dados insuficientes"


def test_scorecard_ordena_e_cruza_dimensoes_observadas():
    _, fund, price = _fake_caches()
    res = sc.calcular_scorecard_dados(fund, price, _macro())
    setores = _by_sector(res)
    fin, con = setores["financeiro"], setores["consumo_ciclico"]
    assert fin["composto"] > con["composto"]
    assert fin["fundamento"] == 100
    assert fin["macro_pontos"] > 0 and con["macro_pontos"] < 0
    assert fin["tecnico"] == 100.0 and con["tecnico"] == 0.0
    assert res[0]["composto"] >= res[-1]["composto"]
    assert fin["n_ativos"] == 2
    assert fin["cobertura_fundamento"] == fin["cobertura_tecnico"] == 100
    assert "não é RS" in fin["metodologia"]["tecnico"]
    assert fin["metodologia"]["calibrado"] is False


def test_cache_nao_le_health_total():
    _, fund, price = _fake_caches()
    macro = {"selic": 14.75, "vix": 16.5, "treasury_10y": 4.5}
    with (
        patch("database.db.get_health_scores", side_effect=AssertionError("Health total não é fundamento")),
        patch("database.db.get_todos_fundamentos_cache", return_value=fund),
        patch("database.db.get_all_price_cache", return_value=price),
        patch("utils.inflation_sectoral.get_inflacao_atual", return_value={}),
        patch("utils.inflation_sectoral.pilar_macro_setorial",
              side_effect=lambda setor, *_: _macro().get(setor, {"pontos": 0})),
    ):
        fn = getattr(sc._calcular_scorecard_cache, "__wrapped__", sc._calcular_scorecard_cache)
        rows = fn("BR", macro)
    assert _by_sector(rows)["financeiro"]["fundamento"] == 100
    assert _by_sector(rows)["financeiro"]["macro_fontes"] == ["regime"]
    assert any("apenas regime" in a for a in _by_sector(rows)["financeiro"]["alertas"])


def test_mudanca_macro_ou_momentum_nao_altera_fundamento():
    _, fund, price = _fake_caches()
    antes = _by_sector(sc.calcular_scorecard_dados(fund, price, _macro()))
    depois = _by_sector(sc.calcular_scorecard_dados(
        fund, {"ITUB4.SA": {"var_12m": -70}, "MGLU3.SA": {"var_12m": 90}},
        {"financeiro": {"pontos": -8}, "consumo_ciclico": {"pontos": 8}}))
    assert antes["financeiro"]["fundamento"] == depois["financeiro"]["fundamento"]
    assert antes["financeiro"]["composto"] != depois["financeiro"]["composto"]


def test_setor_sem_fundamentos_nao_desaparece_nem_recebe_neutro():
    _, fund, price = _fake_caches()
    fund["ITUB4.SA"] = {"setor": "Financial Services"}
    fund["BBAS3.SA"] = {"setor": "Financial Services"}
    fin = _by_sector(sc.calcular_scorecard_dados(fund, price, _macro()))["financeiro"]
    assert fin["n_ativos"] == 2
    assert fin["fundamento"] is None
    assert fin["qualidade"] is None and fin["valuation"] is None
    assert fin["cobertura_fundamento"] == 0
    assert fin["composto"] is None and fin["veredicto"] == "dados insuficientes"


def test_valuation_isolado_nao_vira_fundamento():
    _, fund, price = _fake_caches()
    fund["ITUB4.SA"] = {"setor": "Financial Services", "p/l": 3}
    fund["BBAS3.SA"] = {"setor": "Financial Services", "p/vp": 0.2}
    fin = _by_sector(sc.calcular_scorecard_dados(fund, price, _macro()))["financeiro"]
    assert fin["valuation"] == 100
    assert fin["qualidade"] is None and fin["fundamento"] is None


def test_cobertura_baixa_suspende_composto():
    _, fund, price = _fake_caches()
    fund["BBAS3.SA"] = {"setor": "Financial Services"}
    fund["BBDC4.SA"] = {"setor": "Financial Services"}
    fin = _by_sector(sc.calcular_scorecard_dados(fund, price, _macro()))["financeiro"]
    assert fin["fundamento"] == 100
    assert fin["n_fundamento"] == 1
    assert fin["cobertura_fundamento"] == 33.3
    assert fin["cobertura_por_campo"]["roe%"] == 33.3
    assert fin["composto"] is None


@pytest.mark.parametrize("valor", [None, float("nan"), float("inf"), "-inf", "ruim", True])
def test_dados_invalidos_nao_criam_sinal(valor):
    _, fund, price = _fake_caches()
    for ticker in ("ITUB4.SA", "BBAS3.SA"):
        fund[ticker].update({"roe%": valor, "margem%": valor, "p/l": valor, "p/vp": valor})
        price[ticker]["var_12m"] = valor
    fin = _by_sector(sc.calcular_scorecard_dados(fund, price, _macro()))["financeiro"]
    assert fin["fundamento"] is None and fin["tecnico"] is None
    assert fin["momentum_12m"] is None and fin["composto"] is None


def test_zero_observado_e_diferente_de_ausencia():
    item = sc._fundamento_ativo({"roe%": 0, "margem%": 0, "p/l": 0, "p/vp": 0}, "financeiro")
    assert item["fundamento"] == 0
    assert all(v == 0 for v in item["campos"].values())


@pytest.mark.parametrize("precos", [{"ITUB4.SA": {"var_12m": 20}}, {
    "ITUB4.SA": {"var_12m": 20}, "MGLU3.SA": {"var_12m": 20},
}])
def test_um_setor_ou_empate_sem_discriminacao_tecnica(precos):
    _, fund, _ = _fake_caches()
    rows = sc.calcular_scorecard_dados(fund, precos, _macro())
    assert all(r["tecnico"] is None and r["composto"] is None for r in rows)


def test_macro_ausente_nao_recebe_50():
    _, fund, price = _fake_caches()
    rows = sc.calcular_scorecard_dados(fund, price)
    assert all(r["macro"] is None and r["macro_pontos"] is None for r in rows)
    assert all(r["composto"] is None for r in rows)


def test_contexto_macro_ausente_nao_chama_regime_com_fallback():
    _, fund, price = _fake_caches()
    with (
        patch("database.db.get_todos_fundamentos_cache", return_value=fund),
        patch("database.db.get_all_price_cache", return_value=price),
        patch("utils.inflation_sectoral.pilar_macro_setorial", side_effect=AssertionError("Não imputar macro")),
    ):
        fn = getattr(sc._calcular_scorecard_cache, "__wrapped__", sc._calcular_scorecard_cache)
        rows = fn("BR", {})
    assert all(r["macro"] is None for r in rows)


def test_contexto_macro_participa_da_chave_do_cache():
    with patch.object(sc, "_calcular_scorecard_cache", return_value=[]) as cache:
        sc.calcular_scorecard_setorial("BR", {"selic": 10, "vix": 15})
        sc.calcular_scorecard_setorial("BR", {"selic": 14, "vix": 25})
    assert cache.call_args_list[0].args != cache.call_args_list[1].args


def test_filtra_mercado_e_normaliza_setores():
    _, fund, price = _fake_caches()
    fund["JPM"] = {"setor": "Financeiro", "roe%": 25, "p/l": 10}
    price["JPM"] = {"var_12m": 25}
    us = sc.calcular_scorecard_dados(fund, price, _macro(), "US")
    assert len(us) == 1 and us[0]["n_ativos"] == 1
    assert us[0]["tickers"] == ["JPM"]
    assert sum(r["n_ativos"] for r in sc.calcular_scorecard_dados(fund, price, _macro(), "BR")) == 4


def test_minmax_preserva_diferencas_antes_do_arredondamento():
    _, fund, _ = _fake_caches()
    price = {"ITUB4.SA": {"var_12m": 20.01}, "MGLU3.SA": {"var_12m": 20.02}}
    rows = _by_sector(sc.calcular_scorecard_dados(fund, price, _macro()))
    assert rows["financeiro"]["tecnico"] == 0
    assert rows["consumo_ciclico"]["tecnico"] == 100


def test_fallback_numerico_marcado_nao_observado_nao_pontua_macro():
    _, fund, price = _fake_caches()
    contexto = {"selic": 14.75, "vix": 15, "qualidade": {"selic": {"observado": False}}}
    with (
        patch("database.db.get_todos_fundamentos_cache", return_value=fund),
        patch("database.db.get_all_price_cache", return_value=price),
        patch("utils.inflation_sectoral.pilar_macro_setorial", side_effect=AssertionError("Fallback não é observado")),
    ):
        fn = getattr(sc._calcular_scorecard_cache, "__wrapped__", sc._calcular_scorecard_cache)
        rows = fn("BR", contexto)
    assert all(r["macro"] is None and r["composto"] is None for r in rows)
