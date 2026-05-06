import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
from google import genai

# Importa o Design System e as funções de Banco de Dados
from utils.style import aplicar_tema
from database.db import get_cache_ia, salvar_cache_ia

# --- Configuração da Página ---
st.set_page_config(page_title="Análise Fundamentalista", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 📊 RAIO-X FUNDAMENTALISTA")

# --- Barra de Busca Amigável ---
col_busca, col_vazia = st.columns([4, 6])
with col_busca:
    lista_opcoes = [
        "PETR4.SA - Petrobras (Energia)", 
        "VALE3.SA - Vale (Materiais Básicos)", 
        "ITUB4.SA - Itaú Unibanco (Financeiro)", 
        "BBAS3.SA - Banco do Brasil (Financeiro)", 
        "BBDC4.SA - Bradesco (Financeiro)", 
        "ABEV3.SA - Ambev (Consumo)", 
        "WEGE3.SA - WEG (Indústria)", 
        "PRIO3.SA - Prio (Energia)", 
        "GGBR4.SA - Gerdau (Materiais Básicos)",
        "CSAN3.SA - Cosan (Energia)",
        "RENT3.SA - Localiza (Indústria)",
        "AAPL - Apple (Tecnologia)", 
        "MSFT - Microsoft (Tecnologia)", 
        "NVDA - Nvidia (Tecnologia)", 
        "GOOGL - Alphabet/Google (Tecnologia)",
        "TSLA - Tesla (Consumo Automotivo)",
        "OUTRO (Digitar manualmente)..."
    ]
    
    selecao = st.selectbox("SELECIONE O ATIVO (Ou digite para pesquisar):", lista_opcoes)
    
    if selecao == "OUTRO (Digitar manualmente)...":
        ticker_input = st.text_input("Digite o código do Ticker (Ex: KLBN11.SA):", "").strip().upper()
    else:
        # Extrai apenas o Ticker (ex: "PETR4.SA") separando pelo traço
        ticker_input = selecao.split(" - ")[0].strip()

if not ticker_input:
    st.warning("Por favor, selecione ou digite um ticker válido.")
    st.stop()

# --- Coleta de Dados Base ---
with st.spinner(f"Coletando balanços e múltiplos de {ticker_input}..."):
    try:
        acao = yf.Ticker(ticker_input)
        info = acao.info
        
        # Puxando dados essenciais
        preco_atual = info.get('currentPrice', info.get('regularMarketPrice', 0))
        pl = info.get('trailingPE', info.get('forwardPE', np.nan))
        pvp = info.get('priceToBook', np.nan)
        roe = info.get('returnOnEquity', np.nan) * 100 if info.get('returnOnEquity') else np.nan
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
# ADIÇÃO 2: SECTOR BENCHMARK
# ==========================================
st.markdown("---")
st.markdown("#### SECTOR BENCHMARK (Comparativo de Pares)")

peers_por_setor = {
    "Energy": ["PETR4.SA", "PRIO3.SA", "CSAN3.SA", "XOM", "CVX"],
    "Financial Services": ["ITUB4.SA", "BBAS3.SA", "BBDC4.SA", "JPM", "BAC"],
    "Basic Materials": ["VALE3.SA", "GGBR4.SA", "RIO", "BHP"],
    "Technology": ["AAPL", "MSFT", "NVDA", "GOOGL"],
    "Consumer Defensive": ["ABEV3.SA", "KO", "PEP"],
    "Industrials": ["WEGE3.SA", "RENT3.SA", "GE", "MMM"],
}

if setor in peers_por_setor:
    with st.spinner(f"Mapeando o setor de {setor}..."):
        peers = peers_por_setor[setor]
        
        # Garante que o ativo analisado esteja na lista (para precisão da média)
        if ticker_input not in peers:
            peers.append(ticker_input)
            
        dados_setor = []
        for p in peers:
            try:
                p_info = yf.Ticker(p).info
                p_pl = p_info.get('trailingPE', p_info.get('forwardPE', np.nan))
                p_roe = p_info.get('returnOnEquity', np.nan) * 100 if p_info.get('returnOnEquity') else np.nan
                p_dy = p_info.get('dividendYield', 0) * 100 if p_info.get('dividendYield') else 0
                dados_setor.append({'Ticker': p, 'P/L': p_pl, 'ROE': p_roe, 'DY': p_dy})
            except:
                pass
                
        df_setor = pd.DataFrame(dados_setor)
        
        # Calcula Média e Mediana ignorando os NaNs
        media_pl = df_setor['P/L'].mean()
        mediana_pl = df_setor['P/L'].median()
        media_roe = df_setor['ROE'].mean()
        mediana_roe = df_setor['ROE'].median()
        media_dy = df_setor['DY'].mean()
        mediana_dy = df_setor['DY'].median()

        # Define as cores com base na comparação (Ativo x Mediana)
        cor_pl = "#00FF00" if pl < mediana_pl else "#FF0000" # P/L: Menor é melhor
        cor_roe = "#00FF00" if roe > mediana_roe else "#FF0000" # ROE: Maior é melhor
        cor_dy = "#00FF00" if dy > mediana_dy else "#FF0000" # DY: Maior é melhor

        # Tabela HTML customizada para renderizar as cores direto no Markdown
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
# ADIÇÃO 1: CACHE DE ANÁLISE IA
# ==========================================
st.markdown("---")
st.markdown("#### SÍNTESE FUNDAMENTALISTA COM I.A.")

if st.button("RUN AI ANALYSIS", type="primary"):
    
    # 1. Verifica se já existe uma análise gerada nas últimas 24 horas no SQLite
    analise_em_cache = get_cache_ia(ticker_input, 'fundamental', max_horas=24)
    
    if analise_em_cache:
        st.success(f"⚡ Recuperado do Cache (Gerado nas últimas 24h). Economia de API realizada.")
        st.markdown(analise_em_cache)
        
    else:
        # 2. Se não tem cache, aciona a IA
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
                
                # 3. Salva no banco de dados para os próximos 24 horas
                salvar_cache_ia(ticker_input, 'fundamental', texto_analise)
                
                st.success("✅ Nova análise gerada pelo Gemini e salva no banco de dados.")
                st.markdown(texto_analise)
                
            except Exception as e:
                st.error(f"Erro na comunicação com a IA: {e}")