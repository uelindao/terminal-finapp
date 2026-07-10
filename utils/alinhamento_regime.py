"""
utils/alinhamento_regime.py — alinhamento carteira × regime macro (PLANO_FRONT F3-2).

O elo direto entre o motor macro (tilt setorial, validado no backtest) e a
carteira do usuário: "quanto do meu capital está em setores FAVORECIDOS pelo
regime atual, e quanto em setores PENALIZADOS?".

Função PURA por injeção de dependência (`tilt_fn`) — a página faz o I/O (pesos,
cache de fundamentos, macro_context) e passa tudo pronto. Testável sem rede/Streamlit.

Ponderação: a página passa `peso` já computado por posição (recomendado: custo =
quantidade × preço médio — cache-first, sem cotação ao vivo). Qualquer escala
positiva serve; os percentuais são normalizados pela soma.
"""
from __future__ import annotations

from typing import Callable, Optional

_IMPACTOS = ("favoravel", "desfavoravel", "neutro")


def _mercado_do_ticker(ticker: str) -> str:
    """BR para tickers .SA (ações BR e FIIs); US caso contrário."""
    return "BR" if str(ticker).upper().endswith(".SA") else "US"


def alinhamento_regime(
    posicoes: list[dict],
    fund_cache: dict,
    macro_context: dict,
    *,
    tilt_fn: Optional[Callable] = None,
) -> dict:
    """
    posicoes      : [{'ticker': str, 'peso': float > 0}] — peso em qualquer escala
                    positiva (será normalizado). Posições com peso <= 0 são ignoradas.
    fund_cache    : {ticker: {'setor': str, ...}} (get_todos_fundamentos_cache).
    macro_context : {selic, treasury_10y, vix, ...}.
    tilt_fn       : (setor, macro_context, market) -> {'impacto','pontos',...}.
                    Default: utils.macro_state.tilt_setor (import tardio).

    Retorna:
        {
          'total': soma dos pesos considerados,
          'favoravel_pct' / 'desfavoravel_pct' / 'neutro_pct' / 'sem_setor_pct',
          'saldo_pontos': média ponderada de pontos de tilt (-4..+4) — leitura única
                          do alinhamento líquido da carteira,
          'itens': [{'ticker','setor','peso','peso_pct','impacto','pontos'}] desc por peso,
        }
    """
    if tilt_fn is None:
        # import tardio: evita puxar streamlit/macro_state no import deste módulo
        from utils.macro_state import tilt_setor as tilt_fn

    itens: list[dict] = []
    total = 0.0
    acc = {"favoravel": 0.0, "desfavoravel": 0.0, "neutro": 0.0, "sem_setor": 0.0}
    saldo_peso_pontos = 0.0

    for p in posicoes or []:
        tk = p.get("ticker")
        try:
            peso = float(p.get("peso"))
        except (TypeError, ValueError):
            continue
        if not tk or peso <= 0:
            continue
        total += peso

        setor = (fund_cache.get(tk) or {}).get("setor") or ""
        if not setor:
            acc["sem_setor"] += peso
            itens.append({"ticker": tk, "setor": "", "peso": peso,
                          "impacto": "sem_setor", "pontos": 0})
            continue

        try:
            til = tilt_fn(setor, macro_context, _mercado_do_ticker(tk)) or {}
        except Exception:
            til = {}
        impacto = til.get("impacto", "neutro")
        if impacto not in _IMPACTOS:
            impacto = "neutro"
        pontos = int(til.get("pontos", 0) or 0)

        acc[impacto] += peso
        saldo_peso_pontos += peso * pontos
        itens.append({"ticker": tk, "setor": setor, "peso": peso,
                      "impacto": impacto, "pontos": pontos})

    if total <= 0:
        return {"total": 0.0, "favoravel_pct": 0.0, "desfavoravel_pct": 0.0,
                "neutro_pct": 0.0, "sem_setor_pct": 0.0, "saldo_pontos": 0.0,
                "itens": []}

    for it in itens:
        it["peso_pct"] = it["peso"] / total * 100.0
    itens.sort(key=lambda x: x["peso"], reverse=True)

    return {
        "total": total,
        "favoravel_pct": acc["favoravel"] / total * 100.0,
        "desfavoravel_pct": acc["desfavoravel"] / total * 100.0,
        "neutro_pct": acc["neutro"] / total * 100.0,
        "sem_setor_pct": acc["sem_setor"] / total * 100.0,
        "saldo_pontos": saldo_peso_pontos / total,
        "itens": itens,
    }
