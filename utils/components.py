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
    cols = st.columns([1.2, 3.0, 1.5, 0.9, 0.9, 1.1, 1.4, 0.6])
    labels = ["ativo", "nome / sinal", "preço", "1d", "1m", "30d", "health", ""]
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
    serie_30d:     list  = None,  # série pra sparkline 30d
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

    # ── Sparkline 30d ────────────────────────────────────────
    spark_html = ""
    if serie_30d and len(serie_30d) >= 2:
        _spark_tone = "bull" if serie_30d[-1] >= serie_30d[0] else "bear"
        spark_html = inline_sparkline(
            serie_30d, tone=_spark_tone, largura=72, altura=22,
        )

    # ── Layout 8 colunas (adicionou sparkline 30d) ───────────
    col_tk, col_nm, col_pr, col_1d, col_1m, col_sp, col_hs, col_ac = st.columns(
        [1.2, 3.0, 1.5, 0.9, 0.9, 1.1, 1.4, 0.6]
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

    with col_sp:
        if spark_html:
            st.markdown(
                f'<div style="padding:11px 0 3px;">{spark_html}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="padding:13px 0 3px; color:var(--text-muted); '
                'opacity:.35; font-size:0.7rem;">—</div>',
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


# ══════════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM v5 — componentes novos (Fase 3b)
# ══════════════════════════════════════════════════════════════════════════════
#
# Componentes 100% tokens, prontos para uso nas refatorações de página.
# Sem hex/font hardcoded. Cada um documenta uso e parâmetros.
#
# Convenção de tons: bull/bear/amber/info/accent/muted — mapeiam para os
# pares (fg, pill-bg, border) calibrados em todos os 11 temas.
# ══════════════════════════════════════════════════════════════════════════════

_TONES = {
    "bull":   {"fg": "var(--bull)",        "bg": "var(--pill-bull-bg)",   "bd": "var(--bull)"},
    "bear":   {"fg": "var(--bear)",        "bg": "var(--pill-bear-bg)",   "bd": "var(--bear)"},
    "amber":  {"fg": "var(--amber)",       "bg": "var(--pill-amber-bg)",  "bd": "var(--amber)"},
    "info":   {"fg": "var(--info)",        "bg": "var(--pill-info-bg)",   "bd": "var(--info)"},
    "accent": {"fg": "var(--accent)",      "bg": "var(--pill-accent-bg)", "bd": "var(--accent)"},
    "muted":  {"fg": "var(--text-muted)",  "bg": "var(--pill-muted-bg)",  "bd": "var(--border-normal)"},
}


def _tone(t: str) -> dict:
    return _TONES.get(t, _TONES["muted"])


# ── 1. Chip / chip_status ─────────────────────────────────────────────────────

def chip(label: str, tone: str = "muted", icon: str = "") -> str:
    """
    HTML de chip inline (Bloomberg-style). Para filtros, tags, badges em linhas.
    Retorna string — use com st.markdown(..., unsafe_allow_html=True).

    Ex: st.markdown(chip("BR", "info") + chip("FII", "accent"), unsafe_allow_html=True)
    """
    t = _tone(tone)
    ic = f'<span style="margin-right:4px;">{icon}</span>' if icon else ''
    return (
        f'<span style="display:inline-flex;align-items:center;'
        f'background:{t["bg"]};color:{t["fg"]};'
        f'border:1px solid {t["bd"]};border-radius:999px;'
        f'padding:2px 10px;margin-right:4px;'
        f'font-family:var(--font-ui);font-size:var(--text-xs);'
        f'font-weight:600;letter-spacing:var(--ls-wide);'
        f'text-transform:uppercase;line-height:1.5;">{ic}{label}</span>'
    )


def chip_status(label: str, tone: str = "muted") -> str:
    """
    Variante de chip com dot colorido (status visual em tabelas).
    Use para colunas como Status (Compra/Venda/Espera) em data_table.
    """
    t = _tone(tone)
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'background:{t["bg"]};color:{t["fg"]};'
        f'border-radius:var(--radius-sm);padding:3px 10px;'
        f'font-family:var(--font-ui);font-size:var(--text-xs);'
        f'font-weight:600;line-height:1.4;">'
        f'<span style="width:6px;height:6px;border-radius:50%;'
        f'background:{t["fg"]};flex-shrink:0;"></span>{label}</span>'
    )


# ── 2. Info box ───────────────────────────────────────────────────────────────

def info_box(tipo: str, texto: str, titulo: str = "", icone: str = "") -> None:
    """
    Caixa de aviso inline — mais leve que status_card.
    tipo: bull (sucesso) | bear (perigo) | amber (aviso) | info (info)
    """
    t = _tone(tipo)
    default_icons = {"bull": "✓", "bear": "✕", "amber": "⚠", "info": "ⓘ"}
    ic = icone or default_icons.get(tipo, "ⓘ")
    titulo_html = (
        f'<div style="font-weight:600;font-size:var(--text-sm);'
        f'color:{t["fg"]};margin-bottom:3px;">{titulo}</div>'
        if titulo else ""
    )
    st.markdown(
        f'<div style="display:flex;gap:var(--space-3);'
        f'background:{t["bg"]};border-left:3px solid {t["bd"]};'
        f'border-radius:var(--radius-sm);'
        f'padding:var(--space-3) var(--space-4);'
        f'margin:var(--space-2) 0;font-family:var(--font-ui);">'
        f'<span style="color:{t["fg"]};font-size:var(--text-md);'
        f'flex-shrink:0;line-height:1.3;">{ic}</span>'
        f'<div style="flex:1;min-width:0;">{titulo_html}'
        f'<div style="color:var(--text-secondary);font-size:var(--text-sm);'
        f'line-height:1.5;">{texto}</div></div></div>',
        unsafe_allow_html=True,
    )


# ── 3. Inline sparkline (SVG puro) ────────────────────────────────────────────

def inline_sparkline(
    serie: list[float],
    tone: str = "auto",
    largura: int = 80,
    altura: int = 24,
) -> str:
    """
    SVG inline de sparkline mini (estilo Bloomberg). Retorna string HTML.
    tone:
      "auto"  → bull se serie[-1] >= serie[0], bear caso contrário
      bull|bear|amber|info|accent|muted
    """
    if not serie:
        return ""
    vals = [float(v) for v in serie if v is not None]
    if len(vals) < 2:
        return ""
    if tone == "auto":
        tone = "bull" if vals[-1] >= vals[0] else "bear"
    cor = _tone(tone)["fg"]
    vmin, vmax = min(vals), max(vals)
    rng = (vmax - vmin) or 1.0
    pts = " ".join(
        f"{i * largura / (len(vals) - 1):.1f},"
        f"{altura - ((v - vmin) / rng) * altura:.1f}"
        for i, v in enumerate(vals)
    )
    return (
        f'<svg width="{largura}" height="{altura}" '
        f'viewBox="0 0 {largura} {altura}" '
        f'style="vertical-align:middle;overflow:visible;">'
        f'<polyline points="{pts}" fill="none" stroke="{cor}" '
        f'stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round"/></svg>'
    )


# ── 4. Gradient CTA button ────────────────────────────────────────────────────

def _inject_once(key: str, css: str) -> None:
    """Helper: injeta um bloco de CSS uma vez por sessão."""
    if key not in st.session_state:
        st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
        st.session_state[key] = True


def gradient_cta_button(
    label: str,
    key: str,
    icone: str = "",
    largura_full: bool = False,
) -> bool:
    """
    Botão de ação principal com gradient do acento (refs 3 Apexify, 5 DWISLN).
    Use para CTAs (Conectar, Salvar, Aplicar). Retorna True quando clicado.
    """
    _inject_once(
        "_cta_css_v5",
        'div.ft-cta-wrap+div .stButton button{'
        '  background:var(--accent-gradient) !important;'
        '  color:#fff !important;border:none !important;'
        '  border-radius:var(--radius-md) !important;'
        '  padding:var(--space-3) var(--space-5) !important;'
        '  font-family:var(--font-ui) !important;'
        '  font-size:var(--text-sm) !important;'
        '  font-weight:600 !important;'
        '  letter-spacing:var(--ls-wide) !important;'
        '  box-shadow:var(--shadow-md) !important;'
        '  transition:transform var(--motion-fast) var(--ease-out),'
        '             box-shadow var(--motion-fast) var(--ease-out) !important;}'
        'div.ft-cta-wrap+div .stButton button:hover{'
        '  transform:translateY(-1px) !important;'
        '  box-shadow:var(--shadow-lg) !important;}'
        'div.ft-cta-wrap+div .stButton button:active{transform:translateY(0) !important;}'
    )
    label_full = f"{icone}  {label}" if icone else label
    st.markdown('<div class="ft-cta-wrap"></div>', unsafe_allow_html=True)
    return st.button(label_full, key=key, use_container_width=largura_full)


# ── 5. Metric card v2 (com mini-pill de ícone e estado ativo) ────────────────

def metric_card_v2(
    label:       str,
    valor:       str,
    sublabel:    str = "",
    delta_tone:  str = "muted",
    icon_pill:   str = "",
    icon_tone:   str = "info",
    ativo:       bool = False,
    sparkline:   list[float] | None = None,
    data_source: str = "",
) -> None:
    """
    KPI card v2 — Fase 3b. Diferenças vs metric_card:
      • mini-pill colorida com ícone à esquerda (ref 1 manufacturing)
      • estado `ativo` = fundo com gradient do acento (refs 3 Apexify, 5 DWISLN)
      • sparkline opcional inline abaixo do valor

    delta_tone: colore barra esquerda + valor (bull/bear/amber/info/accent/muted)
    icon_tone:  colore só a mini-pill do ícone
    """
    d = _tone(delta_tone)
    i = _tone(icon_tone)

    icone_pill_html = ""
    if icon_pill:
        icone_pill_html = (
            f'<div style="display:inline-flex;align-items:center;'
            f'justify-content:center;width:34px;height:34px;'
            f'border-radius:var(--radius-sm);background:{i["bg"]};'
            f'color:{i["fg"]};font-size:var(--text-md);'
            f'flex-shrink:0;">{icon_pill}</div>'
        )

    spark_html = (
        f'<div style="margin-top:var(--space-2);opacity:0.85;">'
        f'{inline_sparkline(sparkline, tone=delta_tone, largura=140, altura=28)}'
        f'</div>'
        if sparkline else ""
    )

    sub_html = (
        f'<div style="font-family:var(--font-data);font-size:var(--text-xs);'
        f'color:{d["fg"] if delta_tone != "muted" else "var(--text-muted)"};'
        f'margin-top:3px;">{sublabel}</div>'
        if sublabel else ""
    )

    if ativo:
        bg_main   = "var(--accent-gradient)"
        cor_label = "rgba(255,255,255,0.85)"
        cor_valor = "#fff"
        bd_left   = "transparent"
        sombra    = "var(--shadow-lg)"
    else:
        bg_main   = "var(--bg-surface)"
        cor_label = "var(--text-muted)"
        cor_valor = d["fg"] if delta_tone != "muted" else "var(--text-primary)"
        bd_left   = d["fg"] if delta_tone != "muted" else "var(--border-subtle)"
        sombra    = "var(--shadow-sm)"

    st.markdown(
        f'<div style="background:{bg_main};'
        f'border:1px solid var(--border-subtle);'
        f'border-left:3px solid {bd_left};'
        f'border-radius:var(--radius-md);'
        f'padding:var(--space-4);box-shadow:{sombra};'
        f'transition:transform var(--motion-normal) var(--ease-out),'
        f'box-shadow var(--motion-normal) var(--ease-out);'
        f'margin-bottom:var(--space-2);min-height:96px;">'
        f'<div style="display:flex;align-items:flex-start;gap:var(--space-3);">'
        f'{icone_pill_html}'
        f'<div style="flex:1;min-width:0;">'
        f'<div style="font-family:var(--font-ui);font-size:var(--text-xs);'
        f'color:{cor_label};text-transform:uppercase;'
        f'letter-spacing:var(--ls-wide);margin-bottom:4px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
        f'{label}{_fonte_badge(data_source)}</div>'
        f'<div style="font-family:var(--font-data);font-size:var(--text-xl);'
        f'font-weight:700;color:{cor_valor};line-height:1.1;">{valor}</div>'
        f'{sub_html}'
        f'</div></div>'
        f'{spark_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── 6. KPI grid ───────────────────────────────────────────────────────────────

def kpi_grid(items: list[dict], cols: int = 4) -> None:
    """
    Grade responsiva de KPIs. Cada item é dict com chaves de metric_card_v2:
      {label, valor, sublabel?, delta_tone?, icon_pill?, icon_tone?,
       ativo?, sparkline?, data_source?}

    Faz wrap automático em `cols` colunas.
    """
    if not items:
        return
    n = max(1, min(cols, len(items)))
    colunas = st.columns(n, gap="small")
    for idx, item in enumerate(items):
        with colunas[idx % n]:
            metric_card_v2(
                label       = item.get("label", ""),
                valor       = item.get("valor", "—"),
                sublabel    = item.get("sublabel", ""),
                delta_tone  = item.get("delta_tone", "muted"),
                icon_pill   = item.get("icon_pill", ""),
                icon_tone   = item.get("icon_tone", "info"),
                ativo       = item.get("ativo", False),
                sparkline   = item.get("sparkline"),
                data_source = item.get("data_source", ""),
            )


# ── 7. Tabs pill ──────────────────────────────────────────────────────────────

def tabs_pill(labels: list[str], key: str, default: str | None = None) -> str:
    """
    Tabs em pill (ref 2 Virtus). Retorna o label selecionado. Persiste em
    session_state[key]. Use no topo de seções com múltiplas visões.

    Ex: aba = tabs_pill(["Visão", "Posições", "Risco"], key="pf_tabs")
        if aba == "Posições": ...
    """
    if not labels:
        return ""
    current = st.session_state.get(key) or default or labels[0]
    if current not in labels:
        current = labels[0]

    _inject_once(
        "_tabspill_css_v5",
        'div[data-ftpill="1"]+div [data-testid="column"] .stButton button{'
        '  background:transparent !important;'
        '  border:1px solid transparent !important;'
        '  border-radius:999px !important;'
        '  color:var(--text-secondary) !important;'
        '  padding:6px 14px !important;'
        '  font-family:var(--font-ui) !important;'
        '  font-size:var(--text-sm) !important;'
        '  font-weight:500 !important;'
        '  width:100% !important;'
        '  box-shadow:none !important;'
        '  transition:all var(--motion-fast) var(--ease-out) !important;}'
        'div[data-ftpill="1"]+div [data-testid="column"] .stButton button:hover{'
        '  background:var(--bg-overlay) !important;'
        '  color:var(--text-primary) !important;}'
        'div[data-ftpill="1"]+div [data-testid="column"] .stButton button[kind="primary"]{'
        '  background:var(--accent-gradient) !important;'
        '  color:#fff !important;font-weight:600 !important;'
        '  border-color:transparent !important;'
        '  box-shadow:var(--shadow-sm) !important;}'
    )

    st.markdown('<div data-ftpill="1"></div>', unsafe_allow_html=True)
    cols = st.columns(len(labels), gap="small")
    for i, lab in enumerate(labels):
        with cols[i]:
            if st.button(
                lab,
                key=f"{key}__t{i}",
                type=("primary" if lab == current else "secondary"),
                use_container_width=True,
            ):
                st.session_state[key] = lab
                st.rerun()
    return current


# ── 8. Period selector ────────────────────────────────────────────────────────

def period_selector(
    opcoes: list[str],
    key: str,
    default: str | None = None,
    label: str = "período",
) -> str:
    """
    Dropdown compacto no canto superior direito de cards (ref 1 "Monthly ▼").
    Retorna o valor selecionado. Persiste em session_state[key].
    """
    if not opcoes:
        return ""
    _inject_once(
        "_periodsel_css_v5",
        'div[data-ftperiod="1"]+div [data-testid="stSelectbox"] label{'
        '  font-family:var(--font-ui) !important;'
        '  font-size:var(--text-xs) !important;'
        '  color:var(--text-muted) !important;'
        '  text-transform:uppercase !important;'
        '  letter-spacing:var(--ls-wide) !important;'
        '  margin-bottom:0 !important;}'
        'div[data-ftperiod="1"]+div [data-testid="stSelectbox"]>div>div{'
        '  background:var(--bg-elevated) !important;'
        '  border:1px solid var(--border-subtle) !important;'
        '  border-radius:999px !important;'
        '  min-height:30px !important;'
        '  font-family:var(--font-ui) !important;'
        '  font-size:var(--text-sm) !important;}'
    )
    idx = opcoes.index(default) if default in opcoes else 0
    st.markdown('<div data-ftperiod="1"></div>', unsafe_allow_html=True)
    return st.selectbox(label, opcoes, index=idx, key=key, label_visibility="collapsed")


# ── 9. Breadcrumb ─────────────────────────────────────────────────────────────

def breadcrumb(itens: list[tuple[str, str | None]]) -> None:
    """
    Trilha de navegação (ref 5 DWISLN "Dashboards / Overview").
    itens: lista de (label, url_ou_None). O último item sempre vem destacado
    (atual), independentemente de ter URL.

    Ex: breadcrumb([("Home", "/"), ("Research", "/Research"), ("PETR4", None)])
    """
    if not itens:
        return
    partes = []
    for i, (label, href) in enumerate(itens):
        eh_ultimo = (i == len(itens) - 1)
        if eh_ultimo:
            partes.append(
                f'<span style="color:var(--text-primary);font-weight:600;">{label}</span>'
            )
        elif href:
            partes.append(
                f'<a href="{href}" style="color:var(--text-secondary);'
                f'text-decoration:none;">{label}</a>'
            )
        else:
            partes.append(
                f'<span style="color:var(--text-secondary);">{label}</span>'
            )

    sep = (
        '<span style="color:var(--text-muted);margin:0 8px;'
        'font-family:var(--font-ui);">/</span>'
    )
    st.markdown(
        f'<div style="font-family:var(--font-ui);font-size:var(--text-sm);'
        f'display:flex;align-items:center;flex-wrap:wrap;'
        f'padding:var(--space-1) 0;margin-bottom:var(--space-3);">'
        f'{sep.join(partes)}</div>',
        unsafe_allow_html=True,
    )


# ── 10. Empty state v2 ────────────────────────────────────────────────────────

def empty_state_v2(
    titulo: str,
    descricao: str,
    icone: str = "📭",
    cta_label: str = "",
    cta_key: str = "empty_cta",
    on_click_msg: str = "",
) -> bool:
    """
    Estado vazio enriquecido — ícone grande, texto, CTA opcional com gradient.
    Retorna True se CTA foi clicado.
    """
    st.markdown(
        f'<div style="text-align:center;padding:var(--space-8) var(--space-6);'
        f'background:var(--bg-surface);border:1px dashed var(--border-normal);'
        f'border-radius:var(--radius-lg);margin:var(--space-4) 0;">'
        f'<div style="font-size:2.6rem;margin-bottom:var(--space-3);'
        f'opacity:0.4;line-height:1;">{icone}</div>'
        f'<div style="font-family:var(--font-ui);font-size:var(--text-md);'
        f'font-weight:600;color:var(--text-primary);'
        f'margin-bottom:var(--space-1);">{titulo}</div>'
        f'<div style="font-family:var(--font-ui);font-size:var(--text-sm);'
        f'color:var(--text-muted);max-width:380px;margin:0 auto;'
        f'line-height:1.6;">{descricao}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if cta_label:
        c1, c2, c3 = st.columns([2, 1, 2])
        with c2:
            if gradient_cta_button(cta_label, key=cta_key, largura_full=True):
                if on_click_msg:
                    st.toast(on_click_msg)
                return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM v5 — SHELL (Fase 5)
# ══════════════════════════════════════════════════════════════════════════════
#
# Topbar fina + sidebar redesenhada + side panel lateral. Pensados para
# coexistir com o auto-discovery atual de pages/* (sem st.navigation) — a
# migração ficará por conta de streamlit_app.py opcional.
#
# Os 3 componentes abaixo são puro HTML/CSS (sem dependência de Streamlit
# routing) — funcionam em qualquer página chamando a função.
# ══════════════════════════════════════════════════════════════════════════════


def topbar(
    breadcrumb_itens: list[tuple[str, str | None]] | None = None,
    *,
    show_search: bool = True,
    show_user: bool = True,
    show_sync: bool = True,
    user_name: str = "",
    sync_label: str = "",
) -> None:
    """
    Barra superior fina sticky (ref 5 DWISLN).

    Slots:
      - esquerda: breadcrumb (lista de (label, href|None))
      - centro:   atalho de busca Ctrl+K (visual — abre o command_palette via JS)
      - direita:  indicador sync + user badge + toggle tema (compacto)

    Use no topo de cada página (após aplicar_tema), antes do page_header.
    """
    _inject_once(
        "_topbar_css_v5",
        '.ft-topbar{position:sticky;top:0;z-index:998;'
        '  display:flex;align-items:center;gap:var(--space-4);'
        '  padding:var(--space-2) var(--space-4);'
        '  background:var(--surface-glass);backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border-bottom:1px solid var(--border-subtle);'
        '  margin:calc(-1 * var(--space-4)) calc(-1 * var(--space-4)) var(--space-4);'
        '  font-family:var(--font-ui);font-size:var(--text-sm);}'
        '.ft-topbar-left{flex:1;display:flex;align-items:center;'
        '  gap:var(--space-2);min-width:0;overflow:hidden;}'
        '.ft-topbar-center{flex:0 0 auto;display:flex;align-items:center;}'
        '.ft-topbar-right{flex:1;display:flex;align-items:center;'
        '  justify-content:flex-end;gap:var(--space-3);}'
        '.ft-topbar-search-btn{display:inline-flex;align-items:center;gap:6px;'
        '  background:var(--bg-elevated);border:1px solid var(--border-subtle);'
        '  border-radius:999px;padding:5px 12px;color:var(--text-muted);'
        '  font-size:var(--text-xs);cursor:pointer;'
        '  transition:all var(--motion-fast) var(--ease-out);}'
        '.ft-topbar-search-btn:hover{border-color:var(--accent-border);'
        '  color:var(--text-secondary);}'
        '.ft-topbar-search-btn kbd{font-family:var(--font-data);'
        '  background:var(--bg-base);border:1px solid var(--border-normal);'
        '  border-radius:var(--radius-sm);padding:1px 5px;font-size:.6rem;'
        '  color:var(--text-secondary);margin-left:4px;}'
        '.ft-topbar-pill{display:inline-flex;align-items:center;gap:6px;'
        '  background:var(--pill-muted-bg);border:1px solid var(--border-subtle);'
        '  border-radius:999px;padding:4px 10px;font-size:var(--text-xs);'
        '  color:var(--text-secondary);}'
        '.ft-topbar-pill .dot{width:6px;height:6px;border-radius:50%;'
        '  background:var(--bull);box-shadow:0 0 6px var(--bull);}'
        '.ft-topbar-pill.warn .dot{background:var(--amber);box-shadow:0 0 6px var(--amber);}'
        '.ft-topbar-user{display:inline-flex;align-items:center;gap:6px;'
        '  background:var(--bg-elevated);border:1px solid var(--border-subtle);'
        '  border-radius:999px;padding:3px 4px 3px 10px;font-size:var(--text-xs);'
        '  color:var(--text-secondary);}'
        '.ft-topbar-user .avatar{display:inline-flex;align-items:center;'
        '  justify-content:center;width:22px;height:22px;border-radius:50%;'
        '  background:var(--accent-gradient);color:#fff;'
        '  font-weight:700;font-size:.7rem;}'
        '@media (max-width:900px){.ft-topbar-center{display:none;}}'
    )

    # ── Slot esquerda: breadcrumb ────────────────────────────────────────────
    left_html = ""
    if breadcrumb_itens:
        partes = []
        for i, (label, href) in enumerate(breadcrumb_itens):
            is_last = (i == len(breadcrumb_itens) - 1)
            if is_last:
                partes.append(
                    f'<span style="color:var(--text-primary);font-weight:600;'
                    f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                    f'{label}</span>'
                )
            elif href:
                partes.append(
                    f'<a href="{href}" style="color:var(--text-secondary);'
                    f'text-decoration:none;">{label}</a>'
                )
            else:
                partes.append(
                    f'<span style="color:var(--text-secondary);">{label}</span>'
                )
        sep = (
            '<span style="color:var(--text-muted);"'
            ' aria-hidden="true">/</span>'
        )
        left_html = sep.join(partes)
    else:
        left_html = (
            '<span style="color:var(--text-muted);font-size:var(--text-xs);'
            'text-transform:uppercase;letter-spacing:var(--ls-wide);">'
            '⚡ finterminal</span>'
        )

    # ── Slot centro: busca / Ctrl+K ──────────────────────────────────────────
    center_html = ""
    if show_search:
        center_html = (
            '<div class="ft-topbar-search-btn" '
            'style="display:inline-flex;align-items:center;gap:6px;" '
            'onclick="window.parent.postMessage({type:\'finterm-open-palette\'},\'*\');" '
            'title="abrir command palette (Ctrl+K)">'
            '<span>🔍 buscar</span>'
            '<kbd style="margin-left:4px;">Ctrl+K</kbd></div>'
        )

    # ── Slot direita: sync + user ────────────────────────────────────────────
    right_parts = []
    if show_sync:
        _sl = sync_label or "ativo"
        right_parts.append(
            f'<span class="ft-topbar-pill" '
            f'style="display:inline-flex;align-items:center;gap:6px;" '
            f'title="status de sincronização">'
            f'<span class="dot"></span>{_sl}</span>'
        )
    if show_user:
        nm = user_name or "usuário"
        ini = (nm.strip()[:1] or "U").upper()
        right_parts.append(
            f'<span class="ft-topbar-user" '
            f'style="display:inline-flex;align-items:center;gap:6px;" '
            f'title="conectado como {nm}">'
            f'<span>{nm[:14]}</span><span class="avatar">{ini}</span></span>'
        )

    right_html = "".join(right_parts)

    st.markdown(
        f'<div class="ft-topbar" style="display:flex;align-items:center;gap:var(--space-4);">'
        f'<div class="ft-topbar-left" style="flex:1;display:flex;align-items:center;gap:var(--space-2);">{left_html}</div>'
        f'<div class="ft-topbar-center">{center_html}</div>'
        f'<div class="ft-topbar-right" style="flex:1;display:flex;align-items:center;justify-content:flex-end;gap:var(--space-3);">{right_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def sidebar_nav_item(
    label:    str,
    page_path: str,
    *,
    icon:    str = "",
    active:  bool = False,
    badge:   str = "",
    key:     str = "",
) -> bool:
    """
    Item de navegação pill para usar dentro de st.sidebar (refs 2, 3).
    Retorna True quando clicado (faz st.switch_page para `page_path` automaticamente).

    Use:
      with st.sidebar:
          sidebar_nav_item("Research", "pages/1_Research.py",
                           icon="🔬", active=(current=='Research'), badge="3")
    """
    _inject_once(
        "_sidenav_css_v5",
        'div[data-ftsidenav="1"]+div .stButton button{'
        '  display:flex !important;align-items:center !important;'
        '  justify-content:flex-start !important;gap:var(--space-3) !important;'
        '  background:transparent !important;border:1px solid transparent !important;'
        '  border-radius:var(--radius-md) !important;'
        '  padding:8px 12px !important;width:100% !important;'
        '  font-family:var(--font-ui) !important;'
        '  font-size:var(--text-sm) !important;font-weight:500 !important;'
        '  color:var(--text-secondary) !important;'
        '  transition:all var(--motion-fast) var(--ease-out) !important;'
        '  box-shadow:none !important;text-align:left !important;}'
        'div[data-ftsidenav="1"]+div .stButton button:hover{'
        '  background:var(--bg-overlay) !important;'
        '  color:var(--text-primary) !important;}'
        'div[data-ftsidenav="1"]+div .stButton button[kind="primary"]{'
        '  background:var(--accent-gradient) !important;'
        '  color:#fff !important;font-weight:600 !important;'
        '  border-color:transparent !important;'
        '  box-shadow:var(--shadow-sm) !important;}'
    )

    bk = key or f"nav__{page_path.replace('/', '_').replace('.', '_')}"
    label_display = f"{icon} {label}" if icon else label
    if badge:
        label_display = f"{label_display}  ·  {badge}"

    st.markdown('<div data-ftsidenav="1"></div>', unsafe_allow_html=True)
    if st.button(
        label_display,
        key=bk,
        type=("primary" if active else "secondary"),
        use_container_width=True,
    ):
        try:
            st.switch_page(page_path)
        except Exception:
            pass
        return True
    return False


def side_panel(
    secoes: list[dict],
    *,
    titulo: str = "",
    largura: int = 320,
) -> None:
    """
    Painel lateral direito (ref 5 DWISLN). Render fora do <main> via HTML.

    secoes: lista de dicts {"titulo": str, "items": [str|dict, ...]}
      Cada item pode ser:
        - str   → renderiza como linha simples
        - dict  → {"label": str, "valor": str, "tone": str, "icone": str}

    Em viewports < 1280px o painel vira accordion compacto inline.
    Use no FIM da página principal (após o conteúdo do main).
    """
    if not secoes:
        return

    _inject_once(
        "_sidepanel_css_v5",
        '.ft-side-panel{background:var(--bg-surface);'
        '  border:1px solid var(--border-subtle);'
        '  border-radius:var(--radius-lg);'
        '  padding:var(--space-4);box-shadow:var(--shadow-sm);'
        '  font-family:var(--font-ui);}'
        '.ft-side-panel-title{font-size:var(--text-xs);'
        '  color:var(--text-muted);text-transform:uppercase;'
        '  letter-spacing:var(--ls-wide);font-weight:600;'
        '  margin-bottom:var(--space-3);}'
        '.ft-side-section{border-top:1px solid var(--border-subtle);'
        '  padding-top:var(--space-3);margin-top:var(--space-3);}'
        '.ft-side-section:first-child{border-top:0;padding-top:0;margin-top:0;}'
        '.ft-side-section h4{font-size:var(--text-sm);'
        '  font-weight:600;color:var(--text-primary);'
        '  margin:0 0 var(--space-2);}'
        '.ft-side-item{display:flex;align-items:center;gap:var(--space-2);'
        '  padding:5px 0;font-size:var(--text-sm);}'
        '.ft-side-item-icon{flex:0 0 22px;font-size:var(--text-md);'
        '  color:var(--text-muted);}'
        '.ft-side-item-label{flex:1;color:var(--text-secondary);'
        '  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
        '.ft-side-item-val{font-family:var(--font-data);'
        '  font-size:var(--text-xs);color:var(--text-primary);font-weight:600;}'
        '.ft-side-item-val.bull{color:var(--bull);}'
        '.ft-side-item-val.bear{color:var(--bear);}'
        '.ft-side-item-val.amber{color:var(--amber);}'
        '.ft-side-item-val.info{color:var(--info);}'
        '.ft-side-item-val.accent{color:var(--accent);}'
    )

    def _render_item(item) -> str:
        if isinstance(item, str):
            return (
                f'<div class="ft-side-item">'
                f'<div class="ft-side-item-label">{item}</div></div>'
            )
        icone = item.get("icone", "")
        label = item.get("label", "")
        valor = item.get("valor", "")
        tone  = item.get("tone", "")
        ic = f'<div class="ft-side-item-icon">{icone}</div>' if icone else ''
        vl = (
            f'<div class="ft-side-item-val {tone}">{valor}</div>'
            if valor else ''
        )
        return (
            f'<div class="ft-side-item">{ic}'
            f'<div class="ft-side-item-label">{label}</div>{vl}</div>'
        )

    secs_html = ""
    for sec in secoes:
        s_titulo = sec.get("titulo", "")
        s_items  = sec.get("items", [])
        items_html = "".join(_render_item(it) for it in s_items)
        secs_html += (
            f'<div class="ft-side-section">'
            f'<h4>{s_titulo}</h4>{items_html}</div>'
        )

    titulo_html = (
        f'<div class="ft-side-panel-title">{titulo}</div>' if titulo else ""
    )
    st.markdown(
        f'<div class="ft-side-panel" style="max-width:{largura}px;">'
        f'{titulo_html}{secs_html}</div>',
        unsafe_allow_html=True,
    )


# ── Tabela HTML consolidada (opcional na Fase 5b) ────────────────────────────

def html_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    aligns: list[str] | None = None,
    classes: list[list[str]] | None = None,
    sticky_header: bool = False,
    caption: str = "",
) -> None:
    """
    Tabela HTML consolidada — substitui o boilerplate de ~30 linhas por
    chamada que se repetia em Discovery/Configurações/Backfill/Portfolio.

    headers: list de labels do cabeçalho
    rows:    list de rows, cada row é list de células (str HTML — pode conter
             tags como <a>, <span> etc., os valores não são escapados)
    aligns:  alinhamento por coluna ("left"|"right"|"center"). default left
    classes: classes CSS opcionais por célula — list de lists matching rows
    sticky_header: thead sticky no topo do container

    Estilos centralizados em .ft-table (style.py). Tipografia/cores via tokens.
    """
    if not headers:
        return

    _inject_once(
        "_htmltable_css_v5",
        '.ft-table{width:100%;border-collapse:collapse;'
        '  font-family:var(--font-ui);background:var(--bg-surface);'
        '  border-radius:var(--radius-md);overflow:hidden;}'
        '.ft-table thead th{padding:8px 12px;text-align:left;'
        '  font-size:var(--text-xs);color:var(--text-muted);'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  border-bottom:1px solid var(--border-subtle);'
        '  white-space:nowrap;font-weight:600;}'
        '.ft-table.sticky thead th{position:sticky;top:0;'
        '  background:var(--bg-surface);z-index:1;}'
        '.ft-table tbody td{padding:8px 12px;font-size:var(--text-sm);'
        '  color:var(--text-secondary);}'
        '.ft-table tbody tr{border-bottom:1px solid var(--border-subtle);'
        '  transition:background var(--motion-fast) var(--ease-out);}'
        '.ft-table tbody tr:hover{background:var(--bg-hover);}'
        '.ft-table tbody tr:last-child{border-bottom:0;}'
        '.ft-table td.right,.ft-table th.right{text-align:right;}'
        '.ft-table td.center,.ft-table th.center{text-align:center;}'
        '.ft-table td.bull{color:var(--bull);}'
        '.ft-table td.bear{color:var(--bear);}'
        '.ft-table td.muted{color:var(--text-muted);}'
        '.ft-table td.mono{font-family:var(--font-data);}'
        '.ft-table-caption{font-size:var(--text-xs);'
        '  color:var(--text-muted);margin-bottom:6px;}'
        '.ft-table-wrap{overflow-x:auto;width:100%;}'
    )

    aligns = aligns or ["left"] * len(headers)
    sticky_cls = " sticky" if sticky_header else ""

    # Header
    th_html = ""
    for h, al in zip(headers, aligns):
        cls = f' class="{al}"' if al != "left" else ""
        th_html += f'<th{cls}>{h}</th>'

    # Body
    tr_html = ""
    for ridx, row in enumerate(rows):
        td_html = ""
        for cidx, val in enumerate(row):
            al = aligns[cidx] if cidx < len(aligns) else "left"
            extras = []
            if al != "left":
                extras.append(al)
            if classes and ridx < len(classes) and cidx < len(classes[ridx]):
                extras += [c for c in classes[ridx][cidx].split() if c]
            cls = f' class="{" ".join(extras)}"' if extras else ""
            td_html += f'<td{cls}>{val}</td>'
        tr_html += f'<tr>{td_html}</tr>'

    caption_html = (
        f'<div class="ft-table-caption">{caption}</div>' if caption else ""
    )
    st.markdown(
        f'{caption_html}'
        f'<div class="ft-table-wrap">'
        f'<table class="ft-table{sticky_cls}">'
        f'<thead><tr>{th_html}</tr></thead>'
        f'<tbody>{tr_html}</tbody>'
        f'</table></div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# HERO COMPONENTS (Zona 1 — visual de impacto na Home)
# ══════════════════════════════════════════════════════════════════════════════


def hero_macro(
    score: int,
    label: str,
    descricao: str,
    tom: str = "amber",
    sinais: list[tuple] | None = None,
    fontes_badges: list[tuple[str, str]] | None = None,
) -> None:
    """
    Hero card grande do regime macro. Substitui o gauge + sinais individuais.

    Layout: card com border-glow no tom, esquerda = regime em tipografia 3xl +
    score grande + descrição; direita = grid 2 colunas de sinais como mini-pills.

    Args:
      score: 0–100 (mostrado em destaque grande)
      label: "RISK ON" | "NEUTRO" | "CAUTELOSO" | "RISK OFF"
      descricao: texto curto descritivo do regime
      tom: "bull" | "amber" | "bear" — define cor do gradient e accent
      sinais: lista de (nome, status, tipo_s [bull/amber/bear], valor)
      fontes_badges: lista de (chave, "cache"|"api") para badges discretos no rodapé
    """
    t = _tone(tom)
    sinais = sinais or []
    fontes_badges = fontes_badges or []

    _inject_once(
        "_hero_macro_css_v1",
        '.ft-hero-macro{position:relative;display:grid;'
        '  grid-template-columns:minmax(280px, 1fr) 1.6fr;gap:var(--space-5);'
        '  padding:var(--space-5) var(--space-5);'
        '  border-radius:var(--radius-xl);'
        '  background:var(--surface-glass);backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);'
        '  box-shadow:var(--shadow-lg);overflow:hidden;'
        '  margin-bottom:var(--space-4);}'
        '.ft-hero-macro::before{content:"";position:absolute;inset:0;'
        '  background:linear-gradient(135deg,var(--hero-tone-rgba) 0%,transparent 55%);'
        '  pointer-events:none;}'
        '.ft-hero-macro::after{content:"";position:absolute;left:0;top:0;bottom:0;'
        '  width:3px;background:var(--hero-tone);box-shadow:0 0 18px var(--hero-tone);}'
        '.ft-hero-left{position:relative;display:flex;flex-direction:column;'
        '  justify-content:center;gap:var(--space-2);}'
        '.ft-hero-eyebrow{font-family:var(--font-ui);font-size:var(--text-xs);'
        '  text-transform:uppercase;letter-spacing:var(--ls-wider);'
        '  color:var(--text-muted);}'
        '.ft-hero-label{font-family:var(--font-title);font-size:var(--text-3xl);'
        '  font-weight:800;color:var(--hero-tone);letter-spacing:var(--ls-tight);'
        '  line-height:1;margin:0;'
        '  text-shadow:0 0 24px var(--hero-tone-rgba-strong);}'
        '.ft-hero-score{display:inline-flex;align-items:baseline;gap:6px;'
        '  font-family:var(--font-data);margin-top:var(--space-1);}'
        '.ft-hero-score .num{font-size:var(--text-2xl);font-weight:700;'
        '  color:var(--text-primary);}'
        '.ft-hero-score .max{font-size:var(--text-sm);color:var(--text-muted);}'
        '.ft-hero-desc{font-family:var(--font-ui);font-size:var(--text-sm);'
        '  color:var(--text-secondary);line-height:1.55;max-width:42ch;'
        '  margin-top:var(--space-2);}'
        '.ft-hero-bar{position:relative;height:6px;border-radius:999px;'
        '  background:var(--bg-elevated);overflow:hidden;'
        '  margin-top:var(--space-3);max-width:340px;}'
        '.ft-hero-bar-fill{position:absolute;left:0;top:0;bottom:0;'
        '  background:linear-gradient(90deg,var(--hero-tone) 0%,var(--hero-tone-soft) 100%);'
        '  box-shadow:0 0 12px var(--hero-tone);'
        '  transition:width var(--motion-base) var(--ease-out);}'
        '.ft-hero-right{position:relative;display:grid;'
        '  grid-template-columns:1fr 1fr;gap:8px;align-content:center;}'
        '.ft-hero-sinal{display:grid;'
        '  grid-template-columns:14px minmax(0,1fr) auto;align-items:center;'
        '  gap:8px;padding:8px 12px;border-radius:var(--radius-md);'
        '  background:var(--bg-elevated);border:1px solid var(--border-subtle);'
        '  font-size:var(--text-xs);'
        '  transition:border-color var(--motion-fast) var(--ease-out);}'
        '.ft-hero-sinal:hover{border-color:var(--border-normal);}'
        '.ft-hero-sinal .dot{width:8px;height:8px;border-radius:50%;'
        '  box-shadow:0 0 6px currentColor;}'
        '.ft-hero-sinal .name{font-family:var(--font-ui);'
        '  color:var(--text-secondary);text-transform:uppercase;'
        '  letter-spacing:var(--ls-wide);font-size:.66rem;'
        '  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
        '.ft-hero-sinal .val{font-family:var(--font-data);'
        '  color:var(--text-primary);font-weight:600;'
        '  font-size:var(--text-xs);}'
        '.ft-hero-fontes{grid-column:1 / -1;display:flex;flex-wrap:wrap;'
        '  gap:6px 12px;padding-top:8px;border-top:1px solid var(--border-subtle);'
        '  margin-top:4px;}'
        '.ft-hero-fontes span{font-family:var(--font-ui);font-size:.6rem;'
        '  color:var(--text-muted);}'
        '@media (max-width:900px){.ft-hero-macro{grid-template-columns:1fr;}'
        '  .ft-hero-right{grid-template-columns:1fr;}}'
    )

    # Map tom → cores reais (via _TONES já existente)
    tone_color = t.get("fg", "var(--amber)")
    # rgba derivado pra glow / gradient bg
    rgba_soft = "rgba(255,170,0,0.10)"
    rgba_strong = "rgba(255,170,0,0.45)"
    soft_color = "var(--amber-soft, var(--amber))"
    if tom == "bull":
        rgba_soft = "rgba(74,222,128,0.10)"
        rgba_strong = "rgba(74,222,128,0.45)"
        soft_color = "var(--bull-soft, var(--bull))"
    elif tom == "bear":
        rgba_soft = "rgba(248,113,113,0.10)"
        rgba_strong = "rgba(248,113,113,0.45)"
        soft_color = "var(--bear-soft, var(--bear))"

    # Sinais → cards mini
    sinais_html = ""
    for nome, status, tipo_s, valor in sinais:
        st_t = _tone(tipo_s if tipo_s in ("bull", "bear", "amber") else "muted")
        dot_c = st_t.get("fg", "var(--text-muted)")
        sinais_html += (
            f'<div class="ft-hero-sinal" title="{nome}: {status}">'
            f'<span class="dot" style="background:{dot_c};color:{dot_c};"></span>'
            f'<span class="name">{nome} · {status}</span>'
            f'<span class="val">{valor}</span>'
            f'</div>'
        )

    fontes_html = ""
    if fontes_badges:
        parts = []
        for k, src in fontes_badges:
            ic = "📦" if src == "cache" else "📡"
            parts.append(f'<span>{ic} {k}</span>')
        fontes_html = f'<div class="ft-hero-fontes">{"".join(parts)}</div>'

    pct_fill = max(0, min(100, int(score)))

    st.markdown(
        f'<div class="ft-hero-macro" '
        f'style="--hero-tone:{tone_color};'
        f'--hero-tone-soft:{soft_color};'
        f'--hero-tone-rgba:{rgba_soft};'
        f'--hero-tone-rgba-strong:{rgba_strong};">'
        f'<div class="ft-hero-left">'
        f'<span class="ft-hero-eyebrow">ambiente macro · score</span>'
        f'<h2 class="ft-hero-label">{label}</h2>'
        f'<div class="ft-hero-score"><span class="num">{score}</span>'
        f'<span class="max">/ 100</span></div>'
        f'<div class="ft-hero-bar"><div class="ft-hero-bar-fill" '
        f'style="width:{pct_fill}%;"></div></div>'
        f'<p class="ft-hero-desc">{descricao}</p>'
        f'</div>'
        f'<div class="ft-hero-right">{sinais_html}{fontes_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def kpi_index_row(
    items: list[dict],
) -> None:
    """
    Linha de KPIs grandes para índices/preços. Cada item:
      {nome, valor, var_pct, serie? (lista p/ sparkline), ticker?, sufixo?}

    Renderiza grid responsivo (4-col em desktop, 2-col em mobile) com card
    glassmorphism, sparkline inline, delta colorido e leve glow no tom da var.
    """
    _inject_once(
        "_kpi_index_row_css_v1",
        '.ft-kpi-row{display:grid;grid-template-columns:repeat(4, minmax(0,1fr));'
        '  gap:var(--space-3);margin-bottom:var(--space-4);}'
        '.ft-kpi-card{position:relative;padding:14px 16px;'
        '  border-radius:var(--radius-lg);background:var(--surface-glass);'
        '  backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);overflow:hidden;'
        '  transition:transform var(--motion-fast) var(--ease-out),'
        '             border-color var(--motion-fast) var(--ease-out);}'
        '.ft-kpi-card:hover{transform:translateY(-2px);'
        '  border-color:var(--border-normal);}'
        '.ft-kpi-card::after{content:"";position:absolute;left:0;top:0;'
        '  width:100%;height:2px;background:var(--kpi-tone);'
        '  box-shadow:0 0 10px var(--kpi-tone);opacity:.85;}'
        '.ft-kpi-name{font-family:var(--font-ui);font-size:.66rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  color:var(--text-muted);margin-bottom:6px;'
        '  display:flex;justify-content:space-between;align-items:center;}'
        '.ft-kpi-name .tk{font-size:.58rem;color:var(--text-muted);opacity:.7;}'
        '.ft-kpi-value{font-family:var(--font-data);font-size:var(--text-2xl);'
        '  font-weight:700;color:var(--text-primary);'
        '  line-height:1.1;letter-spacing:var(--ls-tight);}'
        '.ft-kpi-foot{display:flex;justify-content:space-between;'
        '  align-items:center;margin-top:8px;gap:8px;}'
        '.ft-kpi-delta{font-family:var(--font-data);font-size:var(--text-sm);'
        '  font-weight:600;display:inline-flex;align-items:center;gap:3px;}'
        '@media (max-width:900px){.ft-kpi-row{grid-template-columns:repeat(2,1fr);}}'
        '@media (max-width:500px){.ft-kpi-row{grid-template-columns:1fr;}}'
    )

    if not items:
        return

    cards = []
    for it in items:
        nome   = it.get("nome", "")
        valor  = it.get("valor", "")
        var    = float(it.get("var_pct", 0) or 0)
        serie  = it.get("serie") or []
        ticker = it.get("ticker", "")
        sufixo = it.get("sufixo", "")

        is_up   = var >= 0
        tone    = "bull" if is_up else "bear"
        tone_c  = "var(--bull)" if is_up else "var(--bear)"
        arrow   = "▲" if is_up else "▼"

        # Sparkline (compacto)
        spark = ""
        if len(serie) >= 2:
            spark = inline_sparkline(serie, tone=tone, largura=78, altura=20)

        # Formatação do valor (aceita string já formatada ou número)
        if isinstance(valor, (int, float)):
            v = float(valor)
            if abs(v) >= 1000:
                valor_fmt = f"{v:,.0f}".replace(",", ".")
            else:
                valor_fmt = f"{v:.2f}".replace(".", ",")
            if sufixo:
                valor_fmt = f"{valor_fmt} {sufixo}"
        else:
            valor_fmt = str(valor)

        cards.append(
            f'<div class="ft-kpi-card" style="--kpi-tone:{tone_c};">'
            f'<div class="ft-kpi-name">'
            f'<span>{nome}</span>'
            f'<span class="tk">{ticker}</span>'
            f'</div>'
            f'<div class="ft-kpi-value">{valor_fmt}</div>'
            f'<div class="ft-kpi-foot">'
            f'<span class="ft-kpi-delta" style="color:{tone_c};">'
            f'{arrow} {abs(var):.2f}%</span>'
            f'{spark}'
            f'</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="ft-kpi-row">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# WATCHLIST COMPONENTS (Zona 2 — destaques e headers de grupo)
# ══════════════════════════════════════════════════════════════════════════════


def highlights_strip(
    secoes: list[dict],
) -> None:
    """
    Strip horizontal de cards-destaque (Earnings hoje · Movers · Alertas).

    Cada seção: {"titulo", "icone", "tone" (bull/amber/bear/info/accent),
                 "items" (list de dicts {"label", "valor", "tone"} ou str)}

    Substitui o side_panel vertical na Home (que causa nesting de st.columns
    quando colocado ao lado da watchlist). Aqui usa grid responsivo flat.
    """
    if not secoes:
        return

    _inject_once(
        "_highlights_strip_css_v1",
        '.ft-hs-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));'
        '  gap:var(--space-3);margin-bottom:var(--space-4);}'
        '.ft-hs-card{position:relative;padding:var(--space-3) var(--space-4);'
        '  border-radius:var(--radius-lg);background:var(--surface-glass);'
        '  backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);overflow:hidden;'
        '  transition:border-color var(--motion-fast) var(--ease-out);}'
        '.ft-hs-card:hover{border-color:var(--border-normal);}'
        '.ft-hs-card::before{content:"";position:absolute;left:0;top:0;'
        '  bottom:0;width:3px;background:var(--hs-tone);'
        '  box-shadow:0 0 8px var(--hs-tone);}'
        '.ft-hs-head{display:flex;align-items:center;'
        '  justify-content:space-between;margin-bottom:8px;}'
        '.ft-hs-head .ic{display:inline-flex;align-items:center;gap:6px;'
        '  font-family:var(--font-ui);font-size:.66rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  color:var(--hs-tone);font-weight:600;}'
        '.ft-hs-head .qt{font-family:var(--font-data);font-size:.7rem;'
        '  color:var(--text-muted);background:var(--bg-elevated);'
        '  border-radius:999px;padding:2px 8px;}'
        '.ft-hs-list{display:flex;flex-direction:column;gap:4px;}'
        '.ft-hs-item{display:grid;'
        '  grid-template-columns:minmax(0,1fr) auto;'
        '  align-items:center;gap:10px;padding:5px 0;'
        '  border-bottom:1px solid var(--border-subtle);font-size:var(--text-xs);}'
        '.ft-hs-item:last-child{border-bottom:0;}'
        '.ft-hs-item .lb{font-family:var(--font-ui);'
        '  color:var(--text-secondary);'
        '  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
        '.ft-hs-item .vl{font-family:var(--font-data);font-weight:600;'
        '  font-size:var(--text-xs);}'
        '.ft-hs-empty{font-family:var(--font-ui);font-size:var(--text-xs);'
        '  color:var(--text-muted);text-align:center;padding:14px 8px;'
        '  font-style:italic;opacity:.7;}'
        '@media (max-width:900px){.ft-hs-row{grid-template-columns:1fr;}}'
    )

    cards = []
    for sec in secoes:
        titulo = sec.get("titulo", "")
        icone  = sec.get("icone", "")
        tone   = sec.get("tone", "muted")
        items  = sec.get("items", [])

        t = _tone(tone)
        tone_c = t.get("fg", "var(--text-muted)")

        items_html = ""
        if not items:
            items_html = '<div class="ft-hs-empty">— nada agora —</div>'
        else:
            for it in items[:5]:
                if isinstance(it, str):
                    items_html += (
                        f'<div class="ft-hs-item">'
                        f'<span class="lb">{it}</span></div>'
                    )
                else:
                    lb = it.get("label", "")
                    vl = it.get("valor", "")
                    it_tone = it.get("tone", "muted")
                    it_t = _tone(it_tone)
                    it_c = it_t.get("fg", "var(--text-primary)")
                    vl_html = (
                        f'<span class="vl" style="color:{it_c};">{vl}</span>'
                        if vl else ''
                    )
                    items_html += (
                        f'<div class="ft-hs-item">'
                        f'<span class="lb">{lb}</span>{vl_html}</div>'
                    )

        cards.append(
            f'<div class="ft-hs-card" style="--hs-tone:{tone_c};">'
            f'<div class="ft-hs-head">'
            f'<span class="ic">{icone} {titulo}</span>'
            f'<span class="qt">{len(items)}</span>'
            f'</div>'
            f'<div class="ft-hs-list">{items_html}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="ft-hs-row">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def mercado_group_header(
    nome: str,
    qtd: int,
    *,
    tone: str = "info",
    icone: str = "▸",
) -> None:
    """
    Header bonito para grupo de mercado dentro da watchlist (BR / EUA / FIIs).
    Substitui o '▸ brasil' minúsculo por uma faixa com chip e contagem.
    """
    _inject_once(
        "_mercado_group_css_v1",
        '.ft-mkt-group{display:flex;align-items:center;gap:10px;'
        '  padding:14px 0 8px;margin-top:var(--space-3);}'
        '.ft-mkt-group .ic{font-family:var(--font-ui);'
        '  font-size:.72rem;font-weight:700;color:var(--mkt-tone);'
        '  text-transform:uppercase;letter-spacing:var(--ls-wider);'
        '  display:inline-flex;align-items:center;gap:6px;}'
        '.ft-mkt-group .dot{width:6px;height:6px;border-radius:50%;'
        '  background:var(--mkt-tone);box-shadow:0 0 6px var(--mkt-tone);}'
        '.ft-mkt-group .ct{font-family:var(--font-data);font-size:.68rem;'
        '  color:var(--text-muted);background:var(--bg-elevated);'
        '  border:1px solid var(--border-subtle);'
        '  border-radius:999px;padding:1px 8px;}'
        '.ft-mkt-group .ln{flex:1;height:1px;background:linear-gradient('
        '  90deg,var(--mkt-tone-rgba) 0%,transparent 100%);opacity:.6;}'
    )

    t = _tone(tone)
    c = t.get("fg", "var(--accent)")
    # rgba derivado simples
    rgba = "rgba(110,128,255,0.3)"
    if tone == "bull":
        rgba = "rgba(74,222,128,0.3)"
    elif tone == "bear":
        rgba = "rgba(248,113,113,0.3)"
    elif tone == "amber":
        rgba = "rgba(251,191,36,0.3)"
    elif tone == "accent":
        rgba = "rgba(255,140,0,0.3)"

    st.markdown(
        f'<div class="ft-mkt-group" '
        f'style="--mkt-tone:{c};--mkt-tone-rgba:{rgba};">'
        f'<span class="ic"><span class="dot"></span>{icone} {nome}</span>'
        f'<span class="ct">{qtd}</span>'
        f'<span class="ln"></span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO COMPONENTS (Zona 3 — header do portfólio + KPI grid premium)
# ══════════════════════════════════════════════════════════════════════════════


def portfolio_hero(
    *,
    titulo:        str = "PORTFÓLIO",
    valor_atual:   float = 0.0,
    custo_total:   float = 0.0,
    pnl_valor:     float = 0.0,
    pnl_pct:       float = 0.0,
    moeda:         str = "R$",
    serie_valor:   list | None = None,
    data_source:   str = "",
) -> None:
    """
    Hero card grande do portfólio. Substitui o caption "patrimônio atual"
    + 4 metric_card cinzas por um banner único com PL gigante e sparkline.

    Layout: glass card, esquerda = eyebrow + titulo + valor 3xl + delta;
    direita = sparkline grande do valor da carteira.
    """
    is_up   = pnl_valor >= 0
    tone    = "bull" if is_up else "bear"
    tone_c  = "var(--bull)" if is_up else "var(--bear)"
    arrow   = "▲" if is_up else "▼"

    _inject_once(
        "_portfolio_hero_css_v1",
        '.ft-pf-hero{position:relative;display:grid;'
        '  grid-template-columns:1.4fr 1fr;gap:var(--space-5);'
        '  padding:var(--space-5) var(--space-5);'
        '  border-radius:var(--radius-xl);'
        '  background:var(--surface-glass);backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);'
        '  box-shadow:var(--shadow-lg);overflow:hidden;'
        '  margin-bottom:var(--space-3);}'
        '.ft-pf-hero::before{content:"";position:absolute;inset:0;'
        '  background:linear-gradient(135deg,var(--pfh-rgba) 0%,transparent 60%);'
        '  pointer-events:none;}'
        '.ft-pf-hero::after{content:"";position:absolute;left:0;top:0;'
        '  bottom:0;width:3px;background:var(--pfh-tone);'
        '  box-shadow:0 0 16px var(--pfh-tone);}'
        '.ft-pf-left{position:relative;display:flex;flex-direction:column;'
        '  justify-content:center;gap:6px;}'
        '.ft-pf-eyebrow{font-family:var(--font-ui);font-size:.66rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wider);'
        '  color:var(--text-muted);font-weight:600;'
        '  display:inline-flex;align-items:center;gap:6px;}'
        '.ft-pf-eyebrow .ic{font-size:.85rem;}'
        '.ft-pf-sublabel{font-family:var(--font-ui);font-size:var(--text-xs);'
        '  color:var(--text-muted);margin-top:2px;}'
        '.ft-pf-value{font-family:var(--font-data);font-size:var(--text-3xl);'
        '  font-weight:800;color:var(--text-primary);'
        '  letter-spacing:var(--ls-tight);line-height:1.1;'
        '  margin-top:var(--space-1);}'
        '.ft-pf-value .cur{font-size:var(--text-md);'
        '  color:var(--text-muted);font-weight:600;margin-right:6px;}'
        '.ft-pf-delta{display:inline-flex;align-items:baseline;gap:8px;'
        '  margin-top:var(--space-2);font-family:var(--font-data);}'
        '.ft-pf-delta .pct{font-size:var(--text-md);font-weight:700;'
        '  display:inline-flex;align-items:center;gap:3px;}'
        '.ft-pf-delta .abs{font-size:var(--text-xs);'
        '  color:var(--text-muted);}'
        '.ft-pf-right{position:relative;display:flex;align-items:center;'
        '  justify-content:flex-end;}'
        '.ft-pf-spark-wrap{width:100%;max-width:340px;}'
        '.ft-pf-spark-wrap svg{width:100%;height:80px;}'
        '@media (max-width:900px){.ft-pf-hero{grid-template-columns:1fr;}'
        '  .ft-pf-right{justify-content:flex-start;}}'
    )

    # rgba derivado pro gradient bg
    rgba = "rgba(74,222,128,0.10)" if is_up else "rgba(248,113,113,0.10)"

    # Formatar valores
    def _fmt_money(v: float) -> str:
        try:
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return f"{v}"

    valor_html = _fmt_money(valor_atual)
    pnl_abs_html = _fmt_money(abs(pnl_valor))
    sub_html = f"vs custo {moeda} {_fmt_money(custo_total)}" if custo_total else ""

    # Sparkline grande (80px alto)
    spark = ""
    if serie_valor and len(serie_valor) >= 2:
        spark = inline_sparkline(serie_valor, tone=tone, largura=320, altura=80)

    src_html = ""
    if data_source:
        ic = "📦" if data_source == "cache" else "📡"
        src_html = (
            f' <span style="font-size:.6rem;color:var(--text-muted);'
            f'opacity:.6;margin-left:8px;">{ic} {data_source}</span>'
        )

    st.markdown(
        f'<div class="ft-pf-hero" '
        f'style="--pfh-tone:{tone_c};--pfh-rgba:{rgba};">'
        f'<div class="ft-pf-left">'
        f'<span class="ft-pf-eyebrow"><span class="ic">💼</span>{titulo}'
        f'{src_html}</span>'
        f'<div class="ft-pf-value"><span class="cur">{moeda}</span>{valor_html}</div>'
        f'<div class="ft-pf-sublabel">{sub_html}</div>'
        f'<div class="ft-pf-delta">'
        f'<span class="pct" style="color:{tone_c};">{arrow} {abs(pnl_pct):.2f}%</span>'
        f'<span class="abs">({"+" if is_up else "-"}{moeda} {pnl_abs_html})</span>'
        f'</div>'
        f'</div>'
        f'<div class="ft-pf-right"><div class="ft-pf-spark-wrap">{spark}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def portfolio_kpis(items: list[dict]) -> None:
    """
    Grid de KPI cards para o portfólio — mais rico que kpi_index_row.

    Cada item:
      {nome, valor (str/num), sublabel (opc), var_pct (opc),
       serie (opc), tone (opc — auto pelo var_pct), icone (opc),
       ticker_chip (opc — destaca ticker como label primário) }
    """
    if not items:
        return

    _inject_once(
        "_portfolio_kpis_css_v1",
        '.ft-pfk-row{display:grid;'
        '  grid-template-columns:repeat(4,minmax(0,1fr));'
        '  gap:var(--space-3);margin-bottom:var(--space-4);}'
        '.ft-pfk-card{position:relative;padding:14px 16px;'
        '  border-radius:var(--radius-lg);background:var(--surface-glass);'
        '  backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);overflow:hidden;'
        '  transition:transform var(--motion-fast) var(--ease-out),'
        '             border-color var(--motion-fast) var(--ease-out);}'
        '.ft-pfk-card:hover{transform:translateY(-2px);'
        '  border-color:var(--border-normal);}'
        '.ft-pfk-card::after{content:"";position:absolute;left:0;top:0;'
        '  width:100%;height:2px;background:var(--pfk-tone);'
        '  box-shadow:0 0 10px var(--pfk-tone);opacity:.85;}'
        '.ft-pfk-head{display:flex;justify-content:space-between;'
        '  align-items:center;margin-bottom:6px;}'
        '.ft-pfk-name{font-family:var(--font-ui);font-size:.66rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  color:var(--text-muted);font-weight:600;}'
        '.ft-pfk-icon{font-size:.95rem;opacity:.75;}'
        '.ft-pfk-ticker{display:inline-block;font-family:var(--font-data);'
        '  font-size:.62rem;font-weight:700;color:var(--pfk-tone);'
        '  background:var(--bg-elevated);border:1px solid var(--pfk-tone);'
        '  border-radius:var(--radius-sm);padding:1px 6px;'
        '  letter-spacing:var(--ls-wide);margin-bottom:4px;}'
        '.ft-pfk-value{font-family:var(--font-data);font-size:var(--text-xl);'
        '  font-weight:700;color:var(--text-primary);line-height:1.15;'
        '  letter-spacing:var(--ls-tight);}'
        '.ft-pfk-sub{font-family:var(--font-ui);font-size:var(--text-xs);'
        '  color:var(--text-muted);margin-top:3px;}'
        '.ft-pfk-foot{display:flex;justify-content:space-between;'
        '  align-items:center;margin-top:10px;gap:8px;min-height:22px;}'
        '.ft-pfk-delta{font-family:var(--font-data);font-size:var(--text-sm);'
        '  font-weight:600;display:inline-flex;align-items:center;gap:3px;}'
        '@media (max-width:900px){.ft-pfk-row{grid-template-columns:repeat(2,1fr);}}'
        '@media (max-width:500px){.ft-pfk-row{grid-template-columns:1fr;}}'
    )

    cards: list[str] = []
    for it in items:
        nome    = it.get("nome", "")
        valor   = it.get("valor", "")
        sub     = it.get("sublabel", "")
        var_pct = it.get("var_pct")
        serie   = it.get("serie") or []
        icone   = it.get("icone", "")
        ticker  = it.get("ticker_chip", "")
        tone_in = it.get("tone")

        # Determina tom
        if tone_in in ("bull", "bear", "amber", "info", "accent"):
            tone = tone_in
        elif var_pct is not None:
            tone = "bull" if float(var_pct) >= 0 else "bear"
        else:
            tone = "info"

        tone_c = {
            "bull":   "var(--bull)",
            "bear":   "var(--bear)",
            "amber":  "var(--amber)",
            "info":   "var(--info)",
            "accent": "var(--accent)",
        }.get(tone, "var(--info)")

        # Delta
        delta_html = ""
        if var_pct is not None:
            arrow = "▲" if float(var_pct) >= 0 else "▼"
            delta_html = (
                f'<span class="ft-pfk-delta" style="color:{tone_c};">'
                f'{arrow} {abs(float(var_pct)):.2f}%</span>'
            )

        # Sparkline mini
        spark = ""
        if len(serie) >= 2:
            spark = inline_sparkline(serie, tone=tone, largura=78, altura=20)

        # Valor (aceita string ou número)
        if isinstance(valor, (int, float)):
            v = float(valor)
            if abs(v) >= 1000:
                valor_fmt = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            else:
                valor_fmt = f"{v:.2f}".replace(".", ",")
        else:
            valor_fmt = str(valor)

        ticker_html = (
            f'<span class="ft-pfk-ticker">{ticker}</span>' if ticker else ""
        )
        icone_html = (
            f'<span class="ft-pfk-icon">{icone}</span>' if icone else ""
        )
        sub_html = f'<div class="ft-pfk-sub">{sub}</div>' if sub else ""

        cards.append(
            f'<div class="ft-pfk-card" style="--pfk-tone:{tone_c};">'
            f'<div class="ft-pfk-head">'
            f'<span class="ft-pfk-name">{nome}</span>{icone_html}'
            f'</div>'
            f'{ticker_html}'
            f'<div class="ft-pfk-value">{valor_fmt}</div>'
            f'{sub_html}'
            f'<div class="ft-pfk-foot">{delta_html}{spark}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="ft-pfk-row">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# EVENTS / TIMELINE COMPONENTS (polimento Home)
# ══════════════════════════════════════════════════════════════════════════════


def events_strip(eventos: list[dict]) -> None:
    """
    Strip de próximos eventos econômicos — countdown elegante.

    Cada evento: {
      "data": str (DD/MM/YYYY),
      "dias": int (até o evento),
      "titulo": str (ex: "COPOM — juros"),
      "categoria": "brasil"|"eua"|"global",
      "impacto": "alto"|"medio"|"baixo",
    }
    """
    if not eventos:
        return

    _inject_once(
        "_events_strip_css_v1",
        '.ft-evt-row{display:grid;'
        '  grid-template-columns:repeat(auto-fit, minmax(180px,1fr));'
        '  gap:var(--space-3);margin-bottom:var(--space-4);}'
        '.ft-evt-card{position:relative;display:flex;flex-direction:column;'
        '  padding:14px 16px;border-radius:var(--radius-lg);'
        '  background:var(--surface-glass);'
        '  backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);overflow:hidden;'
        '  transition:transform var(--motion-fast) var(--ease-out),'
        '             border-color var(--motion-fast) var(--ease-out);}'
        '.ft-evt-card:hover{transform:translateY(-2px);'
        '  border-color:var(--border-normal);}'
        '.ft-evt-card::before{content:"";position:absolute;left:0;top:0;'
        '  bottom:0;width:3px;background:var(--evt-tone);'
        '  box-shadow:0 0 10px var(--evt-tone);}'
        '.ft-evt-head{display:flex;justify-content:space-between;'
        '  align-items:center;margin-bottom:8px;}'
        '.ft-evt-cat{font-family:var(--font-ui);font-size:.6rem;'
        '  font-weight:700;text-transform:uppercase;'
        '  letter-spacing:var(--ls-wider);color:var(--evt-tone);'
        '  display:inline-flex;align-items:center;gap:5px;}'
        '.ft-evt-imp{font-family:var(--font-ui);font-size:.58rem;'
        '  font-weight:700;color:var(--evt-imp-c);'
        '  background:var(--bg-elevated);'
        '  border:1px solid var(--evt-imp-c);border-radius:var(--radius-sm);'
        '  padding:1px 6px;text-transform:uppercase;'
        '  letter-spacing:var(--ls-wide);}'
        '.ft-evt-titulo{font-family:var(--font-ui);font-size:var(--text-sm);'
        '  color:var(--text-primary);font-weight:600;'
        '  line-height:1.3;margin-bottom:10px;flex:1;}'
        '.ft-evt-foot{display:flex;align-items:baseline;'
        '  justify-content:space-between;margin-top:auto;'
        '  padding-top:8px;border-top:1px solid var(--border-subtle);}'
        '.ft-evt-data{font-family:var(--font-data);font-size:.72rem;'
        '  color:var(--text-secondary);font-weight:600;}'
        '.ft-evt-count{font-family:var(--font-data);font-size:.7rem;'
        '  color:var(--evt-cd-c);font-weight:700;'
        '  display:inline-flex;align-items:baseline;gap:3px;}'
        '.ft-evt-count .n{font-size:1.15rem;}'
    )

    _cat_map = {
        "brasil": ("🇧🇷 brasil", "var(--bull)"),
        "eua":    ("🇺🇸 eua",    "var(--info)"),
        "global": ("🌐 global",   "var(--accent)"),
    }

    cards: list[str] = []
    for ev in eventos:
        dias     = int(ev.get("dias", 99))
        categ    = ev.get("categoria", "global")
        impacto  = ev.get("impacto", "medio")
        titulo   = ev.get("titulo", "")
        data     = ev.get("data", "")

        cat_lbl, tone_c = _cat_map.get(categ, _cat_map["global"])

        # Cor do impacto
        imp_c = {
            "alto":  "var(--bear)",
            "medio": "var(--amber)",
            "baixo": "var(--text-muted)",
        }.get(impacto, "var(--text-muted)")

        # Cor do countdown (urgência)
        cd_c = (
            "var(--bear)"  if dias <= 2 else
            "var(--amber)" if dias <= 7 else
            "var(--text-secondary)"
        )

        # Sufixo do countdown
        if dias <= 0:
            cd_label = "hoje"
            cd_n = ""
        elif dias == 1:
            cd_label = "amanhã"
            cd_n = ""
        else:
            cd_label = f"{dias}d"
            cd_n = ""

        cards.append(
            f'<div class="ft-evt-card" '
            f'style="--evt-tone:{tone_c};--evt-imp-c:{imp_c};--evt-cd-c:{cd_c};">'
            f'<div class="ft-evt-head">'
            f'<span class="ft-evt-cat">{cat_lbl}</span>'
            f'<span class="ft-evt-imp">{impacto}</span>'
            f'</div>'
            f'<div class="ft-evt-titulo">{titulo}</div>'
            f'<div class="ft-evt-foot">'
            f'<span class="ft-evt-data">{data}</span>'
            f'<span class="ft-evt-count">em <span class="n">{cd_label}</span></span>'
            f'</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="ft-evt-row">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def pill_select(
    labels: list[str],
    key:    str,
    default: str | None = None,
) -> str:
    """
    Seletor estilo pill mais compacto que tabs_pill (para usar em ordenacao).
    Retorna o label selecionado. Persiste em session_state[key].

    Diferenca pra tabs_pill: visual menor, sem fundo gradient (so border ativo).
    """
    if not labels:
        return ""
    current = st.session_state.get(key) or default or labels[0]
    if current not in labels:
        current = labels[0]

    _inject_once(
        "_pillselect_css_v1",
        'div[data-fpsel="1"]+div [data-testid="column"] .stButton button{'
        '  background:transparent !important;'
        '  border:1px solid var(--border-subtle) !important;'
        '  border-radius:var(--radius-sm) !important;'
        '  color:var(--text-secondary) !important;'
        '  padding:4px 10px !important;'
        '  font-family:var(--font-ui) !important;'
        '  font-size:var(--text-xs) !important;'
        '  font-weight:500 !important;'
        '  width:100% !important;'
        '  box-shadow:none !important;'
        '  transition:all var(--motion-fast) var(--ease-out) !important;}'
        'div[data-fpsel="1"]+div [data-testid="column"] .stButton button:hover{'
        '  border-color:var(--border-normal) !important;'
        '  color:var(--text-primary) !important;}'
        'div[data-fpsel="1"]+div [data-testid="column"] .stButton button[kind="primary"]{'
        '  background:var(--bg-elevated) !important;'
        '  color:var(--accent) !important;'
        '  border-color:var(--accent) !important;'
        '  font-weight:600 !important;}'
    )

    st.markdown('<div data-fpsel="1"></div>', unsafe_allow_html=True)
    cols = st.columns(len(labels), gap="small")
    for i, lab in enumerate(labels):
        with cols[i]:
            if st.button(
                lab,
                key=f"{key}__{i}",
                type="primary" if lab == current else "secondary",
                use_container_width=True,
            ):
                st.session_state[key] = lab
                st.rerun()
    return current


def watchlist_selector_header(
    watchlists: list[dict],
    ativa_id: int | None,
    *,
    key_prefix: str = "wl_sel",
) -> tuple[int | None, str | None]:
    """
    Header bonito do seletor de watchlist — substitui o columns([5,2,1]).

    Retorna (watchlist_id_selecionada, acao_clicada) onde acao ∈ {None, "criar", "config"}.

    Renderiza:
      - linha superior: titulo "minhas watchlists" + counts
      - tabs_pill com cada watchlist (icone + nome)
      - botões finos à direita: ➕ nova · ⚙ config
    """
    if not watchlists:
        # Sem watchlists: estado vazio + botão criar
        st.markdown(
            '<div style="text-align:center;padding:24px;'
            'border:1px dashed var(--border-subtle);border-radius:var(--radius-md);'
            'color:var(--text-muted);font-family:var(--font-ui);">'
            '<div style="font-size:1.5rem;margin-bottom:8px;opacity:.6;">📋</div>'
            'sem watchlists. crie a primeira pra começar.</div>',
            unsafe_allow_html=True,
        )
        if st.button("➕ criar primeira watchlist", type="primary",
                     use_container_width=True, key=f"{key_prefix}_primeira"):
            return (None, "criar")
        return (None, None)

    _inject_once(
        "_wl_selector_css_v1",
        '.ft-wl-header{display:flex;align-items:center;'
        '  justify-content:space-between;'
        '  margin-bottom:8px;padding-bottom:8px;'
        '  border-bottom:1px solid var(--border-subtle);}'
        '.ft-wl-title{font-family:var(--font-ui);font-size:.7rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wider);'
        '  color:var(--text-muted);font-weight:600;'
        '  display:inline-flex;align-items:center;gap:6px;}'
        '.ft-wl-counts{font-family:var(--font-data);font-size:.7rem;'
        '  color:var(--text-secondary);}'
    )

    # Header textual
    st.markdown(
        f'<div class="ft-wl-header">'
        f'<span class="ft-wl-title">📋 minhas watchlists</span>'
        f'<span class="ft-wl-counts">{len(watchlists)} listas</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Linha principal: tabs_pill com nomes + botões à direita
    nomes = [f"{wl.get('icone', '⭐')} {wl.get('nome', '?')}" for wl in watchlists]
    id_por_nome = {f"{wl.get('icone', '⭐')} {wl.get('nome', '?')}": wl['id']
                   for wl in watchlists}
    nome_por_id = {wl['id']: f"{wl.get('icone', '⭐')} {wl.get('nome', '?')}"
                   for wl in watchlists}

    default_lbl = nome_por_id.get(ativa_id, nomes[0]) if ativa_id else nomes[0]

    col_tabs, col_btns = st.columns([7, 3])
    with col_tabs:
        escolhida = tabs_pill(nomes, key=f"{key_prefix}_pick", default=default_lbl)
    with col_btns:
        sub1, sub2 = st.columns(2)
        acao = None
        with sub1:
            if st.button("➕ nova", key=f"{key_prefix}_btn_nova",
                         use_container_width=True):
                acao = "criar"
        with sub2:
            if st.button("⚙ config", key=f"{key_prefix}_btn_cfg",
                         use_container_width=True):
                acao = "config"

    wl_id = id_por_nome.get(escolhida)
    return (wl_id, acao)
