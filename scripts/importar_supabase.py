"""
importar_supabase.py — copia os dados do projeto Supabase para a base local.

Uso único, depois de restaurar o projeto no painel do Supabase:
  python scripts/importar_supabase.py                tudo, inclusive preços
  python scripts/importar_supabase.py --sem-precos   sem price_history (~860 mil
                                                     linhas; o ETL reconstrói)
  python scripts/importar_supabase.py --so users,portfolios

Lê as credenciais antigas de .streamlit/secrets.toml e usa só leitura via REST.

Regras por tipo de dado:
  pessoais  Supabase é a verdade: substitui o conteúdo local da tabela.
  demais    mescla por chave natural; se a linha já existe, a local fica. Ela é mais
            recente, porque só pode ter vindo do ETL local.
Faz backup da base local antes de começar. Pode ser repetido sem duplicar nada.
"""
import argparse
import json
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.local_db import (colunas_da_tabela, fazer_backup, get_client, get_connection,
                               limpar_cache_colunas)
from scripts.supabase_helper import _get_secret
from utils.tickers import TICKERS_RENOMEADOS

# Ordem importa: o que não dá para reconstruir vem primeiro.
PESSOAIS = ["users", "user_settings", "watchlists", "watchlist_items", "portfolios",
            "portfolio_positions", "portfolio_targets", "decision_log", "report_history",
            "alerts", "alert_config", "alert_log", "saved_comparisons"]
# tabela: colunas da chave natural. `id` remoto é descartado quando a chave é outra,
# senão colidiria com ids gerados localmente pelo ETL.
MESCLAR = {
    "health_score_history": "ticker,calculado_em",
    "macro_observations": "observacao_hash",
    "macro_snapshots": "origem",
    "ai_analyses": "id",
    "ai_analysis_cache": "id",
    "earnings_revisions": "ticker,capturado_em",
    "alertas_disparados": "id",
    "fundamentals_cache": "ticker",
    "health_scores": "ticker",
    "price_cache": "ticker",
    "macro_cache": "indicator",
    "fear_greed_cache": "market",
    "earnings_dates": "ticker",
    "earnings_calendar": "ticker,data_earnings",
    "dividend_history": "ticker,data_pagamento",
    "api_cache": "id",
    "api_key_usage": "provider,api_key_hash,data_uso",
    "price_history": "ticker,data",
}
# Efêmeras ou de uso interno do projeto antigo.
IGNORAR = {"user_sessions", "etl_log"}

ORDEM_PAGINACAO = {
    "price_history": "ticker,data",
    "dividend_history": "ticker,data_pagamento",
    "earnings_revisions": "ticker,capturado_em",
    "price_cache": "ticker",
    "macro_cache": "indicator",
    "macro_snapshots": "origem",
    "fear_greed_cache": "market",
    "earnings_dates": "ticker",
    "earnings_calendar": "ticker,data_earnings",
}
_TAMANHO_PAGINA = 1000


class Supabase:
    """Leitura paginada pela API REST; sem dependência do SDK."""

    def __init__(self, url: str, chave: str):
        self.url = url.rstrip("/")
        self.sessao = requests.Session()
        self.sessao.headers.update({"apikey": chave, "Authorization": f"Bearer {chave}"})

    def tabelas(self) -> dict[str, list[str]]:
        """{tabela: colunas}, do spec OpenAPI: revela o que nunca teve migration."""
        spec = self._get(f"{self.url}/rest/v1/", {}).json()
        return {nome: list((definicao.get("properties") or {}))
                for nome, definicao in (spec.get("definitions") or {}).items()}

    def paginas(self, tabela: str, colunas: list[str]):
        ordem = ORDEM_PAGINACAO.get(tabela) or ("id" if "id" in colunas else colunas[0])
        offset = 0
        while True:
            lote = self._get(f"{self.url}/rest/v1/{tabela}", {
                "select": "*", "order": ordem, "limit": _TAMANHO_PAGINA, "offset": offset,
            }).json()
            if lote:
                yield lote
            # O servidor pode impor teto menor que o pedido: só para em página vazia.
            if not lote:
                return
            offset += len(lote)

    def _get(self, url: str, params: dict, tentativas: int = 4) -> requests.Response:
        for tentativa in range(1, tentativas + 1):
            try:
                resposta = self.sessao.get(url, params=params, timeout=60)
                if resposta.status_code < 500:
                    resposta.raise_for_status()
                    return resposta
                erro = f"HTTP {resposta.status_code}"
            except requests.ConnectionError as exc:
                erro = str(exc)
            if tentativa == tentativas:
                raise RuntimeError(f"falha em {url}: {erro}")
            time.sleep(2 ** tentativa)
        raise AssertionError("inalcançável")


def _garantir_colunas(tabela: str, colunas: list[str]) -> None:
    """Coluna que só existia no painel do Supabase não pode ser perdida."""
    conn = get_connection()
    existe = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                          (tabela,)).fetchone()
    if not existe:
        definicoes = ", ".join(f'"{c}"' for c in colunas)
        conn.execute(f'CREATE TABLE "{tabela}" ({definicoes})')
        limpar_cache_colunas()
        print(f"  [schema] tabela nova: {tabela}")
        return
    for coluna in set(colunas) - set(colunas_da_tabela(tabela)):
        conn.execute(f'ALTER TABLE "{tabela}" ADD COLUMN "{coluna}"')
        print(f"  [schema] coluna nova: {tabela}.{coluna}")
    limpar_cache_colunas()


def substituir_tabela(tabela: str, linhas: list[dict]) -> int:
    """Troca o conteúdo inteiro numa transação: ou entra tudo, ou nada muda."""
    conn = get_connection()
    colunas = colunas_da_tabela(tabela)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(f'DELETE FROM "{tabela}"')
        for linha in linhas:
            nomes = list(linha)
            marcadores = ", ".join("?" * len(nomes))
            lista = ", ".join(f'"{n}"' for n in nomes)
            conn.execute(f'INSERT INTO "{tabela}" ({lista}) VALUES ({marcadores})',
                         [_valor(linha[n], colunas.get(n, "")) for n in nomes])
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return len(linhas)


def _valor(valor, tipo: str):
    from database.local_db import _para_sqlite
    return _para_sqlite(valor, tipo)


def mesclar_lote(tabela: str, chave: str, lote: list[dict]) -> int:
    """Insere o que falta. Devolve quantas linhas o lote trouxe."""
    if chave != "id":
        lote = [{k: v for k, v in linha.items() if k != "id"} for linha in lote]
    get_client().table(tabela).upsert(lote, on_conflict=chave, ignore_duplicates=True).execute()
    return len(lote)


def importar_tabela(remoto: Supabase, tabela: str, colunas: list[str]) -> int:
    _garantir_colunas(tabela, colunas)
    if tabela in PESSOAIS:
        # Lê tudo antes de apagar: falha de rede no meio não pode esvaziar a local.
        linhas = [linha for lote in remoto.paginas(tabela, colunas) for linha in lote]
        return substituir_tabela(tabela, linhas)
    chave = MESCLAR.get(tabela)
    total = 0
    for lote in remoto.paginas(tabela, colunas):
        if chave:
            total += mesclar_lote(tabela, chave, lote)
        else:
            get_client().table(tabela).insert(lote).execute()
            total += len(lote)
        if total % 50_000 == 0:
            print(f"  {tabela}: {total} linhas...", flush=True)
    return total


def atualizar_tickers_renomeados() -> list[dict]:
    """Watchlist muda sozinha; carteira não, e as posições voltam para revisão manual.

    Em fusão a proporção de ações muda, então renomear quantidade e preço médio
    produziria uma posição errada sem nenhum aviso.
    """
    sb = get_client()
    conn = get_connection()
    for antigo, novo in TICKERS_RENOMEADOS.items():
        conn.execute("UPDATE OR IGNORE watchlist_items SET ticker = ? WHERE ticker = ?", (novo, antigo))
    sb.table("watchlist_items").delete().in_("ticker", list(TICKERS_RENOMEADOS)).execute()
    return (sb.table("portfolio_positions").select("ticker, quantidade, preco_medio, portfolio_id")
            .in_("ticker", list(TICKERS_RENOMEADOS)).execute().data)


def conectar() -> Supabase:
    url = _get_secret("SUPABASE_URL")
    chave = _get_secret("SUPABASE_KEY", "SUPABASE_SERVICE_KEY")
    if not url or not chave:
        raise SystemExit("SUPABASE_URL e SUPABASE_KEY não estão em .streamlit/secrets.toml.")
    host = urlparse(url).hostname
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        raise SystemExit(
            f"O endereço do projeto ({host}) não existe no momento.\n"
            "Isso indica projeto PAUSADO. Abra o painel do Supabase, clique em Restore, "
            "espere alguns minutos e rode este script de novo."
        )
    return Supabase(url, chave)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--sem-precos", action="store_true", help="pula price_history")
    parser.add_argument("--so", default="", help="lista de tabelas separadas por vírgula")
    args = parser.parse_args(argv)

    remoto = conectar()
    tabelas = remoto.tabelas()
    if not tabelas:
        raise SystemExit("O Supabase respondeu sem listar tabelas; confira a chave service_role.")
    print(f"[importar] {len(tabelas)} tabelas no Supabase")

    alvo = [t.strip() for t in args.so.split(",") if t.strip()]
    ordem = PESSOAIS + list(MESCLAR) + sorted(set(tabelas) - set(PESSOAIS) - set(MESCLAR) - IGNORAR)
    ordem = [t for t in ordem if t in tabelas and (not alvo or t in alvo)]
    if args.sem_precos:
        ordem = [t for t in ordem if t != "price_history"]

    print(f"[importar] backup local em {fazer_backup()}")
    relatorio, falhas = {}, []
    for tabela in ordem:
        inicio = time.time()
        try:
            relatorio[tabela] = importar_tabela(remoto, tabela, tabelas[tabela])
            print(f"  {tabela}: {relatorio[tabela]} linhas ({time.time() - inicio:.0f}s)", flush=True)
        except Exception as exc:
            falhas.append(tabela)
            print(f"  {tabela}: ERRO {type(exc).__name__}: {exc}", flush=True)

    pendentes = atualizar_tickers_renomeados()
    for posicao in pendentes:
        novo = TICKERS_RENOMEADOS[posicao["ticker"]]
        print(f"  [carteira] {posicao['ticker']} agora negocia como {novo}: ajuste à mão "
              f"(qtd {posicao['quantidade']}, PM {posicao['preco_medio']}; em fusão a proporção muda)")

    caminho = Path(__file__).resolve().parent.parent / "logs" / "importacao_supabase.json"
    caminho.write_text(json.dumps({"linhas": relatorio, "falhas": falhas}, indent=2), encoding="utf-8")
    print(f"[importar] {sum(relatorio.values())} linhas; relatório em {caminho}")
    if falhas:
        print(f"[importar] FALHARAM: {', '.join(falhas)}. Pode rodar de novo com --so.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
