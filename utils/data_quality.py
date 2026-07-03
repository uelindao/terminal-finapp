"""
utils/data_quality.py
=====================
Cobertura de dados fundamentalistas por mercado — mede quantos % dos campos
críticos estão preenchidos no `fundamentals_cache`, para o painel de qualidade
(P2-2). Função PURA e sem I/O: recebe o dict de cache e devolve o resumo.

Objetivo do usuário: enxergar em segundos "quais tickers estão sem P/L, P/VP,
etc. e por quê" — e medir o ganho do derivador de múltiplos (P2-1).
"""
from __future__ import annotations

# Campos críticos avaliados (mesma base do health_engine/scrapers).
CAMPOS_CRITICOS = ["p/l", "p/vp", "roe%", "dy%", "margem%", "ev/ebitda"]

# Campos que NÃO se aplicam a certos mercados (não contam como "faltando"):
#  - FII: p/l, margem%, ev/ebitda não fazem sentido (fundo, não empresa).
#  - Banco: ev/ebitda não é convencional (tratado como n/a no derivador).
_NA_FII = {"p/l", "margem%", "ev/ebitda"}


def _mercado(ticker: str) -> str:
    """Classifica o ticker em 'FII' | 'BR' | 'US' (mesma regra do motor)."""
    try:
        from utils.health_engine import _is_fii
        if _is_fii(ticker):
            return "FII"
    except Exception:
        if ticker.endswith("11.SA"):
            return "FII"
    return "BR" if ticker.endswith(".SA") else "US"


def _campos_aplicaveis(mercado: str) -> list[str]:
    if mercado == "FII":
        return [c for c in CAMPOS_CRITICOS if c not in _NA_FII]
    return CAMPOS_CRITICOS


def calcular_cobertura(fund_cache: dict, top_piores: int = 20) -> dict:
    """
    Recebe {ticker: dados_dict} e devolve:
      {
        'total': N,
        'por_mercado': {mkt: {'n': N, 'campos': {campo: pct}, 'cobertura_media': pct}},
        'piores': [{'ticker','mercado','faltando':[...],'n_faltando','fonte','quality'}...],
      }
    Ignora campos não aplicáveis ao mercado (ex.: p/l de FII) no cálculo.
    """
    por_mkt: dict[str, dict] = {}
    piores: list[dict] = []

    for ticker, dados in (fund_cache or {}).items():
        dados = dados or {}
        mkt = _mercado(ticker)
        aplic = _campos_aplicaveis(mkt)
        bucket = por_mkt.setdefault(
            mkt, {"n": 0, "preenchidos": {c: 0 for c in CAMPOS_CRITICOS}}
        )
        bucket["n"] += 1

        faltando = []
        for campo in aplic:
            if dados.get(campo) is not None:
                bucket["preenchidos"][campo] += 1
            else:
                faltando.append(campo)

        if faltando:
            piores.append({
                "ticker": ticker,
                "mercado": mkt,
                "faltando": faltando,
                "n_faltando": len(faltando),
                "fonte": dados.get("data_source") or dados.get("_fonte") or "—",
                "quality": dados.get("data_quality_pct") or dados.get("qualidade_dados"),
            })

    # Consolida percentuais por mercado
    por_mercado = {}
    for mkt, b in por_mkt.items():
        n = b["n"] or 1
        aplic = _campos_aplicaveis(mkt)
        campos_pct = {
            c: round(100.0 * b["preenchidos"][c] / n, 1)
            for c in aplic
        }
        cobertura_media = round(sum(campos_pct.values()) / len(campos_pct), 1) if campos_pct else 0.0
        por_mercado[mkt] = {
            "n": b["n"],
            "campos": campos_pct,
            "cobertura_media": cobertura_media,
        }

    # Piores: mais campos faltando primeiro; empate → menor quality
    piores.sort(key=lambda x: (-x["n_faltando"], (x["quality"] if x["quality"] is not None else 0)))

    return {
        "total": sum(b["n"] for b in por_mkt.values()),
        "por_mercado": por_mercado,
        "piores": piores[:top_piores],
    }
