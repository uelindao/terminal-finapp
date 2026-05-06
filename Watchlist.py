import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from google import genai
import time

# Importa o Design System e o Banco de Dados
from utils.style import aplicar_tema
from database.db import (
    init_db, adicionar_ativo, remover_ativo, listar_watchlist, atualizar_notas,
    criar_alerta, listar_alertas, desativar_alerta, marcar_disparado,
    get_cache_ia, salvar_cache_ia
)

# --- Configuração da Página (DEVE SER O PRIMEIRO COMANDO) ---
st.set_page_config(page_title="Terminal FinApp | Watchlist", layout="wide", initial_sidebar_state="expanded")

# --- Inicializa o Banco de Dados ---
init_db()

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 👁️ WATCHLIST & RADAR DE ALERTAS")

# ==========================================
# FUNÇÕES DE APOIO
# ==========================================
def detectar_mercado(ticker):
    t = ticker.upper()
    if t.endswith('.SA'): return "B3 (Brasil)"
    elif t.endswith(('.DE', '.PA', '.L', '.AS', '.MI')): return "Europa"
    elif t.endswith(('.T', '.KS', '.HK')): return "Ásia"
    else: return "EUA (Nyse/Nasdaq)"

MAPA_ALERTAS_UI_DB = {
    'Preço acima de': 'preco_acima',
    'Preço abaixo de': 'preco_abaixo',
    'Variação diária acima de %': 'variacao_acima',
    'P/L abaixo de': 'pl_abaixo',
    'DY acima de %': 'dy_acima'
}

# ==========================================
# SEÇÃO 1: ADICIONAR ATIVO
# ==========================================
with st.container():
    c_input, c_btn, c_vazio = st.columns([3, 2, 5])
    with c_input:
        novo_ticker = st.text_input("Adicionar novo ativo à Watchlist:", placeholder="Ex: ITUB4.SA, AAPL, MSFT").strip().upper()
    with c_btn:
        st.markdown("<br>", unsafe_allow_html=True) 
        if st.button("➕ ADICIONAR", use_container_width=True):
            if novo_ticker:
                with st.spinner("Buscando dados na bolsa..."):
                    try:
                        info = yf.Ticker(novo_ticker).info
                        nome = info.get('shortName', novo_ticker)
                        mercado = detectar_mercado(novo_ticker)
                        adicionar_ativo(novo_ticker, nome, mercado)
                        st.success(f"{novo_ticker} adicionado!")
                        time.sleep(1)
                        st.rerun()
                    except Exception:
                        st.error("Ticker não encontrado. Verifique o código.")

# ==========================================
# CARREGAMENTO DOS DADOS DA WATCHLIST
# ==========================================
watchlist = listar_watchlist()
alertas_db = listar_alertas()

live_data = {}
if watchlist:
    with st.spinner("Sincronizando cotações e calculando variações..."):
        for item in watchlist:
            t = item['ticker']
            try:
                acao = yf.Ticker(t)
                hist = acao.history(period="1mo")
                info = acao.info
                
                if not hist.empty:
                    preco_atual = hist['Close'].iloc[-1]
                    preco_ontem = hist['Close'].iloc[-2] if len(hist) > 1 else preco_atual
                    preco_1m = hist['Close'].iloc[0]
                    
                    var_1d = ((preco_atual / preco_ontem) - 1) * 100
                    var_1m = ((preco_atual / preco_1m) - 1) * 100
                    
                    pl = info.get('trailingPE', info.get('forwardPE', 0))
                    dy = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
                    
                    live_data[t] = {
                        'preco': preco_atual,
                        'var_1d': var_1d,
                        'var_1m': var_1m,
                        'pl': pl if pl is not None else 0,
                        'dy': dy if dy is not None else 0
                    }
            except:
                live_data[t] = {'preco': 0, 'var_1d': 0, 'var_1m': 0, 'pl': 0, 'dy': 0}

# ==========================================
# SEÇÃO 3: VERIFICADOR DE ALERTAS
# ==========================================
alertas_disparados_agora = []

for alerta in alertas_db:
    if alerta['ativo'] == 1 and not alerta['disparado_em']: 
        t = alerta['ticker']
        if t in live_data:
            dado = live_data[t]
            tipo = alerta['tipo']
            thresh = alerta['threshold']
            disparar = False
            
            if tipo == 'preco_acima' and dado['preco'] >= thresh: disparar = True
            elif tipo == 'preco_abaixo' and dado['preco'] <= thresh and dado['preco'] > 0: disparar = True
            elif tipo == 'variacao_acima' and dado['var_1d'] >= thresh: disparar = True
            elif tipo == 'pl_abaixo' and dado['pl'] <= thresh and dado['pl'] > 0: disparar = True
            elif tipo == 'dy_acima' and dado['dy'] >= thresh: disparar = True
            
            if disparar:
                marcar_disparado(alerta['id'])
                alertas_disparados_agora.append(alerta)
                st.toast(f"🚨 ALERTA DISPARADO: {t} ({tipo} {thresh})!")

if alertas_disparados_agora:
    st.error(f"⚠️ **{len(alertas_disparados_agora)} NOVOS ALERTAS DISPARADOS!** Verifique as métricas de seus ativos.")
    time.sleep(2) 
    st.rerun() 

# ==========================================
# SEÇÃO 2: GRID DE CARDS
# ==========================================
st.markdown("---")
if not watchlist:
    st.info("Sua watchlist está vazia. Adicione um ativo acima.")
else:
    cols = st.columns(4)
    
    for idx, item in enumerate(watchlist):
        t = item['ticker']
        col_idx = idx % 4
        
        tem_alerta_disparado = any(a['ticker'] == t and a['disparado_em'] is not None for a in alertas_db)
        badge_html = "<span style='background-color:#FF0000; color:white; padding:2px 5px; border-radius:3px; font-size:0.7rem;'>⚠️ ALERTA</span>" if tem_alerta_disparado else ""
        
        dado = live_data.get(t, {'preco': 0, 'var_1d': 0, 'var_1m': 0})
        cor_1d = "#00FF00" if dado['var_1d'] >= 0 else "#FF0000"
        sinal_1d = "+" if dado['var_1d'] >= 0 else ""
        
        cor_1m = "#00FF00" if dado['var_1m'] >= 0 else "#FF0000"
        sinal_1m = "+" if dado['var_1m'] >= 0 else ""
        
        with cols[col_idx]:
            # HTML blindado em bloco único contra o bug de espaçamento do Markdown
            html_card = (
                f'<div style="background-color:#111111; padding:15px; border-radius:8px; border-top:3px solid #FF9900; margin-bottom:10px;">'
                f'<div style="display:flex; justify-content:space-between;">'
                f'<h3 style="margin:0; padding:0; color:#FF9900;">{t}</h3>{badge_html}'
                f'</div>'
                f'<div style="font-size:0.8rem; color:#888888; margin-bottom:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{item["nome"]}</div>'
                f'<div style="font-size:1.8rem; font-weight:bold; color:#FFFFFF; font-family:\'Courier New\';">R$ {dado["preco"]:.2f}</div>'
                f'<div style="font-size:0.9rem; margin-top:5px;">'
                f'1D: <span style="color:{cor_1d}; font-weight:bold;">{sinal_1d}{dado["var_1d"]:.2f}%</span> | '
                f'1M: <span style="color:{cor_1m}; font-weight:bold;">{sinal_1m}{dado["var_1m"]:.2f}%</span>'
                f'</div></div>'
            )
            st.markdown(html_card, unsafe_allow_html=True)
            
            if st.button("✕ Remover", key=f"rm_{t}", use_container_width=True):
                remover_ativo(t)
                st.rerun()

# ==========================================
# SEÇÕES 4 & 5: GERENCIADOR E NOTAS (Expanders)
# ==========================================
st.markdown("---")
st.markdown("#### ⚙️ GERENCIAMENTO E NOTAS")

for item in watchlist:
    t = item['ticker']
    with st.expander(f"Configurações e Notas: {t}"):
        tab_alertas, tab_notas = st.tabs(["Radar de Alertas", "Minhas Notas"])
        
        with tab_alertas:
            c_form, c_lista = st.columns([1, 1])
            with c_form:
                with st.form(f"form_alerta_{t}", clear_on_submit=True):
                    st.markdown(f"**Criar novo gatilho para {t}**")
                    tipo_selecionado = st.selectbox("Condição do Alerta:", list(MAPA_ALERTAS_UI_DB.keys()))
                    threshold = st.number_input("Valor Alvo (R$ ou %):", format="%.2f")
                    if st.form_submit_button("CRIAR ALERTA", type="primary"):
                        tipo_db = MAPA_ALERTAS_UI_DB[tipo_selecionado]
                        criar_alerta(t, tipo_db, threshold)
                        st.success("Alerta armado com sucesso!")
                        time.sleep(1)
                        st.rerun()
                        
            with c_lista:
                alertas_ticker = [a for a in alertas_db if a['ticker'] == t]
                if alertas_ticker:
                    for a in alertas_ticker:
                        status = "🟢 ATIVO" if a['ativo'] == 1 and not a['disparado_em'] else "🔴 DISPARADO/DESATIVADO"
                        st.markdown(f"**{a['tipo']} {a['threshold']}** | {status}")
                        if a['ativo'] == 1:
                            if st.button("Desativar", key=f"des_{a['id']}"):
                                desativar_alerta(a['id'])
                                st.rerun()
                        st.markdown("---")
                else:
                    st.info("Nenhum alerta configurado para este ativo.")
                    
        with tab_notas:
            with st.form(f"form_nota_{t}"):
                nota_atual = item['notas'] if item['notas'] else ""
                nova_nota = st.text_area("Anotações da Tese de Investimento:", value=nota_atual, height=150)
                if st.form_submit_button("SALVAR NOTA", type="primary"):
                    atualizar_notas(t, nova_nota)
                    st.success("Tese atualizada.")

# ==========================================
# SEÇÃO 6: RESUMO VIA IA
# ==========================================
st.markdown("---")
if st.button("🤖 GERAR RESUMO DA CARTEIRA", type="primary"):
    
    cache_resumo = get_cache_ia('PORTFOLIO', 'watchlist_resumo', max_horas=6)
    
    if cache_resumo:
        st.success("⚡ Resumo recuperado do Cache (Gerado nas últimas 6h).")
        st.markdown(cache_resumo)
    else:
        with st.spinner("Analisando o comportamento do seu portfólio no mercado..."):
            try:
                dados_texto = ""
                for t, d in live_data.items():
                    dados_texto += f"- {t}: Preço R${d['preco']:.2f} | Var Diária {d['var_1d']:.2f}% | Var Mensal {d['var_1m']:.2f}%\n"
                
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                
                prompt = f"""
                Aja como Gestor de Portfólio de um Hedge Fund. 
                Estes são os ativos monitorados na Watchlist e suas variações:
                
                {dados_texto}
                
                Faça uma análise rápida e pragmática desta carteira.
                Escreva 3 bullet points apontando os RISCOS atuais com base nestas quedas ou concentrações.
                Escreva 3 bullet points apontando OPORTUNIDADES latentes baseadas nesses movimentos.
                
                Responda em português, formatação markdown, direto ao ponto.
                """
                
                resposta = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                
                salvar_cache_ia('PORTFOLIO', 'watchlist_resumo', resposta.text)
                st.success("✅ Visão do Gestor gerada e em cache.")
                st.markdown(resposta.text)
                
            except Exception as e:
                st.error(f"Erro na geração da IA: {e}")