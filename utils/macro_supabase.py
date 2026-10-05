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
from io import StringIO
from typing import Optional

import pandas as pd
import streamlit as st

from utils.logger import get_logger

logger = get_logger(__name__)

# ─── cliente Supabase (reutiliza o singleton de api_cache) ────────────────────

@st.cache_resource
def _sb():
    """Reutiliza o mesmo cliente e formatos de credenciais do restante do app."""
    try:
        from database.supabase_client import get_supabase
        return get_supabase()
    except Exception as exc:
        logger.warning("[macro_supabase] cliente indisponível: %s", type(exc).__name__)
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
    df = pd.read_json(StringIO(payload), orient="split")
    try:
        df.index = pd.to_datetime(df.index)
        df.index.name = None
    except Exception as _e_dt:
        # snapshot legado com índice não-datetime; preserva como está
        logger.debug(f"[macro_supabase] não foi possível converter índice para datetime: {_e_dt}")
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
        df.attrs["coletado_em"] = updated
        df.attrs["origem"] = origem
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


# ─── Slope da curva de juros US ─────────────────────────────────────────────

def buscar_slope_curva(origem: str = "fred_global") -> Optional[pd.DataFrame]:
    """
    Retorna DataFrame com colunas [data, t10y, t2y, t3m, slope_10y_2y, slope_10y_3m].
    Lê o snapshot persistido pelo sync_macro. Retorna None se não houver dados.
    """
    try:
        snap = carregar_snapshot(origem, max_age_days=30)
        if snap is None or snap.empty:
            return None

        df = pd.DataFrame()
        if "DGS10" in snap.columns:
            df["t10y"] = snap["DGS10"]
        if "DGS2" in snap.columns:
            df["t2y"] = snap["DGS2"]
        if "DGS3MO" in snap.columns:
            df["t3m"] = snap["DGS3MO"]

        if df.empty or "t10y" not in df.columns or "t2y" not in df.columns:
            return None

        df["slope_10y_2y"] = df["t10y"] - df["t2y"]
        if "t3m" in df.columns:
            df["slope_10y_3m"] = df["t10y"] - df["t3m"]

        df.index.name = "data"
        return df.reset_index()

    except Exception:
        logger.error("falha ao reconstruir slope da curva", exc_info=True)
        return None


# ─── Observações versionadas: coexistem com o snapshot de apresentação ───────
# Sem vintages da fonte, coletado_em delimita o que podemos comprovar. Nunca
# trate um backfill atual como informação que o terminal possuía anos atrás.
_COLUNAS_OBSERVACOES = ["serie_id", "referencia_em", "disponivel_em", "coletado_em",
    "valor", "fonte", "unidade", "disponibilidade_base", "vintage_base"]


def preparar_observacoes_versionadas(serie_id: str, serie: pd.Series, *, fonte: str,
    unidade: str, disponibilidade_base: str = "atraso_conservador_assumido",
    atraso_dias: int = 0, mes_fechado: bool = False, publicado_em: pd.Series | None = None,
    coletado_em=None
) -> list[dict]:
    """Serialização pura para append-only; datas estimadas não viram publicações reais.

    A versão é a que foi observada na coleta, sem afirmar que corresponde à
    primeira divulgação do período. Calendário informado precisa vir da fonte.
    """
    import hashlib
    import math
    if serie is None or serie.empty:
        return []
    coleta = pd.Timestamp(coletado_em or datetime.datetime.now(datetime.timezone.utc))
    coleta = coleta.tz_localize("UTC") if coleta.tzinfo is None else coleta.tz_convert("UTC")
    rows = []
    for ref, val in serie.items():
        try:
            valor = float(val)
            if not math.isfinite(valor):
                continue
            referencia = pd.Timestamp(ref)
            referencia = referencia.tz_localize("UTC") if referencia.tzinfo is None else referencia.tz_convert("UTC")
            if publicado_em is not None:
                publicado = publicado_em.get(ref)
                if publicado is None or pd.isna(publicado):
                    continue
                disponivel = pd.Timestamp(publicado)
                disponivel = disponivel.tz_localize("UTC") if disponivel.tzinfo is None else disponivel.tz_convert("UTC")
                base = "divulgacao_informada"
            else:
                disponivel = coleta if disponibilidade_base == "observada_na_coleta" else referencia + (pd.offsets.MonthEnd(0) if mes_fechado else pd.Timedelta(0)) + pd.Timedelta(days=atraso_dias)
                base = disponibilidade_base
            row = {"serie_id": str(serie_id), "referencia_em": referencia.strftime("%Y-%m-%d"),
                "disponivel_em": disponivel.isoformat(), "coletado_em": coleta.isoformat(),
                "valor": valor, "fonte": str(fonte), "unidade": str(unidade),
                "disponibilidade_base": base, "vintage_base": "observada_na_coleta"}
            row["observacao_hash"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
            rows.append(row)
        except (TypeError, ValueError, OverflowError):
            continue
    return rows


def selecionar_observacoes_conhecidas(rows, *, as_of=None, todas_versoes: bool = False) -> pd.DataFrame:
    """Escolhe somente versões coletadas E disponíveis até o corte informado."""
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=_COLUNAS_OBSERVACOES)
    for coluna in ("referencia_em", "disponivel_em", "coletado_em"):
        df[coluna] = pd.to_datetime(df[coluna], utc=True, errors="coerce")
    df = df.dropna(subset=["referencia_em", "disponivel_em", "coletado_em", "valor"])
    if as_of is not None:
        corte = pd.Timestamp(as_of)
        corte = corte.tz_localize("UTC") if corte.tzinfo is None else corte.tz_convert("UTC")
        df = df[(df["coletado_em"] <= corte) & (df["disponivel_em"] <= corte)]
    df = df.sort_values(["referencia_em", "coletado_em"])
    if not todas_versoes:
        df = df.drop_duplicates(["serie_id", "referencia_em"], keep="last")
    df.attrs["metodologia"] = {"vintage": "observada_na_coleta", "backfill_point_in_time": False,
        "corte": str(as_of) if as_of is not None else None}
    return df.reset_index(drop=True)


def _ler_fallback_versionado(sb, serie_id: str):
    """Histórico preservado na tabela existente; None distingue falha de vazio."""
    try:
        resposta = sb.table("macro_snapshots").select("payload").eq(
            "origem", f"vintage_{serie_id}").limit(1).execute()
        if not resposta.data:
            return []
        payload = resposta.data[0]["payload"]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        if not isinstance(payload, dict) or payload.get("schema") != "macro_observations_fallback_v1":
            return None  # jamais substituir um payload desconhecido
        return payload.get("observacoes", [])
    except Exception:
        return None


def _filtrar_referencias(df, inicio=None, fim=None):
    if inicio is not None:
        df = df[df["referencia_em"] >= pd.to_datetime(inicio, utc=True)]
    if fim is not None:
        df = df[df["referencia_em"] <= pd.to_datetime(fim, utc=True)]
    return df


def carregar_observacoes_versionadas(serie_id: str, inicio=None, fim=None, as_of=None,
    limite: int = 5000, *, cliente=None, todas_versoes: bool = False
) -> pd.DataFrame:
    """Versionamento prospectivo, compatível com Cloud sem nova tabela obrigatória.

    Prefere macro_observations e também preserva versões previamente gravadas no
    fallback macro_snapshots. as_of requer disponibilidade E coleta até o corte.
    O fallback é um documento append-only lógico, atualizado por um único ETL;
    a migration opcional oferece inserção atômica e imutabilidade no banco.
    """
    vazio = pd.DataFrame(columns=_COLUNAS_OBSERVACOES)
    sb = cliente if cliente is not None else _sb()
    if sb is None:
        vazio.attrs["armazenamento"] = "nao_configurado"
        return vazio
    rows, tabela_disponivel = [], True
    limite = max(1, min(int(limite), 50000))
    try:
        for offset in range(0, limite, 1000):
            query = sb.table("macro_observations").select(",".join(_COLUNAS_OBSERVACOES)).eq("serie_id", serie_id)
            if inicio is not None:
                query = query.gte("referencia_em", pd.Timestamp(inicio).strftime("%Y-%m-%d"))
            if fim is not None:
                query = query.lte("referencia_em", pd.Timestamp(fim).strftime("%Y-%m-%d"))
            if as_of is not None:
                corte = pd.Timestamp(as_of)
                corte = corte.tz_localize("UTC") if corte.tzinfo is None else corte.tz_convert("UTC")
                query = query.lte("coletado_em", corte.isoformat()).lte("disponivel_em", corte.isoformat())
            quantidade = min(1000, limite - offset)
            lote = query.order("coletado_em", desc=True).order("referencia_em", desc=True).range(
                offset, offset + quantidade - 1).execute().data or []
            rows.extend(lote)
            if len(lote) < quantidade:
                break
    except Exception:
        tabela_disponivel = False
        rows = []
    fallback = _ler_fallback_versionado(sb, serie_id)
    if not tabela_disponivel and fallback is None:
        vazio.attrs["armazenamento"] = "indisponivel"
        return vazio
    rows.extend(fallback or [])
    result = selecionar_observacoes_conhecidas(rows, as_of=as_of, todas_versoes=True)
    result = _filtrar_referencias(result, inicio, fim)
    result = result.drop_duplicates([c for c in _COLUNAS_OBSERVACOES if c in result])
    result = result.sort_values("coletado_em").tail(limite)
    result = selecionar_observacoes_conhecidas(result, as_of=as_of, todas_versoes=todas_versoes)
    result.attrs["armazenamento"] = "versionado" if tabela_disponivel else "fallback_macro_snapshots"
    result.attrs["tabela_disponivel"] = tabela_disponivel
    result.attrs["limite_atingido"] = len(rows) >= limite
    result.attrs["fallback_nao_transacional"] = bool(fallback) or not tabela_disponivel
    return result


def _fingerprint_observacoes(rows):
    import hashlib
    conteudo = []
    for row in rows:
        ponto = {k: v for k, v in row.items() if k not in {"coletado_em", "observacao_hash"}}
        if ponto.get("disponibilidade_base") == "observada_na_coleta":
            ponto.pop("disponivel_em", None)
        conteudo.append(ponto)
    return hashlib.sha256(json.dumps(sorted(conteudo, key=lambda r: r["referencia_em"]),
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _ler_indice_versionado(sb, serie_id):
    try:
        resposta = sb.table("macro_snapshots").select("payload").eq(
            "origem", f"vintage_meta_{serie_id}").limit(1).execute()
        if not resposta.data:
            return {}
        payload = resposta.data[0]["payload"]
        return json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        return {}


def _salvar_indice_versionado(sb, serie_id, fingerprint, armazenamento, rows):
    # Índice pequeno evita reler vintages inteiras a cada ETL2h quando a série
    # não mudou. Só gravado após confirmação de persistência dos valores.
    try:
        referencias = [r["referencia_em"] for r in rows]
        sb.table("macro_snapshots").upsert({"origem": f"vintage_meta_{serie_id}",
            "payload": json.dumps({"fingerprint": fingerprint, "armazenamento": armazenamento}),
            "n_linhas": 0, "n_colunas": 0, "data_inicio": min(referencias),
            "data_fim": max(referencias), "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
            on_conflict="origem").execute()
    except Exception:
        logger.debug("índice auxiliar de vintage indisponível")


def salvar_observacoes_versionadas(serie_id: str, serie: pd.Series, *, fonte: str,
    unidade: str, disponibilidade_base: str = "atraso_conservador_assumido",
    atraso_dias: int = 0, mes_fechado: bool = False, publicado_em=None,
    coletado_em=None, cliente=None
) -> dict:
    """Anexa somente valores novos/revisados, sem alterar vintages anteriores.

    Sem migration, usa a macro_snapshots existente. Não sobrescreve o documento
    se sua leitura falhar. Dados coletados agora nunca ficam conhecidos no passado.
    """
    rows = preparar_observacoes_versionadas(serie_id, serie, fonte=fonte, unidade=unidade,
        disponibilidade_base=disponibilidade_base, atraso_dias=atraso_dias,
        mes_fechado=mes_fechado, publicado_em=publicado_em, coletado_em=coletado_em)
    if not rows:
        return {"ok": False, "n": 0, "motivo": "sem_observacoes_validas"}
    sb = cliente if cliente is not None else _sb()
    if sb is None:
        return {"ok": False, "n": 0, "motivo": "nao_configurado"}
    fingerprint = _fingerprint_observacoes(rows)
    indice = _ler_indice_versionado(sb, serie_id)
    if isinstance(indice, dict) and indice.get("fingerprint") == fingerprint:
        return {"ok": True, "n": 0, "motivo": "sem_revisoes", "armazenamento": indice.get("armazenamento")}
    anteriores = carregar_observacoes_versionadas(serie_id, limite=50000, cliente=sb)
    armazenamento = anteriores.attrs.get("armazenamento")
    if armazenamento not in {"versionado", "fallback_macro_snapshots"}:
        return {"ok": False, "n": 0, "motivo": armazenamento or "indisponivel"}
    if anteriores.attrs.get("limite_atingido"):
        return {"ok": False, "n": 0, "motivo": "historico_excede_limite_leitura"}
    conhecidos = {row["referencia_em"].strftime("%Y-%m-%d"): row for row in anteriores.to_dict("records")}
    novos = []
    for row in rows:
        anterior = conhecidos.get(row["referencia_em"])
        # observada_na_coleta é conhecimento inicial, não uma revisão diária de disponibilidade
        mesmos_metadados = anterior is not None and all(str(anterior[c]) == str(row[c])
            for c in ("fonte", "unidade", "disponibilidade_base"))
        mesma_disponibilidade = (row["disponibilidade_base"] == "observada_na_coleta" or
            anterior is not None and pd.Timestamp(anterior["disponivel_em"]) == pd.Timestamp(row["disponivel_em"]))
        if mesmos_metadados and mesma_disponibilidade and float(anterior["valor"]) == row["valor"]:
            continue
        novos.append(row)
    if not novos:
        _salvar_indice_versionado(sb, serie_id, fingerprint, armazenamento, rows)
        return {"ok": True, "n": 0, "motivo": "sem_revisoes", "armazenamento": armazenamento}
    if anteriores.attrs.get("tabela_disponivel"):
        try:
            for offset in range(0, len(novos), 500):
                sb.table("macro_observations").upsert(novos[offset:offset + 500],
                    on_conflict="observacao_hash", ignore_duplicates=True).execute()
            _salvar_indice_versionado(sb, serie_id, fingerprint, "versionado", rows)
            return {"ok": True, "n": len(novos), "motivo": "anexado", "armazenamento": "versionado"}
        except Exception:
            # A inserção pode falhar por migration/permissão; o documento existente
            # ainda oferece uma alternativa sem perder as versões já coletadas.
            pass
    antigos = _ler_fallback_versionado(sb, serie_id)
    if antigos is None:
        return {"ok": False, "n": 0, "motivo": "fallback_leitura_indisponivel"}
    try:
        completo = antigos + novos
        payload = json.dumps({"schema": "macro_observations_fallback_v1", "observacoes": completo}, ensure_ascii=False)
        referencias = [row["referencia_em"] for row in completo]
        sb.table("macro_snapshots").upsert({"origem": f"vintage_{serie_id}", "payload": payload,
            "n_linhas": len(completo), "n_colunas": len(_COLUNAS_OBSERVACOES),
            "data_inicio": min(referencias), "data_fim": max(referencias),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, on_conflict="origem").execute()
        _salvar_indice_versionado(sb, serie_id, fingerprint, "fallback_macro_snapshots", rows)
        return {"ok": True, "n": len(novos), "motivo": "anexado", "armazenamento": "fallback_macro_snapshots"}
    except Exception:
        return {"ok": False, "n": 0, "motivo": "persistencia_indisponivel"}
