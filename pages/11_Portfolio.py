import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy.stats import norm
import json

# Importações do projeto
from utils.style import aplicar_tema
from database.db import listar_watchlist, get_connection, salvar_peso, get_pesos, get_health_scores
from utils.email_sender import enviar_relatorio_semanal

# --- Configuração da Página ---
st.set_page_config(page_title="Portfolio Analytics", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 💼 PORTFOLIO ANALYTICS")
st.write("Visão consolidada da sua carteira, P&L (Lucros e Perdas) e análise de risco.")

# ==========================================
# SEÇÃO 1 — DEFINIÇÃO DE PESOS E POSIÇÕES
# ==========================================
watchlist = listar_watchlist()
pesos_atuais = {p['ticker']: p for p in get_pesos()}

with st.expander("⚖️ COMPOSIÇÃO DO PORTFÓLIO (Inserir Posições)", expanded=False):
    st.info("Defina o peso (%), preço médio de compra e quantidade de cada ativo na sua carteira real.")
    
    total_pesos = 0
    novos_dados = {}
    
    with st.form("form_pesos"):
        # Cabeçalhos da tabela
        c_h1, c_h2, c_h3, c_h4 = st.columns([2, 2, 2, 2])
        c_h1.markdown("**TICKER**")
        c_h2.markdown("**PESO (%)**")
        c_h3.markdown("**PREÇO MÉDIO (R$ ou $)**")
        c_h4.markdown("**QUANTIDADE**")
        
        for item in watchlist:
            t = item['ticker']
            p_atual = pesos_atuais.get(t, {})
            
            c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
            with c1: 
                st.markdown(f"<div style='margin-top:10px; font-weight:bold; color:#FF9900;'>{t}</div>", unsafe_allow_html=True)
            with c2:
                peso_val = float(p_atual.get('peso') or 0.0)
                peso = st.number_input(f"Peso {t}", 0.0, 100.0, value=peso_val, key=f"peso_{t}", step=0.5, label_visibility="collapsed")
            with c3:
                pm_val = float(p_atual.get('preco_medio') or 0.0)
                pm = st.number_input(f"PM {t}", value=pm_val, key=f"pm_{t}", format="%.2f", label_visibility="collapsed")
            with c4:
                qtd_val = float(p_atual.get('quantidade') or 0.0)
                qtd = st.number_input(f"Qtd {t}", value=qtd_val, key=f"qtd_{t}", format="%.4f", label_visibility="collapsed")
                
            total_pesos += peso
            novos_dados[t] = {'peso': peso, 'pm': pm, 'qtd': qtd}

        # Indicador de total
        cor_total = "#00FF00" if 98 <= total_pesos <= 102 else "#FF9900"
        st.markdown(
            f'<div style="color:{cor_total}; font-family:Courier New; font-size: 1.2rem; font-weight: bold; margin-top: 10px;">'
            f'PESO TOTAL ALOCADO: {total_pesos:.1f}% {"✓" if 98<=total_pesos<=102 else "(Atenção: O ideal é somar 100%)"}'
            f'</div>',
            unsafe_allow_html=True
        )

        if st.form_submit_button("💾 SALVAR ALOCAÇÃO", type="primary", use_container_width=True):
            for t, dados in novos_dados.items():
                salvar_peso(t, dados['peso'], dados['pm'], dados['qtd'])
            st.success("Alocação salva com sucesso!")
            st.rerun()

# Filtrar apenas ativos com peso > 0 para as análises
ativos_alocados = {t: d for t, d in pesos_atuais.items() if d['peso'] > 0}

if not ativos_alocados:
    st.warning("O seu portfólio está vazio. Preencha e salve a alocação acima para ver as análises.")
    st.stop()

# ==========================================
# CÁLCULOS BASE (COLETA DE DADOS)
# ==========================================
tickers_com_peso = list(ativos_alocados.keys())
pesos_lista = np.array([ativos_alocados[t]['peso'] / 100 for t in tickers_com_peso])

# Normaliza os pesos para o cálculo de rentabilidade (se o usuário alocou 80%, trata como 100% da parte alocada)
pesos_normalizados = pesos_lista / pesos_lista.sum()

with st.spinner("Processando métricas e histórico de risco da carteira..."):
    # Coleta histórico de 1 ano
    df_prices = yf.download(tickers_com_peso + ['^BVSP'], period="1y", auto_adjust=True, progress=False)['Close']
    
    if isinstance(df_prices, pd.Series):
        df_prices = df_prices.to_frame()
        
    df_prices = df_prices.dropna(how='all').ffill()
    
    # Extrair benchmark
    if '^BVSP' in df_prices.columns:
        bench_prices = df_prices['^BVSP']
        port_prices = df_prices.drop(columns=['^BVSP'], errors='ignore')
    else:
        bench_prices = None
        port_prices = df_prices

    # Retornos Diários
    df_returns = port_prices.pct_change().dropna()
    
    # Retorno do Portfólio (soma ponderada)
    port_returns = (df_returns * pesos_normalizados).sum(axis=1)
    
    # Retorno do Benchmark
    if bench_prices is not None:
        bench_returns = bench_prices.pct_change().dropna()
        # Alinha os índices
        common_idx = port_returns.index.intersection(bench_returns.index)
        port_returns_aligned = port_returns.loc[common_idx]
        bench_returns_aligned = bench_returns.loc[common_idx]
    
# ==========================================
# SEÇÃO 2 — MÉTRICAS DE PORTFÓLIO
# ==========================================
st.markdown("---")
st.markdown("#### 🎯 MÉTRICAS CONSOLIDADAS DE RISCO E RETORNO (1 Ano)")

try:
    retorno_anual = (port_prices.iloc[-1] / port_prices.iloc[0] - 1)
    retorno_port_anual = (retorno_anual * pesos_normalizados).sum() * 100
    
    volatilidade_anual = port_returns.std() * np.sqrt(252) * 100
    
    risk_free_rate = 0.105 # Taxa Selic proxy
    sharpe = (port_returns.mean() * 252 - risk_free_rate) / (port_returns.std() * np.sqrt(252)) if port_returns.std() > 0 else 0
    
    cum_returns = (1 + port_returns).cumprod()
    max_dd = (cum_returns / cum_returns.cummax() - 1).min() * 100
    
    if bench_prices is not None and not port_returns_aligned.empty:
        cov = np.cov(port_returns_aligned, bench_returns_aligned)[0][1]
        var_bench = np.var(bench_returns_aligned)
        beta = cov / var_bench if var_bench > 0 else 1
    else:
        beta = np.nan
        
    # VaR Paramétrico 95% Diário
    var_95 = norm.ppf(0.05, port_returns.mean(), port_returns.std()) * 100

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Retorno 1 Ano", f"{retorno_port_anual:+.2f}%")
    c2.metric("Volatilidade (a.a)", f"{volatilidade_anual:.2f}%")
    c3.metric("Max Drawdown", f"{max_dd:.2f}%")
    c4.metric("Índice Sharpe", f"{sharpe:.2f}")
    c5.metric("Beta (vs IBOV)", f"{beta:.2f}" if not np.isnan(beta) else "N/D")
    c6.metric("VaR 95% (Diário)", f"{var_95:.2f}%", help="Perda máxima diária esperada em 95% dos dias normais.")
    
except Exception as e:
    st.warning("Dados insuficientes para calcular todas as métricas consolidadas.")

# ==========================================
# SEÇÃO 3 — GRÁFICOS VISUAIS
# ==========================================
st.markdown("---")

c_graf1, c_graf2 = st.columns(2)

with c_graf1:
    st.markdown("##### 🍕 ALOCAÇÃO POR ATIVO")
    fig_pie = go.Figure(go.Pie(
        labels=tickers_com_peso,
        values=[ativos_alocados[t]['peso'] for t in tickers_com_peso],
        hole=0.4,
        textinfo='label+percent'
    ))
    fig_pie.update_layout(
        paper_bgcolor="#010101", plot_bgcolor="#010101",
        font=dict(family="Courier New", color="#E0E0E0"),
        height=350, margin=dict(l=0,r=0,t=20,b=0)
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with c_graf2:
    st.markdown("##### 🏢 ALOCAÇÃO POR SETOR")
    setores = {}
    for t in tickers_com_peso:
        try:
            setor = yf.Ticker(t).info.get('sector', 'Outros')
            setores[setor] = setores.get(setor, 0) + ativos_alocados[t]['peso']
        except:
            setores['Outros'] = setores.get('Outros', 0) + ativos_alocados[t]['peso']
            
    fig_sec = go.Figure(go.Pie(
        labels=list(setores.keys()),
        values=list(setores.values()),
        hole=0.4,
        textinfo='label+percent'
    ))
    fig_sec.update_layout(
        paper_bgcolor="#010101", plot_bgcolor="#010101",
        font=dict(family="Courier New", color="#E0E0E0"),
        height=350, margin=dict(l=0,r=0,t=20,b=0)
    )
    st.plotly_chart(fig_sec, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)
c_graf3, c_graf4 = st.columns(2)

with c_graf3:
    st.markdown("##### 📈 EVOLUÇÃO (PORTFÓLIO vs IBOV)")
    fig_evo = go.Figure()
    
    # Normaliza a curva do portfólio para base 100
    port_evo = (1 + port_returns).cumprod() * 100
    fig_evo.add_trace(go.Scatter(x=port_evo.index, y=port_evo, name='Meu Portfólio', line=dict(color='#FFFFFF', width=2)))
    
    if bench_prices is not None:
        bench_evo = (1 + bench_returns_aligned).cumprod() * 100
        fig_evo.add_trace(go.Scatter(x=bench_evo.index, y=bench_evo, name='IBOVESPA', line=dict(color='#FF9900', width=1.5)))

    fig_evo.update_layout(
        paper_bgcolor="#010101", plot_bgcolor="#010101", height=350,
        margin=dict(l=0,r=0,t=10,b=0), font=dict(family="Courier New", color="#888"),
        xaxis=dict(showgrid=True, gridcolor='#222'), yaxis=dict(showgrid=True, gridcolor='#222')
    )
    st.plotly_chart(fig_evo, use_container_width=True)

with c_graf4:
    st.markdown("##### 🌡️ MATRIZ DE CORRELAÇÃO (DIVERSIFICAÇÃO)")
    df_corr = df_returns.corr()
    
    fig_corr = px.imshow(
        df_corr,
        color_continuous_scale='RdYlGn_r', # Vermelho (Correlacionado), Verde (Descorrelacionado)
        zmin=-1, zmax=1,
        aspect="auto"
    )
    fig_corr.update_layout(
        paper_bgcolor="#010101", plot_bgcolor="#010101", height=350,
        margin=dict(l=0,r=0,t=20,b=0), font=dict(family="Courier New", color="#888")
    )
    st.plotly_chart(fig_corr, use_container_width=True)

# ==========================================
# SEÇÃO 4 — P&L POR ATIVO (LUCROS E PERDAS)
# ==========================================
st.markdown("---")
st.markdown("#### 💰 STATUS DAS POSIÇÕES (P&L)")

pnl_dados = []
valor_total_carteira = 0
custo_total_carteira = 0

with st.spinner("Atualizando preços ao vivo para cálculo de P&L..."):
    for t in tickers_com_peso:
        pm = ativos_alocados[t]['preco_medio']
        qtd = ativos_alocados[t]['quantidade']
        
        try:
            preco_atual = yf.Ticker(t).fast_info.last_price
        except:
            preco_atual = 0
            
        if pm > 0 and qtd > 0:
            custo = pm * qtd
            valor_atual = preco_atual * qtd
            pnl = valor_atual - custo
            pnl_pct = (pnl / custo) * 100
            
            valor_total_carteira += valor_atual
            custo_total_carteira += custo
            
            pnl_dados.append({
                'Ticker': t,
                'Preço Médio': pm,
                'Preço Atual': preco_atual,
                'Qtd': qtd,
                'Custo Total': custo,
                'Valor Atual': valor_atual,
                'P&L Financeiro': pnl,
                'P&L %': pnl_pct
            })

if pnl_dados:
    df_pnl = pd.DataFrame(pnl_dados)
    
    def formatar_pnl(val):
        if type(val) in [float, int]:
            color = '#00FF00' if val > 0 else ('#FF0000' if val < 0 else '#888888')
            return f'color: {color}; font-weight: bold;'
        return ''

    st.dataframe(
        df_pnl.style.applymap(formatar_pnl, subset=['P&L Financeiro', 'P&L %']).format({
            'Preço Médio': '{:.2f}', 'Preço Atual': '{:.2f}', 'Qtd': '{:.4f}',
            'Custo Total': '{:,.2f}', 'Valor Atual': '{:,.2f}',
            'P&L Financeiro': '{:+,.2f}', 'P&L %': '{:+.2f}%'
        }),
        use_container_width=True, hide_index=True
    )
    
    pnl_total = valor_total_carteira - custo_total_carteira
    pnl_total_pct = (pnl_total / custo_total_carteira) * 100 if custo_total_carteira > 0 else 0
    
    st.markdown(
        f'<div style="background:#111; padding:15px; border-radius:5px; border-left:4px solid {"#00FF00" if pnl_total >=0 else "#FF0000"};">'
        f'<span style="font-family:Courier New; color:#888;">PATRIMÓNIO TOTAL:</span> <span style="font-size:1.5rem; font-weight:bold;">${valor_total_carteira:,.2f}</span> &nbsp;&nbsp;|&nbsp;&nbsp; '
        f'<span style="font-family:Courier New; color:#888;">LUCRO/PREJUÍZO ABERTO:</span> <span style="font-size:1.5rem; font-weight:bold; color:{"#00FF00" if pnl_total >=0 else "#FF0000"};">${pnl_total:+,.2f} ({pnl_total_pct:+.2f}%)</span>'
        f'</div>',
        unsafe_allow_html=True
    )
else:
    st.info("Para ver o P&L, certifique-se de que preencheu o Preço Médio e a Quantidade na tabela de Composição do Portfólio acima.")

# ==========================================
# SEÇÃO 5 — ENVIO DE RELATÓRIO
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)
if st.button("📧 ENVIAR RELATÓRIO DA CARTEIRA POR EMAIL"):
    with st.spinner("Preparando e enviando relatório..."):
        # Montar a lista que a função enviar_relatorio_semanal espera
        dados_envio = []
        scores_db = {h['ticker']: h for h in get_health_scores()}
        
        for t in tickers_com_peso:
            try:
                hist = yf.Ticker(t).history(period="35d")
                preco = hist['Close'].iloc[-1]
                var1d = ((preco / hist['Close'].iloc[-2]) - 1) * 100
                var1m = ((preco / hist['Close'].iloc[0]) - 1) * 100
            except:
                var1d = var1m = 0
                
            dados_envio.append({
                'ticker': t,
                'score': scores_db.get(t, {}).get('score', 50),
                'var_1d': var1d,
                'var_1m': var1m
            })
            
        enviado = enviar_relatorio_semanal(dados_envio)
        if enviado:
            st.success("✅ Relatório de Portfólio enviado para o seu email com sucesso!")
        else:
            st.error("❌ Falha ao enviar o email. Verifique as credenciais no ficheiro secrets.toml.")