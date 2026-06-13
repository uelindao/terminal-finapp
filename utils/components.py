"""
utils/components.py — v4.1
Componentes HTML do design system.
Fase 3a: 100% tokens — sem hex/font hardcoded; usa var(--font-{title,ui,data})
e var(--text-*)/--space-*/--ls-*. Cores via var(--bg-*/--text-*/--accent/etc).
"""
import warnings as _warnings
import streamlit as st
import time


def ticker_nav_url(ticker: str) -> str:
    """Gera URL de navegação para Research com token de sessão embutido."""
    s = st.session_state.get('session_token', '')
    if s:
        return f"?research_ticker={ticker}&s={s}"
    return f"?research_ticker={ticker}"

_ticker_nav_url = ticker_nav_url  # alias interno


def handle_ticker_nav():
    """
    Trata navegação via ?research_ticker=TICKER.
    Preserva ?s=TOKEN (da URL ou session_state) para auto-login na nova página.
    Chamar no topo de cada página que exibe tickers clicáveis.
    """
    _rt = st.query_params.get("research_ticker")
    if _rt:
        # Prioridade: token da URL → session_state (aba já logada)
        _s = st.query_params.get("s") or st.session_state.get('session_token', '')
        st.query_params.clear()
        if _s:
            st.query_params["s"] = _s
        st.session_state['research_ticker_externo'] = _rt
        st.switch_page("pages/1_Research.py")


def page_header(titulo: str, subtitulo: str = ""):
    """Header compacto de página."""
    st.markdown(
        f'<div style="margin-bottom: var(--space-4);">'
        f'<div style="'
        f'font-family: var(--font-title); '
        f'font-size: var(--text-lg); '
        f'font-weight: 700; '
        f'color: var(--accent); '
        f'letter-spacing: var(--ls-wide);">'
        f'{titulo}</div>'
        + (
            f'<div style="'
            f'font-family: var(--font-ui); '
            f'font-size: var(--text-sm); '
            f'color: var(--text-muted); '
            f'margin-top: 2px; '
            f'letter-spacing: var(--ls-wide);">'
            f'{subtitulo}</div>'
            if subtitulo else ''
        ) +
        f'</div>',
        unsafe_allow_html=True,
    )


def section_title(titulo: str):
    """Título de seção com barra do acento à esquerda."""
    st.markdown(
        f'<div style="'
        f'font-family: var(--font-ui); '
        f'font-size: var(--text-xs); '
        f'color: var(--accent); '
        f'text-transform: uppercase; '
        f'letter-spacing: var(--ls-wider); '
        f'font-weight: 600; '
        f'border-left: 2px solid var(--accent); '
        f'padding-left: var(--space-2); '
        f'margin: var(--space-4) 0 var(--space-2) 0;">'
        f'{titulo}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _fonte_badge(fonte: str = "") -> str:
    if not fonte:
        return ""
    icone = "📦" if fonte == "cache" else "📡"
    cor = "var(--bull)" if fonte == "cache" else "var(--accent)"
    return f'<span style="font-size:0.55rem; color:{cor}; margin-left:5px; font-weight:400; opacity:0.7;">{icone} {fonte}</span>'


def metric_card(
    label:      str,
    valor:      str,
    sublabel:   str  = "",
    cor_delta:  str  = "muted",
    icone:      str  = "",
    destaque:   bool = False,
    data_source: str = "",
):
    """
    Renderiza card de métrica com 4 níveis visuais.

    cor_delta:
      "bull"  → borda e valor verde  (#00C853)
      "bear"  → borda e valor vermelho (#FF1744)
      "amber" → borda e valor laranja (#FF9900)
      "muted" → borda cinza sutil (padrão)
      "info"  → borda azul (#00B0FF)

    destaque: True → card com background mais escuro e tamanho de
              valor maior — para KPIs principais
    data_source: "cache" | "api" → mostra badge de origem
    """
    _cores = {
        "bull":  {"borda": "var(--bull)",  "valor": "var(--bull)",
                  "bg": "var(--bull-soft)", "bg_dest": "var(--bull-soft)",
                  "sublabel": "var(--bull)"},
        "bear":  {"borda": "var(--bear)",  "valor": "var(--bear)",
                  "bg": "var(--bear-soft)", "bg_dest": "var(--bear-soft)",
                  "sublabel": "var(--bear)"},
        "amber": {"borda": "var(--amber)", "valor": "var(--amber)",
                  "bg": "var(--bg-surface)", "bg_dest": "var(--bg-elevated)",
                  "sublabel": "var(--amber)"},
        "info":  {"borda": "var(--info)",  "valor": "var(--info)",
                  "bg": "var(--bg-surface)", "bg_dest": "var(--bg-elevated)",
                  "sublabel": "var(--info)"},
        "muted": {"borda": "var(--border-subtle)", "valor": "var(--text-secondary)",
                  "bg": "var(--bg-surface)", "bg_dest": "var(--bg-elevated)",
                  "sublabel": "var(--text-muted)"},
    }
    _c = _cores.get(cor_delta, _cores["muted"])

    _sz_label  = "0.65rem"
    _sz_valor  = "1.3rem" if destaque else "1.05rem"
    _sz_sub    = "0.68rem"
    _pad       = "16px 18px" if destaque else "12px 14px"
    _bg        = _c["bg_dest"] if destaque else _c["bg"]

    _icone_html = (
        f'<span style="font-size:1.1rem;margin-right:6px;">{icone}</span>'
    ) if icone else ''

    st.markdown(
        f'<div style="'
        f'background:{_bg}; '
        f'border:1px solid var(--border-subtle); '
        f'border-left:3px solid {_c["borda"]}; '
        f'border-radius:var(--radius-sm); '
        f'padding:{_pad}; '
        f'margin-bottom:4px; '
        f'transition:border-color .2s;">'

        f'<div style="'
        f'font-family:var(--font-ui); '
        f'font-size:{_sz_label}; '
        f'color:var(--text-muted); '
        f'text-transform:uppercase; '
        f'letter-spacing:.08em; '
        f'margin-bottom:4px;">'
        f'{label}{_fonte_badge(data_source)}</div>'

        f'<div style="'
        f'font-family:var(--font-data); '
        f'font-size:{_sz_valor}; '
        f'font-weight:700; '
        f'color:{_c["valor"]}; '
        f'line-height:1.2; '
        f'margin-bottom:2px;">'
        f'{_icone_html}{valor}</div>'

        + (
            f'<div style="'
            f'font-family:var(--font-data); '
            f'font-size:{_sz_sub}; '
            f'color:{_c["sublabel"]};">'
            f'{sublabel}</div>'
            if sublabel else ''
        ) +

        f'</div>',
        unsafe_allow_html=True,
    )


def status_card(
    titulo:  str,
    corpo:   str,
    tipo:    str = "amber",
    icone:   str = "",
):
    """
    Card de status/alerta com fundo colorido.

    tipo:
      "bull"  → fundo verde escuro
      "bear"  → fundo vermelho escuro
      "amber" → fundo laranja escuro
      "info"  → fundo azul escuro
      "muted" → fundo cinza
    """
    _mapa_status = {
        "bull":  ("var(--bull)",  "var(--bull-soft)",  "✅"),
        "bear":  ("var(--bear)",  "var(--bear-soft)",  "⚠️"),
        "amber": ("var(--amber)", "var(--bg-elevated)", "💡"),
        "info":  ("var(--info)",  "var(--bg-elevated)", "ℹ️"),
        "muted": ("var(--text-muted)", "var(--bg-surface)", "📋"),
    }
    _cor, _bg, _icone_def = _mapa_status.get(tipo, _mapa_status["amber"])
    _ic = icone or _icone_def

    st.markdown(
        f'<div style="'
        f'background:{_bg}; '
        f'border:1px solid var(--border-subtle); '
        f'border-left:4px solid {_cor}; '
        f'border-radius:var(--radius-sm); '
        f'padding:14px 18px; '
        f'margin:8px 0;">'

        f'<div style="'
        f'font-family:var(--font-ui); '
        f'font-size:0.75rem; '
        f'color:{_cor}; '
        f'font-weight:700; '
        f'text-transform:uppercase; '
        f'letter-spacing:.08em; '
        f'margin-bottom:6px;">'
        f'{_ic} {titulo}</div>'

        f'<div style="'
        f'font-family:var(--font-ui); '
        f'font-size:0.80rem; '
        f'color:var(--text-secondary); '
        f'line-height:1.7;">'
        f'{corpo}</div>'

        f'</div>',
        unsafe_allow_html=True,
    )


def watchlist_header_row():
    """Header da lista densa — labels das colunas."""
    cols = st.columns([1.2, 3.2, 1.5, 0.9, 0.9, 1.5, 0.6])
    labels = ["ativo", "nome / sinal", "preço", "1d", "1m", "health", ""]
    for col, label in zip(cols, labels):
        with col:
            st.markdown(
                f'<div style="font-family:var(--font-ui);'
                f' font-size:0.62rem; font-weight:600;'
                f' color:var(--text-muted);'
                f' text-transform:uppercase;'
                f' letter-spacing:0.10em;'
                f' padding-bottom:6px;'
                f' border-bottom:1px solid var(--border-normal);">'
                f'{label}</div>',
                unsafe_allow_html=True,
            )


def watchlist_row(
    ticker:        str,
    nome:          str,
    preco:         float,
    var_1d:        float,
    var_1m:        float = 0.0,
    moeda:         str   = "R$",
    health_score:  float = None,
    alertas:       list  = None,
    earnings_info: dict  = None,
    data_source:   str   = "",
    on_delete:     str   = None,   # aceito mas ignorado — chave = ticker
    on_memorial:   str   = None,   # aceito mas ignorado — chave = ticker
):
    """Linha densa de watchlist — ~52px por ativo."""
    cor_1d    = "var(--bull)" if var_1d >= 0 else "var(--bear)"
    cor_1m    = "var(--bull)" if var_1m >= 0 else "var(--bear)"
    seta_1d   = "▲" if var_1d >= 0 else "▼"
    seta_1m   = "▲" if var_1m >= 0 else "▼"
    tem_alert = bool(alertas)

    # ── Health score ─────────────────────────────────────────
    hs_html = ""
    if health_score is not None:
        hs     = int(health_score)
        cor_hs = (
            "var(--bull)"  if hs >= 65 else
            "var(--amber)" if hs >= 40 else
            "var(--bear)"
        )
        hs_html = (
            f'<div style="display:flex; align-items:center;'
            f' gap:8px;">'
            f'<div style="flex:1; background:var(--bg-overlay);'
            f' height:4px; border-radius:2px; overflow:hidden;">'
            f'<div style="width:{hs}%; height:100%;'
            f' background:{cor_hs}; border-radius:2px;'
            f' transition:width 0.3s ease;"></div></div>'
            f'<span style="font-family:var(--font-data);'
            f' font-size:0.75rem; font-weight:bold;'
            f' color:{cor_hs}; min-width:22px;">{hs}</span>'
            f'</div>'
        )

    # ── Sinal de alerta (dot + texto, até 2 linhas) ──────────
    sinal_html = ""
    if tem_alert and alertas:
        sinal_html = (
            f'<div style="display:flex; align-items:flex-start;'
            f' gap:5px; margin-top:4px;">'
            f'<span style="width:6px; height:6px;'
            f' border-radius:50%; background:var(--amber);'
            f' flex-shrink:0; margin-top:3px;'
            f' display:inline-block;"></span>'
            f'<span style="font-family:var(--font-ui);'
            f' font-size:0.68rem; color:var(--text-secondary);'
            f' line-height:1.4; overflow:hidden;'
            f' display:-webkit-box; -webkit-line-clamp:2;'
            f' -webkit-box-orient:vertical;">'
            f'{alertas[0][:80]}'
            f'</span></div>'
        )

    # ── Badge earnings ────────────────────────────────────────
    earn_html = ""
    if earnings_info and 0 <= earnings_info.get("dias", 99) <= 14:
        dias_e = earnings_info["dias"]
        cor_e  = (
            "var(--bear)"  if dias_e <= 3 else
            "var(--amber)" if dias_e <= 7 else
            "var(--text-muted)"
        )
        earn_html = (
            f'<span style="font-family:var(--font-ui);'
            f' font-size:0.58rem; font-weight:600;'
            f' color:{cor_e}; background:var(--accent-soft);'
            f' border:1px solid {cor_e}; padding:1px 5px;'
            f' border-radius:4px; margin-left:6px;'
            f' vertical-align:middle;">'
            f'res·{dias_e}d</span>'
        )

    # ── Layout 7 colunas ─────────────────────────────────────
    col_tk, col_nm, col_pr, col_1d, col_1m, col_hs, col_ac = st.columns(
        [1.2, 3.2, 1.5, 0.9, 0.9, 1.5, 0.6]
    )

    with col_tk:
        _ticker_label = ticker.replace(".SA", "")
        st.markdown(
            f'<div style="padding:11px 0 3px;">'
            f'<a href="{_ticker_nav_url(ticker)}" class="ticker-nav" '
            f'title="abrir research: {_ticker_label}">'
            f'{_ticker_label}</a>{earn_html}</div>',
            unsafe_allow_html=True,
        )

    with col_nm:
        st.markdown(
            f'<div style="font-family:var(--font-ui);'
            f' color:var(--text-secondary); font-size:0.78rem;'
            f' padding:11px 0 2px; font-weight:400;'
            f' overflow:hidden; text-overflow:ellipsis;'
            f' white-space:nowrap;">'
            f'{nome[:30]}</div>'
            f'{sinal_html}'
            f'<div style="height:4px;"></div>',
            unsafe_allow_html=True,
        )

    with col_pr:
        st.markdown(
            f'<div style="font-family:var(--font-data);'
            f' font-weight:600; color:var(--text-primary);'
            f' font-size:0.88rem; padding:11px 0 3px;">'
            f'{moeda} {preco:,.2f}{_fonte_badge(data_source)}</div>',
            unsafe_allow_html=True,
        )

    with col_1d:
        st.markdown(
            f'<div style="font-family:var(--font-data);'
            f' color:{cor_1d}; font-size:0.80rem;'
            f' padding:11px 0 3px; font-weight:600;">'
            f'{seta_1d} {abs(var_1d):.2f}%</div>',
            unsafe_allow_html=True,
        )

    with col_1m:
        st.markdown(
            f'<div style="font-family:var(--font-data);'
            f' color:{cor_1m}; font-size:0.75rem;'
            f' padding:12px 0 3px; opacity:0.75;">'
            f'{seta_1m} {abs(var_1m):.2f}%</div>',
            unsafe_allow_html=True,
        )

    with col_hs:
        if hs_html:
            st.markdown(
                f'<div style="padding:13px 0 3px;">{hs_html}</div>',
                unsafe_allow_html=True,
            )

    with col_ac:
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🗑", key=f"del_{ticker}", help="remover"):
                st.session_state[f"confirm_del_{ticker}"] = True
        with b2:
            if st.button("📊", key=f"mem_{ticker}", help="memorial"):
                st.session_state[f"show_memorial_{ticker}"] = True

    # Separador
    st.markdown(
        '<div style="height:1px; background:var(--border-subtle);'
        ' margin:0;"></div>',
        unsafe_allow_html=True,
    )


# DEPRECATED — preferir watchlist_row() para layouts de lista densa.
# Emite DeprecationWarning quando chamado. Será removido após migração das
# páginas que ainda importam (busca: grep -rn "watchlist_card" pages/).
def watchlist_card(ticker: str, nome: str, preco: float,
                   var_1d: float, moeda: str = "R$",
                   health_score: float = None,
                   alertas: list = None,
                   earnings_info: dict = None):
    """
    [DEPRECATED] Card legado da watchlist — use watchlist_row() em vez deste.
    Será removido no PR de cleanup pós-Fase 6.
    """
    _warnings.warn(
        "watchlist_card() está obsoleto — use watchlist_row() (mais denso, "
        "alinhado com o design system v5). Será removido após Fase 6.",
        DeprecationWarning,
        stacklevel=2,
    )
    cor_var   = "var(--bull)" if var_1d >= 0 else "var(--bear)"
    seta      = "▲" if var_1d >= 0 else "▼"
    tem_alert = bool(alertas)

    hs_html = ""
    if health_score is not None:
        hs     = int(health_score)
        cor_hs = (
            "var(--bull)"  if hs >= 65 else
            "var(--amber)" if hs >= 40 else
            "var(--bear)"
        )
        hs_html = (
            f'<div style="margin-top:8px;">'
            f'<div style="display:flex; justify-content:space-between;'
            f' margin-bottom:3px;">'
            f'<span style="font-family:var(--font-ui);'
            f' font-size:0.60rem; color:var(--text-muted);">health</span>'
            f'<span style="font-family:var(--font-data);'
            f' font-size:0.65rem; color:{cor_hs};'
            f' font-weight:bold;">{hs}</span></div>'
            f'<div style="background:var(--bg-overlay); height:3px;'
            f' border-radius:2px;">'
            f'<div style="background:{cor_hs}; width:{hs}%;'
            f' height:100%; border-radius:2px;"></div>'
            f'</div></div>'
        )

    alerta_html = ""
    if tem_alert and alertas:
        txt = alertas[0][:55] + "…" if len(alertas[0]) > 55 else alertas[0]
        alerta_html = (
            f'<div style="font-family:var(--font-ui);'
            f' font-size:0.65rem; color:var(--text-muted);'
            f' margin-top:5px; line-height:1.4;">{txt}</div>'
        )

    earn_html = ""
    if earnings_info and 0 <= earnings_info.get("dias", 99) <= 14:
        dias_e = earnings_info["dias"]
        cor_e  = (
            "var(--bear)"  if dias_e <= 3 else
            "var(--amber)" if dias_e <= 7 else
            "var(--text-muted)"
        )
        earn_html = (
            f'<span style="font-family:var(--font-ui);'
            f' font-size:0.58rem; color:{cor_e};'
            f' border:1px solid {cor_e}; padding:1px 4px;'
            f' border-radius:4px; margin-left:5px;'
            f' vertical-align:middle;">res·{dias_e}d</span>'
        )

    _alert_badge = (
        '<span style="font-family:var(--font-ui); font-size:0.55rem;'
        ' color:var(--bear); border:1px solid var(--bear);'
        ' padding:0 3px; border-radius:3px; margin-left:5px;">⚠</span>'
        if tem_alert else ""
    )
    st.markdown(
        f'<div style="background:var(--bg-surface);'
        f' border:1px solid var(--border-subtle);'
        f' border-radius:var(--radius-md); padding:12px 14px;'
        f' margin-bottom:6px; transition:border-color 0.15s;">'
        f'<div style="display:flex; align-items:center;'
        f' margin-bottom:4px;">'
        f'<a href="{_ticker_nav_url(ticker)}" class="ticker-nav" '
        f'style="font-size:0.85rem;" title="abrir research">'
        f'{ticker.replace(".SA", "")}</a>{earn_html}'
        f'{_alert_badge}'
        f'</div>'
        f'<div style="font-family:var(--font-ui);'
        f' font-size:0.70rem; color:var(--text-muted);'
        f' margin-bottom:6px; overflow:hidden;'
        f' text-overflow:ellipsis; white-space:nowrap;">'
        f'{nome[:28]}</div>'
        f'<div style="display:flex; justify-content:space-between;'
        f' align-items:baseline;">'
        f'<span style="font-family:var(--font-data);'
        f' font-size:1.0rem; font-weight:600;'
        f' color:var(--text-primary);">'
        f'{moeda} {preco:,.2f}</span>'
        f'<span style="font-family:var(--font-data);'
        f' font-size:0.78rem; color:{cor_var};'
        f' font-weight:600;">'
        f'{seta} {abs(var_1d):.2f}%</span>'
        f'</div>'
        f'{hs_html}'
        f'{alerta_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def empty_state(icone: str, titulo: str, descricao: str):
    """Estado vazio."""
    st.markdown(
        f'<div style="text-align:center; padding:48px 24px;">'
        f'<div style="font-size:2.2rem; margin-bottom:12px;'
        f' opacity:0.3;">{icone}</div>'
        f'<div style="font-family:var(--font-ui);'
        f' font-size:0.85rem; font-weight:600;'
        f' color:var(--text-muted); margin-bottom:6px;">'
        f'{titulo}</div>'
        f'<div style="font-family:var(--font-ui);'
        f' font-size:0.75rem; color:var(--text-muted);'
        f' max-width:280px; margin:0 auto;'
        f' line-height:1.6; opacity:0.6;">'
        f'{descricao}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def progress_steps(steps: list[str], current: int):
    """Progress steps."""
    items = "".join([
        f'<div style="display:flex; align-items:center;'
        f' gap:5px; font-family:var(--font-ui);'
        f' font-size:0.68rem; font-weight:500;'
        f' color:{"var(--bull)" if i < current else ("var(--accent)" if i == current else "var(--text-muted)")};">'
        f'<span>{"✓" if i < current else ("●" if i == current else "○")}</span>'
        f'<span>{s}</span>'
        f'</div>'
        for i, s in enumerate(steps)
    ])
    st.markdown(
        f'<div style="display:flex; gap:20px; padding:8px 0;'
        f' border-bottom:1px solid var(--border-subtle);'
        f' margin-bottom:14px;">{items}</div>',
        unsafe_allow_html=True,
    )


def kpi_row(itens: list[dict]):
    """
    Linha de KPIs.
    itens: [{'label': str, 'valor': str, 'cor': str}, ...]
    """
    CORES = {
        "bull":  "var(--bull)",
        "bear":  "var(--bear)",
        "amber": "var(--amber)",
        "info":  "var(--info)",
        "muted": "var(--text-muted)",
    }
    cols = st.columns(len(itens))
    for i, (item, col) in enumerate(zip(itens, cols)):
        cor    = CORES.get(item.get("cor", "muted"), "var(--text-muted)")
        borda  = "border-right:1px solid var(--border-subtle);" if i < len(itens) - 1 else ""
        with col:
            st.markdown(
                f'<div style="padding:4px 12px; {borda}">'
                f'<div style="font-family:var(--font-ui);'
                f' font-size:0.62rem; font-weight:600;'
                f' color:var(--text-muted); text-transform:uppercase;'
                f' letter-spacing:0.08em; margin-bottom:3px;">'
                f'{item["label"]}</div>'
                f'<div style="font-family:var(--font-data);'
                f' font-size:0.95rem; font-weight:bold;'
                f' color:{cor};">{item["valor"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def auto_refresh_indicator(minutos_cache: int = 5):
    """Indicador de sync."""
    st.markdown(
        f'<div style="font-family:var(--font-ui);'
        f' font-size:0.62rem; color:var(--text-muted);'
        f' text-align:right; margin-bottom:6px; opacity:0.7;">'
        f'↻ {time.strftime("%H:%M")} · cache {minutos_cache}m'
        f'</div>',
        unsafe_allow_html=True,
    )


def inject_ui_enhancements():
    """
    Injeta melhorias de UX globais em todas as páginas:

    • Command palette  (Ctrl+K / ⌘K) — busca tickers B3/FII/EUA e navega entre
      páginas sem sair do teclado.  Fuzzy-match, seleção por ↑↓ e Enter.
    • Toast notifications — window.parent._fintermToast(msg, type, ms)
      Chame show_toast() no Python para acionar.
    • Keyboard shortcuts:
        Alt+1 → Portfolio      Alt+2 → Research
        Alt+3 → Discovery      Alt+4 → Macro
        Alt+5 → Configurações  Alt+6 → Backfill
        Enter → clica botão primário (comportamento legado)
    """
    import json
    from utils.tickers import SCREENER_B3, SCREENER_US, FII_TODOS

    # Tickers para o command palette (limpa sufixo .SA para exibição)
    tickers_b3  = [{"t": t.replace(".SA", ""), "f": "🇧🇷", "full": t} for t in SCREENER_B3]
    tickers_fii = [{"t": t.replace(".SA", ""), "f": "🏢",  "full": t} for t in FII_TODOS]
    tickers_us  = [{"t": t,                    "f": "🇺🇸", "full": t} for t in SCREENER_US]
    tickers_json = json.dumps(tickers_b3 + tickers_fii + tickers_us)

    pages_json = json.dumps([
        {"label": "Portfolio",     "icon": "📊", "nav": "Portfolio",     "key": "1"},
        {"label": "Research",      "icon": "🔬", "nav": "Research",      "key": "2"},
        {"label": "Discovery",     "icon": "🔍", "nav": "Discovery",     "key": "3"},
        {"label": "Macro",         "icon": "🌐", "nav": "Macro",         "key": "4"},
        {"label": "Configurações", "icon": "⚙️", "nav": "Configuracoes", "key": "5"},
        {"label": "Backfill",      "icon": "🗄️", "nav": "Backfill",      "key": "6"},
    ])

    # IMPORTANTE: st.markdown() NÃO executa <script> no Streamlit moderno (React
    # sanitiza innerHTML). Usar st.components.v1.html() que cria iframe real onde
    # scripts executam. O JS usa window.parent para acessar o DOM do Streamlit.
    import streamlit.components.v1 as _comp
    _comp.html(f"""
<script>
(function() {{
    var doc = window.parent.document;
    if (window.parent._fintermInit) return;
    window.parent._fintermInit = true;

    var TICKERS = {tickers_json};
    var PAGES   = {pages_json};

    /* ── CSS ── */
    if (!doc.getElementById('finterm-ux-css')) {{
        var css = doc.createElement('style');
        css.id  = 'finterm-ux-css';
        css.textContent = `
        #finterm-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.72);
            z-index:99998;backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px);}}
        #finterm-overlay.active{{display:flex;align-items:flex-start;
            justify-content:center;padding-top:14vh;animation:ft-fade var(--motion-fast) var(--ease-out);}}
        #finterm-palette{{background:var(--bg-surface);border:1px solid var(--border-normal);
            border-radius:var(--radius-lg);width:min(620px,92vw);
            box-shadow:var(--shadow-xl),0 0 0 1px var(--accent-border);overflow:hidden;
            animation:ft-slide .16s cubic-bezier(.16,1,.3,1);}}
        #finterm-input{{width:100%;background:transparent;border:none;
            border-bottom:1px solid var(--border-subtle);padding:var(--space-4) var(--space-5);
            color:var(--text-primary);font-size:var(--text-md);font-family:var(--font-ui);
            outline:none;box-sizing:border-box;}}
        #finterm-input::placeholder{{color:var(--text-muted);}}
        #finterm-hint{{padding:5px var(--space-5);font-size:var(--text-xs);color:var(--text-muted);
            font-family:var(--font-ui);border-bottom:1px solid var(--border-subtle);
            display:flex;gap:14px;align-items:center;}}
        .ft-k{{background:var(--bg-elevated);border:1px solid var(--border-normal);border-radius:var(--radius-sm);
            padding:1px 5px;font-family:var(--font-data);
            font-size:.6rem;color:var(--text-secondary);margin-right:2px;}}
        #finterm-results{{max-height:340px;overflow-y:auto;padding:6px;}}
        #finterm-results::-webkit-scrollbar{{width:4px;}}
        #finterm-results::-webkit-scrollbar-thumb{{background:var(--border-normal);border-radius:2px;}}
        .ft-section{{font-size:.58rem;color:var(--text-muted);padding:6px 14px 2px;
            text-transform:uppercase;letter-spacing:var(--ls-wide);
            font-family:var(--font-ui);}}
        .ft-item{{display:flex;align-items:center;gap:var(--space-3);padding:10px 14px;
            border-radius:var(--radius-sm);cursor:pointer;transition:background var(--motion-fast);
            font-family:var(--font-ui);}}
        .ft-item:hover,.ft-item.sel{{background:var(--bg-elevated);}}
        .ft-icon{{font-size:.95rem;width:22px;text-align:center;flex-shrink:0;}}
        .ft-main{{flex:1;min-width:0;}}
        .ft-ticker{{font-family:var(--font-data);font-size:var(--text-sm);
            font-weight:600;color:var(--text-primary);}}
        .ft-desc{{font-size:.68rem;color:var(--text-muted);margin-top:1px;}}
        .ft-badge{{font-size:.6rem;padding:2px 7px;border-radius:var(--radius-sm);
            background:var(--border-subtle);color:var(--text-secondary);flex-shrink:0;
            font-family:var(--font-data);}}
        .ft-badge.page{{background:var(--pill-accent-bg);color:var(--accent);}}
        #finterm-footer{{padding:var(--space-2) var(--space-5);border-top:1px solid var(--border-subtle);
            display:flex;gap:var(--space-4);align-items:center;font-size:var(--text-xs);
            color:var(--text-muted);font-family:var(--font-ui);}}
        #finterm-toasts{{position:fixed;top:20px;right:20px;z-index:99999;
            display:flex;flex-direction:column;gap:var(--space-2);pointer-events:none;}}
        .ft-toast{{background:var(--bg-surface);border:1px solid var(--border-normal);border-radius:var(--radius-md);
            padding:12px 16px;min-width:240px;max-width:340px;
            box-shadow:var(--shadow-lg);display:flex;
            align-items:flex-start;gap:10px;animation:ft-tin .22s ease;
            pointer-events:all;overflow:hidden;position:relative;
            font-family:var(--font-ui);}}
        .ft-toast.out{{animation:ft-tout .18s ease forwards;}}
        .ft-toast-icon{{font-size:.95rem;flex-shrink:0;margin-top:1px;}}
        .ft-toast-msg{{font-size:var(--text-sm);color:var(--text-primary);line-height:1.4;}}
        .ft-bar-wrap{{position:absolute;bottom:0;left:0;right:0;height:2px;
            background:rgba(255,255,255,.08);}}
        .ft-bar{{height:100%;transition:width linear;width:100%;}}
        .ft-toast.success{{border-left:3px solid var(--bull);}}
        .ft-toast.success .ft-bar{{background:var(--bull);}}
        .ft-toast.error{{border-left:3px solid var(--bear);}}
        .ft-toast.error .ft-bar{{background:var(--bear);}}
        .ft-toast.warning{{border-left:3px solid var(--amber);}}
        .ft-toast.warning .ft-bar{{background:var(--amber);}}
        .ft-toast.info{{border-left:3px solid var(--info);}}
        .ft-toast.info .ft-bar{{background:var(--info);}}
        .ft-hint-badge{{position:fixed;bottom:76px;right:20px;z-index:9998;
            background:var(--bg-surface);border:1px solid var(--border-normal);border-radius:var(--radius-sm);
            padding:var(--space-2) var(--space-3);font-size:.65rem;color:var(--text-secondary);
            font-family:var(--font-ui);pointer-events:none;
            box-shadow:var(--shadow-md);
            animation:ft-badge-show 4s ease 1.5s both;}}
        @keyframes ft-fade  {{from{{opacity:0}}to{{opacity:1}}}}
        @keyframes ft-slide {{from{{opacity:0;transform:translateY(-14px) scale(.97)}}
                               to{{opacity:1;transform:translateY(0) scale(1)}}}}
        @keyframes ft-tin   {{from{{opacity:0;transform:translateX(20px)}}
                               to{{opacity:1;transform:translateX(0)}}}}
        @keyframes ft-tout  {{from{{opacity:1;transform:translateX(0)}}
                               to{{opacity:0;transform:translateX(20px)}}}}
        @keyframes ft-badge-show{{
            0%{{opacity:0;transform:translateY(6px)}}
            10%{{opacity:1;transform:translateY(0)}}
            80%{{opacity:1}}100%{{opacity:0}}}}
        `;
        doc.head.appendChild(css);
    }}

    /* ── DOM ── */
    if (!doc.getElementById('finterm-overlay')) {{
        var ov = doc.createElement('div');
        ov.id  = 'finterm-overlay';
        ov.innerHTML =
            '<div id="finterm-palette">' +
            '  <input id="finterm-input" type="text"' +
            '   placeholder="🔍  buscar ticker ou página..." autocomplete="off"/>' +
            '  <div id="finterm-hint">' +
            '    <span><span class="ft-k">↑↓</span> navegar</span>' +
            '    <span><span class="ft-k">↵</span> selecionar</span>' +
            '    <span><span class="ft-k">Esc</span> fechar</span>' +
            '    <span style="margin-left:auto;"><span class="ft-k">Ctrl</span>+<span class="ft-k">K</span> abre</span>' +
            '  </div>' +
            '  <div id="finterm-results"></div>' +
            '  <div id="finterm-footer">' +
            '    <span style="color:var(--accent);font-weight:600;">⚡ FINTERMINAL</span>' +
            '    <span style="margin-left:auto;">Alt+1–6 navegação rápida de páginas</span>' +
            '  </div>' +
            '</div>';
        doc.body.appendChild(ov);

        var tc = doc.createElement('div');
        tc.id  = 'finterm-toasts';
        doc.body.appendChild(tc);

        var hb = doc.createElement('div');
        hb.className = 'ft-hint-badge';
        hb.innerHTML = '<span style="color:var(--accent)">Ctrl+K</span> command palette';
        doc.body.appendChild(hb);
    }}

    /* ── VARS ── */
    var ov      = doc.getElementById('finterm-overlay');
    var inp     = doc.getElementById('finterm-input');
    var res     = doc.getElementById('finterm-results');
    var selIdx  = -1;
    var items   = [];

    /* ── NAVIGATION ── */
    function navPage(navLabel) {{
        var links = doc.querySelectorAll('[data-testid="stSidebarNavLink"]');
        for (var i = 0; i < links.length; i++) {{
            if (links[i].textContent.trim().indexOf(navLabel) !== -1) {{
                links[i].click(); return;
            }}
        }}
        window.parent.location.href =
            window.parent.location.origin + '/' + navLabel;
    }}

    function navTicker(ticker) {{
        var links = doc.querySelectorAll('[data-testid="stSidebarNavLink"]');
        var researchHref = '';
        for (var i = 0; i < links.length; i++) {{
            if (links[i].textContent.trim().indexOf('Research') !== -1) {{
                researchHref = links[i].href || ''; break;
            }}
        }}
        var base = researchHref ||
            (window.parent.location.origin + '/Research');
        // Strip query params from base before adding ours
        base = base.split('?')[0];
        window.parent.location.href =
            base + '?research_ticker=' + encodeURIComponent(ticker);
    }}

    /* ── FUZZY MATCH ── */
    function fuzzy(q, text) {{
        q = q.toLowerCase(); text = text.toLowerCase();
        if (text.startsWith(q)) return 200;
        if (text.includes(q))  return 100;
        var qi = 0;
        for (var i = 0; i < text.length && qi < q.length; i++)
            if (text[i] === q[qi]) qi++;
        return qi === q.length ? 10 : 0;
    }}

    /* ── RENDER ── */
    var POPULAR = ['PETR4','VALE3','ITUB4','BBAS3','WEGE3','ELET3','AAPL','NVDA','MSFT','TSLA'];

    function renderResults(q) {{
        q = q.trim();
        items = [];
        var html = '';

        if (!q) {{
            html += '<div class="ft-section">páginas</div>';
            PAGES.forEach(function(p) {{
                html += '<div class="ft-item" data-i="' + items.length + '">' +
                    '<span class="ft-icon">' + p.icon + '</span>' +
                    '<span class="ft-main"><span class="ft-ticker">' + p.label + '</span></span>' +
                    '<span class="ft-badge page">Alt+' + p.key + '</span></div>';
                items.push({{type:'page', nav:p.nav}});
            }});
            html += '<div class="ft-section" style="margin-top:6px">tickers recentes</div>';
            POPULAR.forEach(function(t) {{
                var found = null;
                for (var i = 0; i < TICKERS.length; i++)
                    if (TICKERS[i].t === t) {{ found = TICKERS[i]; break; }}
                if (!found) return;
                html += '<div class="ft-item" data-i="' + items.length + '">' +
                    '<span class="ft-icon">' + found.f + '</span>' +
                    '<span class="ft-main"><span class="ft-ticker">' + found.t + '</span>' +
                    '<span class="ft-desc">abrir em Research</span></span>' +
                    '<span class="ft-badge">ticker</span></div>';
                items.push({{type:'ticker', ticker:found.full}});
            }});
        }} else {{
            var pageHits = PAGES.filter(function(p) {{ return fuzzy(q, p.label) > 0; }});
            var tickerHits = TICKERS
                .map(function(tk) {{ return {{tk:tk, score:fuzzy(q, tk.t)}}; }})
                .filter(function(x) {{ return x.score > 0; }})
                .sort(function(a,b) {{ return b.score - a.score; }})
                .slice(0, 9)
                .map(function(x) {{ return x.tk; }});

            if (pageHits.length) {{
                html += '<div class="ft-section">páginas</div>';
                pageHits.forEach(function(p) {{
                    html += '<div class="ft-item" data-i="' + items.length + '">' +
                        '<span class="ft-icon">' + p.icon + '</span>' +
                        '<span class="ft-main"><span class="ft-ticker">' + p.label + '</span></span>' +
                        '<span class="ft-badge page">página</span></div>';
                    items.push({{type:'page', nav:p.nav}});
                }});
            }}
            if (tickerHits.length) {{
                if (pageHits.length) html += '<div class="ft-section" style="margin-top:6px">tickers</div>';
                tickerHits.forEach(function(tk) {{
                    html += '<div class="ft-item" data-i="' + items.length + '">' +
                        '<span class="ft-icon">' + tk.f + '</span>' +
                        '<span class="ft-main"><span class="ft-ticker">' + tk.t + '</span>' +
                        '<span class="ft-desc">abrir em Research</span></span>' +
                        '<span class="ft-badge">ticker</span></div>';
                    items.push({{type:'ticker', ticker:tk.full}});
                }});
            }}
            if (!pageHits.length && !tickerHits.length) {{
                html = '<div style="padding:24px;text-align:center;color:var(--text-muted);' +
                    'font-size:var(--text-sm);font-family:var(--font-ui);">nenhum resultado para \\"' + q + '\\"</div>';
            }}
        }}

        res.innerHTML = html;
        selIdx = -1;

        res.querySelectorAll('.ft-item').forEach(function(el) {{
            el.addEventListener('click', function() {{
                var i = parseInt(el.getAttribute('data-i'));
                selectItem(i);
            }});
            el.addEventListener('mouseenter', function() {{
                setSelected(parseInt(el.getAttribute('data-i')));
            }});
        }});
    }}

    function setSelected(idx) {{
        res.querySelectorAll('.ft-item').forEach(function(el, i) {{
            el.classList.toggle('sel', i === idx);
        }});
        selIdx = idx;
        // Scroll into view
        var els = res.querySelectorAll('.ft-item');
        if (els[idx]) els[idx].scrollIntoView({{block:'nearest'}});
    }}

    function selectItem(idx) {{
        if (idx < 0 || idx >= items.length) return;
        var item = items[idx];
        closePalette();
        if (item.type === 'page')   navPage(item.nav);
        if (item.type === 'ticker') navTicker(item.ticker);
    }}

    function openPalette() {{
        ov.classList.add('active');
        inp.value = ''; renderResults('');
        setTimeout(function() {{ inp.focus(); }}, 60);
    }}
    function closePalette() {{
        ov.classList.remove('active');
        selIdx = -1;
    }}

    inp.addEventListener('input', function() {{ renderResults(inp.value); }});
    ov.addEventListener('click', function(e) {{
        if (e.target === ov) closePalette();
    }});

    /* ── TOAST SYSTEM ── */
    var ICONS = {{success:'✅', error:'❌', warning:'⚠️', info:'ℹ️'}};
    window.parent._fintermToast = function(msg, type, duration) {{
        type     = type     || 'info';
        duration = duration || 3000;
        var cont = doc.getElementById('finterm-toasts');
        if (!cont) return;
        var t = doc.createElement('div');
        t.className = 'ft-toast ' + type;
        t.innerHTML =
            '<span class="ft-toast-icon">' + (ICONS[type]||'ℹ️') + '</span>' +
            '<div class="ft-toast-msg">' + msg + '</div>' +
            '<div class="ft-bar-wrap"><div class="ft-bar"></div></div>';
        cont.appendChild(t);
        var bar = t.querySelector('.ft-bar');
        requestAnimationFrame(function() {{
            bar.style.transition = 'width ' + duration + 'ms linear';
            bar.style.width = '0%';
        }});
        setTimeout(function() {{
            t.classList.add('out');
            setTimeout(function() {{ t.remove(); }}, 200);
        }}, duration);
    }};

    /* ── KEYBOARD SHORTCUTS ── */
    doc.addEventListener('keydown', function(e) {{
        var open = ov.classList.contains('active');

        // Ctrl+K / ⌘K
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {{
            e.preventDefault();
            open ? closePalette() : openPalette();
            return;
        }}

        if (open) {{
            if (e.key === 'Escape')    {{ e.preventDefault(); closePalette(); return; }}
            if (e.key === 'ArrowDown') {{
                e.preventDefault();
                setSelected(Math.min(selIdx + 1, items.length - 1));
                return;
            }}
            if (e.key === 'ArrowUp') {{
                e.preventDefault();
                setSelected(Math.max(selIdx - 1, 0));
                return;
            }}
            if (e.key === 'Enter') {{
                e.preventDefault();
                selectItem(selIdx >= 0 ? selIdx : 0);
                return;
            }}
            return;
        }}

        // Alt+1-6 → page shortcuts
        if (e.altKey && !e.ctrlKey && !e.shiftKey) {{
            var pi = parseInt(e.key) - 1;
            if (pi >= 0 && pi < PAGES.length) {{
                e.preventDefault();
                navPage(PAGES[pi].nav);
                return;
            }}
        }}

        // Enter → primary button (legado)
        if (e.key === 'Enter' && !e.ctrlKey && !e.altKey) {{
            var focused = doc.activeElement;
            var isInput = focused && (focused.tagName==='INPUT' ||
                focused.tagName==='TEXTAREA' || focused.tagName==='SELECT');
            if (!isInput) {{
                var btns = doc.querySelectorAll('[data-testid="stBaseButton-primary"]');
                if (btns.length > 0) btns[0].click();
            }}
        }}
    }});
}})();
</script>
""", height=0, scrolling=False)


def inject_keyboard_shortcuts():
    """Retrocompatibilidade — chama inject_ui_enhancements()."""
    inject_ui_enhancements()


def show_toast(message: str, type: str = "success", duration: int = 3000) -> None:
    """
    Exibe uma notificação toast animada no canto superior direito.

    Parâmetros
    ----------
    message  : texto da notificação (HTML básico permitido).
    type     : 'success' | 'error' | 'warning' | 'info'
    duration : tempo em ms antes de auto-fechar (padrão 3 000 ms).

    Requer que inject_ui_enhancements() (ou inject_keyboard_shortcuts())
    tenha sido chamado na mesma página antes de show_toast().
    """
    import streamlit.components.v1 as _comp
    msg_safe = (
        message
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", " ")
    )
    _comp.html(
        f"<script>(function(){{"
        f"  if (window.parent._fintermToast)"
        f"    window.parent._fintermToast('{msg_safe}','{type}',{duration});"
        f"}})();</script>",
        height=0,
        scrolling=False,
    )


# ── DICIONÁRIO CENTRAL DE TOOLTIPS ────────────────────────────────────
TOOLTIPS: dict[str, str] = {

    # ── Health Score ──────────────────────────────────────────────────
    "health_score": (
        "score composto de 0-100 calculado pelo motor quantitativo. "
        "combina: piotroski f-score (qualidade de balanço), "
        "roic vs wacc (geração de valor), momentum 12-1m, "
        "valuation setorial, solvência e dados macro. "
        "≥65: acumulação | 40-64: manutenção | <40: reduzir."
    ),
    "piotroski": (
        "f-score de joseph piotroski (2000): 9 critérios binários "
        "de qualidade fundamentalista. avalia rentabilidade (roa, fcf), "
        "alavancagem (dívida, liquidez) e eficiência operacional "
        "(margem bruta, giro de ativos). "
        "7-9: balanço de alta qualidade | 3-6: médio | 0-2: fraco."
    ),
    "roic": (
        "return on invested capital: nopat / capital investido. "
        "mede se a empresa gera retorno acima do custo de capital (wacc). "
        "roic > wacc = empresa cria valor. "
        "roic < wacc = empresa destrói valor mesmo com lucro contábil. "
        "br: wacc ≈ selic + 7.5% | eua: wacc ≈ treasury 10y + 5.5%."
    ),
    "wacc": (
        "weighted average cost of capital: custo médio ponderado de capital. "
        "representa o retorno mínimo que a empresa precisa gerar para "
        "remunerar acionistas e credores. "
        "br: 60% equity (selic+7.5%) + 40% dívida (selic×0.66). "
        "eua: 60% equity (treasury10y+5.5%) + 40% dívida (treasury10y×0.79)."
    ),
    "momentum_12_1": (
        "retorno do ativo de 12 meses atrás até 1 mês atrás "
        "(exclui o último mês para evitar reversão de curto prazo). "
        "fator acadêmico robusto: jegadeesh & titman (1993). "
        "momentum forte historicamente prediz continuação de alta. "
        "momentum negativo severo indica tendência baixista estrutural."
    ),
    "icr": (
        "interest coverage ratio: ebit / despesas financeiras. "
        "mede quantas vezes o lucro operacional cobre os juros da dívida. "
        "≥5x: confortável | 3-5x: adequado | 1.5-3x: atenção | "
        "<1.5x: risco de insolvência. crítico em ambientes de juro alto."
    ),
    "net_debt_ebitda": (
        "dívida líquida (dívida bruta - caixa) dividida pelo ebitda. "
        "indica quantos anos de geração de caixa operacional "
        "são necessários para pagar a dívida. "
        "br conservador: <1.5x | moderado: 1.5-3x | agressivo: >4x. "
        "mais preciso que d/e bruto pois desconta o caixa disponível."
    ),

    # ── Valuation ─────────────────────────────────────────────────────
    "pl": (
        "preço / lucro: quanto o mercado paga por cada real de lucro. "
        "p/l baixo pode indicar desconto ou baixas expectativas de crescimento. "
        "p/l alto pode indicar crescimento esperado ou sobrevalorização. "
        "sempre compare com o setor e o histórico da própria empresa."
    ),
    "pvp": (
        "preço / valor patrimonial: quanto o mercado paga "
        "por cada real de patrimônio líquido contábil. "
        "p/vp < 1: ativo cotado abaixo do valor contábil (desconto). "
        "p/vp > 1: mercado precifica crescimento acima do patrimônio. "
        "para fiis: p/vp próximo de 0.85-0.95 = zona de oportunidade."
    ),
    "ev_ebitda": (
        "enterprise value / ebitda: valor da empresa (incluindo dívida) "
        "dividido pelo lucro operacional antes de juros, impostos e depreciação. "
        "permite comparar empresas com estruturas de capital diferentes. "
        "setores industriais: <8x barato | 8-14x justo | >20x caro. "
        "tech pode justificar múltiplos mais altos pelo crescimento."
    ),
    "dy": (
        "dividend yield: dividendo por ação / preço da ação × 100. "
        "indica a rentabilidade do dividendo em relação ao preço pago. "
        "para ações br: compare com selic (prêmio mínimo de 2-3pp). "
        "para fiis: compare com ntn-b real (prêmio mínimo de 1.5-2.5pp). "
        "dy muito alto (>15%) pode indicar yield trap — verifique sustentabilidade."
    ),
    "roe": (
        "return on equity: lucro líquido / patrimônio líquido × 100. "
        "mede a rentabilidade sobre o capital dos acionistas. "
        ">20%: excelente | 10-20%: bom | <10%: medíocre | negativo: destruindo valor. "
        "atenção: roe alto com alavancagem excessiva pode ser enganoso."
    ),
    "margem_liquida": (
        "lucro líquido / receita líquida × 100. "
        "mede quanto da receita se converte em lucro após todos os custos. "
        ">15%: alta eficiência | 5-15%: adequado | <5%: baixa margem. "
        "varia muito por setor: varejo tem margens baixas por design, "
        "enquanto software e farmacêutico têm margens estruturalmente altas."
    ),

    # ── FII específico ─────────────────────────────────────────────────
    "ntnb_spread": (
        "spread do dividend yield real do fii sobre a ntn-b (ipca+). "
        "a ntn-b é o benchmark correto para fiis — não a selic. "
        "spread positivo: fii remunera acima do título público sem risco. "
        "spread negativo: fii perde do título público — sem prêmio de risco. "
        "mínimo aceitável: +1.5pp (papel) a +2.5pp (tijolo/shopping)."
    ),
    "pvp_fii": (
        "para fiis, o p/vp tem interpretação diferente das ações. "
        "0.80-0.95: zona de oportunidade — desconto saudável ao nav. "
        "0.95-1.05: negociando próximo ao valor patrimonial — justo. "
        ">1.20: ágio elevado — exige crescimento forte dos proventos. "
        "<0.70: desconto crítico — mercado precifica problemas graves."
    ),
    "segmento_fii": (
        "segmento do fii determina os múltiplos justos e o risco. "
        "papel (cri/cra): menor volatilidade, sensível a juros. "
        "logística: demanda crescente, contratos longos, estável. "
        "lajes corporativas: dependente de vacância e ciclo econômico. "
        "shopping: recuperação pós-covid, sensível ao consumo. "
        "fof: diversificado, taxa dupla (gestão + fiis investidos)."
    ),

    # ── Macro indicadores ──────────────────────────────────────────────
    "selic": (
        "taxa básica de juros brasileira definida pelo copom (bacen). "
        "referência para toda a curva de juros e para o custo de capital. "
        "selic alta: penaliza ações de crescimento e fiis (duration longa), "
        "favorece renda fixa e exportadores. "
        "selic >10%: regime de juros altos — exige prêmio de risco maior."
    ),
    "vix": (
        "cboe volatility index: volatilidade implícita do s&p500. "
        "mede o 'medo' do mercado americano nos próximos 30 dias. "
        "<15: complacência / ganância. 15-25: neutro. "
        ">25: stress. >35: pânico / crise. "
        "historicamente, vix >30 é oportunidade de compra em 6-12 meses. "
        "vix alto + beta alto = penalidade dupla no health score."
    ),
    "ipca": (
        "índice de preços ao consumidor amplo: inflação oficial brasileira. "
        "meta bcb: 3% ± 1.5pp (teto: 4.5%). "
        "ipca acima do teto pressiona o copom a manter/elevar a selic. "
        "impacto direto no yield real de fiis e na correção de contratos. "
        "ipca acumulado 12m é mais relevante que a leitura mensal."
    ),
    "yield_curve": (
        "spread entre o treasury americano de 10 anos e o de 2 anos. "
        "curva normal (positiva): 10y > 2y — economia saudável. "
        "curva invertida (negativa): 10y < 2y — sinal recessivo. "
        "100% das recessões americanas desde 1955 foram precedidas "
        "por inversão da curva com antecedência de 6-18 meses (nber). "
        "inversão não garante recessão — mas é o melhor predictor existente."
    ),
    "treasury_10y": (
        "yield do título soberano americano de 10 anos. "
        "benchmark global de 'risk-free rate'. "
        "alta do treasury pressiona p/l de ações de crescimento "
        "(efeito duration: fluxos futuros valem menos). "
        "spread treasury vs juro local indica fluxo de capital emergente. "
        "treasury alto + dólar forte = saída de capital de emergentes."
    ),
    "fear_greed": (
        "índice proprietário de sentimento de mercado (0-100). "
        "componentes: momentum do índice, força do vix (invertida), "
        "posição no range 52 semanas, nasdaq vs s&p500, "
        "ouro como safe haven, ratio vix/volatilidade realizada. "
        "0-25: medo extremo (oportunidade histórica). "
        "75-100: ganância extrema (risco de correção). "
        "extremos de medo historicamente precedem altas."
    ),
    "spread_btp_bund": (
        "spread entre o btp italiano e o bund alemão de 10 anos. "
        "o bund é o ativo livre de risco europeu. "
        "spread mede o prêmio de risco exigido para financiar a itália. "
        "<1.5pp: calmo. 1.5-2.5pp: atenção. >2.5pp: stress. "
        "crise do euro 2011-2012: spread chegou a 5pp. "
        "bce pode ativar omt (outright monetary transactions) se necessário."
    ),

    # ── Portfolio ─────────────────────────────────────────────────────
    "correlacao": (
        "correlação de pearson entre retornos diários dos ativos (-1 a +1). "
        "+1: movem-se identicamente (sem diversificação). "
        "0: independentes (diversificação máxima). "
        "-1: movem-se inversamente (hedge perfeito). "
        "acima de 0.70: alta correlação — risco de concentração oculta. "
        "portfólio bem diversificado tem correlação média próxima de 0.2-0.4."
    ),
    "beta": (
        "sensibilidade do ativo às variações do benchmark (ibov ou s&p500). "
        "beta=1: move igual ao mercado. beta>1: mais volátil que o mercado. "
        "beta<1: menos volátil (defensivo). beta negativo: move inversamente. "
        "beta >1.5 em cenário de vix alto gera penalidade no health score. "
        "calculado empiricamente via regressão dos retornos diários (252d)."
    ),
    "sharpe": (
        "retorno excedente (acima do risk-free) por unidade de risco (desvio padrão). "
        "sharpe = (retorno - selic/cdi) / volatilidade anualizada. "
        ">1.0: bom. >2.0: excelente. <0: retorno abaixo do risk-free. "
        "permite comparar ativos com volatilidades diferentes. "
        "usa selic como risk-free para ativos br."
    ),
    "drawdown": (
        "queda máxima percentual do pico ao vale em um período. "
        "ex: drawdown de -35% significa que o ativo caiu 35% "
        "do seu ponto mais alto antes de se recuperar. "
        "mede o risco real que o investidor enfrentou. "
        "drawdown alto + recovery longo = ativo de alto risco real."
    ),
    "score_assimetria": (
        "score composto 0-100 do radar de oportunidades. "
        "componentes: health score (55%) + valuation histórico fmp (20%) "
        "+ timing de entrada — rsi, micro-recuperação e distância do topo (25%). "
        "identifica ativos de qualidade com preço temporariamente deprimido "
        "e sinais de estabilização — não trend following."
    ),

    # ── Ciclo econômico ────────────────────────────────────────────────
    "ciclo_expansao": (
        "fase de expansão: pib crescendo acima do potencial, "
        "mercado de trabalho aquecido, lucros corporativos em alta. "
        "historicamente dura 4-7 anos (nber). "
        "setores favorecidos: tecnologia, consumo discricionário, "
        "indústria, financeiro. "
        "estratégia: sobrepeso em cíclicos de qualidade."
    ),
    "ciclo_pico": (
        "fase de pico: crescimento máximo mas desacelerando. "
        "inflação no teto, banco central aperta política monetária. "
        "margens de lucro começam a ser comprimidas. "
        "historicamente dura 6-18 meses. "
        "setores favorecidos: energia, materiais, saúde. "
        "estratégia: rotação para defensivos e commodities."
    ),
    "ciclo_contracao": (
        "fase de contração/recessão: pib crescendo abaixo do potencial "
        "ou em queda. desemprego subindo, lucros caindo. "
        "banco central inicia ciclo de corte. "
        "historicamente dura 8-16 meses (nber: média 11m). "
        "setores favorecidos: consumo básico, saúde, utilities. "
        "estratégia: máximo defensivo, renda fixa, caixa."
    ),
    "ciclo_vale": (
        "fase de vale: crescimento no mínimo, banco central estimulando. "
        "ativos de risco extremamente descontados. "
        "historicamente o melhor momento para acumular cíclicos de qualidade. "
        "fase mais curta do ciclo — janela de entrada estreita. "
        "setores favorecidos: tecnologia, construção, consumo discricionário. "
        "estratégia: agressiva — máximo peso em risco."
    ),
}


def tooltip(chave: str = "", texto_custom: str = "") -> None:
    _texto = TOOLTIPS.get(chave, texto_custom)
    if not _texto:
        return
    _texto_esc = (
        _texto
        .replace('"', '&quot;')
        .replace("'", "&#39;")
    )
    st.markdown(
        f'<span title="{_texto_esc}" style="'
        f'cursor:help;'
        f'color:var(--text-muted);'
        f'font-size:var(--text-xs);'
        f'border:1px solid var(--border-normal);'
        f'border-radius:50%;'
        f'padding:0 5px;'
        f'margin-left:4px;'
        f'font-family:var(--font-data);'
        f'user-select:none;'
        f'vertical-align:middle;'
        f'">?</span>',
        unsafe_allow_html=True,
    )


def label_com_tooltip(
    texto: str,
    chave: str = "",
    texto_custom: str = "",
    cor: str | None = None,
    tamanho: str = "0.72rem",
) -> None:
    """
    cor: None (padrão) usa var(--text-secondary). Passe um CSS color custom
    apenas se precisar destacar o label (ex: 'var(--accent)').
    """
    _cor = cor if cor else "var(--text-secondary)"
    _texto_tt = TOOLTIPS.get(chave, texto_custom)
    _tt_esc = (
        _texto_tt
        .replace('"', '&quot;')
        .replace("'", "&#39;")
    ) if _texto_tt else ""

    _tt_html = (
        f' <span title="{_tt_esc}" style="'
        f'cursor:help;color:var(--text-muted);font-size:0.6rem;'
        f'border:1px solid var(--border-normal);border-radius:50%;'
        f'padding:0 4px;margin-left:2px;'
        f'font-family:var(--font-data);user-select:none;">?</span>'
    ) if _tt_esc else ""

    st.markdown(
        f'<div style="font-family:var(--font-ui);'
        f'font-size:{tamanho};color:{_cor};'
        f'margin-bottom:4px;">'
        f'{texto}{_tt_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# NOVOS COMPONENTES — v4.0
# ══════════════════════════════════════════════════════════════════════════════

def metric_card_compact(
    label: str,
    valor: str,
    delta: str | None = None,
    cor: str = "info",
) -> None:
    """Card compacto (h≈64px) para linhas densas com 4-6 métricas lado a lado."""
    _COR_MAP = {
        "bull":  ("var(--bull)",  "var(--bull-soft)"),
        "bear":  ("var(--bear)",  "var(--bear-soft)"),
        "amber": ("var(--amber)", "var(--amber-soft)"),
        "info":  ("var(--info)",  "var(--info-soft)"),
        "muted": ("var(--text-muted)", "transparent"),
    }
    cor_val, cor_bg = _COR_MAP.get(cor, _COR_MAP["info"])
    delta_html = ""
    if delta is not None:
        delta_html = (
            f'<span style="font-size:.68rem;font-family:var(--font-data);'
            f'color:{cor_val};margin-left:6px;">{delta}</span>'
        )
    st.markdown(
        f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
        f'border-radius:var(--radius-md);padding:10px 14px;min-height:64px;'
        f'display:flex;flex-direction:column;justify-content:center;">'
        f'<div style="font-size:.65rem;font-family:var(--font-ui);color:var(--text-muted);'
        f'text-transform:uppercase;letter-spacing:.07em;margin-bottom:4px;">{label}</div>'
        f'<div style="font-size:1.05rem;font-weight:600;font-family:var(--font-data);'
        f'color:var(--text-primary);font-variant-numeric:tabular-nums;'
        f'display:flex;align-items:baseline;">'
        f'{valor}{delta_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def skeleton_loader(n_linhas: int = 3, altura_linha: str = "16px") -> None:
    """Placeholder animado (shimmer) enquanto dados carregam."""
    bars = "".join(
        f'<div style="height:{altura_linha};border-radius:4px;'
        f'background:linear-gradient(90deg,var(--bg-elevated) 25%,'
        f'var(--bg-overlay) 50%,var(--bg-elevated) 75%);'
        f'background-size:200% 100%;animation:_sk_shimmer 1.4s infinite;'
        f'margin-bottom:8px;opacity:{0.9 - i * 0.12:.2f};'
        f'width:{100 - i * 8}%;"></div>'
        for i in range(n_linhas)
    )
    st.markdown(
        f'<style>@keyframes _sk_shimmer{{0%{{background-position:200% 0}}'
        f'100%{{background-position:-200% 0}}}}</style>'
        f'<div style="padding:4px 0;">{bars}</div>',
        unsafe_allow_html=True,
    )


def market_pulse_bar(
    indices: dict[str, tuple[float, float]],
    spread_keys: set | None = None,
) -> None:
    """
    Barra horizontal de pulso de mercado.

    indices: {nome: (preco, variacao_pct)}
    spread_keys: nomes que são spreads (ex: "curva 10y-3m") — formatados em pp, sem sinal %
    """
    spread_keys = spread_keys or {"curva 10y-3m"}
    items = []
    for nome, (preco, var) in indices.items():
        cor   = "var(--bull)" if var >= 0 else "var(--bear)"
        sinal = "▲" if var >= 0 else "▼"
        if nome in spread_keys:
            preco_fmt   = f"{preco:+.2f}pp"
            status_line = "normal" if preco >= 0 else "invertida"
            var_html = (
                f'<span style="font-size:.6rem;font-family:var(--font-data);'
                f'color:{cor};">{status_line}</span>'
            )
        else:
            preco_fmt = f"{preco:,.0f}" if preco >= 1_000 else f"{preco:.2f}"
            var_html  = (
                f'<span style="font-size:.68rem;font-family:var(--font-data);'
                f'color:{cor};">{sinal} {abs(var):.2f}%</span>'
            )
        items.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'justify-content:center;text-align:center;'
            f'flex:1;padding:6px 8px;'
            f'border-right:1px solid var(--border-subtle);gap:2px;">'
            f'<span style="font-size:.58rem;color:var(--text-muted);'
            f'font-family:var(--font-ui);text-transform:uppercase;'
            f'letter-spacing:.05em;white-space:nowrap;">{nome}</span>'
            f'<span style="font-size:.8rem;font-family:var(--font-data);'
            f'font-variant-numeric:tabular-nums;color:var(--text-primary);'
            f'white-space:nowrap;">{preco_fmt}</span>'
            + var_html
            + '</div>'
        )
    html = (
        '<div style="display:flex;align-items:stretch;width:100%;'
        'background:var(--bg-surface);border:1px solid var(--border-subtle);'
        'border-radius:var(--radius-md);padding:0;'
        'overflow:hidden;margin-bottom:16px;">'
        + "".join(items)
        + '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def data_quality_badge(quality_pct: float | None, fonte: str = "", atualizado_em: str = "") -> str:
    """
    Retorna HTML de um badge compacto indicando qualidade do dado.
    Use ao lado de scores e métricas para o usuário saber a confiabilidade.

    Args:
        quality_pct: 0-100 (None = dado indisponível)
        fonte: rótulo da origem (ex: "FMP", "yfinance", "cache 2h")
        atualizado_em: timestamp ou idade legível (ex: "atualizado há 4h")

    Cores:
        verde   >=85
        amarelo 60-84
        laranja 30-59
        vermelho <30
        cinza   None
    """
    import html as _html
    if quality_pct is None:
        # Estado "N/D" precisa ser visível — antes era cinza-pálido e se perdia no fundo
        cor_bg, cor_fg, label = "var(--pill-muted-bg)", "var(--text-muted)", "DADOS N/D"
    elif quality_pct >= 85:
        cor_bg, cor_fg, label = "var(--pill-bull-bg)", "var(--bull)", f"DADOS {int(quality_pct)}%"
    elif quality_pct >= 60:
        cor_bg, cor_fg, label = "var(--pill-amber-bg)", "var(--amber)", f"DADOS {int(quality_pct)}%"
    elif quality_pct >= 30:
        cor_bg, cor_fg, label = "var(--pill-accent-bg)", "var(--accent)", f"DADOS {int(quality_pct)}%"
    else:
        cor_bg, cor_fg, label = "var(--pill-bear-bg)", "var(--bear)", f"DADOS {int(quality_pct)}%"

    tooltip_parts = []
    if fonte:
        tooltip_parts.append(f"fonte: {_html.escape(fonte)}")
    if atualizado_em:
        tooltip_parts.append(_html.escape(atualizado_em))
    tooltip = " · ".join(tooltip_parts) if tooltip_parts else "qualidade do dado (% campos críticos preenchidos)"

    return (
        f'<span title="{tooltip}" style="'
        f'display:inline-block; padding:3px 9px; border-radius:var(--radius-sm); '
        f'background:{cor_bg}; color:{cor_fg}; '
        f'font-family:var(--font-data); font-size:var(--text-xs); '
        f'font-weight:700; letter-spacing:var(--ls-wide); margin-left:var(--space-2); '
        f'vertical-align:middle; border:1px solid {cor_fg};">'
        f'◆ {label}'
        f'</span>'
    )
