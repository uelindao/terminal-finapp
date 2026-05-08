import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import plotly.graph_objects as go
from google import genai

from utils.style import aplicar_tema
from database.db import get_cache_ia, salvar_cache_ia, get_historico_multiplos
from utils.tickers import get_opcoes_selectbox, ticker_from_label

# --- Configuração da Página ---
st.set_page_config(page_title="Análise Fundamentalista", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 📊 RAIO-X FUNDAMENTALISTA")

# --- Barra de Busca Amigável ---
col_busca, col_vazia = st.columns([4, 6])
with col_busca:
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

if not ticker_input or ticker_input.startswith("─"):
    st.info("Selecione um ativo na lista ou digite o ticker manualmente.")
    st.stop()

# --- Coleta de Dados Base ---
with st.spinner(f"Coletando balanços e múltiplos de {ticker_input}..."):
    try:
        acao = yf.Ticker(ticker_input)
        info = acao.info
        
        preco_atual = info.get('currentPrice', info.get('regularMarketPrice', 0))
        pl = info.get('trailingPE', info.get('forwardPE', np.nan))
        pvp = info.get('priceToBook', np.nan)
        
        roe_raw = info.get('returnOnEquity', None)
        roe = roe_raw * 100 if roe_raw is not None else np.nan
        
        dy = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
        setor = info.get('sector', 'Desconhecido')
        nome_empresa = info.get('shortName', ticker_input)
        
    except Exception as e:
        st.error(f"Falha ao buscar dados para {ticker_input}. Verifique o código.")
        st.stop()

st.markdown(f"**Empresa:** {nome_empresa} | **Setor:** {setor} | **Preço:** R$ {preco_atual:.2f}")

# --- KEY METRICS ---
st.markdown("---")
st.markdown("#### KEY METRICS")
c1, c2, c3, c4 = st.columns(4)
c1.metric("P/L (Preço / Lucro)", f"{pl:.2f}" if not np.isnan(pl) else "N/D")
c2.metric("P/VP (Preço / VPA)", f"{pvp:.2f}" if not np.isnan(pvp) else "N/D")
c3.metric("ROE (Retorno s/ PL)", f"{roe:.2f}%" if not np.isnan(roe) else "N/D")
c4.metric("DIVIDEND YIELD", f"{dy:.2f}%")

# ==========================================
# SECTOR BENCHMARK
# ==========================================
st.markdown("---")
st.markdown("#### SECTOR BENCHMARK (Comparativo de Pares)")

# Dicionário Expandido de Pares Setoriais
peers_por_setor = {
    "Energy": ["PETR4.SA", "PRIO3.SA", "CSAN3.SA", "XOM", "CVX"],
    "Financial Services": ["ITUB4.SA", "BBAS3.SA", "BBDC4.SA", "JPM", "BAC"],
    "Basic Materials": ["VALE3.SA", "GGBR4.SA", "RIO", "BHP"],
    "Technology": ["AAPL", "MSFT", "NVDA", "GOOGL"],
    "Consumer Defensive": ["ABEV3.SA", "KO", "PEP", "WMT", "PG"],
    "Industrials": ["WEGE3.SA", "RENT3.SA", "GE", "MMM", "HON"],
    "Consumer Cyclical": ["AMZN", "TSLA", "LREN3.SA", "MGLU3.SA", "HD"],
    "Healthcare": ["JNJ", "UNH", "LLY", "RADL3.SA", "HAPV3.SA"],
    "Utilities": ["EGIE3.SA", "EQTL3.SA", "TAEE11.SA", "SBSP3.SA"],
    "Communication Services": ["META", "NFLX", "VIVT3.SA", "CMCSA"],
    "Real Estate": ["AMT", "PLD", "SPG", "MULT3.SA", "IGTI11.SA"]
}

if setor in peers_por_setor:
    with st.spinner(f"Mapeando o setor de {setor}..."):
        peers = peers_por_setor[setor]
        
        if ticker_input not in peers:
            peers.append(ticker_input)
            
        dados_setor = []
        for p in peers:
            try:
                p_info = yf.Ticker(p).info
                p_pl = p_info.get('trailingPE', p_info.get('forwardPE', np.nan))
                
                p_roe_raw = p_info.get('returnOnEquity', None)
                p_roe = p_roe_raw * 100 if p_roe_raw is not None else np.nan
                
                p_dy = p_info.get('dividendYield', 0) * 100 if p_info.get('dividendYield') else 0
                dados_setor.append({'Ticker': p, 'P/L': p_pl, 'ROE': p_roe, 'DY': p_dy})
            except:
                pass
                
        df_setor = pd.DataFrame(dados_setor)
        
        media_pl = df_setor['P/L'].mean()
        mediana_pl = df_setor['P/L'].median()
        media_roe = df_setor['ROE'].mean()
        mediana_roe = df_setor['ROE'].median()
        media_dy = df_setor['DY'].mean()
        mediana_dy = df_setor['DY'].median()

        cor_pl = "#00FF00" if pl < mediana_pl else "#FF0000"
        cor_roe = "#00FF00" if roe > mediana_roe else "#FF0000"
        cor_dy = "#00FF00" if dy > mediana_dy else "#FF0000"

        html_tabela = f"""
        <table style="width:100%; text-align:left; border-collapse: collapse; font-family: 'Courier New', monospace; font-size: 0.9rem;">
            <tr style="border-bottom: 1px solid #333; color: #888;">
                <th style="padding: 8px;">MÚLTIPLO</th>
                <th style="padding: 8px;">{ticker_input} (ATIVO)</th>
                <th style="padding: 8px;">MÉDIA DO SETOR</th>
                <th style="padding: 8px;">MEDIANA DO SETOR</th>
                <th style="padding: 8px;">DIAGNÓSTICO vs MEDIANA</th>
            </tr>
            <tr style="border-bottom: 1px solid #222;">
                <td style="padding: 8px; font-weight:bold;">P/L (Preço/Lucro)</td>
                <td style="padding: 8px; color: {cor_pl};">{pl:.2f}</td>
                <td style="padding: 8px;">{media_pl:.2f}</td>
                <td style="padding: 8px;">{mediana_pl:.2f}</td>
                <td style="padding: 8px; color: {cor_pl};">{'MELHOR (Mais Barato)' if pl < mediana_pl else 'PIOR (Mais Caro)'}</td>
            </tr>
            <tr style="border-bottom: 1px solid #222;">
                <td style="padding: 8px; font-weight:bold;">ROE (Retorno)</td>
                <td style="padding: 8px; color: {cor_roe};">{roe:.2f}%</td>
                <td style="padding: 8px;">{media_roe:.2f}%</td>
                <td style="padding: 8px;">{mediana_roe:.2f}%</td>
                <td style="padding: 8px; color: {cor_roe};">{'MELHOR (Mais Rentável)' if roe > mediana_roe else 'PIOR (Menos Rentável)'}</td>
            </tr>
            <tr>
                <td style="padding: 8px; font-weight:bold;">Dividend Yield</td>
                <td style="padding: 8px; color: {cor_dy};">{dy:.2f}%</td>
                <td style="padding: 8px;">{media_dy:.2f}%</td>
                <td style="padding: 8px;">{mediana_dy:.2f}%</td>
                <td style="padding: 8px; color: {cor_dy};">{'MELHOR (Paga Mais)' if dy > mediana_dy else 'PIOR (Paga Menos)'}</td>
            </tr>
        </table>
        """
        st.markdown(html_tabela, unsafe_allow_html=True)
        st.caption(f"Amostra de pares analisada: {', '.join(peers)}")
else:
    st.info(f"O setor '{setor}' ainda não possui um dicionário de pares mapeado no nosso sistema para realizar o benchmark.")

# ==========================================
# DCF SIMPLIFICADO (Briefing 7 - Seção A)
# ==========================================
st.markdown("---")
with st.expander("🧮 DCF SIMPLIFICADO — VALOR INTRÍNSECO ESTIMADO", expanded=False):

    st.info("""
    Modelo DCF (Discounted Cash Flow) simplificado.
    Premissas são baseadas no histórico do ativo — ajuste conforme sua visão.
    ⚠️ O resultado é um RANGE estimado de valorização justa, não uma recomendação.
    """)

    # Busca segura de FCF (tenta via cashflow ou puxa o genérico via info)
    try:
        fcf_series = acao.cashflow.loc['Free Cash Flow'].dropna()
        fcf_atual  = fcf_series.iloc[0] if not fcf_series.empty else None
    except:
        fcf_atual = info.get('freeCashflow', None)

    shares = info.get('sharesOutstanding', None)

    if fcf_atual and shares and fcf_atual > 0:
        col1, col2, col3 = st.columns(3)
        with col1:
            g_pes = st.slider("Crescimento Pessimista %/ano", 0.0, 30.0, 5.0, 0.5)
        with col2:
            g_base = st.slider("Crescimento Base %/ano", 0.0, 30.0, 10.0, 0.5)
        with col3:
            g_otm = st.slider("Crescimento Otimista %/ano", 0.0, 50.0, 15.0, 0.5)

        col4, col5 = st.columns(2)
        with col4:
            wacc = st.slider("Taxa de Desconto (WACC) %", 5.0, 20.0, 10.0, 0.5)
        with col5:
            anos = st.slider("Horizonte (anos)", 3, 10, 5)

        def calcular_dcf(fcf, g_anual, wacc_anual, n_anos, shares_out):
            wacc_d = wacc_anual / 100
            g_d    = g_anual / 100
            g_perp = min(g_d * 0.3, 0.03)  # crescimento perpétuo conservador (capado em 3%)

            fluxos = []
            for t in range(1, n_anos + 1):
                fluxos.append(fcf * (1 + g_d)**t / (1 + wacc_d)**t)

            valor_terminal = (fcf * (1 + g_d)**n_anos * (1 + g_perp)) / ((wacc_d - g_perp) * (1 + wacc_d)**n_anos)
            valor_total = sum(fluxos) + valor_terminal
            return valor_total / shares_out

        vp = calcular_dcf(fcf_atual, g_pes, wacc, anos, shares)
        vb = calcular_dcf(fcf_atual, g_base, wacc, anos, shares)
        vo = calcular_dcf(fcf_atual, g_otm, wacc, anos, shares)

        moeda = "R$" if ticker_input.endswith('.SA') else "$"

        margem_seg = vb * 0.75  # preço alvo com margem de segurança de 25%

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PESSIMISTA", f"{moeda} {vp:.2f}")
        c2.metric("BASE", f"{moeda} {vb:.2f}")
        c3.metric("OTIMISTA", f"{moeda} {vo:.2f}")
        c4.metric("PREÇO ATUAL", f"{moeda} {preco_atual:.2f}", delta=f"{((preco_atual/vb)-1)*100:.1f}% vs. base", delta_color="inverse")

        # Sinalização visual
        if preco_atual < margem_seg:
            st.success(f"✅ O Preço atual está abaixo da margem de segurança do modelo ({moeda}{margem_seg:.2f})")
        elif preco_atual < vb:
            st.warning(f"📊 Preço está abaixo do valor base — dentro de uma zona justa de valorização")
        else:
            st.error(f"⚠️ Preço acima do valor intrínseco base — a ser negociado com prémio de {((preco_atual/vb)-1)*100:.1f}%")

        if st.button("🤖 GEMINI REVISA O DCF", key="btn_dcf_ia"):
            cache_dcf = get_cache_ia(ticker_input, 'dcf', max_horas=24)
            if cache_dcf:
                st.markdown(cache_dcf)
            else:
                with st.spinner("Enviando modelo matemático para a IA..."):
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    prompt = f"""
                    Revise este DCF simplificado para {ticker_input}:
                    FCF atual: {moeda}{fcf_atual/1e9:.2f}B
                    Crescimento base assumido: {g_base}% a.a. por {anos} anos
                    WACC: {wacc}%
                    Valor intrínseco base calculado: {moeda}{vb:.2f}
                    Preço atual: {moeda}{preco_atual:.2f}

                    Em português, escreva 3 parágrafos diretos:
                    1. As premissas de crescimento são realistas para o perfil histórico desta empresa?
                    2. O WACC de {wacc}% reflete bem o risco do ambiente que este ativo opera?
                    3. Qual a maior fragilidade oculta deste modelo para este ativo específico?
                    """
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    salvar_cache_ia(ticker_input, 'dcf', resp.text)
                    st.markdown(resp.text)
    else:
        st.warning("O Free Cash Flow (Fluxo de Caixa Livre) não está disponível para este ativo. O modelo DCF não é aplicável.")

# ==========================================
# COMPARAÇÃO TEMPORAL (Briefing 7 - Seção B)
# ==========================================
with st.expander("📅 MÚLTIPLOS HISTÓRICOS DO PRÓPRIO ATIVO", expanded=False):

    st.write("Acompanhe como os fundamentos deste ativo se comportam comparados ao seu próprio passado recente.")

    hist_mult = get_historico_multiplos(ticker_input)

    if len(hist_mult) >= 30:
        df_hm = pd.DataFrame(hist_mult)
        df_hm['data'] = pd.to_datetime(df_hm['data'])

        metrica_sel = st.selectbox(
            "Múltiplo Analisado:",
            ['pl','pvp','roe','margem','dy'],
            format_func=lambda x: {
                'pl':'P/L','pvp':'P/VP','roe':'ROE %',
                'margem':'Margem Líquida %','dy':'Dividend Yield %'
            }[x]
        )

        serie = df_hm.set_index('data')[metrica_sel].dropna()

        if not serie.empty:
            valor_atual = serie.iloc[-1]
            percentil = (serie < valor_atual).mean() * 100
            media = serie.mean()
            mediana = serie.median()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("ATUAL", f"{valor_atual:.2f}")
            c2.metric("MÉDIA HISTÓRICA", f"{media:.2f}")
            c3.metric("MEDIANA HISTÓRICA", f"{mediana:.2f}")
            c4.metric("PERCENTIL HISTÓRICO", f"{percentil:.0f}%", help="100% significa que está no nível mais alto do seu histórico.")

            # Gráfico com plotly e linhas de Percentil
            p25 = serie.quantile(0.25)
            p75 = serie.quantile(0.75)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=serie.index, y=serie,
                name=metrica_sel.upper(),
                line=dict(color='#FFFFFF', width=2)
            ))
            fig.add_hline(y=media, line_color='#FF9900', line_dash='dash', annotation_text="Média")
            fig.add_hline(y=p75, line_color='#FF0000', line_dash='dot', annotation_text="P75 (Pico/Caro)")
            fig.add_hline(y=p25, line_color='#00FF00', line_dash='dot', annotation_text="P25 (Fundo/Barato)")
            
            fig.update_layout(
                paper_bgcolor="#010101", plot_bgcolor="#010101",
                height=350, margin=dict(l=0,r=0,t=20,b=0),
                font=dict(family="Courier New", color="#888"),
                xaxis=dict(showgrid=True, gridcolor='#222'),
                yaxis=dict(showgrid=True, gridcolor='#222')
            )
            st.plotly_chart(fig, use_container_width=True)

            if percentil > 80:
                st.error(f"⚠️ Atenção: A métrica {metrica_sel.upper()} encontra-se no percentil {percentil:.0f}% (nível historicamente elevado para este ativo).")
            elif percentil < 25:
                st.success(f"✅ Oportunidade: A métrica {metrica_sel.upper()} encontra-se no percentil {percentil:.0f}% (nível historicamente descontado para este ativo).")
    else:
        dias_restantes = 30 - len(hist_mult)
        st.info(f"O histórico deste ativo não tem massa crítica ainda ({len(hist_mult)} dias capturados). O Health Score Engine está a acumular dados diariamente. Volte em {dias_restantes} dias para ver a dispersão percentil completa.")

# ==========================================
# CACHE DE ANÁLISE IA
# ==========================================
st.markdown("---")
st.markdown("#### SÍNTESE FUNDAMENTALISTA COM I.A.")

if st.button("RUN AI ANALYSIS", type="primary"):
    
    analise_em_cache = get_cache_ia(ticker_input, 'fundamental', max_horas=24)
    
    if analise_em_cache:
        st.success(f"⚡ Recuperado do Cache (Gerado nas últimas 24h). Economia de API realizada.")
        st.markdown(analise_em_cache)
    else:
        with st.spinner("Lendo balanços e enviando para o processador do Gemini..."):
            try:
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                
                prompt = f"""
                Você é um analista fundamentalista sênior estilo Warren Buffett.
                Analise a empresa {ticker_input} ({nome_empresa}) que atua no setor {setor}.
                
                Dados atuais:
                - P/L: {pl:.2f}
                - P/VP: {pvp:.2f}
                - ROE: {roe:.2f}%
                - DY: {dy:.2f}%
                
                Crie um resumo de 3 parágrafos:
                1. O que a empresa faz e como é seu fosso competitivo (moat).
                2. Uma análise fria destes múltiplos (está cara? barata? rentável?).
                3. O maior risco atual de investir nesta empresa.
                
                Responda em português, com formatação markdown. Seja direto e pragmático.
                """
                
                resposta = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                texto_analise = resposta.text
                
                salvar_cache_ia(ticker_input, 'fundamental', texto_analise)
                
                st.success("✅ Nova análise gerada pelo Gemini e salva no banco de dados.")
                st.markdown(texto_analise)
                
            except Exception as e:
                st.error(f"Erro na comunicação com a IA: {e}")