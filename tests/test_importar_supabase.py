"""Regras do importador: o que é pessoal substitui, o resto nunca pisa no dado local."""
import pytest

from database.local_db import LocalClient, get_connection
from scripts import importar_supabase as imp


class RemotoFalso:
    """Serve páginas pré-montadas; `falha_em` simula queda de rede no meio."""

    def __init__(self, dados: dict, falha_em: int | None = None):
        self.dados, self.falha_em = dados, falha_em

    def paginas(self, tabela, colunas):
        for indice, lote in enumerate(self.dados.get(tabela, [])):
            if indice == self.falha_em:
                raise RuntimeError("rede caiu")
            yield lote


@pytest.fixture
def sb(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTERMINAL_DB_PATH", str(tmp_path / "teste.db"))
    return LocalClient()


def test_pessoais_substituem_e_preservam_ids(sb):
    sb.table("users").insert({"username": "admin_local", "senha_hash": "x"}).execute()
    remoto = RemotoFalso({"users": [[
        {"id": 7, "username": "uel", "senha_hash": "h", "is_admin": True,
         "created_at": "2026-01-01T10:00:00+00:00"}]]})
    assert imp.importar_tabela(remoto, "users", ["id", "username", "senha_hash", "is_admin"]) == 1
    linhas = sb.table("users").select("*").execute().data
    assert [(l["id"], l["username"], l["is_admin"]) for l in linhas] == [(7, "uel", True)]
    assert linhas[0]["created_at"] == "2026-01-01T10:00:00.000000+00:00"


def test_falha_de_rede_nao_esvazia_tabela_pessoal(sb):
    sb.table("watchlists").insert({"user_id": 1, "nome": "minha"}).execute()
    remoto = RemotoFalso({"watchlists": [[{"id": 1, "user_id": 1, "nome": "a"}], []]}, falha_em=1)
    with pytest.raises(RuntimeError):
        imp.importar_tabela(remoto, "watchlists", ["id", "user_id", "nome"])
    assert sb.table("watchlists").select("nome").execute().data == [{"nome": "minha"}]


def test_mesclar_mantem_linha_local_e_traz_a_que_falta(sb):
    sb.table("fundamentals_cache").upsert({"ticker": "A", "dados_json": "{\"novo\": 1}"},
                                          on_conflict="ticker").execute()
    remoto = RemotoFalso({"fundamentals_cache": [[
        {"id": 50, "ticker": "A", "dados_json": "{\"velho\": 1}"},
        {"id": 51, "ticker": "B", "dados_json": "{\"so_remoto\": 1}"},
    ]]})
    imp.importar_tabela(remoto, "fundamentals_cache", ["id", "ticker", "dados_json"])
    linhas = {l["ticker"]: l["dados_json"] for l in sb.table("fundamentals_cache").select("*").execute().data}
    assert linhas == {"A": "{\"novo\": 1}", "B": "{\"so_remoto\": 1}"}


def test_historico_de_score_nao_duplica_ao_repetir(sb):
    lote = [{"id": 1, "ticker": "A", "score": 70, "calculado_em": "2026-07-01T00:00:00+00:00"},
            {"id": 2, "ticker": "A", "score": 71, "calculado_em": "2026-07-02T00:00:00+00:00"}]
    sb.table("health_score_history").insert({"ticker": "Z", "score": 10}).execute()
    remoto = RemotoFalso({"health_score_history": [lote]})
    colunas = ["id", "ticker", "score", "calculado_em"]
    imp.importar_tabela(remoto, "health_score_history", colunas)
    imp.importar_tabela(remoto, "health_score_history", colunas)
    assert sb.table("health_score_history").select("id", count="exact").execute().count == 3


def test_payload_jsonb_vira_texto_lido_pelo_app(sb):
    """No Supabase o payload pode vir como dict; o código espera string ou dict."""
    remoto = RemotoFalso({"macro_snapshots": [[{"origem": "vintage_x", "payload": {"schema": "v1"}}]]})
    imp.importar_tabela(remoto, "macro_snapshots", ["origem", "payload"])
    assert sb.table("macro_snapshots").select("payload").execute().data == [{"payload": '{"schema": "v1"}'}]


def test_coluna_e_tabela_desconhecidas_nao_se_perdem(sb):
    remoto = RemotoFalso({
        "price_cache": [[{"ticker": "A", "preco": 1.0, "coluna_do_painel": "x"}]],
        "tabela_do_painel": [[{"a": 1, "b": {"c": 2}}]],
    })
    imp.importar_tabela(remoto, "price_cache", ["ticker", "preco", "coluna_do_painel"])
    imp.importar_tabela(remoto, "tabela_do_painel", ["a", "b"])
    assert sb.table("price_cache").select("coluna_do_painel").execute().data == [{"coluna_do_painel": "x"}]
    assert get_connection().execute('SELECT b FROM tabela_do_painel').fetchone()[0] == '{"c": 2}'


def test_toda_tabela_do_schema_tem_regra_de_importacao(sb):
    tabelas = {l["name"] for l in get_connection().execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    so_locais = {"user_kv", "chat_portfolio_historico"}
    sem_regra = tabelas - set(imp.PESSOAIS) - set(imp.MESCLAR) - imp.IGNORAR - so_locais
    assert sem_regra == set()


def test_projeto_pausado_explica_o_que_fazer(monkeypatch):
    monkeypatch.setattr(imp, "_get_secret", lambda *n: "https://inexistente.supabase.co")

    def sem_dns(*args, **kwargs):
        raise OSError("getaddrinfo failed")

    monkeypatch.setattr(imp.socket, "getaddrinfo", sem_dns)
    with pytest.raises(SystemExit, match="Restore"):
        imp.conectar()


def test_ticker_renomeado_muda_na_watchlist_mas_nao_na_carteira(sb):
    linha = {"user_id": 1, "watchlist_id": 1}
    sb.table("watchlist_items").insert([{**linha, "ticker": "ELET3.SA"},
                                        {**linha, "ticker": "BRFS3.SA"},
                                        {**linha, "ticker": "MBRF3.SA"}]).execute()
    sb.table("portfolio_positions").insert(
        {"ticker": "BRFS3.SA", "quantidade": 100, "user_id": 1, "portfolio_id": 1}).execute()
    pendentes = imp.atualizar_tickers_renomeados()
    tickers = {l["ticker"] for l in sb.table("watchlist_items").select("ticker").execute().data}
    assert tickers == {"AXIA3.SA", "MBRF3.SA"}
    assert [(p["ticker"], p["quantidade"]) for p in pendentes] == [("BRFS3.SA", 100)]
    assert sb.table("portfolio_positions").select("ticker").execute().data == [{"ticker": "BRFS3.SA"}]
