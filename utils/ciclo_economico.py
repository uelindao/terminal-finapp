"""
utils/ciclo_economico.py
Classificação quantitativa do ciclo econômico.

Metodologia:
- Leading indicators BR e EUA para determinar fase do ciclo
- Score composto de 0-100 por fase (expansão/pico/contração/vale)
- Recomendações setoriais baseadas em Fama-French e MSCI
- Atualização automática via yfinance e BCB

Fontes acadêmicas:
- Hamilton (1989): Markov Switching
- Fama & French (1989): Business conditions and expected returns
- NBER: Business Cycle Dating Committee methodology
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Definição das 4 fases e implicações setoriais ─────────────────────────────
# Baseado em Fama-French (1989) e MSCI Sector Rotation
FASES_CICLO = {
    "expansao": {
        "label":    "expansão",
        "label_en": "expansion / mid cycle",
        "cor":      "#00C853",
        "icone":    "📈",
        "descricao": (
            "crescimento acima do potencial. mercado de trabalho "
            "aquecido. inflação subindo moderadamente. lucros "
            "corporativos em alta. ambiente ideal para cíclicos."
        ),
        "leading_signals": [
            "yield curve positiva (10y > 2y)",
            "pmi manufacturing > 50 e subindo",
            "confiança do consumidor alta",
            "crédito expandindo",
        ],
        "setores_br": {
            "favorecidos": [
                "tecnologia / software",
                "consumo discricionário",
                "indústria / máquinas",
                "financeiro",
                "construção e engenharia",
            ],
            "evitar": [
                "utilities (elétrico)",
                "consumo básico",
                "telecomunicações",
            ],
        },
        "setores_us": {
            "favorecidos": ["technology", "consumer discretionary",
                           "industrials", "financials", "materials"],
            "evitar": ["utilities", "consumer staples", "real estate"],
        },
        "alocacao_sugerida": {
            "ações br":  55,
            "ações eua": 25,
            "fiis":      10,
            "renda fixa": 10,
        },
    },

    "pico": {
        "label":    "pico / desaceleração",
        "label_en": "late cycle / peak",
        "cor":      "#FF9900",
        "icone":    "⚠️",
        "descricao": (
            "crescimento máximo mas desacelerando. inflação no teto. "
            "banco central aperta política monetária. margem de lucro "
            "comprimida. rotação para defensivos começa."
        ),
        "leading_signals": [
            "yield curve achatando (spread 10y-2y < 0.5pp)",
            "pmi manufacturing > 50 mas caindo",
            "inflação acima da meta persistentemente",
            "banco central em ciclo de alta",
        ],
        "setores_br": {
            "favorecidos": [
                "energia",
                "mineração / siderurgia",
                "agronegócio / alimentos",
                "financeiro",
                "saúde",
            ],
            "evitar": [
                "tecnologia / software",
                "construção e engenharia",
                "varejo / consumo",
                "educação",
            ],
        },
        "setores_us": {
            "favorecidos": ["energy", "materials", "financials",
                           "healthcare"],
            "evitar": ["technology", "consumer discretionary",
                      "real estate"],
        },
        "alocacao_sugerida": {
            "ações br":  35,
            "ações eua": 20,
            "fiis":      10,
            "renda fixa": 35,
        },
    },

    "contracao": {
        "label":    "contração / recessão",
        "label_en": "recession / early downturn",
        "cor":      "#FF1744",
        "icone":    "📉",
        "descricao": (
            "crescimento abaixo do potencial ou negativo. desemprego "
            "subindo. lucros em queda. banco central inicia cortes. "
            "preservação de capital é prioridade máxima."
        ),
        "leading_signals": [
            "yield curve invertida (10y < 2y) ou muito plana",
            "pmi manufacturing < 50",
            "confiança do consumidor caindo",
            "crédito contraindo — spreads de crédito abrindo",
        ],
        "setores_br": {
            "favorecidos": [
                "consumo básico",
                "saúde",
                "utilities (elétrico)",
                "telecomunicações",
                "agronegócio / alimentos",
            ],
            "evitar": [
                "tecnologia / software",
                "indústria / máquinas",
                "construção e engenharia",
                "varejo / consumo",
                "siderurgia e metalurgia",
            ],
        },
        "setores_us": {
            "favorecidos": ["consumer staples", "healthcare",
                           "utilities", "communication services"],
            "evitar": ["technology", "industrials", "materials",
                      "consumer discretionary"],
        },
        "alocacao_sugerida": {
            "ações br":  20,
            "ações eua": 15,
            "fiis":      15,
            "renda fixa": 50,
        },
    },

    "vale": {
        "label":    "vale / recuperação inicial",
        "label_en": "trough / early recovery",
        "cor":      "#00B0FF",
        "icone":    "🔄",
        "descricao": (
            "crescimento no mínimo ou começando a se recuperar. "
            "banco central cortou juros agressivamente. ativos de "
            "risco extremamente descontados. melhor janela histórica "
            "para acumular cíclicos de qualidade."
        ),
        "leading_signals": [
            "yield curve normalizando (10y voltando > 2y)",
            "pmi manufacturing abaixo de 50 mas subindo",
            "banco central em ciclo de corte",
            "spreads de crédito fechando",
        ],
        "setores_br": {
            "favorecidos": [
                "construção e engenharia",
                "varejo / consumo",
                "tecnologia / software",
                "indústria / máquinas",
                "financeiro",
            ],
            "evitar": [
                "consumo básico",
                "utilities (elétrico)",
                "saúde",
            ],
        },
        "setores_us": {
            "favorecidos": ["consumer discretionary", "technology",
                           "industrials", "financials", "materials"],
            "evitar": ["consumer staples", "utilities", "healthcare"],
        },
        "alocacao_sugerida": {
            "ações br":  50,
            "ações eua": 25,
            "fiis":      15,
            "renda fixa": 10,
        },
    },
}


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_indicadores_ciclo_br() -> dict:
    """
    Calcula leading indicators do ciclo econômico brasileiro.

    Indicadores:
    1. Curva de juros BR (DI Jan26 vs DI Jan27 via proxy)
    2. IPCA acumulado 12m (proxy de pressão inflacionária)
    3. Selic real ex-ante (Selic - expectativa IPCA)
    4. Momentum do IBOV (proxy de confiança do mercado)
    5. Câmbio (USD/BRL) como proxy de aversão a risco
    6. Commodities (CRB Index via PDBC ou CL=F + GC=F)

    Retorna dict com scores e valores dos indicadores.
    """
    import yfinance as yf

    resultado = {
        'indicadores': {},
        'score_expansao':   0,
        'score_pico':       0,
        'score_contracao':  0,
        'score_vale':       0,
        'fase_provavel':    'expansao',
        'confianca':        0,
        'alertas':          [],
    }

    scores = {
        'expansao':  0,
        'pico':      0,
        'contracao': 0,
        'vale':      0,
    }
    n_ind = 0

    try:
        macro = st.session_state.get('macro_context', {})
        selic = float(macro.get('selic', 10.75))
        # 'ipca'/'ipca_12m' já são o acumulado 12m (% a.a.) — ver contrato em
        # utils/macro_context.py. 'ipca_mensal' é o print do mês (não usar aqui).
        ipca_12m = float(macro.get('ipca_12m') or macro.get('ipca', 4.5))

        # ── 1. Selic real (Selic - IPCA esperado) ────────────────────────
        # Selic real alta → aperto monetário → contração/pico
        # Selic real baixa → estímulo → vale/expansão
        _selic_real = selic - ipca_12m

        resultado['indicadores']['selic_real'] = round(_selic_real, 2)

        if _selic_real > 8.0:
            # Juro real muito alto — BC apertando forte
            scores['contracao'] += 25
            scores['pico']      += 15
            resultado['alertas'].append(
                f"⚠️ juro real muito alto ({_selic_real:.1f}%) — "
                f"aperto monetário severo"
            )
        elif _selic_real > 5.0:
            scores['pico']      += 20
            scores['contracao'] += 10
        elif _selic_real > 2.0:
            scores['expansao']  += 20
            scores['pico']      += 10
        elif _selic_real >= 0:
            scores['expansao']  += 25
            scores['vale']      += 15
        else:
            # Juro real negativo — estímulo máximo
            scores['vale']      += 25
            scores['expansao']  += 10
            resultado['alertas'].append(
                f"💡 juro real negativo ({_selic_real:.1f}%) — "
                f"política monetária estimulativa"
            )
        n_ind += 1

        # ── 2. Inclinação da curva IBOV (proxy yield curve BR) ────────────
        # Usa diferença entre ETFs de prazo diferente como proxy
        # IMA-B 5 (curto) vs IMA-B 5+ (longo) via IMAB11 e B5P211
        try:
            _imab = yf.Ticker('IMAB11.SA').history(
                period='3mo', auto_adjust=True
            )['Close'].dropna()
            _imab5p = yf.Ticker('B5P211.SA').history(
                period='3mo', auto_adjust=True
            )['Close'].dropna()

            if len(_imab) >= 20 and len(_imab5p) >= 20:
                _ret_longo = float(
                    _imab5p.iloc[-1] / _imab5p.iloc[-21] - 1
                ) * 100
                _ret_curto = float(
                    _imab.iloc[-1] / _imab.iloc[-21] - 1
                ) * 100
                _spread_curva = _ret_longo - _ret_curto

                resultado['indicadores']['spread_curva_br'] = (
                    round(_spread_curva, 2)
                )

                if _spread_curva > 1.0:
                    # Curva inclinada — mercado espera crescimento
                    scores['expansao'] += 20
                    scores['vale']     += 10
                elif _spread_curva > 0:
                    scores['expansao'] += 10
                    scores['pico']     += 10
                elif _spread_curva > -1.0:
                    scores['pico']      += 15
                    scores['contracao'] += 10
                else:
                    # Curva invertida — sinal recessivo
                    scores['contracao'] += 20
                    resultado['alertas'].append(
                        "🚨 curva de juros BR invertida — "
                        "sinal historicamente recessivo"
                    )
                n_ind += 1
        except Exception:
            pass

        # ── 3. Momentum do IBOV (proxy atividade econômica) ──────────────
        try:
            _ibov = yf.Ticker('^BVSP').history(
                period='1y', auto_adjust=True
            )['Close'].dropna()

            if len(_ibov) >= 252:
                _ibov_at   = float(_ibov.iloc[-1])
                _ibov_6m   = float(_ibov.iloc[-126])
                _ibov_mm200 = float(_ibov.rolling(200).mean().iloc[-1])
                _ret_6m    = (_ibov_at / _ibov_6m - 1) * 100

                resultado['indicadores']['ibov_ret_6m'] = (
                    round(_ret_6m, 1)
                )
                resultado['indicadores']['ibov_acima_mm200'] = (
                    _ibov_at > _ibov_mm200
                )

                if _ret_6m > 15 and _ibov_at > _ibov_mm200:
                    scores['expansao'] += 20
                elif _ret_6m > 5 and _ibov_at > _ibov_mm200:
                    scores['expansao'] += 12
                    scores['pico']     += 8
                elif _ret_6m > 0:
                    scores['pico']      += 10
                    scores['contracao'] += 10
                elif _ret_6m > -15:
                    scores['contracao'] += 15
                    scores['vale']      += 10
                else:
                    scores['contracao'] += 10
                    scores['vale']      += 20
                    resultado['alertas'].append(
                        f"📉 ibov caiu {_ret_6m:.1f}% em 6 meses — "
                        f"possível contração"
                    )
                n_ind += 1
        except Exception:
            pass

        # ── 4. Câmbio USD/BRL (proxy aversão a risco emergente) ──────────
        try:
            _brl = yf.Ticker('BRL=X').history(
                period='6mo', auto_adjust=True
            )['Close'].dropna()

            if len(_brl) >= 60:
                _brl_at   = float(_brl.iloc[-1])
                _brl_med  = float(_brl.rolling(60).mean().iloc[-1])
                _brl_desvio = (_brl_at / _brl_med - 1) * 100

                resultado['indicadores']['usd_brl'] = round(_brl_at, 2)
                resultado['indicadores']['usd_brl_vs_media'] = (
                    round(_brl_desvio, 1)
                )

                if _brl_desvio > 10:
                    # Dólar muito acima da média — stress/fuga de capital
                    scores['contracao'] += 15
                    resultado['alertas'].append(
                        f"⚠️ dólar {_brl_desvio:.1f}% acima da média "
                        f"— aversão a risco elevada"
                    )
                elif _brl_desvio > 3:
                    scores['pico']      += 10
                    scores['contracao'] += 5
                elif _brl_desvio < -5:
                    # Real apreciando — fluxo positivo
                    scores['expansao'] += 10
                n_ind += 1
        except Exception:
            pass

        # ── 5. Commodities (proxy demanda global + termos de troca BR) ───
        try:
            _oil = yf.Ticker('CL=F').history(
                period='6mo', auto_adjust=True
            )['Close'].dropna()
            _iron = yf.Ticker('TIO=F').history(
                period='6mo', auto_adjust=True
            )['Close'].dropna()

            _comm_score = 0
            _n_comm = 0

            for _ch, _cn in [(_oil, 'petróleo'), (_iron, 'minério')]:
                if len(_ch) >= 60:
                    _ret_c = float(_ch.iloc[-1] / _ch.iloc[-63] - 1) * 100
                    if _ret_c > 10:
                        _comm_score += 15
                    elif _ret_c > 0:
                        _comm_score += 8
                    elif _ret_c > -10:
                        _comm_score -= 5
                    else:
                        _comm_score -= 12
                    _n_comm += 1

            if _n_comm > 0:
                _avg_comm = _comm_score / _n_comm
                if _avg_comm > 10:
                    scores['expansao'] += 15
                    scores['pico']     += 5
                elif _avg_comm > 0:
                    scores['expansao'] += 8
                elif _avg_comm > -8:
                    scores['contracao'] += 8
                else:
                    scores['contracao'] += 15
                    scores['vale']      += 5
                n_ind += 1
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"[ciclo_br] erro: {e}")

    if n_ind == 0:
        resultado['fase_provavel'] = 'expansao'
        resultado['confianca']     = 0
        return resultado

    # Normaliza scores
    total_scores = sum(scores.values()) or 1
    for k in scores:
        scores[k] = round(scores[k] / total_scores * 100)

    # Fase com maior score
    fase_max = max(scores, key=lambda k: scores[k])
    confianca = scores[fase_max] - sorted(scores.values())[-2]

    resultado.update({
        'score_expansao':   scores['expansao'],
        'score_pico':       scores['pico'],
        'score_contracao':  scores['contracao'],
        'score_vale':       scores['vale'],
        'fase_provavel':    fase_max,
        'confianca':        confianca,
        'n_indicadores':    n_ind,
    })

    return resultado


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_indicadores_ciclo_us() -> dict:
    """
    Calcula leading indicators do ciclo econômico dos EUA.

    Indicadores usados (baseados em NBER e Conference Board LEI):
    1. Yield curve 10y-2y (inversão histórica = recessão em 6-18m)
    2. ISM Manufacturing PMI (via proxy — dados mensais)
    3. Fed Funds vs Neutro (r* de Taylor)
    4. S&P500 momentum (6 meses)
    5. Credit spreads (HYG vs IEF como proxy)
    6. Desemprego trend
    """
    import yfinance as yf

    resultado = {
        'indicadores': {},
        'score_expansao':   0,
        'score_pico':       0,
        'score_contracao':  0,
        'score_vale':       0,
        'fase_provavel':    'expansao',
        'confianca':        0,
        'alertas':          [],
    }

    scores = {
        'expansao':  0,
        'pico':      0,
        'contracao': 0,
        'vale':      0,
    }
    n_ind = 0

    try:
        macro = st.session_state.get('macro_context', {})
        treasury_10y = float(macro.get('treasury_10y', 4.5))

        # ── 1. Yield Curve 10y-2y (melhor predictor de recessão EUA) ────
        try:
            _t2y = yf.Ticker('^IRX').history(
                period='2d', auto_adjust=True
            )['Close'].dropna()
            if not _t2y.empty:
                _yield_2y = float(_t2y.iloc[-1]) / 100
                _spread_ycurve = treasury_10y - (_yield_2y * 100)

                resultado['indicadores']['yield_curve_spread'] = (
                    round(_spread_ycurve, 2)
                )

                if _spread_ycurve > 1.5:
                    # Curva íngreme — expansão/vale
                    scores['expansao'] += 25
                    scores['vale']     += 15
                elif _spread_ycurve > 0.5:
                    scores['expansao'] += 18
                    scores['pico']     += 7
                elif _spread_ycurve > 0:
                    scores['pico']      += 15
                    scores['contracao'] += 10
                elif _spread_ycurve > -0.5:
                    scores['contracao'] += 20
                    resultado['alertas'].append(
                        "⚠️ yield curve eua achatada — "
                        "historicamente precede recessão em 6-18 meses"
                    )
                else:
                    scores['contracao'] += 25
                    resultado['alertas'].append(
                        f"🚨 yield curve eua invertida "
                        f"({_spread_ycurve:.2f}pp) — "
                        f"sinal recessivo forte (nber: 8/8 recessões "
                        f"foram precedidas por inversão)"
                    )
                n_ind += 1
        except Exception:
            pass

        # ── 2. S&P500 Momentum (6 meses) ─────────────────────────────────
        try:
            _sp500 = yf.Ticker('^GSPC').history(
                period='1y', auto_adjust=True
            )['Close'].dropna()

            if len(_sp500) >= 126:
                _sp_at   = float(_sp500.iloc[-1])
                _sp_6m   = float(_sp500.iloc[-126])
                _sp_mm200 = float(_sp500.rolling(200).mean().iloc[-1])
                _ret_sp  = (_sp_at / _sp_6m - 1) * 100

                resultado['indicadores']['sp500_ret_6m'] = (
                    round(_ret_sp, 1)
                )
                resultado['indicadores']['sp500_acima_mm200'] = (
                    _sp_at > _sp_mm200
                )

                if _ret_sp > 15 and _sp_at > _sp_mm200:
                    scores['expansao'] += 20
                elif _ret_sp > 5 and _sp_at > _sp_mm200:
                    scores['expansao'] += 12
                    scores['pico']     += 8
                elif _ret_sp > 0:
                    scores['pico']      += 10
                    scores['contracao'] += 10
                elif _ret_sp > -15:
                    scores['contracao'] += 15
                    scores['vale']      += 10
                else:
                    scores['vale']      += 20
                    scores['contracao'] += 10
                n_ind += 1
        except Exception:
            pass

        # ── 3. Credit Spreads (HYG vs IEF) ───────────────────────────────
        # HYG = High Yield bonds, IEF = Investment Grade Treasuries
        # Spread abrindo = stress de crédito = recessão
        try:
            _hyg = yf.Ticker('HYG').history(
                period='6mo', auto_adjust=True
            )['Close'].dropna()
            _ief = yf.Ticker('IEF').history(
                period='6mo', auto_adjust=True
            )['Close'].dropna()

            if len(_hyg) >= 60 and len(_ief) >= 60:
                # Ratio HYG/IEF — caindo = spreads abrindo = stress
                _ratio_at   = float(_hyg.iloc[-1]) / float(_ief.iloc[-1])
                _ratio_3m   = float(_hyg.iloc[-63]) / float(_ief.iloc[-63]) if len(_hyg) >= 63 else _ratio_at
                _ratio_mud  = (_ratio_at / _ratio_3m - 1) * 100

                resultado['indicadores']['credit_spread_trend'] = (
                    round(_ratio_mud, 2)
                )

                if _ratio_mud > 2:
                    # Spreads fechando — risk-on
                    scores['expansao'] += 15
                    scores['vale']     += 10
                elif _ratio_mud > 0:
                    scores['expansao'] += 8
                elif _ratio_mud > -2:
                    scores['pico']      += 10
                    scores['contracao'] += 5
                else:
                    # Spreads abrindo — stress de crédito
                    scores['contracao'] += 15
                    resultado['alertas'].append(
                        "⚠️ spreads de crédito abrindo — "
                        "stress financeiro em formação"
                    )
                n_ind += 1
        except Exception:
            pass

        # ── 4. Fed Funds vs Neutro (r* Taylor Rule) ──────────────────────
        # r* estimado ≈ RPGAP (FRED) ou 2.5% (longo prazo)
        # Fed acima do neutro = aperto = favorece contração/pico
        try:
            _ff_rate = float(
                macro.get('fed_funds', 5.25)
                if 'fed_funds' in macro
                else 5.25
            )
            # r* estimado: 2.5% (Laubach-Williams, Fed NY)
            _r_star = 2.5
            _gap_politica = _ff_rate - _r_star

            resultado['indicadores']['fed_funds_gap'] = (
                round(_gap_politica, 2)
            )

            if _gap_politica > 2.5:
                # BC muito restritivo
                scores['contracao'] += 20
                scores['pico']      += 10
                resultado['alertas'].append(
                    f"⚠️ fed funds {_gap_politica:.1f}pp acima do "
                    f"neutro — aperto monetário intenso"
                )
            elif _gap_politica > 0.5:
                scores['pico']      += 15
                scores['contracao'] += 5
            elif _gap_politica > -0.5:
                scores['expansao']  += 10
                scores['pico']      += 10
            else:
                # BC estimulativo
                scores['expansao']  += 15
                scores['vale']      += 10
            n_ind += 1
        except Exception:
            pass

        # ── 5. VIX (aversão a risco) ──────────────────────────────────────
        try:
            _vix = float(macro.get('vix', 15.0))
            resultado['indicadores']['vix'] = _vix

            if _vix < 15:
                scores['expansao'] += 10
            elif _vix < 20:
                scores['expansao'] += 5
                scores['pico']     += 5
            elif _vix < 30:
                scores['contracao'] += 10
            else:
                scores['contracao'] += 15
                scores['vale']      += 5
                resultado['alertas'].append(
                    f"🚨 vix {_vix:.1f} — stress de mercado elevado"
                )
            n_ind += 1
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"[ciclo_us] erro: {e}")

    if n_ind == 0:
        resultado['fase_provavel'] = 'expansao'
        resultado['confianca']     = 0
        return resultado

    total_scores = sum(scores.values()) or 1
    for k in scores:
        scores[k] = round(scores[k] / total_scores * 100)

    fase_max  = max(scores, key=lambda k: scores[k])
    confianca = scores[fase_max] - sorted(scores.values())[-2]

    resultado.update({
        'score_expansao':   scores['expansao'],
        'score_pico':       scores['pico'],
        'score_contracao':  scores['contracao'],
        'score_vale':       scores['vale'],
        'fase_provavel':    fase_max,
        'confianca':        confianca,
        'n_indicadores':    n_ind,
    })

    return resultado


def get_alocacao_sugerida(fase_br: str, fase_us: str) -> dict:
    """
    Combina fase BR e EUA para gerar alocação sugerida ponderada.
    BR: 60% do peso (investidor brasileiro)
    EUA: 40% do peso
    """
    alloc_br = FASES_CICLO.get(fase_br, FASES_CICLO['expansao'])[
        'alocacao_sugerida'
    ]
    alloc_us = FASES_CICLO.get(fase_us, FASES_CICLO['expansao'])[
        'alocacao_sugerida'
    ]

    resultado = {}
    for classe in alloc_br:
        resultado[classe] = round(
            alloc_br.get(classe, 0) * 0.60
            + alloc_us.get(classe, 0) * 0.40
        )

    # Normaliza para 100%
    total = sum(resultado.values())
    if total > 0:
        for k in resultado:
            resultado[k] = round(resultado[k] / total * 100)

    return resultado
