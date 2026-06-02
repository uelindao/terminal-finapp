"""
utils/brapi_client.py
Cliente para BRAPI (brapi.dev) -- dados de acoes brasileiras.

Free tier: 15.000 requests/mes.
Foco: dados fundamentalistas atuais + historico de precos B3.

BRAPI nao tem historico de DRE/balanco -- apenas snapshot atual.
Usado para complementar Alpha Vantage com dados B3 em tempo real
e para preencher campos nao disponiveis no yfinance.
"""
from __future__ import annotations
import requests
import streamlit as st
from utils.logger import get_logger

logger = get_logger(__name__)

BRAPI_BASE = "https://brapi.dev/api"


def _get_token() -> str:
    try:
        return st.secrets["brapi"]["token"]
    except Exception:
        return ""


@st.cache_data(ttl=3600, show_spinner=False)
def get_quote(ticker: str) -> dict:
    """
    Busca dados atuais de um ativo B3 via BRAPI.
    ticker: formato sem .SA (ex: PETR4, WEGE3, MXRF11)

    Retorna dict com:
    {
      'preco':        float,
      'var_1d':       float (%),
      'pe':           float,
      'pb':           float,
      'dy':           float (%),
      'roe':          float (%),
      'margem':       float (%),
      'ev_ebitda':    float,
      'market_cap':   float,
      'nome':         str,
      'setor':        str,
      'volume':       float,
      'beta':         float,
    }
    """
    token = _get_token()
    t = ticker.replace(".SA", "").upper()

    try:
        resp = requests.get(
            f"{BRAPI_BASE}/quote/{t}",
            params={
                "token":         token,
                "fundamental":   "true",
                "dividends":     "true",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            return {}

        q = results[0]
        fd = q.get("fundamentalData") or q.get("fundamentals") or {}

        def _sf(val):
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        # DY pode vir como 0.08 (8%) ou 8.0 -- normaliza
        _dy_raw = _sf(fd.get("dividendYield") or q.get("dividendYield"))
        if _dy_raw is not None and _dy_raw < 1.0:
            _dy_raw = _dy_raw * 100  # converte de decimal para %

        return {
            "preco":      _sf(q.get("regularMarketPrice")),
            "var_1d":     _sf(q.get("regularMarketChangePercent")),
            "pe":         _sf(fd.get("priceEarnings") or q.get("priceEarnings")),
            "pb":         _sf(fd.get("priceToBook") or q.get("priceToBook")),
            "dy":         _dy_raw,
            "roe":        _sf(fd.get("roe") or q.get("roe")),
            "margem":     _sf(fd.get("netMargin") or fd.get("profit_margin")),
            "ev_ebitda":  _sf(fd.get("enterpriseValueOverEbitda")),
            "market_cap": _sf(q.get("marketCap")),
            "nome":       q.get("longName") or q.get("shortName", ""),
            "setor":      fd.get("sector") or q.get("sector", ""),
            "volume":     _sf(q.get("regularMarketVolume")),
            "beta":       _sf(q.get("beta")),
        }

    except Exception as e:
        logger.warning(f"[brapi] falha para {t}: {e}")
        return {}


@st.cache_data(ttl=86400, show_spinner=False)
def get_historico_precos(
    ticker: str,
    range_: str = "5y",
    interval: str = "1mo",
) -> list[dict]:
    """
    Historico de precos mensais via BRAPI.
    range_: '1mo', '3mo', '6mo', '1y', '2y', '5y'
    interval: '1d', '1wk', '1mo'

    Retorna lista de {'date', 'open', 'high', 'low', 'close', 'volume'}
    """
    token = _get_token()
    t = ticker.replace(".SA", "").upper()

    try:
        resp = requests.get(
            f"{BRAPI_BASE}/quote/{t}",
            params={
                "token":    token,
                "range":    range_,
                "interval": interval,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            return []

        hist = results[0].get("historicalDataPrice", [])
        return hist

    except Exception as e:
        logger.warning(f"[brapi] historico para {t}: {e}")
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def get_score_snapshot_brapi(ticker: str) -> float | None:
    """
    Calcula score snapshot (ponto unico atual) usando
    dados fundamentalistas da BRAPI.

    Retorna score 0-100 para usar como ancora do proxy tecnico:
    - Multiplica o proxy tecnico pelo score da BRAPI
    - Garante que o proxy reflete a qualidade fundamentalista atual
    """
    dados = get_quote(ticker)
    if not dados:
        return None

    score  = 0.0
    max_p  = 0.0
    ok     = 0

    # P/E
    pe = dados.get("pe")
    max_p += 15
    if pe is not None and pe > 0:
        ok += 1
        if pe <= 10:    score += 15
        elif pe <= 18:  score += 10
        elif pe <= 30:  score += 5

    # P/B
    pb = dados.get("pb")
    max_p += 10
    if pb is not None and pb > 0:
        ok += 1
        if pb <= 1.0:   score += 10
        elif pb <= 2.5: score += 7
        elif pb <= 5.0: score += 4

    # ROE
    roe = dados.get("roe")
    max_p += 20
    if roe is not None:
        ok += 1
        roe_pct = roe * 100 if abs(roe) < 2 else roe
        if roe_pct > 20:   score += 20
        elif roe_pct > 12: score += 15
        elif roe_pct > 6:  score += 10
        elif roe_pct > 0:  score += 5
        else:              score -= 5

    # Margem
    mrg = dados.get("margem")
    max_p += 15
    if mrg is not None:
        ok += 1
        mrg_pct = mrg * 100 if abs(mrg) < 2 else mrg
        if mrg_pct > 15:   score += 15
        elif mrg_pct > 8:  score += 10
        elif mrg_pct > 3:  score += 6
        elif mrg_pct >= 0: score += 2
        else:              score -= 5

    # DY
    dy = dados.get("dy")
    max_p += 10
    if dy is not None and 0 < dy <= 30:
        ok += 1
        if dy > 8:    score += 10
        elif dy > 5:  score += 7
        elif dy > 2:  score += 4

    # EV/EBITDA
    ev = dados.get("ev_ebitda")
    max_p += 10
    if ev is not None and ev > 0:
        ok += 1
        if ev < 6:    score += 10
        elif ev < 12: score += 7
        elif ev < 20: score += 3

    if ok < 2 or max_p == 0:
        return None

    return round(max(0.0, min(100.0, score / max_p * 100)), 1)
