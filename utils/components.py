"""
utils/components.py — v4.0
Componentes HTML do design system.
Fontes: Inter/system-ui para UI, Courier New para dados numéricos.
"""
import streamlit as st
import time


def page_header(titulo: str, subtitulo: str = ""):
    """Header compacto de página."""
    st.markdown(
        f'<div style="margin-bottom: 16px;">'
        f'<div style="'
        f'font-family: Courier New, monospace; '
        f'font-size: 1.3rem; '
        f'font-weight: 700; '
        f'color: #FF9900; '
        f'letter-spacing: 0.05em;">'
        f'{titulo}</div>'
        + (
            f'<div style="'
            f'font-family: Courier New, monospace; '
            f'font-size: 0.75rem; '
            f'color: #444; '
            f'margin-top: 2px; '
            f'letter-spacing: 0.05em;">'
            f'{subtitulo}</div>'
            if subtitulo else ''
        ) +
        f'</div>',
        unsafe_allow_html=True,
    )


def section_title(titulo: str):
    """Título de seção com barra de acento âmbar à esquerda."""
    st.markdown(
        f'<div style="'
        f'font-family: Courier New, monospace; '
        f'font-size: 0.72rem; '
        f'color: #FF9900; '
        f'text-transform: uppercase; '
        f'letter-spacing: 0.12em; '
        f'font-weight: 600; '
        f'border-left: 2px solid #FF9900; '
        f'padding-left: 8px; '
        f'margin: 16px 0 8px 0;">'
        f'{titulo}'
        f'</div>',
        unsafe_allow_html=True,
    )


def metric_card(
    label:      str,
    valor:      str,
    sublabel:   str  = "",
    cor_delta:  str  = "muted",
    icone:      str  = "",
    destaque:   bool = False,
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
    """
    _cores = {
        "bull":  {"borda": "#00C853", "valor": "#00C853",
                  "bg": "#001a0a", "bg_dest": "#002a10",
                  "sublabel": "#2d6e42"},
        "bear":  {"borda": "#FF1744", "valor": "#FF1744",
                  "bg": "#1a0005", "bg_dest": "#2a000a",
                  "sublabel": "#7a2030"},
        "amber": {"borda": "#FF9900", "valor": "#FF9900",
                  "bg": "#0d0d0d", "bg_dest": "#1a0f00",
                  "sublabel": "#7a5500"},
        "info":  {"borda": "#00B0FF", "valor": "#00B0FF",
                  "bg": "#00080d", "bg_dest": "#00101a",
                  "sublabel": "#005580"},
        "muted": {"borda": "#2a2a2a", "valor": "#C0C0C0",
                  "bg": "#0d0d0d", "bg_dest": "#141414",
                  "sublabel": "#444"},
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
        f'border:1px solid #1e1e1e; '
        f'border-left:3px solid {_c["borda"]}; '
        f'border-radius:6px; '
        f'padding:{_pad}; '
        f'margin-bottom:4px; '
        f'transition:border-color .2s;">'

        f'<div style="'
        f'font-family:Courier New; '
        f'font-size:{_sz_label}; '
        f'color:#555; '
        f'text-transform:uppercase; '
        f'letter-spacing:.08em; '
        f'margin-bottom:4px;">'
        f'{label}</div>'

        f'<div style="'
        f'font-family:Courier New; '
        f'font-size:{_sz_valor}; '
        f'font-weight:700; '
        f'color:{_c["valor"]}; '
        f'line-height:1.2; '
        f'margin-bottom:2px;">'
        f'{_icone_html}{valor}</div>'

        + (
            f'<div style="'
            f'font-family:Courier New; '
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
        "bull":  ("#00C853", "#001a0a", "✅"),
        "bear":  ("#FF1744", "#1a0005", "⚠️"),
        "amber": ("#FF9900", "#0d0800", "💡"),
        "info":  ("#00B0FF", "#00080d", "ℹ️"),
        "muted": ("#444444", "#0d0d0d", "📋"),
    }
    _cor, _bg, _icone_def = _mapa_status.get(tipo, _mapa_status["amber"])
    _ic = icone or _icone_def

    st.markdown(
        f'<div style="'
        f'background:{_bg}; '
        f'border:1px solid {_cor}33; '
        f'border-left:4px solid {_cor}; '
        f'border-radius:6px; '
        f'padding:14px 18px; '
        f'margin:8px 0;">'

        f'<div style="'
        f'font-family:Courier New; '
        f'font-size:0.75rem; '
        f'color:{_cor}; '
        f'font-weight:700; '
        f'text-transform:uppercase; '
        f'letter-spacing:.08em; '
        f'margin-bottom:6px;">'
        f'{_ic} {titulo}</div>'

        f'<div style="'
        f'font-family:Courier New; '
        f'font-size:0.80rem; '
        f'color:#aaa; '
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
        st.markdown(
            f'<div style="font-family:var(--font-data);'
            f' font-weight:bold; color:var(--accent);'
            f' font-size:0.85rem; padding:11px 0 3px;'
            f' letter-spacing:0.02em;">'
            f'{ticker.replace(".SA", "")}{earn_html}</div>',
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
            f'{moeda} {preco:,.2f}</div>',
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


# Mantido para compatibilidade retroativa com páginas que ainda o usam
def watchlist_card(ticker: str, nome: str, preco: float,
                   var_1d: float, moeda: str = "R$",
                   health_score: float = None,
                   alertas: list = None,
                   earnings_info: dict = None):
    """
    Card legado da watchlist.
    Prefer watchlist_row() para layouts de lista densa.
    """
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
        f'<span style="font-family:var(--font-data);'
        f' font-weight:bold; color:var(--accent);'
        f' font-size:0.85rem;">'
        f'{ticker.replace(".SA", "")}{earn_html}</span>'
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


def inject_keyboard_shortcuts():
    """Atalho Enter → clica no botão primário da página."""
    st.markdown(
        "<script>"
        "const doc = window.parent.document;"
        "doc.addEventListener('keydown', function(e) {"
        "  if (e.key === 'Enter') {"
        "    const btns = doc.querySelectorAll('[data-testid=\"stBaseButton-primary\"]');"
        "    if (btns.length > 0) btns[0].click();"
        "  }"
        "});"
        "</script>",
        unsafe_allow_html=True,
    )
