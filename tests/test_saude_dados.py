import sqlite3
from datetime import datetime, timedelta, timezone

from utils.saude_dados import diagnosticar

AGORA = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _banco(*linhas):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE etl_log (id INTEGER PRIMARY KEY, job_name TEXT, status TEXT, "
                 "started_at TEXT, error_msg TEXT)")
    for job, status, horas_atras, msg in linhas:
        conn.execute("INSERT INTO etl_log (job_name, status, started_at, error_msg) VALUES (?,?,?,?)",
                     (job, status, (AGORA - timedelta(hours=horas_atras)).isoformat(), msg))
    return conn


def test_tudo_em_dia_nao_gera_aviso():
    conn = _banco(("sync_macro", "success", 2, None), ("sync_br", "success", 2, None),
                  ("sync_us", "success", 1, None))
    assert diagnosticar(conn, AGORA) == []


def test_so_a_ultima_execucao_de_cada_job_conta():
    conn = _banco(("sync_macro", "error", 30, "DatabaseError"), ("sync_macro", "success", 2, None),
                  ("sync_br", "success", 2, None), ("sync_us", "success", 1, None))
    assert diagnosticar(conn, AGORA) == []


def test_erro_job_parado_e_execucao_interrompida_aparecem():
    conn = _banco(("sync_macro", "error", 2, "_salvar_snapshot_historico: DatabaseError"),
                  ("sync_br", "running", 26, None),
                  ("sync_us", "success", 60, None))
    problemas = diagnosticar(conn, AGORA)
    assert len(problemas) == 3
    assert "sync_macro terminou com erro: _salvar_snapshot_historico" in problemas[0]
    assert "sync_br começou" in problemas[1] and "não terminou" in problemas[1]
    assert problemas[2].startswith("sync_us não roda desde")


def test_banco_corrompido_vira_primeiro_aviso(monkeypatch):
    import database.local_db as local_db
    monkeypatch.setattr(local_db, "verificar_integridade", lambda conn=None: ["Tree 68 page 3485"])
    conn = _banco(("sync_macro", "success", 2, None), ("sync_br", "success", 2, None),
                  ("sync_us", "success", 1, None))
    problemas = diagnosticar(conn, AGORA)
    assert len(problemas) == 1 and problemas[0].startswith("Banco de dados corrompido")
