"""
utils/alpha_vantage_client.py
Cliente para Alpha Vantage API — dados fundamentalistas históricos.

Free tier: 25 requests/dia.
Cache agressivo de 24h para preservar o limite diário.

Endpoints usados:
  INCOME_STATEMENT  — DRE trimestral (receita, lucro, EBITDA)
  BALANCE_SHEET     — Balanço trimestral (dívida, equity, caixa)
  CASH_FLOW         — Fluxo de caixa trimestral (FCF)
  OVERVIEW          — Snapshot atual de múltiplos
  EARNINGS          — Histórico de EPS trimestral

Cobertura B3: tickers com sufixo .SAO (ex: PETR4.SAO)
"""
from __future__ import annotations
import requests
import streamlit as st
import pandas as pd
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)

AV_BASE = "https://www.alphavantage.co/query"


def _get_key() -> str:
    try:
        return st.secrets["alpha_vantage"]["api_key"]
    except Exception:
        return ""


def _ticker_av(ticker: str) -> str:
    """
    Converte ticker do app para formato Alpha Vantage.
    PETR4.SA  -> PETR4.SAO  (B3 usa .SAO no Alpha Vantage)
    AAPL      -> AAPL       (EUA sem alteração)
    WEGE3.SA  -> WEGE3.SAO
    """
    t = ticker.strip().upper()
    if t.endswith('.SA'):
        return t.replace('.SA', '.SAO')
    return t


@st.cache_data(ttl=86400, show_spinner=False)
def _av_get(function: str, symbol: str) -> dict:
    """
    Chamada generica a API. Cache 24h para preservar limite diario.
    Retorna {} em caso de erro ou limite atingido.
    """
    key = _get_key()
    if not key:
        logger.warning("[av] API key nao configurada")
        return {}

    try:
        resp = requests.get(
            AV_BASE,
            params={
                "function": function,
                "symbol":   symbol,
                "apikey":   key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Alpha Vantage sinaliza erros com 'Note' ou 'Information'
        if "Note" in data:
            logger.warning(
                f"[av] limite de requisicoes atingido: {data['Note'][:80]}"
            )
            return {}
        if "Information" in data:
            logger.warning(
                f"[av] API info: {data['Information'][:80]}"
            )
            return {}
        if "Error Message" in data:
            logger.warning(
                f"[av] erro para {symbol}/{function}: "
                f"{data['Error Message'][:80]}"
            )
            return {}

        return data

    except Exception as e:
        logger.warning(f"[av] falha em {function}/{symbol}: {e}")
        return {}


def _safe_float(val) -> float | None:
    """Converte valor para float com fallback None."""
    if val is None or val in ("None", "N/A", "-", ""):
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def get_quarterly_fundamentals(ticker: str) -> list[dict]:
    """
    Busca dados fundamentalistas trimestrais combinando
    INCOME_STATEMENT, BALANCE_SHEET e CASH_FLOW.

    Retorna lista de dicts ordenada do mais recente ao mais antigo:
    [
      {
        'date':         '2024-09-30',
        'revenue':      float,
        'net_income':   float,
        'gross_profit': float,
        'ebitda':       float,
        'total_debt':   float,
        'total_equity': float,
        'cash':         float,
        'fcf':          float,
        'eps':          float,
      },
      ...
    ]
    """
    av_symbol = _ticker_av(ticker)

    # Busca os 3 endpoints necessarios
    income   = _av_get("INCOME_STATEMENT", av_symbol)
    balance  = _av_get("BALANCE_SHEET",    av_symbol)
    cashflow = _av_get("CASH_FLOW",        av_symbol)

    if not income or "quarterlyReports" not in income:
        logger.info(
            f"[av] sem dados de income para {ticker} ({av_symbol})"
        )
        return []

    # Indexa balance e cashflow por data para lookup rapido
    bal_map = {
        r.get("fiscalDateEnding", ""): r
        for r in balance.get("quarterlyReports", [])
    }
    cf_map = {
        r.get("fiscalDateEnding", ""): r
        for r in cashflow.get("quarterlyReports", [])
    }

    resultados = []
    for inc in income.get("quarterlyReports", []):
        data = inc.get("fiscalDateEnding", "")
        if not data:
            continue

        bal = bal_map.get(data, {})
        cf  = cf_map.get(data, {})

        # Receita e lucro
        revenue      = _safe_float(inc.get("totalRevenue"))
        net_income   = _safe_float(inc.get("netIncome"))
        gross_profit = _safe_float(inc.get("grossProfit"))
        ebitda       = _safe_float(inc.get("ebitda"))
        eps          = _safe_float(inc.get("reportedEPS"))

        # Balanco
        total_debt   = _safe_float(
            bal.get("shortLongTermDebtTotal")
            or bal.get("longTermDebt")
        )
        total_equity = _safe_float(bal.get("totalShareholderEquity"))
        cash         = _safe_float(
            bal.get("cashAndCashEquivalentsAtCarryingValue")
            or bal.get("cashAndShortTermInvestments")
        )

        # Fluxo de caixa
        fcf = _safe_float(
            cf.get("operatingCashflow")
        )
        capex = _safe_float(cf.get("capitalExpenditures"))
        if fcf is not None and capex is not None:
            fcf = fcf - abs(capex)  # FCF = OCF - CapEx

        resultados.append({
            "date":         data,
            "revenue":      revenue,
            "net_income":   net_income,
            "gross_profit": gross_profit,
            "ebitda":       ebitda,
            "total_debt":   total_debt,
            "total_equity": total_equity,
            "cash":         cash,
            "fcf":          fcf,
            "eps":          eps,
        })

    return resultados


@st.cache_data(ttl=86400, show_spinner=False)
def get_overview(ticker: str) -> dict:
    """
    Snapshot atual de multiplos via OVERVIEW.
    Util para complementar dados historicos.
    """
    av_symbol = _ticker_av(ticker)
    data = _av_get("OVERVIEW", av_symbol)

    if not data or "Symbol" not in data:
        return {}

    return {
        "pe":          _safe_float(data.get("PERatio")),
        "pb":          _safe_float(data.get("PriceToBookRatio")),
        "roe":         _safe_float(data.get("ReturnOnEquityTTM")),
        "roa":         _safe_float(data.get("ReturnOnAssetsTTM")),
        "margem":      _safe_float(data.get("ProfitMargin")),
        "dy":          _safe_float(data.get("DividendYield")),
        "ev_ebitda":   _safe_float(data.get("EVToEBITDA")),
        "beta":        _safe_float(data.get("Beta")),
        "setor":       data.get("Sector", ""),
        "industria":   data.get("Industry", ""),
        "descricao":   data.get("Description", "")[:500],
        "market_cap":  _safe_float(data.get("MarketCapitalization")),
        "52w_high":    _safe_float(data.get("52WeekHigh")),
        "52w_low":     _safe_float(data.get("52WeekLow")),
        "eps_ttm":     _safe_float(data.get("EPS")),
    }


@st.cache_data(ttl=86400, show_spinner=False)
def calcular_score_historico_av(ticker: str) -> pd.Series | None:
    """
    Calcula serie temporal de scores fundamentalistas
    usando dados trimestrais do Alpha Vantage.

    Metodologia por trimestre:
    - ROE = net_income / total_equity x 4 (anualizado)
    - Margem liquida = net_income / revenue
    - Divida liquida = total_debt - cash
    - Net Debt/Equity = divida_liquida / equity
    - FCF positivo (binario)
    - Crescimento de receita YoY (compara com 4 trimestres atras)
    - Crescimento de EPS YoY

    Pontuacao 0-100 normalizada pelos campos disponiveis.

    Retorna pd.Series com index de datas ou None se sem dados.
    """
    trimestres = get_quarterly_fundamentals(ticker)

    if not trimestres or len(trimestres) < 4:
        logger.info(
            f"[av] dados insuficientes para score historico: {ticker}"
        )
        return None

    scores_historicos = {}

    for i, t in enumerate(trimestres):
        data = t.get("date", "")
        if not data:
            continue

        score      = 0.0
        max_pts    = 0.0
        campos_ok  = 0

        rev   = t.get("revenue")
        ni    = t.get("net_income")
        gp    = t.get("gross_profit")
        ebit  = t.get("ebitda")
        debt  = t.get("total_debt")
        eq    = t.get("total_equity")
        cash  = t.get("cash")
        fcf   = t.get("fcf")
        eps   = t.get("eps")

        # -- ROE anualizado (0-20 pts) ------------------------------
        max_pts += 20
        if ni is not None and eq is not None and eq > 0:
            roe = (ni / eq) * 4 * 100  # anualizado
            campos_ok += 1
            if roe > 20:    score += 20
            elif roe > 12:  score += 15
            elif roe > 6:   score += 10
            elif roe > 0:   score += 5
            else:           score -= 5

        # -- Margem liquida (0-15 pts) ------------------------------
        max_pts += 15
        if ni is not None and rev is not None and rev > 0:
            margem = (ni / rev) * 100
            campos_ok += 1
            if margem > 15:    score += 15
            elif margem > 8:   score += 11
            elif margem > 3:   score += 7
            elif margem >= 0:  score += 3
            else:              score -= 5

        # -- FCF positivo (0-15 pts) --------------------------------
        max_pts += 15
        if fcf is not None:
            campos_ok += 1
            if fcf > 0:    score += 15
            elif fcf > -abs(ni or 1) * 0.5:
                           score += 5
            else:          score -= 5

        # -- Alavancagem: Net Debt / Equity (0-15 pts) -------------
        max_pts += 15
        if debt is not None and eq is not None and eq > 0:
            net_debt = (debt - (cash or 0))
            nde = net_debt / eq
            campos_ok += 1
            if nde < 0:      score += 15   # caixa liquido
            elif nde < 0.3:  score += 12
            elif nde < 0.8:  score += 8
            elif nde < 1.5:  score += 4
            else:            score -= 3

        # -- Crescimento de Receita YoY (0-15 pts) -----------------
        max_pts += 15
        if i + 4 < len(trimestres):
            rev_4q = trimestres[i + 4].get("revenue")
            if rev is not None and rev_4q is not None and rev_4q > 0:
                rev_growth = (rev / rev_4q - 1) * 100
                campos_ok += 1
                if rev_growth > 15:    score += 15
                elif rev_growth > 8:   score += 11
                elif rev_growth > 2:   score += 7
                elif rev_growth > -2:  score += 4
                else:                  score -= 3

        # -- Crescimento de EPS YoY (0-10 pts) ---------------------
        max_pts += 10
        if i + 4 < len(trimestres) and eps is not None:
            eps_4q = trimestres[i + 4].get("eps")
            if eps_4q is not None and eps_4q != 0:
                eps_growth = (eps / eps_4q - 1) * 100
                campos_ok += 1
                if eps_growth > 20:    score += 10
                elif eps_growth > 8:   score += 7
                elif eps_growth > 0:   score += 4
                else:                  score -= 2

        # -- Margem bruta (0-10 pts) --------------------------------
        max_pts += 10
        if gp is not None and rev is not None and rev > 0:
            mg_bruta = (gp / rev) * 100
            campos_ok += 1
            if mg_bruta > 40:   score += 10
            elif mg_bruta > 20: score += 7
            elif mg_bruta > 10: score += 4
            elif mg_bruta < 0:  score -= 3

        # Exige pelo menos 3 campos para pontuar
        if campos_ok < 3:
            continue

        # Normaliza para 0-100
        score_norm = max(0.0, min(100.0, (score / max_pts * 100)))
        scores_historicos[data] = round(score_norm, 1)

    if len(scores_historicos) < 3:
        return None

    # Converte para serie diaria interpolada
    serie_q = pd.Series(scores_historicos)
    serie_q.index = pd.to_datetime(serie_q.index)
    serie_q = serie_q.sort_index()

    datas_diarias = pd.date_range(
        start=serie_q.index[0],
        end=pd.Timestamp.today(),
        freq="B",
    )
    # Forward fill: mantem score ate o proximo trimestre
    serie_diaria = serie_q.reindex(datas_diarias, method="ffill")

    # Suavizacao leve (5 dias uteis)
    serie_diaria = serie_diaria.rolling(5, min_periods=1).mean()

    logger.info(
        f"[av] score historico calculado para {ticker}: "
        f"{len(serie_q)} trimestres, "
        f"range {serie_diaria.min():.0f}-{serie_diaria.max():.0f}"
    )

    return serie_diaria.round(1)
