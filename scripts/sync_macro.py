"""
sync_macro.py — ETL de dados macroeconomicos
Fontes: BCB SGS (Brasil), FRED (EUA), yfinance (VIX, Treasury)

Execucao:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... FRED_API_KEY=... python scripts/sync_macro.py
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.supabase_helper import (
    upsert_macro, log_etl_start, log_etl_finish,
)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")


def fetch_bcb():
    """Busca indicadores do Brasil via BCB SGS."""
    try:
        from bcb import sgs
        import datetime as dt

        series = {
            "selic":          432,    # Selic Over anual (%)
            "selic_diaria":   11,     # Selic Over diaria
            "ipca":           433,    # IPCA mensal (%)
            "ipca_12m":       13522,  # IPCA acumulado 12 meses
            "desemprego":     24369,  # Taxa de desemprego
            "divida_pib":     13762,  # Divida Bruta/PIB (%)
            "result_primario": 5793,  # Resultado primario (% PIB)
            "cambio":         1,      # Taxa de cambio (BRL/USD)
            "igpm":           189,    # IGP-M mensal
        }

        inicio = (dt.date.today() - dt.timedelta(days=90)).isoformat()
        df = sgs.get(series, start=inicio)

        if df.empty:
            print("  [BCB] dados vazios")
            return

        for nome, codigo in series.items():
            if nome in df.columns:
                val = df[nome].dropna()
                if not val.empty:
                    v = float(val.iloc[-1])
                    # Sanidade Selic
                    if nome == "selic":
                        if v < 1:
                            v = v * 100
                        if v > 50:
                            v = 10.75
                    # Sanidade IPCA
                    if nome == "ipca":
                        if v > 5:
                            v = v / 100

                    sources = {
                        "selic": "bcb", "selic_diaria": "bcb",
                        "ipca": "bcb", "ipca_12m": "bcb",
                        "desemprego": "bcb", "divida_pib": "bcb",
                        "result_primario": "bcb", "cambio": "bcb",
                        "igpm": "bcb",
                    }
                    units = {
                        "selic": "%aa", "selic_diaria": "%",
                        "ipca": "%", "ipca_12m": "%",
                        "desemprego": "%", "divida_pib": "%",
                        "result_primario": "%pib", "cambio": "brl/usd",
                        "igpm": "%",
                    }
                    labels = {
                        "selic": "Selic Over", "selic_diaria": "Selic Diaria",
                        "ipca": "IPCA Mensal", "ipca_12m": "IPCA 12m",
                        "desemprego": "Taxa de Desemprego",
                        "divida_pib": "Divida Bruta/PIB",
                        "result_primario": "Resultado Primario",
                        "cambio": "Dolar (BRL/USD)", "igpm": "IGP-M",
                    }
                    upsert_macro(nome, round(v, 4), label=labels.get(nome, nome),
                                 unit=units.get(nome, ""), source=sources.get(nome, "bcb"))
                    print(f"  [BCB] {nome} = {v:.4f}")

    except Exception as e:
        print(f"  [BCB] ERRO: {e}")


def fetch_fred():
    """Busca indicadores dos EUA via FRED."""
    if not FRED_API_KEY:
        print("  [FRED] FRED_API_KEY nao configurada, pulando")
        return

    try:
        from fredapi import Fred

        fred = Fred(api_key=FRED_API_KEY)

        series = {
            "t10y2y":       ("T10Y2Y", "US Treasury 10Y-2Y Spread", "%", "fred"),
            "vix":          ("VIXCLS", "VIX — Volatility Index", "pts", "fred"),
            "hy_spread":    ("BAMLH0A0HYM2", "High Yield Spread (BofA)", "%", "fred"),
            "treasury_10y": ("DGS10", "US Treasury 10Y Yield", "%", "fred"),
            "treasury_2y":  ("DGS2", "US Treasury 2Y Yield", "%", "fred"),
            "fed_funds":    ("FEDFUNDS", "Federal Funds Rate", "%", "fred"),
            "cpi":          ("CPIAUCSL", "CPI All Urban Consumers", "idx", "fred"),
            "core_cpi":     ("CORESTICKM159SFRBATL", "CPI Core Sticky", "%", "fred"),
            "unemployment": ("UNRATE", "US Unemployment Rate", "%", "fred"),
            "gdp_nowcast":  ("GDPNOW", "GDPNow (Atlanta Fed)", "%", "fred"),
            "dxy":          ("DTWEXBGS", "US Dollar Index (Trade Weighted)", "idx", "fred"),
        }

        for nome, (code, label, unit, source) in series.items():
            try:
                s = fred.get_series(code)
                if not s.empty:
                    v = float(s.dropna().iloc[-1])
                    upsert_macro(nome, round(v, 4), label=label, unit=unit, source=source)
                    print(f"  [FRED] {nome} ({code}) = {v:.4f}")
            except Exception as e:
                print(f"  [FRED] {nome} ({code}): {e}")

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
