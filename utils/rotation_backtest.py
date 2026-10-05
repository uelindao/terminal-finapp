"""Simulador mensal retrospectivo com execução causal e custos explícitos.

Recebe preços ajustados na MESMA moeda. A disponibilidade dos sinais é fornecida
pelo chamador: atrasos assumidos não recuperam vintages reais de divulgação.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd


def _datas(valores):
    return pd.to_datetime(valores, errors="coerce", utc=True).tz_convert(None)


def _resumo(curvas: pd.DataFrame, base_inicial: float | None = None) -> dict:
    resultados = {}
    if curvas.empty:
        return resultados
    anos = (curvas.index[-1] - curvas.index[0]).total_seconds() / (365.25 * 86400)
    meses = (curvas.index[-1].year - curvas.index[0].year) * 12 + curvas.index[-1].month - curvas.index[0].month
    for coluna in curvas:
        valores = curvas[coluna]
        base = base_inicial if base_inicial is not None and coluna == "estrategia" else float(valores.iloc[0])
        retorno = float(valores.iloc[-1] / base - 1)
        cagr = float((1 + retorno) ** (1 / anos) - 1) if anos > 0 and retorno > -1 else None
        diario = valores.pct_change(fill_method=None).dropna()
        resultados[coluna] = {"retorno_total": retorno, "cagr": cagr,
            "drawdown_max": float((valores / valores.cummax().clip(lower=base) - 1).min()),
            "vol_anual": float(diario.std(ddof=1) * np.sqrt(252)) if len(diario) > 1 else None,
            "meses": meses}
    return resultados


def simular_rotacao(precos: pd.DataFrame, sinais: pd.DataFrame,
    pesos_por_quadrante: dict, benchmark, custo_bps: float = 10,
    inicio=None, fim=None, fracao_avaliacao: float = .33
) -> dict:
    """Pesos long-only somam1; rebalanceia no fechamento do primeiro pregão mensal.

    Apenas sinais confirmados estritamente disponíveis ANTES da execução podem
    definir pesos. Retorno do pregão de rebalanceamento pertence à carteira antiga.
    Turnover soma compras e vendas; custo é bps por notional negociado, inclusive
    primeira entrada. Posições derivam entre rebalanceamentos. Nenhum gap é zerado.

    A última fração é avaliação retrospectiva reservada, SEM otimização automática
    nem alegação de validação verdadeiramente fora da amostra/point-in-time.
    """
    metodologia = {"tipo": "simulacao_retrospectiva", "point_in_time": False,
        "vintage": "precos ajustados atuais; disponibilidade de sinal fornecida pelo chamador",
        "execucao": "fechamento_primeiro_pregao_mensal_apos_disponibilidade",
        "turnover": "soma absoluta pesos alvo menos pesos que derivaram; compras mais vendas",
        "custos": "bps por notional negociado; primeira entrada incluída",
        "custo_bps": custo_bps, "mesma_moeda_obrigatoria": True,
        "preenchimento_gaps": False,
        "calendario": "datas observadas de preço; ausência de todos os ativos é indistinguível de feriado sem calendário oficial",
        "avaliacao": "periodo final reservado retrospectivo; nao OOS comprovado",
        "limitacoes": "sem tributos, slippage adicional, liquidez ou risco de execução intradiária"}
    resultado = {"ok": False, "motivo": "", "avisos": [], "curvas": pd.DataFrame(),
        "retornos": pd.DataFrame(), "rebalanceamentos": pd.DataFrame(),
        "resumo": {}, "avaliacao": {}, "cobertura": pd.DataFrame(), "metodologia": metodologia}
    def falhar(motivo):
        resultado["motivo"] = motivo
        return resultado
    try:
        custo = float(custo_bps) / 10000
        fracao = float(fracao_avaliacao)
        if not math.isfinite(custo) or not 0 <= custo < .1 or not 0 < fracao < 1:
            return falhar("Custos e fração de avaliação inválidos.")
        if precos is None or precos.empty or sinais is None or sinais.empty:
            return falhar("São necessários preços e sinais confirmados.")
        if not isinstance(pesos_por_quadrante, dict) or not pesos_por_quadrante:
            return falhar("Configure pesos por quadrante.")
        for pesos in pesos_por_quadrante.values():
            if not isinstance(pesos, dict) or any(not math.isfinite(float(p)) or float(p) < 0 for p in pesos.values()):
                return falhar("Todos os pesos devem ser finitos e não negativos.")
        ativos = sorted({ativo for pesos in pesos_por_quadrante.values() for ativo, peso in pesos.items() if float(peso) > 0})
        if not ativos:
            return falhar("O modelo não possui posições positivas.")
        modelos = {}
        for quadrante, pesos in pesos_por_quadrante.items():
            arr = pd.Series({a: float(pesos.get(a, 0)) for a in ativos}, dtype=float)
            if not np.isfinite(arr).all() or (arr < 0).any() or not np.isclose(arr.sum(), 1., atol=1e-8):
                return falhar(f"Pesos de {quadrante} devem ser não negativos e somar 100%.")
            modelos[str(quadrante)] = arr
        px = precos.copy()
        px.index = _datas(px.index)
        px = px.loc[px.index.notna()].sort_index()
        nome_bench = str(benchmark) if isinstance(benchmark, str) else "__benchmark__"
        if isinstance(benchmark, pd.Series):
            bench = benchmark.copy()
            bench.index = _datas(bench.index)
            px[nome_bench] = bench.reindex(px.index)
        faltantes = [a for a in ativos + [nome_bench] if a not in px]
        if faltantes:
            return falhar("Preços ausentes: " + ", ".join(faltantes))
        px = px[list(dict.fromkeys(ativos + [nome_bench]))].apply(pd.to_numeric, errors="coerce")
        if px.index.has_duplicates:
            duplicadas = px.loc[px.index.duplicated(keep=False)]
            if duplicadas.groupby(level=0).nunique(dropna=False).gt(1).any().any():
                return falhar("Há preços conflitantes para a mesma data; revise a origem dos dados.")
            px = px.loc[~px.index.duplicated(keep="last")]
        calendario_observado = px.notna().any(axis=1)
        px = px.replace([np.inf, -np.inf], np.nan).where(px > 0)
        # Datas totalmente vazias não são inferidas como pregões; valores inválidos
        # (zero/negativo/infinito) preservam sua linha para disparar falha de cobertura.
        px = px.loc[calendario_observado]
        if inicio is not None:
            px = px.loc[px.index >= pd.Timestamp(inicio).tz_localize(None)]
        if fim is not None:
            px = px.loc[px.index <= pd.Timestamp(fim).tz_localize(None)]
        sig = sinais.copy()
        for alvo, opcoes in (("referencia_em", ["referencia_em", "referencia"]),
                             ("disponivel_em", ["disponivel_em", "disponivel"])):
            coluna = next((c for c in opcoes if c in sig), None)
            if coluna is None:
                return falhar("Sinais precisam de referencia_em e disponivel_em.")
            sig[alvo] = pd.to_datetime(sig[coluna], errors="coerce", utc=True).dt.tz_convert(None)
        if "quadrante" not in sig or "confirmado" not in sig:
            return falhar("Sinais precisam de quadrante e confirmado.")
        sig = sig.loc[sig["confirmado"].map(lambda v: isinstance(v, (bool, np.bool_)) and bool(v))]
        sig = sig.dropna(subset=["referencia_em", "disponivel_em"])
        if (sig["disponivel_em"] < sig["referencia_em"]).any():
            return falhar("Disponibilidade anterior à referência: calendário inválido.")
        sig = sig.loc[sig["quadrante"].astype(str).isin(modelos)].sort_values(["disponivel_em", "referencia_em"])
        if sig.empty or px.empty:
            return falhar("Não há sinais confirmados disponíveis para o modelo.")
        primeiras = px.groupby(px.index.to_period("M")).head(1).index
        agenda = {}
        for data in primeiras:
            conhecidos = sig.loc[sig["disponivel_em"] < data]
            if not conhecidos.empty:
                agenda[data] = conhecidos.iloc[-1]
        if not agenda:
            return falhar("Nenhum primeiro pregão mensal ocorre após a disponibilidade dos sinais.")
        entrada = next(iter(agenda))
        px = px.loc[entrada:]
        cobertura = []
        for ativo in px:
            validos = px[ativo].dropna()
            cobertura.append({"ticker": ativo, "observacoes": len(validos), "esperado": len(px),
                "cobertura": len(validos) / len(px), "inicio": validos.index.min() if len(validos) else None,
                "fim": validos.index.max() if len(validos) else None})
        resultado["cobertura"] = pd.DataFrame(cobertura)
        if px.isna().any().any():
            return falhar("Há lacunas de preço no período. Reduza a janela ou escolha proxies com cobertura completa.")
        if px.index[-1] < entrada + pd.DateOffset(months=24):
            return falhar("O laboratório exige pelo menos 24 meses após a primeira execução causal.")
        unidades = pd.Series(0., index=ativos)
        nav, rebals, valores = 1., [], []
        for data, linha in px.iterrows():
            cotacoes = linha[ativos]
            if unidades.sum() > 0:
                nav = float((unidades * cotacoes).sum())
            if data in agenda:
                sinal = agenda[data]
                alvo = modelos[str(sinal["quadrante"])]
                antigos = unidades * cotacoes / nav
                turnover = float((alvo - antigos).abs().sum())
                custo_fracao = turnover * custo
                custo_valor = nav * custo_fracao
                nav -= custo_valor
                unidades = alvo * nav / cotacoes
                rebal = {"data": data, "sinal_referencia": sinal["referencia_em"],
                    "sinal_disponivel": sinal["disponivel_em"], "quadrante": sinal["quadrante"],
                    "turnover": turnover, "custo_fracao": custo_fracao, "custo_valor": custo_valor}
                rebal.update({f"peso_{a}": float(alvo[a]) for a in ativos})
                rebals.append(rebal)
            valores.append(nav)
        curvas = pd.DataFrame({"estrategia": valores,
            "benchmark": px[nome_bench] / px[nome_bench].iloc[0]}, index=px.index)
        # Inclui primeira taxa de entrada no retorno total, sem inventar preço pré-entrada.
        resumo = _resumo(curvas, base_inicial=1.)
        corte = curvas.index[max(1, min(len(curvas) - 2, int(len(curvas) * (1 - fracao))))]
        resultado.update({"ok": True, "motivo": "", "curvas": curvas,
            "retornos": curvas.pct_change(fill_method=None), "rebalanceamentos": pd.DataFrame(rebals),
            "resumo": resumo, "avaliacao": {"corte": corte, "fracao": fracao,
                "construcao": _resumo(curvas.loc[:corte], base_inicial=1.), "reservado": _resumo(curvas.loc[corte:])}})
        resultado["retornos"].iloc[0] = [float(curvas["estrategia"].iloc[0] - 1), 0.]
        resultado["avisos"].append("Estudo retrospectivo: preços ajustados e sinais podem incorporar revisões. Reserve o período final antes de definir pesos.")
        return resultado
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return falhar("Entradas inválidas: " + type(exc).__name__)
