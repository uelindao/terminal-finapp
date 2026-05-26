"""
utils/style.py — v4.0  Bloomberg/Eikon institutional theme.
Paleta de 4 camadas com variáveis CSS, contraste real, informação máxima por pixel.
"""
import streamlit as st


def aplicar_tema():
    """Injeta o CSS global do design system institucional."""
    css = """
    <style>

    /* ═══════════════════════════════════════════════════
       DESIGN TOKENS — 4-LAYER PALETTE
       ═══════════════════════════════════════════════════ */

    :root {
        --bg-base:     #0e1117;   /* fundo — cinza azulado escuro */
        --bg-surface:  #161b27;   /* cards — distinguível do fundo */
        --bg-elevated: #1e2433;   /* inputs, hover — contraste claro */
        --bg-overlay:  #252d40;   /* dropdowns */

        --border-dim:    #252d3d;
        --border-normal: #2e3850;
        --border-active: #FF9900;

        --text-primary:   #E8EAF6; /* branco levemente azulado */
        --text-secondary: #8892A4; /* cinza médio — legível */
        --text-muted:     #4A5568; /* cinza escuro */

        --accent:     #FF9900;
        --accent-dim: #2a1f00;

        --bull:     #00D97E;
        --bull-dim: #00261a;
        --bear:     #FF4560;
        --bear-dim: #2a0010;
        --amber:    #FFB800;
        --info:     #4DA6FF;
    }

    /* ═══════════════════════════════════════════════════
       RESET E LAYOUT BASE
       ═══════════════════════════════════════════════════ */

    body, .stApp {
        background-color: #0e1117 !important;
    }

    .block-container {
        padding-top: 0.75rem !important;
        padding-bottom: 1rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
    }

    /* Remove espaço em branco padrão do Streamlit */
    .main > div { padding-top: 0 !important; }
    [data-testid="stAppViewContainer"] { background-color: var(--bg-base); }
    [data-testid="stHeader"] { background: transparent; }

    /* ═══════════════════════════════════════════════════
       TIPOGRAFIA COMPACTA
       ═══════════════════════════════════════════════════ */

    .page-title {
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        font-weight: bold;
        color: var(--accent);
        text-transform: uppercase;
        letter-spacing: 0.14em;
        border-bottom: 1px solid var(--border-dim);
        padding-bottom: 5px;
        margin-bottom: 10px;
    }

    .section-title {
        font-family: 'Courier New', monospace;
        font-size: 0.68rem;
        font-weight: bold;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.14em;
        border-bottom: 1px solid var(--border-dim);
        padding-bottom: 3px;
        margin-bottom: 8px;
        margin-top: 14px;
    }

    .field-label {
        font-family: 'Courier New', monospace;
        font-size: 0.62rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.10em;
    }

    .body-text {
        font-family: 'Courier New', monospace;
        font-size: 0.78rem;
        color: var(--text-secondary);
        line-height: 1.5;
    }

    .stMarkdown p, .stMarkdown li {
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        color: var(--text-secondary);
        line-height: 1.5;
    }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: 'Courier New', monospace;
        color: var(--accent);
        letter-spacing: 0.06em;
    }
    .stMarkdown h5 {
        font-family: 'Courier New', monospace;
        font-size: 0.72rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-weight: bold;
        margin-bottom: 6px;
    }

    /* ═══════════════════════════════════════════════════
       CORES SEMÂNTICAS
       ═══════════════════════════════════════════════════ */

    .color-bull  { color: var(--bull)  !important; }
    .color-bear  { color: var(--bear)  !important; }
    .color-amber { color: var(--amber) !important; }
    .color-info  { color: var(--info)  !important; }
    .color-muted { color: var(--text-muted) !important; }

    .bg-bull  { background-color: var(--bull-dim);  border-left: 2px solid var(--bull); }
    .bg-bear  { background-color: var(--bear-dim);  border-left: 2px solid var(--bear); }
    .bg-amber { background-color: var(--accent-dim); border-left: 2px solid var(--amber); }
    .bg-info  { background-color: #001833;           border-left: 2px solid var(--info); }

    /* ═══════════════════════════════════════════════════
       CARDS — CANTOS RETOS, GRADIENTE SUTIL
       ═══════════════════════════════════════════════════ */

    .card {
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: 3px !important;
        padding: 8px 10px;
        margin-bottom: 6px;
    }

    .card-bull  { border-left: 2px solid var(--bull)  !important; }
    .card-bear  { border-left: 2px solid var(--bear)  !important; }
    .card-amber { border-left: 2px solid var(--amber) !important; }
    .card-info  { border-left: 2px solid var(--info)  !important; }

    .metric-card {
        background: linear-gradient(
            135deg,
            var(--bg-surface) 0%,
            var(--bg-elevated) 100%
        );
        border: 1px solid var(--border-normal);
        border-radius: 3px;
        padding: 7px 10px;
        text-align: left;
    }
    .metric-card .metric-label {
        font-family: 'Courier New', monospace;
        font-size: 0.60rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 2px;
    }
    .metric-card .metric-value {
        font-family: 'Courier New', monospace;
        font-size: 1.2rem;
        font-weight: bold;
        color: var(--text-primary);
        line-height: 1.15;
    }
    .metric-card .metric-delta {
        font-family: 'Courier New', monospace;
        font-size: 0.68rem;
        margin-top: 1px;
        color: var(--text-muted);
    }

    /* ═══════════════════════════════════════════════════
       BADGES — MICRO TAGS
       ═══════════════════════════════════════════════════ */

    .badge {
        display: inline-block;
        padding: 1px 5px;
        border-radius: 2px;
        font-family: 'Courier New', monospace;
        font-size: 0.60rem;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-bull  { background: var(--bull-dim);   color: var(--bull);  border: 1px solid var(--bull); }
    .badge-bear  { background: var(--bear-dim);   color: var(--bear);  border: 1px solid var(--bear); }
    .badge-amber { background: var(--accent-dim); color: var(--amber); border: 1px solid var(--amber); }
    .badge-info  { background: #001833;           color: var(--info);  border: 1px solid var(--info); }
    .badge-muted { background: var(--bg-elevated); color: var(--text-muted); border: 1px solid var(--border-normal); }

    /* ═══════════════════════════════════════════════════
       BOTÕES — 28 PX, RETANGULARES
       ═══════════════════════════════════════════════════ */

    [data-testid="stBaseButton-primary"] {
        background-color: var(--accent) !important;
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

    [data-testid="stBaseButton-secondary"] {
        background-color: transparent !important;
        color: var(--text-muted) !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.70rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: 2px !important;
        height: 28px !important;
        min-height: 28px !important;
        padding: 0 10px !important;
        line-height: 28px !important;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        border-color: var(--accent) !important;
        color: var(--accent) !important;
        background-color: var(--accent-dim) !important;
    }

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
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: 2px !important;
        color: var(--text-primary) !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.80rem !important;
        padding: 4px 8px !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: var(--border-active) !important;
        box-shadow: 0 0 0 1px rgba(255,153,0,0.20) !important;
    }

    [data-testid="stTextInput"] label,
    [data-testid="stNumberInput"] label,
    [data-testid="stSelectbox"] label,
    [data-testid="stMultiSelect"] label,
    [data-testid="stTextArea"] label,
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label {
        font-family: 'Courier New', monospace !important;
        font-size: 0.65rem !important;
        color: var(--text-muted) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
    }

    [data-testid="stSelectbox"] > div > div {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: 2px !important;
        color: var(--text-primary) !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.80rem !important;
        min-height: 30px !important;
    }

    [data-testid="stMultiSelect"] > div > div {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: 2px !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.78rem !important;
    }

    [data-testid="stRadio"] > div {
        gap: 4px !important;
    }
    [data-testid="stRadio"] label {
        font-size: 0.72rem !important;
        color: var(--text-secondary) !important;
        padding: 2px 6px !important;
        text-transform: none !important;
    }

    /* ═══════════════════════════════════════════════════
       TABELAS E DATAFRAMES
       ═══════════════════════════════════════════════════ */

    [data-testid="stDataFrame"] {
        border: 1px solid var(--border-normal);
        border-radius: 2px;
        overflow: hidden;
    }
    [data-testid="stDataFrame"] thead tr th {
        background-color: var(--bg-surface) !important;
        color: var(--accent) !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.62rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.09em !important;
        border-bottom: 1px solid var(--border-normal) !important;
        padding: 4px 8px !important;
    }
    [data-testid="stDataFrame"] tbody tr td {
        font-family: 'Courier New', monospace !important;
        font-size: 0.74rem !important;
        padding: 3px 8px !important;
        border-bottom: 1px solid var(--border-dim) !important;
    }
    [data-testid="stDataFrame"] tbody tr:nth-child(even) td {
        background-color: var(--bg-surface) !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover td {
        background-color: var(--bg-elevated) !important;
    }

    /* ═══════════════════════════════════════════════════
       SIDEBAR — MAIS ESCURA E COMPACTA
       ═══════════════════════════════════════════════════ */

    [data-testid="stSidebar"] {
        background-color: #111827 !important;
        border-right: 1px solid var(--border-normal) !important;
    }
    [data-testid="stSidebar"] > div {
        padding-top: 0.5rem;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
        font-family: 'Courier New', monospace;
        font-size: 0.72rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        padding: 5px 10px;
        border-radius: 2px;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {
        background-color: var(--bg-elevated);
        color: var(--accent);
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] [aria-current="page"] {
        background-color: var(--accent-dim);
        color: var(--accent) !important;
        border-left: 2px solid var(--accent);
        padding-left: 8px;
    }

    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] .stMarkdown p {
        font-size: 0.72rem !important;
        color: var(--text-muted) !important;
    }

    /* ═══════════════════════════════════════════════════
       ABAS (TABS) — PLANAS E COMPACTAS
       ═══════════════════════════════════════════════════ */

    [data-testid="stTabs"] [role="tablist"] {
        border-bottom: 1px solid var(--border-dim);
        gap: 1px;
        padding-bottom: 0;
    }
    [data-testid="stTabs"] [role="tab"] {
        font-family: 'Courier New', monospace !important;
        font-size: 0.65rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.10em !important;
        color: var(--text-muted) !important;
        padding: 5px 12px !important;
        border-radius: 0 !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        background: transparent !important;
    }
    [data-testid="stTabs"] [role="tab"]:hover {
        color: var(--text-secondary) !important;
        background-color: var(--bg-elevated) !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: var(--accent) !important;
        background-color: transparent !important;
        border-bottom: 2px solid var(--accent) !important;
    }

    [data-testid="stTabsContent"] {
        padding-top: 0.75rem !important;
    }

    /* ═══════════════════════════════════════════════════
       EXPANDERS
       ═══════════════════════════════════════════════════ */

    [data-testid="stExpander"] {
        border: 1px solid var(--border-dim) !important;
        border-radius: 2px !important;
        background-color: var(--bg-surface) !important;
        margin-bottom: 5px !important;
    }
    [data-testid="stExpander"] summary {
        font-family: 'Courier New', monospace !important;
        font-size: 0.70rem !important;
        color: var(--text-muted) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        padding: 7px 10px !important;
        min-height: 0 !important;
    }
    [data-testid="stExpander"] summary:hover {
        color: var(--accent) !important;
        background-color: var(--bg-elevated) !important;
    }

    /* ═══════════════════════════════════════════════════
       MÉTRICAS NATIVAS DO STREAMLIT
       ═══════════════════════════════════════════════════ */

    [data-testid="stMetric"] {
        background: linear-gradient(
            135deg,
            var(--bg-surface) 0%,
            var(--bg-elevated) 100%
        );
        border: 1px solid var(--border-normal);
        border-radius: 3px;
        padding: 6px 10px;
    }
    [data-testid="stMetricLabel"] {
        font-family: 'Courier New', monospace !important;
        font-size: 0.60rem !important;
        color: var(--text-muted) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.10em !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Courier New', monospace !important;
        font-size: 1.1rem !important;
        font-weight: bold !important;
        color: var(--text-primary) !important;
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
        background-color: var(--bull-dim) !important;
        border: 1px solid var(--bull) !important;
        color: var(--bull) !important;
    }
    [data-testid="stError"] {
        background-color: var(--bear-dim) !important;
        border: 1px solid var(--bear) !important;
        color: var(--bear) !important;
    }
    [data-testid="stWarning"] {
        background-color: var(--accent-dim) !important;
        border: 1px solid var(--amber) !important;
        color: var(--amber) !important;
    }
    [data-testid="stInfo"] {
        background-color: #001833 !important;
        border: 1px solid var(--info) !important;
        color: var(--info) !important;
    }

    /* ═══════════════════════════════════════════════════
       CHAT / MENSAGENS IA
       ═══════════════════════════════════════════════════ */

    [data-testid="stChatMessage"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-dim) !important;
        border-radius: 2px !important;
        padding: 8px 12px !important;
        margin-bottom: 4px !important;
    }
    [data-testid="stChatInput"] textarea {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: 2px !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.78rem !important;
        color: var(--text-primary) !important;
    }

    /* ═══════════════════════════════════════════════════
       SPINNER / PROGRESS
       ═══════════════════════════════════════════════════ */

    [data-testid="stSpinner"] {
        font-family: 'Courier New', monospace !important;
        font-size: 0.72rem !important;
        color: var(--text-muted) !important;
    }
    [data-testid="stProgress"] > div > div {
        background-color: var(--accent) !important;
        height: 2px !important;
        border-radius: 0 !important;
    }
    [data-testid="stProgress"] > div {
        background-color: var(--bg-elevated) !important;
        height: 2px !important;
        border-radius: 0 !important;
    }

    /* ═══════════════════════════════════════════════════
       DIVISORES — GRADIENTE
       ═══════════════════════════════════════════════════ */

    hr {
        border: none !important;
        height: 1px !important;
        background: linear-gradient(
            90deg,
            transparent,
            var(--border-normal),
            transparent
        ) !important;
        margin: 8px 0 !important;
    }

    /* ═══════════════════════════════════════════════════
       SCROLLBAR — QUASE INVISÍVEL
       ═══════════════════════════════════════════════════ */

    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border-normal); border-radius: 0; }
    ::-webkit-scrollbar-thumb:hover { background: var(--accent); }

    /* ═══════════════════════════════════════════════════
       COLUNA / GRID — ESPAÇAMENTO REDUZIDO
       ═══════════════════════════════════════════════════ */

    [data-testid="column"] {
        padding-left: 4px !important;
        padding-right: 4px !important;
    }

    [data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
    }

    /* ═══════════════════════════════════════════════════
       PLOTLY / CHARTS
       ═══════════════════════════════════════════════════ */

    [data-testid="stPlotlyChart"] {
        border: 1px solid var(--border-dim);
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
