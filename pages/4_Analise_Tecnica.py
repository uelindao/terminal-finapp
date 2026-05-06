import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Análise Técnica", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #010101; color: #E0E0E0; }
    h1, h2, h3, h4, h5, h6 { color: #FF9900 !important; font-family: 'Courier New', Courier, monospace; text-transform: uppercase; font-size: 1.2rem; margin-bottom: 0px; }
    .block-container { padding-top: 3.5rem; padding-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("### ANÁLISE TÉCNICA E PRICE ACTION")

col1, col2 = st.columns([2, 8])
with col1:
    ticker = st.text_input("TICKER:", value="PETR4.SA").upper()
    periodo = st.selectbox("PERÍODO:", ["6mo", "1y", "2y"], index=0)

st.markdown("---")

if ticker:
    with st.spinner("Gerando Candlesticks e Indicadores..."):
        try:
            df = yf.download(ticker, period=periodo)
            
            if not df.empty:
                if str(df.index.tz) != 'None': df.index = df.index.tz_localize(None)
                
                # Cálculos de Indicadores Técnicos
                df['SMA_50'] = df['Close'].rolling(window=50).mean()
                df['SMA_200'] = df['Close'].rolling(window=200).mean()
                
                fig = go.Figure()
                
                # Plot Candlestick
                fig.add_trace(go.Candlestick(
                    x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                    name="Preço", increasing_line_color='#00FF00', decreasing_line_color='#FF0000'
                ))
                
                # Plot Médias Móveis
                fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], mode='lines', name='SMA 50', line=dict(color='#00FFFF', width=1)))
                fig.add_trace(go.Scatter(x=df.index, y=df['SMA_200'], mode='lines', name='SMA 200', line=dict(color='#FF00FF', width=1.5)))
                
                fig.update_layout(
                    paper_bgcolor="#010101", plot_bgcolor="#010101",
                    xaxis=dict(showgrid=True, gridcolor='#222222', rangeslider=dict(visible=False)),
                    yaxis=dict(showgrid=True, gridcolor='#222222'),
                    margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified", height=600,
                    font=dict(family="Courier New", color="#888888")
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("Ticker não encontrado.")
        except Exception as e:
            st.error(f"Erro no processamento técnico: {e}")