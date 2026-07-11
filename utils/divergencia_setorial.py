"""
utils/divergencia_setorial.py — matriz de divergência macro × setor (PLANO_MACRO M2-1/M2-2).

Confronta o "deveria ser" (tilt de regime, de tilt_setor/reconstrução) com o "é"
(RS setorial realizado, de setor_series). Divergência entre os dois é informação
de primeira ordem:

  tilt \\ RS │ RS forte (+)      │ RS neutro   │ RS fraco (−)
  ──────────┼───────────────────┼─────────────┼──────────────────
  favorecido│ confirmação bull  │ catch-up?   │ DIVERGÊNCIA A
  penalizado│ DIVERGÊNCIA B     │ (—)         │ confirmação bear

  • DIVERGÊNCIA A (favorecido & fraco): macro diz sim, preço diz não — ou o setor
    está barato p/ o regime (candidato a reversão) ou o mercado antecipa
    deterioração que o indicador não captou. Checar micro antes de comprar a tese.
  • DIVERGÊNCIA B (penalizado & forte): preço desafia o macro — mercado pode estar
    antecipando virada de regime (o quadrante que historicamente precede mudanças
    de fase; validar no backtest M3).

Função PURA (dicts injetados). Nada aqui prevê o futuro — a leitura é a hipótese;
o RESULTADO PRÁTICO vem do backtest (M3), que preenche a estatística na UI.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

# quadrantes
CONFIRMA_BULL = "confirmacao_bull"
CONFIRMA_BEAR = "confirmacao_bear"
DIVERG_A = "divergencia_a"      # favorecido & fraco
DIVERG_B = "divergencia_b"      # penalizado & forte
CATCH_UP = "catch_up"           # favorecido & rs neutro
NEUTRO = "neutro"

_DIVERGENCIAS = (DIVERG_A, DIVERG_B)

_LEITURA = {
    CONFIRMA_BULL: "macro e preço alinhados a favor — tendência com suporte do regime.",
    CONFIRMA_BEAR: "macro e preço alinhados contra — fraqueza coerente com o regime.",
    DIVERG_A: ("macro favorece mas o preço ainda não reagiu: ou desconto/catch-up, "
               "ou o mercado antecipa deterioração — checar micro antes de comprar."),
    DIVERG_B: ("preço forte contra o macro: o mercado pode estar antecipando uma "
               "virada de regime — validar com atividade e amplitude."),
    CATCH_UP: "macro favorece e o preço ainda é morno — vigiar por início de catch-up.",
    NEUTRO: "sem sinal claro (tilt neutro).",
}

_TILT_ESCALA = 4.0     # tilt vai de −4 a +4
_RS_ESCALA = 0.10      # 10% de RS na janela ≈ movimento "forte"


def classificar_quadrante(tilt, rs, *, limiar_tilt: int = 1,
                          limiar_rs: float = 0.02) -> str:
    """Classifica um setor no quadrante a partir do tilt (±pts) e do RS (fração)."""
    if tilt is None or rs is None:
        return NEUTRO
    try:
        tilt = float(tilt); rs = float(rs)
    except (TypeError, ValueError):
        return NEUTRO
    if tilt != tilt or rs != rs:      # NaN
        return NEUTRO

    favorecido = tilt >= limiar_tilt
    penalizado = tilt <= -limiar_tilt
    rs_forte = rs >= limiar_rs
    rs_fraco = rs <= -limiar_rs

    if favorecido:
        if rs_forte:
            return CONFIRMA_BULL
        if rs_fraco:
            return DIVERG_A
        return CATCH_UP
    if penalizado:
        if rs_fraco:
            return CONFIRMA_BEAR
        if rs_forte:
            return DIVERG_B
        return NEUTRO
    return NEUTRO


def _magnitude(tilt: float, rs: float) -> float:
    """Distância entre o tilt normalizado e o RS normalizado (0..2). Grande =
    macro e preço discordam com intensidade."""
    tn = max(-1.0, min(1.0, tilt / _TILT_ESCALA))
    rn = max(-1.0, min(1.0, rs / _RS_ESCALA))
    return round(abs(tn - rn), 4)


def matriz_divergencia(
    tilts: dict,
    rs: dict,
    *,
    limiar_tilt: int = 1,
    limiar_rs: float = 0.02,
    apenas_divergencias: bool = False,
) -> list[dict]:
    """
    tilts : {setor: tilt_pts}  (± inteiro).
    rs    : {setor: rs_valor}  (fração; ex. rs_setorial_atual()).
    Retorna itens {setor, quadrante, tilt, rs, magnitude, leitura, is_divergencia}
    ordenados por magnitude desc. Só setores presentes em AMBOS os dicts.
    """
    itens = []
    for setor in (set(tilts or {}) & set(rs or {})):
        _t, _r = tilts.get(setor), rs.get(setor)
        q = classificar_quadrante(_t, _r, limiar_tilt=limiar_tilt, limiar_rs=limiar_rs)
        if apenas_divergencias and q not in _DIVERGENCIAS:
            continue
        try:
            mag = _magnitude(float(_t), float(_r))
        except (TypeError, ValueError):
            mag = 0.0
        itens.append({
            "setor": setor,
            "quadrante": q,
            "tilt": _t,
            "rs": _r,
            "magnitude": mag,
            "leitura": _LEITURA.get(q, ""),
            "is_divergencia": q in _DIVERGENCIAS,
        })
    itens.sort(key=lambda x: x["magnitude"], reverse=True)
    return itens


def dias_em_quadrante(historico: "pd.Series") -> int:
    """
    Nº de observações consecutivas (a partir da mais recente) no MESMO quadrante —
    mede persistência do sinal (≥2 semanas ≠ ruído de 1 dia). `historico` é uma
    Series de rótulos de quadrante ordenada por data crescente.
    """
    if historico is None or len(historico) == 0:
        return 0
    vals = list(historico.dropna())
    if not vals:
        return 0
    atual = vals[-1]
    n = 0
    for v in reversed(vals):
        if v == atual:
            n += 1
        else:
            break
    return n
