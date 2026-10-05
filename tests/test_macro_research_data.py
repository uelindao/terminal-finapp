from io import BytesIO
from zipfile import ZipFile
from unittest.mock import patch
from types import SimpleNamespace

import pandas as pd
from utils.macro_research_data import _fred, buscar_focus_publico, carregar_bancada


def response(csv):
    raw = csv.encode()
    return SimpleNamespace(text=csv, content=raw, raise_for_status=lambda: None)


def test_fred_supports_csv_and_zip_without_filling_missing_observations():
    csv = "observation_date,INDPRO\n2026-01-01,100\n2026-02-01,.\n2026-03-01,102\n"
    with patch("utils.macro_research_data.requests.get", return_value=response(csv)):
        result = _fred(["INDPRO"], 10)
    assert pd.isna(result.loc["2026-02-01", "INDPRO"])
    archive = BytesIO()
    with ZipFile(archive, "w") as z:
        z.writestr("activity.csv", csv)
        z.writestr("yield.csv", "DATE,DFII10\n2026-01-01,2\n2026-03-01,2.1\n")
    mocked = SimpleNamespace(content=archive.getvalue(), raise_for_status=lambda: None)
    with patch("utils.macro_research_data.requests.get", return_value=mocked):
        result = _fred(["INDPRO", "DFII10"], 10)
    assert list(result) == ["INDPRO", "DFII10"]
    assert pd.isna(result.loc["2026-02-01", "DFII10"])


def test_focus_public_reader_encodes_odata_and_separates_horizons():
    urls = []
    def fake(url, **kwargs):
        urls.append(url)
        kind = "12" if "Inflacao12" in url else "annual"
        records = [{"Data": "2026-09-01", "Indicador": "IPCA", "Mediana": 4,
                    "baseCalculo": 0, "Suavizada": "N"}]
        if kind == "annual":
            records[0]["DataReferencia"] = "2027"
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"value": records})
    with patch("utils.macro_research_data.requests.get", side_effect=fake):
        result = buscar_focus_publico()
    assert set(result["horizonte"]) == {"2027", "12m móveis"}
    assert all("Data%20desc" in url for url in urls)
    assert result.attrs["avisos"] == []


def test_cache_first_does_not_call_public_endpoints():
    fn = getattr(carregar_bancada, "__wrapped__", carregar_bancada)
    with patch("utils.macro_research_data._snapshot", return_value=pd.DataFrame()), patch("utils.macro_research_data.requests.get") as get:
        result = fn(False)
    get.assert_not_called()
    assert result["regioes"]["BR"]["atividade"].empty
    assert all(r["referência"] == "ausente" for r in result["qualidade"])



def test_partial_focus_refresh_keeps_cached_annual_and_replaces_only_same_identity():
    from utils.macro_research_data import mesclar_focus
    columns = ["data", "indicador", "horizonte", "mediana", "respondentes", "base_calculo"]
    cached = pd.DataFrame([[pd.Timestamp("2026-09-01"), "IPCA", "2027", 4., 100, 0],
                           [pd.Timestamp("2026-09-01"), "IPCA", "12m móveis", 4.1, 90, 0]], columns=columns)
    fresh = pd.DataFrame([[pd.Timestamp("2026-09-01"), "IPCA", "12m móveis", 4.2, 95, 0],
                          [pd.Timestamp("2026-09-02"), "IPCA", "12m móveis", 4.3, 96, 0]], columns=columns)
    fresh.attrs["avisos"] = ["Focus anual indisponível nesta consulta."]
    merged = mesclar_focus(cached, fresh)
    assert len(merged) == 3
    assert merged.loc[merged["horizonte"] == "2027", "mediana"].tolist() == [4.]
    rolling = merged[merged["horizonte"] == "12m móveis"]
    assert rolling["mediana"].tolist() == [4.2, 4.3]
    assert rolling["respondentes"].tolist() == [95, 96]
    assert merged.attrs["avisos"] == fresh.attrs["avisos"]


def test_workbench_partial_public_focus_retains_other_cached_horizon_and_warning():
    columns = ["data", "indicador", "horizonte", "mediana", "respondentes", "base_calculo"]
    cached = pd.DataFrame([[pd.Timestamp("2026-09-01"), "IPCA", "2027", 4., 100, 0]], columns=columns).set_index("data")
    fresh = pd.DataFrame([[pd.Timestamp("2026-09-02"), "IPCA", "12m móveis", 4.3, 96, 0]], columns=columns)
    fresh.attrs["avisos"] = ["Focus anual indisponível nesta consulta."]
    fn = getattr(carregar_bancada, "__wrapped__", carregar_bancada)
    with patch("utils.macro_research_data._snapshot", side_effect=lambda name: cached if name == "focus_expectativas" else pd.DataFrame()), \
         patch("utils.macro_research_data._bcb", return_value=pd.Series(dtype=float)), \
         patch("utils.macro_research_data._fred", return_value=pd.DataFrame()), \
         patch("utils.macro_research_data.buscar_focus_publico", return_value=fresh):
        result = fn(True)
    assert set(result["focus"]["horizonte"]) == {"2027", "12m móveis"}
    assert "Focus anual indisponível nesta consulta." in result["avisos"]
    assert result["qualidade"][-1]["origem"] == "consulta pública + snapshot"


def test_cache_first_joins_etl_breakeven_snapshot_with_its_own_reference_and_collection():
    activity = pd.DataFrame({"INDPRO": [100.], "CPIAUCSL": [320.],
                             "DGS10": [4.], "DFII10": [2.]},
                            index=pd.to_datetime(["2026-09-01"]))
    activity.attrs["coletado_em"] = "2026-10-02T10:00:00Z"
    expectations = pd.DataFrame({"T10YIE": [2.1, float("nan"), 2.2]},
                                index=pd.to_datetime(["2026-09-29", "2026-09-30", "2026-10-01"]))
    expectations.attrs["coletado_em"] = "2026-10-03T12:00:00Z"
    snapshots = {"fred_global": activity, "expectativas_us": expectations}
    fn = getattr(carregar_bancada, "__wrapped__", carregar_bancada)
    with patch("utils.macro_research_data._snapshot", side_effect=lambda name: snapshots.get(name, pd.DataFrame())), \
         patch("utils.macro_research_data.requests.get") as get:
        result = fn(False)
    get.assert_not_called()
    us = result["regioes"]["US"]["dados"]
    assert us.loc["2026-10-01", "T10YIE"] == 2.2
    assert pd.isna(us.loc["2026-09-30", "T10YIE"])
    assert us.loc["2026-09-01", "INDPRO"] == 100.
    assert pd.isna(us.loc["2026-10-01", "INDPRO"])
    by_source = {row["fonte"]: row for row in result["qualidade"]}
    assert by_source["FRED T10YIE"]["referência"] == "01/10/2026"
    assert by_source["FRED T10YIE"]["coleta"] == "2026-10-03T12:00:00Z"
    assert by_source["FRED T10YIE"]["origem"] == "snapshot · expectativas_us"
    assert by_source["FRED DGS10"]["coleta"] == "2026-10-02T10:00:00Z"


def test_partial_public_refresh_keeps_breakeven_collection_when_endpoint_omits_series():
    activity = pd.DataFrame({"INDPRO": [100.], "CPIAUCSL": [320.], "DGS10": [4.]},
                            index=pd.to_datetime(["2026-09-01"]))
    activity.attrs["coletado_em"] = "2026-10-02T10:00:00Z"
    expectations = pd.DataFrame({"T10YIE": [2.2]}, index=pd.to_datetime(["2026-10-01"]))
    expectations.attrs["coletado_em"] = "2026-10-03T12:00:00Z"
    fresh = pd.DataFrame({"DGS10": [4.1]}, index=pd.to_datetime(["2026-10-02"]))
    snapshots = {"fred_global": activity, "expectativas_us": expectations}
    fn = getattr(carregar_bancada, "__wrapped__", carregar_bancada)
    with patch("utils.macro_research_data._snapshot", side_effect=lambda name: snapshots.get(name, pd.DataFrame())), \
         patch("utils.macro_research_data._bcb", return_value=pd.Series(dtype=float)), \
         patch("utils.macro_research_data._fred", return_value=fresh), \
         patch("utils.macro_research_data.buscar_focus_publico", return_value=pd.DataFrame()):
        result = fn(True)
    us = result["regioes"]["US"]["dados"]
    assert us.loc["2026-10-01", "T10YIE"] == 2.2
    by_source = {row["fonte"]: row for row in result["qualidade"]}
    assert by_source["FRED T10YIE"]["coleta"] == "2026-10-03T12:00:00Z"
    assert by_source["FRED T10YIE"]["origem"] == "snapshot · expectativas_us"
    assert by_source["FRED DGS10"]["origem"] == "consulta pública · FRED"
    assert by_source["FRED DGS10"]["referência"] == "02/10/2026"
