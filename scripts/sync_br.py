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
    upsert_fundamentals, upsert_price, log_etl_start, log_etl_finish, get_client,
)
# Importa listas de tickers diretamente de utils/tickers.py (sem dependência de streamlit)
from utils.tickers import SCREENER_B3, FII_TODOS, BR_INDICES, BRASIL_TODOS

BRAPI_BASE = "https://brapi.dev/api"
# BRAPI_TOKEN: inicializado em _init_brapi_token() para permitir fallback ao secrets.toml
BRAPI_TOKEN = ""


def _init_brapi_token():
    from scripts.supabase_helper import _get_secret
    global BRAPI_TOKEN
    BRAPI_TOKEN = _get_secret("BRAPI_TOKEN")

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


def _dividendos_12m_de_raw(raw: dict) -> float | None:
    """
    Soma os proventos (por cota/ação) dos últimos 12 meses a partir do
    `dividendsData.cashDividends` da BRAPI (campos documentados: 'rate' = valor
    por ação, 'paymentDate' = 'YYYY-MM-DD'). Usado para derivar dy% quando ausente.

    Retorna None se não houver dados (comum: o plano atual da BRAPI costuma
    devolver cashDividends vazio — nesse caso o dy% simplesmente não é derivado).
    """
    from datetime import datetime, timedelta
    dd = (raw or {}).get("dividendsData") or {}
    cash = dd.get("cashDividends") or []
    if not cash:
        return None
    corte = datetime.today().date() - timedelta(days=365)
    total = 0.0
    achou = False
    for item in cash:
        rate = _sf(item.get("rate") or item.get("value"))
        dt_str = str(item.get("paymentDate") or item.get("lastDatePrior") or "")[:10]
        if rate is None or not dt_str:
            continue
        try:
            d = datetime.strptime(dt_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d >= corte and rate > 0:
            total += rate
            achou = True
    return round(total, 6) if achou else None


# Campos estruturais de FII vindos do Fundamentus (listagem fii_resultado.php).
_FII_CAMPOS_ESTRUTURAIS = (
    "vacancia%", "liquidez_diaria", "cap_rate%", "qtd_imoveis",
    "ffo_yield%", "segmento_fii",
)


def _merge_fii(dados: dict, fii_reg: dict) -> None:
    """
    Injeta os dados estruturais de FII (vacância, liquidez, cap rate, nº imóveis)
    no dict de fundamentos, e usa p/vp + dy% do Fundamentus como fonte
    AUTORITATIVA para FIIs (mais confiável que BRAPI/yfinance para fundos).
    Muta `dados` in-place.
    """
    src = dados.setdefault("_field_source", {})
    for k in _FII_CAMPOS_ESTRUTURAIS:
        v = fii_reg.get(k)
        if v is not None:
            dados[k] = v
    for k in ("p/vp", "dy%"):
        v = fii_reg.get(k)
        if v is not None:
            dados[k] = v
            src[k] = "fundamentus_fii"


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
    """Transforma resposta BRAPI em dict padrao para fundamentals_cache.
    Após mapear BRAPI, enriquece com yfinance.info para preencher lacunas."""
    fd = raw.get("fundamentalData") or {}

    # ATENÇÃO (P0-6): a conversão por magnitude abaixo (`if abs(v) < N: v*=100`) é
    # AMBÍGUA e corrompe valores pequenos legítimos — um DY real de 0.9% (já em %)
    # vira 90%. Só dá para resolver em definitivo confirmando a unidade real que a
    # BRAPI entrega (testar ITUB4/TAEE11/PETR4 com BRAPI_TOKEN e fixar a conversão).
    # Enquanto isso, a validação de ranges no fim desta função (validar_fundamentos)
    # descarta os valores estourados (90% DY, 150% ROE) → viram None, não valor falso.
    dy = _sf(fd.get("dividendYield") or raw.get("dividendYield"))
    if dy is not None and dy < 1.0:
        dy = dy * 100

    roe = _sf(fd.get("roe"))
    if roe is not None and abs(roe) < 2.0:
        roe = roe * 100

    margem = _sf(fd.get("netMargin") or fd.get("profitMargin"))
    if margem is not None and abs(margem) < 2.0:
        margem = margem * 100

    data = {
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

    # Fallback yfinance.info — ticker BR no yfinance precisa do sufixo .SA
    from utils.yf_enrichment import enriquecer_com_yfinance, coletar_historico_trimestral
    ticker_yf = ticker if ticker.endswith(".SA") else f"{ticker}.SA"
    enriquecer_com_yfinance(data, ticker_yf, logger=logger)

    # Histórico trimestral — prioridade: CVM oficial (DRE+balanço+DFC desde 2010)
    # se ticker está mapeado/encontrado pelo cvm_client. Cai para yfinance se vazio.
    historico = []
    try:
        from utils.cvm_client import get_historico_trimestral_cvm
        historico = get_historico_trimestral_cvm(ticker_yf, anos=3)
        if historico:
            logger.info(f"[sync_br] {ticker_yf} → histórico CVM ({len(historico)} trimestres)")
    except Exception as e:
        logger.debug(f"[sync_br] CVM falhou {ticker_yf}: {e}")

    if not historico:
        historico = coletar_historico_trimestral(ticker_yf, logger=logger)

    if historico:
        data["historico_trimestral"] = historico

    # Deriva múltiplos AUSENTES (p/l, p/vp, roe%, margem%, ev/ebitda, market_cap)
    # a partir do historico_trimestral + preço (P2-1). Com o plano atual da BRAPI o
    # fundamentalData vem vazio e o yfinance.info falha em muitos tickers BR, então
    # sem isto esses campos ficam None. A derivação só preenche o que está None
    # (provedor/yfinance têm prioridade) e trata a anualização CVM vs yfinance.
    try:
        from utils.derive_multiples import derivar_multiplos
        derivar_multiplos(data, historico, logger=logger)
    except Exception as e:
        logger.debug(f"[sync_br] derivar_multiplos falhou p/ {ticker}: {e}")

    # DY derivado dos proventos dos últimos 12 meses (BRAPI dividendsData), quando ausente.
    try:
        from utils.derive_multiples import derivar_dy
        _div12 = _dividendos_12m_de_raw(raw)
        if _div12 is not None:
            derivar_dy(data, _div12, logger=logger)
    except Exception as e:
        logger.debug(f"[sync_br] derivar_dy falhou p/ {ticker}: {e}")

    # Percentil histórico dos múltiplos (P1-4) → pilar de valuation RELATIVO do score.
    # Best-effort: get_multiplos_percentis usa yfinance (custo extra). Se virar gargalo
    # de rate-limit, basta comentar este bloco — o score só perde o ajuste de ±4.
    if not ticker.endswith("11.SA"):  # FII não tem P/L/EV convencional
        try:
            from utils.fmp_client import get_multiplos_percentis
            _pctl = get_multiplos_percentis(ticker_yf, anos=10)
            if _pctl:
                data["multiplos_hist_pctl"] = _pctl
        except Exception as e:
            logger.debug(f"[sync_br] percentil histórico falhou p/ {ticker}: {e}")

    # Validação de ranges na escrita (P2-4): descarta valores fora de faixa
    # realista (p/l, p/vp, roe%, dy%, ev/ebitda, margem%) antes de persistir —
    # antes o ETL BRAPI não validava e valores estourados iam direto ao cache.
    # validar_fundamentos só toca esses 6 campos; os demais (preco, historico,
    # _raw, etc.) permanecem intactos.
    try:
        from utils.scrapers import validar_fundamentos
        validar_fundamentos(data)  # muta in-place; clampa fora-de-range para None
    except Exception as e:
        logger.debug(f"[sync_br] validar_fundamentos falhou p/ {ticker}: {e}")

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
                    from utils.indicators import rsi_last as _rsi_last
                    price_data["rsi_14"] = round(_rsi_last(s, 14, default=50.0), 1)
                except Exception as e:
                    logger.debug(f"RSI indisponível para {ticker}: {e}")

                upsert_price(ticker, price_data)
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
    print(f"[sync_br] health scores: {ok} ok, {fail} skip")
    return ok, fail


def main():
    _init_brapi_token()
    print(f"[sync_br] inicio — {len(BRASIL_TODOS)} tickers")

    log_id = log_etl_start("sync_br")

    if not BRAPI_TOKEN:
        print("[sync_br] ERRO: BRAPI_TOKEN nao definido")
        log_etl_finish(log_id, error_msg="BRAPI_TOKEN nao definido")
        sys.exit(1)

    ok = 0
    fail = 0
    rate_limit_remaining = 15000
    quality_map: dict[str, float] = {}

    # Coleta ÚNICA dos dados estruturais de FII (vacância, liquidez, cap rate) —
    # 1 request cobre ~560 FIIs. Usado no motor de FII v2 do health_engine (P1-5).
    try:
        from utils.fii_scraper import buscar_dados_fiis
        _fii_listing = buscar_dados_fiis()
        print(f"[sync_br] FIIs do Fundamentus: {len(_fii_listing)} coletados")
    except Exception as e:
        _fii_listing = {}
        logger.warning(f"[sync_br] listagem de FIIs indisponível: {e}")

    for i, ticker in enumerate(BRASIL_TODOS):
        if rate_limit_remaining <= 10:
            print("  [sync_br] rate limit critico, parando...")
            break

        print(f"  [{i+1}/{len(BRASIL_TODOS)}] {ticker}...", end=" ")
        raw = fetch_brapi(ticker)

        # BRAPI free tier (15k/mês) NÃO cobre 2 syncs/dia × ~470 tickers → a cota
        # estoura no meio do mês e fetch_brapi passa a retornar None. Como yfinance
        # + o derivador (P2-1) cobrem os múltiplos, NÃO descartamos o ticker: caímos
        # para transform_brapi({}, ...) = caminho yfinance-only. E os FIIs ainda
        # recebem os dados do Fundamentus (independe do BRAPI). ETL resiliente à cota.
        if raw:
            dados = transform_brapi(raw, ticker)
            _src = "brapi"
        else:
            dados = transform_brapi({}, ticker)
            _src = "yfinance"

        # Enriquecimento estrutural de FII (vacância, liquidez, cap rate) +
        # p/vp e dy% autoritativos do Fundamentus — independe do BRAPI ter respondido.
        _fii_reg = _fii_listing.get(ticker.replace(".SA", ""))
        if _fii_reg:
            _merge_fii(dados, _fii_reg)

        if dados.get("preco") is not None or dados.get("market_cap") is not None:
            quality = calcular_data_quality(dados)
            quality_map[ticker] = quality
            upsert_fundamentals(ticker, dados, source=_src, data_quality_pct=quality)
            print("OK" if raw else "OK(yf)")
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

    sync_health_scores(tickers_com_hist, hist_dict, macro_ctx, quality_map=quality_map)

    # ── Dividendos pagos (incremental) ──────────────────────────────────────
    # FIIs pagam mensal → histórico é volumoso (60+ pagamentos por ticker em 5 anos).
    # Sync incremental baixa só pagamentos novos quando já existe cache.
    print("[sync_br] sincronizando dividendos...")
    try:
        from scripts.sync_us import sync_dividends_incremental
        # Tickers BR no yfinance precisam de .SA — tickers_com_hist já vem do
        # SCREENER_B3+FII+BR_INDICES (todos com sufixo .SA)
        d_ok, d_skip, d_total = sync_dividends_incremental(tickers_com_hist)
        print(f"[sync_br] dividendos: {d_ok} tickers ok, {d_skip} sem novos, {d_total} pagamentos novos")
    except Exception as e:
        logger.error(f"dividendos falhou: {e}")

    _err = f"precos: {p_fail} falha" if p_fail > 0 else ""
    log_etl_finish(log_id, ok=ok, fail=fail, error_msg=_err)
    print(f"[sync_br] fim — fund. {ok}/{fail}, precos {p_ok}/{p_fail}")


if __name__ == "__main__":
    main()
