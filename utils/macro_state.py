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

try:
    import streamlit as st
    _ST = True
except ImportError:
    class _NoOpCache:
        def __call__(self, *a, **kw):
            return lambda f: f
    class _FakeSt:
        cache_data = _NoOpCache()
        class session_state:
            @staticmethod
            def get(*a, **kw):
                return kw.get('default', a[1] if len(a) > 1 else {})
    st = _FakeSt()
    _ST = False

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


# ── Taxonomia setorial canônica ──────────────────────────────────────────────
# O terminal recebe setores em inglês (yfinance/FMP: "Financial Services") E em
# português (cache/CVM/traduzir_setor: "🏦 financeiro"). Sem normalizar, o
# cruzamento setor↔regime/inflação falha silenciosamente. Esta é a chave única.
_SETOR_CANON = {
    # English (yfinance / FMP)
    "financial services":     "financeiro",
    "technology":             "tecnologia",
    "communication services": "comunicacao",
    "healthcare":             "saude",
    "consumer cyclical":      "consumo_ciclico",
    "consumer defensive":     "consumo_defensivo",
    "industrials":            "industria",
    "basic materials":        "materiais",
    "energy":                 "energia",
    "utilities":              "utilities",
    "real estate":            "imobiliario",
    # Portuguese (cache / CVM / traduzir_setor — podem vir com emoji prefixo)
    "financeiro":             "financeiro",
    "tecnologia":             "tecnologia",
    "telecom":                "comunicacao",
    "comunicação":            "comunicacao",
    "saúde":                  "saude",
    "consumo cíclico":        "consumo_ciclico",
    "consumo def.":           "consumo_defensivo",
    "consumo defensivo":      "consumo_defensivo",
    "consumo básico":         "consumo_defensivo",
    "indústria":              "industria",
    "materiais":              "materiais",
    "energia":                "energia",
    "imobiliário":            "imobiliario",
}

def normalizar_setor(setor: str | None) -> str:
    """
    Reduz um rótulo de setor (EN ou PT, com ou sem emoji) à chave canônica.
    Ex.: 'Financial Services' → 'financeiro'; '🏦 financeiro' → 'financeiro'.
    Devolve o texto em minúsculas se não reconhecer.
    """
    if not setor:
        return ""
    s = str(setor).strip().lower()
    # match por substring (cobre prefixos de emoji e sufixos tipo " br")
    for label, canon in _SETOR_CANON.items():
        if label in s:
            return canon
    return s


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

def tilt_setor(setor: str, macro_context: dict | None = None) -> dict:
    """
    Avalia se o setor está favorecido/neutro/desfavorecido no regime atual,
    usando APENAS o macro_context (selic/vix/ipca) — sem chamadas de rede.

    Retorna {'impacto', 'pontos', 'motivos'} onde 'pontos' é a contribuição
    base de regime para o pilar macro-setorial do score (±4). O componente de
    inflação setorial é somado em utils/inflation_sectoral.py.

    Pura e barata: chamável por ticker no ETL.
    """
    if macro_context is None:
        macro_context = st.session_state.get("macro_context", {}) or {}

    motivos: list[str] = []
    canon = normalizar_setor(setor)

    try:
        _selic = float(macro_context.get("selic", SELIC_FALLBACK) or SELIC_FALLBACK)
        _vix   = float(macro_context.get("vix", VIX_FALLBACK) or VIX_FALLBACK)
        _ipca  = float(macro_context.get("ipca_12m") or macro_context.get("ipca", IPCA_12M_FALLBACK))

        # Peso do eixo juro: cresce com o nível da Selic (proibitivo > 13%).
        if _selic >= 13.0:
            juro_w, juro_tag = 1.0, "juro muito alto"
        elif _selic > 10.0:
            juro_w, juro_tag = 0.7, "juro alto"
        else:
            juro_w, juro_tag = 0.0, ""

        raw = juro_w * _TILT_JURO_ALTO.get(canon, 0)
        if juro_w and _TILT_JURO_ALTO.get(canon):
            _dir = "favorece" if _TILT_JURO_ALTO[canon] > 0 else "pressiona"
            motivos.append(f"{juro_tag} (selic {_selic:.1f}%) {_dir} {canon or 'setor'}")

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
