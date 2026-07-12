"""
utils/setores.py
================
Taxonomia setorial CANÔNICA — fonte única para normalizar e rotular setores.

Antes havia ≥7 vocabulários de setor espalhados (normalizar_setor em macro_state,
SETOR_NORMALIZE em macro_regime, _normalizar_setor em risk_brinson, traduzir_setor
em formatters, _LABEL_SETOR em sector_scorecard, MULTIPLOS_SETOR em health_engine,
_TRANSMISSAO_* em inflation_sectoral) — a raiz de bugs silenciosos de cruzamento.

Este módulo é a referência: recebe rótulos EN (yfinance/FMP) ou PT (cache/CVM,
com ou sem emoji) e devolve UMA chave canônica + um rótulo de exibição.

Sem dependências externas — pode ser importado por qualquer módulo sem risco de
import circular.

Chaves canônicas:
  financeiro · tecnologia · energia · materiais · industria · consumo_ciclico ·
  consumo_defensivo · saude · utilities · imobiliario · comunicacao
"""
from __future__ import annotations

# Rótulo (EN yfinance/FMP, ou PT com/sem emoji) → chave canônica.
_SETOR_CANON: dict[str, str] = {
    # English (yfinance / FMP)
    "financial services":     "financeiro",
    "technology":             "tecnologia",
    "communication services": "comunicacao",
    "healthcare":             "saude",
    "consumer cyclical":      "consumo_ciclico",
    "consumer defensive":     "consumo_defensivo",
    "industrials":            "industria",
    "basic materials":        "materiais",
    "energy":                 "energia",
    "utilities":              "utilities",
    "real estate":            "imobiliario",
    # Portuguese (cache / CVM / traduzir_setor — podem vir com emoji prefixo)
    "financeiro":             "financeiro",
    "tecnologia":             "tecnologia",
    "telecom":                "comunicacao",
    "comunicação":            "comunicacao",
    "saúde":                  "saude",
    "consumo cíclico":        "consumo_ciclico",
    "consumo def.":           "consumo_defensivo",
    "consumo defensivo":      "consumo_defensivo",
    "consumo básico":         "consumo_defensivo",
    "indústria":              "industria",
    "materiais":              "materiais",
    "energia":                "energia",
    "imobiliário":            "imobiliario",
}

# Chave canônica → rótulo de exibição PT + emoji (mantém os labels de
# traduzir_setor, para zero mudança visível nas telas que já o usavam).
LABEL_SETOR: dict[str, str] = {
    "financeiro":        "🏦 financeiro",
    "tecnologia":        "💻 tecnologia",
    "energia":           "⛽ energia",
    "materiais":         "⛏️ materiais",
    "industria":         "🏭 indústria",
    "consumo_ciclico":   "🛒 consumo cíclico",
    "consumo_defensivo": "🛒 consumo def.",
    "saude":             "🏥 saúde",
    "utilities":         "⚡ utilities",
    "imobiliario":       "🏢 imobiliário",
    "comunicacao":       "📡 telecom",
}


# Subsetores GRANULARES da B3/Fundamentus (PT) → chave canônica. Match EXATO
# (após remover acentos) — evita os falsos-positivos do substring com nomes
# ambíguos (ex.: "comércio" vs "comércio e distribuição"). Chaves SEM acento.
_SETOR_CANON_B3: dict[str, str] = {
    # energia
    "petroleo, gas e biocombustiveis": "energia",
    "petroleo. gas e biocombustiveis": "energia",
    # materiais
    "mineracao": "materiais",
    "siderurgia e metalurgia": "materiais",
    "quimicos": "materiais",
    "madeira e papel": "materiais",
    "materiais diversos": "materiais",
    "embalagens": "materiais",
    # industria (bens industriais)
    "transporte": "industria",
    "material de transporte": "industria",
    "maquinas e equipamentos": "industria",
    "construcao e engenharia": "industria",
    "servicos diversos": "industria",
    "equipamentos eletricos": "industria",
    # consumo ciclico
    "comercio": "consumo_ciclico",
    "tecidos, vestuario e calcados": "consumo_ciclico",
    "utilidades domesticas": "consumo_ciclico",
    "automoveis e motocicletas": "consumo_ciclico",
    "hoteis e restaurantes": "consumo_ciclico",
    "viagens e lazer": "consumo_ciclico",
    "construcao civil": "consumo_ciclico",
    "diversos": "consumo_ciclico",
    # consumo defensivo (nao ciclico)
    "alimentos processados": "consumo_defensivo",
    "bebidas": "consumo_defensivo",
    "agropecuaria": "consumo_defensivo",
    "produtos de uso pessoal e de limpeza": "consumo_defensivo",
    "comercio e distribuicao": "consumo_defensivo",
    # saude
    "serv.med.hospit. analises e diagnosticos": "saude",
    "medicamentos e outros produtos": "saude",
    # financeiro
    "servicos financeiros diversos": "financeiro",
    "previdencia e seguros": "financeiro",
    "intermediarios financeiros": "financeiro",
    "holdings diversificadas": "financeiro",
    "bancos": "financeiro",
    # imobiliario
    "exploracao de imoveis": "imobiliario",
    "incorporacoes": "imobiliario",
    # utilities
    "energia eletrica": "utilities",
    "agua e saneamento": "utilities",
    "gas": "utilities",
    # tecnologia
    "programas e servicos": "tecnologia",
    "computadores e equipamentos": "tecnologia",
    # comunicacao
    "telecomunicacoes": "comunicacao",
    "midia": "comunicacao",
}


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_setor(setor: str | None) -> str:
    """
    Reduz um rótulo de setor (EN, PT amplo, ou subsetor granular B3) à chave
    canônica. Ex.: 'Financial Services' → 'financeiro'; 'Transporte' → 'industria';
    'Exploração de Imóveis' → 'imobiliario'. Devolve o texto em minúsculas se não
    reconhecer; '' para entrada vazia.
    """
    if not setor:
        return ""
    s = str(setor).strip().lower()
    # 1) subsetor B3 por match EXATO (sem acento) — preciso, sem falso-positivo
    s_na = _sem_acento(s)
    if s_na in _SETOR_CANON_B3:
        return _SETOR_CANON_B3[s_na]
    # 2) match por substring (EN/PT amplo; cobre prefixos de emoji e sufixos " br")
    for label, canon in _SETOR_CANON.items():
        if label in s:
            return canon
    return s


def label_setor(setor: str | None) -> str:
    """
    Rótulo de exibição (PT + emoji) a partir de um setor cru ou canônico.
    Compatível com a antiga traduzir_setor: setores conhecidos → mesmo label;
    desconhecidos → texto em minúsculas; vazio → '—'.
    """
    canon = normalizar_setor(setor)
    if not canon:
        return "—"
    return LABEL_SETOR.get(canon, canon)
