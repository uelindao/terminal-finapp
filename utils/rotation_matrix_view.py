"""Bancada interativa de rotação sobre caches existentes, com leitura explícita."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.charts import base_layout, _cores, _axis
from utils.components import metric_card, section_title
from utils.rotation_matrix import (
    HORIZONTES_MESES, FX_TICKER, metadata_padrao, carregar_precos_matriz,
    calcular_matriz_rotacao, trajetoria_comparada, matriz_setores_snapshot,
)


def _percentual(value):
    return "—" if value is None or pd.isna(value) else f"{float(value) * 100:+.2f}%"


def _mostrar_setores_br(contexto, meses, key_prefix):
    from utils.sector_scorecard import calcular_scorecard_setorial
    from utils.divergencia_live import _snapshot_rs
    snapshot = _snapshot_rs()
    sc = calcular_scorecard_setorial("BR", contexto)
    frame = matriz_setores_snapshot(snapshot, sc, meses)
    st.caption("Setores BR · média simples de ativos do universo atual · benchmark: mediana dos setores.")
    if frame.empty:
        st.info("Ainda não há dados setoriais preparados no cache.")
        return None
    st.caption(f"Preços até {snapshot.get('data') or 'data indisponível'}. Fundamentos e macro são leituras atuais.")
    snapshot_date = pd.to_datetime(snapshot.get("data"), errors="coerce", utc=True)
    today = pd.Timestamp.now(tz="America/Sao_Paulo").normalize()
    if pd.isna(snapshot_date):
        st.warning("Snapshot sem data de preços. A atualidade desta comparação não pode ser confirmada.")
    elif (today.tz_convert("UTC") - snapshot_date).days > 14:
        st.warning("Snapshot de preços desatualizado: a diferença de retornos abaixo pertence ao período indicado, não à leitura atual do mercado.")
    validos = frame.dropna(subset=["relativo"])
    if validos.empty:
        st.info(f"Não há RS de {meses} meses no snapshot disponível. O snapshot legado contém somente 3 meses.")
    else:
        colors = _cores()
        ordem = validos.sort_values("relativo")
        fig = go.Figure(go.Bar(
            x=ordem["relativo"] * 100, y=ordem["label"], orientation="h",
            marker_color=[colors["bull"] if v >= 0 else colors["bear"] for v in ordem["relativo"]],
            hovertemplate="%{y}<br>Diferença: %{x:+.2f} pp<extra></extra>"))
        fig.update_layout(**base_layout(height=380, title=f"Diferença de retorno · {meses} meses"))
        fig.update_xaxes(**_axis(), title="Retorno do setor menos mediana (pp)")
        fig.update_yaxes(**_axis())
        st.plotly_chart(fig, width='stretch', theme=None, key=f"{key_prefix}_br_rs")
    tabela = frame[["label", "relativo", "fundamento", "qualidade", "valuation", "macro",
                    "cobertura_fundamento", "cobertura_tecnico", "status"]].copy()
    tabela["relativo"] *= 100
    tabela.rename(columns={"label": "Setor", "relativo": "Diferença de retorno (pp)",
                           "fundamento": "Fundamento", "qualidade": "Qualidade",
                           "valuation": "Valuation", "macro": "Macro",
                           "cobertura_fundamento": "Cobertura fundamentos (%)",
                           "cobertura_tecnico": "Cobertura momentum 12m (%)",
                           "status": "Histórico"}, inplace=True)
    st.dataframe(tabela, hide_index=True, width='stretch')
    st.caption("O snapshot usa retorno do setor menos retorno mediano, em pontos percentuais. Os pilares refletem o cache atual; o técnico do scorecard usa 12 meses. Eles não são recalculados retrospectivamente ao trocar o horizonte.")
    selecionado = st.selectbox("Inspecionar setor", frame["setor"].tolist(),
                              format_func=lambda s: frame.set_index("setor").loc[s, "label"],
                              key=f"{key_prefix}_br_sector")
    row = frame.loc[frame["setor"] == selecionado].iloc[0].to_dict()
    cols = st.columns(2)
    with cols[0]:
        metric_card("Qualidade", "—" if pd.isna(row["qualidade"]) else f'{row["qualidade"]:.0f}/100',
                    "ROE e margem observados")
    with cols[1]:
        metric_card("Valuation", "—" if pd.isna(row["valuation"]) else f'{row["valuation"]:.0f}/100',
                    "P/L e P/VP observados")
    st.write("Ativos com dados: " + ", ".join(row.get("tickers") or []) + ".")
    if row.get("macro_detalhes"):
        for nome, texto in row["macro_detalhes"].items():
            st.caption(f"{nome}: {texto}")
    with st.expander("Cobertura e método do setor"):
        st.json({"cobertura_por_campo": row.get("cobertura_por_campo"),
                 "metricas_medias": row.get("metricas_medias"), "metodologia": row.get("metodologia")})
        for alerta in row.get("alertas") or []:
            st.caption(alerta)
        st.caption(row["fonte"])
        st.caption(row["metodo_relativo"])
    return row


def render_matriz_rotacao(macro_context=None, horizonte_meses=6, quadrante=None,
                         key_prefix="macro_rotation"):
    """Classes e setores sem ranking comum; retorna a linha inspecionada."""
    section_title("Matriz de rotação")
    st.caption("Compare o que os preços fizeram, a moeda do resultado e as sensibilidades econômicas de cada exposição.")
    controles = st.columns(2)
    with controles[0]:
        mercado = st.radio("Mercado", ["BR", "US"], horizontal=True,
                           format_func=lambda x: "Brasil" if x == "BR" else "Estados Unidos",
                           key=f"{key_prefix}_market")
    with controles[1]:
        tipo = st.radio("Universo", ["Classes", "Setores"], horizontal=True, key=f"{key_prefix}_type")
    controles = st.columns(2)
    with controles[0]:
        chave_global = f"{key_prefix}_global_horizon"
        chave_janela = f"{key_prefix}_months"
        # A mudança da tese sincroniza uma vez. Depois disso, o usuário pode
        # explorar outra janela local até mudar novamente o horizonte global.
        if st.session_state.get(chave_global) != horizonte_meses:
            st.session_state[chave_global] = horizonte_meses
            st.session_state[chave_janela] = horizonte_meses if horizonte_meses in HORIZONTES_MESES else None
        meses = st.selectbox("Janela observada", (None, *HORIZONTES_MESES),
                             format_func=lambda x: "Escolha uma janela disponível" if x is None else f"{x} meses",
                             key=chave_janela,
                             help="A janela pode ser explorada separadamente do horizonte da tese. Mudanças na tese sincronizam esta seleção.")
    with controles[1]:
        moeda = st.radio("Moeda do resultado", ["nativa", "BRL"], horizontal=True,
                         format_func=lambda x: "Origem do ativo" if x == "nativa" else "Reais",
                         key=f"{key_prefix}_currency")
    if horizonte_meses not in HORIZONTES_MESES:
        st.warning(f"O horizonte da tese de {horizonte_meses} meses não está disponível nesta comparação de preços. Escolha uma janela de 3, 6, 12 ou 24 meses.")
    if meses is None:
        return None
    if meses != horizonte_meses:
        st.caption(f"Exploração local: {meses} meses de preços · horizonte da tese: {horizonte_meses} meses.")
    if quadrante is not None:
        st.caption(f"Recorte macro selecionado: {quadrante}. Sensibilidades são qualitativas; retornos abaixo são observados.")
    if tipo == "Setores" and mercado == "BR":
        return _mostrar_setores_br(macro_context or {}, meses, key_prefix)

    metadata = metadata_padrao(mercado, tipo)
    benchmark = "BOVA11.SA" if mercado == "BR" else "SPY"
    unidade_bmk = "BRL" if mercado == "BR" else "USD"
    tickers = tuple(sorted({m["ticker"] for m in metadata} | {benchmark} | ({FX_TICKER} if mercado == "US" and moeda == "BRL" else set())))
    state_key = f"{key_prefix}_history"
    request = (tickers, 550)
    estado = st.session_state.get(state_key) or {}
    if st.button("Ler histórico disponível", icon=":material/database:", key=f"{key_prefix}_load"):
        with st.spinner("Lendo os proxies do histórico já preparado…"):
            try:
                precos = carregar_precos_matriz(*request)
                st.session_state[state_key] = {"request": request, "prices": precos}
                estado = st.session_state[state_key]
            except Exception as exc:
                st.error(f"Não foi possível ler o histórico: {exc}")
                return None
    st.caption(f"Até {len(tickers)} proxies do cache · benchmark {benchmark.removesuffix('.SA')} · preços ajustados preparados pelo ETL.")
    if estado.get("request") != request:
        st.info("Use “Ler histórico disponível” para abrir este universo. A leitura fica disponível enquanto você explora as janelas.")
        return None
    precos = estado["prices"]
    if precos is None or precos.empty:
        st.info("Esses proxies ainda não têm histórico no cache. Eles permanecem indisponíveis até a atualização agendada de preços.")
        return None
    scorecards = {}
    if tipo == "Setores":
        from utils.sector_scorecard import calcular_scorecard_setorial
        scorecards = {r["setor"]: r for r in calcular_scorecard_setorial(mercado, macro_context or {})}
    frame = calcular_matriz_rotacao(
        precos, metadata, meses, moeda, benchmark=benchmark,
        benchmark_moeda=unidade_bmk, scorecards=scorecards)
    validos = frame.loc[frame["status"] == "observado"]
    if not validos.empty:
        cores = _cores()
        mapa = validos.dropna(subset=["volatilidade"])
        if not mapa.empty:
            fig = go.Figure(go.Scatter(
                x=mapa["retorno"] * 100, y=mapa["volatilidade"] * 100,
                text=mapa["label"], mode="markers+text", textposition="top center",
                customdata=mapa[["ticker", "relativo"]].values,
                marker=dict(size=13, color=mapa["relativo"] * 100,
                            colorscale=[[0, cores["bear"]], [0.5, cores["muted"]], [1, cores["bull"]]],
                            cmid=0, showscale=False),
                hovertemplate="%{text}<br>Retorno %{x:+.2f}%<br>Vol. histórica %{y:.2f}%<extra></extra>"))
            fig.update_layout(**base_layout(height=390, title="Retorno × oscilação histórica"))
            fig.update_xaxes(**_axis(), title="Retorno na moeda selecionada (%)")
            fig.update_yaxes(**_axis(), title="Volatilidade anualizada (%)")
            st.plotly_chart(fig, theme=None, width='stretch', key=f"{key_prefix}_map")
            st.caption("Cor: retorno relativo ao benchmark da mesma moeda. Volatilidade é descritiva da janela; gaps não são preenchidos.")
    colunas = ["label", "ticker", "retorno", "relativo", "moeda_exibicao", "cobertura", "inicio", "fim", "status"]
    tabela = frame[colunas].copy()
    for campo in ("retorno", "relativo", "cobertura"):
        tabela[campo] *= 100
    tabela.rename(columns={"label": "Exposição", "ticker": "Proxy", "retorno": "Retorno (%)",
                           "relativo": f"RS vs {benchmark.removesuffix('.SA')} (%)",
                           "moeda_exibicao": "Moeda", "cobertura": "Cobertura (%)",
                           "inicio": "Início", "fim": "Fim", "status": "Dados"}, inplace=True)
    st.dataframe(tabela, hide_index=True, width='stretch')
    if validos.empty:
        st.info("Nenhum proxy cobre esta janela com benchmark, extremos comuns e pelo menos 80% de observações.")
    ticker = st.selectbox("Inspecionar exposição", frame["ticker"].tolist(),
                          format_func=lambda t: f"{frame.set_index('ticker').loc[t, 'label']} · {t.removesuffix('.SA')}",
                          key=f"{key_prefix}_asset_{mercado}_{tipo}")
    row = frame.loc[frame["ticker"] == ticker].iloc[0].to_dict()
    if row["status"] != "observado":
        st.info(row["motivo"])
        st.caption(row["risco"])
        return row
    cols = st.columns(2)
    with cols[0]:
        metric_card(f'Retorno · {row["moeda_exibicao"]}', _percentual(row["retorno"]),
                    f'{meses} meses · {row["inicio"]:%d/%m/%Y} → {row["fim"]:%d/%m/%Y}')
    with cols[1]:
        metric_card("Relativo ao benchmark", _percentual(row["relativo"]),
                    f'{benchmark.removesuffix(".SA")} · mesmas datas e moeda',
                    cor_delta="bull" if row["relativo"] >= 0 else "bear")
    path = trajetoria_comparada(precos, row)
    fig = go.Figure()
    for coluna, cor in zip(path.columns, [_cores()["accent"], _cores()["muted"]]):
        fig.add_trace(go.Scatter(x=path.index, y=path[coluna], name=coluna,
                                mode="lines", line=dict(color=cor, width=2), connectgaps=False))
    fig.update_layout(**base_layout(height=300, title="Patrimônio normalizado · início = 100"))
    fig.update_xaxes(**_axis())
    fig.update_yaxes(**_axis(), title=row["moeda_exibicao"])
    st.plotly_chart(fig, width='stretch', theme=None, key=f"{key_prefix}_path")
    st.write(row["risco"])
    if pd.notna(row["contribuicao_fx"]):
        st.caption(f'Ativo em {row["moeda_origem"]}: {_percentual(row["retorno_nativo"])} · câmbio: {_percentual(row["retorno_fx"])} · contribuição cambial com interação: {_percentual(row["contribuicao_fx"])}.')
    if row.get("scorecard"):
        sc = row["scorecard"]
        st.caption(f'Pilares atuais do universo de empresas: fundamento {sc.get("fundamento")} · valuation {sc.get("valuation")} · macro {sc.get("macro")}. A composição do ETF pode diferir desse universo.')
        with st.expander("Decomposição do setor"):
            st.json({k: sc.get(k) for k in ["qualidade", "valuation", "macro_detalhes", "cobertura_por_campo", "metricas_medias", "metodologia"]})
    with st.expander("Fonte e método da comparação"):
        st.markdown(f'[Características do proxy]({row["fonte"]})')
        st.caption("Preços: cache price_history, preparado pelo ETL com ajuste de splits e distribuições. Não há custos pessoais, impostos ou spread de execução nesta comparação.")
        st.caption("RS=(1+retorno do ativo)/(1+retorno do benchmark)−1. Conversão USD→BRL=(1+retorno USD)*(1+variação BRL por USD)−1. Sem preenchimento de observações ausentes.")
    return row
