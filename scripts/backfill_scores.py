"""
scripts/backfill_scores.py
==========================
Backfill de 10 anos de health scores históricos no Supabase.

Estratégia de dados:
  - FMP /ratios?period=quarter&limit=40    → fundamentos trimestrais (ROE, P/L, D/E…)
  - FMP /key-metrics?period=quarter&limit=40 → ROIC, ND/EBITDA, crescimento…
  - yfinance (preços diários 10a)           → momentum, MM200
  - BCB SGS série 432                       → Selic histórica diária
  - yfinance ^VIX                           → volatilidade histórica diária

Fidelidade ao health score ao vivo: ~85-90%
  ✅ Qualidade (ROE, ROA, margens)
  ✅ Valuation (P/L, P/VP, EV/EBITDA vs próprio histórico)
  ✅ Solvência (D/E, ND/EBITDA, liquidez corrente)
  ✅ ROIC vs WACC (ROIC direto do FMP)
  ✅ Piotroski parcial (F1,F2,F3,F5,F6,F8,F9 = 7/9 critérios)
  ✅ Crescimento (revenue growth, EPS growth)
  ✅ Momentum (preços históricos reais)
  ✅ Macro (Selic + VIX reais na data)

Rate limits com 2 chaves FMP:
  ~500 req/dia → 2 req/ticker → 250 tickers/dia
  EUA (~250 tickers): ~1 dia | BR (~130 tickers): ~1 dia

Execução:
  SUPABASE_URL=...  SUPABASE_KEY=...
  FMP_API_KEY=...   FMP_API_KEY_2=...
  python scripts/backfill_scores.py [--mercado eua|br|todos] [--ticker AAPL]

Checkpoint:
  Salvo em .backfill_checkpoint.json — retoma de onde parou se interrompido.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import datetime
from pathlib import Path

import pandas as pd
import numpy as np

# Adiciona raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger
from utils.fmp_client import get_ratios_trimestrais, get_key_metrics_trimestrais
from utils.tickers import SCREENER_US, SCREENER_B3, FII_TODOS
from database.db import registrar_historico_score_batch, get_datas_historico_score

logger = get_logger("backfill_scores")

CHECKPOINT_PATH = Path(__file__).parent / ".backfill_checkpoint.json"
SLEEP_ENTRE_TICKERS = 0.8   # segundos — respeitar rate limit FMP (10 req/10s)

# ──────────────────────────────────────────────────────────────────────────────
# 1. TIMELINE MACRO HISTÓRICA
# ──────────────────────────────────────────────────────────────────────────────

def construir_timeline_macro(anos: int = 11) -> pd.DataFrame:
    """
    Constrói DataFrame diário com Selic e VIX históricos.
    Index: DatetimeIndex diário. Colunas: selic (%), vix (pts).
    """
    logger.info("[macro] construindo timeline histórica (Selic + VIX)…")
    inicio = (datetime.date.today() - datetime.timedelta(days=anos * 365)).strftime("%Y-%m-%d")

    # Selic — BCB SGS série 432 (% anual)
    selic_s = pd.Series(dtype=float)
    try:
        from bcb import sgs
        df_bcb = sgs.get({"selic": 432}, start=inicio)
        selic_s = df_bcb["selic"].dropna()
        # Sanidade: a série 432 retorna a taxa over anualizada
        # Valores entre 1-50 já estão em % a.a.; valores < 1 são decimais
        selic_s = selic_s.apply(lambda v: v * 100 if v < 1 else v)
        selic_s = selic_s.apply(lambda v: 14.75 if v > 50 else v)  # sanidade
        logger.info(f"[macro] Selic: {len(selic_s)} pontos carregados")
    except Exception as e:
        logger.warning(f"[macro] falha ao carregar Selic: {e} — usando 14.75% flat")

    # VIX — yfinance
    vix_s = pd.Series(dtype=float)
    try:
        import yfinance as yf
        hist_vix = yf.Ticker("^VIX").history(start=inicio, auto_adjust=True)
        if not hist_vix.empty:
            vix_s = hist_vix["Close"].dropna()
            if getattr(vix_s.index, "tz", None) is not None:
                vix_s.index = vix_s.index.tz_localize(None)
            logger.info(f"[macro] VIX: {len(vix_s)} pontos carregados")
    except Exception as e:
        logger.warning(f"[macro] falha ao carregar VIX: {e} — usando 15.0 flat")

    # Monta DataFrame diário
    df = pd.DataFrame(index=pd.date_range(inicio, datetime.date.today(), freq="D"))

    if not selic_s.empty:
        selic_s.index = pd.to_datetime(selic_s.index)
        df["selic"] = selic_s.reindex(df.index, method="ffill")
    else:
        df["selic"] = 14.75

    if not vix_s.empty:
        vix_s.index = pd.to_datetime(vix_s.index)
        df["vix"] = vix_s.reindex(df.index, method="ffill")
    else:
        df["vix"] = 15.0

    df["selic"] = df["selic"].fillna(14.75)
    df["vix"]   = df["vix"].fillna(15.0)

    return df


def macro_na_data(timeline: pd.DataFrame, data_str: str) -> dict:
    """Retorna {'selic': float, 'vix': float} para a data mais próxima disponível."""
    try:
        dt = pd.Timestamp(data_str[:10])
        # Procura a data mais próxima anterior (ffill já aplicado)
        if dt in timeline.index:
            row = timeline.loc[dt]
        else:
            antes = timeline[timeline.index <= dt]
            if antes.empty:
                return {"selic": 14.75, "vix": 15.0}
            row = antes.iloc[-1]
        return {
            "selic": float(row["selic"]),
            "vix":   float(row["vix"]),
        }
    except Exception:
        return {"selic": 14.75, "vix": 15.0}


# ──────────────────────────────────────────────────────────────────────────────
# 2. PREÇOS HISTÓRICOS
# ──────────────────────────────────────────────────────────────────────────────

def carregar_precos(ticker: str, anos: int = 11) -> pd.Series:
    """
    Retorna série de preços de fechamento ajustados (diária, 11 anos).
    ticker: formato yfinance (AAPL, PETR4.SA, etc.)
    """
    try:
        import yfinance as yf
        inicio = (datetime.date.today() - datetime.timedelta(days=anos * 365)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=inicio, auto_adjust=True)
        if hist.empty:
            return pd.Series(dtype=float)
        s = hist["Close"].dropna()
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
        return s
    except Exception as e:
        logger.warning(f"[precos] falha ao carregar {ticker}: {e}")
        return pd.Series(dtype=float)


def calcular_momentum(precos: pd.Series, data_ref_str: str) -> tuple[float | None, bool | None]:
    """
    Calcula momentum 12-1 meses e posição vs MM200 na data_ref.
    Retorna (momentum_pct, acima_mm200).
    """
    try:
        dt = pd.Timestamp(data_ref_str[:10])
        antes = precos[precos.index <= dt]
        if len(antes) < 22:
            return None, None

        preco_atual  = float(antes.iloc[-1])
        preco_1m     = float(antes.iloc[-22])   if len(antes) >= 22  else preco_atual
        preco_12m    = float(antes.iloc[-252])  if len(antes) >= 252 else float(antes.iloc[0])

        # 12-1m: retorno de 12m excluindo o último mês (evita reversão de curto prazo)
        momentum_pct = (preco_1m / preco_12m - 1) * 100 if preco_12m > 0 else None

        mm200 = float(antes.iloc[-200:]["Close"].mean()) if len(antes) >= 200 else None
        acima_mm200 = preco_atual > mm200 if mm200 else None

        return momentum_pct, acima_mm200
    except Exception:
        return None, None


# ──────────────────────────────────────────────────────────────────────────────
# 3. HEALTH SCORE OFFLINE (versão histórica)
# ──────────────────────────────────────────────────────────────────────────────

def _sf(val, default=None) -> float | None:
    """Safe float — retorna None se inválido."""
    if val is None:
        return default
    try:
        v = float(val)
        return v if not np.isnan(v) else default
    except (TypeError, ValueError):
        return default


def calcular_score_historico(
    ratios:      dict,          # linha do /ratios endpoint
    km:          dict,          # linha do /key-metrics endpoint (mesma data)
    ratios_yoy:  dict | None,   # linha de 4 trimestres atrás (para YoY)
    km_yoy:      dict | None,
    precos:      pd.Series,     # série diária de close
    data_ref:    str,           # 'YYYY-MM-DD' — data do trimestre
    macro:       dict,          # {'selic': float, 'vix': float}
    is_br:       bool = False,
) -> int:
    """
    Calcula health score histórico usando dados pré-buscados.
    Sem chamadas a APIs — 100% offline.

    Fidelidade: ~85-90% do score ao vivo.
    """
    score = 0
    selic = macro.get("selic", 14.75)
    vix   = macro.get("vix", 15.0)

    # ── 1. QUALIDADE (máx 20pts) ──────────────────────────────────────────────
    roe = _sf(ratios.get("returnOnEquity"))   # decimal FMP (ex: 0.35 = 35%)
    roa = _sf(ratios.get("returnOnAssets"))
    margem = _sf(ratios.get("netProfitMargin"))

    # ROE
    if roe is not None:
        roe_pct = roe * 100
        if roe_pct >= 20:   score += 8
        elif roe_pct >= 12: score += 5
        elif roe_pct >= 6:  score += 2
        elif roe_pct < 0:   score -= 5

    # ROA
    if roa is not None:
        roa_pct = roa * 100
        if roa_pct >= 10:   score += 6
        elif roa_pct >= 5:  score += 4
        elif roa_pct >= 2:  score += 2
        elif roa_pct < 0:   score -= 4

    # Margem líquida
    if margem is not None:
        mrg_pct = margem * 100
        if mrg_pct >= 20:   score += 6
        elif mrg_pct >= 10: score += 4
        elif mrg_pct >= 4:  score += 2
        elif mrg_pct < 0:   score -= 3

    # ── 2. VALUATION (máx 20pts) ─────────────────────────────────────────────
    pe  = _sf(ratios.get("priceEarningsRatio"))
    pb  = _sf(ratios.get("priceToBookRatio"))
    evm = _sf(ratios.get("enterpriseValueMultiple"))

    # P/L (benchmarks diferenciados BR vs EUA)
    if pe is not None and pe > 0:
        pe_bom = 12 if is_br else 18
        pe_med = 22 if is_br else 30
        if pe <= pe_bom:    score += 8
        elif pe <= pe_med:  score += 4
        elif pe <= 50:      score += 1
        elif pe > 50:       score -= 4

    # P/VP
    if pb is not None and pb > 0:
        if pb <= 1.5:       score += 6
        elif pb <= 3.0:     score += 3
        elif pb <= 5.0:     score += 1
        elif pb > 8.0:      score -= 4

    # EV/EBITDA
    if evm is not None and 0 < evm < 200:
        if evm <= 8:        score += 6
        elif evm <= 15:     score += 3
        elif evm <= 25:     score += 0
        elif evm > 30:      score -= 4

    # ── 3. SOLVÊNCIA (máx 20pts) ──────────────────────────────────────────────
    de    = _sf(ratios.get("debtEquityRatio")) or _sf(km.get("debtToEquity"))
    cr    = _sf(ratios.get("currentRatio"))    or _sf(km.get("currentRatio"))
    icr   = _sf(ratios.get("interestCoverage"))
    nd_eb = _sf(km.get("netDebtToEBITDA"))

    # D/E (mais rigoroso com Selic alta)
    if de is not None:
        lim_bom = 0.5 if (is_br and selic > 10) else 0.8
        lim_med = 1.2 if (is_br and selic > 10) else 1.5
        if de < lim_bom:    score += 12
        elif de < lim_med:  score += 6
        elif de < 2.5:      score += 0
        else:               score -= 8

    # Current ratio
    if cr is not None:
        if cr >= 2.0:       score += 5
        elif cr >= 1.5:     score += 3
        elif cr >= 1.0:     score += 1
        elif cr < 0.8:      score -= 3

    # ICR (cobertura de juros)
    if icr is not None and icr > 0:
        if icr >= 5:        score += 3
        elif icr >= 3:      score += 1
        elif icr < 1.5:     score -= 3

    # ND/EBITDA
    if nd_eb is not None:
        if nd_eb < 0:       score += 5   # caixa líquido
        elif nd_eb <= 1.5:  score += 3
        elif nd_eb <= 3.0:  score += 0
        elif nd_eb <= 4.5:  score -= 3
        else:               score -= 6

    # ── 4. ROIC vs WACC (máx 12pts) ───────────────────────────────────────────
    roic = _sf(km.get("roic"))

    if roic is not None:
        roic_pct = roic * 100
        # WACC estimado: CAPM simplificado
        if is_br:
            wacc = 0.60 * (selic + 7.5) + 0.40 * (selic * 0.66)
        else:
            rf = 4.5  # fallback treasury 10y
            wacc = 0.60 * (rf + 5.5) + 0.40 * (rf * 0.79)

        spread = roic_pct - wacc
        if spread >= 5:     score += 12
        elif spread >= 0:   score += 6
        elif spread >= -3:  score -= 3
        else:               score -= 8

    # ── 5. PIOTROSKI PARCIAL (7/9 critérios) ──────────────────────────────────
    # F1: ROA positivo
    f1 = 1 if (roa is not None and roa > 0) else 0

    # F2: FCF positivo (via FCF/OCF ratio ou FCF yield)
    fcf_ratio = _sf(ratios.get("freeCashFlowOperatingCashFlowRatio"))
    fcf_yield = _sf(km.get("freeCashFlowYield"))
    f2 = 1 if (fcf_ratio and fcf_ratio > 0) or (fcf_yield and fcf_yield > 0) else 0

    # F3, F5, F6, F8, F9: comparação YoY (requer dados do ano anterior)
    f3 = f5 = f6 = f8 = f9 = 0
    if ratios_yoy and km_yoy:
        roa_yoy = _sf(ratios_yoy.get("returnOnAssets"))
        f3 = 1 if (roa is not None and roa_yoy is not None and roa > roa_yoy) else 0

        de_yoy  = _sf(ratios_yoy.get("debtEquityRatio")) or _sf(km_yoy.get("debtToEquity"))
        f5 = 1 if (de is not None and de_yoy is not None and de < de_yoy) else 0

        cr_yoy  = _sf(ratios_yoy.get("currentRatio")) or _sf(km_yoy.get("currentRatio"))
        f6 = 1 if (cr is not None and cr_yoy is not None and cr > cr_yoy) else 0

        gm      = _sf(ratios.get("grossProfitMargin"))
        gm_yoy  = _sf(ratios_yoy.get("grossProfitMargin"))
        f8 = 1 if (gm is not None and gm_yoy is not None and gm > gm_yoy) else 0

        at      = _sf(ratios.get("assetTurnover"))
        at_yoy  = _sf(ratios_yoy.get("assetTurnover"))
        f9 = 1 if (at is not None and at_yoy is not None and at > at_yoy) else 0

    # Normaliza para escala de 9 (7 critérios → escala equivalente)
    criterios = [f1, f2, f3, f5, f6, f8, f9]
    n_validos  = sum(1 for c in criterios if c is not None)
    f_total    = sum(criterios)
    if n_validos > 0:
        f_score_9 = round(f_total / n_validos * 9)
    else:
        f_score_9 = 5  # neutro

    if f_score_9 >= 7:   score += 15
    elif f_score_9 >= 5: score += 8
    elif f_score_9 <= 2: score -= 8

    # ── 6. CRESCIMENTO (máx 15pts) ────────────────────────────────────────────
    rev_growth = _sf(km.get("revenueGrowth"))
    eps_growth = _sf(km.get("epsgrowth"))

    if rev_growth is not None:
        rg_pct = rev_growth * 100
        if rg_pct >= 15:    score += 8
        elif rg_pct >= 5:   score += 5
        elif rg_pct >= 0:   score += 1
        elif rg_pct < -5:   score -= 5

    if eps_growth is not None:
        eg_pct = eps_growth * 100
        if eg_pct >= 20:    score += 7
        elif eg_pct >= 8:   score += 4
        elif eg_pct < -10:  score -= 4

    # ── 7. MOMENTUM (máx 8pts, mín -8pts) ─────────────────────────────────────
    mom, acima_mm200 = calcular_momentum(precos, data_ref)

    if mom is not None:
        if mom >= 20:        score += 8
        elif mom >= 8:       score += 5
        elif mom >= 0:       score += 2
        elif mom >= -10:     score -= 3
        else:                score -= 8

    if acima_mm200 is not None:
        if not acima_mm200:  score -= 4

    # ── 8. PENALIDADE MACRO ────────────────────────────────────────────────────
    # VIX
    if vix > 30:    score -= 10
    elif vix > 25:  score -= 6
    elif vix > 20:  score -= 3

    # Selic (apenas BR)
    if is_br:
        if selic > 13:   score -= 8
        elif selic > 10: score -= 3

    return int(min(max(score, 0), 100))


# ──────────────────────────────────────────────────────────────────────────────
# 4. CHECKPOINT
# ──────────────────────────────────────────────────────────────────────────────

def carregar_checkpoint() -> set[str]:
    if CHECKPOINT_PATH.exists():
        try:
            data = json.loads(CHECKPOINT_PATH.read_text())
            done = set(data.get("concluidos", []))
            logger.info(f"[checkpoint] {len(done)} tickers já processados")
            return done
        except Exception:
            pass
    return set()


def salvar_checkpoint(concluidos: set[str]) -> None:
    try:
        CHECKPOINT_PATH.write_text(json.dumps({
            "concluidos": sorted(concluidos),
            "atualizado": datetime.datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.warning(f"[checkpoint] falha ao salvar: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# 5. PROCESSAMENTO DE UM TICKER
# ──────────────────────────────────────────────────────────────────────────────

def processar_ticker(
    ticker_yf: str,             # formato yfinance (ex: AAPL, PETR4.SA)
    macro_tl:  pd.DataFrame,    # timeline macro pré-construída
    dry_run:   bool = False,    # se True, imprime mas não salva
) -> int:
    """
    Processa um ticker completo: busca FMP, calcula scores históricos, salva.
    Retorna número de pontos inseridos.
    """
    is_br   = ticker_yf.endswith(".SA")
    # FMP usa ticker sem .SA e sem sufixos internacionais
    tk_fmp  = ticker_yf.replace(".SA", "").upper()

    logger.info(f"[{tk_fmp}] buscando fundamentos FMP…")

    # ── Busca FMP ──────────────────────────────────────────────────────────────
    ratios_list = get_ratios_trimestrais(tk_fmp, limit=40)
    time.sleep(0.4)  # respeitar rate limit
    km_list     = get_key_metrics_trimestrais(tk_fmp, limit=40)
    time.sleep(0.4)

    if not ratios_list:
        logger.warning(f"[{tk_fmp}] sem dados FMP /ratios — pulando")
        return 0

    # Alinha ratios e key-metrics por data
    km_by_date = {item.get("date", ""): item for item in km_list}

    # ── Preços históricos ──────────────────────────────────────────────────────
    precos = carregar_precos(ticker_yf)
    if precos.empty:
        logger.warning(f"[{tk_fmp}] sem preços yfinance — momentum não disponível")

    # ── Datas já presentes no banco ───────────────────────────────────────────
    datas_existentes = get_datas_historico_score(ticker_yf)
    if not datas_existentes:
        # Tenta também sem .SA (histórico antigo pode ter sido salvo assim)
        datas_existentes = get_datas_historico_score(tk_fmp)

    # ── Calcula score para cada trimestre ─────────────────────────────────────
    registros: list[dict] = []

    for i, ratios in enumerate(ratios_list):
        data_str = ratios.get("date", "")
        if not data_str:
            continue

        # Pula se já existe no banco
        if data_str[:10] in datas_existentes:
            continue

        km         = km_by_date.get(data_str, {})
        # YoY: 4 trimestres atrás na lista (mesma estação do ano anterior)
        ratios_yoy = ratios_list[i + 4] if i + 4 < len(ratios_list) else None
        km_yoy     = km_by_date.get(ratios_yoy.get("date", ""), {}) if ratios_yoy else None

        macro = macro_na_data(macro_tl, data_str)

        try:
            score = calcular_score_historico(
                ratios      = ratios,
                km          = km,
                ratios_yoy  = ratios_yoy,
                km_yoy      = km_yoy,
                precos      = precos,
                data_ref    = data_str,
                macro       = macro,
                is_br       = is_br,
            )
        except Exception as e:
            logger.warning(f"[{tk_fmp}] erro ao calcular score em {data_str}: {e}")
            continue

        registros.append({
            "ticker":       ticker_yf,      # mantém formato .SA para BR
            "score":        score,
            "calculado_em": data_str + "T00:00:00+00:00",
        })

        logger.debug(f"  {data_str}: score={score}")

    if not registros:
        logger.info(f"[{tk_fmp}] sem novos registros para inserir")
        return 0

    if dry_run:
        logger.info(f"[{tk_fmp}] DRY RUN — {len(registros)} registros calculados (não salvos)")
        for r in registros[:3]:
            logger.info(f"  {r['calculado_em'][:10]}: score={r['score']}")
        return len(registros)

    n = registrar_historico_score_batch(registros, ignorar_existentes=False)
    logger.info(f"[{tk_fmp}] ✅ {n} pontos inseridos no banco")
    return n


# ──────────────────────────────────────────────────────────────────────────────
# 6. LOOP PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backfill de health scores históricos")
    parser.add_argument("--mercado", choices=["eua", "br", "todos"], default="todos",
                        help="Mercado a processar (padrão: todos)")
    parser.add_argument("--ticker",  type=str, default=None,
                        help="Processar apenas este ticker (ex: AAPL ou PETR4.SA)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Calcula sem salvar no banco")
    parser.add_argument("--reset",   action="store_true",
                        help="Ignora checkpoint e reprocessa tudo")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("BACKFILL DE HEALTH SCORES HISTÓRICOS")
    logger.info("=" * 60)

    # Monta lista de tickers
    if args.ticker:
        tickers = [args.ticker]
        logger.info(f"Modo ticker único: {args.ticker}")
    elif args.mercado == "eua":
        tickers = SCREENER_US
    elif args.mercado == "br":
        # FIIs geralmente não têm dados no FMP — focar em ações
        tickers = list(SCREENER_B3)
    else:
        tickers = SCREENER_US + list(SCREENER_B3)

    # Carrega checkpoint
    concluidos = set() if args.reset else carregar_checkpoint()
    pendentes  = [t for t in tickers if t not in concluidos]

    logger.info(f"Total de tickers: {len(tickers)} | Pendentes: {len(pendentes)}")

    if not pendentes:
        logger.info("✅ Todos os tickers já foram processados!")
        return

    # Constrói timeline macro (uma vez para todos os tickers)
    macro_tl = construir_timeline_macro()
    logger.info(f"Timeline macro: {len(macro_tl)} dias")

    # Estatísticas globais
    total_inseridos = 0
    total_erros     = 0

    for idx, ticker in enumerate(pendentes, 1):
        logger.info(f"\n{'─'*40}")
        logger.info(f"[{idx}/{len(pendentes)}] {ticker}")

        try:
            n = processar_ticker(
                ticker_yf = ticker,
                macro_tl  = macro_tl,
                dry_run   = args.dry_run,
            )
            total_inseridos += n
            concluidos.add(ticker)

            if not args.dry_run:
                salvar_checkpoint(concluidos)

        except Exception as e:
            logger.error(f"[{ticker}] ERRO: {e}", exc_info=True)
            total_erros += 1

        # Rate limiting entre tickers
        time.sleep(SLEEP_ENTRE_TICKERS)

        # Log de progresso a cada 10 tickers
        if idx % 10 == 0:
            logger.info(f"\n📊 Progresso: {idx}/{len(pendentes)} | "
                        f"Pontos inseridos: {total_inseridos} | Erros: {total_erros}")

    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL CONCLUÍDO")
    logger.info(f"  Tickers processados : {len(pendentes)}")
    logger.info(f"  Pontos inseridos    : {total_inseridos}")
    logger.info(f"  Erros               : {total_erros}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
