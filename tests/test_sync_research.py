import numpy as np
import pandas as pd
from scripts import sync_price_history as p
from scripts import sync_macro as m


def hist():
    return pd.DataFrame({"Open": [100., 101.], "High": [102., 102.], "Low": [99., 100.],
        "Close": [100., 101.], "Volume": [1, 2], "Dividends": [0., .5], "Stock Splits": [0., 0.]},
        index=pd.to_datetime(["2026-09-29", "2026-09-30"]))


def test_evento_novo_reconcilia_todo_historico(monkeypatch):
    calls = []
    class Ticker:
        def history(self, **kwargs): calls.append(kwargs); return hist()
    class YF:
        def Ticker(self, ticker): return Ticker()
    monkeypatch.setattr(p, "get_last_price_history_date", lambda ticker: "2026-09-29")
    monkeypatch.setattr(p, "upsert_price_history_batch", lambda rows: len(rows))
    n, modo = p.sync_ticker(YF(), "A", reconciliar_completo=False)
    assert n == 2 and modo == "reconciliacao-evento"
    assert calls[0]["auto_adjust"] is True and calls[-1]["period"] == "10y"


def test_reconciliacao_periodica_independe_novo_evento(monkeypatch):
    calls = []
    class Ticker:
        def history(self, **kwargs): calls.append(kwargs); return hist()
    class YF:
        def Ticker(self, ticker): return Ticker()
    monkeypatch.setattr(p, "get_last_price_history_date", lambda ticker: "2026-09-30")
    monkeypatch.setattr(p, "upsert_price_history_batch", lambda rows: len(rows))
    assert p.sync_ticker(YF(), "A", reconciliar_completo=True)[1] == "reconciliacao-mensal"
    assert calls == [{"period": "10y", "auto_adjust": True, "actions": True}]


def test_proxies_cobrem_classes_setores_e_fx():
    universo = set(p.BENCHMARKS + p.PROXIES_ROTACAO)
    assert {"BOVA11.SA", "BOVV11.SA", "LFTS11.SA", "IRFM11.SA", "B5P211.SA", "IMAB11.SA", "GOLD11.SA", "XFIX11.SA", "BRL=X"} <= universo
    assert {"SPY", "IEF", "TIP", "LQD", "HYG", "GLD", "XLK", "XLU", "XLRE", "XLC"} <= universo


def test_gap_sem_vintage_conhecida_na_epoca_ausente():
    realizado = pd.Series([5.], index=pd.to_datetime(["2026-08-01"]))
    focus = pd.Series([4.], index=pd.to_datetime(["2025-08-29"]))
    assert m.gap_focus_mesmo_horizonte(realizado, focus) is None
    conhecimento = pd.Series(pd.to_datetime(["2026-10-05"], utc=True), index=focus.index)
    assert m.gap_focus_mesmo_horizonte(realizado, focus, conhecido_em=conhecimento) is None
    conhecimento.iloc[0] = pd.Timestamp("2025-08-29", tz="UTC")
    gap = m.gap_focus_mesmo_horizonte(realizado, focus, conhecido_em=conhecimento)
    assert gap["valor"] == 1. and gap["surpresa_divulgacao"] is False


def test_focus_normalizado_todos_horizontes_salvos(monkeypatch):
    from utils import macro_research_data as d
    from bcb import sgs
    df = pd.DataFrame({"data": pd.to_datetime(["2026-10-02"]*2), "indicador": ["IPCA", "Selic"],
        "horizonte": ["12m", "2027"], "mediana": [4.5, 12.], "respondentes": [90, 80], "base_calculo": [0, 0]})
    snapshots, pontuais = [], []
    monkeypatch.setattr(d, "buscar_focus_publico", lambda dias: df)
    monkeypatch.setattr(m, "_salvar_snapshot_historico", lambda origem, dados: snapshots.append((origem, dados.copy())))
    monkeypatch.setattr(m, "upsert_macro", lambda *a, **k: pontuais.append(a))
    monkeypatch.setattr(sgs, "get", lambda *a, **k: pd.DataFrame({"x": [5.]}, index=pd.to_datetime(["2026-08-01"])))
    from utils import macro_supabase as ms
    monkeypatch.setattr(ms, "carregar_observacoes_versionadas", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(m, "_get_sb_client", lambda: object())
    monkeypatch.setattr(m, "FRED_API_KEY", "")
    m.fetch_expectativas()
    assert [a[0] for a in snapshots] == ["focus_expectativas", "expectativas_br"]
    assert snapshots[0][1]["horizonte"].tolist() == ["12m", "2027"]
    assert pontuais[0][:2] == ("br_focus_ipca_12m", 4.5)
    assert all(a[0] != "br_gap_expectativa_12m" for a in pontuais)


def test_runrate_preserva_meses_ausentes():
    idx = pd.date_range("2020-01-01", periods=15, freq="MS")
    variacao = pd.Series(1., index=idx).drop(idx[5])
    composto = m._acumular_12m(variacao)
    assert pd.isna(composto.loc[idx[12]])
    indice = pd.Series(np.arange(100., 115.), index=idx).drop(idx[5])
    taxa = m._runrate_indice(indice, 3)
    assert pd.isna(taxa.loc[idx[8]])


def test_modo_proxies_nao_dispara_universo_de_acoes():
    proxies = p.universo_tickers(apenas_proxies=True)
    completo = p.universo_tickers()
    assert proxies == sorted(set([t for t in p.BENCHMARKS if not t.startswith("^")] + p.PROXIES_ROTACAO))
    assert len(proxies) == 26 and len(completo) > len(proxies) * 3
    assert set(proxies) <= set(completo)
