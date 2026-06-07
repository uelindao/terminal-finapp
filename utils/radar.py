"""
utils/radar.py — Radar de oportunidades (isolado de Streamlit commands)
Evita reexecução de widgets do Home.py ao importar.
"""
import streamlit as st
import yfinance as yf
import numpy as np


@st.cache_data(ttl=1800, show_spinner=False)
def calcular_oportunidades_watchlist(
    tickers_tuple: tuple,
    modo: str = "entrada",
) -> list[dict]:
    """
    Radar de oportunidades com score reformulado.

    Pesos:
      55% — health score (qualidade + momentum já embutido)
      20% — valuation vs histórico próprio (FMP percentil)
      25% — timing de entrada (RSI + micro-recuperação +
             distância do topo com filtro de estabilização)

    modo:
      "entrada"    — qualidade + desconto + estabilização
      "realizacao" — sobrecomprado, possível redução
      "dividendo"  — yield real vs NTN-B atrativo
    """
    tickers = list(tickers_tuple)
    if not tickers:
        return []

    from database.db import get_health_scores, get_todos_fundamentos_cache
    from utils.tickers import mapear_ticker_base
    from utils.fmp_client import get_multiplos_medios

    hs_all   = {h['ticker']: h for h in (get_health_scores() or [])}
    fund_all = get_todos_fundamentos_cache()

    resultados = []

    for ticker in tickers:
        t_base  = mapear_ticker_base(ticker)
        hs_row  = hs_all.get(t_base) or hs_all.get(ticker)
        if not hs_row:
            continue

        score_hs = float(hs_row.get('score', 50) or 50)

        score_min = 55 if modo in ("entrada", "dividendo") else 50
        if score_hs < score_min:
            continue

        try:
            hist = yf.Ticker(t_base).history(
                period="1y", auto_adjust=True
            )
            if hist.empty or len(hist) < 60:
                continue

            close = hist['Close'].dropna()

            preco_atual = float(close.iloc[-1])
            high_52w    = float(close.max())
            low_52w     = float(close.min())

            preco_1m  = float(close.iloc[-21])  if len(close) >= 21  else preco_atual
            preco_3m  = float(close.iloc[-63])  if len(close) >= 63  else preco_atual
            preco_6m  = float(close.iloc[-126]) if len(close) >= 126 else preco_atual
            preco_5d  = float(close.iloc[-5])   if len(close) >= 5   else preco_atual
            preco_10d = float(close.iloc[-10])  if len(close) >= 10  else preco_atual

            ret_1m  = (preco_atual / preco_1m  - 1) * 100
            ret_3m  = (preco_atual / preco_3m  - 1) * 100
            ret_6m  = (preco_atual / preco_6m  - 1) * 100
            ret_5d  = (preco_atual / preco_5d  - 1) * 100
            ret_10d = (preco_atual / preco_10d - 1) * 100

            dist_top = (preco_atual / high_52w - 1) * 100

            def _calc_rsi(series, period=14):
                delta = series.diff().dropna()
                gain  = delta.clip(lower=0).rolling(period).mean()
                loss  = (-delta.clip(upper=0)).rolling(period).mean()
                rs    = gain / loss.replace(0, float('nan'))
                return float(100 - (100 / (1 + rs)).iloc[-1])

            try:
                rsi = _calc_rsi(close)
            except Exception:
                rsi = 50.0

            pts_hs = round((score_hs / 100) * 55, 1)

            pts_val = 10.0
            _val_computed = False

            # 1ª tentativa: percentil histórico FMP (5 anos) — mais preciso
            try:
                _medios = get_multiplos_medios(t_base, anos=5)
                if _medios:
                    _stats_pe = _medios.get('pe') or _medios.get('pb')
                    if _stats_pe:
                        _atual_v = _stats_pe.get('atual')
                        _min_v   = _stats_pe.get('min')
                        _max_v   = _stats_pe.get('max')
                        if all(v is not None for v in [_atual_v, _min_v, _max_v]):
                            _banda = _max_v - _min_v
                            if _banda > 0:
                                _pct = (_atual_v - _min_v) / _banda
                                if _pct <= 0.20:   pts_val = 20.0
                                elif _pct <= 0.35: pts_val = 15.0
                                elif _pct <= 0.50: pts_val = 10.0
                                elif _pct <= 0.70: pts_val = 5.0
                                else:              pts_val = 0.0
                                _val_computed = True
            except Exception:
                pass

            # 2ª tentativa: P/L atual do cache de fundamentos (backfill)
            if not _val_computed:
                _fund = fund_all.get(t_base, {})
                _pl   = _fund.get('p/l')
                _pvpa = _fund.get('p/vp')
                _is_br = t_base.endswith('.SA')

                if _pl is not None:
                    try:
                        _pl = float(_pl)
                        if _pl > 0:
                            # Thresholds ajustados por mercado:
                            # BR ~10-15x histórico; EUA ~18-22x histórico
                            if _is_br:
                                if   _pl <= 7:   pts_val = 20.0
                                elif _pl <= 11:  pts_val = 16.0
                                elif _pl <= 16:  pts_val = 10.0
                                elif _pl <= 23:  pts_val = 5.0
                                else:            pts_val = 1.0
                            else:
                                if   _pl <= 12:  pts_val = 20.0
                                elif _pl <= 18:  pts_val = 16.0
                                elif _pl <= 26:  pts_val = 10.0
                                elif _pl <= 38:  pts_val = 5.0
                                else:            pts_val = 1.0
                            _val_computed = True
                    except (TypeError, ValueError):
                        pass

                # 3ª tentativa: P/VPA se P/L indisponível
                if not _val_computed and _pvpa is not None:
                    try:
                        _pvpa = float(_pvpa)
                        if _pvpa > 0:
                            if   _pvpa <= 1.0: pts_val = 18.0
                            elif _pvpa <= 2.0: pts_val = 14.0
                            elif _pvpa <= 3.5: pts_val = 9.0
                            elif _pvpa <= 6.0: pts_val = 4.0
                            else:              pts_val = 1.0
                            _val_computed = True
                    except (TypeError, ValueError):
                        pass

                # sem nenhum dado de múltiplo → neutro 10

            pts_timing = 0.0

            if modo == "entrada":
                queda_acelerada = ret_6m < -25 and ret_3m < -10
                if not queda_acelerada:
                    if dist_top < -30:
                        pts_timing += 10.0
                    elif dist_top < -15:
                        pts_timing += 7.0
                    elif dist_top < -5:
                        pts_timing += 4.0
                    else:
                        pts_timing += 1.0

                if 35 <= rsi <= 48:
                    pts_timing += 10.0
                elif 48 < rsi <= 55:
                    pts_timing += 6.0
                elif rsi < 35:
                    pts_timing += 3.0

                if ret_3m < -5 and ret_10d > 0 and ret_5d > 0:
                    pts_timing += 5.0
                elif ret_3m < -5 and ret_10d > 0:
                    pts_timing += 2.0

                if ret_1m < -15 and ret_3m < -15 and ret_5d < 0:
                    pts_timing = 0.0

            elif modo == "realizacao":
                if rsi > 70:
                    pts_timing += 12.0
                elif rsi > 65:
                    pts_timing += 8.0

                if dist_top > -5:
                    pts_timing += 8.0
                elif dist_top > -10:
                    pts_timing += 4.0

                if ret_3m > 30:
                    pts_timing += 5.0

            elif modo == "dividendo":
                try:
                    from utils.health_engine import (
                        _buscar_yield_ntnb,
                    )
                    fund_d   = fund_all.get(t_base, {})
                    dy       = float(fund_d.get('dy%') or 0)
                    ntnb     = _buscar_yield_ntnb()
                    ipca     = st.session_state.get(
                        'macro_context', {}
                    ).get('ipca', 4.5)
                    dy_real  = ((1 + dy/100) / (1 + ipca/100) - 1) * 100
                    spread   = dy_real - ntnb

                    if spread >= 3.0:
                        pts_timing += 15.0
                    elif spread >= 1.5:
                        pts_timing += 10.0
                    elif spread >= 0:
                        pts_timing += 5.0
                    else:
                        pts_timing = 0.0
                except Exception:
                    pts_timing = 8.0

            score_assim = round(pts_hs + pts_val + pts_timing, 1)

            if score_assim < 30:
                continue

            fund_d = fund_all.get(t_base, {})
            nome   = fund_d.get('nome') or ticker.replace('.SA', '')
            setor  = fund_d.get('setor') or '—'

            resultados.append({
                'ticker':      ticker,
                't_base':      t_base,
                'nome':        nome[:28],
                'setor':       setor,
                'mercado':     'BR' if ticker.endswith('.SA') else 'EUA',
                'score_hs':    score_hs,
                'score_val':   round(pts_val, 1),
                'score_timing':round(pts_timing, 1),
                'score_assim': score_assim,
                'ret_1m':      round(ret_1m, 2),
                'ret_3m':      round(ret_3m, 2),
                'ret_5d':      round(ret_5d, 2),
                'dist_top':    round(dist_top, 2),
                'rsi':         round(rsi, 1),
                'preco_atual': round(preco_atual, 2),
                'modo':        modo,
            })

        except Exception:
            continue

    return sorted(
        resultados,
        key=lambda x: x['score_assim'],
        reverse=True,
    )[:5]
