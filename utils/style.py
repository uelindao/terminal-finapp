import streamlit as st

def aplicar_tema():
    """
    Injeta o CSS centralizado do tema 'Bloomberg-lite' no Streamlit.
    """
    st.markdown("""
    <style>
        /* 1. Fundo da aplicação e cor base do texto */
        .stApp {
            background-color: #010101;
            color: #E0E0E0;
        }
        
        /* 2. Estilização de Títulos (h1 a h6) */
        h1, h2, h3, h4, h5, h6 {
            color: #FF9900 !important;
            font-family: 'Courier New', Courier, monospace;
            text-transform: uppercase;
            font-size: 1.2rem;
            margin-bottom: 0px;
        }
        
        /* 3. Ajuste de respiro superior (evita corte do topo) */
        .block-container {
            padding-top: 3.5rem;
            padding-bottom: 1rem;
        }
        
        /* 4. Estilização das Métricas (st.metric) */
        [data-testid="stMetricValue"] {
            color: #FFFFFF !important;
            font-family: 'Courier New', Courier, monospace;
            font-weight: bold;
            font-size: 1.6rem;
        }
        [data-testid="stMetricLabel"] {
            color: #888888 !important;
            font-family: 'Courier New', Courier, monospace;
            font-weight: bold;
            text-transform: uppercase;
            font-size: 0.8rem;
        }
        
        /* 5. Estilização dos Botões de Rádio (Filtros de Tempo) */
        div.row-widget.stRadio > div {
            background-color: #111111;
            padding: 10px;
            border-radius: 5px;
            border: 1px solid #333333;
        }
        
        /* 6. Estilização das Caixas de Notícias */
        .news-box {
            background-color: #111111;
            padding: 15px;
            border-left: 3px solid #FF9900;
            margin-bottom: 10px;
            font-family: 'Courier New', monospace;
        }
        .news-title {
            font-weight: bold;
            color: #FFFFFF;
            font-size: 1rem;
        }
        .news-publisher {
            color: #888888;
            font-size: 0.8rem;
            text-transform: uppercase;
        }
        
        /* 7. NOVO: Estilização de Tabelas / DataFrames */
        [data-testid="stDataFrame"] > div, .stDataFrame {
            background-color: #111111;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.85rem;
        }
        /* Cor de fundo para as células e cabeçalhos nativos */
        th, td {
            background-color: #111111 !important;
            color: #E0E0E0 !important;
        }
        
        /* 8. NOVO: Estilização de Abas (Tabs) */
        [data-testid="stTabs"] button {
            background-color: #111111 !important;
            color: #888888 !important;
            font-family: 'Courier New', Courier, monospace;
            font-weight: bold;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: #FF9900 !important;
            border-bottom: 2px solid #FF9900 !important;
            background-color: #010101 !important;
        }
    </style>
    """, unsafe_allow_html=True)