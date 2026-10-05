"""Regressões metodológicas: unidades, ausência e inflexões; sem rede."""
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from utils.regime_classifier import (
    classificar_regime, recuperacao_persistente, ler_curva_10y_2y,
    valor_observado, classificar_regime_do_macro_context,
)
from utils.ciclo_economico import (
    calcular_ciclo_br_dados, calcular_ciclo_us_dados, get_alocacao_sugerida,
)
from utils.macro_state import selic_real_fisher, tilt_setor, _consolidar_consenso


def rising(n=260):
    return pd.Series(np.linspace(100, 150, n))


def falling(n=260):
    return pd.Series(np.linspace(150, 100, n))


def test_three_valid_negative_signals_are_not_a_trough():
    r = classificar_regime(3, 4, 25, None, falling(), falling())
    assert r.fase == 'contracao'
    assert r.cobertura == .75
    assert r.sinais['cpi_acelerando'] is None
    assert r.concordancia == 1
    assert r.intensidade_stress == 1


def test_recovery_requires_falling_activity_then_two_monthly_rises():
    r = classificar_regime(3, 4, 25, [3, 3.5, 4], falling(), falling(),
                          atividade_serie=[100, 99, 98, 98.2, 98.4])
    assert r.fase == 'vale'
    assert r.recuperacao_confirmada
    r2 = classificar_regime(3, 4, 25, [3, 3.5, 4], falling(), falling(),
                           atividade_serie=[100, 99, 98, 97, 98])
    assert r2.fase == 'contracao'


@pytest.mark.parametrize('serie', ([100, 99, np.nan, 100, 101], [100, 99], None))
def test_missing_activity_cannot_confirm_recovery(serie):
    assert recuperacao_persistente(serie) is None


def test_non_finite_macro_does_not_count_as_calm():
    r = classificar_regime(np.nan, 4, np.inf, [3, 3.1, np.nan], rising(), rising())
    assert r.fase == 'indefinido'
    assert r.sinais_validos == 1
    assert r.sinais['vix_alto'] is None
    assert r.sinais['yield_invertida'] is None


def test_aligned_slope_takes_precedence_over_different_date_yields():
    r = classificar_regime(5, 3, 15, [4, 3, 2], rising(), rising(), slope_10y_2y=-.2)
    assert r.sinais['yield_invertida'] is True


def test_curve_uses_a_pair_on_the_same_date(monkeypatch):
    from utils import macro_supabase
    df = pd.DataFrame({'data': ['2026-09-01', '2026-09-02'], 't10y': [4.1, 4.2], 't2y': [4.3, np.nan]})
    monkeypatch.setattr(macro_supabase, 'buscar_slope_curva', lambda: df)
    curva = ler_curva_10y_2y()
    assert curva['slope'] == pytest.approx(-.2)
    assert curva['data'] == '2026-09-01'


def test_wrapper_never_requests_irx_as_treasury_two_year(monkeypatch):
    from utils import macro_supabase
    import yfinance
    chamados = []
    def ticker(tk):
        chamados.append(tk)
        return SimpleNamespace(history=lambda **kwargs: pd.DataFrame({'Close': rising()}))
    monkeypatch.setattr(yfinance, 'Ticker', ticker)
    monkeypatch.setattr(macro_supabase, 'buscar_slope_curva', lambda: None)
    monkeypatch.setattr(macro_supabase, 'carregar_snapshot', lambda *args, **kwargs: None)
    r = classificar_regime_do_macro_context({'vix': 15})
    assert chamados == ['SPY', '^BVSP']
    assert r.sinais['yield_invertida'] is None
    assert r.fase == 'indefinido'


def test_fisher_preserves_zero_and_invalid_is_unknown():
    assert selic_real_fisher(0, 0) == 0
    assert selic_real_fisher(15, 5) == pytest.approx((1.15 / 1.05 - 1) * 100)
    assert selic_real_fisher(None, 5) is None
    assert selic_real_fisher(10, np.nan) is None
    assert selic_real_fisher(10, -100) is None


def test_ex_post_and_expected_inflation_are_distinct():
    r = calcular_ciclo_br_dados({'selic': 15, 'ipca_12m': 5}, expectativa_ipca=4)
    assert r['indicadores']['selic_real_ex_post'] == round((1.15 / 1.05 - 1) * 100, 2)
    assert r['indicadores']['selic_real_ex_ante_proxy'] == round((1.15 / 1.04 - 1) * 100, 2)
    assert r['fase_provavel'] == 'indefinido'


def test_price_spread_is_not_a_brazilian_yield_curve_or_cycle_vote():
    r = calcular_ciclo_br_dados({}, {'IMAB11.SA': rising(), 'B5P211.SA': falling()})
    assert 'retorno_relativo_etfs_br' in r['indicadores']
    assert 'spread_curva_br' not in r['indicadores']
    assert r['n_indicadores'] == 0
    assert r['fase_provavel'] == 'indefinido'
    assert not any('invertida' in a for a in r['alertas'])


def test_equity_crash_and_monetary_stimulus_do_not_identify_valley():
    r = calcular_ciclo_br_dados({'selic': 0, 'ipca_12m': 5},
                               {'^BVSP': falling(), 'BRL=X': rising(), 'CL=F': falling()})
    assert r['score_vale'] == 0
    assert r['fase_provavel'] != 'vale'
    assert not r['recuperacao_confirmada']


def test_brazilian_activity_recovery_is_persistent_and_not_one_bounce():
    contexto = {'selic': 4, 'ipca_12m': 4}
    precos = {'^BVSP': falling(), 'BRL=X': pd.Series([5.] * 260)}
    serie = pd.Series([110.] * 8 + [100, 99, 98, 98.2, 98.4])
    r = calcular_ciclo_br_dados(contexto, precos, serie)
    assert r['recuperacao_confirmada']
    assert r['score_vale'] > 0
    serie.iloc[-2] = 97
    r2 = calcular_ciclo_br_dados(contexto, precos, serie)
    assert not r2['recuperacao_confirmada']
    assert r2['score_vale'] == 0


def test_fed_level_is_not_compared_with_invented_real_neutral_rate():
    r = calcular_ciclo_us_dados({'fed_funds': 5.25})
    assert r['indicadores'] == {'fed_funds': 5.25}
    assert r['n_indicadores'] == 0
    assert r['fase_provavel'] == 'indefinido'


def test_unknown_input_has_no_allocation_fallback():
    assert get_alocacao_sugerida('indefinido', 'expansao') == {}
    assert get_alocacao_sugerida('vale', 'pico')


def test_fallback_values_are_not_observations_or_macro_votes():
    ctx = {'selic': 15, 'vix': 30, 'ipca_12m': 5,
           'qualidade': {k: {'observado': False} for k in ('selic', 'vix', 'ipca_12m')}}
    assert valor_observado(ctx, 'selic') is None
    tilt = tilt_setor('consumo ciclico', ctx)
    assert tilt['pontos'] == 0
    assert tilt['cobertura'] == 0
    assert tilt['qualidade'] == 'ausente'
    assert set(tilt['ausentes']) == {'selic', 'vix'}
    ciclo = calcular_ciclo_br_dados(ctx)
    assert ciclo['n_indicadores'] == 0
    assert ciclo['fase_provavel'] == 'indefinido'


def test_consensus_does_not_count_unknown_engines_or_claim_independence():
    assert _consolidar_consenso('expansao', 'indefinido', '')[0] == 'indefinido'
    key, nota = _consolidar_consenso('expansao', 'vale', 'indefinido')
    assert key == 'alinhado_risk_on'
    assert '2/3' in nota
    assert 'não são confirmações independentes' in nota


def test_macro_state_uses_the_same_context_and_unknown_fields(monkeypatch):
    from utils import macro_state, regime_classifier, ciclo_economico
    import database.db as db
    monkeypatch.setattr(macro_state, 'ler_curva_10y_2y', lambda: {'slope': None})
    monkeypatch.setattr(db, 'get_macro_cache', lambda *args: None)
    seen = []
    def classifier(ctx):
        seen.append(ctx)
        return classificar_regime(None, None, None, None, None, None)
    def ciclo(ctx):
        seen.append(ctx)
        return {'fase_provavel': 'indefinido', 'confianca': 0}
    monkeypatch.setattr(regime_classifier, 'classificar_regime_do_macro_context', classifier)
    monkeypatch.setattr(ciclo_economico, 'calcular_indicadores_ciclo_br', ciclo)
    monkeypatch.setattr(ciclo_economico, 'calcular_indicadores_ciclo_us', ciclo)
    contexto = {'selic': 15, 'qualidade': {'selic': {'observado': False}}}
    estado = macro_state.get_macro_state.__wrapped__(contexto)
    assert estado.selic is estado.selic_real is estado.vix is None
    assert estado.score_ambiente is None
    assert estado.fase_sinais_validos == 0
    assert estado.fase_cobertura == 0
    assert estado.consenso == 'indefinido'
    assert seen == [contexto, contexto, contexto]


def test_monthly_gap_cannot_look_like_two_consecutive_monthly_rises():
    atividade = pd.Series([100, 99, 98, 98.2, 98.4],
                          index=pd.to_datetime(['2026-01-01','2026-02-01','2026-03-01','2026-05-01','2026-06-01']))
    assert recuperacao_persistente(atividade) is None
