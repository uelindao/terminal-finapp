import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
from google import genai
import datetime
import time
from fredapi import Fred
from bcb import sgs
import logging

# ── silenciar alertas vermelhos do yahoo finance no terminal ──
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from database.db import (
    listar_watchlist, get_health_scores, adicionar_ativo, 
    get_connection, listar_watchlists, criar_watchlist, get_watchlist_padrao
)
from utils.tickers import (
    SCREENER_B3, SCREENER_US, XSTOCKS_INDICES, 
    BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, mapear_ticker_base
)
from utils.health_engine import calcular_health_score
from utils.components import page_header, section_title, status_card, empty_state, inject_keyboard_shortcuts
from utils.charts import base_layout

# 1. configuração da página
st.set_page_config(page_title="terminal finapp | discovery", layout="wide", page_icon="🎯")

# 2. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()

page_header("🎯 discovery — descoberta de oportunidades", "encontre assimetrias de mercado através de filtros quantitativos e inteligência artificial.")
st.markdown("---")

# 4. motor de tradução de setores (sem fazer novos pedidos à api)
def traduzir_setor(setor_raw: str) -> str:
    mapa_setores = {
        'Energy': '⛽ energia', 'Financial Services': '🏦 financeiro',
        'Technology': '💻 tecnologia', 'Healthcare': '🏥 saúde',
        'Consumer Cyclical': '🛒 consumo cíclico', 'Consumer Defensive': '🛒 consumo def.',
        'Industrials': '🏭 indústria', 'Basic Materials': '⛏️ materiais',
        'Real Estate': '🏢 imobiliário', 'Utilities': '⚡ utilities',
        'Communication Services': '📡 telecom', 'Financeiro': '🏦 financeiro',
    }
    return mapa_setores.get(setor_raw, setor_raw.lower() if setor_raw else '—')

# 5. modais (popups) nativos
@st.dialog("📊 detalhes do ativo", width="large")
def modal_ativo(ticker: str):
    """modal com múltiplos e gráfico de preço ao clicar num ativo."""
    t_base = mapear_ticker_base(ticker)
    
    with st.spinner(f"a carregar dados de {ticker.lower()}..."):
        try:
            acao = yf.Ticker(t_base)
            hist = acao.history(period="6mo")
            preco = acao.fast_info.last_price

            # motor híbrido de captura de fundamentos
            if t_base.endswith('.SA'):
                from utils.scrapers import buscar_dados_b3
                f_dados = buscar_dados_b3(t_base)
                nome = f_dados['nome'] if f_dados['nome'] != '—' else ticker
                setor = f_dados['setor']
                pl = f_dados['p/l']
                pvp = f_dados['p/vp']
                roe = f_dados['roe%']
                dy = f_dados['dy%']
                ev_ebitda = f_dados['ev/ebitda']
                margem = f_dados['margem%']
                beta = None
            else:
                info = acao.info
                nome = info.get('shortName', ticker)
                setor = traduzir_setor(info.get('sector', '—'))
                pl = info.get('trailingPE', None)
                pvp = info.get('priceToBook', None)
                roe_r = info.get('returnOnEquity', None)
                roe = roe_r * 100 if roe_r else None
                dy_r = info.get('dividendYield', None)
                dy = dy_r * 100 if dy_r else None
                ev_ebitda = info.get('enterpriseToEbitda', None)
                margem_r = info.get('profitMargins', None)
                margem = margem_r * 100 if margem_r else None
                beta = info.get('beta', None)

            moeda = "r$" if t_base.endswith('.SA') else "$"

            st.markdown(
                f'<div style="font-family:Courier New;">'
                f'<span style="color:#FF9900; font-size:1.3rem; font-weight:bold;">{ticker.lower()}</span>'
                f'<span style="color:#555; margin-left:10px;">{nome.lower()}</span><br>'
                f'<span style="color:#333; font-size:0.75rem;">{setor.lower()}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.markdown(
                f'<div style="font-size:1.6rem; font-weight:bold; color:#FFF; font-family:Courier New;">'
                f'{moeda} {preco:,.2f}</div>',
                unsafe_allow_html=True
            )
            st.markdown("---")

            def fmt(v, suf=""): return f"{v:.2f}{suf}" if v is not None else "n/d"

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("p/l", fmt(pl))
            c2.metric("p/vp", fmt(pvp))
            c3.metric("roe", fmt(roe, "%"))
            c4.metric("dy", fmt(dy, "%"))

            c5, c6, c7, c8 = st.columns(4)
            c5.metric("ev/ebitda", fmt(ev_ebitda))
            c6.metric("margem líq.", fmt(margem, "%"))
            c7.metric("beta", fmt(beta))
            c8.metric("setor", setor.lower()[:12] if setor != '—' else "—")

            if not hist.empty:
                if hist.index.tz is not None: hist.index = hist.index.tz_localize(None)
                fig = go.Figure(go.Scatter(
                    x=hist.index, y=hist['Close'], fill='tozeroy', fillcolor='rgba(255,153,0,0.06)',
                    line=dict(color='#FF9900', width=1.5), hovertemplate="%{x|%d/%m}<br><b>%{y:.2f}</b><extra></extra>"
                ))
                fig.update_layout(
                    paper_bgcolor='#0d0d0d', plot_bgcolor='#0d0d0d', height=200, margin=dict(l=0,r=0,t=10,b=0),
                    showlegend=False, xaxis=dict(showgrid=True, gridcolor='#1e1e1e', tickfont=dict(size=9)),
                    yaxis=dict(showgrid=True, gridcolor='#1e1e1e', tickfont=dict(size=9))
                )
                st.plotly_chart(fig, use_container_width=True)

            col_a, col_b, col_c = st.columns(3)
            watchlists_disp = listar_watchlists()
            opcoes_wl_modal = {f"{wl['icone']} {wl['nome']}": wl['id'] for wl in watchlists_disp}

            with col_a:
                dest_wl = st.selectbox("adicionar à:", list(opcoes_wl_modal.keys()), key=f"wl_modal_{ticker}")
            with col_b:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("➕ watchlist", key=f"add_wl_modal_{ticker}", use_container_width=True, type="primary"):
                    wl_dest_id = opcoes_wl_modal[dest_wl]
                    mercado_t = "brasil" if t_base.endswith('.SA') else "eua"
                    adicionar_ativo(ticker, nome, mercado_t, watchlist_id=wl_dest_id)
                    st.success(f"✅ {ticker.lower()} adicionado!")
            with col_c:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("📊 abrir no research", key=f"research_{ticker}", use_container_width=True):
                    st.session_state['research_ticker_externo'] = ticker
                    st.switch_page("pages/1_Research.py")

        except Exception as e:
            st.error(f"erro ao carregar dados da ação. detalhe: {e}")

@st.dialog("➕ salvar na watchlist")
def modal_salvar_screener(ticker: str, nome: str, mercado: str):
    """modal de seleção de destino ao guardar um ativo do screener."""
    st.markdown(f"**ativo:** {ticker.lower()} - {nome.lower()}")
    
    acao_wl = st.radio("destino:", ["watchlist existente", "criar nova watchlist"], horizontal=True, key=f"radio_dest_{ticker}")
    
    watchlists_disp = listar_watchlists()
    dest_id = None
    
    if acao_wl == "watchlist existente":
        opcoes_dest = {f"{wl['icone']} {wl['nome']}": wl['id'] for wl in watchlists_disp}
        sel_dest = st.selectbox("selecione a watchlist:", list(opcoes_dest.keys()), key=f"sel_exist_{ticker}")
        dest_id = opcoes_dest[sel_dest]
    else:
        nome_nova_wl = st.text_input("nome da nova watchlist:", placeholder="ex: radar de dividendos", key=f"input_nova_{ticker}")
    
    if st.button("💾 confirmar", type="primary", use_container_width=True, key=f"btn_conf_{ticker}"):
        if acao_wl == "criar nova watchlist":
            if nome_nova_wl.strip():
                dest_id = criar_watchlist(nome_nova_wl.strip(), icone="🎯", cor="#00C853")
            else:
                st.warning("digite um nome para a nova watchlist.")
                return
        
        adicionar_ativo(ticker, nome, mercado, watchlist_id=dest_id)
        st.success(f"✅ {ticker.lower()} salvo com sucesso!")
        time.sleep(1)
        st.rerun()

# 6. interface de separadores (tabs)
tab_setup, tab_screener, tab_comps = st.tabs([
    "🎯 setup ideal",
    "🕵️ screener quantitativo",
    "⚖️ comparação de múltiplos"
])

# ==========================================
# tab 1 — setup ideal
# ==========================================
with tab_setup:
    st.write("ativos que combinam fundamentos sólidos com desconto técnico.")

    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
    with c1:
        watchlists_disp = listar_watchlists()
        tickers_watchlist = [i['ticker'] for i in listar_watchlist()]
        
        if len(watchlists_disp) > 1:
            opcoes_universo = (
                ["universo completo", "watchlist + screener br"] +
                [f"{wl['icone']} {wl['nome']}" for wl in watchlists_disp]
            )
        else:
            opcoes_universo = ["minha watchlist", "watchlist + screener br", "universo completo"]

        universo_sel = st.radio("universo:", opcoes_universo, horizontal=True)

    with c2:
        score_min = st.slider("health score mínimo:", 40, 90, 70, 5)
    with c3:
        rsi_max = st.slider("rsi máximo (sobrevendido):", 20, 55, 40, 5)
        st.session_state['rsi_max'] = rsi_max
    with c4:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_setup = st.button("🔍 varrer agora", type="primary", use_container_width=True)

    with st.expander("ℹ️ entendendo os quadrantes de análise"):
        q1, q2, q3, q4 = st.columns(4)
        q1.success("🎯 **setup ideal**\nscore alto + rsi baixo\nmelhor ponto de entrada")
        q2.warning("⏳ **aguardar pullback**\nscore alto + rsi alto\nboa empresa, preço esticado")
        q3.error("⚠️ **duplo risco**\nscore baixo + rsi alto\nevitar — caro e fraco")
        q4.info("📉 **queda merecida**\nscore baixo + rsi baixo\nfraco estruturalmente")

    if btn_setup:
        if universo_sel == "universo completo":
            universo = list(dict.fromkeys(tickers_watchlist + SCREENER_B3 + SCREENER_US[:15]))
        elif "screener" in universo_sel:
            universo = list(dict.fromkeys(tickers_watchlist + SCREENER_B3[:20]))
        elif any(wl['nome'] in universo_sel for wl in watchlists_disp):
            wl_match = next((wl for wl in watchlists_disp if wl['nome'] in universo_sel), None)
            if wl_match:
                universo = [i['ticker'] for i in listar_watchlist(watchlist_id=wl_match['id'])]
        else:
            universo = tickers_watchlist

        resultados = []
        barra = st.progress(0)
        status = st.empty()
        health_db = {h['ticker']: h for h in get_health_scores()}

        for i, t in enumerate(universo):
            status.text(f"a analisar {t.lower()} ({i+1}/{len(universo)})...")
            barra.progress((i+1)/len(universo))
            t_base = mapear_ticker_base(t)

            try:
                h = health_db.get(t_base)
                if h: score = h['score']
                else: score = calcular_health_score(t_base)['score']

                acao = yf.Ticker(t_base)
                hist_t = acao.history(period="3mo")
                if hist_t.empty or len(hist_t) < 15: continue

                delta = hist_t['Close'].diff()
                ganho = delta.clip(lower=0).rolling(14).mean()
                perda = (-delta.clip(upper=0)).rolling(14).mean()
                rsi = (100 - (100 / (1 + (ganho / perda)))).iloc[-1]

                preco = hist_t['Close'].iloc[-1]
                var_1d = ((preco / hist_t['Close'].iloc[-2]) - 1) * 100
                
                if t_base.endswith('.SA'):
                    from utils.scrapers import buscar_dados_b3
                    f_dados = buscar_dados_b3(t_base)
                    setor = f_dados['setor']
                else:
                    info_dict = acao.info
                    setor = traduzir_setor(info_dict.get('sector', '—'))

                if score >= score_min and rsi <= rsi_max: quadrante, cor = "🎯 setup ideal", "#00C853"
                elif score >= score_min and rsi > rsi_max: quadrante, cor = "⏳ aguardar pullback", "#FF9900"
                elif score < score_min and rsi > rsi_max: quadrante, cor = "⚠️ duplo risco", "#FF1744"
                else: quadrante, cor = "📉 queda merecida", "#555555"

                oportunidade = (score / 100) * (1 - rsi / 100) * 100

                resultados.append({
                    'ticker': t, 'setor': setor, 'quadrante': quadrante, 
                    'score saúde': round(score, 1), 'rsi': round(rsi, 1),
                    'score oportunidade': round(oportunidade, 1),
                    'preço': preco, 'var 1d%': round(var_1d, 2),
                    'na watchlist': t in tickers_watchlist, '_cor': cor
                })
            except Exception:
                pass 

        barra.empty(); status.empty()
        st.session_state['setup_resultados'] = resultados
        st.session_state['setup_ia_result'] = None

    if 'setup_resultados' in st.session_state and st.session_state['setup_resultados']:
        resultados = st.session_state['setup_resultados']
        df_setup = pd.DataFrame(resultados).sort_values('score oportunidade', ascending=False)
        df_setup = df_setup[['ticker', 'setor', 'quadrante', 'score saúde', 'rsi', 'score oportunidade', 'preço', 'var 1d%', 'na watchlist', '_cor']]

        ideais = df_setup[df_setup['quadrante'] == "🎯 setup ideal"]
        pullback = df_setup[df_setup['quadrante'] == "⏳ aguardar pullback"]
        risco = df_setup[df_setup['quadrante'] == "⚠️ duplo risco"]

        st.markdown(f"**resultado:** {len(ideais)} setup ideal | {len(pullback)} aguardar pullback | {len(risco)} duplo risco")

        opcoes_disponiveis = df_setup['quadrante'].unique().tolist()
        defaults_seguros = [q for q in ["🎯 setup ideal", "⏳ aguardar pullback"] if q in opcoes_disponiveis]

        filtro_q = st.multiselect("filtrar por quadrante:", opcoes_disponiveis, default=defaults_seguros)
        df_filtrado = df_setup[df_setup['quadrante'].isin(filtro_q)]

        def colorir_quadrante(val):
            cores = {"🎯 setup ideal": "color: #00C853; font-weight: bold", "⏳ aguardar pullback": "color: #FF9900; font-weight: bold", "⚠️ duplo risco": "color: #FF1744; font-weight: bold", "📉 queda merecida": "color: #888888"}
            return cores.get(val, "")

        st.dataframe(
            df_filtrado.drop(columns=['_cor']).style.applymap(colorir_quadrante, subset=['quadrante']).format({'score saúde': '{:.1f}', 'rsi': '{:.1f}', 'score oportunidade': '{:.1f}', 'preço': '{:.2f}', 'var 1d%': '{:+.2f}%'}),
            use_container_width=True, hide_index=True
        )

        st.markdown("##### 🔍 ver detalhes de um ativo")
        ticker_popup = st.selectbox("selecione um ativo para ver os múltiplos:", [""] + df_filtrado['ticker'].tolist(), key="sel_popup_ativo", label_visibility="collapsed")
        if ticker_popup:
            if st.button(f"📊 ver {ticker_popup.lower()}", key="btn_abrir_popup", type="primary"):
                modal_ativo(ticker_popup)

        st.markdown("---")
        st.markdown("##### ✅ selecionar ativos e gerir watchlists")

        tickers_disponiveis = df_filtrado['ticker'].tolist()
        selecionados = []

        c_all, c_none, _ = st.columns([2, 2, 8])
        if c_all.button("marcar todos", key="sel_all"): st.session_state['sel_todos'] = True
        if c_none.button("desmarcar", key="sel_none"): st.session_state['sel_todos'] = False

        cols_check = st.columns(4)
        for i, ticker in enumerate(tickers_disponiveis):
            row = df_filtrado[df_filtrado['ticker'] == ticker].iloc[0]
            cor_q = {"🎯 setup ideal": "🟢", "⏳ aguardar pullback": "🟡", "⚠️ duplo risco": "🔴", "📉 queda merecida": "⚫"}
            emoji = cor_q.get(row['quadrante'], "⚪")
            label = f"{emoji} {ticker.lower()} ({row['setor'][:10]})"

            default_val = st.session_state.get('sel_todos', False)
            if cols_check[i % 4].checkbox(label, value=default_val, key=f"chk_{ticker}"):
                selecionados.append(ticker)

        if selecionados:
            st.markdown(f"**{len(selecionados)} ativos selecionados**")
            col_wl1, col_wl2 = st.columns([5, 3])
            with col_wl1:
                acao_wl = st.radio("destino:", ["adicionar à watchlist existente", "criar nova watchlist"], horizontal=True, key="radio_destino_wl")
            with col_wl2:
                watchlists_disp = listar_watchlists()
                if acao_wl == "adicionar à watchlist existente":
                    opcoes_dest = {f"{wl['icone']} {wl['nome']}": wl['id'] for wl in watchlists_disp}
                    sel_dest = st.selectbox("watchlist:", list(opcoes_dest.keys()), key="dest_wl_exist")
                    dest_id = opcoes_dest[sel_dest]
                else:
                    nome_nova_wl = st.text_input("nome da nova watchlist:", placeholder="ex: oportunidades maio", key="nome_nova_wl_disc")

            if st.button("💾 salvar seleção", type="primary", use_container_width=True, key="btn_salvar_selecao"):
                if acao_wl == "criar nova watchlist" and nome_nova_wl.strip():
                    dest_id = criar_watchlist(nome_nova_wl.strip(), icone="🎯", cor="#00C853")

                for t in selecionados:
                    t_base = mapear_ticker_base(t)
                    try:
                        mercado_t = "brasil" if t_base.endswith('.SA') else "eua"
                        if t_base.endswith('.SA'):
                            from utils.scrapers import buscar_dados_b3
                            nome_t = buscar_dados_b3(t_base)['nome']
                        else:
                            info_t = yf.Ticker(t_base).info
                            nome_t = info_t.get('shortName', t)
                        adicionar_ativo(t, nome_t, mercado_t, watchlist_id=dest_id)
                    except:
                        adicionar_ativo(t, t, "", watchlist_id=dest_id)

                st.success(f"✅ {len(selecionados)} ativos salvos!")

        if not ideais.empty:
            if st.button("🤖 ia: analisar setup ideais"):
                with st.spinner("gemini a analisar as oportunidades..."):
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        tabela = ideais[['ticker','score saúde','rsi','score oportunidade']].to_csv(index=False)
                        rsi_configurado = st.session_state.get('rsi_max', 40)
                        
                        prompt = f"""
                        você é um gestor de portfólio. o sistema identificou estes ativos como "setup ideal" — fundamentos sólidos + desconto técnico:
                        {tabela}
                        score saúde: 0-100 (saúde fundamentalista da empresa)
                        rsi: momentum (abaixo de {rsi_configurado} = sobrevendido)
                        
                        inicie todas as frases e tópicos com letra minúscula. essa é a forma da nossa escrita.
                        1. **top 3 picks** — qual merece mais atenção e por quê
                        2. **risco comum** — o que esses ativos têm em comum
                        3. **contexto de entrada** — o que monitorar
                        sem recomendação de compra/venda. máximo 300 palavras.
                        """
                        resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        st.session_state['setup_ia_result'] = resp.text
                    except Exception as e:
                        st.error(f"erro na análise da ia: {e}")
            
            if st.session_state.get('setup_ia_result'):
                status_card("análise de setup ideal", st.session_state['setup_ia_result'], "info")

    elif 'setup_resultados' in st.session_state and not st.session_state['setup_resultados']:
        st.warning("nenhum ativo encontrado com os critérios selecionados.")

# ==========================================
# tab 2 — screener quantitativo
# ==========================================
with tab_screener:
    section_title("filtros quantitativos e classificação de ativos")
    
    c_uni1, c_uni2, c_uni3 = st.columns(3)
    with c_uni1: use_b3 = st.checkbox(f"🇧🇷 b3 ({len(SCREENER_B3)} ativos)", value=True, key="scr_b3")
    with c_uni2: use_us = st.checkbox(f"🌎 xstocks / rwa ({len(SCREENER_US)} ativos)", value=True, key="scr_us")
    with c_uni3: use_bench = st.checkbox(f"📊 etfs / benchmarks ({len(XSTOCKS_INDICES)} etfs)", value=False, key="scr_bench")

    universo_scr = []
    if use_b3: universo_scr.extend(SCREENER_B3)
    if use_us: universo_scr.extend(SCREENER_US)
    if use_bench: universo_scr.extend(XSTOCKS_INDICES)

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("⚙️ filtros customizados (pré-ranking)"):
        cf1, cf2, cf3, cf4 = st.columns(4)
        with cf1: pl_max = st.slider("p/l máximo:", 0, 100, 30)
        with cf2: roe_min = st.slider("roe mínimo (%):", 0, 50, 10)
        with cf3: dy_min = st.slider("dy mínimo (%):", 0, 20, 0)
        with cf4: mcap_sel = st.selectbox("market cap mínimo:", ["qualquer", "> 1 bilhão", "> 10 bilhões", "> 100 bilhões"])

    estrategia = st.selectbox(
        "selecione a estratégia quantitativa de ranking:", 
        ["fórmula mágica (greenblatt) - valor + qualidade", "deep value - menor p/vp", "high yield - maior dividend yield", "setup ideal (saúde forte + rsi sobrevendido)"]
    )

    if st.button("🚀 rodar screener", type="primary", use_container_width=True):
        if not universo_scr:
            st.warning("selecione pelo menos um universo de ativos para rastrear.")
        else:
            barra_progresso = st.progress(0)
            texto_status = st.empty()
            
            texto_status.write("a transferir histórico em lote...")
            try:
                tickers_base_unicos = list(set([mapear_ticker_base(t) for t in universo_scr]))
                
                hist_base = yf.download(tickers_base_unicos, period="60d", auto_adjust=True, progress=False)['Close']
                if isinstance(hist_base, pd.Series): 
                    hist_base = hist_base.to_frame(name=tickers_base_unicos[0])
                hist_base = hist_base.ffill()

                rsis = {}
                for t in universo_scr:
                    t_base = mapear_ticker_base(t)
                    try:
                        close = hist_base[t_base].dropna()
                        if len(close) >= 15:
                            delta = close.diff()
                            ganho = delta.clip(lower=0).rolling(14).mean()
                            perda = (-delta.clip(upper=0)).rolling(14).mean()
                            rsis[t] = (100 - (100 / (1 + (ganho / perda)))).iloc[-1]
                        else: rsis[t] = np.nan
                    except: rsis[t] = np.nan
            except Exception:
                rsis = {}
                
            dados_scr = []
            total = len(universo_scr)
            
            for idx, t in enumerate(universo_scr):
                texto_status.write(f"a analisar {t.lower()} ({idx+1}/{total})...")
                t_base = mapear_ticker_base(t)
                try:
                    if t_base.endswith('.SA'):
                        from utils.scrapers import buscar_dados_b3
                        f_dados = buscar_dados_b3(t_base)
                        pl = f_dados['p/l']
                        pvp = f_dados['p/vp']
                        mcap = f_dados['market_cap']
                        roe = f_dados['roe%']
                        dy = f_dados['dy%']
                        nome = f_dados['nome']
                        setor = f_dados['setor']
                    else:
                        info = yf.Ticker(t_base).info
                        pl = info.get('trailingPE', info.get('forwardPE', np.nan))
                        pvp = info.get('priceToBook', np.nan)
                        mcap = info.get('marketCap', 0)
                        roe = (info.get('returnOnEquity') * 100) if info.get('returnOnEquity') is not None else np.nan
                        dy = (info.get('dividendYield') * 100) if info.get('dividendYield') is not None else 0
                        nome = info.get('shortName', t)
                        setor = traduzir_setor(info.get('sector', '—'))
                    
                    dados_scr.append({'ticker': t, 'nome': nome, 'setor': setor, 'p/l': pl, 'p/vp': pvp, 'roe%': roe, 'dy%': dy, 'market cap': mcap, 'rsi': rsis.get(t, np.nan)})
                except Exception:
                    pass 
                barra_progresso.progress((idx + 1) / total)
                
            texto_status.empty(); barra_progresso.empty()
            
            df = pd.DataFrame(dados_scr)
            if df.empty:
                st.error("nenhum dado pôde ser coletado.")
            else:
                colunas_numericas = ['p/l', 'p/vp', 'roe%', 'dy%', 'market cap', 'rsi']
                for col in colunas_numericas:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                df = df.dropna(subset=['p/l', 'roe%', 'p/vp']) 
                if pl_max < 100: df = df[(df['p/l'] <= pl_max) & (df['p/l'] > 0)] 
                if roe_min > 0: df = df[df['roe%'] >= roe_min]
                if dy_min > 0: df = df[df['dy%'] >= dy_min]
                if mcap_sel == "> 1 bilhão": df = df[df['market cap'] >= 1e9]
                elif mcap_sel == "> 10 bilhões": df = df[df['market cap'] >= 10e9]
                elif mcap_sel == "> 100 bilhões": df = df[df['market cap'] >= 100e9]

                if df.empty:
                    st.warning("nenhuma empresa sobreviveu aos filtros escolhidos.")
                else:
                    df['score'] = 0 
                    if "fórmula mágica" in estrategia:
                        df['rank_pl'] = df['p/l'].rank(ascending=True) 
                        df['rank_roe'] = df['roe%'].rank(ascending=False) 
                        df['score'] = df['rank_pl'] + df['rank_roe']
                        df_final = df.sort_values('score', ascending=True).head(5).drop(columns=['rank_pl', 'rank_roe'])
                    elif "deep value" in estrategia:
                        df = df[df['p/vp'] > 0] 
                        df['score'] = df['p/vp'].rank(ascending=True)
                        df_final = df.sort_values('score', ascending=True).head(5)
                    elif "high yield" in estrategia:
                        df['score'] = df['dy%'].rank(ascending=False)
                        df_final = df.sort_values('score', ascending=True).head(5)
                    elif "setup ideal" in estrategia:
                        df = df[(df['rsi'] < 35) & (df['roe%'] > 10) & (df['p/l'] > 0) & (df['p/l'] < 25)]
                        df['score'] = df['rsi'].rank(ascending=True) 
                        df_final = df.sort_values('score', ascending=True).head(10)

                    st.session_state['screener_top5'] = df_final
                    st.session_state['estrategia_usada'] = estrategia

    if 'screener_top5' in st.session_state and not st.session_state['screener_top5'].empty:
        df_final = st.session_state['screener_top5']
        estrategia_usada = st.session_state['estrategia_usada']
        
        st.markdown(f"#### 🏆 top ativos: {estrategia_usada.lower()}")
        
        formatacao = {'p/l': '{:.2f}', 'p/vp': '{:.2f}', 'roe%': '{:.2f}%', 'dy%': '{:.2f}%', 'rsi': '{:.1f}', 'score': '{:.1f}', 'market cap': '${:,.0f}'}
        
        def destacar_score(col):
            if col.name in ['score', 'rsi']: return ['background-color: #221100; color: #FF9900; font-weight: bold'] * len(col)
            return [''] * len(col)
            
        cols_to_show = [c for c in df_final.columns if c not in ['rsi'] or "setup ideal" in estrategia_usada]
        
        st.dataframe(df_final[cols_to_show].style.format(formatacao).apply(destacar_score, axis=0), use_container_width=True, hide_index=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("##### ➕ salvar na watchlist")
        
        cols_b = st.columns(5)
        for idx, row in df_final.reset_index().iterrows():
            t = row['ticker']; n = row['nome']
            with cols_b[idx % 5]:
                if st.button(f"salvar {t.lower()}", key=f"add_{t}", use_container_width=True):
                    t_base = mapear_ticker_base(t)
                    mercado_d = "brasil" if t_base.endswith('.SA') else "eua"
                    modal_salvar_screener(t, n, mercado_d)

        st.markdown("---")
        section_title("🧠 análise contextual — ia + macro")
        
        if st.button("analisar com contexto macro", type="primary", use_container_width=True):
            with st.spinner("a buscar dados macroeconómicos e cruzar com os múltiplos..."):
                try:
                    hoje = datetime.datetime.today()
                    inicio = hoje - datetime.timedelta(days=180)
                    macro = {}
                    
                    try: macro['selic'] = sgs.get({'selic': 432}, start=inicio)['selic'].iloc[-1]
                    except: macro['selic'] = None
                    try: macro['ipca'] = sgs.get({'ipca': 433}, start=inicio)['ipca'].iloc[-1]
                    except: macro['ipca'] = None
                    try: macro['ipca_12m'] = sgs.get({'ipca_12m': 13522}, start=inicio)['ipca_12m'].iloc[-1]
                    except: macro['ipca_12m'] = None

                    if "FRED_API_KEY" in st.secrets:
                        try:
                            fred = Fred(api_key=st.secrets["FRED_API_KEY"])
                            macro['fed'] = fred.get_series('FEDFUNDS', observation_start=inicio).dropna().iloc[-1]
                            macro['dgs10'] = fred.get_series('DGS10', observation_start=inicio).dropna().iloc[-1]
                            macro['vix'] = fred.get_series('VIXCLS', observation_start=inicio).dropna().iloc[-1]
                        except: pass
                    
                    def fmt_m(v, is_vix=False): return f"{v:.1f}" if is_vix and v else (f"{v:.2f}%" if v else "n/d")
                    
                    tabela_txt = df_final[cols_to_show].to_csv(index=False, float_format='%.2f')
                    
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    prompt = f"""
                    você é um gestor de portfólio macro-fundamentalista sênior.

                    cenário macroeconômico real e atual (dados oficiais bcb e fed):
                    - taxa selic (brasil): {fmt_m(macro.get('selic'))}
                    - ipca mensal (brasil): {fmt_m(macro.get('ipca'))}
                    - ipca acumulado 12 meses (brasil): {fmt_m(macro.get('ipca_12m'))}
                    - fed funds rate (eua): {fmt_m(macro.get('fed'))}
                    - treasury 10y (eua): {fmt_m(macro.get('dgs10'))}
                    - vix: {fmt_m(macro.get('vix'), True)}

                    estratégia aplicada pelo algoritmo quantitativo: {estrategia_usada}

                    top finalistas do screener:
                    {tabela_txt}

                    responda em português, formatação markdown, máximo 400 palavras.
                    inicie todas as frases e tópicos com letra minúscula. essa é a forma da nossa escrita.

                    ## diagnóstico do ambiente
                    o cenário macro atual favorece ou desfavorece a estratégia '{estrategia_usada}'? por quê? (baseie-se estritamente nas taxas fornecidas acima, especialmente no juro real frente ao ipca 12m).

                    ## ajuste de convicção por ativo
                    para cada um dos ativos: aumentar, manter ou reduzir convicção dado o macro atual? (tabela: ticker | convicção | razão macroeconômica)

                    ## risco macro ignorado pelo algoritmo
                    cruzando os indicadores fornecidos com o setor das empresas da lista, qual o maior ponto cego desta carteira?
                    """
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    st.session_state['screener_ia_result'] = resp.text
                except Exception as e:
                    st.error(f"erro ao consultar a ia: {e}")
                    
            if st.session_state.get('screener_ia_result'):
                status_card("diagnóstico macro-fundamental", st.session_state['screener_ia_result'], "info")

# ==========================================
# tab 3 — comparação de múltiplos
# ==========================================
with tab_comps:
    st.info("💡 a comparação de múltiplos avançada moveu-se para a aba de research. utilize essa aba para cruzar ativos e obter matrizes completas.")