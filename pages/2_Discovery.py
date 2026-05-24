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
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── silenciar alertas vermelhos do yahoo finance no terminal ──
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from database.db import (
    listar_watchlist, get_health_scores, adicionar_ativo,
    listar_watchlists, criar_watchlist, get_watchlist_padrao,
    get_todos_fundamentos_cache, salvar_fundamento_cache, init_db
)
from utils.tickers import (
    SCREENER_B3, SCREENER_US, XSTOCKS_INDICES, FII_TODOS,
    BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, mapear_ticker_base
)
from utils.health_engine import calcular_health_score
from utils.components import page_header, section_title, status_card, empty_state, inject_keyboard_shortcuts, metric_card
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

init_db()
CACHE_FUNDAMENTOS = get_todos_fundamentos_cache()

c_head1, c_head2, c_head3 = st.columns([6, 2, 2])
with c_head1:
    page_header("🎯 discovery — descoberta", "encontre assimetrias de mercado através de filtros quantitativos e inteligência artificial.")
with c_head2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 sync cache b3 / fii", use_container_width=True, type="primary", help="sincroniza ações e fiis brasileiros."):
        st.session_state['run_sync_b3'] = True
with c_head3:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 sync cache eua", use_container_width=True, type="primary", help="sincroniza ativos do mercado americano."):
        st.session_state['run_sync_us'] = True

st.markdown("---")

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

# ==========================================
# ROTINAS DE SINCRONIZAÇÃO ASSÍNCRONA
# ==========================================
if st.session_state.get('run_sync_b3'):
    st.info("A iniciar sincronização massiva B3 (Ações + FIIs) em background...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    from utils.scrapers import buscar_dados_b3
    
    def fetch_and_save_b3(t):
        try:
            dados = buscar_dados_b3(t)
            salvar_fundamento_cache(t, dados)
            return True
        except: return False

    lista_completa = SCREENER_B3 + FII_TODOS
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_and_save_b3, t): t for t in lista_completa}
        total = len(lista_completa)
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            progress_bar.progress(concluidos / total)
            status_text.text(f"Sincronizando: {futures[future]} ({concluidos}/{total})...")
            
    st.session_state['run_sync_b3'] = False
    st.success("✅ Cache Nacional atualizada! Recarregando...")
    time.sleep(1.5)
    st.rerun()

if st.session_state.get('run_sync_us'):
    st.info("A iniciar extração massiva EUA em background...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def fetch_and_save_us(t_base):
        try:
            info = yf.Ticker(t_base).info
            dados = {
                'nome': info.get('shortName', t_base),
                'setor': traduzir_setor(info.get('sector', '—')),
                'p/l': info.get('trailingPE', info.get('forwardPE', None)),
                'p/vp': info.get('priceToBook', None),
                'roe%': (info.get('returnOnEquity') * 100) if info.get('returnOnEquity') is not None else None,
                'dy%': (info.get('dividendYield') * 100) if info.get('dividendYield') is not None else 0,
                'market_cap': info.get('marketCap', 0),
                'ev/ebitda': info.get('enterpriseToEbitda', None),
                'margem%': (info.get('profitMargins') * 100) if info.get('profitMargins') is not None else None,
                'beta': info.get('beta', None)
            }
            salvar_fundamento_cache(t_base, dados)
            return True
        except: return False

    us_tickers_unicos = list(set([mapear_ticker_base(t) for t in SCREENER_US + XSTOCKS_INDICES]))
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_and_save_us, t): t for t in us_tickers_unicos}
        total = len(us_tickers_unicos)
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            progress_bar.progress(concluidos / total)
            status_text.text(f"Sincronizando EUA: {futures[future]} ({concluidos}/{total})...")
            
    st.session_state['run_sync_us'] = False
    st.success("✅ Cache EUA atualizada! Recarregando...")
    time.sleep(1.5)
    st.rerun()

@st.dialog("➕ salvar na watchlist")
def modal_salvar_screener(ticker: str, nome: str, mercado: str):
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
            if nome_nova_wl.strip(): dest_id = criar_watchlist(nome_nova_wl.strip(), icone="🎯", cor="#00C853")
            else: return st.warning("digite um nome para a nova watchlist.")
        
        adicionar_ativo(ticker, nome, mercado, watchlist_id=dest_id)
        st.success(f"✅ {ticker.lower()} salvo com sucesso!")
        time.sleep(1); st.rerun()

@st.cache_data(ttl=3600, show_spinner=False)
def calcular_momentum(tickers_tuple: tuple) -> list[dict]:
    """Calcula força relativa de 52 semanas para uma lista de tickers."""
    tickers = list(tickers_tuple)
    resultados = []

    def processar(t):
        try:
            t_base = mapear_ticker_base(t)
            acao = yf.Ticker(t_base)
            hist = acao.history(period="1y", auto_adjust=True)
            if hist.empty or len(hist) < 50:
                return None

            close = hist['Close']
            preco_atual = close.iloc[-1]
            preco_1y = close.iloc[0]
            preco_6m = close.iloc[len(close)//2]
            preco_3m = close.iloc[int(len(close)*0.75)]
            preco_1m = close.iloc[-21] if len(close) >= 21 else close.iloc[0]

            ret_1y = (preco_atual / preco_1y - 1) * 100
            ret_6m = (preco_atual / preco_6m - 1) * 100
            ret_3m = (preco_atual / preco_3m - 1) * 100
            ret_1m = (preco_atual / preco_1m - 1) * 100

            mm50  = close.rolling(50).mean().iloc[-1]
            mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.mean()

            acima_mm50  = preco_atual > mm50
            acima_mm200 = preco_atual > mm200

            high_52w = close.max()
            low_52w  = close.min()
            dist_high = (preco_atual / high_52w - 1) * 100

            score_mom = 0
            if ret_1y > 0:  score_mom += 25
            if ret_6m > 0:  score_mom += 25
            if ret_3m > 0:  score_mom += 20
            if ret_1m > 0:  score_mom += 10
            if acima_mm50:  score_mom += 10
            if acima_mm200: score_mom += 10

            f_dados = CACHE_FUNDAMENTOS.get(t_base, {})

            return {
                'ticker': t,
                'nome': f_dados.get('nome', t_base),
                'setor': traduzir_setor(f_dados.get('setor', '—')),
                'preço atual': round(preco_atual, 2),
                'ret 1m (%)': round(ret_1m, 2),
                'ret 3m (%)': round(ret_3m, 2),
                'ret 6m (%)': round(ret_6m, 2),
                'ret 1y (%)': round(ret_1y, 2),
                'dist. topo 52w (%)': round(dist_high, 2),
                'acima mm50': '✅' if acima_mm50 else '❌',
                'acima mm200': '✅' if acima_mm200 else '❌',
                'score momentum': score_mom,
            }
        except:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        futuros = {ex.submit(processar, t): t for t in tickers}
        for fut in as_completed(futuros):
            res = fut.result()
            if res:
                resultados.append(res)

    return sorted(resultados, key=lambda x: x['score momentum'], reverse=True)

# 6. interface de separadores (tabs)
tab_setup, tab_magic, tab_radar, tab_momentum, tab_screener = st.tabs(["🎯 setup ideal (health engine)", "🏆 magic formula (greenblatt)", "🎯 radar de confluência", "🚀 momentum (força relativa)", "🕵️ screener quantitativo"])

# ==========================================
# tab 1 — setup ideal
# ==========================================
with tab_setup:
    st.write("análise cruzada utilizando o novo algoritmo dinâmico de score e momentum para ações e fiis.")

    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        watchlists_disp = listar_watchlists()
        tickers_watchlist = [i['ticker'] for i in listar_watchlist()]
        
        opcoes_universo = ["Brasil - Ações", "Brasil - FIIs", "EUA - Ações"] + [f"{wl['icone']} {wl['nome']}" for wl in watchlists_disp]
        universo_sel = st.selectbox("universo de busca:", opcoes_universo)

    with c2: score_min = st.slider("health score mínimo:", 40, 90, 65, 5)
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_setup = st.button("🔍 varrer com health engine", type="primary", use_container_width=True)

    if btn_setup:
        if universo_sel == "Brasil - Ações": 
            universo = list(dict.fromkeys(SCREENER_B3))
        elif universo_sel == "Brasil - FIIs": 
            universo = list(dict.fromkeys(FII_TODOS))
        elif universo_sel == "EUA - Ações": 
            universo = list(dict.fromkeys(SCREENER_US))
        else:
            wl_match = next((wl for wl in watchlists_disp if wl['nome'] in universo_sel), None)
            if wl_match: 
                universo = [i['ticker'] for i in listar_watchlist(watchlist_id=wl_match['id'])]
            else: 
                universo = tickers_watchlist

        barra = st.progress(0)
        status = st.empty()
        resultados_engine = []

        # batch download único para todos os ativos
        status.text(f"baixando histórico de {len(universo)} ativos de uma vez...")
        tickers_base_universo = list(set([mapear_ticker_base(t) for t in universo]))
        hist_batch = {}

        try:
            df_batch = yf.download(
                tickers_base_universo,
                period="1y",
                auto_adjust=True,
                progress=False,
                threads=True
            )
            if isinstance(df_batch.columns, pd.MultiIndex):
                df_close = df_batch['Close']
            else:
                df_close = df_batch

            if isinstance(df_close, pd.DataFrame):
                for col in df_close.columns:
                    serie = df_close[col].dropna()
                    if len(serie) > 10:
                        hist_batch[str(col)] = serie.to_frame('Close')
            elif isinstance(df_close, pd.Series):
                if tickers_base_universo:
                    hist_batch[tickers_base_universo[0]] = df_close.dropna().to_frame('Close')
        except Exception as e:
            status.text(f"batch falhou ({e}), usando chamadas individuais...")

        # loop sequencial — sem threads para não causar rerun
        macro_ctx = None
        for i, t in enumerate(universo):
            t_base = mapear_ticker_base(t)
            status.text(f"engine a processar {t.lower()} ({i+1}/{len(universo)})...")
            barra.progress((i + 1) / len(universo))

            try:
                hist_ext = hist_batch.get(t_base, None)
                resultado_engine = calcular_health_score(
                    t_base,
                    macro_context=macro_ctx,
                    hist_externo=hist_ext
                )
                score_val = resultado_engine.get('score', 0)
                if score_val >= score_min:
                    f_dados = CACHE_FUNDAMENTOS.get(t_base, {})
                    resultados_engine.append({
                        'ticker': t,
                        'score': score_val,
                        'status': resultado_engine.get('status', ''),
                        'alertas': resultado_engine.get('alertas', []),
                        'nome': f_dados.get('nome', t_base),
                        'setor': traduzir_setor(f_dados.get('setor', '—')),
                        'p/l': f_dados.get('p/l'),
                        'p/vp': f_dados.get('p/vp'),
                        'roe%': f_dados.get('roe%'),
                        'dy%': f_dados.get('dy%'),
                    })
            except Exception:
                continue

        status.text(f"✅ concluído — {len(resultados_engine)} ativos acima do score {score_min}.")
        resultados_engine.sort(key=lambda x: x['score'], reverse=True)

        barra.empty(); status.empty()
        st.session_state['setup_resultados'] = resultados_engine
        st.session_state['setup_ia_result'] = None

    if 'setup_resultados' in st.session_state and st.session_state['setup_resultados']:
        df_setup = pd.DataFrame(st.session_state['setup_resultados']).sort_values('score', ascending=False)

        # filtro por status
        status_disponiveis = df_setup['status'].dropna().unique().tolist()
        status_opcoes = ["todos"] + sorted(set([
            s.split(":")[0].strip() if ":" in s else s
            for s in status_disponiveis
        ]))

        fcol1, fcol2, fcol3 = st.columns([2, 2, 2])
        with fcol1:
            filtro_status = st.selectbox(
                "filtrar por status:",
                status_opcoes,
                key="filtro_status_setup"
            )
        with fcol2:
            filtro_setor = st.selectbox(
                "filtrar por setor:",
                ["todos"] + sorted(df_setup['setor'].dropna().unique().tolist()),
                key="filtro_setor_setup"
            )
        with fcol3:
            st.metric("ativos encontrados", len(df_setup))

        # aplicar filtros
        df_filtrado = df_setup.copy()
        if filtro_status != "todos":
            df_filtrado = df_filtrado[df_filtrado['status'].str.contains(filtro_status, na=False)]
        if filtro_setor != "todos":
            df_filtrado = df_filtrado[df_filtrado['setor'] == filtro_setor]

        if df_filtrado.empty:
            st.info("nenhum ativo encontrado com os filtros selecionados.")
        else:
            st.caption(f"exibindo {len(df_filtrado)} de {len(df_setup)} ativos")

        st.markdown("<br>", unsafe_allow_html=True)
        for idx, row in df_filtrado.reset_index(drop=True).iterrows():
            cols = st.columns([1, 2, 3, 3, 2, 1.5, 1.5, 2])
            with cols[0]:
                st.markdown(f"<div style='font-family: Courier New; font-weight: bold; color: #FF9900; padding-top: 8px;'>{idx+1}</div>", unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"<div style='font-family: Courier New; font-weight: bold; color: #FFFFFF; padding-top: 8px;'>{row['ticker']}</div>", unsafe_allow_html=True)
            with cols[2]:
                nome_trunc = str(row['nome'])[:20] + ('...' if len(str(row['nome'])) > 20 else '')
                st.markdown(f"<div style='font-size: 0.85rem; color: #555; padding-top: 8px;'>{nome_trunc}</div>", unsafe_allow_html=True)
            with cols[3]:
                status_color = "#888888"
                if "🟢" in row['status']: status_color = "#00C853"
                elif "🟡" in row['status']: status_color = "#FF9900"
                elif "🟠" in row['status']: status_color = "#FF7043"
                elif "🔴" in row['status']: status_color = "#FF1744"
                st.markdown(f"<div style='padding-top: 8px; font-size: 0.8rem; font-weight: bold; color: {status_color};'>{row['status']}</div>", unsafe_allow_html=True)
            with cols[4]:
                st.markdown(f"<div style='padding-top: 8px; font-size: 0.85rem;'>{row['setor']}</div>", unsafe_allow_html=True)
            with cols[5]:
                st.markdown(f"<div style='padding-top: 8px; font-weight: bold;'>HS: {row['score']:.1f}</div>", unsafe_allow_html=True)
            with cols[6]:
                var_color = "#00C853" if row.get('var 1d%', 0) >= 0 else "#FF1744"
                st.markdown(f"<div style='padding-top: 8px; color: {var_color};'>{row.get('var 1d%', 0):+.2f}%</div>", unsafe_allow_html=True)
            with cols[7]:
                if st.button("＋ watchlist", key=f"btn_wl_setup_{row['ticker']}_{idx}", use_container_width=True):
                    modal_salvar_screener(row['ticker'], row['nome'], "brasil" if mapear_ticker_base(row['ticker']).endswith('.SA') else "eua")
            st.markdown("<hr style='border-top: 1px solid #1e1e1e; margin: 0.5rem 0;'>", unsafe_allow_html=True)

        st.markdown("---")
        if not df_setup[df_setup['status'].str.contains("🟢")].empty:
            if st.button("🤖 ia: analisar top picks (acumulação forte)", use_container_width=True, type="primary"):
                with st.spinner("gemini a elaborar o racional..."):
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        alvos = df_setup[df_setup['status'].str.contains("🟢")]
                        tabela = alvos[['ticker','score','setor']].to_csv(index=False)
                        
                        prompt = f"""
                        você é um gestor de portfólio sênior. 
                        o sistema FinTerminal classificou estes ativos como "🟢 ACUMULAÇÃO FORTE" (excelente qualidade e preço atrativo).
                        
                        ativos detectados:
                        {tabela}
                        
                        responda de forma técnica e suscinta (máx 300 palavras):
                        1. **análise setorial**: por que esses setores estão oferecendo oportunidades agora?
                        2. **fatores de risco**: o que pode invalidar o score alto desses ativos no médio prazo?
                        
                        inicie todas as frases e tópicos com letra minúscula.
                        """
                        resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        st.session_state['setup_ia_result'] = resp.text
                    except Exception as e: 
                        st.error(f"erro na conexão com a ia. tente novamente. detalhe: {e}")
            
            if st.session_state.get('setup_ia_result'):
                status_card("parecer da ia sobre as oportunidades", st.session_state['setup_ia_result'], "info")

# ==========================================
# tab 2 — magic formula (greenblatt)
# ==========================================
with tab_magic:
    section_title("🏆 magic formula — ranking de valor + qualidade")
    status_card("metodologia greenblatt", "ranking combinado de dois critérios: earnings yield (ebit/ev) — quanto a empresa gera para cada R$ de valor de mercado; e roic — eficiência do capital empregado. empresas no top de ambos os rankings simultaneamente tendem a superar o mercado no longo prazo.", "info")
    
    cm_c1, cm_c2, cm_c3 = st.columns([3, 2, 2])
    with cm_c1:
        magic_universos = st.multiselect("universo de análise:", ["🇧🇷 b3 — ações", "🌎 eua — ações", "🏢 b3 — fiis"], default=["🇧🇷 b3 — ações"])
    with cm_c2:
        magic_top_n = st.slider("top N ativos:", min_value=5, max_value=30, value=15, step=5)
    with cm_c3:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_magic = st.button("🚀 rodar magic formula", type="primary", use_container_width=True)
        
    if btn_magic:
        magic_lista = []
        if "🇧🇷 b3 — ações" in magic_universos: magic_lista.extend(SCREENER_B3)
        if "🌎 eua — ações" in magic_universos: magic_lista.extend(SCREENER_US)
        if "🏢 b3 — fiis" in magic_universos: magic_lista.extend(FII_TODOS)
        
        if not magic_lista:
            st.warning("selecione pelo menos um universo de análise.")
        else:
            with st.spinner("calculando rankings de earnings yield e roic..."):
                magic_dados = []
                for t in magic_lista:
                    t_base = mapear_ticker_base(t)
                    try:
                        f_dados = CACHE_FUNDAMENTOS.get(t_base)
                        if not f_dados:
                            info = yf.Ticker(t_base).info
                            f_dados = {
                                'p/l': info.get('trailingPE', info.get('forwardPE', np.nan)),
                                'p/vp': info.get('priceToBook', np.nan),
                                'ev/ebitda': info.get('enterpriseToEbitda', np.nan),
                                'market_cap': info.get('marketCap', 0),
                                'roe%': (info.get('returnOnEquity') * 100) if info.get('returnOnEquity') else np.nan,
                                'dy%': (info.get('dividendYield') * 100) if info.get('dividendYield') else 0,
                                'nome': info.get('shortName', t), 
                                'setor': traduzir_setor(info.get('sector', '—'))
                            }
                        magic_dados.append({
                            'ticker': t,
                            'nome': f_dados.get('nome', t),
                            'setor': f_dados.get('setor', '—'),
                            'ev/ebitda': pd.to_numeric(f_dados.get('ev/ebitda'), errors='coerce'),
                            'roe%': pd.to_numeric(f_dados.get('roe%'), errors='coerce'),
                            'dy%': pd.to_numeric(f_dados.get('dy%', 0), errors='coerce'),
                            'p/vp': pd.to_numeric(f_dados.get('p/vp'), errors='coerce')
                        })
                    except Exception: pass
                
                df_magic = pd.DataFrame(magic_dados)
                for col in ['ev/ebitda', 'roe%', 'dy%', 'p/vp']:
                    df_magic[col] = pd.to_numeric(df_magic[col], errors='coerce')
                    
                df_magic = df_magic[(df_magic['ev/ebitda'] > 0) & (df_magic['roe%'] > 0)].dropna(subset=['ev/ebitda', 'roe%'])
                df_magic['earnings yield (%)'] = (1 / df_magic['ev/ebitda']) * 100
                df_magic['rank_ey'] = df_magic['earnings yield (%)'].rank(ascending=False, method='min')
                df_magic['rank_roic'] = df_magic['roe%'].rank(ascending=False, method='min')
                df_magic['rank_magic'] = df_magic['rank_ey'] + df_magic['rank_roic']
                df_magic = df_magic.sort_values('rank_magic', ascending=True).head(magic_top_n)
                df_magic['posição'] = range(1, len(df_magic) + 1)
                st.session_state['magic_resultado'] = df_magic
                
    if 'magic_resultado' in st.session_state and not st.session_state['magic_resultado'].empty:
        df_res_magic = st.session_state['magic_resultado']
        section_title(f"top {len(df_res_magic)} ativos — magic formula ranking")
        
        cm_res1, cm_res2 = st.columns(2)
        best_ey = df_res_magic.sort_values('earnings yield (%)', ascending=False).iloc[0]
        best_roe = df_res_magic.sort_values('roe%', ascending=False).iloc[0]
        with cm_res1:
            metric_card("melhor earnings yield", f"{best_ey['ticker']} ({best_ey['earnings yield (%)']:.2f}%)")
        with cm_res2:
            metric_card("melhor roe% (roic proxy)", f"{best_roe['ticker']} ({best_roe['roe%']:.1f}%)")
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        for idx, row in df_res_magic.iterrows():
            cols = st.columns([1, 2, 3, 2, 2, 2, 2, 2])
            with cols[0]:
                st.markdown(f"<div style='font-family: Courier New; font-weight: bold; color: #FF9900; padding-top: 8px;'>{row['posição']}</div>", unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"<div style='font-family: Courier New; font-weight: bold; color: #FFFFFF; padding-top: 8px;'>{row['ticker']}</div>", unsafe_allow_html=True)
            with cols[2]:
                nome_trunc = str(row['nome'])[:25] + ('...' if len(str(row['nome'])) > 25 else '')
                st.markdown(f"<div style='font-size: 0.85rem; color: #555; padding-top: 8px;'>{nome_trunc}</div>", unsafe_allow_html=True)
            with cols[3]:
                st.markdown(f"<div style='padding-top: 8px; font-size: 0.85rem;'>{row['setor']}</div>", unsafe_allow_html=True)
            with cols[4]:
                st.markdown(f"<div style='padding-top: 8px;'>EY: {row['earnings yield (%)']:.2f}%</div>", unsafe_allow_html=True)
            with cols[5]:
                st.markdown(f"<div style='padding-top: 8px;'>ROE: {row['roe%']:.1f}%</div>", unsafe_allow_html=True)
            with cols[6]:
                st.markdown(f"<div style='padding-top: 8px;'>DY: {row['dy%']:.1f}%</div>", unsafe_allow_html=True)
            with cols[7]:
                if st.button("＋ watchlist", key=f"btn_wl_magic_{row['ticker']}_{idx}", use_container_width=True):
                    modal_salvar_screener(row['ticker'], row['nome'], "brasil" if mapear_ticker_base(row['ticker']).endswith('.SA') else "eua")
            
            st.markdown("<hr style='border-top: 1px solid #1e1e1e; margin: 0.5rem 0;'>", unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🧠 ia: analisar o ranking magic formula", type="primary", use_container_width=True):
            with st.spinner("analisando ranking e fundamentos..."):
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    dados_texto = df_res_magic.head(10).to_csv(index=False)
                    prompt = f"analise este ranking top 10 da magic formula de greenblatt:\n{dados_texto}\nidentifique padrões setoriais, riscos e qual dos ativos tem a melhor combination qualidade-preço. responda em minúsculas e direto."
                    res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    status_card("análise ia — magic formula", res.text, "info")
                except Exception as e:
                    st.error(f"Erro na IA: {e}")

# ==========================================
# tab 3 — radar de confluência
# ==========================================
with tab_radar:
    section_title("🎯 radar de confluência — health score × magic formula")
    status_card("como funciona", "cruza dois sistemas independentes: o health engine (qualidade de balanço, momentum técnico e risco macro) com a magic formula de greenblatt (earnings yield e roic). ativos no topo de ambos simultaneamente representam a confluência mais forte — qualidade confirmada por múltiplos ângulos.", "info")
    
    c_rad1, c_rad2, c_rad3, c_rad4 = st.columns(4)
    with c_rad1:
        radar_universos = st.multiselect("universo:", ["🇧🇷 b3 — ações", "🌎 eua — ações", "🏢 b3 — fiis"], default=["🇧🇷 b3 — ações"])
    with c_rad2:
        radar_top_n = st.slider("top N resultados:", min_value=5, max_value=20, value=10, step=5)
    with c_rad3:
        peso_health = st.slider("peso health score (%):", min_value=20, max_value=80, value=60, step=10)
        peso_magic = 100 - peso_health
    with c_rad4:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_radar = st.button("🔍 rodar radar", type="primary", use_container_width=True)
        
    st.caption(f"ponderação atual: health score {peso_health}% | magic formula {peso_magic}%")
    
    if btn_radar:
        radar_lista = []
        if "🇧🇷 b3 — ações" in radar_universos: radar_lista.extend(SCREENER_B3)
        if "🌎 eua — ações" in radar_universos: radar_lista.extend(SCREENER_US)
        if "🏢 b3 — fiis" in radar_universos: radar_lista.extend(FII_TODOS)
        
        if not radar_lista:
            st.warning("selecione pelo menos um universo de análise.")
        else:
            with st.spinner("cruzando health scores com magic formula..."):
                raw_scores = get_health_scores()
                health_map = {item['ticker']: item['score'] for item in raw_scores}
                
                if not health_map:
                    st.warning("rode o health engine primeiro na aba setup ideal para ter scores calculados.")
                else:
                    radar_dados = []
                    for t in radar_lista:
                        t_base = mapear_ticker_base(t)
                        try:
                            f_dados = CACHE_FUNDAMENTOS.get(t_base)
                            if not f_dados:
                                continue
                                
                            ev_ebitda = pd.to_numeric(f_dados.get('ev/ebitda'), errors='coerce')
                            roe = pd.to_numeric(f_dados.get('roe%'), errors='coerce')
                            
                            if pd.isna(ev_ebitda) or ev_ebitda <= 0 or pd.isna(roe):
                                continue
                                
                            health_score_val = health_map.get(t_base, health_map.get(t, None))
                            if health_score_val is None:
                                continue
                                
                            earnings_yield = (1 / ev_ebitda) * 100
                            
                            radar_dados.append({
                                'ticker': t,
                                'nome': f_dados.get('nome', t),
                                'setor': f_dados.get('setor', '—'),
                                'health score': health_score_val,
                                'earnings yield (%)': earnings_yield,
                                'roe%': roe,
                                'dy%': pd.to_numeric(f_dados.get('dy%', 0), errors='coerce'),
                                'p/vp': pd.to_numeric(f_dados.get('p/vp'), errors='coerce')
                            })
                        except Exception:
                            continue
                            
                    if len(radar_dados) < 5:
                        st.warning("poucos ativos com dados suficientes. sincronize o cache e rode o health engine primeiro.")
                    else:
                        df_radar = pd.DataFrame(radar_dados)
                        rank_health = df_radar['health score'].rank(ascending=False, method='min')
                        rank_magic_r = (1 / df_radar['earnings yield (%)']).rank(ascending=True, method='min') + df_radar['roe%'].rank(ascending=False, method='min')
                        
                        rank_health_norm = (rank_health / len(df_radar)) * 100
                        rank_magic_norm = (rank_magic_r / (len(df_radar) * 2)) * 100
                        
                        df_radar['score_confluencia'] = ((peso_health / 100) * (100 - rank_health_norm)) + ((peso_magic / 100) * (100 - rank_magic_norm))
                        
                        df_radar = df_radar.sort_values('score_confluencia', ascending=False).head(radar_top_n)
                        df_radar['posição'] = range(1, len(df_radar) + 1)
                        
                        st.session_state['radar_resultado'] = df_radar
                        st.session_state['peso_health_radar'] = peso_health
                        st.session_state['peso_magic_radar'] = peso_magic
                        
    if 'radar_resultado' in st.session_state and not st.session_state['radar_resultado'].empty:
        df_rad = st.session_state['radar_resultado']
        section_title("🏆 top ativos por confluência")
        
        c_rm1, c_rm2, c_rm3 = st.columns(3)
        with c_rm1:
            metric_card("ativos analisados", str(len(df_rad)))
        with c_rm2:
            metric_card("ponderação", f"HS {st.session_state.get('peso_health_radar', 60)}% / MF {st.session_state.get('peso_magic_radar', 40)}%")
        with c_rm3:
            metric_card("melhor confluência", df_rad.iloc[0]['ticker'])
            
        st.markdown("<br>", unsafe_allow_html=True)
        for idx, row in df_rad.reset_index(drop=True).iterrows():
            cols = st.columns([1, 2, 3, 2, 1.5, 1.5, 1.5, 1.5, 2])
            with cols[0]:
                st.markdown(f"<div style='font-family: Courier New; font-weight: bold; color: #FF9900; padding-top: 8px;'>{row['posição']}</div>", unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"<div style='font-family: Courier New; font-weight: bold; color: #FFFFFF; padding-top: 8px;'>{row['ticker']}</div>", unsafe_allow_html=True)
            with cols[2]:
                nome_trunc = str(row['nome'])[:20] + ('...' if len(str(row['nome'])) > 20 else '')
                st.markdown(f"<div style='font-size: 0.85rem; color: #555; padding-top: 8px;'>{nome_trunc}</div>", unsafe_allow_html=True)
            with cols[3]:
                st.markdown(f"<div style='padding-top: 8px; font-size: 0.85rem;'>{row['setor']}</div>", unsafe_allow_html=True)
            with cols[4]:
                hs_val = row['health score']
                hs_color = "#00C853" if hs_val >= 65 else ("#FF9900" if hs_val >= 40 else "#FF1744")
                st.markdown(f"<div style='padding-top: 8px; font-weight: bold; color: {hs_color};'>HS: {hs_val:.0f}</div>", unsafe_allow_html=True)
            with cols[5]:
                st.markdown(f"<div style='padding-top: 8px; font-size: 0.85rem;'>EY: {row['earnings yield (%)']:.1f}%</div>", unsafe_allow_html=True)
            with cols[6]:
                st.markdown(f"<div style='padding-top: 8px; font-size: 0.85rem;'>ROE: {row['roe%']:.1f}%</div>", unsafe_allow_html=True)
            with cols[7]:
                st.markdown(f"<div style='padding-top: 8px; color: #00B0FF; font-weight: bold;'>{row['score_confluencia']:.1f}</div>", unsafe_allow_html=True)
            with cols[8]:
                if st.button("＋ watchlist", key=f"btn_wl_radar_{row['ticker']}_{idx}", use_container_width=True):
                    modal_salvar_screener(row['ticker'], row['nome'], "brasil" if mapear_ticker_base(row['ticker']).endswith('.SA') else "eua")
            st.markdown("<hr style='border-top: 1px solid #1e1e1e; margin: 0.5rem 0;'>", unsafe_allow_html=True)
        
        fig_scat = go.Figure()
        fig_scat.add_trace(go.Scatter(
            x=df_rad['health score'],
            y=df_rad['earnings yield (%)'],
            mode='markers+text',
            text=df_rad['ticker'],
            textposition='top center',
            marker=dict(
                size=12,
                color=df_rad['score_confluencia'],
                colorscale=[[0, "#FF1744"], [1, "#00C853"]],
                showscale=True,
                colorbar=dict(title="confluência")
            )
        ))
        layout_scat = base_layout(height=450, title="mapa de confluência: health score vs earnings yield")
        layout_scat['xaxis_title'] = "health score"
        layout_scat['yaxis_title'] = "earnings yield (%)"
        fig_scat.update_layout(**layout_scat)
        st.plotly_chart(fig_scat, use_container_width=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🧠 ia: analisar as confluências detectadas", type="primary", use_container_width=True):
            with st.spinner("analisando confluências..."):
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    csv_confl = df_rad.head(10).to_csv(index=False)
                    prompt = f"analise este ranking de confluência (health score + magic formula):\n{csv_confl}\nqual ativo tem a tese mais sólida considerando os dois sistemas? quais setores estão concentrando as melhores confluências? qual o risco de cada um dos top 3? escreva em minúsculas e seja direto."
                    res_conf = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    status_card("análise ia — radar de confluência", res_conf.text, "info")
                except Exception as e:
                    st.error(f"Erro IA: {e}")

# ==========================================
# tab 4 — momentum screener
# ==========================================
with tab_momentum:
    section_title("🚀 momentum screener — força relativa")

    status_card(
        "metodologia",
        "score de momentum de 0 a 100 baseado em 6 critérios: retorno 1y, 6m, 3m e 1m (positivo = ponto), preço acima da MM50 e MM200. ativos com score alto têm momentum técnico consistente em múltiplas janelas.",
        tipo="info"
    )

    mc1, mc2, mc3 = st.columns([3, 2, 2])
    with mc1:
        mom_universos = st.multiselect(
            "universo:",
            ["🇧🇷 b3 — ações", "🌎 eua — ações", "🏢 b3 — fiis"],
            default=["🇧🇷 b3 — ações"],
            key="mom_universos"
        )
    with mc2:
        mom_top_n = st.slider("top N ativos:", 5, 30, 15, 5, key="mom_top_n")
    with mc3:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_momentum = st.button("🚀 calcular momentum", type="primary", use_container_width=True)

    score_minimo = st.slider("score mínimo de momentum:", 0, 100, 50, 10, key="mom_score_min")

    if btn_momentum:
        mom_lista = []
        if "🇧🇷 b3 — ações" in mom_universos: mom_lista += SCREENER_B3
        if "🌎 eua — ações" in mom_universos: mom_lista += SCREENER_US
        if "🏢 b3 — fiis" in mom_universos: mom_lista += FII_TODOS

        if not mom_lista:
            st.warning("selecione pelo menos um universo.")
        else:
            with st.spinner(f"calculando momentum de {len(mom_lista)} ativos..."):
                resultados_mom = calcular_momentum(tuple(mom_lista))
                df_mom = pd.DataFrame(resultados_mom)
                if not df_mom.empty:
                    df_mom = df_mom[df_mom['score momentum'] >= score_minimo]
                    df_mom = df_mom.head(mom_top_n)
                    st.session_state['momentum_resultado'] = df_mom

    if 'momentum_resultado' in st.session_state and not st.session_state['momentum_resultado'].empty:
        df_m = st.session_state['momentum_resultado']

        section_title(f"top {len(df_m)} ativos por momentum")

        mm1, mm2, mm3 = st.columns(3)
        with mm1:
            metric_card("melhor momentum", df_m.iloc[0]['ticker'], f"score {df_m.iloc[0]['score momentum']}/100", "bull")
        with mm2:
            metric_card("retorno médio 1y", f"{df_m['ret 1y (%)'].mean():.1f}%", "", "bull" if df_m['ret 1y (%)'].mean() > 0 else "bear")
        with mm3:
            acima_200 = (df_m['acima mm200'] == '✅').sum()
            metric_card("acima da mm200", f"{acima_200}/{len(df_m)}", "tendência de alta", "bull" if acima_200 > len(df_m)//2 else "amber")

        cols_mostrar = ['ticker', 'nome', 'setor', 'ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)', 'dist. topo 52w (%)', 'acima mm50', 'acima mm200', 'score momentum']

        def colorir_momentum(val):
            if isinstance(val, (int, float)):
                if val > 0: return 'color: #00C853'
                if val < 0: return 'color: #FF1744'
            return ''

        st.dataframe(
            df_m[cols_mostrar].style
                .map(colorir_momentum, subset=['ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)', 'dist. topo 52w (%)'])
                .format({'ret 1m (%)': '{:+.2f}%', 'ret 3m (%)': '{:+.2f}%', 'ret 6m (%)': '{:+.2f}%', 'ret 1y (%)': '{:+.2f}%', 'dist. topo 52w (%)': '{:+.2f}%', 'score momentum': '{:.0f}'}),
            use_container_width=True,
            hide_index=True
        )

        section_title("📊 mapa de retornos por janela temporal")

        fig_mom = go.Figure()
        janelas = ['ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)']
        labels = ['1 mês', '3 meses', '6 meses', '1 ano']

        for _, row in df_m.head(10).iterrows():
            fig_mom.add_trace(go.Scatter(
                x=labels,
                y=[row[j] for j in janelas],
                mode='lines+markers',
                name=row['ticker'],
                line=dict(width=1.5),
                hovertemplate=f"{row['ticker']}<br>%{{x}}: %{{y:+.1f}}%<extra></extra>"
            ))

        fig_mom.add_hline(y=0, line_color="#333", line_dash="dash", line_width=1)
        fig_mom.update_layout(**base_layout(height=400, title="retorno acumulado por janela — top 10 ativos"))
        st.plotly_chart(fig_mom, use_container_width=True)

        st.markdown("---")

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            for _, row in df_m.iterrows():
                c1, c2, c3 = st.columns([2, 3, 2])
                c1.markdown(f"**{row['ticker']}**")
                score = row['score momentum']
                cor_score = "#00C853" if score >= 70 else ("#FF9900" if score >= 40 else "#FF1744")
                barra = "█" * int(score // 10) + "░" * int(10 - score // 10)
                c2.markdown(f'<span style="font-family:Courier New; font-size:0.8rem; color:{cor_score};">{barra}</span>', unsafe_allow_html=True)
                if c3.button("＋ watchlist", key=f"btn_wl_mom_{row['ticker']}", use_container_width=True):
                    mercado = "brasil" if mapear_ticker_base(row['ticker']).endswith('.SA') else "eua"
                    modal_salvar_screener(row['ticker'], row['nome'], mercado)

        with col_a2:
            if st.button("🧠 ia: analisar momentum e identificar líderes setoriais", type="primary", use_container_width=True):
                with st.spinner("analisando momentum..."):
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        dados_texto = df_m[cols_mostrar].head(10).to_csv(index=False)
                        prompt = f"""você é um analista técnico e quantitativo sênior. analise os dados de momentum abaixo e responda em 4 bullet points curtos em português:
1. qual ativo tem o momentum mais consistente e por quê.
2. quais setores estão liderando o movimento.
3. algum ativo próximo do topo de 52 semanas que pode estar em breakout.
4. riscos: algum ativo com momentum positivo mas fundamentos fracos que pode ser uma armadilha.

dados:\n{dados_texto}

inicie todas as frases com letra minúscula. seja direto e objetivo."""
                        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        status_card("análise de momentum — ia", response.text, tipo="info")
                    except Exception as e:
                        st.error(f"erro no agente de ia: {e}")

# ==========================================
# tab 5 — screener quantitativo
# ==========================================
with tab_screener:
    section_title("filtros quantitativos e classificação de ativos")
    
    c_uni1, c_uni2, c_uni3, c_uni4 = st.columns(4)
    with c_uni1: use_b3 = st.checkbox(f"🇧🇷 b3 ({len(SCREENER_B3)} ações)", value=True, key="scr_b3")
    with c_uni2: use_fii = st.checkbox(f"🏢 fiis ({len(FII_TODOS)} fundos)", value=True, key="scr_fii")
    with c_uni3: use_us = st.checkbox(f"🌎 xstocks/us ({len(SCREENER_US)} ativos)", value=False, key="scr_us")
    with c_uni4: use_bench = st.checkbox(f"📊 etfs ({len(XSTOCKS_INDICES)} etfs)", value=False, key="scr_bench")

    universo_scr = []
    if use_b3: universo_scr.extend(SCREENER_B3)
    if use_fii: universo_scr.extend(FII_TODOS)
    if use_us: universo_scr.extend(SCREENER_US)
    if use_bench: universo_scr.extend(XSTOCKS_INDICES)

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("⚙️ filtros customizados (pré-ranking)"):
        cf1, cf2, cf3, cf4 = st.columns(4)
        with cf1: pl_max = st.slider("p/l máximo (ações):", 0, 100, 30)
        with cf2: pvp_max = st.slider("p/vp máximo (geral):", 0.0, 5.0, 2.5, 0.1)
        with cf3: dy_min = st.slider("dy mínimo (%):", 0, 20, 0)
        with cf4: mcap_sel = st.selectbox("market cap mínimo:", ["qualquer", "> 1 bilhão", "> 10 bilhões", "> 100 bilhões"])

    estrategia = st.selectbox(
        "selecione a estratégia quantitativa de ranking:", 
        ["fórmula mágica (greenblatt) - valor + qualidade", "deep value - menor p/vp", "high yield - maior dividend yield"]
    )

    if st.button("🚀 rodar screener", type="primary", use_container_width=True):
        if not universo_scr: st.warning("selecione pelo menos um universo de ativos para rastrear.")
        else:
            barra_progresso = st.progress(0)
            texto_status = st.empty()
            
            dados_scr = []
            total = len(universo_scr)
            
            for idx, t in enumerate(universo_scr):
                texto_status.write(f"a mapear {t.lower()} ({idx+1}/{total})...")
                t_base = mapear_ticker_base(t)
                try:
                    f_dados = CACHE_FUNDAMENTOS.get(t_base)
                    if not f_dados:
                        if t_base.endswith('.SA'):
                            from utils.scrapers import buscar_dados_b3
                            f_dados = buscar_dados_b3(t_base)
                        else:
                            info = yf.Ticker(t_base).info
                            f_dados = {
                                'p/l': info.get('trailingPE', info.get('forwardPE', np.nan)),
                                'p/vp': info.get('priceToBook', np.nan),
                                'market_cap': info.get('marketCap', 0),
                                'roe%': (info.get('returnOnEquity') * 100) if info.get('returnOnEquity') else np.nan,
                                'dy%': (info.get('dividendYield') * 100) if info.get('dividendYield') else 0,
                                'ev/ebitda': info.get('enterpriseToEbitda', np.nan),
                                'margem%': (info.get('profitMargins') * 100) if info.get('profitMargins') else np.nan,
                                'nome': info.get('shortName', t), 'setor': traduzir_setor(info.get('sector', '—'))
                            }
                    
                    dados_scr.append({
                        'ticker': t, 'nome': f_dados.get('nome', t), 'setor': f_dados.get('setor', '—'),
                        'p/l': f_dados.get('p/l', np.nan), 'p/vp': f_dados.get('p/vp', np.nan), 'roe%': f_dados.get('roe%', np.nan),
                        'dy%': f_dados.get('dy%', np.nan), 'market cap': f_dados.get('market_cap', 0),
                        'ev/ebitda': f_dados.get('ev/ebitda', np.nan), 'margem%': f_dados.get('margem%', np.nan)
                    })
                except Exception: pass 
                barra_progresso.progress((idx + 1) / total)
                
            texto_status.empty(); barra_progresso.empty()
            
            df = pd.DataFrame(dados_scr)
            if df.empty: st.error("nenhum dado pôde ser coletado.")
            else:
                for col in ['p/l', 'p/vp', 'roe%', 'dy%', 'market cap', 'ev/ebitda', 'margem%']:
                    if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

                # Filtros inteligentes que ignoram P/L para FIIs
                mask = (df['p/vp'] <= pvp_max) & (df['p/vp'] > 0) & (df['dy%'] >= dy_min)
                
                df_final = df[mask].copy()
                
                # Filtro de Market Cap
                if mcap_sel == "> 1 bilhão": df_final = df_final[df_final['market cap'] >= 1e9]
                elif mcap_sel == "> 10 bilhões": df_final = df_final[df_final['market cap'] >= 10e9]
                elif mcap_sel == "> 100 bilhões": df_final = df_final[df_final['market cap'] >= 100e9]

                if df_final.empty: st.warning("nenhuma empresa sobreviveu aos filtros.")
                else:
                    df_final['score_rank'] = 0 
                    if "fórmula mágica" in estrategia:
                        df_final = df_final[(df_final['ev/ebitda'] > 0)].dropna(subset=['ev/ebitda'])
                        df_final['earnings yield'] = (1 / df_final['ev/ebitda']) * 100
                        df_final['roic proxy'] = df_final['roe%']
                        df_final = df_final.dropna(subset=['earnings yield', 'roic proxy'])
                        df_final['rank_ey'] = df_final['earnings yield'].rank(ascending=False)
                        df_final['rank_roic'] = df_final['roic proxy'].rank(ascending=False)
                        df_final['score_rank'] = df_final['rank_ey'] + df_final['rank_roic']
                        df_resultado = df_final.sort_values('score_rank', ascending=True).head(15).drop(columns=['rank_ey', 'rank_roic'])
                    elif "deep value" in estrategia:
                        df_final['score_rank'] = df_final['p/vp'].rank(ascending=True)
                        df_resultado = df_final.sort_values('score_rank', ascending=True).head(10)
                    elif "high yield" in estrategia:
                        df_final['score_rank'] = df_final['dy%'].rank(ascending=False)
                        df_resultado = df_final.sort_values('score_rank', ascending=True).head(10)

                    st.session_state['screener_top10'] = df_resultado
                    st.session_state['estrategia_usada'] = estrategia

    if 'screener_top10' in st.session_state and not st.session_state['screener_top10'].empty:
        df_res = st.session_state['screener_top10']
        estr_u = st.session_state['estrategia_usada']
        
        st.markdown(f"#### 🏆 top ativos detectados: {estr_u.lower()}")
        st.markdown("<br>", unsafe_allow_html=True)
        
        for idx, row in df_res.reset_index(drop=True).iterrows():
            cols = st.columns([1, 2, 3, 2, 1.5, 1.5, 1.5, 1.5, 2])
            with cols[0]:
                st.markdown(f"<div style='font-family: Courier New; font-weight: bold; color: #FF9900; padding-top: 8px;'>{idx+1}</div>", unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"<div style='font-family: Courier New; font-weight: bold; color: #FFFFFF; padding-top: 8px;'>{row['ticker']}</div>", unsafe_allow_html=True)
            with cols[2]:
                nome_trunc = str(row['nome'])[:20] + ('...' if len(str(row['nome'])) > 20 else '')
                st.markdown(f"<div style='font-size: 0.85rem; color: #555; padding-top: 8px;'>{nome_trunc}</div>", unsafe_allow_html=True)
            with cols[3]:
                st.markdown(f"<div style='padding-top: 8px; font-size: 0.85rem;'>{row['setor']}</div>", unsafe_allow_html=True)
            
            if "fórmula mágica" in estr_u:
                c4_label, c4_val = "EY", f"{row.get('earnings yield', 0):.1f}%"
                c5_label, c5_val = "ROIC", f"{row.get('roic proxy', 0):.1f}%"
            else:
                c4_label, c4_val = "P/L", f"{row.get('p/l', 0):.2f}"
                c5_label, c5_val = "ROE", f"{row.get('roe%', 0):.1f}%"
                
            c6_label, c6_val = "P/VP", f"{row.get('p/vp', 0):.2f}"
            c7_label, c7_val = "DY", f"{row.get('dy%', 0):.1f}%"

            with cols[4]: st.markdown(f"<div style='padding-top: 8px; font-size: 0.8rem;'><span style='color:#888'>{c4_label}:</span> {c4_val}</div>", unsafe_allow_html=True)
            with cols[5]: st.markdown(f"<div style='padding-top: 8px; font-size: 0.8rem;'><span style='color:#888'>{c5_label}:</span> {c5_val}</div>", unsafe_allow_html=True)
            with cols[6]: st.markdown(f"<div style='padding-top: 8px; font-size: 0.8rem;'><span style='color:#888'>{c6_label}:</span> {c6_val}</div>", unsafe_allow_html=True)
            with cols[7]: st.markdown(f"<div style='padding-top: 8px; font-size: 0.8rem;'><span style='color:#888'>{c7_label}:</span> {c7_val}</div>", unsafe_allow_html=True)
            with cols[8]:
                if st.button("＋ watchlist", key=f"btn_wl_scr_{row['ticker']}_{idx}", use_container_width=True):
                    modal_salvar_screener(row['ticker'], row['nome'], "brasil" if mapear_ticker_base(row['ticker']).endswith('.SA') else "eua")
            st.markdown("<hr style='border-top: 1px solid #1e1e1e; margin: 0.5rem 0;'>", unsafe_allow_html=True)