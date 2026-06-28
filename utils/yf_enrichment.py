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

    # Roteado pela fachada única (utils/market_data.yf_info): circuit breaker
    # central + backoff. Protege o ETL inteiro do rate-limit do yfinance.info,
    # antes chamado cru aqui (e em ~10 outros pontos).
    from utils.market_data import yf_info
    info = yf_info(ticker_yf)
    if not info:
        if logger:
            logger.debug(f"[yf_enrich] {ticker_yf} info indisponível (falha/circuito aberto)")
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


# ── Histórico trimestral ─────────────────────────────────────────────────────
# Mapeia métricas canônicas → possíveis nomes em yfinance.quarterly_*.
# Quando há múltiplas opções, usa a primeira que existir no DataFrame.
_MAP_INCOME = {
    "receita":   ["Total Revenue", "Operating Revenue"],
    "lucro":     ["Net Income", "Net Income Common Stockholders",
                  "Net Income From Continuing Operation Net Minority Interest"],
    "ebitda":    ["EBITDA", "Normalized EBITDA"],
    "ebit":      ["EBIT", "Operating Income"],
    "gross":     ["Gross Profit"],
    "opex":      ["Operating Expense"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
}
_MAP_BALANCE = {
    "ativos_totais":      ["Total Assets"],
    "passivos_totais":    ["Total Liabilities Net Minority Interest", "Total Liab"],
    "patrimonio":         ["Stockholders Equity", "Common Stock Equity",
                            "Total Equity Gross Minority Interest"],
    "ativos_circ":        ["Current Assets"],
    "passivos_circ":      ["Current Liabilities"],
    "divida_total":       ["Total Debt"],
    "cash":               ["Cash And Cash Equivalents",
                           "Cash Cash Equivalents And Short Term Investments"],
    "shares":             ["Ordinary Shares Number", "Share Issued"],
}
_MAP_CASHFLOW = {
    "cfo":   ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure"],
    "fcf":   ["Free Cash Flow"],
}


def _extrair_serie(df, nomes_candidatos: list[str]) -> dict:
    """Acha a 1ª linha do DataFrame que match algum nome candidato (case-insensitive).
    Retorna {data_str: valor} para cada coluna (trimestre) onde o valor não é NaN."""
    if df is None or df.empty:
        return {}
    # Normaliza nomes do índice pra busca
    idx_norm = {str(i).strip().lower(): i for i in df.index}
    linha = None
    for cand in nomes_candidatos:
        chave = cand.strip().lower()
        if chave in idx_norm:
            linha = df.loc[idx_norm[chave]]
            break
    if linha is None:
        return {}
    out = {}
    for col, val in linha.items():
        try:
            f = float(val)
            if f != f:  # NaN
                continue
            data_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            out[data_str] = f
        except (ValueError, TypeError):
            continue
    return out


def coletar_dividendos_yfinance(
    ticker_yf: str,
    desde: str | None = None,
    logger=None,
) -> list[dict]:
    """
    Coleta dividendos pagos via yf.Ticker.dividends.

    Retorna lista de dicts no formato {ticker, data_pagamento (YYYY-MM-DD),
    valor (float > 0), tipo}. yfinance traz histórico completo desde a IPO
    do ativo — passa 'desde' (YYYY-MM-DD) para sync incremental.

    Para FIIs brasileiros (sufixo `11.SA`), tipo='rendimento'. Caso contrário,
    tipo='dividendo' (yfinance não separa dividendo de JCP em ações BR).
    """
    try:
        import yfinance as yf
        serie = yf.Ticker(ticker_yf).dividends
    except Exception as e:
        if logger:
            logger.debug(f"[yf_div] {ticker_yf} indisponível: {e}")
        return []

    if serie is None or serie.empty:
        return []

    # Detecta FII brasileiro pelo sufixo (ticker termina em 11.SA mas não index)
    is_fii = (
        ticker_yf.endswith("11.SA")
        and ticker_yf not in {"BOVA11.SA", "SMAL11.SA", "IVVB11.SA"}
    )
    tipo_padrao = "rendimento" if is_fii else "dividendo"

    desde_dt = None
    if desde:
        try:
            from datetime import datetime
            desde_dt = datetime.strptime(desde, "%Y-%m-%d").date()
        except Exception:
            desde_dt = None

    out = []
    for idx, val in serie.items():
        try:
            f = float(val)
            if f != f or f <= 0:
                continue
        except (ValueError, TypeError):
            continue
        try:
            data_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            if desde_dt is not None:
                from datetime import datetime
                d = datetime.strptime(data_str, "%Y-%m-%d").date()
                if d <= desde_dt:
                    continue
        except Exception:
            continue
        out.append({
            "ticker":         ticker_yf,
            "data_pagamento": data_str,
            "valor":          round(f, 6),
            "tipo":           tipo_padrao,
        })
    return out


def coletar_historico_trimestral(ticker_yf: str, max_periodos: int = 8, logger=None) -> list[dict]:
    """
    Coleta últimos N trimestres de DRE + Balanço + DFC via yfinance.
    Retorna lista de dicts (mais recente primeiro), com chave 'periodo' (YYYY-MM-DD)
    e métricas canônicas. yfinance hoje devolve ~5 trimestres em ações large cap;
    em small caps pode devolver 2-4. Quem consome trata None como ausente.

    Custo: 3 chamadas HTTP por ticker, ~200-400ms. Use sleep externo em batch.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker_yf)
        qf = t.quarterly_financials
        qb = t.quarterly_balance_sheet
        qc = t.quarterly_cashflow
    except Exception as e:
        if logger:
            logger.debug(f"[yf_quart] {ticker_yf} indisponível: {e}")
        return []

    # Coleta cada métrica como {data: valor}
    series: dict[str, dict] = {}
    for nome, candidatos in _MAP_INCOME.items():
        series[nome] = _extrair_serie(qf, candidatos)
    for nome, candidatos in _MAP_BALANCE.items():
        series[nome] = _extrair_serie(qb, candidatos)
    for nome, candidatos in _MAP_CASHFLOW.items():
        series[nome] = _extrair_serie(qc, candidatos)

    # União das datas observadas, ordenadas desc
    datas = set()
    for s in series.values():
        datas.update(s.keys())
    if not datas:
        return []
    datas_ord = sorted(datas, reverse=True)[:max_periodos]

    # Materializa lista de dicts por período
    historico = []
    for data in datas_ord:
        registro = {"periodo": data}
        for nome, s in series.items():
            registro[nome] = s.get(data)
        historico.append(registro)
    return historico

