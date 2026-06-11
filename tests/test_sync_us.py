"""
tests/test_sync_us.py
Testes para o ETL de ativos dos EUA.
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd


class TestTransformFmp:
    """Testes para a função transform_fmp."""

    @patch("scripts.sync_us.fetch_fmp_profile")
    @patch("scripts.sync_us.fetch_fmp_ratios")
    def test_returns_none_when_empty(self, mock_ratios, mock_profile):
        from scripts.sync_us import transform_fmp
        mock_profile.return_value = None
        mock_ratios.return_value = None
        assert transform_fmp("INVALID") is None

    @patch("scripts.sync_us.fetch_fmp_profile")
    @patch("scripts.sync_us.fetch_fmp_ratios")
    def test_basic_transform(self, mock_ratios, mock_profile):
        from scripts.sync_us import transform_fmp
        mock_profile.return_value = {
            "companyName": "Test Inc.",
            "sector": "Technology",
            "mktCap": 1000000000,
            "beta": 1.0,
        }
        mock_ratios.return_value = {
            "priceToEarningsRatioTTM": 20.0,
            "priceToBookRatioTTM": 3.0,
            "dividendYieldTTM": 2.5,
            "netProfitMarginTTM": 0.15,
            "enterpriseValueMultipleTTM": 15.0,
            "returnOnEquity": 0.12,
        }

        result = transform_fmp("TEST")
        assert result is not None
        assert result["ticker"] == "TEST"
        assert result["nome"] == "test inc."
        assert result["setor"] == "technology"
        assert result["p/l"] == 20.0
        assert result["p/vp"] == 3.0
        assert result["dy%"] == 2.5
        assert result["roe%"] == 12.0  # returnOnEquity 0.12 * 100

    @patch("scripts.sync_us.fetch_fmp_profile")
    @patch("scripts.sync_us.fetch_fmp_ratios")
    def test_no_key_metrics_called(self, mock_ratios, mock_profile):
        """Verifica que key-metrics NÃO é chamado (otimização free tier)."""
        from scripts.sync_us import transform_fmp
        mock_profile.return_value = {"companyName": "Test"}
        mock_ratios.return_value = {"returnOnEquity": 0.10}

        with patch("scripts.sync_us.fetch_fmp_key_metrics") as mock_km:
            result = transform_fmp("TEST")
            mock_km.assert_not_called()

    @patch("scripts.sync_us.fetch_fmp_profile")
    @patch("scripts.sync_us.fetch_fmp_ratios")
    def test_margem_normalization(self, mock_ratios, mock_profile):
        """Margem < 2 deve ser multiplicada por 100."""
        from scripts.sync_us import transform_fmp
        mock_profile.return_value = {"companyName": "Test"}
        mock_ratios.return_value = {"netProfitMarginTTM": 0.15}

        result = transform_fmp("TEST")
        assert result["margem%"] == 15.0

    @patch("scripts.sync_us.fetch_fmp_profile")
    @patch("scripts.sync_us.fetch_fmp_ratios")
    def test_roe_normalization(self, mock_ratios, mock_profile):
        """ROE < 2 deve ser multiplicado por 100."""
        from scripts.sync_us import transform_fmp
        mock_profile.return_value = {"companyName": "Test"}
        mock_ratios.return_value = {"returnOnEquity": 0.12}

        result = transform_fmp("TEST")
        assert result["roe%"] == 12.0


class TestSafeSf:
    """Testes para a função _sf."""

    def test_float(self):
        from scripts.sync_us import _sf
        assert _sf(3.14) == 3.14

    def test_none(self):
        from scripts.sync_us import _sf
        assert _sf(None) is None

    def test_string(self):
        from scripts.sync_us import _sf
        assert _sf("3.14") == 3.14

    def test_invalid(self):
        from scripts.sync_us import _sf
        assert _sf("abc") is None
