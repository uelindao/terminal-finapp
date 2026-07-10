"""Testes de utils/alinhamento_regime — alinhamento carteira × regime (F3-2).

Função pura com tilt_fn injetável: sem rede, sem Streamlit.
"""
from utils.alinhamento_regime import alinhamento_regime, _mercado_do_ticker


def _fake_tilt(mapa):
    """Cria um tilt_fn de teste: setor -> (impacto, pontos)."""
    def _fn(setor, macro_context, market):
        imp, pts = mapa.get(setor, ("neutro", 0))
        return {"impacto": imp, "pontos": pts}
    return _fn


_TILT = _fake_tilt({
    "Energia":    ("favoravel", 3),
    "Tecnologia": ("desfavoravel", -2),
    "Bancos":     ("neutro", 0),
})


def test_mercado_do_ticker():
    assert _mercado_do_ticker("PETR4.SA") == "BR"
    assert _mercado_do_ticker("HGLG11.SA") == "BR"
    assert _mercado_do_ticker("AAPL") == "US"


def test_percentuais_ponderados_por_peso():
    posicoes = [
        {"ticker": "PETR4.SA", "peso": 60.0},   # Energia favorável
        {"ticker": "AAPL",     "peso": 40.0},   # Tecnologia desfavorável
    ]
    cache = {"PETR4.SA": {"setor": "Energia"}, "AAPL": {"setor": "Tecnologia"}}
    r = alinhamento_regime(posicoes, cache, {}, tilt_fn=_TILT)
    assert round(r["favoravel_pct"]) == 60
    assert round(r["desfavoravel_pct"]) == 40
    assert round(r["neutro_pct"]) == 0


def test_saldo_pontos_media_ponderada():
    posicoes = [
        {"ticker": "PETR4.SA", "peso": 50.0},   # +3
        {"ticker": "AAPL",     "peso": 50.0},   # -2
    ]
    cache = {"PETR4.SA": {"setor": "Energia"}, "AAPL": {"setor": "Tecnologia"}}
    r = alinhamento_regime(posicoes, cache, {}, tilt_fn=_TILT)
    assert r["saldo_pontos"] == 0.5   # (0.5*3 + 0.5*-2)


def test_posicao_sem_setor_no_cache():
    posicoes = [{"ticker": "XPTO3.SA", "peso": 100.0}]
    r = alinhamento_regime(posicoes, {}, {}, tilt_fn=_TILT)
    assert round(r["sem_setor_pct"]) == 100
    assert r["itens"][0]["impacto"] == "sem_setor"


def test_normaliza_qualquer_escala_de_peso():
    """Pesos em custo bruto (não somam 100) devem normalizar corretamente."""
    posicoes = [
        {"ticker": "PETR4.SA", "peso": 3000.0},  # Energia
        {"ticker": "BBAS3.SA", "peso": 1000.0},  # Bancos neutro
    ]
    cache = {"PETR4.SA": {"setor": "Energia"}, "BBAS3.SA": {"setor": "Bancos"}}
    r = alinhamento_regime(posicoes, cache, {}, tilt_fn=_TILT)
    assert round(r["favoravel_pct"]) == 75
    assert round(r["neutro_pct"]) == 25
    assert r["total"] == 4000.0


def test_ignora_peso_zero_ou_negativo():
    posicoes = [
        {"ticker": "PETR4.SA", "peso": 100.0},
        {"ticker": "VALE3.SA", "peso": 0.0},
        {"ticker": "ITUB4.SA", "peso": -5.0},
    ]
    cache = {"PETR4.SA": {"setor": "Energia"}}
    r = alinhamento_regime(posicoes, cache, {}, tilt_fn=_TILT)
    assert len(r["itens"]) == 1
    assert r["total"] == 100.0


def test_itens_ordenados_por_peso_desc():
    posicoes = [
        {"ticker": "A.SA", "peso": 10.0},
        {"ticker": "B.SA", "peso": 50.0},
        {"ticker": "C.SA", "peso": 30.0},
    ]
    cache = {t: {"setor": "Bancos"} for t in ("A.SA", "B.SA", "C.SA")}
    r = alinhamento_regime(posicoes, cache, {}, tilt_fn=_TILT)
    assert [i["ticker"] for i in r["itens"]] == ["B.SA", "C.SA", "A.SA"]
    assert all("peso_pct" in i for i in r["itens"])


def test_carteira_vazia():
    r = alinhamento_regime([], {}, {}, tilt_fn=_TILT)
    assert r["total"] == 0.0 and r["itens"] == []


def test_peso_invalido_e_ignorado():
    posicoes = [
        {"ticker": "PETR4.SA", "peso": "abc"},   # inválido
        {"ticker": "BBAS3.SA", "peso": 100.0},
    ]
    cache = {"BBAS3.SA": {"setor": "Bancos"}}
    r = alinhamento_regime(posicoes, cache, {}, tilt_fn=_TILT)
    assert r["total"] == 100.0 and len(r["itens"]) == 1
