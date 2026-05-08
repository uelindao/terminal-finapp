import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from fredapi import Fred
from bcb import sgs

from utils.auth import check_password

if not check_password():
    st.stop()

from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label

# --- Configuração da Página ---
st.set_page_config(page_title="Overlay Macro", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 🔭 OVERLAY MACRO")
st.write("Sobreponha a cotação do ativo com indicadores macroeconômicos globais para identificar correlações.")

# ==========================================
# SEÇÃO DE BUSCA PADRONIZADA (Briefing 3)
# ==========================================
col_sel_ov, col_man_ov, col_ind = st.columns([3, 2, 3])
with col_sel_ov:
    opcoes_ov = get_opcoes_selectbox()
    selecao_ov = st.selectbox("ATIVO:", opcoes_ov, key="overlay_sel")
with col_man_ov:
    ticker_manual_ov = st.text_input(
        "Ou digite:", "", key="overlay_manual"
    ).strip().upper()

with col_ind:
    indicador = st.selectbox("INDICADOR MACRO:", [
        "Taxa Selic (Brasil)", 
        "IPCA (Inflação BR)", 
        "Fed Funds Rate (Juros EUA)", 
        "Treasury 10Y (EUA)", 
        "VIX (S&P 500 Volatility)"
    ])

ticker_input = ticker_manual_ov if ticker_manual_ov else (ticker_from_label(selecao_ov) or "PETR4.SA")

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# MOTOR DO OVERLAY MACRO
# ==========================================
if st.button("GERAR OVERLAY MACRO", type="primary", use_container_width=True):
    if not ticker_input or ticker_input.startswith("─"):
        st.warning("Selecione um ativo válido para iniciar a análise.")
        st.stop()
        
    with st.spinner(f"Buscando histórico de {ticker_input} e série macroeconômica..."):
        try:
            # 1. Busca os dados da ação (últimos 5 anos)
            stock_data = yf.download(ticker_input, period="5y", auto_adjust=True, progress=False)['Close']
            if isinstance(stock_data, pd.DataFrame):
                 stock_data = stock_data[ticker_input]
                 
            stock_data = stock_data.dropna()
            
            # Limpa o fuso horário (tz-naive) para o Plotly não quebrar
            if hasattr(stock_data.index, 'tz') and stock_data.index.tz is not None:
                stock_data.index = stock_data.index.tz_localize(None)

            # 2. Busca os dados Macro
            hoje = datetime.datetime.today()
            inicio = hoje - datetime.timedelta(days=5*365)
            macro_data = None
            macro_name = ""

            if "Selic" in indicador:
                macro_data = sgs.get({'Selic': 432}, start=inicio)['Selic']
                macro_name = "Taxa Selic (%)"
            elif "IPCA" in indicador:
                macro_data = sgs.get({'IPCA': 433}, start=inicio)['IPCA']
                macro_name = "IPCA (%)"
            else:
                if "FRED_API_KEY" not in st.secrets:
                    st.error("A chave FRED_API_KEY não foi encontrada no ficheiro secrets.toml. Necessária para dados dos EUA.")
                    st.stop()
                    
                fred = Fred(api_key=st.secrets["FRED_API_KEY"])
                if "Fed Funds" in indicador:
                    macro_data = fred.get_series('FEDFUNDS', observation_start=inicio)
                    macro_name = "Fed Funds Rate (%)"
                elif "Treasury" in indicador:
                    macro_data = fred.get_series('DGS10', observation_start=inicio)
                    macro_name = "Treasury 10Y (%)"
                elif "VIX" in indicador:
                    macro_data = fred.get_series('VIXCLS', observation_start=inicio)
                    macro_name = "Índice VIX"

            if macro_data is not None:
                macro_data = macro_data.dropna()
                if hasattr(macro_data.index, 'tz') and macro_data.index.tz is not None:
                    macro_data.index = macro_data.index.tz_localize(None)

                # 3. Desenho do Gráfico com 2 Eixos
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                
                # Eixo Esquerdo (Ação)
                fig.add_trace(
                    go.Scatter(x=stock_data.index, y=stock_data, name=ticker_input, line=dict(color="#FF9900", width=2)),
                    secondary_y=False
                )
                
                # Eixo Direito (Macro)
                fig.add_trace(
                    go.Scatter(x=macro_data.index, y=macro_data, name=macro_name, line=dict(color="#00FFFF", dash="dot", width=2)),
                    secondary_y=True
                )

                fig.update_layout(
                    paper_bgcolor="#010101", 
                    plot_bgcolor="#010101", 
                    height=500,
                    font=dict(family="Courier New", color="#888888"),
                    hovermode="x unified",
                    title=f"Estudo de Correlação: {ticker_input} vs {macro_name}",
                    margin=dict(l=0, r=0, t=40, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                
                fig.update_yaxes(title_text=f"Preço {ticker_input}", showgrid=True, gridcolor='#222222', secondary_y=False)
                fig.update_yaxes(title_text=macro_name, showgrid=False, secondary_y=True)
                fig.update_xaxes(showgrid=True, gridcolor='#222222')

                st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.warning("Não foi possível obter a série de dados macroeconómicos neste momento.")
                
        except Exception as e:
            st.error(f"Erro ao processar e alinhar os dados: {e}")