"""
refresh_historico_trimestral.py — atualiza só o campo historico_trimestral
em fundamentals_cache para todos os tickers BR/US já cacheados, sem
depender de BRAPI/FMP. Útil quando o schema canônico ganha novos campos
(ex.: cash, interest_expense) e queremos re-popular sem rodar o ETL pesado.

Fontes:
- BR (sufixo .SA + não-FII): CVM oficial primeiro, yfinance.quarterly_* como fallback
- BR FII: yfinance.quarterly_* direto
- US (sem .SA): yfinance.quarterly_*

Execução:
    python scripts/refresh_historico_trimestral.py
"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.yf_enrichment import coletar_historico_trimestral
from utils.cvm_client import get_historico_trimestral_cvm
from utils.health_engine import _is_fii
from scripts.supabase_helper import get_client

logger = get_logger(__name__)


def main():
    sb = get_client()
    print("[refresh_hist] lendo lista de tickers do fundamentals_cache...")
    rows = sb.table("fundamentals_cache").select("ticker").execute().data or []
    tickers = [r["ticker"] for r in rows]

    # Filtro opcional via CLI: --br-only, --us-only
    if "--br-only" in sys.argv:
        tickers = [t for t in tickers if t.endswith(".SA")]
        print(f"[refresh_hist] filtro BR-only — {len(tickers)} tickers")
    elif "--us-only" in sys.argv:
        tickers = [t for t in tickers if not t.endswith(".SA")]
        print(f"[refresh_hist] filtro US-only — {len(tickers)} tickers")
    else:
        print(f"[refresh_hist] {len(tickers)} tickers no cache")

    ok = 0
    skip = 0
    fail = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            historico = []
            is_br = ticker.endswith(".SA")
            is_fii_t = _is_fii(ticker)

            if is_br and not is_fii_t:
                try:
                    historico = get_historico_trimestral_cvm(ticker, anos=3)
                    if historico:
                        print(f"  [{i}/{len(tickers)}] {ticker} CVM ({len(historico)} trim)")
                except Exception as e:
                    logger.debug(f"CVM falhou {ticker}: {e}")

            if not historico:
                ticker_yf = ticker if (is_br or "." in ticker or "^" in ticker) else ticker
                historico = coletar_historico_trimestral(ticker_yf, logger=logger)
                if historico:
                    print(f"  [{i}/{len(tickers)}] {ticker} yfinance ({len(historico)} trim)")

            if not historico:
                print(f"  [{i}/{len(tickers)}] {ticker} sem dados, SKIP")
                skip += 1
                time.sleep(0.3)
                continue

            # Lê dados_json atual e injeta historico_trimestral
            atual = sb.table("fundamentals_cache").select(
                "dados_json"
            ).eq("ticker", ticker).execute()
            dados = {}
            if atual.data and atual.data[0].get("dados_json"):
                raw = atual.data[0]["dados_json"]
                if isinstance(raw, str):
                    try:
                        dados = json.loads(raw)
                    except Exception:
                        dados = {}
                elif isinstance(raw, dict):
                    dados = raw

            dados["historico_trimestral"] = historico

            sb.table("fundamentals_cache").update(
                {"dados_json": json.dumps(dados)}
            ).eq("ticker", ticker).execute()
            ok += 1
            time.sleep(0.4)  # cortesia yfinance
        except Exception as e:
            print(f"  [{i}/{len(tickers)}] {ticker} ERRO: {e}")
            fail += 1
            time.sleep(0.5)

    print(f"\n[refresh_hist] fim — ok: {ok} | skip: {skip} | fail: {fail}")


if __name__ == "__main__":
    main()
