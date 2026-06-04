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

from scripts.supabase_helper import (
    upsert_fundamentals, upsert_price, log_etl_start, log_etl_finish,
)

BRAPI_BASE = "https://brapi.dev/api"
BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "")


# Universo B3 (fonte: utils/tickers.py)
SCREENER_B3 = [
    "ABCB4.SA","ABEV3.SA","B3SA3.SA","BBAS3.SA","BBDC3.SA","BBDC4.SA",
    "BBSE3.SA","BPAC11.SA","BRSR6.SA","CIEL3.SA","IRBR3.SA","ITSA4.SA",
    "ITUB3.SA","ITUB4.SA","PSSA3.SA","SANB11.SA","WIZC3.SA",
    "CSAN3.SA","ENEV3.SA","PETR3.SA","PETR4.SA","PRIO3.SA","RECV3.SA",
    "RRRP3.SA","VBBR3.SA","UGPA3.SA","DMMO3.SA",
    "AURE3.SA","CCEE3.SA","CMIG4.SA","CPFE3.SA","CPLE3.SA","CPLE6.SA",
    "EGIE3.SA","ELET3.SA","ELET6.SA","ENGI11.SA","EQTL3.SA","CSMG3.SA",
    "SAPR11.SA","SAPR4.SA","SBSP3.SA","TAEE11.SA","TRPL4.SA",
    "BRAP4.SA","CSNA3.SA","FESA4.SA","GGBR4.SA","GOAU4.SA","USIM5.SA","VALE3.SA",
    "CYRE3.SA","DIRR3.SA","EVEN3.SA","EZTC3.SA","HBOR3.SA","MDNE3.SA",
    "MRVE3.SA","PLPL3.SA","TEND3.SA","TRIS3.SA",
    "ABEV3.SA","BEEF3.SA","BRFS3.SA","JBSS3.SA","MRFG3.SA","MDIA3.SA",
    "SLCE3.SA","SMTO3.SA","CAML3.SA","CRFB3.SA",
    "FLRY3.SA","HAPV3.SA","HYPE3.SA","PARD3.SA","QUAL3.SA","RADL3.SA",
    "RDOR3.SA","ONCO3.SA","DASA3.SA","AALR3.SA",
    "INTB3.SA","LWSA3.SA","TOTS3.SA","POSI3.SA","CASH3.SA","IFCM3.SA","MOVI3.SA",
    "TIMS3.SA","VIVT3.SA","OIBR3.SA",
    "ALOS3.SA","ALPA4.SA","ARZZ3.SA","ASAI4.SA","CEAB3.SA","COGN3.SA",
    "CVCB3.SA","GRND3.SA","LREN3.SA","MGLU3.SA","NTCO3.SA","ODPV3.SA",
    "PETZ3.SA","SBFG3.SA","SOMA3.SA","VIVA3.SA","VULC3.SA","ZAMP3.SA","AMOB3.SA","BTOW3.SA",
    "EMBR3.SA","FRAS3.SA","KEPL3.SA","ROMI3.SA","TUPY3.SA","WEGE3.SA",
    "MYPK3.SA","RAPT4.SA","POMO4.SA","FOBJ3.SA",
    "DXCO3.SA","KLBN11.SA","SUZB3.SA",
    "AZUL4.SA","CCRO3.SA","GOLL4.SA","JSLG3.SA","MULT3.SA","RAIL3.SA",
    "RENT3.SA","STBP3.SA","VAMO3.SA",
    "BRML3.SA","IGTI11.SA","IRDM11.SA",
    "ANIM3.SA","COGN3.SA","SEER3.SA","YDUQ3.SA",
    "BRKM5.SA","UNIP6.SA",
    "BBSE3.SA","CXSE3.SA","SULA11.SA",
    "CBAV3.SA","CMIN3.SA",
]

BR_INDICES = ["BOVA11.SA","SMAL11.SA","IVVB11.SA","HASH11.SA","NASH11.SA","DIVO11.SA"]

FII_TODOS = [
    "ALZR11.SA","ARRI11.SA","BARI11.SA","BCFF11.SA","BRCO11.SA","BRCR11.SA",
    "BTLG11.SA","CACR11.SA","CPTS11.SA","CVBI11.SA","DEVA11.SA","FEXC11.SA",
    "GARE11.SA","GTWR11.SA","HABT11.SA","HCTR11.SA","HFOF11.SA","HGBS11.SA",
    "HGCR11.SA","HGLG11.SA","HGRE11.SA","HGRU11.SA","HSML11.SA","HTMX11.SA",
    "IRDM11.SA","JSRE11.SA","KFOF11.SA","KNCR11.SA","KNHY11.SA","KNIP11.SA",
    "KNRI11.SA","KNSC11.SA","LVBI11.SA","MALL11.SA","MCCI11.SA","MCHF11.SA",
    "MXRF11.SA","OUJP11.SA","PVBI11.SA","RBRF11.SA","RBRR11.SA","RBRY11.SA",
    "RBVA11.SA","RCRB11.SA","RECR11.SA","RECT11.SA","RZAK11.SA","RZTR11.SA",
    "SARE11.SA","SNCI11.SA","SNFF11.SA","TGAR11.SA","TRXF11.SA","URPR11.SA",
    "VCJR11.SA","VGHF11.SA","VGIP11.SA","VGIR11.SA","VILG11.SA","VINO11.SA",
    "VISC11.SA","VTLG11.SA","XPCI11.SA","XPIN11.SA","XPLG11.SA","XPML11.SA",
    "XPPR11.SA","XPSF11.SA",
]

BRASIL_TODOS = sorted(set(SCREENER_B3 + BR_INDICES + FII_TODOS))


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


def sync_prices_batch_yfinance(tickers: list[str], batch_size: int = 20):
    """Busca precos via yfinance em lotes menores (evita rate limit)."""
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np

        base_all = list(set(t.replace(".SA", "") for t in tickers))
        total_ok = 0
        total_fail = 0

        for batch_start in range(0, len(base_all), batch_size):
            batch_base = base_all[batch_start:batch_start + batch_size]
            print(f"  [yfinance] lote {batch_start//batch_size + 1}/{(len(base_all)-1)//batch_size + 1} — {len(batch_base)} ativos...")

            try:
                hist = yf.download(
                    batch_base, period="1y", auto_adjust=True, progress=False
                )
            except Exception as e:
                print(f"  [yfinance] lote falhou download: {e}")
                total_fail += len(batch_base)
                continue

            if hist.empty:
                print(f"  [yfinance] lote vazio, pulando")
                total_fail += len(batch_base)
                continue

            if isinstance(hist.columns, pd.MultiIndex):
                close = hist.xs('Close', axis=1, level=1)
            else:
                close = hist['Close'] if 'Close' in hist else hist

            for ticker_full in tickers:
                t_base = ticker_full.replace(".SA", "")
                if t_base not in batch_base:
                    continue
                try:
                    if isinstance(close, pd.DataFrame) and t_base in close.columns:
                        s = close[t_base].dropna()
                    elif isinstance(close, pd.Series):
                        s = close.dropna()
                    else:
                        total_fail += 1
                        continue

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

                    # RSI-14
                    try:
                        delta = s.diff().dropna()
                        gain = delta.clip(lower=0).rolling(14).mean()
                        loss = (-delta.clip(upper=0)).rolling(14).mean()
                        rs = gain / loss.replace(0, np.nan)
                        rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if len(rs) >= 14 else 50.0
                        price_data["rsi_14"] = round(rsi, 1)
                    except Exception:
                        pass

                    upsert_price(ticker_full, price_data)
                    total_ok += 1
                except Exception as e:
                    print(f"  [yfinance] ERRO {ticker_full}: {e}")
                    total_fail += 1

        return total_ok, total_fail
    except Exception as e:
        print(f"  [ERRO] sync_prices_batch: {e}")
        return 0, len(tickers)


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
            upsert_fundamentals(ticker, dados, source="brapi")
            print("OK")
            ok += 1
        else:
            print("FALHA")
            fail += 1

        time.sleep(0.35)  # ~3 req/s cortesia

    # Sync precos em batch
    print("[sync_br] sincronizando precos...")
    p_ok, p_fail = sync_prices_batch_yfinance(BRASIL_TODOS)
    print(f"[sync_br] precos: {p_ok} ok, {p_fail} falha")

    _err = f"precos: {p_fail} falha" if p_fail > 0 else ""
    log_etl_finish(log_id, ok=ok, fail=fail, error_msg=_err)
    print(f"[sync_br] fim — fund. {ok}/{fail}, precos {p_ok}/{p_fail}")


if __name__ == "__main__":
    main()
