import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from google import genai

# Importa o Design System, Banco de Dados e Catálogo de Tickers
from utils.style import aplicar_tema
from database.db import get_cache_ia, salvar_cache_ia
from utils.tickers import get_opcoes_selectbox, ticker_from_label

# --- Configuração da Página ---
st.set_page_config(page_title="Análise Técnica", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 📈 ESTÚDIO DE ANÁLISE TÉCNICA")
st.write("Gráficos interativos com indicadores de momentum, volatilidade e rastreamento de tendência.")

# ==========================================
# PAINEL DE CONTROLE (UI) E BUSCA CENTRALIZADA
# ==========================================
st.markdown("---")

col_busca, col_periodo = st.columns([6, 2])
with col_busca:
    col_sel, col_manual = st.columns([5, 3])
    with col_sel:
        opcoes = get_opcoes_selectbox()
        selecao = st.selectbox("ATIVO (selecione ou use o campo ao lado):", opcoes)
    with col_manual:
        ticker_manual = st.text_input(
            "Ou digite o ticker diretamente:", ""
        ).strip().upper()

    # Prioriza o campo manual se preenchido
    if ticker_manual:
        ticker_input = ticker_manual
    else:
        ticker_input = ticker_from_label(selecao) or "PETR4.SA"

with col_periodo:
    st.markdown("<br>", unsafe_allow_html=True) # Alinhamento visual
    periodo_sel = st.selectbox("PERÍODO DE ANÁLISE:", ["3mo", "6mo", "1y", "2y", "5y"], index=2)

st.markdown("#### ⚙️ INDICADORES TÉCNICOS")
c1, c2, c3 = st.columns(3)
with c1:
    show_sma50 = st.checkbox("Mostrar Média Móvel Simples (50 períodos)", value=True)
with c2:
    show_sma200 = st.checkbox("Mostrar Média Móvel Simples (200 períodos)", value=True)
with c3:
    show_bb = st.checkbox("Mostrar Bandas de Bollinger (20, 2σ)", value=True)

st.markdown("<br>", unsafe_allow_html=True)
btn_gerar = st.button("GERAR GRÁFICO TÉCNICO", type="primary", use_container_width=True)

# ==========================================
# MOTOR DA ANÁLISE TÉCNICA
# ==========================================
if btn_gerar or ticker_input:
    if not ticker_input or ticker_input.startswith("─"):
        st.warning("Por favor, selecione um ativo válido na lista ou digite um ticker.")
        st.stop()
        
    with st.spinner("Puxando histórico de preços e calculando indicadores matemáticos..."):
        try:
            # Puxa o histórico
            df = yf.Ticker(ticker_input).history(period=periodo_sel)
            
            if df.empty:
                st.error("Não foram encontrados dados para este ticker no período selecionado.")
                st.stop()
                
            # Remove o timezone para evitar conflitos no Plotly
            if hasattr(df.index, 'tz') and df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            # ------------------------------------------
            # 1. CÁLCULO DOS INDICADORES MATEMÁTICOS
            # ------------------------------------------
            
            # Médias Móveis
            df['SMA50'] = df['Close'].rolling(window=50).mean()
            df['SMA200'] = df['Close'].rolling(window=200).mean()
            
            # RSI (14 Períodos) - Cálculo manual
            delta = df['Close'].diff()
            ganho = delta.clip(lower=0).rolling(14).mean()
            perda = (-delta.clip(upper=0)).rolling(14).mean()
            rs = ganho / perda
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # Bandas de Bollinger (20 Períodos, 2 Desvios Padrão)
            df['BB_mid'] = df['Close'].rolling(20).mean()
            df['BB_std'] = df['Close'].rolling(20).std()
            df['BB_upper'] = df['BB_mid'] + 2 * df['BB_std']
            df['BB_lower'] = df['BB_mid'] - 2 * df['BB_std']

            # ------------------------------------------
            # 2. CONSTRUÇÃO DO GRÁFICO (SUBPLOTS)
            # ------------------------------------------
            fig = make_subplots(
                rows=3, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.04,
                row_heights=[0.6, 0.2, 0.2],
                specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": False}]]
            )

            # --- PAINEL 1: Candlestick e Indicadores no Preço ---
            fig.add_trace(
                go.Candlestick(
                    x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                    name='Preço'
                ), row=1, col=1
            )

            if show_sma50:
                fig.add_trace(go.Scatter(x=df.index, y=df['SMA50'], line=dict(color='#00FFFF', width=1.5), name='SMA 50'), row=1, col=1)
            
            if show_sma200:
                fig.add_trace(go.Scatter(x=df.index, y=df['SMA200'], line=dict(color='#FF00FF', width=1.5), name='SMA 200'), row=1, col=1)

            if show_bb:
                # Linha Superior
                fig.add_trace(go.Scatter(x=df.index, y=df['BB_upper'], line=dict(color='#FF9900', width=1, dash='dot'), name='BB Superior'), row=1, col=1)
                # Linha Inferior com preenchimento (fill='tonexty')
                fig.add_trace(go.Scatter(x=df.index, y=df['BB_lower'], line=dict(color='#FF9900', width=1, dash='dot'), name='BB Inferior', fill='tonexty', fillcolor='rgba(255, 153, 0, 0.05)'), row=1, col=1)

            # --- PAINEL 2: Volume de Negociação ---
            cores_volume = ['#00FF00' if c >= o else '#FF0000' for c, o in zip(df['Close'], df['Open'])]
            fig.add_trace(
                go.Bar(x=df.index, y=df['Volume'], marker_color=cores_volume, name='Volume'),
                row=2, col=1
            )

            # --- PAINEL 3: RSI (Índice de Força Relativa) ---
            fig.add_trace(
                go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#FFFFFF', width=1.5), name='RSI (14)'),
                row=3, col=1
            )
            # Linhas de sinal (Sobrecomprado/Sobrevendido)
            fig.add_hline(y=70, line_dash="dash", line_color="#FF0000", line_width=1, row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#00FF00", line_width=1, row=3, col=1)

            # --- Layout e Estilização Geral ---
            fig.update_layout(
                paper_bgcolor="#010101", 
                plot_bgcolor="#010101",
                font=dict(family="Courier New", color="#E0E0E0"),
                height=800,
                margin=dict(l=0, r=0, t=30, b=0),
                hovermode="x unified",
                xaxis_rangeslider_visible=False,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#222222', row=1, col=1)
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#222222', title="Volume", row=2, col=1)
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#222222', title="RSI", range=[0, 100], tickvals=[30, 50, 70], row=3, col=1)
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#222222')

            st.plotly_chart(fig, use_container_width=True)

            # ------------------------------------------
            # 3. INTERPRETAÇÃO DE SINAIS AUTOMÁTICOS
            # ------------------------------------------
            st.markdown("#### 🤖 DIAGNÓSTICO DO SETUP TÉCNICO (ÚLTIMO PREGÃO)")
            
            last_close = df['Close'].iloc[-1]
            last_sma50 = df['SMA50'].iloc[-1] if not pd.isna(df['SMA50'].iloc[-1]) else None
            last_sma200 = df['SMA200'].iloc[-1] if not pd.isna(df['SMA200'].iloc[-1]) else None
            last_rsi = df['RSI'].iloc[-1] if not pd.isna(df['RSI'].iloc[-1]) else None
            last_bb_upper = df['BB_upper'].iloc[-1] if not pd.isna(df['BB_upper'].iloc[-1]) else None
            last_bb_lower = df['BB_lower'].iloc[-1] if not pd.isna(df['BB_lower'].iloc[-1]) else None

            # Diagnóstico Média Móvel
            if last_sma50 is not None and last_sma200 is not None:
                tendencia = "ALTISTA 🟢" if last_sma50 > last_sma200 else "BAIXISTA 🔴"
                txt_tendencia = f"- **Rastreamento de Tendência:** A SMA50 (R$ {last_sma50:.2f}) está {'acima' if last_sma50 > last_sma200 else 'abaixo'} da SMA200 (R$ {last_sma200:.2f}) → Tendência Estrutural **{tendencia}**."
            else:
                txt_tendencia = "- **Rastreamento de Tendência:** *Dados insuficientes no período para calcular o cruzamento da SMA200.*"

            # Diagnóstico RSI
            if last_rsi is not None:
                if last_rsi >= 70: 
                    rsi_status = "SOBRECOMPRADO 🔴 (Possível Risco de Correção/Exaustão)"
                elif last_rsi <= 30: 
                    rsi_status = "SOBREVENDIDO 🟢 (Possível Repique/Desconto)"
                else: 
                    rsi_status = "NEUTRO ⚪ (Sem extremos direcionais)"
                txt_rsi = f"- **Momento (RSI):** O RSI atual marca **{last_rsi:.1f}** — [{rsi_status}]."
            else:
                txt_rsi = "- **Momento (RSI):** *Dados insuficientes para cálculo.*"

            # Diagnóstico Bollinger
            if last_bb_upper is not None and last_bb_lower is not None:
                dist_upper = abs(last_close - last_bb_upper) / last_bb_upper
                dist_lower = abs(last_close - last_bb_lower) / last_bb_lower
                
                if dist_upper <= 0.02:
                    bb_status = f"próximo (+/- 2%) da Banda SUPERIOR 🔴 (Esticado em R$ {last_bb_upper:.2f})."
                elif dist_lower <= 0.02:
                    bb_status = f"próximo (+/- 2%) da Banda INFERIOR 🟢 (Sobre-desconto em R$ {last_bb_lower:.2f})."
                else:
                    bb_status = "navegando dentro do canal normal de volatilidade (sem encostar nos extremos)."
                txt_bb = f"- **Volatilidade (Bollinger):** O preço de fechamento (R$ {last_close:.2f}) está {bb_status}"
            else:
                txt_bb = "- **Volatilidade (Bollinger):** *Dados insuficientes para cálculo.*"

            st.markdown(f"""
            <div style="background-color: #111111; padding: 20px; border-radius: 8px; border-left: 5px solid #FF9900;">
                {txt_tendencia}<br><br>
                {txt_rsi}<br><br>
                {txt_bb}
            </div>
            """, unsafe_allow_html=True)
            
        except Exception as e:
            st.error(f"Erro ao processar dados técnicos: {str(e)}")

# ==========================================
# 4. SÍNTESE TÉCNICA VIA INTELIGÊNCIA ARTIFICIAL
# ==========================================
st.markdown("---")
st.markdown("#### 🧠 LEITURA DE CHARTISMO POR I.A.")

if btn_gerar or ticker_input:
    if 'last_close' in locals():
        if st.button("ANALISAR SINAIS GRÁFICOS COM IA", type="primary"):
            
            chave_cache = f"tecnica_{ticker_input}_{periodo_sel}"
            cache_tecnica = get_cache_ia('TECNICA', chave_cache, max_horas=6)
            
            if cache_tecnica:
                st.success("⚡ Recuperado do Cache (Gerado nas últimas 6h).")
                st.markdown(cache_tecnica)
            else:
                with st.spinner("Enviando vetores de momentum e osciladores para o Gemini..."):
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        
                        prompt = f"""
                        Aja como um analista técnico (chartista) experiente de uma mesa de operações.
                        Faça uma leitura tática objetiva do ativo {ticker_input} baseando-se estritamente nestes dados de fechamento do último pregão:
                        
                        - Preço Atual: R$ {last_close:.2f}
                        - SMA 50: R$ {last_sma50:.2f} (Tendência de curto/médio prazo)
                        - SMA 200: R$ {last_sma200:.2f} (Tendência estrutural)
                        - RSI (14): {last_rsi:.1f}
                        - Banda de Bollinger Superior: R$ {last_bb_upper:.2f}
                        - Banda de Bollinger Inferior: R$ {last_bb_lower:.2f}
                        
                        Escreva um breve relatório de 3 tópicos curtos (em português europeu/brasileiro):
                        1. **Rastreamento de Tendência**: O que o cruzamento das médias e a posição do preço indicam?
                        2. **Exaustão ou Momentum**: Avalie o RSI e o espaço até as Bandas de Bollinger. O ativo está esticado?
                        3. **Conclusão Tática**: Um resumo indicando se o cenário atual é de risco, oportunidade de pullback ou rompimento.
                        
                        Seja direto, profissional e evite jargões excessivamente complexos.
                        """
                        
                        resposta = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        
                        salvar_cache_ia('TECNICA', chave_cache, resposta.text)
                        st.success("✅ Leitura Técnica gerada pelo Gemini e armazenada em cache.")
                        st.markdown(resposta.text)
                        
                    except Exception as e:
                        st.error(f"Erro na comunicação com a IA: {e}")