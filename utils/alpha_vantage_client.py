"""
utils/alpha_vantage_client.py
Cliente Alpha Vantage com cache Supabase e rotacao de chaves.

Free tier: 25 req/dia por chave.
Cache Supabase: dados trimestrais historicos permanentes (3650 dias).
Cobertura B3: tickers .SA -> .SAO (ex: PETR4.SA -> PETR4.SAO)
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from utils.logger import get_logger
from utils.api_cache import (
    fetch_with_cache,
    get_todos_do_provider,
    get_av_rotator,
    save_to_cache,
    _periodo_from_date,
)

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


@st.cache_data(ttl=3600, show_spinner=False)
def get_quarterly_fundamentals_cached(ticker: str) -> list[dict]:
    """
    Busca dados fundamentalistas trimestrais completos.
    Estrategia de cache por trimestre:
    1. Le todos os trimestres ja no Supabase
    2. Busca AV apenas para trimestres ausentes ou recentes
    3. Salva novos trimestres no Supabase

    Retorna lista de dicts por trimestre, do mais recente ao mais antigo.
    """
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

    # -- Passo 3: Monta lista consolidada por trimestre -------------------
    todos_periodos = sorted(
        set(list(cached_income.keys())
            + list(cached_balance.keys())
            + list(cached_cashflow.keys())),
        reverse=True,
    )

    if not todos_periodos:
        return []

    resultados = []
    for p in todos_periodos:
        inc = cached_income.get(p, {})
        bal = cached_balance.get(p, {})
        cf  = cached_cashflow.get(p, {})

        if not inc:
            continue

        data_str = inc.get("fiscalDateEnding", p)
        rev     = _safe_float(inc.get("totalRevenue"))
        ni      = _safe_float(inc.get("netIncome"))
        gp      = _safe_float(inc.get("grossProfit"))
        ebitda  = _safe_float(inc.get("ebitda"))
        eps     = _safe_float(inc.get("reportedEPS"))
        debt    = _safe_float(
            bal.get("shortLongTermDebtTotal")
            or bal.get("longTermDebt")
        )
        equity  = _safe_float(bal.get("totalShareholderEquity"))
        cash    = _safe_float(
            bal.get("cashAndCashEquivalentsAtCarryingValue")
            or bal.get("cashAndShortTermInvestments")
        )
        ocf     = _safe_float(cf.get("operatingCashflow"))
        capex   = _safe_float(cf.get("capitalExpenditures"))
        fcf     = (ocf - abs(capex)) if (ocf and capex) else ocf

        resultados.append({
            "date":         data_str,
            "periodo":      p,
            "revenue":      rev,
            "net_income":   ni,
            "gross_profit": gp,
            "ebitda":       ebitda,
            "total_debt":   debt,
            "total_equity": equity,
            "cash":         cash,
            "fcf":          fcf,
            "eps":          eps,
        })

    return resultados


@st.cache_data(ttl=86400, show_spinner=False)
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
