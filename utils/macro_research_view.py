"""Interactive exploration of macro trajectories and expectations."""
from __future__ import annotations

import html
import math
import time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.charts import base_layout, _cores
from utils.components import metric_card, section_title, section_selector, empty_state
from utils.macro_research import QUADRANTS, preparar_transicoes, revisar_expectativa, fisher

MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def month_label(value):
    value = pd.Timestamp(value)
    return f"{MONTHS[value.month-1]}/{value.year}"


def _fmt(value, suffix="%", digits=2):
    return "n/d" if value is None or pd.isna(value) else f"{value:,.{digits}f}{suffix}".replace(",", " ").replace(".", ",")


def _observed(context, field):
    value = context.get(field)
    meta = (context.get("qualidade") or {}).get(field, {})
    if meta.get("observado") is False:
        return None
    try:
        return float(value) if math.isfinite(float(value)) else None
    except (TypeError, ValueError):
        return None


def _last(frame, column):
    s = frame.get(column, pd.Series(dtype=float)).dropna()
    return (float(s.iloc[-1]), s.index[-1]) if len(s) else (None, None)


def _history(bundle, region, window, persistence, threshold):
    data = bundle["regioes"][region]
    frame = preparar_transicoes(data["atividade"], data["inflacao"],
                               inflacao_tipo=data["inflacao_tipo"], janela=window,
                               persistencia=persistence, limiar_atividade=threshold,
                               limiar_inflacao=threshold)
    return data, frame


def recortar_trajetoria(history, data_final, meses):
    """Calendar months, retaining absent observations as visible breaks."""
    final = pd.Timestamp(data_final)
    start = (final.to_period("M") - (meses - 1)).to_timestamp()
    return history.loc[start:final]


def render_transicoes(bundle, *, key_prefix="macro_transitions") -> dict:
    controls = st.columns([1, 1, 1])
    with controls[0]:
        region = st.selectbox("Economia", ["BR", "US"], format_func=lambda x: "Brasil" if x == "BR" else "EUA",
                              key=f"{key_prefix}_region")
    with controls[1]:
        window = st.selectbox("Ritmo", [3, 6], format_func=lambda x: f"{x} meses", key=f"{key_prefix}_window")
    with controls[2]:
        persistence = st.selectbox("Confirmação", [2, 3, 1], format_func=lambda x: f"{x} observações mensais",
                                   key=f"{key_prefix}_persistence")
    with st.expander("Ajustar sensibilidade e ler o método"):
        threshold = st.slider("Faixa de direção pouco definida (pp)", 0.0, 1.0, 0.25, 0.05,
                              key=f"{key_prefix}_threshold")
        st.caption("Atividade: variação anualizada da média móvel contra a média do período anterior. "
                   "Inflação: composição mensal anualizada. Os eixos mostram a mudança desses ritmos "
                   "contra o valor de três/seis meses antes. A confirmação usa observações passadas, "
                   "mas o histórico contém as revisões disponíveis hoje.")
        st.caption("Brasil: IPCA sem ajuste sazonal; o ritmo curto pode carregar sazonalidade. "
                   "EUA: produção industrial é um recorte da atividade, não o PIB completo.")
    data, history = _history(bundle, region, window, persistence, threshold)
    valid = history.dropna(subset=["delta_atividade", "delta_inflacao"])
    if valid.empty:
        empty_state("◌", "Trajetória ainda sem dados suficientes",
                    "O estudo precisa de histórico mensal de atividade e inflação. Atualize as séries ou aguarde o próximo processamento.")
        return {"regiao": region, "quadrante": None, "referencia_em": None}

    dates = list(valid.index.to_pydatetime())
    key_date = f"{key_prefix}_date"
    pending = st.session_state.pop(f"{key_prefix}_pending", None)
    if pending is not None and pd.Timestamp(pending).to_pydatetime() in dates:
        st.session_state[key_date] = pd.Timestamp(pending).to_pydatetime()
    if st.session_state.get(key_date) not in dates:
        st.session_state[key_date] = dates[-1]
    date_selected = st.select_slider("Mês de referência · explore a trajetória",
                                    options=dates, format_func=month_label, key=key_date)
    selected = valid.loc[pd.Timestamp(date_selected)]
    latest = history.iloc[-1]
    latest_ref = history.index[-1]
    if pd.Timestamp.today().normalize() - latest_ref > pd.Timedelta(days=90):
        st.warning(f"Referência mais recente: {month_label(latest_ref)}. Histórico desatualizado; atualize antes de usar como contexto atual.")
    if not bool(latest["confirmado"]):
        st.caption(f"Última referência ({month_label(latest_ref)}) sem direção confirmada. A matriz não recebe um regime presumido.")
    metric_columns = st.columns(3)
    with metric_columns[0]:
        metric_card("Atividade · ritmo anualizado", _fmt(selected["atividade_ritmo"]),
                    f"Mudança em {window}m: {_fmt(selected['delta_atividade'], ' pp')}", "info")
    with metric_columns[1]:
        metric_card("Inflação · ritmo anualizado", _fmt(selected["inflacao_ritmo"]),
                    f"Mudança em {window}m: {_fmt(selected['delta_inflacao'], ' pp')}", "amber")
    with metric_columns[2]:
        metric_card("Leitura da direção", selected["estado"],
                    f"{int(selected['consecutivos'])} observações consecutivas · {month_label(date_selected)}", "info")
    st.markdown(f"**{QUADRANTS[selected['quadrante']]}** · {data['atividade_label']}")
    view = section_selector(["Mapa", "Ritmos", "Evidências"], key=f"{key_prefix}_view", label="Exploração")
    display_months = st.selectbox("Trajetória visível", [12, 24, 60, 120],
                                  format_func=lambda x: f"{x} meses", key=f"{key_prefix}_span")
    cut = recortar_trajetoria(history, date_selected, display_months)
    colors = _cores()
    palette = {"crescimento_desinflacao": colors["bull"], "crescimento_inflacao": colors["info"],
               "desaceleracao_inflacao": colors["bear"], "desaceleracao_desinflacao": colors["amber"],
               "transicao": colors["muted"], "indisponivel": colors["muted"]}
    if view == "Mapa":
        figure = go.Figure(go.Scatter(
            x=cut["delta_atividade"], y=cut["delta_inflacao"], mode="lines+markers",
            marker=dict(size=8, color=[palette[k] for k in cut["quadrante"]]),
            line=dict(color=colors["muted"], width=1.5),
            customdata=[[str(d.date()), QUADRANTS[q], month_label(d)] for d, q in zip(cut.index, cut["quadrante"])],
            hovertemplate="%{customdata[2]}<br>Atividade: %{x:+.2f} pp<br>Inflação: %{y:+.2f} pp<br>%{customdata[1]}<extra></extra>",
            name="Trajetória", connectgaps=False,
        ))
        figure.add_trace(go.Scatter(x=[selected["delta_atividade"]], y=[selected["delta_inflacao"]],
                                   mode="markers", marker=dict(size=15, color=palette[selected["quadrante"]],
                                   line=dict(color=colors["text"], width=2)),
                                   customdata=[[str(pd.Timestamp(date_selected).date()), QUADRANTS[selected["quadrante"]], month_label(date_selected)]],
                                   name=month_label(date_selected), hovertemplate="%{customdata[2]}<extra></extra>"))
        figure.add_hline(y=0, line_color=colors["border"], line_dash="dash")
        figure.add_vline(x=0, line_color=colors["border"], line_dash="dash")
        figure.add_hrect(y0=-threshold, y1=threshold, fillcolor=colors["muted"], opacity=0.06, line_width=0)
        figure.add_vrect(x0=-threshold, x1=threshold, fillcolor=colors["muted"], opacity=0.06, line_width=0)
        figure.update_layout(**base_layout(height=460, title="Direção da atividade × direção da inflação"))
        figure.update_xaxes(title_text=f"Mudança do ritmo de atividade em {window}m (pp)", zeroline=False)
        figure.update_yaxes(title_text=f"Mudança do ritmo de inflação em {window}m (pp)", zeroline=False)
        event = st.plotly_chart(figure, width='stretch', key=f"{key_prefix}_map",
                                on_select="rerun", selection_mode=["points"],
                                config={"displaylogo": False, "responsive": True})
        selection = event.get("selection", {}).get("points", [])
        if selection:
            custom = selection[0].get("customdata") or []
            if custom:
                picked = pd.Timestamp(custom[0]).to_pydatetime()
                signature = str(picked)
                if signature != st.session_state.get(f"{key_prefix}_last_pick") and picked in dates:
                    st.session_state[f"{key_prefix}_last_pick"] = signature
                    st.session_state[f"{key_prefix}_pending"] = picked
                    st.rerun()
        st.caption("Clique em um ponto para inspecionar o mês. Direções se referem ao ritmo, e não ao nível: "
                   "desaceleração pode ocorrer com crescimento positivo. O gráfico não indica fundo do ciclo ou compra.")
    elif view == "Ritmos":
        figure = go.Figure()
        for column, name, color in [("atividade_ritmo", "Atividade", colors["info"]),
                                    ("inflacao_ritmo", "Inflação", colors["amber"])]:
            figure.add_trace(go.Scatter(x=cut.index, y=cut[column], name=name,
                                       line=dict(color=color, width=2), connectgaps=False))
        figure.update_layout(**base_layout(height=400, title=f"Ritmos anualizados · {window} meses"))
        figure.update_yaxes(title_text="% anualizado")
        st.plotly_chart(figure, width='stretch', key=f"{key_prefix}_rates")
    else:
        previous_options = [d for d in dates if d <= date_selected]
        comparison_key = f"{key_prefix}_comparison"
        if st.session_state.get(comparison_key) not in previous_options:
            st.session_state[comparison_key] = previous_options[max(0, len(previous_options)-4)]
        comparison = st.selectbox("Comparar com", previous_options,
                                   format_func=month_label, key=comparison_key)
        previous = valid.loc[pd.Timestamp(comparison)]
        table = pd.DataFrame([
            {"medida": "Ritmo da atividade (% a.a.)", "mês selecionado": selected["atividade_ritmo"],
             "comparação": previous["atividade_ritmo"], "mudança (pp)": selected["atividade_ritmo"]-previous["atividade_ritmo"]},
            {"medida": "Ritmo da inflação (% a.a.)", "mês selecionado": selected["inflacao_ritmo"],
             "comparação": previous["inflacao_ritmo"], "mudança (pp)": selected["inflacao_ritmo"]-previous["inflacao_ritmo"]},
        ])
        st.dataframe(table, hide_index=True, width='stretch')
        export = history.copy()
        export["leitura"] = export["quadrante"].map(QUADRANTS)
        st.download_button("Exportar trajetória", export.to_csv(index_label="referencia_em").encode("utf-8-sig"),
                           file_name=f"trajetoria_macro_{region.lower()}.csv", mime="text/csv",
                           key=f"{key_prefix}_export")
    return {"regiao": region, "quadrante": latest["quadrante"], "confirmado": bool(latest["confirmado"]),
            "referencia_em": latest_ref.isoformat(), "janela": window, "persistencia": persistence,
            "historico": history}


def render_expectativas(bundle, macro_context=None, *, key_prefix="macro_expectations"):
    context = macro_context or {}
    focus = bundle["focus"]
    view = section_selector(["Ano de referência", "Inflação 12m", "Juros e preços"], key=f"{key_prefix}_view")
    colors = _cores()
    if view in ("Ano de referência", "Inflação 12m"):
        if focus.empty:
            empty_state("◌", "Expectativas ainda indisponíveis",
                        "Atualize as séries. A bancada compara medianas do mesmo horizonte e da mesma base de participantes.")
            return
        if view == "Ano de referência":
            annual = focus[focus["horizonte"] != "12m móveis"]
            years = sorted(annual["horizonte"].astype(str).unique())
            if not years:
                st.info("Sem dados anuais nesta consulta.")
                return
            next_year = str(pd.Timestamp.today().year + 1)
            year = st.selectbox("Ano previsto", years, index=years.index(next_year) if next_year in years else len(years)-1,
                                key=f"{key_prefix}_year")
            horizon = year
            indicators = [x for x in ["IPCA", "Selic", "PIB Total", "Câmbio"] if x in annual["indicador"].unique()]
        else:
            horizon = "12m móveis"
            indicators = ["IPCA"]
        days = st.selectbox("Revisão contra", [30, 90], format_func=lambda n: f"{n} dias antes",
                            key=f"{key_prefix}_revision")
        rows = []
        for indicator in indicators:
            result = revisar_expectativa(focus, indicator, horizon, dias=days)
            rows.append({"Indicador": indicator, "Mediana": result["atual"],
                         "Revisão": result["revisao"], "Data da pesquisa": result["data"],
                         "Pesquisa anterior": result["data_anterior"], "Respondentes": result["respondentes"],
                         "Idade (dias)": None if result["data"] is None else
                         (pd.Timestamp.today().normalize() - result["data"].normalize()).days})
        columns = st.columns(min(3, max(1, len(rows))))
        for i, row in enumerate(rows):
            suffix = " BRL/USD" if row["Indicador"] == "Câmbio" else "%"
            revision_unit = " BRL/USD" if row["Indicador"] == "Câmbio" else " pp"
            with columns[i % len(columns)]:
                metric_card(f"{row['Indicador']} · {horizon}", _fmt(row["Mediana"], suffix),
                            f"Revisão: {_fmt(row['Revisão'], revision_unit)}", "info")
        indicator = st.selectbox("Explorar expectativa", indicators, key=f"{key_prefix}_indicator")
        subset = focus[(focus["indicador"] == indicator) & (focus["horizonte"] == horizon)].sort_values("data")
        figure = go.Figure(go.Scatter(x=subset["data"], y=subset["mediana"], mode="lines", name=f"{indicator} · {horizon}",
                                     line=dict(color=colors["accent"], width=2), connectgaps=False))
        figure.update_layout(**base_layout(height=360, title=f"Revisões da mediana · {indicator} · {horizon}"))
        st.plotly_chart(figure, width='stretch', key=f"{key_prefix}_chart")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        st.caption("Focus é uma pesquisa de expectativas, não uma previsão do Banco Central ou uma medida direta "
                   "do preço de mercado. Comparações anuais conservam o mesmo ano previsto; 12m móveis muda de "
                   "período-alvo ao longo do tempo. A revisão fica ausente quando falta uma pesquisa próxima à data anterior.")
        stale = [row for row in rows if row["Idade (dias)"] is not None and row["Idade (dias)"] > 10]
        for row in stale:
            st.warning(f"{row['Indicador']} · {horizon}: pesquisa de {row['Data da pesquisa']:%d/%m/%Y} "
                       f"({row['Idade (dias)']} dias). Esta expectativa está desatualizada.")
        st.markdown("[Fonte e metodologia: expectativas de mercado do BCB](https://www.bcb.gov.br/controleinflacao/expectativasmercado)")
    else:
        us = bundle["regioes"]["US"]["dados"]
        nominal, nominal_date = _last(us, "DGS10")
        real, real_date = _last(us, "DFII10")
        breakeven, breakeven_date = _last(us, "T10YIE")
        for label, reference in [("Nominal 10a", nominal_date), ("Real TIPS 10a", real_date),
                                 ("Compensação de inflação", breakeven_date)]:
            if reference is not None and (pd.Timestamp.today().normalize() - pd.Timestamp(reference).normalize()).days > 10:
                st.warning(f"{label}: última cotação de {_date(reference)}. Série desatualizada.")
        a, b, c = st.columns(3)
        with a:
            metric_card("Treasury nominal · 10 anos", _fmt(nominal), f"DGS10 · {_date(nominal_date)}", "info")
        with b:
            metric_card("Treasury real · 10 anos", _fmt(real), f"TIPS DFII10 · {_date(real_date)}", "info")
        with c:
            metric_card("Compensação de inflação · 10 anos", _fmt(breakeven), f"T10YIE · {_date(breakeven_date)}", "amber")
        if not us.empty:
            figure = go.Figure()
            for column, label, color in [("DGS10", "Nominal 10a", colors["accent"]), ("DFII10", "Real 10a", colors["info"]),
                                         ("T10YIE", "Compensação de inflação", colors["amber"])]:
                if column in us:
                    s = us[column].loc[us.index >= us.index.max() - pd.DateOffset(years=3)]
                    figure.add_trace(go.Scatter(x=s.index, y=s, name=label, line=dict(color=color), connectgaps=False))
            figure.update_layout(**base_layout(height=380, title="Juros longos e compensação de inflação · EUA"))
            figure.update_yaxes(title_text="% ao ano")
            st.plotly_chart(figure, width='stretch', key=f"{key_prefix}_yields")
        st.caption("Compensação de inflação inclui expectativas, prêmios de risco e liquidez. "
                   "Taxas longas não seguem mecanicamente as decisões do Fed. Ausências não são substituídas por valores presumidos.")
        focus_12m = revisar_expectativa(focus, "IPCA", "12m móveis") if not focus.empty else {"atual": None, "data": None}
        focus_date = focus_12m.get("data")
        focus_fresh = (focus_date is not None and 0 <=
                       (pd.Timestamp.today().normalize() - focus_date.normalize()).days <= 10)
        nominal_br = _observed(context, "selic")
        proxy = fisher(nominal_br, focus_12m["atual"]) if focus_fresh else None
        metric_card("Brasil · proxy real ex ante", _fmt(proxy),
                    f"Selic constante por 12m · pesquisa Focus {_date(focus_date)}", "amber")
        if not focus_fresh:
            st.caption("Proxy suspensa: falta uma pesquisa IPCA 12m de até dez dias atrás.")
        st.caption("A proxy não usa a curva DI nem a taxa nominal média esperada. A Selic de fim de ano do Focus "
                   "tem outro horizonte e não entra automaticamente nessa conta.")
        st.markdown("[Taxa real TIPS: FRED DFII10](https://fred.stlouisfed.org/series/DFII10)")


def _date(value):
    return "sem dado" if value is None else pd.Timestamp(value).strftime("%d/%m/%Y")


def render_bancada_macro(macro_context=None):
    from utils.macro_research_data import carregar_bancada
    context = macro_context or {}
    section_title("Bancada de rotação macro")
    st.caption("Acompanhe transições, expectativas e exposições por horizonte. Cada estudo explicita suas hipóteses.")
    control_a, control_b = st.columns([3, 1])
    with control_a:
        horizon = st.selectbox("Horizonte da tese", [6, 3, 12, 24, 36],
                               format_func=lambda n: f"{n} meses · {'médio' if n <= 12 else 'longo'} prazo",
                               key="macro_research_horizon")
    with control_b:
        refresh = st.button("Atualizar séries", key="macro_research_refresh", width='stretch')
    if refresh:
        with st.spinner("Consultando fontes públicas e atualizando a bancada…"):
            carregar_bancada.clear()
            st.session_state["_macro_research_fresh"] = carregar_bancada(True)
            st.session_state["_macro_research_fresh_at"] = time.time()
    if time.time() - st.session_state.get("_macro_research_fresh_at", 0) >= 3600:
        st.session_state.pop("_macro_research_fresh", None)
    bundle = st.session_state.get("_macro_research_fresh") or carregar_bancada(False)
    study = section_selector(["Transições", "Expectativas", "Rotação", "Laboratório", "Teses"],
                             key="macro_research_study", label="Estudo")
    if study == "Transições":
        selection = render_transicoes(bundle)
        st.session_state["_macro_research_latest"] = {k: v for k, v in selection.items() if k != "historico"}
    elif study == "Expectativas":
        render_expectativas(bundle, context)
    elif study == "Rotação":
        from utils.rotation_matrix_view import render_matriz_rotacao
        selection = st.session_state.get("_macro_research_latest", {})
        render_matriz_rotacao(macro_context=context, horizonte_meses=horizon,
                              quadrante=selection.get("quadrante") if selection.get("confirmado") else None)
        if selection.get("referencia_em"):
            st.caption(f"Última referência macro disponível: {selection.get('regiao')} · "
                       f"{month_label(selection['referencia_em'])}. Preços têm suas próprias datas na matriz.")
    elif study == "Laboratório":
        from utils.rotation_backtest_view import render_laboratorio_rotacao
        render_laboratorio_rotacao(bundle, horizonte_meses=horizon)
    else:
        from utils.macro_theses_view import render_teses_macro
        selection = st.session_state.get("_macro_research_latest", {})
        render_teses_macro(macro_context=context, quadrante=selection.get("quadrante"), horizonte_meses=horizon)
    with st.expander("Fontes, cobertura e datas"):
        st.dataframe(pd.DataFrame(bundle["qualidade"]), hide_index=True, width='stretch')
        st.caption(bundle["base_temporal"])
        for warning in bundle["avisos"]:
            st.caption(warning)
