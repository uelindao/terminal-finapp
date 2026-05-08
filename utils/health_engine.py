import yfinance as yf
import numpy as np
import pandas as pd
from database.db import get_historico_multiplos, salvar_multiplos_historicos, salvar_health_score

def calcular_health_score(ticker: str) -> dict:
    """
    Calcula score de 0-100 para um ticker.
    100 = ativo barato e saudável → COMPRAR/MANTER
    0   = ativo caro e deteriorando → REDUZIR/VENDER

    Retorna dict com score, componentes e lista de alertas.
    """
    info = yf.Ticker(ticker).info
    alertas = []
    pontos_fund = 100.0
    pontos_tec  = 100.0

    # ── COLETA DE MÚLTIPLOS ATUAIS ──────────────────────────────
    pl    = info.get('trailingPE', None)
    pvp   = info.get('priceToBook', None)
    roe_r = info.get('returnOnEquity', None)
    roe   = roe_r * 100 if roe_r else None
    marg_r= info.get('profitMargins', None)
    marg  = marg_r * 100 if marg_r else None
    dy_r  = info.get('dividendYield', None)
    dy    = dy_r * 100 if dy_r else None
    de    = info.get('debtToEquity', None)
    div_ebitda = de / 10 if de else None  # proxy

    # Salva snapshot histórico
    salvar_multiplos_historicos(ticker, {
        'pl': pl, 'pvp': pvp, 'roe': roe,
        'margem': marg, 'dy': dy, 'div_ebitda': div_ebitda
    })

    # ── ANÁLISE DE PERCENTIL HISTÓRICO ──────────────────────────
    # Busca histórico salvo (mínimo 30 dias para ser significativo)
    hist = get_historico_multiplos(ticker)

    if len(hist) >= 30:
        df_h = pd.DataFrame(hist)

        def percentil_atual(col, valor_atual, inverter=False):
            """
            Calcula em qual percentil o valor atual está.
            inverter=True: para métricas onde MENOR é MELHOR (P/L, P/VP).
            Retorna 0-100, onde 100 = mais caro/ruim historicamente.
            """
            serie = df_h[col].dropna()
            if len(serie) < 10 or valor_atual is None:
                return 50.0
            pct = (serie < valor_atual).mean() * 100
            return pct if not inverter else 100 - pct

        # P/L: percentil alto = caro = ruim
        if pl and pl > 0:
            pct_pl = percentil_atual('pl', pl)
            if pct_pl > 85:
                alertas.append(f"⚠️ P/L em percentil {pct_pl:.0f}% histórico — ativo nos níveis mais caros dos últimos {len(hist)} dias")
                pontos_fund -= 25
            elif pct_pl > 70:
                alertas.append(f"📊 P/L elevado (percentil {pct_pl:.0f}%) — valuation esticado")
                pontos_fund -= 12

        # ROE: percentil baixo = qualidade caindo = ruim
        if roe:
            pct_roe = percentil_atual('roe', roe, inverter=True)
            if pct_roe > 80:
                alertas.append(f"⚠️ ROE em mínimas históricas (percentil {pct_roe:.0f}%) — qualidade deteriorando")
                pontos_fund -= 20
            elif pct_roe > 65:
                pontos_fund -= 8

        # Margem: queda consecutiva
        margens = df_h['margem'].dropna().tail(6).tolist()
        if len(margens) >= 4:
            decrescente = all(margens[i] >= margens[i+1] for i in range(len(margens)-1))
            if decrescente:
                alertas.append("⚠️ Margem líquida em queda por 4+ períodos consecutivos")
                pontos_fund -= 20

        # DY: queda brusca (preço subiu demais ou cortaram dividendo)
        if dy:
            pct_dy = percentil_atual('dy', dy, inverter=True)
            if pct_dy > 75:
                alertas.append(f"📊 DY abaixo de {100-pct_dy:.0f}% da média histórica — preço pode estar caro")
                pontos_fund -= 10

    # ── ANÁLISE TÉCNICA ──────────────────────────────────────────
    try:
        hist_p = yf.Ticker(ticker).history(period="6mo")
        if not hist_p.empty and len(hist_p) >= 50:
            close = hist_p['Close']

            # RSI
            delta = close.diff()
            ganho = delta.clip(lower=0).rolling(14).mean()
            perda = (-delta.clip(upper=0)).rolling(14).mean()
            rs = ganho / perda
            rsi = (100 - (100 / (1 + rs))).iloc[-1]

            if rsi >= 78:
                alertas.append(f"🔴 RSI extremo ({rsi:.1f}) — momentum sobrecomprado")
                pontos_tec -= 30
            elif rsi >= 70:
                alertas.append(f"📊 RSI elevado ({rsi:.1f}) — zona de atenção técnica")
                pontos_tec -= 15

            # SMA Cross
            if len(close) >= 200:
                sma50  = close.rolling(50).mean().iloc[-1]
                sma200 = close.rolling(200).mean().iloc[-1]
                if sma50 < sma200:
                    alertas.append("🔴 Death Cross ativo — SMA50 abaixo da SMA200")
                    pontos_tec -= 25

            # Bollinger
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = (bb_mid + 2 * bb_std).iloc[-1]
            pct_bb = (close.iloc[-1] - (bb_mid - 2*bb_std).iloc[-1]) / (4 * bb_std.iloc[-1]) * 100
            if pct_bb >= 95:
                alertas.append("🔴 Preço tocando banda superior de Bollinger")
                pontos_tec -= 20

    except Exception:
        pass  # Falha técnica não derruba score fundamentalista

    # ── SCORE FINAL ──────────────────────────────────────────────
    score_fund = max(0.0, min(100.0, pontos_fund))
    score_tec  = max(0.0, min(100.0, pontos_tec))
    score_final = (score_fund * 0.65) + (score_tec * 0.35)  # 65% fund, 35% técnico

    salvar_health_score(ticker, score_final, score_fund, score_tec, alertas)

    return {
        'score': score_final,
        'score_fund': score_fund,
        'score_tec': score_tec,
        'alertas': alertas,
        'dados_hist_suficientes': len(hist) >= 30
    }