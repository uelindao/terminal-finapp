"""
utils/charts.py
Templates e funções de gráfico padronizadas.
Garante consistência visual em todo o app — cores seguem o tema ativo.
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


# ── Paleta fallback (quando tema não disponível) ──────────────────────────────
CORES_SERIES = [
    "#FF8C00", "#3B82F6", "#10B981", "#EF4444",
    "#8B5CF6", "#06B6D4", "#F59E0B", "#EC4899",
]


def _cores() -> dict:
    """Retorna paleta de cores do tema ativo."""
    try:
        from utils.themes import get_chart_colors
        return get_chart_colors()
    except Exception:
        return {
            "accent":   "#FF8C00",
            "bull":     "#10B981",
            "bear":     "#EF4444",
            "amber":    "#F59E0B",
            "info":     "#3B82F6",
            "text":     "#F0F2FF",
            "muted":    "#6B7280",
            "surface":  "#1C1D2B",
            "elevated": "#23243A",
            "border":   "#2A2C3E",
        }


def base_layout(height: int = 400, title: str = "") -> dict:
    """Retorna o layout base para qualquer gráfico (cores dinâmicas por tema)."""
    c = _cores()
    layout = dict(
        paper_bgcolor=c["surface"],
        plot_bgcolor=c["surface"],
        font=dict(family="Inter, system-ui, sans-serif", color=c["muted"], size=11),
        margin=dict(l=0, r=0, t=30 if title else 12, b=0),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=c["elevated"],
            bordercolor=c["border"],
            font=dict(family="Inter, system-ui, sans-serif", color=c["text"], size=11),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right",  x=1,
            font=dict(color=c["muted"], size=10, family="Inter, system-ui, sans-serif"),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
        ),
        height=height,
    )
    if title:
        layout["title"] = dict(
            text=title,
            font=dict(color=c["muted"], size=11, family="Courier New"),
            x=0,
        )
    return layout


def _axis() -> dict:
    """Retorna estilo de eixo para o tema ativo."""
    c = _cores()
    return dict(
        showgrid=True,
        gridcolor=c["border"],
        gridwidth=1,
        zeroline=False,
        linecolor=c["border"],
        tickfont=dict(family="Inter, system-ui, sans-serif", size=10, color=c["muted"]),
    )


# Alias para retrocompatibilidade com imports que fazem `from utils.charts import AXIS_BASE`
@property
def _axis_base_compat():
    return _axis()

AXIS_BASE = dict(
    showgrid=True, gridcolor="#2A2C3E", gridwidth=1,
    zeroline=False, linecolor="#353755",
    tickfont=dict(family="Inter, system-ui, sans-serif", size=10, color="#4A4D6A"),
)
LAYOUT_BASE = dict(
    paper_bgcolor="#13141E", plot_bgcolor="#13141E",
    font=dict(family="Inter, system-ui, sans-serif", color="#8B8FA8", size=11),
    margin=dict(l=0, r=0, t=30, b=0),
    hovermode="x unified",
)


# ── CHART TYPE TOGGLE ─────────────────────────────────────────────────────────

def chart_type_toggle(key: str = "chart_type", default: str = "linha") -> str:
    """
    Widget compacto de toggle linha / barras.
    Retorna 'linha' ou 'barras'.

    Parâmetros
    ----------
    key     : chave única no session_state (use key diferente por seção)
    default : tipo inicial ('linha' | 'barras')
    """
    sk = f"_ct_{key}"
    if sk not in st.session_state:
        st.session_state[sk] = default

    atual = st.session_state[sk]
    c = _cores()

    # Botões inline via HTML + session_state trick
    col_l, col_b, col_space = st.columns([1, 1, 8])
    if col_l.button(
        "📈 linha",
        key=f"{sk}_linha",
        help="gráfico de linha",
        type="primary" if atual == "linha" else "secondary",
        use_container_width=True,
    ):
        st.session_state[sk] = "linha"
        st.rerun()

    if col_b.button(
        "📊 barras",
        key=f"{sk}_barras",
        help="gráfico de barras",
        type="primary" if atual == "barras" else "secondary",
        use_container_width=True,
    ):
        st.session_state[sk] = "barras"
        st.rerun()

    return st.session_state[sk]


# ── FUNÇÕES DE GRÁFICO ────────────────────────────────────────────────────────

def linha(df, x_col, y_col, titulo="", cor=None, height=300, fill=False):
    """Gráfico de linha simples e padronizado."""
    c = _cores()
    cor = cor or c["accent"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col] if x_col else df.index,
        y=df[y_col],
        mode="lines",
        line=dict(color=cor, width=1.8),
        fill="tozeroy" if fill else "none",
        fillcolor=f"{cor}18" if fill else None,
        hovertemplate="%{x}<br><b>%{y:.2f}</b><extra></extra>",
    ))
    ax = _axis()
    layout = base_layout(height=height, title=titulo)
    layout.update(xaxis={**ax, "title": ""}, yaxis={**ax, "title": ""})
    fig.update_layout(**layout)
    return fig


def linha_ou_barras(
    df, x_col, y_col,
    tipo: str = "linha",
    titulo: str = "",
    cor: str = None,
    cor_negativo: str = None,
    height: int = 300,
    fill: bool = False,
):
    """
    Renderiza como linha ou barras verticais conforme `tipo`.
    Compatível com chart_type_toggle().

    tipo : 'linha' | 'barras'
    """
    c = _cores()
    cor          = cor          or c["accent"]
    cor_negativo = cor_negativo or c["bear"]
    ax           = _axis()
    layout       = base_layout(height=height, title=titulo)
    layout.update(xaxis={**ax, "title": ""}, yaxis={**ax, "title": ""})

    fig = go.Figure()

    xs = df[x_col] if x_col else df.index
    ys = df[y_col]

    if tipo == "barras":
        cores_bar = [cor if v >= 0 else cor_negativo for v in ys]
        fig.add_trace(go.Bar(
            x=xs, y=ys,
            marker_color=cores_bar,
            hovertemplate="%{x}<br><b>%{y:.2f}</b><extra></extra>",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="lines",
            line=dict(color=cor, width=1.8),
            fill="tozeroy" if fill else "none",
            fillcolor=f"{cor}18" if fill else None,
            hovertemplate="%{x}<br><b>%{y:.2f}</b><extra></extra>",
        ))

    fig.update_layout(**layout)
    return fig


def velas(df, titulo="", height=500, mostrar_volume=True):
    """Candlestick com volume opcional."""
    c = _cores()
    if mostrar_volume:
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.75, 0.25], vertical_spacing=0.03,
        )
    else:
        fig = go.Figure()

    candle = go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        name="Preço",
        increasing=dict(line=dict(color=c["bull"]), fillcolor=f'{c["bull"]}20'),
        decreasing=dict(line=dict(color=c["bear"]), fillcolor=f'{c["bear"]}20'),
        hoverlabel=dict(font=dict(family="Inter, system-ui, sans-serif")),
    )

    ax = _axis()
    layout = base_layout(height=height, title=titulo)
    layout["xaxis_rangeslider_visible"] = False
    layout.update(xaxis={**ax}, yaxis={**ax})

    if mostrar_volume:
        fig.add_trace(candle, row=1, col=1)
        cores_vol = [
            c["bull"] if close >= open_ else c["bear"]
            for close, open_ in zip(df["Close"], df["Open"])
        ]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"],
            marker_color=cores_vol,
            name="Volume", showlegend=False,
            hovertemplate="%{x}<br>Vol: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)
        layout.update(yaxis2={**ax, "title": "Vol"})
    else:
        fig.add_trace(candle)

    fig.update_layout(**layout)
    return fig


def barras(categorias, valores, titulo="", cor=None, cor_negativo=None, height=300):
    """Barras horizontais com cores automáticas por sinal."""
    c = _cores()
    cor          = cor          or c["accent"]
    cor_negativo = cor_negativo or c["bear"]
    cores = [cor if v >= 0 else cor_negativo for v in valores]

    ax = _axis()
    layout = base_layout(height=height, title=titulo)
    layout.update(xaxis={**ax, "title": ""}, yaxis={**ax, "title": ""})

    fig = go.Figure(go.Bar(
        x=valores, y=categorias, orientation="h",
        marker_color=cores,
        hovertemplate="%{y}<br><b>%{x:+.2f}</b><extra></extra>",
    ))
    fig.add_hline(y=0, line_color=c["border"], line_width=1)
    fig.update_layout(**layout)
    return fig


def barras_verticais(
    categorias,
    valores,
    titulo: str = "",
    cor: str = None,
    cor_negativo: str = None,
    height: int = 300,
    show_values: bool = True,
):
    """
    Barras verticais com cores automáticas por sinal e valores no topo.
    Ideal para comparação de múltiplos, crescimento trimestral, etc.
    """
    c = _cores()
    cor          = cor          or c["accent"]
    cor_negativo = cor_negativo or c["bear"]
    cores = [cor if v >= 0 else cor_negativo for v in valores]

    ax = _axis()
    layout = base_layout(height=height, title=titulo)
    layout.update(xaxis={**ax, "title": ""}, yaxis={**ax, "title": ""})

    text_vals = [f"{v:+.1f}%" if all(abs(vv) <= 200 for vv in valores) else f"{v:,.0f}"
                 for v in valores] if show_values else None

    fig = go.Figure(go.Bar(
        x=categorias, y=valores,
        marker_color=cores,
        text=text_vals,
        textposition="outside",
        textfont=dict(size=9, color=c["muted"], family="Courier New"),
        hovertemplate="%{x}<br><b>%{y:+.2f}</b><extra></extra>",
    ))
    fig.add_hline(y=0, line_color=c["border"], line_width=1)
    fig.update_layout(**layout)
    return fig


def base100(df, titulo="", height=400):
    """Performance comparada em base 100."""
    c = _cores()
    fig = go.Figure()
    cores_seq = [c["accent"], c["info"], c["bull"], c["amber"], c["bear"],
                 "#8B5CF6", "#06B6D4", "#EC4899"]

    for i, col in enumerate(df.columns):
        retorno = df[col].iloc[-1] - 100
        cor = cores_seq[i % len(cores_seq)]
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col],
            name=f"{col} ({retorno:+.1f}%)",
            line=dict(color=cor, width=1.8),
            hovertemplate=f"{col}<br>%{{x}}<br>Base 100: %{{y:.1f}}<extra></extra>",
        ))

    ax = _axis()
    layout = base_layout(height=height, title=titulo)
    layout.update(xaxis={**ax}, yaxis={**ax, "title": "Base 100"})
    fig.add_hline(y=100, line_color=c["border"], line_dash="dash", line_width=1)
    fig.update_layout(**layout)
    return fig
