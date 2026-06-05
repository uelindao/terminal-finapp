"""
utils/macro_context.py
Fetch leve do contexto macro atual para uso em qualquer página.
Garante que o session_state["macro_context"] esteja sempre atualizado.
"""
import streamlit as st
from utils.logger import get_logger

logger = get_logger(__name__)

# Valores de fallback (usados quando APIs estão indisponíveis)
SELIC_FALLBACK       = 14.75   # % a.a. — atualizar quando COPOM mudar
IPCA_FALLBACK        =  0.45   # % mês
VIX_FALLBACK         = 15.0    # pontos
TREASURY_10Y_FALLBACK =  4.5   # % a.a.


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_macro_rapido() -> dict:
    """
    Busca Selic, IPCA e VIX em paralelo.
    Cache de 1 hora — chamada barata (~300ms).
    Retorna dict com valores atuais e label de regime.
    """
    selic = SELIC_FALLBACK
    ipca  = IPCA_FALLBACK
    vix   = VIX_FALLBACK

    # Selic e IPCA via BCB SGS
    try:
        from bcb import sgs
        import datetime
        inicio = (datetime.datetime.today() - datetime.timedelta(days=60)).strftime('%Y-%m-%d')
        df_bcb = sgs.get({'selic': 432, 'ipca': 433}, start=inicio)
        if 'selic' in df_bcb.columns and not df_bcb['selic'].dropna().empty:
            selic = float(df_bcb['selic'].dropna().iloc[-1])
            # Série 432 = % anual (ex: 14.75). Sanidade:
            if 0 < selic < 1:
                selic = selic * 100        # veio como decimal
            elif selic > 50:
                selic = SELIC_FALLBACK     # erro — fallback seguro
        if 'ipca' in df_bcb.columns and not df_bcb['ipca'].dropna().empty:
            ipca = float(df_bcb['ipca'].dropna().iloc[-1])
            # Série 433 = % mensal (ex: 0.38). Sanidade:
            if abs(ipca) > 5:              # >5% no mês = hiperinflação
                ipca = 0.45
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
        "ipca":         round(ipca, 2),
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
