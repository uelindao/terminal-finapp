"""
utils/themes.py — v3.0
Sistema de temas visuais + tipografia personalizável do Finterminal.

Cada tema tem paleta de cores, par tipográfico padrão e personalidade visual.
O usuário pode sobrescrever fontes de títulos, interface e dados independentemente.
"""

import streamlit as st

_GF = "https://fonts.googleapis.com/css2?"

# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGOS DE FONTES
# ══════════════════════════════════════════════════════════════════════════════

# Fontes para títulos / display (h1, h2, logotipo, page-title)
FONTES_TITULO: dict[str, dict] = {
    "space_grotesk":    {"nome": "Space Grotesk",    "css": "'Space Grotesk', 'Inter', sans-serif",         "gf": "Space+Grotesk:wght@500;600;700"},
    "syne":             {"nome": "Syne",              "css": "'Syne', 'Inter', sans-serif",                  "gf": "Syne:wght@600;700;800"},
    "barlow_condensed": {"nome": "Barlow Condensed",  "css": "'Barlow Condensed', sans-serif",               "gf": "Barlow+Condensed:wght@500;600;700"},
    "rajdhani":         {"nome": "Rajdhani",          "css": "'Rajdhani', sans-serif",                       "gf": "Rajdhani:wght@500;600;700"},
    "inter":            {"nome": "Inter",             "css": "'Inter', system-ui, sans-serif",               "gf": "Inter:wght@500;600;700"},
    "ibm_plex_sans":    {"nome": "IBM Plex Sans",     "css": "'IBM Plex Sans', 'Inter', sans-serif",         "gf": "IBM+Plex+Sans:wght@500;600;700"},
    "plus_jakarta":     {"nome": "Plus Jakarta Sans", "css": "'Plus Jakarta Sans', 'Inter', sans-serif",     "gf": "Plus+Jakarta+Sans:wght@500;600;700"},
    "dm_sans":          {"nome": "DM Sans",           "css": "'DM Sans', 'Inter', sans-serif",               "gf": "DM+Sans:wght@500;600;700"},
    "outfit":           {"nome": "Outfit",            "css": "'Outfit', 'Inter', sans-serif",                "gf": "Outfit:wght@500;600;700"},
}

# Fontes para interface / corpo (labels, botões, parágrafos)
FONTES_UI: dict[str, dict] = {
    "inter":         {"nome": "Inter",             "css": "'Inter', system-ui, -apple-system, sans-serif",  "gf": "Inter:wght@300;400;500;600"},
    "ibm_plex_sans": {"nome": "IBM Plex Sans",     "css": "'IBM Plex Sans', 'Inter', sans-serif",           "gf": "IBM+Plex+Sans:wght@300;400;500;600"},
    "dm_sans":       {"nome": "DM Sans",           "css": "'DM Sans', 'Inter', sans-serif",                 "gf": "DM+Sans:wght@300;400;500;600"},
    "outfit":        {"nome": "Outfit",            "css": "'Outfit', 'Inter', sans-serif",                  "gf": "Outfit:wght@300;400;500;600"},
    "plus_jakarta":  {"nome": "Plus Jakarta Sans", "css": "'Plus Jakarta Sans', 'Inter', sans-serif",       "gf": "Plus+Jakarta+Sans:wght@400;500;600"},
    "nunito_sans":   {"nome": "Nunito Sans",       "css": "'Nunito Sans', 'Inter', sans-serif",             "gf": "Nunito+Sans:wght@300;400;500;600"},
    "space_grotesk": {"nome": "Space Grotesk",     "css": "'Space Grotesk', 'Inter', sans-serif",           "gf": "Space+Grotesk:wght@300;400;500;600"},
}

# Fontes para dados / números / código (monospace)
FONTES_DATA: dict[str, dict] = {
    "jetbrains_mono":  {"nome": "JetBrains Mono",  "css": "'JetBrains Mono', 'Consolas', monospace",  "gf": "JetBrains+Mono:wght@400;500;600"},
    "ibm_plex_mono":   {"nome": "IBM Plex Mono",   "css": "'IBM Plex Mono', 'Consolas', monospace",   "gf": "IBM+Plex+Mono:wght@400;500"},
    "fira_code":       {"nome": "Fira Code",        "css": "'Fira Code', 'Consolas', monospace",       "gf": "Fira+Code:wght@400;500"},
    "dm_mono":         {"nome": "DM Mono",          "css": "'DM Mono', 'Consolas', monospace",         "gf": "DM+Mono:wght@400;500"},
    "space_mono":      {"nome": "Space Mono",       "css": "'Space Mono', 'Consolas', monospace",      "gf": "Space+Mono:wght@400;700"},
    "roboto_mono":     {"nome": "Roboto Mono",      "css": "'Roboto Mono', 'Consolas', monospace",     "gf": "Roboto+Mono:wght@400;500"},
    "source_code_pro": {"nome": "Source Code Pro",  "css": "'Source Code Pro', 'Consolas', monospace", "gf": "Source+Code+Pro:wght@400;500"},
}

# Padrões tipográficos por tema (chaves nos catálogos acima)
TEMAS_FONTES_DEFAULT: dict[str, dict] = {
    "dark":     {"titulo": "space_grotesk", "ui": "inter",        "data": "jetbrains_mono"},
    "navy":     {"titulo": "ibm_plex_sans", "ui": "ibm_plex_sans","data": "ibm_plex_mono"},
    "emerald":  {"titulo": "plus_jakarta",  "ui": "plus_jakarta", "data": "fira_code"},
    "graphite": {"titulo": "dm_sans",       "ui": "dm_sans",      "data": "dm_mono"},
    "cyber":    {"titulo": "syne",          "ui": "outfit",       "data": "space_mono"},
    "glass":    {"titulo": "outfit",        "ui": "dm_sans",      "data": "fira_code"},
    "light":    {"titulo": "inter",         "ui": "inter",        "data": "jetbrains_mono"},
    "papel":    {"titulo": "plus_jakarta",  "ui": "ibm_plex_sans","data": "ibm_plex_mono"},
    "mono":     {"titulo": "ibm_plex_sans", "ui": "ibm_plex_sans","data": "ibm_plex_mono"},
    "amber":    {"titulo": "space_grotesk", "ui": "dm_sans",      "data": "jetbrains_mono"},
    "verde":    {"titulo": "space_grotesk", "ui": "dm_sans",      "data": "jetbrains_mono"},
}


# ══════════════════════════════════════════════════════════════════════════════
# TEMAS DE CORES
# ══════════════════════════════════════════════════════════════════════════════

TEMAS: dict[str, dict] = {

    # ── 1. Dark Terminal ──────────────────────────────────────────────────────
    # Intenção: terminal moderno, preto profundo (próximo das refs 1, 2), acento laranja.
    "dark": {
        "nome":    "Dark Terminal",
        "emoji":   "🖤",
        "desc":    "preto profundo · acento laranja",
        "sidebar": "#070811",
        "vars": {
            "--sidebar-bg":     "#070811",
            "--bg-base":        "#0E0F18",
            "--bg-surface":     "#17182A",
            "--bg-elevated":    "#1F2138",
            "--bg-overlay":     "#28293F",
            "--border-subtle":  "#262839",
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
            "--amber-soft":     "rgba(245,158,11,0.10)",
            "--info":           "#3B82F6",
            "--info-soft":      "rgba(59,130,246,0.10)",
            "--radius-sm":      "8px",
            "--radius-md":      "14px",
            "--radius-lg":      "18px",
        },
    },

    # ── 2. Bloomberg ──────────────────────────────────────────────────────────
    # Intenção: estética terminal pro (Bloomberg/Refinitiv), navy profundo, cantos
    # discretamente arredondados. Refinos mantidos sutis pra preservar identidade.
    "navy": {
        "nome":    "Bloomberg",
        "emoji":   "🔵",
        "desc":    "navy profundo · IBM Plex · laranja vivo",
        "sidebar": "#060A13",
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
            "--amber-soft":     "rgba(251,191,36,0.10)",
            "--info":           "#38BDF8",
            "--info-soft":      "rgba(56,189,248,0.10)",
            "--radius-sm":      "6px",
            "--radius-md":      "10px",
            "--radius-lg":      "14px",
        },
    },

    # ── 3. Emerald ────────────────────────────────────────────────────────────
    # Intenção: quant verde / mesa de operações sustentável. Inspirado em ref 5
    # (DWISLN) — verde mais elétrico, com pop neon discreto. Cards bem arredondados.
    "emerald": {
        "nome":    "Emerald",
        "emoji":   "💚",
        "desc":    "verde elétrico · Jakarta · esmeralda neon",
        "sidebar": "#060E09",
        "vars": {
            "--sidebar-bg":     "#060E09",
            "--bg-base":        "#0A1612",
            "--bg-surface":     "#111E18",
            "--bg-elevated":    "#192A20",
            "--bg-overlay":     "#1F3428",
            "--border-subtle":  "#1F3428",
            "--border-normal":  "#2A4535",
            "--border-focus":   "#22E47C",
            "--text-primary":   "#E8F5EE",
            "--text-secondary": "#90B89F",
            "--text-muted":     "#5A7A65",
            "--accent":         "#22E47C",
            "--accent-rgb":     "34,228,124",
            "--accent-hover":   "#10B981",
            "--accent-soft":    "rgba(34,228,124,0.10)",
            "--accent-border":  "rgba(34,228,124,0.30)",
            "--bull":           "#22E47C",
            "--bull-soft":      "rgba(34,228,124,0.12)",
            "--bear":           "#F87171",
            "--bear-soft":      "rgba(248,113,113,0.10)",
            "--amber":          "#FCD34D",
            "--amber-soft":     "rgba(252,211,77,0.10)",
            "--info":           "#60A5FA",
            "--info-soft":      "rgba(96,165,250,0.10)",
            "--radius-sm":      "10px",
            "--radius-md":      "16px",
            "--radius-lg":      "22px",
        },
    },

    # ── 4. Graphite ───────────────────────────────────────────────────────────
    # Intenção: dashboard clean estilo Apexify (ref 3) sem o roxo — cinza com
    # toque azulado discreto, acento azul aço. Boa base para reading sessions longas.
    "graphite": {
        "nome":    "Graphite",
        "emoji":   "⚫",
        "desc":    "cinza azulado · DM Sans · azul aço",
        "sidebar": "#0A0B10",
        "vars": {
            "--sidebar-bg":     "#0A0B10",
            "--bg-base":        "#0F1117",
            "--bg-surface":     "#181923",
            "--bg-elevated":    "#22232E",
            "--bg-overlay":     "#2C2D38",
            "--border-subtle":  "#2A2B36",
            "--border-normal":  "#3A3B47",
            "--border-focus":   "#60A5FA",
            "--text-primary":   "#F5F5F8",
            "--text-secondary": "#A3A6B5",
            "--text-muted":     "#737685",
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
            "--amber-soft":     "rgba(251,191,36,0.10)",
            "--info":           "#818CF8",
            "--info-soft":      "rgba(129,140,248,0.10)",
            "--radius-sm":      "6px",
            "--radius-md":      "12px",
            "--radius-lg":      "16px",
        },
    },

    # ── 5. Cyber ──────────────────────────────────────────────────────────────
    # Intenção: pop neon roxo+rosa (refs 3 Apexify + 4 AdminSchool). Acento
    # secundário rosa permite gradient roxo→rosa em CTAs e cor de série pop.
    "cyber": {
        "nome":    "Cyber",
        "emoji":   "🟣",
        "desc":    "violeta neon · Outfit · pop rosa",
        "sidebar": "#080514",
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
            "--text-secondary": "#A599C8",
            "--text-muted":     "#7A6D96",
            "--accent":         "#A855F7",
            "--accent-rgb":     "168,85,247",
            "--accent-hover":   "#EC4899",
            "--accent-soft":    "rgba(168,85,247,0.08)",
            "--accent-border":  "rgba(168,85,247,0.25)",
            "--accent-secondary":      "#EC4899",
            "--accent-secondary-soft": "rgba(236,72,153,0.10)",
            "--bull":           "#34D399",
            "--bull-soft":      "rgba(52,211,153,0.10)",
            "--bear":           "#FB7185",
            "--bear-soft":      "rgba(251,113,133,0.10)",
            "--amber":          "#FCD34D",
            "--amber-soft":     "rgba(252,211,77,0.10)",
            "--info":           "#38BDF8",
            "--info-soft":      "rgba(56,189,248,0.10)",
            "--radius-sm":      "8px",
            "--radius-md":      "16px",
            "--radius-lg":      "22px",
        },
    },

    # ── 6. Koyfin (Light Professional) ───────────────────────────────────────
    # Intenção: clean profissional Koyfin/Apexify (ref 3) em modo claro. Sombras
    # presentes (não vai chapado). text-muted escurecido pra passar WCAG AA.
    "light": {
        "nome":    "Koyfin",
        "emoji":   "☀️",
        "desc":    "claro profissional · Inter · azul cobalto",
        "sidebar": "#E4E8F3",
        "is_light": True,
        "vars": {
            "--sidebar-bg":     "#E4E8F3",
            "--bg-base":        "#F0F2F8",
            "--bg-surface":     "#FFFFFF",
            "--bg-elevated":    "#E8EBF4",
            "--bg-overlay":     "#DDE1EE",
            "--border-subtle":  "#DDE1EE",
            "--border-normal":  "#C8CDE0",
            "--border-focus":   "#2563EB",
            "--text-primary":   "#1A1D2E",
            "--text-secondary": "#3B4259",
            "--text-muted":     "#6F7796",
            "--accent":         "#2563EB",
            "--accent-rgb":     "37,99,235",
            "--accent-hover":   "#1D4ED8",
            "--accent-soft":    "rgba(37,99,235,0.08)",
            "--accent-border":  "rgba(37,99,235,0.22)",
            "--bull":           "#059669",
            "--bull-soft":      "rgba(5,150,105,0.10)",
            "--bear":           "#DC2626",
            "--bear-soft":      "rgba(220,38,38,0.10)",
            "--amber":          "#D97706",
            "--amber-soft":     "rgba(217,119,6,0.10)",
            "--info":           "#0891B2",
            "--info-soft":      "rgba(8,145,178,0.10)",
            "--radius-sm":      "8px",
            "--radius-md":      "14px",
            "--radius-lg":      "18px",
        },
    },

    # ── 7. Papel (Bloomberg Print / Apresentação) ─────────────────────────────
    # Intenção: print elegante para apresentação/relatório. Acento laranja
    # escurecido pra passar WCAG AA sobre creme (era #FF6900 = 2.76; agora #CC5200 = 4.5+).
    "papel": {
        "nome":    "Papel",
        "emoji":   "📄",
        "desc":    "creme elegante · IBM Plex · laranja print",
        "sidebar": "#EDE9DF",
        "is_light": True,
        "vars": {
            "--sidebar-bg":     "#EDE9DF",
            "--bg-base":        "#FAFAF7",
            "--bg-surface":     "#FFFFFF",
            "--bg-elevated":    "#F2EFE6",
            "--bg-overlay":     "#E8E4D9",
            "--border-subtle":  "#E5E0D5",
            "--border-normal":  "#CFC9BB",
            "--border-focus":   "#CC5200",
            "--text-primary":   "#1C1C1E",
            "--text-secondary": "#3C3C3F",
            "--text-muted":     "#6E6E73",
            "--accent":         "#CC5200",
            "--accent-rgb":     "204,82,0",
            "--accent-hover":   "#A84300",
            "--accent-soft":    "rgba(204,82,0,0.08)",
            "--accent-border":  "rgba(204,82,0,0.28)",
            "--bull":           "#1A7F4B",
            "--bull-soft":      "rgba(26,127,75,0.10)",
            "--bear":           "#C0392B",
            "--bear-soft":      "rgba(192,57,43,0.10)",
            "--amber":          "#B45309",
            "--amber-soft":     "rgba(180,83,9,0.10)",
            "--info":           "#1D4ED8",
            "--info-soft":      "rgba(29,78,216,0.10)",
            "--radius-sm":      "4px",
            "--radius-md":      "10px",
            "--radius-lg":      "14px",
        },
    },

    # ── 8. Retro Âmbar (Grafite + laranja) ───────────────────────────────────
    # Intenção: nostalgia CRT âmbar (PDP-11, terminais 80s). Cantos retos
    # propositais — não aplicar refs modernas aqui.
    "amber": {
        "nome":    "Retro Âmbar",
        "emoji":   "🟠",
        "desc":    "grafite · laranja âmbar · terminal retrô CRT",
        "sidebar": "#0A0A0A",
        "vars": {
            "--sidebar-bg":     "#0A0A0A",
            "--bg-base":        "#111111",
            "--bg-surface":     "#1A1A1A",
            "--bg-elevated":    "#242424",
            "--bg-overlay":     "#2E2E2E",
            "--border-subtle":  "#2E2E2E",
            "--border-normal":  "#3D2E00",
            "--border-focus":   "#FF8C00",
            "--text-primary":   "#E8E8E8",
            "--text-secondary": "#A8A8A8",
            "--text-muted":     "#606060",
            "--accent":         "#FF8C00",
            "--accent-rgb":     "255,140,0",
            "--accent-hover":   "#FF6B00",
            "--accent-soft":    "rgba(255,140,0,0.10)",
            "--accent-border":  "rgba(255,140,0,0.28)",
            "--bull":           "#4ADE80",
            "--bull-soft":      "rgba(74,222,128,0.12)",
            "--bear":           "#F87171",
            "--bear-soft":      "rgba(248,113,113,0.12)",
            "--amber":          "#FBBF24",
            "--amber-soft":     "rgba(251,191,36,0.12)",
            "--info":           "#38BDF8",
            "--info-soft":      "rgba(56,189,248,0.12)",
            "--radius-sm":      "4px",
            "--radius-md":      "8px",
            "--radius-lg":      "10px",
        },
    },

    # ── 9. Retro Verde (Grafite + verde) ──────────────────────────────────────
    # Intenção: nostalgia CRT verde fosforescente (terminais 70s/80s). Idem amber.
    "verde": {
        "nome":    "Retro Verde",
        "emoji":   "🟢",
        "desc":    "grafite · verde fosforescente · terminal retrô CRT",
        "sidebar": "#0A0A0A",
        "vars": {
            "--sidebar-bg":     "#0A0A0A",
            "--bg-base":        "#111111",
            "--bg-surface":     "#1A1A1A",
            "--bg-elevated":    "#242424",
            "--bg-overlay":     "#2E2E2E",
            "--border-subtle":  "#2E2E2E",
            "--border-normal":  "#003D1A",
            "--border-focus":   "#00E676",
            "--text-primary":   "#E8E8E8",
            "--text-secondary": "#A8A8A8",
            "--text-muted":     "#606060",
            "--accent":         "#00E676",
            "--accent-rgb":     "0,230,118",
            "--accent-hover":   "#00C864",
            "--accent-soft":    "rgba(0,230,118,0.10)",
            "--accent-border":  "rgba(0,230,118,0.28)",
            "--bull":           "#00E676",
            "--bull-soft":      "rgba(0,230,118,0.12)",
            "--bear":           "#F87171",
            "--bear-soft":      "rgba(248,113,113,0.12)",
            "--amber":          "#FBBF24",
            "--amber-soft":     "rgba(251,191,36,0.12)",
            "--info":           "#38BDF8",
            "--info-soft":      "rgba(56,189,248,0.12)",
            "--radius-sm":      "4px",
            "--radius-md":      "8px",
            "--radius-lg":      "10px",
        },
    },

    # ── 10. Glass (NOVO) ──────────────────────────────────────────────────────
    # Intenção: glassmorphism inspirado em ref 3 (Apexify) — fundo profundo
    # roxo-azul, surfaces translúcidos com backdrop-filter, gradient roxo→azul.
    # Cards usam --surface-glass + --glass-blur (componentes da Fase 3 ativam).
    "glass": {
        "nome":    "Glass",
        "emoji":   "🪟",
        "desc":    "vidro fosco · roxo-azul · superfícies translúcidas",
        "sidebar": "#0B0822",
        "vars": {
            "--sidebar-bg":     "#0B0822",
            "--bg-base":        "#0F0B24",
            "--bg-surface":     "#1A1238",
            "--bg-elevated":    "#241A4A",
            "--bg-overlay":     "#2E235E",
            "--border-subtle":  "rgba(167,139,250,0.12)",
            "--border-normal":  "rgba(167,139,250,0.22)",
            "--border-focus":   "#A78BFA",
            "--text-primary":   "#F0EDFF",
            "--text-secondary": "#B4A7D6",
            "--text-muted":     "#7A6DA0",
            "--accent":         "#A78BFA",
            "--accent-rgb":     "167,139,250",
            "--accent-hover":   "#60A5FA",
            "--accent-soft":    "rgba(167,139,250,0.10)",
            "--accent-border":  "rgba(167,139,250,0.30)",
            "--accent-secondary":      "#60A5FA",
            "--accent-secondary-soft": "rgba(96,165,250,0.10)",
            "--bull":           "#34D399",
            "--bull-soft":      "rgba(52,211,153,0.12)",
            "--bear":           "#FB7185",
            "--bear-soft":      "rgba(251,113,133,0.12)",
            "--amber":          "#FBBF24",
            "--amber-soft":     "rgba(251,191,36,0.12)",
            "--info":           "#60A5FA",
            "--info-soft":      "rgba(96,165,250,0.12)",
            "--radius-sm":      "10px",
            "--radius-md":      "16px",
            "--radius-lg":      "22px",
        },
    },

    # ── 11. Mono Pro (NOVO) ───────────────────────────────────────────────────
    # Intenção: papel digital FT/Tufte — alto contraste B&W com um único acento
    # laranja print. Densidade alta, cantos quase retos. Charts em escala de
    # cinza com acento só no destaque (ver CHART_PALETTES["mono"]).
    "mono": {
        "nome":    "Mono Pro",
        "emoji":   "⚪",
        "desc":    "preto & branco · IBM Plex · laranja print",
        "sidebar": "#FFFFFF",
        "is_light": True,
        "vars": {
            "--sidebar-bg":     "#FFFFFF",
            "--bg-base":        "#FAFAF8",
            "--bg-surface":     "#FFFFFF",
            "--bg-elevated":    "#F2F2EF",
            "--bg-overlay":     "#E8E8E4",
            "--border-subtle":  "#DDDDD7",
            "--border-normal":  "#B5B5AE",
            "--border-focus":   "#0A0A0A",
            "--text-primary":   "#0A0A0A",
            "--text-secondary": "#3A3A38",
            "--text-muted":     "#6E6E68",
            "--accent":         "#D94800",
            "--accent-rgb":     "217,72,0",
            "--accent-hover":   "#B33C00",
            "--accent-soft":    "rgba(217,72,0,0.08)",
            "--accent-border":  "rgba(217,72,0,0.28)",
            "--bull":           "#0F7A3A",
            "--bull-soft":      "rgba(15,122,58,0.10)",
            "--bear":           "#B91C1C",
            "--bear-soft":      "rgba(185,28,28,0.10)",
            "--amber":          "#A86B00",
            "--amber-soft":     "rgba(168,107,0,0.10)",
            "--info":           "#1E40AF",
            "--info-soft":      "rgba(30,64,175,0.10)",
            "--radius-sm":      "2px",
            "--radius-md":      "4px",
            "--radius-lg":      "6px",
        },
    },
}

TEMAS_ORDER = ["dark", "navy", "emerald", "graphite", "cyber", "glass", "amber", "verde", "light", "papel", "mono"]
TEMAS_META  = {k: {"nome": v["nome"], "emoji": v["emoji"], "desc": v["desc"]}
               for k, v in TEMAS.items()}


# ══════════════════════════════════════════════════════════════════════════════
# DESIGN TOKENS v2 — escala compartilhada (Fase 1)
# Espaçamento, tipografia, motion são iguais em todos os temas.
# Radius e cores vêm de cada tema (preserva identidade).
# ══════════════════════════════════════════════════════════════════════════════

TOKENS_BASE: dict[str, str] = {
    # Espaçamento — escala 4/8/12/16/20/24/32/40
    "--space-0": "0",
    "--space-1": "4px",
    "--space-2": "8px",
    "--space-3": "12px",
    "--space-4": "16px",
    "--space-5": "20px",
    "--space-6": "24px",
    "--space-7": "32px",
    "--space-8": "40px",

    # Tipografia — escala harmônica
    "--text-xs":   "0.7rem",
    "--text-sm":   "0.8rem",
    "--text-base": "0.9rem",
    "--text-md":   "1rem",
    "--text-lg":   "1.2rem",
    "--text-xl":   "1.5rem",
    "--text-2xl":  "2rem",
    "--text-3xl":  "2.8rem",

    # Letter-spacing — uppercase labels estilo Bloomberg
    "--ls-tight":  "-0.01em",
    "--ls-normal": "0",
    "--ls-wide":   "0.08em",
    "--ls-wider":  "0.12em",

    # Motion
    "--motion-fast":   "120ms",
    "--motion-normal": "200ms",
    "--motion-slow":   "320ms",
    "--ease-out":      "cubic-bezier(.22,.61,.36,1)",
    "--ease-in-out":   "cubic-bezier(.65,0,.35,1)",

    # Radius extra (xl) para cards grandes / modais — cada tema mantém sm/md/lg próprios
    "--radius-xl": "20px",

    # Glass blur (compartilhado — surface-glass varia por tema)
    "--glass-blur": "blur(16px) saturate(160%)",
}


# Paletas de séries para charts (Plotly) — 8 cores qualitativas por tema.
# Pensadas para boa separação visual e razoável para daltonismo.
CHART_PALETTES: dict[str, list[str]] = {
    "dark":     ["#FF8C00", "#3B82F6", "#10B981", "#A855F7", "#F59E0B", "#06B6D4", "#EC4899", "#94A3B8"],
    "navy":     ["#F97316", "#38BDF8", "#22C55E", "#A78BFA", "#FBBF24", "#06B6D4", "#F472B6", "#94A3B8"],
    "emerald":  ["#22E47C", "#34D399", "#60A5FA", "#FBBF24", "#FB7185", "#A78BFA", "#06B6D4", "#90B89F"],
    "graphite": ["#60A5FA", "#818CF8", "#4ADE80", "#FBBF24", "#F87171", "#A78BFA", "#06B6D4", "#A3A6B5"],
    "cyber":    ["#A855F7", "#EC4899", "#06B6D4", "#34D399", "#FBBF24", "#F472B6", "#60A5FA", "#A599C8"],
    "glass":    ["#A78BFA", "#60A5FA", "#34D399", "#FBBF24", "#FB7185", "#06B6D4", "#EC4899", "#B4A7D6"],
    "light":    ["#2563EB", "#059669", "#D97706", "#DC2626", "#9333EA", "#0891B2", "#DB2777", "#475569"],
    "papel":    ["#CC5200", "#1A7F4B", "#B45309", "#1D4ED8", "#7C3AED", "#0E7490", "#BE185D", "#475569"],
    "mono":     ["#0A0A0A", "#D94800", "#3A3A38", "#6E6E68", "#0F7A3A", "#B91C1C", "#1E40AF", "#A86B00"],
    "amber":    ["#FF8C00", "#FBBF24", "#4ADE80", "#38BDF8", "#A78BFA", "#F87171", "#22D3EE", "#A8A8A8"],
    "verde":    ["#00E676", "#4ADE80", "#FBBF24", "#38BDF8", "#A78BFA", "#F87171", "#22D3EE", "#A8A8A8"],
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """#RRGGBB ou #RGB → (r, g, b). Retorna (0,0,0) para entradas inválidas."""
    h = hex_color.lstrip("#").strip()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def _rgba(hex_color: str, alpha: float) -> str:
    """#RRGGBB + alpha → 'rgba(r, g, b, a)'. Se já for rgba(...), devolve como veio."""
    if not hex_color or not hex_color.startswith("#"):
        return hex_color
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


def _compute_derived(vars: dict, is_light: bool, tema_id: str) -> dict[str, str]:
    """
    Tokens derivados das cores semânticas do tema:
    gradient do acento, glass surfaces, pill backgrounds, sombras, cores de chart.
    Mantém retrocompatibilidade — só adiciona, não sobrescreve nada existente.
    """
    accent     = vars.get("--accent", "#FF8C00")
    accent_hov = vars.get("--accent-hover", accent)
    bg_surface = vars.get("--bg-surface", "#1C1D2B")
    bg_elev    = vars.get("--bg-elevated", bg_surface)

    bull  = vars.get("--bull",  "#10B981")
    bear  = vars.get("--bear",  "#EF4444")
    amber = vars.get("--amber", "#F59E0B")
    info  = vars.get("--info",  "#3B82F6")

    # Sombras — mais sutis em claro, mais profundas em escuro
    if is_light:
        shadows = {
            "--shadow-sm": "0 1px 2px rgba(15,23,42,0.06), 0 1px 1px rgba(15,23,42,0.04)",
            "--shadow-md": "0 4px 12px rgba(15,23,42,0.08), 0 2px 4px rgba(15,23,42,0.04)",
            "--shadow-lg": "0 12px 28px rgba(15,23,42,0.10), 0 4px 10px rgba(15,23,42,0.06)",
            "--shadow-xl": "0 24px 48px rgba(15,23,42,0.14), 0 8px 18px rgba(15,23,42,0.08)",
        }
    else:
        shadows = {
            "--shadow-sm": "0 1px 2px rgba(0,0,0,0.32), 0 1px 1px rgba(0,0,0,0.18)",
            "--shadow-md": "0 6px 16px rgba(0,0,0,0.42), 0 2px 6px rgba(0,0,0,0.22)",
            "--shadow-lg": "0 18px 36px rgba(0,0,0,0.50), 0 6px 14px rgba(0,0,0,0.30)",
            "--shadow-xl": "0 32px 60px rgba(0,0,0,0.58), 0 10px 24px rgba(0,0,0,0.38)",
        }

    # Paleta de chart por tema (com fallback pro dark)
    palette = CHART_PALETTES.get(tema_id, CHART_PALETTES["dark"])
    chart_vars = {f"--chart-{i+1}": cor for i, cor in enumerate(palette)}

    derived: dict[str, str] = {
        # Gradient do acento — usado em CTAs, KPI ativo, item sidebar selecionado
        "--accent-gradient":        f"linear-gradient(135deg, {accent} 0%, {accent_hov} 100%)",
        "--accent-gradient-strong": f"linear-gradient(135deg, {accent_hov} 0%, {accent} 100%)",

        # Glass surfaces — tema Glass usa pleno; outros temas podem usar em overlays
        "--surface-glass":        _rgba(bg_surface, 0.62),
        "--surface-glass-strong": _rgba(bg_surface, 0.82),

        # Pill backgrounds — mini-ícone colorido no canto do KPI (ref 1)
        "--pill-bull-bg":   _rgba(bull,   0.16),
        "--pill-bear-bg":   _rgba(bear,   0.16),
        "--pill-amber-bg":  _rgba(amber,  0.16),
        "--pill-info-bg":   _rgba(info,   0.16),
        "--pill-accent-bg": _rgba(accent, 0.16),
        "--pill-muted-bg":  bg_elev,

        # Chart tokens — grid sutil, eixo, fundo do tooltip
        "--chart-grid":        _rgba(vars.get("--text-muted", "#6B7280"), 0.20),
        "--chart-axis":        vars.get("--text-muted", "#6B7280"),
        "--chart-tooltip-bg":  _rgba(bg_elev, 0.96),
        "--chart-tooltip-bd":  vars.get("--border-normal", bg_elev),
    }

    return {**derived, **shadows, **chart_vars}


def get_design_tokens() -> dict[str, str]:
    """
    Snapshot dos tokens efetivos do tema ativo (base + tema + derivados).
    Útil para consumo Python — ex.: gerar cores de série pro Plotly.
    """
    tema_id = get_tema_ativo()
    tema    = TEMAS.get(tema_id, TEMAS["dark"])
    is_lt   = tema.get("is_light", False)
    derived = _compute_derived(tema["vars"], is_lt, tema_id)
    return {**TOKENS_BASE, **tema["vars"], **derived}


def get_chart_palette() -> list[str]:
    """Paleta de 8 cores qualitativas do tema ativo (uso em Plotly)."""
    tema_id = get_tema_ativo()
    return list(CHART_PALETTES.get(tema_id, CHART_PALETTES["dark"]))


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — TEMA
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


def is_tema_claro() -> bool:
    """Retorna True se o tema ativo é de fundo claro (light mode)."""
    return TEMAS.get(get_tema_ativo(), {}).get("is_light", False)


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
# HELPERS — FONTES
# ══════════════════════════════════════════════════════════════════════════════

def get_fontes_ativas() -> dict[str, str]:
    """
    Retorna as chaves das fontes ativas para {titulo, ui, data}.
    Prioridade: session_state (picker) > padrão do tema ativo.
    """
    tema_id  = get_tema_ativo()
    defaults = TEMAS_FONTES_DEFAULT.get(tema_id, TEMAS_FONTES_DEFAULT["dark"])

    ft = st.session_state.get("_font_titulo", "")
    fu = st.session_state.get("_font_ui",     "")
    fd = st.session_state.get("_font_data",   "")

    return {
        "titulo": ft if ft in FONTES_TITULO else defaults["titulo"],
        "ui":     fu if fu in FONTES_UI     else defaults["ui"],
        "data":   fd if fd in FONTES_DATA   else defaults["data"],
    }


def resetar_fontes() -> None:
    """Remove overrides de fonte, voltando ao padrão do tema ativo."""
    for k in ("_font_titulo", "_font_ui", "_font_data"):
        st.session_state.pop(k, None)


def _build_gf_import(f_titulo: dict, f_ui: dict, f_data: dict) -> str:
    """Constrói URL única do Google Fonts combinando as 3 fontes (sem duplicatas)."""
    seen: set[str] = set()
    families: list[str] = []
    for f in (f_titulo, f_ui, f_data):
        family_name = f["gf"].split(":")[0]
        if family_name not in seen:
            families.append(f["gf"])
            seen.add(family_name)
    url = _GF + "&".join(f"family={fam}" for fam in families) + "&display=swap"
    return f"@import url('{url}');"


# ══════════════════════════════════════════════════════════════════════════════
# CSS DO TEMA
# ══════════════════════════════════════════════════════════════════════════════

def get_tema_css() -> str:
    """
    Bloco <style> injetado APÓS o CSS principal — sobrescreve variáveis :root
    com as cores do tema + as fontes escolhidas (ou padrões do tema).
    """
    tema_id    = get_tema_ativo()
    tema       = TEMAS.get(tema_id, TEMAS["dark"])
    sidebar_bg = tema["vars"]["--sidebar-bg"]

    # Fontes ativas
    fontes   = get_fontes_ativas()
    f_titulo = FONTES_TITULO.get(fontes["titulo"], FONTES_TITULO["space_grotesk"])
    f_ui     = FONTES_UI.get(fontes["ui"],         FONTES_UI["inter"])
    f_data   = FONTES_DATA.get(fontes["data"],      FONTES_DATA["jetbrains_mono"])

    font_import = _build_gf_import(f_titulo, f_ui, f_data)

    # Variáveis de fonte sobrescrevem o :root
    font_vars = {
        "--font-title": f_titulo["css"],
        "--font-ui":    f_ui["css"],
        "--font-data":  f_data["css"],
    }

    # Tokens derivados (gradient, glass, pills, sombras, chart-1..8)
    is_light_t   = tema.get("is_light", False)
    derived_vars = _compute_derived(tema["vars"], is_light_t, tema_id)

    # Ordem: base (espaçamento/tipografia/motion) → tema (cores) → derivados → fontes
    all_vars = {**TOKENS_BASE, **tema["vars"], **derived_vars, **font_vars}
    vars_str = "\n".join(f"        {k}: {v};" for k, v in all_vars.items())

    light_overrides = ""
    if tema.get("is_light"):
        t = tema["vars"]
        light_overrides = f"""
    /* ── Light mode: override seletores Streamlit que ficam escuros ── */
    html, body, .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    section.main > div {{
        background-color: {t['--bg-base']} !important;
        color: {t['--text-primary']} !important;
    }}
    .stMarkdown p, .stMarkdown li, .stMarkdown span,
    [data-testid="stText"], [data-testid="stCaptionContainer"],
    label, .stSelectbox label, .stTextInput label,
    .stSlider label, .stNumberInput label, .stRadio label,
    .stCheckbox label, .stTextarea label {{
        color: {t['--text-secondary']} !important;
    }}
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stMultiSelect"] > div > div {{
        background-color: {t['--bg-surface']} !important;
        border-color: {t['--border-normal']} !important;
        color: {t['--text-primary']} !important;
    }}
    [data-testid="stDataFrame"],
    [data-testid="stDataFrame"] > div,
    [data-testid="stDataFrame"] canvas {{
        background-color: {t['--bg-surface']} !important;
        color: {t['--text-primary']} !important;
    }}
    [data-testid="stExpander"] {{
        background-color: {t['--bg-surface']} !important;
        border-color: {t['--border-subtle']} !important;
    }}
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        background-color: {t['--bg-elevated']} !important;
    }}
    [data-testid="stTabs"] [data-baseweb="tab"] {{
        color: {t['--text-secondary']} !important;
    }}
    [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {{
        color: {t['--accent']} !important;
    }}
    [data-testid="stMetric"] > div {{
        background-color: {t['--bg-surface']} !important;
    }}
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] [data-testid="stMetricLabel"] {{
        color: {t['--text-primary']} !important;
    }}
    [data-testid="stAlert"] {{
        background-color: {t['--bg-elevated']} !important;
    }}
    [data-baseweb="popover"], [data-baseweb="menu"] {{
        background-color: {t['--bg-surface']} !important;
        border-color: {t['--border-normal']} !important;
    }}
    [data-baseweb="option"]:hover {{
        background-color: {t['--bg-elevated']} !important;
    }}
    hr {{ border-color: {t['--border-subtle']} !important; }}
    .stMarkdown code {{
        background: {t['--bg-elevated']} !important;
        color: {t['--accent']} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {t['--text-secondary']};
    }}
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] strong {{
        color: {t['--text-primary']} !important;
    }}
    """

    return f"""<style>
    {font_import}
    :root {{
{vars_str}
    }}
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div:first-child {{
        background-color: {sidebar_bg} !important;
    }}
    {light_overrides}
</style>"""


# ══════════════════════════════════════════════════════════════════════════════
# WIDGET SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def render_theme_switcher_sidebar() -> None:
    """Selectbox de tema na sidebar com preview de paleta. Escuros e Claros agrupados."""
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
        format_func=lambda tid: (
            f"{TEMAS[tid]['emoji']}  {TEMAS[tid]['nome']}"
            + ("  ·  claro" if TEMAS[tid].get("is_light") else "")
        ),
        index=idx,
        label_visibility="collapsed",
        key="_theme_selectbox",
    )

    if escolha != ativo:
        set_tema(escolha)
        st.rerun()

    # Preview de cores do tema ativo
    v = TEMAS[ativo]["vars"]
    dots = "".join(
        f'<div style="width:7px;height:7px;border-radius:50%;background:{v[c]};'
        f'flex-shrink:0;border:1px solid rgba(0,0,0,0.1);"></div>'
        for c in ("--accent", "--bull", "--bear", "--info")
    )
    st.sidebar.markdown(
        f'<div style="display:flex;align-items:center;gap:5px;padding:2px 4px 10px;">'
        f'{dots}'
        f'<span style="font-size:.58rem;color:var(--text-muted);font-family:var(--font-ui);'
        f'margin-left:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
        f'{TEMAS[ativo]["desc"]}</span></div>',
        unsafe_allow_html=True,
    )
