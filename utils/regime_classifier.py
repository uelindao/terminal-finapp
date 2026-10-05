"""Sinais macro de stress e recuperação; concordância não é probabilidade.

A fase é uma leitura heurística, não uma datação de recessões. Sinais ausentes
ficam desconhecidos. Stress elevado, isoladamente, nunca identifica um vale.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Optional

from utils.logger import get_logger
from utils.indicators import momentum_12_1 as _momentum_12_1

logger = get_logger(__name__)


def numero_finito(valor) -> Optional[float]:
    """Preserva zero; não converte ausência, booleano ou infinito em observação."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
        return numero if isfinite(numero) else None
    except (TypeError, ValueError):
        return None



def valor_observado(contexto: dict, chave: str, *aliases) -> Optional[float]:
    """Ignora valores fallback quando a camada de dados informa a proveniência."""
    qualidade = contexto.get("qualidade") or {}
    for nome in (chave, *aliases):
        dado = numero_finito(contexto.get(nome))
        meta = qualidade.get(nome) or qualidade.get(chave) or {}
        if dado is not None and meta.get("observado") is not False:
            return dado
    return None

def recuperacao_persistente(serie) -> Optional[bool]:
    """Duas altas mensais após duas quedas; só aceita cinco leituras contíguas.

    O chamador deve fornecer uma série mensal de atividade. Não preencher lacunas
    nem transformar preços de ações em atividade. A regra é evidência descritiva,
    não uma probabilidade estimada de recuperação.
    """
    if serie is None:
        return None
    indice = getattr(serie, "index", None)
    if indice is not None and hasattr(indice, "to_period") and len(indice) >= 5:
        meses = indice[-5:].to_period("M").asi8
        if any(meses[i + 1] - meses[i] != 1 for i in range(4)):
            return None
    valores = list(serie)
    if len(valores) < 5:
        return None
    ultimos = [numero_finito(v) for v in valores[-5:]]
    if any(v is None for v in ultimos):
        return None
    a, b, c, d, e = ultimos
    return bool(a > b > c and c < d < e)


@dataclass
class RegimeResult:
    fase: str
    concordancia: float
    score_sinais: int
    sinais: dict
    leitura: str
    intensidade_stress: float = 0.0
    cobertura: float = 0.0
    sinais_validos: int = 0
    recuperacao_confirmada: bool = False

    @property
    def probabilidade(self) -> float:
        """Alias legado de concordância; NÃO representa probabilidade estatística."""
        return self.concordancia


def classificar_regime(
    t10y: Optional[float], t2y: Optional[float], vix: Optional[float],
    cpi_yoy_serie: Optional[list[float]], spy_serie: Optional[list[float]],
    ibov_serie: Optional[list[float]], *, slope_10y_2y: Optional[float] = None,
    atividade_serie=None,
) -> RegimeResult:
    """Classifica sinais válidos; menos de três dos quatro = indefinido.

    A curva é 10y−2y de verdade. O argumento slope permite usar o par alinhado do
    snapshot, sem misturar datas de yields. Um vale exige recuperação persistente
    na atividade mensal além de stress. Percentuais descrevem os sinais observados.
    """
    t10y, t2y, vix = map(numero_finito, (t10y, t2y, vix))
    slope = numero_finito(slope_10y_2y)
    if slope is None and t10y is not None and t2y is not None:
        slope = t10y - t2y
    sinais = {
        "yield_invertida": None if slope is None else bool(slope < 0),
        "vix_alto": None if vix is None else bool(vix > 20),
        "cpi_acelerando": None,
        "momentum_negativo": None,
    }
    cpi = list(cpi_yoy_serie) if cpi_yoy_serie is not None else []
    if len(cpi) >= 3:
        a, b, c = [numero_finito(v) for v in cpi[-3:]]
        if all(v is not None for v in (a, b, c)):
            sinais["cpi_acelerando"] = bool(c > b > a)
    spy = list(spy_serie) if spy_serie is not None else []
    ibov = list(ibov_serie) if ibov_serie is not None else []
    # Não retirar pontos ausentes: isso mudaria o horizonte do momentum.
    mom_spy = _momentum_12_1(spy) if all(numero_finito(v) is not None and float(v) > 0 for v in spy) else None
    mom_ibov = _momentum_12_1(ibov) if all(numero_finito(v) is not None and float(v) > 0 for v in ibov) else None
    if mom_spy is not None and mom_ibov is not None:
        sinais["momentum_negativo"] = bool(mom_spy < 0 and mom_ibov < 0)
    score = sum(v is True for v in sinais.values())
    validos = sum(v is not None for v in sinais.values())
    stress = score / validos if validos else 0.0
    recuperacao = recuperacao_persistente(atividade_serie) is True
    if validos < 3:
        fase = "indefinido"
    elif score >= 2 and recuperacao:
        fase = "vale"
    elif stress >= 0.75:
        fase = "contracao"
    elif stress >= 0.5:
        fase = "pico"
    else:
        fase = "expansao"
    concordancia = max(stress, 1 - stress) if validos else 0.0
    leitura = {
        "indefinido": "Cobertura insuficiente para classificar o ciclo; dados ausentes não são sinais favoráveis.",
        "expansao": "Predominam sinais sem stress. Isso não confirma crescimento acima do potencial.",
        "pico": "Sinais financeiros mistos; acompanhar a direção da atividade e da inflação.",
        "contracao": "Predominam sinais de stress. A intensidade negativa não identifica um fundo do ciclo.",
        "vale": "A atividade mensal caiu e apresentou duas altas consecutivas; indício de recuperação, sujeito a revisão.",
    }[fase]
    return RegimeResult(fase, round(concordancia, 4), score, sinais, leitura,
                        round(stress, 4), validos / 4, validos, recuperacao)


def ler_curva_10y_2y() -> dict:
    """Último par DGS10/DGS2 na mesma data; ausência não usa ^IRX como 2 anos."""
    try:
        from utils.macro_supabase import buscar_slope_curva
        df = buscar_slope_curva()
        if df is not None and not df.empty and {"t10y", "t2y"}.issubset(df.columns):
            pares = df.dropna(subset=["t10y", "t2y"])
            if not pares.empty:
                row = pares.iloc[-1]
                t10, t2 = numero_finito(row["t10y"]), numero_finito(row["t2y"])
                if t10 is not None and t2 is not None:
                    return {"t10y": t10, "t2y": t2, "slope": t10 - t2,
                            "data": str(row.get("data", pares.index[-1])), "fonte": "FRED DGS10/DGS2"}
    except Exception:
        logger.debug("curva 10y−2y indisponível", exc_info=True)
    return {"t10y": None, "t2y": None, "slope": None, "data": None, "fonte": None}


def classificar_regime_do_macro_context(macro_context=None) -> RegimeResult:
    """Snapshot macro e séries de preço; nenhuma proxy falsa de Treasury 2y."""
    import yfinance as yf
    if macro_context is None:
        try:
            from utils.macro_context import _fetch_macro_rapido
            macro_context = _fetch_macro_rapido()
        except Exception:
            macro_context = {}
    macro = macro_context or {}
    curva = ler_curva_10y_2y()
    cpi, atividade = None, None
    try:
        from utils.macro_supabase import carregar_snapshot
        df = carregar_snapshot("fred_global", max_age_days=7)
        if df is not None and not df.empty:
            if "CPI_YOY" in df:
                cpi = df["CPI_YOY"].dropna().resample("MS").last().tail(6).tolist()
            # Apenas quando o ETL realmente coletou atividade mensal.
            if "INDPRO" in df:
                atividade = df["INDPRO"].dropna().resample("MS").last().tail(5).tolist()
    except Exception:
        logger.debug("atividade/CPI indisponíveis no snapshot", exc_info=True)
    series = []
    for ticker in ("SPY", "^BVSP"):
        try:
            hist = yf.Ticker(ticker).history(period="14mo")
            series.append(hist["Close"].tolist() if hist is not None and not hist.empty else None)
        except Exception:
            series.append(None)
    return classificar_regime(curva["t10y"], curva["t2y"], valor_observado(macro, "vix"),
                              cpi, *series, slope_10y_2y=curva["slope"], atividade_serie=atividade)
