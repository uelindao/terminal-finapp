"""Interactive views of the already loaded watchlist; no extra data requests."""
from math import isfinite
import numpy as np

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.charts import base_layout, _axis, _cores, _palette
from utils.components import metric_card
from utils.formatters import fmt_preco
from utils.tickers import mapear_ticker_base


def _number(value):
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def market_snapshot(assets, quotes, scores):
    """Preserve missing observations instead of positioning them at zero."""
    rows = []
    for asset in assets:
        ticker = asset['ticker']
        base = mapear_ticker_base(ticker)
        quote = quotes.get(ticker, quotes.get(base, {})) or {}
        health = scores.get(ticker, scores.get(base, {})) or {}
        rows.append({
            'ticker': ticker, 'label': ticker.replace('.SA', ''),
            'nome': asset.get('nome') or ticker,
            'retorno_dia': _number(quote.get('var_1d')),
            'retorno_mes': _number(quote.get('var_1m')),
            'score': _number(health.get('score')),
            'preco': _number(quote.get('preco')) if (_number(quote.get('preco')) or 0) > 0 else None,
            'moeda': 'R$' if base.endswith('.SA') else 'US$',
        })
    return pd.DataFrame(rows, columns=[
        'ticker', 'label', 'nome', 'retorno_dia', 'retorno_mes', 'score', 'preco', 'moeda',
    ])


def relative_paths(tickers, quotes, observations=30):
    """Align cached undated paths by trailing observation; never imply dates."""
    paths = {}
    for ticker in tickers:
        quote = quotes.get(ticker, quotes.get(mapear_ticker_base(ticker), {})) or {}
        raw = quote.get('serie_30d')
        if raw is None:
            continue
        values = [_number(value) for value in list(raw)[-observations:]]
        # Dropping internal gaps would shift one asset relative to another.
        if len(values) >= 2 and all(v is not None and v > 0 for v in values):
            paths[ticker] = values
    if not paths:
        return pd.DataFrame()
    common_length = min(len(values) for values in paths.values())
    return pd.DataFrame({
        ticker: [(value / values[-common_length] - 1) * 100
                 for value in values[-common_length:]]
        for ticker, values in paths.items()
    }, index=range(1, common_length + 1))


def normalized_history(history, tickers):
    """Date-aligned relative paths on valid shared observations, with no forward fill."""
    if history is None or history.empty:
        return pd.DataFrame()
    data = history.reindex(columns=[t for t in tickers if t in history.columns]).apply(pd.to_numeric, errors='coerce')
    data = data.replace([np.inf, -np.inf], np.nan).where(data > 0)
    data = data.loc[:, data.count() >= 2].dropna().sort_index()
    if len(data) < 2:
        return pd.DataFrame()
    return (data / data.iloc[0] - 1) * 100


def _open_asset(ticker):
    st.session_state['research_ticker_externo'] = ticker
    st.switch_page('pages/1_Research.py')


def _asset_lens(snapshot, ticker):
    row = snapshot.loc[snapshot['ticker'] == ticker].iloc[0]
    st.caption(f"{row['label']} · {row['nome']}")
    columns = st.columns(4)
    for col, label, value, suffix in zip(columns,
            ['Preço', 'Variação hoje', 'Variação 1 mês', 'Score'],
            [row['preco'], row['retorno_dia'], row['retorno_mes'], row['score']],
            [row['moeda'], '%', '%', '/100']):
        with col:
            missing = pd.isna(value)
            text = '—' if missing else (fmt_preco(value, suffix) if label == 'Preço'
                    else f'{value:+.2f}%' if suffix == '%' else f'{value:.0f}/100')
            tone = 'muted' if missing or suffix != '%' else 'bull' if value >= 0 else 'bear'
            metric_card(label, text, 'Sem dado' if missing else '', cor_delta=tone)
    st.button(f"Abrir análise de {row['label']}", key='wl_explorer_open',
              icon=':material/query_stats:', on_click=_open_asset, args=(ticker,))


@st.fragment
def render_market_explorer(assets, quotes, scores, view, watchlist_id):
    """Chart controls rerun only this view; filtering remains owned by Home."""
    snapshot = market_snapshot(assets, quotes, scores)
    if snapshot.empty:
        st.info('Nenhum ativo neste recorte. Ajuste os filtros de mercado e tag.')
        return
    colors = _cores()
    if view == 'Mapa':
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            horizon = st.radio('Retorno no eixo horizontal', ['1 mês', 'Hoje'],
                              horizontal=True, key='wl_map_horizon')
        with c2:
            interaction = st.radio('Interação', ['Ativo', 'Grupo'], horizontal=True, key='wl_map_interaction')
        with c3:
            st.caption('Passe o cursor para ler. Clique em um ponto para inspecionar.' if interaction == 'Ativo' else 'Arraste uma caixa no gráfico para selecionar um grupo; o laço está na barra de ferramentas.')
        x_column = 'retorno_mes' if horizon == '1 mês' else 'retorno_dia'
        valid = snapshot.dropna(subset=[x_column, 'score'])
        excluded = len(snapshot) - len(valid)
        if valid.empty:
            st.info('O mapa precisa de retorno e score disponíveis. A lista continua mostrando todos os ativos.')
            return
        color_values = valid['retorno_dia'].fillna(0).tolist()
        bound = max(1.0, max(abs(value) for value in color_values))
        custom = valid[['ticker', 'nome', 'retorno_dia', 'retorno_mes']].fillna('—').values
        fig = go.Figure(go.Scatter(
            x=valid[x_column], y=valid['score'], customdata=custom,
            text=valid['label'], mode='markers+text', textposition='top center',
            textfont=dict(color=colors['text'], size=11),
            marker=dict(size=14, color=color_values, cmin=-bound, cmax=bound,
                        colorscale=[[0, colors['bear']], [.5, colors['muted']], [1, colors['bull']]],
                        line=dict(color=colors['surface'], width=2), showscale=False),
            selected=dict(marker=dict(opacity=1, size=18)),
            unselected=dict(marker=dict(opacity=.35)),
            hovertemplate='<b>%{text}</b><br>%{customdata[1]}<br>Retorno: %{x:+.2f}%<br>Score: %{y:.0f}/100<extra></extra>',
        ))
        fig.update_layout({**base_layout(height=430), 'hovermode': 'closest'},
                          dragmode='pan' if interaction == 'Ativo' else 'select', clickmode='event+select',
                          xaxis={**_axis(), 'title': f'Retorno {horizon.lower()} (%)'},
                          yaxis={**_axis(), 'title': 'Score fundamentalista', 'range': [-5, 105]})
        fig.add_vline(x=0, line_color=colors['border'], line_dash='dash')
        event = st.plotly_chart(fig, use_container_width=True, theme=None,
                               key=f'wl_map_{watchlist_id}_{x_column}_{interaction}', on_select='rerun',
                               selection_mode='points' if interaction == 'Ativo' else ['box', 'lasso'],
                               config={'displaylogo': False, 'scrollZoom': False})
        if excluded:
            st.caption(f'{excluded} ativo(s) fora do mapa por falta de retorno ou score. Cor: variação de hoje; cinza também representa variação diária indisponível.')
        else:
            st.caption('Cor: variação de hoje. Score e retorno descrevem dimensões diferentes do ativo.')
        points = event.selection.points if event else []
        selected_tickers = [p.get('customdata', [None])[0] for p in points if p.get('customdata')]
        selected_tickers = [t for t in selected_tickers if t in snapshot['ticker'].values]
        if selected_tickers:
            lens_options = selected_tickers
            st.caption(f'{len(selected_tickers)} ativo(s) selecionado(s) no mapa.')
        else:
            lens_options = snapshot['ticker'].tolist()
        lens_key = f'wl_map_lens_{watchlist_id}'
        if st.session_state.get(lens_key) not in lens_options:
            st.session_state[lens_key] = lens_options[0]
        ticker = st.selectbox('Inspecionar ativo', lens_options, key=lens_key,
                              format_func=lambda t: t.replace('.SA', ''))
        _asset_lens(snapshot, ticker)
    else:
        available = snapshot['ticker'].tolist()
        select_key = f'wl_compare_assets_{watchlist_id}'
        if select_key in st.session_state:
            st.session_state[select_key] = [t for t in st.session_state[select_key] if t in available]
        columns = st.columns([3, 1, 1])
        with columns[0]:
            chosen = st.multiselect('Ativos para comparar', available, default=available[:3],
                                    format_func=lambda t: t.replace('.SA', ''),
                                    max_selections=6, key=select_key)
        periods = {'1 mês': ('1mo', 22), '3 meses': ('3mo', 66), '6 meses': ('6mo', 132), '1 ano': ('1y', 252)}
        with columns[1]:
            period_label = st.selectbox('Período', list(periods), key='wl_compare_period')
        with columns[2]:
            perspective = st.selectbox('Perspectiva', ['Retorno', 'Drawdown'], key='wl_compare_perspective')
        if not chosen:
            st.info('Selecione os ativos que deseja comparar.')
            return
        period, observations = periods[period_label]
        from utils.price_history import obter_close_carteira
        with st.spinner('Carregando a janela de comparação…'):
            history = obter_close_carteira(tuple(chosen), periodo=period)
        dated = history is not None and not history.empty
        paths = normalized_history(history.tail(observations), chosen) if dated else relative_paths(chosen, quotes, min(observations, 30))
        if paths.empty:
            st.info('Não há pelo menos duas observações comuns para estes ativos. Reduza a seleção ou amplie o período.')
            return
        plotted = ((paths / 100 + 1) / (paths / 100 + 1).cummax() - 1) * 100 if perspective == 'Drawdown' else paths
        missing = [t for t in chosen if t not in paths.columns]
        if missing:
            st.caption('Sem série suficiente: ' + ', '.join(t.replace('.SA', '') for t in missing))
        fig = go.Figure()
        palette = _palette()
        for index, ticker in enumerate(paths.columns):
            fig.add_trace(go.Scatter(x=plotted.index, y=plotted[ticker], mode='lines',
                name=ticker.replace('.SA', ''), line=dict(color=palette[index % len(palette)], width=2),
                hovertemplate=f'{ticker.replace(".SA", "")} · %{{y:+.2f}}%<extra></extra>'))
        fig.update_layout(**base_layout(height=410),
            xaxis={**_axis(), 'title': 'Data' if dated else 'Observação na janela comum'},
            yaxis={**_axis(), 'title': 'Queda desde o pico na janela (%)' if perspective == 'Drawdown' else 'Variação desde a primeira observação (%)'})
        fig.add_hline(y=0, line_color=colors['border'], line_dash='dash')
        st.plotly_chart(fig, use_container_width=True, theme=None, key=f'wl_compare_{watchlist_id}',
                        config={'displaylogo': False})
        st.caption(f'{len(paths)} observações comuns · {period_label} · moeda original de cada ativo. ' + ('Somente datas compartilhadas, sem preencher lacunas. ' if dated else 'Cache sem datas: alinhamento pelo fim da série, limitado a 30 observações. ') + 'Clique na legenda para ocultar uma trajetória; dê dois cliques para isolá-la.')
        summary = snapshot[snapshot['ticker'].isin(paths.columns)].copy()
        summary['janela'] = summary['ticker'].map(plotted.iloc[-1].to_dict())
        st.dataframe(summary[['label', 'janela', 'retorno_dia', 'retorno_mes', 'score']],
                     hide_index=True, use_container_width=True,
                     column_config={'label': 'Ativo',
                         'janela': st.column_config.NumberColumn('Drawdown atual (%)' if perspective == 'Drawdown' else 'Retorno na janela (%)', format='%+.2f'),
                         'retorno_dia': st.column_config.NumberColumn('Hoje (%)', format='%+.2f'),
                         'retorno_mes': st.column_config.NumberColumn('1 mês (%)', format='%+.2f'),
                         'score': st.column_config.NumberColumn('Score', format='%.0f')})
