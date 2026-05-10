import yfinance as yf
import pandas as pd
import numpy as np
import json
from database.db import salvar_health_score

def calcular_health_score(ticker: str):
    try:
        acao = yf.Ticker(ticker)
        info = acao.info
        
        # busca histórico mais longo para médias móveis
        hist = acao.history(period="1y")
        
        score_fund = 0
        score_tec = 0
        alertas = []
        
        if hist.empty or len(hist) < 50:
            salvar_health_score(ticker, 50, json.dumps(["histórico insuficiente para análise"]))
            return

        # ==========================================
        # 1. ANÁLISE FUNDAMENTALISTA (MÁX 50 PTS)
        # ==========================================
        
        # a. lucratividade (P/L) - máx 15 pts (muito rigoroso)
        pl = info.get('trailingPE', info.get('forwardPE', None))
        if pl is not None:
            if 0 < pl <= 15:
                score_fund += 15
            elif 15 < pl <= 25:
                score_fund += 8
                alertas.append(f"múltiplo p/l esticado ({pl:.1f})")
            elif pl > 25:
                score_fund += 0
                alertas.append(f"valuation muito caro (p/l de {pl:.1f})")
            else:
                alertas.append("p/l negativo (empresa reportando prejuízo)")
        else:
            score_fund += 7  # nota neutra para etfs/criptos
            
        # b. rentabilidade (ROE) - máx 15 pts (exigência acima da selic)
        roe_raw = info.get('returnOnEquity', None)
        if roe_raw is not None:
            roe = roe_raw * 100
            if roe >= 20:
                score_fund += 15
            elif 10 <= roe < 20:
                score_fund += 8
            elif 0 < roe < 10:
                score_fund += 0
                alertas.append(f"roe muito baixo ({roe:.1f}%), perdendo para o custo de capital")
            else:
                alertas.append("roe negativo (destruição de valor ao acionista)")
        else:
            score_fund += 7
            
        # c. preço/valor patrimonial (P/VP) - máx 10 pts
        pvp = info.get('priceToBook', None)
        if pvp is not None:
            if 0 < pvp <= 1.5:
                score_fund += 10
            elif 1.5 < pvp <= 3:
                score_fund += 5
            elif pvp > 3:
                score_fund += 0
                alertas.append(f"p/vp muito alto ({pvp:.1f})")
            else:
                alertas.append("p/vp negativo (passivo a descoberto)")
        else:
            score_fund += 5
            
        # d. retorno em dividendos - máx 10 pts (exigindo > 6% para nota máxima)
        dy_raw = info.get('dividendYield', None)
        if dy_raw is not None:
            dy = dy_raw * 100
            if dy >= 6:
                score_fund += 10
            elif 2 <= dy < 6:
                score_fund += 5
            elif dy > 0:
                score_fund += 2
        else:
            score_fund += 5
            
        # ==========================================
        # 2. ANÁLISE TÉCNICA E MOMENTO (MÁX 50 PTS)
        # ==========================================
        close = hist['Close']
        
        # a. tendência de longo prazo (MM200) - máx 15 pts
        if len(close) >= 200:
            mm200 = close.rolling(200).mean().iloc[-1]
            if close.iloc[-1] > mm200:
                score_tec += 15
            else:
                alertas.append("tendência estrutural de baixa (abaixo da mm200)")
        else:
            score_tec += 7
            
        # b. tendência de curto prazo (MM50) - máx 15 pts
        if len(close) >= 50:
            mm50 = close.rolling(50).mean().iloc[-1]
            if close.iloc[-1] > mm50:
                score_tec += 15
            else:
                alertas.append("perdeu momento de curto prazo (abaixo da mm50)")
        else:
            score_tec += 7
            
        # c. sobrecompra/sobrevenda (RSI 14) - máx 20 pts
        if len(close) >= 15:
            delta = close.diff()
            ganho = delta.clip(lower=0).rolling(14).mean()
            perda = (-delta.clip(upper=0)).rolling(14).mean()
            rs = ganho / perda
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            
            if rsi < 40:
                score_tec += 20  # excelente ponto de entrada técnico
            elif 40 <= rsi <= 60:
                score_tec += 10  # neutro
            elif 60 < rsi <= 70:
                score_tec += 5   # esticando
            else:
                score_tec += 0
                alertas.append(f"ativo tecnicamente sobrecomprado (rsi: {rsi:.1f})")
        else:
            score_tec += 10
            
        score_final = score_fund + score_tec
        
        salvar_health_score(ticker, score_final, alertas)
        
    except Exception as e:
        salvar_health_score(ticker, 50, [f"erro interno no cálculo: {str(e)}"])