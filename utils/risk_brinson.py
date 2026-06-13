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


# Variantes EN (yfinance/FMP) e PT (BRAPI/B3 granular) → setor canônico macro
_MAPA_SETOR = {
    # Tecnologia
    'technology': 'tecnologia',
    'information technology': 'tecnologia',
    'tecnologia da informação': 'tecnologia',
    'software': 'tecnologia',
    'hardware e equipamentos': 'tecnologia',
    'programas e serviços': 'tecnologia',
    # Comunicação
    'communication services': 'comunicação',
    'communications': 'comunicação',
    'telecomunicações': 'comunicação',
    'mídia': 'comunicação',
    # Consumo cíclico / discricionário
    'consumer cyclical': 'consumo cíclico',
    'consumer discretionary': 'consumo cíclico',
    'comércio': 'consumo cíclico',
    'comércio e distribuição': 'consumo cíclico',
    'tecidos, vestuário e calçados': 'consumo cíclico',
    'utilidades domésticas': 'consumo cíclico',
    'viagens e lazer': 'consumo cíclico',
    'automóveis e motocicletas': 'consumo cíclico',
    'hotéis e restaurantes': 'consumo cíclico',
    'mídia impressa': 'consumo cíclico',
    'diversos': 'consumo cíclico',
    'construção civil': 'consumo cíclico',
    # Consumo defensivo / staples
    'consumer defensive': 'consumo defensivo',
    'consumer staples': 'consumo defensivo',
    'alimentos processados': 'consumo defensivo',
    'bebidas': 'consumo defensivo',
    'produtos de uso pessoal e de limpeza': 'consumo defensivo',
    'comércio e distribuição (cons. básico)': 'consumo defensivo',
    'agropecuária': 'consumo defensivo',
    # Energia
    'energy': 'energia',
    'petróleo, gás e biocombustíveis': 'energia',
    'petróleo e gás': 'energia',
    # Financeiro
    'financial services': 'financeiro',
    'financials': 'financeiro',
    'intermediários financeiros': 'financeiro',
    'previdência e seguros': 'financeiro',
    'serviços financeiros diversos': 'financeiro',
    'holdings diversificadas': 'financeiro',
    # Saúde
    'healthcare': 'saúde',
    'health care': 'saúde',
    'comércio e distribuição (saúde)': 'saúde',
    # Industrial
    'industrials': 'industrial',
    'máquinas e equipamentos': 'industrial',
    'material de transporte': 'industrial',
    'transporte': 'industrial',
    'serviços diversos': 'industrial',
    'construção e engenharia': 'industrial',
    'serviços educacionais': 'industrial',
    # Materiais básicos
    'basic materials': 'materiais básicos',
    'materials': 'materiais básicos',
    'mineração': 'materiais básicos',
    'siderurgia e metalurgia': 'materiais básicos',
    'papel e celulose': 'materiais básicos',
    'químicos': 'materiais básicos',
    'madeira e papel': 'materiais básicos',
    'embalagens': 'materiais básicos',
    # Imobiliário (REIT/FII operacional)
    'real estate': 'imobiliário',
    'exploração de imóveis': 'imobiliário',
    'incorporação': 'imobiliário',
    # Utilities (energia elétrica + saneamento + gás)
    'utilities': 'utilities',
    'energia elétrica': 'utilities',
    'água e saneamento': 'utilities',
    'gás': 'utilities',
}

# Lookup por ticker para os principais quando o setor cache está vazio
_TICKERS_SETOR_OVERRIDE = {
    'PETR3.SA': 'energia', 'PETR4.SA': 'energia', 'PRIO3.SA': 'energia',
    'VALE3.SA': 'materiais básicos', 'CSNA3.SA': 'materiais básicos',
    'USIM5.SA': 'materiais básicos', 'GGBR4.SA': 'materiais básicos',
    'ITUB3.SA': 'financeiro', 'ITUB4.SA': 'financeiro',
    'BBDC3.SA': 'financeiro', 'BBDC4.SA': 'financeiro',
    'BBAS3.SA': 'financeiro', 'SANB11.SA': 'financeiro',
    'BPAC11.SA': 'financeiro', 'BBSE3.SA': 'financeiro',
    'ITSA4.SA': 'financeiro',
    'WEGE3.SA': 'industrial', 'EMBR3.SA': 'industrial',
    'RAIL3.SA': 'industrial',
    'MGLU3.SA': 'consumo cíclico', 'LREN3.SA': 'consumo cíclico',
    'RENT3.SA': 'consumo cíclico', 'AMER3.SA': 'consumo cíclico',
    'ABEV3.SA': 'consumo defensivo', 'JBSS3.SA': 'consumo defensivo',
    'BRFS3.SA': 'consumo defensivo', 'NTCO3.SA': 'consumo defensivo',
    'ELET3.SA': 'utilities', 'ELET6.SA': 'utilities',
    'CMIG3.SA': 'utilities', 'CMIG4.SA': 'utilities',
    'CPLE6.SA': 'utilities', 'EGIE3.SA': 'utilities',
    'EQTL3.SA': 'utilities', 'SBSP3.SA': 'utilities',
    'RADL3.SA': 'saúde', 'HAPV3.SA': 'saúde', 'RDOR3.SA': 'saúde',
    'VIVT3.SA': 'comunicação', 'TIMS3.SA': 'comunicação',
    'TOTS3.SA': 'tecnologia',
    'B3SA3.SA': 'financeiro',
    'SUZB3.SA': 'materiais básicos', 'KLBN11.SA': 'materiais básicos',
}


def _normalizar_setor(s: str, ticker: str = "") -> str:
    """Padroniza nomes de setor para agregação consistente.
    Aceita ticker opcional para usar override quando o setor cache está vazio."""
    if not s and ticker and ticker in _TICKERS_SETOR_OVERRIDE:
        return _TICKERS_SETOR_OVERRIDE[ticker]
    if not s:
        return "outros"
    s = str(s).strip().lower()
    if s in _MAPA_SETOR:
        return _MAPA_SETOR[s]
    # Fallback: aplica override do ticker se há informação setor vaga
    if ticker and ticker in _TICKERS_SETOR_OVERRIDE:
        return _TICKERS_SETOR_OVERRIDE[ticker]
    return s


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
        setor = _normalizar_setor(setores.get(tk, ""), ticker=tk)
        d = por_setor_carteira.setdefault(setor, {'peso': 0.0, 'peso_x_ret': 0.0})
        d['peso'] += peso
        d['peso_x_ret'] += peso * float(rets[tk])

    # Agrega por setor — benchmark
    por_setor_bench: dict[str, dict] = {}
    for tk in bench_tickers:
        peso_b = pesos_bench[tk]
        setor = _normalizar_setor(setores.get(tk, ""), ticker=tk)
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
