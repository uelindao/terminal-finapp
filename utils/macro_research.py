"""Pure transformations for a personal medium/long-term macro workbench.

Reference dates describe the economy, not when the data was released. A chart
built from today's vintage is retrospective, never a point-in-time backtest.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

QUADRANTS = {
    "crescimento_desinflacao": "Atividade acelerando · inflação arrefecendo",
    "crescimento_inflacao": "Atividade acelerando · inflação acelerando",
    "desaceleracao_inflacao": "Atividade desacelerando · inflação acelerando",
    "desaceleracao_desinflacao": "Atividade desacelerando · inflação arrefecendo",
    "transicao": "Direção ainda pouco definida",
    "indisponivel": "Dados insuficientes",
}


def mensal(series: pd.Series) -> pd.Series:
    """Calendarize without filling gaps or dropping intervening months."""
    if series is None or len(series) == 0:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    s = pd.to_numeric(series.copy(), errors="coerce").replace([np.inf, -np.inf], np.nan)
    index = pd.to_datetime(s.index, errors="coerce", utc=True)
    s.index = index.tz_convert(None)
    s = s[~s.index.isna()].sort_index()
    if s.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    # Joined snapshots also contain daily rates. Those dates extend the index
    # of monthly series with NaNs but do not create new monthly references.
    # Trim only exterior emptiness; every gap between observed months remains.
    first, last = s.first_valid_index(), s.last_valid_index()
    if first is None or last is None:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    return s.loc[first:last].resample("ME").last()


def taxa_anualizada(monthly_pct: pd.Series, window: int = 3) -> pd.Series:
    if window not in (3, 6, 12):
        raise ValueError("Janela deve ser 3, 6 ou 12 meses.")
    s = mensal(monthly_pct)
    factors = (1 + s / 100).where(s > -100)
    product = factors.rolling(window, min_periods=window).apply(np.prod, raw=True)
    return (product.pow(12 / window) - 1) * 100


def preparar_transicoes(
    atividade: pd.Series,
    inflacao: pd.Series,
    *,
    inflacao_tipo: str = "mensal_pct",
    janela: int = 3,
    persistencia: int = 2,
    limiar_atividade: float = 0.25,
    limiar_inflacao: float = 0.25,
) -> pd.DataFrame:
    """Direction of SA activity and inflation, with causal confirmation.

    The confirmation at t uses only t and the preceding monthly observations.
    Persistence concerns observations, not calendar release dates.
    """
    if janela not in (3, 6) or persistencia < 1:
        raise ValueError("Janela 3/6 meses e persistência positiva são necessárias.")
    if any(not math.isfinite(float(v)) or float(v) < 0
           for v in (limiar_atividade, limiar_inflacao)):
        raise ValueError("Limiares devem ser finitos e não negativos.")
    if inflacao_tipo not in ("mensal_pct", "indice"):
        raise ValueError("Inflação deve ser mensal_pct ou indice.")
    activity = mensal(atividade).where(lambda x: x > 0)
    inflation = mensal(inflacao)
    if inflacao_tipo == "indice":
        inflation = (inflation.where(inflation > 0).pct_change(fill_method=None)) * 100
    mean = activity.rolling(janela, min_periods=janela).mean()
    growth = ((mean / mean.shift(janela)).pow(12 / janela) - 1) * 100
    run_rate = taxa_anualizada(inflation, janela)
    frame = pd.concat({"atividade_nivel": activity, "inflacao_mensal": inflation,
                       "atividade_ritmo": growth, "inflacao_ritmo": run_rate}, axis=1).sort_index()
    if frame.empty:
        return pd.DataFrame(columns=["atividade_ritmo", "inflacao_ritmo", "delta_atividade",
                                     "delta_inflacao", "quadrante", "consecutivos",
                                     "confirmado", "estado"])
    # Reindex the joint calendar so a missing month cannot imply persistence.
    common_last = min(activity.last_valid_index(), inflation.last_valid_index()) if (
        activity.last_valid_index() is not None and inflation.last_valid_index() is not None) else None
    if common_last is not None:
        frame = frame.loc[:common_last]
    frame = frame.reindex(pd.date_range(frame.index.min(), frame.index.max(), freq="ME"))
    frame["delta_atividade"] = frame["atividade_ritmo"] - frame["atividade_ritmo"].shift(janela)
    frame["delta_inflacao"] = frame["inflacao_ritmo"] - frame["inflacao_ritmo"].shift(janela)
    keys, counts = [], []
    previous, count = None, 0
    for x, y in zip(frame["delta_atividade"], frame["delta_inflacao"]):
        if pd.isna(x) or pd.isna(y):
            key = "indisponivel"
        elif abs(x) <= limiar_atividade or abs(y) <= limiar_inflacao:
            key = "transicao"
        elif x > 0:
            key = "crescimento_inflacao" if y > 0 else "crescimento_desinflacao"
        else:
            key = "desaceleracao_inflacao" if y > 0 else "desaceleracao_desinflacao"
        count = count + 1 if key == previous and key not in ("transicao", "indisponivel") else (0 if key in ("transicao", "indisponivel") else 1)
        keys.append(key)
        counts.append(count)
        previous = key
    frame["quadrante"] = keys
    frame["consecutivos"] = counts
    frame["confirmado"] = frame["consecutivos"] >= persistencia
    frame["estado"] = [("confirmado" if confirmed else "em formação")
                       if key not in ("transicao", "indisponivel") else QUADRANTS[key]
                       for key, confirmed in zip(keys, frame["confirmado"])]
    frame.attrs["metodologia"] = {
        "base_temporal": "datas de referência; vintage disponível hoje",
        "atividade": f"média {janela}m / média dos {janela}m anteriores, anualizada",
        "inflacao": f"inflação composta {janela}m, anualizada",
        "direcao": f"mudança do ritmo em {janela} meses (pp)",
        "persistencia": persistencia,
        "causalidade": "transformações sem dados futuros; revisões históricas não eliminadas",
    }
    return frame


def normalizar_focus(records: list[dict], *, tipo: str) -> pd.DataFrame:
    """Preserve fixed target years and sample definitions when comparing revisions."""
    columns = ["data", "indicador", "horizonte", "mediana", "respondentes", "base_calculo"]
    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(records)
    required = {"Data", "Indicador", "Mediana"}
    if not required.issubset(df):
        return pd.DataFrame(columns=columns)
    if "baseCalculo" in df:
        df = df[pd.to_numeric(df["baseCalculo"], errors="coerce").eq(0)].copy()
    if tipo == "12m":
        if "Suavizada" in df:
            df = df[df["Suavizada"].astype(str).str.lower().isin(["n", "nao", "não", "false", "0"])].copy()
        horizon = pd.Series("12m móveis", index=df.index)
    elif tipo == "anual":
        if "DataReferencia" not in df:
            return pd.DataFrame(columns=columns)
        horizon = df["DataReferencia"].astype(str)
    else:
        raise ValueError("Tipo Focus desconhecido.")
    result = pd.DataFrame({
        "data": pd.to_datetime(df["Data"], errors="coerce"),
        "indicador": df["Indicador"].astype(str),
        "horizonte": horizon,
        "mediana": pd.to_numeric(df["Mediana"], errors="coerce"),
        "respondentes": pd.to_numeric(df.get("numeroRespondentes", pd.Series(index=df.index, dtype=float)), errors="coerce"),
        "base_calculo": 0,
    })
    result = result.replace([np.inf, -np.inf], np.nan).dropna(subset=["data", "mediana"])
    result = result.sort_values("data").drop_duplicates(["data", "indicador", "horizonte"], keep="last")
    return result.reset_index(drop=True)


def revisar_expectativa(
    focus: pd.DataFrame, indicador: str, horizonte: str, *,
    data_corte=None, dias: int = 30, tolerancia_dias: int = 7,
) -> dict:
    """Compare one target and sample, with a backward-only bounded as-of lookup."""
    empty = {"atual": None, "anterior": None, "revisao": None, "data": None,
             "data_anterior": None, "respondentes": None}
    if focus is None or focus.empty:
        return empty
    df = focus[(focus["indicador"] == indicador) & (focus["horizonte"].astype(str) == str(horizonte))].copy()
    cut = pd.Timestamp(data_corte) if data_corte is not None else pd.Timestamp.today()
    df = df[df["data"] <= cut].sort_values("data")
    if df.empty:
        return empty
    latest = df.iloc[-1]
    target = latest["data"] - pd.Timedelta(days=dias)
    history = df[df["data"] <= target]
    old = history.iloc[-1] if not history.empty else None
    if old is not None and (target - old["data"]).days > tolerancia_dias:
        old = None
    return {"atual": float(latest["mediana"]),
            "anterior": float(old["mediana"]) if old is not None else None,
            "revisao": float(latest["mediana"] - old["mediana"]) if old is not None else None,
            "data": latest["data"], "data_anterior": old["data"] if old is not None else None,
            "respondentes": None if pd.isna(latest["respondentes"]) else int(latest["respondentes"])}


def fisher(nominal, inflation) -> float | None:
    try:
        nominal, inflation = float(nominal), float(inflation)
        if not all(math.isfinite(x) for x in (nominal, inflation)) or inflation <= -100 or nominal <= -100:
            return None
        return ((1 + nominal / 100) / (1 + inflation / 100) - 1) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return None
