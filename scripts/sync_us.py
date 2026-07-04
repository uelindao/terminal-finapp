"""
sync_us.py — ETL de ativos dos EUA
Fontes: FMP (Financial Modeling Prep) + yfinance (fallback precos)
FMP free tier: ~500 req/dia (2 chaves × 250). Usa 1 call/ticker (profile) = ~233 calls/dia.
Múltiplos (P/L, P/VP, DY, ROE, margem, EV/EBITDA) vêm via yfinance.info no enrichment.

Execucao:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... FMP_API_KEY=... python scripts/sync_us.py
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
    upsert_fundamentals, upsert_price, log_etl_start, log_etl_finish, get_client,
)
# Importa lista de tickers diretamente de utils/tickers.py (sem dependência de streamlit)
from utils.tickers import SCREENER_US

FMP_BASE = "https://financialmodelingprep.com/stable"
FMP_KEYS = []

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


def _init_keys():
    from scripts.supabase_helper import _get_secret
    global FMP_KEYS
    k1 = _get_secret("FMP_API_KEY")
    k2 = _get_secret("FMP_API_KEY_2")
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
    if not FMP_KEYS:
        logger.error("[fmp] nenhuma FMP_API_KEY configurada — todas as chamadas FMP vão falhar")
        return []
    for key in FMP_KEYS:
        p = {"apikey": key}
        if params:
            p.update(params)
        try:
            resp = requests.get(f"{FMP_BASE}/{endpoint}", params=p, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                # FMP retorna erros com HTTP 200 e body dict — detectar e logar
                if isinstance(data, dict):
                    err = data.get("Error Message") or data.get("message") or data.get("error")
                    if err:
                        logger.warning(f"[fmp] {endpoint} retornou erro (HTTP 200): {err}")
                        continue
                return data
            else:
                logger.warning(f"[fmp] {endpoint} HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.debug(f"FMP key falhou para {endpoint}: {e}, tentando próxima")
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


def transform_fmp(ticker: str) -> dict | None:
    """Transforma dados FMP em dict padrao para fundamentals_cache.

    FMP free tier: usa apenas /profile (gratuito) para nome/setor/mkt_cap/beta.
    O endpoint /ratios-ttm virou paywall (HTTP 402) — todos os múltiplos
    (P/L, P/VP, DY, ROE, margem, EV/EBITDA) vêm agora via yfinance.info
    no enriquecer_com_yfinance() abaixo.
    """
    profile = fetch_fmp_profile(ticker)

    data: dict = {}

    if profile:
        data["nome"] = (profile.get("companyName") or "").lower()
        data["setor"] = (profile.get("sector") or profile.get("industry") or "").lower()
        data["market_cap"] = _sf(profile.get("mktCap"))
        data["beta"] = _sf(profile.get("beta"))

    data["ticker"] = ticker
    data["data_quality"] = 80
    data["_raw"] = {"profile": profile}

    # Fallback yfinance.info para campos que FMP não trouxe (free tier deixa
    # buracos especialmente em ROE, margem, P/VP, DY, EV/EBITDA).
    from utils.yf_enrichment import enriquecer_com_yfinance, coletar_historico_trimestral
    enriquecer_com_yfinance(data, ticker, logger=logger)

    # Histórico trimestral (DRE + balanço + DFC) — viabiliza Piotroski YoY no health_engine
    historico = coletar_historico_trimestral(ticker, logger=logger)
    if historico:
        data["historico_trimestral"] = historico

    # Se mesmo após fallback não temos nada útil (preço + market_cap), descarta
    if data.get("preco") is None and data.get("market_cap") is None:
        return None

    # Deriva múltiplos AUSENTES (p/l, p/vp, roe%, margem%, ev/ebitda) do histórico +
    # preço (P2-1). FMP free deixa esses campos p/ o yfinance.info, que tem buracos;
    # a derivação preenche o que ficou None (histórico US é trimestral → soma 4Q).
    try:
        from utils.derive_multiples import derivar_multiplos
        derivar_multiplos(data, historico, logger=logger)
    except Exception as e:
        logger.debug(f"[sync_us] derivar_multiplos falhou p/ {ticker}: {e}")

    # Percentil histórico dos múltiplos (P1-4) — pilar de valuation relativo (best-effort).
    try:
        from utils.fmp_client import get_multiplos_percentis
        _pctl = get_multiplos_percentis(ticker, anos=10)
        if _pctl:
            data["multiplos_hist_pctl"] = _pctl
    except Exception as e:
        logger.debug(f"[sync_us] percentil histórico falhou p/ {ticker}: {e}")

    # Validação de ranges na escrita (P2-4) — mesma proteção do sync_br.
    try:
        from utils.scrapers import validar_fundamentos
        validar_fundamentos(data)
    except Exception as e:
        logger.debug(f"[sync_us] validar_fundamentos falhou p/ {ticker}: {e}")

    return data


def sync_dividends_incremental(tickers: list[str]) -> tuple[int, int, int]:
    """
    Sync incremental de dividendos via yf.Ticker.dividends. Para cada ticker:
    - Consulta data do último dividendo cacheado
    - Se vazio: baixa histórico completo (desde IPO)
    - Se cache existente: baixa apenas pagamentos posteriores

    Retorna (n_tickers_ok, n_tickers_skip_uptodate, n_linhas_total).
    """
    import time
    from utils.yf_enrichment import coletar_dividendos_yfinance
    from scripts.supabase_helper import (
        upsert_dividend_history_batch, get_last_dividend_date,
    )

    ok = 0
    skip = 0
    total = 0
    for i, ticker in enumerate(tickers, 1):
        try:
            desde = get_last_dividend_date(ticker)
            divs = coletar_dividendos_yfinance(ticker, desde=desde, logger=logger)
            if not divs:
                skip += 1
                continue
            n = upsert_dividend_history_batch(divs)
            total += n
            ok += 1
            if i % 25 == 0:
                print(f"  [div] {i}/{len(tickers)} processados, acum {total} pagamentos")
            time.sleep(0.2)  # gentle com yfinance
        except Exception as e:
            logger.warning(f"[div] {ticker} falhou: {e}")
    return ok, skip, total


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
                    from utils.indicators import rsi_last as _rsi_last
                    price_data["rsi_14"] = round(_rsi_last(s, 14, default=50.0), 1)
                except Exception as e:
                    logger.debug(f"RSI indisponível para {ticker}: {e}")

                upsert_price(ticker, price_data)
                # Captura hist para reuso no health score (evita re-download)
                hist_dict[ticker] = s.to_frame(name='Close')
                total_ok += 1
            except Exception as e:
                print(f"  [yfinance] ERRO {ticker}: {e}")
                total_fail += 1

    return total_ok, total_fail, hist_dict


def sync_health_scores(tickers_ok: list[str], hist_dict: dict, macro_ctx: dict,
                       quality_map: dict | None = None):
    """Calcula e persiste health scores usando dados já cacheados — sem download extra.

    quality_map: opcional. Map ticker -> data_quality_pct (0-100). Quando passado,
    grava a qualidade do dado na coluna correspondente de health_scores após o
    cálculo, fechando o ciclo iniciado em fundamentals_cache.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.health_engine import calcular_health_score

    ok = 0
    fail = 0
    sb = get_client() if quality_map else None
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
            if sb is not None and quality_map and ticker in quality_map:
                try:
                    sb.table("health_scores").update(
                        {"data_quality_pct": quality_map[ticker]}
                    ).eq("ticker", ticker).execute()
                except Exception as e:
                    logger.debug(f"[health] update data_quality_pct falhou {ticker}: {e}")
        except Exception as e:
            print(f"  [health] SKIP {ticker}: {e}")
            fail += 1
    print(f"[sync_us] health scores: {ok} ok, {fail} skip")
    return ok, fail


def sync_earnings_revisions(client, tickers: list[str], setores_map: dict[str, str]):
    """Coleta EPS estimate atual + compara com leitura de 30 dias atrás (do próprio banco) → registra revisão."""
    from datetime import timedelta
    from utils.fmp_client import buscar_analyst_estimates

    # Pré-flight: tabela existe e está acessível?
    try:
        client.table("earnings_revisions").select("ticker", count="exact").limit(0).execute()
    except Exception as e:
        print(f"  [revisions] ABORT: tabela earnings_revisions inacessível ({e})")
        print("  [revisions] rode o CREATE TABLE do supabase_setup.sql no SQL Editor antes do próximo ETL.")
        return 0, 0

    logger.info(f"earnings revisions: processando {len(tickers)} tickers")
    n_ok = 0
    n_fmp_vazio = 0
    n_eps_none = 0
    n_erro = 0
    for i, ticker in enumerate(tickers):
        try:
            est = buscar_analyst_estimates(ticker)
            if not est:
                n_fmp_vazio += 1
                continue
            eps_atual = est.get("estimatedEpsAvg") or est.get("epsAvg")
            if eps_atual is None:
                n_eps_none += 1
                continue

            # Busca leitura ~30d atrás do mesmo ticker no banco
            limite = (datetime.now(timezone.utc) - timedelta(days=27)).isoformat()
            prev = client.table("earnings_revisions").select("eps_estimate").eq("ticker", ticker).lte("capturado_em", limite).order("capturado_em", desc=True).limit(1).execute()
            eps_30d = prev.data[0]["eps_estimate"] if prev.data else None

            delta_pct = None
            revisao_pos = None
            if eps_30d not in (None, 0):
                delta_pct = round(100.0 * (eps_atual - eps_30d) / abs(eps_30d), 2)
                revisao_pos = delta_pct > 1.0  # >+1% = revisão positiva clara

            # Insert (não upsert): cada execução cria uma captura nova (timestamp default now()).
            # Não há conflito porque PK é (ticker, capturado_em) e capturado_em sempre muda.
            client.table("earnings_revisions").insert({
                "ticker": ticker,
                "setor": setores_map.get(ticker),
                "eps_estimate": float(eps_atual),
                "eps_estimate_30d_atras": float(eps_30d) if eps_30d is not None else None,
                "delta_pct": delta_pct,
                "revisao_positiva": revisao_pos,
            }).execute()
            n_ok += 1

            time.sleep(0.4)  # rate limit
        except Exception:
            n_erro += 1
            logger.error(f"erro revisao {ticker}", exc_info=True)
            continue
    print(f"  [revisions] resumo: ok={n_ok}, fmp_vazio={n_fmp_vazio}, eps_none={n_eps_none}, erro={n_erro}")
    return n_ok, n_erro


def main():
    _init_keys()
    print(f"[sync_us] inicio — {len(SCREENER_US)} tickers")

    log_id = log_etl_start("sync_us")

    ok = 0
    fail = 0
    quality_map: dict[str, float] = {}
    setores_map: dict[str, str] = {}

    for i, ticker in enumerate(SCREENER_US):
        print(f"  [{i+1}/{len(SCREENER_US)}] {ticker}...", end=" ")
        dados = transform_fmp(ticker)

        if dados:
            quality = calcular_data_quality(dados)
            quality_map[ticker] = quality
            upsert_fundamentals(ticker, dados, source="fmp", data_quality_pct=quality)
            if dados.get("setor"):
                setores_map[ticker] = dados["setor"]
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
    except Exception as e:
        logger.debug(f"macro context usando padrão: {e}")
        macro_ctx = {'selic': 10.5, 'vix': 15.0, 'ipca': 4.5}

    sync_health_scores(tickers_com_hist, hist_dict, macro_ctx, quality_map=quality_map)

    # ── Earnings Revisions (revisões de EPS nos últimos 30d) ────────────────
    # Limita a top 100 tickers para não estourar rate limit
    # TODO: ampliar para 200 quando free tier permitir
    tickers_rev = SCREENER_US[:100]
    try:
        sb_rev = get_client()
        sync_earnings_revisions(sb_rev, tickers_rev, setores_map)
    except Exception as e:
        logger.error(f"earnings revisions falhou: {e}")

    # ── Dividendos pagos (incremental) ──────────────────────────────────────
    # Para tickers que sincronizaram fundamentos com sucesso. Sync incremental
    # baixa só pagamentos novos quando já existe cache (~50ms/ticker), histórico
    # completo no cold-start (~500ms/ticker).
    print("[sync_us] sincronizando dividendos...")
    try:
        d_ok, d_skip, d_total = sync_dividends_incremental(tickers_com_hist)
        print(f"[sync_us] dividendos: {d_ok} tickers ok, {d_skip} sem novos, {d_total} pagamentos novos")
    except Exception as e:
        logger.error(f"dividendos falhou: {e}")

    _err = f"precos: {p_fail} falha" if p_fail > 0 else ""
    log_etl_finish(log_id, ok=ok, fail=fail, error_msg=_err)
    print(f"[sync_us] fim — fund. {ok}/{fail}, precos {p_ok}/{p_fail}")


if __name__ == "__main__":
    main()
