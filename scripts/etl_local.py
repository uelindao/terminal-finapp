"""
etl_local.py — orquestra o ETL no PC, no lugar do GitHub Actions.

Uso:
  python scripts/etl_local.py diario     macro + setores + fundamentos BR e EUA
  python scripts/etl_local.py semanal    histórico OHLCV + setores + backtest
  python scripts/etl_local.py macro|br|us|precos|brief

Cada etapa roda em subprocesso, para que a falha de uma não derrube as seguintes.
Saída em logs/etl_AAAA-MM-DD.log. Ao final faz backup do banco e retorna 1 se
alguma etapa falhou: o resultado aparece no histórico do Agendador e na Home.
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from database.local_db import fazer_backup
from scripts.supabase_helper import _get_secret, log_etl_finish, log_etl_start

ETAPAS = {
    "macro": ["scripts/sync_macro.py"],
    "br": ["scripts/sync_br.py"],
    "us": ["scripts/sync_us.py"],
    "precos": ["scripts/sync_price_history.py"],
    "setores": ["scripts/backfill_setores.py", "--sleep", "0.3"],
    "backtest": ["scripts/backtest_divergencias.py", "--anos", "8", "--min-persist", "2", "--save"],
    "brief": ["scripts/morning_brief.py"],
}
JOBS = {
    "macro": ["macro"],
    "br": ["br"],
    "us": ["us"],
    "precos": ["precos"],
    "brief": ["brief"],
    # setores antes de br: o score usa o setor no pilar macro-setorial.
    "diario": ["macro", "setores", "br", "us"],
    "semanal": ["precos", "setores", "backtest"],
}
# Etapa que, se falhar, invalida as seguintes do mesmo job.
_PRE_REQUISITOS = {"backtest": "precos"}

_SEGREDOS_ETL = ("FRED_API_KEY", "FMP_API_KEY", "FMP_API_KEY_2", "BRAPI_TOKEN")


def _ambiente() -> dict:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    for nome in _SEGREDOS_ETL:
        valor = _get_secret(nome)
        if valor:
            env.setdefault(nome, valor)
    return env


def _console_utf8() -> None:
    """O console do Windows usa cp1252 e quebraria no primeiro caractere fora dele."""
    # Sob pythonw (Agendador) não há console: sys.stdout é None.
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _rodar_etapa(nome: str, log) -> bool:
    comando = [sys.executable, *ETAPAS[nome]]
    inicio = datetime.now()
    log.write(f"\n=== {inicio:%H:%M:%S} {nome}: {' '.join(ETAPAS[nome])}\n")
    log.flush()
    processo = subprocess.Popen(comando, cwd=RAIZ, env=_ambiente(), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
    for linha in processo.stdout:
        log.write(linha)
        log.flush()
        print(linha, end="", flush=True)
    codigo = processo.wait()
    duracao = datetime.now() - inicio
    log.write(f"=== {nome}: código {codigo} em {str(duracao).split('.')[0]}\n")
    log.flush()
    return codigo == 0


def executar(job: str) -> int:
    pasta_logs = RAIZ / "logs"
    pasta_logs.mkdir(exist_ok=True)
    falhas: list[str] = []
    log_id = log_etl_start(f"etl_local:{job}")
    with (pasta_logs / f"etl_{datetime.now():%Y-%m-%d}.log").open("a", encoding="utf-8") as log:
        for etapa in JOBS[job]:
            if _PRE_REQUISITOS.get(etapa) in falhas:
                falhas.append(etapa)
                log.write(f"=== {etapa}: pulada, depende de {_PRE_REQUISITOS[etapa]}\n")
                continue
            try:
                sucesso = _rodar_etapa(etapa, log)
            except Exception as exc:
                # Sem isto, o etl_log ficaria em 'running' para sempre.
                log.write(f"=== {etapa}: ERRO no orquestrador: {exc!r}\n")
                sucesso = False
            if not sucesso:
                falhas.append(etapa)
        try:
            arquivo = fazer_backup()
            log.write(f"=== backup: {arquivo}\n")
        except Exception as exc:
            falhas.append("backup")
            log.write(f"=== backup FALHOU: {exc}\n")
    total = len(JOBS[job])
    log_etl_finish(log_id, ok=total - len([f for f in falhas if f != "backup"]), fail=len(falhas),
                   error_msg=f"falhou: {', '.join(falhas)}" if falhas else "")
    print(f"[etl_local] {job}: " + (f"FALHOU em {', '.join(falhas)}" if falhas else "ok"))
    return 1 if falhas else 0


def main() -> int:
    _console_utf8()
    parser = argparse.ArgumentParser(description="ETL local do FinTerminal")
    parser.add_argument("job", choices=sorted(JOBS))
    return executar(parser.parse_args().job)


if __name__ == "__main__":
    raise SystemExit(main())
