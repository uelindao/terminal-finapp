"""
recalc_health_scores.py — recalcula health_scores para tickers já cacheados.

Usa o histórico_trimestral, price_cache e macro_cache que já estão no Supabase.
Não chama BRAPI/FMP nem yfinance.info — apenas yfinance.history como fallback
quando price_cache não tem o ticker. Útil para aplicar mudanças no health_engine
sem rodar o ETL completo.

Filtros opcionais via CLI:
    --br-only: apenas tickers .SA (BR)
    --us-only: apenas tickers sem .SA (US)
    --limit N: limita ao primeiro N

Execução:
    python scripts/recalc_health_scores.py
    python scripts/recalc_health_scores.py --br-only
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.health_engine import calcular_health_score
from scripts.supabase_helper import get_client

logger = get_logger(__name__)


def _macro_context():
    sb = get_client()
    ctx = {'selic': 14.75, 'vix': 15.0, 'ipca': 5.5, 'treasury_10y': 4.5}
    try:
        res = sb.table("macro_cache").select("indicator,value").in_(
            "indicator", ["selic", "vix", "ipca_12m", "us10y"]
        ).execute()
        for row in (res.data or []):
            k = row["indicator"]
            v = float(row["value"])
            if k == "selic":     ctx["selic"] = v
            elif k == "vix":     ctx["vix"] = v
            elif k == "ipca_12m":ctx["ipca"] = v
            elif k == "us10y":   ctx["treasury_10y"] = v
    except Exception as e:
        print(f"[recalc] macro context fallback — {e}")
    return ctx


def main():
    sb = get_client()
    rows = sb.table("fundamentals_cache").select("ticker").execute().data or []
    tickers = [r["ticker"] for r in rows]

    if "--br-only" in sys.argv:
        tickers = [t for t in tickers if t.endswith(".SA")]
    elif "--us-only" in sys.argv:
        tickers = [t for t in tickers if not t.endswith(".SA")]

    if "--limit" in sys.argv:
        try:
            i = sys.argv.index("--limit")
            n = int(sys.argv[i + 1])
            tickers = tickers[:n]
        except (ValueError, IndexError):
            pass

    macro = _macro_context()
    print(f"[recalc] {len(tickers)} tickers | macro: {macro}")

    ok = 0
    skip = 0
    fail = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            r = calcular_health_score(ticker, macro_context=macro, force=True)
            score = r.get("score")
            if score is None:
                print(f"  [{i}/{len(tickers)}] {ticker} SKIP (score=None)")
                skip += 1
            else:
                print(f"  [{i}/{len(tickers)}] {ticker} score={score}")
                ok += 1
        except Exception as e:
            print(f"  [{i}/{len(tickers)}] {ticker} FAIL: {e}")
            fail += 1
        time.sleep(0.05)

    print(f"\n[recalc] fim — ok: {ok} | skip: {skip} | fail: {fail}")


if __name__ == "__main__":
    main()
