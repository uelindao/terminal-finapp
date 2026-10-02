"""Data and interaction regressions for the personal watchlist explorer."""
import json
from textwrap import dedent

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from utils.market_explorer import market_snapshot, relative_paths, normalized_history
from utils.components import inline_sparkline


def test_snapshot_preserves_missing_and_zero_observations():
    assets = [{'ticker': 'PETR4.SA'}, {'ticker': 'AAPL'}, {'ticker': 'MSFT'}]
    result = market_snapshot(assets, {'PETR4.SA': {'var_1d': 0, 'var_1m': float('nan')}},
                             {'PETR4.SA': {'score': 0}, 'AAPL': {'score': 85}})
    assert result.iloc[0]['retorno_dia'] == 0
    assert result.iloc[0]['score'] == 0
    assert pd.isna(result.iloc[0]['retorno_mes'])
    assert pd.isna(result.iloc[1]['retorno_dia'])
    assert pd.isna(result.iloc[2]['score'])
    assert result['moeda'].tolist() == ['R$', 'US$', 'US$']


def test_comparison_uses_common_trailing_window_and_same_origin():
    quotes = {'AAPL': {'serie_30d': [5, 10, 20, 30]},
              'MSFT': {'serie_30d': [50, 60, 75]}}
    paths = relative_paths(['AAPL', 'MSFT'], quotes)
    assert len(paths) == 3
    assert paths.iloc[0].tolist() == [0, 0]
    assert paths.iloc[-1].tolist() == pytest.approx([200, 50])
    short = relative_paths(['AAPL', 'MSFT'], quotes, observations=2)
    assert short.iloc[-1].tolist() == pytest.approx([50, 25])


def test_comparison_rejects_gaps_and_invalid_price_paths():
    quotes = {'gap': {'serie_30d': [10, np.nan, 12]},
              'zero': {'serie_30d': [0, 10]},
              'empty': {'serie_30d': []},
              'valid': {'serie_30d': pd.Series([10, 11, 12])}}
    result = relative_paths(list(quotes), quotes)
    assert result.columns.tolist() == ['valid']
    assert result['valid'].tolist() == pytest.approx([0, 10, 20])


def test_sparkline_accepts_pandas_and_ignores_nonfinite_values():
    html = inline_sparkline(pd.Series([10, np.nan, 12, np.inf, 14]))
    assert '<polyline' in html
    assert 'nan' not in html
    assert 'inf' not in html
    assert inline_sparkline(pd.Series(dtype=float)) == ''


def test_profiles_apply_to_plotly_without_breaking_filled_lines_and_candles():
    source = '''
        import json
        import pandas as pd
        import streamlit as st
        from utils.appearance import set_perfil
        from utils.charts import aplicar_template_ativo, base_layout, _axis, linha, velas
        data = pd.DataFrame({'Open':[10,11], 'High':[12,13], 'Low':[9,10], 'Close':[11,12], 'Volume':[100,110]}, index=pd.date_range('2026-01-01',periods=2))
        results = []
        for profile in ['terminal', 'mesa', 'caderno', 'radar']:
            set_perfil(profile)
            aplicar_template_ativo()
            line = linha(data, None, 'Close', fill=True)
            candles = velas(data, mostrar_volume=True)
            results.append([profile, base_layout()['height'], _axis()['showgrid'], line.data[0].fillcolor, candles.data[0].increasing.fillcolor])
        st.text(json.dumps(results))
    '''
    at = AppTest.from_string(dedent(source)).run()
    assert not at.exception, [e.message for e in at.exception]
    results = json.loads(at.text[0].value)
    assert [r[1] for r in results] == [330, 400, 450, 480]
    assert [r[2] for r in results] == [True, True, False, True]
    assert all(r[3].startswith('rgba(') and r[4].startswith('rgba(') for r in results)


def test_map_and_comparison_render_with_sparse_watchlist():
    source = '''
        import streamlit as st
        import pandas as pd
        import utils.price_history as ph
        ph.obter_close_carteira = lambda *a, **k: pd.DataFrame()
        from utils.market_explorer import render_market_explorer
        assets = [{'ticker':'AAPL','nome':'Apple'}, {'ticker':'MSFT','nome':'Microsoft'}]
        quotes = {'AAPL': {'preco':100,'var_1d':1,'var_1m':5,'serie_30d':[90,95,100]}}
        scores = {'AAPL': {'score':75}}
        view = st.radio('View', ['Mapa', 'Comparar'])
        render_market_explorer(assets,quotes,scores,view,1)
    '''
    at = AppTest.from_string(dedent(source)).run()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.get('plotly_chart')) == 1
    assert any('fora do mapa' in caption.value for caption in at.caption)
    at.radio[0].set_value('Comparar').run()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.get('plotly_chart')) == 1
    assert any('Sem série suficiente: MSFT' in caption.value for caption in at.caption)


def test_dated_comparison_uses_shared_dates_and_rejects_filled_gaps():
    frame = pd.DataFrame({'AAPL':[10, 11, None, 13], 'MSFT':[None, 20, 21, 22]}, index=pd.date_range('2026-01-01',periods=4))
    result = normalized_history(frame, ['AAPL','MSFT'])
    assert result.index.tolist() == [pd.Timestamp('2026-01-02'), pd.Timestamp('2026-01-04')]
    assert result.iloc[0].tolist() == [0,0]
    assert result.iloc[-1].tolist() == pytest.approx([(13/11-1)*100,10])
    assert normalized_history(frame, ['AAPL','MSFT']).shape == (2,2)
