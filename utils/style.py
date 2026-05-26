"""
utils/style.py — v3.0  Bloomberg/Eikon institutional theme.
Denso, funcional, informação máxima por pixel.
Princípios: padding -50%, fontes menores, cantos retos, cores sutis.
"""
import streamlit as st


def aplicar_tema():
    """Injeta o CSS global do design system institucional."""
    css = """
    <style>

    /* ═══════════════════════════════════════════════════
       RESET E LAYOUT BASE
       ═══════════════════════════════════════════════════ */

    .block-container {
        padding-top: 0.75rem !important;
        padding-bottom: 1rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
    }

    /* Remove espaço em branco padrão do Streamlit */
    .main > div { padding-top: 0 !important; }
    [data-testid="stAppViewContainer"] { background-color: #030303; }
    [data-testid="stHeader"] { background: transparent; }

    /* ═══════════════════════════════════════════════════
       TIPOGRAFIA COMPACTA
       ═══════════════════════════════════════════════════ */

    /* Nível 1: Título de página — menor e mais tenso */
    .page-title {
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        font-weight: bold;
        color: #FF9900;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        border-bottom: 1px solid #1a1a1a;
        padding-bottom: 5px;
        margin-bottom: 10px;
    }

    /* Nível 2: Título de seção */
    .section-title {
        font-family: 'Courier New', monospace;
        font-size: 0.68rem;
        font-weight: bold;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        border-bottom: 1px solid #141414;
        padding-bottom: 3px;
        margin-bottom: 8px;
        margin-top: 14px;
    }

    /* Nível 3: Label de campo */
    .field-label {
        font-family: 'Courier New', monospace;
        font-size: 0.62rem;
        color: #444;
        text-transform: uppercase;
        letter-spacing: 0.10em;
    }

    /* Corpo de texto analítico */
    .body-text {
        font-family: 'Courier New', monospace;
        font-size: 0.78rem;
        color: #aaa;
        line-height: 1.5;
    }

    /* Override de markdown gerado pelo Streamlit */
    .stMarkdown p, .stMarkdown li {
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        color: #aaa;
        line-height: 1.5;
    }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: 'Courier New', monospace;
        color: #FF9900;
        letter-spacing: 0.06em;
    }
    .stMarkdown h5 {
        font-family: 'Courier New', monospace;
        font-size: 0.72rem;
        color: #555;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-weight: bold;
        margin-bottom: 6px;
    }

    /* ═══════════════════════════════════════════════════
       CORES SEMÂNTICAS
       ═══════════════════════════════════════════════════ */

    .color-bull  { color: #00C853 !important; }
    .color-bear  { color: #FF1744 !important; }
    .color-amber { color: #FF9900 !important; }
    .color-info  { color: #00B0FF !important; }
    .color-muted { color: #444444 !important; }

    /* Fundos com borda esquerda — sem background excessivo */
    .bg-bull  { background-color: #050f08; border-left: 2px solid #00C853; }
    .bg-bear  { background-color: #0f0305; border-left: 2px solid #FF1744; }
    .bg-amber { background-color: #0f0800; border-left: 2px solid #FF9900; }
    .bg-info  { background-color: #000c12; border-left: 2px solid #00B0FF; }

    /* ═══════════════════════════════════════════════════
       CARDS — CANTOS RETOS, PADDING MÍNIMO
       ═══════════════════════════════════════════════════ */

    .card {
        background-color: #080808;
        border: 1px solid #181818;
        border-radius: 2px;
        padding: 8px 10px;
        margin-bottom: 6px;
    }

    .card-bull  { border-left: 2px solid #00C853; }
    .card-bear  { border-left: 2px solid #FF1744; }
    .card-amber { border-left: 2px solid #FF9900; }
    .card-info  { border-left: 2px solid #00B0FF; }

    /* Card de métrica — compacto */
    .metric-card {
        background-color: #080808;
        border: 1px solid #181818;
        border-radius: 2px;
        padding: 7px 10px;
        text-align: left;
    }
    .metric-card .metric-label {
        font-family: 'Courier New', monospace;
        font-size: 0.60rem;
        color: #444;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 2px;
    }
    .metric-card .metric-value {
        font-family: 'Courier New', monospace;
        font-size: 1.2rem;
        font-weight: bold;
        color: #E8E8E8;
        line-height: 1.15;
    }
    .metric-card .metric-delta {
        font-family: 'Courier New', monospace;
        font-size: 0.68rem;
        margin-top: 1px;
        color: #555;
    }

    /* ═══════════════════════════════════════════════════
       BADGES — MICRO TAGS
       ═══════════════════════════════════════════════════ */

    .badge {
        display: inline-block;
        padding: 1px 5px;
        border-radius: 1px;
        font-family: 'Courier New', monospace;
        font-size: 0.60rem;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-bull  { background: #050f08; color: #00C853; border: 1px solid #00C853; }
    .badge-bear  { background: #0f0305; color: #FF1744; border: 1px solid #FF1744; }
    .badge-amber { background: #0f0800; color: #FF9900; border: 1px solid #FF9900; }
    .badge-info  { background: #000c12; color: #00B0FF; border: 1px solid #00B0FF; }
    .badge-muted { background: #0d0d0d; color: #444;    border: 1px solid #222; }

    /* ═══════════════════════════════════════════════════
       BOTÕES — 28 PX, RETANGULARES
       ═══════════════════════════════════════════════════ */

    /* Primário */
    [data-testid="stBaseButton-primary"] {
        background-color: #FF9900 !important;
        color: #000 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.70rem !important;
        font-weight: bold !important;
        text-transform: uppercase !important;
        letter-spacing: 0.07em !important;
        border: none !important;
        border-radius: 2px !important;
        height: 28px !important;
        min-height: 28px !important;
        padding: 0 10px !important;
        line-height: 28px !important;
    }
    [data-testid="stBaseButton-primary"]:hover {
        background-color: #e68a00 !important;
    }

    /* Secundário */
    [data-testid="stBaseButton-secondary"] {
        background-color: transparent !important;
        color: #555 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.70rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        border: 1px solid #242424 !important;
        border-radius: 2px !important;
        height: 28px !important;
        min-height: 28px !important;
        padding: 0 10px !important;
        line-height: 28px !important;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        border-color: #FF9900 !important;
        color: #FF9900 !important;
        background-color: #0f0800 !important;
    }

    /* Tamanho uniforme independente de use_container_width */
    [data-testid="stBaseButton-primary"] p,
    [data-testid="stBaseButton-secondary"] p {
        font-size: 0.70rem !important;
        margin: 0 !important;
        line-height: 28px !important;
    }

    /* ═══════════════════════════════════════════════════
       INPUTS — COMPACTOS
       ═══════════════════════════════════════════════════ */

    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea {
        background-color: #080808 !important;
        border: 1px solid #1e1e1e !important;
        border-radius: 2px !important;
        color: #D0D0D0 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.80rem !important;
        padding: 4px 8px !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: #FF9900 !important;
        box-shadow: 0 0 0 1px rgba(255,153,0,0.20) !important;
    }

    /* Labels dos inputs */
    [data-testid="stTextInput"] label,
    [data-testid="stNumberInput"] label,
    [data-testid="stSelectbox"] label,
    [data-testid="stMultiSelect"] label,
    [data-testid="stTextArea"] label,
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label {
        font-family: 'Courier New', monospace !important;
        font-size: 0.65rem !important;
        color: #444 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
    }

    /* Selectbox */
    [data-testid="stSelectbox"] > div > div {
        background-color: #080808 !important;
        border: 1px solid #1e1e1e !important;
        border-radius: 2px !important;
        color: #D0D0D0 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.80rem !important;
        min-height: 30px !important;
    }

    /* Multiselect */
    [data-testid="stMultiSelect"] > div > div {
        background-color: #080808 !important;
        border: 1px solid #1e1e1e !important;
        border-radius: 2px !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.78rem !important;
    }

    /* Radio */
    [data-testid="stRadio"] > div {
        gap: 4px !important;
    }
    [data-testid="stRadio"] label {
        font-size: 0.72rem !important;
        color: #666 !important;
        padding: 2px 6px !important;
        text-transform: none !important;
    }

    /* ═══════════════════════════════════════════════════
       TABELAS E DATAFRAMES
       ═══════════════════════════════════════════════════ */

    [data-testid="stDataFrame"] {
        border: 1px solid #141414;
        border-radius: 2px;
        overflow: hidden;
    }
    [data-testid="stDataFrame"] thead tr th {
        background-color: #0a0a0a !important;
        color: #FF9900 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.62rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.09em !important;
        border-bottom: 1px solid #1a1a1a !important;
        padding: 4px 8px !important;
    }
    [data-testid="stDataFrame"] tbody tr td {
        font-family: 'Courier New', monospace !important;
        font-size: 0.74rem !important;
        padding: 3px 8px !important;
        border-bottom: 1px solid #0e0e0e !important;
    }
    [data-testid="stDataFrame"] tbody tr:nth-child(even) td {
        background-color: #060606 !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover td {
        background-color: #101010 !important;
    }

    /* ═══════════════════════════════════════════════════
       SIDEBAR — MAIS ESCURA E COMPACTA
       ═══════════════════════════════════════════════════ */

    [data-testid="stSidebar"] {
        background-color: #030303;
        border-right: 1px solid #141414;
    }
    [data-testid="stSidebar"] > div {
        padding-top: 0.5rem;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
        font-family: 'Courier New', monospace;
        font-size: 0.72rem;
        color: #555;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        padding: 5px 10px;
        border-radius: 2px;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {
        background-color: #0a0a0a;
        color: #FF9900;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] [aria-current="page"] {
        background-color: #0f0800;
        color: #FF9900 !important;
        border-left: 2px solid #FF9900;
        padding-left: 8px;
    }

    /* Texto na sidebar */
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] .stMarkdown p {
        font-size: 0.72rem !important;
        color: #555 !important;
    }

    /* ═══════════════════════════════════════════════════
       ABAS (TABS) — PLANAS E COMPACTAS
       ═══════════════════════════════════════════════════ */

    [data-testid="stTabs"] [role="tablist"] {
        border-bottom: 1px solid #141414;
        gap: 1px;
        padding-bottom: 0;
    }
    [data-testid="stTabs"] [role="tab"] {
        font-family: 'Courier New', monospace !important;
        font-size: 0.65rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.10em !important;
        color: #444 !important;
        padding: 5px 12px !important;
        border-radius: 0 !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        background: transparent !important;
    }
    [data-testid="stTabs"] [role="tab"]:hover {
        color: #888 !important;
        background-color: #0a0a0a !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: #FF9900 !important;
        background-color: transparent !important;
        border-bottom: 2px solid #FF9900 !important;
    }

    /* Conteúdo da aba — padding mínimo */
    [data-testid="stTabsContent"] {
        padding-top: 0.75rem !important;
    }

    /* ═══════════════════════════════════════════════════
       EXPANDERS — MENOS DESTAQUE, MAIS FUNCIONAL
       ═══════════════════════════════════════════════════ */

    [data-testid="stExpander"] {
        border: 1px solid #141414 !important;
        border-radius: 2px !important;
        background-color: #060606 !important;
        margin-bottom: 5px !important;
    }
    [data-testid="stExpander"] summary {
        font-family: 'Courier New', monospace !important;
        font-size: 0.70rem !important;
        color: #555 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        padding: 7px 10px !important;
        min-height: 0 !important;
    }
    [data-testid="stExpander"] summary:hover {
        color: #FF9900 !important;
        background-color: #0a0a0a !important;
    }

    /* ═══════════════════════════════════════════════════
       MÉTRICAS NATIVAS DO STREAMLIT
       ═══════════════════════════════════════════════════ */

    [data-testid="stMetric"] {
        background-color: #080808;
        border: 1px solid #181818;
        border-radius: 2px;
        padding: 6px 10px;
    }
    [data-testid="stMetricLabel"] {
        font-family: 'Courier New', monospace !important;
        font-size: 0.60rem !important;
        color: #444 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.10em !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Courier New', monospace !important;
        font-size: 1.1rem !important;
        font-weight: bold !important;
        color: #E8E8E8 !important;
    }
    [data-testid="stMetricDelta"] {
        font-family: 'Courier New', monospace !important;
        font-size: 0.66rem !important;
    }

    /* ═══════════════════════════════════════════════════
       ALERTAS / STATUS CARDS
       ═══════════════════════════════════════════════════ */

    [data-testid="stAlert"] {
        border-radius: 2px !important;
        padding: 6px 10px !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.74rem !important;
    }
    [data-testid="stSuccess"] {
        background-color: #050f08 !important;
        border: 1px solid #00C853 !important;
        color: #00C853 !important;
    }
    [data-testid="stError"] {
        background-color: #0f0305 !important;
        border: 1px solid #FF1744 !important;
        color: #FF1744 !important;
    }
    [data-testid="stWarning"] {
        background-color: #0f0800 !important;
        border: 1px solid #FF9900 !important;
        color: #FF9900 !important;
    }
    [data-testid="stInfo"] {
        background-color: #000c12 !important;
        border: 1px solid #00B0FF !important;
        color: #00B0FF !important;
    }

    /* ═══════════════════════════════════════════════════
       CHAT / MENSAGENS IA
       ═══════════════════════════════════════════════════ */

    [data-testid="stChatMessage"] {
        background-color: #060606 !important;
        border: 1px solid #141414 !important;
        border-radius: 2px !important;
        padding: 8px 12px !important;
        margin-bottom: 4px !important;
    }
    [data-testid="stChatInput"] textarea {
        background-color: #080808 !important;
        border: 1px solid #1e1e1e !important;
        border-radius: 2px !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.78rem !important;
        color: #D0D0D0 !important;
    }

    /* ═══════════════════════════════════════════════════
       SPINNER / PROGRESS
       ═══════════════════════════════════════════════════ */

    [data-testid="stSpinner"] {
        font-family: 'Courier New', monospace !important;
        font-size: 0.72rem !important;
        color: #555 !important;
    }
    [data-testid="stProgress"] > div > div {
        background-color: #FF9900 !important;
        height: 2px !important;
        border-radius: 0 !important;
    }
    [data-testid="stProgress"] > div {
        background-color: #141414 !important;
        height: 2px !important;
        border-radius: 0 !important;
    }

    /* ═══════════════════════════════════════════════════
       DIVISORES — LINHA FINA
       ═══════════════════════════════════════════════════ */

    hr {
        border: none;
        border-top: 1px solid #111;
        margin: 10px 0;
    }

    /* ═══════════════════════════════════════════════════
       SCROLLBAR — QUASE INVISÍVEL
       ═══════════════════════════════════════════════════ */

    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #1e1e1e; border-radius: 0; }
    ::-webkit-scrollbar-thumb:hover { background: #FF9900; }

    /* ═══════════════════════════════════════════════════
       COLUNA / GRID — ESPAÇAMENTO REDUZIDO
       ═══════════════════════════════════════════════════ */

    /* Remove espaçamento extra entre colunas */
    [data-testid="column"] {
        padding-left: 4px !important;
        padding-right: 4px !important;
    }

    /* Reduz gap de st.columns */
    [data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
    }

    /* ═══════════════════════════════════════════════════
       PLOTLY / CHARTS — REMOVE BORDA PADRÃO
       ═══════════════════════════════════════════════════ */

    [data-testid="stPlotlyChart"] {
        border: 1px solid #141414;
        border-radius: 2px;
        overflow: hidden;
    }

    /* ═══════════════════════════════════════════════════
       TOOLTIPS E POPOVERS
       ═══════════════════════════════════════════════════ */

    [data-testid="stPopover"] [data-testid="stBaseButton-secondary"] {
        border: none !important;
        padding: 0 4px !important;
    }

    /* ═══════════════════════════════════════════════════
       RESPONSIVE MÍNIMO
       ═══════════════════════════════════════════════════ */

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        .metric-card .metric-value { font-size: 1rem !important; }
    }

    /* ═══════════════════════════════════════════════════
       TRANSIÇÕES — APENAS ONDE NECESSÁRIO
       ═══════════════════════════════════════════════════ */

    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-secondary"],
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
        transition: color 0.1s, background-color 0.1s, border-color 0.1s !important;
    }

    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
