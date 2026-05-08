import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

from utils.auth import check_password

if not check_password():
    st.stop()

# Importações do projeto
from utils.style import aplicar_tema
from database.db import listar_watchlist, get_pesos, salvar_peso, get_health_scores
from utils.email_sender import enviar_relatorio_semanal

# --- Configuração da Página ---
st.set_page_config(page_title="Portfolio Analytics", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 💼 PORTFOLIO ANALYTICS")
st.write("Visão consolidada da sua carteira, P&L (Lucros e Perdas) e análise de risco.")

# ==========================================
# SEÇÃO 1 — DEFINIÇÃO DE POSIÇÕES (UX Melhorada via Data Editor)
# ==========================================
watchlist = listar_watchlist()
pesos_atuais = {p['ticker']: p for p in get_pesos()}

with st.expander("⚖️ COMPOSIÇÃO DO PORTFÓLIO (Planilha Rápida)", expanded=True):
    st.info("💡 **Esqueça as percentagens!** Preencha apenas a **Quantidade** e o **Preço Médio** que pagou. O terminal calculará os pesos da sua carteira automaticamente.")
    
    # 1. Prepara os dados num formato tabular (Pandas DataFrame)
    dados_tabela = []
    for item in watchlist:
        t = item['ticker']
        p_atual = pesos_atuais.get(t, {})
        
        # Tratamento rigoroso para evitar "None" na tabela
        qtd = p_atual.get('quantidade')
        qtd = float(qtd) if qtd is not None else 0.0
        
        pm = p_atual.get('preco_medio')
        pm = float(pm) if pm is not None else 0.0
        
        dados_tabela.append({"Ticker": t, "Quantidade": qtd, "Preço Médio": pm})
        
    df_base = pd.DataFrame(dados_tabela)
    
    # 2. Renderiza a planilha interativa estilo Excel
    if not df_base.empty:
        df_editado = st.data_editor(
            df_base,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Ticker": st.column_config.TextColumn("Ativo (Watchlist)", disabled=True),
                "Quantidade": st.column_config.NumberColumn(
                    "Quantidade Atual", 
                    min_value=0.0, 
                    step=0.0001, # Permite frações para criptos/tokens
                    format="%.4f"
                ),
                "Preço Médio": st.column_config.NumberColumn(
                    "Preço Médio Pago ($/R$)", 
                    min_value=0.0, 
                    step=0.0001, # Permite frações pequenas
                    format="%.4f"
                )
            }
        )
        
        if st.button("💾 SALVAR E REBALANCEAR", type="primary", use_container_width=True):
            # 3. Matemática Automática: Calcula o património total para derivar os pesos
            df_editado['Valor Total'] = df_editado['Quantidade'] * df_editado['Preço Médio']
            patrimonio_total = df_editado['Valor Total'].sum()
            
            # 4. Salva no banco de dados com os pesos matematicamente perfeitos
            for _, row in df_editado.iterrows():
                t = row['Ticker']
                qtd = row['Quantidade']
                pm = row['Preço Médio']
                
                if patrimonio_total > 0 and qtd > 0:
                    peso_real = (row['Valor Total'] / patrimonio_total) * 100
                else:
                    peso_real = 0.0
                    
                salvar_peso(t, peso_real, pm, qtd)
                
            st.success("✅ Portfólio atualizado! Pesos calculados com precisão absoluta.")
            st.rerun()
    else:
        st.warning("A sua Watchlist está vazia. Adicione ativos na Home primeiro.")
        st.stop()

# ==========================================
# SEÇÃO 2 — CÁLCULOS BASE E COLETA DE DADOS LIVES
# ==========================================
# Filtrar apenas ativos com peso > 0 para as análises subsequentes
ativos_alocados = {t: d for t, d in pesos_atuais.items() if d['peso'] > 0}

if not ativos_alocados:
    st.warning("O seu portfólio está vazio ou sem capital alocado. Preencha a planilha acima e clique em 'Salvar' para visualizar os gráficos de risco.")
    st.stop()

tickers_com_peso = list(ativos_alocados.keys())

with st.spinner("A sincronizar cotações em tempo real para cálculo de P&L..."):
    live_data = {}
    try:
        hist = yf.download(tickers_com_peso, period="5d", auto_adjust=True, progress=False)['Close']
        if len(tickers_com_peso) == 1:
            hist = hist.to_frame(name=tickers_com_peso[0])
        hist = hist.ffill()
        
        for t in tickers_com_peso:
            try:
                preco_atual = float(hist[t].dropna().iloc[-1])
                live_data[t] = preco_atual
            except:
                live_data[t] = 0.0
    except Exception as e:
        st.error("Erro ao transferir dados da bolsa.")

# ==========================================
# SEÇÃO 3 — MÉTRICAS GLOBAIS E TABELA DE P&L
# ==========================================
st.markdown("---")
st.markdown("#### 📊 PERFORMANCE E DISTRIBUIÇÃO")

linhas_portfolio = []
custo_total_carteira = 0.0
valor_atual_carteira = 0.0

health_data = {h['ticker']: h.get('score', 50) for h in get_health_scores()}

for t, dados in ativos_alocados.items():
    qtd = float(dados.get('quantidade', 0))
    pm = float(dados.get('preco_medio', 0))
    preco_atual = live_data.get(t, 0.0)
    
    custo_posicao = qtd * pm
    valor_posicao = qtd * preco_atual
    
    pnl_valor = valor_posicao - custo_posicao
    pnl_pct = (pnl_valor / custo_posicao * 100) if custo_posicao > 0 else 0.0
    
    custo_total_carteira += custo_posicao
    valor_atual_carteira += valor_posicao
    
    linhas_portfolio.append({
        "Ativo": t,
        "Qtd": qtd,
        "Preço Médio": pm,
        "Preço Atual": preco_atual,
        "Custo Total": custo_posicao,
        "Valor Atual": valor_posicao,
        "P&L ($)": pnl_valor,
        "P&L (%)": pnl_pct,
        "Health Score": health_data.get(t, "N/A")
    })

df_portfolio = pd.DataFrame(linhas_portfolio)

# Recalcular os pesos reais com base no VALOR ATUAL (Mark-to-Market)
if valor_atual_carteira > 0:
    df_portfolio['Peso Atual (%)'] = (df_portfolio['Valor Atual'] / valor_atual_carteira) * 100
else:
    df_portfolio['Peso Atual (%)'] = 0.0

# Métricas Topo
pnl_global_valor = valor_atual_carteira - custo_total_carteira
pnl_global_pct = (pnl_global_valor / custo_total_carteira * 100) if custo_total_carteira > 0 else 0.0

col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("Custo Total Alocado", f"{custo_total_carteira:,.2f}")
col_m2.metric("Património Atual (Mark-to-Market)", f"{valor_atual_carteira:,.2f}", f"{pnl_global_pct:+.2f}%")
col_m3.metric("P&L Global (Lucro/Prejuízo)", f"{pnl_global_valor:+,.2f}", delta_color="normal")

st.markdown("<br>", unsafe_allow_html=True)

# Tabela Formatada
def colorir_pnl(val):
    if pd.isna(val) or val == 0: return ''
    return 'color: #00FF00' if val > 0 else 'color: #FF0000'

st.dataframe(
    df_portfolio.style
        .applymap(colorir_pnl, subset=['P&L ($)', 'P&L (%)'])
        .format({
            "Qtd": "{:.4f}",
            "Preço Médio": "{:.4f}",
            "Preço Atual": "{:.2f}",
            "Custo Total": "{:,.2f}",
            "Valor Atual": "{:,.2f}",
            "P&L ($)": "{:+,.2f}",
            "P&L (%)": "{:+.2f}%",
            "Peso Atual (%)": "{:.2f}%"
        }),
    use_container_width=True,
    hide_index=True
)

# ==========================================
# SEÇÃO 4 — GRÁFICOS DE ALOCAÇÃO E RISCO
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)
col_g1, col_g2 = st.columns(2)

with col_g1:
    st.markdown("**⚖️ Alocação por Ativo**")
    fig_pie = go.Figure(go.Pie(
        labels=df_portfolio['Ativo'],
        values=df_portfolio['Valor Atual'],
        hole=0.4,
        textinfo='label+percent',
        marker=dict(line=dict(color='#010101', width=2))
    ))
    fig_pie.update_layout(
        paper_bgcolor="#010101", 
        plot_bgcolor="#010101",
        font=dict(family="Courier New", color="#E0E0E0"),
        margin=dict(t=20, b=20, l=20, r=20),
        height=350
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_g2:
    st.markdown("**📈 P&L por Ativo ($/R$)**")
    df_pnl = df_portfolio.sort_values(by='P&L ($)', ascending=True)
    fig_bar = go.Figure(go.Bar(
        x=df_pnl['P&L ($)'],
        y=df_pnl['Ativo'],
        orientation='h',
        marker_color=['#FF0000' if val < 0 else '#00FF00' for val in df_pnl['P&L ($)']]
    ))
    fig_bar.update_layout(
        paper_bgcolor="#010101", 
        plot_bgcolor="#010101",
        font=dict(family="Courier New", color="#E0E0E0"),
        margin=dict(t=20, b=20, l=20, r=20),
        height=350,
        xaxis=dict(showgrid=True, gridcolor='#222222'),
        yaxis=dict(showgrid=False)
    )
    st.plotly_chart(fig_bar, use_container_width=True)