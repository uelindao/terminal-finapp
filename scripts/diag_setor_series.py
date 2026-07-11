"""
scripts/diag_setor_series.py — diagnostico das series setoriais (PLANO_MACRO).

Pinpoint de por que 'carregar_retornos_setoriais_br' voltou vazio: mede a
cobertura do price_history, o mapeamento ticker->setor e o resultado da agregacao.

Uso:  python scripts/diag_setor_series.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _p(txt=""):
    print(str(txt).encode("ascii", "replace").decode())


def main():
    from database.db import get_price_history_batch, get_todos_fundamentos_cache
    from utils.tickers import SCREENER_B3, FII_TODOS, mapear_ticker_base
    from utils.setores import normalizar_setor

    _p("=" * 64)
    _p("  DIAGNOSTICO SERIES SETORIAIS")
    _p("=" * 64)

    # 1) fundamentals_cache tem setor?
    cache = get_todos_fundamentos_cache() or {}
    _p(f"[1] fundamentals_cache: {len(cache)} tickers")

    # 1a) cobertura de 'setor' em TODO o cache + formato das chaves
    _com_setor_total = sum(1 for v in cache.values() if isinstance(v, dict) and v.get("setor"))
    _p(f"    entradas com 'setor' preenchido: {_com_setor_total} de {len(cache)}")
    _amostra_chaves = list(cache.keys())[:10]
    _p(f"    amostra de CHAVES do cache: {_amostra_chaves}")
    # 1b) tickers BR famosos: o que o cache retorna?
    _p("    --- lookup de tickers conhecidos (chave -> setor) ---")
    for tk in ["PETR4.SA", "VALE3.SA", "ITUB4.SA", "BBAS3.SA", "ABEV3.SA", "WEGE3.SA"]:
        _base = mapear_ticker_base(tk)
        _e_sa = cache.get(tk)
        _e_base = cache.get(_base)
        _hit = _e_sa if isinstance(_e_sa, dict) else (_e_base if isinstance(_e_base, dict) else {})
        _via = "tk" if isinstance(_e_sa, dict) else ("base:" + _base if isinstance(_e_base, dict) else "AUSENTE")
        _p(f"      {tk:<10} [{_via}] setor={_hit.get('setor')!r}  nome={str(_hit.get('nome'))[:18]!r}")
    com_setor = 0
    setor_por_ticker = {}
    for tk in list(SCREENER_B3) + list(FII_TODOS):
        raw = (cache.get(tk) or cache.get(mapear_ticker_base(tk)) or {}).get("setor")
        c = normalizar_setor(raw)
        if c:
            setor_por_ticker[tk] = c
            com_setor += 1
    _p(f"    tickers B3+FII com setor mapeado: {com_setor} de {len(SCREENER_B3)+len(FII_TODOS)}")
    _dist = {}
    for s in setor_por_ticker.values():
        _dist[s] = _dist.get(s, 0) + 1
    _p(f"    setores distintos (canonizados): {len(_dist)} -> {dict(sorted(_dist.items(), key=lambda x:-x[1])[:12])}")

    # Dump dos valores CRUS de setor (reversivel via repr — preserva acentos) para
    # construir o mapa exato B3-subsetor -> canonico.
    _p("    --- valores CRUS de 'setor' no cache (repr + contagem) ---")
    _raw_count = {}
    for tk in list(SCREENER_B3) + list(FII_TODOS):
        raw = (cache.get(tk) or cache.get(mapear_ticker_base(tk)) or {}).get("setor")
        if raw:
            _raw_count[str(raw)] = _raw_count.get(str(raw), 0) + 1
    for raw, n in sorted(_raw_count.items(), key=lambda x: -x[1]):
        _p(f"      {n:>3}x  {raw!r}")

    # 2) price_history: cobertura de uma amostra de B3
    amostra = list(SCREENER_B3[:30])
    _p(f"[2] price_history: consultando amostra de {len(amostra)} tickers B3 (dias=400)...")
    df = get_price_history_batch(amostra, dias=400)
    _p(f"    shape retornado: {df.shape}  (linhas=datas, colunas=tickers)")
    if not df.empty:
        _p(f"    periodo: {df.index.min()} -> {df.index.max()}")
        _p(f"    tickers com dados: {list(df.columns)[:10]}{'...' if df.shape[1] > 10 else ''}")
    else:
        _p("    >>> VAZIO: price_history nao tem esses tickers (ou tabela vazia).")

    # 3) agregacao real
    _p("[3] carregar_retornos_setoriais_br(dias=400)...")
    from utils.setor_series import carregar_retornos_setoriais_br
    ret = carregar_retornos_setoriais_br(dias=400)
    _p(f"    retorno setorial shape: {ret.shape}")
    if not ret.empty:
        _p(f"    setores: {list(ret.columns)}")
        _p(f"    semanas de dados (aprox): {ret.notna().any(axis=1).sum()} dias uteis")

    _p("=" * 64)
    if df.empty:
        _p("  CONCLUSAO: rode  python scripts/sync_price_history.py  (cold start ~15-20min)")
        _p("             para popular o price_history das acoes B3.")
    elif ret.empty:
        _p("  CONCLUSAO: price_history OK mas agregacao vazia — revisar mapeamento de setor.")
    else:
        _p("  CONCLUSAO: series OK — o backtest deve rodar.")


if __name__ == "__main__":
    main()
