"""
tests/test_fmp_client.py
Testes para o cliente FMP.
"""
import pytest
from unittest.mock import patch, MagicMock
import requests


class TestSafePct:
    """Testes para a função _safe_pct."""

    def test_decimal_to_pct(self):
        from utils.fmp_client import _safe_pct
        # FMP /stable/ retorna percentual (0.36 para 0.36%)
        # _safe_pct multiplica por 100 para compatibilidade
        assert _safe_pct(0.15) == 15.0

    def test_none_returns_none(self):
        from utils.fmp_client import _safe_pct
        assert _safe_pct(None) is None

    def test_invalid_value(self):
        from utils.fmp_client import _safe_pct
        assert _safe_pct("abc") is None

    def test_zero(self):
        from utils.fmp_client import _safe_pct
        assert _safe_pct(0) == 0.0


class TestSafeFloat:
    """Testes para a função _safe_float."""

    def test_float(self):
        from utils.fmp_client import _safe_float
        assert _safe_float(3.14) == 3.14

    def test_int(self):
        from utils.fmp_client import _safe_float
        assert _safe_float(42) == 42.0

    def test_string(self):
        from utils.fmp_client import _safe_float
        assert _safe_float("3.14") == 3.14

    def test_none(self):
        from utils.fmp_client import _safe_float
        assert _safe_float(None) is None


class TestResolveEndpoint:
    """Testes para resolução de endpoints antigos."""

    def test_path_style(self):
        from utils.fmp_client import _resolve_endpoint
        endpoint, params = _resolve_endpoint("ratios/AAPL", {})
        assert endpoint == "ratios"
        assert params["symbol"] == "AAPL"

    def test_query_style(self):
        from utils.fmp_client import _resolve_endpoint
        endpoint, params = _resolve_endpoint("ratios", {"symbol": "AAPL"})
        assert endpoint == "ratios"
        assert params["symbol"] == "AAPL"

    def test_unknown_endpoint(self):
        from utils.fmp_client import _resolve_endpoint
        endpoint, params = _resolve_endpoint("unknown", {})
        assert endpoint == "unknown"


class TestGetEarningsCalendar:
    """Testes para o calendário de earnings."""

    @patch("utils.fmp_client._get")
    def test_empty_response(self, mock_get):
        from utils.fmp_client import get_earnings_calendar
        mock_get.return_value = []
        result = get_earnings_calendar()
        assert result == []

    @patch("utils.fmp_client._get")
    def test_filters_by_tickers(self, mock_get):
        from utils.fmp_client import get_earnings_calendar
        mock_get.return_value = [
            {"symbol": "AAPL", "date": "2026-01-15", "eps": 2.0, "epsEstimated": 1.8},
            {"symbol": "MSFT", "date": "2026-01-16", "eps": 3.0, "epsEstimated": 2.5},
        ]
        result = get_earnings_calendar(tickers=["AAPL"])
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
