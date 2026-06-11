"""
sync_macro.py — ETL de dados macroeconomicos
Fontes: BCB SGS (Brasil), FRED (EUA), yfinance (VIX, Treasury)

Execucao:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... FRED_API_KEY=... python scripts/sync_macro.py

O que este script faz:
  1. Busca valores atuais (pontuais) → salva em macro_cache (upsert_macro)
  2. Busca séries históricas completas → salva em macro_snapshots (salvar_snapshot)
     → fallback para puxar_historico_mestre() em fins de semana / cold-start
"""

import os
import sys
import json
import datetime as dt
from datetime import timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
logger = get_logger(__name__)

from scripts.supabase_helper import (
    upsert_macro, log_etl_start, log_etl_finish,
)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# ── helper de serialização / upsert de snapshots históricos ──────────────────

def _get_sb_client():
    """Cliente Supabase standalone (usa env vars, não st.secrets)."""
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise ValueError("SUPABASE_URL e SUPABASE_SERVICE_KEY devem estar definidas.")
    return create_client(url, key)


def _salvar_snapshot_historico(origem: str, df: pd.DataFrame) -> bool:
    """
    Salva o DataFrame histórico (séries temporais) na tabela macro_snapshots.
    Usa upsert por 'origem' — substitui snapshot anterior.
    Compatível com o esquema criado em scripts/migrations/create_macro_snapshots.sql
    """
    if df is None or df.empty:
        print(f"  [snapshot] {origem}: DataFrame vazio, pulando.")
        return False
    try:
        sb = _get_sb_client()
        # Serializa com o mesmo formato que utils/macro_supabase.py espera
        df2 = df.copy()
        if isinstance(df2.index, pd.DatetimeIndex):
            df2.index = df2.index.strftime("%Y-%m-%d")
        payload_str = df2.to_json(orient="split", date_format="iso")

        sb.table("macro_snapshots").upsert(
            {
                "origem":      origem,
                "payload":     payload_str,
                "n_linhas":    len(df),
                "n_colunas":   df.shape[1],
                "data_inicio": str(df.index.min().date()) if not df.empty else None,
                "data_fim":    str(df.index.max().date()) if not df.empty else None,
                "updated_at":  dt.datetime.utcnow().isoformat(),
            },
            on_conflict="origem",
        ).execute()
        print(f"  [snapshot] {origem}: {len(df)} linhas salvas em macro_snapshots.")
        return True
    except Exception as e:
        print(f"  [snapshot] {origem}: ERRO ao salvar — {e}")
        return False


def fetch_bcb():
    """
    Busca indicadores do Brasil via BCB SGS.
    1. Salva valores pontuais em macro_cache (para os cards de métricas)
    2. Salva série histórica 10 anos em macro_snapshots (fallback para gráficos)
    """
    try:
        from bcb import sgs

        # ── séries para valores pontuais (macro_cache) ──────────────────────
        series_pontual = {
            "selic":           432,
            "selic_diaria":    11,
            "ipca":            433,
            "ipca_12m":        13522,
            "desemprego":      24369,
            "divida_pib":      13762,
            "result_primario": 5793,
            "cambio":          1,
            "igpm":            189,
        }

        inicio_90d = (dt.date.today() - dt.timedelta(days=90)).isoformat()
        df_90d = sgs.get(series_pontual, start=inicio_90d)

        if df_90d.empty:
            print("  [BCB] dados pontuais vazios (90d)")
        else:
            for nome in series_pontual:
                if nome in df_90d.columns:
                    val = df_90d[nome].dropna()
                    if not val.empty:
                        v = float(val.iloc[-1])
                        if nome == "selic":
                            if v < 1: v = v * 100
                            if v > 50: v = 14.75
                        if nome == "ipca":
                            if v > 5: v = v / 100
                        labels  = {"selic": "Selic Over", "selic_diaria": "Selic Diaria",
                                   "ipca": "IPCA Mensal", "ipca_12m": "IPCA 12m",
                                   "desemprego": "Taxa de Desemprego", "divida_pib": "Divida Bruta/PIB",
                                   "result_primario": "Resultado Primario", "cambio": "Dolar (BRL/USD)",
                                   "igpm": "IGP-M"}
                        units   = {"selic": "%aa", "selic_diaria": "%", "ipca": "%", "ipca_12m": "%",
                                   "desemprego": "%", "divida_pib": "%", "result_primario": "%pib",
                                   "cambio": "brl/usd", "igpm": "%"}
                        upsert_macro(nome, round(v, 4), label=labels.get(nome, nome),
                                     unit=units.get(nome, ""), source="bcb")
                        print(f"  [BCB] {nome} = {v:.4f}")

        # ── séries históricas 10 anos → macro_snapshots ─────────────────────
        print("  [BCB] buscando série histórica 10 anos...")
        series_hist = {
            "Selic":            432,
            "IPCA":             433,
            "Dolar":            1,
            "Desemprego":       24369,
            "Divida_Bruta_PIB": 13762,
            "Result_Primario":  5793,
            "Result_Nominal":   4192,
        }
        inicio_10a = (dt.date.today() - dt.timedelta(days=365 * 10)).isoformat()
        dfs_hist = {}
        for nome, codigo in series_hist.items():
            try:
                _df = sgs.get({nome: codigo}, start=inicio_10a)
                if not _df.empty:
                    dfs_hist[nome] = _df[nome]
                    print(f"  [BCB hist] {nome}: {len(_df)} pts")
            except Exception as _e:
                print(f"  [BCB hist] {nome}: {_e}")

        if dfs_hist:
            df_br_hist = pd.DataFrame(dfs_hist)
            # Calcula IPCA_12M acumulado
            if "IPCA" in df_br_hist.columns:
                try:
                    _ipca_raw = df_br_hist["IPCA"].dropna()
                    _ipca_12m = ((1 + _ipca_raw / 100).rolling(12).apply(
                        lambda x: x.prod(), raw=True) - 1) * 100
                    df_br_hist["IPCA_12M"] = _ipca_12m
                except Exception as e:
                    logger.debug(f"falha ao calcular IPCA_12M acumulado: {e}")
            _salvar_snapshot_historico("bcb_br", df_br_hist)
        else:
            print("  [BCB hist] nenhum dado histórico obtido.")

    except Exception as e:
        print(f"  [BCB] ERRO: {e}")


def fetch_fred():
    """
    Busca indicadores dos EUA via FRED.
    1. Salva valores pontuais em macro_cache
    2. Salva série histórica 10 anos em macro_snapshots
    """
    if not FRED_API_KEY:
        print("  [FRED] FRED_API_KEY nao configurada, pulando")
        return

    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)

        # ── séries para valores pontuais (macro_cache) ──────────────────────
        series_pontual = {
            "t10y2y":       ("T10Y2Y",                  "US Treasury 10Y-2Y Spread", "%",    "fred"),
            "vix":          ("VIXCLS",                  "VIX — Volatility Index",    "pts",  "fred"),
            "hy_spread":    ("BAMLH0A0HYM2",            "High Yield Spread (BofA)",  "%",    "fred"),
            "treasury_10y": ("DGS10",                   "US Treasury 10Y Yield",     "%",    "fred"),
            "treasury_2y":  ("DGS2",                    "US Treasury 2Y Yield",      "%",    "fred"),
            "fed_funds":    ("FEDFUNDS",                "Federal Funds Rate",         "%",    "fred"),
            "cpi":          ("CPIAUCSL",                "CPI All Urban Consumers",    "idx",  "fred"),
            "core_cpi":     ("CORESTICKM159SFRBATL",    "CPI Core Sticky",            "%",    "fred"),
            "unemployment": ("UNRATE",                  "US Unemployment Rate",       "%",    "fred"),
            "dxy":          ("DTWEXBGS",                "US Dollar Index",            "idx",  "fred"),
        }
        for nome, (code, label, unit, source) in series_pontual.items():
            try:
                s = fred.get_series(code)
                if not s.empty:
                    v = float(s.dropna().iloc[-1])
                    upsert_macro(nome, round(v, 4), label=label, unit=unit, source=source)
                    print(f"  [FRED] {nome} ({code}) = {v:.4f}")
            except Exception as e:
                print(f"  [FRED] {nome} ({code}): {e}")

        # ── séries históricas 10 anos → macro_snapshots ─────────────────────
        print("  [FRED] buscando série histórica 10 anos...")
        series_hist = {
            "FEDFUNDS": "FEDFUNDS", "CPIAUCSL": "CPIAUCSL", "UNRATE": "UNRATE",
            "DGS10": "DGS10", "DGS2": "DGS2", "VIXCLS": "VIXCLS",
            "ECBDFR": "ECBDFR", "IRLTLT01EZM156N": "IRLTLT01EZM156N",
            "IRLTLT01JPM156N": "IRLTLT01JPM156N",
            "T10Y2Y": "T10Y2Y", "BAMLH0A0HYM2": "BAMLH0A0HYM2",
            "GFDEGDQ188S": "GFDEGDQ188S", "MTSDS133FMS": "MTSDS133FMS",
            "CP0000EZ19M086NEST": "CP0000EZ19M086NEST", "LRHUTTTTEZM156S": "LRHUTTTTEZM156S",
            "IRLTLT01DEM156N": "IRLTLT01DEM156N", "IRLTLT01ITM156N": "IRLTLT01ITM156N",
            "IRSTCB01JPM156N": "IRSTCB01JPM156N", "CHNCPIALLMINMEI": "CHNCPIALLMINMEI",
        }
        inicio_10a = dt.date.today() - dt.timedelta(days=365 * 10)
        dfs_fred = {}
        for nome, serie_id in series_hist.items():
            try:
                _s = fred.get_series(serie_id, observation_start=inicio_10a)
                if not _s.empty:
                    dfs_fred[nome] = _s
                    print(f"  [FRED hist] {nome}: {len(_s)} pts")
            except Exception as _e:
                print(f"  [FRED hist] {nome}: {_e}")

        if dfs_fred:
            df_global_hist = pd.DataFrame(dfs_fred)
            # Calcula CPI YoY
            if "CPIAUCSL" in df_global_hist.columns:
                try:
                    df_global_hist["CPI_YOY"] = df_global_hist["CPIAUCSL"].pct_change(12) * 100
                except Exception as e:
                    logger.debug(f"falha ao calcular CPI_YOY: {e}")
            _salvar_snapshot_historico("fred_global", df_global_hist)
        else:
            print("  [FRED hist] nenhum dado histórico obtido.")

    except Exception as e:
        print(f"  [FRED] ERRO: {e}")


def fetch_yfinance_macro():
    """Busca indicadores macro via yfinance (VIX, Treasury)."""
    try:
        import yfinance as yf
        import pandas as pd

        tickers = ["^VIX", "^TNX", "^GSPC", "^IXIC"]

        for t in tickers:
            try:
                hist = yf.Ticker(t).history(period="5d")
                if hist.empty:
                    continue
                v = float(hist["Close"].dropna().iloc[-1])

                name_map = {
                    "^VIX": "vix",
                    "^TNX": "treasury_10y",
                    "^GSPC": "sp500",
                    "^IXIC": "nasdaq",
                }
                label_map = {
                    "^VIX": "VIX",
                    "^TNX": "US Treasury 10Y Yield",
                    "^GSPC": "S&P 500",
                    "^IXIC": "NASDAQ Composite",
                }
                unit_map = {
                    "^VIX": "pts", "^TNX": "%",
                    "^GSPC": "pts", "^IXIC": "pts",
                }
                key = name_map[t]
                # So upsert if not already present from FRED (yfinance is fallback)
                upsert_macro(key, round(v, 4),
                             label=label_map[t], unit=unit_map[t], source="yfinance")
                print(f"  [yfinance] {key} = {v:.4f}")
            except Exception as e:
                print(f"  [yfinance] {t}: {e}")

    except Exception as e:
        print(f"  [yfinance] ERRO: {e}")


def main():
    print("[sync_macro] inicio")
    log_id = log_etl_start("sync_macro")

    print("[sync_macro] BCB SGS...")
    fetch_bcb()

    print("[sync_macro] FRED...")
    fetch_fred()

    print("[sync_macro] yfinance...")
    fetch_yfinance_macro()

    log_etl_finish(log_id, ok=1, fail=0)
    print("[sync_macro] fim")


if __name__ == "__main__":
    main()
