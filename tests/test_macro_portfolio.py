"""Cenários por posição/moeda e cobertura de base, sem rede."""
import math
import pytest
from utils.macro_portfolio import montar_exposicoes, simular_cenario, resumo_exposicoes


def positions():
    return [{'ticker':'PETR4.SA','quantidade':10,'preco_medio':30},
            {'ticker':'AAPL','quantidade':2,'preco_medio':90}]


def test_value_weights_use_observed_quote_and_fx():
    exp = montar_exposicoes(positions(),{'PETR4.SA':{'preco':40},'AAPL':{'preco':100,'moeda':'USD'}},
                            {'PETR4.SA':{'setor':'Energy'}},{'USD':5})
    assert exp['valor_base_brl'] == 1400
    assert exp['total_completo']
    assert exp['posicoes'][0]['peso_pct'] == pytest.approx(400/1400*100)
    assert exp['posicoes'][1]['peso_pct'] == pytest.approx(1000/1400*100)
    assert exp['n_custo'] == 0


def test_currency_and_fx_are_not_invented():
    exp = montar_exposicoes(positions(),{'PETR4.SA':{'preco':40},'AAPL':{'preco':100}},cambios={'USD':5})
    assert exp['posicoes'][1]['moeda'] == 'a confirmar'
    assert exp['posicoes'][1]['valor_brl'] is None
    assert exp['valor_base_brl'] == 400
    assert not exp['total_completo']
    assert exp['cobertura_posicoes_pct'] == 50
    assert exp['posicoes'][1]['peso_pct'] is None


def test_known_currency_without_fx_still_unknown_brl():
    exp = montar_exposicoes(positions(),{'AAPL':{'preco':100,'moeda':'USD'}})
    assert exp['posicoes'][1]['valor_local'] == 200
    assert exp['posicoes'][1]['cambio_brl'] is None
    assert exp['posicoes'][1]['valor_brl'] is None
    assert exp['n_custo'] == 1
    assert exp['posicoes'][0]['base_valor'].startswith('custo')


def test_local_and_fx_shocks_compose_exactly_and_brl_has_no_direct_fx():
    exp = montar_exposicoes(positions(),{'AAPL':{'preco':100,'moeda':'USD'}},cambios={'USD':5})
    r = simular_cenario(exp,{'PETR4.SA':-10,'AAPL':-10},{'USD':10,'BRL':50})
    assert r['posicoes'][1]['impacto_pct'] == pytest.approx(-1)
    assert r['posicoes'][0]['impacto_pct'] == pytest.approx(-10)
    assert r['delta_brl'] == pytest.approx(-40)
    assert r['valor_cenario_brl'] == pytest.approx(1260)


def test_non_usd_currency_and_manual_profiles_are_supported():
    pos = [{'ticker':'SAP.DE','quantidade':1,'preco_medio':100}]
    exp = montar_exposicoes(pos,{'SAP.DE':{'preco':200,'moeda':'EUR'}},cambios={'EUR':6},
        ajustes={'SAP.DE':{'classe':'renda fixa prefixada','crescimento':'baixa'}})
    assert exp['posicoes'][0]['juros_duration'] == 'alta'
    assert exp['posicoes'][0]['crescimento'] == 'baixa'
    assert exp['valor_base_brl'] == 1200
    assert simular_cenario(exp,{}, {'EUR':10})['delta_brl'] == pytest.approx(120)


@pytest.mark.parametrize('v',[-101,math.nan,math.inf,None])
def test_invalid_shocks_do_not_produce_results(v):
    exp = montar_exposicoes(positions()[:1])
    with pytest.raises(ValueError):
        simular_cenario(exp,{'PETR4.SA':v})


def test_qualitative_exposures_do_not_become_automatic_returns():
    exp = montar_exposicoes(positions()[:1],fundamentos={'PETR4.SA':{'setor':'Energy'}})
    assert exp['posicoes'][0]['commodities'] == 'alta'
    assert simular_cenario(exp)['impacto_pct'] == 0
    assert sum(r['peso_pct'] for r in resumo_exposicoes(exp) if r['fator'] == 'commodities') == 100


def test_negative_and_invalid_quantities_never_receive_weights():
    exp = montar_exposicoes([{'ticker':'X','quantidade':-1},{'ticker':'Y','quantidade':math.nan}])
    assert exp['posicoes'] == []
    assert exp['valor_base_brl'] == 0
    assert not exp['total_completo']


def test_view_renders_unknown_fx_and_zero_scenario_without_external_calls():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string('''
from utils.macro_portfolio_view import render_cenarios_macro
render_cenarios_macro({'AAPL':{'quantidade':2,'preco_medio':90}},
                     {'AAPL':{'preco':100,'moeda':'USD'}}, {'AAPL':{'setor':'Technology'}}, portfolio_id=17)
''').run(timeout=20)
    assert not at.exception
    assert any('parcial' in w.value.lower() for w in at.warning)
    at.number_input[0].set_value(5).run()
    assert not at.exception
    assert not at.warning
    at.slider[0].set_value(10).run()
    assert not at.exception
    assert any('+10.00%' in m.value for m in at.markdown)
