"""
utils/divergencia_live.py — divergências para a UI (PLANO_MACRO M2-3/M3-2).

REGRA DE OURO (aprendida na marra): a UI NUNCA lê o price_history.

A versão anterior computava RS/breadth ao vivo, puxando ~470 tickers × 400 dias
(~11 MB) por chamada, com cache de 1h que reseta a cada restart do Streamlit —
isso estourou a cota de EGRESS do Supabase e derrubou o projeto inteiro.

Agora: o job semanal (scripts/backtest_divergencias.py --save) persiste dois JSONs
minúsculos (~2 KB) — `divergencia_rs_v1` (RS por setor + breadth) e
`backtest_div_v1` (estatística por quadrante). A UI só LÊ isso.

O TILT continua fresco: é função pura (tilt_setor), custo zero, calculado aqui a
partir do macro_context da sessão. Ou seja, o lado macro reage a mudanças de
Selic/VIX na hora; o lado preço (RS) é semanal — que é a cadência real dele.
"""
from __future__ import annotations

import json

import streamlit as st


@st.cache_data(ttl=3600, show_spinner=False)
def _snapshot_rs() -> dict:
    """Lê o snapshot de RS/breadth persistido pelo job semanal. {} se ausente."""
    try:
        from database.db import get_ai_analysis
        row = get_ai_analysis(tipo="divergencia_rs_v1", ticker=None,
                              user_id=None, modo=None)
        if row and row.get("conteudo"):
            return json.loads(row["conteudo"]) or {}
    except Exception:
        pass
    return {}


@st.cache_data(ttl=3600, show_spinner=False)
def estatistica_divergencias_br() -> dict:
    """
    Estatística do backtest por quadrante (persistida pelo job semanal).
    {} se ainda não houver — a UI então omite a coluna de histórico.
    Sem fallback de compute ao vivo: recalcular custaria ~59 MB de egress.
    """
    try:
        from database.db import get_ai_analysis
        row = get_ai_analysis(tipo="backtest_div_v1", ticker=None,
                              user_id=None, modo=None)
        if row and row.get("conteudo"):
            return json.loads(row["conteudo"]) or {}
    except Exception:
        pass
    return {}


def divergencias_atuais_br(macro_context: dict) -> list[dict]:
    """
    Matriz de divergência atual (BR): RS do snapshot (semanal, barato) × tilt
    calculado AGORA (função pura, custo zero) a partir do macro_context.
    Lista vazia se não há snapshot (rodar o job semanal).
    """
    snap = _snapshot_rs()
    rs = snap.get("rs") or {}
    if not rs:
        return []
    from utils.macro_state import tilt_setor
    from utils.regime_historico import SETORES_TILT
    from utils.divergencia_setorial import matriz_divergencia

    tilts = {}
    for s in SETORES_TILT:
        try:
            tilts[s] = int((tilt_setor(s, macro_context or {}, "BR") or {}).get("pontos", 0) or 0)
        except Exception:
            pass
    return matriz_divergencia(tilts, rs)


def breadth_atual_br() -> float | None:
    """Amplitude interna (% de setores acima da própria MM ~10 semanas), do snapshot."""
    v = _snapshot_rs().get("breadth")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def data_snapshot_br() -> str:
    """Data em que o snapshot foi gerado (p/ a UI mostrar a defasagem). '' se ausente."""
    return str(_snapshot_rs().get("data") or "")


def divergencias_b_br(macro_context: dict) -> list[dict]:
    """
    Divergências B setoriais ATUAIS (BR) p/ o "atenção hoje" (M2-4): setor, label,
    flag `novo` (entrou em B desde o último snapshot diário de estado) e a
    estatística do quadrante. Custo: só leitura de JSONs pequenos.
    """
    from datetime import date
    from utils.setores import LABEL_SETOR
    from utils.divergencia_setorial import DIVERG_B

    matriz = divergencias_atuais_br(macro_context)
    if not matriz:
        return []
    b_hoje = [it for it in matriz if it.get("quadrante") == DIVERG_B]
    setores_b = {it["setor"] for it in b_hoje}
    hoje = date.today().isoformat()

    # snapshot diário de ESTADO (só p/ detectar transições) — KV pequeno
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
    return [{
        "setor": it["setor"],
        "setor_label": LABEL_SETOR.get(it["setor"], it["setor"]),
        "quadrante": DIVERG_B,
        "novo": it["setor"] in novas,
        "hist_media": _st.get("media"),
        "hist_hit": _st.get("hit_rate"),
        "hist_n": _st.get("n"),
    } for it in b_hoje]


def stat_para_quadrante(estatistica: dict, quadrante: str, horizonte: int = 13) -> dict | None:
    """Extrai {n, media, mediana, hit_rate} do resultado do backtest p/ um
    quadrante/horizonte, ou None. Tolera chave de horizonte int OU str (o JSON
    persistido serializa os horizontes como string)."""
    try:
        _hs = (estatistica or {}).get("estatistica", {}).get(quadrante, {})
        return _hs.get(horizonte) or _hs.get(str(horizonte))
    except Exception:
        return None
