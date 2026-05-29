import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from bcb import sgs
from fredapi import Fred
import yfinance as yf
import datetime

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label, mapear_ticker_base
from utils.logger import get_logger

logger = get_logger(__name__)

# componentes do design system (camada 2 e 4)
from utils.components import page_header, section_title, metric_card, status_card, empty_state, inject_keyboard_shortcuts, auto_refresh_indicator
from utils.ai_client import chamar_ia, SYSTEM_MACRO
from utils.fmp_client import get_earnings_calendar as _fmp_earnings_calendar
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout
from utils.macro_context import garantir_macro_context
from utils.macro_regime import classificar_regime, get_impacto_setor

# 1. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()
garantir_macro_context()

page_header("🌍 ambiente macroeconómico", "monitoramento de juros, inflação, atividade e apetite ao risco global.")

if "FRED_API_KEY" not in st.secrets:
    st.warning("⚠️ **aviso de arquitetura:** a chave da api do fred não foi encontrada no arquivo `secrets.toml`.\n\nsem ela, os dados dos eua e risco global ficarão indisponíveis.")

# ==========================================
# funções globais de cache e apoio
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def puxar_historico_mestre():
    hoje = datetime.datetime.today()
    inicio_10a = hoje - datetime.timedelta(days=365 * 10) 
    
    # 1. brasil (sgs)
    series_bcb = {
        'Selic':            432,
        'IPCA':             433,
        'Dolar':            1,
        'Desemprego':       24369,
        # séries fiscais
        'Divida_Bruta_PIB': 13762,   # Dívida Bruta do Governo Geral % PIB
        'Result_Primario':  5793,    # Resultado primário do setor público (% PIB)
        'Result_Nominal':   4192,    # Resultado nominal do setor público
    }
    dfs_br_dict = {}
    for nome, codigo in series_bcb.items():
        try:
            df_temp = sgs.get({nome: codigo}, start=inicio_10a)
            if not df_temp.empty: dfs_br_dict[nome] = df_temp[nome]
        except Exception: pass
    # Fallback Selic: se série 432 falhou, tenta série 11 (Selic efetiva diária)
    if 'Selic' not in dfs_br_dict:
        try:
            _selic_fb = sgs.get({'Selic': 11}, start=inicio_10a)
            if not _selic_fb.empty:
                dfs_br_dict['Selic'] = _selic_fb['Selic']
        except Exception: pass
            
    df_br = pd.DataFrame(dfs_br_dict) if dfs_br_dict else pd.DataFrame()
    
    # 2. global (fred)
    df_global = pd.DataFrame()
    if "FRED_API_KEY" in st.secrets:
        try:
            fred = Fred(api_key=st.secrets["FRED_API_KEY"])
            series_fred = {
                'FEDFUNDS': 'FEDFUNDS', 'CPIAUCSL': 'CPIAUCSL', 'UNRATE': 'UNRATE',
                'DGS10': 'DGS10', 'DGS2': 'DGS2', 'VIXCLS': 'VIXCLS',
                'ECBDFR': 'ECBDFR', 'IRLTLT01EZM156N': 'IRLTLT01EZM156N', 'IRLTLT01JPM156N': 'IRLTLT01JPM156N',
                'T10Y2Y': 'T10Y2Y', 'BAMLH0A0HYM2': 'BAMLH0A0HYM2',
                'GFDEGDQ188S': 'GFDEGDQ188S', 'MTSDS133FMS': 'MTSDS133FMS',
            }
            dfs_global_dict = {}
            for nome, serie_id in series_fred.items():
                try: dfs_global_dict[nome] = fred.get_series(serie_id, observation_start=inicio_10a)
                except Exception: pass
            df_global = pd.DataFrame(dfs_global_dict)
            if 'CPIAUCSL' in df_global.columns:
                df_global['CPI_MoM'] = df_global['CPIAUCSL'].pct_change() * 100
                df_global['CPI_YOY'] = df_global['CPIAUCSL'].pct_change(12) * 100
        except Exception: pass 
    
    # 3. commodities
    df_commodities = pd.DataFrame()
    try:
        df_commodities = yf.download(['CL=F', 'GC=F'], start=inicio_10a, progress=False)['Close']
        if isinstance(df_commodities, pd.Series): df_commodities = df_commodities.to_frame()
    except Exception: pass 
        
    return df_br, df_global, df_commodities

def valor_atual_seguro(df, coluna):
    if not df.empty and coluna in df.columns and not df[coluna].dropna().empty:
        return df[coluna].dropna().iloc[-1]
    return None

def criar_grafico_macro(df, coluna_y, titulo, cor_linha):
    layout = base_layout(height=280, title=titulo)
    if df.empty or coluna_y not in df.columns or df[coluna_y].dropna().empty:
        fig = px.line()
        fig.add_annotation(text=f"sem dados: {titulo}", x=0.5, y=0.5, showarrow=False, font=dict(color="#FF1744", size=14))
        layout['xaxis'] = dict(visible=False)
        layout['yaxis'] = dict(visible=False)
        fig.update_layout(**layout)
        return fig
    df_plot = df.dropna(subset=[coluna_y])
    fig = px.line(df_plot, x=df_plot.index, y=coluna_y)
    fig.update_layout(**layout)
    fig.update_traces(line_color=cor_linha, line_width=1.5)
    return fig

def tooltip_info(texto):
    """HTML snippet for a hover-info icon. Use with st.markdown(..., unsafe_allow_html=True)."""
    _texto_escaped = texto.replace('"', '&quot;')
    return f"""<span style="cursor:help; border-bottom:1px dashed #666; font-size:0.85em; color:#aaa;" title="{_texto_escaped}">&#9432;</span>"""

def calcular_semaforo_fiscal(df_br: pd.DataFrame) -> dict:
    """
    Avalia o risco fiscal brasileiro com base em dívida/PIB, tendência
    e resultado primário. Retorna dict com status, cor e label.
    """
    resultado = {
        'divida_pib':       None,
        'result_primario':  None,
        'tendencia_divida': None,
        'status':           'neutro',
        'cor':              'amber',
        'label':            'INDEFINIDO',
    }

    try:
        # --- Dívida/PIB atual e tendência (últimos 6 meses) ---
        if 'Divida_Bruta_PIB' in df_br.columns:
            serie_divida = df_br['Divida_Bruta_PIB'].dropna()
            if len(serie_divida) >= 6:
                divida_atual    = float(serie_divida.iloc[-1])
                divida_6m_atras = float(serie_divida.iloc[-6])
                tendencia       = divida_atual - divida_6m_atras
                resultado['divida_pib']       = divida_atual
                resultado['tendencia_divida'] = tendencia

        # --- Resultado primário atual ---
        if 'Result_Primario' in df_br.columns:
            serie_result = df_br['Result_Primario'].dropna()
            if not serie_result.empty:
                resultado['result_primario'] = float(serie_result.iloc[-1])

        # --- Pontuação de risco ---
        divida   = resultado['divida_pib']
        tendencia = resultado['tendencia_divida']
        primario = resultado['result_primario']

        pontos_risco = 0

        if divida is not None:
            if divida > 90:   pontos_risco += 3
            elif divida > 80: pontos_risco += 2
            elif divida > 70: pontos_risco += 1

        if tendencia is not None:
            if tendencia > 3:   pontos_risco += 2   # subindo rápido
            elif tendencia > 1: pontos_risco += 1

        if primario is not None:
            if primario < -3:   pontos_risco += 2   # déficit primário alto
            elif primario < -1: pontos_risco += 1

        # --- Classificação ---
        if pontos_risco >= 5:
            resultado.update({'status': 'critico', 'cor': 'bear',  'label': 'FISCAL CRÍTICO'})
        elif pontos_risco >= 3:
            resultado.update({'status': 'alerta',  'cor': 'amber', 'label': 'ATENÇÃO FISCAL'})
        else:
            resultado.update({'status': 'saudavel', 'cor': 'bull', 'label': 'FISCAL ESTÁVEL'})

    except Exception as e:
        logger.warning(f"[macro] erro semáforo fiscal: {e}")

    return resultado


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_fear_greed() -> dict:
    """
    Calcula Fear & Greed Index proprietário com 7 componentes.
    Retorna dict com score 0-100, label, cor, tipo e breakdown.
    """
    componentes: dict = {}
    scores: list[int] = []

    try:
        fim    = datetime.datetime.today()
        inicio = fim - datetime.timedelta(days=365)

        dados = yf.download(
            ['^GSPC', '^VIX', '^IXIC', 'GC=F', 'BTC-USD'],
            start=inicio, end=fim,
            auto_adjust=True, progress=False,
        )['Close']

        sp500 = dados['^GSPC'].dropna()
        vix   = dados['^VIX'].dropna()

        # ── 1. MOMENTUM DO S&P500 (125 dias vs MM125) ──────────────────────
        if len(sp500) >= 125:
            mm125      = sp500.rolling(125).mean()
            desvio_pct = ((sp500.iloc[-1] - mm125.iloc[-1]) / mm125.iloc[-1] * 100)
            score_mom  = min(max(int(50 + desvio_pct * 2), 0), 100)
            componentes['momentum_sp500'] = {
                'score': score_mom,
                'label': 'Momentum S&P500',
                'valor': f"{desvio_pct:+.1f}% vs MM125",
            }
            scores.append(score_mom)

        # ── 2. FORÇA DO VIX (invertido — VIX alto = medo) ──────────────────
        if len(vix) >= 252:
            vix_atual   = float(vix.iloc[-1])
            vix_52w_max = float(vix.rolling(252).max().iloc[-1])
            vix_52w_min = float(vix.rolling(252).min().iloc[-1])
            amplitude   = vix_52w_max - vix_52w_min
            if amplitude > 0:
                pos_vix   = (vix_atual - vix_52w_min) / amplitude
                score_vix = min(max(int((1 - pos_vix) * 100), 0), 100)
            else:
                score_vix = 50
            componentes['vix'] = {
                'score': score_vix,
                'label': 'Força VIX (invertido)',
                'valor': f"VIX: {vix_atual:.1f}",
            }
            scores.append(score_vix)

        # ── 3. AMPLITUDE DE MERCADO (High-Low 52 semanas) ──────────────────
        if len(sp500) >= 252:
            max_52w   = sp500.rolling(252).max()
            min_52w   = sp500.rolling(252).min()
            range_52w = max_52w.iloc[-1] - min_52w.iloc[-1]
            if range_52w > 0:
                pos_atual = (sp500.iloc[-1] - min_52w.iloc[-1]) / range_52w * 100
                score_amp = int(pos_atual)
            else:
                score_amp = 50
            componentes['amplitude'] = {
                'score': score_amp,
                'label': 'Posição no Range 52 semanas',
                'valor': f"{score_amp:.0f}% do range",
            }
            scores.append(score_amp)

        # ── 4. MOMENTUM NASDAQ vs S&P500 ────────────────────────────────────
        nasdaq = dados['^IXIC'].dropna()
        if len(nasdaq) >= 20 and len(sp500) >= 20:
            ret_nq_20d  = ((nasdaq.iloc[-1] / nasdaq.iloc[-20]) - 1) * 100
            ret_sp_20d  = ((sp500.iloc[-1]  / sp500.iloc[-20])  - 1) * 100
            diferencial = ret_nq_20d - ret_sp_20d
            score_nq    = min(max(int(50 + diferencial * 3), 0), 100)
            componentes['nasdaq_vs_sp'] = {
                'score': score_nq,
                'label': 'Nasdaq vs S&P500 (20d)',
                'valor': f"diferencial: {diferencial:+.1f}pp",
            }
            scores.append(score_nq)

        # ── 5. OURO como SAFE HAVEN ─────────────────────────────────────────
        ouro = dados['GC=F'].dropna()
        if len(ouro) >= 20 and len(sp500) >= 20:
            ret_ouro_20d = ((ouro.iloc[-1]  / ouro.iloc[-20])  - 1) * 100
            ret_sp_20d   = ((sp500.iloc[-1] / sp500.iloc[-20]) - 1) * 100
            fuga_ouro    = ret_ouro_20d - ret_sp_20d
            score_ouro   = min(max(int(50 - fuga_ouro * 2), 0), 100)
            componentes['safe_haven'] = {
                'score': score_ouro,
                'label': 'Ouro vs Ações (safe haven)',
                'valor': f"ouro {ret_ouro_20d:+.1f}% vs ações {ret_sp_20d:+.1f}%",
            }
            scores.append(score_ouro)

        # ── 6. VOLATILIDADE REALIZADA vs IMPLÍCITA ──────────────────────────
        if len(sp500) >= 30 and len(vix) >= 5:
            rets_sp  = sp500.pct_change().dropna()
            vol_real = float(rets_sp.iloc[-20:].std() * (252 ** 0.5) * 100)
            vix_agora = float(vix.iloc[-1])
            ratio     = vix_agora / vol_real if vol_real > 0 else 1.0
            score_vol = min(max(int(100 - (ratio - 1) * 50), 0), 100)
            componentes['vol_ratio'] = {
                'score': score_vol,
                'label': 'VIX vs Volatilidade Realizada',
                'valor': f"ratio: {ratio:.2f}x",
            }
            scores.append(score_vol)

        # ── 7. BITCOIN como APETITE A RISCO ────────────────────────────────
        btc = dados['BTC-USD'].dropna()
        if len(btc) >= 30:
            ret_btc_30d = ((btc.iloc[-1] / btc.iloc[-30]) - 1) * 100
            score_btc   = min(max(int(50 + ret_btc_30d * 0.8), 0), 100)
            componentes['bitcoin'] = {
                'score': score_btc,
                'label': 'Bitcoin (apetite a risco)',
                'valor': f"{ret_btc_30d:+.1f}% em 30d",
            }
            scores.append(score_btc)

    except Exception as e:
        logger.warning(f"[macro] erro fear&greed: {e}")

    fg_score = int(sum(scores) / len(scores)) if scores else 50
    fg_score = min(max(fg_score, 0), 100)

    if fg_score <= 25:
        label, cor, tipo = "MEDO EXTREMO",     "#FF1744", "bear"
    elif fg_score <= 45:
        label, cor, tipo = "MEDO",             "#FF9900", "amber"
    elif fg_score <= 55:
        label, cor, tipo = "NEUTRO",           "#888888", "muted"
    elif fg_score <= 75:
        label, cor, tipo = "GANÂNCIA",         "#00C853", "bull"
    else:
        label, cor, tipo = "GANÂNCIA EXTREMA", "#00FF88", "bull"

    return {
        'score':       fg_score,
        'label':       label,
        'cor':         cor,
        'tipo':        tipo,
        'componentes': componentes,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_fear_greed_br() -> dict:
    """
    Fear & Greed brasileiro com 7 componentes adaptados ao mercado BR.
    """
    import numpy as np

    scores: dict = {}
    total = 0
    n = 0

    try:
        _ibov = yf.Ticker('^BVSP').history(period='1y', auto_adjust=True)['Close'].dropna()
    except Exception:
        _ibov = None

    # 1. Momentum IBOV vs MM125
    if _ibov is not None and len(_ibov) >= 125:
        _mm125 = float(_ibov.rolling(125).mean().iloc[-1])
        _atual = float(_ibov.iloc[-1])
        _mom   = (_atual / _mm125 - 1) * 100
        _s = min(100, max(0, 50 + _mom * 3))
        scores['momentum_ibov'] = round(_s)
        total += _s; n += 1

    # 2. VIX invertido
    try:
        _vix = yf.Ticker('^VIX').history(period='3mo', auto_adjust=True)['Close'].dropna()
        if len(_vix) >= 20:
            _vix_atual = float(_vix.iloc[-1])
            _s = min(100, max(0, 100 - (_vix_atual - 10) * 3))
            scores['vix_invertido'] = round(_s)
            total += _s; n += 1
    except Exception:
        pass

    # 3. Posição 52 semanas IBOV
    if _ibov is not None and len(_ibov) >= 252:
        _h52 = float(_ibov.rolling(252).max().iloc[-1])
        _l52 = float(_ibov.rolling(252).min().iloc[-1])
        _at  = float(_ibov.iloc[-1])
        _pct = (_at - _l52) / (_h52 - _l52) * 100 if _h52 > _l52 else 50
        scores['range_52s'] = round(_pct)
        total += _pct; n += 1

    # 4. Small caps vs IBOV (SMAL11 vs BOVA11)
    try:
        _smal = yf.Ticker('SMAL11.SA').history(period='1mo', auto_adjust=True)['Close'].dropna()
        _bova = yf.Ticker('BOVA11.SA').history(period='1mo', auto_adjust=True)['Close'].dropna()
        if len(_smal) >= 5 and len(_bova) >= 5:
            _ret_smal = float(_smal.iloc[-1] / _smal.iloc[0] - 1)
            _ret_bova = float(_bova.iloc[-1] / _bova.iloc[0] - 1)
            _diff = (_ret_smal - _ret_bova) * 100
            _s = min(100, max(0, 50 + _diff * 10))
            scores['small_vs_ibov'] = round(_s)
            total += _s; n += 1
    except Exception:
        pass

    # 5. Dólar invertido (USD/BRL alto = medo)
    try:
        _usdbrl = yf.Ticker('BRL=X').history(period='3mo', auto_adjust=True)['Close'].dropna()
        if len(_usdbrl) >= 20:
            _d_atual = float(_usdbrl.iloc[-1])
            _d_media = float(_usdbrl.rolling(60).mean().iloc[-1])
            _desvio = (_d_atual / _d_media - 1) * 100
            _s = min(100, max(0, 50 - _desvio * 5))
            scores['dolar_invertido'] = round(_s)
            total += _s; n += 1
    except Exception:
        pass

    # 6. Volume IBOV
    try:
        _ibov_full = yf.Ticker('^BVSP').history(period='3mo', auto_adjust=True)
        if 'Volume' in _ibov_full:
            _vol = _ibov_full['Volume'].dropna()
            if len(_vol) >= 30:
                _v_at  = float(_vol.iloc[-5:].mean())
                _v_med = float(_vol.rolling(30).mean().iloc[-1])
                _ratio = _v_at / _v_med if _v_med > 0 else 1
                _s = min(100, max(0, _ratio * 50))
                scores['volume_ibov'] = round(_s)
                total += _s; n += 1
    except Exception:
        pass

    if n == 0:
        return {'score': 50, 'label': 'neutro', 'scores': {}}

    _score_final = round(total / n)

    if _score_final >= 75:
        _label = 'ganância extrema'
    elif _score_final >= 60:
        _label = 'ganância'
    elif _score_final >= 45:
        _label = 'neutro'
    elif _score_final >= 30:
        _label = 'medo'
    else:
        _label = 'medo extremo'

    return {'score': _score_final, 'label': _label, 'scores': scores, 'n': n}


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_correlacoes(tickers_tuple: tuple, janela: int = 60) -> dict:
    """
    Calcula matriz de correlação e séries de correlação rolante
    entre pares relevantes (ativo da watchlist vs benchmark).
    """
    tickers = list(tickers_tuple)
    resultado = {
        'matriz_atual':  None,
        'retornos':      None,
        'rolling_pairs': {},
    }

    try:
        hist = yf.download(
            tickers, period="2y",
            auto_adjust=True, progress=False,
        )['Close']

        if isinstance(hist, pd.Series):
            hist = hist.to_frame(name=tickers[0])

        # Remove colunas com dados insuficientes (< 70% de preenchimento)
        hist = hist.dropna(axis=1, thresh=int(len(hist) * 0.7))
        hist = hist.ffill().dropna()

        retornos = hist.pct_change().dropna()

        # Matriz de correlação na janela solicitada
        if len(retornos) >= janela:
            resultado['matriz_atual'] = (
                retornos.iloc[-janela:]
                .corr()
                .round(2)
            )

        resultado['retornos'] = retornos

        # Pares relevantes: ativo da watchlist vs benchmark natural
        cols = list(retornos.columns)
        benchmarks_set = {'^BVSP', '^GSPC', 'BRL=X', 'GC=F'}
        pares_relevantes = []

        for t in [c for c in cols if c not in benchmarks_set]:
            bench = '^BVSP' if t.endswith('.SA') else '^GSPC'
            if bench in cols:
                pares_relevantes.append((t, bench))

        # Par IBOV vs S&P500 sempre incluso
        if '^BVSP' in cols and '^GSPC' in cols:
            pares_relevantes.append(('^BVSP', '^GSPC'))

        for par in pares_relevantes[:6]:  # máx 6 pares no gráfico
            t1, t2 = par
            if t1 in retornos.columns and t2 in retornos.columns:
                rolling_corr = (
                    retornos[t1]
                    .rolling(janela)
                    .corr(retornos[t2])
                    .dropna()
                )
                resultado['rolling_pairs'][f"{t1} / {t2}"] = rolling_corr

    except Exception as e:
        logger.warning(f"[macro] erro correlação: {e}")

    return resultado


def renderizar_noticias(ticker, titulo_secao):
    section_title(titulo_secao)
    try:
        acao = yf.Ticker(ticker)
        noticias = acao.news
        if noticias:
            noticias_renderizadas = 0
            for noti in noticias:
                if noticias_renderizadas >= 5: break
                dados = noti.get('content', noti)
                titulo = dados.get('title', dados.get('headline', ''))
                if not titulo: continue
                link = dados.get('link', dados.get('url', dados.get('clickThroughUrl', dados.get('previewUrl', '#'))))
                if isinstance(link, dict): link = link.get('url', '#')
                publisher_data = dados.get('provider', dados.get('publisher', 'agência internacional'))
                if isinstance(publisher_data, dict): publisher = publisher_data.get('displayName', 'agência internacional')
                else: publisher = publisher_data
                
                st.markdown(f'<div class="card" style="padding:10px; border-left:3px solid #00B0FF; margin-bottom: 8px;"><div style="font-family:Courier New; font-size:0.7em; color:#888;">{publisher.lower()}</div><a href="{link}" target="_blank" style="text-decoration:none; color:#E0E0E0; font-family:Courier New; font-size:0.85rem;">{titulo.lower()}</a></div>', unsafe_allow_html=True)
                noticias_renderizadas += 1
            if noticias_renderizadas == 0: st.info("formato interno de notícias não suportado.")
        else: empty_state("🗞️", "sem notícias", "feed vazio no momento.")
    except Exception as e: st.error(f"falha ao sincronizar feed de notícias.")

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_retornos_setoriais():
    etfs_setoriais = {
        "energia": "XLE", 
        "financeiro": "XLF", 
        "tecnologia": "XLK", 
        "saúde": "XLV", 
        "indústria": "XLI", 
        "cons. básico": "XLP", 
        "cons. discric.": "XLY", 
        "materiais": "XLB", 
        "utilities": "XLU", 
        "imobiliário": "XLRE", 
        "telecom": "XLC"
    }
    periodos = ["1mo", "3mo", "6mo", "1y"]
    resultados = {}
    for label, ticker in etfs_setoriais.items():
        linha = []
        for periodo in periodos:
            try:
                df = yf.download(ticker, period=periodo, auto_adjust=True, progress=False)
                fechamento = df['Close']
                if isinstance(fechamento, pd.DataFrame):
                    fechamento = fechamento[ticker]
                fechamento = fechamento.dropna()
                if not fechamento.empty:
                    retorno = ((fechamento.iloc[-1] / fechamento.iloc[0]) - 1) * 100
                    linha.append(round(retorno, 2))
                else:
                    linha.append(None)
            except Exception:
                linha.append(None)
        resultados[label] = linha
    
    return pd.DataFrame(resultados.values(), index=list(resultados.keys()), columns=["1 mês", "3 meses", "6 meses", "12 meses"])

def diagnosticar_ciclo(t10y2y, vix, hy_spread):
    if t10y2y is None or vix is None:
        return "dados insuficientes", "#555555", "—"
    if t10y2y < -0.2 and vix > 20:
        return "🔴 contração / recessão", "#FF1744", "utilities (xlu), saúde (xlv), cons. básico (xlp)"
    if t10y2y < 0.3 and vix < 20 and (hy_spread is not None and hy_spread < 4.5):
        return "🟡 recuperação (early cycle)", "#FF9900", "financeiro (xlf), indústria (xli), cons. discric. (xly)"
    if 0.3 <= t10y2y < 1.0 and vix < 18:
        return "🟢 expansão (mid cycle)", "#00C853", "tecnologia (xlk), indústria (xli), energia (xle)"
    if t10y2y >= 1.0 and vix < 20:
        return "🟡 pico de ciclo (late cycle)", "#FF9900", "energia (xle), materiais (xlb), saúde (xlv)"
    return "⚪ transição", "#888888", "posicionamento neutro — aguardar confirmação"

def get_eventos_macro_fixos() -> list[dict]:
    """
    Retorna calendário de eventos macro fixos para os próximos 90 dias.
    Datas atualizadas manualmente — COPOM, Fed, ECB.
    """
    hoje = datetime.date.today()

    eventos = [
        # COPOM 2026
        {"data": datetime.date(2026, 5, 6),  "evento": "COPOM — decisão de juros", "categoria": "brasil", "impacto": "alto"},
        {"data": datetime.date(2026, 6, 17), "evento": "COPOM — decisão de juros", "categoria": "brasil", "impacto": "alto"},
        {"data": datetime.date(2026, 7, 29), "evento": "COPOM — decisão de juros", "categoria": "brasil", "impacto": "alto"},
        {"data": datetime.date(2026, 9, 16), "evento": "COPOM — decisão de juros", "categoria": "brasil", "impacto": "alto"},
        {"data": datetime.date(2026, 11, 4), "evento": "COPOM — decisão de juros", "categoria": "brasil", "impacto": "alto"},
        {"data": datetime.date(2026, 12, 9), "evento": "COPOM — decisão de juros", "categoria": "brasil", "impacto": "alto"},
        # Fed 2026
        {"data": datetime.date(2026, 6, 17), "evento": "Fed — decisão de juros (FOMC)", "categoria": "eua", "impacto": "alto"},
        {"data": datetime.date(2026, 7, 29), "evento": "Fed — decisão de juros (FOMC)", "categoria": "eua", "impacto": "alto"},
        {"data": datetime.date(2026, 9, 16), "evento": "Fed — decisão de juros (FOMC)", "categoria": "eua", "impacto": "alto"},
        {"data": datetime.date(2026, 11, 4), "evento": "Fed — decisão de juros (FOMC)", "categoria": "eua", "impacto": "alto"},
        {"data": datetime.date(2026, 12, 9), "evento": "Fed — decisão de juros (FOMC)", "categoria": "eua", "impacto": "alto"},
        # IPCA 2026
        {"data": datetime.date(2026, 5, 12), "evento": "IPCA — inflação mensal (IBGE)", "categoria": "brasil", "impacto": "medio"},
        {"data": datetime.date(2026, 6, 9),  "evento": "IPCA — inflação mensal (IBGE)", "categoria": "brasil", "impacto": "medio"},
        {"data": datetime.date(2026, 7, 9),  "evento": "IPCA — inflação mensal (IBGE)", "categoria": "brasil", "impacto": "medio"},
        # CPI EUA 2026
        {"data": datetime.date(2026, 5, 13), "evento": "CPI EUA — inflação ao consumidor", "categoria": "eua", "impacto": "medio"},
        {"data": datetime.date(2026, 6, 10), "evento": "CPI EUA — inflação ao consumidor", "categoria": "eua", "impacto": "medio"},
        {"data": datetime.date(2026, 7, 14), "evento": "CPI EUA — inflação ao consumidor", "categoria": "eua", "impacto": "medio"},
        # Payroll EUA 2026
        {"data": datetime.date(2026, 5, 1),  "evento": "Payroll EUA — empregos não-agrícolas", "categoria": "eua", "impacto": "alto"},
        {"data": datetime.date(2026, 6, 5),  "evento": "Payroll EUA — empregos não-agrícolas", "categoria": "eua", "impacto": "alto"},
        {"data": datetime.date(2026, 7, 2),  "evento": "Payroll EUA — empregos não-agrícolas", "categoria": "eua", "impacto": "alto"},
    ]

    proximos = [e for e in eventos if e['data'] >= hoje]
    proximos.sort(key=lambda x: x['data'])
    return proximos[:20]


def buscar_earnings_calendario(tickers_tuple: tuple, data_fim_str: str | None = None) -> list[dict]:
    """
    Busca earnings dates via FMP para uma lista de tickers.
    Substitui a versão yfinance que quebra no yfinance >=1.3.0
    (.calendar retorna dict em vez de DataFrame).
    """
    hoje = datetime.date.today()
    fim  = data_fim_str or (hoje + datetime.timedelta(days=90)).strftime("%Y-%m-%d")

    fmp_eventos = _fmp_earnings_calendar(
        tickers     = list(tickers_tuple),
        data_inicio = hoje.strftime("%Y-%m-%d"),
        data_fim    = fim,
    )

    eventos = []
    for ev in fmp_eventos:
        try:
            data_ev = datetime.date.fromisoformat(ev["data"])
        except Exception:
            continue

        eps_e = ev.get("eps_est")
        eps_r = ev.get("eps_real")
        surp  = ev.get("surpresa")

        if eps_r is not None:
            detalhe = f"eps real: {eps_r:.2f}"
            if surp is not None:
                detalhe += f" ({'+' if surp >= 0 else ''}{surp:.1f}% vs est.)"
        elif eps_e is not None:
            detalhe = f"eps estimado: {eps_e:.2f}"
        else:
            detalhe = "eps: n/d"

        hora_label = {"bmo": "antes da abertura", "amc": "após fechamento"}.get(
            ev.get("hora", ""), ev.get("hora", "")
        )
        if hora_label:
            detalhe += f" | {hora_label}"

        eventos.append({
            "data":      data_ev,
            "evento":    f"{ev['ticker']} — divulgação de resultados",
            "categoria": "earnings",
            "impacto":   "alto",
            "detalhe":   detalhe,
        })

    eventos.sort(key=lambda x: x["data"])
    return eventos

# ==========================================
# abas principais da página
# ==========================================
tab_global, tab_ciclo, tab_calendar, tab_overlay, tab_sentimento, tab_correlacoes = st.tabs(["🌐 painel global", "🔄 ciclo econômico", "📅 calendário de eventos", "🔭 overlay macro × preços", "🧠 sentimento", "🔗 correlações"])

with tab_global:
    auto_refresh_indicator(1440) # atualizado diariamente pelo cache
    
    with st.spinner("sincronizando feed de bancos centrais e mídia global via apis oficiais..."):
        df_br_master, df_global_master, df_comm_master = puxar_historico_mestre()
        
        col_espaco, col_filtro = st.columns([7, 3])
        with col_filtro:
            janela = st.radio("horizonte de tempo:", ["3 anos", "5 anos", "10 anos"], index=1, horizontal=True, label_visibility="collapsed")
            
        anos_filtro = int(janela.split()[0])
        data_corte = datetime.datetime.today() - datetime.timedelta(days=365 * anos_filtro)
        
        df_br = df_br_master[df_br_master.index >= data_corte] if not df_br_master.empty else df_br_master
        df_global = df_global_master[df_global_master.index >= data_corte] if not df_global_master.empty else df_global_master
        
        if not df_comm_master.empty:
            df_comm = df_comm_master[df_comm_master.index >= data_corte]
            if isinstance(df_comm.columns, pd.MultiIndex): df_comm.columns = df_comm.columns.get_level_values(1)
        else: df_comm = df_comm_master

        # Atualiza macro_context global para uso nas outras páginas
        _selic_ss  = valor_atual_seguro(df_br, 'Selic')
        _ipca_ss   = valor_atual_seguro(df_br, 'IPCA')
        _vix_ss    = valor_atual_seguro(df_global, 'VIXCLS')

        if _selic_ss is not None or _vix_ss is not None:
            _selic_val = float(_selic_ss) if _selic_ss is not None else st.session_state.get("macro_context", {}).get("selic", 10.75)
            _ipca_val  = float(_ipca_ss)  if _ipca_ss  is not None else st.session_state.get("macro_context", {}).get("ipca", 4.5)
            _vix_val   = float(_vix_ss)   if _vix_ss   is not None else st.session_state.get("macro_context", {}).get("vix", 15.0)

            _juros_altos = _selic_val > 10.0
            _risco_alto  = _vix_val   > 20.0

            if _juros_altos and not _risco_alto:
                _regime_label = "juros altos / risco controlado"
            elif _juros_altos and _risco_alto:
                _regime_label = "juros altos / stress global"
            elif not _juros_altos and _risco_alto:
                _regime_label = "juros baixos / stress global"
            else:
                _regime_label = "juros baixos / risco controlado"

            st.session_state["macro_context"] = {
                "selic": round(_selic_val, 2),
                "ipca":  round(_ipca_val, 2),
                "vix":   round(_vix_val, 1),
                "label": _regime_label,
            }

        section_title("leitura macroeconômica (ai synthesis)")
        if st.button("gerar relatório do cenário atual >>", type="primary"):
            with st.spinner("processando vetores de juros, inflação e risco global..."):
                _prompt_macro = (
                    "dados macroeconômicos atuais:\n"
                    f"brasil — selic: {valor_atual_seguro(df_br, 'Selic') or 0:.2f}%, "
                    f"ipca: {valor_atual_seguro(df_br, 'IPCA') or 0:.2f}%\n"
                    f"eua — fed funds: {valor_atual_seguro(df_global, 'FEDFUNDS') or 0:.2f}%, "
                    f"cpi m/m: {valor_atual_seguro(df_global, 'CPI_MoM') or 0:.2f}%\n"
                    f"europa — bce: {valor_atual_seguro(df_global, 'ECBDFR') or 0:.2f}%\n"
                    f"risco global — vix: {valor_atual_seguro(df_global, 'VIXCLS') or 0:.2f}\n\n"
                    "escreva 3 bullet points curtos em português, letra minúscula:\n"
                    "1. relação juros brasil x eua e implicação para o câmbio.\n"
                    "2. temperatura inflacionária global.\n"
                    "3. apetite ao risco (vix) e o que isso sinaliza para emergentes."
                )
                chamar_ia(
                    prompt_usuario = _prompt_macro,
                    system         = SYSTEM_MACRO,
                    max_tokens     = 400,
                    temperatura    = 0.3,
                    stream         = True,
                )
        
        st.markdown("---")
        
        aba_sel = st.radio("selecione o mercado:", ["🇧🇷 brasil", "🇺🇸 estados unidos", "🌍 europa/ásia", "🌐 risco", "🛢️ commodities", "📰 macro news"], horizontal=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        if aba_sel == "🇧🇷 brasil":
            c1, c2, c3, c4 = st.columns(4)
            v_selic = valor_atual_seguro(df_br, 'Selic')
            v_ipca_m = valor_atual_seguro(df_br, 'IPCA')
            v_dolar = valor_atual_seguro(df_br, 'Dolar')
            v_desemp = valor_atual_seguro(df_br, 'Desemprego')

            # Calcula IPCA acumulado 12 meses
            _ipca_12m = None
            if 'IPCA' in df_br.columns:
                _ipca_mensal = df_br['IPCA'].dropna() / 100
                _ipca_roll = (1 + _ipca_mensal).rolling(12).apply(lambda x: x.prod() - 1, raw=True) * 100
                df_br['IPCA_12M'] = _ipca_roll
                _ipca_12m = valor_atual_seguro(df_br, 'IPCA_12M')

            with c1: metric_card("selic atual", fmt_pct(v_selic, sinal=False))
            with c2: metric_card("ipca 12m", fmt_pct(_ipca_12m or v_ipca_m, sinal=False))
            with c3: metric_card("dólar (ptax)", fmt_preco(v_dolar, "r$"))
            with c4: metric_card("desemprego", fmt_pct(v_desemp, sinal=False))
            
            st.markdown(tooltip_info("Selic — taxa básica de juros definida pelo Copom. Impacta diretamente renda fixa, crédito e atividade econômica."), unsafe_allow_html=True)
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(criar_grafico_macro(df_br, 'Selic', "taxa selic histórica (%)", "#00C853"), use_container_width=True, config={'responsive': True})
            with g2:
                if 'IPCA_12M' in df_br.columns and not df_br['IPCA_12M'].dropna().empty:
                    _fig_ipca = go.Figure()
                    _fig_ipca.add_trace(go.Scatter(
                        x=df_br.index, y=df_br['IPCA_12M'].dropna(),
                        name='IPCA acum. 12m',
                        line=dict(color='#00B0FF', width=2),
                        hovertemplate='%{x}<br>IPCA 12m: %{y:.2f}%<extra></extra>',
                    ))
                    _fig_ipca.add_hline(y=3.0, line_color='#00C853', line_dash='dash', line_width=1,
                                        annotation_text='meta 3%', annotation_font_color='#00C853', annotation_font_size=9)
                    _fig_ipca.add_hline(y=4.5, line_color='#FF9900', line_dash='dot', line_width=1,
                                        annotation_text='teto 4.5%', annotation_font_color='#FF9900', annotation_font_size=9)
                    _fig_ipca.update_layout(**base_layout(height=300, title='inflação acumulada 12 meses — ipca (%)'))
                    st.plotly_chart(_fig_ipca, use_container_width=True, config={'responsive': True})
                    st.caption("ipca acumulado dos últimos 12 meses (produto das taxas mensais). meta bcb: 3% ± 1.5pp. fonte: bcb sgs série 433.")
                else:
                    st.plotly_chart(criar_grafico_macro(df_br, 'IPCA', "inflação mensal ipca (%)", "#00B0FF"), use_container_width=True, config={'responsive': True})
            st.markdown(tooltip_info("Dólar Ptax — taxa de câmbio oficial calculada pelo BCB. Referência para contratos de derivativos e ajuste de ativos dolarizados."), unsafe_allow_html=True)
            g3, g4 = st.columns(2)
            with g3: st.plotly_chart(criar_grafico_macro(df_br, 'Dolar', "dólar comercial (r$)", "#FFFFFF"), use_container_width=True, config={'responsive': True})
            with g4: st.plotly_chart(criar_grafico_macro(df_br, 'Desemprego', "taxa de desemprego pnadc (%)", "#E040FB"), use_container_width=True, config={'responsive': True})
            st.markdown(tooltip_info("Desemprego PNAD Contínua — taxa de desemprego calculada pelo IBGE. Indicador defasado de atividade econômica."), unsafe_allow_html=True)

            # ── FISCAL BRASILEIRO ──────────────────────────────────────────────
            st.markdown("---")
            section_title("🏛️ fiscal brasileiro")

            # usar df_br_master para o semáforo (precisa dos 6 meses mais recentes
            # independente do filtro de horizonte selecionado pelo usuário)
            fiscal = calcular_semaforo_fiscal(df_br_master)

            f1, f2, f3 = st.columns(3)
            with f1:
                divida_val = fiscal['divida_pib']
                tend_val   = fiscal['tendencia_divida']
                if divida_val is not None:
                    if tend_val is not None:
                        sinal_tend  = "▲" if tend_val > 0 else "▼"
                        delta_divida = f"{sinal_tend} {abs(tend_val):.1f}pp em 6m"
                        cor_tend     = "bear" if tend_val > 1 else ("bull" if tend_val < -1 else "muted")
                    else:
                        delta_divida, cor_tend = "", "muted"
                    metric_card("dívida bruta/pib", f"{divida_val:.1f}%", delta_divida, cor_tend)
                else:
                    metric_card("dívida bruta/pib", "n/d", "sem dados bcb")
            with f2:
                prim_val = fiscal['result_primario']
                if prim_val is not None:
                    metric_card(
                        "resultado primário",
                        f"{prim_val:+.2f}% pib",
                        "superávit" if prim_val >= 0 else "déficit",
                        "bull" if prim_val >= 0 else "bear",
                    )
                else:
                    metric_card("resultado primário", "n/d", "sem dados bcb")
            with f3:
                cores_map = {"bear": "bear", "amber": "amber", "bull": "bull"}
                metric_card("status fiscal", fiscal['label'], "", cores_map.get(fiscal['cor'], "muted"))

            gf1, gf2 = st.columns(2)
            with gf1:
                fig_divida = criar_grafico_macro(df_br, 'Divida_Bruta_PIB',
                                                 "dívida bruta do governo geral (% pib)", "#FF1744")
                fig_divida.add_hline(
                    y=60, line_color="#FF9900", line_dash="dash", line_width=1,
                    annotation_text="limite prudencial 60% pib",
                    annotation_font=dict(color="#FF9900", size=10, family="Courier New"),
                )
                st.plotly_chart(fig_divida, use_container_width=True, config={'responsive': True})
            with gf2:
                st.plotly_chart(
                    criar_grafico_macro(df_br, 'Result_Primario',
                                        "resultado primário do setor público (% pib)", "#00B0FF"),
                    use_container_width=True,
                    config={'responsive': True},
                )

            if fiscal['status'] == 'critico':
                corpo_fiscal = (
                    "trajetória fiscal insustentável detectada. "
                    "dívida/pib acima de 90% com déficit primário elevado penaliza "
                    "ativos de risco brasileiros. prefira ativos dolarizados ou renda fixa curta."
                )
                tipo_fiscal = "bear"
            elif fiscal['status'] == 'alerta':
                corpo_fiscal = (
                    "fiscal em deterioração. monitore evolução da dívida/pib e aprovação "
                    "de medidas de contenção de gastos. impacto moderado no câmbio e juros longos."
                )
                tipo_fiscal = "amber"
            else:
                corpo_fiscal = (
                    "fiscal sob controle. trajetória de dívida estável reduz prêmio "
                    "de risco brasil e favorece ativos locais."
                )
                tipo_fiscal = "bull"
            status_card("interpretação fiscal", corpo_fiscal, tipo=tipo_fiscal)

        elif aba_sel == "🇺🇸 estados unidos":
            c1, c2, c3, c4 = st.columns(4)
            v_fed = valor_atual_seguro(df_global, 'FEDFUNDS')
            v_cpi_yoy = valor_atual_seguro(df_global, 'CPI_YOY')
            v_dgs10 = valor_atual_seguro(df_global, 'DGS10')
            v_unrate = valor_atual_seguro(df_global, 'UNRATE')
            with c1: metric_card("fed funds rate", fmt_pct(v_fed, sinal=False))
            with c2: metric_card("cpi yoy", fmt_pct(v_cpi_yoy, sinal=False))
            with c3: metric_card("treasury 10y", fmt_pct(v_dgs10, sinal=False))
            with c4: metric_card("desemprego (us)", fmt_pct(v_unrate, sinal=False))
            
            st.markdown(tooltip_info("Fed Funds Rate — taxa de juros básica americana definida pelo FOMC. Referência global para custo do dinheiro."), unsafe_allow_html=True)
            st.markdown(tooltip_info("CPI YoY — variação anual do índice de preços ao consumidor americano. Principal referência de inflação nos EUA, acompanhada de perto pelo Fed."), unsafe_allow_html=True)
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(criar_grafico_macro(df_global, 'FEDFUNDS', "fed funds rate (%)", "#00C853"), use_container_width=True, config={'responsive': True})
            with g2: st.plotly_chart(criar_grafico_macro(df_global, 'CPI_YOY', "inflação anual cpi yoy (%)", "#00B0FF"), use_container_width=True, config={'responsive': True})
            st.markdown(tooltip_info("Treasury 10y — rendimento do título público americano de 10 anos. Referência para taxas de juros globais e custo de financiamento de longo prazo."), unsafe_allow_html=True)
            st.markdown(tooltip_info("UNRATE — taxa de desemprego americana (U-3). Indicador-chave de saúde do mercado de trabalho, monitorado pelo Fed."), unsafe_allow_html=True)
            g3, g4 = st.columns(2)
            with g3: st.plotly_chart(criar_grafico_macro(df_global, 'DGS10', "treasury yield 10y (%)", "#FFFFFF"), use_container_width=True, config={'responsive': True})
            with g4: st.plotly_chart(criar_grafico_macro(df_global, 'UNRATE', "taxa de desemprego (us) (%)", "#FF9900"), use_container_width=True, config={'responsive': True})

            # ── FISCAL EUA ──────────────────────────────────────────────────────
            st.markdown("---")
            section_title("🏛️ fiscal americano")

            v_divida_eua_pib = valor_atual_seguro(df_global, 'GFDEGDQ188S')
            v_deficit_eua = valor_atual_seguro(df_global, 'MTSDS133FMS')

            f1, f2 = st.columns(2)
            with f1:
                if v_divida_eua_pib is not None:
                    metric_card("dívida pública/pib (eua)", f"{v_divida_eua_pib:.1f}%")
                else:
                    metric_card("dívida pública/pib (eua)", "n/d", "fred indisponível")
            with f2:
                if v_deficit_eua is not None:
                    metric_card("déficit/superávit federal", f"{v_deficit_eua:+.1f}% pib")
                else:
                    metric_card("déficit/superávit federal", "n/d", "fred indisponível")

            gf1, gf2 = st.columns(2)
            with gf1:
                if 'GFDEGDQ188S' in df_global.columns and not df_global['GFDEGDQ188S'].dropna().empty:
                    fig_debt = criar_grafico_macro(df_global, 'GFDEGDQ188S', "dívida pública federal (% pib)", "#FF1744")
                    fig_debt.add_hline(y=78, line_color="#FF9900", line_dash="dash", line_width=1,
                                      annotation_text="patamar 2019 (pré-covid)", annotation_font_color="#FF9900", annotation_font_size=9)
                    st.plotly_chart(fig_debt, use_container_width=True, config={'responsive': True})
            with gf2:
                if 'MTSDS133FMS' in df_global.columns and not df_global['MTSDS133FMS'].dropna().empty:
                    st.plotly_chart(criar_grafico_macro(df_global, 'MTSDS133FMS', "resultado federal mensal (% pib)", "#00B0FF"),
                                    use_container_width=True, config={'responsive': True})

        elif aba_sel == "🌍 europa/ásia":
            v_ecb = valor_atual_seguro(df_global, 'ECBDFR')
            if v_ecb is not None: st.plotly_chart(criar_grafico_macro(df_global, 'ECBDFR', "bce - taxa de juros europeia (%)", "#FF9900"), use_container_width=True, config={'responsive': True})
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(criar_grafico_macro(df_global, 'IRLTLT01EZM156N', "euro area 10y yield (%)", "#00B0FF"), use_container_width=True, config={'responsive': True})
            with g2: st.plotly_chart(criar_grafico_macro(df_global, 'IRLTLT01JPM156N', "japan 10y yield (%)", "#FF1744"), use_container_width=True, config={'responsive': True})

        elif aba_sel == "🌐 risco":
            section_title("curva de juros eua & spreads de crédito")
            
            c1, c2, c3 = st.columns(3)
            v_vix = valor_atual_seguro(df_global, 'VIXCLS')
            v_t10y2y = valor_atual_seguro(df_global, 'T10Y2Y')
            v_hy = valor_atual_seguro(df_global, 'BAMLH0A0HYM2')
            
            with c1:
                metric_card("vix atual", f"{v_vix:.2f}" if v_vix is not None else "n/d")
            with c2:
                cor_t10 = "bull" if (v_t10y2y is not None and v_t10y2y > 0) else ("bear" if (v_t10y2y is not None and v_t10y2y < 0) else "")
                metric_card("spread 10y-2y", fmt_pct(v_t10y2y, sinal=False) if v_t10y2y is not None else "n/d", cor_delta=cor_t10)
            with c3:
                metric_card("spread hy crédito", fmt_pct(v_hy, sinal=False) if v_hy is not None else "n/d")
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            if v_t10y2y is not None:
                if v_t10y2y < 0:
                    st.warning("⚠️ curva invertida: historicamente precede recessão em 12-18 meses. posicionamento defensivo recomendado.")
                elif 0 <= v_t10y2y <= 0.5:
                    st.info("📊 spread estreito: ciclo de crédito em atenção.")
            
            fig_t10 = criar_grafico_macro(df_global, 'T10Y2Y', "spread 10y-2y (%)", "#00B0FF")
            fig_t10.add_hline(y=0, line_color="#FF1744", line_dash="dash", line_width=1)
            fig_t10.add_annotation(x=0.01, y=0, xref="paper", text="zona de inversão", font=dict(color="#FF1744", size=10, family="Courier New"), showarrow=False, yshift=-14)
            st.plotly_chart(fig_t10, use_container_width=True, config={'responsive': True})
            
            st.plotly_chart(criar_grafico_macro(df_global, 'VIXCLS', "índice vix (cboe volatility index)", "#FF1744"), use_container_width=True, config={'responsive': True})
            st.info("o vix mede a volatilidade esperada do s&p 500.")
            
            st.plotly_chart(criar_grafico_macro(df_global, 'BAMLH0A0HYM2', "spread crédito high yield (%)", "#E040FB"), use_container_width=True, config={'responsive': True})

        elif aba_sel == "🛢️ commodities":
            _commodities_config = [
                ("CL=F",  "petróleo wti",    "#8B00FF", "us$/barril", "^GSPC",   "s&p500"),
                ("GC=F",  "ouro",            "#FFD700", "us$/onça",   "^TNX",    "treasury 10y"),
                ("SI=F",  "prata",           "#C0C0C0", "us$/onça",   "GC=F",    "ouro"),
                ("HG=F",  "cobre",           "#B87333", "us$/libra",  "^GSPC",   "s&p500"),
                ("NG=F",  "gás natural",     "#00BFFF", "us$/mmbtu",  "CL=F",    "petróleo"),
                ("ZC=F",  "milho",           "#FFD700", "us$/bushel", "BOVA11.SA","ibov"),
                ("ZS=F",  "soja",            "#90EE90", "us$/bushel", "BOVA11.SA","ibov"),
                ("ZW=F",  "trigo",           "#DEB887", "us$/bushel", "ZC=F",    "milho"),
                ("KC=F",  "café",            "#6F4E37", "us$/libra",  "BRL=X",   "usd/brl"),
                ("SB=F",  "açúcar",          "#FF69B4", "us$/libra",  "BRL=X",   "usd/brl"),
                ("CT=F",  "algodão",         "#F5F5DC", "us$/libra",  "^GSPC",   "s&p500"),
                ("PL=F",  "platina",         "#E5E4E2", "us$/onça",   "GC=F",    "ouro"),
            ]

            _col_com_sel = st.columns(4)
            _selected_comms = []
            for _i, (_tk, _nm, _cor, _un, _bt, _bn) in enumerate(_commodities_config):
                with _col_com_sel[_i % 4]:
                    if st.checkbox(_nm, value=_i < 4, key=f"chk_comm_{_tk}"):
                        _selected_comms.append((_tk, _nm, _cor, _un, _bt, _bn))

            _mostrar_benchmark = st.toggle("mostrar benchmark comparativo", value=True, key="tog_comm_bench")
            _periodo_comm = st.radio(
                "período:",
                ["6mo", "1y", "2y", "5y"],
                format_func=lambda x: {"6mo": "6 meses", "1y": "1 ano", "2y": "2 anos", "5y": "5 anos"}[x],
                horizontal=True,
                key="radio_comm_periodo",
            )

            for _tk, _nm, _cor, _un, _bt, _bn in _selected_comms:
                try:
                    _hist_c = yf.Ticker(_tk).history(period=_periodo_comm, auto_adjust=True)['Close'].dropna()
                    if _hist_c.empty:
                        continue

                    _preco_at = float(_hist_c.iloc[-1])
                    _preco_in = float(_hist_c.iloc[0])
                    _ret_c    = (_preco_at / _preco_in - 1) * 100

                    st.markdown(
                        f'<div style="font-family:Courier New;font-size:0.75rem;color:{_cor};'
                        f'margin-top:12px;margin-bottom:4px;">'
                        f'{_nm.upper()} — {_preco_at:,.2f} {_un} ({_ret_c:+.1f}% no período)'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    if _mostrar_benchmark:
                        try:
                            _hist_b = yf.Ticker(_bt).history(period=_periodo_comm, auto_adjust=True)['Close'].dropna()
                        except Exception:
                            _hist_b = None

                        if _hist_b is not None and not _hist_b.empty:
                            _b100_c = (_hist_c / _hist_c.iloc[0]) * 100
                            _b100_b = (_hist_b / _hist_b.iloc[0]) * 100

                            _fig_c = go.Figure()
                            _fig_c.add_trace(go.Scatter(x=_b100_c.index, y=_b100_c.values, name=_nm, line=dict(color=_cor, width=2), hovertemplate=f'{_nm}: %{{y:.1f}}<extra></extra>'))
                            _fig_c.add_trace(go.Scatter(x=_b100_b.index, y=_b100_b.values, name=_bn, line=dict(color='#555', width=1.5, dash='dot'), hovertemplate=f'{_bn}: %{{y:.1f}}<extra></extra>'))
                            _fig_c.add_hline(y=100, line_color='#333', line_dash='dash', line_width=1)
                            _fig_c.update_layout(**base_layout(height=220, title=f"{_nm} vs {_bn} (base 100)"))
                            st.plotly_chart(_fig_c, use_container_width=True, config={'responsive': True})
                            _ret_b = (float(_hist_b.iloc[-1]) / float(_hist_b.iloc[0]) - 1) * 100
                            st.caption(f"{_nm}: {_ret_c:+.1f}% | {_bn}: {_ret_b:+.1f}% no período. correlação empírica no horizonte selecionado.")
                            continue

                    _fig_c = go.Figure(go.Scatter(x=_hist_c.index, y=_hist_c.values, line=dict(color=_cor, width=2), fill='tozeroy', fillcolor=f'{_cor}15', hovertemplate=f'%{{x}}<br>{_nm}: %{{y:,.2f}} {_un}<extra></extra>'))
                    _fig_c.update_layout(**base_layout(height=200, title=f"{_nm} ({_un})"))
                    st.plotly_chart(_fig_c, use_container_width=True, config={'responsive': True})

                except Exception:
                    st.caption(f"{_nm}: dados indisponíveis")

        elif aba_sel == "📰 macro news":
            col_news1, col_news2 = st.columns(2)
            with col_news1: renderizar_noticias("SPY", "🇺🇸 radar global (spy etf)")
            with col_news2: renderizar_noticias("EWZ", "🇧🇷 radar brasil (ewz etf)")

with tab_ciclo:
    v_t10y2y = valor_atual_seguro(df_global_master, 'T10Y2Y')
    v_vix = valor_atual_seguro(df_global_master, 'VIXCLS')
    v_hy = valor_atual_seguro(df_global_master, 'BAMLH0A0HYM2')
    
    fase_ciclo, cor_ciclo, setores_ciclo = diagnosticar_ciclo(v_t10y2y, v_vix, v_hy)
    
    section_title("🔄 posicionamento no ciclo econômico")
    
    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        metric_card("fase atual do ciclo", fase_ciclo)
    with col_c2:
        st.markdown(f'<div class="card" style="padding:15px; border-left:4px solid {cor_ciclo};"><div style="font-family:Courier New; font-size:0.72rem; color:#555; margin-bottom:5px;">setores favorecidos neste ciclo:</div><div style="font-family:Courier New; font-size:0.9rem; color:#E0E0E0;">{setores_ciclo}</div></div>', unsafe_allow_html=True)

    # --- REGIME MACRO EXPANDIDO (classificacao 6 regimes) ---
    _regime_atual = classificar_regime(
        selic=valor_atual_seguro(df_br_master, 'Selic'),
        vix=valor_atual_seguro(df_global_master, 'VIXCLS'),
        ipca=valor_atual_seguro(df_br_master, 'IPCA'),
    )
    _cor_regime_card = (
        "#FF1744" if "stress" in _regime_atual['label']
        else "#FF9900" if "altos" in _regime_atual['label'] or "muito" in _regime_atual['label']
        else "#00C853"
    )

    st.markdown('<br>', unsafe_allow_html=True)
    section_title("🏷️ regime macro — rotação setorial")

    st.markdown(
        f'<div style="background:#0d0d0d;border:1px solid #1e1e1e;border-left:3px solid {_cor_regime_card};border-radius:6px;padding:16px;margin-bottom:16px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">'
        f'<div><span style="font-family:Courier New;font-size:0.65rem;color:#555;text-transform:uppercase;">regime atual</span><br>'
        f'<span style="font-family:Courier New;font-size:1rem;font-weight:700;color:{_cor_regime_card};">{_regime_atual["label"]}</span></div>'
        f'<div><span style="font-family:Courier New;font-size:0.65rem;color:#555;text-transform:uppercase;">score ambiente</span><br>'
        f'<span style="font-family:Courier New;font-size:1rem;font-weight:700;color:{_cor_regime_card};">{_regime_atual["score_ambiente"]}/100</span></div>'
        f'<div><span style="font-family:Courier New;font-size:0.65rem;color:#555;text-transform:uppercase;">selic / vix</span><br>'
        f'<span style="font-family:Courier New;font-size:0.9rem;color:#ccc;">{_regime_atual["selic"]:.2f}% / {_regime_atual["vix"]:.1f}</span></div>'
        f'</div>'
        f'<div style="margin-top:12px;font-family:Courier New;font-size:0.72rem;color:#888;line-height:1.5;">{_regime_atual["descricao"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Tabela de rotacao
    _fav = _regime_atual['setores_favorecidos']
    _prej = _regime_atual['setores_prejudicados']
    _cfav, _cprej = st.columns(2)
    with _cfav:
        st.markdown(
            f'<div style="background:#0a1a0a;border:1px solid #1a3a1a;border-radius:6px;padding:12px;">'
            f'<div style="font-family:Courier New;font-size:0.62rem;color:#00C853;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">✔ setores favorecidos</div>'
            + ''.join(f'<div style="font-family:Courier New;font-size:0.78rem;color:#aaa;padding:2px 0;">→ {s}</div>' for s in _fav)
            + f'</div>',
            unsafe_allow_html=True,
        )
    with _cprej:
        st.markdown(
            f'<div style="background:#1a0a0a;border:1px solid #3a1a1a;border-radius:6px;padding:12px;">'
            f'<div style="font-family:Courier New;font-size:0.62rem;color:#FF1744;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">✘ setores prejudicados</div>'
            + ''.join(f'<div style="font-family:Courier New;font-size:0.78rem;color:#aaa;padding:2px 0;">→ {s}</div>' for s in _prej)
            + f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="background:#0d0d0d;border:1px solid #1e1e1e;border-radius:4px;padding:10px 14px;margin-top:8px;font-family:Courier New;font-size:0.72rem;color:#FF9900;">'
        f'🎯 {_regime_atual["posicionamento"]}</div>',
        unsafe_allow_html=True,
    )

    section_title("📊 performance setorial s&p 500 (etfs)")
    with st.spinner("carregando retornos setoriais..."):
        df_setores = buscar_retornos_setoriais()
        
    if not df_setores.empty:
        fig_heat = px.imshow(df_setores, color_continuous_scale=[[0, "#FF1744"], [0.5, "#111111"], [1, "#00C853"]], zmin=-15, zmax=15, text_auto=".1f", aspect="auto")
        layout_heat = base_layout(height=420, title="retorno por setor e janela temporal (%)")
        fig_heat.update_layout(**layout_heat)
        fig_heat.update_traces(textfont=dict(family="Courier New", size=11, color="#FFFFFF"))
        fig_heat.update_coloraxes(showscale=False)
        st.plotly_chart(fig_heat, use_container_width=True, config={'responsive': True})
        st.caption("verde = retorno positivo no período | vermelho = retorno negativo | dados: etfs setoriais s&p 500 via yahoo finance")
    else:
        empty_state("📊", "sem dados setoriais", "não foi possível carregar os retornos dos etfs setoriais.")

    section_title("🧠 síntese de rotação (ia)")
    if st.button("gerar análise de rotação setorial >>", type="primary"):
        with st.spinner("o agente está analisando o ciclo e os dados setoriais..."):
            _ctx_setores = ""
            for _idx, _row in df_setores.iterrows():
                _v1m  = f"{_row['1 mês']:.1f}%"    if pd.notna(_row['1 mês'])    else "n/d"
                _v3m  = f"{_row['3 meses']:.1f}%"  if pd.notna(_row['3 meses'])  else "n/d"
                _v6m  = f"{_row['6 meses']:.1f}%"  if pd.notna(_row['6 meses'])  else "n/d"
                _v12m = f"{_row['12 meses']:.1f}%"  if pd.notna(_row['12 meses']) else "n/d"
                _ctx_setores += f"{_idx}: 1m={_v1m}, 3m={_v3m}, 6m={_v6m}, 12m={_v12m}. "
            _prompt_rotacao = (
                f"ciclo econômico atual: {fase_ciclo}\n"
                f"yield curve 10y-2y: {v_t10y2y}% | vix: {v_vix} | spread hy: {v_hy}%\n\n"
                f"retorno dos etfs setoriais:\n{_ctx_setores}\n\n"
                "escreva 4 bullet points curtos em português, letra minúscula:\n"
                "1. fase do ciclo e o que ela implica para alocação.\n"
                "2. setor com melhor momentum (maior retorno consistente nas janelas).\n"
                "3. setor para evitar ou reduzir.\n"
                "4. recomendação de posicionamento para os próximos 3 meses."
            )
            chamar_ia(
                prompt_usuario = _prompt_rotacao,
                system         = SYSTEM_MACRO,
                max_tokens     = 500,
                temperatura    = 0.3,
                stream         = True,
            )

with tab_calendar:
    section_title("📅 calendário de eventos de mercado")

    status_card(
        "cobertura",
        "eventos macro fixos (copom, fed, cpi, payroll) para os próximos 90 dias + earnings dates do portfólio e watchlists via FMP. cache de 1h — datas atualizam automaticamente.",
        tipo="info"
    )

    # filtros
    fc1, fc2 = st.columns([3, 1])
    with fc1:
        filtro_cat = st.multiselect(
            "filtrar por categoria:",
            ["brasil", "eua", "earnings"],
            default=["brasil", "eua", "earnings"],
            key="cal_filtro_cat"
        )
    with fc2:
        janela_dias = st.selectbox("janela:", [30, 60, 90], index=2, key="cal_janela")

    hoje = datetime.date.today()
    limite_cal = hoje + datetime.timedelta(days=janela_dias)

    # eventos macro fixos
    eventos_macro = get_eventos_macro_fixos()
    eventos_macro = [e for e in eventos_macro if e['categoria'] in filtro_cat and e['data'] <= limite_cal]

    # earnings do portfólio + watchlists (via FMP)
    from database.db import get_pesos, listar_watchlists, listar_watchlist
    pesos = get_pesos()
    tickers_port = set([p['ticker'] for p in pesos if p.get('quantidade', 0) > 0])

    # agrega tickers de todas as watchlists do usuário
    try:
        _wls = listar_watchlists() or []
        for _wl in _wls:
            _itens = listar_watchlist(_wl['id']) or []
            for _it in _itens:
                if _it.get('ticker'):
                    tickers_port.add(_it['ticker'])
    except Exception:
        pass

    tickers_port = tuple(tickers_port)

    eventos_earnings = []
    if "earnings" in filtro_cat and tickers_port:
        with st.spinner("buscando earnings dates via FMP (portfólio + watchlists)..."):
            eventos_earnings = buscar_earnings_calendario(
                tickers_port,
                data_fim_str=limite_cal.strftime("%Y-%m-%d"),
            )
            eventos_earnings = [e for e in eventos_earnings if e['data'] <= limite_cal]

    todos_eventos = sorted(eventos_macro + eventos_earnings, key=lambda x: x['data'])

    if not todos_eventos:
        empty_state("📅", "sem eventos", f"nenhum evento encontrado nos próximos {janela_dias} dias para as categorias selecionadas.")
    else:
        # métricas rápidas
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            proximos_7 = len([e for e in todos_eventos if e['data'] <= hoje + datetime.timedelta(days=7)])
            metric_card("próximos 7 dias", str(proximos_7), "eventos críticos" if proximos_7 > 0 else "", "bear" if proximos_7 > 0 else "muted")
        with mc2:
            total_alto = len([e for e in todos_eventos if e['impacto'] == 'alto'])
            metric_card("alto impacto", str(total_alto), f"de {len(todos_eventos)} eventos", "amber")
        with mc3:
            total_earnings = len([e for e in todos_eventos if e['categoria'] == 'earnings'])
            metric_card("earnings portfólio", str(total_earnings), f"nos próximos {janela_dias}d", "info")

        st.markdown("---")

        # timeline de eventos agrupados por semana
        section_title("🗓️ timeline de eventos")

        semana_atual = None
        for evento in todos_eventos:
            semana = evento['data'].isocalendar()[1]
            ano = evento['data'].year
            chave_semana = f"{ano}-{semana}"

            if chave_semana != semana_atual:
                semana_atual = chave_semana
                inicio_semana = evento['data'] - datetime.timedelta(days=evento['data'].weekday())
                dias_ate = (inicio_semana - hoje).days
                if dias_ate <= 0:
                    label_semana = "🔴 esta semana"
                elif dias_ate <= 7:
                    label_semana = "🟡 próxima semana"
                else:
                    label_semana = f"📆 semana de {inicio_semana.strftime('%d/%m')}"
                st.markdown(f'<div style="font-family:Courier New; font-size:0.75rem; color:#555; text-transform:uppercase; letter-spacing:0.1em; margin:16px 0 4px 0; border-bottom:1px solid #1e1e1e; padding-bottom:4px;">{label_semana}</div>', unsafe_allow_html=True)

            cat = evento['categoria']
            cor_cat = {"brasil": "#009C3B", "eua": "#3C3B6E", "earnings": "#FF9900"}.get(cat, "#555")
            icone_imp = {"alto": "🔴", "medio": "🟡", "baixo": "🟢"}.get(evento['impacto'], "⚪")
            label_cat = {"brasil": "BR", "eua": "EUA", "earnings": "EARN"}.get(cat, cat.upper())
            detalhe = evento.get('detalhe', '')

            dias_evento = (evento['data'] - hoje).days
            if dias_evento == 0:
                data_label = "hoje"
                cor_data = "#FF1744"
            elif dias_evento == 1:
                data_label = "amanhã"
                cor_data = "#FF9900"
            else:
                data_label = evento['data'].strftime('%d/%m/%Y')
                cor_data = "#888"

            ev1, ev2 = st.columns([5, 1])
            with ev1:
                texto_evento = f"{evento['evento']}"
                if detalhe:
                    texto_evento += f" | {detalhe}"
                st.markdown(
                    f'<div style="background:#0d0d0d; border:1px solid #1e1e1e; border-left:3px solid {cor_cat}; border-radius:4px; padding:10px 14px; margin-bottom:6px;">'
                    f'<span style="font-family:Courier New; font-size:0.7rem; color:{cor_cat}; text-transform:uppercase; font-weight:bold;">{label_cat}</span>'
                    f'<span style="font-family:Courier New; font-size:0.7rem; color:#333; margin:0 6px;">|</span>'
                    f'<span style="font-family:Courier New; font-size:0.85rem; color:#E0E0E0;">{texto_evento}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            with ev2:
                st.markdown(
                    f'<div style="text-align:right; padding-top:12px;">'
                    f'<span style="font-family:Courier New; font-size:0.75rem; color:{cor_data};">{data_label}</span>'
                    f' {icone_imp}</div>',
                    unsafe_allow_html=True
                )

        st.markdown("---")

        if st.button("🧠 ia: analisar o calendário e identificar riscos", type="primary", use_container_width=True):
            with st.spinner("analisando eventos e gerando briefing..."):
                _eventos_txt = "\n".join([
                    f"{e['data'].strftime('%d/%m/%Y')} | {e['categoria'].upper()} | "
                    f"{e['evento']} | impacto: {e['impacto']}"
                    for e in todos_eventos[:15]
                ])
                _prompt_cal = (
                    f"calendário dos próximos {janela_dias} dias:\n"
                    f"{_eventos_txt}\n\n"
                    "responda em 4 bullet points em português, letra minúscula:\n"
                    "1. evento de maior impacto potencial e o que monitorar.\n"
                    "2. como o calendário pode afetar o mercado brasileiro especificamente.\n"
                    "3. qual posicionamento defensivo faz sentido antes dos eventos críticos.\n"
                    "4. após os eventos, quais serão os principais gatilhos para reposicionamento."
                )
                chamar_ia(
                    prompt_usuario = _prompt_cal,
                    system         = SYSTEM_MACRO,
                    max_tokens     = 600,
                    temperatura    = 0.3,
                    stream         = True,
                )

with tab_overlay:
    st.write("sobreponha a cotação do ativo com indicadores macroeconômicos globais para identificar correlações.")
    
    col_sel_ov, col_man_ov, col_ind = st.columns([3, 2, 3])
    with col_sel_ov:
        opcoes_ov = get_opcoes_selectbox()
        selecao_ov = st.selectbox("ativo:", opcoes_ov, key="overlay_sel")
    with col_man_ov:
        ticker_manual_ov = st.text_input("ou digite:", "", key="overlay_manual").strip().upper()
    with col_ind:
        indicador = st.selectbox("indicador macro:", ["taxa selic (brasil)", "ipca (inflação br)", "fed funds rate (juros eua)", "treasury 10y (eua)", "vix (s&p 500 volatility)"])

    ticker_input = ticker_manual_ov if ticker_manual_ov else (ticker_from_label(selecao_ov) or "PETR4.SA")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("gerar overlay macro", type="primary", use_container_width=True):
        if not ticker_input or ticker_input.startswith("─"):
            st.warning("selecione um ativo válido para iniciar a análise.")
        else:
            with st.spinner(f"buscando histórico de {ticker_input.lower()} e série macroeconômica..."):
                try:
                    stock_data = yf.download(ticker_input, period="5y", auto_adjust=True, progress=False)['Close']
                    if isinstance(stock_data, pd.DataFrame): stock_data = stock_data[ticker_input]
                    stock_data = stock_data.dropna()
                    if hasattr(stock_data.index, 'tz') and stock_data.index.tz is not None: stock_data.index = stock_data.index.tz_localize(None)

                    hoje = datetime.datetime.today()
                    inicio = hoje - datetime.timedelta(days=5*365)
                    macro_data = None
                    macro_name = ""

                    if "selic" in indicador.lower(): macro_data, macro_name = sgs.get({'Selic': 432}, start=inicio)['Selic'], "taxa selic (%)"
                    elif "ipca" in indicador.lower(): macro_data, macro_name = sgs.get({'IPCA': 433}, start=inicio)['IPCA'], "ipca (%)"
                    else:
                        fred = Fred(api_key=st.secrets["FRED_API_KEY"])
                        if "fed funds" in indicador.lower(): macro_data, macro_name = fred.get_series('FEDFUNDS', observation_start=inicio), "fed funds rate (%)"
                        elif "treasury" in indicador.lower(): macro_data, macro_name = fred.get_series('DGS10', observation_start=inicio), "treasury 10y (%)"
                        elif "vix" in indicador.lower(): macro_data, macro_name = fred.get_series('VIXCLS', observation_start=inicio), "índice vix"

                    if macro_data is not None:
                        macro_data = macro_data.dropna()
                        if hasattr(macro_data.index, 'tz') and macro_data.index.tz is not None: macro_data.index = macro_data.index.tz_localize(None)

                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        fig.add_trace(go.Scatter(x=stock_data.index, y=stock_data, name=ticker_input.lower(), line=dict(color="#FF9900", width=2)), secondary_y=False)
                        fig.add_trace(go.Scatter(x=macro_data.index, y=macro_data, name=macro_name, line=dict(color="#00B0FF", dash="dot", width=2)), secondary_y=True)

                        layout_macro = base_layout(height=500, title=f"estudo de correlação: {ticker_input.lower()} vs {macro_name}")
                        fig.update_layout(**layout_macro)
                        fig.update_yaxes(title_text=f"preço {ticker_input.lower()}", showgrid=True, gridcolor='#1e1e1e', secondary_y=False)
                        fig.update_yaxes(title_text=macro_name, showgrid=False, secondary_y=True)
                        fig.update_xaxes(showgrid=True, gridcolor='#1e1e1e')

                        st.plotly_chart(fig, use_container_width=True, config={'responsive': True})
                    else: st.warning("não foi possível obter a série de dados macroeconómicos.")
                except Exception as e: st.error(f"erro ao processar e alinhar os dados: {e}")

with tab_sentimento:
    section_title("😱 fear & greed — eua | brasil | global")

    with st.spinner("calculando índices de sentimento..."):
        _fg_eua = calcular_fear_greed()
        _fg_br  = calcular_fear_greed_br()

        _score_global = round(_fg_eua.get('score', 50) * 0.50 + _fg_br.get('score', 50) * 0.50)
        if _score_global >= 75:
            _label_global = 'ganância extrema'
        elif _score_global >= 60:
            _label_global = 'ganância'
        elif _score_global >= 45:
            _label_global = 'neutro'
        elif _score_global >= 30:
            _label_global = 'medo'
        else:
            _label_global = 'medo extremo'

    _col_fg1, _col_fg2, _col_fg3 = st.columns(3)

    def _renderizar_gauge(col, score, label, titulo):
        with col:
            st.markdown(
                f'<div style="text-align:center;margin-bottom:8px;">'
                f'<span style="font-family:Courier New;font-size:0.72rem;'
                f'color:#555;text-transform:uppercase;">{titulo}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            _cor_fg = "#00C853" if score >= 60 else ("#FF9900" if score >= 40 else "#FF1744")
            _fig_fg = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': label.upper(), 'font': {'size': 11, 'color': _cor_fg, 'family': 'Courier New'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickfont': {'size': 9, 'color': '#555'}},
                    'bar': {'color': _cor_fg, 'thickness': 0.25},
                    'bgcolor': '#0d0d0d', 'bordercolor': '#1e1e1e',
                    'steps': [
                        {'range': [0, 25], 'color': '#2a0005'},
                        {'range': [25, 45], 'color': '#1a0f00'},
                        {'range': [45, 55], 'color': '#111111'},
                        {'range': [55, 75], 'color': '#001a08'},
                        {'range': [75, 100], 'color': '#002a10'},
                    ],
                    'threshold': {'line': {'color': _cor_fg, 'width': 2}, 'thickness': 0.75, 'value': score},
                },
                number={'font': {'size': 32, 'color': _cor_fg, 'family': 'Courier New'}},
            ))
            _fig_fg.update_layout(height=220, paper_bgcolor='#0d0d0d', plot_bgcolor='#0d0d0d', margin=dict(l=20, r=20, t=30, b=10))
            st.plotly_chart(_fig_fg, use_container_width=True, config={'responsive': True})

    _renderizar_gauge(_col_fg1, _fg_eua.get('score', 50), _fg_eua.get('label', '—'), "🇺🇸 eua")
    _renderizar_gauge(_col_fg2, _fg_br.get('score', 50), _fg_br.get('label', '—'), "🇧🇷 brasil")
    _renderizar_gauge(_col_fg3, _score_global, _label_global, "🌍 global")

    st.caption(
        "eua: 7 componentes (momentum s&p500, vix, 52w, nasdaq/sp500, "
        "ouro, vix/vol.realizada, bitcoin). "
        "brasil: 7 componentes (momentum ibov, vix, 52w ibov, "
        "small/ibov, dólar, volume ibov). "
        "global: média ponderada 50% eua + 50% brasil."
    )

with tab_correlacoes:
    section_title("🔗 correlação dinâmica entre ativos")

    status_card(
        "como interpretar",
        "correlação próxima de +1: ativos se movem juntos (sem diversificação real). "
        "correlação próxima de 0: ativos independentes (boa diversificação). "
        "correlação próxima de -1: ativos se movem em direções opostas (hedge natural). "
        "a matriz usa a janela selecionada; o gráfico mostra como a correlação MUDA ao longo do tempo.",
        tipo="info",
    )

    # ── monta lista de tickers: watchlist do usuário + benchmarks ────────────
    from database.db import listar_watchlist, get_watchlist_padrao

    try:
        wl_id      = get_watchlist_padrao()
        watchlist  = listar_watchlist(watchlist_id=wl_id) if wl_id else []
        tickers_wl = [mapear_ticker_base(item['ticker']) for item in watchlist][:12]
    except Exception as _e_wl:
        logger.warning(f"[macro/correlações] erro ao buscar watchlist: {_e_wl}")
        tickers_wl = []

    benchmarks    = ['^BVSP', '^GSPC', 'BRL=X', 'GC=F']
    tickers_todos = list(dict.fromkeys(tickers_wl + benchmarks))

    # ── seletor de janela ────────────────────────────────────────────────────
    janela_corr = st.select_slider(
        "janela de correlação:",
        options=[21, 42, 60, 90, 126],
        value=60,
        format_func=lambda x: f"{x} dias (~{x // 21}m)",
        key="corr_janela",
    )

    with st.spinner("calculando correlações..."):
        corr_data = calcular_correlacoes(tuple(tickers_todos), janela=janela_corr)

    # ── heatmap da matriz ────────────────────────────────────────────────────
    if corr_data['matriz_atual'] is not None:
        matriz = corr_data['matriz_atual']

        fig_heat = go.Figure(go.Heatmap(
            z=matriz.values,
            x=matriz.columns.tolist(),
            y=matriz.index.tolist(),
            colorscale=[
                [0.0, '#FF1744'],   # -1: correlação inversa
                [0.5, '#111111'],   # 0:  neutro
                [1.0, '#00C853'],   # +1: correlação perfeita
            ],
            zmid=0,
            zmin=-1, zmax=1,
            text=matriz.values.round(2),
            texttemplate="%{text}",
            textfont={"size": 10, "color": "#E0E0E0", "family": "Courier New"},
            hoverongaps=False,
            showscale=True,
            colorbar=dict(
                tickfont=dict(color='#555', family='Courier New'),
                bordercolor='#333',
            ),
        ))

        layout_heat = base_layout(
            height=max(300, len(matriz) * 45),
            title=f"matriz de correlação — janela {janela_corr} dias",
        )
        fig_heat.update_layout(**layout_heat)
        fig_heat.update_xaxes(tickangle=45, tickfont=dict(size=9, family='Courier New'))
        fig_heat.update_yaxes(tickfont=dict(size=9, family='Courier New'))

        st.plotly_chart(fig_heat, use_container_width=True, config={'responsive': True})
        st.caption(
            f"correlação de pearson calculada sobre os últimos {janela_corr} pregões. "
            "diagonal principal sempre = 1. benchmarks: ^bvsp (ibovespa), ^gspc (s&p500), "
            "brl=x (dólar/brl), gc=f (ouro)."
        )

        # ── insights automáticos ─────────────────────────────────────────────
        section_title("🔍 insights de correlação")

        pares_alta  = []
        pares_baixa = []
        cols_m      = matriz.columns.tolist()

        for i in range(len(cols_m)):
            for j in range(i + 1, len(cols_m)):
                t1      = cols_m[i]
                t2      = cols_m[j]
                cor_val = float(matriz.iloc[i, j])
                if cor_val > 0.75:
                    pares_alta.append((t1, t2, cor_val))
                elif cor_val < 0.1:
                    pares_baixa.append((t1, t2, cor_val))

        if pares_alta:
            pares_str = ", ".join(
                [f"{t1}/{t2} ({v:.2f})" for t1, t2, v in
                 sorted(pares_alta, key=lambda x: -x[2])[:3]]
            )
            status_card(
                "⚠️ alta correlação detectada",
                f"{pares_str} — estes ativos se movem juntos. "
                "manter os dois pode não diversificar o risco da carteira.",
                tipo="amber",
            )

        if pares_baixa:
            pares_str = ", ".join(
                [f"{t1}/{t2} ({v:.2f})" for t1, t2, v in
                 sorted(pares_baixa, key=lambda x: abs(x[2]))[:3]]
            )
            status_card(
                "✅ boa diversificação detectada",
                f"{pares_str} — correlação baixa ou negativa. "
                "estes ativos oferecem diversificação real na carteira.",
                tipo="bull",
            )

        if not pares_alta and not pares_baixa:
            status_card(
                "correlações em zona moderada",
                "nenhum par com correlação extrema detectado nesta janela. "
                "carteira com nível de diversificação razoável.",
                tipo="muted",
            )

    else:
        empty_state(
            "🔗", "sem dados de correlação",
            "não foi possível calcular a matriz — verifique sua watchlist e conexão.",
        )

    # ── correlação rolante no tempo ──────────────────────────────────────────
    if corr_data['rolling_pairs']:
        section_title("📈 evolução da correlação ao longo do tempo")

        fig_roll = go.Figure()
        cores    = ["#FF9900", "#00B0FF", "#00C853", "#FF1744", "#E040FB", "#00BCD4"]

        for i, (par, serie) in enumerate(corr_data['rolling_pairs'].items()):
            fig_roll.add_trace(go.Scatter(
                x=serie.index,
                y=serie.values,
                name=par.lower(),
                line=dict(color=cores[i % len(cores)], width=1.5),
                hovertemplate=(
                    f"{par}<br>%{{x}}<br>correlação: %{{y:.2f}}<extra></extra>"
                ),
            ))

        fig_roll.add_hline(
            y=0.7,  line_color="#FF9900", line_dash="dash",  line_width=1,
            annotation_text="alta correlação (0.7)",
            annotation_font=dict(color="#FF9900", family="Courier New", size=10),
        )
        fig_roll.add_hline(
            y=0,    line_color="#333333", line_dash="dot",   line_width=1,
        )
        fig_roll.add_hline(
            y=-0.7, line_color="#00B0FF", line_dash="dash",  line_width=1,
            annotation_text="correlação inversa (-0.7)",
            annotation_font=dict(color="#00B0FF", family="Courier New", size=10),
        )

        layout_roll = base_layout(
            height=350,
            title=f"correlação rolante {janela_corr} dias — ativos vs benchmarks",
        )
        layout_roll.update({
            'yaxis': {'range': [-1.1, 1.1], 'title': 'correlação',
                      'gridcolor': '#1e1e1e', 'showgrid': True},
        })
        fig_roll.update_layout(**layout_roll)
        st.plotly_chart(fig_roll, use_container_width=True, config={'responsive': True})
        st.caption(
            "cada linha representa a correlação rolante entre um ativo da watchlist "
            "e seu benchmark natural (ativos .SA vs ibovespa; ativos globais vs s&p500). "
            f"janela móvel de {janela_corr} pregões."
        )