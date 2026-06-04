"""
sync_us.py — ETL de ativos dos EUA
Fontes: FMP (Financial Modeling Prep) + yfinance (fallback precos)
FMP free tier: ~250 req/dia — suficiente para ~170 tickers US

Execucao:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... FMP_API_KEY=... python scripts/sync_us.py
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.supabase_helper import (
    upsert_fundamentals, upsert_price, log_etl_start, log_etl_finish,
)

FMP_BASE = "https://financialmodelingprep.com/api/v3"
FMP_KEYS = []


def _init_keys():
    global FMP_KEYS
    k1 = os.environ.get("FMP_API_KEY", "")
    k2 = os.environ.get("FMP_API_KEY_2", "")
    if k1:
        FMP_KEYS.append(k1)
    if k2:
        FMP_KEYS.append(k2)
    if not FMP_KEYS:
        print("[sync_us] AVISO: nenhuma FMP_API_KEY configurada")


# Universo US (fonte: utils/tickers.py)
SCREENER_US = [
    # Technology
    "AAPL","ADBE","ADI","AMAT","AMD","AMZN","ANET","ANSS","ASML","AVGO",
    "CDNS","CRM","CSCO","FTNT","GOOG","GOOGL","HPQ","IBM","INTC","INTU",
    "KLAC","LRCX","META","MSFT","MU","NOW","NVDA","ORCL","PANW","PYPL",
    "QCOM","SNPS","TXN","ZBRA",
    # Health
    "ABBV","ABT","AMGN","BAX","BDX","BIIB","BMY","BSX","CI","CVS","DHR",
    "ELV","GILD","HCA","HUM","IDXX","ISRG","JNJ","MDT","MRK","PFE",
    "REGN","SYK","TMO","UNH","VRTX","ZBH",
    # Financial
    "AIG","AMP","AON","AXP","BAC","BK","BLK","BRK-B","C","CB","CFG",
    "CME","COF","DFS","FI","GS","ICE","JPM","MCO","MMC","MS","MSCI",
    "PGR","SCHW","SPGI","TFC","TRV","USB","V","WFC",
    # Consumer Cyclical
    "ABNB","AMZN","AZO","BKNG","CMG","DHI","EBAY","F","GM","HD","LEN",
    "LOW","LVS","MAR","MCD","MGM","NKE","ORLY","PHM","ROST","SBUX",
    "TGT","TJX","TSLA","YUM",
    # Consumer Defensive
    "CAG","CL","CLX","COST","EL","GIS","HSY","K","KMB","KO","MDLZ",
    "MKC","MO","PEP","PG","PM","SJM","STZ","SYY","WMT",
    # Energy
    "BKR","COP","CVX","DVN","EOG","FANG","HAL","HES","KMI","MPC","MRO",
    "OKE","OXY","PSX","SLB","VLO","WMB","XOM",
    # Industrial
    "BA","CAT","CSX","DE","EMR","ETN","FDX","GD","GE","HON","ITW","LMT",
    "MMM","NOC","NSC","PH","RTX","TT","UNP","UPS","WM",
    # Materials
    "ALB","APD","CF","DD","ECL","FCX","FMC","IP","LIN","MOS","NEM",
    "NUE","PKG","PPG","SHW",
    # Utilities
    "AEE","AEP","AES","AWK","D","DTE","DUK","ED","EIX","ES","ETR",
    "EXC","FE","NEE","NI","PCG","PEG","SO","SRE","WEC","XEL",
    # Telecom
    "CHTR","CMCSA","DISH","LUMN","T","TMUS","VZ",
    # REITs
    "AMT","ARE","AVB","CCI","DLR","EQR","EXR","IRM","KIM","O","PSA",
    "PLD","SBAC","SPG","WELL","WY",
]


def _sf(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _fmp_get(endpoint: str, params: dict | None = None) -> list | dict:
    """FMP GET com fallback entre multiplas chaves."""
    for key in FMP_KEYS:
        p = {"apikey": key}
        if params:
            p.update(params)
        try:
            resp = requests.get(f"{FMP_BASE}/{endpoint}", params=p, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    return []


def fetch_fmp_profile(ticker: str) -> dict | None:
    """Fetch company profile from FMP."""
    data = _fmp_get(f"profile/{ticker}")
    if isinstance(data, list) and data:
        return data[0]
    return None


def fetch_fmp_key_metrics(ticker: str) -> dict | None:
    """Fetch key financial metrics from FMP."""
    data = _fmp_get(f"key-metrics/{ticker}", {"limit": 1})
    if isinstance(data, list) and data:
        return data[0]
    return None


def fetch_fmp_ratios(ticker: str) -> dict | None:
    """Fetch TTM ratios from FMP."""
    data = _fmp_get(f"ratios-ttm/{ticker}")
    if isinstance(data, list) and data:
        return data[0]
    return None


def transform_fmp(ticker: str) -> dict | None:
    """Transforma dados FMP em dict padrao para fundamentals_cache."""
    profile = fetch_fmp_profile(ticker)
    metrics = fetch_fmp_key_metrics(ticker)
    ratios = fetch_fmp_ratios(ticker)

    if not profile and not ratios and not metrics:
        return None

    data = {}

    if profile:
        data["nome"] = (profile.get("companyName") or "").lower()
        data["setor"] = (profile.get("sector") or profile.get("industry") or "").lower()
        data["market_cap"] = _sf(profile.get("mktCap"))
        data["beta"] = _sf(profile.get("beta"))

    if ratios:
        data["p/l"] = _sf(ratios.get("peRatioTTM") or ratios.get("priceEarningsRatioTTM"))
        data["p/vp"] = _sf(ratios.get("pbRatioTTM") or ratios.get("priceToBookRatioTTM"))
        data["dy%"] = _sf(ratios.get("dividendYieldTTM"))
        roe = _sf(ratios.get("roeTTM"))
        if roe is not None:
            if abs(roe) < 2:
                roe = roe * 100
        data["roe%"] = roe
        margem = _sf(ratios.get("netProfitMarginTTM"))
        if margem is not None:
            if abs(margem) < 2:
                margem = margem * 100
        data["margem%"] = margem
        data["ev/ebitda"] = _sf(ratios.get("enterpriseValueOverEBITDATTM"))

    if metrics:
        data.setdefault("ev/ebitda",
                        _sf(metrics.get("enterpriseValueOverEBITDA")))
        roe_m = _sf(metrics.get("roe"))
        if roe_m is not None and data.get("roe%") is None:
            if abs(roe_m) < 2:
                roe_m = roe_m * 100
            data["roe%"] = roe_m

    # Normalize DY
    dy = data.get("dy%")
    if dy is not None and dy < 1.0:
        data["dy%"] = dy * 100

    data["ticker"] = ticker
    data["data_quality"] = 80
    data["_raw"] = {"profile": profile, "metrics": metrics, "ratios": ratios}

    return data


def sync_prices_batch_yfinance(tickers: list[str]):
    """Busca precos em batch via yfinance e salva na price_cache."""
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np

        print(f"  [yfinance] baixando precos para {len(tickers)} ativos US...")

        hist = yf.download(tickers, period="1y", auto_adjust=True, progress=False)

        if hist.empty:
            print("  [yfinance] hist vazio, pulando")
            return 0, 0

        close = hist.get("Close", hist)
        ok = 0

        for ticker in tickers:
            try:
                if isinstance(close, pd.DataFrame) and ticker in close.columns:
                    s = close[ticker].dropna()
                elif isinstance(close, pd.Series):
                    s = close.dropna()
                else:
                    continue

                if len(s) < 2:
                    continue

                preco = float(s.iloc[-1])
                var_1d = ((preco / float(s.iloc[-2])) - 1) * 100

                delta = s.diff().dropna()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, np.nan)
                rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if len(rs) >= 14 else 50.0

                price_data = {
                    "preco":  round(preco, 2),
                    "var_1d": round(var_1d, 2),
                    "var_1m": round(((preco / float(s.iloc[-21])) - 1) * 100, 2) if len(s) >= 21 else None,
                    "var_12m": round(((preco / float(s.iloc[-252])) - 1) * 100, 2) if len(s) >= 252 else None,
                    "volume": None,
                    "max_52s": round(float(s.max()), 2),
                    "min_52s": round(float(s.min()), 2),
                    "rsi_14":  round(rsi, 1),
                }
                upsert_price(ticker, price_data)
                ok += 1
            except Exception as e:
                print(f"  [ERRO] preco {ticker}: {e}")

        return ok, len(tickers) - ok
    except Exception as e:
        print(f"  [ERRO] sync_prices_batch: {e}")
        return 0, len(tickers)


def main():
    _init_keys()
    print(f"[sync_us] inicio — {len(SCREENER_US)} tickers")

    log_id = log_etl_start("sync_us")

    ok = 0
    fail = 0

    for i, ticker in enumerate(SCREENER_US):
        print(f"  [{i+1}/{len(SCREENER_US)}] {ticker}...", end=" ")
        dados = transform_fmp(ticker)

        if dados:
            upsert_fundamentals(ticker, dados, source="fmp")
            print("OK")
            ok += 1
        else:
            print("FALHA")
            fail += 1

        time.sleep(0.25)

    # Sync precos
    print("[sync_us] sincronizando precos...")
    p_ok, p_fail = sync_prices_batch_yfinance(SCREENER_US)
    print(f"[sync_us] precos: {p_ok} ok, {p_fail} falha")

    log_etl_finish(log_id, ok=ok, fail=fail)
    print(f"[sync_us] fim — {ok} ok, {fail} falha")


if __name__ == "__main__":
    main()
