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
from utils.components import page_header, section_title, inject_ui_enhancements, show_toast
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

page_header("🕐 backfill histórico", "popula 10 anos de health scores via FMP · CVM · yfinance.")
inject_ui_enhancements()
try:
    from utils.themes import render_theme_switcher_sidebar
    render_theme_switcher_sidebar()
except Exception:
    pass

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


def _ratios_yf(
    ticker_yf: str, anos: int = 4
) -> tuple[list[tuple[str, dict, dict]], int, str]:
    """
    Fallback para tickers BR sem cobertura FMP.
    Tenta dados trimestrais primeiro (até anos*4 períodos, ~12 trimestres),
    depois cai para anuais (até anos períodos).
    Dados de fluxo trimestrais são anualizados (×4) para compatibilidade com _score_offline.
    Retorna (list[(data_str, ratios_dict, km_dict)], yoy_offset, granular_str).
    """
    import yfinance as yf

    def _get_attr(tk, *names):
        """Tenta vários nomes de atributo — compatível com yfinance 0.2.x e 1.x."""
        for name in names:
            try:
                v = getattr(tk, name, None)
                if v is not None and not (hasattr(v, 'empty') and v.empty):
                    return v
            except Exception:
                continue
        return None

    try:
        tk   = yf.Ticker(ticker_yf)

        # tk.info pode ser lento/falhar em 1.x — isola para não abortar tudo
        info = {}
        try:
            info = tk.info or {}
        except Exception:
            pass

        # yfinance 1.x: quarterly_income_stmt; 0.2.x: quarterly_financials
        fin = _get_attr(tk, "quarterly_income_stmt", "quarterly_financials")
        bal = _get_attr(tk, "quarterly_balance_sheet")
        cf  = _get_attr(tk, "quarterly_cashflow")
        is_quarterly = fin is not None and not fin.empty

        if not is_quarterly:
            # fallback anual — mesmos aliases
            fin = _get_attr(tk, "income_stmt", "financials")
            bal = _get_attr(tk, "balance_sheet")
            cf  = _get_attr(tk, "cashflow")
    except Exception:
        return [], 1, "anual (yfinance)"

    if fin is None or fin.empty:
        return [], 1, "anual (yfinance)"

    shares = (
        info.get("sharesOutstanding")
        or info.get("impliedSharesOutstanding")
        or info.get("floatShares") or 0
    )

    # Fator de anualização: dados trimestrais precisam de ×4 para ROE/PE ficarem na escala certa
    ann   = 4.0 if is_quarterly else 1.0
    n_per = anos * 4 if is_quarterly else anos   # períodos a ler
    yoy_offset  = 4 if is_quarterly else 1
    granular    = "trimestral (yfinance)" if is_quarterly else "anual (yfinance)"

    # Preços mensais para calcular PE/PB na data fiscal
    hist_px = pd.Series(dtype=float)
    try:
        hist_px = tk.history(period=f"{anos + 2}y", interval="1mo")["Close"].dropna()
        if getattr(hist_px.index, "tz", None) is not None:
            hist_px.index = hist_px.index.tz_localize(None)
    except Exception:
        pass

    def _r(df, *names):
        """Primeira linha cujo nome (sem espaço/case) coincide."""
        if df is None or df.empty:
            return None
        for name in names:
            key = name.lower().replace(" ", "").replace("_", "")
            for idx in df.index:
                if str(idx).lower().replace(" ", "").replace("_", "") == key:
                    return df.loc[idx]
        return None

    def _v(series, col):
        if series is None or col not in series.index:
            return None
        v = series[col]
        try:
            import numpy as np
            return None if np.isnan(float(v)) else float(v)
        except Exception:
            return None

    cols       = list(fin.columns)[:n_per]   # mais recentes primeiro
    resultados = []

    for i, col in enumerate(cols):
        try:
            dt_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)[:10]

            # ── Demonstração de resultado (anualizado se trimestral) ──
            net_income  = _v(_r(fin, "Net Income", "Net Income Common Stockholders"), col)
            revenue     = _v(_r(fin, "Total Revenue", "Revenue"), col)
            gross_pft   = _v(_r(fin, "Gross Profit"), col)
            ebitda_v    = _v(_r(fin, "EBITDA"), col)
            ebit        = _v(_r(fin, "EBIT", "Operating Income"), col)
            interest_ex = _v(_r(fin, "Interest Expense"), col)

            if ann != 1.0:
                net_income  = net_income  * ann if net_income  is not None else None
                revenue     = revenue     * ann if revenue     is not None else None
                gross_pft   = gross_pft   * ann if gross_pft   is not None else None
                ebitda_v    = ebitda_v    * ann if ebitda_v    is not None else None
                ebit        = ebit        * ann if ebit        is not None else None
                interest_ex = interest_ex * ann if interest_ex is not None else None

            # ── Balanço (ponto no tempo — não anualizar) ──────────────
            equity = tot_assets = tot_debt = cash = None
            cur_assets = cur_liab = None
            if bal is not None and not bal.empty and col in bal.columns:
                equity     = _v(_r(bal, "Stockholders Equity", "Common Stock Equity",
                                      "Total Stockholder Equity"), col)
                tot_assets = _v(_r(bal, "Total Assets"), col)
                tot_debt   = _v(_r(bal, "Total Debt", "Long Term Debt"), col) or 0
                cash       = _v(_r(bal, "Cash And Cash Equivalents", "Cash"), col) or 0
                cur_assets = _v(_r(bal, "Current Assets", "Total Current Assets"), col)
                cur_liab   = _v(_r(bal, "Current Liabilities", "Total Current Liabilities"), col)

            # ── Fluxo de caixa (anualizado se trimestral) ─────────────
            fcf = op_cf = None
            if cf is not None and not cf.empty and col in cf.columns:
                op_cf_raw = _v(_r(cf, "Operating Cash Flow",
                                      "Total Cash From Operating Activities"), col)
                capex_raw = _v(_r(cf, "Capital Expenditure", "Capital Expenditures"), col)
                if op_cf_raw is not None:
                    op_cf = op_cf_raw * ann
                if op_cf_raw and capex_raw:
                    fcf = (op_cf_raw + capex_raw) * ann   # capex é negativo no yfinance

            # ── Preço na data fiscal ──────────────────────────────────
            price = None
            if not hist_px.empty:
                target = pd.Timestamp(dt_str)
                diffs  = (hist_px.index - target).map(abs)
                price  = float(hist_px.iloc[diffs.argmin()])

            # ── Ratios derivados (formato decimal FMP) ────────────────
            # margens: razão entre fluxos → anualização cancela, está correto
            roe        = (net_income / equity)     if (net_income and equity and equity > 0)        else None
            roa        = (net_income / tot_assets) if (net_income and tot_assets and tot_assets > 0) else None
            net_margin = (net_income / revenue)    if (net_income and revenue and revenue != 0)      else None
            gross_mgn  = (gross_pft  / revenue)    if (gross_pft  and revenue and revenue != 0)      else None
            at         = (revenue    / tot_assets) if (revenue    and tot_assets and tot_assets > 0) else None
            cr         = (cur_assets / cur_liab)   if (cur_assets and cur_liab and cur_liab > 0)     else None
            de         = (tot_debt   / equity)     if (tot_debt   and equity and equity > 0)         else None
            icr        = (ebit / abs(interest_ex)) if (ebit and interest_ex and interest_ex != 0)   else None
            fcf_op     = (fcf / op_cf)             if (fcf and op_cf and op_cf != 0)                else None

            mktcap = (price * shares) if (price and shares) else None
            pe  = (mktcap / net_income) if (mktcap and net_income and net_income > 0) else None
            pb  = (mktcap / equity)     if (mktcap and equity and equity > 0)         else None
            evm = None
            if mktcap and ebitda_v and ebitda_v > 0:
                ev  = mktcap + (tot_debt or 0) - (cash or 0)
                evm = ev / ebitda_v

            # ── KM fields ─────────────────────────────────────────────
            roic      = (ebit / (tot_debt + equity)) if (ebit and tot_debt is not None and equity and (tot_debt + equity) > 0) else None
            nd_eb     = ((tot_debt - cash) / ebitda_v) if (tot_debt is not None and cash is not None and ebitda_v and ebitda_v > 0) else None
            fcf_yield = (fcf / mktcap) if (fcf and mktcap and mktcap > 0) else None

            # YoY: comparar com mesmo período há yoy_offset períodos atrás
            rev_growth = eps_growth = None
            if i + yoy_offset < len(cols):
                col_prev  = cols[i + yoy_offset]
                rev_prev  = _v(_r(fin, "Total Revenue", "Revenue"), col_prev)
                ni_prev   = _v(_r(fin, "Net Income", "Net Income Common Stockholders"), col_prev)
                if revenue and rev_prev and rev_prev != 0:
                    rev_growth = (revenue - rev_prev * ann) / abs(rev_prev * ann)
                if net_income and ni_prev and ni_prev != 0:
                    eps_growth = (net_income - ni_prev * ann) / abs(ni_prev * ann)

            # Sanidade
            if pe  and (pe  <= 0 or pe  > 500): pe  = None
            if pb  and (pb  <= 0 or pb  > 100): pb  = None
            if evm and (evm <= 0 or evm > 300): evm = None

            ratios = {
                "date":                               dt_str,
                "returnOnEquity":                     roe,
                "returnOnAssets":                     roa,
                "netProfitMargin":                    net_margin,
                "grossProfitMargin":                  gross_mgn,
                "priceEarningsRatio":                 pe,
                "priceToBookRatio":                   pb,
                "enterpriseValueMultiple":            evm,
                "debtEquityRatio":                    de,
                "currentRatio":                       cr,
                "interestCoverage":                   icr,
                "freeCashFlowOperatingCashFlowRatio": fcf_op,
                "assetTurnover":                      at,
            }
            km = {
                "date":              dt_str,
                "roic":              roic,
                "netDebtToEBITDA":   nd_eb,
                "freeCashFlowYield": fcf_yield,
                "debtToEquity":      de,
                "currentRatio":      cr,
                "revenueGrowth":     rev_growth,
                "epsgrowth":         eps_growth,
            }
            resultados.append((dt_str, ratios, km))
        except Exception:
            continue

    return resultados, yoy_offset, granular


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
) -> tuple[int, int, str, str]:
    """
    Processa um ticker dentro do contexto Streamlit.
    Retorna (n_inseridos, n_skipped, diagnostico, fonte_usada).
    fonte_usada: "FMP-q" | "FMP-a" | "CVM/ITR" | "CVM/DFP" | "YF-q" | "YF-a" | "—"
    """
    import yfinance as yf
    from utils.fmp_client import get_ratios_trimestrais, get_key_metrics_trimestrais, _get
    from database.db import registrar_historico_score_batch, get_datas_historico_score

    is_br       = ticker_yf.endswith(".SA")
    tk_fmp      = ticker_yf.replace(".SA", "").upper()
    diag        = ""
    fonte_usada = "—"

    status_placeholder.write(f"🔄 `{tk_fmp}` — buscando FMP (quarterly)…")

    # ── 1. Trimestral ─────────────────────────────────────────────────────────
    ratios_list = get_ratios_trimestrais(tk_fmp, limit=40)
    time.sleep(0.4)
    km_list     = get_key_metrics_trimestrais(tk_fmp, limit=40)
    time.sleep(0.4)
    yoy_offset  = 4
    granular    = "trimestral"
    if ratios_list:
        fonte_usada = "FMP-q"

    # ── 2. Fallback anual ─────────────────────────────────────────────────────
    if not ratios_list:
        status_placeholder.write(f"🔄 `{tk_fmp}` — quarterly vazio, tentando annual…")
        ratios_list = _get("ratios", {"symbol": tk_fmp, "limit": 10}) or []
        time.sleep(0.4)
        km_list     = _get("key-metrics", {"symbol": tk_fmp, "limit": 10}) or []
        time.sleep(0.4)
        yoy_offset  = 1
        granular    = "anual"
        if ratios_list:
            fonte_usada = "FMP-a"

    # ── 3. CVM — fonte oficial para ativos BR (10 anos de DFP/ITR) ──────────────
    if not ratios_list and is_br:
        cvm_nota = ""
        try:
            from utils.cvm_client import get_historico_cvm, get_cvm_code
            cd_cvm = get_cvm_code(ticker_yf)
            if cd_cvm:
                status_placeholder.write(
                    f"🏛️ `{tk_fmp}` — CVM CD={cd_cvm}, baixando ZIPs…"
                )
                cvm_data, cvm_yoy, cvm_gran = get_historico_cvm(ticker_yf, anos=10)
                if cvm_data:
                    ratios_list = [r for _, r, _ in cvm_data]
                    km_list     = [k for _, _, k in cvm_data]
                    yoy_offset  = cvm_yoy
                    granular    = cvm_gran
                    fonte_usada = "CVM/ITR" if "itr" in cvm_gran.lower() else "CVM/DFP"
                    cvm_nota    = f"CVM OK: {len(ratios_list)}p"
                else:
                    cvm_nota = f"CVM CD={cd_cvm} sem dados"
            else:
                cvm_nota = "CVM: sem mapeamento"
        except Exception as _e:
            logger.warning(f"[backfill] CVM falhou para {tk_fmp}: {_e}")
            cvm_nota = f"CVM err: {str(_e)[:35]}"
        if cvm_nota and not ratios_list:
            diag = cvm_nota  # mostra motivo na coluna "nota" da tabela

    # ── 4. Fallback yfinance (BR sem CVM + todos os EUA sem FMP) ─────────────
    if not ratios_list:
        msg = "CVM sem dados" if is_br else "FMP vazio"
        status_placeholder.write(f"🔄 `{tk_fmp}` — {msg}, tentando yfinance (trimestral → anual)…")
        yf_data, yf_yoy, yf_gran = _ratios_yf(ticker_yf, anos=4)
        if yf_data:
            ratios_list = [r for _, r, _ in yf_data]
            km_list     = [k for _, _, k in yf_data]
            yoy_offset  = yf_yoy
            granular    = yf_gran
            fonte_usada = "YF-q" if "trimestral" in yf_gran else "YF-a"

    if not ratios_list:
        # Distingue quota/transitório de ausência real de cobertura
        # yfinance 1.x: se chegou aqui após tentar income_stmt, provável ausência real
        diag = "sem dados (não coberto por nenhuma fonte)"
        status_placeholder.write(f"⚠️ `{tk_fmp}` — {diag}")
        # Sentinel persistente: evita reprocessar indefinidamente tickers sem cobertura real.
        # Para retentativas (ex: quota FMP voltou), use o botão "retry sem dados".
        try:
            registrar_historico_score_batch(
                [{"ticker": ticker_yf, "score": 0, "calculado_em": "2000-01-01"}],
                ignorar_existentes=True,
            )
        except Exception:
            pass
        return 0, 0, diag, fonte_usada

    diag = f"{len(ratios_list)} períodos ({granular}), km: {len(km_list)}"
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
        return 0, skipped, diag, fonte_usada

    # ── Salva no Supabase ─────────────────────────────────────────────────────
    status_placeholder.write(
        f"💾 `{tk_fmp}` — inserindo {len(registros)} pontos no Supabase…"
    )
    try:
        n = registrar_historico_score_batch(registros, ignorar_existentes=False)
        diag += f" | inseridos: {n}"
        return n, skipped, diag, fonte_usada
    except Exception as e:
        diag += f" | ERRO INSERT: {e}"
        status_placeholder.write(f"❌ `{tk_fmp}` — falha no insert: {e}")
        logger.error(f"[backfill] insert {tk_fmp}: {e}", exc_info=True)
        return 0, skipped, diag, fonte_usada


# ──────────────────────────────────────────────────────────────────────────────
# DASHBOARD DE COBERTURA
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _cobertura_atual() -> pd.DataFrame:
    """Retorna DataFrame com cobertura atual por ticker."""
    from database.supabase_client import get_supabase
    try:
        sb   = get_supabase()
        rows = sb.table("health_score_history").select("ticker, calculado_em, score").execute().data or []
        if not rows:
            return pd.DataFrame(columns=["ticker", "pontos", "inicio", "fim", "sem_dados"])
        df = pd.DataFrame(rows)
        # Sentinels "sem dados": score=0, calculado_em=2000-01-01 — excluir do cálculo de datas
        df["calculado_em"] = pd.to_datetime(df["calculado_em"], format="ISO8601", utc=True)
        df_real  = df[~((df["score"] == 0) & (df["calculado_em"].dt.year == 2000))]
        df_nd    = df[ ((df["score"] == 0) & (df["calculado_em"].dt.year == 2000))]
        nd_set   = set(df_nd["ticker"].tolist())

        agg = df.groupby("ticker")["calculado_em"].agg(
            pontos="count",
        ).reset_index()
        # Datas reais (ignora sentinel)
        if not df_real.empty:
            agg_real = df_real.groupby("ticker")["calculado_em"].agg(
                inicio="min", fim="max"
            ).reset_index()
            agg = agg.merge(agg_real, on="ticker", how="left")
        else:
            agg["inicio"] = pd.NaT
            agg["fim"]    = pd.NaT
        agg["inicio"] = pd.to_datetime(agg.get("inicio")).dt.strftime("%Y-%m-%d")
        agg["fim"]    = pd.to_datetime(agg.get("fim")).dt.strftime("%Y-%m-%d")
        agg["sem_dados"] = agg["ticker"].isin(nd_set)
        return agg.sort_values("pontos", ascending=False)
    except Exception as e:
        logger.warning(f"[backfill] falha ao buscar cobertura: {e}")
        return pd.DataFrame(columns=["ticker", "pontos", "inicio", "fim", "sem_dados"])


# ── UI ────────────────────────────────────────────────────────────────────────

# Se backfill acabou de rodar, força releitura de cobertura antes de montar o lote
if st.session_state.pop("backfill_just_completed", False):
    _cobertura_atual.clear()

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

# "cobertos" = têm dados reais (excluir sentinels "sem dados")
_has_sem_dados = "sem_dados" in cob.columns
cob_eua_ok = cob_eua[~cob_eua["sem_dados"]] if _has_sem_dados else cob_eua
cob_br_ok  = cob_br[~cob_br["sem_dados"]]   if _has_sem_dados else cob_br

m1, m2, m3, m4 = st.columns(4)
with m1:
    n_eua = len(cob_eua_ok)
    n_eua_nd = len(cob_eua) - n_eua
    delta_eua = f"{n_eua/total_eua*100:.0f}%" + (f" | {n_eua_nd} sem dados" if n_eua_nd else "")
    st.metric("tickers EUA cobertos", f"{n_eua} / {total_eua}",
              delta_eua if total_eua else "—")
with m2:
    n_br = len(cob_br_ok)
    n_br_nd = len(cob_br) - n_br
    delta_br = f"{n_br/total_br*100:.0f}%" + (f" | {n_br_nd} sem dados" if n_br_nd else "")
    st.metric("tickers BR cobertos", f"{n_br} / {total_br}",
              delta_br if total_br else "—")
with m3:
    # Exclui pontos sentinel (score=0, 2000-01-01) da contagem total
    cob_com_dados = cob[~cob["sem_dados"]] if _has_sem_dados else cob
    total_pts = int(cob_com_dados["pontos"].sum()) if not cob_com_dados.empty else 0
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
# SYNC RÁPIDO — SCREENER / RESEARCH  (fundamentais atuais → api_cache)
# ──────────────────────────────────────────────────────────────────────────────

with st.expander("🔄 sincronização de fundamentos — screener / research", expanded=False):
    st.info(
        "Sincroniza dados atuais (P/L, ROE, DY, setor…) usados pelo Discovery e Screener.\n\n"
        "**B3:** Fundamentus scraper + yfinance como fallback.  \n"
        "**EUA:** FMP (ratios-ttm + profile) + yfinance como fallback.  \n"
        "Não consome quota FMP além do necessário.",
        icon="ℹ️",
    )
    _sc1, _sc2 = st.columns(2)
    with _sc1:
        if st.button("🇧🇷 sync B3 + FIIs", type="primary",
                     use_container_width=True, key="btn_backfill_sync_b3"):
            st.session_state["run_backfill_sync_b3"] = True
    with _sc2:
        if st.button("🇺🇸 sync EUA", type="primary",
                     use_container_width=True, key="btn_backfill_sync_us"):
            st.session_state["run_backfill_sync_us"] = True

    # ── Handler: sync B3 + FIIs ───────────────────────────────────────────────
    if st.session_state.get("run_backfill_sync_b3"):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from utils.scrapers import buscar_dados_b3
        from database.db import salvar_fundamento_cache
        from utils.tickers import FII_TODOS

        _b3_lista = list(dict.fromkeys(SCREENER_B3 + FII_TODOS))
        _bar_b3   = st.progress(0, text="iniciando sync B3…")
        _log_b3   = st.empty()

        def _sync_b3_item(t):
            try:
                dados = buscar_dados_b3(t)
                salvar_fundamento_cache(t, dados)
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=8) as _ex_b3:
            _futs_b3 = {_ex_b3.submit(_sync_b3_item, t): t for t in _b3_lista}
            _total_b3 = len(_b3_lista)
            _done_b3  = 0
            for _fut in as_completed(_futs_b3):
                _done_b3 += 1
                _pct_b3 = _done_b3 / _total_b3
                _tk_b3  = _futs_b3[_fut]
                _bar_b3.progress(_pct_b3, text=f"b3: {_tk_b3} ({_done_b3}/{_total_b3})")
                _log_b3.caption(f"→ {_tk_b3} {'✅' if _fut.result() else '❌'}")

        st.session_state["run_backfill_sync_b3"] = False
        show_toast(f"sync B3 concluído — {_total_b3} ativos processados", "success", 5000)
        st.cache_data.clear()
        st.rerun()

    # ── Handler: sync EUA ─────────────────────────────────────────────────────
    if st.session_state.get("run_backfill_sync_us"):
        import yfinance as yf
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from database.db import salvar_fundamento_cache
        from utils.formatters import traduzir_setor
        from utils.tickers import SCREENER_US, XSTOCKS_INDICES, mapear_ticker_base
        from utils.fmp_client import (
            get_profile, get_financial_scores, get_analyst_grades,
            _get as fmp_get, FMP_MAX_LIMIT
        )

        _us_lista = list({mapear_ticker_base(t) for t in SCREENER_US + XSTOCKS_INDICES})
        _bar_us   = st.progress(0, text="iniciando sync EUA…")
        _log_us   = st.empty()

        def _sync_us_item(t_base):
            try:
                dados = {}

                # Fonte 1: FMP (ratios-ttm, profile, financial-scores)
                try:
                    _rt = fmp_get("ratios-ttm", {"symbol": t_base})
                    if isinstance(_rt, list) and _rt:
                        r = _rt[0]
                        pe = r.get("priceToEarningsRatioTTM") or r.get("peRatioTTM")
                        pb = r.get("priceToBookRatioTTM") or r.get("pbRatioTTM")
                        dy = r.get("dividendYieldTTM")
                        margem = r.get("netProfitMarginTTM")
                        ev_ebitda = r.get("enterpriseValueMultipleTTM") or r.get("enterpriseValueOverEBITDATTM")

                        if pe is not None: dados["p/l"] = float(pe)
                        if pb is not None: dados["p/vp"] = float(pb)
                        if dy is not None:
                            dados["dy%"] = float(dy) * 100 if float(dy) < 1 else float(dy)
                        if margem is not None:
                            dados["margem%"] = float(margem) * 100 if abs(float(margem)) < 2 else float(margem)
                        if ev_ebitda is not None: dados["ev/ebitda"] = float(ev_ebitda)
                except Exception:
                    pass

                # FMP key-metrics para ROE
                try:
                    _km = fmp_get("key-metrics", {"symbol": t_base, "limit": 1})
                    if isinstance(_km, list) and _km:
                        roe_m = _km[0].get("returnOnEquity") or _km[0].get("roe")
                        if roe_m is not None:
                            dados["roe%"] = float(roe_m) * 100 if abs(float(roe_m)) < 2 else float(roe_m)
                except Exception:
                    pass

                # FMP profile para nome/setor/market_cap
                try:
                    prof = get_profile(t_base)
                    if prof:
                        dados["nome"] = prof.get("nome", t_base)
                        dados["setor"] = traduzir_setor(prof.get("setor", "—"))
                        dados["market_cap"] = prof.get("market_cap")
                        dados["beta"] = prof.get("beta")
                        dados["preco"] = prof.get("preco")
                except Exception:
                    pass

                # Fallback: yfinance se FMP não retornou múltiplos críticos
                _temMultiplos = all(k in dados for k in ("p/l", "p/vp", "roe%"))
                if not _temMultiplos:
                    try:
                        info = yf.Ticker(t_base).info or {}
                        if "p/l" not in dados:
                            pe_yf = info.get("trailingPE") or info.get("forwardPE")
                            if pe_yf is not None: dados["p/l"] = float(pe_yf)
                        if "p/vp" not in dados:
                            pb_yf = info.get("priceToBook")
                            if pb_yf is not None: dados["p/vp"] = float(pb_yf)
                        if "roe%" not in dados:
                            roe_yf = info.get("returnOnEquity")
                            if roe_yf is not None: dados["roe%"] = float(roe_yf) * 100
                        if "margem%" not in dados:
                            mrg_yf = info.get("profitMargins")
                            if mrg_yf is not None: dados["margem%"] = float(mrg_yf) * 100
                        if "dy%" not in dados:
                            dy_yf = info.get("dividendYield")
                            dados["dy%"] = (float(dy_yf) * 100) if dy_yf is not None else 0
                        if "ev/ebitda" not in dados:
                            ev_yf = info.get("enterpriseToEbitda")
                            if ev_yf is not None: dados["ev/ebitda"] = float(ev_yf)
                        if "nome" not in dados:
                            dados["nome"] = info.get("shortName", t_base)
                        if "setor" not in dados:
                            dados["setor"] = traduzir_setor(info.get("sector", "—"))
                        if "market_cap" not in dados:
                            dados["market_cap"] = info.get("marketCap")
                        if "beta" not in dados:
                            dados["beta"] = info.get("beta")
                    except Exception:
                        pass

                if not dados:
                    return False

                dados["ticker"] = t_base
                dados["data_quality"] = 85 if dados.get("p/l") and dados.get("roe%") else 60
                salvar_fundamento_cache(t_base, dados)
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=5) as _ex_us:
            _futs_us  = {_ex_us.submit(_sync_us_item, t): t for t in _us_lista}
            _total_us = len(_us_lista)
            _done_us  = 0
            for _fut in as_completed(_futs_us):
                _done_us += 1
                _pct_us  = _done_us / _total_us
                _tk_us   = _futs_us[_fut]
                _bar_us.progress(_pct_us, text=f"eua: {_tk_us} ({_done_us}/{_total_us})")
                _log_us.caption(f"→ {_tk_us} {'✅' if _fut.result() else '❌'}")

        st.session_state["run_backfill_sync_us"] = False
        show_toast(f"sync EUA concluído — {_total_us} ativos processados", "success", 5000)
        st.cache_data.clear()
        st.rerun()

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
        "pular tickers já processados",
        value=True,
        help="Evita re-processar tickers com dados no banco ou já rodados nesta sessão.",
    )

# Monta lista de tickers pendentes
if mercado_sel == "EUA":
    todos_tickers = list(SCREENER_US)
elif mercado_sel == "Brasil (B3)":
    todos_tickers = list(SCREENER_B3)
else:
    todos_tickers = list(SCREENER_US) + list(SCREENER_B3)

# Filtra cobertura
if pular_cobertos:
    # 1. Tickers com ≥4 pontos no banco
    completos_db: set[str] = set()
    if not cob.empty:
        # >= 1: qualquer ticker com ao menos 1 registro (inclusive sentinel "sem dados")
        # fica fora do lote — evita re-processar tickers que já foram tentados
        completos_db = set(cob[cob["pontos"] >= 1]["ticker"].tolist())
        # BR tickers são salvos como "PETR4.SA" no banco mas listados sem sufixo em SCREENER_B3
        completos_db |= {t.replace(".SA", "") for t in completos_db}
    # 2. Tickers já processados nesta sessão (persiste entre reruns)
    ja_processados: set[str] = st.session_state.get("backfill_ja_processados", set())
    completos = completos_db | ja_processados
    pendentes = [t for t in todos_tickers if t not in completos
                 and t.replace(".SA", "") not in completos]
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
                r = _get("ratios", {"symbol": ticker_teste.upper().replace('.SA',''), "period": "quarter", "limit": 3})
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

    st.markdown("---")
    st.markdown("**🏛️ Diagnóstico CVM** — testa acesso aos ZIPs e resolução de ticker BR")
    ticker_cvm_teste = st.text_input(
        "ticker BR para testar CVM:", value="BBAS3",
        help="sem sufixo .SA",
        key="diag_cvm_tk",
    )
    if st.button("🏛️ testar CVM agora", key="btn_diag_cvm"):
        import datetime as _dt
        from utils.cvm_client import probe_url, get_cvm_code, _DFP_URL, _ITR_URL, _parse_zip

        tk_cvm = ticker_cvm_teste.strip().upper().replace(".SA", "")
        ano_ref = _dt.date.today().year - 1  # ano anterior — mais provável de existir

        # 1. CD_CVM
        cd = get_cvm_code(tk_cvm)
        if cd:
            st.success(f"✅ CD_CVM = **{cd}** para {tk_cvm}")
        else:
            st.error(f"❌ CD_CVM não encontrado para {tk_cvm}")

        # 2. Probe URLs
        for tipo, tmpl in [("DFP", _DFP_URL), ("ITR", _ITR_URL)]:
            url = tmpl.format(year=ano_ref)
            ok, msg = probe_url(url)
            if ok:
                st.success(f"✅ {tipo} {ano_ref}: {msg}  \n`{url}`")
            else:
                st.error(f"❌ {tipo} {ano_ref}: {msg}  \n`{url}`")

        # 3. Tenta parsear DFP (lento — baixa o ZIP)
        if cd:
            with st.spinner(f"baixando DFP {ano_ref} (~60s)…"):
                dfs = _parse_zip(_DFP_URL, ano_ref)
            if dfs:
                st.success(f"✅ DFP {ano_ref} parseado: {list(dfs.keys())}")
                for tipo, df in dfs.items():
                    n_emp = df["CD_CVM"].nunique() if "CD_CVM" in df.columns else "?"
                    n_lin_emp = len(df[df["CD_CVM"].str.strip() == cd]) if "CD_CVM" in df.columns else 0
                    st.info(
                        f"  **{tipo}**: {len(df):,} linhas, {n_emp} empresas | "
                        f"linhas p/ CD_CVM={cd}: **{n_lin_emp}**"
                    )
            else:
                st.error(f"❌ DFP {ano_ref}: download/parse falhou — veja logs do servidor")

st.markdown("<br>", unsafe_allow_html=True)

# Botão de execução
col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 2])
btn_run   = col_btn1.button("▶ iniciar backfill", type="primary",
                             use_container_width=True, disabled=not lote)
btn_clear = col_btn2.button("🗑 limpar cache", use_container_width=True,
                             help="Força recarregar cobertura do banco")
btn_reset_nd = col_btn3.button(
    "🔄 retry 'sem dados'",
    use_container_width=True,
    help="Remove marcadores de 'sem dados' para retentar tickers que falharam por quota/timeout",
)

if btn_clear:
    st.cache_data.clear()
    st.rerun()

if btn_reset_nd:
    # Remove registros sentinel (score=0, calculado_em=2000-01-01) para recolocar no lote
    try:
        from database.supabase_client import get_supabase as _get_sb
        _sb = _get_sb()
        _sb.table("health_score_history") \
            .delete() \
            .eq("calculado_em", "2000-01-01") \
            .eq("score", 0) \
            .execute()
        st.cache_data.clear()
        show_toast("tickers 'sem dados' removidos do cache — serão retentados no próximo lote", "success", 4000)
        st.rerun()
    except Exception as _e:
        st.error(f"erro ao resetar: {_e}")

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

    # Progress bar, status do ticker atual e log acumulativo
    barra     = st.progress(0, text="iniciando…")
    status_ph = st.empty()   # linha de status do ticker em processamento
    resumo    = st.empty()   # totais rodapé
    log_ph    = st.empty()   # tabela acumulativa de tickers processados

    total_inseridos = 0
    total_skipped   = 0
    erros           = []
    log_entries: list[dict] = []
    inicio_run      = time.time()

    def _render_log(entries: list[dict]) -> None:
        """Renderiza tabela HTML dos tickers já processados (mais recente no topo)."""
        if not entries:
            return
        linhas = []
        for e in reversed(entries):
            cor_ins = "var(--bull)" if e["n_ins"] > 0 else "var(--text-muted)"
            cor_tic = "var(--text-primary)"
            icone   = e["icone"]
            linhas.append(
                f"<tr>"
                f"<td style='padding:3px 10px 3px 4px;color:{cor_tic};font-weight:600'>"
                f"  {icone} {e['ticker']}</td>"
                f"<td style='padding:3px 8px;color:var(--accent)'>{e['fonte']}</td>"
                f"<td style='padding:3px 8px;color:var(--text-secondary)'>{e['periodos']}</td>"
                f"<td style='padding:3px 8px;color:{cor_ins};font-weight:600'>"
                f"  {e['n_ins']}</td>"
                f"<td style='padding:3px 4px;color:var(--text-muted);font-size:.75rem'>"
                f"  {e['nota']}</td>"
                f"</tr>"
            )
        html = (
            "<div style='max-height:320px;overflow-y:auto;margin-top:8px'>"
            "<table style='width:100%;border-collapse:collapse;"
            "font-family:var(--font-ui,sans-serif);font-size:.82rem'>"
            "<thead><tr style='border-bottom:1px solid var(--border-subtle)'>"
            "<th style='text-align:left;padding:4px 10px 4px 4px;color:var(--text-muted);"
            "font-weight:500'>ticker</th>"
            "<th style='text-align:left;padding:4px 8px;color:var(--text-muted);"
            "font-weight:500'>fonte</th>"
            "<th style='text-align:left;padding:4px 8px;color:var(--text-muted);"
            "font-weight:500'>períodos</th>"
            "<th style='text-align:left;padding:4px 8px;color:var(--text-muted);"
            "font-weight:500'>inseridos</th>"
            "<th style='text-align:left;padding:4px 4px;color:var(--text-muted);"
            "font-weight:500'>detalhe</th>"
            "</tr></thead>"
            f"<tbody>{''.join(linhas)}</tbody>"
            "</table></div>"
        )
        log_ph.markdown(html, unsafe_allow_html=True)

    for idx, ticker in enumerate(lote, 1):
        pct = idx / len(lote)
        barra.progress(pct, text=f"{idx}/{len(lote)} — {ticker.replace('.SA', '')}")

        try:
            n_ins, n_skip, diag, fonte = _processar_ticker_st(ticker, macro_tl, status_ph)
            total_inseridos += n_ins
            total_skipped   += n_skip

            # Determina nota curta para a tabela
            if n_ins > 0:
                icone = "✅"
                nota  = f"+{n_ins} pts"
            elif n_skip > 0:
                icone = "⏭️"
                nota  = f"skip {n_skip}"
            elif "sem dados" in diag or "quota" in diag:
                icone = "⚠️"
                nota  = "sem dados"
            else:
                icone = "ℹ️"
                nota  = "0 novos"

            # Extrai número de períodos do diag ("X períodos (...)")
            import re as _re
            m_per = _re.search(r"(\d+) períodos", diag)
            periodos = m_per.group(1) if m_per else "—"

        except Exception as e:
            erros.append(ticker)
            fonte, n_ins, n_skip = "—", 0, 0
            icone, nota, periodos = "❌", str(e)[:40], "—"
            logger.error(f"[backfill] {ticker}: {e}", exc_info=True)

        log_entries.append({
            "ticker":   ticker.replace(".SA", ""),
            "fonte":    fonte,
            "periodos": periodos,
            "n_ins":    n_ins,
            "icone":    icone,
            "nota":     nota,
        })

        # Limpa status do ticker atual e re-renderiza log
        status_ph.empty()
        _render_log(log_entries)

        # Atualiza totais
        elapsed        = time.time() - inicio_run
        restantes_lote = len(lote) - idx
        eta_s          = max(0, (elapsed / idx) * restantes_lote) if idx > 0 else 0
        eta_str        = f"~{int(eta_s)}s" if restantes_lote > 0 else "concluído"
        resumo.markdown(
            f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.78rem;'
            f'color:var(--text-muted);padding:4px 0 8px">'
            f'inseridos: <b style="color:var(--bull)">{total_inseridos}</b> pts · '
            f'skip: {total_skipped} · '
            f'erros: <b style="color:var(--bear)">{len(erros)}</b> · '
            f'{int(elapsed)}s decorridos · eta: {eta_str}'
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

    # Marca tickers como processados e sinaliza que a cobertura deve ser relida
    ja_proc = st.session_state.get("backfill_ja_processados", set())
    ja_proc.update(lote)
    ja_proc.update(t.replace(".SA", "") for t in lote)
    st.session_state["backfill_ja_processados"] = ja_proc
    st.session_state["backfill_just_completed"] = True

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
