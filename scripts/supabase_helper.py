"""
supabase_helper.py
Helpers de conexao Supabase para scripts standalone (fora do Streamlit).
Usa SUPABASE_URL e SUPABASE_SERVICE_KEY de variaveis de ambiente.
"""

import os
import json
from datetime import datetime, timezone
from typing import Any


def get_client():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL e SUPABASE_SERVICE_KEY devem estar definidas "
            "como variaveis de ambiente ou no .env"
        )
    return create_client(url, key)


def upsert_fundamentals(ticker: str, dados: dict, source: str = "brapi") -> None:
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
