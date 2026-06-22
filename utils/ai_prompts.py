"""
utils/ai_prompts.py
Builders centralizados de prompt para análises de IA.

Filosofia:
  - Dados ricos do terminal (health breakdown, valuation histórico, Piotroski,
    ROIC vs WACC, ND/EBITDA, fatores macro) são empilhados no prompt em ordem
    cache-friendly (estático → semi-estático → volátil).
  - System prompts referenciam explicitamente nosso framework quantitativo.
  - Instruções finais forçam ancoragem numérica ("use os dados acima, não invente").

Ordem cache-hit DeepSeek:
  1. system (fixo)
  2. identidade (estático)
  3. fundamentos / histórico (estático)
  4. health breakdown (semi-estático)
  5. macro (semi-estático)
  6. peers (semi-estático)
  7. técnico / performance (volátil)
  8. preço atual / data (volátil)
"""
from __future__ import annotations
from typing import Any


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPTS — referenciam o framework quantitativo do terminal
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_ANALISTA_V2 = (
    "você é um analista fundamentalista sênior com background em equity research "
    "de banco de investimento. domina o framework quantitativo: ROIC vs WACC "
    "(custo de capital ajustado por Selic/Treasury via Fisher), Piotroski F-Score, "
    "Net Debt/EBITDA, cobertura de juros (ICR), crescimento YoY de receita e lucro, "
    "valuation por múltiplos em contexto histórico (percentil 5 anos). "
    "regras invioláveis: "
    "1) sempre ancora afirmações nos números fornecidos — não inventa dados; "
    "2) quantifica gaps de valuation (ex.: 'p/l 8x vs média histórica 12x → desconto 33%'); "
    "3) menciona o custo de capital ao discutir ROIC ('ROIC 18% vs WACC 17% → cria valor marginal'); "
    "4) traduz alertas do motor quantitativo em implicação prática; "
    "5) escreve em português do brasil, frases iniciando em letra minúscula, sem emojis, "
    "sem negrito ou markdown excessivo, tópicos curtos e objetivos."
)

SYSTEM_PORTFOLIO_V2 = (
    "você é um gestor de portfólio quantitativo de family office, com expertise em "
    "atribuição de performance (Brinson), risk parity, VaR e exposição a fatores "
    "(Fama-French, beta setorial). avalia carteiras pela ótica de risco ajustado: "
    "sharpe, sortino, calmar, drawdown máximo, concentração herfindahl, exposição "
    "cambial e a juros. regras: "
    "1) recomendações sempre acionáveis — ticker, direção, magnitude (ex.: 'reduzir "
    "PETR4 de 12% para 8%, alocar em IVVB11 para reduzir beta brasileiro'); "
    "2) referencia números da carteira ('seu sharpe 0.45 vs Ibov 0.31 → alpha real'); "
    "3) considera contexto macro ao sugerir ajustes (regime de juros, vix, fx); "
    "4) identifica viés comportamental quando aplicável (averção a perda, ancoragem, etc.); "
    "5) escreve em português do brasil, minúsculas, sem emojis, tópicos curtos e diretos."
)

SYSTEM_TESE_V2 = (
    "você é um analista sell-side sênior elaborando teses de investimento de qualidade "
    "institucional. estrutura padrão: (1) contexto do negócio e moat competitivo; "
    "(2) drivers de valor com magnitude esperada; (3) riscos com probabilidade e impacto; "
    "(4) valuation por múltiplos (vs peers + percentil histórico) e DCF reverso quando aplicável; "
    "(5) veredicto direcional (comprar/manter/evitar) com alvo de preço e horizonte. "
    "regras: "
    "1) toda afirmação ancorada em dado fornecido; "
    "2) quantifica drivers ('cada 1pp de margem ebitda = r$ X em valor'); "
    "3) compara múltiplos com peers e história ('p/l 15x = percentil 70 = caro'); "
    "4) menciona ROIC vs WACC ao discutir alocação de capital; "
    "5) escreve em português do brasil, minúsculas, sem emojis, sem markdown excessivo."
)

SYSTEM_MACRO_V2 = (
    "você é um estrategista macro de hedge fund global especializado em mercados "
    "emergentes e EUA. interpreta dados — curva de juros, inflação corrente e esperada, "
    "câmbio (real vs DXY), spreads de crédito (HY), commodities, vix — e traduz em "
    "implicações para alocação. domina os regimes brasileiros (juros altos comprime "
    "múltiplos, beneficia banco e penaliza varejo/construção; selic real >5% atrai "
    "renda fixa e pressiona ações; câmbio depreciado beneficia exportadoras). "
    "regras: "
    "1) referencia números fornecidos com interpretação (selic real 9.3% via Fisher); "
    "2) identifica regime e implicações por setor; "
    "3) menciona o que está precificado e o que é surpresa; "
    "4) sugere posicionamento concreto (overweight/underweight setor); "
    "5) minúsculas, sem emojis, direto."
)


# ══════════════════════════════════════════════════════════════════════════════
# BUILDERS DE CONTEXTO — blocos reutilizáveis
# ══════════════════════════════════════════════════════════════════════════════

def _safe_get(d: dict, k: str, default=None):
    if not isinstance(d, dict):
        return default
    return d.get(k, default)


def _fmt_pct(v, dec=1):
    try:
        return f"{float(v):.{dec}f}%"
    except (TypeError, ValueError):
        return "n/d"


def _fmt_num(v, dec=2):
    try:
        return f"{float(v):.{dec}f}"
    except (TypeError, ValueError):
        return "n/d"


def bloco_identidade(ticker: str, nome: str, setor: str, mercado: str) -> str:
    _tipo = "fii" if "11.SA" in ticker else ("acao br" if ticker.endswith(".SA") else "acao us")
    return (
        f"ativo: {ticker.upper()}\n"
        f"nome: {nome or 'n/d'}\n"
        f"setor: {setor or 'n/d'}\n"
        f"mercado: {mercado}\n"
        f"tipo: {_tipo}\n"
    )


def bloco_fundamentos_atuais(fund: dict) -> str:
    """Snapshot de múltiplos e qualidade dos dados."""
    fund = fund or {}
    return (
        "\nfundamentos atuais:\n"
        f"p/l: {fund.get('p/l', 'n/d')}\n"
        f"p/vp: {fund.get('p/vp', 'n/d')}\n"
        f"roe: {_fmt_pct(fund.get('roe%'))}\n"
        f"roa: {_fmt_pct(fund.get('roa%'))}\n"
        f"dividend yield: {_fmt_pct(fund.get('dy%'))}\n"
        f"margem líquida: {_fmt_pct(fund.get('margem%'))}\n"
        f"margem ebitda: {_fmt_pct(fund.get('margem_ebitda%'))}\n"
        f"ev/ebitda: {fund.get('ev/ebitda', 'n/d')}\n"
        f"liquidez corrente: {_fmt_num(fund.get('liquidez_corrente'))}\n"
        f"qualidade dos dados: {fund.get('qualidade_dados', 0)}%\n"
    )


def bloco_valuation_historico(multiplos: dict) -> str:
    """
    Múltiplos em contexto de 5–10 anos via FMP/yfinance.
    Mostra atual, média, percentil e sinal (caro/justo/barato).
    """
    if not multiplos:
        return ""

    def _fmt_stats(stats, sufixo="x"):
        if not stats:
            return "sem dados históricos"
        atual = stats.get("atual")
        media = stats.get("media")
        minv  = stats.get("min")
        maxv  = stats.get("max")
        if atual is None or media is None:
            return "sem dados históricos"
        banda = (maxv - minv) if maxv and minv and maxv != minv else 1.0
        pct = int(max(0, min(100, (atual - minv) / banda * 100))) if banda else 50
        desvio = (atual - media) / media * 100 if media != 0 else 0
        sinal = "caro" if desvio > 20 else ("barato" if desvio < -15 else "justo")
        return (
            f"atual {atual:.1f}{sufixo} | média 5a {media:.1f}{sufixo} | "
            f"percentil histórico {pct}% | sinal: {sinal} ({desvio:+.0f}% vs média)"
        )

    linhas = []
    for chave, label, suf in [
        ("pe", "p/l", "x"),
        ("pb", "p/vp", "x"),
        ("ev_ebitda", "ev/ebitda", "x"),
        ("dy", "dividend yield", "%"),
        ("roe", "roe histórico", "%"),
    ]:
        if multiplos.get(chave):
            linhas.append(f"{label}: {_fmt_stats(multiplos[chave], sufixo=suf)}")

    if not linhas:
        return ""
    return "\nvaluation em contexto histórico (5–10 anos):\n" + "\n".join(linhas) + "\n"


def bloco_health_score(health_result: dict, ticker: str = "") -> str:
    """
    Health score com breakdown completo: ROIC vs WACC, Piotroski, ND/EBITDA,
    ICR, crescimento YoY. Inclui alertas do motor quantitativo.
    """
    if not isinstance(health_result, dict):
        return ""

    score = health_result.get("score", 50)
    status = health_result.get("status", "n/d")
    breakdown = health_result.get("breakdown", {}) or {}
    alertas = health_result.get("alertas", []) or []

    # Separa pontuações (números) de métricas (strings descritivas)
    pontos_lines = []
    info_lines = []
    for k, v in breakdown.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            pontos_lines.append(f"- {k}: {v:+.1f}pts")
        else:
            info_lines.append(f"- {k}: {v}")

    txt = (
        f"\nhealth score (motor quantitativo proprietário): {score}/100 — {status}\n"
        f"\nbreakdown de pontuação:\n" + "\n".join(pontos_lines[:12]) + "\n"
    )
    if info_lines:
        txt += "\nmétricas calculadas:\n" + "\n".join(info_lines[:10]) + "\n"
    if alertas:
        txt += "\nalertas do motor quantitativo:\n" + "\n".join(
            f"- {a}" for a in alertas[:8]
        ) + "\n"
    return txt


def bloco_tecnico(
    rsi=None,
    dist_topo_52w=None,
    acima_mm50=None,
    acima_mm200=None,
    ret_1m=None,
    ret_3m=None,
    ret_6m=None,
    ret_1y=None,
    vol_anual=None,
) -> str:
    """Indicadores técnicos e performance recente."""
    linhas = []
    if rsi is not None:
        try:
            _v = float(rsi)
            _interp = "sobrevenda" if _v < 30 else ("sobrecompra" if _v > 70 else "neutro")
            linhas.append(f"rsi 14d: {_v:.0f} ({_interp})")
        except (TypeError, ValueError):
            pass
    if dist_topo_52w is not None:
        try:
            linhas.append(f"distância do topo 52 semanas: {float(dist_topo_52w):+.1f}%")
        except (TypeError, ValueError):
            pass
    if acima_mm50 is not None:
        linhas.append(f"acima da média móvel 50d: {'sim' if acima_mm50 else 'não'}")
    if acima_mm200 is not None:
        linhas.append(f"acima da média móvel 200d: {'sim' if acima_mm200 else 'não'}")

    perf = []
    for label, v in [("1m", ret_1m), ("3m", ret_3m), ("6m", ret_6m), ("1y", ret_1y)]:
        if v is not None:
            try:
                perf.append(f"{label} {float(v):+.1f}%")
            except (TypeError, ValueError):
                pass
    if perf:
        linhas.append("retornos acumulados: " + " | ".join(perf))

    if vol_anual is not None:
        try:
            linhas.append(f"volatilidade anualizada: {float(vol_anual):.1f}%")
        except (TypeError, ValueError):
            pass

    if not linhas:
        return ""
    return "\nindicadores técnicos e performance:\n" + "\n".join(linhas) + "\n"


def bloco_peers(peer_data: list, ticker_alvo: str) -> str:
    """Comparação com peers do setor."""
    if not peer_data:
        return ""
    linhas = []
    for p in peer_data[:6]:
        tk = p.get("ticker", "")
        marker = " (este)" if tk == ticker_alvo else ""
        linhas.append(
            f"- {tk}{marker} | p/l {p.get('p/l', 'n/d')} | p/vp {p.get('p/vp', 'n/d')} "
            f"| roe {p.get('roe%', 'n/d')} | dy {p.get('dy%', 'n/d')} "
            f"| margem {p.get('mrg_liq%', 'n/d')} | health {p.get('health', 'n/d')}"
        )
    return "\ncomparação com peers do setor:\n" + "\n".join(linhas) + "\n"


def bloco_dividendos(div_stats: dict) -> str:
    """
    Estatísticas de dividendos: yield projetado, crescimento, consistência.
    div_stats: {'dy_projetado_12m': X, 'total_12m': Y, 'crescimento_5a': Z, 'n_pagamentos_12m': N}
    """
    if not div_stats:
        return ""
    linhas = []
    if div_stats.get("dy_projetado_12m") is not None:
        linhas.append(f"dy projetado 12m: {_fmt_pct(div_stats['dy_projetado_12m'])}")
    if div_stats.get("total_12m") is not None:
        linhas.append(f"total pago últimos 12m: r$ {div_stats['total_12m']:.2f}/cota")
    if div_stats.get("crescimento_5a") is not None:
        linhas.append(f"crescimento médio anual 5a: {_fmt_pct(div_stats['crescimento_5a'])}")
    if div_stats.get("n_pagamentos_12m") is not None:
        linhas.append(f"pagamentos em 12m: {div_stats['n_pagamentos_12m']}")
    if not linhas:
        return ""
    return "\nhistórico de dividendos:\n" + "\n".join(linhas) + "\n"


def bloco_macro(macro_context: dict, impacto_setor: dict = None) -> str:
    """Contexto macro com Fisher (selic real) e impacto setorial."""
    if not macro_context:
        return ""
    selic = macro_context.get("selic", 10.75)
    ipca = macro_context.get("ipca", 4.5)
    vix = macro_context.get("vix", 15.0)
    label = macro_context.get("label", "neutro")

    # Selic real via Fisher: (1+selic) / (1+ipca) - 1
    try:
        selic_real = ((1 + float(selic) / 100) / (1 + float(ipca) / 100) - 1) * 100
        selic_real_txt = f"selic real (fisher): {selic_real:.1f}%\n"
    except (TypeError, ValueError, ZeroDivisionError):
        selic_real_txt = ""

    txt = (
        f"\ncontexto macro (regime brasileiro):\n"
        f"selic nominal: {selic:.2f}%\n"
        f"ipca 12m: {ipca:.1f}%\n"
        f"{selic_real_txt}"
        f"vix (eua): {vix:.1f}\n"
        f"regime classificado: {label}\n"
    )
    if isinstance(impacto_setor, dict) and impacto_setor:
        txt += (
            f"impacto do regime no setor do ativo: {impacto_setor.get('impacto', 'neutro')}\n"
            f"justificativa: {impacto_setor.get('justificativa', 'n/d')}\n"
        )
    return txt


def bloco_volatil(preco_atual: float, var_1d: float, moeda: str = "r$") -> str:
    """SEMPRE último — dados que mudam a cada tick."""
    return (
        f"\ncotação atual: {moeda} {preco_atual:,.2f}\n"
        f"variação hoje: {var_1d:+.2f}%\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
# BUILDERS DE PROMPT COMPLETOS
# ══════════════════════════════════════════════════════════════════════════════

def build_research_prompt(
    ticker: str,
    nome: str,
    setor: str,
    mercado: str,
    fundamentos: dict,
    health_result: dict,
    macro_context: dict,
    preco_atual: float,
    var_1d: float = 0.0,
    multiplos_historicos: dict = None,
    impacto_setor: dict = None,
    peer_data: list = None,
    tecnico: dict = None,
    dividendos: dict = None,
) -> str:
    """
    Prompt institucional para análise de ativo único.
    Aproveita todos os dados ricos do terminal: health breakdown,
    valuation histórico, peers, técnico, dividendos, macro.
    """
    moeda = "r$" if ticker.endswith(".SA") else "us$"
    tec = tecnico or {}

    prompt = (
        bloco_identidade(ticker, nome, setor, mercado)
        + bloco_fundamentos_atuais(fundamentos)
        + bloco_valuation_historico(multiplos_historicos)
        + bloco_health_score(health_result, ticker)
        + bloco_peers(peer_data, ticker)
        + bloco_dividendos(dividendos)
        + bloco_tecnico(
            rsi=tec.get("rsi"),
            dist_topo_52w=tec.get("dist_topo_52w"),
            acima_mm50=tec.get("acima_mm50"),
            acima_mm200=tec.get("acima_mm200"),
            ret_1m=tec.get("ret_1m"),
            ret_3m=tec.get("ret_3m"),
            ret_6m=tec.get("ret_6m"),
            ret_1y=tec.get("ret_1y"),
            vol_anual=tec.get("vol_anual"),
        )
        + bloco_macro(macro_context, impacto_setor)
        + bloco_volatil(preco_atual, var_1d, moeda)
    )

    instrucao = (
        "\n\nentregue análise institucional com a estrutura abaixo. "
        "use exclusivamente os dados acima — não invente números. "
        "quando referenciar uma métrica, cite o número específico.\n\n"
        "1. tese central (2 linhas): "
        "argumento principal de bull/bear, ancorado em ROIC vs WACC, "
        "valuation histórico e regime macro.\n\n"
        "2. pontos positivos (3 bullets quantificados): "
        "o que está funcionando — cite o número e o contexto "
        "(ex.: 'ROIC 18% vs WACC 17% gera valor', 'p/l percentil 25 = barato').\n\n"
        "3. riscos principais (3 bullets quantificados): "
        "o que pode destruir a tese — cite alertas do motor quando aplicável "
        "(ex.: 'ND/EBITDA 4.2x = alavancagem crítica', 'lucro caindo 30% YoY').\n\n"
        "4. valuation: "
        "(a) interprete múltiplo principal vs percentil histórico de 5 anos; "
        "(b) compare com peers do setor citados acima; "
        "(c) quantifique gap em percentual.\n\n"
        "5. impacto macro (2 bullets): "
        "como selic real (Fisher), vix e regime atual afetam ESPECIFICAMENTE "
        "este ativo. cite impacto setorial fornecido se houver.\n\n"
        "6. veredicto direcional: "
        "comprar / manter / evitar — com horizonte (6m / 12m / 24m) e "
        "qual gatilho monitorar para mudar a tese.\n\n"
        "7. métrica-chave para monitorar (1 linha): "
        "número específico + frequência (ex.: 'ROE trimestral > 15%')."
    )
    return prompt + instrucao


def build_discovery_prompt(
    top_ativos: list,
    modo: str,
    universo: str,
    macro_context: dict,
) -> str:
    """
    Prompt de análise qualitativa do top X do screener Discovery.
    Espera top_ativos com payload rico (não só números — health breakdown,
    multiples, ROIC, setor).
    """
    modo_desc = {
        "entrada":    "melhor ponto de entrada (timing)",
        "dividendo":  "renda recorrente via dividendos",
        "realizacao": "possível realização parcial de posição",
    }.get(modo, modo)

    linhas = []
    for i, a in enumerate(top_ativos[:5], 1):
        linhas.append(
            f"\n#{i} — {a.get('ticker', 'n/d')} ({a.get('nome', '')[:25]})\n"
            f"  mercado: {a.get('mercado', 'n/d')} | setor: {a.get('setor', 'n/d')}\n"
            f"  score discovery: {a.get('score', 0):.0f}/100 "
            f"(qualidade {a.get('q_score', 0):.0f}, valuation {a.get('v_score', 0):.0f}, "
            f"timing {a.get('t_score', 0):.0f})\n"
            f"  health score (motor): {a.get('health_score', 'n/d')}\n"
            f"  fundamentos: p/l {a.get('pl', 'n/d')} | p/vp {a.get('pvp', 'n/d')} "
            f"| roe {a.get('roe', 'n/d')} | dy {a.get('dy', 'n/d')} | margem {a.get('margem', 'n/d')}\n"
            f"  técnico: rsi {a.get('rsi', 'n/d')} | ret 5d {a.get('ret_5d', 0):+.1f}% "
            f"| ret 3m {a.get('ret_3m', 0):+.1f}% | dist topo 52w {a.get('dist_top', 0):.0f}%\n"
            f"  alertas: {a.get('alertas_curtos', 'nenhum')}"
        )

    macro_block = bloco_macro(macro_context)

    prompt = (
        f"análise comparativa — discovery screener\n"
        f"modo: {modo_desc}\n"
        f"universo: {universo}\n"
        f"{macro_block}\n"
        f"top {len(top_ativos)} ativos por score quantitativo:\n"
        + "\n".join(linhas)
        + "\n\nresponda em 6 tópicos diretos. minúsculas. ancore tudo em dados acima.\n"
        "1. ranking de tese: ordene os 5 ativos pela qualidade da tese "
        "no regime macro atual — justifique cada posição.\n"
        "2. melhor risco/retorno no modo escolhido: qual ativo entrega "
        f"mais valor para o modo '{modo_desc}'? quantifique a vantagem.\n"
        "3. risco oculto: para cada ativo, identifique um risco que o "
        "score quantitativo PODE estar subestimando "
        "(setorial, governança, ciclo, balanço escondido).\n"
        "4. impacto macro setorial: como o regime atual "
        f"({macro_context.get('label', 'n/d')}, selic {macro_context.get('selic', 0):.2f}%) "
        "afeta diferencialmente cada setor representado.\n"
        "5. estratégia de entrada: para o top 3, sugira faixas de preço "
        "para entrada (suporte técnico se sobreCOMPRADO, atual se em "
        "região neutra de rsi).\n"
        "6. escolha única: se for forçado a escolher 1, qual e por quê? "
        "tese de 12 meses com 3 catalisadores e 3 gatilhos de saída."
    )
    return prompt


def build_portfolio_performance_prompt(
    metricas: dict,
    posicoes_top: list,
    setor_concentracao: dict,
    fx_exposicao: dict,
    periodo: str,
    macro_context: dict,
    alpha_cdi: float,
    alpha_ibov: float,
) -> str:
    """Prompt rico para análise de performance da carteira."""
    met_txt = "\n".join([
        f"- {nm}: ret {mv.get('retorno', 0):+.2f}% | "
        f"vol {mv.get('vol', 0):.2f}% | sharpe {mv.get('sharpe', 0):.2f} | "
        f"drawdown {mv.get('drawdown', 0):.2f}%"
        for nm, mv in (metricas or {}).items()
    ])

    top_txt = ""
    if posicoes_top:
        top_txt = "\n\ntop posições (peso, p&l, health):\n" + "\n".join(
            f"- {p.get('ticker', '')}: peso {p.get('peso_pct', 0):.1f}% | "
            f"p&l {p.get('pnl_pct', 0):+.1f}% | health {p.get('health_score', 'n/d')}"
            for p in posicoes_top[:10]
        )

    setor_txt = ""
    if setor_concentracao:
        setor_txt = "\n\nconcentração setorial:\n" + "\n".join(
            f"- {s}: {p:.1f}%" for s, p in sorted(
                setor_concentracao.items(), key=lambda x: -x[1]
            )[:8]
        )

    fx_txt = ""
    if fx_exposicao:
        fx_txt = (
            f"\n\nexposição cambial:\n"
            f"- brasil (brl): {fx_exposicao.get('br', 0):.1f}%\n"
            f"- eua (usd): {fx_exposicao.get('us', 0):.1f}%"
        )

    return (
        f"análise de performance da carteira\n"
        f"período: {periodo}\n"
        + bloco_macro(macro_context) +
        f"\nmétricas vs benchmarks:\n{met_txt}\n"
        f"alpha vs cdi: {alpha_cdi:+.2f}pp\n"
        f"alpha vs ibovespa: {alpha_ibov:+.2f}pp\n"
        f"{top_txt}{setor_txt}{fx_txt}\n\n"
        "responda em 6 tópicos. minúsculas. quantifique tudo.\n"
        "1. alpha real? compare retorno absoluto com cdi e ibov no período. "
        "atribua o alpha a (alocação setorial, seleção de ativos, beta).\n"
        "2. eficiência: sharpe vs benchmarks indica risco bem remunerado? "
        "cite os números e compare.\n"
        "3. risco: drawdown máximo está adequado para perfil retorno-alvo? "
        "qual o pior cenário (var implícito)?\n"
        "4. concentração: identifique riscos de concentração (setor único > 30%, "
        "posição única > 15%, fx desbalanceado).\n"
        "5. ajuste para o regime macro atual: que rebalanceamento concreto "
        "(reduzir X de A% para B%, aumentar Y) melhoraria risco/retorno?\n"
        "6. 3 ações práticas imediatas: comprar / vender / manter — com "
        "ticker e magnitude."
    )


def build_portfolio_context_v2(
    posicoes_enriched: list,
    metricas: dict,
    macro: dict,
    setor_concentracao: dict = None,
    fx_exposicao: dict = None,
    dy_carteira: float = None,
    health_medio: float = None,
    exposicao_macro: dict = None,
) -> str:
    """
    Contexto rico para chat de portfolio.
    Substitui o contexto simples de listagem por uma visão executiva
    com concentração, FX, DY projetado e health médio ponderado.
    """
    linhas = ["estado atual da carteira do usuário:\n"]

    if posicoes_enriched:
        linhas.append("posições (ordenadas por peso):")
        for e in sorted(posicoes_enriched, key=lambda x: -x.get("peso_pct", 0)):
            tk = e.get("ticker", "")
            moeda = "r$" if tk.endswith(".SA") else "us$"
            hs = e.get("health_score") or e.get("hs") or "n/d"
            hs_str = f"{int(hs)}/100" if isinstance(hs, (int, float)) else str(hs)
            linhas.append(
                f"- {tk}: peso {e.get('peso_pct', 0):.1f}% | "
                f"qtd {e.get('qtd', 0):.0f} | "
                f"preço {moeda} {e.get('preco_atual', e.get('pa', 0)):,.2f} | "
                f"pm {moeda} {e.get('preco_medio', e.get('pm', 0)):,.2f} | "
                f"valor {moeda} {e.get('valor', 0):,.0f} | "
                f"p&l {e.get('pnl_pct', e.get('pnl', 0)):+.1f}% | "
                f"health {hs_str} | "
                f"setor {e.get('setor', 'n/d')}"
            )

    if metricas:
        linhas.append(
            f"\nresumo agregado:\n"
            f"- valor total (m2m): r$ {metricas.get('valor_total', 0):,.2f}\n"
            f"- custo total: r$ {metricas.get('custo_total', 0):,.2f}\n"
            f"- p&l total: {metricas.get('pnl_total_pct', 0):+.1f}%\n"
            f"- número de posições: {metricas.get('num_posicoes', 0)}"
        )

    if health_medio is not None:
        linhas.append(f"- health score médio ponderado: {health_medio:.0f}/100")
    if dy_carteira is not None:
        linhas.append(f"- dy projetado da carteira (12m): {dy_carteira:.2f}%")

    if setor_concentracao:
        linhas.append("\nconcentração setorial:")
        for s, p in sorted(setor_concentracao.items(), key=lambda x: -x[1])[:8]:
            linhas.append(f"- {s}: {p:.1f}%")

    if fx_exposicao:
        linhas.append(
            f"\nexposição cambial:\n"
            f"- brasil: {fx_exposicao.get('br', 0):.1f}%\n"
            f"- eua: {fx_exposicao.get('us', 0):.1f}%"
        )

    if macro:
        linhas.append(bloco_macro(macro))

    if exposicao_macro:
        linhas.append(
            "\nexposição macro do book (tilt regime + inflação setorial, "
            "ponderado por peso):\n"
            f"- tilt macro médio: {exposicao_macro.get('tilt_medio', 0):+.1f} "
            f"(escala −8 contra … +8 a favor)\n"
            f"- {exposicao_macro.get('leitura', '')}\n"
            f"- peso em setores favoráveis: {exposicao_macro.get('pct_favoravel', 0):.0f}% | "
            f"desfavoráveis: {exposicao_macro.get('pct_desfavoravel', 0):.0f}%\n"
            f"- exposto a duration (setores sob juro alto): "
            f"{exposicao_macro.get('duration_exposta_pct', 0):.0f}% | "
            f"com proteção inflacionária (receita indexada): "
            f"{exposicao_macro.get('inflacao_protegida_pct', 0):.0f}%"
        )

    return "\n".join(linhas)
