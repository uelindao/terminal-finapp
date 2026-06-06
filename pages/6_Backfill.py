"""
pages/6_Backfill.py
===================
Painel de administração para backfill de health scores históricos.
Acesso restrito a administradores.

Roda diretamente no Streamlit Community Cloud:
  - Sem dependência de filesystem local (checkpoint via banco de dados)
  - Processa tickers em lotes configuráveis
  - Mostra progresso em tempo real
  - Usa as FMP_API_KEY do st.secrets automaticamente
"""
import streamlit as st
import pandas as pd
import time
import datetime

from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from utils.components import page_header, section_title
from utils.logger import get_logger
from utils.tickers import SCREENER_US, SCREENER_B3

logger = get_logger(__name__)

# ── Guarda de acesso ──────────────────────────────────────────────────────────
if not require_auth():
    st.stop()

render_user_badge()
aplicar_tema()

user = get_current_user()
if not user or not user.get("is_admin"):
    st.error("🔒 acesso restrito a administradores.")
    st.stop()

st.set_page_config(
    page_title="backfill | finterminal",
    layout="wide",
    page_icon="🕐",
)

page_header("🕐 backfill histórico", "popula 10 anos de health scores históricos via FMP.")

# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES CORE (sem dependência de arquivo local — tudo via banco)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _build_macro_timeline() -> pd.DataFrame:
    """Baixa Selic (BCB) e VIX (yfinance) dos últimos 11 anos."""
    import yfinance as yf
    import numpy as np

    inicio = (datetime.date.today() - datetime.timedelta(days=11 * 365)).strftime("%Y-%m-%d")
    df = pd.DataFrame(
        index=pd.date_range(inicio, datetime.date.today(), freq="D")
    )

    # Selic via BCB SGS
    try:
        from bcb import sgs
        df_bcb = sgs.get({"selic": 432}, start=inicio)
        s = df_bcb["selic"].dropna()
        s.index = pd.to_datetime(s.index)
        s = s.apply(lambda v: v * 100 if v < 1 else v)
        s = s.apply(lambda v: 14.75 if v > 50 else v)
        df["selic"] = s.reindex(df.index, method="ffill").fillna(14.75)
    except Exception:
        df["selic"] = 14.75

    # VIX via yfinance
    try:
        hist = yf.Ticker("^VIX").history(start=inicio, auto_adjust=True)
        if not hist.empty:
            v = hist["Close"].dropna()
            if getattr(v.index, "tz", None) is not None:
                v.index = v.index.tz_localize(None)
            v.index = pd.to_datetime(v.index)
            df["vix"] = v.reindex(df.index, method="ffill").fillna(15.0)
        else:
            df["vix"] = 15.0
    except Exception:
        df["vix"] = 15.0

    df["selic"] = df["selic"].fillna(14.75)
    df["vix"]   = df["vix"].fillna(15.0)
    return df


def _macro_na_data(timeline: pd.DataFrame, data_str: str) -> dict:
    try:
        dt    = pd.Timestamp(data_str[:10])
        antes = timeline[timeline.index <= dt]
        row   = antes.iloc[-1] if not antes.empty else timeline.iloc[0]
        return {"selic": float(row["selic"]), "vix": float(row["vix"])}
    except Exception:
        return {"selic": 14.75, "vix": 15.0}


def _safe(val, default=None):
    if val is None:
        return default
    try:
        import numpy as np
        v = float(val)
        return v if not np.isnan(v) else default
    except (TypeError, ValueError):
        return default


def _calcular_momentum(precos: pd.Series, data_ref: str):
    """Retorna (momentum_pct_12_1m, acima_mm200)."""
    try:
        import numpy as np
        dt    = pd.Timestamp(data_ref[:10])
        antes = precos[precos.index <= dt]
        if len(antes) < 22:
            return None, None
        p_atual = float(antes.iloc[-1])
        p_1m    = float(antes.iloc[-22])   if len(antes) >= 22  else p_atual
        p_12m   = float(antes.iloc[-252])  if len(antes) >= 252 else float(antes.iloc[0])
        mom     = (p_1m / p_12m - 1) * 100 if p_12m > 0 else None
        mm200   = float(antes.iloc[-200:].mean()) if len(antes) >= 200 else None
        acima   = p_atual > mm200 if mm200 else None
        return mom, acima
    except Exception:
        return None, None


def _score_offline(
    ratios: dict, km: dict,
    ratios_yoy, km_yoy,
    precos: pd.Series,
    data_ref: str,
    macro: dict,
    is_br: bool,
) -> int:
    """Health score histórico offline (~85-90% de fidelidade ao motor ao vivo)."""
    score = 0
    selic = macro.get("selic", 14.75)
    vix   = macro.get("vix", 15.0)

    # ── Qualidade ────────────────────────────────────────────────────────────
    roe    = _safe(ratios.get("returnOnEquity"))
    roa    = _safe(ratios.get("returnOnAssets"))
    margem = _safe(ratios.get("netProfitMargin"))

    if roe is not None:
        rp = roe * 100
        score += 8 if rp >= 20 else (5 if rp >= 12 else (2 if rp >= 6 else (-5 if rp < 0 else 0)))

    if roa is not None:
        rp = roa * 100
        score += 6 if rp >= 10 else (4 if rp >= 5 else (2 if rp >= 2 else (-4 if rp < 0 else 0)))

    if margem is not None:
        mp = margem * 100
        score += 6 if mp >= 20 else (4 if mp >= 10 else (2 if mp >= 4 else (-3 if mp < 0 else 0)))

    # ── Valuation ────────────────────────────────────────────────────────────
    pe  = _safe(ratios.get("priceEarningsRatio"))
    pb  = _safe(ratios.get("priceToBookRatio"))
    evm = _safe(ratios.get("enterpriseValueMultiple"))

    if pe is not None and pe > 0:
        pb_ok, pm = (12, 22) if is_br else (18, 30)
        score += 8 if pe <= pb_ok else (4 if pe <= pm else (1 if pe <= 50 else -4))

    if pb is not None and pb > 0:
        score += 6 if pb <= 1.5 else (3 if pb <= 3.0 else (1 if pb <= 5.0 else (-4 if pb > 8.0 else 0)))

    if evm is not None and 0 < evm < 200:
        score += 6 if evm <= 8 else (3 if evm <= 15 else (0 if evm <= 25 else -4))

    # ── Solvência ────────────────────────────────────────────────────────────
    de    = _safe(ratios.get("debtEquityRatio")) or _safe(km.get("debtToEquity"))
    cr    = _safe(ratios.get("currentRatio"))    or _safe(km.get("currentRatio"))
    icr   = _safe(ratios.get("interestCoverage"))
    nd_eb = _safe(km.get("netDebtToEBITDA"))

    if de is not None:
        lb = 0.5 if (is_br and selic > 10) else 0.8
        lm = 1.2 if (is_br and selic > 10) else 1.5
        score += 12 if de < lb else (6 if de < lm else (0 if de < 2.5 else -8))

    if cr is not None:
        score += 5 if cr >= 2.0 else (3 if cr >= 1.5 else (1 if cr >= 1.0 else (-3 if cr < 0.8 else 0)))

    if icr is not None and icr > 0:
        score += 3 if icr >= 5 else (1 if icr >= 3 else (-3 if icr < 1.5 else 0))

    if nd_eb is not None:
        score += 5 if nd_eb < 0 else (3 if nd_eb <= 1.5 else (0 if nd_eb <= 3.0 else (-3 if nd_eb <= 4.5 else -6)))

    # ── ROIC vs WACC ─────────────────────────────────────────────────────────
    roic = _safe(km.get("roic"))
    if roic is not None:
        rp    = roic * 100
        wacc  = (0.60 * (selic + 7.5) + 0.40 * (selic * 0.66)) if is_br else (0.60 * (4.5 + 5.5) + 0.40 * (4.5 * 0.79))
        delta = rp - wacc
        score += 12 if delta >= 5 else (6 if delta >= 0 else (-3 if delta >= -3 else -8))

    # ── Piotroski parcial (7/9) ───────────────────────────────────────────────
    fcf_r = _safe(ratios.get("freeCashFlowOperatingCashFlowRatio"))
    fcf_y = _safe(km.get("freeCashFlowYield"))
    f1 = 1 if (roa is not None and roa > 0) else 0
    f2 = 1 if ((fcf_r and fcf_r > 0) or (fcf_y and fcf_y > 0)) else 0
    f3 = f5 = f6 = f8 = f9 = 0
    if ratios_yoy and km_yoy:
        roa_p = _safe(ratios_yoy.get("returnOnAssets"))
        f3 = 1 if (roa and roa_p and roa > roa_p) else 0
        de_p = _safe(ratios_yoy.get("debtEquityRatio")) or _safe(km_yoy.get("debtToEquity"))
        f5 = 1 if (de and de_p and de < de_p) else 0
        cr_p = _safe(ratios_yoy.get("currentRatio")) or _safe(km_yoy.get("currentRatio"))
        f6 = 1 if (cr and cr_p and cr > cr_p) else 0
        gm   = _safe(ratios.get("grossProfitMargin"))
        gm_p = _safe(ratios_yoy.get("grossProfitMargin"))
        f8 = 1 if (gm and gm_p and gm > gm_p) else 0
        at   = _safe(ratios.get("assetTurnover"))
        at_p = _safe(ratios_yoy.get("assetTurnover"))
        f9 = 1 if (at and at_p and at > at_p) else 0

    crit = [f1, f2, f3, f5, f6, f8, f9]
    n    = len([c for c in crit if c is not None])
    fs9  = round(sum(crit) / n * 9) if n else 5
    score += 15 if fs9 >= 7 else (8 if fs9 >= 5 else (-8 if fs9 <= 2 else 0))

    # ── Crescimento ──────────────────────────────────────────────────────────
    rg = _safe(km.get("revenueGrowth"))
    eg = _safe(km.get("epsgrowth"))
    if rg is not None:
        rp = rg * 100
        score += 8 if rp >= 15 else (5 if rp >= 5 else (1 if rp >= 0 else (-5 if rp < -5 else 0)))
    if eg is not None:
        ep = eg * 100
        score += 7 if ep >= 20 else (4 if ep >= 8 else (-4 if ep < -10 else 0))

    # ── Momentum ─────────────────────────────────────────────────────────────
    mom, acima = _calcular_momentum(precos, data_ref)
    if mom is not None:
        score += 8 if mom >= 20 else (5 if mom >= 8 else (2 if mom >= 0 else (-3 if mom >= -10 else -8)))
    if acima is not None and not acima:
        score -= 4

    # ── Macro ────────────────────────────────────────────────────────────────
    score += -10 if vix > 30 else (-6 if vix > 25 else (-3 if vix > 20 else 0))
    if is_br:
        score += -8 if selic > 13 else (-3 if selic > 10 else 0)

    return int(min(max(score, 0), 100))


def _processar_ticker_st(
    ticker_yf: str,
    macro_tl:  pd.DataFrame,
    status_placeholder,
) -> tuple[int, int, str]:
    """
    Processa um ticker dentro do contexto Streamlit.
    Retorna (n_inseridos, n_skipped, diagnostico).
    """
    import yfinance as yf
    from utils.fmp_client import get_ratios_trimestrais, get_key_metrics_trimestrais, _get
    from database.db import registrar_historico_score_batch, get_datas_historico_score

    is_br  = ticker_yf.endswith(".SA")
    tk_fmp = ticker_yf.replace(".SA", "").upper()
    diag   = ""

    status_placeholder.write(f"🔄 `{tk_fmp}` — buscando FMP (quarterly)…")

    # ── 1. Trimestral ─────────────────────────────────────────────────────────
    ratios_list = get_ratios_trimestrais(tk_fmp, limit=40)
    time.sleep(0.4)
    km_list     = get_key_metrics_trimestrais(tk_fmp, limit=40)
    time.sleep(0.4)
    yoy_offset  = 4
    granular    = "trimestral"

    # ── 2. Fallback anual ─────────────────────────────────────────────────────
    if not ratios_list:
        status_placeholder.write(f"🔄 `{tk_fmp}` — quarterly vazio, tentando annual…")
        ratios_list = _get(f"ratios/{tk_fmp}", {"limit": 10}) or []
        time.sleep(0.4)
        km_list     = _get(f"key-metrics/{tk_fmp}", {"limit": 10}) or []
        time.sleep(0.4)
        yoy_offset  = 1
        granular    = "anual"

    if not ratios_list:
        diag = "FMP: sem dados (ativo não coberto ou quota esgotada)"
        status_placeholder.write(f"⚠️ `{tk_fmp}` — {diag}")
        return 0, 0, diag

    diag = f"FMP: {len(ratios_list)} períodos ({granular}), km: {len(km_list)}"
    status_placeholder.write(f"🔄 `{tk_fmp}` — {diag}")

    km_by_date       = {item.get("date", ""): item for item in km_list}
    datas_existentes = get_datas_historico_score(ticker_yf) | get_datas_historico_score(tk_fmp)

    # ── Preços históricos ─────────────────────────────────────────────────────
    precos = pd.Series(dtype=float)
    try:
        inicio_preco = (
            datetime.date.today() - datetime.timedelta(days=11 * 365)
        ).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker_yf).history(start=inicio_preco, auto_adjust=True)
        if not hist.empty:
            precos = hist["Close"].dropna()
            if getattr(precos.index, "tz", None) is not None:
                precos.index = precos.index.tz_localize(None)
    except Exception:
        pass

    # ── Calcula score por período ─────────────────────────────────────────────
    registros:  list[dict] = []
    skipped     = 0
    calc_erros  = 0

    for i, ratios in enumerate(ratios_list):
        data_str = ratios.get("date", "")
        if not data_str:
            continue
        if data_str[:10] in datas_existentes:
            skipped += 1
            continue

        km         = km_by_date.get(data_str, {})
        ratios_yoy = ratios_list[i + yoy_offset] if i + yoy_offset < len(ratios_list) else None
        km_yoy     = km_by_date.get((ratios_yoy or {}).get("date", ""), {})
        macro      = _macro_na_data(macro_tl, data_str)

        try:
            score = _score_offline(
                ratios=ratios, km=km,
                ratios_yoy=ratios_yoy, km_yoy=km_yoy,
                precos=precos, data_ref=data_str,
                macro=macro, is_br=is_br,
            )
            # Usa somente a data (sem timezone) — mais compatível com Supabase
            registros.append({
                "ticker":       ticker_yf,
                "score":        int(score),
                "calculado_em": data_str,   # "YYYY-MM-DD" — Supabase converte para TIMESTAMPTZ
            })
        except Exception as e:
            calc_erros += 1
            logger.warning(f"[backfill] score {tk_fmp} {data_str}: {e}")

    diag += f" | calculados: {len(registros)} | skip: {skipped} | calc_erros: {calc_erros}"

    if not registros:
        status_placeholder.write(
            f"ℹ️ `{tk_fmp}` — sem registros novos "
            f"(skip={skipped}, calc_erros={calc_erros})"
        )
        return 0, skipped, diag

    # ── Salva no Supabase ─────────────────────────────────────────────────────
    status_placeholder.write(
        f"💾 `{tk_fmp}` — inserindo {len(registros)} pontos no Supabase…"
    )
    try:
        n = registrar_historico_score_batch(registros, ignorar_existentes=False)
        diag += f" | inseridos: {n}"
        return n, skipped, diag
    except Exception as e:
        diag += f" | ERRO INSERT: {e}"
        status_placeholder.write(f"❌ `{tk_fmp}` — falha no insert: {e}")
        logger.error(f"[backfill] insert {tk_fmp}: {e}", exc_info=True)
        return 0, skipped, diag


# ──────────────────────────────────────────────────────────────────────────────
# DASHBOARD DE COBERTURA
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _cobertura_atual() -> pd.DataFrame:
    """Retorna DataFrame com cobertura atual por ticker."""
    from database.supabase_client import get_supabase
    try:
        sb   = get_supabase()
        rows = sb.table("health_score_history").select("ticker, calculado_em").execute().data or []
        if not rows:
            return pd.DataFrame(columns=["ticker", "pontos", "inicio", "fim"])
        df = pd.DataFrame(rows)
        df["calculado_em"] = pd.to_datetime(df["calculado_em"], utc=True)
        agg = df.groupby("ticker")["calculado_em"].agg(
            pontos="count",
            inicio="min",
            fim="max",
        ).reset_index()
        agg["inicio"] = agg["inicio"].dt.strftime("%Y-%m-%d")
        agg["fim"]    = agg["fim"].dt.strftime("%Y-%m-%d")
        return agg.sort_values("pontos", ascending=False)
    except Exception as e:
        logger.warning(f"[backfill] falha ao buscar cobertura: {e}")
        return pd.DataFrame(columns=["ticker", "pontos", "inicio", "fim"])


# ── UI ────────────────────────────────────────────────────────────────────────

# Dashboard de cobertura
section_title("📊 cobertura atual")

cob = _cobertura_atual()

# Universos de referência (deduplicados)
_us_set = set(SCREENER_US)
_br_set = set(SCREENER_B3)
total_eua = len(_us_set)
total_br  = len(_br_set)

# Interseção com listas canônicas — evita contar FIIs/watchlist fora dos screeners
cob_eua = cob[cob["ticker"].isin(_us_set)]
cob_br  = cob[cob["ticker"].isin(_br_set)]

m1, m2, m3, m4 = st.columns(4)
with m1:
    n_eua = len(cob_eua)
    st.metric("tickers EUA cobertos", f"{n_eua} / {total_eua}",
              f"{n_eua/total_eua*100:.0f}%" if total_eua else "—")
with m2:
    n_br = len(cob_br)
    st.metric("tickers BR cobertos", f"{n_br} / {total_br}",
              f"{n_br/total_br*100:.0f}%" if total_br else "—")
with m3:
    total_pts = int(cob["pontos"].sum()) if not cob.empty else 0
    st.metric("total de pontos no banco", f"{total_pts:,}")
with m4:
    # Mediana só dos tickers com backfill real (≥ 5 pontos)
    cob_real = cob[cob["pontos"] >= 5]
    med_pts  = int(cob_real["pontos"].median()) if not cob_real.empty else 0
    st.metric("mediana pontos/ticker (≥5)", med_pts,
              help="meta: ~10 pontos = 10 anos anuais | ~40 = 10 anos trimestrais")

# Barra de progresso global
cobertos      = n_eua + n_br
total_tickers = total_eua + total_br
if total_tickers:
    st.progress(
        min(cobertos / total_tickers, 1.0),
        text=f"{cobertos}/{total_tickers} tickers do screener com dados históricos",
    )

st.markdown("<br>", unsafe_allow_html=True)

# Tabela de cobertura expandida
with st.expander("🔍 detalhe por ticker", expanded=False):
    if not cob.empty:
        col_flt1, col_flt2 = st.columns(2)
        with col_flt1:
            _merc_flt = st.selectbox("mercado:", ["todos", "eua", "brasil"])
        with col_flt2:
            _min_pts = st.number_input("mín. pontos:", 0, 40, 0)

        df_exib = cob.copy()
        if _merc_flt == "eua":
            df_exib = df_exib[~df_exib["ticker"].str.endswith(".SA")]
        elif _merc_flt == "brasil":
            df_exib = df_exib[df_exib["ticker"].str.endswith(".SA")]
        if _min_pts > 0:
            df_exib = df_exib[df_exib["pontos"] >= _min_pts]

        st.dataframe(
            df_exib.rename(columns={
                "ticker": "ticker", "pontos": "pontos históricos",
                "inicio": "primeiro score", "fim": "último score",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("nenhum dado histórico ainda. execute o backfill abaixo.")

st.markdown("---")

# ──────────────────────────────────────────────────────────────────────────────
# CONTROLES DE BACKFILL
# ──────────────────────────────────────────────────────────────────────────────
section_title("🚀 executar backfill")

col_a, col_b, col_c = st.columns([2, 2, 2])

with col_a:
    mercado_sel = st.selectbox(
        "mercado:",
        ["EUA", "Brasil (B3)", "Todos"],
        help="FMP tem boa cobertura de EUA e das maiores ações BR.",
    )
with col_b:
    batch_size = st.slider(
        "tickers por sessão:",
        min_value=5, max_value=100, value=30, step=5,
        help="Com 2 chaves FMP free: ~500 req/dia. "
             "Cada ticker usa 2 req + yfinance. "
             "30 tickers ≈ 3-5 min.",
    )
with col_c:
    pular_cobertos = st.checkbox(
        "pular tickers com ≥ 20 pontos",
        value=True,
        help="Evita re-processar tickers já completos.",
    )

# Monta lista de tickers pendentes
if mercado_sel == "EUA":
    todos_tickers = list(SCREENER_US)
elif mercado_sel == "Brasil (B3)":
    todos_tickers = list(SCREENER_B3)
else:
    todos_tickers = list(SCREENER_US) + list(SCREENER_B3)

# Filtra cobertura
if pular_cobertos and not cob.empty:
    completos = set(cob[cob["pontos"] >= 20]["ticker"].tolist())
    pendentes = [t for t in todos_tickers if t not in completos]
else:
    pendentes = todos_tickers

lote = pendentes[:batch_size]

st.markdown(
    f'<div style="font-family:Courier New; font-size:0.78rem; color:#555; margin:8px 0;">'
    f'pendentes: <span style="color:#FF9900;">{len(pendentes)}</span> tickers | '
    f'este lote: <span style="color:#00C853;">{len(lote)}</span> tickers'
    f'</div>',
    unsafe_allow_html=True,
)

# Mostra prévia do lote
if lote:
    with st.expander("📋 tickers neste lote", expanded=False):
        cols_prev = st.columns(6)
        for ci, tk in enumerate(lote):
            cols_prev[ci % 6].caption(tk.replace(".SA", ""))

st.markdown("<br>", unsafe_allow_html=True)

# ── Diagnóstico rápido ────────────────────────────────────────────────────────
with st.expander("🔍 diagnóstico (testar FMP + Supabase antes de rodar)", expanded=False):
    ticker_teste = st.text_input("ticker de teste:", value="AAPL",
                                 help="EUA sem sufixo. Para BR: PETR4 (sem .SA)")
    if st.button("🧪 testar agora", key="btn_diag"):
        from utils.fmp_client import _get
        from database.supabase_client import get_supabase

        col_d1, col_d2 = st.columns(2)

        # Teste FMP
        with col_d1:
            st.markdown("**FMP — /ratios (quarterly)**")
            try:
                r = _get(f"ratios/{ticker_teste.upper().replace('.SA','')}", {"period": "quarter", "limit": 3})
                if r and isinstance(r, list) and len(r) > 0:
                    st.success(f"✅ {len(r)} registros | primeiro: {r[0].get('date')}")
                    st.json({"amostra": r[0]}, expanded=False)
                elif isinstance(r, list) and len(r) == 0:
                    st.warning("⚠️ FMP retornou lista vazia — quota esgotada ou ticker não coberto")
                else:
                    st.error(f"❌ resposta inesperada: {r}")
            except Exception as e:
                st.error(f"❌ exceção: {e}")

        # Teste Supabase insert
        with col_d2:
            st.markdown("**Supabase — insert de teste**")
            try:
                sb = get_supabase()
                payload = [{
                    "ticker": "_BACKFILL_TEST_",
                    "score": 42,
                    "calculado_em": "2000-01-01",
                }]
                sb.table("health_score_history").insert(payload).execute()
                # Limpa o registro de teste
                sb.table("health_score_history").delete().eq("ticker", "_BACKFILL_TEST_").execute()
                st.success("✅ insert + delete OK — Supabase funcionando")
            except Exception as e:
                st.error(f"❌ insert falhou: {e}")

st.markdown("<br>", unsafe_allow_html=True)

# Botão de execução
col_btn1, col_btn2, _ = st.columns([2, 2, 4])
btn_run   = col_btn1.button("▶ iniciar backfill", type="primary",
                             use_container_width=True, disabled=not lote)
btn_clear = col_btn2.button("🗑 limpar cache", use_container_width=True,
                             help="Força recarregar cobertura do banco")

if btn_clear:
    st.cache_data.clear()
    st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# EXECUÇÃO
# ──────────────────────────────────────────────────────────────────────────────
if btn_run and lote:
    st.markdown("---")
    section_title("⚙️ processando…")

    # Constrói timeline macro uma vez
    with st.spinner("carregando contexto macro histórico (Selic + VIX)…"):
        macro_tl = _build_macro_timeline()
    st.success(f"✅ macro timeline: {len(macro_tl):,} dias carregados")

    # Progress bar e log
    barra    = st.progress(0, text="iniciando…")
    log_area = st.empty()
    resumo   = st.empty()

    total_inseridos = 0
    total_skipped   = 0
    erros           = []
    inicio_run      = time.time()

    for idx, ticker in enumerate(lote, 1):
        pct  = idx / len(lote)
        barra.progress(pct, text=f"{idx}/{len(lote)} — {ticker.replace('.SA', '')}")

        status_ph = log_area.empty()
        try:
            n_ins, n_skip, diag = _processar_ticker_st(ticker, macro_tl, status_ph)
            total_inseridos += n_ins
            total_skipped   += n_skip

            if n_ins > 0:
                log_area.success(
                    f"✅ `{ticker.replace('.SA','')}` — {n_ins} pts inseridos | {diag}"
                )
            elif "sem dados" in diag or "quota" in diag:
                log_area.warning(
                    f"⚠️ `{ticker.replace('.SA','')}` — {diag}"
                )
            else:
                log_area.info(
                    f"ℹ️ `{ticker.replace('.SA','')}` — {diag}"
                )
        except Exception as e:
            erros.append(ticker)
            log_area.error(f"❌ `{ticker.replace('.SA','')}` — exceção: {e}")
            logger.error(f"[backfill] {ticker}: {e}", exc_info=True)

        # Atualiza resumo corrente
        elapsed       = time.time() - inicio_run
        restantes_lote = len(lote) - idx
        eta_s          = max(0, (elapsed / idx) * restantes_lote) if idx > 0 else 0
        eta_str        = f"~{int(eta_s)}s" if restantes_lote > 0 else "concluído"
        resumo.markdown(
            f'<div style="font-family:Courier New; font-size:0.78rem; '
            f'color:#555; padding:4px 0;">'
            f'inseridos: <b style="color:#00C853;">{total_inseridos}</b> pontos | '
            f'já existiam: {total_skipped} | '
            f'erros: <b style="color:#FF1744;">{len(erros)}</b> | '
            f'decorrido: {int(elapsed)}s | '
            f'eta: {eta_str}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Resumo final
    barra.progress(1.0, text="concluído!")
    elapsed_total = time.time() - inicio_run

    st.markdown("---")
    st.success(
        f"🎉 **backfill concluído!**  \n"
        f"- **{total_inseridos:,}** pontos históricos inseridos  \n"
        f"- **{total_skipped:,}** já existiam no banco  \n"
        f"- **{len(lote) - len(erros)}** tickers processados com sucesso  \n"
        f"- Tempo total: **{int(elapsed_total)}s** "
        f"({elapsed_total/len(lote):.1f}s/ticker)  \n"
        + (f"- ⚠️ Erros: {', '.join(erros)}" if erros else "")
    )

    if pendentes[batch_size:]:
        restantes = len(pendentes) - batch_size
        st.info(
            f"📋 ainda faltam **{restantes}** tickers. "
            f"Clique em **▶ iniciar backfill** novamente para continuar."
        )

    # Invalida cache de cobertura para atualizar o dashboard
    st.cache_data.clear()
    time.sleep(1)
    st.rerun()
