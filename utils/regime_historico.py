"""
utils/regime_historico.py — reconstrução histórica de regime e tilt (PLANO_MACRO M0-2).

Constrói o "deveria ser" no tempo. Como `classificar_regime` e `tilt_setor` são
funções PURAS que aceitam os parâmetros macro explicitamente, dá para reconstituir
o regime e o tilt setorial de CADA semana do passado alimentando com os valores
macro DA ÉPOCA (Selic, IPCA 12m, VIX, Treasury 10y) — reconstrução fiel, não
aproximada.

Núcleo puro (`reconstruir_regime_tilt`) por injeção das funções de regime/tilt →
testável sem Streamlit. O loader (`carregar_inputs_macro_semanais`) faz o I/O
(SGS do BCB + yfinance) e é best-effort (tolera falha de API).

Nota: a reconstrução usa o mapa de tilt ATUAL sobre dados passados — ou seja,
"como a estratégia de hoje teria classificado o passado". É exatamente o que um
backtest de estratégia precisa (evita look-ahead de mudanças futuras no motor).
"""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

# 11 setores canônicos que têm tilt de regime (keys de _TILT_JURO_ALTO/_TILT_STRESS)
SETORES_TILT = [
    "comunicacao", "consumo_ciclico", "consumo_defensivo", "energia",
    "financeiro", "imobiliario", "industria", "materiais", "saude",
    "tecnologia", "utilities",
]

_IPCA_FALLBACK = 4.5
_T10_FALLBACK = 4.3


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x   # NaN → None


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
        _ipca = ipca if ipca is not None else _IPCA_FALLBACK
        _t10 = t10 if t10 is not None else _T10_FALLBACK

        reg = fn_regime(selic=selic, vix=vix, ipca=_ipca, treasury_10y=_t10) or {}
        ctx = {"selic": selic, "vix": vix, "treasury_10y": _t10}
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

    if not linhas:
        return pd.DataFrame()
    return pd.DataFrame(linhas).set_index("data")


# ── loader (I/O best-effort — fora do núcleo puro/testes) ─────────────────────

def carregar_inputs_macro_semanais(anos: int = 8) -> pd.DataFrame:
    """
    Puxa Selic (SGS 432), IPCA 12m (SGS 13522), VIX (^VIX) e Treasury 10y (^TNX/10),
    reamostra em base SEMANAL (sexta, último valor, ffill). Best-effort: cada fonte
    falha em silêncio e sai como coluna ausente. Retorna DataFrame p/ reconstruir.
    """
    from datetime import date, timedelta
    inicio = (date.today() - timedelta(days=int(anos * 365.25)))
    idx = pd.date_range(inicio, date.today(), freq="W-FRI")
    out = pd.DataFrame(index=idx)

    def _sgs(cod, nome):
        try:
            from bcb import sgs
            s = sgs.get({nome: cod}, start=inicio.isoformat())[nome]
            s.index = pd.to_datetime(s.index)
            return s.reindex(idx, method="ffill")
        except Exception:
            return None

    def _yf_close(tk, div=1.0):
        try:
            import yfinance as yf
            df = yf.download(tk, start=inicio.isoformat(), progress=False,
                             auto_adjust=False)
            close = df["Close"]
            if hasattr(close, "columns"):     # MultiIndex → 1ª coluna
                close = close.iloc[:, 0]
            close.index = pd.to_datetime(close.index)
            return (close / div).reindex(idx, method="ffill")
        except Exception:
            return None

    for col, s in (
        ("selic", _sgs(432, "selic")),
        ("ipca_12m", _sgs(13522, "ipca_12m")),
        ("vix", _yf_close("^VIX")),
        ("treasury_10y", _yf_close("^TNX", div=10.0)),
    ):
        if s is not None:
            out[col] = s
    return out.dropna(subset=[c for c in ("selic", "vix") if c in out.columns])


def reconstruir_regime_tilt_br(anos: int = 8) -> pd.DataFrame:
    """Conveniência: carrega inputs semanais BR e reconstrói regime+tilt."""
    inputs = carregar_inputs_macro_semanais(anos=anos)
    if inputs.empty:
        return pd.DataFrame()
    return reconstruir_regime_tilt(inputs, market="BR")
