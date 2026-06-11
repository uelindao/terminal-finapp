"""
utils/macro_supabase.py
Persistência de séries históricas macro no Supabase.

Resolve o problema de "sem dados" em fins de semana / cold-start:
  1. Em dias úteis, puxar_historico_mestre() busca ao vivo (BCB / FRED)
     e salva o resultado nesta camada (cache-aside).
  2. Se a API falhar (fim de semana, timeout, manutenção), o app lê
     o último snapshot bem-sucedido do Supabase.

Tabela necessária (rodar 1x no SQL Editor do Supabase):
  → veja scripts/migrations/create_macro_snapshots.sql

Formato de armazenamento:
  DataFrame.to_json(orient='split') → text → jsonb
  Reconstrói via pd.read_json(orient='split', convert_dates=True)
"""

from __future__ import annotations

import json
import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from utils.logger import get_logger

logger = get_logger(__name__)

# ─── cliente Supabase (reutiliza o singleton de api_cache) ────────────────────

@st.cache_resource
def _sb():
    """Retorna o cliente Supabase ou None se não configurado."""
    try:
        from supabase import create_client
        url      = st.secrets.get("supabase", {}).get("url", "")
        anon_key = st.secrets.get("supabase", {}).get("anon_key", "")
        if not url or not anon_key:
            return None
        return create_client(url, anon_key)
    except Exception as e:
        logger.warning(f"[macro_supabase] Supabase não disponível: {e}")
        return None


# ─── serialização ─────────────────────────────────────────────────────────────

def _df_to_json(df: pd.DataFrame) -> str:
    """
    Serializa um DataFrame com DatetimeIndex para JSON (orient='split').
    O índice é convertido para string ISO para garantir portabilidade.
    """
    df2 = df.copy()
    if isinstance(df2.index, pd.DatetimeIndex):
        df2.index = df2.index.strftime("%Y-%m-%d")
    return df2.to_json(orient="split", date_format="iso")


def _json_to_df(payload: str) -> pd.DataFrame:
    """
    Reconstrói um DataFrame a partir de JSON serializado com orient='split'.
    Reconverte a coluna de índice para DatetimeIndex.
    """
    df = pd.read_json(payload, orient="split")
    try:
        df.index = pd.to_datetime(df.index)
        df.index.name = None
    except Exception:
        pass
    return df


# ─── operações principais ─────────────────────────────────────────────────────

def salvar_snapshot(origem: str, df: pd.DataFrame) -> bool:
    """
    Salva o DataFrame de uma origem (ex.: 'bcb_br', 'fred_global') no Supabase.
    Faz upsert por 'origem' — substitui o snapshot anterior da mesma origem.
    Retorna True em sucesso, False em falha silenciosa.
    """
    if df is None or df.empty:
        return False

    sb = _sb()
    if sb is None:
        return False

    try:
        payload_json = _df_to_json(df)
        sb.table("macro_snapshots").upsert(
            {
                "origem":      origem,
                "payload":     payload_json,
                "n_linhas":    len(df),
                "n_colunas":   df.shape[1],
                "data_inicio": str(df.index.min().date()) if not df.empty else None,
                "data_fim":    str(df.index.max().date()) if not df.empty else None,
                "updated_at":  datetime.datetime.utcnow().isoformat(),
            },
            on_conflict="origem",
        ).execute()
        logger.info(f"[macro_supabase] snapshot '{origem}' salvo ({len(df)} linhas).")
        return True
    except Exception as e:
        logger.warning(f"[macro_supabase] salvar_snapshot '{origem}' falhou: {e}")
        return False


def carregar_snapshot(origem: str, max_age_days: int = 7) -> Optional[pd.DataFrame]:
    """
    Carrega o snapshot mais recente de uma origem do Supabase.
    Retorna None se não encontrar, expirado (> max_age_days) ou Supabase offline.
    """
    sb = _sb()
    if sb is None:
        return None

    try:
        cutoff = (
            datetime.datetime.utcnow() - datetime.timedelta(days=max_age_days)
        ).isoformat()

        resp = (
            sb.table("macro_snapshots")
            .select("payload, updated_at, n_linhas")
            .eq("origem", origem)
            .gte("updated_at", cutoff)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )

        if not resp.data:
            logger.info(f"[macro_supabase] sem snapshot válido para '{origem}'.")
            return None

        row = resp.data[0]
        payload = row["payload"]
        # payload pode vir como string ou como dict (se Supabase desserializou)
        if isinstance(payload, dict):
            payload = json.dumps(payload)

        df = _json_to_df(payload)
        updated = row.get("updated_at", "?")
        logger.info(
            f"[macro_supabase] snapshot '{origem}' carregado do Supabase "
            f"({row['n_linhas']} linhas, atualizado: {updated[:10]})."
        )
        return df

    except Exception as e:
        logger.warning(f"[macro_supabase] carregar_snapshot '{origem}' falhou: {e}")
        return None


def snapshot_existe(origem: str) -> bool:
    """Verifica rapidamente se existe um snapshot para a origem (sem carregar payload)."""
    sb = _sb()
    if sb is None:
        return False
    try:
        resp = (
            sb.table("macro_snapshots")
            .select("origem")
            .eq("origem", origem)
            .limit(1)
            .execute()
        )
        return bool(resp.data)
    except Exception:
        return False


def listar_snapshots() -> list[dict]:
    """
    Retorna metadados de todos os snapshots salvos (sem o payload pesado).
    Útil para diagnóstico / página de admin.
    """
    sb = _sb()
    if sb is None:
        return []
    try:
        resp = (
            sb.table("macro_snapshots")
            .select("origem, n_linhas, n_colunas, data_inicio, data_fim, updated_at")
            .order("updated_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.warning(f"[macro_supabase] listar_snapshots falhou: {e}")
        return []


# ─── Fear & Greed Cache ──────────────────────────────────────────────────────

def salvar_fear_greed(market: str, score: int, label: str, componentes: dict) -> bool:
    """
    Salva o resultado do Fear & Greed Index no Supabase.
    market: 'us' ou 'br'
    Retorna True em sucesso, False em falha silenciosa.
    """
    sb = _sb()
    if sb is None:
        return False

    try:
        sb.table("fear_greed_cache").upsert(
            {
                "market":       market,
                "score":        int(score),
                "label":        label,
                "componentes":  componentes,
            },
            on_conflict="market",
        ).execute()
        logger.info(f"[macro_supabase] fear_greed '{market}' salvo (score={score}).")
        return True
    except Exception as e:
        logger.warning(f"[macro_supabase] salvar_fear_greed '{market}' falhou: {e}")
        return False


def carregar_fear_greed(market: str, max_age_hours: int = 4) -> dict | None:
    """
    Carrega o Fear & Greed Index do cache do Supabase.
    Retorna None se não encontrar, expirado (> max_age_hours) ou Supabase offline.
    """
    sb = _sb()
    if sb is None:
        return None

    try:
        cutoff = (
            datetime.datetime.utcnow() - datetime.timedelta(hours=max_age_hours)
        ).isoformat()

        resp = (
            sb.table("fear_greed_cache")
            .select("score, label, componentes, updated_at")
            .eq("market", market)
            .gte("updated_at", cutoff)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )

        if not resp.data:
            return None

        row = resp.data[0]
        componentes = row.get("componentes", {})
        if isinstance(componentes, str):
            componentes = json.loads(componentes)

        return {
            "score":       row["score"],
            "label":       row["label"],
            "componentes": componentes,
        }

    except Exception as e:
        logger.warning(f"[macro_supabase] carregar_fear_greed '{market}' falhou: {e}")
        return None
