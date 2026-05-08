import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from fredapi import Fred
from bcb import sgs
from google import genai
from scipy.stats import spearmanr
import datetime

# Importa dependências do projeto e o novo catálogo central
from utils.style import aplicar_tema
from database.db import (
    init_db, listar_watchlist, listar_alertas,
    get_cache_ia, salvar_cache_ia, get_connection
)
from utils.tickers import get_opcoes_selectbox, ticker_from_label

# --- Configuração da Página ---
st.set_page_config(
    page_title="FinTerminal | Super Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="⚡"
)

# Inicializa banco e tema
init_db()
aplicar_tema()

# --- CSS Extra Específico do Dashboard ---
st.markdown("""
<style>
.dash-card {
    background-color: #0d0d0d;
    border: 1px solid #222222;
    border-top: 2px solid #FF9900;
    border-radius: 6px;
    padding: 16px;
    margin-bottom: 12px;
}
.badge-verde  { background:#003300; color:#00FF00; padding:2px 8px; border-radius:3px; font-size:0.75rem; font-family:'Courier New'; }
.badge-vermelho { background:#330000; color:#FF0000; padding:2px 8px; border-radius:3px; font-size:0.75rem; font-family:'Courier New'; }
.badge-ambar  { background:#332200; color:#FF9900; padding:2px 8px; border-radius:3px; font-size:0.75rem; font-family:'Courier New'; }
.secao-titulo {
    font-family: 'Courier New', monospace;
    color: #FF9900;
    font-size: 0.85rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    border-bottom: 1px solid #222;
    padding-bottom: 4px;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# CABEÇALHO E SELETOR DE MODO
# ==========================================
st.markdown("### ⚡ SUPER DASHBOARD — FINTERMINAL")

col_modo, col_info = st.columns([4, 8])
with col_modo:
    modo = st.radio(
        "MODO DE VISUALIZAÇÃO:",
        ["🌐 Visão de Mercado", "🔬 Visão de Ativo"],
        horizontal=True,
        label_visibility="collapsed"
    )

with col_info:
    st.caption(f"⏱ Atualizado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')} — Dados via YFinance, BCB, FRED")

st.markdown("---")

# ==========================================
# MODO 1 — VISÃO DE MERCADO
# ==========================================
if "Mercado" in modo:

    # ------------------------------------------
    # SEÇÃO 1.1 — STATUS GLOBAL DOS ÍNDICES
    # ------------------------------------------
    with st.expander("📊 ÍNDICES GLOBAIS", expanded=True):
        try:
            @st.cache_data(ttl=300, show_spinner=False)
            def buscar_indices_globais():
                INDICES = {
                    "IBOVESPA":  ("^BVSP",   "🇧🇷"),
                    "S&P 500":   ("^GSPC",   "🇺🇸"),
                    "NASDAQ":    ("^IXIC",   "🇺🇸"),
                    "FTSE 100":  ("^FTSE",   "🇬🇧"),
                    "DAX":       ("^GDAXI",  "🇩🇪"),
                    "NIKKEI":    ("^N225",   "🇯🇵"),
                    "HANG SENG": ("^HSI",    "🇭🇰"),
                    "BTC/USD":   ("BTC-USD", "₿"),
                    "OURO":      ("GC=F",    "🥇"),
                    "PETRÓLEO":  ("CL=F",    "🛢️"),
                    "DXY":       ("DX-Y.NYB","💵"),
                    "VIX":       ("^VIX",    "😰"),
                }
                resultados = {}
                for nome, (ticker, emoji) in INDICES.items():
                    try:
                        hist = yf.Ticker(ticker).history(period="5d")
                        hist = hist.dropna(subset=['Close'])
                        if len(hist) >= 2:
                            preco = hist['Close'].iloc[-1]
                            anterior = hist['Close'].iloc[-2]
                            var = ((preco / anterior) - 1) * 100
                            resultados[nome] = {
                                "preco": preco, "var": var,
                                "emoji": emoji, "ticker": ticker
                            }
                    except:
                        pass
                return resultados

            indices = buscar_indices_globais()

            cols = st.columns(6)
            for i, (nome, dados) in enumerate(indices.items()):
                cor = "#00FF00" if dados['var'] >= 0 else "#FF0000"
                sinal = "▲" if dados['var'] >= 0 else "▼"
                formato_preco = f"{dados['preco']:,.0f}" if dados['preco'] > 10000 and "BTC" in nome else f"{dados['preco']:,.2f}"
                
                html_card = (
                    f"<div class='dash-card' style='text-align:center; padding:10px;'>"
                    f"<div style='font-size:1.4rem;'>{dados['emoji']}</div>"
                    f"<div style='color:#888; font-size:0.7rem; font-family:\"Courier New\";'>{nome}</div>"
                    f"<div style='color:#FFF; font-size:1.1rem; font-weight:bold; font-family:\"Courier New\";'>{formato_preco}</div>"
                    f"<div style='color:{cor}; font-size:0.85rem; font-family:\"Courier New\";'>{sinal} {abs(dados['var']):.2f}%</div>"
                    f"</div>"
                )
                with cols[i % 6]:
                    st.markdown(html_card, unsafe_allow_html=True)
        except Exception as e:
            st.warning(f"Não foi possível carregar os índices: {e}")

    # ------------------------------------------
    # SEÇÃO 1.2 — RADAR MACRO GLOBAL
    # ------------------------------------------
    with st.expander("🌍 RADAR MACROECONÔMICO", expanded=True):
        try:
            @st.cache_data(ttl=3600, show_spinner=False)
            def buscar_macro_resumo():
                hoje = datetime.datetime.today()
                inicio = hoje - datetime.timedelta(days=365)
                resultado = {}
                try:
                    df_br = sgs.get({'Selic': 432, 'IPCA': 433, 'Dolar': 1}, start=inicio)
                    resultado['selic']  = df_br['Selic'].dropna().iloc[-1]
                    resultado['ipca']   = df_br['IPCA'].dropna().iloc[-1]
                    resultado['dolar']  = df_br['Dolar'].dropna().iloc[-1]
                except:
                    resultado['selic'] = resultado['ipca'] = resultado['dolar'] = None
                if "FRED_API_KEY" in st.secrets:
                    try:
                        fred = Fred(api_key=st.secrets["FRED_API_KEY"])
                        for key, serie in [('fed_funds','FEDFUNDS'), ('treasury10','DGS10'), ('vix','VIXCLS'), ('ecb','ECBDFR')]:
                            try:
                                s = fred.get_series(serie, observation_start=inicio)
                                resultado[key] = s.dropna().iloc[-1]
                            except: resultado[key] = None
                    except: pass
                return resultado

            macro = buscar_macro_resumo()
            col_br, col_us, col_eu, col_risco = st.columns(4)
            with col_br:
                st.markdown('<div class="secao-titulo">🇧🇷 BRASIL</div>', unsafe_allow_html=True)
                st.metric("SELIC", f"{macro.get('selic',0):.2f}%" if macro.get('selic') else "N/D")
                st.metric("IPCA", f"{macro.get('ipca',0):.2f}%" if macro.get('ipca') else "N/D")
                st.metric("USD/BRL", f"R$ {macro.get('dolar',0):.2f}" if macro.get('dolar') else "N/D")
            with col_us:
                st.markdown('<div class="secao-titulo">🇺🇸 EUA</div>', unsafe_allow_html=True)
                st.metric("FED FUNDS", f"{macro.get('fed_funds',0):.2f}%" if macro.get('fed_funds') else "N/D")
                st.metric("TREASURY 10Y", f"{macro.get('treasury10',0):.2f}%" if macro.get('treasury10') else "N/D")
            with col_eu:
                st.markdown('<div class="secao-titulo">🇪🇺 EUROPA</div>', unsafe_allow_html=True)
                st.metric("BCE RATE", f"{macro.get('ecb',0):.2f}%" if macro.get('ecb') else "N/D")
            with col_risco:
                st.markdown('<div class="secao-titulo">🌡️ RISCO</div>', unsafe_allow_html=True)
                vix = macro.get('vix', 0)
                if vix:
                    nivel = "PÂNICO" if vix > 30 else ("ALERTA" if vix > 20 else "CALMO")
                    st.metric("VIX", f"{vix:.1f}")
                    st.markdown(f'<span class="badge-{"vermelho" if vix>30 else ("ambar" if vix>20 else "verde")}">{nivel}</span>', unsafe_allow_html=True)
        except Exception as e:
            st.warning(f"Erro ao carregar dados macro: {e}")

    # ------------------------------------------
    # SEÇÃO 1.3 — MINHA WATCHLIST
    # ------------------------------------------
    with st.expander("⭐ WATCHLIST — RADAR ATUAL", expanded=True):
        try:
            watchlist = listar_watchlist()
            alertas_db = listar_alertas()
            if not watchlist:
                st.info("Watchlist vazia. Adicione ativos na página Watchlist.")
            else:
                @st.cache_data(ttl=180, show_spinner=False)
                def buscar_cotacoes_watchlist(tickers_tuple):
                    dados = {}
                    for t in tickers_tuple:
                        try:
                            hist = yf.Ticker(t).history(period="5d").dropna()
                            if len(hist) >= 2:
                                preco = hist['Close'].iloc[-1]
                                anterior = hist['Close'].iloc[-2]
                                var_1d = ((preco / anterior) - 1) * 100
                            else: preco = var_1d = 0
                            dados[t] = {"preco": preco, "var_1d": var_1d}
                        except: dados[t] = {"preco": 0, "var_1d": 0}
                    return dados
                tickers_tuple = tuple(item['ticker'] for item in watchlist)
                cotacoes = buscar_cotacoes_watchlist(tickers_tuple)
                alertas_por_ticker = {a['ticker']: a for a in alertas_db if a['disparado_em'] is not None}
                cols = st.columns(4)
                for idx, item in enumerate(watchlist):
                    t = item['ticker']
                    d = cotacoes.get(t, {"preco": 0, "var_1d": 0})
                    tem_alerta = t in alertas_por_ticker
                    cor_var = "#00FF00" if d['var_1d'] >= 0 else "#FF0000"
                    sinal = "▲" if d['var_1d'] >= 0 else "▼"
                    badge = '<span class="badge-vermelho">⚠ ALERTA</span>' if tem_alerta else ""
                    moeda = "R$" if t.endswith(".SA") else "$"
                    html_card = (f"<div class='dash-card'><div style='display:flex; justify-content:space-between; align-items:center;'><span style='color:#FF9900; font-family:\"Courier New\"; font-weight:bold; font-size:1rem;'>{t}</span>{badge}</div>"
                                 f"<div style='color:#888; font-size:0.75rem; font-family:\"Courier New\"; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>{item.get('nome','')}</div>"
                                 f"<div style='color:#FFF; font-size:1.4rem; font-weight:bold; font-family:\"Courier New\"; margin-top:4px;'>{moeda} {d['preco']:.2f}</div>"
                                 f"<div style='color:{cor_var}; font-size:0.9rem; font-family:\"Courier New\";'>{sinal} {abs(d['var_1d']):.2f}% hoje</div></div>")
                    with cols[idx % 4]: st.markdown(html_card, unsafe_allow_html=True)
        except Exception as e: st.warning(f"Erro ao carregar watchlist: {e}")

    # ------------------------------------------
    # SEÇÃO 1.4 — PERFORMANCE COMPARADA
    # ------------------------------------------
    with st.expander("📈 PERFORMANCE COMPARADA (BASE 100)", expanded=False):
        col_sel, col_per = st.columns([6, 2])
        with col_sel:
            indices_graf = st.multiselect("Índices:", ["^BVSP","^GSPC","^IXIC","^FTSE","^GDAXI","^N225","BTC-USD","GC=F"], default=["^BVSP","^GSPC","^IXIC"])
        with col_per: periodo_idx = st.selectbox("Período:", ["1mo","3mo","6mo","1y","2y"], index=3)
        if indices_graf:
            @st.cache_data(ttl=600, show_spinner=False)
            def buscar_historico_indices(tickers_tuple, periodo):
                df = yf.download(list(tickers_tuple), period=periodo, auto_adjust=True, progress=False)['Close']
                if isinstance(df, pd.Series): df = df.to_frame()
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(1)
                df = df.dropna(how='all').ffill().dropna()
                if hasattr(df.index, 'tz') and df.index.tz is not None: df.index = df.index.tz_localize(None)
                if not df.empty: return (df / df.iloc[0]) * 100
                return pd.DataFrame()
            df_norm = buscar_historico_indices(tuple(indices_graf), periodo_idx)
            if not df_norm.empty:
                fig = px.line(df_norm)
                fig.update_layout(paper_bgcolor="#010101", plot_bgcolor="#010101", height=350, xaxis=dict(showgrid=True, gridcolor='#222'), yaxis=dict(showgrid=True, gridcolor='#222', title="Base 100"), hovermode="x unified", margin=dict(l=0,r=0,t=10,b=0), font=dict(family="Courier New", color="#888"), legend=dict(orientation="h", y=1.05, x=1, xanchor="right"))
                fig.add_hline(y=100, line_dash="dash", line_color="#444", opacity=0.5)
                st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------
    # SEÇÃO 1.5 — SÍNTESE IA
    # ------------------------------------------
    with st.expander("🤖 SÍNTESE MACRO GLOBAL (IA)", expanded=False):
        cache_mercado = get_cache_ia("MARKET", "visao_mercado", max_horas=6)
        if cache_mercado: st.success("⚡ Cache ativo (6h)"); st.markdown(cache_mercado)
        else:
            if st.button("GERAR SÍNTESE DO CENÁRIO ATUAL", type="primary"):
                with st.spinner("Processando..."):
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        snapshot = f"IBOV {indices.get('IBOVESPA',{}).get('var',0):+.2f}%, SP500 {indices.get('S&P 500',{}).get('var',0):+.2f}%, SELIC {macro.get('selic',0):.2f}%, VIX {macro.get('vix',0):.1f}"
                        prompt = f"Aja como estrategista macro. Analise o snapshot e resuma temperatura do mercado, Brasil e Global (máx 300 palavras):\n{snapshot}"
                        resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        salvar_cache_ia("MARKET", "visao_mercado", resp.text); st.markdown(resp.text)
                    except Exception as e: st.error(f"Erro IA: {e}")

# ==========================================
# MODO 2 — VISÃO DE ATIVO
# ==========================================
else:
    # --- BUSCA CENTRALIZADA (Sessão 6) ---
    col_sel, col_manual, col_btn = st.columns([4, 2, 2])
    with col_sel:
        opcoes = get_opcoes_selectbox()
        selecao_dash = st.selectbox("ATIVO:", opcoes, key="dash_sel")
    with col_manual:
        ticker_manual_dash = st.text_input("Ou digite:", "", key="dash_manual").strip().upper()
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        analisar = st.button("⚡ ANALISAR", type="primary", use_container_width=True)

    ticker_ativo = ticker_manual_dash if ticker_manual_dash else (ticker_from_label(selecao_dash) or "PETR4.SA")

    if analisar or ("dash_ticker" not in st.session_state) or (st.session_state.dash_ticker != ticker_ativo):
        st.session_state.dash_ticker = ticker_ativo
        st.session_state.dash_carregado = False

    # Coleta Massiva
    if not st.session_state.get("dash_carregado", False) or analisar:
        with st.spinner(f"Sincronizando dados de {ticker_ativo}..."):
            try:
                acao = yf.Ticker(ticker_ativo)
                info = acao.info
                hist_1y = acao.history(period="1y")
                preco = info.get('currentPrice', info.get('regularMarketPrice', 0))
                nome = info.get('shortName', ticker_ativo)
                setor = info.get('sector', 'N/D')
                moeda_sym = "R$" if ticker_ativo.endswith(".SA") else "$"
                
                var_1d = ((preco / hist_1y['Close'].iloc[-2]) - 1) * 100 if len(hist_1y) >= 2 else 0
                var_1m = ((preco / hist_1y['Close'].iloc[-22]) - 1) * 100 if len(hist_1y) >= 22 else 0
                var_1a = ((preco / hist_1y['Close'].iloc[0]) - 1) * 100 if len(hist_1y) >= 2 else 0

                fund = {"P/L": info.get('trailingPE'), "P/VP": info.get('priceToBook'), "EV/EBITDA": info.get('enterpriseToEbitda'), "ROE%": (info.get('returnOnEquity',0)*100 if info.get('returnOnEquity') else None), "Margem%": (info.get('profitMargins',0)*100 if info.get('profitMargins') else None), "DY%": (info.get('dividendYield',0)*100 if info.get('dividendYield') else None), "Beta": info.get('beta'), "Market Cap": info.get('marketCap')}
                
                df_tec = hist_1y.copy()
                if hasattr(df_tec.index, 'tz') and df_tec.index.tz is not None: df_tec.index = df_tec.index.tz_localize(None)
                df_tec['SMA_50'] = df_tec['Close'].rolling(50).mean(); df_tec['SMA_200'] = df_tec['Close'].rolling(200).mean()
                delta = df_tec['Close'].diff(); ganho = delta.clip(lower=0).rolling(14).mean(); perda = (-delta.clip(upper=0)).rolling(14).mean()
                df_tec['RSI'] = 100 - (100 / (1 + (ganho / perda)))
                df_tec['BB_mid'] = df_tec['Close'].rolling(20).mean(); df_tec['BB_std'] = df_tec['Close'].rolling(20).std()
                df_tec['BB_upper'] = df_tec['BB_mid'] + 2 * df_tec['BB_std']; df_tec['BB_lower'] = df_tec['BB_mid'] - 2 * df_tec['BB_std']
                df_tec['vol_color'] = df_tec.apply(lambda r: '#00FF00' if r['Close'] >= r['Open'] else '#FF0000', axis=1)

                st.session_state.update({"dash_info": info, "dash_hist": hist_1y, "dash_tec": df_tec, "dash_nome": nome, "dash_setor": setor, "dash_preco": preco, "dash_moeda": moeda_sym, "dash_vars": (var_1d, var_1m, var_1a), "dash_fund": fund, "dash_earnings": acao.earnings_history if hasattr(acao, 'earnings_history') else None, "dash_noticias": acao.news or [], "dash_carregado": True})
            except Exception as e: st.error(f"Erro ao carregar ativo: {e}"); st.stop()

    info = st.session_state.dash_info; hist_1y = st.session_state.dash_hist; df_tec = st.session_state.dash_tec; nome = st.session_state.dash_nome; preco = st.session_state.dash_preco; moeda_sym = st.session_state.dash_moeda; var_1d, var_1m, var_1a = st.session_state.dash_vars; fund = st.session_state.dash_fund; earnings = st.session_state.dash_earnings; noticias = st.session_state.dash_noticias

    # HEADER DO ATIVO
    def fmt(v, suf="", d=2): return f"{v:.{d}f}{suf}" if v is not None and not np.isnan(v) else "N/D"
    def fmt_mcap(v): 
        if not v: return "N/D"
        if v >= 1e12: return f"{v/1e12:.2f}T"
        if v >= 1e9: return f"{v/1e9:.2f}B"
        return f"{v/1e6:.2f}M"
    
    html_header = (f"<div class='dash-card'><div style='display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px;'>"
                   f"<div><span style='font-size:1.8rem; font-weight:bold; color:#FF9900; font-family:\"Courier New\";'>{ticker_ativo}</span>"
                   f"<span style='font-size:1rem; color:#888; margin-left:10px; font-family:\"Courier New\";'>{nome}</span><br>"
                   f"<span style='font-size:0.75rem; color:#555; font-family:\"Courier New\";'>{st.session_state.dash_setor}</span></div>"
                   f"<div style='text-align:right;'><div style='font-size:2rem; font-weight:bold; color:#FFF; font-family:\"Courier New\";'>{moeda_sym} {preco:.2f}</div>"
                   f"<div style='color:{'#00FF00' if var_1d>=0 else '#FF0000'}; font-size:1rem; font-family:\"Courier New\";'>{'▲' if var_1d>=0 else '▼'} {abs(var_1d):.2f}% hoje</div></div>"
                   f"<div style='display:flex; gap:20px; font-family:\"Courier New\"; font-size:0.85rem;'>"
                   f"<div><span style='color:#888;'>1 MÊS</span><br><span style='color:{'#00FF00' if var_1m>=0 else '#FF0000'};'>{'▲' if var_1m>=0 else '▼'} {abs(var_1m):.2f}%</span></div>"
                   f"<div><span style='color:#888;'>1 ANO</span><br><span style='color:{'#00FF00' if var_1a>=0 else '#FF0000'};'>{'▲' if var_1a>=0 else '▼'} {abs(var_1a):.2f}%</span></div>"
                   f"<div><span style='color:#888;'>MARKET CAP</span><br><span style='color:#FFF;'>{moeda_sym} {fmt_mcap(fund.get('Market Cap'))}</span></div></div></div></div>")
    st.markdown(html_header, unsafe_allow_html=True)

    # FUNDAMENTOS
    with st.expander("📊 FUNDAMENTOS", expanded=True):
        c = st.columns(7)
        metr = [("P/L", fund.get("P/L")), ("P/VP", fund.get("P/VP")), ("EV/EBIT", fund.get("EV/EBITDA")), ("ROE", fund.get("ROE%"), "%"), ("MARGEM", fund.get("Margem%"), "%"), ("DY", fund.get("DY%"), "%"), ("BETA", fund.get("Beta"))]
        for i, m in enumerate(metr): c[i].metric(m[0], fmt(m[1], m[2] if len(m)>2 else ""))

    # TÉCNICA
    with st.expander("📈 PRICE ACTION & INDICADORES", expanded=True):
        col_op1, col_op2 = st.columns([6, 4])
        with col_op1: ind_sel = st.multiselect("Indicadores:", ["SMA 50","SMA 200","Bollinger"], default=["SMA 50","SMA 200"], key="dash_ind")
        with col_op2: periodo_tec = st.radio("Período:", ["3mo","6mo","1y"], index=2, horizontal=True)
        df_p = df_tec.tail({"3mo":63, "6mo":126, "1y":252}[periodo_tec])
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'], name="Preço"), row=1, col=1)
        if "SMA 50" in ind_sel: fig.add_trace(go.Scatter(x=df_p.index, y=df_p['SMA_50'], name="SMA 50", line=dict(color='#00FFFF', width=1)), row=1, col=1)
        if "SMA 200" in ind_sel: fig.add_trace(go.Scatter(x=df_p.index, y=df_p['SMA_200'], name="SMA 200", line=dict(color='#FF00FF', width=1.5)), row=1, col=1)
        if "Bollinger" in ind_sel:
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p['BB_upper'], name="BB Upper", line=dict(color='#FF9900', dash='dash')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p['BB_lower'], name="BB Lower", line=dict(color='#FF9900', dash='dash'), fill='tonexty', fillcolor='rgba(255,153,0,0.04)'), row=1, col=1)
        fig.add_trace(go.Bar(x=df_p.index, y=df_p['Volume'], marker_color=df_p['vol_color'], showlegend=False), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_p.index, y=df_p['RSI'], name="RSI", line=dict(color='#FFF')), row=3, col=1)
        fig.add_hline(y=70, line_color='#F00', line_dash='dash', row=3, col=1); fig.add_hline(y=30, line_color='#0F0', line_dash='dash', row=3, col=1)
        fig.update_layout(paper_bgcolor="#010101", plot_bgcolor="#010101", height=600, hovermode="x unified", font=dict(family="Courier New", color="#888"), margin=dict(l=0,r=0,t=30,b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

    # IA SÍNTESE
    with st.expander("🤖 SÍNTESE COMPLETA (IA)", expanded=False):
        cache_sint = get_cache_ia(ticker_ativo, 'sintese_dashboard', max_horas=12)
        if cache_sint: st.success("⚡ Cache 12h"); st.markdown(cache_sint)
        else:
            if st.button("GERAR SÍNTESE COMPLETA", type="primary"):
                with st.spinner("Analisando..."):
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        p = f"Analise {ticker_ativo} ({nome}). Preço: {moeda_sym}{preco:.2f}. P/L: {fmt(fund.get('P/L'))}, ROE: {fmt(fund.get('ROE%'),'%')}. RSI: {df_tec['RSI'].iloc[-1]:.1f}. Faça um relatório markdown com Tese, Valuation, Técnica e Riscos."
                        r = client.models.generate_content(model='gemini-2.5-flash', contents=p)
                        salvar_cache_ia(ticker_ativo, 'sintese_dashboard', r.text); st.markdown(r.text)
                    except Exception as e: st.error(f"Erro IA: {e}")