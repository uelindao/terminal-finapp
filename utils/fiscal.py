"""Leitura fiscal descritiva: saldo primário com superávit positivo, sem previsão."""
from __future__ import annotations
import pandas as pd
from utils.macro_research import mensal


def calcular_semaforo_fiscal(df_br: pd.DataFrame) -> dict:
    resultado = {"divida_pib": None, "result_primario": None, "tendencia_divida": None,
                 "status": "neutro", "cor": "amber", "label": "DADOS INSUFICIENTES",
                 "cobertura": 0., "metodo": "heuristica_descritiva"}
    if df_br is None or df_br.empty:
        return resultado
    if "Divida_Bruta_PIB" in df_br:
        divida = mensal(df_br["Divida_Bruta_PIB"])
        if not divida.empty:
            resultado["divida_pib"] = float(divida.iloc[-1])
            # t contra t−6 meses: sete referências e nenhum mês intermediário ausente.
            janela = divida.iloc[-7:]
            if len(janela) == 7 and janela.notna().all():
                resultado["tendencia_divida"] = float(janela.iloc[-1] - janela.iloc[0])
    # Coluna legada Result_Primario tem sinal NFSP oposto e não é aceita como saldo.
    if "Saldo_Primario_PIB" in df_br:
        saldo = mensal(df_br["Saldo_Primario_PIB"])
        if not saldo.empty:
            resultado["result_primario"] = float(saldo.iloc[-1])
    valores = [resultado[k] for k in ("divida_pib", "tendencia_divida", "result_primario")]
    resultado["cobertura"] = sum(v is not None for v in valores) / 3
    if resultado["cobertura"] < 1:
        return resultado
    divida, tendencia, primario = valores
    pontos = (3 if divida > 90 else 2 if divida > 80 else 1 if divida > 70 else 0)
    pontos += 2 if tendencia > 3 else 1 if tendencia > 1 else 0
    pontos += 2 if primario < -3 else 1 if primario < -1 else 0
    if pontos >= 5:
        resultado.update(status="critico", cor="bear", label="PRESSÃO FISCAL ALTA")
    elif pontos >= 3:
        resultado.update(status="alerta", cor="amber", label="ATENÇÃO FISCAL")
    else:
        resultado.update(status="saudavel", cor="bull", label="PRESSÃO FISCAL BAIXA")
    return resultado
