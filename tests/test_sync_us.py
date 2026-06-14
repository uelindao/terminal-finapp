"""
tests/test_sync_us.py
Testes para o ETL de ativos dos EUA.

Após o commit ae95dea (`fix(health,cvm,fmp): bancos, CVM e endpoint paywall`)
o `fetch_fmp_ratios` foi removido — o endpoint /ratios-ttm virou paywall no FMP
free tier. Múltiplos (P/L, P/VP, DY, ROE, margem, EV/EBITDA) agora vêm via
`utils.yf_enrichment.enriquecer_com_yfinance`, que `transform_fmp` chama.

Estes testes foram atualizados para refletir a nova arquitetura:
mocka-se `fetch_fmp_profile` + `enriquecer_com_yfinance` + `coletar_historico_trimestral`.
A normalização decimal → % (antes em `transform_fmp`) agora é testada via
`utils.yf_enrichment._pct`.
"""
import pytest
from unittest.mock import patch


class TestTransformFmp:
    """Testes do pipeline de transform_fmp pós-remoção de fetch_fmp_ratios."""

    @patch("utils.yf_enrichment.coletar_historico_trimestral")
    @patch("utils.yf_enrichment.enriquecer_com_yfinance")
    @patch("scripts.sync_us.fetch_fmp_profile")
    def test_returns_none_when_empty(self, mock_profile, mock_enrich, mock_hist):
        """Sem profile FMP e sem dados yfinance → retorna None."""
        from scripts.sync_us import transform_fmp
        mock_profile.return_value = None
        mock_enrich.side_effect = lambda data, ticker, logger=None: data  # noop
        mock_hist.return_value = None
        assert transform_fmp("INVALID") is None

    @patch("utils.yf_enrichment.coletar_historico_trimestral")
    @patch("utils.yf_enrichment.enriquecer_com_yfinance")
    @patch("scripts.sync_us.fetch_fmp_profile")
    def test_basic_transform(self, mock_profile, mock_enrich, mock_hist):
        """Profile FMP fornece identidade; yfinance preenche múltiplos."""
        from scripts.sync_us import transform_fmp

        mock_profile.return_value = {
            "companyName": "Test Inc.",
            "sector":      "Technology",
            "mktCap":      1_000_000_000,
            "beta":        1.0,
        }

        def fake_enrich(data, ticker, logger=None):
            data["preco"]      = 100.0
            data["p/l"]        = 20.0
            data["p/vp"]       = 3.0
            data["dy%"]        = 2.5
            data["roe%"]       = 12.0
            data["margem%"]    = 15.0
            data["ev/ebitda"]  = 15.0
            return data

        mock_enrich.side_effect = fake_enrich
        mock_hist.return_value = None

        result = transform_fmp("TEST")
        assert result is not None
        assert result["ticker"]     == "TEST"
        assert result["nome"]       == "test inc."
        assert result["setor"]      == "technology"
        assert result["market_cap"] == 1_000_000_000
        assert result["p/l"]        == 20.0
        assert result["p/vp"]       == 3.0
        assert result["dy%"]        == 2.5
        assert result["roe%"]       == 12.0
        assert result["margem%"]    == 15.0
        # data_quality fixo em 80 (definido em transform_fmp)
        assert result["data_quality"] == 80

    @patch("utils.yf_enrichment.coletar_historico_trimestral")
    @patch("utils.yf_enrichment.enriquecer_com_yfinance")
    @patch("scripts.sync_us.fetch_fmp_profile")
    def test_descarta_quando_sem_preco_e_market_cap(
        self, mock_profile, mock_enrich, mock_hist,
    ):
        """Profile parcial sem mktCap + yfinance não preenche preço → None."""
        from scripts.sync_us import transform_fmp
        mock_profile.return_value = {"companyName": "ZeroCorp"}  # sem mktCap
        mock_enrich.side_effect = lambda data, ticker, logger=None: data  # noop
        mock_hist.return_value = None
        assert transform_fmp("ZERO") is None

    @patch("utils.yf_enrichment.coletar_historico_trimestral")
    @patch("utils.yf_enrichment.enriquecer_com_yfinance")
    @patch("scripts.sync_us.fetch_fmp_profile")
    def test_no_key_metrics_called(self, mock_profile, mock_enrich, mock_hist):
        """key-metrics não é chamado por transform_fmp (otimização free tier)."""
        from scripts.sync_us import transform_fmp
        mock_profile.return_value = {"companyName": "Test", "mktCap": 1_000_000}
        mock_enrich.side_effect = lambda data, ticker, logger=None: data
        mock_hist.return_value = None

        with patch("scripts.sync_us.fetch_fmp_key_metrics") as mock_km:
            transform_fmp("TEST")
            mock_km.assert_not_called()


class TestPctNormalization:
    """Testes de utils/yf_enrichment._pct — converte decimal yfinance → %.

    Substitui os antigos `test_margem_normalization` / `test_roe_normalization`,
    que testavam a normalização via FMP ratios (removida no commit ae95dea).
    A regra (|val| < 2 → val * 100) agora vive em `utils.yf_enrichment._pct`.
    """

    def test_decimal_pequeno_normalizado(self):
        from utils.yf_enrichment import _pct
        assert _pct(0.15) == 15.0   # margem 15%

    def test_decimal_negativo_normalizado(self):
        from utils.yf_enrichment import _pct
        assert _pct(-0.08) == -8.0  # ROE negativo

    def test_valor_grande_mantido(self):
        """Valor >= 2.0 é assumido já em %."""
        from utils.yf_enrichment import _pct
        assert _pct(15.0) == 15.0
        assert _pct(2.5)  == 2.5

    def test_none_retorna_none(self):
        from utils.yf_enrichment import _pct
        assert _pct(None) is None

    def test_string_invalida_retorna_none(self):
        from utils.yf_enrichment import _pct
        assert _pct("abc") is None


class TestSafeSf:
    """Testes para a função _sf (safe float)."""

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
