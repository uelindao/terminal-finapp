"""
Ponto único de acesso ao banco.

O nome é herança da época do Supabase: `get_supabase()` tem ~100 chamadas e devolve
hoje o client da base local (database/local_db.py), com a mesma API fluente.
"""
from database.local_db import LocalClient, get_client


def get_supabase() -> LocalClient:
    return get_client()
