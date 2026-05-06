import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from scipy.stats import pearsonr, spearmanr
from bcb import sgs
from fredapi import Fred
import datetime

# Importa o Design System
from utils.style import aplicar_tema

# --- Configuração da Página ---
st.set_page_config(page_title="Overlay Macro vs Micro", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

st.markdown("### 🔭 OVERLAY MACROECONÔMICO E CORRELAÇÃO")
st.write("Sobreponha o preço de ativos com indicadores macroeconômicos globais para encontrar relações de causa e efeito na sua tese de investimento.")

# Aviso amigável caso falte a chave do FRED
if "FRED_API_KEY" not in st.secrets:
    st.warning("⚠️ A chave da API do FRED não foi encontrada no arquivo `secrets.toml`. Os indicadores dos EUA e Europa falharão.")

# ==========================================
# CATÁLOGO DE INDICADORES
# ==========================================
indicadores_catalogo = {
    # BRASIL
    "🇧🇷 SELIC": {"fonte": "BCB", "codigo": 432},
    "🇧🇷 IPCA Mensal": {"fonte": "BCB", "codigo": 433},
    "🇧🇷 Dólar (PTAX)": {"fonte": "BCB", "codigo": 1},
    "🇧🇷 Desemprego": {"fonte": "BCB", "codigo": 24369},
    # EUA
    "🇺🇸 Fed Funds Rate": {"fonte": "FRED", "serie": "FEDFUNDS"},
    "🇺🇸 CPI Mensal": {"fonte": "FRED", "serie": "CPIAUCSL"},
    "🇺🇸 Treasury 10Y": {"fonte": "FRED", "serie": "DGS10"},
    "🇺🇸 VIX": {"fonte": "FRED", "serie": "VIXCLS"},
    "🇺🇸 DXY (Índice Dólar)": {"fonte": "FRED", "serie": "DTWEXBGS"},
    # EUROPA
    "🇪🇺 BCE Rate": {"fonte": "FRED", "serie": "ECBDFR"},
    "🇪🇺 Euro Area 10Y": {"fonte": "FRED", "serie": "IRLTLT01EZM156N"},
    # COMMODITIES (via yfinance)
    "🛢️ Petróleo WTI": {"fonte": "YF", "ticker": "CL=F"},
    "🥇 Ouro": {"fonte": "YF", "ticker": "GC=F"},
}

opcoes_ind1 = list(indicadores_catalogo.keys())
opcoes_ind2 = ["Nenhum"] + list(indicadores_catalogo.keys())

# ==========================================
# PAINEL DE CONTROLE (UI)
# ==========================================
st.markdown("---")
c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 3, 3])

with c1:
    ticker_input = st.text_input("TICKER DO ATIVO (Ex: PETR4.SA, SPY):", "PETR4.SA").strip().upper()
with c2:
    tipo_preco = st.radio("Série de Preço:", ["Ajustado (Adj Close)", "Sem Ajuste (Close)"], horizontal=True)
with c3:
    periodo_str = st.selectbox("Período:", ["1A", "2A", "3A", "5A"])
with c4:
    ind1_selecionado = st.selectbox("Indicador Macro 1 (Obrigatório):", opcoes_ind1, index=0) # Default SELIC
with c5:
    ind2_selecionado = st.selectbox("Indicador Macro 2 (Opcional):", opcoes_ind2, index=0) # Default Nenhum

btn_gerar = st.button("GERAR OVERLAY ESTRUTURAL", type="primary", use_container_width=True)

# Mapeia tempo
mapa_periodos = {"1A": "1y", "2A": "2y", "3A": "3y", "5A": "5y"}
periodo_yf = mapa_periodos[periodo_str]
anos = int(periodo_str[0])
data_inicio = datetime.datetime.today() - datetime.timedelta(days=365 * anos)

# ==========================================
# FUNÇÕES DE BUSCA DE DADOS
# ==========================================
def buscar_indicador(nome_selecionado, data_start):
    if nome_selecionado == "Nenhum":
        return None
        
    config = indicadores_catalogo[nome_selecionado]
    fonte = config["fonte"]
    
    try:
        if fonte == "BCB":
            df = sgs.get({nome_selecionado: config["codigo"]}, start=data_start)
            return df[nome_selecionado] # Retorna Series
            
        elif fonte == "FRED":
            fred = Fred(api_key=st.secrets["FRED_API_KEY"])
            serie = fred.get_series(config["serie"], observation_start=data_start)
            serie.name = nome_selecionado
            # Trata CPI transformando em variação mensal %
            if config["serie"] == "CPIAUCSL":
                serie = serie.pct_change() * 100
                serie.name = "🇺🇸 CPI Mensal (%)"
            return serie
            
        elif fonte == "YF":
            df = yf.download(config["ticker"], start=data_start, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                serie = df['Close'][config["ticker"]]
            else:
                serie = df['Close']
            serie.name = nome_selecionado
            return serie
    except Exception as e:
        st.error(f"Erro ao buscar {nome_selecionado}: {e}")
        return None

def interpretar_correlacao(r):
    abs_r = abs(r)
    if abs_r >= 0.7:
        forca = "FORTE"
    elif abs_r >= 0.4:
        forca = "MODERADA"
    else:
        forca = "FRACA"
        
    direcao = "DIRETA (Média/Longo Prazo)" if r > 0 else "INVERSA (Média/Longo Prazo)"
    
    # Textos customizados
    if forca == "FRACA":
        txt = f"**CORRELAÇÃO {forca} ({direcao})**: O indicador parece não exercer influência gravitacional pesada sobre este ativo neste período específico."
    elif r > 0:
        txt = f"**CORRELAÇÃO {forca} E {direcao}**: Historicamente, quando o indicador sobe, o ativo tende a **ACOMPANHAR A ALTA**."
    else:
        txt = f"**CORRELAÇÃO {forca} E {direcao}**: Historicamente, quando o indicador sobe, o ativo tende a **SOFRER QUEDAS**."
        
    return txt

# ==========================================
# EXECUÇÃO DO MOTOR
# ==========================================
if btn_gerar:
    if not ticker_input:
        st.warning("Preencha o Ticker do ativo.")
        st.stop()

    with st.spinner("Sincronizando frequências de tempo entre Mercado e Indicadores..."):
        # 1. Busca Ativo
        coluna_preco = "Adj Close" if "Ajustado" in tipo_preco else "Close"
        try:
            # Puxa o histórico de forma robusta
            ativo_df = yf.Ticker(ticker_input).history(period=periodo_yf)
            # YFinance padroniza colunas em inglês internamente no .history()
            coluna_real = "Close" # history() já ajusta internamente se auto_adjust=True (padrão)
            
            # Se o usuário pediu especificamente "Sem ajuste", temos que garantir o download cru
            if coluna_preco == "Close":
                ativo_df_cru = yf.download(ticker_input, period=periodo_yf, auto_adjust=False, progress=False)
                if isinstance(ativo_df_cru.columns, pd.MultiIndex):
                    serie_ativo = ativo_df_cru['Close'][ticker_input]
                else:
                    serie_ativo = ativo_df_cru['Close']
            else:
                # Adj Close
                ativo_df_adj = yf.download(ticker_input, period=periodo_yf, auto_adjust=True, progress=False)
                if isinstance(ativo_df_adj.columns, pd.MultiIndex):
                    serie_ativo = ativo_df_adj['Close'][ticker_input]
                else:
                    serie_ativo = ativo_df_adj['Close']
                    
            serie_ativo.name = f"Preço {ticker_input}"
            
            # Normaliza timezone para evitar conflitos no merge
            serie_ativo.index = serie_ativo.index.tz_localize(None) 
            
        except Exception as e:
            st.error(f"Erro ao buscar ativo {ticker_input}: {e}")
            st.stop()

        if serie_ativo.empty:
            st.error("Não foram encontrados dados de preço para este ticker.")
            st.stop()

        # 2. Busca Indicadores
        s1 = buscar_indicador(ind1_selecionado, data_inicio)
        if s1 is not None: s1.index = s1.index.tz_localize(None)
            
        s2 = buscar_indicador(ind2_selecionado, data_inicio) if ind2_selecionado != "Nenhum" else None
        if s2 is not None: s2.index = s2.index.tz_localize(None)

        # 3. Consolidação de Frequências (Magia do Pandas)
        # Junta todos usando o índice do ativo (dias de pregão) como base
        df_merged = pd.DataFrame(serie_ativo)
        
        if s1 is not None:
            df_merged = df_merged.join(pd.DataFrame(s1), how='outer')
        if s2 is not None:
            df_merged = df_merged.join(pd.DataFrame(s2), how='outer')
            
        # Preenche os buracos gerados por feriados ou dados mensais arrastando o último valor conhecido (Forward Fill)
        df_merged = df_merged.ffill()
        
        # Filtra para mostrar apenas os dias em que o mercado estava aberto (exclui finais de semana puros gerados pelos indicadores)
        df_merged = df_merged.dropna(subset=[f"Preço {ticker_input}"])
        
        # Dropa os NaNs iniciais caso o indicador tenha começado a sair depois do ativo
        df_merged = df_merged.dropna()

        # ==========================================
        # CONSTRUÇÃO DO GRÁFICO (Plotly Dual-Axis)
        # ==========================================
        st.info("💡 **Nota de Design:** O gráfico utiliza eixos duplos. As linhas coloridas seguem a escala da direita, enquanto o ativo principal segue a escala de preço da esquerda. A comparação visual é absoluta, sem necessidade de normalização.")

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Traço 1: Ativo (Eixo Secundário = Falso -> Eixo Esquerdo)
        fig.add_trace(
            go.Scatter(x=df_merged.index, y=df_merged[f"Preço {ticker_input}"], name=f"{ticker_input}", line=dict(color="#FFFFFF", width=2)),
            secondary_y=False,
        )

        nome_s1 = s1.name if s1 is not None else ind1_selecionado
        # Traço 2: Ind 1 (Eixo Secundário = Verdadeiro -> Eixo Direito)
        if s1 is not None:
            fig.add_trace(
                go.Scatter(x=df_merged.index, y=df_merged[nome_s1], name=nome_s1, line=dict(color="#FF9900", width=1.5)),
                secondary_y=True,
            )

        nome_s2 = s2.name if s2 is not None else ind2_selecionado
        # Traço 3: Ind 2 (Eixo Direito também)
        if s2 is not None:
            fig.add_trace(
                go.Scatter(x=df_merged.index, y=df_merged[nome_s2], name=nome_s2, line=dict(color="#00FFFF", width=1.5)),
                secondary_y=True,
            )

        # Ajustes de Layout
        fig.update_layout(
            paper_bgcolor="#010101", 
            plot_bgcolor="#010101",
            height=550,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#E0E0E0")),
            margin=dict(l=0, r=0, t=50, b=0),
            font=dict(family="Courier New")
        )
        
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#222222', color="#888888")
        fig.update_yaxes(title_text="Preço do Ativo (R$ / US$)", showgrid=False, color="#FFFFFF", secondary_y=False)
        fig.update_yaxes(title_text="Indicadores Macro (% / Pts)", showgrid=True, gridwidth=1, gridcolor='#222222', color="#FF9900", secondary_y=True)

        st.plotly_chart(fig, use_container_width=True)

        # ==========================================
        # ANÁLISE DE CORRELAÇÃO MATEMÁTICA
        # ==========================================
        st.markdown("### 🧮 VETORES DE CORRELAÇÃO MATEMÁTICA")
        
        if len(df_merged) > 30: # Garante validade estatística
            array_preco = df_merged[f"Preço {ticker_input}"].values
            
            # Avalia Indicador 1
            if s1 is not None:
                array_ind1 = df_merged[nome_s1].values
                p_r, _ = pearsonr(array_preco, array_ind1)
                s_rho, _ = spearmanr(array_preco, array_ind1)
                
                with st.container():
                    st.markdown(f"<div style='background-color:#111111; padding:15px; border-left:3px solid #FF9900; margin-bottom:10px;'>", unsafe_allow_html=True)
                    st.markdown(f"<h4 style='margin-top:0px; color:#FF9900;'>{ticker_input}  vs  {nome_s1}</h4>", unsafe_allow_html=True)
                    st.markdown(f"**Correlação Linear (Pearson):** {p_r:.2f} | **Correlação de Ranking (Spearman):** {s_rho:.2f}")
                    st.markdown(interpretar_correlacao(s_rho)) # Usa spearman pois ativos não são perfeitamente lineares
                    st.markdown("</div>", unsafe_allow_html=True)
                    
            # Avalia Indicador 2
            if s2 is not None:
                array_ind2 = df_merged[nome_s2].values
                p_r2, _ = pearsonr(array_preco, array_ind2)
                s_rho2, _ = spearmanr(array_preco, array_ind2)
                
                with st.container():
                    st.markdown(f"<div style='background-color:#111111; padding:15px; border-left:3px solid #00FFFF; margin-bottom:10px;'>", unsafe_allow_html=True)
                    st.markdown(f"<h4 style='margin-top:0px; color:#00FFFF;'>{ticker_input}  vs  {nome_s2}</h4>", unsafe_allow_html=True)
                    st.markdown(f"**Correlação Linear (Pearson):** {p_r2:.2f} | **Correlação de Ranking (Spearman):** {s_rho2:.2f}")
                    st.markdown(interpretar_correlacao(s_rho2))
                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("Amostragem de dados muito curta para extrair correlações estatísticas significativas (menos de 30 dias contínuos).")