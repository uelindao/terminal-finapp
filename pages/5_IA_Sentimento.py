import streamlit as st
import yfinance as yf
from google import genai

st.set_page_config(page_title="Scanner de Sentimento", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #010101; color: #E0E0E0; }
    h1, h2, h3, h4, h5, h6 { color: #FF9900 !important; font-family: 'Courier New', Courier, monospace; text-transform: uppercase; font-size: 1.2rem; margin-bottom: 0px; }
    .block-container { padding-top: 3.5rem; padding-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("### IA SENTIMENTAL & NEWS SCANNER")
st.write("Agente autônomo de processamento de linguagem natural (NLP) para leitura de fluxo de notícias.")

col1, col2 = st.columns([2, 8])
with col1:
    ticker = st.text_input("TICKER PARA SCAN:", value="NVDA").upper()

st.markdown("---")

if st.button("RODAR VARREDURA DE SENTIMENTO >>", type="primary"):
    with st.spinner(f"Interceptando manchetes globais para {ticker}..."):
        try:
            acao = yf.Ticker(ticker)
            noticias = acao.news
            
            if noticias:
                # Extrai apenas os títulos das notícias
                manchetes = [noticia['title'] for noticia in noticias[:10]] # Limita as 10 mais recentes
                manchetes_texto = "\n".join([f"- {m}" for m in manchetes])
                
                # Exibe as manchetes cruas no painel lateral
                col_ia, col_news = st.columns([6, 4])
                
                with col_news:
                    st.markdown("#### RAW NEWS FEED")
                    st.code(manchetes_texto, language="text")
                
                with col_ia:
                    st.markdown("#### VÉRTICE DA IA")
                    
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    prompt = f"""
                    Você é um analista quantitativo focado em NLP (Natural Language Processing).
                    Analise as seguintes manchetes recentes sobre a empresa {ticker}:
                    
                    {manchetes_texto}
                    
                    Sua tarefa:
                    1. Defina o sentimento geral do mercado em UMA palavra: BULLISH (Otimista), BEARISH (Pessimista) ou NEUTRAL (Neutro).
                    2. Escreva um parágrafo rápido justificando o sentimento com base nos títulos.
                    
                    Responda em português, tom institucional, sem cifrões.
                    """
                    
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    st.info(response.text)
                    
            else:
                st.warning(f"Sem fluxo de notícias recente para {ticker} nas bases americanas.")
                
        except Exception as e:
            st.error(f"Erro na varredura: {e}")