"""
Testes do motor de sizing + exposição macro do book (utils/portfolio_sizing).
Puro — sem rede.
"""
import numpy as np
import pandas as pd

from utils.portfolio_sizing import (
    sugerir_sizing, exposicao_macro_book, vol_anual_por_ticker,
    _edge_mult, _macro_mult, _market_do_ticker,
)


def test_helpers():
    assert _market_do_ticker("PETR4.SA") == "BR"
    assert _market_do_ticker("AAPL") == "US"
    assert _edge_mult(50) == 1.0
    assert _edge_mult(100) == 1.8        # clamp
    assert _edge_mult(None) == 1.0
    assert _macro_mult(0) == 1.0
    assert _macro_mult(8) <= 1.5
    assert _macro_mult(-8) >= 0.5


def _precos_sinteticos():
    rng = np.random.default_rng(42)
    n = 260
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    # ITUB4 baixa vol; MGLU3 alta vol
    itub = 30 * np.exp(np.cumsum(rng.normal(0, 0.010, n)))
    mglu = 5 * np.exp(np.cumsum(rng.normal(0, 0.040, n)))
    return pd.DataFrame({"ITUB4.SA": itub, "MGLU3.SA": mglu}, index=idx)


def test_sizing_inverse_vol_e_edge():
    precos = _precos_sinteticos()
    vols = vol_anual_por_ticker(precos)
    assert vols["MGLU3.SA"] > vols["ITUB4.SA"]   # alta vol detectada

    pesos = {"ITUB4.SA": 50.0, "MGLU3.SA": 50.0}
    health = {"ITUB4.SA": 75, "MGLU3.SA": 30}
    setor = {"ITUB4.SA": "Financial Services", "MGLU3.SA": "Consumer Cyclical"}
    macro = {"selic": 14.75, "vix": 16.5, "ipca_12m": 5.0, "treasury_10y": 4.5}

    res = sugerir_sizing(pesos, precos, health, setor, macro)
    alvo = {r["ticker"]: r["peso_alvo"] for r in res}
    acao = {r["ticker"]: r["acao"] for r in res}

    # ITUB (baixa vol + edge alto + setor favorecido) > MGLU (alta vol + edge baixo + pressionado)
    assert alvo["ITUB4.SA"] > alvo["MGLU3.SA"]
    # alvos somam ~100
    assert abs(sum(alvo.values()) - 100) < 0.5
    # ação coerente: aumentar ITUB, reduzir MGLU (estavam 50/50)
    assert acao["ITUB4.SA"] == "aumentar"
    assert acao["MGLU3.SA"] == "reduzir"


def test_book_brigando_com_macro():
    # book 100% em setores pressionados por juro alto → tilt negativo
    pesos = {"MGLU3.SA": 50.0, "MRVE3.SA": 50.0}  # varejo + construção
    setor = {"MGLU3.SA": "Consumer Cyclical", "MRVE3.SA": "Real Estate"}
    macro = {"selic": 14.75, "vix": 16.5, "ipca_12m": 5.0, "treasury_10y": 4.5}

    exp = exposicao_macro_book(pesos, setor, macro)
    assert exp["tilt_medio"] < 0
    assert exp["pct_desfavoravel"] > 50
    assert exp["duration_exposta_pct"] > 50
    assert "BRIGANDO" in exp["leitura"]


def test_book_alinhado_macro():
    pesos = {"ITUB4.SA": 60.0, "BBAS3.SA": 40.0}  # bancos
    setor = {"ITUB4.SA": "Financial Services", "BBAS3.SA": "Financial Services"}
    macro = {"selic": 14.75, "vix": 16.5, "ipca_12m": 5.0, "treasury_10y": 4.5}

    exp = exposicao_macro_book(pesos, setor, macro)
    assert exp["tilt_medio"] > 0
    assert "ALINHADO" in exp["leitura"]
