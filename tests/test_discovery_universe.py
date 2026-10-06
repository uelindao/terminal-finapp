import pytest
from utils.discovery_universe import (
    UNIVERSOS_IA, tickers_oportunidades_ia,
    chaves_cache_oportunidades_ia, filtrar_resultados_oportunidades_ia,
)
from utils.ai_prompts import build_discovery_prompt


def test_acoes_excluem_fii_mal_catalogado_sem_excluir_units():
    acoes = set(tickers_oportunidades_ia("BR_ACOES"))
    fiis = set(tickers_oportunidades_ia("FII"))
    assert acoes.isdisjoint(fiis)
    assert "IRDM11.SA" in fiis and "IRDM11.SA" not in acoes
    assert {"TAEE11.SA", "BPAC11.SA", "KLBN11.SA", "IGTI11.SA"} <= acoes
    assert {"RECR11.SA", "VGIP11.SA"} <= fiis


def test_todas_acoes_reunem_mercados_sem_incluir_fiis_ou_duplicatas():
    todos = tickers_oportunidades_ia("ACOES")
    assert set(todos) == set(tickers_oportunidades_ia("BR_ACOES")) | set(tickers_oportunidades_ia("US_ACOES"))
    assert set(todos).isdisjoint(tickers_oportunidades_ia("FII"))
    assert len(todos) == len(set(todos))


def test_resultado_contaminado_nao_chega_ao_ranking_ou_payload():
    rows = [{"ticker": t} for t in ["VALE3.SA", "TAEE11.SA", "RECR11.SA", "VGIP11.SA", "AAPL"]]
    assert [r["ticker"] for r in filtrar_resultados_oportunidades_ia(rows, "BR_ACOES")] == ["VALE3.SA", "TAEE11.SA"]
    assert [r["ticker"] for r in filtrar_resultados_oportunidades_ia(rows, "FII")] == ["RECR11.SA", "VGIP11.SA"]


def test_cache_por_classe_e_foco_nao_reutiliza_analise_mista_legada():
    chaves = [chaves_cache_oportunidades_ia(u, m) for u in UNIVERSOS_IA
              for m in ("entrada", "dividendo", "realizacao")]
    assert len({s for s, _ in chaves}) == 12
    assert len({b for _, b in chaves}) == 12
    assert not {b for _, b in chaves} & {"BR_entrada", "US_entrada", "AMBOS_entrada"}


@pytest.mark.parametrize("universo", ["BR_ACOES", "FII", "US_ACOES", "ACOES"])
def test_prompt_identifica_universo_e_classe_exclusiva(universo):
    p = build_discovery_prompt([], "entrada", universo, {})
    assert f"universo: {UNIVERSOS_IA[universo]}" in p
    assert f"classe desta análise: {'FIIs' if universo == 'FII' else 'ações'}" in p
    assert "exclusivamente os candidatos fornecidos" in p


def test_universo_antigo_misto_nao_pode_reaparecer_como_fallback():
    with pytest.raises(ValueError):
        tickers_oportunidades_ia("BR")
