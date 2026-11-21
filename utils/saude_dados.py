"""
Diagnóstico da atualização dos dados: o ETL rodou, terminou bem, o banco está são?

Existe porque o ETL já falhou em silêncio duas vezes: em out/2026 no GitHub Actions
(continue-on-error deixava tudo verde) e em nov/2026 no PC, quando o banco ficou
corrompido por 15 dias e o morning brief seguiu chegando como se nada houvesse.
O brief mostra o resultado no topo do email.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

# Jobs que, se pararem, deixam o app com dado velho. O brief e o semanal ficam de
# fora da cobrança de frequência: o brief é quem lê este diagnóstico, e o semanal
# tem cadência própria.
_JOBS_DIARIOS = ("sync_macro", "sync_br", "sync_us")
_MAX_SEM_RODAR = timedelta(hours=36)   # cobre fim de semana curto e PC ligado mais tarde
_MAX_RODANDO = timedelta(hours=3)


def _quando(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def diagnosticar(conn: sqlite3.Connection | None = None,
                 agora: datetime | None = None) -> list[str]:
    """Lista de problemas em português; vazia quando está tudo em dia."""
    from database.local_db import get_connection, verificar_integridade

    conn = conn or get_connection()
    agora = agora or datetime.now(timezone.utc)
    problemas: list[str] = []

    try:
        falhas = verificar_integridade(conn)
    except sqlite3.DatabaseError as exc:
        falhas = [str(exc)]
    if falhas:
        problemas.append("Banco de dados corrompido (" + falhas[0][:80] + "). "
                         "O backup diário está suspenso até o reparo com scripts/reparar_banco.py.")

    try:
        linhas = conn.execute(
            "SELECT job_name, status, started_at, error_msg FROM etl_log "
            "WHERE id IN (SELECT max(id) FROM etl_log GROUP BY job_name)"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        return problemas + [f"Não foi possível ler o etl_log: {exc}"]
    ultimo = {job: (status, _quando(inicio), msg) for job, status, inicio, msg in linhas}

    for job in _JOBS_DIARIOS:
        if job not in ultimo or ultimo[job][1] is None:
            problemas.append(f"{job} nunca rodou.")
            continue
        status, inicio, msg = ultimo[job]
        if agora - inicio > _MAX_SEM_RODAR:
            problemas.append(f"{job} não roda desde {inicio.astimezone(_BRT):%d/%m %H:%M}.")
        elif status == "error":
            problemas.append(f"{job} terminou com erro: {msg or 'sem detalhe'}.")
        elif status == "running" and agora - inicio > _MAX_RODANDO:
            problemas.append(f"{job} começou às {inicio.astimezone(_BRT):%d/%m %H:%M} e não terminou "
                             "(PC desligado no meio?).")
    return problemas


_BRT = timezone(timedelta(hours=-3))
