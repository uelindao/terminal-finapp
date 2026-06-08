try:
    import streamlit as st
    _ST_AVAILABLE = True
except ImportError:
    # ETL context (GitHub Actions) — sem Streamlit instalado
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
    _ST_AVAILABLE = False

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from database.db import (
    salvar_health_score, get_todos_fundamentos_cache, registrar_historico_score,
    get_health_scores, get_all_price_cache,
)
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


def safe_int(val, default=0) -> int:
    """Converte valor para int de forma segura, tratando string/None."""
    if val is None:
        return default
    try:
        return int(float(val))
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

def calcular_piotroski(acao, setor: str = "", is_br: bool = False):
    try:
        def _get_val_financials(df, *nomes):
            if df is None or df.empty:
                return None
            for nome in nomes:
                try:
                    if nome in df.index:
                        val = df.loc[nome]
                        if isinstance(val, pd.Series):
                            val = val.dropna()
                            return float(val.iloc[0]) if not val.empty else None
                        return float(val)
                except Exception:
                    continue
            return None

        try:
            fin   = acao.financials if acao else None
            bal   = acao.balance_sheet if acao else None
            cf    = acao.cashflow if acao else None
            fin_q = acao.quarterly_financials if acao else None
            bal_q = acao.quarterly_balance_sheet if acao else None
        except Exception:
            fin = bal = cf = fin_q = bal_q = None

        # Total Assets (dois períodos)
        total_assets_atual = None
        total_assets_ant   = None
        try:
            if bal is not None and not bal.empty:
                row = None
                for nome in ['Total Assets', 'TotalAssets', 'totalAssets']:
                    if nome in bal.index:
                        row = bal.loc[nome].dropna()
                        break
                if row is not None and len(row) >= 1:
                    total_assets_atual = float(row.iloc[0])
                if row is not None and len(row) >= 2:
                    total_assets_ant   = float(row.iloc[1])
        except Exception:
            pass

        # Net Income
        net_income = _get_val_financials(
            fin,
            'Net Income', 'NetIncome', 'netIncome',
            'Net Income Common Stockholders',
        )

        # Para ativos .SA: desconta 'Other Income Expense'
        # (variação cambial que contamina o net_income no yfinance)
        if is_br and net_income is not None:
            try:
                other_income = _get_val_financials(
                    fin,
                    'Other Income Expense',
                    'Non Operating Income',
                    'otherIncomeExpense',
                )
                if (other_income is not None
                        and abs(other_income) > abs(net_income) * 0.5):
                    ebit_proxy = _get_val_financials(
                        fin, 'EBIT', 'Operating Income',
                        'operatingIncome', 'Total Operating Income'
                    )
                    if ebit_proxy is not None:
                        net_income = ebit_proxy * (1 - 0.34)
            except Exception:
                pass

        # Operating Cash Flow
        op_cashflow = _get_val_financials(
            cf,
            'Operating Cash Flow', 'operatingCashFlow',
            'Total Cash From Operating Activities',
            'Cash From Operations',
        )

        # Return on Assets (atual e anterior)
        roa_atual = None
        roa_ant   = None
        try:
            if net_income is not None and total_assets_atual and total_assets_atual > 0:
                roa_atual = net_income / total_assets_atual
            ni_ant = None
            try:
                row_ni = None
                for nome in ['Net Income', 'NetIncome']:
                    if fin is not None and nome in fin.index:
                        row_ni = fin.loc[nome].dropna()
                        break
                if row_ni is not None and len(row_ni) >= 2:
                    ni_ant = float(row_ni.iloc[1])
            except Exception:
                pass
            if ni_ant is not None and total_assets_ant and total_assets_ant > 0:
                roa_ant = ni_ant / total_assets_ant
        except Exception:
            pass

        # Long Term Debt
        debt_atual = _get_val_financials(
            bal,
            'Long Term Debt', 'longTermDebt',
            'Long Term Debt And Capital Lease Obligation',
            'Total Long Term Debt',
        )
        debt_ant = None
        try:
            for nome in ['Long Term Debt', 'longTermDebt',
                         'Long Term Debt And Capital Lease Obligation']:
                if bal is not None and nome in bal.index:
                    row_d = bal.loc[nome].dropna()
                    if len(row_d) >= 2:
                        debt_ant = float(row_d.iloc[1])
                    break
        except Exception:
            pass

        # Current Ratio
        current_ratio_atual = None
        current_ratio_ant   = None
        try:
            ca = _get_val_financials(bal, 'Current Assets', 'currentAssets',
                                      'Total Current Assets')
            cl = _get_val_financials(bal, 'Current Liabilities', 'currentLiabilities',
                                      'Total Current Liabilities')
            if ca and cl and cl > 0:
                current_ratio_atual = ca / cl
            for nome_ca in ['Current Assets', 'Total Current Assets']:
                if bal is not None and nome_ca in bal.index:
                    row_ca = bal.loc[nome_ca].dropna()
                    for nome_cl in ['Current Liabilities', 'Total Current Liabilities']:
                        if nome_cl in bal.index:
                            row_cl = bal.loc[nome_cl].dropna()
                            if len(row_ca) >= 2 and len(row_cl) >= 2:
                                ca2, cl2 = float(row_ca.iloc[1]), float(row_cl.iloc[1])
                                if cl2 > 0:
                                    current_ratio_ant = ca2 / cl2
                            break
                    break
        except Exception:
            pass

        # Shares outstanding (para F7 — diluição)
        shares_atual = _get_val_financials(
            bal, 'Share Issued', 'sharesIssued',
            'Ordinary Shares Number', 'commonStock',
        )
        shares_ant = None
        try:
            for nome in ['Share Issued', 'Ordinary Shares Number']:
                if bal is not None and nome in bal.index:
                    row_s = bal.loc[nome].dropna()
                    if len(row_s) >= 2:
                        shares_ant = float(row_s.iloc[1])
                    break
        except Exception:
            pass

        # Gross Margin (atual e anterior)
        gross_margin_atual = None
        gross_margin_ant   = None
        try:
            rev = _get_val_financials(fin, 'Total Revenue', 'totalRevenue')
            gp  = _get_val_financials(fin, 'Gross Profit', 'grossProfit')
            if rev and rev > 0 and gp is not None:
                gross_margin_atual = gp / rev

            for nome_r in ['Total Revenue', 'totalRevenue']:
                if fin is not None and nome_r in fin.index:
                    row_r = fin.loc[nome_r].dropna()
                    for nome_g in ['Gross Profit', 'grossProfit']:
                        if nome_g in fin.index:
                            row_g = fin.loc[nome_g].dropna()
                            if len(row_r) >= 2 and len(row_g) >= 2:
                                r2 = float(row_r.iloc[1])
                                g2 = float(row_g.iloc[1])
                                if r2 > 0:
                                    gross_margin_ant = g2 / r2
                            break
                    break
        except Exception:
            pass

        # Asset Turnover (F9)
        asset_turnover_atual = None
        asset_turnover_ant   = None
        try:
            rev_val = _get_val_financials(fin, 'Total Revenue', 'totalRevenue')
            if rev_val and total_assets_atual and total_assets_atual > 0:
                asset_turnover_atual = rev_val / total_assets_atual
            for nome_r in ['Total Revenue', 'totalRevenue']:
                if fin is not None and nome_r in fin.index:
                    row_r = fin.loc[nome_r].dropna()
                    if len(row_r) >= 2 and total_assets_ant and total_assets_ant > 0:
                        asset_turnover_ant = float(row_r.iloc[1]) / total_assets_ant
                    break
        except Exception:
            pass

        # ── Critérios Piotroski com try/except individual ─────────────
        f1 = f2 = f3 = f4 = f5 = f6 = f7 = f8 = f9 = 0

        try:
            f1 = 1 if (roa_atual is not None and roa_atual > 0) else 0
        except Exception:
            pass

        try:
            f2 = 1 if (op_cashflow is not None and op_cashflow > 0) else 0
        except Exception:
            pass

        try:
            f3 = 1 if (roa_atual and roa_ant and roa_atual > roa_ant) else 0
        except Exception:
            pass

        try:
            if (op_cashflow and net_income and
                    total_assets_atual and total_assets_atual > 0):
                accrual = op_cashflow / total_assets_atual
                f4 = 1 if accrual > (net_income / total_assets_atual) else 0
        except Exception:
            pass

        # Empresas financeiras são estruturalmente alavancadas — F5 e F6 distorcem
        _setor_lower  = setor.lower()
        _is_financial = any(
            x in _setor_lower
            for x in ['financial', 'bank', 'insurance', 'financeiro',
                      'bancário', 'seguro', 'crédito']
        )

        if _is_financial:
            f5 = None
            f6 = None
        else:
            try:
                _lev_atual = (debt_atual / total_assets_atual) if debt_atual is not None and total_assets_atual is not None and total_assets_atual > 0 else None
                _lev_ant   = (debt_ant / total_assets_ant) if debt_ant is not None and total_assets_ant is not None and total_assets_ant > 0 else None
                f5 = 1 if _lev_atual is not None and _lev_ant is not None and _lev_atual < _lev_ant else 0
            except Exception:
                pass
            try:
                _cr_atual = current_ratio_atual
                _cr_ant   = current_ratio_ant
                f6 = 1 if _cr_atual is not None and _cr_ant is not None and _cr_atual > _cr_ant else 0
            except Exception:
                pass

        try:
            if shares_atual and shares_ant:
                f7 = 1 if shares_atual <= shares_ant * 1.01 else 0
            else:
                f7 = 1
        except Exception:
            f7 = 1

        try:
            f8 = 1 if (gross_margin_atual and gross_margin_ant and
                       gross_margin_atual > gross_margin_ant) else 0
        except Exception:
            pass

        try:
            f9 = 1 if (asset_turnover_atual and asset_turnover_ant and
                       asset_turnover_atual > asset_turnover_ant) else 0
        except Exception:
            pass

        _criterios = [f1, f2, f3, f4, f5, f6, f7, f8, f9]
        _criterios_validos = [c for c in _criterios if c is not None]
        f_score_total = sum(_criterios_validos)
        _n_validos = len(_criterios_validos)
        if _n_validos < 9 and _n_validos > 0:
            f_score_total = round((f_score_total / _n_validos) * 9)

        detalhamento = {
            "F1 ROA positivo":               f1,
            "F2 FCF positivo":               f2,
            "F3 ROA crescendo":              f3,
            "F4 qualidade lucro (FCF>ROA)":  f4,
            "F5 dívida reduzindo":           f5 if f5 is not None else "n/a (financeiro)",
            "F6 liquidez melhorando":        f6 if f6 is not None else "n/a (financeiro)",
            "F7 sem diluição":               f7,
            "F8 margem bruta crescendo":     f8,
            "F9 giro de ativos crescendo":   f9,
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

        # Qualidade do crescimento: receita caindo mas margem expandindo
        if rev_growth is not None and rev_growth < 0 \
           and earnings_growth is not None and earnings_growth > 0.10:
            score_cresc += 4
            alertas_cresc.append(
                "💡 receita em queda mas lucro crescendo — "
                "possível reestruturação e expansão de margem."
            )

        # Penaliza compressão de margem mesmo com receita crescendo
        if rev_growth is not None and rev_growth > 0.05 \
           and earnings_growth is not None and earnings_growth < -0.10:
            score_cresc -= 4
            alertas_cresc.append(
                "⚠️ receita crescendo mas lucro caindo — "
                "compressão de margem. crescimento de baixa qualidade."
            )

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
            # Brasil: IRPJ 15% + adicional IRPJ 10% + CSLL 9% = 34%
            # EUA: federal corporate tax 21%
            tax_rate       = 0.34 if is_br else 0.21
            nopat          = ebit * (1 - tax_rate)
            invested_cap   = total_assets - current_liab

            if invested_cap > 0:
                roic_valor = (nopat / invested_cap) * 100

                selic = macro_context.get('selic', 10.5)

                if is_br:
                    _ke_br   = selic + 7.5
                    _kd_br   = selic * (1 - 0.34)
                    wacc_ref = 0.60 * _ke_br + 0.40 * _kd_br
                else:
                    _rf_us   = macro_context.get('treasury_10y', 4.5)
                    _ke_us   = _rf_us + 5.5
                    _kd_us   = _rf_us * (1 - 0.21)
                    wacc_ref = 0.60 * _ke_us + 0.40 * _kd_us

                wacc_ref = max(6.0, min(25.0, wacc_ref))

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


@st.cache_data(ttl=86400, show_spinner=False)
def _buscar_yield_ntnb() -> float:
    """
    Busca o yield atual da NTN-B 2035 (IPCA+spread) via BCB SGS.
    Série 12466 = taxa indicativa NTN-B Principal 2035.
    Fallback: 6.5% (valor conservador de longo prazo).
    Retorna o yield REAL anualizado em percentual (ex: 6.8).
    """
    try:
        import datetime
        from bcb import sgs
        inicio = (
            datetime.datetime.today() - datetime.timedelta(days=30)
        ).strftime('%Y-%m-%d')
        df = sgs.get({'ntnb': 12466}, start=inicio)
        if not df.empty and 'ntnb' in df.columns:
            val = float(df['ntnb'].dropna().iloc[-1])
            if 3.0 <= val <= 15.0:   # sanidade
                return round(val, 2)
    except Exception:
        pass
    return 6.5   # fallback conservador


def _detectar_segmento_fii(ticker: str, dados: dict) -> str:
    """
    Detecta o segmento do FII com base no ticker e no nome/setor.
    Retorna: 'papel' | 'logistica' | 'lajes' | 'shopping' |
             'residencial' | 'hibrido' | 'fof' | 'desconhecido'
    """
    t = ticker.upper().replace('.SA', '')
    nome = str(dados.get('nome', '') or '').lower()
    setor = str(dados.get('setor', '') or '').lower()

    # FOF — fundos de fundos (geralmente têm "fof" no nome ou ticker)
    if any(x in nome for x in ['fof', 'fundo de fund']):
        return 'fof'
    if t in ['HFOF11', 'KFOF11', 'BCFF11', 'RBRF11', 'FEXC11']:
        return 'fof'

    # Papel (CRI/CRA — renda fixa)
    if any(x in nome for x in ['receb', 'credito', 'cri', 'cra', 'renda fixa']):
        return 'papel'
    if t in ['MXRF11', 'KNCR11', 'KNIP11', 'IRDM11', 'CVBI11',
             'HABT11', 'HCTR11', 'RBRY11', 'RBRR11', 'DEVA11',
             'CPTS11', 'KNHY11', 'KNSC11', 'RZTR11', 'RZAK11',
             'VGHF11', 'VGIR11', 'VGIP11', 'SNCI11', 'RECR11',
             'CACR11', 'BARI11', 'MCCI11']:
        return 'papel'

    # Logística / Galpões
    if any(x in nome for x in ['logist', 'galpão', 'industrial', 'armazem']):
        return 'logistica'
    if t in ['HGLG11', 'BTLG11', 'BRCO11', 'LVBI11', 'VILG11',
             'XPLG11', 'GTWR11', 'TRXF11', 'TGAR11', 'GARE11']:
        return 'logistica'

    # Shoppings
    if any(x in nome for x in ['shopping', 'mall', 'varejo']):
        return 'shopping'
    if t in ['XPML11', 'VISC11', 'MALL11', 'HSML11', 'JSFR11']:
        return 'shopping'

    # Lajes corporativas / Escritórios
    if any(x in nome for x in ['laje', 'escritorio', 'comercial', 'corporate']):
        return 'lajes'
    if t in ['HGRE11', 'BRCR11', 'PVBI11', 'RCRB11', 'JSRE11',
             'RECT11', 'SARE11']:
        return 'lajes'

    # Residencial
    if any(x in nome for x in ['resid', 'habitac', 'moradia']):
        return 'residencial'
    if t in ['HGRU11', 'RBVA11']:
        return 'residencial'

    return 'hibrido'


def calcular_health_score(ticker: str, macro_context: dict = None, hist_externo=None, force: bool = False) -> dict:
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
        # Se score foi calculado nas últimas 24h, retorna do cache (exceto se force=True)
        # threshold > 50 para não servir o fallback de erro (que é exatamente 50)
        if not force:
            try:
                todos_health = get_health_scores()
                if todos_health:
                    h = next((h for h in todos_health if h['ticker'] == ticker), None)
                    if h and h.get('updated_at'):
                        updated = h['updated_at']
                        if isinstance(updated, str):
                            from datetime import datetime as _dt
                            updated = _dt.fromisoformat(updated.replace('Z', '+00:00'))
                        idade = (datetime.now(timezone.utc) - updated).total_seconds()
                        if idade < 86400 and h.get('score', 0) > 50:
                            return {'score': h['score'], 'alertas': [], 'status': 'cached'}
            except Exception:
                pass

        cache = get_todos_fundamentos_cache()
        dados_base = cache.get(ticker, {})
        cache_disponivel = bool(dados_base and dados_base.get('qualidade_dados', 0) >= 40)

        # Tenta price_cache primeiro (mais rápido que yfinance)
        preco_cached = None
        preco_cache_data = get_all_price_cache()
        if ticker in preco_cache_data:
            preco_cached = preco_cache_data[ticker]

        # usar hist_externo se disponível, senão buscar individualmente
        acao_temp = None
        _hist_externo_usado = hist_externo is not None and not (
            isinstance(hist_externo, pd.DataFrame) and hist_externo.empty
        )
        if _hist_externo_usado:
            hist = hist_externo if isinstance(hist_externo, pd.DataFrame) else pd.DataFrame({'Close': hist_externo})
        else:
            acao_temp = yf.Ticker(ticker)
            hist = acao_temp.history(period="1y", auto_adjust=True)
            # yfinance recente pode retornar MultiIndex mesmo para único ticker
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            if not hist.empty and hasattr(hist.index, 'tz') and hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)

        # info (mercado) pode vir vazia se cache tem dados
        info = {}
        if not cache_disponivel:
            try:
                acao_info = acao_temp if acao_temp is not None else yf.Ticker(ticker)
                info = acao_info.info or {}
            except Exception as _e_info:
                logger.warning(f"[health_engine] info yfinance falhou para {ticker}: {_e_info} — usando cache")

        # acao (balanço) para Piotroski/ROIC/Crescimento
        # Quando hist_externo é fornecido (ETL) e cache tem dados, evita chamada extra ao Yahoo
        if is_fii:
            acao = None
        elif acao_temp is not None:
            acao = acao_temp
        elif _hist_externo_usado and cache_disponivel:
            acao = None  # ETL com cache suficiente — pula balanço (sem yfinance extra)
        else:
            acao = yf.Ticker(ticker)

        qualidade = dados_base.get('qualidade_dados', 50)
        dados_confiaveis = qualidade >= 40

        pvp = safe_float(dados_base.get('p/vp')) or safe_float(info.get('priceToBook'))
        _dy_raw_info = safe_float(info.get('dividendYield'))
        _dy_from_info = (_dy_raw_info if _dy_raw_info and _dy_raw_info > 0.30 else (_dy_raw_info * 100 if _dy_raw_info else 0))
        dy = safe_float(dados_base.get('dy%')) or _dy_from_info
        if dy is not None:
            try:
                dy = float(dy)
                if dy > 30 or dy < 0:
                    dy = None
            except (TypeError, ValueError):
                dy = None
        
        score = 0
        alertas = []
        breakdown = {}
        
        if hist.empty or len(hist) < 50:
            # Fallback: usa price_cache se disponível
            if preco_cached and preco_cached.get('rsi_14') is not None:
                pass  # segue com dados minimos
            else:
                payload = {"alertas": ["histórico insuficiente para análise técnica"], "breakdown": {}}
                salvar_health_score(ticker, 50, payload)
                return {'score': 50, 'alertas': ["histórico insuficiente"]}

        close = hist['Close']
        mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.mean()
        preco_atual = close.iloc[-1] if not hist.empty else (float(preco_cached.get('preco', 0)) if preco_cached else 0)

        # RSI: prefere o da price_cache (já calculado no ETL com dados consistentes)
        rsi = None
        if preco_cached and preco_cached.get('rsi_14') is not None:
            rsi = float(preco_cached['rsi_14'])
        if rsi is None and len(close) >= 15:
            delta = close.diff()
            ganho = delta.clip(lower=0).rolling(14).mean()
            perda = (-delta.clip(upper=0)).rolling(14).mean()
            rs = ganho / perda.replace(0, float('nan'))
            rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if len(perda) >= 14 else 50
        if rsi is None:
            rsi = 50
        
        penalidade_tec = 0
        if preco_atual < mm200:
            dist_mm200 = ((preco_atual / float(mm200)) - 1) * 100
            if dist_mm200 < -15:
                penalidade_tec = -8
                alertas.append(
                    f"📉 tendência de baixa severa "
                    f"({dist_mm200:.1f}% abaixo da MM200)."
                )
            else:
                penalidade_tec = -4
                alertas.append(
                    f"⚠️ preço abaixo da MM200 "
                    f"({dist_mm200:.1f}%). monitorar tendência."
                )
            
        penalidade_vix = 0
        if vix_alto:
            beta_val = info.get('beta')

            if beta_val is None and hist is not None and len(hist) >= 60:
                try:
                    bench_ticker = "^BVSP" if is_br or is_fii else "^GSPC"
                    import yfinance as _yf
                    bench_hist = _yf.Ticker(bench_ticker).history(
                        period="1y", auto_adjust=True
                    )
                    if not bench_hist.empty:
                        _ret_ativo = hist['Close'].pct_change().dropna()
                        _ret_bench = bench_hist['Close'].pct_change().dropna()
                        _df_beta   = pd.concat(
                            [_ret_ativo, _ret_bench], axis=1
                        ).dropna()
                        if len(_df_beta) >= 30:
                            _cov = _df_beta.cov().iloc[0, 1]
                            _var = _df_beta.iloc[:, 1].var()
                            beta_val = _cov / _var if _var > 0 else 1.0
                except Exception:
                    beta_val = 1.0

            beta_val = float(beta_val) if beta_val is not None else 1.0

            if beta_val > 1.5:
                penalidade_vix = -10
                alertas.append(
                    f"⚠️ ativo de alto beta ({beta_val:.2f}) "
                    f"em stress global (VIX alto). risco elevado."
                )
            elif beta_val > 1.2:
                penalidade_vix = -6
                alertas.append(
                    f"⚠️ ativo volátil (beta {beta_val:.2f}) "
                    f"em cenário de stress (VIX alto)."
                )

            if not is_fii:
                breakdown['Beta calculado'] = f"{beta_val:.2f}"

        # ══ MOTOR 1: FUNDOS IMOBILIÁRIOS (FIIs) ════════════════════════════════
        # Benchmarks corrigidos: P/VP por segmento, yield vs NTN-B (IPCA+)
        # ══════════════════════════════════════════════════════════════════════
        if is_fii:
            segmento = _detectar_segmento_fii(ticker, dados_base)
            yield_ntnb = _buscar_yield_ntnb()   # yield REAL NTN-B (ex: 6.8%)

            # ── P/VP por segmento ──────────────────────────────────────────
            pvp_thresholds = {
                'papel':       (0.85, 0.95, 1.05),
                'logistica':   (0.90, 1.00, 1.15),
                'lajes':       (0.80, 0.95, 1.10),
                'shopping':    (0.85, 1.00, 1.20),
                'fof':         (0.85, 0.95, 1.05),
                'residencial': (0.88, 1.00, 1.15),
                'hibrido':     (0.88, 1.00, 1.12),
                'desconhecido':(0.88, 1.00, 1.12),
            }
            pvp_lim = pvp_thresholds.get(segmento, (0.88, 1.00, 1.12))

            score_pvp = 0
            if pvp is not None and pvp > 0:
                try:
                    pvp_f = float(pvp)
                    if 0.80 <= pvp_f <= 0.95:
                        score_pvp = 40
                        alertas.append(
                            f"✅ p/vp {pvp_f:.2f} — desconto saudável, "
                            f"melhor ponto de entrada."
                        )
                    elif 0.75 <= pvp_f < 0.80:
                        score_pvp = 30
                        alertas.append(
                            f"✅ p/vp {pvp_f:.2f} — desconto relevante. "
                            f"verificar fundamentos do fundo."
                        )
                    elif 0.95 < pvp_f <= 1.05:
                        score_pvp = 28
                    elif 1.05 < pvp_f <= 1.20:
                        score_pvp = 15
                        alertas.append(
                            f"⚠️ p/vp {pvp_f:.2f} — ágio moderado vs patrimônio."
                        )
                    elif pvp_f > 1.20:
                        score_pvp = 5
                        alertas.append(
                            f"🚨 p/vp {pvp_f:.2f} — ágio elevado. "
                            f"exige crescimento forte dos proventos para justificar."
                        )
                    elif 0.65 <= pvp_f < 0.75:
                        score_pvp = 12
                        alertas.append(
                            f"⚠️ p/vp {pvp_f:.2f} — desconto grande. "
                            f"mercado pode estar precificando vacância ou má gestão."
                        )
                    else:
                        score_pvp = 3
                        alertas.append(
                            f"🚨 p/vp {pvp_f:.2f} — desconto crítico. "
                            f"alto risco de deterioração do patrimônio."
                        )
                except (TypeError, ValueError):
                    score_pvp = 15
            else:
                score_pvp = 15

            # ── Yield vs NTN-B (benchmark correto para FII) ───────────────
            score_y = 0
            if dy is not None and dy > 0:
                try:
                    dy_f = float(dy)

                    ipca_atual = 4.5
                    try:
                        ipca_atual = st.session_state.get(
                            "macro_context", {}
                        ).get("ipca", 4.5)
                    except Exception:
                        pass

                    dy_real = ((1 + dy_f/100) / (1 + ipca_atual/100) - 1) * 100
                    spread = dy_real - yield_ntnb

                    if spread >= 4.0:
                        score_y = 40
                        alertas.append(
                            f"✅ yield real {dy_real:.1f}% — spread {spread:+.1f}pp "
                            f"vs NTN-B ({yield_ntnb:.1f}%). muito atrativo."
                        )
                    elif spread >= 2.0:
                        score_y = 30
                        alertas.append(
                            f"✅ yield real {dy_real:.1f}% — spread {spread:+.1f}pp "
                            f"vs NTN-B adequado."
                        )
                    elif spread >= 0.5:
                        score_y = 18
                        alertas.append(
                            f"ℹ️ yield real {dy_real:.1f}% — spread {spread:+.1f}pp "
                            f"vs NTN-B estreito."
                        )
                    elif spread >= -1.0:
                        score_y = 8
                        alertas.append(
                            f"⚠️ yield real {dy_real:.1f}% — spread {spread:+.1f}pp "
                            f"vs NTN-B ({yield_ntnb:.1f}%). margem insuficiente."
                        )
                    else:
                        score_y = 0
                        alertas.append(
                            f"🚨 yield real {dy_real:.1f}% perde do título público "
                            f"sem risco (NTN-B {yield_ntnb:.1f}%). spread: {spread:+.1f}pp."
                        )

                    breakdown['NTN-B benchmark'] = f"{yield_ntnb:.2f}%"
                    breakdown['DY real']         = f"{dy_real:.1f}%"
                    breakdown['Spread vs NTN-B'] = f"{spread:+.2f}pp"

                except (TypeError, ValueError):
                    score_y = 20
            else:
                score_y = 0
                alertas.append("⚠️ fii sem histórico de proventos recentes.")

            # ── Score total FII e breakdown ───────────────────────────────
            score += score_pvp + score_y
            try:
                _seg_fii = _detectar_segmento_fii(ticker, dados_base)
            except Exception:
                _seg_fii = "fii"
            breakdown = {
                f"Valuation P/VP ({_seg_fii})":   score_pvp,
                "Geração de Renda (Yield NTN-B)": score_y,
                "Momento Técnico (MM200)":        0,
            }

            # ── Penalidade técnica ─────────────────────────────────────────
            score += penalidade_tec

        # ==========================================
        # MOTOR 2 e 3: AÇÕES (B3 vs EUA)
        # ==========================================
        else:
            # setor_yf precisa ser definido antes de calcular_piotroski
            setor_yf = (info.get('sector', '') or dados_base.get('setor', '')).lower()

            if acao is not None:
                f_score, f_detalhamento = calcular_piotroski(acao, setor_yf, is_br=ticker.endswith('.SA'))
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

            # --- Valuation Adaptativo com múltiplos setoriais (máx 26pts) ---
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

            # ── Net Debt / EBITDA — métrica complementar de alavancagem ──────
            score_nd = 0
            try:
                if acao is not None:
                    _bs_nd  = acao.balance_sheet
                    _fin_nd = acao.financials

                    _total_debt = None
                    _cash       = None
                    _ebitda     = None

                    for _nome in ['Total Debt', 'Long Term Debt And Capital '
                                  'Lease Obligation']:
                        if _bs_nd is not None and _nome in _bs_nd.index:
                            _v = _bs_nd.loc[_nome, _bs_nd.columns[0]]
                            if isinstance(_v, pd.Series): _v = _v.iloc[0]
                            if pd.notna(_v):
                                _total_debt = float(_v)
                            break

                    for _nome in ['Cash And Cash Equivalents',
                                  'Cash Cash Equivalents And Short Term Investments']:
                        if _bs_nd is not None and _nome in _bs_nd.index:
                            _v = _bs_nd.loc[_nome, _bs_nd.columns[0]]
                            if isinstance(_v, pd.Series): _v = _v.iloc[0]
                            if pd.notna(_v):
                                _cash = float(_v)
                            break

                    for _nome in ['EBITDA', 'Normalized EBITDA']:
                        if _fin_nd is not None and _nome in _fin_nd.index:
                            _v = _fin_nd.loc[_nome, _fin_nd.columns[0]]
                            if isinstance(_v, pd.Series): _v = _v.iloc[0]
                            if pd.notna(_v):
                                _ebitda = float(_v)
                            break

                    if _total_debt is not None and _cash is not None \
                       and _ebitda is not None and _ebitda > 0:
                        _net_debt = _total_debt - _cash
                        nd_ebitda = _net_debt / _ebitda

                        _lim_cons = 1.5 if is_br else 2.0
                        _lim_mod  = 3.0 if is_br else 3.5
                        _lim_ag   = 4.5 if is_br else 5.0

                        if nd_ebitda < 0:
                            score_nd = 8
                            alertas.append(
                                f"✅ caixa líquido positivo "
                                f"(net debt/ebitda: {nd_ebitda:.1f}x)."
                            )
                        elif nd_ebitda <= _lim_cons:
                            score_nd = 6
                        elif nd_ebitda <= _lim_mod:
                            score_nd = 3
                        elif nd_ebitda <= _lim_ag:
                            score_nd = 0
                            alertas.append(
                                f"⚠️ alavancagem elevada "
                                f"(net debt/ebitda: {nd_ebitda:.1f}x)."
                            )
                        else:
                            score_nd = -6
                            alertas.append(
                                f"🚨 alavancagem crítica "
                                f"(net debt/ebitda: {nd_ebitda:.1f}x). "
                                f"risco de refinanciamento em juros altos."
                            )

                        breakdown['Net Debt / EBITDA'] = f"{nd_ebitda:.1f}x"
            except Exception:
                pass

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
            
            score_r_final = max(0, score_r)

            # ── Interest Coverage Ratio (EBIT / Despesas Financeiras) ────────
            score_icr = 0
            try:
                if acao is not None:
                    _fin_icr = acao.financials
                    if _fin_icr is not None and not _fin_icr.empty:
                        _ebit_icr = None
                        _int_exp_icr = None

                        for _nome in ['EBIT']:
                            if _nome in _fin_icr.index:
                                _v = _fin_icr.loc[_nome, _fin_icr.columns[0]]
                                if isinstance(_v, pd.Series): _v = _v.iloc[0]
                                if pd.notna(_v): _ebit_icr = float(_v)
                                break

                        for _nome in ['Interest Expense',
                                      'Interest Expense Non Operating']:
                            if _nome in _fin_icr.index:
                                _v = _fin_icr.loc[_nome, _fin_icr.columns[0]]
                                if isinstance(_v, pd.Series): _v = _v.iloc[0]
                                if pd.notna(_v):
                                    _int_exp_icr = abs(float(_v))
                                break

                        if _ebit_icr is not None and _int_exp_icr is not None \
                           and _int_exp_icr > 0:
                            icr = _ebit_icr / _int_exp_icr

                            if icr >= 5.0:
                                score_icr = 8
                            elif icr >= 3.0:
                                score_icr = 5
                            elif icr >= 1.5:
                                score_icr = 2
                            elif icr >= 1.0:
                                score_icr = 0
                                alertas.append(
                                    f"⚠️ cobertura de juros baixa "
                                    f"(icr: {icr:.1f}x) — "
                                    f"lucro mal cobre as despesas financeiras."
                                )
                            else:
                                score_icr = -8
                                alertas.append(
                                    f"🚨 cobertura de juros crítica "
                                    f"(icr: {icr:.1f}x) — "
                                    f"ebit insuficiente para cobrir juros."
                                )

                            breakdown['Interest Coverage (EBIT/JurosExp)'] = \
                                f"{icr:.1f}x"
            except Exception:
                pass

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

            # penalidade por múltiplos fundamentais ausentes (P/L, P/VP, ROE, margem)
            _multiplos_presentes = sum(1 for v in [pl, pvp, roe, margem] if v is not None)
            if _multiplos_presentes == 0:
                penalidade_dados -= 25
                alertas.append("🚨 múltiplos fundamentais ausentes (p/l, p/vp, roe, margem). score penalizado.")
            elif _multiplos_presentes <= 1:
                penalidade_dados -= 10
                alertas.append(f"⚠️ poucos múltiplos disponíveis ({_multiplos_presentes}/4). score pode estar subestimado.")

            score = (
                score_q + score_v + score_r_final + score_y
                + score_piotroski + score_crescimento + score_roic
                + score_momentum + score_icr + score_nd
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
                "Cobertura de Juros (ICR)": score_icr,
                "Net Debt / EBITDA": score_nd,
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
        import traceback
        _tb = traceback.format_exc()
        logger.error(f"[health_engine] erro crítico ao calcular health score para {ticker}: {e}\n{_tb}")
        # Não sobrescreve o score salvo no banco — preserva o último valor válido
        try:
            _scores_db = get_health_scores()
            _score_atual = next((h['score'] for h in (_scores_db or []) if h['ticker'] == ticker), 0)
        except Exception:
            _score_atual = 0
        _score_retorno = _score_atual if _score_atual > 50 else 50
        payload = {"alertas": [f"erro no cálculo: {e}", f"traceback: {_tb[:300]}"], "breakdown": {}}
        if _score_atual <= 50:  # só sobrescreve se não há score válido salvo
            salvar_health_score(ticker, 50, payload)
        return {'score': _score_retorno, 'alertas': [f"erro: {e}"], 'status': "⚪ ERRO"}