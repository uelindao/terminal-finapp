"""
utils/charts.py
Templates e funções de gráfico padronizadas.
Garante consistência visual em todo o app.
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Paleta de cores padrão para séries múltiplas
CORES_SERIES = [
    "#FF8C00",  # laranja primário
    "#3B82F6",  # azul info
    "#10B981",  # verde esmeralda
    "#EF4444",  # vermelho
    "#8B5CF6",  # roxo
    "#06B6D4",  # ciano
    "#F59E0B",  # âmbar
    "#EC4899",  # rosa
]

LAYOUT_BASE = dict(
    paper_bgcolor="#13141E",
    plot_bgcolor="#13141E",
    font=dict(
        family="Inter, system-ui, sans-serif",
        color="#8B8FA8",
        size=11,
    ),
    margin=dict(l=0, r=0, t=30, b=0),
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor="#23243A",
        bordercolor="#353755",
        font=dict(
            family="Inter, system-ui, sans-serif",
            color="#F0F2FF",
            size=11,
        ),
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font=dict(
            color="#8B8FA8",
            size=10,
            family="Inter, system-ui, sans-serif",
        ),
        bgcolor="rgba(0,0,0,0)",
        borderwidth=0,
    ),
)

AXIS_BASE = dict(
    showgrid=True,
    gridcolor="#2A2C3E",
    gridwidth=1,
    zeroline=False,
    linecolor="#353755",
    tickfont=dict(
        family="Inter, system-ui, sans-serif",
        size=10,
        color="#4A4D6A",
    ),
)

def base_layout(height=400, title="") -> dict:
    """Retorna o layout base para qualquer gráfico."""
    layout = {**LAYOUT_BASE, "height": height}
    if title:
        layout["title"] = dict(
            text=title,
            font=dict(color="#555", size=11, family="Courier New"),
            x=0
        )
    return layout

def linha(df, x_col, y_col, titulo="", cor="#FF9900", height=300, fill=False):
    """Gráfico de linha simples e padronizado."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col] if x_col else df.index,
        y=df[y_col],
        mode="lines",
        line=dict(color=cor, width=1.5),
        fill="tozeroy" if fill else "none",
        fillcolor=f"{cor}15" if fill else None,
        hovertemplate="%{x}<br><b>%{y:.2f}</b><extra></extra>"
    ))
    layout = base_layout(height=height, title=titulo)
    layout.update(
        xaxis={**AXIS_BASE, "title": ""},
        yaxis={**AXIS_BASE, "title": ""}
    )
    fig.update_layout(**layout)
    return fig

def velas(df, titulo="", height=500, mostrar_volume=True):
    """
    Gráfico de candlestick com volume opcional.
    df deve ter colunas: Open, High, Low, Close, Volume
    """
    if mostrar_volume:
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.75, 0.25],
            vertical_spacing=0.03
        )
        row_candle, row_vol = 1, 2
    else:
        fig = go.Figure()
        row_candle = None

    candle = go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        name="Preço",
        increasing=dict(line=dict(color="#10B981"), fillcolor="#10B98120"),
        decreasing=dict(line=dict(color="#EF4444"), fillcolor="#EF444420"),
        hoverlabel=dict(font=dict(family="Inter, system-ui, sans-serif")),
    )

    if mostrar_volume:
        fig.add_trace(candle, row=1, col=1)
        cores_vol = [
            "#10B981" if c >= o else "#EF4444"
            for c, o in zip(df["Close"], df["Open"])
        ]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"],
            marker_color=cores_vol,
            name="Volume",
            showlegend=False,
            hovertemplate="%{x}<br>Vol: %{y:,.0f}<extra></extra>"
        ), row=2, col=1)
    else:
        fig.add_trace(candle)

    layout = base_layout(height=height, title=titulo)
    layout["xaxis_rangeslider_visible"] = False
    layout.update(
        xaxis={**AXIS_BASE, "title": ""},
        yaxis={**AXIS_BASE, "title": ""},
    )
    if mostrar_volume:
        layout.update(yaxis2={**AXIS_BASE, "title": "Vol"})
    fig.update_layout(**layout)
    return fig

def barras(categorias, valores, titulo="", cor="#FF9900", cor_negativo="#FF1744", height=300):
    """Barras horizontais com cores automáticas por sinal."""
    cores = [cor if v >= 0 else cor_negativo for v in valores]
    fig = go.Figure(go.Bar(
        x=valores,
        y=categorias,
        orientation='h',
        marker_color=cores,
        hovertemplate="%{y}<br><b>%{x:+.2f}</b><extra></extra>"
    ))
    layout = base_layout(height=height, title=titulo)
    layout.update(
        xaxis={**AXIS_BASE, "title": ""},
        yaxis={**AXIS_BASE, "title": ""}
    )
    fig.add_hline(y=0, line_color="#353755", line_width=1)
    fig.update_layout(**layout)
    return fig

def base100(df, titulo="", height=400):
    """Performance comparada em base 100 com legenda de retorno."""
    fig = go.Figure()
    for i, col in enumerate(df.columns):
        retorno = df[col].iloc[-1] - 100
        cor = CORES_SERIES[i % len(CORES_SERIES)]
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df[col],
            name=f"{col} ({retorno:+.1f}%)",
            line=dict(color=cor, width=1.8),
            hovertemplate=f"{col}<br>%{{x}}<br>Base 100: %{{y:.1f}}<extra></extra>"
        ))
    fig.add_hline(y=100, line_color="#353755", line_dash="dash", line_width=1)
    layout = base_layout(height=height, title=titulo)
    layout.update(
        xaxis={**AXIS_BASE},
        yaxis={**AXIS_BASE, "title": "Base 100"}
    )
    fig.update_layout(**layout)
    return fig