"""
utils/style.py — v2.0
Design System completo do terminal.
"""
import streamlit as st

def aplicar_tema():
    """Injeta o CSS global na aplicação."""
    css = """
    <style>
    /* ═══════════════════════════════════════════════════
       TIPOGRAFIA — HIERARQUIA DE 3 NÍVEIS
       ═══════════════════════════════════════════════════ */

    /* Nível 1: Título de página */
    .page-title {
        font-family: 'Courier New', monospace;
        font-size: 1.6rem;
        font-weight: bold;
        color: #FF9900;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        border-bottom: 2px solid #FF9900;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }

    /* Nível 2: Título de seção */
    .section-title {
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        font-weight: bold;
        color: #FF9900;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        border-bottom: 1px solid #2a2a2a;
        padding-bottom: 4px;
        margin-bottom: 12px;
        margin-top: 20px;
    }

    /* Nível 3: Label de campo */
    .field-label {
        font-family: 'Courier New', monospace;
        font-size: 0.72rem;
        color: #555555;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    /* Corpo de texto analítico */
    .body-text {
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        color: #C0C0C0;
        line-height: 1.6;
    }

    /* ═══════════════════════════════════════════════════
       SISTEMA DE CORES SEMÂNTICAS
       ═══════════════════════════════════════════════════ */

    /* Positivo / Alta / Lucro */
    .color-bull   { color: #00C853 !important; }
    .bg-bull      { background-color: #001a0d; border-left: 3px solid #00C853; }

    /* Negativo / Baixa / Prejuízo */
    .color-bear   { color: #FF1744 !important; }
    .bg-bear      { background-color: #1a0005; border-left: 3px solid #FF1744; }

    /* Neutro / Alerta / Atenção */
    .color-amber  { color: #FF9900 !important; }
    .bg-amber     { background-color: #1a0f00; border-left: 3px solid #FF9900; }

    /* Informação / Destaque técnico */
    .color-info   { color: #00B0FF !important; }
    .bg-info      { background-color: #00111a; border-left: 3px solid #00B0FF; }

    /* Desabilitado / Histórico / Secundário */
    .color-muted  { color: #555555 !important; }

    /* ═══════════════════════════════════════════════════
       CARDS — SISTEMA DE CONTAINERS
       ═══════════════════════════════════════════════════ */

    /* Card padrão */
    .card {
        background-color: #0d0d0d;
        border: 1px solid #1e1e1e;
        border-radius: 6px;
        padding: 16px;
        margin-bottom: 12px;
    }

    /* Card com destaque lateral (status) */
    .card-bull  { border-left: 3px solid #00C853; }
    .card-bear  { border-left: 3px solid #FF1744; }
    .card-amber { border-left: 3px solid #FF9900; }
    .card-info  { border-left: 3px solid #00B0FF; }

    /* Card de métrica grande */
    .metric-card {
        background-color: #0d0d0d;
        border: 1px solid #1e1e1e;
        border-radius: 6px;
        padding: 12px 16px;
        text-align: center;
    }
    .metric-card .metric-label {
        font-family: 'Courier New', monospace;
        font-size: 0.68rem;
        color: #555;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }
    .metric-card .metric-value {
        font-family: 'Courier New', monospace;
        font-size: 1.5rem;
        font-weight: bold;
        color: #FFFFFF;
        line-height: 1.2;
    }
    .metric-card .metric-delta {
        font-family: 'Courier New', monospace;
        font-size: 0.78rem;
        margin-top: 2px;
    }

    /* ═══════════════════════════════════════════════════
       BADGES E TAGS
       ═══════════════════════════════════════════════════ */

    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 3px;
        font-family: 'Courier New', monospace;
        font-size: 0.68rem;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-bull   { background: #001a0d; color: #00C853; border: 1px solid #00C853; }
    .badge-bear   { background: #1a0005; color: #FF1744; border: 1px solid #FF1744; }
    .badge-amber  { background: #1a0f00; color: #FF9900; border: 1px solid #FF9900; }
    .badge-info   { background: #00111a; color: #00B0FF; border: 1px solid #00B0FF; }
    .badge-muted  { background: #111;    color: #555555; border: 1px solid #333; }

    /* ═══════════════════════════════════════════════════
       TABELAS E DATAFRAMES
       ═══════════════════════════════════════════════════ */

    [data-testid="stDataFrame"] {
        border: 1px solid #1e1e1e;
        border-radius: 6px;
        overflow: hidden;
    }
    [data-testid="stDataFrame"] thead tr th {
        background-color: #111111 !important;
        color: #FF9900 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        border-bottom: 1px solid #2a2a2a !important;
    }
    [data-testid="stDataFrame"] tbody tr:nth-child(even) td {
        background-color: #0a0a0a !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover td {
        background-color: #141414 !important;
    }

    /* ═══════════════════════════════════════════════════
       BOTÕES
       ═══════════════════════════════════════════════════ */

    /* Botão primário — ação principal */
    [data-testid="stBaseButton-primary"] {
        background-color: #FF9900 !important;
        color: #000000 !important;
        font-family: 'Courier New', monospace !important;
        font-weight: bold !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        border: none !important;
        border-radius: 4px !important;
        transition: opacity 0.15s ease !important;
    }
    [data-testid="stBaseButton-primary"]:hover {
        opacity: 0.85 !important;
    }

    /* Botão secundário — ação secundária */
    [data-testid="stBaseButton-secondary"] {
        background-color: transparent !important;
        color: #888888 !important;
        font-family: 'Courier New', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        border: 1px solid #333333 !important;
        border-radius: 4px !important;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        border-color: #FF9900 !important;
        color: #FF9900 !important;
    }

    /* ═══════════════════════════════════════════════════
       INPUTS E SELECTBOXES
       ═══════════════════════════════════════════════════ */

    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {
        background-color: #0d0d0d !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 4px !important;
        color: #E0E0E0 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.9rem !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus {
        border-color: #FF9900 !important;
        box-shadow: 0 0 0 1px rgba(255, 153, 0, 0.3) !important;
    }

    /* Selectbox */
    [data-testid="stSelectbox"] > div > div {
        background-color: #0d0d0d !important;
        border-color: #2a2a2a !important;
        color: #E0E0E0 !important;
        font-family: 'Courier New', monospace !important;
    }

    /* ═══════════════════════════════════════════════════
       SIDEBAR
       ═══════════════════════════════════════════════════ */

    [data-testid="stSidebar"] {
        background-color: #050505;
        border-right: 1px solid #1e1e1e;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        color: #888888;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding: 6px 12px;
        border-radius: 4px;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {
        background-color: #111111;
        color: #FF9900;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] [aria-current="page"] {
        background-color: #1a0f00;
        color: #FF9900 !important;
        border-left: 3px solid #FF9900;
    }

    /* ═══════════════════════════════════════════════════
       ABAS (TABS)
       ═══════════════════════════════════════════════════ */

    [data-testid="stTabs"] [role="tablist"] {
        border-bottom: 1px solid #1e1e1e;
        gap: 4px;
    }
    [data-testid="stTabs"] [role="tab"] {
        font-family: 'Courier New', monospace !important;
        font-size: 0.78rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        color: #555555 !important;
        padding: 8px 16px !important;
        border-radius: 4px 4px 0 0 !important;
        border: 1px solid transparent !important;
        transition: all 0.15s ease !important;
    }
    [data-testid="stTabs"] [role="tab"]:hover {
        color: #888888 !important;
        background-color: #0d0d0d !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: #FF9900 !important;
        background-color: #1a0f00 !important;
        border-color: #2a2a2a !important;
        border-bottom-color: #1a0f00 !important;
    }

    /* ═══════════════════════════════════════════════════
       EXPANDERS
       ═══════════════════════════════════════════════════ */

    [data-testid="stExpander"] {
        border: 1px solid #1e1e1e !important;
        border-radius: 6px !important;
        background-color: #0a0a0a !important;
        margin-bottom: 8px !important;
    }
    [data-testid="stExpander"] summary {
        font-family: 'Courier New', monospace !important;
        font-size: 0.82rem !important;
        color: #888888 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        padding: 12px 16px !important;
    }
    [data-testid="stExpander"] summary:hover {
        color: #FF9900 !important;
    }

    /* ═══════════════════════════════════════════════════
       DIVISORES E ESPAÇAMENTO
       ═══════════════════════════════════════════════════ */

    hr {
        border: none;
        border-top: 1px solid #1e1e1e;
        margin: 20px 0;
    }

    /* Reduz padding lateral em mobile */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
    }

    /* ═══════════════════════════════════════════════════
       SCROLLBAR CUSTOMIZADA
       ═══════════════════════════════════════════════════ */

    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #050505; }
    ::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #FF9900; }

    /* ═══════════════════════════════════════════════════
       ANIMAÇÕES SUAVES
       ═══════════════════════════════════════════════════ */

    .stApp * {
        transition: color 0.1s ease, background-color 0.1s ease,
                    border-color 0.1s ease, opacity 0.1s ease;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)