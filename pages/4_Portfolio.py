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
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from utils.tickers import BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, get_opcoes_selectbox, ticker_from_label, mapear_ticker_base
from database.db import registrar_decisao, listar_decisoes, atualizar_resultado, get_pesos, listar_watchlist, salvar_peso, get_health_scores, listar_watchlists, criar_portfolio, listar_portfolios, get_portfolio_padrao, definir_portfolio_padrao, deletar_portfolio, salvar_peso_alvo, get_pesos_alvo, deletar_peso_alvo, get_todos_fundamentos_cache, salvar_mensagem_chat, get_historico_chat, limpar_historico_chat

# componentes do design system
from utils.components import page_header, section_title, metric_card, status_card, empty_state, inject_keyboard_shortcuts, tooltip, label_com_tooltip
from utils.ai_client import chamar_ia, SYSTEM_PORTFOLIO
from utils.portfolio_importer import importar_planilha, TEMPLATE_CSV
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout
from utils.logger import get_logger

logger = get_logger(__name__)

# 1. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()

page_header("💼 gestão de portfólio", "visão consolidada da sua carteira, backtesting e diário de decisões.")

@st.cache_data(ttl=3600, show_spinner=False)
def calcular_betas(tickers_tuple: tuple) -> dict:
    """Calcula beta de cada ativo contra IBOV e S&P500 usando 1 ano de dados."""
    tickers = list(tickers_tuple)
    betas = {}
    try:
        benchmarks = ["^BVSP", "^GSPC"]
        todos = list(set([mapear_ticker_base(t) for t in tickers] + benchmarks))
        hist = yf.download(todos, period="1y", auto_adjust=True, progress=False)['Close']
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
    except:
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
        hist = yf.download(
            tickers_base,
            period=periodo,
            auto_adjust=True,
            progress=False,
        )['Close']

        if isinstance(hist, pd.Series):
            hist = hist.to_frame(name=tickers_base[0])

        # Remove timezone e normaliza
        if getattr(hist.index, 'tz', None) is not None:
            hist.index = hist.index.tz_localize(None)

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

        _hist = yf.download(
            _todos,
            period=periodo,
            auto_adjust=True,
            progress=False,
        )['Close']

        if isinstance(_hist, pd.Series):
            _hist = _hist.to_frame(name=_todos[0])

        if getattr(_hist.index, 'tz', None) is not None:
            _hist.index = _hist.index.tz_localize(None)

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

@st.cache_data(ttl=86400, show_spinner=False)
def buscar_score_historico_externo(ticker: str) -> tuple[pd.Series | None, str]:
    """
    Busca score historico fundamentalista de fontes externas.
    Ordem de prioridade:
    1. Alpha Vantage (quarterly statements historicos)
    2. FMP (ratios historicos)
    3. BRAPI snapshot x proxy tecnico (apenas para BR)

    Retorna (serie_diaria | None, fonte_label)
    """
    # -- Opcao 1: Alpha Vantage ----------------------------------------
    try:
        from utils.alpha_vantage_client import calcular_score_historico_av
        _av_serie = calcular_score_historico_av(ticker)
        if _av_serie is not None and len(_av_serie) >= 60:
            return _av_serie, 'alpha_vantage'
    except Exception:
        pass

    # -- Opcao 2: FMP (ja existente) -----------------------------------
    try:
        from utils.fmp_client import _get, _safe_float, _safe_pct

        t_clean = ticker.replace('.SA', '').upper()

        _ratios  = _get(f"ratios/{t_clean}", {"limit": 40})
        _income  = _get(f"income-statement/{t_clean}", {"limit": 40, "period": "quarter"})
        _balance = _get(f"balance-sheet-statement/{t_clean}", {"limit": 40, "period": "quarter"})
        _cashflow = _get(f"cash-flow-statement/{t_clean}", {"limit": 40, "period": "quarter"})

        if _ratios and len(_ratios) >= 4:
            _income_map   = {it.get('date', ''): it for it in (_income or [])}
            _balance_map  = {it.get('date', ''): it for it in (_balance or [])}
            _cashflow_map = {it.get('date', ''): it for it in (_cashflow or [])}

            _datas_ratio = sorted([r.get('date', '') for r in _ratios if r.get('date')], reverse=True)

            scores_fmp = {}
            for _data in _datas_ratio:
                try:
                    _r = next((x for x in _ratios if x.get('date') == _data), {})

                    s = 0.0
                    m = 0.0
                    ok = 0

                    pe  = _safe_float(_r.get('priceEarningsRatio'))
                    m += 15
                    if pe and 0 < pe <= 30:
                        ok += 1
                        if pe <= 10: s += 15
                        elif pe <= 18: s += 10
                        elif pe <= 30: s += 5

                    pb = _safe_float(_r.get('priceToBookRatio'))
                    m += 10
                    if pb and pb > 0:
                        ok += 1
                        if pb <= 1.5: s += 10
                        elif pb <= 3: s += 6
                        elif pb <= 6: s += 3

                    roe = _safe_pct(_r.get('returnOnEquity'))
                    m += 20
                    if roe is not None:
                        ok += 1
                        if roe > 20: s += 20
                        elif roe > 10: s += 13
                        elif roe > 0: s += 6
                        else: s -= 5

                    de = _safe_float(_r.get('debtEquityRatio'))
                    m += 10
                    if de is not None:
                        ok += 1
                        if de < 0.3: s += 10
                        elif de < 0.8: s += 6
                        elif de < 1.5: s += 3
                        else: s -= 3

                    fcf = _safe_float(_r.get('freeCashFlowPerShare'))
                    m += 10
                    if fcf is not None:
                        ok += 1
                        if fcf > 0: s += 10
                        elif fcf > -1: s += 3

                    rev_g = _safe_float(_r.get('revenueGrowth'))
                    m += 10
                    if rev_g is not None:
                        ok += 1
                        if rev_g > 0.15: s += 10
                        elif rev_g > 0.05: s += 7
                        elif rev_g > 0: s += 4
                        else: s -= 3

                    if ok >= 2 and m > 0:
                        scores_fmp[_data] = round(
                            max(0, min(100, s / m * 100)), 1
                        )
                except Exception:
                    continue

            if len(scores_fmp) >= 3:
                _serie_fmp = pd.Series(scores_fmp)
                _serie_fmp.index = pd.to_datetime(_serie_fmp.index)
                _serie_fmp = _serie_fmp.sort_index()
                _datas = pd.date_range(
                    _serie_fmp.index[0],
                    pd.Timestamp.today(), freq="B"
                )
                _serie_d = _serie_fmp.reindex(_datas, method="ffill"
                ).rolling(5, min_periods=1).mean()
                return _serie_d.round(1), 'fmp'

    except Exception:
        pass

    # -- Opcao 3: BRAPI snapshot x proxy (apenas BR) -------------------
    if ticker.endswith('.SA'):
        try:
            from utils.brapi_client import get_score_snapshot_brapi
            _snap = get_score_snapshot_brapi(ticker)
            if _snap is not None:
                return None, f'brapi_snapshot:{_snap:.1f}'
        except Exception:
            pass

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
            _delta   = _hist.diff()
            _gain    = _delta.clip(lower=0).rolling(14).mean()
            _loss    = (-_delta.clip(upper=0)).rolling(14).mean()
            _rsi     = (100 - (100 / (1 + _gain / _loss.replace(0, np.nan)))).fillna(50)

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

            # ── Calibração com BRAPI snapshot (apenas BR) ─────────
            # Se BRAPI retornou um snapshot, usa como fator
            # de escala para o proxy: ancora o proxy no
            # nivel fundamentalista atual
            if (
                ticker.endswith('.SA')
                and isinstance(_ext_fonte, str)
                and _ext_fonte.startswith('brapi_snapshot:')
            ):
                try:
                    _snap_val = float(_ext_fonte.split(':')[1])
                    # Proxy medio ao redor de 50 -> ancora em snap_val
                    # Mantem a variacao relativa mas muda o nivel medio
                    _proxy_mean = float(_score_proxy.mean())
                    _delta_ancora = _snap_val - _proxy_mean
                    _score_proxy_cal = (
                        _score_proxy + _delta_ancora
                    ).clip(0, 100)
                    _scores_serie = _score_proxy_cal.rename('score')
                    _fonte_score  = 'proxy_calibrado_brapi'

                    resultado['aviso'] = (
                        f"proxy técnico calibrado com dados fundamentais "
                        f"atuais da brapi (ancora: {_snap_val:.0f}/100). "
                        "o nivel do score reflete os fundamentos atuais, "
                        "mas a variacao historica e tecnica."
                    )
                except Exception:
                    _scores_serie = _score_proxy.rename('score')
            else:
                _scores_serie = _score_proxy.rename('score')
                resultado['aviso'] = (
                    "score proxy puramente tecnico — sem dados "
                    "fundamentalistas disponiveis para este ativo. "
                    "resultados de qualidade inferior."
                )

        resultado['fonte_score'] = _fonte_score

        # ── Diagnóstico de APIs externas ──────────────────────────────
        # Só interessa quando caiu em proxy (fundamentalistas falharam)
        if _fonte_score in ('proxy_tecnico', 'proxy_calibrado_brapi'):
            from utils.alpha_vantage_client import _get_key as _av_key
            if not _av_key():
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
                            f"https://financialmodelingprep.com/api/v3/ratios/PETR4",
                            params={"limit": 1, "apikey": _fk},
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
tab_posicoes, tab_concentracao, tab_stress, tab_backtest, tab_diario, tab_ir, tab_chat = st.tabs([
    "💼 posições & p&l",
    "📊 concentração",
    "⚡ stress test",
    "📊 backtesting",
    "📝 diário de decisões",
    "🧾 imposto de renda",
    "💬 chat ia",
])

# variáveis partilhadas entre tabs — preenchidas em tab_posicoes
live_data: dict      = {}
ativos_alocados: dict = {}

# ==========================================
# tab 1: posições e p&l
# ==========================================
with tab_posicoes:

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
                '<div style="font-family:Courier New; font-size:0.78rem; '
                'color:#555; line-height:1.6;">'
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
                st.dataframe(df_prev, use_container_width=True, hide_index=True)

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
        
        c_txt, c_btn = st.columns([3, 1])
        with c_txt:
            st.markdown(f"<div style='font-family: Courier New; font-size: 0.85rem; color: #888; padding-top: 10px;'>patrimônio estimado: {fmt_preco(patrimonio_estimado, '$')} | {num_posicoes} posições ativas</div>", unsafe_allow_html=True)
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
                except: 
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
            st.info(
                "adicione posições com quantidade e preço médio "
                "para calcular a performance."
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
                st.warning(
                    "não foi possível calcular a performance. "
                    "verifique se os tickers estão corretos."
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
                    st.dataframe(_df_met, use_container_width=True, hide_index=True)

                st.markdown("<br>", unsafe_allow_html=True)

                _series = _perf.get('series', {})
                if _series:
                    _fig_perf = go.Figure()
                    _cores_perf = {
                        'minha carteira': '#FF9900',
                        'ibovespa':       '#00C853',
                        's&p500 (br)':    '#00B0FF',
                        'ifix (fiis)':    '#8B5CF6',
                        'cdi':            '#555555',
                        'cdi (aprox)':    '#444444',
                    }

                    if 'minha carteira' in _series:
                        _s = _series['minha carteira']
                        _ret_f = float(_s.iloc[-1]) - 100 if not _s.empty else 0
                        _fig_perf.add_trace(go.Scatter(
                            x=_s.index, y=_s.values,
                            name=f"minha carteira ({_ret_f:+.1f}%)",
                            line=dict(color='#FF9900', width=3),
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
                        y=100, line_color='#333',
                        line_dash='dash', line_width=1,
                    )

                    _lay_perf = base_layout(
                        height=420,
                        title=f"performance comparada — base 100 ({_periodo_perf})",
                    )
                    _lay_perf.update(
                        yaxis=dict(title='base 100', showgrid=True, gridcolor='#2A2C3E'),
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

                _ac1, _ac2, _ac3 = st.columns(3)
                with _ac1:
                    metric_card(
                        "retorno da carteira",
                        f"{_ret_cart:+.2f}%",
                        f"no período de {_periodo_perf}",
                        "bull" if _ret_cart > 0 else "bear",
                        destaque=True,
                    )
                with _ac2:
                    metric_card(
                        "alpha vs cdi",
                        f"{_alpha_cdi:+.2f}pp",
                        "acima ou abaixo do cdi",
                        "bull" if _alpha_cdi > 0 else "bear",
                    )
                with _ac3:
                    metric_card(
                        "alpha vs ibovespa",
                        f"{_alpha_ibov:+.2f}pp",
                        "acima ou abaixo do ibov",
                        "bull" if _alpha_ibov > 0 else "bear",
                    )

                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(
                    "🧠 ia: analisar performance e sugerir ajustes",
                    key="btn_ia_perf",
                    type="secondary",
                    use_container_width=True,
                ):
                    _met_txt = "\n".join([
                        f"- {nm}: retorno {mv['retorno']:+.2f}% | "
                        f"vol {mv['vol']:.2f}% | "
                        f"sharpe {mv['sharpe']:.2f} | "
                        f"drawdown {mv['drawdown']:.2f}%"
                        for nm, mv in _met.items()
                    ])
                    _macro_perf = st.session_state.get('macro_context', {})
                    _prompt_perf = (
                        f"análise de performance da carteira:\n\n"
                        f"período: {_periodo_perf}\n"
                        f"regime macro: {_macro_perf.get('label','—')}\n\n"
                        f"métricas comparativas:\n{_met_txt}\n\n"
                        f"alpha vs cdi: {_alpha_cdi:+.2f}pp\n"
                        f"alpha vs ibovespa: {_alpha_ibov:+.2f}pp\n\n"
                        "em 4 tópicos diretos (minúsculas):\n"
                        "1. a carteira está gerando alpha real ou "
                        "perdendo para o benchmark passivo?\n"
                        "2. o sharpe da carteira vs benchmarks indica "
                        "risco bem remunerado?\n"
                        "3. o drawdown máximo está adequado para o "
                        "perfil de risco implícito?\n"
                        "4. considerando o regime macro atual, "
                        "que ajuste de alocação poderia melhorar "
                        "o risco/retorno?"
                    )
                    from utils.ai_client import chamar_ia
                    _us_perf = st.session_state.get('user_settings', {})
                    chamar_ia(
                        prompt_usuario=_prompt_perf,
                        system=(
                            "você é um gestor de portfólio quantitativo. "
                            "analise os dados fornecidos. seja direto. "
                            "minúsculas."
                        ),
                        max_tokens=600,
                        temperatura=0.3,
                        stream=True,
                        user_settings=_us_perf,
                    )

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

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1: metric_card("custo total alocado", fmt_preco(custo_total_carteira, "$"), destaque=True)
        with col_m2: metric_card("património atual (m2m)", fmt_preco(valor_atual_carteira, "$"), fmt_pct(pnl_global_pct), "bull" if pnl_global_pct >= 0 else "bear", destaque=True)
        with col_m3: metric_card("p&l global", fmt_preco(pnl_global_valor, "$"), "", "bull" if pnl_global_valor >= 0 else "bear")

        st.markdown("<br>", unsafe_allow_html=True)

        def colorir_pnl(val):
            if pd.isna(val) or val == 0: return ''
            return 'color: #00C853; font-weight: bold;' if val > 0 else 'color: #FF1744; font-weight: bold;'

        st.dataframe(
            df_portfolio.style.map(colorir_pnl, subset=['p&l ($)', 'p&l (%)']).format({
                "qtd": "{:.4f}", "preço médio": "{:.4f}", "preço atual": "{:.2f}",
                "custo total": "{:,.2f}", "valor atual": "{:,.2f}", "p&l ($)": "{:+,.2f}",
                "p&l (%)": "{:+.2f}%", "peso atual (%)": "{:.2f}%"
            }),
            use_container_width=True, hide_index=True
        )
        
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

        with col_g2:
            section_title("📈 p&l por ativo")
            df_pnl = df_portfolio.sort_values(by='p&l ($)', ascending=True)
            fig_bar = go.Figure(go.Bar(x=df_pnl['p&l ($)'], y=df_pnl['ativo'], orientation='h', marker_color=['#FF1744' if val < 0 else '#00C853' for val in df_pnl['p&l ($)']]))
            layout_bar = base_layout(height=350)
            if 'yaxis' in layout_bar:
                layout_bar['yaxis']['showgrid'] = False
            fig_bar.update_layout(**layout_bar)
            st.plotly_chart(fig_bar, use_container_width=True, config={'responsive': True})

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

            cg1, cg2, cg3, cg4 = st.columns(4)
            with cg1:
                metric_card(
                    "patrimônio total (brl)",
                    f"R$ {total_brl_carteira:,.2f}",
                    f"custo: R$ {total_custo_brl:,.2f}",
                    cor_delta="info",
                )
            with cg2:
                cor_total = "bull" if pl_total_brl >= 0 else "bear"
                metric_card(
                    "p&l total em brl",
                    f"R$ {pl_total_brl:+,.2f}",
                    f"{pl_total_pct:+.2f}% sobre custo",
                    cor_delta=cor_total,
                )
            with cg3:
                cor_usd = "bull" if pl_usd >= 0 else "bear"
                metric_card(
                    "p&l ativos eua (usd)",
                    f"$ {pl_usd:+,.2f}",
                    f"{pl_usd_pct:+.2f}% | câmbio R$ {cambio_atual:.2f}",
                    cor_delta=cor_usd,
                )
            with cg4:
                cor_camb = "bull" if contrib_cambio >= 0 else "bear"
                metric_card(
                    "contribuição cambial",
                    f"R$ {contrib_cambio:+,.2f}",
                    "efeito usd/brl no resultado",
                    cor_delta=cor_camb,
                )

            st.markdown("---")
            col_br, col_us = st.columns(2)

            with col_br:
                section_title("🇧🇷 ativos brasileiros (brl)")
                total_br_val  = sum(p['valor_atual'] for p in posicoes_brl)
                total_br_cust = sum(p['valor_custo'] for p in posicoes_brl)
                pl_br         = total_br_val - total_br_cust
                pl_br_pct     = ((total_br_val / total_br_cust) - 1) * 100 if total_br_cust > 0 else 0.0

                st.markdown(
                    f'<div style="font-family:Courier New; font-size:0.85rem; margin-bottom:8px;">'
                    f'<span style="color:#555;">patrimônio: </span>'
                    f'<span style="color:#E0E0E0; font-weight:bold;">R$ {total_br_val:,.2f}</span> | '
                    f'<span style="color:#555;">p&l: </span>'
                    f'<span style="color:{"#00C853" if pl_br >= 0 else "#FF1744"}; font-weight:bold;">'
                    f'R$ {pl_br:+,.2f} ({pl_br_pct:+.1f}%)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for pos in sorted(posicoes_brl, key=lambda x: abs(x['pl_pct']), reverse=True):
                    cor_p = "#00C853" if pos['pl_pct'] >= 0 else "#FF1744"
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; '
                        f'padding:4px 0; border-bottom:1px solid #111; '
                        f'font-family:Courier New; font-size:0.75rem;">'
                        f'<span style="color:#FF9900;">{pos["ticker"].replace(".SA","")}</span>'
                        f'<span style="color:#555;">R$ {pos["preco_atual"]:,.2f}</span>'
                        f'<span style="color:{cor_p};">{pos["pl_pct"]:+.1f}%</span>'
                        f'<span style="color:{cor_p};">R$ {pos["pl_moeda"]:+,.0f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            with col_us:
                section_title("🇺🇸 ativos eua (usd + brl)")

                st.markdown(
                    f'<div style="font-family:Courier New; font-size:0.85rem; margin-bottom:8px;">'
                    f'<span style="color:#555;">em usd: </span>'
                    f'<span style="color:#E0E0E0; font-weight:bold;">$ {total_usd:,.2f}</span> | '
                    f'<span style="color:#555;">em brl: </span>'
                    f'<span style="color:#E0E0E0; font-weight:bold;">R$ {total_usd * cambio_atual:,.2f}</span>'
                    f'<br><span style="color:#555; font-size:0.65rem;">câmbio: R$ {cambio_atual:.4f}/USD</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for pos in sorted(posicoes_usd, key=lambda x: abs(x['pl_pct']), reverse=True):
                    cor_p = "#00C853" if pos['pl_pct'] >= 0 else "#FF1744"
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; '
                        f'padding:4px 0; border-bottom:1px solid #111; '
                        f'font-family:Courier New; font-size:0.75rem;">'
                        f'<span style="color:#FF9900;">{pos["ticker"].replace(".SA","")}</span>'
                        f'<span style="color:#555;">$ {pos["preco_atual"]:,.2f}</span>'
                        f'<span style="color:{cor_p};">{pos["pl_pct"]:+.1f}%</span>'
                        f'<span style="color:{cor_p}; font-size:0.68rem;">R$ {pos["pl_brl"]:+,.0f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # ── rebalanceamento inteligente ───────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚖️ rebalanceamento inteligente", expanded=False):

            st.markdown(
                '<div style="font-family:Courier New; font-size:0.78rem; color:#555; margin-bottom:16px;">'
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
                cor_total = "#00C853" if abs(total_alvo - 100) < 0.1 else "#FF1744"
                aviso_soma = "✅" if abs(total_alvo - 100) < 0.1 else "⚠️ deve somar 100%"
                st.markdown(
                    f'<div style="font-family:Courier New; font-size:0.85rem; '
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
                            cor_op = "#00C853" if d['diferença R$'] > 0 else "#FF1744"
                            op_txt = "COMPRAR" if d['diferença R$'] > 0 else "VENDER"
                            seta   = "▲" if d['diferença R$'] > 0 else "▼"

                            r1, r2, r3, r4, r5 = st.columns([2, 2, 2, 3, 3], gap="small")
                            with r1:
                                st.markdown(
                                    f'<div style="font-family:Courier New; color:#FF9900; font-weight:bold;">{d["ticker"]}</div>'
                                    f'<div style="font-family:Courier New; font-size:0.7rem; color:#555;">{d["peso atual"]} → {d["peso alvo"]}</div>',
                                    unsafe_allow_html=True,
                                )
                            with r2:
                                cor_dev = ("#FF1744" if abs(d['desvio']) > 5
                                           else "#FF9900" if abs(d['desvio']) > 2
                                           else "#00C853")
                                st.markdown(
                                    f'<div style="font-family:Courier New; color:{cor_dev}; font-size:0.85rem;">'
                                    f'desvio: {d["desvio"]:+.1f}pp</div>',
                                    unsafe_allow_html=True,
                                )
                            with r3:
                                st.markdown(
                                    f'<div style="font-family:Courier New; color:#888; font-size:0.8rem;">'
                                    f'R$ {d["valor atual"]:,.0f} → R$ {d["valor alvo"]:,.0f}</div>',
                                    unsafe_allow_html=True,
                                )
                            with r4:
                                st.markdown(
                                    f'<div style="font-family:Courier New; color:{cor_op}; font-size:0.85rem; font-weight:bold;">'
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
                                        f'<div style="font-family:Courier New; color:{cor_op}; font-size:0.8rem;">'
                                        f'{qtd_fmt} @ R$ {d["preço"]:,.2f}</div>',
                                        unsafe_allow_html=True,
                                    )

                            st.markdown(
                                '<div style="height:1px; background:#1e1e1e; margin:4px 0;"></div>',
                                unsafe_allow_html=True,
                            )

                        # Resumo
                        total_compras = sum(d['diferença R$'] for d in dados_rebal if d['diferença R$'] > 0)
                        total_vendas  = abs(sum(d['diferença R$'] for d in dados_rebal if d['diferença R$'] < 0))
                        aporte_liq    = max(0.0, total_compras - total_vendas)

                        st.markdown("---")
                        rc1, rc2, rc3 = st.columns(3)
                        with rc1:
                            metric_card("total a comprar",   f"R$ {total_compras:,.2f}", "", "bull")
                        with rc2:
                            metric_card("total a vender",    f"R$ {total_vendas:,.2f}",  "", "bear")
                        with rc3:
                            metric_card("aporte necessário", f"R$ {aporte_liq:,.2f}",
                                        "além do que já tem em carteira", "amber")

# ==========================================
# tab 2: concentração de risco
# ==========================================
with tab_concentracao:
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

        # ── CARDS DE RESUMO ──────────────────────────────────────────────
        st.markdown("---")
        cc1, cc2, cc3, cc4 = st.columns(4)

        _maior = max(dados_conc, key=lambda x: x['peso'])
        _cor_ma = ("bear" if _maior['peso'] > 25 else
                   "amber" if _maior['peso'] > 15 else "bull")
        with cc1:
            metric_card(
                "maior posição",
                _maior['ticker'],
                f"{_maior['peso']:.1f}% da carteira",
                cor_delta=_cor_ma,
            )
        with cc2:
            metric_card(
                "nº de ativos",
                str(len(dados_conc)),
                "diversificação por ativo",
                cor_delta="info",
            )
        with cc3:
            _pct_brl = paises_peso.get('Brasil', 0.0)
            _pct_usd = paises_peso.get('EUA', 0.0)
            metric_card(
                "exposição brl / usd",
                f"{_pct_brl:.0f}% / {_pct_usd:.0f}%",
                "brasil vs eua",
                cor_delta="info",
            )
        with cc4:
            _hhi      = sum(_dc['peso'] ** 2 for _dc in dados_conc) / 10000
            _diversif = max(0.0, 100.0 - _hhi * 100)
            _cor_hhi  = ("bull" if _diversif > 70 else
                         "amber" if _diversif > 50 else "bear")
            metric_card(
                "índice de diversificação",
                f"{_diversif:.0f}/100",
                "baseado no HHI (100 = máx diversif.)",
                cor_delta=_cor_hhi,
            )

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
                textfont=dict(family='Courier New', size=10, color='#888'),
                marker=dict(
                    colors=_cores_pizza[:len(labels)],
                    line=dict(color='#050505', width=2),
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

        # ── MATRIZ DE CORRELAÇÃO ─────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        label_com_tooltip(
            "🔗 MATRIZ DE CORRELAÇÃO ENTRE ATIVOS",
            chave="correlacao",
            cor="#FF9900",
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

                # Cards de resumo
                _cc1, _cc2, _cc3 = st.columns(3)
                with _cc1:
                    _cor_div = (
                        "#00C853" if _score_div >= 60
                        else "#FF9900" if _score_div >= 35
                        else "#FF1744"
                    )
                    _label_div = (
                        "boa diversificação" if _score_div >= 60
                        else "diversificação moderada" if _score_div >= 35
                        else "alta concentração"
                    )
                    metric_card(
                        "score de diversificação",
                        f"{_score_div}/100",
                        _label_div,
                        "bull" if _score_div >= 60 else ("amber" if _score_div >= 35 else "bear"),
                    )
                    tooltip("correlacao")
                with _cc2:
                    metric_card(
                        "pares de alta correlação",
                        str(sum(1 for a in _alertas_corr if "alta" in a)),
                        "> 0.70 — risco de concentração oculta",
                        "bear" if any("alta" in a for a in _alertas_corr) else "bull",
                    )
                with _cc3:
                    metric_card(
                        "hedges naturais",
                        str(sum(1 for a in _alertas_corr if "hedge" in a)),
                        "correlação < -0.30",
                        "bull" if any("hedge" in a for a in _alertas_corr) else "muted",
                    )

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
                    textfont=dict(size=11, color='white', family='Courier New'),
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
                _lay_corr.update(
                    xaxis=dict(tickfont=dict(size=10, color='#aaa', family='Courier New')),
                    yaxis=dict(tickfont=dict(size=10, color='#aaa', family='Courier New')),
                    margin=dict(l=80, r=40, t=40, b=80),
                    autosize=True,
                )
                _fig_corr.update_layout(**_lay_corr)
                st.plotly_chart(_fig_corr, use_container_width=True, config={'responsive': True})

                # Alertas de correlação
                if _alertas_corr:
                    st.markdown(
                        '<div style="font-family:Courier New; font-size:0.72rem; '
                        'color:#555; margin-top:4px;">⚠️ pares críticos:</div>',
                        unsafe_allow_html=True,
                    )
                    for _ac in _alertas_corr:
                        _cor_ac = "#FF9900" if "alta" in _ac else "#00C853"
                        st.markdown(
                            f'<div style="font-family:Courier New; font-size:0.75rem; '
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
# tab 3: stress test
# ==========================================
with tab_stress:
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
                <div style="font-family:Courier New; font-size:0.82rem; color:#888; padding:8px; background:#0d0d0d; border-radius:4px; border-left:3px solid #FF9900;">
                IBOV: <span style="color:{'#FF1744' if c['ibov']<0 else '#00C853'}">{c['ibov']:+.1f}%</span> &nbsp;|&nbsp;
                S&P500: <span style="color:{'#FF1744' if c['sp500']<0 else '#00C853'}">{c['sp500']:+.1f}%</span> &nbsp;|&nbsp;
                Dólar: <span style="color:{'#FF1744' if c['dolar']<0 else '#00C853'}">{c['dolar']:+.1f}%</span> &nbsp;|&nbsp;
                Selic: <span style="color:{'#FF1744' if c['selic']<0 else '#00C853'}">{c['selic']:+.2f}pp</span>
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

            def colorir_stress(val):
                if isinstance(val, (int, float)):
                    if val > 0: return 'color: #00C853'
                    if val < 0: return 'color: #FF1744'
                return ''

            st.dataframe(
                df_s.style
                    .map(colorir_stress, subset=['impacto (%)', 'impacto (R$)'])
                    .format({
                        'valor atual (R$)': 'R$ {:,.2f}',
                        'beta': '{:.2f}',
                        'impacto (%)': '{:+.2f}%',
                        'impacto (R$)': 'R$ {:+,.2f}',
                        'valor estressado (R$)': 'R$ {:,.2f}'
                    }),
                use_container_width=True,
                hide_index=True
            )

            fig_stress = go.Figure(go.Bar(
                x=df_s['impacto (R$)'],
                y=df_s['ticker'],
                orientation='h',
                marker_color=['#FF1744' if v < 0 else '#00C853' for v in df_s['impacto (R$)']],
                hovertemplate='%{y}<br>impacto: R$ %{x:+,.2f}<extra></extra>'
            ))
            fig_stress.add_vline(x=0, line_color="#333", line_width=1)
            fig_stress.update_layout(**base_layout(height=max(300, len(df_s) * 35 + 80), title="impacto por posição (R$)"))
            st.plotly_chart(fig_stress, use_container_width=True, config={'responsive': True})

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

# ==========================================
# tab 3: backtesting
# ==========================================
with tab_backtest:
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
        '<div style="font-family:Courier New;font-size:0.75rem;'
        'color:#555;margin-bottom:16px;line-height:1.7;">'
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
                _fonte_configs = {
                    'banco_local': (
                        '#00C853', '✅',
                        'scores reais do banco local',
                        'melhor qualidade — dados calculados pelo motor do app'
                    ),
                    'alpha_vantage': (
                        '#00B0FF', '📊',
                        'alpha vantage — dre/balanço histórico trimestral',
                        'dados fundamentalistas reais: receita, lucro, dívida, fcf — trimestrais desde 2010'
                    ),
                    'fmp': (
                        '#00B0FF', '📈',
                        'financial modeling prep — múltiplos históricos',
                        'ratios históricos via fmp: p/l, p/vp, roe, margens'
                    ),
                    'proxy_calibrado_brapi': (
                        '#FF9900', '🔧',
                        'proxy técnico calibrado (brapi)',
                        'indicadores técnicos com nível âncora nos fundamentos atuais via brapi'
                    ),
                    'proxy_tecnico': (
                        '#FF1744', '⚠️',
                        'proxy puramente técnico',
                        'sem dados fundamentalistas disponíveis — menor qualidade'
                    ),
                    'sem_dados': (
                        '#555', '❓',
                        'sem dados externos',
                        'nenhuma fonte disponível'
                    ),
                }
                # Fallback para prefixo 'brapi_snapshot'
                if isinstance(_fonte, str) and _fonte.startswith('brapi_snapshot'):
                    _fonte = 'proxy_calibrado_brapi'

                _f_cor, _f_icon, _f_label, _f_desc = _fonte_configs.get(
                    _fonte, _fonte_configs['proxy_tecnico']
                )

                st.markdown(
                    f'<div style="background:#0d0d0d;border:1px solid #1e1e1e;'
                    f'border-left:3px solid {_f_cor};border-radius:4px;'
                    f'padding:8px 14px;margin-bottom:12px;display:flex;'
                    f'gap:12px;align-items:center;">'
                    f'<span style="font-size:1rem;">{_f_icon}</span>'
                    f'<div>'
                    f'<div style="font-family:Courier New;font-size:0.72rem;'
                    f'color:{_f_cor};font-weight:600;">'
                    f'fonte dos dados: {_f_label}</div>'
                    f'<div style="font-family:Courier New;font-size:0.65rem;'
                    f'color:#555;">{_f_desc}</div>'
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
                        f'<div style="background:#0d0d0d;border:1px solid #1e1e1e;'
                        f'border-radius:6px;padding:12px 16px;margin-bottom:12px;">'
                        f'<div style="font-family:Courier New;font-size:0.68rem;'
                        f'color:#FF9900;font-weight:600;margin-bottom:8px;">'
                        f'📊 distribuição do score — {_fonte_ui.replace("_"," ")}</div>'
                        f'<div style="display:grid;grid-template-columns:repeat(5,1fr);'
                        f'gap:8px;margin-bottom:10px;">'
                        + ''.join([
                            f'<div style="text-align:center;">'
                            f'<div style="font-size:0.58rem;color:#555;'
                            f'text-transform:uppercase;margin-bottom:2px;">{lbl}</div>'
                            f'<div style="font-family:Courier New;font-size:0.9rem;'
                            f'color:#ccc;font-weight:600;">{val:.0f}</div>'
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
                    st.dataframe(pd.DataFrame(_bt_rows), use_container_width=True, hide_index=True)

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
                    _cores_bt = {
                        'estratégia (score)': '#FF9900',   # laranja sólido
                        'cdi':                '#00B0FF',   # azul claro — visível no tema escuro
                        'cdi (aprox)':        '#4488AA',   # azul médio
                    }

                    for _nm, _sr in _bt_series.items():
                        if _sr.empty:
                            continue
                        _cor_bt = _cores_bt.get(_nm, '#00C853')
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
                            marker=dict(symbol='triangle-up', size=10, color='#00C853'),
                            name='compra',
                            hovertemplate='compra: %{x}<br>score: %{text}<extra></extra>',
                            text=[str(t['score']) for t in _comp],
                        ))

                    if _vend:
                        _fig_bt.add_trace(go.Scatter(
                            x=[t['data'] for t in _vend],
                            y=[100] * len(_vend),
                            mode='markers',
                            marker=dict(symbol='triangle-down', size=10, color='#FF1744'),
                            name='venda',
                            hovertemplate='venda: %{x}<br>score: %{text}<br>ret: %{customdata:.1f}%<extra></extra>',
                            text=[str(t['score']) for t in _vend],
                            customdata=[t.get('retorno_trade', 0) for t in _vend],
                        ))

                    _fig_bt.add_hline(y=100, line_color='#333', line_dash='dash', line_width=1)

                    _lay_bt = base_layout(
                        height=420,
                        title=f"backtesting — {_bt_ticker_label} | entrada ≥{_bt_entrada} | saída <{_bt_saida}",
                    )
                    _lay_bt.update(yaxis=dict(title='base 100', showgrid=True, gridcolor='#2A2C3E'))
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
                            line_color='#00C853',
                            line_dash='dash',
                            line_width=1.5,
                            annotation_text=f'entrada ≥{_bt_entrada}',
                            annotation_font_color='#00C853',
                            annotation_font_size=9,
                            annotation_position='right',
                        )

                        # Linha de threshold de saída
                        _fig_score_bt.add_hline(
                            y=_bt_saida,
                            line_color='#FF1744',
                            line_dash='dash',
                            line_width=1.5,
                            annotation_text=f'saída <{_bt_saida}',
                            annotation_font_color='#FF1744',
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
                            annotation_font_color='#333',
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
                                gridcolor='#2A2C3E',
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
                            line=dict(color='#FF1744', width=1),
                            name='drawdown',
                            hovertemplate='%{x}<br>drawdown: %{y:.1f}%<extra></extra>',
                        ))
                        _fig_ocean.add_hline(y=0, line_color='#333', line_dash='dash', line_width=1)
                        _lay_ocean = base_layout(
                            height=180,
                            title="⛰️ underwater — drawdown da estratégia",
                        )
                        _lay_ocean.update(
                            yaxis=dict(title='drawdown %', showgrid=True, gridcolor='#2A2C3E'),
                            margin=dict(t=40, b=20),
                        )
                        _fig_ocean.update_layout(**_lay_ocean)
                        st.plotly_chart(_fig_ocean, use_container_width=True, config={'responsive': True})

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
                        _fig_roll_sharpe.add_hline(y=0, line_color='#333', line_dash='dash', line_width=1)
                        _fig_roll_sharpe.add_hline(y=1, line_color='#00C853', line_dash='dot', line_width=1)
                        _lay_roll = base_layout(
                            height=180,
                            title="📉 rolling sharpe — janela 252 pregões",
                        )
                        _lay_roll.update(
                            yaxis=dict(title='sharpe', showgrid=True, gridcolor='#2A2C3E'),
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
                    st.dataframe(_df_trades, use_container_width=True, hide_index=True)

# ==========================================
# tab 3: diário de decisões
# ==========================================
with tab_diario:
    
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
                except: 
                    try:
                        preco_atual = float(yf.Ticker(t_base).history(period="1d")['Close'].iloc[-1])
                    except:
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
        def formatar_tabela(val):
            if type(val) in [float, int]:
                color = '#00C853' if val > 0 else ('#FF1744' if val < 0 else '#888888')
                return f'color: {color}; font-weight: bold;'
            return ''

        st.dataframe(df_decisoes.drop(columns=['id']).style.map(formatar_tabela, subset=['retorno %']).format({'preço decisão': '{:.2f}', 'preço atual': '{:.2f}', 'retorno %': '{:+.2f}%'}), use_container_width=True, hide_index=True)

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
with tab_ir:
    from utils.ir_calculator import calcular_ir_venda, gerar_resumo_mensal

    section_title("🧾 calculadora de imposto de renda")

    st.markdown(
        '<div style="font-family:Courier New; font-size:0.78rem; color:#555; '
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
            f'<div class="card" style="margin-top:12px; padding:14px; border-left:3px solid #00B0FF;">'
            f'<div style="font-family:Courier New; font-size:0.7rem; color:#555; '
            f'text-transform:uppercase; margin-bottom:6px;">regra aplicada</div>'
            f'<div style="font-family:Courier New; font-size:0.82rem; color:#E0E0E0;">'
            f'{resultado_ir["regra_aplicada"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for obs in resultado_ir['observacoes']:
            st.markdown(
                f'<div style="font-family:Courier New; font-size:0.78rem; color:#888; '
                f'padding:5px 0; border-bottom:1px solid #1e1e1e;">{obs}</div>',
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
                f'background:#0d0d0d; border:1px solid #1e1e1e; border-radius:4px;">'
                f'<div style="font-family:Courier New; font-size:0.78rem; '
                f'color:#FF9900; font-weight:bold; margin-bottom:4px;">{titulo}</div>'
                f'<div style="font-family:Courier New; font-size:0.76rem; '
                f'color:#888; line-height:1.5;">{descricao}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ==========================================
# tab 6: chat ia
# ==========================================
with tab_chat:

    section_title("💬 chat com sua carteira — deepseek v4 pro")

    st.markdown(
        '<div style="font-family:Courier New; font-size:0.72rem; color:#333; '
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
            linhas.append(
                f"\nambiente macro atual:\n"
                f"- selic: {macro.get('selic', 10.75):.2f}%\n"
                f"- vix: {macro.get('vix', 15.0):.1f}\n"
                f"- ambiente: {macro.get('label', 'neutro')}"
            )

        return "\n".join(linhas)

    # ── MONTA CONTEXTO (com invalidação se dados mudaram) ────────────────

    _ctx_key     = "chat_portfolio_contexto"
    _ctx_version = f"{_portfolio_id_chat}_{len(pesos_chat)}_{len(live_chat)}"

    if st.session_state.get("chat_ctx_version") != _ctx_version:
        st.session_state.pop(_ctx_key, None)
        st.session_state["chat_ctx_version"] = _ctx_version

    if _ctx_key not in st.session_state:
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
                f'<div style="font-family:Courier New; font-size:0.83rem; '
                f'color:#C0C0C0; line-height:1.6;">{_msg["content"]}</div>',
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
                f'<div style="font-family:Courier New; font-size:0.83rem; '
                f'color:#E0E0E0;">{_pergunta}</div>',
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