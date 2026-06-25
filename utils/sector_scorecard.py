"""
utils/sector_scorecard.py
=========================
Scorecard de rotação setorial — a tabela que um gestor abre primeiro.

Cruza os TRÊS ângulos que antes viviam isolados no terminal:
  • FUNDAMENTO  — health score médio do setor (motor quantitativo)
  • TÉCNICO     — força relativa (momentum 12m do setor vs universo), do price_cache
  • MACRO       — vento de regime + inflação setorial (utils/inflation_sectoral)

Saída: ranking de setores por nota composta, com sub-notas e veredicto.
Tudo a partir de dados JÁ cacheados (health_scores, fundamentals, price_cache) —
zero chamadas de rede, no mesmo espírito do heatmap da Discovery.
"""
from __future__ import annotations

from utils.st_fallback import st, ST_AVAILABLE as _ST

from utils.logger import get_logger
from utils.setores import normalizar_setor, LABEL_SETOR as _LABEL_SETOR

logger = get_logger(__name__)

# Pesos da nota composta.
_W_FUND, _W_TEC, _W_MAC = 0.45, 0.25, 0.30


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _macro_para_0_100(pontos: int) -> float:
    """Mapeia o pilar macro-setorial (±8) para escala 0-100 (50 = neutro)."""
    return _clamp(50 + pontos * 6.25, 0, 100)


def _composto(fund: float, tec: float, mac: float) -> float:
    return round(_W_FUND * fund + _W_TEC * tec + _W_MAC * mac, 1)


def _veredicto(composto: float, mac_pontos: int) -> tuple[str, str]:
    """Veredicto + cor a partir da nota composta e do vento macro."""
    if composto >= 62:
        return "overweight", "#00C853"
    if composto >= 48:
        return "neutro", "#FF9900"
    return "underweight", "#FF1744"


@st.cache_data(ttl=1800, show_spinner=False)
def calcular_scorecard_setorial(universo: str = "BR") -> list[dict]:
    """
    Monta o scorecard de rotação setorial para 'BR' ou 'US'.

    Retorna lista de dicts (ordenada por nota composta desc), cada um com:
      setor, label, n_ativos, fundamento, tecnico, macro, macro_pontos,
      composto, veredicto, cor, tickers (amostra).
    """
    from database.db import (
        get_health_scores, get_todos_fundamentos_cache, get_all_price_cache,
    )

    is_br = str(universo).upper() == "BR"
    market = "BR" if is_br else "US"

    hs_map = {h["ticker"]: h.get("score") for h in (get_health_scores() or [])}
    fund_all = get_todos_fundamentos_cache() or {}
    price_all = get_all_price_cache() or {}

    macro_context = st.session_state.get("macro_context", {}) or {}

    # ── agrupa por setor canônico ─────────────────────────────────────────────
    grupos: dict[str, dict] = {}
    for ticker, dados in fund_all.items():
        if is_br and not ticker.endswith(".SA"):
            continue
        if not is_br and ticker.endswith(".SA"):
            continue
        setor_raw = (dados or {}).get("setor")
        canon = normalizar_setor(setor_raw)
        if not canon or canon not in _LABEL_SETOR:
            continue
        score = hs_map.get(ticker)
        if score is None:
            continue
        g = grupos.setdefault(canon, {"scores": [], "mom12": [], "tickers": []})
        g["scores"].append(float(score))
        g["tickers"].append(ticker)
        pc = price_all.get(ticker) or {}
        _v12 = pc.get("var_12m")
        if _v12 is not None:
            try:
                g["mom12"].append(float(_v12))
            except (TypeError, ValueError):
                pass

    if not grupos:
        return []

    # momentum médio por setor + média do universo (para força relativa)
    mom_setor = {
        c: (sum(g["mom12"]) / len(g["mom12"]) if g["mom12"] else None)
        for c, g in grupos.items()
    }
    moms = [m for m in mom_setor.values() if m is not None]
    mom_min, mom_max = (min(moms), max(moms)) if moms else (0.0, 0.0)
    banda = (mom_max - mom_min) or 1.0

    resultado = []
    for canon, g in grupos.items():
        fundamento = round(sum(g["scores"]) / len(g["scores"]), 1)

        # técnico: força relativa = momentum do setor normalizado 0-100 (cross-section)
        m = mom_setor.get(canon)
        tecnico = round(_clamp((m - mom_min) / banda * 100, 0, 100), 1) if m is not None else 50.0

        # macro: pilar regime + inflação setorial
        mac_pontos = 0
        try:
            from utils.inflation_sectoral import pilar_macro_setorial
            mac_pontos = int(pilar_macro_setorial(canon, market, macro_context).get("pontos", 0))
        except Exception as e:
            logger.debug(f"[scorecard] macro setor '{canon}' falhou: {e}")
        macro = round(_macro_para_0_100(mac_pontos), 1)

        composto = _composto(fundamento, tecnico, macro)
        veredicto, cor = _veredicto(composto, mac_pontos)

        resultado.append({
            "setor":        canon,
            "label":        _LABEL_SETOR.get(canon, canon),
            "n_ativos":     len(g["scores"]),
            "fundamento":   fundamento,
            "tecnico":      tecnico,
            "momentum_12m": round(m, 1) if m is not None else None,
            "macro":        macro,
            "macro_pontos": mac_pontos,
            "composto":     composto,
            "veredicto":    veredicto,
            "cor":          cor,
            "tickers":      [t.replace(".SA", "") for t in g["tickers"][:6]],
        })

    return sorted(resultado, key=lambda x: x["composto"], reverse=True)
