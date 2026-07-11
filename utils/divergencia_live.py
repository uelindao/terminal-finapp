"""
utils/divergencia_live.py — divergências ao vivo + estatística (PLANO_MACRO M2-3/M3-2).

Cola o motor de quadrantes (puro) às fontes de dados para a UI:
  • `divergencias_atuais_br` — matriz de divergência de HOJE (tilt atual × RS 3m).
  • `estatistica_divergencias_br` — backtest por episódio (cache diário) p/ a coluna
    "resultado histórico" da UI. Degrada em silêncio se as APIs macro falharem.

Ambas cacheadas: a UI nunca recomputa o pesado a cada rerun.
"""
from __future__ import annotations

import streamlit as st

_JANELA_RS = 63     # ~3 meses


@st.cache_data(ttl=3600, show_spinner=False)
def divergencias_atuais_br(_macro_context: dict) -> list[dict]:
    """Matriz de divergência atual (BR): tilt de regime de hoje × RS setorial 3m.
    `_macro_context` não é hasheado (underscore) — refresca no ttl de 1h."""
    from utils.setor_series import carregar_retornos_setoriais_br, rs_setorial_atual
    from utils.macro_state import tilt_setor
    from utils.regime_historico import SETORES_TILT
    from utils.divergencia_setorial import matriz_divergencia

    ret = carregar_retornos_setoriais_br(dias=400)
    if ret.empty:
        return []
    rs = rs_setorial_atual(ret, janela=_JANELA_RS)
    if not rs:
        return []
    tilts = {}
    for s in SETORES_TILT:
        try:
            tilts[s] = int((tilt_setor(s, _macro_context or {}, "BR") or {}).get("pontos", 0) or 0)
        except Exception:
            pass
    return matriz_divergencia(tilts, rs)


@st.cache_data(ttl=86400, show_spinner=False)
def estatistica_divergencias_br(anos: int = 8, min_persist: int = 2) -> dict:
    """Backtest por episódio (cache diário). {} se dados/APIs indisponíveis."""
    try:
        import pandas as pd
        from utils.setor_series import carregar_retornos_setoriais_br
        from utils.regime_historico import reconstruir_regime_tilt_br
        from utils.backtest_divergencia import rodar_backtest

        ret = carregar_retornos_setoriais_br(dias=int(anos * 260))
        if ret.empty:
            return {}
        ret_sem = (1 + ret.fillna(0.0)).resample("W-FRI").prod() - 1.0
        tilt = reconstruir_regime_tilt_br(anos=anos)
        if tilt.empty:
            return {}
        return rodar_backtest(ret_sem, tilt, janela_rs=13,
                              horizontes=(4, 13, 26), min_persistencia=min_persist)
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def breadth_atual_br(janela_semanas: int = 10) -> float | None:
    """Amplitude interna BR: % de setores acima da própria MM (~janela_semanas).
    None se sem dados."""
    from utils.setor_series import carregar_retornos_setoriais_br, breadth_setorial
    ret = carregar_retornos_setoriais_br(dias=260)
    if ret.empty:
        return None
    b = breadth_setorial(ret, janela_mm=int(janela_semanas * 5)).dropna()
    return float(b.iloc[-1]) if len(b) else None


def stat_para_quadrante(estatistica: dict, quadrante: str, horizonte: int = 13) -> dict | None:
    """Extrai {n, media, mediana, hit_rate} do resultado do backtest p/ um
    quadrante/horizonte, ou None se ausente."""
    try:
        return (estatistica or {}).get("estatistica", {}).get(quadrante, {}).get(horizonte)
    except Exception:
        return None
