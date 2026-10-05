"""Lightweight macro context with provenance and an hourly session refresh.

Legacy numeric fallbacks remain for callers that need a contingency value.
Models must check quality before interpreting those values as observations.
"""
import datetime
import math
import time

import streamlit as st
from utils.logger import get_logger

logger = get_logger(__name__)
SELIC_FALLBACK = 14.75
IPCA_FALLBACK = IPCA_12M_FALLBACK = 4.5
IPCA_MENSAL_FALLBACK = 0.45
VIX_FALLBACK = 15.0
TREASURY_10Y_FALLBACK = 4.5


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_macro_rapido() -> dict:
    values = {"selic": SELIC_FALLBACK, "ipca_12m": IPCA_12M_FALLBACK,
              "ipca_mensal": IPCA_MENSAL_FALLBACK, "vix": VIX_FALLBACK,
              "treasury_10y": TREASURY_10Y_FALLBACK}
    collected = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sources = {"selic": "BCB SGS 432", "ipca_12m": "BCB SGS 13522",
               "ipca_mensal": "BCB SGS 433", "vix": "Yahoo ^VIX",
               "treasury_10y": "Yahoo ^TNX"}
    quality = {k: {"observado": False, "status": "fallback", "fonte": source,
                   "referencia_em": None, "coletado_em": collected}
               for k, source in sources.items()}

    def accept(key, series, low, high):
        s = series.dropna()
        if s.empty:
            return
        value = float(s.iloc[-1])
        if math.isfinite(value) and low <= value <= high:
            values[key] = value
            reference = s.index[-1]
            quality[key].update(observado=True, status="observado",
                                referencia_em=str(reference.isoformat()
                                                  if hasattr(reference, "isoformat") else reference))

    try:
        from bcb import sgs
        start = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
        frame = sgs.get({"selic": 432, "ipca_mensal": 433, "ipca_12m": 13522}, start=start)
        for key, bounds in {"selic": (0, 50), "ipca_mensal": (-5, 5),
                            "ipca_12m": (-10, 50)}.items():
            if key in frame:
                accept(key, frame[key], *bounds)
    except Exception as exc:
        logger.warning("[macro_context] BCB indisponível: %s", exc)

    try:
        import yfinance as yf
        for key, ticker, bounds in [("vix", "^VIX", (0.01, 200)),
                                    ("treasury_10y", "^TNX", (0, 20))]:
            try:
                frame = yf.Ticker(ticker).history(period="5d")
                if "Close" in frame:
                    # ^TNX is a percentage, not an index scaled by ten.
                    accept(key, frame["Close"], *bounds)
            except Exception as exc:
                logger.warning("[macro_context] %s indisponível: %s", ticker, exc)
    except ImportError:
        pass

    observed = quality["selic"]["observado"] and quality["vix"]["observado"]
    if not observed:
        label = "contexto incompleto · valores de contingência"
    else:
        rate = "juros altos" if values["selic"] > 10 else "juros baixos"
        risk = "stress global" if values["vix"] > 20 else "risco controlado"
        label = f"{rate} / {risk}"
    quality["ipca"] = dict(quality["ipca_12m"])
    return {**{k: round(v, 2) for k, v in values.items()},
            "ipca": round(values["ipca_12m"], 2), "label": label,
            "qualidade": quality, "coletado_em": collected}


def garantir_macro_context() -> dict:
    """Refresh long-running sessions too; injected contexts stay intact for an hour."""
    now = time.time()
    previous = st.session_state.get("_macro_context_carregado_em")
    if "macro_context" not in st.session_state or (previous is not None and now - previous >= 3600):
        st.session_state["macro_context"] = _fetch_macro_rapido()
        st.session_state["_macro_context_carregado_em"] = now
    elif previous is None:
        st.session_state["_macro_context_carregado_em"] = now
    return st.session_state["macro_context"]


def atualizar_contexto_series(contexto: dict, brasil, global_) -> dict:
    """Merge dated observations without discarding quality or reviving fallbacks."""
    import pandas as pd
    result = dict(contexto or {})
    quality = {k: dict(v) for k, v in result.get("qualidade", {}).items()}
    fields = [(brasil, "Selic", "selic", (0, 50), "BCB SGS 432"),
              (brasil, "IPCA_12M", "ipca_12m", (-10, 50), "BCB SGS 433 · composição 12m"),
              (brasil, "IPCA", "ipca_mensal", (-5, 5), "BCB SGS 433"),
              (global_, "VIXCLS", "vix", (0.01, 200), "FRED VIXCLS"),
              (global_, "DGS10", "treasury_10y", (0, 20), "FRED DGS10")]
    for frame, column, key, bounds, source in fields:
        quality.setdefault(key, {"observado": False, "status": "não observado",
                                 "fonte": source, "referencia_em": None, "coletado_em": None})
        if frame is None or column not in frame:
            continue
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if series.empty:
            continue
        value = float(series.iloc[-1])
        if not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
            continue
        reference = pd.to_datetime(series.index[-1], utc=True, errors="coerce")
        if pd.isna(reference):
            continue
        old_reference = pd.to_datetime(quality[key].get("referencia_em"), utc=True, errors="coerce")
        if not pd.isna(old_reference) and old_reference > reference:
            continue
        result[key] = round(value, 2)
        quality[key] = {"observado": True, "status": "observado", "fonte": source,
                        "referencia_em": reference.isoformat(),
                        "coletado_em": frame.attrs.get("coletado_em")}
    if "ipca_12m" in result:
        result["ipca"] = result["ipca_12m"]
        quality["ipca"] = dict(quality["ipca_12m"])
    if quality["selic"]["observado"] and quality["vix"]["observado"]:
        rate = "juros altos" if result["selic"] > 10 else "juros baixos"
        risk = "stress global" if result["vix"] > 20 else "risco controlado"
        result["label"] = f"{rate} / {risk}"
    else:
        result["label"] = "contexto incompleto · valores de contingência"
    result["qualidade"] = quality
    return result
