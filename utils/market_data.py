"""
Helper centralizada de dados de mercado — yfinance + cache.

Por que existir?
  - Várias páginas baixam yf.download(tickers, period="5d") múltiplas vezes
    por render (Home, Dashboard, Watchlists, Portfolio).
  - Cada chamada vai pra rede mesmo com tickers iguais (cache_data por
    closure não compartilha entre módulos).
  - Aqui: uma helper @st.cache_data global, batches grandes, TTL único.

Uso:
    from utils.market_data import bulk_close_history

    series = bulk_close_history(tuple(["WEGE3.SA","PETR4.SA"]), period="1mo")
    # series = {"WEGE3.SA": [12.3, 12.4, ...], "PETR4.SA": [...]}

Garantias:
  - Argumentos hashable (tuple) — st.cache_data exige.
  - Período padrão "1mo" cobre sparkline 30d com folga.
  - TTL 300s (5min) — alinhado com taxa de atualização do mercado intraday.
  - Tickers já com sufixo .SA (mapeamento upstream).
  - Falhas silenciosas: ticker sem dado retorna [] (não None).
"""
from __future__ import annotations

import logging
import threading
import time

import pandas as pd
import yfinance as yf

# st real em produção; stub no-op no ETL (GitHub Actions sem streamlit).
# Mesmo padrão de health_engine/macro_state — torna esta fachada importável
# pelo ETL, requisito para centralizar o acesso ao yfinance.
from utils.st_fallback import st  # noqa: F401

logger = logging.getLogger(__name__)
logging.getLogger('yfinance').setLevel(logging.CRITICAL)


def buscar_ativo_yahoo(query: str) -> list[dict]:
    """
    Busca tickers no Yahoo Finance search API (autocomplete de busca de ativos).
    Retorna a lista de 'quotes' (ou [] em falha). Era duplicada em Home e Research.
    """
    import requests
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
    try:
        r = requests.get(url, headers={'user-agent': 'Mozilla/5.0'}, timeout=5)
        return r.json().get('quotes', [])
    except Exception as e:
        logger.debug(f"[buscar_ativo_yahoo] falha: {e}")
        return []


@st.cache_data(ttl=300, show_spinner=False)
def close_series(ticker: str, period: str = "1y", auto_adjust: bool = True) -> pd.Series:
    """
    Série de Close (tz-naive, dropna) de UM ticker. Cacheada (5min) — substitui o
    padrão repetido `yf.Ticker(t).history(period=p, auto_adjust=True)['Close'].dropna()`
    espalhado pelo terminal, compartilhando o cache de benchmarks comuns (^BVSP,
    ^GSPC, ^VIX, BRL=X) entre funções/páginas e reduzindo o risco de rate-limit.

    Retorna Series vazia em falha/sem dados (nunca levanta).
    """
    try:
        h = yf.Ticker(ticker).history(period=period, auto_adjust=auto_adjust)
        if h is None or h.empty or "Close" not in h.columns:
            return pd.Series(dtype=float)
        if isinstance(h.columns, pd.MultiIndex):
            h.columns = h.columns.get_level_values(0)
        s = h["Close"].dropna()
        if hasattr(s.index, "tz") and s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        return s
    except Exception as e:
        logger.warning(f"[market_data] close_series({ticker},{period}) falhou: {e}")
        return pd.Series(dtype=float)


@st.cache_data(ttl=300, show_spinner=False)
def bulk_close_history(
    tickers: tuple[str, ...],
    period: str = "1mo",
) -> dict[str, list[float]]:
    """
    Baixa séries de Close para múltiplos tickers em UMA chamada batch.

    Args:
        tickers: tuple de tickers (e.g. ("WEGE3.SA", "AAPL"))
        period: período yfinance ("5d","1mo","3mo","1y", etc.)

    Returns:
        dict {ticker: [floats ordenados cronologicamente]}
        Tickers sem dado retornam [].
    """
    if not tickers:
        return {}

    out: dict[str, list[float]] = {t: [] for t in tickers}
    try:
        raw = yf.download(
            list(tickers),
            period      = period,
            auto_adjust = True,
            progress    = False,
            threads     = True,
        )
        if raw is None or raw.empty:
            return out

        # Extrai os Close
        if isinstance(raw.columns, pd.MultiIndex):
            try:
                close = raw.xs('Close', axis=1, level=0)
            except KeyError:
                close = raw.xs('Close', axis=1, level=1)
        else:
            close = raw.get('Close', raw)

        if isinstance(close, pd.Series):
            # single ticker case
            close = close.to_frame(name=tickers[0])
        close = close.ffill()

        for t in tickers:
            if t in close.columns:
                s = close[t].dropna()
                if len(s) > 0:
                    out[t] = [float(x) for x in s.tolist()]
    except Exception as e:
        logger.warning(f"[market_data] bulk_close_history({len(tickers)}) falhou: {e}")

    return out


@st.cache_data(ttl=300, show_spinner=False)
def bulk_var_dia(
    tickers: tuple[str, ...],
) -> dict[str, dict]:
    """
    Wrapper otimizado para o caso muito comum de "preço atual + var dia".
    Roda bulk_close_history(period="5d") e calcula derivadas.

    Returns:
        {ticker: {"preco": float, "var_1d": float}}
    """
    series = bulk_close_history(tickers, period="5d")
    out: dict[str, dict] = {}
    for t, s in series.items():
        if len(s) >= 2:
            p_atual = s[-1]
            p_ontem = s[-2]
            try:
                var = ((p_atual / p_ontem) - 1) * 100 if p_ontem > 0 else 0.0
            except Exception:
                var = 0.0
            out[t] = {"preco": p_atual, "var_1d": var}
    return out


# ═══════════════════════════════════════════════════════════════════════════
# CIRCUIT BREAKER + ENTRADA ÚNICA PARA yfinance.info
# ═══════════════════════════════════════════════════════════════════════════
# Problema: `yf.Ticker(t).info` é a chamada mais frágil do terminal — retorna
# "Too Many Requests" sob carga e era invocada crua em ~10 lugares, cada um com
# seu try/except. Quando o Yahoo limitava, dezenas de telas degradavam em
# silêncio e o app continuava martelando o endpoint a cada render.
#
# Aqui isso vira UM ponto de passagem com disjuntor: após N falhas seguidas o
# circuito ABRE e a fachada para de bater no Yahoo por um período de descanso,
# servindo {} (os chamadores já tratam dict vazio). Passado o cooldown, entra
# em meia-abertura e tenta de novo. provider_health() expõe o estado p/ a UI.

class _CircuitBreaker:
    """Disjuntor simples e thread-safe (yfinance baixa em threads)."""

    def __init__(self, name: str, fail_threshold: int = 5, cooldown_s: float = 300.0):
        self.name = name
        self.fail_threshold = fail_threshold
        self.cooldown_s = cooldown_s
        self._fails = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        """True = circuito aberto (pular a chamada). Meia-abertura após cooldown."""
        with self._lock:
            if self._opened_at == 0.0:
                return False
            if time.time() - self._opened_at >= self.cooldown_s:
                # cooldown vencido → meia-abertura: zera e permite 1 tentativa
                self._opened_at = 0.0
                self._fails = 0
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._fails = 0
            self._opened_at = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._fails += 1
            if self._fails >= self.fail_threshold and self._opened_at == 0.0:
                self._opened_at = time.time()
                logger.warning(
                    f"[market_data] circuito '{self.name}' ABERTO após "
                    f"{self._fails} falhas — descanso de {self.cooldown_s:.0f}s."
                )

    def status(self) -> dict:
        with self._lock:
            aberto = self._opened_at != 0.0 and (
                time.time() - self._opened_at < self.cooldown_s
            )
            restante = (
                max(0.0, self.cooldown_s - (time.time() - self._opened_at))
                if aberto else 0.0
            )
            return {
                "provider": self.name,
                "aberto": aberto,
                "falhas_consecutivas": self._fails,
                "cooldown_restante_s": round(restante, 1),
            }


# Disjuntor global do yfinance.info (estado por processo).
_YF_INFO_BREAKER = _CircuitBreaker("yfinance.info", fail_threshold=5, cooldown_s=300.0)


def yf_info(ticker: str, *, force: bool = False) -> dict:
    """
    ENTRADA ÚNICA para `yfinance.Ticker(ticker).info` em todo o terminal.

    Protegida por circuit breaker: se o Yahoo está limitando (circuito aberto),
    retorna {} imediatamente em vez de bater no endpoint. `force=True` ignora o
    disjuntor (refresh explícito disparado pelo usuário).

    Nunca levanta. Retorna {} em falha — os chamadores já tratam dict vazio.
    Não é cacheada de propósito: o estado do disjuntor precisa refletir cada
    tentativa real; cache de fundamentos é responsabilidade da camada acima.
    """
    if not force and _YF_INFO_BREAKER.is_open():
        logger.debug(f"[market_data] yf_info({ticker}) pulado — circuito aberto.")
        return {}
    try:
        info = yf.Ticker(ticker).info or {}
        # info "real" tem dezenas de chaves; um dict quase vazio sob rate-limit
        # é sintoma de bloqueio, não de ativo sem dado → conta como falha.
        if len(info) > 3:
            _YF_INFO_BREAKER.record_success()
            return info
        _YF_INFO_BREAKER.record_failure()
        return {}
    except Exception as e:
        _YF_INFO_BREAKER.record_failure()
        logger.warning(f"[market_data] yf_info({ticker}) falhou: {e}")
        return {}


def provider_health() -> dict:
    """Estado dos disjuntores de provedores — para uma tela de admin/diagnóstico."""
    return {"yfinance_info": _YF_INFO_BREAKER.status()}


# ═══════════════════════════════════════════════════════════════════════════
# FACHADA DE FUNDAMENTOS — cascata cache → BRAPI/FMP → yfinance.info
# ═══════════════════════════════════════════════════════════════════════════
# Devolve SEMPRE o mesmo shape (chaves do fundamentals_cache), venha de qual
# fonte vier. Páginas devem chamar isto (cache-first, allow_live=False); o ETL
# usa allow_live=True para popular o cache.

_FUND_KEYS = (
    "nome", "setor", "preco", "p/l", "p/vp", "dy%", "roe%",
    "margem%", "ev/ebitda", "market_cap", "beta",
)


def _fund_vazio(source: str = "") -> dict:
    d: dict = {k: None for k in _FUND_KEYS}
    d["qualidade_dados"] = None
    d["data_source"] = source
    return d


def _sf(val):
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _pct(val):
    """Normaliza margem/ROE/DY: yfinance entrega decimal (0.24); cache usa %."""
    f = _sf(val)
    if f is None:
        return None
    return round(f * 100, 2) if abs(f) < 2.0 else round(f, 2)


def _normalizar_cache(d: dict) -> dict:
    out = _fund_vazio(d.get("data_source") or "cache")
    out["qualidade_dados"] = d.get("qualidade_dados") or d.get("data_quality_pct")
    for k in _FUND_KEYS:
        if d.get(k) is not None:
            out[k] = d[k]
    return out


def _normalizar_brapi(q: dict) -> dict:
    out = _fund_vazio("brapi")
    out.update({
        "nome": q.get("nome"), "setor": q.get("setor"),
        "preco": q.get("preco"), "p/l": q.get("pe"), "p/vp": q.get("pb"),
        "dy%": q.get("dy"), "roe%": q.get("roe"), "margem%": q.get("margem"),
        "ev/ebitda": q.get("ev_ebitda"), "market_cap": q.get("market_cap"),
        "beta": q.get("beta"),
    })
    return out


def _normalizar_fmp(p: dict) -> dict:
    out = _fund_vazio("fmp")
    out.update({
        "nome": p.get("nome"), "setor": p.get("setor"),
        "preco": p.get("preco"), "market_cap": p.get("market_cap"),
        "beta": p.get("beta"),
    })
    return out


def _merge_yf_info(base: dict, ticker: str) -> dict:
    """Completa campos None do `base` com yfinance.info (via disjuntor)."""
    info = yf_info(ticker)
    if not info:
        return base
    candidatos = {
        "nome": info.get("longName") or info.get("shortName"),
        "setor": info.get("sector"),
        "preco": _sf(info.get("currentPrice") or info.get("regularMarketPrice")),
        "p/l": _sf(info.get("trailingPE") or info.get("forwardPE")),
        "p/vp": _sf(info.get("priceToBook")),
        "dy%": _pct(info.get("dividendYield") or info.get("trailingAnnualDividendYield")),
        "roe%": _pct(info.get("returnOnEquity")),
        "margem%": _pct(info.get("profitMargins")),
        "ev/ebitda": _sf(info.get("enterpriseToEbitda")),
        "market_cap": _sf(info.get("marketCap")),
        "beta": _sf(info.get("beta")),
    }
    preencheu = False
    for k, v in candidatos.items():
        if base.get(k) is None and v is not None:
            base[k] = v
            preencheu = True
    if preencheu and base.get("data_source") in (None, "", "cache_miss"):
        base["data_source"] = "yfinance"
    return base


def fundamentos(ticker: str, *, allow_live: bool = True) -> dict:
    """
    Snapshot fundamental de UM ticker, no shape canônico do fundamentals_cache.
    Substitui as ~123 chamadas cruas a `yfinance.Ticker().info` espalhadas.

    Cascata:
      1. cache Supabase (fundamentals_cache)  ← páginas param aqui (allow_live=False)
      2. provedor primário por mercado: BRAPI (.SA) / FMP (US)
      3. yfinance.info (via disjuntor) — completa lacunas / último recurso

    A escolha BR-vs-US e o fallback ficam DENTRO da fachada; o chamador nunca
    precisa saber a fonte. Nunca levanta — devolve dict de chaves None em falha.
    """
    # 1. cache Supabase
    try:
        from database.db import get_todos_fundamentos_cache
        d = get_todos_fundamentos_cache().get(ticker)
        if d and any(d.get(k) is not None for k in ("p/l", "p/vp", "roe%", "preco")):
            return _normalizar_cache(d)
    except Exception as e:
        logger.debug(f"[market_data] fundamentos: cache indisponível p/ {ticker}: {e}")

    if not allow_live:
        return _fund_vazio("cache_miss")

    is_br = ticker.endswith(".SA")

    # 2. provedor primário por mercado (lazy import: clientes dependem de
    #    streamlit/secrets — se indisponível no ETL, o try cai p/ o yfinance).
    try:
        if is_br:
            from utils.brapi_client import get_quote
            q = get_quote(ticker)
            if q and q.get("preco") is not None:
                base = _normalizar_brapi(q)
                return _merge_yf_info(base, ticker)
        else:
            from utils.fmp_client import get_profile
            p = get_profile(ticker)
            if p and (p.get("preco") is not None or p.get("market_cap") is not None):
                base = _normalizar_fmp(p)
                return _merge_yf_info(base, ticker)
    except Exception as e:
        logger.debug(f"[market_data] fundamentos: provedor primário falhou p/ {ticker}: {e}")

    # 3. yfinance puro (último recurso)
    return _merge_yf_info(_fund_vazio("cache_miss"), ticker)


@st.cache_data(ttl=300, show_spinner=False)
def bulk_var_periodo(
    tickers: tuple[str, ...],
    period: str = "1mo",
) -> dict[str, dict]:
    """
    Wrapper completo: preço, var dia, var período e série 30d em uma chamada.

    Returns:
        {ticker: {"preco","var_1d","var_periodo","serie"}}
    """
    series = bulk_close_history(tickers, period=period)
    out: dict[str, dict] = {}
    for t, s in series.items():
        if len(s) >= 2:
            p_atual    = s[-1]
            p_ontem    = s[-2]
            p_inicial  = s[0]
            try:
                v_1d = ((p_atual / p_ontem)   - 1) * 100 if p_ontem > 0 else 0.0
                v_pd = ((p_atual / p_inicial) - 1) * 100 if p_inicial > 0 else 0.0
            except Exception:
                v_1d, v_pd = 0.0, 0.0
            out[t] = {
                "preco":       p_atual,
                "var_1d":      v_1d,
                "var_periodo": v_pd,
                "serie":       s[-30:],
            }
    return out
