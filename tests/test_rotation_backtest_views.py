"""Offline interaction verification of the rotation laboratory."""
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from test_macro_research_views import FIXTURE_SOURCE
import utils.rotation_backtest_view as view


def test_lab_runs_from_explicit_request_and_invalidates_changed_assumptions(monkeypatch):
    dates = pd.bdate_range('2020-01-01','2026-01-01')
    columns = ['BOVV11.SA','LFTS11.SA','IMAB11.SA','BOVA11.SA']
    prices = pd.DataFrame({t:100*np.exp(np.arange(len(dates))*(.0001+i*.00005)) for i,t in enumerate(columns)},index=dates)
    calls = []
    def load(tickers, dias):
        calls.append((tickers,dias))
        return prices
    monkeypatch.setattr(view,'carregar_precos_matriz',load)
    app = AppTest.from_string(FIXTURE_SOURCE+'\nfrom utils.rotation_backtest_view import render_laboratorio_rotacao\nrender_laboratorio_rotacao(bundle)').run(timeout=30)
    assert not app.exception
    assert calls == []
    app.button(key='macro_lab_run').click().run(timeout=30)
    assert not app.exception
    assert len(calls) == 1 and len(calls[0][0]) == 4
    assert app.session_state['macro_lab_result']['result']['ok']
    assert len(app.get('plotly_chart')) == 1
    for mode in ['Rebalanceamentos','Comparação temporal','Cobertura','Patrimônio']:
        app.get('button_group')[0].set_value(mode).run(timeout=30)
        assert not app.exception
    assert len(calls) == 1
    app.number_input(key='macro_lab_cost').set_value(20.0).run()
    assert not app.exception
    assert len(app.get('plotly_chart')) == 0


def test_lab_incomplete_cache_returns_coverage_instead_of_fabricated_performance(monkeypatch):
    monkeypatch.setattr(view,'carregar_precos_matriz',lambda *a,**k:pd.DataFrame())
    app = AppTest.from_string(FIXTURE_SOURCE+'\nfrom utils.rotation_backtest_view import render_laboratorio_rotacao\nrender_laboratorio_rotacao(bundle)').run(timeout=30)
    app.button(key='macro_lab_run').click().run(timeout=30)
    assert not app.exception
    assert not app.session_state['macro_lab_result']['result']['ok']
    assert len(app.warning) >= 1
    assert len(app.get('plotly_chart')) == 0


def test_lab_common_window_respects_inception_without_filling_internal_gaps():
    dates = pd.bdate_range('2020-01-01','2026-01-01')
    prices = pd.DataFrame({'A':100.,'B':200.},index=dates)
    prices.loc[prices.index<'2022-01-01','B']=np.nan
    prices.loc[pd.Timestamp('2024-01-02'),'B']=np.nan
    first,last = view.limites_precos_comuns(prices,['A','B'],dates[0],dates[-1])
    assert first == pd.Timestamp('2022-01-03')
    assert last == dates[-1]
    assert pd.isna(prices.loc['2024-01-02','B'])
