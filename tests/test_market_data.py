"""
Teste do helper close_series (utils/market_data) — consolidação Tier 3 do
padrão yf.Ticker().history()['Close'].dropna().
"""
import time
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

import utils.market_data as md


def _fake_hist(tz=False):
    idx = pd.date_range("2025-01-01", periods=10, freq="B", tz="America/Sao_Paulo" if tz else None)
    df = pd.DataFrame({"Open": np.arange(10.0), "Close": np.arange(10.0, 20.0)}, index=idx)
    df.iloc[3, df.columns.get_loc("Close")] = np.nan   # um NaN p/ testar dropna
    return df


def test_close_series_extrai_close_dropna_tznaive():
    fake_tk = MagicMock()
    fake_tk.history.return_value = _fake_hist(tz=True)
    with patch.object(md.yf, "Ticker", return_value=fake_tk):
        s = md.close_series.__wrapped__("PETR4.SA", "1y") if hasattr(
            md.close_series, "__wrapped__"
        ) else md.close_series("PETR4.SA", "1y")
    assert isinstance(s, pd.Series)
    assert s.isna().sum() == 0            # dropna aplicado
    assert len(s) == 9                    # 10 - 1 NaN
    assert getattr(s.index, "tz", None) is None   # tz removido
    assert s.iloc[-1] == 19.0


def test_close_series_falha_retorna_vazia():
    fake_tk = MagicMock()
    fake_tk.history.side_effect = RuntimeError("rate limit")
    with patch.object(md.yf, "Ticker", return_value=fake_tk):
        s = md.close_series.__wrapped__("X", "1y") if hasattr(
            md.close_series, "__wrapped__"
        ) else md.close_series("X", "1y")
    assert isinstance(s, pd.Series) and s.empty


# ── Circuit breaker + yf_info ────────────────────────────────────────────────

def _reset_breaker():
    """Zera o disjuntor global entre testes (estado por processo)."""
    md._YF_INFO_BREAKER._fails = 0
    md._YF_INFO_BREAKER._opened_at = 0.0


def _info_rico():
    """Simula um info real do yfinance (dezenas de chaves > limiar de 3)."""
    return {
        "longName": "Petrobras", "sector": "Energy", "currentPrice": 38.0,
        "trailingPE": 8.0, "priceToBook": 1.2, "returnOnEquity": 0.18,
        "profitMargins": 0.22, "marketCap": 5e11, "beta": 1.1,
    }


def test_yf_info_sucesso_mantem_circuito_fechado():
    _reset_breaker()
    fake_tk = MagicMock()
    fake_tk.info = _info_rico()
    with patch.object(md.yf, "Ticker", return_value=fake_tk):
        info = md.yf_info("PETR4.SA")
    assert info.get("trailingPE") == 8.0
    assert md._YF_INFO_BREAKER.is_open() is False
    assert md._YF_INFO_BREAKER._fails == 0


def test_yf_info_abre_circuito_apos_falhas_consecutivas():
    _reset_breaker()
    fake_tk = MagicMock()
    type(fake_tk).info = property(lambda self: (_ for _ in ()).throw(RuntimeError("429 Too Many Requests")))
    with patch.object(md.yf, "Ticker", return_value=fake_tk) as mk:
        for _ in range(md._YF_INFO_BREAKER.fail_threshold):
            assert md.yf_info("X") == {}
        assert md._YF_INFO_BREAKER.is_open() is True
        chamadas_ate_abrir = mk.call_count
        # com o circuito aberto, a próxima chamada NÃO bate no yfinance
        assert md.yf_info("X") == {}
        assert mk.call_count == chamadas_ate_abrir
    _reset_breaker()


def test_yf_info_info_vazio_conta_como_falha():
    """Sob rate-limit o yfinance devolve dict quase vazio — deve contar falha."""
    _reset_breaker()
    fake_tk = MagicMock()
    fake_tk.info = {"symbol": "X"}  # <= 3 chaves
    with patch.object(md.yf, "Ticker", return_value=fake_tk):
        assert md.yf_info("X") == {}
    assert md._YF_INFO_BREAKER._fails == 1
    _reset_breaker()


def test_yf_info_force_ignora_circuito_aberto():
    _reset_breaker()
    md._YF_INFO_BREAKER._fails = 99
    md._YF_INFO_BREAKER._opened_at = time.time()  # circuito aberto agora
    fake_tk = MagicMock()
    fake_tk.info = _info_rico()
    with patch.object(md.yf, "Ticker", return_value=fake_tk):
        assert md.yf_info("X", force=True).get("trailingPE") == 8.0   # force passa
    # sem force, com o circuito aberto, pula a chamada
    md._YF_INFO_BREAKER._fails = 99
    md._YF_INFO_BREAKER._opened_at = time.time()
    with patch.object(md.yf, "Ticker", return_value=fake_tk) as mk:
        assert md.yf_info("X", force=False) == {}
        assert mk.call_count == 0
    _reset_breaker()


def test_provider_health_reporta_estado():
    _reset_breaker()
    h = md.provider_health()
    assert "yfinance_info" in h
    assert h["yfinance_info"]["aberto"] is False
    assert h["yfinance_info"]["provider"] == "yfinance.info"


# ── Fachada fundamentos() — contrato de shape e cache-first ───────────────────

def test_fundamentos_shape_canonico_via_yfinance():
    """Independente da fonte, devolve TODAS as chaves canônicas."""
    _reset_breaker()
    fake_tk = MagicMock()
    fake_tk.info = _info_rico()
    with patch("database.db.get_todos_fundamentos_cache", return_value={}), \
         patch("utils.fmp_client.get_profile", return_value={}), \
         patch.object(md.yf, "Ticker", return_value=fake_tk):
        d = md.fundamentos("AAPL", allow_live=True)
    for k in md._FUND_KEYS:
        assert k in d, f"chave canônica ausente: {k}"
    assert d["p/l"] == 8.0
    assert d["data_source"] == "yfinance"
    _reset_breaker()


def test_fundamentos_cache_first_nao_chama_rede():
    """Com cache válido, retorna do cache sem tocar yfinance."""
    _reset_breaker()
    cache = {"PETR4.SA": {
        "p/l": 7.5, "p/vp": 1.1, "roe%": 19.0, "preco": 40.0,
        "setor": "energy", "nome": "petrobras", "data_source": "brapi",
        "qualidade_dados": 85,
    }}
    fake_tk = MagicMock()
    fake_tk.info = _info_rico()
    with patch("database.db.get_todos_fundamentos_cache", return_value=cache), \
         patch.object(md.yf, "Ticker", return_value=fake_tk) as mk:
        d = md.fundamentos("PETR4.SA", allow_live=True)
    assert d["p/l"] == 7.5
    assert d["data_source"] == "brapi"
    assert mk.call_count == 0          # cache-first: zero rede


def test_fundamentos_allow_live_false_para_no_cache_miss():
    _reset_breaker()
    with patch("database.db.get_todos_fundamentos_cache", return_value={}), \
         patch.object(md.yf, "Ticker") as mk:
        d = md.fundamentos("XPTO3.SA", allow_live=False)
    assert d["data_source"] == "cache_miss"
    assert all(d[k] is None for k in md._FUND_KEYS)
    assert mk.call_count == 0
