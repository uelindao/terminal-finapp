"""
Reconstrói o banco SQLite a partir de um arquivo corrompido, tabela a tabela.

Uso (com o app e as tarefas agendadas parados):
    py -3.11 scripts/reparar_banco.py ORIGEM DESTINO

ORIGEM é o banco danificado (com o -wal e o -shm ao lado, se existirem); ele só
é lido. DESTINO não pode existir. O esquema vem do sqlite_master da ORIGEM, não
do schema.sql, porque o banco real tem colunas que o schema.sql não conhece.

Cada tabela é copiada com INSERT ... SELECT. Se a leitura falhar no meio, a
tabela é refeita linha a linha por rowid e as linhas ilegíveis ficam de fora.
Índices e triggers são criados depois dos dados. No fim roda integrity_check
no DESTINO e imprime as contagens das duas pontas.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def _contar(conn: sqlite3.Connection, esquema: str, tabela: str) -> int | str:
    try:
        return conn.execute(f'SELECT count(*) FROM {esquema}."{tabela}"').fetchone()[0]
    except sqlite3.DatabaseError as exc:
        return f"erro: {exc}"


def _copiar_linha_a_linha(conn: sqlite3.Connection, leitura: sqlite3.Connection,
                          tabela: str) -> tuple[int, int]:
    """Lê a tabela um rowid por vez numa conexão só de leitura; devolve (copiadas, ilegíveis)."""
    conn.execute(f'DELETE FROM main."{tabela}"')
    try:
        maximo = leitura.execute(f'SELECT max(rowid) FROM "{tabela}"').fetchone()[0] or 0
    except sqlite3.DatabaseError:
        maximo = 1_000_000
    copiadas = ilegiveis = 0
    for rowid in range(0, maximo + 1):
        try:
            linhas = leitura.execute(f'SELECT * FROM "{tabela}" WHERE rowid = ?', (rowid,)).fetchall()
        except sqlite3.DatabaseError:
            ilegiveis += 1
            continue
        for linha in linhas:
            marcas = ",".join("?" * len(linha))
            conn.execute(f'INSERT INTO main."{tabela}" VALUES ({marcas})', linha)
            copiadas += 1
    return copiadas, ilegiveis


def reparar(origem: Path, destino: Path) -> bool:
    if destino.exists():
        raise SystemExit(f"{destino} já existe; escolha outro destino.")
    conn = sqlite3.connect(f"file:{destino.as_posix()}", uri=True, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = OFF")
    # Só leitura: um checkpoint do WAL não pode escrever no arquivo danificado.
    uri_origem = f"file:{origem.resolve().as_posix()}?mode=ro"
    conn.execute("ATTACH DATABASE ? AS old", (uri_origem,))
    leitura = sqlite3.connect(uri_origem, uri=True)

    versao = conn.execute("PRAGMA old.user_version").fetchone()[0]
    objetos = conn.execute(
        "SELECT type, name, tbl_name, sql FROM old.sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
    ).fetchall()
    tabelas = [(n, s) for t, n, _, s in objetos if t == "table"]
    resto = [(t, n, s) for t, n, _, s in objetos if t in ("index", "trigger", "view")]

    conn.execute("BEGIN")
    for nome, sql in tabelas:
        conn.execute(sql)
    conn.execute("COMMIT")

    ok = True
    print(f"{'tabela':32} {'origem':>10} {'destino':>10}  obs")
    for nome, _ in tabelas:
        obs = ""
        conn.execute("BEGIN")
        try:
            conn.execute(f'INSERT INTO main."{nome}" SELECT * FROM old."{nome}"')
        except sqlite3.DatabaseError as exc:
            conn.execute("ROLLBACK")
            conn.execute("BEGIN")
            copiadas, ilegiveis = _copiar_linha_a_linha(conn, leitura, nome)
            obs = f"leitura falhou ({exc}); linha a linha: {copiadas} salvas, {ilegiveis} ilegíveis"
        conn.execute("COMMIT")
        print(f"{nome:32} {str(_contar(conn, 'old', nome)):>10} {_contar(conn, 'main', nome):>10}  {obs}")

    # sqlite_sequence guarda o último id de cada tabela AUTOINCREMENT.
    tem_seq = conn.execute("SELECT 1 FROM old.sqlite_master WHERE name = 'sqlite_sequence'").fetchone()
    if tem_seq:
        conn.execute("DELETE FROM main.sqlite_sequence")
        conn.execute("INSERT INTO main.sqlite_sequence SELECT * FROM old.sqlite_sequence")

    for tipo, nome, sql in resto:
        try:
            conn.execute(sql)
        except sqlite3.DatabaseError as exc:
            ok = False
            print(f"  {tipo} {nome} não foi recriado: {exc}")

    conn.execute(f"PRAGMA main.user_version = {int(versao)}")
    conn.execute("DETACH DATABASE old")
    leitura.close()
    resultado = [r[0] for r in conn.execute("PRAGMA integrity_check").fetchall()]
    print("integrity_check:", resultado[:5])
    conn.execute("PRAGMA journal_mode = WAL")
    conn.close()
    return ok and resultado == ["ok"]


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sys.exit(0 if reparar(Path(sys.argv[1]), Path(sys.argv[2])) else 1)
