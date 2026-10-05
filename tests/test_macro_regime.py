"""Proveniência do regime legado e compatibilidade de chamadas históricas."""
import math
from types import SimpleNamespace
import pytest
import utils.macro_regime as regime


@pytest.fixture(autouse=True)
def session_context(monkeypatch):
    ctx = {'selic':13.75, 'vix':17, 'ipca':4.5, 'treasury_10y':4.3,
           'qualidade':{'selic':{'observado':False}, 'vix':{'observado':False}}}
    monkeypatch.setattr(regime, 'st', SimpleNamespace(session_state={'macro_context':ctx}))
    return ctx


def test_fallback_context_never_produces_observed_regime_or_score():
    r = regime.classificar_regime()
    assert r['regime_key'] == 'indefinido'
    assert r['score_ambiente'] is None
    assert r['selic'] is r['vix'] is None
    assert r['setores_favorecidos'] == r['setores_prejudicados'] == []
    assert r['cobertura_eixos'] == 0
    impact = regime.get_impacto_setor('financeiro', r)
    assert impact['impacto'] == 'neutro'
    assert 'não determinado' in impact['justificativa']


def test_explicit_historical_values_are_not_contaminated_by_current_session():
    r = regime.classificar_regime(selic=13.75, vix=17, ipca=4.5, treasury_10y=4.3)
    assert r['regime_key'] == 'juros_muito_altos_risco_controlado'
    assert r['score_ambiente'] == 65
    assert r['qualidade']['selic']['observado']


def test_context_argument_conserves_provenance_even_with_explicit_values(session_context):
    r = regime.classificar_regime(selic=13.75, vix=17, macro_context=session_context)
    assert r['regime_key'] == 'indefinido'
    assert r['score_ambiente'] is None


def test_only_observed_rate_and_risk_define_regime_without_fabricating_extra_fields():
    r = regime.classificar_regime(macro_context={'selic':0, 'vix':15})
    assert r['regime_key'] == 'juros_baixos_risco_controlado'
    assert r['score_ambiente'] == 100
    assert r['selic'] == 0
    assert r['ipca'] is r['treasury_10y'] is None
    assert r['ausentes'] == ['ipca', 'treasury_10y']


@pytest.mark.parametrize('valor', [math.nan, math.inf, None, True, 'inválido'])
def test_invalid_axis_stays_unknown(valor):
    r = regime.classificar_regime(macro_context={'selic':valor, 'vix':15})
    assert r['regime_key'] == 'indefinido'
    assert r['score_ambiente'] is None
    assert r['cobertura_eixos'] == .5


def test_annual_inflation_contract_preferred_over_legacy_alias():
    r = regime.classificar_regime(macro_context={'selic':12, 'vix':15, 'ipca':.3, 'ipca_12m':5.1})
    assert r['ipca'] == 5.1


def test_missing_context_never_uses_default_macro_constants():
    r = regime.classificar_regime(macro_context={})
    assert r['regime_key'] == 'indefinido'
    assert r['score_ambiente'] is None
    assert set(r['ausentes']) == {'selic','vix','ipca','treasury_10y'}
