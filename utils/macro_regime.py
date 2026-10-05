"""
utils/macro_regime.py
6 regimes macroeconomicos e rotacao setorial.
"""
from __future__ import annotations
from utils.st_fallback import st
from utils.logger import get_logger
from utils.regime_classifier import numero_finito, valor_observado

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

SETOR_NORMALIZE = {
    "tecnologia":             "tecnologia",
    "financeiro":             "bancos/financeiro",
    "consumo ciclico":        "consumo discricionario",
    "consumo discricionario": "consumo discricionario",
    "consumo def.":           "consumo basico",
    "consumo basico":         "consumo basico",
    "industria":              "industria",
    "materiais":              "commodities",
    "commodities":            "commodities",
    "energia":                "energia",
    "imobiliario":            "imobiliario",
    "utilities":              "utilities",
    "saude":                  "saude defensiva",
    "telecom":                "tecnologia",
    "saude defensiva":        "saude defensiva",
}


def classificar_regime(selic=None, vix=None, ipca=None, treasury_10y=None, *, macro_context=None):
    """Regime descritivo Selic × VIX; ausência nunca produz score observado.

    Sem argumentos usa o contexto da sessão com sua proveniência. Entradas
    explícitas são puras (ETL/histórico); o chamador que extrai valores do
    contexto deve passá-lo em ``macro_context`` para conservar a qualidade.
    IPCA/Treasury são contexto adicional e não entram na regra de classificação.
    """
    explicitos = {'selic':selic, 'vix':vix, 'ipca':ipca, 'treasury_10y':treasury_10y}
    ctx = macro_context
    if ctx is None:
        ctx = (st.session_state.get('macro_context', {}) or {}) if all(v is None for v in explicitos.values()) else {}
    aliases = {'ipca':('ipca_12m',)}
    valores = {}
    qualidade = {}
    for chave, valor in explicitos.items():
        nomes = (chave, *aliases.get(chave, ()))
        if valor is None:
            # IPCA do contrato atual é anual; prefere a chave explícita de 12m.
            nomes = ('ipca_12m', 'ipca') if chave == 'ipca' else nomes
            observado = valor_observado(ctx, *nomes)
        else:
            observado = numero_finito(valor)
            meta = (ctx.get('qualidade') or {})
            if any((meta.get(nome) or {}).get('observado') is False for nome in nomes):
                observado = None
        valores[chave] = observado
        qualidade[chave] = {'observado':observado is not None,
                            'status':'observado' if observado is not None else 'ausente'}
    selic, vix, ipca, treasury_10y = (valores[k] for k in explicitos)
    ausentes = [k for k, v in valores.items() if v is None]
    if selic is None or vix is None:
        return {
            'regime_key':'indefinido', 'label':'contexto macro incompleto',
            'descricao':'Selic e VIX observados são necessários para classificar juros e risco.',
            'setores_favorecidos':[], 'setores_prejudicados':[],
            'posicionamento':'Atualize os eixos ausentes antes de interpretar o regime.',
            'selic':selic, 'vix':vix, 'ipca':ipca, 'treasury_10y':treasury_10y,
            'score_ambiente':None, 'qualidade':qualidade, 'ausentes':ausentes,
            'cobertura_eixos':sum(v is not None for v in (selic, vix)) / 2,
        }
    if selic >= 13.0: jb = 'muito_altos'
    elif selic > 10.0: jb = 'altos'
    else: jb = 'baixos'
    rb = 'stress_global' if vix > 20 else 'risco_controlado'
    rk = f'juros_{jb}_{rb}'
    regime = REGIMES[rk]
    sa = 100 - 20 * (selic > 10) - 15 * (selic > 13) - 20 * (vix > 20) - 15 * (vix > 30)
    return {
        'regime_key':rk, 'label':regime['label'], 'descricao':regime['descricao'],
        'setores_favorecidos':regime['setores_favorecidos'],
        'setores_prejudicados':regime['setores_prejudicados'],
        'posicionamento':regime['posicionamento'],
        'selic':round(selic, 2), 'vix':round(vix, 1),
        'ipca':round(ipca, 1) if ipca is not None else None,
        'treasury_10y':round(treasury_10y, 2) if treasury_10y is not None else None,
        'score_ambiente':max(0, min(100, sa)), 'qualidade':qualidade,
        'ausentes':ausentes, 'cobertura_eixos':1.0,
    }


def get_impacto_setor(setor_nome=None, regime_dict=None):
    if regime_dict is None:
        regime_dict = classificar_regime()
    if regime_dict.get('regime_key') == 'indefinido':
        return {'setor_normalizado':setor_nome or 'desconhecido', 'impacto':'neutro',
                'cor':'#8A949E', 'justificativa':'Contexto macro incompleto; impacto setorial não determinado.'}
    sn = None
    for k, v in SETOR_NORMALIZE.items():
        if setor_nome and k.lower() in setor_nome.lower():
            sn = v; break
    if sn is None and setor_nome: sn = setor_nome.lower()
    if sn is None: sn = "desconhecido"
    fav = [s.lower() for s in regime_dict.get("setores_favorecidos", [])]
    prej = [s.lower() for s in regime_dict.get("setores_prejudicados", [])]
    sl = sn.lower()
    regime_label = regime_dict.get("label", "")
    if any(s in sl for s in fav):
        return {"setor_normalizado": sn, "impacto": "favoravel", "cor": "#00C853", "justificativa": f"setor favorecido no regime de {regime_label}"}
    elif any(p in sl for p in prej):
        return {"setor_normalizado": sn, "impacto": "desfavoravel", "cor": "#FF1744", "justificativa": f"setor prejudicado no regime de {regime_label}"}
    return {"setor_normalizado": sn, "impacto": "neutro", "cor": "#FF9900", "justificativa": "setor sem correlacao direta com o regime atual"}
