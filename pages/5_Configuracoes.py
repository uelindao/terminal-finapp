import streamlit as st

from utils.auth   import require_auth, get_current_user, render_user_badge
from utils.style  import aplicar_tema
from utils.components import (
    page_header, section_title, metric_card, status_card, empty_state
)
from utils.ai_client import PROVIDERS
from database.db import (
    get_user_id,
    listar_usuarios, criar_usuario, deletar_usuario, alterar_senha,
    listar_watchlists, criar_watchlist, renomear_watchlist, deletar_watchlist,
    definir_watchlist_padrao, get_watchlist_padrao,
    listar_portfolios, criar_portfolio, renomear_portfolio, deletar_portfolio,
    definir_portfolio_padrao, get_portfolio_padrao,
    listar_relatorios_enviados,
    listar_watchlist,
    salvar_config_alerta, get_configs_alerta, deletar_config_alerta,
    get_user_settings, get_user_setting, salvar_user_settings, salvar_user_setting,
)

if not require_auth():
    st.stop()

aplicar_tema()
render_user_badge()

user          = get_current_user()
user_id_atual = get_user_id()
is_admin      = st.session_state.get('is_admin', False)

page_header("⚙️ configurações", "conta · watchlists · portfólios · ia · administração")

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_conta, tab_wl, tab_pf, tab_alertas, tab_ia, tab_admin = st.tabs([
    "👤 minha conta",
    "⭐ watchlists",
    "💼 portfólios",
    "🔔 alertas",
    "🤖 minha ia",
    "👑 administração",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MINHA CONTA
# ══════════════════════════════════════════════════════════════════════════════
with tab_conta:
    section_title("informações da conta")

    if user:
        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("usuário", user['username'], "", "muted")
        with c2:
            metric_card("nome", user['nome'] or "—", "", "muted")
        with c3:
            metric_card(
                "perfil",
                "administrador" if user['is_admin'] else "usuário",
                "",
                "amber" if user['is_admin'] else "muted",
            )

    section_title("alterar senha")

    col_s, _ = st.columns([1.6, 1])
    with col_s:
        with st.form("form_alterar_senha"):
            s1, s2, s3 = st.columns(3)
            with s1:
                senha_atual = st.text_input("senha atual:", type="password", key="cfg_s_atual")
            with s2:
                nova_senha  = st.text_input("nova senha:", type="password", key="cfg_s_nova")
            with s3:
                conf_senha  = st.text_input("confirmar:", type="password", key="cfg_s_conf")

            if st.form_submit_button("🔒 alterar senha", type="primary"):
                if not senha_atual or not nova_senha:
                    st.error("preencha todos os campos.")
                elif nova_senha != conf_senha:
                    st.error("as senhas não coincidem.")
                elif len(nova_senha) < 6:
                    st.error("a nova senha deve ter pelo menos 6 caracteres.")
                else:
                    from database.db import autenticar_usuario
                    username = st.session_state.get('username', '')
                    check = autenticar_usuario(username, senha_atual)
                    if not check:
                        st.error("senha atual incorreta.")
                    else:
                        alterar_senha(user_id_atual, nova_senha)
                        st.success("✅ senha alterada com sucesso!")

    st.markdown("<br>", unsafe_allow_html=True)
    section_title("sessão")

    ms1, ms2, ms3 = st.columns(3)
    with ms1:
        st.metric("user id", f"#{user_id_atual}")
    with ms2:
        wl_padrao_id   = get_watchlist_padrao()
        wls_all        = listar_watchlists()
        nome_wl_padrao = next((w['nome'] for w in wls_all if w['id'] == wl_padrao_id), "—")
        st.metric("watchlist padrão", nome_wl_padrao)
    with ms3:
        pf_padrao_id   = get_portfolio_padrao()
        pfs_all        = listar_portfolios()
        nome_pf_padrao = next((p['nome'] for p in pfs_all if p['id'] == pf_padrao_id), "—")
        st.metric("portfólio padrão", nome_pf_padrao)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚪 encerrar sessão", type="secondary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.success("sessão encerrada. recarregue a página para fazer login.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — WATCHLISTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_wl:
    section_title("suas watchlists")

    wls          = listar_watchlists()
    wl_padrao_id = get_watchlist_padrao()

    with st.expander("➕ criar nova watchlist", expanded=False):
        with st.form("form_criar_wl"):
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                novo_nome_wl_criar  = st.text_input("nome", placeholder="ex: crescimento, dividendos…")
            with c2:
                novo_icone_wl_criar = st.text_input("ícone", value="⭐", max_chars=2)
            with c3:
                nova_cor_wl_criar   = st.color_picker("cor", value="#FF9900")
            nova_desc_wl_criar = st.text_area("descrição (opcional)", height=60)

            if st.form_submit_button("✅ criar watchlist", use_container_width=True, type="primary"):
                if not novo_nome_wl_criar.strip():
                    st.error("informe um nome para a watchlist.")
                else:
                    criar_watchlist(
                        novo_nome_wl_criar.strip(), nova_desc_wl_criar,
                        nova_cor_wl_criar, novo_icone_wl_criar
                    )
                    st.success(f"watchlist '{novo_nome_wl_criar}' criada!")
                    st.rerun()

    st.divider()

    if not wls:
        empty_state("⭐", "sem watchlists", "crie sua primeira watchlist acima.")
    else:
        st.caption(f"{len(wls)} watchlist(s)")
        for wl in wls:
            is_padrao = wl['id'] == wl_padrao_id
            badge     = " ⭐ padrão" if is_padrao else ""
            with st.expander(
                f"{wl.get('icone','⭐')} **{wl['nome']}**{badge}  —  {wl.get('total_ativos',0)} ativo(s)",
                expanded=False
            ):
                col_edit, col_acoes = st.columns([3, 1])
                with col_edit:
                    with st.form(f"form_editar_wl_{wl['id']}"):
                        ec1, ec2, ec3 = st.columns([3, 1, 1])
                        with ec1:
                            novo_nome_wl = st.text_input("nome", value=wl['nome'], key=f"nm_wl_{wl['id']}")
                        with ec2:
                            novo_icone_wl = st.text_input("ícone", value=wl.get('icone','⭐'), max_chars=2, key=f"ic_wl_{wl['id']}")
                        with ec3:
                            nova_cor_wl = st.color_picker("cor", value=wl.get('cor','#FF9900'), key=f"cr_wl_{wl['id']}")
                        nova_desc_wl = st.text_area("descrição", value=wl.get('descricao',''), height=60, key=f"dc_wl_{wl['id']}")

                        if st.form_submit_button("💾 salvar", use_container_width=True):
                            if not novo_nome_wl.strip():
                                st.error("nome não pode ser vazio.")
                            else:
                                renomear_watchlist(
                                    wl['id'], novo_nome_wl.strip(), nova_desc_wl,
                                    novo_icone=novo_icone_wl, nova_cor=nova_cor_wl
                                )
                                st.success("watchlist atualizada!")
                                st.rerun()

                with col_acoes:
                    st.markdown("**ações**")
                    if not is_padrao:
                        if st.button("⭐ definir padrão", key=f"pad_wl_{wl['id']}", use_container_width=True):
                            definir_watchlist_padrao(wl['id'])
                            st.success(f"'{wl['nome']}' definida como padrão.")
                            st.rerun()
                    else:
                        st.markdown(
                            '<span style="color:var(--amber); font-size:0.82em;">✔ padrão</span>',
                            unsafe_allow_html=True
                        )
                    st.markdown("")
                    if wl.get('total_ativos', 0) == 0:
                        if st.button("🗑️ deletar", key=f"del_wl_{wl['id']}", use_container_width=True, type="secondary"):
                            deletar_watchlist(wl['id'])
                            st.warning(f"watchlist '{wl['nome']}' removida.")
                            st.rerun()
                    else:
                        st.caption(f"remova os {wl.get('total_ativos')} ativos antes de deletar.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PORTFÓLIOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_pf:
    section_title("seus portfólios")

    pfs          = listar_portfolios()
    pf_padrao_id = get_portfolio_padrao()

    with st.expander("➕ criar novo portfólio", expanded=False):
        with st.form("form_criar_pf"):
            pc1, pc2, pc3 = st.columns([3, 1, 1])
            with pc1:
                novo_nome_pf_criar  = st.text_input("nome", placeholder="ex: longo prazo, especulativo…")
            with pc2:
                novo_icone_pf_criar = st.text_input("ícone", value="💼", max_chars=2)
            with pc3:
                nova_cor_pf_criar   = st.color_picker("cor", value="#3b82f6")
            nova_desc_pf_criar = st.text_area("descrição (opcional)", height=60)

            if st.form_submit_button("✅ criar portfólio", use_container_width=True, type="primary"):
                if not novo_nome_pf_criar.strip():
                    st.error("informe um nome para o portfólio.")
                else:
                    criar_portfolio(
                        novo_nome_pf_criar.strip(), nova_desc_pf_criar,
                        nova_cor_pf_criar, novo_icone_pf_criar
                    )
                    st.success(f"portfólio '{novo_nome_pf_criar}' criado!")
                    st.rerun()

    st.divider()

    if not pfs:
        empty_state("💼", "sem portfólios", "crie seu primeiro portfólio acima.")
    else:
        st.caption(f"{len(pfs)} portfólio(s)")
        for pf in pfs:
            is_padrao = pf['id'] == pf_padrao_id
            badge     = " ⭐ padrão" if is_padrao else ""
            with st.expander(
                f"{pf.get('icone','💼')} **{pf['nome']}**{badge}  —  {pf.get('total_ativos',0)} ativo(s)",
                expanded=False
            ):
                col_edit_pf, col_acoes_pf = st.columns([3, 1])
                with col_edit_pf:
                    with st.form(f"form_editar_pf_{pf['id']}"):
                        pe1, pe2, pe3 = st.columns([3, 1, 1])
                        with pe1:
                            novo_nome_pf = st.text_input("nome", value=pf['nome'], key=f"nm_pf_{pf['id']}")
                        with pe2:
                            novo_icone_pf = st.text_input("ícone", value=pf.get('icone','💼'), max_chars=2, key=f"ic_pf_{pf['id']}")
                        with pe3:
                            nova_cor_pf = st.color_picker("cor", value=pf.get('cor','#FF9900'), key=f"cr_pf_{pf['id']}")
                        nova_desc_pf = st.text_area("descrição", value=pf.get('descricao',''), height=60, key=f"dc_pf_{pf['id']}")

                        if st.form_submit_button("💾 salvar", use_container_width=True):
                            if not novo_nome_pf.strip():
                                st.error("nome não pode ser vazio.")
                            else:
                                renomear_portfolio(
                                    pf['id'], novo_nome_pf.strip(), nova_desc_pf,
                                    novo_icone=novo_icone_pf, nova_cor=nova_cor_pf
                                )
                                st.success("portfólio atualizado!")
                                st.rerun()

                with col_acoes_pf:
                    st.markdown("**ações**")
                    if not is_padrao:
                        if st.button("⭐ definir padrão", key=f"pad_pf_{pf['id']}", use_container_width=True):
                            definir_portfolio_padrao(pf['id'])
                            st.success(f"'{pf['nome']}' definido como padrão.")
                            st.rerun()
                    else:
                        st.markdown(
                            '<span style="color:var(--amber); font-size:0.82em;">✔ padrão</span>',
                            unsafe_allow_html=True
                        )
                    st.markdown("")
                    if pf.get('total_ativos', 0) == 0:
                        if st.button("🗑️ deletar", key=f"del_pf_{pf['id']}", use_container_width=True, type="secondary"):
                            deletar_portfolio(pf['id'])
                            st.warning(f"portfólio '{pf['nome']}' removido.")
                            st.rerun()
                    else:
                        st.caption(f"remova os {pf.get('total_ativos')} ativos antes de deletar.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ALERTAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_alertas:
    section_title("e-mail e relatórios")

    try:
        remetente    = st.secrets["email"]["remetente"]
        destinatario = st.secrets["email"]["destinatario"]
        tem_config   = bool(remetente and destinatario)
    except Exception:
        tem_config   = False
        remetente    = ""
        destinatario = ""

    if tem_config:
        st.success(
            f"✅ SMTP configurado — remetente: `{remetente}` · destinatário: `{destinatario}`",
            icon="📬"
        )
    else:
        st.warning(
            "⚠️ credenciais de e-mail não configuradas em `secrets.toml`. "
            "adicione a seção `[email]` com `remetente` e `destinatario`.",
            icon="📭"
        )

    col_cfg_email, col_hist_email = st.columns([1, 1], gap="large")

    with col_cfg_email:
        section_title("preferências de envio")

        email_salvo = st.session_state.get('email', '')
        with st.form("form_email_config"):
            email_input = st.text_input("e-mail para relatórios:", value=email_salvo, placeholder="seu@email.com")
            freq_opcoes = ["semanal (toda segunda)", "quinzenal", "mensal", "nunca"]
            freq_idx    = st.session_state.get('freq_relatorio_idx', 0)
            frequencia  = st.selectbox("frequência:", freq_opcoes, index=freq_idx)

            st.markdown("**conteúdo:**")
            inc_health    = st.checkbox("health scores do portfólio", value=True)
            inc_macro     = st.checkbox("resumo macro (ibovespa, câmbio, juros)", value=True)
            inc_alertas   = st.checkbox("alertas de venda ativos", value=True)
            inc_benchmark = st.checkbox("comparação com benchmark", value=False)

            if st.form_submit_button("💾 salvar preferências", use_container_width=True, type="primary"):
                st.session_state['email_relatorio']    = email_input
                st.session_state['freq_relatorio_idx'] = freq_opcoes.index(frequencia)
                st.success("✅ preferências salvas!")

        if st.button("📤 enviar relatório agora", use_container_width=True):
            email_destino = st.session_state.get('email_relatorio', email_salvo)
            if not email_destino:
                st.error("configure um e-mail acima antes de enviar.")
            else:
                try:
                    from utils.email_sender import enviar_relatorio_semanal
                    from database.db import get_pesos, registrar_envio_relatorio
                    pesos = get_pesos() or []
                    ok = enviar_relatorio_semanal({'tickers': [p['ticker'] for p in pesos], 'email': email_destino})
                    if ok:
                        registrar_envio_relatorio([p['ticker'] for p in pesos])
                        st.success(f"✅ relatório enviado para {email_destino}!")
                    else:
                        st.error("falha ao enviar. verifique as configurações SMTP.")
                except ImportError:
                    st.warning("módulo `utils/email_sender.py` não encontrado.", icon="⚠️")
                except Exception as e:
                    st.error(f"erro: {e}")

    with col_hist_email:
        section_title("histórico de envios")
        relatorios = listar_relatorios_enviados(limite=15)
        if not relatorios:
            empty_state("📭", "sem envios", "nenhum relatório enviado ainda.")
        else:
            st.caption(f"{len(relatorios)} envio(s)")
            for r in relatorios:
                enviado_em  = r.get('enviado_em', '')[:16] if r.get('enviado_em') else '—'
                tickers_str = r.get('tickers_incluidos', '') or ''
                n_tickers   = len(tickers_str.split(',')) if tickers_str else 0
                status      = r.get('status', 'enviado')
                cor_st      = 'var(--bull)' if status == 'enviado' else 'var(--bear)'
                st.markdown(
                    f'<div style="background:var(--bg-surface);'
                    f' border:1px solid var(--border-subtle);'
                    f' border-radius:var(--radius-md);'
                    f' padding:10px 14px; margin-bottom:6px;">'
                    f'<div style="display:flex; justify-content:space-between;">'
                    f'<span style="font-family:var(--font-data); font-size:0.80rem;'
                    f' color:var(--text-secondary);">📅 {enviado_em}</span>'
                    f'<span style="font-family:var(--font-ui); font-size:0.68rem;'
                    f' font-weight:600; color:{cor_st};">● {status}</span>'
                    f'</div>'
                    f'<div style="font-family:var(--font-ui); font-size:0.68rem;'
                    f' color:var(--text-muted); margin-top:3px;">'
                    f'{n_tickers} ticker(s) · tipo: {r.get("tipo","semanal")}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

    st.divider()
    section_title("alertas de preço")
    st.info("os alertas de preço são configurados na watchlist de cada ativo.", icon="🔔")

    try:
        from database.db import listar_alertas
        import pandas as pd
        alertas_raw = listar_alertas(user_id_atual)
        if alertas_raw:
            df_al = pd.DataFrame(alertas_raw)
            if 'criado_em' not in df_al.columns and 'created_at' in df_al.columns:
                df_al['criado_em'] = df_al['created_at']
            show_cols = [c for c in ['ticker', 'tipo', 'threshold', 'criado_em'] if c in df_al.columns]
            st.dataframe(df_al[show_cols], use_container_width=True, hide_index=True)
        else:
            st.caption("nenhum alerta de preço configurado.")
    except Exception as e:
        st.caption(f"não foi possível carregar alertas: {e}")

    st.divider()
    section_title("alertas de health score")

    st.markdown(
        '<div style="font-family:var(--font-ui); font-size:0.78rem;'
        ' color:var(--text-muted); margin-bottom:12px; line-height:1.6;">'
        'receba uma notificação quando o health score de um ativo cair abaixo do limite.'
        '</div>',
        unsafe_allow_html=True,
    )

    from utils.notificacoes import solicitar_permissao_notificacao
    if st.button("🔔 ativar notificações no browser", type="secondary", key="btn_notif"):
        solicitar_permissao_notificacao()
        st.success("solicitação enviada! aceite a permissão no popup do browser.")

    try:
        _wl_id_cfg = get_watchlist_padrao()
        _wl_items  = listar_watchlist(watchlist_id=_wl_id_cfg)
    except Exception:
        _wl_items = []

    _configs_hs = {c['ticker']: c['threshold'] for c in get_configs_alerta(user_id_atual)}

    if _wl_items:
        st.markdown("<br>", unsafe_allow_html=True)
        for item in _wl_items:
            t = item['ticker']
            col_t, col_sl, col_btn = st.columns([2, 3, 1])
            with col_t:
                st.markdown(
                    f'<div style="font-family:var(--font-data); color:var(--accent);'
                    f' padding-top:10px;">{t.replace(".SA","")}</div>',
                    unsafe_allow_html=True,
                )
            with col_sl:
                threshold_val = st.slider(
                    f"limite {t}:", min_value=0, max_value=80,
                    value=_configs_hs.get(t, 40), step=5,
                    key=f"alert_th_{t}", label_visibility="collapsed",
                )
            with col_btn:
                if t in _configs_hs:
                    if st.button("🗑️", key=f"del_alert_{t}", help="remover alerta"):
                        deletar_config_alerta(user_id_atual, t)
                        st.rerun()
                else:
                    if st.button("➕", key=f"add_alert_{t}", help="ativar alerta"):
                        salvar_config_alerta(user_id_atual, t, threshold_val)
                        st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 salvar todos os alertas de health score", type="primary",
                     use_container_width=True, key="btn_salvar_alertas"):
            for item in _wl_items:
                t  = item['ticker']
                th = st.session_state.get(f"alert_th_{t}", 40)
                salvar_config_alerta(user_id_atual, t, th)
            st.success("✅ alertas salvos!")
    else:
        empty_state("🔔", "watchlist vazia", "adicione ativos à watchlist para configurar alertas de health score.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — MINHA IA
# ══════════════════════════════════════════════════════════════════════════════
with tab_ia:
    section_title("⚡ modo de análise ia")

    settings     = get_user_settings(user_id_atual) if user else {}
    _modo_atual  = st.session_state.get('ai_modo_atual')
    if _modo_atual is None:
        _modo_atual = 'pro' if settings.get('ai_api_key', '').strip() else 'free'
        st.session_state['ai_modo_atual'] = _modo_atual

    _col_t1, _col_t2 = st.columns(2)

    with _col_t1:
        _borda_free = "#FF9900" if _modo_atual == 'free' else "#1e1e1e"
        st.markdown(
            f'<div style="background:#0d0d0d;border:2px solid '
            f'{_borda_free};border-radius:6px;padding:16px;'
            f'text-align:center;">'
            f'<div style="font-size:1.2rem;">🆓</div>'
            f'<div style="font-family:Courier New;color:#FF9900;'
            f'font-weight:700;margin:4px 0;">tier gratuito</div>'
            f'<div style="font-family:Courier New;font-size:0.7rem;'
            f'color:#555;">gemini 2.0 flash · sem chave necessária</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            "✅ usar gratuito" if _modo_atual == 'free' else "usar gratuito",
            key="btn_modo_free",
            use_container_width=True,
            type="primary" if _modo_atual == 'free' else "secondary",
        ):
            st.session_state['ai_modo_atual'] = 'free'
            st.success("modo gratuito ativado!")
            st.rerun()

    with _col_t2:
        _tem_chave_pro = bool(settings.get('ai_api_key', '').strip())
        _borda_pro = "#FF9900" if _modo_atual == 'pro' else "#1e1e1e"
        st.markdown(
            f'<div style="background:#0d0d0d;border:2px solid '
            f'{_borda_pro};border-radius:6px;padding:16px;'
            f'text-align:center;">'
            f'<div style="font-size:1.2rem;">⚡</div>'
            f'<div style="font-family:Courier New;color:#FF9900;'
            f'font-weight:700;margin:4px 0;">tier pro</div>'
            f'<div style="font-family:Courier New;font-size:0.7rem;'
            f'color:#555;">deepseek v4 / openai · chave pessoal</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            "✅ usar pro" if _modo_atual == 'pro' else "usar pro",
            key="btn_modo_pro",
            use_container_width=True,
            type="primary" if _modo_atual == 'pro' else "secondary",
            disabled=not _tem_chave_pro,
            help="configure sua chave api abaixo para ativar" if not _tem_chave_pro else "",
        ):
            st.session_state['ai_modo_atual'] = 'pro'
            st.success("modo pro ativado!")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    section_title("configurar chave pro (opcional)")
    
    _provider_labels = {
        'deepseek':         '⚡ DeepSeek V4 Pro',
        'openai':           '🟢 OpenAI GPT-4o',
        'gemini':           '🔵 Google Gemini Pro',
        'anthropic_compat': '🟠 Anthropic Claude',
    }
    _provider_keys = list(_provider_labels.keys())
    _cur_provider  = settings.get('ai_provider', 'deepseek')
    _cur_idx       = _provider_keys.index(_cur_provider) if _cur_provider in _provider_keys else 0

    with st.form("form_ia_settings"):
        col_ia1, col_ia2 = st.columns(2)

        with col_ia1:
            provider_sel = st.selectbox(
                "provider:",
                options=_provider_keys,
                format_func=lambda x: _provider_labels[x],
                index=_cur_idx,
                key="cfg_ia_provider",
            )
            moeda_sel = st.selectbox(
                "moeda base:",
                ['BRL', 'USD'],
                index=0 if settings.get('moeda_base', 'BRL') == 'BRL' else 1,
                key="cfg_ia_moeda",
            )

        with col_ia2:
            api_key_input = st.text_input(
                "sua api key (deixe vazio para free tier):",
                type="password",
                placeholder="sk-… ou AIza… ou deixe vazio",
                value="",
                key="cfg_ia_key",
                help="DeepSeek: platform.deepseek.com | OpenAI: platform.openai.com | Gemini: aistudio.google.com",
            )
            benchmark_sel = st.selectbox(
                "benchmark principal:",
                ['IBOV', 'CDI', 'SP500', 'IBOV+SP500'],
                index=['IBOV','CDI','SP500','IBOV+SP500'].index(settings.get('benchmark','IBOV')),
                key="cfg_ia_benchmark",
            )

        col_bt1, col_bt2, col_bt3 = st.columns([2, 1, 1])
        with col_bt1:
            btn_salvar  = st.form_submit_button("💾 salvar", type="primary", use_container_width=True)
        with col_bt2:
            btn_testar  = st.form_submit_button("🧪 testar", use_container_width=True)
        with col_bt3:
            btn_remover = st.form_submit_button("🗑 remover chave", use_container_width=True)

        _model_map = {
            'deepseek':         'deepseek-chat',
            'openai':           'gpt-4o',
            'gemini':           'gemini-2.5-pro',
            'anthropic_compat': 'claude-sonnet-4-5',
        }

        if btn_salvar:
            novas = {
                'ai_provider': provider_sel,
                'ai_model':    _model_map.get(provider_sel, 'deepseek-chat'),
                'ai_api_key':  api_key_input,
                'moeda_base':  moeda_sel,
                'benchmark':   benchmark_sel,
                'alert_threshold': settings.get('alert_threshold', 40),
            }
            salvar_user_settings(user_id_atual, novas)
            if api_key_input.strip():
                st.session_state['ai_modo_atual'] = 'pro'
            elif not settings.get('ai_api_key', '').strip():
                st.session_state['ai_modo_atual'] = 'free'
            st.success("✅ configurações de ia salvas!")
            st.rerun()

        if btn_testar:
            if not api_key_input.strip():
                st.warning("insira uma api key para testar.")
            else:
                from utils.ai_client import chamar_ia
                test_settings = {
                    'ai_provider': provider_sel,
                    'ai_model':    _model_map.get(provider_sel, 'deepseek-chat'),
                    'ai_api_key':  api_key_input,
                }
                with st.spinner(f"testando {_provider_labels.get(provider_sel)}…"):
                    resp = chamar_ia(
                        "responda apenas: ok",
                        system="você é um assistente. responda apenas: ok",
                        max_tokens=10, stream=False,
                        user_settings=test_settings,
                    )
                if resp and 'ok' in resp.lower():
                    st.success(f"✅ {_provider_labels.get(provider_sel)} conectado!")
                else:
                    st.error(f"❌ resposta inesperada: '{resp}'. verifique a chave.")

        if btn_remover:
            novas = {**settings, 'ai_api_key': ''}
            salvar_user_settings(user_id_atual, novas)
            st.session_state['ai_modo_atual'] = 'free'
            st.success("chave removida — voltando ao free tier.")
            st.rerun()

    # ── Status atual ──────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _tem_chave    = bool(settings.get('ai_api_key'))
    _status_chave = "chave pessoal" if _tem_chave else "chave global (free tier)"
    st.markdown(
        f'<div style="font-family:var(--font-data); font-size:0.72rem;'
        f' color:var(--text-muted); padding:8px 12px;'
        f' background:var(--bg-surface); border:1px solid var(--border-subtle);'
        f' border-radius:var(--radius-sm);">'
        f'provider: <span style="color:var(--accent);">{_provider_labels.get(_cur_provider, _cur_provider)}</span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'chave: <span style="color:{"var(--bull)" if _tem_chave else "var(--text-muted)"};">{_status_chave}</span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'benchmark: <span style="color:var(--accent);">{settings.get("benchmark","IBOV")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Como obter chaves ─────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("📚 como obter uma chave de api", expanded=False):
        st.markdown("""
**DeepSeek V4 Pro** *(recomendado — mais barato)*
→ [platform.deepseek.com](https://platform.deepseek.com) → API Keys
→ ~$0.004/1k tokens

**Google Gemini Pro** *(pago — mais limite que o free)*
→ [aistudio.google.com](https://aistudio.google.com) → Get API Key

**OpenAI GPT-4o**
→ [platform.openai.com](https://platform.openai.com) → API Keys
→ ~$0.005/1k tokens

**Anthropic Claude**
→ [console.anthropic.com](https://console.anthropic.com) → API Keys
        """)

    # ── Referência de providers ───────────────────────────────────────────────
    with st.expander("📋 referência de providers", expanded=False):
        import pandas as _pd
        _rows = [
            {'provider': k, 'nome': v['label'], 'modelo padrão': v['model_default'], 'secret': v['secret_key']}
            for k, v in PROVIDERS.items()
        ]
        st.dataframe(_pd.DataFrame(_rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — ADMINISTRAÇÃO (apenas admins)
# ══════════════════════════════════════════════════════════════════════════════
with tab_admin:
    if not is_admin:
        st.markdown(
            '<div style="text-align:center; padding:60px 24px;">'
            '<div style="font-size:2.4rem; opacity:0.25; margin-bottom:14px;">🔒</div>'
            '<div style="font-family:var(--font-ui); font-size:0.85rem;'
            ' color:var(--text-muted);">acesso restrito a administradores.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.stop()

    # Banner admin
    st.markdown(
        '<div style="background:var(--accent-soft); border:1px solid var(--accent-border);'
        ' border-left:3px solid var(--accent); border-radius:var(--radius-md);'
        ' padding:10px 14px; margin-bottom:16px;">'
        '<span style="font-family:var(--font-ui); font-size:0.75rem; color:var(--accent);">'
        '⚡ você está logado como administrador — funcionalidades exclusivas abaixo.'
        '</span></div>',
        unsafe_allow_html=True,
    )

    section_title("usuários cadastrados")

    usuarios = listar_usuarios()
    st.caption(f"{len(usuarios)} usuário(s) no sistema")

    for u in usuarios:
        tag_admin       = "🛡️ admin" if u.get('is_admin') else "👤 usuário"
        ultimo_login    = u.get('ultimo_login', '')
        ul_str          = ultimo_login[:16] if ultimo_login else 'nunca'
        criado_em       = u.get('criado_em', '')[:10] if u.get('criado_em') else '—'

        with st.expander(f"**{u['username']}** · {tag_admin}  —  {u.get('nome','')}", expanded=False):
            i1, i2, i3 = st.columns(3)
            i1.metric("id", f"#{u['id']}")
            i2.metric("criado em", criado_em)
            i3.metric("último login", ul_str)
            st.caption(f"e-mail: {u.get('email') or '—'}")

            ac1, ac2 = st.columns(2)
            with ac1:
                with st.form(f"form_reset_{u['id']}"):
                    nova_senha_adm = st.text_input(
                        "nova senha:", type="password",
                        placeholder="mín. 6 chars",
                        key=f"adm_pwd_{u['id']}"
                    )
                    if st.form_submit_button("🔑 redefinir senha", use_container_width=True):
                        if len(nova_senha_adm) < 6:
                            st.error("mínimo 6 caracteres.")
                        else:
                            alterar_senha(u['id'], nova_senha_adm)
                            st.success(f"senha de '{u['username']}' redefinida.")
            with ac2:
                if u['id'] != user_id_atual:
                    st.markdown(
                        '<div style="border:1px solid rgba(239,68,68,0.25);'
                        ' background:rgba(239,68,68,0.05);'
                        ' border-radius:var(--radius-sm);'
                        ' padding:8px 10px; margin-bottom:8px;">'
                        '<span style="font-family:var(--font-ui); font-size:0.68rem;'
                        ' color:var(--bear);">⚠️ zona de risco</span></div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        f"🗑️ deletar '{u['username']}'",
                        key=f"del_usr_{u['id']}",
                        use_container_width=True,
                        type="secondary",
                    ):
                        deletar_usuario(u['id'])
                        st.warning(f"usuário '{u['username']}' removido.")
                        st.rerun()
                else:
                    st.info("você não pode deletar sua própria conta.", icon="ℹ️")

    st.divider()
    section_title("criar novo usuário")

    with st.form("form_criar_usuario"):
        cu1, cu2 = st.columns(2)
        with cu1:
            novo_username    = st.text_input("username:", placeholder="login único (sem espaços)")
            novo_nome_adm    = st.text_input("nome completo:", placeholder="opcional")
        with cu2:
            novo_email_adm   = st.text_input("e-mail:", placeholder="opcional")
            nova_senha_novo  = st.text_input("senha inicial:", type="password", placeholder="mín. 6 chars")

        novo_admin_flag = st.checkbox("conceder permissão de administrador")

        if st.form_submit_button("✅ criar usuário", use_container_width=True, type="primary"):
            if not novo_username.strip():
                st.error("informe um username.")
            elif len(nova_senha_novo) < 6:
                st.error("senha mínima: 6 caracteres.")
            else:
                ok = criar_usuario(
                    novo_username.strip(), nova_senha_novo,
                    nome=novo_nome_adm, email=novo_email_adm,
                    is_admin=novo_admin_flag
                )
                if ok:
                    st.success(f"✅ usuário '{novo_username}' criado com sucesso!")
                    st.rerun()
                else:
                    st.error(f"username '{novo_username}' já existe.")

    st.divider()
    section_title("informações do sistema")

    try:
        from database.supabase_client import get_supabase
        import pandas as pd
        sb = get_supabase()
        tabelas = [
            'users', 'watchlists', 'watchlist_items', 'portfolios',
            'portfolio_positions', 'health_scores', 'fundamentals_cache',
            'decision_log', 'report_history', 'alerts', 'ai_analysis_cache',
            'saved_comparisons', 'health_score_history',
        ]
        rows = []
        for t in tabelas:
            try:
                res   = sb.table(t).select('id', count='exact').execute()
                count = res.count if res.count is not None else len(res.data)
                rows.append({'tabela': t, 'registros': count})
            except Exception:
                rows.append({'tabela': t, 'registros': '—'})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("banco: **Supabase (PostgreSQL)**")
    except Exception as e:
        st.warning(f"não foi possível carregar informações do banco: {e}")

    st.divider()
    section_title("manutenção")

    mn1, mn2 = st.columns(2)
    with mn1:
        if st.button("🧹 limpar cache do Streamlit", use_container_width=True):
            st.cache_data.clear()
            st.success("cache limpo!")
    with mn2:
        if st.button("🗑️ limpar cache de IA (análises > 30 dias)", use_container_width=True):
            try:
                from database.db import limpar_cache_ia_antigo
                removidos = limpar_cache_ia_antigo(dias=30)
                st.success(f"{removidos} análise(s) removida(s).")
            except Exception as e:
                st.error(f"erro: {e}")
