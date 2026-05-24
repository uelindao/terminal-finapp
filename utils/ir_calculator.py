"""
utils/ir_calculator.py
Calculadora de IR para investimentos no Brasil.

Regras vigentes (2024/2025):
- Ações BR:  isenção se vendas <= R$ 20.000/mês
             15% sobre lucro se vendas > R$ 20.000/mês
             20% se day trade (sem isenção)
- FIIs:      20% sobre ganho de capital (sem isenção de R$ 20k)
             Proventos de FII são isentos de IR para PF
- Ações EUA: 15% sobre lucro (sem isenção)
             Variação cambial é tributável separadamente
- Compensação de prejuízos: dentro da mesma categoria
"""

from utils.logger import get_logger

logger = get_logger(__name__)

# Alíquotas vigentes
ALIQUOTA_ACAO_NORMAL    = 0.15    # 15%
ALIQUOTA_DAY_TRADE      = 0.20    # 20%
ALIQUOTA_FII            = 0.20    # 20%
ALIQUOTA_ACAO_US        = 0.15    # 15%
LIMITE_ISENCAO_ACAO_BR  = 20_000.0  # R$ 20.000/mês


def calcular_ir_venda(
    ticker:           str,
    tipo_ativo:       str,    # 'acao_br' | 'fii' | 'acao_us'
    preco_compra:     float,
    preco_venda:      float,
    quantidade:       float,
    custo_operacao:   float = 0.0,
    day_trade:        bool  = False,
    total_vendas_mes: float = 0.0,   # soma de outras vendas no mês
    prejuizo_acum:    float = 0.0,   # saldo negativo acumulado
) -> dict:
    """
    Calcula IR de uma operação de venda.
    Retorna dict com todos os detalhes do cálculo.
    """
    custo_total = (preco_compra * quantidade) + custo_operacao
    receita     = preco_venda * quantidade
    lucro_bruto = receita - custo_total

    resultado = {
        'ticker':           ticker,
        'tipo_ativo':       tipo_ativo,
        'custo_total':      custo_total,
        'receita_venda':    receita,
        'lucro_bruto':      lucro_bruto,
        'prejuizo_comp':    0.0,
        'lucro_tributavel': 0.0,
        'aliquota':         0.0,
        'ir_devido':        0.0,
        'isento':           False,
        'day_trade':        day_trade,
        'regra_aplicada':   '',
        'observacoes':      [],
    }

    obs = resultado['observacoes']

    # ── AÇÕES BRASILEIRAS ────────────────────────────────────────────────────
    if tipo_ativo == 'acao_br':

        if day_trade:
            aliquota = ALIQUOTA_DAY_TRADE
            resultado['regra_aplicada'] = (
                "Day Trade: 20% sobre lucro, sem isenção"
            )
            obs.append("operação day trade — alíquota 20%, sem isenção de R$ 20k")

        else:
            vendas_com_atual = total_vendas_mes + receita

            if vendas_com_atual <= LIMITE_ISENCAO_ACAO_BR:
                resultado['isento']         = True
                resultado['regra_aplicada'] = (
                    f"Isento: vendas no mês "
                    f"(R$ {vendas_com_atual:,.2f}) <= R$ 20.000"
                )
                obs.append(
                    f"✅ isento: total de vendas no mês "
                    f"R$ {vendas_com_atual:,.2f} <= R$ 20.000"
                )
                return resultado

            aliquota = ALIQUOTA_ACAO_NORMAL
            resultado['regra_aplicada'] = (
                f"Tributado: vendas no mês "
                f"(R$ {vendas_com_atual:,.2f}) > R$ 20.000"
            )
            obs.append(
                f"⚠️ vendas acima de R$ 20.000 — lucro tributável a 15%"
            )

    # ── FIIs ─────────────────────────────────────────────────────────────────
    elif tipo_ativo == 'fii':
        aliquota = ALIQUOTA_FII
        resultado['regra_aplicada'] = (
            "FII: 20% sobre ganho de capital (sem isenção)"
        )
        obs.append(
            "proventos mensais de FII são isentos — "
            "apenas ganho de capital é tributado aqui"
        )

    # ── AÇÕES EUA ─────────────────────────────────────────────────────────────
    elif tipo_ativo == 'acao_us':
        aliquota = ALIQUOTA_ACAO_US
        resultado['regra_aplicada'] = "Ações EUA: 15% sobre lucro líquido"
        obs.append(
            "variação cambial na compra/venda pode gerar tributação adicional"
        )

    else:
        resultado['regra_aplicada'] = "tipo de ativo não reconhecido"
        return resultado

    # Compensação de prejuízo acumulado
    lucro_apos_comp = lucro_bruto

    if prejuizo_acum < 0 and lucro_bruto > 0:
        compensacao     = min(lucro_bruto, abs(prejuizo_acum))
        lucro_apos_comp = lucro_bruto - compensacao
        resultado['prejuizo_comp'] = compensacao
        obs.append(
            f"💡 prejuízo compensado: R$ {compensacao:,.2f} "
            f"(saldo anterior: R$ {prejuizo_acum:,.2f})"
        )

    resultado['lucro_tributavel'] = max(0.0, lucro_apos_comp)
    resultado['aliquota']         = aliquota

    if resultado['lucro_tributavel'] > 0:
        resultado['ir_devido'] = resultado['lucro_tributavel'] * aliquota
        obs.append(
            f"IR a recolher: R$ {resultado['ir_devido']:,.2f} "
            f"({aliquota * 100:.0f}% × "
            f"R$ {resultado['lucro_tributavel']:,.2f})"
        )
        obs.append(
            "⚡ prazo: DARF deve ser pago até o último dia "
            "útil do mês seguinte à operação"
        )
    elif lucro_bruto <= 0:
        obs.append(
            f"📋 prejuízo de R$ {abs(lucro_bruto):,.2f} — "
            "pode ser compensado em operações futuras da mesma categoria"
        )

    return resultado


def gerar_resumo_mensal(operacoes: list) -> dict:
    """
    Gera resumo de IR por categoria para um mês.
    operacoes: lista de resultados de calcular_ir_venda()
    """
    resumo = {
        'acao_br':   {'lucro': 0.0, 'ir': 0.0, 'isento': True,  'vendas': 0.0},
        'fii':       {'lucro': 0.0, 'ir': 0.0, 'isento': False, 'vendas': 0.0},
        'acao_us':   {'lucro': 0.0, 'ir': 0.0, 'isento': False, 'vendas': 0.0},
        'day_trade': {'lucro': 0.0, 'ir': 0.0, 'isento': False, 'vendas': 0.0},
        'total_ir':  0.0,
    }

    for op in operacoes:
        cat = 'day_trade' if op.get('day_trade') else op.get('tipo_ativo', 'acao_br')
        if cat in resumo:
            resumo[cat]['lucro']  += op.get('lucro_bruto', 0.0)
            resumo[cat]['ir']     += op.get('ir_devido', 0.0)
            resumo[cat]['vendas'] += op.get('receita_venda', 0.0)
            if not op.get('isento'):
                resumo[cat]['isento'] = False

    resumo['total_ir'] = sum(resumo[c]['ir'] for c in resumo if c != 'total_ir')
    return resumo
