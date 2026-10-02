"""Preferências de leitura: callbacks, links e navegação sem serviços externos."""
from textwrap import dedent

from streamlit.testing.v1 import AppTest


def app(source):
    test = AppTest.from_string(dedent(source), default_timeout=15).run()
    assert not test.exception, [item.message for item in test.exception]
    return test


def test_profile_palette_and_density_change_independently():
    at = app('''
        import streamlit as st
        from utils.themes import render_theme_switcher_sidebar, get_tema_ativo
        from utils.appearance import get_perfil_ativo, get_densidade_ativa, set_densidade
        render_theme_switcher_sidebar()
        st.button("Compactar", on_click=set_densidade, args=("compacta",))
        st.text(f"{get_perfil_ativo()}|{get_tema_ativo()}|{get_densidade_ativa()}")
    ''')
    at.selectbox(key="_appearance_sidebar_profile").set_value("caderno").run()
    assert not at.exception
    assert at.text[0].value == "caderno|dark|auto"
    at.selectbox(key="_theme_selectbox").set_value("light").run()
    at.button[0].click().run()
    assert not at.exception
    assert at.text[0].value == "caderno|light|compacta"
    at.run()
    assert at.selectbox(key="_appearance_sidebar_profile").value == "caderno"
    assert at.selectbox(key="_theme_selectbox").value == "light"


def test_custom_font_survives_widget_cleanup_on_another_page():
    at = app('''
        import streamlit as st
        from utils.themes import get_fontes_ativas, FONTES_TITULO
        def font_changed():
            st.session_state["_appearance_font_titulo"] = st.session_state["_font_titulo"]
        def leave_settings():
            st.session_state["reading_page"] = True
        if not st.session_state.get("reading_page"):
            st.selectbox("Título", [""] + list(FONTES_TITULO), key="_font_titulo", on_change=font_changed)
        st.button("Ler ativo", on_click=leave_settings)
        st.text(get_fontes_ativas()["titulo"])
    ''')
    at.selectbox[0].set_value("source_serif").run()
    at.button[0].click().run()
    at.run()
    assert not at.exception
    assert not at.selectbox
    assert "_font_titulo" not in at.session_state
    assert at.text[0].value == "source_serif"
    assert at.session_state["_appearance_font_titulo"] == "source_serif"


def test_preset_resets_custom_fonts_and_synchronizes_existing_sidebar():
    at = app('''
        import streamlit as st
        from utils.themes import render_theme_switcher_sidebar, get_fontes_ativas
        from utils.appearance import aplicar_preset, get_aparencia_estado
        render_theme_switcher_sidebar()
        def set_custom():
            st.session_state["_font_titulo"] = "syne"
            st.session_state["_appearance_font_titulo"] = "syne"
        st.button("Fonte manual", on_click=set_custom)
        st.button("Aplicar caderno", on_click=aplicar_preset, args=("caderno",))
        st.text(get_fontes_ativas()["titulo"])
        st.json(get_aparencia_estado())
    ''')
    at.button[0].click().run()
    assert at.text[0].value == "syne"
    at.button[1].click().run()
    assert not at.exception
    assert at.text[0].value == "source_serif"
    assert "_appearance_font_titulo" not in at.session_state
    assert at.selectbox(key="_appearance_sidebar_profile").value == "caderno"
    assert at.selectbox(key="_theme_selectbox").value == "papel"


def test_explicit_link_preferences_override_restored_preferences():
    at = AppTest.from_string(dedent('''
        import streamlit as st
        from utils.appearance import restaurar_aparencia, get_aparencia_estado
        restaurar_aparencia({"perfil": "caderno", "paleta": "papel", "densidade": "auto"})
        state = get_aparencia_estado()
        st.text(f"{state['perfil']}|{state['paleta']}|{state['densidade']}")
    '''))
    at.query_params.update(profile="terminal", theme="light", density="compacta")
    at.run()
    assert not at.exception
    assert at.text[0].value == "terminal|light|compacta"


def test_malformed_import_does_not_replace_valid_preferences():
    at = app('''
        import streamlit as st
        from utils.appearance import set_perfil, restaurar_aparencia, get_aparencia_estado
        set_perfil("radar")
        restaurar_aparencia({"perfil": ["unknown"], "paleta": {}, "densidade": 7,
                            "fontes": {"titulo": [], "ui": None, "data": "unknown"}}, preservar_url=False)
        state = get_aparencia_estado()
        st.text(f"{state['perfil']}|{state['paleta']}|{state['densidade']}")
    ''')
    assert at.text[0].value == "radar|dark|auto"
