import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from google import genai
import time
import datetime
from fredapi import Fred
from bcb import sgs

# Importa o Design System, Banco de Dados e Catálogo Central
from utils.style import aplicar_tema
from database.db import adicionar_ativo, get_cache_ia, salvar_cache_ia
from utils.tickers import SCREENER_B3, SCREENER_US, XSTOCKS_INDICES

# --- Configuração da Página ---
st.set_page_config(page_title="Screener IA", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 🕵️ SCREENER QUANTITATIVO & IA")
st.write("Filtre o mercado através de regras quantitativas e utilize a Inteligência Artificial para refinar o stock picking.")

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
def detectar_mercado(ticker):
    t = ticker.upper()
    if t.endswith('.SA'): return "B3 (Brasil)"
    elif t.endswith(('.DE', '.PA', '.L', '.AS', '.MI')): return "Europa"
    elif t.endswith(('.T', '.KS', '.HK')): return "Ásia"
    else: return "EUA (Nyse/Nasdaq)"

# ==========================================
# 1. UNIVERSO EXPANDIDO (Conectado ao utils/tickers.py)
# ==========================================
B3_TICKERS = SCREENER_B3
US_TICKERS = SCREENER_US
SP500_SAMPLE = XSTOCKS_INDICES

st.markdown("#### 1. SELECIONE O UNIVERSO DE ATIVOS")
c_uni1, c_uni2, c_uni3 = st.columns(3)
with c_uni1:
    use_b3 = st.checkbox(f"🇧🇷 B3 ({len(B3_TICKERS)} ativos — carteira + bluechips BR)", value=True)
with c_uni2:
    use_us = st.checkbox(f"🌎 XStocks RWA ({len(US_TICKERS)} ativos — NYSE/NASDAQ operáveis)", value=True)
with c_uni3:
    use_bench = st.checkbox(f"📊 ETFs / Benchmarks ({len(SP500_SAMPLE)} ETFs)", value=False)

universo = []
if use_b3: universo.extend(B3_TICKERS)
if use_us: universo.extend(US_TICKERS)
if use_bench: universo.extend(SP500_SAMPLE)

# ==========================================
# 2. FILTROS CUSTOMIZADOS E ESTRATÉGIA
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("⚙️ FILTROS CUSTOMIZADOS (Pré-Ranking)"):
    st.write("Estes filtros eliminam empresas que não atendem aos critérios básicos ANTES da classificação.")
    cf1, cf2, cf3, cf4 = st.columns(4)
    with cf1:
        pl_max = st.slider("P/L Máximo:", 0, 100, 30)
    with cf2:
        roe_min = st.slider("ROE Mínimo (%):", 0, 50, 10)
    with cf3:
        dy_min = st.slider("DY Mínimo (%):", 0, 20, 0)
    with cf4:
        mcap_sel = st.selectbox("Market Cap Mínimo:", ["Qualquer", "> 1 Bilhão", "> 10 Bilhões", "> 100 Bilhões"])

st.markdown("<br>", unsafe_allow_html=True)
estrategia = st.selectbox(
    "2. SELECIONE A ESTRATÉGIA QUANTITATIVA DE RANKING:", 
    [
        "Fórmula Mágica (Greenblatt) - Valor + Qualidade", 
        "Deep Value - Menor P/VP", 
        "High Yield - Maior Dividend Yield"
    ]
)

if st.button("🚀 RODAR SCREENER", type="primary", use_container_width=True):
    if not universo:
        st.warning("Selecione pelo menos um universo de ativos para rastrear.")
    else:
        barra_progresso = st.progress(0)
        texto_status = st.empty()
        
        dados = []
        total = len(universo)
        
        for idx, t in enumerate(universo):
            texto_status.write(f"Analisando fundamentos de {t} ({idx+1}/{total})...")
            try:
                info = yf.Ticker(t).info
                
                pl = info.get('trailingPE', info.get('forwardPE', np.nan))
                pvp = info.get('priceToBook', np.nan)
                mcap = info.get('marketCap', 0)
                
                roe_raw = info.get('returnOnEquity', None)
                roe = roe_raw * 100 if roe_raw is not None else np.nan
                
                dy_raw = info.get('dividendYield', None)
                dy = dy_raw * 100 if dy_raw is not None else 0
                
                nome = info.get('shortName', t)
                
                dados.append({
                    'Ticker': t, 'Nome': nome, 'P/L': pl, 'P/VP': pvp, 
                    'ROE%': roe, 'DY%': dy, 'Market Cap': mcap
                })
            except:
                pass 
            
            barra_progresso.progress((idx + 1) / total)
            
        texto_status.empty()
        barra_progresso.empty()
        
        df = pd.DataFrame(dados)
        
        if df.empty:
            st.error("Nenhum dado pôde ser coletado.")
        else:
            # ------------------------------------------
            # APLICAÇÃO DOS FILTROS CUSTOMIZADOS
            # ------------------------------------------
            df = df.dropna(subset=['P/L', 'ROE%', 'P/VP']) 
            
            if pl_max < 100:
                df = df[(df['P/L'] <= pl_max) & (df['P/L'] > 0)] 
            if roe_min > 0:
                df = df[df['ROE%'] >= roe_min]
            if dy_min > 0:
                df = df[df['DY%'] >= dy_min]
                
            if mcap_sel == "> 1 Bilhão": df = df[df['Market Cap'] >= 1e9]
            elif mcap_sel == "> 10 Bilhões": df = df[df['Market Cap'] >= 10e9]
            elif mcap_sel == "> 100 Bilhões": df = df[df['Market Cap'] >= 100e9]

            if df.empty:
                st.warning("Nenhuma empresa sobreviveu aos seus Filtros Customizados. Tente relaxar os critérios.")
            else:
                # ------------------------------------------
                # APLICAÇÃO DO RANKING (ESTRATÉGIA)
                # ------------------------------------------
                df['SCORE'] = 0 

                if "Fórmula Mágica" in estrategia:
                    df['Rank_PL'] = df['P/L'].rank(ascending=True) 
                    df['Rank_ROE'] = df['ROE%'].rank(ascending=False) 
                    df['SCORE'] = df['Rank_PL'] + df['Rank_ROE']
                    df_final = df.sort_values('SCORE', ascending=True).head(5)
                    df_final = df_final.drop(columns=['Rank_PL', 'Rank_ROE'])
                    
                elif "Deep Value" in estrategia:
                    df = df[df['P/VP'] > 0] 
                    df['SCORE'] = df['P/VP'].rank(ascending=True)
                    df_final = df.sort_values('SCORE', ascending=True).head(5)
                    
                elif "High Yield" in estrategia:
                    df['SCORE'] = df['DY%'].rank(ascending=False)
                    df_final = df.sort_values('SCORE', ascending=True).head(5)

                st.session_state['screener_top5'] = df_final
                st.session_state['estrategia_usada'] = estrategia

# ==========================================
# 3, 4 E IA: EXIBIÇÃO DE RESULTADOS E AÇÕES
# ==========================================
if 'screener_top5' in st.session_state and not st.session_state['screener_top5'].empty:
    df_final = st.session_state['screener_top5']
    estrategia_usada = st.session_state['estrategia_usada']
    
    st.markdown("---")
    st.markdown(f"#### 🏆 TOP 5 FINALISTAS: {estrategia_usada.upper()}")
    
    formatacao = {
        'P/L': '{:.2f}', 'P/VP': '{:.2f}', 'ROE%': '{:.2f}%', 
        'DY%': '{:.2f}%', 'SCORE': '{:.1f}', 'Market Cap': '${:,.0f}'
    }
    
    def destacar_score(col):
        if col.name == 'SCORE':
            return ['background-color: #221100; color: #FF9900; font-weight: bold' for _ in col]
        return ['' for _ in col]
    
    st.dataframe(
        df_final.style.format(formatacao).apply(destacar_score, axis=0),
        use_container_width=True, hide_index=True
    )
    
    if st.button("➕ ADICIONAR FINALISTAS À WATCHLIST"):
        for t in df_final['Ticker']:
            nome_empresa = df_final[df_final['Ticker'] == t]['Nome'].iloc[0]
            mercado = detectar_mercado(t)
            adicionar_ativo(t, nome_empresa, mercado)
        st.success(f"✅ {len(df_final)} ativos adicionados à sua Watchlist com sucesso!")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # ==========================================
    # ANÁLISE IA CONTEXTUAL MACRO (Briefing 4)
    # ==========================================
    @st.cache_data(ttl=21600, show_spinner=False)
    def buscar_macro_para_ia():
        hoje = datetime.datetime.today()
        inicio = hoje - datetime.timedelta(days=30)
        resultado = {}
        try:
            df_br = sgs.get({'Selic': 432, 'IPCA': 433}, start=inicio)
            if not df_br.empty:
                resultado['selic'] = df_br['Selic'].dropna().iloc[-1]
                resultado['ipca']  = df_br['IPCA'].dropna().iloc[-1]
        except: pass
        if "FRED_API_KEY" in st.secrets:
            try:
                fred = Fred(api_key=st.secrets["FRED_API_KEY"])
                resultado['fed']  = fred.get_series('FEDFUNDS').iloc[-1]
                resultado['vix']  = fred.get_series('VIXCLS').iloc[-1]
                resultado['dgs10']= fred.get_series('DGS10').iloc[-1]
            except: pass
        return resultado

    st.markdown("---")
    st.markdown("#### 🧠 ANÁLISE CONTEXTUAL — IA + MACRO")

    if st.button("ANALISAR COM CONTEXTO MACRO", type="primary", key="btn_ia_contextual"):
        macro = buscar_macro_para_ia()
        tabela_txt = df_final.to_csv(index=False, float_format='%.2f')

        with st.spinner("Cruzando múltiplos com ambiente macroeconômico..."):
            try:
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

                # BLINDAGEM ANTI-CRASH PARA VARIÁVEIS MACRO
                def formatar_macro(valor, is_vix=False):
                    if isinstance(valor, (int, float)):
                        return f"{valor:.1f}" if is_vix else f"{valor:.2f}%"
                    return "N/D"

                selic_str = formatar_macro(macro.get('selic'))
                ipca_str  = formatar_macro(macro.get('ipca'))
                fed_str   = formatar_macro(macro.get('fed'))
                dgs10_str = formatar_macro(macro.get('dgs10'))
                vix_str   = formatar_macro(macro.get('vix'), is_vix=True)

                prompt = f"""
                Você é um gestor de portfólio macro-fundamentalista sênior.

                CENÁRIO MACROECONÔMICO ATUAL:
                - Selic: {selic_str}
                - IPCA mensal: {ipca_str}
                - Fed Funds Rate (EUA): {fed_str}
                - Treasury 10Y (EUA): {dgs10_str}
                - VIX: {vix_str}

                ESTRATÉGIA APLICADA PELO ALGORITMO: {estrategia_usada}

                TOP 5 FINALISTAS DO SCREENER:
                {tabela_txt}

                Responda em português, formatação markdown, máximo 400 palavras:

                ## Diagnóstico do Ambiente
                O cenário macro atual favorece ou desfavorece a estratégia
                '{estrategia_usada}'? Por quê? (1 parágrafo)

                ## Ajuste de Convicção por Ativo
                Para cada um dos 5 ativos: aumentar, manter ou reduzir
                convicção dado o macro atual? (tabela: Ticker | Convicção | Razão)

                ## Risco Macro Ignorado pelo Algoritmo
                Qual o maior risco macroeconômico que o screener quantitativo
                não captura para esta cesta específica?

                ## Recomendação de Posicionamento
                Dada a combinação macro + múltiplos, qual posicionamento
                (concentrado/diversificado, defensivo/agressivo) faz mais
                sentido agora?

                Tom: institucional, analítico, baseado em dados.
                Sem recomendação explícita de compra/venda.
                """

                resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                
                chave_cache = f'contextual_{hash(tabela_txt)}'
                salvar_cache_ia('SCREENER', chave_cache, resp.text)
                st.markdown(resp.text)
                
            except Exception as e:
                st.error(f"Erro ao consultar a IA: {e}")