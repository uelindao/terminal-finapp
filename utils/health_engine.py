import yfinance as yf
import pandas as pd
import numpy as np
from database.db import salvar_health_score, get_todos_fundamentos_cache, registrar_historico_score
from utils.tickers import FII_TODOS
from utils.logger import get_logger

logger = get_logger(__name__)

# Referência de múltiplos por setor (yfinance sector strings, lowercase)
# Tupla: (pe_bom, pe_medio, pb_bom, pb_medio)
MULTIPLOS_SETOR: dict[str, tuple] = {
    "technology":             (30, 50, 6.0, 12.0),
    "financial services":     (12, 20, 1.5,  3.0),
    "utilities":              (18, 28, 1.5,  2.5),
    "consumer staples":       (22, 35, 3.0,  6.0),
    "consumer cyclical":      (20, 35, 3.0,  7.0),
    "healthcare":             (22, 38, 4.0,  8.0),
    "energy":                 (12, 20, 1.5,  3.0),
    "basic materials":        (12, 22, 1.5,  3.0),
    "industrials":            (20, 32, 3.0,  6.0),
    "real estate":            (20, 35, 1.5,  3.0),
    "communication services": (22, 38, 4.0,  8.0),
    # fallback para setores não mapeados (aplicado via lógica BR vs EUA)
    "_default":               (18, 32, 2.0,  4.0),
}


def safe_float(val, default=None) -> float | None:
    """Converte valor para float de forma segura, tratando string/None."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


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
    except Exception as e:
        logger.warning(f"[health_engine] falha ao calcular Piotroski F-Score: {e}")
        return 0, {}


def calcular_crescimento(acao, info: dict) -> tuple[int, dict]:
    """
    Pilar de Crescimento de Receita e Lucro (máx 15pts).
    Usa info.get('revenueGrowth') / 'earningsGrowth' como fonte primária;
    cai para acao.financials quando não disponível.
    Retorna (score, {'alertas': [...], 'rev_growth': float|None, 'earnings_growth': float|None}).
    """
    score_cresc = 0
    alertas_cresc: list[str] = []
    rev_growth: float | None = None
    earnings_growth: float | None = None

    try:
        # --- Fonte primária: info (decimal — 0.15 = 15%) ---
        rev_growth = info.get('revenueGrowth')
        earnings_growth = info.get('earningsGrowth')

        # --- Fallback: calcula manualmente via financials ---
        if acao is not None:
            fin = acao.financials
            if fin is not None and not fin.empty and len(fin.columns) >= 2:

                if rev_growth is None:
                    for nome in ['Total Revenue', 'Revenue']:
                        if nome in fin.index:
                            v_atual = fin.loc[nome, fin.columns[0]]
                            v_ant   = fin.loc[nome, fin.columns[1]]
                            if isinstance(v_atual, pd.Series): v_atual = v_atual.iloc[0]
                            if isinstance(v_ant,   pd.Series): v_ant   = v_ant.iloc[0]
                            if pd.notna(v_atual) and pd.notna(v_ant) and float(v_ant) != 0:
                                rev_growth = (float(v_atual) - float(v_ant)) / abs(float(v_ant))
                            break

                if earnings_growth is None:
                    for nome in ['Net Income', 'Net Income Common Stockholders']:
                        if nome in fin.index:
                            v_atual = fin.loc[nome, fin.columns[0]]
                            v_ant   = fin.loc[nome, fin.columns[1]]
                            if isinstance(v_atual, pd.Series): v_atual = v_atual.iloc[0]
                            if isinstance(v_ant,   pd.Series): v_ant   = v_ant.iloc[0]
                            if pd.notna(v_atual) and pd.notna(v_ant) and float(v_ant) != 0:
                                earnings_growth = (float(v_atual) - float(v_ant)) / abs(float(v_ant))
                            break

        # --- Pontuação de receita (máx 8pts) ---
        if rev_growth is not None:
            if rev_growth > 0.15:
                score_cresc += 8
            elif rev_growth > 0.05:
                score_cresc += 5
            elif rev_growth < 0:
                score_cresc -= 5
                alertas_cresc.append("⚠️ receita em queda (sinal de deterioração).")

        # --- Pontuação de lucro (máx 7pts) ---
        if earnings_growth is not None:
            if earnings_growth > 0.20:
                score_cresc += 7
            elif earnings_growth > 0.05:
                score_cresc += 4
            elif earnings_growth < 0 and rev_growth is not None and rev_growth < 0:
                alertas_cresc.append("🚨 compressão de margem e queda de receita simultâneas.")

    except Exception as e:
        logger.warning(f"[health_engine] falha ao calcular crescimento: {e}")

    return score_cresc, {
        'alertas': alertas_cresc,
        'rev_growth': rev_growth,
        'earnings_growth': earnings_growth,
    }


def calcular_roic(
    acao, info: dict,
    is_br: bool, is_us: bool,
    macro_context: dict,
) -> tuple[int, float | None]:
    """
    Pilar ROIC vs WACC simplificado (máx 12pts).
    WACC_ref: Selic + 3% para B3, 7.5% fixo para EUA.
    Retorna (score, roic_valor_percentual | None).
    A adição do alerta de ROIC negativo fica a cargo da função chamadora.
    """
    if acao is None:
        return 0, None

    score_roic = 0
    roic_valor: float | None = None

    try:
        fin = acao.financials
        bs  = acao.balance_sheet

        def _get(df, nomes, col=0):
            if df is None or df.empty:
                return None
            for nome in nomes:
                if nome in df.index and len(df.columns) > col:
                    val = df.loc[nome, df.columns[col]]
                    if isinstance(val, pd.Series):
                        val = val.iloc[0]
                    if pd.notna(val):
                        return float(val)
            return None

        ebit         = _get(fin, ['EBIT'])
        total_assets = _get(bs,  ['Total Assets'])
        current_liab = _get(bs,  ['Current Liabilities'])

        if ebit is not None and total_assets is not None and current_liab is not None:
            tax_rate       = 0.25
            nopat          = ebit * (1 - tax_rate)
            invested_cap   = total_assets - current_liab

            if invested_cap > 0:
                roic_valor = (nopat / invested_cap) * 100

                selic    = macro_context.get('selic', 10.5)
                wacc_ref = (selic + 3.0) if is_br else 7.5

                if roic_valor > wacc_ref * 1.5:
                    score_roic = 12
                elif roic_valor > wacc_ref:
                    score_roic = 8
                elif roic_valor >= 0:
                    score_roic = 3
                else:
                    score_roic = -5   # alerta adicionado pelo chamador

    except Exception as e:
        logger.warning(f"[health_engine] falha ao calcular ROIC: {e}")

    return score_roic, roic_valor


def calcular_momentum(hist: pd.DataFrame) -> tuple[int, dict, list]:
    """
    Fator Momentum 12-1 meses (evita reversão de curto prazo).
    Retorno = preço há 1 mês / preço há 12 meses − 1.
    Máx +10pts / mín −8pts.
    Retorna (score_mom, detalhes_dict, alertas_list).
    """
    if hist is None or len(hist) < 250:
        return 0, {}, []
    close = hist['Close'] if 'Close' in hist.columns else hist.iloc[:, 0]
    close = close.dropna()
    if len(close) < 230:
        return 0, {}, []

    preco_12m_atras = float(close.iloc[-252]) if len(close) >= 252 else float(close.iloc[0])
    preco_1m_atras  = float(close.iloc[-21])
    retorno_momentum = ((preco_1m_atras / preco_12m_atras) - 1) * 100

    preco_atual = float(close.iloc[-1])
    retorno_1m  = ((preco_atual / preco_1m_atras) - 1) * 100

    score_mom  = 0
    alertas_mom: list[str] = []

    if retorno_momentum > 20:
        score_mom = 10
        alertas_mom.append(f"✅ Momentum forte (12-1m: +{retorno_momentum:.1f}%)")
    elif retorno_momentum > 8:
        score_mom = 6
    elif retorno_momentum > 0:
        score_mom = 3
    elif retorno_momentum < -20:
        score_mom = -8
        alertas_mom.append(f"🚨 Momentum negativo severo (12-1m: {retorno_momentum:.1f}%)")
    elif retorno_momentum < -8:
        score_mom = -4
        alertas_mom.append(f"⚠️ Momentum negativo (12-1m: {retorno_momentum:.1f}%)")

    detalhes = {
        "Momentum 12-1m":      f"{retorno_momentum:+.1f}%",
        "Retorno último mês":  f"{retorno_1m:+.1f}%",
    }
    return score_mom, detalhes, alertas_mom


def calcular_health_score(ticker: str, macro_context: dict = None, hist_externo=None) -> dict:
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
        cache = get_todos_fundamentos_cache()
        dados_base = cache.get(ticker, {})
        cache_disponivel = bool(dados_base and dados_base.get('qualidade_dados', 0) >= 40)

        # usar hist_externo se disponível, senão buscar individualmente
        if hist_externo is not None and not (isinstance(hist_externo, pd.DataFrame) and hist_externo.empty):
            hist = hist_externo if isinstance(hist_externo, pd.DataFrame) else pd.DataFrame({'Close': hist_externo})
        else:
            acao_temp = yf.Ticker(ticker)
            hist = acao_temp.history(period="1y")

        # pular acao.info para qualquer mercado com cache populado
        if cache_disponivel and (is_br or is_fii or is_us):
            info = {}
            acao = None
        else:
            if 'acao_temp' in locals():
                acao = acao_temp
            else:
                acao = yf.Ticker(ticker)
            info = acao.info

        qualidade = dados_base.get('qualidade_dados', 50)
        dados_confiaveis = qualidade >= 40

        pvp = safe_float(dados_base.get('p/vp')) or safe_float(info.get('priceToBook'))
        dy = safe_float(dados_base.get('dy%')) or (safe_float(info.get('dividendYield'), 0) * 100 if info.get('dividendYield') else 0)
        
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
        beta_seguro = safe_float(info.get('beta'), default=1.0)
        if vix_alto and (beta_seguro > 1.2):
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
                selic_atual = macro_context.get('selic', 10.5)
                # yield mínimo aceitável = Selic + 2% (prêmio de risco imobiliário)
                yield_minimo   = selic_atual + 2.0
                yield_otimo    = selic_atual + 4.0
                yield_excessivo = selic_atual + 8.0

                if dy >= yield_otimo and dy <= yield_excessivo:
                    score_y += 40
                elif dy >= yield_minimo and dy < yield_otimo:
                    score_y += 25
                    alertas.append(f"ℹ️ yield ({dy:.1f}%) adequado mas abaixo do ótimo para selic {selic_atual:.1f}%.")
                elif dy > yield_excessivo:
                    score_y += 15
                    alertas.append(f"🚨 yield trap? dividendo ({dy:.1f}%) excessivamente alto vs selic {selic_atual:.1f}%.")
                elif dy < yield_minimo and dy >= selic_atual:
                    score_y += 10
                    alertas.append(f"⚠️ yield ({dy:.1f}%) abaixo do prêmio mínimo exigido vs selic {selic_atual:.1f}%.")
                else:
                    score_y += 0
                    alertas.append(f"🚨 yield ({dy:.1f}%) muito baixo para FII com selic a {selic_atual:.1f}%.")
            else:
                score_y += 20

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
            if acao is not None:
                f_score, f_detalhamento = calcular_piotroski(acao)
            else:
                f_score, f_detalhamento = 0, {}
            
            pl = safe_float(dados_base.get('p/l')) or safe_float(info.get('trailingPE')) or safe_float(info.get('forwardPE'))
            raw_roe = safe_float(info.get('returnOnEquity'))
            roe = safe_float(dados_base.get('roe%')) or (raw_roe * 100 if raw_roe is not None else None)
            raw_margem = safe_float(info.get('profitMargins'))
            margem = safe_float(dados_base.get('margem%')) or (raw_margem * 100 if raw_margem is not None else None)
            ev_ebitda = safe_float(dados_base.get('ev/ebitda')) or safe_float(info.get('enterpriseToEbitda'))
            debt_equity = safe_float(info.get('debtToEquity'))

            # --- Qualidade e Rentabilidade (máx 24pts) ---
            score_q = 0
            if roe is not None:
                if roe > 20: score_q += 12
                elif roe > 10: score_q += 8
                elif roe > 0: score_q += 4
                else: alertas.append("⚠️ empresa destruindo valor (roe negativo).")

            if margem is not None:
                if margem > 15: score_q += 12
                elif margem > 5: score_q += 8
                elif margem < 0: alertas.append("⚠️ margem líquida negativa.")
            else: score_q += 6
            
            # --- Valuation Adaptativo com múltiplos setoriais (máx 26pts) ---
            # Fonte: info.get('sector') em inglês (yfinance) ou fallback para dado do cache
            setor_yf = (info.get('sector', '') or dados_base.get('setor', '')).lower()
            if setor_yf in MULTIPLOS_SETOR:
                # setor identificado — usa thresholds específicos do setor
                limite_pl_bom, limite_pl_medio, limite_pvp_bom, limite_pvp_medio = MULTIPLOS_SETOR[setor_yf]
            else:
                # setor não mapeado — mantém diferenciação BR vs EUA (comportamento original)
                limite_pl_bom    = 18 if is_us else 13
                limite_pl_medio  = 32 if is_us else 25
                limite_pvp_bom   = 4.0 if is_us else 2.0
                limite_pvp_medio = 8.0 if is_us else 4.0

            score_v = 0
            if pl is not None and pl > 0:
                if pl <= limite_pl_bom:    score_v += 13
                elif pl <= limite_pl_medio: score_v += 8
                elif pl > limite_pl_medio:  alertas.append(f"⚠️ valuation esticado (p/l de {pl:.1f}).")

            if pvp is not None and pvp > 0:
                if pvp <= limite_pvp_bom:    score_v += 13
                elif pvp <= limite_pvp_medio: score_v += 8
                elif pvp > limite_pvp_medio:  alertas.append(f"⚠️ prêmio patrimonial excessivo (p/vp de {pvp:.1f}).")

            # --- Solvência e Risco (máx 20pts, D/E mais rigoroso em B3 com juros altos) ---
            score_r = 0
            penalizacao_divida = 2 if (is_br and juros_altos_br) else 1

            if debt_equity is not None:
                limite_de_bom   = 30 if (is_br and juros_altos_br) else 50
                limite_de_medio = 100 if (is_br and juros_altos_br) else 120

                if debt_equity < limite_de_bom: score_r += 20
                elif debt_equity < limite_de_medio: score_r += 10
                elif debt_equity > 150:
                    alertas.append(f"🚨 risco de solvência (dívida alta, d/e: {debt_equity:.0f}).")
                    score_r -= (10 * penalizacao_divida)
            elif ev_ebitda is not None and ev_ebitda > 0:
                limite_ev_bom   = 12 if is_us else 8
                limite_ev_medio = 20 if is_us else 14

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
                score_piotroski = -8
                alertas.append(f"🚨 balanço fraco (piotroski f-score: {f_score}/9). risco de deterioração fundamentalista.")

            # --- Crescimento de Receita e Lucro (máx 15pts) ---
            score_crescimento = 0
            if acao is not None:
                score_crescimento, detalhes_cresc = calcular_crescimento(acao, info)
                alertas.extend(detalhes_cresc.get('alertas', []))

            # --- ROIC vs WACC (máx 12pts) ---
            score_roic = 0
            roic_valor: float | None = None
            if acao is not None:
                score_roic, roic_valor = calcular_roic(acao, info, is_br, is_us, macro_context)
                if roic_valor is not None and roic_valor < 0:
                    alertas.append("🚨 ROIC negativo — empresa destruindo capital dos acionistas.")

            # --- Momentum 12-1m (máx 10pts, mín −8pts) ---
            score_momentum = 0
            det_mom: dict = {}
            alertas_mom_list: list[str] = []
            if hist is not None and not hist.empty:
                score_momentum, det_mom, alertas_mom_list = calcular_momentum(hist)
                alertas.extend(alertas_mom_list)

            # penalidade por dados de baixa qualidade
            penalidade_dados = 0
            if not dados_confiaveis and not is_us:
                penalidade_dados = -10
                alertas.append(f"⚠️ dados fundamentalistas com qualidade baixa ({qualidade}%). score pode estar subestimado.")

            score = (
                score_q + score_v + score_r_final + score_y
                + score_piotroski + score_crescimento + score_roic
                + score_momentum
                + penalidade_tec + penalidade_vix + penalidade_dados
            )

            setor_label = setor_yf.title() if setor_yf and setor_yf in MULTIPLOS_SETOR else ('EUA' if is_us else 'B3')
            breakdown = {
                "Qualidade e Rentabilidade": score_q,
                f"Valuation ({setor_label})": score_v,
                "Solvência e Risco Macro": score_r_final,
                "Geração de Caixa / Yield": score_y,
                "Qualidade de Balanço (Piotroski F-Score)": score_piotroski,
                "Crescimento (Receita/Lucro)": score_crescimento,
                "ROIC vs WACC": score_roic,
                "Momentum (12-1m)": score_momentum,
                "Penalidade Técnica (MM200)": penalidade_tec,
                "Risco Volatilidade (VIX)": penalidade_vix,
                "Penalidade Dados (Qualidade)": penalidade_dados,
            }

            if roic_valor is not None:
                breakdown["  ↳ ROIC"] = f"{roic_valor:.1f}%"

            if det_mom:
                for k, v in det_mom.items():
                    breakdown[f"  ↳ {k}"] = v

            if f_detalhamento:
                for k, v in f_detalhamento.items():
                    breakdown[f"  ↳ {k}"] = v

        # ==========================================
        # DIAGNÓSTICO FINAL COMPARTILHADO
        # ==========================================
        score = min(max(int(score), 0), 100)

        # RSI como qualificador adicional, não como gate exclusivo
        rsi_sobrevendido  = rsi < 35
        rsi_sobrecomprado = rsi > 70

        if score >= 72:
            if rsi_sobrevendido:
                status_acao = "🟢 ACUMULAÇÃO FORTE: Ativo sólido com desconto e sobrevendido."
            elif rsi_sobrecomprado:
                status_acao = "🟡 ATENÇÃO: Fundamentos sólidos mas sobrecomprado no curto prazo."
            else:
                status_acao = "🟢 ACUMULAÇÃO: Ativo sólido. Bom ponto de entrada."
        elif score >= 58:
            status_acao = "🟡 MANUTENÇÃO: Saudável, sem desconto gritante. Aporte neutro."
        elif score >= 40:
            if preco_atual < mm200:
                status_acao = "🟠 REDUZIR EXPOSIÇÃO: Fundamentos fracos e tendência de baixa."
            else:
                status_acao = "🟠 AGUARDAR: Fundamentos medianos. Sem catalisador claro."
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
        registrar_historico_score(ticker, score)
        return {'score': score, 'alertas': alertas, 'status': status_acao}
        
    except Exception as e:
        logger.error(f"[health_engine] erro crítico ao calcular health score para {ticker}: {e}")
        payload = {"alertas": [f"erro no cálculo: {e}"], "breakdown": {}}
        salvar_health_score(ticker, 50, payload)
        return {'score': 50, 'alertas': [f"erro: {e}"], 'status': "⚪ ERRO"}