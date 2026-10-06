"""Universos separados para o ranking e a análise de oportunidades de IA."""
from utils.tickers import SCREENER_B3, SCREENER_US, FII_TODOS, mapear_ticker_base

UNIVERSOS_IA = {
    "BR_ACOES": "Ações brasileiras",
    "FII": "FIIs",
    "US_ACOES": "Ações EUA",
    "ACOES": "Todas as ações",
}


def tickers_oportunidades_ia(universo: str) -> list[str]:
    # A lista B3 também contém IRDM11; a classe vem do catálogo, não do sufixo11.
    fiis = {mapear_ticker_base(t) for t in FII_TODOS}
    acoes_br = [t for t in SCREENER_B3 if mapear_ticker_base(t) not in fiis]
    opcoes = {"BR_ACOES": acoes_br, "FII": FII_TODOS,
              "US_ACOES": SCREENER_US, "ACOES": acoes_br + SCREENER_US}
    if universo not in opcoes:
        raise ValueError("Universo de oportunidades desconhecido")
    return list(dict.fromkeys(opcoes[universo]))


def chaves_cache_oportunidades_ia(universo: str, modo: str) -> tuple[str, str]:
    if universo not in UNIVERSOS_IA:
        raise ValueError("Universo de oportunidades desconhecido")
    modo_db = f"v3_{universo}_{modo}"
    return f"ia_disc_{modo_db}", modo_db


def filtrar_resultados_oportunidades_ia(resultados: list[dict], universo: str) -> list[dict]:
    permitidos = {mapear_ticker_base(t) for t in tickers_oportunidades_ia(universo)}
    return [r for r in resultados if mapear_ticker_base(r.get("ticker", "")) in permitidos]
