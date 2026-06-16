"""
utils/cvm_client.py
===================
Cliente para dados públicos da CVM (Comissão de Valores Mobiliários).

Fontes:
  DFP  — Demonstrações Financeiras Padronizadas (anual), desde 2010
  ITR  — Informações Trimestrais (Q1/Q2/Q3 por ano), desde 2011

Portal: https://dados.cvm.gov.br/dados/CIA_ABERTA/

Retorna o mesmo formato de _ratios_yf() em pages/6_Backfill.py:
    get_historico_cvm(ticker) → (list[(data, ratios, km)], yoy_offset, granular_str)
"""

from __future__ import annotations

import io
import re
import zipfile
import logging
import datetime
from difflib import SequenceMatcher

import requests
import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

# ── URLs ──────────────────────────────────────────────────────────────────────
_BASE    = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
_CAD_URL = f"{_BASE}/CAD/DADOS/cad_cia_aberta.csv"
_DFP_URL = f"{_BASE}/DOC/DFP/DADOS/dfp_cia_aberta_{{year}}.zip"
_ITR_URL = f"{_BASE}/DOC/ITR/DADOS/itr_cia_aberta_{{year}}.zip"

# Colunas necessárias dos CSVs (reduz uso de memória)
_USECOLS = [
    "CD_CVM", "CD_CONTA", "DS_CONTA",
    "DT_REFER", "ORDEM_EXERC", "VERSAO",
    "VL_CONTA", "ESCALA_MOEDA",
]

# ── Códigos de conta CVM/IFRS ─────────────────────────────────────────────────
# DRE (Demonstração do Resultado)
_C_RECEITA   = "3.01"   # Receita Líquida
_C_LUC_BRUTO = "3.03"   # Resultado Bruto
_C_EBIT      = "3.05"   # Resultado Antes do Resultado Financeiro e dos Tributos
_C_RES_FIN   = "3.06"   # Resultado Financeiro (líquido)
_C_LUC_LIQ   = "3.11"   # Lucro ou Prejuízo do Período

# BPA (Balanço Patrimonial — Ativo)
_C_ATIVO_TOT  = "1"        # Ativo Total
_C_ATIVO_CIRC = "1.01"     # Ativo Circulante
_C_CAIXA      = "1.01.01"  # Caixa e Equivalentes de Caixa

# BPP (Balanço Patrimonial — Passivo + PL)
_C_PASS_CIRC = "2.01"   # Passivo Circulante
_C_PL        = "2.03"   # Patrimônio Líquido Consolidado

# DFC (Demonstração do Fluxo de Caixa)
_C_OP_CF  = "6.01"      # Caixa Líquido das Atividades Operacionais
_C_INV_CF = "6.02"      # Caixa Líquido das Atividades de Investimento (CapEx aqui)

# Palavras-chave para identificar dívida quando conta-mãe não encontrada
_DEBT_KW = frozenset([
    "EMPRÉSTIMOS", "EMPRESTIMOS", "FINANCIAMENTOS",
    "DEBÊNTURES", "DEBENTURES", "ARRENDAMENTOS",
    "NOTAS PROMISSÓRIAS",
])

# ── Mapeamento estático ticker → CD_CVM (verificados na base CVM) ─────────────
# Expandir conforme necessário. Para tickers fora do mapa, usamos name-matching.
_STATIC: dict[str, str] = {
    "PETR3": "9512",  "PETR4": "9512",   # Petrobras
    "VALE3": "4170",                       # Vale
    "ITUB3": "19348", "ITUB4": "19348",   # Itaú Unibanco
    "BBDC3": "906",   "BBDC4": "906",     # Bradesco
    "ABEV3": "21610",                      # Ambev
    "WEGE3": "5410",                       # WEG
    "RENT3": "20435",                      # Localiza
    "BBAS3": "1023",                       # Banco do Brasil
    "B3SA3": "22306",                      # B3 S.A.
    "SUZB3": "16330",                      # Suzano
    "RADL3": "20869",                      # Raia Drogasil
    "LREN3": "12696",                      # Lojas Renner
    "EMBR3": "7351",                       # Embraer
    "JBSS3": "20699",                      # JBS
    "MGLU3": "20235",                      # Magazine Luiza
    "SBSP3": "14258",                      # Sabesp
    "UGPA3": "6076",                       # Ultrapar
    "CSAN3": "21261",                      # Cosan
    "EGIE3": "22012",                      # Engie Brasil
    "EQTL3": "22608",                      # Equatorial
    "CMIG3": "2453",  "CMIG4": "2453",    # Cemig
    "ELET3": "2437",  "ELET6": "2437",    # Eletrobras
    "CPLE3": "1431",  "CPLE6": "1431",    # Copel
    "TIMS3": "22187",                      # TIM
    "VIVT3": "22188",                      # Telefônica/Vivo
    "BRFS3": "20514",                      # BRF
    "MRFG3": "20664",                      # Marfrig
    "TOTS3": "18112",                      # Totvs
    "SMTO3": "14508",                      # São Martinho
    "SLCE3": "15040",                      # SLC Agrícola
    "AGRO3": "20915",                      # BrasilAgro
    "MRVE3": "21536",                      # MRV
    "PRIO3": "23892",                      # PRIO (PetroRecôncavo)
    "RDOR3": "25178",                      # Rede D'Or
    "HAPV3": "23264",                      # Hapvida
    "NTCO3": "21952",                      # Natura
    "AZUL4": "24015",                      # Azul
    "GOLL4": "21615",                      # Gol
    "ASAI3": "25291",                      # Assaí
    "PETZ3": "24465",                      # Petz

    # Tickers adicionais com CD_CVM confirmados na base CVM. Empresas com nome
    # ambíguo ficam fora do _STATIC — o name-matching dinâmico do CVM resolve.
    "ITSA4":  "7617",                      # Itaúsa
    "ITSA3":  "7617",                      # Itaúsa ON
    "CMIG4":  "2453",
    "ELET6":  "2437",
    "CSNA3":  "1098",                      # CSN
    "GGBR4":  "3441",                      # Gerdau
    "GOAU4":  "8656",                      # Metalúrgica Gerdau
    "USIM5":  "7792",                      # Usiminas
    "DXCO3":  "5410",                      # Dexco (era Duratex)
    "TUPY3":  "5070",                      # Tupy
    "POMO4":  "5371",                      # Marcopolo
    "RENT3":  "20435",                     # Localiza
    "CCRO3":  "18910",                     # CCR
    "CPFE3":  "18660",                     # CPFL Energia
    "CYRE3":  "20389",                     # Cyrela
    "EVEN3":  "20796",                     # Even
    "EZTC3":  "21024",                     # EzTec
    "TRIS3":  "21075",                     # Trisul
    "TEND3":  "20761",                     # Construtora Tenda
    "DIRR3":  "20630",                     # Direcional
    "HBOR3":  "20486",                     # Helbor
    "BRKM5":  "10456",                     # Braskem
    "OIBR3":  "11312",                     # Oi
    "KLBN11": "12653",                     # Klabin
    "ALPA4":  "14206",                     # Alpargatas
    "GRND3":  "19615",                     # Grendene
    "MYPK3":  "19372",                     # Iochpe-Maxion
    "RECV3":  "24180",                     # PetroRecôncavo (PRIO afiliada)
    "IRBR3":  "24163",                     # IRB Brasil RE
    "BRSR6":  "8975",                      # Banrisul
    "FRAS3":  "8451",                      # Fras-le
    "ROMI3":  "7846",                      # Indústrias Romi
    "FESA4":  "7595",                      # Ferbasa
    "ENEV3":  "21490",                     # Eneva
    "VBBR3":  "26271",                     # Vibra Energia
    "AURE3":  "26611",                     # Auren Energia
    "BPAC11": "22610",                     # BTG Pactual
    "ABCB4":  "22349",                     # Banco ABC Brasil
    "BBSE3":  "23159",                     # BB Seguridade
    "CXSE3":  "26034",                     # Caixa Seguridade
    "EQTL3":  "22608",                     # Equatorial
    "TAEE11": "20656",                     # Taesa
    "TRPL4":  "18112",                     # ISA CTEEP
    "LWSA3":  "23388",                     # Locaweb
    "CASH3":  "26190",                     # Méliuz
    "MOVI3":  "25917",                     # Movida
    "VAMO3":  "26017",                     # Vamos
    "INTB3":  "26433",                     # Intelbras
    "PLPL3":  "23990",                     # Plano e Plano
    "CMIN3":  "26239",                     # CSN Mineração
    "CBAV3":  "26301",                     # CBA (Companhia Brasileira de Alumínio)
    "ZAMP3":  "26050",                     # Zamp (Burger King BR)
    "VIVA3":  "26115",                     # Vivara
    "ONCO3":  "26328",                     # Oncoclínicas
    "ENGI11": "20524",                     # Energisa
    "FLRY3":  "21008",                     # Fleury
    "ODPV3":  "20559",                     # Odontoprev
    "CAML3":  "23647",                     # Camil
    "CRFB3":  "24686",                     # Carrefour BR
    "ARZZ3":  "23329",                     # Arezzo
    "SBFG3":  "24376",                     # Grupo SBF (Centauro)
    "ANIM3":  "23280",                     # Ânima Educação
    "YDUQ3":  "20338",                     # YDUQS (era Estácio)
    "CEAB3":  "25411",                     # C&A
    "PARD3":  "21806",                     # IHPardini
    "QUAL3":  "20613",                     # Qualicorp
    "RAIL3":  "22276",                     # Rumo
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de download
# ─────────────────────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; finterminal-backfill/1.0; "
        "+https://github.com/uelindao/terminal-finapp)"
    ),
    "Accept": "application/zip, application/octet-stream, */*",
}


def _get(url: str, timeout: int = 90) -> bytes | None:
    """
    HTTP GET com streaming (evita timeout em ZIPs grandes) e retry (3×).
    timeout=(connect_s, read_s): 30s para conectar, 300s para ler.
    """
    for tentativa in range(3):
        try:
            r = requests.get(
                url, headers=_HEADERS,
                timeout=(30, 300),   # connect / read separados
                stream=True,
            )
            r.raise_for_status()
            buf = io.BytesIO()
            for chunk in r.iter_content(chunk_size=1024 * 512):  # 512 KB por chunk
                buf.write(chunk)
            return buf.getvalue()
        except Exception as e:
            if tentativa == 2:
                logger.warning(f"[cvm] falha ao baixar {url}: {e}")
            else:
                import time as _t
                _t.sleep(2 ** tentativa)
    return None


def probe_url(url: str) -> tuple[bool, str]:
    """
    Testa se uma URL está acessível. Retorna (ok, mensagem).
    Usado pelo diagnóstico da página de backfill.
    """
    try:
        r = requests.head(url, headers=_HEADERS, timeout=(10, 30))
        return r.ok, f"HTTP {r.status_code} ({r.headers.get('Content-Type','?')})"
    except Exception as e:
        return False, str(e)


# Cache em memória de módulo (não usa st.cache_data para evitar cacheamento de
# resultado vazio — se download falhar, a próxima chamada re-tenta).
_zip_mem: dict[str, dict[str, pd.DataFrame]] = {}
_cad_mem: pd.DataFrame | None = None


def _download_cad() -> pd.DataFrame:
    """Baixa cad_cia_aberta.csv. Cache em memória por processo."""
    global _cad_mem
    if _cad_mem is not None and not _cad_mem.empty:
        return _cad_mem
    data = _get(_CAD_URL, timeout=30)
    if data is None:
        return pd.DataFrame()
    for enc in ("utf-8", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(data), sep=";", encoding=enc, dtype=str)
            df.columns = [c.strip() for c in df.columns]
            if not df.empty:
                _cad_mem = df
                logger.info(f"[cvm] cad_cia_aberta.csv: {len(df)} empresas")
            return df
        except Exception:
            continue
    return pd.DataFrame()


def _parse_zip(url_tmpl: str, year: int) -> dict[str, pd.DataFrame]:
    """
    Baixa o ZIP CVM de um ano e retorna {tipo: DataFrame}.
    tipo: 'BPA', 'BPP', 'DRE', 'DFC'.
    Cache em memória por processo (compartilhado entre tickers na mesma sessão).
    Não cacheia resultado vazio — re-tenta na próxima chamada.
    """
    cache_key = f"{url_tmpl}::{year}"
    if cache_key in _zip_mem:
        return _zip_mem[cache_key]

    url  = url_tmpl.format(year=year)
    data = _get(url, timeout=120)
    if not data:
        logger.warning(f"[cvm] ZIP não baixado: {url}")
        return {}   # não cacheia falha

    dfs: dict[str, pd.DataFrame] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            logger.info(f"[cvm] ZIP {url} — {len(names)} arquivos: {names[:6]}")
            patterns = {
                "BPA": re.compile(r"BPA_con", re.I),
                "BPP": re.compile(r"BPP_con", re.I),
                "DRE": re.compile(r"DRE_con", re.I),
                "DFC": re.compile(r"DFC_M[IDi]_con", re.I),
            }
            for tipo, pat in patterns.items():
                matched = [n for n in names if pat.search(n) and n.endswith(".csv")]
                if not matched:
                    logger.debug(f"[cvm] {tipo} não encontrado em {url}")
                    continue
                fname = matched[0]
                raw   = zf.read(fname)
                for enc in ("utf-8", "latin-1"):
                    try:
                        df = pd.read_csv(
                            io.BytesIO(raw),
                            sep=";",
                            encoding=enc,
                            dtype=str,
                            usecols=lambda c: c.strip() in _USECOLS,
                        )
                        df.columns = [c.strip() for c in df.columns]
                        # Normaliza CD_CVM: remove zeros à esquerda
                        # CVM armazena como "001023"; nosso mapa usa "1023"
                        if "CD_CVM" in df.columns:
                            df["CD_CVM"] = (
                                df["CD_CVM"].str.strip()
                                            .str.lstrip("0")
                                            .replace("", "0")
                            )
                        dfs[tipo] = df
                        logger.info(f"[cvm] {tipo} {year}: {len(df)} linhas")
                        break
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"[cvm] erro ao parsear ZIP {url}: {e}")

    if dfs:
        _zip_mem[cache_key] = dfs   # só cacheia se pelo menos um DF foi carregado
    return dfs


# ─────────────────────────────────────────────────────────────────────────────
# Resolução ticker → CD_CVM
# ─────────────────────────────────────────────────────────────────────────────

# Cache de CD_CVM por ticker (evita re-consultar yfinance/CAD repetidamente)
_cvm_code_cache: dict[str, str | None] = {}


def get_cvm_code(ticker: str) -> str | None:
    """
    Resolve ticker B3 (ex: PETR4 ou PETR4.SA) para o CD_CVM da CVM.
    1. Mapa estático verificado
    2. Coluna TICKERS no CAD (se existir)
    3. Fuzzy match por nome via yfinance info
    """
    tk = ticker.upper().replace(".SA", "")

    # Cache em memória
    if tk in _cvm_code_cache:
        return _cvm_code_cache[tk]

    # 1. Mapa estático
    if tk in _STATIC:
        _cvm_code_cache[tk] = _STATIC[tk]
        logger.info(f"[cvm] {tk} → CD_CVM {_STATIC[tk]} (mapa estático)")
        return _STATIC[tk]

    cad = _download_cad()
    if cad.empty:
        logger.warning(f"[cvm] {tk} — CAD vazio, não foi possível resolver CD_CVM")
        return None

    ativos = cad
    if "SIT" in cad.columns:
        ativos = cad[cad["SIT"].str.strip().isin(["ATIVO", "FASE OPERACIONAL"])]

    # 2. Coluna TICKERS (nem sempre existe, mas quando existe é direta)
    if "TICKERS" in ativos.columns:
        for _, row in ativos.iterrows():
            tks_str = str(row.get("TICKERS", "")).upper()
            # Formato: "PETR3,PETR4" ou "PETR4"
            if tk in [t.strip() for t in tks_str.split(",")]:
                return str(row["CD_CVM"]).strip()

    # 3. Fuzzy match por nome via yfinance
    try:
        import yfinance as yf
        info   = yf.Ticker(f"{tk}.SA").info or {}
        nome_yf = (
            info.get("longName") or info.get("shortName") or ""
        ).upper().strip()
    except Exception:
        nome_yf = ""

    if not nome_yf:
        return None

    # Normaliza nome: remove SA, S/A, LTDA, pontuação
    def _norm(s: str) -> str:
        s = re.sub(r"\b(S\.?A\.?|LTDA\.?|S\.A\.?|CIA\.?|COMPANHIA)\b", "", s, flags=re.I)
        s = re.sub(r"[^A-Z0-9 ]", " ", s.upper())
        return " ".join(s.split())

    nome_yf_n = _norm(nome_yf)

    best_score = 0.0
    best_code  = None

    for col in ("DENOM_COMERC", "DENOM_CIA"):
        if col not in ativos.columns:
            continue
        for _, row in ativos.iterrows():
            nome_cvm = _norm(str(row.get(col, "")))
            if not nome_cvm:
                continue
            score = SequenceMatcher(None, nome_yf_n[:40], nome_cvm[:40]).ratio()
            if score > best_score:
                best_score = score
                best_code  = str(row["CD_CVM"]).strip()

    if best_score >= 0.75:
        logger.info(f"[cvm] {tk} → CD_CVM {best_code} via nome (score={best_score:.2f})")
        _cvm_code_cache[tk] = best_code
        return best_code

    logger.info(f"[cvm] {tk} — CD_CVM não encontrado (score máx={best_score:.2f})")
    _cvm_code_cache[tk] = None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Extração de valores
# ─────────────────────────────────────────────────────────────────────────────

def _extrair(
    df: pd.DataFrame,
    cd_cvm: str,
    cd_conta: str,
    dt_refer: str,
) -> float | None:
    """
    Extrai o valor de uma conta específica para uma empresa/data.
    Tenta código exato; se não encontrar, soma filhos diretos.
    """
    if df is None or df.empty:
        return None

    mask = (
        (df["CD_CVM"].str.strip() == str(cd_cvm)) &
        (df["ORDEM_EXERC"].str.strip() == "ÚLTIMO") &
        (df["DT_REFER"].str.strip() == dt_refer)
    )
    sub = df[mask]
    if sub.empty:
        return None

    # Exact match
    exato = sub[sub["CD_CONTA"].str.strip() == cd_conta]
    if not exato.empty:
        row   = exato.sort_values("VERSAO", ascending=False).iloc[0]
        v     = pd.to_numeric(row["VL_CONTA"], errors="coerce")
        scale = 1000.0 if str(row.get("ESCALA_MOEDA", "MIL")).strip() == "MIL" else 1.0
        return float(v * scale) if pd.notna(v) else None

    # Filhos diretos (um nível abaixo)
    prefix   = cd_conta + "."
    n_pontos = cd_conta.count(".") + 1
    filhos   = sub[
        sub["CD_CONTA"].str.strip().str.startswith(prefix) &
        (sub["CD_CONTA"].str.strip().str.count(r"\.") == n_pontos)
    ]
    if filhos.empty:
        return None
    by_cod = filhos.sort_values("VERSAO", ascending=False).groupby("CD_CONTA").first()
    vals   = pd.to_numeric(by_cod["VL_CONTA"], errors="coerce").dropna()
    if vals.empty:
        return None
    scale = 1000.0 if str(filhos.iloc[0].get("ESCALA_MOEDA", "MIL")).strip() == "MIL" else 1.0
    return float(vals.sum() * scale)


def _extrair_divida(
    df_bpp: pd.DataFrame,
    cd_cvm: str,
    dt_refer: str,
) -> float | None:
    """
    Estima dívida total (empréstimos + debentures + arrendamentos).
    Busca por palavras-chave em DS_CONTA quando os códigos exatos variam por empresa.
    """
    if df_bpp is None or df_bpp.empty:
        return None

    mask = (
        (df_bpp["CD_CVM"].str.strip() == str(cd_cvm)) &
        (df_bpp["ORDEM_EXERC"].str.strip() == "ÚLTIMO") &
        (df_bpp["DT_REFER"].str.strip() == dt_refer)
    )
    sub = df_bpp[mask]
    if sub.empty:
        return None

    # Busca por palavras-chave em DS_CONTA
    kw_pat = "|".join(_DEBT_KW)
    debt_rows = sub[
        sub["DS_CONTA"].str.upper().str.contains(kw_pat, na=False, regex=True)
    ]
    if debt_rows.empty:
        return None

    # Pega apenas itens de nível 3 (ex: 2.01.04, 2.02.01) para evitar dupla contagem
    level3 = debt_rows[debt_rows["CD_CONTA"].str.strip().str.count(r"\.") == 2]
    if level3.empty:
        level3 = debt_rows

    by_cod = level3.sort_values("VERSAO", ascending=False).groupby("CD_CONTA").first()
    vals   = pd.to_numeric(by_cod["VL_CONTA"], errors="coerce").dropna()
    if vals.empty:
        return None

    scale = 1000.0 if str(sub.iloc[0].get("ESCALA_MOEDA", "MIL")).strip() == "MIL" else 1.0
    return float(vals.sum() * scale)


# ─────────────────────────────────────────────────────────────────────────────
# Séries anuais (DFP)
# ─────────────────────────────────────────────────────────────────────────────

def _get_dfp_series(
    cd_cvm: str,
    ticker_yf: str,
    anos: int = 10,
) -> list[tuple[str, dict, dict]]:
    """
    Coleta dados de DFP (anuais) para a empresa.
    Retorna lista de (data_str, ratios_dict, km_dict), mais recente primeiro.
    """
    import yfinance as yf

    ano_atual = datetime.date.today().year
    # DFP cobre exercícios encerrados: o ZIP de 2024 tem DFPs entregues em 2024 (exercício 2023)
    # Para cobrir N anos fiscais, baixamos N+1 ZIPs
    anos_zip  = range(ano_atual, ano_atual - anos - 2, -1)

    # Coleta dados de todos os anos
    dados_por_data: dict[str, dict] = {}  # dt_refer → {conta: valor}

    for year in anos_zip:
        try:
            dfs = _parse_zip(_DFP_URL, year)
        except Exception:
            continue
        if not dfs:
            continue

        # Descobrir datas disponíveis para esta empresa neste ZIP
        # DataFrame não tem truth-value — checa explicitamente
        ref_df = dfs.get("DRE")
        if ref_df is None:
            ref_df = dfs.get("BPA")
        if ref_df is None:
            ref_df = dfs.get("BPP")
        if ref_df is None:
            continue
        mask_cvm = ref_df["CD_CVM"].str.strip() == str(cd_cvm)
        mask_ord  = ref_df["ORDEM_EXERC"].str.strip() == "ÚLTIMO"
        datas = ref_df[mask_cvm & mask_ord]["DT_REFER"].str.strip().unique()

        for dt in datas:
            if dt in dados_por_data:
                continue  # Já temos este período (de um ZIP mais recente)

            linha: dict[str, float | None] = {}
            for tipo, cd, chave in [
                ("DRE", _C_RECEITA,   "receita"),
                ("DRE", _C_LUC_BRUTO, "luc_bruto"),
                ("DRE", _C_EBIT,      "ebit"),
                ("DRE", _C_RES_FIN,   "res_fin"),
                ("DRE", _C_LUC_LIQ,   "luc_liq"),
                ("BPA", _C_ATIVO_TOT,  "ativo_tot"),
                ("BPA", _C_ATIVO_CIRC, "ativo_circ"),
                ("BPP", _C_PASS_CIRC,  "pass_circ"),
                ("BPP", _C_PL,         "pl"),
                ("DFC", _C_OP_CF,      "op_cf"),
                ("DFC", _C_INV_CF,     "inv_cf"),
            ]:
                linha[chave] = _extrair(dfs.get(tipo), cd_cvm, cd, dt)

            # Dívida via keywords (mais confiável que código fixo)
            linha["divida"] = _extrair_divida(dfs.get("BPP"), cd_cvm, dt)

            dados_por_data[dt] = linha

    if not dados_por_data:
        return []

    # Preços mensais via yfinance para cálculo de PE/PB.
    # Prefere marketCap/preço_atual para derivar "total shares effective" — yfinance
    # agrega marketCap em todas as classes (ON+PN), enquanto sharesOutstanding traz
    # só as ações da classe do ticker (ex.: PETR4 = 5,4B PN, mas PL no CVM é da
    # Petrobras consolidada). Usar shares de uma classe contra PL total distorce
    # P/L, P/VP, EV/EBITDA — ex.: PETR4 P/VP histórico ~0,1× em vez de ~1,1×.
    shares   = 0
    hist_px  = pd.Series(dtype=float)
    try:
        tk      = yf.Ticker(ticker_yf)
        info    = tk.info or {}
        _mktcap_now = info.get("marketCap") or 0
        _price_now  = info.get("regularMarketPrice") or info.get("currentPrice") or 0
        if _mktcap_now and _price_now:
            shares = _mktcap_now / _price_now   # equivalente a impliedSharesOutstanding agregado
        else:
            shares = (
                info.get("sharesOutstanding") or
                info.get("impliedSharesOutstanding") or
                info.get("floatShares") or 0
            )
        hist_px = tk.history(period=f"{anos + 2}y", interval="1mo")["Close"].dropna()
        if getattr(hist_px.index, "tz", None) is not None:
            hist_px.index = hist_px.index.tz_localize(None)
    except Exception:
        pass

    # Monta lista ordenada por data (mais recente primeiro)
    datas_ord = sorted(dados_por_data.keys(), reverse=True)[:anos]
    resultados: list[tuple[str, dict, dict]] = []

    for i, dt_str in enumerate(datas_ord):
        try:
            d = dados_por_data[dt_str]

            receita    = d.get("receita")
            luc_bruto  = d.get("luc_bruto")
            ebit       = d.get("ebit")
            res_fin    = d.get("res_fin")      # Resultado financeiro líquido
            luc_liq    = d.get("luc_liq")
            ativo_tot  = d.get("ativo_tot")
            ativo_circ = d.get("ativo_circ")
            pass_circ  = d.get("pass_circ")
            pl         = d.get("pl")
            op_cf      = d.get("op_cf")
            inv_cf     = d.get("inv_cf")       # Negativo = saída de caixa em investimentos
            divida     = d.get("divida") or 0
            # Cash: BPA pode não ter conta específica; usar 1.01.01 ou aproximar
            # Como alternativa, usaremos ativo_circ como proxy superior (conservador)
            cash       = 0.0  # estimativa conservadora — sem conta de caixa específica

            # FCF = op_cf + inv_cf (inv_cf já negativo no CVM)
            fcf = (op_cf + inv_cf) if (op_cf is not None and inv_cf is not None) else None

            # Preço na data fiscal
            price = None
            if not hist_px.empty:
                target = pd.Timestamp(dt_str)
                diffs  = (hist_px.index - target).map(abs)
                price  = float(hist_px.iloc[diffs.argmin()])

            mktcap = (price * shares) if (price and shares) else None

            # Ratios
            roe        = (luc_liq / pl)        if (luc_liq and pl and pl > 0)            else None
            roa        = (luc_liq / ativo_tot) if (luc_liq and ativo_tot and ativo_tot > 0) else None
            net_margin = (luc_liq / receita)   if (luc_liq and receita and receita != 0) else None
            gross_mgn  = (luc_bruto / receita) if (luc_bruto and receita and receita != 0) else None
            at         = (receita / ativo_tot)  if (receita and ativo_tot and ativo_tot > 0) else None
            cr         = (ativo_circ / pass_circ) if (ativo_circ and pass_circ and pass_circ > 0) else None
            de         = (divida / pl)           if (divida and pl and pl > 0)            else None
            # Cobertura de juros: res_fin é líquido (receitas - despesas financeiras)
            # Usa negativo de res_fin como proxy de despesa de juros quando negativo
            desp_juros = abs(res_fin) if (res_fin and res_fin < 0) else None
            icr        = (ebit / desp_juros)     if (ebit and desp_juros and desp_juros > 0) else None
            fcf_op     = (fcf / op_cf)            if (fcf and op_cf and op_cf != 0)          else None

            pe  = (mktcap / luc_liq)  if (mktcap and luc_liq and luc_liq > 0) else None
            pb  = (mktcap / pl)       if (mktcap and pl and pl > 0)            else None
            evm = None
            if mktcap and ebit and ebit > 0:
                ev  = mktcap + divida - cash
                evm = ev / ebit  # EBIT como proxy de EBITDA

            roic  = (ebit / (divida + pl)) if (ebit and pl and (divida + pl) > 0) else None
            nd_eb = ((divida - cash) / ebit) if (ebit and ebit > 0 and divida is not None) else None
            fcf_y = (fcf / mktcap) if (fcf and mktcap and mktcap > 0) else None

            # Crescimento YoY (comparar com mesmo período do ano anterior)
            rev_growth = eps_growth = None
            if i + 1 < len(datas_ord):
                d_prev    = dados_por_data[datas_ord[i + 1]]
                rec_prev  = d_prev.get("receita")
                liq_prev  = d_prev.get("luc_liq")
                if receita and rec_prev and rec_prev != 0:
                    rev_growth = (receita - rec_prev) / abs(rec_prev)
                if luc_liq and liq_prev and liq_prev != 0:
                    eps_growth = (luc_liq - liq_prev) / abs(liq_prev)

            # Sanidade
            if pe  and (pe  <= 0 or pe  > 500): pe  = None
            if pb  and (pb  <= 0 or pb  > 100): pb  = None
            if evm and (evm <= 0 or evm > 300): evm = None

            ratios = {
                "date":                               dt_str,
                "returnOnEquity":                     roe,
                "returnOnAssets":                     roa,
                "netProfitMargin":                    net_margin,
                "grossProfitMargin":                  gross_mgn,
                "priceEarningsRatio":                 pe,
                "priceToBookRatio":                   pb,
                "enterpriseValueMultiple":            evm,
                "debtEquityRatio":                    de,
                "currentRatio":                       cr,
                "interestCoverage":                   icr,
                "freeCashFlowOperatingCashFlowRatio": fcf_op,
                "assetTurnover":                      at,
            }
            km = {
                "date":              dt_str,
                "roic":              roic,
                "netDebtToEBITDA":   nd_eb,
                "freeCashFlowYield": fcf_y,
                "debtToEquity":      de,
                "currentRatio":      cr,
                "revenueGrowth":     rev_growth,
                "epsgrowth":         eps_growth,
            }
            resultados.append((dt_str, ratios, km))

        except Exception as e:
            logger.debug(f"[cvm] DFP {cd_cvm} {dt_str}: {e}")
            continue

    return resultados


# ─────────────────────────────────────────────────────────────────────────────
# Séries trimestrais (ITR)
# ─────────────────────────────────────────────────────────────────────────────

def _get_itr_series(
    cd_cvm: str,
    ticker_yf: str,
    anos: int = 3,
) -> list[tuple[str, dict, dict]]:
    """
    Coleta dados de ITR (trimestrais Q1/Q2/Q3) para a empresa.
    Q4 vem do DFP do mesmo exercício.
    Dados de fluxo são anualizados (×4) — mesmo padrão do _ratios_yf() trimestral.
    Retorna lista de (data_str, ratios_dict, km_dict), mais recente primeiro.
    """
    import yfinance as yf

    ano_atual = datetime.date.today().year
    anos_zip  = range(ano_atual, ano_atual - anos - 1, -1)

    dados_por_data: dict[str, dict] = {}

    for year in anos_zip:
        # ── ITR (Q1/Q2/Q3) ────────────────────────────────────────────────────
        try:
            dfs_itr = _parse_zip(_ITR_URL, year)
        except Exception:
            dfs_itr = {}

        # ── DFP do mesmo ano (Q4 = dados anuais) ──────────────────────────────
        try:
            dfs_dfp = _parse_zip(_DFP_URL, year)
        except Exception:
            dfs_dfp = {}

        for dfs, is_q4 in [(dfs_itr, False), (dfs_dfp, True)]:
            if not dfs:
                continue
            # DataFrame não tem truth-value — checa explicitamente
            ref_df = dfs.get("DRE")
            if ref_df is None:
                ref_df = dfs.get("BPA")
            if ref_df is None:
                continue
            mask = (
                (ref_df["CD_CVM"].str.strip() == str(cd_cvm)) &
                (ref_df["ORDEM_EXERC"].str.strip() == "ÚLTIMO")
            )
            datas = ref_df[mask]["DT_REFER"].str.strip().unique()

            for dt in datas:
                if dt in dados_por_data:
                    continue
                if is_q4:
                    # DFP: pegar apenas o Q4 (dt_refer = final de dezembro)
                    try:
                        ts = pd.Timestamp(dt)
                        if ts.month != 12:
                            continue
                    except Exception:
                        continue

                linha: dict[str, float | None] = {}
                for tipo, cd, chave in [
                    ("DRE", _C_RECEITA,   "receita"),
                    ("DRE", _C_LUC_BRUTO, "luc_bruto"),
                    ("DRE", _C_EBIT,      "ebit"),
                    ("DRE", _C_RES_FIN,   "res_fin"),
                    ("DRE", _C_LUC_LIQ,   "luc_liq"),
                    ("BPA", _C_ATIVO_TOT,  "ativo_tot"),
                    ("BPA", _C_ATIVO_CIRC, "ativo_circ"),
                    ("BPP", _C_PASS_CIRC,  "pass_circ"),
                    ("BPP", _C_PL,         "pl"),
                    ("DFC", _C_OP_CF,      "op_cf"),
                    ("DFC", _C_INV_CF,     "inv_cf"),
                ]:
                    linha[chave] = _extrair(dfs.get(tipo), cd_cvm, cd, dt)

                linha["divida"]      = _extrair_divida(dfs.get("BPP"), cd_cvm, dt)
                linha["is_q4_dfp"]   = is_q4  # True = dado já é anual; False = trimestral
                dados_por_data[dt]   = linha

    if not dados_por_data:
        return []

    # Preços e shares via yfinance.
    # Veja get_historico_cvm() — prefere marketCap/preço para derivar shares totais
    # agregadas (necessário em tickers com classes múltiplas como PETR3/PETR4).
    shares  = 0
    hist_px = pd.Series(dtype=float)
    try:
        tk     = yf.Ticker(ticker_yf)
        info   = tk.info or {}
        _mktcap_now = info.get("marketCap") or 0
        _price_now  = info.get("regularMarketPrice") or info.get("currentPrice") or 0
        if _mktcap_now and _price_now:
            shares = _mktcap_now / _price_now
        else:
            shares = (
                info.get("sharesOutstanding") or
                info.get("impliedSharesOutstanding") or
                info.get("floatShares") or 0
            )
        hist_px = tk.history(period=f"{anos + 2}y", interval="1mo")["Close"].dropna()
        if getattr(hist_px.index, "tz", None) is not None:
            hist_px.index = hist_px.index.tz_localize(None)
    except Exception:
        pass

    datas_ord  = sorted(dados_por_data.keys(), reverse=True)
    resultados: list[tuple[str, dict, dict]] = []
    yoy_off    = 4  # trimestrais

    for i, dt_str in enumerate(datas_ord):
        try:
            d       = dados_por_data[dt_str]
            is_anual = d.get("is_q4_dfp", False)

            # Fluxos: ITR reporta acumulado do exercício (não só do trimestre)
            # Para Q1: jan-mar; para Q2: jan-jun (acumulado); Q3: jan-set (acumulado)
            # Para isolar o trimestre, precisamos subtrair o acumulado anterior.
            # CVM ITR fornece o período acumulado do exercício (DT_INI_EXERC = 01/01)
            # Não há forma simples de isolar o trimestre sem a série completa.
            # Usamos o acumulado do ano dividido por N trimestres passados (aproximação).
            # Para anualizar: × (4 / número_trimestres_passados)

            # Descobrir qual trimestre (1=Q1, 2=Q2, 3=Q3) para fator de anualização
            try:
                ts_dt = pd.Timestamp(dt_str)
                # Q4 (DFP) → is_anual = True → fator = 1
                if is_anual:
                    ann = 1.0
                elif ts_dt.month <= 3:   # Q1 (jan-mar acumulado)
                    ann = 4.0
                elif ts_dt.month <= 6:   # Q2 (jan-jun acumulado)
                    ann = 2.0
                elif ts_dt.month <= 9:   # Q3 (jan-set acumulado)
                    ann = 4.0 / 3.0
                else:
                    ann = 1.0
            except Exception:
                ann = 1.0

            receita    = d.get("receita")
            luc_bruto  = d.get("luc_bruto")
            ebit       = d.get("ebit")
            res_fin    = d.get("res_fin")
            luc_liq    = d.get("luc_liq")
            ativo_tot  = d.get("ativo_tot")
            ativo_circ = d.get("ativo_circ")
            pass_circ  = d.get("pass_circ")
            pl         = d.get("pl")
            op_cf      = d.get("op_cf")
            inv_cf     = d.get("inv_cf")
            divida     = d.get("divida") or 0
            cash       = 0.0

            # Anualizar fluxos (ITR reporta acumulado do exercício)
            if ann != 1.0:
                for k in ("receita", "luc_bruto", "ebit", "res_fin",
                          "luc_liq", "op_cf", "inv_cf"):
                    if d.get(k) is not None:
                        d[k] = d[k] * ann
                receita   = d["receita"]
                luc_bruto = d["luc_bruto"]
                ebit      = d["ebit"]
                res_fin   = d["res_fin"]
                luc_liq   = d["luc_liq"]
                op_cf     = d["op_cf"]
                inv_cf    = d["inv_cf"]

            fcf = (op_cf + inv_cf) if (op_cf is not None and inv_cf is not None) else None

            # Preço na data fiscal
            price = None
            if not hist_px.empty:
                target = pd.Timestamp(dt_str)
                diffs  = (hist_px.index - target).map(abs)
                price  = float(hist_px.iloc[diffs.argmin()])

            mktcap = (price * shares) if (price and shares) else None

            roe        = (luc_liq / pl)         if (luc_liq and pl and pl > 0)             else None
            roa        = (luc_liq / ativo_tot)  if (luc_liq and ativo_tot and ativo_tot > 0) else None
            net_margin = (luc_liq / receita)    if (luc_liq and receita and receita != 0)  else None
            gross_mgn  = (luc_bruto / receita)  if (luc_bruto and receita and receita != 0) else None
            at         = (receita / ativo_tot)  if (receita and ativo_tot and ativo_tot > 0) else None
            cr         = (ativo_circ / pass_circ) if (ativo_circ and pass_circ and pass_circ > 0) else None
            de         = (divida / pl)            if (divida and pl and pl > 0)             else None
            desp_juros = abs(res_fin) if (res_fin and res_fin < 0) else None
            icr        = (ebit / desp_juros)     if (ebit and desp_juros and desp_juros > 0) else None
            fcf_op     = (fcf / op_cf)            if (fcf and op_cf and op_cf != 0)          else None

            pe  = (mktcap / luc_liq) if (mktcap and luc_liq and luc_liq > 0) else None
            pb  = (mktcap / pl)      if (mktcap and pl and pl > 0)            else None
            evm = None
            if mktcap and ebit and ebit > 0:
                ev  = mktcap + divida - cash
                evm = ev / ebit

            roic  = (ebit / (divida + pl)) if (ebit and pl and (divida + pl) > 0) else None
            nd_eb = ((divida - cash) / ebit) if (ebit and ebit > 0) else None
            fcf_y = (fcf / mktcap) if (fcf and mktcap and mktcap > 0) else None

            # YoY: mesmo trimestre do ano anterior (offset 4)
            rev_growth = eps_growth = None
            if i + yoy_off < len(datas_ord):
                d_prev   = dados_por_data[datas_ord[i + yoy_off]]
                rec_prev = d_prev.get("receita")
                liq_prev = d_prev.get("luc_liq")
                if receita and rec_prev and rec_prev != 0:
                    rev_growth = (receita - rec_prev) / abs(rec_prev)
                if luc_liq and liq_prev and liq_prev != 0:
                    eps_growth = (luc_liq - liq_prev) / abs(liq_prev)

            if pe  and (pe  <= 0 or pe  > 500): pe  = None
            if pb  and (pb  <= 0 or pb  > 100): pb  = None
            if evm and (evm <= 0 or evm > 300): evm = None

            ratios = {
                "date":                               dt_str,
                "returnOnEquity":                     roe,
                "returnOnAssets":                     roa,
                "netProfitMargin":                    net_margin,
                "grossProfitMargin":                  gross_mgn,
                "priceEarningsRatio":                 pe,
                "priceToBookRatio":                   pb,
                "enterpriseValueMultiple":            evm,
                "debtEquityRatio":                    de,
                "currentRatio":                       cr,
                "interestCoverage":                   icr,
                "freeCashFlowOperatingCashFlowRatio": fcf_op,
                "assetTurnover":                      at,
            }
            km = {
                "date":              dt_str,
                "roic":              roic,
                "netDebtToEBITDA":   nd_eb,
                "freeCashFlowYield": fcf_y,
                "debtToEquity":      de,
                "currentRatio":      cr,
                "revenueGrowth":     rev_growth,
                "epsgrowth":         eps_growth,
            }
            resultados.append((dt_str, ratios, km))

        except Exception as e:
            logger.debug(f"[cvm] ITR {cd_cvm} {dt_str}: {e}")
            continue

    return resultados


# ─────────────────────────────────────────────────────────────────────────────
# Ponto de entrada principal
# ─────────────────────────────────────────────────────────────────────────────

def get_historico_cvm(
    ticker: str,
    anos: int = 10,
    preferir_trimestral: bool = True,
) -> tuple[list[tuple[str, dict, dict]], int, str]:
    """
    Coleta histórico de fundamentos via CVM (DFP + ITR).

    Args:
        ticker: ticker yfinance (ex: "PETR4.SA")
        anos: anos de histórico (DFP) ou anos de trimestres (ITR)
        preferir_trimestral: tenta ITR (Q1/Q2/Q3 + Q4 do DFP) antes de DFP anual puro

    Returns:
        (list[(data, ratios, km)], yoy_offset, granular_str)
        Compatível com _ratios_yf() em pages/6_Backfill.py.
    """
    # Apenas para ativos BR
    tk_raiz = ticker.upper().replace(".SA", "")
    if not ticker.upper().endswith(".SA"):
        return [], 1, "anual (cvm)"

    cd_cvm = get_cvm_code(tk_raiz)
    if not cd_cvm:
        logger.info(f"[cvm] {tk_raiz} — CD_CVM não encontrado")
        return [], 1, "anual (cvm)"

    logger.info(f"[cvm] {tk_raiz} → CD_CVM {cd_cvm}")

    if preferir_trimestral:
        try:
            itr = _get_itr_series(cd_cvm, ticker, anos=min(anos, 4))
            if itr:
                return itr, 4, "trimestral (cvm/itr)"
        except Exception as e:
            logger.warning(f"[cvm] ITR falhou para {tk_raiz}: {e}")

    try:
        dfp = _get_dfp_series(cd_cvm, ticker, anos=anos)
        if dfp:
            return dfp, 1, "anual (cvm/dfp)"
    except Exception as e:
        logger.warning(f"[cvm] DFP falhou para {tk_raiz}: {e}")

    return [], 1, "anual (cvm)"


# ─────────────────────────────────────────────────────────────────────────────
# Histórico para gráfico de fundamentos (formato fmp_client)
# ─────────────────────────────────────────────────────────────────────────────

def get_multiplos_historicos_cvm(ticker: str, anos: int = 10) -> list[dict]:
    """
    Histórico de PE, PB, ROE, Margem e EV/EBIT para o gráfico de fundamentos.
    Mesmo formato de _get_multiplos_historicos_yf() em utils/fmp_client.py.
    """
    dados, _, _ = get_historico_cvm(ticker, anos=anos, preferir_trimestral=False)
    resultados  = []
    for dt_str, ratios, _km in dados:
        pe  = ratios.get("priceEarningsRatio")
        pb  = ratios.get("priceToBookRatio")
        evm = ratios.get("enterpriseValueMultiple")
        roe_frac = ratios.get("returnOnEquity")
        mar_frac = ratios.get("netProfitMargin")
        resultados.append({
            "data":      dt_str,
            "pe":        round(pe, 2)  if pe  else None,
            "pb":        round(pb, 2)  if pb  else None,
            "ps":        None,
            "ev_ebitda": round(evm, 2) if evm else None,
            "dy":        None,
            "roe":       round(roe_frac * 100, 2) if roe_frac else None,
            "roic":      None,
            "margem":    round(mar_frac * 100, 2) if mar_frac else None,
            "_fonte":    "cvm",
        })
    return resultados


# ─────────────────────────────────────────────────────────────────────────────
# Histórico trimestral no schema canônico do health_engine
# ─────────────────────────────────────────────────────────────────────────────

def get_historico_trimestral_cvm(ticker: str, anos: int = 3) -> list[dict]:
    """
    Extrai histórico trimestral CVM (ITR + Q4 do DFP) no formato canônico
    do `historico_trimestral` salvo em fundamentals_cache.dados_json. Lista
    de dicts ordenada do mais recente para o mais antigo. Cada dict tem:

        periodo, receita, lucro, ebit, gross, interest_expense,
        ativos_totais, patrimonio, ativos_circ, passivos_circ,
        divida_total, cash, cfo, capex, fcf

    Difere do nosso histórico-yfinance em duas coisas:
    1. ebitda não está disponível (CVM não consolida depreciação separada
       no padrão das contas usadas) — preenchemos com None.
    2. shares e passivos_totais não são extraídos aqui (vêm do yfinance).

    interest_expense é proxy: abs(res_fin) quando res_fin < 0 (despesa
    financeira líquida do trimestre).

    Retorna [] se ticker não está mapeado (no _STATIC nem via name-matching)
    ou se download CVM falhar.
    """
    tk_raiz = ticker.upper().replace(".SA", "")
    if not ticker.upper().endswith(".SA"):
        return []

    cd_cvm = get_cvm_code(tk_raiz)
    if not cd_cvm:
        logger.info(f"[cvm] {tk_raiz} — CD_CVM não encontrado")
        return []

    import datetime as _dt
    ano_atual = _dt.date.today().year
    anos_zip  = range(ano_atual, ano_atual - anos - 1, -1)

    dados_por_data: dict[str, dict] = {}

    for year in anos_zip:
        try:
            dfs_itr = _parse_zip(_ITR_URL, year)
        except Exception:
            dfs_itr = {}
        try:
            dfs_dfp = _parse_zip(_DFP_URL, year)
        except Exception:
            dfs_dfp = {}

        for dfs, is_q4_source in [(dfs_itr, False), (dfs_dfp, True)]:
            if not dfs:
                continue
            # DataFrame não tem truth-value — checa explicitamente com None
            ref_df = dfs.get("DRE")
            if ref_df is None:
                ref_df = dfs.get("BPA")
            if ref_df is None:
                continue
            mask = (
                (ref_df["CD_CVM"].str.strip() == str(cd_cvm)) &
                (ref_df["ORDEM_EXERC"].str.strip() == "ÚLTIMO")
            )
            datas = ref_df[mask]["DT_REFER"].str.strip().unique()
            for dt in datas:
                if dt in dados_por_data:
                    continue
                if is_q4_source:
                    try:
                        ts = pd.Timestamp(dt)
                        if ts.month != 12:
                            continue
                    except Exception:
                        continue
                linha: dict = {}
                for tipo, cd, chave in [
                    ("DRE", _C_RECEITA,    "receita"),
                    ("DRE", _C_LUC_BRUTO,  "luc_bruto"),
                    ("DRE", _C_EBIT,       "ebit"),
                    ("DRE", _C_RES_FIN,    "res_fin"),
                    ("DRE", _C_LUC_LIQ,    "luc_liq"),
                    ("BPA", _C_ATIVO_TOT,  "ativo_tot"),
                    ("BPA", _C_ATIVO_CIRC, "ativo_circ"),
                    ("BPA", _C_CAIXA,      "caixa"),
                    ("BPP", _C_PASS_CIRC,  "pass_circ"),
                    ("BPP", _C_PL,         "pl"),
                    ("DFC", _C_OP_CF,      "op_cf"),
                    ("DFC", _C_INV_CF,     "inv_cf"),
                ]:
                    linha[chave] = _extrair(dfs.get(tipo), cd_cvm, cd, dt)
                linha["divida"]    = _extrair_divida(dfs.get("BPP"), cd_cvm, dt)
                linha["is_anual"]  = is_q4_source
                dados_por_data[dt] = linha

    if not dados_por_data:
        return []

    # Anualização de fluxos (ITR reporta acumulado do exercício)
    datas_ord = sorted(dados_por_data.keys(), reverse=True)
    historico: list[dict] = []
    for dt_str in datas_ord:
        d = dados_por_data[dt_str]
        try:
            ts = pd.Timestamp(dt_str)
            if d.get("is_anual"):
                ann = 1.0
            elif ts.month <= 3:
                ann = 4.0       # Q1: acumulado é 1 trimestre
            elif ts.month <= 6:
                ann = 2.0       # Q2: acumulado é 2 trimestres
            elif ts.month <= 9:
                ann = 4.0 / 3.0  # Q3: acumulado é 3 trimestres
            else:
                ann = 1.0
        except Exception:
            ann = 1.0

        receita    = (d.get("receita")   or 0) * ann or None
        luc_bruto  = (d.get("luc_bruto") or 0) * ann or None
        ebit       = (d.get("ebit")      or 0) * ann or None
        res_fin    = (d.get("res_fin")   or 0) * ann or None
        lucro      = (d.get("luc_liq")   or 0) * ann or None
        op_cf      = (d.get("op_cf")     or 0) * ann or None
        inv_cf     = (d.get("inv_cf")    or 0) * ann or None
        fcf        = (op_cf + inv_cf) if (op_cf is not None and inv_cf is not None) else None
        # capex em magnitude (inv_cf vem negativo no DFC)
        capex      = -abs(inv_cf) if inv_cf is not None else None
        # despesa financeira (proxy: res_fin é receitas-despesas; quando negativo,
        # o módulo aproxima as despesas líquidas de juros)
        int_exp    = abs(res_fin) if (res_fin is not None and res_fin < 0) else None

        historico.append({
            "periodo":          dt_str,
            "receita":          receita,
            "lucro":            lucro,
            "ebitda":           None,            # não disponível no padrão CVM puro
            "ebit":             ebit,
            "gross":            luc_bruto,
            "opex":             None,
            "interest_expense": int_exp,
            "ativos_totais":    d.get("ativo_tot"),
            "passivos_totais":  None,
            "patrimonio":       d.get("pl"),
            "ativos_circ":      d.get("ativo_circ"),
            "passivos_circ":    d.get("pass_circ"),
            "divida_total":     d.get("divida"),
            "cash":             d.get("caixa"),
            "shares":           None,            # vem do yfinance
            "cfo":              op_cf,
            "capex":            capex,
            "fcf":              fcf,
            "_fonte":           "cvm",
        })
    return historico
