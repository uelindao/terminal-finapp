"""
utils/setor_series.py — séries de retorno setorial no tempo (PLANO_MACRO M0-1).

Constrói o "é" no tempo: a partir de preços de fechamento por ticker + o setor
canônico de cada um, produz a série de retorno diário por SETOR (equal-weight) e
a força relativa (RS) setorial = retorno acumulado do setor − mediana do universo.

Design: o núcleo é PURO por injeção de dependência (recebe o DataFrame de preços
e o mapa ticker→setor prontos) → 100% testável com fixtures sintéticas, sem rede.
O loader `carregar_retornos_setoriais_br` faz o I/O (price_history + cache de
fundamentos) e delega ao núcleo.

Vieses documentados (honestidade > número bonito):
  • SURVIVORSHIP: price_history cobre apenas tickers ATUAIS → retornos setoriais
    históricos têm viés otimista. Atenua-se ao usar RS RELATIVO entre setores
    (o viés empurra todos na mesma direção, cancelando parcialmente).
  • EQUAL-WEIGHT: sem market cap histórico, cada ticker pesa igual → viés
    small-cap. NUNCA comparar séries EW-BR com séries cap-weight (ETFs US)
    diretamente numa mesma estatística.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_JANELA_PADRAO = 63     # ~3 meses de pregões
_MIN_TICKERS = 3        # setor precisa de >= N tickers válidos no dia
_MIN_COBERTURA = 0.8    # janela precisa de >= 80% de dias válidos


def retorno_diario_setorial(
    precos: pd.DataFrame,
    setor_por_ticker: dict,
    *,
    min_tickers: int = _MIN_TICKERS,
) -> pd.DataFrame:
    """
    Retorno diário EQUAL-WEIGHT por setor.

    precos           : DataFrame index=data, columns=ticker, values=close ajustado.
    setor_por_ticker : {ticker: setor_canônico}.
    min_tickers      : dias com menos de N tickers válidos no setor → NaN (excluído,
                       nunca zerado — zerar inventaria retorno que não existiu).

    Retorna DataFrame index=data, columns=setor, values=retorno diário.
    """
    if precos is None or precos.empty:
        return pd.DataFrame()
    # fill_method=None: gaps viram NaN (correto — a média EW ignora NaN e min_tickers
    # trata), em vez do pad deprecado que fabricava retorno 0 em dias sem cotação.
    rets = precos.pct_change(fill_method=None)

    grupos: dict[str, list] = {}
    for tk in rets.columns:
        s = setor_por_ticker.get(tk)
        if s:
            grupos.setdefault(s, []).append(tk)

    out: dict[str, pd.Series] = {}
    for setor, tks in grupos.items():
        sub = rets[tks]
        media = sub.mean(axis=1)                 # EW, ignora NaN (skipna)
        n_valid = sub.notna().sum(axis=1)
        media = media.where(n_valid >= min_tickers)
        out[setor] = media
    if not out:
        return pd.DataFrame(index=precos.index)
    return pd.DataFrame(out)


def retorno_acumulado(
    retornos: pd.DataFrame,
    janela: int = _JANELA_PADRAO,
    *,
    min_cobertura: float = _MIN_COBERTURA,
) -> pd.DataFrame:
    """
    Retorno acumulado em janela móvel (via soma de log-retornos, robusto a gaps).
    Exige >= `min_cobertura` de dias válidos na janela, senão NaN.
    """
    if retornos is None or retornos.empty:
        return pd.DataFrame()
    logr = np.log1p(retornos)
    soma = logr.rolling(janela).sum()            # sum ignora NaN
    cont = logr.rolling(janela).count()
    cum = np.expm1(soma)
    return cum.where(cont >= janela * min_cobertura)


def rs_setorial(
    retornos: pd.DataFrame,
    janela: int = _JANELA_PADRAO,
    *,
    min_cobertura: float = _MIN_COBERTURA,
) -> pd.DataFrame:
    """
    Força relativa setorial = retorno acumulado do setor − MEDIANA do universo
    (cross-section por data). RS > 0 = setor batendo a mediana; < 0 = perdendo.
    """
    cum = retorno_acumulado(retornos, janela, min_cobertura=min_cobertura)
    if cum.empty:
        return pd.DataFrame()
    mediana = cum.median(axis=1)                 # mediana transversal por data
    return cum.sub(mediana, axis=0)


def rs_setorial_atual(
    retornos: pd.DataFrame,
    janela: int = _JANELA_PADRAO,
) -> dict:
    """RS setorial mais recente disponível como {setor: rs}. {} se sem dados."""
    rs = rs_setorial(retornos, janela)
    if rs.empty:
        return {}
    validas = rs.dropna(how="all")
    if validas.empty:
        return {}
    return validas.iloc[-1].dropna().to_dict()


def breadth_setorial(
    retornos: pd.DataFrame,
    janela_mm: int = 10,
) -> pd.Series:
    """
    Amplitude interna (PLANO_MACRO M4-2): % de setores cujo índice de preço está
    ACIMA da própria média móvel de `janela_mm` períodos, por data.

    Divergência de amplitude: índice forte com breadth caindo = topo estreito
    (poucos setores sustentando a alta — frágil); índice fraco com breadth
    subindo = fundo largo (melhora difusa — construtivo).
    """
    if retornos is None or retornos.empty:
        return pd.Series(dtype=float)
    idx = (1 + retornos.fillna(0.0)).cumprod()
    mm = idx.rolling(janela_mm).mean()
    valido = mm.notna()
    n_acima = (idx > mm).where(valido, other=False).sum(axis=1)
    n_total = valido.sum(axis=1)
    return (n_acima / n_total * 100.0).where(n_total > 0)


# ── loader (I/O — fora do núcleo puro/testes) ─────────────────────────────────

def carregar_retornos_setoriais_br(
    dias: int = 1260,
    *,
    min_tickers: int = _MIN_TICKERS,
) -> pd.DataFrame:
    """
    Carrega retornos diários setoriais BR (SCREENER_B3 + FIIs), agregando por
    setor canônico. Cache-first (price_history + fundamentals_cache). Retorna
    DataFrame vazio se não houver dados.
    """
    from database.db import get_price_history_batch, get_todos_fundamentos_cache
    from utils.tickers import SCREENER_B3, FII_TODOS, mapear_ticker_base
    from utils.setores import normalizar_setor

    cache = get_todos_fundamentos_cache() or {}
    universo = list(dict.fromkeys(list(SCREENER_B3) + list(FII_TODOS)))
    setor_por_ticker: dict[str, str] = {}
    for tk in universo:
        raw = (cache.get(tk) or cache.get(mapear_ticker_base(tk)) or {}).get("setor")
        canon = normalizar_setor(raw)
        if canon:
            setor_por_ticker[tk] = canon
    if not setor_por_ticker:
        return pd.DataFrame()

    precos = get_price_history_batch(list(setor_por_ticker), dias=dias)
    if precos is None or precos.empty:
        return pd.DataFrame()
    return retorno_diario_setorial(precos, setor_por_ticker, min_tickers=min_tickers)
