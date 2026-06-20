import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from bcb import sgs
from fredapi import Fred
import yfinance as yf
import datetime
import time

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label, mapear_ticker_base
from utils.logger import get_logger

logger = get_logger(__name__)

# componentes do design system (camada 2 e 4)
from utils.components import (
    page_header, section_title, metric_card, status_card, empty_state,
    inject_keyboard_shortcuts, auto_refresh_indicator, tooltip,
    label_com_tooltip, topbar, hero_macro, kpi_index_row, info_box,
)
from utils.ai_client import chamar_ia, SYSTEM_MACRO
from utils.fmp_client import get_earnings_calendar as _fmp_earnings_calendar
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout, chart_type_toggle, _cores as _chart_cores
from utils.macro_context import garantir_macro_context
from utils.macro_regime import classificar_regime, get_impacto_setor
from utils.regime_classifier import classificar_regime_do_macro_context
from utils.macro_supabase import (
    carregar_fear_greed, salvar_fear_greed,
    carregar_snapshot, salvar_snapshot,
    buscar_slope_curva,
)

# 1. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()
try:
    from utils.themes import render_theme_switcher_sidebar
    render_theme_switcher_sidebar()
except Exception:
    pass
garantir_macro_context()

_user_top_macro = get_current_user() or {}
topbar(
    breadcrumb_itens=[("⚡ finterminal", "/"), ("macro", None)],
    user_name=_user_top_macro.get('username', '') or _user_top_macro.get('nome', '') or 'usuário',
    sync_label="ao vivo",
)
page_header("🌍 ambiente macroeconómico", "monitoramento de juros, inflação, atividade e apetite ao risco global.")

if "FRED_API_KEY" not in st.secrets:
    info_box(
        tipo   = "amber",
        titulo = "aviso de arquitetura",
        texto  = "chave da api do FRED não foi encontrada em secrets.toml. sem ela, dados dos EUA e risco global ficarão indisponíveis.",
        icone  = "⚠",
    )

# ── Regime Macro — classificador automático ──────────────────────────────────
section_title("regime macro — classificador automático")

@st.cache_data(ttl=3600, show_spinner=False)
def _regime_macro_cached():
    """
    Cache 1h. O classificador faz 4-5 chamadas yfinance em sequência
    (^TNX, ^VIX, ^IRX, SPY, ^BVSP). Sem cache, cada render da página
    dispara todas elas — lento e arrisca rate limit.
    """
    return classificar_regime_do_macro_context()

try:
    _regime = _regime_macro_cached()
    # Mapeia fase do regime → tom do hero_macro
    _tom_regime = {
        "expansao":  "bull",
        "pico":      "amber",
        "contracao": "accent",
        "vale":      "bear",
    }.get(_regime.fase, "amber")

    # Converte sinais (dict) em lista de tuplas (nome, status, tipo, valor)
    _sinais_lst = []
    for k, v in _regime.sinais.items():
        if v is True:
            _status, _tipo, _val = "ativo", "bull", "✓"
        elif v is False:
            _status, _tipo, _val = "ausente", "bear", "✗"
        else:
            _status, _tipo, _val = "indef.", "amber", "—"
        _sinais_lst.append((k, _status, _tipo, _val))

    hero_macro(
        score      = int(_regime.probabilidade * 100),
        label      = _regime.fase.upper(),
        descricao  = _regime.leitura,
        tom        = _tom_regime,
        sinais     = _sinais_lst,
    )
except Exception as e:
    info_box(
        tipo   = "amber",
        titulo = "classificador de regime indisponível",
        texto  = str(e),
        icone  = "⚠",
    )

# ==========================================
# funções globais de cache e apoio
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def puxar_historico_mestre():
    """
    Busca séries históricas macro (BCB Brasil + FRED Global + yfinance Commodities).

    Padrão cache-first com fallback live:
      1. Tenta carregar snapshot recente do Supabase (< 6h)
      2. Se cache válido → retorna imediatamente (evita APIs lentas)
      3. Se cache expirado/ausente → chama APIs ao vivo → salva novo snapshot
         (resolve "sem dados" em fins de semana, cold-start, manutenção BCB/FRED)

    TTL: 1h (st.cache_data) + 6h (Supabase) — cache entre sessões e deploys.
    """
    from utils.macro_supabase import salvar_snapshot, carregar_snapshot

    hoje      = datetime.datetime.today()
    inicio_10a = hoje - datetime.timedelta(days=365 * 10)

    MAX_CACHE_HORAS = 6  # horas de validade do cache Supabase

    # ── 1. Brasil — BCB SGS ───────────────────────────────────────────────────
    df_br = None
    # Cache-first: tenta carregar do Supabase
    _cache_br = carregar_snapshot("bcb_br", max_age_days=MAX_CACHE_HORAS / 24)
    if _cache_br is not None and not _cache_br.empty:
        df_br = _cache_br
        logger.info("[macro] BCB: servindo do cache Supabase (cache-first).")
    else:
        # Cache miss → busca ao vivo
        series_bcb = {
            'Selic':            432,
            'IPCA':             433,
            'Dolar':            1,
            'Desemprego':       24369,
            'Divida_Bruta_PIB': 13762,
            'Result_Primario':  5793,
            'Result_Nominal':   4192,
        }
        dfs_br_dict = {}
        for nome, codigo in series_bcb.items():
            try:
                df_temp = sgs.get({nome: codigo}, start=inicio_10a)
                if not df_temp.empty:
                    dfs_br_dict[nome] = df_temp[nome]
            except Exception as e:
                logger.error(f"[macro] BCB série '{nome}' (código {codigo}) falhou: {e}")

        # Fallback Selic: série 432 → 439
        if 'Selic' not in dfs_br_dict:
            try:
                _selic_fb = sgs.get({'Selic': 439}, start=inicio_10a)
                if not _selic_fb.empty:
                    dfs_br_dict['Selic'] = _selic_fb['Selic']
            except Exception as e:
                logger.error(f"[macro] BCB Selic fallback (série 439) falhou: {e}")

        df_br = pd.DataFrame(dfs_br_dict) if dfs_br_dict else pd.DataFrame()

        # Calcula IPCA acumulado 12m
        if not df_br.empty and 'IPCA' in df_br.columns:
            try:
                _ipca_raw = df_br['IPCA'].dropna()
                df_br['IPCA_12M'] = ((1 + _ipca_raw / 100)
                                     .rolling(12)
                                     .apply(lambda x: x.prod(), raw=True) - 1) * 100
            except Exception:
                pass

        if not df_br.empty:
            salvar_snapshot("bcb_br", df_br)
            logger.info("[macro] BCB: dados ao vivo OK, snapshot Supabase atualizado.")
        else:
            # Live API failed → emergency fallback to stale cache (up to 7 days)
            _stale = carregar_snapshot("bcb_br", max_age_days=7)
            if _stale is not None and not _stale.empty:
                df_br = _stale
                logger.warning("[macro] BCB: servindo cache expirado (fallback emergencial).")
            else:
                logger.error("[macro] BCB: sem dados ao vivo e sem snapshot Supabase disponível.")

    # ── 2. Global — FRED ─────────────────────────────────────────────────────
    df_global = pd.DataFrame()
    # Cache-first: tenta carregar do Supabase. Valida que colunas críticas
    # estão presentes — snapshots antigos podem ter sido salvos sem CPIAUCSL
    # quando a série ainda não estava no series_fred, e o cache de 6h
    # mantinha o snapshot incompleto servindo até expirar.
    _cache_global = carregar_snapshot("fred_global", max_age_days=MAX_CACHE_HORAS / 24)
    _cache_ok = (
        _cache_global is not None
        and not _cache_global.empty
        and "CPIAUCSL" in _cache_global.columns
        and not _cache_global["CPIAUCSL"].dropna().empty
    )
    if _cache_ok:
        df_global = _cache_global
        logger.info("[macro] FRED: servindo do cache Supabase (cache-first).")
    elif _cache_global is not None and not _cache_global.empty:
        logger.warning(
            "[macro] FRED: snapshot Supabase incompleto (sem CPIAUCSL) — "
            "forçando refetch ao vivo."
        )

    if df_global.empty and "FRED_API_KEY" in st.secrets:
        try:
            fred = Fred(api_key=st.secrets["FRED_API_KEY"])
            try:
                fred.get_series_info('FEDFUNDS')
            except Exception as e:
                logger.error(f"[macro] Chave FRED API parece inválida: {e}")
                return df_br, df_global, pd.DataFrame()

            series_fred = {
                'FEDFUNDS': 'FEDFUNDS', 'CPIAUCSL': 'CPIAUCSL', 'UNRATE': 'UNRATE',
                'DGS10': 'DGS10', 'DGS2': 'DGS2', 'DGS3MO': 'DGS3MO', 'VIXCLS': 'VIXCLS',
                'ECBDFR': 'ECBDFR', 'IRLTLT01EZM156N': 'IRLTLT01EZM156N',
                'IRLTLT01JPM156N': 'IRLTLT01JPM156N',
                'T10Y2Y': 'T10Y2Y', 'BAMLH0A0HYM2': 'BAMLH0A0HYM2',
                'GFDEGDQ188S': 'GFDEGDQ188S', 'MTSDS133FMS': 'MTSDS133FMS',
                'CP0000EZ19M086NEST': 'CP0000EZ19M086NEST',
                'LRHUTTTTEZM156S': 'LRHUTTTTEZM156S',
                'IRLTLT01DEM156N': 'IRLTLT01DEM156N', 'IRLTLT01ITM156N': 'IRLTLT01ITM156N',
                'IRSTCB01JPM156N': 'IRSTCB01JPM156N', 'CHNCPIALLMINMEI': 'CHNCPIALLMINMEI',
            }
            dfs_global_dict = {}
            for nome, serie_id in series_fred.items():
                try:
                    dfs_global_dict[nome] = fred.get_series(
                        serie_id, observation_start=inicio_10a
                    )
                except Exception as e:
                    logger.error(f"[macro] FRED série '{serie_id}' ({nome}) falhou: {e}")
                time.sleep(1)

            df_global = pd.DataFrame(dfs_global_dict)
            if 'CPIAUCSL' in df_global.columns:
                # Mesma lógica do recálculo abaixo: dropna ANTES do pct_change
                # porque o merge cria índice diário e CPIAUCSL é mensal/esparsa.
                _cpi_m = df_global['CPIAUCSL'].dropna()
                if len(_cpi_m) >= 2:
                    _mom = _cpi_m.pct_change(fill_method=None) * 100
                    df_global['CPI_MoM'] = _mom.reindex(df_global.index)
                if len(_cpi_m) >= 13:
                    _yoy = _cpi_m.pct_change(12, fill_method=None) * 100
                    df_global['CPI_YOY'] = _yoy.reindex(df_global.index)

            if not df_global.empty:
                salvar_snapshot("fred_global", df_global)
                logger.info("[macro] FRED: dados ao vivo OK, snapshot Supabase atualizado.")
            else:
                # Live API failed → emergency fallback to stale cache (up to 7 days)
                _stale_g = carregar_snapshot("fred_global", max_age_days=7)
                if _stale_g is not None and not _stale_g.empty:
                    df_global = _stale_g
                    logger.warning("[macro] FRED: servindo cache expirado (fallback emergencial).")
                else:
                    logger.warning("[macro] FRED: nenhuma série carregada e sem cache disponível.")

        except Exception as e:
            logger.exception(f"[macro] Bloco FRED inteiro falhou: {e}")
            # Emergency fallback
            _stale_ge = carregar_snapshot("fred_global", max_age_days=7)
            if _stale_ge is not None and not _stale_ge.empty:
                df_global = _stale_ge
                logger.warning("[macro] FRED: servindo cache expirado após exceção.")

    # ── 3. Commodities — yfinance (cache-first) ────────────────────────────────
    df_commodities = pd.DataFrame()
    try:
        # Cache-first: tenta Supabase (6h TTL), senão baixa live
        _cached_comm = carregar_snapshot("commodities_yf", max_age_days=1)
        if _cached_comm is not None and not _cached_comm.empty:
            df_commodities = _cached_comm
            logger.info("[macro] commodities: servindo do cache Supabase.")
        else:
            df_commodities = yf.download(
                ['CL=F', 'GC=F'], start=inicio_10a, progress=False
            )['Close']
            if isinstance(df_commodities, pd.Series):
                df_commodities = df_commodities.to_frame()
            if not df_commodities.empty:
                salvar_snapshot("commodities_yf", df_commodities)
    except Exception as e:
        logger.error(f"[macro] Download de commodities falhou: {e}")

    return df_br, df_global, df_commodities

def valor_atual_seguro(df, coluna):
    if not df.empty and coluna in df.columns and not df[coluna].dropna().empty:
        return df[coluna].dropna().iloc[-1]
    return None

def criar_grafico_macro(df, coluna_y, titulo, cor_linha, tipo: str = "linha"):
    """Gráfico macro com suporte a linha ou barras (tipo = 'linha'|'barras')."""
    layout = base_layout(height=280, title=titulo)
    if df.empty or coluna_y not in df.columns or df[coluna_y].dropna().empty:
        fig = px.line()
        fig.add_annotation(text=f"sem dados: {titulo}", x=0.5, y=0.5, showarrow=False, font=dict(color=_chart_cores()["bear"], size=14))
        layout['xaxis'] = dict(visible=False)
        layout['yaxis'] = dict(visible=False)
        fig.update_layout(**layout)
        return fig
    df_plot = df.dropna(subset=[coluna_y])
    if tipo == "barras":
        fig = go.Figure(go.Bar(
            x=df_plot.index, y=df_plot[coluna_y],
            marker_color=cor_linha,
            hovertemplate="%{x}<br><b>%{y:.2f}</b><extra></extra>",
        ))
    else:
        fig = px.line(df_plot, x=df_plot.index, y=coluna_y)
        fig.update_traces(line_color=cor_linha, line_width=1.5)
    fig.update_layout(**layout)
    return fig

def _hex_to_rgba(hex_color: str, alpha: float = 0.08) -> str:
    h = hex_color.lstrip('#')
    return f'rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})'

def tooltip_info(texto):
    """HTML snippet for a hover-info icon. Use with st.markdown(..., unsafe_allow_html=True)."""
    _texto_escaped = texto.replace('"', '&quot;')
    return f"""<span style="cursor:help; border-bottom:1px dashed var(--text-muted); font-size:0.85em; color:var(--text-muted);" title="{_texto_escaped}">&#9432;</span>"""


# ── Calendário COPOM oficial (atualizar anualmente) ───────────────────────────
_COPOM_CALENDAR = {
    # 2025 — datas publicadas pelo BCB
    "1/2025": datetime.date(2025, 1, 29),
    "2/2025": datetime.date(2025, 3, 19),
    "3/2025": datetime.date(2025, 5,  7),
    "4/2025": datetime.date(2025, 6, 18),
    "5/2025": datetime.date(2025, 7, 30),
    "6/2025": datetime.date(2025, 9, 17),
    "7/2025": datetime.date(2025, 10, 29),
    "8/2025": datetime.date(2025, 12, 10),
    # 2026 — estimados pela cadência histórica (~6-8 semanas de intervalo)
    "1/2026": datetime.date(2026, 1, 28),
    "2/2026": datetime.date(2026, 3, 18),
    "3/2026": datetime.date(2026, 5,  6),
    "4/2026": datetime.date(2026, 6, 17),
    "5/2026": datetime.date(2026, 7, 29),
    "6/2026": datetime.date(2026, 9, 16),
    "7/2026": datetime.date(2026, 10, 28),
    "8/2026": datetime.date(2026, 12,  9),
}


@st.cache_data(ttl=3600, show_spinner=False)
def puxar_curva_di():
    """
    Constrói a curva DI brasileira (implied forward SELIC) via Focus/BCB.

    Abordagem 1 (preferida): ExpectativasMercadoSelic por reunião COPOM
      → cada ponto da curva = expectativa de SELIC na reunião N do COPOM
      → mapeia o número da reunião para a data aproximada via _COPOM_CALENDAR
      → retorna a curva com a granularidade de cada decisão do BCB

    Abordagem 2 (fallback): ExpectativasMercadoAnuais
      → pontos anuais (dez/2025, dez/2026...) via consensus do Focus

    Retorna:
      (df_curve, tipo, df_historico) onde:
        df_curve: DataFrame com [tenor_dias, tenor_label, selic_mediana, selic_media]
        tipo: 'copom' | 'anual' | None
        df_historico: DataFrame com curvas históricas [data, tenor_label, selic_mediana]
    """
    try:
        from bcb import Expectativas

        em      = Expectativas()
        hoje    = datetime.date.today()
        cutoff  = (hoje - datetime.timedelta(days=10)).isoformat()
        cutoff_hist = (hoje - datetime.timedelta(days=180)).isoformat()

        # ── Abordagem 1: por reunião COPOM ────────────────────────────────
        try:
            ep_sel = em.get_endpoint('ExpectativasMercadoSelic')
            df_sel = (
                ep_sel.query()
                .filter(ep_sel.baseCalculo == 0)   # % ao ano
                .filter(ep_sel.Data >= cutoff)
                .collect()
            )
            if df_sel is not None and not df_sel.empty:
                latest_date = df_sel['Data'].max()
                df_latest   = df_sel[df_sel['Data'] == latest_date].copy()

                # Curva do dia mais recente
                pontos = []
                for _, row in df_latest.iterrows():
                    reuniao = str(row.get('reuniao', '')).strip()
                    if reuniao in _COPOM_CALENDAR:
                        dt_cop = _COPOM_CALENDAR[reuniao]
                        dias   = (dt_cop - hoje).days
                        if dias > 0:
                            pontos.append({
                                'tenor_dias':    dias,
                                'tenor_label':   reuniao,
                                'selic_mediana': row.get('Mediana'),
                                'selic_media':   row.get('Media'),
                                'n_respondentes': row.get('numeroRespondentes', 0),
                            })

                if len(pontos) >= 3:
                    df_curve = pd.DataFrame(pontos).sort_values('tenor_dias').reset_index(drop=True)

                    # Histórico: curvas de 30d e 90d atrás para comparação
                    df_hist_list = []
                    for lookback_days, lbl in [(30, "30d atrás"), (90, "90d atrás")]:
                        _dt = (hoje - datetime.timedelta(days=lookback_days)).isoformat()
                        _dt_from = (hoje - datetime.timedelta(days=lookback_days + 10)).isoformat()
                        try:
                            _df_lb = (
                                ep_sel.query()
                                .filter(ep_sel.baseCalculo == 0)
                                .filter(ep_sel.Data >= _dt_from)
                                .filter(ep_sel.Data <= _dt)
                                .collect()
                            )
                            if _df_lb is not None and not _df_lb.empty:
                                _ld = _df_lb['Data'].max()
                                _df_lb = _df_lb[_df_lb['Data'] == _ld]
                                for _, _r in _df_lb.iterrows():
                                    _reun = str(_r.get('reuniao', '')).strip()
                                    if _reun in _COPOM_CALENDAR:
                                        _dt_c = _COPOM_CALENDAR[_reun]
                                        _d = (hoje - _dt_c).days  # dias desde então
                                        df_hist_list.append({
                                            'curva':         lbl,
                                            'tenor_label':   _reun,
                                            'selic_mediana': _r.get('Mediana'),
                                            'tenor_dias_orig': (_dt_c - hoje).days,
                                        })
                        except Exception:
                            pass

                    df_historico = pd.DataFrame(df_hist_list) if df_hist_list else pd.DataFrame()
                    return df_curve, 'copom', df_historico

        except Exception as _e:
            logger.warning(f"[curva_di] ExpectativasMercadoSelic falhou: {_e}")

        # ── Abordagem 2: expectativas anuais ──────────────────────────────
        ep_anual = em.get_endpoint('ExpectativasMercadoAnuais')
        df_anual = (
            ep_anual.query()
            .filter(ep_anual.Indicador == 'Selic')
            .filter(ep_anual.Data >= cutoff)
            .collect()
        )
        if df_anual is not None and not df_anual.empty:
            latest_date = df_anual['Data'].max()
            df_l = df_anual[df_anual['Data'] == latest_date].sort_values('DataReferencia').copy()
            pontos = []
            for _, row in df_l.iterrows():
                try:
                    ano = int(str(row.get('DataReferencia', ''))[:4])
                    dt_ref = datetime.date(ano, 12, 31)
                    dias = (dt_ref - hoje).days
                    if dias > 0:
                        pontos.append({
                            'tenor_dias':    dias,
                            'tenor_label':   f"dez/{ano}",
                            'selic_mediana': row.get('Mediana'),
                            'selic_media':   row.get('Media'),
                            'n_respondentes': row.get('numeroRespondentes', 0),
                        })
                except Exception:
                    pass
            if len(pontos) >= 2:
                df_curve = pd.DataFrame(pontos).sort_values('tenor_dias').reset_index(drop=True)
                return df_curve, 'anual', pd.DataFrame()

        return None, None, pd.DataFrame()

    except Exception as e:
        logger.error(f"[curva_di] Erro geral: {e}")
        return None, None, pd.DataFrame()

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
                
                st.markdown(f'<div class="card" style="padding:10px; border-left:3px solid var(--info); margin-bottom: 8px;"><div style="font-family:var(--font-ui,sans-serif); font-size:0.7em; color:var(--text-muted);">{publisher.lower()}</div><a href="{link}" target="_blank" style="text-decoration:none; color:var(--text-primary); font-family:var(--font-ui,sans-serif); font-size:0.85rem;">{titulo.lower()}</a></div>', unsafe_allow_html=True)
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
        return "🔴 contração / recessão", "var(--bear)", "utilities (xlu), saúde (xlv), cons. básico (xlp)"
    if t10y2y < 0.3 and vix < 20 and (hy_spread is not None and hy_spread < 4.5):
        return "🟡 recuperação (early cycle)", "var(--amber)", "financeiro (xlf), indústria (xli), cons. discric. (xly)"
    if 0.3 <= t10y2y < 1.0 and vix < 18:
        return "🟢 expansão (mid cycle)", "var(--bull)", "tecnologia (xlk), indústria (xli), energia (xle)"
    if t10y2y >= 1.0 and vix < 20:
        return "🟡 pico de ciclo (late cycle)", "var(--amber)", "energia (xle), materiais (xlb), saúde (xlv)"
    return "⚪ transição", "#888888", "posicionamento neutro — aguardar confirmação"


def _render_evento_card(evento: dict, key_prefix: str = "ev"):
    """Renderiza um card de evento (macro ou earnings) no calendário."""
    # Macro events: evento, data (datetime), categoria, impacto, detalhe
    # Earnings events: ticker, data (str), eps_est, hora, surpresa
    is_earnings = "ticker" in evento and "evento" not in evento

    if is_earnings:
        ticker = evento.get("ticker", "—")
        data_str = evento.get("data", "")
        hora = evento.get("hora", "amc")
        eps = evento.get("eps_est")
        surpresa = evento.get("surpresa")

        label = f"📊 {ticker}"
        detalhe = f"eps est: {eps}" if eps else ""
        if surpresa is not None:
            detalhe += f" | surpresa: {surpresa:+.1f}%"
        hora_label = "após fechamento" if hora == "amc" else "pré-mercado"

        with st.container():
            cols = st.columns([5, 1])
            with cols[0]:
                st.markdown(
                    f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
                    f'border-left:3px solid #FF9900;border-radius:4px;padding:8px 12px;margin-bottom:4px;">'
                    f'<span style="font-size:0.85rem;font-weight:600;">{label}</span>'
                    f'<span style="font-size:0.72rem;color:var(--text-muted);margin-left:8px;">{detalhe}</span>'
                    f'</div>', unsafe_allow_html=True
                )
            with cols[1]:
                st.caption(f"{data_str}\n{hora_label}")
    else:
        nome = evento.get("evento", "—")
        cat = evento.get("categoria", "")
        impacto = evento.get("impacto", "baixo")
        detalhe = evento.get("detalhe", "")
        data_raw = evento.get("data")
        data_str = data_raw.strftime("%d/%m") if hasattr(data_raw, "strftime") else str(data_raw)

        cor_cat = {"brasil": "#009C3B", "eua": "#3C3B6E"}.get(cat, "#555")
        icone_imp = {"alto": "🔴", "medio": "🟡", "baixo": "🟢"}.get(impacto, "⚪")
        label_cat = {"brasil": "BR", "eua": "EUA"}.get(cat, cat.upper())

        with st.container():
            cols = st.columns([5, 1])
            with cols[0]:
                texto = f"{nome}"
                if detalhe:
                    texto += f" | {detalhe}"
                st.markdown(
                    f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
                    f'border-left:3px solid {cor_cat};border-radius:4px;padding:8px 12px;margin-bottom:4px;">'
                    f'<span style="font-size:0.7rem;color:{cor_cat};font-weight:bold;text-transform:uppercase;">{label_cat}</span>'
                    f'<span style="font-size:0.8rem;margin-left:6px;">{texto}</span>'
                    f'</div>', unsafe_allow_html=True
                )
            with cols[1]:
                st.markdown(f"<div style='text-align:right;'>{data_str} {icone_imp}</div>", unsafe_allow_html=True)


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


def buscar_earnings_calendario(tickers_tuple: tuple | None = None, data_fim_str: str | None = None) -> list[dict]:
    """
    Busca earnings dates via FMP para uma lista de tickers.
    Substitui a versão yfinance que quebra no yfinance >=1.3.0
    (.calendar retorna dict em vez de DataFrame).
    """
    hoje = datetime.date.today()
    fim  = data_fim_str or (hoje + datetime.timedelta(days=90)).strftime("%Y-%m-%d")

    fmp_eventos = _fmp_earnings_calendar(
        tickers     = list(tickers_tuple) if tickers_tuple else None,
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
            "data":      data_ev.strftime("%Y-%m-%d"),
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
        
        col_espaco, col_btn, col_filtro = st.columns([5, 2, 3])
        with col_btn:
            if st.button("🔄 recarregar dados", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        with col_filtro:
            janela = st.radio("horizonte de tempo:", ["3 anos", "5 anos", "10 anos"], index=1, horizontal=True, label_visibility="collapsed")
            
        anos_filtro = int(janela.split()[0])
        data_corte = datetime.datetime.today() - datetime.timedelta(days=365 * anos_filtro)
        
        df_br = df_br_master[df_br_master.index >= data_corte] if not df_br_master.empty else df_br_master
        df_global = df_global_master[df_global_master.index >= data_corte] if not df_global_master.empty else df_global_master

        if df_global_master.empty:
            st.warning(
                "⚠️ **dados globais (fred) indisponíveis.** "
                "os indicadores dos eua, europa/ásia e risco não serão exibidos. "
                "causas possíveis: chave de api inválida/expirada, "
                "limite de requisições excedido ou falha de rede. "
                "tente clicar em \"recarregar dados\" acima."
            )

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
            # Sanidade: série 432/439 = % anual. Se < 1, veio como decimal
            if 0 < _selic_val < 1:
                _selic_val = _selic_val * 100
            elif _selic_val > 50:
                _selic_val = 10.75
            _ipca_val  = float(_ipca_ss)  if _ipca_ss  is not None else st.session_state.get("macro_context", {}).get("ipca", 4.5)
            if abs(_ipca_val) > 5:
                _ipca_val = 0.45
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
            _macro_tipo = chart_type_toggle(key="macro_br", default="linha")
            c1, c2, c3, c4 = st.columns(4)
            v_selic = valor_atual_seguro(df_br, 'Selic')
            v_ipca_m = valor_atual_seguro(df_br, 'IPCA')
            v_dolar = valor_atual_seguro(df_br, 'Dolar')
            v_desemp = valor_atual_seguro(df_br, 'Desemprego')

            # Fallback live para Selic: snapshot pode estar com a coluna ausente
            # após mudanças no schema. Tenta BCB SGS 432, depois 439.
            if v_selic is None:
                try:
                    _ini_fb = (datetime.datetime.today() - datetime.timedelta(days=60)).strftime('%Y-%m-%d')
                    _selic_live = sgs.get({'Selic': 432}, start=_ini_fb)
                    if _selic_live.empty:
                        _selic_live = sgs.get({'Selic': 439}, start=_ini_fb)
                    if not _selic_live.empty:
                        v_selic = float(_selic_live['Selic'].dropna().iloc[-1])
                        logger.info(f"[macro] Selic fallback BCB live: {v_selic}%")
                except Exception as e:
                    logger.warning(f"[macro] fallback Selic BCB falhou: {e}")

            # Calcula IPCA acumulado 12 meses
            _ipca_12m = None
            if 'IPCA' in df_br.columns:
                _ipca_mensal = df_br['IPCA'].dropna() / 100
                _ipca_roll = (1 + _ipca_mensal).rolling(12).apply(lambda x: x.prod() - 1, raw=True) * 100
                df_br['IPCA_12M'] = _ipca_roll
                _ipca_12m = valor_atual_seguro(df_br, 'IPCA_12M')

            # KPIs Brasil (design system v5)
            from utils.components import portfolio_kpis as _pf_kpis_br
            _ipca_val = _ipca_12m or v_ipca_m
            _selic_tone = (
                "bear" if (v_selic and v_selic > 13)
                else "amber" if (v_selic and v_selic > 10)
                else "bull"
            )
            _ipca_tone = (
                "bear" if (_ipca_val and _ipca_val > 6)
                else "amber" if (_ipca_val and _ipca_val > 4.5)
                else "bull"
            )
            _desemp_tone = (
                "bear" if (v_desemp and v_desemp > 10)
                else "amber" if (v_desemp and v_desemp > 7)
                else "bull"
            )
            _pf_kpis_br([
                {
                    "nome":     "selic atual",
                    "valor":    fmt_pct(v_selic, sinal=False),
                    "sublabel": "taxa básica de juros",
                    "tone":     _selic_tone,
                    "icone":    "🏛",
                },
                {
                    "nome":     "ipca 12m",
                    "valor":    fmt_pct(_ipca_val, sinal=False),
                    "sublabel": "inflação acumulada",
                    "tone":     _ipca_tone,
                    "icone":    "📊",
                },
                {
                    "nome":     "dólar (ptax)",
                    "valor":    fmt_preco(v_dolar, "r$"),
                    "sublabel": "câmbio comercial",
                    "tone":     "info",
                    "icone":    "💵",
                },
                {
                    "nome":     "desemprego",
                    "valor":    fmt_pct(v_desemp, sinal=False),
                    "sublabel": "taxa pnad contínua",
                    "tone":     _desemp_tone,
                    "icone":    "👥",
                },
            ])
            tooltip("selic")
            tooltip("ipca")
            
            st.markdown(tooltip_info("Selic — taxa básica de juros definida pelo Copom. Impacta diretamente renda fixa, crédito e atividade econômica."), unsafe_allow_html=True)
            # ── SELIC REAL (ex-post) ──────────────────────────────────────────
            _selic_real = None
            if v_selic is not None and _ipca_12m is not None:
                _sr = float(v_selic) - float(_ipca_12m)
                if abs(_sr) < 30:
                    _selic_real = round(_sr, 2)

            # Adiciona coluna de SELIC real no df para uso nos gráficos
            if 'Selic' in df_br.columns and 'IPCA_12M' in df_br.columns:
                df_br['Selic_Real'] = (df_br['Selic'] - df_br['IPCA_12M']).clip(-10, 25)

            # Linha extra de métricas
            m1, m2, m3 = st.columns(3)
            with m1:
                if _selic_real is not None:
                    metric_card(
                        "selic real (ex-post)",
                        fmt_pct(_selic_real, sinal=True),
                        "selic − ipca 12m acum.",
                        "bear" if _selic_real > 8 else "amber" if _selic_real > 5 else "bull",
                    )
                else:
                    metric_card("selic real", "n/d", "dados insuficientes")
            with m2:
                if _selic_real is not None:
                    _regr = (
                        "juros reais restritivos — crédito caro, consumo/investimento pressionados"
                        if _selic_real > 8
                        else "zona neutra — política monetária equilibrada"
                        if _selic_real > 4
                        else "estimulativo — favorece consumo e ações domésticas"
                    )
                    metric_card("regime monetário", "restritivo" if _selic_real > 8 else "neutro" if _selic_real > 4 else "estimulativo", _regr, "bear" if _selic_real > 8 else "amber" if _selic_real > 4 else "bull")
            with m3:
                # Prêmio de risco implícito: quanto a renda fixa paga vs o risco
                if v_selic is not None:
                    metric_card(
                        "carry brasil",
                        fmt_pct(v_selic, sinal=False),
                        "taxa bruta que o brasil paga ao mundo",
                        "amber",
                    )

            st.markdown("<br>", unsafe_allow_html=True)

            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(criar_grafico_macro(df_br, 'Selic', "taxa selic histórica (%)", _chart_cores()["bull"], _macro_tipo), use_container_width=True, config={'responsive': True})
                st.caption(
                    "selic é a taxa básica de juros definida pelo copom (banco central do brasil). "
                    "impacta diretamente o custo do crédito, a rentabilidade da renda fixa e o "
                    "valuation das ações. quando a selic real (selic − ipca) supera 8%, os múltiplos "
                    "p/l do ibovespa tendem a comprimir — renda fixa concorre com equities. "
                    "leitura: a trajetória importa mais do que o nível absoluto — ciclo de corte = "
                    "vento favorável para bolsa; ciclo de alta = rotação para crédito e renda fixa."
                )
            with g2:
                if 'IPCA_12M' in df_br.columns and not df_br['IPCA_12M'].dropna().empty:
                    _fig_ipca = go.Figure()
                    _fig_ipca.add_trace(go.Scatter(
                        x=df_br.index, y=df_br['IPCA_12M'].dropna(),
                        name='IPCA acum. 12m',
                        line=dict(color='#00B0FF', width=2),
                        hovertemplate='%{x}<br>IPCA 12m: %{y:.2f}%<extra></extra>',
                    ))
                    _cc_ipca = _chart_cores()
                    _fig_ipca.add_hline(y=3.0, line_color=_cc_ipca["bull"], line_dash='dash', line_width=1,
                                        annotation_text='meta 3%', annotation_font_color=_cc_ipca["bull"], annotation_font_size=9)
                    _fig_ipca.add_hline(y=4.5, line_color=_cc_ipca["amber"], line_dash='dot', line_width=1,
                                        annotation_text='teto 4.5%', annotation_font_color=_cc_ipca["amber"], annotation_font_size=9)
                    _fig_ipca.update_layout(**base_layout(height=300, title='inflação acumulada 12 meses — ipca (%)'))
                    st.plotly_chart(_fig_ipca, use_container_width=True, config={'responsive': True})
                    st.caption("ipca acumulado dos últimos 12 meses (produto das taxas mensais). meta bcb: 3% ± 1.5pp. fonte: bcb sgs série 433.")
                else:
                    st.plotly_chart(criar_grafico_macro(df_br, 'IPCA', "inflação mensal ipca (%)", "#00B0FF"), use_container_width=True, config={'responsive': True})
            # ── CURVA DI BRASILEIRA ───────────────────────────────────────────
            st.markdown("---")
            section_title("📈 curva di — expectativas de selic pelo mercado (focus/bcb)")

            with st.spinner("carregando expectativas de selic..."):
                _di_curve, _di_tipo, _di_hist = puxar_curva_di()

            if _di_curve is not None and not _di_curve.empty and v_selic is not None:
                # ── métricas da curva ─────────────────────────────────────────
                _di_spot       = float(v_selic)
                _di_ultimo     = float(_di_curve['selic_mediana'].dropna().iloc[-1])
                _di_primeiro   = float(_di_curve['selic_mediana'].dropna().iloc[0])
                _di_slope      = _di_ultimo - _di_spot   # inclinação total curva
                _di_next       = float(_di_curve['selic_mediana'].dropna().iloc[0])
                _di_next_lbl   = _di_curve['tenor_label'].iloc[0]

                _implied_move  = _di_next - _di_spot
                _move_str      = f"{_implied_move:+.2f}pp" if abs(_implied_move) > 0.05 else "sem movimento esperado"
                _move_cor      = "bear" if _implied_move > 0.1 else "bull" if _implied_move < -0.1 else "amber"

                _shape = (
                    "📉 curva inclinada p/ baixo — mercado precifica ciclo de cortes"
                    if _di_slope < -0.5
                    else "📈 curva inclinada p/ cima — mercado precifica aperto monetário"
                    if _di_slope > 0.5
                    else "➡️ curva flat — selic esperada estável no horizonte"
                )
                _shape_cor = "bull" if _di_slope < -0.5 else "bear" if _di_slope > 0.5 else "amber"

                _cd1, _cd2, _cd3, _cd4 = st.columns(4)
                with _cd1: metric_card("selic spot", fmt_pct(_di_spot), "taxa atual")
                with _cd2: metric_card(
                    f"próxima reunião ({_di_next_lbl})",
                    fmt_pct(_di_next),
                    _move_str, _move_cor,
                )
                with _cd3: metric_card(
                    "selic terminal (curva)",
                    fmt_pct(_di_ultimo),
                    f"último nó da curva · inclinação {_di_slope:+.2f}pp",
                    _shape_cor,
                )
                with _cd4: metric_card(
                    "formato da curva",
                    "cortes" if _di_slope < -0.5 else "altas" if _di_slope > 0.5 else "flat",
                    _shape, _shape_cor,
                )

                # ── gráfico da curva ──────────────────────────────────────────
                _fig_di = go.Figure()

                # Spot SELIC (ponto zero)
                _fig_di.add_trace(go.Scatter(
                    x=[0], y=[_di_spot],
                    mode='markers',
                    name='selic spot',
                    marker=dict(color='#FF6B35', size=12, symbol='diamond'),
                    hovertemplate=f'spot: {_di_spot:.2f}%<extra></extra>',
                ))

                # Curva atual — mediana Focus
                _x_cur = _di_curve['tenor_dias'].tolist()
                _y_med = _di_curve['selic_mediana'].tolist()
                _y_med_avg = _di_curve['selic_media'].tolist()
                _lbl_cur = _di_curve['tenor_label'].tolist()

                _fig_di.add_trace(go.Scatter(
                    x=[0] + _x_cur,
                    y=[_di_spot] + _y_med,
                    mode='lines+markers',
                    name='curva di (mediana)',
                    line=dict(color='#00E5FF', width=2.5),
                    marker=dict(size=7, color='#00E5FF'),
                    hovertemplate='%{text}<br>selic mediana: %{y:.2f}%<extra></extra>',
                    text=['spot'] + _lbl_cur,
                ))

                # Média Focus (linha suave por baixo)
                if any(v is not None for v in _y_med_avg):
                    _fig_di.add_trace(go.Scatter(
                        x=[0] + _x_cur,
                        y=[_di_spot] + _y_med_avg,
                        mode='lines',
                        name='curva di (média)',
                        line=dict(color='#00E5FF', width=1, dash='dot'),
                        opacity=0.4,
                        hovertemplate='%{text}<br>selic média: %{y:.2f}%<extra></extra>',
                        text=['spot'] + _lbl_cur,
                    ))

                # Curvas históricas — 30d e 90d atrás
                if _di_hist is not None and not _di_hist.empty:
                    _hist_cores = {"30d atrás": "#FFAA00", "90d atrás": "#888888"}
                    for _lbl_h in _di_hist['curva'].unique():
                        _dh = _di_hist[_di_hist['curva'] == _lbl_h].sort_values('tenor_dias_orig')
                        if not _dh.empty:
                            _fig_di.add_trace(go.Scatter(
                                x=_dh['tenor_dias_orig'].tolist(),
                                y=_dh['selic_mediana'].tolist(),
                                mode='lines',
                                name=_lbl_h,
                                line=dict(color=_hist_cores.get(_lbl_h, '#666'), width=1.5, dash='dot'),
                                opacity=0.6,
                                hovertemplate=f"{_lbl_h}: %{{y:.2f}}%<extra></extra>",
                            ))

                # Linha horizontal — taxa neutra nominal (IPCA meta 4.5% + neutro real 4.5%)
                _taxa_neutra = 9.0
                _cc_di = _chart_cores()
                _fig_di.add_hline(
                    y=_taxa_neutra, line_color=_cc_di["bull"], line_dash='dash', line_width=1,
                    annotation_text=f'taxa neutra ~{_taxa_neutra:.0f}%',
                    annotation_font_color=_cc_di["bull"], annotation_font_size=9,
                )

                _fig_di.update_layout(**base_layout(
                    height=320,
                    title=f"curva di implícita — expectativas de selic por reunião copom (focus/bcb · {_di_tipo})"
                ))
                _fig_di.update_xaxes(
                    title_text="dias corridos",
                    tickvals=[0, 90, 180, 270, 365, 540, 730],
                    ticktext=['spot', '3m', '6m', '9m', '1a', '18m', '2a'],
                )
                _fig_di.update_yaxes(title_text="selic implícita (% ao ano)")

                st.plotly_chart(_fig_di, use_container_width=True, config={'responsive': True})

                # ── caption analítico dinâmico ────────────────────────────────
                if _di_slope < -1.0:
                    _di_caption_regime = (
                        "curva fortemente inclinada p/ baixo: o mercado precifica ciclo de cortes "
                        f"de {abs(_di_slope):.1f}pp da selic no horizonte da curva. "
                        "ambiente favorável para: ações domésticas (consumo, construção, finanças), "
                        "fundos imobiliários de papel (high yield), duration longa em renda fixa. "
                        "risco: surpresa altista de inflação pode reprecificar a curva."
                    )
                elif _di_slope < -0.25:
                    _di_caption_regime = (
                        "curva levemente inclinada p/ baixo: mercado espera cortes graduais de selic. "
                        f"recuo esperado de ~{abs(_di_slope):.1f}pp no horizonte. "
                        "ambiente moderadamente favorável para equities e renda fixa de duration média."
                    )
                elif _di_slope > 1.0:
                    _di_caption_regime = (
                        "curva inclinada p/ cima: mercado precifica aperto monetário adicional de "
                        f"+{_di_slope:.1f}pp. "
                        "ambiente desfavorável para ações domésticas — renda fixa é mais competitiva. "
                        "favorece: exportadoras, bancos (spread maior), setores defensivos."
                    )
                elif _di_slope > 0.25:
                    _di_caption_regime = (
                        "curva levemente ascendente: mercado antecipa possível alta de selic. "
                        "posicionamento defensivo em equities recomendado — preferência por empresas "
                        "com baixa alavancagem e geração de caixa robusta."
                    )
                else:
                    _di_caption_regime = (
                        "curva flat: mercado não vê movimento relevante de selic no horizonte. "
                        "selic estrutural (terminal rate) próxima ao nível atual. "
                        "ambiente neutro — foco em seleção setorial, não na direcionalidade de juros."
                    )

                st.caption(
                    f"curva di implícita (focus/bcb · fonte: {_di_tipo}): cada ponto representa a "
                    "mediana das expectativas do mercado para a selic ao final de cada reunião copom. "
                    f"taxa neutra nominal estimada: ~9% (ipca meta 4.5% + neutro real ~4.5%). "
                    f"{_di_caption_regime}"
                )

                # Tipo de dado mostrado
                _fonte_str = (
                    "📍 fonte: bcb focus — expectativas por reunião copom (granularidade máxima)"
                    if _di_tipo == 'copom'
                    else "📍 fonte: bcb focus — expectativas anuais (projeções dez/ano)"
                )
                st.caption(_fonte_str)

            else:
                st.info(
                    "curva di: dados do focus bcb temporariamente indisponíveis. "
                    "verifique a conexão com a api do banco central."
                )

            # ── 🌉 PONTE 2: P/L JUSTO PELO CICLO DE JUROS ────────────────────
            st.markdown("---")
            section_title("📐 p/l justo — valuation do ibovespa pelo regime de juros reais")

            # Formula: P/L_justo = 1 / (selic_real + ERP)
            # ERP histórico para Brasil ≈ 5% (equity risk premium)
            _ERP_BR = 0.05

            _pl_justo_atual = None
            if _selic_real is not None:
                _sr_dec = _selic_real / 100
                if _sr_dec + _ERP_BR > 0:
                    _pl_justo_atual = round(1 / (_sr_dec + _ERP_BR), 1)

            # Série histórica de P/L teórico
            _pl_hist = None
            if 'Selic_Real' in df_br.columns:
                try:
                    _sr_hist = df_br['Selic_Real'].dropna() / 100
                    _pl_hist = (1 / (_sr_hist + _ERP_BR)).clip(4, 25)
                    _pl_hist.name = 'pl_teorico'
                except Exception:
                    pass

            _pj1, _pj2, _pj3, _pj4 = st.columns(4)
            with _pj1:
                metric_card("p/l teórico ibov", f"{_pl_justo_atual:.1f}x" if _pl_justo_atual else "n/d", "1 / (selic real + erp 5%)", "bear" if (_pl_justo_atual or 99) < 8 else "amber" if (_pl_justo_atual or 99) < 11 else "bull")
            with _pj2:
                _erp_str = f"selic real {_selic_real:.1f}% + erp {_ERP_BR*100:.0f}% = {((_selic_real or 0)/100+_ERP_BR)*100:.0f}% custo equity" if _selic_real else "n/d"
                metric_card("custo de equity br", f"{((_selic_real or 0)/100 + _ERP_BR)*100:.1f}%" if _selic_real else "n/d", _erp_str, "bear")
            with _pj3:
                # P/L justo com SELIC real a 4% (cenário de alívio)
                _pl_cenario_bull = round(1 / (0.04 + _ERP_BR), 1)
                metric_card("p/l se selic real = 4%", f"{_pl_cenario_bull:.1f}x", "cenário de alívio monetário", "bull")
            with _pj4:
                if _pl_justo_atual:
                    _upside = ((_pl_cenario_bull / _pl_justo_atual) - 1) * 100
                    metric_card("upside teórico de múltiplo", f"+{_upside:.0f}%", "expansão p/l se selic real cair para 4%", "bull" if _upside > 20 else "amber")

            if _pl_hist is not None and not _pl_hist.empty:
                _fig_pl = go.Figure()
                # Banda de P/L teórico
                _fig_pl.add_trace(go.Scatter(
                    x=_pl_hist.index, y=_pl_hist.values,
                    name='p/l teórico (1/(selic real+erp))',
                    fill='tozeroy', fillcolor='rgba(0,229,255,0.07)',
                    line=dict(color='#00E5FF', width=2),
                    hovertemplate='%{x|%b %Y}<br>p/l teórico: %{y:.1f}x<extra></extra>',
                ))
                # Bandas de referência
                _cc_pl = _chart_cores()
                _fig_pl.add_hline(y=15, line_color=_cc_pl["bull"],  line_dash='dash', line_width=1, annotation_text='15x (juro baixo)', annotation_font_color=_cc_pl["bull"],  annotation_font_size=9)
                _fig_pl.add_hline(y=10, line_color=_cc_pl["amber"], line_dash='dash', line_width=1, annotation_text='10x (neutro)',    annotation_font_color=_cc_pl["amber"], annotation_font_size=9)
                _fig_pl.add_hline(y=7,  line_color=_cc_pl["bear"],  line_dash='dash', line_width=1, annotation_text='7x (juro alto)',  annotation_font_color=_cc_pl["bear"],  annotation_font_size=9)
                # Ponto atual
                if _pl_justo_atual:
                    _fig_pl.add_trace(go.Scatter(
                        x=[_pl_hist.index[-1]], y=[_pl_justo_atual],
                        mode='markers', name='atual',
                        marker=dict(color='#FF6B35', size=12, symbol='diamond'),
                        hovertemplate=f'atual: {_pl_justo_atual:.1f}x<extra></extra>',
                    ))
                _fig_pl.update_layout(**base_layout(height=280, title="p/l teórico ibovespa pelo regime de juros reais (modelo gordon simplificado)"))
                _fig_pl.update_yaxes(title_text="p/l teórico (x)", range=[3, 22])
                st.plotly_chart(_fig_pl, use_container_width=True, config={'responsive': True})
                st.caption(
                    "p/l teórico = 1 / (selic real + erp). "
                    "equidade risk premium (erp) estimado em 5% para o brasil (média histórica). "
                    "quando a selic real cai, o p/l justo SOBE — expansão de múltiplos. "
                    "quando sobe, o p/l justo CAI — compressão. "
                    "este modelo de gordon simplificado ignora crescimento de lucros, mas captura "
                    "o efeito da taxa de desconto de forma direta. "
                    "leitura: ibovespa negociando ABAIXO do p/l teórico = desconto raro (compra). "
                    "acima = múltiplo esticado dado o regime de juros atual. "
                    "nota: p/l real do ibovespa varia conforme earnings realizados — use como referência, não como alvo exato."
                )

            st.markdown("---")
            st.markdown(tooltip_info("Dólar Ptax — taxa de câmbio oficial calculada pelo BCB. Referência para contratos de derivativos e ajuste de ativos dolarizados."), unsafe_allow_html=True)
            g3, g4 = st.columns(2)
            with g3:
                st.plotly_chart(criar_grafico_macro(df_br, 'Dolar', "dólar comercial (r$)", "#FFFFFF"), use_container_width=True, config={'responsive': True})
                st.caption(
                    "dólar ptax: taxa de câmbio oficial calculada pelo bcb. "
                    "dólar forte = pressão inflacionária via importados e combustíveis, mas "
                    "beneficia exportadoras (VALE3, PETR3, agro, papel&celulose). "
                    "r$5.50-r$6.00 é a zona de equilíbrio no cenário atual; acima de r$6.50 "
                    "o bcb tende a postura mais hawkish para conter passthrough para o ipca. "
                    "leitura: dólar subindo + commodities subindo = proteção para carteiras "
                    "com exportadoras. dólar subindo isolado = risco de recessão global."
                )
            with g4:
                st.plotly_chart(criar_grafico_macro(df_br, 'Desemprego', "taxa de desemprego pnadc (%)", "#E040FB"), use_container_width=True, config={'responsive': True})
                st.caption(
                    "desemprego pnad contínua (ibge): lagged em 1-2 trimestres. "
                    "queda do desemprego → maior massa salarial → consumo e inflação. "
                    "abaixo de 8% favorece setor de consumo doméstico e varejo (LREN3, AMER3, RENT3). "
                    "mercado informal (~40% da pea) não capturado — desemprego real é maior. "
                    "leitura: desemprego caindo + copom cortando = janela positiva para small caps "
                    "de consumo."
                )
            st.markdown(tooltip_info("Desemprego PNAD Contínua — taxa de desemprego calculada pelo IBGE. Indicador defasado de atividade econômica."), unsafe_allow_html=True)

            # ── FISCAL BRASILEIRO ──────────────────────────────────────────────
            st.markdown("---")
            section_title("🏛️ fiscal brasileiro")

            # usar df_br_master para o semáforo (precisa dos 6 meses mais recentes
            # independente do filtro de horizonte selecionado pelo usuário)
            fiscal = calcular_semaforo_fiscal(df_br_master)

            # KPIs Fiscal Brasil (design system v5)
            from utils.components import portfolio_kpis as _pf_kpis_fbr
            divida_val = fiscal['divida_pib']
            tend_val   = fiscal['tendencia_divida']
            prim_val   = fiscal['result_primario']
            cores_map  = {"bear": "bear", "amber": "amber", "bull": "bull"}

            if divida_val is not None and tend_val is not None:
                sinal_tend  = "▲" if tend_val > 0 else "▼"
                divida_sub  = f"{sinal_tend} {abs(tend_val):.1f}pp em 6m"
                cor_tend    = "bear" if tend_val > 1 else ("bull" if tend_val < -1 else "muted")
            else:
                divida_sub, cor_tend = "sem dados BCB", "muted"

            _pf_kpis_fbr([
                {
                    "nome":     "dívida bruta/pib",
                    "valor":    f"{divida_val:.1f}%" if divida_val is not None else "n/d",
                    "sublabel": divida_sub,
                    "tone":     cor_tend,
                    "icone":    "🏛",
                },
                {
                    "nome":     "resultado primário",
                    "valor":    f"{prim_val:+.2f}% pib" if prim_val is not None else "n/d",
                    "sublabel": ("superávit" if (prim_val or 0) >= 0 else "déficit") if prim_val is not None else "sem dados BCB",
                    "tone":     "bull" if (prim_val or -1) >= 0 else "bear",
                    "icone":    "💰",
                },
                {
                    "nome":     "status fiscal",
                    "valor":    fiscal['label'],
                    "sublabel": "leitura agregada do quadro",
                    "tone":     cores_map.get(fiscal['cor'], "muted"),
                    "icone":    "🚦",
                },
            ])

            gf1, gf2 = st.columns(2)
            with gf1:
                _cc_div = _chart_cores()
                fig_divida = criar_grafico_macro(df_br, 'Divida_Bruta_PIB',
                                                 "dívida bruta do governo geral (% pib)", _cc_div["bear"])
                fig_divida.add_hline(
                    y=60, line_color=_cc_div["amber"], line_dash="dash", line_width=1,
                    annotation_text="limite prudencial 60% pib",
                    annotation_font=dict(color=_cc_div["amber"], size=10, family="Inter, system-ui, sans-serif"),
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
            _macro_us_tipo = chart_type_toggle(key="macro_us", default="linha")
            v_fed    = valor_atual_seguro(df_global, 'FEDFUNDS')
            v_dgs10  = valor_atual_seguro(df_global, 'DGS10')
            v_unrate = valor_atual_seguro(df_global, 'UNRATE')

            # CPI YoY — SEMPRE recalcula de CPIAUCSL se a série base existir.
            # CRÍTICO: dropna() ANTES de pct_change(12) — df_global tem índice diário
            # (DGS10/DGS2 são diárias), mas CPIAUCSL é mensal. Sem dropna, pct_change(12)
            # desloca 12 LINHAS (não 12 meses), e como a coluna CPIAUCSL é esparsa
            # (NaN em quase todas as linhas), o resultado fica quase todo NaN. Depois
            # reindex traz de volta ao índice diário com NaN entre os pontos mensais.
            if 'CPIAUCSL' in df_global.columns:
                try:
                    _cpi_monthly = df_global['CPIAUCSL'].dropna()
                    if len(_cpi_monthly) >= 13:
                        _yoy_monthly = _cpi_monthly.pct_change(12, fill_method=None) * 100
                        df_global['CPI_YOY'] = _yoy_monthly.reindex(df_global.index)
                        _last_yoy = df_global['CPI_YOY'].dropna()
                        logger.info(
                            f"[macro] CPI_YOY recalculado: {len(_cpi_monthly)} pontos CPIAUCSL, "
                            f"último valor CPI_YOY = {_last_yoy.iloc[-1]:.2f}% on {_last_yoy.index[-1].date()}"
                            if not _last_yoy.empty else "[macro] CPI_YOY: serie vazia após reindex"
                        )
                    else:
                        logger.warning(f"[macro] CPI_YOY: CPIAUCSL tem só {len(_cpi_monthly)} pontos (precisa >=13).")
                except Exception as e:
                    logger.error(f"[macro] CPI_YOY calc via CPIAUCSL falhou: {e}")
            else:
                logger.warning("[macro] CPI_YOY: CPIAUCSL ausente no snapshot fred_global.")

            _cpi_yoy_val = valor_atual_seguro(df_global, 'CPI_YOY')
            _df_cpi_yoy  = df_global['CPI_YOY'].dropna() if 'CPI_YOY' in df_global.columns else pd.Series(dtype=float)

            # KPIs EUA (design system v5)
            from utils.components import portfolio_kpis as _pf_kpis_us
            _fed_tone = "bear" if (v_fed and v_fed > 5) else ("amber" if (v_fed and v_fed > 3.5) else "bull")
            _cpi_tone = "bear" if (_cpi_yoy_val and _cpi_yoy_val > 3.5) else ("bull" if (_cpi_yoy_val and _cpi_yoy_val < 2.5) else "amber")
            _t10_tone = "bear" if (v_dgs10 and v_dgs10 > 4.5) else ("amber" if (v_dgs10 and v_dgs10 > 3.5) else "bull")
            _unrate_tone = "bear" if (v_unrate and v_unrate > 5.5) else ("amber" if (v_unrate and v_unrate > 4.5) else "bull")

            _pf_kpis_us([
                {
                    "nome":     "fed funds rate",
                    "valor":    fmt_pct(v_fed, sinal=False),
                    "sublabel": "taxa fomc",
                    "tone":     _fed_tone,
                    "icone":    "🏛",
                },
                {
                    "nome":     "cpi yoy",
                    "valor":    f"{_cpi_yoy_val:.2f}%" if _cpi_yoy_val else "n/d",
                    "sublabel": "inflação acumulada",
                    "tone":     _cpi_tone,
                    "icone":    "📊",
                },
                {
                    "nome":     "treasury 10y",
                    "valor":    fmt_pct(v_dgs10, sinal=False),
                    "sublabel": "yield benchmark",
                    "tone":     _t10_tone,
                    "icone":    "📈",
                },
                {
                    "nome":     "desemprego (us)",
                    "valor":    fmt_pct(v_unrate, sinal=False),
                    "sublabel": "taxa BLS",
                    "tone":     _unrate_tone,
                    "icone":    "👥",
                },
            ])
            tooltip("treasury_10y")
            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(criar_grafico_macro(df_global, 'FEDFUNDS', "fed funds rate (%)", _chart_cores()["bull"], _macro_us_tipo), use_container_width=True, config={'responsive': True})
                st.caption(
                    "fed funds rate: taxa básica americana definida pelo fomc (fed). "
                    "referência global para o custo do dinheiro — juros altos nos eua "
                    "valorizam o dólar, drenam capital de emergentes e pressionam o real. "
                    "leitura: cada +0.25pp de fed funds = saída de fluxo de emergentes. "
                    "ciclo de cortes do fed = vento favorável para ibovespa e reais. "
                    "ciclo de alta = pressão no câmbio e juros no brasil via carry trade."
                )

            # Gráfico CPI YoY
            with g2:
                if not _df_cpi_yoy.empty:
                    _fig_cpi = go.Figure()
                    _fig_cpi.add_trace(go.Scatter(
                        x=_df_cpi_yoy.index,
                        y=_df_cpi_yoy.values,
                        name='cpi yoy',
                        line=dict(color='#00B0FF', width=2),
                        fill='tozeroy',
                        fillcolor='rgba(0, 176, 255, 0.08)',
                        hovertemplate=(
                            '%{x|%b %Y}<br>'
                            'cpi yoy: %{y:.2f}%<extra></extra>'
                        ),
                    ))
                    _cc_cpi = _chart_cores()
                    _fig_cpi.add_hline(
                        y=2.0, line_color=_cc_cpi["bull"],
                        line_dash='dash', line_width=1,
                        annotation_text='meta 2%',
                        annotation_font_color=_cc_cpi["bull"],
                        annotation_font_size=9,
                    )
                    _fig_cpi.add_hline(
                        y=3.5, line_color=_cc_cpi["amber"],
                        line_dash='dot', line_width=1,
                        annotation_text='alerta 3.5%',
                        annotation_font_color=_cc_cpi["amber"],
                        annotation_font_size=9,
                    )
                    _lay_cpi = base_layout(
                        height=280,
                        title='inflação anual eua — cpi yoy (%)'
                    )
                    _fig_cpi.update_layout(**_lay_cpi)
                    st.plotly_chart(
                        _fig_cpi, use_container_width=True,
                        config={'responsive': True}
                    )
                    st.caption(
                        "cpi yoy = variação percentual do índice de preços "
                        "ao consumidor vs mesmo mês do ano anterior. "
                        "meta fed: 2%. acima de 3.5% pressiona manutenção "
                        "de juros altos. fonte: fred — cpiaucsl."
                    )
                else:
                    st.caption("cpi yoy: aguardando dados da próxima leitura do fred.")
            st.markdown(tooltip_info("Treasury 10y — rendimento do título público americano de 10 anos. Referência para taxas de juros globais e custo de financiamento de longo prazo."), unsafe_allow_html=True)
            st.markdown(tooltip_info("UNRATE — taxa de desemprego americana (U-3). Indicador-chave de saúde do mercado de trabalho, monitorado pelo Fed."), unsafe_allow_html=True)
            g3, g4 = st.columns(2)
            with g3:
                st.plotly_chart(criar_grafico_macro(df_global, 'DGS10', "treasury yield 10y (%)", "#FFFFFF"), use_container_width=True, config={'responsive': True})
                st.caption(
                    "treasury 10y: título público americano de 10 anos — referência global de "
                    "custo do capital. acima de 4.5% comprime múltiplos de growth e pressiona "
                    "emergentes via fortalecimento do dólar. inversão com o 2y (treasury 2y > 10y) "
                    "sinaliza expectativa de desaceleração econômica. leitura: treasuries acima de "
                    "5% historicamente precedem estresse em high yield e ações de alto crescimento."
                )
            with g4:
                st.plotly_chart(criar_grafico_macro(df_global, 'UNRATE', "taxa de desemprego (us) (%)", _chart_cores()["amber"]), use_container_width=True, config={'responsive': True})
                st.caption(
                    "taxa de desemprego americana u-3 (bureau of labor statistics). "
                    "abaixo de 4% = mercado de trabalho aquecido → risco inflacionário → fed hawkish. "
                    "acima de 5% = desaceleração → fed pode cortar juros. "
                    "leitura: desemprego subindo rapidamente ('sahm rule') é sinal recessivo clássico — "
                    "alta de 0.5pp em 3 meses ativa o sinal historicamente."
                )

            # ── INCLINAÇÃO DA CURVA DE JUROS ─────────────────────────────────
            st.markdown("---")
            section_title("📐 inclinação da curva (us treasury)")
            df_slope = buscar_slope_curva()
            if df_slope is None or df_slope.empty:
                st.info("Dados de inclinação ainda não coletados — aguarde próxima execução do ETL macro.")
            else:
                df_slope = df_slope.dropna(subset=["slope_10y_2y"]).tail(252 * 10)
                fig_slope = go.Figure()
                fig_slope.add_hrect(y0=-5, y1=0, fillcolor="rgba(231,76,60,0.08)", line_width=0, layer="below")
                fig_slope.add_hrect(y0=0, y1=5, fillcolor="rgba(46,204,113,0.08)", line_width=0, layer="below")
                fig_slope.add_hline(y=0, line_color=_chart_cores()["muted"], line_width=1, line_dash="dot")
                fig_slope.add_trace(go.Scatter(
                    x=df_slope["data"], y=df_slope["slope_10y_2y"],
                    mode="lines", name="T10Y - T2Y (pp)",
                    line=dict(width=2, color="#ff8c00"),
                ))
                if "slope_10y_3m" in df_slope.columns and not df_slope["slope_10y_3m"].dropna().empty:
                    fig_slope.add_trace(go.Scatter(
                        x=df_slope["data"], y=df_slope["slope_10y_3m"],
                        mode="lines", name="T10Y - T3M (pp)",
                        line=dict(width=1.5, color="#00B0FF", dash="dot"),
                    ))
                fig_slope.update_layout(
                    height=320, margin=dict(l=20, r=20, t=10, b=10),
                    showlegend=True,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(title="spread (pp)", zeroline=False, gridcolor="rgba(120,120,120,0.15)"),
                    xaxis=dict(gridcolor="rgba(120,120,120,0.15)"),
                    legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
                )
                st.plotly_chart(fig_slope, use_container_width=True)
                _slope_val = float(df_slope["slope_10y_2y"].iloc[-1])
                if _slope_val < 0:
                    st.markdown(
                        f'<div style="color:var(--bear); font-family:Courier New,monospace;">'
                        f'Curva invertida ({_slope_val:+.2f} pp) — sinal clássico de fim de ciclo.</div>',
                        unsafe_allow_html=True,
                    )
                elif _slope_val < 0.5:
                    st.markdown(
                        f'<div style="color:var(--amber); font-family:Courier New,monospace;">'
                        f'Curva achatada ({_slope_val:+.2f} pp) — atenção.</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="color:var(--bull); font-family:Courier New,monospace;">'
                        f'Curva positiva ({_slope_val:+.2f} pp).</div>',
                        unsafe_allow_html=True,
                    )
                st.caption(
                    "inclinação da curva de juros (spread 10y−2y e 10y−3m): o mercado precifica "
                    "inversão quando juros curtos > juros longos (expectativa de recessão). "
                    "historicamente, inversão precede recessão em 12-18 meses. "
                    "desinversão (spread voltando a positivo) pode sinalizar piora iminente. "
                    "fonte: fred — dgs10, dgs2, dgs3mo (série histórica 10 anos)."
                )

            # ── 📐 P/L JUSTO — EUA (Gordon simplificado) ───────────────────────
            st.markdown("---")
            section_title("📐 p/l justo — valuation do s&p 500 pelo regime de juros reais (eua)")
            _ERP_US = 0.03
            _real_yield_us = None
            if v_dgs10 is not None and _cpi_yoy_val is not None:
                _real_yield_us = v_dgs10 - _cpi_yoy_val
            _pl_justo_us = None
            if _real_yield_us is not None:
                _ry_dec = _real_yield_us / 100
                if _ry_dec + _ERP_US > 0:
                    _pl_justo_us = round(1 / (_ry_dec + _ERP_US), 1)

            # Série histórica do P/L teórico (a partir de DGS10 − CPI_YOY)
            _pl_hist_us = None
            if 'DGS10' in df_global.columns and 'CPI_YOY' in df_global.columns:
                try:
                    _ry_hist = (df_global['DGS10'] - df_global['CPI_YOY']).dropna()
                    _pl_hist_us = (1 / (_ry_hist / 100 + _ERP_US)).clip(10, 40)
                    _pl_hist_us.name = 'pl_teorico_us'
                except Exception:
                    pass

            # P/L real do S&P 500 via yfinance.
            # ^GSPC é índice — yfinance NÃO retorna trailingPE pra índices (None).
            # Usar ETFs que replicam o S&P 500 (SPY/IVV/VOO) como fonte primária.
            # Try independente por ticker — uma exceção em um não impede o próximo.
            _pl_real_spx = None
            for _proxy_spx in ("SPY", "IVV", "VOO"):
                try:
                    _pe_val = (yf.Ticker(_proxy_spx).info or {}).get("trailingPE")
                    if _pe_val is not None and _pe_val > 0:
                        _pl_real_spx = float(_pe_val)
                        break
                except Exception:
                    continue

            _pj1, _pj2, _pj3, _pj4 = st.columns(4)
            with _pj1:
                metric_card(
                    "p/l teórico s&p 500", f"{_pl_justo_us:.1f}x" if _pl_justo_us else "n/d",
                    "1 / (real yield 10y + erp 3%)",
                    "bear" if (_pl_justo_us or 99) < 14 else "amber" if (_pl_justo_us or 99) < 18 else "bull"
                )
            with _pj2:
                _custo_eq = ((_real_yield_us or 0) / 100 + _ERP_US) * 100 if _real_yield_us is not None else None
                metric_card(
                    "custo de equity us", f"{_custo_eq:.1f}%" if _custo_eq else "n/d",
                    f"10y real {_real_yield_us:.1f}% + erp {_ERP_US*100:.0f}%" if _real_yield_us is not None else "dados insuficientes",
                    "bear"
                )
            with _pj3:
                _pl_cenario_bull_us = round(1 / (0.01 + _ERP_US), 1)
                metric_card(
                    "p/l se real yield = 1%", f"{_pl_cenario_bull_us:.1f}x",
                    "cenário de corte do fed (real yield baixo)", "bull"
                )
            with _pj4:
                if _pl_justo_us and _pl_real_spx:
                    _desconto = ((_pl_real_spx / _pl_justo_us) - 1) * 100
                    metric_card(
                        "s&p 500 vs teórico",
                        f"{_desconto:+.0f}%" if abs(_desconto) < 999 else "n/a",
                        f"spx real {_pl_real_spx:.1f}x vs teórico {_pl_justo_us:.1f}x",
                        "bull" if _desconto < -10 else "bear" if _desconto > 15 else "amber"
                    )
                elif _pl_justo_us:
                    metric_card("s&p 500 real", "n/d", "yfinance indisponível", "amber")

            if _pl_hist_us is not None and not _pl_hist_us.empty:
                _fig_pl_us = go.Figure()
                _fig_pl_us.add_trace(go.Scatter(
                    x=_pl_hist_us.index, y=_pl_hist_us.values,
                    name='p/l teórico (1/(10y real+erp))',
                    fill='tozeroy', fillcolor='rgba(0,176,255,0.07)',
                    line=dict(color='#00B0FF', width=2),
                    hovertemplate='%{x|%b %Y}<br>p/l teórico: %{y:.1f}x<extra></extra>',
                ))
                if _pl_real_spx:
                    _fig_pl_us.add_trace(go.Scatter(
                        x=[_pl_hist_us.index[-1]], y=[_pl_real_spx],
                        mode='markers',                         name='s&p 500 real',
                        marker=dict(color='#FF6B35', size=12, symbol='diamond'),
                        hovertemplate=f's&p 500 real: {_pl_real_spx:.1f}x<extra></extra>',
                    ))
                _cc_pl_us = _chart_cores()
                _fig_pl_us.add_hline(y=25, line_color=_cc_pl_us["bull"],  line_dash='dash', line_width=1, annotation_text='25x (juro baixo)', annotation_font_color=_cc_pl_us["bull"],  annotation_font_size=9)
                _fig_pl_us.add_hline(y=18, line_color=_cc_pl_us["amber"], line_dash='dash', line_width=1, annotation_text='18x (neutro)',    annotation_font_color=_cc_pl_us["amber"], annotation_font_size=9)
                _fig_pl_us.add_hline(y=13, line_color=_cc_pl_us["bear"],  line_dash='dash', line_width=1, annotation_text='13x (juro alto)',  annotation_font_color=_cc_pl_us["bear"],  annotation_font_size=9)
                if _pl_justo_us:
                    _fig_pl_us.add_trace(go.Scatter(
                        x=[_pl_hist_us.index[-1]], y=[_pl_justo_us],
                        mode='markers', name='teórico atual',
                        marker=dict(color='#00E5FF', size=10, symbol='circle'),
                        hovertemplate=f'teórico: {_pl_justo_us:.1f}x<extra></extra>',
                    ))
                _fig_pl_us.update_layout(**base_layout(height=280, title="p/l teórico s&p 500 pelo regime de juros reais (modelo gordon simplificado)"))
                _fig_pl_us.update_yaxes(title_text="p/l teórico (x)", range=[8, 38])
                st.plotly_chart(_fig_pl_us, use_container_width=True, config={'responsive': True})
                st.caption(
                    "p/l teórico = 1 / (real yield 10y + erp). "
                    "equity risk premium (erp) estimado em 3% para eua (mercado maduro). "
                    "real yield = treasury 10y − cpi yoy. "
                    "quando o fed corta juros, a real yield cai → p/l justo SOBE. "
                    "quando o fed aperta, sobe → p/l justo CAI. "
                    "leitura: s&p 500 acima do p/l teórico = valuation esticado; "
                    "abaixo = desconto relativo ao regime de juros. "
                    "use como referência de regime, não como timing tool."
                )

            # ── FISCAL EUA ──────────────────────────────────────────────────────
            st.markdown("---")
            section_title("🏛️ fiscal americano")

            v_divida_eua_pib = valor_atual_seguro(df_global, 'GFDEGDQ188S')

            f1, f2 = st.columns(2)
            with f1:
                if v_divida_eua_pib is not None:
                    metric_card("dívida pública/pib (eua)", f"{v_divida_eua_pib:.1f}%")
                else:
                    metric_card("dívida pública/pib (eua)", "n/d", "fred indisponível")

            # Déficit federal EUA — valor absoluto em bilhões
            _deficit = df_global.get('MTSDS133FMS', pd.Series(dtype=float)).dropna()
            if not _deficit.empty:
                _def_close = (
                    _deficit
                    if isinstance(_deficit, pd.Series)
                    else pd.Series(dtype=float)
                )

                # MTSDS133FMS está em milhões USD → converte para bilhões
                _def_bi = _def_close / 1000

                # Acumulado 12 meses (rolling sum)
                _def_12m = _def_bi.rolling(12).sum()

                _def_mensal_atual = float(_def_bi.dropna().iloc[-1])
                _def_12m_atual    = float(_def_12m.dropna().iloc[-1])
                _sinal_def        = "superávit" if _def_mensal_atual >= 0 else "déficit"
                _cc_def           = _chart_cores()
                _cor_def          = _cc_def["bull"] if _def_mensal_atual >= 0 else _cc_def["bear"]

                with f2:
                    metric_card(
                        "resultado fiscal (12m acum.)",
                        f"us$ {_def_12m_atual:,.0f}bi",
                        f"{'superávit' if _def_12m_atual >= 0 else 'déficit'} "
                        f"acumulado últimos 12 meses",
                        "bull" if _def_12m_atual >= 0 else "bear",
                    )

                # Gráfico de barras mensais + linha de acumulado 12m
                _fig_def = go.Figure()

                # Barras mensais
                _fig_def.add_trace(go.Bar(
                    x=_def_bi.index,
                    y=_def_bi.values,
                    name="mensal (us$ bi)",
                    marker_color=[
                        _cc_def["bull"] if v >= 0 else _cc_def["bear"]
                        for v in _def_bi.values
                    ],
                    opacity=0.7,
                    hovertemplate=(
                        '%{x|%b %Y}<br>'
                        'resultado: us$ %{y:,.0f}bi<extra></extra>'
                    ),
                ))

                # Linha de acumulado 12m
                _fig_def.add_trace(go.Scatter(
                    x=_def_12m.index,
                    y=_def_12m.values,
                    name="acum. 12m (us$ bi)",
                    line=dict(color=_cc_def["amber"], width=2),
                    hovertemplate=(
                        '%{x|%b %Y}<br>'
                        'acum 12m: us$ %{y:,.0f}bi<extra></extra>'
                    ),
                ))

                _fig_def.add_hline(
                    y=0, line_color=_cc_def["muted"],
                    line_dash='dash', line_width=1,
                )

                _lay_def = base_layout(
                    height=280,
                    title='resultado fiscal federal eua (us$ bilhões)'
                )
                _fig_def.update_layout(**_lay_def)
                st.plotly_chart(
                    _fig_def, use_container_width=True,
                    config={'responsive': True}
                )
                st.caption(
                    "barras = resultado mensal. linha laranja = acumulado 12 meses. "
                    "déficits persistentes pressionam emissão de títulos e "
                    "juros longos. fonte: fred — mtsds133fms (us$ milhões)."
                )
            else:
                with f2:
                    metric_card("resultado fiscal", "n/d", "fred indisponível")

            gf1, gf2 = st.columns(2)
            with gf1:
                if 'GFDEGDQ188S' in df_global.columns and not df_global['GFDEGDQ188S'].dropna().empty:
                    _cc_debt = _chart_cores()
                    fig_debt = criar_grafico_macro(df_global, 'GFDEGDQ188S', "dívida pública federal (% pib)", _cc_debt["bear"])
                    fig_debt.add_hline(y=78, line_color=_cc_debt["amber"], line_dash="dash", line_width=1,
                                      annotation_text="patamar 2019 (pré-covid)", annotation_font_color=_cc_debt["amber"], annotation_font_size=9)
                    st.plotly_chart(fig_debt, use_container_width=True, config={'responsive': True})

        elif aba_sel == "🌍 europa/ásia":
            # ── EUROPA ───────────────────────────────────────────────────────────
            section_title("🇪🇺 europa — banco central europeu e economia")

            _col_eu1, _col_eu2, _col_eu3, _col_eu4 = st.columns(4)

            _ecb_rate    = None
            _eu_cpi      = None
            _eu_unemp    = None
            _eu_gdp_grow = None

            try:
                _ecb_series = df_global['ECBDFR'].dropna()
                if not _ecb_series.empty:
                    _ecb_rate = round(float(_ecb_series.iloc[-1]), 2)
            except Exception as e:
                logger.error(f"[macro] BCE deposit rate falhou: {e}")
            try:
                _eu_cpi_raw = df_global['CP0000EZ19M086NEST'].dropna()
                if not _eu_cpi_raw.empty:
                    _eu_cpi_yoy = _eu_cpi_raw.pct_change(12) * 100
                    _eu_cpi = round(float(_eu_cpi_yoy.dropna().iloc[-1]), 2)
            except Exception as e:
                logger.error(f"[macro] Euro CPI falhou: {e}")
            try:
                _eu_un_series = df_global['LRHUTTTTEZM156S'].dropna()
                if not _eu_un_series.empty:
                    _eu_unemp = round(float(_eu_un_series.dropna().iloc[-1]), 1)
            except Exception as e:
                logger.error(f"[macro] Euro desemprego falhou: {e}")

            with _col_eu1:
                metric_card(
                    "bce deposit rate",
                    f"{_ecb_rate:.2f}%" if _ecb_rate is not None else "N/D",
                    "taxa de depósito do bce",
                    "bear" if (_ecb_rate or 0) > 3 else "amber",
                )
            with _col_eu2:
                metric_card(
                    "cpi zona euro (yoy)",
                    f"{_eu_cpi:.2f}%" if _eu_cpi is not None else "N/D",
                    "variação anual hicp",
                    "bear" if (_eu_cpi or 0) > 3 else "bull",
                )
            with _col_eu3:
                metric_card(
                    "desemprego zona euro",
                    f"{_eu_unemp:.1f}%" if _eu_unemp is not None else "N/D",
                    "taxa de desemprego",
                    "bear" if (_eu_unemp or 0) > 7 else "bull",
                )
            with _col_eu4:
                metric_card("euro/usd", "—", "par cambial")

            _eu_col1, _eu_col2 = st.columns(2)

            with _eu_col1:
                try:
                    _ecb_hist = df_global['ECBDFR'].dropna()
                    if not _ecb_hist.empty:
                        _fig_ecb = go.Figure(go.Scatter(
                            x=_ecb_hist.index,
                            y=_ecb_hist.values,
                            line=dict(color=_chart_cores()["accent"], width=2),
                            hovertemplate=(
                                '%{x|%b %Y}<br>'
                                'bce rate: %{y:.2f}%<extra></extra>'
                            ),
                        ))
                        _fig_ecb.add_hline(
                            y=0, line_color=_chart_cores()["muted"],
                            line_dash='dash', line_width=1,
                        )
                        _lay_ecb = base_layout(
                            height=260,
                            title='bce — taxa de depósito (%)'
                        )
                        _fig_ecb.update_layout(**_lay_ecb)
                        st.plotly_chart(
                            _fig_ecb, use_container_width=True,
                            config={'responsive': True}
                        )
                        st.caption(
                            "taxa de depósito do banco central europeu (bce). "
                            "subidas rápidas de 2022-2023 foram as mais "
                            "agressivas da história do euro. "
                            "juros altos na europa encarecem crédito e "
                            "pressionam países com alta dívida (itália, grécia). "
                            "fonte: fred — ecbdfr."
                        )
                except Exception:
                    st.info("bce: dados indisponíveis")

            with _eu_col2:
                try:
                    _eu10y_ser = df_global['IRLTLT01EZM156N'].dropna()
                    if not _eu10y_ser.empty:
                        _bund_ser = df_global['IRLTLT01DEM156N'].dropna()
                        _fig_eu10y = go.Figure()
                        _fig_eu10y.add_trace(go.Scatter(
                            x=_eu10y_ser.index,
                            y=_eu10y_ser.values,
                            name='zona euro 10y',
                            line=dict(color='#00B0FF', width=2),
                            hovertemplate=(
                                '%{x|%b %Y}<br>'
                                'eu 10y: %{y:.2f}%<extra></extra>'
                            ),
                        ))
                        if not _bund_ser.empty:
                            _fig_eu10y.add_trace(go.Scatter(
                                x=_bund_ser.index,
                                y=_bund_ser.values,
                                name='bund alemão 10y',
                                line=dict(
                                    color='#FFD700', width=1.5,
                                    dash='dot'
                                ),
                                hovertemplate=(
                                    '%{x|%b %Y}<br>'
                                    'bund: %{y:.2f}%<extra></extra>'
                                ),
                            ))
                        _lay_eu10y = base_layout(
                            height=260,
                            title='yields soberanos europa 10 anos (%)'
                        )
                        _fig_eu10y.update_layout(**_lay_eu10y)
                        st.plotly_chart(
                            _fig_eu10y, use_container_width=True,
                            config={'responsive': True}
                        )
                        st.caption(
                            "yield do título soberano da zona euro vs bund alemão. "
                            "o spread entre países periféricos (itália, espanha) "
                            "e o bund é o principal indicador de stress fiscal europeu. "
                            "spread alto = mercado exige prêmio de risco. "
                            "fonte: fred — irltlt01ezm156n / irltlt01dem156n."
                        )
                except Exception:
                    st.info("yields europa: dados indisponíveis")

            try:
                _btp_ser = df_global['IRLTLT01ITM156N'].dropna()
                _bund2_ser = df_global['IRLTLT01DEM156N'].dropna()
                if not _btp_ser.empty and not _bund2_ser.empty:
                    _spread_btp = (
                        _btp_ser.reindex(_bund2_ser.index, method='ffill')
                        - _bund2_ser
                    ).dropna()
    
                    _spread_atual = round(float(_spread_btp.iloc[-1]), 2)

                    section_title("🔥 spread btp-bund — stress fiscal europeu")
                    metric_card(
                        "spread btp-bund (itália vs alemanha)",
                        f"{_spread_atual:.2f}pp",
                        "acima de 2.5pp = stress fiscal elevado",
                        "bear" if _spread_atual > 2.5
                        else "amber" if _spread_atual > 1.5
                        else "bull",
                        destaque=True,
                    )
                    tooltip("spread_btp_bund")

                    _cc_btp = _chart_cores()
                    _fig_spread = go.Figure(go.Scatter(
                        x=_spread_btp.index,
                        y=_spread_btp.values,
                        line=dict(color=_cc_btp["bear"], width=2),
                        fill='tozeroy',
                        fillcolor=f'{_cc_btp["bear"]}14',
                        hovertemplate=(
                            '%{x|%b %Y}<br>'
                            'spread: %{y:.2f}pp<extra></extra>'
                        ),
                    ))
                    _fig_spread.add_hline(
                        y=2.5, line_color=_cc_btp["amber"],
                        line_dash='dash', line_width=1,
                        annotation_text='alerta 2.5pp',
                        annotation_font_color=_cc_btp["amber"],
                        annotation_font_size=9,
                    )
                    _lay_spread = base_layout(
                        height=250,
                        title='spread btp-bund (pp) — barómetro de stress europeu'
                    )
                    _fig_spread.update_layout(**_lay_spread)
                    st.plotly_chart(
                        _fig_spread, use_container_width=True,
                        config={'responsive': True}
                    )
                    st.caption(
                        "spread entre o título italiano de 10 anos (btp) e o "
                        "alemão (bund). o bund é o ativo livre de risco europeu. "
                        "spread > 2.5pp historicamente precede crises de dívida "
                        "(2011-2012: spread chegou a 5pp, causando crise do euro). "
                        "indicador chave para risco sistêmico europeu. "
                        "fonte: fred — irltlt01itm156n / irltlt01dem156n."
                    )
            except Exception as e:
                logger.error(f"[macro] BTP-Bund spread falhou: {e}")

            st.markdown("<br>", unsafe_allow_html=True)

            # ── ÁSIA ─────────────────────────────────────────────────────────────
            section_title("🌏 ásia — japão e china")

            _asia_c1, _asia_c2 = st.columns(2)

            with _asia_c1:
                section_title("🇯🇵 japão")
                try:
                    import yfinance as yf
                    _nk = yf.Ticker('^N225').history(
                        period='5y', auto_adjust=True
                    )['Close'].dropna()
                    _usdjpy = yf.Ticker('JPY=X').history(
                        period='2y', auto_adjust=True
                    )['Close'].dropna()
                    _boj_ser = df_global['IRSTCB01JPM156N'].dropna()
                    _jpy10y_ser = df_global['IRLTLT01JPM156N'].dropna()
                    _jcols = st.columns(2)
                    with _jcols[0]:
                        if not _nk.empty:
                            _nk_val = float(_nk.iloc[-1])
                            _nk_1y  = float(_nk.iloc[-252]) if len(_nk) >= 252 else _nk_val
                            _nk_ret = (_nk_val / _nk_1y - 1) * 100
                            metric_card(
                                "nikkei 225",
                                f"{_nk_val:,.0f}",
                                f"{_nk_ret:+.1f}% (12m)",
                                "bull" if _nk_ret > 0 else "bear",
                            )
                    with _jcols[1]:
                        if not _usdjpy.empty:
                            _yen_val = float(_usdjpy.iloc[-1])
                            metric_card(
                                "usd/jpy",
                                f"¥ {_yen_val:.1f}",
                                "yen fraco = pressão inflacionária",
                                "bear" if _yen_val > 150 else "amber",
                            )
                    if not _nk.empty:
                        _fig_nk = go.Figure(go.Scatter(
                            x=_nk.index, y=_nk.values,
                            line=dict(color='#FF6B6B', width=2),
                            fill='tozeroy',
                            fillcolor='rgba(255, 107, 107, 0.08)',
                            hovertemplate=(
                                '%{x}<br>nikkei: %{y:,.0f}<extra></extra>'
                            ),
                        ))
                        _lay_nk = base_layout(
                            height=220, title='nikkei 225 (5 anos)'
                        )
                        _fig_nk.update_layout(**_lay_nk)
                        st.plotly_chart(
                            _fig_nk, use_container_width=True,
                            config={'responsive': True}
                        )
                        st.caption(
                            "nikkei 225: principal índice de ações japonês. "
                            "japão é exportador — yen fraco (usd/jpy alto) "
                            "beneficia exportadores mas pressiona poder de compra. "
                            "boj manteve política ultrafrouxa por décadas; "
                            "mudança de stance é evento macro global relevante."
                        )
                    if not _jpy10y_ser.empty:
                        _fig_jpy10y = go.Figure(go.Scatter(
                            x=_jpy10y_ser.index,
                            y=_jpy10y_ser.values,
                            line=dict(color=_chart_cores()["accent"], width=2),
                            hovertemplate=(
                                '%{x|%b %Y}<br>'
                                'jp 10y: %{y:.2f}%<extra></extra>'
                            ),
                        ))
                        _fig_jpy10y.add_hline(
                            y=1.0, line_color=_chart_cores()["muted"],
                            line_dash='dot', line_width=1,
                            annotation_text='teto ytc histórico 1%',
                            annotation_font_color=_chart_cores()["muted"],
                            annotation_font_size=8,
                        )
                        _lay_jpy10y = base_layout(
                            height=200,
                            title='japão — yield título 10 anos (%)'
                        )
                        _fig_jpy10y.update_layout(**_lay_jpy10y)
                        st.plotly_chart(
                            _fig_jpy10y, use_container_width=True,
                            config={'responsive': True}
                        )
                        st.caption(
                            "yield soberano japonês de 10 anos. "
                            "o boj controlou o yield via ycc (yield curve control) "
                            "por anos — abandono do ycc em 2024 foi evento macro "
                            "histórico, causando apreciação do yen e volatilidade global. "
                            "fonte: fred — irltlt01jpm156n."
                        )
                except Exception as _e_jp:
                    st.info(f"dados japão indisponíveis: {_e_jp}")

            with _asia_c2:
                section_title("🇨🇳 china")
                try:
                    import yfinance as yf
                    _sse = yf.Ticker('000001.SS').history(
                        period='5y', auto_adjust=True
                    )['Close'].dropna()
                    _cny = yf.Ticker('CNY=X').history(
                        period='2y', auto_adjust=True
                    )['Close'].dropna()
                    _cn_cpi_ser = df_global['CHNCPIALLMINMEI'].dropna()
                    _cncols = st.columns(2)
                    with _cncols[0]:
                        if not _sse.empty:
                            _sse_val = float(_sse.iloc[-1])
                            _sse_1y  = float(_sse.iloc[-252]) if len(_sse) >= 252 else _sse_val
                            _sse_ret = (_sse_val / _sse_1y - 1) * 100
                            metric_card(
                                "shanghai composite",
                                f"{_sse_val:,.0f}",
                                f"{_sse_ret:+.1f}% (12m)",
                                "bull" if _sse_ret > 0 else "bear",
                            )
                    with _cncols[1]:
                        if not _cny.empty:
                            _cny_val = float(_cny.iloc[-1])
                            metric_card(
                                "usd/cny",
                                f"¥ {_cny_val:.3f}",
                                "yuan vs dólar",
                                "bear" if _cny_val > 7.2 else "bull",
                            )
                    if not _cn_cpi_ser.empty:
                        _cn_cpi_yoy = _cn_cpi_ser.pct_change(12) * 100
                        _cn_cpi_val = round(
                            float(_cn_cpi_yoy.dropna().iloc[-1]), 2
                        )
                        metric_card(
                            "cpi china (yoy)",
                            f"{_cn_cpi_val:.2f}%",
                            "deflação = risco de armadilha japonesa",
                            "bear" if _cn_cpi_val < 0
                            else "amber" if _cn_cpi_val < 1
                            else "bull",
                        )
                    if not _sse.empty:
                        _fig_sse = go.Figure(go.Scatter(
                            x=_sse.index, y=_sse.values,
                            line=dict(color='#FF4444', width=2),
                            fill='tozeroy',
                            fillcolor='rgba(255, 68, 68, 0.08)',
                            hovertemplate=(
                                '%{x}<br>shanghai: %{y:,.0f}<extra></extra>'
                            ),
                        ))
                        _lay_sse = base_layout(
                            height=220, title='shanghai composite (5 anos)'
                        )
                        _fig_sse.update_layout(**_lay_sse)
                        st.plotly_chart(
                            _fig_sse, use_container_width=True,
                            config={'responsive': True}
                        )
                        st.caption(
                            "shanghai composite: principal índice de ações chinês. "
                            "china é a segunda maior economia do mundo e "
                            "principal parceiro comercial do brasil. "
                            "desaceleração chinesa impacta diretamente "
                            "commodities (minério, soja, petróleo) e o ibov. "
                            "risco deflacionário e crise imobiliária (evergrande) "
                            "são preocupações estruturais."
                        )
                    if not _cn_cpi_ser.empty:
                        _cn_cpi_yoy_serie = _cn_cpi_ser.pct_change(12) * 100
                        _fig_cn_cpi = go.Figure(go.Scatter(
                            x=_cn_cpi_yoy_serie.dropna().index,
                            y=_cn_cpi_yoy_serie.dropna().values,
                            line=dict(color='#FFD700', width=2),
                            hovertemplate=(
                                '%{x|%b %Y}<br>'
                                'cpi china yoy: %{y:.2f}%<extra></extra>'
                            ),
                        ))
                        _fig_cn_cpi.add_hline(
                            y=0, line_color=_chart_cores()["bear"],
                            line_dash='dash', line_width=1,
                            annotation_text='deflação',
                            annotation_font_color=_chart_cores()["bear"],
                            annotation_font_size=9,
                        )
                        _lay_cn_cpi = base_layout(
                            height=200,
                            title='china — inflação cpi yoy (%)'
                        )
                        _fig_cn_cpi.update_layout(**_lay_cn_cpi)
                        st.plotly_chart(
                            _fig_cn_cpi, use_container_width=True,
                            config={'responsive': True}
                        )
                        st.caption(
                            "inflação anual chinesa. cpi abaixo de 0% = deflação. "
                            "deflação persistente indica demanda fraca e "
                            "excesso de capacidade — armadilha japonesa. "
                            "impacta exportações brasileiras via preços de commodities. "
                            "fonte: fred — chncpiallminmei."
                        )
                except Exception as _e_cn:
                    st.info(f"dados china indisponíveis: {_e_cn}")

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
                tooltip("yield_curve")
            with c3:
                metric_card("spread hy crédito", fmt_pct(v_hy, sinal=False) if v_hy is not None else "n/d")
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            if v_t10y2y is not None:
                if v_t10y2y < 0:
                    info_box(
                        tipo   = "bear",
                        titulo = "curva invertida",
                        texto  = "historicamente precede recessão em 12-18 meses. posicionamento defensivo recomendado.",
                        icone  = "⚠",
                    )
                elif 0 <= v_t10y2y <= 0.5:
                    info_box(
                        tipo   = "amber",
                        titulo = "spread estreito",
                        texto  = "ciclo de crédito em atenção.",
                        icone  = "📊",
                    )
            
            _cc_t10 = _chart_cores()
            fig_t10 = criar_grafico_macro(df_global, 'T10Y2Y', "spread 10y-2y (%)", _cc_t10["info"])
            fig_t10.add_hline(y=0, line_color=_cc_t10["bear"], line_dash="dash", line_width=1)
            fig_t10.add_annotation(x=0.01, y=0, xref="paper", text="zona de inversão", font=dict(color=_cc_t10["bear"], size=10, family="Inter, system-ui, sans-serif"), showarrow=False, yshift=-14)
            st.plotly_chart(fig_t10, use_container_width=True, config={'responsive': True})
            st.caption(
                "spread 10y−2y (fred: t10y2y): diferença entre o rendimento do treasury 10 anos e o de "
                "2 anos. quando negativo (curva invertida), historicamente precede recessão em "
                "12-18 meses com ~80% de acerto desde 1970. a inversão ocorre quando o fed sobe "
                "muito os juros curtos enquanto o mercado antecipa desaceleração futura. "
                "leitura: curva invertida há >6 meses = cautela máxima com risco. "
                "desinversão (spread voltando a positivo) pode sinalizar piora iminente, "
                "não melhora — é quando a recessão costuma chegar."
            )

            st.plotly_chart(criar_grafico_macro(df_global, 'VIXCLS', "índice vix (cboe volatility index)", _chart_cores()["bear"]), use_container_width=True, config={'responsive': True})
            st.caption(
                "vix (cboe volatility index): mede a volatilidade implícita das opções do s&p500 "
                "para os próximos 30 dias. apelidado de 'índice do medo'. "
                "abaixo de 15 = mercado complacente, risco de surpresa negativa. "
                "15-25 = zona normal de atenção. 25-35 = stress elevado. acima de 35 = pânico — "
                "historicamente zonas de compra de risco com horizonte 12m+. "
                "leitura: vix subindo junto com queda de bolsa = risco sistêmico. "
                "vix alto com bolsa estável = ruído. pico do vix com reversão = sinal de fundo."
            )

            st.plotly_chart(criar_grafico_macro(df_global, 'BAMLH0A0HYM2', "spread crédito high yield (%)", "#E040FB"), use_container_width=True, config={'responsive': True})
            st.caption(
                "spread high yield (ice bofa us hy index — fred: bamlh0a0hym2): diferença de rendimento "
                "entre títulos corporativos de alto risco (high yield / junk) e o treasury equivalente. "
                "spread baixo (<300 bps) = apetite a risco elevado, crédito fácil. "
                "spread alto (>600 bps) = stress de crédito, aperto financeiro. "
                "leitura: spread de hy subindo rapidamente (+150 bps em 30d) é um dos sinais mais "
                "antecedentes de recessão e de stress em mercados emergentes — precede quedas de bolsa."
            )

            # ── 🌉 PONTE 1: MONITOR DE CARRY TRADE ───────────────────────────
            st.markdown("---")
            section_title("💱 monitor de carry trade — prêmio de juros brasil vs eua")

            # Cálculo do spread de carry
            _v_fed   = valor_atual_seguro(df_global, 'FEDFUNDS')
            _v_cpi_y = valor_atual_seguro(df_global, 'CPI_YOY')
            _v_selic_r_risco = None
            _v_real_fed = None
            _carry_spread = None

            try:
                _v_selic_spot = valor_atual_seguro(df_br, 'Selic')
                _v_ipca_12_r  = valor_atual_seguro(df_br, 'IPCA_12M')
                if _v_selic_spot and _v_ipca_12_r:
                    _sr = float(_v_selic_spot) - float(_v_ipca_12_r)
                    if abs(_sr) < 30:
                        _v_selic_r_risco = round(_sr, 2)
                if _v_fed and _v_cpi_y:
                    _v_real_fed = round(float(_v_fed) - float(_v_cpi_y), 2)
                if _v_selic_r_risco is not None and _v_real_fed is not None:
                    _carry_spread = round(_v_selic_r_risco - _v_real_fed, 2)
            except Exception:
                pass

            _cr1, _cr2, _cr3, _cr4 = st.columns(4)
            with _cr1:
                metric_card("selic real (br)", fmt_pct(_v_selic_r_risco, sinal=True) if _v_selic_r_risco else "n/d", "selic − ipca 12m", "bear" if (_v_selic_r_risco or 0) > 8 else "amber")
            with _cr2:
                metric_card("real fed funds (us)", fmt_pct(_v_real_fed, sinal=True) if _v_real_fed is not None else "n/d", "fed funds − cpi yoy", "bear" if (_v_real_fed or 0) > 3 else "bull" if (_v_real_fed or 0) < 0 else "amber")
            with _cr3:
                _carry_cor = "bull" if (_carry_spread or 0) > 6 else "amber" if (_carry_spread or 0) > 3 else "bear"
                metric_card("prêmio de carry br", fmt_pct(_carry_spread, sinal=True) if _carry_spread is not None else "n/d", "selic real − real fed funds", _carry_cor)
            with _cr4:
                _carry_status = (
                    "🟢 carry atrativo — capital tende a fluir para o brasil"
                    if (_carry_spread or 0) > 6
                    else "🟡 carry moderado — fluxo neutro"
                    if (_carry_spread or 0) > 3
                    else "🔴 carry comprimido — risco de saída de capital"
                )
                metric_card("status do carry", "atrativo" if (_carry_spread or 0) > 6 else "moderado" if (_carry_spread or 0) > 3 else "comprimido", _carry_status, _carry_cor)

            # Gráfico histórico do carry spread
            try:
                if 'Selic_Real' in df_br.columns and 'FEDFUNDS' in df_global.columns and 'CPI_YOY' in df_global.columns:
                    _real_fed_hist = (df_global['FEDFUNDS'] - df_global['CPI_YOY']).dropna()
                    _selic_real_hist = df_br['Selic_Real'].dropna()
                    # Alinha os índices
                    _idx_comum = _selic_real_hist.index.intersection(_real_fed_hist.index)
                    if len(_idx_comum) > 12:
                        _carry_hist = (_selic_real_hist.reindex(_idx_comum, method='ffill') - _real_fed_hist.reindex(_idx_comum, method='ffill')).dropna()
                        _fig_carry = go.Figure()
                        # Área de carry positivo (verde)
                        _cc_carry = _chart_cores()
                        _fig_carry.add_trace(go.Scatter(
                            x=_carry_hist.index, y=_carry_hist.values,
                            name="carry spread (pp)", fill='tozeroy',
                            fillcolor=f'{_cc_carry["bull"]}1a',
                            line=dict(color=_cc_carry["bull"], width=2),
                            hovertemplate='%{x|%b %Y}<br>carry: %{y:.2f}pp<extra></extra>',
                        ))
                        _fig_carry.add_trace(go.Scatter(
                            x=_selic_real_hist.index, y=_selic_real_hist.values,
                            name="selic real (br)", line=dict(color=_cc_carry["amber"], width=1.5, dash='dot'), opacity=0.7,
                            hovertemplate='selic real: %{y:.2f}%<extra></extra>',
                        ))
                        _fig_carry.add_trace(go.Scatter(
                            x=_real_fed_hist.index, y=_real_fed_hist.values,
                            name="real fed funds (us)", line=dict(color='#00B0FF', width=1.5, dash='dot'), opacity=0.7,
                            hovertemplate='real fed funds: %{y:.2f}%<extra></extra>',
                        ))
                        _fig_carry.add_hline(y=6, line_color=_cc_carry["bull"],  line_dash='dash', line_width=1, annotation_text='carry atrativo (6pp)', annotation_font_color=_cc_carry["bull"],  annotation_font_size=9)
                        _fig_carry.add_hline(y=3, line_color=_cc_carry["amber"], line_dash='dash', line_width=1, annotation_text='mínimo atrativo (3pp)', annotation_font_color=_cc_carry["amber"], annotation_font_size=9)
                        _fig_carry.add_hline(y=0, line_color=_cc_carry["bear"],  line_dash='solid', line_width=1)
                        _fig_carry.update_layout(**base_layout(height=300, title="carry trade br-us: selic real − real fed funds (pp)"))
                        st.plotly_chart(_fig_carry, use_container_width=True, config={'responsive': True})
                        st.caption(
                            "carry spread = selic real brasileira − real fed funds americano. "
                            "acima de 6pp: capital externo tem incentivo forte para entrar no brasil "
                            "(carry trade) → tendência de apreciação do real e fluxo para bolsa. "
                            "abaixo de 3pp: carry pouco atrativo → risco de saída de capital, "
                            "depreciação do real e pressão inflacionária. "
                            "o carry spread explica ~60-70% dos movimentos do câmbio no médio prazo. "
                            "leitura: quando o fed corta juros (real fed funds cai), o spread br amplia "
                            "automaticamente sem o bcb precisar mexer na selic — vento favorável."
                        )
                else:
                    st.info("carry trade: dados históricos insuficientes para o gráfico.")
            except Exception as _e_carry:
                logger.warning(f"[macro] Carry trade chart falhou: {_e_carry}")

        elif aba_sel == "🛢️ commodities":
            _commodities_config = [
                # minério de ferro — driver #1 do ibovespa via VALE3
                ("TIO=F",  "minério de ferro", "#FF6B35", "us$/ton",    "VALE3.SA", "vale3"),
                ("CL=F",   "petróleo wti",     "#8B00FF", "us$/barril", "^GSPC",    "s&p500"),
                ("GC=F",   "ouro",             "#FFD700", "us$/onça",   "^TNX",     "treasury 10y"),
                ("SI=F",   "prata",            "#C0C0C0", "us$/onça",   "GC=F",     "ouro"),
                ("HG=F",   "cobre",            "#B87333", "us$/libra",  "^GSPC",    "s&p500"),
                ("NG=F",   "gás natural",      "#00BFFF", "us$/mmbtu",  "CL=F",     "petróleo"),
                ("ZC=F",   "milho",            "#F5C518", "us$/bushel", "BOVA11.SA", "ibov"),
                ("ZS=F",   "soja",             "#90EE90", "us$/bushel", "BOVA11.SA", "ibov"),
                ("ZW=F",   "trigo",            "#DEB887", "us$/bushel", "ZC=F",     "milho"),
                ("KC=F",   "café",             "#6F4E37", "us$/libra",  "BRL=X",    "usd/brl"),
                ("SB=F",   "açúcar",           "#FF69B4", "us$/libra",  "BRL=X",    "usd/brl"),
                ("CT=F",   "algodão",          "#F5F5DC", "us$/libra",  "^GSPC",    "s&p500"),
                ("PL=F",   "platina",          "#E5E4E2", "us$/onça",   "GC=F",     "ouro"),
            ]

            # Análise interpretativa por commodity (contexto macro + impacto Brasil)
            _COMM_ANALISE = {
                "TIO=F": (
                    "minério de ferro: driver #1 do ibovespa. vale3 representa ~10% do índice e "
                    "sua receita é quase inteiramente em ferro para a china (~70% do consumo global). "
                    "acima de us$100/t: vale distribui dividendos generosos e sustenta o ibovespa. "
                    "abaixo de us$80/t: pressão nos lucros da vale e impacto direto no índice. "
                    "leitura: minério + pmi industrial chinês = indicador conjunto mais importante "
                    "para quem investe em brasil via ibovespa."
                ),
                "CL=F": (
                    "petróleo wti: referência americana. impacto duplo no brasil — "
                    "receitas da petrobras (60% dolarizadas) vs custo de combustíveis para a economia. "
                    "acima de us$80/barril: petr3/petr4 se valorizam e a arrecadação federal cresce. "
                    "abaixo de us$60/barril: modelo de dividendos da petrobras fica sob pressão. "
                    "leitura: petróleo + dólar = rentabilidade da petrobras (o maior peso do ibov junto com vale)."
                ),
                "GC=F": (
                    "ouro: proteção clássica contra inflação, crises e desvalorização monetária. "
                    "correlação negativa com dólar forte (dxy) e positiva com incerteza geopolítica. "
                    "leitura: ouro subindo enquanto s&p500 cai = flight to safety (risk-off global). "
                    "ouro + bolsa subindo juntos = excesso de liquidez. ratio ouro/prata>80x = "
                    "prata historicamente barata. acima de us$2.500/onça: novo regime de alta."
                ),
                "HG=F": (
                    "cobre ('dr. cobre'): leading indicator de atividade industrial global. "
                    "correlação direta com pmi industrial chinês e americano. "
                    "queda >10% em 30 dias historicamente precede desaceleração do pib global em 3-6 meses. "
                    "leitura: cobre caindo = sinal antecedente de desaceleração. "
                    "para o brasil: impacto indireto via sentimento sobre emergentes e exportadoras. "
                    "high copper + high iron ore = super ciclo de commodities industriais."
                ),
                "NG=F": (
                    "gás natural henry hub (eua): impacto no brasil principalmente via custo industrial "
                    "e inflação global de energia. gás caro = desvantagem competitiva para indústria "
                    "e pressão inflacionária. para o brasil: relevante nos períodos de escassez hídrica "
                    "quando as termelétricas são acionadas (custo da energia elétrica sobe). "
                    "leitura: gás natural + petróleo alto = stagflação energética global."
                ),
                "ZS=F": (
                    "soja: brasil é o maior exportador mundial (~55% do mercado global). "
                    "preço alto gera superávit comercial, aprecia o real e beneficia agro (agro3, slce3, slc5). "
                    "drivers: demanda chinesa por ração animal + clima na safra br (set-jan) e eua (mai-ago). "
                    "leitura: acima de us$1.300/bushel, exportadores br ampliam margens. "
                    "safra recorde de soja + milho = pressão de baixa nos preços (lei da oferta)."
                ),
                "ZC=F": (
                    "milho: segunda maior commodity agrícola brasileira. "
                    "correlação com soja via rotação de culturas (produtor escolhe entre as duas). "
                    "demanda americana para etanol é variável crítica (renewable fuel standard). "
                    "leitura: milho + soja altos juntos = super ciclo agrícola — favorece real e ibov. "
                    "milho caro + soja cara = pressão nos custos de proteína animal (inflação alimentar)."
                ),
                "ZW=F": (
                    "trigo: brasil é importador líquido (sul do brasil produz, mas insuficiente). "
                    "alta de trigo → pressão no ipca via alimentos industrializados e panificação. "
                    "geopolítica: ucrânia + rússia respondem por 30% das exportações mundiais. "
                    "leitura: guerra no leste europeu = diretamente inflacionária via trigo para o brasil. "
                    "trigo acima de us$7/bushel = sinal de atenção para inflação de alimentos."
                ),
                "KC=F": (
                    "café arábica: brasil produz ~35% do café mundial. "
                    "exportações geram us$8-10bi/ano em divisas. "
                    "sensível a eventos climáticos no cerrado e sul de minas (geadas em jul-ago). "
                    "leitura: café acima de us$2/libra = exportadores brasileiros ampliam receita. "
                    "pico de preço pós-geada tende a normalizar em 12-18 meses via replantio. "
                    "brasil café3 (b3) e cooperativas do sul de minas são os principais beneficiários."
                ),
                "SB=F": (
                    "açúcar: brasil responde por ~30% da produção mundial. "
                    "correlação com petróleo: usinas alternam entre açúcar e etanol de cana-de-açúcar — "
                    "petróleo alto → mais etanol → menos açúcar → preço do açúcar sobe. "
                    "leitura: petróleo + açúcar subindo juntos = ambiente positivo para raiz4, smto3. "
                    "acima de us$0.25/libra: margens das usinas ficam muito favoráveis."
                ),
                "CT=F": (
                    "algodão: brasil é o 5º maior produtor mundial, concentrado no cerrado (mt, go, ba). "
                    "exportações cresceram fortemente na última década. "
                    "demanda ligada ao setor têxtil global — desaceleração da china impacta. "
                    "leitura: algodão acima de us$0.90/libra beneficia exportadores brasileiros. "
                    "correlação com pmi manufatura global — queda do algodão pode sinalizar "
                    "desaceleração do consumo de vestuário em mercados desenvolvidos."
                ),
                "PL=F": (
                    "platina: metal do grupo pgm (platinum group metals). "
                    "uso principal em catalisadores automotivos (carros a combustão). "
                    "risco estrutural: transição para veículos elétricos reduz demanda por pgm. "
                    "ratio platina/ouro abaixo de 0.5x = platina historicamente barata vs ouro. "
                    "leitura: platina vs ouro é um proxy de otimismo para o ciclo industrial e "
                    "combustão interna. alta = aposta em ciclo industrial. queda = transição energética."
                ),
            }

            # ── CESTA DE EXPORTAÇÃO BRASILEIRA ───────────────────────────────────
            section_title("🇧🇷 cesta de exportação brasileira")
            st.caption(
                "índice ponderado das principais commodities exportadas pelo brasil, "
                "refletindo aproximadamente a pauta exportadora nacional. "
                "sobe quando o brasil ganha poder de compra no mercado externo → "
                "favorece o real, reduz risco fiscal e cria ambiente para corte de juros."
            )

            _CESTA_PESOS = {
                "TIO=F": 0.28,   # minério de ferro ~28% da pauta
                "CL=F":  0.24,   # petróleo ~24%
                "ZS=F":  0.22,   # soja ~22%
                "SB=F":  0.08,   # açúcar ~8%
                "KC=F":  0.08,   # café ~8%
                "HG=F":  0.05,   # cobre/metais ~5%
                "CT=F":  0.05,   # algodão ~5%
            }
            _periodo_cesta = st.radio(
                "período cesta:", ["6mo", "1y", "2y"],
                format_func=lambda x: {"6mo": "6 meses", "1y": "1 ano", "2y": "2 anos"}[x],
                horizontal=True, key="radio_cesta_exp",
            )
            with st.spinner("calculando cesta de exportação..."):
                _series_cesta = {}
                for _tk_c, _w_c in _CESTA_PESOS.items():
                    try:
                        _h = yf.Ticker(_tk_c).history(period=_periodo_cesta, auto_adjust=True)['Close'].dropna()
                        if not _h.empty:
                            _series_cesta[_tk_c] = (_h / _h.iloc[0]) * 100  # base 100
                    except Exception:
                        pass

            if _series_cesta:
                _df_cesta = pd.DataFrame(_series_cesta).dropna()
                # índice ponderado
                _pesos_disp = {k: _CESTA_PESOS[k] for k in _df_cesta.columns if k in _CESTA_PESOS}
                _soma_pesos = sum(_pesos_disp.values())
                _cesta_idx = sum(_df_cesta[k] * v for k, v in _pesos_disp.items()) / _soma_pesos

                _fig_cesta = go.Figure()
                _fig_cesta.add_trace(go.Scatter(
                    x=_cesta_idx.index, y=_cesta_idx.values,
                    name="cesta exportação br", fill="tozeroy",
                    fillcolor="rgba(255,107,53,0.10)",
                    line=dict(color="#FF6B35", width=2.5),
                    hovertemplate="cesta: %{y:.1f}<extra></extra>",
                ))
                # Adiciona linhas individuais com baixa opacidade
                _NOMES_CESTA = {"TIO=F":"minério","CL=F":"petróleo","ZS=F":"soja",
                                "SB=F":"açúcar","KC=F":"café","HG=F":"cobre","CT=F":"algodão"}
                _CORES_CESTA = {"TIO=F":"#FF6B35","CL=F":"#8B00FF","ZS=F":"#90EE90",
                                "SB=F":"#FF69B4","KC=F":"#6F4E37","HG=F":"#B87333","CT=F":"#F5F5DC"}
                for _k, _s in _df_cesta.items():
                    _fig_cesta.add_trace(go.Scatter(
                        x=_s.index, y=_s.values,
                        name=_NOMES_CESTA.get(_k, _k), opacity=0.35,
                        line=dict(color=_CORES_CESTA.get(_k, "#888"), width=1, dash="dot"),
                        hovertemplate=f"{_NOMES_CESTA.get(_k,'?')}: %{{y:.1f}}<extra></extra>",
                    ))
                _fig_cesta.add_hline(y=100, line_color=_chart_cores()["muted"], line_dash="dash", line_width=1)
                _fig_cesta.update_layout(**base_layout(height=280, title="cesta de exportação brasileira (base 100)"))
                st.plotly_chart(_fig_cesta, use_container_width=True, config={'responsive': True})
                _ret_cesta = float(_cesta_idx.iloc[-1]) - 100
                _nm_disp = [_NOMES_CESTA.get(k, k) for k in _df_cesta.columns]
                st.caption(
                    f"retorno da cesta no período: {_ret_cesta:+.1f}% (base 100 no início). "
                    f"componentes com dados: {', '.join(_nm_disp)}. "
                    f"pesos: minério 28% · petróleo 24% · soja 22% · açúcar 8% · café 8% · cobre 5% · algodão 5%. "
                    "cesta acima de 100 → pauta exportadora valorizada → câmbio e balança comercial favoráveis."
                )
            else:
                st.caption("cesta de exportação: dados temporariamente indisponíveis.")

            # ── 🌉 PONTE 3: CADEIA DE TRANSMISSÃO COMMODITIES→EMPRESAS ─────────
            st.markdown("---")
            section_title("⛓️ cadeia de transmissão — commodities → empresas brasileiras")
            st.caption(
                "impacto estimado dos preços de commodities nos fundamentos das principais "
                "empresas da b3. coeficientes baseados em dados públicos de produção e filings. "
                "use como indicador direcional, não como previsão de lucro."
            )

            # Definição das empresas e suas sensibilidades
            # Formato: (ticker_yf, nome, commodity_tk, nome_comm, unidade, base_price,
            #           sensit_label, sensit_formula_str, direcao, cor)
            _TRANSMISSAO = [
                {
                    "empresa":       "Vale",
                    "ticker":        "VALE3.SA",
                    "comm_tk":       "TIO=F",
                    "comm_nome":     "minério de ferro",
                    "unidade":       "us$/ton",
                    "base":          90.0,    # preço base de referência
                    "delta_label":   "cada us$10/t acima de us$90",
                    "ebitda_delta":  4.0,     # R$bi de EBITDA adicional por $10/t (a 5.5 BRL/USD, ~330Mt prod)
                    "dy_delta":      0.015,   # variação de DY (pp) por $10/t
                    "logica":        "long — sobe com minério",
                    "cor":           "#FF6B35",
                    "nota":          "produção ~330Mt/a · preço cif china",
                },
                {
                    "empresa":       "Petrobras",
                    "ticker":        "PETR3.SA",
                    "comm_tk":       "CL=F",
                    "comm_nome":     "petróleo wti",
                    "unidade":       "us$/barril",
                    "base":          70.0,
                    "delta_label":   "cada us$10/bbl acima de us$70",
                    "ebitda_delta":  15.0,   # R$bi adicionais por $10/bbl (2.8Mboe/d × 365 × 5.5)
                    "dy_delta":      0.020,
                    "logica":        "long — sobe com petróleo",
                    "cor":           "#8B00FF",
                    "nota":          "produção ~2.8Mboe/d · dividend policy: 45% lucro líquido",
                },
                {
                    "empresa":       "Suzano",
                    "ticker":        "SUZB3.SA",
                    "comm_tk":       "BZUN",    # proxy — celulose não tem ticker yfinance direto
                    "comm_nome":     "celulose (bhkp — proxy)",
                    "unidade":       "us$/ton",
                    "base":          650.0,
                    "delta_label":   "cada us$100/t acima de us$650",
                    "ebitda_delta":  3.5,    # R$bi por $100/t (11Mt de prod × 100 × 5.5 / 1000)
                    "dy_delta":      0.010,
                    "logica":        "long — sobe com celulose",
                    "cor":           "#00C853",
                    "nota":          "produção ~11Mt/a bhkp · suzano = maior produtora mundial",
                },
                {
                    "empresa":       "JBS",
                    "ticker":        "JBSS3.SA",
                    "comm_tk":       "ZC=F",
                    "comm_nome":     "milho (proxy custo ração)",
                    "unidade":       "us$/bushel",
                    "base":          4.5,
                    "delta_label":   "cada us$1/bushel acima de us$4.50",
                    "ebitda_delta":  -2.0,   # negativo — é custo de produção
                    "dy_delta":      -0.008,
                    "logica":        "short — milho caro comprime margens",
                    "cor":           "#FF9800",
                    "nota":          "milho + soja são ~65% do custo de ração · jbs produz ~35Mboe equiv.",
                },
                {
                    "empresa":       "Gerdau",
                    "ticker":        "GGBR4.SA",
                    "comm_tk":       "TIO=F",
                    "comm_nome":     "minério de ferro (custo)",
                    "unidade":       "us$/ton",
                    "base":          90.0,
                    "delta_label":   "cada us$10/t acima de us$90",
                    "ebitda_delta":  -0.8,   # efeito negativo líquido (custo > benefício de demanda)
                    "dy_delta":      -0.004,
                    "logica":        "neutro/negativo — minério é custo para siderurgia",
                    "cor":           "#B87333",
                    "nota":          "siderurgia integrada · minério é ~30% do custo de produção",
                },
            ]

            _trans_cols = st.columns(len(_TRANSMISSAO))
            for _ti, _t in enumerate(_TRANSMISSAO):
                with _trans_cols[_ti]:
                    # Busca preço atual da commodity
                    _tk_comm = _t["comm_tk"]
                    _preco_comm = None
                    _delta_vs_base = None
                    try:
                        _h_comm = yf.Ticker(_tk_comm).history(period="5d", auto_adjust=True)['Close'].dropna()
                        if not _h_comm.empty:
                            _preco_comm = float(_h_comm.iloc[-1])
                            _delta_vs_base = _preco_comm - _t["base"]
                    except Exception:
                        pass

                    if _preco_comm is not None:
                        _impacto_ebitda = _t["ebitda_delta"] * (_delta_vs_base / (10 if _t["unidade"] != "us$/bushel" else 1))
                        _sinal = "📈" if _impacto_ebitda > 0 else "📉"
                        _cor_imp = "bull" if _impacto_ebitda > 0 else "bear"
                    else:
                        _impacto_ebitda = None
                        _sinal = "—"
                        _cor_imp = "muted"

                    st.markdown(
                        f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
                        f'border-top:3px solid {_t["cor"]};border-radius:6px;'
                        f'padding:12px;margin-bottom:8px;font-family:var(--font-ui,sans-serif);font-size:0.7rem;">'
                        f'<div style="color:{_t["cor"]};font-weight:bold;font-size:0.75rem;margin-bottom:6px;">'
                        f'{_t["empresa"]}</div>'
                        f'<div style="color:var(--text-muted);font-size:0.62rem;margin-bottom:4px;">{_t["logica"]}</div>'
                        f'<div style="color:var(--text-secondary);margin-bottom:4px;">'
                        f'{_t["comm_nome"]}: <span style="color:var(--text-primary);">'
                        f'{"us${:,.1f}".format(_preco_comm) if _preco_comm else "n/d"}</span></div>'
                        f'<div style="color:var(--text-secondary);margin-bottom:4px;">vs base (us${_t["base"]:.0f}): '
                        f'<span style="color:{"var(--bull)" if (_delta_vs_base or 0) * (1 if _t["ebitda_delta"] > 0 else -1) > 0 else "var(--bear)"};">'
                        f'{"us${:+,.1f}".format(_delta_vs_base) if _delta_vs_base is not None else "n/d"}</span></div>'
                        f'<div style="color:var(--text-secondary);">ebitda implícito: '
                        f'<span style="color:{"var(--bull)" if (_impacto_ebitda or 0) > 0 else "var(--bear)"};">'
                        f'{"R${:+.1f}bi".format(_impacto_ebitda) if _impacto_ebitda is not None else "n/d"}</span></div>'
                        f'<div style="color:var(--text-muted);font-size:0.58rem;margin-top:6px;">{_t["nota"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.caption(
                "ebitda implícito = variação estimada em relação ao preço base de referência, "
                "usando coeficientes de sensibilidade derivados de dados públicos de produção. "
                "verde = commodity favorece a empresa · vermelho = commodity pressiona margens. "
                "valores em r$bi, convertidos à taxa de 5.5 brl/usd (referência). "
                "nota: jbs e gerdau têm sensibilidade inversa (commodity é custo, não receita)."
            )

            st.markdown("---")
            section_title("📊 commodities individuais")

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
                        f'<div style="font-family:var(--font-data,monospace);font-size:0.75rem;color:{_cor};'
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
                            _fig_c.add_hline(y=100, line_color=_chart_cores()["muted"], line_dash='dash', line_width=1)
                            _fig_c.update_layout(**base_layout(height=220, title=f"{_nm} vs {_bn} (base 100)"))
                            st.plotly_chart(_fig_c, use_container_width=True, config={'responsive': True})
                            _ret_b = (float(_hist_b.iloc[-1]) / float(_hist_b.iloc[0]) - 1) * 100
                            st.caption(f"retorno no período: {_nm} {_ret_c:+.1f}% | {_bn} {_ret_b:+.1f}%.")
                            if _tk in _COMM_ANALISE:
                                st.caption(_COMM_ANALISE[_tk])
                            continue

                    _fig_c = go.Figure(go.Scatter(x=_hist_c.index, y=_hist_c.values, line=dict(color=_cor, width=2), fill='tozeroy', fillcolor=_hex_to_rgba(_cor), hovertemplate=f'%{{x}}<br>{_nm}: %{{y:,.2f}} {_un}<extra></extra>'))
                    _fig_c.update_layout(**base_layout(height=200, title=f"{_nm} ({_un})"))
                    st.plotly_chart(_fig_c, use_container_width=True, config={'responsive': True})
                    if _tk in _COMM_ANALISE:
                        st.caption(_COMM_ANALISE[_tk])

                except Exception:
                    st.caption(f"{_nm}: dados indisponíveis")

        elif aba_sel == "📰 macro news":
            col_news1, col_news2 = st.columns(2)
            with col_news1: renderizar_noticias("SPY", "🇺🇸 radar global (spy etf)")
            with col_news2: renderizar_noticias("EWZ", "🇧🇷 radar brasil (ewz etf)")

with tab_ciclo:

    from utils.ciclo_economico import (
        calcular_indicadores_ciclo_br,
        calcular_indicadores_ciclo_us,
        get_alocacao_sugerida,
        FASES_CICLO,
    )

    section_title("🔄 posicionamento no ciclo econômico")

    # Calcula ciclos
    with st.spinner("calculando indicadores do ciclo..."):
        _ciclo_br = calcular_indicadores_ciclo_br()
        _ciclo_us = calcular_indicadores_ciclo_us()

    _fase_br = _ciclo_br.get('fase_provavel', 'expansao')
    _fase_us = _ciclo_us.get('fase_provavel', 'expansao')
    _dados_fase_br = FASES_CICLO.get(_fase_br, FASES_CICLO['expansao'])
    _dados_fase_us = FASES_CICLO.get(_fase_us, FASES_CICLO['expansao'])

    # ── Cards de fase BR e EUA ────────────────────────────────────────
    _cc1, _cc2 = st.columns(2)

    for _col_c, _dados_f, _ciclo, _pais in [
        (_cc1, _dados_fase_br, _ciclo_br, "🇧🇷 brasil"),
        (_cc2, _dados_fase_us, _ciclo_us, "🇺🇸 eua"),
    ]:
        with _col_c:
            _cor_f    = _dados_f['cor']
            _conf     = _ciclo.get('confianca', 0)
            _n_ind    = _ciclo.get('n_indicadores', 0)

            st.markdown(
                f'<div style="background:var(--bg-surface);'
                f'border:1px solid var(--border-subtle);'
                f'border-top:3px solid {_cor_f};'
                f'border-radius:6px;padding:16px;'
                f'margin-bottom:12px;">'

                f'<div style="font-family:var(--font-ui,sans-serif);'
                f'font-size:0.65rem;color:var(--text-muted);'
                f'text-transform:uppercase;'
                f'margin-bottom:4px;">'
                f'{_pais} — fase do ciclo</div>'

                f'<div style="font-size:1.5rem;'
                f'margin-bottom:4px;">'
                f'{_dados_f["icone"]}</div>'

                f'<div style="font-family:var(--font-data,monospace);'
                f'font-size:1rem;font-weight:700;'
                f'color:{_cor_f};margin-bottom:6px;">'
                f'{_dados_f["label"].upper()}</div>'

                f'<div style="font-family:var(--font-ui,sans-serif);'
                f'font-size:0.7rem;color:var(--text-muted);'
                f'line-height:1.6;margin-bottom:10px;">'
                f'{_dados_f["descricao"]}</div>'

                f'<div style="display:flex;gap:16px;'
                f'border-top:1px solid var(--border-subtle);'
                f'padding-top:8px;">'

                f'<div style="text-align:center;">'
                f'<div style="font-size:0.6rem;color:var(--text-muted);'
                f'text-transform:uppercase;">confiança</div>'
                f'<div style="font-family:var(--font-data,monospace);'
                f'color:{_cor_f};font-weight:600;">'
                f'{_conf:.0f}pp</div>'
                f'</div>'

                f'<div style="text-align:center;">'
                f'<div style="font-size:0.6rem;color:var(--text-muted);'
                f'text-transform:uppercase;">indicadores</div>'
                f'<div style="font-family:var(--font-data,monospace);'
                f'color:var(--text-secondary);">{_n_ind} usados</div>'
                f'</div>'

                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            _fase_atual = _ciclo.get('fase_provavel', 'expansao')
            tooltip(f"ciclo_{_fase_atual}")

            # Scores das 4 fases como mini barras
            section_title("probabilidade por fase")
            for _fn, _fk in [
                ("expansão",  "score_expansao"),
                ("pico",      "score_pico"),
                ("contração", "score_contracao"),
                ("vale",      "score_vale"),
            ]:
                _sv = _ciclo.get(_fk, 0)
                _fc = FASES_CICLO.get(
                    _fk.replace('score_', ''), {}
                ).get('cor', '#555')
                _destaque = (
                    _fn.replace('ã', 'a').replace('ç', 'c')
                    in _fase_br if _pais == "🇧🇷 brasil"
                    else _fn.replace('ã', 'a').replace('ç', 'c')
                    in _fase_us
                )
                st.markdown(
                    f'<div style="display:flex;'
                    f'align-items:center;gap:8px;'
                    f'margin-bottom:4px;">'
                    f'<div style="font-family:var(--font-ui,sans-serif);'
                    f'font-size:0.65rem;color:var(--text-muted);'
                    f'min-width:70px;">{_fn}</div>'
                    f'<div style="flex:1;background:var(--bg-elevated,#111);'
                    f'border-radius:2px;height:6px;">'
                    f'<div style="background:{_fc};'
                    f'border-radius:2px;height:6px;'
                    f'width:{_sv}%;"></div>'
                    f'</div>'
                    f'<div style="font-family:var(--font-data,monospace);'
                    f'font-size:0.65rem;'
                    f'color:{"var(--accent)" if _destaque else "var(--text-muted)"};'
                    f'min-width:30px;text-align:right;">'
                    f'{_sv}%</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                tooltip(f"ciclo_{_fk.replace('score_', '')}")

    # ── Alertas dos indicadores ───────────────────────────────────────
    _alertas_todos = (
        _ciclo_br.get('alertas', [])
        + _ciclo_us.get('alertas', [])
    )
    if _alertas_todos:
        st.markdown("<br>", unsafe_allow_html=True)
        section_title("🚨 sinais dos indicadores")
        for _al in _alertas_todos:
            st.markdown(
                f'<div style="font-family:var(--font-ui,sans-serif);'
                f'font-size:0.75rem;color:var(--text-muted);'
                f'padding:4px 0;border-bottom:1px solid var(--border-subtle);">'
                f'{_al}</div>',
                unsafe_allow_html=True,
            )

    # ── Indicadores detalhados ────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("📊 indicadores utilizados")

    _ind_br = _ciclo_br.get('indicadores', {})
    _ind_us = _ciclo_us.get('indicadores', {})

    _ind_cols = st.columns(2)

    _map_labels_br = {
        'selic_real':           ('Selic Real (Selic - IPCA 12m)', '%'),
        'spread_curva_br':      ('Spread Curva BR (IMA-B 5+ vs 5)', 'pp'),
        'ibov_ret_6m':          ('Retorno IBOV 6 meses', '%'),
        'ibov_acima_mm200':     ('IBOV acima da MM200', ''),
        'usd_brl':              ('USD/BRL atual', 'R$'),
        'usd_brl_vs_media':     ('USD/BRL vs Média 60d', '%'),
    }
    _map_labels_us = {
        'yield_curve_spread':   ('Yield Curve 10y-2y', 'pp'),
        'sp500_ret_6m':         ('Retorno S&P500 6 meses', '%'),
        'sp500_acima_mm200':    ('S&P500 acima da MM200', ''),
        'credit_spread_trend':  ('Credit Spreads HYG/IEF (3m)', '%'),
        'fed_funds_gap':        ('Fed Funds vs Neutro (r*)', 'pp'),
        'vix':                  ('VIX', 'pts'),
    }

    with _ind_cols[0]:
        st.markdown(
            '<div style="font-family:var(--font-ui,sans-serif);'
            'font-size:0.68rem;color:var(--accent);'
            'margin-bottom:8px;">🇧🇷 indicadores br</div>',
            unsafe_allow_html=True,
        )
        for _k, (_lbl, _un) in _map_labels_br.items():
            _v = _ind_br.get(_k)
            if _v is None:
                continue
            _v_str = (
                ("✅" if _v else "❌")
                if isinstance(_v, bool)
                else f"{_v}{_un}"
            )
            st.markdown(
                f'<div style="display:flex;'
                f'justify-content:space-between;'
                f'padding:3px 0;border-bottom:1px solid var(--border-subtle);">'
                f'<span style="font-family:var(--font-ui,sans-serif);'
                f'font-size:0.68rem;color:var(--text-muted);">{_lbl}</span>'
                f'<span style="font-family:var(--font-data,monospace);'
                f'font-size:0.72rem;color:var(--text-secondary);">{_v_str}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with _ind_cols[1]:
        st.markdown(
            '<div style="font-family:var(--font-ui,sans-serif);'
            'font-size:0.68rem;color:var(--accent);'
            'margin-bottom:8px;">🇺🇸 indicadores eua</div>',
            unsafe_allow_html=True,
        )
        for _k, (_lbl, _un) in _map_labels_us.items():
            _v = _ind_us.get(_k)
            if _v is None:
                continue
            _v_str = (
                ("✅" if _v else "❌")
                if isinstance(_v, bool)
                else f"{_v}{_un}"
            )
            st.markdown(
                f'<div style="display:flex;'
                f'justify-content:space-between;'
                f'padding:3px 0;border-bottom:1px solid var(--border-subtle);">'
                f'<span style="font-family:var(--font-ui,sans-serif);'
                f'font-size:0.68rem;color:var(--text-muted);">{_lbl}</span>'
                f'<span style="font-family:var(--font-data,monospace);'
                f'font-size:0.72rem;color:var(--text-secondary);">{_v_str}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Recomendações setoriais por fase ─────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("🎯 setores favorecidos nesta fase")

    _rec_cols = st.columns(2)

    for _col_r, _dados_f, _pais in [
        (_rec_cols[0], _dados_fase_br, "🇧🇷 br"),
        (_rec_cols[1], _dados_fase_us, "🇺🇸 eua"),
    ]:
        with _col_r:
            st.markdown(
                f'<div style="font-family:var(--font-ui,sans-serif);'
                f'font-size:0.68rem;color:{_dados_f["cor"]};'
                f'margin-bottom:6px;font-weight:600;">'
                f'{_pais} — {_dados_f["label"]}</div>',
                unsafe_allow_html=True,
            )

            _key_set = (
                'setores_br' if _pais == "🇧🇷 br"
                else 'setores_us'
            )

            st.markdown(
                '<div style="font-size:0.6rem;color:var(--bull);'
                'text-transform:uppercase;margin-bottom:3px;">'
                '✅ favorecidos</div>',
                unsafe_allow_html=True,
            )
            for _sf in _dados_f[_key_set]['favorecidos']:
                st.markdown(
                    f'<div style="font-family:var(--font-ui,sans-serif);'
                    f'font-size:0.72rem;color:var(--bull);'
                    f'padding:2px 0;">→ {_sf}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                '<div style="font-size:0.6rem;color:var(--bear);'
                'text-transform:uppercase;margin:8px 0 3px;">'
                '✗ evitar</div>',
                unsafe_allow_html=True,
            )
            for _se in _dados_f[_key_set]['evitar']:
                st.markdown(
                    f'<div style="font-family:var(--font-ui,sans-serif);'
                    f'font-size:0.72rem;color:var(--bear);'
                    f'padding:2px 0;">→ {_se}</div>',
                    unsafe_allow_html=True,
                )

    # ── Alocação sugerida ─────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("💼 alocação sugerida para o ciclo atual")

    _alloc = get_alocacao_sugerida(_fase_br, _fase_us)

    _alloc_cols = st.columns(len(_alloc))
    _alloc_cores = {
        'ações br':   '#FF9900',
        'ações eua':  '#00B0FF',
        'fiis':       '#00C853',
        'renda fixa': '#555555',
    }

    for _col_a, (_classe, _pct) in zip(
        _alloc_cols, _alloc.items()
    ):
        with _col_a:
            metric_card(
                _classe,
                f"{_pct}%",
                "sugestão pelo ciclo",
                cor_delta="amber",
            )

    st.caption(
        "alocação derivada mecanicamente das fases identificadas. "
        "br: 60% do peso | eua: 40% do peso. "
        "não constitui recomendação de investimento. "
        "ajuste conforme seu perfil e horizonte."
    )

    # ── Análise IA do ciclo ───────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(
        "🧠 ia: análise profunda do ciclo econômico",
        type="primary",
        use_container_width=True,
        key="btn_ia_ciclo",
    ):
        _ind_br_txt = "\n".join([
            f"- {k}: {v}"
            for k, v in _ind_br.items()
        ])
        _ind_us_txt = "\n".join([
            f"- {k}: {v}"
            for k, v in _ind_us.items()
        ])
        _alertas_txt = "\n".join(
            _alertas_todos[:8]
        ) or "nenhum alerta crítico"

        _prompt_ciclo = (
            f"análise do ciclo econômico atual:\n\n"
            f"brasil — fase: {_fase_br} "
            f"(confiança: {_ciclo_br.get('confianca',0):.0f}pp)\n"
            f"indicadores br:\n{_ind_br_txt}\n\n"
            f"eua — fase: {_fase_us} "
            f"(confiança: {_ciclo_us.get('confianca',0):.0f}pp)\n"
            f"indicadores eua:\n{_ind_us_txt}\n\n"
            f"alertas dos indicadores:\n{_alertas_txt}\n\n"
            f"alocação sugerida pelo modelo: "
            + ", ".join([
                f"{k}: {v}%"
                for k, v in _alloc.items()
            ]) +
            "\n\nem 5 tópicos diretos (letra minúscula):\n"
            "1. em qual fase do ciclo estamos e qual a "
            "principal evidência?\n"
            "2. qual o risco de virada de fase nos próximos "
            "3-6 meses e qual indicador monitorar?\n"
            "3. historicamente quanto tempo dura esta fase "
            "e como termina?\n"
            "4. para o investidor br: qual a principal "
            "oportunidade e o principal risco agora?\n"
            "5. a alocação sugerida pelo modelo faz sentido "
            "para este momento? ajuste se necessário."
        )

        from utils.ai_client import chamar_ia
        _system_ciclo = (
            "você é um economista especializado em ciclos "
            "econômicos e alocação de ativos. use fama-french, "
            "nber methodology e exemplos históricos. "
            "seja preciso, use dados fornecidos. minúsculas."
        )
        _us_ciclo = st.session_state.get('user_settings', {})
        chamar_ia(
            prompt_usuario = _prompt_ciclo,
            system         = _system_ciclo,
            max_tokens     = 900,
            temperatura    = 0.3,
            stream         = True,
            user_settings  = _us_ciclo,
        )

with tab_calendar:
    section_title("📅 calendário de eventos de mercado")

    cal_tab1, cal_tab2 = st.tabs(["🏛️ decisões macro", "📊 earnings"])

    # ── Tab: Decisões Macro ─────────────────────────────────────────────────
    with cal_tab1:
        status_card(
            "cobertura",
            "eventos macro fixos (copom, fed, cpi, payroll) — próximos 90 dias.",
            tipo="info"
        )
        fc1, fc2 = st.columns([3, 1])
        with fc1:
            filtro_cat = st.multiselect(
                "filtrar por categoria:",
                ["brasil", "eua"],
                default=["brasil", "eua"],
                key="cal_filtro_cat"
            )
        with fc2:
            janela_dias = st.selectbox("janela:", [30, 60, 90], index=2, key="cal_janela")

        hoje = datetime.date.today()
        limite_cal = hoje + datetime.timedelta(days=janela_dias)
        eventos_macro = get_eventos_macro_fixos()
        eventos_macro = [e for e in eventos_macro if e['categoria'] in filtro_cat and e['data'] <= limite_cal]

        if not eventos_macro:
            empty_state("📅", "sem eventos", f"nenhum evento macro nos próximos {janela_dias} dias.")
        else:
            mc1, mc2 = st.columns(2)
            with mc1:
                prox_7 = len([e for e in eventos_macro if e['data'] <= hoje + datetime.timedelta(days=7)])
                metric_card("próximos 7 dias", str(prox_7), "" if prox_7 > 0 else "nenhum", "bear" if prox_7 > 0 else "muted")
            with mc2:
                total_alto = len([e for e in eventos_macro if e['impacto'] == 'alto'])
                metric_card("alto impacto", str(total_alto), f"de {len(eventos_macro)} eventos", "amber")
            for ev in eventos_macro:
                _render_evento_card(ev, key_prefix=f"macro_{ev.get('_uid','')}")

    # ── Tab: Earnings ───────────────────────────────────────────────────────
    with cal_tab2:
        status_card(
            "cobertura",
            "earnings dates de todas as empresas disponíveis no FMP. cache de 1h.",
            tipo="info"
        )
        ec1, ec2 = st.columns([3, 1])
        with ec1:
            filtro_ticker = st.text_input("filtrar ticker (opcional):", placeholder="ex: AAPL, MSFT...", key="cal_filtro_ticker")
        with ec2:
            janela_earn = st.selectbox("janela:", [30, 60, 90], index=2, key="cal_janela_earnings")

        hoje_earn = datetime.date.today()
        limite_earn = hoje_earn + datetime.timedelta(days=janela_earn)

        with st.spinner("buscando earnings dates via FMP..."):
            eventos_earnings = buscar_earnings_calendario(
                data_fim_str=limite_earn.strftime("%Y-%m-%d"),
            )

        # earnings events have string dates; compare as strings
        limite_str = limite_earn.strftime("%Y-%m-%d")
        eventos_earnings = [e for e in eventos_earnings if e.get('data') and e['data'] <= limite_str]

        if filtro_ticker:
            _ft = filtro_ticker.strip().upper().replace(".SA", "")
            eventos_earnings = [e for e in eventos_earnings if _ft in e.get("ticker", "").upper()]

        if not eventos_earnings:
            empty_state("📊", "sem earnings", f"nenhum earnings nos próximos {janela_earn} dias.")
        else:
            ec_a, ec_b, ec_c = st.columns(3)
            with ec_a:
                prox7_str = (hoje_earn + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
                prox_7 = len([e for e in eventos_earnings if e['data'] <= prox7_str])
                metric_card("próximos 7 dias", str(prox_7), "" if prox_7 > 0 else "nenhum", "bear" if prox_7 > 0 else "muted")
            with ec_b:
                com_est = len([e for e in eventos_earnings if e.get('eps_est') is not None])
                metric_card("com estimativa", str(com_est), f"de {len(eventos_earnings)}", "amber")
            with ec_c:
                metric_card("total na janela", str(len(eventos_earnings)), f"{janela_earn} dias", "muted")
            for ev in eventos_earnings:
                _render_evento_card(ev, key_prefix=f"earn_{ev.get('ticker','')}_{ev.get('data','')}")

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
                        _cc_ov = _chart_cores()
                        fig.add_trace(go.Scatter(x=stock_data.index, y=stock_data, name=ticker_input.lower(), line=dict(color=_cc_ov["accent"], width=2)), secondary_y=False)
                        fig.add_trace(go.Scatter(x=macro_data.index, y=macro_data, name=macro_name, line=dict(color=_cc_ov["info"], dash="dot", width=2)), secondary_y=True)

                        layout_macro = base_layout(height=500, title=f"estudo de correlação: {ticker_input.lower()} vs {macro_name}")
                        fig.update_layout(**layout_macro)
                        fig.update_yaxes(title_text=f"preço {ticker_input.lower()}", showgrid=True, gridcolor=_cc_ov["border"], secondary_y=False)
                        fig.update_yaxes(title_text=macro_name, showgrid=False, secondary_y=True)
                        fig.update_xaxes(showgrid=True, gridcolor=_cc_ov["border"])

                        st.plotly_chart(fig, use_container_width=True, config={'responsive': True})
                    else: st.warning("não foi possível obter a série de dados macroeconómicos.")
                except Exception as e: st.error(f"erro ao processar e alinhar os dados: {e}")

with tab_sentimento:
    section_title("😱 fear & greed — eua | brasil | global")
    tooltip("fear_greed")

    with st.spinner("calculando índices de sentimento..."):
        # Cache-first: tenta Supabase (4h TTL), senão calcula live
        _fg_eua = carregar_fear_greed("us", max_age_hours=4)
        if _fg_eua is None:
            _fg_eua = calcular_fear_greed()
            salvar_fear_greed("us", _fg_eua.get('score', 50),
                              _fg_eua.get('label', 'neutro'),
                              _fg_eua.get('componentes', {}))

        _fg_br = carregar_fear_greed("br", max_age_hours=4)
        if _fg_br is None:
            _fg_br = calcular_fear_greed_br()
            salvar_fear_greed("br", _fg_br.get('score', 50),
                              _fg_br.get('label', 'neutro'),
                              _fg_br.get('scores', {}))

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
                f'<span style="font-family:var(--font-ui,sans-serif);font-size:0.72rem;'
                f'color:var(--text-muted);text-transform:uppercase;">{titulo}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            _cc_fg = _chart_cores()
            _cor_fg = _cc_fg["bull"] if score >= 60 else (_cc_fg["amber"] if score >= 40 else _cc_fg["bear"])
            _fig_fg = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': label.upper(), 'font': {'size': 11, 'color': _cor_fg, 'family': 'Inter, system-ui, sans-serif'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickfont': {'size': 9, 'color': _cc_fg["muted"]}},
                    'bar': {'color': _cor_fg, 'thickness': 0.25},
                    'bgcolor': _cc_fg["surface"], 'bordercolor': _cc_fg["border"],
                    'steps': [
                        {'range': [0, 25], 'color': '#2a0005'},
                        {'range': [25, 45], 'color': '#1a0f00'},
                        {'range': [45, 55], 'color': '#111111'},
                        {'range': [55, 75], 'color': '#001a08'},
                        {'range': [75, 100], 'color': '#002a10'},
                    ],
                    'threshold': {'line': {'color': _cor_fg, 'width': 2}, 'thickness': 0.75, 'value': score},
                },
                number={'font': {'size': 32, 'color': _cor_fg, 'family': 'Inter, system-ui, sans-serif'}},
            ))
            _fig_fg.update_layout(height=220, paper_bgcolor=_cc_fg["surface"], plot_bgcolor=_cc_fg["surface"], margin=dict(l=20, r=20, t=30, b=10))
            st.plotly_chart(_fig_fg, use_container_width=True, config={'responsive': True}, key=f"fg_gauge_{titulo}")

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

        _cc_heat = _chart_cores()
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
            textfont={"size": 10, "color": _cc_heat["text"], "family": "Inter, system-ui, sans-serif"},
            hoverongaps=False,
            showscale=True,
            colorbar=dict(
                tickfont=dict(color=_cc_heat["muted"], family='Inter, system-ui, sans-serif'),
                bordercolor=_cc_heat["border"],
            ),
        ))

        layout_heat = base_layout(
            height=max(300, len(matriz) * 45),
            title=f"matriz de correlação — janela {janela_corr} dias",
        )
        fig_heat.update_layout(**layout_heat)
        fig_heat.update_xaxes(tickangle=45, tickfont=dict(size=9, family='Inter, system-ui, sans-serif'))
        fig_heat.update_yaxes(tickfont=dict(size=9, family='Inter, system-ui, sans-serif'))

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

        _cc_roll = _chart_cores()
        fig_roll.add_hline(
            y=0.7,  line_color=_cc_roll["amber"], line_dash="dash",  line_width=1,
            annotation_text="alta correlação (0.7)",
            annotation_font=dict(color=_cc_roll["amber"], family="Inter, system-ui, sans-serif", size=10),
        )
        fig_roll.add_hline(
            y=0,    line_color=_cc_roll["border"], line_dash="dot",   line_width=1,
        )
        fig_roll.add_hline(
            y=-0.7, line_color=_cc_roll["info"], line_dash="dash",  line_width=1,
            annotation_text="correlação inversa (-0.7)",
            annotation_font=dict(color=_cc_roll["info"], family="Inter, system-ui, sans-serif", size=10),
        )

        layout_roll = base_layout(
            height=350,
            title=f"correlação rolante {janela_corr} dias — ativos vs benchmarks",
        )
        layout_roll.update({
            'yaxis': {'range': [-1.1, 1.1], 'title': 'correlação',
                      'gridcolor': _cc_roll["border"], 'showgrid': True},
        })
        fig_roll.update_layout(**layout_roll)
        st.plotly_chart(fig_roll, use_container_width=True, config={'responsive': True})
        st.caption(
            "cada linha representa a correlação rolante entre um ativo da watchlist "
            "e seu benchmark natural (ativos .SA vs ibovespa; ativos globais vs s&p500). "
            f"janela móvel de {janela_corr} pregões."
        )