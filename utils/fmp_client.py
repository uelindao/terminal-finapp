"""
utils/fmp_client.py
Cliente para Financial Modeling Prep (FMP) API.
Documentação: https://financialmodelingprep.com/developer/docs

Endpoints usados:
  /ratios/{ticker}         — múltiplos históricos (P/E, P/B, ROE, ROIC…)
  /key-metrics/{ticker}    — métricas chave históricas (FCF, D/E, etc.)
  /stock_peers             — peers por setor
  /earning_calendar        — calendário de earnings
  /profile/{ticker}        — perfil da empresa

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

FMP_BASE = "https://financialmodelingprep.com/api/v3"


# ── Helpers internos ──────────────────────────────────────────────────────────

def _get_keys() -> list[str]:
    """Retorna lista de FMP_API_KEYs configuradas (ordem de tentativa)."""
    keys = []
    try:
        k1 = st.secrets.get("FMP_API_KEY", "")
        if k1: keys.append(k1)
        k2 = st.secrets.get("FMP_API_KEY_2", "")
        if k2: keys.append(k2)
    except Exception:
        pass
    if keys:
        logger.debug(f"{len(keys)} FMP_API_KEY(s) configurada(s)")
    else:
        logger.warning("[fmp] nenhuma FMP_API_KEY configurada em secrets.toml")
    return keys


def _get(endpoint: str, params: dict | None = None) -> dict | list:
    """
    GET genérico para a API FMP com fallback entre múltiplas chaves.
    Tenta cada chave em ordem; se uma retorna 403, passa para a próxima.
    Retorna [] em caso de todas falharem.
    """
    keys = _get_keys()
    if not keys:
        return []

    p = dict(params or {})

    for i, key in enumerate(keys):
        try:
            p["apikey"] = key
            resp = requests.get(f"{FMP_BASE}/{endpoint}", params=p, timeout=10)

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

@st.cache_data(ttl=86400, show_spinner=False)
def get_multiplos_historicos(ticker: str, anos: int = 5) -> list[dict]:
    """
    Busca P/L, P/VP, EV/EBITDA, DY, ROE e ROIC históricos (endpoint /ratios).
    Retorna lista de dicts do mais recente ao mais antigo.

    Exemplo de item:
        {'data': '2024-12-31', 'pe': 28.5, 'pb': 6.2,
         'ev_ebitda': 18.3, 'dy': 0.8, 'roe': 35.1, 'roic': 22.4, 'margem': 12.1}
    """
    t = ticker.replace(".SA", "").upper()
    data = _get(f"ratios/{t}", {"limit": anos * 4})

    if not data or not isinstance(data, list):
        return []

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

    return resultados


@st.cache_data(ttl=86400, show_spinner=False)
def get_key_metrics_historico(ticker: str, anos: int = 5) -> list[dict]:
    """
    Métricas chave históricas trimestrais via /key-metrics.
    Útil para ver tendência de ROIC, FCF e alavancagem ao longo do tempo.
    """
    t = ticker.replace(".SA", "").upper()
    data = _get(f"key-metrics/{t}", {"limit": anos * 4, "period": "quarter"})

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
        vals = [
            h[campo] for h in historico
            if h.get(campo) is not None
            and float(h[campo]) > 0
            and float(h[campo]) < 999
        ]
        if not vals:
            return None
        return {
            "media": round(sum(vals) / len(vals), 2),
            "min":   round(min(vals), 2),
            "max":   round(max(vals), 2),
            "atual": round(vals[0], 2),   # mais recente primeiro
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
    data = _get("stock_peers", {"symbol": t})

    if not data or not isinstance(data, list):
        return []

    # FMP retorna lista com um item contendo 'peersList'
    item = data[0] if data else {}
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

    data = _get("earning_calendar", {"from": inicio, "to": fim})

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


# ── Perfil da empresa ─────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def get_profile(ticker: str) -> dict:
    """
    Perfil completo: setor, indústria, descrição, market cap, CEO, etc.
    Retorna {} se o ticker não for encontrado.
    """
    t = ticker.replace(".SA", "").upper()
    data = _get(f"profile/{t}")

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
