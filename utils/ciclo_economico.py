"""Leitura heurística do ciclo BR/EUA com dados e cobertura explícitos.

Pontos relativos das quatro fases não são probabilidades calibradas. A descrição
setorial das fases é uma hipótese educacional de transmissão econômica. Este
módulo não estima Markov Switching nem reproduz a datação de recessões do NBER.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)

# Série de Close cacheada (Tier 3): consolida o padrão yf.Ticker().history().
from utils.market_data import close_series


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
            "indícios persistentes de recuperação da atividade após queda. "
            "A leitura depende dos dados publicados e pode ser revisada; "
            "não implica ativos baratos nem uma janela garantida de retorno."
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



from utils.regime_classifier import (
    numero_finito, valor_observado, recuperacao_persistente, ler_curva_10y_2y,
)


def _serie_valida(serie):
    """Não comprime lacunas internas ou troca o horizonte dos retornos."""
    if serie is None:
        return pd.Series(dtype=float)
    try:
        s = pd.Series(serie, dtype=float)
    except (TypeError, ValueError):
        return pd.Series(dtype=float)
    if s.empty or not np.isfinite(s.to_numpy()).all() or (s <= 0).any():
        return pd.Series(dtype=float)
    return s


def _retorno(serie, periodos):
    if len(serie) <= periodos:
        return None
    return float((serie.iloc[-1] / serie.iloc[-1 - periodos] - 1) * 100)


def _juro_real(nominal, inflacao):
    if nominal is None or inflacao is None or inflacao <= -100:
        return None
    return ((1 + nominal / 100) / (1 + inflacao / 100) - 1) * 100


def _finalizar(scores, indicadores, alertas, n_ind, total, recuperacao):
    # Pontos de estímulo ou uma queda forte no preço não identificam um fundo.
    if not recuperacao:
        scores['contracao'] += scores['vale']
        scores['vale'] = 0
    soma = sum(scores.values())
    normalizados = {k: round(v / soma * 100) if soma else 0 for k, v in scores.items()}
    fase = max(normalizados, key=normalizados.get) if soma and n_ind >= 3 else 'indefinido'
    ordenados = sorted(normalizados.values())
    diferenca = ordenados[-1] - ordenados[-2] if soma and fase != 'indefinido' else 0
    if n_ind < total:
        alertas.append(f'Cobertura {n_ind}/{total}: leituras ausentes não contam como favoráveis.')
    return {
        'indicadores': indicadores, 'alertas': alertas,
        **{f'score_{k}': v for k, v in normalizados.items()},
        'fase_provavel': fase, 'confianca': diferenca,
        'diferenca_pontos': diferenca, 'n_indicadores': n_ind,
        'cobertura': n_ind / total, 'recuperacao_confirmada': bool(recuperacao),
        'qualidade': {'status': 'suficiente' if n_ind == total else ('parcial' if n_ind >= 3 else 'insuficiente'),
                     'observados': n_ind, 'esperados': total},
        'metodologia': 'Pontos relativos por fase; não são probabilidades. Diferença em pontos percentuais.',
    }


def calcular_ciclo_br_dados(macro, series=None, atividade=None, expectativa_ipca=None):
    """Motor puro BR: os wrappers fazem o I/O e os testes injetam dados."""
    series = series or {}
    scores = dict.fromkeys(('expansao', 'pico', 'contracao', 'vale'), 0)
    indicadores, alertas, n_ind = {}, [], 0
    selic = valor_observado(macro, 'selic')
    ipca = valor_observado(macro, 'ipca_12m', 'ipca')
    real = _juro_real(selic, ipca)
    if real is not None:
        indicadores['selic_real'] = indicadores['selic_real_ex_post'] = round(real, 2)
        if real > 8:
            scores['contracao'] += 25; scores['pico'] += 15
            alertas.append(f'Juro real ex post elevado ({real:.1f}% Fisher); usa inflação já realizada.')
        elif real > 5:
            scores['pico'] += 20; scores['contracao'] += 10
        elif real > 2:
            scores['expansao'] += 20; scores['pico'] += 10
        elif real >= 0:
            scores['expansao'] += 25
        else:
            scores['expansao'] += 10
            alertas.append('Juro real ex post negativo não confirma recuperação da atividade.')
        n_ind += 1
    esperado = numero_finito(expectativa_ipca)
    ex_ante = _juro_real(selic, esperado)
    if ex_ante is not None:
        indicadores['selic_real_ex_ante_proxy'] = round(ex_ante, 2)
        alertas.append('Proxy ex ante: Selic atual constante versus inflação esperada em 12 meses; não é taxa real forward negociada.')

    imab = _serie_valida(series.get('IMAB11.SA'))
    b5 = _serie_valida(series.get('B5P211.SA'))
    if len(imab) > 20 and len(b5) > 20:
        # Diferença de retornos de ETFs não é inclinação da curva de taxas.
        indicadores['retorno_relativo_etfs_br'] = round(_retorno(imab, 20) - _retorno(b5, 20), 2)

    ibov = _serie_valida(series.get('^BVSP'))
    if len(ibov) >= 200:
        ret = _retorno(ibov, 126)
        acima = bool(ibov.iloc[-1] > ibov.tail(200).mean())
        indicadores.update(ibov_ret_6m=round(ret, 1), ibov_acima_mm200=acima)
        if ret > 15 and acima:
            scores['expansao'] += 20
        elif ret > 5 and acima:
            scores['expansao'] += 12; scores['pico'] += 8
        elif ret > 0:
            scores['pico'] += 10; scores['contracao'] += 10
        else:
            scores['contracao'] += 20
        n_ind += 1

    brl = _serie_valida(series.get('BRL=X'))
    if len(brl) >= 60:
        desvio = float((brl.iloc[-1] / brl.tail(60).mean() - 1) * 100)
        indicadores.update(usd_brl=round(float(brl.iloc[-1]), 2), usd_brl_vs_media=round(desvio, 1))
        if desvio > 10:
            scores['contracao'] += 15
        elif desvio > 3:
            scores['pico'] += 10; scores['contracao'] += 5
        elif desvio < -5:
            scores['expansao'] += 10
        n_ind += 1

    commodities = [_retorno(_serie_valida(series.get(t)), 63) for t in ('CL=F', 'TIO=F')]
    commodities = [v for v in commodities if v is not None]
    if commodities:
        ret = sum(commodities) / len(commodities)
        indicadores['commodities_ret_3m'] = round(ret, 1)
        if ret > 10:
            scores['expansao'] += 15; scores['pico'] += 5
        elif ret > 0:
            scores['expansao'] += 8
        elif ret > -10:
            scores['contracao'] += 8
        else:
            scores['contracao'] += 15
        n_ind += 1

    ibc = _serie_valida(atividade)
    recuperacao = False
    if len(ibc) >= 13:
        yoy, ret3 = _retorno(ibc, 12), _retorno(ibc, 3)
        recuperacao = bool(yoy < 0 and recuperacao_persistente(ibc) is True)
        indicadores.update(ibc_br_yoy=round(yoy, 2), ibc_br_3m=round(ret3, 2))
        if recuperacao:
            scores['vale'] += 50
            alertas.append('IBC-Br abaixo de um ano atrás, com duas altas mensais após duas quedas: indício persistente de recuperação.')
        elif yoy > 2.5 and ret3 > 0.3:
            scores['expansao'] += 25
        elif yoy > 1:
            scores['expansao'] += 15; scores['pico'] += 8
        elif yoy > 0 and ret3 > 0:
            scores['expansao'] += 10
        elif yoy < 0:
            scores['contracao'] += 20
        else:
            scores['pico'] += 10; scores['contracao'] += 5
        n_ind += 1
    return _finalizar(scores, indicadores, alertas, n_ind, 5, recuperacao)


def calcular_ciclo_us_dados(macro, series=None, curva=None, atividade=None):
    """Motor puro EUA; curva de yields observada e nenhuma taxa neutra inventada."""
    scores = dict.fromkeys(('expansao', 'pico', 'contracao', 'vale'), 0)
    indicadores, alertas, n_ind = {}, [], 0
    series, curva = series or {}, curva or {}
    slope = numero_finito(curva.get('slope'))
    if slope is not None:
        indicadores['yield_curve_spread'] = round(slope, 2)
        if slope > 1.5:
            scores['expansao'] += 25
        elif slope > 0.5:
            scores['expansao'] += 18; scores['pico'] += 7
        elif slope > 0:
            scores['pico'] += 15; scores['contracao'] += 10
        else:
            scores['contracao'] += 25
            alertas.append('Curva 10y−2y invertida: sinal financeiro de risco, sem datação automática de recessão.')
        n_ind += 1

    sp = _serie_valida(series.get('^GSPC'))
    if len(sp) >= 200:
        ret = _retorno(sp, 126)
        acima = bool(sp.iloc[-1] > sp.tail(200).mean())
        indicadores.update(sp500_ret_6m=round(ret, 1), sp500_acima_mm200=acima)
        if ret > 15 and acima:
            scores['expansao'] += 20
        elif ret > 5 and acima:
            scores['expansao'] += 12; scores['pico'] += 8
        elif ret > 0:
            scores['pico'] += 10; scores['contracao'] += 10
        else:
            scores['contracao'] += 20
        n_ind += 1

    hyg, ief = _serie_valida(series.get('HYG')), _serie_valida(series.get('IEF'))
    if len(hyg) > 63 and len(ief) > 63:
        comuns = hyg.index.intersection(ief.index)
        ratio = (hyg.reindex(comuns) / ief.reindex(comuns)).dropna()
        ret = _retorno(ratio, 63)
        if ret is not None:
            indicadores['hyg_ief_ret_relativo_3m'] = round(ret, 2)
            alertas.append('HYG/IEF é retorno relativo entre ETFs com duration distinta; não mede diretamente spread de crédito.')
            if ret > 2:
                scores['expansao'] += 15
            elif ret > 0:
                scores['expansao'] += 8
            elif ret > -2:
                scores['pico'] += 10; scores['contracao'] += 5
            else:
                scores['contracao'] += 15
            n_ind += 1

    ff = valor_observado(macro, 'fed_funds')
    neutro = valor_observado(macro, 'fed_neutral_nominal')
    if ff is not None:
        indicadores['fed_funds'] = ff
    if ff is not None and neutro is not None:
        gap = ff - neutro
        indicadores['fed_funds_gap'] = round(gap, 2)
        if gap > 2.5:
            scores['contracao'] += 20; scores['pico'] += 10
        elif gap > 0.5:
            scores['pico'] += 15; scores['contracao'] += 5
        elif gap >= -0.5:
            scores['expansao'] += 10; scores['pico'] += 10
        else:
            scores['expansao'] += 15
        n_ind += 1

    vix = valor_observado(macro, 'vix')
    if vix is not None:
        indicadores['vix'] = vix
        if vix < 15:
            scores['expansao'] += 10
        elif vix < 20:
            scores['expansao'] += 5; scores['pico'] += 5
        else:
            scores['contracao'] += 15
        n_ind += 1

    atividade = _serie_valida(atividade)
    recuperacao = False
    if len(atividade) >= 13:
        yoy, ret3 = _retorno(atividade, 12), _retorno(atividade, 3)
        recuperacao = bool(yoy < 0 and recuperacao_persistente(atividade) is True)
        indicadores.update(producao_industrial_yoy=round(yoy, 2), producao_industrial_3m=round(ret3, 2))
        if recuperacao:
            scores['vale'] += 50
        elif yoy < 0:
            scores['contracao'] += 25
        else:
            scores['expansao'] += 25 if ret3 > 0 else 10
        n_ind += 1
    return _finalizar(scores, indicadores, alertas, n_ind, 6, recuperacao)


def _precos(tickers):
    resultado = {}
    for ticker in tickers:
        try:
            resultado[ticker] = close_series(ticker, '1y')
        except Exception:
            resultado[ticker] = None
    return resultado


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_indicadores_ciclo_br(macro_context: dict | None = None) -> dict:
    """BR: juros ex post, preços e IBC-Br. Pontos relativos, não probabilidades."""
    macro = dict(macro_context if macro_context is not None else (st.session_state.get('macro_context', {}) or {}))
    atividade = None
    try:
        from bcb import sgs
        import datetime as dt
        inicio = (dt.date.today() - dt.timedelta(days=500)).isoformat()
        df = sgs.get({'ibc': 24364}, start=inicio)
        if df is not None and 'ibc' in df:
            atividade = df['ibc'].dropna().resample('MS').last()
    except Exception:
        logger.debug('IBC-Br indisponível', exc_info=True)
    expectativa = None
    try:
        from database.db import get_macro_cache
        expectativa = get_macro_cache('br_focus_ipca_12m')
    except Exception:
        pass
    precos = _precos(('IMAB11.SA', 'B5P211.SA', '^BVSP', 'BRL=X', 'CL=F', 'TIO=F'))
    return calcular_ciclo_br_dados(macro, precos, atividade, expectativa)


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_indicadores_ciclo_us(macro_context: dict | None = None) -> dict:
    """EUA: yields observados e sinais financeiros; sem preenchimento fictício."""
    macro = dict(macro_context if macro_context is not None else (st.session_state.get('macro_context', {}) or {}))
    atividade = None
    try:
        from utils.macro_supabase import carregar_snapshot
        df = carregar_snapshot('fred_global', max_age_days=30)
        if df is not None and 'INDPRO' in df:
            atividade = df['INDPRO'].dropna().resample('MS').last()
    except Exception:
        pass
    return calcular_ciclo_us_dados(macro, _precos(('^GSPC', 'HYG', 'IEF')), ler_curva_10y_2y(), atividade)


def get_alocacao_sugerida(fase_br: str, fase_us: str) -> dict:
    """Exemplo educacional fixo BR60/US40; somente para fases determinadas."""
    if fase_br not in FASES_CICLO or fase_us not in FASES_CICLO:
        return {}
    alloc_br, alloc_us = FASES_CICLO[fase_br]['alocacao_sugerida'], FASES_CICLO[fase_us]['alocacao_sugerida']
    resultado = {classe: round(alloc_br.get(classe, 0) * 0.60 + alloc_us.get(classe, 0) * 0.40) for classe in alloc_br}
    total = sum(resultado.values())
    return {classe: round(peso / total * 100) for classe, peso in resultado.items()} if total else {}
