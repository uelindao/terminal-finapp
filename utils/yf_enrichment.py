"""
yf_enrichment.py — preenche campos críticos de fundamentos via yfinance.Ticker.info
quando o provedor primário (FMP free tier ou BRAPI) deixou de retornar.

yfinance.info é gratuito, não exige chave, e cobre 30+ campos úteis. Custo: ~50ms
por ticker e propenso a rate-limit se chamado em rajada — manter sleep externo.

Convenções de unidade alinhadas com sync_us/sync_br:
- ROE, margem, ROIC em %, não decimal (24.5, não 0.245)
- P/L, P/VP, EV/EBITDA em razão pura (5.0, não 5%)
- DY% em %, não decimal
"""

from typing import Optional


CAMPOS_CRITICOS = [
    "preco", "p/l", "p/vp", "dy%", "roe%",
    "margem%", "ev/ebitda", "market_cap",
]


def _sf(val) -> Optional[float]:
    """Safe float — None/str/erro -> None."""
    if val is None:
        return None
    try:
        f = float(val)
        # yfinance ocasionalmente retorna inf para múltiplos
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _pct(val) -> Optional[float]:
    """Converte decimal yfinance (0.24) para % (24.0). Aceita já em %."""
    f = _sf(val)
    if f is None:
        return None
    # yfinance margens/ROE/ROIC vêm em decimal (0.245). Se valor pequeno, normaliza.
    if abs(f) < 2.0:
        f = f * 100
    return round(f, 2)


def enriquecer_com_yfinance(dados: dict, ticker_yf: str, logger=None) -> dict:
    """
    Preenche campos críticos ausentes em `dados` com valores de yfinance.Ticker.info.
    Modifica `dados` in-place e também retorna o dict (conveniência).

    `ticker_yf` deve incluir o sufixo certo (.SA para BR, plain para US).

    Mutates: dados[*] dos campos faltantes
    Adiciona: dados['_raw']['yf_info'] com as chaves consultadas (auditoria)
    """
    faltantes = [c for c in CAMPOS_CRITICOS if dados.get(c) is None]
    if not faltantes:
        return dados

    try:
        import yfinance as yf
        info = yf.Ticker(ticker_yf).info or {}
    except Exception as e:
        if logger:
            logger.debug(f"[yf_enrich] {ticker_yf} info indisponível: {e}")
        return dados

    if not info:
        return dados

    mapeamento = {
        "preco":      lambda i: _sf(i.get("currentPrice") or i.get("regularMarketPrice")),
        "p/l":        lambda i: _sf(i.get("trailingPE") or i.get("forwardPE")),
        "p/vp":       lambda i: _sf(i.get("priceToBook")),
        "dy%":        lambda i: _pct(i.get("trailingAnnualDividendYield") or i.get("dividendYield")),
        "roe%":       lambda i: _pct(i.get("returnOnEquity")),
        "margem%":    lambda i: _pct(i.get("profitMargins") or i.get("netMargins")),
        "ev/ebitda":  lambda i: _sf(i.get("enterpriseToEbitda")),
        "market_cap": lambda i: _sf(i.get("marketCap")),
    }

    preenchidos = []
    for campo in faltantes:
        extractor = mapeamento.get(campo)
        if extractor is None:
            continue
        valor = extractor(info)
        if valor is not None:
            dados[campo] = valor
            preenchidos.append(campo)

    # Campos auxiliares úteis ao health_engine, sempre preenche se ausente
    extras = {
        "roic%":       _pct(info.get("returnOnAssets")),  # proxy ROIC quando ausente
        "debt_equity": _sf(info.get("debtToEquity")),
        "fcf":         _sf(info.get("freeCashflow")),
        "shares_out":  _sf(info.get("sharesOutstanding")),
        "ebitda":      _sf(info.get("ebitda")),
        "receita":     _sf(info.get("totalRevenue")),
        "lucro":       _sf(info.get("netIncomeToCommon") or info.get("netIncome")),
        "beta_yf":     _sf(info.get("beta")),
    }
    for k, v in extras.items():
        if v is not None and dados.get(k) is None:
            dados[k] = v

    if preenchidos:
        # Marca origem para auditoria
        raw = dados.get("_raw")
        if isinstance(raw, dict):
            raw["yf_info_preenchidos"] = preenchidos
        if logger:
            logger.debug(f"[yf_enrich] {ticker_yf} preencheu {len(preenchidos)} campos: {preenchidos}")

    return dados
