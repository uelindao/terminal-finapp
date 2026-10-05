"""Monthly retrospective research with explicit weights and availability delays."""
from __future__ import annotations

import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.charts import base_layout, _cores
from utils.components import section_title, metric_card, empty_state, section_selector
from utils.macro_research import QUADRANTS, preparar_transicoes
from utils.rotation_matrix import metadata_padrao, carregar_precos_matriz

REGIMES = tuple(k for k in QUADRANTS if k not in ('transicao', 'indisponivel'))


def preparar_sinais_laboratorio(data, janela, persistencia, atraso_dias):
    history = preparar_transicoes(data['atividade'], data['inflacao'],
                                  inflacao_tipo=data['inflacao_tipo'], janela=janela,
                                  persistencia=persistencia)
    signals = history[['quadrante', 'confirmado']].copy()
    signals['referencia_em'] = signals.index
    signals['disponivel_em'] = signals.index + pd.Timedelta(days=int(atraso_dias))
    return signals.reset_index(drop=True)


def limites_precos_comuns(precos, tickers, inicio, fim):
    """Trim only exterior coverage; the simulator still rejects internal gaps."""
    starts, ends = [pd.Timestamp(inicio)], [pd.Timestamp(fim)]
    for ticker in tickers:
        if ticker not in precos:
            return None, None
        valid = pd.to_numeric(precos[ticker], errors='coerce').replace([float('inf'),-float('inf')],float('nan'))
        valid = valid[valid > 0].dropna()
        if valid.empty:
            return None, None
        starts.append(pd.Timestamp(valid.index.min()))
        ends.append(pd.Timestamp(valid.index.max()))
    return max(starts), min(ends)


def render_laboratorio_rotacao(bundle, horizonte_meses=6, key_prefix='macro_lab'):
    section_title('Laboratório de rotação')
    st.caption('Estudo retrospectivo mensal: escolha os instrumentos, escreva os pesos por direção macro e compare com um benchmark na mesma moeda.')
    a, b, c = st.columns(3)
    with a:
        region = st.selectbox('Economia e moeda', ['BR', 'US'],
                              format_func=lambda x: 'Brasil · BRL' if x == 'BR' else 'EUA · USD', key=key_prefix+'_region')
    with b:
        window = st.selectbox('Ritmo usado no sinal', [3, 6], format_func=lambda n:f'{n} meses', key=key_prefix+'_window')
    with c:
        persistence = st.selectbox('Observações para confirmar', [2, 3, 1], key=key_prefix+'_persistence')
    metadata = metadata_padrao(region)
    labels = {m['ticker']:m['label'] for m in metadata}
    options = list(labels)
    selection_key = key_prefix+'_assets_'+region
    defaults = ['BOVV11.SA', 'LFTS11.SA', 'IMAB11.SA'] if region == 'BR' else ['SPY', 'IEF', 'GLD']
    assets = st.multiselect('Instrumentos do estudo · até quatro', options, default=defaults, max_selections=4,
                            format_func=lambda x:f'{labels[x]} · {x}', key=selection_key)
    benchmark = 'BOVA11.SA' if region == 'BR' else 'SPY'
    delay_key = key_prefix+'_delay_'+region
    with st.expander('Premissas de disponibilidade e execução', expanded=False):
        delay = st.number_input('Atraso após o mês de referência (dias corridos)', min_value=0, max_value=180,
                                value=45 if region == 'BR' else 20, key=delay_key)
        cost = st.number_input('Custo por valor comprado ou vendido (pontos-base)', min_value=0.0, max_value=999.0,
                               value=10.0, step=1.0, key=key_prefix+'_cost')
        fraction = st.slider('Fração final reservada para comparação', .2, .5, .33, .01, key=key_prefix+'_fraction')
        today = pd.Timestamp.now(tz='America/Sao_Paulo').date()
        requested_dates = st.date_input('Janela desejada do estudo',
                                        value=((pd.Timestamp(today)-pd.DateOffset(years=6)).date(), today),
                                        key=key_prefix+'_dates')
        st.caption('Atraso é uma hipótese, não um calendário oficial de divulgação. Execução no fechamento do primeiro pregão de cada mês, usando apenas sinais confirmados disponíveis antes daquele dia. O retorno do dia da execução pertence à posição anterior. Turnover considera o valor comprado e vendido, com pesos que mudam entre rebalanceamentos.')
        st.caption('Os dados históricos usam as revisões disponíveis hoje. O trecho final reservado é uma comparação retrospectiva com pesos fixos; não valida uma estratégia que tenha sido escolhida sem conhecer o futuro. Impostos, spread variável e capacidade de execução não entram na conta.')
    if not assets:
        st.info('Selecione pelo menos um instrumento para definir os pesos.')
        return
    grid = pd.DataFrame([{'Direção macro':QUADRANTS[q], **{ticker:100/len(assets) for ticker in assets}} for q in REGIMES])
    st.caption('Pesos em %. O ponto de partida é igual em todas as direções; altere as linhas para testar sua hipótese de rotação. Cada linha deve somar 100%. Sem sinal confirmado, a posição anterior permanece.')
    weights = st.data_editor(grid, hide_index=True, width='stretch', disabled=['Direção macro'],
                             column_config={t:st.column_config.NumberColumn(t, min_value=0, max_value=100, required=True, format='%.2f%%') for t in assets},
                             key=key_prefix+'_weights_'+region+'_'+','.join(assets))
    weights_map = {q:{t:pd.to_numeric(weights.iloc[i][t], errors='coerce')/100 for t in assets} for i,q in enumerate(REGIMES)}
    valid_weights = all(all(math.isfinite(v) and 0 <= v <= 1 for v in row.values())
                        and abs(sum(row.values())-1) < 1e-6 for row in weights_map.values())
    if not valid_weights:
        st.warning('Corrija os pesos: cada direção precisa somar exatamente 100%.')
    dates_valid = isinstance(requested_dates, (tuple,list)) and len(requested_dates) == 2
    if not dates_valid:
        st.warning('Selecione o início e o fim da janela do estudo.')
    signature = (region, tuple(assets), window, persistence, int(delay), float(cost), float(fraction), tuple(requested_dates),
                 tuple((q,tuple(row.items())) for q,row in weights_map.items()))
    execute = st.button('Executar estudo histórico', type='primary', key=key_prefix+'_run', disabled=not (valid_weights and dates_valid), width='stretch')
    if execute:
        from utils.rotation_backtest import simular_rotacao
        data = bundle['regioes'][region]
        signals = preparar_sinais_laboratorio(data, window, persistence, delay)
        with st.spinner('Lendo apenas os instrumentos escolhidos e calculando o estudo…'):
            tickers = tuple(dict.fromkeys([*assets, benchmark]))
            prices = carregar_precos_matriz(tickers, dias=2080)
            first, last = limites_precos_comuns(prices, tickers, *requested_dates)
            result = simular_rotacao(prices, signals, weights_map, benchmark, custo_bps=cost,
                                      inicio=first, fim=last, fracao_avaliacao=fraction)
            result['janela_comum'] = (first,last)
        st.session_state[key_prefix+'_result'] = {'signature':signature, 'result':result}
    saved = st.session_state.get(key_prefix+'_result')
    if not saved or saved['signature'] != signature:
        empty_state('◌', 'Defina a hipótese e execute o estudo',
                    'O cálculo exige pelo menos 24 meses com preços completos após a primeira entrada. Dados ausentes suspendem o resultado.')
        return
    result = saved['result']
    common = result.get('janela_comum')
    if common and all(d is not None for d in common):
        st.caption(f'Janela comum de preços: {common[0]:%d/%m/%Y} a {common[1]:%d/%m/%Y}. '
                   'Início limitado pela existência dos instrumentos; lacunas internas permanecem inválidas.')
    for warning in result.get('avisos', []):
        st.caption(warning)
    if not result.get('ok'):
        st.warning(result.get('motivo') or 'Histórico insuficiente para esta hipótese.')
        coverage = result.get('cobertura')
        if isinstance(coverage, pd.DataFrame) and not coverage.empty:
            st.dataframe(coverage, width='stretch', hide_index=True)
        return
    summary = result['resumo']
    cols = st.columns(3)
    with cols[0]:
        metric_card('Rotação · retorno total', f"{summary['estrategia']['retorno_total']:.1%}", 'Após os custos definidos', 'info')
    with cols[1]:
        metric_card(f'Benchmark · {benchmark}', f"{summary['benchmark']['retorno_total']:.1%}", 'Mesma moeda e intervalo', 'info')
    with cols[2]:
        metric_card('Maior queda · rotação', f"{summary['estrategia']['drawdown_max']:.1%}", 'Queda desde o pico observado', 'amber')
    mode = section_selector(['Patrimônio', 'Rebalanceamentos', 'Comparação temporal', 'Cobertura'], key=key_prefix+'_view')
    if mode == 'Patrimônio':
        curve = result['curvas']
        fig = go.Figure()
        colors = _cores()
        for column,color in [('estrategia',colors['accent']), ('benchmark',colors['muted'])]:
            fig.add_trace(go.Scatter(x=curve.index, y=curve[column]*100, name='Rotação' if column=='estrategia' else benchmark,
                                     line=dict(color=color, width=2), connectgaps=False))
        fig.update_layout(**base_layout(height=400, title='Patrimônio normalizado · base 100'))
        st.plotly_chart(fig, width='stretch', key=key_prefix+'_equity')
        st.caption(f"Horizonte da tese: {horizonte_meses} meses. O estudo mantém o rebalanceamento mensal; a janela total e as datas aparecem na curva.")
    elif mode == 'Rebalanceamentos':
        st.dataframe(result['rebalanceamentos'], width='stretch', hide_index=True)
        st.download_button('Exportar execuções e pesos', result['rebalanceamentos'].to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'rotacao_{region.lower()}_execucoes.csv', mime='text/csv', key=key_prefix+'_export')
    elif mode == 'Comparação temporal':
        evaluation = result['avaliacao']
        st.caption(f"Corte temporal: {pd.Timestamp(evaluation['corte']):%d/%m/%Y}. Pesos e custos idênticos nos dois trechos.")
        records = []
        for period,label in [('construcao','Trecho inicial'), ('reservado','Trecho final reservado')]:
            for name,values in evaluation[period].items():
                records.append({'Trecho':label, 'Série':name, **values})
        st.dataframe(pd.DataFrame(records), width='stretch', hide_index=True)
        st.caption('Sem otimização automática de pesos. Se você ajustou a hipótese após observar os resultados, esse trecho também participou da escolha.')
    else:
        st.dataframe(result['cobertura'], width='stretch', hide_index=True)
        st.json(result['metodologia'])
