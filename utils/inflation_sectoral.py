"""
utils/inflation_sectoral.py
===========================
Camada de TRANSMISSÃO inflação→setor — traduz a inflação decomposta
(snapshots 'inflacao_br'/'inflacao_us' do sync_macro) em pressão de margem por
setor, e combina com o tilt de regime (macro_state) no pilar macro-setorial do
score (utils/health_engine).

Modelo (primeiros princípios, não econometria):
  Cada setor tem (a) drivers de CUSTO — quais cortes de inflação encarecem seu
  COGS, com peso — e (b) INDEXAÇÃO DE RECEITA 0..1 — quanto da receita acompanha
  a inflação (pricing power / contratos indexados).

    custo_setor   = Σ peso_i · inflação_corte_i          (inflação de insumo)
    squeeze       = max(0, custo_setor − headline) · (1 − indexação)
                    → inflação de custo ACIMA da média que NÃO é repassada
    tailwind      = max(0, headline − meta) · indexação
                    → receita indexada subindo acima da meta (utilities, FII,
                      saúde, imobiliário com aluguel IPCA/IGP-M)
    pontos_infl   = clamp(round(0.4·tailwind − 0.8·squeeze), −4, +4)

Graceful: sem snapshot de inflação (ETL sem secrets, cold-start), o componente
de inflação é 0 e só o tilt de regime entra — o score nunca quebra.
"""
from __future__ import annotations

from utils.st_fallback import st, ST_AVAILABLE as _ST

from utils.logger import get_logger
from utils.macro_state import tilt_setor, normalizar_setor

logger = get_logger(__name__)

# Meta de inflação de referência (centro da meta BR ≈ 3%; CPI alvo Fed ≈ 2%).
_META_BR = 3.0
_META_US = 2.0

# ── Matriz de transmissão BR (cortes do IPCA por setor canônico) ─────────────
# 'custo': [(corte_ipca, peso)]; 'indexacao': 0..1 (pricing power/receita indexada)
_TRANSMISSAO_BR: dict[str, dict] = {
    "consumo_ciclico":   {"custo": [("servicos", 0.4), ("livres", 0.6)],            "indexacao": 0.2},
    "consumo_defensivo": {"custo": [("alimentacao", 0.7), ("livres", 0.3)],         "indexacao": 0.7},
    "saude":             {"custo": [("saude", 0.6), ("servicos", 0.4)],             "indexacao": 0.8},
    "utilities":         {"custo": [("administrados", 0.6)],                         "indexacao": 0.9},
    "comunicacao":       {"custo": [("servicos", 0.6)],                              "indexacao": 0.7},
    "imobiliario":       {"custo": [("habitacao", 0.5), ("servicos", 0.5)],         "indexacao": 0.8},
    "industria":         {"custo": [("comercializaveis", 0.6), ("administrados", 0.4)], "indexacao": 0.4},
    "materiais":         {"custo": [("comercializaveis", 0.6), ("administrados", 0.4)], "indexacao": 0.6},
    "energia":           {"custo": [("administrados", 0.5)],                         "indexacao": 0.8},
    "financeiro":        {"custo": [("servicos", 0.4)],                              "indexacao": 0.6},
    "tecnologia":        {"custo": [("servicos", 0.6)],                              "indexacao": 0.5},
}

# ── Matriz de transmissão US (componentes do CPI) ────────────────────────────
_TRANSMISSAO_US: dict[str, dict] = {
    "consumo_ciclico":   {"custo": [("servicos_core", 0.5), ("bens_core", 0.5)], "indexacao": 0.3},
    "consumo_defensivo": {"custo": [("alimentos", 0.7), ("bens_core", 0.3)],     "indexacao": 0.7},
    "saude":             {"custo": [("servicos_core", 0.7)],                      "indexacao": 0.8},
    "utilities":         {"custo": [("energia", 0.6)],                            "indexacao": 0.9},
    "imobiliario":       {"custo": [("shelter", 0.8)],                            "indexacao": 0.9},  # REIT: aluguel = shelter
    "industria":         {"custo": [("bens_core", 0.6), ("energia", 0.4)],       "indexacao": 0.4},
    "materiais":         {"custo": [("bens_core", 0.5), ("energia", 0.5)],       "indexacao": 0.6},
    "energia":           {"custo": [("energia", 0.3)],                            "indexacao": 0.8},
    "tecnologia":        {"custo": [("servicos_core", 0.5)],                      "indexacao": 0.6},
    "financeiro":        {"custo": [("servicos_core", 0.4)],                      "indexacao": 0.6},
    "comunicacao":       {"custo": [("servicos_core", 0.5)],                      "indexacao": 0.7},
}


# ── Leitura do snapshot de inflação (resiliente: app streamlit OU ETL env) ───

def _carregar_inflacao_df(origem: str):
    """Carrega o snapshot de inflação. Tenta camada streamlit, depois env (ETL)."""
    # 1. via macro_supabase (app / st.secrets)
    try:
        from utils.macro_supabase import carregar_snapshot
        df = carregar_snapshot(origem, max_age_days=45)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.debug(f"[inflation_sectoral] carregar_snapshot('{origem}') falhou: {e}")
    # 2. fallback ETL: SUPABASE_URL/SERVICE_KEY via os.environ
    try:
        import os
        import json as _json
        url = os.environ.get("SUPABASE_URL", "")
        key = (os.environ.get("SUPABASE_SERVICE_KEY", "")
               or os.environ.get("SUPABASE_ANON_KEY", ""))
        if url and key:
            from supabase import create_client
            from utils.macro_supabase import _json_to_df
            sb = create_client(url, key)
            resp = (sb.table("macro_snapshots")
                    .select("payload").eq("origem", origem).limit(1).execute())
            if resp.data:
                payload = resp.data[0]["payload"]
                if isinstance(payload, dict):
                    payload = _json.dumps(payload)
                return _json_to_df(payload)
    except Exception as e:
        logger.debug(f"[inflation_sectoral] fallback env para '{origem}' falhou: {e}")
    return None


@st.cache_data(ttl=21600, show_spinner=False)
def get_inflacao_atual(market: str = "BR", horizonte: str | None = None) -> dict:
    """
    Retorna {corte: valor_%} para o mercado, no horizonte pedido.
    horizonte=None → nível padrão (BR: *_12m acumulado; US: *_yoy).
    horizonte='3m'/'6m' → run-rate ANUALIZADO (momentum — capta inflexão).
    Retorna {} se snapshot ausente (degrada o pilar/cockpit para neutro).
    """
    is_br = str(market).upper() == "BR"
    origem = "inflacao_br" if is_br else "inflacao_us"
    if horizonte:
        suf = "_" + str(horizonte).lstrip("_")
    else:
        suf = "_12m" if is_br else "_yoy"

    df = _carregar_inflacao_df(origem)
    out: dict[str, float] = {}
    if df is None or df.empty:
        return out

    for col in df.columns:
        if str(col).endswith(suf):
            s = df[col].dropna()
            if not s.empty:
                out[str(col)[: -len(suf)]] = round(float(s.iloc[-1]), 2)
    return out


def gap_margem(market: str = "BR", horizonte: str | None = None) -> dict | None:
    """
    Gap de margem da economia = inflação ao PRODUTOR − inflação ao CONSUMIDOR.
    BR: IGP-M (atacado) − IPCA cheio; US: PPI (all commodities) − core CPI.

    Positivo = custo do produtor subindo mais rápido que o preço final →
    compressão de margem agregada. Negativo = alívio de margem.

    Retorna {'gap', 'produtor', 'consumidor'} (pp/%) ou None se indisponível.
    """
    is_br = str(market).upper() == "BR"
    infl = get_inflacao_atual(market, horizonte=horizonte)
    if not infl:
        return None
    prod = infl.get("igpm") if is_br else infl.get("ppi")
    cons = infl.get("ipca_cheio") if is_br else infl.get("core")
    if prod is None or cons is None:
        return None
    return {"gap": round(prod - cons, 2), "produtor": prod, "consumidor": cons}


def _headline(infl: dict, market: str) -> float:
    """Inflação headline (proxy de média) a partir dos cortes disponíveis."""
    if str(market).upper() == "BR":
        # 'livres' + 'administrados' aproxima o headline; senão média dos grupos
        if infl.get("livres") is not None and infl.get("administrados") is not None:
            return 0.74 * infl["livres"] + 0.26 * infl["administrados"]
    else:
        if infl.get("core") is not None:
            return infl["core"]
    vals = [v for v in infl.values() if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else (_META_BR if str(market).upper() == "BR" else _META_US)


def pressao_inflacao_setor(setor_canon: str, market: str, infl: dict) -> dict:
    """
    Componente de inflação do pilar macro-setorial.
    Retorna {'pontos', 'custo_inflacao', 'squeeze', 'tailwind', 'motivos'}.
    """
    if not infl or not setor_canon:
        return {"pontos": 0, "motivos": []}

    is_br = str(market).upper() == "BR"
    matriz = _TRANSMISSAO_BR if is_br else _TRANSMISSAO_US
    meta = _META_BR if is_br else _META_US
    cfg = matriz.get(setor_canon)
    if not cfg:
        return {"pontos": 0, "motivos": []}

    headline = _headline(infl, market)

    # custo ponderado dos insumos do setor
    num, den = 0.0, 0.0
    for corte, peso in cfg["custo"]:
        v = infl.get(corte)
        if v is not None:
            num += peso * v
            den += peso
    if den <= 0:
        return {"pontos": 0, "motivos": []}
    custo = num / den
    indexacao = cfg["indexacao"]

    squeeze = max(0.0, custo - headline) * (1 - indexacao)
    tailwind = max(0.0, headline - meta) * indexacao
    pontos = int(max(-4, min(4, round(0.4 * tailwind - 0.8 * squeeze))))

    motivos: list[str] = []
    if pontos <= -1:
        motivos.append(
            f"custo de insumo {custo:.1f}% acima da média ({headline:.1f}%) "
            f"e baixo repasse (indexação {indexacao:.0%}) → compressão de margem"
        )
    elif pontos >= 1:
        motivos.append(
            f"receita indexada (indexação {indexacao:.0%}) com inflação "
            f"{headline:.1f}% acima da meta → proteção de margem"
        )

    return {
        "pontos": pontos,
        "custo_inflacao": round(custo, 2),
        "headline": round(headline, 2),
        "squeeze": round(squeeze, 2),
        "tailwind": round(tailwind, 2),
        "motivos": motivos,
    }


def pilar_macro_setorial(setor: str, market: str = "BR",
                         macro_context: dict | None = None) -> dict:
    """
    Pilar macro-setorial do score (±8): combina o tilt de regime (juro × stress)
    com a transmissão de inflação setorial.

    Retorna {'pontos', 'impacto', 'alertas', 'breakdown', 'setor_canon'}.
    Robusto: qualquer falha → pontos 0 (nunca derruba o score).
    """
    canon = normalizar_setor(setor)
    alertas: list[str] = []
    breakdown: dict = {}

    # 1. tilt de regime (puro) ────────────────────────────────────────────────
    try:
        tilt = tilt_setor(setor, macro_context, market=market)
    except Exception as e:
        logger.debug(f"[inflation_sectoral] tilt_setor falhou: {e}")
        tilt = {"pontos": 0, "motivos": []}
    pts_regime = int(tilt.get("pontos", 0))

    # 2. transmissão de inflação setorial ──────────────────────────────────────
    pts_infl = 0
    try:
        infl = get_inflacao_atual(market)
        pres = pressao_inflacao_setor(canon, market, infl)
        pts_infl = int(pres.get("pontos", 0))
        if pres.get("motivos"):
            breakdown["inflação setorial"] = "; ".join(pres["motivos"])
    except Exception as e:
        logger.debug(f"[inflation_sectoral] pressao_inflacao_setor falhou: {e}")

    total = int(max(-8, min(8, pts_regime + pts_infl)))

    if tilt.get("motivos"):
        breakdown["regime"] = "; ".join(tilt["motivos"])

    _motivos_txt = "; ".join(
        tilt.get("motivos", []) + ([breakdown["inflação setorial"]] if "inflação setorial" in breakdown else [])
    )
    if total <= -3:
        alertas.append(
            f"🌡️ vento macro-setorial contra ({canon or 'setor'})"
            + (f": {_motivos_txt}" if _motivos_txt else ".")
        )
    elif total >= 3:
        alertas.append(
            f"🌤️ vento macro-setorial a favor ({canon or 'setor'})"
            + (f": {_motivos_txt}" if _motivos_txt else ".")
        )

    impacto = "favoravel" if total > 0 else ("desfavoravel" if total < 0 else "neutro")

    return {
        "pontos": total,
        "pts_regime": pts_regime,
        "pts_inflacao": pts_infl,
        "impacto": impacto,
        "alertas": alertas,
        "breakdown": breakdown,
        "setor_canon": canon,
    }
