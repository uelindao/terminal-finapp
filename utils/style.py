"""
utils/style.py — v5.0  Design system moderno.
Paleta azul-escuro com profundidade real, Inter + Courier New,
border-radius generoso, laranja como acento preciso.
Referências: Virtus, Metric Flow, Plutio dark mode.
"""
import streamlit as st


def aplicar_tema():
    """Injeta o CSS global do design system."""
    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ═══════════════════════════════════════════════════
       VARIÁVEIS GLOBAIS
       ═══════════════════════════════════════════════════ */

    :root {
        --bg-base:       #13141E;
        --bg-surface:    #1C1D2B;
        --bg-elevated:   #23243A;
        --bg-overlay:    #2C2D45;

        --border-subtle: #2A2C3E;
        --border-normal: #353755;
        --border-focus:  #FF8C00;

        --text-primary:   #F0F2FF;
        --text-secondary: #9CA3B8;
        --text-muted:     #6B7280;

        --accent:        #FF8C00;
        --accent-hover:  #FF6B00;
        --accent-soft:   rgba(255,140,0,0.08);
        --accent-border: rgba(255,140,0,0.25);

        --bull:      #10B981;
        --bull-soft: rgba(16,185,129,0.10);
        --bear:      #EF4444;
        --bear-soft: rgba(239,68,68,0.10);
        --amber:     #F59E0B;
        --info:      #3B82F6;

        --radius-sm: 6px;
        --radius-md: 10px;
        --radius-lg: 14px;

        --font-ui:   'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
        --font-data: 'Courier New', 'Consolas', monospace;
    }

    /* ═══════════════════════════════════════════════════
       BASE
       ═══════════════════════════════════════════════════ */

    html, body, .stApp {
        background-color: var(--bg-base) !important;
        color: var(--text-primary) !important;
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
    }

    [data-testid="stAppViewContainer"] {
        background-color: var(--bg-base) !important;
    }
    [data-testid="stHeader"] {
        background: transparent !important;
    }
    .main > div {
        padding-top: 0 !important;
    }

    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 1.8rem !important;
        padding-right: 1.8rem !important;
        max-width: 100% !important;
    }

    /* ═══════════════════════════════════════════════════
       TIPOGRAFIA
       ═══════════════════════════════════════════════════ */

    .page-title {
        font-family: var(--font-ui);
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: -0.01em;
        margin-bottom: 4px;
    }

    .section-title {
        font-family: var(--font-ui);
        font-size: 0.68rem;
        font-weight: 600;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        padding-bottom: 8px;
        margin-bottom: 10px;
        margin-top: 16px;
        border-bottom: 1px solid var(--border-subtle);
    }

    .field-label {
        font-family: var(--font-ui);
        font-size: 0.70rem;
        font-weight: 500;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }

    .body-text {
        font-family: var(--font-ui);
        font-size: 0.85rem;
        color: var(--text-secondary);
        line-height: 1.6;
    }

    /* Markdown do Streamlit */
    .stMarkdown p, .stMarkdown li {
        font-family: var(--font-ui) !important;
        font-size: 0.85rem !important;
        color: var(--text-secondary) !important;
        line-height: 1.6 !important;
    }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: var(--font-ui) !important;
        color: var(--text-primary) !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
    }
    .stMarkdown h5 {
        font-family: var(--font-ui) !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        color: var(--text-muted) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
    }
    .stMarkdown code {
        font-family: var(--font-data) !important;
        font-size: 0.80rem !important;
        background: var(--bg-elevated) !important;
        padding: 1px 5px !important;
        border-radius: 4px !important;
        color: var(--accent) !important;
    }

    /* ═══════════════════════════════════════════════════
       CORES SEMÂNTICAS
       ═══════════════════════════════════════════════════ */

    .color-bull  { color: var(--bull)  !important; }
    .color-bear  { color: var(--bear)  !important; }
    .color-amber { color: var(--amber) !important; }
    .color-info  { color: var(--info)  !important; }
    .color-muted { color: var(--text-muted) !important; }

    .bg-bull  { background: var(--bull-soft);  border-left: 3px solid var(--bull); }
    .bg-bear  { background: var(--bear-soft);  border-left: 3px solid var(--bear); }
    .bg-amber { background: rgba(245,158,11,0.10); border-left: 3px solid var(--amber); }
    .bg-info  { background: rgba(59,130,246,0.10); border-left: 3px solid var(--info); }

    /* ═══════════════════════════════════════════════════
       CARDS
       ═══════════════════════════════════════════════════ */

    .card {
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: var(--radius-md) !important;
        padding: 14px 16px !important;
        margin-bottom: 8px !important;
        transition: border-color 0.15s ease !important;
    }
    .card:hover {
        border-color: var(--border-normal) !important;
    }
    .card-bull  { border-left: 3px solid var(--bull)  !important; }
    .card-bear  { border-left: 3px solid var(--bear)  !important; }
    .card-amber { border-left: 3px solid var(--amber) !important; }
    .card-info  { border-left: 3px solid var(--info)  !important; }

    /* Metric card */
    .metric-card {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        padding: 14px 16px;
        transition: all 0.15s ease;
    }
    .metric-card:hover {
        border-color: var(--border-normal);
        transform: translateY(-1px);
    }
    .metric-card .metric-label {
        font-family: var(--font-ui);
        font-size: 0.68rem;
        font-weight: 500;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.07em;
        margin-bottom: 6px;
    }
    .metric-card .metric-value {
        font-family: var(--font-data);
        font-size: 1.35rem;
        font-weight: bold;
        color: var(--text-primary);
        line-height: 1.15;
    }
    .metric-card .metric-delta {
        font-family: var(--font-ui);
        font-size: 0.72rem;
        color: var(--text-muted);
        margin-top: 4px;
        font-weight: 500;
    }

    /* ═══════════════════════════════════════════════════
       BADGES
       ═══════════════════════════════════════════════════ */

    .badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 2px 8px;
        border-radius: 20px;
        font-family: var(--font-ui);
        font-size: 0.62rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-bull  { background: var(--bull-soft);         color: var(--bull);  border: 1px solid rgba(16,185,129,0.2); }
    .badge-bear  { background: var(--bear-soft);         color: var(--bear);  border: 1px solid rgba(239,68,68,0.2); }
    .badge-amber { background: rgba(245,158,11,0.10);    color: var(--amber); border: 1px solid rgba(245,158,11,0.2); }
    .badge-info  { background: rgba(59,130,246,0.10);    color: var(--info);  border: 1px solid rgba(59,130,246,0.2); }
    .badge-muted { background: rgba(74,77,106,0.15);     color: var(--text-muted); border: 1px solid var(--border-subtle); }

    /* ═══════════════════════════════════════════════════
       BOTÕES
       ═══════════════════════════════════════════════════ */

    /* Primário */
    [data-testid="stBaseButton-primary"] {
        background: var(--accent) !important;
        color: #000 !important;
        font-family: var(--font-ui) !important;
        font-size: 0.75rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.03em !important;
        border: none !important;
        border-radius: var(--radius-sm) !important;
        height: 34px !important;
        min-height: 34px !important;
        padding: 0 16px !important;
        transition: all 0.15s ease !important;
        box-shadow: 0 2px 8px rgba(255,140,0,0.25) !important;
    }
    [data-testid="stBaseButton-primary"]:hover {
        background: var(--accent-hover) !important;
        box-shadow: 0 4px 12px rgba(255,140,0,0.35) !important;
        transform: translateY(-1px) !important;
    }

    /* Secundário */
    [data-testid="stBaseButton-secondary"] {
        background: var(--bg-elevated) !important;
        color: var(--text-secondary) !important;
        font-family: var(--font-ui) !important;
        font-size: 0.75rem !important;
        font-weight: 500 !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: var(--radius-sm) !important;
        height: 34px !important;
        min-height: 34px !important;
        padding: 0 14px !important;
        transition: all 0.15s ease !important;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        background: var(--bg-overlay) !important;
        color: var(--text-primary) !important;
        border-color: var(--border-focus) !important;
    }

    /* Texto dos botões */
    [data-testid="stBaseButton-primary"] p,
    [data-testid="stBaseButton-secondary"] p {
        font-size: 0.75rem !important;
        font-family: var(--font-ui) !important;
        margin: 0 !important;
        line-height: 34px !important;
    }

    /* ═══════════════════════════════════════════════════
       INPUTS
       ═══════════════════════════════════════════════════ */

    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-data) !important;
        font-size: 0.85rem !important;
        height: 36px !important;
        padding: 0 12px !important;
        transition: border-color 0.15s ease !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus {
        border-color: var(--border-focus) !important;
        box-shadow: 0 0 0 3px rgba(255,140,0,0.12) !important;
        outline: none !important;
    }
    [data-testid="stTextArea"] textarea {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-data) !important;
        font-size: 0.82rem !important;
        padding: 8px 12px !important;
    }
    [data-testid="stTextArea"] textarea:focus {
        border-color: var(--border-focus) !important;
        box-shadow: 0 0 0 3px rgba(255,140,0,0.12) !important;
    }

    /* Labels dos campos */
    [data-testid="stTextInput"] label,
    [data-testid="stNumberInput"] label,
    [data-testid="stSelectbox"] label,
    [data-testid="stMultiSelect"] label,
    [data-testid="stTextArea"] label,
    [data-testid="stSlider"] label,
    [data-testid="stRadio"] > label,
    [data-testid="stCheckbox"] > label {
        font-family: var(--font-ui) !important;
        font-size: 0.70rem !important;
        font-weight: 500 !important;
        color: var(--text-secondary) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        margin-bottom: 4px !important;
    }

    /* Selectbox */
    [data-testid="stSelectbox"] > div > div {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-ui) !important;
        font-size: 0.85rem !important;
        min-height: 36px !important;
        transition: border-color 0.15s !important;
    }
    [data-testid="stSelectbox"] > div > div:hover {
        border-color: var(--border-focus) !important;
    }

    /* Multiselect */
    [data-testid="stMultiSelect"] > div > div {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: var(--radius-sm) !important;
        font-family: var(--font-ui) !important;
        font-size: 0.82rem !important;
    }

    /* Number input step buttons */
    [data-testid="stNumberInput"] button {
        background: var(--bg-overlay) !important;
        border-color: var(--border-normal) !important;
        color: var(--text-secondary) !important;
        border-radius: 4px !important;
    }

    /* Radio */
    [data-testid="stRadio"] label p,
    [data-testid="stCheckbox"] label p {
        font-family: var(--font-ui) !important;
        font-size: 0.80rem !important;
        color: var(--text-secondary) !important;
    }
    [data-testid="stRadio"] > div {
        gap: 6px !important;
    }

    /* ═══════════════════════════════════════════════════
       TABS
       ═══════════════════════════════════════════════════ */

    [data-testid="stTabs"] [role="tablist"] {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        padding: 4px;
        gap: 2px;
        display: inline-flex;
        margin-bottom: 4px;
    }
    [data-testid="stTabs"] [role="tab"] {
        font-family: var(--font-ui) !important;
        font-size: 0.72rem !important;
        font-weight: 500 !important;
        color: var(--text-muted) !important;
        padding: 6px 14px !important;
        border-radius: var(--radius-sm) !important;
        border: none !important;
        background: transparent !important;
        transition: all 0.15s ease !important;
        letter-spacing: 0.02em !important;
    }
    [data-testid="stTabs"] [role="tab"]:hover {
        color: var(--text-secondary) !important;
        background: var(--bg-elevated) !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: var(--text-primary) !important;
        background: var(--bg-elevated) !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.35) !important;
    }
    [data-testid="stTabsContent"] {
        padding-top: 1rem !important;
    }

    /* ═══════════════════════════════════════════════════
       SIDEBAR
       ═══════════════════════════════════════════════════ */

    /* ─── SIDEBAR ─────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: #0B0C15 !important;
        border-right: 1px solid var(--border-subtle) !important;
        min-width: 200px !important;
        max-width: 220px !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding: 0 !important;
    }
    /* Logo */
    [data-testid="stSidebar"] > div:first-child::before {
        content: "⚡  FINTERMINAL";
        display: block;
        font-family: var(--font-ui);
        font-size: 0.66rem;
        font-weight: 700;
        color: var(--accent);
        letter-spacing: 0.20em;
        text-transform: uppercase;
        padding: 16px 16px 12px;
        border-bottom: 1px solid var(--border-subtle);
        margin-bottom: 4px;
    }
    /* Nav container */
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] {
        padding: 6px 0 !important;
    }
    /* Nav links */
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
        font-family: var(--font-ui) !important;
        font-size: 0.80rem !important;
        font-weight: 500 !important;
        color: var(--text-secondary) !important;
        padding: 8px 14px !important;
        margin: 1px 8px !important;
        border-radius: 6px !important;
        display: block !important;
        transition: all 0.12s ease !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {
        color: var(--text-primary) !important;
        background: var(--bg-elevated) !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] [aria-current="page"] {
        background: var(--accent-soft) !important;
        color: var(--accent) !important;
        border: 1px solid var(--accent-border) !important;
        font-weight: 600 !important;
    }
    /* Área de conteúdo abaixo da nav */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        padding: 0 8px !important;
    }
    /* Texto geral */
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] .stMarkdown p {
        font-family: var(--font-ui) !important;
        font-size: 0.75rem !important;
        color: var(--text-muted) !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    /* Expanders */
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        margin: 4px 0 !important;
        border-radius: 6px !important;
        border: 1px solid var(--border-subtle) !important;
        background: var(--bg-surface) !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        font-family: var(--font-ui) !important;
        font-size: 0.75rem !important;
        font-weight: 500 !important;
        color: var(--text-secondary) !important;
        padding: 7px 10px !important;
        white-space: nowrap !important;
    }
    /* Inputs dentro dos expanders */
    [data-testid="stSidebar"] [data-testid="stExpander"]
        [data-testid="stTextInput"] {
        width: 100% !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"]
        [data-testid="stTextInput"] input {
        width: 100% !important;
        font-size: 0.75rem !important;
        height: 30px !important;
        min-width: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"]
        [data-testid="stTextInput"] label {
        font-size: 0.65rem !important;
    }
    /* Botões dentro dos expanders */
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
    [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
        height: 28px !important;
        min-height: 28px !important;
        font-size: 0.70rem !important;
        width: 100% !important;
        padding: 0 8px !important;
    }
    /* Colunas dentro dos expanders — empilha para caber na sidebar */
    [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 4px !important;
    }
    [data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
        [data-testid="stVerticalBlock"] {
        width: 100% !important;
        min-width: 0 !important;
        flex: none !important;
    }

    /* ═══════════════════════════════════════════════════
       DATAFRAMES
       ═══════════════════════════════════════════════════ */

    [data-testid="stDataFrame"] {
        border: 1px solid var(--border-subtle) !important;
        border-radius: var(--radius-md) !important;
        overflow: hidden !important;
    }
    [data-testid="stDataFrame"] thead tr th {
        background: var(--bg-elevated) !important;
        color: var(--text-muted) !important;
        font-family: var(--font-ui) !important;
        font-size: 0.65rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        padding: 8px 12px !important;
        border-bottom: 1px solid var(--border-normal) !important;
    }
    [data-testid="stDataFrame"] tbody tr td {
        font-family: var(--font-data) !important;
        font-size: 0.80rem !important;
        color: var(--text-secondary) !important;
        padding: 6px 12px !important;
        border-bottom: 1px solid var(--border-subtle) !important;
    }
    [data-testid="stDataFrame"] tbody tr:nth-child(even) td {
        background: var(--bg-surface) !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover td {
        background: var(--bg-elevated) !important;
        color: var(--text-primary) !important;
    }

    /* ═══════════════════════════════════════════════════
       EXPANDERS
       ═══════════════════════════════════════════════════ */

    [data-testid="stExpander"] {
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: var(--radius-md) !important;
        margin-bottom: 8px !important;
        overflow: hidden !important;
    }
    [data-testid="stExpander"] summary {
        font-family: var(--font-ui) !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        color: var(--text-secondary) !important;
        padding: 10px 14px !important;
        background: var(--bg-elevated) !important;
        transition: all 0.15s ease !important;
    }
    [data-testid="stExpander"] summary:hover {
        color: var(--text-primary) !important;
        background: var(--bg-overlay) !important;
    }

    /* ═══════════════════════════════════════════════════
       MÉTRICAS NATIVAS
       ═══════════════════════════════════════════════════ */

    [data-testid="stMetric"] {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        padding: 14px 16px !important;
        transition: border-color 0.15s;
    }
    [data-testid="stMetric"]:hover {
        border-color: var(--border-normal);
    }
    [data-testid="stMetricLabel"] p {
        font-family: var(--font-ui) !important;
        font-size: 0.68rem !important;
        font-weight: 600 !important;
        color: var(--text-muted) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.07em !important;
    }
    [data-testid="stMetricValue"] {
        font-family: var(--font-data) !important;
        font-size: 1.4rem !important;
        color: var(--text-primary) !important;
    }
    [data-testid="stMetricDelta"] {
        font-family: var(--font-ui) !important;
        font-size: 0.72rem !important;
        font-weight: 500 !important;
    }

    /* ═══════════════════════════════════════════════════
       ALERTAS NATIVOS
       ═══════════════════════════════════════════════════ */

    [data-testid="stAlert"] {
        border-radius: var(--radius-md) !important;
        font-family: var(--font-ui) !important;
        font-size: 0.80rem !important;
        padding: 10px 14px !important;
    }
    [data-testid="stSuccess"] {
        background: var(--bull-soft) !important;
        border: 1px solid rgba(16,185,129,0.25) !important;
        color: var(--bull) !important;
    }
    [data-testid="stError"] {
        background: var(--bear-soft) !important;
        border: 1px solid rgba(239,68,68,0.25) !important;
        color: var(--bear) !important;
    }
    [data-testid="stWarning"] {
        background: rgba(245,158,11,0.10) !important;
        border: 1px solid rgba(245,158,11,0.25) !important;
        color: var(--amber) !important;
    }
    [data-testid="stInfo"] {
        background: rgba(59,130,246,0.10) !important;
        border: 1px solid rgba(59,130,246,0.25) !important;
        color: var(--info) !important;
    }

    /* ═══════════════════════════════════════════════════
       CHAT
       ═══════════════════════════════════════════════════ */

    [data-testid="stChatMessage"] {
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: var(--radius-md) !important;
        padding: 10px 14px !important;
        margin-bottom: 6px !important;
    }
    [data-testid="stChatInput"] {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: var(--radius-md) !important;
    }
    [data-testid="stChatInput"] textarea {
        font-family: var(--font-ui) !important;
        font-size: 0.85rem !important;
        color: var(--text-primary) !important;
    }

    /* ═══════════════════════════════════════════════════
       SPINNER / PROGRESS
       ═══════════════════════════════════════════════════ */

    [data-testid="stSpinner"] p {
        font-family: var(--font-ui) !important;
        font-size: 0.75rem !important;
        color: var(--text-muted) !important;
    }
    [data-testid="stProgress"] > div > div {
        background: var(--accent) !important;
        height: 3px !important;
        border-radius: var(--radius-sm) !important;
    }
    [data-testid="stProgress"] > div {
        background: var(--bg-elevated) !important;
        height: 3px !important;
        border-radius: var(--radius-sm) !important;
    }

    /* ═══════════════════════════════════════════════════
       DOWNLOAD BUTTON
       ═══════════════════════════════════════════════════ */

    [data-testid="stDownloadButton"] button {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border-normal) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text-secondary) !important;
        font-family: var(--font-ui) !important;
        font-size: 0.72rem !important;
        font-weight: 500 !important;
        height: 34px !important;
    }
    [data-testid="stDownloadButton"] button:hover {
        border-color: var(--accent) !important;
        color: var(--accent) !important;
    }

    /* ═══════════════════════════════════════════════════
       PLOTLY CHARTS
       ═══════════════════════════════════════════════════ */

    [data-testid="stPlotlyChart"] {
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        overflow: hidden;
    }

    /* ═══════════════════════════════════════════════════
       SCROLLBAR
       ═══════════════════════════════════════════════════ */

    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: var(--bg-base); }
    ::-webkit-scrollbar-thumb {
        background: var(--border-normal);
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: var(--accent);
    }

    /* ═══════════════════════════════════════════════════
       DIVIDER
       ═══════════════════════════════════════════════════ */

    hr {
        border: none !important;
        height: 1px !important;
        background: var(--border-subtle) !important;
        margin: 12px 0 !important;
    }

    /* ═══════════════════════════════════════════════════
       GRID / COLUNAS
       ═══════════════════════════════════════════════════ */

    [data-testid="column"] {
        padding-left: 6px !important;
        padding-right: 6px !important;
    }
    [data-testid="stHorizontalBlock"] {
        gap: 0.6rem !important;
    }

    /* ═══════════════════════════════════════════════════
       OCULTAR DECORAÇÕES STREAMLIT
       ═══════════════════════════════════════════════════ */

    footer { display: none !important; }
    #MainMenu { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }

    /* ═══════════════════════════════════════════════════
       TRANSITIONS — SELETIVO
       ═══════════════════════════════════════════════════ */

    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-secondary"],
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
        transition: all 0.15s ease !important;
    }

    /* ═══════════════════════════════════════════════════
       MOBILE
       ═══════════════════════════════════════════════════ */

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
        }
        .metric-card .metric-value {
            font-size: 1.1rem !important;
        }
    }

    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
