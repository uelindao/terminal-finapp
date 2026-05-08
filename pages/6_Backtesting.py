import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import datetime

from utils.auth import check_password

if not check_password():
    st.stop()

# Importa o Design System centralizado e o Catálogo de Tickers
from utils.style import aplicar_tema
from utils.tickers import get_opcoes_multiselect_backtesting, BR_ACOES

# --- Configuração da Página ---
st.set_page_config(page_title="Backtesting de Portfólio", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 📊 BACKTESTING DE PORTFÓLIO (NORMALIZADO)")
st.write("Compare a performance acumulada de diferentes ativos e benchmarks ao longo do tempo em base 100.")

# ==========================================
# PAINEL DE CONTROLE (UI) E MULTISELECT CENTRALIZADO
# ==========================================
st.markdown("---")
c1, c2, c3 = st.columns([5, 2, 2])

with c1:
    opcoes_bt = get_opcoes_multiselect_backtesting()
    
    # Blindagem: Garante que os defaults existem na lista para evitar StreamlitAPIException
    defaults_desejados = ["ITUB4.SA", "VALE3.SA", "^BVSP", "^GSPC"]
    defaults_seguros = [t for t in defaults_desejados if t in opcoes_bt]
    
    selecionados = st.multiselect(
        "SELECIONE OS ATIVOS E BENCHMARKS:",
        options=opcoes_bt,
        default=defaults_seguros
    )
    
    ticker_extra = st.text_input(
        "Adicionar ticker não listado (opcional):", ""
    ).strip().upper()
    
    if ticker_extra and ticker_extra not in selecionados:
        selecionados = selecionados + [ticker_extra]

with c2:
    periodo_opcoes = {"1 Ano": "1y", "2 Anos": "2y", "3 Anos": "3y", "5 Anos": "5y", "YTD": "ytd"}
    periodo_sel = st.selectbox("PERÍODO:", list(periodo_opcoes.keys()), index=0)

with c3:
    st.markdown("<br>", unsafe_allow_html=True)
    btn_calcular = st.button("CALCULAR BACKTEST", type="primary", use_container_width=True)

# ==========================================
# MOTOR DE CÁLCULO E GRÁFICO
# ==========================================
if btn_calcular or selecionados:
    if not selecionados:
        st.warning("Selecione pelo menos um ativo para iniciar a comparação.")
    else:
        with st.spinner("Sincronizando séries históricas e ajustando proventos..."):
            try:
                # auto_adjust=True garante que o ajuste venha no 'Close'
                dados_raw = yf.download(
                    selecionados, 
                    period=periodo_opcoes[periodo_sel], 
                    auto_adjust=True, 
                    progress=False
                )
                
                # Tratamento para quando o YF retorna apenas um ativo (Series) ou vários (DataFrame)
                if len(selecionados) == 1:
                    df_precos = dados_raw['Close'].to_frame()
                    df_precos.columns = selecionados
                else:
                    df_precos = dados_raw['Close']

                # Remove linhas sem dados (feriados específicos de um mercado)
                df_precos = df_precos.dropna(how='all').ffill()

                # CÁLCULO BASE 100 (Normalização)
                primeiro_preco = df_precos.iloc[0]
                df_norm = (df_precos / primeiro_preco) * 100

                # ==========================================
                # CONSTRUÇÃO DO GRÁFICO (Plotly)
                # ==========================================
                fig = go.Figure()

                for coluna in df_norm.columns:
                    retorno_total = df_norm[coluna].iloc[-1] - 100
                    fig.add_trace(go.Scatter(
                        x=df_norm.index, 
                        y=df_norm[coluna],
                        name=f"{coluna} ({retorno_total:+.2f}%)",
                        mode='lines',
                        line=dict(width=2),
                        hovertemplate="<b>%{x}</b><br>Base 100: %{y:.2f}<br>Retorno: %{customdata:+.2f}%<extra></extra>",
                        customdata=df_norm[coluna] - 100
                    ))

                fig.update_layout(
                    paper_bgcolor="#010101", 
                    plot_bgcolor="#010101",
                    height=550,
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#888888")),
                    margin=dict(l=0, r=0, t=30, b=0),
                    font=dict(family="Courier New")
                )

                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#222222', color="#888888")
                fig.update_yaxes(
                    title_text="Performance Acumulada (Base 100)", 
                    showgrid=True, 
                    gridwidth=1, 
                    gridcolor='#222222', 
                    color="#888888"
                )
                
                # Linha guia do 100 (Ponto de partida)
                fig.add_hline(y=100, line_dash="dash", line_color="#888888", opacity=0.5)

                st.plotly_chart(fig, use_container_width=True)

                # --- Cards de Resumo ---
                st.markdown("#### RESUMO DE PERFORMANCE NO PERÍODO")
                cols_metrics = st.columns(len(selecionados))
                for idx, col in enumerate(df_norm.columns):
                    retorno_final = df_norm[col].iloc[-1] - 100
                    cols_metrics[idx].metric(
                        label=col, 
                        value=f"{retorno_final:+.2f}%",
                        delta=f"Base 100: {df_norm[col].iloc[-1]:.2f}"
                    )
                    
                # ==========================================
                # MÉTRICAS DE PERFORMANCE E RISCO
                # ==========================================
                retornos = df_norm.pct_change().dropna()
                
                metricas = {}
                for col in retornos.columns:
                    total = (df_norm[col].iloc[-1] / 100) - 1
                    vol = retornos[col].std() * (252 ** 0.5)  # anualizada
                    sharpe = (retornos[col].mean() * 252) / (retornos[col].std() * (252**0.5)) if vol > 0 else 0
                    max_dd_serie = (df_norm[col] / df_norm[col].cummax() - 1)
                    max_dd = max_dd_serie.min()
                    metricas[col] = {
                        'Retorno Total %': f"{total*100:.2f}%",
                        'Volatilidade Anual %': f"{vol*100:.2f}%",
                        'Sharpe Ratio': f"{sharpe:.2f}",
                        'Max Drawdown %': f"{max_dd*100:.2f}%"
                    }
                
                df_metricas = pd.DataFrame(metricas).T
                st.markdown("---")
                st.markdown("#### 🧮 MÉTRICAS DE PERFORMANCE E RISCO")
                st.dataframe(df_metricas, use_container_width=True)

            except Exception as e:
                st.error(f"Erro ao calcular backtest: {str(e)}")