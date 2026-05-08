import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
from google import genai
from fredapi import Fred
from bcb import sgs

from utils.auth import check_password

if not check_password():
    st.stop()

# Importações do projeto
from utils.style import aplicar_tema
from database.db import (
    listar_watchlist, get_health_scores, get_pesos, 
    get_historico_multiplos, get_cache_ia, salvar_cache_ia
)

# --- Configuração da Página ---
st.set_page_config(page_title="Insights Cruzados", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### ⚡ INSIGHTS CRUZADOS — ANÁLISE MULTI-DIMENSIONAL")
st.write("Análises avançadas que combinam técnica, fundamentos, macroeconomia e a sua posição atual.")

# ==========================================
# 1. COLETA DE DADOS GLOBAIS E MACRO
# ==========================================
watchlist = listar_watchlist()

if not watchlist:
    st.info("A sua Watchlist está vazia. Adicione ativos para gerar insights.")
    st.stop()

@st.cache_data(ttl=86400, show_spinner=False)
def coletar_macro_1ano():
    """Coleta dados macro do último ano para cálculo de correlação."""
    hoje = datetime.datetime.today()
    inicio = hoje - datetime.timedelta(days=365)
    macro_df = pd.DataFrame()
    
    # SELIC (SGS 11 - Taxa Selic diária)
    try:
        selic = sgs.get({'Selic': 11}, start=inicio)
        macro_df['Selic'] = selic['Selic']
    except:
        pass
        
    # VIX (FRED)
    if "FRED_API_KEY" in st.secrets:
        try:
            fred = Fred(api_key=st.secrets["FRED_API_KEY"])
            vix = fred.get_series('VIXCLS', observation_start=inicio)
            macro_df['VIX'] = vix
        except:
            pass
            
    if not macro_df.empty:
        # Preenche buracos de fim de semana e calcula variações percentuais
        macro_df = macro_df.ffill().pct_change().dropna()
        
    return macro_df

# Carregamento de Banco de Dados Local
pesos = {p['ticker']: p['peso'] for p in get_pesos()}
health_data = {h['ticker']: h.get('score', 50) for h in get_health_scores()}
macro_hist = coletar_macro_1ano()

# Estrutura para guardar todos os insights gerados (para a IA no final)
insights_compilados = []

# ==========================================
# 2. MOTOR DE INSIGHTS POR ATIVO
# ==========================================
st.markdown("---")
st.markdown("#### 🔍 DIAGNÓSTICOS INDIVIDUAIS CRUZADOS")

with st.spinner("Calculando cruzamentos dimensionais para a sua carteira..."):
    
    cols = st.columns(3)
    col_idx = 0
    
    for item in watchlist:
        t = item['ticker']
        peso_ativo = pesos.get(t, 0)
        h_score = health_data.get(t, 50)
        insights_ativo = []
        
        try:
            # 2.1 Coleta Histórico de Preços (1 Ano)
            tk = yf.Ticker(t)
            hist = tk.history(period="1y")
            
            if len(hist) < 50:
                continue
                
            close = hist['Close']
            
            # Cálculo de RSI
            delta = close.diff()
            ganho = delta.clip(lower=0).rolling(14).mean()
            perda = (-delta.clip(upper=0)).rolling(14).mean()
            rs = ganho / perda
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            
            # 2.2 Análise do Histórico de Múltiplos
            hist_mult = get_historico_multiplos(t)
            pl_percentil = 50
            if len(hist_mult) >= 30:
                df_hm = pd.DataFrame(hist_mult)
                pl_atual = df_hm['pl'].dropna().iloc[-1] if not df_hm['pl'].dropna().empty else None
                if pl_atual:
                    serie_pl = df_hm['pl'].dropna()
                    pl_percentil = (serie_pl < pl_atual).mean() * 100
                    
            # 2.3 Cálculo de Correlações Macro
            corr_selic = 0
            corr_vix = 0
            if not macro_hist.empty:
                retornos_ativo = close.pct_change().dropna()
                # Alinha os índices de data
                if hasattr(retornos_ativo.index, 'tz') and retornos_ativo.index.tz is not None:
                    retornos_ativo.index = retornos_ativo.index.tz_localize(None)
                    
                df_corr = pd.concat([retornos_ativo, macro_hist], axis=1).dropna()
                if not df_corr.empty and len(df_corr) > 30:
                    if 'Selic' in df_corr: corr_selic = df_corr[close.name].corr(df_corr['Selic'])
                    if 'VIX' in df_corr: corr_vix = df_corr[close.name].corr(df_corr['VIX'])

            # ==========================================
            # AVALIAÇÃO DAS CONDIÇÕES E GERAÇÃO DE INSIGHTS
            # ==========================================
            
            # INSIGHT 1: Momento vs Valuation
            if rsi > 70 and pl_percentil > 80:
                insights_ativo.append(("🔴 DUPLO RISCO", "Tecnicamente sobrecomprado E fundamentalmente no pico de precificação histórico. Risco severo de correção."))
            elif rsi > 70 and pl_percentil < 50:
                insights_ativo.append(("🟢 MOMENTUM SAUDÁVEL", "Força compradora técnica (RSI alto), mas com P/L ainda abaixo das médias históricas. O rali tem lastro."))
            elif rsi < 30 and pl_percentil < 30:
                insights_ativo.append(("🟢 DUPLA OPORTUNIDADE", "Oversold extremo no gráfico E múltiplos descontados historicamente. Excelente zona de acumulação."))
            elif rsi < 30 and pl_percentil > 70:
                insights_ativo.append(("🔴 QUEDA MERECIDA", "Preço caiu (RSI baixo), mas os lucros caíram mais rápido (P/L no pico). Evitar facas a cair."))

            # INSIGHT 2: Correlação Macro vs Posição
            if peso_ativo > 5 and corr_selic < -0.3:
                insights_ativo.append(("📉 RISCO DE JUROS", f"Representa {peso_ativo}% da sua carteira e tem forte correlação inversa com a Selic. Altas de juros vão penalizar fortemente esta posição."))
            if peso_ativo > 0 and corr_vix > 0.3:
                insights_ativo.append(("🛡️ ESCUDO DEFENSIVO", "Ativo apresenta correlação positiva com o VIX. Funciona como proteção (hedge) natural em momentos de pânico nos mercados."))

            # INSIGHT 3: Earnings Surprise vs Precificação
            try:
                eh = tk.earnings_history
                if eh is not None and not eh.empty and 'Surprise(%)' in eh.columns:
                    surpresa_media = eh['Surprise(%)'].mean() * 100
                    if surpresa_media > 10 and rsi < 50:
                        insights_ativo.append(("🎁 ASSIMETRIA DE BALANÇO", f"Empresa bateu as estimativas em média {surpresa_media:.1f}% nos últimos balanços, mas o preço atual ainda não reflete esse otimismo (RSI neutro/baixo)."))
            except:
                pass

            # INSIGHT 4: Divergência Saúde vs Técnica
            if h_score > 70 and rsi > 70:
                insights_ativo.append(("⚠️ AGUARDAR PULLBACK", "Fundamentos excelentes (Score > 70), mas tecnicamente muito esticado (RSI > 70). Considere aguardar um recuo para aportar."))
            elif h_score < 40 and rsi < 35:
                insights_ativo.append(("🚨 CONVERGÊNCIA BAIXISTA", "Fundamentos em deterioração rápida (Score < 40) E gráfico em colapso. Revisar tese com urgência!"))
            elif h_score > 70 and rsi < 35:
                insights_ativo.append(("🎯 SETUP IDEAL", "Empresa muito saudável (Score > 70) sendo negociada em desconto técnico irracional (RSI < 35). Ponto ideal de entrada."))

            # ==========================================
            # RENDERIZAÇÃO DO CARD DO ATIVO (Sem Indentação Markdown)
            # ==========================================
            if insights_ativo:
                cor_score = "#00FF00" if h_score >= 65 else ("#FF9900" if h_score >= 40 else "#FF0000")
                
                with cols[col_idx % 3]:
                    # Usamos concatenação segura sem espaços no início para evitar o bloco de código
                    html_card = (
                        f"<div style='background-color:#111; padding:15px; border-radius:6px; border-top:2px solid {cor_score}; margin-bottom:15px; min-height: 250px;'>"
                        f"<div style='display:flex; justify-content:space-between; border-bottom:1px solid #333; padding-bottom:10px; margin-bottom:10px;'>"
                        f"<span style='font-weight:bold; color:#FFF; font-size:1.1rem; font-family:Courier New;'>{t}</span>"
                        f"<span style='background:{cor_score}33; color:{cor_score}; padding:2px 8px; border-radius:4px; font-size:0.8rem; font-family:Courier New;'>SCORE: {h_score:.0f}</span>"
                        f"</div>"
                    )
                    
                    texto_para_ia = f"Ativo: {t} | Peso na Carteira: {peso_ativo}%\n"
                    
                    for titulo, desc in insights_ativo:
                        html_card += (
                            f"<div style='margin-bottom:10px;'>"
                            f"<div style='font-size:0.8rem; font-weight:bold; color:#FF9900;'>{titulo}</div>"
                            f"<div style='font-size:0.85rem; color:#AAA;'>{desc}</div>"
                            f"</div>"
                        )
                        texto_para_ia += f"- {titulo}: {desc}\n"
                        
                    html_card += "</div>"
                    st.markdown(html_card, unsafe_allow_html=True)
                    
                    insights_compilados.append(texto_para_ia)
                    
                col_idx += 1

        except Exception as e:
            continue

if not insights_compilados:
    st.info("O sistema não detetou nenhuma divergência ou assimetria crítica na sua Watchlist neste momento.")
    st.stop()

# ==========================================
# 3. SÍNTESE IA HOLÍSTICA DA CARTEIRA
# ==========================================
st.markdown("---")
st.markdown("#### 🧠 VISÃO HOLÍSTICA DO GESTOR DE IA")

if st.button("GERAR SÍNTESE ESTRATÉGICA DO PORTFÓLIO", type="primary"):
    
    chave_cache = f"insights_{len(insights_compilados)}_{datetime.date.today()}"
    cache_insights = get_cache_ia('PORTFOLIO', chave_cache, max_horas=12)
    
    if cache_insights:
        st.success("⚡ Relatório recuperado do Cache (Gerado hoje).")
        st.markdown(cache_insights)
    else:
        with st.spinner("A analisar a totalidade das intersecções do seu portfólio..."):
            try:
                texto_insights_prompt = "\n\n".join(insights_compilados)
                
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                prompt = f"""
                Você é o Gestor Principal de um Hedge Fund Macro-Fundamentalista com visão sistêmica.
                Abaixo estão os insights cruzados automáticos gerados pelo nosso terminal para os ativos monitorados na carteira do cliente.
                
                {texto_insights_prompt}
                
                Escreva um relatório executivo em português (PT-BR ou PT-PT), formatação markdown elegante e direta:
                
                ## 🌡️ Saúde Geral da Carteira
                Atribua uma nota de 0 a 10 para o posicionamento global da carteira face aos dados e justifique em 2 frases diretas.
                
                ## 🌪️ Maior Risco Sistêmico
                Identifique o risco que afeta MÚLTIPLOS ativos simultaneamente (ex: muita correlação com Selic, excesso de ativos no quadrante de Duplo Risco).
                
                ## 💎 Maior Oportunidade Não Explorada
                Com base exclusivamente nestes insights, qual posição (ou tipo de posição) merece um aporte imediato ou atenção especial e porquê?
                
                ## ⚖️ Sugestão de Rebalanceamento
                Faça 2 a 3 sugestões concretas e pragmáticas (ex: "reduzir ativo X porque está com duplo risco", "aumentar Y porque apresenta divergência ideal"). Baseie-se ESTRITAMENTE nos dados fornecidos.
                """
                
                resposta = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                
                salvar_cache_ia('PORTFOLIO', chave_cache, resposta.text)
                st.markdown(resposta.text)
                
            except Exception as e:
                st.error(f"Erro na comunicação com o motor de IA: {e}")