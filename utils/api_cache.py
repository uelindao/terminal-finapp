"""
utils/api_cache.py
Camada de cache persistente via Supabase para dados de APIs externas.

Resolve dois problemas do Streamlit Community Cloud:
1. Rate limits de APIs gratuitas (Alpha Vantage: 25 req/dia)
2. Perda de cache entre redeployos (st.cache_data e volátil)

Politica de max_age diferenciada por tipo de dado:
- Trimestrais historicos fechados: 3650 dias (nunca mudam)
- Trimestre mais recente: 7 dias (pode ter revisao)
- Snapshot atual (multiplos, preco): 1 dia
- Dados macro (Selic, VIX): 1 dia
"""
from __future__ import annotations

import hashlib
import time
import datetime
from typing import Callable, Any

import streamlit as st
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_AGE = {
    "historico_trimestral": 3650,
    "trimestre_recente":       7,
    "snapshot":                1,
    "macro":                   1,
}


@st.cache_resource
def _get_supabase_client():
    """
    Retorna cliente Supabase. Cache de resource (singleton por sessao).
    Retorna None se nao configurado — o cache fica desabilitado
    e o app funciona normalmente sem Supabase.
    """
    try:
        from supabase import create_client
        url      = st.secrets.get("supabase", {}).get("url", "")
        anon_key = st.secrets.get("supabase", {}).get("anon_key", "")
        if not url or not anon_key:
            return None
        return create_client(url, anon_key)
    except Exception as e:
        logger.warning(f"[api_cache] Supabase nao configurado: {e}")
        return None


def _periodo_from_date(date_str: str) -> str:
    try:
        dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
        q  = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{q}"
    except Exception:
        return date_str[:7]


def _is_periodo_fechado(periodo: str | None) -> bool:
    if not periodo:
        return False
    try:
        parts = periodo.split("-Q")
        if len(parts) != 2:
            return False
        ano, q = int(parts[0]), int(parts[1])
        hoje = datetime.date.today()
        ano_atual, q_atual = hoje.year, (hoje.month - 1) // 3 + 1
        if ano < ano_atual:
            return True
        if ano == ano_atual and q < q_atual:
            return True
        return False
    except Exception:
        return False


def get_from_cache(
    ticker:   str,
    provider: str,
    endpoint: str,
    periodo:  str | None = None,
    max_age_days: int | None = None,
) -> dict | list | None:
    """
    Busca dado no cache Supabase.
    Retorna o dado (dict/list) se existir e estiver dentro do max_age.
    Retorna None se nao existir, expirado ou Supabase offline.
    """
    sb = _get_supabase_client()
    if sb is None:
        return None

    if max_age_days is None:
        if periodo is None:
            max_age_days = MAX_AGE["snapshot"]
        elif _is_periodo_fechado(periodo):
            max_age_days = MAX_AGE["historico_trimestral"]
        else:
            max_age_days = MAX_AGE["trimestre_recente"]

    try:
        cutoff = (
            datetime.datetime.utcnow()
            - datetime.timedelta(days=max_age_days)
        ).isoformat()

        query = (
            sb.table("api_cache")
            .select("data, updated_at")
            .eq("ticker",   ticker.upper())
            .eq("provider", provider)
            .eq("endpoint", endpoint)
            .gte("updated_at", cutoff)
        )

        if periodo is not None:
            query = query.eq("periodo", periodo)
        else:
            query = query.is_("periodo", "null")

        resp = query.limit(1).execute()

        if resp.data:
            return resp.data[0]["data"]
        return None

    except Exception as e:
        logger.warning(f"[api_cache] get falhou ({ticker}/{endpoint}): {e}")
        return None


def save_to_cache(
    ticker:   str,
    provider: str,
    endpoint: str,
    data:     dict | list,
    periodo:  str | None = None,
) -> bool:
    """
    Salva dado no cache Supabase via upsert.
    Retorna True se salvou com sucesso.
    """
    sb = _get_supabase_client()
    if sb is None:
        return False

    try:
        payload = {
            "ticker":   ticker.upper(),
            "provider": provider,
            "endpoint": endpoint,
            "periodo":  periodo,
            "data":     data,
        }
        sb.table("api_cache").upsert(
            payload,
            on_conflict="ticker,provider,endpoint,periodo"
        ).execute()
        return True
    except Exception as e:
        logger.warning(f"[api_cache] save falhou ({ticker}/{endpoint}): {e}")
        return False


def fetch_with_cache(
    ticker:      str,
    provider:    str,
    endpoint:    str,
    fetch_func:  Callable[[], Any],
    periodo:     str | None = None,
    max_age_days: int | None = None,
) -> Any:
    """
    Busca dado com cache-aside pattern:
    1. Tenta cache Supabase
    2. Se miss/expirado: chama fetch_func()
    3. Salva resultado no cache
    4. Retorna dado
    """
    cached = get_from_cache(ticker, provider, endpoint, periodo, max_age_days)
    if cached is not None:
        logger.debug(f"[api_cache] HIT {ticker}/{provider}/{endpoint}")
        return cached

    logger.info(f"[api_cache] MISS {ticker}/{provider}/{endpoint} — buscando API")
    try:
        resultado = fetch_func()
    except Exception as e:
        logger.warning(f"[api_cache] fetch_func falhou: {e}")
        return None

    if resultado is None:
        return None

    save_to_cache(ticker, provider, endpoint, resultado, periodo)
    return resultado


def get_todos_do_provider(
    ticker:   str,
    provider: str,
    endpoint: str,
) -> list[dict]:
    """
    Busca TODOS os periodos trimestrais de um ativo/provider/endpoint
    do cache Supabase.

    Retorna lista de {periodo, data} ordenada do mais antigo ao mais recente.
    """
    sb = _get_supabase_client()
    if sb is None:
        return []

    try:
        resp = (
            sb.table("api_cache")
            .select("periodo, data, updated_at")
            .eq("ticker",   ticker.upper())
            .eq("provider", provider)
            .eq("endpoint", endpoint)
            .not_.is_("periodo", "null")
            .order("periodo", desc=False)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.warning(f"[api_cache] get_todos falhou: {e}")
        return []


# ── Rotacao de chaves Alpha Vantage ───────────────────────────────────────────

class AlphaVantageKeyRotator:
    """
    Gerencia rotacao de chaves Alpha Vantage respeitando limite de 25 req/dia.
    Usa Supabase para persistir contagem entre sessoes.
    """

    LIMITE_DIARIO = 25

    def __init__(self):
        keys = []
        try:
            raw = st.secrets.get("alpha_vantage", {})
            plural = raw.get("api_keys", [])
            singular = raw.get("api_key", "")
            if isinstance(plural, list):
                keys.extend(plural)
            if singular and singular not in keys:
                keys.append(singular)
        except Exception:
            pass
        self.keys = keys

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _get_uso_hoje(self, key: str) -> int:
        sb = _get_supabase_client()
        if sb is None:
            return 0
        try:
            resp = (
                sb.table("api_key_usage")
                .select("n_requests")
                .eq("provider",      "alpha_vantage")
                .eq("api_key_hash",  self._hash_key(key))
                .eq("data_uso",      str(datetime.date.today()))
                .execute()
            )
            if resp.data:
                return int(resp.data[0]["n_requests"])
            return 0
        except Exception:
            return 0

    def _incrementar_uso(self, key: str) -> None:
        sb = _get_supabase_client()
        if sb is None:
            return
        try:
            sb.table("api_key_usage").upsert(
                {
                    "provider":     "alpha_vantage",
                    "api_key_hash": self._hash_key(key),
                    "data_uso":     str(datetime.date.today()),
                    "n_requests":   self._get_uso_hoje(key) + 1,
                },
                on_conflict="provider,api_key_hash,data_uso"
            ).execute()
        except Exception:
            pass

    def get_available_key(self) -> str | None:
        for key in self.keys:
            uso = self._get_uso_hoje(key)
            if uso < self.LIMITE_DIARIO:
                return key
        logger.warning(
            "[av] todas as chaves atingiram o limite diario de "
            f"{self.LIMITE_DIARIO} requests"
        )
        return None

    def request(
        self,
        params: dict,
        sleep_between: float = 2.0,
    ) -> dict:
        import requests as _req
        AV_BASE = "https://www.alphavantage.co/query"

        for key in self.keys:
            uso = self._get_uso_hoje(key)
            if uso >= self.LIMITE_DIARIO:
                continue

            try:
                p = dict(params)
                p["apikey"] = key
                resp = _req.get(AV_BASE, params=p, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                if any(
                    phrase in str(data)
                    for phrase in [
                        "Limit Reached",
                        "Thank you for using Alpha Vantage",
                        "Our standard API rate limit",
                    ]
                ):
                    logger.warning(
                        f"[av] chave {self._hash_key(key)} atingiu limite"
                    )
                    self._incrementar_uso(key)
                    time.sleep(sleep_between)
                    continue

                if "Error Message" in data:
                    logger.warning(f"[av] erro: {data['Error Message'][:80]}")
                    return {}

                self._incrementar_uso(key)
                return data

            except Exception as e:
                logger.warning(f"[av] request falhou: {e}")
                time.sleep(sleep_between)
                continue

        return {}


@st.cache_resource
def get_av_rotator() -> AlphaVantageKeyRotator:
    return AlphaVantageKeyRotator()
