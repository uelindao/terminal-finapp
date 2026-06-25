"""
Testes da taxonomia setorial canônica (utils/setores) e da compat de
traduzir_setor (utils/formatters) após a consolidação.
"""
from utils.setores import normalizar_setor, label_setor, LABEL_SETOR
from utils.formatters import traduzir_setor


def test_normalizar_en_e_pt():
    assert normalizar_setor("Financial Services") == "financeiro"
    assert normalizar_setor("🏦 financeiro") == "financeiro"
    assert normalizar_setor("Consumer Cyclical") == "consumo_ciclico"
    assert normalizar_setor("Consumer Defensive") == "consumo_defensivo"
    assert normalizar_setor("Real Estate") == "imobiliario"
    assert normalizar_setor("Communication Services") == "comunicacao"
    assert normalizar_setor("") == ""
    assert normalizar_setor(None) == ""
    # desconhecido → minúsculas
    assert normalizar_setor("Algo Estranho") == "algo estranho"


def test_label_e_compat_traduzir():
    # labels GICS idênticos ao mapa antigo de traduzir_setor (TitleCase EN)
    esperado = {
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
    for raw, label in esperado.items():
        assert label_setor(raw) == label, raw
        assert traduzir_setor(raw) == label, raw   # delegação preserva os labels

    # vazio → "—"; desconhecido → minúsculas (mesma regra de antes)
    assert traduzir_setor("") == "—"
    assert traduzir_setor("Algo Estranho") == "algo estranho"


def test_label_setor_chaves_cobrem_canonicos():
    # todo canônico do _SETOR_CANON tem rótulo em LABEL_SETOR
    from utils.setores import _SETOR_CANON
    for canon in set(_SETOR_CANON.values()):
        assert canon in LABEL_SETOR, canon
