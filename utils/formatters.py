"""
utils/formatters.py
Funções centrais para formatação de números, moedas e percentuais.
"""

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