"""
utils/atencao_hoje.py — motor do bloco "atenção hoje" da Home (F1-1).

Responde ao job J1 do PLANO_FRONT ("o que mudou? o que exige atenção HOJE?").
Consolida, em uma lista curta e ranqueada por severidade, três classes de sinais
que já existem no banco/código do terminal — sem nenhuma chamada de rede aqui:

  1. SCORE que se moveu   → health_score_history (Δ entre as duas últimas leituras)
  2. TÉCNICO relevante    → price_cache (RSI extremo, extremos de 52s, tranco no dia)
  3. EVENTO de hoje/amanhã→ calendário macro (COPOM, FOMC, CPI, IPCA, payroll...)

Design: função PURA (`coletar_atencao_hoje`) por injeção de dependência — a Home
faz o I/O (db) e passa os dados já carregados. Isso mantém o módulo 100% testável
com fixtures sintéticas e o render cache-first (zero yfinance ao vivo).

Cada item retornado é um dict:
    {
        "tipo":       "score" | "tecnico" | "evento",
        "ticker":     str | None,        # None em eventos macro
        "icone":      str,               # emoji de severidade/direção
        "titulo":     str,               # rótulo escaneável
        "detalhe":    str,               # o "so what" (1 linha)
        "tom":        "bull"|"bear"|"amber"|"info",
        "severidade": float,             # usado só para ranquear (desc)
    }
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

# ── limiares (parametrizáveis via coletar_atencao_hoje) ──────────────────────
_DELTA_SCORE_MIN = 5.0     # |Δ score| mínimo entre as duas últimas leituras
_RSI_SOBREVENDIDO = 30.0
_RSI_SOBRECOMPRADO = 70.0
_VAR_1D_FORTE = 5.0        # % de variação no dia que já é "tranco" (var_1d é percentual)
_PROX_MAX_52 = 0.98        # preço ≥ 98% da máxima de 52s → perto da máxima
_PROX_MIN_52 = 1.02        # preço ≤ 102% da mínima de 52s → perto da mínima
_MAX_POR_TICKER = 2        # evita um único ativo dominar a lista


def _num(v: Any) -> Optional[float]:
    """Converte para float ou None (tolera str, None, NaN)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _sinal_score(ticker: str, historico: list[dict]) -> Optional[dict]:
    """
    Δ entre as duas leituras mais recentes de health score (histórico asc).
    Sobe a severidade quando o score CRUZA faixas de decisão (50 e 40).
    """
    if not historico or len(historico) < 2:
        return None
    atual = _num(historico[-1].get("score"))
    ant = _num(historico[-2].get("score"))
    if atual is None or ant is None:
        return None
    delta = atual - ant
    if abs(delta) < _DELTA_SCORE_MIN:
        return None

    subiu = delta > 0
    sev = abs(delta) * 2.0
    # bônus por cruzar limiar de decisão (piora/melhora "de faixa")
    for limiar in (50.0, 40.0):
        if (ant >= limiar > atual) or (ant < limiar <= atual):
            sev += 8.0

    return {
        "tipo": "score",
        "ticker": ticker,
        "icone": "📈" if subiu else "📉",
        "titulo": f"{ticker} · score {int(round(ant))}→{int(round(atual))}",
        "detalhe": (
            f"{'subiu' if subiu else 'caiu'} {abs(delta):.0f} pts na última leitura"
        ),
        "tom": "bull" if subiu else "bear",
        "severidade": sev,
    }


def _sinal_tecnico(ticker: str, pc: dict) -> Optional[dict]:
    """
    Escolhe o sinal técnico MAIS severo do price_cache (um por ticker):
    RSI extremo, proximidade de extremo de 52s, ou tranco no dia.
    """
    preco = _num(pc.get("preco"))
    rsi = _num(pc.get("rsi_14"))
    var_1d = _num(pc.get("var_1d"))
    max_52 = _num(pc.get("max_52s"))
    min_52 = _num(pc.get("min_52s"))

    candidatos: list[dict] = []

    if rsi is not None:
        if rsi <= _RSI_SOBREVENDIDO:
            candidatos.append({
                "icone": "🟢", "tom": "bull",
                "titulo": f"{ticker} · sobrevendido",
                "detalhe": f"RSI {rsi:.0f} — pode indicar exagero de queda",
                "severidade": 18.0 + (_RSI_SOBREVENDIDO - rsi),
            })
        elif rsi >= _RSI_SOBRECOMPRADO:
            candidatos.append({
                "icone": "🔴", "tom": "amber",
                "titulo": f"{ticker} · sobrecomprado",
                "detalhe": f"RSI {rsi:.0f} — pode indicar exagero de alta",
                "severidade": 18.0 + (rsi - _RSI_SOBRECOMPRADO),
            })

    if preco is not None and max_52 and preco >= _PROX_MAX_52 * max_52:
        candidatos.append({
            "icone": "🔺", "tom": "bull",
            "titulo": f"{ticker} · perto da máxima 52s",
            "detalhe": f"a {(preco / max_52 - 1) * 100:+.1f}% da máxima de 52 semanas",
            "severidade": 12.0,
        })

    if preco is not None and min_52 and preco <= _PROX_MIN_52 * min_52:
        candidatos.append({
            "icone": "🔻", "tom": "bear",
            "titulo": f"{ticker} · perto da mínima 52s",
            "detalhe": f"a {(preco / min_52 - 1) * 100:+.1f}% da mínima de 52 semanas",
            "severidade": 14.0,
        })

    if var_1d is not None and abs(var_1d) >= _VAR_1D_FORTE:
        subiu = var_1d > 0
        candidatos.append({
            "icone": "⚡", "tom": "bull" if subiu else "bear",
            "titulo": f"{ticker} · {var_1d:+.1f}% no dia",
            "detalhe": f"movimento forte {'de alta' if subiu else 'de baixa'} na sessão",
            "severidade": abs(var_1d) * 1.2,
        })

    if not candidatos:
        return None
    melhor = max(candidatos, key=lambda c: c["severidade"])
    melhor.update(tipo="tecnico", ticker=ticker)
    return melhor


def _sinais_eventos(eventos: list[dict], hoje: date) -> list[dict]:
    """Eventos macro de HOJE ou AMANHÃ (calendário fixo COPOM/FOMC/CPI/IPCA...)."""
    out: list[dict] = []
    for ev in eventos or []:
        d = ev.get("data")
        if isinstance(d, datetime):
            d = d.date()
        if not isinstance(d, date):
            continue
        dias = (d - hoje).days
        if dias not in (0, 1):
            continue
        alto = str(ev.get("impacto", "")).lower() == "alto"
        quando = "hoje" if dias == 0 else "amanhã"
        base = 20.0 if dias == 0 else 13.0
        out.append({
            "tipo": "evento",
            "ticker": None,
            "icone": "🚨" if alto else "📅",
            "titulo": str(ev.get("evento", "evento")),
            "detalhe": f"{quando} · {str(ev.get('categoria', '')).lower()}".strip(" ·"),
            "tom": "amber" if alto else "info",
            "severidade": base + (6.0 if alto else 0.0),
        })
    return out


def coletar_atencao_hoje(
    watchlist: list[str],
    historico_por_ticker: dict[str, list[dict]],
    price_cache: dict[str, dict],
    eventos: Optional[list[dict]] = None,
    hoje: Optional[date] = None,
    *,
    limite: int = 8,
) -> list[dict]:
    """
    Monta a lista ranqueada de "atenção hoje".

    watchlist            : tickers a monitorar (como armazenados no banco).
    historico_por_ticker : {ticker: [{score, calculado_em}, ...]} em ordem ASC.
    price_cache          : {ticker: {preco, var_1d, rsi_14, max_52s, min_52s, ...}}.
    eventos              : [{data: date, evento, categoria, impacto}] (macro fixo).
    hoje                 : data de referência (default: date.today()).
    limite               : máximo de itens no resultado.

    Retorna itens ordenados por severidade desc; no máximo `_MAX_POR_TICKER`
    itens por ticker. Lista vazia = "mercado calmo".
    """
    hoje = hoje or date.today()
    itens: list[dict] = []

    for ticker in watchlist or []:
        s = _sinal_score(ticker, historico_por_ticker.get(ticker, []))
        if s:
            itens.append(s)
        pc = price_cache.get(ticker)
        if pc:
            t = _sinal_tecnico(ticker, pc)
            if t:
                itens.append(t)

    itens.extend(_sinais_eventos(eventos or [], hoje))

    # ranqueia por severidade; limita itens por ticker para não concentrar
    itens.sort(key=lambda i: i["severidade"], reverse=True)
    por_ticker: dict[str, int] = {}
    resultado: list[dict] = []
    for it in itens:
        tk = it.get("ticker")
        if tk is not None:
            if por_ticker.get(tk, 0) >= _MAX_POR_TICKER:
                continue
            por_ticker[tk] = por_ticker.get(tk, 0) + 1
        resultado.append(it)
        if len(resultado) >= limite:
            break
    return resultado
