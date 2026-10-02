"""Preparação dos valores da carteira para apresentação, sem conversão cambial."""
from utils.tickers import mapear_ticker_base


def currency_totals(positions: dict, prices: dict) -> list[dict]:
    """Agrupa as posições por moeda, preservando os preços e custos de origem."""
    groups = {}
    for ticker, position in positions.items():
        quantity = float(position.get("quantidade") or 0)
        if quantity <= 0:
            continue
        currency = "BRL" if mapear_ticker_base(ticker).endswith(".SA") else "USD"
        group = groups.setdefault(currency, {"currency": currency, "value": 0.0, "cost": 0.0, "positions": 0, "missing_prices": 0})
        price = float(prices.get(ticker) or 0)
        group["value"] += quantity * price
        group["cost"] += quantity * float(position.get("preco_medio") or 0)
        group["positions"] += 1
        group["missing_prices"] += int(price <= 0)
    for group in groups.values():
        group["pnl"] = group["value"] - group["cost"]
        group["pnl_pct"] = group["pnl"] / group["cost"] * 100 if group["cost"] > 0 else 0.0
    return [groups[c] for c in ("BRL", "USD") if c in groups]
