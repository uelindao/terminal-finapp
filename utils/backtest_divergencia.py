"""
utils/backtest_divergencia.py — resultado prático das divergências (PLANO_MACRO M3-1).

Junta o "deveria ser" no tempo (tilt reconstruído, M0-2) com o "é" no tempo (RS
setorial, M0-1), classifica cada setor-semana num quadrante (M2-1) e mede o que
cada quadrante RENDEU depois: forward RS em 4/13/26 semanas, agregado por
EPISÓDIO (sequência contígua no quadrante — não por semana, que infla n e
autocorrelaciona).

Núcleo PURO e testável. É o portão do plano: nenhum sinal sobe para a UI sem a
estatística que sai daqui. Se um quadrante não tiver edge, o número refutado
aparece do mesmo jeito.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from utils.divergencia_setorial import classificar_quadrante


def forward_ret(retornos: pd.DataFrame, janela: int) -> pd.DataFrame:
    """Retorno FORWARD acumulado de (t, t+janela] por coluna. Usa dados futuros —
    correto para backtest (roda offline). NaN diário tratado como 0 (sem move)."""
    if retornos is None or retornos.empty:
        return pd.DataFrame()
    cp = (1 + retornos.fillna(0.0)).cumprod()
    return cp.shift(-janela) / cp - 1.0


def forward_rs(retornos: pd.DataFrame, janela: int) -> pd.DataFrame:
    """Forward RS = retorno forward do setor − mediana transversal (por data).
    Positivo = o setor bateu o universo nas próximas `janela` observações."""
    fr = forward_ret(retornos, janela)
    if fr.empty:
        return fr
    return fr.sub(fr.median(axis=1), axis=0)


def matriz_quadrantes(
    tilt_hist: pd.DataFrame,
    rs_hist: pd.DataFrame,
    *,
    limiar_tilt: int = 1,
    limiar_rs: float = 0.02,
) -> pd.DataFrame:
    """
    tilt_hist : DataFrame index=data, colunas 'tilt_<setor>' (ou já '<setor>').
    rs_hist   : DataFrame index=data, colunas '<setor>' (RS trailing, M0-1).
    Retorna DataFrame index=data ∩, colunas=setores ∩, valores=rótulo de quadrante.
    """
    if tilt_hist is None or tilt_hist.empty or rs_hist is None or rs_hist.empty:
        return pd.DataFrame()
    tilt = tilt_hist.rename(columns=lambda c: c[5:] if str(c).startswith("tilt_") else c)
    setores = [c for c in tilt.columns if c in rs_hist.columns]
    datas = tilt.index.intersection(rs_hist.index)
    if not setores or len(datas) == 0:
        return pd.DataFrame()
    out = pd.DataFrame(index=datas, columns=setores, dtype=object)
    for s in setores:
        ts, rsx = tilt[s].reindex(datas), rs_hist[s].reindex(datas)
        out[s] = [
            classificar_quadrante(ts.iloc[i], rsx.iloc[i],
                                  limiar_tilt=limiar_tilt, limiar_rs=limiar_rs)
            for i in range(len(datas))
        ]
    return out


def extrair_episodios(quadrantes: pd.DataFrame) -> list[dict]:
    """
    Episódio = sequência contígua de um setor no MESMO quadrante. Retorna
    {setor, data (entrada), quadrante, comprimento}. Uma obs por episódio evita
    autocorrelação (o mesmo sinal contado N vezes).
    """
    eps: list[dict] = []
    if quadrantes is None or quadrantes.empty:
        return eps
    for s in quadrantes.columns:
        serie = quadrantes[s].dropna()
        prev, start, comp = None, None, 0
        for d, q in serie.items():
            if q != prev:
                if prev is not None:
                    eps.append({"setor": s, "data": start, "quadrante": prev,
                                "comprimento": comp})
                prev, start, comp = q, d, 1
            else:
                comp += 1
        if prev is not None:
            eps.append({"setor": s, "data": start, "quadrante": prev,
                        "comprimento": comp})
    return eps


def estatistica_por_quadrante(
    episodios: list[dict],
    fwd_rs_por_horizonte: dict,
    *,
    min_persistencia: int = 1,
) -> dict:
    """
    episodios            : saída de extrair_episodios.
    fwd_rs_por_horizonte : {horizonte: DataFrame forward_rs (data×setor)}.
    min_persistencia     : só episódios com comprimento >= N entram.

    Retorna {quadrante: {horizonte: {n, media, mediana, hit_rate}}}. hit_rate =
    fração de episódios com forward RS > 0.
    """
    agg: dict = {}
    for ep in episodios:
        if ep.get("comprimento", 1) < min_persistencia:
            continue
        q = ep["quadrante"]
        for h, fr in fwd_rs_por_horizonte.items():
            if fr is None or fr.empty or ep["setor"] not in fr.columns:
                continue
            if ep["data"] not in fr.index:
                continue
            val = fr.at[ep["data"], ep["setor"]]
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue
            agg.setdefault(q, {}).setdefault(h, []).append(float(val))

    out: dict = {}
    for q, hs in agg.items():
        out[q] = {}
        for h, vals in hs.items():
            arr = np.array(vals, dtype=float)
            out[q][h] = {
                "n": int(arr.size),
                "media": round(float(arr.mean()), 4),
                "mediana": round(float(np.median(arr)), 4),
                "hit_rate": round(float((arr > 0).mean()), 3),
            }
    return out


def rodar_backtest(
    retornos_setoriais: pd.DataFrame,
    tilt_hist: pd.DataFrame,
    *,
    janela_rs: int = 13,
    horizontes: tuple = (4, 13, 26),
    limiar_tilt: int = 1,
    limiar_rs: float = 0.02,
    min_persistencia: int = 1,
) -> dict:
    """
    Pipeline completo (para dados semanais alinhados): RS trailing → quadrantes →
    episódios → forward RS por horizonte → estatística. `retornos_setoriais` e
    `tilt_hist` devem estar na MESMA frequência/índice (semanal).
    """
    from utils.setor_series import rs_setorial
    rs_hist = rs_setorial(retornos_setoriais, janela_rs, min_cobertura=0.6)
    quad = matriz_quadrantes(tilt_hist, rs_hist,
                             limiar_tilt=limiar_tilt, limiar_rs=limiar_rs)
    eps = extrair_episodios(quad)
    fwd = {h: forward_rs(retornos_setoriais, h) for h in horizontes}
    stats = estatistica_por_quadrante(eps, fwd, min_persistencia=min_persistencia)
    return {"n_episodios": len(eps), "estatistica": stats,
            "horizontes": list(horizontes), "janela_rs": janela_rs}
