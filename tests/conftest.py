"""
tests/conftest.py
Fixtures compartilhadas e mocks para testes do finterminal.
"""
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Adiciona o diretório raiz ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_streamlit():
    """Mock do Streamlit para testes fora do contexto de execução."""
    mock_st = MagicMock()
    mock_st.session_state = {}
    mock_st.cache_data = lambda *a, **kw: lambda f: f
    mock_st.cache_resource = lambda *a, **kw: lambda f: f
    return mock_st


@pytest.fixture
def sample_fmp_profile():
    """Dados de perfil FMP de exemplo."""
    return {
        "companyName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "mktCap": 2800000000000,
        "beta": 1.2,
        "price": 175.50,
    }


@pytest.fixture
def sample_fmp_ratios():
    """Dados de ratios FMP de exemplo."""
    return {
        "priceToEarningsRatioTTM": 28.5,
        "priceToBookRatioTTM": 45.2,
        "dividendYieldTTM": 0.55,
        "netProfitMarginTTM": 0.25,
        "enterpriseValueMultipleTTM": 22.3,
        "returnOnEquity": 0.15,
    }


@pytest.fixture
def sample_yf_info():
    """Dados yfinance info de exemplo."""
    return {
        "trailingPE": 28.5,
        "priceToBook": 45.2,
        "dividendYield": 0.0055,
        "returnOnEquity": 0.15,
        "profitMargins": 0.25,
        "enterpriseToEbitda": 22.3,
        "debtToEquity": 50.0,
        "beta": 1.2,
        "sector": "Technology",
        "marketCap": 2800000000000,
    }


@pytest.fixture
def mock_fmp_response(sample_fmp_profile, sample_fmp_ratios):
    """Mock de respostas FMP para testes de transform_fmp."""
    def _mock_get(endpoint, params=None):
        if endpoint == "profile":
            return [sample_fmp_profile]
        elif endpoint in ("ratios-ttm", "ratios"):
            return [sample_fmp_ratios]
        return []
    return _mock_get
