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
    upsert_macro as _upsert_macro_db, log_etl_start, log_etl_finish,
)
# upsert_macro é usado abaixo para slopes da curva de juros

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

_ETL_GRAVACOES = 0
_ETL_FALHAS = []
_ETL_AVISOS = []


def _registrar_falha(fonte: str, erro):
    item = f"{fonte}: {type(erro).__name__}"
    if item not in _ETL_FALHAS:
        _ETL_FALHAS.append(item)


def upsert_macro(*args, **kwargs):
    """Confirmação de gravações reais; funções de coleta mantêm a mesma API."""
    global _ETL_GRAVACOES
    try:
        _upsert_macro_db(*args, **kwargs)
        _ETL_GRAVACOES += 1
    except Exception as exc:
        _registrar_falha("persistencia_macro", exc)
        raise


def _persistir_versionado(origem: str, df: pd.DataFrame):
    """Inicializa auditoria prospectiva; ausência da migration é aviso explícito."""
    from utils.macro_supabase import salvar_observacoes_versionadas
    cliente = _get_sb_client()
    if origem == "focus_expectativas":
        for (indicador, horizonte), grupo in df.groupby(["indicador", "horizonte"]):
            resultado = salvar_observacoes_versionadas(f"{origem}:{indicador}:{horizonte}",
                pd.to_numeric(grupo["mediana"], errors="coerce"), fonte="BCB Focus",
                unidade="mediana conforme indicador", disponibilidade_base="observada_na_coleta", cliente=cliente)
            if not resultado["ok"]:
                aviso = f"historico_versionado: {resultado['motivo']}"
                if aviso not in _ETL_AVISOS:
                    _ETL_AVISOS.append(aviso)
        return
    for coluna in df.columns:
        serie = df[coluna].dropna()
        if serie.empty:
            continue
        mensal = origem in {"inflacao_br", "inflacao_us"} or coluna in {
            "IPCA", "IPCA_12M", "Desemprego", "Divida_Bruta_PIB", "Result_Primario", "Result_Nominal", "IBC_Br",
            "CPIAUCSL", "CPI_YOY", "UNRATE", "FEDFUNDS", "INDPRO", "CP0000EZ19M086NEST", "LRHUTTTTEZM156S",
            "CHNCPIALLMINMEI", "GFDEGDQ188S", "MTSDS133FMS"}
        atraso = 45 if coluna in {"IBC_Br", "INDPRO", "Desemprego", "UNRATE"} else (20 if mensal else 1)
        unidade = "indice" if coluna in {"IBC_Br", "INDPRO", "CPIAUCSL"} else ("%" if coluna in {"Selic", "IPCA", "IPCA_12M", "DGS10", "DGS2", "DGS3MO", "DFII10", "FEDFUNDS"} else "conforme_fonte")
        disponibilidade_base = "observada_na_coleta" if origem.startswith("expectativas_") else "atraso_conservador_assumido"
        resultado = salvar_observacoes_versionadas(f"{origem}:{coluna}", serie, fonte=origem,
            unidade=unidade, atraso_dias=atraso, mes_fechado=mensal, cliente=cliente,
            disponibilidade_base=disponibilidade_base)
        if not resultado["ok"]:
            aviso = f"historico_versionado: {resultado['motivo']}"
            if aviso not in _ETL_AVISOS:
                _ETL_AVISOS.append(aviso)
            if "migration" in resultado["motivo"]:
                break  # uma chamada basta para indicar tabela ainda não instalada


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
                "updated_at":  dt.datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="origem",
        ).execute()
        global _ETL_GRAVACOES
        _ETL_GRAVACOES += 1
        print(f"  [snapshot] {origem}: {len(df)} linhas salvas em macro_snapshots.")
        try:
            _persistir_versionado(origem, df)
        except Exception as exc:
            # Compatibilidade: a auditoria nova não derruba o cache vigente.
            aviso = f"historico_versionado: {type(exc).__name__}"
            if aviso not in _ETL_AVISOS:
                _ETL_AVISOS.append(aviso)
        return True
    except Exception as e:
        _registrar_falha("_salvar_snapshot_historico", e)
        print(f"  [snapshot] {origem}: ERRO ao salvar — {type(e).__name__}")
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
                        if not pd.notna(v) or not __import__("math").isfinite(v):
                            continue
                        if nome == "selic" and not 0 <= v <= 50:
                            raise ValueError("Selic fora da unidade % a.a. informada pelo SGS432")
                        if nome == "ipca" and not -10 <= v <= 10:
                            raise ValueError("IPCA mensal fora da unidade % informada pelo SGS433")
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
            "IBC_Br":           24364,  # índice dessazonalizado, catálogo oficial BCB
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
                _registrar_falha("fetch_bcb", _e)
                print(f"  [BCB hist] {nome}: {type(_e).__name__}")

        if dfs_hist:
            df_br_hist = pd.DataFrame(dfs_hist)
            # Calcula IPCA_12M acumulado
            if "IPCA" in df_br_hist.columns:
                try:
                    _ipca_raw = df_br_hist["IPCA"].resample("MS").last()
                    _ipca_12m = ((1 + _ipca_raw / 100).rolling(12).apply(
                        lambda x: x.prod(), raw=True) - 1) * 100
                    df_br_hist["IPCA_12M"] = _ipca_12m
                except Exception as e:
                    _registrar_falha("fetch_bcb", e)
                    logger.debug(f"falha ao calcular IPCA_12M acumulado: {type(e).__name__}")
            _salvar_snapshot_historico("bcb_br", df_br_hist)
        else:
            print("  [BCB hist] nenhum dado histórico obtido.")

    except Exception as e:
        _registrar_falha("fetch_bcb", e)
        print(f"  [BCB] ERRO: {type(e).__name__}")


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
                _registrar_falha("fetch_fred", e)
                print(f"  [FRED] {nome} ({code}): {type(e).__name__}")

        # ── séries históricas 10 anos → macro_snapshots ─────────────────────
        print("  [FRED] buscando série histórica 10 anos...")
        series_hist = {
            "FEDFUNDS": "FEDFUNDS", "CPIAUCSL": "CPIAUCSL", "UNRATE": "UNRATE",
            "DGS10": "DGS10", "DGS2": "DGS2", "DGS3MO": "DGS3MO", "VIXCLS": "VIXCLS",
            "INDPRO": "INDPRO", "DFII10": "DFII10",
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
                _registrar_falha("fetch_fred", _e)
                print(f"  [FRED hist] {nome}: {type(_e).__name__}")

        if dfs_fred:
            df_global_hist = pd.DataFrame(dfs_fred)
            # Calcula CPI YoY — dropna ANTES de pct_change porque o merge cria
            # índice diário (DGS10/DGS2 são diários) e CPIAUCSL é mensal/esparsa.
            # Sem dropna, pct_change(12) desloca 12 LINHAS e dá NaN quase sempre.
            if "CPIAUCSL" in df_global_hist.columns:
                try:
                    _cpi_m = df_global_hist["CPIAUCSL"].resample("MS").last()
                    if len(_cpi_m) >= 13:
                        _yoy = _cpi_m.pct_change(12, fill_method=None) * 100
                        df_global_hist["CPI_YOY"] = _yoy.reindex(df_global_hist.index)
                except Exception as e:
                    _registrar_falha("fetch_fred", e)
                    logger.debug(f"falha ao calcular CPI_YOY: {type(e).__name__}")
            _salvar_snapshot_historico("fred_global", df_global_hist)

            # ── slopes da curva de juros → macro_cache ────────────────────────
            try:
                for curto, chave, descricao in (("DGS2", "slope_10y_2y_pp", "US Treasury 10Y-2Y Slope"),
                                              ("DGS3MO", "slope_10y_3m_pp", "US Treasury 10Y-3M Slope")):
                    if "DGS10" not in df_global_hist or curto not in df_global_hist:
                        continue
                    par = df_global_hist[["DGS10", curto]].dropna()
                    if par.empty:
                        continue
                    slope = round(float(par["DGS10"].iloc[-1] - par[curto].iloc[-1]), 4)
                    upsert_macro(chave, slope, label=descricao, unit="pp", source="fred")
                    print(f"  [FRED] {chave} = {slope:.4f}; mesma data {par.index[-1].date()}")
            except Exception as _e_slope:
                _registrar_falha("fetch_fred", _e_slope)
                print(f"  [FRED] slope calc: {type(_e_slope).__name__}")
        else:
            print("  [FRED hist] nenhum dado histórico obtido.")

    except Exception as e:
        _registrar_falha("fetch_fred", e)
        print(f"  [FRED] ERRO: {type(e).__name__}")


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
                if not __import__("math").isfinite(v) or v <= 0:
                    raise ValueError("Valor Yahoo não finito/positivo")
                if t == "^TNX" and v > 20:
                    raise ValueError("Treasury Yahoo fora da unidade percentual esperada")

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
                _registrar_falha("fetch_yfinance_macro", e)
                print(f"  [yfinance] {t}: {type(e).__name__}")

    except Exception as e:
        _registrar_falha("fetch_yfinance_macro", e)
        print(f"  [yfinance] ERRO: {type(e).__name__}")


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
    s = pd.to_numeric(serie, errors="coerce").resample("MS").last()
    return ((1 + s / 100).rolling(12).apply(lambda x: x.prod(), raw=True) - 1) * 100


def _acumular_anualizado(serie_mensal: pd.Series, meses: int) -> pd.Series:
    """
    Run-rate ANUALIZADO de uma série de variação MENSAL (%) — compõe os últimos
    `meses` e anualiza: ((Π(1+m/100))^(12/meses) − 1)·100. Capta a inflexão que
    o YoY/12m esconde (ex.: administrados a 11% anualizado em 3m vs 5.8% no 12m).
    """
    s = pd.to_numeric(serie_mensal, errors="coerce").resample("MS").last()
    prod = (1 + s / 100).rolling(meses).apply(lambda x: x.prod(), raw=True)
    return (prod ** (12.0 / meses) - 1) * 100


def _runrate_indice(serie_indice: pd.Series, meses: int) -> pd.Series:
    """Run-rate ANUALIZADO de uma série de ÍNDICE (CPI): (idx_t/idx_{t-meses})^(12/meses)−1."""
    s = pd.to_numeric(serie_indice, errors="coerce").resample("MS").last()
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
                _registrar_falha("fetch_inflacao_setorial", _e)
                print(f"  [infl BR] {nome} ({codigo}): {type(_e).__name__}")

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
                    _registrar_falha("fetch_inflacao_setorial", e)
                    logger.debug(f"falha run-rate {nome}: {type(e).__name__}")
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
        _registrar_falha("fetch_inflacao_setorial", e)
        print(f"  [infl BR] ERRO: {type(e).__name__}")

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
                    _registrar_falha("fetch_inflacao_setorial", _e)
                    print(f"  [infl US] {nome} ({serie_id}): {type(_e).__name__}")

            if cols_us:
                df_infl_us = pd.DataFrame(cols_us)
                # Componentes são ÍNDICES → YoY (nível) + run-rates anualizados 3m/6m.
                for nome in list(df_infl_us.columns):
                    try:
                        _m = df_infl_us[nome].resample("MS").last()
                        if len(_m) >= 13:
                            df_infl_us[f"{nome}_yoy"] = (
                                _m.pct_change(12, fill_method=None) * 100
                            ).reindex(df_infl_us.index)
                        if len(_m) >= 7:
                            df_infl_us[f"{nome}_6m"] = _runrate_indice(_m, 6).reindex(df_infl_us.index)
                        if len(_m) >= 4:
                            df_infl_us[f"{nome}_3m"] = _runrate_indice(_m, 3).reindex(df_infl_us.index)
                    except Exception as e:
                        _registrar_falha("fetch_inflacao_setorial", e)
                        logger.debug(f"falha run-rate us {nome}: {type(e).__name__}")

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
                        _registrar_falha("fetch_inflacao_setorial", _e)
                        print(f"  [infl US] {nome} ({serie_id}): {type(_e).__name__}")

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
            _registrar_falha("fetch_inflacao_setorial", e)
            print(f"  [infl US] ERRO: {type(e).__name__}")


def gap_focus_mesmo_horizonte(realizado: pd.Series, focus_12m: pd.Series, *, conhecido_em: pd.Series | None = None) -> dict | None:
    """Gap de previsão de 12m, usando previsão anterior ao MESMO período realizado.

    NÃO é surpresa de divulgação. Sem observação do Focus no fechamento da
    janela anterior (tolerância5d), não calcula nem recicla uma previsão atual.
    As datas do histórico Focus vêm da fonte; sua coleta atual não demonstra
    vintages anteriores do terminal, e esse limite acompanha o resultado.
    """
    if realizado is None or focus_12m is None or conhecido_em is None or realizado.dropna().empty or focus_12m.dropna().empty:
        return None
    r = realizado.dropna().sort_index()
    f = focus_12m.dropna().sort_index().copy()
    f.index = pd.to_datetime(f.index).tz_localize(None)
    referencia = pd.Timestamp(r.index[-1]).tz_localize(None) + pd.offsets.MonthEnd(0)
    inicio = referencia - pd.DateOffset(years=1)
    anterior = f[f.index <= inicio]
    if anterior.empty or (inicio - anterior.index[-1]).days > 5:
        return None
    conhecimento = conhecido_em.copy()
    conhecimento.index = pd.to_datetime(conhecimento.index).tz_localize(None)
    conhecido = conhecimento.get(anterior.index[-1])
    if conhecido is None or pd.isna(conhecido):
        return None
    conhecido = pd.Timestamp(conhecido)
    conhecido = conhecido.tz_convert(None) if conhecido.tzinfo else conhecido
    if conhecido > inicio:
        return None
    return {"valor": round(float(r.iloc[-1]) - float(anterior.iloc[-1]), 2),
        "realizado": float(r.iloc[-1]), "esperado": float(anterior.iloc[-1]),
        "referencia_fim": referencia.strftime("%Y-%m-%d"),
        "previsao_referencia": anterior.index[-1].strftime("%Y-%m-%d"),
        "tipo": "gap_previsao_mesmo_horizonte_12m", "surpresa_divulgacao": False,
        "previsao_conhecida_em": conhecido.isoformat(),
        "vintage": "previsao comprovada no historico prospectivo do terminal"}


def _remover_proxies_surpresa_legados():
    """Retira chaves inválidas do cache no próximo ETL; não remove observações auditadas."""
    try:
        _get_sb_client().table("macro_cache").delete().in_("indicator",
            ["br_surpresa_inflacao", "us_surpresa_inflacao", "br_gap_expectativa_12m"]).execute()
    except Exception as exc:
        _registrar_falha("limpeza_proxies_legados", exc)


def fetch_expectativas():
    """Expectativas/breakevens; somente gap12m correspondente, nunca falsa surpresa."""
    try:
        from bcb import sgs
        from utils.macro_research_data import buscar_focus_publico
        todas = buscar_focus_publico(dias=420)
        if todas is None or todas.empty:
            raise ValueError("Focus sem observações válidas")
        for aviso in todas.attrs.get("avisos", []):
            _ETL_AVISOS.append(str(aviso))
        _salvar_snapshot_historico("focus_expectativas", todas.set_index("data"))
        pontos = todas.loc[(todas["indicador"] == "IPCA") & (todas["horizonte"] == "12m")]
        focus = pontos.set_index("data")["mediana"].sort_index().dropna()
        if focus.empty:
            raise ValueError("Focus12m sem mediana não suavizada")
        upsert_macro("br_focus_ipca_12m", round(float(focus.iloc[-1]), 2),
                     label="Focus IPCA próximos 12m", unit="%", source="bcb")
        _salvar_snapshot_historico("expectativas_br", focus.to_frame("Focus_IPCA_12m"))
        realizado = sgs.get({"x": 13522}, last=1)["x"].dropna()
        from utils.macro_supabase import carregar_observacoes_versionadas
        limite_previsao = (pd.Timestamp(realizado.index[-1]) + pd.offsets.MonthEnd(0) - pd.DateOffset(years=1)) if not realizado.empty else None
        conhecidas = carregar_observacoes_versionadas("expectativas_br:Focus_IPCA_12m",
            as_of=limite_previsao, cliente=_get_sb_client()) if limite_previsao is not None else pd.DataFrame()
        if conhecidas.empty:
            gap = None
        else:
            # Usar a versão de previsão realmente conhecida à época, não o
            # valor hoje retornado pela API para aquela referência antiga.
            historico_focus = conhecidas.set_index("referencia_em")["valor"]
            conhecimento = conhecidas.set_index("referencia_em")["coletado_em"]
            gap = gap_focus_mesmo_horizonte(realizado, historico_focus, conhecido_em=conhecimento)
        if gap is not None:
            upsert_macro("br_gap_expectativa_12m", gap["valor"],
                label=f"Gap previsão 12m BR (Focus {gap['previsao_referencia']}; fim {gap['referencia_fim']})",
                unit="pp", source="bcb")
    except Exception as exc:
        _registrar_falha("expectativas_bcb", exc)
        print(f"  [exp BR] indisponível: {type(exc).__name__}")

    if not FRED_API_KEY:
        print("  [exp US] FRED_API_KEY ausente, etapa não configurada")
        return
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        series = {}
        for nome, sid, label in [
            ("mich", "MICH", "Michigan expectativa 1 ano"),
            ("be_5y", "T5YIE", "Breakeven 5 anos"),
            ("be_5y5y", "T5YIFR", "Breakeven forward 5y5y"),
            ("be_10y", "T10YIE", "Breakeven 10 anos"),
        ]:
            try:
                serie = fred.get_series(sid, observation_start=(dt.date.today() - dt.timedelta(days=365 * 10)))
                if serie is None or serie.dropna().empty:
                    raise ValueError("Série de expectativa vazia")
                series[sid] = serie
                upsert_macro(f"us_{nome}", round(float(serie.dropna().iloc[-1]), 2),
                    label=label, unit="%", source="fred")
            except Exception as exc:
                _registrar_falha(f"expectativas_fred_{sid}", exc)
        if series:
            _salvar_snapshot_historico("expectativas_us", pd.DataFrame(series))
    except Exception as exc:
        _registrar_falha("expectativas_fred", exc)


def main():
    global _ETL_GRAVACOES
    _ETL_GRAVACOES = 0
    _ETL_FALHAS.clear()
    _ETL_AVISOS.clear()
    print("[sync_macro] inicio")
    log_id = log_etl_start("sync_macro")
    _remover_proxies_surpresa_legados()
    for nome, coletar in [("BCB", fetch_bcb), ("FRED", fetch_fred),
        ("inflacao_setorial", fetch_inflacao_setorial), ("expectativas", fetch_expectativas),
        ("yfinance", fetch_yfinance_macro)]:
        antes = _ETL_GRAVACOES
        print(f"[sync_macro] {nome}...")
        try:
            coletar()
        except Exception as exc:
            _registrar_falha(nome, exc)
        if _ETL_GRAVACOES == antes and (nome != "FRED" or FRED_API_KEY):
            if not any(nome.lower() in erro.lower() for erro in _ETL_FALHAS):
                _ETL_FALHAS.append(f"{nome}: nenhuma gravação confirmada")
    erro = "; ".join(_ETL_FALHAS)
    log_etl_finish(log_id, ok=_ETL_GRAVACOES, fail=len(_ETL_FALHAS), error_msg=erro)
    print(f"[sync_macro] fim: gravacoes={_ETL_GRAVACOES}, falhas={len(_ETL_FALHAS)}")
    for aviso in _ETL_AVISOS:
        print(f"[sync_macro] aviso: {aviso}; snapshots atuais preservados")
    return 1 if _ETL_FALHAS else 0


if __name__ == "__main__":
    raise SystemExit(main())
