"""
Watchlists — ferramenta full-screen de gestão consolidada das watchlists.

Diferenças vs widget da Home:
  - Seletor MULTI-watchlist (visualiza união de várias listas)
  - Filtros avançados (mercado · tag · busca textual · health range)
  - Painel "Overlap" — tickers presentes em >1 lista
  - Tabela densa com sparkline 30d, var 1m, contagem de alertas
  - KPI header com agregados (total · alertas · bull · bear)

Pensado pra gestor que mantém múltiplas watchlists (Dividendos BR, Tech EUA,
FIIs, Especulação, etc.) e precisa de visão consolidada.
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import json
import datetime as dt
import logging

logging.getLogger('yfinance').setLevel(logging.CRITICAL)

from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from utils.components import (
    topbar, section_title, info_box, portfolio_kpis, highlights_strip,
    tabs_pill, pill_select, chip, chip_status, html_table,
    inline_sparkline, info_box as _info_box, inject_keyboard_shortcuts,
    chip_filter_row,
)
from database.db import (
    listar_watchlist, listar_watchlists, listar_tags_watchlist,
    get_health_scores, get_all_price_cache,
)
from utils.tickers import mapear_ticker_base, normalizar_mercado


# ─────────────────────────────────────────────────────────────────────────────
# Auth + tema
# ─────────────────────────────────────────────────────────────────────────────
if not require_auth():
    st.stop()

render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()
try:
    from utils.themes import render_theme_switcher_sidebar
    render_theme_switcher_sidebar()
except Exception:
    pass

_user = get_current_user() or {}
topbar(
    breadcrumb_itens = [("⚡ finterminal", "/"), ("watchlists", None)],
    user_name        = _user.get('username', '') or _user.get('nome', '') or 'usuário',
    sync_label       = "ao vivo",
)

# ─────────────────────────────────────────────────────────────────────────────
# Hero textual
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-family:var(--font-ui);font-size:.7rem;'
    'color:var(--text-muted);text-transform:uppercase;'
    'letter-spacing:var(--ls-wider);margin-bottom:6px;font-weight:600;">'
    '👁 watchlists · visão consolidada</div>'
    '<h1 style="font-family:var(--font-title);font-size:var(--text-3xl);'
    'font-weight:800;color:var(--text-primary);margin:0 0 var(--space-2);'
    'letter-spacing:var(--ls-tight);">todas as suas listas em uma tela</h1>'
    '<div style="font-family:var(--font-ui);font-size:var(--text-sm);'
    'color:var(--text-secondary);margin-bottom:var(--space-4);'
    'max-width:60ch;">filtre por mercado, tese ou health · veja '
    'overlap entre listas · identifique top picks e críticos em segundos.</div>',
    unsafe_allow_html=True,
)

# ═════════════════════════════════════════════════════════════════════════════
# 1. CARREGAR WATCHLISTS
# ═════════════════════════════════════════════════════════════════════════════
watchlists = listar_watchlists() or []

if not watchlists:
    info_box(
        tipo   = "info",
        titulo = "sem watchlists ainda",
        texto  = "crie sua primeira watchlist na Home (👁️ watchlist & radar). depois volte aqui para ver a visão consolidada.",
        icone  = "📋",
    )
    st.stop()

# ═════════════════════════════════════════════════════════════════════════════
# 2. SELETOR MULTI-WATCHLIST
# ═════════════════════════════════════════════════════════════════════════════
section_title("📋 watchlists ativas")

st.markdown(
    '<div style="font-family:var(--font-ui);font-size:.66rem;'
    'color:var(--text-muted);text-transform:uppercase;'
    'letter-spacing:var(--ls-wide);margin-bottom:8px;font-weight:600;">'
    'marque uma ou mais para combinar (união)</div>',
    unsafe_allow_html=True,
)

# Linha de checkboxes (1 por watchlist)
_n_wl = len(watchlists)
_cols_wl = st.columns(min(_n_wl, 6))

watchlists_selecionadas: list[dict] = []
for i, wl in enumerate(watchlists):
    with _cols_wl[i % len(_cols_wl)]:
        _key = f"wlpro_chk_{wl['id']}"
        _default = (i == 0)  # primeira marcada por padrão
        _label = f"{wl.get('icone','⭐')} {wl.get('nome','?')} · {wl.get('total_ativos', 0)}"
        if st.checkbox(_label, value=st.session_state.get(_key, _default), key=_key):
            watchlists_selecionadas.append(wl)

if not watchlists_selecionadas:
    info_box(
        tipo   = "amber",
        titulo = "selecione pelo menos uma watchlist",
        texto  = "marque ao menos uma das listas acima para começar.",
        icone  = "☝",
    )
    st.stop()

# ═════════════════════════════════════════════════════════════════════════════
# 3. UNIÃO DE ATIVOS (cross-watchlist)
# ═════════════════════════════════════════════════════════════════════════════
# Mapeia: ticker → set(watchlist_ids onde aparece)
ativos_uniao: dict[str, dict] = {}
overlap_map: dict[str, set] = {}

for wl in watchlists_selecionadas:
    try:
        items = listar_watchlist(watchlist_id=wl['id']) or []
    except Exception:
        items = []
    for it in items:
        tk = it.get('ticker')
        if not tk:
            continue
        if tk not in ativos_uniao:
            ativos_uniao[tk] = dict(it)
        if tk not in overlap_map:
            overlap_map[tk] = set()
        overlap_map[tk].add(wl['id'])

if not ativos_uniao:
    info_box(
        tipo   = "info",
        titulo = "watchlists vazias",
        texto  = "as watchlists selecionadas não têm ativos. adicione na Home.",
        icone  = "📭",
    )
    st.stop()

# ═════════════════════════════════════════════════════════════════════════════
# 4. KPIs AGREGADOS
# ═════════════════════════════════════════════════════════════════════════════
health_data = {h['ticker']: h for h in (get_health_scores() or [])}
cache_precos = get_all_price_cache() or {}

# Sincronizar preços (cache + yfinance fallback)
@st.cache_data(ttl=300, show_spinner=False)
def _precos_e_serie(tickers_tuple: tuple) -> dict:
    out: dict = {}
    if not tickers_tuple:
        return out
    try:
        tb_set = list(set(mapear_ticker_base(t) for t in tickers_tuple))
        _raw = yf.download(tb_set, period="1mo", auto_adjust=True, progress=False)
        if isinstance(_raw.columns, pd.MultiIndex):
            try:
                hist = _raw.xs('Close', axis=1, level=0)
            except KeyError:
                hist = _raw.xs('Close', axis=1, level=1)
        else:
            hist = _raw.get('Close', _raw)
        if isinstance(hist, pd.Series):
            hist = hist.to_frame(name=tb_set[0])
        hist = hist.ffill()

        for t in tickers_tuple:
            tb = mapear_ticker_base(t)
            try:
                if tb in hist.columns:
                    s = hist[tb].dropna()
                    if len(s) >= 2:
                        p_atual = float(s.iloc[-1])
                        p_ontem = float(s.iloc[-2])
                        p_1m    = float(s.iloc[0])
                        out[t] = {
                            "preco":   p_atual,
                            "var_1d":  ((p_atual / p_ontem) - 1) * 100,
                            "var_1m":  ((p_atual / p_1m)    - 1) * 100,
                            "serie":   [float(x) for x in s.tail(30).tolist()],
                        }
            except Exception:
                pass
    except Exception:
        pass
    return out

with st.spinner("sincronizando preços e série 30d..."):
    precos_extras = _precos_e_serie(tuple(sorted(ativos_uniao.keys())))

# Merge: cache → extras (extras tem série, cache tem dado mais fresco)
precos: dict[str, dict] = {}
for t in ativos_uniao:
    p_cache = cache_precos.get(t, {})
    p_extra = precos_extras.get(t, {})
    precos[t] = {
        "preco":  float(p_cache.get('preco', p_extra.get('preco', 0)) or 0),
        "var_1d": float(p_cache.get('var_1d', p_extra.get('var_1d', 0)) or 0),
        "var_1m": float(p_cache.get('var_1m', p_extra.get('var_1m', 0)) or 0),
        "serie":  p_extra.get('serie', []),
    }

# Estatísticas
n_total = len(ativos_uniao)
n_bull  = sum(1 for t in ativos_uniao if precos[t]['var_1d'] > 0)
n_bear  = sum(1 for t in ativos_uniao if precos[t]['var_1d'] < 0)
n_alert = 0
soma_health = 0
n_health = 0
for t in ativos_uniao:
    tb = mapear_ticker_base(t)
    h = health_data.get(tb, {})
    try:
        sc = float(h.get('score', 50) or 50)
        soma_health += sc
        n_health += 1
        if sc < 40:
            n_alert += 1
    except Exception:
        pass
health_medio = (soma_health / n_health) if n_health else 0

n_overlap = sum(1 for ids in overlap_map.values() if len(ids) > 1)

# Soma das variações 1d (média ponderada simples)
soma_var = 0
n_var = 0
for t in ativos_uniao:
    v = precos[t]['var_1d']
    if v != 0:
        soma_var += v
        n_var += 1
media_var = (soma_var / n_var) if n_var else 0

# KPI row (4 cards via portfolio_kpis — sublabel + delta opcional)
_health_tone = "bull" if health_medio >= 60 else ("amber" if health_medio >= 45 else "bear")
_mov_tone    = "bull" if n_bull >= n_bear else "bear"

portfolio_kpis([
    {
        "nome":     "total ativos",
        "valor":    f"{n_total}",
        "sublabel": f"em {len(watchlists_selecionadas)} list{'a' if len(watchlists_selecionadas) == 1 else 'as'}",
        "tone":     "info",
        "icone":    "📊",
    },
    {
        "nome":     "health médio",
        "valor":    f"{health_medio:.1f}",
        "sublabel": f"{n_alert} crítico{'s' if n_alert != 1 else ''} (<40)",
        "tone":     _health_tone,
        "icone":    "💎" if _health_tone == "bull" else ("⚠" if _health_tone == "amber" else "🚨"),
    },
    {
        "nome":     "movimento hoje",
        "valor":    f"{(n_bull/max(n_total,1))*100:.0f}%",
        "sublabel": f"↑{n_bull} subiram · ↓{n_bear} caíram",
        "var_pct":  media_var,
        "tone":     _mov_tone,
    },
    {
        "nome":     "overlap",
        "valor":    f"{n_overlap}",
        "sublabel": "ativos em ≥2 listas",
        "tone":     "accent" if n_overlap > 0 else "muted",
        "icone":    "🔗",
    },
])

# ═════════════════════════════════════════════════════════════════════════════
# 5. FILTROS
# ═════════════════════════════════════════════════════════════════════════════
section_title("🔍 filtros")

# Mercado filter (normalizado)
mercados_disp = sorted(set(
    normalizar_mercado(it.get('mercado')) for it in ativos_uniao.values()
))
_mkt_label_map = {
    "brasil":       "🇧🇷 BR",
    "eua":          "🇺🇸 EUA",
    "criptomoedas": "₿ Cripto",
    "outros":       "🌐 Outros",
}
mkt_opcoes = ["Todos"] + [_mkt_label_map[m] for m in mercados_disp]
st.markdown(
    '<div style="font-family:var(--font-ui);font-size:.58rem;'
    'color:var(--text-muted);text-transform:uppercase;'
    'letter-spacing:var(--ls-wide);margin-top:6px;margin-bottom:2px;'
    'font-weight:600;opacity:.7;">mercado</div>',
    unsafe_allow_html=True,
)
mkt_sel = chip_filter_row(
    mkt_opcoes, key="wlpro_mkt", default="Todos", max_chip_cols=10,
)

# Tag filter (todas as tags únicas entre as watchlists selecionadas)
tags_union: set = set()
for wl in watchlists_selecionadas:
    try:
        for t in (listar_tags_watchlist(wl['id']) or []):
            tags_union.add(t)
    except Exception:
        pass
tags_disp = sorted(tags_union)

if tags_disp:
    tag_opcoes = ["🌐 todas"] + [f"📁 {t}" for t in tags_disp]
    st.markdown(
        '<div style="font-family:var(--font-ui);font-size:.58rem;'
        'color:var(--text-muted);text-transform:uppercase;'
        'letter-spacing:var(--ls-wide);margin-top:6px;margin-bottom:2px;'
        'font-weight:600;opacity:.7;">tese / tag</div>',
        unsafe_allow_html=True,
    )
    tag_sel_raw = chip_filter_row(
        tag_opcoes, key="wlpro_tag", default="🌐 todas", max_chip_cols=10,
    )
    tag_sel = (
        'todas' if tag_sel_raw == "🌐 todas"
        else tag_sel_raw.replace("📁 ", "", 1)
    )
else:
    tag_sel = 'todas'

# Busca textual (linha separada compacta)
st.markdown(
    '<div style="font-family:var(--font-ui);font-size:.58rem;'
    'color:var(--text-muted);text-transform:uppercase;'
    'letter-spacing:var(--ls-wide);margin-top:6px;margin-bottom:2px;'
    'font-weight:600;opacity:.7;">buscar ticker</div>',
    unsafe_allow_html=True,
)
busca = st.text_input(
    "buscar ticker:",
    placeholder="ex: petr, wege, aapl...",
    label_visibility="collapsed",
    key="wlpro_busca",
)

# Ordenação compacta
st.markdown(
    '<div style="display:flex;align-items:center;gap:10px;'
    'margin-top:14px;margin-bottom:4px;">'
    '<span style="font-family:var(--font-ui);font-size:.6rem;'
    'color:var(--text-muted);text-transform:uppercase;'
    'letter-spacing:var(--ls-wider);font-weight:700;">↕ ordenar por</span>'
    '<span style="flex:1;height:1px;background:var(--border-subtle);'
    'opacity:.5;"></span></div>',
    unsafe_allow_html=True,
)
ord_campo = chip_filter_row(
    ["health", "var 1d", "var 1m", "ticker"],
    key="wlpro_ord_campo",
    default="health",
    max_chip_cols=10,
)
ord_dir = chip_filter_row(
    ["↓ desc", "↑ asc"],
    key="wlpro_ord_dir",
    default="↓ desc",
    max_chip_cols=10,
)

# Aplicar filtros
ativos_filtrados: list[dict] = []
_label_mkt_inverso = {v: k for k, v in _mkt_label_map.items()}
mkt_chave = (
    None if mkt_sel == "Todos"
    else _label_mkt_inverso.get(mkt_sel, "outros")
)

for tk, it in ativos_uniao.items():
    # Mercado (normalizado)
    if mkt_chave and normalizar_mercado(it.get('mercado')) != mkt_chave:
        continue
    # Tag
    if tag_sel != 'todas' and (it.get('tag') or 'geral') != tag_sel:
        continue
    # Busca
    if busca:
        b_lower = busca.lower().strip()
        if (b_lower not in tk.lower()) and (b_lower not in (it.get('nome') or '').lower()):
            continue
    ativos_filtrados.append(it)

# Ordenação
def _sort_key(it):
    tk = it.get('ticker', '')
    tb = mapear_ticker_base(tk)
    p  = precos.get(tk, {})
    h  = health_data.get(tb, {})
    if ord_campo == "health":
        return float(h.get('score', 50) or 50)
    elif ord_campo == "var 1d":
        return float(p.get('var_1d', 0) or 0)
    elif ord_campo == "var 1m":
        return float(p.get('var_1m', 0) or 0)
    elif ord_campo == "ticker":
        return tk
    return 0

ativos_filtrados.sort(key=_sort_key, reverse=("↓" in ord_dir))

# ═════════════════════════════════════════════════════════════════════════════
# 6. TABELA AVANÇADA
# ═════════════════════════════════════════════════════════════════════════════
section_title(f"📊 {len(ativos_filtrados)} ativos · união filtrada")

if not ativos_filtrados:
    info_box(
        tipo   = "info",
        titulo = "nenhum ativo bate com os filtros",
        texto  = "tente afrouxar os filtros (Todos os mercados, todas as teses).",
        icone  = "🔍",
    )
else:
    headers = ["Ticker", "Nome", "Mercado", "Tese", "Preço", "1d", "1m", "30d", "Health", "Listas"]
    rows: list[list[str]] = []
    for it in ativos_filtrados:
        tk = it['ticker']
        tb = mapear_ticker_base(tk)
        p  = precos.get(tk, {})
        h  = health_data.get(tb, {})

        v_1d = float(p.get('var_1d', 0) or 0)
        v_1m = float(p.get('var_1m', 0) or 0)
        preco = float(p.get('preco', 0) or 0)
        serie = p.get('serie', [])
        score = float(h.get('score', 50) or 50)

        # Cores
        c_1d = "var(--bull)" if v_1d >= 0 else "var(--bear)"
        c_1m = "var(--bull)" if v_1m >= 0 else "var(--bear)"
        a_1d = "▲" if v_1d >= 0 else "▼"
        a_1m = "▲" if v_1m >= 0 else "▼"

        moeda = "R$" if tb.endswith(".SA") else "$"

        # Chip mercado (normalizado)
        mk = normalizar_mercado(it.get('mercado'))
        _mk_tone = {"brasil": "bull", "eua": "info", "criptomoedas": "accent"}.get(mk, "muted")
        _mk_lbl = {"brasil": "BR", "eua": "EUA", "criptomoedas": "Cripto"}.get(mk, "Outros")

        # Chip tese
        tag_lbl = it.get('tag') or 'geral'

        # Chip status health
        if score >= 65:
            status_lbl = f"{int(score)}"
            status_tone = "bull"
        elif score >= 40:
            status_lbl = f"{int(score)}"
            status_tone = "amber"
        else:
            status_lbl = f"{int(score)}"
            status_tone = "bear"

        # Sparkline
        spark_html = ""
        if serie and len(serie) >= 2:
            spark_html = inline_sparkline(
                serie,
                tone="bull" if serie[-1] >= serie[0] else "bear",
                largura=80,
                altura=22,
            )

        # Listas em que aparece
        n_listas = len(overlap_map.get(tk, set()))
        listas_html = (
            f'<span style="font-family:var(--font-data);font-size:.7rem;'
            f'color:{"var(--accent)" if n_listas > 1 else "var(--text-muted)"};'
            f'font-weight:600;">{n_listas}×</span>'
        )

        ticker_label = tk.replace('.SA', '')
        rows.append([
            f'<a href="/Research?research_ticker={tk}" target="_blank" '
            f'style="font-family:var(--font-data);font-weight:700;'
            f'color:var(--accent);text-decoration:none;">{ticker_label}</a>',
            f'<span style="font-family:var(--font-ui);font-size:.78rem;'
            f'color:var(--text-secondary);">'
            f'{(it.get("nome") or tk)[:28]}</span>',
            chip(_mk_lbl, tone=_mk_tone),
            chip(tag_lbl, tone="muted") if tag_lbl != 'geral' else
                f'<span style="color:var(--text-muted);font-size:.7rem;">—</span>',
            f'<span style="font-family:var(--font-data);font-weight:600;'
            f'color:var(--text-primary);">{moeda} {preco:,.2f}</span>',
            f'<span style="font-family:var(--font-data);color:{c_1d};'
            f'font-weight:600;">{a_1d} {abs(v_1d):.2f}%</span>',
            f'<span style="font-family:var(--font-data);color:{c_1m};'
            f'opacity:.85;">{a_1m} {abs(v_1m):.2f}%</span>',
            spark_html or '<span style="color:var(--text-muted);opacity:.4;">—</span>',
            chip_status(status_lbl, tone=status_tone),
            listas_html,
        ])

    html_table(
        headers,
        rows,
        aligns=["left", "left", "left", "left", "right", "right", "right", "center", "center", "center"],
        sticky_header=True,
    )

# ═════════════════════════════════════════════════════════════════════════════
# 7. OVERLAP + DESTAQUES (highlights_strip)
# ═════════════════════════════════════════════════════════════════════════════
section_title("🎯 destaques cross-watchlist")

# Overlap: tickers presentes em >1 lista (top 5)
nome_por_id = {wl['id']: f"{wl.get('icone','⭐')} {wl.get('nome','?')}" for wl in watchlists}
overlap_items = []
for tk, ids in sorted(overlap_map.items(), key=lambda kv: -len(kv[1]))[:5]:
    if len(ids) > 1:
        listas_str = ", ".join(
            nome_por_id.get(wid, '?').split(' ', 1)[-1]  # sem ícone
            for wid in list(ids)[:3]
        )
        overlap_items.append({
            "label": f"{tk.replace('.SA','')} · {len(ids)}×",
            "valor": "",
            "tone":  "accent",
        })

# Top picks (health > 70)
top_picks = sorted(
    [(it['ticker'], float(health_data.get(mapear_ticker_base(it['ticker']), {}).get('score', 50) or 50))
     for it in ativos_uniao.values()],
    key=lambda kv: -kv[1],
)[:5]
top_picks_items = [
    {"label": tk.replace('.SA',''), "valor": f"{int(s)}", "tone": "bull"}
    for tk, s in top_picks if s >= 65
]

# Críticos (health < 40)
criticos_items = []
for it in ativos_uniao.values():
    tk = it['ticker']
    tb = mapear_ticker_base(tk)
    sc = float(health_data.get(tb, {}).get('score', 50) or 50)
    if sc < 40:
        criticos_items.append({
            "label": f"{tk.replace('.SA','')} · {int(sc)}",
            "valor": "",
            "tone":  "bear",
        })

highlights_strip([
    {
        "titulo": "top picks (health ≥ 65)",
        "icone":  "✨",
        "tone":   "bull",
        "items":  top_picks_items[:5],
    },
    {
        "titulo": "overlap (em ≥2 listas)",
        "icone":  "🔗",
        "tone":   "accent",
        "items":  overlap_items,
    },
    {
        "titulo": "críticos (health < 40)",
        "icone":  "⚠",
        "tone":   "bear",
        "items":  criticos_items[:5],
    },
])

# ═════════════════════════════════════════════════════════════════════════════
# Rodapé
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.caption(
    f"📋 watchlists · {len(watchlists_selecionadas)} listas selecionadas · "
    f"{n_total} ativos na união · "
    f"cache de 5min para preços/séries 30d"
)
