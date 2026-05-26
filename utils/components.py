import streamlit as st
import time


def page_header(titulo: str, subtitulo: str = ""):
    """Header compacto de página."""
    sub = (
        f'<span style="font-size:0.65rem; color:#444; '
        f'margin-left:12px; letter-spacing:0.06em;">'
        f'{subtitulo}</span>'
        if subtitulo else ""
    )
    st.markdown(
        f'<div style="display:flex; align-items:baseline; '
        f'gap:8px; border-bottom:1px solid #1a1a1a; '
        f'padding-bottom:5px; margin-bottom:12px;">'
        f'<span style="font-family:Courier New; '
        f'font-size:0.9rem; font-weight:bold; '
        f'color:#FF9900; text-transform:uppercase; '
        f'letter-spacing:0.12em;">{titulo}</span>'
        f'{sub}</div>',
        unsafe_allow_html=True,
    )


def section_title(titulo: str):
    """Título de seção compacto."""
    st.markdown(
        f'<div style="font-family:Courier New; '
        f'font-size:0.60rem; font-weight:bold; '
        f'color:#444444; text-transform:uppercase; '
        f'letter-spacing:0.14em; '
        f'border-bottom:1px solid #111; '
        f'padding-bottom:3px; margin-bottom:8px; '
        f'margin-top:12px;">{titulo}</div>',
        unsafe_allow_html=True,
    )


def metric_card(label: str, valor: str,
                delta: str = "", cor_delta: str = "muted"):
    """Metric card compacto — estilo institucional."""
    COR = {
        "bull":  "#00C853",
        "bear":  "#FF1744",
        "amber": "#FF9900",
        "info":  "#00B0FF",
        "muted": "#444444",
    }
    cor = COR.get(cor_delta, "#444444")

    delta_html = (
        f'<div style="font-family:Courier New; '
        f'font-size:0.58rem; color:{cor}; '
        f'margin-top:2px; line-height:1.2;">{delta}</div>'
        if delta else ""
    )
    st.markdown(
        f'<div style="background:#080808; '
        f'border:1px solid #141414; border-radius:2px; '
        f'border-top:1px solid #1e1e1e; '
        f'padding:5px 8px;">'
        f'<div style="font-family:Courier New; '
        f'font-size:0.58rem; color:#444; '
        f'text-transform:uppercase; letter-spacing:0.1em; '
        f'margin-bottom:2px;">{label}</div>'
        f'<div style="font-family:Courier New; '
        f'font-size:1.05rem; font-weight:bold; '
        f'color:#E0E0E0; line-height:1.1;">{valor}</div>'
        f'{delta_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def status_card(titulo: str, corpo: str,
                tipo: str = "info", subtitulo: str = ""):
    """Card de status compacto com borda lateral."""
    COR = {
        "bull":  "#00C853",
        "bear":  "#FF1744",
        "amber": "#FF9900",
        "info":  "#00B0FF",
        "muted": "#333333",
    }
    cor = COR.get(tipo, "#00B0FF")
    sub_html = (
        f'<div style="font-size:0.58rem; '
        f'color:#333; margin-top:1px;">{subtitulo}</div>'
        if subtitulo else ""
    )
    st.markdown(
        f'<div style="border-left:2px solid {cor}; '
        f'background:#060606; padding:6px 10px; '
        f'margin-bottom:6px; border-radius:0 2px 2px 0;">'
        f'<div style="font-family:Courier New; '
        f'font-size:0.60rem; color:#444; '
        f'text-transform:uppercase; '
        f'letter-spacing:0.1em;">{titulo}</div>'
        f'{sub_html}'
        f'<div style="font-family:Courier New; '
        f'font-size:0.75rem; color:#888; '
        f'margin-top:3px; line-height:1.5;">{corpo}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def watchlist_card(ticker: str, nome: str, preco: float,
                   var_1d: float, moeda: str = "R$",
                   health_score: float = None,
                   alertas: list = None,
                   earnings_info: dict = None):
    """
    Card da watchlist — estilo linha de terminal.
    Compacto, denso, toda info em poucos pixels.
    """
    cor_var   = "#00C853" if var_1d >= 0 else "#FF1744"
    seta      = "▲" if var_1d >= 0 else "▼"
    tem_alert = bool(alertas and len(alertas) > 0)

    # Health score barra compacta
    score_html = ""
    if health_score is not None:
        cor_sc = (
            "#00C853" if health_score >= 65
            else "#FF9900" if health_score >= 40
            else "#FF1744"
        )
        pct = int(health_score)
        score_html = (
            f'<div style="margin-top:5px;">'
            f'<div style="display:flex; align-items:center; '
            f'justify-content:space-between; margin-bottom:2px;">'
            f'<span style="font-family:Courier New; '
            f'font-size:0.55rem; color:#333;">HS</span>'
            f'<span style="font-family:Courier New; '
            f'font-size:0.62rem; color:{cor_sc}; '
            f'font-weight:bold;">{pct}</span></div>'
            f'<div style="background:#0a0a0a; height:2px; '
            f'border-radius:0;">'
            f'<div style="background:{cor_sc}; '
            f'width:{pct}%; height:100%;"></div>'
            f'</div></div>'
        )

    # Badge alerta
    alerta_html = ""
    if tem_alert:
        alerta_html = (
            f'<span style="font-family:Courier New; '
            f'font-size:0.52rem; color:#FF1744; '
            f'border:1px solid #FF1744; padding:0 3px; '
            f'border-radius:1px; margin-left:4px; '
            f'vertical-align:middle;">⚠</span>'
        )

    # Badge earnings
    earn_html = ""
    if earnings_info and earnings_info.get("dias") is not None:
        dias_e = earnings_info["dias"]
        if 0 <= dias_e <= 14:
            cor_e = (
                "#FF1744" if dias_e <= 3
                else "#FF9900" if dias_e <= 7
                else "#444"
            )
            earn_html = (
                f'<span style="font-family:Courier New; '
                f'font-size:0.52rem; color:{cor_e}; '
                f'border:1px solid {cor_e}; padding:0 3px; '
                f'border-radius:1px; margin-left:4px; '
                f'vertical-align:middle;">'
                f'res.{dias_e}d</span>'
            )

    # Primeiro alerta (resumido)
    alerta_txt = ""
    if tem_alert and alertas:
        alerta_txt = (
            f'<div style="font-family:Courier New; '
            f'font-size:0.58rem; color:#333; '
            f'margin-top:4px; line-height:1.3; '
            f'overflow:hidden; '
            f'display:-webkit-box; '
            f'-webkit-line-clamp:2; '
            f'-webkit-box-orient:vertical;">'
            f'{alertas[0]}</div>'
        )

    st.markdown(
        f'<div style="background:#080808; '
        f'border:1px solid #141414; '
        f'border-top:1px solid #1e1e1e; '
        f'border-radius:2px; padding:8px 10px; '
        f'margin-bottom:4px;">'
        # Linha 1: ticker + badges
        f'<div style="display:flex; '
        f'align-items:center; margin-bottom:3px;">'
        f'<span style="font-family:Courier New; '
        f'font-weight:bold; color:#FF9900; '
        f'font-size:0.82rem; letter-spacing:0.05em;">'
        f'{ticker.replace(".SA", "")}</span>'
        f'{alerta_html}{earn_html}'
        f'</div>'
        # Linha 2: nome
        f'<div style="font-family:Courier New; '
        f'font-size:0.58rem; color:#333; '
        f'margin-bottom:5px; '
        f'overflow:hidden; text-overflow:ellipsis; '
        f'white-space:nowrap;">{nome[:28]}</div>'
        # Linha 3: preço + variação
        f'<div style="display:flex; '
        f'justify-content:space-between; '
        f'align-items:baseline;">'
        f'<span style="font-family:Courier New; '
        f'font-size:1.05rem; font-weight:bold; '
        f'color:#E0E0E0;">'
        f'{moeda} {preco:,.2f}</span>'
        f'<span style="font-family:Courier New; '
        f'font-size:0.72rem; color:{cor_var}; '
        f'font-weight:bold;">'
        f'{seta}{abs(var_1d):.2f}%</span>'
        f'</div>'
        f'{score_html}'
        f'{alerta_txt}'
        f'</div>',
        unsafe_allow_html=True,
    )


def empty_state(icone: str, titulo: str, descricao: str):
    """Estado vazio compacto."""
    st.markdown(
        f'<div style="text-align:center; '
        f'padding:32px 24px; color:#222;">'
        f'<div style="font-size:1.8rem; '
        f'margin-bottom:8px; opacity:0.4;">{icone}</div>'
        f'<div style="font-family:Courier New; '
        f'font-size:0.72rem; color:#333; '
        f'font-weight:bold; text-transform:uppercase; '
        f'letter-spacing:0.1em; margin-bottom:4px;">'
        f'{titulo}</div>'
        f'<div style="font-family:Courier New; '
        f'font-size:0.65rem; color:#222; '
        f'max-width:260px; margin:0 auto; '
        f'line-height:1.5;">{descricao}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def progress_steps(steps: list[str], current: int):
    """Progress steps compacto."""
    items = "".join([
        f'<div style="display:flex; align-items:center; '
        f'gap:4px; font-family:Courier New; '
        f'font-size:0.60rem; '
        f'color:{"#00C853" if i < current else ("#FF9900" if i == current else "#222")};">'
        f'<span>{"✓" if i < current else ("▶" if i == current else "○")}</span>'
        f'<span style="text-transform:uppercase;">{s}</span>'
        f'</div>'
        for i, s in enumerate(steps)
    ])
    st.markdown(
        f'<div style="display:flex; gap:16px; '
        f'padding:6px 0; border-bottom:1px solid #111; '
        f'margin-bottom:12px;">{items}</div>',
        unsafe_allow_html=True,
    )


def auto_refresh_indicator(minutos_cache: int = 5):
    """Indicador de sync compacto."""
    st.markdown(
        f'<div style="font-family:Courier New; '
        f'font-size:0.58rem; color:#222; '
        f'text-align:right; margin-bottom:8px;">'
        f'sync {time.strftime("%H:%M")} · '
        f'ttl {minutos_cache}m</div>',
        unsafe_allow_html=True,
    )


def kpi_row(itens: list[dict]):
    """
    Linha de KPIs compacta no estilo Bloomberg.
    itens: [{'label': str, 'valor': str, 'cor': str}, ...]
    """
    COR = {
        "bull":  "#00C853",
        "bear":  "#FF1744",
        "amber": "#FF9900",
        "info":  "#00B0FF",
        "muted": "#444444",
    }
    cols = st.columns(len(itens))
    for i, item in enumerate(itens):
        cor = COR.get(item.get("cor", "muted"), "#444")
        border = "border-right:none;" if i == len(itens) - 1 else ""
        with cols[i]:
            st.markdown(
                f'<div style="border-right:1px solid #111; '
                f'padding:4px 8px; {border}">'
                f'<div style="font-family:Courier New; '
                f'font-size:0.58rem; color:#333; '
                f'text-transform:uppercase; '
                f'letter-spacing:0.1em;">'
                f'{item["label"]}</div>'
                f'<div style="font-family:Courier New; '
                f'font-size:0.88rem; font-weight:bold; '
                f'color:{cor};">{item["valor"]}</div>'
                f'</div>',
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
    on_delete:     str   = None,
    on_memorial:   str   = None,
):
    """
    Linha densa de watchlist — uma linha de ~48px por ativo.
    Informação máxima, ações mínimas e inline.
    """
    cor_var  = "var(--bull)" if var_1d >= 0 else "var(--bear)"
    cor_1m   = "var(--bull)" if var_1m >= 0 else "var(--bear)"
    seta     = "▲" if var_1d >= 0 else "▼"
    seta_1m  = "▲" if var_1m >= 0 else "▼"
    tem_alert = bool(alertas and len(alertas) > 0)

    # Health score — barra mini + número
    hs_html = ""
    if health_score is not None:
        hs = int(health_score)
        cor_hs = ("var(--bull)"  if hs >= 65 else
                  "var(--amber)" if hs >= 40 else
                  "var(--bear)")
        hs_html = (
            f'<div style="display:flex; align-items:center;'
            f' gap:5px; min-width:80px; padding:12px 0 4px;">'
            f'<div style="flex:1; background:var(--bg-elevated);'
            f' height:4px; border-radius:1px;">'
            f'<div style="width:{hs}%; height:100%;'
            f' background:{cor_hs}; border-radius:1px;"></div>'
            f'</div>'
            f'<span style="font-size:0.75rem; color:{cor_hs};'
            f' font-weight:bold; min-width:22px;'
            f' text-align:right;">{hs}</span>'
            f'</div>'
        )

    # Badges compactos (irão para dentro de col_nm)
    badges_html = ""
    if tem_alert:
        badges_html += (
            ' <span style="font-size:0.52rem; color:var(--bear);'
            ' border:1px solid var(--bear); padding:0 3px;'
            ' border-radius:2px; vertical-align:middle;">⚠</span>'
        )
    if earnings_info and 0 <= earnings_info.get("dias", 99) <= 14:
        dias_e = earnings_info["dias"]
        cor_e  = ("var(--bear)"  if dias_e <= 3 else
                  "var(--amber)" if dias_e <= 7 else
                  "var(--text-muted)")
        badges_html += (
            f' <span style="font-size:0.52rem; color:{cor_e};'
            f' border:1px solid {cor_e}; padding:0 3px;'
            f' border-radius:2px; vertical-align:middle;">res·{dias_e}d</span>'
        )

    # Primeiro alerta — texto puro (sem wrapper div)
    alerta_resumo_txt = ""
    if tem_alert and alertas:
        alerta_resumo_txt = (
            alertas[0][:60] + "…" if len(alertas[0]) > 60 else alertas[0]
        )

    # Layout: 7 colunas (badges migrados para col_nm)
    col_tk, col_nm, col_pr, col_1d, col_1m, \
        col_hs, col_ac = st.columns(
            [1.4, 2.8, 1.6, 1.0, 1.0, 1.5, 0.6]
        )

    with col_tk:
        st.markdown(
            f'<div style="font-family:Courier New;'
            f' font-weight:bold; color:var(--accent);'
            f' font-size:0.85rem; padding:12px 0 4px;">'
            f'{ticker.replace(".SA", "")}</div>',
            unsafe_allow_html=True,
        )

    with col_nm:
        alerta_sub = (
            f'<div style="font-size:0.65rem;'
            f' color:var(--text-muted); line-height:1.3;'
            f' overflow:hidden; text-overflow:ellipsis;'
            f' white-space:nowrap; max-width:280px;">'
            f'{alerta_resumo_txt}</div>'
        ) if alerta_resumo_txt else ""
        st.markdown(
            f'<div style="font-family:Courier New;'
            f' color:var(--text-secondary); font-size:0.75rem;'
            f' padding:12px 0 4px; overflow:hidden;'
            f' text-overflow:ellipsis; white-space:nowrap;">'
            f'{nome[:28]}{badges_html}</div>'
            f'{alerta_sub}',
            unsafe_allow_html=True,
        )

    with col_pr:
        st.markdown(
            f'<div style="font-family:Courier New;'
            f' font-weight:bold; color:var(--text-primary);'
            f' font-size:0.92rem; padding:12px 0 4px;">'
            f'{moeda} {preco:,.2f}</div>',
            unsafe_allow_html=True,
        )

    with col_1d:
        st.markdown(
            f'<div style="font-family:Courier New;'
            f' color:{cor_var}; font-size:0.78rem;'
            f' padding:12px 0 4px; font-weight:bold;">'
            f'{seta} {abs(var_1d):.2f}%</div>',
            unsafe_allow_html=True,
        )

    with col_1m:
        st.markdown(
            f'<div style="font-family:Courier New;'
            f' color:{cor_1m}; font-size:0.78rem;'
            f' padding:12px 0 4px;">'
            f'{seta_1m} {abs(var_1m):.2f}%</div>',
            unsafe_allow_html=True,
        )

    with col_hs:
        if health_score is not None:
            st.markdown(hs_html, unsafe_allow_html=True)

    with col_ac:
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button(
                "🗑", key=f"del_{on_delete or ticker}",
                help="remover da watchlist",
            ):
                st.session_state[f"confirm_del_{ticker}"] = True
        with btn_c2:
            if st.button(
                "📊", key=f"mem_{on_memorial or ticker}",
                help="memorial de cálculo",
            ):
                st.session_state[f"show_memorial_{ticker}"] = True

    # Linha separadora
    st.markdown(
        '<div style="height:1px; background:linear-gradient('
        '90deg, transparent, var(--border-dim), transparent);'
        ' margin:0;"></div>',
        unsafe_allow_html=True,
    )


def watchlist_header_row():
    """
    Header da lista densa — labels das colunas.
    Chame uma vez antes do loop de watchlist_row().
    """
    col_tk, col_nm, col_pr, col_1d, col_1m, \
        col_hs, col_ac = st.columns(
            [1.4, 2.8, 1.6, 1.0, 1.0, 1.5, 0.6]
        )

    labels = [
        (col_tk, "ativo"),
        (col_nm, "nome / alerta"),
        (col_pr, "preço"),
        (col_1d, "1d %"),
        (col_1m, "1m %"),
        (col_hs, "health"),
        (col_ac, ""),
    ]

    for col, label in labels:
        with col:
            st.markdown(
                f'<div style="font-family:Courier New;'
                f' font-size:0.62rem; color:var(--text-muted);'
                f' text-transform:uppercase;'
                f' letter-spacing:0.12em;'
                f' padding-bottom:4px;'
                f' border-bottom:1px solid var(--border-dim);">'
                f'{label}</div>',
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
