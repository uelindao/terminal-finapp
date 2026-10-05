"""Interaction checks for the macro workbench with isolated illustrative data."""
from textwrap import dedent

import pytest
from streamlit.testing.v1 import AppTest

FIXTURE_SOURCE = """
import streamlit as st
import pandas as pd
import numpy as np
from utils.macro_research_view import render_transicoes, render_expectativas
dates = pd.date_range('2020-01-31', periods=60, freq='ME')
activity = pd.Series(100*np.exp(np.linspace(0,.3,60)+.02*np.sin(np.arange(60)/4)), index=dates)
inflation = pd.Series(.3+.15*np.sin(np.arange(60)/5), index=dates)
us_prices = pd.DataFrame({'INDPRO':activity, 'CPIAUCSL':100*(1+inflation/100).cumprod(),
                         'DFII10':2.0, 'DGS10':4.0, 'T10YIE':2.2}, index=dates)
focus_dates = pd.date_range(pd.Timestamp.today().normalize()-pd.Timedelta(days=120), periods=120)
focus = pd.DataFrame([
 {'data':d,'indicador':indicator,'horizonte':horizon,'mediana':base+i*.001,'respondentes':100,'base_calculo':0}
 for i,d in enumerate(focus_dates)
 for indicator,horizon,base in [('IPCA',str(pd.Timestamp.today().year+1),4.),
                              ('Selic',str(pd.Timestamp.today().year+1),10.),
                              ('PIB Total',str(pd.Timestamp.today().year+1),2.),
                              ('IPCA','12m móveis',4.5)]])
bundle = {'regioes':{
 'BR':{'atividade':activity,'inflacao':inflation,'inflacao_tipo':'mensal_pct','atividade_label':'IBC-Br · amostra','dados':pd.DataFrame({'IBC_Br':activity,'IPCA':inflation})},
 'US':{'atividade':activity,'inflacao':us_prices['CPIAUCSL'],'inflacao_tipo':'indice','atividade_label':'Produção industrial · amostra','dados':us_prices}},
 'focus':focus,'qualidade':[],'avisos':[],'base_temporal':'Dados ilustrativos'}
"""


def run(extra):
    at = AppTest.from_string(dedent(FIXTURE_SOURCE + extra), default_timeout=20).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def test_transition_views_and_region_switch_keep_valid_dates():
    at = run("\nrender_transicoes(bundle)")
    for value in ("Ritmos", "Evidências", "Mapa"):
        at.get("button_group")[0].set_value(value).run()
        assert not at.exception, [e.message for e in at.exception]
    at.selectbox(key="macro_transitions_region").set_value("US").run()
    assert not at.exception
    at.selectbox(key="macro_transitions_window").set_value(6).run()
    assert not at.exception
    assert len(at.select_slider[0].options) > 1


def test_expectation_views_target_year_and_missing_revision():
    at = run("\nrender_expectativas(bundle, {'selic': 10})")
    for value in ("Inflação 12m", "Juros e preços", "Ano de referência"):
        at.get("button_group")[0].set_value(value).run()
        assert not at.exception, [e.message for e in at.exception]
    at.selectbox(key="macro_expectations_revision").set_value(90).run()
    assert not at.exception


def test_empty_sources_render_without_fake_metrics_or_errors():
    at = run("""
bundle['regioes']['BR']['atividade'] = pd.Series(dtype=float)
bundle['focus'] = pd.DataFrame()
render_transicoes(bundle)
render_expectativas(bundle)
""")
    assert not at.exception
    assert len(at.get("plotly_chart")) == 0



def test_calendar_window_keeps_missing_months_and_comparison_options_update():
    import numpy as np
    import pandas as pd
    from utils.macro_research_view import recortar_trajetoria
    frame = pd.DataFrame({'delta_atividade': np.arange(24,dtype=float)},
                         index=pd.date_range('2024-01-31', periods=24, freq='ME'))
    frame.iloc[19] = np.nan
    cut = recortar_trajetoria(frame, frame.index[-1], 12)
    assert len(cut) == 12
    assert cut.index[0] == pd.Timestamp('2025-01-31')
    assert pd.isna(cut.iloc[7,0])
    app = run('\nrender_transicoes(bundle)')
    app.get('button_group')[0].set_value('Evidências').run()
    app.select_slider[0].set_value(pd.Timestamp('2020-10-31').to_pydatetime()).run()
    assert not app.exception


def test_stale_rolling_focus_cannot_enter_proxy_with_fresh_annual_research():
    app = run("""
bundle['focus'].loc[bundle['focus']['horizonte']=='12m móveis','data'] -= pd.Timedelta(days=40)
render_expectativas(bundle, {'selic':10})
""")
    app.get('button_group')[0].set_value('Juros e preços').run()
    assert not app.exception
    assert any('Proxy suspensa' in c.value for c in app.caption)
    app.get('button_group')[0].set_value('Inflação 12m').run()
    assert any('desatualizada' in w.value for w in app.warning)
