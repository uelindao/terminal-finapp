"""Testes de utils/data_quality — cobertura de campos por mercado."""
from utils.data_quality import calcular_cobertura, _mercado, _campos_aplicaveis


def test_classificacao_mercado():
    assert _mercado("PETR4.SA") == "BR"
    assert _mercado("HGLG11.SA") == "FII"
    assert _mercado("AAPL") == "US"
    # 11.SA que NÃO é FII (fonte única health_engine)
    assert _mercado("TAEE11.SA") == "BR"


def test_fii_ignora_campos_nao_aplicaveis():
    aplic = _campos_aplicaveis("FII")
    assert "p/l" not in aplic and "margem%" not in aplic and "ev/ebitda" not in aplic
    assert "p/vp" in aplic and "dy%" in aplic


def test_cobertura_basica():
    cache = {
        "PETR4.SA": {"p/l": 4.5, "p/vp": 1.1, "roe%": 24.0, "dy%": 8.0,
                     "margem%": 21.0, "ev/ebitda": 3.4, "data_source": "brapi"},
        "AZUL4.SA": {"p/l": None, "p/vp": 1.2, "roe%": None, "dy%": None,
                     "margem%": None, "ev/ebitda": None, "data_source": "brapi"},
    }
    r = calcular_cobertura(cache)
    assert r["total"] == 2
    br = r["por_mercado"]["BR"]
    assert br["n"] == 2
    assert br["campos"]["p/vp"] == 100.0     # ambos têm
    assert br["campos"]["roe%"] == 50.0      # só PETR4
    # AZUL4 é o pior (5 campos faltando)
    assert r["piores"][0]["ticker"] == "AZUL4.SA"
    assert r["piores"][0]["n_faltando"] == 5


def test_fii_nao_conta_pl_como_faltando():
    cache = {"HGLG11.SA": {"p/vp": 0.95, "dy%": 9.0, "roe%": 8.0,
                           "p/l": None, "margem%": None, "ev/ebitda": None}}
    r = calcular_cobertura(cache)
    # FII com p/vp, dy, roe preenchidos e só os n/a faltando → nada em 'piores'
    assert r["piores"] == []
    assert r["por_mercado"]["FII"]["cobertura_media"] == 100.0


def test_cache_vazio():
    r = calcular_cobertura({})
    assert r["total"] == 0
    assert r["piores"] == []
    assert r["por_mercado"] == {}
