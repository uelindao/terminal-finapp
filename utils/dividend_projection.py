"""
utils/dividend_projection.py — projeção de dividendos 12 meses.

Lê histórico do cache (dividend_history) e projeta os próximos 12 pagamentos
usando duas premissas:

1. Frequência (mensal/trimestral/semestral/anual) é estável — basta detectar
   o padrão dos últimos 24 meses e replicar.
2. Crescimento YoY = soma 12m recente / soma 12m anterior − 1. Cap em 10%
   para evitar extrapolar saltos pontuais (mudança de política de payout).

Para FIIs (mensal) a projeção é precisa; para ações trimestrais/anuais o
modelo erra mais quando a empresa muda payout — mas serve como referência.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, timedelta
from collections import Counter

import pandas as pd


# Crescimento máximo aplicado à projeção. Reduz o risco de extrapolar um
# salto pontual que não vai se repetir.
_CRESCIMENTO_MAX = 0.10


@dataclass
class ResultadoProjecao:
    """Projeção 12m de dividendos da carteira."""
    renda_total_12m: float            # R$
    dy_projetado_pct: float           # %
    valor_carteira: float             # R$
    por_mes: dict[str, float]         # {"Jul/26": 1234.0, ...} — 12 meses
    por_ticker: dict[str, float]      # {"PETR4.SA": 800.0, ...}
    detalhes_ticker: dict[str, dict]  # {ticker: {freq, growth, last_div, n_pagamentos}}


def _detectar_frequencia(datas: pd.Series) -> tuple[str, int]:
    """
    Retorna (label, n_pagamentos_por_ano_estimado) baseado nas datas.
    Considera os últimos 12 meses de dados.
    """
    if datas.empty:
        return "desconhecida", 0
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=365)
    recentes = datas[datas >= cutoff]
    n = len(recentes)
    if n >= 10:
        return "mensal", 12
    elif n >= 6:
        return "bimestral", 6
    elif n >= 3:
        return "trimestral", 4
    elif n >= 2:
        return "semestral", 2
    elif n == 1:
        return "anual", 1
    return "irregular", 0


def _crescimento_yoy(df: pd.DataFrame) -> float:
    """
    Taxa de crescimento YoY = soma últimos 12m / soma 12-24m anteriores − 1.
    Retorna 0 quando não há dois períodos comparáveis. Aplica cap simétrico.
    """
    if df.empty:
        return 0.0
    hoje = pd.Timestamp.now().normalize()
    c12 = hoje - pd.Timedelta(days=365)
    c24 = hoje - pd.Timedelta(days=730)
    recente = df[df['data_pagamento'] >= c12]['valor'].sum()
    anterior = df[(df['data_pagamento'] >= c24) & (df['data_pagamento'] < c12)]['valor'].sum()
    if anterior <= 0:
        return 0.0
    g = (recente / anterior) - 1
    return max(-_CRESCIMENTO_MAX, min(_CRESCIMENTO_MAX, g))


def _projetar_ticker(
    df_hist: pd.DataFrame,
    quantidade: float,
    hoje: Optional[date] = None,
) -> tuple[dict[str, float], dict]:
    """
    Projeta pagamentos por mês (próximos 12) para um ticker.
    Retorna ({mes_str: valor_por_cota * quantidade}, detalhes).

    Modelo: replica o padrão dos últimos 12m × (1 + growth), mês a mês.
    Para frequência mensal, usa média dos últimos 6 pagamentos × crescimento.
    """
    if hoje is None:
        hoje = date.today()
    detalhes = {
        'freq': 'desconhecida',
        'n_payments_12m': 0,
        'growth': 0.0,
        'last_div': None,
    }
    if df_hist.empty:
        return {}, detalhes

    df_hist = df_hist.copy()
    df_hist['data_pagamento'] = pd.to_datetime(df_hist['data_pagamento'])
    df_hist = df_hist.sort_values('data_pagamento').reset_index(drop=True)

    freq, n_ano = _detectar_frequencia(df_hist['data_pagamento'])
    growth = _crescimento_yoy(df_hist)

    cutoff_12m = pd.Timestamp(hoje) - pd.Timedelta(days=365)
    recentes = df_hist[df_hist['data_pagamento'] >= cutoff_12m]
    detalhes.update({
        'freq': freq,
        'n_payments_12m': len(recentes),
        'growth': growth,
        'last_div': float(df_hist.iloc[-1]['valor']) if len(df_hist) else None,
    })

    if recentes.empty or n_ano == 0:
        return {}, detalhes

    por_mes: dict[str, float] = {}

    # Estratégia: para cada pagamento dos últimos 12m, prevê um pagamento
    # equivalente +12 meses depois × (1 + growth).
    for _, row in recentes.iterrows():
        data_pag = row['data_pagamento'].date()
        valor_cota = float(row['valor'])
        data_proj = date(data_pag.year + 1, data_pag.month, min(data_pag.day, 28))
        # só conta se cair nos próximos 12 meses
        if data_proj <= hoje or data_proj > hoje + timedelta(days=370):
            continue
        valor_proj = valor_cota * (1 + growth) * quantidade
        mes_key = data_proj.strftime("%b/%y").lower()
        por_mes[mes_key] = por_mes.get(mes_key, 0.0) + valor_proj

    return por_mes, detalhes


def projetar_dividendos_carteira(
    quantidades: dict[str, float],
    valor_carteira: float,
    meses_historico: int = 730,
) -> ResultadoProjecao:
    """
    Projeta dividendos 12m da carteira inteira.

    `quantidades`: dict {ticker_base: qtd_cotas} — usa ticker já normalizado
                   (sem mapeamento .SA extra). Lê de dividend_history direto.
    `valor_carteira`: total alocado em R$, para calcular DY projetado.
    `meses_historico`: janela em dias usada para buscar histórico (default 24m).
    """
    from database.db import get_dividend_history

    por_mes_total: dict[str, float] = {}
    por_ticker: dict[str, float] = {}
    detalhes_ticker: dict[str, dict] = {}
    hoje = date.today()

    # Gera as 12 chaves de mês na ordem cronológica (para o calendário)
    meses_ordem: list[str] = []
    for i in range(1, 13):
        m = hoje.month + i
        a = hoje.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        meses_ordem.append(date(a, m, 1).strftime("%b/%y").lower())

    for ticker, qtd in quantidades.items():
        if qtd <= 0:
            continue
        df_hist = get_dividend_history(ticker, dias=meses_historico)
        por_mes_t, det = _projetar_ticker(df_hist, qtd, hoje=hoje)
        detalhes_ticker[ticker] = det
        if not por_mes_t:
            por_ticker[ticker] = 0.0
            continue
        total_t = sum(por_mes_t.values())
        por_ticker[ticker] = total_t
        for m, v in por_mes_t.items():
            por_mes_total[m] = por_mes_total.get(m, 0.0) + v

    # Preenche meses vazios com 0 (mantém ordem cronológica)
    por_mes_ordenado = {m: por_mes_total.get(m, 0.0) for m in meses_ordem}

    renda_total = sum(por_mes_total.values())
    dy_proj = (renda_total / valor_carteira * 100) if valor_carteira > 0 else 0.0

    return ResultadoProjecao(
        renda_total_12m=renda_total,
        dy_projetado_pct=dy_proj,
        valor_carteira=valor_carteira,
        por_mes=por_mes_ordenado,
        por_ticker=por_ticker,
        detalhes_ticker=detalhes_ticker,
    )
