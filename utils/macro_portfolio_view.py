"""Exploração de exposições e cenário local × FX para a carteira pessoal."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from utils.components import section_title, portfolio_kpis
from utils.charts import base_layout, _cores
from utils.macro_portfolio import montar_exposicoes, resumo_exposicoes, simular_cenario, FATORES, NIVEIS, numero
from utils.tickers import mapear_ticker_base

LABELS = {'juros_duration':'Juros / duration','crescimento':'Crescimento','credito':'Crédito','commodities':'Commodities'}


def render_cenarios_macro(posicoes, precos_cache=None, fundamentos=None, macro_context=None,
                          portfolio_id=None, key_prefix='portfolio_macro'):
    section_title('Cenários macro da carteira')
    st.caption('As etiquetas econômicas são hipóteses qualitativas editáveis. O cenário aplica somente os choques de preço e câmbio que você definir; não é uma previsão.')
    key = f'{key_prefix}_{portfolio_id or "atual"}'
    holdings = [{'ticker':tk,'ticker_base':mapear_ticker_base(tk),**d} for tk,d in posicoes.items()] if isinstance(posicoes,dict) else posicoes
    if not holdings:
        st.info('Adicione posições com quantidade positiva para explorar cenários.')
        return
    precos_cache, fundamentos = precos_cache or {}, fundamentos or {}
    cambios = {}
    # Aceita cotação observada em cache; nunca usa get_cambio_usd_brl com fallback.
    pc_fx = precos_cache.get('BRL=X') or {}
    usd = numero(pc_fx.get('preco') or pc_fx.get('price'))
    if usd is None:
        from utils.regime_classifier import valor_observado
        usd = valor_observado(macro_context or {},'usd_brl','dolar')
    if usd is not None and usd > 0:
        cambios['USD'] = usd
    inicial = montar_exposicoes(holdings,precos_cache,fundamentos,cambios)
    perfil_df = pd.DataFrame([{k:p[k] for k in ('ticker','setor','classe','moeda',*FATORES)} for p in inicial['posicoes']])
    if perfil_df.empty:
        st.info('Nenhuma posição long com quantidade válida neste portfólio.')
        return
    with st.expander('Revisar perfil econômico e moedas',expanded=False):
        st.caption('Moeda é a cotação do instrumento. Exposição econômica de receitas/custos pode ser distinta. Alterações ficam nesta sessão e não mudam suas posições.')
        cols = {f:st.column_config.SelectboxColumn(LABELS[f],options=NIVEIS,required=True) for f in FATORES}
        cols['moeda'] = st.column_config.TextColumn('Moeda da cotação · código de 3 letras')
        editado = st.data_editor(perfil_df,disabled=['ticker'],hide_index=True,width='stretch',
                               column_config=cols,key=key+'_perfil')
    ajustes = {str(row['ticker']):row.to_dict() for _,row in editado.iterrows()}
    moedas = sorted({str(row['moeda']).upper() for _,row in editado.iterrows() if str(row['moeda']).upper() != 'BRL' and len(str(row['moeda'])) == 3})
    with st.expander('Câmbio usado na base · BRL por unidade de moeda',expanded=any(m not in cambios for m in moedas)):
        st.caption('Sem câmbio válido, a posição permanece fora da base modelada. Um valor digitado é uma premissa manual explícita, não uma cotação observada.')
        for moeda in moedas:
            valor = st.number_input(f'{moeda} → BRL',min_value=0.0,value=float(cambios.get(moeda,0)),format='%.4f',key=key+'_fxbase_'+moeda)
            if valor > 0:
                cambios[moeda] = valor
        if usd is not None:
            st.caption(f'USD/BRL observado na base/cache: {usd:.4f}. Você pode ajustar a premissa acima.')
    exposicoes = montar_exposicoes(holdings,precos_cache,fundamentos,cambios,ajustes)
    portfolio_kpis([
        {'nome':'Base modelada','valor':f"R$ {exposicoes['valor_base_brl']:,.2f}",'sublabel':'patrimônio completo' if exposicoes['total_completo'] else 'subtotal conhecido; não é o patrimônio total'},
        {'nome':'Cobertura','valor':f"{exposicoes['n_valoradas']}/{exposicoes['n_posicoes']}",'sublabel':'posições com valor e câmbio válidos'},
        {'nome':'Base pelo custo','valor':str(exposicoes['n_custo']),'sublabel':'posições sem cotação em cache','tone':'amber'},
    ])
    if not exposicoes['total_completo']:
        st.warning('Resultado parcial: posições sem moeda, preço/custo ou câmbio não entram no subtotal nem no peso modelado.')
    base_df = pd.DataFrame(exposicoes['posicoes'])
    st.dataframe(base_df[['ticker','setor','classe','moeda','valor_local','cambio_brl','valor_brl','peso_pct','base_valor','referencia_preco']],
                 hide_index=True,width='stretch')
    resumo = pd.DataFrame(resumo_exposicoes(exposicoes))
    cores = _cores()
    fig = go.Figure()
    paleta = [cores['bear'],cores['amber'],cores['bull'],cores['accent'],cores['muted']]
    for nivel,cor in zip(NIVEIS,paleta):
        recorte = resumo[resumo['nivel'] == nivel]
        fig.add_trace(go.Bar(name=nivel,x=[LABELS[f] for f in recorte['fator']],y=recorte['peso_pct'],marker_color=cor))
    fig.update_layout(**base_layout(height=310),barmode='stack',yaxis_title='Peso da base modelada (%)')
    st.plotly_chart(fig,width='stretch',theme=None,key=key+'_exposicoes')
    st.caption('Alta/média/baixa/mista expressam relevância econômica presumida, sem coeficiente de retorno. “A confirmar” preserva a falta de evidência.')
    section_title('Defina seu cenário condicional')
    nome = st.text_input('Nome do cenário',value='Hipótese de rotação',key=key+'_nome',max_chars=150)
    st.caption('Defina o impacto local por ativo, em %. Choques em juros ou crescimento precisam ser traduzidos por você em uma hipótese de preço; o terminal não inventa essa sensibilidade.')
    cenario_df = pd.DataFrame([{'ticker':p['ticker'],'setor':p['setor'],'moeda':p['moeda'],'impacto_local_pct':0.0} for p in exposicoes['posicoes']])
    choques_df = st.data_editor(cenario_df,disabled=['ticker','setor','moeda'],hide_index=True,width='stretch',
      column_config={'impacto_local_pct':st.column_config.NumberColumn('Impacto local assumido (%)',min_value=-100.0,max_value=1000.0,step=1.0)},key=key+'_choques')
    choque_fx = {}
    for moeda in moedas:
        choque_fx[moeda] = st.slider(f'Choque em {moeda}/BRL (%)',min_value=-50.0,max_value=50.0,value=0.0,step=1.0,key=key+'_choque_'+moeda)
    try:
        resultado = simular_cenario(exposicoes,{str(row['ticker']):row['impacto_local_pct'] for _,row in choques_df.iterrows()},choque_fx)
    except ValueError as exc:
        st.error(str(exc))
        return
    impacto = resultado['impacto_pct']
    portfolio_kpis([
        {'nome':'Impacto condicional','valor':f'{impacto:+.2f}%' if impacto is not None else 'n/d','sublabel':nome,'tone':'bear' if impacto is not None and impacto < 0 else 'info'},
        {'nome':'Variação em BRL','valor':f"R$ {resultado['delta_brl']:+,.2f}",'sublabel':'sobre a base modelada'},
        {'nome':'Base após cenário','valor':f"R$ {resultado['valor_cenario_brl']:,.2f}",'sublabel':'subtotal' if not resultado['total_completo'] else 'cenário da carteira'},
    ])
    df_resultado = pd.DataFrame(resultado['posicoes'])
    validos = df_resultado.dropna(subset=['delta_brl'])
    if not validos.empty:
        fig = go.Figure(go.Bar(x=validos['ticker'],y=validos['delta_brl'],
            marker_color=[cores['bear'] if v < 0 else cores['bull'] for v in validos['delta_brl']]))
        fig.update_layout(**base_layout(height=310),yaxis_title='Contribuição no cenário (BRL)')
        st.plotly_chart(fig,width='stretch',theme=None,key=key+'_resultado')
    st.dataframe(df_resultado[['ticker','moeda','peso_pct','choque_local_pct','choque_fx_pct','impacto_pct','delta_brl']],hide_index=True,width='stretch')
    st.caption('Fórmula: (1 + choque local) × (1 + choque cambial) − 1. Exemplo: −10% local e +10% cambial = −1% em BRL. Exportadoras em BRL só recebem o efeito que você incluir no choque local.')
    st.download_button('Exportar premissas e resultado em CSV',data=df_resultado.to_csv(index=False),mime='text/csv',
                       file_name='cenario_macro_carteira.csv',key=key+'_export')
