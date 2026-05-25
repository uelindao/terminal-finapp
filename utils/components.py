import streamlit as st
import time

def page_header(titulo: str, subtitulo: str = ""):
    sub_html = f'<div style="font-family:Courier New; font-size:0.82rem; color:#555; margin-top:4px;">{subtitulo}</div>' if subtitulo else ""
    st.markdown(f'<div class="page-title">{titulo}</div>{sub_html}', unsafe_allow_html=True)

def section_title(titulo: str):
    st.markdown(f'<div class="section-title">{titulo}</div>', unsafe_allow_html=True)

def metric_card(label: str, valor: str, delta: str = "", cor_delta: str = "muted"):
    delta_html = f'<div class="metric-delta color-{cor_delta}">{delta}</div>' if delta else ""
    html = f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{valor}</div>{delta_html}</div>'
    st.markdown(html, unsafe_allow_html=True)

def status_card(titulo: str, corpo: str, tipo: str = "info", subtitulo: str = ""):
    sub = f'<div style="font-family:Courier New;font-size:0.72rem;color:#555;margin-top:2px;">{subtitulo}</div>' if subtitulo else ""
    html = f'<div class="card card-{tipo}" style="padding:14px 16px; margin-bottom:8px;"><div style="font-family:Courier New; font-size:0.75rem; color:#555; text-transform:uppercase; letter-spacing:0.08em;">{titulo}</div>{sub}<div style="font-family:Courier New; font-size:0.88rem; color:#E0E0E0; margin-top:6px; line-height:1.5;">{corpo}</div></div>'
    st.markdown(html, unsafe_allow_html=True)

def watchlist_card(
    ticker:        str,
    nome:          str,
    preco:         float,
    var_1d:        float,
    moeda:         str   = "R$",
    health_score:  float = None,
    alertas:       list  = None,
    earnings_info: dict  = None,
):
    """
    Card de ativo da watchlist.

    earnings_info (opcional): dict com
        'dias' — int, dias até o próximo resultado
        'data' — str, data formatada dd/mm/yyyy
    """
    cor_var    = "#00C853" if var_1d >= 0 else "#FF1744"
    sinal      = "▲" if var_1d >= 0 else "▼"
    bg_var     = "#001a0d" if var_1d >= 0 else "#1a0005"
    tem_alerta = bool(alertas and len(alertas) > 0)

    badge_alerta = (
        '<span class="badge badge-bear" style="font-size:0.6rem;">⚠ alerta</span>'
        if tem_alerta else ""
    )

    # Badge de earnings
    badge_earnings = ""
    if earnings_info and earnings_info.get('dias') is not None:
        dias_earn = earnings_info['dias']
        if 0 <= dias_earn <= 3:
            _label_e = "hoje" if dias_earn == 0 else f"em {dias_earn}d"
            badge_earnings = (
                f'<span class="badge badge-bear" '
                f'style="font-size:0.6rem; margin-left:4px;">'
                f'📅 resultado {_label_e}</span>'
            )
        elif dias_earn <= 7:
            badge_earnings = (
                f'<span class="badge badge-amber" '
                f'style="font-size:0.6rem; margin-left:4px;">'
                f'📅 resultado em {dias_earn}d</span>'
            )
        elif dias_earn <= 14:
            badge_earnings = (
                f'<span class="badge badge-muted" '
                f'style="font-size:0.6rem; margin-left:4px;">'
                f'📅 resultado em {dias_earn}d</span>'
            )

    score_html = ""
    if health_score is not None:
        score_cor = (
            "#00C853" if health_score >= 65
            else "#FF9900" if health_score >= 40
            else "#FF1744"
        )
        barra      = "█" * (int(health_score) // 10) + "░" * (10 - int(health_score) // 10)
        score_html = (
            f'<div style="margin-top:8px; padding-top:8px; border-top:1px solid #1e1e1e;">'
            f'<div style="font-family:Courier New; font-size:0.62rem; color:#555;">health score</div>'
            f'<div style="font-family:Courier New; font-size:0.75rem; color:{score_cor};">'
            f'{barra} {health_score:.0f}</div></div>'
        )

    alertas_html = (
        f"<div style='font-size:0.7em; color:#FF1744; margin-top:8px; line-height:1.2;'>"
        f"{' | '.join(alertas[:2])}</div>"
        if tem_alerta else ""
    )

    html = (
        f'<div class="card" style="border-top:2px solid #FF9900; padding:14px;">'
        f'<div style="display:flex; justify-content:space-between; align-items:flex-start;">'
        f'<div>'
        f'<span style="font-family:Courier New; font-weight:bold; color:#FF9900; font-size:1rem;">{ticker}</span>'
        f' {badge_alerta}{badge_earnings}'
        f'<div style="font-family:Courier New; font-size:0.72rem; color:#444; margin-top:2px; '
        f'max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{nome}</div>'
        f'</div></div>'
        f'<div style="font-family:Courier New; font-size:1.4rem; font-weight:bold; color:#FFFFFF; margin-top:8px;">'
        f'{moeda} {preco:,.2f}</div>'
        f'<div style="background:{bg_var}; border-radius:3px; padding:3px 8px; display:inline-block; margin-top:4px;">'
        f'<span style="font-family:Courier New; font-size:0.82rem; color:{cor_var}; font-weight:bold;">'
        f'{sinal} {abs(var_1d):.2f}% hoje</span></div>'
        f'{score_html}{alertas_html}</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def empty_state(icone: str, titulo: str, descricao: str):
    st.markdown(f'<div style="text-align:center; padding:48px 24px; color:#333;"><div style="font-size:2.5rem; margin-bottom:12px;">{icone}</div><div style="font-family:Courier New; font-size:0.95rem; color:#555; font-weight:bold; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:8px;">{titulo}</div><div style="font-family:Courier New; font-size:0.78rem; color:#3a3a3a; max-width:300px; margin:0 auto; line-height:1.6;">{descricao}</div></div>', unsafe_allow_html=True)

def progress_steps(steps: list[str], current: int):
    items = "".join([f'<div style="display:flex; align-items:center; gap:6px; font-family:Courier New; font-size:0.72rem; color:{"#00C853" if i<current else ("#FF9900" if i==current else "#333")};"><span>{"✓" if i<current else ("●" if i==current else "○")}</span><span style="text-transform:uppercase;">{s}</span></div>' for i, s in enumerate(steps)])
    st.markdown(f'<div style="display:flex; gap:20px; padding:10px 0; border-bottom:1px solid #1e1e1e; margin-bottom:16px;">{items}</div>', unsafe_allow_html=True)

def inject_keyboard_shortcuts():
    st.markdown("<script>const doc = window.parent.document; doc.addEventListener('keydown', function(e) { if (e.key === 'Enter') { const primaryBtns = doc.querySelectorAll('[data-testid=\"stBaseButton-primary\"]'); if (primaryBtns.length > 0) primaryBtns[0].click(); } });</script>", unsafe_allow_html=True)

def auto_refresh_indicator(minutos_cache=5):
    st.markdown(f'<div style="font-family:Courier New; font-size:0.75rem; color:#555; text-align:right; margin-top:-30px; margin-bottom:20px;">🔄 sincronizado às {time.strftime("%H:%M:%S")} (ttl: {minutos_cache} min)</div>', unsafe_allow_html=True)