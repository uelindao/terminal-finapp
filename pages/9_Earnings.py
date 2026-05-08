import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from google import genai

from utils.auth import check_password

if not check_password():
    st.stop()

# Importa as dependências do projeto e o novo catálogo de tickers
from utils.style import aplicar_tema
from database.db import listar_watchlist, get_cache_ia, salvar_cache_ia
from utils.tickers import get_opcoes_selectbox, ticker_from_label

# --- Configuração da Página ---
st.set_page_config(page_title="Earnings Dashboard", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

# ==========================================
# FUNÇÃO AUXILIAR DE EXTRAÇÃO (BLINDADA)
# ==========================================
def extrair_data_earnings(calendar):
    """Extrai data de earnings de forma blindada para múltiplas versões do yfinance."""
    try:
        if calendar is None:
            return None
        if isinstance(calendar, pd.DataFrame):
            if 'Earnings Date' in calendar.index:
                val = calendar.loc['Earnings Date'].iloc[0]
                if not pd.isna(val): return pd.Timestamp(val)
            col = next((c for c in calendar.columns if 'Earnings' in str(c) or 'Date' in str(c)), None)
            if col:
                val = calendar[col].iloc[0] if not calendar[col].empty else None
                return pd.Timestamp(val) if val is not None and not pd.isna(val) else None
        if isinstance(calendar, dict):
            dates = calendar.get('Earnings Date', calendar.get('earningsDate', []))
            if dates and len(dates) > 0:
                return pd.Timestamp(dates[0])
    except:
        pass
    return None

st.markdown("### 📋 EARNINGS DASHBOARD — RESULTADOS TRIMESTRAIS")

tab1, tab2 = st.tabs(["🔍 Análise Individual", "📅 Calendário da Watchlist"])

# ==========================================
# ABA 1: ANÁLISE INDIVIDUAL
# ==========================================
with tab1:
    c1, c2 = st.columns([3, 1])
    with c1:
        opcoes = get_opcoes_selectbox()
        selecao = st.selectbox(
            "SELECIONE O ATIVO (pesquise pelo nome ou ticker):",
            opcoes
        )
        
        ticker_manual = ""
        if "digitar" in selecao.lower():
            ticker_manual = st.text_input(
                "Digite o ticker (Ex: KLBN11.SA, COIN):", ""
            ).strip().upper()
        
        ticker_input = ticker_manual if ticker_manual else (ticker_from_label(selecao) or "")
            
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_analisar = st.button("ANALISAR EARNINGS", type="primary", use_container_width=True)

    if btn_analisar or ticker_input:
        if not ticker_input or ticker_input.startswith("─"):
            st.info("Selecione um ativo na lista ou digite o ticker manualmente.")
            st.stop()
            
        acao = yf.Ticker(ticker_input)
        
        # --- SEÇÃO A: PRÓXIMO EARNINGS ---
        st.markdown("#### ⏳ PRÓXIMO RESULTADO ESTIMADO")
        try:
            cal = acao.calendar
            data_e = extrair_data_earnings(cal)
            
            if data_e:
                hoje = pd.Timestamp.now().normalize()
                data_e_ts = pd.Timestamp(data_e).normalize()
                dias_restantes = (data_e_ts - hoje).days
                
                eps_est = np.nan
                if isinstance(cal, pd.DataFrame) and 'EPS Estimate' in cal.index:
                    eps_est = cal.loc['EPS Estimate'].iloc[0]
                
                m1, m2, m3 = st.columns(3)
                m1.metric("DATA PREVISTA", data_e_ts.strftime('%d/%m/%Y'))
                m2.metric("CONTAGEM REGRESSIVA", f"{dias_restantes} dias")
                m3.metric("EPS ESTIMADO", f"{eps_est:.2f}" if not pd.isna(eps_est) else "N/D")
            else:
                st.info("💡 O provedor de dados (Yahoo Finance) não disponibilizou o calendário futuro para este ativo.")
        except:
            st.info("💡 Não foi possível extrair o calendário de eventos futuros deste ativo.")

        # --- SEÇÃO B & C: HISTÓRICO DE SURPRESAS ---
        st.markdown("---")
        st.markdown("#### 📈 HISTÓRICO DE SURPRESAS (EPS)")
        
        try:
            hist_surpresa = acao.earnings_history
            
            if hist_surpresa is not None and not hist_surpresa.empty:
                df_s = hist_surpresa.head(8).copy()
                if 'Reported EPS' in df_s.columns and 'EPS Estimate' in df_s.columns:
                    df_s['Surpresa %'] = ((df_s['Reported EPS'] - df_s['EPS Estimate']) / df_s['EPS Estimate'].abs()) * 100
                    
                    c_tab, c_chart = st.columns([1, 1])
                    
                    with c_tab:
                        def color_surpresa(val):
                            if pd.isna(val): return ''
                            color = '#00FF00' if val > 0 else '#FF0000'
                            return f'color: {color}'
                        
                        st.dataframe(
                            df_s[['EPS Estimate', 'Reported EPS', 'Surpresa %']].style.format("{:.2f}", na_rep="N/D").applymap(color_surpresa, subset=['Surpresa %']),
                            use_container_width=True
                        )
                    
                    with c_chart:
                        fig_s = go.Figure()
                        cores = ['#00FF00' if x > 0 else '#FF0000' for x in df_s['Surpresa %']]
                        fig_s.add_trace(go.Bar(
                            x=df_s.index.astype(str), y=df_s['Surpresa %'],
                            marker_color=cores, name="Surpresa %"
                        ))
                        fig_s.add_hline(y=0, line_color="white", opacity=0.5)
                        fig_s.update_layout(
                            height=300, paper_bgcolor="#010101", plot_bgcolor="#010101",
                            margin=dict(l=0, r=0, t=20, b=0), font=dict(color="#888888")
                        )
                        st.plotly_chart(fig_s, use_container_width=True)
                else:
                    st.info("💡 O histórico de surpresas EPS não possui dados completos para este ticker.")
            else:
                st.info("💡 Histórico de estimativas vs resultados não fornecido pelo Yahoo Finance para este ativo.")
        except Exception:
            st.info("💡 Não há dados históricos estruturados de surpresas de lucros para este ativo.")

        # --- SEÇÃO D & E: EVOLUÇÃO FINANCEIRA E MARGENS ---
        st.markdown("---")
        st.markdown("#### 📊 EVOLUÇÃO TRIMESTRAL E MARGENS")
        
        rev = pd.Series(dtype=float)
        m_liq = pd.Series(dtype=float)
        
        try:
            q_fin = acao.quarterly_financials.T
            if not q_fin.empty and 'Total Revenue' in q_fin.columns and 'Net Income' in q_fin.columns:
                q_fin = q_fin.sort_index()
                rev = q_fin['Total Revenue'].dropna()
                net_inc = q_fin['Net Income'].dropna()
                
                m_bruta = (q_fin['Gross Profit'] / rev) * 100 if 'Gross Profit' in q_fin.columns else None
                m_oper = (q_fin['Operating Income'] / rev) * 100 if 'Operating Income' in q_fin.columns else None
                m_liq = (net_inc / rev) * 100
                
                fig_fin = make_subplots(specs=[[{"secondary_y": True}]])
                fig_fin.add_trace(go.Bar(x=rev.index.astype(str), y=rev, name="Receita Total", marker_color="#FF9900"), secondary_y=False)
                fig_fin.add_trace(go.Scatter(x=net_inc.index.astype(str), y=net_inc, name="Lucro Líquido", line=dict(color="#00FFFF", width=3)), secondary_y=True)
                
                fig_fin.update_layout(height=400, paper_bgcolor="#010101", plot_bgcolor="#010101", font=dict(color="#888888"), margin=dict(t=30))
                st.plotly_chart(fig_fin, use_container_width=True)
                
                st.markdown("##### Dinâmica de Margens (%)")
                fig_margens = go.Figure()
                if m_bruta is not None: fig_margens.add_trace(go.Scatter(x=m_bruta.index.astype(str), y=m_bruta, name="M. Bruta", line=dict(color="#FF9900")))
                if m_oper is not None: fig_margens.add_trace(go.Scatter(x=m_oper.index.astype(str), y=m_oper, name="M. Operacional", line=dict(color="#00FFFF")))
                fig_margens.add_trace(go.Scatter(x=m_liq.index.astype(str), y=m_liq, name="M. Líquida", line=dict(color="#00FF00")))
                
                fig_margens.update_layout(height=350, paper_bgcolor="#010101", plot_bgcolor="#010101", font=dict(color="#888888"))
                st.plotly_chart(fig_margens, use_container_width=True)
            else:
                st.warning("⚠️ Os demonstrativos financeiros trimestrais deste ativo estão incompletos no provedor de dados.")
        except Exception as e:
            st.warning("⚠️ Falha ao processar balanços trimestrais.")

        # --- SEÇÃO F: ANÁLISE IA ---
        st.markdown("---")
        st.markdown("#### 🧠 SÍNTESE DO ÚLTIMO RESULTADO (VIA IA)")
        
        if st.button("🤖 GERAR COMMENTARY DO ÚLTIMO TRIMESTRE", type="primary"):
            cache_e = get_cache_ia(ticker_input, 'earnings', max_horas=48)
            if cache_e:
                st.success("⚡ Comentário recuperado do cache (48h).")
                st.markdown(cache_e)
            else:
                with st.spinner("Acionando a IA para leitura dos balanços..."):
                    try:
                        try:
                            ult_rev = f"R$ {rev.iloc[-1]:,.2f}" if not rev.empty else "N/D"
                            ult_liq = f"{m_liq.iloc[-1]:.2f}%" if not m_liq.empty else "N/D"
                        except:
                            ult_rev, ult_liq = "N/D", "N/D"
                            
                        info = acao.info
                        if ult_rev == "N/D" and info.get('totalRevenue'):
                            ult_rev = f"R$ {info.get('totalRevenue'):,.2f} (Anual/TTM)"
                        if ult_liq == "N/D" and info.get('profitMargins'):
                            ult_liq = f"{info.get('profitMargins')*100:.2f}% (Anual/TTM)"
                            
                        cresc = info.get('earningsQuarterlyGrowth', 'N/D')
                        if cresc != 'N/D': cresc = f"{cresc*100:.2f}%"

                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        prompt = f"""
                        Você é um analista fundamentalista sênior. 
                        Faça uma leitura rápida do momento financeiro de {ticker_input} usando as métricas abaixo como base:
                        
                        - Receita Referência: {ult_rev}
                        - Margem Líquida Referência: {ult_liq}
                        - Crescimento Trimestral Lucro (YoY): {cresc}
                        
                        Se algum dado constar como "N/D", utilize seu vasto conhecimento de mercado para dissertar qualitativamente sobre a empresa.
                        
                        Escreva em português (formato markdown):
                        1. **Headline (1 linha)**: Diagnóstico resumido.
                        2. **Pontos Positivos**: (max 3 bullets)
                        3. **Pontos de Atenção/Riscos**: (max 3 bullets)
                        
                        Seja objetivo, profissional e sem recomendação de compra/venda.
                        """
                        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        salvar_cache_ia(ticker_input, 'earnings', res.text)
                        st.markdown(res.text)
                    except Exception as e:
                        st.error(f"Erro na comunicação com a IA: {e}")

# ==========================================
# ABA 2: CALENDÁRIO DA WATCHLIST
# ==========================================
with tab2:
    watchlist = listar_watchlist()
    
    if not watchlist:
        st.info("Sua Watchlist está vazia. Adicione ativos para monitorar o calendário.")
    else:
        proximos_events = []
        
        with st.spinner("Varrendo calendário de earnings da sua Watchlist... (Leva alguns segundos)"):
            for item in watchlist:
                t = item['ticker']
                try:
                    tk = yf.Ticker(t)
                    data_e = extrair_data_earnings(tk.calendar)
                    
                    if data_e:
                        hoje = pd.Timestamp.now().normalize()
                        ts_e = pd.Timestamp(data_e).tz_localize(None).normalize()
                        dias = (ts_e - hoje).days
                        
                        if 0 <= dias <= 60:
                            proximos_events.append({
                                'Ticker': t,
                                'Nome': item['nome'],
                                'Data': ts_e.strftime('%d/%m/%Y'),
                                'Em (dias)': dias,
                                'ts': ts_e
                            })
                except:
                    continue
        
        if not proximos_events:
            st.info("💡 Nenhum evento de Earnings encontrado nos próximos 60 dias para os ativos da sua Watchlist.")
        else:
            df_cal = pd.DataFrame(proximos_events).sort_values('ts')
            
            st.markdown(f"**{len(df_cal)} eventos detectados no horizonte de 60 dias.**")
            
            def color_urgencia(val):
                if val <= 7: return 'background-color: #330000; color: #FF0000'
                if val <= 30: return 'background-color: #221100; color: #FF9900'
                return 'color: #888888'

            st.dataframe(
                df_cal.drop(columns=['ts']).style.applymap(color_urgencia, subset=['Em (dias)']),
                use_container_width=True, hide_index=True
            )
            
            st.markdown("#### TIMELINE DE EARNINGS")
            fig_time = go.Figure()
            
            cores_g = []
            for d in df_cal['Em (dias)']:
                if d <= 7: cores_g.append('#FF0000')
                elif d <= 30: cores_g.append('#FF9900')
                else: cores_g.append('#888888')
            
            fig_time.add_trace(go.Scatter(
                x=df_cal['ts'], y=df_cal['Ticker'],
                mode='markers+text',
                text=df_cal['Ticker'],
                textposition="top center",
                marker=dict(size=12, color=cores_g, symbol='diamond'),
                name="Data de Resultado"
            ))
            
            # --- CORREÇÃO DO BUG DO PLOTLY COM DATAS ---
            data_hoje = datetime.datetime.now()
            
            fig_time.add_shape(
                type="line",
                x0=data_hoje, y0=0, x1=data_hoje, y1=1,
                xref="x", yref="paper",
                line=dict(color="white", dash="dash", width=1),
                opacity=0.5
            )
            
            fig_time.add_annotation(
                x=data_hoje, y=1.05,
                xref="x", yref="paper",
                text="HOJE", showarrow=False,
                font=dict(color="white", size=10)
            )
            # -------------------------------------------
            
            fig_time.update_layout(
                height=400, paper_bgcolor="#010101", plot_bgcolor="#010101",
                font=dict(color="#888888", family="Courier New"),
                yaxis=dict(showgrid=False), margin=dict(t=40)
            )
            st.plotly_chart(fig_time, use_container_width=True)