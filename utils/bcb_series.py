"""Leitor público SGS compartilhado pelo ETL e pelos gráficos macro."""

import datetime as dt

import pandas as pd


def buscar_serie_bcb(codigo: int, nome: str, inicio: dt.date, fim: dt.date) -> pd.Series:
    """SGS público com timeout, retry limitado e janelas diárias menores.

    O BCB limita consultas diárias a dez anos. Janelas de até cinco anos
    também evitam respostas lentas observadas no histórico diário SGS432.
    A série só é retornada depois de todas as janelas válidas; uma falha
    nunca publica apenas parte da coluna como se fosse o histórico completo.
    """
    import math
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    if inicio > fim:
        raise ValueError("Intervalo SGS invertido")
    retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    partes = []
    comeco = inicio
    with requests.Session() as sessao:
        sessao.mount("https://api.bcb.gov.br/", HTTPAdapter(max_retries=retry))
        while comeco <= fim:
            # Intervalos inclusivos, sem repetir nem perder o dia entre janelas.
            limite = (pd.Timestamp(comeco) + pd.DateOffset(years=5)).date()
            final = min(fim, limite) if codigo in {1, 11, 432} else fim
            resposta = sessao.get(
                f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados",
                params={"formato": "json", "dataInicial": comeco.strftime("%d/%m/%Y"),
                        "dataFinal": final.strftime("%d/%m/%Y")}, timeout=(10, 20))
            resposta.raise_for_status()
            registros = resposta.json()
            if not isinstance(registros, list) or not registros:
                raise ValueError(f"SGS{codigo} sem observações no intervalo solicitado")
            frame = pd.DataFrame(registros)
            if not {"data", "valor"} <= set(frame.columns):
                raise ValueError(f"SGS{codigo} sem colunas de data/valor")
            datas = pd.to_datetime(frame["data"], format="%d/%m/%Y", errors="raise")
            valores = pd.to_numeric(frame["valor"].astype(str).str.replace(",", ".", regex=False), errors="raise")
            if not valores.map(math.isfinite).all():
                raise ValueError(f"SGS{codigo} retornou valores não finitos")
            serie = pd.Series(valores.to_numpy(dtype=float), index=datas, name=nome)
            # SGS mensal filtra por mês e pode devolver01/MM quando início foi05/MM.
            menor_data = pd.Timestamp(comeco) if codigo in {1, 11, 432} else pd.Timestamp(comeco).to_period("M").start_time
            if not serie.index.to_series().between(menor_data, pd.Timestamp(final)).all():
                raise ValueError(f"SGS{codigo} retornou observações fora do intervalo")
            if serie.index.has_duplicates:
                if serie.groupby(level=0).nunique().gt(1).any():
                    raise ValueError(f"SGS{codigo} retornou valores conflitantes para a mesma data")
                serie = serie.loc[~serie.index.duplicated(keep="last")]
            partes.append(serie)
            comeco = final + dt.timedelta(days=1)
    return pd.concat(partes).sort_index()

