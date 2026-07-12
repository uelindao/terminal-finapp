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


def test_subsetores_b3_granulares():
    # subsetores granulares da B3 (o que o cache BR realmente guarda) → canônico
    casos = {
        "Transporte": "industria",
        "Alimentos Processados": "consumo_defensivo",
        "Petróleo, Gás e Biocombustíveis": "energia",
        "Exploração de Imóveis": "imobiliario",
        "Energia Elétrica": "utilities",           # NÃO 'energia' (petróleo)
        "Comércio": "consumo_ciclico",
        "Comércio e Distribuição": "consumo_defensivo",  # exato ≠ 'comércio'
        "Serviços Financeiros Diversos": "financeiro",
        "Previdência e Seguros": "financeiro",
        "Serv.Méd.Hospit. Análises e Diagnósticos": "saude",
        "Produtos de Uso Pessoal e de Limpeza": "consumo_defensivo",
        "Hoteis e Restaurantes": "consumo_ciclico",
        "Mineração": "materiais",
        "Telecomunicações": "comunicacao",
    }
    for raw, esperado in casos.items():
        assert normalizar_setor(raw) == esperado, f"{raw} -> {normalizar_setor(raw)}"


def test_subsetor_b3_todos_canonicos_validos():
    # todo alvo do mapa B3 é um canônico conhecido (tem LABEL_SETOR)
    from utils.setores import _SETOR_CANON_B3
    for canon in set(_SETOR_CANON_B3.values()):
        assert canon in LABEL_SETOR, canon


def test_energia_eletrica_nao_colide_com_energia():
    # regressão: 'energia elétrica' (utilities) não pode cair em 'energia' (petróleo)
    assert normalizar_setor("Energia Elétrica") == "utilities"
    assert normalizar_setor("Energy") == "energia"
