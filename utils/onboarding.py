"""
utils/onboarding.py
Wizard de onboarding de 3 passos para novos usuários.
"""
import streamlit as st
from utils.components import section_title, status_card, progress_steps

# Packs curados para início rápido
SUGESTOES_ONBOARDING = {
    'blue_chips_br': {
        'label':   '🏆 Blue Chips Brasil',
        'descr':   'As maiores e mais líquidas da B3',
        'tickers': ['WEGE3.SA', 'ITUB4.SA', 'VALE3.SA', 'PETR4.SA', 'BBAS3.SA'],
    },
    'dividendos_br': {
        'label':   '💰 Dividendos Brasil',
        'descr':   'Pagadores históricos de proventos',
        'tickers': ['TAEE11.SA', 'EGIE3.SA', 'BBSE3.SA', 'TRPL4.SA', 'VIVT3.SA'],
    },
    'fiis_diversificados': {
        'label':   '🏢 FIIs Diversificados',
        'descr':   'Fundos de diferentes segmentos',
        'tickers': ['HGLG11.SA', 'KNRI11.SA', 'XPML11.SA', 'MXRF11.SA', 'VISC11.SA'],
    },
    'big_tech_us': {
        'label':   '🌐 Big Tech EUA',
        'descr':   'As maiores de tecnologia do mundo',
        'tickers': ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META'],
    },
    'carteira_global': {
        'label':   '🌍 Carteira Global',
        'descr':   'Mix equilibrado BR + EUA + FIIs',
        'tickers': ['WEGE3.SA', 'VALE3.SA', 'HGLG11.SA', 'AAPL', 'MSFT'],
    },
}


def render_onboarding(user_id: int, watchlist_id: int) -> bool:
    """
    Renderiza o wizard de onboarding de 3 passos.
    Retorna True se o onboarding foi concluído nesta chamada.
    """
    step = st.session_state.get('onboarding_step', 0)

    progress_steps(
        steps=["boas-vindas", "primeiro ativo", "concluído"],
        current=step,
    )

    # ── STEP 0: BOAS-VINDAS ─────────────────────────────────────────────────
    if step == 0:
        st.markdown(
            '<div style="text-align:center; padding:32px 0;">'
            '<div style="font-family:Courier New; font-size:2rem; '
            'color:#FF9900; font-weight:bold;">⚡ bem-vindo ao finterminal</div>'
            '<div style="font-family:Courier New; font-size:0.88rem; '
            'color:#555; margin-top:12px; line-height:1.8;">'
            'seu terminal de análise financeira pessoal.<br>'
            'vamos configurar sua watchlist em 2 passos simples.'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        section_title("o que você vai encontrar aqui")

        features = [
            ("🔬", "research",    "análise profunda de qualquer ativo com health score"),
            ("🌍", "macro",       "ambiente macroeconômico global e brasil"),
            ("💼", "portfólio",   "controle de posições, p&l e métricas de risco"),
            ("🎯", "screener",    "filtre o mercado por fundamentos e qualidade"),
            ("🧾", "imposto de renda", "calcule ir de cada operação automaticamente"),
        ]

        for icone, titulo, descr in features:
            st.markdown(
                f'<div style="display:flex; gap:12px; align-items:center; '
                f'padding:8px 0; border-bottom:1px solid #111;">'
                f'<span style="font-size:1.2rem;">{icone}</span>'
                f'<div>'
                f'<span style="font-family:Courier New; font-size:0.78rem; '
                f'color:#FF9900; text-transform:uppercase;">{titulo}</span>'
                f'<span style="font-family:Courier New; font-size:0.75rem; '
                f'color:#555; margin-left:8px;">{descr}</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("começar →", type="primary",
                     use_container_width=True, key="ob_comecar"):
            st.session_state['onboarding_step'] = 1
            st.rerun()

    # ── STEP 1: ADICIONAR PRIMEIRO ATIVO ────────────────────────────────────
    elif step == 1:
        st.markdown(
            '<div style="font-family:Courier New; font-size:0.88rem; '
            'color:#555; margin-bottom:20px;">'
            'escolha um ponto de partida ou adicione manualmente. '
            'você pode modificar sua watchlist a qualquer momento.'
            '</div>',
            unsafe_allow_html=True,
        )

        section_title("🚀 packs de início rápido")

        cols_pack = st.columns(len(SUGESTOES_ONBOARDING))

        for i, (key, pack) in enumerate(SUGESTOES_ONBOARDING.items()):
            with cols_pack[i]:
                ativos_str = ", ".join([t.replace('.SA', '') for t in pack['tickers']])
                is_sel     = st.session_state.get('onboarding_pack') == key
                borda_cor  = "#FF9900" if is_sel else "#1e1e1e"
                st.markdown(
                    f'<div style="background:#0d0d0d; border:1px solid {borda_cor}; '
                    f'border-top:2px solid #FF9900; border-radius:4px; '
                    f'text-align:center; min-height:120px; padding:12px; '
                    f'margin-bottom:6px;">'
                    f'<div style="font-family:Courier New; font-size:0.82rem; '
                    f'color:#FF9900; font-weight:bold; margin-bottom:4px;">'
                    f'{pack["label"]}</div>'
                    f'<div style="font-family:Courier New; font-size:0.7rem; '
                    f'color:#555; margin-bottom:6px;">{pack["descr"]}</div>'
                    f'<div style="font-family:Courier New; font-size:0.65rem; '
                    f'color:#333;">{ativos_str}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                btn_label = "✅ selecionado" if is_sel else "selecionar"
                if st.button(btn_label, key=f"pack_{key}",
                             use_container_width=True):
                    st.session_state['onboarding_pack'] = key
                    st.rerun()

        # Adição manual
        st.markdown("<br>", unsafe_allow_html=True)
        section_title("ou adicione manualmente")

        ticker_manual = st.text_input(
            "ticker:", placeholder="ex: WEGE3, AAPL, MXRF11",
            key="ob_ticker_manual",
        ).upper().strip()

        col_ob1, col_ob2 = st.columns(2)

        with col_ob1:
            pack_final = st.session_state.get('onboarding_pack')
            btn_pack_label = (
                f"✅ usar pack: {SUGESTOES_ONBOARDING[pack_final]['label']}"
                if pack_final else "selecione um pack acima"
            )
            if st.button(
                btn_pack_label,
                type="primary" if pack_final else "secondary",
                use_container_width=True,
                disabled=not pack_final,
                key="ob_usar_pack",
            ):
                from database.db import adicionar_ativo
                pack = SUGESTOES_ONBOARDING[pack_final]
                for t in pack['tickers']:
                    mercado = 'Brasil (B3)' if t.endswith('.SA') else 'EUA'
                    adicionar_ativo(
                        ticker=t,
                        nome=t.replace('.SA', ''),
                        mercado=mercado,
                        watchlist_id=watchlist_id,
                    )
                st.session_state['onboarding_step'] = 2
                st.rerun()

        with col_ob2:
            if st.button(
                "adicionar manualmente e continuar →",
                type="secondary",
                use_container_width=True,
                disabled=not ticker_manual,
                key="ob_manual_continuar",
            ):
                from database.db import adicionar_ativo
                mercado = 'Brasil (B3)' if ticker_manual.endswith('.SA') else 'EUA'
                adicionar_ativo(
                    ticker=ticker_manual,
                    nome=ticker_manual.replace('.SA', ''),
                    mercado=mercado,
                    watchlist_id=watchlist_id,
                )
                st.session_state['onboarding_step'] = 2
                st.rerun()

    # ── STEP 2: CONCLUÍDO ────────────────────────────────────────────────────
    elif step == 2:
        st.markdown(
            '<div style="text-align:center; padding:32px 0;">'
            '<div style="font-size:3rem;">✅</div>'
            '<div style="font-family:Courier New; font-size:1.4rem; '
            'color:#00C853; font-weight:bold; margin-top:12px;">'
            'watchlist configurada!</div>'
            '<div style="font-family:Courier New; font-size:0.82rem; '
            'color:#555; margin-top:8px; line-height:1.8;">'
            'os health scores serão calculados em alguns instantes.<br>'
            'explore o menu lateral para acessar todas as ferramentas.'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        c_prox = st.columns(3)
        proximos = [
            ("🔬", "research",   "pages/1_Research.py",  "analise o primeiro ativo da sua watchlist"),
            ("🌍", "macro",      "pages/3_Macro.py",     "veja o ambiente macroeconômico atual"),
            ("💼", "portfólio",  "pages/4_Portfolio.py", "registre suas posições reais"),
        ]
        for i, (icone, label, page, descr) in enumerate(proximos):
            with c_prox[i]:
                st.page_link(page, label=f"{icone} {label}", help=descr)

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("ir para a watchlist →", type="primary",
                     use_container_width=True, key="ob_finalizar"):
            from database.db import marcar_onboarding_completo
            marcar_onboarding_completo(user_id)
            st.session_state.pop('onboarding_step', None)
            st.session_state.pop('onboarding_pack', None)
            st.rerun()

        return True

    return False
