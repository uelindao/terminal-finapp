"""
utils/components.py — v4.1
Componentes HTML do design system.
Fase 3a: 100% tokens — sem hex/font hardcoded; usa var(--font-{title,ui,data})
e var(--text-*)/--space-*/--ls-*. Cores via var(--bg-*/--text-*/--accent/etc).
"""
import warnings as _warnings
import streamlit as st
import time
import re as _re
from html import escape as _escape


def _clean_label(label: str) -> str:
    """Remove decoração inicial, preservando símbolos no conteúdo financeiro."""
    text = _re.sub(r"^[^\wÀ-ÿ]+", "", str(label)).strip()
    text = text[:1].upper() + text[1:]
    for acronym in ("IA", "P/L", "P/VP", "ROE", "ROIC", "EBITDA", "RSI", "MACD", "DY", "CAGR", "YTD", "USD", "BRL", "ETF", "FIIs", "VaR", "CVaR"):
        text = _re.sub(r"(?<!\w)" + _re.escape(acronym) + r"(?!\w)", acronym, text, flags=_re.I)
    return text



def ticker_nav_url(ticker: str) -> str:
    """Gera URL de navegação para Research com token de sessão embutido."""
    from urllib.parse import urlencode
    params = {"research_ticker": ticker}
    if st.session_state.get('session_token'):
        params["s"] = st.session_state['session_token']
    for key in ("theme", "profile", "density"):
        value = st.query_params.get(key)
        if value:
            params[key] = value
    return "?" + urlencode(params)

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
        appearance_params = {key: st.query_params.get(key) for key in ("theme", "profile", "density") if st.query_params.get(key)}
        st.query_params.clear()
        st.query_params.update(appearance_params)
        if _s:
            st.query_params["s"] = _s
        st.session_state['research_ticker_externo'] = _rt
        st.switch_page("pages/1_Research.py")


def page_header(titulo: str, subtitulo: str = ""):
    """Hierarquia editorial, com título sem decoração e descrição útil."""
    title = _clean_label(titulo)
    st.markdown(
        '<header class="ft-page-header">'
        '<div class="ft-page-eyebrow">FinTerminal / Análise pessoal</div>'
        f'<h1>{_escape(title)}</h1>'
        + (f'<p>{_escape(subtitulo)}</p>' if subtitulo else '') + '</header>',
        unsafe_allow_html=True,
    )


def section_title(titulo: str):
    """Uma hierarquia de seção legível, sem ruído de ícones coloridos."""
    st.markdown(f'<h2 class="ft-section-title">{_escape(_clean_label(titulo))}</h2>', unsafe_allow_html=True)



def _attention_cards_html(itens: list[dict]) -> str:
    """Cartões de sinais com links de análise e conteúdo escapado."""
    categories = {"score": "Score", "tecnico": "Técnico", "evento": "Agenda", "divergencia": "Macro"}
    cards = []
    for item in itens:
        tone = item.get("tom", "info")
        if tone not in ("bull", "bear", "amber", "info"):
            tone = "info"
        category = categories.get(item.get("tipo"), "Sinal")
        title = _escape(str(item.get("titulo", "Sinal de mercado")))
        detail = _escape(str(item.get("detalhe", "")))
        content = (
            '<div class="ft-attention-card-top">'
            f'<span class="ft-attention-type">{category}</span>'
            + ('<span class="ft-attention-open" aria-hidden="true">↗</span>' if item.get("ticker") else '')
            + '</div>'
            f'<strong class="ft-attention-title">{title}</strong>'
            f'<span class="ft-attention-detail">{detail}</span>'
        )
        attributes = f'class="ft-attention-card" style="--attention-tone:var(--{tone if tone != "info" else "accent"})"'
        if item.get("ticker"):
            href = _escape(ticker_nav_url(str(item["ticker"])), quote=True)
            cards.append(f'<a {attributes} href="{href}" target="_self">{content}</a>')
        else:
            cards.append(f'<div {attributes}>{content}</div>')
    return '<div class="ft-attention-grid">' + ''.join(cards) + '</div>'


def attention_panel(itens: list[dict], *, limite: int = 6) -> None:
    """Seis sinais prioritários num relance; o restante fica acessível recolhido.

    A ordem vem do motor de sinais; a apresentação não altera seu ranking.
    """
    limit = max(1, int(limite))
    visible, remaining = itens[:limit], itens[limit:]
    total = len(itens)
    count = f"{len(visible)} de {total} sinais" if remaining else ("1 sinal" if total == 1 else f"{total} sinais")
    heading = (
        '<div class="ft-attention-heading">'
        '<h2>Atenção hoje</h2>'
        + (f'<span class="ft-attention-count">{count}</span>' if total else '')
        + '</div>'
    )
    body = _attention_cards_html(visible) if visible else (
        '<div class="ft-attention-empty">Sem sinais novos na watchlist ou na agenda de hoje.</div>'
    )
    st.markdown('<section class="ft-attention-panel" aria-label="Sinais prioritários">' + heading + body + '</section>', unsafe_allow_html=True)
    if remaining:
        label = "Mais 1 sinal" if len(remaining) == 1 else f"Mais {len(remaining)} sinais"
        with st.expander(label, expanded=False):
            st.markdown(_attention_cards_html(remaining), unsafe_allow_html=True)


def section_selector(secoes: list[str], key: str, *, label: str = "Seção",
                     default: str | None = None) -> str:
    """Uma seção sempre selecionada; rótulos visuais sem alterar as chaves antigas."""
    if not secoes:
        return ""
    preferred = default if default in secoes else secoes[0]
    previous_key = f"_section_previous_{key}"
    current = st.session_state.get(key)
    if current not in secoes:
        remembered = st.session_state.get(previous_key)
        st.session_state[key] = remembered if remembered in secoes else preferred
    st.session_state[previous_key] = st.session_state[key]
    def changed():
        selected = st.session_state.get(key)
        if selected not in secoes:
            st.session_state[key] = st.session_state.get(previous_key, preferred)
        else:
            st.session_state[previous_key] = selected
    if hasattr(st, "segmented_control"):
        return st.segmented_control(
            label, secoes, key=key, format_func=_clean_label,
            label_visibility="collapsed", on_change=changed,
        ) or st.session_state.get(key) or preferred
    return st.radio(label, secoes, key=key, horizontal=True,
                    format_func=_clean_label, label_visibility="collapsed")


def _fonte_badge(fonte: str = "") -> str:
    if not fonte:
        return ""
    icone = "📦" if fonte == "cache" else "📡"
    cor = "var(--bull)" if fonte == "cache" else "var(--accent)"
    return f'<span style="font-size:0.78rem; color:{cor}; margin-left:5px; font-weight:400; opacity:0.7;">{icone} {fonte}</span>'


def metric_card(label: str, valor: str, sublabel: str = "", cor_delta: str = "muted",
                icone: str = "", destaque: bool = False, data_source: str = ""):
    """Número primeiro, contexto abaixo; cor semântica no contexto da métrica."""
    tone = cor_delta if cor_delta in ("bull", "bear", "amber", "info") else "muted"
    source = f'<span class="ft-source">{_escape(data_source)}</span>' if data_source else ''
    emphasis = ' ft-metric-highlight' if destaque else ''
    st.html(
        f'<div class="metric-card ft-metric{emphasis}">'
        f'<div class="ft-metric-label">{_escape(_clean_label(label))}{source}</div>'
        f'<div class="ft-metric-value">{_escape(str(valor))}</div>'
        + (f'<div class="ft-metric-sub color-{tone}">{_escape(sublabel)}</div>' if sublabel else '')
        + '</div>',
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
    """Cabeçalho da lista; cada célula também tem rótulo próprio no celular."""
    st.markdown('<div class="ft-watchlist-header"><span>Ativo</span><span>Preço</span>'
                '<span>Hoje</span><span>1 mês</span><span>30 dias</span><span>Qualidade</span></div>', unsafe_allow_html=True)


def watchlist_row(ticker: str, nome: str, preco: float, var_1d: float,
                  var_1m: float = 0.0, moeda: str = "R$", health_score: float | None = None,
                  alertas: list | None = None, earnings_info: dict | None = None,
                  data_source: str = "", serie_30d: list | None = None):
    """Lista adaptável: dados escaneáveis e ações nativas em um menu por ativo."""
    from utils.formatters import fmt_preco
    has_price = preco is not None and preco > 0
    price = fmt_preco(preco, moeda) if has_price else "—"
    def delta(value):
        if not has_price or value is None:
            return '<span class="color-muted">—</span>'
        tone = "bull" if value >= 0 else "bear"
        arrow = "▲" if value >= 0 else "▼"
        return f'<span class="color-{tone}">{arrow} {abs(value):.2f}%</span>'
    if health_score is not None:
        score = float(health_score)
        tone = "bull" if score >= 65 else "amber" if score >= 40 else "bear"
        health = f'<span class="color-{tone}">{int(score)}<span class="ft-watchlist-max"> / 100</span></span>'
    else:
        health = '<span class="color-muted">—</span>'
    spark = inline_sparkline(serie_30d, tone="auto" if var_1m is None else "bull" if var_1m >= 0 else "bear", largura=110, altura=28) if serie_30d is not None and len(serie_30d) >= 2 else '<span class="color-muted">—</span>'
    notice = ''
    if alertas:
        notice = f'<span class="ft-watchlist-alert" title="{_escape(str(alertas[0]), quote=True)}">Atenção</span>'
    if earnings_info and 0 <= earnings_info.get("dias", 99) <= 14:
        notice += f'<span class="ft-watchlist-event">Resultado em {earnings_info["dias"]}d</span>'
    main, actions = st.columns([10, 1.4], vertical_alignment="center")
    with main:
        st.markdown(
            '<div class="ft-watchlist-row">'
            f'<div class="ft-watchlist-asset"><a href="{_escape(ticker_nav_url(ticker), quote=True)}" target="_self" class="ticker-nav">{_escape(ticker.replace(".SA", ""))}</a>'
            f'<span class="ft-watchlist-name">{_escape(nome)}</span><div class="ft-watchlist-notices">{notice}</div></div>'
            f'<div class="ft-watchlist-cell"><span class="ft-watchlist-mobile-label">Preço</span>{_escape(price)}</div>'
            f'<div class="ft-watchlist-cell"><span class="ft-watchlist-mobile-label">Hoje</span>{delta(var_1d)}</div>'
            f'<div class="ft-watchlist-cell"><span class="ft-watchlist-mobile-label">1 mês</span>{delta(var_1m)}</div>'
            f'<div class="ft-watchlist-spark">{spark}</div>'
            f'<div class="ft-watchlist-cell"><span class="ft-watchlist-mobile-label">Qualidade</span>{health}</div></div>',
            unsafe_allow_html=True,
        )
    with actions:
        with st.popover("Opções", use_container_width=True):
            st.caption(f"Ações para {ticker.replace('.SA', '')}")
            if st.button("Ver análise do score", key=f"mem_{ticker}", icon=":material/insights:", use_container_width=True):
                st.session_state[f"show_memorial_{ticker}"] = True
            if st.button("Remover da watchlist", key=f"del_{ticker}", icon=":material/delete_outline:", use_container_width=True):
                st.session_state[f"confirm_del_{ticker}"] = True


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
            f' font-size:0.78rem; color:var(--text-muted);">health</span>'
            f'<span style="font-family:var(--font-data);'
            f' font-size:0.78rem; color:{cor_hs};'
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
            f' font-size:0.78rem; color:var(--text-muted);'
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
            f' font-size:0.78rem; color:{cor_e};'
            f' border:1px solid {cor_e}; padding:1px 4px;'
            f' border-radius:4px; margin-left:5px;'
            f' vertical-align:middle;">res·{dias_e}d</span>'
        )

    _alert_badge = (
        '<span style="font-family:var(--font-ui); font-size:0.78rem;'
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
        f' font-size:0.78rem; color:var(--text-muted);'
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
    """Estado vazio com título e orientação legíveis em qualquer tema."""
    st.markdown(
        '<div class="ft-empty">'
        f'<div class="ft-empty-icon" aria-hidden="true">{_escape(icone)}</div>'
        f'<h3>{_escape(_clean_label(titulo))}</h3><p>{_escape(descricao)}</p></div>',
        unsafe_allow_html=True,
    )


def progress_steps(steps: list[str], current: int):
    """Progress steps."""
    items = "".join([
        f'<div style="display:flex; align-items:center;'
        f' gap:5px; font-family:var(--font-ui);'
        f' font-size:0.78rem; font-weight:500;'
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
                f' font-size:0.78rem; font-weight:600;'
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
        f' font-size:0.78rem; color:var(--text-muted);'
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
        Alt+1 → Home           Alt+2 → Research
        Alt+3 → Discovery      Alt+4 → Macro
        Alt+5 → Portfolio      Alt+6 → Configurações
        Enter → confirma apenas dentro do formulário ativo
    """
    import json
    from utils.tickers import SCREENER_B3, SCREENER_US, FII_TODOS

    # Tickers para o command palette (limpa sufixo .SA para exibição)
    tickers_b3  = [{"t": t.replace(".SA", ""), "f": "🇧🇷", "full": t} for t in SCREENER_B3]
    tickers_fii = [{"t": t.replace(".SA", ""), "f": "🏢",  "full": t} for t in FII_TODOS]
    tickers_us  = [{"t": t,                    "f": "🇺🇸", "full": t} for t in SCREENER_US]
    tickers_json = json.dumps(tickers_b3 + tickers_fii + tickers_us)

    pages_json = json.dumps([
        {"label": "Visão geral",          "icon": "⚡", "nav": "Home",          "key": "1"},
        {"label": "Análise de ativos",      "icon": "🔬", "nav": "Research",      "key": "2"},
        {"label": "Oportunidades",     "icon": "🔍", "nav": "Discovery",     "key": "3"},
        {"label": "Macro",         "icon": "🌐", "nav": "Macro",         "key": "4"},
        {"label": "Carteira",     "icon": "💼", "nav": "Portfolio",     "key": "5"},
        {"label": "Configurações", "icon": "⚙",  "nav": "Configuracoes", "key": "6"},
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
            font-size:0.78rem;color:var(--text-secondary);margin-right:2px;}}
        #finterm-results{{max-height:340px;overflow-y:auto;padding:6px;}}
        #finterm-results::-webkit-scrollbar{{width:4px;}}
        #finterm-results::-webkit-scrollbar-thumb{{background:var(--border-normal);border-radius:2px;}}
        .ft-section{{font-size:0.78rem;color:var(--text-muted);padding:6px 14px 2px;
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
        .ft-desc{{font-size:0.78rem;color:var(--text-muted);margin-top:1px;}}
        .ft-badge{{font-size:0.78rem;padding:2px 7px;border-radius:var(--radius-sm);
            background:var(--border-subtle);color:var(--text-secondary);flex-shrink:0;
            font-family:var(--font-data);}}
        .ft-badge.page{{background:var(--pill-accent-bg);color:var(--accent);}}
        #finterm-footer{{padding:var(--space-2) var(--space-5);border-top:1px solid var(--border-subtle);
            display:flex;gap:var(--space-4);align-items:center;font-size:var(--text-xs);
            color:var(--text-muted);font-family:var(--font-ui);}}
        #finterm-toasts{{position:fixed;top:20px;right:20px;z-index:99999;
            display:flex;flex-direction:column;gap:var(--space-2);pointer-events:none;}}
        .ft-toast{{background:var(--surface-glass);backdrop-filter:var(--glass-blur);
            -webkit-backdrop-filter:var(--glass-blur);
            border:1px solid var(--border-subtle);border-radius:var(--radius-lg);
            padding:12px 16px;min-width:260px;max-width:360px;
            box-shadow:var(--shadow-xl);display:flex;
            align-items:flex-start;gap:10px;animation:ft-tin .25s var(--ease-out);
            pointer-events:all;overflow:hidden;position:relative;
            font-family:var(--font-ui);}}
        .ft-toast::before{{content:"";position:absolute;left:0;top:0;bottom:0;
            width:3px;background:var(--toast-tone);
            box-shadow:0 0 10px var(--toast-tone);}}
        .ft-toast.out{{animation:ft-tout .18s ease forwards;}}
        .ft-toast-icon{{font-size:1.05rem;flex-shrink:0;margin-top:1px;
            color:var(--toast-tone);}}
        .ft-toast-msg{{font-size:var(--text-sm);color:var(--text-primary);
            line-height:1.4;font-weight:500;flex:1;}}
        .ft-bar-wrap{{position:absolute;bottom:0;left:0;right:0;height:2px;
            background:rgba(255,255,255,.06);}}
        .ft-bar{{height:100%;transition:width linear;width:100%;
            background:var(--toast-tone);
            box-shadow:0 0 6px var(--toast-tone);}}
        .ft-toast.success,.ft-toast.bull{{--toast-tone:var(--bull);}}
        .ft-toast.error,.ft-toast.bear{{--toast-tone:var(--bear);}}
        .ft-toast.warning,.ft-toast.amber{{--toast-tone:var(--amber);}}
        .ft-toast.info{{--toast-tone:var(--info);}}
        .ft-toast.accent{{--toast-tone:var(--accent);}}
        .ft-hint-badge{{position:fixed;bottom:76px;right:20px;z-index:9998;
            background:var(--bg-surface);border:1px solid var(--border-normal);border-radius:var(--radius-sm);
            padding:var(--space-2) var(--space-3);font-size:0.78rem;color:var(--text-secondary);
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
            '<div id="finterm-palette" role="dialog" aria-modal="true" aria-label="Buscar ativo ou página">' +
            '  <input id="finterm-input" type="text" aria-label="Buscar ativo ou página"' +
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
        var links = doc.querySelectorAll('[data-testid="stSidebarNavLink"], [data-testid="stPageLink-NavLink"]');
        for (var i = 0; i < links.length; i++) {{
            var path = new URL(links[i].href).pathname.replace(/\\/$/, '');
            if ((navLabel === 'Home' && !path) || path.endsWith('/' + navLabel)) {{
                links[i].click(); return;
            }}
        }}
        window.parent.location.href =
            window.parent.location.origin + (navLabel === 'Home' ? '/' : '/' + navLabel) + window.parent.location.search;
    }}

    function navTicker(ticker) {{
        var links = doc.querySelectorAll('[data-testid="stSidebarNavLink"], [data-testid="stPageLink-NavLink"]');
        var researchHref = '';
        for (var i = 0; i < links.length; i++) {{
            if (new URL(links[i].href).pathname.endsWith('/Research')) {{
                researchHref = links[i].href || ''; break;
            }}
        }}
        var base = researchHref ||
            (window.parent.location.origin + '/Research');
        // Strip query params from base before adding ours
        base = base.split('?')[0];
        window.parent.location.href =
            base + '?research_ticker=' + encodeURIComponent(ticker) +
            (new URLSearchParams(window.parent.location.search).get('s') ? '&s=' + encodeURIComponent(new URLSearchParams(window.parent.location.search).get('s')) : '');
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
                    'font-size:var(--text-sm);font-family:var(--font-ui);">nenhum resultado para \\"' + q.replace(/[<>]/g, '') + '\\"</div>';
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

    var previousFocus = null;
    function openPalette() {{
        previousFocus = doc.activeElement;
        ov.classList.add('active');
        inp.value = ''; renderResults('');
        setTimeout(function() {{ inp.focus(); }}, 60);
    }}
    function closePalette() {{
        ov.classList.remove('active');
        selIdx = -1;
        if (previousFocus && previousFocus.isConnected) previousFocus.focus();
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
            if (e.key === 'Tab') {{ e.preventDefault(); inp.focus(); return; }}
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

    }});
}})();
</script>
""", height=0, scrolling=False)


def inject_keyboard_shortcuts():
    """Retrocompatibilidade — chama inject_ui_enhancements()."""
    inject_ui_enhancements()


def show_toast(message: str, type: str = "success", duration: int = 3000) -> None:
    """
    Exibe uma notificação toast (canto sup direito) integrada ao design system v5.

    Args:
        message: texto da notificação (HTML básico permitido)
        type:    aceita aliases do design system:
                   'success'/'bull'  → verde (sucesso)
                   'error'/'bear'    → vermelho (erro/destrutivo)
                   'warning'/'amber' → âmbar (atenção)
                   'info'            → azul (informação)
                   'accent'          → cor do tema ativo (destaque neutro)
        duration: ms antes de auto-fechar (default 3000)

    Visual v5:
      - glass background com backdrop-filter
      - border-left luminoso com glow no tone
      - barra de progresso animada para o user "ver" o tempo restante
      - shadow-xl para flutuar acima do conteúdo

    Requer inject_keyboard_shortcuts() / inject_ui_enhancements() na página.
    """
    import streamlit.components.v1 as _comp

    # Mapeia aliases v5 → classes CSS suportadas pelo JS
    _alias = {
        "bull":   "success",
        "bear":   "error",
        "amber":  "warning",
        "accent": "accent",
        "info":   "info",
    }
    _type = _alias.get(type, type)

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
        f"    window.parent._fintermToast('{msg_safe}','{_type}',{duration});"
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


def label_com_tooltip(texto: str, chave: str = "", texto_custom: str = "",
                      cor: str | None = None, tamanho: str = ".85rem") -> None:
    """Rótulo legível com ajuda que também pode receber foco do teclado."""
    description = TOOLTIPS.get(chave, texto_custom)
    help_html = (f'<abbr tabindex="0" title="{_escape(description, quote=True)}" '
                 f'aria-label="{_escape(description, quote=True)}">?</abbr>') if description else ''
    color = cor or "var(--text-secondary)"
    st.markdown(f'<div class="ft-inline-heading" style="color:{color};font-size:max(.82rem,{tamanho});">'
                f'{_escape(_clean_label(texto))} {help_html}</div>', unsafe_allow_html=True)


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
            f'<span style="font-size:0.78rem;font-family:var(--font-data);'
            f'color:{cor_val};margin-left:6px;">{delta}</span>'
        )
    st.markdown(
        f'<div style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
        f'border-radius:var(--radius-md);padding:10px 14px;min-height:64px;'
        f'display:flex;flex-direction:column;justify-content:center;">'
        f'<div style="font-size:0.78rem;font-family:var(--font-ui);color:var(--text-muted);'
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
                f'<span style="font-size:0.78rem;font-family:var(--font-data);'
                f'color:{cor};">{status_line}</span>'
            )
        else:
            preco_fmt = f"{preco:,.0f}" if preco >= 1_000 else f"{preco:.2f}"
            var_html  = (
                f'<span style="font-size:0.78rem;font-family:var(--font-data);'
                f'color:{cor};">{sinal} {abs(var):.2f}%</span>'
            )
        items.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'justify-content:center;text-align:center;'
            f'flex:1;padding:6px 8px;'
            f'border-right:1px solid var(--border-subtle);gap:2px;">'
            f'<span style="font-size:0.78rem;color:var(--text-muted);'
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
    if serie is None or len(serie) == 0:
        return ""
    from math import isfinite
    vals = []
    for value in serie:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if isfinite(number):
            vals.append(number)
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
    """
    Helper: injeta um bloco de CSS — sempre escreve no markdown.

    Por que sempre injetar (não cachear via session_state)?
    Streamlit re-executa o script inteiro a cada rerun, mas o DOM é
    reconstruído. Se cachearmos em session_state e pularmos `st.markdown`,
    o <style> some do DOM ao mesmo tempo que a flag persiste — resultado:
    componentes renderizam sem CSS (texto cru).

    A duplicação não é problema: o React do Streamlit faz dedup por chave
    estável e múltiplos <style> idênticos só somam uma regra ao CSSOM.
    O parâmetro `key` é mantido por compatibilidade (não usado mais).
    """
    st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)


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
    """Abas nativas: conteúdo sob demanda, sem colunas vazias ou rerun adicional."""
    return section_selector(labels, key, default=default)


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


def topbar(breadcrumb_itens: list[tuple[str, str | None]] | None = None, *,
           show_search: bool = True, show_user: bool = True, show_sync: bool = True,
           user_name: str = "", sync_label: str = "") -> None:
    """Contexto e busca nativa: funciona por mouse, toque e teclado."""
    names = {"finterminal": "FinTerminal", "home": "Visão geral", "research": "Análise de ativos",
             "discovery": "Oportunidades", "macro": "Cenário macro", "portfolio": "Carteira"}
    parts = [_escape(names.get(_clean_label(label).lower(), _clean_label(label)))
             for label, _ in (breadcrumb_itens or [("FinTerminal", None)])]
    left = ' <span aria-hidden="true">/</span> '.join(parts)
    status = '<span class="ft-topbar-pill">Atualizações periódicas</span>' if show_sync else ''
    user = f'<span class="ft-topbar-user">{_escape(user_name)}</span>' if show_user and user_name else ''
    context, search = st.columns([5, 1.4], vertical_alignment="center")
    with context:
        st.markdown(f'<div class="ft-topbar"><div class="ft-topbar-left">{left}</div>'
                    f'<div class="ft-topbar-right">{status}{user}</div></div>', unsafe_allow_html=True)
    if show_search:
        with search:
            with st.popover("Buscar ativo", icon=":material/search:", use_container_width=True):
                st.caption("Digite um ticker ou nome. Ex.: PETR4, AAPL, Nubank.")
                with st.form("_topbar_search_form"):
                    term = st.text_input("Ativo", key="_topbar_search_term", placeholder="Ticker ou empresa")
                    submit = st.form_submit_button("Abrir análise", type="primary", use_container_width=True)
                if submit:
                    ticker = _resolver_ticker_busca(term)
                    if ticker:
                        st.session_state["research_ticker_externo"] = ticker
                        st.switch_page("pages/1_Research.py")
                    else:
                        st.warning("Informe um ticker ou nome válido para encontrar o ativo.")


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
        "_htmltable_css_v7",
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
        '.ft-table td.amber{color:var(--amber);}'
        '.ft-table td.muted{color:var(--text-muted);}'
        '.ft-table td.mono{font-family:var(--font-data);}'
        '.ft-table td.strong{font-weight:600;}'
        '.ft-table td.hl{background:var(--bull-soft,rgba(46,204,113,0.15));}'
        '.ft-table td.hlx{background:var(--accent-soft,rgba(99,179,237,0.10));}'
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
        '  letter-spacing:var(--ls-wide);font-size:0.78rem;'
        '  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
        '.ft-hero-sinal .val{font-family:var(--font-data);'
        '  color:var(--text-primary);font-weight:600;'
        '  font-size:var(--text-xs);}'
        '.ft-hero-fontes{grid-column:1 / -1;display:flex;flex-wrap:wrap;'
        '  gap:6px 12px;padding-top:8px;border-top:1px solid var(--border-subtle);'
        '  margin-top:4px;}'
        '.ft-hero-fontes span{font-family:var(--font-ui);font-size:0.78rem;'
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
        '.ft-kpi-name{font-family:var(--font-ui);font-size:0.78rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  color:var(--text-muted);margin-bottom:6px;'
        '  display:flex;justify-content:space-between;align-items:center;}'
        '.ft-kpi-name .tk{font-size:0.78rem;color:var(--text-muted);opacity:.7;}'
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
        serie  = it.get("serie")
        if serie is None:
            serie = []
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
        '  font-family:var(--font-ui);font-size:0.78rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  color:var(--hs-tone);font-weight:600;}'
        '.ft-hs-head .qt{font-family:var(--font-data);font-size:0.78rem;'
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
        '.ft-mkt-group .ct{font-family:var(--font-data);font-size:0.78rem;'
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
        '.ft-pf-eyebrow{font-family:var(--font-ui);font-size:0.78rem;'
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
    if serie_valor is not None and len(serie_valor) >= 2:
        spark = inline_sparkline(serie_valor, tone=tone, largura=320, altura=80)

    src_html = ""
    if data_source:
        ic = "📦" if data_source == "cache" else "📡"
        src_html = (
            f' <span style="font-size:0.78rem;color:var(--text-muted);'
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
        '.ft-pfk-name{font-family:var(--font-ui);font-size:0.78rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  color:var(--text-muted);font-weight:600;}'
        '.ft-pfk-icon{font-size:.95rem;opacity:.75;}'
        '.ft-pfk-ticker{display:inline-block;font-family:var(--font-data);'
        '  font-size:0.78rem;font-weight:700;color:var(--pfk-tone);'
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
        serie   = it.get("serie")
        if serie is None:
            serie = []
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
        '.ft-evt-cat{font-family:var(--font-ui);font-size:0.78rem;'
        '  font-weight:700;text-transform:uppercase;'
        '  letter-spacing:var(--ls-wider);color:var(--evt-tone);'
        '  display:inline-flex;align-items:center;gap:5px;}'
        '.ft-evt-imp{font-family:var(--font-ui);font-size:0.78rem;'
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
        '.ft-evt-count{font-family:var(--font-data);font-size:0.78rem;'
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


def pill_select(labels: list[str], key: str, default: str | None = None) -> str:
    """Seletor compacto com dimensões naturais para os rótulos."""
    return section_selector(labels, key, default=default)


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
        if st.button("Criar primeira watchlist", type="primary",
                     use_container_width=True, key=f"{key_prefix}_primeira"):
            return (None, "criar")
        return (None, None)

    _inject_once(
        "_wl_selector_css_v1",
        '.ft-wl-header{display:flex;align-items:center;'
        '  justify-content:space-between;'
        '  margin-bottom:8px;padding-bottom:8px;'
        '  border-bottom:1px solid var(--border-subtle);}'
        '.ft-wl-title{font-family:var(--font-ui);font-size:0.78rem;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wider);'
        '  color:var(--text-muted);font-weight:600;'
        '  display:inline-flex;align-items:center;gap:6px;}'
        '.ft-wl-counts{font-family:var(--font-data);font-size:0.78rem;'
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
            if st.button("Nova", key=f"{key_prefix}_btn_nova",
                         use_container_width=True):
                acao = "criar"
        with sub2:
            if st.button("Config", key=f"{key_prefix}_btn_cfg",
                         use_container_width=True):
                acao = "config"

    wl_id = id_por_nome.get(escolhida)
    return (wl_id, acao)


# ══════════════════════════════════════════════════════════════════════════════
# OPPORTUNITY CARD (design system v5 — substitui o card antigo da Home)
# ══════════════════════════════════════════════════════════════════════════════


def opportunity_card(
    *,
    ticker:    str,
    nome:      str,
    setor:     str = "",
    rank:      int = 0,
    score_hs:  float = 0,
    score_val: float = 0,
    score_timing: float = 0,
    rsi:       float = 0,
    ret_5d:    float = 0,
    ret_3m:    float = 0,
    dist_top:  float = 0,
) -> str:
    """
    Retorna HTML de card de oportunidade — glassmorphism + breakdown + stats.

    Use dentro de uma st.column do Streamlit:
        with col:
            st.markdown(opportunity_card(...), unsafe_allow_html=True)
            if st.button(f"Analisar {ticker}", key=...): ...

    Renderiza:
      - ticker grande em accent + medal badge à direita
      - nome em ui-secondary + setor em muted
      - 3 barras de breakdown: qualidade, valuation, timing
      - 4 micro-stats em grid: RSI · 5d · 3m · topo
    """
    _inject_once(
        "_opportunity_card_v1",
        '.ft-opp-card{position:relative;padding:14px 16px;'
        '  border-radius:var(--radius-lg);background:var(--surface-glass);'
        '  backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);overflow:hidden;'
        '  transition:transform var(--motion-fast) var(--ease-out),'
        '             border-color var(--motion-fast) var(--ease-out);'
        '  margin-bottom:8px;}'
        '.ft-opp-card:hover{transform:translateY(-2px);'
        '  border-color:var(--border-normal);}'
        '.ft-opp-card::after{content:"";position:absolute;left:0;top:0;'
        '  width:100%;height:2px;background:var(--accent);'
        '  box-shadow:0 0 10px var(--accent);opacity:.85;}'
        '.ft-opp-head{display:flex;justify-content:space-between;'
        '  align-items:flex-start;margin-bottom:8px;}'
        '.ft-opp-tk{font-family:var(--font-data);font-size:var(--text-md);'
        '  font-weight:800;color:var(--accent);letter-spacing:var(--ls-tight);}'
        '.ft-opp-medal{font-size:1.1rem;line-height:1;}'
        '.ft-opp-name{font-family:var(--font-ui);font-size:var(--text-xs);'
        '  color:var(--text-secondary);line-height:1.35;'
        '  overflow:hidden;text-overflow:ellipsis;'
        '  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;}'
        '.ft-opp-setor{font-family:var(--font-ui);font-size:0.78rem;'
        '  color:var(--text-muted);text-transform:uppercase;'
        '  letter-spacing:var(--ls-wide);margin-top:2px;'
        '  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
        '.ft-opp-bds{margin-top:10px;}'
        '.ft-opp-bd-row{display:flex;justify-content:space-between;'
        '  align-items:center;margin-bottom:3px;}'
        '.ft-opp-bd-row .lb{font-family:var(--font-ui);'
        '  font-size:0.78rem;color:var(--text-muted);}'
        '.ft-opp-bd-row .vl{font-family:var(--font-data);font-size:0.78rem;'
        '  font-weight:600;color:var(--bd-tone);}'
        '.ft-opp-bd-bar{background:var(--bg-overlay);border-radius:2px;'
        '  height:3px;margin-bottom:8px;overflow:hidden;}'
        '.ft-opp-bd-bar-fill{background:var(--bd-tone);border-radius:2px;'
        '  height:100%;box-shadow:0 0 4px var(--bd-tone);'
        '  transition:width var(--motion-base) var(--ease-out);}'
        '.ft-opp-stats{display:grid;grid-template-columns:repeat(4,1fr);'
        '  gap:6px;margin-top:8px;padding-top:8px;'
        '  border-top:1px solid var(--border-subtle);}'
        '.ft-opp-stat{text-align:center;}'
        '.ft-opp-stat .l{font-family:var(--font-ui);font-size:0.78rem;'
        '  color:var(--text-muted);text-transform:uppercase;'
        '  letter-spacing:var(--ls-wide);}'
        '.ft-opp-stat .v{font-family:var(--font-data);font-size:0.78rem;'
        '  font-weight:600;margin-top:1px;}'
    )

    medals = ["01", "02", "03", "04", "05"]
    medal = medals[rank] if 0 <= rank < len(medals) else ""

    # Breakdown bars
    bd_items = [
        ("qualidade (hs)",  score_hs,     100, f"{score_hs:.0f}/100"),
        ("valuation hist.", score_val,    20,  f"{score_val:.0f}/20"),
        ("timing entrada",  score_timing, 25,  f"{score_timing:.0f}/25"),
    ]
    bds_html = ""
    for lbl, val, vmax, vstr in bd_items:
        pct = min(100, int(val / vmax * 100)) if vmax > 0 else 0
        tone_c = (
            "var(--bull)"  if pct >= 70 else
            "var(--amber)" if pct >= 40 else
            "var(--text-muted)"
        )
        bds_html += (
            f'<div class="ft-opp-bd-row" style="--bd-tone:{tone_c};">'
            f'<span class="lb">{lbl}</span><span class="vl">{vstr}</span>'
            f'</div>'
            f'<div class="ft-opp-bd-bar" style="--bd-tone:{tone_c};">'
            f'<div class="ft-opp-bd-bar-fill" style="width:{pct}%;"></div>'
            f'</div>'
        )

    # Micro-stats
    rsi_c = "var(--bull)" if 35 <= rsi <= 55 else "var(--amber)"
    r5_c  = "var(--bull)" if ret_5d >= 0 else "var(--bear)"
    r3_c  = "var(--bull)" if ret_3m >= 0 else "var(--bear)"

    setor_html = (
        f'<div class="ft-opp-setor">{setor[:30]}</div>'
        if setor and setor != "—" else ""
    )

    return (
        f'<div class="ft-opp-card">'
        f'<div class="ft-opp-head">'
        f'<span class="ft-opp-tk">{ticker.replace(".SA","")}</span>'
        f'<span class="ft-opp-medal">{medal}</span>'
        f'</div>'
        f'<div class="ft-opp-name">{_escape(nome[:60])}</div>'
        f'{setor_html}'
        f'<div class="ft-opp-bds">{bds_html}</div>'
        f'<div class="ft-opp-stats">'
        f'<div class="ft-opp-stat">'
        f'<div class="l">RSI</div>'
        f'<div class="v" style="color:{rsi_c};">{rsi:.0f}</div></div>'
        f'<div class="ft-opp-stat">'
        f'<div class="l">5d</div>'
        f'<div class="v" style="color:{r5_c};">{ret_5d:+.1f}%</div></div>'
        f'<div class="ft-opp-stat">'
        f'<div class="l">3m</div>'
        f'<div class="v" style="color:{r3_c};">{ret_3m:+.1f}%</div></div>'
        f'<div class="ft-opp-stat">'
        f'<div class="l">topo</div>'
        f'<div class="v" style="color:var(--text-secondary);">{dist_top:.0f}%</div></div>'
        f'</div>'
        f'</div>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# CHIP FILTER ROW — filtros compactos (substitui tabs_pill em filtros)
# ══════════════════════════════════════════════════════════════════════════════


def chip_filter_row(labels: list[str], key: str, default: str | None = None,
                    max_chip_cols: int = 8) -> str:
    """Filtros com largura natural; max_chip_cols mantido por compatibilidade."""
    return section_selector(labels, key, default=default)


# ══════════════════════════════════════════════════════════════════════════════
# TICKER HERO — banner premium para a página Research
# ══════════════════════════════════════════════════════════════════════════════


def ticker_hero(
    *,
    ticker:      str,
    nome:        str,
    setor:       str = "",
    mercado:     str = "",      # "BR" | "EUA" | "FII" | "Cripto"
    preco_atual: float = 0.0,
    moeda:       str = "R$",
    var_1d:      float = 0.0,
    var_1m:      float = 0.0,
    var_ytd:     float = 0.0,
    health:      float | None = None,
    serie_30d:   list | None = None,
) -> None:
    """
    Banner premium do ticker no Research. Substitui o page_header + grid
    de 4 metric_card por um único hero com:

    Esquerda:
      - chip mercado (BR/EUA/FII/Cripto)
      - ticker em 3xl + nome em ui-sm + setor em muted
      - preço atual em mono 3xl
      - 3 deltas (1d · 1m · YTD) coloridos
    Direita:
      - chip_status do health score
      - sparkline grande 30d (320x90)
    """
    is_up   = var_1d >= 0
    tone    = "bull" if is_up else "bear"
    tone_c  = "var(--bull)" if is_up else "var(--bear)"
    rgba    = "rgba(74,222,128,0.10)" if is_up else "rgba(248,113,113,0.10)"

    _inject_once(
        "_ticker_hero_css_v1",
        '.ft-tk-hero{position:relative;display:grid;'
        '  grid-template-columns:1.7fr 1fr;gap:var(--space-5);'
        '  padding:var(--space-5);border-radius:var(--radius-xl);'
        '  background:var(--surface-glass);backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);'
        '  box-shadow:var(--shadow-lg);overflow:hidden;'
        '  margin-bottom:var(--space-3);}'
        '.ft-tk-hero::before{content:"";position:absolute;inset:0;'
        '  background:linear-gradient(135deg,var(--tk-rgba) 0%,transparent 60%);'
        '  pointer-events:none;}'
        '.ft-tk-hero::after{content:"";position:absolute;left:0;top:0;'
        '  bottom:0;width:3px;background:var(--tk-tone);'
        '  box-shadow:0 0 16px var(--tk-tone);}'
        '.ft-tk-left{position:relative;display:flex;flex-direction:column;'
        '  justify-content:center;gap:var(--space-1);min-width:0;}'
        '.ft-tk-meta{display:flex;align-items:center;gap:8px;'
        '  margin-bottom:var(--space-1);}'
        '.ft-tk-mkt{display:inline-flex;align-items:center;gap:4px;'
        '  background:var(--bg-elevated);border:1px solid var(--border-subtle);'
        '  border-radius:var(--radius-sm);padding:2px 8px;'
        '  font-family:var(--font-ui);font-size:0.78rem;font-weight:700;'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  color:var(--text-secondary);}'
        '.ft-tk-name{font-family:var(--font-title);font-size:var(--text-3xl);'
        '  font-weight:800;color:var(--text-primary);'
        '  letter-spacing:var(--ls-tight);line-height:1;margin:0;}'
        '.ft-tk-sub{font-family:var(--font-ui);font-size:var(--text-xs);'
        '  color:var(--text-muted);margin-top:2px;'
        '  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'
        '  max-width:90%;}'
        '.ft-tk-price{font-family:var(--font-data);font-size:var(--text-3xl);'
        '  font-weight:700;color:var(--text-primary);line-height:1.1;'
        '  letter-spacing:var(--ls-tight);margin-top:var(--space-2);}'
        '.ft-tk-price .cur{font-size:var(--text-md);'
        '  color:var(--text-muted);font-weight:600;margin-right:6px;}'
        '.ft-tk-deltas{display:flex;flex-wrap:wrap;gap:12px 18px;'
        '  margin-top:var(--space-2);}'
        '.ft-tk-delta{display:inline-flex;flex-direction:column;'
        '  font-family:var(--font-data);}'
        '.ft-tk-delta .l{font-size:0.78rem;color:var(--text-muted);'
        '  text-transform:uppercase;letter-spacing:var(--ls-wide);'
        '  font-family:var(--font-ui);margin-bottom:2px;}'
        '.ft-tk-delta .v{font-size:var(--text-sm);font-weight:700;}'
        '.ft-tk-right{position:relative;display:flex;flex-direction:column;'
        '  align-items:flex-end;justify-content:space-between;gap:10px;}'
        '.ft-tk-spark-wrap{width:100%;max-width:340px;}'
        '.ft-tk-spark-wrap svg{width:100%;height:90px;}'
        '@media (max-width:900px){.ft-tk-hero{grid-template-columns:1fr;}'
        '  .ft-tk-right{align-items:flex-start;}}'
    )

    def _fmt(v: float) -> str:
        try:
            if abs(v) >= 1000:
                return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"{v:.2f}".replace(".", ",")
        except Exception:
            return str(v)

    def _delta_html(label: str, val: float) -> str:
        c = "var(--bull)" if val >= 0 else "var(--bear)"
        arrow = "▲" if val >= 0 else "▼"
        return (
            f'<div class="ft-tk-delta">'
            f'<span class="l">{label}</span>'
            f'<span class="v" style="color:{c};">{arrow} {abs(val):.2f}%</span>'
            f'</div>'
        )

    deltas_html = (
        _delta_html("variação dia", var_1d) +
        _delta_html("1 mês",        var_1m) +
        _delta_html("no ano",       var_ytd)
    )

    health_html = ""
    if health is not None:
        try:
            h = float(health)
            if h >= 65:
                h_tone = "bull"
            elif h >= 40:
                h_tone = "amber"
            else:
                h_tone = "bear"
            health_html = chip_status(f"health {int(h)}", tone=h_tone)
        except Exception:
            pass

    spark_html = ""
    if serie_30d is not None and len(serie_30d) >= 2:
        spark_html = inline_sparkline(
            serie_30d, tone=tone, largura=320, altura=90,
        )

    mkt_html = (
        f'<span class="ft-tk-mkt">{mercado}</span>' if mercado else ""
    )

    st.markdown(
        f'<div class="ft-tk-hero" '
        f'style="--tk-tone:{tone_c};--tk-rgba:{rgba};">'
        f'<div class="ft-tk-left">'
        f'<div class="ft-tk-meta">{mkt_html}</div>'
        f'<h1 class="ft-tk-name">{ticker.replace(".SA","")}</h1>'
        f'<div class="ft-tk-sub">{_escape(nome[:80])} · {_escape(setor[:40])}</div>'
        f'<div class="ft-tk-price"><span class="cur">{moeda}</span>{_fmt(preco_atual)}</div>'
        f'<div class="ft-tk-deltas">{deltas_html}</div>'
        f'</div>'
        f'<div class="ft-tk-right">'
        f'<div>{health_html}</div>'
        f'<div class="ft-tk-spark-wrap">{spark_html}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# SKELETON LOADERS — UX percebida (estruturas fantasma durante loading)
# ══════════════════════════════════════════════════════════════════════════════


def _skeleton_css() -> None:
    """Injeta CSS dos skeletons + animação shimmer."""
    _inject_once(
        "_skeleton_css_v1",
        '@keyframes ft-shimmer{'
        '  0%{background-position:-1000px 0;}'
        '  100%{background-position:1000px 0;}}'
        '.ft-skel{'
        '  background:linear-gradient(90deg,'
        '    var(--bg-elevated) 0%,'
        '    var(--bg-overlay) 50%,'
        '    var(--bg-elevated) 100%);'
        '  background-size:1000px 100%;'
        '  animation:ft-shimmer 1.6s linear infinite;'
        '  border-radius:var(--radius-sm);'
        '  display:block;}'
        '.ft-skel-text{height:.85em;margin:6px 0;}'
        '.ft-skel-line{height:.65em;margin:5px 0;border-radius:3px;}'
        '.ft-skel-block{height:80px;margin:8px 0;'
        '  border-radius:var(--radius-md);}'
        '.ft-skel-card{position:relative;padding:14px 16px;'
        '  border-radius:var(--radius-lg);background:var(--surface-glass);'
        '  border:1px solid var(--border-subtle);}'
        '.ft-skel-card .ft-skel-text{height:.65em;width:35%;'
        '  margin-bottom:10px;}'
        '.ft-skel-card .ft-skel-block{height:32px;margin:4px 0;width:60%;}'
        '.ft-skel-card-row{display:grid;'
        '  grid-template-columns:repeat(4,minmax(0,1fr));'
        '  gap:var(--space-3);margin-bottom:var(--space-4);}'
        '@media (max-width:900px){.ft-skel-card-row{'
        '  grid-template-columns:repeat(2,1fr);}}'
        '.ft-skel-table{width:100%;border-collapse:collapse;'
        '  background:var(--bg-surface);'
        '  border-radius:var(--radius-md);overflow:hidden;}'
        '.ft-skel-table th,.ft-skel-table td{padding:9px 12px;'
        '  border-bottom:1px solid var(--border-subtle);}'
        '.ft-skel-table .ft-skel{height:.7em;}'
    )


def skeleton_kpi_row(n: int = 4) -> None:
    """
    Skeleton fantasma para uma linha de KPIs (4 cards por default).
    Use enquanto carrega dados que vão preencher um portfolio_kpis ou kpi_index_row.
    """
    _skeleton_css()
    cards = "".join(
        '<div class="ft-skel-card">'
        '<span class="ft-skel ft-skel-text"></span>'
        '<span class="ft-skel ft-skel-block"></span>'
        '<span class="ft-skel ft-skel-line" style="width:50%;"></span>'
        '</div>'
        for _ in range(max(1, n))
    )
    st.markdown(
        f'<div class="ft-skel-card-row" '
        f'style="grid-template-columns:repeat({n},minmax(0,1fr));">{cards}</div>',
        unsafe_allow_html=True,
    )


def skeleton_table(
    n_rows: int = 5,
    n_cols: int = 4,
    *,
    show_header: bool = True,
) -> None:
    """
    Skeleton fantasma para uma tabela (default 5 linhas × 4 colunas).
    """
    _skeleton_css()
    th = ""
    if show_header:
        th = (
            '<thead><tr>' +
            "".join(
                f'<th><span class="ft-skel ft-skel-text" '
                f'style="width:{60 + (i*5) % 30}%;"></span></th>'
                for i in range(n_cols)
            ) +
            '</tr></thead>'
        )
    tr = "".join(
        '<tr>' +
        "".join(
            f'<td><span class="ft-skel ft-skel-line" '
            f'style="width:{45 + (i*13 + r*7) % 45}%;"></span></td>'
            for i in range(n_cols)
        ) +
        '</tr>'
        for r in range(max(1, n_rows))
    )
    st.markdown(
        f'<table class="ft-skel-table">{th}<tbody>{tr}</tbody></table>',
        unsafe_allow_html=True,
    )


def skeleton_hero() -> None:
    """
    Skeleton fantasma para um hero (portfolio_hero / ticker_hero / hero_macro).
    """
    _skeleton_css()
    st.markdown(
        '<div class="ft-skel-card" style="display:grid;'
        'grid-template-columns:1.5fr 1fr;gap:24px;padding:24px;'
        'border-radius:var(--radius-xl);margin-bottom:var(--space-3);">'
        '<div>'
        '<span class="ft-skel ft-skel-line" style="width:25%;height:.5em;"></span>'
        '<span class="ft-skel ft-skel-block" style="width:50%;height:36px;margin:8px 0;"></span>'
        '<span class="ft-skel ft-skel-block" style="width:45%;height:28px;margin:6px 0;"></span>'
        '<span class="ft-skel ft-skel-line" style="width:60%;"></span>'
        '</div>'
        '<div style="display:flex;align-items:center;justify-content:flex-end;">'
        '<span class="ft-skel ft-skel-block" style="width:100%;height:80px;"></span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# EMPTY STATE v5 — glass + CTA gradient + ícone com glow
# ══════════════════════════════════════════════════════════════════════════════


def empty_state_v5(
    *,
    titulo:      str,
    descricao:   str = "",
    icone:       str = "📭",
    tone:        str = "info",   # info | bull | amber | bear | accent
    cta_label:   str = "",
    cta_key:     str = "ev5_cta",
    cta_icone:   str = "",
    secondary_label: str = "",   # botão secundário ghost (opcional)
    secondary_key:   str = "ev5_sec",
) -> dict:
    """
    Empty state premium — glass card com ícone gigante glow + título + descrição +
    CTA gradient + botão secundário opcional.

    Retorna dict:
        {"cta": bool, "secondary": bool}

    Tones: info (azul) · bull (verde) · amber · bear · accent (laranja)
    """
    t = _tone(tone)
    tone_c = t.get("fg", "var(--info)")

    _inject_once(
        "_empty_v5_css_v1",
        '.ft-ev5{position:relative;text-align:center;'
        '  padding:var(--space-8) var(--space-6);'
        '  border-radius:var(--radius-xl);'
        '  background:var(--surface-glass);backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px dashed var(--border-normal);'
        '  margin:var(--space-4) auto;max-width:560px;'
        '  animation:ft-fadein .4s var(--ease-out);}'
        '@keyframes ft-fadein{from{opacity:0;transform:translateY(8px);}'
        '  to{opacity:1;transform:translateY(0);}}'
        '.ft-ev5::before{content:"";position:absolute;inset:0;'
        '  background:radial-gradient(circle at 50% 0%,'
        '    var(--ev5-rgba) 0%,transparent 70%);'
        '  pointer-events:none;border-radius:var(--radius-xl);}'
        '.ft-ev5-icon{font-size:3.4rem;line-height:1;'
        '  margin-bottom:var(--space-3);opacity:.85;'
        '  filter:drop-shadow(0 0 18px var(--ev5-tone));'
        '  position:relative;display:inline-block;}'
        '.ft-ev5-titulo{font-family:var(--font-title);'
        '  font-size:var(--text-lg);font-weight:700;'
        '  color:var(--text-primary);'
        '  letter-spacing:var(--ls-tight);'
        '  margin-bottom:var(--space-1);position:relative;}'
        '.ft-ev5-desc{font-family:var(--font-ui);'
        '  font-size:var(--text-sm);color:var(--text-secondary);'
        '  line-height:1.6;max-width:42ch;margin:0 auto;'
        '  position:relative;}'
    )

    rgba = "rgba(110,128,255,0.10)"
    if tone == "bull":   rgba = "rgba(74,222,128,0.10)"
    elif tone == "bear": rgba = "rgba(248,113,113,0.10)"
    elif tone == "amber":rgba = "rgba(251,191,36,0.10)"
    elif tone == "accent": rgba = "rgba(255,140,0,0.10)"

    st.markdown(
        f'<div class="ft-ev5" '
        f'style="--ev5-tone:{tone_c};--ev5-rgba:{rgba};">'
        f'<div class="ft-ev5-icon">{icone}</div>'
        f'<div class="ft-ev5-titulo">{titulo}</div>'
        f'<div class="ft-ev5-desc">{descricao}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    res = {"cta": False, "secondary": False}
    if cta_label or secondary_label:
        col_l, col_m, col_r = st.columns([2, 2, 2])
        idx = 0
        cols_used = []
        if cta_label:
            cols_used.append(col_m if not secondary_label else col_l)
        if secondary_label:
            cols_used.append(col_m if cta_label else col_l)
            if cta_label:
                cols_used[-1] = col_r

        if cta_label:
            target_col = col_m if not secondary_label else col_l
            with target_col:
                lbl = f"{cta_icone} {cta_label}" if cta_icone else cta_label
                if gradient_cta_button(lbl, key=cta_key, largura_full=True):
                    res["cta"] = True

        if secondary_label:
            target_col = col_m if not cta_label else col_r
            with target_col:
                if st.button(secondary_label, key=secondary_key,
                             use_container_width=True):
                    res["secondary"] = True

    return res


# ══════════════════════════════════════════════════════════════════════════════
# URL STATE — filtros persistem no link (deeplink)
# ══════════════════════════════════════════════════════════════════════════════


def url_state_chip_filter_row(
    labels:  list[str],
    qp_key:  str,
    *,
    default: str | None = None,
    max_chip_cols: int = 8,
) -> str:
    """
    Variação do chip_filter_row que persiste o estado no URL via st.query_params.

    - O parâmetro selecionado vira `?qp_key=<label_slug>` na URL
    - Compartilhar o link compartilha o filtro aplicado
    - Recarregar a página preserva o filtro

    Slug: removemos espaços e baixamos pra um identificador URL-safe.
    """
    if not labels:
        return ""

    # Mapa slug → label original
    def _slug(s: str) -> str:
        import unicodedata
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")[:32]

    slug_to_label = {_slug(lab): lab for lab in labels}
    label_to_slug = {lab: slug for slug, lab in slug_to_label.items()}

    # Lê estado atual do URL
    qp = st.query_params
    current_slug = qp.get(qp_key, [])
    if isinstance(current_slug, list):
        current_slug = current_slug[0] if current_slug else ""
    current = slug_to_label.get(current_slug, default or labels[0])
    if current not in labels:
        current = labels[0]

    state_key = f"_url_filter_{qp_key}"
    previous_slug_key = f"_url_filter_slug_{qp_key}"
    if st.session_state.get(previous_slug_key) != current_slug:
        st.session_state[state_key] = current
    selected = section_selector(labels, state_key, default=current)
    selected_slug = label_to_slug[selected]
    if selected != current:
        st.query_params[qp_key] = selected_slug
    st.session_state[previous_slug_key] = selected_slug
    return selected


# ══════════════════════════════════════════════════════════════════════════════
# LAZY CHART — render só quando o user expandir/clicar (perf)
# ══════════════════════════════════════════════════════════════════════════════


def lazy_chart(
    titulo:      str,
    render_fn,
    *,
    key:         str,
    descricao:   str = "",
    icone:       str = "📈",
    auto_load:   bool = False,
) -> None:
    """
    Wrapper para gráficos pesados (Plotly + cálculo) que só são computados
    quando o usuário clica para expandir. Reduz tempo de render inicial.

    Args:
        titulo:    nome do gráfico (mostrado no header sempre)
        render_fn: callable() → None que faz o cálculo + st.plotly_chart
        key:       chave única do session_state (estado expand)
        descricao: subtítulo opcional
        icone:     emoji do header
        auto_load: se True, carrega na primeira render automaticamente

    Visual:
      - Card glass com header + botão "carregar gráfico"
      - Quando expandido: render_fn() é executado
      - Estado persiste no session_state (não recolhe ao mudar filtros)

    Por que importa:
      Plotly + cálculo pesado (e.g. correlação de 30 ativos) pode levar
      2-5 segundos. Em uma página com 5 desses gráficos, são 10-25s.
      Lazy: usuário carrega só o que quer ver.
    """
    _inject_once(
        "_lazy_chart_css_v1",
        '.ft-lazy{position:relative;padding:14px 18px;'
        '  border-radius:var(--radius-lg);background:var(--surface-glass);'
        '  backdrop-filter:var(--glass-blur);'
        '  -webkit-backdrop-filter:var(--glass-blur);'
        '  border:1px solid var(--border-subtle);'
        '  margin-bottom:var(--space-3);}'
        '.ft-lazy-head{display:flex;align-items:center;'
        '  justify-content:space-between;gap:12px;}'
        '.ft-lazy-titulo{font-family:var(--font-ui);font-size:var(--text-sm);'
        '  font-weight:600;color:var(--text-primary);'
        '  display:inline-flex;align-items:center;gap:6px;}'
        '.ft-lazy-titulo .ic{font-size:1rem;opacity:.85;}'
        '.ft-lazy-desc{font-family:var(--font-ui);font-size:var(--text-xs);'
        '  color:var(--text-muted);margin-top:4px;}'
        '.ft-lazy-status{font-family:var(--font-ui);font-size:0.78rem;'
        '  color:var(--text-muted);text-transform:uppercase;'
        '  letter-spacing:var(--ls-wide);'
        '  background:var(--bg-elevated);border:1px solid var(--border-subtle);'
        '  border-radius:999px;padding:2px 10px;}'
    )

    state_key = f"__lazy_{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = bool(auto_load)

    expanded = st.session_state[state_key]

    if not expanded:
        _desc_html = (
            f'<div class="ft-lazy-desc">{descricao}</div>' if descricao else ""
        )
        st.markdown(
            f'<div class="ft-lazy">'
            f'<div class="ft-lazy-head">'
            f'<div>'
            f'<div class="ft-lazy-titulo">'
            f'<span class="ic">{icone}</span>{titulo}</div>'
            f'{_desc_html}'
            f'</div>'
            f'<span class="ft-lazy-status">não carregado</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns([2, 1, 2])
        with c2:
            if st.button(
                "Carregar gráfico",
                key=f"__lazy_btn_{key}",
                use_container_width=True,
            ):
                st.session_state[state_key] = True
                st.rerun()
        return

    # Expandido — render real
    _desc_html2 = (
        f'<div class="ft-lazy-desc">{descricao}</div>' if descricao else ""
    )
    st.markdown(
        f'<div class="ft-lazy" style="border-color:var(--accent-border);">'
        f'<div class="ft-lazy-head">'
        f'<div>'
        f'<div class="ft-lazy-titulo">'
        f'<span class="ic">{icone}</span>{titulo}</div>'
        f'{_desc_html2}'
        f'</div>'
        f'<span class="ft-lazy-status" '
        f'style="color:var(--bull);border-color:var(--bull);">'
        f'● carregado</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    try:
        render_fn()
    except Exception as e:
        st.error(f"Falha ao renderizar gráfico: {e}")

    # Botão recolher (canto direito)
    c1, c2 = st.columns([5, 1])
    with c2:
        if st.button("× recolher", key=f"__lazy_btn_close_{key}",
                     use_container_width=True):
            st.session_state[state_key] = False
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# BUSCA GLOBAL DE ATIVO (navegação) — disponível na sidebar de TODA página.
# Torna o deep dive (Research) acessível de qualquer lugar, em 1 passo.
# ══════════════════════════════════════════════════════════════════════════════

def _resolver_ticker_busca(termo: str) -> str | None:
    """Resolve símbolos conhecidos diretamente; nomes e outros termos pelo provedor."""
    from utils.tickers import BRASIL_TODOS, SCREENER_US, BR_INDICES, XSTOCKS_TODOS
    query = (termo or "").strip()
    symbol = query.upper()
    if not symbol:
        return None
    if _re.fullmatch(r"[A-Z]{4}[0-9]{1,2}", symbol):
        return symbol + ".SA"
    if _re.fullmatch(r"[A-Z]{4}[0-9]{1,2}\.SA", symbol):
        return symbol
    known = {str(ticker).upper(): str(ticker)
             for ticker in [*BRASIL_TODOS, *SCREENER_US, *BR_INDICES, *XSTOCKS_TODOS]}
    if symbol in known:
        return known[symbol]
    try:
        from utils.market_data import buscar_ativo_yahoo
        for result in buscar_ativo_yahoo(query) or []:
            if result.get("symbol"):
                return result["symbol"]
    except Exception:
        pass
    return None


def busca_global_sidebar(research_page: str = "pages/1_Research.py") -> None:
    """Busca enviada pelo botão ou Enter, sem rerun a cada campo editado."""
    with st.sidebar:
        with st.form("_busca_global_form", border=False):
            termo = st.text_input("Buscar ativo", key="_busca_global_termo",
                                  placeholder="Ticker ou empresa", help="Ex.: PETR4, HGLG11, AAPL ou Nubank.")
            submitted = st.form_submit_button("Abrir análise →", use_container_width=True)
        if submitted:
            if not termo.strip():
                st.warning("Digite um ticker ou nome de empresa.")
                return
            with st.spinner("Buscando ativo…"):
                ticker = _resolver_ticker_busca(termo)
            if ticker:
                st.session_state["research_ticker_externo"] = ticker
                st.switch_page(research_page)
            else:
                st.warning("Ativo não encontrado. Tente o ticker completo.")




def page_jump_links(items: list[tuple[str, str]]) -> None:
    """Atalhos para seções de páginas extensas, mantendo o contexto atual."""
    links = ''.join(f'<a href="#{_escape(anchor, quote=True)}" target="_self">{_escape(label)}</a>' for label, anchor in items)
    st.markdown(f'<nav class="ft-jump-links" aria-label="Nesta página">{links}</nav>', unsafe_allow_html=True)


def confirm_action(titulo: str, descricao: str, action, *, key: str) -> None:
    """Confirma remoções dentro do produto; executar apenas no botão de confirmação."""
    @st.dialog(titulo)
    def dialog():
        st.write(descricao)
        cancel, confirm = st.columns(2)
        if cancel.button("Cancelar", key=f"{key}_cancel", use_container_width=True):
            st.rerun()
        if confirm.button("Confirmar remoção", key=f"{key}_confirm", type="primary", use_container_width=True, on_click=action):
            st.toast("Remoção concluída.")
            st.rerun()
    dialog()
