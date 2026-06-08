"""
utils/fmp_client.py
Cliente para Financial Modeling Prep (FMP) API — endpoints /stable/.
Documentação: https://financialmodelingprep.com/developer/docs

Endpoints usados:
  /ratios?symbol={ticker}           — múltiplos históricos (P/E, P/B, ROE, ROIC…)
  /key-metrics?symbol={ticker}      — métricas chave históricas (FCF, D/E, etc.)
  /stock-peers?symbol={ticker}      — peers por setor
  /earnings-calendar?from=&to=      — calendário de earnings
  /profile?symbol={ticker}          — perfil da empresa
  /financial-scores?symbol={ticker} — Altman Z-Score, Piotroski F-Score
  /analyst-estimates?symbol={ticker}— estimativas de analistas (receita, EBITDA, EPS)
  /grades-consensus?symbol={ticker} — consenso de recomendações (Buy/Hold/Sell)

Política de cache:
  - Múltiplos/perfil: 24 h (dados raramente mudam intraday)
  - Earnings calendar: 1 h (datas podem ser ajustadas)

Segurança:
  - A FMP_API_KEY nunca é registrada em logs — apenas "configurada" ou "ausente".
"""
from __future__ import annotations

import requests
import streamlit as st

from utils.logger import get_logger

logger = get_logger(__name__)

FMP_BASE    = "https://financialmodelingprep.com/stable"
FMP_TIMEOUT = 15  # segundos
FMP_MAX_LIMIT = 5  # free tier: max 5 registros por request em endpoints históricos


# ── Helpers internos ──────────────────────────────────────────────────────────

def _get_keys() -> list[str]:
    """
    Retorna lista de FMP_API_KEYs configuradas.
    Suporta tanto contexto Streamlit (st.secrets) quanto ETL (os.environ).
    """
    import os
    keys = []
    try:
        k1 = st.secrets.get("FMP_API_KEY", "") or os.environ.get("FMP_API_KEY", "")
        if k1: keys.append(k1)
        k2 = st.secrets.get("FMP_API_KEY_2", "") or os.environ.get("FMP_API_KEY_2", "")
        if k2: keys.append(k2)
    except Exception:
        # Contexto ETL sem streamlit
        k1 = os.environ.get("FMP_API_KEY", "")
        k2 = os.environ.get("FMP_API_KEY_2", "")
        if k1: keys.append(k1)
        if k2: keys.append(k2)
    if keys:
        logger.debug(f"[fmp] {len(keys)} FMP_API_KEY(s) configurada(s)")
    else:
        logger.warning("[fmp] nenhuma FMP_API_KEY configurada (secrets.toml ou env var)")
    return keys


_ENDPOINT_MAP = {
    "ratios":              "ratios",
    "ratios-ttm":          "ratios-ttm",
    "key-metrics":         "key-metrics",
    "stock_peers":         "stock-peers",
    "stock-peers":         "stock-peers",
    "earning_calendar":    "earnings-calendar",
    "earnings-calendar":   "earnings-calendar",
    "profile":             "profile",
    "financial-scores":    "financial-scores",
    "analyst-estimates":   "analyst-estimates",
    "grades-consensus":    "grades-consensus",
}


def _resolve_endpoint(endpoint: str, params: dict | None) -> tuple[str, dict]:
    """
    Converte chamadas antigas (path-style: 'ratios/AAPL') para novas
    (query-style: 'ratios?symbol=AAPL').  Retorna (endpoint_novo, params).
    """
    import re

    p = dict(params or {})

    # Ex: "ratios/AAPL" → endpoint="ratios", symbol="AAPL"
    m = re.match(r"^([a-z_-]+)/([A-Za-z0-9.^]+)$", endpoint, re.IGNORECASE)
    if m:
        raw_name, ticker = m.group(1), m.group(2)
        p.setdefault("symbol", ticker.upper().replace(".SA", ""))
        endpoint = raw_name

    resolved = _ENDPOINT_MAP.get(endpoint, endpoint)
    return resolved, p


def _get(endpoint: str, params: dict | None = None) -> dict | list:
    """
    GET genérico para a API FMP com fallback entre múltiplas chaves.
    Tenta cada chave em ordem; se uma retorna 403, passa para a próxima.
    Aceita nomes antigos (path-style) e novos (query-style).
    Retorna [] em caso de todas falharem.
    """
    keys = _get_keys()
    if not keys:
        return []

    endpoint, p = _resolve_endpoint(endpoint, params)

    for i, key in enumerate(keys):
        try:
            p["apikey"] = key
            url = f"{FMP_BASE}/{endpoint}"
            logger.debug(f"[fmp] GET {url} params={{k:v for k,v in p.items() if k!='apikey'}}")
            resp = requests.get(url, params=p, timeout=10)

            if resp.status_code == 403:
                if i < len(keys) - 1:
                    logger.info(
                        f"[fmp] key {i+1} bloqueada (403), tentando key {i+2}"
                    )
                    continue
                logger.warning(
                    f"[fmp] todas as {len(keys)} keys retornaram 403 em /{endpoint}"
                )
                return []

            if resp.status_code == 402:
                logger.warning(
                    f"[fmp] endpoint premium (402) em /{endpoint} — assinatura necessária"
                )
                return []

            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict) and "Error Message" in data:
                logger.warning(
                    f"[fmp] erro da API em /{endpoint}: {data['Error Message']}"
                )
                return []

            return data

        except Exception as e:
            if i < len(keys) - 1:
                logger.info(
                    f"[fmp] key {i+1} falhou ({type(e).__name__}), tentando key {i+2}"
                )
                continue
            logger.warning(f"[fmp] falha em /{endpoint}: {e}")
            return []

    return []


def _safe_pct(val) -> float | None:
    """Converte decimal FMP (0.15) para percentual (15.0), descartando outliers."""
    try:
        v = float(val)
        return round(v * 100, 2) if v is not None else None
    except Exception:
        return None


def _safe_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except Exception:
        return None


# ── Múltiplos históricos ──────────────────────────────────────────────────────

def _row(df, *nomes):
    """Retorna a primeira linha de df cujo nome (case-insensitive) está em nomes."""
    for nome in nomes:
        for idx in df.index:
            if str(idx).lower().replace(" ", "") == nome.lower().replace(" ", ""):
                return df.loc[idx]
    return None


def _get_multiplos_historicos_yf(ticker: str, anos: int = 3) -> list[dict]:
    """
    Fallback yfinance para histórico de fundamentos quando FMP retorna vazio.
    Tenta dados trimestrais primeiro (mais pontos para o gráfico); cai para anuais.
    Dados de fluxo trimestrais são anualizados (×4) para PE/ROE ficarem na escala correta.
    Funciona bem para ativos .SA onde FMP free-tier é limitado.
    """
    try:
        import yfinance as yf
        import pandas as pd

        tk   = yf.Ticker(ticker)
        info = tk.info or {}

        # Tenta trimestral primeiro (até anos*4 períodos ≈ 12 trimestres)
        fin = tk.quarterly_financials
        bal = tk.quarterly_balance_sheet
        is_quarterly = fin is not None and not fin.empty

        if not is_quarterly:
            fin = tk.financials
            bal = tk.balance_sheet

        if fin is None or fin.empty:
            return []

        shares = (
            info.get("sharesOutstanding")
            or info.get("impliedSharesOutstanding")
            or info.get("floatShares")
        )
        if not shares or shares <= 0:
            shares = None

        ann    = 4.0 if is_quarterly else 1.0
        n_per  = anos * 4 if is_quarterly else anos
        fonte  = "yfinance-q" if is_quarterly else "yfinance"

        # Preços mensais para estimar market cap na data fiscal
        try:
            hist_px = tk.history(period=f"{anos + 1}y", interval="1mo")["Close"].dropna()
            if hasattr(hist_px.index, "tz") and hist_px.index.tz is not None:
                hist_px.index = hist_px.index.tz_localize(None)
        except Exception:
            hist_px = pd.Series(dtype=float)

        resultados = []
        colunas = list(fin.columns)[:n_per]  # mais recentes primeiro

        for col in colunas:
            try:
                dt_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)[:10]

                # ── Demonstração de resultado (anualizado se trimestral) ─
                net_income = None
                for row_name in ("Net Income", "Net Income Common Stockholders",
                                 "Net Income Including Noncontrolling Interests"):
                    s = _row(fin, row_name)
                    if s is not None and col in s.index:
                        v = s[col]
                        try:
                            import numpy as np
                            net_income = float(v) * ann if not np.isnan(float(v)) else None
                        except Exception:
                            pass
                        break

                revenue = None
                for row_name in ("Total Revenue", "Revenue"):
                    s = _row(fin, row_name)
                    if s is not None and col in s.index:
                        v = s[col]
                        try:
                            import numpy as np
                            revenue = float(v) * ann if not np.isnan(float(v)) else None
                        except Exception:
                            pass
                        break

                ebitda = None
                s_ebitda = _row(fin, "EBITDA")
                if s_ebitda is not None and col in s_ebitda.index:
                    v = s_ebitda[col]
                    try:
                        import numpy as np
                        ebitda = float(v) * ann if not np.isnan(float(v)) else None
                    except Exception:
                        pass

                # ── Balanço patrimonial (ponto no tempo — não anualizar) ─
                equity = total_debt = cash = None
                if bal is not None and not bal.empty and col in bal.columns:
                    for row_name in ("Stockholders Equity", "Common Stock Equity",
                                     "Total Stockholder Equity"):
                        s = _row(bal, row_name)
                        if s is not None and col in s.index:
                            equity = s[col]
                            break
                    for row_name in ("Total Debt", "Long Term Debt"):
                        s = _row(bal, row_name)
                        if s is not None and col in s.index:
                            total_debt = s[col]
                            break
                    for row_name in ("Cash And Cash Equivalents", "Cash",
                                     "Cash And Short Term Investments"):
                        s = _row(bal, row_name)
                        if s is not None and col in s.index:
                            cash = s[col]
                            break

                # ── Preço próximo à data fiscal ───────────────────────
                price = None
                if not hist_px.empty:
                    target = pd.Timestamp(dt_str)
                    diffs  = (hist_px.index - target).map(abs)
                    price  = float(hist_px.iloc[diffs.argmin()])

                # ── Cálculo dos múltiplos ─────────────────────────────
                # margens: razão de fluxos anualizados → anualização cancela
                pe = pb = ev_ebitda = roe = margem = None

                if net_income and revenue and revenue != 0:
                    margem = round((net_income / revenue) * 100, 2)

                if net_income and equity and equity > 0:
                    roe = round((net_income / equity) * 100, 2)

                if price and shares and net_income and net_income > 0:
                    mktcap = price * shares
                    pe = round(mktcap / net_income, 2)
                    if equity and equity > 0:
                        pb = round(mktcap / equity, 2)
                    if ebitda and ebitda > 0:
                        ev = mktcap + (total_debt or 0) - (cash or 0)
                        ev_ebitda = round(ev / ebitda, 2)

                # sanidade: descarta valores absurdos
                pe        = pe        if pe        and 0 < pe        < 500 else None
                pb        = pb        if pb        and 0 < pb        < 100 else None
                ev_ebitda = ev_ebitda if ev_ebitda and 0 < ev_ebitda < 300 else None
                roe       = roe       if roe       and -200 < roe    < 500 else None

                resultados.append({
                    "data":      dt_str,
                    "pe":        pe,
                    "pb":        pb,
                    "ps":        None,
                    "ev_ebitda": ev_ebitda,
                    "dy":        None,
                    "roe":       roe,
                    "roic":      None,
                    "margem":    margem,
                    "_fonte":    fonte,
                })
            except Exception:
                continue

        return resultados

    except Exception as e:
        logger.warning(f"[fmp] fallback yfinance falhou para {ticker}: {e}")
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_multiplos_historicos(ticker: str, anos: int = 5) -> list[dict]:
    """
    Busca P/L, P/VP, EV/EBITDA, DY, ROE e ROIC históricos.
    Para ativos BR (.SA): prefere CVM (dados oficiais) antes do FMP.
    Para EUA: usa FMP diretamente.
    """
    is_br = ticker.upper().endswith(".SA")

    # ── Ativos BR: CVM primeiro (dados oficiais IFRS brasileiros) ────────────
    if is_br:
        try:
            from utils.cvm_client import get_multiplos_historicos_cvm
            cvm = get_multiplos_historicos_cvm(ticker, anos=anos)
            if cvm:
                return cvm
        except Exception:
            pass

    # ── FMP (EUA ou fallback para BR) ────────────────────────────────────────
    t    = ticker.replace(".SA", "").upper()
    data = _get("ratios", {"symbol": t, "limit": min(anos * 4, FMP_MAX_LIMIT)})

    if not data or not isinstance(data, list):
        # Fallback yfinance quando FMP retorna vazio (ex: 402 premium)
        return _get_multiplos_historicos_yf(ticker, min(anos, 3))

    resultados = []
    for item in data[: anos * 4]:
        try:
            pe  = _safe_float(item.get("priceEarningsRatio"))
            pb  = _safe_float(item.get("priceToBookRatio"))
            ps  = _safe_float(item.get("priceToSalesRatio"))
            evm = _safe_float(item.get("enterpriseValueMultiple"))
            dy  = _safe_pct(item.get("dividendYield"))
            roe = _safe_pct(item.get("returnOnEquity"))
            roi = _safe_pct(item.get("returnOnInvestedCapital"))
            mrg = _safe_pct(item.get("netProfitMargin"))

            resultados.append({
                "data":      item.get("date", ""),
                "pe":        pe,
                "pb":        pb,
                "ps":        ps,
                "ev_ebitda": evm,
                "dy":        dy,
                "roe":       roe,
                "roic":      roi,
                "margem":    mrg,
            })
        except Exception:
            continue

    if not resultados and is_br:
        return _get_multiplos_historicos_yf(ticker, min(anos, 3))

    return resultados


@st.cache_data(ttl=86400, show_spinner=False)
def get_key_metrics_historico(ticker: str, anos: int = 5) -> list[dict]:
    """
    Métricas chave históricas trimestrais via /key-metrics.
    Útil para ver tendência de ROIC, FCF e alavancagem ao longo do tempo.
    """
    t = ticker.replace(".SA", "").upper()
    data = _get("key-metrics", {"symbol": t, "limit": min(anos * 4, FMP_MAX_LIMIT)})

    if not data or not isinstance(data, list):
        return []

    resultados = []
    for item in data:
        try:
            resultados.append({
                "data":          item.get("date", ""),
                "roic":          _safe_pct(item.get("roic")),
                "fcf_per_share": _safe_float(item.get("freeCashFlowPerShare")),
                "div_yield":     _safe_pct(item.get("dividendYield")),
                "debt_equity":   _safe_float(item.get("debtToEquity")),
                "current_ratio": _safe_float(item.get("currentRatio")),
                "ev_ebitda":     _safe_float(item.get("enterpriseValueOverEBITDA")),
                "pe_ratio":      _safe_float(item.get("peRatio")),
                "pb_ratio":      _safe_float(item.get("pbRatio")),
                "revenue_growth": _safe_float(item.get("revenueGrowth")),
            })
        except Exception:
            continue

    return resultados


def get_multiplos_medios(ticker: str, anos: int = 5) -> dict:
    """
    Calcula estatísticas históricas de múltiplos para contextualizar o valuation atual.

    Retorna dict com chaves 'pe', 'pb', 'ev_ebitda', 'dy', 'roe', 'roic'.
    Cada valor é None ou um dict: {'media', 'min', 'max', 'atual'}.
    Retorna {} se FMP não tiver dados para o ticker.
    """
    historico = get_multiplos_historicos(ticker, anos)
    if not historico:
        return {}

    def _stats(campo: str) -> dict | None:
        raw = [
            float(h[campo]) for h in historico
            if h.get(campo) is not None
            and float(h[campo]) > 0
            and float(h[campo]) < 999
        ]
        if not raw:
            return None
        atual = raw[0]  # mais recente — capturado antes de qualquer filtragem

        # Filtra outliers extremos via IQR (2.5×) para não distorcer range histórico
        # Ex: P/L ~1x durante trimestre de lucro quase-zero infla a média
        vals = raw
        if len(raw) >= 4:
            arr = sorted(raw)
            mid = len(arr) // 4
            q1, q3 = arr[mid], arr[3 * mid]
            iqr = q3 - q1
            if iqr > 0:
                lo = max(0.01, q1 - 2.5 * iqr)
                hi = q3 + 2.5 * iqr
                filtered = [v for v in raw if lo <= v <= hi]
                if filtered:
                    vals = filtered

        return {
            "media": round(sum(vals) / len(vals), 2),
            "min":   round(min(vals), 2),
            "max":   round(max(vals), 2),
            "atual": round(atual, 2),
        }

    return {
        "pe":        _stats("pe"),
        "pb":        _stats("pb"),
        "ev_ebitda": _stats("ev_ebitda"),
        "dy":        _stats("dy"),
        "roe":       _stats("roe"),
        "roic":      _stats("roic"),
    }


# ── Peers ─────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def get_peers(ticker: str) -> list[str]:
    """
    Retorna lista de peers (concorrentes do mesmo setor) via /stock_peers.
    Ex: 'AAPL' → ['MSFT', 'GOOGL', 'META', 'AMZN', 'NVDA']
    Limita a 8 peers.
    """
    t = ticker.replace(".SA", "").upper()
    data = _get("stock-peers", {"symbol": t})

    if not data or not isinstance(data, list):
        return []

    # Nova estrutura FMP /stable: lista de dicts com 'symbol'
    if isinstance(data[0], dict) and "symbol" in data[0]:
        return [p["symbol"] for p in data if isinstance(p, dict) and p.get("symbol") and p["symbol"] != t][:8]

    # Estrutura antiga: [{peersList: [...]}]
    item = data[0]
    if isinstance(item, dict):
        peers = item.get("peersList", [])
        return [p for p in peers if p and p != t][:8]

    return []


# ── Earnings Calendar ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)   # 1 h — datas podem mudar
def get_earnings_calendar(
    tickers:     list[str] | None = None,
    data_inicio: str | None       = None,
    data_fim:    str | None       = None,
) -> list[dict]:
    """
    Busca calendário de earnings via /earning_calendar.
    Se `tickers` for fornecido, filtra apenas os da lista.
    data_inicio / data_fim: formato YYYY-MM-DD (padrão: hoje até +60 dias).

    Cada item retornado:
        {'ticker', 'data' (str YYYY-MM-DD), 'eps_est', 'eps_real',
         'receita_est', 'receita_real', 'hora', 'surpresa' (% float|None)}
    """
    import datetime as _dt

    hoje  = _dt.date.today()
    inicio = data_inicio or hoje.strftime("%Y-%m-%d")
    fim    = data_fim or (hoje + _dt.timedelta(days=60)).strftime("%Y-%m-%d")

    data = _get("earnings-calendar", {"from": inicio, "to": fim})

    if not data or not isinstance(data, list):
        return []

    tickers_set: set[str] = set()
    if tickers:
        tickers_set = {t.replace(".SA", "").upper() for t in tickers}

    eventos = []
    for item in data:
        symbol = (item.get("symbol") or "").upper()
        if tickers_set and symbol not in tickers_set:
            continue

        eps_r = _safe_float(item.get("eps"))
        eps_e = _safe_float(item.get("epsEstimated"))
        surpresa = None
        if eps_r is not None and eps_e is not None and eps_e != 0:
            surpresa = round((eps_r - eps_e) / abs(eps_e) * 100, 1)

        try:
            eventos.append({
                "ticker":        symbol,
                "data":          item.get("date", ""),
                "eps_est":       eps_e,
                "eps_real":      eps_r,
                "receita_est":   _safe_float(item.get("revenueEstimated")),
                "receita_real":  _safe_float(item.get("revenue")),
                "hora":          item.get("time", "amc"),
                "surpresa":      surpresa,
                "ano_fiscal":    item.get("fiscalDateEnding", ""),
            })
        except Exception:
            continue

    return sorted(eventos, key=lambda x: x["data"])


# ── Funções para backfill histórico (sem @st.cache_data — uso em ETL) ─────────

def get_ratios_trimestrais(ticker: str, limit: int = 40) -> list[dict]:
    """
    Busca múltiplos históricos via /ratios (quarterly ou annual fallback).
    quarter é premium (402) — fallback para annual.
    limit=40 = 10 anos. Sem cache — uso em scripts ETL.
    """
    t    = ticker.replace(".SA", "").upper()
    data = _get("ratios", {"symbol": t, "period": "quarter", "limit": min(limit, FMP_MAX_LIMIT)})
    if isinstance(data, list) and data:
        return data
    # Fallback: annual (gratuito no free tier)
    data = _get("ratios", {"symbol": t, "limit": min(limit, FMP_MAX_LIMIT)})
    return data if isinstance(data, list) else []


def get_key_metrics_trimestrais(ticker: str, limit: int = 40) -> list[dict]:
    """
    Busca métricas-chave via /key-metrics (quarterly ou annual fallback).
    quarter é premium (402) — fallback para annual.
    limit=40. Sem cache — uso em scripts ETL.
    """
    t    = ticker.replace(".SA", "").upper()
    data = _get("key-metrics", {"symbol": t, "period": "quarter", "limit": min(limit, FMP_MAX_LIMIT)})
    if isinstance(data, list) and data:
        return data
    # Fallback: annual (gratuito no free tier)
    data = _get("key-metrics", {"symbol": t, "limit": min(limit, FMP_MAX_LIMIT)})
    return data if isinstance(data, list) else []


# ── Perfil da empresa ─────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def get_profile(ticker: str) -> dict:
    """
    Perfil completo: setor, indústria, descrição, market cap, CEO, etc.
    Retorna {} se o ticker não for encontrado.
    """
    t = ticker.replace(".SA", "").upper()
    data = _get("profile", {"symbol": t})

    if not data or not isinstance(data, list):
        return {}

    p = data[0]
    return {
        "nome":        p.get("companyName", ""),
        "setor":       p.get("sector", ""),
        "industria":   p.get("industry", ""),
        "descricao":   (p.get("description", "") or "")[:600],
        "market_cap":  _safe_float(p.get("mktCap")),
        "funcionarios": p.get("fullTimeEmployees"),
        "ceo":         p.get("ceo", ""),
        "website":     p.get("website", ""),
        "exchange":    p.get("exchangeShortName", ""),
        "pais":        p.get("country", ""),
        "moeda":       p.get("currency", ""),
        "ipo_date":    p.get("ipoDate", ""),
        "beta":        _safe_float(p.get("beta")),
        "preco":       _safe_float(p.get("price")),
        "logo_url":    p.get("image", ""),
    }


# ── Financial Scores (Altman Z-Score + Piotroski F-Score) ─────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def get_financial_scores(ticker: str) -> dict:
    """
    Busca Altman Z-Score e Piotroski F-Score via /financial-scores.
    Retorna {} se o ticker não for encontrado.

    Campos retornados:
      altmanZScore, piotroskiScore,
      workingCapital, totalAssets, retainedEarnings, ebit, marketCap,
      totalLiabilities, totalCurrentAssets, totalCurrentLiabilities,
      cashAndCashEquivalents, netReceivables
    """
    t = ticker.replace(".SA", "").upper()
    data = _get("financial-scores", {"symbol": t})

    if not data or not isinstance(data, list):
        return {}

    p = data[0]
    return {
        "altman_z_score":    _safe_float(p.get("altmanZScore")),
        "piotroski_score":   _safe_float(p.get("piotroskiScore")),
        "working_capital":   _safe_float(p.get("workingCapital")),
        "total_assets":      _safe_float(p.get("totalAssets")),
        "retained_earnings": _safe_float(p.get("retainedEarnings")),
        "ebit":              _safe_float(p.get("ebit")),
        "market_cap":        _safe_float(p.get("marketCap")),
        "total_liabilities": _safe_float(p.get("totalLiabilities")),
        "current_assets":    _safe_float(p.get("totalCurrentAssets")),
        "current_liabilities": _safe_float(p.get("totalCurrentLiabilities")),
        "cash":              _safe_float(p.get("cashAndCashEquivalents")),
        "net_receivables":   _safe_float(p.get("netReceivables")),
    }


# ── Analyst Consensus (Buy/Hold/Sell) ────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_analyst_grades(ticker: str) -> dict:
    """
    Busca consenso de analistas via /grades-consensus.
    Retorna {} se o ticker não for encontrado.

    Campos retornados:
      strongBuy, buy, hold, sell, strongSell, consensus, numAnalysts
    """
    t = ticker.replace(".SA", "").upper()
    data = _get("grades-consensus", {"symbol": t})

    if not data or not isinstance(data, list):
        return {}

    p = data[0]
    return {
        "strong_buy":  _safe_float(p.get("strongBuy")),
        "buy":         _safe_float(p.get("buy")),
        "hold":        _safe_float(p.get("hold")),
        "sell":        _safe_float(p.get("sell")),
        "strong_sell": _safe_float(p.get("strongSell")),
        "consensus":   p.get("consensus", ""),
        "num_analysts": _safe_float(p.get("numAnalysts")),
    }


# ── Analyst Estimates (Revenue, EBITDA, EPS) ─────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_analyst_estimates(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict]:
    """
    Busca estimativas de analistas via /analyst-estimates.
    period: 'annual' ou 'quarter'
    Retorna [] se o ticker não for encontrado.

    Campos retornados por período:
      date, estimatedRevenue, estimatedEbitda, estimatedEps,
      numberAnalystEstimatedRevenue, numberAnalystEstimatedEps,
      estimatedRevenueGrowth
    """
    t = ticker.replace(".SA", "").upper()
    data = _get("analyst-estimates", {"symbol": t, "period": period})

    if not data or not isinstance(data, list):
        return []

    resultados = []
    for item in data:
        try:
            resultados.append({
                "date":                item.get("date", ""),
                "estimated_revenue":   _safe_float(item.get("revenueAvg") or item.get("estimatedRevenue")),
                "estimated_ebitda":    _safe_float(item.get("ebitdaAvg") or item.get("estimatedEbitda")),
                "estimated_eps":       _safe_float(item.get("epsAvg") or item.get("estimatedEps")),
                "num_analysts_revenue": _safe_float(item.get("numAnalystEstimatedRevenue") or item.get("numAnalystsRevenue")),
                "num_analysts_eps":    _safe_float(item.get("numAnalystEstimatedEps") or item.get("numAnalystsEps")),
                "revenue_growth_est":  _safe_float(item.get("estimatedRevenueGrowth")),
            })
        except Exception:
            continue

    return resultados[:limit]
