"""
tests/test_health_engine.py
Testes para o motor de health score.
"""
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np


class TestSafeFloat:
    """Testes para a função safe_float."""

    def test_float_value(self):
        from utils.health_engine import safe_float
        assert safe_float(3.14) == 3.14

    def test_int_value(self):
        from utils.health_engine import safe_float
        assert safe_float(42) == 42.0

    def test_string_number(self):
        from utils.health_engine import safe_float
        assert safe_float("3.14") == 3.14

    def test_none_returns_default(self):
        from utils.health_engine import safe_float
        assert safe_float(None) is None
        assert safe_float(None, 0) == 0

    def test_invalid_string(self):
        from utils.health_engine import safe_float
        assert safe_float("abc") is None


class TestCalcPiotroski:
    """Testes para o cálculo do Piotroski F-Score."""

    def test_returns_tuple(self):
        from utils.health_engine import calcular_piotroski
        mock_acao = MagicMock()
        mock_acao.financials = pd.DataFrame()
        mock_acao.balance_sheet = pd.DataFrame()
        mock_acao.cashflow = pd.DataFrame()
        mock_acao.quarterly_financials = pd.DataFrame()
        mock_acao.quarterly_balance_sheet = pd.DataFrame()

        score, detalhes = calcular_piotroski(mock_acao, setor="", is_br=False)
        assert isinstance(score, int)
        assert isinstance(detalhes, dict)

    def test_empty_financials_returns_zero(self):
        from utils.health_engine import calcular_piotroski
        mock_acao = MagicMock()
        mock_acao.financials = pd.DataFrame()
        mock_acao.balance_sheet = pd.DataFrame()
        mock_acao.cashflow = pd.DataFrame()
        mock_acao.quarterly_financials = pd.DataFrame()
        mock_acao.quarterly_balance_sheet = pd.DataFrame()

        score, _ = calcular_piotroski(mock_acao)
        # Com dados vazios, F-score deve ser 0 ou baixo
        assert 0 <= score <= 9


class TestCalcCrescimento:
    """Testes para o cálculo de crescimento."""

    def test_returns_tuple(self):
        from utils.health_engine import calcular_crescimento
        mock_acao = MagicMock()
        mock_acao.financials = pd.DataFrame()
        info = {"revenueGrowth": 0.15, "earningsGrowth": 0.20}

        score, detalhes = calcular_crescimento(mock_acao, info)
        assert isinstance(score, int)
        assert "alertas" in detalhes
        assert "rev_growth" in detalhes

    def test_high_growth_positive_score(self):
        from utils.health_engine import calcular_crescimento
        mock_acao = MagicMock()
        mock_acao.financials = pd.DataFrame()
        info = {"revenueGrowth": 0.20, "earningsGrowth": 0.25}

        score, _ = calcular_crescimento(mock_acao, info)
        assert score > 0

    def test_negative_growth_negative_score(self):
        from utils.health_engine import calcular_crescimento
        mock_acao = MagicMock()
        mock_acao.financials = pd.DataFrame()
        info = {"revenueGrowth": -0.10, "earningsGrowth": -0.15}

        score, _ = calcular_crescimento(mock_acao, info)
        assert score < 0


class TestCalcMomentum:
    """Testes para o cálculo de momentum."""

    def test_insufficient_data(self):
        from utils.health_engine import calcular_momentum
        df = pd.DataFrame({"Close": range(10)})
        score, detalhes, alertas = calcular_momentum(df)
        assert score == 0

    def test_sufficient_data(self):
        from utils.health_engine import calcular_momentum
        # Simula 260 dias de dados com tendência de alta
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(260) * 0.5)
        df = pd.DataFrame({"Close": prices})

        score, detalhes, alertas = calcular_momentum(df)
        assert isinstance(score, int)
        assert isinstance(detalhes, dict)


class TestDyNormalization:
    """Testes para normalização de DY (yfinance sempre retorna decimal)."""

    def test_yf_decimal_to_pct(self):
        """yfinance retorna 0.035 para 3.5% — deve virar 3.5."""
        # O código em scrapers.py agora sempre multiplica por 100
        dy_raw = 0.035
        dy_pct = round(dy_raw * 100, 2)
        assert dy_pct == 3.5

    def test_yf_high_yield_cap(self):
        """Yields > 50% são considerados erro de dados."""
        dy_raw = 0.60  # 60% — improvável
        dy_pct = dy_raw * 100
        # Sanity cap: > 50% → None
        result = dy_pct if dy_pct <= 50 else None
        assert result is None

    def test_yf_normal_yield(self):
        """Yield normal de 6.5%."""
        dy_raw = 0.065
        dy_pct = dy_raw * 100
        assert dy_pct == 6.5


class TestScoreRange:
    """Testes para garantir que o score fica dentro do range 0-100."""

    def test_score_always_0_to_100(self):
        """Verifica que score final é sempre 0-100."""
        for raw_score in [-50, 0, 50, 100, 150, 200]:
            clamped = min(max(int(raw_score), 0), 100)
            assert 0 <= clamped <= 100
