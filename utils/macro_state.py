"""
utils/macro_state.py
====================
Estado macro CANÔNICO — fonte única de verdade consumida por todas as páginas
e pelo motor de score.

Problema que resolve:
  O terminal tinha TRÊS motores de regime que não se conheciam e podiam se
  contradizer na mesma sessão:
    1. macro_regime.classificar_regime  → 6 estados (Selic × VIX)
    2. ciclo_economico.calcular_*        → 4 fases (leading indicators BR/US)
    3. regime_classifier.classificar_*   → 4 fases (curva/VIX/CPI/momentum)

  Aqui eles são consolidados num único objeto `MacroState`, com um campo de
  CONSENSO que sinaliza concordância/divergência entre os motores — informação
  acionável por si só ("os três concordam em contração" vs "divergem").

Contrato de unidade do IPCA (ver utils/macro_context.py):
  'ipca'/'ipca_12m' = acumulado 12m (% a.a.); 'ipca_mensal' = print do mês.

Funções públicas:
  get_macro_state(macro_context=None) -> MacroState   (rico; UI; cache 1h)
  tilt_setor(setor, macro_context=None) -> dict        (puro; usado no score)

`tilt_setor` é PURA (sem yfinance/streamlit) — funciona no ETL (GitHub Actions).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from utils.regime_classifier import valor_observado, numero_finito, ler_curva_10y_2y

from utils.st_fallback import st, ST_AVAILABLE as _ST

from utils.logger import get_logger

logger = get_logger(__name__)


# ── Fisher: selic real = (1+selic)/(1+ipca) - 1 ──────────────────────────────

def selic_real_fisher(selic: float, ipca_12m: float) -> Optional[float]:
    """Juro real ex post de Fisher; ausência nunca vira zero observado."""
    nominal, inflacao = numero_finito(selic), numero_finito(ipca_12m)
    if nominal is None or inflacao is None or inflacao <= -100:
        return None
    return ((1 + nominal / 100) / (1 + inflacao / 100) - 1) * 100


# ── Normalização de fases entre os motores ───────────────────────────────────
# regime_classifier e ciclo_economico usam o mesmo vocabulário de 4 fases:
#   expansao | pico | contracao | vale
_FASE_RISK_ON  = {"expansao", "vale"}    # janelas pró-risco/cíclico
_FASE_RISK_OFF = {"pico", "contracao"}   # janelas defensivas


# Taxonomia setorial canônica consolidada em utils/setores (era definida aqui).
# Reexportado para compat: `from utils.macro_state import normalizar_setor`.
from utils.setores import normalizar_setor, _SETOR_CANON  # noqa: F401


# ── Tilt setorial por primeiros princípios (consistente entre regimes) ───────
# Substitui as listas de vocabulário livre do macro_regime (inconsistentes entre
# os 6 estados) por uma matriz econômica determinística sobre setores canônicos.
#
# Eixo JURO (selic alta / juro real alto): comprime duration e crédito ao
# consumidor; beneficia spread bancário e exportadoras (câmbio/commodities).
_TILT_JURO_ALTO = {
    "financeiro":        +2,   # NIM/spread melhora com selic alta
    "energia":           +1,   # exportadora, ligada a câmbio/commodities
    "materiais":         +1,   # idem (mineração/siderurgia/papel)
    "consumo_defensivo": +1,   # demanda inelástica, repasse via preço
    "saude":              0,
    "comunicacao":        0,
    "tecnologia":        -1,   # duration longa sofre com desconto maior
    "utilities":         -1,   # proxy de bond, mas tarifa indexada amortece
    "industria":         -1,
    "consumo_ciclico":   -2,   # crédito caro + renda real comprimida
    "imobiliario":       -2,   # financiamento e cap rate sobem
}
# Eixo STRESS (VIX alto): flight-to-quality penaliza beta/cíclicos.
_TILT_STRESS = {
    "consumo_defensivo": +2,
    "saude":             +2,
    "utilities":         +1,
    "comunicacao":        0,
    "energia":           -1,
    "materiais":         -1,
    "imobiliario":       -1,
    "industria":         -1,
    "financeiro":        -1,   # beta elevado
    "consumo_ciclico":   -2,
    "tecnologia":        -2,
}


@dataclass
class MacroState:
    """Estado macro consolidado — uma só fonte de verdade."""
    # núcleo de valores (todos anuais onde aplicável)
    selic: Optional[float]
    ipca_12m: Optional[float]
    selic_real: Optional[float]
    vix: Optional[float]
    treasury_10y: Optional[float]
    curve_slope_10y_2y: Optional[float]   # pp — invertida (<0) = sinal recessivo

    # regime 6-estados (Selic × VIX) — macro_regime
    regime_key: str
    regime_label: str
    setores_favorecidos: list[str]
    setores_prejudicados: list[str]
    posicionamento: str
    score_ambiente: Optional[int]

    # ciclo 4-fases — regime_classifier (curva/VIX/CPI/momentum)
    fase_ciclo: str
    fase_prob: float  # alias legado de concordância; NÃO probabilidade
    fase_sinais: dict

    # ciclo 4-fases — ciclo_economico (leading indicators BR/US)
    fase_br: str
    fase_us: str
    confianca_br: int
    confianca_us: int

    # consenso entre os motores de fase
    consenso: str          # "alinhado_risk_on" | "alinhado_risk_off" | "divergente"
    consenso_nota: str

    fonte: dict = field(default_factory=dict)
    fase_concordancia: float = 0.0
    fase_intensidade_stress: float = 0.0
    fase_cobertura: float = 0.0
    fase_sinais_validos: int = 0
    selic_real_ex_ante_proxy: Optional[float] = None
    qualidade: dict = field(default_factory=dict)


def _consolidar_consenso(fase_ciclo: str, fase_br: str, fase_us: str) -> tuple[str, str]:
    """Compara apenas fases determinadas, sem tratar motores como independentes."""
    fases = [f for f in (fase_ciclo, fase_br, fase_us) if f in _FASE_RISK_ON | _FASE_RISK_OFF]
    total = len(fases)
    if total < 2:
        return "indefinido", f"Cobertura {total}/3: insuficiente para formar consenso entre leituras."
    risk_on = sum(f in _FASE_RISK_ON for f in fases)
    if risk_on == total:
        return "alinhado_risk_on", f"{total}/3 leituras apontam sinais pró-risco; compartilham indicadores e não são confirmações independentes."
    if risk_on == 0:
        return "alinhado_risk_off", f"{total}/3 leituras apontam sinais defensivos; concordância não é probabilidade de recessão."
    return "divergente", f"{total}/3 leituras disponíveis divergem; examinar direção da atividade, inflação e condições financeiras."


@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_state(macro_context: dict | None = None) -> MacroState:
    """
    Consolida os três motores de regime num único MacroState.

    Cache 1h. Faz chamadas yfinance pesadas (regime_classifier + ciclo_economico),
    por isso é cacheada e idempotente. Para uso no score (por ticker), prefira
    `tilt_setor`, que é leve e pura.
    """
    # ── núcleo de valores ──────────────────────────────────────────────────
    if macro_context is None:
        try:
            from utils.macro_context import garantir_macro_context
            macro_context = garantir_macro_context()
        except Exception:
            macro_context = st.session_state.get("macro_context", {}) or {}

    selic = valor_observado(macro_context, "selic")
    ipca_12m = valor_observado(macro_context, "ipca_12m", "ipca")
    vix = valor_observado(macro_context, "vix")
    treasury_10y = valor_observado(macro_context, "treasury_10y")
    selic_r = selic_real_fisher(selic, ipca_12m)
    curva = ler_curva_10y_2y()
    curve_slope = curva["slope"]
    expectativa = valor_observado(macro_context, "br_focus_ipca_12m")
    if expectativa is None:
        try:
            from database.db import get_macro_cache
            expectativa = numero_finito(get_macro_cache("br_focus_ipca_12m"))
        except Exception:
            pass
    ex_ante = selic_real_fisher(selic, expectativa)
    qualidade = {nome: {"observado": valor is not None,
                        "status": "observado" if valor is not None else "ausente"}
                 for nome, valor in (("selic", selic), ("ipca_12m", ipca_12m),
                                     ("vix", vix), ("treasury_10y", treasury_10y))}
    for nome, meta in (macro_context.get("qualidade") or {}).items():
        if nome in qualidade:
            qualidade[nome].update(meta)

    qualidade["curva_10y_2y"] = {"observado": curve_slope is not None,
                                     "referencia_em": curva.get("data"),
                                     "fonte": curva.get("fonte")}

    # ── regime 6-estados (Selic × VIX) ─────────────────────────────────────
    regime = {}
    try:
        from utils.macro_regime import classificar_regime
        if all(v is not None for v in (selic, vix, ipca_12m, treasury_10y)):
            regime = classificar_regime(selic=selic, vix=vix, ipca=ipca_12m, treasury_10y=treasury_10y)
    except Exception as e:
        logger.warning(f"[macro_state] classificar_regime falhou: {e}")

    # ── ciclo 4-fases (curva/VIX/CPI/momentum) ─────────────────────────────
    fase_ciclo, fase_prob, fase_sinais = "", 0.0, {}
    fase_intensidade, fase_cobertura, fase_validos = 0.0, 0.0, 0
    try:
        from utils.regime_classifier import classificar_regime_do_macro_context
        _rc = classificar_regime_do_macro_context(macro_context)
        fase_ciclo  = _rc.fase
        fase_prob   = _rc.concordancia
        fase_intensidade = _rc.intensidade_stress
        fase_cobertura = _rc.cobertura
        fase_validos = _rc.sinais_validos
        fase_sinais = _rc.sinais
    except Exception as e:
        logger.warning(f"[macro_state] regime_classifier falhou: {e}")

    # ── ciclo BR/US (leading indicators) ───────────────────────────────────
    fase_br, fase_us, conf_br, conf_us = "", "", 0, 0
    try:
        from utils.ciclo_economico import (
            calcular_indicadores_ciclo_br, calcular_indicadores_ciclo_us,
        )
        _cb = calcular_indicadores_ciclo_br(macro_context)
        _cu = calcular_indicadores_ciclo_us(macro_context)
        fase_br = _cb.get("fase_provavel", "")
        fase_us = _cu.get("fase_provavel", "")
        conf_br = int(_cb.get("confianca", 0) or 0)
        conf_us = int(_cu.get("confianca", 0) or 0)
    except Exception as e:
        logger.warning(f"[macro_state] ciclo_economico falhou: {e}")

    consenso, consenso_nota = _consolidar_consenso(fase_ciclo, fase_br, fase_us)

    return MacroState(
        selic=round(selic, 2) if selic is not None else None,
        ipca_12m=round(ipca_12m, 2) if ipca_12m is not None else None,
        selic_real=round(selic_r, 2) if selic_r is not None else None,
        vix=round(vix, 1) if vix is not None else None,
        treasury_10y=round(treasury_10y, 2) if treasury_10y is not None else None,
        curve_slope_10y_2y=curve_slope,
        regime_key=regime.get("regime_key", "indefinido"),
        regime_label=regime.get("label", "n/d"),
        setores_favorecidos=regime.get("setores_favorecidos", []),
        setores_prejudicados=regime.get("setores_prejudicados", []),
        posicionamento=regime.get("posicionamento", ""),
        score_ambiente=int(regime["score_ambiente"]) if regime.get("score_ambiente") is not None else None,
        fase_ciclo=fase_ciclo or "indefinido",
        fase_prob=fase_prob,
        fase_sinais=fase_sinais,
        fase_br=fase_br or "indefinido",
        fase_us=fase_us or "indefinido",
        confianca_br=conf_br,
        confianca_us=conf_us,
        consenso=consenso,
        consenso_nota=consenso_nota,
        fase_concordancia=fase_prob,
        fase_intensidade_stress=fase_intensidade,
        fase_cobertura=fase_cobertura,
        fase_sinais_validos=fase_validos,
        selic_real_ex_ante_proxy=round(ex_ante, 2) if ex_ante is not None else None,
        qualidade=qualidade,
        fonte={
            "regime": "macro_regime (selic×vix)",
            "ciclo":  "regime_classifier (curva/vix/cpi/momentum)",
            "leading": "ciclo_economico (br/us)",
        },
    )


# ── tilt setorial PURO (sem yfinance/streamlit) — usado no health_engine ─────

def tilt_setor(setor: str, macro_context: dict | None = None,
               market: str = "BR") -> dict:
    """
    Avalia se o setor está favorecido/neutro/desfavorecido no regime atual,
    usando APENAS o macro_context (selic/treasury/vix) — sem chamadas de rede.

    O eixo de JURO é consciente de mercado: ações BR sofrem com a Selic
    (taxa nominal alta em termos absolutos), ações US com o Treasury 10y
    (níveis "altos" muito menores). O eixo de STRESS (VIX) é global.

    Retorna {'impacto', 'pontos', 'motivos', 'setor_canon'} onde 'pontos' é a
    contribuição base de regime para o pilar macro-setorial do score (±4). O
    componente de inflação setorial é somado em utils/inflation_sectoral.py.

    Pura e barata: chamável por ticker no ETL.
    """
    if macro_context is None:
        macro_context = st.session_state.get("macro_context", {}) or {}

    motivos: list[str] = []
    canon = normalizar_setor(setor)

    _vix = valor_observado(macro_context, "vix")
    is_us = str(market).upper() == "US"
    chave_juro = "treasury_10y" if is_us else "selic"
    juro = valor_observado(macro_context, chave_juro)
    ausentes = [nome for nome, valor in ((chave_juro, juro), ("vix", _vix)) if valor is None]
    raw = 0.0
    if juro is not None:
        if is_us:
            juro_w = 1.0 if juro >= 5.5 else (0.6 if juro >= 4.0 else 0.0)
            juro_tag = f"Treasury 10y {juro:.1f}%"
        else:
            juro_w = 1.0 if juro >= 13 else (0.7 if juro > 10 else 0.0)
            juro_tag = f"Selic {juro:.1f}%"
        raw += juro_w * _TILT_JURO_ALTO.get(canon, 0)
        if juro_w and _TILT_JURO_ALTO.get(canon):
            direcao = "favorece" if _TILT_JURO_ALTO[canon] > 0 else "pressiona"
            motivos.append(f"{juro_tag}: hipótese de transmissão que {direcao} {canon}")
    if _vix is not None and _vix > 20:
        stress = _TILT_STRESS.get(canon, 0)
        raw += stress
        if stress:
            motivos.append(f"Stress global observado (VIX {_vix:.0f}): contribuição {stress:+d}")
    if ausentes:
        motivos.append("Eixos ausentes: " + ", ".join(ausentes) + "; não preenchidos por fallback.")
    pontos = int(max(-4, min(4, round(raw))))
    impacto = "favoravel" if pontos > 0 else ("desfavoravel" if pontos < 0 else "neutro")
    return {"impacto": impacto, "pontos": pontos, "motivos": motivos, "setor_canon": canon,
            "cobertura": (2 - len(ausentes)) / 2, "ausentes": ausentes,
            "qualidade": "completa" if not ausentes else ("parcial" if len(ausentes) == 1 else "ausente")}


# ── Cockpit macro (faixa persistente — fonte única no topo das páginas) ──────

def render_cockpit_macro(market: str = "BR") -> None:
    """
    Renderiza uma faixa macro compacta — a "fonte única de verdade" para o topo
    de qualquer página. LEVE: lê do macro_context + snapshot de inflação, sem as
    chamadas yfinance pesadas de get_macro_state(). Silenciosa em falha.
    """
    if not _ST:
        return
    try:
        from utils.macro_context import garantir_macro_context
        mc = garantir_macro_context()
    except Exception:
        mc = st.session_state.get("macro_context", {}) or {}

    try:
        selic = valor_observado(mc, "selic")
        ipca = valor_observado(mc, "ipca_12m", "ipca")
        vix = valor_observado(mc, "vix")
        sreal = selic_real_fisher(selic, ipca)
        treasury = valor_observado(mc, "treasury_10y")

        # regime label (puro, sem rede)
        regime_label = "n/d"
        try:
            from utils.macro_regime import classificar_regime
            regime_label = classificar_regime(
                selic=selic, vix=vix, ipca=ipca,
                treasury_10y=treasury,
            ).get("label", "n/d") if all(v is not None for v in (selic, vix, ipca, treasury)) else "n/d"
        except Exception:
            pass

        # inflação setorial: nível 12m + momentum 3m anualizado (capta inflexão
        # que o 12m esconde). Degrada para None sem snapshot.
        nucleo = servicos = nucleo_3m = servicos_3m = None
        try:
            from utils.inflation_sectoral import get_inflacao_atual
            _skey = "servicos" if market == "BR" else "servicos_core"
            _infl  = get_inflacao_atual(market)
            _infl3 = get_inflacao_atual(market, horizonte="3m")
            servicos    = _infl.get(_skey)
            servicos_3m = _infl3.get(_skey)
            _nucs  = [v for k, v in _infl.items()  if k.startswith("nucleo")]
            _nucs3 = [v for k, v in _infl3.items() if k.startswith("nucleo")]
            if _nucs:
                nucleo = round(sum(_nucs) / len(_nucs), 2)
            elif market != "BR":
                nucleo = _infl.get("median") or _infl.get("core")
            if _nucs3:
                nucleo_3m = round(sum(_nucs3) / len(_nucs3), 2)
            elif market != "BR":
                nucleo_3m = _infl3.get("median") or _infl3.get("core")
        except Exception:
            pass

        # gap de margem (produtor − consumidor): IGP-M−IPCA (BR) / PPI−core (US).
        gap_m = None
        try:
            from utils.inflation_sectoral import gap_margem as _gap_margem
            _g = _gap_margem(market)
            if _g:
                gap_m = _g["gap"]
        except Exception:
            pass

        # surpresa de inflação: realizado − esperado (Focus BR / Michigan US).
        surp_m = None
        try:
            from utils.inflation_sectoral import surpresa_inflacao as _surp_infl
            _sp = _surp_infl(market)
            if _sp:
                surp_m = _sp["surpresa"]
        except Exception:
            pass

        # difusão da inflação (breadth): % da cesta acima da meta.
        dif_m = None
        try:
            from utils.inflation_sectoral import diffusion_inflacao as _dif
            dif_m = _dif(market)
        except Exception:
            pass

        _cor_juro = "var(--text-muted)" if selic is None else ("var(--bear)" if selic > 13 else ("var(--amber)" if selic > 10 else "var(--bull)"))
        _cor_vix = "var(--text-muted)" if vix is None else ("var(--bear)" if vix > 25 else ("var(--amber)" if vix > 20 else "var(--bull)"))

        def _kpi(lbl, val, cor="var(--text-secondary)"):
            return (
                f'<div class="ft-context-kpi">'
                f'<span style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em;">{lbl}</span>'
                f'<span style="font-size:0.86rem;font-weight:600;color:{cor};font-family:var(--font-data,monospace);">{val}</span>'
                f'</div>'
            )

        partes = [
            _kpi("regime", regime_label, "var(--accent)"),
            _kpi("selic", f"{selic:.2f}%" if selic is not None else "n/d", _cor_juro),
            _kpi("juro real ex post", f"{sreal:+.1f}%" if sreal is not None else "n/d", _cor_juro),
            _kpi("ipca 12m", f"{ipca:.1f}%" if ipca is not None else "n/d"),
        ]
        def _mom(v3, v12):
            """Seta + cor pela aceleração (3m vs 12m). Subindo = ruim p/ juro (bear)."""
            if v3 is None or v12 is None:
                return "", "var(--text-secondary)"
            if v3 > v12 + 0.2:
                return " ↑", "var(--bear)"
            if v3 < v12 - 0.2:
                return " ↓", "var(--bull)"
            return " →", "var(--amber)"

        if nucleo is not None:
            _a, _c = _mom(nucleo_3m, nucleo)
            _v = f"{nucleo:.1f}%" if nucleo_3m is None else f"{nucleo:.1f}→{nucleo_3m:.1f}%{_a}"
            partes.append(_kpi("núcleo 12m→3m", _v, _c))
        if servicos is not None:
            _a, _c = _mom(servicos_3m, servicos)
            _v = f"{servicos:.1f}%" if servicos_3m is None else f"{servicos:.1f}→{servicos_3m:.1f}%{_a}"
            partes.append(_kpi("serviços 12m→3m", _v, _c))
        if gap_m is not None:
            # gap > 0 = custo sobe mais que preço → aperta margem (bear)
            _cg = "var(--bear)" if gap_m > 0.5 else ("var(--bull)" if gap_m < -0.5 else "var(--amber)")
            partes.append(_kpi("margem prod−cons", f"{gap_m:+.1f}pp", _cg))
        if surp_m is not None:
            # Gap entre inflação passada e expectativa futura, não surpresa de divulgação.
            _cs = "var(--bear)" if surp_m > 0.3 else ("var(--bull)" if surp_m < -0.3 else "var(--amber)")
            partes.append(_kpi("realizado−expectativa", f"{surp_m:+.1f}pp", _cs))
        if dif_m is not None:
            # difusão alta = inflação ampla/disseminada (bear)
            _pa = dif_m["pct_acima_meta"]
            _cd = "var(--bear)" if _pa >= 60 else ("var(--amber)" if _pa >= 35 else "var(--bull)")
            partes.append(_kpi("difusão >meta", f"{_pa}% ({dif_m['acima']}/{dif_m['total']})", _cd))
        partes.append(_kpi("vix", f"{vix:.0f}" if vix is not None else "n/d", _cor_vix))

        primary = partes[:4] + partes[-1:]
        details = partes[4:-1]
        st.markdown('<div class="ft-macro-context">' + ''.join(primary) + '</div>', unsafe_allow_html=True)
        if details:
            with st.expander("Detalhes do contexto macro", expanded=False):
                st.markdown('<div class="ft-macro-context ft-context-details">' + ''.join(details) + '</div>', unsafe_allow_html=True)
    except Exception as e:
        logger.debug(f"[macro_state] render_cockpit_macro falhou: {e}")
