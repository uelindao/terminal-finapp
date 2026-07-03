"""
utils/fii_scraper.py
====================
Coleta em UMA request os dados de TODOS os FIIs listados no Fundamentus
(fundamentus.com.br/fii_resultado.php) — a fonte que o BRAPI/yfinance não cobrem
bem para fundos imobiliários. Alimenta o motor de FII v2 (P1-5) com os campos
que realmente diferenciam FIIs: liquidez diária, vacância, cap rate, nº de imóveis.

Semântica por segmento:
  - FIIs de PAPEL (CRI/CRA) não possuem imóvel físico → qtd_imoveis, vacancia e
    cap_rate vêm 0/vazios. O consumidor (health_engine) só usa vacância p/ tijolo.

Robusto: `buscar_dados_fiis` nunca levanta — devolve {} em falha (o score cai
para o motor FII básico). O parser é PURO (testável com HTML sintético).
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)

_URL = "https://www.fundamentus.com.br/fii_resultado.php"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Cabeçalho do Fundamentus (normalizado) → chave canônica no cache.
_MAP_COLUNAS = {
    "papel":            "ticker",
    "segmento":         "segmento_fii",
    "cotacao":          "preco",
    "ffo yield":        "ffo_yield%",
    "dividend yield":   "dy%",
    "p/vp":             "p/vp",
    "valor de mercado": "market_cap",
    "liquidez":         "liquidez_diaria",
    "qtd de imoveis":   "qtd_imoveis",
    "cap rate":         "cap_rate%",
    "vacancia media":   "vacancia%",
}
# Campos tratados como percentuais (mantêm 2 casas) vs valores absolutos.
_PCT = {"ffo_yield%", "dy%", "cap_rate%", "vacancia%"}
_INT = {"qtd_imoveis"}


def _norm_hdr(s: str) -> str:
    """Normaliza cabeçalho: minúsculas, sem acento, espaços colapsados."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _br_num(s: str):
    """
    Converte número no formato BR do Fundamentus para float.
    '.' = separador de milhar, ',' = decimal, '%'/'R$' ignorados.
    Ex.: '165.857.000'→165857000.0 ; '6,90'→6.9 ; '15,19%'→15.19 ; '0,00'→0.0
    """
    if s is None:
        return None
    s = str(s).replace("%", "").replace("R$", "").strip()
    if not s or s in ("-", "—", "N/D", "n/d"):
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parsear_tabela_fiis(html: str) -> dict[str, dict]:
    """
    Parseia o HTML da listagem e devolve {ticker_base: {campos canônicos}}.
    ticker_base sem sufixo .SA (ex.: 'HGLG11'). Campos numéricos já convertidos.
    """
    from bs4 import BeautifulSoup
    out: dict[str, dict] = {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        tabela = soup.find("table")
        if not tabela:
            return out
        linhas = tabela.find_all("tr")
        if len(linhas) < 2:
            return out

        # Índice de coluna → chave canônica, a partir do cabeçalho (robusto a reordenação)
        headers = [_norm_hdr(th.get_text()) for th in linhas[0].find_all(["th", "td"])]
        idx_para_chave: dict[int, str] = {}
        for i, h in enumerate(headers):
            if h in _MAP_COLUNAS:
                idx_para_chave[i] = _MAP_COLUNAS[h]

        if "ticker" not in idx_para_chave.values():
            return out

        for tr in linhas[1:]:
            tds = tr.find_all("td")
            if not tds:
                continue
            reg: dict = {}
            for i, td in enumerate(tds):
                chave = idx_para_chave.get(i)
                if not chave:
                    continue
                txt = td.get_text(strip=True)
                if chave == "ticker":
                    reg["ticker"] = txt.upper()
                elif chave == "segmento_fii":
                    reg["segmento_fii"] = txt.lower()
                else:
                    v = _br_num(txt)
                    if chave in _INT and v is not None:
                        v = int(round(v))
                    elif v is not None and chave in _PCT:
                        v = round(v, 2)
                    reg[chave] = v
            tk = reg.get("ticker")
            if tk:
                out[tk] = reg
    except Exception as e:
        logger.warning(f"[fii_scraper] falha ao parsear tabela: {e}")
    return out


def buscar_dados_fiis(timeout: int = 20) -> dict[str, dict]:
    """
    Baixa e parseia a listagem completa de FIIs. Retorna {ticker_base: dados}.
    Nunca levanta — devolve {} em falha de rede/parse.
    """
    try:
        import requests
        r = requests.get(_URL, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        dados = parsear_tabela_fiis(r.text)
        logger.info(f"[fii_scraper] {len(dados)} FIIs coletados do Fundamentus.")
        return dados
    except Exception as e:
        logger.warning(f"[fii_scraper] falha ao buscar listagem de FIIs: {e}")
        return {}
