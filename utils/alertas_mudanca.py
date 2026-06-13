"""
utils/alertas_mudanca.py — detector de mudanças relevantes em tickers.

Diferente de alertas de threshold absoluto (ex.: "avisar quando score < 40"),
esse módulo detecta **mudanças significativas** dos próprios indicadores:

  • queda_score_7d:    score caiu ≥ 10 pontos vs 7 dias atrás
  • salto_dy_30d:      DY% subiu ≥ 1pp em 30 dias (preço caiu OU provento alto)
  • variacao_semanal:  retorno últimos 5 dias > +10% ou < -10%

Persistido em `alertas_disparados`. Anti-duplicata: pula se já houve disparo
do mesmo (ticker, tipo) nas últimas 24h.

Sem streamlit — pode ser chamado por scripts/ETL.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


LIMITE_QUEDA_SCORE_PTS = 10
LIMITE_SALTO_DY_PP = 1.0
LIMITE_VAR_SEMANAL_PCT = 10.0


def _ja_disparou_recente(client, ticker: str, tipo: str, janela_horas: int = 24) -> bool:
    """Anti-duplicata: já houve disparo deste (ticker, tipo) nas últimas N horas?"""
    try:
        limite = (datetime.now(timezone.utc) - timedelta(hours=janela_horas)).isoformat()
        r = client.table("alertas_disparados").select("id").eq(
            "ticker", ticker
        ).eq("tipo", tipo).gte("disparado_em", limite).limit(1).execute()
        return bool(r.data)
    except Exception as e:
        logger.debug(f"dedup falhou {ticker}/{tipo}: {e}")
        return False


def _persistir(
    client, ticker: str, tipo: str,
    valor_atual: Optional[float],
    valor_anterior: Optional[float],
    mensagem: str,
) -> None:
    try:
        delta = None
        if valor_atual is not None and valor_anterior is not None:
            delta = round(float(valor_atual) - float(valor_anterior), 3)
        client.table("alertas_disparados").insert({
            "ticker": ticker,
            "tipo": tipo,
            "valor_atual": round(float(valor_atual), 3) if valor_atual is not None else None,
            "valor_anterior": round(float(valor_anterior), 3) if valor_anterior is not None else None,
            "delta": delta,
            "mensagem": mensagem,
        }).execute()
    except Exception as e:
        logger.error(f"falha ao persistir alerta {ticker}/{tipo}: {e}")


def detectar_queda_score(client, ticker: str, score_atual: Optional[float]) -> bool:
    """Compara score atual com leitura mais recente de ≥7 dias atrás."""
    if score_atual is None:
        return False
    try:
        limite = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        r = client.table("health_score_history").select("score").eq(
            "ticker", ticker
        ).lte("calculado_em", limite).order(
            "calculado_em", desc=True
        ).limit(1).execute()
        if not r.data:
            return False
        score_ant = r.data[0].get("score")
        if score_ant is None:
            return False
        delta = float(score_ant) - float(score_atual)
        if delta < LIMITE_QUEDA_SCORE_PTS:
            return False
        if _ja_disparou_recente(client, ticker, "queda_score_7d"):
            return False
        _persistir(
            client, ticker, "queda_score_7d",
            valor_atual=score_atual,
            valor_anterior=score_ant,
            mensagem=f"Score caiu de {score_ant:.0f} para {score_atual:.0f} em 7 dias ({-delta:+.0f}pts).",
        )
        return True
    except Exception as e:
        logger.debug(f"erro detectar_queda_score {ticker}: {e}")
        return False


def detectar_salto_dy(client, ticker: str, dy_atual: Optional[float]) -> bool:
    """
    DY% subiu ≥ 1pp em 30 dias — sinal de queda forte de preço OU provento alto.

    Reconstrói DY há 30d usando dividend_history e price_history:
       DY_30d_atras = soma_dividendos_12m_terminando_há_30d / preço_há_30d
    """
    if dy_atual is None or dy_atual <= 0:
        return False
    try:
        import pandas as pd
        # 1) Soma dividendos 12m terminando 30d atrás
        hoje = datetime.now(timezone.utc).date()
        cutoff_fim = (hoje - timedelta(days=30)).isoformat()
        cutoff_ini = (hoje - timedelta(days=395)).isoformat()
        rd = client.table("dividend_history").select(
            "valor, data_pagamento"
        ).eq("ticker", ticker).gte(
            "data_pagamento", cutoff_ini
        ).lte("data_pagamento", cutoff_fim).execute()
        if not rd.data:
            return False
        soma_div = sum(float(d["valor"]) for d in rd.data if d.get("valor"))
        if soma_div <= 0:
            return False

        # 2) Preço há 30d (tolerância: pega a leitura mais próxima entre -32 e -27 dias)
        ini = (hoje - timedelta(days=32)).isoformat()
        fim = (hoje - timedelta(days=27)).isoformat()
        rp = client.table("price_history").select(
            "data, close"
        ).eq("ticker", ticker).gte(
            "data", ini
        ).lte("data", fim).order("data", desc=True).limit(1).execute()
        if not rp.data:
            return False
        preco_30d = float(rp.data[0]["close"])
        if preco_30d <= 0:
            return False

        dy_30d_atras = soma_div / preco_30d * 100
        if dy_30d_atras <= 0:
            return False
        delta = float(dy_atual) - dy_30d_atras
        if delta < LIMITE_SALTO_DY_PP:
            return False
        if _ja_disparou_recente(client, ticker, "salto_dy_30d"):
            return False
        _persistir(
            client, ticker, "salto_dy_30d",
            valor_atual=dy_atual,
            valor_anterior=dy_30d_atras,
            mensagem=(
                f"DY subiu de {dy_30d_atras:.2f}% para {dy_atual:.2f}% em 30 dias "
                f"(+{delta:.2f}pp). verificar: queda de preço ou provento extraordinário."
            ),
        )
        return True
    except Exception as e:
        logger.debug(f"erro detectar_salto_dy {ticker}: {e}")
        return False


def detectar_variacao_semanal(
    client, ticker: str, var_semanal_pct: Optional[float] = None,
) -> bool:
    """
    Detecta variação semanal ±10%. Se `var_semanal_pct` não for passada, calcula
    a partir de price_history (últimos 7 dias corridos).
    """
    try:
        if var_semanal_pct is None:
            hoje = datetime.now(timezone.utc).date().isoformat()
            ini = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
            r = client.table("price_history").select(
                "data, close"
            ).eq("ticker", ticker).gte(
                "data", ini
            ).order("data", desc=False).limit(20).execute()
            if not r.data or len(r.data) < 4:
                return False
            preco_inicio = float(r.data[0]["close"])
            preco_fim = float(r.data[-1]["close"])
            if preco_inicio <= 0:
                return False
            var_semanal_pct = (preco_fim / preco_inicio - 1) * 100
        if abs(var_semanal_pct) < LIMITE_VAR_SEMANAL_PCT:
            return False
        if _ja_disparou_recente(client, ticker, "variacao_semanal"):
            return False
        sentido = "alta" if var_semanal_pct > 0 else "queda"
        _persistir(
            client, ticker, "variacao_semanal",
            valor_atual=var_semanal_pct, valor_anterior=None,
            mensagem=f"Variação semanal de {sentido}: {var_semanal_pct:+.2f}%.",
        )
        return True
    except Exception as e:
        logger.debug(f"erro detectar_variacao_semanal {ticker}: {e}")
        return False


def avaliar_ticker(
    client, ticker: str, *,
    score: Optional[float] = None,
    dy_pct: Optional[float] = None,
    var_semanal_pct: Optional[float] = None,
) -> int:
    """
    Roda os 3 detectores para um ticker. Retorna número de alertas novos.

    Chamadores típicos:
    - Scripts ETL após calcular score/fundamentos.
    - recalc_health_scores.py para varrer todos os tickers.
    """
    n = 0
    if score is not None and detectar_queda_score(client, ticker, score):
        n += 1
    if dy_pct is not None and detectar_salto_dy(client, ticker, dy_pct):
        n += 1
    if detectar_variacao_semanal(client, ticker, var_semanal_pct):
        n += 1
    return n


def listar_alertas_recentes(
    client, *,
    horas: int = 24,
    apenas_nao_visualizados: bool = False,
    limit: int = 100,
) -> list[dict]:
    """Lista alertas disparados na janela recente (mais novos primeiro)."""
    try:
        limite = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
        q = client.table("alertas_disparados").select("*").gte(
            "disparado_em", limite
        ).order("disparado_em", desc=True).limit(limit)
        if apenas_nao_visualizados:
            q = q.eq("visualizado", False)
        return (q.execute().data or [])
    except Exception as e:
        logger.error(f"falha listar alertas: {e}")
        return []
