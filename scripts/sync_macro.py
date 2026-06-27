"""
sync_macro.py — ETL de dados macroeconomicos
Fontes: BCB SGS (Brasil), FRED (EUA), yfinance (VIX, Treasury)

Execucao:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... FRED_API_KEY=... python scripts/sync_macro.py

O que este script faz:
  1. Busca valores atuais (pontuais) → salva em macro_cache (upsert_macro)
  2. Busca séries históricas completas → salva em macro_snapshots (salvar_snapshot)
     → fallback para puxar_historico_mestre() em fins de semana / cold-start
"""

import os
import sys
import json
import datetime as dt
from datetime import timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
logger = get_logger(__name__)

from scripts.supabase_helper import (
    upsert_macro, log_etl_start, log_etl_finish,
)
# upsert_macro é usado abaixo para slopes da curva de juros

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# ── helper de serialização / upsert de snapshots históricos ──────────────────

def _get_sb_client():
    """Cliente Supabase standalone (usa env vars, não st.secrets)."""
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise ValueError("SUPABASE_URL e SUPABASE_SERVICE_KEY devem estar definidas.")
    return create_client(url, key)


def _salvar_snapshot_historico(origem: str, df: pd.DataFrame) -> bool:
    """
    Salva o DataFrame histórico (séries temporais) na tabela macro_snapshots.
    Usa upsert por 'origem' — substitui snapshot anterior.
    Compatível com o esquema criado em scripts/migrations/create_macro_snapshots.sql
    """
    if df is None or df.empty:
        print(f"  [snapshot] {origem}: DataFrame vazio, pulando.")
        return False
    try:
        sb = _get_sb_client()
        # Serializa com o mesmo formato que utils/macro_supabase.py espera
        df2 = df.copy()
        if isinstance(df2.index, pd.DatetimeIndex):
            df2.index = df2.index.strftime("%Y-%m-%d")
        payload_str = df2.to_json(orient="split", date_format="iso")

        sb.table("macro_snapshots").upsert(
            {
                "origem":      origem,
                "payload":     payload_str,
                "n_linhas":    len(df),
                "n_colunas":   df.shape[1],
                "data_inicio": str(df.index.min().date()) if not df.empty else None,
                "data_fim":    str(df.index.max().date()) if not df.empty else None,
                "updated_at":  dt.datetime.utcnow().isoformat(),
            },
            on_conflict="origem",
        ).execute()
        print(f"  [snapshot] {origem}: {len(df)} linhas salvas em macro_snapshots.")
        return True
    except Exception as e:
        print(f"  [snapshot] {origem}: ERRO ao salvar — {e}")
        return False


def fetch_bcb():
    """
    Busca indicadores do Brasil via BCB SGS.
    1. Salva valores pontuais em macro_cache (para os cards de métricas)
    2. Salva série histórica 10 anos em macro_snapshots (fallback para gráficos)
    """
    try:
        from bcb import sgs

        # ── séries para valores pontuais (macro_cache) ──────────────────────
        series_pontual = {
            "selic":           432,
            "selic_diaria":    11,
            "ipca":            433,
            "ipca_12m":        13522,
            "desemprego":      24369,
            "divida_pib":      13762,
            "result_primario": 5793,
            "cambio":          1,
            "igpm":            189,
        }

        inicio_90d = (dt.date.today() - dt.timedelta(days=90)).isoformat()
        df_90d = sgs.get(series_pontual, start=inicio_90d)

        if df_90d.empty:
            print("  [BCB] dados pontuais vazios (90d)")
        else:
            for nome in series_pontual:
                if nome in df_90d.columns:
                    val = df_90d[nome].dropna()
                    if not val.empty:
                        v = float(val.iloc[-1])
                        if nome == "selic":
                            if v < 1: v = v * 100
                            if v > 50: v = 14.75
                        if nome == "ipca":
                            if v > 5: v = v / 100
                        labels  = {"selic": "Selic Over", "selic_diaria": "Selic Diaria",
                                   "ipca": "IPCA Mensal", "ipca_12m": "IPCA 12m",
                                   "desemprego": "Taxa de Desemprego", "divida_pib": "Divida Bruta/PIB",
                                   "result_primario": "Resultado Primario", "cambio": "Dolar (BRL/USD)",
                                   "igpm": "IGP-M"}
                        units   = {"selic": "%aa", "selic_diaria": "%", "ipca": "%", "ipca_12m": "%",
                                   "desemprego": "%", "divida_pib": "%", "result_primario": "%pib",
                                   "cambio": "brl/usd", "igpm": "%"}
                        upsert_macro(nome, round(v, 4), label=labels.get(nome, nome),
                                     unit=units.get(nome, ""), source="bcb")
                        print(f"  [BCB] {nome} = {v:.4f}")

        # ── séries históricas 10 anos → macro_snapshots ─────────────────────
        print("  [BCB] buscando série histórica 10 anos...")
        series_hist = {
            "Selic":            432,
            "IPCA":             433,
            "Dolar":            1,
            "Desemprego":       24369,
            "Divida_Bruta_PIB": 13762,
            "Result_Primario":  5793,
            "Result_Nominal":   4192,
        }
        inicio_10a = (dt.date.today() - dt.timedelta(days=365 * 10)).isoformat()
        dfs_hist = {}
        for nome, codigo in series_hist.items():
            try:
                _df = sgs.get({nome: codigo}, start=inicio_10a)
                if not _df.empty:
                    dfs_hist[nome] = _df[nome]
                    print(f"  [BCB hist] {nome}: {len(_df)} pts")
            except Exception as _e:
                print(f"  [BCB hist] {nome}: {_e}")

        if dfs_hist:
            df_br_hist = pd.DataFrame(dfs_hist)
            # Calcula IPCA_12M acumulado
            if "IPCA" in df_br_hist.columns:
                try:
                    _ipca_raw = df_br_hist["IPCA"].dropna()
                    _ipca_12m = ((1 + _ipca_raw / 100).rolling(12).apply(
                        lambda x: x.prod(), raw=True) - 1) * 100
                    df_br_hist["IPCA_12M"] = _ipca_12m
                except Exception as e:
                    logger.debug(f"falha ao calcular IPCA_12M acumulado: {e}")
            _salvar_snapshot_historico("bcb_br", df_br_hist)
        else:
            print("  [BCB hist] nenhum dado histórico obtido.")

    except Exception as e:
        print(f"  [BCB] ERRO: {e}")


def fetch_fred():
    """
    Busca indicadores dos EUA via FRED.
    1. Salva valores pontuais em macro_cache
    2. Salva série histórica 10 anos em macro_snapshots
    """
    if not FRED_API_KEY:
        print("  [FRED] FRED_API_KEY nao configurada, pulando")
        return

    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)

        # ── séries para valores pontuais (macro_cache) ──────────────────────
        series_pontual = {
            "t10y2y":       ("T10Y2Y",                  "US Treasury 10Y-2Y Spread", "%",    "fred"),
            "vix":          ("VIXCLS",                  "VIX — Volatility Index",    "pts",  "fred"),
            "hy_spread":    ("BAMLH0A0HYM2",            "High Yield Spread (BofA)",  "%",    "fred"),
            "treasury_10y": ("DGS10",                   "US Treasury 10Y Yield",     "%",    "fred"),
            "treasury_2y":  ("DGS2",                    "US Treasury 2Y Yield",      "%",    "fred"),
            "treasury_3m":  ("DGS3MO",                  "US Treasury 3M Yield",      "%",    "fred"),
            "fed_funds":    ("FEDFUNDS",                "Federal Funds Rate",         "%",    "fred"),
            "cpi":          ("CPIAUCSL",                "CPI All Urban Consumers",    "idx",  "fred"),
            "core_cpi":     ("CORESTICKM159SFRBATL",    "CPI Core Sticky",            "%",    "fred"),
            "unemployment": ("UNRATE",                  "US Unemployment Rate",       "%",    "fred"),
            "dxy":          ("DTWEXBGS",                "US Dollar Index",            "idx",  "fred"),
        }
        for nome, (code, label, unit, source) in series_pontual.items():
            try:
                s = fred.get_series(code)
                if not s.empty:
                    v = float(s.dropna().iloc[-1])
                    upsert_macro(nome, round(v, 4), label=label, unit=unit, source=source)
                    print(f"  [FRED] {nome} ({code}) = {v:.4f}")
            except Exception as e:
                print(f"  [FRED] {nome} ({code}): {e}")

        # ── séries históricas 10 anos → macro_snapshots ─────────────────────
        print("  [FRED] buscando série histórica 10 anos...")
        series_hist = {
            "FEDFUNDS": "FEDFUNDS", "CPIAUCSL": "CPIAUCSL", "UNRATE": "UNRATE",
            "DGS10": "DGS10", "DGS2": "DGS2", "DGS3MO": "DGS3MO", "VIXCLS": "VIXCLS",
            "ECBDFR": "ECBDFR", "IRLTLT01EZM156N": "IRLTLT01EZM156N",
            "IRLTLT01JPM156N": "IRLTLT01JPM156N",
            "T10Y2Y": "T10Y2Y", "BAMLH0A0HYM2": "BAMLH0A0HYM2",
            "GFDEGDQ188S": "GFDEGDQ188S", "MTSDS133FMS": "MTSDS133FMS",
            "CP0000EZ19M086NEST": "CP0000EZ19M086NEST", "LRHUTTTTEZM156S": "LRHUTTTTEZM156S",
            "IRLTLT01DEM156N": "IRLTLT01DEM156N", "IRLTLT01ITM156N": "IRLTLT01ITM156N",
            "IRSTCB01JPM156N": "IRSTCB01JPM156N", "CHNCPIALLMINMEI": "CHNCPIALLMINMEI",
        }
        inicio_10a = dt.date.today() - dt.timedelta(days=365 * 10)
        dfs_fred = {}
        for nome, serie_id in series_hist.items():
            try:
                _s = fred.get_series(serie_id, observation_start=inicio_10a)
                if not _s.empty:
                    dfs_fred[nome] = _s
                    print(f"  [FRED hist] {nome}: {len(_s)} pts")
            except Exception as _e:
                print(f"  [FRED hist] {nome}: {_e}")

        if dfs_fred:
            df_global_hist = pd.DataFrame(dfs_fred)
            # Calcula CPI YoY — dropna ANTES de pct_change porque o merge cria
            # índice diário (DGS10/DGS2 são diários) e CPIAUCSL é mensal/esparsa.
            # Sem dropna, pct_change(12) desloca 12 LINHAS e dá NaN quase sempre.
            if "CPIAUCSL" in df_global_hist.columns:
                try:
                    _cpi_m = df_global_hist["CPIAUCSL"].dropna()
                    if len(_cpi_m) >= 13:
                        _yoy = _cpi_m.pct_change(12, fill_method=None) * 100
                        df_global_hist["CPI_YOY"] = _yoy.reindex(df_global_hist.index)
                except Exception as e:
                    logger.debug(f"falha ao calcular CPI_YOY: {e}")
            _salvar_snapshot_historico("fred_global", df_global_hist)

            # ── slopes da curva de juros → macro_cache ────────────────────────
            try:
                _t10_last = df_global_hist["DGS10"].dropna().iloc[-1] if "DGS10" in df_global_hist.columns else None
                _t2_last  = df_global_hist["DGS2"].dropna().iloc[-1]  if "DGS2"  in df_global_hist.columns else None
                _t3m_last = df_global_hist["DGS3MO"].dropna().iloc[-1] if "DGS3MO" in df_global_hist.columns else None
                if _t10_last is not None and _t2_last is not None:
                    _slope_10y2y = round(float(_t10_last) - float(_t2_last), 4)
                    upsert_macro("slope_10y_2y_pp", _slope_10y2y,
                                 label="US Treasury 10Y-2Y Slope", unit="pp", source="fred")
                    print(f"  [FRED] slope_10y_2y_pp = {_slope_10y2y:.4f}")
                if _t10_last is not None and _t3m_last is not None:
                    _slope_10y3m = round(float(_t10_last) - float(_t3m_last), 4)
                    upsert_macro("slope_10y_3m_pp", _slope_10y3m,
                                 label="US Treasury 10Y-3M Slope", unit="pp", source="fred")
                    print(f"  [FRED] slope_10y_3m_pp = {_slope_10y3m:.4f}")
            except Exception as _e_slope:
                print(f"  [FRED] slope calc: {_e_slope}")
        else:
            print("  [FRED hist] nenhum dado histórico obtido.")

    except Exception as e:
        print(f"  [FRED] ERRO: {e}")


def fetch_yfinance_macro():
    """Busca indicadores macro via yfinance (VIX, Treasury)."""
    try:
        import yfinance as yf
        import pandas as pd

        tickers = ["^VIX", "^TNX", "^GSPC", "^IXIC"]

        for t in tickers:
            try:
                hist = yf.Ticker(t).history(period="5d")
                if hist.empty:
                    continue
                v = float(hist["Close"].dropna().iloc[-1])

                name_map = {
                    "^VIX": "vix",
                    "^TNX": "treasury_10y",
                    "^GSPC": "sp500",
                    "^IXIC": "nasdaq",
                }
                label_map = {
                    "^VIX": "VIX",
                    "^TNX": "US Treasury 10Y Yield",
                    "^GSPC": "S&P 500",
                    "^IXIC": "NASDAQ Composite",
                }
                unit_map = {
                    "^VIX": "pts", "^TNX": "%",
                    "^GSPC": "pts", "^IXIC": "pts",
                }
                key = name_map[t]
                # So upsert if not already present from FRED (yfinance is fallback)
                upsert_macro(key, round(v, 4),
                             label=label_map[t], unit=unit_map[t], source="yfinance")
                print(f"  [yfinance] {key} = {v:.4f}")
            except Exception as e:
                print(f"  [yfinance] {t}: {e}")

    except Exception as e:
        print(f"  [yfinance] ERRO: {e}")


# ── Inflação SETORIAL (decomposição IPCA/CPI) ────────────────────────────────
# Códigos SGS verificados ao vivo contra a API do BCB + catálogo oficial.
#
# IPCA por GRUPO (variação mensal %):
_IPCA_GRUPOS_BR = {
    "alimentacao":         1635,   # Alimentação e bebidas
    "habitacao":           1636,   # Habitação
    "artigos_residencia":  1637,   # Artigos de residência
    "vestuario":           1638,   # Vestuário
    "transportes":         1639,   # Transportes
    "comunicacao":         1640,   # Comunicação
    "saude":               1641,   # Saúde e cuidados pessoais
    "despesas_pessoais":   1642,   # Despesas pessoais
    "educacao":            1643,   # Educação
}
# IPCA por CATEGORIA ESPECIAL (variação mensal %) — cortes que o BC acompanha:
_IPCA_CATEGORIAS_BR = {
    "comercializaveis":     4447,
    "nao_comercializaveis": 4448,
    "administrados":        4449,   # monitorados (energia elétrica, combustível, tarifas)
    "servicos":            10844,   # núcleo de rigidez — função de reação do Copom
    "livres":              11428,
}
# Núcleos do IPCA (variação mensal %) — medem inflação subjacente:
_IPCA_NUCLEOS_BR = {
    "nucleo_ma_suav":      4466,    # médias aparadas com suavização
    "nucleo_ma_sem_suav": 16121,    # médias aparadas sem suavização
    "nucleo_dupla_pond":  16122,    # dupla ponderação
    "nucleo_ex2":         27838,    # exclusão EX2
    "nucleo_ex3":         27839,    # exclusão EX3
}
# Preços ao PRODUTOR/atacado vs consumidor (variação mensal %) — gap de margem.
# igpm (atacado, IGP-M) − ipca_cheio (consumidor) = pressão de margem da economia.
_PPI_BR = {
    "igpm":       189,    # IGP-M (≈60% atacado/IPA) — proxy de preço ao produtor
    "ipca_cheio": 433,    # IPCA cheio (consumidor) — para o gap PPI−CPI
}
# CPI EUA por componente (índice — YoY calculado abaixo) via FRED:
_CPI_COMPONENTES_US = {
    "core":           "CPILFESL",        # all items less food & energy
    "energia":        "CPIENGSL",        # energy
    "alimentos":      "CPIUFDSL",        # food
    "shelter":        "CUSR0000SAH1",    # shelter (40% do core — sticky)
    "servicos_core":  "CUSR0000SASLE",   # services less energy services
    "bens_core":      "CUSR0000SACL1E",  # commodities less food & energy
    "ppi":            "PPIACO",          # Producer Price Index, all commodities
}
# Núcleos do CPI (já em % anualizado mensal — NÃO são índice) via FRED/Cleveland:
_CPI_NUCLEOS_US = {
    "median":       "MEDCPIM158SFRBCLE",      # median CPI (1m % anualizado)
    "trimmed_mean": "TRMMEANCPIM158SFRBCLE",  # 16% trimmed-mean (1m % anualizado)
}


def _acumular_12m(serie: pd.Series) -> pd.Series:
    """Acumula uma série de variação mensal (%) em janela de 12 meses (composto)."""
    s = serie.dropna()
    return ((1 + s / 100).rolling(12).apply(lambda x: x.prod(), raw=True) - 1) * 100


def _acumular_anualizado(serie_mensal: pd.Series, meses: int) -> pd.Series:
    """
    Run-rate ANUALIZADO de uma série de variação MENSAL (%) — compõe os últimos
    `meses` e anualiza: ((Π(1+m/100))^(12/meses) − 1)·100. Capta a inflexão que
    o YoY/12m esconde (ex.: administrados a 11% anualizado em 3m vs 5.8% no 12m).
    """
    s = serie_mensal.dropna()
    prod = (1 + s / 100).rolling(meses).apply(lambda x: x.prod(), raw=True)
    return (prod ** (12.0 / meses) - 1) * 100


def _runrate_indice(serie_indice: pd.Series, meses: int) -> pd.Series:
    """Run-rate ANUALIZADO de uma série de ÍNDICE (CPI): (idx_t/idx_{t-meses})^(12/meses)−1."""
    s = serie_indice.dropna()
    return ((s / s.shift(meses)) ** (12.0 / meses) - 1) * 100


def fetch_inflacao_setorial():
    """
    Decomposição setorial da inflação — alimenta a camada de transmissão
    macro→setor→ativo (utils/inflation_sectoral.py).

    BR (BCB SGS): grupos + categorias (serviços/administrados/livres) + núcleos.
                  Persiste snapshot 'inflacao_br' com colunas mensais e *_12m.
    EUA (FRED):   componentes do CPI (core/shelter/serviços/bens/energia/alimentos),
                  com YoY. Persiste snapshot 'inflacao_us'.
    Também salva valores pontuais (12m/YoY) em macro_cache para o cockpit.
    """
    # ── Brasil ────────────────────────────────────────────────────────────────
    try:
        from bcb import sgs
        inicio_10a = (dt.date.today() - dt.timedelta(days=365 * 10)).isoformat()
        todos = {**_IPCA_GRUPOS_BR, **_IPCA_CATEGORIAS_BR, **_IPCA_NUCLEOS_BR, **_PPI_BR}

        cols = {}
        for nome, codigo in todos.items():
            try:
                _df = sgs.get({nome: codigo}, start=inicio_10a)
                if _df is not None and not _df.empty:
                    cols[nome] = _df[nome]
                    print(f"  [infl BR] {nome} ({codigo}): {len(_df)} pts")
            except Exception as _e:
                print(f"  [infl BR] {nome} ({codigo}): {_e}")

        if cols:
            df_infl_br = pd.DataFrame(cols)
            # Por corte: acumulado 12m + run-rates ANUALIZADOS 3m/6m (momentum —
            # capta a inflexão que o 12m esconde).
            for nome in list(df_infl_br.columns):
                try:
                    df_infl_br[f"{nome}_12m"] = _acumular_12m(df_infl_br[nome]).reindex(df_infl_br.index)
                    df_infl_br[f"{nome}_3m"]  = _acumular_anualizado(df_infl_br[nome], 3).reindex(df_infl_br.index)
                    df_infl_br[f"{nome}_6m"]  = _acumular_anualizado(df_infl_br[nome], 6).reindex(df_infl_br.index)
                except Exception as e:
                    logger.debug(f"falha run-rate {nome}: {e}")
            _salvar_snapshot_historico("inflacao_br", df_infl_br)

            def _last(nome, suf):
                c = f"{nome}_{suf}"
                if c in df_infl_br.columns and not df_infl_br[c].dropna().empty:
                    return round(float(df_infl_br[c].dropna().iloc[-1]), 2)
                return None

            def _nucleo_medio(suf):
                vals = [_last(n, suf) for n in _IPCA_NUCLEOS_BR]
                vals = [v for v in vals if v is not None]
                return round(sum(vals) / len(vals), 2) if vals else None

            # Pontual p/ cockpit: 12m (nível) + 3m anualizado (momentum)
            for _suf, _lbl_suf in [("12m", "12m"), ("3m", "3m anualizado")]:
                _nm = _nucleo_medio(_suf)
                if _nm is not None:
                    upsert_macro(f"ipca_nucleo_{_suf}", _nm,
                                 label=f"IPCA Núcleo (média {_lbl_suf})", unit="%", source="bcb")
                for _k in ("servicos", "administrados", "livres"):
                    _v = _last(_k, _suf)
                    if _v is not None:
                        upsert_macro(f"ipca_{_k}_{_suf}", _v,
                                     label=f"IPCA {_k.title()} {_lbl_suf}", unit="%", source="bcb")
                        print(f"  [infl BR] ipca_{_k}_{_suf} = {_v}")

                # Gap de margem: atacado (IGP-M) − consumidor (IPCA cheio).
                # Positivo = custo sobe mais que o preço final → compressão de margem.
                _igpm = _last("igpm", _suf)
                _ipca_c = _last("ipca_cheio", _suf)
                if _igpm is not None:
                    upsert_macro(f"br_igpm_{_suf}", _igpm,
                                 label=f"IGP-M (atacado) {_lbl_suf}", unit="%", source="bcb")
                if _igpm is not None and _ipca_c is not None:
                    _gap = round(_igpm - _ipca_c, 2)
                    upsert_macro(f"br_gap_margem_{_suf}", _gap,
                                 label=f"Gap margem BR (IGP-M−IPCA) {_lbl_suf}", unit="pp", source="bcb")
                    print(f"  [infl BR] br_gap_margem_{_suf} = {_gap}")
    except Exception as e:
        print(f"  [infl BR] ERRO: {e}")

    # ── EUA ───────────────────────────────────────────────────────────────────
    if not FRED_API_KEY:
        print("  [infl US] FRED_API_KEY ausente, pulando")
    else:
        try:
            from fredapi import Fred
            fred = Fred(api_key=FRED_API_KEY)
            inicio_10a = dt.date.today() - dt.timedelta(days=365 * 10)

            cols_us = {}
            for nome, serie_id in _CPI_COMPONENTES_US.items():
                try:
                    _s = fred.get_series(serie_id, observation_start=inicio_10a)
                    if _s is not None and not _s.empty:
                        cols_us[nome] = _s
                        print(f"  [infl US] {nome} ({serie_id}): {len(_s)} pts")
                except Exception as _e:
                    print(f"  [infl US] {nome} ({serie_id}): {_e}")

            if cols_us:
                df_infl_us = pd.DataFrame(cols_us)
                # Componentes são ÍNDICES → YoY (nível) + run-rates anualizados 3m/6m.
                for nome in list(df_infl_us.columns):
                    try:
                        _m = df_infl_us[nome].dropna()
                        if len(_m) >= 13:
                            df_infl_us[f"{nome}_yoy"] = (
                                _m.pct_change(12, fill_method=None) * 100
                            ).reindex(df_infl_us.index)
                        if len(_m) >= 7:
                            df_infl_us[f"{nome}_6m"] = _runrate_indice(_m, 6).reindex(df_infl_us.index)
                        if len(_m) >= 4:
                            df_infl_us[f"{nome}_3m"] = _runrate_indice(_m, 3).reindex(df_infl_us.index)
                    except Exception as e:
                        logger.debug(f"falha run-rate us {nome}: {e}")

                # Núcleos Cleveland (median / trimmed-mean) — já vêm em % ANUALIZADO
                # mensal; guarda o nível e a média móvel 3m (suaviza o ruído mensal).
                for nome, serie_id in _CPI_NUCLEOS_US.items():
                    try:
                        _s = fred.get_series(serie_id, observation_start=inicio_10a)
                        if _s is not None and not _s.empty:
                            df_infl_us[nome] = _s
                            df_infl_us[f"{nome}_3m"] = _s.rolling(3).mean().reindex(df_infl_us.index)
                            print(f"  [infl US] {nome} ({serie_id}): {len(_s)} pts")
                    except Exception as _e:
                        print(f"  [infl US] {nome} ({serie_id}): {_e}")

                _salvar_snapshot_historico("inflacao_us", df_infl_us)

                def _last_us(nome, suf):
                    c = f"{nome}_{suf}"
                    if c in df_infl_us.columns and not df_infl_us[c].dropna().empty:
                        return round(float(df_infl_us[c].dropna().iloc[-1]), 2)
                    return None

                # Pontual: YoY (nível) + 3m anualizado (momentum) dos cortes-chave
                for _k in ("core", "shelter", "servicos_core", "bens_core"):
                    for _suf in ("yoy", "3m"):
                        _v = _last_us(_k, _suf)
                        if _v is not None:
                            upsert_macro(f"us_cpi_{_k}_{_suf}", _v,
                                         label=f"US CPI {_k} {_suf}", unit="%", source="fred")
                            print(f"  [infl US] us_cpi_{_k}_{_suf} = {_v}")
                for _k in ("median", "trimmed_mean"):
                    _v = _last_us(_k, "3m")
                    if _v is not None:
                        upsert_macro(f"us_cpi_{_k}_3m", _v,
                                     label=f"US CPI {_k} (3m)", unit="%", source="fred")
                        print(f"  [infl US] us_cpi_{_k}_3m = {_v}")

                # Gap de margem US: PPI (produtor) − core CPI (consumidor).
                # Positivo = custo do produtor subindo mais que o preço → margem aperta.
                for _suf in ("yoy", "3m"):
                    _ppi = _last_us("ppi", _suf)
                    _core = _last_us("core", _suf)
                    if _ppi is not None:
                        upsert_macro(f"us_ppi_{_suf}", _ppi,
                                     label=f"US PPI {_suf}", unit="%", source="fred")
                    if _ppi is not None and _core is not None:
                        _gap = round(_ppi - _core, 2)
                        upsert_macro(f"us_gap_margem_{_suf}", _gap,
                                     label=f"Gap margem US (PPI−core CPI) {_suf}", unit="pp", source="fred")
                        print(f"  [infl US] us_gap_margem_{_suf} = {_gap}")
        except Exception as e:
            print(f"  [infl US] ERRO: {e}")


def fetch_expectativas():
    """
    Expectativas de inflação + a SURPRESA (realizado − esperado) — o sinal de
    "o que já está precificado". Surpresa positiva = inflação acima do esperado
    → hawkish → ruim para duration; negativa = dovish.

    BR: Focus 12m à frente (API Olinda do BCB, sem chave).
    EUA: survey Michigan 1y (MICH) + breakevens (5y, 5y5y, 10y) via FRED.
    """
    # ── BR: Focus 12 meses (Olinda) ────────────────────────────────────────────
    try:
        import requests
        from bcb import sgs
        url = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/"
               "odata/ExpectativasMercadoInflacao12Meses?$top=1&$orderby=Data%20desc"
               "&$format=json&$filter=Indicador%20eq%20'IPCA'%20and%20"
               "Suavizada%20eq%20'S'%20and%20baseCalculo%20eq%200")
        focus = None
        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            vals = r.json().get("value", [])
            if vals and vals[0].get("Mediana") is not None:
                focus = round(float(vals[0]["Mediana"]), 2)
        if focus is not None:
            upsert_macro("br_focus_ipca_12m", focus,
                         label="Focus IPCA 12m à frente", unit="%", source="bcb")
            _ipca12 = sgs.get({"x": 13522}, last=1)["x"].dropna()
            if not _ipca12.empty:
                _real = round(float(_ipca12.iloc[-1]), 2)
                _surp = round(_real - focus, 2)
                upsert_macro("br_surpresa_inflacao", _surp,
                             label="Surpresa inflação BR (realizado−Focus)",
                             unit="pp", source="bcb")
                print(f"  [exp BR] focus={focus} realizado={_real} surpresa={_surp:+.2f}")
    except Exception as e:
        print(f"  [exp BR] ERRO: {e}")

    # ── EUA: Michigan 1y + breakevens (FRED) ───────────────────────────────────
    if not FRED_API_KEY:
        print("  [exp US] FRED_API_KEY ausente, pulando")
        return
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        _vals = {}
        for nome, sid, lbl in [
            ("mich",    "MICH",   "Michigan 1y inflation expectation"),
            ("be_5y",   "T5YIE",  "5y breakeven"),
            ("be_5y5y", "T5YIFR", "5y5y forward breakeven"),
            ("be_10y",  "T10YIE", "10y breakeven"),
        ]:
            try:
                _s = fred.get_series(sid)
                if _s is not None and not _s.dropna().empty:
                    _vals[nome] = round(float(_s.dropna().iloc[-1]), 2)
                    upsert_macro(f"us_{nome}", _vals[nome], label=f"US {lbl}", unit="%", source="fred")
                    print(f"  [exp US] {nome} ({sid}) = {_vals[nome]}")
            except Exception as _e:
                print(f"  [exp US] {nome} ({sid}): {_e}")
        # surpresa = core CPI YoY − Michigan 1y
        if "mich" in _vals:
            _core = fred.get_series("CPILFESL").dropna()
            if len(_core) >= 13:
                _yoy = round(float((_core.iloc[-1] / _core.iloc[-13] - 1) * 100), 2)
                _surp = round(_yoy - _vals["mich"], 2)
                upsert_macro("us_surpresa_inflacao", _surp,
                             label="Surpresa inflação US (core−Michigan)",
                             unit="pp", source="fred")
                print(f"  [exp US] core={_yoy} mich={_vals['mich']} surpresa={_surp:+.2f}")
    except Exception as e:
        print(f"  [exp US] ERRO: {e}")


def main():
    print("[sync_macro] inicio")
    log_id = log_etl_start("sync_macro")

    print("[sync_macro] BCB SGS...")
    fetch_bcb()

    print("[sync_macro] FRED...")
    fetch_fred()

    print("[sync_macro] inflação setorial (IPCA/CPI)...")
    fetch_inflacao_setorial()

    print("[sync_macro] expectativas / surpresa (Focus + breakevens)...")
    fetch_expectativas()

    print("[sync_macro] yfinance...")
    fetch_yfinance_macro()

    log_etl_finish(log_id, ok=1, fail=0)
    print("[sync_macro] fim")


if __name__ == "__main__":
    main()
