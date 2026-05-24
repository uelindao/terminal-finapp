"""
Cliente Supabase centralizado com singleton pattern.
A instância é criada uma única vez e reutilizada em toda a aplicação.

Ordem de busca das credenciais:
  1. st.secrets["SUPABASE_URL"]          (top-level — formato recomendado)
  2. st.secrets["supabase"]["SUPABASE_URL"] (seção [supabase] no secrets.toml)
  3. os.environ["SUPABASE_URL"]          (fallback fora do contexto Streamlit)
"""
import os
from supabase import create_client, Client
from utils.logger import get_logger

logger = get_logger(__name__)

_client: Client | None = None


def _ler_credenciais() -> tuple[str, str]:
    """
    Lê SUPABASE_URL e SUPABASE_KEY de st.secrets (top-level ou seção
    [supabase]) ou de variáveis de ambiente, nessa ordem de prioridade.
    Levanta RuntimeError se nenhuma fonte tiver as duas chaves.
    """
    url = key = ""

    try:
        import streamlit as st

        # 1ª tentativa: chaves top-level (formato documentado no README)
        url = st.secrets.get("SUPABASE_URL") or ""
        key = st.secrets.get("SUPABASE_KEY") or ""

        # 2ª tentativa: seção [supabase] (ex.: [supabase]\nSUPABASE_URL = "…")
        if not url or not key:
            sub = st.secrets.get("supabase") or {}
            url = url or (sub.get("SUPABASE_URL") or "")
            key = key or (sub.get("SUPABASE_KEY") or "")

    except Exception as e:
        logger.warning(f"[supabase_client] st.secrets indisponível: {e}")

    # 3ª tentativa: variáveis de ambiente (CI/CD, uso fora do Streamlit)
    url = url or os.environ.get("SUPABASE_URL", "")
    key = key or os.environ.get("SUPABASE_KEY", "")

    if not url or not key:
        raise RuntimeError(
            "Credenciais Supabase não encontradas.\n"
            "Adicione as seguintes linhas ao .streamlit/secrets.toml:\n\n"
            '  SUPABASE_URL = "https://<projeto>.supabase.co"\n'
            '  SUPABASE_KEY = "<service_role_key>"\n\n'
            "As chaves devem estar no nível raiz do arquivo, "
            "NÃO dentro de uma seção [supabase]."
        )

    return url, key


def get_supabase() -> Client:
    """
    Retorna o client Supabase (singleton).
    Lê as credenciais via _ler_credenciais() na primeira chamada.
    """
    global _client
    if _client is not None:
        return _client

    url, key = _ler_credenciais()
    _client = create_client(url, key)
    logger.info("[supabase_client] client Supabase inicializado com sucesso.")
    return _client
