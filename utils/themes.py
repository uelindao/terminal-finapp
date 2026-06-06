"""
utils/themes.py
===============
Sistema de temas visuais do Finterminal.

Cada tema define um dict de variáveis CSS que sobrescreve o :root do design system.
O tema ativo é armazenado em st.session_state["_theme"] e persiste via st.query_params.

Uso
---
    from utils.themes import get_tema_css, TEMAS_META
    css_vars = get_tema_css()           # retorna bloco <style>:root{...}</style>
    render_theme_switcher_sidebar()     # widget compacto para a sidebar
"""

import streamlit as st


# ══════════════════════════════════════════════════════════════════════════════
# DEFINIÇÃO DOS TEMAS
# Cada tema: nome display, emoji/icon, descrição curta e variáveis CSS.
# ══════════════════════════════════════════════════════════════════════════════

TEMAS: dict[str, dict] = {

    # ── 1. Dark Terminal (padrão) ──────────────────────────────────────────
    "dark": {
        "nome":      "Dark Terminal",
        "emoji":     "🖤",
        "desc":      "azul-escuro clássico, acento laranja",
        "sidebar":   "#0B0C15",
        "vars": {
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
            "--accent-hover":   "#FF6B00",
            "--accent-soft":    "rgba(255,140,0,0.08)",
            "--accent-border":  "rgba(255,140,0,0.25)",
            "--bull":           "#10B981",
            "--bull-soft":      "rgba(16,185,129,0.10)",
            "--bear":           "#EF4444",
            "--bear-soft":      "rgba(239,68,68,0.10)",
            "--amber":          "#F59E0B",
            "--info":           "#3B82F6",
        },
    },

    # ── 2. Bloomberg (navy profundo) ──────────────────────────────────────
    "navy": {
        "nome":      "Bloomberg",
        "emoji":     "🔵",
        "desc":      "navy profundo, acento laranja vivo",
        "sidebar":   "#060A13",
        "vars": {
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
            "--accent-hover":   "#EA6A00",
            "--accent-soft":    "rgba(249,115,22,0.08)",
            "--accent-border":  "rgba(249,115,22,0.28)",
            "--bull":           "#22C55E",
            "--bull-soft":      "rgba(34,197,94,0.10)",
            "--bear":           "#F43F5E",
            "--bear-soft":      "rgba(244,63,94,0.10)",
            "--amber":          "#FBBF24",
            "--info":           "#38BDF8",
        },
    },

    # ── 3. Emerald (verde financeiro) ─────────────────────────────────────
    "emerald": {
        "nome":      "Emerald",
        "emoji":     "💚",
        "desc":      "verde escuro, acento esmeralda",
        "sidebar":   "#060E09",
        "vars": {
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
            "--accent-hover":   "#059669",
            "--accent-soft":    "rgba(16,185,129,0.08)",
            "--accent-border":  "rgba(16,185,129,0.28)",
            "--bull":           "#34D399",
            "--bull-soft":      "rgba(52,211,153,0.10)",
            "--bear":           "#F87171",
            "--bear-soft":      "rgba(248,113,113,0.10)",
            "--amber":          "#FCD34D",
            "--info":           "#60A5FA",
        },
    },

    # ── 4. Graphite (cinza profissional) ──────────────────────────────────
    "graphite": {
        "nome":      "Graphite",
        "emoji":     "⚫",
        "desc":      "cinza neutro, acento azul aço",
        "sidebar":   "#0A0A0A",
        "vars": {
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
            "--accent-hover":   "#3B82F6",
            "--accent-soft":    "rgba(96,165,250,0.08)",
            "--accent-border":  "rgba(96,165,250,0.25)",
            "--bull":           "#4ADE80",
            "--bull-soft":      "rgba(74,222,128,0.10)",
            "--bear":           "#F87171",
            "--bear-soft":      "rgba(248,113,113,0.10)",
            "--amber":          "#FBBF24",
            "--info":           "#818CF8",
        },
    },

    # ── 5. Cyber (roxo neon) ──────────────────────────────────────────────
    "cyber": {
        "nome":      "Cyber",
        "emoji":     "🟣",
        "desc":      "violeta escuro, acento roxo neon",
        "sidebar":   "#080514",
        "vars": {
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
            "--accent-hover":   "#9333EA",
            "--accent-soft":    "rgba(168,85,247,0.08)",
            "--accent-border":  "rgba(168,85,247,0.25)",
            "--bull":           "#34D399",
            "--bull-soft":      "rgba(52,211,153,0.10)",
            "--bear":           "#FB7185",
            "--bear-soft":      "rgba(251,113,133,0.10)",
            "--amber":          "#FCD34D",
            "--info":           "#38BDF8",
        },
    },
}

# Ordem de exibição no switcher
TEMAS_ORDER = ["dark", "navy", "emerald", "graphite", "cyber"]

# Metadata para exibição rápida (sem carregar vars completas)
TEMAS_META = {k: {"nome": v["nome"], "emoji": v["emoji"], "desc": v["desc"]}
              for k, v in TEMAS.items()}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_tema_ativo() -> str:
    """Retorna o ID do tema ativo (default: 'dark')."""
    # Persistência via query params (sobrevive a reloads)
    qp = st.query_params.get("theme", None)
    if qp and qp in TEMAS:
        st.session_state["_theme"] = qp
    return st.session_state.get("_theme", "dark")


def set_tema(tema_id: str) -> None:
    """Define o tema ativo e persiste em query params."""
    if tema_id not in TEMAS:
        return
    st.session_state["_theme"] = tema_id
    try:
        st.query_params["theme"] = tema_id
    except Exception:
        pass


def get_tema_css() -> str:
    """
    Retorna bloco <style> com as variáveis CSS do tema ativo,
    para injetar via st.markdown(unsafe_allow_html=True).
    Também injeta background da sidebar.
    """
    tema_id  = get_tema_ativo()
    tema     = TEMAS.get(tema_id, TEMAS["dark"])
    sidebar  = tema["sidebar"]
    vars_str = "\n".join(
        f"        {k}: {v};" for k, v in tema["vars"].items()
    )
    return f"""<style>
    :root {{
{vars_str}
    }}
    [data-testid="stSidebar"] > div:first-child {{
        background-color: {sidebar} !important;
    }}
</style>"""


def get_accent_color() -> str:
    """Retorna a cor de acento do tema ativo (para uso em charts Python)."""
    tema_id = get_tema_ativo()
    return TEMAS.get(tema_id, TEMAS["dark"])["vars"]["--accent"]


def get_chart_colors() -> dict:
    """Retorna paleta de cores do tema ativo para uso em gráficos Plotly."""
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
    """
    Renderiza o seletor de tema compacto na sidebar.
    Chamado uma vez por página no bloco de configuração da sidebar.
    """
    ativo = get_tema_ativo()

    st.sidebar.markdown(
        '<div style="font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;'
        'color:var(--text-muted);font-family:var(--font-ui);'
        'padding:0 4px;margin-bottom:4px;margin-top:12px;">tema</div>',
        unsafe_allow_html=True,
    )

    # Botões compactos inline — um por tema
    cols = st.sidebar.columns(len(TEMAS_ORDER))
    for col, tid in zip(cols, TEMAS_ORDER):
        meta = TEMAS_META[tid]
        is_active = (tid == ativo)
        border = "2px solid var(--accent)" if is_active else "1px solid var(--border-subtle)"
        bg     = "var(--accent-soft)"       if is_active else "transparent"
        if col.button(
            meta["emoji"],
            key=f"_theme_btn_{tid}",
            help=f"{meta['nome']} — {meta['desc']}",
            use_container_width=True,
        ):
            set_tema(tid)
            st.rerun()

        # Underline do ativo
        if is_active:
            col.markdown(
                f'<div style="height:2px;background:var(--accent);'
                f'border-radius:1px;margin-top:-10px;"></div>',
                unsafe_allow_html=True,
            )
