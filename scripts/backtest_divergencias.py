"""
scripts/backtest_divergencias.py — resultado prático das divergências (PLANO_MACRO M3-1).

Roda OFFLINE com os dados reais (Supabase price_history + SGS/yfinance) e imprime
o que cada quadrante de divergência rendeu no passado: forward RS 4/13/26 semanas,
agregado por episódio. É o portão de validação — os números aqui decidem o que
sobe para a UI.

Uso:
    python scripts/backtest_divergencias.py [--anos 8] [--min-persist 2]

Requer as credenciais Supabase em .streamlit/secrets.toml (como os demais ETLs).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Silencia o dilúvio de "missing ScriptRunContext" do Streamlit em modo bare
# (classificar_regime/tilt_setor tocam st.session_state — inofensivo fora do app).
import logging as _logging  # noqa: E402
_logging.getLogger("streamlit").setLevel(_logging.ERROR)

import pandas as pd  # noqa: E402

from utils.setor_series import carregar_retornos_setoriais_br  # noqa: E402
from utils.regime_historico import reconstruir_regime_tilt_br  # noqa: E402
from utils.backtest_divergencia import rodar_backtest          # noqa: E402
from utils.divergencia_setorial import (                        # noqa: E402
    DIVERG_A, DIVERG_B, CONFIRMA_BULL, CONFIRMA_BEAR, CATCH_UP, NEUTRO,
)

_ORDEM = [DIVERG_A, DIVERG_B, CONFIRMA_BULL, CONFIRMA_BEAR, CATCH_UP, NEUTRO]
_ROTULO = {
    DIVERG_A: "DIVERGENCIA A (favorecido & fraco)",
    DIVERG_B: "DIVERGENCIA B (penalizado & forte)",
    CONFIRMA_BULL: "confirmacao bull",
    CONFIRMA_BEAR: "confirmacao bear",
    CATCH_UP: "catch-up (favorecido & morno)",
    NEUTRO: "neutro",
}


def _p(txt=""):
    print(str(txt).encode("ascii", "replace").decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anos", type=int, default=8)
    ap.add_argument("--min-persist", type=int, default=2,
                    help="comprimento minimo do episodio (semanas) p/ entrar na stat")
    ap.add_argument("--janela-rs", type=int, default=13)
    ap.add_argument("--save", action="store_true",
                    help="persiste a estatistica no Supabase p/ a UI ler (rapido/robusto)")
    args = ap.parse_args()

    _p("[1/3] carregando retornos setoriais BR (price_history)...")
    ret_diario = carregar_retornos_setoriais_br(dias=int(args.anos * 260))
    if ret_diario.empty:
        _p("  ERRO: sem retornos setoriais (price_history vazio?). Abortando.")
        return
    ret_sem = (1 + ret_diario.fillna(0.0)).resample("W-FRI").prod() - 1.0
    _p(f"  {ret_sem.shape[1]} setores, {len(ret_sem)} semanas.")

    _p("[2/3] reconstruindo regime/tilt historico (SGS + yfinance)...")
    tilt = reconstruir_regime_tilt_br(anos=args.anos)
    if tilt.empty:
        _p("  ERRO: reconstrucao de tilt vazia (APIs macro?). Abortando.")
        return
    _p(f"  {len(tilt)} semanas de tilt reconstruido.")

    _p("[3/3] rodando backtest por episodio...")
    out = rodar_backtest(
        ret_sem, tilt, janela_rs=args.janela_rs, horizontes=(4, 13, 26),
        min_persistencia=args.min_persist,
    )
    stats = out["estatistica"]

    _p("")
    _p("=" * 72)
    _p(f"  RESULTADO PRATICO DAS DIVERGENCIAS  (episodios={out['n_episodios']}, "
       f"janela_rs={out['janela_rs']}s, min_persist={args.min_persist}s)")
    _p("=" * 72)
    _p("  forward RS = quanto o setor bateu a mediana do universo DEPOIS do sinal")
    _p("  (positivo = superou; por EPISODIO, nao por semana)")
    _p("-" * 72)
    _p(f"  {'quadrante':<36} {'horiz':>5} {'n':>4} {'media':>8} {'mediana':>8} {'hit':>6}")
    _p("-" * 72)
    for q in _ORDEM:
        if q not in stats:
            continue
        for h in (4, 13, 26):
            if h not in stats[q]:
                continue
            s = stats[q][h]
            _p(f"  {_ROTULO[q]:<36} {str(h)+'s':>5} {s['n']:>4} "
               f"{s['media']*100:>7.2f}% {s['mediana']*100:>7.2f}% "
               f"{s['hit_rate']*100:>5.0f}%")
        _p("-" * 72)

    _p("")
    _p("  LEITURA: divergencia B com fwd RS >0 e hit >50% sustenta a tese de")
    _p("  antecipacao de virada; divergencia A idem para catch-up. n<10 = baixa")
    _p("  confianca (mostrar o numero, rebaixar a certeza na UI). Vies: survivorship")
    _p("  (price_history so tem tickers atuais) e equal-weight BR.")

    if args.save:
        try:
            import json
            from datetime import date
            from database.db import save_ai_analysis
            payload = dict(out)
            payload["gerado_em"] = date.today().isoformat()
            payload["min_persist"] = args.min_persist
            save_ai_analysis(
                tipo="backtest_div_v1", conteudo=json.dumps(payload),
                ticker=None, user_id=None, modelo="backtest",
                ttl_horas=24 * 120,   # 120 dias — re-rodar o script atualiza
            )
            _p("")
            _p("  [save] estatistica persistida no Supabase (backtest_div_v1) — a UI")
            _p("         (Discovery > divergencias) e a IA vao LER isto, sem recomputar.")
        except Exception as e:
            _p(f"  [save] FALHA ao persistir: {e}")


if __name__ == "__main__":
    main()
