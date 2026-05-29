"""
utils/macro_regime.py
6 regimes macroeconomicos e rotacao setorial.
"""
from __future__ import annotations
import streamlit as st
from utils.logger import get_logger
logger = get_logger(__name__)

REGIMES = {
    "juros_baixos_risco_controlado": {
        "label": "juros baixos / risco controlado",
        "descricao": "selic baixa (< 10%) e vix baixo (< 20) - ambiente ideal para risco.",
        "setores_favorecidos": ["tecnologia", "consumo discricionario", "industria", "imobiliario", "small caps"],
        "setores_prejudicados": ["utilities", "consumo basico", "saude defensiva"],
        "posicionamento": "risk-on: preferir crescimento, small caps e setores ciclicos.",
    },
    "juros_baixos_stress_global": {
        "label": "juros baixos / stress global",
        "descricao": "selic baixa mas vix elevado (> 20) - aversao a risco global.",
        "setores_favorecidos": ["utilities", "consumo basico", "ouro/commodities", "saude defensiva"],
        "setores_prejudicados": ["tecnologia", "small caps", "consumo discricionario", "imobiliario"],
        "posicionamento": "cauteloso: preferir defensivos e ativos reais.",
    },
    "juros_altos_risco_controlado": {
        "label": "juros altos / risco controlado",
        "descricao": "selic elevada (> 10%) mas vix baixo - juro restritivo comprime valuations locais.",
        "setores_favorecidos": ["bancos/financeiro", "energia", "commodities", "eua (sp500)"],
        "setores_prejudicados": ["imobiliario br", "consumo discricionario br", "small caps br", "fiis de tijolo"],
        "posicionamento": "seletivo: preferir renda fixa curta e setores que ganham com juro alto.",
    },
    "juros_altos_stress_global": {
        "label": "juros altos / stress global",
        "descricao": "juro restritivo + volatilidade global elevada - flight to quality.",
        "setores_favorecidos": ["caixa/renda fixa curta", "ouro", "dolar", "utilities defensivas"],
        "setores_prejudicados": ["tecnologia", "imobiliario", "small caps", "consumo discricionario", "bancos"],
        "posicionamento": "defensivo maximo: priorizar caixa, renda fixa pos-fixada e hedge cambial.",
    },
    "juros_muito_altos_risco_controlado": {
        "label": "juros muito altos / risco controlado",
        "descricao": "selic acima de 13% com vix baixo - juro proibitivo comprime a curva local.",
        "setores_favorecidos": ["renda fixa pos-fixada", "bancos (spread alto)", "commodities exportadoras"],
        "setores_prejudicados": ["fiis", "consumo", "industria local", "construcao civil", "small caps"],
        "posicionamento": "renda fixa primeiro: alocar em tesouro selic e CDBs.",
    },
    "juros_muito_altos_stress_global": {
        "label": "juros muito altos / stress global",
        "descricao": "selic > 13% + vix > 20 - tempestade perfeita para emergentes.",
        "setores_favorecidos": ["caixa", "dolar/hedge cambial", "ouro", "treasury eua curta"],
        "setores_prejudicados": ["todos os setores de risco", "acoes br", "fiis", "moedas emergentes"],
        "posicionamento": "protecao total: migrar para dolar, ouro e renda fixa curta global.",
    },
}

SETOR_NORMALIZE = {}
for k, v in {
    "tecnologia": "tecnologia", "financeiro": "bancos/financeiro",
    "consumo ciclico": "consumo discricionario", "consumo discricionario": "consumo discricionario",
    "consumo def.": "consumo basico", "consumo basico": "consumo basico",
    "industria": "industria", "materiais": "commodities", "commodities": "commodities",
    "energia": "energia", "imobiliario": "imobiliario",
    "utilities": "utilities", "saude": "saude defensiva",
    "telecom": "tecnologia", "saude defensiva": "saude defensiva",
}.items():
    SETOR_NORMALIZE[k] = v


def classificar_regime(selic=None, vix=None, ipca=None, treasury_10y=None):
    ctx = st.session_state.get("macro_context", {})
    if selic is None: selic = ctx.get("selic", 10.75)
    if vix is None: vix = ctx.get("vix", 15.0)
    if ipca is None: ipca = ctx.get("ipca", 4.5)
    if treasury_10y is None: treasury_10y = ctx.get("treasury_10y", 4.5)
    selic = float(selic); vix = float(vix)
    if selic >= 13.0: jb = "muito_altos"
    elif selic > 10.0: jb = "altos"
    else: jb = "baixos"
    rb = "stress_global" if vix > 20 else "risco_controlado"
    rk = f"juros_{jb}_{rb}"
    regime = REGIMES.get(rk, REGIMES["juros_altos_stress_global"])
    sa = 100
    if selic > 10: sa -= 20
    if selic > 13: sa -= 15
    if vix > 20: sa -= 20
    if vix > 30: sa -= 15
    sa = max(0, min(100, sa))
    return {
        "regime_key": rk, "label": regime["label"],
        "descricao": regime["descricao"],
        "setores_favorecidos": regime["setores_favorecidos"],
        "setores_prejudicados": regime["setores_prejudicados"],
        "posicionamento": regime["posicionamento"],
        "selic": round(selic, 2), "vix": round(vix, 1),
        "ipca": round(ipca, 1), "treasury_10y": round(treasury_10y, 2),
        "score_ambiente": sa,
    }


def get_impacto_setor(setor_nome=None, regime_dict=None):
    if regime_dict is None:
        regime_dict = classificar_regime()
    sn = None
    for k, v in SETOR_NORMALIZE.items():
        if setor_nome and k.lower() in setor_nome.lower():
            sn = v; break
    if sn is None and setor_nome: sn = setor_nome.lower()
    if sn is None: sn = "desconhecido"
    fav = [s.lower() for s in regime_dict.get("setores_favorecidos", [])]
    prej = [s.lower() for s in regime_dict.get("setores_prejudicados", [])]
    sl = sn.lower()
    if any(s in sl for s in fav):
        return {"setor_normalizado": sn, "impacto": "favoravel", "cor": "#00C853", "justificativa": f"setor favorecido no regime de {regime_dict[chr(108)+chr(97)+chr(98)+chr(101)+chr(108)]}"}
    elif any(p in sl for p in prej):
        return {"setor_normalizado": sn, "impacto": "desfavoravel", "cor": "#FF1744", "justificativa": f"setor prejudicado no regime de {regime_dict[chr(108)+chr(97)+chr(98)+chr(101)+chr(108)]}"}
    return {"setor_normalizado": sn, "impacto": "neutro", "cor": "#FF9900", "justificativa": "setor sem correlacao direta com o regime atual"}
