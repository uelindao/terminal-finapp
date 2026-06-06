"""
utils/themes.py — v2.0
Sistema de temas visuais do Finterminal.

Cada tema define paleta de cores completa, par tipográfico e personalidade visual.
O tema ativo persiste via st.query_params["theme"] + st.session_state["_theme"].
"""

import streamlit as st

_GF = "https://fonts.googleapis.com/css2?"

# ══════════════════════════════════════════════════════════════════════════════
# TEMAS
# ══════════════════════════════════════════════════════════════════════════════

TEMAS: dict[str, dict] = {

    # ── 1. Dark Terminal — Inter + JetBrains Mono ─────────────────────────────
    "dark": {
        "nome":  "Dark Terminal",
        "emoji": "🖤",
        "desc":  "azul-escuro clássico · acento laranja",
        "sidebar": "#0B0C15",
        "font_import": (
            f"@import url('{_GF}family=Inter:wght@300;400;500;600;700"
            "&family=JetBrains+Mono:wght@400;500;600&display=swap');"
        ),
        "vars": {
            "--sidebar-bg":     "#0B0C15",
            "--bg-base":        "#13141E",
            "--bg-surface":     "#1C1D2B",
            "--bg-elevated":    "#23243A",
            "--bg-overlay":     "#2C2D45",
            "--border-subtle":  "#2A2C3E",
            "--border-normal":  "#353755",
            "--border-focus":   "#FF8C00",
            "--text-primary":   "#F0F2FF",
            "--text-secondary": "#9CA3B8",
            "--text-muted":     "#6B7280",
            "--accent":         "#FF8C00",
            "--accent-rgb":     "255,140,0",
            "--accent-hover":   "#FF6B00",
            "--accent-soft":    "rgba(255,140,0,0.08)",
            "--accent-border":  "rgba(255,140,0,0.25)",
            "--bull":           "#10B981",
            "--bull-soft":      "rgba(16,185,129,0.10)",
            "--bear":           "#EF4444",
            "--bear-soft":      "rgba(239,68,68,0.10)",
            "--amber":          "#F59E0B",
            "--info":           "#3B82F6",
            "--radius-sm":      "6px",
            "--radius-md":      "10px",
            "--radius-lg":      "14px",
            "--font-ui":        "'Inter', system-ui, -apple-system, sans-serif",
            "--font-data":      "'JetBrains Mono', 'Consolas', monospace",
        },
    },

    # ── 2. Bloomberg — IBM Plex Sans + IBM Plex Mono ──────────────────────────
    "navy": {
        "nome":  "Bloomberg",
        "emoji": "🔵",
        "desc":  "navy profundo · IBM Plex · laranja vivo",
        "sidebar": "#060A13",
        "font_import": (
            f"@import url('{_GF}family=IBM+Plex+Sans:wght@300;400;500;600;700"
            "&family=IBM+Plex+Mono:wght@400;500&display=swap');"
        ),
        "vars": {
            "--sidebar-bg":     "#060A13",
            "--bg-base":        "#0A0E1A",
            "--bg-surface":     "#111827",
            "--bg-elevated":    "#1A2035",
            "--bg-overlay":     "#1E2A45",
            "--border-subtle":  "#1E2A45",
            "--border-normal":  "#2A3850",
            "--border-focus":   "#F97316",
            "--text-primary":   "#E8F4FD",
            "--text-secondary": "#94A3B8",
            "--text-muted":     "#64748B",
            "--accent":         "#F97316",
            "--accent-rgb":     "249,115,22",
            "--accent-hover":   "#EA6A00",
            "--accent-soft":    "rgba(249,115,22,0.08)",
            "--accent-border":  "rgba(249,115,22,0.28)",
            "--bull":           "#22C55E",
            "--bull-soft":      "rgba(34,197,94,0.10)",
            "--bear":           "#F43F5E",
            "--bear-soft":      "rgba(244,63,94,0.10)",
            "--amber":          "#FBBF24",
            "--info":           "#38BDF8",
            "--radius-sm":      "4px",
            "--radius-md":      "8px",
            "--radius-lg":      "12px",
            "--font-ui":        "'IBM Plex Sans', 'Inter', system-ui, sans-serif",
            "--font-data":      "'IBM Plex Mono', 'Consolas', monospace",
        },
    },

    # ── 3. Emerald — Plus Jakarta Sans + Fira Code ────────────────────────────
    "emerald": {
        "nome":  "Emerald",
        "emoji": "💚",
        "desc":  "verde escuro · Jakarta · acento esmeralda",
        "sidebar": "#060E09",
        "font_import": (
            f"@import url('{_GF}family=Plus+Jakarta+Sans:wght@400;500;600;700"
            "&family=Fira+Code:wght@400;500&display=swap');"
        ),
        "vars": {
            "--sidebar-bg":     "#060E09",
            "--bg-base":        "#0A1612",
            "--bg-surface":     "#111E18",
            "--bg-elevated":    "#192A20",
            "--bg-overlay":     "#1F3428",
            "--border-subtle":  "#1F3428",
            "--border-normal":  "#2A4535",
            "--border-focus":   "#10B981",
            "--text-primary":   "#E8F5EE",
            "--text-secondary": "#90B89F",
            "--text-muted":     "#5A7A65",
            "--accent":         "#10B981",
            "--accent-rgb":     "16,185,129",
            "--accent-hover":   "#059669",
            "--accent-soft":    "rgba(16,185,129,0.08)",
            "--accent-border":  "rgba(16,185,129,0.28)",
            "--bull":           "#34D399",
            "--bull-soft":      "rgba(52,211,153,0.10)",
            "--bear":           "#F87171",
            "--bear-soft":      "rgba(248,113,113,0.10)",
            "--amber":          "#FCD34D",
            "--info":           "#60A5FA",
            "--radius-sm":      "8px",
            "--radius-md":      "12px",
            "--radius-lg":      "18px",
            "--font-ui":        "'Plus Jakarta Sans', 'Inter', system-ui, sans-serif",
            "--font-data":      "'Fira Code', 'Consolas', monospace",
        },
    },

    # ── 4. Graphite — DM Sans + DM Mono ──────────────────────────────────────
    "graphite": {
        "nome":  "Graphite",
        "emoji": "⚫",
        "desc":  "cinza neutro · DM Sans · azul aço",
        "sidebar": "#0A0A0A",
        "font_import": (
            f"@import url('{_GF}family=DM+Sans:wght@300;400;500;700"
            "&family=DM+Mono:wght@400;500&display=swap');"
        ),
        "vars": {
            "--sidebar-bg":     "#0A0A0A",
            "--bg-base":        "#111111",
            "--bg-surface":     "#1A1A1A",
            "--bg-elevated":    "#242424",
            "--bg-overlay":     "#2E2E2E",
            "--border-subtle":  "#2E2E2E",
            "--border-normal":  "#3A3A3A",
            "--border-focus":   "#60A5FA",
            "--text-primary":   "#F5F5F5",
            "--text-secondary": "#A3A3A3",
            "--text-muted":     "#737373",
            "--accent":         "#60A5FA",
            "--accent-rgb":     "96,165,250",
            "--accent-hover":   "#3B82F6",
            "--accent-soft":    "rgba(96,165,250,0.08)",
            "--accent-border":  "rgba(96,165,250,0.25)",
            "--bull":           "#4ADE80",
            "--bull-soft":      "rgba(74,222,128,0.10)",
            "--bear":           "#F87171",
            "--bear-soft":      "rgba(248,113,113,0.10)",
            "--amber":          "#FBBF24",
            "--info":           "#818CF8",
            "--radius-sm":      "4px",
            "--radius-md":      "8px",
            "--radius-lg":      "10px",
            "--font-ui":        "'DM Sans', 'Inter', system-ui, sans-serif",
            "--font-data":      "'DM Mono', 'Consolas', monospace",
        },
    },

    # ── 5. Cyber — Outfit + Space Mono ───────────────────────────────────────
    "cyber": {
        "nome":  "Cyber",
        "emoji": "🟣",
        "desc":  "violeta escuro · Outfit · roxo neon",
        "sidebar": "#080514",
        "font_import": (
            f"@import url('{_GF}family=Outfit:wght@300;400;500;600;700"
            "&family=Space+Mono:wght@400;700&display=swap');"
        ),
        "vars": {
            "--sidebar-bg":     "#080514",
            "--bg-base":        "#0D0A1A",
            "--bg-surface":     "#130F24",
            "--bg-elevated":    "#1C1730",
            "--bg-overlay":     "#261F3E",
            "--border-subtle":  "#261F3E",
            "--border-normal":  "#332A52",
            "--border-focus":   "#A855F7",
            "--text-primary":   "#F0ECFF",
            "--text-secondary": "#9788C0",
            "--text-muted":     "#6B5E8A",
            "--accent":         "#A855F7",
            "--accent-rgb":     "168,85,247",
            "--accent-hover":   "#9333EA",
            "--accent-soft":    "rgba(168,85,247,0.08)",
            "--accent-border":  "rgba(168,85,247,0.25)",
            "--bull":           "#34D399",
            "--bull-soft":      "rgba(52,211,153,0.10)",
            "--bear":           "#FB7185",
            "--bear-soft":      "rgba(251,113,133,0.10)",
            "--amber":          "#FCD34D",
            "--info":           "#38BDF8",
            "--radius-sm":      "6px",
            "--radius-md":      "12px",
            "--radius-lg":      "18px",
            "--font-ui":        "'Outfit', 'Inter', system-ui, sans-serif",
            "--font-data":      "'Space Mono', 'Consolas', monospace",
        },
    },
}

TEMAS_ORDER = ["dark", "navy", "emerald", "graphite", "cyber"]
TEMAS_META  = {k: {"nome": v["nome"], "emoji": v["emoji"], "desc": v["desc"]}
               for k, v in TEMAS.items()}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_tema_ativo() -> str:
    qp = st.query_params.get("theme", None)
    if qp and qp in TEMAS:
        st.session_state["_theme"] = qp
    return st.session_state.get("_theme", "dark")


def set_tema(tema_id: str) -> None:
    if tema_id not in TEMAS:
        return
    st.session_state["_theme"] = tema_id
    try:
        st.query_params["theme"] = tema_id
    except Exception:
        pass


def get_tema_css() -> str:
    """
    Bloco <style> injetado APÓS o CSS principal para sobrescrever as variáveis
    :root com os valores do tema ativo (fonte, cores, sidebar bg).
    Também importa o par tipográfico do tema via Google Fonts.
    """
    tema_id    = get_tema_ativo()
    tema       = TEMAS.get(tema_id, TEMAS["dark"])
    font_imp   = tema.get("font_import", "")
    sidebar_bg = tema["vars"].get("--sidebar-bg", tema.get("sidebar", "#0B0C15"))
    vars_str   = "\n".join(f"        {k}: {v};" for k, v in tema["vars"].items())

    return f"""<style>
    {font_imp}
    :root {{
{vars_str}
    }}
    /* Sidebar — background do tema (ambos os seletores que o Streamlit usa) */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div:first-child {{
        background-color: {sidebar_bg} !important;
    }}
</style>"""


def get_accent_color() -> str:
    return TEMAS.get(get_tema_ativo(), TEMAS["dark"])["vars"]["--accent"]


def get_chart_colors() -> dict:
    t = TEMAS.get(get_tema_ativo(), TEMAS["dark"])["vars"]
    return {
        "accent":   t["--accent"],
        "bull":     t["--bull"],
        "bear":     t["--bear"],
        "amber":    t["--amber"],
        "info":     t["--info"],
        "text":     t["--text-primary"],
        "muted":    t["--text-muted"],
        "surface":  t["--bg-surface"],
        "elevated": t["--bg-elevated"],
        "border":   t["--border-subtle"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# WIDGET SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def render_theme_switcher_sidebar() -> None:
    """Selectbox de tema na sidebar com preview de paleta."""
    ativo = get_tema_ativo()

    st.sidebar.markdown(
        '<div style="font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;'
        'color:var(--text-muted);font-family:var(--font-ui);'
        'padding:0 4px;margin-bottom:4px;margin-top:12px;">tema</div>',
        unsafe_allow_html=True,
    )

    idx = TEMAS_ORDER.index(ativo) if ativo in TEMAS_ORDER else 0
    escolha = st.sidebar.selectbox(
        "Tema",
        options=TEMAS_ORDER,
        format_func=lambda tid: f"{TEMAS[tid]['emoji']}  {TEMAS[tid]['nome']}",
        index=idx,
        label_visibility="collapsed",
        key="_theme_selectbox",
    )

    if escolha != ativo:
        set_tema(escolha)
        st.rerun()

    # Dots de preview das cores do tema ativo
    v = TEMAS[ativo]["vars"]
    dots = "".join(
        f'<div style="width:7px;height:7px;border-radius:50%;background:{v[c]};">'
        f'</div>'
        for c in ("--accent", "--bull", "--bear", "--info")
    )
    st.sidebar.markdown(
        f'<div style="display:flex;align-items:center;gap:5px;padding:2px 4px 10px;">'
        f'{dots}'
        f'<span style="font-size:.58rem;color:var(--text-muted);'
        f'font-family:var(--font-ui);margin-left:2px;white-space:nowrap;overflow:hidden;'
        f'text-overflow:ellipsis;">{TEMAS[ativo]["desc"]}</span></div>',
        unsafe_allow_html=True,
    )
