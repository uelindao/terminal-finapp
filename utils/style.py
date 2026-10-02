"""Interface compartilhada do FinTerminal; cores e fontes vêm do tema ativo."""
from pathlib import Path

import streamlit as st


def _interface_css() -> str:
    return Path(__file__).with_name("interface.css").read_text(encoding="utf-8")


def aplicar_tema():
    """Aplica a interface a cada renderização, inclusive login e estados de erro."""
    from utils.themes import get_tema_css
    st.markdown(get_tema_css(), unsafe_allow_html=True)
    st.markdown(f"<style>{_interface_css()}</style>", unsafe_allow_html=True)
    from utils.charts import aplicar_template_ativo
    aplicar_template_ativo()
