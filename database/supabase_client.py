"""
Cliente Supabase centralizado com singleton pattern.
A instância é criada uma única vez e reutilizada em toda a aplicação.
"""
from supabase import create_client, Client
from utils.logger import get_logger

logger = get_logger(__name__)

_client: Client | None = None


def get_supabase() -> Client:
    """
    Retorna o client Supabase (singleton).
    Lê as credenciais de st.secrets, com fallback para variáveis de ambiente.
    """
    global _client
    if _client is not None:
        return _client

    try:
        import streamlit as st
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        # Fallback para variáveis de ambiente (uso fora do contexto Streamlit)
        import os
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            raise RuntimeError(
                "Credenciais Supabase não encontradas. "
                "Configure SUPABASE_URL e SUPABASE_KEY em .streamlit/secrets.toml."
            )

    _client = create_client(url, key)
    logger.info("[supabase_client] client Supabase inicializado.")
    return _client
