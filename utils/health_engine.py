import yfinance as yf
import pandas as pd
import numpy as np
from database.db import salvar_health_score, get_todos_fundamentos_cache
from utils.tickers import FII_TODOS

def _is_fii(ticker: str) -> bool:
    """Determina se o ativo é um Fundo Imobiliário (FII)."""
    nao_fiis = [
        'TAEE11.SA', 'SANB11.SA', 'KLBN11.SA', 'ALUP11.SA', 'BPAC11.SA', 
        'ENGI11.SA', 'BOVA11.SA', 'IVVB11.SA', 'HASH11.SA', 'SMAL11.SA',
        'NASH11.SA', 'DIVO11.SA', 'BIDI11.SA', 'SULA11.SA', 'IGTI11.SA'
    ]
    if ticker in FII_TODOS:
        return True
    if ticker.endswith('11.SA') and ticker not in nao_fiis:
        return True
    return False

def calcular_piotroski(acao):
    try:
        financials = acao.financials
        balance_sheet = acao.balance_sheet
        cashflow = acao.cashflow

        def get_val(df, possiveis_nomes, col_idx=0):
            if df is None or df.empty:
                return None
            for nome in possiveis_nomes:
                if nome in df.index and len(df.columns) > col_idx:
                    val = df.loc[nome, df.columns[col_idx]]
                    if isinstance(val, pd.Series):
                        val = val.iloc[0]
                    if pd.notna(val):
                        return float(val)
            return None

        total_assets_atual = get_val(balance_sheet, ["Total Assets"], 0)
        total_assets_anterior = get_val(balance_sheet, ["Total Assets"], 1)
        net_income = get_val(financials, ["Net Income", "Net Income Common Stockholders"], 0)
        net_income_anterior = get_val(financials, ["Net Income", "Net Income Common Stockholders"], 1)
        operating_cashflow = get_val(cashflow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], 0)
        long_debt_atual = get_val(balance_sheet, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 0)
        long_debt_anterior = get_val(balance_sheet, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 1)
        current_assets_atual = get_val(balance_sheet, ["Current Assets"], 0)
        current_assets_anterior = get_val(balance_sheet, ["Current Assets"], 1)
        current_liab_atual = get_val(balance_sheet, ["Current Liabilities"], 0)
        current_liab_anterior = get_val(balance_sheet, ["Current Liabilities"], 1)
        shares_atual = get_val(balance_sheet, ["Ordinary Shares Number", "Share Issued"], 0)
        shares_anterior = get_val(balance_sheet, ["Ordinary Shares Number", "Share Issued"], 1)
        gross_profit_atual = get_val(financials, ["Gross Profit"], 0)
        gross_profit_anterior = get_val(financials, ["Gross Profit"], 1)
        revenue_atual = get_val(financials, ["Total Revenue", "Revenue"], 0)
        revenue_anterior = get_val(financials, ["Total Revenue", "Revenue"], 1)

        f1 = 1 if total_assets_atual is not None and total_assets_atual > 0 and net_income is not None and (net_income / total_assets_atual) > 0 else 0
        
        f2 = 1 if operating_cashflow is not None and operating_cashflow > 0 else 0
        
        roa_atual = (net_income / total_assets_atual) if net_income is not None and total_assets_atual is not None and total_assets_atual > 0 else None
        roa_anterior = (net_income_anterior / total_assets_anterior) if net_income_anterior is not None and total_assets_anterior is not None and total_assets_anterior > 0 else None
        f3 = 1 if roa_atual is not None and roa_anterior is not None and roa_atual > roa_anterior else 0
        
        f4 = 1 if operating_cashflow is not None and total_assets_atual is not None and total_assets_atual > 0 and net_income is not None and (operating_cashflow / total_assets_atual) > (net_income / total_assets_atual) else 0
        
        leverage_atual = (long_debt_atual / total_assets_atual) if long_debt_atual is not None and total_assets_atual is not None and total_assets_atual > 0 else None
        leverage_anterior = (long_debt_anterior / total_assets_anterior) if long_debt_anterior is not None and total_assets_anterior is not None and total_assets_anterior > 0 else None
        f5 = 1 if leverage_atual is not None and leverage_anterior is not None and leverage_atual < leverage_anterior else 0
        
        current_ratio_atual = (current_assets_atual / current_liab_atual) if current_assets_atual is not None and current_liab_atual is not None and current_liab_atual > 0 else None
        current_ratio_anterior = (current_assets_anterior / current_liab_anterior) if current_assets_anterior is not None and current_liab_anterior is not None and current_liab_anterior > 0 else None
        f6 = 1 if current_ratio_atual is not None and current_ratio_anterior is not None and current_ratio_atual > current_ratio_anterior else 0
        
        f7 = 1 if shares_atual is not None and shares_anterior is not None and shares_atual <= shares_anterior else 0
        
        gross_margin_atual = (gross_profit_atual / revenue_atual) if gross_profit_atual is not None and revenue_atual is not None and revenue_atual > 0 else None
        gross_margin_anterior = (gross_profit_anterior / revenue_anterior) if gross_profit_anterior is not None and revenue_anterior is not None and revenue_anterior > 0 else None
        f8 = 1 if gross_margin_atual is not None and gross_margin_anterior is not None and gross_margin_atual > gross_margin_anterior else 0
        
        asset_turnover_atual = (revenue_atual / total_assets_atual) if revenue_atual is not None and total_assets_atual is not None and total_assets_atual > 0 else None
        asset_turnover_anterior = (revenue_anterior / total_assets_anterior) if revenue_anterior is not None and total_assets_anterior is not None and total_assets_anterior > 0 else None
        f9 = 1 if asset_turnover_atual is not None and asset_turnover_anterior is not None and asset_turnover_atual > asset_turnover_anterior else 0

        f_score_total = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9
        
        detalhamento = {
            "F1 ROA positivo": f1,
            "F2 FCF positivo": f2,
            "F3 ROA crescendo": f3,
            "F4 qualidade lucro (FCF > ROA)": f4,
            "F5 dívida reduzindo": f5,
            "F6 liquidez melhorando": f6,
            "F7 sem diluição": f7,
            "F8 margem bruta crescendo": f8,
            "F9 giro de ativos crescendo": f9
        }
        
        return f_score_total, detalhamento
    except Exception:
        return 0, {}

def calcular_health_score(ticker: str, macro_context: dict = None) -> dict:
    """
    Motor quantitativo institucional (Dynamic Scoring).
    Cruza pilares fundamentalistas com o cenário macro e momentum técnico.
    Contém motores distintos para FIIs, Ações B3 e Ações EUA.
    """
    if macro_context is None:
        macro_context = {'selic': 10.5, 'vix': 15.0, 'ipca': 4.5}
    
    juros_altos_br = macro_context.get('selic', 10.5) > 10.0
    vix_alto = macro_context.get('vix', 15.0) > 20.0
    
    # Detecção de Mercado
    is_fii = _is_fii(ticker)
    is_br = ticker.endswith('.SA') and not is_fii
    is_us = not ticker.endswith('.SA') and not is_fii
    
    try:
        acao = yf.Ticker(ticker)
        info = acao.info
        hist = acao.history(period="1y")
        
        cache = get_todos_fundamentos_cache()
        dados_base = cache.get(ticker, {})
        
        pvp = dados_base.get('p/vp') or info.get('priceToBook', None)
        dy = dados_base.get('dy%') or (info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0)
        
        score = 0
        alertas = []
        breakdown = {}
        
        if hist.empty or len(hist) < 50:
            payload = {"alertas": ["histórico insuficiente para análise técnica"], "breakdown": {}}
            salvar_health_score(ticker, 50, payload)
            return {'score': 50, 'alertas': ["histórico insuficiente"]}

        close = hist['Close']
        mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.mean()
        preco_atual = close.iloc[-1]
        
        delta = close.diff()
        ganho = delta.clip(lower=0).rolling(14).mean()
        perda = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = (100 - (100 / (1 + (ganho / perda)))).iloc[-1] if len(close) >= 15 else 50
        
        penalidade_tec = 0
        if preco_atual < mm200:
            alertas.append("📉 tendência de baixa (preço abaixo da MM200).")
            penalidade_tec = -15
            
        penalidade_vix = 0
        if vix_alto and (info.get('beta', 1) > 1.2):
            alertas.append("⚠️ ativo volátil em cenário de stress (VIX alto).")
            penalidade_vix = -10

        # ==========================================
        # MOTOR 1: FUNDOS IMOBILIÁRIOS (FIIs)
        # ==========================================
        if is_fii:
            score_pvp = 0
            if pvp is not None and pvp > 0:
                if 0.90 <= pvp <= 1.05: score_pvp += 40 
                elif 0.80 <= pvp < 0.90: 
                    score_pvp += 30 
                    alertas.append("⚠️ desconto alto no p/vp. verificar risco de vacância.")
                elif pvp < 0.80:
                    score_pvp += 10
                    alertas.append("🚨 p/vp crítico (< 0.80). o mercado precifica problemas graves.")
                elif pvp > 1.05:
                    score_pvp += 20
                    alertas.append("⚠️ fundo negociado com ágio.")
            else: score_pvp += 20
                
            score_y = 0
            if dy is not None:
                if 8.0 <= dy <= 12.0: score_y += 40 
                elif dy > 12.0:
                    score_y += 20
                    alertas.append("🚨 yield trap? dividendos excessivamente altos.")
                elif 5.0 <= dy < 8.0: score_y += 20
                elif dy < 5.0: alertas.append("⚠️ dividend yield muito baixo para um FII.")
            else: score_y += 20

            score_tec = 20 + penalidade_tec
            score = score_pvp + score_y + score_tec
            
            breakdown = {
                "Valuation Justo (P/VP)": score_pvp,
                "Geração de Renda (Yield)": score_y,
                "Momento Técnico": score_tec
            }

        # ==========================================
        # MOTOR 2 e 3: AÇÕES (B3 vs EUA)
        # ==========================================
        else:
            f_score, f_detalhamento = calcular_piotroski(acao)
            
            pl = dados_base.get('p/l') or info.get('trailingPE', info.get('forwardPE', None))
            roe = dados_base.get('roe%') or (info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else None)
            margem = dados_base.get('margem%') or (info.get('profitMargins', 0) * 100 if info.get('profitMargins') else None)
            ev_ebitda = dados_base.get('ev/ebitda') or info.get('enterpriseToEbitda', None)
            debt_equity = info.get('debtToEquity', None)

            # --- Qualidade e Rentabilidade ---
            score_q = 0
            if roe is not None:
                if roe > 20: score_q += 15
                elif roe > 10: score_q += 10
                elif roe > 0: score_q += 5
                else: alertas.append("⚠️ empresa destruindo valor (roe negativo).")
                
            if margem is not None:
                if margem > 15: score_q += 15
                elif margem > 5: score_q += 10
                elif margem < 0: alertas.append("⚠️ margem líquida negativa.")
            else: score_q += 7
            
            # --- Valuation Adaptativo (B3 vs EUA) ---
            score_v = 0
            if pl is not None and pl > 0:
                limite_pl_bom = 18 if is_us else 10
                limite_pl_medio = 30 if is_us else 20
                
                if pl <= limite_pl_bom: score_v += 15
                elif pl <= limite_pl_medio: score_v += 10
                elif pl > limite_pl_medio: alertas.append(f"⚠️ valuation esticado (p/l de {pl:.1f}).")
                
            if pvp is not None and pvp > 0:
                limite_pvp_bom = 3.5 if is_us else 1.5
                limite_pvp_medio = 6.0 if is_us else 3.0
                
                if pvp <= limite_pvp_bom: score_v += 15
                elif pvp <= limite_pvp_medio: score_v += 10
                elif pvp > limite_pvp_medio: alertas.append(f"⚠️ prêmio patrimonial excessivo (p/vp de {pvp:.1f}).")

            # --- Solvência e Risco ---
            score_r = 0
            penalizacao_divida = 2 if (is_br and juros_altos_br) else 1 
            
            if debt_equity is not None:
                if debt_equity < 50: score_r += 20
                elif debt_equity < 120: score_r += 10
                elif debt_equity > 150: 
                    alertas.append(f"🚨 risco de solvência (dívida alta).")
                    score_r -= (10 * penalizacao_divida)
            elif ev_ebitda is not None and ev_ebitda > 0:
                limite_ev_bom = 12 if is_us else 8
                limite_ev_medio = 18 if is_us else 12
                
                if ev_ebitda <= limite_ev_bom: score_r += 20
                elif ev_ebitda <= limite_ev_medio: score_r += 10
                elif ev_ebitda > limite_ev_medio:
                    alertas.append(f"🚨 alavancagem alta (ev/ebitda: {ev_ebitda:.1f}).")
                    score_r -= (5 * penalizacao_divida)
            else: score_r += 10 
            
            score_r_final = max(0, score_r)

            # --- Geração de Caixa / Yield Adaptativo ---
            score_y = 0
            exigencia_yield = 2.5 if is_us else (6.0 if juros_altos_br else 4.0)
            
            if dy is not None:
                if dy >= exigencia_yield: score_y += 20
                elif dy >= (exigencia_yield / 2): score_y += 10
                elif dy == 0 and is_br: alertas.append("ℹ️ empresa não distribui proventos.")

            score_piotroski = 0
            if f_score >= 7:
                score_piotroski = 15
                alertas.append(f"✅ balanço de alta qualidade (piotroski f-score: {f_score}/9).")
            elif f_score >= 5:
                score_piotroski = 8
            elif f_score <= 2 and f_detalhamento:
                score_piotroski = -10
                alertas.append(f"🚨 balanço fraco (piotroski f-score: {f_score}/9). risco de deterioração fundamentalista.")

            score = score_q + score_v + score_r_final + score_y + score_piotroski + penalidade_tec + penalidade_vix

            breakdown = {
                "Qualidade e Rentabilidade": score_q,
                f"Valuation (Padrão {'EUA' if is_us else 'B3'})": score_v,
                "Solvência e Risco Macro": score_r_final,
                f"Geração de Caixa / Yield": score_y,
                "Qualidade de Balanço (Piotroski F-Score)": score_piotroski,
                "Penalidade Técnica (MM200)": penalidade_tec,
                "Risco Volatilidade (VIX)": penalidade_vix
            }
            
            if f_detalhamento:
                for k, v in f_detalhamento.items():
                    breakdown[f"  ↳ {k}"] = v

        # ==========================================
        # DIAGNÓSTICO FINAL COMPARTILHADO
        # ==========================================
        status_acao = ""
        score = min(max(int(score), 0), 100) 

        if score >= 75 and rsi < 40:
            status_acao = "🟢 ACUMULAÇÃO FORTE: Ativo sólido com desconto e sobrevendido."
        elif score >= 65 and rsi >= 40:
            status_acao = "🟡 MANUTENÇÃO: Saudável, sem desconto gritante. Aporte neutro."
        elif score < 65 and score >= 40 and preco_atual < mm200:
            status_acao = "🟠 REDUZIR EXPOSIÇÃO: Fundamentos fracos e tendência de baixa."
        elif score < 40:
            status_acao = "🔴 VENDA DEFINITIVA: Quebra de tese (Score Crítico)."
        else:
            status_acao = "⚪ AGUARDAR: Zona indefinida."
            
        alertas.insert(0, status_acao)

        payload = {
            "alertas": alertas,
            "breakdown": breakdown
        }

        salvar_health_score(ticker, score, payload)
        return {'score': score, 'alertas': alertas, 'status': status_acao}
        
    except Exception as e:
        payload = {"alertas": [f"erro no cálculo: {e}"], "breakdown": {}}
        salvar_health_score(ticker, 50, payload)
        return {'score': 50, 'alertas': [f"erro: {e}"], 'status': "⚪ ERRO"}