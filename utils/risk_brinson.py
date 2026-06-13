"""
utils/risk_brinson.py — atribuição de performance Brinson-Hood-Beebower.

Decompõe o retorno excessivo da carteira vs benchmark em três componentes:

  Allocation = Σᵢ (wᵖᵢ − wᵇᵢ) × rᵇᵢ
    impacto de ter pesos setoriais diferentes do benchmark.
    Positivo: você superpesou setores que subiram.

  Selection  = Σᵢ wᵇᵢ × (rᵖᵢ − rᵇᵢ)
    impacto de escolher ativos melhores que a média do setor no benchmark.

  Interaction = Σᵢ (wᵖᵢ − wᵇᵢ) × (rᵖᵢ − rᵇᵢ)
    cruzamento — geralmente pequeno; agrupado quando a UI quer só 2 componentes.

Soma dos três = r_portfolio − r_benchmark.

Benchmark "sintético": ponderado por market_cap dos tickers do universo
(SCREENER_B3 ou SCREENER_US). Não é o IBOV/S&P real, mas uma boa proxy
quando a carteira é mais concentrada em large/mid caps.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np


@dataclass
class ResultadoBrinson:
    """Decomposição Brinson de uma carteira vs benchmark sintético."""
    retorno_carteira: float          # decimal
    retorno_benchmark: float
    retorno_excessivo: float
    allocation: float
    selection: float
    interaction: float
    por_setor: dict[str, dict] = field(default_factory=dict)
    # {setor: {peso_p, peso_b, ret_p, ret_b, alloc, sel, inter}}


def _normalizar_setor(s: str) -> str:
    """Padroniza nomes de setor para agregação consistente."""
    if not s:
        return "outros"
    s = str(s).strip().lower()
    # Mapeamento de variações conhecidas (yfinance/brapi/fmp) → canônico
    mapa = {
        'technology': 'tecnologia',
        'information technology': 'tecnologia',
        'tecnologia da informação': 'tecnologia',
        'communication services': 'comunicação',
        'communications': 'comunicação',
        'consumer cyclical': 'consumo cíclico',
        'consumer discretionary': 'consumo cíclico',
        'consumer defensive': 'consumo defensivo',
        'consumer staples': 'consumo defensivo',
        'energy': 'energia',
        'financial services': 'financeiro',
        'financials': 'financeiro',
        'healthcare': 'saúde',
        'health care': 'saúde',
        'industrials': 'industrial',
        'basic materials': 'materiais básicos',
        'materials': 'materiais básicos',
        'real estate': 'imobiliário',
        'utilities': 'utilities',
    }
    return mapa.get(s, s)


def _retornos_periodo(precos: pd.DataFrame) -> pd.Series:
    """Retorno total do período para cada coluna (último / primeiro − 1)."""
    if precos is None or precos.empty:
        return pd.Series(dtype=float)
    primeira = precos.iloc[0]
    ultima = precos.iloc[-1]
    return ((ultima / primeira) - 1).dropna()


def calcular_brinson(
    pesos_carteira: dict[str, float],
    universo_benchmark: list[str],
    setores: dict[str, str],
    market_caps: dict[str, float],
    precos: pd.DataFrame,
) -> Optional[ResultadoBrinson]:
    """
    Calcula decomposição Brinson da carteira vs benchmark sintético.

    `pesos_carteira`: {ticker: peso_decimal} — somar ≈ 1.0
    `universo_benchmark`: lista de tickers que compõem o benchmark
                         (ex.: SCREENER_B3)
    `setores`: {ticker: setor_str}
    `market_caps`: {ticker: market_cap_brl} — para ponderar o benchmark
    `precos`: DataFrame de Close, datas no índice, colunas = tickers
              (precisa cobrir tanto carteira quanto universo)

    Retorna None se faltarem dados essenciais.
    """
    if not pesos_carteira or precos is None or precos.empty:
        return None

    # Retornos totais por ticker no período
    rets = _retornos_periodo(precos)
    if rets.empty:
        return None

    # Filtra universo do benchmark — apenas tickers com mkt cap > 0 e retorno disponível
    bench_tickers = [
        t for t in universo_benchmark
        if t in market_caps and market_caps.get(t, 0) > 0 and t in rets.index
    ]
    if not bench_tickers:
        return None

    # Pesos do benchmark (proporcional a market_cap)
    total_mc = sum(market_caps[t] for t in bench_tickers)
    if total_mc <= 0:
        return None
    pesos_bench = {t: market_caps[t] / total_mc for t in bench_tickers}

    # Agrega por setor — carteira
    por_setor_carteira: dict[str, dict] = {}
    for tk, peso in pesos_carteira.items():
        if peso <= 0 or tk not in rets.index:
            continue
        setor = _normalizar_setor(setores.get(tk, ""))
        d = por_setor_carteira.setdefault(setor, {'peso': 0.0, 'peso_x_ret': 0.0})
        d['peso'] += peso
        d['peso_x_ret'] += peso * float(rets[tk])

    # Agrega por setor — benchmark
    por_setor_bench: dict[str, dict] = {}
    for tk in bench_tickers:
        peso_b = pesos_bench[tk]
        setor = _normalizar_setor(setores.get(tk, ""))
        d = por_setor_bench.setdefault(setor, {'peso': 0.0, 'peso_x_ret': 0.0})
        d['peso'] += peso_b
        d['peso_x_ret'] += peso_b * float(rets[tk])

    # Setores presentes em qualquer um dos dois
    todos_setores = sorted(set(por_setor_carteira.keys()) | set(por_setor_bench.keys()))

    por_setor: dict[str, dict] = {}
    alloc_total = sel_total = inter_total = 0.0
    ret_carteira = ret_bench = 0.0

    for s in todos_setores:
        wp = por_setor_carteira.get(s, {}).get('peso', 0.0)
        wb = por_setor_bench.get(s, {}).get('peso', 0.0)
        rp = (por_setor_carteira[s]['peso_x_ret'] / wp) if wp > 0 else 0.0
        rb = (por_setor_bench[s]['peso_x_ret'] / wb) if wb > 0 else 0.0

        alloc = (wp - wb) * rb
        sel = wb * (rp - rb)
        inter = (wp - wb) * (rp - rb)

        por_setor[s] = {
            'peso_p': wp, 'peso_b': wb,
            'ret_p': rp,  'ret_b': rb,
            'alloc': alloc, 'sel': sel, 'inter': inter,
        }
        alloc_total += alloc
        sel_total += sel
        inter_total += inter

        ret_carteira += wp * rp
        ret_bench += wb * rb

    return ResultadoBrinson(
        retorno_carteira=ret_carteira,
        retorno_benchmark=ret_bench,
        retorno_excessivo=ret_carteira - ret_bench,
        allocation=alloc_total,
        selection=sel_total,
        interaction=inter_total,
        por_setor=por_setor,
    )
