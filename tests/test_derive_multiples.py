"""Testes de utils/derive_multiples — derivação de múltiplos ausentes."""
from utils.derive_multiples import derivar_multiplos, derivar_dy


def _hist_cvm():
    """Histórico estilo CVM: fluxos JÁ anualizados por período (usa T0)."""
    return [{
        "periodo": "2026-03-31", "_fonte": "cvm",
        "receita": 100.0, "lucro": 10.0, "ebit": 20.0, "ebitda": 25.0,
        "patrimonio": 50.0, "ativos_totais": 120.0,
        "divida_total": 30.0, "cash": 10.0, "shares": None,
    }]


def _hist_yf(lucro_por_tri=2.5):
    """Histórico estilo yfinance: fluxos POR TRIMESTRE (soma 4 = anual)."""
    q = {
        "receita": 25.0, "lucro": lucro_por_tri, "ebit": 5.0, "ebitda": 6.25,
        "patrimonio": 50.0, "ativos_totais": 120.0,
        "divida_total": 30.0, "cash": 10.0, "shares": 10.0,
    }
    return [dict(q, periodo=f"2026-{m:02d}-01") for m in (3, 1)] + \
           [dict(q, periodo=f"2025-{m:02d}-01") for m in (10, 7)]


def test_cvm_deriva_todos_multiplos():
    data = {"ticker": "X.SA", "setor": "industrials", "market_cap": 200.0,
            "p/l": None, "p/vp": None, "roe%": None, "margem%": None, "ev/ebitda": None}
    derivar_multiplos(data, _hist_cvm())
    assert data["p/l"] == 20.0          # 200 / 10
    assert data["p/vp"] == 4.0          # 200 / 50
    assert data["roe%"] == 20.0         # 10/50*100
    assert data["margem%"] == 10.0      # 10/100*100
    assert data["ev/ebitda"] == 8.8     # (200+30-10)/25
    assert data["_field_source"]["p/l"] == "derivado"


def test_yfinance_soma_4_trimestres():
    """yfinance: TTM = soma de 4 trimestres (4×2.5 = 10 anual), NÃO T0×algo."""
    data = {"ticker": "Y", "setor": "tech", "market_cap": 200.0,
            "p/l": None, "roe%": None, "margem%": None}
    derivar_multiplos(data, _hist_yf(2.5))
    assert data["p/l"] == 20.0          # 200 / (4×2.5)
    assert data["roe%"] == 20.0         # 10/50*100
    assert data["margem%"] == 10.0      # 10/(4×25)*100


def test_yfinance_menos_de_4_trimestres_nao_deriva_fluxo():
    data = {"ticker": "Y", "setor": "tech", "market_cap": 200.0, "p/l": None, "p/vp": None}
    hist = _hist_yf()[:2]  # só 2 trimestres
    derivar_multiplos(data, hist)
    assert data["p/l"] is None          # sem 4 trimestres não anualiza fluxo
    assert data["p/vp"] == 4.0          # patrimônio é snapshot → deriva


def test_market_cap_derivado_de_preco_x_acoes():
    data = {"ticker": "Y", "setor": "tech", "preco": 20.0, "market_cap": None, "p/vp": None}
    derivar_multiplos(data, _hist_yf())  # shares=10 no T0
    assert data["market_cap"] == 200.0  # 20 × 10
    assert data["p/vp"] == 4.0


def test_precedencia_nao_sobrescreve_provedor():
    data = {"ticker": "X.SA", "setor": "industrials", "market_cap": 200.0, "p/l": 15.0}
    derivar_multiplos(data, _hist_cvm())
    assert data["p/l"] == 15.0          # valor do provedor preservado
    assert "p/l" not in data.get("_field_source", {})


def test_banco_pula_ev_ebitda():
    data = {"ticker": "ITUB4.SA", "setor": "bancos", "nome": "itau unibanco",
            "market_cap": 200.0, "ev/ebitda": None, "roe%": None}
    derivar_multiplos(data, _hist_cvm())
    assert data["ev/ebitda"] is None    # banco não tem ev/ebitda convencional
    assert data["roe%"] == 20.0         # roe ainda deriva


def test_prejuizo_nao_deriva_pl_e_sinaliza():
    hist = _hist_cvm()
    hist[0]["lucro"] = -5.0
    data = {"ticker": "X.SA", "setor": "industrials", "market_cap": 200.0, "p/l": None}
    derivar_multiplos(data, hist)
    assert data["p/l"] is None
    assert data["_flags"]["prejuizo"] is True


def test_sanidade_descarta_absurdo():
    hist = _hist_cvm()
    hist[0]["patrimonio"] = 0.01   # p/vp = 200/0.01 = 20000 → fora do range
    data = {"ticker": "X.SA", "setor": "industrials", "market_cap": 200.0, "p/vp": None}
    derivar_multiplos(data, hist)
    assert data["p/vp"] is None    # descartado por range


def test_derivar_dy():
    data = {"ticker": "TAEE11.SA", "preco": 10.0, "dy%": None}
    derivar_dy(data, dividendos_12m=0.9)
    assert data["dy%"] == 9.0
    # precedência: não sobrescreve
    data2 = {"ticker": "X", "preco": 10.0, "dy%": 5.0}
    derivar_dy(data2, dividendos_12m=0.9)
    assert data2["dy%"] == 5.0
