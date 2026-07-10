import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import datetime
import logging
import time

# silenciar alertas vermelhos do yahoo finance no terminal
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from utils.tickers import BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, get_opcoes_selectbox, ticker_from_label, mapear_ticker_base
from database.db import registrar_decisao, listar_decisoes, atualizar_resultado, get_pesos, listar_watchlist, salvar_peso, get_health_scores, listar_watchlists, criar_portfolio, listar_portfolios, get_portfolio_padrao, definir_portfolio_padrao, deletar_portfolio, salvar_peso_alvo, get_pesos_alvo, deletar_peso_alvo, get_todos_fundamentos_cache, salvar_mensagem_chat, get_historico_chat, limpar_historico_chat

# componentes do design system
from utils.components import (
    page_header, section_title, section_selector, metric_card, status_card, empty_state,
    inject_keyboard_shortcuts, tooltip, label_com_tooltip,
    handle_ticker_nav, ticker_nav_url, topbar,
    portfolio_hero, portfolio_kpis, info_box,
)
from utils.ai_client import chamar_ia, SYSTEM_PORTFOLIO
from utils.portfolio_importer import importar_planilha, TEMPLATE_CSV
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout, _cores as _chart_cores, _font_family_ui
from utils.logger import get_logger
from utils.price_history import obter_close_carteira

logger = get_logger(__name__)

# 1. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()
handle_ticker_nav()
try:
    from utils.themes import render_theme_switcher_sidebar
    render_theme_switcher_sidebar()
except Exception:
    pass
# Busca global de ativo — navegação de qualquer página para o deep dive (UX).
from utils.components import busca_global_sidebar
busca_global_sidebar()

_user_top_pf = get_current_user() or {}
topbar(
    breadcrumb_itens=[("⚡ finterminal", "/"), ("portfolio", None)],
    user_name=_user_top_pf.get('username', '') or _user_top_pf.get('nome', '') or 'usuário',
    sync_label="ao vivo",
)
page_header("💼 gestão de portfólio", "visão consolidada da sua carteira, backtesting e diário de decisões.")
# Barra de contexto macro sempre-on (regime/juro real/vix) — UX: nunca perder o pano de fundo.
try:
    from utils.macro_state import render_cockpit_macro as _rcm
    _rcm('BR')
except Exception:
    pass

@st.cache_data(ttl=3600, show_spinner=False)
def calcular_betas(tickers_tuple: tuple) -> dict:
    """Calcula beta de cada ativo contra IBOV e S&P500 usando 1 ano de dados.
    Lê preços do cache Supabase (price_history); cai para yfinance se vazio."""
    tickers = list(tickers_tuple)
    betas = {}
    try:
        benchmarks = ["^BVSP", "^GSPC"]
        todos = list(set([mapear_ticker_base(t) for t in tickers] + benchmarks))
        hist = obter_close_carteira(tuple(todos), periodo="1y")
        if hist.empty:
            raise ValueError("histórico vazio (cache + yfinance falhou)")
        if isinstance(hist, pd.Series):
            hist = hist.to_frame()
        rets = hist.pct_change().dropna()

        for t in tickers:
            t_base = mapear_ticker_base(t)
            if t_base not in rets.columns:
                betas[t] = {'beta_ibov': 1.0, 'beta_sp': 1.0, 'is_br': t.endswith('.SA')}
                continue

            is_br = t.endswith('.SA')
            benchmark = "^BVSP" if is_br else "^GSPC"

            if benchmark in rets.columns:
                cov = rets[[t_base, benchmark]].dropna().cov()
                var_bench = rets[benchmark].var()
                beta = cov.loc[t_base, benchmark] / var_bench if var_bench > 0 else 1.0
                beta = max(min(beta, 3.0), -1.0)
            else:
                beta = 1.0

            betas[t] = {
                'beta_ibov': round(beta, 2) if is_br else round(beta * 0.3, 2),
                'beta_sp': round(beta * 0.3, 2) if is_br else round(beta, 2),
                'is_br': is_br
            }
    except Exception as e:
        logger.warning(f"[portfolio] falha ao calcular betas: {e}")
        for t in tickers:
            betas[t] = {'beta_ibov': 1.0, 'beta_sp': 1.0, 'is_br': t.endswith('.SA')}

    return betas


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_matriz_correlacao(tickers_tuple: tuple, periodo: str = "1y") -> dict:
    """
    Calcula matriz de correlação entre os ativos do portfólio.
    Retorna dict com:
      - 'matriz': pd.DataFrame com correlações
      - 'alertas': list[str] pares com correlação > 0.70
      - 'diversificacao_score': int 0-100
    """
    tickers = list(tickers_tuple)
    resultado = {'matriz': None, 'alertas': [], 'diversificacao_score': 50}

    if len(tickers) < 2:
        return resultado

    try:
        tickers_base = [mapear_ticker_base(t) for t in tickers]
        hist = obter_close_carteira(tuple(tickers_base), periodo=periodo)

        if hist.empty:
            return resultado

        if isinstance(hist, pd.Series):
            hist = hist.to_frame(name=tickers_base[0])

        # Retornos diários
        rets = hist.pct_change().dropna()

        # Remove colunas com dados insuficientes
        rets = rets.dropna(axis=1, thresh=int(len(rets) * 0.7))

        if rets.shape[1] < 2:
            return resultado

        # Renomeia colunas para tickers originais
        mapa_reverso = {mapear_ticker_base(t): t for t in tickers}
        rets.columns = [mapa_reverso.get(c, c) for c in rets.columns]

        corr = rets.corr().round(2)
        resultado['matriz'] = corr

        # Alertas de alta correlação (pares > 0.70)
        alertas = []
        cols = corr.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                val = corr.iloc[i, j]
                if val > 0.70:
                    alertas.append(
                        f"{cols[i].replace('.SA','')} ↔ "
                        f"{cols[j].replace('.SA','')} — "
                        f"correlação {val:.2f} (alta)"
                    )
                elif val < -0.30:
                    alertas.append(
                        f"{cols[i].replace('.SA','')} ↔ "
                        f"{cols[j].replace('.SA','')} — "
                        f"correlação {val:.2f} (hedge natural)"
                    )
        resultado['alertas'] = alertas

        # Score de diversificação: 100 = correlação média próxima de 0
        # 0 = todos os ativos correlacionados > 0.9
        n = len(cols)
        if n > 1:
            vals_upper = [
                corr.iloc[i, j]
                for i in range(n)
                for j in range(i + 1, n)
            ]
            corr_media = float(np.mean(vals_upper)) if vals_upper else 0.5
            # Score: 0 de corr = 100 pts, 1.0 de corr = 0 pts
            score_div = int(max(0, min(100, (1 - corr_media) * 100)))
            resultado['diversificacao_score'] = score_div

    except Exception as e:
        logger.warning(f"[portfolio] correlação: {e}")

    return resultado


@st.cache_data(ttl=300, show_spinner=False)
def get_cambio_usd_brl() -> float:
    """Busca cotação atual do dólar via yfinance."""
    try:
        ticker_fx = yf.Ticker("BRL=X")
        hist_fx   = ticker_fx.history(period="1d")
        if not hist_fx.empty:
            return float(hist_fx['Close'].iloc[-1])
    except Exception as e:
        logger.warning(f"[portfolio] câmbio: {e}")
    return 5.80  # fallback


# ── Performance vs benchmarks ──────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def calcular_performance_vs_benchmarks(
    posicoes_tuple: tuple,
    periodo: str = "1y",
) -> dict:
    """
    Calcula performance consolidada da carteira vs benchmarks.

    Metodologia:
    - Carteira: retorno ponderado pelo valor de mercado atual
      de cada posição (TWR simplificado)
    - Benchmarks: BOVA11 (ibov), CDI via BCB, IVVB11 (s&p500 br),
      XFIX11 (ifix - fiis)

    Retorna dict com séries temporais e métricas comparativas.
    """
    import numpy as np

    posicoes = list(posicoes_tuple)
    if not posicoes:
        return {}

    resultado = {
        'series':   {},
        'metricas': {},
        'erros':    [],
    }

    try:
        from utils.tickers import mapear_ticker_base

        # Baixa histórico de todos os ativos + benchmarks
        _todos_tickers = [
            mapear_ticker_base(p[0]) for p in posicoes
        ]
        _benchmarks = {
            'ibovespa':    'BOVA11.SA',
            's&p500 (br)': 'IVVB11.SA',
            'ifix (fiis)': 'XFIX11.SA',
        }

        _todos = _todos_tickers + list(_benchmarks.values())

        _hist = obter_close_carteira(tuple(_todos), periodo=periodo)

        if isinstance(_hist, pd.Series):
            _hist = _hist.to_frame(name=_todos[0])

        _hist = _hist.dropna(how='all')

        if _hist.empty:
            return resultado

        # Retornos diários
        _rets = _hist.pct_change().dropna()

        # Série da carteira (ponderada por valor)
        _pesos = {}
        _valor_total = 0.0

        for _p in posicoes:
            _tk_base = mapear_ticker_base(_p[0])
            _qtd     = float(_p[1] or 0)
            _pm      = float(_p[2] or 0)
            _valor   = _qtd * _pm
            if _valor > 0 and _tk_base in _hist.columns:
                _pesos[_tk_base] = _valor
                _valor_total    += _valor

        if _valor_total == 0:
            return resultado

        for k in _pesos:
            _pesos[k] = _pesos[k] / _valor_total

        _ret_carteira = pd.Series(0.0, index=_rets.index)
        for _tk, _peso in _pesos.items():
            if _tk in _rets.columns:
                _ret_carteira += _rets[_tk].fillna(0) * _peso

        def _to_base100(serie: pd.Series) -> pd.Series:
            serie = serie.dropna()
            if serie.empty:
                return serie
            return (1 + serie).cumprod() * 100

        resultado['series']['minha carteira'] = _to_base100(_ret_carteira)

        for _nome, _ticker in _benchmarks.items():
            _tk_col = _ticker.replace('.SA', '')
            if _tk_col in _rets.columns:
                resultado['series'][_nome] = _to_base100(_rets[_tk_col].dropna())
            elif _ticker in _rets.columns:
                resultado['series'][_nome] = _to_base100(_rets[_ticker].dropna())

        # CDI via BCB
        try:
            from bcb import sgs
            import datetime
            _dias_periodo = {
                '3mo': 90, '6mo': 180, '1y': 365,
                '2y': 730, '3y': 1095,
            }.get(periodo, 365)
            _inicio_cdi = (
                datetime.datetime.today()
                - datetime.timedelta(days=_dias_periodo + 10)
            ).strftime('%Y-%m-%d')
            _df_cdi = sgs.get({'cdi': 12}, start=_inicio_cdi)
            if not _df_cdi.empty:
                _cdi_diario = _df_cdi['cdi'] / 100 / 252
                _cdi_diario = _cdi_diario.reindex(
                    _ret_carteira.index, method='ffill'
                ).fillna(_cdi_diario.mean())
                resultado['series']['cdi'] = _to_base100(_cdi_diario)
        except Exception:
            _selic = st.session_state.get(
                'macro_context', {}
            ).get('selic', 10.75)
            _cdi_aprox = pd.Series(
                (_selic / 100 / 252), index=_ret_carteira.index,
            )
            resultado['series']['cdi (aprox)'] = _to_base100(_cdi_aprox)

        # Métricas por série
        _selic_anual = st.session_state.get(
            'macro_context', {}
        ).get('selic', 10.75) / 100
        _rf_diario = _selic_anual / 252

        for _nome, _serie in resultado['series'].items():
            if _serie.empty:
                continue
            try:
                _ret_total = float(_serie.iloc[-1]) / 100 - 1
                _rets_d    = _serie.pct_change().dropna()
                _vol_anual = float(_rets_d.std() * np.sqrt(252) * 100)
                _sharpe = (
                    (_rets_d.mean() - _rf_diario) / _rets_d.std() * np.sqrt(252)
                ) if _rets_d.std() > 0 else 0.0

                _peak = _serie.cummax()
                _dd   = ((_serie - _peak) / _peak * 100)
                _max_dd = float(_dd.min())

                resultado['metricas'][_nome] = {
                    'retorno':  round(_ret_total * 100, 2),
                    'vol':      round(_vol_anual, 2),
                    'sharpe':   round(float(_sharpe), 2),
                    'drawdown': round(_max_dd, 2),
                }
            except Exception:
                pass

    except Exception as e:
        resultado['erros'].append(str(e))

    return resultado


# ── Score histórico via fontes externas ──────────────────────────────

def buscar_score_historico_externo(
    ticker: str,
) -> tuple[pd.Series | None, str]:
    """
    Busca score histórico de fontes externas na ordem:
    1. Alpha Vantage (via Supabase cache)
    2. FMP (somente para ativos EUA)
    3. BRAPI snapshot (apenas BR — para calibrar proxy)

    Retorna (serie_diaria | None, fonte_label)
    """
    _av_snap = None

    # ── Opção 1: Alpha Vantage + Supabase ────────────────────────
    try:
        from utils.alpha_vantage_client import calcular_score_historico_av
        _av = calcular_score_historico_av(ticker)
        if _av is not None and len(_av) >= 60:
            _max_v = float(_av.max())
            _min_v = float(_av.min())
            _std_v = float(_av.std())
            # Valida qualidade: precisa ter variação real
            if _std_v >= 2.0 and (_max_v - _min_v) >= 5:
                return _av, 'alpha_vantage'
            else:
                _av_snap = float(_av.median())
    except Exception:
        pass

    # ── Opção 2: FMP (somente EUA) ────────────────────────────────
    if not ticker.endswith('.SA'):
        try:
            from utils.fmp_client import get_multiplos_historicos
            t_clean  = ticker.upper()
            hist_fmp = get_multiplos_historicos(t_clean, anos=7)

            if hist_fmp and len(hist_fmp) >= 4:
                scores_fmp = {}
                for item in hist_fmp:
                    data = item.get('data', '')
                    if not data:
                        continue
                    s, m, ok = 0.0, 0.0, 0

                    pe  = item.get('pe')
                    m  += 15
                    if pe and 0 < pe <= 40:
                        ok += 1
                        if pe <= 12:   s += 15
                        elif pe <= 20: s += 10
                        elif pe <= 30: s += 5

                    roe = item.get('roe')
                    m  += 20
                    if roe is not None:
                        ok += 1
                        if roe > 20:   s += 20
                        elif roe > 12: s += 14
                        elif roe > 6:  s += 8
                        elif roe > 0:  s += 4
                        else:          s -= 5

                    roic = item.get('roic')
                    m   += 15
                    if roic is not None:
                        ok += 1
                        if roic > 15:   s += 15
                        elif roic > 8:  s += 10
                        elif roic > 0:  s += 5

                    mrg = item.get('margem')
                    m  += 15
                    if mrg is not None:
                        ok += 1
                        if mrg > 15:   s += 15
                        elif mrg > 8:  s += 10
                        elif mrg > 3:  s += 6
                        elif mrg >= 0: s += 2
                        else:          s -= 5

                    if ok >= 2 and m > 0:
                        scores_fmp[data] = round(
                            max(0, min(100, s / m * 100)), 1
                        )

                if len(scores_fmp) >= 3:
                    serie = pd.Series(scores_fmp)
                    serie.index = pd.to_datetime(serie.index)
                    serie = serie.sort_index()
                    datas = pd.date_range(
                        serie.index[0],
                        pd.Timestamp.today(), freq="B"
                    )
                    serie_d = serie.reindex(
                        datas, method="ffill"
                    ).rolling(5, min_periods=1).mean()
                    if float(serie_d.std()) >= 2.0:
                        return serie_d.round(1), 'fmp'
        except Exception:
            pass

    # ── Opção 3: BRAPI snapshot para calibração (apenas BR) ───────
    if ticker.endswith('.SA'):
        try:
            from utils.brapi_client import get_score_snapshot_brapi
            snap = get_score_snapshot_brapi(ticker)
            if snap is not None:
                return None, f'brapi_snapshot:{snap:.1f}'
        except Exception:
            pass

    # Se AV retornou dados mas sem variação, usa como calibração
    if _av_snap is not None:
        return None, f'av_snapshot:{_av_snap:.1f}'

    return None, 'sem_dados'


# ── Backtesting do health score ──────────────────────────────────────

@st.cache_data(ttl=7200, show_spinner=False)
def rodar_backtesting_score(
    ticker:              str,
    threshold_entrada:   int   = 55,
    threshold_saida:     int   = 35,
    periodo:             str   = "5y",
    capital_inicial:     float = 10000.0,
    custo_transacao_pct: float = 0.3,
) -> dict:
    """
    Simula estratégia baseada no health score histórico.

    Parâmetros:
        custo_transacao_pct: custo de ida+volta por operação (%)
            B3: ~0.3% (corretagem + emolumentos + ISS)
            EUA: ~0.1% (corretagem low cost)

    Períodos suportados:
        '1y', '2y', '3y', '5y', '10y', 'max'

    Limitações honestas (exibidas ao usuário):
        - Score proxy é técnico, não fundamentalista
        - Survivorship bias: só analisa ativos que sobreviveram
        - Look-ahead bias em períodos > 4 anos de fundamentals
        - Custos de transação simulados mas não incluem spread
          bid/ask, slippage de liquidez nem impostos (IR)
    """
    import numpy as np
    import datetime
    from utils.tickers import mapear_ticker_base
    from database.db import get_historico_score

    resultado = {
        'trades':   [],
        'series':   {},
        'metricas': {},
        'n_trades': 0,
        'erro':     None,
    }

    try:
        t_base = mapear_ticker_base(ticker)

        # Download de histórico com suporte a períodos longos
        _periodo_yf = periodo
        _corte_dias = None
        if periodo == '3y':
            _periodo_yf = '5y'
            _corte_dias = 3 * 365
        elif periodo == '10y':
            _periodo_yf = '10y'
        elif periodo == 'max':
            _periodo_yf = 'max'

        _hist_raw = yf.Ticker(t_base).history(
            period=_periodo_yf, auto_adjust=True
        )['Close'].dropna()

        if _corte_dias and len(_hist_raw) > _corte_dias:
            _hist = _hist_raw.iloc[-_corte_dias:]
        else:
            _hist = _hist_raw

        if getattr(_hist.index, 'tz', None) is not None:
            _hist.index = _hist.index.tz_localize(None)

        if len(_hist) < 60:
            resultado['erro'] = (
                "histórico de preços insuficiente para este ativo "
                "no período solicitado."
            )
            return resultado

        # ── PRIORIDADE DE FONTE DE SCORES ────────────────────────────────
        # 1ª opção: histórico real do banco (calculado pelo app)
        # 2ª opção: dados históricos do FMP (fundamentais reais)
        # 3ª opção: proxy técnico (fallback)

        _scores_raw = get_historico_score(ticker)
        _fonte_score = None
        _scores_serie = None

        # Opção 1: banco local
        if _scores_raw and len(_scores_raw) >= 10:
            try:
                _scores_dict = {}
                for _row in _scores_raw:
                    try:
                        _dt_s = pd.Timestamp(_row['data_hora'])
                        if getattr(_dt_s, 'tz', None) is not None:
                            _dt_s = _dt_s.tz_localize(None)
                        _scores_dict[_dt_s.date()] = int(_row['score'])
                    except Exception:
                        continue

                _score_vals = []
                _ultimo_score = 50
                for _dt in _hist.index:
                    _d = _dt.date() if hasattr(_dt, 'date') else _dt
                    if _d in _scores_dict:
                        _ultimo_score = _scores_dict[_d]
                    _score_vals.append(_ultimo_score)

                _scores_serie_candidata = pd.Series(
                    _score_vals, index=_hist.index, name='score'
                )

                # ── Verificação de qualidade dos dados ────────────
                # Se todos os scores são iguais (ou quase), os dados
                # são degenerados — provavelmente salvos com valor
                # default de 50. Nesse caso, descarta e usa FMP/proxy.
                _std_scores  = float(_scores_serie_candidata.std())
                _range_scores = (
                    float(_scores_serie_candidata.max())
                    - float(_scores_serie_candidata.min())
                )
                _n_unicos = _scores_serie_candidata.nunique()

                if _std_scores < 2.0 or _range_scores < 5 or _n_unicos < 3:
                    # Dados degenerados — avisa e descarta
                    resultado['aviso_banco'] = (
                        f"histórico local com {len(_scores_raw)} registros "
                        f"mas sem variação real (range {_range_scores:.0f} pts, "
                        f"{_n_unicos} valores únicos). "
                        "provavelmente scores salvos como default (50) antes "
                        "da calibração do motor. usando fmp ou proxy como fallback."
                    )
                    _scores_serie = None
                    _fonte_score  = None
                else:
                    _scores_serie = _scores_serie_candidata
                    _fonte_score = 'banco_local'

            except Exception:
                _scores_serie = None

        # Opção 2: Alpha Vantage / FMP / BRAPI (externo)
        if _scores_serie is None:
            with st.spinner(
                f"buscando dados fundamentalistas para {ticker} "
                f"(alpha vantage / fmp / brapi)..."
            ):
                _ext_serie, _ext_fonte = buscar_score_historico_externo(ticker)

            if _ext_serie is not None and len(_ext_serie) >= 60:
                try:
                    _hist_idx = _hist.index
                    if getattr(_hist_idx, 'tz', None) is not None:
                        _hist_idx = _hist_idx.tz_localize(None)
                    _ext_alinhada = _ext_serie.reindex(
                        _hist_idx, method='ffill'
                    ).fillna(50)
                    _scores_serie = _ext_alinhada.rename('score')
                    _fonte_score  = _ext_fonte
                except Exception:
                    _scores_serie = None

        # Opção 3: Proxy técnico + calibração BRAPI (fallback final)
        if _scores_serie is None:
            _fonte_score = 'proxy_tecnico'

            # ── PROXY DE SCORE TÉCNICO-QUANTITATIVO ──────────────────
            from utils.indicators import rsi as _rsi_series
            _rsi     = _rsi_series(_hist, 14).fillna(50)

            _mom_12_1 = pd.Series(np.nan, index=_hist.index)
            if len(_hist) >= 252:
                _preco_12m = _hist.shift(252)
                _preco_1m  = _hist.shift(21)
                _mom_12_1  = ((_preco_1m / _preco_12m) - 1) * 100
            _mom_12_1_norm = ((_mom_12_1.clip(-50, 50) + 50) / 100 * 100).fillna(50)

            _mm50   = _hist.rolling(50).mean()
            _mm200  = _hist.rolling(200).mean()
            _mm_ref = _mm200.where(_mm200.notna(), _mm50)
            _trend  = (_hist > _mm_ref).astype(float) * 100

            _vol_20d  = _hist.pct_change().rolling(20).std() * np.sqrt(252)
            _vol_pct  = _vol_20d.rank(pct=True) * 100
            _low_vol  = (100 - _vol_pct).fillna(50)

            if len(_hist) >= 252:
                _high_52w = _hist.rolling(252).max()
                _low_52w  = _hist.rolling(252).min()
                _range_52w = ((_hist - _low_52w) / (_high_52w - _low_52w + 1e-10) * 100).fillna(50)
            else:
                _range_52w = pd.Series(50.0, index=_hist.index)

            _mom_1m = _hist.pct_change(21) * 100
            _mom_3m = _hist.pct_change(63) * 100
            _aceleracao = (_mom_1m > _mom_3m / 3).astype(float) * 100

            _score_proxy = (
                _mom_12_1_norm * 0.30 + _trend * 0.25 + _rsi * 0.15
                + _low_vol * 0.10 + _range_52w * 0.15 + _aceleracao * 0.05
            ).fillna(50).clip(0, 100)

            _scores_serie = _score_proxy.rename('score')

            # ── Calibração por snapshot (BRAPI ou AV) ────────────────
            _snap_val = None
            if isinstance(_ext_fonte, str):
                for _prefix in ('brapi_snapshot:', 'av_snapshot:'):
                    if _ext_fonte.startswith(_prefix):
                        try:
                            _snap_val = float(
                                _ext_fonte.replace(_prefix, '')
                            )
                        except Exception:
                            pass
                        break

            if _snap_val is not None and _scores_serie is not None:
                _proxy_mean  = float(_scores_serie.mean())
                _delta       = _snap_val - _proxy_mean
                _scores_cal  = (_scores_serie + _delta).clip(0, 100)
                _scores_serie = _scores_cal.rename('score')
                _fonte_score  = 'proxy_calibrado'
                _fonte_label  = (
                    'alpha_vantage' if 'av_snapshot' in _ext_fonte
                    else 'brapi'
                )
                resultado['aviso'] = (
                    f"proxy técnico calibrado com snapshot "
                    f"fundamentalista ({_fonte_label}: "
                    f"{_snap_val:.0f}/100). "
                    "a variação histórica é técnica; o nível reflete "
                    "os fundamentos atuais do ativo."
                )
            elif _scores_serie is not None:
                _fonte_score = 'proxy_tecnico'
                resultado['aviso'] = (
                    "score proxy puramente técnico — sem dados "
                    "fundamentalistas disponíveis (alpha vantage e "
                    "brapi sem cobertura para este ativo)."
                )

        resultado['fonte_score'] = _fonte_score

        # ── Diagnóstico de APIs externas ──────────────────────────────
        # Só interessa quando caiu em proxy (fundamentalistas falharam)
        if _fonte_score in ('proxy_tecnico', 'proxy_calibrado'):
            from utils.api_cache import get_av_rotator
            if not get_av_rotator().keys:
                resultado['aviso_av_key'] = (
                    "Alpha Vantage API key nao configurada. "
                    "adicione no Streamlit Cloud: Settings > Secrets > [alpha_vantage] api_key"
                )

            try:
                import requests as _req
                _r_av = _req.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "OVERVIEW", "symbol": "PETR4.SAO", "apikey": "demo"},
                    timeout=5,
                )
                if _r_av.status_code == 200:
                    _j = _r_av.json()
                    if "Note" in _j or "Information" in _j:
                        resultado['aviso_av_limite'] = (
                            "Alpha Vantage: limite de requisicoes diarias atingido (25/dia). "
                            "os dados fundamentalistas serao usados amanha."
                        )
            except Exception:
                pass

            try:
                _fmp_keys = []
                for _k_name in ("FMP_API_KEY", "FMP_API_KEY_2"):
                    _k = st.secrets.get(_k_name, "")
                    if _k: _fmp_keys.append(_k)

                if not _fmp_keys:
                    resultado['aviso_fmp_key'] = (
                        "Financial Modeling Prep API keys nao configuradas no secrets.toml."
                    )
                else:
                    _falhas = []
                    for _fk in _fmp_keys:
                        _rf = _req.get(
                            f"https://financialmodelingprep.com/stable/ratios",
                            params={"symbol": "PETR4", "limit": 1, "apikey": _fk},
                            timeout=5,
                        )
                        if _rf.status_code == 403:
                            _falhas.append(_fk[:8])

                    if len(_falhas) == len(_fmp_keys):
                        resultado['aviso_fmp_403'] = (
                            f"todas as {len(_fmp_keys)} FMP API keys bloqueadas (403). "
                            f"ultima testada: {_fmp_keys[-1][:8]}... "
                            "gere novas chaves em financialmodelingprep.com."
                        )
                    elif _falhas:
                        resultado['aviso_fmp_403'] = (
                            f"{len(_falhas)} de {len(_fmp_keys)} FMP key(s) bloqueadas: "
                            f"{', '.join(f'{f}...' for f in _falhas)}. "
                            "as demais estao funcionando."
                        )
            except Exception:
                pass

            try:
                from utils.brapi_client import _get_token as _brapi_token
                if not _brapi_token():
                    resultado['aviso_brapi_key'] = (
                        "BRAPI token nao configurado. "
                        "adicione no Streamlit Cloud: Settings > Secrets > [brapi] token"
                    )
            except Exception:
                pass

        n_anos = len(_hist) / 252
        resultado['score_distribution'] = {
            'mediana':   round(float(_scores_serie.median()), 1),
            'p25':       round(float(_scores_serie.quantile(0.25)), 1),
            'p75':       round(float(_scores_serie.quantile(0.75)), 1),
            'p10':       round(float(_scores_serie.quantile(0.10)), 1),
            'p90':       round(float(_scores_serie.quantile(0.90)), 1),
            'min':       round(float(_scores_serie.min()), 1),
            'max':       round(float(_scores_serie.max()), 1),
            'n_pregoes': len(_scores_serie),
            'n_anos':    round(n_anos, 1),
        }

        # ── CDI via BCB (série 12 = taxa DIÁRIA em %) ────────────────
        _cdi_taxa_diaria = {}
        _cdi_taxa_fallback = (1 + 10.75 / 100) ** (1 / 252) - 1
        _cdi_acum_serie = None

        try:
            from bcb import sgs as _sgs_bt

            _inicio_str = (
                _hist.index[0].strftime('%Y-%m-%d')
                if hasattr(_hist.index[0], 'strftime')
                else str(_hist.index[0])[:10]
            )

            _df_cdi_raw = _sgs_bt.get({'cdi': 12}, start=_inicio_str)

            if not _df_cdi_raw.empty and 'cdi' in _df_cdi_raw.columns:
                _serie_bcb = _df_cdi_raw['cdi'].dropna()

                if getattr(_serie_bcb.index, 'tz', None) is not None:
                    _serie_bcb.index = _serie_bcb.index.tz_localize(None)

                # BCB série 12 = taxa DIÁRIA em % (ex: 0.042)
                # Converte para decimal: divide por 100
                _serie_diaria_decimal = _serie_bcb / 100

                for _dt_bcb, _taxa in _serie_diaria_decimal.items():
                    _d_key = _dt_bcb.date() if hasattr(_dt_bcb, 'date') else _dt_bcb
                    _cdi_taxa_diaria[_d_key] = float(_taxa)

                if _cdi_taxa_diaria:
                    _cdi_taxa_fallback = float(_serie_diaria_decimal.mean())

                _cdi_alinhado = _serie_diaria_decimal.reindex(_hist.index, method='ffill').fillna(_cdi_taxa_fallback)
                _cdi_acum_serie = (1 + _cdi_alinhado).cumprod() * capital_inicial

        except Exception:
            pass

        if _cdi_acum_serie is None:
            _selic_aa = st.session_state.get('macro_context', {}).get('selic', 10.75)
            _cdi_taxa_fallback = (1 + _selic_aa / 100) ** (1 / 252) - 1
            _cdi_acum_serie = pd.Series(
                [capital_inicial * ((1 + _cdi_taxa_fallback) ** i) for i in range(len(_hist))],
                index=_hist.index,
            )

        resultado['series']['cdi'] = _cdi_acum_serie / capital_inicial * 100

        # Salva série do score para visualização
        resultado['serie_score'] = _scores_serie.copy()

        # Debug do CDI — confirma valores
        if _cdi_acum_serie is not None and not _cdi_acum_serie.empty:
            _cdi_retorno_total = float(
                _cdi_acum_serie.iloc[-1] / capital_inicial - 1
            ) * 100
            _n_dias_cdi = len(_cdi_acum_serie)
            _n_anos_cdi = _n_dias_cdi / 252
            _cdi_cagr = (
                (1 + _cdi_retorno_total / 100) ** (1 / _n_anos_cdi) - 1
            ) * 100 if _n_anos_cdi > 0 else 0

            resultado['cdi_debug'] = {
                'retorno_total':  round(_cdi_retorno_total, 2),
                'cagr_anual':     round(_cdi_cagr, 2),
                'n_dias':         _n_dias_cdi,
                'n_anos':         round(_n_anos_cdi, 2),
                'taxa_media_dia': round(
                    float(_cdi_taxa_fallback) * 100, 5
                ),
            }

        # ── Simulação da estratégia ─────────────────────────────────────
        _capital       = capital_inicial
        _capital_bh    = capital_inicial
        _posicao       = False
        _preco_compra  = None
        _trades        = []
        _capital_serie = [capital_inicial]
        _bh_serie      = [capital_inicial]
        _dias_investido = 0

        _preco_ant = float(_hist.iloc[0])

        for _i in range(1, len(_hist)):
            _dt      = _hist.index[_i]
            _preco   = float(_hist.iloc[_i])
            _score   = float(_scores_serie.iloc[_i])
            _ret_dia = (_preco / _preco_ant) - 1.0
            _preco_ant = _preco

            _capital_bh = _capital_bh * (1.0 + _ret_dia)

            if _posicao:
                _capital = _capital * (1.0 + _ret_dia)
                _dias_investido += 1
            else:
                _dt_key  = _dt.date() if hasattr(_dt, 'date') else _dt
                _taxa_cdi_d = _cdi_taxa_diaria.get(_dt_key, _cdi_taxa_fallback)
                _capital = _capital * (1.0 + _taxa_cdi_d)

            if not _posicao and _score >= threshold_entrada:
                _custo_entrada = custo_transacao_pct / 200.0
                _capital      *= (1.0 - _custo_entrada)
                _posicao       = True
                _preco_compra  = _preco * (1.0 + _custo_entrada)
                _trades.append({
                    'tipo':  'compra',
                    'data':  str(_dt)[:10],
                    'preco': round(_preco, 2),
                    'score': round(_score, 1),
                })

            elif _posicao and _score < threshold_saida:
                _custo_saida = custo_transacao_pct / 200.0
                _capital    *= (1.0 - _custo_saida)
                _ret_trade   = (
                    (_preco * (1.0 - _custo_saida)) / _preco_compra - 1.0
                    if _preco_compra else 0.0
                )
                _posicao      = False
                _preco_compra = None
                _trades.append({
                    'tipo':           'venda',
                    'data':           str(_dt)[:10],
                    'preco':          round(_preco, 2),
                    'score':          round(_score, 1),
                    'retorno_trade':  round(_ret_trade * 100, 2),
                })

            _capital_serie.append(_capital)
            _bh_serie.append(_capital_bh)

        _cap_serie_pd = pd.Series(_capital_serie, index=_hist.index, dtype=float)
        _bh_serie_pd  = pd.Series(_bh_serie, index=_hist.index, dtype=float)

        resultado['series']['estratégia (score)'] = (
            _cap_serie_pd / capital_inicial * 100.0
        )
        resultado['series'][f'buy & hold ({ticker.replace(".SA","")})'] = (
            _bh_serie_pd / capital_inicial * 100.0
        )
        resultado['trades']            = _trades
        resultado['n_trades']          = sum(1 for t in _trades if t['tipo'] == 'compra')
        resultado['pct_tempo_investido'] = round(
            _dias_investido / max(len(_hist) - 1, 1) * 100, 1
        )

        if resultado['pct_tempo_investido'] >= 99:
            _ret_est = float(_cap_serie_pd.iloc[-1] / capital_inicial - 1)
            _ret_bh  = float(_bh_serie_pd.iloc[-1] / capital_inicial - 1)
            if abs(_ret_est - _ret_bh) > 0.02:
                resultado['aviso_sanidade'] = (
                    f"⚠️ divergência detectada: estratégia {_ret_est*100:+.1f}% "
                    f"vs b&h {_ret_bh*100:+.1f}% mesmo 100% investida. "
                    f"verifique dados de preço e score."
                )

        # CDI já está base 100 em resultado['series']['cdi']

        # Métricas finais com CAGR, Calmar, % dias positivos
        def _calc_metricas(serie_b100: pd.Series, nome: str, is_renda_fixa: bool = False) -> dict:
            _rets_d  = serie_b100.pct_change().dropna()
            _ret_tot = float(serie_b100.iloc[-1]) / 100 - 1
            _vol     = float(_rets_d.std() * np.sqrt(252) * 100)

            # CAGR (taxa composta anual)
            _n_anos = len(serie_b100) / 252
            if _n_anos > 0 and float(serie_b100.iloc[-1]) > 0:
                if float(serie_b100.iloc[0]) > 0:
                    _cagr = (float(serie_b100.iloc[-1]) / float(serie_b100.iloc[0])) ** (1 / _n_anos) - 1
                else:
                    _cagr = 0.0
            else:
                _cagr = 0.0

            if is_renda_fixa or _vol < 0.01:
                _sharpe = None
            else:
                _selic_d = st.session_state.get('macro_context', {}).get('selic', 10.75) / 100 / 252
                _sharpe = (
                    (_rets_d.mean() - _selic_d) / _rets_d.std() * np.sqrt(252)
                ) if _rets_d.std() > 0.0001 else None

            _peak  = serie_b100.cummax()
            _dd    = (serie_b100 - _peak) / _peak * 100
            _max_dd = float(_dd.min())

            # Calmar = CAGR / |max drawdown|
            _calmar = round(_cagr * 100 / abs(_max_dd), 2) if _max_dd < -0.01 and _cagr != 0 else 0.0

            # % dias positivos
            _pct_pos = round(float((_rets_d > 0).mean()) * 100, 1)

            return {
                'retorno':   round(_ret_tot * 100, 2),
                'cagr':      round(_cagr * 100, 2),
                'vol':       round(_vol, 2) if _vol > 0.01 else 0.0,
                'sharpe':    round(float(_sharpe), 2) if _sharpe is not None else None,
                'drawdown':  round(_max_dd, 2),
                'calmar':    _calmar,
                'pct_pos':   _pct_pos,
            }

        for _nm, _sr in resultado['series'].items():
            _is_rf = 'cdi' in _nm.lower()
            resultado['metricas'][_nm] = _calc_metricas(_sr, _nm, is_renda_fixa=_is_rf)

        resultado['trades']   = _trades
        resultado['n_trades'] = len(
            [t for t in _trades if t['tipo'] == 'compra']
        )

    except Exception as e:
        resultado['erro'] = str(e)

    return resultado


# Aplica thresholds pendentes (antes de renderizar widgets)
if '_pending_entrada' in st.session_state:
    st.session_state['sl_bt_entrada'] = st.session_state.pop('_pending_entrada')
    st.session_state['sl_bt_saida']   = st.session_state.pop('_pending_saida')
    st.session_state.pop('bt_resultado', None)
    # não chama st.rerun() — os sliders lerão os valores
    # quando forem renderizados ainda nesta execução

# 4. criação das tabs
# LAZY RENDERING (P4-1): as abas do Portfolio são ACOPLADAS — portfolio_id_ativo,
# pesos_atuais, ativos_alocados e live_data são computados em "posições" e usados
# pelas análises. Em vez do hoist arriscado desse setup, "posições" (o núcleo +
# os dados compartilhados) fica SEMPRE renderizado no topo (st.container), e as 7
# seções analíticas PESADAS (risco/stress/backtest/chat...) são gateadas por um
# seletor abaixo — só a ativa renderiza. Elimina o custo de render de todas as
# análises a cada rerun sem tocar no fluxo de dados.
_SECOES_PF = ["📊 concentração", "📐 risco", "⚡ stress test", "📊 backtesting",
              "📝 diário de decisões", "🧾 imposto de renda", "💬 chat ia"]

# variáveis partilhadas entre tabs — preenchidas em tab_posicoes
live_data: dict      = {}
ativos_alocados: dict = {}

# ==========================================
# posições e p&l — SEMPRE renderizado (computa os dados compartilhados)
# ==========================================
with st.container():

    portfolios_lista = listar_portfolios()
    if not portfolios_lista:
        criar_portfolio("principal", icone="💼", cor="#FF9900")
        portfolios_lista = listar_portfolios()

    col_sel, col_btn = st.columns([4, 1])
    with col_sel:
        portfolio_idx = st.selectbox(
            "portfólio ativo:",
            range(len(portfolios_lista)),
            format_func=lambda i: f"{portfolios_lista[i]['icone']} {portfolios_lista[i]['nome']} ({portfolios_lista[i]['total_ativos']} ativos)",
            key="sel_portfolio_ativo"
        )
    portfolio_ativo = portfolios_lista[portfolio_idx]
    portfolio_id_ativo = portfolio_ativo['id']

    # Detecta troca de portfólio e limpa caches do chat
    _prev_portfolio_id = st.session_state.get('_prev_portfolio_id_chat')
    if _prev_portfolio_id and _prev_portfolio_id != portfolio_id_ativo:
        for _ck in ['chat_portfolio_contexto', 'chat_ctx_version',
                    'pesos_ativos_cache', 'live_data_cache',
                    'health_chat_cache', 'metricas_cache',
                    'chat_portfolio_msgs']:
            st.session_state.pop(_ck, None)
        st.session_state.pop(
            f"pesos_ativos_cache_{_prev_portfolio_id}", None
        )
    st.session_state['_prev_portfolio_id_chat'] = portfolio_id_ativo

    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⚙️ gerenciar", use_container_width=True, key="btn_gerenciar_portfolio"):
            st.session_state['show_portfolio_manager'] = not st.session_state.get('show_portfolio_manager', False)

    if st.session_state.get('show_portfolio_manager', False):
        with st.expander("⚙️ gerenciar portfólios", expanded=True):
            st.markdown("##### criar novo portfólio")
            with st.form("form_novo_portfolio", clear_on_submit=True):
                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    novo_pf_nome = st.text_input("nome:", placeholder="ex: ações EUA")
                with fc2:
                    novo_pf_icone = st.selectbox("ícone:", ["💼", "🇧🇷", "🇺🇸", "🏢", "📈", "₿", "🌍"])
                with fc3:
                    novo_pf_cor = st.selectbox("cor:", ["#FF9900", "#00C853", "#00B0FF", "#E040FB", "#FF1744"])
                if st.form_submit_button("criar portfólio", type="primary"):
                    if novo_pf_nome.strip():
                        criar_portfolio(novo_pf_nome.strip(), icone=novo_pf_icone, cor=novo_pf_cor)
                        st.success(f"✅ portfólio '{novo_pf_nome}' criado!")
                        st.rerun()
                    else:
                        st.warning("digite um nome para o portfólio.")
            st.markdown("---")
            st.markdown("##### portfólios existentes")
            for pf in portfolios_lista:
                pc1, pc2, pc3 = st.columns([4, 1, 1])
                pc1.markdown(f"{pf['icone']} **{pf['nome']}** — {pf['total_ativos']} ativos")
                if pf['padrao']:
                    pc2.markdown('<span class="badge badge-amber">padrão</span>', unsafe_allow_html=True)
                else:
                    if pc2.button("⭐ padrão", key=f"pf_pad_{pf['id']}", use_container_width=True):
                        definir_portfolio_padrao(pf['id'])
                        st.rerun()
                if pc3.button("🗑️ excluir", key=f"pf_del_{pf['id']}", use_container_width=True, disabled=(len(portfolios_lista) <= 1)):
                    deletar_portfolio(pf['id'])
                    st.rerun()

    watchlist = listar_watchlist()
    pesos_atuais = {p['ticker']: p for p in get_pesos(portfolio_id=portfolio_id_ativo)}

    tickers_unicos = list(set([item['ticker'] for item in watchlist] + list(pesos_atuais.keys())))
    posicoes_ativas = []
    
    for t in tickers_unicos:
        p_atual = pesos_atuais.get(t, {})
        qtd = float(p_atual.get('quantidade') or 0)
        if qtd > 0:
            pm = float(p_atual.get('preco_medio') or 0)
            posicoes_ativas.append({
                "ticker": t,
                "quantidade": qtd,
                "preço médio": pm,
                "valor estimado": qtd * pm
            })
            
    # ══ IMPORTAÇÃO VIA PLANILHA ══════════════════════════════════════════════
    with st.expander("📥 importar portfólio via planilha", expanded=False):

        col_imp1, col_imp2 = st.columns([3, 1])
        with col_imp1:
            st.markdown(
                '<div style="font-family:var(--font-ui,sans-serif); font-size:0.78rem; '
                'color:var(--text-muted); line-height:1.6;">'
                '📋 <b>formato aceito:</b> CSV ou Excel com colunas '
                '<code>ticker</code>, <code>quantidade</code>, '
                '<code>preco_medio</code>.<br>'
                '💡 <b>dica:</b> envie prints da sua corretora para o Claude '
                'ou ChatGPT pedindo para gerar um CSV neste formato.</div>',
                unsafe_allow_html=True,
            )
        with col_imp2:
            st.download_button(
                label               = "📄 baixar template",
                data                = TEMPLATE_CSV,
                file_name           = "template_portfolio.csv",
                mime                = "text/csv",
                use_container_width = True,
                key                 = "dl_template_portfolio",
            )

        st.markdown("<br>", unsafe_allow_html=True)

        arquivo_imp = st.file_uploader(
            "selecione o arquivo:",
            type = ['csv', 'xlsx', 'xls'],
            key  = "uploader_portfolio",
            help = "CSV ou Excel com ticker, quantidade e preço médio",
        )

        if arquivo_imp is not None:
            resultado_imp = importar_planilha(
                arquivo_imp.read(), arquivo_imp.name
            )

            if resultado_imp['posicoes']:
                section_title(
                    f"✅ {len(resultado_imp['posicoes'])} posições detectadas "
                    f"— confirme antes de importar"
                )

                # ── Preview ──────────────────────────────────────────────
                df_prev = pd.DataFrame(resultado_imp['posicoes'])[
                    ['ticker', 'nome', 'quantidade', 'preco_medio', 'mercado']
                ].copy()
                df_prev['valor_estimado'] = (
                    df_prev['quantidade'] * df_prev['preco_medio']
                ).apply(lambda x: f"R$ {x:,.2f}")
                df_prev['preco_medio'] = df_prev['preco_medio'].apply(
                    lambda x: f"R$ {x:,.2f}"
                )
                def _generic_html_table(df: pd.DataFrame, first_col_left: bool = True) -> str:
                    _mn = 'var(--font-mono,monospace)'
                    _hdrs = "".join(
                        f'<th style="padding:7px 10px;text-align:{"left" if i==0 and first_col_left else "right"};'
                        f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                        f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                        for i, c in enumerate(df.columns)
                    )
                    _rows = ""
                    for _, row in df.iterrows():
                        _cells = ""
                        for i, (col, val) in enumerate(row.items()):
                            _align = "left" if i == 0 and first_col_left else "right"
                            _cell = f'<span style="font-family:{_mn};font-size:0.8rem;">{val}</span>'
                            _cells += f'<td style="padding:7px 10px;text-align:{_align};">{_cell}</td>'
                        _rows += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                                  f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                                  f'onmouseout="this.style.background=\'transparent\'">{_cells}</tr>')
                    return (f'<div style="overflow-x:auto;">'
                            f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                            f'<thead><tr>{_hdrs}</tr></thead><tbody>{_rows}</tbody></table></div>')
                st.markdown(_generic_html_table(df_prev), unsafe_allow_html=True)

                # Erros não-críticos como warnings
                for erro_imp in resultado_imp['erros']:
                    st.warning(f"⚠️ {erro_imp}")

                st.markdown("---")

                col_conf1, col_conf2, col_conf3 = st.columns(3)
                with col_conf1:
                    modo_import = st.radio(
                        "modo de importação:",
                        options=['adicionar', 'substituir'],
                        format_func=lambda x: {
                            'adicionar':  '➕ adicionar às posições atuais',
                            'substituir': '🔄 substituir portfólio inteiro',
                        }[x],
                        key="modo_importacao",
                    )

                with col_conf3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button(
                        "✅ confirmar importação",
                        type="primary",
                        use_container_width=True,
                        key="btn_confirmar_import",
                    ):
                        from database.db import (
                            adicionar_ativo, get_watchlist_padrao,
                        )

                        wl_id_imp  = get_watchlist_padrao()
                        importados = 0
                        erros_imp  = []

                        for pos in resultado_imp['posicoes']:
                            try:
                                # Garante que o ativo existe na watchlist
                                adicionar_ativo(
                                    ticker       = pos['ticker'],
                                    nome         = pos['nome'],
                                    mercado      = pos['mercado'],
                                    watchlist_id = wl_id_imp,
                                )
                                # Salva posição no portfólio
                                salvar_peso(
                                    pos['ticker'],
                                    0.0,
                                    pos['preco_medio'],
                                    pos['quantidade'],
                                    portfolio_id=portfolio_id_ativo,
                                )
                                importados += 1
                            except Exception as e_pos:
                                erros_imp.append(
                                    f"{pos['ticker']}: {e_pos}"
                                )

                        if importados > 0:
                            st.success(
                                f"✅ {importados} posições importadas com sucesso!"
                            )
                            st.rerun()
                        for e_msg in erros_imp:
                            st.error(f"❌ {e_msg}")

            else:
                st.error("não foi possível detectar posições no arquivo.")
                for erro_imp in resultado_imp['erros']:
                    st.error(f"❌ {erro_imp}")
                st.info(
                    "💡 verifique se o arquivo tem as colunas: "
                    "ticker, quantidade, preco_medio"
                )

    # ══ TABELA DE POSIÇÕES ATIVAS ════════════════════════════════════════════
    if posicoes_ativas:
        section_title("📋 posições ativas")
        df_ativas = pd.DataFrame(posicoes_ativas)
        
        df_ativas_editado = st.data_editor(
            df_ativas,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "ticker": st.column_config.TextColumn("ativo", disabled=True),
                "quantidade": st.column_config.NumberColumn("quantidade", min_value=0.0, step=0.001, format="%.4f"),
                "preço médio": st.column_config.NumberColumn("preço médio (R$/US$)", min_value=0.0, step=0.01, format="%.4f"),
                "valor estimado": st.column_config.NumberColumn("valor estimado", disabled=True, format="%.2f")
            }
        )
        
        patrimonio_estimado = (df_ativas_editado['quantidade'] * df_ativas_editado['preço médio']).sum()
        num_posicoes = len(df_ativas_editado[df_ativas_editado['quantidade'] > 0])
        
        c_txt, c_nav, c_btn = st.columns([3, 2, 1])
        with c_txt:
            st.markdown(f"<div style='font-family:var(--font-data,monospace); font-size: 0.85rem; color:var(--text-muted); padding-top: 10px;'>patrimônio estimado: {fmt_preco(patrimonio_estimado, '$')} | {num_posicoes} posições ativas</div>", unsafe_allow_html=True)
        with c_nav:
            _tickers_port = df_ativas['ticker'].tolist()
            _sel_nav = st.selectbox(
                "→ research:",
                [""] + [t.replace('.SA','') for t in _tickers_port],
                label_visibility="collapsed",
                key="port_nav_ticker",
                placeholder="abrir no research...",
            )
            if _sel_nav:
                _match = next((t for t in _tickers_port if t.replace('.SA','') == _sel_nav), _sel_nav)
                st.session_state['research_ticker_externo'] = _match
                st.switch_page("pages/1_Research.py")
        with c_btn:
            btn_salvar = st.button("💾 salvar correções da tabela", type="primary", use_container_width=True)
            
        if btn_salvar:
            df_ativas_editado['valor total'] = df_ativas_editado['quantidade'] * df_ativas_editado['preço médio']
            patrimonio_total = df_ativas_editado['valor total'].sum()
            
            for _, row in df_ativas_editado.iterrows():
                t = row['ticker']
                qtd = row['quantidade']
                pm = row['preço médio']
                v_total = row['valor total']
                peso_real = (v_total / patrimonio_total) * 100 if (patrimonio_total > 0 and qtd > 0) else 0.0
                # Sanitiza NaN/Inf para evitar erro no json.dumps do Supabase
                import math as _mt
                def _sn(v):
                    if v is None: return None
                    try: return None if _mt.isnan(v) or _mt.isinf(v) else v
                    except TypeError: return v
                salvar_peso(t, _sn(peso_real), _sn(pm), _sn(qtd), portfolio_id=portfolio_id_ativo)
                
            st.success("✅ posições atualizadas.")
            st.rerun()
    else:
        empty_state("📋", "nenhuma posição ativa", "adicione sua primeira posição abaixo.")

    st.markdown("<hr style='margin: 1.5rem 0; opacity: 0.2;'>", unsafe_allow_html=True)
    section_title("➕ lançar operação (compra / venda)")
    
    with st.form("form_add_posicao", clear_on_submit=True):
        col_op, col_f1, col_f2, col_f3 = st.columns([1, 2, 1, 1], gap="small")
        
        with col_op:
            tipo_op = st.radio("tipo de operação:", ["🟢 Comprar", "🔴 Vender"])
            
        with col_f1:
            opcoes_wl = [w['ticker'] for w in watchlist]
            ticker_sel = st.selectbox("ativo da watchlist", opcoes_wl, format_func=lambda x: x.lower()) if opcoes_wl else None
            
        with col_f2:
            qtd_form = st.number_input("quantidade operada", min_value=0.0, step=0.001, format="%.4f")
            
        with col_f3:
            pm_form = st.number_input("preço (R$/US$)", min_value=0.0, step=0.01, format="%.4f")
            
        ticker_manual_form = st.text_input("ou digite um ticker manualmente (sobrescreve seleção acima):", placeholder="ex: PETR4.SA ou AAPL").strip().upper()
        
        st.markdown("<br>", unsafe_allow_html=True)
        btn_add = st.form_submit_button("registrar operação no portfólio", type="primary", use_container_width=True)
        
        if btn_add:
            ticker_final = ticker_manual_form if ticker_manual_form else ticker_sel
            
            if ticker_final and qtd_form > 0 and pm_form > 0:
                # Obter dados atuais da posição antes da operação
                p_atual = pesos_atuais.get(ticker_final, {})
                qtd_atual = float(p_atual.get('quantidade') or 0)
                pm_atual = float(p_atual.get('preco_medio') or 0)
                
                if "Comprar" in tipo_op:
                    nova_qtd = qtd_atual + qtd_form
                    # Cálculo inteligente de Preço Médio
                    novo_pm = ((qtd_atual * pm_atual) + (qtd_form * pm_form)) / nova_qtd if nova_qtd > 0 else pm_form
                    
                    salvar_peso(ticker_final, 0.0, novo_pm, nova_qtd, portfolio_id=portfolio_id_ativo)
                    st.success(f"✅ compra de {qtd_form} cotas de {ticker_final} registrada! novo PM: {novo_pm:.2f}")
                    time.sleep(1.5)
                    st.rerun()
                    
                elif "Vender" in tipo_op:
                    if qtd_form > qtd_atual:
                        st.warning(f"⚠️ você está tentando vender {qtd_form} cotas, mas só possui {qtd_atual} de {ticker_final}.")
                    else:
                        nova_qtd = qtd_atual - qtd_form
                        # Em vendas, o Preço Médio das cotas restantes NÃO muda. Se zerar a posição, zera o PM.
                        novo_pm = pm_atual if nova_qtd > 0 else 0.0
                        
                        salvar_peso(ticker_final, 0.0, novo_pm, nova_qtd, portfolio_id=portfolio_id_ativo)
                        st.success(f"✅ venda de {qtd_form} cotas de {ticker_final} registrada com sucesso!")
                        time.sleep(1.5)
                        st.rerun()
            else:
                st.warning("preencha ticker, uma quantidade maior que zero e um preço válido.")

    ativos_alocados = {t: d for t, d in pesos_atuais.items() if d['peso'] > 0}
    
    if ativos_alocados:
        tickers_com_peso = list(ativos_alocados.keys())

        with st.spinner("a sincronizar cotações em tempo real para cálculo de p&l..."):
            live_data = {}
            for t in tickers_com_peso:
                t_base = mapear_ticker_base(t)
                try:
                    hist = yf.Ticker(t_base).history(period="5d")['Close'].dropna()
                    if not hist.empty:
                        live_data[t] = float(hist.iloc[-1])
                    else:
                        live_data[t] = 0.0
                except Exception as _e:
                    logger.debug(f"[portfolio] live_data fallback para {t_base}: {_e}")
                    live_data[t] = 0.0

        st.markdown("---")
        section_title("📊 performance e distribuição")

        linhas_portfolio = []
        custo_total_carteira = 0.0
        valor_atual_carteira = 0.0
        
        health_raw = get_health_scores()
        health_data = {h['ticker']: h.get('score', 50) for h in health_raw}

        for t, dados in ativos_alocados.items():
            qtd = float(dados.get('quantidade') or 0)
            pm = float(dados.get('preco_medio') or 0)
            preco_atual = live_data.get(t, 0.0)
            custo_posicao = qtd * pm
            valor_posicao = qtd * preco_atual
            pnl_valor = valor_posicao - custo_posicao
            pnl_pct = (pnl_valor / custo_posicao * 100) if custo_posicao > 0 else 0.0
            
            custo_total_carteira += custo_posicao
            valor_atual_carteira += valor_posicao
            
            linhas_portfolio.append({
                "ativo": t, "qtd": qtd, "preço médio": pm, "preço atual": preco_atual,
                "custo total": custo_posicao, "valor atual": valor_posicao,
                "p&l ($)": pnl_valor, "p&l (%)": pnl_pct, "health score": health_data.get(mapear_ticker_base(t), "n/d")
            })

        df_portfolio = pd.DataFrame(linhas_portfolio)
        df_portfolio['peso atual (%)'] = (df_portfolio['valor atual'] / valor_atual_carteira) * 100 if valor_atual_carteira > 0 else 0.0

        pnl_global_valor = valor_atual_carteira - custo_total_carteira
        pnl_global_pct = (pnl_global_valor / custo_total_carteira * 100) if custo_total_carteira > 0 else 0.0

        # ── PERFORMANCE VS BENCHMARKS ─────────────────────────────────
        st.markdown("---")
        section_title("📈 performance da carteira vs benchmarks")

        label_com_tooltip(
            "retorno ponderado pelo valor de mercado de cada posição "
            "vs ibovespa, s&p500 (via ivvb11), ifix e cdi.",
            texto_custom=(
                "metodologia: retorno diário ponderado pelo valor "
                "de mercado de cada posição (twr simplificado). "
                "cdi via bcb série 12 (taxa overnight acumulada). "
                "base 100 = início do período selecionado."
            ),
            cor="#555",
            tamanho="0.72rem",
        )

        _periodo_perf = st.radio(
            "período:",
            ["3mo", "6mo", "1y", "2y"],
            format_func=lambda x: {
                "3mo": "3 meses",
                "6mo": "6 meses",
                "1y":  "1 ano",
                "2y":  "2 anos",
            }[x],
            horizontal=True,
            key="radio_periodo_perf",
        )

        # Monta tuple de posições para cache
        _pos_dict_perf = [
            {
                'ticker': t,
                'quantidade': float(d.get('quantidade', 0) or 0),
                'preco_medio': float(d.get('preco_medio', 0) or 0),
            }
            for t, d in ativos_alocados.items()
            if float(d.get('quantidade', 0) or 0) > 0
        ]

        if not _pos_dict_perf:
            info_box(
                tipo   = "info",
                titulo = "sem posições com quantidade/preço",
                texto  = "adicione posições com quantidade e preço médio para calcular a performance.",
                icone  = "📭",
            )
        else:
            with st.spinner("calculando performance vs benchmarks..."):
                _perf = calcular_performance_vs_benchmarks(
                    tuple(
                        (p['ticker'], p['quantidade'], p['preco_medio'])
                        for p in _pos_dict_perf
                    ),
                    periodo=_periodo_perf,
                )

            if not _perf or not _perf.get('series'):
                info_box(
                    tipo   = "amber",
                    titulo = "performance indisponível",
                    texto  = "não foi possível calcular. verifique se os tickers estão corretos.",
                    icone  = "⚠",
                )
            else:
                _met = _perf.get('metricas', {})
                if _met:
                    _met_rows = []
                    for _nm, _mv in _met.items():
                        _cor_ret = "🟢" if _mv['retorno'] > 0 else "🔴"
                        _met_rows.append({
                            'ativo / índice': _nm,
                            'retorno':   f"{_cor_ret} {_mv['retorno']:+.2f}%",
                            'vol. anual':f"{_mv['vol']:.2f}%",
                            'sharpe':    f"{_mv['sharpe']:.2f}",
                            'max drawdown': f"{_mv['drawdown']:.2f}%",
                        })
                    _df_met = pd.DataFrame(_met_rows)
                    _mn_m = 'var(--font-mono,monospace)'
                    _hdrs_m = "".join(
                        f'<th style="padding:7px 10px;text-align:{"left" if c=="ativo / índice" else "right"};'
                        f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                        f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                        for c in _df_met.columns
                    )
                    _rows_m = ""
                    for _, row in _df_met.iterrows():
                        _cells_m = ""
                        for col in _df_met.columns:
                            _v = str(row[col])
                            _align = "left" if col == "ativo / índice" else "right"
                            _has_pct = '%' in _v
                            _cv = "#2ecc71" if '+' in _v and _has_pct else ("#e74c3c" if '-' in _v and _has_pct else "var(--text-primary)")
                            _fw = "600" if col == "retorno" else "400"
                            _cells_m += (f'<td style="padding:7px 10px;text-align:{_align};">'
                                         f'<span style="font-family:{_mn_m};font-size:0.8rem;font-weight:{_fw};color:{_cv};">{_v}</span></td>')
                        _rows_m += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                                    f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                                    f'onmouseout="this.style.background=\'transparent\'">{_cells_m}</tr>')
                    st.markdown(
                        f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
                        f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                        f'<thead><tr>{_hdrs_m}</tr></thead><tbody>{_rows_m}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("<br>", unsafe_allow_html=True)

                _series = _perf.get('series', {})
                if _series:
                    _fig_perf = go.Figure()
                    _cc_perf = _chart_cores()
                    _cores_perf = {
                        'minha carteira': _cc_perf["accent"],
                        'ibovespa':       _cc_perf["bull"],
                        's&p500 (br)':    _cc_perf["info"],
                        'ifix (fiis)':    '#8B5CF6',
                        'cdi':            _cc_perf["muted"],
                        'cdi (aprox)':    _cc_perf["muted"],
                    }

                    if 'minha carteira' in _series:
                        _s = _series['minha carteira']
                        _ret_f = float(_s.iloc[-1]) - 100 if not _s.empty else 0
                        _fig_perf.add_trace(go.Scatter(
                            x=_s.index, y=_s.values,
                            name=f"minha carteira ({_ret_f:+.1f}%)",
                            line=dict(color=_cc_perf["accent"], width=3),
                            hovertemplate=(
                                '%{x}<br>carteira: %{y:.1f}<extra></extra>'
                            ),
                        ))

                    for _nm, _s in _series.items():
                        if _nm == 'minha carteira' or _s.empty:
                            continue
                        _ret_f = float(_s.iloc[-1]) - 100 if not _s.empty else 0
                        _cor   = _cores_perf.get(_nm, '#555')
                        _fig_perf.add_trace(go.Scatter(
                            x=_s.index, y=_s.values,
                            name=f"{_nm} ({_ret_f:+.1f}%)",
                            line=dict(color=_cor, width=1.5, dash='dot'),
                            hovertemplate=(
                                f'%{{x}}<br>{_nm}: %{{y:.1f}}<extra></extra>'
                            ),
                        ))

                    _fig_perf.add_hline(
                        y=100, line_color=_chart_cores()["muted"],
                        line_dash='dash', line_width=1,
                    )

                    _lay_perf = base_layout(
                        height=420,
                        title=f"performance comparada — base 100 ({_periodo_perf})",
                    )
                    _lay_perf.update(
                        yaxis=dict(title='base 100', showgrid=True, gridcolor=_chart_cores()["border"]),
                        xaxis=dict(showgrid=False),
                    )
                    _fig_perf.update_layout(**_lay_perf)
                    st.plotly_chart(
                        _fig_perf, use_container_width=True,
                        config={'responsive': True},
                    )

                    st.caption(
                        "base 100 = início do período. "
                        "carteira: retorno ponderado pelo valor de mercado. "
                        "cdi: taxa overnight acumulada (bcb série 12). "
                        "s&p500: via ivvb11 (em r$, sem hedge cambial)."
                    )

                # Alpha vs CDI e Ibov
                _ret_cart = _met.get('minha carteira', {}).get('retorno', 0)
                _ret_cdi  = (
                    _met.get('cdi', _met.get('cdi (aprox)', {}))
                    .get('retorno', 0)
                )
                _ret_ibov = _met.get('ibovespa', {}).get('retorno', 0)
                _alpha_cdi  = _ret_cart - _ret_cdi
                _alpha_ibov = _ret_cart - _ret_ibov

                portfolio_kpis([
                    {
                        "nome":     "retorno carteira",
                        "valor":    f"{_ret_cart:+.2f}%",
                        "sublabel": f"no período de {_periodo_perf}",
                        "tone":     "bull" if _ret_cart > 0 else "bear",
                        "icone":    "📈" if _ret_cart > 0 else "📉",
                    },
                    {
                        "nome":     "alpha vs cdi",
                        "valor":    f"{_alpha_cdi:+.2f}pp",
                        "sublabel": "acima ou abaixo do cdi",
                        "tone":     "bull" if _alpha_cdi > 0 else "bear",
                        "icone":    "🎯",
                    },
                    {
                        "nome":     "alpha vs ibovespa",
                        "valor":    f"{_alpha_ibov:+.2f}pp",
                        "sublabel": "acima ou abaixo do ibov",
                        "tone":     "bull" if _alpha_ibov > 0 else "bear",
                        "icone":    "🇧🇷",
                    },
                ])

                st.markdown("<br>", unsafe_allow_html=True)

                # ── Exibe análise cacheada se houver ──────────────────────────
                try:
                    from database.db import get_ai_analysis as _get_ai_pf
                    _uid_perf_view = st.session_state.get('user_id')
                    _db_cache_pf = _get_ai_pf(
                        tipo="portfolio",
                        ticker=None,
                        user_id=_uid_perf_view,
                        modo=f"performance_{_periodo_perf}",
                    )
                    if _db_cache_pf:
                        st.markdown(
                            f'<div style="background:var(--bg-surface); border:1px solid var(--border-subtle); '
                            f'border-left:3px solid var(--accent); border-radius:6px; padding:12px 16px; margin-bottom:12px;">'
                            f'<div style="font-family:var(--font-ui,sans-serif); font-size:0.65rem; '
                            f'color:var(--text-muted); margin-bottom:8px;">'
                            f'⚡ análise via cache supabase '
                            f'— gerada em {str(_db_cache_pf.get("created_at",""))[:16].replace("T"," ")}'
                            f'</div>'
                            f'<div style="font-family:var(--font-data,monospace); font-size:0.82rem; '
                            f'color:var(--text-primary); line-height:1.7; white-space:pre-wrap;">'
                            f'{_db_cache_pf["conteudo"]}'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )
                        st.caption("clique no botão abaixo para regenerar.")
                except Exception:
                    pass

                if st.button(
                    "🧠 ia: analisar performance e sugerir ajustes",
                    key="btn_ia_perf",
                    type="secondary",
                    use_container_width=True,
                ):
                    _macro_perf = st.session_state.get('macro_context', {})

                    # ── Concentração setorial e exposição cambial ──────────
                    _setor_conc = {}
                    _fx_exp = {"br": 0.0, "us": 0.0}
                    _top_positions = []
                    try:
                        from database.db import get_todos_fundamentos_cache as _gtc
                        _cache_pf = _gtc() or {}
                        _tot_v = sum((p.get('valor') or 0) for p in (st.session_state.get('pesos_ativos_cache') or []))
                        for _p in (st.session_state.get('pesos_ativos_cache') or []):
                            _tk = _p.get('ticker', '')
                            _v = float(_p.get('valor') or 0)
                            _fd_p = _cache_pf.get(_tk) or _cache_pf.get(mapear_ticker_base(_tk)) or {}
                            _set = _fd_p.get('setor') or 'outros'
                            _setor_conc[_set] = _setor_conc.get(_set, 0) + _v
                            if _tk.endswith('.SA'):
                                _fx_exp['br'] += _v
                            else:
                                _fx_exp['us'] += _v
                            _top_positions.append(_p)
                        if _tot_v > 0:
                            _setor_conc = {k: v / _tot_v * 100 for k, v in _setor_conc.items()}
                            _fx_exp = {k: v / _tot_v * 100 for k, v in _fx_exp.items()}
                        # Ordena top por peso
                        _top_positions = sorted(
                            _top_positions, key=lambda x: -(x.get('peso_pct') or 0)
                        )[:10]
                    except Exception:
                        pass

                    from utils.ai_prompts import build_portfolio_performance_prompt
                    _prompt_perf = build_portfolio_performance_prompt(
                        metricas         = _met,
                        posicoes_top     = _top_positions,
                        setor_concentracao = _setor_conc,
                        fx_exposicao     = _fx_exp,
                        periodo          = _periodo_perf,
                        macro_context    = _macro_perf,
                        alpha_cdi        = _alpha_cdi,
                        alpha_ibov       = _alpha_ibov,
                    )
                    from utils.ai_client import chamar_ia, SYSTEM_PORTFOLIO
                    _us_perf = st.session_state.get('user_settings', {})
                    _resposta_perf = chamar_ia(
                        prompt_usuario=_prompt_perf,
                        system=SYSTEM_PORTFOLIO,
                        max_tokens=1000,
                        temperatura=0.3,
                        stream=True,
                        user_settings=_us_perf,
                    )
                    # ── Persiste no Supabase (TTL 1 dia, por user_id+periodo) ──
                    if _resposta_perf:
                        try:
                            from database.db import save_ai_analysis
                            _uid_perf = st.session_state.get('user_id')
                            save_ai_analysis(
                                tipo="portfolio",
                                ticker=None,
                                user_id=_uid_perf,
                                modo=f"performance_{_periodo_perf}",
                                conteudo=_resposta_perf,
                                modelo="auto",
                                ttl_horas=24,
                            )
                        except Exception:
                            pass

        # ── persiste dados para o chat IA (tab_chat usa estes) ──
        st.session_state['pesos_ativos_cache'] = [
            {
                'ticker':      row['ativo'],
                'quantidade':  row['qtd'],
                'preco_medio': row['preço médio'],
                'preco_atual': row['preço atual'],
                'valor':       row['valor atual'],
                'peso_pct':    row['peso atual (%)'],
                'pnl_pct':     row['p&l (%)'],
                'health_score': row['health score'],
            }
            for _, row in df_portfolio.iterrows()
        ]
        st.session_state['metricas_cache'] = {
            'valor_total':   valor_atual_carteira,
            'custo_total':   custo_total_carteira,
            'pnl_total_pct': pnl_global_pct,
            'num_posicoes':  len(df_portfolio),
        }

        # ── Banner do portfólio (design system v5) ───────────────────────
        portfolio_hero(
            titulo      = "GESTÃO DE PORTFÓLIO",
            valor_atual = valor_atual_carteira,
            custo_total = custo_total_carteira,
            pnl_valor   = pnl_global_valor,
            pnl_pct     = pnl_global_pct,
            moeda       = "R$",
            data_source = "",
        )

        # ── KPIs auxiliares ──────────────────────────────────────────────
        _pf_kpis = [
            {
                "nome":     "custo alocado",
                "valor":    custo_total_carteira,
                "sublabel": "total investido (preço médio × qtd)",
                "tone":     "info",
                "icone":    "💰",
            },
            {
                "nome":     "p&l global",
                "valor":    pnl_global_valor,
                "sublabel": f"{pnl_global_pct:+.2f}% sobre custo",
                "tone":     "bull" if pnl_global_valor >= 0 else "bear",
                "icone":    "📈" if pnl_global_valor >= 0 else "📉",
            },
            {
                "nome":     "posições",
                "valor":    f"{len(df_portfolio)}",
                "sublabel": "ativos no portfólio",
                "tone":     "accent",
                "icone":    "📊",
            },
            {
                "nome":     "valor médio/posição",
                "valor":    (valor_atual_carteira / max(len(df_portfolio), 1)),
                "sublabel": "ticket médio atual",
                "tone":     "info",
                "icone":    "🎯",
            },
        ]
        portfolio_kpis(_pf_kpis)

        # Tabela de posições HTML — P&L colorido, health bar, link para Research
        def _pf_table_html(df: pd.DataFrame) -> str:
            _hdrs = ["Ativo", "Qtd", "PM", "Preço", "Custo", "Valor", "P&L $", "P&L %", "Health", "Peso %"]
            _thead = "".join(
                f'<th style="padding:8px 10px;text-align:{"right" if i>1 else "left"};'
                f'font-size:0.68rem;color:var(--text-muted);text-transform:uppercase;'
                f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{h}</th>'
                for i, h in enumerate(_hdrs)
            )
            _rows = ""
            _max_peso = float(df['peso atual (%)'].max()) if not df.empty else 1.0
            for _, row in df.iterrows():
                _tk    = str(row['ativo'])
                _url   = f"/Research?research_ticker={_tk}"
                _pnl_v = float(row['p&l ($)'])
                _pnl_p = float(row['p&l (%)'])
                _hs    = row.get('health score')
                _peso  = float(row['peso atual (%)'])
                _cv    = "#2ecc71" if _pnl_v >= 0 else "#e74c3c"

                # health bar mini
                try:
                    _hsi = int(_hs)
                    _hc  = "#2ecc71" if _hsi >= 65 else ("#f39c12" if _hsi >= 40 else "#e74c3c")
                    _hs_html = (
                        f'<div style="display:flex;align-items:center;gap:5px;">'
                        f'<div style="flex:1;background:var(--border-subtle);border-radius:2px;height:4px;overflow:hidden;">'
                        f'<div style="width:{_hsi}%;height:100%;background:{_hc};border-radius:2px;"></div></div>'
                        f'<span style="font-size:0.75rem;color:{_hc};font-family:var(--font-mono,monospace);min-width:20px;">{_hsi}</span>'
                        f'</div>'
                    )
                except (TypeError, ValueError):
                    _hs_html = '<span style="color:var(--text-muted);">—</span>'

                # peso bar mini
                _pw_pct = min((_peso / _max_peso) * 100, 100) if _max_peso > 0 else 0
                _peso_html = (
                    f'<div style="display:flex;align-items:center;gap:5px;">'
                    f'<div style="flex:1;background:var(--border-subtle);border-radius:2px;height:4px;overflow:hidden;">'
                    f'<div style="width:{_pw_pct:.0f}%;height:100%;background:var(--accent);border-radius:2px;"></div></div>'
                    f'<span style="font-size:0.75rem;color:var(--text-muted);font-family:var(--font-mono,monospace);min-width:30px;">{_peso:.1f}%</span>'
                    f'</div>'
                )

                _mn = 'var(--font-mono,monospace)'
                _cells = (
                    f'<td style="padding:8px 10px;white-space:nowrap;">'
                    f'<a href="{_url}" target="_blank" style="color:var(--accent);font-family:{_mn};'
                    f'font-weight:600;font-size:0.82rem;text-decoration:none;" '
                    f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">{_tk.replace(".SA","")}</a></td>'
                    f'<td style="padding:8px 10px;font-family:{_mn};font-size:0.78rem;color:var(--text-muted);text-align:right;">{row["qtd"]:.4f}</td>'
                    f'<td style="padding:8px 10px;font-family:{_mn};font-size:0.78rem;text-align:right;">{row["preço médio"]:.4f}</td>'
                    f'<td style="padding:8px 10px;font-family:{_mn};font-size:0.82rem;font-weight:600;text-align:right;">{row["preço atual"]:.2f}</td>'
                    f'<td style="padding:8px 10px;font-family:{_mn};font-size:0.78rem;color:var(--text-muted);text-align:right;">{row["custo total"]:,.0f}</td>'
                    f'<td style="padding:8px 10px;font-family:{_mn};font-size:0.82rem;font-weight:600;text-align:right;">{row["valor atual"]:,.0f}</td>'
                    f'<td style="padding:8px 10px;font-family:{_mn};font-size:0.82rem;font-weight:600;color:{_cv};text-align:right;">{_pnl_v:+,.0f}</td>'
                    f'<td style="padding:8px 10px;font-family:{_mn};font-size:0.82rem;font-weight:600;color:{_cv};text-align:right;">{_pnl_p:+.2f}%</td>'
                    f'<td style="padding:8px 10px;min-width:100px;">{_hs_html}</td>'
                    f'<td style="padding:8px 10px;min-width:100px;">{_peso_html}</td>'
                )
                _rows += (
                    f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                    f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                    f'onmouseout="this.style.background=\'transparent\'">{_cells}</tr>'
                )
            return (
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                f'<thead><tr>{_thead}</tr></thead><tbody>{_rows}</tbody></table></div>'
            )

        st.markdown(_pf_table_html(df_portfolio), unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        csv = df_portfolio.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 exportar carteira (csv)",
            data=csv,
            file_name="portfolio_finapp.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.markdown("<br>", unsafe_allow_html=True)
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            section_title("⚖️ alocação por ativo")
            fig_pie = go.Figure(go.Pie(labels=df_portfolio['ativo'], values=df_portfolio['valor atual'], hole=0.4, textinfo='label+percent', marker=dict(line=dict(color='#010101', width=2))))
            layout_pie = base_layout(height=350)
            if 'xaxis' in layout_pie:
                layout_pie['xaxis']['visible'] = False
            if 'yaxis' in layout_pie:
                layout_pie['yaxis']['visible'] = False
            fig_pie.update_layout(**layout_pie)
            st.plotly_chart(fig_pie, use_container_width=True, config={'responsive': True})
            st.caption("distribuição do capital entre os ativos da carteira. concentração excessiva em poucos nomes eleva o risco idiossincrático — fatias muito grandes merecem atenção.")

        with col_g2:
            section_title("📈 p&l por ativo")
            _cc_pnl = _chart_cores()
            df_pnl  = df_portfolio.sort_values(by='p&l ($)', ascending=True)
            fig_bar = go.Figure(go.Bar(
                x=df_pnl['p&l ($)'], y=df_pnl['ativo'], orientation='h',
                marker_color=[_cc_pnl["bear"] if val < 0 else _cc_pnl["bull"]
                              for val in df_pnl['p&l ($)']],
                hovertemplate="%{y}<br>P&L: <b>%{x:+,.2f}</b><extra></extra>",
            ))
            layout_bar = base_layout(height=350)
            if 'yaxis' in layout_bar:
                layout_bar['yaxis']['showgrid'] = False
            fig_bar.update_layout(**layout_bar)
            st.plotly_chart(fig_bar, use_container_width=True, config={'responsive': True})
            st.caption("lucro/prejuízo não realizado por posição. identifica os ativos que puxam o resultado da carteira para cima ou para baixo.")

        # ── VISÃO CONSOLIDADA POR MOEDA ──────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        cambio_atual = get_cambio_usd_brl()

        posicoes_brl = []
        posicoes_usd = []

        for t, dados in ativos_alocados.items():
            qtd = float(dados.get('quantidade') or 0)
            pm  = float(dados.get('preco_medio') or 0)
            if qtd <= 0:
                continue

            t_base_moeda = mapear_ticker_base(t)
            eh_br        = t_base_moeda.endswith('.SA')
            preco_atual  = live_data.get(t, 0.0)

            if preco_atual <= 0:
                continue

            valor_atual  = preco_atual * qtd
            valor_custo  = pm * qtd
            pl_moeda     = valor_atual - valor_custo
            pl_pct       = ((valor_atual / valor_custo) - 1) * 100 if valor_custo > 0 else 0.0

            entry = {
                'ticker':          t,
                'qtd':             qtd,
                'pm':              pm,
                'preco_atual':     preco_atual,
                'valor_atual':     valor_atual,
                'valor_custo':     valor_custo,
                'pl_moeda':        pl_moeda,
                'pl_pct':          pl_pct,
                'moeda':           'BRL' if eh_br else 'USD',
                'valor_atual_brl': valor_atual if eh_br else valor_atual * cambio_atual,
                'valor_custo_brl': valor_custo if eh_br else valor_custo * cambio_atual,
                'pl_brl':          pl_moeda if eh_br else pl_moeda * cambio_atual,
            }

            if eh_br:
                posicoes_brl.append(entry)
            else:
                posicoes_usd.append(entry)

        if posicoes_brl or posicoes_usd:
            section_title("💰 visão consolidada por moeda")

            total_brl_carteira = (
                sum(p['valor_atual_brl'] for p in posicoes_brl) +
                sum(p['valor_atual_brl'] for p in posicoes_usd)
            )
            total_custo_brl = (
                sum(p['valor_custo_brl'] for p in posicoes_brl) +
                sum(p['valor_custo_brl'] for p in posicoes_usd)
            )
            pl_total_brl = total_brl_carteira - total_custo_brl
            pl_total_pct = ((total_brl_carteira / total_custo_brl) - 1) * 100 if total_custo_brl > 0 else 0.0

            total_usd  = sum(p['valor_atual'] for p in posicoes_usd)
            custo_usd  = sum(p['valor_custo'] for p in posicoes_usd)
            pl_usd     = total_usd - custo_usd
            pl_usd_pct = ((total_usd / custo_usd) - 1) * 100 if custo_usd > 0 else 0.0

            # contribuição cambial = diferença entre converter o P&L USD pelo câmbio atual
            # e o P&L BRL "real" das posições USD (custo em câmbio da época vs. câmbio hoje)
            pl_brl_posicoes_usd   = sum(p['pl_brl'] for p in posicoes_usd)
            pl_usd_em_brl_simples = pl_usd * cambio_atual
            contrib_cambio        = pl_brl_posicoes_usd - pl_usd_em_brl_simples

            portfolio_kpis([
                {
                    "nome":     "patrimônio total (brl)",
                    "valor":    f"R$ {total_brl_carteira:,.2f}",
                    "sublabel": f"custo R$ {total_custo_brl:,.2f}",
                    "tone":     "info",
                    "icone":    "💎",
                },
                {
                    "nome":     "p&l total brl",
                    "valor":    f"R$ {pl_total_brl:+,.2f}",
                    "sublabel": f"{pl_total_pct:+.2f}% sobre custo",
                    "tone":     "bull" if pl_total_brl >= 0 else "bear",
                    "icone":    "📈" if pl_total_brl >= 0 else "📉",
                },
                {
                    "nome":     "p&l eua (usd)",
                    "valor":    f"$ {pl_usd:+,.2f}",
                    "sublabel": f"{pl_usd_pct:+.2f}% · câmbio R$ {cambio_atual:.2f}",
                    "tone":     "bull" if pl_usd >= 0 else "bear",
                    "icone":    "🇺🇸",
                },
                {
                    "nome":     "contribuição cambial",
                    "valor":    f"R$ {contrib_cambio:+,.2f}",
                    "sublabel": "efeito usd/brl no resultado",
                    "tone":     "bull" if contrib_cambio >= 0 else "bear",
                    "icone":    "💱",
                },
            ])

            st.markdown("---")
            col_br, col_us = st.columns(2)

            with col_br:
                section_title("🇧🇷 ativos brasileiros (brl)")
                total_br_val  = sum(p['valor_atual'] for p in posicoes_brl)
                total_br_cust = sum(p['valor_custo'] for p in posicoes_brl)
                pl_br         = total_br_val - total_br_cust
                pl_br_pct     = ((total_br_val / total_br_cust) - 1) * 100 if total_br_cust > 0 else 0.0

                st.markdown(
                    f'<div style="font-family:var(--font-data,monospace); font-size:0.85rem; margin-bottom:8px;">'
                    f'<span style="color:var(--text-muted);">patrimônio: </span>'
                    f'<span style="color:var(--text-primary); font-weight:bold;">R$ {total_br_val:,.2f}</span> | '
                    f'<span style="color:var(--text-muted);">p&l: </span>'
                    f'<span style="color:{"var(--bull)" if pl_br >= 0 else "var(--bear)"}; font-weight:bold;">'
                    f'R$ {pl_br:+,.2f} ({pl_br_pct:+.1f}%)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for pos in sorted(posicoes_brl, key=lambda x: abs(x['pl_pct']), reverse=True):
                    cor_p = "var(--bull)" if pos['pl_pct'] >= 0 else "var(--bear)"
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; '
                        f'padding:4px 0; border-bottom:1px solid var(--border-subtle); '
                        f'font-family:var(--font-data,monospace); font-size:0.75rem;">'
                        f'<a href="{ticker_nav_url(pos["ticker"])}" class="ticker-nav" style="font-size:0.75rem;">{pos["ticker"].replace(".SA","")}</a>'
                        f'<span style="color:var(--text-muted);">R$ {pos["preco_atual"]:,.2f}</span>'
                        f'<span style="color:{cor_p};">{pos["pl_pct"]:+.1f}%</span>'
                        f'<span style="color:{cor_p};">R$ {pos["pl_moeda"]:+,.0f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            with col_us:
                section_title("🇺🇸 ativos eua (usd + brl)")

                st.markdown(
                    f'<div style="font-family:var(--font-data,monospace); font-size:0.85rem; margin-bottom:8px;">'
                    f'<span style="color:var(--text-muted);">em usd: </span>'
                    f'<span style="color:var(--text-primary); font-weight:bold;">$ {total_usd:,.2f}</span> | '
                    f'<span style="color:var(--text-muted);">em brl: </span>'
                    f'<span style="color:var(--text-primary); font-weight:bold;">R$ {total_usd * cambio_atual:,.2f}</span>'
                    f'<br><span style="color:var(--text-muted); font-size:0.65rem;">câmbio: R$ {cambio_atual:.4f}/USD</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for pos in sorted(posicoes_usd, key=lambda x: abs(x['pl_pct']), reverse=True):
                    cor_p = "var(--bull)" if pos['pl_pct'] >= 0 else "var(--bear)"
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; '
                        f'padding:4px 0; border-bottom:1px solid var(--border-subtle); '
                        f'font-family:var(--font-data,monospace); font-size:0.75rem;">'
                        f'<a href="{ticker_nav_url(pos["ticker"])}" class="ticker-nav" style="font-size:0.75rem;">{pos["ticker"].replace(".SA","")}</a>'
                        f'<span style="color:var(--text-muted);">$ {pos["preco_atual"]:,.2f}</span>'
                        f'<span style="color:{cor_p};">{pos["pl_pct"]:+.1f}%</span>'
                        f'<span style="color:{cor_p}; font-size:0.68rem;">R$ {pos["pl_brl"]:+,.0f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # ── rebalanceamento inteligente ───────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚖️ rebalanceamento inteligente", expanded=False):

            st.markdown(
                '<div style="font-family:var(--font-ui,sans-serif); font-size:0.78rem; color:var(--text-muted); margin-bottom:16px;">'
                'defina a alocação-alvo (%) para cada ativo e veja exatamente quanto '
                'comprar ou vender para rebalancear a carteira.</div>',
                unsafe_allow_html=True,
            )

            pesos_alvo_list = get_pesos_alvo(portfolio_id_ativo)
            pesos_alvo_dict = {p['ticker']: float(p['peso_alvo']) for p in pesos_alvo_list}

            if valor_atual_carteira <= 0:
                st.warning("adicione posições com quantidade e preço para usar o rebalanceamento.")
            else:
                # ── 1. definição dos alvos ────────────────────────────────────
                section_title("1. defina os pesos-alvo (%)")

                tickers_port = [
                    t for t, d in ativos_alocados.items()
                    if float(d.get('quantidade') or 0) > 0
                ]

                total_alvo  = 0.0
                novos_alvos = {}

                n_cols     = min(4, len(tickers_port))
                cols_alvo  = st.columns(n_cols) if n_cols > 0 else [st]
                for i, t in enumerate(tickers_port):
                    with cols_alvo[i % len(cols_alvo)]:
                        alvo_atual = pesos_alvo_dict.get(t, 0.0)
                        novo_alvo  = st.number_input(
                            f"{t.replace('.SA', '')}",
                            min_value=0.0, max_value=100.0,
                            value=float(alvo_atual),
                            step=1.0, format="%.1f",
                            key=f"alvo_{t}",
                        )
                        novos_alvos[t] = novo_alvo
                        total_alvo    += novo_alvo

                # Indicador de soma dos alvos
                cor_total = "var(--bull)" if abs(total_alvo - 100) < 0.1 else "var(--bear)"
                aviso_soma = "✅" if abs(total_alvo - 100) < 0.1 else "⚠️ deve somar 100%"
                st.markdown(
                    f'<div style="font-family:var(--font-data,monospace); font-size:0.85rem; '
                    f'color:{cor_total}; margin:8px 0;">'
                    f'total alocado: {total_alvo:.1f}% {aviso_soma}</div>',
                    unsafe_allow_html=True,
                )

                col_s1, col_s2 = st.columns([1, 3])
                with col_s1:
                    if st.button("💾 salvar alvos", type="primary", use_container_width=True,
                                 key="btn_salvar_alvos"):
                        for t, alvo in novos_alvos.items():
                            salvar_peso_alvo(portfolio_id_ativo, t, alvo)
                        st.success("✅ alvos salvos!")
                        st.rerun()

                # ── 2. plano de rebalanceamento ───────────────────────────────
                if pesos_alvo_dict and abs(total_alvo - 100) < 5:

                    section_title("2. plano de rebalanceamento")

                    aporte_adicional = st.number_input(
                        "aporte adicional disponível (R$):",
                        min_value=0.0, value=0.0,
                        step=100.0, format="%.2f",
                        key="aporte_rebal",
                        help="valor extra que você quer aportar agora",
                    )

                    valor_total_novo = valor_atual_carteira + aporte_adicional

                    dados_rebal = []
                    for t, dados in ativos_alocados.items():
                        qtd_atual = float(dados.get('quantidade') or 0)
                        if qtd_atual <= 0:
                            continue

                        preco_at  = live_data.get(t, 0.0)
                        val_atual = qtd_atual * preco_at
                        pct_atual = (val_atual / valor_atual_carteira * 100
                                     if valor_atual_carteira > 0 else 0.0)

                        alvo_pct  = pesos_alvo_dict.get(t, 0.0)
                        val_alvo  = valor_total_novo * alvo_pct / 100
                        diferenca = val_alvo - val_atual
                        qtd_op    = diferenca / preco_at if preco_at > 0 else 0.0
                        desvio_pp = pct_atual - alvo_pct

                        dados_rebal.append({
                            'ticker':       t.replace('.SA', ''),
                            '_ticker_orig': t,
                            'peso atual':   f"{pct_atual:.1f}%",
                            'peso alvo':    f"{alvo_pct:.1f}%",
                            'desvio':       desvio_pp,
                            'valor atual':  val_atual,
                            'valor alvo':   val_alvo,
                            'diferença R$': diferenca,
                            'ação':         qtd_op,
                            'preço':        preco_at,
                        })

                    if dados_rebal:
                        dados_rebal.sort(key=lambda x: abs(x['desvio']), reverse=True)

                        for d in dados_rebal:
                            cor_op = "var(--bull)" if d['diferença R$'] > 0 else "var(--bear)"
                            op_txt = "COMPRAR" if d['diferença R$'] > 0 else "VENDER"
                            seta   = "▲" if d['diferença R$'] > 0 else "▼"

                            r1, r2, r3, r4, r5 = st.columns([2, 2, 2, 3, 3], gap="small")
                            with r1:
                                st.markdown(
                                    f'<div style="font-family:var(--font-data,monospace); color:var(--accent); font-weight:bold;">{d["ticker"]}</div>'
                                    f'<div style="font-family:var(--font-data,monospace); font-size:0.7rem; color:var(--text-muted);">{d["peso atual"]} → {d["peso alvo"]}</div>',
                                    unsafe_allow_html=True,
                                )
                            with r2:
                                cor_dev = ("var(--bear)" if abs(d['desvio']) > 5
                                           else "var(--amber)" if abs(d['desvio']) > 2
                                           else "var(--bull)")
                                st.markdown(
                                    f'<div style="font-family:var(--font-data,monospace); color:{cor_dev}; font-size:0.85rem;">'
                                    f'desvio: {d["desvio"]:+.1f}pp</div>',
                                    unsafe_allow_html=True,
                                )
                            with r3:
                                st.markdown(
                                    f'<div style="font-family:var(--font-data,monospace); color:var(--text-muted); font-size:0.8rem;">'
                                    f'R$ {d["valor atual"]:,.0f} → R$ {d["valor alvo"]:,.0f}</div>',
                                    unsafe_allow_html=True,
                                )
                            with r4:
                                st.markdown(
                                    f'<div style="font-family:var(--font-data,monospace); color:{cor_op}; font-size:0.85rem; font-weight:bold;">'
                                    f'{seta} {op_txt} R$ {abs(d["diferença R$"]):,.2f}</div>',
                                    unsafe_allow_html=True,
                                )
                            with r5:
                                if d['preço'] > 0 and abs(d['ação']) >= 0.01:
                                    qtd_fmt = (
                                        f"{d['ação']:+.0f} cotas"
                                        if abs(d['ação']) >= 1
                                        else f"{d['ação']:+.4f} lotes"
                                    )
                                    st.markdown(
                                        f'<div style="font-family:var(--font-data,monospace); color:{cor_op}; font-size:0.8rem;">'
                                        f'{qtd_fmt} @ R$ {d["preço"]:,.2f}</div>',
                                        unsafe_allow_html=True,
                                    )

                            st.markdown(
                                '<div style="height:1px; background:var(--border-subtle); margin:4px 0;"></div>',
                                unsafe_allow_html=True,
                            )

                        # Resumo
                        total_compras = sum(d['diferença R$'] for d in dados_rebal if d['diferença R$'] > 0)
                        total_vendas  = abs(sum(d['diferença R$'] for d in dados_rebal if d['diferença R$'] < 0))
                        aporte_liq    = max(0.0, total_compras - total_vendas)

                        st.markdown("---")
                        portfolio_kpis([
                            {
                                "nome":     "total a comprar",
                                "valor":    f"R$ {total_compras:,.2f}",
                                "sublabel": "ordens de compra agregadas",
                                "tone":     "bull",
                                "icone":    "🟢",
                            },
                            {
                                "nome":     "total a vender",
                                "valor":    f"R$ {total_vendas:,.2f}",
                                "sublabel": "ordens de venda agregadas",
                                "tone":     "bear",
                                "icone":    "🔴",
                            },
                            {
                                "nome":     "aporte necessário",
                                "valor":    f"R$ {aporte_liq:,.2f}",
                                "sublabel": "além do que já tem em carteira",
                                "tone":     "amber",
                                "icone":    "💰",
                            },
                        ])

# ══════════════════════════════════════════════════════════════════════════
# SELETOR DE ANÁLISE (P4-1) — renderiza SÓ a seção escolhida abaixo das posições
# ══════════════════════════════════════════════════════════════════════════
st.markdown("<br>", unsafe_allow_html=True)
section_title("📈 análises da carteira")
_secao_pf = section_selector(_SECOES_PF, key="portfolio_secao", label="análise")

# ==========================================
# tab 2: concentração de risco
# ==========================================
if _secao_pf == "📊 concentração":
    # ── CARREGA DADOS INDEPENDENTE DA ABA POSIÇÕES ────────────────────────
    _pesos_conc = st.session_state.get("pesos_ativos_cache", [])
    if not _pesos_conc:
        _pesos_conc = [p for p in get_pesos(portfolio_id=portfolio_id_ativo) if float(p.get('quantidade') or 0) > 0]
        st.session_state["pesos_ativos_cache"] = _pesos_conc

    # ── TENTA CARREGAR COTAÇÕES VIA CACHE OU YFINANCE ─────────────────────
    _live_conc = st.session_state.get("live_data_cache", {})
    if not _live_conc and _pesos_conc:
        _tickers_conc = list(set([
            _p['ticker'] for _p in _pesos_conc
        ]))
        try:
            _hist_c = yf.download(
                _tickers_conc, period="2d",
                auto_adjust=True, progress=False,
            )
            if isinstance(_hist_c.columns, pd.MultiIndex):
                _hist_c.columns = _hist_c.columns.get_level_values(0)
            _close_c = _hist_c.get('Close', _hist_c)
            for _tc in _tickers_conc:
                try:
                    if isinstance(_close_c, pd.DataFrame) and _tc in _close_c.columns:
                        _s = _close_c[_tc].dropna()
                    elif isinstance(_close_c, pd.Series):
                        _s = _close_c.dropna()
                    else:
                        continue
                    _live_conc[_tc] = {'preco': float(_s.iloc[-1])}
                except Exception:
                    _live_conc[_tc] = {'preco': 0.0}
            st.session_state["live_data_cache"] = _live_conc
        except Exception as _ec:
            logger.warning(f"[conc] cotações: {_ec}")

    section_title("🎯 análise de concentração de risco")

    # ── MONTA DADOS DE CONCENTRAÇÃO ──────────────────────────────────────
    _cache_fund = get_todos_fundamentos_cache()

    _total_cart = 0.0
    for _p in _pesos_conc:
        _qtd = float(_p.get('quantidade') or 0)
        _tb  = _p['ticker']
        _pr  = _live_conc.get(_tb, {}).get('preco', 0.0)
        # Fallback: usa preco_medio do banco se cotação live falhou
        if _pr <= 0:
            _pr = float(_p.get('preco_medio') or 0)
        _total_cart += _pr * _qtd

    if _total_cart <= 0:
        empty_state(
            "📊", "sem dados de posições",
            "adicione posições com quantidade e preço para ver a análise de concentração."
        )
    else:
        dados_conc = []

        for _p in _pesos_conc:
            _t   = _p['ticker']
            _qtd = float(_p.get('quantidade') or 0)
            if _qtd <= 0:
                continue

            _preco  = _live_conc.get(_t, {}).get('preco', 0.0)
            if _preco <= 0:
                _preco = float(_p.get('preco_medio') or 0)
            _valor  = _preco * _qtd
            _peso   = (_valor / _total_cart * 100) if _total_cart > 0 else 0.0

            _eh_br = _t.endswith('.SA')
            _moeda = 'BRL' if _eh_br else 'USD'
            _pais  = 'Brasil' if _eh_br else 'EUA'

            # setor — prioriza cache de fundamentos local
            _t_base = _t.replace('.SA', '')
            _fund_p = _cache_fund.get(_t, _cache_fund.get(_t_base, {}))
            _setor  = _fund_p.get('setor') or '—'
            if _setor in ('—', '', None):
                _setor = 'outros'

            dados_conc.append({
                'ticker': _t.replace('.SA', ''),
                'valor':  _valor,
                'peso':   _peso,
                'setor':  _setor.lower(),
                'pais':   _pais,
                'moeda':  _moeda,
                'eh_br':  _eh_br,
            })

        # ── ALERTAS DE CONCENTRAÇÃO ──────────────────────────────────────
        alertas_conc = []

        # por ativo (> 20 %)
        for _dc in dados_conc:
            if _dc['peso'] > 20:
                alertas_conc.append({
                    'tipo':  'ativo',
                    'msg':   f"⚠️ {_dc['ticker']} representa {_dc['peso']:.1f}% da carteira (limite sugerido: 20%)",
                    'nivel': 'bear' if _dc['peso'] > 30 else 'amber',
                })

        # por setor (> 40 %)
        setores_peso: dict[str, float] = {}
        for _dc in dados_conc:
            setores_peso[_dc['setor']] = setores_peso.get(_dc['setor'], 0.0) + _dc['peso']

        for _setor_k, _setor_v in setores_peso.items():
            if _setor_v > 40:
                alertas_conc.append({
                    'tipo':  'setor',
                    'msg':   f"⚠️ setor '{_setor_k}' representa {_setor_v:.1f}% da carteira (limite sugerido: 40%)",
                    'nivel': 'bear' if _setor_v > 55 else 'amber',
                })

        # por país (> 80 %)
        paises_peso: dict[str, float] = {}
        for _dc in dados_conc:
            paises_peso[_dc['pais']] = paises_peso.get(_dc['pais'], 0.0) + _dc['peso']

        for _pais_k, _pais_v in paises_peso.items():
            if _pais_v > 80:
                alertas_conc.append({
                    'tipo':  'pais',
                    'msg':   f"⚠️ {_pais_v:.1f}% da carteira concentrada em {_pais_k} — considere diversificação geográfica",
                    'nivel': 'amber',
                })

        # por moeda
        moedas_peso: dict[str, float] = {}
        for _dc in dados_conc:
            moedas_peso[_dc['moeda']] = moedas_peso.get(_dc['moeda'], 0.0) + _dc['peso']

        # exibe alertas
        if alertas_conc:
            for _alerta in alertas_conc:
                status_card(
                    f"concentração por {_alerta['tipo']}",
                    _alerta['msg'],
                    tipo=_alerta['nivel'],
                )
        else:
            status_card(
                "✅ concentração dentro dos limites",
                "nenhum ativo acima de 20%, nenhum setor acima de 40%. carteira bem diversificada.",
                tipo="bull",
            )

        # ── CARDS DE RESUMO (design system v5) ───────────────────────────
        st.markdown("---")

        _maior = max(dados_conc, key=lambda x: x['peso'])
        _cor_ma = ("bear" if _maior['peso'] > 25 else
                   "amber" if _maior['peso'] > 15 else "bull")
        _pct_brl = paises_peso.get('Brasil', 0.0)
        _pct_usd = paises_peso.get('EUA', 0.0)
        _hhi      = sum(_dc['peso'] ** 2 for _dc in dados_conc) / 10000
        _diversif = max(0.0, 100.0 - _hhi * 100)
        _cor_hhi  = ("bull" if _diversif > 70 else
                     "amber" if _diversif > 50 else "bear")

        portfolio_kpis([
            {
                "nome":        "maior posição",
                "ticker_chip": _maior['ticker'].replace('.SA', ''),
                "valor":       f"{_maior['peso']:.1f}%",
                "sublabel":    "da carteira total",
                "tone":        _cor_ma,
                "icone":       "🥇" if _cor_ma == "bull" else ("⚠" if _cor_ma == "amber" else "🚨"),
            },
            {
                "nome":     "nº de ativos",
                "valor":    str(len(dados_conc)),
                "sublabel": "diversificação por ativo",
                "tone":     "info",
                "icone":    "📊",
            },
            {
                "nome":     "exposição br / us",
                "valor":    f"{_pct_brl:.0f}% / {_pct_usd:.0f}%",
                "sublabel": "alocação por país",
                "tone":     "info",
                "icone":    "🌎",
            },
            {
                "nome":     "índice diversificação",
                "valor":    f"{_diversif:.0f}/100",
                "sublabel": "HHI (100 = máx)",
                "tone":     _cor_hhi,
                "icone":    "💎" if _cor_hhi == "bull" else "⚠",
            },
        ])

        # ── GRÁFICOS DE PIZZA ────────────────────────────────────────────
        st.markdown("---")

        _cores_pizza = [
            "#FF9900", "#00C853", "#00B0FF", "#FF1744", "#E040FB",
            "#FFD700", "#8B00FF", "#FF69B4", "#00BFFF", "#B87333",
            "#C0C0C0", "#90EE90", "#DEB887", "#6F4E37", "#F5F5DC",
            "#E5E4E2", "#FF8C00",
        ]

        def _pizza_chart(labels, values, title, height=290):
            _fig = go.Figure(go.Pie(
                labels=labels,
                values=values,
                hole=0.45,
                textinfo='label+percent',
                textfont=dict(family=_font_family_ui(), size=10, color=_chart_cores()["muted"]),
                marker=dict(
                    colors=_cores_pizza[:len(labels)],
                    line=dict(color=_chart_cores()["surface"], width=2),
                ),
                hovertemplate='%{label}<br>%{value:.1f}%<extra></extra>',
            ))
            _layout = base_layout(height=height, title=title)
            _layout['showlegend'] = False
            _fig.update_layout(**_layout)
            return _fig

        _cg1, _cg2, _cg3 = st.columns(3)

        with _cg1:
            _labels_a = [_dc['ticker'] for _dc in dados_conc]
            _values_a = [_dc['peso']   for _dc in dados_conc]
            st.plotly_chart(
                _pizza_chart(_labels_a, _values_a, "por ativo"),
                use_container_width=True,
                config={'responsive': True},
            )

        with _cg2:
            _labels_s = list(setores_peso.keys())
            _values_s = list(setores_peso.values())
            st.plotly_chart(
                _pizza_chart(_labels_s, _values_s, "por setor"),
                use_container_width=True,
                config={'responsive': True},
            )

        with _cg3:
            _labels_m = list(moedas_peso.keys())
            _values_m = list(moedas_peso.values())
            st.plotly_chart(
                _pizza_chart(_labels_m, _values_m, "por moeda"),
                use_container_width=True,
                config={'responsive': True},
            )
        st.caption("distribuição do capital por ativo, setor e moeda. boa diversificação evita concentração excessiva em um único nome, setor ou moeda — reduz o risco não-remunerado.")

        # ── MATRIZ DE CORRELAÇÃO ─────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        label_com_tooltip(
            "🔗 MATRIZ DE CORRELAÇÃO ENTRE ATIVOS",
            chave="correlacao",
            cor="var(--accent)",
            tamanho="0.72rem",
        )

        _tickers_corr = tuple([
            p['ticker'] for p in _pesos_conc
            if float(p.get('quantidade') or 0) > 0
        ])

        if len(_tickers_corr) < 2:
            st.info("adicione pelo menos 2 posições para calcular a correlação.")
        else:
            _periodo_corr = st.radio(
                "período de cálculo:",
                ["6mo", "1y", "2y"],
                format_func=lambda x: {"6mo": "6 meses", "1y": "1 ano", "2y": "2 anos"}[x],
                horizontal=True,
                key="radio_periodo_corr",
            )

            with st.spinner("calculando correlações..."):
                _res_corr = calcular_matriz_correlacao(_tickers_corr, _periodo_corr)

            _corr_df = _res_corr.get('matriz')
            _score_div = _res_corr.get('diversificacao_score', 50)
            _alertas_corr = _res_corr.get('alertas', [])

            if _corr_df is not None and not _corr_df.empty:

                # Cards de resumo (design system v5)
                _label_div = (
                    "boa diversificação" if _score_div >= 60
                    else "diversificação moderada" if _score_div >= 35
                    else "alta concentração"
                )
                _tone_div = "bull" if _score_div >= 60 else ("amber" if _score_div >= 35 else "bear")
                _n_alta = sum(1 for a in _alertas_corr if "alta" in a)
                _n_hedge = sum(1 for a in _alertas_corr if "hedge" in a)

                portfolio_kpis([
                    {
                        "nome":     "score diversificação",
                        "valor":    f"{_score_div}/100",
                        "sublabel": _label_div,
                        "tone":     _tone_div,
                        "icone":    "💎" if _tone_div == "bull" else "⚠",
                    },
                    {
                        "nome":     "pares alta correlação",
                        "valor":    str(_n_alta),
                        "sublabel": "> 0.70 — concentração oculta",
                        "tone":     "bear" if _n_alta > 0 else "bull",
                        "icone":    "🚨" if _n_alta > 0 else "✓",
                    },
                    {
                        "nome":     "hedges naturais",
                        "valor":    str(_n_hedge),
                        "sublabel": "correlação < -0.30",
                        "tone":     "bull" if _n_hedge > 0 else "muted",
                        "icone":    "🛡" if _n_hedge > 0 else "—",
                    },
                ])
                tooltip("correlacao")

                st.markdown("<br>", unsafe_allow_html=True)

                # Heatmap de correlação
                _ticks = _corr_df.columns.tolist()
                _ticks_clean = [t.replace('.SA', '') for t in _ticks]
                _z = _corr_df.values.tolist()

                # Texto das células
                _text = [
                    [f"{_corr_df.iloc[i, j]:.2f}" for j in range(len(_ticks))]
                    for i in range(len(_ticks))
                ]

                _fig_corr = go.Figure(go.Heatmap(
                    z=_z,
                    x=_ticks_clean,
                    y=_ticks_clean,
                    text=_text,
                    texttemplate="%{text}",
                    textfont=dict(size=11, color='white', family='Inter, system-ui, sans-serif'),
                    colorscale=[
                        [0.0,  "#1565C0"],   # azul escuro — correlação negativa
                        [0.35, "#1a1a1a"],   # neutro — correlação zero
                        [0.65, "#1a1a1a"],   # neutro
                        [1.0,  "#B71C1C"],   # vermelho — correlação alta
                    ],
                    zmin=-1, zmax=1,
                    colorbar=dict(
                        title=dict(text="correlação", font=dict(color="#888", size=10)),
                        tickfont=dict(color="#888", size=9),
                        thickness=12,
                    ),
                    hovertemplate=(
                        "%{y} ↔ %{x}<br>"
                        "correlação: %{z:.2f}<extra></extra>"
                    ),
                ))

                _dim_corr = max(280, min(len(_ticks) * 55, 600))
                _lay_corr = base_layout(
                    height=_dim_corr,
                    title=f"correlação de retornos diários — {_periodo_corr}"
                )
                _cc_corr = _chart_cores()
                _lay_corr.update(
                    xaxis=dict(tickfont=dict(size=10, color=_cc_corr["muted"], family='Inter, system-ui, sans-serif')),
                    yaxis=dict(tickfont=dict(size=10, color=_cc_corr["muted"], family='Inter, system-ui, sans-serif')),
                    margin=dict(l=80, r=40, t=40, b=80),
                    autosize=True,
                )
                _fig_corr.update_layout(**_lay_corr)
                st.plotly_chart(_fig_corr, use_container_width=True, config={'responsive': True})

                # Alertas de correlação
                if _alertas_corr:
                    st.markdown(
                        '<div style="font-family:var(--font-ui,sans-serif); font-size:0.72rem; '
                        'color:var(--text-muted); margin-top:4px;">⚠️ pares críticos:</div>',
                        unsafe_allow_html=True,
                    )
                    for _ac in _alertas_corr:
                        _cor_ac = "var(--amber)" if "alta" in _ac else "var(--bull)"
                        st.markdown(
                            f'<div style="font-family:var(--font-data,monospace); font-size:0.75rem; '
                            f'color:{_cor_ac}; padding:2px 0;">• {_ac}</div>',
                            unsafe_allow_html=True,
                        )

                # Interpretação IA
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(
                    "🧠 ia: interpretar diversificação da carteira",
                    key="btn_ia_corr",
                    type="secondary",
                ):
                    _prompt_corr = (
                        f"portfólio com {len(_ticks)} ativos.\n\n"
                        f"score de diversificação: {_score_div}/100\n\n"
                        f"pares com alta correlação (> 0.70):\n"
                        + "\n".join([f"- {a}" for a in _alertas_corr if "alta" in a] or ["nenhum"])
                        + f"\n\npares com correlação negativa (hedge natural):\n"
                        + "\n".join([f"- {a}" for a in _alertas_corr if "hedge" in a] or ["nenhum"])
                        + f"\n\nativos: {', '.join(_ticks_clean)}\n\n"
                        "em 3 tópicos curtos (letra minúscula):\n"
                        "1. o portfólio está bem diversificado ou há concentração oculta?\n"
                        "2. quais pares representam o maior risco de correlação?\n"
                        "3. que tipo de ativo poderia melhorar a diversificação?"
                    )
                    _us_corr = st.session_state.get('user_settings', {})
                    chamar_ia(
                        prompt_usuario=_prompt_corr,
                        system=SYSTEM_PORTFOLIO,
                        max_tokens=400,
                        temperatura=0.3,
                        stream=True,
                        user_settings=_us_corr,
                    )
            else:
                st.warning("dados insuficientes para calcular correlação.")

# ==========================================
# tab 3: risco institucional (VaR, Brinson, fatores, dividendos)
# ==========================================
if _secao_pf == "📐 risco":
    section_title("📐 risco institucional do portfólio")

    if not ativos_alocados:
        empty_state(
            "💼",
            "sem posições para analisar",
            "adicione posições na aba 'posições & p&l' antes de calcular risco.",
        )
    else:
        # Constrói carteira a partir das posições da aba principal.
        # ativos_alocados[t] = {'quantidade', 'preco_medio', 'peso'}; live_data[t] = preço atual.
        _pesos_carteira: dict[str, float] = {}
        _valor_total = 0.0
        for _tk_orig, _dados_pos in ativos_alocados.items():
            _qtd = float(_dados_pos.get("quantidade") or 0)
            _preco_atual = float(live_data.get(_tk_orig) or 0)
            _valor = _qtd * _preco_atual
            if _valor <= 0:
                continue
            _tk_base = mapear_ticker_base(_tk_orig)
            _pesos_carteira[_tk_base] = _pesos_carteira.get(_tk_base, 0) + _valor
            _valor_total += _valor

        if _valor_total <= 0 or not _pesos_carteira:
            empty_state(
                "📊",
                "valor da carteira indisponível",
                "verifique se as cotações ao vivo foram carregadas na aba 'posições & p&l'.",
            )
        else:
            # Normaliza pesos
            _pesos_carteira = {t: v / _valor_total for t, v in _pesos_carteira.items()}

            # ── EXPOSIÇÃO MACRO DO BOOK + SIZING SUGERIDO (Fronteira 2) ──────
            try:
                from utils.macro_context import garantir_macro_context
                _macro_ctx_pf = garantir_macro_context()
            except Exception:
                _macro_ctx_pf = st.session_state.get("macro_context", {}) or {}
            _cache_fund_pf = get_todos_fundamentos_cache() or {}
            _setor_map_pf = {
                t: (_cache_fund_pf.get(t, {}) or {}).get("setor", "")
                for t in _pesos_carteira
            }
            _health_map_pf = {
                h["ticker"]: h.get("score") for h in (get_health_scores() or [])
            }

            with st.expander("🌡️ exposição macro do book (regime + inflação setorial)",
                             expanded=True):
                try:
                    from utils.portfolio_sizing import exposicao_macro_book
                    _exp_macro = exposicao_macro_book(
                        _pesos_carteira, _setor_map_pf, _macro_ctx_pf
                    )
                except Exception as _e_exp:
                    _exp_macro = {}
                    logger.warning(f"[portfolio] exposição macro falhou: {_e_exp}")

                if _exp_macro:
                    _tone_book = (
                        "bull" if _exp_macro["tilt_medio"] >= 2
                        else "bear" if _exp_macro["tilt_medio"] <= -2
                        else "amber"
                    )
                    status_card(
                        "leitura macro do book",
                        _exp_macro["leitura"],
                        tipo="bear" if _tone_book == "bear" else (
                            "bull" if _tone_book == "bull" else "info"),
                    )
                    portfolio_kpis([
                        {"nome": "tilt macro médio", "valor": f"{_exp_macro['tilt_medio']:+.1f}",
                         "sublabel": "−8 contra · +8 a favor", "tone": _tone_book, "icone": "🧭"},
                        {"nome": "favorável", "valor": f"{_exp_macro['pct_favoravel']:.0f}%",
                         "sublabel": "peso com vento a favor", "tone": "bull", "icone": "🌤"},
                        {"nome": "exposto a duration", "valor": f"{_exp_macro['duration_exposta_pct']:.0f}%",
                         "sublabel": "setores sob juro alto", "tone": "amber", "icone": "📉"},
                        {"nome": "proteção inflação", "valor": f"{_exp_macro['inflacao_protegida_pct']:.0f}%",
                         "sublabel": "receita indexada", "tone": "info", "icone": "🛡"},
                    ])
                    _piores_book = [a for a in _exp_macro["por_ativo"] if a["tilt"] < 0][:6]
                    if _piores_book:
                        st.markdown("##### posições brigando com o macro")
                        st.dataframe(
                            pd.DataFrame([{
                                "ticker": a["ticker"].replace(".SA", ""),
                                "peso %": a["peso"], "setor": a["setor"],
                                "tilt macro": a["tilt"], "impacto": a["impacto"],
                            } for a in _piores_book]),
                            use_container_width=True, hide_index=True,
                        )
                else:
                    st.caption("exposição macro indisponível (sem setor/cache).")

            with st.expander("🎯 sizing sugerido — risk parity tiltado por edge e macro",
                             expanded=False):
                st.markdown(
                    "*peso-alvo = paridade de risco (1/volatilidade) × edge (health score) "
                    "× vento macro-setorial. compare com seu peso atual para rebalancear.*"
                )
                try:
                    from utils.portfolio_sizing import sugerir_sizing
                    from utils.price_history import obter_close_carteira as _occ_sz
                    _precos_sz = _occ_sz(tuple(_pesos_carteira.keys()), periodo="1y")
                    _sizing = sugerir_sizing(
                        _pesos_carteira, _precos_sz, _health_map_pf,
                        _setor_map_pf, _macro_ctx_pf,
                    )
                except Exception as _e_sz:
                    _sizing = []
                    logger.warning(f"[portfolio] sizing falhou: {_e_sz}")

                if _sizing:
                    _df_sizing = pd.DataFrame([{
                        "ticker":     s["ticker"].replace(".SA", ""),
                        "peso atual": s["peso_atual"],
                        "peso-alvo":  s["peso_alvo"],
                        "Δ pp":       s["delta_pp"],
                        "ação":       s["acao"],
                        "vol %":      s["vol"],
                        "health":     s["health"],
                        "macro":      s["macro_pts"],
                    } for s in _sizing])
                    _cfg_sz = {
                        "peso atual": st.column_config.ProgressColumn("peso atual %", min_value=0, max_value=float(max(20, _df_sizing["peso atual"].max())), format="%.1f"),
                        "peso-alvo":  st.column_config.ProgressColumn("peso-alvo %", min_value=0, max_value=float(max(20, _df_sizing["peso-alvo"].max())), format="%.1f"),
                    }
                    try:
                        st.dataframe(_df_sizing, use_container_width=True, hide_index=True, column_config=_cfg_sz)
                    except Exception:
                        st.dataframe(_df_sizing, use_container_width=True, hide_index=True)
                    info_box(
                        tipo="info",
                        titulo="como ler",
                        texto="‘aumentar/reduzir’ é o movimento para alinhar risco e edge. "
                              "vol alta derruba o peso-alvo (paridade de risco); health alto e "
                              "vento macro a favor elevam. teto de 20% por posição quando viável.",
                        icone="🎯",
                    )
                else:
                    st.caption("dados insuficientes para sizing (precisa de histórico de preços).")

            # ── Seção VaR ───────────────────────────────────────────────
            with st.expander("📉 value-at-risk (VaR e CVaR)", expanded=True):
                st.markdown(
                    "*VaR responde: 'em um dia ruim típico (1 em 20 ou 1 em 100), "
                    "quanto a carteira pode perder?'. CVaR responde: 'se passar do VaR, "
                    "qual a perda média esperada na cauda?'.*"
                )

                _col_periodo, _col_horizonte = st.columns([1, 1])
                with _col_periodo:
                    _periodo_var = st.selectbox(
                        "janela de retornos",
                        options=["1y", "2y", "3y", "5y"],
                        index=1,
                        key="var_periodo",
                        help="histórico usado para calcular a distribuição de retornos diários",
                    )
                with _col_horizonte:
                    _label_horizonte = st.selectbox(
                        "horizonte",
                        options=["1 dia", "5 dias (semanal)", "21 dias (mensal)"],
                        index=0,
                        key="var_horizonte",
                        help="perda projetada no horizonte selecionado (escala pela raiz do tempo)",
                    )
                    _horizonte_dias = {"1 dia": 1, "5 dias (semanal)": 5,
                                        "21 dias (mensal)": 21}[_label_horizonte]

                with st.spinner("calculando risco..."):
                    from utils.price_history import obter_close_carteira
                    from utils.risk_var import calcular_risco_carteira, formatar_perda

                    _precos_var = obter_close_carteira(
                        tuple(_pesos_carteira.keys()),
                        periodo=_periodo_var,
                    )
                    _resultado = calcular_risco_carteira(
                        _pesos_carteira,
                        _precos_var,
                        valor_carteira=_valor_total,
                        horizonte_dias=_horizonte_dias,
                    )

                if _resultado is None:
                    st.warning(
                        f"dados insuficientes (precisa ≥ 60 dias de histórico para "
                        f"{len(_pesos_carteira)} ativos). tente um período maior."
                    )
                else:
                    _r = _resultado
                    # Header com vol anual + número de observações
                    _c_meta1, _c_meta2, _c_meta3 = st.columns(3)
                    with _c_meta1:
                        metric_card(
                            "vol anualizada",
                            f"{_r.vol_anual*100:.1f}%",
                            sublabel=f"σ diária: {_r.vol_diaria*100:.2f}%",
                        )
                    with _c_meta2:
                        metric_card(
                            "observações",
                            f"{_r.n_observacoes}",
                            sublabel=f"janela: {_periodo_var}",
                        )
                    with _c_meta3:
                        _fat_label = "🚨 fat tails detectado" if _r.fat_tails else "✅ caudas normais"
                        _fat_desc = (
                            "histórico > 30% pior que paramétrico — distribuição assimétrica"
                            if _r.fat_tails
                            else "histórico próximo à hipótese normal"
                        )
                        metric_card("perfil de caudas", _fat_label, sublabel=_fat_desc)

                    st.markdown(f"#### perda esperada em **{_label_horizonte.split(' ')[0]} dia(s)**")

                    # VaR 95% e 99% lado a lado
                    _col1, _col2 = st.columns(2)

                    with _col1:
                        st.markdown("##### confiança 95% (1 dia ruim em 20)")
                        _p95_pct, _p95_brl = formatar_perda(_r.var_95_pct, _valor_total)
                        _p95p_pct, _p95p_brl = formatar_perda(_r.var_95_param_pct, _valor_total)
                        _c95_pct, _c95_brl = formatar_perda(_r.cvar_95_pct, _valor_total)
                        metric_card(
                            "VaR histórico",
                            f"-{_p95_pct}",
                            sublabel=f"perda de {_p95_brl}",
                        )
                        metric_card(
                            "VaR paramétrico",
                            f"-{_p95p_pct}",
                            sublabel=f"hipótese normal: {_p95p_brl}",
                        )
                        metric_card(
                            "CVaR (expected shortfall)",
                            f"-{_c95_pct}",
                            sublabel=f"perda média se passar do VaR: {_c95_brl}",
                        )

                    with _col2:
                        st.markdown("##### confiança 99% (1 dia ruim em 100)")
                        _p99_pct, _p99_brl = formatar_perda(_r.var_99_pct, _valor_total)
                        _p99p_pct, _p99p_brl = formatar_perda(_r.var_99_param_pct, _valor_total)
                        _c99_pct, _c99_brl = formatar_perda(_r.cvar_99_pct, _valor_total)
                        metric_card(
                            "VaR histórico",
                            f"-{_p99_pct}",
                            sublabel=f"perda de {_p99_brl}",
                        )
                        metric_card(
                            "VaR paramétrico",
                            f"-{_p99p_pct}",
                            sublabel=f"hipótese normal: {_p99p_brl}",
                        )
                        metric_card(
                            "CVaR (expected shortfall)",
                            f"-{_c99_pct}",
                            sublabel=f"perda média se passar do VaR: {_c99_brl}",
                        )

                    # Histograma da distribuição de retornos
                    st.markdown("##### distribuição de retornos diários da carteira")
                    _rets_pct = _r.retornos_diarios * 100
                    _fig = go.Figure()
                    _fig.add_trace(go.Histogram(
                        x=_rets_pct,
                        nbinsx=60,
                        marker_color=_chart_cores().get("accent", "#FF9900"),
                        opacity=0.85,
                        name="retornos diários",
                    ))
                    _fig.add_vline(
                        x=_r.var_95_pct * 100,
                        line=dict(color="#ffaa33", width=2, dash="dash"),
                        annotation_text=f"VaR 95%: {_r.var_95_pct*100:.2f}%",
                        annotation_position="top left",
                    )
                    _fig.add_vline(
                        x=_r.var_99_pct * 100,
                        line=dict(color="#ff3030", width=2, dash="dash"),
                        annotation_text=f"VaR 99%: {_r.var_99_pct*100:.2f}%",
                        annotation_position="top left",
                    )
                    _fig.update_layout(
                        **base_layout(),
                        height=350,
                        xaxis_title="retorno diário (%)",
                        yaxis_title="frequência",
                        showlegend=False,
                    )
                    st.plotly_chart(_fig, use_container_width=True)
                    st.caption("distribuição dos retornos diários da carteira. a cauda esquerda (perdas) define o var — quanto mais gorda, maior a probabilidade de quedas extremas.")

                    # Sumário em linguagem natural
                    _diag = ""
                    if _r.fat_tails:
                        _diag = (
                            f" o histograma mostra **fat tails** — a distribuição empírica "
                            f"é mais severa que a normal. Use o VaR histórico como referência, "
                            f"não o paramétrico."
                        )
                    st.info(
                        f"📐 com 95% de confiança, a carteira perde no máximo "
                        f"**{_p95_pct}** ({_p95_brl}) em {_label_horizonte}. "
                        f"se passar disso, a perda média esperada é **{_c95_pct}** "
                        f"({_c95_brl}).{_diag}"
                    )

            # ── Decomposição Brinson ──────────────────────────────────────
            with st.expander("📊 decomposição brinson (atribuição por setor)", expanded=False):
                st.markdown(
                    "*decompõe o retorno excessivo vs benchmark em três efeitos: "
                    "**alocação** (peso setorial diferente do mercado), **seleção** "
                    "(ativos melhores que a média do setor) e **interação** (cruzamento). "
                    "soma = retorno carteira − retorno benchmark.*"
                )

                from utils.tickers import SCREENER_B3, SCREENER_US
                from utils.risk_brinson import calcular_brinson
                from utils.price_history import obter_close_carteira
                from database.db import get_todos_fundamentos_cache

                _periodo_br = st.selectbox(
                    "janela de comparação",
                    options=["3m", "6m", "1y", "2y"],
                    index=2,
                    key="brinson_periodo",
                    help="período usado para calcular retornos da carteira e do benchmark",
                )

                # Detecta mercado dominante na carteira (BR vs US)
                _n_br = sum(1 for t in _pesos_carteira if t.endswith(".SA"))
                _n_us = len(_pesos_carteira) - _n_br
                _eh_br = _n_br >= _n_us

                # Universo do benchmark — top-50 por market cap para limitar download
                _cache_fund = get_todos_fundamentos_cache()
                _setores = {t: d.get("setor") or "" for t, d in _cache_fund.items()}
                _mkt_caps = {
                    t: float(d.get("market_cap") or 0)
                    for t, d in _cache_fund.items() if d.get("market_cap")
                }

                _screener = SCREENER_B3 if _eh_br else SCREENER_US
                # FII fora — Brinson é sobre ações
                _universo = [
                    t for t in _screener
                    if t in _mkt_caps and not (t.endswith("11.SA") and t in _cache_fund and "fii" in str(_cache_fund.get(t, {}).get("setor", "")).lower())
                ]
                _universo_top = sorted(_universo, key=lambda t: -_mkt_caps[t])[:50]

                # Tickers necessários = carteira + universo
                _todos_tickers = list(set(list(_pesos_carteira.keys()) + _universo_top))

                with st.spinner("calculando atribuição brinson..."):
                    _precos_br = obter_close_carteira(
                        tuple(_todos_tickers),
                        periodo=_periodo_br,
                    )
                    _bri = calcular_brinson(
                        pesos_carteira=_pesos_carteira,
                        universo_benchmark=_universo_top,
                        setores=_setores,
                        market_caps=_mkt_caps,
                        precos=_precos_br,
                    )

                if _bri is None:
                    st.warning(
                        "dados insuficientes para decomposição brinson. precisa de "
                        "preços (price_history) + setor + market_cap no cache para "
                        "ambos carteira e universo do benchmark."
                    )
                else:
                    _bench_label = "IBOV proxy" if _eh_br else "S&P 500 proxy"
                    # Header — retornos
                    _bc1, _bc2, _bc3 = st.columns(3)
                    with _bc1:
                        metric_card(
                            "retorno carteira",
                            f"{_bri.retorno_carteira*100:+.2f}%",
                            sublabel=f"janela: {_periodo_br}",
                        )
                    with _bc2:
                        metric_card(
                            f"retorno {_bench_label}",
                            f"{_bri.retorno_benchmark*100:+.2f}%",
                            sublabel=f"top-{len(_universo_top)} por mkt cap",
                        )
                    with _bc3:
                        _excess = _bri.retorno_excessivo * 100
                        _excess_emoji = "🟢" if _excess > 0 else "🔴"
                        metric_card(
                            "retorno excessivo",
                            f"{_excess_emoji} {_excess:+.2f}pp",
                            sublabel="carteira − benchmark",
                        )

                    # 3 efeitos
                    st.markdown("##### efeitos Brinson")
                    _ec1, _ec2, _ec3 = st.columns(3)
                    with _ec1:
                        metric_card(
                            "alocação",
                            f"{_bri.allocation*100:+.2f}pp",
                            sublabel="peso setorial vs mercado",
                        )
                    with _ec2:
                        metric_card(
                            "seleção",
                            f"{_bri.selection*100:+.2f}pp",
                            sublabel="picks dentro de cada setor",
                        )
                    with _ec3:
                        metric_card(
                            "interação",
                            f"{_bri.interaction*100:+.2f}pp",
                            sublabel="cruzamento (geralmente pequeno)",
                        )

                    # Waterfall: benchmark → alocação → seleção → interação → carteira
                    import plotly.graph_objects as go
                    _fig_wf = go.Figure(go.Waterfall(
                        name="brinson",
                        orientation="v",
                        measure=["absolute", "relative", "relative", "relative", "total"],
                        x=[_bench_label, "alocação", "seleção", "interação", "carteira"],
                        y=[
                            _bri.retorno_benchmark * 100,
                            _bri.allocation * 100,
                            _bri.selection * 100,
                            _bri.interaction * 100,
                            _bri.retorno_carteira * 100,
                        ],
                        text=[
                            f"{_bri.retorno_benchmark*100:+.2f}%",
                            f"{_bri.allocation*100:+.2f}pp",
                            f"{_bri.selection*100:+.2f}pp",
                            f"{_bri.interaction*100:+.2f}pp",
                            f"{_bri.retorno_carteira*100:+.2f}%",
                        ],
                        textposition="outside",
                        increasing={"marker": {"color": "#16a34a"}},
                        decreasing={"marker": {"color": "#dc2626"}},
                        totals={"marker": {"color": "#2563eb"}},
                    ))
                    _fig_wf.update_layout(
                        title="benchmark → carteira: decomposição dos efeitos",
                        yaxis_title="%",
                        height=380,
                        showlegend=False,
                        margin=dict(t=40, b=20, l=0, r=0),
                    )
                    st.plotly_chart(_fig_wf, use_container_width=True)
                    st.caption("atribuição de brinson: decompõe o retorno vs. benchmark em efeito de alocação (escolha de setores) e de seleção (escolha de ativos dentro do setor).")

                    # Tabela por setor
                    st.markdown("##### atribuição por setor")
                    _linhas_setor = []
                    for s, d in sorted(
                        _bri.por_setor.items(),
                        key=lambda x: -(x[1]['alloc'] + x[1]['sel'])
                    ):
                        _linhas_setor.append({
                            "setor": s,
                            "peso carteira": f"{d['peso_p']*100:.1f}%",
                            "peso bench": f"{d['peso_b']*100:.1f}%",
                            "ret carteira": f"{d['ret_p']*100:+.1f}%" if d['peso_p'] > 0 else "—",
                            "ret bench": f"{d['ret_b']*100:+.1f}%" if d['peso_b'] > 0 else "—",
                            "alocação": f"{d['alloc']*100:+.2f}pp",
                            "seleção": f"{d['sel']*100:+.2f}pp",
                        })
                    _mn_br = 'var(--font-mono,monospace)'
                    _df_br = pd.DataFrame(_linhas_setor)
                    _hdrs_br = "".join(
                        f'<th style="padding:7px 10px;text-align:{"left" if c=="setor" else "right"};'
                        f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                        f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                        for c in _df_br.columns
                    )
                    _rows_br = ""
                    for _, row in _df_br.iterrows():
                        _cells_br = ""
                        for col in _df_br.columns:
                            _v = str(row[col])
                            _align = "left" if col == "setor" else "right"
                            _cv = "var(--text-primary)"
                            if col in ("alocação","seleção","ret carteira","ret bench"):
                                _cv = "#2ecc71" if _v.startswith('+') else ("#e74c3c" if _v.startswith('-') else "var(--text-muted)")
                            _cells_br += (f'<td style="padding:7px 10px;text-align:{_align};">'
                                          f'<span style="font-family:{_mn_br};font-size:0.8rem;color:{_cv};">{_v}</span></td>')
                        _rows_br += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                                     f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                                     f'onmouseout="this.style.background=\'transparent\'">{_cells_br}</tr>')
                    st.markdown(
                        f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
                        f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                        f'<thead><tr>{_hdrs_br}</tr></thead><tbody>{_rows_br}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

                    # Sumário em linguagem natural
                    _dominante = "alocação" if abs(_bri.allocation) > abs(_bri.selection) else "seleção"
                    _veredito = (
                        f"a carteira **{'superou' if _bri.retorno_excessivo > 0 else 'ficou atrás do'}** "
                        f"o {_bench_label} em **{abs(_bri.retorno_excessivo)*100:.2f}pp** "
                        f"na janela de {_periodo_br}. o componente dominante foi **{_dominante}** "
                        f"({(_bri.allocation if _dominante == 'alocação' else _bri.selection)*100:+.2f}pp). "
                    )
                    if _dominante == "alocação":
                        _veredito += (
                            "o resultado veio principalmente de **pesar setores diferentes** do mercado — "
                            "decisão top-down (setorial)."
                        )
                    else:
                        _veredito += (
                            "o resultado veio principalmente de **escolher ativos melhores** dentro de "
                            "cada setor — decisão bottom-up (picking)."
                        )
                    st.info(_veredito)

            with st.expander("🎯 exposição a fatores fama-french", expanded=False):
                st.markdown(
                    "*regressão dos retornos da carteira sobre 3 fatores estilo "
                    "Fama-French. **β_MKT** mede sensibilidade ao mercado, **β_SMB** "
                    "tilt para small vs large caps, **β_HML** tilt para value vs "
                    "growth. **alpha** é o retorno não explicado pelos fatores. "
                    "fatores construídos do próprio universo do screener — sem "
                    "dependência externa.*"
                )

                from utils.risk_factors import (
                    construir_fatores_sinteticos, regressao_fama_french,
                )
                from utils.risk_var import calcular_retornos_carteira
                from utils.tickers import SCREENER_B3 as _SC_B3, SCREENER_US as _SC_US

                _periodo_ff = st.selectbox(
                    "janela de regressão",
                    options=["1y", "2y", "3y"],
                    index=1,
                    key="ff_periodo",
                    help="histórico usado na regressão. mais longo = betas mais estáveis",
                )

                # Mercado dominante para escolher screener e rf
                _n_br_ff = sum(1 for t in _pesos_carteira if t.endswith(".SA"))
                _eh_br_ff = _n_br_ff >= (len(_pesos_carteira) - _n_br_ff)
                _screener_ff = _SC_B3 if _eh_br_ff else _SC_US
                _rf_anual = 0.1475 if _eh_br_ff else 0.045  # Selic vs T-10y

                _cache_ff = get_todos_fundamentos_cache()
                _mc_ff = {
                    t: float(d.get("market_cap") or 0)
                    for t, d in _cache_ff.items() if d.get("market_cap")
                }
                _pvp_ff = {
                    t: float(d.get("p/vp") or 0)
                    for t, d in _cache_ff.items() if d.get("p/vp")
                }
                _universo_ff = sorted(
                    [t for t in _screener_ff if t in _mc_ff],
                    key=lambda t: -_mc_ff[t],
                )[:50]
                _todos_ff = list(set(list(_pesos_carteira.keys()) + _universo_ff))

                with st.spinner("rodando regressão fama-french..."):
                    _precos_ff = obter_close_carteira(
                        tuple(_todos_ff),
                        periodo=_periodo_ff,
                    )
                    _fatores = construir_fatores_sinteticos(
                        _universo_ff, _mc_ff, _pvp_ff, _precos_ff,
                        rf_anual=_rf_anual,
                    )
                    _rets_cart = calcular_retornos_carteira(_pesos_carteira, _precos_ff)
                    _ff = regressao_fama_french(_rets_cart, _fatores)

                if _ff is None:
                    st.warning(
                        "dados insuficientes (precisa ≥ 60 dias de retornos + fatores). "
                        "tente um período maior."
                    )
                else:
                    # Header: alpha + R² + N obs
                    _fc1, _fc2, _fc3 = st.columns(3)
                    with _fc1:
                        _alpha_emoji = (
                            "🟢" if (_ff.alpha_anual > 0 and _ff.pvalue_alpha < 0.10) else
                            "🔴" if (_ff.alpha_anual < 0 and _ff.pvalue_alpha < 0.10) else
                            "⚪"
                        )
                        metric_card(
                            "alpha anualizado",
                            f"{_alpha_emoji} {_ff.alpha_anual*100:+.2f}%",
                            sublabel=f"p-valor: {_ff.pvalue_alpha:.3f}",
                        )
                    with _fc2:
                        metric_card(
                            "R² do modelo",
                            f"{_ff.r_squared*100:.1f}%",
                            sublabel="variância explicada pelos fatores",
                        )
                    with _fc3:
                        metric_card(
                            "observações",
                            f"{_ff.n_obs}",
                            sublabel=f"janela: {_periodo_ff}",
                        )

                    # 3 betas
                    st.markdown("##### exposições (betas)")
                    _bb1, _bb2, _bb3 = st.columns(3)
                    with _bb1:
                        metric_card(
                            "β mercado",
                            f"{_ff.beta_mkt:+.2f}",
                            sublabel=f"sens. ao mercado · p={_ff.pvalue_mkt:.3f}",
                        )
                    with _bb2:
                        _smb_label = "small caps" if _ff.beta_smb > 0 else "large caps"
                        metric_card(
                            "β SMB",
                            f"{_ff.beta_smb:+.2f}",
                            sublabel=f"tilt: {_smb_label} · p={_ff.pvalue_smb:.3f}",
                        )
                    with _bb3:
                        _hml_label = "value" if _ff.beta_hml > 0 else "growth"
                        metric_card(
                            "β HML",
                            f"{_ff.beta_hml:+.2f}",
                            sublabel=f"tilt: {_hml_label} · p={_ff.pvalue_hml:.3f}",
                        )

                    # Gráfico de barras dos betas com intervalo de confiança 95%
                    import plotly.graph_objects as go
                    _fig_betas = go.Figure()
                    _nomes = ["β mercado", "β SMB (smalls)", "β HML (value)"]
                    _vals = [_ff.beta_mkt, _ff.beta_smb, _ff.beta_hml]
                    _ses = [_ff.se_mkt, _ff.se_smb, _ff.se_hml]
                    _fig_betas.add_trace(go.Bar(
                        x=_nomes, y=_vals,
                        error_y=dict(type="data", array=[1.96 * s for s in _ses]),
                        marker_color=["#3b82f6", "#f59e0b", "#10b981"],
                        text=[f"{v:+.2f}" for v in _vals],
                        textposition="outside",
                    ))
                    _fig_betas.update_layout(
                        title="exposições aos fatores (intervalo 95%)",
                        yaxis_title="beta",
                        height=320,
                        showlegend=False,
                        margin=dict(t=40, b=20, l=0, r=0),
                    )
                    _fig_betas.add_hline(y=0, line_width=1, line_color=_chart_cores()["muted"])
                    st.plotly_chart(_fig_betas, use_container_width=True)
                    st.caption("sensibilidade da carteira a cada fator de risco (mercado, câmbio, juros), com intervalo de 95%. betas altos indicam maior exposição àquele fator.")

                    # Sumário em linguagem natural
                    _interp_mkt = (
                        "defensiva (menos sensível que o mercado)" if _ff.beta_mkt < 0.9 else
                        "agressiva (mais sensível que o mercado)" if _ff.beta_mkt > 1.1 else
                        "alinhada com o mercado"
                    )
                    _interp_smb = (
                        "**small caps**" if _ff.beta_smb > 0.2 else
                        "**large caps**" if _ff.beta_smb < -0.2 else
                        "**neutro em tamanho**"
                    )
                    _interp_hml = (
                        "**value** (P/VP baixo)" if _ff.beta_hml > 0.2 else
                        "**growth** (P/VP alto)" if _ff.beta_hml < -0.2 else
                        "**neutro em estilo**"
                    )
                    _alpha_sig = "significativo" if _ff.pvalue_alpha < 0.10 else "não-significativo"
                    st.info(
                        f"🎯 carteira é **{_interp_mkt}** (β={_ff.beta_mkt:.2f}), com tilt "
                        f"para {_interp_smb} e {_interp_hml}. alpha anualizado: "
                        f"**{_ff.alpha_anual*100:+.2f}%** ({_alpha_sig} estatisticamente "
                        f"a 90%). os fatores explicam **{_ff.r_squared*100:.0f}%** da "
                        f"variância dos retornos da carteira."
                    )

            with st.expander("💰 projeção de dividendos 12m", expanded=False):
                st.markdown(
                    "*projeta os próximos 12 pagamentos por ticker replicando o padrão "
                    "histórico × crescimento yoy (cap ±10%). lê do cache dividend_history "
                    "— sem chamadas yfinance.*"
                )
                from utils.dividend_projection import projetar_dividendos_carteira

                # Constrói {ticker_base: quantidade} a partir de ativos_alocados
                _quantidades: dict[str, float] = {}
                for _tk_orig, _dados_pos in ativos_alocados.items():
                    _qtd = float(_dados_pos.get("quantidade") or 0)
                    if _qtd <= 0:
                        continue
                    _tk_base = mapear_ticker_base(_tk_orig)
                    _quantidades[_tk_base] = _quantidades.get(_tk_base, 0) + _qtd

                with st.spinner("projetando dividendos..."):
                    _proj = projetar_dividendos_carteira(
                        _quantidades,
                        valor_carteira=_valor_total,
                    )

                if _proj.renda_total_12m <= 0:
                    st.info(
                        "sem histórico de dividendos suficiente no cache para projetar. "
                        "verifique se o ETL `sync_br` / `sync_us` já populou a tabela "
                        "`dividend_history`."
                    )
                else:
                    # Header — 3 cards
                    _cd1, _cd2, _cd3 = st.columns(3)
                    with _cd1:
                        metric_card(
                            "renda esperada 12m",
                            f"R$ {_proj.renda_total_12m:,.0f}".replace(",", "."),
                            sublabel=f"≈ R$ {_proj.renda_total_12m/12:,.0f}/mês".replace(",", "."),
                        )
                    with _cd2:
                        metric_card(
                            "yield projetado",
                            f"{_proj.dy_projetado_pct:.2f}%",
                            sublabel="sobre o valor atual da carteira",
                        )
                    with _cd3:
                        _n_pagantes = sum(1 for v in _proj.por_ticker.values() if v > 0)
                        metric_card(
                            "ativos pagantes",
                            f"{_n_pagantes}",
                            sublabel=f"de {len(_quantidades)} posições",
                        )

                    # Calendário mensal (plotly)
                    import plotly.graph_objects as go
                    _meses = list(_proj.por_mes.keys())
                    _valores = list(_proj.por_mes.values())
                    _fig_cal = go.Figure(go.Bar(
                        x=_meses,
                        y=_valores,
                        marker_color="#16a34a",
                        text=[f"R$ {v:,.0f}".replace(",", ".") if v > 0 else ""
                              for v in _valores],
                        textposition="outside",
                        hovertemplate="<b>%{x}</b><br>R$ %{y:,.0f}<extra></extra>",
                    ))
                    _fig_cal.update_layout(
                        title="calendário projetado (12 meses)",
                        xaxis_title="",
                        yaxis_title="R$",
                        height=320,
                        showlegend=False,
                        margin=dict(t=40, b=20, l=0, r=0),
                    )
                    st.plotly_chart(_fig_cal, use_container_width=True)
                    st.caption("proventos projetados para os próximos 12 meses com base no histórico de distribuição das posições. ajuda a planejar o fluxo de renda passiva da carteira.")

                    # Top contribuidores
                    st.markdown("##### top contribuidores 12m")
                    _top = sorted(
                        [(t, v) for t, v in _proj.por_ticker.items() if v > 0],
                        key=lambda x: x[1], reverse=True,
                    )[:10]
                    if _top:
                        _linhas_tabela = []
                        for _tk, _val in _top:
                            _det = _proj.detalhes_ticker.get(_tk, {})
                            _linhas_tabela.append({
                                "ticker": _tk,
                                "renda 12m (R$)": f"{_val:,.0f}".replace(",", "."),
                                "freq.": _det.get('freq', 'n/d'),
                                "n pag. 12m": _det.get('n_payments_12m', 0),
                                "growth yoy": f"{_det.get('growth', 0)*100:+.1f}%",
                                "% do total": f"{_val/_proj.renda_total_12m*100:.1f}%",
                            })
                        _mn_dv = 'var(--font-mono,monospace)'
                        _df_dv = pd.DataFrame(_linhas_tabela)
                        _hdrs_dv = "".join(
                            f'<th style="padding:7px 10px;text-align:{"left" if c=="ticker" else "right"};'
                            f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                            f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                            for c in _df_dv.columns
                        )
                        _rows_dv = ""
                        for _, row in _df_dv.iterrows():
                            _cells_dv = ""
                            for col in _df_dv.columns:
                                _v = str(row[col])
                                _align = "left" if col == "ticker" else "right"
                                _cv = "var(--text-primary)"
                                if col == "ticker":
                                    _url_dv = f"/Research?research_ticker={_v}"
                                    _cells_dv += (f'<td style="padding:7px 10px;"><a href="{_url_dv}" target="_blank" '
                                                  f'style="color:var(--accent);font-family:{_mn_dv};font-weight:600;'
                                                  f'font-size:0.8rem;text-decoration:none;" '
                                                  f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'
                                                  f'{_v.replace(".SA","")}</a></td>')
                                    continue
                                if col == "growth yoy":
                                    _cv = "#2ecc71" if _v.startswith('+') else ("#e74c3c" if _v.startswith('-') else "var(--text-muted)")
                                _cells_dv += (f'<td style="padding:7px 10px;text-align:{_align};">'
                                              f'<span style="font-family:{_mn_dv};font-size:0.8rem;color:{_cv};">{_v}</span></td>')
                            _rows_dv += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                                         f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                                         f'onmouseout="this.style.background=\'transparent\'">{_cells_dv}</tr>')
                        st.markdown(
                            f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
                            f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                            f'<thead><tr>{_hdrs_dv}</tr></thead><tbody>{_rows_dv}</tbody></table></div>',
                            unsafe_allow_html=True,
                        )

                    # Sumário em linguagem natural
                    _maior_mes = max(_proj.por_mes.items(), key=lambda x: x[1])
                    st.info(
                        f"💡 projeção total de **R$ {_proj.renda_total_12m:,.0f}** "
                        f"em 12 meses ({_proj.dy_projetado_pct:.2f}% sobre R$ "
                        f"{_proj.valor_carteira:,.0f}). o mês de **{_maior_mes[0]}** "
                        f"concentra o maior pagamento estimado (R$ {_maior_mes[1]:,.0f}). "
                        f"premissas: padrão dos últimos 12m × crescimento yoy "
                        f"(cap ±10% para evitar extrapolação)."
                        .replace(",", ".")
                    )

# ==========================================
# tab 4: stress test
# ==========================================
if _secao_pf == "⚡ stress test":
    section_title("⚡ stress test de portfólio")

    status_card(
        "metodologia",
        "simula o impacto de choques macro no portfólio usando betas históricos de cada ativo contra ibov e s&p500. o impacto é estimado como: variação_ativo = beta × choque_benchmark. os resultados são aproximações baseadas em comportamento histórico.",
        tipo="info"
    )

    ativos_stress = {t: d for t, d in {p['ticker']: p for p in get_pesos(portfolio_id=st.session_state.get('portfolio_id_stress', get_portfolio_padrao()))}.items() if d.get('quantidade', 0) > 0}

    if not ativos_stress:
        empty_state("⚡", "portfólio vazio", "adicione posições na aba posições & p&l para rodar o stress test.")
    else:
        st.markdown("---")
        section_title("⚙️ configurar cenários")

        cenarios_padrao = {
            "🔴 crise financeira severa": {"ibov": -35.0, "sp500": -40.0, "dolar": +35.0, "selic": +3.0},
            "🟠 recessão brasil": {"ibov": -20.0, "sp500": -5.0, "dolar": +20.0, "selic": +2.0},
            "🟡 aperto monetário fed": {"ibov": -10.0, "sp500": -15.0, "dolar": +10.0, "selic": +1.0},
            "🟢 pouso suave (bull case)": {"ibov": +15.0, "sp500": +12.0, "dolar": -8.0, "selic": -1.5},
            "✏️ cenário personalizado": None,
        }

        sc1, sc2 = st.columns([2, 3])
        with sc1:
            cenario_sel = st.selectbox("cenário macro:", list(cenarios_padrao.keys()), key="stress_cenario")

        with sc2:
            if cenarios_padrao[cenario_sel] is not None:
                c = cenarios_padrao[cenario_sel]
                st.markdown(f"""
                <div style="font-family:var(--font-data,monospace); font-size:0.82rem; color:var(--text-muted); padding:8px; background:var(--bg-surface); border-radius:4px; border-left:3px solid var(--accent);">
                IBOV: <span style="color:{'var(--bear)' if c['ibov']<0 else 'var(--bull)'}">{c['ibov']:+.1f}%</span> &nbsp;|&nbsp;
                S&P500: <span style="color:{'var(--bear)' if c['sp500']<0 else 'var(--bull)'}">{c['sp500']:+.1f}%</span> &nbsp;|&nbsp;
                Dólar: <span style="color:{'var(--bear)' if c['dolar']<0 else 'var(--bull)'}">{c['dolar']:+.1f}%</span> &nbsp;|&nbsp;
                Selic: <span style="color:{'var(--bear)' if c['selic']<0 else 'var(--bull)'}">{c['selic']:+.2f}pp</span>
                </div>
                """, unsafe_allow_html=True)
                choque_ibov = c['ibov']
                choque_sp = c['sp500']
            else:
                p1, p2 = st.columns(2)
                with p1:
                    choque_ibov = st.slider("ibov (%):", -60.0, 30.0, -20.0, 5.0, key="stress_ibov")
                    choque_dolar = st.slider("dólar (%):", -20.0, 50.0, 10.0, 5.0, key="stress_dolar")
                with p2:
                    choque_sp = st.slider("s&p500 (%):", -60.0, 30.0, -15.0, 5.0, key="stress_sp")
                    choque_selic = st.slider("selic (pp):", -3.0, 5.0, 1.0, 0.5, key="stress_selic")

        btn_stress = st.button("⚡ rodar stress test", type="primary", use_container_width=True)

        if btn_stress:
            with st.spinner("calculando betas e simulando cenários..."):
                tickers_stress = list(ativos_stress.keys())
                betas_calc = calcular_betas(tuple(tickers_stress))

                linhas_stress = []
                for t, dados in ativos_stress.items():
                    qtd = float(dados.get('quantidade') or 0)
                    pm = float(dados.get('preco_medio') or 0)
                    valor_pos = qtd * pm

                    beta_info = betas_calc.get(t, {'beta_ibov': 1.0, 'beta_sp': 1.0, 'is_br': t.endswith('.SA')})

                    if beta_info['is_br']:
                        impacto_pct = beta_info['beta_ibov'] * choque_ibov
                    else:
                        impacto_pct = beta_info['beta_sp'] * choque_sp

                    impacto_valor = valor_pos * (impacto_pct / 100)
                    valor_estressado = valor_pos + impacto_valor

                    linhas_stress.append({
                        'ticker': t,
                        'valor atual (R$)': round(valor_pos, 2),
                        'beta': beta_info['beta_ibov'] if beta_info['is_br'] else beta_info['beta_sp'],
                        'benchmark': 'ibov' if beta_info['is_br'] else 's&p500',
                        'impacto (%)': round(impacto_pct, 2),
                        'impacto (R$)': round(impacto_valor, 2),
                        'valor estressado (R$)': round(valor_estressado, 2),
                    })

                df_stress = pd.DataFrame(linhas_stress).sort_values('impacto (R$)')
                patrimonio_atual = df_stress['valor atual (R$)'].sum()
                patrimonio_stress = df_stress['valor estressado (R$)'].sum()
                impacto_total = patrimonio_stress - patrimonio_atual
                impacto_total_pct = (impacto_total / patrimonio_atual * 100) if patrimonio_atual > 0 else 0

                st.session_state['stress_resultado'] = df_stress
                st.session_state['stress_resumo'] = {
                    'patrimonio_atual': patrimonio_atual,
                    'patrimonio_stress': patrimonio_stress,
                    'impacto_total': impacto_total,
                    'impacto_total_pct': impacto_total_pct,
                    'cenario': cenario_sel
                }

        if 'stress_resultado' in st.session_state and 'stress_resumo' in st.session_state:
            df_s = st.session_state['stress_resultado']
            resumo = st.session_state['stress_resumo']

            st.markdown("---")
            section_title(f"📊 resultado — {resumo['cenario']}")
            tooltip("beta")

            cor_impacto = "bull" if resumo['impacto_total'] >= 0 else "bear"
            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                metric_card("patrimônio atual", fmt_numero(resumo['patrimonio_atual'], "R$ "))
            with rc2:
                metric_card("patrimônio estressado", fmt_numero(resumo['patrimonio_stress'], "R$ "),
                           fmt_pct(resumo['impacto_total_pct']), cor_impacto)
            with rc3:
                metric_card("impacto total", fmt_numero(resumo['impacto_total'], "R$ "),
                           "perda estimada" if resumo['impacto_total'] < 0 else "ganho estimado", cor_impacto)

            def _stress_table_html(df: pd.DataFrame) -> str:
                _mn = 'var(--font-mono,monospace)'
                _col_map = {
                    'ticker': ('Ticker', 'left'),
                    'valor atual (R$)': ('Valor Atual', 'right'),
                    'beta': ('Beta', 'right'),
                    'impacto (%)': ('Impacto %', 'right'),
                    'impacto (R$)': ('Impacto R$', 'right'),
                    'valor estressado (R$)': ('Valor Stress.', 'right'),
                }
                _cols = [c for c in _col_map if c in df.columns]
                _hdrs = "".join(
                    f'<th style="padding:7px 10px;text-align:{_col_map[c][1]};font-size:0.67rem;'
                    f'color:var(--text-muted);text-transform:uppercase;border-bottom:1px solid var(--border-subtle);white-space:nowrap;">'
                    f'{_col_map[c][0]}</th>'
                    for c in _cols
                )
                _rows = ""
                for _, row in df.iterrows():
                    _cells = ""
                    for col in _cols:
                        _v = row[col]
                        _align = _col_map[col][1]
                        if col == 'ticker':
                            _url = f"/Research?research_ticker={_v}"
                            _cell = (f'<a href="{_url}" target="_blank" style="color:var(--accent);'
                                     f'font-family:{_mn};font-weight:600;font-size:0.8rem;text-decoration:none;" '
                                     f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'
                                     f'{str(_v).replace(".SA","")}</a>')
                        elif col in ('impacto (%)','impacto (R$)'):
                            try:
                                _fv = float(_v)
                                _cv = "#2ecc71" if _fv > 0 else "#e74c3c"
                                _fmt = f'{_fv:+.2f}%' if col == 'impacto (%)' else f'R$ {_fv:+,.2f}'
                                _cell = f'<span style="font-family:{_mn};font-size:0.8rem;color:{_cv};font-weight:600;">{_fmt}</span>'
                            except (TypeError, ValueError):
                                _cell = '<span style="color:var(--text-muted);">—</span>'
                        elif col == 'beta':
                            try:
                                _cell = f'<span style="font-family:{_mn};font-size:0.78rem;">{float(_v):.2f}</span>'
                            except (TypeError, ValueError):
                                _cell = '<span style="color:var(--text-muted);">—</span>'
                        elif col in ('valor atual (R$)','valor estressado (R$)'):
                            try:
                                _cell = f'<span style="font-family:{_mn};font-size:0.8rem;">R$ {float(_v):,.2f}</span>'
                            except (TypeError, ValueError):
                                _cell = '<span style="color:var(--text-muted);">—</span>'
                        else:
                            _cell = f'<span style="font-size:0.8rem;">{_v}</span>'
                        _cells += f'<td style="padding:7px 10px;text-align:{_align};">{_cell}</td>'
                    _rows += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                              f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                              f'onmouseout="this.style.background=\'transparent\'">{_cells}</tr>')
                return (f'<div style="overflow-x:auto;">'
                        f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                        f'<thead><tr>{_hdrs}</tr></thead><tbody>{_rows}</tbody></table></div>')

            st.markdown(_stress_table_html(df_s), unsafe_allow_html=True)

            _cc_stress = _chart_cores()
            fig_stress = go.Figure(go.Bar(
                x=df_s['impacto (R$)'],
                y=df_s['ticker'],
                orientation='h',
                marker_color=[_cc_stress["bear"] if v < 0 else _cc_stress["bull"]
                              for v in df_s['impacto (R$)']],
                hovertemplate='%{y}<br>impacto: R$ %{x:+,.2f}<extra></extra>',
            ))
            fig_stress.add_vline(x=0, line_color=_cc_stress["border"], line_width=1)
            fig_stress.update_layout(**base_layout(height=max(300, len(df_s) * 35 + 80), title="impacto por posição (R$)"))
            st.plotly_chart(fig_stress, use_container_width=True, config={'responsive': True})
            st.caption("impacto estimado de cada cenário de stress histórico sobre o valor da carteira. mostra a vulnerabilidade a choques como crises cambiais, alta de juros ou quedas de bolsa.")

            if st.button("🧠 ia: recomendar proteções para este cenário", type="primary", use_container_width=True):
                with st.spinner("deepseek analisando exposições..."):
                    _prompt_stress = (
                        f"cenário de stress: {resumo['cenario']}\n"
                        f"impacto total estimado: {resumo['impacto_total_pct']:+.1f}% "
                        f"(R$ {resumo['impacto_total']:+,.2f})\n\n"
                        f"posições e impactos:\n{df_s.to_csv(index=False)}\n\n"
                        "responda com 4 bullet points em português, letra minúscula:\n"
                        "1. qual posição representa o maior risco no cenário e por quê.\n"
                        "2. sugestão de hedge ou redução de exposição.\n"
                        "3. quais posições podem se beneficiar neste cenário (naturalmente defensivas).\n"
                        "4. recomendação de realocação para reduzir o impacto total em pelo menos 30%."
                    )
                    chamar_ia(
                        prompt_usuario = _prompt_stress,
                        system         = SYSTEM_PORTFOLIO,
                        max_tokens     = 600,
                        temperatura    = 0.3,
                        stream         = True,
                    )

        # ── Stress setorial (sensibilidades pré-definidas por setor) ────────
        st.markdown("---")
        section_title("🎯 stress setorial (sensibilidades pré-definidas)")
        st.markdown(
            "<div style='font-family:var(--font-ui,sans-serif);font-size:0.78rem;"
            "color:var(--text-muted);margin-bottom:12px;'>"
            "diferente do stress por beta (que aplica choque uniforme via β_IBOV/β_SP), "
            "aqui cada cenário tem <b>impacto setorial específico</b> baseado em literatura macro. "
            "ex.: copom +200bps ajuda banco mas penaliza varejo/construção; usd +10% beneficia "
            "exportadoras (vale, petro, suzano) e prejudica importadoras (varejo).</div>",
            unsafe_allow_html=True,
        )

        from utils.portfolio_stress import (
            calcular_stress_setorial, CENARIOS as _CENARIOS_SETOR,
        )

        cenario_set_sel = st.selectbox(
            "cenário setorial:",
            list(_CENARIOS_SETOR.keys()),
            key="stress_setorial_cenario",
        )

        # Constrói pesos e setores a partir das posições
        from database.db import get_todos_fundamentos_cache as _gt_cache
        _cache_st = _gt_cache()
        _setores_st = {t: d.get("setor") or "" for t, d in _cache_st.items()}

        _pesos_st: dict[str, float] = {}
        _valor_total_st = 0.0
        for _tk, _dados in ativos_stress.items():
            _qtd = float(_dados.get("quantidade") or 0)
            _pm = float(_dados.get("preco_medio") or 0)
            _v = _qtd * _pm
            if _v <= 0:
                continue
            _pesos_st[_tk] = _v
            _valor_total_st += _v
        if _valor_total_st > 0:
            _pesos_st = {t: v / _valor_total_st for t, v in _pesos_st.items()}

        _r_set = calcular_stress_setorial(
            _pesos_st, _setores_st, cenario_set_sel, _valor_total_st,
        )

        if _r_set is None:
            st.info("não foi possível calcular o stress setorial.")
        else:
            _emoji_imp = "🔴" if _r_set.impacto_total_pct < -3 else ("🟠" if _r_set.impacto_total_pct < 0 else "🟢")
            _cs1, _cs2, _cs3 = st.columns(3)
            with _cs1:
                metric_card(
                    "patrimônio atual",
                    fmt_numero(_r_set.valor_carteira, "R$ "),
                )
            with _cs2:
                metric_card(
                    "patrimônio estressado",
                    fmt_numero(_r_set.valor_carteira + _r_set.impacto_total_brl, "R$ "),
                    f"{_r_set.impacto_total_pct:+.2f}%",
                    "bear" if _r_set.impacto_total_pct < 0 else "bull",
                )
            with _cs3:
                metric_card(
                    f"{_emoji_imp} impacto total",
                    fmt_numero(_r_set.impacto_total_brl, "R$ "),
                    cenario_set_sel,
                    "bear" if _r_set.impacto_total_pct < 0 else "bull",
                )

            # Tabela por posição
            st.markdown("##### impacto por posição")
            _df_pos = pd.DataFrame(_r_set.por_posicao)
            if not _df_pos.empty:
                _df_pos_r = _df_pos.rename(columns={
                    "ticker": "ticker", "setor": "setor",
                    "peso_pct": "peso (%)", "impacto_setor_pct": "impacto setor (%)",
                    "contribuicao_pct": "contribuição (pp)", "contribuicao_brl": "contribuição (R$)",
                })
                _mn_pos = 'var(--font-mono,monospace)'
                _hdrs_pos = "".join(
                    f'<th style="padding:7px 10px;text-align:{"left" if c in ("ticker","setor") else "right"};'
                    f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                    f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                    for c in _df_pos_r.columns
                )
                _rows_pos = ""
                for _, row in _df_pos_r.iterrows():
                    _cells_pos = ""
                    for col in _df_pos_r.columns:
                        _v = row[col]
                        _align = "left" if col in ("ticker","setor") else "right"
                        if col == "ticker":
                            _url_p = f"/Research?research_ticker={_v}"
                            _cells_pos += (f'<td style="padding:7px 10px;"><a href="{_url_p}" target="_blank" '
                                           f'style="color:var(--accent);font-family:{_mn_pos};font-weight:600;'
                                           f'font-size:0.8rem;text-decoration:none;" '
                                           f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'
                                           f'{str(_v).replace(".SA","")}</a></td>')
                            continue
                        elif col in ("contribuição (pp)","contribuição (R$)","impacto setor (%)"):
                            try:
                                _fv = float(_v)
                                _cv = "#2ecc71" if _fv > 0 else ("#e74c3c" if _fv < 0 else "var(--text-muted)")
                                if col == "contribuição (pp)": _fmt = f"{_fv:+.2f}pp"
                                elif col == "contribuição (R$)": _fmt = f"R$ {_fv:+,.0f}"
                                else: _fmt = f"{_fv:+.1f}%"
                                _cell = f'<span style="font-family:{_mn_pos};font-size:0.8rem;color:{_cv};font-weight:600;">{_fmt}</span>'
                            except (TypeError, ValueError):
                                _cell = f'<span style="font-size:0.8rem;">{_v}</span>'
                        elif col == "peso (%)":
                            try:
                                _cell = f'<span style="font-family:{_mn_pos};font-size:0.78rem;">{float(_v):.1f}%</span>'
                            except (TypeError, ValueError):
                                _cell = f'<span style="font-size:0.8rem;">{_v}</span>'
                        else:
                            _cell = f'<span style="font-size:0.8rem;">{_v}</span>'
                        _cells_pos += f'<td style="padding:7px 10px;text-align:{_align};">{_cell}</td>'
                    _rows_pos += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                                  f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                                  f'onmouseout="this.style.background=\'transparent\'">{_cells_pos}</tr>')
                st.markdown(
                    f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
                    f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                    f'<thead><tr>{_hdrs_pos}</tr></thead><tbody>{_rows_pos}</tbody></table></div>',
                    unsafe_allow_html=True,
                )

            # Gráfico por setor
            st.markdown("##### impacto por setor (R$)")
            _df_setor = pd.DataFrame(_r_set.por_setor)
            if not _df_setor.empty:
                _df_setor["contribuicao_brl"] = _df_setor["contribuicao_pct"] / 100 * _r_set.valor_carteira
                _df_setor = _df_setor.sort_values("contribuicao_brl")
                _cc_set = _chart_cores()
                fig_st_set = go.Figure(go.Bar(
                    x=_df_setor["contribuicao_brl"],
                    y=_df_setor["setor"],
                    orientation="h",
                    marker_color=[_cc_set["bear"] if v < 0 else _cc_set["bull"]
                                  for v in _df_setor["contribuicao_brl"]],
                    text=[f"R$ {v:+,.0f}".replace(",", ".") for v in _df_setor["contribuicao_brl"]],
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>contribuição: R$ %{x:+,.0f}<extra></extra>",
                ))
                fig_st_set.add_vline(x=0, line_color=_cc_set["border"], line_width=1)
                fig_st_set.update_layout(**base_layout(
                    height=max(280, len(_df_setor) * 36 + 60),
                    title="contribuição por setor",
                ))
                st.plotly_chart(fig_st_set, use_container_width=True, config={'responsive': True})

# ==========================================
# tab 3: backtesting
# ==========================================
if _secao_pf == "📊 backtesting":
    from utils.components import label_com_tooltip
    section_title("🔬 backtesting — estratégia baseada no health score")

    # Bias warnings banner
    st.warning(
        "⚠️ **limitações importantes** — "
        "score proxy (quando sem histórico real) é puramente técnico, "
        "não fundamentalista. "
        "⚠️ **survivorship bias:** analisamos apenas ativos que existem hoje. "
        "⚠️ **look-ahead bias** em períodos > 4 anos. "
        "⚠️ custos de transação não incluem spread bid/ask, slippage ou IR. "
        "⚠️ backtesting intraday com preço de fechamento — "
        "sinais reais podem não ser executados ao preço simulado."
    )

    st.markdown(
        '<div style="font-family:var(--font-ui,sans-serif);font-size:0.75rem;'
        'color:var(--text-muted);margin-bottom:16px;line-height:1.7;">'
        'simula a estratégia de <b>comprar</b> quando o health score '
        'supera o threshold de entrada e <b>vender</b> quando cai '
        'abaixo do threshold de saída. compara com buy & hold e cdi. '
        '</div>',
        unsafe_allow_html=True,
    )

    _bt_c1, _bt_c2, _bt_c3, _bt_c4 = st.columns(4)

    with _bt_c1:
        _bt_ticker = st.selectbox(
            "ativo:",
            options=[
                p['ticker']
                for p in listar_watchlist()
                if p.get('ticker')
            ] or ["WEGE3.SA"],
            key="sel_bt_ticker",
        )

    with _bt_c2:
        _bt_entrada = st.slider(
            "threshold entrada (score ≥):",
            min_value=40, max_value=90,
            value=55,
            step=5,
            key="sl_bt_entrada",
            help=(
                "score mínimo para sinal de compra. "
                "com score proxy (sem histórico real), "
                "use 50-55. com histórico real, use 60-70."
            ),
        )

    with _bt_c3:
        _bt_saida = st.slider(
            "threshold saída (score <):",
            min_value=20, max_value=70,
            value=35,
            step=5,
            key="sl_bt_saida",
            help=(
                "score máximo para sinal de venda. "
                "deve ser menor que o threshold de entrada."
            ),
        )

    with _bt_c4:
        _bt_periodo = st.radio(
            "período:",
            ["1y", "2y", "3y", "5y", "10y", "max"],
            format_func=lambda x: {
                "1y": "1 ano", "2y": "2 anos", "3y": "3 anos",
                "5y": "5 anos", "10y": "10 anos", "max": "máx",
            }[x],
            key="radio_bt_periodo",
        )

    _bt_custo = st.columns(1)[0]
    with _bt_custo:
        _bt_custo_pct = st.slider(
            "custo transação (ida+volta):",
            min_value=0.0, max_value=2.0,
            value=0.3, step=0.05,
            key="sl_bt_custo",
            help=(
                "B3 ≈ 0,3% (corretagem + emolumentos + ISS). "
                "EUA ≈ 0,1% (corretagem low cost). "
                "inclui corretagem, emolumentos, ISS; "
                "não inclui spread bid/ask, slippage nem IR."
            ),
        )

    if _bt_entrada <= _bt_saida:
        st.warning("threshold de entrada deve ser maior que o de saída.")
    else:
        if st.button("▶ rodar backtesting", type="primary", use_container_width=True, key="btn_rodar_bt"):
            st.session_state.pop('bt_resultado', None)
            st.session_state.pop('bt_ticker', None)
            with st.spinner(f"simulando estratégia para {_bt_ticker}..."):
                _bt_result = rodar_backtesting_score(
                    ticker=_bt_ticker,
                    threshold_entrada=_bt_entrada,
                    threshold_saida=_bt_saida,
                    periodo=_bt_periodo,
                    custo_transacao_pct=_bt_custo_pct,
                )
            st.session_state['bt_resultado'] = _bt_result
            st.session_state['bt_ticker']    = _bt_ticker

        _bt_res = st.session_state.get('bt_resultado')

        if _bt_res:
            if _bt_res.get('erro'):
                st.error(f"erro: {_bt_res['erro']}")
            else:
                # Badge indicando fonte dos dados de score
                _fonte = _bt_res.get('fonte_score', 'proxy_tecnico')
                _cc_bt_badge = _chart_cores()
                _fonte_configs = {
                    'banco_local': (
                        _cc_bt_badge["bull"], '✅',
                        'scores reais (banco local)',
                        'calculados pelo motor do app — máxima qualidade'
                    ),
                    'alpha_vantage': (
                        _cc_bt_badge["info"], '📊',
                        'alpha vantage — dre/balanço histórico (supabase)',
                        'fundamentais trimestrais reais desde 2010 via alpha vantage + cache supabase'
                    ),
                    'fmp': (
                        _cc_bt_badge["info"], '📈',
                        'financial modeling prep — múltiplos históricos',
                        'ratios históricos via fmp (somente ativos eua)'
                    ),
                    'proxy_calibrado': (
                        _cc_bt_badge["amber"], '🔧',
                        'proxy técnico calibrado por fundamentos',
                        'indicadores técnicos com nível âncora nos fundamentos atuais'
                    ),
                    'proxy_tecnico': (
                        _cc_bt_badge["bear"], '⚠️',
                        'proxy puramente técnico',
                        'sem dados fundamentalistas — qualidade inferior'
                    ),
                    'sem_dados': (
                        _cc_bt_badge["muted"], '❓',
                        'sem dados disponíveis',
                        'nenhuma fonte retornou dados para este ativo'
                    ),
                }
                # Normaliza prefixos de snapshot
                if isinstance(_fonte, str):
                    if _fonte.startswith(('brapi_snapshot:', 'av_snapshot:')):
                        _fonte = 'proxy_calibrado'

                _f_cor, _f_icon, _f_label, _f_desc = _fonte_configs.get(
                    _fonte, _fonte_configs['proxy_tecnico']
                )

                # Adiciona info de Supabase se fonte é AV
                if _fonte == 'alpha_vantage':
                    try:
                        from utils.api_cache import _get_supabase_client
                        _sb_info = " | cache supabase ativo" if _get_supabase_client() else " | sem supabase"
                    except Exception:
                        _sb_info = ""
                    _f_desc += _sb_info

                st.markdown(
                    f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
                    f'border-left:3px solid {_f_cor};border-radius:4px;'
                    f'padding:8px 14px;margin-bottom:12px;display:flex;'
                    f'gap:12px;align-items:center;">'
                    f'<span style="font-size:1rem;">{_f_icon}</span>'
                    f'<div>'
                    f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.72rem;'
                    f'color:{_f_cor};font-weight:600;">'
                    f'fonte dos dados: {_f_label}</div>'
                    f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.65rem;'
                    f'color:var(--text-muted);">{_f_desc}</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Debug do CDI (temporário — para validação)
                _cdi_dbg = _bt_res.get('cdi_debug', {})
                if _cdi_dbg:
                    st.caption(
                        f"📊 CDI calculado: retorno total {_cdi_dbg['retorno_total']:+.2f}% | "
                        f"CAGR {_cdi_dbg['cagr_anual']:.2f}%/ano | "
                        f"taxa diária média {_cdi_dbg['taxa_media_dia']:.4f}%/dia | "
                        f"período: {_cdi_dbg['n_anos']:.1f} anos ({_cdi_dbg['n_dias']} pregões)"
                    )
                    if not (5 <= _cdi_dbg['cagr_anual'] <= 20):
                        st.warning(
                            f"⚠️ CDI com CAGR {_cdi_dbg['cagr_anual']:.2f}%/ano está "
                            f"fora do range esperado (5-20%/ano). "
                            f"verifique a fonte de dados do CDI."
                        )

                if _bt_res.get('aviso'):
                    st.info(f"⚠️ {_bt_res['aviso']}")

                # Aviso de sanidade
                if _bt_res.get('aviso_sanidade'):
                    st.warning(_bt_res['aviso_sanidade'])

                # Aviso banco_local degenerado
                if _bt_res.get('aviso_banco'):
                    st.warning(f"⚠️ {_bt_res['aviso_banco']}")

                # ── Diagnóstico de APIs externas ────────────────────────
                if _bt_res.get('aviso_av_key'):
                    st.error(f"🔴 {_bt_res['aviso_av_key']}")
                if _bt_res.get('aviso_av_limite'):
                    st.warning(f"⚠️ {_bt_res['aviso_av_limite']}")
                if _bt_res.get('aviso_fmp_403'):
                    st.error(f"🔴 {_bt_res['aviso_fmp_403']}")
                if _bt_res.get('aviso_fmp_key'):
                    st.warning(f"⚠️ {_bt_res['aviso_fmp_key']}")
                if _bt_res.get('aviso_brapi_key'):
                    st.warning(f"⚠️ {_bt_res['aviso_brapi_key']}")

                _pct_inv_ui = _bt_res.get('pct_tempo_investido', 0)
                _n_trades_ui = _bt_res.get('n_trades', 0)

                if _n_trades_ui == 0:
                    st.error(
                        "**nenhuma operação realizada** — o score nunca atingiu "
                        f"o threshold de entrada ({_bt_entrada}) no período. "
                        "**a curva laranja (estratégia) mostra o rendimento do "
                        "caixa (cdi) porque o capital ficou 100% em caixa.** "
                        "use os botões de threshold abaixo para calibrar os "
                        "parâmetros corretos para este ativo."
                    )
                elif _pct_inv_ui >= 95 and _n_trades_ui <= 2:
                    st.info(
                        f"💡 a estratégia ficou {_pct_inv_ui:.0f}% do tempo investida "
                        f"com apenas {_n_trades_ui} operação(ões) — essencialmente "
                        f"equivalente a buy & hold. para uma estratégia mais seletiva, "
                        f"use os botões abaixo para ajustar os thresholds."
                    )

                # ── Distribuição do score + guia de thresholds ──────────────
                _dist_ui = _bt_res.get('score_distribution', {})
                if _dist_ui:
                    _p90 = _dist_ui.get('p90', 75)
                    _p75 = _dist_ui.get('p75', 65)
                    _p50 = _dist_ui.get('mediana', 55)
                    _p25 = _dist_ui.get('p25', 40)
                    _p10 = _dist_ui.get('p10', 30)
                    _fonte_ui = _bt_res.get('fonte_score', 'proxy_tecnico')

                    st.markdown(
                        f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
                        f'border-radius:6px;padding:12px 16px;margin-bottom:12px;">'
                        f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.68rem;'
                        f'color:var(--accent);font-weight:600;margin-bottom:8px;">'
                        f'📊 distribuição do score — {_fonte_ui.replace("_"," ")}</div>'
                        f'<div style="display:grid;grid-template-columns:repeat(5,1fr);'
                        f'gap:8px;margin-bottom:10px;">'
                        + ''.join([
                            f'<div style="text-align:center;">'
                            f'<div style="font-size:0.58rem;color:var(--text-muted);'
                            f'text-transform:uppercase;margin-bottom:2px;">{lbl}</div>'
                            f'<div style="font-family:var(--font-data,monospace);font-size:0.9rem;'
                            f'color:var(--text-secondary);font-weight:600;">{val:.0f}</div>'
                            f'</div>'
                            for lbl, val in [
                                ('p10', _p10), ('p25', _p25),
                                ('mediana', _p50), ('p75', _p75),
                                ('p90', _p90),
                            ]
                        ]) +
                        f'</div>'
                        f'<div style="display:flex;gap:8px;flex-wrap:wrap;">'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    def _ajustar_threshold(val, lo, hi, step=5):
                        clamped = max(lo, min(hi, round(float(val) / step) * step))
                        return int(str(clamped))

                    # Contador para evitar chaves duplicadas entre reruns
                    if '_bt_click_gen' not in st.session_state:
                        st.session_state['_bt_click_gen'] = 0

                    _bt1, _bt2, _bt3 = st.columns(3)
                    with _bt1:
                        if st.button(
                            f"🎯 seletivo: entrada {_p90:.0f} / saída {_p25:.0f}",
                            key=f"btn_th_seletivo_{st.session_state['_bt_click_gen']}",
                            use_container_width=True,
                            help="entra apenas nos melhores 10% momentos",
                        ):
                            st.session_state['_bt_click_gen'] += 1
                            st.session_state['_pending_entrada'] = _ajustar_threshold(_p90, 40, 90)
                            st.session_state['_pending_saida']   = _ajustar_threshold(_p25, 20, 70)
                            st.rerun()
                    with _bt2:
                        if st.button(
                            f"⚖️ moderado: entrada {_p75:.0f} / saída {_p25:.0f}",
                            key=f"btn_th_moderado_{st.session_state['_bt_click_gen']}",
                            use_container_width=True,
                            help="entra nos melhores 25% momentos",
                        ):
                            st.session_state['_bt_click_gen'] += 1
                            st.session_state['_pending_entrada'] = _ajustar_threshold(_p75, 40, 90)
                            st.session_state['_pending_saida']   = _ajustar_threshold(_p25, 20, 70)
                            st.rerun()
                    with _bt3:
                        if st.button(
                            f"📈 ativo: entrada {_p50:.0f} / saída {_p10:.0f}",
                            key=f"btn_th_ativo_{st.session_state['_bt_click_gen']}",
                            use_container_width=True,
                            help="entra na maioria dos momentos positivos",
                        ):
                            st.session_state['_bt_click_gen'] += 1
                            st.session_state['_pending_entrada'] = _ajustar_threshold(_p50, 40, 90)
                            st.session_state['_pending_saida']   = _ajustar_threshold(_p10, 20, 70)
                            st.rerun()
                
                _bt_ticker_label = st.session_state.get('bt_ticker', _bt_ticker).replace('.SA', '')

                # Métricas comparativas
                _bt_met = _bt_res.get('metricas', {})
                if _bt_met:
                    st.markdown("<br>", unsafe_allow_html=True)
                    section_title("📊 métricas comparativas")

                    _bt_rows = []
                    for _nm, _mv in _bt_met.items():
                        _bt_rows.append({
                            'estratégia': _nm,
                            'retorno total': f"{_mv['retorno']:+.2f}%",
                            'cagr': f"{_mv['cagr']:+.2f}%" if _mv.get('cagr') is not None else "n/a",
                            'vol. anual': f"{_mv['vol']:.2f}%",
                            'sharpe': f"{_mv['sharpe']:.2f}" if _mv.get('sharpe') is not None else "n/a",
                            'max drawdown': f"{_mv['drawdown']:.2f}%",
                            'calmar': f"{_mv['calmar']:.2f}" if _mv.get('calmar') is not None else "n/a",
                        })
                    _mn_bt = 'var(--font-mono,monospace)'
                    _df_bt = pd.DataFrame(_bt_rows)
                    _hdrs_bt = "".join(
                        f'<th style="padding:7px 10px;text-align:{"left" if c=="estratégia" else "right"};'
                        f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                        f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                        for c in _df_bt.columns
                    )
                    _rows_bt = ""
                    for idx_bt, (_, row) in enumerate(_df_bt.iterrows()):
                        _cells_bt = ""
                        _is_strat = idx_bt == 0
                        _row_bg = "background:rgba(99,179,237,0.08);" if _is_strat else ""
                        for col in _df_bt.columns:
                            _v = str(row[col])
                            _align = "left" if col == "estratégia" else "right"
                            _cv = "var(--text-primary)"
                            if col in ("retorno total","cagr"):
                                _cv = "#2ecc71" if '+' in _v else ("#e74c3c" if '-' in _v else "var(--text-muted)")
                            _fw = "700" if _is_strat else "400"
                            _cells_bt += (f'<td style="padding:7px 10px;text-align:{_align};">'
                                          f'<span style="font-family:{_mn_bt};font-size:0.8rem;font-weight:{_fw};color:{_cv};">{_v}</span></td>')
                        _rows_bt += (f'<tr style="border-bottom:1px solid var(--border-subtle);{_row_bg}" '
                                     f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                                     f'onmouseout="this.style.background=\'{("rgba(99,179,237,0.08)" if _is_strat else "transparent")}\'">{_cells_bt}</tr>')
                    st.markdown(
                        f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
                        f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                        f'<thead><tr>{_hdrs_bt}</tr></thead><tbody>{_rows_bt}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

                    _ret_est = _bt_met.get('estratégia (score)', {}).get('retorno', 0)
                    _bh_key  = [k for k in _bt_met if 'buy & hold' in k]
                    _ret_bh  = _bt_met[_bh_key[0]].get('retorno', 0) if _bh_key else 0
                    _cdi_key = [k for k in _bt_met if 'cdi' in k]
                    _ret_cdi = _bt_met[_cdi_key[0]].get('retorno', 0) if _cdi_key else 0

                    _alpha_bh  = _ret_est - _ret_bh
                    _alpha_cdi = _ret_est - _ret_cdi

                    _bt_est_met = _bt_met.get('estratégia (score)', {})
                    _bt_cagr     = _bt_est_met.get('cagr', 0)
                    _bt_calmar   = _bt_est_met.get('calmar', 0)
                    _bt_pct_pos  = _bt_est_met.get('pct_pos', 0)
                    _bt_pct_tempo = _bt_res.get('pct_tempo_investido', 0)

                    _am1, _am2, _am3, _am4, _am5, _am6 = st.columns(6)
                    with _am1:
                        metric_card("cagr", f"{_bt_cagr:+.2f}%", f"período {_bt_periodo}", "bull" if _bt_cagr > 0 else "bear", destaque=True)
                    with _am2:
                        metric_card("alpha vs b&h", f"{_alpha_bh:+.2f}pp", "estratégia vs comprar e segurar", "bull" if _alpha_bh > 0 else "bear")
                    with _am3:
                        metric_card("alpha vs cdi", f"{_alpha_cdi:+.2f}pp", "estratégia vs renda fixa", "bull" if _alpha_cdi > 0 else "bear")
                    with _am4:
                        metric_card("nº de operações", str(_bt_res.get('n_trades', 0)), "entradas realizadas no período")
                    with _am5:
                        metric_card("% tempo investido", f"{_bt_pct_tempo:.0f}%", "pregões com posição ativa", "bull" if _bt_pct_tempo > 50 else "amber")
                    with _am6:
                        metric_card("calmar", f"{_bt_calmar:.2f}", "cagr / |max drawdown|", "bull" if _bt_calmar > 0.5 else "amber")

                # Gráfico de performance
                _bt_series = _bt_res.get('series', {})
                if _bt_series:
                    st.markdown("<br>", unsafe_allow_html=True)
                    section_title("📈 curva de capital — base 100")

                    _fig_bt = go.Figure()
                    _cc_bt = _chart_cores()
                    _cores_bt = {
                        'estratégia (score)': _cc_bt["accent"],
                        'cdi':                _cc_bt["info"],
                        'cdi (aprox)':        _cc_bt["info"],
                    }

                    for _nm, _sr in _bt_series.items():
                        if _sr.empty:
                            continue
                        _cor_bt = _cores_bt.get(_nm, _cc_bt["bull"])
                        if 'estratégia' in _nm:
                            _lw   = 2.5
                            _dash = 'solid'
                        elif 'cdi' in _nm.lower():
                            _lw   = 1.5
                            _dash = 'dash'      # traço — mais visível que ponto
                        else:
                            _lw   = 1.8
                            _dash = 'dot'
                        _ret_f  = float(_sr.iloc[-1]) - 100
                        _fig_bt.add_trace(go.Scatter(
                            x=_sr.index, y=_sr.values,
                            name=f"{_nm} ({_ret_f:+.1f}%)",
                            line=dict(color=_cor_bt, width=_lw, dash=_dash),
                            hovertemplate=f'%{{x}}<br>{_nm}: %{{y:.1f}}<extra></extra>',
                        ))

                    # Marca trades no gráfico
                    _trades = _bt_res.get('trades', [])
                    _comp   = [t for t in _trades if t['tipo'] == 'compra']
                    _vend   = [t for t in _trades if t['tipo'] == 'venda']

                    if _comp:
                        _fig_bt.add_trace(go.Scatter(
                            x=[t['data'] for t in _comp],
                            y=[100] * len(_comp),
                            mode='markers',
                            marker=dict(symbol='triangle-up', size=10, color=_cc_bt["bull"]),
                            name='compra',
                            hovertemplate='compra: %{x}<br>score: %{text}<extra></extra>',
                            text=[str(t['score']) for t in _comp],
                        ))

                    if _vend:
                        _fig_bt.add_trace(go.Scatter(
                            x=[t['data'] for t in _vend],
                            y=[100] * len(_vend),
                            mode='markers',
                            marker=dict(symbol='triangle-down', size=10, color=_cc_bt["bear"]),
                            name='venda',
                            hovertemplate='venda: %{x}<br>score: %{text}<br>ret: %{customdata:.1f}%<extra></extra>',
                            text=[str(t['score']) for t in _vend],
                            customdata=[t.get('retorno_trade', 0) for t in _vend],
                        ))

                    _fig_bt.add_hline(y=100, line_color=_chart_cores()["muted"], line_dash='dash', line_width=1)

                    _lay_bt = base_layout(
                        height=420,
                        title=f"backtesting — {_bt_ticker_label} | entrada ≥{_bt_entrada} | saída <{_bt_saida}",
                    )
                    _lay_bt.update(yaxis=dict(title='base 100', showgrid=True, gridcolor=_chart_cores()["border"]))
                    _fig_bt.update_layout(**_lay_bt)
                    st.plotly_chart(_fig_bt, use_container_width=True, config={'responsive': True})
                    st.caption(
                        "▲ triângulo verde = sinal de compra (score atingiu threshold). "
                        "▼ triângulo vermelho = sinal de venda. "
                        "quando fora do mercado o capital fica em caixa (sem rendimento). "
                        "backtesting não garante performance futura."
                    )

                    # ── GRÁFICO DO SCORE AO LONGO DO TEMPO ───────────────────
                    _score_serie_ui = _bt_res.get('serie_score')
                    if _score_serie_ui is not None and not _score_serie_ui.empty:
                        st.markdown("<br>", unsafe_allow_html=True)
                        section_title("📊 evolução do score — com thresholds")

                        _fig_score_bt = go.Figure()

                        # Linha do score
                        _fig_score_bt.add_trace(go.Scatter(
                            x=_score_serie_ui.index,
                            y=_score_serie_ui.values,
                            name='score',
                            line=dict(color='#8B8FA8', width=1.5),
                            fill='tozeroy',
                            fillcolor='rgba(139,143,168,0.12)',
                            hovertemplate='%{x}<br>score: %{y:.0f}<extra></extra>',
                        ))

                        # Linha de threshold de entrada
                        _fig_score_bt.add_hline(
                            y=_bt_entrada,
                            line_color=_cc_bt["bull"],
                            line_dash='dash',
                            line_width=1.5,
                            annotation_text=f'entrada ≥{_bt_entrada}',
                            annotation_font_color=_cc_bt["bull"],
                            annotation_font_size=9,
                            annotation_position='right',
                        )

                        # Linha de threshold de saída
                        _fig_score_bt.add_hline(
                            y=_bt_saida,
                            line_color=_cc_bt["bear"],
                            line_dash='dash',
                            line_width=1.5,
                            annotation_text=f'saída <{_bt_saida}',
                            annotation_font_color=_cc_bt["bear"],
                            annotation_font_size=9,
                            annotation_position='right',
                        )

                        # Região de "zona de compra" (entre saída e entrada)
                        _fig_score_bt.add_hrect(
                            y0=_bt_saida,
                            y1=_bt_entrada,
                            fillcolor='rgba(255,153,0,0.03)',
                            line_width=0,
                            annotation_text='zona neutra',
                            annotation_font_color=_chart_cores()["muted"],
                            annotation_font_size=8,
                        )

                        _lay_sc = base_layout(
                            height=220,
                            title=f'score histórico — {_bt_ticker_label}',
                        )
                        _lay_sc.update(
                            yaxis=dict(
                                title='score',
                                range=[0, 105],
                                showgrid=True,
                                gridcolor=_chart_cores()["border"],
                            ),
                        )
                        _fig_score_bt.update_layout(**_lay_sc)
                        st.plotly_chart(
                            _fig_score_bt,
                            use_container_width=True,
                            config={'responsive': True},
                        )

                        # Estatísticas do score no período
                        _sc_max   = float(_score_serie_ui.max())
                        _sc_min   = float(_score_serie_ui.min())
                        _sc_med   = float(_score_serie_ui.median())
                        _pct_acima = float(
                            (_score_serie_ui >= _bt_entrada).mean() * 100
                        )

                        st.caption(
                            f"score no período — "
                            f"mín: {_sc_min:.0f} | "
                            f"mediana: {_sc_med:.0f} | "
                            f"máx: {_sc_max:.0f} | "
                            f"% do tempo acima do threshold de entrada ({_bt_entrada}): "
                            f"{_pct_acima:.1f}%"
                        )

                        if _pct_acima < 1:
                            st.warning(
                                f"⚠️ o score NUNCA atingiu {_bt_entrada} neste período. "
                                f"o máximo foi {_sc_max:.0f}. "
                                f"use os botões abaixo para ajustar os thresholds "
                                f"baseado na distribuição real do score."
                            )

                    # ── Gráfico de underwater (ocean chart) ──
                    _sr_est = _bt_series.get('estratégia (score)')
                    if _sr_est is not None and not _sr_est.empty:
                        _peak_est  = _sr_est.cummax()
                        _dd_est    = (_sr_est - _peak_est) / _peak_est * 100

                        _fig_ocean = go.Figure()
                        _fig_ocean.add_trace(go.Scatter(
                            x=_dd_est.index, y=_dd_est.values,
                            fill='tozeroy',
                            line=dict(color=_cc_bt["bear"], width=1),
                            name='drawdown',
                            hovertemplate='%{x}<br>drawdown: %{y:.1f}%<extra></extra>',
                        ))
                        _fig_ocean.add_hline(y=0, line_color=_chart_cores()["muted"], line_dash='dash', line_width=1)
                        _lay_ocean = base_layout(
                            height=180,
                            title="⛰️ underwater — drawdown da estratégia",
                        )
                        _lay_ocean.update(
                            yaxis=dict(title='drawdown %', showgrid=True, gridcolor=_chart_cores()["border"]),
                            margin=dict(t=40, b=20),
                        )
                        _fig_ocean.update_layout(**_lay_ocean)
                        st.plotly_chart(_fig_ocean, use_container_width=True, config={'responsive': True})
                        st.caption("curva de drawdown (underwater): quanto a estratégia esteve abaixo do topo anterior ao longo do tempo. quedas profundas e prolongadas indicam maior risco de perda.")

                    # ── Rolling Sharpe 252d (com proteção contra vol zero) ──
                    _series_rolling = {}
                    for _nm_rs, _sr_rs in _bt_series.items():
                        if _sr_rs.empty or 'cdi' in _nm_rs.lower():
                            continue
                        _r_d_rs = _sr_rs.pct_change().dropna()
                        if len(_r_d_rs) < 252:
                            continue

                        _roll_std_rs = _r_d_rs.rolling(252).std()
                        _vol_minima_rs = 0.001 / np.sqrt(252)

                        _roll_mean_rs = _r_d_rs.rolling(252).mean()
                        _selic_d_rs = st.session_state.get('macro_context', {}).get('selic', 10.75) / 100 / 252

                        _roll_sh_rs = pd.Series(np.nan, index=_r_d_rs.index)
                        _mask_valido_rs = _roll_std_rs > _vol_minima_rs
                        _roll_sh_rs[_mask_valido_rs] = (
                            (_roll_mean_rs[_mask_valido_rs] - _selic_d_rs)
                            / _roll_std_rs[_mask_valido_rs]
                            * np.sqrt(252)
                        )
                        _roll_sh_rs = _roll_sh_rs.clip(-5, 5).dropna()

                        if not _roll_sh_rs.empty and _roll_sh_rs.notna().sum() > 20:
                            _series_rolling[_nm_rs] = _roll_sh_rs

                    if not _series_rolling:
                        st.info(
                            "rolling sharpe não disponível: a estratégia não "
                            "realizou operações suficientes no período. "
                            "ajuste os thresholds de entrada/saída "
                            "ou use um período diferente."
                        )
                    else:
                        _fig_roll_sharpe = go.Figure()
                        for _nm_rs, _sr_rs in _series_rolling.items():
                            _fig_roll_sharpe.add_trace(go.Scatter(
                                x=_sr_rs.index, y=_sr_rs.values,
                                line=dict(color='#00B0FF', width=1.5),
                                name='rolling sharpe (252d)',
                                hovertemplate='%{x}<br>sharpe: %{y:.2f}<extra></extra>',
                            ))
                        _fig_roll_sharpe.add_hline(y=0, line_color=_chart_cores()["muted"], line_dash='dash', line_width=1)
                        _fig_roll_sharpe.add_hline(y=1, line_color=_cc_bt["bull"], line_dash='dot', line_width=1)
                        _lay_roll = base_layout(
                            height=180,
                            title="📉 rolling sharpe — janela 252 pregões",
                        )
                        _lay_roll.update(
                            yaxis=dict(title='sharpe', showgrid=True, gridcolor=_chart_cores()["border"]),
                            margin=dict(t=40, b=20),
                        )
                        _fig_roll_sharpe.update_layout(**_lay_roll)
                        st.plotly_chart(_fig_roll_sharpe, use_container_width=True, config={'responsive': True})
                        st.caption(
                            "rolling sharpe = (retorno médio diário - selic) / vol diária × √252. "
                            "linha verde = sharpe 1,0 (referência). "
                            "valores entre -5 e +5 por legibilidade. "
                            "valores > 1 indicam boa relação risco-retorno."
                        )

                # Log de trades
                if _bt_res.get('trades'):
                    st.markdown("<br>", unsafe_allow_html=True)
                    section_title("📋 log de operações")
                    _df_trades = pd.DataFrame(_bt_res['trades'])
                    if 'retorno_trade' in _df_trades.columns:
                        _df_trades['retorno_trade'] = _df_trades['retorno_trade'].apply(
                            lambda x: f"{x:+.2f}%" if pd.notna(x) else "—"
                        )
                    _mn_tr = 'var(--font-mono,monospace)'
                    _hdrs_tr = "".join(
                        f'<th style="padding:7px 10px;text-align:{"right" if c in ("retorno_trade","preco_entrada","preco_saida","retorno_trade") else "left"};'
                        f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                        f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                        for c in _df_trades.columns
                    )
                    _rows_tr = ""
                    for _, row in _df_trades.iterrows():
                        _cells_tr = ""
                        for col in _df_trades.columns:
                            _v = row[col]
                            _align = "right" if col in ("retorno_trade","preco_entrada","preco_saida") else "left"
                            _sv = str(_v) if _v is not None else "—"
                            if col == "retorno_trade":
                                _is_pos = str(_sv).startswith('+')
                                _is_neg = str(_sv).startswith('-')
                                _cv = "#2ecc71" if _is_pos else ("#e74c3c" if _is_neg else "var(--text-muted)")
                                _cell = f'<span style="font-family:{_mn_tr};font-size:0.82rem;font-weight:600;color:{_cv};">{_sv}</span>'
                            else:
                                _cell = f'<span style="font-family:{_mn_tr};font-size:0.78rem;">{_sv}</span>'
                            _cells_tr += f'<td style="padding:7px 10px;text-align:{_align};">{_cell}</td>'
                        _rows_tr += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                                     f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                                     f'onmouseout="this.style.background=\'transparent\'">{_cells_tr}</tr>')
                    st.markdown(
                        f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
                        f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                        f'<thead><tr>{_hdrs_tr}</tr></thead><tbody>{_rows_tr}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

# ==========================================
# tab 3: diário de decisões
# ==========================================
if _secao_pf == "📝 diário de decisões":
    
    with st.expander("➕ registrar nova decisão", expanded=False):
        with st.form("form_decisao", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                opcoes = get_opcoes_selectbox()
                selecao = st.selectbox("ativo:", opcoes, format_func=lambda x: x.lower())
                ticker_manual = st.text_input("ou digite o ticker manualmente:", "").strip().upper()
            with c2:
                tipo_decisao = st.selectbox("tipo de operação:", ['compra', 'venda', 'aumento posição', 'redução'])
                data_dec = st.date_input("data da decisão", datetime.date.today())
            with c3:
                preco_dec = st.number_input("preço na decisão (r$ / $):", min_value=0.0, format="%.2f")
                qtd_dec = st.number_input("quantidade:", min_value=0.0, format="%.4f")
                
            tese_dec = st.text_area("tese de investimento (por que comprou/vendeu? o que esperava?):", height=100)
            btn_salvar = st.form_submit_button("💾 registrar decisão", type="primary")
            
            if btn_salvar:
                ticker_final = ticker_manual if ticker_manual else ticker_from_label(selecao)
                if not ticker_final or not tese_dec or preco_dec <= 0:
                    st.error("preencha o ticker, o preço válido e a tese de investimento.")
                else:
                    registrar_decisao(ticker_final, tipo_decisao, data_dec.isoformat(), preco_dec, qtd_dec, tese_dec)
                    st.success("✅ decisão registrada com sucesso no seu diário de bordo!")
                    st.rerun()

    decisoes = listar_decisoes()
    if not decisoes:
        empty_state("📝", "diário vazio", "o seu diário de decisões está vazio. registre sua primeira operação acima.")
    else:
        st.markdown("---")
        with st.spinner("atualizando preços para auditar resultados..."):
            dados_tabela = []
            acertos = erros = neutros = total_avaliados = 0
            retornos_compra = []
            
            for d in decisoes:
                t = d['ticker']
                t_base = mapear_ticker_base(t)
                try:
                    preco_atual = yf.Ticker(t_base).fast_info.last_price
                except Exception:
                    try:
                        preco_atual = float(yf.Ticker(t_base).history(period="1d")['Close'].iloc[-1])
                    except Exception:
                        preco_atual = 0.0
                    
                retorno_pct = ((preco_atual / d['preco_decisao']) - 1) * 100 if d['preco_decisao'] and preco_atual else 0.0
                if d['tipo'] in ['venda', 'redução']: retorno_pct = -retorno_pct

                data_d = datetime.datetime.strptime(d['data_decisao'], "%Y-%m-%d").date()
                dias_passados = (datetime.date.today() - data_d).days
                
                res = d['resultado']
                if res == 'acerto': acertos += 1; total_avaliados += 1
                elif res == 'erro': erros += 1; total_avaliados += 1
                elif res == 'neutro': neutros += 1; total_avaliados += 1
                    
                if d['tipo'] == 'compra': retornos_compra.append(retorno_pct)
                    
                dados_tabela.append({'id': d['id'], 'ticker': t.lower(), 'tipo': d['tipo'], 'data': d['data_decisao'], 'preço decisão': d['preco_decisao'], 'preço atual': preco_atual, 'retorno %': retorno_pct, 'dias': dias_passados, 'tese': d['tese'][:50] + "..." if len(d['tese']) > 50 else d['tese'], 'resultado': res if res else '⏳ aguardando'})

        df_decisoes = pd.DataFrame(dados_tabela)

        section_title("📊 estatísticas de acerto (track record)")
        c_e1, c_e2, c_e3, c_e4 = st.columns(4)
        taxa_acerto = (acertos / total_avaliados * 100) if total_avaliados > 0 else 0
        retorno_medio_compra = sum(retornos_compra) / len(retornos_compra) if retornos_compra else 0
        melhor_decisao = df_decisoes['retorno %'].max() if not df_decisoes.empty else 0
        pior_decisao = df_decisoes['retorno %'].min() if not df_decisoes.empty else 0

        with c_e1: metric_card("taxa de acerto", f"{taxa_acerto:.1f}%", f"{total_avaliados} julgadas", "info")
        with c_e2: metric_card("retorno médio", fmt_pct(retorno_medio_compra), cor_delta="bull" if retorno_medio_compra >= 0 else "bear")
        with c_e3: metric_card("melhor decisão", fmt_pct(melhor_decisao), cor_delta="bull" if melhor_decisao >= 0 else "bear")
        with c_e4: metric_card("pior decisão", fmt_pct(pior_decisao), cor_delta="bull" if pior_decisao >= 0 else "bear")

        section_title("📜 histórico de operações")
        def _decisoes_table_html(df: pd.DataFrame) -> str:
            _mn = 'var(--font-mono,monospace)'
            _df = df.drop(columns=['id'], errors='ignore')
            _hdrs = "".join(
                f'<th style="padding:7px 10px;text-align:{"right" if c in ("preço decisão","preço atual","retorno %") else "left"};'
                f'font-size:0.67rem;color:var(--text-muted);text-transform:uppercase;'
                f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                for c in _df.columns
            )
            _rows = ""
            for _, row in _df.iterrows():
                _cells = ""
                for col in _df.columns:
                    _v = row[col]
                    _align = "right" if col in ("preço decisão","preço atual","retorno %") else "left"
                    if col == 'ticker':
                        _url = f"/Research?research_ticker={_v}"
                        _cell = (f'<a href="{_url}" target="_blank" style="color:var(--accent);'
                                 f'font-family:{_mn};font-weight:600;font-size:0.8rem;text-decoration:none;" '
                                 f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'
                                 f'{str(_v).replace(".SA","")}</a>')
                    elif col == 'retorno %':
                        try:
                            _fv = float(_v)
                            _cv = "#2ecc71" if _fv > 0 else ("#e74c3c" if _fv < 0 else "var(--text-muted)")
                            _cell = f'<span style="font-family:{_mn};font-size:0.82rem;font-weight:600;color:{_cv};">{_fv:+.2f}%</span>'
                        except (TypeError, ValueError):
                            _cell = f'<span style="font-family:{_mn};font-size:0.8rem;">{_v}</span>'
                    elif col in ('preço decisão','preço atual'):
                        try:
                            _cell = f'<span style="font-family:{_mn};font-size:0.8rem;">{float(_v):.2f}</span>'
                        except (TypeError, ValueError):
                            _cell = f'<span style="font-size:0.8rem;">{_v}</span>'
                    elif col == 'resultado':
                        _cv = "#2ecc71" if str(_v) == 'acerto' else ("#e74c3c" if str(_v) == 'erro' else "var(--text-muted)")
                        _cell = f'<span style="font-size:0.8rem;color:{_cv};font-weight:500;">{_v}</span>'
                    else:
                        _cell = f'<span style="font-size:0.8rem;">{_v}</span>'
                    _cells += f'<td style="padding:7px 10px;text-align:{_align};">{_cell}</td>'
                _rows += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                          f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                          f'onmouseout="this.style.background=\'transparent\'">{_cells}</tr>')
            return (f'<div style="overflow-x:auto;">'
                    f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                    f'<thead><tr>{_hdrs}</tr></thead><tbody>{_rows}</tbody></table></div>')
        st.markdown(_decisoes_table_html(df_decisoes), unsafe_allow_html=True)

        with st.expander("⚖️ julgar uma decisão (atualizar status)"):
            c_u1, c_u2, c_u3 = st.columns([2, 2, 2])
            with c_u1: id_selecionado = st.selectbox("selecione o id da decisão:", df_decisoes['id'].tolist())
            with c_u2: novo_status = st.selectbox("veredicto:", ['acerto', 'erro', 'neutro', '⏳ aguardando'])
            with c_u3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("atualizar resultado", type="primary", use_container_width=True):
                    status_db = None if novo_status == '⏳ aguardando' else novo_status
                    atualizar_resultado(id_selecionado, status_db)
                    st.success("julgamento atualizado!")
                    st.rerun()

        st.markdown("---")
        if st.button("🧠 ia: revisar padrões de decisão", type="primary"):
            with st.spinner("deepseek analisando padrões comportamentais..."):
                try:
                    df_revisao = df_decisoes.head(10).drop(columns=['id'])
                    csv_dados  = df_revisao.to_csv(index=False, float_format='%.2f')
                    _prompt_diario = (
                        f"histórico das últimas decisões de investimento:\n{csv_dados}\n\n"
                        "analise os padrões e responda em 4 tópicos, letra minúscula:\n"
                        "1. padrão de sucesso: o que o investidor costuma fazer de certo nas decisões marcadas como acerto.\n"
                        "2. padrão de erro: o que costuma falhar nas decisões de erro.\n"
                        "3. viés comportamental: identifique o viés mais provável.\n"
                        "4. plano de ação: uma sugestão prática de melhoria."
                    )
                    chamar_ia(
                        prompt_usuario = _prompt_diario,
                        system         = SYSTEM_PORTFOLIO,
                        max_tokens     = 600,
                        temperatura    = 0.3,
                        stream         = True,
                    )
                except Exception as e:
                    st.error(f"falha ao conectar com o mentor de ia: {e}")

# ==========================================
# tab 5: imposto de renda
# ==========================================
if _secao_pf == "🧾 imposto de renda":
    from utils.ir_calculator import calcular_ir_venda, gerar_resumo_mensal

    section_title("🧾 calculadora de imposto de renda")

    st.markdown(
        '<div style="font-family:var(--font-ui,sans-serif); font-size:0.78rem; color:var(--text-muted); '
        'margin-bottom:20px; line-height:1.6;">'
        '📋 <b>regras aplicadas:</b> ações BR (isenção R$ 20k/mês, 15% acima), '
        'FIIs (20% ganho de capital), ações EUA (15%), day trade (20%). '
        'compensação de prejuízos automática dentro da mesma categoria.</div>',
        unsafe_allow_html=True,
    )

    # ── calculadora rápida ────────────────────────────────────────────────────
    section_title("🧮 calculadora rápida de operação")

    with st.form("form_calc_ir"):
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            ticker_ir = st.text_input(
                "ticker:", placeholder="WEGE3", key="ir_ticker"
            ).upper()
            tipo_ir = st.selectbox(
                "tipo de ativo:",
                options=['acao_br', 'fii', 'acao_us'],
                format_func=lambda x: {
                    'acao_br': '🇧🇷 Ação BR',
                    'fii':     '🏢 FII',
                    'acao_us': '🇺🇸 Ação EUA',
                }[x],
                key="ir_tipo",
            )
            day_trade_ir = st.checkbox("day trade?", key="ir_dt")

        with col_b:
            preco_compra_ir = st.number_input(
                "preço médio de compra (R$):",
                min_value=0.01, value=10.0,
                step=0.01, format="%.2f", key="ir_pc",
            )
            qtd_ir = st.number_input(
                "quantidade vendida:",
                min_value=1, value=100,
                step=1, key="ir_qtd",
            )
            custo_ir = st.number_input(
                "custos operacionais (R$):",
                min_value=0.0, value=0.0,
                step=0.01, format="%.2f",
                key="ir_custo",
                help="corretagem + emolumentos B3",
            )

        with col_c:
            preco_venda_ir = st.number_input(
                "preço de venda (R$):",
                min_value=0.01, value=12.0,
                step=0.01, format="%.2f", key="ir_pv",
            )
            outras_vendas_ir = st.number_input(
                "outras vendas no mês (R$):",
                min_value=0.0, value=0.0,
                step=100.0, format="%.2f",
                key="ir_outras",
                help="soma de outras vendas de ações no mês corrente",
            )
            prejuizo_ir = st.number_input(
                "prejuízo acumulado (R$):",
                min_value=0.0, value=0.0,
                step=100.0, format="%.2f",
                key="ir_prej",
                help="saldo negativo de meses anteriores (insira valor positivo)",
            )

        calcular_btn = st.form_submit_button(
            "🧮 calcular IR", type="primary", use_container_width=True,
        )

    if calcular_btn:
        resultado_ir = calcular_ir_venda(
            ticker           = ticker_ir or "TICKER",
            tipo_ativo       = tipo_ir,
            preco_compra     = preco_compra_ir,
            preco_venda      = preco_venda_ir,
            quantidade       = float(qtd_ir),
            custo_operacao   = custo_ir,
            day_trade        = day_trade_ir,
            total_vendas_mes = outras_vendas_ir,
            prejuizo_acum    = -abs(prejuizo_ir),
        )

        st.markdown("---")
        section_title("📊 resultado do cálculo")

        rc1, rc2, rc3, rc4 = st.columns(4)
        lucro  = resultado_ir['lucro_bruto']
        cor_l  = "bull" if lucro >= 0 else "bear"
        ir_dev = resultado_ir['ir_devido']

        with rc1:
            metric_card(
                "lucro/prejuízo bruto",
                f"R$ {lucro:,.2f}",
                f"receita: R$ {resultado_ir['receita_venda']:,.2f}",
                cor_delta=cor_l,
            )
        with rc2:
            if resultado_ir['prejuizo_comp'] > 0:
                metric_card(
                    "prejuízo compensado",
                    f"R$ {resultado_ir['prejuizo_comp']:,.2f}",
                    "deduzido do lucro tributável",
                    cor_delta="info",
                )
            else:
                metric_card(
                    "lucro tributável",
                    f"R$ {resultado_ir['lucro_tributavel']:,.2f}",
                    f"alíquota: {resultado_ir['aliquota'] * 100:.0f}%",
                    cor_delta=cor_l,
                )
        with rc3:
            metric_card(
                "ir a recolher (DARF)",
                f"R$ {ir_dev:,.2f}",
                "até último dia útil do mês seguinte",
                cor_delta="bear" if ir_dev > 0 else "bull",
            )
        with rc4:
            lucro_liq = lucro - ir_dev
            custo_base = preco_compra_ir * float(qtd_ir)
            retorno_pct = (lucro_liq / custo_base * 100) if custo_base > 0 else 0.0
            metric_card(
                "lucro líquido após IR",
                f"R$ {lucro_liq:,.2f}",
                f"retorno: {retorno_pct:+.1f}%",
                cor_delta="bull" if lucro_liq >= 0 else "bear",
            )

        # Regra aplicada + observações
        st.markdown(
            f'<div class="card" style="margin-top:12px; padding:14px; border-left:3px solid var(--info);">'
            f'<div style="font-family:var(--font-ui,sans-serif); font-size:0.7rem; color:var(--text-muted); '
            f'text-transform:uppercase; margin-bottom:6px;">regra aplicada</div>'
            f'<div style="font-family:var(--font-data,monospace); font-size:0.82rem; color:var(--text-primary);">'
            f'{resultado_ir["regra_aplicada"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for obs in resultado_ir['observacoes']:
            st.markdown(
                f'<div style="font-family:var(--font-ui,sans-serif); font-size:0.78rem; color:var(--text-muted); '
                f'padding:5px 0; border-bottom:1px solid var(--border-subtle);">{obs}</div>',
                unsafe_allow_html=True,
            )

        # Alerta DARF
        if resultado_ir['ir_devido'] >= 10.0:
            codigo_darf = "6015" if tipo_ir in ('acao_br', 'acao_us') else "3317"
            status_card(
                "⚡ lembrete: DARF",
                f"você tem R$ {resultado_ir['ir_devido']:,.2f} de IR a recolher. "
                f"emita o DARF pelo site da Receita Federal "
                f"(código {codigo_darf} para {'ações' if tipo_ir != 'fii' else 'FIIs'}) "
                f"até o último dia útil do próximo mês.",
                tipo="amber",
            )
        elif resultado_ir['isento']:
            status_card(
                "✅ operação isenta",
                "suas vendas neste mês estão abaixo do limite de R$ 20.000 — "
                "nenhum DARF precisa ser emitido para esta operação.",
                tipo="bull",
            )

    # ── guia de referência ────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("📚 guia rápido de alíquotas e regras (2024/2025)", expanded=False):
        regras = [
            ("🇧🇷 Ações BR — swing trade",
             "isenção total se vendas no mês ≤ R$ 20.000. "
             "acima desse limite: 15% sobre o lucro líquido. "
             "prejuízo pode ser compensado em meses futuros (mesma categoria)."),
            ("⚡ Ações BR — day trade",
             "20% sobre o lucro, sem isenção de R$ 20k. "
             "obrigatório retenção na fonte de 1% (IRRF) pela corretora."),
            ("🏢 FIIs",
             "20% sobre ganho de capital na venda. sem limite de isenção. "
             "proventos mensais distribuídos pelo fundo são isentos para pessoa física."),
            ("🇺🇸 Ações EUA / BDRs",
             "15% sobre lucro em reais. variação cambial entre a data de compra "
             "e venda também é tributável. sem isenção de R$ 20k."),
            ("📋 Compensação de prejuízos",
             "prejuízos em ações só compensam lucros de ações (não de FIIs). "
             "prejuízos em FIIs só compensam lucros de FIIs. "
             "sem prazo de validade — acumula até ser zerado."),
            ("📅 Prazo de pagamento",
             "DARF deve ser pago até o último dia útil do mês seguinte à operação. "
             "código DARF: 6015 (ações e day trade), 3317 (FIIs e fundos). "
             "valor mínimo de DARF: R$ 10,00 (abaixo disso, acumula para o próximo mês)."),
        ]
        for titulo, descricao in regras:
            st.markdown(
                f'<div style="margin-bottom:12px; padding:10px 14px; '
                f'background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:4px;">'
                f'<div style="font-family:var(--font-ui,sans-serif); font-size:0.78rem; '
                f'color:var(--accent); font-weight:bold; margin-bottom:4px;">{titulo}</div>'
                f'<div style="font-family:var(--font-ui,sans-serif); font-size:0.76rem; '
                f'color:var(--text-muted); line-height:1.5;">{descricao}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ==========================================
# tab 6: chat ia
# ==========================================
if _secao_pf == "💬 chat ia":

    section_title("💬 chat com sua carteira — deepseek v4 pro")

    st.markdown(
        '<div style="font-family:var(--font-ui,sans-serif); font-size:0.72rem; color:var(--text-muted); '
        'margin-bottom:16px; line-height:1.5;">'
        'faça perguntas em linguagem natural sobre sua carteira. '
        'o modelo tem acesso completo às suas posições, health scores e métricas. '
        'não é recomendação de investimento.</div>',
        unsafe_allow_html=True,
    )

    # ── CARREGA DADOS SE NÃO ESTIVEREM NO SESSION_STATE ─────────────────

    # 1. Posições do portfólio
    # Usa o portfolio_id_ativo definido em tab_posicoes
    _portfolio_id_chat = portfolio_id_ativo
    _cache_key_pesos = f"pesos_ativos_cache_{_portfolio_id_chat}"
    pesos_chat = st.session_state.get(_cache_key_pesos, [])
    if not pesos_chat:
        pesos_chat = get_pesos(portfolio_id=_portfolio_id_chat)
        st.session_state[_cache_key_pesos] = pesos_chat

    # 2. Health scores
    health_chat = st.session_state.get("health_chat_cache", {})
    if not health_chat:
        health_chat = {h['ticker']: h for h in get_health_scores()}
        st.session_state["health_chat_cache"] = health_chat

    # 3. Cotações atuais (busca apenas tickers com posição)
    live_chat = st.session_state.get("live_data_cache", {})
    if not live_chat and pesos_chat:
        _tickers_chat = list(set([
            mapear_ticker_base(p['ticker'])
            for p in pesos_chat
            if float(p.get('quantidade') or 0) > 0
        ]))

        if _tickers_chat:
            try:
                with st.spinner("carregando dados da carteira..."):
                    _hist_chat = yf.download(
                        _tickers_chat,
                        period="2d",
                        auto_adjust=True,
                        progress=False,
                        multi_level_index=False,
                    )

                    if isinstance(_hist_chat.columns, pd.MultiIndex):
                        _hist_chat.columns = _hist_chat.columns.get_level_values(0)

                    _close = _hist_chat.get('Close', _hist_chat)

                    for _tc in _tickers_chat:
                        try:
                            if isinstance(_close, pd.DataFrame) and _tc in _close.columns:
                                _serie = _close[_tc].dropna()
                            elif isinstance(_close, pd.Series):
                                _serie = _close.dropna()
                            else:
                                continue

                            _pa = float(_serie.iloc[-1])
                            _pb = float(_serie.iloc[-2]) if len(_serie) >= 2 else _pa
                            _v1d = ((_pa / _pb) - 1) * 100 if _pb > 0 else 0.0
                            live_chat[_tc] = {'preco': _pa, 'var_1d': _v1d}
                        except Exception:
                            live_chat[_tc] = {'preco': 0.0, 'var_1d': 0.0}

                    st.session_state["live_data_cache"] = live_chat
            except Exception as _e:
                logger.warning(f"[chat] falha ao carregar cotações: {_e}")

    # 4. Métricas globais (opcionais — usa vazio se não tiver)
    metricas_chat = st.session_state.get("metricas_cache", {})

    # ── DEFINIÇÃO DA FUNÇÃO DE CONTEXTO ──────────────────────────────────

    def montar_contexto_carteira(
        posicoes: list,
        live_data_ctx: dict,
        health_data_ctx: dict,
        metricas_ctx: dict,
    ) -> str:
        """
        Serializa o estado da carteira em texto estruturado.
        Aceita tanto o formato enriquecido (vindo de pesos_ativos_cache)
        quanto o formato bruto do get_pesos(), enriquecendo on-the-fly com
        live_data_ctx e health_data_ctx.
        Gerado UMA VEZ e armazenado no session_state para cache hit.
        """
        linhas = ["estado atual da carteira do usuário:\n"]

        # Calcula totais para peso relativo
        _total_valor = 0.0
        _enriched = []
        for _p in posicoes:
            _qtd = float(_p.get('quantidade') or 0)
            _pm  = float(_p.get('preco_medio') or _p.get('preço médio') or 0)
            if _qtd <= 0:
                continue

            _tk     = _p.get('ticker', '')
            _tb     = mapear_ticker_base(_tk)
            # preco_atual: enriquecido ou vivo ou zero
            _pa     = float(_p.get('preco_atual') or
                            live_data_ctx.get(_tb, {}).get('preco') or
                            live_data_ctx.get(_tk, {}).get('preco') or 0)
            _valor  = _pa * _qtd if _pa > 0 else _pm * _qtd
            _total_valor += _valor

            _hs_raw = _p.get('health_score') or health_data_ctx.get(_tb, {}).get('score') or 50
            _pnl    = float(_p.get('pnl_pct') or
                            (((_pa / _pm) - 1) * 100 if _pm > 0 and _pa > 0 else 0))

            _enriched.append({
                'ticker':    _tk,
                'qtd':       _qtd,
                'pm':        _pm,
                'pa':        _pa,
                'valor':     _valor,
                'hs':        _hs_raw,
                'pnl':       _pnl,
            })

        if _enriched:
            linhas.append("posições:")
            for _e in _enriched:
                _peso_pct = (_e['valor'] / _total_valor * 100) if _total_valor > 0 else 0
                _hs_str   = f"{_e['hs']}/100" if isinstance(_e['hs'], (int, float)) else str(_e['hs'])
                _moeda    = "r$" if mapear_ticker_base(_e['ticker']).endswith('.SA') else "$"
                linhas.append(
                    f"- {_e['ticker']}: "
                    f"{_e['qtd']:.0f} cotas | "
                    f"preço {_moeda} {_e['pa']:,.2f} | "
                    f"pm {_moeda} {_e['pm']:,.2f} | "
                    f"valor {_moeda} {_e['valor']:,.0f} | "
                    f"peso {_peso_pct:.1f}% | "
                    f"health {_hs_str} | "
                    f"p&l {_e['pnl']:+.1f}%"
                )
        else:
            linhas.append("nenhuma posição encontrada.")

        if metricas_ctx:
            linhas.append(
                f"\nresumo da carteira:\n"
                f"- valor total (m2m): r$ {metricas_ctx.get('valor_total', 0):,.2f}\n"
                f"- custo total investido: r$ {metricas_ctx.get('custo_total', 0):,.2f}\n"
                f"- p&l total: {metricas_ctx.get('pnl_total_pct', 0):+.1f}%\n"
                f"- número de posições: {metricas_ctx.get('num_posicoes', 0)}"
            )
        elif _total_valor > 0:
            # fallback: calcula métricas da lista enriquecida
            _custo_total = sum(_e['pm'] * _e['qtd'] for _e in _enriched)
            _pnl_total   = ((_total_valor / _custo_total) - 1) * 100 if _custo_total > 0 else 0
            linhas.append(
                f"\nresumo da carteira:\n"
                f"- valor total (m2m): r$ {_total_valor:,.2f}\n"
                f"- custo total investido: r$ {_custo_total:,.2f}\n"
                f"- p&l total: {_pnl_total:+.1f}%\n"
                f"- número de posições: {len(_enriched)}"
            )

        macro = st.session_state.get("macro_context", {})
        if macro:
            try:
                from utils.macro_state import selic_real_fisher
                _sel = float(macro.get('selic', 10.75))
                _ip = float(macro.get('ipca_12m') or macro.get('ipca', 4.5))
                _jr = f" | juro real (fisher): {selic_real_fisher(_sel, _ip):+.1f}%"
            except Exception:
                _ip, _jr = float(macro.get('ipca_12m') or macro.get('ipca', 4.5)), ""
            linhas.append(
                f"\nambiente macro atual:\n"
                f"- selic: {macro.get('selic', 10.75):.2f}% | ipca 12m: {_ip:.1f}%{_jr}\n"
                f"- vix: {macro.get('vix', 15.0):.1f}\n"
                f"- ambiente: {macro.get('label', 'neutro')}"
            )

        # exposição macro do book (regime + inflação setorial)
        if _enriched and _total_valor > 0:
            try:
                from utils.portfolio_sizing import exposicao_macro_book
                _cf_chat = get_todos_fundamentos_cache() or {}
                _pesos_b, _setor_b = {}, {}
                for _e in _enriched:
                    _tbb = mapear_ticker_base(_e['ticker'])
                    _pesos_b[_tbb] = _pesos_b.get(_tbb, 0.0) + _e['valor']
                    _setor_b[_tbb] = (_cf_chat.get(_tbb, {}) or _cf_chat.get(_e['ticker'], {}) or {}).get('setor', '')
                _exp_b = exposicao_macro_book(_pesos_b, _setor_b, macro or {})
                if _exp_b:
                    linhas.append(
                        f"\nexposição macro do book (tilt regime+inflação setorial):\n"
                        f"- tilt macro médio: {_exp_b['tilt_medio']:+.1f} (−8 contra … +8 a favor)\n"
                        f"- {_exp_b['leitura']}\n"
                        f"- favorável: {_exp_b['pct_favoravel']:.0f}% | desfavorável: {_exp_b['pct_desfavoravel']:.0f}% | "
                        f"duration: {_exp_b['duration_exposta_pct']:.0f}% | proteção inflação: {_exp_b['inflacao_protegida_pct']:.0f}%"
                    )
            except Exception as _e_eb:
                logger.debug(f"[chat] exposição macro (fallback) falhou: {_e_eb}")

        return "\n".join(linhas)

    # ── MONTA CONTEXTO (com invalidação se dados mudaram) ────────────────

    _ctx_key     = "chat_portfolio_contexto"
    _ctx_version = f"{_portfolio_id_chat}_{len(pesos_chat)}_{len(live_chat)}"

    if st.session_state.get("chat_ctx_version") != _ctx_version:
        st.session_state.pop(_ctx_key, None)
        st.session_state["chat_ctx_version"] = _ctx_version

    if _ctx_key not in st.session_state:
        # Versão rica: concentração setorial, FX, health médio ponderado
        try:
            from utils.ai_prompts import build_portfolio_context_v2
            from database.db import get_todos_fundamentos_cache as _gtc_v2
            _cache_v2 = _gtc_v2() or {}

            _enriched_v2 = []
            _tot_v = 0.0
            _hs_w_sum = 0.0
            for _p in pesos_chat:
                _tk = _p.get('ticker', '')
                _tb = mapear_ticker_base(_tk)
                _qtd = float(_p.get('quantidade') or 0)
                _pm = float(_p.get('preco_medio') or _p.get('preço médio') or 0)
                if _qtd <= 0:
                    continue
                _pa = float(
                    _p.get('preco_atual') or
                    live_chat.get(_tb, {}).get('preco') or
                    live_chat.get(_tk, {}).get('preco') or 0
                )
                _valor = _pa * _qtd if _pa > 0 else _pm * _qtd
                _tot_v += _valor
                _hs = _p.get('health_score') or health_chat.get(_tb, {}).get('score') or 50
                _pnl_pct = ((_pa / _pm - 1) * 100) if _pm > 0 and _pa > 0 else 0
                _fd_p = _cache_v2.get(_tk) or _cache_v2.get(_tb) or {}
                _enriched_v2.append({
                    'ticker':       _tk,
                    'qtd':          _qtd,
                    'preco_medio':  _pm,
                    'preco_atual':  _pa,
                    'valor':        _valor,
                    'health_score': _hs,
                    'pnl_pct':      _pnl_pct,
                    'setor':        _fd_p.get('setor', 'n/d'),
                })

            # Pesos relativos e métricas agregadas
            _setor_conc = {}
            _fx = {"br": 0.0, "us": 0.0}
            for e in _enriched_v2:
                if _tot_v > 0:
                    e['peso_pct'] = e['valor'] / _tot_v * 100
                else:
                    e['peso_pct'] = 0
                _set = e.get('setor') or 'outros'
                _setor_conc[_set] = _setor_conc.get(_set, 0) + e['valor']
                if e['ticker'].endswith('.SA'):
                    _fx['br'] += e['valor']
                else:
                    _fx['us'] += e['valor']
                try:
                    _hs_w_sum += float(e['health_score']) * e['valor']
                except (TypeError, ValueError):
                    pass
            if _tot_v > 0:
                _setor_conc = {k: v / _tot_v * 100 for k, v in _setor_conc.items()}
                _fx = {k: v / _tot_v * 100 for k, v in _fx.items()}
                _hs_medio = _hs_w_sum / _tot_v if _hs_w_sum > 0 else None
            else:
                _hs_medio = None

            # Exposição macro do book (tilt regime + inflação setorial) → IA
            _exp_macro_chat = None
            try:
                from utils.portfolio_sizing import exposicao_macro_book
                _pesos_macro_chat, _setor_macro_chat = {}, {}
                for e in _enriched_v2:
                    _tbm = mapear_ticker_base(e['ticker'])
                    _pesos_macro_chat[_tbm] = _pesos_macro_chat.get(_tbm, 0.0) + e['valor']
                    _setor_macro_chat[_tbm] = e.get('setor', '')
                _exp_macro_chat = exposicao_macro_book(
                    _pesos_macro_chat, _setor_macro_chat,
                    st.session_state.get("macro_context", {}),
                )
            except Exception as _e_exp_ai:
                logger.debug(f"[chat] exposição macro p/ IA falhou: {_e_exp_ai}")

            st.session_state[_ctx_key] = build_portfolio_context_v2(
                posicoes_enriched   = _enriched_v2,
                metricas            = metricas_chat,
                macro               = st.session_state.get("macro_context", {}),
                setor_concentracao  = _setor_conc,
                fx_exposicao        = _fx,
                dy_carteira         = None,
                health_medio        = _hs_medio,
                exposicao_macro     = _exp_macro_chat,
            )
        except Exception:
            st.session_state[_ctx_key] = montar_contexto_carteira(
                pesos_chat, live_chat, health_chat, metricas_chat
            )

    contexto_carteira = st.session_state[_ctx_key]

    # ── sugestões rápidas ─────────────────────────────────────────────────

    section_title("sugestões de perguntas")

    _sugestoes = [
        "qual meu ativo com pior health score?",
        "estou bem diversificado ou concentrado?",
        "meu p&l está bom para o ambiente macro atual?",
        "quais posições devo revisar primeiro?",
        "como o vix atual afeta minha carteira?",
        "qual meu ativo mais correlacionado com o ibov?",
        "qual posição tem maior risco de queda?",
        "devo rebalancear minha carteira agora?",
        "quais ativos estão próximos do stop loss?",
        "minha exposição a juros está adequada?",
    ]

    # Renderiza em grid 2 colunas para não overflow
    _sug_rows = [_sugestoes[i:i+2] for i in range(0, len(_sugestoes), 2)]

    for _row in _sug_rows:
        _scols = st.columns(len(_row))
        for _sci, _sug in enumerate(_row):
            with _scols[_sci]:
                if st.button(
                    _sug,
                    key=f"sug_{_sug[:20]}",
                    use_container_width=True,
                ):
                    st.session_state["chat_input_pendente"] = _sug
                    st.rerun()

    # ── carrega user da sessão ────────────────────────────────────────────

    _user_id_chat = st.session_state.get('user_id', 0)

    # ── inicializa histórico (banco local + session_state) ────────────────

    _hist_key_db = f"chat_hist_loaded_{_portfolio_id_chat}"
    if "chat_portfolio_msgs" not in st.session_state:
        st.session_state["chat_portfolio_msgs"] = []
        # Carrega mensagens do banco local SQLite na primeira inicialização
        _hist_db = get_historico_chat(_user_id_chat, _portfolio_id_chat, limite=30)
        if _hist_db:
            st.session_state["chat_portfolio_msgs"] = [
                {'role': h['role'], 'content': h['conteudo']}
                for h in _hist_db
            ]
        st.session_state[_hist_key_db] = True

    # ── exibe histórico da conversa ───────────────────────────────────────

    st.markdown("---")

    for _msg in st.session_state["chat_portfolio_msgs"]:
        _role   = _msg["role"]
        _avatar = "👤" if _role == "user" else "⚡"
        with st.chat_message(_role, avatar=_avatar):
            st.markdown(
                f'<div style="font-family:var(--font-data,monospace); font-size:0.83rem; '
                f'color:var(--text-primary); line-height:1.6;">{_msg["content"]}</div>',
                unsafe_allow_html=True,
            )

    # ── input do usuário ──────────────────────────────────────────────────

    _input_default = st.session_state.pop("chat_input_pendente", "")

    _pergunta = st.chat_input(
        "pergunte sobre sua carteira...",
        key="chat_portfolio_input",
    ) or _input_default

    if _pergunta:
        # Adiciona ao histórico e exibe imediatamente
        st.session_state["chat_portfolio_msgs"].append(
            {"role": "user", "content": _pergunta}
        )
        salvar_mensagem_chat(_user_id_chat, _portfolio_id_chat, 'user', _pergunta)
        with st.chat_message("user", avatar="👤"):
            st.markdown(
                f'<div style="font-family:var(--font-data,monospace); font-size:0.83rem; '
                f'color:var(--text-primary);">{_pergunta}</div>',
                unsafe_allow_html=True,
            )

        # Monta o prompt: contexto (semi-estático) → histórico → pergunta atual
        # Ordem garante máximo cache hit no prefixo
        _msgs_ant = st.session_state["chat_portfolio_msgs"][:-1]
        _hist_txt = ""
        if _msgs_ant:
            _pares = []
            for _m in _msgs_ant[-6:]:   # últimas 3 trocas (6 mensagens)
                _pfx = "usuário" if _m["role"] == "user" else "analista"
                _pares.append(f"{_pfx}: {_m['content']}")
            _hist_txt = "\nhistórico recente:\n" + "\n".join(_pares) + "\n"

        _prompt_chat = (
            f"{contexto_carteira}"
            f"{_hist_txt}"
            f"\npergunta atual: {_pergunta}"
            f"\n\nresponda de forma direta e objetiva usando os dados da carteira acima. "
            f"letra minúscula."
        )

        _resposta = chamar_ia(
            prompt_usuario = _prompt_chat,
            system         = SYSTEM_PORTFOLIO,
            max_tokens     = 600,
            temperatura    = 0.3,
            stream         = True,
            thinking       = False,
        )

        # Salva resposta no histórico
        st.session_state["chat_portfolio_msgs"].append(
            {"role": "assistant", "content": _resposta}
        )
        salvar_mensagem_chat(_user_id_chat, _portfolio_id_chat, 'assistant', _resposta)

    # ── botão limpar ──────────────────────────────────────────────────────

    if st.session_state.get("chat_portfolio_msgs"):
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ limpar conversa", key="btn_limpar_chat"):
            limpar_historico_chat(_user_id_chat, _portfolio_id_chat)
            st.session_state["chat_portfolio_msgs"] = []
            st.session_state.pop(_ctx_key, None)
            st.session_state.pop(_hist_key_db, None)
            st.rerun()