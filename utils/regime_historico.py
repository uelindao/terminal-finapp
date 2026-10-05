"""Reconstrução retrospectiva semanal de regime e tilt.

Usa o mapa atual sobre a vintage hoje disponível, com atrasos de divulgação
assumidos e explícitos. Não equivale a um backtest point-in-time: revisões e
calibração posterior do próprio mapa não são removidas por esta reconstrução.
"""
from __future__ import annotations

from typing import Callable, Optional
import numpy as np

import pandas as pd

# 11 setores canônicos que têm tilt de regime (keys de _TILT_JURO_ALTO/_TILT_STRESS)
SETORES_TILT = [
    "comunicacao", "consumo_ciclico", "consumo_defensivo", "energia",
    "financeiro", "imobiliario", "industria", "materiais", "saude",
    "tecnologia", "utilities",
]



def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def reconstruir_regime_tilt(
    inputs: pd.DataFrame,
    setores: Optional[list] = None,
    *,
    market: str = "BR",
    fn_regime: Optional[Callable] = None,
    fn_tilt: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    inputs  : DataFrame index=data, colunas incluindo [selic, vix] e opcionalmente
              [ipca_12m, treasury_10y]. Linhas sem selic OU vix são puladas.
    setores : setores canônicos p/ o tilt (default SETORES_TILT).
    fn_regime / fn_tilt: injetáveis (default macro_regime.classificar_regime e
              macro_state.tilt_setor).

    Retorna DataFrame index=data com: regime_label, regime_key, score_ambiente,
    selic, ipca_12m, vix, treasury_10y, tilt_<setor> (± pts) para cada setor.
    """
    if fn_regime is None:
        from utils.macro_regime import classificar_regime as fn_regime
    if fn_tilt is None:
        from utils.macro_state import tilt_setor as fn_tilt
    setores = setores or SETORES_TILT
    if inputs is None or inputs.empty:
        return pd.DataFrame()

    linhas = []
    for dt, row in inputs.iterrows():
        selic, vix = _f(row.get("selic")), _f(row.get("vix"))
        if selic is None or vix is None:
            continue
        ipca = _f(row.get("ipca_12m"))
        t10 = _f(row.get("treasury_10y"))
        if ipca is None or t10 is None:
            continue  # ausência não vira um cenário macro inventado
        reg = fn_regime(selic=selic, vix=vix, ipca=ipca, treasury_10y=t10) or {}
        ctx = {"selic": selic, "vix": vix, "treasury_10y": t10}
        d = {
            "data": dt,
            "regime_label": reg.get("label"),
            "regime_key": reg.get("regime_key"),
            "score_ambiente": reg.get("score_ambiente"),
            "selic": selic, "ipca_12m": ipca, "vix": vix, "treasury_10y": t10,
        }
        for s in setores:
            try:
                d[f"tilt_{s}"] = int((fn_tilt(s, ctx, market) or {}).get("pontos", 0) or 0)
            except Exception:
                d[f"tilt_{s}"] = 0
        linhas.append(d)

    result = pd.DataFrame(linhas).set_index("data") if linhas else pd.DataFrame()
    result.attrs.update(inputs.attrs)
    result.attrs["linhas_excluidas_sem_inputs"] = len(inputs) - len(result)
    result.attrs.setdefault("metodologia", {"tipo": "retrospectiva", "point_in_time": False,
        "vintage": "informada pelo chamador; disponibilidade não comprovada"})
    return result


# ── loader (I/O best-effort — fora do núcleo puro/testes) ─────────────────────

def alinhar_serie_disponivel(serie: pd.Series, indice: pd.DatetimeIndex, *,
    atraso_dias: int = 0, mes_fechado: bool = False, publicado_em: pd.Series | None = None
) -> pd.DataFrame:
    """Último valor divulgado até cada corte, sem antecipar a referência mensal.

    Quando não há calendário real, usa atraso conservador ASSUMIDO. O valor é
    da vintage fornecida; atrasar seu uso não corrige revisões ex post.
    """
    if serie is None or serie.empty:
        return pd.DataFrame(index=indice, columns=["valor", "referencia_em", "disponivel_em"])
    valores = pd.to_numeric(serie, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().copy()
    valores.index = pd.to_datetime(valores.index, utc=True).tz_convert(None)
    referencia = valores.index
    if publicado_em is not None:
        disponivel = pd.to_datetime(publicado_em.reindex(serie.index), utc=True).dt.tz_convert(None)
        disponivel.index = pd.to_datetime(disponivel.index, utc=True).tz_convert(None)
        disponibilidade = pd.DatetimeIndex(disponivel.reindex(referencia))
    else:
        base = referencia + pd.offsets.MonthEnd(0) if mes_fechado else referencia
        disponibilidade = base + pd.Timedelta(days=atraso_dias)
    dados = pd.DataFrame({"valor": valores.to_numpy(), "referencia_em": referencia,
                          "disponivel_em": disponibilidade}).dropna(subset=["disponivel_em"])
    dados = dados.sort_values(["disponivel_em", "referencia_em"]).drop_duplicates("disponivel_em", keep="last")
    dados = dados.set_index("disponivel_em", drop=False)
    corte = pd.to_datetime(indice, utc=True).tz_convert(None)
    # Valores financeiros conhecidos apenas no dia seguinte: escolha explícita
    # de fechamento conservador, sem pressupor o horário real de publicação.
    result = dados.reindex(corte, method="ffill") if not dados.empty else pd.DataFrame(index=corte, columns=["valor", "referencia_em", "disponivel_em"])
    result.index = indice
    result.attrs["disponibilidade_base"] = "divulgacao_informada" if publicado_em is not None else "atraso_conservador_assumido"
    return result


def carregar_inputs_macro_semanais(anos: int = 8) -> pd.DataFrame:
    """BCB/Yahoo, vintage atual; IPCA após mês fechado +20d, diárias +1d.

    Atrasos são suposições explícitas, não datas oficiais de divulgação. As
    séries armazenadas append-only permitem auditoria prospectiva a partir da
    coleta, mas não inventam vintages anteriores à implantação.
    """
    from datetime import date, timedelta
    inicio = date.today() - timedelta(days=int(anos * 365.25))
    idx = pd.date_range(inicio, date.today(), freq="W-FRI")
    out = pd.DataFrame(index=idx)
    metodos = {}

    def _sgs(cod, nome):
        try:
            from bcb import sgs
            return sgs.get({nome: cod}, start=(inicio - timedelta(days=70)).isoformat())[nome]
        except Exception:
            return None

    def _yf_close(tk):
        try:
            import yfinance as yf
            df = yf.download(tk, start=(inicio - timedelta(days=7)).isoformat(), progress=False,
                             auto_adjust=False)
            close = df["Close"]
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]
            return close
        except Exception:
            return None

    for col, serie, fonte, atraso, mensal in (
        ("selic", _sgs(432, "selic"), "BCB SGS432", 1, False),
        ("ipca_12m", _sgs(13522, "ipca_12m"), "BCB SGS13522", 20, True),
        ("vix", _yf_close("^VIX"), "Yahoo ^VIX", 1, False),
        ("treasury_10y", _yf_close("^TNX"), "Yahoo ^TNX (%)", 1, False),
    ):
        if serie is not None:
            alinhada = alinhar_serie_disponivel(serie, idx, atraso_dias=atraso, mes_fechado=mensal)
            idade = pd.Series(idx, index=idx) - pd.to_datetime(alinhada["disponivel_em"])
            max_idade = 75 if mensal else 7
            out[col] = alinhada["valor"].where(idade <= pd.Timedelta(days=max_idade))
            metodos[col] = {"fonte": fonte, "atraso_dias": atraso, "mes_fechado": mensal,
                            "disponibilidade_base": "atraso_conservador_assumido", "max_idade_dias": max_idade}
    out.attrs["metodologia"] = {"tipo": "reconstrucao_retrospectiva", "point_in_time": False,
        "vintage": "mais recente disponível; revisões históricas não removidas", "series": metodos,
        "mapa_tilt": "atual aplicado ao passado; calibração ex post possível"}
    return out


def reconstruir_regime_tilt_br(anos: int = 8) -> pd.DataFrame:
    """Conveniência: carrega inputs semanais BR e reconstrói regime+tilt."""
    inputs = carregar_inputs_macro_semanais(anos=anos)
    if inputs.empty:
        return pd.DataFrame()
    return reconstruir_regime_tilt(inputs, market="BR")
