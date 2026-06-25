"""
streamlit_app.py — entry point OPCIONAL com st.navigation (Streamlit 1.41+).

Este arquivo é uma alternativa ao Home.py para quem quer usar o roteamento
programático do Streamlit ao invés do auto-discovery de pages/*.

Em produção (Streamlit Cloud) o entry point continua sendo Home.py. Para
ativar este router, mude no painel da Streamlit Cloud:

    Settings → Main module file path → streamlit_app.py

Ou rode localmente:

    streamlit run streamlit_app.py

Benefícios da migração:
  - Ícones/títulos personalizados por página (mais bonito na sidebar)
  - URLs estáveis e explícitas (url_path) — preserva os links
    `/Research?research_ticker=X` hardcoded em Discovery (commit a21c5ae)
  - Grupos de páginas (Análise, Configurações) na sidebar
  - Roteamento programático

Compat preservada:
  - URLs padrão (/Research, /Discovery, etc) mantidas via url_path explícito
  - handle_ticker_nav() continua válido (usa query_params)
  - Tema/fontes injetados em aplicar_tema() antes de st.navigation
"""
import streamlit as st


# CSS global + tokens + template Plotly. Precisa rodar ANTES de st.navigation
# para que cada página herde os estilos. aplicar_tema() é idempotente.
from utils.style import aplicar_tema
aplicar_tema()


# ── Definição das páginas ────────────────────────────────────────────────────
# url_path explícito garante que <a href="/Research?...">, etc.,
# continuem funcionando após a migração.

pages = {
    "📊 Análise": [
        st.Page(
            "Home.py",
            title="Home",
            icon="🏠",
            default=True,
            url_path="",
        ),
        st.Page(
            "pages/1_Research.py",
            title="Research",
            icon="🔬",
            url_path="Research",
        ),
        st.Page(
            "pages/2_Discovery.py",
            title="Discovery",
            icon="🔍",
            url_path="Discovery",
        ),
        st.Page(
            "pages/3_Macro.py",
            title="Macro",
            icon="🌐",
            url_path="Macro",
        ),
        st.Page(
            "pages/4_Portfolio.py",
            title="Portfolio",
            icon="📈",
            url_path="Portfolio",
        ),
    ],
    "⚙️ Sistema": [
        st.Page(
            "pages/5_Configuracoes.py",
            title="Configurações",
            icon="⚙️",
            url_path="Configuracoes",
        ),
        # Backfill deixou de ser página própria — agora é uma aba em Configurações
        # (utils/backfill_view.render). Dashboard e Watchlists foram removidos.
    ],
}


# st.navigation renderiza a sidebar de navegação automaticamente. A página
# escolhida é retornada como st.Page — chamar .run() executa o arquivo dela.
pg = st.navigation(pages)
pg.run()
