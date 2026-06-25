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


def normalizar_setor(setor: str | None) -> str:
    """
    Reduz um rótulo de setor (EN ou PT, com ou sem emoji) à chave canônica.
    Ex.: 'Financial Services' → 'financeiro'; '🏦 financeiro' → 'financeiro'.
    Devolve o texto em minúsculas se não reconhecer; '' para entrada vazia.
    """
    if not setor:
        return ""
    s = str(setor).strip().lower()
    # match por substring (cobre prefixos de emoji e sufixos tipo " br")
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
