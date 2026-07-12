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


@st.cache_data(ttl=3600, show_spinner=False)
def estatistica_divergencias_br(anos: int = 8, min_persist: int = 2) -> dict:
    """
    Estatística do backtest por quadrante. PREFERE a versão PERSISTIDA no Supabase
    (rápida/robusta — popular com `python scripts/backtest_divergencias.py --save`);
    só cai no compute LIVE (lento/flaky na Cloud) se não houver persistida.
    """
    # 1) persistida (rápido)
    try:
        import json
        from database.db import get_ai_analysis
        row = get_ai_analysis(tipo="backtest_div_v1", ticker=None,
                              user_id=None, modo=None)
        if row and row.get("conteudo"):
            return json.loads(row["conteudo"])
    except Exception:
        pass
    # 2) fallback: compute live
    try:
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


def divergencias_b_br(macro_context: dict) -> list[dict]:
    """
    Divergências B setoriais ATUAIS (BR), enriquecidas p/ o "atenção hoje" (M2-4):
    setor, label, flag `novo` (entrou em B desde o último snapshot diário), e a
    estatística do quadrante (fwd RS/hit/n). Persiste um snapshot diário em
    ai_analyses (divergencia_snap) — write-on-read, 1x/dia — p/ detectar transições.
    NÃO cacheado (efeito colateral + comparação); as fontes internas já são cacheadas.
    """
    import json
    from datetime import date
    from utils.setores import LABEL_SETOR
    from utils.divergencia_setorial import DIVERG_B

    matriz = divergencias_atuais_br(macro_context)
    b_hoje = [it for it in matriz if it.get("quadrante") == DIVERG_B]
    if not b_hoje and not matriz:
        return []
    setores_b = {it["setor"] for it in b_hoje}
    hoje = date.today().isoformat()

    # snapshot diário (freshness): reusa ai_analyses como KV
    novas: set = set()
    try:
        from database.db import get_ai_analysis, save_ai_analysis
        prev = get_ai_analysis(tipo="divergencia_snap", ticker=None, user_id=None, modo=None)
        prev_json = json.loads(prev["conteudo"]) if (prev and prev.get("conteudo")) else {}
        if prev_json.get("data") == hoje:
            novas = set(prev_json.get("b_novas", []))
        else:
            prev_b = {s for s, q in (prev_json.get("estado") or {}).items() if q == DIVERG_B}
            novas = setores_b - prev_b
            estado = {it["setor"]: it["quadrante"] for it in matriz}
            save_ai_analysis(
                tipo="divergencia_snap",
                conteudo=json.dumps({"data": hoje, "estado": estado,
                                     "b_novas": sorted(novas)}),
                ticker=None, user_id=None, modelo="snap", ttl_horas=24 * 40,
            )
    except Exception:
        pass

    _st = stat_para_quadrante(estatistica_divergencias_br(), DIVERG_B, 13) or {}
    out = []
    for it in b_hoje:
        out.append({
            "setor": it["setor"],
            "setor_label": LABEL_SETOR.get(it["setor"], it["setor"]),
            "quadrante": DIVERG_B,
            "novo": it["setor"] in novas,
            "hist_media": _st.get("media"),
            "hist_hit": _st.get("hit_rate"),
            "hist_n": _st.get("n"),
        })
    return out


def stat_para_quadrante(estatistica: dict, quadrante: str, horizonte: int = 13) -> dict | None:
    """Extrai {n, media, mediana, hit_rate} do resultado do backtest p/ um
    quadrante/horizonte, ou None. Tolera chave de horizonte int OU str (o JSON
    persistido serializa os horizontes como string)."""
    try:
        _hs = (estatistica or {}).get("estatistica", {}).get(quadrante, {})
        return _hs.get(horizonte) or _hs.get(str(horizonte))
    except Exception:
        return None
