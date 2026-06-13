"""
utils/portfolio_stress.py — stress tests setoriais heurísticos.

Diferente do stress por beta (que aplica choque de mercado uniforme via β_IBOV/β_SP),
esse módulo modela cenários macro com **sensibilidades setoriais** baseadas em
literatura/intuição econômica. Cada cenário tem um vetor `setor → impacto_pct` que
estima como cada setor reagiria ao choque.

Não é Monte Carlo — é estimativa de primeira ordem útil para "o que aconteceria
se o Copom subir 200bps amanhã?".
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# Cenários e sensibilidades — calibradas com base em literatura macro/setorial.
# Cada chave do dict interno é um setor (lowercase) ou "_default" para outros.
# Os nomes de setor devem casar com os normalizados em utils.risk_brinson._normalizar_setor.
CENARIOS: dict[str, dict[str, float]] = {
    "🏦 Copom +200bps": {
        "financeiro":            +3.0,   # NIM melhora curto prazo
        "utilities":             -4.0,
        "imobiliário":           -6.0,
        "consumo cíclico":       -5.0,
        "tecnologia":            -3.0,
        "industrial":            -2.0,
        "consumo defensivo":     -1.0,
        "energia":               -1.0,
        "_default":              -2.0,
    },
    "📉 S&P 500 -10%": {
        "tecnologia":           -12.0,
        "financeiro":           -10.0,
        "energia":               -8.0,
        "saúde":                 -5.0,
        "consumo defensivo":     -3.0,
        "utilities":             -3.0,
        "imobiliário":           -4.0,
        "industrial":            -9.0,
        "materiais básicos":    -10.0,
        "consumo cíclico":      -11.0,
        "comunicação":           -8.0,
        "_default":              -8.0,
    },
    "💵 USD/BRL +10%": {
        # Exportadoras (commodities, papel, mineração) ganham; importadoras (varejo, aéreas) perdem
        "materiais básicos":     +8.0,
        "energia":               +6.0,
        "industrial":            +2.0,   # mix exportador/importador
        "consumo cíclico":       -8.0,
        "consumo defensivo":     -3.0,
        "tecnologia":            -2.0,
        "saúde":                 -2.0,
        "imobiliário":           -3.0,
        "financeiro":             0.0,
        "utilities":             -1.0,
        "_default":              -2.0,
    },
    "🛢️ Petróleo +30%": {
        "energia":              +18.0,
        "materiais básicos":     +5.0,
        "industrial":            -3.0,
        "consumo cíclico":       -3.0,
        "consumo defensivo":     -1.0,
        "imobiliário":           -1.0,
        "financeiro":             0.0,
        "_default":              -1.0,
    },
    "🌐 Risk-off global": {
        "tecnologia":           -15.0,
        "consumo cíclico":      -12.0,
        "industrial":           -10.0,
        "materiais básicos":    -10.0,
        "financeiro":            -8.0,
        "energia":               -6.0,
        "imobiliário":           -7.0,
        "comunicação":           -7.0,
        "saúde":                 -3.0,
        "consumo defensivo":     -2.0,
        "utilities":             -2.0,
        "_default":              -7.0,
    },
}


@dataclass
class StressSetorialResult:
    """Resultado de stress setorial."""
    cenario: str
    impacto_total_pct: float           # impacto agregado na carteira (%)
    impacto_total_brl: float
    valor_carteira: float
    por_posicao: list[dict] = field(default_factory=list)
    # cada item: {ticker, setor, peso_pct, impacto_setor_pct, contribuicao_pct, contribuicao_brl}
    por_setor: list[dict] = field(default_factory=list)
    # cada item: {setor, peso_pct, impacto_setor_pct, contribuicao_pct}


def calcular_stress_setorial(
    pesos_carteira: dict[str, float],
    setores: dict[str, str],
    cenario: str,
    valor_carteira: float,
) -> Optional[StressSetorialResult]:
    """
    Aplica um cenário de stress setorial à carteira.

    `pesos_carteira`: {ticker: peso_decimal} — soma ≈ 1.0
    `setores`: {ticker: setor_str} — case-insensitive
    `cenario`: chave de CENARIOS (ex.: "🏦 Copom +200bps")
    `valor_carteira`: R$ total para converter % em $

    Retorna None se cenário inválido ou carteira vazia.
    """
    if cenario not in CENARIOS or not pesos_carteira:
        return None

    sensib = CENARIOS[cenario]
    default = sensib.get("_default", 0.0)

    from utils.risk_brinson import _normalizar_setor

    por_posicao: list[dict] = []
    por_setor_agg: dict[str, dict] = {}
    impacto_total_pct = 0.0

    for tk, peso in pesos_carteira.items():
        if peso <= 0:
            continue
        setor_norm = _normalizar_setor(setores.get(tk, ""), ticker=tk)
        impacto_setor = sensib.get(setor_norm, default)
        # Contribuição: peso × impacto setorial
        contribuicao = peso * impacto_setor  # em %
        contribuicao_brl = contribuicao / 100 * valor_carteira

        por_posicao.append({
            "ticker": tk,
            "setor": setor_norm,
            "peso_pct": round(peso * 100, 2),
            "impacto_setor_pct": round(impacto_setor, 2),
            "contribuicao_pct": round(contribuicao, 3),
            "contribuicao_brl": round(contribuicao_brl, 2),
        })
        impacto_total_pct += contribuicao

        # Agrega por setor
        d = por_setor_agg.setdefault(
            setor_norm,
            {"peso_pct": 0.0, "impacto_setor_pct": impacto_setor, "contribuicao_pct": 0.0},
        )
        d["peso_pct"] += peso * 100
        d["contribuicao_pct"] += contribuicao

    por_setor = [
        {"setor": s, **{k: round(v, 2) for k, v in vals.items()}}
        for s, vals in sorted(por_setor_agg.items(), key=lambda x: x[1]["contribuicao_pct"])
    ]

    return StressSetorialResult(
        cenario=cenario,
        impacto_total_pct=round(impacto_total_pct, 2),
        impacto_total_brl=round(impacto_total_pct / 100 * valor_carteira, 2),
        valor_carteira=valor_carteira,
        por_posicao=sorted(por_posicao, key=lambda x: x["contribuicao_pct"]),
        por_setor=por_setor,
    )
