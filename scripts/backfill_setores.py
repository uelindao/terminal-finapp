"""
scripts/backfill_setores.py — popula 'setor' das acoes BR no fundamentals_cache.

CAUSA-RAIZ (diagnosticada): o sync_br grava 'setor' so do campo do BRAPI, que vem
vazio no free tier -> ~200 acoes BR ficam sem setor -> tilt/scorecard/divergencias
inertes. O yfinance .info['sector'] traz o GICS em ingles (Energy, Financial
Services, ...) que ja mapeia limpo via normalizar_setor.

Este backfill busca .info['sector'] de cada ticker BR e faz MERGE no dados_json
(upsert so da coluna dados_json -> preserva data_source/quality/etc). Setor e
estavel: rodar uma vez resolve; re-rodar so atualiza.

Uso:  python scripts/backfill_setores.py [--limit N] [--sleep 0.5]
Requer .streamlit/secrets.toml (como os demais ETLs).
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _p(txt=""):
    print(str(txt).encode("ascii", "replace").decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = todos")
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--force", action="store_true",
                    help="reprocessa todos (default: só os que ainda não têm setor canônico)")
    args = ap.parse_args()

    import yfinance as yf
    from scripts.supabase_helper import get_client
    from utils.tickers import SCREENER_B3, FII_TODOS
    from utils.setores import normalizar_setor

    sb = get_client()
    universo = list(dict.fromkeys(list(SCREENER_B3) + list(FII_TODOS)))
    if args.limit:
        universo = universo[:args.limit]

    # dados_json existentes (para merge)
    _p(f"[backfill_setores] carregando cache existente de {len(universo)} tickers...")
    existentes: dict = {}
    passo = 200
    for i in range(0, len(universo), passo):
        lote = universo[i:i + passo]
        try:
            rows = (sb.table("fundamentals_cache")
                    .select("ticker, dados_json").in_("ticker", lote).execute().data) or []
            for r in rows:
                existentes[r["ticker"]] = r
        except Exception as e:
            _p(f"  aviso: falha ao ler lote {i}: {e}")

    # INCREMENTAL: por padrão pula quem já tem setor canônico (re-run só preenche
    # as lacunas que falharam por 404/timeout do yfinance — barato e rápido).
    if not args.force:
        def _ja_tem(tk):
            row = existentes.get(tk)
            if not row or not row.get("dados_json"):
                return False
            try:
                _s = json.loads(row["dados_json"]).get("setor")
            except Exception:
                return False
            return bool(normalizar_setor(_s))
        antes = len(universo)
        universo = [tk for tk in universo if not _ja_tem(tk)]
        _p(f"    incremental: {antes - len(universo)} já com setor, "
           f"{len(universo)} a processar (use --force p/ refazer todos)")

    def _fetch_info(tk, tentativas=3):
        # yfinance quoteSummary 404/timeout de forma intermitente — retry com backoff.
        for t in range(tentativas):
            try:
                info = yf.Ticker(tk).info or {}
                if info.get("sector") or info.get("longName"):
                    return info
            except Exception:
                pass
            time.sleep(1.0 + t)
        return {}

    ok = pulado = falha = 0
    _dist: dict = {}
    for idx, tk in enumerate(universo):
        try:
            info = _fetch_info(tk)
            setor_raw = (info.get("sector") or "").strip()
            if not setor_raw:
                # FIIs no yfinance costumam vir sem sector → assume imobiliário
                setor_raw = "Real Estate" if tk.replace(".SA", "").endswith("11") else ""
            if not setor_raw:
                pulado += 1
                continue

            row = existentes.get(tk)
            dados = {}
            if row and row.get("dados_json"):
                try:
                    dados = json.loads(row["dados_json"])
                except Exception:
                    dados = {}
            dados["setor"] = setor_raw.lower()
            if info.get("longName") and not dados.get("nome"):
                dados["nome"] = str(info["longName"]).lower()

            sb.table("fundamentals_cache").upsert(
                {"ticker": tk, "dados_json": json.dumps(dados)}, on_conflict="ticker"
            ).execute()
            _canon = normalizar_setor(setor_raw)
            _dist[_canon] = _dist.get(_canon, 0) + 1
            ok += 1
            if (idx + 1) % 25 == 0:
                _p(f"  {idx+1}/{len(universo)} ... ({ok} ok)")
        except Exception as e:
            falha += 1
            if falha <= 5:
                _p(f"  falha {tk}: {e}")
        time.sleep(args.sleep)

    _p("=" * 56)
    _p(f"  concluido: {ok} atualizados, {pulado} sem setor, {falha} falhas")
    _p(f"  distribuicao canonica: {dict(sorted(_dist.items(), key=lambda x:-x[1]))}")
    _p("  agora rode: python scripts/backtest_divergencias.py --anos 8 --min-persist 2")


if __name__ == "__main__":
    main()
