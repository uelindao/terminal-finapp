"""
sync_br.py — ETL de ativos brasileiros (B3 + FIIs)
Fonte primaria: BRAPI (brapi.dev) — 15.000 req/mes free
Fallback precos: yfinance (batch)

Execucao:
  SUPABASE_URL=https://xxx.supabase.co SUPABASE_SERVICE_KEY=eyJ... BRAPI_TOKEN=xxx python scripts/sync_br.py
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
logger = get_logger(__name__)

from scripts.supabase_helper import (
    upsert_fundamentals, upsert_price, log_etl_start, log_etl_finish,
)
# Importa listas de tickers diretamente de utils/tickers.py (sem dependência de streamlit)
from utils.tickers import SCREENER_B3, FII_TODOS, BR_INDICES, BRASIL_TODOS

BRAPI_BASE = "https://brapi.dev/api"
BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "")

# Campos críticos esperados no dict de fundamentos (chaves reais dos transforms)
CAMPOS_CRITICOS = [
    "preco", "p/l", "p/vp", "dy%", "roe%",
    "margem%", "ev/ebitda", "market_cap",
]


def calcular_data_quality(fundamentals: dict) -> float:
    """Retorna % (0-100) de campos críticos preenchidos no dict de fundamentos."""
    if not fundamentals:
        return 0.0
    preenchidos = sum(
        1 for campo in CAMPOS_CRITICOS
        if fundamentals.get(campo) is not None
    )
    return round(100.0 * preenchidos / len(CAMPOS_CRITICOS), 1)


def _sf(val):
    """Safe float conversion."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def fetch_brapi(ticker: str) -> dict | None:
    """Fetch fundamental data from BRAPI for one ticker."""
    t = ticker.replace(".SA", "").upper()
    try:
        resp = requests.get(
            f"{BRAPI_BASE}/quote/{t}",
            params={"token": BRAPI_TOKEN, "fundamental": "true", "dividends": "true"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return results[0] if results else None
    except Exception as e:
        print(f"  [ERRO] BRAPI {ticker}: {e}")
        return None


def transform_brapi(raw: dict, ticker: str) -> dict:
    """Transforma resposta BRAPI em dict padrao para fundamentals_cache."""
    fd = raw.get("fundamentalData") or {}

    dy = _sf(fd.get("dividendYield") or raw.get("dividendYield"))
    if dy is not None and dy < 1.0:
        dy = dy * 100

    roe = _sf(fd.get("roe"))
    if roe is not None and abs(roe) < 2.0:
        roe = roe * 100

    margem = _sf(fd.get("netMargin") or fd.get("profitMargin"))
    if margem is not None and abs(margem) < 2.0:
        margem = margem * 100

    return {
        "ticker":        ticker,
        "nome":          (raw.get("longName") or raw.get("shortName") or "").lower(),
        "setor":         (fd.get("sector") or raw.get("sector") or "").lower(),
        "p/l":           _sf(fd.get("priceEarnings") or raw.get("priceEarnings")),
        "p/vp":          _sf(fd.get("priceToBook") or raw.get("priceToBook")),
        "dy%":           round(dy, 2) if dy is not None else None,
        "roe%":          round(roe, 2) if roe is not None else None,
        "margem%":       round(margem, 2) if margem is not None else None,
        "ev/ebitda":     _sf(fd.get("enterpriseValueOverEbitda")),
        "market_cap":    _sf(raw.get("marketCap")),
        "preco":         _sf(raw.get("regularMarketPrice")),
        "beta":          _sf(raw.get("beta")),
        "data_quality":  85,
        "_raw":          raw,
    }


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
    hist_dict: dict[str, pd.DataFrame] = {}

    for batch_start in range(0, len(tickers), batch_size):
        batch_full = tickers[batch_start:batch_start + batch_size]
        print(f"  [yfinance] lote {batch_start//batch_size + 1}/{(len(tickers)-1)//batch_size + 1} — {len(batch_full)} ativos...")

        try:
            hist = yf.download(batch_full, period="1y", auto_adjust=True, progress=False)
        except Exception as e:
            print(f"  [yfinance] lote falhou download: {e}")
            total_fail += len(batch_full)
            continue

        if hist.empty:
            print(f"  [yfinance] lote vazio, pulando")
            total_fail += len(batch_full)
            continue

        close = _get_yf_close(hist)
        if close.empty:
            total_fail += len(batch_full)
            continue

        for ticker in batch_full:
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
                except Exception as e:
                    logger.debug(f"RSI indisponível para {ticker}: {e}")

                upsert_price(ticker, price_data)
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
    print(f"[sync_br] health scores: {ok} ok, {fail} skip")
    return ok, fail


def main():
    print(f"[sync_br] inicio — {len(BRASIL_TODOS)} tickers")

    log_id = log_etl_start("sync_br")

    if not BRAPI_TOKEN:
        print("[sync_br] ERRO: BRAPI_TOKEN nao definido")
        log_etl_finish(log_id, error_msg="BRAPI_TOKEN nao definido")
        sys.exit(1)

    ok = 0
    fail = 0
    rate_limit_remaining = 15000

    for i, ticker in enumerate(BRASIL_TODOS):
        if rate_limit_remaining <= 10:
            print("  [sync_br] rate limit critico, parando...")
            break

        print(f"  [{i+1}/{len(BRASIL_TODOS)}] {ticker}...", end=" ")
        raw = fetch_brapi(ticker)

        if raw:
            dados = transform_brapi(raw, ticker)
            quality = calcular_data_quality(dados)
            upsert_fundamentals(ticker, dados, source="brapi", data_quality_pct=quality)
            print("OK")
            ok += 1
        else:
            print("FALHA")
            fail += 1

        time.sleep(0.35)  # ~3 req/s cortesia

    # Sync precos em batch
    print("[sync_br] sincronizando precos...")
    p_ok, p_fail, hist_dict = sync_prices_batch_yfinance(BRASIL_TODOS)
    print(f"[sync_br] precos: {p_ok} ok, {p_fail} falha")

    # Health scores — usa hist já baixado, sem chamadas extras ao Yahoo
    print("[sync_br] calculando health scores...")
    tickers_com_hist = [t for t in BRASIL_TODOS if t in hist_dict]
    macro_ctx = {'selic': 14.75, 'vix': 15.0, 'ipca': 5.5}
    try:
        from scripts.supabase_helper import get_client
        _sb = get_client()
        _res = _sb.table("macro_cache").select("indicator,value").in_(
            "indicator", ["selic", "vix", "ipca_12m"]
        ).execute()
        for row in (_res.data or []):
            _k = row["indicator"]
            _v = float(row["value"])
            if _k == "selic":
                macro_ctx["selic"] = _v
            elif _k == "vix":
                macro_ctx["vix"] = _v
            elif _k == "ipca_12m":
                macro_ctx["ipca"] = _v
        print(f"[sync_br] macro context: {macro_ctx}")
    except Exception as e:
        print(f"[sync_br] macro context usando padrão — {e}")

    sync_health_scores(tickers_com_hist, hist_dict, macro_ctx)

    _err = f"precos: {p_fail} falha" if p_fail > 0 else ""
    log_etl_finish(log_id, ok=ok, fail=fail, error_msg=_err)
    print(f"[sync_br] fim — fund. {ok}/{fail}, precos {p_ok}/{p_fail}")


if __name__ == "__main__":
    main()
