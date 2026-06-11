"""
sync_us.py — ETL de ativos dos EUA
Fontes: FMP (Financial Modeling Prep) + yfinance (fallback precos)
FMP free tier: ~500 req/dia (2 chaves × 250). Usa 2 calls/ticker (profile + ratios-ttm) = ~466 calls

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
# Importa lista de tickers diretamente de utils/tickers.py (sem dependência de streamlit)
from utils.tickers import SCREENER_US

FMP_BASE = "https://financialmodelingprep.com/stable"
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
    data = _fmp_get("profile", {"symbol": ticker})
    if isinstance(data, list) and data:
        return data[0]
    return None


def fetch_fmp_key_metrics(ticker: str) -> dict | None:
    """Fetch key financial metrics from FMP."""
    data = _fmp_get("key-metrics", {"symbol": ticker, "limit": 1})
    if isinstance(data, list) and data:
        return data[0]
    return None


def fetch_fmp_ratios(ticker: str) -> dict | None:
    """Fetch TTM ratios from FMP."""
    data = _fmp_get("ratios-ttm", {"symbol": ticker})
    if isinstance(data, list) and data:
        return data[0]
    return None


def transform_fmp(ticker: str) -> dict | None:
    """Transforma dados FMP em dict padrao para fundamentals_cache.
    Usa apenas profile + ratios-ttm (2 chamadas/ticker) para respeitar free tier.
    """
    profile = fetch_fmp_profile(ticker)
    ratios = fetch_fmp_ratios(ticker)

    if not profile and not ratios:
        return None

    data = {}

    if profile:
        data["nome"] = (profile.get("companyName") or "").lower()
        data["setor"] = (profile.get("sector") or profile.get("industry") or "").lower()
        data["market_cap"] = _sf(profile.get("mktCap"))
        data["beta"] = _sf(profile.get("beta"))

    if ratios:
        data["p/l"] = _sf(ratios.get("priceToEarningsRatioTTM") or ratios.get("peRatioTTM"))
        data["p/vp"] = _sf(ratios.get("priceToBookRatioTTM") or ratios.get("pbRatioTTM"))
        data["dy%"] = _sf(ratios.get("dividendYieldTTM"))
        margem = _sf(ratios.get("netProfitMarginTTM"))
        if margem is not None:
            if abs(margem) < 2:
                margem = margem * 100
        data["margem%"] = margem
        data["ev/ebitda"] = _sf(ratios.get("enterpriseValueMultipleTTM")
                                 or ratios.get("enterpriseValueOverEBITDATTM"))
        roe_r = _sf(ratios.get("returnOnEquity"))
        if roe_r is not None:
            if abs(roe_r) < 2:
                roe_r = roe_r * 100
            data["roe%"] = roe_r

    data["ticker"] = ticker
    data["data_quality"] = 80
    data["_raw"] = {"profile": profile, "ratios": ratios}

    return data


def _get_yf_close(hist):
    """Extrai DataFrame de Close de um yfinance MultiIndex (lida com ambos formatos)."""
    import pandas as pd
    if not isinstance(hist, pd.DataFrame) or hist.empty:
        return pd.DataFrame()
    if not isinstance(hist.columns, pd.MultiIndex):
        return hist['Close'] if 'Close' in hist else hist
    try:
        return hist.xs('Close', axis=1, level=0)
    except KeyError:
        return hist.xs('Close', axis=1, level=1)


def sync_prices_batch_yfinance(tickers: list[str], batch_size: int = 20):
    """Busca precos via yfinance em lotes. Retorna (ok, fail, hist_dict)."""
    import yfinance as yf
    import pandas as pd
    total_ok = 0
    total_fail = 0
    hist_dict: dict[str, pd.DataFrame] = {}  # {ticker: DataFrame com coluna Close}

    for batch_start in range(0, len(tickers), batch_size):
        batch = tickers[batch_start:batch_start + batch_size]
        print(f"  [yfinance] lote {batch_start//batch_size + 1}/{(len(tickers)-1)//batch_size + 1} — {len(batch)} ativos...")

        try:
            hist = yf.download(batch, period="1y", auto_adjust=True, progress=False)
        except Exception as e:
            print(f"  [yfinance] lote falhou download: {e}")
            total_fail += len(batch)
            continue

        if hist.empty:
            print(f"  [yfinance] lote vazio, pulando")
            total_fail += len(batch)
            continue

        close = _get_yf_close(hist)
        if close.empty:
            total_fail += len(batch)
            continue

        for ticker in batch:
            try:
                if isinstance(close, pd.DataFrame):
                    s = close[ticker].dropna() if ticker in close.columns else pd.Series()
                else:
                    s = close.dropna()

                if len(s) < 2:
                    total_fail += 1
                    continue

                preco = float(s.iloc[-1])
                price_data = {
                    "preco":  round(preco, 2),
                    "var_1d": round(((preco / float(s.iloc[-2])) - 1) * 100, 2),
                    "var_1m": round(((preco / float(s.iloc[-21])) - 1) * 100, 2) if len(s) >= 21 else None,
                    "var_12m": round(((preco / float(s.iloc[-252])) - 1) * 100, 2) if len(s) >= 252 else None,
                    "volume": None,
                    "max_52s": round(float(s.max()), 2),
                    "min_52s": round(float(s.min()), 2),
                }

                try:
                    delta = s.diff().dropna()
                    gain = delta.clip(lower=0).rolling(14).mean()
                    loss = (-delta.clip(upper=0)).rolling(14).mean()
                    rs = gain / loss.replace(0, float('nan'))
                    rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if len(rs.dropna()) >= 14 else 50.0
                    price_data["rsi_14"] = round(rsi, 1)
                except Exception:
                    pass

                upsert_price(ticker, price_data)
                # Captura hist para reuso no health score (evita re-download)
                hist_dict[ticker] = s.to_frame(name='Close')
                total_ok += 1
            except Exception as e:
                print(f"  [yfinance] ERRO {ticker}: {e}")
                total_fail += 1

    return total_ok, total_fail, hist_dict


def sync_health_scores(tickers_ok: list[str], hist_dict: dict, macro_ctx: dict):
    """Calcula e persiste health scores usando dados já cacheados — sem download extra."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.health_engine import calcular_health_score

    ok = 0
    fail = 0
    for ticker in tickers_ok:
        try:
            hist_df = hist_dict.get(ticker)
            calcular_health_score(
                ticker,
                macro_context=macro_ctx,
                hist_externo=hist_df,
                force=True,
            )
            ok += 1
        except Exception as e:
            print(f"  [health] SKIP {ticker}: {e}")
            fail += 1
    print(f"[sync_us] health scores: {ok} ok, {fail} skip")
    return ok, fail


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
    p_ok, p_fail, hist_dict = sync_prices_batch_yfinance(SCREENER_US)
    print(f"[sync_us] precos: {p_ok} ok, {p_fail} falha")

    # Health scores — usa hist já baixado, sem chamadas extras ao Yahoo
    print("[sync_us] calculando health scores...")
    tickers_com_hist = [t for t in SCREENER_US if t in hist_dict]
    try:
        from database.db import get_all_macro_cache
        _mc = get_all_macro_cache()
        macro_ctx = {
            'selic':  _mc.get('selic', {}).get('value', 10.5),
            'vix':    _mc.get('vix', {}).get('value', 15.0),
            'ipca':   _mc.get('ipca_12m', {}).get('value', 4.5),
        }
    except Exception:
        macro_ctx = {'selic': 10.5, 'vix': 15.0, 'ipca': 4.5}

    sync_health_scores(tickers_com_hist, hist_dict, macro_ctx)

    _err = f"precos: {p_fail} falha" if p_fail > 0 else ""
    log_etl_finish(log_id, ok=ok, fail=fail, error_msg=_err)
    print(f"[sync_us] fim — fund. {ok}/{fail}, precos {p_ok}/{p_fail}")


if __name__ == "__main__":
    main()
