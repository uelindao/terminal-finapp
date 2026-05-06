import streamlit as st
import yfinance as yf
import plotly.express as px
import pandas as pd
import datetime

st.set_page_config(page_title="Backtesting de Portfólio", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #010101; color: #E0E0E0; }
    h1, h2, h3, h4, h5, h6 { color: #FF9900 !important; font-family: 'Courier New', Courier, monospace; text-transform: uppercase; font-size: 1.2rem; margin-bottom: 0px; }
    .block-container { padding-top: 3.5rem; padding-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("### BACKTESTING DE PORTFÓLIO (NORMALIZADO)")

# Dicionário simplificado para o exemplo
opcoes_ativos = ["PETR4.SA", "VALE3.SA", "ITUB4.SA", "WEGE3.SA", "BBAS3.SA", "AAPL", "MSFT", "NVDA", "^BVSP", "^GSPC"]

col1, col2 = st.columns([7, 3])
with col1:
    ativos_selecionados = st.multiselect("SELECIONE OS ATIVOS E BENCHMARKS:", opcoes_ativos, default=["WEGE3.SA", "ITUB4.SA", "^BVSP"])
with col2:
    periodo = st.selectbox("PERÍODO:", ["1y", "2y", "5y", "10y"], index=0)

st.markdown("---")

if ativos_selecionados:
    with st.spinner("Calculando retornos históricos..."):
        try:
            # Baixa os dados de fechamento ajustado (já desconta dividendos)
            dados = yf.download(ativos_selecionados, period=periodo)['Adj Close']
            
            # Se for apenas 1 ativo, o yfinance retorna uma Series, precisamos converter para DataFrame
            if isinstance(dados, pd.Series):
                dados = dados.to_frame(name=ativos_selecionados[0])
            
            # Normalização (Base 100): Pega o preço de hoje, divide pelo primeiro dia, multiplica por 100
            # Isso mostra a evolução percentual de todos saindo da mesma linha de largada
            dados_normalizados = (dados / dados.iloc[0]) * 100
            
            # Remove timezone se houver
            if str(dados_normalizados.index.tz) != 'None':
                dados_normalizados.index = dados_normalizados.index.tz_localize(None)

            fig = px.line(dados_normalizados, x=dados_normalizados.index, y=dados_normalizados.columns)
            fig.update_layout(
                paper_bgcolor="#010101", plot_bgcolor="#010101",
                xaxis=dict(showgrid=True, gridcolor='#222222', title=""),
                yaxis=dict(showgrid=True, gridcolor='#222222', title="Retorno (Base 100)"),
                margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified", height=500,
                font=dict(family="Courier New", color="#888888"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title="")
            )
            st.plotly_chart(fig, use_container_width=True)
            
        except Exception as e:
            st.error(f"Erro ao calcular backtest: {e}")
else:
    st.warning("Selecione pelo menos um ativo para iniciar o Backtest.")