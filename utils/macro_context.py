"""
utils/macro_context.py
Fetch leve do contexto macro atual para uso em qualquer página.
Garante que o session_state["macro_context"] esteja sempre atualizado.
"""
import streamlit as st
from utils.logger import get_logger

logger = get_logger(__name__)

# Valores de fallback (usados quando APIs estão indisponíveis)
#
# CONTRATO DE UNIDADE DO IPCA (importante — origem de bug histórico):
#   - 'ipca' / 'ipca_12m' → IPCA acumulado 12 meses (% a.a.). CHAVE CANÔNICA.
#     Use SEMPRE este valor em Fisher, selic real e yield real (FII/NTN-B).
#   - 'ipca_mensal'       → print do mês (série 433, % m). Apenas exibição /
#     cálculos mensais. NUNCA usar em fórmula anual.
SELIC_FALLBACK        = 14.75   # % a.a. — atualizar quando COPOM mudar
IPCA_FALLBACK         =  4.5    # % a.a. (acumulado 12m) — chave canônica anual
IPCA_12M_FALLBACK     =  4.5    # % a.a. — alias explícito de IPCA_FALLBACK
IPCA_MENSAL_FALLBACK  =  0.45   # % mês — print mensal (série 433)
VIX_FALLBACK          = 15.0    # pontos
TREASURY_10Y_FALLBACK =  4.5    # % a.a.


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_macro_rapido() -> dict:
    """
    Busca Selic, IPCA e VIX em paralelo.
    Cache de 1 hora — chamada barata (~300ms).
    Retorna dict com valores atuais e label de regime.
    """
    selic       = SELIC_FALLBACK
    ipca_12m    = IPCA_12M_FALLBACK      # acumulado 12m (anual) — chave canônica
    ipca_mensal = IPCA_MENSAL_FALLBACK   # print do mês (série 433)
    vix         = VIX_FALLBACK

    # Selic e IPCA via BCB SGS
    # 432 = Selic meta (% a.a.) | 433 = IPCA mês (%) | 13522 = IPCA acum. 12m (% a.a.)
    try:
        from bcb import sgs
        import datetime
        inicio = (datetime.datetime.today() - datetime.timedelta(days=120)).strftime('%Y-%m-%d')
        df_bcb = sgs.get({'selic': 432, 'ipca_mensal': 433, 'ipca_12m': 13522}, start=inicio)
        if 'selic' in df_bcb.columns and not df_bcb['selic'].dropna().empty:
            selic = float(df_bcb['selic'].dropna().iloc[-1])
            # Série 432 = % anual (ex: 14.75). Sanidade:
            if 0 < selic < 1:
                selic = selic * 100        # veio como decimal
            elif selic > 50:
                selic = SELIC_FALLBACK     # erro — fallback seguro
        # IPCA acumulado 12m (anual) — usado em Fisher / selic real / yield real
        if 'ipca_12m' in df_bcb.columns and not df_bcb['ipca_12m'].dropna().empty:
            _v12 = float(df_bcb['ipca_12m'].dropna().iloc[-1])
            if 0 < _v12 < 50:              # sanidade: 0–50% a.a.
                ipca_12m = _v12
        # IPCA mensal (print do mês) — exibição / cálculos mensais
        if 'ipca_mensal' in df_bcb.columns and not df_bcb['ipca_mensal'].dropna().empty:
            _vm = float(df_bcb['ipca_mensal'].dropna().iloc[-1])
            if abs(_vm) <= 5:              # >5% no mês = erro/hiperinflação
                ipca_mensal = _vm
    except Exception as e:
        logger.warning(f"[macro_context] falha BCB: {e}")

    # VIX via yfinance
    try:
        import yfinance as yf
        hist_vix = yf.Ticker("^VIX").history(period="2d")
        if not hist_vix.empty:
            vix = float(hist_vix['Close'].dropna().iloc[-1])
    except Exception as e:
        logger.warning(f"[macro_context] falha VIX: {e}")

    # Treasury 10y via yfinance (^TNX = yield em percentual direto)
    treasury_10y = TREASURY_10Y_FALLBACK
    try:
        hist_tnx = yf.Ticker("^TNX").history(period="2d")
        if not hist_tnx.empty:
            treasury_10y = float(hist_tnx['Close'].dropna().iloc[-1])
            if treasury_10y > 20:
                treasury_10y = treasury_10y / 100
    except Exception as e:
        logger.warning(f"[macro_context] falha TNX: {e}")

    # Classificação de regime
    juros_altos = selic > 10.0
    risco_alto = vix > 20.0

    if juros_altos and not risco_alto:
        label = "juros altos / risco controlado"
    elif juros_altos and risco_alto:
        label = "juros altos / stress global"
    elif not juros_altos and risco_alto:
        label = "juros baixos / stress global"
    else:
        label = "juros baixos / risco controlado"

    return {
        "selic":        round(selic, 2),
        "ipca":         round(ipca_12m, 2),     # canônico: acumulado 12m (% a.a.)
        "ipca_12m":     round(ipca_12m, 2),     # alias explícito
        "ipca_mensal":  round(ipca_mensal, 2),  # print do mês (série 433)
        "vix":          round(vix, 1),
        "treasury_10y": round(treasury_10y, 2),
        "label":        label,
    }


def garantir_macro_context() -> dict:
    """
    Garante que st.session_state["macro_context"] existe e está atualizado.
    Chame no início de qualquer página que precise de contexto macro.
    Retorna o dict atual.
    """
    if "macro_context" not in st.session_state:
        ctx = _fetch_macro_rapido()
        st.session_state["macro_context"] = ctx
    return st.session_state["macro_context"]
