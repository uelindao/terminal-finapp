"""
supabase_helper.py
Helpers de banco e de segredos para scripts standalone (fora do Streamlit).
Grava na base local; o nome é herança da época do Supabase.
Segredos vêm de variáveis de ambiente e, quando ausentes, de .streamlit/secrets.toml.
"""

import os
import json
import tomllib
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from database.local_db import get_client

_SECRETS_TOML = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
# Segredos que o app guarda aninhados em seções do secrets.toml.
_ALIASES = {"BRAPI_TOKEN": ("brapi", "token")}


@lru_cache(maxsize=1)
def _secrets_toml() -> dict:
    """Lido direto, sem st.secrets: o ETL roda pelo Agendador, fora do Streamlit."""
    try:
        with _SECRETS_TOML.open("rb") as arquivo:
            return tomllib.load(arquivo)
    except FileNotFoundError:
        return {}


def _get_secret(*nomes: str) -> str:
    """Resolve uma chave em env vars, depois no secrets.toml (raiz e aliases)."""
    for nome in nomes:
        val = os.environ.get(nome, "")
        if val:
            return val
    segredos = _secrets_toml()
    for nome in nomes:
        val = segredos.get(nome)
        if not val and nome in _ALIASES:
            secao, chave = _ALIASES[nome]
            val = (segredos.get(secao) or {}).get(chave)
        if val:
            return val
    return ""


def upsert_fundamentals(ticker: str, dados: dict, source: str = "brapi",
                         data_quality_pct: float | None = None) -> None:
    """Faz upsert de dados fundamentalistas no fundamentals_cache."""
    sb = get_client()
    payload = {
        "ticker":        ticker,
        "dados_json":    json.dumps(dados),
        "data_source":   source,
        "data_quality":  dados.get("data_quality", 50),
        "last_validated": datetime.now(timezone.utc).isoformat(),
        "raw_json":      json.dumps(dados.get("_raw", {})),
    }
    if data_quality_pct is not None:
        payload["data_quality_pct"] = data_quality_pct
    sb.table("fundamentals_cache").upsert(
        payload, on_conflict="ticker"
    ).execute()


def upsert_price(ticker: str, price_data: dict) -> None:
    """Faz upsert de dados de preco na price_cache."""
    sb = get_client()
    payload = {
        "ticker":      ticker,
        "preco":       price_data.get("preco"),
        "var_1d":      price_data.get("var_1d"),
        "var_1m":      price_data.get("var_1m"),
        "var_12m":     price_data.get("var_12m"),
        "volume":      price_data.get("volume"),
        "max_52s":     price_data.get("max_52s"),
        "min_52s":     price_data.get("min_52s"),
        "rsi_14":      price_data.get("rsi_14"),
        "data_coleta": datetime.now(timezone.utc).date().isoformat(),
        "updated_at":  datetime.now(timezone.utc).isoformat(),
    }
    # Remove None values to avoid overwriting with null
    payload = {k: v for k, v in payload.items() if v is not None}
    sb.table("price_cache").upsert(
        payload, on_conflict="ticker"
    ).execute()


def upsert_price_history_batch(rows: list[dict], chunk_size: int = 500) -> int:
    """
    Upsert em lote de barras OHLCV diárias na tabela price_history.
    Cada `row` deve ter as chaves: ticker, data (YYYY-MM-DD), open, high, low, close, volume.
    Retorna o número total de linhas processadas.

    Faz chunking para evitar payload >1MB no Supabase. on_conflict (ticker,data)
    sobrescreve barras existentes (útil em revisões de close por split/dividendo).
    """
    if not rows:
        return 0
    sb = get_client()
    total = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        sb.table("price_history").upsert(
            chunk, on_conflict="ticker,data"
        ).execute()
        total += len(chunk)
    return total


def get_last_price_history_date(ticker: str) -> str | None:
    """
    Retorna a data (YYYY-MM-DD) da barra mais recente de `ticker` em price_history,
    ou None se não há dados. Usado para sync incremental — baixa só do dia seguinte
    em diante.
    """
    sb = get_client()
    try:
        res = sb.table("price_history").select("data").eq("ticker", ticker).order(
            "data", desc=True
        ).limit(1).execute()
        if res.data:
            return res.data[0]["data"]
    except Exception:
        pass
    return None


def upsert_dividend_history_batch(rows: list[dict], chunk_size: int = 500) -> int:
    """
    Upsert em lote de dividendos pagos na tabela dividend_history.
    Cada `row` deve ter: ticker, data_pagamento (YYYY-MM-DD), valor, tipo.
    on_conflict (ticker, data_pagamento) — idempotente.
    """
    if not rows:
        return 0
    sb = get_client()
    total = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        sb.table("dividend_history").upsert(
            chunk, on_conflict="ticker,data_pagamento"
        ).execute()
        total += len(chunk)
    return total


def get_last_dividend_date(ticker: str) -> str | None:
    """Retorna data do último dividendo cacheado para sync incremental."""
    sb = get_client()
    try:
        res = sb.table("dividend_history").select("data_pagamento").eq(
            "ticker", ticker
        ).order("data_pagamento", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]["data_pagamento"]
    except Exception:
        pass
    return None


def upsert_macro(indicator: str, value: float, label: str = "",
                  unit: str = "", source: str = "") -> None:
    """Faz upsert de um indicador macro na macro_cache."""
    sb = get_client()
    sb.table("macro_cache").upsert({
        "indicator":   indicator,
        "value":       value,
        "label":       label,
        "unit":        unit,
        "source":      source,
        "updated_at":  datetime.now(timezone.utc).isoformat(),
    }, on_conflict="indicator").execute()


def log_etl_start(job_name: str) -> int:
    """Registra inicio de uma execucao ETL e retorna o id."""
    sb = get_client()
    res = sb.table("etl_log").insert({
        "job_name": job_name,
        "status":   "running",
    }).execute()
    return res.data[0]["id"]


def log_etl_finish(log_id: int, ok: int = 0, fail: int = 0,
                    error_msg: str = "") -> None:
    """Atualiza o registro de execucao ETL com resultado."""
    sb = get_client()
    payload = {
        "status":       "error" if error_msg else "success",
        "tickers_ok":   ok,
        "tickers_fail": fail,
        "finished_at":  datetime.now(timezone.utc).isoformat(),
    }
    if error_msg:
        payload["error_msg"] = error_msg
    sb.table("etl_log").update(payload).eq("id", log_id).execute()


def get_all_tickers_from_watchlists() -> list[str]:
    """Retorna todos os tickers unicos de todas as watchlists de todos os usuarios."""
    sb = get_client()
    res = sb.table("watchlist_items").select("ticker").execute()
    tickers = list(set(r["ticker"] for r in (res.data or []) if r.get("ticker")))
    return sorted(tickers)
