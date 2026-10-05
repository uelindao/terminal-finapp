"""Cache-first public data adapters for the macro research workbench.

No credentials are fetched here. Streamlit uses its existing snapshot adapter.
Public requests are opt-in from the interface and reused by the scheduled ETL.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import StringIO, BytesIO
from zipfile import ZipFile, is_zipfile
from urllib.parse import quote, urlencode

import pandas as pd
import requests
import streamlit as st

from utils.macro_research import normalizar_focus
from utils.logger import get_logger

logger = get_logger(__name__)
FOCUS_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def focus_url(endpoint: str, params: dict) -> str:
    # Olinda rejects '+' for spaces in OData expressions.
    return FOCUS_BASE + endpoint + "?" + urlencode(params, quote_via=quote)


def buscar_focus_publico(dias: int = 420) -> pd.DataFrame:
    start = (date.today() - timedelta(days=dias)).isoformat()
    queries = [
        ("ExpectativasMercadoInflacao12Meses", "12m",
         f"Indicador eq 'IPCA' and baseCalculo eq 0 and Data ge '{start}' and Suavizada eq 'N'", 1000),
        ("ExpectativasMercadoAnuais", "anual",
         f"(Indicador eq 'IPCA' or Indicador eq 'Selic' or Indicador eq 'PIB Total' or Indicador eq 'Câmbio') and baseCalculo eq 0 and Data ge '{start}'", 6000),
    ]
    def get(query):
        endpoint, kind, filter_, cap = query
        response = requests.get(focus_url(endpoint, {"$filter": filter_, "$top": cap,
                                                   "$orderby": "Data desc", "$format": "json"}), timeout=20)
        response.raise_for_status()
        result = normalizar_focus(response.json().get("value", []), tipo=kind)
        result.attrs["limitado"] = len(response.json().get("value", [])) >= cap
        return result
    pieces, warnings = [], []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(get, query) for query in queries]
        for query, future in zip(queries, futures):
            try:
                part = future.result()
                if part.attrs.get("limitado"):
                    warnings.append("Histórico Focus limitado aos registros mais recentes retornados pela API.")
                pieces.append(part)
            except Exception as exc:
                logger.warning("[macro_research] Focus %s: %s", query[1], type(exc).__name__)
                warnings.append(f"Focus {query[1]} indisponível nesta consulta.")
    frame = pd.concat(pieces, ignore_index=True) if pieces else normalizar_focus([], tipo="anual")
    frame.attrs.update(fonte="BCB Focus/OData", avisos=warnings,
                       coletado_em=pd.Timestamp.now(tz="UTC").isoformat(),
                       metodologia="Medianas base 0; 12m não suavizada; anos de referência mantidos.")
    return frame


def mesclar_focus(cache: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """Merge surveys by reference identity without inventing missing history.

    A partial response for 12m cannot discard the cached annual survey, and
    the fresh response takes precedence only for the same date and target.
    """
    pieces = [frame for frame in (cache, fresh) if frame is not None and not frame.empty]
    if not pieces:
        return normalizar_focus([], tipo="anual")
    frame = pd.concat(pieces, ignore_index=True)
    frame["data"] = pd.to_datetime(frame["data"], errors="coerce", utc=True).dt.tz_convert(None)
    frame["horizonte"] = frame["horizonte"].astype(str)
    frame["mediana"] = pd.to_numeric(frame["mediana"], errors="coerce")
    frame = frame.dropna(subset=["data", "indicador", "horizonte", "mediana"])
    frame = frame.drop_duplicates(["data", "indicador", "horizonte"], keep="last").sort_values("data")
    frame.attrs.update(fresh.attrs if fresh is not None else {})
    return frame.reset_index(drop=True)


def _bcb(code: int, years: int = 10) -> pd.Series:
    end = date.today()
    params = {"formato": "json", "dataInicial": (end - timedelta(days=365 * years)).strftime("%d/%m/%Y"),
              "dataFinal": end.strftime("%d/%m/%Y")}
    response = requests.get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados", params=params, timeout=15)
    response.raise_for_status()
    frame = pd.DataFrame(response.json())
    if frame.empty or not {"data", "valor"}.issubset(frame):
        return pd.Series(dtype=float)
    series = pd.Series(pd.to_numeric(frame["valor"], errors="coerce").to_numpy(),
                       index=pd.to_datetime(frame["data"], dayfirst=True, errors="coerce"))
    return series[~series.index.isna()].sort_index()


def _fred(series_ids: list[str], years: int = 10) -> pd.DataFrame:
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    response = requests.get(FRED_CSV, params={"id": ",".join(series_ids), "cosd": start}, timeout=20)
    response.raise_for_status()

    def parse(data):
        frame = pd.read_csv(data, na_values=["."])
        date_col = next((c for c in ("observation_date", "DATE") if c in frame), None)
        if date_col is None:
            return pd.DataFrame()
        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
        frame = frame.dropna(subset=[date_col]).set_index(date_col)
        frame = frame[[c for c in frame if c in series_ids]]
        return frame.apply(pd.to_numeric, errors="coerce").sort_index()

    payload = BytesIO(response.content)
    if is_zipfile(payload):
        with ZipFile(payload) as archive:
            frames = [parse(BytesIO(archive.read(name))) for name in archive.namelist()
                      if name.lower().endswith(".csv")]
        frames = [f for f in frames if not f.empty]
        frame = pd.concat(frames, axis=1) if frames else pd.DataFrame()
        frame = frame.loc[:, ~frame.columns.duplicated()]
    else:
        frame = parse(StringIO(response.text))
    return frame.loc[frame.index >= pd.Timestamp(start)] if not frame.empty else frame


def _snapshot(source: str) -> pd.DataFrame:
    try:
        from utils.macro_supabase import carregar_snapshot
        frame = carregar_snapshot(source, max_age_days=45)
        return frame.copy() if frame is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_bancada(permitir_rede: bool = False) -> dict:
    br, us, focus = _snapshot("bcb_br"), _snapshot("fred_global"), _snapshot("focus_expectativas")
    origins = {"BR": "snapshot", "US": "snapshot", "Focus": "snapshot"}
    warnings = []
    if not focus.empty:
        if "data" not in focus.columns:
            focus = focus.rename_axis("data").reset_index()
        focus["data"] = pd.to_datetime(focus["data"], errors="coerce")
        for col in ("mediana", "respondentes"):
            if col in focus:
                focus[col] = pd.to_numeric(focus[col], errors="coerce")
        focus = focus.dropna(subset=["data", "mediana"]) if "mediana" in focus else pd.DataFrame()

    if permitir_rede:
        def get_br():
            pieces = {}
            for name, code in {"IBC_Br": 24364, "IPCA": 433, "Selic": 432}.items():
                try:
                    pieces[name] = _bcb(code)
                except Exception:
                    warnings.append(f"Série BR {name} indisponível; mantendo cache quando existente.")
            return pd.DataFrame(pieces)
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = {"BR": pool.submit(get_br),
                    "US": pool.submit(_fred, ["INDPRO", "CPIAUCSL", "DFII10", "DGS10", "DGS2", "T10YIE", "BAMLH0A0HYM2"]),
                    "Focus": pool.submit(buscar_focus_publico)}
            for name, future in jobs.items():
                try:
                    fresh = future.result()
                    if name == "Focus":
                        warnings.extend(fresh.attrs.get("avisos", []))
                    if not fresh.empty:
                        origins[name] = "consulta pública"
                        fresh.attrs["coletado_em"] = pd.Timestamp.now(tz="UTC").isoformat()
                        if name == "BR":
                            br = fresh.combine_first(br)
                            br.attrs.update(fresh.attrs)
                        elif name == "US":
                            us = fresh.combine_first(us)
                            us.attrs.update(fresh.attrs)
                        else:
                            # A failing endpoint cannot erase the other horizon
                            # already available in the snapshot.
                            cached = not focus.empty
                            focus = mesclar_focus(focus, fresh)
                            if cached:
                                origins[name] = "consulta pública + snapshot"
                except Exception:
                    warnings.append(f"Consulta {name} indisponível; mantendo o snapshot quando existente.")

    regions = {}
    quality = []
    for name, frame, activity, inflation, kind, label in [
        ("BR", br, "IBC_Br", "IPCA", "mensal_pct", "IBC-Br com ajuste sazonal"),
        ("US", us, "INDPRO", "CPIAUCSL", "indice", "Produção industrial com ajuste sazonal"),
    ]:
        regions[name] = {"atividade": frame.get(activity, pd.Series(dtype=float)),
                         "inflacao": frame.get(inflation, pd.Series(dtype=float)),
                         "inflacao_tipo": kind, "atividade_label": label,
                         "origem": origins[name], "dados": frame}
        for column, display, source in [(activity, label, "BCB SGS 24364" if name == "BR" else "FRED INDPRO"),
                                         (inflation, "IPCA mensal sem ajuste sazonal" if name == "BR" else "CPI com ajuste sazonal",
                                          "BCB SGS 433" if name == "BR" else "FRED CPIAUCSL")]:
            s = frame.get(column, pd.Series(dtype=float)).dropna()
            quality.append({"região": name, "série": display, "fonte": source,
                            "referência": s.index[-1].strftime("%d/%m/%Y") if not s.empty else "ausente",
                            "coleta": frame.attrs.get("updated_at", frame.attrs.get("coletado_em", "não informada")),
                            "origem": origins[name], "observações": len(s)})
    if focus.empty:
        warnings.append("Expectativas Focus ainda sem snapshot. Atualize as séries para consultar a fonte pública.")
    else:
        quality.append({"região": "BR", "série": "Focus · medianas", "fonte": "BCB OData",
                        "referência": focus["data"].max().strftime("%d/%m/%Y"),
                        "coleta": focus.attrs.get("coletado_em", focus.attrs.get("updated_at", "não informada")),
                        "origem": origins["Focus"], "observações": len(focus)})
    return {"regioes": regions, "focus": focus, "qualidade": quality,
            "avisos": list(dict.fromkeys(warnings)),
            "base_temporal": "Reconstrução por datas de referência e vintage atual; não representa dados conhecidos na época."}
