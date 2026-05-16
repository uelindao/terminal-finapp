import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from bcb import sgs
from fredapi import Fred
import yfinance as yf
import datetime
from google import genai

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label

# componentes do design system (camada 2 e 4)
from utils.components import page_header, section_title, metric_card, status_card, empty_state, inject_keyboard_shortcuts, auto_refresh_indicator
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout

# 1. configuração da página
st.set_page_config(page_title="terminal finapp | macro", layout="wide", page_icon="🌍")

# 2. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()

page_header("🌍 ambiente macroeconómico", "monitoramento de juros, inflação, atividade e apetite ao risco global.")

if "FRED_API_KEY" not in st.secrets:
    st.warning("⚠️ **aviso de arquitetura:** a chave da api do fred não foi encontrada no arquivo `secrets.toml`.\n\nsem ela, os dados dos eua e risco global ficarão indisponíveis.")

# ==========================================
# funções globais de cache e apoio
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def puxar_historico_mestre():
    hoje = datetime.datetime.today()
    inicio_10a = hoje - datetime.timedelta(days=365 * 10) 
    
    # 1. brasil (sgs)
    series_bcb = {'Selic': 432, 'IPCA': 433, 'Dolar': 1, 'Desemprego': 24369}
    dfs_br_dict = {}
    for nome, codigo in series_bcb.items():
        try:
            df_temp = sgs.get({nome: codigo}, start=inicio_10a)
            if not df_temp.empty: dfs_br_dict[nome] = df_temp[nome]
        except Exception: pass
            
    df_br = pd.DataFrame(dfs_br_dict) if dfs_br_dict else pd.DataFrame()
    
    # 2. global (fred)
    df_global = pd.DataFrame()
    if "FRED_API_KEY" in st.secrets:
        try:
            fred = Fred(api_key=st.secrets["FRED_API_KEY"])
            series_fred = {
                'FEDFUNDS': 'FEDFUNDS', 'CPIAUCSL': 'CPIAUCSL', 'UNRATE': 'UNRATE',
                'DGS10': 'DGS10', 'DGS2': 'DGS2', 'VIXCLS': 'VIXCLS',
                'ECBDFR': 'ECBDFR', 'IRLTLT01EZM156N': 'IRLTLT01EZM156N', 'IRLTLT01JPM156N': 'IRLTLT01JPM156N',
                'T10Y2Y': 'T10Y2Y', 'BAMLH0A0HYM2': 'BAMLH0A0HYM2'
            }
            dfs_global_dict = {}
            for nome, serie_id in series_fred.items():
                try: dfs_global_dict[nome] = fred.get_series(serie_id, observation_start=inicio_10a)
                except Exception: pass
            df_global = pd.DataFrame(dfs_global_dict)
            if 'CPIAUCSL' in df_global.columns:
                df_global['CPI_MoM'] = df_global['CPIAUCSL'].pct_change() * 100
        except Exception: pass 
    
    # 3. commodities
    df_commodities = pd.DataFrame()
    try:
        df_commodities = yf.download(['CL=F', 'GC=F'], start=inicio_10a, progress=False)['Close']
        if isinstance(df_commodities, pd.Series): df_commodities = df_commodities.to_frame()
    except Exception: pass 
        
    return df_br, df_global, df_commodities

def valor_atual_seguro(df, coluna):
    if not df.empty and coluna in df.columns and not df[coluna].dropna().empty:
        return df[coluna].dropna().iloc[-1]
    return None

def criar_grafico_macro(df, coluna_y, titulo, cor_linha):
    layout = base_layout(height=280, title=titulo)
    if df.empty or coluna_y not in df.columns or df[coluna_y].dropna().empty:
        fig = px.line()
        fig.add_annotation(text=f"sem dados: {titulo}", x=0.5, y=0.5, showarrow=False, font=dict(color="#FF1744", size=14))
        layout['xaxis'] = dict(visible=False)
        layout['yaxis'] = dict(visible=False)
        fig.update_layout(**layout)
        return fig
    df_plot = df.dropna(subset=[coluna_y])
    fig = px.line(df_plot, x=df_plot.index, y=coluna_y)
    fig.update_layout(**layout)
    fig.update_traces(line_color=cor_linha, line_width=1.5)
    return fig

def renderizar_noticias(ticker, titulo_secao):
    section_title(titulo_secao)
    try:
        acao = yf.Ticker(ticker)
        noticias = acao.news
        if noticias:
            noticias_renderizadas = 0
            for noti in noticias:
                if noticias_renderizadas >= 5: break
                dados = noti.get('content', noti)
                titulo = dados.get('title', dados.get('headline', ''))
                if not titulo: continue
                link = dados.get('link', dados.get('url', dados.get('clickThroughUrl', dados.get('previewUrl', '#'))))
                if isinstance(link, dict): link = link.get('url', '#')
                publisher_data = dados.get('provider', dados.get('publisher', 'agência internacional'))
                if isinstance(publisher_data, dict): publisher = publisher_data.get('displayName', 'agência internacional')
                else: publisher = publisher_data
                
                st.markdown(f'<div class="card" style="padding:10px; border-left:3px solid #00B0FF; margin-bottom: 8px;"><div style="font-family:Courier New; font-size:0.7em; color:#888;">{publisher.lower()}</div><a href="{link}" target="_blank" style="text-decoration:none; color:#E0E0E0; font-family:Courier New; font-size:0.85rem;">{titulo.lower()}</a></div>', unsafe_allow_html=True)
                noticias_renderizadas += 1
            if noticias_renderizadas == 0: st.info("formato interno de notícias não suportado.")
        else: empty_state("🗞️", "sem notícias", "feed vazio no momento.")
    except Exception as e: st.error(f"falha ao sincronizar feed de notícias.")

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_retornos_setoriais():
    etfs_setoriais = {
        "energia": "XLE", 
        "financeiro": "XLF", 
        "tecnologia": "XLK", 
        "saúde": "XLV", 
        "indústria": "XLI", 
        "cons. básico": "XLP", 
        "cons. discric.": "XLY", 
        "materiais": "XLB", 
        "utilities": "XLU", 
        "imobiliário": "XLRE", 
        "telecom": "XLC"
    }
    periodos = ["1mo", "3mo", "6mo", "1y"]
    resultados = {}
    for label, ticker in etfs_setoriais.items():
        linha = []
        for periodo in periodos:
            try:
                df = yf.download(ticker, period=periodo, auto_adjust=True, progress=False)
                fechamento = df['Close']
                if isinstance(fechamento, pd.DataFrame):
                    fechamento = fechamento[ticker]
                fechamento = fechamento.dropna()
                if not fechamento.empty:
                    retorno = ((fechamento.iloc[-1] / fechamento.iloc[0]) - 1) * 100
                    linha.append(round(retorno, 2))
                else:
                    linha.append(None)
            except Exception:
                linha.append(None)
        resultados[label] = linha
    
    return pd.DataFrame(resultados.values(), index=list(resultados.keys()), columns=["1 mês", "3 meses", "6 meses", "12 meses"])

def diagnosticar_ciclo(t10y2y, vix, hy_spread):
    if t10y2y is None or vix is None:
        return "dados insuficientes", "#555555", "—"
    if t10y2y < -0.2 and vix > 20:
        return "🔴 contração / recessão", "#FF1744", "utilities (xlu), saúde (xlv), cons. básico (xlp)"
    if t10y2y < 0.3 and vix < 20 and (hy_spread is not None and hy_spread < 4.5):
        return "🟡 recuperação (early cycle)", "#FF9900", "financeiro (xlf), indústria (xli), cons. discric. (xly)"
    if 0.3 <= t10y2y < 1.0 and vix < 18:
        return "🟢 expansão (mid cycle)", "#00C853", "tecnologia (xlk), indústria (xli), energia (xle)"
    if t10y2y >= 1.0 and vix < 20:
        return "🟡 pico de ciclo (late cycle)", "#FF9900", "energia (xle), materiais (xlb), saúde (xlv)"
    return "⚪ transição", "#888888", "posicionamento neutro — aguardar confirmação"

# ==========================================
# abas principais da página
# ==========================================
tab_global, tab_ciclo, tab_overlay = st.tabs(["🌐 painel global", "🔄 ciclo econômico", "🔭 overlay macro × preços"])

with tab_global:
    auto_refresh_indicator(1440) # atualizado diariamente pelo cache
    
    with st.spinner("sincronizando feed de bancos centrais e mídia global via apis oficiais..."):
        df_br_master, df_global_master, df_comm_master = puxar_historico_mestre()
        
        col_espaco, col_filtro = st.columns([7, 3])
        with col_filtro:
            janela = st.radio("horizonte de tempo:", ["3 anos", "5 anos", "10 anos"], index=1, horizontal=True, label_visibility="collapsed")
            
        anos_filtro = int(janela.split()[0])
        data_corte = datetime.datetime.today() - datetime.timedelta(days=365 * anos_filtro)
        
        df_br = df_br_master[df_br_master.index >= data_corte] if not df_br_master.empty else df_br_master
        df_global = df_global_master[df_global_master.index >= data_corte] if not df_global_master.empty else df_global_master
        
        if not df_comm_master.empty:
            df_comm = df_comm_master[df_comm_master.index >= data_corte]
            if isinstance(df_comm.columns, pd.MultiIndex): df_comm.columns = df_comm.columns.get_level_values(1)
        else: df_comm = df_comm_master

        section_title("leitura macroeconômica (ai synthesis)")
        if st.button("gerar relatório do cenário atual >>", type="primary"):
            with st.spinner("processando vetores de juros, inflação e risco global..."):
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    prompt = f"""
                    aja como um estrategista macro de um hedge fund. 
                    brasil: selic {valor_atual_seguro(df_br, 'Selic') or 0:.2f}%, ipca {valor_atual_seguro(df_br, 'IPCA') or 0:.2f}%.
                    eua: fed funds {valor_atual_seguro(df_global, 'FEDFUNDS') or 0:.2f}%, cpi {valor_atual_seguro(df_global, 'CPI_MoM') or 0:.2f}%.
                    europa: bce {valor_atual_seguro(df_global, 'ECBDFR') or 0:.2f}%.
                    risco: vix {valor_atual_seguro(df_global, 'VIXCLS') or 0:.2f}.
                    
                    escreva 3 bullet points curtos em português:
                    1. relação juros brasil x eua.
                    2. temperatura inflacionária global.
                    3. apetite ao risco (vix).
                    inicie todas as frases e tópicos com letra minúscula. essa é a forma da nossa escrita.
                    sem uso de cifrões.
                    """
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    status_card("cenário macro", response.text, "info")
                except Exception as e: st.error(f"erro no agente de ia: {e}")
        
        st.markdown("---")
        
        aba_sel = st.radio("selecione o mercado:", ["🇧🇷 brasil", "🇺🇸 estados unidos", "🌍 europa/ásia", "🌐 risco", "🛢️ commodities", "📰 macro news"], horizontal=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        if aba_sel == "🇧🇷 brasil":
            c1, c2, c3, c4 = st.columns(4)
            v_selic = valor_atual_seguro(df_br, 'Selic')
            v_ipca = valor_atual_seguro(df_br, 'IPCA')
            v_dolar = valor_atual_seguro(df_br, 'Dolar')
            v_desemp = valor_atual_seguro(df_br, 'Desemprego')
            with c1: metric_card("selic atual", fmt_pct(v_selic, sinal=False))
            with c2: metric_card("ipca mensal", fmt_pct(v_ipca, sinal=False))
            with c3: metric_card("dólar (ptax)", fmt_preco(v_dolar, "r$"))
            with c4: metric_card("desemprego", fmt_pct(v_desemp, sinal=False))
            
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(criar_grafico_macro(df_br, 'Selic', "taxa selic histórica (%)", "#00C853"), use_container_width=True)
            with g2: st.plotly_chart(criar_grafico_macro(df_br, 'IPCA', "inflação mensal ipca (%)", "#00B0FF"), use_container_width=True)
            g3, g4 = st.columns(2)
            with g3: st.plotly_chart(criar_grafico_macro(df_br, 'Dolar', "dólar comercial (r$)", "#FFFFFF"), use_container_width=True)
            with g4: st.plotly_chart(criar_grafico_macro(df_br, 'Desemprego', "taxa de desemprego pnadc (%)", "#E040FB"), use_container_width=True)

        elif aba_sel == "🇺🇸 estados unidos":
            c1, c2, c3, c4 = st.columns(4)
            v_fed = valor_atual_seguro(df_global, 'FEDFUNDS')
            v_cpi = valor_atual_seguro(df_global, 'CPI_MoM')
            v_dgs10 = valor_atual_seguro(df_global, 'DGS10')
            v_unrate = valor_atual_seguro(df_global, 'UNRATE')
            with c1: metric_card("fed funds rate", fmt_pct(v_fed, sinal=False))
            with c2: metric_card("cpi mensal", fmt_pct(v_cpi, sinal=False))
            with c3: metric_card("treasury 10y", fmt_pct(v_dgs10, sinal=False))
            with c4: metric_card("desemprego (us)", fmt_pct(v_unrate, sinal=False))
            
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(criar_grafico_macro(df_global, 'FEDFUNDS', "fed funds rate (%)", "#00C853"), use_container_width=True)
            with g2: st.plotly_chart(criar_grafico_macro(df_global, 'CPI_MoM', "inflação mensal cpi (%)", "#00B0FF"), use_container_width=True)
            g3, g4 = st.columns(2)
            with g3: st.plotly_chart(criar_grafico_macro(df_global, 'DGS10', "treasury yield 10y (%)", "#FFFFFF"), use_container_width=True)
            with g4: st.plotly_chart(criar_grafico_macro(df_global, 'UNRATE', "taxa de desemprego (us) (%)", "#FF9900"), use_container_width=True)

        elif aba_sel == "🌍 europa/ásia":
            v_ecb = valor_atual_seguro(df_global, 'ECBDFR')
            if v_ecb is not None: st.plotly_chart(criar_grafico_macro(df_global, 'ECBDFR', "bce - taxa de juros europeia (%)", "#FF9900"), use_container_width=True)
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(criar_grafico_macro(df_global, 'IRLTLT01EZM156N', "euro area 10y yield (%)", "#00B0FF"), use_container_width=True)
            with g2: st.plotly_chart(criar_grafico_macro(df_global, 'IRLTLT01JPM156N', "japan 10y yield (%)", "#FF1744"), use_container_width=True)

        elif aba_sel == "🌐 risco":
            section_title("curva de juros eua & spreads de crédito")
            
            c1, c2, c3 = st.columns(3)
            v_vix = valor_atual_seguro(df_global, 'VIXCLS')
            v_t10y2y = valor_atual_seguro(df_global, 'T10Y2Y')
            v_hy = valor_atual_seguro(df_global, 'BAMLH0A0HYM2')
            
            with c1:
                metric_card("vix atual", f"{v_vix:.2f}" if v_vix is not None else "n/d")
            with c2:
                cor_t10 = "bull" if (v_t10y2y is not None and v_t10y2y > 0) else ("bear" if (v_t10y2y is not None and v_t10y2y < 0) else "")
                metric_card("spread 10y-2y", fmt_pct(v_t10y2y, sinal=False) if v_t10y2y is not None else "n/d", cor_delta=cor_t10)
            with c3:
                metric_card("spread hy crédito", fmt_pct(v_hy, sinal=False) if v_hy is not None else "n/d")
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            if v_t10y2y is not None:
                if v_t10y2y < 0:
                    st.warning("⚠️ curva invertida: historicamente precede recessão em 12-18 meses. posicionamento defensivo recomendado.")
                elif 0 <= v_t10y2y <= 0.5:
                    st.info("📊 spread estreito: ciclo de crédito em atenção.")
            
            fig_t10 = criar_grafico_macro(df_global, 'T10Y2Y', "spread 10y-2y (%)", "#00B0FF")
            fig_t10.add_hline(y=0, line_color="#FF1744", line_dash="dash", line_width=1)
            fig_t10.add_annotation(x=0.01, y=0, xref="paper", text="zona de inversão", font=dict(color="#FF1744", size=10, family="Courier New"), showarrow=False, yshift=-14)
            st.plotly_chart(fig_t10, use_container_width=True)
            
            st.plotly_chart(criar_grafico_macro(df_global, 'VIXCLS', "índice vix (cboe volatility index)", "#FF1744"), use_container_width=True)
            st.info("o vix mede a volatilidade esperada do s&p 500.")
            
            st.plotly_chart(criar_grafico_macro(df_global, 'BAMLH0A0HYM2', "spread crédito high yield (%)", "#E040FB"), use_container_width=True)

        elif aba_sel == "🛢️ commodities":
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(criar_grafico_macro(df_comm, 'CL=F', "petróleo wti (us$ / barril)", "#E040FB"), use_container_width=True)
            with g2: st.plotly_chart(criar_grafico_macro(df_comm, 'GC=F', "ouro futuros (us$ / onça)", "#FFEB3B"), use_container_width=True)

        elif aba_sel == "📰 macro news":
            col_news1, col_news2 = st.columns(2)
            with col_news1: renderizar_noticias("SPY", "🇺🇸 radar global (spy etf)")
            with col_news2: renderizar_noticias("EWZ", "🇧🇷 radar brasil (ewz etf)")

with tab_ciclo:
    v_t10y2y = valor_atual_seguro(df_global_master, 'T10Y2Y')
    v_vix = valor_atual_seguro(df_global_master, 'VIXCLS')
    v_hy = valor_atual_seguro(df_global_master, 'BAMLH0A0HYM2')
    
    fase_ciclo, cor_ciclo, setores_ciclo = diagnosticar_ciclo(v_t10y2y, v_vix, v_hy)
    
    section_title("🔄 posicionamento no ciclo econômico")
    
    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        metric_card("fase atual do ciclo", fase_ciclo)
    with col_c2:
        st.markdown(f'<div class="card" style="padding:15px; border-left:4px solid {cor_ciclo};"><div style="font-family:Courier New; font-size:0.72rem; color:#555; margin-bottom:5px;">setores favorecidos neste ciclo:</div><div style="font-family:Courier New; font-size:0.9rem; color:#E0E0E0;">{setores_ciclo}</div></div>', unsafe_allow_html=True)

    section_title("📊 performance setorial s&p 500 (etfs)")
    with st.spinner("carregando retornos setoriais..."):
        df_setores = buscar_retornos_setoriais()
        
    if not df_setores.empty:
        fig_heat = px.imshow(df_setores, color_continuous_scale=[[0, "#FF1744"], [0.5, "#111111"], [1, "#00C853"]], zmin=-15, zmax=15, text_auto=".1f", aspect="auto")
        layout_heat = base_layout(height=420, title="retorno por setor e janela temporal (%)")
        fig_heat.update_layout(**layout_heat)
        fig_heat.update_traces(textfont=dict(family="Courier New", size=11, color="#FFFFFF"))
        fig_heat.update_coloraxes(showscale=False)
        st.plotly_chart(fig_heat, use_container_width=True)
        st.caption("verde = retorno positivo no período | vermelho = retorno negativo | dados: etfs setoriais s&p 500 via yahoo finance")
    else:
        empty_state("📊", "sem dados setoriais", "não foi possível carregar os retornos dos etfs setoriais.")

    section_title("🧠 síntese de rotação (ia)")
    if st.button("gerar análise de rotação setorial >>", type="primary"):
        with st.spinner("o agente está analisando o ciclo e os dados setoriais..."):
            try:
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                contexto_setores = ""
                for index, row in df_setores.iterrows():
                    v_1m = f"{row['1 mês']:.1f}%" if pd.notna(row['1 mês']) else "n/d"
                    v_3m = f"{row['3 meses']:.1f}%" if pd.notna(row['3 meses']) else "n/d"
                    v_6m = f"{row['6 meses']:.1f}%" if pd.notna(row['6 meses']) else "n/d"
                    v_12m = f"{row['12 meses']:.1f}%" if pd.notna(row['12 meses']) else "n/d"
                    contexto_setores += f"{index}: 1m={v_1m}, 3m={v_3m}, 6m={v_6m}, 12m={v_12m}. "
                
                prompt = f"aja como um estrategista de alocação de um fundo de investimentos multimercado. dados do ciclo econômico atual: fase identificada: {fase_ciclo}. yield curve 10y-2y: {v_t10y2y}%. vix: {v_vix}. spread high yield: {v_hy}%. retorno dos etfs setoriais: {contexto_setores}. escreva 4 bullet points curtos em português: 1. fase do ciclo e o que ela implica para alocação. 2. setor com melhor momentum (maior retorno consistente nas janelas). 3. setor para evitar ou reduzir. 4. recomendação de posicionamento para os próximos 3 meses. inicie todas as frases com letra minúscula. sem uso de cifrões."
                response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                status_card("rotação setorial recomendada", response.text, "info")
            except Exception as e:
                st.error(f"erro no agente de ia: {e}")

with tab_overlay:
    st.write("sobreponha a cotação do ativo com indicadores macroeconômicos globais para identificar correlações.")
    
    col_sel_ov, col_man_ov, col_ind = st.columns([3, 2, 3])
    with col_sel_ov:
        opcoes_ov = get_opcoes_selectbox()
        selecao_ov = st.selectbox("ativo:", opcoes_ov, key="overlay_sel")
    with col_man_ov:
        ticker_manual_ov = st.text_input("ou digite:", "", key="overlay_manual").strip().upper()
    with col_ind:
        indicador = st.selectbox("indicador macro:", ["taxa selic (brasil)", "ipca (inflação br)", "fed funds rate (juros eua)", "treasury 10y (eua)", "vix (s&p 500 volatility)"])

    ticker_input = ticker_manual_ov if ticker_manual_ov else (ticker_from_label(selecao_ov) or "PETR4.SA")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("gerar overlay macro", type="primary", use_container_width=True):
        if not ticker_input or ticker_input.startswith("─"):
            st.warning("selecione um ativo válido para iniciar a análise.")
        else:
            with st.spinner(f"buscando histórico de {ticker_input.lower()} e série macroeconômica..."):
                try:
                    stock_data = yf.download(ticker_input, period="5y", auto_adjust=True, progress=False)['Close']
                    if isinstance(stock_data, pd.DataFrame): stock_data = stock_data[ticker_input]
                    stock_data = stock_data.dropna()
                    if hasattr(stock_data.index, 'tz') and stock_data.index.tz is not None: stock_data.index = stock_data.index.tz_localize(None)

                    hoje = datetime.datetime.today()
                    inicio = hoje - datetime.timedelta(days=5*365)
                    macro_data = None
                    macro_name = ""

                    if "selic" in indicador.lower(): macro_data, macro_name = sgs.get({'Selic': 432}, start=inicio)['Selic'], "taxa selic (%)"
                    elif "ipca" in indicador.lower(): macro_data, macro_name = sgs.get({'IPCA': 433}, start=inicio)['IPCA'], "ipca (%)"
                    else:
                        fred = Fred(api_key=st.secrets["FRED_API_KEY"])
                        if "fed funds" in indicador.lower(): macro_data, macro_name = fred.get_series('FEDFUNDS', observation_start=inicio), "fed funds rate (%)"
                        elif "treasury" in indicador.lower(): macro_data, macro_name = fred.get_series('DGS10', observation_start=inicio), "treasury 10y (%)"
                        elif "vix" in indicador.lower(): macro_data, macro_name = fred.get_series('VIXCLS', observation_start=inicio), "índice vix"

                    if macro_data is not None:
                        macro_data = macro_data.dropna()
                        if hasattr(macro_data.index, 'tz') and macro_data.index.tz is not None: macro_data.index = macro_data.index.tz_localize(None)

                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        fig.add_trace(go.Scatter(x=stock_data.index, y=stock_data, name=ticker_input.lower(), line=dict(color="#FF9900", width=2)), secondary_y=False)
                        fig.add_trace(go.Scatter(x=macro_data.index, y=macro_data, name=macro_name, line=dict(color="#00B0FF", dash="dot", width=2)), secondary_y=True)

                        layout_macro = base_layout(height=500, title=f"estudo de correlação: {ticker_input.lower()} vs {macro_name}")
                        fig.update_layout(**layout_macro)
                        fig.update_yaxes(title_text=f"preço {ticker_input.lower()}", showgrid=True, gridcolor='#1e1e1e', secondary_y=False)
                        fig.update_yaxes(title_text=macro_name, showgrid=False, secondary_y=True)
                        fig.update_xaxes(showgrid=True, gridcolor='#1e1e1e')

                        st.plotly_chart(fig, use_container_width=True)
                    else: st.warning("não foi possível obter a série de dados macroeconómicos.")
                except Exception as e: st.error(f"erro ao processar e alinhar os dados: {e}")