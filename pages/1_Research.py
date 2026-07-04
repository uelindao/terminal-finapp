import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import json as _json
from fredapi import Fred
from utils.ai_client import chamar_ia, SYSTEM_ANALISTA, SYSTEM_TESE
from utils.earnings_scraper import buscar_resultados
from bcb import sgs
import logging
import requests

# silenciar alertas vermelhos do yahoo finance no terminal
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label, mapear_ticker_base, FII_TODOS, BRASIL_TODOS, XSTOCKS_TODOS
from database.db import listar_watchlists, listar_watchlist, get_todos_fundamentos_cache, salvar_fundamento_cache, init_db, get_historico_score, get_health_scores, get_user_settings
from utils.scrapers import buscar_dados_b3, buscar_dados_us
from utils.fmp_client import get_multiplos_medios, get_peers, get_multiplos_historicos

# componentes do design system
from utils.components import (
    page_header, section_title, metric_card, status_card,
    ticker_hero, portfolio_kpis as _portfolio_kpis_v5, info_box as _info_box_v5,
    empty_state, inject_keyboard_shortcuts,
    tooltip, label_com_tooltip, TOOLTIPS,
    data_quality_badge,
    # Fase 6 — shell visual
    topbar,
)
from utils.macro_context import garantir_macro_context
from utils.macro_regime import classificar_regime  # apenas o label do regime
from utils.formatters import fmt_preco, fmt_pct, fmt_numero, safe_float
from utils.charts import base_layout, CORES_SERIES, base100, linha, chart_type_toggle, barras_verticais, _cores as _chart_cores

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
init_db()

# Carrega configurações pessoais do usuário (chave de IA, provider, etc.)
_current_user = get_current_user()
_user_settings = {}
if _current_user:
    try:
        _raw_settings = get_user_settings(_current_user['user_id'])
        if _raw_settings:
            _user_settings = dict(_raw_settings)
    except Exception:
        pass  # sem configurações — usa tier free

CACHE_FUNDAMENTOS = get_todos_fundamentos_cache()

# ==========================================
# MOTOR DE BUSCA GLOBAL (YAHOO FINANCE)
# ==========================================
# buscar_ativo_yahoo consolidado em utils/market_data (era duplicado em Home).
# yf_info: entrada única p/ yfinance.info (circuit breaker central) — Fase 2.
from utils.market_data import buscar_ativo_yahoo, yf_info

# ==========================================
# GESTÃO DE ESTADO E SIDEBAR
# ==========================================
if 'research_ticker' not in st.session_state:
    # Suporta abertura em nova aba via ?research_ticker=TICKER
    _qt = st.query_params.get("research_ticker")
    st.session_state['research_ticker'] = _qt if _qt else "PETR4.SA"
    if _qt:
        st.query_params.clear()

if 'research_ticker_externo' in st.session_state:
    st.session_state['research_ticker'] = st.session_state.pop('research_ticker_externo')

# Lê modo e ativos pré-selecionados vindos da Home
if 'research_modo' in st.session_state:
    _modo_presel = st.session_state.pop('research_modo')
else:
    _modo_presel = None

if 'comp_ativos_presel' in st.session_state:
    _ativos_presel = st.session_state.pop('comp_ativos_presel')
else:
    _ativos_presel = None

with st.sidebar:
    section_title("🔬 modo de análise")
    modo_pesquisa = st.radio("selecione o escopo:", ["Deep Dive (Individual)", "Comparativo (Múltiplos)"], index=1 if _modo_presel == 'Comparativo (Múltiplos)' else 0, label_visibility="collapsed")
    
    st.markdown("---")
    
    if modo_pesquisa == "Deep Dive (Individual)":
        section_title("pesquisar ativo")
        
        # --- NOVA BUSCA GLOBAL (YAHOO FINANCE API) ---
        termo = st.text_input("buscar qualquer ativo global:", placeholder="nome ou ticker (ex: nubank, aapl)...")
        if st.button("🔍 buscar ativo", use_container_width=True):
            if termo:
                with st.spinner("procurando na rede global..."):
                    resultados = buscar_ativo_yahoo(termo)
                    if resultados:
                        melhor_match = resultados[0].get('symbol')
                        if melhor_match:
                            st.session_state['research_ticker'] = melhor_match
                            st.rerun()
                    else:
                        st.warning("ativo não encontrado.")
        
        st.markdown("<div style='text-align: center; color: var(--text-muted); padding: 10px 0;'>ou selecione da base:</div>", unsafe_allow_html=True)
        
        # --- LISTA PADRÃO COM PROTEÇÃO PARA ATIVOS EXTERNOS ---
        opcoes = get_opcoes_selectbox()
        ticker_atual = st.session_state['research_ticker']
        
        # Verifica se o ticker pesquisado está na lista padrão, se não, adiciona ele no topo
        ticker_presente = any(ticker_atual in opt for opt in opcoes)
        if not ticker_presente:
            opcoes.insert(0, f"{ticker_atual} — Ativo Externo")
        
        idx_default = 0
        for i, opt in enumerate(opcoes):
            if ticker_atual in opt:
                idx_default = i
                break

        escolha = st.selectbox("lista de ativos:", opcoes, index=idx_default, label_visibility="collapsed")
        
        # Extrair ticker com segurança
        if " — " in escolha:
            ticker_limpo = escolha.split(" — ")[0].strip()
        else:
            ticker_limpo = ticker_from_label(escolha)
            
        # Atualiza a página caso o usuário escolha outro item da lista dropdown
        if ticker_limpo and ticker_limpo != st.session_state['research_ticker']:
            st.session_state['research_ticker'] = ticker_limpo
            st.rerun()
            
    else:
        section_title("comparar ativos")
        _default_comp = (
            _ativos_presel
            if _ativos_presel
            else ["PETR4.SA", "VALE3.SA", "ITUB4.SA"]
        )
        ativos_comp = st.multiselect("selecione os ativos:",
                                     options=BRASIL_TODOS + XSTOCKS_TODOS,
                                     default=[
                                         t for t in _default_comp
                                         if t in BRASIL_TODOS + XSTOCKS_TODOS
                                     ])
    
    st.markdown("---")

    # ── HEALTH SCORE DO ATIVO ATUAL (sidebar) ──────────────────────────────
    st.markdown(
        '<div style="height:1px;background:var(--border-subtle);margin:12px 0;"></div>',
        unsafe_allow_html=True,
    )
    _tk_sidebar = st.session_state.get('research_ticker', '')
    _tk_base_sb = mapear_ticker_base(_tk_sidebar) if _tk_sidebar else ''
    if _tk_sidebar:
        _hs_all_sb = {h['ticker']: h.get('score', 50) for h in (get_health_scores() or [])}
        _hs_score = _hs_all_sb.get(_tk_base_sb) or _hs_all_sb.get(_tk_sidebar) or 50
        _cor_sb = (
            "var(--bull)" if _hs_score >= 65
            else "var(--amber)" if _hs_score >= 40
            else "var(--bear)"
        )
        _label_sb = (
            "acumulação" if _hs_score >= 65
            else "manutenção" if _hs_score >= 40
            else "reduzir"
        )
        # Badge de qualidade do dado — prefere a coluna nova (ETL), com fallback ao campo legado dos scrapers
        _cache_sb = CACHE_FUNDAMENTOS.get(_tk_base_sb, {})
        _qual_sb = (
            _cache_sb.get('data_quality_pct') if _cache_sb else None
        ) or (
            _cache_sb.get('qualidade_dados') if _cache_sb else None
        )
        _fonte_sb = _cache_sb.get('data_source', '') if _cache_sb else ''
        _hs_row_sb = {r['ticker']: r for r in (get_health_scores() or [])}.get(_tk_base_sb, {})
        _atualizado_sb = _hs_row_sb.get('updated_at', '') if _hs_row_sb else ''
        _badge_sb = data_quality_badge(_qual_sb, _fonte_sb, _atualizado_sb)
        st.markdown(
            f'<div style="background:var(--bg-surface); border:1px solid var(--border-subtle); '
            f'border-left:3px solid {_cor_sb}; border-radius:4px; '
            f'padding:10px 12px; margin-bottom:8px;">'
            f'<div style="font-size:0.62rem; color:var(--text-muted); '
            f'text-transform:uppercase; letter-spacing:.08em; '
            f'margin-bottom:4px;">health score</div>'
            f'<div style="font-family:var(--font-data,monospace); font-size:1.6rem; '
            f'font-weight:700; color:{_cor_sb}; line-height:1;">'
            f'{_hs_score}<span style="font-size:0.8rem;color:var(--text-muted);">/100</span>'
            f'{_badge_sb}'
            f'</div>'
            f'<div style="font-family:var(--font-data,monospace); font-size:0.7rem; '
            f'color:{_cor_sb}; margin-top:2px;">{_label_sb}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── ADICIONAR À WATCHLIST ─────────────────────────────────────────────
    st.markdown(
        '<div style="height:1px;background:var(--border-subtle);margin:8px 0;"></div>',
        unsafe_allow_html=True,
    )
    section_title("+ watchlist")
    _watchlists_sb = listar_watchlists()
    if _watchlists_sb:
        _opcoes_wl_sb = {f"{wl['icone']} {wl['nome']}": wl['id'] for wl in _watchlists_sb}
        _dest_wl_sb = st.selectbox(
            "destino:", list(_opcoes_wl_sb.keys()),
            key="sb_dest_wl", label_visibility="collapsed",
        )
        if st.button(
            f"+ adicionar {_tk_sidebar.replace('.SA','')}",
            key="sb_btn_add_wl", use_container_width=True,
        ):
            from database.db import adicionar_ativo
            _wl_id_sb = _opcoes_wl_sb[_dest_wl_sb]
            _merc_sb  = "Brasil (B3)" if _tk_sidebar.endswith('.SA') else "EUA"
            _nome_sb  = CACHE_FUNDAMENTOS.get(_tk_base_sb, {}).get('nome') or _tk_sidebar
            adicionar_ativo(
                ticker=_tk_sidebar, nome=_nome_sb,
                mercado=_merc_sb, watchlist_id=_wl_id_sb,
            )
            st.success(f"✅ {_tk_sidebar.replace('.SA','')} adicionado!")

    # ── ÚLTIMOS 5 ATIVOS VISITADOS ────────────────────────────────────────
    _hist_sb = st.session_state.get('research_historico', [])
    _hist_exibir = [t for t in _hist_sb if t != _tk_sidebar][:4]
    if _hist_exibir:
        st.markdown(
            '<div style="height:1px;background:var(--border-subtle);margin:8px 0;"></div>',
            unsafe_allow_html=True,
        )
        section_title("visitados recentemente")
        _hs_all_sb = {h['ticker']: h.get('score', 50) for h in (get_health_scores() or [])}
        for _ht in _hist_exibir:
            _hs_ht  = _hs_all_sb.get(_ht, 50)
            _cor_ht = (
                "var(--bull)" if _hs_ht >= 65 else "var(--amber)" if _hs_ht >= 40 else "var(--bear)"
            )
            _col_ht1, _col_ht2 = st.columns([3, 1])
            with _col_ht1:
                if st.button(
                    _ht.replace('.SA', '').lower(),
                    key=f"hist_btn_{_ht}", use_container_width=True,
                ):
                    st.session_state['research_ticker'] = _ht
                    st.rerun()
            with _col_ht2:
                st.markdown(
                    f'<div style="font-family:var(--font-data,monospace); font-size:0.75rem; '
                    f'color:{_cor_ht}; text-align:right; padding-top:6px;">{_hs_ht}</div>',
                    unsafe_allow_html=True,
                )

# Trava de segurança para números
# safe_float consolidado em utils/formatters (importado acima).

def calcular_crescimento_implicito(preco, eps, wacc, g_terminal, n_anos):
    try:
        if eps is None or eps <= 0 or preco is None or preco <= 0:
            return None
        if wacc <= g_terminal:
            return None
            
        def valor_dcf(g):
            soma_fc = sum((eps * (1 + g)**t) / ((1 + wacc)**t) for t in range(1, n_anos + 1))
            valor_term = (eps * (1 + g)**n_anos * (1 + g_terminal)) / (wacc - g_terminal)
            valor_term_descontado = valor_term / ((1 + wacc)**n_anos)
            return soma_fc + valor_term_descontado
            
        lo = -0.5
        hi = 3.0
        for _ in range(200):
            mid = (lo + hi) / 2
            try:
                if valor_dcf(mid) > preco:
                    hi = mid
                else:
                    lo = mid
            except Exception:
                return None
        return mid
    except Exception:
        return None

# ==========================================
# MODO 2: COMPARATIVO MULTI-ATIVOS
# ==========================================
if modo_pesquisa == "Comparativo (Múltiplos)":
    _user_top_cmp = get_current_user() or {}
    topbar(
        breadcrumb_itens=[
            ("⚡ finterminal", "/"),
            ("research", None),
            ("comparativo", None),
        ],
        user_name=_user_top_cmp.get('username', '') or _user_top_cmp.get('nome', '') or 'usuário',
        sync_label="ao vivo",
    )
    page_header("⚖️ comparativo de mercado", "análise relativa de múltiplos e performance em base 100.")
    
    if not ativos_comp:
        from utils.components import info_box as _info_box_r
        _info_box_r(
            tipo   = "info",
            titulo = "selecione ativos para começar",
            texto  = "use a barra lateral para escolher 2 ou mais ativos e iniciar a comparação.",
            icone  = "👈",
        )
        # Sem ativos não há dados_comp: interromper aqui evita NameError no botão
        # de veredito e no st.columns(len(ativos_comp)) mais abaixo na página.
        st.stop()
    else:
        with st.spinner("sincronizando matriz de múltiplos..."):
            dados_comp = []
            try:
                from utils.price_history import obter_close_carteira
                hist_all = obter_close_carteira(tuple(ativos_comp), periodo="10y")
                if isinstance(hist_all, pd.Series): hist_all = hist_all.to_frame(name=ativos_comp[0])
                hist_all = hist_all.ffill().dropna(how='all')
            except: hist_all = pd.DataFrame()
            
            for t in ativos_comp:
                t_base = mapear_ticker_base(t)
                try:
                    # Fallback duplo: tenta t_base e t original no cache
                    cache_d = (
                        CACHE_FUNDAMENTOS.get(t_base)
                        or CACHE_FUNDAMENTOS.get(t)
                        or CACHE_FUNDAMENTOS.get(t_base.replace('.SA', ''))
                        or {}
                    )

                    # Busca info do yfinance via fachada (circuit breaker central)
                    info = yf_info(t_base)

                    # Helper seguro
                    def _get_val(cache_key, yf_key, multiplier=1.0):
                        v = cache_d.get(cache_key)
                        if v is None:
                            raw = info.get(yf_key)
                            if raw is not None and yf_key == 'dividendYield':
                                raw_f = float(raw)
                                # yfinance retorna decimal (0.035 = 3.5%). Sempre ×100.
                                v = raw_f * 100 if raw_f <= 0.50 else None
                            else:
                                v = (float(raw) * multiplier) if raw is not None else None
                        try:
                            return float(v) if v is not None else None
                        except (TypeError, ValueError):
                            return None

                    dados_comp.append({
                        "ticker":    t,
                        "nome":      cache_d.get('nome') or info.get('shortName', t),
                        "setor":     cache_d.get('setor') or info.get('sector', '—'),
                        "p/l":       _get_val('p/l', 'trailingPE'),
                        "p/vp":      _get_val('p/vp', 'priceToBook'),
                        "roe%":      _get_val('roe%', 'returnOnEquity', 100),
                        "dy%":       _get_val('dy%', 'dividendYield', 100),
                        "mrg_liq%":  _get_val('margem%', 'profitMargins', 100),
                        "ev/ebitda": _get_val('ev/ebitda', 'enterpriseToEbitda'),
                        "mkt_cap":   _get_val('market_cap', 'marketCap'),
                    })
                except Exception as _e_comp:
                    dados_comp.append({
                        "ticker": t, "nome": t, "setor": "—",
                        "p/l": None, "p/vp": None, "roe%": None,
                        "dy%": None, "mrg_liq%": None,
                        "ev/ebitda": None, "mkt_cap": None,
                    })

            df_comp = pd.DataFrame(dados_comp)

            # Adiciona health score ao comparativo
            from database.db import get_health_scores
            _hs_comp = {h['ticker']: h.get('score') for h in (get_health_scores() or [])}
            df_comp['health'] = df_comp['ticker'].apply(
                lambda tk: _hs_comp.get(tk) or _hs_comp.get(mapear_ticker_base(tk))
            )

            # Reordena colunas com health primeiro
            _cols_order = ['ticker', 'nome', 'health', 'p/l', 'p/vp',
                           'roe%', 'dy%', 'mrg_liq%', 'ev/ebitda']
            df_comp = df_comp[[c for c in _cols_order if c in df_comp.columns]]

            c1, c2 = st.columns([6, 4])
            with c1:
                st.markdown("**matriz de múltiplos quantitativos**")
                if not df_comp.empty:
                    def _peers_table_html(df: "pd.DataFrame") -> str:
                        _cols = [c for c in ['ticker','nome','health','p/l','p/vp','roe%','dy%','mrg_liq%','ev/ebitda'] if c in df.columns]
                        _mn = 'var(--font-mono,monospace)'
                        # compute best/worst for highlighting
                        _best_max = {c: df[c].max() for c in ['roe%','dy%','mrg_liq%','health'] if c in df.columns and df[c].notna().any()}
                        _best_min = {c: df[c].min() for c in ['p/l','p/vp','ev/ebitda'] if c in df.columns and df[c].notna().any()}
                        _hdrs = ""
                        for col in _cols:
                            _align = "left" if col in ('ticker','nome') else "right"
                            _hdrs += f'<th style="padding:7px 10px;text-align:{_align};font-size:0.67rem;color:var(--text-muted);text-transform:uppercase;border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{col}</th>'
                        _rows = ""
                        for _, row in df.iterrows():
                            _cells = ""
                            for col in _cols:
                                _v = row[col]
                                _align = "left" if col in ('ticker','nome') else "right"
                                _bg = ""
                                if col in _best_max and pd.notna(_v) and _v == _best_max[col]:
                                    _bg = "background:rgba(46,204,113,0.15);"
                                elif col in _best_min and pd.notna(_v) and _v == _best_min[col]:
                                    _bg = "background:rgba(46,204,113,0.15);"
                                if col == 'ticker':
                                    _tk_url = f"/Research?research_ticker={_v}"
                                    _cell = (f'<a href="{_tk_url}" target="_blank" style="color:var(--accent);'
                                             f'font-family:{_mn};font-weight:600;font-size:0.8rem;text-decoration:none;" '
                                             f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'
                                             f'{str(_v).replace(".SA","")}</a>')
                                elif col == 'nome':
                                    _cell = f'<span style="color:var(--text-muted);font-size:0.78rem;">{str(_v)[:20] if pd.notna(_v) else "—"}</span>'
                                elif col == 'health':
                                    try:
                                        _hi = int(_v)
                                        _hc = "#2ecc71" if _hi >= 65 else ("#f39c12" if _hi >= 40 else "#e74c3c")
                                        _cell = f'<span style="font-family:{_mn};font-size:0.8rem;color:{_hc};font-weight:600;">{_hi}</span>'
                                    except (TypeError, ValueError):
                                        _cell = '<span style="color:var(--text-muted);">—</span>'
                                elif col in ('roe%','dy%','mrg_liq%'):
                                    _cell = f'<span style="font-family:{_mn};font-size:0.8rem;">{_v:.1f}%</span>' if pd.notna(_v) else '<span style="color:var(--text-muted);">—</span>'
                                else:
                                    _cell = f'<span style="font-family:{_mn};font-size:0.8rem;">{_v:.1f}</span>' if pd.notna(_v) else '<span style="color:var(--text-muted);">—</span>'
                                _cells += f'<td style="padding:7px 10px;text-align:{_align};{_bg}">{_cell}</td>'
                            _rows += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                                      f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                                      f'onmouseout="this.style.background=\'transparent\'">{_cells}</tr>')
                        return (f'<div style="overflow-x:auto;">'
                                f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                                f'<thead><tr>{_hdrs}</tr></thead><tbody>{_rows}</tbody></table></div>')
                    st.markdown(_peers_table_html(df_comp), unsafe_allow_html=True)
            with c2:
                st.markdown("**performance relativa (base 100 — 10 anos)**")
                if not hist_all.empty:
                    df_b100 = (hist_all / hist_all.iloc[0]) * 100
                    fig_b100 = base100(df_b100, height=350)
                    st.plotly_chart(fig_b100, use_container_width=True, config={'responsive': True})
                    st.caption("cada ativo parte de 100 no início do período — mostra quem valorizou mais em termos relativos, ignorando o preço absoluto.")

    # ── HEALTH SCORES LADO A LADO ─────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("⚡ health scores comparados")

    _hs_comp_all = {
        h['ticker']: h
        for h in (get_health_scores() or [])
    }

    _cols_hs = st.columns(len(ativos_comp))
    for _ci_hs, (_col_hs, _tk_hs) in enumerate(zip(_cols_hs, ativos_comp)):
        _tb_hs   = mapear_ticker_base(_tk_hs)
        _row_hs  = (
            _hs_comp_all.get(_tb_hs)
            or _hs_comp_all.get(_tk_hs)
            or {}
        )
        # score=None no banco = indisponível; nesse caso tratamos como sem dado para o card
        _score_hs = _row_hs.get('score') if _row_hs else None

        _break_hs = {}
        if _row_hs:
            try:
                import json as _json_hs
                _raw_hs = _row_hs.get('alertas_venda', '{}')
                _p_hs   = (
                    _json_hs.loads(_raw_hs)
                    if isinstance(_raw_hs, str)
                    else (_raw_hs or {})
                )
                _break_hs = _p_hs.get('breakdown', {})
            except Exception:
                pass

        with _col_hs:
            if _score_hs is not None:
                _cor_hs_c = (
                    "var(--bull)" if _score_hs >= 65
                    else "var(--amber)" if _score_hs >= 40
                    else "var(--bear)"
                )
                _label_hs_c = (
                    "acumulação" if _score_hs >= 65
                    else "manutenção" if _score_hs >= 40
                    else "reduzir"
                )
                st.markdown(
                    f'<div style="background:var(--bg-surface); '
                    f'border:1px solid var(--border-subtle); '
                    f'border-top:3px solid {_cor_hs_c}; '
                    f'border-radius:6px; padding:16px; '
                    f'text-align:center;">'

                    f'<div style="font-family:var(--font-data,monospace); '
                    f'font-size:0.82rem; color:var(--accent); '
                    f'font-weight:700; margin-bottom:8px;">'
                    f'{_tk_hs.replace(".SA","")}</div>'

                    f'<div style="font-family:var(--font-data,monospace); '
                    f'font-size:2.2rem; font-weight:700; '
                    f'color:{_cor_hs_c}; line-height:1;">'
                    f'{_score_hs}'
                    f'<span style="font-size:1rem;color:var(--text-muted);">/100</span>'
                    f'</div>'

                    f'<div style="font-family:var(--font-data,monospace); '
                    f'font-size:0.72rem; color:{_cor_hs_c}; '
                    f'margin-top:4px;">{_label_hs_c}</div>'

                    f'</div>',
                    unsafe_allow_html=True,
                )

                if _break_hs:
                    _items_bk = []
                    for _k_bk, _v_bk in _break_hs.items():
                        try:
                            _items_bk.append((_k_bk, float(_v_bk)))
                        except (TypeError, ValueError):
                            pass
                    _items_bk.sort(key=lambda x: x[1], reverse=True)
                    _top_pos = _items_bk[:3]
                    _top_neg = [i for i in _items_bk if i[1] < 0][-2:]

                    for _kb, _vb in _top_pos:
                        _label_bk = _kb.replace('_', ' ')[:22]
                        st.markdown(
                            f'<div style="font-family:var(--font-data,monospace); '
                            f'font-size:0.65rem; color:var(--bull); '
                            f'padding:1px 0;">✓ {_label_bk}</div>',
                            unsafe_allow_html=True,
                        )
                    for _kb, _vb in _top_neg:
                        _label_bk = _kb.replace('_', ' ')[:22]
                        st.markdown(
                            f'<div style="font-family:var(--font-data,monospace); '
                            f'font-size:0.65rem; color:var(--bear); '
                            f'padding:1px 0;">✗ {_label_bk}</div>',
                            unsafe_allow_html=True,
                        )
            else:
                st.markdown(
                    f'<div style="background:var(--bg-surface); '
                    f'border:1px solid var(--border-subtle); border-radius:6px; '
                    f'padding:16px; text-align:center;">'
                    f'<div style="color:var(--accent); font-weight:700;">'
                    f'{_tk_hs.replace(".SA","")}</div>'
                    f'<div style="color:var(--text-muted); font-size:0.75rem; '
                    f'margin-top:8px;">score não calculado</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── VEREDITO DA IA ─────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("🧠 veredito — deepseek v4 pro")

    if st.button(
        "🧠 comparar e gerar veredito",
        type="primary",
        use_container_width=True,
        key="btn_veredito_comp",
    ):
        _linhas_comp_ia = []
        for _row_c in dados_comp:
            _tk_c    = _row_c.get('ticker', '')
            _hs_c    = (
                _hs_comp_all.get(mapear_ticker_base(_tk_c), {})
                .get('score', '—')
            )
            _linhas_comp_ia.append(
                f"{_tk_c}: "
                f"p/l={_row_c.get('p/l') or '—'} | "
                f"p/vp={_row_c.get('p/vp') or '—'} | "
                f"roe={_row_c.get('roe%') or '—'}% | "
                f"dy={_row_c.get('dy%') or '—'}% | "
                f"margem={_row_c.get('mrg_liq%') or '—'}% | "
                f"health={_hs_c}/100"
            )

        _macro_comp = st.session_state.get("macro_context", {})
        _prompt_comp_ia = (
            f"comparativo entre {len(ativos_comp)} ativos:\n\n"
            + "\n".join(_linhas_comp_ia)
            + f"\n\ncontexto macro: {_macro_comp.get('label','—')} | "
            f"selic {_macro_comp.get('selic',10.75):.2f}% | "
            f"vix {_macro_comp.get('vix',15.0):.1f}\n\n"
            "responda em 4 tópicos curtos (letra minúscula):\n"
            "1. qual tem melhor relação risco/retorno considerando "
            "fundamentos e health score?\n"
            "2. qual está mais barato pelo valuation atual?\n"
            "3. qual tem maior risco no ambiente macro atual?\n"
            "4. veredito final: se fosse escolher apenas um, qual "
            "seria e por quê? seja direto."
        )

        chamar_ia(
            prompt_usuario = _prompt_comp_ia,
            system         = SYSTEM_ANALISTA,
            max_tokens     = 600,
            temperatura    = 0.3,
            stream         = True,
            user_settings  = _user_settings,
        )

    st.stop()

# ==========================================
# MODO 1: DEEP DIVE (INDIVIDUAL)
# ==========================================
ticker = st.session_state['research_ticker']
t_base = mapear_ticker_base(ticker)
# Fonte única da verdade para detecção de FII (mesma lógica do health_engine).
# Antes uma lista de exceções local (3 tickers) divergia da do motor (15 tickers),
# fazendo SANB11/BPAC11/ALUP11 renderizarem como FII (KPIs e modelo P/VP errados).
from utils.health_engine import _is_fii
is_fii = _is_fii(ticker)

# Registra ativo no histórico de visitados (máx 5)
_hist_key = 'research_historico'
_hist = st.session_state.get(_hist_key, [])
if ticker and (not _hist or _hist[0] != ticker):
    _hist = [t for t in _hist if t != ticker]
    _hist.insert(0, ticker)
    st.session_state[_hist_key] = _hist[:5]

@st.cache_resource(ttl=3600)
def carregar_dados_ativo(tk):
    acao = yf.Ticker(tk)

    # ── histórico: bloco isolado — falha aqui é fatal ──────────────────────
    # Lê do cache Supabase (price_history); cai pra yfinance ao vivo se vazio.
    hist = pd.DataFrame()
    try:
        from utils.price_history import obter_ohlcv_ativo
        hist = obter_ohlcv_ativo(tk, periodo="10y")
    except Exception:
        pass  # hist permanece vazio — tratado logo abaixo

    # ── info: bloco isolado — falha aqui NÃO mata o histórico ──────────────
    # Via fachada (yf_info): circuit breaker central. Devolve {} em falha/circuito
    # aberto — o fallback para CACHE_FUNDAMENTOS abaixo trata isso.
    info = yf_info(tk)

    if hist.empty:
        return None, pd.DataFrame(), {}

    return acao, hist, info

acao_obj, df_hist, info_dict = carregar_dados_ativo(t_base)
if acao_obj is None or df_hist.empty:
    empty_state(
        "🔍",
        "ativo não encontrado",
        f"não foi possível carregar dados para '{ticker}'. "
        "verifique se o ticker está correto ou tente buscar "
        "pelo nome da empresa na barra de pesquisa acima.",
    )
    st.info(
        "💡 dica: ações BR precisam do sufixo .SA "
        "(ex: WEGE3.SA). ações EUA sem sufixo (ex: AAPL)."
    )
    st.stop()

cache_d = CACHE_FUNDAMENTOS.get(t_base, {})

# Busca múltiplos históricos FMP (escopo global — usado no prompt IA e na tab_val)
with st.spinner("carregando histórico de múltiplos (fmp)..."):
    _medios = get_multiplos_medios(t_base, anos=10)

# ── Fallback: busca fundamentos diretamente quando não está no cache ──────
# Ativos externos (buscados manualmente) não passam pelo sync do screener.
_qualidade_cache = cache_d.get('qualidade_dados', 0) if cache_d else 0
if not cache_d or _qualidade_cache < 30:
    with st.spinner(f"buscando fundamentos de {t_base}..."):
        try:
            _fund_fresh = (
                buscar_dados_b3(t_base) if t_base.endswith('.SA')
                else buscar_dados_us(t_base)
            )
            if _fund_fresh and _fund_fresh.get('qualidade_dados', 0) > 0:
                cache_d = _fund_fresh
                # Persiste no cache para próximas visitas
                salvar_fundamento_cache(t_base, _fund_fresh)
        except Exception as _e_fund:
            logging.getLogger(__name__).warning(
                f"[research] falha ao buscar fundamentos {t_base}: {_e_fund}"
            )

# --- HEADER & MÉTRICAS ---
nome_exibicao = info_dict.get('longName') or info_dict.get('shortName') or cache_d.get('nome') or ticker
moeda = "r$" if ticker.endswith(".SA") else "$"
setor_raw = cache_d.get('setor') or info_dict.get('sector')
setor = "logística (fii)" if "logística" in str(setor_raw).lower() else (setor_raw if setor_raw else ("fundo imobiliário" if is_fii else "mercado global"))

# Topbar fina sticky (Fase 6) — breadcrumb dinâmico com o ticker atual
_user_top = get_current_user() or {}
topbar(
    breadcrumb_itens=[
        ("⚡ finterminal", "/"),
        ("research", None),
        (ticker.replace(".SA", "").lower(), None),
    ],
    user_name=_user_top.get('username', '') or _user_top.get('nome', '') or 'usuário',
    sync_label="ao vivo",
)

# ── TICKER HERO (banner premium do ativo) ──────────────────────────────────
_preco_atual_th = 0.0
_var_1d_th = 0.0
_var_1m_th = 0.0
_var_ytd_th = 0.0
_serie_30d_th: list = []
_health_th = None
try:
    _close = df_hist['Close'].dropna()
    if len(_close) >= 2:
        _preco_atual_th = float(_close.iloc[-1])
        _var_1d_th = ((_preco_atual_th / float(_close.iloc[-2])) - 1) * 100
        # 1m: ~21 dias úteis
        if len(_close) >= 22:
            _var_1m_th = ((_preco_atual_th / float(_close.iloc[-22])) - 1) * 100
        # YTD: primeiro dia útil deste ano
        import datetime as _dt_th
        _ano_inicio = pd.Timestamp(_dt_th.date(_dt_th.date.today().year, 1, 1))
        _close_ytd = _close[_close.index >= _ano_inicio]
        if len(_close_ytd) >= 2:
            _var_ytd_th = ((_preco_atual_th / float(_close_ytd.iloc[0])) - 1) * 100
        _serie_30d_th = [float(x) for x in _close.tail(30).tolist()]
except Exception:
    pass

# Health score se houver
try:
    from database.db import get_health_scores as _ghs_th
    _h_map_th = {h['ticker']: h for h in (_ghs_th() or [])}
    _health_th = _h_map_th.get(t_base, {}).get('score')
    if _health_th is not None:
        _health_th = float(_health_th)
except Exception:
    _health_th = None

# Mercado label
_mkt_th = (
    "FII" if is_fii
    else "BR" if ticker.endswith(".SA")
    else "EUA"
)

ticker_hero(
    ticker      = ticker,
    nome        = nome_exibicao,
    setor       = setor,
    mercado     = _mkt_th,
    preco_atual = _preco_atual_th,
    moeda       = moeda.upper(),
    var_1d      = _var_1d_th,
    var_1m      = _var_1m_th,
    var_ytd     = _var_ytd_th,
    health      = _health_th,
    serie_30d   = _serie_30d_th,
)

# ── KPIs PRINCIPAIS (premium via portfolio_kpis) ───────────────────────────
if is_fii:
    pvp = safe_float(cache_d.get('p/vp')) or safe_float(info_dict.get('priceToBook'))
    _dy_raw_fii = safe_float(info_dict.get('dividendYield', 0))
    # yfinance retorna decimal. Sempre ×100.
    _dy_info_fii = (_dy_raw_fii * 100 if _dy_raw_fii and _dy_raw_fii <= 0.50 else 0)
    dy = safe_float(cache_d.get('dy%')) or _dy_info_fii
    mcap = safe_float(info_dict.get('marketCap')) or safe_float(cache_d.get('market_cap', 0))
    assets = safe_float(info_dict.get('totalAssets'))

    _pvp_tone = "bull" if (pvp and pvp < 1) else ("bear" if (pvp and pvp > 1.1) else "amber")
    _dy_tone  = "bull" if (dy and dy > 8) else "muted"

    _portfolio_kpis_v5([
        {
            "nome":     "preço / vp",
            "valor":    f"{pvp:.2f}" if pvp is not None else "n/d",
            "sublabel": "desconto" if pvp and pvp < 1 else ("ágio" if pvp else "—"),
            "tone":     _pvp_tone,
            "icone":    "🏷",
        },
        {
            "nome":     "dividend yield",
            "valor":    fmt_pct(dy),
            "sublabel": "últimos 12 meses",
            "tone":     _dy_tone,
            "icone":    "💵",
        },
        {
            "nome":     "mkt cap",
            "valor":    fmt_numero(mcap, moeda),
            "sublabel": "capitalização",
            "tone":     "info",
            "icone":    "📊",
        },
        {
            "nome":     "patrimônio líq.",
            "valor":    fmt_numero(assets, moeda),
            "sublabel": "ativos totais",
            "tone":     "info",
            "icone":    "🏛",
        },
    ])

    # Segmento e spread NTN-B para FIIs
    from utils.health_engine import _detectar_segmento_fii, _buscar_yield_ntnb
    _segmento_fii = _detectar_segmento_fii(t_base, cache_d)
    _ntnb_yield   = _buscar_yield_ntnb()

    _dy_fii   = safe_float(cache_d.get('dy%')) or 0.0
    _ipca_fii = st.session_state.get("macro_context", {}).get("ipca", 4.5)
    _dy_real  = ((1 + _dy_fii/100) / (1 + _ipca_fii/100) - 1) * 100
    _spread   = _dy_real - _ntnb_yield

    _cor_spread = (
        "var(--bull)" if _spread >= 2.5
        else "var(--amber)" if _spread >= 0
        else "var(--bear)"
    )

    # ── Bloco de spread NTN-B (premium via portfolio_kpis) ─────────────
    from utils.components import portfolio_kpis as _pf_kpis_fii
    _spread_tone = (
        "bull"  if _spread >= 2.5
        else "amber" if _spread >= 0
        else "bear"
    )
    _pf_kpis_fii([
        {
            "nome":     "segmento",
            "valor":    _segmento_fii,
            "sublabel": "categoria do FII",
            "tone":     "accent",
            "icone":    "🏢",
        },
        {
            "nome":     "yield real",
            "valor":    f"{_dy_real:.2f}%",
            "sublabel": "dy − inflação",
            "tone":     "info",
            "icone":    "📊",
        },
        {
            "nome":     "ntn-b benchmark",
            "valor":    f"{_ntnb_yield:.2f}%",
            "sublabel": "IPCA + (taxa real)",
            "tone":     "info",
            "icone":    "🏛",
        },
        {
            "nome":        "spread vs ntn-b",
            "valor":       f"{_spread:+.2f}pp",
            "sublabel":    "prêmio sobre tesouro",
            "tone":        _spread_tone,
            "icone":       "✨" if _spread >= 2.5 else ("⚠" if _spread < 0 else "📈"),
        },
    ])
    tooltip("ntnb_spread")

else:
    pl = safe_float(cache_d.get('p/l')) or safe_float(info_dict.get('trailingPE')) or safe_float(info_dict.get('forwardPE'))
    roe = safe_float(cache_d.get('roe%')) or (safe_float(info_dict.get('returnOnEquity', 0)) * 100)
    mrg = safe_float(cache_d.get('margem%')) or (safe_float(info_dict.get('profitMargins', 0)) * 100)
    _dy_raw_us = safe_float(info_dict.get('dividendYield', 0))
    # yfinance retorna decimal. Sempre ×100.
    _dy_info_us = (_dy_raw_us * 100 if _dy_raw_us and _dy_raw_us <= 0.50 else 0)
    dy = safe_float(cache_d.get('dy%')) or _dy_info_us

    _pl_tone  = "bull" if (pl and 5 < pl < 18) else ("bear" if (pl and pl > 30) else "amber")
    _roe_tone = "bull" if (roe and roe > 15) else ("amber" if (roe and roe > 8) else "muted")
    _mrg_tone = "bull" if (mrg and mrg > 10) else ("amber" if (mrg and mrg > 5) else "bear")
    _dy_tone  = "bull" if (dy and dy > 4) else "muted"

    _portfolio_kpis_v5([
        {
            "nome":     "preço / lucro",
            "valor":    f"{pl:.1f}x" if pl is not None else "n/d",
            "sublabel": "valuation",
            "tone":     _pl_tone,
            "icone":    "🏷",
        },
        {
            "nome":     "r.o.e",
            "valor":    fmt_pct(roe),
            "sublabel": "retorno sobre PL",
            "tone":     _roe_tone,
            "icone":    "📈",
        },
        {
            "nome":     "margem líq.",
            "valor":    fmt_pct(mrg),
            "sublabel": "eficiência operacional",
            "tone":     _mrg_tone,
            "icone":    "💰",
        },
        {
            "nome":     "div yield",
            "valor":    fmt_pct(dy),
            "sublabel": "últimos 12 meses",
            "tone":     _dy_tone,
            "icone":    "💵",
        },
    ])

st.markdown("<br>", unsafe_allow_html=True)

# ── CARD DE IMPACTO MACRO DO SETOR ────────────────────────────────────
# Impacto setorial via pilar_macro_setorial — o MESMO motor do health score
# (tilt de regime canônico + transmissão de inflação). Antes usava
# macro_regime.get_impacto_setor (matching de substring, vocabulário livre),
# que podia CONTRADIZER o breakdown do próprio score na mesma tela.
_macro_regime = classificar_regime()   # apenas o label do regime (canônico)
_market_rs = "US" if not ticker.endswith(".SA") else "BR"
try:
    from utils.inflation_sectoral import pilar_macro_setorial
    _pilar_rs = pilar_macro_setorial(
        setor, _market_rs, st.session_state.get("macro_context", {})
    )
except Exception:
    _pilar_rs = {"impacto": "neutro", "pontos": 0, "alertas": [], "breakdown": {}}
_pts_rs = int(_pilar_rs.get("pontos", 0) or 0)
_imp_rs = _pilar_rs.get("impacto", "neutro")
_motivos_rs = "; ".join(
    _pilar_rs.get("alertas", []) or [str(v) for v in _pilar_rs.get("breakdown", {}).values()]
)
_impacto_setor = {
    "impacto": _imp_rs,
    "pontos": _pts_rs,
    "cor": {"favoravel": "var(--bull)", "desfavoravel": "var(--bear)",
            "neutro": "var(--amber)"}.get(_imp_rs, "var(--amber)"),
    "justificativa": _motivos_rs or (
        f"vento macro-setorial {'a favor' if _pts_rs > 0 else 'contra' if _pts_rs < 0 else 'neutro'} "
        f"({_pts_rs:+d} pts)"
    ),
}
_icone_impacto = {"favoravel": "🟢", "desfavoravel": "🔴", "neutro": "🟡"}
_cor_regime = "var(--bear)" if "stress" in _macro_regime["label"] else ("var(--amber)" if "altos" in _macro_regime["label"] or "muito" in _macro_regime["label"] else "var(--bull)")
st.markdown(
    f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:6px;padding:8px 16px;margin-bottom:12px;display:flex;align-items:center;gap:28px;flex-wrap:wrap;">'
    f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.62rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;">regime</div>'
    f'<div style="font-family:var(--font-data,monospace);font-size:0.82rem;color:{_cor_regime};">{_macro_regime["label"]}</div>'
    f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.62rem;color:var(--text-muted);text-transform:uppercase;">setor</div>'
    f'<div style="font-family:var(--font-data,monospace);font-size:0.82rem;color:var(--text-primary);">{setor[:25].lower()}</div>'
    f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.62rem;color:var(--text-muted);text-transform:uppercase;">impacto</div>'
    f'<div style="font-family:var(--font-data,monospace);font-size:0.85rem;font-weight:600;color:{_impacto_setor["cor"]};">'
    f'{_icone_impacto[_impacto_setor["impacto"]]} {_impacto_setor["impacto"].upper()}</div>'
    f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.68rem;color:var(--text-muted);margin-left:auto;">{_impacto_setor["justificativa"][:50]}</div>'
    f'</div>',
    unsafe_allow_html=True,
)
# Persiste impacto_setor para uso no prompt da IA
st.session_state['impacto_setor_ativo'] = _impacto_setor
tooltip(
    "",
    texto_custom=(
        "indica como o regime macro atual afeta o setor deste ativo. "
        "baseado no framework de rotação setorial "
        "(fama-french 1989, msci sector rotation). "
        "favorecido: regime beneficia historicamente este setor. "
        "penalizado: regime desfavorece. neutro: sem impacto claro."
    )
)

# ── FORWARD-LOOKING (consenso de analistas + próximo resultado) ──────────
# Preenche a lacuna "só passado" do deep dive: forward P/E, EPS projetado,
# preço-alvo de consenso e próximo earnings — tudo de yfinance.info (BR e US).
if not is_fii:
    _fpe   = safe_float(info_dict.get('forwardPE'))
    _tpe   = safe_float(info_dict.get('trailingPE'))
    _feps  = safe_float(info_dict.get('forwardEps'))
    _teps  = safe_float(info_dict.get('trailingEps'))
    _tgt   = safe_float(info_dict.get('targetMeanPrice'))
    _tgtlo = safe_float(info_dict.get('targetLowPrice'))
    _tgthi = safe_float(info_dict.get('targetHighPrice'))
    _nan   = info_dict.get('numberOfAnalystOpinions')
    _reck  = str(info_dict.get('recommendationKey') or '').lower()
    _preco_fw = _preco_atual_th or (safe_float(info_dict.get('currentPrice')) or 0)

    if any(v is not None for v in (_fpe, _tgt, _feps)):
        section_title("🔮 forward-looking — consenso de analistas")

        # próximo earnings via acao_obj.calendar (objeto já cacheado; yfinance
        # guarda o calendar no ticker após a 1ª leitura).
        _earn_str, _earn_dias = None, None
        try:
            import datetime as _dt_e
            _cal = acao_obj.calendar
            _ed = _cal.get('Earnings Date') if isinstance(_cal, dict) else None
            _d0 = _ed[0] if isinstance(_ed, (list, tuple)) and _ed else (_ed or None)
            if _d0 is not None and hasattr(_d0, 'strftime'):
                _earn_str = _d0.strftime('%d/%m/%Y')
                try:
                    _earn_dias = (_d0 - _dt_e.date.today()).days
                except Exception:
                    _earn_dias = None
        except Exception:
            pass

        _fw1, _fw2, _fw3, _fw4 = st.columns(4)
        with _fw1:
            if _earn_str:
                _sub_e = f"em {_earn_dias} dias" if (_earn_dias is not None and _earn_dias >= 0) else "estimado"
                metric_card("próximo resultado", _earn_str, _sub_e,
                            "amber" if (_earn_dias is not None and 0 <= _earn_dias <= 14) else "info")
            else:
                metric_card("próximo resultado", "n/d", "sem data de earnings")
        with _fw2:
            if _fpe is not None and _fpe > 0:
                if _tpe and _fpe < _tpe:
                    _dir_pe, _tone_pe = "lucro esperado ↑", "bull"
                elif _tpe and _fpe > _tpe:
                    _dir_pe, _tone_pe = "lucro esperado ↓", "bear"
                else:
                    _dir_pe, _tone_pe = "estável", "muted"
                metric_card("forward p/l", f"{_fpe:.1f}x",
                            (f"trailing {_tpe:.1f}x · {_dir_pe}" if _tpe else _dir_pe), _tone_pe)
            else:
                metric_card("forward p/l", "n/d", "sem estimativa")
        with _fw3:
            if _tgt is not None and _preco_fw > 0:
                _upside = (_tgt / _preco_fw - 1) * 100
                _rng = f"faixa {moeda.upper()} {_tgtlo:.0f}–{_tgthi:.0f}" if (_tgtlo and _tgthi) else ""
                metric_card("preço-alvo (consenso)", f"{moeda.upper()} {_tgt:.2f}",
                            f"{_upside:+.0f}% vs atual · {_rng}".strip(" ·"),
                            "bull" if _upside > 10 else "bear" if _upside < -10 else "amber")
            else:
                metric_card("preço-alvo", "n/d", "sem cobertura de analistas")
        with _fw4:
            _rec_map = {'strong_buy': 'compra forte', 'buy': 'compra', 'hold': 'manter',
                        'underperform': 'reduzir', 'sell': 'venda'}
            _rec_txt = _rec_map.get(_reck, _reck or 'n/d')
            _rec_tone = "bull" if _reck in ('strong_buy', 'buy') else ("bear" if _reck in ('sell', 'underperform') else "muted")
            try:
                _nan_txt = f"{int(_nan)} analistas" if _nan else "consenso"
            except (TypeError, ValueError):
                _nan_txt = "consenso"
            metric_card("recomendação", _rec_txt, _nan_txt, _rec_tone)

        if _feps is not None and _teps not in (None, 0):
            _eps_g = (_feps / abs(_teps) - 1) * 100
            st.caption(
                f"eps projetado {moeda.upper()} {_feps:.2f} vs {moeda.upper()} {_teps:.2f} atual "
                f"→ o mercado embute crescimento de lucro de {_eps_g:+.0f}% no próximo exercício. "
                "compare com o crescimento realizado na tabela de fundamentos: projeção muito acima do "
                "histórico = preço otimista (risco de decepção); abaixo = expectativa conservadora."
            )
        st.markdown("<br>", unsafe_allow_html=True)

# ── HEALTH RESULT DO BANCO (para o prompt de IA e breakdown) ─────────────
_hs_all = get_health_scores()
_hs_map = {r['ticker']: r for r in (_hs_all or [])}
_hs_row = _hs_map.get(t_base, {})
if _hs_row:
    _raw = _hs_row.get('alertas_venda', '{}')
    _p   = _json.loads(_raw) if isinstance(_raw, str) else (_raw or {})
    # score=None no banco sinaliza dado indisponível (caminho de erro do engine);
    # exibimos 50 neutro na UI mas a tag de indisponibilidade fica no status/alertas.
    _score_db = _hs_row.get('score')
    health_result = {
        'score':     _score_db if _score_db is not None else 50,
        'score_indisponivel': _score_db is None,
        'status':    (_p.get('alertas') or ['—'])[0],
        'alertas':   _p.get('alertas', []),
        'breakdown': _p.get('breakdown', {}),
    }
else:
    health_result = {'score': 50, 'score_indisponivel': True, 'status': '—', 'alertas': [], 'breakdown': {}}

# --- EVOLUÇÃO DO HEALTH SCORE (últimos 180 dias) ---
historico = get_historico_score(t_base, dias=180)
if len(historico) >= 3:
    label_com_tooltip(
        "📈 EVOLUÇÃO DO HEALTH SCORE",
        chave="health_score",
        cor="var(--accent)",
        tamanho="0.72rem",
    )
    df_hist_score = pd.DataFrame(historico)
    df_hist_score['calculado_em'] = pd.to_datetime(df_hist_score['calculado_em'], format="ISO8601", utc=True)
    df_hist_score = df_hist_score.set_index('calculado_em')
    _hs_tipo  = chart_type_toggle(key=f"hs_{t_base}", default="linha")
    _cc_hs    = _chart_cores()
    from utils.charts import linha_ou_barras as _linha_ou_barras
    fig_score = _linha_ou_barras(
        df_hist_score, x_col=None, y_col='score',
        tipo=_hs_tipo,
        titulo=f"health score — {ticker} (180 dias)",
        cor=_cc_hs["accent"], cor_negativo=_cc_hs["bear"], height=220,
    )
    fig_score.add_hline(y=65, line_color=_cc_hs["bull"], line_dash="dash",
                        line_width=1, annotation_text="acumulação")
    fig_score.add_hline(y=40, line_color=_cc_hs["bear"], line_dash="dash",
                        line_width=1, annotation_text="reduzir")
    fig_score.update_yaxes(range=[0, 100])
    st.plotly_chart(fig_score, use_container_width=True, config={'responsive': True})
    st.caption("evolução do health score (0-100) nos últimos 180 dias. acima de 65 = zona de acumulação; abaixo de 40 = reduzir. quedas abruptas sinalizam deterioração de fundamentos ou técnico.")

    # ── BREAKDOWN VISUAL DO HEALTH SCORE ─────────────────────────────────
    _breakdown_vis = health_result.get('breakdown', {})
    if _breakdown_vis:
        label_com_tooltip(
            "🔬 BREAKDOWN DO HEALTH SCORE",
            texto_custom=(
                "decomposição do health score em seus pilares. "
                "barras verdes = pontos positivos. "
                "barras vermelhas = penalidades. "
                "pilares: piotroski, roic vs wacc, valuation, "
                "solvência, crescimento, momentum e dados macro."
            ),
            cor="var(--accent)",
            tamanho="0.72rem",
        )

        # Mapeamento de nomes internos para labels amigáveis
        _label_map = {
            # Piotroski
            'roa_positivo':          'ROA positivo (Piotroski)',
            'fcf_positivo':          'FCF positivo (Piotroski)',
            'roa_crescendo':         'ROA crescendo (Piotroski)',
            'accrual_ok':            'Qualidade do lucro (Piotroski)',
            'alavancagem_ok':        'Alavancagem saudável (Piotroski)',
            'liquidez_ok':           'Liquidez corrente (Piotroski)',
            'sem_diluicao':          'Sem diluição de ações (Piotroski)',
            'margem_crescendo':      'Margem bruta crescendo (Piotroski)',
            'giro_crescendo':        'Giro do ativo crescendo (Piotroski)',
            # ROIC/WACC
            'roic_vs_wacc':          'ROIC vs WACC (geração de valor)',
            'roic_acima_wacc':       'ROIC acima do custo de capital',
            # Valuation
            'pl_atrativo':           'P/L atrativo',
            'pvp_atrativo':          'P/VP atrativo',
            'dy_atrativo':           'Dividend yield atrativo',
            'ev_ebitda_ok':          'EV/EBITDA razoável',
            # Qualidade
            'roe_alto':              'ROE elevado',
            'margem_liquida_ok':     'Margem líquida saudável',
            'divida_controlada':     'Dívida controlada',
            # Momentum
            'momentum_12_1':         'Momentum 12-1 meses',
            'acima_mm200':           'Preço acima da MM200',
            'tendencia_alta':        'Tendência de alta',
            # FII específicos
            'pvp_fii_ok':            'P/VP atrativo (FII)',
            'yield_vs_selic':        'Yield vs Selic (FII)',
            'yield_atrativo':        'Dividend yield atrativo (FII)',
        }

        # Separa pilares com pontuação numérica de sub-rows informacionais
        # (ex.: "↳ ROIC = 3.0%", "↳ Momentum 12-1m = +51.6%" — strings que não
        # contribuem com pontos, mas detalham os pilares). Sub-rows entram em
        # uma lista expansível abaixo do gráfico, em vez de virar barra zerada.
        _itens_bd = []
        _itens_info = []  # [(label_curto, valor_str)]
        for k, v in _breakdown_vis.items():
            label = _label_map.get(k, k.replace('_', ' '))
            # 1) numérico direto?
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                _itens_bd.append({'label': label, 'pontos': float(v), 'chave': k})
                continue
            if isinstance(v, bool):
                _itens_bd.append({'label': label, 'pontos': float(v), 'chave': k})
                continue
            # 2) string "X/Y" → pontuação fracionada (Piotroski legacy)
            if isinstance(v, str) and '/' in v and v.count('/') == 1:
                try:
                    _itens_bd.append({'label': label, 'pontos': float(v.split('/')[0]),
                                      'chave': k})
                    continue
                except Exception:
                    pass
            # 3) string "sim"/"yes"/"✅"
            if isinstance(v, str) and v.lower() in ('sim', 'yes', 'true', '✅'):
                _itens_bd.append({'label': label, 'pontos': 1.0, 'chave': k})
                continue
            # 4) qualquer outra string = item informacional (não vai pro gráfico)
            if v is not None and v != '':
                _itens_info.append((label.lstrip('↳ ').strip(), str(v)))

        if _itens_bd:
            # Ordena: maiores pontos primeiro
            _itens_bd.sort(key=lambda x: x['pontos'], reverse=True)

            _labels_bd = [i['label'] for i in _itens_bd]
            _valores_bd = [i['pontos'] for i in _itens_bd]
            _cc_bd = _chart_cores()
            _cores_bd = [
                _cc_bd["bull"] if v > 0 else _cc_bd["bear"]
                for v in _valores_bd
            ]

            _fig_bd = go.Figure(go.Bar(
                x=_valores_bd,
                y=_labels_bd,
                orientation='h',
                marker_color=_cores_bd,
                hovertemplate="%{y}<br>pontos: %{x}<extra></extra>",
                text=[f"+{v:.0f}" if v > 0 else f"{v:.0f}" for v in _valores_bd],
                textposition='outside',
                textfont=dict(size=10, color=_cc_bd["muted"]),
            ))
            _lay_bd = base_layout(
                height=max(200, len(_itens_bd) * 28),
                title=f"pilares do score — {ticker.lower()} | total: {health_result.get('score', 0)}/100"
            )
            _lay_bd.update(
                xaxis={**{'showgrid': True, 'gridcolor': _cc_bd["border"],
                          'zeroline': True, 'zerolinecolor': _cc_bd["border"],
                          'title': 'pontos contribuídos'},
                       'range': [min(0, min(_valores_bd)) - 1,
                                 max(_valores_bd) + 2]},
                yaxis={'showgrid': False, 'title': ''},
                margin=dict(l=220, r=60, t=40, b=20),
            )
            _fig_bd.update_layout(**_lay_bd)
            st.plotly_chart(_fig_bd, use_container_width=True, config={'responsive': True})

            # Linha de resumo abaixo do gráfico
            _positivos = sum(1 for i in _itens_bd if i['pontos'] > 0)
            _negativos = sum(1 for i in _itens_bd if i['pontos'] <= 0)
            _qual_main = (
                cache_d.get('data_quality_pct') if cache_d else None
            ) or (
                cache_d.get('qualidade_dados') if cache_d else None
            )
            _fonte_main = cache_d.get('data_source', '') if cache_d else ''
            _atualizado_main = _hs_row.get('updated_at', '') if _hs_row else ''
            _badge_main = data_quality_badge(_qual_main, _fonte_main, _atualizado_main)
            st.markdown(
                f'<div style="font-family:var(--font-ui,sans-serif); font-size:0.72rem; '
                f'color:var(--text-muted); margin-top:-8px;">'
                f'✅ {_positivos} pilares positivos &nbsp;|&nbsp; '
                f'❌ {_negativos} pilares neutros ou negativos &nbsp;|&nbsp; '
                f'score total: {health_result.get("score", 0)}/100'
                f'{_badge_main}'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Detalhes informacionais (valores absolutos dos sub-rows) ──
            # ROIC%, momentum%, retorno último mês — não somam pontos, só explicam
            if _itens_info:
                with st.expander("📊 detalhes informacionais dos pilares", expanded=False):
                    _linhas_info = "".join(
                        f'<div style="display:flex; justify-content:space-between; '
                        f'padding:4px 0; border-bottom:1px solid var(--border-subtle);">'
                        f'<span style="color:var(--text-muted); font-size:0.78rem;">{_html_safe}</span>'
                        f'<span style="color:var(--text); font-family:var(--font-mono); font-size:0.78rem;">{_val_safe}</span>'
                        f'</div>'
                        for _html_safe, _val_safe in (
                            (str(lbl).replace('<', '&lt;'), str(val).replace('<', '&lt;'))
                            for lbl, val in _itens_info
                        )
                    )
                    st.markdown(
                        f'<div style="font-family:var(--font-ui,sans-serif);">{_linhas_info}</div>',
                        unsafe_allow_html=True,
                    )

# ── SEÇÃO: VALUATION EM CONTEXTO HISTÓRICO (FMP) ────────────────────────
def _render_multiplo_card(label: str, valor_atual, stats: dict | None, sufixo: str = "×"):
    """Renderiza card de múltiplo com barra de posição histórica e cor de sinal."""
    if stats is None or valor_atual is None:
        st.markdown(
            f'<div style="background:var(--bg-surface);border-radius:var(--radius-sm,6px);padding:12px 14px;margin-bottom:8px;">'
            f'<div style="font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;">{label}</div>'
            f'<div style="font-size:1.1rem;color:var(--text-muted);">—</div>'
            f'<div style="font-size:0.65rem;color:var(--text-muted);margin-top:4px;">sem histórico FMP</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    media = stats["media"]
    minv  = stats["min"]
    maxv  = stats["max"]
    atual = float(valor_atual)

    # posição na banda histórica (0–1)
    banda = maxv - minv if maxv != minv else 1.0
    pos   = max(0.0, min(1.0, (atual - minv) / banda))

    # sinal de cor
    if media > 0:
        desvio = (atual - media) / media
        if desvio <= -0.15:
            cor, sinal = "var(--bull)", "▼ desconto"
        elif desvio >= 0.20:
            cor, sinal = "var(--bear)", "▲ prêmio"
        else:
            cor, sinal = "var(--amber)", "≈ justo"
    else:
        cor, sinal = "var(--text-muted)", "—"

    bar_fill  = f"width:{round(pos * 100)}%;"
    bar_color = cor

    st.markdown(
        f'<div style="background:var(--bg-surface);border-radius:var(--radius-sm,6px);padding:12px 14px;margin-bottom:8px;">'
        f'<div style="font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;">{label}</div>'
        f'<div style="font-size:1.25rem;font-weight:600;color:{cor};">{atual:.1f}{sufixo}</div>'
        f'<div style="font-size:0.65rem;color:var(--text-secondary);margin-top:2px;">'
        f'média 5a: {media:.1f}{sufixo} &nbsp;|&nbsp; {sinal}'
        f'</div>'
        f'<div style="background:var(--border-normal,#333);border-radius:2px;height:4px;margin-top:6px;">'
        f'<div style="background:{bar_color};border-radius:2px;height:4px;{bar_fill}"></div>'
        f'</div>'
        f'<div style="display:flex;justify-content:space-between;font-size:0.58rem;color:var(--text-muted);margin-top:2px;">'
        f'<span>{minv:.1f}</span><span>{maxv:.1f}</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

def _render_historico_proventos(divs_raw, modo, ticker, moeda):
    """
    Cards + gráfico + tabela do histórico de proventos (P3-3).
    modo='fii'  → cadência mensal, janela 24 meses, por cota (4 casas decimais).
    modo='acao' → agregação ANUAL, janela 5 anos, por ação (2 casas).
    Extraído do bloco antes exclusivo de FII para reuso em ações pagadoras.
    """
    _cur = moeda.lower()
    _dec = 4 if modo == 'fii' else 2
    if divs_raw is None or (hasattr(divs_raw, 'empty') and divs_raw.empty):
        st.info("empresa não distribuiu proventos no período ou dados indisponíveis.")
        return
    _divs = divs_raw.copy()
    if getattr(_divs.index, 'tz', None) is not None:
        _divs.index = _divs.index.tz_localize(None)

    if modo == 'fii':
        _cutoff = pd.Timestamp.now() - pd.DateOffset(months=24)
        _serie = _divs[_divs.index >= _cutoff].sort_index()
        _lbl_ult, _lbl_media, _lbl_cont = "último provento", "média mensal (24m)", "pagamentos no período"
        _sub_ult, _sub_media = "por cota", "por cota"
        _sub_janela, _cont_bom = "últimos 24 meses", 20
        _titulo_graf = f"proventos mensais — {ticker.lower()} (24 meses)"
        _y_titulo = f"{_cur} por cota"
    else:
        _cutoff = pd.Timestamp.now() - pd.DateOffset(years=5)
        _d5 = _divs[_divs.index >= _cutoff].sort_index()
        if _d5.empty:
            st.info("empresa não distribuiu proventos nos últimos 5 anos.")
            return
        _serie = _d5.groupby(_d5.index.year).sum()
        _serie.index = pd.to_datetime([f"{int(y)}-12-31" for y in _serie.index])
        _lbl_ult, _lbl_media, _lbl_cont = "último ano", "média anual (5a)", "anos com pagamento"
        _sub_ult, _sub_media = "total no ano", "por ação"
        _sub_janela, _cont_bom = "últimos 5 anos", 5
        _titulo_graf = f"proventos anuais — {ticker.lower()} (5 anos)"
        _y_titulo = f"{_cur} por ação"

    if _serie.empty:
        st.info(f"nenhum provento encontrado nos {_sub_janela}.")
        return

    _n = len(_serie)
    _media = float(_serie.mean())
    _ult = float(_serie.iloc[-1])
    _meio = _n // 2
    _m1 = float(_serie.iloc[:_meio].mean()) if _meio > 0 else _media
    _m2 = float(_serie.iloc[_meio:].mean()) if _meio > 0 else _media
    _var_tend = (_m2 / _m1 - 1) * 100 if _m1 > 0 else 0

    _cc = _chart_cores()
    if _var_tend >= 5:
        _tend_label, _tend_cor, _tend_tipo = "📈 crescendo", _cc["bull"], "bull"
    elif _var_tend <= -5:
        _tend_label, _tend_cor, _tend_tipo = "📉 caindo", _cc["bear"], "bear"
    else:
        _tend_label, _tend_cor, _tend_tipo = "➡️ estável", _cc["amber"], "amber"

    _d1, _d2, _d3, _d4 = st.columns(4)
    with _d1:
        metric_card(_lbl_ult, f"{_cur} {_ult:.{_dec}f}", _sub_ult)
    with _d2:
        metric_card(_lbl_media, f"{_cur} {_media:.{_dec}f}", _sub_media)
    with _d3:
        metric_card("tendência dos proventos", _tend_label,
                    f"{_var_tend:+.1f}% (1ª vs 2ª metade)", _tend_tipo)
    with _d4:
        metric_card(_lbl_cont, str(_n), _sub_janela, "bull" if _n >= _cont_bom else "amber")

    st.markdown("<br>", unsafe_allow_html=True)
    _tipo = chart_type_toggle(key=f"div_{ticker}_{modo}", default="barras")
    _x = [str(d.year) for d in _serie.index] if modo == 'acao' else [str(d.date()) for d in _serie.index]
    _vlist = _serie.values.tolist()
    _cores = [_cc["bull"] if v >= _media else _cc["accent"] for v in _vlist]
    _fig = go.Figure()
    if _tipo == "barras":
        _fig.add_trace(go.Bar(x=_x, y=_vlist, marker_color=_cores, name="provento"))
    else:
        _fig.add_trace(go.Scatter(x=_x, y=_vlist, mode="lines+markers",
            line=dict(color=_cc["accent"], width=2), marker=dict(color=_cores, size=7), name="provento"))
    _fig.add_hline(y=_media, line_color=_cc["accent"], line_dash="dash", line_width=1,
        annotation_text=f"média {_cur} {_media:.{_dec}f}", annotation_font_color=_cc["accent"], annotation_font_size=9)
    if _n >= 4:
        _xr = list(range(_n))
        _coef = np.polyfit(_xr, _vlist, 1)
        _tr = [_coef[0] * x + _coef[1] for x in _xr]
        _fig.add_trace(go.Scatter(x=_x, y=_tr, mode="lines",
            line=dict(color=_tend_cor, width=1.5, dash="dot"), name="tendência"))
    _lay = base_layout(height=280, title=_titulo_graf)
    _lay.update(
        xaxis=dict(showgrid=False, tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(showgrid=True, gridcolor=_cc["border"], title=_y_titulo),
        margin=dict(l=60, r=20, t=40, b=60),
    )
    _fig.update_layout(**_lay)
    st.plotly_chart(_fig, use_container_width=True, config={'responsive': True})
    if modo == 'fii':
        st.caption("proventos mensais por cota (24 meses). a linha tracejada é a média e a de tendência mostra se os rendimentos crescem ou encolhem — chave para a sustentabilidade do dividend yield.")
    else:
        st.caption("proventos anuais por ação (5 anos). tendência de alta sinaliza política de dividendos consistente; cortes indicam pressão nos lucros ou mudança de alocação de capital.")

    st.markdown("<br>", unsafe_allow_html=True)
    _ncols = 12 if modo == 'fii' else _n
    section_title(f"últimos {_ncols} proventos" if modo == 'fii' else "proventos por ano")
    _ult_serie = _serie.iloc[-_ncols:].sort_index(ascending=False)
    _rows_div = []
    _prev_val = None
    for _idx_d, _val_d in _ult_serie.items():
        _val_f = float(_val_d)
        if _prev_val is not None and _prev_val > 0:
            _var_m = (_val_f / _prev_val - 1) * 100
            _var_s = f"{_var_m:+.1f}%"
        else:
            _var_s = "—"
        _rows_div.append({
            'data': str(_idx_d.year) if modo == 'acao' else str(_idx_d.date()),
            'provento': f"{_cur} {_val_f:.{_dec}f}",
            'vs anterior': _var_s,
            'vs média': f"{(_val_f/_media - 1)*100:+.1f}%" if _media > 0 else "—",
        })
        _prev_val = _val_f

    _mn = 'var(--font-mono,monospace)'
    _hdrs = "".join(
        f'<th style="padding:7px 10px;text-align:{"left" if i==0 else "right"};'
        f'font-size:0.67rem;color:var(--text-muted);text-transform:uppercase;'
        f'border-bottom:1px solid var(--border-subtle);">{h}</th>'
        for i, h in enumerate(['Período' if modo == 'acao' else 'Data', 'Provento', 'vs anterior', 'vs média'])
    )
    _body = ""
    for r in _rows_div:
        _va, _vm = r['vs anterior'], r['vs média']
        _cv = "#2ecc71" if str(_va).startswith('+') else ("#e74c3c" if str(_va).startswith('-') else "var(--text-muted)")
        _cvm = "#2ecc71" if str(_vm).startswith('+') else ("#e74c3c" if str(_vm).startswith('-') else "var(--text-muted)")
        _body += (
            f'<tr style="border-bottom:1px solid var(--border-subtle);">'
            f'<td style="padding:7px 10px;font-family:{_mn};font-size:0.78rem;color:var(--text-muted);">{r["data"]}</td>'
            f'<td style="padding:7px 10px;font-family:{_mn};font-size:0.82rem;font-weight:600;text-align:right;">{r["provento"]}</td>'
            f'<td style="padding:7px 10px;font-family:{_mn};font-size:0.8rem;color:{_cv};text-align:right;">{_va}</td>'
            f'<td style="padding:7px 10px;font-family:{_mn};font-size:0.8rem;color:{_cvm};text-align:right;">{_vm}</td>'
            f'</tr>'
        )
    st.markdown(
        f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
        f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
        f'<thead><tr>{_hdrs}</tr></thead><tbody>{_body}</tbody></table></div>',
        unsafe_allow_html=True,
    )


# (FMP valuation movido para tab_val)

section_title("🧠 análise ia — deepseek v4 pro")


def montar_prompt_ativo(
    ticker, nome, setor, tipo_mercado,
    fundamentos, health_result,
    preco_atual, var_1d, macro_context,
    multiplos_historicos: dict = None,   # ← novo parâmetro
    impacto_setor: dict = None,
) -> str:
    """
    Monta prompt em ordem cache-friendly.
    Estático primeiro (identidade → fundamentos → histórico FMP →
    score → macro), volátil por último.
    """
    fund = fundamentos or {}

    # ── BLOCO 1: IDENTIDADE ──────────────────────────────────────────────
    b1 = (
        f"ativo: {ticker.upper()}\n"
        f"nome: {nome}\n"
        f"setor: {setor}\n"
        f"mercado: {tipo_mercado}\n"
        f"tipo: {'fii' if '11.SA' in ticker else 'acao br' if '.SA' in ticker else 'acao us'}\n"
    )

    # ── BLOCO 2: FUNDAMENTOS ATUAIS ─────────────────────────────────────
    b2 = (
        f"\nfundamentos atuais:\n"
        f"p/l: {fund.get('p/l', 'n/d')}\n"
        f"p/vp: {fund.get('p/vp', 'n/d')}\n"
        f"roe: {fund.get('roe%', 'n/d')}%\n"
        f"dividend yield: {fund.get('dy%', 'n/d')}%\n"
        f"margem liquida: {fund.get('margem%', 'n/d')}%\n"
        f"ev/ebitda: {fund.get('ev/ebitda', 'n/d')}\n"
        f"qualidade dos dados: {fund.get('qualidade_dados', 0)}%\n"
    )

    # ── BLOCO 3: VALUATION HISTÓRICO FMP (5 anos) ────────────────────────
    # Dados já carregados na página — só formata para o prompt
    b3 = ""
    if multiplos_historicos:
        linhas_hist = []

        def _fmt_stats(stats, sufixo="x"):
            if not stats:
                return "sem dados"
            atual  = stats.get("atual")
            media  = stats.get("media")
            minv   = stats.get("min")
            maxv   = stats.get("max")
            if atual is None or media is None:
                return "sem dados"
            banda  = (maxv - minv) if maxv and minv and maxv != minv else 1.0
            pct    = int(max(0, min(100, (atual - minv) / banda * 100))) if banda else 50
            desvio = (atual - media) / media * 100 if media != 0 else 0
            sinal  = "caro" if desvio > 20 else ("barato" if desvio < -15 else "justo")
            return (
                f"atual {atual:.1f}{sufixo} | "
                f"média 5a {media:.1f}{sufixo} | "
                f"percentil histórico {pct}% | "
                f"sinal: {sinal} ({desvio:+.0f}% vs média)"
            )

        if multiplos_historicos.get("pe"):
            linhas_hist.append(f"p/l: {_fmt_stats(multiplos_historicos['pe'])}")
        if multiplos_historicos.get("pb"):
            linhas_hist.append(f"p/vp: {_fmt_stats(multiplos_historicos['pb'])}")
        if multiplos_historicos.get("ev_ebitda"):
            linhas_hist.append(f"ev/ebitda: {_fmt_stats(multiplos_historicos['ev_ebitda'])}")
        if multiplos_historicos.get("dy"):
            linhas_hist.append(f"dividend yield: {_fmt_stats(multiplos_historicos['dy'], sufixo='%')}")
        if multiplos_historicos.get("roe"):
            linhas_hist.append(f"roe histórico: {_fmt_stats(multiplos_historicos['roe'], sufixo='%')}")

        if linhas_hist:
            b3 = (
                "\nvaluation em contexto histórico (5 anos via FMP):\n"
                + "\n".join(linhas_hist)
                + "\n"
            )

    # ── BLOCO 4: HEALTH SCORE ────────────────────────────────────────────
    alertas   = health_result.get('alertas', [])
    breakdown = health_result.get('breakdown', {})
    alertas_txt = "\n".join([f"- {a}" for a in alertas[:8]])
    bkdown_txt  = "\n".join([f"- {k}: {v}" for k, v in list(breakdown.items())[:10]])
    b4 = (
        f"\nhealth score: {health_result.get('score', 50)}/100\n"
        f"status: {health_result.get('status', 'n/d')}\n\n"
        f"alertas do motor quantitativo:\n{alertas_txt}\n\n"
        f"breakdown:\n{bkdown_txt}\n"
    )

    # ── BLOCO 5: CONTEXTO MACRO ──────────────────────────────────────────
    b5 = (
        f"\ncontexto macro:\n"
        f"selic: {macro_context.get('selic', 10.75):.2f}%\n"
        f"vix: {macro_context.get('vix', 15.0):.1f}\n"
        f"ipca: {macro_context.get('ipca', 4.5):.1f}%\n"
        f"regime: {macro_context.get('label', 'neutro')}\n"
    )

    # ---- BLOCO 5B: IMPACTO SETORIAL (MACRO) ----
    b5b = ""
    if impacto_setor:
        b5b = (
            f"impacto do regime no setor: {impacto_setor.get('impacto', 'neutro')}\n"
            f"justificativa: {impacto_setor.get('justificativa', 'n/d')}\n"
        )

    # ---- BLOCO 6: DADOS VOLÁTEIS — SEMPRE POR ÚLTIMO ──────────────────────
    b6 = (
        f"\ncotacao atual: r$ {preco_atual:,.2f}\n"
        f"variacao hoje: {var_1d:+.2f}%\n"
    )

    instrucao = (
        "\ncom base nos dados acima, forneça a análise nos seguintes tópicos:\n\n"
        "tese central: argumento principal para manter ou não este ativo (2 linhas máximo)\n\n"
        "pontos positivos: (3 bullets)\n"
        "- o que está funcionando nos fundamentos ou no técnico\n\n"
        "riscos principais: (3 bullets)\n"
        "- o que pode destruir a tese ou prejudicar o retorno\n\n"
        "valuation: (2 bullets)\n"
        "- interprete se o ativo está caro ou barato considerando o histórico de 5 anos\n"
        "- use os dados de percentil histórico fornecidos acima\n\n"
        "impacto macro: (2 bullets)\n"
        "- como o regime atual de juros e risco afeta especificamente este ativo\n\n"
        "métrica para monitorar:\n"
        "- uma métrica específica com frequência sugerida de acompanhamento\n\n"
        "seja objetivo. use os dados fornecidos. não invente números."
    )

    return b1 + b2 + b3 + b4 + b5 + b5b + b6 + instrucao


# --- TABS ---
# LAZY RENDERING (P4-1): st.tabs renderiza TODAS as abas a cada rerun. Aqui isso
# recalcula FMP, técnico, DRE, IA e overlay de uma vez. Trocado por um seletor que
# renderiza só a seção ativa (os blocos `with tab_X:` viraram `if _secao_r == ...`).
# As abas leem apenas variáveis de módulo (calculadas antes) — sem dependência cruzada.
_SECOES_R = ["📊 valuation & peers", "📈 técnico (10y)", "💎 fundamentos",
             "🧠 análise & ia", "🌍 overlay macro"]
if hasattr(st, "segmented_control"):
    _secao_r = st.segmented_control(
        "seção", _SECOES_R, default=_SECOES_R[0],
        key="research_secao", label_visibility="collapsed",
    ) or st.session_state.get("research_secao") or _SECOES_R[0]
else:
    _secao_r = st.radio("seção", _SECOES_R, index=0, horizontal=True,
                        key="research_secao", label_visibility="collapsed")

if _secao_r == "📊 valuation & peers":
    # ── VALUATION EM CONTEXTO HISTÓRICO (FMP) ────────────────────────
    if _medios:
        section_title("📊 valuation em contexto histórico (10 anos)")
        _col_pe, _col_pb, _col_ev, _col_dy = st.columns(4)
        with _col_pe:
            _render_multiplo_card("P/L", cache_d.get('p/l'), _medios.get('pe'))
        with _col_pb:
            _render_multiplo_card("P/VP", cache_d.get('p/vp'), _medios.get('pb'))
        with _col_ev:
            _render_multiplo_card("EV/EBITDA", cache_d.get('ev/ebitda'), _medios.get('ev_ebitda'))
        with _col_dy:
            _render_multiplo_card("Div. Yield", cache_d.get('dy%'), _medios.get('dy'), sufixo="%")
    else:
        section_title("📊 múltiplos atuais")
        st.markdown(
            '<div style="font-family:var(--font-ui,sans-serif); font-size:0.68rem; '
            'color:var(--text-muted); margin-bottom:12px;">'
            'histórico via FMP não disponível para este ativo. '
            'exibindo múltiplos do cache local.'
            '</div>',
            unsafe_allow_html=True,
        )
        _cols_mult = st.columns(4)
        _metricas_basicas = [
            ("P/L",       cache_d.get('p/l'),    ""),
            ("P/VP",      cache_d.get('p/vp'),   ""),
            ("ROE %",     cache_d.get('roe%'),    "%"),
            ("Div Yield", cache_d.get('dy%'),     "%"),
        ]
        for _cm, (_lbl, _val, _suf) in zip(_cols_mult, _metricas_basicas):
            with _cm:
                _val_str = f"{float(_val):.2f}{_suf}" if _val is not None else "n/d"
                metric_card(_lbl.lower(), _val_str)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── COMPARAÇÃO COM PEERS ─────────────────────────────────────────────
    with st.spinner("buscando peers do setor..."):
        _peers_list = get_peers(t_base)

    # Fallback local: FMP não retornou peers → busca tickers do mesmo setor no cache
    _peers_fonte = "fmp"
    if not _peers_list and setor_raw:
        _stop_words_p = {"e", "de", "do", "da", "dos", "das", "o", "a", "em", "por"}
        _setor_norm_p = str(setor_raw).lower().strip()
        _setor_kws_p  = set(_setor_norm_p.replace(",", " ").split()) - _stop_words_p
        _candidatos_p = []
        for _tk_p, _fd_p in CACHE_FUNDAMENTOS.items():
            if _tk_p == t_base:
                continue
            _s_p = str(_fd_p.get('setor') or '').lower().strip()
            if not _s_p:
                continue
            _s_kws_p = set(_s_p.replace(",", " ").split()) - _stop_words_p
            if _setor_kws_p & _s_kws_p:
                _candidatos_p.append(_tk_p)
        if _candidatos_p:
            _candidatos_p.sort(
                key=lambda x: -(float(CACHE_FUNDAMENTOS[x].get('roe%') or 0))
            )
            _peers_list  = _candidatos_p[:6]
            _peers_fonte = "local"

    def _fmt_num(v, dec=1):
        try:    return f"{float(v):.{dec}f}" if v is not None else "—"
        except: return "—"

    if _peers_list:
        _fonte_tag = (
            '<span style="font-size:0.6rem;color:var(--text-muted);'
            'font-family:var(--font-ui,sans-serif);margin-left:6px;">'
            + ("via fmp" if _peers_fonte == "fmp" else "base local · mesmo setor")
            + '</span>'
        )
        section_title(f"👥 comparação com peers {_fonte_tag}")

        _h1, _h2, _h3, _h4, _h5, _h6 = st.columns([2, 3, 1, 1, 1, 1], gap="small")
        for _hcol, _htxt in zip(
            [_h1, _h2, _h3, _h4, _h5, _h6],
            ["ticker", "nome", "p/l", "roe%", "dy%", "margem%"],
        ):
            _hcol.markdown(
                f'<div style="font-size:0.65rem;color:var(--text-muted);'
                f'text-transform:uppercase;padding-bottom:4px;">{_htxt}</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div style="border-top:1px solid var(--border-subtle);margin-bottom:6px;"></div>',
            unsafe_allow_html=True,
        )

        _tickers_peers = [t_base] + [p for p in _peers_list if p != t_base][:5]
        for _pt in _tickers_peers:
            _pd_peer    = CACHE_FUNDAMENTOS.get(_pt, {})
            _is_atual   = (_pt == t_base)
            _fw_peer    = "600" if _is_atual else "400"
            _cor_t_css  = "var(--accent)" if _is_atual else "var(--text-secondary)"
            _nome_peer  = _pd_peer.get('nome') or _pt
            _pe_peer    = _pd_peer.get('p/l')
            _roe_peer   = _pd_peer.get('roe%')
            _dy_peer    = _pd_peer.get('dy%')
            _mrg_peer   = _pd_peer.get('margem_liq%') or _pd_peer.get('mrg_liq%')

            _p1, _p2, _p3, _p4, _p5, _p6 = st.columns([2, 3, 1, 1, 1, 1], gap="small")
            _p1.markdown(
                f'<span style="color:{_cor_t_css};font-weight:{_fw_peer};'
                f'font-size:0.85rem;font-family:var(--font-data,monospace);">{_pt}</span>',
                unsafe_allow_html=True,
            )
            _p2.markdown(
                f'<span style="font-size:0.8rem;color:var(--text-secondary);">'
                f'{_nome_peer[:22]}</span>',
                unsafe_allow_html=True,
            )
            for _pc, _pv in zip([_p3, _p4, _p5, _p6], [_pe_peer, _roe_peer, _dy_peer, _mrg_peer]):
                _pc.markdown(
                    f'<span style="font-size:0.85rem;color:var(--text-primary);">'
                    f'{_fmt_num(_pv)}</span>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                '<div style="border-top:1px solid var(--border-subtle);margin:3px 0;"></div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="font-size:0.72rem;color:var(--text-muted);padding:8px 0;">'
            'comparação com peers não disponível — sem setor definido para este ativo.'
            '</div>',
            unsafe_allow_html=True,
        )

if _secao_r == "📈 técnico (10y)":
    try:
        fig_tec = go.Figure()
        fig_tec.add_trace(go.Candlestick(x=df_hist.index, open=df_hist['Open'], high=df_hist['High'], low=df_hist['Low'], close=df_hist['Close'], name="price"))
        if len(df_hist) >= 50: fig_tec.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Close'].rolling(50).mean(), name="mm50", line=dict(color=CORES_SERIES[1], width=1)))
        if len(df_hist) >= 200: fig_tec.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Close'].rolling(200).mean(), name="mm200", line=dict(color=CORES_SERIES[3], width=1.5)))
        fig_tec.update_layout(**base_layout(height=500, title=f"price action histórico (10 anos): {ticker.lower()}"))
        fig_tec.update_layout(xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_tec, use_container_width=True, config={'responsive': True})
        st.caption("candlestick de 10 anos com médias de 50 e 200 dias. preço acima da mm200 = tendência de alta estrutural; mm50 cruzando abaixo da mm200 (cruz da morte) é sinal técnico de baixa.")
    except Exception as e: st.error(f"Erro gráfico técnico: {e}")

if _secao_r == "💎 fundamentos":
    section_title("📊 demonstrações financeiras (dre)")
    if is_fii: st.info("💡 FIIs não possuem DRE trimestral padrão. Avalie os Rendimentos em Fundamentos.")
    else:
        # Prefere o histórico trimestral JÁ no cache (CVM/yfinance) — sem novas
        # chamadas de rede. Cai para o gráfico yfinance ao vivo se ausente.
        _hist_tri = cache_d.get('historico_trimestral') if cache_d else None
        if isinstance(_hist_tri, list) and len(_hist_tri) >= 2:
            _rows_ft = _hist_tri[:12]  # mais recente primeiro

            def _gt(d, k):
                v = d.get(k) if d else None
                try:
                    return float(v) if v is not None else None
                except (TypeError, ValueError):
                    return None

            def _fmt_val(v):
                if v is None:
                    return "—"
                sig = "-" if v < 0 else ""
                a = abs(v)
                pref = moeda.upper() + " "
                if a >= 1e9:
                    return f"{sig}{pref}{a/1e9:,.1f}b"
                if a >= 1e6:
                    return f"{sig}{pref}{a/1e6:,.0f}m"
                return f"{sig}{pref}{a:,.0f}"

            def _yoy(rows, i, key):
                if i + 4 >= len(rows):
                    return None
                a = _gt(rows[i], key)
                b = _gt(rows[i + 4], key)
                if a is None or b is None or b == 0:
                    return None
                return (a / abs(b) - 1) * 100

            _mn_ft = 'var(--font-mono,monospace)'
            _cols_ft = ['período', 'receita', 'mrg bruta', 'mrg líq', 'ebitda', 'lucro', 'cfo', 'dív. líq.']
            _hdr_ft = "".join(
                f'<th style="padding:6px 9px;text-align:{"left" if i==0 else "right"};font-size:0.62rem;'
                f'color:var(--text-muted);text-transform:uppercase;border-bottom:1px solid var(--border-subtle);'
                f'white-space:nowrap;">{c}</th>'
                for i, c in enumerate(_cols_ft)
            )

            def _yoy_span(y):
                if y is None:
                    return ""
                _c = "#2ecc71" if y >= 0 else "#e74c3c"
                return f' <span style="font-size:0.6rem;color:{_c};">{y:+.0f}%</span>'

            def _cell_ft(txt, cor=None):
                _c = f'color:{cor};' if cor else ''
                return f'<td style="padding:6px 9px;text-align:right;font-family:{_mn_ft};font-size:0.74rem;{_c}">{txt}</td>'

            _body_ft = ""
            for i, r in enumerate(_rows_ft):
                _per = str(r.get('periodo', '—'))[:7]
                _rec = _gt(r, 'receita'); _luc = _gt(r, 'lucro')
                _gross = _gt(r, 'gross'); _ebitda = _gt(r, 'ebitda'); _cfo = _gt(r, 'cfo')
                _div = _gt(r, 'divida_total'); _cash = _gt(r, 'cash')
                _ndiv = (_div - (_cash or 0)) if _div is not None else None
                _mb = (_gross / _rec * 100) if (_gross is not None and _rec) else None
                _ml = (_luc / _rec * 100) if (_luc is not None and _rec) else None
                _mlc = "#2ecc71" if (_ml is not None and _ml >= 0) else ("#e74c3c" if _ml is not None else None)
                _ndc = "#e74c3c" if (_ndiv is not None and _ndiv > 0) else ("#2ecc71" if _ndiv is not None else None)
                _body_ft += (
                    f'<tr style="border-bottom:1px solid var(--border-subtle);">'
                    f'<td style="padding:6px 9px;font-family:{_mn_ft};font-size:0.72rem;color:var(--text-muted);">{_per}</td>'
                    + _cell_ft(_fmt_val(_rec) + _yoy_span(_yoy(_rows_ft, i, 'receita')))
                    + _cell_ft(f"{_mb:.1f}%" if _mb is not None else "—")
                    + _cell_ft(f"{_ml:.1f}%" if _ml is not None else "—", _mlc)
                    + _cell_ft(_fmt_val(_ebitda))
                    + _cell_ft(_fmt_val(_luc) + _yoy_span(_yoy(_rows_ft, i, 'lucro')))
                    + _cell_ft(_fmt_val(_cfo))
                    + _cell_ft(_fmt_val(_ndiv), _ndc)
                    + '</tr>'
                )
            section_title("📑 demonstrações trimestrais")
            st.markdown(
                f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
                f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                f'<thead><tr>{_hdr_ft}</tr></thead><tbody>{_body_ft}</tbody></table></div>',
                unsafe_allow_html=True,
            )
            _fonte_ft = str(_rows_ft[0].get('_fonte') or 'yfinance').lower()
            _basis_ft = ("valores anualizados por período (fonte cvm — itr acumulado)"
                         if _fonte_ft == 'cvm' else "valores trimestrais (fonte yfinance)")
            st.caption(
                f"{_basis_ft}. yoy = variação vs mesmo período 1 ano antes. "
                "mrg bruta/líq = % da receita. dív. líq. = dívida total − caixa."
            )

            # ── mini-gráficos de tendência (cronológico) ───────────────────
            st.markdown("<br>", unsafe_allow_html=True)
            _chron = list(reversed(_rows_ft))
            _x_ft = [str(r.get('periodo', ''))[:7] for r in _chron]
            _cc_ft = _chart_cores()
            _mb_s = [(_gt(r, 'gross') / _gt(r, 'receita') * 100) if (_gt(r, 'gross') is not None and _gt(r, 'receita')) else None for r in _chron]
            _ml_s = [(_gt(r, 'lucro') / _gt(r, 'receita') * 100) if (_gt(r, 'lucro') is not None and _gt(r, 'receita')) else None for r in _chron]
            _cfo_s = [_gt(r, 'cfo') for r in _chron]
            _luc_s = [_gt(r, 'lucro') for r in _chron]
            _rec_s = [_gt(r, 'receita') for r in _chron]
            _nd_s = [(_gt(r, 'divida_total') - (_gt(r, 'cash') or 0)) if _gt(r, 'divida_total') is not None else None for r in _chron]

            def _mini_ft(series_list):
                # Sem título dentro do gráfico (evita sobreposição com a legenda);
                # o título/explicação vai na caption abaixo de cada gráfico.
                fig = go.Figure()
                for nome, ys, cor in series_list:
                    fig.add_trace(go.Scatter(
                        x=_x_ft, y=ys, name=nome, mode="lines+markers",
                        line=dict(color=cor, width=2), marker=dict(size=4),
                    ))
                _lay = base_layout(height=210)
                _lay.update(
                    xaxis=dict(showgrid=False, tickangle=-30, tickfont=dict(size=8, color=_cc_ft["muted"])),
                    yaxis=dict(showgrid=True, gridcolor=_cc_ft["border"], tickfont=dict(size=9, color=_cc_ft["muted"])),
                    margin=dict(l=48, r=10, t=24, b=42), showlegend=True,
                    legend=dict(font=dict(size=9), orientation="h", yanchor="bottom", y=1.02, x=0),
                )
                fig.update_layout(**_lay)
                return fig

            _fc1, _fc2 = st.columns(2)
            with _fc1:
                st.plotly_chart(_mini_ft([("bruta", _mb_s, _cc_ft["info"]), ("líquida", _ml_s, _cc_ft["bull"])]),
                                use_container_width=True, config={'responsive': True})
                st.caption(
                    "**margens (%)** — margem bruta (receita − custos diretos) e margem líquida "
                    "(lucro final ÷ receita). estáveis ou em expansão indicam poder de precificação "
                    "e eficiência; queda sustentada sinaliza pressão de custos ou concorrência."
                )
                st.plotly_chart(_mini_ft([("dív. líq.", _nd_s, _cc_ft["bear"])]),
                                use_container_width=True, config={'responsive': True})
                st.caption(
                    "**dívida líquida** — dívida total − caixa. tendência de queda = desalavancagem "
                    "(favorável com juros altos, reduz risco financeiro); alta rápida exige atenção "
                    "ao custo da dívida e à cobertura de juros."
                )
            with _fc2:
                st.plotly_chart(_mini_ft([("cfo", _cfo_s, _cc_ft["accent"]), ("lucro", _luc_s, _cc_ft["bull"])]),
                                use_container_width=True, config={'responsive': True})
                st.caption(
                    "**cfo vs lucro (qualidade do lucro)** — fluxo de caixa operacional vs lucro líquido. "
                    "cfo acompanhando ou acima do lucro = lucro de alta qualidade (vira caixa de verdade); "
                    "lucro muito acima do cfo sugere resultado contábil sem geração de caixa."
                )
                st.plotly_chart(_mini_ft([("receita", _rec_s, _cc_ft["info"])]),
                                use_container_width=True, config={'responsive': True})
                st.caption(
                    "**receita** — a linha de topo por período. crescimento consistente sustenta a tese; "
                    "queda é o primeiro sinal de deterioração do negócio. compare com a variação yoy da tabela acima."
                )
        else:
            # Fallback: sem histórico no cache → gráfico receita vs lucro via yfinance
            section_title("📊 demonstrações financeiras (dre)")
            _earn_tipo = chart_type_toggle(key=f"earn_{t_base}", default="barras")
            st.subheader("receita vs lucro (últimos períodos)")
            try:
                fin = acao_obj.quarterly_financials
                if fin is None or (isinstance(fin, pd.DataFrame) and fin.empty): fin = acao_obj.financials
                if fin is not None and not fin.empty:
                    l_rev = ['Total Revenue', 'Total Operating Revenue', 'Operating Revenue']
                    l_net = ['Net Income', 'Net Income Common Stockholders', 'Net Income From Continuing Operations']
                    row_rev = fin.index[fin.index.isin(l_rev)].tolist()
                    row_net = fin.index[fin.index.isin(l_net)].tolist()
                    if row_rev and row_net:
                        df_earn = pd.DataFrame({'Receita': fin.loc[row_rev[0]], 'Lucro Líquido': fin.loc[row_net[0]]}).sort_index()
                        df_earn.index = df_earn.index.astype(str)
                        _cc = _chart_cores()
                        fig_earn = go.Figure()
                        if _earn_tipo == "barras":
                            fig_earn.add_trace(go.Bar(x=df_earn.index, y=df_earn['Receita'],
                                name="receita", marker_color=_cc["info"]))
                            fig_earn.add_trace(go.Bar(x=df_earn.index, y=df_earn['Lucro Líquido'],
                                name="lucro", marker_color=_cc["bull"]))
                            fig_earn.update_layout(**base_layout(height=400), barmode='group')
                        else:
                            fig_earn.add_trace(go.Scatter(x=df_earn.index, y=df_earn['Receita'],
                                name="receita", mode="lines+markers",
                                line=dict(color=_cc["info"], width=2)))
                            fig_earn.add_trace(go.Scatter(x=df_earn.index, y=df_earn['Lucro Líquido'],
                                name="lucro", mode="lines+markers",
                                line=dict(color=_cc["bull"], width=2)))
                            fig_earn.update_layout(**base_layout(height=400))
                        st.plotly_chart(fig_earn, use_container_width=True, config={'responsive': True})
                        st.caption("receita e lucro líquido dos últimos períodos. o ideal é receita crescente com o lucro acompanhando (margem preservada).")
            except Exception as e:
                logging.getLogger(__name__).warning(f"[research] tab earnings: {e}")
                st.error(f"erro ao carregar demonstrações: {e}")

if _secao_r == "🧠 análise & ia":
    section_title("🧠 análise ia — deepseek v4 pro")

    # ── Tenta cache do Supabase (compartilhado entre sessões) ────────────
    _cache_ia = st.session_state.get(f"ia_cache_{t_base}")
    if not _cache_ia:
        try:
            from database.db import get_ai_analysis as _get_ai
            _score_atual_ia = health_result.get('score') if isinstance(health_result, dict) else None
            _db_cache = _get_ai(
                tipo="research",
                ticker=t_base,
                user_id=None,                       # research é global
                modo=None,
                health_score_atual=_score_atual_ia,
                health_threshold=10,
            )
            if _db_cache:
                import datetime as _dtc
                try:
                    _dtt = _dtc.datetime.fromisoformat(str(_db_cache['created_at']).replace('Z','+00:00'))
                    _ts_fmt = _dtt.strftime('%d/%m/%Y %H:%M')
                except Exception:
                    _ts_fmt = str(_db_cache['created_at'])[:16]
                _cache_ia = {
                    'texto':     _db_cache['conteudo'],
                    'timestamp': _ts_fmt,
                    'score':     _db_cache.get('health_score_snapshot') or '—',
                    'macro':     'cache supabase',
                    'fonte':     'db',
                }
                st.session_state[f"ia_cache_{t_base}"] = _cache_ia
        except Exception as _e_cache_ia:
            logging.getLogger(__name__).warning(f"[research] cache ai lookup: {_e_cache_ia}")

    if _cache_ia:
        _fonte_tag = (
            ' <span style="color:var(--accent);">⚡ cache</span>'
            if _cache_ia.get('fonte') == 'db' else ''
        )
        st.markdown(
            f'<div style="background:var(--bg-surface); border:1px solid var(--border-subtle); '
            f'border-left:3px solid var(--accent); border-radius:6px; '
            f'padding:12px 16px; margin-bottom:16px;">'

            f'<div style="font-family:var(--font-ui,sans-serif); font-size:0.65rem; '
            f'color:var(--text-muted); margin-bottom:8px;">'
            f'📋 análise salva em {_cache_ia["timestamp"]} '
            f'| health score na época: {_cache_ia["score"]}/100 '
            f'| regime: {_cache_ia["macro"]}{_fonte_tag}'
            f'</div>'

            f'<div style="font-family:var(--font-data,monospace); font-size:0.82rem; '
            f'color:var(--text-primary); line-height:1.8; white-space:pre-wrap;">'
            f'{_cache_ia["texto"]}'
            f'</div>'

            f'</div>',
            unsafe_allow_html=True,
        )
        st.caption("análise instantânea via cache. clique em 'analisar' para forçar nova geração.")
    else:
        st.caption("nenhuma análise gerada ainda para este ativo.")

    _col_ia1, _col_ia2, _col_ia3 = st.columns([3, 1, 1], gap="small")
    with _col_ia1:
        st.markdown(
            '<div style="font-family:var(--font-ui,sans-serif); font-size:0.72rem; color:var(--text-muted); line-height:1.5;">'
            'deepseek v4 pro — análise com base em fundamentos, health score e macro. '
            'não é recomendação.</div>',
            unsafe_allow_html=True,
        )
    with _col_ia2:
        usar_thinking = st.checkbox(
            "modo reasoning",
            value=False,
            key="ia_thinking",
            help="ativa raciocínio profundo — mais lento e caro, use para decisões importantes",
        )
    with _col_ia3:
        btn_analise_ia = st.button(
            "🧠 analisar",
            type="primary",
            use_container_width=True,
            key="btn_analise_ia",
        )

    if btn_analise_ia:
        macro_ctx = st.session_state.get("macro_context", {
            "selic": 10.75, "vix": 15.0, "ipca": 4.5, "label": "neutro"
        })

        preco_ia = float(df_hist['Close'].iloc[-1]) if not df_hist.empty else 0.0
        var_ia   = 0.0
        if len(df_hist) >= 2:
            _p_hoje = float(df_hist['Close'].iloc[-1])
            _p_ant  = float(df_hist['Close'].iloc[-2])
            if _p_ant > 0:
                var_ia = (_p_hoje - _p_ant) / _p_ant * 100

        _impacto_setor_call = st.session_state.get("impacto_setor_ativo")

        # ── Calcula indicadores técnicos e performance a partir de df_hist ────
        _tec_data = {}
        try:
            if not df_hist.empty and len(df_hist) >= 20:
                _close = df_hist['Close']
                from utils.indicators import rsi_last as _rsi_last
                _tec_data['rsi'] = _rsi_last(_close, 14, default=None)

                _hi52 = float(_close.tail(252).max()) if len(_close) >= 50 else float(_close.max())
                _tec_data['dist_topo_52w'] = ((_close.iloc[-1] / _hi52) - 1) * 100 if _hi52 > 0 else None

                if len(_close) >= 50:
                    _tec_data['acima_mm50'] = bool(_close.iloc[-1] > _close.tail(50).mean())
                if len(_close) >= 200:
                    _tec_data['acima_mm200'] = bool(_close.iloc[-1] > _close.tail(200).mean())

                def _ret_periodo(dias):
                    if len(_close) <= dias:
                        return None
                    p0 = float(_close.iloc[-dias-1])
                    p1 = float(_close.iloc[-1])
                    return ((p1 / p0) - 1) * 100 if p0 > 0 else None

                _tec_data['ret_1m'] = _ret_periodo(21)
                _tec_data['ret_3m'] = _ret_periodo(63)
                _tec_data['ret_6m'] = _ret_periodo(126)
                _tec_data['ret_1y'] = _ret_periodo(252)

                # Vol anualizada (últimos 252 dias)
                _rets = _close.pct_change().dropna().tail(252)
                if len(_rets) > 20:
                    _tec_data['vol_anual'] = float(_rets.std() * (252 ** 0.5) * 100)
        except Exception:
            pass

        # ── Monta peer data a partir de df_comp (peers já carregados) ─────────
        _peer_payload = None
        try:
            if 'df_comp' in dir() and not df_comp.empty:
                _peer_payload = df_comp.head(6).to_dict(orient='records')
        except Exception:
            _peer_payload = None

        from utils.ai_prompts import build_research_prompt
        _prompt_ia = build_research_prompt(
            ticker        = t_base,
            nome          = cache_d.get("nome", nome_exibicao),
            setor         = setor,
            mercado       = ("brasil (b3)" if t_base.endswith(".SA") else "eua"),
            fundamentos   = cache_d,
            health_result = health_result,
            macro_context = macro_ctx,
            preco_atual   = preco_ia,
            var_1d        = var_ia,
            multiplos_historicos = _medios,
            impacto_setor = _impacto_setor_call,
            peer_data     = _peer_payload,
            tecnico       = _tec_data,
            dividendos    = None,
        )

        _resposta_ia = chamar_ia(
            prompt_usuario = _prompt_ia,
            system         = SYSTEM_ANALISTA,
            max_tokens     = 1800,
            temperatura    = 0.3,
            stream         = True,
            thinking       = usar_thinking,
            user_settings  = _user_settings,
        )

        if _resposta_ia:
            import datetime as _dt
            st.session_state[f"ia_cache_{t_base}"] = {
                'texto':     _resposta_ia,
                'timestamp': _dt.datetime.now().strftime('%d/%m/%Y %H:%M'),
                'score':     health_result.get('score', 50),
                'macro':     macro_ctx.get('label', '—'),
            }
            # ── Persiste no Supabase (compartilhado, TTL 7 dias) ─────────
            try:
                from database.db import save_ai_analysis, _hash_contexto
                _hash_ctx = _hash_contexto(
                    t_base, cache_d.get('p/l'), cache_d.get('roe%'),
                    cache_d.get('dy%'), cache_d.get('ev/ebitda'),
                    health_result.get('score'),
                )
                save_ai_analysis(
                    tipo="research",
                    ticker=t_base,
                    user_id=None,                    # global
                    conteudo=_resposta_ia,
                    modelo="auto",
                    contexto_hash=_hash_ctx,
                    health_score_snapshot=int(health_result.get('score', 50)),
                    ttl_horas=168,                   # 7 dias
                )
            except Exception as _e_save_ia:
                logging.getLogger(__name__).warning(f"[research] save ai cache: {_e_save_ia}")

        st.session_state[f"ia_analise_{t_base}"] = True

    elif st.session_state.get(f"ia_analise_{t_base}"):
        st.caption("análise já gerada nesta sessão. clique novamente para atualizar.")

    st.markdown("---")
    section_title("📄 exportar tese em pdf")

    _col_pdf1, _col_pdf2 = st.columns([3, 1])
    with _col_pdf1:
        st.markdown(
            '<div style="font-family:var(--font-ui,sans-serif); font-size:0.72rem; color:var(--text-muted);">'
            'gera um relatório profissional com fundamentos, análise ia e '
            'health score em formato pdf. o deepseek redige a tese completa '
            'antes da renderização — pode levar alguns segundos.</div>',
            unsafe_allow_html=True,
        )
    with _col_pdf2:
        btn_gerar_pdf = st.button(
            "📄 gerar pdf",
            type             = "secondary",
            use_container_width = True,
            key              = "btn_gerar_pdf",
        )

    if btn_gerar_pdf:
        _fund_pdf  = cache_d
        _alertas   = health_result.get("alertas", [])
        _breakdown = health_result.get("breakdown", {})
        _macro_ctx = st.session_state.get("macro_context", {
            "selic": 10.75, "vix": 15.0, "ipca": 4.5, "label": "neutro"
        })
        _preco_pdf = float(df_hist['Close'].iloc[-1]) if not df_hist.empty else 0.0

        with st.spinner("deepseek v4 pro redigindo tese..."):
            _prompt_pdf = (
                f"ativo: {t_base.upper()}\n"
                f"nome: {_fund_pdf.get('nome', nome_exibicao)}\n"
                f"setor: {setor}\n"
                f"tipo: {'fii' if '11.SA' in t_base else 'acao br' if '.SA' in t_base else 'acao us'}\n\n"
                f"fundamentos:\n"
                f"p/l: {_fund_pdf.get('p/l', 'n/d')}\n"
                f"p/vp: {_fund_pdf.get('p/vp', 'n/d')}\n"
                f"roe: {_fund_pdf.get('roe%', 'n/d')}%\n"
                f"dy: {_fund_pdf.get('dy%', 'n/d')}%\n"
                f"margem: {_fund_pdf.get('margem%', 'n/d')}%\n\n"
                f"health score: {health_result.get('score', 50)}/100\n"
                f"status: {health_result.get('status', 'n/d')}\n\n"
                f"alertas:\n"
                + "\n".join([f"- {a}" for a in _alertas[:6]])
                + f"\n\ncontexto macro:\n"
                f"selic: {_macro_ctx.get('selic', 10.75):.2f}%\n"
                f"vix: {_macro_ctx.get('vix', 15.0):.1f}\n"
                f"ambiente: {_macro_ctx.get('label', 'neutro')}\n\n"
                f"cotacao atual: r$ {_preco_pdf:,.2f}\n\n"
                "redija uma tese de investimento completa com: "
                "1. contexto do negocio, "
                "2. drivers de valor, "
                "3. riscos principais, "
                "4. valuation e veredicto. "
                "texto direto, sem asteriscos, letra minuscula."
            )
            _analise_pdf = chamar_ia(
                prompt_usuario = _prompt_pdf,
                system         = SYSTEM_TESE,
                max_tokens     = 1200,
                temperatura    = 0.3,
                stream         = False,
                thinking       = False,
                user_settings  = _user_settings,
            )

        with st.spinner("montando pdf..."):
            try:
                from utils.pdf_generator import gerar_tese_pdf
                _pdf_bytes = gerar_tese_pdf(
                    ticker        = t_base,
                    nome          = _fund_pdf.get("nome", nome_exibicao),
                    setor         = setor,
                    health_score  = health_result.get("score", 50),
                    preco_atual   = _preco_pdf,
                    fundamentos   = _fund_pdf,
                    analise_ia    = _analise_pdf or "análise indisponível.",
                    alertas       = _alertas,
                    breakdown     = _breakdown,
                    macro_context = _macro_ctx,
                )
                _nome_arquivo = (
                    f"tese_{t_base.replace('.SA', '').lower()}_"
                    f"{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
                )
                st.download_button(
                    label               = "⬇️ baixar tese em pdf",
                    data                = _pdf_bytes,
                    file_name           = _nome_arquivo,
                    mime                = "application/pdf",
                    type                = "primary",
                    use_container_width = True,
                    key                 = "btn_download_pdf",
                )
                st.success(f"✅ tese gerada: {_nome_arquivo}")
            except Exception as _e_pdf:
                st.error(f"erro ao gerar pdf: {_e_pdf}")

    st.markdown("---")
    section_title("📋 tese de investimento — deepseek v4 pro")

    if st.button(
        "📝 gerar tese de longo prazo",
        use_container_width=True,
        type="secondary",
        key="btn_tese_footer"
    ):
        try:
            from utils.health_engine import safe_int as _si
        except ImportError:
            def _si(v, d=0):
                try: return int(float(v)) if v is not None else d
                except Exception: return d
        val_pl   = _si(cache_d.get('p/l'))
        val_pvp  = _si(cache_d.get('p/vp'))
        val_roe  = _si(cache_d.get('roe%'))
        val_dy   = _si(cache_d.get('dy%'))
        val_divida = _si(cache_d.get('divida_liquida'))
        val_ativo  = _si(cache_d.get('ativos'))
        ltv_f = (val_divida / val_ativo * 100) if val_ativo and val_ativo > 0 else 0

        _prompt_tese = (
            f"ativo: {ticker.upper()}\n"
            f"setor: {setor}\n"
            f"tipo: {'fii' if is_fii else 'acao br' if ticker.endswith('.SA') else 'acao us'}\n\n"
            f"fundamentos:\n"
            f"p/l: {f'{val_pl:.2f}' if val_pl else 'n/d'}\n"
            f"p/vp: {f'{val_pvp:.2f}' if val_pvp else 'n/d'}\n"
            f"roe: {f'{val_roe:.1f}%' if val_roe else 'n/d'}\n"
            f"dividend yield: {f'{val_dy:.1f}%' if val_dy else 'n/d'}\n"
            f"alavancagem (dívida/ativos): {ltv_f:.1f}%\n"
            f"health score: {health_result.get('score', 50)}/100\n\n"
            "escreva uma tese de investimento de longo prazo em 4 parágrafos curtos. "
            "avalie se a alavancagem é adequada para o setor. "
            "conclua com uma visão de risco/retorno. letra minúscula."
        )
        with st.spinner("deepseek elaborando tese..."):
            chamar_ia(
                prompt_usuario = _prompt_tese,
                system         = SYSTEM_TESE,
                max_tokens     = 1000,
                temperatura    = 0.3,
                stream         = True,
                user_settings  = _user_settings,
            )

    # ── FUNDAMENTOS ──────────────────────────────────────────────────────────
    section_title("💎 fundamentos & indicadores")
    # Busca dados complementares ausentes no cache/info_dict
    _beta_tab = None
    _de_tab = None
    _descr_tab = cache_d.get('descricao') or cache_d.get('description')
    try:
        from utils.fmp_client import get_profile
        _profile_fmp = get_profile(t_base)
        if _profile_fmp:
            _beta_tab = _profile_fmp.get('beta')
            _descr_tab = _descr_tab or _profile_fmp.get('descricao', '')
    except Exception:
        pass
    if _beta_tab is None and df_hist is not None and len(df_hist) >= 60:
        try:
            _bench_t = "^BVSP" if t_base.endswith('.SA') else "^GSPC"
            from utils.price_history import obter_ohlcv_ativo
            _h_bench = obter_ohlcv_ativo(_bench_t, periodo="1y")
            if not _h_bench.empty:
                _r_a = df_hist['Close'].pct_change().dropna()
                _r_b = _h_bench['Close'].pct_change().dropna()
                _df_b = pd.concat([_r_a, _r_b], axis=1).dropna()
                if len(_df_b) >= 30:
                    from utils.indicators import beta as _beta_fn
                    _b = _beta_fn(_r_a, _r_b)
                    _beta_tab = round(_b, 2) if _b is not None else None
        except Exception:
            pass
    if _de_tab is None:
        try:
            _de_raw = yf_info(t_base).get('debtToEquity')
            if _de_raw is not None:
                _de_tab = round(float(_de_raw), 2)
        except Exception:
            pass

    c_f1, c_f2 = st.columns(2)
    with c_f1:
        st.markdown("**múltiplos e risco**")
        vol = fmt_pct(df_hist['Close'].pct_change().std() * np.sqrt(252) * 100) if len(df_hist) > 10 else "N/D"
        if is_fii:
            debt = safe_float(info_dict.get('totalDebt', 0))
            assets_t = safe_float(info_dict.get('totalAssets', 1))
            ltv = (debt / assets_t * 100) if assets_t > 0 else 0
            f_d = {"métrica": ["P/VP", "Yield (12m)", "Volatilidade Anual", "Alavancagem (Dívida/Ativos)", "Setor/Segmento"], 
                   "valor": [f"{pvp:.2f}" if pvp is not None else "N/D", fmt_pct(dy), vol, f"{ltv:.1f}%" if ltv > 0 else "baixa/nula", setor]}
        else:
            ev_e = safe_float(cache_d.get('ev/ebitda')) or safe_float(info_dict.get('enterpriseToEbitda'))
            pvp_val = safe_float(cache_d.get('p/vp')) or safe_float(info_dict.get('priceToBook'))
            beta_val = _beta_tab or safe_float(info_dict.get('beta'))
            debt_val = _de_tab or safe_float(info_dict.get('debtToEquity'))
            
            f_d = {
                "métrica": ["EV/EBITDA", "P/VP", "Volatilidade Anual", "Beta", "Dívida/Patrimônio"], 
                "valor": [
                    f"{ev_e:.2f}" if ev_e is not None else "N/D", 
                    f"{pvp_val:.2f}" if pvp_val is not None else "N/D", 
                    vol, 
                    f"{beta_val:,.2f}" if beta_val is not None else "N/D", 
                    f"{debt_val:,.1f}%" if debt_val is not None else "N/D"
                ]
            }
        st.table(pd.DataFrame(f_d))

        # ── HISTÓRICO DE PROVENTOS (FII mensal 24m / ação anual 5a) ───────
        st.markdown("<br>", unsafe_allow_html=True)
        section_title(f"💰 histórico de proventos (últimos {'24 meses' if is_fii else '5 anos'})")
        try:
            _render_historico_proventos(
                acao_obj.dividends if acao_obj is not None else None,
                'fii' if is_fii else 'acao',
                ticker, moeda,
            )
        except Exception as _e_div:
            st.warning(f"não foi possível carregar o histórico de proventos: {_e_div}")

    with c_f2:
        st.markdown("**descrição**")
        _descricao_texto = _descr_tab or info_dict.get('longBusinessSummary', '')
        st.markdown(
            _descricao_texto[:800] + "..."
            if _descricao_texto and len(str(_descricao_texto)) > 10
            else '_descrição não disponível para este ativo._'
        )

    # ── EVOLUÇÃO HISTÓRICA DE FUNDAMENTOS (FMP) ──────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("📈 evolução de fundamentos (histórico — fmp / yfinance)")
    st.caption(
        "trajetória de 10 anos dos principais indicadores. p/l e ev/ebitda mostram se o "
        "valuation está esticado ou comprimido vs. a própria história; roe e margem líquida "
        "revelam se a rentabilidade é consistente ou volátil ao longo do ciclo."
    )

    with st.spinner("carregando histórico de fundamentos..."):
        _hist_fund = get_multiplos_historicos(t_base, anos=10)

    if _hist_fund:
        _df_hf = (
            pd.DataFrame(_hist_fund)
              .dropna(subset=["data"])
              .sort_values("data")
              .reset_index(drop=True)
        )

        _cc_hf = _chart_cores()

        _metricas_evo = [
            ("P/L — price to earnings",      "pe",        _cc_hf["accent"]),
            ("ROE % — retorno s/ patrimônio", "roe",       _cc_hf["bull"]),
            ("Margem Líquida %",              "margem",    _cc_hf["info"]),
            ("EV/EBITDA",                     "ev_ebitda", _cc_hf["amber"]),
        ]

        _evcol1, _evcol2 = st.columns(2)
        _evcol3, _evcol4 = st.columns(2)
        _ev_cols = [_evcol1, _evcol2, _evcol3, _evcol4]

        for _evcol, (_evlbl, _evcampo, _evcor) in zip(_ev_cols, _metricas_evo):
            with _evcol:
                _df_ev = _df_hf[["data", _evcampo]].dropna()
                if _df_ev.empty:
                    st.markdown(
                        f'<div style="font-size:0.75rem;color:var(--text-muted);'
                        f'padding:8px 0;">{_evlbl} — sem dados</div>',
                        unsafe_allow_html=True,
                    )
                    continue

                _fig_ev = go.Figure()
                # Converte hex → rgba para fillcolor (Plotly não aceita hex de 8 dígitos)
                try:
                    _h = _evcor.lstrip("#")
                    _r, _g, _b = int(_h[0:2],16), int(_h[2:4],16), int(_h[4:6],16)
                    _fill_ev = f"rgba({_r},{_g},{_b},0.09)"
                except Exception:
                    _fill_ev = "rgba(100,100,200,0.09)"
                _fig_ev.add_trace(go.Scatter(
                    x=_df_ev["data"].tolist(),
                    y=_df_ev[_evcampo].tolist(),
                    mode="lines+markers",
                    line=dict(color=_evcor, width=2),
                    marker=dict(size=4, color=_evcor),
                    fill="tozeroy",
                    fillcolor=_fill_ev,
                    hovertemplate="%{x}<br><b>%{y:.2f}</b><extra></extra>",
                    name=_evlbl,
                ))
                _lay_ev = base_layout(height=220, title=_evlbl)
                _lay_ev.update(
                    xaxis=dict(
                        showgrid=False,
                        tickangle=-30,
                        tickfont=dict(size=8, color=_cc_hf["muted"]),
                        linecolor=_cc_hf["border"],
                    ),
                    yaxis=dict(
                        showgrid=True,
                        gridcolor=_cc_hf["border"],
                        tickfont=dict(size=9, color=_cc_hf["muted"]),
                        zeroline=False,
                    ),
                    margin=dict(l=44, r=8, t=36, b=44),
                )
                _fig_ev.update_layout(**_lay_ev)
                st.plotly_chart(_fig_ev, use_container_width=True, config={"responsive": True})
    else:
        st.markdown(
            '<div style="font-size:0.75rem;color:var(--text-muted);padding:12px 0;">'
            'histórico de fundamentos não disponível (FMP sem dados e yfinance sem demonstrações para este ativo).'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── DCF REVERSO ──────────────────────────────────────────────────────────
    section_title("🧮 dcf reverso & valuation implícito")
    if is_fii:
        section_title("🏢 modelo de valuation — p/vp justo (fii)")

        st.markdown(
            '<div style="font-family:var(--font-ui,sans-serif); font-size:0.75rem; '
            'color:var(--text-muted); margin-bottom:16px; line-height:1.7;">'
            'para fiis o modelo correto não é dcf, mas sim a comparação entre '
            '<b>cap rate implícito</b> (yield real do fii) e o '
            '<b>custo de oportunidade</b> (ntn-b + spread de risco do segmento). '
            'o p/vp justo é derivado dessa relação: quando o yield real supera '
            'o custo de oportunidade, o fii merece negociar acima de 1.0x p/vp.'
            '</div>',
            unsafe_allow_html=True,
        )

        from utils.health_engine import _buscar_yield_ntnb, _detectar_segmento_fii

        _ntnb_dcf    = _buscar_yield_ntnb()
        _seg_dcf     = _detectar_segmento_fii(t_base, cache_d)
        _dy_dcf      = safe_float(cache_d.get('dy%')) or 0.0
        _pvp_dcf     = safe_float(cache_d.get('p/vp')) or 1.0
        _ipca_dcf    = st.session_state.get("macro_context", {}).get("ipca", 4.5)
        _dy_real_dcf = ((1 + _dy_dcf/100) / (1 + _ipca_dcf/100) - 1) * 100

        section_title("⚙️ parâmetros do modelo")

        _spreads_default = {
            'papel':       1.5,
            'logistica':   2.5,
            'lajes':       3.0,
            'shopping':    3.0,
            'fof':         2.0,
            'residencial': 2.5,
            'hibrido':     2.5,
            'desconhecido':2.5,
        }
        _spread_default = _spreads_default.get(_seg_dcf, 2.5)

        _fv1, _fv2, _fv3, _fv4 = st.columns(4)

        with _fv1:
            _ntnb_input = st.number_input(
                "yield ntn-b real (% a.a.)",
                value=float(max(2.0, min(12.0, _ntnb_dcf or 6.5))),
                min_value=2.0,
                max_value=12.0,
                step=0.1,
                format="%.2f",
            )
        with _fv2:
            _spread_input = st.slider(
                "spread de risco do segmento (pp)",
                min_value=0.5,
                max_value=6.0,
                value=float(_spread_default),
                step=0.25,
                format="%.2f",
            )
        with _fv3:
            _dy_input = st.number_input(
                "dividend yield atual (%)",
                value=float(_dy_dcf) if _dy_dcf > 0 else 8.0,
                min_value=0.1,
                max_value=30.0,
                step=0.1,
                format="%.2f",
            )
        with _fv4:
            _ipca_input = st.number_input(
                "ipca esperado (%)",
                value=float(max(1.0, min(12.0, _ipca_dcf or 4.5))),
                min_value=1.0,
                max_value=12.0,
                step=0.1,
                format="%.1f",
            )

        st.markdown("---")

        _custo_op     = _ntnb_input + _spread_input
        _dy_real_calc = ((1 + _dy_input/100) / (1 + _ipca_input/100) - 1) * 100
        _pvp_justo    = _dy_real_calc / _custo_op if _custo_op > 0 else 1.0
        _pvp_justo    = round(_pvp_justo, 3)
        _pvp_atual    = _pvp_dcf
        _upside_pvp   = (_pvp_justo / _pvp_atual - 1) * 100 if _pvp_atual > 0 else 0
        _spread_efetivo = _dy_real_calc - _custo_op

        _rc1, _rc2, _rc3, _rc4 = st.columns(4)

        _cor_pvpj = "var(--bull)" if _pvp_justo > _pvp_atual else "var(--bear)"
        _cor_spread_ef = "var(--bull)" if _spread_efetivo >= 0 else "var(--bear)"
        _cor_upside = "var(--bull)" if _upside_pvp > 0 else "var(--bear)"

        with _rc1:
            metric_card(
                "p/vp justo calculado",
                f"{_pvp_justo:.3f}×",
                f"p/vp mercado: {_pvp_atual:.3f}×",
                "bull" if _pvp_justo > _pvp_atual else "bear",
            )
        with _rc2:
            metric_card(
                "upside / downside",
                f"{_upside_pvp:+.1f}%",
                "vs p/vp atual de mercado",
                "bull" if _upside_pvp > 0 else "bear",
            )
        with _rc3:
            metric_card(
                "spread efetivo",
                f"{_spread_efetivo:+.2f}pp",
                f"yield real {_dy_real_calc:.1f}% − custo {_custo_op:.1f}%",
                "bull" if _spread_efetivo >= 0 else "bear",
            )
        with _rc4:
            metric_card(
                "segmento detectado",
                _seg_dcf,
                f"spread padrão: {_spread_default:.1f}pp",
            )

        if _pvp_justo > _pvp_atual * 1.10:
            _interp = (
                f"fii potencialmente subavaliado: p/vp justo de {_pvp_justo:.3f}× "
                f"supera o preço de mercado de {_pvp_atual:.3f}× em "
                f"{_upside_pvp:.1f}%. o yield real compensa o custo de "
                f"oportunidade com folga de {_spread_efetivo:.2f}pp."
            )
            _tipo_interp = "bull"
        elif _pvp_justo > _pvp_atual:
            _interp = (
                f"fii levemente subavaliado: p/vp justo ({_pvp_justo:.3f}×) "
                f"acima do mercado ({_pvp_atual:.3f}×). spread efetivo de "
                f"{_spread_efetivo:.2f}pp — margem estreita, monitorar dividendos."
            )
            _tipo_interp = "amber"
        elif _pvp_justo > _pvp_atual * 0.90:
            _interp = (
                f"fii próximo do valor justo: p/vp calculado de {_pvp_justo:.3f}× "
                f"vs mercado {_pvp_atual:.3f}×. spread negativo de "
                f"{_spread_efetivo:.2f}pp — yield real insuficiente vs "
                f"ntn-b + spread de risco."
            )
            _tipo_interp = "amber"
        else:
            _interp = (
                f"fii potencialmente sobreavaliado: p/vp justo de {_pvp_justo:.3f}× "
                f"abaixo do mercado de {_pvp_atual:.3f}×. o yield real "
                f"({_dy_real_calc:.1f}%) não remunera adequadamente o risco "
                f"vs ntn-b ({_ntnb_input:.1f}%) + spread ({_spread_input:.1f}pp)."
            )
            _tipo_interp = "bear"

        status_card("interpretação do modelo", _interp, _tipo_interp)

        section_title("🗺️ sensibilidade — p/vp justo por yield real e spread")

        import numpy as np
        import plotly.graph_objects as go

        _dy_reais_range   = [round(x, 1) for x in list(np.arange(4.0, 14.1, 0.5))]
        _spreads_cenarios = [
            round(_spread_input - 1.0, 2),
            round(_spread_input, 2),
            round(_spread_input + 1.0, 2),
        ]
        _spreads_cenarios = [max(0.5, s) for s in _spreads_cenarios]

        _fig_fii_sens = go.Figure()

        for _i_sp, _sp in enumerate(_spreads_cenarios):
            _custo_c = _ntnb_input + _sp
            _pvps_c  = [
                round(dy_r / _custo_c, 3) if _custo_c > 0 else 1.0
                for dy_r in _dy_reais_range
            ]
            from utils.charts import CORES_SERIES
            _fig_fii_sens.add_trace(go.Scatter(
                x=_dy_reais_range,
                y=_pvps_c,
                name=f"spread {_sp:.1f}pp",
                line=dict(
                    color=CORES_SERIES[_i_sp % len(CORES_SERIES)],
                    width=1.8,
                ),
            ))

        _fig_fii_sens.add_scatter(
            x=[_dy_real_calc],
            y=[_pvp_justo],
            mode="markers",
            marker=dict(color=_chart_cores()["accent"], size=12, symbol="diamond"),
            name="posição atual",
        )

        _fig_fii_sens.add_hline(
            y=_pvp_atual,
            line_color=_chart_cores()["muted"],
            line_dash="dash",
            line_width=1,
            annotation_text=f"p/vp mercado ({_pvp_atual:.2f}×)",
            annotation_font_color=_chart_cores()["muted"],
            annotation_font_size=9,
        )
        _fig_fii_sens.add_hline(
            y=1.0,
            line_color=_chart_cores()["muted"],
            line_dash="dot",
            line_width=1,
        )

        _lay_fii = base_layout(
            height=380,
            title="p/vp justo por yield real e spread de risco (ntn-b fixo)",
        )
        _lay_fii.update(
            xaxis=dict(title="yield real do fii (% a.a.)", showgrid=True, gridcolor=_chart_cores()["border"]),
            yaxis=dict(title="p/vp justo calculado", showgrid=True, gridcolor=_chart_cores()["border"]),
        )
        _fig_fii_sens.update_layout(**_lay_fii)
        st.plotly_chart(_fig_fii_sens, use_container_width=True, config={'responsive': True})

        st.caption(
            f"ntn-b fixo em {_ntnb_input:.2f}% | ipca {_ipca_input:.1f}% | "
            f"segmento: {_seg_dcf} | diamante laranja = posição atual"
        )

        st.markdown("---")
        if st.button(
            "🧠 ia: interpretar valuation e gerar tese para este fii",
            type="primary",
            key="btn_ia_fii_dcf",
        ):
            _prompt_fii_val = (
                f"fii: {ticker.upper()} | segmento: {_seg_dcf}\n\n"
                f"modelo de valuation (p/vp justo):\n"
                f"yield nominal: {_dy_input:.2f}%\n"
                f"yield real: {_dy_real_calc:.2f}%\n"
                f"ntn-b benchmark: {_ntnb_input:.2f}% (ipca+)\n"
                f"spread de risco do segmento: {_spread_input:.2f}pp\n"
                f"custo de oportunidade total: {_custo_op:.2f}%\n"
                f"spread efetivo: {_spread_efetivo:+.2f}pp\n"
                f"p/vp justo calculado: {_pvp_justo:.3f}×\n"
                f"p/vp de mercado atual: {_pvp_atual:.3f}×\n"
                f"upside/downside implícito: {_upside_pvp:+.1f}%\n\n"
                f"health score: {health_result.get('score', 50)}/100\n"
                f"contexto macro: selic {st.session_state.get('macro_context',{}).get('selic',10.75):.2f}%"
                f" | ipca {_ipca_input:.1f}%\n\n"
                "em 4 tópicos curtos (letra minúscula):\n"
                "1. o yield real remunera adequadamente o risco vs título público?\n"
                "2. o p/vp atual está justo, barato ou caro para o segmento?\n"
                "3. cenário bull e bear para os proventos nos próximos 12 meses.\n"
                "4. recomendação: acumular / manter / reduzir — com justificativa."
            )
            chamar_ia(
                prompt_usuario = _prompt_fii_val,
                system         = SYSTEM_TESE,
                max_tokens     = 800,
                temperatura    = 0.3,
                stream         = True,
                user_settings  = _user_settings,
            )
    else:
        eps_base = safe_float(info_dict.get('trailingEps')) or safe_float(info_dict.get('forwardEps'))
        preco_base = safe_float(df_hist['Close'].iloc[-1]) if not df_hist.empty else None
        is_us = not ticker.endswith('.SA')
        
        section_title("⚙️ parâmetros do modelo")
        
        c_dcf1, c_dcf2, c_dcf3, c_dcf4 = st.columns(4)
        with c_dcf1:
            eps_input = st.number_input("eps (lucro/ação)", value=float(eps_base) if eps_base and eps_base > 0 else 5.0, min_value=-100.0, step=0.01, format="%.2f")
        with c_dcf2:
            preco_input = st.number_input("preço atual", value=float(preco_base) if preco_base else 100.0, min_value=0.01, step=0.01, format="%.2f")
        with c_dcf3:
            wacc_pct = st.slider("wacc (custo capital %)", min_value=4.0, max_value=20.0, value=9.0 if is_us else 12.0, step=0.5, format="%.1f%%")
        with c_dcf4:
            g_term_pct = st.slider("crescimento terminal %", min_value=1.0, max_value=5.0, value=3.0, step=0.5, format="%.1f%%")
            
        c_dcf5, c_dcf6 = st.columns(2)
        with c_dcf5:
            n_anos = st.slider("horizonte de projeção (anos)", min_value=5, max_value=15, value=10, step=1)
        with c_dcf6:
            margem_seg_pct = st.slider("margem de segurança (%)", min_value=0, max_value=40, value=15, step=5)
            
        wacc = wacc_pct / 100
        g_terminal = g_term_pct / 100
        
        st.markdown("---")
        
        g_implicito = calcular_crescimento_implicito(preco_input, eps_input, wacc, g_terminal, n_anos)
        
        section_title("📊 crescimento implícito no preço atual")
        
        if g_implicito is None:
            st.warning("não foi possível calcular. verifique se o eps é positivo e o wacc é maior que o crescimento terminal.")
        else:
            g_implicito_pct = g_implicito * 100
            preco_com_ms = preco_input * (1 - (margem_seg_pct / 100))
            
            c_res1, c_res2, c_res3, c_res4 = st.columns(4)
            with c_res1:
                metric_card("crescimento implícito (a.a.)", fmt_pct(g_implicito_pct), cor_delta="bull" if g_implicito_pct < 15 else "bear")
            with c_res2:
                metric_card("p/l implícito", f"{preco_input/eps_input:.1f}x" if eps_input > 0 else "n/d")
            with c_res3:
                metric_card("preço com margem segurança", f"{moeda.upper()} {preco_com_ms:.2f}")
            with c_res4:
                metric_card("horizonte analisado", f"{n_anos} anos")
                
            if g_implicito_pct < 8:
                interpretacao = "crescimento baixo precificado — assimetria favorável se a empresa crescer acima disso."
                cor_int = "bull"
            elif g_implicito_pct <= 20:
                interpretacao = "crescimento moderado a alto precificado — valuation justo se tese de crescimento se confirmar."
                cor_int = "amber"
            else:
                interpretacao = "crescimento muito alto precificado — risco elevado de decepção. exige execução perfeita."
                cor_int = "bear"
                
            status_card("interpretação do valuation", interpretacao, cor_int)
            
            section_title("🗺️ mapa de sensibilidade — preço justo estimado por cenário")
            
            cenarios_g = [-5, 0, 5, 8, 10, 12, 15, 20, 25]
            cenarios_wacc = [round(wacc_pct - 2, 1), wacc_pct, round(wacc_pct + 2, 1)]
            
            dados_sens = []
            for wacc_c in cenarios_wacc:
                linha = {}
                w_c_dec = wacc_c / 100
                for g_c in cenarios_g:
                    g_c_dec = g_c / 100
                    try:
                        if w_c_dec <= g_terminal:
                            linha[f"g={g_c}%"] = "—"
                        else:
                            vp_soma = sum(eps_input * (1 + g_c_dec)**t / (1 + w_c_dec)**t for t in range(1, n_anos + 1))
                            vp_term = (eps_input * (1 + g_c_dec)**n_anos * (1 + g_terminal)) / (w_c_dec - g_terminal) / ((1 + w_c_dec)**n_anos)
                            linha[f"g={g_c}%"] = round(vp_soma + vp_term, 2)
                    except Exception:
                        linha[f"g={g_c}%"] = "—"
                dados_sens.append(linha)
                
            df_sens = pd.DataFrame(dados_sens, index=[f"wacc {w}%" for w in cenarios_wacc])

            _mn_s = 'var(--font-mono,monospace)'
            _g_cols = [f"g={g}%" for g in cenarios_g]
            _hdrs_s = '<th style="padding:7px 10px;font-size:0.67rem;color:var(--text-muted);text-transform:uppercase;border-bottom:1px solid var(--border-subtle);">wacc \\ g</th>'
            _hdrs_s += "".join(
                f'<th style="padding:7px 10px;text-align:right;font-size:0.67rem;color:var(--text-muted);text-transform:uppercase;border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                for c in _g_cols
            )
            _rows_s = ""
            for idx_row, w_label in enumerate(df_sens.index):
                _is_main = (w_label == f"wacc {wacc_pct}%")
                _row_style = "background:rgba(99,179,237,0.08);" if _is_main else ""
                _cells_s = f'<td style="padding:7px 10px;font-family:{_mn_s};font-size:0.78rem;font-weight:{"700" if _is_main else "400"};color:var(--text-muted);white-space:nowrap;">{w_label}</td>'
                for gc in _g_cols:
                    _v = df_sens.loc[w_label, gc]
                    if _v == "—" or not isinstance(_v, (int, float)):
                        _cells_s += f'<td style="padding:7px 10px;text-align:right;color:var(--text-muted);font-size:0.8rem;">—</td>'
                    else:
                        _is_cheap = _v > preco_input
                        _bg = "background:rgba(46,204,113,0.15);" if _is_cheap else ""
                        _cv = "#2ecc71" if _is_cheap else "var(--text-primary)"
                        _cells_s += (f'<td style="padding:7px 10px;text-align:right;font-family:{_mn_s};font-size:0.8rem;color:{_cv};{_bg}">'
                                     f'{moeda.upper()} {_v:,.2f}</td>')
                _rows_s += f'<tr style="border-bottom:1px solid var(--border-subtle);{_row_style}">{_cells_s}</tr>'
            st.markdown(
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                f'<thead><tr>{_hdrs_s}</tr></thead><tbody>{_rows_s}</tbody></table></div>',
                unsafe_allow_html=True,
            )
            st.caption(f"valores em {moeda.upper()} | célula verde = subvalorizado vs preço atual de {preco_input} | linha destacada = wacc configurado acima.")
            
            fig = go.Figure()
            for i, wacc_c in enumerate(cenarios_wacc):
                y_vals = []
                for g_c in cenarios_g:
                    val = df_sens.loc[f"wacc {wacc_c}%", f"g={g_c}%"]
                    y_vals.append(val if val != "—" else None)
                    
                fig.add_trace(go.Scatter(x=cenarios_g, y=y_vals, name=f"wacc {wacc_c}%", line=dict(color=CORES_SERIES[i % len(CORES_SERIES)])))
                
            fig.add_hline(y=preco_input, line_color=_chart_cores()["accent"], line_dash="dash", annotation_text="preço atual")
            fig.update_layout(**base_layout(height=380, title="preço justo estimado por taxa de crescimento e wacc"))
            st.plotly_chart(fig, use_container_width=True, config={'responsive': True})
            st.caption("preço justo estimado para cada combinação de crescimento e wacc. onde a curva cruza o preço atual está o crescimento que o mercado já embute — acima disso o ativo está caro; abaixo, barato.")
            
            st.markdown("---")
            if st.button("🧠 ia: interpretar o valuation e gerar tese", type="primary"):
                _prompt_dcf = (
                    f"ativo: {ticker} | setor: {setor}\n\n"
                    f"modelo dcf reverso:\n"
                    f"eps: {eps_input:.2f} | wacc: {wacc_pct}% | g terminal: {g_term_pct}% | horizonte: {n_anos} anos\n\n"
                    f"resultado:\n"
                    f"crescimento implícito no preço: {g_implicito_pct:.1f}%\n"
                    f"preço atual: {moeda.upper()} {preco_input:.2f}\n\n"
                    "responda em 4 tópicos curtos, letra minúscula:\n"
                    "1. o crescimento implícito é realista para o setor?\n"
                    "2. comparação com pares do setor se souber.\n"
                    "3. cenário bull e bear para o preço em 3 anos.\n"
                    "4. recomendação (comprar / aguardar / evitar) com justificativa."
                )
                with st.spinner("deepseek analisando o valuation..."):
                    chamar_ia(
                        prompt_usuario = _prompt_dcf,
                        system         = SYSTEM_TESE,
                        max_tokens     = 800,
                        temperatura    = 0.3,
                        stream         = True,
                        user_settings  = _user_settings,
                    )

    # ── NOTÍCIAS & SENTIMENTO ────────────────────────────────────────────────
    section_title("📰 notícias & sentimento")
    st.subheader("sentimento via notícias")
    try:
        news = acao_obj.news
        if news:
            # yfinance recente aninha os campos em item['content']; versões antigas
            # os traziam no topo. Trata os dois formatos (igual a 3_Macro).
            _n_render = 0
            for item in news:
                if _n_render >= 5:
                    break
                dados_n  = item.get('content', item)
                titulo_n = dados_n.get('title', dados_n.get('headline', ''))
                if not titulo_n:
                    continue
                _pub = dados_n.get('provider', dados_n.get('publisher', 'agência'))
                if isinstance(_pub, dict):
                    _pub = _pub.get('displayName', 'agência')
                _uid = item.get('id') or item.get('uuid') or f"news_{_n_render}"
                with st.container():
                    cn1, cn2 = st.columns([4, 1])
                    cn1.markdown(f"**{titulo_n}**")
                    cn1.caption(str(_pub or 'agência').lower())
                    if cn2.button("ia: analisar", key=f"news_ia_{_uid}"):
                        with st.spinner("ia..."):
                            _res_news = chamar_ia(
                                prompt_usuario=(
                                    f"ativo: {ticker}\n\n"
                                    f"manchete: {titulo_n}\n\n"
                                    "em 1 frase curta com letra minúscula, diga se esta notícia é "
                                    "positiva, negativa ou neutra para o ativo e por quê."
                                ),
                                system      = SYSTEM_ANALISTA,
                                max_tokens  = 120,
                                temperatura = 0.2,
                                stream      = False,
                                user_settings  = _user_settings,
                            )
                            if _res_news:
                                st.info(_res_news)
                    st.markdown("---")
                _n_render += 1
            if _n_render == 0:
                st.info("sem notícias no formato esperado.")
        else:
            st.info("sem notícias disponíveis.")
    except Exception as _e_news:
        logging.getLogger(__name__).warning(f"[research] notícias: {_e_news}")
        st.info("sem notícias.")

if _secao_r == "🌍 overlay macro":
    st.subheader("estudo de correlação estrutural (10 anos)")
    ind_macro = st.selectbox("comparar com:", ["Taxa Selic (Brasil)", "IPCA (Inflação BR)", "Dólar Comercial (BRL=X)", "VIX (Volatilidade Global)"])
    inicio_macro = (datetime.datetime.now() - datetime.timedelta(days=365*10)).strftime('%Y-%m-%d')
    try:
        m_data = None
        if "Selic" in ind_macro: m_data, m_name = sgs.get({'selic': 432}, start=inicio_macro)['selic'], "selic %"
        elif "IPCA" in ind_macro: m_data, m_name = sgs.get({'ipca': 433}, start=inicio_macro)['ipca'], "ipca %"
        elif "Dólar" in ind_macro:
            m_data = yf.download("BRL=X", start=inicio_macro, progress=False)['Close']
            if isinstance(m_data, pd.DataFrame): m_data = m_data.iloc[:, 0]
            m_name = "usd/brl"
        elif "VIX" in ind_macro and "FRED_API_KEY" in st.secrets:
            m_data, m_name = Fred(api_key=st.secrets["FRED_API_KEY"]).get_series('VIXCLS', observation_start=inicio_macro), "vix index"
            
        if m_data is not None and not m_data.empty:
            m_data.index = pd.to_datetime(m_data.index).tz_localize(None)
            stk_p = df_hist['Close'].copy()
            stk_p.index = pd.to_datetime(stk_p.index).tz_localize(None)
            fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
            fig_macro.add_trace(go.Scatter(x=stk_p.index, y=stk_p, name=ticker.lower(), line=dict(color=_chart_cores()["accent"])), secondary_y=False)
            fig_macro.add_trace(go.Scatter(x=m_data.index, y=m_data, name=m_name, line=dict(color="#00B0FF", dash="dot")), secondary_y=True)
            fig_macro.update_layout(**base_layout(height=450, title=f"{ticker.lower()} vs {ind_macro.lower()}"))
            st.plotly_chart(fig_macro, use_container_width=True, config={'responsive': True})
            st.caption("sobrepõe o preço do ativo (eixo esq.) à série macro (eixo dir.). movimentos espelhados ou opostos revelam a sensibilidade do ativo àquele fator (juros, câmbio, inflação).")
    except: st.warning("Erro overlay.")

# Fim da página