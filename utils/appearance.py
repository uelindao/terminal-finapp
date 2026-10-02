"""Perfis de leitura: composição visual independente da paleta de cores.

O estado é simples e público para a página de preferências: perfil, paleta,
densidade e overrides de fontes. Os parâmetros de URL permitem reabrir a
mesma bancada; os dados financeiros e o conteúdo das páginas não mudam.
"""
from __future__ import annotations

import streamlit as st

PERFIS_VISUAIS = {
    "terminal": {
        "nome": "Terminal compacto",
        "desc": "Mais dados por tela, cantos retos, números alinhados e gráficos enxutos.",
        "uso": "Comparar indicadores e acompanhar listas de ativos.",
        "fontes": {"titulo": "ibm_plex_sans", "ui": "ibm_plex_sans", "data": "ibm_plex_mono"},
        "densidade": "compacta",
        "tokens": {
            "--content-width": "1760px", "--page-title-size": "clamp(1.55rem, 2.2vw, 2.05rem)",
            "--radius-sm": "3px", "--radius-md": "3px", "--radius-lg": "4px", "--radius-xl": "6px",
            "--metric-value-size": "1.35rem", "--metric-min-height": "82px", "--metric-background": "var(--bg-base)",
            "--hero-padding": "18px", "--hero-value-size": "clamp(1.7rem, 3vw, 2.4rem)",
            "--chart-height": "330", "--chart-grid-opacity": "0.18", "--chart-grid-visible": "true",
            "--chart-grid-dash": "solid", "--chart-line-width": "1.7", "--chart-fill-opacity": "0.05",
            "--chart-font-size": "11", "--chart-hovermode": "x unified", "--chart-padding": "6px 4px 4px",
        },
    },
    "mesa": {
        "nome": "Mesa de análise",
        "desc": "Painéis equilibrados, hierarquia suave e espaço para cruzar contexto e preço.",
        "uso": "Explorar fundamentos, carteira e cenário macro na mesma sessão.",
        "fontes": {"titulo": "ibm_plex_sans", "ui": "dm_sans", "data": "ibm_plex_mono"},
        "densidade": "equilibrada",
        "tokens": {
            "--content-width": "1560px", "--page-title-size": "clamp(1.8rem, 3vw, 2.65rem)",
            "--radius-sm": "6px", "--radius-md": "8px", "--radius-lg": "10px", "--radius-xl": "12px",
            "--metric-value-size": "1.65rem", "--metric-min-height": "112px", "--metric-background": "var(--bg-surface)",
            "--hero-padding": "28px", "--hero-value-size": "clamp(1.8rem, 3.4vw, 2.9rem)",
            "--chart-height": "400", "--chart-grid-opacity": "0.16", "--chart-grid-visible": "true",
            "--chart-grid-dash": "dot", "--chart-line-width": "2.2", "--chart-fill-opacity": "0.10",
            "--chart-font-size": "12", "--chart-hovermode": "x unified", "--chart-padding": "12px 8px 8px",
        },
    },
    "caderno": {
        "nome": "Caderno quantitativo",
        "desc": "Página de leitura, superfícies planas, títulos serifados e gráficos sem grade.",
        "uso": "Ler teses, relatórios, séries históricas e registrar decisões.",
        "fontes": {"titulo": "source_serif", "ui": "ibm_plex_sans", "data": "ibm_plex_mono"},
        "densidade": "confortavel",
        "tokens": {
            "--content-width": "1240px", "--page-title-size": "clamp(2rem, 3vw, 2.9rem)",
            "--radius-sm": "2px", "--radius-md": "3px", "--radius-lg": "4px", "--radius-xl": "6px",
            "--metric-value-size": "1.75rem", "--metric-min-height": "104px", "--metric-background": "transparent",
            "--hero-padding": "24px", "--hero-value-size": "clamp(1.8rem, 3vw, 2.8rem)",
            "--chart-height": "450", "--chart-grid-opacity": "0.12", "--chart-grid-visible": "false",
            "--chart-grid-dash": "dot", "--chart-line-width": "2", "--chart-fill-opacity": "0.04",
            "--chart-font-size": "13", "--chart-hovermode": "x unified", "--chart-padding": "16px 4px 8px",
        },
    },
    "radar": {
        "nome": "Radar visual",
        "desc": "Bancada ampla, valores em destaque e gráficos maiores para perceber relações.",
        "uso": "Explorar tendências, dispersões, correlações e sinais técnicos.",
        "fontes": {"titulo": "space_grotesk", "ui": "dm_sans", "data": "jetbrains_mono"},
        "densidade": "equilibrada",
        "tokens": {
            "--content-width": "1840px", "--page-title-size": "clamp(1.8rem, 2.8vw, 2.6rem)",
            "--radius-sm": "8px", "--radius-md": "12px", "--radius-lg": "14px", "--radius-xl": "16px",
            "--metric-value-size": "2.05rem", "--metric-min-height": "132px", "--metric-background": "var(--bg-surface)",
            "--hero-padding": "30px", "--hero-value-size": "clamp(2rem, 4vw, 3.3rem)",
            "--chart-height": "480", "--chart-grid-opacity": "0.14", "--chart-grid-visible": "true",
            "--chart-grid-dash": "dot", "--chart-line-width": "2.7", "--chart-fill-opacity": "0.16",
            "--chart-font-size": "12", "--chart-hovermode": "x unified", "--chart-padding": "16px 12px 10px",
        },
    },
}
PERFIS_ORDER = list(PERFIS_VISUAIS)
DENSIDADES = {
    "auto": {"nome": "Padrão do perfil", "tokens": {}},
    "compacta": {"nome": "Compacta", "tokens": {
        "--layout-gap": "0.65rem", "--column-gap": "0.75rem", "--card-padding": "12px 14px",
        "--body-size": "0.875rem", "--body-leading": "1.55", "--control-height": "36px",
        "--control-padding": "6px 12px", "--section-margin": "0.9rem 0 0.4rem",
        "--watchlist-row-padding": "10px 16px", "--watchlist-row-height": "60px", "--table-cell-padding": "8px 12px",
        "--page-padding-x": "clamp(1rem, 2.3vw, 2rem)", "--form-padding": "16px", "--expander-height": "40px",
    }},
    "equilibrada": {"nome": "Equilibrada", "tokens": {
        "--layout-gap": "1rem", "--column-gap": "1rem", "--card-padding": "18px 20px",
        "--body-size": "0.94rem", "--body-leading": "1.65", "--control-height": "44px",
        "--control-padding": "9px 16px", "--section-margin": "1.25rem 0 0.5rem",
        "--watchlist-row-padding": "16px 20px", "--watchlist-row-height": "76px", "--table-cell-padding": "12px 14px",
        "--page-padding-x": "clamp(1.25rem, 3vw, 3rem)", "--form-padding": "20px", "--expander-height": "48px",
    }},
    "confortavel": {"nome": "Confortável", "tokens": {
        "--layout-gap": "1.25rem", "--column-gap": "1.2rem", "--card-padding": "22px 24px",
        "--body-size": "0.98rem", "--body-leading": "1.85", "--control-height": "46px",
        "--control-padding": "11px 18px", "--section-margin": "1.6rem 0 0.75rem",
        "--watchlist-row-padding": "20px 24px", "--watchlist-row-height": "86px", "--table-cell-padding": "15px 16px",
        "--page-padding-x": "clamp(1.25rem, 3.4vw, 3.5rem)", "--form-padding": "24px", "--expander-height": "52px",
    }},
}
PRESETS_APARENCIA = {
    "terminal": {"nome": "Terminal compacto", "perfil": "terminal", "paleta": "dark", "densidade": "auto", "desc": "Carbon · dados densos · IBM Plex"},
    "mesa": {"nome": "Mesa de análise", "perfil": "mesa", "paleta": "graphite", "densidade": "auto", "desc": "Graphite · painéis equilibrados · leitura contínua"},
    "caderno": {"nome": "Caderno quantitativo", "perfil": "caderno", "paleta": "papel", "densidade": "auto", "desc": "Papel · leitura espaçada · títulos serifados"},
    "radar": {"nome": "Radar visual", "perfil": "radar", "paleta": "navy", "densidade": "auto", "desc": "Navy · gráficos amplos · sinais em destaque"},
}


def _estado_validado(key: str, query_key: str, catalogo: dict, default: str) -> str:
    parametro = st.query_params.get(query_key)
    if isinstance(parametro, str) and parametro in catalogo:
        st.session_state[key] = parametro
    valor = st.session_state.get(key, default)
    return valor if isinstance(valor, str) and valor in catalogo else default


def get_perfil_ativo() -> str:
    return _estado_validado("_visual_profile", "profile", PERFIS_VISUAIS, "mesa")


def get_densidade_ativa() -> str:
    """Preferência do usuário; 'auto' usa a densidade do perfil atual."""
    return _estado_validado("_visual_density", "density", DENSIDADES, "auto")


def _set_estado(key: str, query_key: str, valor: str, catalogo: dict) -> None:
    if not isinstance(valor, str) or valor not in catalogo:
        return
    st.session_state[key] = valor
    st.query_params[query_key] = valor


def set_perfil(perfil: str) -> None:
    """Use em callback; fontes manuais continuam disponíveis ao trocar o perfil."""
    _set_estado("_visual_profile", "profile", perfil, PERFIS_VISUAIS)


def set_densidade(densidade: str) -> None:
    _set_estado("_visual_density", "density", densidade, DENSIDADES)


def get_perfil_tokens() -> dict[str, str]:
    perfil = PERFIS_VISUAIS[get_perfil_ativo()]
    densidade = get_densidade_ativa()
    efetiva = perfil["densidade"] if densidade == "auto" else densidade
    return {**perfil["tokens"], **DENSIDADES[efetiva]["tokens"]}


def aplicar_preset(preset_id: str) -> None:
    """Aplica composição, paleta e fontes juntas; chamar via on_click/on_change."""
    if not isinstance(preset_id, str) or preset_id not in PRESETS_APARENCIA:
        return
    from utils.themes import set_tema, resetar_fontes
    preset = PRESETS_APARENCIA[preset_id]
    set_perfil(preset["perfil"])
    set_tema(preset["paleta"])
    set_densidade(preset["densidade"])
    resetar_fontes()


def get_aparencia_estado() -> dict:
    from utils.themes import get_tema_ativo, get_fontes_ativas
    get_fontes_ativas()  # migra overrides legados para chaves que sobrevivem às páginas
    return {
        "perfil": get_perfil_ativo(), "paleta": get_tema_ativo(), "densidade": get_densidade_ativa(),
        "fontes": {parte: st.session_state.get(f"_appearance_font_{parte}", "") for parte in ("titulo", "ui", "data")},
    }


def restaurar_aparencia(estado: dict, *, preservar_url: bool = True) -> None:
    """Carrega preferências salvas; URLs explícitas têm prioridade por padrão."""
    if not isinstance(estado, dict):
        return
    from utils.themes import TEMAS, FONTES_TITULO, FONTES_UI, FONTES_DATA
    for campo, key, query_key, catalogo in (
        ("perfil", "_visual_profile", "profile", PERFIS_VISUAIS),
        ("paleta", "_theme", "theme", TEMAS),
        ("densidade", "_visual_density", "density", DENSIDADES),
    ):
        valor = estado.get(campo)
        if isinstance(valor, str) and valor in catalogo and not (preservar_url and st.query_params.get(query_key) in catalogo):
            st.session_state[key] = valor
            if not preservar_url:
                st.query_params[query_key] = valor
    fontes = estado.get("fontes", {})
    if isinstance(fontes, dict):
        for parte, catalogo in (("titulo", FONTES_TITULO), ("ui", FONTES_UI), ("data", FONTES_DATA)):
            fonte = fontes.get(parte)
            if isinstance(fonte, str) and fonte in catalogo:
                st.session_state[f"_appearance_font_{parte}"] = fonte
                st.session_state[f"_font_{parte}"] = fonte
            elif fonte == "":
                st.session_state.pop(f"_appearance_font_{parte}", None)
                st.session_state.pop(f"_font_{parte}", None)
