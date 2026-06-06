"""
utils/formatters.py
Funções centrais para formatação de números, moedas e percentuais.
"""


def safe_float(val, default=None):
    """Converte valor para float de forma segura, tratando None/NaN/strings."""
    if val is None:
        return default
    try:
        import pandas as pd
        if isinstance(val, float) and pd.isna(val):
            return default
    except Exception:
        pass
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def fmt_numero(n, prefixo=""):
    """Formata grandes números para K, M, B, T de forma elegante."""
    if n is None: return "N/D"
    try:
        n = float(n)
        if abs(n) >= 1e12: return f"{prefixo}{n/1e12:.2f}T"
        if abs(n) >= 1e9:  return f"{prefixo}{n/1e9:.2f}B"
        if abs(n) >= 1e6:  return f"{prefixo}{n/1e6:.2f}M"
        if abs(n) >= 1e3:  return f"{prefixo}{n/1e3:.2f}K"
        return f"{prefixo}{n:,.2f}"
    except Exception:
        return "N/D"

def fmt_pct(n, casas=2, sinal=True):
    """Formata percentuais com ou sem sinal positivo."""
    if n is None: return "N/D"
    try:
        n = float(n)
        s = "+" if (sinal and n > 0) else ""
        return f"{s}{n:.{casas}f}%"
    except Exception:
        return "N/D"

def fmt_preco(n, moeda="R$"):
    """Formata preços de mercado."""
    if n is None: return "N/D"
    try:
        n = float(n)
        return f"{moeda} {n:,.2f}"
    except Exception:
        return "N/D"


def traduzir_setor(setor_raw: str) -> str:
    """Traduz nome de setor em inglês (yfinance / FMP) para label PT-BR com emoji."""
    mapa = {
        "Energy":                 "⛽ energia",
        "Financial Services":     "🏦 financeiro",
        "Technology":             "💻 tecnologia",
        "Healthcare":             "🏥 saúde",
        "Consumer Cyclical":      "🛒 consumo cíclico",
        "Consumer Defensive":     "🛒 consumo def.",
        "Industrials":            "🏭 indústria",
        "Basic Materials":        "⛏️ materiais",
        "Real Estate":            "🏢 imobiliário",
        "Utilities":              "⚡ utilities",
        "Communication Services": "📡 telecom",
        "Financeiro":             "🏦 financeiro",
    }
    return mapa.get(setor_raw, setor_raw.lower() if setor_raw else "—")