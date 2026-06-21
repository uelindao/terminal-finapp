"""
Testes do scorecard de rotação setorial (utils/sector_scorecard).
Mocka os caches (health/fundamentals/price) — sem rede.
"""
from unittest.mock import patch

import utils.sector_scorecard as sc


def test_helpers_puros():
    # macro ±8 → 0-100 com 50 neutro
    assert sc._macro_para_0_100(0) == 50
    assert sc._macro_para_0_100(8) == 100
    assert sc._macro_para_0_100(-8) == 0
    # composto pondera 0.45/0.25/0.30
    assert sc._composto(100, 100, 100) == 100.0
    assert sc._composto(0, 0, 0) == 0.0
    v, _cor = sc._veredicto(70, 2)
    assert v == "overweight"
    v2, _ = sc._veredicto(30, -2)
    assert v2 == "underweight"


def _fake_caches():
    health = [
        {"ticker": "ITUB4.SA", "score": 75},
        {"ticker": "BBAS3.SA", "score": 70},
        {"ticker": "MGLU3.SA", "score": 30},
        {"ticker": "LREN3.SA", "score": 35},
    ]
    fund = {
        "ITUB4.SA": {"setor": "Financial Services"},
        "BBAS3.SA": {"setor": "Financial Services"},
        "MGLU3.SA": {"setor": "Consumer Cyclical"},
        "LREN3.SA": {"setor": "Consumer Cyclical"},
    }
    price = {
        "ITUB4.SA": {"var_12m": 25.0},
        "BBAS3.SA": {"var_12m": 20.0},
        "MGLU3.SA": {"var_12m": -40.0},
        "LREN3.SA": {"var_12m": -10.0},
    }
    return health, fund, price


def test_scorecard_ordena_e_cruza():
    health, fund, price = _fake_caches()
    macro = {"selic": 14.75, "vix": 16.5, "ipca_12m": 5.0, "treasury_10y": 4.5}

    with (
        patch("database.db.get_health_scores", return_value=health),
        patch("database.db.get_todos_fundamentos_cache", return_value=fund),
        patch("database.db.get_all_price_cache", return_value=price),
        patch.object(sc.st, "session_state", create=True) as _ss,
    ):
        # session_state.get("macro_context", {}) → macro
        _ss.get = lambda *a, **k: macro if a and a[0] == "macro_context" else (k.get("default") if k else None)
        # cache_data desabilitado em bare mode; chama direto a função embrulhada
        res = sc.calcular_scorecard_setorial.__wrapped__("BR") if hasattr(
            sc.calcular_scorecard_setorial, "__wrapped__"
        ) else sc.calcular_scorecard_setorial("BR")

    setores = {r["setor"]: r for r in res}
    assert "financeiro" in setores and "consumo_ciclico" in setores
    fin, con = setores["financeiro"], setores["consumo_ciclico"]

    # Financeiro: fundamento alto + macro favorável (juro alto) > consumo cíclico
    assert fin["composto"] > con["composto"]
    # Financeiro favorecido no regime de juro muito alto
    assert fin["macro_pontos"] > 0
    # Consumo cíclico pressionado por juro alto
    assert con["macro_pontos"] < 0
    # Técnico (força relativa) reflete momentum: financeiro líder = 100, consumo = 0
    assert fin["tecnico"] == 100.0
    assert con["tecnico"] == 0.0
    # ranking ordenado desc
    assert res[0]["composto"] >= res[-1]["composto"]
