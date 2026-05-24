"""
utils/notificacoes.py
Notificações nativas do browser para alertas de health score.
"""
import streamlit as st
import streamlit.components.v1 as components


def solicitar_permissao_notificacao():
    """
    Injeta JavaScript para solicitar permissão de notificação ao browser.
    Deve ser chamado uma vez por sessão.
    """
    components.html("""
    <script>
    if ('Notification' in window) {
        if (Notification.permission === 'default') {
            Notification.requestPermission().then(function(p) {
                if (p === 'granted') {
                    console.log('FinTerminal: notificações ativadas');
                }
            });
        }
    }
    </script>
    """, height=0)


def disparar_notificacao_browser(titulo: str, corpo: str, icone: str = "⚡"):
    """
    Dispara uma notificação nativa do browser.
    Só funciona se o usuário concedeu permissão.
    """
    titulo_esc = titulo.replace("'", "\\'").replace('"', '\\"')
    corpo_esc  = corpo.replace("'", "\\'").replace('"', '\\"')

    components.html(f"""
    <script>
    (function() {{
        if (!('Notification' in window)) return;

        if (Notification.permission === 'granted') {{
            var n = new Notification('{icone} {titulo_esc}', {{
                body:    '{corpo_esc}',
                icon:    'https://finterminal.app/favicon.ico',
                badge:   'https://finterminal.app/favicon.ico',
                tag:     'finterminal-alert',
                requireInteraction: true
            }});

            n.onclick = function() {{
                window.focus();
                n.close();
            }};

            // Auto-fecha após 8 segundos
            setTimeout(function() {{ n.close(); }}, 8000);
        }}
    }})();
    </script>
    """, height=0)


def verificar_e_disparar_alertas(user_id: int, health_scores: list):
    """
    Verifica os health scores contra as configurações de alerta do usuário
    e dispara notificações browser + avisos visuais no Streamlit.

    health_scores: lista de dicts com 'ticker' e 'score'
    """
    from database.db import get_configs_alerta, registrar_disparo_alerta

    configs = get_configs_alerta(user_id)
    if not configs:
        return

    config_dict       = {c['ticker']: c['threshold'] for c in configs}
    alertas_disparados = []

    for h in health_scores:
        ticker    = h.get('ticker', '')
        score     = h.get('score', 50)
        threshold = config_dict.get(ticker)

        if threshold is None:
            continue

        if score <= threshold:
            novo = registrar_disparo_alerta(user_id, ticker, score, threshold)
            if novo:
                alertas_disparados.append({
                    'ticker':    ticker,
                    'score':     score,
                    'threshold': threshold,
                })

    if not alertas_disparados:
        return

    # Notificação browser consolidada
    if len(alertas_disparados) == 1:
        a      = alertas_disparados[0]
        titulo = f"Alerta: {a['ticker'].replace('.SA', '')} — Score {a['score']}"
        corpo  = (
            f"Health Score caiu para {a['score']}/100, "
            f"abaixo do limite de {a['threshold']}. "
            "Verifique no FinTerminal."
        )
    else:
        tickers_str = ", ".join(
            [a['ticker'].replace('.SA', '') for a in alertas_disparados]
        )
        titulo = f"{len(alertas_disparados)} alertas de health score"
        corpo  = f"Ativos abaixo do limite: {tickers_str}"

    disparar_notificacao_browser(titulo, corpo)

    # Avisos visuais na UI
    for a in alertas_disparados:
        st.warning(
            f"🚨 **{a['ticker'].replace('.SA', '')}** — "
            f"health score caiu para **{a['score']}/100** "
            f"(limite configurado: {a['threshold']})"
        )
