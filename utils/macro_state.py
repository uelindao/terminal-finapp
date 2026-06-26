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

from utils.st_fallback import st, ST_AVAILABLE as _ST

from utils.logger import get_logger
from utils.macro_context import (
    SELIC_FALLBACK, VIX_FALLBACK, IPCA_12M_FALLBACK, TREASURY_10Y_FALLBACK,
)

logger = get_logger(__name__)


# ── Fisher: selic real = (1+selic)/(1+ipca) - 1 ──────────────────────────────

def selic_real_fisher(selic: float, ipca_12m: float) -> float:
    """Taxa de juro real ex-post via Fisher, em % a.a. ipca_12m = anual."""
    try:
        return ((1 + float(selic) / 100) / (1 + float(ipca_12m) / 100) - 1) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


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
    selic: float
    ipca_12m: float
    selic_real: float
    vix: float
    treasury_10y: float
    curve_slope_10y_2y: Optional[float]   # pp — invertida (<0) = sinal recessivo

    # regime 6-estados (Selic × VIX) — macro_regime
    regime_key: str
    regime_label: str
    setores_favorecidos: list[str]
    setores_prejudicados: list[str]
    posicionamento: str
    score_ambiente: int

    # ciclo 4-fases — regime_classifier (curva/VIX/CPI/momentum)
    fase_ciclo: str
    fase_prob: float
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


def _consolidar_consenso(fase_ciclo: str, fase_br: str, fase_us: str) -> tuple[str, str]:
    """Compara as fases dos 3 ângulos e classifica o consenso."""
    fases = [f for f in (fase_ciclo, fase_br, fase_us) if f]
    if not fases:
        return "indefinido", "sem leitura de fase disponível."
    risk_on  = sum(1 for f in fases if f in _FASE_RISK_ON)
    risk_off = sum(1 for f in fases if f in _FASE_RISK_OFF)
    total = len(fases)
    if risk_on == total:
        return "alinhado_risk_on", (
            f"os {total} motores de ciclo apontam janela pró-risco — "
            "convicção alta para cíclicos."
        )
    if risk_off == total:
        return "alinhado_risk_off", (
            f"os {total} motores de ciclo apontam janela defensiva — "
            "convicção alta para preservação de capital."
        )
    return "divergente", (
        f"motores de ciclo divergem (risk-on {risk_on} × risk-off {risk_off}) — "
        "reduzir convicção direcional e priorizar seleção bottom-up."
    )


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

    selic        = float(macro_context.get("selic", SELIC_FALLBACK) or SELIC_FALLBACK)
    ipca_12m     = float(macro_context.get("ipca_12m") or macro_context.get("ipca", IPCA_12M_FALLBACK))
    vix          = float(macro_context.get("vix", VIX_FALLBACK) or VIX_FALLBACK)
    treasury_10y = float(macro_context.get("treasury_10y", TREASURY_10Y_FALLBACK) or TREASURY_10Y_FALLBACK)
    selic_r      = selic_real_fisher(selic, ipca_12m)

    # ── inclinação da curva US (10y-2y) — melhor leitura de ciclo global ────
    curve_slope = None
    try:
        from utils.macro_supabase import buscar_slope_curva
        _df_slope = buscar_slope_curva()
        if _df_slope is not None and not _df_slope.empty and "slope_10y_2y" in _df_slope.columns:
            _s = _df_slope["slope_10y_2y"].dropna()
            if not _s.empty:
                curve_slope = round(float(_s.iloc[-1]), 2)
    except Exception as e:
        logger.debug(f"[macro_state] slope da curva indisponível: {e}")

    # ── regime 6-estados (Selic × VIX) ─────────────────────────────────────
    regime = {}
    try:
        from utils.macro_regime import classificar_regime
        regime = classificar_regime(selic=selic, vix=vix, ipca=ipca_12m, treasury_10y=treasury_10y)
    except Exception as e:
        logger.warning(f"[macro_state] classificar_regime falhou: {e}")

    # ── ciclo 4-fases (curva/VIX/CPI/momentum) ─────────────────────────────
    fase_ciclo, fase_prob, fase_sinais = "", 0.0, {}
    try:
        from utils.regime_classifier import classificar_regime_do_macro_context
        _rc = classificar_regime_do_macro_context()
        fase_ciclo  = _rc.fase
        fase_prob   = _rc.probabilidade
        fase_sinais = _rc.sinais
    except Exception as e:
        logger.warning(f"[macro_state] regime_classifier falhou: {e}")

    # ── ciclo BR/US (leading indicators) ───────────────────────────────────
    fase_br, fase_us, conf_br, conf_us = "", "", 0, 0
    try:
        from utils.ciclo_economico import (
            calcular_indicadores_ciclo_br, calcular_indicadores_ciclo_us,
        )
        _cb = calcular_indicadores_ciclo_br()
        _cu = calcular_indicadores_ciclo_us()
        fase_br = _cb.get("fase_provavel", "")
        fase_us = _cu.get("fase_provavel", "")
        conf_br = int(_cb.get("confianca", 0) or 0)
        conf_us = int(_cu.get("confianca", 0) or 0)
    except Exception as e:
        logger.warning(f"[macro_state] ciclo_economico falhou: {e}")

    consenso, consenso_nota = _consolidar_consenso(fase_ciclo, fase_br, fase_us)

    return MacroState(
        selic=round(selic, 2),
        ipca_12m=round(ipca_12m, 2),
        selic_real=round(selic_r, 2),
        vix=round(vix, 1),
        treasury_10y=round(treasury_10y, 2),
        curve_slope_10y_2y=curve_slope,
        regime_key=regime.get("regime_key", "indefinido"),
        regime_label=regime.get("label", "n/d"),
        setores_favorecidos=regime.get("setores_favorecidos", []),
        setores_prejudicados=regime.get("setores_prejudicados", []),
        posicionamento=regime.get("posicionamento", ""),
        score_ambiente=int(regime.get("score_ambiente", 50)),
        fase_ciclo=fase_ciclo or "indefinido",
        fase_prob=fase_prob,
        fase_sinais=fase_sinais,
        fase_br=fase_br or "indefinido",
        fase_us=fase_us or "indefinido",
        confianca_br=conf_br,
        confianca_us=conf_us,
        consenso=consenso,
        consenso_nota=consenso_nota,
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

    try:
        _vix = float(macro_context.get("vix", VIX_FALLBACK) or VIX_FALLBACK)
        _t10 = float(macro_context.get("treasury_10y", TREASURY_10Y_FALLBACK) or TREASURY_10Y_FALLBACK)
        _selic = float(macro_context.get("selic", SELIC_FALLBACK) or SELIC_FALLBACK)

        # Eixo juro consciente de mercado.
        if str(market).upper() == "US":
            if _t10 >= 5.5:
                juro_w, juro_tag = 1.0, f"juro US alto ({_t10:.1f}% 10y)"
            elif _t10 >= 4.0:
                juro_w, juro_tag = 0.6, f"juro US elevado ({_t10:.1f}% 10y)"
            else:
                juro_w, juro_tag = 0.0, ""
        else:
            if _selic >= 13.0:
                juro_w, juro_tag = 1.0, f"juro muito alto (selic {_selic:.1f}%)"
            elif _selic > 10.0:
                juro_w, juro_tag = 0.7, f"juro alto (selic {_selic:.1f}%)"
            else:
                juro_w, juro_tag = 0.0, ""

        raw = juro_w * _TILT_JURO_ALTO.get(canon, 0)
        if juro_w and _TILT_JURO_ALTO.get(canon):
            _dir = "favorece" if _TILT_JURO_ALTO[canon] > 0 else "pressiona"
            motivos.append(f"{juro_tag} {_dir} {canon or 'setor'}")

        if _vix > 20.0:
            _s = _TILT_STRESS.get(canon, 0)
            raw += _s
            if _s:
                _dir = "defensivo no" if _s > 0 else "vulnerável ao"
                motivos.append(f"{_dir} stress global (vix {_vix:.0f})")

        pontos = int(max(-4, min(4, round(raw))))
        if pontos > 0:
            impacto = "favoravel"
        elif pontos < 0:
            impacto = "desfavoravel"
        else:
            impacto = "neutro"
    except Exception as e:
        logger.debug(f"[macro_state] tilt_setor falhou para '{setor}': {e}")
        impacto, pontos = "neutro", 0

    return {"impacto": impacto, "pontos": pontos, "motivos": motivos, "setor_canon": canon}


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
        selic = float(mc.get("selic", SELIC_FALLBACK) or SELIC_FALLBACK)
        ipca  = float(mc.get("ipca_12m") or mc.get("ipca", IPCA_12M_FALLBACK))
        vix   = float(mc.get("vix", VIX_FALLBACK) or VIX_FALLBACK)
        sreal = selic_real_fisher(selic, ipca)

        # regime label (puro, sem rede)
        regime_label = "n/d"
        try:
            from utils.macro_regime import classificar_regime
            regime_label = classificar_regime(
                selic=selic, vix=vix, ipca=ipca,
                treasury_10y=mc.get("treasury_10y", TREASURY_10Y_FALLBACK),
            ).get("label", "n/d")
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

        _cor_juro = "var(--bear)" if selic > 13 else ("var(--amber)" if selic > 10 else "var(--bull)")
        _cor_vix  = "var(--bear)" if vix > 25 else ("var(--amber)" if vix > 20 else "var(--bull)")

        def _kpi(lbl, val, cor="var(--text-secondary)"):
            return (
                f'<div style="display:flex;flex-direction:column;gap:1px;">'
                f'<span style="font-size:0.56rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em;">{lbl}</span>'
                f'<span style="font-size:0.86rem;font-weight:600;color:{cor};font-family:var(--font-data,monospace);">{val}</span>'
                f'</div>'
            )

        partes = [
            _kpi("regime", regime_label, "var(--accent)"),
            _kpi("selic", f"{selic:.2f}%", _cor_juro),
            _kpi("juro real (fisher)", f"{sreal:+.1f}%", _cor_juro),
            _kpi("ipca 12m", f"{ipca:.1f}%"),
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
        partes.append(_kpi("vix", f"{vix:.0f}", _cor_vix))

        st.markdown(
            '<div style="display:flex;gap:26px;flex-wrap:wrap;align-items:center;'
            'background:var(--bg-surface);border:1px solid var(--border-subtle);'
            'border-left:3px solid var(--accent);border-radius:6px;'
            'padding:8px 18px;margin-bottom:14px;font-family:var(--font-ui,sans-serif);">'
            + "".join(partes) +
            '</div>',
            unsafe_allow_html=True,
        )
    except Exception as e:
        logger.debug(f"[macro_state] render_cockpit_macro falhou: {e}")
