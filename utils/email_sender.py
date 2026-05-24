import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import streamlit as st
from datetime import datetime
import threading
from utils.logger import get_logger

logger = get_logger(__name__)

def _enviar_assincrono(msg, remetente, app_password, destinatario):
    """Função interna que roda em uma thread separada para não bloquear a UI."""
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(remetente, app_password)
            smtp.sendmail(remetente, destinatario, msg.as_string())
    except Exception as e:
        logger.error(f"[email_sender] falha ao enviar email via SMTP: {e}")

def enviar_alerta_email(ticker: str, score: float, alertas: list[str]) -> bool:
    """
    Envia email de alerta de venda para o usuário de forma assíncrona.
    Retorna True (o envio em si ocorre em background).
    """
    try:
        remetente    = st.secrets["email"]["remetente"]
        app_password = st.secrets["email"]["app_password"]
        destinatario = st.secrets["email"]["destinatario"]
    except KeyError:
        return False  # Configuração de email não encontrada

    assunto = f"⚠️ FinTerminal — Alerta de Venda: {ticker} (Score: {score:.0f}/100)"

    # Corpo HTML do email
    alertas_html = "".join(f"<li>{a}</li>" for a in alertas)
    cor_score = "#00cc00" if score >= 65 else ("#ff9900" if score >= 40 else "#ff0000")
    label = "SAUDÁVEL" if score >= 65 else ("ATENÇÃO" if score >= 40 else "REDUZIR/VENDER")

    html = f"""
    <html><body style="background:#0d0d0d; color:#e0e0e0;
           font-family:'Courier New',monospace; padding:20px;">
        <div style="max-width:600px; margin:0 auto;">
            <h2 style="color:#FF9900; border-bottom:1px solid #333; padding-bottom:10px;">
                ⚡ FINTERMINAL — ALERTA DE ATIVO
            </h2>

            <div style="background:#111; border-left:4px solid {cor_score};
                        padding:16px; border-radius:4px; margin:20px 0;">
                <div style="font-size:1.4rem; font-weight:bold; color:#FF9900;">
                    {ticker}
                </div>
                <div style="font-size:2rem; color:{cor_score}; font-weight:bold;">
                    HEALTH SCORE: {score:.0f}/100
                </div>
                <div style="color:{cor_score}; font-size:1rem;">
                    STATUS: {label}
                </div>
            </div>

            <h3 style="color:#FF9900;">📋 Alertas Detectados</h3>
            <ul style="color:#e0e0e0; line-height:1.8;">
                {alertas_html}
            </ul>

            <div style="color:#555; font-size:0.8rem; margin-top:30px;
                        border-top:1px solid #222; padding-top:10px;">
                Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} pelo FinTerminal.
                Este alerta é informativo e não constitui recomendação de investimento.
            </div>
        </div>
    </body></html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = assunto
    msg['From']    = remetente
    msg['To']      = destinatario
    msg.attach(MIMEText(html, 'html'))

    # Inicia a thread para enviar o email sem travar o Streamlit
    threading.Thread(target=_enviar_assincrono, args=(msg, remetente, app_password, destinatario)).start()
    
    return True


def enviar_relatorio_semanal(dados_carteira: list[dict]) -> bool:
    """
    Envia relatório semanal completo da carteira de forma assíncrona.
    dados_carteira: lista de dicts com ticker, score, var_1d, var_1m, alertas
    """
    try:
        remetente    = st.secrets["email"]["remetente"]
        app_password = st.secrets["email"]["app_password"]
        destinatario = st.secrets["email"]["destinatario"]
    except KeyError:
        return False

    assunto = f"📊 FinTerminal — Relatório Semanal | {datetime.now().strftime('%d/%m/%Y')}"

    # Ordena: piores scores primeiro
    dados_ordenados = sorted(dados_carteira, key=lambda x: x.get('score', 100))

    linhas_html = ""
    for d in dados_ordenados:
        score = d.get('score', 50)
        cor = "#00cc00" if score >= 65 else ("#ff9900" if score >= 40 else "#ff0000")
        var1d = d.get('var_1d', 0)
        var1m = d.get('var_1m', 0)
        sinal1d = "▲" if var1d >= 0 else "▼"
        sinal1m = "▲" if var1m >= 0 else "▼"
        cor1d = "#00cc00" if var1d >= 0 else "#ff0000"
        cor1m = "#00cc00" if var1m >= 0 else "#ff0000"

        linhas_html += f"""
        <tr>
            <td style="padding:8px; color:#FF9900; font-weight:bold;">
                {d['ticker']}
            </td>
            <td style="padding:8px; color:{cor}; font-weight:bold; text-align:center;">
                {score:.0f}/100
            </td>
            <td style="padding:8px; color:{cor1d}; text-align:center;">
                {sinal1d} {abs(var1d):.2f}%
            </td>
            <td style="padding:8px; color:{cor1m}; text-align:center;">
                {sinal1m} {abs(var1m):.2f}%
            </td>
        </tr>
        """

    html = f"""
    <html><body style="background:#0d0d0d; color:#e0e0e0;
           font-family:'Courier New',monospace; padding:20px;">
        <div style="max-width:700px; margin:0 auto;">
            <h2 style="color:#FF9900;">📊 RELATÓRIO SEMANAL — FINTERMINAL</h2>
            <p style="color:#888;">
                {datetime.now().strftime('%d/%m/%Y %H:%M')}
            </p>

            <table style="width:100%; border-collapse:collapse;
                          background:#111; border-radius:4px;">
                <thead>
                    <tr style="border-bottom:2px solid #FF9900; color:#888;">
                        <th style="padding:10px; text-align:left;">TICKER</th>
                        <th style="padding:10px; text-align:center;">HEALTH</th>
                        <th style="padding:10px; text-align:center;">1D</th>
                        <th style="padding:10px; text-align:center;">1M</th>
                    </tr>
                </thead>
                <tbody>{linhas_html}</tbody>
            </table>

            <div style="color:#555; font-size:0.8rem; margin-top:30px;
                        border-top:1px solid #222; padding-top:10px;">
                Relatório automático do FinTerminal. Não constitui
                recomendação de investimento.
            </div>
        </div>
    </body></html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = assunto
    msg['From']    = remetente
    msg['To']      = destinatario
    msg.attach(MIMEText(html, 'html'))

    # Inicia a thread para enviar o email sem travar o Streamlit
    threading.Thread(target=_enviar_assincrono, args=(msg, remetente, app_password, destinatario)).start()
    
    return True