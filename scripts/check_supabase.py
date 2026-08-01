"""
scripts/check_supabase.py — health-check LEVE do Supabase (1 linha de egress).

Diz em 2 segundos se o projeto esta operacional ou restrito por cota, sem rodar
nada pesado. Use antes de disparar ETLs/backtest.

Uso:  python scripts/check_supabase.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.getLogger("streamlit").setLevel(logging.ERROR)
logging.getLogger("db").setLevel(logging.CRITICAL)
logging.disable(logging.WARNING)


def _p(txt=""):
    print(str(txt).encode("ascii", "replace").decode())


def main():
    try:
        from database.db import get_supabase
        sb = get_supabase()
        sb.table("etl_log").select("id").limit(1).execute()
    except Exception as e:
        msg = str(e)
        if "egress" in msg.lower():
            _p("STATUS: RESTRITO — cota de EGRESS excedida.")
            _p("  O projeto so volta apos upgrade do plano ou remocao do spend cap")
            _p("  no painel do Supabase (Organization > Billing). Enquanto isso,")
            _p("  TODOS os acessos ao banco falham (app, ETLs, backtest).")
        elif "quota" in msg.lower() or "402" in msg:
            _p(f"STATUS: RESTRITO por cota — {msg[:200]}")
        elif "Credenciais" in msg:
            _p("STATUS: SEM CREDENCIAIS — rode a partir da raiz do projeto")
            _p("  (precisa do .streamlit/secrets.toml).")
        else:
            _p(f"STATUS: ERRO — {msg[:250]}")
        return 1

    _p("STATUS: OK — Supabase operacional.")
    _p("  Proximo passo sugerido:")
    _p("    python scripts/backtest_divergencias.py --anos 8 --min-persist 2 --save")
    return 0


if __name__ == "__main__":
    sys.exit(main())
