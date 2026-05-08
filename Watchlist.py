import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from google import genai
import time
import json
from datetime import datetime, timedelta
import sqlite3

from utils.auth import check_password

if not check_password():
    st.stop()

from utils.style import aplicar_tema
from database.db import (
    init_db, adicionar_ativo, remover_ativo, listar_watchlist, atualizar_notas,
    criar_alerta, listar_alertas, desativar_alerta, marcar_disparado,
    get_cache_ia, salvar_cache_ia, get_connection, popular_watchlist_inicial, 
    get_health_scores, get_pesos
)
from utils.health_engine import calcular_health_score
from utils.email_sender import enviar_alerta_email, enviar_relatorio_semanal

st.set_page_config(page_title="Terminal FinApp | Home", layout="wide", initial_sidebar_state="expanded")

init_db()
popular_watchlist_inicial() 

semana_atual = datetime.now().strftime("%Y-W%W")
cache_relatorio = get_cache_ia("RELATORIO", semana_atual, max_horas=168)

if not cache_relatorio:
    salvar_cache_ia("RELATORIO", semana_atual, "gerado")
    watchlist_report = listar_watchlist()
    pesos = {p['ticker']: p for p in get_pesos()}
    scores = {h['ticker']: h for h in get_health_scores()}

    dados_carteira = []
    if watchlist_report:
        tickers_report = [i['ticker'] for i in watchlist_report]
        try:
            hist_report = yf.download(tickers_report, period="35d", auto_adjust=True, progress=False)['Close']
            if len(tickers_report) == 1:
                hist_report = hist_report.to_frame(name=tickers_report[0])
            hist_report = hist_report.ffill()
            
            for t in tickers_report:
                try:
                    s = hist_report[t].dropna()
                    preco = s.iloc[-1]
                    var1d = ((preco/s.iloc[-2])-1)*100
                    var1m = ((preco/s.iloc[0])-1)*100
                except:
                    preco = var1d = var1m = 0

                dados_carteira.append({
                    'ticker': t,
                    'score': scores.get(t, {}).get('score', 50),
                    'var_1d': var1d,
                    'var_1m': var1m,
                    'peso': pesos.get(t, {}).get('peso', 0),
                })
        except:
            pass

    st.session_state['relatorio_semanal'] = dados_carteira
    st.session_state['relatorio_pronto'] = True

aplicar_tema()

def detectar_mercado(ticker):
    t = ticker.upper()
    if t.endswith('.SA'): return "brasil"
    elif t in ['BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD']: return "criptomoedas"
    elif t in ['GC=F', 'CL=F', 'SI=F', 'HG=F', 'BZ=F', 'CC=F']: return "commodities"
    elif t.endswith(('.DE', '.PA', '.L', '.AS', '.MI')): return "europa"
    elif t.endswith(('.T', '.KS', '.HK')): return "ásia"
    else: return "eua"

MAPA_ALERTAS_UI_DB = {
    'preço acima de': 'preco_acima',
    'preço abaixo de': 'preco_abaixo',
    'variação diária acima de %': 'variacao_acima',
    'p/l abaixo de': 'pl_abaixo',
    'dy acima de %': 'dy_acima'
}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_market_status():
    tickers_map = {
        '^BVSP': 'ibovespa',
        '^GSPC': 's&p 500',
        '^IXIC': 'nasdaq',
        '^FTSE': 'ftse 100',
        'BTC-USD': 'bitcoin',
        'GC=F': 'ouro'
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
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT ticker, tipo, gerado_em FROM cache_analise_ia ORDER BY gerado_em DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

if st.session_state.get('relatorio_pronto'):
    with st.expander("📊 relatório semanal disponível", expanded=True):
        st.write("o seu relatório de performance e saúde da carteira desta semana foi gerado em background pelo sistema.")
        col1, col2, col3 = st.columns([2, 2, 6])
        with col1:
            if st.button("📧 enviar por email", type="primary"):
                dados = st.session_state.get('relatorio_semanal', [])
                if enviar_relatorio_semanal(dados):
                    st.success("✅ relatório enviado com sucesso!")
                    st.session_state['relatorio_pronto'] = False
                else:
                    st.error("falha no envio. verifique as suas configurações no secrets.toml.")
        with col2:
            if st.button("dispensar"):
                st.session_state['relatorio_pronto'] = False
                st.rerun()

st.markdown("### 🌐 panorama global de mercado")
market_data = fetch_market_status()

if market_data:
    cols = st.columns(len(market_data))
    for i, item in enumerate(market_data):
        valor_fmt = f"${item['valor']:,.0f}" if item['nome'] == 'bitcoin' else f"{item['valor']:,.2f}"
        cols[i].metric(item['nome'], valor_fmt, f"{item['var']:+.2f}%")
        
st.markdown("---")

c_links, c_ia = st.columns([1, 1])

with c_links:
    st.markdown("#### ⚡ navegação rápida")
    col_link1, col_link2, col_link3 = st.columns(3)
    with col_link1:
        st.page_link("pages/1_Macro_Global.py", label="macro global", icon="🌍")
        st.page_link("pages/3_Fundamentalista.py", label="fundamentalista", icon="📊")
        st.page_link("pages/4_Analise_Tecnica.py", label="análise técnica", icon="📈")
        st.page_link("pages/8_Comparacao.py", label="comparação", icon="⚖️")
    with col_link2:
        st.page_link("pages/2_Screener_IA.py", label="screener IA", icon="🕵️")
        st.page_link("pages/5_IA_Sentimento.py", label="IA sentimento", icon="🧠")
        st.page_link("pages/6_Backtesting.py", label="backtesting", icon="🔙")
        st.page_link("pages/7_Overlay.py", label="overlay macro", icon="🔭")
    with col_link3:
        st.page_link("pages/11_Portfolio.py", label="portfolio", icon="💼")
        st.page_link("pages/12_Decisoes.py", label="decisões", icon="📝")
        st.page_link("pages/13_Solana.py", label="solana on-chain", icon="⛓️")
        st.page_link("pages/14_Insights.py", label="insights cruzados", icon="⚡")

with c_ia:
    st.markdown("#### 🧠 últimas análises geradas pela IA")
    recent_ai = get_recent_ai()
    if recent_ai:
        for r in recent_ai:
            data_formatada = r['gerado_em'][:16] 
            st.markdown(f"- 🤖 **{r['ticker']}** — *{r['tipo'].capitalize()}* — {data_formatada}")
    else:
        st.info("nenhuma análise de inteligência artificial em cache no momento.")

st.markdown("---")

st.markdown("### 👁️ watchlist pública & radar de alertas")

watchlist = listar_watchlist()

with st.container():
    c_input, c_btn, c_vazio = st.columns([3, 2, 5])
    with c_input:
        novo_ticker = st.text_input("adicionar novo ativo à watchlist:", placeholder="ex: ITUB4.SA, AAPL, BTC-USD, GC=F").strip().upper()
    with c_btn:
        st.markdown("<br>", unsafe_allow_html=True) 
        if st.button("➕ adicionar", use_container_width=True):
            if novo_ticker:
                with st.spinner("buscando dados..."):
                    try:
                        info = yf.Ticker(novo_ticker).info
                        nome = info.get('shortName', novo_ticker)
                        mercado = detectar_mercado(novo_ticker)
                        adicionar_ativo(novo_ticker, nome, mercado)
                        
                        # Tenta calcular o Health Score automaticamente ao adicionar
                        try:
                            calcular_health_score(novo_ticker)
                        except Exception:
                            pass
                            
                        st.success(f"{novo_ticker} adicionado!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception:
                        st.error("ticker não encontrado. verifique o código.")

if watchlist:
    with st.expander("🗑️ edição em lote (remover vários ativos rapidamente)"):
        tickers_na_lista = [item['ticker'] for item in watchlist]
        remover_selecionados = st.multiselect("selecione os ativos que deseja remover:", tickers_na_lista)
        if st.button("remover selecionados", type="primary"):
            for t in remover_selecionados:
                remover_ativo(t)
            st.success("ativos removidos com sucesso!")
            time.sleep(0.5)
            st.rerun()

alertas_db = listar_alertas()

if st.button("🔄 atualizar health scores", type="primary"):
    with st.spinner("calculando scores de saúde de todos os ativos..."):
        for item in watchlist:
            try:
                calcular_health_score(item['ticker'])
            except Exception:
                pass
    st.success("scores atualizados!")
    time.sleep(0.5)
    st.rerun()

live_data = {}
if watchlist:
    # Normaliza o nome do mercado para evitar grupos duplicados (Correção Brasil/B3)
    for item in watchlist:
        if item['mercado'].lower() in ["b3 (brasil)", "brasil"]:
            item['mercado'] = "brasil"

    tickers_ativos = [item['ticker'] for item in watchlist]
    with st.spinner("sincronizando cotações em lote..."):
        try:
            hist = yf.download(tickers_ativos, period="1mo", auto_adjust=True, progress=False)['Close']
            if len(tickers_ativos) == 1:
                hist = hist.to_frame(name=tickers_ativos[0])
            hist = hist.ffill()
            
            for t in tickers_ativos:
                try:
                    s = hist[t].dropna()
                    if len(s) >= 2:
                        preco_atual = float(s.iloc[-1])
                        preco_ontem = float(s.iloc[-2])
                        preco_1m = float(s.iloc[0])
                        var_1d = ((preco_atual / preco_ontem) - 1) * 100
                        var_1m = ((preco_atual / preco_1m) - 1) * 100
                        live_data[t] = {'preco': preco_atual, 'var_1d': var_1d, 'var_1m': var_1m}
                    else:
                        live_data[t] = {'preco': 0, 'var_1d': 0, 'var_1m': 0}
                except:
                    live_data[t] = {'preco': 0, 'var_1d': 0, 'var_1m': 0}
        except Exception:
            pass

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
            elif tipo == 'variacao_acima' and dado.get('var_1d', 0) >= thresh: disparar = True
            
            if disparar:
                marcar_disparado(alerta['id'])
                alertas_disparados_agora.append(alerta)
                st.toast(f"🚨 alerta disparado: {t} ({tipo} {thresh})!")

if alertas_disparados_agora:
    st.error(f"⚠️ **{len(alertas_disparados_agora)} novos alertas disparados!**")
    time.sleep(2) 
    st.rerun() 

health_data = {h['ticker']: h for h in get_health_scores()}

if not watchlist:
    pass # Tratado acima
else:
    mercados_unicos = list(set([item['mercado'] for item in watchlist]))
    
    for mercado in sorted(mercados_unicos):
        st.markdown(f"#### 📌 {mercado.upper()}")
        ativos_mercado = [i for i in watchlist if i['mercado'] == mercado]
        
        cols = st.columns(4)
        for idx, item in enumerate(ativos_mercado):
            t = item['ticker']
            col_idx = idx % 4
            
            # --- Definição dinâmica da Moeda ---
            moeda_display = "R$" if item['mercado'].lower() == "brasil" else "$"
            
            tem_alerta = any(a['ticker'] == t and a['disparado_em'] is not None for a in alertas_db)
            badge = "<span style='background-color:#FF0000; color:white; padding:2px 5px; border-radius:3px; font-size:0.7rem;'>⚠️ alerta</span>" if tem_alerta else ""
            
            dado = live_data.get(t, {'preco': 0, 'var_1d': 0, 'var_1m': 0})
            cor_1d = "#00FF00" if dado['var_1d'] >= 0 else "#FF0000"
            sinal_1d = "+" if dado['var_1d'] >= 0 else ""
            cor_1m = "#00FF00" if dado['var_1m'] >= 0 else "#FF0000"
            sinal_1m = "+" if dado['var_1m'] >= 0 else ""

            score_info = health_data.get(t, {})
            score = score_info.get('score', None)
            
            html_score = ""
            if score is not None:
                cor_score = "#00FF00" if score >= 65 else ("#FF9900" if score >= 40 else "#FF0000")
                label_score = "saudável" if score >= 65 else ("atenção" if score >= 40 else "⚠️ venda")
                barra = "█" * int(score/10) + "░" * (10 - int(score/10))
                
                html_score = f'''
                <div style="margin-top:8px; border-top:1px solid #222; padding-top:6px;">
                    <div style="font-size:0.7rem; color:#888; font-family:Courier New;">health score</div>
                    <div style="color:{cor_score}; font-family:Courier New; font-size:0.85rem;">{barra} {score:.0f}/100</div>
                    <div style="color:{cor_score}; font-size:0.7rem; font-family:Courier New;">{label_score}</div>
                </div>
                '''
            else:
                html_score = '''
                <div style="margin-top:8px; border-top:1px solid #222; padding-top:6px;">
                    <div style="font-size:0.7rem; color:#555; font-family:Courier New;">health score</div>
                    <div style="color:#555; font-size:0.8rem; font-style:italic;">Não calculado.</div>
                </div>
                '''
            
            with cols[col_idx]:
                html_card = (
                    f'<div style="background-color:#111111; padding:15px; border-radius:8px; border-top:3px solid #FF9900; margin-bottom:10px;">'
                    f'<div style="display:flex; justify-content:space-between;">'
                    f'<h3 style="margin:0; padding:0; color:#FF9900;">{t}</h3>{badge}</div>'
                    f'<div style="font-size:0.8rem; color:#888888; margin-bottom:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{item["nome"]}</div>'
                    f'<div style="font-size:1.8rem; font-weight:bold; color:#FFFFFF; font-family:\'Courier New\';">{moeda_display} {dado["preco"]:.2f}</div>'
                    f'<div style="font-size:0.9rem; margin-top:5px;">'
                    f'1D: <span style="color:{cor_1d}; font-weight:bold;">{sinal_1d}{dado["var_1d"]:.2f}%</span> | '
                    f'1M: <span style="color:{cor_1m}; font-weight:bold;">{sinal_1m}{dado["var_1m"]:.2f}%</span></div>'
                    f'{html_score}</div>'
                )
                st.markdown(html_card, unsafe_allow_html=True)
                
                if st.button("✕ remover", key=f"rm_{t}", use_container_width=True):
                    remover_ativo(t)
                    st.rerun()

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
                    st.toast(f"📧 email de alerta de venda enviado para {h['ticker']}!")

if alertas_venda:
    st.markdown("<br>", unsafe_allow_html=True)
    st.error("⚠️ **atenção! ativos com health score crítico (abaixo de 40):**")
    for t, s, al in alertas_venda:
        st.warning(f"**{t}** (score: {s:.0f})")
        for a in al:
            st.write(f"- {a}")

st.markdown("---")
st.markdown("#### ⚙️ gerenciamento e notas")

for item in watchlist:
    t = item['ticker']
    with st.expander(f"configurações e notas: {t}"):
        tab_alertas, tab_notas = st.tabs(["radar de alertas", "minhas notas"])
        
        with tab_alertas:
            c_form, c_lista = st.columns([1, 1])
            with c_form:
                with st.form(f"form_alerta_{t}", clear_on_submit=True):
                    st.markdown(f"**criar novo gatilho para {t}**")
                    tipo_selecionado = st.selectbox("condição do alerta:", list(MAPA_ALERTAS_UI_DB.keys()))
                    threshold = st.number_input("valor alvo:", format="%.2f")
                    if st.form_submit_button("criar alerta", type="primary"):
                        tipo_db = MAPA_ALERTAS_UI_DB[tipo_selecionado]
                        criar_alerta(t, tipo_db, threshold)
                        st.success("alerta armado com sucesso!")
                        time.sleep(1)
                        st.rerun()
                        
            with c_lista:
                alertas_ticker = [a for a in alertas_db if a['ticker'] == t]
                if alertas_ticker:
                    for a in alertas_ticker:
                        status = "🟢 ativo" if a['ativo'] == 1 and not a['disparado_em'] else "🔴 disparado/desativado"
                        st.markdown(f"**{a['tipo']} {a['threshold']}** | {status}")
                        if a['ativo'] == 1:
                            if st.button("desativar", key=f"des_{a['id']}"):
                                desativar_alerta(a['id'])
                                st.rerun()
                        st.markdown("---")
                else:
                    st.info("nenhum alerta configurado para este ativo.")
                    
        with tab_notas:
            with st.form(f"form_nota_{t}"):
                nota_atual = item['notas'] if item['notas'] else ""
                nova_nota = st.text_area("anotações da tese de investimento:", value=nota_atual, height=150)
                if st.form_submit_button("salvar nota", type="primary"):
                    atualizar_notas(t, nova_nota)
                    st.success("tese atualizada.")

st.markdown("---")
if st.button("🤖 gerar resumo da carteira", type="primary"):
    cache_resumo = get_cache_ia('PORTFOLIO', 'watchlist_resumo', max_horas=6)
    if cache_resumo:
        st.success("⚡ resumo recuperado do cache (gerado nas últimas 6h).")
        st.markdown(cache_resumo)
    else:
        with st.spinner("analisando o comportamento do seu portfólio no mercado..."):
            try:
                dados_texto = ""
                for t, d in live_data.items():
                    dados_texto += f"- {t}: preço {d['preco']:.2f} | var diária {d['var_1d']:.2f}% | var mensal {d['var_1m']:.2f}%\n"
                
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                prompt = f"""
                aja como gestor de portfólio de um hedge fund. 
                estes são os ativos monitorados na watchlist e suas variações:
                
                {dados_texto}
                
                faça uma análise rápida e pragmática desta carteira.
                escreva 3 bullet points apontando os riscos atuais com base nestas quedas ou concentrações.
                escreva 3 bullet points apontando oportunidades latentes baseadas nesses movimentos.
                
                responda em português, formatação markdown, direto ao ponto.
                """
                resposta = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                salvar_cache_ia('PORTFOLIO', 'watchlist_resumo', resposta.text)
                st.success("✅ visão do gestor gerada e em cache.")
                st.markdown(resposta.text)
            except Exception as e:
                st.error(f"erro na geração da IA: {e}")