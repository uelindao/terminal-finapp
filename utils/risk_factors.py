"""
utils/risk_factors.py — exposição a fatores estilo Fama-French.

Modelo 3 fatores (Fama-French 1993):

    R_carteira − Rf = α + β_MKT × (R_mkt − Rf) + β_SMB × SMB + β_HML × HML + ε

- β_MKT: beta de mercado (1 = se move como o mercado)
- β_SMB: positivo = tilt para small caps; negativo = large caps
- β_HML: positivo = tilt para value (P/VP baixo); negativo = growth
- α: retorno não explicado pelos fatores (alfa)

Fatores são **sintéticos**, construídos do próprio universo do screener:
- MKT-RF: retorno equally-weighted do universo − Rf diária
- SMB: média(smalls) − média(bigs), com corte na mediana de market_cap
- HML: média(top-30% P/VP) − média(bottom-30% P/VP)

Trade-offs vs Ken French / NEFIN:
- (+) zero dependência externa, funciona com cache local
- (+) consistente entre BR e US
- (−) factor universe pequeno (50-200 tickers vs ~3000) — betas podem
      ser menos estáveis em janelas curtas
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class ResultadoFatores:
    """Resultado da regressão Fama-French."""
    alpha_diario: float           # decimal — intercepto da regressão
    alpha_anual: float            # alpha_diario × 252
    beta_mkt: float
    beta_smb: float
    beta_hml: float
    r_squared: float
    n_obs: int
    pvalue_alpha: float
    pvalue_mkt: float
    pvalue_smb: float
    pvalue_hml: float
    se_alpha: float
    se_mkt: float
    se_smb: float
    se_hml: float


def construir_fatores_sinteticos(
    universo: list[str],
    market_caps: dict[str, float],
    pvp: dict[str, float],
    precos: pd.DataFrame,
    rf_anual: float,
) -> pd.DataFrame:
    """
    Constrói série diária dos fatores Fama-French sintéticos.

    Retorna DataFrame com índice de datas e colunas: MKT_RF, SMB, HML, RF.

    `precos`: DataFrame Close × ticker (datas no índice).
    `rf_anual`: taxa livre de risco anualizada em decimal (ex.: 0.1475 = Selic).
                Converte para diária via (1+rf)^(1/252) − 1.
    """
    if precos is None or precos.empty:
        return pd.DataFrame()

    rf_diaria = (1 + rf_anual) ** (1 / 252) - 1
    rets = precos.pct_change().dropna(how="all")
    if rets.empty:
        return pd.DataFrame()

    # Filtra universo a tickers presentes nos preços + com market_cap + p/vp
    universo_valido = [
        t for t in universo
        if t in rets.columns and t in market_caps and market_caps[t] > 0
    ]
    if len(universo_valido) < 10:
        return pd.DataFrame()

    # ── MKT-RF: retorno equally-weighted do universo - rf ──
    rets_universo = rets[universo_valido]
    r_mkt = rets_universo.mean(axis=1)
    mkt_rf = r_mkt - rf_diaria

    # ── SMB: smalls − bigs (corte na mediana de market_cap) ──
    mc_vals = sorted([(t, market_caps[t]) for t in universo_valido], key=lambda x: x[1])
    n = len(mc_vals)
    smalls = [t for t, _ in mc_vals[: n // 2]]
    bigs   = [t for t, _ in mc_vals[n - n // 2 :]]
    smb = rets_universo[smalls].mean(axis=1) - rets_universo[bigs].mean(axis=1)

    # ── HML: top-30% pvp (value) − bottom-30% pvp (growth) ──
    pvp_vals = sorted(
        [(t, pvp[t]) for t in universo_valido if t in pvp and pvp[t] > 0],
        key=lambda x: x[1],
    )
    if len(pvp_vals) < 6:
        hml = pd.Series(0.0, index=mkt_rf.index)
    else:
        n_p = len(pvp_vals)
        cut = max(1, n_p // 3)
        # P/VP baixo = "value" no sentido contábil tradicional. Tilt =
        # baixo P/VP > alto P/VP. Mantém o sinal canônico do HML.
        value = [t for t, _ in pvp_vals[:cut]]
        growth = [t for t, _ in pvp_vals[-cut:]]
        hml = rets_universo[value].mean(axis=1) - rets_universo[growth].mean(axis=1)

    fatores = pd.DataFrame({
        "MKT_RF": mkt_rf,
        "SMB": smb,
        "HML": hml,
        "RF": rf_diaria,
    }).dropna()
    return fatores


def regressao_fama_french(
    retornos_carteira: pd.Series,
    fatores: pd.DataFrame,
) -> Optional[ResultadoFatores]:
    """
    Roda OLS de (R_carteira − Rf) sobre (MKT_RF, SMB, HML).

    Retorna ResultadoFatores ou None se dados insuficientes (< 60 dias).
    """
    if retornos_carteira is None or retornos_carteira.empty:
        return None
    if fatores is None or fatores.empty:
        return None

    df = pd.concat([retornos_carteira.rename("ret"), fatores], axis=1).dropna()
    if len(df) < 60:
        return None

    y = (df["ret"] - df["RF"]).values
    x_cols = ["MKT_RF", "SMB", "HML"]
    X = np.column_stack([np.ones(len(df))] + [df[c].values for c in x_cols])

    # OLS: β = (X'X)^-1 X'y
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    y_pred = X @ beta
    resid = y - y_pred
    n, k = X.shape
    df_resid = n - k

    ss_res = (resid ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    sigma2 = ss_res / df_resid if df_resid > 0 else 0.0
    var_beta = sigma2 * np.diag(XtX_inv)
    se = np.sqrt(np.maximum(var_beta, 0))
    t_stat = np.divide(beta, se, out=np.zeros_like(beta), where=se > 0)
    p_vals = 2 * stats.t.sf(np.abs(t_stat), df=df_resid)

    return ResultadoFatores(
        alpha_diario=float(beta[0]),
        alpha_anual=float(beta[0]) * 252,
        beta_mkt=float(beta[1]),
        beta_smb=float(beta[2]),
        beta_hml=float(beta[3]),
        r_squared=float(r2),
        n_obs=n,
        pvalue_alpha=float(p_vals[0]),
        pvalue_mkt=float(p_vals[1]),
        pvalue_smb=float(p_vals[2]),
        pvalue_hml=float(p_vals[3]),
        se_alpha=float(se[0]),
        se_mkt=float(se[1]),
        se_smb=float(se[2]),
        se_hml=float(se[3]),
    )
