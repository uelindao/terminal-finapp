import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import datetime
import time
import logging
from utils.formatters import traduzir_setor

# ── silenciar alertas vermelhos do yahoo finance no terminal ──
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from database.db import (
    listar_watchlist, get_health_scores, adicionar_ativo,
    listar_watchlists, criar_watchlist, get_watchlist_padrao,
    get_todos_fundamentos_cache, init_db
)
from utils.tickers import (
    SCREENER_B3, SCREENER_US, XSTOCKS_INDICES, FII_TODOS,
    BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, mapear_ticker_base
)
from utils.health_engine import calcular_health_score
from utils.components import (
    page_header, section_title, status_card, empty_state,
    inject_keyboard_shortcuts, metric_card, tooltip, label_com_tooltip,
    handle_ticker_nav, ticker_nav_url, topbar,
    portfolio_kpis, info_box, chip_filter_row, tabs_pill,
)
from utils.ai_client import chamar_ia, SYSTEM_ANALISTA
from utils.charts import base_layout, chart_type_toggle, barras_verticais, _cores as _chart_cores
from utils.macro_regime import classificar_regime

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


init_db()
CACHE_FUNDAMENTOS = get_todos_fundamentos_cache()

_user_top_disc = get_current_user() or {}
topbar(
    breadcrumb_itens=[("⚡ finterminal", "/"), ("discovery", None)],
    user_name=_user_top_disc.get('username', '') or _user_top_disc.get('nome', '') or 'usuário',
    sync_label="ao vivo",
)
page_header("🎯 discovery — descoberta", "encontre assimetrias de mercado através de filtros quantitativos e inteligência artificial.")

_n_cache_br = sum(1 for t in CACHE_FUNDAMENTOS if str(t).endswith('.SA'))
_n_cache_us = sum(1 for t in CACHE_FUNDAMENTOS if not str(t).endswith('.SA'))
st.caption(f"cache: {_n_cache_br} ativos BR | {_n_cache_us} ativos EUA")


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
# Momentum e Radar fundidos numa única aba (antes eram duas que se sobrepunham):
# momentum = força relativa técnica; radar = oportunidades por health×valuation×timing.
# LAZY RENDERING (P4-1): seletor persistente no lugar de st.tabs — renderiza só a
# seção ativa (screener/momentum/ia/setorial rodam scans pesados). Blocos
# `with tab_X:` viraram `if _secao_d == ...`. Sem dependência cruzada entre abas.
_SECOES_D = ["🔍 screener quantitativo", "🚀 momentum & radar",
             "🧠 ia: oportunidades do dia", "🗺️ rotação setorial"]
if hasattr(st, "segmented_control"):
    _secao_d = st.segmented_control(
        "seção", _SECOES_D, default=_SECOES_D[0],
        key="discovery_secao", label_visibility="collapsed",
    ) or st.session_state.get("discovery_secao") or _SECOES_D[0]
else:
    _secao_d = st.radio("seção", _SECOES_D, index=0, horizontal=True,
                        key="discovery_secao", label_visibility="collapsed")

# ==========================================
# tab 1 — momentum (força relativa)
# ==========================================
if _secao_d == "🚀 momentum & radar":
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
            info_box(
                tipo   = "amber",
                titulo = "selecione um universo",
                texto  = "marque ao menos um universo (B3 / FIIs / EUA) para rodar o screener.",
                icone  = "☝",
            )
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

        _ret_med = df_m['ret 1y (%)'].mean()
        acima_200 = (df_m['acima mm200'] == '✅').sum()
        portfolio_kpis([
            {
                "nome":        "melhor momentum",
                "ticker_chip": str(df_m.iloc[0]['ticker']).replace('.SA', ''),
                "valor":       f"{df_m.iloc[0]['score momentum']}/100",
                "sublabel":    "score do líder do ranking",
                "tone":        "bull",
                "icone":       "🚀",
            },
            {
                "nome":     "retorno médio 1y",
                "valor":    f"{_ret_med:+.1f}%",
                "sublabel": "performance agregada do top",
                "tone":     "bull" if _ret_med > 0 else "bear",
                "icone":    "📈" if _ret_med > 0 else "📉",
            },
            {
                "nome":     "acima da mm200",
                "valor":    f"{acima_200}/{len(df_m)}",
                "sublabel": "tendência de alta de longo prazo",
                "tone":     "bull" if acima_200 > len(df_m) // 2 else "amber",
                "icone":    "📊",
            },
        ])

        cols_mostrar = ['ticker', 'nome', 'setor', 'ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)', 'dist. topo 52w (%)', 'acima mm50', 'acima mm200', 'score momentum']

        def _momentum_table_html(df: "pd.DataFrame") -> str:
            _mn = 'var(--font-mono,monospace)'
            _show = [c for c in cols_mostrar if c in df.columns]
            _ret_cols = ['ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)', 'dist. topo 52w (%)']
            _hdrs = "".join(
                f'<th style="padding:7px 9px;text-align:{"left" if c in ("ticker","nome","setor") else "right"};'
                f'font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;'
                f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                for c in _show
            )
            _rows = ""
            for _, row in df.iterrows():
                _cells = ""
                for col in _show:
                    _v = row[col]
                    _align = "left" if col in ("ticker","nome","setor") else "right"
                    if col == 'ticker':
                        _url = f"/Research?research_ticker={_v}"
                        _cell = (f'<a href="{_url}" target="_blank" style="color:var(--accent);'
                                 f'font-family:{_mn};font-weight:600;font-size:0.78rem;text-decoration:none;" '
                                 f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'
                                 f'{str(_v).replace(".SA","")}</a>')
                    elif col == 'nome':
                        _cell = f'<span style="font-size:0.78rem;color:var(--text-muted);">{str(_v)[:18] if _v else "—"}</span>'
                    elif col == 'setor':
                        _cell = f'<span style="font-size:0.75rem;color:var(--text-muted);">{str(_v)[:14] if _v else "—"}</span>'
                    elif col == 'score momentum':
                        try:
                            _si = int(float(_v))
                            _sc = "#2ecc71" if _si >= 60 else ("#f39c12" if _si >= 30 else "#e74c3c")
                            _cell = f'<span style="font-family:{_mn};font-size:0.8rem;font-weight:600;color:{_sc};">{_si}</span>'
                        except (TypeError, ValueError):
                            _cell = '<span style="color:var(--text-muted);">—</span>'
                    elif col in ('acima mm50','acima mm200'):
                        try:
                            _bv = bool(_v)
                            _cell = f'<span style="color:{"#2ecc71" if _bv else "#e74c3c"};font-size:0.8rem;">{"✓" if _bv else "✗"}</span>'
                        except (TypeError, ValueError):
                            _cell = '<span style="color:var(--text-muted);">—</span>'
                    elif col in _ret_cols:
                        try:
                            _fv = float(_v)
                            _cv = "#2ecc71" if _fv > 0 else ("#e74c3c" if _fv < 0 else "var(--text-muted)")
                            _cell = f'<span style="font-family:{_mn};font-size:0.78rem;color:{_cv};">{_fv:+.2f}%</span>'
                        except (TypeError, ValueError):
                            _cell = '<span style="color:var(--text-muted);">—</span>'
                    else:
                        _cell = f'<span style="font-family:{_mn};font-size:0.78rem;">{_v}</span>'
                    _cells += f'<td style="padding:7px 9px;text-align:{_align};">{_cell}</td>'
                _rows += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                          f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                          f'onmouseout="this.style.background=\'transparent\'">{_cells}</tr>')
            return (f'<div style="overflow-x:auto;">'
                    f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                    f'<thead><tr>{_hdrs}</tr></thead><tbody>{_rows}</tbody></table></div>')

        st.markdown(_momentum_table_html(df_m[cols_mostrar]), unsafe_allow_html=True)

        section_title("📊 mapa de retornos por janela temporal")

        _mom_tipo = chart_type_toggle(key="mom_retornos", default="linha")
        _cc_mom   = _chart_cores()
        _cores_seq = [_cc_mom["accent"], _cc_mom["info"], _cc_mom["bull"],
                      _cc_mom["amber"], _cc_mom["bear"], "#8B5CF6", "#06B6D4", "#EC4899",
                      "#A78BFA", "#34D399"]

        fig_mom = go.Figure()
        janelas = ['ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)']
        labels  = ['1 mês', '3 meses', '6 meses', '1 ano']

        for i, (_, row) in enumerate(df_m.head(10).iterrows()):
            cor_i = _cores_seq[i % len(_cores_seq)]
            if _mom_tipo == "barras":
                fig_mom.add_trace(go.Bar(
                    name=row['ticker'],
                    x=labels,
                    y=[row[j] for j in janelas],
                    marker_color=cor_i,
                    hovertemplate=f"{row['ticker']}<br>%{{x}}: %{{y:+.1f}}%<extra></extra>",
                ))
            else:
                fig_mom.add_trace(go.Scatter(
                    x=labels, y=[row[j] for j in janelas],
                    mode='lines+markers', name=row['ticker'],
                    line=dict(color=cor_i, width=1.8),
                    marker=dict(size=6),
                    hovertemplate=f"{row['ticker']}<br>%{{x}}: %{{y:+.1f}}%<extra></extra>",
                ))

        fig_mom.add_hline(y=0, line_color=_cc_mom["border"], line_dash="dash", line_width=1)
        _lay_mom = base_layout(height=400, title="retorno acumulado por janela — top 10 ativos")
        if _mom_tipo == "barras":
            _lay_mom["barmode"] = "group"
        fig_mom.update_layout(**_lay_mom)
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
                cor_score = "var(--bull)" if score >= 70 else ("var(--amber)" if score >= 40 else "var(--bear)")
                barra = "█" * int(score // 10) + "░" * int(10 - score // 10)
                c2.markdown(f'<span style="font-family:var(--font-data,monospace); font-size:0.8rem; color:{cor_score};">{barra}</span>', unsafe_allow_html=True)
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
if _secao_d == "🔍 screener quantitativo":
    section_title("🕵️ screener quantitativo — filtros paramétricos")

    # ── 🌉 PONTE 4: CONTEXTO MACRO PARA O SCREENER ───────────────────────────
    try:
        from utils.macro_regime import classificar_regime
        _mc = st.session_state.get("macro_context", {})
        _regime_scr = classificar_regime(
            selic=_mc.get("selic"), vix=_mc.get("vix"),
            ipca=_mc.get("ipca"), treasury_10y=_mc.get("treasury_10y"),
        )
        _fav_scr  = _regime_scr.get("setores_favorecidos", [])
        _prej_scr = _regime_scr.get("setores_prejudicados", [])
        _lbl_scr  = _regime_scr.get("label", "neutro")
        _pos_scr  = _regime_scr.get("posicionamento", "")
        _scr_amb  = _regime_scr.get("score_ambiente", 50)
        _cor_amb  = "var(--bull)" if _scr_amb >= 60 else ("var(--amber)" if _scr_amb >= 35 else "var(--bear)")

        _selic_val = _mc.get("selic")
        # ipca_12m (% aa) vem do macro_cache; ipca do session_state é mensal — não usar.
        _ipca_12m = _mc.get("ipca_12m")
        if _ipca_12m is None:
            try:
                from database.db import get_all_macro_cache
                _mc_cache = {r["indicator"]: r["value"] for r in (get_all_macro_cache() or [])}
                _ipca_12m = _mc_cache.get("ipca_12m")
                if _ipca_12m is not None:
                    _ipca_12m = float(_ipca_12m)
            except Exception:
                _ipca_12m = None
        # Fisher: selic_real = (1 + selic/100) / (1 + ipca_12m/100) - 1
        if _selic_val and _ipca_12m:
            _selic_r_scr = round(((1 + _selic_val / 100) / (1 + _ipca_12m / 100) - 1) * 100, 1)
        else:
            _selic_r_scr = None
        _cor_selic_r = "var(--bear)" if (_selic_r_scr or 0) > 8 else ("var(--amber)" if (_selic_r_scr or 0) > 4 else "var(--bull)")

        st.markdown(
            f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
            f'border-left:4px solid {_cor_amb};border-radius:6px;'
            f'padding:12px 16px;margin-bottom:12px;font-family:var(--font-ui,sans-serif);">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
            f'<div>'
            f'<span style="color:var(--text-muted);font-size:0.65rem;text-transform:uppercase;">regime macro atual</span><br>'
            f'<span style="color:{_cor_amb};font-size:0.85rem;font-weight:bold;">{_lbl_scr}</span>'
            f'<span style="color:var(--text-muted);font-size:0.7rem;margin-left:8px;">score {_scr_amb}/100</span>'
            f'</div>'
            + (f'<div><span style="color:var(--text-muted);font-size:0.65rem;">selic real</span><br>'
               f'<span style="color:{_cor_selic_r};font-size:0.8rem;">'
               f'{_selic_r_scr:+.1f}%aa</span></div>' if _selic_r_scr else '')
            + (f'<div><span style="color:var(--text-muted);font-size:0.65rem;">setores favorecidos</span><br>'
               f'<span style="color:var(--bull);font-size:0.7rem;">{", ".join(_fav_scr[:3]) if _fav_scr else "—"}</span></div>'
               if _fav_scr else '')
            + (f'<div><span style="color:var(--text-muted);font-size:0.65rem;">setores em cautela</span><br>'
               f'<span style="color:var(--bear);font-size:0.7rem;">{", ".join(_prej_scr[:3]) if _prej_scr else "—"}</span></div>'
               if _prej_scr else '')
            + f'<div style="color:var(--text-muted);font-size:0.68rem;max-width:280px;">{_pos_scr}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    # ── seleção de universo (tabs_pill) ─────────────────────────────────────
    from utils.components import tabs_pill as _tabs_pill_disc, info_box as _info_box_disc
    _univ_labels = [
        f"🇧🇷 B3 ({len(SCREENER_B3)})",
        f"🏢 FIIs ({len(FII_TODOS)})",
        f"🇺🇸 EUA ({len(SCREENER_US)})",
    ]
    _univ_pick = _tabs_pill_disc(_univ_labels, key="screener_univ_pill", default=_univ_labels[0])
    universo_sel = (
        'b3'  if _univ_pick.startswith("🇧🇷")
        else 'fii' if _univ_pick.startswith("🏢")
        else 'us'
    )
    _info_box_disc(
        tipo   = "info",
        titulo = "como funciona",
        texto  = (
            "dados do cache de fundamentos (atualizado pelos botões 🔄 sync no topo). "
            "health score integra técnico, fundamentos e macro."
        ),
        icone  = "ⓘ",
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
            '<div style="font-family:var(--font-ui,sans-serif); font-size:0.72rem; color:var(--text-muted); '
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
            df_display = df_res[['ticker', 'nome', 'score', 'p/l', 'p/vp', 'roe%', 'dy%', 'margem%']].copy()

            for col in ['p/l', 'p/vp', 'roe%', 'dy%', 'margem%']:
                if col in df_display.columns:
                    df_display[col] = df_display[col].apply(
                        lambda x: f"{x:.1f}" if pd.notna(x) and x is not None else "—"
                    )

            def _health_bar_html(s) -> str:
                """Barra CSS de progresso para o health score."""
                try:
                    s = int(s)
                except (TypeError, ValueError):
                    return '<span style="color:var(--text-muted);">— n/c</span>'
                if s <= 0:
                    return '<span style="color:var(--text-muted);">— n/c</span>'
                _cor = ("#2ecc71" if s >= 65 else ("#f39c12" if s >= 40 else "#e74c3c"))
                _pct = min(s, 100)
                return (
                    f'<div style="display:flex;align-items:center;gap:8px;min-width:140px;">'
                    f'<div style="flex:1;background:var(--border-subtle,rgba(255,255,255,0.1));'
                    f'border-radius:3px;height:6px;overflow:hidden;">'
                    f'<div style="width:{_pct}%;height:100%;background:{_cor};border-radius:3px;"></div>'
                    f'</div>'
                    f'<span style="font-family:var(--font-mono,monospace);font-size:0.8rem;'
                    f'color:{_cor};min-width:26px;">{s}</span>'
                    f'</div>'
                )

            # Tabela HTML com links no ticker — abre Research em nova aba
            _header_cols = ["Ticker", "Nome", "Health Score", "P/L", "P/VP", "ROE %", "DY %", "Margem %"]
            _data_cols   = ['ticker', 'nome', 'score', 'p/l', 'p/vp', 'roe%', 'dy%', 'margem%']

            _thead = "".join(
                f'<th style="padding:8px 12px;text-align:left;font-size:0.7rem;'
                f'color:var(--text-muted);text-transform:uppercase;'
                f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{h}</th>'
                for h in _header_cols
            )
            _rows_html = ""
            for _, _row in df_display.iterrows():
                _tk_full  = df_res.loc[_row.name, '_ticker_full'] if _row.name in df_res.index else _row['ticker']
                _tk_label = _row['ticker']
                _url      = f"/Research?research_ticker={_tk_full}"
                _cells = (
                    f'<td style="padding:8px 12px;white-space:nowrap;">'
                    f'<a href="{_url}" target="_blank" '
                    f'style="color:var(--accent);font-family:var(--font-mono,monospace);'
                    f'font-weight:600;font-size:0.82rem;text-decoration:none;" '
                    f'onmouseover="this.style.textDecoration=\'underline\'" '
                    f'onmouseout="this.style.textDecoration=\'none\'">{_tk_label}</a></td>'
                )
                for col in _data_cols[1:]:
                    _val = _row.get(col, "—")
                    if col == 'score':
                        _cells += f'<td style="padding:8px 12px;min-width:160px;">{_health_bar_html(_val)}</td>'
                    else:
                        _cells += (
                            f'<td style="padding:8px 12px;font-size:0.82rem;'
                            f'color:var(--text-secondary,#ccc);white-space:nowrap;">{_val}</td>'
                        )
                _rows_html += (
                    f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                    f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                    f'onmouseout="this.style.background=\'transparent\'">'
                    f'{_cells}</tr>'
                )

            st.markdown(
                f'<div style="font-size:0.68rem;color:var(--text-muted);margin-bottom:6px;">'
                f'clique no ticker para abrir no research em nova aba ↗</div>'
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;'
                f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                f'<thead><tr>{_thead}</tr></thead>'
                f'<tbody>{_rows_html}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )

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

if _secao_d == "🧠 ia: oportunidades do dia":
    section_title("🧠 ia: oportunidades do dia")

    st.markdown(
        '<div style="font-family:var(--font-ui,sans-serif);font-size:0.75rem;'
        'color:var(--text-muted);margin-bottom:16px;line-height:1.7;">'
        'análise de ia do universo completo de ativos. '
        'identifica os top 5 com maior assimetria '
        'risco/retorno no momento, considerando health score, '
        'regime macro e timing técnico. '
        'atualizado sob demanda — clique para rodar.'
        '</div>',
        unsafe_allow_html=True,
    )

    # Universo + modo (chip_filter_row compacto, design system v5)
    st.markdown(
        '<div style="font-family:var(--font-ui);font-size:.58rem;'
        'color:var(--text-muted);text-transform:uppercase;'
        'letter-spacing:var(--ls-wide);margin-top:6px;margin-bottom:2px;'
        'font-weight:600;opacity:.7;">universo</div>',
        unsafe_allow_html=True,
    )
    _univ_ia_raw = chip_filter_row(
        ["🇧🇷 brasil (b3 + fiis)", "🇺🇸 eua (s&p500)", "🌍 todos"],
        key="radio_univ_ia_disc_v2",
        default="🇧🇷 brasil (b3 + fiis)",
        max_chip_cols=10,
    )
    _univ_ia = (
        "BR" if _univ_ia_raw.startswith("🇧🇷")
        else "US" if _univ_ia_raw.startswith("🇺🇸")
        else "AMBOS"
    )

    st.markdown(
        '<div style="font-family:var(--font-ui);font-size:.58rem;'
        'color:var(--text-muted);text-transform:uppercase;'
        'letter-spacing:var(--ls-wide);margin-top:6px;margin-bottom:2px;'
        'font-weight:600;opacity:.7;">foco</div>',
        unsafe_allow_html=True,
    )
    _modo_ia_raw = chip_filter_row(
        ["🎯 melhor entrada", "💰 renda / dividendos", "📤 possível realização"],
        key="radio_modo_ia_disc_v2",
        default="🎯 melhor entrada",
        max_chip_cols=10,
    )
    _modo_ia = (
        "entrada"    if _modo_ia_raw.startswith("🎯")
        else "dividendo" if _modo_ia_raw.startswith("💰")
        else "realizacao"
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

            def _ia_table_html(df: "pd.DataFrame") -> str:
                _mn = 'var(--font-mono,monospace)'
                _num_cols = ['score total','qualidade (hs)','valuation','timing','rsi','5d %','3m %','topo %']
                _hdrs = "".join(
                    f'<th style="padding:7px 10px;text-align:{"left" if c in ("ticker","nome","mercado") else "right"};'
                    f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                    f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                    for c in df.columns
                )
                _rows = ""
                for _, row in df.iterrows():
                    _cells = ""
                    for col in df.columns:
                        _v = row[col]
                        _align = "left" if col in ("ticker","nome","mercado") else "right"
                        if col == 'ticker':
                            _url = f"/Research?research_ticker={_v}"
                            _cell = (f'<a href="{_url}" target="_blank" style="color:var(--accent);'
                                     f'font-family:{_mn};font-weight:600;font-size:0.8rem;text-decoration:none;" '
                                     f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'
                                     f'{str(_v).replace(".SA","")}</a>')
                        elif col == 'nome':
                            _cell = f'<span style="font-size:0.77rem;color:var(--text-muted);">{str(_v)[:18] if pd.notna(_v) else "—"}</span>'
                        elif col == 'mercado':
                            _cell = f'<span style="font-size:0.75rem;color:var(--text-muted);">{_v}</span>'
                        elif col == 'score total':
                            try:
                                _si = int(float(_v))
                                _sc = "#2ecc71" if _si >= 65 else ("#f39c12" if _si >= 45 else "#e74c3c")
                                _cell = f'<span style="font-family:{_mn};font-size:0.85rem;font-weight:700;color:{_sc};">{_si}</span>'
                            except (TypeError, ValueError):
                                _cell = '<span style="color:var(--text-muted);">—</span>'
                        elif col in ('5d %','3m %'):
                            try:
                                _fv = float(_v)
                                _cv = "#2ecc71" if _fv > 0 else ("#e74c3c" if _fv < 0 else "var(--text-muted)")
                                _cell = f'<span style="font-family:{_mn};font-size:0.78rem;color:{_cv};">{_fv:+.1f}%</span>'
                            except (TypeError, ValueError):
                                _cell = '<span style="color:var(--text-muted);">—</span>'
                        elif col in _num_cols:
                            try:
                                _fv = float(_v)
                                _cell = f'<span style="font-family:{_mn};font-size:0.78rem;">{_fv:.0f}</span>'
                            except (TypeError, ValueError):
                                _cell = '<span style="color:var(--text-muted);">—</span>'
                        else:
                            _cell = f'<span style="font-size:0.78rem;">{_v}</span>'
                        _cells += f'<td style="padding:7px 10px;text-align:{_align};">{_cell}</td>'
                    _rows += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                              f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                              f'onmouseout="this.style.background=\'transparent\'">{_cells}</tr>')
                return (f'<div style="overflow-x:auto;">'
                        f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                        f'<thead><tr>{_hdrs}</tr></thead><tbody>{_rows}</tbody></table></div>')

            st.markdown(_ia_table_html(_df_ia), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            section_title("🤖 análise qualitativa — ia")

            _cache_key_analise = f"{_cache_key_ia}_analise"

            # ── Tenta cache do Supabase (TTL 1 dia, por modo+universo) ──────────
            if not st.session_state.get(_cache_key_analise) and not _btn_rodar_ia:
                try:
                    from database.db import get_ai_analysis as _get_ai_disc
                    _db_cache_disc = _get_ai_disc(
                        tipo="discovery",
                        ticker=None,
                        user_id=None,
                        modo=f"{_univ_ia}_{_modo_ia}",
                    )
                    if _db_cache_disc:
                        st.session_state[_cache_key_analise] = _db_cache_disc['conteudo']
                        st.caption(
                            f"⚡ análise via cache supabase — gerada em "
                            f"{str(_db_cache_disc.get('created_at',''))[:16].replace('T',' ')}"
                        )
                except Exception:
                    pass

            if st.session_state.get(_cache_key_analise):
                st.markdown(
                    f'<div style="font-family:var(--font-data,monospace);'
                    f'font-size:0.82rem;color:var(--text-primary);'
                    f'line-height:1.8;background:var(--bg-surface);'
                    f'border:1px solid var(--border-subtle);'
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
                    _macro_ia = st.session_state.get("macro_context", {})

                    # Enriquece top 5 com fundamentos do cache e setor
                    from database.db import get_todos_fundamentos_cache as _gtc
                    _cache_disc = _gtc() or {}

                    _top_payload = []
                    for _r in _top5:
                        _tk = _r['ticker']
                        _fd = _cache_disc.get(_tk) or _cache_disc.get(mapear_ticker_base(_tk)) or {}
                        _alertas_curtos = ""
                        try:
                            _hs_row = next(
                                (h for h in (get_health_scores() or [])
                                 if h['ticker'] == _tk or h['ticker'] == mapear_ticker_base(_tk)),
                                None,
                            )
                            if _hs_row:
                                _als = _hs_row.get('alertas') or []
                                if isinstance(_als, list) and _als:
                                    _alertas_curtos = " | ".join(str(a)[:60] for a in _als[:3])
                        except Exception:
                            pass
                        _top_payload.append({
                            'ticker':       _tk,
                            'nome':         _r.get('nome', ''),
                            'mercado':      _r.get('mercado', ''),
                            'setor':        _fd.get('setor', 'n/d'),
                            'score':        _r.get('score_assim', 0),
                            'q_score':      _r.get('score_hs', 0),
                            'v_score':      _r.get('score_val', 0),
                            't_score':      _r.get('score_timing', 0),
                            'health_score': _r.get('score_hs', 'n/d'),
                            'pl':           _fd.get('p/l', 'n/d'),
                            'pvp':          _fd.get('p/vp', 'n/d'),
                            'roe':          _fd.get('roe%', 'n/d'),
                            'dy':           _fd.get('dy%', 'n/d'),
                            'margem':       _fd.get('margem%', 'n/d'),
                            'rsi':          _r.get('rsi', 'n/d'),
                            'ret_5d':       _r.get('ret_5d', 0),
                            'ret_3m':       _r.get('ret_3m', 0),
                            'dist_top':     _r.get('dist_top', 0),
                            'alertas_curtos': _alertas_curtos or "nenhum",
                        })

                    from utils.ai_prompts import build_discovery_prompt
                    _prompt_ia_disc = build_discovery_prompt(
                        top_ativos    = _top_payload,
                        modo          = _modo_ia,
                        universo      = _univ_ia,
                        macro_context = _macro_ia,
                    )

                    _us_ia_disc = st.session_state.get('user_settings', {})
                    _resposta_ia_disc = chamar_ia(
                        prompt_usuario = _prompt_ia_disc,
                        system         = SYSTEM_ANALISTA,
                        max_tokens     = 1200,
                        temperatura    = 0.3,
                        stream         = True,
                        user_settings  = _us_ia_disc,
                    )

                    # ── Persiste no Supabase (TTL 1 dia) ──────────────────
                    if _resposta_ia_disc:
                        try:
                            from database.db import save_ai_analysis
                            save_ai_analysis(
                                tipo="discovery",
                                ticker=None,
                                user_id=None,
                                modo=f"{_univ_ia}_{_modo_ia}",
                                conteudo=_resposta_ia_disc,
                                modelo="auto",
                                ttl_horas=24,
                            )
                        except Exception:
                            pass
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

if _secao_d == "🗺️ rotação setorial":
    label_com_tooltip(
        "🗺️ ROTAÇÃO SETORIAL — HEALTH SCORE MÉDIO POR SETOR",
        chave="health_score",
        cor="var(--accent)",
        tamanho="0.72rem",
    )

    st.markdown(
        '<div style="font-family:var(--font-ui,sans-serif); font-size:0.75rem; '
        'color:var(--text-muted); margin-bottom:16px; line-height:1.6;">'
        'score médio dos ativos de cada setor no universo analisado. '
        'setores verdes (≥65) em fase de acumulação. '
        'vermelhos (<40) em cautela. dados baseados nos health scores '
        'calculados pelo motor quantitativo.'
        '</div>',
        unsafe_allow_html=True,
    )

    _col_univ, _col_refresh = st.columns([3, 1])
    with _col_univ:
        _univ_set_raw = chip_filter_row(
            ["🇧🇷 Brasil (B3 + FIIs)", "🇺🇸 EUA (S&P500)"],
            key="radio_univ_setorial_v2",
            default="🇧🇷 Brasil (B3 + FIIs)",
            max_chip_cols=10,
        )
        _univ_set = "BR" if _univ_set_raw.startswith("🇧🇷") else "US"
    with _col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 recalcular", key="btn_refresh_setorial",
                     use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── SCORECARD DE ROTAÇÃO (fundamento × técnico × macro) ───────────────────
    section_title("🎯 scorecard de rotação — fundamento × técnico × macro")
    st.markdown(
        '<div style="font-family:var(--font-ui,sans-serif); font-size:0.72rem; '
        'color:var(--text-muted); margin:-4px 0 12px 0; line-height:1.55;">'
        'nota composta que cruza qualidade (health médio), força relativa '
        '(momentum 12m vs universo) e vento macro (regime + inflação setorial). '
        'overweight ≥ 62 · neutro 48–61 · underweight &lt; 48.'
        '</div>',
        unsafe_allow_html=True,
    )
    try:
        from utils.sector_scorecard import calcular_scorecard_setorial
        _scorecard = calcular_scorecard_setorial(_univ_set)
    except Exception:
        _scorecard = []

    if _scorecard:
        import pandas as _pd_sc
        _df_sc = _pd_sc.DataFrame([{
            "setor":      r["label"],
            "composto":   r["composto"],
            "fundamento": r["fundamento"],
            "técnico":    r["tecnico"],
            "macro":      r["macro"],
            "veredicto":  r["veredicto"],
            "ativos":     r["n_ativos"],
        } for r in _scorecard])
        _colcfg = {
            "composto":   st.column_config.ProgressColumn("composto", min_value=0, max_value=100, format="%.0f"),
            "fundamento": st.column_config.ProgressColumn("fundamento", min_value=0, max_value=100, format="%.0f"),
            "técnico":    st.column_config.ProgressColumn("técnico (RS 12m)", min_value=0, max_value=100, format="%.0f"),
            "macro":      st.column_config.ProgressColumn("macro (regime+infl.)", min_value=0, max_value=100, format="%.0f"),
        }
        try:
            st.dataframe(_df_sc, use_container_width=True, hide_index=True, column_config=_colcfg)
        except Exception:
            st.dataframe(_df_sc, use_container_width=True, hide_index=True)

        _ow = [r["label"] for r in _scorecard if r["veredicto"] == "overweight"]
        _uw = [r["label"] for r in _scorecard if r["veredicto"] == "underweight"]
        st.markdown(
            f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.72rem;'
            f'color:var(--text-muted);margin-top:6px;line-height:1.6;">'
            f'<span style="color:var(--bull);font-weight:600;">▲ overweight:</span> '
            f'{", ".join(_ow[:4]) or "—"} &nbsp;·&nbsp; '
            f'<span style="color:var(--bear);font-weight:600;">▼ underweight:</span> '
            f'{", ".join(_uw[-4:]) or "—"}'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

    with st.spinner("agrupando setores..."):
        _dados_set = calcular_heatmap_setorial(_univ_set)

    if not _dados_set:
        info_box(
            tipo   = "info",
            titulo = "nenhum dado setorial disponível",
            texto  = "rode o sync de fundamentos no topo da página primeiro.",
            icone  = "📭",
        )
    else:
        _n_acum_total  = sum(1 for s in _dados_set if s['sinal'] == 'acumulação')
        _n_neutro_total = sum(1 for s in _dados_set if s['sinal'] == 'neutro')
        _n_caut_total  = sum(1 for s in _dados_set if s['sinal'] == 'cautela')

        portfolio_kpis([
            {
                "nome":     "setores analisados",
                "valor":    str(len(_dados_set)),
                "sublabel": "com dados suficientes",
                "tone":     "info",
                "icone":    "📊",
            },
            {
                "nome":     "em acumulação",
                "valor":    str(_n_acum_total),
                "sublabel": "score médio ≥ 65",
                "tone":     "bull" if _n_acum_total > 0 else "muted",
                "icone":    "✨" if _n_acum_total > 0 else "—",
            },
            {
                "nome":     "neutros",
                "valor":    str(_n_neutro_total),
                "sublabel": "score 45–64",
                "tone":     "amber",
                "icone":    "⚖",
            },
            {
                "nome":     "em cautela",
                "valor":    str(_n_caut_total),
                "sublabel": "score médio < 45",
                "tone":     "bear" if _n_caut_total > 0 else "muted",
                "icone":    "⚠" if _n_caut_total > 0 else "—",
            },
        ])

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
            "var(--bear)" if "stress" in _regime_label
            else "var(--amber)" if "altos" in _regime_label
            else "var(--bull)"
        )
        _cor_score = "var(--bull)" if _score_amb >= 60 else ("var(--amber)" if _score_amb >= 35 else "var(--bear)")

        _html_parts = [
            f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);border-left:3px solid {_cor_regime};border-radius:6px;padding:10px 16px;margin-bottom:16px;">',
            f'<div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;">',
            f'<span style="font-family:var(--font-ui,sans-serif);font-size:0.62rem;color:var(--text-muted);text-transform:uppercase;">regime atual</span>',
            f'<span style="font-family:var(--font-data,monospace);font-size:0.82rem;font-weight:600;color:{_cor_regime};">{_regime_label}</span>',
            f'<span style="font-family:var(--font-ui,sans-serif);font-size:0.72rem;color:var(--text-muted);">{_regime_desc[:60]}</span>',
            f'<span style="font-family:var(--font-ui,sans-serif);font-size:0.62rem;color:var(--text-muted);text-transform:uppercase;">score amb.</span>',
            f'<span style="font-family:var(--font-data,monospace);font-size:0.82rem;font-weight:600;color:{_cor_score};">{_score_amb}/100</span>',
            '</div>',
        ]

        _html_parts.append('<div style="display:flex;gap:24px;margin-top:8px;flex-wrap:wrap;">')

        if _fav_setores:
            fav_spans = ''
            for _s in _fav_setores:
                _match = [d for d in _dados_set if _s.lower() in d["setor"].lower()]
                _score_val = _match[0]['score_medio'] if _match else None
                _extra = ' ({:.0f})'.format(_score_val) if _score_val is not None else ''
                fav_spans += f'<span style="background:var(--bull-soft,#003300);color:var(--bull);font-family:var(--font-data,monospace);font-size:0.6rem;padding:2px 6px;border-radius:3px;">{_s}{_extra}</span>'
            _html_parts.append(
                f'<div style="flex:1;min-width:140px;">'
                f'<div style="font-size:0.6rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:3px;">\U0001f7e2 favorecidos pelo regime</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:3px;">{fav_spans}</div>'
                f'</div>'
            )

        if _prej_setores:
            prej_spans = ''
            for _s in _prej_setores:
                _match = [d for d in _dados_set if _s.lower() in d["setor"].lower()]
                _score_val = _match[0]['score_medio'] if _match else None
                _extra = ' ({:.0f})'.format(_score_val) if _score_val is not None else ''
                prej_spans += f'<span style="background:var(--bear-soft,#330000);color:var(--bear);font-family:var(--font-data,monospace);font-size:0.6rem;padding:2px 6px;border-radius:3px;">{_s}{_extra}</span>'
            _html_parts.append(
                f'<div style="flex:1;min-width:140px;">'
                f'<div style="font-size:0.6rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:3px;">\U0001f534 prejudicados pelo regime</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:3px;">{prej_spans}</div>'
                f'</div>'
            )

        _html_parts.append('</div>')

        if _posicionamento:
            _html_parts.append(
                f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.62rem;color:var(--text-muted);margin-top:6px;border-top:1px solid var(--border-subtle);padding-top:4px;">{_posicionamento}</div>'
            )

        _html_parts.append('</div>')

        st.markdown(''.join(_html_parts), unsafe_allow_html=True)

        import plotly.graph_objects as go

        _cc_set = _chart_cores()

        # Mapeamento de cor de sinal → cor do tema
        def _cor_sinal(sinal):
            if sinal == "acumulação": return _cc_set["bull"]
            if sinal == "cautela":   return _cc_set["bear"]
            return _cc_set["amber"]

        _setores_nomes  = [d['setor'] for d in _dados_set]
        _scores_medios  = [d['score_medio'] for d in _dados_set]
        _cores_barras   = [_cor_sinal(d['sinal']) for d in _dados_set]
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
            x=_scores_medios, y=_setores_nomes,
            orientation='h',
            marker_color=_cores_barras,
            marker_opacity=0.88,
            text=[f"{s:.0f}" for s in _scores_medios],
            textposition='outside',
            textfont=dict(size=10, color=_cc_set["muted"], family='Inter, system-ui, sans-serif'),
            hovertext=_hover_texts, hoverinfo='text',
            name='score médio',
        ))
        _fig_set.add_vline(
            x=65, line_color=_cc_set["bull"], line_dash="dash",
            line_width=1, annotation_text="acumulação",
            annotation_font_color=_cc_set["bull"], annotation_font_size=9,
        )
        _fig_set.add_vline(
            x=40, line_color=_cc_set["bear"], line_dash="dash",
            line_width=1, annotation_text="cautela",
            annotation_font_color=_cc_set["bear"], annotation_font_size=9,
        )

        _h_set = max(300, len(_dados_set) * 40)
        _lay_set = base_layout(height=_h_set, title=f"health score médio por setor — {_univ_set}")
        _lay_set.update(
            xaxis=dict(range=[0, 115], showgrid=True,
                       gridcolor=_cc_set["border"], title='score médio'),
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

    st.markdown("<br>", unsafe_allow_html=True)
    section_title("Força Relativa Setorial (US) — base 100, 12 meses")

    from utils.setor_rs import calcular_rs_setorial

    @st.cache_data(ttl=3600, show_spinner=False)
    def _carregar_rs():
        return calcular_rs_setorial()

    rs = _carregar_rs()
    if rs is None:
        st.info("RS indisponível — falha em yfinance ou dados insuficientes.")
    else:
        _fig_rs = go.Figure()
        _cc_rs = _chart_cores()
        _cores_rs = [
            _cc_rs["accent"], _cc_rs["info"], _cc_rs["bull"],
            _cc_rs["amber"], _cc_rs["bear"],
            "#8B5CF6", "#06B6D4", "#EC4899", "#A78BFA",
            "#34D399", "#F472B6",
        ]
        for i, col in enumerate(rs.df_rs.columns):
            _fig_rs.add_trace(go.Scatter(
                x=rs.df_rs.index, y=rs.df_rs[col],
                mode="lines", name=col,
                line=dict(width=1.5, color=_cores_rs[i % len(_cores_rs)]),
                hovertemplate=f"{col}<br>%{{x}}<br>RS: %{{y:.1f}}<extra></extra>",
            ))
        _fig_rs.add_hline(y=100, line_color=_cc_rs["border"], line_dash="dot", line_width=1)
        _lay_rs = base_layout(height=420, title="RS lines — setores EUA vs SPY (base 100)")
        _lay_rs.update(
            yaxis=dict(title="RS (base 100)", gridcolor=_cc_rs["border"]),
            xaxis=dict(gridcolor=_cc_rs["border"]),
            legend=dict(orientation="h", yanchor="bottom", y=-0.22, font=dict(size=9)),
        )
        _fig_rs.update_layout(**_lay_rs)
        st.plotly_chart(_fig_rs, use_container_width=True, config={"responsive": True})
        st.caption(
            "rs (relative strength) = preço do etf setorial dividido pelo spy, "
            "normalizado a 100 no início do período. linhas acima de 100 = "
            "setor outperforming o índice; abaixo = underperforming. "
            "etfs: xlk (tech), xlf (financeiro), xle (energia), xlv (saúde), "
            "xli (industrial), xly (cons. discricionário), xlp (cons. básico), "
            "xlu (utilities), xlre (real estate), xlb (materiais), xlc (comunicação). "
            "leitura: setor com rs subindo persistente = rotação institucional em curso; "
            "topos seguidos de quedas bruscas = exaustão e possível reversão."
        )

        def _rank_table_html(df: "pd.DataFrame") -> str:
            if df is None or df.empty:
                return '<span style="color:var(--text-muted);font-size:0.8rem;">sem dados</span>'
            _mn = 'var(--font-mono,monospace)'
            _hdrs = "".join(
                f'<th style="padding:6px 8px;text-align:{"left" if i==0 else "right"};'
                f'font-size:0.64rem;color:var(--text-muted);text-transform:uppercase;'
                f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                for i, c in enumerate(df.columns)
            )
            _rows = ""
            for idx, (_, row) in enumerate(df.iterrows()):
                _cells = ""
                for i, (col, val) in enumerate(row.items()):
                    _align = "left" if i == 0 else "right"
                    if i == 0:
                        _cell = f'<span style="font-size:0.78rem;">{val}</span>'
                    else:
                        try:
                            _fv = float(val)
                            _cv = "#2ecc71" if _fv > 0 else ("#e74c3c" if _fv < 0 else "var(--text-muted)")
                            _cell = f'<span style="font-family:{_mn};font-size:0.78rem;color:{_cv};">{_fv:+.1f}%</span>'
                        except (TypeError, ValueError):
                            _cell = f'<span style="font-size:0.78rem;">{val}</span>'
                    _cells += f'<td style="padding:6px 8px;text-align:{_align};">{_cell}</td>'
                _bg = "background:rgba(46,204,113,0.08);" if idx == 0 else ""
                _rows += (f'<tr style="border-bottom:1px solid var(--border-subtle);{_bg}" '
                          f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                          f'onmouseout="this.style.background=\'{("rgba(46,204,113,0.08)" if idx==0 else "transparent")}\'">{_cells}</tr>')
            return (f'<div style="overflow-x:auto;">'
                    f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                    f'<thead><tr>{_hdrs}</tr></thead><tbody>{_rows}</tbody></table></div>')

        st.markdown("<br>", unsafe_allow_html=True)
        _rc1, _rc2, _rc3 = st.columns(3)
        with _rc1:
            st.markdown("**Ranking 3 meses**")
            st.markdown(_rank_table_html(rs.ranking_3m), unsafe_allow_html=True)
        with _rc2:
            st.markdown("**Ranking 6 meses**")
            st.markdown(_rank_table_html(rs.ranking_6m), unsafe_allow_html=True)
        with _rc3:
            st.markdown("**Ranking 12 meses**")
            st.markdown(_rank_table_html(rs.ranking_12m), unsafe_allow_html=True)
        st.caption(
            "Δ rs (%) = variação percentual da rs line no período. "
            "valores positivos = setor venceu o spy no intervalo, negativos = perdeu. "
            "compare horizontes: setor liderando 12m mas perdendo 3m sinaliza topo de ciclo "
            "ou rotação saindo. setor perdendo 12m mas liderando 3m pode indicar reversão "
            "de tendência (estágio inicial — confirmar com fundamentos)."
        )

    st.markdown("<br>", unsafe_allow_html=True)
    section_title("Earnings Revisions Breadth (EUA, últimos 30 dias)")

    try:
        from database.supabase_client import get_supabase
        _client_er = get_supabase()
        # Conta total de leituras (com e sem comparação) para sinalizar progresso
        res_all = _client_er.table("earnings_revisions").select("ticker", count="exact").execute()
        n_total_capturas = getattr(res_all, "count", None) or len(res_all.data or [])
        res_er = _client_er.table("earnings_revisions").select("setor, revisao_positiva").not_.is_("revisao_positiva", "null").execute()
        if not res_er.data:
            if n_total_capturas == 0:
                st.info(
                    "📊 **Sem capturas ainda.** O ETL US ainda não populou a tabela. "
                    "Próxima execução vai gravar os snapshots iniciais."
                )
            else:
                st.info(
                    f"📊 **Capturas iniciais em andamento — {n_total_capturas} leituras gravadas.** "
                    "A breadth precisa de 2 snapshots por ticker espaçados em ~30 dias para calcular a revisão. "
                    "Próxima rodada do ETL (em ~30 dias após a primeira) vai começar a popular a tabela. "
                    "Aguarde o ciclo completo."
                )
        else:
            df_er = pd.DataFrame(res_er.data)
            breadth = df_er.groupby("setor").agg(
                n_total=("revisao_positiva", "count"),
                n_pos=("revisao_positiva", "sum"),
            ).reset_index()
            breadth["breadth_pct"] = (breadth["n_pos"] / breadth["n_total"] * 100).round(1)
            breadth = breadth.sort_values("breadth_pct", ascending=False)
            _breadth_disp = breadth.rename(columns={
                "setor": "Setor", "n_total": "N", "n_pos": "Pos", "breadth_pct": "% revisões positivas",
            })
            _mn_er = 'var(--font-mono,monospace)'
            _hdrs_er = "".join(
                f'<th style="padding:7px 10px;text-align:{"left" if c=="Setor" else "right"};'
                f'font-size:0.67rem;color:var(--text-muted);text-transform:uppercase;'
                f'border-bottom:1px solid var(--border-subtle);">{c}</th>'
                for c in _breadth_disp.columns
            )
            _rows_er = ""
            for _, row in _breadth_disp.iterrows():
                _pct = float(row['% revisões positivas'])
                _bc = "#2ecc71" if _pct >= 60 else ("#f39c12" if _pct >= 40 else "#e74c3c")
                _bar_w = min(_pct, 100)
                _rows_er += (
                    f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                    f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                    f'onmouseout="this.style.background=\'transparent\'">'
                    f'<td style="padding:7px 10px;font-size:0.8rem;">{row["Setor"]}</td>'
                    f'<td style="padding:7px 10px;font-family:{_mn_er};font-size:0.78rem;text-align:right;color:var(--text-muted);">{int(row["N"])}</td>'
                    f'<td style="padding:7px 10px;font-family:{_mn_er};font-size:0.78rem;text-align:right;color:var(--text-muted);">{int(row["Pos"])}</td>'
                    f'<td style="padding:7px 10px;min-width:140px;">'
                    f'<div style="display:flex;align-items:center;gap:8px;">'
                    f'<div style="flex:1;background:var(--border-subtle);border-radius:3px;height:5px;overflow:hidden;">'
                    f'<div style="width:{_bar_w:.0f}%;height:100%;background:{_bc};border-radius:3px;"></div></div>'
                    f'<span style="font-family:{_mn_er};font-size:0.8rem;color:{_bc};min-width:38px;text-align:right;">{_pct:.1f}%</span>'
                    f'</div></td>'
                    f'</tr>'
                )
            st.markdown(
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                f'<thead><tr>{_hdrs_er}</tr></thead><tbody>{_rows_er}</tbody></table></div>',
                unsafe_allow_html=True,
            )
        st.caption(
            "earnings revisions breadth = % de empresas por setor com revisão positiva "
            "(>+1%) na estimativa média de eps de analistas nos últimos 30 dias. "
            "fonte: fmp analyst-estimates. é um dos indicadores mais robustos de rotação "
            "setorial — institucionais costumam alocar onde o consenso está revisando pra cima. "
            "leitura: breadth >60% = momentum positivo de revisões; <40% = setor sob pressão. "
            "captura: top 100 tickers do screener us, 1× por execução do etl."
        )
    except Exception as e:
        st.warning(f"Indisponível: {e}")

# ==========================================
# tab 5 — radar de mercado
# ==========================================
if _secao_d == "🚀 momentum & radar":
    st.markdown("<hr style='margin:32px 0 8px;border:0;border-top:1px solid var(--border-subtle);'>", unsafe_allow_html=True)
    section_title("⚡ radar de mercado — oportunidades fora da sua watchlist")
    tooltip("score_assimetria")

    st.markdown(
        '<div style="font-family:var(--font-ui,sans-serif);font-size:0.75rem;'
        'color:var(--text-muted);margin-bottom:16px;line-height:1.6;">'
        'scan em todo o universo de ativos (não só sua watchlist). '
        'filtra por qualidade mínima (health ≥ 55) antes de '
        'calcular o score de assimetria — economiza tempo e foca '
        'onde vale a pena olhar.'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="font-family:var(--font-ui);font-size:.58rem;'
        'color:var(--text-muted);text-transform:uppercase;'
        'letter-spacing:var(--ls-wide);margin-top:6px;margin-bottom:2px;'
        'font-weight:600;opacity:.7;">universo</div>',
        unsafe_allow_html=True,
    )
    _univ_radar_raw = chip_filter_row(
        ["🇧🇷 Brasil (B3 + FIIs)", "🇺🇸 EUA (S&P500)"],
        key="radio_univ_radar_v2",
        default="🇧🇷 Brasil (B3 + FIIs)",
        max_chip_cols=10,
    )
    _univ_radar = "BR" if _univ_radar_raw.startswith("🇧🇷") else "US"

    st.markdown(
        '<div style="font-family:var(--font-ui);font-size:.58rem;'
        'color:var(--text-muted);text-transform:uppercase;'
        'letter-spacing:var(--ls-wide);margin-top:6px;margin-bottom:2px;'
        'font-weight:600;opacity:.7;">modo</div>',
        unsafe_allow_html=True,
    )
    _modo_radar_raw = chip_filter_row(
        ["🎯 entrada", "📤 realização", "💰 dividendos"],
        key="radio_modo_radar_disc_v2",
        default="🎯 entrada",
        max_chip_cols=10,
    )
    _modo_radar_disc = (
        "entrada"    if _modo_radar_raw.startswith("🎯")
        else "realizacao" if _modo_radar_raw.startswith("📤")
        else "dividendo"
    )

    _btn_radar = st.button(
        "▶ rodar scan",
        type="primary",
        use_container_width=False,
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
                f'<div style="font-family:var(--font-ui,sans-serif);'
                f'font-size:0.72rem;color:var(--text-muted);margin-bottom:12px;">'
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

            st.markdown(_ia_table_html(_df_radar), unsafe_allow_html=True)

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