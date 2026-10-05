import numpy as np
import pandas as pd
import pytest

from utils.macro_research import preparar_transicoes, taxa_anualizada, normalizar_focus, revisar_expectativa, fisher
from utils.macro_research_data import focus_url


def inputs():
    index = pd.date_range("2020-01-31", periods=60, freq="ME")
    activity = pd.Series(100 * np.exp(np.linspace(0, 0.3, 60) + 0.02 * np.sin(np.arange(60)/4)), index=index)
    inflation = pd.Series(0.3 + 0.15 * np.sin(np.arange(60)/5), index=index)
    return activity, inflation


def test_transitions_are_prefix_causal_and_confirmation_does_not_use_future():
    activity, inflation = inputs()
    full = preparar_transicoes(activity, inflation)
    prefix = preparar_transicoes(activity.iloc[:36], inflation.iloc[:36])
    pd.testing.assert_frame_equal(prefix, full.iloc[:36], check_freq=False)
    assert (full.loc[full["confirmado"], "consecutivos"] >= 2).all()


def test_calendar_gap_breaks_persistence_and_is_not_filled():
    activity, inflation = inputs()
    missing_date = activity.index[32]
    result = preparar_transicoes(activity.drop(missing_date), inflation)
    assert pd.isna(result.loc[missing_date, "atividade_nivel"])
    assert result.loc[missing_date, "quadrante"] == "indisponivel"
    assert result.loc[missing_date, "consecutivos"] == 0
    assert not result.loc[missing_date, "confirmado"]


def test_index_inflation_and_monthly_pct_have_same_rates():
    activity, inflation = inputs()
    index = 100 * (1 + inflation / 100).cumprod()
    raw = preparar_transicoes(activity, inflation)
    indexed = preparar_transicoes(activity, index, inflacao_tipo="indice")
    pd.testing.assert_series_equal(raw["inflacao_ritmo"].iloc[5:], indexed["inflacao_ritmo"].iloc[5:], rtol=1e-10)
    assert taxa_anualizada(pd.Series([1., 1., 1.], index=activity.index[:3])).iloc[-1] == pytest.approx((1.01**12-1)*100)


def test_invalid_inputs_do_not_generate_regime():
    activity, inflation = inputs()
    activity.iloc[30] = float("inf")
    inflation.iloc[31] = -101
    result = preparar_transicoes(activity, inflation)
    assert result.loc[activity.index[30], "quadrante"] == "indisponivel"
    assert result.loc[activity.index[31], "quadrante"] == "indisponivel"
    with pytest.raises(ValueError):
        preparar_transicoes(activity, inflation, persistencia=0)


def test_focus_preserves_target_and_sample_definition():
    records = [
        {"Data": "2026-08-01", "Indicador": "IPCA", "DataReferencia": "2027", "Mediana": 4, "baseCalculo": 0, "numeroRespondentes": 100},
        {"Data": "2026-09-01", "Indicador": "IPCA", "DataReferencia": "2027", "Mediana": 4.2, "baseCalculo": 0, "numeroRespondentes": 90},
        {"Data": "2026-09-01", "Indicador": "IPCA", "DataReferencia": "2028", "Mediana": 3.5, "baseCalculo": 0},
        {"Data": "2026-09-01", "Indicador": "IPCA", "DataReferencia": "2027", "Mediana": 9, "baseCalculo": 1},
    ]
    focus = normalizar_focus(records, tipo="anual")
    result = revisar_expectativa(focus, "IPCA", "2027", data_corte="2026-09-02", dias=30)
    assert result["atual"] == 4.2
    assert result["revisao"] == pytest.approx(0.2)
    assert result["respondentes"] == 90
    old_cut = revisar_expectativa(focus, "IPCA", "2027", data_corte="2026-08-10")
    assert old_cut["atual"] == 4


def test_focus_no_future_lookup_or_distant_revision():
    records = [
        {"Data": "2026-01-01", "Indicador": "IPCA", "DataReferencia": "2027", "Mediana": 4, "baseCalculo": 0},
        {"Data": "2026-09-01", "Indicador": "IPCA", "DataReferencia": "2027", "Mediana": 4.2, "baseCalculo": 0},
    ]
    result = revisar_expectativa(normalizar_focus(records, tipo="anual"), "IPCA", "2027", data_corte="2026-09-01")
    assert result["anterior"] is None and result["revisao"] is None


def test_smoothed_focus_does_not_mix_with_unsmoothed_12m():
    records = [{"Data": "2026-09-01", "Indicador": "IPCA", "Mediana": m, "baseCalculo": 0, "Suavizada": smooth}
               for m, smooth in [(4.2, "N"), (5.5, "S")]]
    focus = normalizar_focus(records, tipo="12m")
    assert focus["mediana"].tolist() == [4.2]
    assert focus["horizonte"].tolist() == ["12m móveis"]


def test_odata_url_uses_percent20_as_required_by_olinda():
    url = focus_url("ExpectativasMercadoAnuais", {"$filter": "Indicador eq 'IPCA'", "$orderby": "Data desc"})
    assert "Indicador%20eq%20%27IPCA%27" in url
    assert "Data%20desc" in url and "+" not in url


def test_fisher_is_explicit_and_missing_stays_missing():
    assert fisher(10, 5) == pytest.approx((1.1/1.05-1)*100)
    assert fisher(None, 5) is None
    assert fisher(10, float("nan")) is None
    assert fisher(10, -100) is None



def test_daily_join_does_not_create_unobserved_months_after_monthly_reference():
    from utils.macro_research import mensal
    activity, inflation = inputs()
    daily_dates = pd.bdate_range(activity.index[0] - pd.Timedelta(days=60), activity.index[-1] + pd.Timedelta(days=100))
    joined = pd.DataFrame({"activity": activity, "inflation": inflation, "rate": pd.Series(10., index=daily_dates)})
    actual = preparar_transicoes(joined["activity"], joined["inflation"])
    expected = preparar_transicoes(activity, inflation)
    pd.testing.assert_frame_equal(actual, expected)
    assert mensal(joined["activity"]).index[-1] == activity.index[-1]
    assert actual.iloc[-1]["quadrante"] != "indisponivel"


def test_common_month_ignores_later_inflation_but_preserves_internal_unknowns():
    activity, inflation = inputs()
    activity.iloc[30] = np.nan
    extended = inflation.copy()
    extended.loc[inflation.index[-1] + pd.offsets.MonthEnd(1)] = .5
    result = preparar_transicoes(activity, extended)
    assert result.index[-1] == activity.index[-1]
    assert pd.isna(result.loc[activity.index[30], "atividade_nivel"])
    assert result.loc[activity.index[30], "quadrante"] == "indisponivel"
    assert not result.loc[activity.index[30], "confirmado"]
    assert result.loc[activity.index[30], "consecutivos"] == 0


def test_monthly_all_missing_does_not_create_fake_reference_calendar():
    from utils.macro_research import mensal
    missing = pd.Series(np.nan, index=pd.bdate_range("2025-01-01", "2025-04-01"))
    assert mensal(missing).empty
