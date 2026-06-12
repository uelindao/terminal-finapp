"""
sync_price_history.py — ETL de histórico OHLCV diário (até 10 anos)
Fonte única: yfinance (gratuito, sem chave)

Para cada ticker:
  - Consulta data da última barra já em price_history
  - Se vazio:        baixa period="10y" (cold start)
  - Se atualizado:   baixa apenas dias novos (sync incremental)

Execucao:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scripts/sync_price_history.py

Frequência recomendada: semanal (domingo). Sync incremental é leve (~5 barras
por ticker), cold-start inicial é pesado (~2.500 barras por ticker, ~1M linhas
ao todo) e leva ~15-20 min.
"""

import os
import sys
import time
from datetime import datetime, timezone, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
logger = get_logger(__name__)

from scripts.supabase_helper import (
    upsert_price_history_batch,
    get_last_price_history_date,
    log_etl_start,
    log_etl_finish,
)
from utils.tickers import SCREENER_B3, BR_INDICES, SCREENER_US

# Benchmarks adicionais que precisamos para cálculos (beta, RS, fatores)
BENCHMARKS = ["^BVSP", "^GSPC", "^VIX", "SPY", "BOVA11.SA"]


def _yf_history_to_rows(ticker: str, hist) -> list[dict]:
    """
    Converte DataFrame retornado por yf.Ticker.history em lista de dicts
    prontos para upsert na price_history.

    yfinance com auto_adjust=True retorna 'Close' já ajustado por splits e
    dividendos — usamos esse close para cálculos de retorno consistentes.
    """
    if hist is None or hist.empty:
        return []
    rows = []
    for idx, row in hist.iterrows():
        # idx é Timestamp
        try:
            data_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        except Exception:
            continue
        try:
            o = float(row["Open"]) if "Open" in row and row["Open"] == row["Open"] else None
            h = float(row["High"]) if "High" in row and row["High"] == row["High"] else None
            l = float(row["Low"])  if "Low"  in row and row["Low"]  == row["Low"]  else None
            c = float(row["Close"]) if "Close" in row and row["Close"] == row["Close"] else None
            v = int(row["Volume"]) if "Volume" in row and row["Volume"] == row["Volume"] else None
        except (ValueError, TypeError):
            continue
        if c is None:
            continue
        rows.append({
            "ticker": ticker,
            "data":   data_str,
            "open":   o,
            "high":   h,
            "low":    l,
            "close":  c,
            "volume": v,
        })
    return rows


def sync_ticker(yf_module, ticker: str) -> tuple[int, str]:
    """
    Sincroniza histórico de um único ticker. Retorna (n_linhas_upsert, modo).
    modo: 'cold-start', 'incremental' ou 'skip-uptodate'.
    """
    ultima = get_last_price_history_date(ticker)
    hoje = date.today()

    if ultima is None:
        # Cold start: baixa 10 anos
        try:
            hist = yf_module.Ticker(ticker).history(period="10y", auto_adjust=True)
        except Exception as e:
            logger.warning(f"[ph] {ticker} cold-start falhou: {e}")
            return 0, "erro"
        rows = _yf_history_to_rows(ticker, hist)
        if not rows:
            return 0, "vazio"
        upsert_price_history_batch(rows)
        return len(rows), "cold-start"

    # Incremental: do dia seguinte ao último em diante
    try:
        ultima_dt = datetime.strptime(ultima, "%Y-%m-%d").date()
    except Exception:
        return 0, "erro-parse"
    inicio = ultima_dt + timedelta(days=1)
    if inicio > hoje:
        return 0, "skip-uptodate"

    try:
        hist = yf_module.Ticker(ticker).history(
            start=inicio.isoformat(),
            end=(hoje + timedelta(days=1)).isoformat(),
            auto_adjust=True,
        )
    except Exception as e:
        logger.warning(f"[ph] {ticker} incremental falhou: {e}")
        return 0, "erro"

    rows = _yf_history_to_rows(ticker, hist)
    if not rows:
        return 0, "skip-uptodate"
    upsert_price_history_batch(rows)
    return len(rows), "incremental"


def main():
    import yfinance as yf

    tickers = sorted(set(SCREENER_B3 + BR_INDICES + SCREENER_US + BENCHMARKS))
    print(f"[ph] inicio — {len(tickers)} tickers")

    log_id = log_etl_start("sync_price_history")

    ok = 0
    fail = 0
    total_linhas = 0
    stats: dict[str, int] = {}

    t0 = time.time()
    for i, ticker in enumerate(tickers, 1):
        try:
            n, modo = sync_ticker(yf, ticker)
            stats[modo] = stats.get(modo, 0) + 1
            total_linhas += n
            ok += 1
            if i % 20 == 0:
                elapsed = time.time() - t0
                print(f"  [{i}/{len(tickers)}] {ticker} {modo} +{n} | "
                      f"acum {total_linhas} linhas em {elapsed:.0f}s")
            time.sleep(0.3)  # gentle com yfinance
        except Exception as e:
            print(f"  [ph] ERRO {ticker}: {e}")
            fail += 1

    log_etl_finish(log_id, ok=ok, fail=fail)
    print(f"\n[ph] fim — ok {ok}, fail {fail}, total {total_linhas} linhas")
    print(f"     stats: {stats}")


if __name__ == "__main__":
    main()
