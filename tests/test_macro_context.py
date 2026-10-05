from unittest.mock import patch
from types import SimpleNamespace

import pandas as pd
import pytest
import utils.macro_context as context


def uncached():
    return getattr(context._fetch_macro_rapido, "__wrapped__", context._fetch_macro_rapido)


def test_missing_sources_are_explicit_not_observations():
    with patch("bcb.sgs.get", side_effect=RuntimeError("offline")), patch("yfinance.Ticker", side_effect=RuntimeError("offline")):
        result = uncached()()
    assert all(not q["observado"] for q in result["qualidade"].values())
    assert "incompleto" in result["label"]
    assert result["qualidade"]["ipca"]["status"] == "fallback"


def test_real_observations_have_reference_dates_and_percent_units():
    dates = pd.to_datetime(["2026-08-01", "2026-09-01"])
    bcb = pd.DataFrame({"selic": [14, 13], "ipca_12m": [4.3, -0.1], "ipca_mensal": [0.3, -0.2]}, index=dates)
    def ticker(name):
        close = [15, 16] if name == "^VIX" else [4.1, 4.2]
        return SimpleNamespace(history=lambda **kw: pd.DataFrame({"Close": close}, index=dates))
    with patch("bcb.sgs.get", return_value=bcb), patch("yfinance.Ticker", side_effect=ticker):
        result = uncached()()
    assert result["treasury_10y"] == 4.2
    assert result["ipca_12m"] == -0.1
    assert all(q["observado"] for q in result["qualidade"].values())
    assert result["qualidade"]["vix"]["referencia_em"].startswith("2026-09-01")


def test_ambiguous_treasury_scale_is_rejected():
    frame = pd.DataFrame({"Close": [42.0]}, index=pd.to_datetime(["2026-09-01"]))
    with patch("bcb.sgs.get", return_value=pd.DataFrame()), patch("yfinance.Ticker", return_value=SimpleNamespace(history=lambda **kw: frame)):
        result = uncached()()
    assert not result["qualidade"]["treasury_10y"]["observado"]


def test_long_session_refreshes_without_overwriting_fresh_injected_context():
    state = {"macro_context": {"selic": 10}, "_macro_context_carregado_em": 100}
    with patch.object(context, "st", SimpleNamespace(session_state=state)), patch.object(context.time, "time", return_value=200), patch.object(context, "_fetch_macro_rapido", return_value={"selic": 9}) as fetch:
        assert context.garantir_macro_context()["selic"] == 10
        fetch.assert_not_called()
    with patch.object(context, "st", SimpleNamespace(session_state=state)), patch.object(context.time, "time", return_value=3800), patch.object(context, "_fetch_macro_rapido", return_value={"selic": 9}) as fetch:
        assert context.garantir_macro_context()["selic"] == 9
        fetch.assert_called_once()



def test_series_merge_preserves_quality_missing_and_newer_context():
    import pandas as pd
    from utils.macro_context import atualizar_contexto_series
    ctx = {"selic": 14, "ipca_12m": 4.5, "vix": 15, "treasury_10y": 4.5,
           "qualidade": {"vix": {"observado": False, "status": "fallback"},
                         "selic": {"observado": True, "referencia_em": "2026-09-30"}}}
    frame = pd.DataFrame({"Selic": [10], "IPCA_12M": [-1.2], "IPCA": [-.1]},
                         index=pd.to_datetime(["2026-08-31"]))
    merged = atualizar_contexto_series(ctx, frame, pd.DataFrame())
    assert merged["selic"] == 14
    assert merged["ipca"] == -1.2
    assert merged["qualidade"]["ipca_12m"]["observado"] is True
    assert merged["qualidade"]["vix"]["observado"] is False
    assert merged["qualidade"]["treasury_10y"]["observado"] is False
    assert "incompleto" in merged["label"]
    assert ctx["qualidade"]["vix"]["status"] == "fallback"
