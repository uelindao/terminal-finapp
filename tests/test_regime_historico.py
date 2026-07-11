"""Testes de utils/regime_historico — reconstrução histórica (PLANO_MACRO M0-2)."""
import numpy as np
import pandas as pd

from utils.regime_historico import reconstruir_regime_tilt, SETORES_TILT


def _inputs():
    idx = pd.date_range("2020-01-03", periods=4, freq="W-FRI")
    return pd.DataFrame({
        "selic":        [4.5, 2.0, 13.75, 14.25],
        "ipca_12m":     [4.0, 3.0, 10.0, 4.7],
        "vix":          [15.0, 60.0, 20.0, 14.0],
        "treasury_10y": [1.9, 0.6, 3.9, 4.3],
    }, index=idx)


# ── agregação pura (stubs) ────────────────────────────────────────────────────

def test_estrutura_com_stubs():
    fn_regime = lambda **k: {"label": "L", "regime_key": "k", "score_ambiente": 50}
    fn_tilt = lambda s, ctx, m: {"pontos": 3 if s == "financeiro" else -1}
    df = reconstruir_regime_tilt(_inputs(), ["financeiro", "imobiliario"],
                                 fn_regime=fn_regime, fn_tilt=fn_tilt)
    assert list(df.columns) == ["regime_label", "regime_key", "score_ambiente",
                                "selic", "ipca_12m", "vix", "treasury_10y",
                                "tilt_financeiro", "tilt_imobiliario"]
    assert (df["tilt_financeiro"] == 3).all()
    assert (df["tilt_imobiliario"] == -1).all()
    assert len(df) == 4


def test_pula_linha_sem_selic_ou_vix():
    inp = _inputs().copy()
    inp.loc[inp.index[1], "vix"] = np.nan
    fn_regime = lambda **k: {"label": "L"}
    fn_tilt = lambda s, ctx, m: {"pontos": 0}
    df = reconstruir_regime_tilt(inp, ["financeiro"], fn_regime=fn_regime, fn_tilt=fn_tilt)
    assert len(df) == 3          # a linha com vix NaN foi pulada


def test_ctx_passado_ao_tilt_tem_valores_da_epoca():
    capturado = {}
    fn_regime = lambda **k: {"label": "L"}
    def fn_tilt(s, ctx, m):
        capturado.update(ctx)
        return {"pontos": 0}
    reconstruir_regime_tilt(_inputs().head(1), ["financeiro"],
                            fn_regime=fn_regime, fn_tilt=fn_tilt)
    assert capturado["selic"] == 4.5 and capturado["vix"] == 15.0


def test_vazio_nao_quebra():
    assert reconstruir_regime_tilt(pd.DataFrame()).empty


# ── integração real (fidelidade) ──────────────────────────────────────────────

def test_integracao_fidelidade_regime_e_tilt():
    df = reconstruir_regime_tilt(_inputs())     # usa classificar_regime + tilt_setor reais
    assert not df.empty and len(df) == 4
    assert all(f"tilt_{s}" in df.columns for s in SETORES_TILT)

    # 2020-03 sintético: vix 60 = stress global
    assert "stress" in str(df.iloc[1]["regime_key"]).lower()
    # selic 2%: juros baixos
    assert "baixos" in str(df.iloc[1]["regime_key"]).lower()

    # selic muito alta (13.75 / 14.25): imobiliário penalizado, financeiro favorecido
    for i in (2, 3):
        assert df.iloc[i]["tilt_imobiliario"] < 0
        assert df.iloc[i]["tilt_financeiro"] > 0

    # selic baixa + vix calmo (linha 0): sem penalidade de juro nem de stress
    assert df.iloc[0]["tilt_imobiliario"] == 0
    # linha 1 tem vix 60 (stress) → imobiliário vulnerável (tilt < 0 vem do stress)
    assert df.iloc[1]["tilt_imobiliario"] < 0
