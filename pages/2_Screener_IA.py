import streamlit as st
import yfinance as yf
import pandas as pd
from google import genai
import time

st.set_page_config(page_title="screener quantitativo & ia", layout="wide")

st.title("🎯 screener quantitativo & ia")
st.write("motor de busca autônomo: filtra o mercado e passa os finalistas para o comitê de IA.")

# --- universo de cobertura (amostra para testes rápidos) ---
tickers_universo = [
    "PETR4.SA", "VALE3.SA", "ITUB4.SA", "WEGE3.SA", "BBAS3.SA", 
    "ABEV3.SA", "RENT3.SA", "CSAN3.SA", "PRIO3.SA", "GGBR4.SA",
    "AAPL", "MSFT", "NVDA", "KO", "JPM"
]

# --- interface do screener ---
estrategia = st.selectbox(
    "selecione a estratégia do fundo:",
    [
        "fórmula mágica (greenblatt) - alto roe e baixo p/l",
        "dividendos (value) - alto yield e maturidade",
        "crescimento (growth) - expansão de receita agressiva"
    ]
)

st.markdown("---")

if st.button("rodar varredura do mercado", type="primary"):
    
    # container para UX (feedback visual pro usuário)
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    dados_acoes = []
    
    # 1. ETAPA DE FORÇA BRUTA (PYTHON VARRENDO O MERCADO)
    total_tickers = len(tickers_universo)
    for i, ticker in enumerate(tickers_universo):
        status_text.text(f"coletando fundamentos de {ticker} ({i+1}/{total_tickers})...")
        progress_bar.progress((i + 1) / total_tickers)
        
        try:
            acao = yf.Ticker(ticker)
            info = acao.info
            
            # extrai os dados crus
            pl = info.get('trailingPE', None)
            roe = info.get('returnOnEquity', None)
            dy = info.get('dividendYield', 0.0)
            crescimento = info.get('revenueGrowth', 0.0)
            
            # filtra lixo (empresas com prejuízo ou sem dados)
            if pl and roe and pl > 0:
                dados_acoes.append({
                    "ticker": ticker,
                    "P/L": pl,
                    "ROE": roe * 100, # converte pra %
                    "DY": dy * 100 if dy else 0.0,
                    "Crescimento": crescimento * 100 if crescimento else 0.0
                })
        except:
            pass # se der erro num ticker, ignora e vai pro próximo
            
    df_mercado = pd.DataFrame(dados_acoes)
    
    # 2. ETAPA DE FILTRAGEM (ALGORITMOS)
    status_text.text("aplicando algoritmos de filtragem...")
    time.sleep(1) # pausa dramática pro usuário ver que o sistema está calculando
    
    if "fórmula mágica" in estrategia:
        # ranqueia por roe (maior é melhor) e p/l (menor é melhor)
        df_mercado['rank_roe'] = df_mercado['ROE'].rank(ascending=False)
        df_mercado['rank_pl'] = df_mercado['P/L'].rank(ascending=True)
        df_mercado['score_magico'] = df_mercado['rank_roe'] + df_mercado['rank_pl']
        # pega as 3 menores pontuações
        top_finalistas = df_mercado.sort_values('score_magico').head(3)
        
    elif "dividendos" in estrategia:
        top_finalistas = df_mercado.sort_values('DY', ascending=False).head(3)
        
    elif "crescimento" in estrategia:
        top_finalistas = df_mercado.sort_values('Crescimento', ascending=False).head(3)
    
    # limpa a tela de loading
    status_text.empty()
    progress_bar.empty()
    
    # mostra a tabela final pro usuário
    st.subheader(f"🏆 top 3 finalistas: {estrategia.split(' - ')[0]}")
    st.dataframe(top_finalistas.style.format(precision=2), use_container_width=True)
    
    # 3. ETAPA DO COMITÊ (IA)
    st.markdown("---")
    st.subheader("🤖 veredito do comitê de IA")
    
    with st.spinner("ia está revisando as finalistas para dar a cartada final..."):
        try:
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            
            tabela_texto = top_finalistas.to_csv(index=False)
            
            prompt = f"""
            você é o head de investimentos de um fundo quantitativo.
            nosso algoritmo rodou a estratégia de '{estrategia}' em todo o mercado e filtrou estas 3 empresas finalistas.
            
            DADOS DAS FINALISTAS:
            {tabela_texto}
            
            sua tarefa:
            escreva um veredito rápido comparando as três.
            indique claramente QUAL das três você compraria hoje e o porquê, baseado estritamente na relação entre as métricas listadas.
            inicie todas as frases e títulos com letras minúsculas (brand guideline corporativo).
            não invente dados que não estão na tabela.
            """
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            
            texto_seguro = response.text.replace("$", r"\$")
            st.write(texto_seguro)
            
        except Exception as ia_error:
            st.error(f"erro na IA: {ia_error}")