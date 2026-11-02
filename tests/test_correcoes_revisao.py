"""Regressões dos defeitos encontrados na revisão geral (nov/2026)."""
from datetime import datetime, timedelta, timezone

import pytest

from database.local_db import LocalClient
from utils.data_quality import avaliar_frescor_etl
from utils.health_engine import _calc_nd_do_historico


def _tri(ebitda, divida=None, cash=None, **extra):
    return {"ebitda": ebitda, "divida_total": divida, "cash": cash, **extra}


class TestNdEbitda:
    def test_yfinance_soma_quatro_trimestres(self):
        # 100 de EBITDA por trimestre = 400/ano; dívida líquida 400 = 1,0x, não 4,0x.
        historico = [_tri(100, divida=500, cash=100)] + [_tri(100)] * 7
        pontos, nd = _calc_nd_do_historico(historico, is_br=False)
        assert nd == pytest.approx(1.0)
        assert pontos == 4

    def test_cvm_ja_vem_anualizado(self):
        historico = [_tri(400, divida=500, cash=100, _fonte="cvm")]
        assert _calc_nd_do_historico(historico, is_br=True)[1] == pytest.approx(1.0)

    def test_menos_de_quatro_trimestres_fica_sem_dado(self):
        assert _calc_nd_do_historico([_tri(100, divida=500)] * 3, is_br=False) == (0, None)

    def test_cai_para_ebit_anual_sem_ebitda(self):
        historico = [{"ebit": 100, "divida_total": 400}] + [{"ebit": 100}] * 3
        assert _calc_nd_do_historico(historico, is_br=False)[1] == pytest.approx(1.0)


class TestFrescorEtl:
    AGORA = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def _execucao(self, dias_atras, status="success", **extra):
        fim = (self.AGORA - timedelta(days=dias_atras)).isoformat()
        return {"job_name": "etl_local:diario", "status": status, "started_at": fim,
                "finished_at": fim, **extra}

    def test_em_dia_nao_avisa(self):
        assert avaliar_frescor_etl([self._execucao(1)], self.AGORA) is None

    def test_sem_nenhuma_coleta_orienta(self):
        assert "etl_local.py" in avaliar_frescor_etl([], self.AGORA)

    def test_dados_parados_avisam_com_a_data(self):
        aviso = avaliar_frescor_etl([self._execucao(5)], self.AGORA)
        assert "5 dias" in aviso and "05/11" in aviso

    def test_falha_recente_aparece_mesmo_com_dado_fresco(self):
        execucoes = [self._execucao(0, status="error", error_msg="falhou: br"), self._execucao(1)]
        assert "falhou: br" in avaliar_frescor_etl(execucoes, self.AGORA)

    def test_so_falhas_nao_finge_sucesso(self):
        assert "sucesso" in avaliar_frescor_etl([self._execucao(0, status="error")], self.AGORA)


def test_snapshot_de_api_cache_nao_acumula(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTERMINAL_DB_PATH", str(tmp_path / "teste.db"))
    from utils.api_cache import get_from_cache, save_to_cache
    assert save_to_cache("aapl", "fmp", "quote", {"v": 1})
    assert save_to_cache("aapl", "fmp", "quote", {"v": 2})
    linhas = LocalClient().table("api_cache").select("data").execute().data
    assert linhas == [{"data": {"v": 2}}]
    assert get_from_cache("AAPL", "fmp", "quote") == {"v": 2}


def test_deletar_usuario_remove_dados_dependentes(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTERMINAL_DB_PATH", str(tmp_path / "teste.db"))
    from database import db
    sb = LocalClient()
    uid = sb.table("users").insert({"username": "a", "senha_hash": "x"}).execute().data[0]["id"]
    sb.table("user_settings").insert({"user_id": uid}).execute()
    sb.table("alert_config").insert({"user_id": uid, "ticker": "A"}).execute()
    db.deletar_usuario(uid)
    assert sb.table("user_settings").select("id").execute().data == []
    assert sb.table("alert_config").select("id").execute().data == []


def test_autenticacao_completa_sobre_a_base_local(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTERMINAL_DB_PATH", str(tmp_path / "teste.db"))
    from database import db
    assert db.criar_usuario("Maria", "segredo-de-teste", nome="m")
    usuario = db.autenticar_usuario("maria", "segredo-de-teste")
    assert usuario["username"] == "maria" and "senha_hash" not in usuario
    assert db.autenticar_usuario("maria", "errada") is None
    assert db.criar_sessao(usuario["id"], "token-x")
    assert db.validar_sessao("token-x")["id"] == usuario["id"]
    db.revogar_sessao("token-x")
    assert db.validar_sessao("token-x") is None


def test_chat_e_preferencias_ficam_no_banco_unico(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTERMINAL_DB_PATH", str(tmp_path / "teste.db"))
    from database import db
    db.salvar_mensagem_chat(1, 2, "user", "olá")
    db.salvar_user_setting(1, "tema", "carbon")
    assert db.get_historico_chat(1, 2)[0]["conteudo"] == "olá"
    assert db.get_user_setting(1, "tema") == "carbon"
    assert not (tmp_path.parent / "local_store.db").exists()


def test_serie_de_inflacao_que_falha_mantem_a_coluna_anterior(monkeypatch):
    """A API do BCB oscila em séries diferentes a cada rodada: sem isso, a coluna sumia."""
    import pandas as pd
    from scripts import sync_macro as m

    meses = pd.date_range("2024-01-01", periods=24, freq="MS")
    alvo = next(iter(m._IPCA_GRUPOS_BR))

    def buscar(codigo, nome, inicio, fim):
        if nome == alvo:
            raise TimeoutError("BCB fora")
        return pd.Series(0.3, index=meses, name=nome)

    salvos = {}
    monkeypatch.setattr(m, "_buscar_serie_bcb", buscar)
    monkeypatch.setattr(m, "_carregar_snapshot_historico",
                        lambda origem: pd.DataFrame({alvo: [0.5] * 24}, index=meses))
    monkeypatch.setattr(m, "_salvar_snapshot_historico",
                        lambda origem, df: salvos.__setitem__(origem, df.copy()))
    monkeypatch.setattr(m, "upsert_macro", lambda *a, **k: None)
    monkeypatch.setattr(m, "FRED_API_KEY", "")
    m.fetch_inflacao_setorial()
    assert salvos["inflacao_br"][alvo].iloc[-1] == 0.5


def test_universo_nao_tem_codigo_morto_nem_duplicado():
    from utils.tickers import (BR_INDICES, FII_TODOS, SCREENER_B3, SCREENER_US,
                               TICKERS_EXTINTOS, TICKERS_RENOMEADOS)
    for lista in (SCREENER_B3, FII_TODOS, BR_INDICES, SCREENER_US):
        assert len(lista) == len(set(lista))
        assert not set(lista) & (TICKERS_EXTINTOS | set(TICKERS_RENOMEADOS))
    assert {"AXIA3.SA", "EMBJ3.SA", "MBRF3.SA"} <= set(SCREENER_B3)
    # Destino de renomeação não pode ser, ele mesmo, um código morto.
    assert not set(TICKERS_RENOMEADOS.values()) & (TICKERS_EXTINTOS | set(TICKERS_RENOMEADOS))


def test_console_cp1252_nao_derruba_o_orquestrador(monkeypatch):
    import io
    import sys
    from scripts import etl_local
    bruto = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(bruto, encoding="cp1252"))
    etl_local._console_utf8()
    print("cobertura → ok", flush=True)
    assert "→".encode("utf-8") in bruto.getvalue()


def test_sem_console_nao_quebra(monkeypatch):
    import sys
    from scripts import etl_local
    monkeypatch.setattr(sys, "stdout", None)
    etl_local._console_utf8()


def test_excecao_no_orquestrador_vira_falha_registrada(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTERMINAL_DB_PATH", str(tmp_path / "teste.db"))
    from scripts import etl_local

    def explode(nome, log):
        raise RuntimeError("quebrou")

    monkeypatch.setattr(etl_local, "_rodar_etapa", explode)
    monkeypatch.setattr(etl_local, "RAIZ", tmp_path)
    monkeypatch.setattr(etl_local, "fazer_backup", lambda: "ok")
    assert etl_local.executar("macro") == 1
    linha = LocalClient().table("etl_log").select("status, error_msg").execute().data[0]
    assert linha["status"] == "error" and "macro" in linha["error_msg"]


def test_fetch_brapi_nao_pede_dividendos_nem_vaza_token(monkeypatch, capsys):
    import requests
    from scripts import sync_br

    chamadas = {}

    class Resposta:
        status_code = 403

        def raise_for_status(self):
            raise requests.HTTPError("403 for url: https://brapi.dev?token=SEGREDO", response=self)

    def get_falso(url, params, timeout):
        chamadas.update(params)
        return Resposta()

    monkeypatch.setattr(sync_br.requests, "get", get_falso)
    monkeypatch.setattr(sync_br, "BRAPI_TOKEN", "SEGREDO")
    assert sync_br.fetch_brapi("AALR3.SA") is None
    assert "dividends" not in chamadas
    saida = capsys.readouterr().out
    assert "SEGREDO" not in saida and "403" in saida


def test_momentum_pontua_com_a_janela_do_etl():
    import numpy as np
    import pandas as pd
    from scripts.sync_br import PERIODO_PRECOS
    from utils.health_engine import calcular_momentum

    assert PERIODO_PRECOS == "2y"
    # 494 pregões, como 2 anos de B3, em alta de ~1,2x ao ano.
    precos = 10 * np.cumprod(np.full(494, 1.0012))
    pontos, _, _ = calcular_momentum(pd.DataFrame({"Close": precos}))
    assert pontos > 0


def test_cache_do_streamlit_nao_congela_leituras_no_etl():
    """Fora do app, cada chamada precisa ver o que acabou de ser gravado."""
    from database.db import _st_cache

    chamadas = []

    @_st_cache(ttl=1800)
    def ler():
        chamadas.append(1)
        return len(chamadas)

    assert ler() == 1
    assert ler() == 2
    ler.clear()


def test_fundamentos_gravados_aparecem_na_mesma_execucao(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTERMINAL_DB_PATH", str(tmp_path / "teste.db"))
    from database import db
    assert db.get_todos_fundamentos_cache() == {}
    db.salvar_fundamento_cache("A", {"preco": 1})
    assert db.get_todos_fundamentos_cache()["A"]["preco"] == 1
