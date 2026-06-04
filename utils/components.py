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


def _fonte_badge(fonte: str = "") -> str:
    if not fonte:
        return ""
    icone = "📦" if fonte == "cache" else "📡"
    cor = "#4CAF50" if fonte == "cache" else "#FF9900"
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
        f'{label}{_fonte_badge(data_source)}</div>'

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
        f'color:#444;'
        f'font-size:0.65rem;'
        f'border:1px solid #2a2a2a;'
        f'border-radius:50%;'
        f'padding:0 5px;'
        f'margin-left:4px;'
        f'font-family:Courier New;'
        f'user-select:none;'
        f'vertical-align:middle;'
        f'">?</span>',
        unsafe_allow_html=True,
    )


def label_com_tooltip(
    texto: str,
    chave: str = "",
    texto_custom: str = "",
    cor: str = "#555",
    tamanho: str = "0.72rem",
) -> None:
    _texto_tt = TOOLTIPS.get(chave, texto_custom)
    _tt_esc = (
        _texto_tt
        .replace('"', '&quot;')
        .replace("'", "&#39;")
    ) if _texto_tt else ""

    _tt_html = (
        f' <span title="{_tt_esc}" style="'
        f'cursor:help;color:#333;font-size:0.6rem;'
        f'border:1px solid #2a2a2a;border-radius:50%;'
        f'padding:0 4px;margin-left:2px;'
        f'font-family:Courier New;user-select:none;">?</span>'
    ) if _tt_esc else ""

    st.markdown(
        f'<div style="font-family:Courier New;'
        f'font-size:{tamanho};color:{cor};'
        f'margin-bottom:4px;">'
        f'{texto}{_tt_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
