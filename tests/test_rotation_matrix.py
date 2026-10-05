"""Provas offline de janela, moedas, cobertura e ausência de sinais artificiais."""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

from utils.rotation_matrix import (
    calcular_matriz_rotacao, converter_retorno_usd_brl, normalizar_precos,
    trajetoria_comparada, metadata_padrao, carregar_precos_matriz,
    matriz_setores_snapshot,
)


def _prices():
    index = pd.bdate_range("2024-01-01", "2026-01-01")
    n = len(index)
    return pd.DataFrame({
        "SPY": np.linspace(100, 140, n), "ASSET": np.linspace(100, 180, n),
        "BOVA11.SA": np.linspace(100, 130, n), "BRASSET.SA": np.linspace(100, 160, n),
        "BRL=X": np.linspace(4, 6, n),
    }, index=index)


def _meta(ticker="ASSET", moeda="USD", **extra):
    return {"ticker": ticker, "label": ticker, "moeda": moeda,
            "tipo": "classe", "ajustado": True, **extra}


def _row(prices=None, metadata=None, **kwargs):
    prices = _prices() if prices is None else prices
    metadata = [_meta()] if metadata is None else metadata
    kwargs.setdefault("data_final", prices.index.max())
    return calcular_matriz_rotacao(prices, metadata, **kwargs).iloc[0]


def test_conversao_exata_inclui_interacao():
    assert converter_retorno_usd_brl(0.1, 0.2) == pytest.approx(0.32)
    assert converter_retorno_usd_brl(-0.1, -0.2) == pytest.approx(-0.28)
    assert converter_retorno_usd_brl(None, 0.2) is None
    assert converter_retorno_usd_brl(float("nan"), 0.2) is None
    assert converter_retorno_usd_brl(0.1, -1) is None


def test_retorno_relativo_usa_razao_patrimonio_mesmas_datas():
    prices = _prices()
    row = _row(prices, horizonte_meses=6)
    ini, fim = row["inicio"], row["fim"]
    ativo = prices.loc[fim, "ASSET"] / prices.loc[ini, "ASSET"] - 1
    ref = prices.loc[fim, "SPY"] / prices.loc[ini, "SPY"] - 1
    assert row["status"] == "observado"
    assert row["retorno"] == pytest.approx(ativo)
    assert row["relativo"] == pytest.approx((1 + ativo) / (1 + ref) - 1)
    assert row["benchmark"] == "SPY" and row["moeda_exibicao"] == "USD"
    assert pd.isna(row["retorno_fx"])


def test_fx_e_benchmark_convertidos_nas_mesmas_extremidades():
    prices = _prices()
    row = _row(prices, moeda="BRL")
    ini, fim = row["inicio"], row["fim"]
    r = prices.loc[fim, "ASSET"] / prices.loc[ini, "ASSET"] - 1
    fx = prices.loc[fim, "BRL=X"] / prices.loc[ini, "BRL=X"] - 1
    rb = prices.loc[fim, "SPY"] / prices.loc[ini, "SPY"] - 1
    assert row["retorno"] == pytest.approx((1 + r) * (1 + fx) - 1)
    assert row["retorno_benchmark"] == pytest.approx((1 + rb) * (1 + fx) - 1)
    assert row["contribuicao_fx"] == pytest.approx((1 + r) * fx)
    assert row["retorno"] == pytest.approx(row["retorno_nativo"] + row["contribuicao_fx"])


def test_fx_comum_cancela_na_forca_relativa():
    nativa = _row(moeda="nativa")
    reais = _row(moeda="BRL")
    assert nativa["relativo"] == pytest.approx(reais["relativo"])


def test_brl_para_usd_usa_cotacao_inversa():
    prices = _prices()
    row = _row(prices, [_meta("BRASSET.SA", "BRL")], moeda="USD")
    ini, fim = row["inicio"], row["fim"]
    r = prices.loc[fim, "BRASSET.SA"] / prices.loc[ini, "BRASSET.SA"] - 1
    fx = prices.loc[fim, "BRL=X"] / prices.loc[ini, "BRL=X"] - 1
    assert row["retorno"] == pytest.approx((1 + r) / (1 + fx) - 1)
    assert row["retorno_fx"] == pytest.approx(1 / (1 + fx) - 1)
    assert row["benchmark"] == "BOVA11.SA"


def test_benchmark_ou_fx_ausente_nao_imputa_zero():
    prices = _prices().drop(columns="SPY")
    row = _row(prices)
    assert row["status"] == "indisponível" and pd.isna(row["retorno"])
    row = _row(_prices().drop(columns="BRL=X"), moeda="BRL")
    assert row["status"] == "indisponível" and "Câmbio" in row["motivo"]
    assert pd.isna(row["retorno_fx"])


@pytest.mark.parametrize("campo", ["ASSET", "BRL=X"])
@pytest.mark.parametrize("extremo", ["inicio", "fim"])
@pytest.mark.parametrize("valor", [0, -10, np.nan, np.inf, True])
def test_extremidades_contaminadas_suspendem_comparacao(campo, extremo, valor):
    prices = _prices()
    original = _row(prices, moeda="BRL")
    if isinstance(valor, bool):
        prices[campo] = prices[campo].astype(object)
    prices.loc[original[extremo], campo] = valor
    row = _row(prices, moeda="BRL")
    assert row["status"] == "indisponível" and pd.isna(row["relativo"])


def test_gap_interno_nao_e_preenchido_no_grafico():
    prices = _prices()
    original = _row(prices)
    date = prices.loc[original["inicio"]:original["fim"]].index[15]
    prices.loc[date, "ASSET"] = np.nan
    row = _row(prices)
    assert row["status"] == "observado" and row["cobertura"] < 1
    path = trajetoria_comparada(prices, row.to_dict())
    assert pd.isna(path.loc[date, "Ativo"])
    assert path.iloc[0]["Ativo"] == 100
    assert path.iloc[-1]["Ativo"] == pytest.approx((1 + row["retorno"]) * 100)


def test_cobertura_baixa_suspende_resultado():
    prices = _prices()
    original = _row(prices)
    dates = prices.loc[original["inicio"]:original["fim"]].index[2:-2]
    prices.loc[dates[::2], "ASSET"] = np.nan
    row = _row(prices)
    assert row["cobertura"] < 0.8
    assert row["status"] == "indisponível" and "Cobertura" in row["motivo"]


def test_duas_cotacoes_nao_simulam_cobertura_diaria():
    prices = _prices()
    keep = [_row(prices)["inicio"], prices.index[-1]]
    row = _row(prices.loc[keep])
    assert row["status"] == "indisponível"
    assert "cobertura diária" in row["motivo"]


def test_nao_estende_janela_curta_para_horizonte_longo():
    row = _row(_prices().tail(80), horizonte_meses=12)
    assert row["status"] == "indisponível"
    assert "não cobre" in row["motivo"]


def test_data_final_exclui_precos_futuros():
    prices = _prices()
    data = pd.Timestamp("2025-06-30")
    antes = _row(prices, data_final=data)
    prices.loc[prices.index > data, "ASSET"] = 10000000
    depois = _row(prices, data_final=data)
    assert antes["retorno"] == depois["retorno"]
    assert depois["fim"] <= data


def test_preco_nao_ajustado_e_moeda_desconhecida_sao_explicitos():
    row = _row(metadata=[_meta(ajustado=False)])
    assert row["status"] == "indisponível" and "ajustados" in row["motivo"]
    row = _row(metadata=[_meta(moeda="EUR")])
    assert row["status"] == "indisponível" and "Moeda" in row["motivo"]
    row = _row(benchmark="ASSET_UNKNOWN")
    assert row["status"] == "indisponível" and "Moeda" in row["motivo"]


def test_fundamento_nunca_e_inventado_para_classes():
    row = _row(metadata=[_meta(setor="financeiro")],
               scorecards={"financeiro": {"fundamento": 99, "valuation": 99}})
    assert pd.isna(row["fundamento"]) and pd.isna(row["valuation"])
    row = _row(metadata=[_meta(tipo="setor", setor="financeiro")],
               scorecards={"financeiro": {"fundamento": 72, "valuation": 65, "macro": 60}})
    assert row["fundamento"] == 72 and row["valuation"] == 65


def test_datas_duplicadas_nao_recebem_prioridade_arbitraria():
    prices = _prices()
    date = prices.index[100]
    duplicate = pd.concat([prices, prices.loc[[date]]])
    clean = normalizar_precos(duplicate)
    assert date not in clean.index


def test_metadados_proxy_e_teto_leitura():
    assert len(metadata_padrao("BR", "Classes")) == 7
    assert len(metadata_padrao("US", "Classes")) == 6
    assert len(metadata_padrao("US", "Setores")) == 11
    assert all(m["tipo"] == "setor" for m in metadata_padrao("US", "Setores"))
    assert "HGLG11.SA" not in [m["ticker"] for m in metadata_padrao("BR")]
    fn = getattr(carregar_precos_matriz, "__wrapped__", carregar_precos_matriz)
    with pytest.raises(ValueError):
        fn(tuple(f"T{i}" for i in range(16)))
    with patch("database.db.get_price_history_batch", return_value=pd.DataFrame()) as loader:
        fn(("SPY", "IEF", "SPY"), 550)
        loader.assert_called_once_with(["SPY", "IEF"], dias=550)


def test_snapshot_br_nao_inventa_outros_horizontes():
    sc = [{"setor": "financeiro", "fundamento": 75}]
    snapshot = {"rs": {"financeiro": 0.12}, "data": "2026-01-01"}
    curto = matriz_setores_snapshot(snapshot, sc, 3).iloc[0]
    longo = matriz_setores_snapshot(snapshot, sc, 12).iloc[0]
    assert curto["relativo"] == 0.12
    assert pd.isna(longo["relativo"]) and longo["status"] == "indisponível"
    assert "Mediana" in curto["benchmark"]
    snapshot["rs_por_horizonte"] = {"12": {"financeiro": 0.25}}
    assert matriz_setores_snapshot(snapshot, sc, 12).iloc[0]["relativo"] == 0.25


def test_interface_exige_leitura_explicita_e_explora_sem_nova_leitura():
    from streamlit.testing.v1 import AppTest
    import utils.rotation_matrix_view as view
    prices = _prices().rename(columns={"ASSET": "BOVV11.SA"})
    script = """
import streamlit as st
from utils.rotation_matrix_view import render_matriz_rotacao
render_matriz_rotacao(horizonte_meses=6, key_prefix="test_rotation")
"""
    with patch.object(view, "carregar_precos_matriz", return_value=prices) as loader:
        app = AppTest.from_string(script).run(timeout=20)
        assert not app.exception
        assert loader.call_count == 0
        app.button[0].click().run(timeout=20)
        assert not app.exception
        assert loader.call_count == 1
        # A janela muda o cálculo sobre a mesma leitura local da sessão.
        app.selectbox[0].select(12).run(timeout=20)
        assert not app.exception
        assert loader.call_count == 1
        assert len(app.dataframe) == 1


def test_interface_sincroniza_tese_e_preserva_exploracao_local_explicitamente():
    from streamlit.testing.v1 import AppTest
    script = """
import streamlit as st
from utils.rotation_matrix_view import render_matriz_rotacao
global_horizon = st.selectbox("Horizonte da tese", [6, 12, 36], key="test_global")
render_matriz_rotacao(horizonte_meses=global_horizon, key_prefix="test_sync")
"""
    app = AppTest.from_string(script).run(timeout=20)
    assert not app.exception
    assert app.selectbox(key="test_sync_months").value == 6
    app.selectbox(key="test_sync_months").select(3).run(timeout=20)
    assert app.selectbox(key="test_sync_months").value == 3
    app.run(timeout=20)
    assert app.selectbox(key="test_sync_months").value == 3
    app.selectbox(key="test_global").select(12).run(timeout=20)
    assert app.selectbox(key="test_sync_months").value == 12
    app.selectbox(key="test_global").select(36).run(timeout=20)
    assert not app.exception
    assert app.selectbox(key="test_sync_months").value is None
    assert len(app.warning) == 1
    app.selectbox(key="test_sync_months").select(24).run(timeout=20)
    assert not app.exception
    assert app.selectbox(key="test_sync_months").value == 24


def test_cache_antigo_nao_define_a_data_atual_do_estudo():
    end = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None).normalize() - pd.Timedelta(days=30)
    prices = _prices()
    prices.index = pd.bdate_range(end=end, periods=len(prices))
    current = calcular_matriz_rotacao(prices, [_meta()]).iloc[0]
    assert current["status"] == "indisponível"
    assert current["motivo"] == "Benchmark desatualizado."
    # Um recorte histórico explícito continua válido e identifica seus extremos.
    historical = calcular_matriz_rotacao(prices, [_meta()], data_final=prices.index[-1]).iloc[0]
    assert historical["status"] == "observado"
    assert historical["fim"] == prices.index[-1]


def test_setor_br_rotula_diferenca_e_avisa_snapshot_antigo():
    from streamlit.testing.v1 import AppTest
    import utils.sector_scorecard as scorecard
    import utils.divergencia_live as divergence
    row = {"setor": "financeiro", "fundamento": 70, "qualidade": 75,
           "valuation": 65, "macro": 60, "cobertura_fundamento": 50,
           "cobertura_tecnico": 75, "tickers": ["TEST3"]}
    script = """
from utils.rotation_matrix_view import _mostrar_setores_br
_mostrar_setores_br({}, 3, "test_snapshot")
"""
    with patch.object(scorecard, "calcular_scorecard_setorial", return_value=[row]), \
         patch.object(divergence, "_snapshot_rs", return_value={"data": "2020-01-01", "rs": {"financeiro": .12}}):
        app = AppTest.from_string(script).run(timeout=20)
    assert not app.exception
    assert len(app.warning) == 1
    table = app.dataframe[0].value
    assert table.iloc[0]["Diferença de retorno (pp)"] == pytest.approx(12)
    assert table.iloc[0]["Cobertura fundamentos (%)"] == 50
    assert table.iloc[0]["Cobertura momentum 12m (%)"] == 75
