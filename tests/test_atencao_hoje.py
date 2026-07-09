"""Testes de utils/atencao_hoje — motor do bloco 'atenção hoje' (F1-1).

Função pura por injeção de dependência: sem I/O, só fixtures sintéticas.
"""
from datetime import date

from utils.atencao_hoje import coletar_atencao_hoje


def _hist(*scores):
    """Histórico ASC de health score no formato do db (get_historico_score)."""
    return [{"score": s, "calculado_em": f"2026-07-0{i+1}T00:00:00"}
            for i, s in enumerate(scores)]


# ── SCORE ────────────────────────────────────────────────────────────────────

def test_score_queda_relevante_gera_item_bear():
    itens = coletar_atencao_hoje(
        watchlist=["PETR4.SA"],
        historico_por_ticker={"PETR4.SA": _hist(70, 60)},
        price_cache={},
        hoje=date(2026, 7, 9),
    )
    assert len(itens) == 1
    it = itens[0]
    assert it["tipo"] == "score" and it["tom"] == "bear"
    assert "70→60" in it["titulo"]


def test_score_variacao_pequena_ignorada():
    itens = coletar_atencao_hoje(
        watchlist=["VALE3.SA"],
        historico_por_ticker={"VALE3.SA": _hist(60, 63)},  # Δ=3 < 5
        price_cache={},
    )
    assert itens == []


def test_score_cruzar_faixa_50_tem_severidade_maior():
    """Cair de 52→48 (cruza 50) deve pontuar mais que 82→78 (não cruza)."""
    cruza = coletar_atencao_hoje(
        watchlist=["A.SA"], historico_por_ticker={"A.SA": _hist(52, 47)},
        price_cache={},
    )[0]
    nao = coletar_atencao_hoje(
        watchlist=["B.SA"], historico_por_ticker={"B.SA": _hist(82, 77)},
        price_cache={},
    )[0]
    assert cruza["severidade"] > nao["severidade"]


def test_score_historico_curto_nao_quebra():
    assert coletar_atencao_hoje(
        watchlist=["X.SA"], historico_por_ticker={"X.SA": _hist(60)},
        price_cache={},
    ) == []


# ── TÉCNICO ──────────────────────────────────────────────────────────────────

def test_rsi_sobrevendido():
    it = coletar_atencao_hoje(
        watchlist=["MGLU3.SA"], historico_por_ticker={},
        price_cache={"MGLU3.SA": {"preco": 10.0, "rsi_14": 22}},
    )[0]
    assert it["tipo"] == "tecnico" and it["tom"] == "bull"
    assert "sobrevendido" in it["titulo"]


def test_perto_da_maxima_52s():
    it = coletar_atencao_hoje(
        watchlist=["WEGE3.SA"], historico_por_ticker={},
        price_cache={"WEGE3.SA": {"preco": 99.0, "max_52s": 100.0, "rsi_14": 55}},
    )[0]
    assert "máxima" in it["titulo"]


def test_tranco_no_dia():
    it = coletar_atencao_hoje(
        watchlist=["BBAS3.SA"], historico_por_ticker={},
        price_cache={"BBAS3.SA": {"preco": 50.0, "var_1d": -7.3, "rsi_14": 45}},
    )[0]
    assert it["tom"] == "bear" and "-7.3%" in it["titulo"]


def test_apenas_um_tecnico_por_ticker():
    """Vários sinais técnicos → só o mais severo entra."""
    itens = coletar_atencao_hoje(
        watchlist=["Z.SA"], historico_por_ticker={},
        price_cache={"Z.SA": {"preco": 5.0, "rsi_14": 15, "min_52s": 5.0,
                              "var_1d": -6.0}},
    )
    assert len([i for i in itens if i["tipo"] == "tecnico"]) == 1


def test_price_cache_ruido_nao_gera_item():
    assert coletar_atencao_hoje(
        watchlist=["OK.SA"], historico_por_ticker={},
        price_cache={"OK.SA": {"preco": 50.0, "rsi_14": 55, "var_1d": 0.4,
                              "max_52s": 80.0, "min_52s": 20.0}},
    ) == []


# ── EVENTOS ──────────────────────────────────────────────────────────────────

def test_evento_hoje_alto_impacto():
    itens = coletar_atencao_hoje(
        watchlist=[], historico_por_ticker={}, price_cache={},
        eventos=[{"data": date(2026, 7, 9), "evento": "COPOM — juros",
                  "categoria": "brasil", "impacto": "alto"}],
        hoje=date(2026, 7, 9),
    )
    assert len(itens) == 1 and itens[0]["tipo"] == "evento"
    assert "hoje" in itens[0]["detalhe"]


def test_evento_distante_ignorado():
    assert coletar_atencao_hoje(
        watchlist=[], historico_por_ticker={}, price_cache={},
        eventos=[{"data": date(2026, 7, 20), "evento": "CPI", "impacto": "alto"}],
        hoje=date(2026, 7, 9),
    ) == []


# ── RANKING / LIMITES ────────────────────────────────────────────────────────

def test_ordena_por_severidade_desc():
    itens = coletar_atencao_hoje(
        watchlist=["A.SA", "B.SA"],
        historico_por_ticker={"A.SA": _hist(80, 78),          # Δ=-2? não; usar 6
                              "B.SA": _hist(70, 40)},          # Δ=-30 forte + cruza
        price_cache={},
    )
    # B (queda enorme cruzando faixas) deve vir antes de qualquer coisa de A
    assert itens[0]["ticker"] == "B.SA"


def test_respeita_limite():
    wl = [f"T{i}.SA" for i in range(20)]
    hist = {t: _hist(70, 50) for t in wl}
    itens = coletar_atencao_hoje(
        watchlist=wl, historico_por_ticker=hist, price_cache={}, limite=5,
    )
    assert len(itens) == 5


def test_max_dois_itens_por_ticker():
    itens = coletar_atencao_hoje(
        watchlist=["DUP.SA"],
        historico_por_ticker={"DUP.SA": _hist(70, 50)},   # 1 item score
        price_cache={"DUP.SA": {"preco": 5.0, "rsi_14": 12}},  # 1 item tecnico
    )
    assert len([i for i in itens if i["ticker"] == "DUP.SA"]) <= 2


def test_mercado_calmo_retorna_vazio():
    assert coletar_atencao_hoje(
        watchlist=["CALM.SA"],
        historico_por_ticker={"CALM.SA": _hist(60, 61)},
        price_cache={"CALM.SA": {"preco": 50.0, "rsi_14": 50, "var_1d": 0.2}},
        eventos=[], hoje=date(2026, 7, 9),
    ) == []
