"""
Dashboard executivo — visão geral do mercado em uma tela.

Tela inicial alternativa que combina, em uma página enxuta:
  - regime macro automático (hero_macro)
  - 4 índices globais com sparkline (kpi_index_row)
  - patrimônio do portfólio (portfolio_hero)
  - earnings da semana dos ativos da watchlist (events_strip)
  - top movers · alertas críticos · watchlists ativas (highlights_strip)

Optimizado para scan rápido — abrir, ler 30s, fechar.
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import datetime as dt
from datetime import datetime
import logging

# Silenciar warning vermelho do yfinance no console
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from utils.components import (
    topbar, hero_macro, kpi_index_row, events_strip, highlights_strip,
    portfolio_hero, info_box, section_title, inject_keyboard_shortcuts,
)
from utils.macro_context import garantir_macro_context
from database.db import (
    get_all_price_cache,
    get_pesos, get_health_scores, get_earnings_dates,
    listar_watchlist, listar_watchlists,
)
from utils.tickers import mapear_ticker_base


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
garantir_macro_context()

_user = get_current_user() or {}
topbar(
    breadcrumb_itens = [("⚡ finterminal", "/"), ("dashboard", None)],
    user_name        = _user.get('username', '') or _user.get('nome', '') or 'usuário',
    sync_label       = "ao vivo",
)

# ─────────────────────────────────────────────────────────────────────────────
# Hero textual
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="font-family:var(--font-ui);font-size:.7rem;'
    f'color:var(--text-muted);text-transform:uppercase;'
    f'letter-spacing:var(--ls-wider);margin-bottom:6px;font-weight:600;">'
    f'visão geral · {datetime.now().strftime("%d/%m/%Y · %H:%M")}</div>'
    f'<h1 style="font-family:var(--font-title);font-size:var(--text-3xl);'
    f'font-weight:800;color:var(--text-primary);margin:0 0 var(--space-4);'
    f'letter-spacing:var(--ls-tight);">dashboard executivo</h1>'
    f'<div style="font-family:var(--font-ui);font-size:var(--text-sm);'
    f'color:var(--text-secondary);margin-bottom:var(--space-4);'
    f'max-width:60ch;">scan de 30s do mercado, do portfólio e dos eventos da '
    f'semana — tudo em uma tela.</div>',
    unsafe_allow_html=True,
)

# ═════════════════════════════════════════════════════════════════════════════
# 1. REGIME MACRO — hero_macro
# ═════════════════════════════════════════════════════════════════════════════
try:
    from utils.regime_classifier import classificar_regime_do_macro_context

    @st.cache_data(ttl=3600, show_spinner=False)
    def _regime_dash():
        return classificar_regime_do_macro_context()

    _regime = _regime_dash()
    _tom = {
        "expansao":  "bull",
        "pico":      "amber",
        "contracao": "accent",
        "vale":      "bear",
    }.get(_regime.fase, "amber")

    _sinais_lst = []
    for k, v in _regime.sinais.items():
        if v is True:
            _s, _t, _vl = "ativo", "bull", "✓"
        elif v is False:
            _s, _t, _vl = "ausente", "bear", "✗"
        else:
            _s, _t, _vl = "indef.", "amber", "—"
        _sinais_lst.append((k, _s, _t, _vl))

    hero_macro(
        score     = int(_regime.probabilidade * 100),
        label     = _regime.fase.upper(),
        descricao = _regime.leitura,
        tom       = _tom,
        sinais    = _sinais_lst,
    )
except Exception as e:
    info_box(
        tipo   = "amber",
        titulo = "regime macro indisponível",
        texto  = f"{e}",
        icone  = "⚠",
    )

# ═════════════════════════════════════════════════════════════════════════════
# 2. ÍNDICES GLOBAIS — kpi_index_row com sparkline
# ═════════════════════════════════════════════════════════════════════════════
section_title("🌐 índices globais")


@st.cache_data(ttl=300, show_spinner=False)
def _indices_dashboard():
    tickers = {
        "IBOVESPA":  "^BVSP",
        "S&P 500":   "^GSPC",
        "USD / BRL": "BRL=X",
        "BITCOIN":   "BTC-USD",
    }
    out = []
    try:
        _raw = yf.download(
            list(tickers.values()),
            period       = "5d",
            auto_adjust  = True,
            progress     = False,
        )
        if isinstance(_raw.columns, pd.MultiIndex):
            try:
                hist = _raw.xs('Close', axis=1, level=0)
            except KeyError:
                hist = _raw.xs('Close', axis=1, level=1)
        else:
            hist = _raw.get('Close', _raw)
        if isinstance(hist, pd.Series):
            hist = hist.to_frame(name=list(tickers.values())[0])

        for nm, tk in tickers.items():
            try:
                s = hist[tk].dropna() if tk in hist.columns else pd.Series()
                if len(s) < 2:
                    continue
                p_atual = float(s.iloc[-1])
                var = ((p_atual / float(s.iloc[-2])) - 1) * 100
                out.append({
                    "nome":    nm,
                    "ticker":  tk,
                    "valor":   p_atual,
                    "var_pct": var,
                    "serie":   [float(x) for x in s.tail(20).tolist()],
                })
            except Exception:
                pass
    except Exception:
        pass
    return out


_idx_data = _indices_dashboard()
if _idx_data:
    kpi_index_row(_idx_data)
else:
    info_box(
        tipo   = "amber",
        titulo = "índices indisponíveis",
        texto  = "yfinance não retornou dados — tente novamente em alguns minutos.",
        icone  = "⚠",
    )

# ═════════════════════════════════════════════════════════════════════════════
# 3. PORTFÓLIO — portfolio_hero
# ═════════════════════════════════════════════════════════════════════════════
section_title("💼 patrimônio do portfólio")

pesos = get_pesos() or []
ativos = {p['ticker']: p for p in pesos if p.get('peso', 0) > 0}

valor_atual_pf = 0.0
custo_total_pf = 0.0
var_dia_pf: dict = {}

if ativos:
    tickers_pf = list(ativos.keys())
    cache_pc = get_all_price_cache()
    tickers_missing = []
    for t, d in ativos.items():
        qtd = float(d.get('quantidade', 0) or 0)
        pm  = float(d.get('preco_medio', 0) or 0)
        custo_total_pf += qtd * pm
        pc = cache_pc.get(t, {})
        p_cache = float(pc.get('preco', 0) or 0)
        if p_cache > 0:
            valor_atual_pf += qtd * p_cache
            var_dia_pf[t] = float(pc.get('var_1d', 0) or 0)
        else:
            tickers_missing.append((t, qtd))

    # Fallback yfinance pros sem cache
    if tickers_missing:
        try:
            tb_set = list(set(mapear_ticker_base(t) for t, _ in tickers_missing))
            _raw_pf = yf.download(tb_set, period="2d", auto_adjust=True, progress=False)
            if isinstance(_raw_pf.columns, pd.MultiIndex):
                try:
                    _close = _raw_pf.xs('Close', axis=1, level=0)
                except KeyError:
                    _close = _raw_pf.xs('Close', axis=1, level=1)
            else:
                _close = _raw_pf.get('Close', _raw_pf)
            if isinstance(_close, pd.Series):
                _close = _close.to_frame(name=tb_set[0])
            _close = _close.ffill()
            for t, qtd in tickers_missing:
                tb = mapear_ticker_base(t)
                if tb in _close.columns:
                    try:
                        s = _close[tb].dropna()
                        if len(s) >= 2:
                            p = float(s.iloc[-1])
                            valor_atual_pf += qtd * p
                            var_dia_pf[t] = ((p / float(s.iloc[-2])) - 1) * 100
                    except Exception:
                        pass
        except Exception:
            pass

    pnl_v = valor_atual_pf - custo_total_pf
    pnl_p = (pnl_v / custo_total_pf * 100) if custo_total_pf > 0 else 0.0

    portfolio_hero(
        titulo      = "PATRIMÔNIO",
        valor_atual = valor_atual_pf,
        custo_total = custo_total_pf,
        pnl_valor   = pnl_v,
        pnl_pct     = pnl_p,
        moeda       = "R$",
        data_source = "cache",
    )
else:
    info_box(
        tipo   = "info",
        titulo = "portfólio vazio",
        texto  = "adicione posições em ⚙ Configurações → Portfólio para ver seu PL aqui.",
        icone  = "📭",
    )

# ═════════════════════════════════════════════════════════════════════════════
# 4. EARNINGS DA SEMANA — events_strip
# ═════════════════════════════════════════════════════════════════════════════
section_title("📅 earnings nos próximos 7 dias")

hoje = dt.date.today()
watchlists = listar_watchlists() or []
tickers_watch = set()
for wl in watchlists:
    try:
        for it in (listar_watchlist(watchlist_id=wl['id']) or []):
            if it.get('ticker'):
                tickers_watch.add(it['ticker'])
    except Exception:
        pass

tickers_base_watch = list(set(mapear_ticker_base(t) for t in tickers_watch))
earnings_map = get_earnings_dates(tickers_base_watch) if tickers_base_watch else {}

evt_items = []
for tb, d in earnings_map.items():
    try:
        dias = (d - hoje).days
        if 0 <= dias <= 7:
            evt_items.append({
                "data":      d.strftime('%d/%m'),
                "dias":      dias,
                "titulo":    tb.replace('.SA', ''),
                "categoria": "brasil" if tb.endswith('.SA') else "eua",
                "impacto":   "alto" if dias <= 2 else "medio",
            })
    except Exception:
        pass

evt_items.sort(key=lambda x: x['dias'])
if evt_items:
    events_strip(evt_items[:6])
else:
    info_box(
        tipo   = "info",
        titulo = "sem earnings esta semana",
        texto  = "nenhum ativo da watchlist reporta nos próximos 7 dias.",
        icone  = "📭",
    )

# ═════════════════════════════════════════════════════════════════════════════
# 5. DESTAQUES — highlights_strip (movers · alertas · watchlists)
# ═════════════════════════════════════════════════════════════════════════════
section_title("📊 destaques do dia")

# Top movers do portfólio
movers_items = []
if var_dia_pf:
    movers_sorted = sorted(
        var_dia_pf.items(),
        key=lambda kv: abs(kv[1]),
        reverse=True,
    )[:5]
    for t, v in movers_sorted:
        movers_items.append({
            "label": t.replace('.SA', ''),
            "valor": f"{'+' if v >= 0 else ''}{v:.2f}%",
            "tone":  "bull" if v >= 0 else "bear",
        })

# Alertas críticos (health < 40) nas watchlists
health = {h['ticker']: h for h in (get_health_scores() or [])}
alertas_items = []
for t in tickers_watch:
    tb = mapear_ticker_base(t)
    h = health.get(tb, {})
    score = h.get('score', 50)
    try:
        score = float(score)
    except Exception:
        score = 50
    if score < 40:
        alertas_items.append({
            "label": f"{t.replace('.SA','')} · score {int(score)}",
            "valor": "",
            "tone":  "bear",
        })

# Watchlists com contagem
wl_items = [
    {
        "label": f"{wl.get('icone','⭐')} {wl.get('nome','?')}",
        "valor": f"{wl.get('total_ativos', 0)}",
        "tone":  "info",
    }
    for wl in watchlists[:5]
]

highlights_strip([
    {
        "titulo": "top movers",
        "icone":  "📊",
        "tone":   "accent",
        "items":  movers_items,
    },
    {
        "titulo": "alertas críticos",
        "icone":  "⚠",
        "tone":   "bear",
        "items":  alertas_items[:5],
    },
    {
        "titulo": "watchlists",
        "icone":  "👁",
        "tone":   "info",
        "items":  wl_items,
    },
])

# ═════════════════════════════════════════════════════════════════════════════
# Rodapé
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.caption(
    f"última atualização: {datetime.now().strftime('%H:%M:%S')} · "
    f"índices em cache de 5min · regime macro em cache de 1h"
)
