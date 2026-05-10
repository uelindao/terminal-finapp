import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from google import genai
from fredapi import Fred
from bcb import sgs
import logging

# silenciar alertas vermelhos do yahoo finance no terminal
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label, mapear_ticker_base
from database.db import listar_watchlists, listar_watchlist

# componentes do design system
from utils.components import page_header, section_title, metric_card, status_card, empty_state, inject_keyboard_shortcuts
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout

# 1. configuração da página
st.set_page_config(page_title="terminal finapp | research", layout="wide", page_icon="🔬")

# 2. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()

# ==========================================
# função do modo de comparação multi-ativo
# ==========================================
def _render_modo_comparacao():
    """modo de comparação de múltiplos ativos em cadeia."""
    st.markdown("##### selecione os ativos para comparar")

    col_orig, col_lista = st.columns([4, 6])

    with col_orig:
        origem = st.radio("origem dos ativos:", ["🔍 buscar manualmente", "📋 importar de watchlist"], key="comp_origem")

        if origem == "🔍 buscar manualmente":
            opcoes = get_opcoes_selectbox()
            sel_add = st.selectbox("ativo:", opcoes, key="comp_sel_add", label_visibility="collapsed", format_func=lambda x: x.lower())
            man_add = st.text_input("ou digite:", "", key="comp_man_add", placeholder="ex: wege3.sa").strip().upper()
            ticker_add = man_add if man_add else (ticker_from_label(sel_add) or "")

            if st.button("➕ adicionar", key="btn_add_comp", type="primary", use_container_width=True):
                if ticker_add and not ticker_add.startswith("─"):
                    lista = st.session_state.get('comp_lista', [])
                    if ticker_add not in lista:
                        lista.append(ticker_add)
                        st.session_state['comp_lista'] = lista
                        st.rerun()

        else:
            watchlists_disp = listar_watchlists()
            if watchlists_disp:
                opcoes_wl = {f"{wl['icone']} {wl['nome']}": wl['id'] for wl in watchlists_disp}
                sel_wl = st.selectbox("watchlist:", list(opcoes_wl.keys()), key="comp_wl_import")
                wl_id = opcoes_wl[sel_wl]

                if st.button("📥 importar todos", type="primary", use_container_width=True, key="btn_import_wl"):
                    ativos_wl = [item['ticker'] for item in listar_watchlist(wl_id)]
                    st.session_state['comp_lista'] = list(dict.fromkeys(st.session_state.get('comp_lista', []) + ativos_wl))
                    st.rerun()
            else:
                st.info("nenhuma watchlist encontrada.")

    with col_lista:
        comp_lista = st.session_state.get('comp_lista', [])

        if comp_lista:
            st.markdown(f"**{len(comp_lista)} ativos selecionados:**")

            cols_tags = st.columns(min(len(comp_lista), 4) or 1)
            for i, t in enumerate(comp_lista):
                with cols_tags[i % 4]:
                    st.markdown(
                        f'<div style="background:#1a0f00; border:1px solid #FF9900; border-radius:4px; padding:4px 8px; margin:2px; font-family:Courier New; font-size:0.8rem; display:flex; justify-content:space-between;">'
                        f'<span style="color:#FF9900;">{t.lower()}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    if st.button("✕", key=f"rm_comp_{t}", help=f"remover {t.lower()}"):
                        comp_lista.remove(t)
                        st.session_state['comp_lista'] = comp_lista
                        st.rerun()

            if st.button("🧹 limpar tudo", key="btn_limpar_comp"):
                st.session_state['comp_lista'] = []
                st.rerun()
        else:
            st.info("adicione ativos ao lado para começar a comparação.")

    if len(comp_lista) < 2:
        st.info("adicione pelo menos 2 ativos para comparar.")
        return

    st.markdown("---")
    section_title("📊 tabela comparativa de múltiplos")

    with st.spinner(f"a carregar dados de {len(comp_lista)} ativos..."):
        dados_comp = []
        for t in comp_lista:
            t_base = mapear_ticker_base(t)
            try:
                acao = yf.Ticker(t_base)
                info = acao.info
                moeda = "r$" if t_base.endswith('.SA') else "$"
                preco = info.get('currentPrice', info.get('regularMarketPrice', 0))
                
                if t_base.endswith('.SA'):
                    from utils.scrapers import buscar_dados_b3
                    f_dados = buscar_dados_b3(t_base)
                    nome = f_dados['nome'] if f_dados['nome'] != '—' else info.get('shortName', t).lower()
                    setor_raw = f_dados['setor']
                    pl = f_dados['p/l']
                    pvp = f_dados['p/vp']
                    ev_ebitda = f_dados['ev/ebitda']
                    roe = f_dados['roe%']
                    margem = f_dados['margem%']
                    dy = f_dados['dy%']
                    beta = info.get('beta', None)
                else:
                    nome = info.get('shortName', t)[:20].lower()
                    setor_raw = info.get('sector', '—')
                    pl = info.get('trailingPE', None)
                    pvp = info.get('priceToBook', None)
                    ev_ebitda = info.get('enterpriseToEbitda', None)
                    roe_r = info.get('returnOnEquity', None)
                    roe = roe_r * 100 if roe_r else None
                    marg_r = info.get('profitMargins', None)
                    margem = marg_r * 100 if marg_r else None
                    dy_r = info.get('dividendYield', None)
                    dy = dy_r * 100 if dy_r else None
                    beta = info.get('beta', None)

                dados_comp.append({
                    'ticker': t,
                    'nome': nome,
                    'setor': setor_raw[:15].lower() if setor_raw != '—' else '—',
                    'preço': f"{moeda} {preco:,.2f}",
                    'p/l': pl,
                    'p/vp': pvp,
                    'ev/ebitda': ev_ebitda,
                    'roe%': roe,
                    'margem%': margem,
                    'dy%': dy,
                    'beta': beta,
                })
            except:
                dados_comp.append({'ticker': t, 'nome': t.lower(), 'setor': '—'})

    df_comp = pd.DataFrame(dados_comp)

    colunas_num = ['p/l', 'p/vp', 'ev/ebitda', 'roe%', 'margem%', 'dy%', 'beta']
    colunas_menor_melhor = ['p/l', 'p/vp', 'ev/ebitda', 'beta']

    def colorir_quartil(s):
        if s.name not in colunas_num: return [''] * len(s)
        valores = pd.to_numeric(s, errors='coerce')
        resultado = []
        for v in valores:
            if pd.isna(v):
                resultado.append('')
                continue
            q25, q75 = valores.quantile(0.25), valores.quantile(0.75)
            if s.name in colunas_menor_melhor:
                if v <= q25: resultado.append('background-color:#001a0d; color:#00C853; font-weight: bold;')
                elif v >= q75: resultado.append('background-color:#1a0005; color:#FF1744; font-weight: bold;')
                else: resultado.append('')
            else:
                if v >= q75: resultado.append('background-color:#001a0d; color:#00C853; font-weight: bold;')
                elif v <= q25: resultado.append('background-color:#1a0005; color:#FF1744; font-weight: bold;')
                else: resultado.append('')
        return resultado

    st.dataframe(
        df_comp.style.apply(colorir_quartil, axis=0).format({
            'p/l': '{:.2f}', 'p/vp': '{:.2f}', 'ev/ebitda': '{:.2f}',
            'roe%': '{:.1f}%', 'margem%': '{:.1f}%', 'dy%': '{:.1f}%', 'beta': '{:.2f}',
        }, na_rep='n/d'),
        use_container_width=True, hide_index=True
    )

    section_title("📈 performance histórica (base 100)")
    periodo_comp = st.selectbox("período:", ["3mo", "6mo", "1y", "2y", "5y"], index=2, key="comp_periodo")
    
    with st.spinner("sincronizando cotações históricas..."):
        tickers_base = list(set([mapear_ticker_base(t) for t in comp_lista]))
        hist_data = yf.download(tickers_base, period=periodo_comp, auto_adjust=True, progress=False)['Close']
        
        if isinstance(hist_data, pd.Series): 
            hist_data = hist_data.to_frame(name=tickers_base[0])
            
        if isinstance(hist_data.columns, pd.MultiIndex): 
            hist_data.columns = hist_data.columns.get_level_values(1)

        hist_data = hist_data.dropna(how='all').ffill()
        if hist_data.index.tz is not None: hist_data.index = hist_data.index.tz_localize(None)

        df_precos_exibicao = pd.DataFrame(index=hist_data.index)
        for t in comp_lista:
            t_base = mapear_ticker_base(t)
            if t_base in hist_data.columns:
                df_precos_exibicao[t] = hist_data[t_base]

        if not df_precos_exibicao.empty:
            primeiro_preco = df_precos_exibicao.bfill().iloc[0]
            df_norm = (df_precos_exibicao / primeiro_preco) * 100

            fig = go.Figure()
            cores_backtest = ["#FF9900", "#00B0FF", "#00C853", "#FF1744", "#E040FB", "#00BCD4", "#FFEB3B"]
            for i, col in enumerate(df_norm.columns):
                retorno_total = df_norm[col].iloc[-1] - 100
                cor_linha = cores_backtest[i % len(cores_backtest)]
                fig.add_trace(go.Scatter(x=df_norm.index, y=df_norm[col], name=f"{col.lower()} ({retorno_total:+.2f}%)", mode='lines', line=dict(width=2, color=cor_linha)))

            layout_bt = base_layout(height=450)
            fig.update_layout(**layout_bt)
            fig.add_hline(y=100, line_dash="dash", line_color="#333", opacity=0.8)
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# header e fluxo principal
# ==========================================
page_header("🔬 terminal de análise — research", "análise 360º de ativos: fundamentos, técnica, resultados, sentimento e correlação macro.")
st.markdown("---")

modo = st.radio("modo:", ["📊 análise individual", "⚖️ comparar múltiplos ativos"], horizontal=True, key="research_modo")

if modo == "📊 análise individual":
    col_sel, col_man, col_periodo = st.columns([4, 2, 2])
    with col_sel:
        ticker_externo = st.session_state.pop('research_ticker_externo', None)
        opcoes = get_opcoes_selectbox()
        selecao = st.selectbox("ativo:", opcoes, key="research_sel", label_visibility="collapsed", format_func=lambda x: x.lower())
    with col_man:
        ticker_manual = st.text_input("ou digite o ticker:", ticker_externo or "", key="research_manual", placeholder="ex: petr4.sa").strip().upper()
    with col_periodo:
        periodo = st.selectbox("período p/ gráficos:", ["3mo", "6mo", "1y", "2y", "5y"], index=2, label_visibility="collapsed")

    ticker = ticker_manual if ticker_manual else (ticker_from_label(selecao) or "")

    if not ticker or ticker.startswith("─"):
        empty_state(icone="🔍", titulo="nenhum ativo selecionado", descricao="utilize a barra de pesquisa acima para selecionar uma empresa e iniciar a análise profunda.")
        st.stop()

    t_base = mapear_ticker_base(ticker)

    if "research_ticker" not in st.session_state or st.session_state.research_ticker != ticker:
        with st.spinner(f"sincronizando banco de dados global para {ticker.lower()}..."):
            try:
                acao = yf.Ticker(t_base)
                st.session_state.research_info = acao.info
                st.session_state.research_news = acao.news or []
                st.session_state.research_acao = acao
                st.session_state.research_ticker = ticker
                st.session_state.research_t_base = t_base
            except Exception as e:
                st.error(f"erro ao carregar os dados iniciais do ativo: {e}")
                st.stop()

    info = st.session_state.research_info
    noticias = st.session_state.research_news
    acao = st.session_state.research_acao
    t_base = st.session_state.research_t_base

    preco = info.get('currentPrice', info.get('regularMarketPrice', 0))
    moeda = "r$" if t_base.endswith('.SA') else "$"
    
    if t_base.endswith('.SA'):
        from utils.scrapers import buscar_dados_b3
        f_dados = buscar_dados_b3(t_base)
        nome = f_dados['nome'] if f_dados['nome'] != '—' else info.get('shortName', ticker)
        setor = f_dados['setor']
    else:
        nome = info.get('shortName', ticker)
        setor = info.get('sector', 'desconhecido')

    st.markdown(f"**empresa:** {nome.lower()} | **setor:** {setor.lower()} | **preço atual:** {fmt_preco(preco, moeda)}")
    st.markdown("<br>", unsafe_allow_html=True)

    tab_fund, tab_tec, tab_earn, tab_sent, tab_overlay = st.tabs(["📊 fundamentos", "📈 técnica", "📋 earnings", "📰 sentimento", "🔭 overlay macro"])

    with tab_fund:
        if t_base.endswith('.SA'):
            pl = f_dados['p/l'] if f_dados['p/l'] is not None else np.nan
            pvp = f_dados['p/vp'] if f_dados['p/vp'] is not None else np.nan
            roe = f_dados['roe%'] if f_dados['roe%'] is not None else np.nan
            dy = f_dados['dy%'] if f_dados['dy%'] is not None else 0
        else:
            pl = info.get('trailingPE', info.get('forwardPE', np.nan))
            pvp = info.get('priceToBook', np.nan)
            roe_raw = info.get('returnOnEquity', None)
            roe = roe_raw * 100 if roe_raw is not None else np.nan
            dy = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0

        section_title("métricas chave")
        c1, c2, c3, c4 = st.columns(4)
        with c1: metric_card("p/l (preço / lucro)", fmt_numero(pl))
        with c2: metric_card("p/vp (preço / vpa)", fmt_numero(pvp))
        with c3: metric_card("roe (retorno s/ pl)", fmt_pct(roe, sinal=False))
        with c4: metric_card("dividend yield", fmt_pct(dy, sinal=False))

        st.markdown("---")
        section_title("benchmark setorial (comparativo de pares)")
        
        peers_por_setor = {
            "Energy": ["PETR4.SA", "PRIO3.SA", "CSAN3.SA", "XOM", "CVX"],
            "Financial Services": ["ITUB4.SA", "BBAS3.SA", "BBDC4.SA", "JPM", "BAC"],
            "Basic Materials": ["VALE3.SA", "GGBR4.SA", "RIO", "BHP"],
            "Technology": ["AAPL", "MSFT", "NVDA", "GOOGL"],
            "Consumer Defensive": ["ABEV3.SA", "KO", "PEP", "WMT", "PG"],
            "Industrials": ["WEGE3.SA", "RENT3.SA", "GE", "MMM", "HON"],
            "Consumer Cyclical": ["AMZN", "TSLA", "LREN3.SA", "MGLU3.SA", "HD"],
            "Healthcare": ["JNJ", "UNH", "LLY", "RADL3.SA", "HAPV3.SA"],
            "Utilities": ["EGIE3.SA", "EQTL3.SA", "TAEE11.SA", "SBSP3.SA"],
            "Communication Services": ["META", "NFLX", "VIVT3.SA", "CMCSA"],
            "Real Estate": ["AMT", "PLD", "SPG", "MULT3.SA", "IGTI11.SA"]
        }

        # usando o sector bruto original do yahoo para manter a compatibilidade com o mapa de pares
        sector_raw = info.get('sector', '')
        if sector_raw in peers_por_setor:
            peers = peers_por_setor[sector_raw]
            if t_base not in peers: peers.append(t_base)
                
            dados_setor = []
            for p in peers:
                try:
                    if p.endswith('.SA'):
                        from utils.scrapers import buscar_dados_b3
                        f_peer = buscar_dados_b3(p)
                        p_pl = f_peer['p/l'] if f_peer['p/l'] is not None else np.nan
                        p_roe = f_peer['roe%'] if f_peer['roe%'] is not None else 0
                        p_dy = f_peer['dy%'] if f_peer['dy%'] is not None else 0
                    else:
                        p_info = yf.Ticker(p).info
                        p_pl = p_info.get('trailingPE', p_info.get('forwardPE', np.nan))
                        p_roe = (p_info.get('returnOnEquity', 0) or 0) * 100
                        p_dy = (p_info.get('dividendYield', 0) or 0) * 100
                    
                    dados_setor.append({'ticker': p, 'p/l': p_pl, 'roe': p_roe, 'dy': p_dy})
                except: pass
                    
            df_setor = pd.DataFrame(dados_setor)
            if not df_setor.empty:
                media_pl, mediana_pl = df_setor['p/l'].mean(), df_setor['p/l'].median()
                media_roe, mediana_roe = df_setor['roe'].mean(), df_setor['roe'].median()
                media_dy, mediana_dy = df_setor['dy'].mean(), df_setor['dy'].median()

                df_display = pd.DataFrame({
                    "múltiplo": ["p/l", "roe", "dy"],
                    f"{ticker.lower()}": [pl, roe, dy],
                    "mediana setor": [mediana_pl, mediana_roe, mediana_dy]
                })
                
                def colorir_comparacao(row):
                    estilos = [''] * len(row)
                    m = row['múltiplo']
                    val = row[ticker.lower()]
                    med = row['mediana setor']
                    if pd.isna(val) or pd.isna(med): return estilos
                    if m == "p/l": cor = 'color: #00C853; font-weight: bold' if val < med else 'color: #FF1744; font-weight: bold'
                    else: cor = 'color: #00C853; font-weight: bold' if val > med else 'color: #FF1744; font-weight: bold'
                    estilos[1] = cor
                    return estilos
                
                st.dataframe(df_display.style.apply(colorir_comparacao, axis=1).format({f"{ticker.lower()}": "{:.2f}", "mediana setor": "{:.2f}"}), use_container_width=True, hide_index=True)
                st.caption(f"amostra de pares analisada: {', '.join(peers).lower()}")
        else: st.info("setor sem pares mapeados para benchmark.")

        st.markdown("---")
        with st.expander("🧮 dcf simplificado — valor intrínseco estimado", expanded=False):
            try:
                fcf_series = acao.cashflow.loc['Free Cash Flow'].dropna()
                fcf_atual  = fcf_series.iloc[0] if not fcf_series.empty else None
            except:
                fcf_atual = info.get('freeCashflow', None)
            shares = info.get('sharesOutstanding', None)

            if fcf_atual and shares and fcf_atual > 0:
                c1, c2, c3 = st.columns(3)
                with c1: g_pes = st.slider("crescimento pessimista %/ano", 0.0, 30.0, 5.0, 0.5)
                with c2: g_base = st.slider("crescimento base %/ano", 0.0, 30.0, 10.0, 0.5)
                with c3: wacc = st.slider("taxa de desconto (wacc) %", 5.0, 20.0, 10.0, 0.5)
                
                def calcular_dcf(fcf, g, w, n, s):
                    w_d, g_d, fluxos = w/100, g/100, []
                    g_p = min(g_d * 0.3, 0.03)
                    for t in range(1, n + 1): fluxos.append(fcf * (1 + g_d)**t / (1 + w_d)**t)
                    v_term = (fcf * (1 + g_d)**n * (1 + g_p)) / ((w_d - g_p) * (1 + w_d)**n)
                    return (sum(fluxos) + v_term) / s

                vp = calcular_dcf(fcf_atual, g_pes, wacc, 5, shares)
                vb = calcular_dcf(fcf_atual, g_base, wacc, 5, shares)
                vo = calcular_dcf(fcf_atual, g_base+5, wacc, 5, shares)

                m1, m2, m3, m4 = st.columns(4)
                with m1: metric_card("pessimista", fmt_preco(vp, moeda))
                with m2: metric_card("base", fmt_preco(vb, moeda))
                with m3: metric_card("otimista", fmt_preco(vo, moeda))
                
                delta_pct = ((preco/vb)-1)*100
                cor_d = "bull" if preco < vb else "bear"
                with m4: metric_card("preço atual", fmt_preco(preco, moeda), f"{fmt_pct(delta_pct)} vs base", cor_delta=cor_d)

            else:
                st.warning("fluxo de caixa livre indisponível para o modelo dcf.")

        st.markdown("---")
        if st.button("🧠 gerar síntese fundamentalista (ia)", type="primary"):
            with st.spinner("processando..."):
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    prompt = f"empresa: {ticker}. p/l: {pl:.2f}, roe: {roe:.2f}%, dy: {dy:.2f}%. resuma (3 tópicos): fosso competitivo, valuation frio e riscos. inicie todas as frases e tópicos com letra minúscula. essa é a forma da nossa escrita."
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    status_card("síntese ia", resp.text, "info")
                except Exception as e: st.error(f"erro na ia: {e}")

    with tab_tec:
        c1, c2, c3 = st.columns(3)
        with c1: show_sma50 = st.checkbox("sma 50", value=True)
        with c2: show_sma200 = st.checkbox("sma 200", value=True)
        with c3: show_bb = st.checkbox("bollinger bands", value=True)

        with st.spinner("desenhando gráficos..."):
            try:
                df = acao.history(period=periodo)
                if not df.empty:
                    if hasattr(df.index, 'tz') and df.index.tz is not None: df.index = df.index.tz_localize(None)
                    
                    df['SMA50'] = df['Close'].rolling(50).mean()
                    df['SMA200'] = df['Close'].rolling(200).mean()
                    delta = df['Close'].diff()
                    df['RSI'] = 100 - (100 / (1 + (delta.clip(lower=0).rolling(14).mean() / (-delta.clip(upper=0)).rolling(14).mean())))
                    df['BB_mid'] = df['Close'].rolling(20).mean()
                    df['BB_std'] = df['Close'].rolling(20).std()
                    df['BB_up'], df['BB_dn'] = df['BB_mid'] + 2*df['BB_std'], df['BB_mid'] - 2*df['BB_std']

                    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.04)
                    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='preço'), row=1, col=1)
                    
                    if show_sma50: fig.add_trace(go.Scatter(x=df.index, y=df['SMA50'], line=dict(color='#00FFFF'), name='sma 50'), row=1, col=1)
                    if show_sma200: fig.add_trace(go.Scatter(x=df.index, y=df['SMA200'], line=dict(color='#FF00FF'), name='sma 200'), row=1, col=1)
                    if show_bb:
                        fig.add_trace(go.Scatter(x=df.index, y=df['BB_up'], line=dict(color='#FF9900', dash='dot'), name='bb up'), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=df['BB_dn'], line=dict(color='#FF9900', dash='dot'), fill='tonexty', fillcolor='rgba(255,153,0,0.05)', name='bb dn'), row=1, col=1)

                    cores_vol = ['#00C853' if c >= o else '#FF1744' for c, o in zip(df['Close'], df['Open'])]
                    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=cores_vol, name='volume'), row=2, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#E0E0E0'), name='rsi'), row=3, col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="#FF1744", row=3, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="#00C853", row=3, col=1)

                    layout_custom = base_layout(height=700)
                    layout_custom["xaxis_rangeslider_visible"] = False
                    fig.update_layout(**layout_custom)
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    if st.button("🤖 analisar setup com ia"):
                        with st.spinner("analisando..."):
                            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                            p = f"analise {ticker} graficamente. preço: {preco:.2f}, sma50: {df['SMA50'].iloc[-1]:.2f}, sma200: {df['SMA200'].iloc[-1]:.2f}, rsi: {df['RSI'].iloc[-1]:.1f}. resuma: 1. tendência, 2. momentum, 3. tática. inicie todas as frases e tópicos com letra minúscula. essa é a forma da nossa escrita."
                            r = client.models.generate_content(model='gemini-2.5-flash', contents=p)
                            status_card("síntese gráfica", r.text, "info")
            except Exception as e:
                st.error(f"erro ao plotar: {e}")

    with tab_earn:
        section_title("⏳ próximo resultado & surpresas")
        try:
            def extract_date(cal):
                if isinstance(cal, pd.DataFrame) and 'Earnings Date' in cal.index: return pd.Timestamp(cal.loc['Earnings Date'].iloc[0])
                if isinstance(cal, dict) and cal.get('earningsDate'): return pd.Timestamp(cal['earningsDate'][0])
                return None
                
            data_e = extract_date(acao.calendar)
            if data_e:
                hoje = pd.Timestamp.now().normalize()
                dias_restantes = (pd.Timestamp(data_e).normalize() - hoje).days
                m1, m2 = st.columns(2)
                with m1: metric_card("data prevista", data_e.strftime('%d/%m/%Y'))
                with m2: metric_card("contagem", f"{dias_restantes} dias", cor_delta="info")
            else: st.info("💡 calendário futuro indisponível no yahoo finance para este ativo.")
            
            hist_s = acao.earnings_history
            if hist_s is not None and not hist_s.empty:
                df_s = hist_s.head(8).copy()
                if 'Reported EPS' in df_s.columns and 'EPS Estimate' in df_s.columns:
                    df_s['surpresa %'] = ((df_s['Reported EPS'] - df_s['EPS Estimate']) / df_s['EPS Estimate'].abs()) * 100
                    fig_s = go.Figure(go.Bar(x=df_s.index.astype(str), y=df_s['surpresa %'], marker_color=['#00C853' if x>0 else '#FF1744' for x in df_s['surpresa %']]))
                    fig_s.update_layout(**base_layout(height=300))
                    st.plotly_chart(fig_s, use_container_width=True)
                else: st.info("💡 dados de histórico de surpresas (eps) incompletos.")
            else: st.info("💡 histórico de surpresas (eps) não fornecido pelo provedor para este ativo.")
        except Exception: st.info("💡 dados de calendário e surpresas indisponíveis.")

        st.markdown("---")
        section_title("📊 evolução trimestral")
        try:
            q_fin = acao.quarterly_financials.T
            if not q_fin.empty and 'Total Revenue' in q_fin.columns and 'Net Income' in q_fin.columns:
                q_fin = q_fin.sort_index()
                rev = q_fin['Total Revenue'].dropna()
                net_inc = q_fin['Net Income'].dropna()
                fig_fin = make_subplots(specs=[[{"secondary_y": True}]])
                fig_fin.add_trace(go.Bar(x=rev.index.astype(str), y=rev, name="receita total", marker_color="#FF9900"), secondary_y=False)
                fig_fin.add_trace(go.Scatter(x=net_inc.index.astype(str), y=net_inc, name="lucro líquido", line=dict(color="#00B0FF", width=3)), secondary_y=True)
                layout_fin = base_layout(height=400)
                fig_fin.update_layout(**layout_fin)
                st.plotly_chart(fig_fin, use_container_width=True)
            else: st.info("💡 os demonstrativos trimestrais estão incompletos no provedor para este ativo.")
        except Exception: st.info("💡 falha ao processar balanços trimestrais.")

    with tab_sent:
        section_title("📰 raw news feed")
        if noticias:
            manchetes = []
            for n in noticias[:10]:
                c = n.get('content', n)
                t = c.get('title', c.get('headline', ''))
                if t: manchetes.append(f"- {t.lower()}")
            txt = "\n".join(manchetes)
            st.code(txt, language="text")
            if st.button("analisar humor com ia", type="primary"):
                with st.spinner("lendo manchetes..."):
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        r = client.models.generate_content(model='gemini-2.5-flash', contents=f"resuma o sentimento geral de {ticker} com base nestas manchetes:\n{txt}. inicie todas as frases e tópicos com letra minúscula. essa é a forma da nossa escrita.")
                        status_card("diagnóstico de sentimento", r.text, "info")
                    except Exception as e: st.error(e)
        else: empty_state("🗞️", "sem notícias", "não foram encontradas manchetes recentes nos indexadores do yahoo finance para este ativo.")

    with tab_overlay:
        section_title("🔭 correlação macroeconômica")
        ind_macro = st.selectbox("selecione o indicador:", ["taxa selic (br)", "ipca (br)", "fed funds (eua)", "treasury 10y", "vix"])
        if st.button("gerar overlay", use_container_width=True):
            with st.spinner("buscando séries..."):
                try:
                    stk = acao.history(period="5y")['Close'].dropna()
                    if hasattr(stk.index, 'tz') and stk.index.tz is not None: stk.index = stk.index.tz_localize(None)
                    inicio = datetime.datetime.today() - datetime.timedelta(days=5*365)
                    m_data, m_name = None, ""
                    if "selic" in ind_macro.lower(): m_data, m_name = sgs.get({'selic': 432}, start=inicio)['selic'], "selic (%)"
                    elif "ipca" in ind_macro.lower(): m_data, m_name = sgs.get({'ipca': 433}, start=inicio)['ipca'], "ipca (%)"
                    else:
                        fred = Fred(api_key=st.secrets["FRED_API_KEY"])
                        if "fed funds" in ind_macro.lower(): m_data, m_name = fred.get_series('FEDFUNDS', observation_start=inicio), "fed funds (%)"
                        elif "treasury" in ind_macro.lower(): m_data, m_name = fred.get_series('DGS10', observation_start=inicio), "treasury 10y (%)"
                        elif "vix" in ind_macro.lower(): m_data, m_name = fred.get_series('VIXCLS', observation_start=inicio), "vix"
                    if m_data is not None:
                        m_data = m_data.dropna()
                        if hasattr(m_data.index, 'tz') and m_data.index.tz is not None: m_data.index = m_data.index.tz_localize(None)
                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        fig.add_trace(go.Scatter(x=stk.index, y=stk, name=ticker.lower(), line=dict(color="#FF9900")), secondary_y=False)
                        fig.add_trace(go.Scatter(x=m_data.index, y=m_data, name=m_name, line=dict(color="#00B0FF", dash="dot")), secondary_y=True)
                        layout_macro = base_layout(height=450)
                        fig.update_layout(**layout_macro)
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e: st.error(f"erro: {e}")
else:
    _render_modo_comparacao()