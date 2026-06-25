"""
Teste do helper close_series (utils/market_data) — consolidação Tier 3 do
padrão yf.Ticker().history()['Close'].dropna().
"""
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
