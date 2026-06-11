"""
Testes de regressão do health_engine — congelam o score atual para detectar
mudanções não intencionais.

Estratégia:
  A função pública calcular_health_score() faz I/O pesado (Supabase, yfinance,
  BCB). Para testes offline, mockamos todas as camadas de I/O e alimentamos o
  motor com dados dos fixtures JSON em tests/fixtures/. O score resultante é
  comparado com o "expected" calibrado do output atual do motor.

  Opção 1 (adotada): Mockar I/O e rodar calcular_health_score() completa.
  Funções internas (calcular_piotroski, calcular_crescimento, calcular_roic,
  calcular_momentum) são chamadas naturalmente pelo motor — sem necessidade
  de testá-las separadamente aqui.

  Nota: Usamos uma classe concreta (_FakeTicker) em vez de MagicMock para o
  objeto yfinance.Ticker, porque MagicMock pode ter comportamento inesperado
  com atributos de DataFrames dentro do engine.
"""
import json
import pathlib
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


# ═══════════════════════════════════════════════════════════════════════════════
# FakeTicker: substitute real do yfinance.Ticker para testes offline
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeTicker:
    """Objeto leve que emula a interface de yfinance.Ticker para testes."""

    def __init__(self, ticker_str: str = ""):
        self.ticker = ticker_str
        self.info: dict = {}
        self.financials: pd.DataFrame = pd.DataFrame()
        self.balance_sheet: pd.DataFrame = pd.DataFrame()
        self.cashflow: pd.DataFrame = pd.DataFrame()
        self.quarterly_financials: pd.DataFrame = pd.DataFrame()
        self.quarterly_balance_sheet: pd.DataFrame = pd.DataFrame()
        self._hist: pd.DataFrame = pd.DataFrame()

    def history(self, **kwargs) -> pd.DataFrame:
        return self._hist


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers: construir objetos a partir de fixtures JSON
# ═══════════════════════════════════════════════════════════════════════════════

def _build_yf_info(inputs: dict) -> dict:
    """Constrói o dict info que yfinance.Ticker.info retornaria."""
    info = dict(inputs.get("yf_info", {}))
    info.setdefault("sector", inputs.get("fundamentals", {}).get("setor", "Technology"))
    return info


def _build_dataframe(rows: dict, n_cols: int = 2) -> pd.DataFrame:
    """Constrói DataFrame financeiro no formato yfinance.

    rows: dict[str, list[float]] — nome_da_row → valores (col0=atual, col1=anterior)
    """
    dates = pd.date_range("2025-12-31", periods=n_cols, freq="-1YE")[::-1]
    data = {}
    for nome, valores in rows.items():
        data[nome] = [float(v) for v in valores[:n_cols]]
    return pd.DataFrame(data, index=dates[:n_cols]).T


def _build_price_history(tech: dict, n_rows: int = 260) -> pd.DataFrame:
    """Constrói DataFrame de histórico de preços a partir dos dados técnicos."""
    prices = tech.get("prices")
    if prices and len(prices) >= n_rows:
        close = prices[:n_rows]
    else:
        start = tech.get("start_price", 100)
        end = tech.get("end_price", 120)
        # Seed determinística entre processos: hash() de string em CPython usa
        # PYTHONHASHSEED=random por padrão, o que gera flakiness. Derivamos a
        # seed dos próprios bytes do float (estável).
        import struct
        seed = abs(struct.unpack("<I", struct.pack("<f", float(start)))[0]) % (2**31)
        np.random.seed(seed)
        noise = np.random.randn(n_rows) * (abs(end - start) / n_rows * 2)
        close = np.linspace(start, end, n_rows) + np.cumsum(noise) * 0.3
        close = list(close)

    dates = pd.date_range("2025-06-01", periods=len(close), freq="B")
    return pd.DataFrame({"Close": close}, index=dates)


def build_mocks_from_fixture(fixture: dict):
    """Retorna dados mock a partir de um fixture JSON."""
    inputs = fixture["inputs"]
    ticker = fixture["ticker"]

    # ── yfinance info ───────────────────────────────────────────────────
    yf_info = _build_yf_info(inputs)

    # ── DataFrames financeiros ──────────────────────────────────────────
    yf_fin_rows = inputs.get("yf_financials", {})
    yf_bs_rows = inputs.get("yf_balance_sheet", {})
    yf_cf_rows = inputs.get("yf_cashflow", {})

    fin_df = _build_dataframe(yf_fin_rows) if yf_fin_rows else pd.DataFrame()
    bs_df = _build_dataframe(yf_bs_rows) if yf_bs_rows else pd.DataFrame()
    cf_df = _build_dataframe(yf_cf_rows) if yf_cf_rows else pd.DataFrame()

    # ── Fake Ticker ─────────────────────────────────────────────────────
    fake_ticker = _FakeTicker(ticker)
    fake_ticker.info = yf_info
    fake_ticker.financials = fin_df
    fake_ticker.balance_sheet = bs_df
    fake_ticker.cashflow = cf_df

    # ── Histórico de preços ─────────────────────────────────────────────
    tech = inputs.get("tecnico", {})
    hist_df = _build_price_history(tech)
    fake_ticker._hist = hist_df

    # ── Cache do Supabase ───────────────────────────────────────────────
    fundamentals = dict(inputs.get("fundamentals", {}))
    dados_base = {
        "qualidade_dados": fundamentals.pop("qualidade_dados", 80),
        **fundamentals,
    }

    preco_cache_rsi = tech.get("rsi_14")
    preco_cache = {}
    if preco_cache_rsi is not None:
        preco_cache["rsi_14"] = float(preco_cache_rsi)
    if tech.get("end_price"):
        preco_cache["preco"] = float(tech["end_price"])

    # ── Macro context ───────────────────────────────────────────────────
    macro = dict(inputs.get("macro", {}))

    # ── Yield NTN-B (para FIIs) ─────────────────────────────────────────
    ntnb_yield = inputs.get("ntnb_yield", 6.8)

    return {
        "fake_ticker": fake_ticker,
        "dados_base": dados_base,
        "preco_cache": preco_cache,
        "macro": macro,
        "ntnb_yield": ntnb_yield,
        "hist_df": hist_df,
        "yf_info": yf_info,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Coleta de fixtures
# ═══════════════════════════════════════════════════════════════════════════════

def carregar_fixtures():
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.json"))


# ═══════════════════════════════════════════════════════════════════════════════
# Teste de regressão parametrizado
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("fixture_path", carregar_fixtures(), ids=lambda p: p.stem)
def test_regressao_score(fixture_path):
    """Garante que o score de cada fixture não move mais que a tolerância."""
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    ticker = data["ticker"]
    tipo = data["tipo"]
    expected = data["expected"]["score"]
    tolerancia = data["expected"].get("tolerancia", 2)

    m = build_mocks_from_fixture(data)

    with (
        patch("utils.health_engine.get_health_scores", return_value=[]),
        patch("utils.health_engine.get_todos_fundamentos_cache",
              return_value={ticker: m["dados_base"]}),
        patch("utils.health_engine.get_all_price_cache",
              return_value={ticker: m["preco_cache"]} if m["preco_cache"] else {}),
        patch("utils.health_engine.salvar_health_score"),
        patch("utils.health_engine.registrar_historico_score"),
        patch("utils.health_engine._buscar_yield_ntnb",
              return_value=m["ntnb_yield"]),
        patch("utils.health_engine.yf.Ticker", return_value=m["fake_ticker"]),
    ):
        from utils.health_engine import calcular_health_score

        resultado = calcular_health_score(
            ticker=ticker,
            macro_context=m["macro"],
            hist_externo=m["hist_df"],
            force=True,
        )

    score = resultado.get("score")
    assert score is not None, (
        f"score retornou None para {ticker} ({tipo}) — erro no cálculo"
    )
    diff = abs(score - expected)
    assert diff <= tolerancia, (
        f"Score regrediu para {ticker} ({tipo}): "
        f"esperado {expected} ± {tolerancia}, obtido {score} (diff {diff})"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Calibração auxiliar: roda o motor e retorna o score (usado por scripts externos)
# ═══════════════════════════════════════════════════════════════════════════════

def _calibrar_fixture(fixture_path: pathlib.Path):
    """Roda o motor com os inputs do fixture e retorna o score obtido."""
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    ticker = data["ticker"]
    m = build_mocks_from_fixture(data)

    with (
        patch("utils.health_engine.get_health_scores", return_value=[]),
        patch("utils.health_engine.get_todos_fundamentos_cache",
              return_value={ticker: m["dados_base"]}),
        patch("utils.health_engine.get_all_price_cache",
              return_value={ticker: m["preco_cache"]} if m["preco_cache"] else {}),
        patch("utils.health_engine.salvar_health_score"),
        patch("utils.health_engine.registrar_historico_score"),
        patch("utils.health_engine._buscar_yield_ntnb",
              return_value=m["ntnb_yield"]),
        patch("utils.health_engine.yf.Ticker", return_value=m["fake_ticker"]),
    ):
        from utils.health_engine import calcular_health_score

        resultado = calcular_health_score(
            ticker=ticker,
            macro_context=m["macro"],
            hist_externo=m["hist_df"],
            force=True,
        )
    return resultado.get("score")
