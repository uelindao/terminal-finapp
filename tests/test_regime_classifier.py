"""
tests/test_regime_classifier.py
Testes do classificador de regime macro — 1 teste por fase com dados sintéticos.
"""
from utils.regime_classifier import classificar_regime, _momentum_12_1


def _serie_crescente(n: int = 252, base: float = 100.0) -> list[float]:
    """Serie subindo: base + i*0.2 — momentum positivo."""
    return [base + i * 0.2 for i in range(n)]


def _serie_caindo(n: int = 252, topo: float = 150.0, piso: float = 100.0) -> list[float]:
    """Serie onde p[-252] > p[-21] — momentum negativo."""
    # Primeiros 231 = topo, últimos 21 = piso
    return [topo] * (n - 21) + [piso] * 21


def test_expansao():
    """Score 0: yield positiva, VIX baixo, CPI desacelerando, momentum positivo."""
    r = classificar_regime(
        t10y=4.5,
        t2y=4.0,
        vix=15.0,
        cpi_yoy_serie=[3.5, 3.4, 3.3],
        spy_serie=_serie_crescente(),
        ibov_serie=_serie_crescente(),
    )
    assert r.fase == "expansao"
    assert r.score_sinais == 0


def test_pico():
    """Score 2: yield invertida + VIX alto (sinais de pico)."""
    r = classificar_regime(
        t10y=3.8,
        t2y=4.2,
        vix=22.0,
        cpi_yoy_serie=[3.0, 3.0, 3.0],  # estável → cpi_acelerando = False
        spy_serie=_serie_crescente(),
        ibov_serie=_serie_crescente(),
    )
    assert r.fase == "pico"
    assert r.score_sinais == 2


def test_contracao():
    """Score 3: yield invertida + VIX alto + CPI acelerando."""
    r = classificar_regime(
        t10y=3.8,
        t2y=4.2,
        vix=25.0,
        cpi_yoy_serie=[3.0, 3.5, 4.0],  # acelerando
        spy_serie=_serie_crescente(),
        ibov_serie=_serie_crescente(),
    )
    assert r.fase == "contracao"
    assert r.score_sinais == 3


def test_vale():
    """Score 4: todos os sinais negativos — yield invertida, VIX alto,
    CPI acelerando, momentum negativo (SPY e IBOV caindo)."""
    r = classificar_regime(
        t10y=3.8,
        t2y=4.2,
        vix=28.0,
        cpi_yoy_serie=[3.0, 3.5, 4.0],
        spy_serie=_serie_caindo(),
        ibov_serie=_serie_caindo(),
    )
    assert r.fase == "vale"
    assert r.score_sinais == 4


def test_momentum_12_1_positivo():
    """_momentum_12_1 retorna positivo quando série sobe."""
    serie = _serie_crescente(260)
    mom = _momentum_12_1(serie)
    assert mom is not None
    assert mom > 0


def test_momentum_12_1_negativo():
    """_momentum_12_1 retorna negativo quando série cai."""
    serie = _serie_caindo(260)
    mom = _momentum_12_1(serie)
    assert mom is not None
    assert mom < 0


def test_momentum_12_1_dados_insuficientes():
    """_momentum_12_1 retorna None com menos de 252 pontos."""
    assert _momentum_12_1([100.0] * 200) is None
    assert _momentum_12_1([]) is None
    assert _momentum_12_1(None) is None


def test_entradas_none():
    """Sinais com input None contam como False, probabilidade descontada."""
    r = classificar_regime(
        t10y=None,
        t2y=None,
        vix=None,
        cpi_yoy_serie=None,
        spy_serie=None,
        ibov_serie=None,
    )
    assert r.fase == "expansao"
    assert r.score_sinais == 0
    assert r.probabilidade < 0.55  # desconto por dados faltando
