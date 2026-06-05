import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
import datetime
import time
from fredapi import Fred
from bcb import sgs
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── silenciar alertas vermelhos do yahoo finance no terminal ──
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from database.db import (
    listar_watchlist, get_health_scores, adicionar_ativo,
    listar_watchlists, criar_watchlist, get_watchlist_padrao,
    get_todos_fundamentos_cache, salvar_fundamento_cache, init_db
)
from utils.tickers import (
    SCREENER_B3, SCREENER_US, XSTOCKS_INDICES, FII_TODOS,
    BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, mapear_ticker_base
)
from utils.health_engine import calcular_health_score
from utils.components import page_header, section_title, status_card, empty_state, inject_keyboard_shortcuts, metric_card, tooltip, label_com_tooltip, handle_ticker_nav, ticker_nav_url
from utils.ai_client import chamar_ia, SYSTEM_ANALISTA
from utils.charts import base_layout
from utils.macro_regime import classificar_regime
from utils.api_cache import get_tickers_cached_av, get_av_rotator, _get_supabase_client

try:
    from utils.api_cache import get_sync_dashboard
except ImportError:
    def get_sync_dashboard():
        return {}

try:
    from utils.alpha_vantage_client import sync_progressivo
except ImportError:
    def sync_progressivo(watchlist_tickers=None, max_requests=None,
                         incluir_fiis_brapi=False, callback=None):
        return {"_erro": "alpha_vantage_client não disponível"}

# 1. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()
handle_ticker_nav()

# ── Auto-sync diário: roda 1x por sessão por dia ─────────────────────────────
_hoje_sync = str(datetime.date.today())
if st.session_state.get("_av_auto_sync_date") != _hoje_sync:
    st.session_state["_av_auto_sync_date"] = _hoje_sync
    _rot_check = get_av_rotator()
    _quota_disp = sum(
        max(0, 25 - _rot_check._get_uso_hoje(k)) for k in _rot_check.keys
    ) if _rot_check.keys else 0
    if _quota_disp > 0:
        _n_est = _quota_disp // 3
        with st.spinner(f"🔄 sincronização automática diária (~{_n_est} ativos via AV + yfinance)…"):
            try:
                sync_progressivo(watchlist_tickers=[], max_requests=None)  # usa toda a quota disponível
            except Exception as _e_auto:
                pass  # silencioso — não bloqueia o usuário

init_db()
CACHE_FUNDAMENTOS = get_todos_fundamentos_cache()

c_head1, c_head2, c_head3 = st.columns([6, 2, 2])
with c_head1:
    page_header("🎯 discovery — descoberta", "encontre assimetrias de mercado através de filtros quantitativos e inteligência artificial.")
with c_head2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 sync cache b3 / fii", use_container_width=True, type="primary", help="sincroniza ações e fiis brasileiros."):
        st.session_state['run_sync_b3'] = True
with c_head3:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 sync cache eua", use_container_width=True, type="primary", help="sincroniza ativos do mercado americano."):
        st.session_state['run_sync_us'] = True

_n_cache_br = sum(1 for t in CACHE_FUNDAMENTOS if str(t).endswith('.SA'))
_n_cache_us = sum(1 for t in CACHE_FUNDAMENTOS if not str(t).endswith('.SA'))
st.caption(f"cache: {_n_cache_br} ativos BR | {_n_cache_us} ativos EUA")

# ══ SYNC AVANÇADO — FUNDAMENTOS POR ALPHA VANTAGE / YFINANCE ═══════════
with st.expander("🔄 sincronização de fundamentos (AV + yfinance)", expanded=True):

    # ── Dashboard de progresso ─────────────────────────────────────────
    _dash = get_sync_dashboard()
    _fii_set = set(FII_TODOS)
    _b3_set  = set(SCREENER_B3)

    _da, _db, _dc, _dd, _de, _df = st.columns(6)
    with _da:
        _n_av  = _dash.get("cached_av_count", 0)
        _n_tot = _dash.get("cached_count", 0)
        _n_b3  = _dash.get("b3_total", 143)
        metric_card("av (10 anos)", str(_n_av),
                    f"{_n_tot} c/ dados · {_n_b3} total",
                    "bull" if _n_av > 0 else "muted")
    with _db:
        _n_rest = _dash.get("restantes_count", 0)
        metric_card("fila av", str(_n_rest),
                    "precisam de sync AV",
                    "amber" if _n_rest > 0 else "bull")
    with _dc:
        _q_rest = _dash.get("quota_restante_hoje", 0)
        metric_card("quota hoje", str(_q_rest),
                    f"req restantes / {_dash.get('quota_total',25)}",
                    "bull" if _q_rest > 0 else "bear")
    with _dd:
        metric_card("chaves AV", str(_dash.get("n_chaves", 0)), "configuradas",
                    "bull" if _dash.get("chave_disponivel") else "bear")
    with _de:
        _hoje_sinc = len(_dash.get("sincronizados_hoje", []))
        metric_card("hoje",      str(_hoje_sinc), "via AV", "info")
    with _df:
        _est = _dash.get("est_dias_uteis", 0)
        metric_card("previsão",  f"{_est}d" if _est > 0 else "✅",
                    "dias úteis restantes", "muted" if _est > 2 else "bull")

    # ── Barra de progresso ─────────────────────────────────────────────
    _pct   = _dash.get("pct_completo", 0)   # % com AV (10 anos)
    _pct_t = _dash.get("pct_total", 0)      # % com qualquer dado
    _n_av  = _dash.get("cached_av_count", 0)
    _n_tot = _dash.get("cached_count", 0)
    _n_t   = _dash.get("b3_total", 1)
    st.markdown(
        f'<div style="margin:10px 0 4px;">'
        f'<div style="font-family:var(--font-ui); font-size:0.65rem;'
        f' color:var(--text-muted); margin-bottom:4px;">'
        f'av (10 anos): {_n_av}/{_n_t} — {_pct}%'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'com dados (yf+av): {_n_tot}/{_n_t} — {_pct_t}%</div>'
        f'<div style="background:var(--bg-elevated); border-radius:4px; height:6px;">'
        f'<div style="background:var(--accent); width:{_pct}%; height:6px;'
        f' border-radius:4px; transition:width 0.3s;"></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # Aviso se sem quota e sem yfinance
    if not _dash.get("chave_disponivel") and _dash.get("restantes_count", 0) > 0:
        st.info("⚡ quota AV esgotada hoje — o sync usará **yfinance** como fallback (4-5 anos de histórico).", icon="ℹ️")

    st.markdown("---")

    # ── Controles de sincronização ─────────────────────────────────────
    _modo_sync = st.radio("modo:", ["watchlist", "ticker avulso", "b3 completo"], horizontal=True, key="sync_modo")

    _wl_opts = {}
    _ticker_input = ""
    _continuar_b3 = False
    _sync_fiis    = False

    if _modo_sync == "watchlist":
        _wl_list = listar_watchlists()
        _wl_opts = {f"{w.get('icone','📋')} {w['nome']} ({w.get('total_ativos',0)} ativos)": w['id'] for w in _wl_list}
        _wl_sel = st.selectbox("selecionar watchlist:", list(_wl_opts.keys()) if _wl_opts else ["(nenhuma)"], key="sync_wl_sel")
        _col_opt1, _col_opt2 = st.columns(2)
        with _col_opt1:
            _continuar_b3 = st.checkbox("continuar com B3 restante após watchlist", value=True, key="sync_continuar_b3")
        with _col_opt2:
            _sync_fiis = st.checkbox("incluir FIIs via BRAPI", value=False, key="sync_fiis")

    elif _modo_sync == "ticker avulso":
        _ticker_input = st.text_input("ticker(es):", placeholder="ex: PETR4, VALE3", key="sync_ticker_input")

    elif _modo_sync == "b3 completo":
        st.caption(f"sincronizará todos os {_dash.get('restantes_count',0)} ativos B3 restantes. usa AV quando disponível, yfinance como fallback.")
        _col_opt2, _ = st.columns(2)
        with _col_opt2:
            _sync_fiis = st.checkbox("incluir FIIs via BRAPI", value=False, key="sync_fiis_b3")

    # ── Botão de ver cache ─────────────────────────────────────────────
    if st.button("📋 ver status de todos os ativos", use_container_width=True, key="btn_ver_cache"):
        _rows = []
        _todos_b3 = sorted(set(t.upper() for t in (_b3_set | _fii_set)))
        _cache_av = get_tickers_cached_av()
        # também verifica cache yfinance
        from utils.api_cache import get_tickers_cached_av as _gtca
        _cache_yf_raw = _get_supabase_client()
        _cache_yf: dict = {}
        if _cache_yf_raw:
            try:
                _r_yf = (_cache_yf_raw.table("api_cache")
                         .select("ticker, periodo")
                         .eq("provider", "yfinance")
                         .eq("endpoint", "INCOME_STATEMENT")
                         .not_.is_("periodo", "null")
                         .execute())
                for _rr in (_r_yf.data or []):
                    _t2 = _rr["ticker"]
                    _cache_yf[_t2] = _cache_yf.get(_t2, 0) + 1
            except Exception:
                pass

        for _t in _todos_b3:
            _nq_av = _cache_av.get(_t, 0)
            _nq_yf = _cache_yf.get(_t, 0)
            _nq    = _nq_av or _nq_yf
            if _t in _fii_set:
                _status = "⏭️ FII"
                _fonte  = "brapi"
            elif _nq_av > 0:
                _status = "✅ av"
                _fonte  = "alpha_vantage"
            elif _nq_yf > 0:
                _status = "✅ yf"
                _fonte  = "yfinance"
            else:
                _status = "❌"
                _fonte  = "—"
            _rows.append({"ativo": _t, "trim.": _nq if _nq > 0 else "—", "fonte": _fonte, "status": _status})
        st.dataframe(
            _rows,
            column_config={
                "ativo":   st.column_config.TextColumn("ativo",  width="small"),
                "trim.":   st.column_config.TextColumn("trim.",  width="small"),
                "fonte":   st.column_config.TextColumn("fonte",  width="medium"),
                "status":  st.column_config.TextColumn("status", width="small"),
            },
            use_container_width=True, hide_index=True,
            height=min(60 * len(_rows), 400),
        )

    # ── Execução do sync ───────────────────────────────────────────────
    if st.button("🚀 iniciar sincronização", type="primary", use_container_width=True, key="btn_sync_avancado"):
        _wl_tickers: list[str] = []
        _max_req = None

        if _modo_sync == "watchlist" and _wl_opts and _wl_sel in _wl_opts:
            _wl_id = _wl_opts[_wl_sel]
            _items = listar_watchlist(_wl_id)
            _wl_tickers = list({it['ticker'].upper() for it in _items})
            if not _continuar_b3:
                _max_req = len(_wl_tickers) * 3 + 3  # limita à watchlist

        elif _modo_sync == "ticker avulso" and _ticker_input:
            _wl_tickers = [t.strip().upper() for t in _ticker_input.replace(",", " ").split() if t.strip()]
            _max_req = len(_wl_tickers) * 3 + 3

        elif _modo_sync == "b3 completo":
            _wl_tickers = []  # usa toda a fila B3

        if not _wl_tickers and _modo_sync not in ("b3 completo",):
            st.warning("nenhum ativo selecionado.")
        else:
            _progresso  = st.progress(0, text="iniciando…")
            _log_area   = st.empty()
            _log_linhas: list[str] = []
            _adicionados: list[str] = []

            def _cb(ticker, status, n_trim, fonte):
                _icon = "⚡" if fonte == "yfinance" else ("⏭️" if "fii" in fonte.lower() else ("✅" if n_trim > 0 else "❌"))
                _msg  = f"{_icon} {ticker} — {n_trim} trim. [{fonte}]"
                _log_linhas.append(_msg)
                _log_area.code("\n".join(_log_linhas[-25:]), language="")
                if isinstance(n_trim, (int, float)) and n_trim > 0:
                    _adicionados.append(ticker)

            with st.spinner("sincronizando…"):
                _res = sync_progressivo(
                    watchlist_tickers   = _wl_tickers,
                    max_requests        = _max_req,
                    incluir_fiis_brapi  = _sync_fiis,
                    callback            = _cb,
                )

            _progresso.progress(1.0, text="concluído!")
            _proc = _res.get("_processados", len(_adicionados))
            _qus  = _res.get("_quota_usada", 0)
            _qre  = _res.get("_quota_restante", 0)
            st.success(
                f"✅ {_proc} ativos com dados · {_qus} req AV usadas · {_qre} req restantes hoje"
            )

            if _adicionados:
                st.dataframe(
                    [{"ativo": t, "status": "✅ sincronizado"} for t in sorted(_adicionados)],
                    use_container_width=True, hide_index=True,
                )
            st.cache_data.clear()
            st.rerun()

st.markdown("---")

def traduzir_setor(setor_raw: str) -> str:
    mapa_setores = {
        'Energy': '⛽ energia', 'Financial Services': '🏦 financeiro',
        'Technology': '💻 tecnologia', 'Healthcare': '🏥 saúde',
        'Consumer Cyclical': '🛒 consumo cíclico', 'Consumer Defensive': '🛒 consumo def.',
        'Industrials': '🏭 indústria', 'Basic Materials': '⛏️ materiais',
        'Real Estate': '🏢 imobiliário', 'Utilities': '⚡ utilities',
        'Communication Services': '📡 telecom', 'Financeiro': '🏦 financeiro',
    }
    return mapa_setores.get(setor_raw, setor_raw.lower() if setor_raw else '—')

# ==========================================
# ROTINAS DE SINCRONIZAÇÃO ASSÍNCRONA
# ==========================================
if st.session_state.get('run_sync_b3'):
    st.info("A iniciar sincronização massiva B3 (Ações + FIIs) em background...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    from utils.scrapers import buscar_dados_b3
    
    def fetch_and_save_b3(t):
        try:
            dados = buscar_dados_b3(t)
            salvar_fundamento_cache(t, dados)
            return True
        except: return False

    lista_completa = SCREENER_B3 + FII_TODOS
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_and_save_b3, t): t for t in lista_completa}
        total = len(lista_completa)
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            progress_bar.progress(concluidos / total)
            status_text.text(f"Sincronizando: {futures[future]} ({concluidos}/{total})...")
            
    st.session_state['run_sync_b3'] = False
    st.success("✅ Cache Nacional atualizada! Recarregando...")
    time.sleep(1.5)
    st.rerun()

if st.session_state.get('run_sync_us'):
    st.info("A iniciar extração massiva EUA em background...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def fetch_and_save_us(t_base):
        try:
            info = yf.Ticker(t_base).info
            dados = {
                'nome': info.get('shortName', t_base),
                'setor': traduzir_setor(info.get('sector', '—')),
                'p/l': info.get('trailingPE', info.get('forwardPE', None)),
                'p/vp': info.get('priceToBook', None),
                'roe%': (info.get('returnOnEquity') * 100) if info.get('returnOnEquity') is not None else None,
                'dy%': (info.get('dividendYield') * 100) if info.get('dividendYield') is not None else 0,
                'market_cap': info.get('marketCap', 0),
                'ev/ebitda': info.get('enterpriseToEbitda', None),
                'margem%': (info.get('profitMargins') * 100) if info.get('profitMargins') is not None else None,
                'beta': info.get('beta', None)
            }
            salvar_fundamento_cache(t_base, dados)
            return True
        except: return False

    us_tickers_unicos = list(set([mapear_ticker_base(t) for t in SCREENER_US + XSTOCKS_INDICES]))
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_and_save_us, t): t for t in us_tickers_unicos}
        total = len(us_tickers_unicos)
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            progress_bar.progress(concluidos / total)
            status_text.text(f"Sincronizando EUA: {futures[future]} ({concluidos}/{total})...")
            
    st.session_state['run_sync_us'] = False
    st.success("✅ Cache EUA atualizada! Recarregando...")
    time.sleep(1.5)
    st.rerun()

@st.dialog("➕ salvar na watchlist")
def modal_salvar_screener(ticker: str, nome: str, mercado: str):
    st.markdown(f"**ativo:** {ticker.lower()} - {nome.lower()}")
    acao_wl = st.radio("destino:", ["watchlist existente", "criar nova watchlist"], horizontal=True, key=f"radio_dest_{ticker}")
    watchlists_disp = listar_watchlists()
    dest_id = None
    
    if acao_wl == "watchlist existente":
        opcoes_dest = {f"{wl['icone']} {wl['nome']}": wl['id'] for wl in watchlists_disp}
        sel_dest = st.selectbox("selecione a watchlist:", list(opcoes_dest.keys()), key=f"sel_exist_{ticker}")
        dest_id = opcoes_dest[sel_dest]
    else:
        nome_nova_wl = st.text_input("nome da nova watchlist:", placeholder="ex: radar de dividendos", key=f"input_nova_{ticker}")
    
    if st.button("💾 confirmar", type="primary", use_container_width=True, key=f"btn_conf_{ticker}"):
        if acao_wl == "criar nova watchlist":
            if nome_nova_wl.strip(): dest_id = criar_watchlist(nome_nova_wl.strip(), icone="🎯", cor="#00C853")
            else: return st.warning("digite um nome para a nova watchlist.")
        
        adicionar_ativo(ticker, nome, mercado, watchlist_id=dest_id)
        st.success(f"✅ {ticker.lower()} salvo com sucesso!")
        time.sleep(1); st.rerun()

@st.cache_data(ttl=3600, show_spinner=False)
def calcular_momentum(tickers_tuple: tuple) -> list[dict]:
    """Calcula força relativa de 52 semanas para uma lista de tickers."""
    tickers = list(tickers_tuple)
    resultados = []

    def processar(t):
        try:
            t_base = mapear_ticker_base(t)
            acao = yf.Ticker(t_base)
            hist = acao.history(period="1y", auto_adjust=True)
            if hist.empty or len(hist) < 50:
                return None

            close = hist['Close']
            preco_atual = close.iloc[-1]
            preco_1y = close.iloc[0]
            preco_6m = close.iloc[len(close)//2]
            preco_3m = close.iloc[int(len(close)*0.75)]
            preco_1m = close.iloc[-21] if len(close) >= 21 else close.iloc[0]

            ret_1y = (preco_atual / preco_1y - 1) * 100
            ret_6m = (preco_atual / preco_6m - 1) * 100
            ret_3m = (preco_atual / preco_3m - 1) * 100
            ret_1m = (preco_atual / preco_1m - 1) * 100

            mm50  = close.rolling(50).mean().iloc[-1]
            mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.mean()

            acima_mm50  = preco_atual > mm50
            acima_mm200 = preco_atual > mm200

            high_52w = close.max()
            low_52w  = close.min()
            dist_high = (preco_atual / high_52w - 1) * 100

            score_mom = 0
            if ret_1y > 0:  score_mom += 25
            if ret_6m > 0:  score_mom += 25
            if ret_3m > 0:  score_mom += 20
            if ret_1m > 0:  score_mom += 10
            if acima_mm50:  score_mom += 10
            if acima_mm200: score_mom += 10

            f_dados = CACHE_FUNDAMENTOS.get(t_base, {})

            return {
                'ticker': t,
                'nome': f_dados.get('nome', t_base),
                'setor': traduzir_setor(f_dados.get('setor', '—')),
                'preço atual': round(preco_atual, 2),
                'ret 1m (%)': round(ret_1m, 2),
                'ret 3m (%)': round(ret_3m, 2),
                'ret 6m (%)': round(ret_6m, 2),
                'ret 1y (%)': round(ret_1y, 2),
                'dist. topo 52w (%)': round(dist_high, 2),
                'acima mm50': '✅' if acima_mm50 else '❌',
                'acima mm200': '✅' if acima_mm200 else '❌',
                'score momentum': score_mom,
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        futuros = {ex.submit(processar, t): t for t in tickers}
        for fut in as_completed(futuros):
            res = fut.result()
            if res:
                resultados.append(res)

    return sorted(resultados, key=lambda x: x['score momentum'], reverse=True)


@st.cache_data(ttl=1800, show_spinner=False)
def calcular_heatmap_setorial(universo: str = "BR") -> list[dict]:
    """
    Agrupa health scores por setor e calcula métricas setoriais.
    Usa apenas dados já existentes no cache de fundamentos e health scores.
    Retorna lista de dicts ordenada por score médio descendente.
    """
    # Pega todos os health scores do banco
    todos_hs = get_health_scores()
    if not todos_hs:
        return []

    # Mapa ticker → score
    hs_map = {h['ticker']: h.get('score', 50) for h in todos_hs}

    # Agrupa por setor usando cache de fundamentos
    setores: dict = {}

    for ticker, dados in CACHE_FUNDAMENTOS.items():
        # Filtra por universo
        if universo == "BR" and not ticker.endswith(".SA"):
            continue
        if universo == "US" and ticker.endswith(".SA"):
            continue

        setor_raw = dados.get('setor') or '—'
        if not setor_raw or setor_raw == '—':
            continue

        setor = traduzir_setor(setor_raw)
        score = hs_map.get(ticker)
        if score is None:
            continue

        if setor not in setores:
            setores[setor] = {
                'setor':   setor,
                'ativos':  [],
                'scores':  [],
            }

        setores[setor]['ativos'].append(ticker)
        setores[setor]['scores'].append(score)

    # Calcula métricas por setor
    resultado = []
    for setor, dados_s in setores.items():
        scores = dados_s['scores']
        if not scores:
            continue

        score_medio = round(sum(scores) / len(scores), 1)
        score_max   = max(scores)
        score_min   = min(scores)
        n_acum      = sum(1 for s in scores if s >= 65)
        n_reduzir   = sum(1 for s in scores if s < 40)
        n_ativos    = len(scores)

        # Sinal do setor
        if score_medio >= 65:
            sinal = "acumulação"
            cor   = "#00C853"
        elif score_medio >= 45:
            sinal = "neutro"
            cor   = "#FF9900"
        else:
            sinal = "cautela"
            cor   = "#FF1744"

        resultado.append({
            'setor':        setor,
            'score_medio':  score_medio,
            'score_max':    score_max,
            'score_min':    score_min,
            'n_ativos':     n_ativos,
            'n_acumulacao': n_acum,
            'n_reduzir':    n_reduzir,
            'sinal':        sinal,
            'cor':          cor,
            'tickers':      dados_s['ativos'][:8],  # top 8 para exibição
        })

    return sorted(resultado, key=lambda x: x['score_medio'], reverse=True)


@st.cache_data(ttl=3600, show_spinner=False)
def rodar_radar_universo(
    universo: str = "BR",
    modo:     str = "entrada",
    top_n:    int = 10,
) -> list[dict]:
    """
    Roda o radar em todo o universo de ativos (não só watchlist).
    Usa health scores e fundamentos já cacheados.
    Só baixa histórico de preços dos candidatos qualificados
    (health score >= 55) para economizar chamadas à API.
    """
    import yfinance as yf
    import numpy as np

    if universo == "BR":
        from utils.tickers import SCREENER_B3, FII_TODOS
        todos = SCREENER_B3 + FII_TODOS
    else:
        from utils.tickers import SCREENER_US
        todos = SCREENER_US

    hs_all = {
        h['ticker']: float(h.get('score', 0) or 0)
        for h in (get_health_scores() or [])
    }

    candidatos = [
        t for t in todos
        if hs_all.get(t, 0) >= 55
        or hs_all.get(mapear_ticker_base(t), 0) >= 55
    ]

    if not candidatos:
        return []

    candidatos = candidatos[:60]

    from utils.radar import calcular_oportunidades_watchlist
    try:
        resultado = calcular_oportunidades_watchlist(
            tuple(candidatos),
            modo=modo,
        )
        return resultado[:top_n]
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def rodar_screener(
    universo:        str,
    pl_min:          float,
    pl_max:          float,
    pvp_max:         float,
    roe_min:         float,
    dy_min:          float,
    score_min:       int,
    piotroski_min:   int,
    apenas_acima_mm: bool,
) -> pd.DataFrame:
    """
    Filtra o universo de ativos usando o cache de fundamentos
    e os health scores já calculados.
    """
    if universo == 'b3':
        tickers = SCREENER_B3
    elif universo == 'fii':
        tickers = FII_TODOS
    else:
        tickers = SCREENER_US

    cache_fund  = get_todos_fundamentos_cache()
    health_data = {h['ticker']: h for h in get_health_scores()}

    resultados = []

    for ticker in tickers:
        t_base = mapear_ticker_base(ticker)
        fund   = cache_fund.get(ticker) or cache_fund.get(t_base) or {}
        health = health_data.get(ticker) or health_data.get(t_base) or {}

        if not fund and not health:
            continue

        pl      = fund.get('p/l')
        pvp     = fund.get('p/vp')
        roe     = fund.get('roe%')
        dy      = fund.get('dy%', 0) or 0
        margem  = fund.get('margem%')
        ev_ebit = fund.get('ev/ebitda')
        nome    = fund.get('nome', '—')
        setor   = fund.get('setor', '—')
        score   = health.get('score', 0) or 0

        # Score 0 = nunca calculado
        nao_calculado = (score == 0)

        # ── Filtro health score ──────────────────────────────────
        # Se score_min > 0 e o ativo nunca teve score calculado
        # (score == 0), exclui — 0 não é "ótimo", é "sem dados".
        if score_min > 0:
            if nao_calculado or score < score_min:
                continue

        # ── Filtros fundamentalistas ─────────────────────────────
        # Regra: se o usuário definiu o filtro E o dado é None,
        # exclui o ativo. Dado ausente ≠ filtro aprovado.
        algum_filtro_fund = (
            pl_min > 0 or pl_max > 0 or
            pvp_max > 0 or roe_min > 0 or dy_min > 0
        )

        if pl_min > 0 or pl_max > 0:
            if pl is None:
                continue
            if pl_min > 0 and pl < pl_min:
                continue
            if pl_max > 0 and pl > pl_max:
                continue

        if pvp_max > 0:
            if pvp is None:
                continue
            if pvp > pvp_max:
                continue

        if roe_min > 0:
            if roe is None:
                continue
            if roe < roe_min:
                continue

        if dy_min > 0:
            if dy is None or dy < dy_min:
                continue

        # Se nenhum filtro fundamentalista foi definido mas o ativo
        # não tem nenhum dado, ainda inclui (com flag sem_dados)
        sem_dados_fund = (
            pl is None and pvp is None and
            roe is None and (dy == 0 or dy is None)
        )

        resultados.append({
            'ticker':        ticker.replace('.SA', ''),
            'nome':          nome[:30] if nome else '—',
            'setor':         setor[:25] if setor else '—',
            'p/l':           pl,
            'p/vp':          pvp,
            'roe%':          roe,
            'dy%':           dy if dy else None,
            'margem%':       margem,
            'ev/ebitda':     ev_ebit,
            'score':         score,
            '_nao_calc':     nao_calculado,
            '_sem_dados':    sem_dados_fund,
            '_ticker_full':  ticker,
        })

    if not resultados:
        return pd.DataFrame()

    df = pd.DataFrame(resultados)
    df = df.sort_values('score', ascending=False)
    return df


# 6. interface de separadores (tabs)
tab_screen, tab_mom, tab_ia, tab_setorial, tab_radar = st.tabs([
    "🔍 screener quantitativo",
    "🚀 momentum (força relativa)",
    "🧠 ia: oportunidades do dia",
    "🗺️ rotação setorial",
    "⚡ radar de mercado",
])

# ==========================================
# tab 1 — momentum (força relativa)
# ==========================================
with tab_mom:
    section_title("🚀 momentum screener — força relativa")

    status_card(
        "metodologia",
        "score de momentum de 0 a 100 baseado em 6 critérios: retorno 1y, 6m, 3m e 1m (positivo = ponto), preço acima da MM50 e MM200. ativos com score alto têm momentum técnico consistente em múltiplas janelas.",
        tipo="info"
    )

    mc1, mc2, mc3 = st.columns([3, 2, 2])
    with mc1:
        mom_universos = st.multiselect(
            "universo:",
            ["🇧🇷 b3 — ações", "🌎 eua — ações", "🏢 b3 — fiis"],
            default=["🇧🇷 b3 — ações"],
            key="mom_universos"
        )
    with mc2:
        mom_top_n = st.slider("top N ativos:", 5, 30, 15, 5, key="mom_top_n")
    with mc3:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_momentum = st.button("🚀 calcular momentum", type="primary", use_container_width=True)

    score_minimo = st.slider("score mínimo de momentum:", 0, 100, 50, 10, key="mom_score_min")

    if btn_momentum:
        mom_lista = []
        if "🇧🇷 b3 — ações" in mom_universos: mom_lista += SCREENER_B3
        if "🌎 eua — ações" in mom_universos: mom_lista += SCREENER_US
        if "🏢 b3 — fiis" in mom_universos: mom_lista += FII_TODOS

        if not mom_lista:
            st.warning("selecione pelo menos um universo.")
        else:
            with st.spinner(f"calculando momentum de {len(mom_lista)} ativos..."):
                resultados_mom = calcular_momentum(tuple(mom_lista))
                df_mom = pd.DataFrame(resultados_mom)
                if not df_mom.empty:
                    df_mom = df_mom[df_mom['score momentum'] >= score_minimo]
                    df_mom = df_mom.head(mom_top_n)
                    st.session_state['momentum_resultado'] = df_mom

    if 'momentum_resultado' in st.session_state and not st.session_state['momentum_resultado'].empty:
        df_m = st.session_state['momentum_resultado']

        section_title(f"top {len(df_m)} ativos por momentum")

        mm1, mm2, mm3 = st.columns(3)
        with mm1:
            metric_card("melhor momentum", df_m.iloc[0]['ticker'], f"score {df_m.iloc[0]['score momentum']}/100", "bull")
        with mm2:
            metric_card("retorno médio 1y", f"{df_m['ret 1y (%)'].mean():.1f}%", "", "bull" if df_m['ret 1y (%)'].mean() > 0 else "bear")
        with mm3:
            acima_200 = (df_m['acima mm200'] == '✅').sum()
            metric_card("acima da mm200", f"{acima_200}/{len(df_m)}", "tendência de alta", "bull" if acima_200 > len(df_m)//2 else "amber")

        cols_mostrar = ['ticker', 'nome', 'setor', 'ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)', 'dist. topo 52w (%)', 'acima mm50', 'acima mm200', 'score momentum']

        def colorir_momentum(val):
            if isinstance(val, (int, float)):
                if val > 0: return 'color: #00C853'
                if val < 0: return 'color: #FF1744'
            return ''

        st.dataframe(
            df_m[cols_mostrar].style
                .map(colorir_momentum, subset=['ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)', 'dist. topo 52w (%)'])
                .format({'ret 1m (%)': '{:+.2f}%', 'ret 3m (%)': '{:+.2f}%', 'ret 6m (%)': '{:+.2f}%', 'ret 1y (%)': '{:+.2f}%', 'dist. topo 52w (%)': '{:+.2f}%', 'score momentum': '{:.0f}'}),
            use_container_width=True,
            hide_index=True
        )

        section_title("📊 mapa de retornos por janela temporal")

        fig_mom = go.Figure()
        janelas = ['ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)']
        labels = ['1 mês', '3 meses', '6 meses', '1 ano']

        for _, row in df_m.head(10).iterrows():
            fig_mom.add_trace(go.Scatter(
                x=labels,
                y=[row[j] for j in janelas],
                mode='lines+markers',
                name=row['ticker'],
                line=dict(width=1.5),
                hovertemplate=f"{row['ticker']}<br>%{{x}}: %{{y:+.1f}}%<extra></extra>"
            ))

        fig_mom.add_hline(y=0, line_color="#333", line_dash="dash", line_width=1)
        fig_mom.update_layout(**base_layout(height=400, title="retorno acumulado por janela — top 10 ativos"))
        st.plotly_chart(fig_mom, use_container_width=True, config={'responsive': True})

        st.markdown("---")

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            for _, row in df_m.iterrows():
                c1, c2, c3 = st.columns([2, 3, 2])
                _tk_mom = row['ticker']
                c1.markdown(
                    f'<a href="{ticker_nav_url(_tk_mom)}" class="ticker-nav" style="font-size:0.85rem;">'
                    f'{_tk_mom.replace(".SA","")}</a>',
                    unsafe_allow_html=True,
                )
                score = row['score momentum']
                cor_score = "#00C853" if score >= 70 else ("#FF9900" if score >= 40 else "#FF1744")
                barra = "█" * int(score // 10) + "░" * int(10 - score // 10)
                c2.markdown(f'<span style="font-family:Courier New; font-size:0.8rem; color:{cor_score};">{barra}</span>', unsafe_allow_html=True)
                if c3.button("＋ watchlist", key=f"btn_wl_mom_{row['ticker']}", use_container_width=True):
                    mercado = "brasil" if mapear_ticker_base(row['ticker']).endswith('.SA') else "eua"
                    modal_salvar_screener(row['ticker'], row['nome'], mercado)

        with col_a2:
            if st.button("🧠 ia: analisar momentum e identificar líderes setoriais", type="primary", use_container_width=True):
                with st.spinner("deepseek analisando momentum..."):
                    _dados_mom = df_m[cols_mostrar].head(10).to_csv(index=False)
                    chamar_ia(
                        prompt_usuario=(
                            f"dados de momentum:\n{_dados_mom}\n\n"
                            "responda em 4 bullet points curtos em português, letra minúscula:\n"
                            "1. qual ativo tem o momentum mais consistente e por quê.\n"
                            "2. quais setores estão liderando o movimento.\n"
                            "3. algum ativo próximo do topo de 52 semanas que pode estar em breakout.\n"
                            "4. riscos: algum ativo com momentum positivo mas fundamentos fracos."
                        ),
                        system      = SYSTEM_ANALISTA,
                        max_tokens  = 500,
                        temperatura = 0.3,
                        stream      = True,
                    )

# ==========================================
# tab 2 — screener quantitativo
# ==========================================
with tab_screen:
    section_title("🕵️ screener quantitativo — filtros paramétricos")

    # ── seleção de universo ──────────────────────────────────────────────────
    col_univ, col_info_scr = st.columns([2, 3])
    with col_univ:
        universo_sel = st.radio(
            "universo de ativos:",
            options=['b3', 'fii', 'us'],
            format_func=lambda x: {
                'b3':  f'🇧🇷 Ações B3 ({len(SCREENER_B3)} ativos)',
                'fii': f'🏢 FIIs ({len(FII_TODOS)} fundos)',
                'us':  f'🇺🇸 Ações EUA ({len(SCREENER_US)} ativos)',
            }[x],
            horizontal=True,
            key="screener_univ",
        )
    with col_info_scr:
        status_card(
            "como funciona",
            "os dados são do cache de fundamentos atualizado pelos botões de sync no topo da página. "
            "health score integra fatores técnicos, fundamentalistas e macro. "
            "use o botão 🔄 sync antes de rodar o screener pela primeira vez.",
            tipo="info",
        )

    st.markdown("---")

    # ══ BOTÕES DE PRESET E RESET ════════════════════════════════════════════
    section_title("⚙️ filtros")

    col_p1, col_p2, col_p3 = st.columns([1, 1, 4])
    with col_p1:
        if st.button("💎 valor", key="btn_preset_valor",
                     use_container_width=True, help="P/L baixo + ROE alto"):
            st.session_state["disc_pl_max_w"]  = 15.0
            st.session_state["disc_pl_min_w"]  = 0.0
            st.session_state["disc_roe_w"]     = 12.0
            st.session_state["disc_score_w"]   = 55
            st.session_state["disc_dy_w"]      = 0.0
            st.session_state["disc_pvp_w"]     = 0.0
            st.rerun()
    with col_p2:
        if st.button("💰 dividendo", key="btn_preset_div",
                     use_container_width=True, help="DY alto + score ok"):
            st.session_state["disc_dy_w"]      = 6.0
            st.session_state["disc_score_w"]   = 45
            st.session_state["disc_pl_max_w"]  = 0.0
            st.session_state["disc_pl_min_w"]  = 0.0
            st.session_state["disc_roe_w"]     = 0.0
            st.session_state["disc_pvp_w"]     = 0.0
            st.rerun()
    with col_p3:
        if st.button("↺ resetar filtros", key="btn_reset_filtros",
                     use_container_width=True):
            for _k in ['disc_pl_min_w', 'disc_pl_max_w', 'disc_roe_w',
                       'disc_dy_w', 'disc_score_w', 'disc_pvp_w',
                       'disc_mm_w']:
                st.session_state.pop(_k, None)
            st.rerun()

    # ══ WIDGETS DE FILTRO (com value= persistente via session_state) ════════
    f1, f2, f3, f4 = st.columns(4)

    with f1:
        st.markdown(
            '<div style="font-family:Courier New; font-size:0.72rem; color:#555; '
            'text-transform:uppercase; letter-spacing:0.08em; margin-bottom:6px;">p/l (faixa)</div>',
            unsafe_allow_html=True,
        )
        pl_col1, pl_col2 = st.columns(2)
        with pl_col1:
            st.number_input(
                "mín", min_value=0.0, max_value=200.0,
                step=1.0, key="disc_pl_min_w",
                label_visibility="collapsed",
                value=st.session_state.get('disc_pl_min_w', 0.0),
            )
        with pl_col2:
            st.number_input(
                "máx", min_value=0.0, max_value=500.0,
                step=1.0, key="disc_pl_max_w",
                label_visibility="collapsed",
                value=st.session_state.get('disc_pl_max_w', 15.0),
            )
        st.caption("0 = sem limite")

    with f2:
        st.number_input(
            "p/vp máximo:", min_value=0.0, max_value=20.0,
            step=0.1, format="%.1f",
            key="disc_pvp_w", help="0 = sem filtro",
            value=st.session_state.get('disc_pvp_w', 0.0),
        )
        st.number_input(
            "roe mínimo (%):", min_value=0.0, max_value=100.0,
            step=1.0, key="disc_roe_w",
            value=st.session_state.get('disc_roe_w', 0.0),
        )

    with f3:
        st.number_input(
            "dividend yield mínimo (%):",
            min_value=0.0, max_value=30.0,
            step=0.5, format="%.1f",
            key="disc_dy_w",
            value=st.session_state.get('disc_dy_w', 0.0),
        )
        st.slider(
            "health score mínimo:",
            min_value=0, max_value=100,
            step=5, key="disc_score_w",
            value=st.session_state.get('disc_score_w', 50),
        )

    with f4:
        st.checkbox(
            "apenas acima da MM200",
            key="disc_mm_w",
            value=st.session_state.get('disc_mm_w', False),
        )

    # ══ LEITURA DOS VALORES (via session_state após render) ═══════════════════
    pl_min    = st.session_state["disc_pl_min_w"]
    pl_max    = st.session_state["disc_pl_max_w"]
    pvp_max   = st.session_state["disc_pvp_w"]
    roe_min   = st.session_state["disc_roe_w"]
    dy_min    = st.session_state["disc_dy_w"]
    score_min = st.session_state["disc_score_w"]
    apenas_mm = st.session_state["disc_mm_w"]

    # ══ BOTÃO RODAR ══════════════════════════════════════════════════════════
    if st.button("🔍 rodar screener", type="primary",
                 use_container_width=True, key="btn_rodar"):
        with st.spinner("filtrando universo de ativos..."):
            df_result = rodar_screener(
                universo        = universo_sel,
                pl_min          = pl_min,
                pl_max          = pl_max,
                pvp_max         = pvp_max,
                roe_min         = roe_min,
                dy_min          = dy_min,
                score_min       = score_min,
                piotroski_min   = 0,
                apenas_acima_mm = apenas_mm,
            )
        st.session_state["screener_resultado"] = df_result
        st.session_state["screener_universo"]  = universo_sel

    # ── resultados ───────────────────────────────────────────────────────────
    if 'screener_resultado' in st.session_state:
        df_res = st.session_state['screener_resultado']
        univ   = st.session_state.get('screener_universo', 'b3')

        st.markdown("---")

        if df_res.empty:
            empty_state(
                "🎯",
                "nenhum ativo encontrado",
                "tente relaxar os filtros — reduza o ROE mínimo, "
                "aumente o P/L máximo ou diminua o health score mínimo. "
                "use o botão '↺ resetar filtros' para voltar aos defaults.",
            )
        else:
            col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
            with col_r1:
                section_title(f"📋 {len(df_res)} ativos encontrados")
            with col_r2:
                ordenar_por = st.selectbox(
                    "ordenar por:",
                    options=['score', 'dy%', 'roe%', 'p/l', 'p/vp'],
                    key="sc_ordem",
                )
                df_res = df_res.sort_values(
                    ordenar_por,
                    ascending=(ordenar_por in ['p/l', 'p/vp']),
                    na_position='last',
                )
            with col_r3:
                csv_scr = df_res.drop(
                    columns=['_ticker_full', '_nao_calc', '_sem_dados'],
                    errors='ignore',
                ).to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 exportar CSV",
                    data=csv_scr,
                    file_name=f"screener_{univ}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="sc_download",
                )

            # ── PROBLEMA 4: aviso cache incompleto ──────────────
            ativos_sem_dados = int(df_res.get('_sem_dados', pd.Series(dtype=bool)).sum()) if '_sem_dados' in df_res.columns else 0
            if ativos_sem_dados > len(df_res) * 0.3:
                status_card(
                    "⚠️ cache de fundamentos incompleto",
                    f"{ativos_sem_dados} de {len(df_res)} ativos sem dados fundamentalistas. "
                    f"clique em '🔄 sync cache eua' no topo da página para atualizar os dados "
                    f"antes de rodar o screener.",
                    tipo="amber",
                )

            # ── Tabela principal ─────────────────────────────────
            cols_display = ['ticker', 'nome', 'health', 'p/l', 'p/vp', 'roe%', 'dy%', 'margem%']
            df_display   = df_res[['ticker', 'nome', 'score', 'p/l', 'p/vp', 'roe%', 'dy%', 'margem%']].copy()

            # PROBLEMA 3: Barra de health como texto (evita cor invertida do ProgressColumn)
            df_display.insert(2, 'health', df_res['score'].apply(
                lambda s: (
                    f"{'█' * (int(s) // 10)}{'░' * (10 - int(s) // 10)} {int(s)}"
                    if s and s > 0 else "— n/c"
                )
            ))
            df_display = df_display.drop(columns=['score'])

            for col in ['p/l', 'p/vp', 'roe%', 'dy%', 'margem%']:
                if col in df_display.columns:
                    df_display[col] = df_display[col].apply(
                        lambda x: f"{x:.1f}" if pd.notna(x) and x is not None else "—"
                    )

            st.caption("clique em uma linha para abrir no research →")
            _sel_screener = st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun",
                key="df_screener_quant",
                column_config={
                    'ticker': st.column_config.TextColumn("Ticker", width="small"),
                    'nome':   st.column_config.TextColumn("Nome",   width="medium"),
                    'health': st.column_config.TextColumn("Health Score", width="medium"),
                    'p/l':    st.column_config.TextColumn("P/L",   width="small"),
                    'p/vp':   st.column_config.TextColumn("P/VP",  width="small"),
                    'roe%':   st.column_config.TextColumn("ROE %", width="small"),
                    'dy%':    st.column_config.TextColumn("DY %",  width="small"),
                    'margem%':st.column_config.TextColumn("Margem %", width="small"),
                },
            )
            if _sel_screener and _sel_screener.selection.rows:
                _row_idx = _sel_screener.selection.rows[0]
                _sel_ticker = df_res.iloc[_row_idx]['_ticker_full']
                st.session_state['research_ticker_externo'] = _sel_ticker
                st.switch_page("pages/1_Research.py")

            # ── adicionar à watchlist ────────────────────────────────────────
            section_title("➕ adicionar à watchlist")

            tickers_full = df_res['_ticker_full'].tolist()
            tickers_sel  = st.multiselect(
                "selecione ativos para adicionar:",
                options=tickers_full,
                format_func=lambda x: x.replace('.SA', ''),
                key="sc_add_wl",
            )

            if tickers_sel:
                if st.button(
                    f"➕ adicionar {len(tickers_sel)} ativo(s) à watchlist",
                    type="primary", key="sc_btn_add_wl",
                ):
                    _cache_scr = get_todos_fundamentos_cache()
                    try:
                        _wl_id = get_watchlist_padrao()
                    except Exception:
                        _wl_id = None

                    adicionados = 0
                    for t_add in tickers_sel:
                        t_add_base = mapear_ticker_base(t_add)
                        fund_t     = _cache_scr.get(t_add) or _cache_scr.get(t_add_base) or {}
                        mercado    = 'Brasil (B3)' if t_add.endswith('.SA') else 'EUA'
                        ok = adicionar_ativo(
                            ticker       = t_add,
                            nome         = fund_t.get('nome', t_add),
                            mercado      = mercado,
                            watchlist_id = _wl_id,
                        )
                        if ok:
                            adicionados += 1

                    if adicionados > 0:
                        st.success(f"✅ {adicionados} ativo(s) adicionados à watchlist!")
                        st.rerun()

with tab_ia:
    section_title("🧠 ia: oportunidades do dia")

    st.markdown(
        '<div style="font-family:Courier New;font-size:0.75rem;'
        'color:#555;margin-bottom:16px;line-height:1.7;">'
        'análise de ia do universo completo de ativos. '
        'identifica os top 5 com maior assimetria '
        'risco/retorno no momento, considerando health score, '
        'regime macro e timing técnico. '
        'atualizado sob demanda — clique para rodar.'
        '</div>',
        unsafe_allow_html=True,
    )

    _col_ia_u, _col_ia_m = st.columns(2)
    with _col_ia_u:
        _univ_ia = st.radio(
            "universo:",
            ["BR", "US", "AMBOS"],
            format_func=lambda x: {
                "BR":    "🇧🇷 brasil (b3 + fiis)",
                "US":    "🇺🇸 eua (s&p500)",
                "AMBOS": "🌍 todos",
            }[x],
            horizontal=True,
            key="radio_univ_ia_disc",
        )
    with _col_ia_m:
        _modo_ia = st.radio(
            "foco:",
            ["entrada", "dividendo", "realizacao"],
            format_func=lambda x: {
                "entrada":    "🎯 melhor entrada",
                "dividendo":  "💰 renda / dividendos",
                "realizacao": "📤 possível realização",
            }[x],
            horizontal=True,
            key="radio_modo_ia_disc",
        )

    _btn_rodar_ia = st.button(
        "🧠 analisar oportunidades agora",
        type="primary",
        use_container_width=True,
        key="btn_ia_disc_rodar",
    )

    _cache_key_ia = f"ia_disc_{_univ_ia}_{_modo_ia}"

    if _btn_rodar_ia:
        st.session_state.pop(_cache_key_ia, None)
        st.session_state.pop(f"{_cache_key_ia}_analise", None)

    if _btn_rodar_ia or st.session_state.get(_cache_key_ia):

        if not st.session_state.get(_cache_key_ia):
            with st.spinner(
                "filtrando universo por qualidade... "
                "(pode levar 30-60 segundos)"
            ):
                from utils.radar import calcular_oportunidades_watchlist

                if _univ_ia == "BR":
                    _tickers_ia = SCREENER_B3 + FII_TODOS
                elif _univ_ia == "US":
                    _tickers_ia = SCREENER_US
                else:
                    _tickers_ia = SCREENER_B3 + FII_TODOS + SCREENER_US

                _hs_ia = {
                    h['ticker']: float(h.get('score', 0) or 0)
                    for h in (get_health_scores() or [])
                }
                _cands_ia = [
                    t for t in _tickers_ia
                    if _hs_ia.get(t, 0) >= 55
                    or _hs_ia.get(mapear_ticker_base(t), 0) >= 55
                ][:80]

                _resultados_ia = calcular_oportunidades_watchlist(
                    tuple(_cands_ia),
                    modo=_modo_ia,
                )
                st.session_state[_cache_key_ia] = _resultados_ia

        _resultados_ia = st.session_state.get(_cache_key_ia, [])

        if not _resultados_ia:
            st.warning(
                "nenhum ativo passou pelos filtros de qualidade "
                "e timing. tente rodar o sync de fundamentos "
                "no topo da página ou mude o modo."
            )
        else:
            st.markdown("<br>", unsafe_allow_html=True)
            section_title(
                f"📊 top {len(_resultados_ia)} ativos — "
                f"score quantitativo"
            )

            import pandas as pd
            _df_ia = pd.DataFrame(_resultados_ia)[[
                'ticker', 'nome', 'mercado',
                'score_assim', 'score_hs',
                'score_val', 'score_timing',
                'rsi', 'ret_5d', 'ret_3m', 'dist_top',
            ]]
            _df_ia.columns = [
                'ticker', 'nome', 'mercado',
                'score total', 'qualidade (hs)',
                'valuation', 'timing',
                'rsi', '5d %', '3m %', 'topo %',
            ]

            st.dataframe(
                _df_ia.style.format({
                    'score total':    '{:.0f}',
                    'qualidade (hs)': '{:.0f}',
                    'valuation':      '{:.0f}',
                    'timing':         '{:.0f}',
                    'rsi':            '{:.0f}',
                    '5d %':           '{:+.1f}%',
                    '3m %':           '{:+.1f}%',
                    'topo %':         '{:.0f}%',
                }).background_gradient(
                    subset=['score total'],
                    cmap='RdYlGn',
                    vmin=30, vmax=85,
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("<br>", unsafe_allow_html=True)
            section_title("🤖 análise qualitativa — ia")

            _cache_key_analise = f"{_cache_key_ia}_analise"

            if st.session_state.get(_cache_key_analise):
                st.markdown(
                    f'<div style="font-family:Courier New;'
                    f'font-size:0.82rem;color:#C0C0C0;'
                    f'line-height:1.8;background:#0a0a0a;'
                    f'border:1px solid #1a1a1a;'
                    f'border-radius:6px;padding:16px;">'
                    f'{st.session_state[_cache_key_analise]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "🔄 regenerar análise",
                    key="btn_regen_ia_disc",
                ):
                    st.session_state.pop(_cache_key_analise, None)
                    st.rerun()
            else:
                if st.button(
                    "🧠 gerar análise qualitativa da ia",
                    type="secondary",
                    use_container_width=True,
                    key="btn_gen_analise_ia_disc",
                ):
                    _top5 = _resultados_ia[:5]
                    _macro_ia = st.session_state.get(
                        "macro_context", {}
                    )
                    _linhas_top5 = []
                    for _r in _top5:
                        _linhas_top5.append(
                            f"- {_r['ticker']} ({_r['nome'][:20]}) "
                            f"| mercado: {_r['mercado']} "
                            f"| score: {_r['score_assim']:.0f}/100 "
                            f"| health: {_r['score_hs']:.0f} "
                            f"| rsi: {_r['rsi']:.0f} "
                            f"| ret 5d: {_r['ret_5d']:+.1f}% "
                            f"| ret 3m: {_r['ret_3m']:+.1f}% "
                            f"| dist topo: {_r['dist_top']:.0f}%"
                        )

                    _modo_desc = {
                        "entrada":   "melhor ponto de entrada",
                        "dividendo": "renda e dividendos",
                        "realizacao":"possível realização parcial",
                    }.get(_modo_ia, _modo_ia)

                    _prompt_ia_disc = (
                        f"análise de oportunidades — "
                        f"modo: {_modo_desc}\n\n"
                        f"universo analisado: {_univ_ia}\n"
                        f"regime macro: "
                        f"{_macro_ia.get('label', '—')}\n"
                        f"selic: {_macro_ia.get('selic', 10.75):.2f}%"
                        f" | vix: {_macro_ia.get('vix', 15.0):.1f}\n\n"
                        f"top {len(_top5)} ativos por score "
                        f"quantitativo:\n"
                        + "\n".join(_linhas_top5) +
                        f"\n\nem 5 tópicos diretos (minúsculas):\n"
                        f"1. qual desses ativos tem a tese mais "
                        f"sólida para o regime macro atual? por quê?\n"
                        f"2. qual representa o melhor risco/retorno "
                        f"no modo '{_modo_desc}'?\n"
                        f"3. qual deles tem o maior risco oculto "
                        f"que o score quantitativo pode não capturar?\n"
                        f"4. como o regime macro atual "
                        f"({_macro_ia.get('label', '—')}) "
                        f"afeta especificamente esses ativos?\n"
                        f"5. se tivesse que escolher apenas um "
                        f"agora, qual seria e com qual tese de 12 meses?"
                    )

                    _system_ia_disc = (
                        "você é um analista de investimentos "
                        "especializado em mercados br e eua. "
                        "use os dados quantitativos fornecidos. "
                        "seja direto e específico. minúsculas. "
                        "não repita os dados — interprete-os."
                    )
                    _us_ia_disc = st.session_state.get(
                        'user_settings', {}
                    )
                    _resposta_ia_disc = chamar_ia(
                        prompt_usuario = _prompt_ia_disc,
                        system         = _system_ia_disc,
                        max_tokens     = 700,
                        temperatura    = 0.3,
                        stream         = True,
                        user_settings  = _us_ia_disc,
                    )
                    if _resposta_ia_disc:
                        st.session_state[_cache_key_analise] = (
                            _resposta_ia_disc
                        )

            st.markdown("<br>", unsafe_allow_html=True)
            _ac1, _ac2 = st.columns(2)

            with _ac1:
                if _resultados_ia:
                    _top1_ia = _resultados_ia[0]
                    if st.button(
                        f"🔬 analisar {_top1_ia['ticker'].replace('.SA','')} "
                        f"no research",
                        type="primary",
                        use_container_width=True,
                        key="btn_ia_disc_research",
                    ):
                        st.session_state[
                            'research_ticker_externo'
                        ] = _top1_ia['ticker']
                        st.switch_page("pages/1_Research.py")

            with _ac2:
                if st.button(
                    f"+ adicionar top {min(5,len(_resultados_ia))} "
                    f"à watchlist",
                    type="secondary",
                    use_container_width=True,
                    key="btn_ia_disc_add_wl",
                ):
                    try:
                        _wl_id_ia = get_watchlist_padrao()
                        _add_count = 0
                        for _r in _resultados_ia[:5]:
                            _merc_ia = (
                                "Brasil (B3)"
                                if _r['ticker'].endswith('.SA')
                                else "EUA"
                            )
                            adicionar_ativo(
                                ticker       = _r['ticker'],
                                nome         = _r['nome'],
                                mercado      = _merc_ia,
                                watchlist_id = _wl_id_ia,
                            )
                            _add_count += 1
                        st.success(
                            f"✅ {_add_count} ativos adicionados!"
                        )
                    except Exception as _e_add:
                        st.error(f"erro ao adicionar: {_e_add}")

with tab_setorial:
    label_com_tooltip(
        "🗺️ ROTAÇÃO SETORIAL — HEALTH SCORE MÉDIO POR SETOR",
        chave="health_score",
        cor="#FF9900",
        tamanho="0.72rem",
    )

    st.markdown(
        '<div style="font-family:Courier New; font-size:0.75rem; '
        'color:#555; margin-bottom:16px; line-height:1.6;">'
        'score médio dos ativos de cada setor no universo analisado. '
        'setores verdes (≥65) em fase de acumulação. '
        'vermelhos (<40) em cautela. dados baseados nos health scores '
        'calculados pelo motor quantitativo.'
        '</div>',
        unsafe_allow_html=True,
    )

    _col_univ, _col_refresh = st.columns([3, 1])
    with _col_univ:
        _univ_set = st.radio(
            "universo:",
            ["BR", "US"],
            format_func=lambda x: {
                "BR": "🇧🇷 Brasil (B3 + FIIs)",
                "US": "🇺🇸 EUA (S&P500)",
            }[x],
            horizontal=True,
            key="radio_univ_setorial",
        )
    with _col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 recalcular", key="btn_refresh_setorial",
                     use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("agrupando setores..."):
        _dados_set = calcular_heatmap_setorial(_univ_set)

    if not _dados_set:
        st.info(
            "nenhum dado setorial disponível. "
            "rode o sync de fundamentos no topo da página primeiro."
        )
    else:
        _n_acum_total  = sum(1 for s in _dados_set if s['sinal'] == 'acumulação')
        _n_neutro_total = sum(1 for s in _dados_set if s['sinal'] == 'neutro')
        _n_caut_total  = sum(1 for s in _dados_set if s['sinal'] == 'cautela')

        _rs1, _rs2, _rs3, _rs4 = st.columns(4)
        with _rs1:
            metric_card("setores analisados", str(len(_dados_set)), "com dados suficientes")
        with _rs2:
            metric_card("em acumulação", str(_n_acum_total),
                        "score médio ≥ 65", "bull" if _n_acum_total > 0 else "muted")
        with _rs3:
            metric_card("neutros", str(_n_neutro_total), "score 45–64", "amber")
        with _rs4:
            metric_card("em cautela", str(_n_caut_total),
                        "score médio < 45", "bear" if _n_caut_total > 0 else "muted")

        st.markdown("<br>", unsafe_allow_html=True)

        # ---- CONTEXTO DO REGIME MACRO ATUAL ----
        _regime_disc = classificar_regime()
        _regime_label = _regime_disc.get("label", "neutro")
        _regime_desc = _regime_disc.get("descricao", "")
        _score_amb = _regime_disc.get("score_ambiente", 50)
        _fav_setores = _regime_disc.get("setores_favorecidos", [])
        _prej_setores = _regime_disc.get("setores_prejudicados", [])
        _posicionamento = _regime_disc.get("posicionamento", "")

        _cor_regime = (
            "#FF1744" if "stress" in _regime_label
            else "#FF9900" if "altos" in _regime_label
            else "#00C853"
        )
        _cor_score = "#00C853" if _score_amb >= 60 else ("#FF9900" if _score_amb >= 35 else "#FF1744")

        _html_parts = [
            f'<div style="background:#0d0d0d;border:1px solid #1e1e1e;border-left:3px solid {_cor_regime};border-radius:6px;padding:10px 16px;margin-bottom:16px;">',
            f'<div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;">',
            f'<span style="font-family:Courier New;font-size:0.62rem;color:#555;text-transform:uppercase;">regime atual</span>',
            f'<span style="font-family:Courier New;font-size:0.82rem;font-weight:600;color:{_cor_regime};">{_regime_label}</span>',
            f'<span style="font-family:Courier New;font-size:0.72rem;color:#666;">{_regime_desc[:60]}</span>',
            f'<span style="font-family:Courier New;font-size:0.62rem;color:#555;text-transform:uppercase;">score amb.</span>',
            f'<span style="font-family:Courier New;font-size:0.82rem;font-weight:600;color:{_cor_score};">{_score_amb}/100</span>',
            '</div>',
        ]

        _html_parts.append('<div style="display:flex;gap:24px;margin-top:8px;flex-wrap:wrap;">')

        if _fav_setores:
            fav_spans = ''
            for _s in _fav_setores:
                _match = [d for d in _dados_set if _s.lower() in d["setor"].lower()]
                _score_val = _match[0]['score_medio'] if _match else None
                _extra = ' ({:.0f})'.format(_score_val) if _score_val is not None else ''
                fav_spans += f'<span style="background:#003300;color:#00C853;font-family:Courier New;font-size:0.6rem;padding:2px 6px;border-radius:3px;">{_s}{_extra}</span>'
            _html_parts.append(
                f'<div style="flex:1;min-width:140px;">'
                f'<div style="font-size:0.6rem;color:#555;text-transform:uppercase;margin-bottom:3px;">\U0001f7e2 favorecidos pelo regime</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:3px;">{fav_spans}</div>'
                f'</div>'
            )

        if _prej_setores:
            prej_spans = ''
            for _s in _prej_setores:
                _match = [d for d in _dados_set if _s.lower() in d["setor"].lower()]
                _score_val = _match[0]['score_medio'] if _match else None
                _extra = ' ({:.0f})'.format(_score_val) if _score_val is not None else ''
                prej_spans += f'<span style="background:#330000;color:#FF1744;font-family:Courier New;font-size:0.6rem;padding:2px 6px;border-radius:3px;">{_s}{_extra}</span>'
            _html_parts.append(
                f'<div style="flex:1;min-width:140px;">'
                f'<div style="font-size:0.6rem;color:#555;text-transform:uppercase;margin-bottom:3px;">\U0001f534 prejudicados pelo regime</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:3px;">{prej_spans}</div>'
                f'</div>'
            )

        _html_parts.append('</div>')

        if _posicionamento:
            _html_parts.append(
                f'<div style="font-family:Courier New;font-size:0.62rem;color:#555;margin-top:6px;border-top:1px solid #1e1e1e;padding-top:4px;">{_posicionamento}</div>'
            )

        _html_parts.append('</div>')

        st.markdown(''.join(_html_parts), unsafe_allow_html=True)

        import plotly.graph_objects as go


        _setores_nomes  = [d['setor'] for d in _dados_set]
        _scores_medios  = [d['score_medio'] for d in _dados_set]
        _cores_barras   = [d['cor'] for d in _dados_set]
        _hover_texts    = [
            f"<b>{d['setor']}</b><br>"
            f"score médio: {d['score_medio']}<br>"
            f"ativos: {d['n_ativos']}<br>"
            f"acumulação: {d['n_acumulacao']} | cautela: {d['n_reduzir']}<br>"
            f"range: {d['score_min']} – {d['score_max']}<br>"
            f"tickers: {', '.join([t.replace('.SA','') for t in d['tickers']])}"
            for d in _dados_set
        ]

        _fig_set = go.Figure()

        _fig_set.add_trace(go.Bar(
            x=_scores_medios,
            y=_setores_nomes,
            orientation='h',
            marker_color=_cores_barras,
            marker_opacity=0.85,
            text=[f"{s:.0f}" for s in _scores_medios],
            textposition='outside',
            textfont=dict(size=10, color='#aaa', family='Courier New'),
            hovertext=_hover_texts,
            hoverinfo='text',
            name='score médio',
        ))

        _fig_set.add_vline(
            x=65, line_color="#00C853", line_dash="dash",
            line_width=1, annotation_text="acumulação",
            annotation_font_color="#00C853",
            annotation_font_size=9,
        )
        _fig_set.add_vline(
            x=40, line_color="#FF1744", line_dash="dash",
            line_width=1, annotation_text="cautela",
            annotation_font_color="#FF1744",
            annotation_font_size=9,
        )

        _h_set = max(300, len(_dados_set) * 38)
        _lay_set = base_layout(
            height=_h_set,
            title=f"health score médio por setor — {_univ_set}"
        )
        _lay_set.update(
            xaxis=dict(range=[0, 110], showgrid=True,
                       gridcolor='#2A2C3E', title='score médio'),
            yaxis=dict(showgrid=False, title=''),
            margin=dict(l=180, r=60, t=40, b=20),
        )
        _fig_set.update_layout(**_lay_set)
        st.plotly_chart(_fig_set, use_container_width=True, config={'responsive': True})

        st.markdown("<br>", unsafe_allow_html=True)
        section_title("detalhamento por setor")

        for _ds in _dados_set:
            _exp_label = (
                f"{_ds['setor']} — "
                f"score {_ds['score_medio']:.0f} | "
                f"{_ds['n_ativos']} ativos | "
                f"{_ds['sinal'].upper()}"
            )
            with st.expander(_exp_label, expanded=False):
                _dc1, _dc2, _dc3, _dc4 = st.columns(4)
                _dc1.metric("score médio",   f"{_ds['score_medio']:.1f}")
                _dc2.metric("melhor score",  f"{_ds['score_max']:.0f}")
                _dc3.metric("pior score",    f"{_ds['score_min']:.0f}")
                _dc4.metric("n° de ativos",  str(_ds['n_ativos']))

                st.markdown(
                    "**ativos com dados:** "
                    + " · ".join([
                        t.replace('.SA', '') for t in _ds['tickers']
                    ]),
                )

# ==========================================
# tab 5 — radar de mercado
# ==========================================
with tab_radar:
    section_title("⚡ radar de mercado — oportunidades fora da sua watchlist")
    tooltip("score_assimetria")

    st.markdown(
        '<div style="font-family:Courier New;font-size:0.75rem;'
        'color:#555;margin-bottom:16px;line-height:1.6;">'
        'scan em todo o universo de ativos (não só sua watchlist). '
        'filtra por qualidade mínima (health ≥ 55) antes de '
        'calcular o score de assimetria — economiza tempo e foca '
        'onde vale a pena olhar.'
        '</div>',
        unsafe_allow_html=True,
    )

    _rc1, _rc2, _rc3 = st.columns([2, 2, 1])
    with _rc1:
        _univ_radar = st.radio(
            "universo:",
            ["BR", "US"],
            format_func=lambda x: {
                "BR": "🇧🇷 Brasil (B3 + FIIs)",
                "US": "🇺🇸 EUA (S&P500)",
            }[x],
            horizontal=True,
            key="radio_univ_radar",
        )
    with _rc2:
        _modo_radar_disc = st.radio(
            "modo:",
            ["entrada", "realizacao", "dividendo"],
            format_func=lambda x: {
                "entrada":    "🎯 entrada",
                "realizacao": "📤 realização",
                "dividendo":  "💰 dividendos",
            }[x],
            horizontal=True,
            key="radio_modo_radar_disc",
        )
    with _rc3:
        st.markdown("<br>", unsafe_allow_html=True)
        _btn_radar = st.button(
            "▶ rodar scan",
            type="primary",
            use_container_width=True,
            key="btn_rodar_radar",
        )

    if _btn_radar or st.session_state.get('radar_resultado'):

        if _btn_radar:
            with st.spinner(
                "filtrando universo e calculando scores... "
                "pode levar 20-40 segundos..."
            ):
                from utils.radar import calcular_oportunidades_watchlist

                _todos_radar = (
                    SCREENER_B3 + FII_TODOS
                    if _univ_radar == "BR"
                    else SCREENER_US
                )

                _hs_radar = {
                    h['ticker']: float(h.get('score', 0) or 0)
                    for h in (get_health_scores() or [])
                }
                _cands = [
                    t for t in _todos_radar
                    if _hs_radar.get(t, 0) >= 55
                    or _hs_radar.get(mapear_ticker_base(t), 0) >= 55
                ][:60]

                _resultado_radar = calcular_oportunidades_watchlist(
                    tuple(_cands),
                    modo=_modo_radar_disc,
                )
                st.session_state['radar_resultado'] = _resultado_radar
                st.session_state['radar_modo_last'] = _modo_radar_disc

        _resultado_radar = st.session_state.get('radar_resultado', [])

        if not _resultado_radar:
            st.info(
                "nenhum ativo passou pelos filtros de qualidade "
                "e timing. tente rodar o sync de fundamentos "
                "primeiro ou mude o modo."
            )
        else:
            st.markdown(
                f'<div style="font-family:Courier New;'
                f'font-size:0.72rem;color:#555;margin-bottom:12px;">'
                f'top {len(_resultado_radar)} ativos do universo '
                f'{_univ_radar} no modo '
                f'{st.session_state.get("radar_modo_last","—")}'
                f'</div>',
                unsafe_allow_html=True,
            )

            _df_radar = pd.DataFrame(_resultado_radar)[[
                'ticker', 'nome', 'score_assim',
                'score_hs', 'score_val', 'score_timing',
                'rsi', 'ret_5d', 'ret_3m', 'dist_top',
            ]]
            _df_radar.columns = [
                'ticker', 'nome', 'score total',
                'qualidade', 'valuation', 'timing',
                'rsi', '5d %', '3m %', 'topo %',
            ]

            st.dataframe(
                _df_radar.style.format({
                    'score total': '{:.0f}',
                    'qualidade':   '{:.0f}',
                    'valuation':   '{:.0f}',
                    'timing':      '{:.0f}',
                    'rsi':         '{:.0f}',
                    '5d %':        '{:+.1f}%',
                    '3m %':        '{:+.1f}%',
                    'topo %':      '{:.0f}%',
                }),
                use_container_width=True,
                hide_index=True,
            )

            _top1 = _resultado_radar[0]
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(
                f"🔬 analisar {_top1['ticker'].replace('.SA','')} "
                f"(score {_top1['score_assim']:.0f}) no research",
                type="primary",
                use_container_width=True,
                key="btn_radar_research_top1",
            ):
                st.session_state['research_ticker_externo'] = (
                    _top1['ticker']
                )
                st.switch_page("pages/1_Research.py")

            if st.button(
                f"+ adicionar top {len(_resultado_radar)} "
                f"à watchlist para acompanhar",
                type="secondary",
                use_container_width=True,
                key="btn_radar_add_wl",
            ):
                from database.db import (
                    adicionar_ativo, get_watchlist_padrao
                )
                _wl_id_r = get_watchlist_padrao()
                _adicionados = 0
                for _r in _resultado_radar:
                    try:
                        _merc_r = (
                            "Brasil (B3)"
                            if _r['ticker'].endswith('.SA')
                            else "EUA"
                        )
                        adicionar_ativo(
                            ticker       = _r['ticker'],
                            nome         = _r['nome'],
                            mercado      = _merc_r,
                            watchlist_id = _wl_id_r,
                        )
                        _adicionados += 1
                    except Exception:
                        pass
                st.success(
                    f"✅ {_adicionados} ativos adicionados "
                    f"à watchlist padrão!"
                )

    else:
        st.info(
            "clique em '▶ rodar scan' para analisar o "
            "universo completo de ativos."
        )