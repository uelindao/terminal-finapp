"""
sync_price_history.py — ETL de histórico OHLCV diário (até 10 anos)
Fonte única: yfinance (gratuito, sem chave)

Para cada ticker:
  - Consulta data da última barra já em price_history
  - Se vazio:        baixa period="10y" (cold start)
  - Se atualizado: revisa90dias de barras; eventos novos de split/dividendo
    recalibram todos os10anos. Primeiro domingo do mês reconcilia10anos também.

Execucao:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scripts/sync_price_history.py

Frequência recomendada: semanal (domingo). Sync incremental é leve (~5 barras
por ticker), cold-start inicial é pesado (~2.500 barras por ticker, ~1M linhas
ao todo) e leva ~15-20 min.
"""

import argparse
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
BENCHMARKS = ["^BVSP", "^GSPC", "^VIX", "SPY", "BOVA11.SA", "BOVV11.SA", "BRL=X"]
PROXIES_ROTACAO = ["LFTS11.SA", "IRFM11.SA", "B5P211.SA", "IMAB11.SA", "GOLD11.SA", "XFIX11.SA",
    "IEF", "TIP", "LQD", "HYG", "GLD", "XLC", "XLY", "XLP", "XLE", "XLF", "XLRE",
    "XLI", "XLB", "XLV", "XLK", "XLU"]


def _yf_history_to_rows(ticker: str, hist) -> list[dict]:
    """
    Converte DataFrame retornado por yf.Ticker.history em lista de dicts
    prontos para upsert na price_history.

    yfinance com auto_adjust=True retorna 'Close' já ajustado por splits e
    dividendos — usamos esse close para cálculos de retorno consistentes.
    """
    if hist is None or hist.empty:
        return []
    import math
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
        if c is None or not math.isfinite(c) or c <= 0:
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


def _tem_evento_corporativo_novo(hist, ultima: str) -> bool:
    """Eventos posteriores à barra armazenada exigem ajuste dos preços antigos."""
    import pandas as pd
    if hist is None or hist.empty:
        return False
    datas = pd.to_datetime(hist.index, utc=True).tz_convert(None)
    novas = hist.loc[datas.normalize() > pd.Timestamp(ultima)]
    return any(coluna in novas and pd.to_numeric(novas[coluna], errors="coerce").fillna(0).ne(0).any()
               for coluna in ("Dividends", "Stock Splits", "Capital Gains"))


def sync_ticker(yf_module, ticker: str, *, reconciliar_completo: bool | None = None,
                janela_revisao_dias: int = 90) -> tuple[int, str]:
    """Revisão90d, reconciliação10a após evento e no primeiro domingo mensal.

    Revisar só dias novos conserva a antiga base ajustada quando ocorre um
    dividendo/split; por isso eventos novos desencadeiam recarga histórica.
    A reconciliação mensal também cobre correções tardias do fornecedor.
    """
    ultima = get_last_price_history_date(ticker)
    hoje = date.today()
    if reconciliar_completo is None:
        reconciliar_completo = hoje.weekday() == 6 and hoje.day <= 7
    acao = yf_module.Ticker(ticker)
    if ultima is None or reconciliar_completo:
        try:
            hist = acao.history(period="10y", auto_adjust=True, actions=True)
        except Exception as e:
            logger.warning(f"[ph] {ticker} histórico falhou: {type(e).__name__}")
            return 0, "erro"
        rows = _yf_history_to_rows(ticker, hist)
        if not rows:
            return 0, "vazio"
        n = upsert_price_history_batch(rows)
        return n, "cold-start" if ultima is None else "reconciliacao-mensal"
    try:
        ultima_dt = datetime.strptime(ultima, "%Y-%m-%d").date()
    except Exception:
        return 0, "erro-parse"
    inicio = ultima_dt - timedelta(days=max(1, int(janela_revisao_dias)))
    try:
        hist = acao.history(start=inicio.isoformat(), end=(hoje + timedelta(days=1)).isoformat(),
                            auto_adjust=True, actions=True)
        evento = _tem_evento_corporativo_novo(hist, ultima)
        if evento:
            hist = acao.history(period="10y", auto_adjust=True, actions=True)
    except Exception as e:
        logger.warning(f"[ph] {ticker} revisão falhou: {type(e).__name__}")
        return 0, "erro"
    rows = _yf_history_to_rows(ticker, hist)
    if not rows:
        return 0, "vazio"
    n = upsert_price_history_batch(rows)
    return n, "reconciliacao-evento" if evento else "revisao90d"


def universo_tickers(apenas_proxies: bool = False) -> list[str]:
    base = [t for t in BENCHMARKS if not t.startswith("^")] + PROXIES_ROTACAO if apenas_proxies else BENCHMARKS + PROXIES_ROTACAO
    if not apenas_proxies:
        base += SCREENER_B3 + BR_INDICES + SCREENER_US
    return sorted(set(base))


def main(argv=None):
    import yfinance as yf
    parser = argparse.ArgumentParser(description="Atualiza preços ajustados no cache histórico.")
    parser.add_argument("--proxies-only", action="store_true",
        help="apenas benchmarks, classes, ETFs setoriais e câmbio; sem atualizar o universo de ações")
    args = parser.parse_args(argv)
    tickers = universo_tickers(apenas_proxies=args.proxies_only)
    print(f"[ph] inicio — {len(tickers)} tickers; modo={'proxies' if args.proxies_only else 'universo completo'}")

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
            if modo.startswith("erro") or modo == "vazio":
                fail += 1
            else:
                ok += 1
            if i % 20 == 0:
                elapsed = time.time() - t0
                print(f"  [{i}/{len(tickers)}] {ticker} {modo} +{n} | "
                      f"acum {total_linhas} linhas em {elapsed:.0f}s")
            time.sleep(0.3)  # gentle com yfinance
        except Exception as e:
            print(f"  [ph] ERRO {ticker}: {type(e).__name__}")
            fail += 1

    cobertura = ok / max(1, ok + fail)
    erro = f"{fail} tickers sem sincronização; cobertura={cobertura:.1%}" if fail else ""
    log_etl_finish(log_id, ok=ok, fail=fail, error_msg=erro)
    print(f"\n[ph] fim — ok {ok}, fail {fail}, total {total_linhas} linhas")
    print(f"     stats: {stats}; cobertura={cobertura:.1%}")
    # Falhas parciais constam no log; abaixo90% interrompe a cadeia semanal.
    # Cobertura setorial mínima é validada novamente pelo backtest.
    return 1 if cobertura < 0.90 else 0


if __name__ == "__main__":
    raise SystemExit(main())
