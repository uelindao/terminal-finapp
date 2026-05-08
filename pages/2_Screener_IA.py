import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from google import genai
import time
import datetime
from fredapi import Fred
from bcb import sgs

from utils.style import aplicar_tema
from database.db import adicionar_ativo, get_cache_ia, salvar_cache_ia
from utils.tickers import SCREENER_B3, SCREENER_US, XSTOCKS_INDICES

from utils.auth import check_password

if not check_password():
    st.stop()

st.set_page_config(page_title="screener ia", layout="wide", initial_sidebar_state="collapsed")
aplicar_tema()

st.markdown("### 🕵️ screener quantitativo & ia")
st.write("filtre o mercado através de regras quantitativas e utilize a inteligência artificial para refinar o stock picking.")

def detectar_mercado(ticker):
    t = ticker.upper()
    if t.endswith('.SA'): return "brasil"
    elif t.endswith(('.DE', '.PA', '.L', '.AS', '.MI')): return "europa"
    elif t.endswith(('.T', '.KS', '.HK')): return "ásia"
    else: return "eua"

b3_tickers = SCREENER_B3
us_tickers = SCREENER_US
sp500_sample = XSTOCKS_INDICES

st.markdown("#### 1. selecione o universo de ativos")
c_uni1, c_uni2, c_uni3 = st.columns(3)
with c_uni1:
    use_b3 = st.checkbox(f"🇧🇷 b3 ({len(b3_tickers)} ativos)", value=True)
with c_uni2:
    use_us = st.checkbox(f"🌎 xstocks rwa ({len(us_tickers)} ativos)", value=True)
with c_uni3:
    use_bench = st.checkbox(f"📊 etfs / benchmarks ({len(sp500_sample)} etfs)", value=False)

universo = []
if use_b3: universo.extend(b3_tickers)
if use_us: universo.extend(us_tickers)
if use_bench: universo.extend(sp500_sample)

st.markdown("<br>", unsafe_allow_html=True)
with st.expander("⚙️ filtros customizados (pré-ranking)"):
    st.write("estes filtros eliminam empresas que não atendem aos critérios básicos antes da classificação.")
    cf1, cf2, cf3, cf4 = st.columns(4)
    with cf1:
        pl_max = st.slider("p/l máximo:", 0, 100, 30)
    with cf2:
        roe_min = st.slider("roe mínimo (%):", 0, 50, 10)
    with cf3:
        dy_min = st.slider("dy mínimo (%):", 0, 20, 0)
    with cf4:
        mcap_sel = st.selectbox("market cap mínimo:", ["qualquer", "> 1 bilhão", "> 10 bilhões", "> 100 bilhões"])

st.markdown("<br>", unsafe_allow_html=True)
estrategia = st.selectbox(
    "2. selecione a estratégia quantitativa de ranking:", 
    [
        "fórmula mágica (greenblatt) - valor + qualidade", 
        "deep value - menor p/vp", 
        "high yield - maior dividend yield",
        "setup ideal (saúde forte + rsi sobrevendido)"
    ]
)

if st.button("🚀 rodar screener", type="primary", use_container_width=True):
    if not universo:
        st.warning("selecione pelo menos um universo de ativos para rastrear.")
    else:
        barra_progresso = st.progress(0)
        texto_status = st.empty()
        
        texto_status.write("baixando histórico de preços em lote para cálculo de rsi...")
        try:
            hist = yf.download(universo, period="60d", auto_adjust=True, progress=False)['Close']
            if len(universo) == 1:
                hist = hist.to_frame(name=universo[0])
            hist = hist.ffill()

            rsis = {}
            for t in universo:
                try:
                    close = hist[t].dropna()
                    if len(close) >= 15:
                        delta = close.diff()
                        ganho = delta.clip(lower=0).rolling(14).mean()
                        perda = (-delta.clip(upper=0)).rolling(14).mean()
                        rs = ganho / perda
                        rsi = (100 - (100 / (1 + rs))).iloc[-1]
                        rsis[t] = rsi
                    else:
                        rsis[t] = np.nan
                except:
                    rsis[t] = np.nan
        except:
            rsis = {}
            
        dados = []
        total = len(universo)
        
        for idx, t in enumerate(universo):
            texto_status.write(f"analisando fundamentos de {t} ({idx+1}/{total})...")
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
                    'ticker': t, 'nome': nome, 'p/l': pl, 'p/vp': pvp, 
                    'roe%': roe, 'dy%': dy, 'market cap': mcap, 'rsi': rsis.get(t, np.nan)
                })
            except:
                pass 
            
            barra_progresso.progress((idx + 1) / total)
            
        texto_status.empty()
        barra_progresso.empty()
        
        df = pd.DataFrame(dados)
        
        if df.empty:
            st.error("nenhum dado pôde ser coletado.")
        else:
            df = df.dropna(subset=['p/l', 'roe%', 'p/vp']) 
            
            if pl_max < 100:
                df = df[(df['p/l'] <= pl_max) & (df['p/l'] > 0)] 
            if roe_min > 0:
                df = df[df['roe%'] >= roe_min]
            if dy_min > 0:
                df = df[df['dy%'] >= dy_min]
                
            if mcap_sel == "> 1 bilhão": df = df[df['market cap'] >= 1e9]
            elif mcap_sel == "> 10 bilhões": df = df[df['market cap'] >= 10e9]
            elif mcap_sel == "> 100 bilhões": df = df[df['market cap'] >= 100e9]

            if df.empty:
                st.warning("nenhuma empresa sobreviveu aos seus filtros customizados.")
            else:
                df['score'] = 0 

                if "fórmula mágica" in estrategia:
                    df['rank_pl'] = df['p/l'].rank(ascending=True) 
                    df['rank_roe'] = df['roe%'].rank(ascending=False) 
                    df['score'] = df['rank_pl'] + df['rank_roe']
                    df_final = df.sort_values('score', ascending=True).head(5)
                    df_final = df_final.drop(columns=['rank_pl', 'rank_roe'])
                    
                elif "deep value" in estrategia:
                    df = df[df['p/vp'] > 0] 
                    df['score'] = df['p/vp'].rank(ascending=True)
                    df_final = df.sort_values('score', ascending=True).head(5)
                    
                elif "high yield" in estrategia:
                    df['score'] = df['dy%'].rank(ascending=False)
                    df_final = df.sort_values('score', ascending=True).head(5)
                    
                elif "setup ideal" in estrategia:
                    df = df[(df['rsi'] < 35) & (df['roe%'] > 10) & (df['p/l'] > 0) & (df['p/l'] < 25)]
                    df['score'] = df['rsi'].rank(ascending=True) 
                    df_final = df.sort_values('score', ascending=True).head(10)

                st.session_state['screener_top5'] = df_final
                st.session_state['estrategia_usada'] = estrategia

if 'screener_top5' in st.session_state and not st.session_state['screener_top5'].empty:
    df_final = st.session_state['screener_top5']
    estrategia_usada = st.session_state['estrategia_usada']
    
    st.markdown("---")
    st.markdown(f"#### 🏆 top ativos: {estrategia_usada}")
    
    formatacao = {
        'p/l': '{:.2f}', 'p/vp': '{:.2f}', 'roe%': '{:.2f}%', 
        'dy%': '{:.2f}%', 'rsi': '{:.1f}', 'score': '{:.1f}', 'market cap': '${:,.0f}'
    }
    
    def destacar_score(col):
        if col.name in ['score', 'rsi']:
            return ['background-color: #221100; color: #FF9900; font-weight: bold' for _ in col]
        return ['' for _ in col]
        
    cols_to_show = [c for c in df_final.columns if c not in ['rsi'] or "setup ideal" in estrategia_usada]
    
    st.dataframe(
        df_final[cols_to_show].style.format(formatacao).apply(destacar_score, axis=0),
        use_container_width=True, hide_index=True
    )
    
    if st.button("➕ adicionar finalistas à watchlist"):
        for t in df_final['ticker']:
            nome_empresa = df_final[df_final['ticker'] == t]['nome'].iloc[0]
            mercado = detectar_mercado(t)
            adicionar_ativo(t, nome_empresa, mercado)
        st.success(f"✅ ativos adicionados à sua watchlist com sucesso!")

    st.markdown("<br>", unsafe_allow_html=True)
    
    @st.cache_data(ttl=21600, show_spinner=False)
    def buscar_macro_para_ia():
        hoje = datetime.datetime.today()
        inicio = hoje - datetime.timedelta(days=180)
        resultado = {}
        
        # busca a meta selic anualizada (código 432)
        try:
            df_selic = sgs.get({'selic': 432}, start=inicio)
            resultado['selic'] = df_selic['selic'].dropna().iloc[-1]
        except: pass
        
        # ipca mensal
        try:
            df_ipca = sgs.get({'ipca': 433}, start=inicio)
            resultado['ipca'] = df_ipca['ipca'].dropna().iloc[-1]
        except: pass

        # ipca acumulado 12 meses (código 13522)
        try:
            df_ipca_12m = sgs.get({'ipca_12m': 13522}, start=inicio)
            resultado['ipca_12m'] = df_ipca_12m['ipca_12m'].dropna().iloc[-1]
        except: pass

        if "FRED_API_KEY" in st.secrets:
            try:
                fred = Fred(api_key=st.secrets["FRED_API_KEY"])
                resultado['fed']  = fred.get_series('FEDFUNDS', observation_start=inicio).dropna().iloc[-1]
                resultado['vix']  = fred.get_series('VIXCLS', observation_start=inicio).dropna().iloc[-1]
                resultado['dgs10']= fred.get_series('DGS10', observation_start=inicio).dropna().iloc[-1]
            except: pass
        return resultado

    st.markdown("---")
    st.markdown("#### 🧠 análise contextual — ia + macro")

    if st.button("analisar com contexto macro", type="primary", key="btn_ia_contextual"):
        macro = buscar_macro_para_ia()
        tabela_txt = df_final[cols_to_show].to_csv(index=False, float_format='%.2f')

        with st.spinner("cruzando múltiplos com ambiente macroeconômico..."):
            try:
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

                def formatar_macro(valor, is_vix=False):
                    if isinstance(valor, (int, float)):
                        return f"{valor:.1f}" if is_vix else f"{valor:.2f}%"
                    return "n/d"

                selic_str = formatar_macro(macro.get('selic'))
                ipca_str  = formatar_macro(macro.get('ipca'))
                ipca_12m_str = formatar_macro(macro.get('ipca_12m'))
                fed_str   = formatar_macro(macro.get('fed'))
                dgs10_str = formatar_macro(macro.get('dgs10'))
                vix_str   = formatar_macro(macro.get('vix'), is_vix=True)

                prompt = f"""
                você é um gestor de portfólio macro-fundamentalista sênior.

                cenário macroeconômico real e atual (dados oficiais bcb e fed):
                - taxa selic (brasil): {selic_str}
                - ipca mensal (brasil): {ipca_str}
                - ipca acumulado 12 meses (brasil): {ipca_12m_str}
                - fed funds rate (eua): {fed_str}
                - treasury 10y (eua): {dgs10_str}
                - vix: {vix_str}

                estratégia aplicada pelo algoritmo quantitativo: {estrategia_usada}

                top finalistas do screener:
                {tabela_txt}

                responda em português, formatação markdown, máximo 400 palavras. inicie todas as frases e tópicos com letra minúscula.

                ## diagnóstico do ambiente
                o cenário macro atual favorece ou desfavorece a estratégia
                '{estrategia_usada}'? por quê? (baseie-se estritamente nas taxas fornecidas acima, especialmente no juro real frente ao ipca 12m).

                ## ajuste de convicção por ativo
                para cada um dos ativos: aumentar, manter ou reduzir
                convicção dado o macro atual? (tabela: ticker | convicção | razão macroeconômica)

                ## risco macro ignorado pelo algoritmo
                cruzando os indicadores fornecidos (selic, ipca mensal vs 12m, juros eua) com o setor das empresas da lista, qual o maior ponto cego desta carteira?

                ## recomendação de posicionamento
                dada a combinação macro + múltiplos, qual posicionamento faz mais sentido agora?
                """

                resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                
                chave_cache = f'contextual_{hash(tabela_txt)}'
                salvar_cache_ia('SCREENER', chave_cache, resp.text)
                st.markdown(resp.text)
                
            except Exception as e:
                st.error(f"erro ao consultar a ia: {e}")