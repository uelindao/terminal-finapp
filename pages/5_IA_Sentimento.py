import streamlit as st
import yfinance as yf
from google import genai

from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label

from utils.auth import check_password

if not check_password():
    st.stop()

# --- Configuração da Página ---
st.set_page_config(page_title="IA Sentimento", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 🧠 ANÁLISE DE SENTIMENTO POR IA")
st.write("Interceptação de manchetes recentes e síntese de humor de mercado guiada por inteligência artificial.")

# ==========================================
# SEÇÃO DE BUSCA PADRONIZADA (Briefing 3)
# ==========================================
col_busca, col_vazia = st.columns([4, 6])
with col_busca:
    opcoes = get_opcoes_selectbox()
    selecao = st.selectbox("SELECIONE O ATIVO PARA ANÁLISE DE HUMOR:", opcoes)

    ticker_manual = ""
    if "digitar" in selecao.lower():
        ticker_manual = st.text_input(
            "Digite o ticker (Ex: KLBN11.SA, COIN):", ""
        ).strip().upper()

    ticker_input = ticker_manual if ticker_manual else (ticker_from_label(selecao) or "")

if not ticker_input or ticker_input.startswith("─"):
    st.info("Selecione um ativo para iniciar a análise.")
    st.stop()

# ==========================================
# FUNÇÕES DE APOIO
# ==========================================
def extrair_titulo_noticia(noticia):
    """Extrai o título de uma notícia do yfinance de forma blindada."""
    content = noticia.get('content', None)
    if isinstance(content, dict):
        titulo = content.get('title', '')
        if titulo:
            return titulo
    titulo = noticia.get('title', '')
    if titulo:
        return titulo
    return noticia.get('headline', '')

# ==========================================
# PROCESSAMENTO E IA
# ==========================================
if st.button("ANALISAR SENTIMENTO", type="primary"):
    with st.spinner(f"Interceptando notícias recentes de {ticker_input}..."):
        try:
            acao = yf.Ticker(ticker_input)
            noticias = acao.news

            if noticias:
                manchetes = []
                for noticia in noticias[:10]:
                    titulo = extrair_titulo_noticia(noticia)
                    if titulo:
                        manchetes.append(titulo)

                manchetes_texto = "\n".join([f"- {m}" for m in manchetes])

                col_ia, col_news = st.columns([6, 4])

                with col_news:
                    st.markdown("#### RAW NEWS FEED")
                    st.code(manchetes_texto, language="text")

                with col_ia:
                    st.markdown("#### VÉRTICE DA IA")
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        prompt = f"""
                        Aja como um analista de sentimento de mercado. Leia as manchetes abaixo 
                        sobre a empresa {ticker_input} e resuma o sentimento geral em 3 bullet points, 
                        dizendo se é otimista, pessimista ou neutro:
                        
                        {manchetes_texto}
                        """
                        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        st.info(response.text)
                    except Exception as e:
                        st.error(f"Erro de conexão com o agente de IA: {e}")
            else:
                st.warning(f"Nenhuma notícia recente encontrada nos radares para o ticker {ticker_input}.")
                
        except Exception as e:
            st.error(f"Falha ao conectar com o serviço de cotações/notícias: {e}")