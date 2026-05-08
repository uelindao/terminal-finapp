import streamlit as st
import pandas as pd
import plotly.express as px
from bcb import sgs
from fredapi import Fred
import yfinance as yf
import datetime
from google import genai

from utils.auth import check_password

if not check_password():
    st.stop()

# Importa o nosso Design System centralizado
from utils.style import aplicar_tema

# --- Configuração da Página ---
st.set_page_config(page_title="Painel Macro Global", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### PAINEL MACROECONÔMICO GLOBAL")

if "FRED_API_KEY" not in st.secrets:
    st.warning("⚠️ **Aviso de Arquitetura:** A chave da API do FRED não foi encontrada no arquivo `secrets.toml`.\n\nSem ela, os dados dos EUA e Risco Global ficarão indisponíveis.")

# --- Motor de Dados Macro (Arquitetura Bulkhead TOTAL) ---
@st.cache_data(ttl=86400, show_spinner=False)
def puxar_historico_mestre():
    hoje = datetime.datetime.today()
    inicio_10a = hoje - datetime.timedelta(days=365 * 10) 
    
    # 1. BRASIL (SGS) - Compartimentos 100% isolados
    series_bcb = {
        'Selic': 432,
        'IPCA': 433,
        'Dolar': 1,
        'Desemprego': 24369
    }
    
    dfs_br_dict = {}
    for nome, codigo in series_bcb.items():
        try:
            # Puxa cada indicador do Brasil separadamente
            df_temp = sgs.get({nome: codigo}, start=inicio_10a)
            if not df_temp.empty:
                dfs_br_dict[nome] = df_temp[nome]
        except Exception:
            pass
            
    df_br = pd.DataFrame(dfs_br_dict) if dfs_br_dict else pd.DataFrame()
    
    # 2. GLOBAL (FRED API OFICIAL) - Compartimentos isolados
    df_global = pd.DataFrame()
    if "FRED_API_KEY" in st.secrets:
        try:
            fred = Fred(api_key=st.secrets["FRED_API_KEY"])
            series_fred = {
                'FEDFUNDS': 'FEDFUNDS', 'CPIAUCSL': 'CPIAUCSL', 'UNRATE': 'UNRATE',
                'DGS10': 'DGS10', 'DGS2': 'DGS2', 'VIXCLS': 'VIXCLS',
                'ECBDFR': 'ECBDFR', 'IRLTLT01EZM156N': 'IRLTLT01EZM156N', 'IRLTLT01JPM156N': 'IRLTLT01JPM156N',
            }
            dfs_global_dict = {}
            for nome, serie_id in series_fred.items():
                try:
                    dfs_global_dict[nome] = fred.get_series(serie_id, observation_start=inicio_10a)
                except Exception:
                    pass
            df_global = pd.DataFrame(dfs_global_dict)
            if 'CPIAUCSL' in df_global.columns:
                df_global['CPI_MoM'] = df_global['CPIAUCSL'].pct_change() * 100
        except Exception:
            pass 
    
    # 3. COMMODITIES (YFINANCE)
    df_commodities = pd.DataFrame()
    try:
        df_commodities = yf.download(['CL=F', 'GC=F'], start=inicio_10a, progress=False)['Close']
        if isinstance(df_commodities, pd.Series): 
            df_commodities = df_commodities.to_frame()
    except Exception:
        pass 
        
    return df_br, df_global, df_commodities

# --- Funções Auxiliares Seguras ---
def valor_atual_seguro(df, coluna):
    if not df.empty and coluna in df.columns and not df[coluna].dropna().empty:
        return df[coluna].dropna().iloc[-1]
    return None

def criar_grafico_macro(df, coluna_y, titulo, cor_linha):
    if df.empty or coluna_y not in df.columns or df[coluna_y].dropna().empty:
        fig = px.line()
        fig.add_annotation(text=f"Sem Dados: {titulo}", x=0.5, y=0.5, showarrow=False, font=dict(color="#FF0000", size=14))
        fig.update_layout(
            title=dict(text=titulo, font=dict(color="#888888", size=14)),
            paper_bgcolor="#010101", plot_bgcolor="#010101", 
            xaxis=dict(visible=False), yaxis=dict(visible=False), height=280
        )
        return fig

    df_plot = df.dropna(subset=[coluna_y])
    fig = px.line(df_plot, x=df_plot.index, y=coluna_y)
    fig.update_layout(
        title=dict(text=titulo, font=dict(color="#888888", size=14)),
        paper_bgcolor="#010101", plot_bgcolor="#010101",
        xaxis=dict(showgrid=True, gridcolor='#222222', title=""),
        yaxis=dict(showgrid=True, gridcolor='#222222', title=""),
        margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified", height=280,
        font=dict(family="Courier New", color="#888888")
    )
    fig.update_traces(line_color=cor_linha, line_width=1.5)
    return fig

# --- Renderizador de Notícias (Blindado) ---
def renderizar_noticias(ticker, titulo_secao):
    st.markdown(f"#### {titulo_secao}")
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
                publisher_data = dados.get('provider', dados.get('publisher', 'Agência Internacional'))
                if isinstance(publisher_data, dict): publisher = publisher_data.get('displayName', 'Agência Internacional')
                else: publisher = publisher_data
                    
                st.markdown(f"""
                <div class="news-box">
                    <div class="news-publisher">{publisher}</div>
                    <a href="{link}" target="_blank" style="text-decoration: none;">
                        <div class="news-title">{titulo}</div>
                    </a>
                </div>
                """, unsafe_allow_html=True)
                noticias_renderizadas += 1
            if noticias_renderizadas == 0:
                st.info("Formato interno de notícias não suportado.")
        else:
            st.info("Sem notícias recentes neste radar.")
    except Exception as e:
        st.error(f"Falha ao sincronizar feed de notícias.")

# --- Execução Visual ---
with st.spinner("Sincronizando feed de Bancos Centrais e Mídia Global via APIs Oficiais..."):
    df_br_master, df_global_master, df_comm_master = puxar_historico_mestre()
    
    # --- SELETOR DE TEMPO ---
    st.markdown("<br>", unsafe_allow_html=True)
    col_espaco, col_filtro = st.columns([7, 3])
    with col_filtro:
        janela = st.radio("HORIZONTE DE TEMPO:", ["3 Anos", "5 Anos", "10 Anos"], index=1, horizontal=True, label_visibility="collapsed")
        
    anos_filtro = int(janela.split()[0])
    data_corte = datetime.datetime.today() - datetime.timedelta(days=365 * anos_filtro)
    
    df_br = df_br_master[df_br_master.index >= data_corte] if not df_br_master.empty else df_br_master
    df_global = df_global_master[df_global_master.index >= data_corte] if not df_global_master.empty else df_global_master
    
    if not df_comm_master.empty:
        df_comm = df_comm_master[df_comm_master.index >= data_corte]
        if isinstance(df_comm.columns, pd.MultiIndex):
            df_comm.columns = df_comm.columns.get_level_values(1)
    else:
        df_comm = df_comm_master

    # --- IA: ANÁLISE MACROECONÔMICA ---
    st.markdown("#### LEITURA MACROECONÔMICA (AI SYNTHESIS)")
    if st.button("GERAR RELATÓRIO DO CENÁRIO ATUAL >>", type="primary"):
        with st.spinner("Processando vetores de juros, inflação e risco global..."):
            try:
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                
                prompt = f"""
                Aja como um Estrategista Macro de um Hedge Fund. 
                BRASIL: Selic {valor_atual_seguro(df_br, 'Selic') or 0:.2f}%, IPCA {valor_atual_seguro(df_br, 'IPCA') or 0:.2f}%.
                EUA: Fed Funds {valor_atual_seguro(df_global, 'FEDFUNDS') or 0:.2f}%, CPI {valor_atual_seguro(df_global, 'CPI_MoM') or 0:.2f}%.
                EUROPA: BCE {valor_atual_seguro(df_global, 'ECBDFR') or 0:.2f}%.
                RISCO: VIX {valor_atual_seguro(df_global, 'VIXCLS') or 0:.2f}.
                
                Escreva 3 bullet points curtos em português:
                1. Relação juros Brasil x EUA.
                2. Temperatura inflacionária global.
                3. Apetite ao risco (VIX).
                Sem uso de cifrões.
                """
                response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                st.info(response.text)
            except Exception as e:
                st.error(f"Erro no agente de IA: {e}")
    
    st.markdown("---")

    # --- ABAS DE NAVEGAÇÃO ---
    aba_br, aba_us, aba_eu_asia, aba_risco, aba_comm, aba_news = st.tabs([
        "🇧🇷 BRASIL", "🇺🇸 ESTADOS UNIDOS", "🌍 EUROPA/ÁSIA", "🌐 RISCO", "🛢️ COMMODITIES", "📰 MACRO NEWS"
    ])
    
    with aba_br:
        c1, c2, c3, c4 = st.columns(4)
        v_selic = valor_atual_seguro(df_br, 'Selic')
        v_ipca = valor_atual_seguro(df_br, 'IPCA')
        v_dolar = valor_atual_seguro(df_br, 'Dolar')
        v_desemp = valor_atual_seguro(df_br, 'Desemprego')
        
        c1.metric("SELIC ATUAL", f"{v_selic:.2f}%" if v_selic is not None else "N/D")
        c2.metric("IPCA MENSAL", f"{v_ipca:.2f}%" if v_ipca is not None else "N/D")
        c3.metric("DÓLAR (PTAX)", f"R$ {v_dolar:.2f}" if v_dolar is not None else "N/D")
        c4.metric("DESEMPREGO", f"{v_desemp:.1f}%" if v_desemp is not None else "N/D")
        
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(criar_grafico_macro(df_br, 'Selic', "TAXA SELIC HISTÓRICA (%)", "#00FF00"), use_container_width=True)
        with g2: st.plotly_chart(criar_grafico_macro(df_br, 'IPCA', "INFLAÇÃO MENSAL IPCA (%)", "#00FFFF"), use_container_width=True)
        g3, g4 = st.columns(2)
        with g3: st.plotly_chart(criar_grafico_macro(df_br, 'Dolar', "DÓLAR COMERCIAL (R$)", "#FFFFFF"), use_container_width=True)
        with g4: st.plotly_chart(criar_grafico_macro(df_br, 'Desemprego', "TAXA DE DESEMPREGO PNADC (%)", "#FF00FF"), use_container_width=True)

    with aba_us:
        c1, c2, c3, c4 = st.columns(4)
        v_fed = valor_atual_seguro(df_global, 'FEDFUNDS')
        v_cpi = valor_atual_seguro(df_global, 'CPI_MoM')
        v_dgs10 = valor_atual_seguro(df_global, 'DGS10')
        v_unrate = valor_atual_seguro(df_global, 'UNRATE')
        
        c1.metric("FED FUNDS RATE", f"{v_fed:.2f}%" if v_fed is not None else "N/D")
        c2.metric("CPI MENSAL", f"{v_cpi:.2f}%" if v_cpi is not None else "N/D")
        c3.metric("TREASURY 10Y", f"{v_dgs10:.2f}%" if v_dgs10 is not None else "N/D")
        c4.metric("DESEMPREGO (US)", f"{v_unrate:.1f}%" if v_unrate is not None else "N/D")
        
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(criar_grafico_macro(df_global, 'FEDFUNDS', "FED FUNDS RATE (%)", "#00FF00"), use_container_width=True)
        with g2: st.plotly_chart(criar_grafico_macro(df_global, 'CPI_MoM', "INFLAÇÃO MENSAL CPI (%)", "#00FFFF"), use_container_width=True)
        g3, g4 = st.columns(2)
        with g3: st.plotly_chart(criar_grafico_macro(df_global, 'DGS10', "TREASURY YIELD 10Y (%)", "#FFFFFF"), use_container_width=True)
        with g4: st.plotly_chart(criar_grafico_macro(df_global, 'UNRATE', "TAXA DE DESEMPREGO (US) (%)", "#FF9900"), use_container_width=True)

    with aba_eu_asia:
        v_ecb = valor_atual_seguro(df_global, 'ECBDFR')
        if v_ecb is not None:
            st.plotly_chart(criar_grafico_macro(df_global, 'ECBDFR', "BCE - TAXA DE JUROS EUROPEIA (%)", "#FF9900"), use_container_width=True)
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(criar_grafico_macro(df_global, 'IRLTLT01EZM156N', "EURO AREA 10Y YIELD (%)", "#0088FF"), use_container_width=True)
        with g2: st.plotly_chart(criar_grafico_macro(df_global, 'IRLTLT01JPM156N', "JAPAN 10Y YIELD (%)", "#FF5555"), use_container_width=True)

    with aba_risco:
        st.plotly_chart(criar_grafico_macro(df_global, 'VIXCLS', "ÍNDICE VIX (CBOE VOLATILITY INDEX)", "#FF0000"), use_container_width=True)
        st.info("O VIX mede a volatilidade esperada do S&P 500.")

    with aba_comm:
        st.markdown("#### MOTORES INFLACIONÁRIOS E RESERVAS DE VALOR")
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(criar_grafico_macro(df_comm, 'CL=F', "PETRÓLEO WTI (US$ / BARRIL)", "#AA00FF"), use_container_width=True)
        with g2: st.plotly_chart(criar_grafico_macro(df_comm, 'GC=F', "OURO FUTUROS (US$ / ONÇA)", "#FFD700"), use_container_width=True)

    with aba_news:
        st.write("Interceptação de manchetes globais focadas em índices de mercado amplo.")
        col_news1, col_news2 = st.columns(2)
        with col_news1:
            renderizar_noticias("SPY", "🇺🇸 RADAR GLOBAL (SPY ETF)")
        with col_news2:
            renderizar_noticias("EWZ", "🇧🇷 RADAR BRASIL (EWZ ETF)")