"""
utils/earnings_scraper.py
Busca resultados financeiros trimestrais.

Fontes:
- BR: Status Invest (statusinvest.com.br/acoes/{ticker})
- EUA: yfinance quarterly financials
"""

import re
import datetime
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
import streamlit as st
from utils.logger import get_logger

logger = get_logger(__name__)

HEADERS_SI = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Referer': 'https://statusinvest.com.br/',
}


def _extrair_num_br(texto: str) -> float | None:
    """Converte string brasileira (1.234,56) em float."""
    txt = (str(texto)
           .strip()
           .replace('R$', '')
           .replace('%', '')
           .strip())
    if not txt or txt in ('-', '—', 'n/d', 'nan'):
        return None
    try:
        if ',' in txt and '.' in txt:
            txt = txt.replace('.', '').replace(',', '.')
        elif ',' in txt:
            txt = txt.replace(',', '.')
        return float(txt)
    except Exception:
        return None


def _calendar_proxima_data(acao_yf) -> str | None:
    """Extrai próxima data de earnings do objeto yfinance (suporta v0.2 e v1.x)."""
    try:
        cal = acao_yf.calendar
        if cal is None:
            return None

        # yfinance >= 1.x retorna dict
        if isinstance(cal, dict):
            for k in ('Earnings Date', 'earningsDate', 'earnings_date'):
                val = cal.get(k)
                if val is not None:
                    if isinstance(val, (list, tuple)) and val:
                        val = val[0]
                    if isinstance(val, pd.Timestamp) and pd.notna(val):
                        return val.strftime('%d/%m/%Y')
                    if isinstance(val, str) and val:
                        return val
            return None

        # yfinance < 1.x retorna DataFrame
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            if 'Earnings Date' in cal.index:
                ed = cal.loc['Earnings Date'].iloc[0]
                if pd.notna(ed) and isinstance(ed, pd.Timestamp):
                    return ed.strftime('%d/%m/%Y')
    except Exception:
        pass
    return None


def _quarterly_financials(acao_yf):
    """Retorna quarterly financials compatível com v0.2 e v1.x."""
    # yfinance 1.x prefere quarterly_income_stmt
    for attr in ('quarterly_income_stmt', 'quarterly_financials'):
        try:
            df = getattr(acao_yf, attr, None)
            if df is not None and not df.empty:
                return df
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# BR — Status Invest
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=21600, show_spinner=False)   # 6 h
def buscar_resultados_br(ticker: str) -> dict:
    """
    Busca resultados trimestrais do Status Invest para ações BR.
    Fallback para yfinance se o scraping falhar.
    """
    resultado = {
        'historico':    [],
        'proxima_data': None,
        'fonte':        'status invest',
        'erro':         None,
    }

    t_clean = ticker.replace('.SA', '').strip().upper()
    url = f"https://statusinvest.com.br/acoes/{t_clean.lower()}"

    try:
        resp = requests.get(url, headers=HEADERS_SI, timeout=12)

        if resp.status_code != 200:
            resultado['erro'] = f"status invest retornou {resp.status_code}"
            return _fallback_yfinance_br(ticker, resultado)

        soup = BeautifulSoup(resp.text, 'lxml')

        # ── Estratégia 1: tabela com palavras-chave de resultados ──
        for tabela in soup.find_all('table'):
            headers_txt = ' '.join(
                th.get_text(strip=True).lower()
                for th in tabela.find_all('th')
            )
            if not any(k in headers_txt for k in ('receita', 'lucro', 'lpa', 'ebitda')):
                continue

            linhas = tabela.find_all('tr')
            # descobre índices de coluna do header
            header_row = linhas[0] if linhas else None
            col_headers = [th.get_text(strip=True).lower()
                           for th in (header_row.find_all(['th', 'td'])
                                      if header_row else [])]

            def _idx(alternativas):
                for a in alternativas:
                    for i, h in enumerate(col_headers):
                        if a in h:
                            return i
                return None

            idx_periodo  = _idx(['trimestre', 'período', 'data', 'quarter']) or 0
            idx_receita  = _idx(['receita'])
            idx_lucro    = _idx(['lucro líq', 'lucro liq', 'lucro net'])
            idx_lpa      = _idx(['lpa', 'eps'])
            idx_margem   = _idx(['margem'])

            for linha in linhas[1:9]:   # últimos 8 trimestres
                cels = linha.find_all(['td', 'th'])
                if not cels:
                    continue

                def _cel(idx):
                    return cels[idx].get_text(strip=True) if idx is not None and idx < len(cels) else None

                periodo = _cel(idx_periodo) or ''
                if not periodo or periodo.lower() in ('—', 'nan', ''):
                    continue

                resultado['historico'].append({
                    'periodo': periodo,
                    'receita': _extrair_num_br(_cel(idx_receita)),
                    'lucro':   _extrair_num_br(_cel(idx_lucro)),
                    'lpa':     _extrair_num_br(_cel(idx_lpa)),
                    'margem':  _extrair_num_br(_cel(idx_margem)),
                })

            if resultado['historico']:
                break

        # ── Próxima data: regex na página inteira ──
        texto_pg = soup.get_text(' ', strip=True)
        padroes = [
            r'próximo resultado[:\s]+(\d{2}/\d{2}/\d{4})',
            r'previsão[:\s]+(\d{2}/\d{2}/\d{4})',
            r'data do resultado[:\s]+(\d{2}/\d{2}/\d{4})',
        ]
        for padrao in padroes:
            m = re.search(padrao, texto_pg, re.IGNORECASE)
            if m:
                resultado['proxima_data'] = m.group(1)
                break

        # Fallback de data via yfinance
        if not resultado['proxima_data']:
            try:
                resultado['proxima_data'] = _calendar_proxima_data(
                    yf.Ticker(ticker)
                )
            except Exception:
                pass

        logger.info(
            f"[earnings] {t_clean}: "
            f"{len(resultado['historico'])} trimestres do Status Invest"
        )

    except Exception as e:
        logger.warning(f"[earnings] falha status invest {t_clean}: {e}")
        resultado['erro'] = str(e)
        resultado = _fallback_yfinance_br(ticker, resultado)

    # Se o scraping não trouxe nada, tenta fallback
    if not resultado['historico']:
        resultado = _fallback_yfinance_br(ticker, resultado)

    return resultado


def _fallback_yfinance_br(ticker: str, resultado: dict) -> dict:
    """Fallback usando yfinance quando Status Invest falha."""
    try:
        acao = yf.Ticker(ticker)
        financials = _quarterly_financials(acao)

        if financials is not None and not financials.empty:
            for col in financials.columns[:8]:
                try:
                    periodo = (col.strftime('%m/%Y')
                               if hasattr(col, 'strftime') else str(col))

                    receita = lucro = None
                    for nome_r in ('Total Revenue', 'Revenue', 'Revenues'):
                        if nome_r in financials.index:
                            v = financials.loc[nome_r, col]
                            if pd.notna(v):
                                receita = float(v) / 1e6
                                break

                    for nome_l in ('Net Income', 'Net Income Common Stockholders',
                                   'Net Income From Continuing Operations'):
                        if nome_l in financials.index:
                            v = financials.loc[nome_l, col]
                            if pd.notna(v):
                                lucro = float(v) / 1e6
                                break

                    margem = None
                    if receita and lucro and receita != 0:
                        margem = lucro / receita * 100

                    resultado['historico'].append({
                        'periodo': periodo,
                        'receita': receita,
                        'lucro':   lucro,
                        'lpa':     None,
                        'margem':  margem,
                    })
                except Exception:
                    continue

            resultado['fonte'] = 'yfinance (fallback)'

        if not resultado.get('proxima_data'):
            resultado['proxima_data'] = _calendar_proxima_data(acao)

    except Exception as e:
        logger.warning(f"[earnings] fallback yfinance {ticker}: {e}")

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# EUA — yfinance
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=21600, show_spinner=False)
def buscar_resultados_us(ticker: str) -> dict:
    """
    Busca resultados trimestrais via yfinance para ações EUA.
    Inclui EPS realizado vs estimado e próxima data.
    """
    resultado = {
        'historico':    [],
        'proxima_data': None,
        'eps_estimado': None,
        'receita_est':  None,
        'fonte':        'yfinance',
        'erro':         None,
    }

    try:
        acao = yf.Ticker(ticker)

        # ── Histórico de EPS (realizado vs estimado) ──
        eps_por_periodo: dict[str, dict] = {}
        for attr in ('earnings_history', 'earnings_dates'):
            try:
                hist_eps = getattr(acao, attr, None)
                if hist_eps is None or (hasattr(hist_eps, 'empty') and hist_eps.empty):
                    continue
                for idx, row in hist_eps.head(8).iterrows():
                    periodo = (idx.strftime('%m/%Y')
                               if hasattr(idx, 'strftime') else str(idx))
                    eps_r = _safe_float_row(row, ('epsActual', 'EPS Actual', 'reported_eps'))
                    eps_e = _safe_float_row(row, ('epsEstimate', 'EPS Estimate', 'eps_estimate'))
                    surpresa = None
                    if eps_r is not None and eps_e is not None and eps_e != 0:
                        surpresa = (eps_r - eps_e) / abs(eps_e) * 100
                    eps_por_periodo[periodo] = {
                        'periodo':  periodo,
                        'eps_real': eps_r,
                        'eps_est':  eps_e,
                        'surpresa': surpresa,
                        'receita':  None,
                        'lucro':    None,
                    }
                if eps_por_periodo:
                    break
            except Exception:
                continue

        resultado['historico'] = list(eps_por_periodo.values())

        # ── Financials trimestrais (receita e lucro) ──
        financials = _quarterly_financials(acao)
        if financials is not None and not financials.empty:
            for i, col in enumerate(financials.columns[:8]):
                periodo = (col.strftime('%m/%Y')
                           if hasattr(col, 'strftime') else str(col))

                receita = lucro = None
                for nome_r in ('Total Revenue', 'Revenue', 'Revenues'):
                    if nome_r in financials.index:
                        v = financials.loc[nome_r, col]
                        if pd.notna(v):
                            receita = float(v) / 1e9
                            break
                for nome_l in ('Net Income', 'Net Income Common Stockholders',
                               'Net Income From Continuing Operations'):
                    if nome_l in financials.index:
                        v = financials.loc[nome_l, col]
                        if pd.notna(v):
                            lucro = float(v) / 1e9
                            break

                # Enriquece entrada existente ou cria nova
                if i < len(resultado['historico']):
                    resultado['historico'][i]['receita'] = receita
                    resultado['historico'][i]['lucro']   = lucro
                else:
                    resultado['historico'].append({
                        'periodo':  periodo,
                        'receita':  receita,
                        'lucro':    lucro,
                        'eps_real': None,
                        'eps_est':  None,
                        'surpresa': None,
                    })

        # ── Próxima data e estimativas ──
        resultado['proxima_data'] = _calendar_proxima_data(acao)

        try:
            cal = acao.calendar
            if isinstance(cal, dict):
                for k in ('Earnings High', 'earningsHigh'):
                    if k in cal and cal[k]:
                        resultado['eps_estimado'] = float(
                            cal[k][0] if isinstance(cal[k], list) else cal[k]
                        )
                        break
                for k in ('Revenue High', 'revenueHigh'):
                    if k in cal and cal[k]:
                        resultado['receita_est'] = float(
                            cal[k][0] if isinstance(cal[k], list) else cal[k]
                        ) / 1e9
                        break
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                if 'Earnings High' in cal.index:
                    v = cal.loc['Earnings High'].iloc[0]
                    if pd.notna(v):
                        resultado['eps_estimado'] = float(v)
                if 'Revenue High' in cal.index:
                    v = cal.loc['Revenue High'].iloc[0]
                    if pd.notna(v):
                        resultado['receita_est'] = float(v) / 1e9
        except Exception:
            pass

        logger.info(
            f"[earnings] {ticker}: "
            f"{len(resultado['historico'])} trimestres do yfinance"
        )

    except Exception as e:
        logger.error(f"[earnings] falha yfinance {ticker}: {e}")
        resultado['erro'] = str(e)

    return resultado


def _safe_float_row(row, keys: tuple) -> float | None:
    for k in keys:
        try:
            v = row.get(k) if hasattr(row, 'get') else row[k]
            if v is not None and pd.notna(v):
                return float(v)
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Roteador principal
# ─────────────────────────────────────────────────────────────────────────────

def buscar_resultados(ticker: str) -> dict:
    """Detecta mercado e chama a fonte correta."""
    if ticker.endswith('.SA'):
        from utils.health_engine import _is_fii
        if _is_fii(ticker):
            return {
                'historico':    [],
                'proxima_data': None,
                'fonte':        'n/a',
                'erro':         None,
                'is_fii':       True,
            }
        return buscar_resultados_br(ticker)
    return buscar_resultados_us(ticker)
