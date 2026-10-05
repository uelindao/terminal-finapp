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


def forward_ret(retornos: pd.DataFrame, janela: int, *, min_cobertura: float = 1.0) -> pd.DataFrame:
    """Retorno de (t, t+janela], com cobertura explícita e sem inventar retorno zero.

    Por padrão, qualquer ausência no horizonte invalida a observação. A borda
    final sem todas as semanas futuras permanece ausente, mesmo com cobertura
    relaxada. É um resultado descritivo posterior, não um sinal conhecido em t.
    """
    if retornos is None or retornos.empty:
        return pd.DataFrame()
    if janela < 1 or not 0 < min_cobertura <= 1:
        raise ValueError("Janela positiva e cobertura em (0, 1] são obrigatórias.")
    r = retornos.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    r = r.where(r >= -1.0)
    futuro = r.shift(-1).iloc[::-1]
    min_obs = int(np.ceil(janela * min_cobertura))
    out = futuro.rolling(janela, min_periods=min_obs).apply(
        lambda x: np.nanprod(1.0 + x) - 1.0, raw=True
    ).iloc[::-1]
    horizonte_completo = pd.Series(np.arange(len(r)) + janela < len(r), index=r.index)
    return out.where(horizonte_completo, np.nan)


def forward_rs(retornos: pd.DataFrame, janela: int, *, min_cobertura: float = 1.0) -> pd.DataFrame:
    """Forward do setor menos mediana transversal, usando horizontes válidos."""
    fr = forward_ret(retornos, janela, min_cobertura=min_cobertura)
    if fr.empty:
        return fr
    return fr.sub(fr.median(axis=1), axis=0)


def retornos_semanais(retornos_diarios: pd.DataFrame, *, min_cobertura: float = 1.0) -> pd.DataFrame:
    """Agrega semanas sem zerar gaps de cobertura setorial.

    O denominador é o calendário de pregões presente no dataframe, não cinco
    dias fixos: feriados não contam como falhas. Semana sem preço válido fica
    ausente. O primeiro dia de toda a matriz (pct_change) não é um gap interno.
    """
    if retornos_diarios is None or retornos_diarios.empty:
        return pd.DataFrame()
    if not 0 < min_cobertura <= 1:
        raise ValueError("Cobertura deve estar em (0, 1].")
    r = retornos_diarios.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    r = r.where(r >= -1.0)
    r = r.sort_index()
    if len(r) and r.iloc[0].isna().all():
        r = r.iloc[1:]
    if r.empty:
        return pd.DataFrame()
    esperado = pd.Series(1, index=r.index).resample("W-FRI").sum()
    valido = r.resample("W-FRI").count()
    acumulado = (1 + r).resample("W-FRI").prod(min_count=1) - 1.0
    return acumulado.where(valido.ge(esperado * min_cobertura, axis=0) & valido.gt(0))


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
            if pd.notna(ts.iloc[i]) and pd.notna(rsx.iloc[i]) else None
            for i in range(len(datas))
        ]
    return out


def extrair_episodios(quadrantes: pd.DataFrame) -> list[dict]:
    """Sequências contíguas, incluindo suas datas; gaps interrompem o episódio.

    Contagem por episódio reduz repetição, mas não elimina dependência entre
    setores ou entre horizontes futuros sobrepostos.
    """
    eps: list[dict] = []
    if quadrantes is None or quadrantes.empty:
        return eps
    for setor in quadrantes.columns:
        anterior, datas, ultima_data = None, [], None
        for data, quadrante in quadrantes[setor].sort_index().items():
            q = None if pd.isna(quadrante) else quadrante
            lacuna = ultima_data is not None and isinstance(data, pd.Timestamp) and (data - ultima_data).days > 7
            if q != anterior or lacuna:
                if anterior is not None and datas:
                    eps.append({"setor": setor, "data": datas[0], "quadrante": anterior,
                                "comprimento": len(datas), "datas": list(datas)})
                anterior, datas = q, []
            if q is not None:
                datas.append(data)
            ultima_data = data
        if anterior is not None and datas:
            eps.append({"setor": setor, "data": datas[0], "quadrante": anterior,
                        "comprimento": len(datas), "datas": list(datas)})
    return eps


def data_confirmacao(ep: dict, indice: pd.Index, min_persistencia: int = 1):
    """A Nª observação conhecida confirma o sinal; nenhuma semana anterior entra.

    A duração posterior não influencia a elegibilidade. Suporta os episódios
    legados sem lista de datas, reconstruindo apenas o deslocamento no índice.
    """
    if min_persistencia < 1:
        raise ValueError("Persistência deve ser ao menos uma observação.")
    if ep.get("comprimento", 1) < min_persistencia:
        return None
    datas = ep.get("datas")
    if datas:
        return datas[min_persistencia - 1] if len(datas) >= min_persistencia else None
    if ep.get("data") not in indice:
        return None
    pos = indice.get_loc(ep["data"])
    if not isinstance(pos, (int, np.integer)) or pos + min_persistencia > len(indice):
        return None
    return indice[pos + min_persistencia - 1]


def estatistica_por_quadrante(
    episodios: list[dict],
    fwd_rs_por_horizonte: dict,
    *,
    min_persistencia: int = 1,
) -> dict:
    """
    episodios            : saída de extrair_episodios.
    fwd_rs_por_horizonte : {horizonte: DataFrame forward_rs (data×setor)}.
    min_persistencia     : entrada após confirmação na Nª observação; o retorno
                          começa na semana seguinte à confirmação.

    Retorna {quadrante: {horizonte: {n, media, mediana, hit_rate}}}. hit_rate =
    fração de episódios com forward RS > 0.
    """
    agg: dict = {}
    for ep in episodios:
        q = ep["quadrante"]
        for h, fr in fwd_rs_por_horizonte.items():
            if fr is None or fr.empty or ep["setor"] not in fr.columns:
                continue
            confirmacao = data_confirmacao(ep, fr.index, min_persistencia)
            if confirmacao is None or confirmacao not in fr.index:
                continue
            val = fr.at[confirmacao, ep["setor"]]
            if val is None or not np.isfinite(val):
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
    horizontes: tuple = (4, 13, 26, 52),
    limiar_tilt: int = 1,
    limiar_rs: float = 0.02,
    min_persistencia: int = 1,
    min_cobertura: float = 1.0,
) -> dict:
    """
    Pipeline completo (para dados semanais alinhados): RS trailing → quadrantes →
    episódios → forward RS por horizonte → estatística. `retornos_setoriais` e
    `tilt_hist` devem estar na MESMA frequência/índice (semanal).
    """
    from utils.setor_series import rs_setorial
    rs_hist = rs_setorial(retornos_setoriais, janela_rs, min_cobertura=min_cobertura)
    quad = matriz_quadrantes(tilt_hist, rs_hist,
                             limiar_tilt=limiar_tilt, limiar_rs=limiar_rs)
    eps = extrair_episodios(quad)
    fwd = {h: forward_rs(retornos_setoriais, h, min_cobertura=min_cobertura) for h in horizontes}
    stats = estatistica_por_quadrante(eps, fwd, min_persistencia=min_persistencia)
    confirmados = sum(data_confirmacao(ep, quad.index, min_persistencia) is not None for ep in eps)
    return {"n_episodios": len(eps), "n_confirmados": confirmados, "estatistica": stats,
            "horizontes": list(horizontes), "janela_rs": janela_rs,
            "metodologia": {"versao": 2, "entrada": "apos_confirmacao",
                "persistencia": min_persistencia, "cobertura_minima": min_cobertura,
                "tipo": "estudo_descritivo_retrospectivo", "fora_da_amostra": False,
                "vintage": "atual_com_atrasos_explicitos",
                "custos_incluidos": False, "sobreposicao_horizontes": True,
                "vies_universo": "tickers atuais; equal-weight BR"}}
