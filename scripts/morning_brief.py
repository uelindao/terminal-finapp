"""
scripts/morning_brief.py — relatório matinal automatizado.

Roda via GitHub Action às 11:00 UTC (8:00 BRT, dias úteis). Gera e envia
email HTML com 4 blocos:

1. Regime macro atual (utils/regime_classifier)
2. Top 5 altas / Top 5 quedas overnight (S&P 500 sample via yfinance)
3. Earnings reportando hoje (se houver tabela earnings_calendar)
4. Alertas inteligentes das últimas 24h (utils/alertas_mudanca)

Env vars necessárias:
    SUPABASE_URL, SUPABASE_SERVICE_KEY
    EMAIL_REMETENTE, EMAIL_APP_PASSWORD, EMAIL_DESTINATARIO
    FRED_API_KEY (opcional, alimenta regime_classifier)
"""
import os
import sys
import html as _html
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

logger = get_logger(__name__)


# ── Bloco 1: Regime macro ────────────────────────────────────────────────────
def bloco_regime() -> str:
    try:
        from utils.regime_classifier import classificar_regime_do_macro_context
        r = classificar_regime_do_macro_context()
        cor = {
            "expansao": "#2ecc71", "pico": "#f1c40f",
            "contracao": "#ff8c00", "vale": "#e74c3c",
        }.get(r.fase, "#888")
        return f"""
<h2 style="margin:0 0 8px 0; font-family:Arial,sans-serif; color:#FF9900;">
  📊 Regime Macro
</h2>
<div style="border-left:4px solid {cor}; padding:12px 16px;
            background:#f6f6f8; border-radius:4px; margin-bottom:18px;">
  <strong style="color:{cor}; font-size:1.1rem; text-transform:uppercase;">
    {_html.escape(r.fase)} · prob {int(r.probabilidade*100)}%
  </strong><br>
  <span style="color:#555; font-size:0.9rem;">{_html.escape(r.leitura)}</span>
</div>
"""
    except Exception as e:
        logger.error(f"bloco_regime falhou: {e}", exc_info=True)
        return "<p style='color:#888;'>Regime macro indisponível.</p>"


# ── Bloco 2: Movimentos overnight ────────────────────────────────────────────
_TOP_US = [
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","JPM","V","XOM",
    "JNJ","WMT","PG","UNH","HD","BAC","MA","DIS","ABBV","KO",
    "PFE","CVX","MRK","PEP","COST","TMO","CSCO","AVGO","MCD","ABT",
]


def bloco_movimentos_overnight() -> str:
    try:
        import yfinance as yf
        dados: list[tuple[str, float, float]] = []
        for t in _TOP_US:
            try:
                hist = yf.Ticker(t).history(period="5d", interval="1d", auto_adjust=True)
                if len(hist) < 2:
                    continue
                last = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
                if prev <= 0:
                    continue
                var = (last / prev - 1) * 100
                dados.append((t, last, var))
            except Exception:
                continue
        if not dados:
            return "<p style='color:#888;'>Movimentos overnight indisponíveis.</p>"
        dados.sort(key=lambda x: x[2], reverse=True)
        gain = dados[:5]
        loss = dados[-5:][::-1]

        def _linha(t, p, v):
            cor = "#2ecc71" if v >= 0 else "#e74c3c"
            return (
                f'<tr>'
                f'<td style="padding:5px 10px; font-family:Courier New,monospace;">{_html.escape(t)}</td>'
                f'<td style="padding:5px 10px; font-family:Courier New,monospace; color:#555;">US$ {p:.2f}</td>'
                f'<td style="padding:5px 10px; color:{cor}; text-align:right; font-family:Courier New,monospace;">{v:+.2f}%</td>'
                f'</tr>'
            )

        return f"""
<h2 style="margin:18px 0 8px 0; font-family:Arial,sans-serif; color:#FF9900;">
  📈 Movimentos Overnight (EUA)
</h2>
<table style="border-collapse:collapse; width:100%; font-family:Arial,sans-serif;
              font-size:0.88rem; background:#fafafa; border-radius:4px;">
  <tr><th colspan="3" style="text-align:left; background:#e8f5e9; padding:6px 10px; color:#1b5e20;">▲ Top 5 Altas</th></tr>
  {''.join(_linha(*r) for r in gain)}
  <tr><th colspan="3" style="text-align:left; background:#ffebee; padding:6px 10px; color:#b71c1c;">▼ Top 5 Quedas</th></tr>
  {''.join(_linha(*r) for r in loss)}
</table>
"""
    except Exception as e:
        logger.error(f"bloco_movimentos falhou: {e}", exc_info=True)
        return "<p style='color:#888;'>Movimentos overnight indisponíveis.</p>"


# ── Bloco 3: Earnings do dia ─────────────────────────────────────────────────
def bloco_earnings_hoje(client) -> str:
    try:
        hoje = datetime.now(timezone.utc).date().isoformat()
        # Tabela earnings_revisions tem capturado_em; não é earnings_calendar.
        # Tentativa: usar tabela earnings_calendar se existir; senão, pula com aviso amigável.
        try:
            res = client.table("earnings_calendar").select(
                "ticker, data_earnings, periodo"
            ).eq("data_earnings", hoje).execute()
        except Exception:
            return ""  # tabela não existe — silencia bloco

        if not res.data:
            return ""
        rows = "".join(
            f'<tr><td style="padding:5px 10px; font-family:Courier New,monospace;">{_html.escape(r["ticker"])}</td>'
            f'<td style="padding:5px 10px; color:#555;">{_html.escape(r.get("periodo", "") or "")}</td></tr>'
            for r in res.data[:20]
        )
        return f"""
<h2 style="margin:18px 0 8px 0; font-family:Arial,sans-serif; color:#FF9900;">
  📅 Earnings Hoje
</h2>
<table style="border-collapse:collapse; font-family:Arial,sans-serif; font-size:0.88rem;">
{rows}
</table>
"""
    except Exception as e:
        logger.error(f"bloco_earnings falhou: {e}", exc_info=True)
        return ""


# ── Bloco 4: Alertas inteligentes ────────────────────────────────────────────
def bloco_alertas(client) -> str:
    try:
        from utils.alertas_mudanca import listar_alertas_recentes
        alertas = listar_alertas_recentes(client, horas=24, limit=30)
        if not alertas:
            return ("<h2 style='margin:18px 0 8px 0; font-family:Arial,sans-serif; color:#FF9900;'>"
                    "🚨 Alertas (24h)</h2>"
                    "<p style='color:#888; font-family:Arial,sans-serif;'>"
                    "Sem alertas inteligentes nas últimas 24h. ✅</p>")

        tipos_label = {
            "queda_score_7d": ("📉 Queda Score", "#e74c3c"),
            "salto_dy_30d":   ("💰 Salto DY", "#f39c12"),
            "variacao_semanal": ("⚡ Var. Semanal", "#3498db"),
        }
        rows = ""
        for a in alertas[:20]:
            tk = _html.escape(a.get("ticker", ""))
            tipo_key = a.get("tipo", "")
            label, cor = tipos_label.get(tipo_key, (tipo_key, "#666"))
            msg = _html.escape(a.get("mensagem", "") or "")
            rows += (
                f'<tr>'
                f'<td style="padding:5px 10px; font-family:Courier New,monospace; color:#222;">{tk}</td>'
                f'<td style="padding:5px 10px; color:{cor}; font-weight:600; font-family:Arial,sans-serif;">{label}</td>'
                f'<td style="padding:5px 10px; color:#555; font-family:Arial,sans-serif; font-size:0.85rem;">{msg}</td>'
                f'</tr>'
            )
        return f"""
<h2 style="margin:18px 0 8px 0; font-family:Arial,sans-serif; color:#FF9900;">
  🚨 Alertas Inteligentes (24h)
</h2>
<table style="border-collapse:collapse; width:100%; font-family:Arial,sans-serif;
              font-size:0.88rem; background:#fafafa; border-radius:4px;">
{rows}
</table>
"""
    except Exception as e:
        logger.error(f"bloco_alertas falhou: {e}", exc_info=True)
        return ""


# ── Montagem final ───────────────────────────────────────────────────────────
def montar_html(client) -> str:
    data_str = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%d/%m/%Y")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Finterminal — Morning Brief</title></head>
<body style="font-family:Arial,sans-serif; max-width:720px; margin:0 auto;
             padding:20px; color:#222; background:#fff;">
  <h1 style="border-bottom:2px solid #FF9900; padding-bottom:8px; color:#FF9900;
             margin:0 0 18px 0;">
    ⚡ Finterminal — Morning Brief &middot; {data_str}
  </h1>
  {bloco_regime()}
  {bloco_movimentos_overnight()}
  {bloco_earnings_hoje(client)}
  {bloco_alertas(client)}
  <hr style="margin:28px 0; border:0; border-top:1px solid #ddd;">
  <small style="color:#888;">
    Gerado automaticamente pelo Finterminal. Não constitui recomendação de investimento.
  </small>
</body></html>"""


def main():
    from scripts.supabase_helper import get_client
    from utils.email_sender import enviar_email_html

    print("[morning_brief] iniciando...")
    client = get_client()
    html = montar_html(client)
    data = datetime.now(timezone.utc) - timedelta(hours=3)
    assunto = f"Finterminal — Morning Brief {data.strftime('%d/%m')}"

    ok = enviar_email_html(assunto, html)
    if not ok:
        logger.error("envio do morning brief falhou")
        sys.exit(2)
    print(f"[morning_brief] enviado: {assunto}")


if __name__ == "__main__":
    main()
