"""
Contrato do adaptador SQLite: o que o código herdou do Supabase e não pode mudar
em silêncio. Os casos cobrem as armadilhas que corromperiam dados sem erro visível.
"""
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from database import local_db
from database.local_db import LocalClient, fazer_backup, get_connection


@pytest.fixture
def sb(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTERMINAL_DB_PATH", str(tmp_path / "teste.db"))
    return LocalClient()


def test_upsert_preserva_colunas_omitidas(sb):
    sb.table("price_cache").upsert(
        {"ticker": "PETR4.SA", "preco": 30.0, "rsi_14": 55.0}, on_conflict="ticker").execute()
    sb.table("price_cache").upsert({"ticker": "PETR4.SA", "preco": 31.0}, on_conflict="ticker").execute()
    linha = sb.table("price_cache").select("*").eq("ticker", "PETR4.SA").execute().data[0]
    assert linha["preco"] == 31.0
    assert linha["rsi_14"] == 55.0


def test_upsert_em_lote_com_colunas_diferentes(sb):
    sb.table("price_cache").upsert([
        {"ticker": "A", "preco": 1.0},
        {"ticker": "B", "preco": 2.0, "volume": 10},
    ], on_conflict="ticker").execute()
    assert sb.table("price_cache").select("ticker", count="exact").execute().count == 2


def test_upsert_ignore_duplicates_mantem_o_existente(sb):
    sb.table("price_cache").upsert({"ticker": "A", "preco": 1.0}, on_conflict="ticker").execute()
    sb.table("price_cache").upsert({"ticker": "A", "preco": 9.0}, on_conflict="ticker",
                                   ignore_duplicates=True).execute()
    assert sb.table("price_cache").select("preco").execute().data[0]["preco"] == 1.0


def test_insert_devolve_id_gerado(sb):
    res = sb.table("watchlists").insert({"user_id": 1, "nome": "x"}).execute()
    assert isinstance(res.data[0]["id"], int)
    assert res.data[0]["padrao"] is False


def test_insert_duplicado_levanta_erro(sb):
    linha = {"ticker": "A", "user_id": 1, "watchlist_id": 1}
    sb.table("watchlist_items").insert(linha).execute()
    with pytest.raises(sqlite3.IntegrityError):
        sb.table("watchlist_items").insert(linha).execute()
    # A transação falha não pode travar as próximas escritas.
    sb.table("watchlist_items").insert({**linha, "ticker": "B"}).execute()


def test_update_e_delete_devolvem_linhas_afetadas(sb):
    sb.table("price_cache").upsert({"ticker": "A", "preco": 1.0}, on_conflict="ticker").execute()
    assert len(sb.table("price_cache").update({"preco": 2.0}).eq("ticker", "A").execute().data) == 1
    assert len(sb.table("price_cache").delete().eq("ticker", "Z").execute().data) == 0
    assert len(sb.table("price_cache").delete().eq("ticker", "A").execute().data) == 1


def test_updated_at_avanca_no_upsert_sem_o_campo(sb):
    # carregar_fear_greed filtra por updated_at, que salvar_fear_greed não envia.
    sb.table("fear_greed_cache").upsert(
        {"market": "us", "score": 50, "label": "x", "componentes": {}}, on_conflict="market").execute()
    antigo = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    sb.table("fear_greed_cache").update({"updated_at": antigo}).eq("market", "us").execute()
    sb.table("fear_greed_cache").upsert(
        {"market": "us", "score": 60, "label": "y", "componentes": {}}, on_conflict="market").execute()
    corte = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert sb.table("fear_greed_cache").select("score").gte("updated_at", corte).execute().data


def test_timestamp_canonico_e_comparavel(sb):
    futuro = datetime.now(timezone.utc) + timedelta(hours=1)
    token = sb.table("users").insert({"username": "a", "senha_hash": "x"}).execute().data[0]
    sb.table("user_sessions").insert(
        {"token": "t", "user_id": token["id"], "expires_at": futuro.isoformat()}).execute()
    # Cortes com e sem fuso (isoformat de now(utc) e de utcnow) precisam casar igual.
    agora_tz = datetime.now(timezone.utc).isoformat()
    agora_naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    assert sb.table("user_sessions").select("id").gt("expires_at", agora_tz).execute().data
    assert sb.table("user_sessions").select("id").gt("expires_at", agora_naive).execute().data
    assert not sb.table("user_sessions").select("id").lt("expires_at", agora_tz).execute().data


def test_default_de_created_at_usa_o_formato_canonico(sb):
    criado = sb.table("users").insert({"username": "a", "senha_hash": "x"}).execute().data[0]["created_at"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00", criado)
    assert datetime.fromisoformat(criado).tzinfo is not None


def test_literal_now_vira_timestamp(sb):
    sb.table("portfolio_targets").upsert(
        {"portfolio_id": 1, "ticker": "A", "peso_alvo": 5, "updated_at": "now()"},
        on_conflict="portfolio_id,ticker").execute()
    valor = sb.table("portfolio_targets").select("updated_at").execute().data[0]["updated_at"]
    assert valor[:4].isdigit() and "T" in valor


def test_json_e_booleano_voltam_com_o_tipo_original(sb):
    sb.table("fear_greed_cache").insert(
        {"market": "br", "score": 1, "label": "x", "componentes": {"a": [1, 2]}}).execute()
    sb.table("alert_config").insert({"user_id": 1, "ticker": "A", "threshold": 40, "ativo": False}).execute()
    assert sb.table("fear_greed_cache").select("componentes").execute().data[0]["componentes"] == {"a": [1, 2]}
    linhas = sb.table("alert_config").select("ativo").eq("ativo", False).execute().data
    assert linhas == [{"ativo": False}]


def test_dict_em_coluna_texto_vira_json_string(sb):
    sb.table("macro_snapshots").upsert(
        {"origem": "x", "payload": {"a": 1}}, on_conflict="origem").execute()
    assert sb.table("macro_snapshots").select("payload").execute().data[0]["payload"] == '{"a": 1}'


def test_filtros_compostos(sb):
    sb.table("api_cache").insert([
        {"ticker": "A", "provider": "p", "endpoint": "e", "periodo": None, "data": {}},
        {"ticker": "A", "provider": "p", "endpoint": "e", "periodo": "2024-Q1", "data": {}},
        {"ticker": "B", "provider": "p", "endpoint": "e", "periodo": "2024-Q1", "data": {}},
    ]).execute()
    tabela = sb.table("api_cache")
    assert len(tabela.select("id").is_("periodo", "null").execute().data) == 1
    assert len(tabela.select("id").not_.is_("periodo", "null").execute().data) == 2
    assert len(tabela.select("id").in_("ticker", ["A"]).execute().data) == 2
    assert len(tabela.select("id").in_("ticker", []).execute().data) == 0
    assert len(tabela.select("id").eq("ticker", "A").neq("periodo", "x").execute().data) == 1


def test_order_range_limit_e_count(sb):
    sb.table("price_history").upsert(
        [{"ticker": "A", "data": f"2026-01-{d:02d}", "close": float(d)} for d in range(1, 11)],
        on_conflict="ticker,data").execute()
    q = sb.table("price_history").select("close", count="exact").order("data", desc=True)
    res = q.range(2, 4).execute()
    assert [r["close"] for r in res.data] == [8.0, 7.0, 6.0]
    assert res.count == 10
    assert sb.table("price_history").select("close").limit(0).execute().data == []


def test_sem_teto_de_1000_linhas(sb):
    linhas = [{"ticker": "A", "data": (date(2000, 1, 1) + timedelta(days=i)).isoformat(), "close": 1.0}
              for i in range(1500)]
    sb.table("price_history").upsert(linhas, on_conflict="ticker,data").execute()
    assert len(sb.table("price_history").select("data").execute().data) == 1500


def test_nulos_ordenam_como_no_postgres(sb):
    sb.table("price_cache").upsert(
        [{"ticker": "A", "preco": 1.0}, {"ticker": "B", "preco": None}], on_conflict="ticker").execute()
    assert sb.table("price_cache").select("ticker").order("preco", desc=True).execute().data[0]["ticker"] == "B"
    assert sb.table("price_cache").select("ticker").order("preco").execute().data[0]["ticker"] == "A"


def test_operador_desconhecido_falha_alto(sb):
    with pytest.raises(AttributeError):
        sb.table("users").select("*").textSearch("x", "y")


def test_coluna_inexistente_e_identificador_malicioso_falham(sb):
    with pytest.raises(sqlite3.OperationalError):
        sb.table("users").select("nao_existe").execute()
    with pytest.raises(ValueError):
        sb.table("users").select('id"; DROP TABLE users; --').execute()


def test_tabela_inexistente_falha_em_todas_as_operacoes(sb):
    with pytest.raises(sqlite3.OperationalError):
        sb.table("nao_existe").select("*").execute()
    with pytest.raises(sqlite3.OperationalError):
        sb.table("nao_existe").insert({"a": 1}).execute()


def test_macro_observations_e_append_only(sb):
    linha = {"observacao_hash": "h", "serie_id": "s", "referencia_em": "2026-01-01",
             "disponivel_em": "2026-01-01", "coletado_em": "2026-01-01", "valor": 1.0,
             "fonte": "f", "unidade": "u", "disponibilidade_base": "b"}
    sb.table("macro_observations").upsert(linha, on_conflict="observacao_hash",
                                           ignore_duplicates=True).execute()
    sb.table("macro_observations").upsert(linha, on_conflict="observacao_hash",
                                           ignore_duplicates=True).execute()
    assert sb.table("macro_observations").select("id", count="exact").execute().count == 1
    with pytest.raises(sqlite3.IntegrityError):
        sb.table("macro_observations").update({"valor": 2.0}).eq("serie_id", "s").execute()


def test_rpc_increment_api_usage_acumula_no_dia(sb):
    for _ in range(3):
        sb.rpc("increment_api_usage", {"p_provider": "av", "p_key_hash": "h"}).execute()
    assert sb.table("api_key_usage").select("n_requests").execute().data[0]["n_requests"] == 3


def test_apagar_usuario_derruba_sessoes(sb):
    uid = sb.table("users").insert({"username": "a", "senha_hash": "x"}).execute().data[0]["id"]
    sb.table("user_sessions").insert({"token": "t", "user_id": uid, "expires_at": "2099-01-01"}).execute()
    sb.table("users").delete().eq("id", uid).execute()
    assert sb.table("user_sessions").select("id").execute().data == []


def test_escala_numpy_e_aceita(sb):
    np = pytest.importorskip("numpy")
    sb.table("price_cache").upsert(
        {"ticker": "A", "preco": np.float64(1.5), "volume": np.int64(7)}, on_conflict="ticker").execute()
    assert sb.table("price_cache").select("volume").execute().data[0]["volume"] == 7


def test_conexoes_por_thread_escrevem_sem_travar(sb):
    erros = []

    def gravar(indice):
        try:
            for j in range(20):
                sb.table("price_cache").upsert({"ticker": f"T{indice}-{j}", "preco": 1.0},
                                               on_conflict="ticker").execute()
        except Exception as exc:
            erros.append(exc)

    threads = [threading.Thread(target=gravar, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not erros
    assert sb.table("price_cache").select("ticker", count="exact").execute().count == 120


def test_backup_gera_copia_integra_e_roda_rotacao(sb, tmp_path):
    sb.table("price_cache").upsert({"ticker": "A", "preco": 1.0}, on_conflict="ticker").execute()
    pasta = tmp_path / "bk"
    for _ in range(3):
        arquivo = fazer_backup(pasta, manter=2)
    assert len(list(pasta.glob("*.db"))) <= 2
    copia = sqlite3.connect(arquivo)
    assert copia.execute("SELECT COUNT(*) FROM price_cache").fetchone()[0] == 1
    copia.close()


def test_todo_on_conflict_do_codigo_tem_indice_unico(sb):
    """Sem UNIQUE correspondente o SQLite recusa o upsert só em tempo de execução."""
    raiz = Path(__file__).resolve().parent.parent
    padrao = re.compile(
        r"""\.table\(\s*["'](\w+)["']\s*\)\s*\.upsert\((?:(?!\.table\().)*?on_conflict\s*=\s*["']([\w, ]+)["']""",
        re.S)
    achados = set()
    for arquivo in [*raiz.glob("*.py"), *(raiz / "pages").glob("*.py"), *(raiz / "utils").glob("*.py"),
                    *(raiz / "database").glob("*.py"), *(raiz / "scripts").glob("*.py")]:
        if arquivo.name == "db_sqlite_legacy.py":
            continue
        texto = arquivo.read_text(encoding="utf-8")
        achados.update(padrao.findall(texto))
    assert len(achados) >= 12, achados

    conn = get_connection()
    for tabela, alvo in sorted(achados):
        chaves = {c.strip() for c in alvo.split(",")}
        indices = [{l["name"] for l in conn.execute(f'PRAGMA index_info("{i["name"]}")')}
                   for i in conn.execute(f'PRAGMA index_list("{tabela}")') if i["unique"]]
        pk = {l["name"] for l in conn.execute(f'PRAGMA table_info("{tabela}")') if l["pk"]}
        assert chaves in [*indices, pk], f"{tabela}: sem UNIQUE para {alvo}"


def test_tabelas_usadas_no_codigo_existem(sb):
    raiz = Path(__file__).resolve().parent.parent
    padrao = re.compile(r"""\.table\(\s*["'](\w+)["']""")
    usadas = set()
    for arquivo in [*raiz.glob("*.py"), *(raiz / "pages").glob("*.py"), *(raiz / "utils").glob("*.py"),
                    *(raiz / "scripts").glob("*.py")]:
        usadas.update(padrao.findall(arquivo.read_text(encoding="utf-8")))
    usadas.update(padrao.findall((raiz / "database" / "db.py").read_text(encoding="utf-8")))
    existentes = {l["name"] for l in get_connection().execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert usadas - existentes == set()
