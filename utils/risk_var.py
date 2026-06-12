"""
utils/risk_var.py — Value-at-Risk e Expected Shortfall para portfólios.

Três métricas complementares:
- VaR histórico: percentil empírico da distribuição de retornos observados.
  Captura caudas reais (assimetrias, fat-tails) mas é amostral.
- VaR paramétrico: assume normal, calcula μ - z·σ. Estável mas subestima
  caudas em mercados estressados.
- CVaR (Expected Shortfall): média dos retornos abaixo do VaR. Métrica
  preferida para mandatos institucionais — sensível à magnitude das perdas
  extremas, não só à frequência.

A divergência entre histórico e paramétrico é em si um sinal: > 30% indica
"fat tails" — distribuição não-normal, prudência extra recomendada.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# z-score para nível de confiança bilateral (cauda esquerda)
_Z = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}


@dataclass
class ResultadoVaR:
    """Sumário de risco da carteira para um período/horizonte."""
    n_observacoes: int
    horizonte_dias: int
    valor_carteira: float        # R$ — base para converter % em $
    retorno_medio_diario: float  # decimal
    vol_diaria: float            # decimal (desvio padrão)
    vol_anual: float             # decimal
    var_95_pct: float            # decimal (negativo, ex.: -0.025 = perda de 2.5%)
    var_99_pct: float
    var_95_param_pct: float
    var_99_param_pct: float
    cvar_95_pct: float
    cvar_99_pct: float
    fat_tails: bool              # True se histórico > 30% pior que paramétrico no 95%
    retornos_diarios: pd.Series  # série usada (compartilhada para histograma)


def calcular_retornos_carteira(
    pesos: dict[str, float],
    precos: pd.DataFrame,
) -> pd.Series:
    """
    Calcula série de retornos diários da carteira ponderada pelos pesos.

    `pesos` é dict {ticker: peso_decimal}. Somar 1.0 (ou menos — peso ausente
    vira caixa, não computa).

    `precos` é DataFrame com índice de datas e uma coluna por ticker. Retornos
    diários são log-returns simples (pct_change). Retorna Series indexada por
    data com retorno diário ponderado.
    """
    if precos is None or precos.empty:
        return pd.Series(dtype=float)
    pesos_norm = {t: w for t, w in pesos.items() if w and w > 0 and t in precos.columns}
    if not pesos_norm:
        return pd.Series(dtype=float)
    soma = sum(pesos_norm.values())
    if soma > 0:
        pesos_norm = {t: w / soma for t, w in pesos_norm.items()}

    rets_ativos = precos[list(pesos_norm.keys())].pct_change().dropna(how="all")
    if rets_ativos.empty:
        return pd.Series(dtype=float)

    peso_arr = np.array([pesos_norm[t] for t in rets_ativos.columns])
    ret_carteira = (rets_ativos.fillna(0).values * peso_arr).sum(axis=1)
    return pd.Series(ret_carteira, index=rets_ativos.index, name="ret_carteira")


def calcular_risco_carteira(
    pesos: dict[str, float],
    precos: pd.DataFrame,
    valor_carteira: float,
    horizonte_dias: int = 1,
) -> Optional[ResultadoVaR]:
    """
    Calcula VaR/CVaR completo para uma carteira.

    `pesos`: dict ticker → peso decimal
    `precos`: DataFrame Close × ticker
    `valor_carteira`: R$ total — para converter % em $ na UI
    `horizonte_dias`: 1d (default), 5d (semanal), 21d (mensal). Escala pela
                     raiz do tempo (assumindo retornos iid)

    Retorna None se dados insuficientes (< 60 observações). UI deve tratar
    esse caso com mensagem clara em vez de mostrar números falsos.
    """
    rets = calcular_retornos_carteira(pesos, precos)
    if len(rets) < 60:
        return None

    mu = float(rets.mean())
    sigma = float(rets.std(ddof=1))
    if sigma <= 0 or not np.isfinite(sigma):
        return None

    # Escala raiz-tempo para horizontes > 1 dia
    escala = float(np.sqrt(horizonte_dias))
    mu_h = mu * horizonte_dias
    sigma_h = sigma * escala

    # VaR histórico: percentil empírico dos retornos. Para horizonte > 1, soma
    # janelas rolantes (mais preciso que escala raiz-tempo em retornos não-iid)
    if horizonte_dias > 1:
        rets_horizonte = rets.rolling(horizonte_dias).sum().dropna()
    else:
        rets_horizonte = rets

    var_95 = float(np.percentile(rets_horizonte, 5))    # cauda esquerda
    var_99 = float(np.percentile(rets_horizonte, 1))

    # VaR paramétrico: μ - z·σ (cauda esquerda)
    var_95_param = float(mu_h - _Z[0.95] * sigma_h)
    var_99_param = float(mu_h - _Z[0.99] * sigma_h)

    # CVaR: média dos retornos no quantil cauda esquerda
    abaixo_95 = rets_horizonte[rets_horizonte <= var_95]
    abaixo_99 = rets_horizonte[rets_horizonte <= var_99]
    cvar_95 = float(abaixo_95.mean()) if len(abaixo_95) > 0 else var_95
    cvar_99 = float(abaixo_99.mean()) if len(abaixo_99) > 0 else var_99

    # Fat-tails: histórico > 30% mais severo que paramétrico no 95%
    fat = abs(var_95) > abs(var_95_param) * 1.30

    return ResultadoVaR(
        n_observacoes=len(rets),
        horizonte_dias=horizonte_dias,
        valor_carteira=valor_carteira,
        retorno_medio_diario=mu,
        vol_diaria=sigma,
        vol_anual=sigma * float(np.sqrt(252)),
        var_95_pct=var_95,
        var_99_pct=var_99,
        var_95_param_pct=var_95_param,
        var_99_param_pct=var_99_param,
        cvar_95_pct=cvar_95,
        cvar_99_pct=cvar_99,
        fat_tails=fat,
        retornos_diarios=rets,
    )


def formatar_perda(pct: float, valor_carteira: float) -> tuple[str, str]:
    """Retorna (pct_str, valor_str) — perda em % e em R$. pct é negativo."""
    perda_pct = abs(pct) * 100
    perda_brl = abs(pct) * valor_carteira
    return f"{perda_pct:.2f}%", f"R$ {perda_brl:,.0f}".replace(",", ".")
