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
