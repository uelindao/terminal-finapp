"""Calibragem do motor de health score (nov/2026)."""
import pytest

from utils.health_engine import (_calc_icr_do_historico, _penalidade_vix, _pontuar_pvp_fii,
                                 status_do_score)


@pytest.mark.parametrize("vix, beta, esperado", [
    (19.0, 2.0, 0),     # abaixo do início da rampa
    (20.0, 2.0, 0),
    (25.0, 2.0, -4),    # meio da rampa: metade dos 8
    (25.0, 1.3, -2),    # metade dos 5 (2,5 arredonda para 2)
    (30.0, 1.6, -8),
    (45.0, 1.6, -8),    # teto
    (35.0, 1.1, 0),     # beta baixo nunca é penalizado
])
def test_penalidade_vix_em_rampa(vix, beta, esperado):
    assert _penalidade_vix({"vix": vix}, beta) == esperado


def test_penalidade_vix_usa_media_de_10_pregoes_quando_existe():
    # Pico de um dia (29,7) com média de 10 pregões em 21: quase sem penalidade
    assert _penalidade_vix({"vix": 29.7, "vix_media_10d": 21.0}, 1.6) == -1


@pytest.mark.parametrize("pvp, segmento, pontos", [
    (0.80, "papel", 30),        # papel a 0,80 já não é "desconto saudável"
    (0.90, "papel", 40),
    (0.80, "lajes", 40),        # lajes aceita desconto maior
    (1.10, "shopping", 28),     # shopping tolera ágio até 1,20
    (1.10, "papel", 15),
    (1.40, "papel", 5),
    (0.60, "logistica", 3),
    (None, "papel", 15),
])
def test_pvp_de_fii_usa_as_faixas_do_segmento(pvp, segmento, pontos):
    assert _pontuar_pvp_fii(pvp, segmento)[0] == pontos


def test_segmento_desconhecido_cai_na_faixa_padrao():
    assert _pontuar_pvp_fii(0.95, "algo_novo") == _pontuar_pvp_fii(0.95, "desconhecido")


def test_icr_de_empresa_com_resultado_financeiro_positivo_e_nota_maxima():
    hist = [{"ebit": 1000.0, "interest_expense": None, "res_fin": 150.0}]
    assert _calc_icr_do_historico(hist) == (5, None)


def test_icr_sem_dado_de_juros_nem_resultado_financeiro_continua_zero():
    assert _calc_icr_do_historico([{"ebit": 1000.0, "interest_expense": None}]) == (0, None)
    # EBIT negativo com resultado financeiro positivo não ganha nota
    assert _calc_icr_do_historico([{"ebit": -10.0, "interest_expense": None, "res_fin": 5.0}]) == (0, None)


def test_icr_com_despesa_de_juros_segue_a_tabela():
    score, icr = _calc_icr_do_historico([{"ebit": 400.0, "interest_expense": -100.0}])
    assert (score, icr) == (3, 4.0)


@pytest.mark.parametrize("mercado, score, rotulo", [
    ("br", 60, "ACUMULAÇÃO"),
    ("us", 60, "MANUTENÇÃO"),
    ("br", 20, "AGUARDAR"),
    ("us", 20, "VENDA DEFINITIVA"),
    ("br", 10, "VENDA DEFINITIVA"),
    ("fii", 20, "VENDA DEFINITIVA"),
])
def test_rotulo_depende_do_mercado(mercado, score, rotulo):
    assert rotulo in status_do_score(score, mercado, rsi=50, abaixo_mm200=False)


def test_rotulo_mantem_qualificadores_de_rsi_e_mm200():
    assert "ACUMULAÇÃO FORTE" in status_do_score(80, "us", rsi=30)
    assert "ATENÇÃO" in status_do_score(80, "us", rsi=75)
    assert "REDUZIR EXPOSIÇÃO" in status_do_score(40, "us", abaixo_mm200=True)
    assert "ACUMULAÇÃO" in status_do_score(80, "us", rsi=None)
