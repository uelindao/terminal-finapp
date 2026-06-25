"""
utils/st_fallback.py
====================
Fallback do Streamlit para módulos compartilhados (utils/) que também rodam no
ETL (GitHub Actions, sem `streamlit` instalado).

Antes este shim estava copiado em 4 módulos (health_engine, macro_state,
inflation_sectoral, sector_scorecard). Centralizado aqui.

Uso:
    from utils.st_fallback import st, ST_AVAILABLE

Quando o Streamlit existe, `st` é o módulo real. Quando não, `st` é um stub
no-op: `@st.cache_data`/`@st.cache_resource` viram decoradores transparentes e
`st.session_state.get(...)` devolve o default.
"""
try:
    import streamlit as st          # noqa: F401  (reexportado)
    ST_AVAILABLE = True
except ImportError:
    class _NoOpCache:
        """Decorador transparente — substitui st.cache_data/cache_resource."""
        def __call__(self, *a, **kw):
            return lambda f: f

    class _FakeSt:
        cache_data = _NoOpCache()
        cache_resource = _NoOpCache()

        class session_state:
            @staticmethod
            def get(*a, **kw):
                return kw.get('default', a[1] if len(a) > 1 else {})

    st = _FakeSt()
    ST_AVAILABLE = False
