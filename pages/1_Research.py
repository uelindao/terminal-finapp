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
from utils.tickers import get_opcoes_selectbox, ticker_from_label, mapear_ticker_base, FII_TODOS, BRASIL_TODOS, XSTOCKS_TODOS
from database.db import listar_watchlists, listar_watchlist, get_todos_fundamentos_cache, init_db

# componentes do design system
from utils.components import page_header, section_title, metric_card, status_card, empty_state, inject_keyboard_shortcuts
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout, CORES_SERIES, base100

# 1. configuração da página
st.set_page_config(page_title="terminal finapp | research", layout="wide", page_icon="🔬")

# 2. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()
init_db()

CACHE_FUNDAMENTOS = get_todos_fundamentos_cache()

# ==========================================
# GESTÃO DE ESTADO E SIDEBAR
# ==========================================
if 'research_ticker' not in st.session_state:
    st.session_state['research_ticker'] = "PETR4.SA"

if 'research_ticker_externo' in st.session_state:
    st.session_state['research_ticker'] = st.session_state.pop('research_ticker_externo')

with st.sidebar:
    section_title("🔬 modo de análise")
    modo_pesquisa = st.radio("selecione o escopo:", ["Deep Dive (Individual)", "Comparativo (Múltiplos)"], label_visibility="collapsed")
    
    st.markdown("---")
    
    if modo_pesquisa == "Deep Dive (Individual)":
        section_title("pesquisar ativo")
        opcoes = get_opcoes_selectbox()
        
        idx_default = 0
        for i, opt in enumerate(opcoes):
            if st.session_state['research_ticker'] in opt:
                idx_default = i
                break

        escolha = st.selectbox("selecionar ticker:", opcoes, index=idx_default)
        ticker_limpo = ticker_from_label(escolha)
        if ticker_limpo:
            st.session_state['research_ticker'] = ticker_limpo
    else:
        section_title("comparar ativos")
        ativos_comp = st.multiselect("selecione os ativos:", 
                                     options=BRASIL_TODOS + XSTOCKS_TODOS,
                                     default=["PETR4.SA", "VALE3.SA", "ITUB4.SA"])
    
    st.markdown("---")
    st.caption("v2.3 — ia context-aware ativa")

# Trava de segurança para números
def safe_float(val):
    try:
        if val is None or pd.isna(val): return None
        return float(val)
    except: return None

def calcular_crescimento_implicito(preco, eps, wacc, g_terminal, n_anos):
    try:
        if eps is None or eps <= 0 or preco is None or preco <= 0:
            return None
        if wacc <= g_terminal:
            return None
            
        def valor_dcf(g):
            soma_fc = sum((eps * (1 + g)**t) / ((1 + wacc)**t) for t in range(1, n_anos + 1))
            valor_term = (eps * (1 + g)**n_anos * (1 + g_terminal)) / (wacc - g_terminal)
            valor_term_descontado = valor_term / ((1 + wacc)**n_anos)
            return soma_fc + valor_term_descontado
            
        lo = -0.5
        hi = 3.0
        for _ in range(200):
            mid = (lo + hi) / 2
            try:
                if valor_dcf(mid) > preco:
                    hi = mid
                else:
                    lo = mid
            except:
                return None
        return mid
    except:
        return None

# ==========================================
# MODO 2: COMPARATIVO MULTI-ATIVOS
# ==========================================
if modo_pesquisa == "Comparativo (Múltiplos)":
    page_header("⚖️ comparativo de mercado", "análise relativa de múltiplos e performance em base 100.")
    
    if not ativos_comp:
        st.info("selecione ativos na barra lateral para iniciar a comparação.")
    else:
        with st.spinner("sincronizando matriz de múltiplos..."):
            dados_comp = []
            try:
                hist_all = yf.download(ativos_comp, period="10y", progress=False)['Close']
                if isinstance(hist_all, pd.Series): hist_all = hist_all.to_frame(name=ativos_comp[0])
                hist_all = hist_all.ffill().dropna(how='all')
                if hist_all.index.tz is not None: hist_all.index = hist_all.index.tz_localize(None)
            except: hist_all = pd.DataFrame()
            
            for t in ativos_comp:
                t_base = mapear_ticker_base(t)
                try:
                    info = yf.Ticker(t_base).info
                    cache_d = CACHE_FUNDAMENTOS.get(t_base, {})
                    dados_comp.append({
                        "ticker": t,
                        "p/l": safe_float(cache_d.get('p/l')) or safe_float(info.get('trailingPE')),
                        "p/vp": safe_float(cache_d.get('p/vp')) or safe_float(info.get('priceToBook')),
                        "roe%": safe_float(cache_d.get('roe%')) or (safe_float(info.get('returnOnEquity', 0))*100),
                        "dy%": safe_float(cache_d.get('dy%')) or (safe_float(info.get('dividendYield', 0))*100),
                        "mrg_liq%": safe_float(cache_d.get('margem%')) or (safe_float(info.get('profitMargins', 0))*100),
                        "mkt_cap": safe_float(info.get('marketCap')) or safe_float(cache_d.get('market_cap'))
                    })
                except: pass

            df_comp = pd.DataFrame(dados_comp)
            c1, c2 = st.columns([6, 4])
            with c1:
                st.markdown("**matriz de múltiplos quantitativos**")
                if not df_comp.empty:
                    st.dataframe(df_comp.style.format({"p/l": "{:.2f}", "p/vp": "{:.2f}", "roe%": "{:.1f}%", "dy%": "{:.1f}%", "mrg_liq%": "{:.1f}%", "mkt_cap": "${:,.0f}"}), use_container_width=True, hide_index=True)
            with c2:
                st.markdown("**performance relativa (base 100 — 10 anos)**")
                if not hist_all.empty:
                    df_b100 = (hist_all / hist_all.iloc[0]) * 100
                    fig_b100 = base100(df_b100, height=350)
                    st.plotly_chart(fig_b100, use_container_width=True)
    st.stop()

# ==========================================
# MODO 1: DEEP DIVE (INDIVIDUAL)
# ==========================================
ticker = st.session_state['research_ticker']
t_base = mapear_ticker_base(ticker)
is_fii = ticker in FII_TODOS or (ticker.endswith("11.SA") and ticker not in ['TAEE11.SA', 'KLBN11.SA', 'ENGI11.SA'])

@st.cache_resource(ttl=3600)
def carregar_dados_ativo(tk):
    try:
        acao = yf.Ticker(tk)
        hist = acao.history(period="10y")
        info = acao.info
        if not isinstance(info, dict): info = {}
        if not hist.empty and hist.index.tz is not None: hist.index = hist.index.tz_localize(None)
        return acao, hist, info
    except: return None, pd.DataFrame(), {}

acao_obj, df_hist, info_dict = carregar_dados_ativo(t_base)
if acao_obj is None or df_hist.empty:
    empty_state("❌", "ativo não encontrado", "não foi possível carregar os dados históricos.")
    st.stop()

cache_d = CACHE_FUNDAMENTOS.get(t_base, {})

# --- HEADER & MÉTRICAS ---
nome_exibicao = info_dict.get('longName') or info_dict.get('shortName') or cache_d.get('nome') or ticker
moeda = "r$" if ticker.endswith(".SA") else "$"
setor_raw = cache_d.get('setor') or info_dict.get('sector')
setor = "logística (fii)" if "logística" in str(setor_raw).lower() else (setor_raw if setor_raw else ("fundo imobiliário" if is_fii else "mercado global"))

page_header(f"🔬 {ticker.lower()}", f"{nome_exibicao.lower()} | {setor.lower()}")

c1, c2, c3, c4 = st.columns(4)
if is_fii:
    pvp = safe_float(cache_d.get('p/vp')) or safe_float(info_dict.get('priceToBook'))
    dy = safe_float(cache_d.get('dy%')) or (safe_float(info_dict.get('dividendYield', 0)) * 100)
    mcap = safe_float(info_dict.get('marketCap')) or safe_float(cache_d.get('market_cap', 0))
    assets = safe_float(info_dict.get('totalAssets'))
    with c1: metric_card("preço / vp", f"{pvp:.2f}" if pvp else "n/d", "desconto" if pvp and pvp < 1 else ("ágio" if pvp else ""), "bull" if pvp and pvp < 1 else "bear")
    with c2: metric_card("dividend yield", fmt_pct(dy), "12m", "bull" if dy and dy > 8 else "muted")
    with c3: metric_card("mkt cap", fmt_numero(mcap, moeda))
    with c4: metric_card("patrimônio líq.", fmt_numero(assets, moeda))
else:
    pl = safe_float(cache_d.get('p/l')) or safe_float(info_dict.get('trailingPE')) or safe_float(info_dict.get('forwardPE'))
    roe = safe_float(cache_d.get('roe%')) or (safe_float(info_dict.get('returnOnEquity', 0)) * 100)
    mrg = safe_float(cache_d.get('margem%')) or (safe_float(info_dict.get('profitMargins', 0)) * 100)
    dy = safe_float(cache_d.get('dy%')) or (safe_float(info_dict.get('dividendYield', 0)) * 100)
    with c1: metric_card("preço / lucro", f"{pl:.1f}" if pl else "n/d", "valuation")
    with c2: metric_card("r.o.e", fmt_pct(roe), "rentabilidade", "bull" if roe and roe > 15 else "muted")
    with c3: metric_card("margem líq.", fmt_pct(mrg), "eficiência", "bull" if mrg and mrg > 10 else "bear")
    with c4: metric_card("div yield", fmt_pct(dy), "12m")

st.markdown("<br>", unsafe_allow_html=True)

# --- TABS ---
tab_tec, tab_earn, tab_fund, tab_dcf, tab_sent, tab_macro = st.tabs([
    "📈 análise técnica (10y)", "📊 demonstrações (dre)", "💎 fundamentos", "🧮 valuation lab (dcf reverso)", "📰 notícias & ia", "🌍 overlay macro (10y)"
])

with tab_tec:
    try:
        fig_tec = go.Figure()
        fig_tec.add_trace(go.Candlestick(x=df_hist.index, open=df_hist['Open'], high=df_hist['High'], low=df_hist['Low'], close=df_hist['Close'], name="price"))
        if len(df_hist) >= 50: fig_tec.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Close'].rolling(50).mean(), name="mm50", line=dict(color=CORES_SERIES[1], width=1)))
        if len(df_hist) >= 200: fig_tec.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Close'].rolling(200).mean(), name="mm200", line=dict(color=CORES_SERIES[3], width=1.5)))
        fig_tec.update_layout(**base_layout(height=500, title=f"price action histórico (10 anos): {ticker.lower()}"))
        fig_tec.update_layout(xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_tec, use_container_width=True)
    except Exception as e: st.error(f"Erro gráfico técnico: {e}")

with tab_earn:
    if is_fii: st.info("💡 FIIs não possuem DRE trimestral padrão. Avalie os Rendimentos em Fundamentos.")
    else:
        st.subheader("receita vs lucro (últimos períodos)")
        try:
            fin = acao_obj.quarterly_financials
            if fin is None or (isinstance(fin, pd.DataFrame) and fin.empty): fin = acao_obj.financials
            if fin is not None and not fin.empty:
                l_rev = ['Total Revenue', 'Total Operating Revenue', 'Operating Revenue']
                l_net = ['Net Income', 'Net Income Common Stockholders', 'Net Income From Continuing Operations']
                row_rev = fin.index[fin.index.isin(l_rev)].tolist()
                row_net = fin.index[fin.index.isin(l_net)].tolist()
                if row_rev and row_net:
                    df_earn = pd.DataFrame({'Receita': fin.loc[row_rev[0]], 'Lucro Líquido': fin.loc[row_net[0]]}).sort_index()
                    df_earn.index = df_earn.index.astype(str)
                    fig_earn = go.Figure()
                    fig_earn.add_trace(go.Bar(x=df_earn.index, y=df_earn['Receita'], name="receita", marker_color=CORES_SERIES[1]))
                    fig_earn.add_trace(go.Bar(x=df_earn.index, y=df_earn['Lucro Líquido'], name="lucro", marker_color=CORES_SERIES[2]))
                    fig_earn.update_layout(**base_layout(height=400), barmode='group')
                    st.plotly_chart(fig_earn, use_container_width=True)
        except: st.error("Erro earnings.")

with tab_fund:
    c_f1, c_f2 = st.columns(2)
    with c_f1:
        st.markdown("**múltiplos e risco**")
        vol = fmt_pct(df_hist['Close'].pct_change().std() * np.sqrt(252) * 100) if len(df_hist) > 10 else "N/D"
        if is_fii:
            debt = safe_float(info_dict.get('totalDebt', 0))
            assets_t = safe_float(info_dict.get('totalAssets', 1))
            ltv = (debt / assets_t * 100) if assets_t > 0 else 0
            f_d = {"métrica": ["P/VP", "Yield (12m)", "Volatilidade Anual", "Alavancagem (Dívida/Ativos)", "Setor/Segmento"], 
                   "valor": [f"{pvp:.2f}" if pvp else "N/D", fmt_pct(dy), vol, f"{ltv:.1f}%" if ltv > 0 else "baixa/nula", setor]}
        else:
            ev_e = safe_float(cache_d.get('ev/ebitda')) or safe_float(info_dict.get('enterpriseToEbitda'))
            f_d = {"métrica": ["EV/EBITDA", "P/VP", "Volatilidade Anual", "Beta", "Dívida/Patrimônio"], 
                   "valor": [f"{ev_e:.2f}" if ev_e else "N/D", f"{safe_float(cache_d.get('p/vp')) or safe_float(info_dict.get('priceToBook')):.2f}", vol, f"{safe_float(info_dict.get('beta')):,.2f}" if safe_float(info_dict.get('beta')) else "N/D", f"{safe_float(info_dict.get('debtToEquity')):,.1f}%" if safe_float(info_dict.get('debtToEquity')) else "N/D"]}
        st.table(pd.DataFrame(f_d))
    with c_f2:
        st.markdown("**descrição**")
        st.write(info_dict.get('longBusinessSummary', 'Sem descrição.')[:800] + "...")

with tab_dcf:
    if is_fii:
        empty_state("🧮", "dcf não aplicável", "o modelo de dcf reverso é projetado para ações com lucro por ação. fiis são avaliados por p/vp e dividend yield.")
    else:
        eps_base = safe_float(info_dict.get('trailingEps')) or safe_float(info_dict.get('forwardEps'))
        preco_base = safe_float(df_hist['Close'].iloc[-1]) if not df_hist.empty else None
        is_us = not ticker.endswith('.SA')
        
        section_title("⚙️ parâmetros do modelo")
        
        c_dcf1, c_dcf2, c_dcf3, c_dcf4 = st.columns(4)
        with c_dcf1:
            eps_input = st.number_input("eps (lucro/ação)", value=float(eps_base) if eps_base and eps_base > 0 else 5.0, min_value=-100.0, step=0.01, format="%.2f")
        with c_dcf2:
            preco_input = st.number_input("preço atual", value=float(preco_base) if preco_base else 100.0, min_value=0.01, step=0.01, format="%.2f")
        with c_dcf3:
            wacc_pct = st.slider("wacc (custo capital %)", min_value=4.0, max_value=20.0, value=9.0 if is_us else 12.0, step=0.5, format="%.1f%%")
        with c_dcf4:
            g_term_pct = st.slider("crescimento terminal %", min_value=1.0, max_value=5.0, value=3.0, step=0.5, format="%.1f%%")
            
        c_dcf5, c_dcf6 = st.columns(2)
        with c_dcf5:
            n_anos = st.slider("horizonte de projeção (anos)", min_value=5, max_value=15, value=10, step=1)
        with c_dcf6:
            margem_seg_pct = st.slider("margem de segurança (%)", min_value=0, max_value=40, value=15, step=5)
            
        wacc = wacc_pct / 100
        g_terminal = g_term_pct / 100
        
        st.markdown("---")
        
        g_implicito = calcular_crescimento_implicito(preco_input, eps_input, wacc, g_terminal, n_anos)
        
        section_title("📊 crescimento implícito no preço atual")
        
        if g_implicito is None:
            st.warning("não foi possível calcular. verifique se o eps é positivo e o wacc é maior que o crescimento terminal.")
        else:
            g_implicito_pct = g_implicito * 100
            preco_com_ms = preco_input * (1 - (margem_seg_pct / 100))
            
            c_res1, c_res2, c_res3, c_res4 = st.columns(4)
            with c_res1:
                metric_card("crescimento implícito (a.a.)", fmt_pct(g_implicito_pct), cor_delta="bull" if g_implicito_pct < 15 else "bear")
            with c_res2:
                metric_card("p/l implícito", f"{preco_input/eps_input:.1f}x" if eps_input > 0 else "n/d")
            with c_res3:
                metric_card("preço com margem segurança", f"{moeda.upper()} {preco_com_ms:.2f}")
            with c_res4:
                metric_card("horizonte analisado", f"{n_anos} anos")
                
            if g_implicito_pct < 8:
                interpretacao = "crescimento baixo precificado — assimetria favorável se a empresa crescer acima disso."
                cor_int = "bull"
            elif g_implicito_pct <= 20:
                interpretacao = "crescimento moderado a alto precificado — valuation justo se tese de crescimento se confirmar."
                cor_int = "amber"
            else:
                interpretacao = "crescimento muito alto precificado — risco elevado de decepção. exige execução perfeita."
                cor_int = "bear"
                
            status_card("interpretação do valuation", interpretacao, cor_int)
            
            section_title("🗺️ mapa de sensibilidade — preço justo estimado por cenário")
            
            cenarios_g = [-5, 0, 5, 8, 10, 12, 15, 20, 25]
            cenarios_wacc = [round(wacc_pct - 2, 1), wacc_pct, round(wacc_pct + 2, 1)]
            
            dados_sens = []
            for wacc_c in cenarios_wacc:
                linha = {}
                w_c_dec = wacc_c / 100
                for g_c in cenarios_g:
                    g_c_dec = g_c / 100
                    try:
                        if w_c_dec <= g_terminal:
                            linha[f"g={g_c}%"] = "—"
                        else:
                            vp_soma = sum(eps_input * (1 + g_c_dec)**t / (1 + w_c_dec)**t for t in range(1, n_anos + 1))
                            vp_term = (eps_input * (1 + g_c_dec)**n_anos * (1 + g_terminal)) / (w_c_dec - g_terminal) / ((1 + w_c_dec)**n_anos)
                            linha[f"g={g_c}%"] = round(vp_soma + vp_term, 2)
                    except:
                        linha[f"g={g_c}%"] = "—"
                dados_sens.append(linha)
                
            df_sens = pd.DataFrame(dados_sens, index=[f"wacc {w}%" for w in cenarios_wacc])
            
            st.dataframe(df_sens, use_container_width=True, hide_index=False)
            st.caption(f"valores em {moeda.upper()} | célula verde = subvalorizado vs preço atual de {preco_input} | linha destacada = wacc configurado acima.")
            
            fig = go.Figure()
            for i, wacc_c in enumerate(cenarios_wacc):
                y_vals = []
                for g_c in cenarios_g:
                    val = df_sens.loc[f"wacc {wacc_c}%", f"g={g_c}%"]
                    y_vals.append(val if val != "—" else None)
                    
                fig.add_trace(go.Scatter(x=cenarios_g, y=y_vals, name=f"wacc {wacc_c}%", line=dict(color=CORES_SERIES[i % len(CORES_SERIES)])))
                
            fig.add_hline(y=preco_input, line_color="#FF9900", line_dash="dash", annotation_text="preço atual")
            fig.update_layout(**base_layout(height=380, title="preço justo estimado por taxa de crescimento e wacc"))
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            if st.button("🧠 ia: interpretar o valuation e gerar tese", type="primary"):
                with st.spinner("analisando..."):
                    prompt_ia = f"você é um analista de valuation sênior. analise o modelo de dcf reverso abaixo e dê sua opinião sobre o valuation do ativo. ativo: {ticker}. preço atual: {preco_input}. eps: {eps_input}. crescimento implícito no preço: {g_implicito_pct:.1f}%. wacc utilizado: {wacc_pct}%. crescimento terminal: {g_term_pct}%. horizonte: {n_anos} anos. responda com: 1. avaliação do crescimento implícito (é realista para o setor?). 2. comparação com pares do setor se souber. 3. cenário bull e bear para o preço em 3 anos baseado na sensibilidade. 4. recomendação de ação (comprar, aguardar, evitar) com justificativa. escreva em minúsculas e seja direto e objetivo."
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        res_ia = client.models.generate_content(model='gemini-2.5-flash', contents=prompt_ia).text
                        status_card("interpretação ia do valuation lab", res_ia, "info")
                    except Exception as e:
                        st.error(f"Erro IA: {e}")

with tab_sent:
    st.subheader("sentimento via notícias")
    try:
        news = acao_obj.news
        if news:
            for item in news[:5]:
                with st.container():
                    cn1, cn2 = st.columns([4, 1])
                    cn1.markdown(f"**{item.get('title')}**")
                    cn1.caption(f"{item.get('publisher')} | {datetime.datetime.fromtimestamp(item.get('providerPublishTime'))}")
                    if cn2.button("ia: analisar", key=item.get('uuid')):
                        with st.spinner("ia..."):
                            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                            res = client.models.generate_content(model='gemini-2.5-flash', contents=f"analise se '{item.get('title')}' é positivo ou negativo para {ticker} em 1 frase curta com minúsculas.").text
                            st.info(res)
                    st.markdown("---")
    except: st.info("Sem notícias.")

with tab_macro:
    st.subheader("estudo de correlação estrutural (10 anos)")
    ind_macro = st.selectbox("comparar com:", ["Taxa Selic (Brasil)", "IPCA (Inflação BR)", "Dólar Comercial (BRL=X)", "VIX (Volatilidade Global)"])
    inicio_macro = (datetime.datetime.now() - datetime.timedelta(days=365*10)).strftime('%Y-%m-%d')
    try:
        m_data = None
        if "Selic" in ind_macro: m_data, m_name = sgs.get({'selic': 432}, start=inicio_macro)['selic'], "selic %"
        elif "IPCA" in ind_macro: m_data, m_name = sgs.get({'ipca': 433}, start=inicio_macro)['ipca'], "ipca %"
        elif "Dólar" in ind_macro:
            m_data = yf.download("BRL=X", start=inicio_macro, progress=False)['Close']
            if isinstance(m_data, pd.DataFrame): m_data = m_data.iloc[:, 0]
            m_name = "usd/brl"
        elif "VIX" in ind_macro and "FRED_API_KEY" in st.secrets:
            m_data, m_name = Fred(api_key=st.secrets["FRED_API_KEY"]).get_series('VIXCLS', observation_start=inicio_macro), "vix index"
            
        if m_data is not None and not m_data.empty:
            m_data.index = pd.to_datetime(m_data.index).tz_localize(None)
            stk_p = df_hist['Close'].copy()
            stk_p.index = pd.to_datetime(stk_p.index).tz_localize(None)
            fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
            fig_macro.add_trace(go.Scatter(x=stk_p.index, y=stk_p, name=ticker.lower(), line=dict(color="#FF9900")), secondary_y=False)
            fig_macro.add_trace(go.Scatter(x=m_data.index, y=m_data, name=m_name, line=dict(color="#00B0FF", dash="dot")), secondary_y=True)
            fig_macro.update_layout(**base_layout(height=450, title=f"{ticker.lower()} vs {ind_macro.lower()}"))
            st.plotly_chart(fig_macro, use_container_width=True)
    except: st.warning("Erro overlay.")

# --- DIAGNÓSTICO IA (FOOTER REFORMULADO) ---
st.markdown("---")
if st.button("🧠 gerar diagnóstico de tese via gemini", use_container_width=True, type="primary"):
    with st.spinner("sintetizando fundamentos e construindo a tese..."):
        try:
            # Coleta de dados blindada para o prompt
            val_pl = safe_float(cache_d.get('p/l')) or safe_float(info_dict.get('trailingPE'))
            val_pvp = safe_float(cache_d.get('p/vp')) or safe_float(info_dict.get('priceToBook'))
            val_roe = safe_float(cache_d.get('roe%')) or (safe_float(info_dict.get('returnOnEquity', 0)) * 100)
            val_dy = safe_float(cache_d.get('dy%')) or (safe_float(info_dict.get('dividendYield', 0)) * 100)
            
            # Cálculo de Alavancagem para FIIs
            debt_val = safe_float(info_dict.get('totalDebt', 0))
            assets_val = safe_float(info_dict.get('totalAssets', 1))
            ltv_val = (debt_val / assets_val * 100) if assets_val > 0 else 0

            # Construção do Contexto Rico para a IA
            if is_fii:
                ctx = f"ativo: {ticker} (Fundo Imobiliário). Segmento: {setor}. P/VP: {val_pvp:.2f}. Dividend Yield: {val_dy:.1f}%. Alavancagem (Dívida/Ativos): {ltv_val:.1f}%."
            else:
                ctx = f"ativo: {ticker}. P/L: {val_pl:.2f}. ROE: {val_roe:.1f}%. Dividend Yield: {val_dy:.1f}%. Setor: {setor}."

            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            res = client.models.generate_content(model='gemini-2.5-flash', 
                contents=f"você é um analista fundamentalista sênior. escreva uma tese de investimento de longo prazo para {ticker} baseada estritamente nestes dados: {ctx}. analise se o nível de dívida/alavancagem é adequado para o setor informado. escreva 4 parágrafos curtos em minúsculas.").text
            status_card(f"racional: {ticker.lower()}", res, "info")
        except Exception as e: st.error(f"Erro IA: {e}")