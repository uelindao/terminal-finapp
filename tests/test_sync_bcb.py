import datetime as dt

import pandas as pd
import pytest
import requests

from scripts import sync_macro as m
from utils.bcb_series import buscar_serie_bcb


class Resposta:
    def __init__(self, registros):
        self.registros = registros

    def raise_for_status(self):
        pass

    def json(self):
        return self.registros


def sessao_sgs(monkeypatch, registros=None, falha_em=None):
    chamadas, adaptadores = [], []

    class Sessao:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def mount(self, url, adaptador):
            adaptadores.append((url, adaptador))

        def get(self, url, **kwargs):
            chamadas.append((url, kwargs))
            if falha_em == len(chamadas):
                raise requests.ReadTimeout("janela indisponível")
            data = kwargs["params"]["dataInicial"]
            return Resposta(registros if registros is not None else [{"data": data, "valor": "13.75"}])

    monkeypatch.setattr(requests, "Session", Sessao)
    return chamadas, adaptadores


def test_selic_diaria_divide_dez_anos_sem_repetir_dia_e_com_timeout(monkeypatch):
    chamadas, adaptadores = sessao_sgs(monkeypatch)
    serie = buscar_serie_bcb(432, "Selic", dt.date(2016, 10, 5), dt.date(2026, 10, 5))
    assert len(chamadas) == 2
    assert len(serie) == 2
    anterior = None
    for url, kwargs in chamadas:
        assert url.endswith(".432/dados") and kwargs["timeout"] == (10, 20)
        params = kwargs["params"]
        inicio = dt.datetime.strptime(params["dataInicial"], "%d/%m/%Y").date()
        final = dt.datetime.strptime(params["dataFinal"], "%d/%m/%Y").date()
        assert final <= (pd.Timestamp(inicio) + pd.DateOffset(years=5)).date()
        if anterior is not None:
            assert inicio == anterior + dt.timedelta(days=1)
        anterior = final
    assert anterior == dt.date(2026, 10, 5)
    retry = adaptadores[0][1].max_retries
    assert retry.total == 2 and retry.allowed_methods == ["GET"]
    assert {429, 500, 502, 503, 504} <= set(retry.status_forcelist)


def test_falha_na_segunda_janela_nao_retorna_historico_parcial(monkeypatch):
    chamadas, _ = sessao_sgs(monkeypatch, falha_em=2)
    with pytest.raises(requests.ReadTimeout):
        buscar_serie_bcb(432, "Selic", dt.date(2016, 10, 5), dt.date(2026, 10, 5))
    assert len(chamadas) == 2


def test_mensal_nao_divide_janela_validamente_menor_que_limite_diario(monkeypatch):
    chamadas, _ = sessao_sgs(monkeypatch)
    buscar_serie_bcb(433, "IPCA", dt.date(2016, 10, 5), dt.date(2026, 10, 5))
    assert len(chamadas) == 1


@pytest.mark.parametrize("registros", [[], {"erro": "SGS"}, [{"data": "05/10/2026", "valor": "NaN"}],
    [{"data": "30/09/2026", "valor": "1"}],
    [{"data": "05/10/2026", "valor": "1"}, {"data": "05/10/2026", "valor": "2"}]])
def test_resposta_invalida_nao_vira_indicador(registros, monkeypatch):
    sessao_sgs(monkeypatch, registros=registros)
    with pytest.raises(ValueError):
        buscar_serie_bcb(433, "IPCA", dt.date(2026, 10, 5), dt.date(2026, 10, 5))


def preparar_etl(monkeypatch, falha_hist=()):
    chamadas, pontuais, snapshots, preservar = [], [], [], []
    monkeypatch.setattr(m, "_ETL_FALHAS", [])
    valores = {432: 13.75, 433: -0.32, 1: 4.9859, 24369: 5.3,
               13762: 82.86, 5793: 0.62, 5727: 9.48, 24364: 109.91611,
               11: .050788, 13522: 4.22, 189: 1.57}

    def buscar(codigo, nome, inicio, fim):
        chamadas.append((codigo, nome, inicio, fim))
        if codigo in falha_hist and (fim - inicio).days > 100:
            raise requests.ReadTimeout("falha histórica")
        return pd.Series([valores[codigo]], index=pd.to_datetime([fim]), name=nome)

    def manter(origem, dados, **kwargs):
        preservar.append((origem, kwargs))
        return dados

    monkeypatch.setattr(m, "_buscar_serie_bcb", buscar)
    monkeypatch.setattr(m, "upsert_macro", lambda nome, valor, **kw: pontuais.append((nome, valor, kw)))
    monkeypatch.setattr(m, "_salvar_snapshot_historico", lambda origem, dados: snapshots.append((origem, dados)))
    monkeypatch.setattr(m, "_preservar_colunas_snapshot", manter)
    return chamadas, pontuais, snapshots, preservar


def test_falha_historica_selic_preserva_outros_dados_e_ainda_coleta_pontual(monkeypatch):
    chamadas, pontuais, snapshots, preservar = preparar_etl(monkeypatch, falha_hist=(432,))
    m.fetch_bcb()
    assert len(pontuais) == 9 and len(snapshots) == 1
    assert "Selic" not in snapshots[0][1].columns
    assert "IPCA" in snapshots[0][1].columns and "IBC_Br" in snapshots[0][1].columns
    assert any(codigo == 432 and (fim - inicio).days == 90 for codigo, _, inicio, fim in chamadas)
    assert m._ETL_FALHAS == ["fetch_bcb_hist_Selic_SGS432: ReadTimeout"]
    assert preservar == [("bcb_br", {"descartar_legadas": ("Result_Primario", "Result_Nominal")})]


def test_todas_series_historicas_indisponiveis_nao_substituem_snapshot(monkeypatch):
    _, pontuais, snapshots, preservar = preparar_etl(monkeypatch,
        falha_hist=(432, 433, 1, 24369, 13762, 5793, 5727, 24364))
    m.fetch_bcb()
    assert len(pontuais) == 9 and not snapshots and not preservar
    assert len(m._ETL_FALHAS) == 8


def test_codigo_nominal_e_sinal_fiscal_confirmados_na_fonte(monkeypatch):
    chamadas, pontuais, snapshots, _ = preparar_etl(monkeypatch)
    m.fetch_bcb()
    historico = snapshots[0][1]
    assert all(codigo != 4192 for codigo, *_ in chamadas)
    assert historico["NFSP_Nominal_PIB"].dropna().iloc[-1] == 9.48
    assert historico["Saldo_Primario_PIB"].dropna().iloc[-1] == -0.62
    assert not {"Result_Primario", "Result_Nominal"} & set(historico.columns)
    cache = {nome: (valor, kw) for nome, valor, kw in pontuais}
    assert cache["result_primario"][0] == -.62
    assert cache["selic"][1]["label"] == "Meta Selic"
    assert cache["selic_diaria"][1]["unit"] == "%ad"
    assert not m._ETL_FALHAS


def test_ipca_acumulado_nao_pula_mes_ausente(monkeypatch):
    _, _, snapshots, _ = preparar_etl(monkeypatch)
    buscar = m._buscar_serie_bcb
    idx = pd.date_range("2024-01-01", periods=16, freq="MS")

    def com_lacuna(codigo, nome, inicio, fim):
        if codigo == 433:
            return pd.Series(1., index=idx.delete(5), name=nome)
        return buscar(codigo, nome, inicio, fim)

    monkeypatch.setattr(m, "_buscar_serie_bcb", com_lacuna)
    m.fetch_bcb()
    assert snapshots[0][1]["IPCA_12M"].dropna().empty


def test_falha_pontual_isolada_nao_aborta_cards_ou_historico(monkeypatch):
    _, pontuais, snapshots, _ = preparar_etl(monkeypatch)
    buscar = m._buscar_serie_bcb

    def falhar_igpm(codigo, nome, inicio, fim):
        if codigo == 189:
            raise requests.HTTPError("falha pública")
        return buscar(codigo, nome, inicio, fim)

    monkeypatch.setattr(m, "_buscar_serie_bcb", falhar_igpm)
    m.fetch_bcb()
    assert len(pontuais) == 8 and len(snapshots) == 1
    assert m._ETL_FALHAS == ["fetch_bcb_pontual_igpm_SGS189: HTTPError"]


def test_mensal_aceita_referencia_primeiro_dia_retornada_por_filtro_intra_mes(monkeypatch):
    sessao_sgs(monkeypatch, registros=[{"data": "01/10/2026", "valor": "0.62"}])
    serie = buscar_serie_bcb(5793, "NFSP", dt.date(2026, 10, 5), dt.date(2026, 10, 5))
    assert serie.index[0] == pd.Timestamp("2026-10-01")
    assert serie.iloc[0] == .62


def test_diaria_nao_aceita_observacao_fora_dia_inicial(monkeypatch):
    sessao_sgs(monkeypatch, registros=[{"data": "01/10/2026", "valor": "13.75"}])
    with pytest.raises(ValueError):
        buscar_serie_bcb(432, "Selic", dt.date(2026, 10, 5), dt.date(2026, 10, 5))
