"""
utils/portfolio_sizing.py
=========================
Fronteira 2 — do score ao TAMANHO, e exposição macro do book inteiro.

Fecha o elo análise→decisão: o terminal deixa de só dizer "isto é bom" (score)
e passa a dizer "quanto disto comprar, dado o que você já tem" (peso-alvo) e
"o seu book está alinhado ou brigando com o macro" (exposição agregada).

Duas funções públicas (puras — testáveis, sem rede):
  sugerir_sizing(...)        → peso-alvo por ativo + ação (aumentar/reduzir/manter)
  exposicao_macro_book(...)  → tilt macro-setorial agregado da carteira

Metodologia do sizing (risk parity tiltado — padrão de mesa):
  base_i   = 1 / vol_i                      (inverse-vol: paridade de risco)
  edge_i   = f(health_score_i)              (alfa: qualidade do ativo)
  macro_i  = g(pilar_macro_setorial_i)      (regime + inflação setorial)
  raw_i    = base_i · edge_i · macro_i
  alvo_i   = raw_i / Σ raw · 100            (normalizado, com teto por posição)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)


def _market_do_ticker(ticker: str) -> str:
    return "BR" if str(ticker).upper().endswith(".SA") else "US"


def _edge_mult(health_score: float | None) -> float:
    """Health → multiplicador de alfa. 50 = neutro (1.0); clamp [0.3, 1.8]."""
    if health_score is None:
        return 1.0
    try:
        return float(max(0.3, min(1.8, float(health_score) / 50.0)))
    except (TypeError, ValueError):
        return 1.0


def _macro_mult(pontos: int) -> float:
    """Pilar macro-setorial (±8) → multiplicador de regime. clamp [0.5, 1.5]."""
    return float(max(0.5, min(1.5, 1.0 + pontos * 0.06)))


def vol_anual_por_ticker(precos: pd.DataFrame) -> dict[str, float]:
    """Volatilidade anualizada (decimal) por coluna de preços de fechamento."""
    out: dict[str, float] = {}
    if precos is None or not isinstance(precos, pd.DataFrame) or precos.empty:
        return out
    rets = precos.pct_change().dropna(how="all")
    for col in rets.columns:
        s = rets[col].dropna()
        if len(s) >= 30:
            v = float(s.std() * np.sqrt(252))
            if v > 0:
                out[str(col)] = round(v, 4)
    return out


def sugerir_sizing(
    pesos_atuais: dict[str, float],
    precos: pd.DataFrame,
    health_map: dict[str, float],
    setor_map: dict[str, str],
    macro_context: dict,
    max_peso: float = 20.0,
    limiar_acao_pp: float = 1.5,
) -> list[dict]:
    """
    Sugere peso-alvo por ativo (risk parity tiltado por edge e macro).

    Args:
      pesos_atuais: {ticker: peso 0..1 ou 0..100}  (auto-detecta escala)
      precos:       DataFrame Close (colunas = tickers) para vol por ativo
      health_map:   {ticker: health_score}
      setor_map:    {ticker: setor (EN ou PT)}
      macro_context: contexto macro (selic/vix/ipca_12m/treasury_10y)
      max_peso:     teto por posição (%) — aplicado e renormalizado
      limiar_acao_pp: banda morta (pp) para classificar como "manter"

    Retorna lista de dicts ordenada por peso-alvo desc.
    """
    if not pesos_atuais:
        return []

    # normaliza escala dos pesos para 0..1
    _soma = sum(v for v in pesos_atuais.values() if v) or 1.0
    escala = 100.0 if _soma > 1.5 else 1.0
    pesos = {t: (float(w) / escala) for t, w in pesos_atuais.items() if w}
    _tot = sum(pesos.values()) or 1.0
    pesos = {t: w / _tot for t, w in pesos.items()}

    vols = vol_anual_por_ticker(precos)
    _vol_mediana = float(np.median(list(vols.values()))) if vols else 0.30

    try:
        from utils.inflation_sectoral import pilar_macro_setorial
    except Exception:
        pilar_macro_setorial = None

    linhas = []
    for t, w_atual in pesos.items():
        vol = vols.get(t) or _vol_mediana or 0.30
        if vol <= 0:
            vol = _vol_mediana or 0.30
        hs = health_map.get(t)
        setor = setor_map.get(t, "")
        macro_pts = 0
        if pilar_macro_setorial is not None:
            try:
                macro_pts = int(pilar_macro_setorial(
                    setor, _market_do_ticker(t), macro_context
                ).get("pontos", 0))
            except Exception as e:
                logger.debug(f"[sizing] pilar macro '{t}' falhou: {e}")

        base = 1.0 / vol
        raw = base * _edge_mult(hs) * _macro_mult(macro_pts)
        linhas.append({
            "ticker": t, "peso_atual": round(w_atual * 100, 2),
            "vol": round(vol * 100, 1), "health": hs,
            "macro_pts": macro_pts, "_raw": raw,
        })

    # normaliza peso-alvo
    soma_raw = sum(l["_raw"] for l in linhas) or 1.0
    for l in linhas:
        l["peso_alvo"] = l["_raw"] / soma_raw * 100

    # aplica teto por posição e renormaliza o excedente entre os demais.
    # Só faz sentido se o teto for factível (n · teto > 100); com poucas
    # posições o teto é ignorado (não dá para todos respeitarem e somar 100).
    if max_peso and max_peso > 0 and len(linhas) * max_peso > 100 + 1e-6:
        for _ in range(5):
            excedentes = [l for l in linhas if l["peso_alvo"] > max_peso]
            if not excedentes:
                break
            sobra = sum(l["peso_alvo"] - max_peso for l in excedentes)
            for l in excedentes:
                l["peso_alvo"] = max_peso
            livres = [l for l in linhas if l["peso_alvo"] < max_peso - 1e-6]
            base_livre = sum(l["peso_alvo"] for l in livres) or 1.0
            for l in livres:
                l["peso_alvo"] += sobra * (l["peso_alvo"] / base_livre)

    for l in linhas:
        l["peso_alvo"] = round(l["peso_alvo"], 2)
        l["delta_pp"] = round(l["peso_alvo"] - l["peso_atual"], 2)
        if abs(l["delta_pp"]) < limiar_acao_pp:
            l["acao"] = "manter"
        elif l["delta_pp"] > 0:
            l["acao"] = "aumentar"
        else:
            l["acao"] = "reduzir"
        l.pop("_raw", None)

    return sorted(linhas, key=lambda x: x["peso_alvo"], reverse=True)


def exposicao_macro_book(
    pesos_atuais: dict[str, float],
    setor_map: dict[str, str],
    macro_context: dict,
) -> dict:
    """
    Agrega o tilt macro-setorial de cada posição × peso → exposição do book.

    Retorna {tilt_medio, regime_medio, inflacao_medio, pct_favoravel,
    pct_neutro, pct_desfavoravel, duration_exposta_pct, inflacao_protegida_pct,
    leitura, por_ativo}.
    """
    if not pesos_atuais:
        return {}

    _soma = sum(v for v in pesos_atuais.values() if v) or 1.0
    escala = 100.0 if _soma > 1.5 else 1.0
    pesos = {t: (float(w) / escala) for t, w in pesos_atuais.items() if w}
    _tot = sum(pesos.values()) or 1.0
    pesos = {t: w / _tot for t, w in pesos.items()}

    try:
        from utils.inflation_sectoral import pilar_macro_setorial
    except Exception:
        return {}

    tilt_medio = regime_medio = inflacao_medio = 0.0
    pct_fav = pct_neu = pct_des = 0.0
    dur_exp = infl_prot = 0.0
    por_ativo = []

    for t, w in pesos.items():
        setor = setor_map.get(t, "")
        try:
            p = pilar_macro_setorial(setor, _market_do_ticker(t), macro_context)
        except Exception:
            p = {"pontos": 0, "pts_regime": 0, "pts_inflacao": 0, "impacto": "neutro", "setor_canon": ""}
        pts = int(p.get("pontos", 0))
        pr = int(p.get("pts_regime", 0))
        pi = int(p.get("pts_inflacao", 0))
        tilt_medio    += w * pts
        regime_medio  += w * pr
        inflacao_medio += w * pi
        if pts > 0:
            pct_fav += w
        elif pts < 0:
            pct_des += w
        else:
            pct_neu += w
        if pr < 0:                 # setor pressionado por juro = exposto a duration
            dur_exp += w
        if pi > 0:                 # receita indexada = proteção inflacionária
            infl_prot += w
        por_ativo.append({
            "ticker": t, "peso": round(w * 100, 1),
            "setor": p.get("setor_canon", ""), "tilt": pts,
            "impacto": p.get("impacto", "neutro"),
        })

    if tilt_medio <= -2:
        leitura = ("⚠️ o book está BRIGANDO com o macro — concentração em setores "
                   "pressionados pelo regime/inflação atuais.")
    elif tilt_medio >= 2:
        leitura = ("✅ o book está ALINHADO ao macro — exposição predominante a "
                   "setores favorecidos pelo regime/inflação atuais.")
    else:
        leitura = "➖ exposição macro do book equilibrada (sem viés setorial forte)."

    return {
        "tilt_medio":           round(tilt_medio, 2),
        "regime_medio":         round(regime_medio, 2),
        "inflacao_medio":       round(inflacao_medio, 2),
        "pct_favoravel":        round(pct_fav * 100, 1),
        "pct_neutro":           round(pct_neu * 100, 1),
        "pct_desfavoravel":     round(pct_des * 100, 1),
        "duration_exposta_pct": round(dur_exp * 100, 1),
        "inflacao_protegida_pct": round(infl_prot * 100, 1),
        "leitura":              leitura,
        "por_ativo":            sorted(por_ativo, key=lambda x: x["tilt"]),
    }
