"""
scripts/backtest_health_score.py
================================
Backtest do health score: mede se o score PREDIZ retorno futuro (Information
Coefficient) — a validação honesta de "podemos confiar mais no número?".

Metodologia:
  Para cada observação (ticker, data, score) do health_score_history, calcula o
  retorno FORWARD (preço em data+H / preço em data − 1) usando price_history, para
  horizontes H de 21/63/126 pregões (~1m/3m/6m). Depois:
    - IC = correlação de Spearman entre score e retorno forward (por mercado × H).
      IC > 0.05 = sinal preditivo útil; ~0 = sem poder; < 0 = contrário.
    - Análise por bucket: retorno forward médio de acumulação (score>=65) vs
      manutenção (40-65) vs reduzir (<40). Um score bom deve ter bucket alto
      com retorno > bucket baixo (monotonicidade).

  CAVEAT: exige histórico maduro. Observações cujo forward ainda não ocorreu
  (data+H no futuro) são descartadas. Com o scoring recente, rode de novo em
  3-6 meses para um resultado robusto.

Uso:
  python scripts/backtest_health_score.py            # todos horizontes
  python scripts/backtest_health_score.py --h 63     # só 3 meses
"""
from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import date, datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_client():
    """Client Supabase a partir de env (ETL) ou secrets.toml do repo principal."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not (url and key):
        import tomllib
        for p in (".streamlit/secrets.toml",
                  os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")):
            if os.path.exists(p):
                with open(p, "rb") as f:
                    s = tomllib.load(f)
                url = url or s.get("SUPABASE_URL", "")
                key = key or s.get("SUPABASE_SERVICE_KEY") or s.get("SUPABASE_KEY", "")
                break
    from supabase import create_client
    return create_client(url, key)


def _paginate(query_fn, page: int = 1000, cap: int = 2_000_000):
    """Coleta todas as linhas de uma tabela paginando por .range()."""
    out, off = [], 0
    while off < cap:
        rows = query_fn(off, off + page - 1)
        if not rows:
            break
        out += rows
        if len(rows) < page:
            break
        off += page
    return out


def _mercado(ticker: str) -> str:
    if ticker.endswith("11.SA"):
        return "FII"
    return "BR" if ticker.endswith(".SA") else "US"


def _spearman(pairs: list[tuple[float, float]]) -> float | None:
    """Correlação de Spearman (rank) entre x e y. None se < 10 pares."""
    n = len(pairs)
    if n < 10:
        return None

    def _ranks(vals):
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    rx, ry = _ranks(xs), _ranks(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _preco_em_ou_apos(serie: list[tuple[str, float]], alvo: str, tol_dias: int = 7):
    """serie: lista ordenada (data_str, close). Retorna o 1º close em data >= alvo
    dentro de `tol_dias` (trata feriados/fins de semana). None se fora da tolerância."""
    import bisect
    datas = [d for d, _ in serie]
    i = bisect.bisect_left(datas, alvo)
    if i >= len(serie):
        return None
    d_found = datas[i]
    try:
        gap = (date.fromisoformat(d_found) - date.fromisoformat(alvo)).days
    except ValueError:
        return None
    return serie[i][1] if gap <= tol_dias else None


def rodar_backtest(horizontes=(21, 63, 126), desde: str = "2025-09-01"):
    sb = _get_client()
    print(f"[backtest] carregando scores desde {desde}...")
    scores = _paginate(lambda a, b: sb.table("health_score_history")
                       .select("ticker,score,calculado_em")
                       .gte("calculado_em", desde)
                       .range(a, b).execute().data)
    scores = [s for s in scores if s.get("score") is not None]
    print(f"[backtest] {len(scores)} observações de score")

    tickers = sorted(set(s["ticker"] for s in scores))
    print(f"[backtest] carregando price_history de {len(tickers)} tickers...")
    precos: dict[str, list[tuple[str, float]]] = defaultdict(list)
    ph = _paginate(lambda a, b: sb.table("price_history")
                  .select("ticker,data,close")
                  .gte("data", desde)
                  .range(a, b).execute().data, page=1000)
    for row in ph:
        c = row.get("close")
        if c is not None:
            precos[row["ticker"]].append((row["data"][:10], float(c)))
    for tk in precos:
        precos[tk].sort()

    hoje = date.today().isoformat()
    # coleta pares (score, fwd_ret) por (mercado, horizonte)
    dados = defaultdict(list)  # (mkt, H) -> [(score, ret)]
    buckets = defaultdict(lambda: defaultdict(list))  # (mkt,H) -> bucket -> [ret]
    from datetime import timedelta
    for s in scores:
        tk = s["ticker"]
        serie = precos.get(tk)
        if not serie:
            continue
        d0 = s["calculado_em"][:10]
        p0 = _preco_em_ou_apos(serie, d0)
        if not p0 or p0 <= 0:
            continue
        sc = float(s["score"])
        for H in horizontes:
            try:
                d1 = (date.fromisoformat(d0) + timedelta(days=int(H * 1.42))).isoformat()
            except ValueError:
                continue
            if d1 > hoje:
                continue  # forward ainda no futuro
            p1 = _preco_em_ou_apos(serie, d1)
            if not p1 or p1 <= 0:
                continue
            ret = (p1 / p0 - 1) * 100
            mkt = _mercado(tk)
            dados[(mkt, H)].append((sc, ret))
            dados[("TODOS", H)].append((sc, ret))
            b = "acum (>=65)" if sc >= 65 else ("manut (40-65)" if sc >= 40 else "reduzir (<40)")
            buckets[(mkt, H)][b].append(ret)
            buckets[("TODOS", H)][b].append(ret)

    print("\n" + "=" * 64)
    print("INFORMATION COEFFICIENT (Spearman score × retorno forward)")
    print("=" * 64)
    _hlabel = {21: "1m", 63: "3m", 126: "6m"}
    for mkt in ("TODOS", "BR", "US", "FII"):
        for H in horizontes:
            pares = dados.get((mkt, H), [])
            ic = _spearman(pares)
            ic_s = f"{ic:+.3f}" if ic is not None else "n/d (poucos dados)"
            print(f"  {mkt:6s} {_hlabel.get(H, str(H)):3s}: IC={ic_s:20s} (n={len(pares)})")

    print("\n" + "=" * 64)
    print("RETORNO FORWARD MÉDIO POR BUCKET DE SCORE (monotonicidade)")
    print("=" * 64)
    for mkt in ("TODOS", "BR", "US", "FII"):
        for H in horizontes:
            bk = buckets.get((mkt, H))
            if not bk:
                continue
            partes = []
            for b in ("acum (>=65)", "manut (40-65)", "reduzir (<40)"):
                vs = bk.get(b, [])
                if vs:
                    partes.append(f"{b}={sum(vs)/len(vs):+.1f}% (n={len(vs)})")
            if partes:
                print(f"  {mkt:6s} {_hlabel.get(H, str(H)):3s}: " + " | ".join(partes))

    print("\nCAVEAT: histórico de score é recente (maioria jun-jul/2026). Horizontes")
    print("longos (3m/6m) têm poucos dados maduros. Rode de novo em 3-6 meses.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--h", type=int, default=None, help="horizonte único em pregões (21/63/126)")
    ap.add_argument("--desde", default="2025-09-01")
    args = ap.parse_args()
    hz = (args.h,) if args.h else (21, 63, 126)
    rodar_backtest(horizontes=hz, desde=args.desde)
