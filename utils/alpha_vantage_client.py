"""
utils/alpha_vantage_client.py
Cliente Alpha Vantage com cache Supabase e rotacao de chaves.

Free tier: 25 req/dia por chave.
Cache Supabase: dados trimestrais historicos permanentes (3650 dias).
Cobertura B3: tickers .SA -> .SAO (ex: PETR4.SA -> PETR4.SAO)

Providers suportados (em ordem de preferência):
  1. Alpha Vantage — 10 anos histórico, 25 req/dia
  2. yfinance      — 4-5 anos histórico, sem quota, fallback automático
"""
from __future__ import annotations
import pandas as pd
from utils.logger import get_logger
from utils.api_cache import (
    fetch_with_cache,
    get_todos_do_provider,
    get_av_rotator,
    save_to_cache,
    get_from_cache,
    _periodo_from_date,
)
import datetime as _dt

logger = get_logger(__name__)


def _ticker_av(ticker: str) -> str:
    t = ticker.strip().upper()
    if t.endswith('.SA'):
        return t[:-3] + '.SAO'
    return t


def _safe_float(val) -> float | None:
    if val is None or str(val).strip() in ("None", "N/A", "-", ""):
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _fetch_statement_av(av_symbol: str, function: str) -> dict:
    rotator = get_av_rotator()
    return rotator.request({"function": function, "symbol": av_symbol})


def get_quarterly_fundamentals_yfinance(ticker: str) -> list[dict]:
    """
    Busca dados fundamentalistas trimestrais via yfinance.
    Fallback quando AV não tem quota disponível.
    Salva resultado no Supabase (provider='yfinance') para evitar buscas repetidas.
    Retorna ~4-5 anos de dados para large caps B3; campos inconsistentes para small caps.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("[yf] yfinance não instalado")
        return []

    # Tenta cache yfinance primeiro (TTL: 7 dias para trimestre recente, permanente para fechados)
    cached_yf_income   = {r["periodo"]: r["data"] for r in get_todos_do_provider(ticker, "yfinance", "INCOME_STATEMENT")}
    cached_yf_balance  = {r["periodo"]: r["data"] for r in get_todos_do_provider(ticker, "yfinance", "BALANCE_SHEET")}
    cached_yf_cashflow = {r["periodo"]: r["data"] for r in get_todos_do_provider(ticker, "yfinance", "CASH_FLOW")}

    # Se já tem dados cacheados, retorna direto
    if cached_yf_income:
        logger.debug(f"[yf] cache hit {ticker} — {len(cached_yf_income)} trimestres")
        return _consolidar_trimestres(cached_yf_income, cached_yf_balance, cached_yf_cashflow)

    logger.info(f"[yf] buscando trimestrais para {ticker}")
    try:
        t = yf.Ticker(ticker)
        inc_df = t.quarterly_income_stmt
        bal_df = t.quarterly_balance_sheet
        cf_df  = t.quarterly_cashflow
    except Exception as e:
        logger.warning(f"[yf] falha ao buscar {ticker}: {e}")
        return []

    if inc_df is None or inc_df.empty:
        logger.warning(f"[yf] sem dados de income para {ticker}")
        return []

    def _get_field(df, *fields):
        """Busca campo no DataFrame yfinance (linhas = métricas, colunas = datas)."""
        if df is None or df.empty:
            return None, None
        for field in fields:
            for idx in df.index:
                if field.lower() in str(idx).lower():
                    return idx, field
        return None, None

    def _val(df, col, *fields):
        if df is None or df.empty:
            return None
        for field in fields:
            for idx in df.index:
                if field.lower() in str(idx).lower():
                    try:
                        v = df.loc[idx, col]
                        if v is not None and not (isinstance(v, float) and pd.isna(v)):
                            return float(v)
                    except Exception:
                        pass
        return None

    for col in inc_df.columns:
        try:
            date_str = str(col)[:10]
            periodo  = _periodo_from_date(date_str)

            inc_row = {
                "fiscalDateEnding": date_str,
                "totalRevenue":     _val(inc_df, col, "Total Revenue", "Revenue"),
                "netIncome":        _val(inc_df, col, "Net Income"),
                "grossProfit":      _val(inc_df, col, "Gross Profit"),
                "ebitda":           _val(inc_df, col, "EBITDA", "Normalized EBITDA", "Reconciled Depreciation"),
                "reportedEPS":      _val(inc_df, col, "Basic EPS", "Diluted EPS"),
            }
            bal_row = {
                "shortLongTermDebtTotal":               _val(bal_df, col, "Total Debt"),
                "longTermDebt":                         _val(bal_df, col, "Long Term Debt"),
                "totalShareholderEquity":               _val(bal_df, col, "Stockholders Equity", "Total Equity Gross Minority Interest"),
                "cashAndCashEquivalentsAtCarryingValue": _val(bal_df, col, "Cash And Cash Equivalents", "Cash Equivalents"),
            }
            cf_row = {
                "operatingCashflow":   _val(cf_df, col, "Operating Cash Flow"),
                "capitalExpenditures": _val(cf_df, col, "Capital Expenditure"),
            }

            # Salva no Supabase para uso futuro
            if inc_row.get("totalRevenue") or inc_row.get("netIncome"):
                save_to_cache(ticker, "yfinance", "INCOME_STATEMENT", inc_row, periodo)
                save_to_cache(ticker, "yfinance", "BALANCE_SHEET",    bal_row, periodo)
                save_to_cache(ticker, "yfinance", "CASH_FLOW",        cf_row,  periodo)
                cached_yf_income[periodo]   = inc_row
                cached_yf_balance[periodo]  = bal_row
                cached_yf_cashflow[periodo] = cf_row

        except Exception as ex:
            logger.debug(f"[yf] erro ao processar coluna {col} para {ticker}: {ex}")
            continue

    if not cached_yf_income:
        return []

    logger.info(f"[yf] {ticker}: {len(cached_yf_income)} trimestres salvos no Supabase")
    return _consolidar_trimestres(cached_yf_income, cached_yf_balance, cached_yf_cashflow)


def _consolidar_trimestres(
    cached_income: dict,
    cached_balance: dict,
    cached_cashflow: dict,
) -> list[dict]:
    """Monta lista consolidada de trimestres a partir dos dicts de cache."""
    todos_periodos = sorted(
        set(list(cached_income.keys()) + list(cached_balance.keys()) + list(cached_cashflow.keys())),
        reverse=True,
    )
    resultados = []
    for p in todos_periodos:
        inc = cached_income.get(p, {})
        bal = cached_balance.get(p, {})
        cf  = cached_cashflow.get(p, {})
        if not inc:
            continue
        data_str = inc.get("fiscalDateEnding", p)
        rev      = _safe_float(inc.get("totalRevenue"))
        ni       = _safe_float(inc.get("netIncome"))
        gp       = _safe_float(inc.get("grossProfit"))
        ebitda   = _safe_float(inc.get("ebitda"))
        eps      = _safe_float(inc.get("reportedEPS"))
        debt     = _safe_float(bal.get("shortLongTermDebtTotal") or bal.get("longTermDebt"))
        equity   = _safe_float(bal.get("totalShareholderEquity"))
        cash     = _safe_float(bal.get("cashAndCashEquivalentsAtCarryingValue") or bal.get("cashAndShortTermInvestments"))
        ocf      = _safe_float(cf.get("operatingCashflow"))
        capex    = _safe_float(cf.get("capitalExpenditures"))
        fcf      = (ocf - abs(capex)) if (ocf and capex) else ocf
        resultados.append({
            "date": data_str, "periodo": p,
            "revenue": rev, "net_income": ni, "gross_profit": gp,
            "ebitda": ebitda, "total_debt": debt, "total_equity": equity,
            "cash": cash, "fcf": fcf, "eps": eps,
        })
    return resultados


def get_quarterly_fundamentals_cached(ticker: str) -> list[dict]:
    """
    Busca dados fundamentalistas trimestrais completos.
    Estrategia de cache por trimestre:
    1. Verifica sentinel "NO_COVERAGE" (30 dias) — se existir, usa yfinance direto
    2. Le todos os trimestres ja no Supabase (AV)
    3. Busca AV apenas para trimestres ausentes ou recentes
    4. Salva novos trimestres no Supabase
    5. Fallback yfinance se AV sem cobertura; salva sentinel para evitar re-tentativas

    Retorna lista de dicts por trimestre, do mais recente ao mais antigo.
    """
    # Passo 0: Verifica sentinel "sem cobertura AV" (TTL 30 dias).
    # Evita 3 req AV por sessão para tickers que AV não cobre (comum em B3).
    _no_cov = get_from_cache(ticker, "alpha_vantage", "NO_COVERAGE", None, max_age_days=30)
    if _no_cov is not None:
        logger.debug(f"[av] {ticker} sem cobertura AV (sentinel 30d) — yfinance direto")
        return get_quarterly_fundamentals_yfinance(ticker)

    av_symbol = _ticker_av(ticker)

    # -- Passo 1: Carrega o que ja esta no cache -------------------------
    cached_income   = {
        r["periodo"]: r["data"]
        for r in get_todos_do_provider(ticker, "alpha_vantage", "INCOME_STATEMENT")
    }
    cached_balance  = {
        r["periodo"]: r["data"]
        for r in get_todos_do_provider(ticker, "alpha_vantage", "BALANCE_SHEET")
    }
    cached_cashflow = {
        r["periodo"]: r["data"]
        for r in get_todos_do_provider(ticker, "alpha_vantage", "CASH_FLOW")
    }

    # -- Passo 2: Busca AV para preencher lacunas -------------------------
    rotator = get_av_rotator()
    key_ok  = rotator.get_available_key() is not None

    if key_ok:
        _inc_data = fetch_with_cache(
            ticker   = ticker,
            provider = "alpha_vantage",
            endpoint = "INCOME_STATEMENT_RAW",
            fetch_func = lambda: _fetch_statement_av(
                av_symbol, "INCOME_STATEMENT"
            ),
            periodo  = None,
            max_age_days = 7,
        )
        if _inc_data and "quarterlyReports" in _inc_data:
            for rep in _inc_data["quarterlyReports"]:
                p = _periodo_from_date(rep.get("fiscalDateEnding", ""))
                if p not in cached_income:
                    save_to_cache(ticker, "alpha_vantage",
                                  "INCOME_STATEMENT", rep, p)
                    cached_income[p] = rep

        _bal_data = fetch_with_cache(
            ticker   = ticker,
            provider = "alpha_vantage",
            endpoint = "BALANCE_SHEET_RAW",
            fetch_func = lambda: _fetch_statement_av(
                av_symbol, "BALANCE_SHEET"
            ),
            periodo  = None,
            max_age_days = 7,
        )
        if _bal_data and "quarterlyReports" in _bal_data:
            for rep in _bal_data["quarterlyReports"]:
                p = _periodo_from_date(rep.get("fiscalDateEnding", ""))
                if p not in cached_balance:
                    save_to_cache(ticker, "alpha_vantage",
                                  "BALANCE_SHEET", rep, p)
                    cached_balance[p] = rep

        _cf_data = fetch_with_cache(
            ticker   = ticker,
            provider = "alpha_vantage",
            endpoint = "CASH_FLOW_RAW",
            fetch_func = lambda: _fetch_statement_av(
                av_symbol, "CASH_FLOW"
            ),
            periodo  = None,
            max_age_days = 7,
        )
        if _cf_data and "quarterlyReports" in _cf_data:
            for rep in _cf_data["quarterlyReports"]:
                p = _periodo_from_date(rep.get("fiscalDateEnding", ""))
                if p not in cached_cashflow:
                    save_to_cache(ticker, "alpha_vantage",
                                  "CASH_FLOW", rep, p)
                    cached_cashflow[p] = rep

    # -- Passo 3: Monta lista consolidada AV ---------------------------------
    av_result = _consolidar_trimestres(cached_income, cached_balance, cached_cashflow)

    if av_result:
        return av_result

    # -- Passo 4: Fallback yfinance (AV sem quota ou sem cobertura) ----------
    if key_ok and not cached_income and not cached_balance and not cached_cashflow:
        # Havia quota mas AV retornou vazio → ausência de cobertura (não quota esgotada).
        # Salva sentinel para evitar 3 req AV desnecessárias por sessão nos próximos 30 dias.
        save_to_cache(
            ticker, "alpha_vantage", "NO_COVERAGE",
            {"sem_cobertura_desde": str(_dt.date.today())},
            None,
        )
        logger.info(f"[av] {ticker} — sem cobertura AV — sentinel NO_COVERAGE salvo (30d)")

    motivo = "sem quota" if not key_ok else "sem cobertura AV"
    logger.info(f"[av] {ticker} — {motivo} — usando yfinance como fallback")
    yf_result = get_quarterly_fundamentals_yfinance(ticker)
    return yf_result


def sync_progressivo(
    watchlist_tickers: list[str],
    max_requests: int | None = None,
    incluir_fiis_brapi: bool = False,
    callback=None,
) -> dict:
    """
    Sincroniza ativos em ordem de prioridade até a quota AV acabar.

    Ordem: watchlist sem cache → B3 restante (por ordem do SCREENER_B3)
    Se AV sem quota: usa yfinance automaticamente para todos.

    Args:
        watchlist_tickers: tickers da watchlist do usuário (prioridade máxima)
        max_requests: limita requests AV (None = usa tudo disponível)
        incluir_fiis_brapi: sincroniza FIIs via BRAPI ao final
        callback(ticker, status, n_trim, fonte): chamado por ativo processado

    Returns:
        dict com resultados por ticker + metadados _quota_usada, _parou_por, etc.
    """
    from utils.api_cache import get_tickers_cached_av, AlphaVantageKeyRotator
    try:
        from utils.tickers import SCREENER_B3, FII_TODOS
    except ImportError:
        return {"_erro": "utils.tickers não encontrado"}

    fii_set  = set(FII_TODOS)
    cached   = get_tickers_cached_av()
    rotator  = get_av_rotator()

    # Quota disponível
    chave = rotator.get_available_key()
    uso_inicial = sum(rotator._get_uso_hoje(k) for k in rotator.keys) if rotator.keys else 0
    quota_total  = AlphaVantageKeyRotator.LIMITE_DIARIO * max(1, len(rotator.keys))
    quota_disp   = max(0, quota_total - uso_inicial)
    if max_requests is not None:
        quota_disp = min(quota_disp, max_requests)

    # Fila priorizada: watchlist → B3 (sem cache, sem FII, sem duplicata)
    _ja_na_fila: set[str] = set()
    fila: list[str] = []
    for t in watchlist_tickers:
        t_up = t.upper()
        if t_up not in cached and t_up not in fii_set and t_up not in _ja_na_fila:
            fila.append(t_up)
            _ja_na_fila.add(t_up)
    for t in SCREENER_B3:
        if t not in cached and t not in fii_set and t not in _ja_na_fila:
            fila.append(t)
            _ja_na_fila.add(t)

    # Calcula max_ativos: se tem quota AV, usa 3 req/ativo; senão vai pelo yfinance sem limite
    av_disponivel = chave is not None and quota_disp >= 3
    max_ativos = (quota_disp // 3) if av_disponivel else len(fila)
    if max_requests is not None and not av_disponivel:
        max_ativos = min(max_ativos, max_requests)  # respeita limite mesmo no yfinance

    resultado: dict = {}
    parou_por = "completo"

    for ticker in fila[:max_ativos]:
        try:
            q = get_quarterly_fundamentals_cached(ticker)
            n = len(q) if q else 0
            # Detecta qual fonte foi usada
            fonte = "alpha_vantage" if av_disponivel and rotator.get_available_key() else "yfinance"
            resultado[ticker] = n
            if callback:
                callback(ticker, "✅" if n > 0 else "❌", n, fonte)
        except Exception as e:
            resultado[ticker] = 0
            if callback:
                callback(ticker, "❌", 0, str(e))

        # Reavalia quota após cada ativo (pode ter esgotado no meio)
        if av_disponivel and rotator.get_available_key() is None:
            # Quota AV acabou — continua com yfinance para o restante da fila
            av_disponivel = False
            logger.info("[sync] quota AV esgotada — continuando com yfinance")

    # FIIs via BRAPI (opcional)
    if incluir_fiis_brapi:
        try:
            from utils.brapi_client import calcular_score_fii_brapi
            fiis_b3 = [t for t in fii_set if t in set(SCREENER_B3)]
            for ticker in fiis_b3:
                score = calcular_score_fii_brapi(ticker)
                resultado[ticker] = f"fii_score:{score:.1f}" if score is not None else "fii:sem_dados"
                if callback:
                    callback(ticker, "⏭️ FII", score or 0, "brapi")
        except Exception as e:
            logger.warning(f"[sync] FII BRAPI falhou: {e}")

    # Metadados
    uso_final    = sum(rotator._get_uso_hoje(k) for k in rotator.keys) if rotator.keys else uso_inicial
    resultado["_quota_usada"]    = max(0, uso_final - uso_inicial)
    resultado["_quota_restante"] = max(0, quota_total - uso_final)
    resultado["_parou_por"]      = parou_por
    resultado["_total_fila"]     = len(fila)
    resultado["_processados"]    = sum(1 for k, v in resultado.items()
                                       if not k.startswith("_") and isinstance(v, int) and v > 0)
    return resultado


def calcular_score_historico_av(ticker: str) -> pd.Series | None:
    """
    Calcula serie de scores fundamentalistas historicos usando
    dados trimestrais do Alpha Vantage (com cache Supabase).
    """
    trimestres = get_quarterly_fundamentals_cached(ticker)
    if not trimestres or len(trimestres) < 4:
        return None

    scores = {}
    for i, t in enumerate(trimestres):
        data   = t.get("date", "")
        if not data:
            continue

        s, max_p, ok = 0.0, 0.0, 0

        rev, ni, gp    = t.get("revenue"), t.get("net_income"), t.get("gross_profit")
        debt, eq, cash = t.get("total_debt"), t.get("total_equity"), t.get("cash")
        fcf, eps       = t.get("fcf"), t.get("eps")

        max_p += 20
        if ni is not None and eq is not None and eq > 0:
            roe = (ni / eq) * 4 * 100
            ok += 1
            if roe > 20:    s += 20
            elif roe > 12:  s += 15
            elif roe > 6:   s += 10
            elif roe > 0:   s += 5
            else:           s -= 5

        max_p += 15
        if ni is not None and rev is not None and rev > 0:
            mrg = (ni / rev) * 100
            ok += 1
            if mrg > 15:    s += 15
            elif mrg > 8:   s += 11
            elif mrg > 3:   s += 7
            elif mrg >= 0:  s += 3
            else:           s -= 5

        max_p += 15
        if fcf is not None:
            ok += 1
            if fcf > 0:   s += 15
            else:         s -= 5

        max_p += 15
        if debt is not None and eq is not None and eq > 0:
            nd = (debt - (cash or 0)) / eq
            ok += 1
            if nd < 0:      s += 15
            elif nd < 0.3:  s += 12
            elif nd < 0.8:  s += 8
            elif nd < 1.5:  s += 4
            else:           s -= 3

        max_p += 15
        if i + 4 < len(trimestres):
            rev4 = trimestres[i+4].get("revenue")
            if rev is not None and rev4 and rev4 > 0:
                rg = (rev / rev4 - 1) * 100
                ok += 1
                if rg > 15:   s += 15
                elif rg > 8:  s += 11
                elif rg > 2:  s += 7
                elif rg > -2: s += 4
                else:         s -= 3

        max_p += 10
        if gp is not None and rev is not None and rev > 0:
            mgb = (gp / rev) * 100
            ok += 1
            if mgb > 40:    s += 10
            elif mgb > 20:  s += 7
            elif mgb > 10:  s += 4
            elif mgb < 0:   s -= 3

        max_p += 10
        if i + 4 < len(trimestres) and eps is not None:
            eps4 = trimestres[i+4].get("eps")
            if eps4 and eps4 != 0:
                eg = (eps / eps4 - 1) * 100
                ok += 1
                if eg > 20:   s += 10
                elif eg > 8:  s += 7
                elif eg > 0:  s += 4
                else:         s -= 2

        if ok < 3 or max_p == 0:
            continue

        scores[data] = round(max(0.0, min(100.0, s / max_p * 100)), 1)

    if len(scores) < 3:
        return None

    serie = pd.Series(scores)
    serie.index = pd.to_datetime(serie.index)
    serie = serie.sort_index()

    datas = pd.date_range(serie.index[0], pd.Timestamp.today(), freq="B")
    return serie.reindex(datas, method="ffill").rolling(5, min_periods=1).mean().round(1)
