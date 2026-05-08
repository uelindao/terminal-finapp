import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from google import genai
import time
import json
from datetime import datetime, timedelta

# Importa o Design System, Banco de Dados e Email
from utils.style import aplicar_tema
from database.db import (
    init_db, adicionar_ativo, remover_ativo, listar_watchlist, atualizar_notas,
    criar_alerta, listar_alertas, desativar_alerta, marcar_disparado,
    get_cache_ia, salvar_cache_ia, get_connection, popular_watchlist_inicial, 
    get_health_scores, get_pesos
)
from utils.health_engine import calcular_health_score
from utils.email_sender import enviar_alerta_email, enviar_relatorio_semanal

# --- Configuração da Página ---
st.set_page_config(page_title="Terminal FinApp | Home", layout="wide", initial_sidebar_state="expanded")

# --- Inicializa o Banco de Dados Globalmente ---
init_db()
popular_watchlist_inicial() 

# ==========================================
# GERAÇÃO DO RELATÓRIO SEMANAL (Briefing 5)
# ==========================================
# Chave do relatório: semana atual (ex: "2026-W19")
semana_atual = datetime.now().strftime("%Y-W%W")
cache_relatorio = get_cache_ia("RELATORIO", semana_atual, max_horas=168)  # 7 dias

if not cache_relatorio:
    # Marca como gerado para não repetir na mesma semana
    salvar_cache_ia("RELATORIO", semana_atual, "gerado")

    # Coleta dados da watchlist em background
    watchlist_report = listar_watchlist()
    pesos     = {p['ticker']: p for p in get_pesos()}
    scores    = {h['ticker']: h for h in get_health_scores()}

    dados_carteira = []
    for item in watchlist_report:
        t = item['ticker']
        try:
            hist = yf.Ticker(t).history(period="35d")
            preco = hist['Close'].iloc[-1]
            var1d = ((preco/hist['Close'].iloc[-2])-1)*100
            var1m = ((preco/hist['Close'].iloc[0])-1)*100
        except:
            preco = var1d = var1m = 0

        dados_carteira.append({
            'ticker': t,
            'score': scores.get(t, {}).get('score', 50),
            'var_1d': var1d,
            'var_1m': var1m,
            'peso': pesos.get(t, {}).get('peso', 0),
        })

    st.session_state['relatorio_semanal'] = dados_carteira
    st.session_state['relatorio_pronto'] = True

# --- Injeta o CSS Centralizado ---
aplicar_tema()

# ==========================================
# FUNÇÕES DE APOIO GERAIS E DASHBOARD
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

@st.cache_data(ttl=300, show_spinner=False)
def fetch_market_status():
    tickers_map = {
        '^BVSP': 'IBOVESPA',
        '^GSPC': 'S&P 500',
        '^IXIC': 'NASDAQ',
        '^FTSE': 'FTSE 100',
        'BTC-USD': 'BITCOIN',
        'GC=F': 'OURO'
    }
    tickers = list(tickers_map.keys())
    data = []
    try:
        hist = yf.download(tickers, period="5d", auto_adjust=True, progress=False)
        df_close = hist['Close'] if isinstance(hist.columns, pd.MultiIndex) else hist
        df_close = df_close.ffill() 
        
        for t in tickers:
            nome = tickers_map[t]
            try:
                s = df_close[t].dropna()
                if len(s) >= 2:
                    curr = s.iloc[-1]
                    prev = s.iloc[-2]
                    var = ((curr / prev) - 1) * 100
                    data.append({'nome': nome, 'valor': curr, 'var': var})
                elif len(s) == 1:
                    data.append({'nome': nome, 'valor': s.iloc[-1], 'var': 0.0})
                else:
                    data.append({'nome': nome, 'valor': 0.0, 'var': 0.0})
            except Exception:
                data.append({'nome': nome, 'valor': 0.0, 'var': 0.0})
    except Exception:
        for t in tickers:
            data.append({'nome': tickers_map[t], 'valor': 0.0, 'var': 0.0})
    return data

def get_recent_ai():
    try:
        import sqlite3
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT ticker, tipo, gerado_em FROM cache_analise_ia ORDER BY gerado_em DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

# ==========================================
# BANNER RELATÓRIO SEMANAL
# ==========================================
if st.session_state.get('relatorio_pronto'):
    with st.expander("📊 RELATÓRIO SEMANAL DISPONÍVEL", expanded=True):
        st.write("O seu relatório de performance e saúde da carteira desta semana foi gerado em background pelo sistema.")
        col1, col2, col3 = st.columns([2, 2, 6])
        with col1:
            if st.button("📧 ENVIAR POR EMAIL", type="primary"):
                dados = st.session_state.get('relatorio_semanal', [])
                if enviar_relatorio_semanal(dados):
                    st.success("✅ Relatório enviado com sucesso para o seu email!")
                    # Limpa o state para não mostrar o botão de novo caso feche a aba
                    st.session_state['relatorio_pronto'] = False
                else:
                    st.error("Falha no envio. Verifique as suas configurações no secrets.toml.")
        with col2:
            if st.button("DISPENSAR"):
                st.session_state['relatorio_pronto'] = False
                st.rerun()

# ==========================================
# HEADER 1: DASHBOARD DE MERCADO
# ==========================================
st.markdown("### 🌐 PANORAMA GLOBAL DE MERCADO")
market_data = fetch_market_status()

if market_data:
    cols = st.columns(len(market_data))
    for i, item in enumerate(market_data):
        if item['nome'] == 'BITCOIN':
            valor_fmt = f"${item['valor']:,.0f}"
        else:
            valor_fmt = f"{item['valor']:,.2f}"
            
        cols[i].metric(item['nome'], valor_fmt, f"{item['var']:+.2f}%")
        
st.markdown("---")

# ==========================================
# HEADER 2: ACESSO RÁPIDO & HISTÓRICO DE IA
# ==========================================
c_links, c_ia = st.columns([1, 1])

with c_links:
    st.markdown("#### ⚡ NAVEGAÇÃO RÁPIDA")
    col_link1, col_link2 = st.columns(2)
    with col_link1:
        st.page_link("pages/1_Macro_Global.py", label="Macro Global", icon="🌍")
        st.page_link("pages/3_Fundamentalista.py", label="Fundamentalista", icon="📊")
        st.page_link("pages/4_Analise_Tecnica.py", label="Análise Técnica", icon="📈")
        st.page_link("pages/8_Comparacao.py", label="Comparação", icon="⚖️")
    with col_link2:
        st.page_link("pages/2_Screener_IA.py", label="Screener IA", icon="🕵️")
        st.page_link("pages/5_IA_Sentimento.py", label="IA Sentimento", icon="🧠")
        st.page_link("pages/6_Backtesting.py", label="Backtesting", icon="🔙")
        st.page_link("pages/7_Overlay.py", label="Overlay Macro", icon="🔭")

with c_ia:
    st.markdown("#### 🧠 ÚLTIMAS ANÁLISES GERADAS PELA IA")
    recent_ai = get_recent_ai()
    if recent_ai:
        for r in recent_ai:
            data_formatada = r['gerado_em'][:16] 
            st.markdown(f"- 🤖 **{r['ticker']}** — *{r['tipo'].capitalize()}* — {data_formatada}")
    else:
        st.info("Nenhuma análise de inteligência artificial em cache no momento.")

st.markdown("---")

# ==========================================
# CORE: WATCHLIST & RADAR DE ALERTAS
# ==========================================
st.markdown("### 👁️ WATCHLIST PÚBLICA & RADAR DE ALERTAS")

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

# -- Botão de Atualizar Health Scores --
if st.button("🔄 ATUALIZAR HEALTH SCORES", type="primary"):
    with st.spinner("Calculando scores de saúde de todos os ativos (este processo pode demorar um pouco)..."):
        for item in watchlist:
            try:
                calcular_health_score(item['ticker'])
            except Exception as e:
                pass
    st.success("Scores atualizados com sucesso!")
    time.sleep(1)
    st.rerun()

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
# VERIFICADOR DE ALERTAS
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
# GRID DE CARDS COM HEALTH SCORES
# ==========================================
health_data = {h['ticker']: h for h in get_health_scores()}

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

        # --- Injeção do Health Score ---
        score_info = health_data.get(t, {})
        score = score_info.get('score', None)
        
        if score is not None:
            cor_score = "#00FF00" if score >= 65 else ("#FF9900" if score >= 40 else "#FF0000")
            label_score = "SAUDÁVEL" if score >= 65 else ("ATENÇÃO" if score >= 40 else "⚠️ VENDA")
            barra = "█" * int(score/10) + "░" * (10 - int(score/10))
            
            html_score = f'''
            <div style="margin-top:8px; border-top:1px solid #222; padding-top:6px;">
                <div style="font-size:0.7rem; color:#888; font-family:Courier New;">
                    HEALTH SCORE
                </div>
                <div style="color:{cor_score}; font-family:Courier New; font-size:0.85rem;">
                    {barra} {score:.0f}/100
                </div>
                <div style="color:{cor_score}; font-size:0.7rem; font-family:Courier New;">
                    {label_score}
                </div>
            </div>
            '''
        else:
            html_score = ""
        
        with cols[col_idx]:
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
                f'</div>'
                f'{html_score}'
                f'</div>'
            )
            st.markdown(html_card, unsafe_allow_html=True)
            
            if st.button("✕ Remover", key=f"rm_{t}", use_container_width=True):
                remover_ativo(t)
                st.rerun()

# ==========================================
# AVISOS DE VENDA E ATENÇÃO COM DISPARO DE EMAIL
# ==========================================
alertas_venda = []
for h in health_data.values():
    score = h.get('score', 100)
    if score < 40:
        al = json.loads(h.get('alertas_venda', '[]'))
        if al:
            alertas_venda.append((h['ticker'], score, al))
            
            flag_enviado = get_cache_ia(h['ticker'], 'email_alerta_enviado', max_horas=20)
            if not flag_enviado:
                enviado = enviar_alerta_email(h['ticker'], score, al)
                if enviado:
                    salvar_cache_ia(h['ticker'], 'email_alerta_enviado', 'sim')
                    st.toast(f"📧 Email de alerta de venda enviado para {h['ticker']}!")

if alertas_venda:
    st.markdown("<br>", unsafe_allow_html=True)
    st.error("⚠️ **ATENÇÃO! ATIVOS COM HEALTH SCORE CRÍTICO (ABAIXO DE 40):**")
    for t, s, al in alertas_venda:
        st.warning(f"**{t}** (Score: {s:.0f})")
        for a in al:
            st.write(f"- {a}")

# ==========================================
# GERENCIADOR E NOTAS (Expanders)
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
# RESUMO VIA IA
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