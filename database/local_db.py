"""
Base local em SQLite com a mesma API fluente que o projeto usava no Supabase.

O arquivo substitui o PostgreSQL gerenciado: `get_client().table('x').select('a')
.eq('b', 1).execute().data` funciona igual, então os mais de 200 pontos de acesso
do app e do ETL continuam intactos. Só existe o subconjunto de operadores que o
código usa; um operador desconhecido falha com AttributeError em vez de devolver
dado errado.

Diferenças deliberadas em relação ao PostgREST:
  - Não há teto de 1000 linhas por resposta.
  - `updated_at` é carimbado em todo update/upsert (no Postgres dependia de trigger
    por tabela, e fear_greed_cache lia um carimbo que nunca avançava).

Concorrência: WAL + busy_timeout, uma conexão por thread. O ETL pode escrever com
o Streamlit aberto.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from utils.logger import get_logger

logger = get_logger(__name__)

_RAIZ = Path(__file__).resolve().parent.parent
_SCHEMA_SQL = Path(__file__).with_name("schema.sql")
_SCHEMA_VERSION = 1
_NOME_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_local = threading.local()
_schema_lock = threading.Lock()
_schema_pronto: set[str] = set()
_colunas_cache: dict[tuple[str, str], dict[str, str]] = {}


def db_path() -> Path:
    """Caminho do banco; FINTERMINAL_DB_PATH permite isolar testes e diagnósticos."""
    configurado = os.environ.get("FINTERMINAL_DB_PATH", "").strip()
    return Path(configurado) if configurado else _RAIZ / "data" / "finterminal_local.db"


def _garantir_schema(conn: sqlite3.Connection, caminho: str) -> None:
    with _schema_lock:
        if caminho in _schema_pronto:
            return
        # journal_mode fica gravado no arquivo. Trocá-lo pede lock exclusivo e ignora
        # o busy_timeout, por isso roda uma vez, sob o lock, e não a cada conexão.
        conn.execute("PRAGMA journal_mode = WAL")
        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        if versao < _SCHEMA_VERSION:
            conn.executescript(_SCHEMA_SQL.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            logger.info(f"[local_db] schema aplicado em {caminho}")
        _schema_pronto.add(caminho)


def get_connection() -> sqlite3.Connection:
    """Conexão da thread atual, trocada se FINTERMINAL_DB_PATH mudar."""
    caminho = str(db_path())
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "caminho", None) == caminho:
        return conn
    if conn is not None:
        conn.close()
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(caminho, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _garantir_schema(conn, caminho)
    _local.conn, _local.caminho = conn, caminho
    return conn


def colunas_da_tabela(tabela: str) -> dict[str, str]:
    """{coluna: tipo declarado}. Tabela inexistente é erro, como no PostgREST."""
    chave = (str(db_path()), tabela)
    if chave not in _colunas_cache:
        linhas = get_connection().execute(f'PRAGMA table_info("{tabela}")').fetchall()
        if not linhas:
            raise sqlite3.OperationalError(f"tabela inexistente: {tabela}")
        _colunas_cache[chave] = {l["name"]: (l["type"] or "").upper() for l in linhas}
    return _colunas_cache[chave]


def limpar_cache_colunas() -> None:
    """Chamado por quem altera o schema em tempo de execução (importador)."""
    _colunas_cache.clear()


# ── Conversão de valores ─────────────────────────────────────────────────────

def _agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _para_iso_utc(valor: Any) -> Any:
    """Formato único de TIMESTAMPTZ. Sem isso, cortes por string dariam errado.

    Hora sem fuso é tratada como UTC (é o que utcnow() produz e o que o Postgres
    assumia com a sessão em UTC). Texto que não é data segue intacto.
    """
    if isinstance(valor, str):
        texto = valor.strip()
        if texto.lower() == "now()":
            return _agora_iso()
        try:
            momento = datetime.fromisoformat(texto)
        except ValueError:
            return valor
    elif isinstance(valor, datetime):
        momento = valor
    elif isinstance(valor, date):
        momento = datetime(valor.year, valor.month, valor.day)
    else:
        return valor
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _para_sqlite(valor: Any, tipo: str = "") -> Any:
    if tipo == "JSON":
        return None if valor is None else json.dumps(valor, ensure_ascii=False, default=str)
    if tipo == "TIMESTAMPTZ":
        return _para_iso_utc(valor)
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False, default=str)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    # Escalares numpy: o sqlite3 não os aceita, mas são comuns vindo do pandas.
    if hasattr(valor, "item") and not isinstance(valor, (str, bytes)):
        return valor.item()
    return valor


def _linha_para_dict(linha: sqlite3.Row, colunas: dict[str, str]) -> dict:
    registro = dict(linha)
    for nome, valor in registro.items():
        if valor is None:
            continue
        tipo = colunas.get(nome)
        if tipo == "BOOLEAN":
            registro[nome] = bool(valor)
        elif tipo == "JSON" and isinstance(valor, str):
            try:
                registro[nome] = json.loads(valor)
            except ValueError:
                logger.warning(f"[local_db] JSON inválido na coluna {nome}")
    return registro


def _nome(identificador: str) -> str:
    if not _NOME_VALIDO.match(identificador):
        raise ValueError(f"identificador inválido: {identificador!r}")
    return f'"{identificador}"'


def _coluna(tabela: str, coluna: str) -> str:
    """Nome de coluna validado contra o schema.

    O SQLite lê "coluna_inexistente" como literal de texto: sem esta checagem, um
    nome errado devolveria a própria string como dado, sem erro nenhum.
    """
    identificador = _nome(coluna)
    if coluna not in colunas_da_tabela(tabela):
        raise sqlite3.OperationalError(f"coluna inexistente: {tabela}.{coluna}")
    return identificador


# ── Query builder ────────────────────────────────────────────────────────────

@dataclass
class Resposta:
    data: list = field(default_factory=list)
    count: int | None = None


class _Filtros:
    """Filtros encadeáveis; `.not_` nega apenas o filtro seguinte."""

    def __init__(self, tabela: str):
        self._tabela = tabela
        self._condicoes: list[str] = []
        self._parametros: list[Any] = []
        self._negar_proximo = False

    @property
    def not_(self):
        self._negar_proximo = True
        return self

    def _filtrar(self, coluna: str, operador: str, valor: Any):
        tipo = colunas_da_tabela(self._tabela).get(coluna, "")
        return self._adicionar(f"{_coluna(self._tabela, coluna)} {operador} ?", [_para_sqlite(valor, tipo)])

    def _adicionar(self, condicao: str, parametros: list):
        if self._negar_proximo:
            condicao = f"NOT ({condicao})"
            self._negar_proximo = False
        self._condicoes.append(condicao)
        self._parametros.extend(parametros)
        return self

    def eq(self, coluna, valor):
        return self._filtrar(coluna, "=", valor)

    def neq(self, coluna, valor):
        return self._filtrar(coluna, "<>", valor)

    def gt(self, coluna, valor):
        return self._filtrar(coluna, ">", valor)

    def gte(self, coluna, valor):
        return self._filtrar(coluna, ">=", valor)

    def lt(self, coluna, valor):
        return self._filtrar(coluna, "<", valor)

    def lte(self, coluna, valor):
        return self._filtrar(coluna, "<=", valor)

    def in_(self, coluna, valores: Iterable):
        valores = list(valores)
        tipo = colunas_da_tabela(self._tabela).get(coluna, "")
        marcadores = ",".join("?" * len(valores))
        return self._adicionar(f"{_coluna(self._tabela, coluna)} IN ({marcadores})",
                               [_para_sqlite(v, tipo) for v in valores])

    def is_(self, coluna, valor):
        """Cobre os dois usos do PostgREST: 'null' e booleanos."""
        if valor is None or str(valor).lower() == "null":
            return self._adicionar(f"{_coluna(self._tabela, coluna)} IS NULL", [])
        return self._adicionar(f"{_coluna(self._tabela, coluna)} = ?", [bool(valor)])

    def _where(self) -> str:
        return f" WHERE {' AND '.join(self._condicoes)}" if self._condicoes else ""


class _Select(_Filtros):
    def __init__(self, tabela: str, colunas: str, count: str | None):
        super().__init__(tabela)
        self._colunas = colunas
        self._contar = count == "exact"
        self._ordem: list[str] = []
        self._limite: int | None = None
        self._deslocamento = 0

    def order(self, coluna, desc: bool = False):
        # Mesma posição de NULL do Postgres: por último em ASC, primeiro em DESC.
        direcao = "DESC NULLS FIRST" if desc else "ASC NULLS LAST"
        self._ordem.append(f"{_coluna(self._tabela, coluna)} {direcao}")
        return self

    def limit(self, n: int):
        self._limite = int(n)
        return self

    def range(self, inicio: int, fim: int):
        self._deslocamento = int(inicio)
        self._limite = int(fim) - int(inicio) + 1
        return self

    def _lista_colunas(self) -> str:
        if self._colunas.strip() == "*":
            return "*"
        return ", ".join(_coluna(self._tabela, c.strip()) for c in self._colunas.split(","))

    def execute(self) -> Resposta:
        conn = get_connection()
        colunas = colunas_da_tabela(self._tabela)
        sql = f"SELECT {self._lista_colunas()} FROM {_nome(self._tabela)}{self._where()}"
        if self._ordem:
            sql += f" ORDER BY {', '.join(self._ordem)}"
        if self._limite is not None:
            sql += f" LIMIT {self._limite} OFFSET {self._deslocamento}"
        linhas = conn.execute(sql, self._parametros).fetchall()
        total = None
        if self._contar:
            total = conn.execute(
                f"SELECT COUNT(*) FROM {_nome(self._tabela)}{self._where()}", self._parametros
            ).fetchone()[0]
        return Resposta([_linha_para_dict(l, colunas) for l in linhas], total)


class _Update(_Filtros):
    def __init__(self, tabela: str, valores: dict):
        super().__init__(tabela)
        self._valores = valores

    def execute(self) -> Resposta:
        colunas = colunas_da_tabela(self._tabela)
        valores = dict(self._valores)
        if "updated_at" in colunas:
            valores.setdefault("updated_at", "now()")
        atribuicoes = ", ".join(f"{_coluna(self._tabela, c)} = ?" for c in valores)
        parametros = [_para_sqlite(v, colunas.get(c, "")) for c, v in valores.items()]
        sql = (f"UPDATE {_nome(self._tabela)} SET {atribuicoes}{self._where()} RETURNING *")
        linhas = get_connection().execute(sql, parametros + self._parametros).fetchall()
        return Resposta([_linha_para_dict(l, colunas) for l in linhas])


class _Delete(_Filtros):
    def execute(self) -> Resposta:
        colunas = colunas_da_tabela(self._tabela)
        sql = f"DELETE FROM {_nome(self._tabela)}{self._where()} RETURNING *"
        linhas = get_connection().execute(sql, self._parametros).fetchall()
        return Resposta([_linha_para_dict(l, colunas) for l in linhas])


class _Insert:
    """insert e upsert. Grava só as colunas informadas (ver _clausula_conflito)."""

    def __init__(self, tabela: str, linhas: dict | list[dict], *, upsert: bool = False,
                 on_conflict: str = "", ignore_duplicates: bool = False):
        self._tabela = tabela
        self._linhas = [linhas] if isinstance(linhas, dict) else list(linhas)
        self._upsert = upsert
        self._on_conflict = on_conflict
        self._ignorar = ignore_duplicates

    def _chaves_conflito(self) -> list[str]:
        if self._on_conflict:
            return [c.strip() for c in self._on_conflict.split(",")]
        info = get_connection().execute(f'PRAGMA table_info("{self._tabela}")').fetchall()
        return [l["name"] for l in sorted(info, key=lambda l: l["pk"]) if l["pk"]]

    def _clausula_conflito(self, colunas_linha: list[str]) -> str:
        """DO UPDATE só das colunas enviadas: coluna omitida preserva o valor atual.

        INSERT OR REPLACE apagaria as demais; upsert_price e o setor dos
        fundamentos dependem dessa preservação.
        """
        if not self._upsert:
            return ""
        chaves = self._chaves_conflito()
        alvo = ", ".join(_nome(c) for c in chaves)
        atualizar = [c for c in colunas_linha if c not in chaves]
        if self._ignorar or not atualizar:
            return f" ON CONFLICT ({alvo}) DO NOTHING"
        atribuicoes = [f"{_nome(c)} = excluded.{_nome(c)}" for c in atualizar]
        if "updated_at" in colunas_da_tabela(self._tabela) and "updated_at" not in atualizar:
            atribuicoes.append(f""""updated_at" = '{_agora_iso()}'""")
        return f" ON CONFLICT ({alvo}) DO UPDATE SET {', '.join(atribuicoes)}"

    def execute(self) -> Resposta:
        colunas = colunas_da_tabela(self._tabela)
        conn = get_connection()
        grupos: dict[tuple, list[dict]] = {}
        for linha in self._linhas:
            grupos.setdefault(tuple(linha), []).append(linha)
        retorno: list[dict] = []
        conn.execute("BEGIN IMMEDIATE")
        try:
            for colunas_linha, linhas in grupos.items():
                nomes = ", ".join(_coluna(self._tabela, c) for c in colunas_linha)
                marcadores = ", ".join("?" * len(colunas_linha))
                sql = (f"INSERT INTO {_nome(self._tabela)} ({nomes}) VALUES ({marcadores})"
                       f"{self._clausula_conflito(list(colunas_linha))}")
                valores = [[_para_sqlite(l[c], colunas.get(c, "")) for c in colunas_linha]
                           for l in linhas]
                if len(valores) == 1:
                    # Só a linha única pede RETURNING: é o caso de `.data[0]['id']`.
                    criadas = conn.execute(f"{sql} RETURNING *", valores[0]).fetchall()
                    retorno.extend(_linha_para_dict(l, colunas) for l in criadas)
                else:
                    conn.executemany(sql, valores)
                    retorno.extend(dict(l) for l in linhas)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return Resposta(retorno)


class _Tabela:
    def __init__(self, nome: str):
        _nome(nome)
        self._nome_tabela = nome

    def select(self, colunas: str = "*", count: str | None = None) -> _Select:
        return _Select(self._nome_tabela, colunas, count)

    def insert(self, linhas) -> _Insert:
        return _Insert(self._nome_tabela, linhas)

    def upsert(self, linhas, on_conflict: str = "", ignore_duplicates: bool = False) -> _Insert:
        return _Insert(self._nome_tabela, linhas, upsert=True, on_conflict=on_conflict,
                       ignore_duplicates=ignore_duplicates)

    def update(self, valores: dict) -> _Update:
        return _Update(self._nome_tabela, valores)

    def delete(self) -> _Delete:
        return _Delete(self._nome_tabela)


class _Rpc:
    def __init__(self, nome: str, parametros: dict):
        self._nome_rpc, self._parametros = nome, parametros

    def execute(self) -> Resposta:
        if self._nome_rpc != "increment_api_usage":
            raise NotImplementedError(f"rpc desconhecida: {self._nome_rpc}")
        get_connection().execute(
            "INSERT INTO api_key_usage (provider, api_key_hash, data_uso, n_requests) "
            "VALUES (?, ?, ?, 1) ON CONFLICT (provider, api_key_hash, data_uso) "
            "DO UPDATE SET n_requests = n_requests + 1",
            (self._parametros["p_provider"], self._parametros["p_key_hash"],
             date.today().isoformat()),
        )
        return Resposta()


class LocalClient:
    """Mesmo contrato do client Supabase, sobre o arquivo SQLite."""

    def table(self, nome: str) -> _Tabela:
        return _Tabela(nome)

    def rpc(self, nome: str, parametros: dict) -> _Rpc:
        return _Rpc(nome, parametros)


_client = LocalClient()


def get_client() -> LocalClient:
    return _client


# ── Backup ───────────────────────────────────────────────────────────────────

def fazer_backup(destino: Path | None = None, manter: int = 7,
                 uma_vez_por_dia: bool = False) -> Path:
    """Cópia consistente (API de backup do SQLite) e rotação dos arquivos antigos.

    Com `uma_vez_por_dia`, devolve a cópia de hoje se ela já existe: o ETL roda várias
    vezes ao dia e, sem isso, as 7 cópias cobririam só dois dias.

    Por padrão grava em data/backups. FINTERMINAL_BACKUP_DIR aponta para fora do
    disco principal (ex.: pasta do OneDrive): o banco agora é o único lar da
    carteira e do histórico de scores.
    """
    pasta = destino or Path(os.environ.get("FINTERMINAL_BACKUP_DIR", "") or db_path().parent / "backups")
    pasta.mkdir(parents=True, exist_ok=True)
    if uma_vez_por_dia:
        de_hoje = sorted(pasta.glob(f"finterminal_{datetime.now():%Y%m%d}_*.db"))
        if de_hoje:
            return de_hoje[-1]
    arquivo = pasta / f"finterminal_{datetime.now():%Y%m%d_%H%M%S}.db"
    copia = sqlite3.connect(arquivo)
    try:
        get_connection().backup(copia)
    finally:
        copia.close()
    for antigo in sorted(pasta.glob("finterminal_*.db"))[:-manter]:
        antigo.unlink()
    return arquivo
