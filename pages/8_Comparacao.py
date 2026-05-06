import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
import plotly.express as px
from google import genai

# Importa o Design System e o Banco de Dados
from utils.style import aplicar_tema
from database.db import get_connection, get_cache_ia, salvar_cache_ia

# --- Configuração da Página ---
st.set_page_config(page_title="Análise Comparativa", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### ⚖️ ANÁLISE COMPARATIVA (COMPS)")

# ==========================================
# FUNÇÕES DE BANCO DE DADOS E TEMPLATES
# ==========================================
def salvar_comparacao_db(nome, tickers):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO comparacoes_salvas (nome, tickers) VALUES (?, ?)", (nome, json.dumps(tickers)))
    conn.commit()
    conn.close()

def carregar_comparacoes_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, nome, tickers FROM comparacoes_salvas ORDER BY criado_em DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Templates Setoriais (Padrões do Sistema)
TEMPLATES_SETORIAIS = {
    "🇧🇷 BR - Bancos Grandes": ["ITUB4.SA", "BBAS3.SA", "BBDC4.SA", "SANB11.SA"],
    "🇧🇷 BR - Petróleo e Óleo": ["PETR4.SA", "PRIO3.SA", "ENAT3.SA", "RECV3.SA"],
    "🇧🇷 BR - Elétricas (Ger/Transm)": ["ELET3.SA", "EGIE3.SA", "EQTL3.SA", "TAEE11.SA"],
    "🇧🇷 BR - Mineração e Siderurgia": ["VALE3.SA", "GGBR4.SA", "CSNA3.SA", "USIM5.SA"],
    "🇧🇷 BR - Varejo Vestuário": ["LREN3.SA", "ARZZ3.SA", "CEAB3.SA", "GUAR3.SA"],
    "🇧🇷 BR - Frigoríficos": ["JBSS3.SA", "MRFG3.SA", "BRFS3.SA", "BEEF3.SA"],
    "🇺🇸 US - Big Techs (Mag 7)": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"],
    "🇺🇸 US - Bancos": ["JPM", "BAC", "WFC", "GS", "MS"],
    "🇺🇸 US - Semicondutores": ["NVDA", "AMD", "INTC", "TSM", "ASML"],
    "🇺🇸 US - Saúde / Farma": ["JNJ", "UNH", "LLY", "PFE", "ABBV"],
    "🇺🇸 US - Petróleo": ["XOM", "CVX", "COP", "SLB"]
}

# ==========================================
# SEÇÃO 1 & 5: SELEÇÃO E SALVAMENTO DE ATIVOS
# ==========================================
st.markdown("---")

# Inicializa sessão para manter estado na tela
if "comps_tickers" not in st.session_state:
    st.session_state.comps_tickers = ["PETR4.SA", "PRIO3.SA", "ENAT3.SA"]
if "analise_ativa" not in st.session_state:
    st.session_state.analise_ativa = False

c_load, c_save, c_vazio = st.columns([3, 3, 4])
with c_load:
    # Monta as opções misturando Padrões do Sistema com os Salvos do Usuário
    opcoes_load = {"Selecione uma comparação...": []}
    
    for nome, tickers in TEMPLATES_SETORIAIS.items():
        opcoes_load[f"📚 PADRÃO: {nome}"] = tickers
        
    comps_salvas = carregar_comparacoes_db()
    for c in comps_salvas:
        opcoes_load[f"💾 SALVO: {c['nome']}"] = json.loads(c['tickers'])
        
    selecao_load = st.selectbox("Carregar Comparação Setorial:", list(opcoes_load.keys()))
    if st.button("CARREGAR", use_container_width=True) and selecao_load != "Selecione uma comparação...":
        st.session_state.comps_tickers = opcoes_load[selecao_load]
        st.session_state.analise_ativa = False
        st.rerun()

with c_save:
    nome_salvar = st.text_input("Nomear esta comparação (Ex: Minha Carteira):", "")
    if st.button("SALVAR COMPARAÇÃO ATUAL", use_container_width=True):
        if nome_salvar and len(st.session_state.comps_tickers) >= 2:
            salvar_comparacao_db(nome_salvar, st.session_state.comps_tickers)
            st.success("Salvo com sucesso!")
            st.rerun()
        else:
            st.warning("Dê um nome e selecione pelo menos 2 ativos.")

st.markdown("<br>", unsafe_allow_html=True)

# MULTISELECT PRINCIPAL
col_busca, col_add = st.columns([7, 3])
with col_busca:
    # Coleta todos os tickers possíveis para não dar erro no Streamlit
    todos_tickers_base = ["PETR4.SA", "VALE3.SA", "ITUB4.SA", "ABEV3.SA", "WEGE3.SA", "AAPL", "MSFT"]
    para_opcoes = set(todos_tickers_base + st.session_state.comps_tickers)
    for t_list in TEMPLATES_SETORIAIS.values():
        para_opcoes.update(t_list)
        
    tickers_selecionados = st.multiselect(
        "SELECIONE OS ATIVOS PARA A ANÁLISE (Máx: 8):", 
        options=sorted(list(para_opcoes)),
        default=st.session_state.comps_tickers,
        max_selections=8
    )
    st.session_state.comps_tickers = tickers_selecionados

with col_add:
    novo_ticker = st.text_input("Adicionar Ticker Personalizado:")
    if st.button("➕ ADICIONAR NA LISTA", use_container_width=True):
        if novo_ticker and novo_ticker.upper() not in st.session_state.comps_tickers:
            st.session_state.comps_tickers.append(novo_ticker.upper())
            st.rerun()

st.markdown("<br>", unsafe_allow_html=True)
if st.button("📊 ANALISAR COMPARAÇÃO", type="primary", use_container_width=True):
    if len(tickers_selecionados) < 2:
        st.error("Selecione pelo menos 2 ativos para comparar.")
    else:
        st.session_state.analise_ativa = True

# ==========================================
# MOTOR DA ANÁLISE (Executa apenas se ativo)
# ==========================================
if st.session_state.analise_ativa and len(st.session_state.comps_tickers) >= 2:
    tickers = st.session_state.comps_tickers
    
    with st.spinner("Coletando múltiplos e cruzando dados de mercado..."):
        dados = []
        for t in tickers:
            try:
                info = yf.Ticker(t).info
                pl = info.get('trailingPE', info.get('forwardPE', np.nan))
                pvp = info.get('priceToBook', np.nan)
                evebitda = info.get('enterpriseToEbitda', np.nan)
                roe = info.get('returnOnEquity', np.nan)
                margem = info.get('profitMargins', np.nan)
                dy = info.get('dividendYield', np.nan)
                beta = info.get('beta', np.nan)
                mcap = info.get('marketCap', np.nan)
                
                dados.append({
                    'Ticker': t,
                    'P/L': pl,
                    'P/VP': pvp,
                    'EV/EBITDA': evebitda,
                    'ROE%': (roe * 100) if not pd.isna(roe) else np.nan,
                    'Margem%': (margem * 100) if not pd.isna(margem) else np.nan,
                    'DY%': (dy * 100) if not pd.isna(dy) else np.nan,
                    'Beta': beta,
                    'Market Cap': mcap
                })
            except:
                pass
                
        df = pd.DataFrame(dados)
        
        # Filtra lixo estatístico
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        
        # ==========================================
        # SEÇÃO 2: TABELA DE MÚLTIPLOS COM QUARTIS
        # ==========================================
        st.markdown("---")
        st.markdown("#### 📑 MATRIZ DE MÚLTIPLOS (QUARTIS)")
        
        def color_quartiles(s):
            if s.name in ['P/L', 'P/VP', 'EV/EBITDA', 'Beta']: 
                q1 = s.quantile(0.25)
                q3 = s.quantile(0.75)
                return ['background-color: #003300; color: white' if v <= q1 and not pd.isna(v) else 
                        ('background-color: #330000; color: white' if v >= q3 and not pd.isna(v) else '') for v in s]
            elif s.name in ['ROE%', 'Margem%', 'DY%']: 
                q1 = s.quantile(0.25)
                q3 = s.quantile(0.75)
                return ['background-color: #003300; color: white' if v >= q3 and not pd.isna(v) else 
                        ('background-color: #330000; color: white' if v <= q1 and not pd.isna(v) else '') for v in s]
            else:
                return ['' for v in s]

        df_numerico = df.drop(columns=['Ticker'])
        linha_media = df_numerico.mean(numeric_only=True)
        linha_mediana = df_numerico.median(numeric_only=True)
        
        formatacao = {
            'P/L': '{:.2f}', 'P/VP': '{:.2f}', 'EV/EBITDA': '{:.2f}', 
            'ROE%': '{:.2f}%', 'Margem%': '{:.2f}%', 'DY%': '{:.2f}%', 
            'Beta': '{:.2f}', 'Market Cap': '${:,.0f}'
        }

        st.dataframe(
            df.style.apply(color_quartiles, axis=0).format(formatacao, na_rep="N/D"),
            use_container_width=True, hide_index=True
        )
        
        st.markdown("**Métricas do Grupo (Benchmark):**")
        c1, c2 = st.columns(2)
        with c1:
            df_media = pd.DataFrame([linha_media], index=['MÉDIA'])
            st.dataframe(df_media.style.format(formatacao, na_rep="N/D"), use_container_width=True)
        with c2:
            df_mediana = pd.DataFrame([linha_mediana], index=['MEDIANA'])
            st.dataframe(df_mediana.style.format(formatacao, na_rep="N/D"), use_container_width=True)
        
        # ==========================================
        # SEÇÃO 3: RADAR CHART (SCATTERPOLAR)
        # ==========================================
        st.markdown("---")
        st.markdown("#### 🎯 RADAR DE QUALIDADE (SCORE 0 a 100)")
        st.write("Métricas normalizadas relativas ao grupo. Um polígono maior indica fundamentos mais equilibrados em todas as pontas (Score 100 = Melhor do Grupo).")
        
        colunas_radar = ['P/L', 'ROE%', 'Margem%', 'DY%', 'P/VP', 'Beta']
        df_radar = df[['Ticker'] + colunas_radar].copy().fillna(0)
        
        fig_radar = go.Figure()
        
        for idx, row in df_radar.iterrows():
            scores = []
            for col in colunas_radar:
                val = row[col]
                max_val = df_radar[col].max()
                min_val = df_radar[col].min()
                
                if max_val == min_val:
                    score = 50 
                else:
                    norm = (val - min_val) / (max_val - min_val) * 100
                    if col in ['P/L', 'P/VP', 'Beta']:
                        score = 100 - norm
                    else:
                        score = norm
                scores.append(score)
            
            scores.append(scores[0])
            cats_fechado = colunas_radar + [colunas_radar[0]]
            
            fig_radar.add_trace(go.Scatterpolar(
                r=scores,
                theta=cats_fechado,
                fill='toself',
                name=row['Ticker']
            ))

        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], gridcolor="#333333"),
                angularaxis=dict(gridcolor="#333333")
            ),
            paper_bgcolor="#010101",
            plot_bgcolor="#010101",
            font=dict(color="#E0E0E0", family="Courier New"),
            margin=dict(l=40, r=40, t=40, b=40),
            height=500
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        # ==========================================
        # SEÇÃO 4: HISTÓRICO NORMALIZADO (BASE 100)
        # ==========================================
        st.markdown("---")
        st.markdown("#### 📈 PERFORMANCE HISTÓRICA (BASE 100)")
        
        tempo_hist = st.radio("Janela de Tempo:", ["1A", "3A", "5A"], horizontal=True)
        mapa_tempo = {"1A": "1y", "3A": "3y", "5A": "5y"}
        
        with st.spinner("Puxando histórico de preços..."):
            try:
                df_hist = yf.download(tickers, period=mapa_tempo[tempo_hist], auto_adjust=True, progress=False)['Close']
                
                if isinstance(df_hist, pd.Series):
                    df_hist = df_hist.to_frame()
                
                df_hist = df_hist.dropna(how='all')
                
                primeiro_valido = df_hist.bfill().iloc[0]
                df_norm = (df_hist / primeiro_valido) * 100
                
                if isinstance(df_norm.columns, pd.MultiIndex):
                    df_norm.columns = df_norm.columns.get_level_values(1)
                
                fig_hist = px.line(df_norm, x=df_norm.index, y=df_norm.columns)
                fig_hist.update_layout(
                    paper_bgcolor="#010101", plot_bgcolor="#010101",
                    xaxis=dict(showgrid=True, gridcolor='#222222', title=""),
                    yaxis=dict(showgrid=True, gridcolor='#222222', title="Base 100 (100 = 0%)"),
                    hovermode="x unified", height=450,
                    font=dict(family="Courier New", color="#888888"),
                    legend_title_text="Ativos"
                )
                
                fig_hist.add_hline(y=100, line_dash="dash", line_color="#888888", opacity=0.5)
                
                st.plotly_chart(fig_hist, use_container_width=True)
                
            except Exception as e:
                st.error(f"Erro ao processar gráfico histórico: {e}")

        # ==========================================
        # SEÇÃO 6: ANÁLISE IA DA COMPARAÇÃO
        # ==========================================
        st.markdown("---")
        st.markdown("#### 🤖 SÍNTESE DA COMPARAÇÃO VIA IA")
        
        chave_cache = f"comps_{'_'.join(sorted(tickers))}"
        
        if st.button("ANALISAR COMPARAÇÃO COM IA", type="primary"):
            cache_comps = get_cache_ia('COMPS', chave_cache, max_horas=24)
            
            if cache_comps:
                st.success("⚡ Recuperado do Cache (Gerado nas últimas 24h).")
                st.markdown(cache_comps)
            else:
                with st.spinner("Processando Matriz de Múltiplos e avaliando Valuation vs Qualidade..."):
                    try:
                        csv_data = df.to_csv(index=False, float_format='%.2f')
                        
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        prompt = f"""
                        Você é analista de equity institucional. 
                        Compare estas empresas baseando-se estritamente na tabela de múltiplos abaixo:
                        
                        {csv_data}
                        
                        Responda em português, com formatação markdown. 
                        Aponte diretamente e com justificativas numéricas curtas:
                        1. A empresa mais barata (foco em P/L, P/VP, EV/EBITDA).
                        2. A empresa de melhor qualidade/rentabilidade (foco em ROE, Margem).
                        3. A empresa de maior risco aparente (avaliando Beta e Múltiplos esticados).
                        
                        Seja objetivo e baseado APENAS nos dados fornecidos. 
                        Não faça recomendação de compra ou venda.
                        """
                        
                        resposta = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        
                        salvar_cache_ia('COMPS', chave_cache, resposta.text)
                        st.success("✅ Matriz avaliada pelo Gemini.")
                        st.markdown(resposta.text)
                        
                    except Exception as e:
                        st.error(f"Falha ao conectar com o modelo de IA: {e}")