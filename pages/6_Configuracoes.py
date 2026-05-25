import streamlit as st
from database.db import (
    get_user_id, listar_usuarios, criar_usuario, deletar_usuario, alterar_senha,
    listar_watchlists, criar_watchlist, renomear_watchlist, deletar_watchlist,
    definir_watchlist_padrao, get_watchlist_padrao,
    listar_portfolios, criar_portfolio, renomear_portfolio, deletar_portfolio,
    definir_portfolio_padrao, get_portfolio_padrao,
    listar_relatorios_enviados,
    listar_watchlist,
    salvar_config_alerta, get_configs_alerta, deletar_config_alerta,
    get_user_settings, salvar_user_settings,
)
from utils.ai_client import PROVIDERS
from utils.notificacoes import solicitar_permissao_notificacao

st.set_page_config(page_title="configurações", page_icon="⚙️", layout="wide")

# ── estilos ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .config-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #2d2d4e;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 24px;
  }
  .config-card {
    background: #1a1a2e;
    border: 1px solid #2d2d4e;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
  }
  .danger-zone {
    border: 1px solid #ff4b4b44;
    background: #ff4b4b0a;
    border-radius: 10px;
    padding: 16px;
    margin-top: 16px;
  }
  .tag-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75em;
    font-weight: 600;
    margin-left: 6px;
  }
</style>
""", unsafe_allow_html=True)

# ── cabeçalho ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="config-header">
  <h2 style="margin:0; color:#e2e8f0;">⚙️ configurações</h2>
  <p style="margin:4px 0 0; color:#94a3b8; font-size:0.9em;">
    gerencie sua conta, listas, portfólios e preferências do sistema
  </p>
</div>
""", unsafe_allow_html=True)

user_id_atual = get_user_id()

# verifica se é admin
try:
    is_admin = st.session_state.get('is_admin', False)
except Exception:
    is_admin = False

# ── tabs ───────────────────────────────────────────────────────────────────────
tabs_labels = ["👤 minha conta", "⭐ watchlists", "💼 portfólios", "📧 email & alertas", "🤖 minha ia", "🛡️ administração"]
tab_conta, tab_wl, tab_pf, tab_email, tab_ia, tab_admin = st.tabs(tabs_labels)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MINHA CONTA
# ══════════════════════════════════════════════════════════════════════════════
with tab_conta:
    st.subheader("👤 informações da conta")

    col_info, col_senha = st.columns([1, 1], gap="large")

    with col_info:
        st.markdown("#### perfil")

        username = st.session_state.get('username', 'usuário')
        nome = st.session_state.get('nome', '')
        email = st.session_state.get('email', '')

        st.markdown(f"""
        <div class="config-card">
          <p style="margin:0; color:#94a3b8; font-size:0.8em;">usuário</p>
          <p style="margin:2px 0 12px; font-size:1.1em; font-weight:600; color:#e2e8f0;">
            {username}
            {'<span class="tag-pill" style="background:#7c3aed22; color:#a78bfa; border:1px solid #7c3aed44;">admin</span>' if is_admin else ''}
          </p>
          <p style="margin:0; color:#94a3b8; font-size:0.8em;">nome</p>
          <p style="margin:2px 0 12px; color:#e2e8f0;">{nome if nome else '—'}</p>
          <p style="margin:0; color:#94a3b8; font-size:0.8em;">e-mail</p>
          <p style="margin:2px 0 0; color:#e2e8f0;">{email if email else '—'}</p>
        </div>
        """, unsafe_allow_html=True)

        st.info("para alterar nome e e-mail, contate o administrador do sistema.", icon="ℹ️")

    with col_senha:
        st.markdown("#### alterar senha")

        with st.form("form_alterar_senha"):
            senha_atual = st.text_input("senha atual", type="password", placeholder="••••••••")
            nova_senha = st.text_input("nova senha", type="password", placeholder="mínimo 6 caracteres")
            conf_senha = st.text_input("confirmar nova senha", type="password", placeholder="repita a senha")

            if st.form_submit_button("🔒 alterar senha", use_container_width=True, type="primary"):
                if not senha_atual or not nova_senha:
                    st.error("preencha todos os campos.")
                elif nova_senha != conf_senha:
                    st.error("as senhas não coincidem.")
                elif len(nova_senha) < 6:
                    st.error("a nova senha deve ter pelo menos 6 caracteres.")
                else:
                    from database.db import autenticar_usuario
                    check = autenticar_usuario(username, senha_atual)
                    if not check:
                        st.error("senha atual incorreta.")
                    else:
                        alterar_senha(user_id_atual, nova_senha)
                        st.success("✅ senha alterada com sucesso!")

    st.divider()

    # sessão
    st.markdown("#### sessão")
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.metric("user id", f"#{user_id_atual}")
    with col_s2:
        wl_padrao_id = get_watchlist_padrao()
        wls = listar_watchlists()
        nome_wl_padrao = next((w['nome'] for w in wls if w['id'] == wl_padrao_id), "—")
        st.metric("watchlist padrão", nome_wl_padrao)
    with col_s3:
        pf_padrao_id = get_portfolio_padrao()
        pfs = listar_portfolios()
        nome_pf_padrao = next((p['nome'] for p in pfs if p['id'] == pf_padrao_id), "—")
        st.metric("portfólio padrão", nome_pf_padrao)

    if st.button("🚪 encerrar sessão", type="secondary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.success("sessão encerrada. recarregue a página para fazer login.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — WATCHLISTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_wl:
    st.subheader("⭐ gerenciar watchlists")

    wls = listar_watchlists()
    wl_padrao_id = get_watchlist_padrao()

    # criar nova
    with st.expander("➕ criar nova watchlist", expanded=False):
        with st.form("form_criar_wl"):
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                novo_nome_wl_criar = st.text_input("nome da watchlist", placeholder="ex: crescimento, dividendos…")
            with c2:
                novo_icone_wl_criar = st.text_input("ícone", value="⭐", max_chars=2)
            with c3:
                nova_cor_wl_criar = st.color_picker("cor", value="#FF9900")
            nova_desc_wl_criar = st.text_area("descrição (opcional)", height=60)

            if st.form_submit_button("✅ criar watchlist", use_container_width=True, type="primary"):
                if not novo_nome_wl_criar.strip():
                    st.error("informe um nome para a watchlist.")
                else:
                    criar_watchlist(novo_nome_wl_criar.strip(), nova_desc_wl_criar, nova_cor_wl_criar, novo_icone_wl_criar)
                    st.success(f"watchlist '{novo_nome_wl_criar}' criada!")
                    st.rerun()

    st.divider()

    if not wls:
        st.info("nenhuma watchlist encontrada. crie uma acima.", icon="⭐")
    else:
        st.caption(f"{len(wls)} watchlist(s) encontrada(s)")

        for wl in wls:
            is_padrao = wl['id'] == wl_padrao_id
            badge = " ⭐ padrão" if is_padrao else ""

            with st.expander(f"{wl.get('icone','⭐')} **{wl['nome']}**{badge}  —  {wl.get('total_ativos', 0)} ativo(s)", expanded=False):
                col_edit, col_acoes = st.columns([3, 1])

                with col_edit:
                    with st.form(f"form_editar_wl_{wl['id']}"):
                        st.markdown(f"<small style='color:#64748b;'>id: {wl['id']}</small>", unsafe_allow_html=True)
                        ec1, ec2, ec3 = st.columns([3, 1, 1])
                        with ec1:
                            novo_nome_wl = st.text_input("nome", value=wl['nome'], key=f"nome_wl_{wl['id']}")
                        with ec2:
                            novo_icone_wl = st.text_input("ícone", value=wl.get('icone', '⭐'), max_chars=2, key=f"icone_wl_{wl['id']}")
                        with ec3:
                            nova_cor_wl = st.color_picker("cor", value=wl.get('cor', '#FF9900'), key=f"cor_wl_{wl['id']}")
                        nova_desc_wl = st.text_area("descrição", value=wl.get('descricao', ''), height=60, key=f"desc_wl_{wl['id']}")

                        if st.form_submit_button("💾 salvar alterações", use_container_width=True):
                            if not novo_nome_wl.strip():
                                st.error("o nome não pode ser vazio.")
                            else:
                                renomear_watchlist(
                                    wl['id'],
                                    novo_nome_wl.strip(),
                                    nova_desc_wl,
                                    novo_icone=novo_icone_wl,
                                    nova_cor=nova_cor_wl
                                )
                                st.success("watchlist atualizada!")
                                st.rerun()

                with col_acoes:
                    st.markdown("**ações**")

                    if not is_padrao:
                        if st.button("⭐ definir padrão", key=f"padrao_wl_{wl['id']}", use_container_width=True):
                            definir_watchlist_padrao(wl['id'])
                            st.success(f"'{wl['nome']}' definida como padrão.")
                            st.rerun()
                    else:
                        st.markdown(
                            "<span style='color:#f59e0b; font-size:0.85em;'>✔ watchlist padrão</span>",
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
    st.subheader("💼 gerenciar portfólios")

    pfs = listar_portfolios()
    pf_padrao_id = get_portfolio_padrao()

    # criar novo
    with st.expander("➕ criar novo portfólio", expanded=False):
        with st.form("form_criar_pf"):
            pc1, pc2, pc3 = st.columns([3, 1, 1])
            with pc1:
                novo_nome_pf_criar = st.text_input("nome do portfólio", placeholder="ex: longo prazo, especulativo…")
            with pc2:
                novo_icone_pf_criar = st.text_input("ícone", value="💼", max_chars=2)
            with pc3:
                nova_cor_pf_criar = st.color_picker("cor", value="#3b82f6")
            nova_desc_pf_criar = st.text_area("descrição (opcional)", height=60)

            if st.form_submit_button("✅ criar portfólio", use_container_width=True, type="primary"):
                if not novo_nome_pf_criar.strip():
                    st.error("informe um nome para o portfólio.")
                else:
                    criar_portfolio(novo_nome_pf_criar.strip(), nova_desc_pf_criar, nova_cor_pf_criar, novo_icone_pf_criar)
                    st.success(f"portfólio '{novo_nome_pf_criar}' criado!")
                    st.rerun()

    st.divider()

    if not pfs:
        st.info("nenhum portfólio encontrado. crie um acima.", icon="💼")
    else:
        st.caption(f"{len(pfs)} portfólio(s) encontrado(s)")

        for pf in pfs:
            is_padrao = pf['id'] == pf_padrao_id
            badge = " ⭐ padrão" if is_padrao else ""

            with st.expander(f"{pf.get('icone','💼')} **{pf['nome']}**{badge}  —  {pf.get('total_ativos', 0)} ativo(s)", expanded=False):
                col_edit_pf, col_acoes_pf = st.columns([3, 1])

                with col_edit_pf:
                    with st.form(f"form_editar_pf_{pf['id']}"):
                        st.markdown(f"<small style='color:#64748b;'>id: {pf['id']}</small>", unsafe_allow_html=True)
                        pe1, pe2, pe3 = st.columns([3, 1, 1])
                        with pe1:
                            novo_nome_pf = st.text_input("nome", value=pf['nome'], key=f"nome_pf_{pf['id']}")
                        with pe2:
                            novo_icone_pf = st.text_input("ícone", value=pf.get('icone', '💼'), max_chars=2, key=f"icone_pf_{pf['id']}")
                        with pe3:
                            nova_cor_pf = st.color_picker("cor", value=pf.get('cor', '#FF9900'), key=f"cor_pf_{pf['id']}")
                        nova_desc_pf = st.text_area("descrição", value=pf.get('descricao', ''), height=60, key=f"desc_pf_{pf['id']}")

                        if st.form_submit_button("💾 salvar alterações", use_container_width=True):
                            if not novo_nome_pf.strip():
                                st.error("o nome não pode ser vazio.")
                            else:
                                renomear_portfolio(
                                    pf['id'],
                                    novo_nome_pf.strip(),
                                    nova_desc_pf,
                                    novo_icone=novo_icone_pf,
                                    nova_cor=nova_cor_pf
                                )
                                st.success("portfólio atualizado!")
                                st.rerun()

                with col_acoes_pf:
                    st.markdown("**ações**")

                    if not is_padrao:
                        if st.button("⭐ definir padrão", key=f"padrao_pf_{pf['id']}", use_container_width=True):
                            definir_portfolio_padrao(pf['id'])
                            st.success(f"'{pf['nome']}' definido como padrão.")
                            st.rerun()
                    else:
                        st.markdown(
                            "<span style='color:#f59e0b; font-size:0.85em;'>✔ portfólio padrão</span>",
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
# TAB 4 — EMAIL & ALERTAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_email:
    st.subheader("📧 configurações de e-mail e alertas")

    # leitura das credenciais SMTP configuradas nos secrets
    try:
        remetente = st.secrets["email"]["remetente"]
        destinatario = st.secrets["email"]["destinatario"]
        tem_config = bool(remetente and destinatario)
    except Exception:
        tem_config = False
        remetente = ""
        destinatario = ""

    if tem_config:
        st.success(
            f"✅ SMTP configurado — remetente: `{remetente}` · destinatário padrão: `{destinatario}`",
            icon="📬"
        )
    else:
        st.warning(
            "⚠️ credenciais de e-mail não configuradas em `secrets.toml`. "
            "adicione a seção `[email]` com `remetente` e `destinatario` para habilitar o envio.",
            icon="📭"
        )

    col_email_cfg, col_email_hist = st.columns([1, 1], gap="large")

    with col_email_cfg:
        st.markdown("#### endereço de e-mail")

        email_salvo = st.session_state.get('email', '')

        with st.form("form_email_config"):
            email_input = st.text_input(
                "e-mail para receber relatórios",
                value=email_salvo,
                placeholder="seu@email.com"
            )
            freq_opcoes = ["semanal (toda segunda)", "quinzenal", "mensal", "nunca"]
            freq_idx = st.session_state.get('freq_relatorio_idx', 0)
            frequencia = st.selectbox("frequência dos relatórios", freq_opcoes, index=freq_idx)

            st.markdown("**conteúdo do relatório**")
            inc_health = st.checkbox("health scores do portfólio", value=True)
            inc_macro = st.checkbox("resumo macro (ibovespa, câmbio, juros)", value=True)
            inc_alertas = st.checkbox("alertas de venda ativos", value=True)
            inc_benchmark = st.checkbox("comparação com benchmark", value=False)

            if st.form_submit_button("💾 salvar preferências", use_container_width=True, type="primary"):
                st.session_state['email_relatorio'] = email_input
                st.session_state['freq_relatorio_idx'] = freq_opcoes.index(frequencia)
                st.success("✅ preferências de e-mail salvas!")

        st.divider()

        st.markdown("#### teste de envio")
        if st.button("📤 enviar relatório agora", use_container_width=True):
            email_destino = st.session_state.get('email_relatorio', email_salvo)
            if not email_destino:
                st.error("configure um e-mail acima antes de enviar.")
            else:
                try:
                    from utils.email_sender import enviar_relatorio_semanal
                    pesos = []
                    try:
                        from database.db import get_pesos
                        pesos = get_pesos()
                    except Exception:
                        pass
                    ok = enviar_relatorio_semanal({'tickers': [p['ticker'] for p in pesos], 'email': email_destino})
                    if ok:
                        from database.db import registrar_envio_relatorio
                        registrar_envio_relatorio([p['ticker'] for p in pesos])
                        st.success(f"✅ relatório enviado para {email_destino}!")
                    else:
                        st.error("falha ao enviar o relatório. verifique as configurações SMTP.")
                except ImportError:
                    st.warning("módulo `utils/email_sender.py` não encontrado. implemente a função `enviar_relatorio_semanal` para ativar essa funcionalidade.", icon="⚠️")
                except Exception as e:
                    st.error(f"erro ao enviar: {e}")

    with col_email_hist:
        st.markdown("#### histórico de envios")

        relatorios = listar_relatorios_enviados(limite=15)

        if not relatorios:
            st.info("nenhum relatório enviado ainda.", icon="📭")
        else:
            st.caption(f"{len(relatorios)} envio(s) registrado(s)")
            for r in relatorios:
                enviado_em = r.get('enviado_em', '')[:16] if r.get('enviado_em') else '—'
                tickers_str = r.get('tickers_incluidos', '') or ''
                tickers_list = tickers_str.split(',') if tickers_str else []
                n_tickers = len(tickers_list)
                status = r.get('status', 'enviado')
                status_cor = '#22c55e' if status == 'enviado' else '#ef4444'

                st.markdown(f"""
                <div class="config-card" style="padding:10px 14px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="color:#e2e8f0; font-size:0.9em;">📅 {enviado_em}</span>
                    <span style="color:{status_cor}; font-size:0.75em; font-weight:600;">● {status}</span>
                  </div>
                  <div style="color:#94a3b8; font-size:0.8em; margin-top:4px;">
                    {n_tickers} ticker(s) · tipo: {r.get('tipo','semanal')}
                  </div>
                </div>
                """, unsafe_allow_html=True)

    st.divider()

    st.markdown("#### 🔔 alertas de preço")
    st.info("os alertas de preço são configurados diretamente na página de cada ativo (watchlist). aqui você pode ver um resumo.", icon="🔔")

    try:
        from database.db import listar_alertas
        alertas_raw = listar_alertas(user_id_atual)
        if alertas_raw:
            import pandas as pd
            df_alertas = pd.DataFrame(alertas_raw)
            # garantir coluna de data compatível
            if 'criado_em' not in df_alertas.columns and 'created_at' in df_alertas.columns:
                df_alertas['criado_em'] = df_alertas['created_at']
            show_cols = [c for c in ['ticker', 'tipo', 'threshold', 'criado_em'] if c in df_alertas.columns]
            df_alertas = df_alertas[show_cols].rename(columns={'threshold': 'gatilho', 'criado_em': 'criado em'})
            st.dataframe(df_alertas, use_container_width=True, hide_index=True)
        else:
            st.caption("nenhum alerta de preço configurado.")
    except Exception as e:
        st.caption(f"não foi possível carregar alertas: {e}")

    st.divider()

    # ── alertas de health score ───────────────────────────────────────────────
    st.markdown("#### 🔔 alertas de health score")
    st.markdown(
        '<div style="font-family:Courier New; font-size:0.78rem; '
        'color:#94a3b8; margin-bottom:16px; line-height:1.6;">'
        'configure alertas para ser notificado quando o health score '
        'de um ativo cair abaixo do limite definido.<br>'
        '⚠️ o browser precisa ter permissão para notificações do browser.'
        '</div>',
        unsafe_allow_html=True,
    )

    if st.button("🔔 ativar notificações no browser", type="secondary",
                 key="btn_ativar_notif"):
        solicitar_permissao_notificacao()
        st.success("solicitação enviada! aceite a permissão no popup do browser.")

    st.markdown("---")

    # carrega watchlist padrão do usuário para listar ativos
    try:
        _wl_id_cfg   = get_watchlist_padrao()
        _wl_items    = listar_watchlist(watchlist_id=_wl_id_cfg)
    except Exception:
        _wl_items = []

    _configs_hs = {
        c['ticker']: c['threshold']
        for c in get_configs_alerta(user_id_atual)
    }

    if _wl_items:
        st.markdown("##### configurar por ativo")

        for item in _wl_items:
            t = item['ticker']
            col_t, col_sl, col_btn = st.columns([2, 3, 1])

            with col_t:
                st.markdown(
                    f'<div style="font-family:Courier New; color:#FF9900; '
                    f'padding-top:10px;">{t.replace(".SA", "")}</div>',
                    unsafe_allow_html=True,
                )
            with col_sl:
                threshold_val = st.slider(
                    f"limite {t}:",
                    min_value=0, max_value=80,
                    value=_configs_hs.get(t, 40),
                    step=5,
                    key=f"alert_th_{t}",
                    label_visibility="collapsed",
                )
            with col_btn:
                if t in _configs_hs:
                    if st.button("🗑️", key=f"del_alert_{t}",
                                 help="remover alerta"):
                        deletar_config_alerta(user_id_atual, t)
                        st.rerun()
                else:
                    if st.button("➕", key=f"add_alert_{t}",
                                 help="ativar alerta"):
                        salvar_config_alerta(user_id_atual, t, threshold_val)
                        st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 salvar todos os alertas", type="primary",
                     use_container_width=True, key="btn_salvar_alertas_hs"):
            for item in _wl_items:
                t  = item['ticker']
                th = st.session_state.get(f"alert_th_{t}", 40)
                salvar_config_alerta(user_id_atual, t, th)
            st.success("✅ alertas salvos com sucesso!")
    else:
        st.info("adicione ativos à watchlist para configurar alertas de health score.",
                icon="🔔")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — MINHA IA
# ══════════════════════════════════════════════════════════════════════════════
with tab_ia:
    st.subheader("🤖 configurações de ia")

    _user_ia = st.session_state.get('user_id')
    if not _user_ia:
        st.warning("faça login para configurar suas preferências de ia.", icon="🔒")
    else:
        _settings_atuais = get_user_settings(_user_ia)

        st.markdown(
            '<div style="font-family:Courier New; font-size:0.75rem; color:#555; '
            'margin-bottom:20px; line-height:1.6;">'
            '🔑 configure sua própria chave de api para não depender da chave global do servidor.<br>'
            'se o campo ficar vazio, o sistema usa automaticamente a chave global.'
            '</div>',
            unsafe_allow_html=True,
        )

        # ── provider labels ──────────────────────────────────────────────────
        _provider_labels = {k: v['label'] for k, v in PROVIDERS.items()}
        _provider_keys   = list(PROVIDERS.keys())

        _cur_provider = _settings_atuais.get('ai_provider', 'deepseek')
        _cur_provider_idx = _provider_keys.index(_cur_provider) if _cur_provider in _provider_keys else 0

        # ── formulário ──────────────────────────────────────────────────────
        with st.form("form_ai_settings"):
            col_ai1, col_ai2 = st.columns(2)

            with col_ai1:
                provider_sel = st.selectbox(
                    "provider de ia:",
                    options=_provider_keys,
                    format_func=lambda x: f"{'⚡' if x=='deepseek' else '🟢' if x=='openai' else '🔵' if x=='gemini' else '🟠'} {_provider_labels[x]}",
                    index=_cur_provider_idx,
                    key="cfg_ai_provider",
                )

                moeda_sel = st.selectbox(
                    "moeda base:",
                    options=['BRL', 'USD'],
                    index=0 if _settings_atuais.get('moeda_base', 'BRL') == 'BRL' else 1,
                    key="cfg_moeda",
                )

            with col_ai2:
                api_key_input = st.text_input(
                    "sua api key (opcional):",
                    type="password",
                    placeholder="sk-… ou deixe vazio para usar a chave global",
                    value="",          # nunca pré-preenche por segurança
                    key="cfg_api_key",
                    help="deixe vazio para manter a chave já salva ou usar a global",
                )

                benchmark_sel = st.selectbox(
                    "benchmark principal:",
                    options=['IBOV', 'CDI', 'SP500', 'IBOV+SP500'],
                    index=['IBOV', 'CDI', 'SP500', 'IBOV+SP500'].index(
                        _settings_atuais.get('benchmark', 'IBOV')
                    ),
                    key="cfg_benchmark",
                )

            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                _btn_salvar = st.form_submit_button(
                    "💾 salvar configurações",
                    type="primary",
                    use_container_width=True,
                )
            with col_btn2:
                _btn_testar = st.form_submit_button(
                    "🧪 testar conexão",
                    type="secondary",
                    use_container_width=True,
                )

            if _btn_salvar:
                _model_map = {
                    'deepseek':         'deepseek-chat',
                    'openai':           'gpt-4o',
                    'gemini':           'gemini-2.5-flash',
                    'anthropic_compat': 'claude-sonnet-4-5',
                }
                _novas = {
                    'ai_provider':     provider_sel,
                    'ai_model':        _model_map.get(provider_sel, 'deepseek-chat'),
                    'ai_api_key':      api_key_input,   # vazio → preserva anterior no banco
                    'moeda_base':      moeda_sel,
                    'benchmark':       benchmark_sel,
                    'alert_threshold': _settings_atuais.get('alert_threshold', 40),
                }
                salvar_user_settings(_user_ia, _novas)
                st.success("✅ configurações salvas com sucesso!")
                st.rerun()

            if _btn_testar:
                from utils.ai_client import chamar_ia, SYSTEM_ANALISTA as _SYS
                _model_map = {
                    'deepseek':         'deepseek-chat',
                    'openai':           'gpt-4o',
                    'gemini':           'gemini-2.5-flash',
                    'anthropic_compat': 'claude-sonnet-4-5',
                }
                _test_settings = {
                    'ai_provider': provider_sel,
                    'ai_model':    _model_map.get(provider_sel, 'deepseek-chat'),
                    'ai_api_key':  api_key_input,
                }
                with st.spinner(f"testando conexão com {_provider_labels.get(provider_sel, provider_sel)}…"):
                    try:
                        _resp = chamar_ia(
                            prompt_usuario="responda apenas: ok",
                            system="você é um assistente. responda apenas: ok",
                            max_tokens=10,
                            stream=False,
                            user_settings=_test_settings,
                        )
                        if _resp and 'ok' in _resp.lower():
                            st.success(f"✅ conexão com {_provider_labels.get(provider_sel)} funcionando!")
                        else:
                            st.warning(f"resposta inesperada: '{_resp}' — verifique o modelo.")
                    except Exception as _e_test:
                        st.error(f"❌ falha na conexão: {_e_test}")

        # ── status atual ─────────────────────────────────────────────────────
        _tem_chave = bool(_settings_atuais.get('ai_api_key'))
        _status_chave = "✅ chave pessoal configurada" if _tem_chave else "⚠️ usando chave global do servidor"
        st.markdown(
            f'<div style="font-family:Courier New; font-size:0.72rem; color:#555; '
            f'margin-top:12px; padding:8px 12px; background:#0d0d0d; '
            f'border:1px solid #1e1e1e; border-radius:4px;">'
            f'provider ativo: <span style="color:#FF9900;">{_provider_labels.get(_cur_provider, _cur_provider)}</span>'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'api key: <span style="color:{"#00C853" if _tem_chave else "#FF9900"};">{_status_chave}</span>'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'benchmark: <span style="color:#FF9900;">{_settings_atuais.get("benchmark", "IBOV")}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.divider()

        # ── referência de modelos ─────────────────────────────────────────────
        with st.expander("📋 referência de providers e modelos", expanded=False):
            _rows = []
            for _k, _v in PROVIDERS.items():
                _rows.append({
                    'provider':      _k,
                    'nome':          _v['label'],
                    'modelo padrão': _v['model_default'],
                    'variável secret': _v['secret_key'],
                })
            import pandas as _pd
            st.dataframe(_pd.DataFrame(_rows), use_container_width=True, hide_index=True)
            st.caption(
                "para usar a chave global, defina a variável correspondente em "
                "`.streamlit/secrets.toml`. a chave pessoal tem prioridade sobre a global."
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — ADMINISTRAÇÃO (apenas admin)
# ══════════════════════════════════════════════════════════════════════════════
with tab_admin:
    st.subheader("🛡️ administração do sistema")

    if not is_admin:
        st.warning("🔒 área restrita a administradores.", icon="🛡️")
        st.stop()

    # ── listagem de usuários ───────────────────────────────────────────────
    st.markdown("#### usuários cadastrados")

    usuarios = listar_usuarios()
    st.caption(f"{len(usuarios)} usuário(s) no sistema")

    for u in usuarios:
        tag_admin = "🛡️ admin" if u.get('is_admin') else "👤 usuário"
        ultimo_login = u.get('ultimo_login', '')
        ultimo_login_str = ultimo_login[:16] if ultimo_login else 'nunca'
        criado_em = u.get('criado_em', '')[:10] if u.get('criado_em') else '—'

        with st.expander(f"**{u['username']}** · {tag_admin}  —  {u.get('nome','')}", expanded=False):
            info1, info2, info3 = st.columns(3)
            with info1:
                st.metric("id", f"#{u['id']}")
            with info2:
                st.metric("criado em", criado_em)
            with info3:
                st.metric("último login", ultimo_login_str)

            st.caption(f"e-mail: {u.get('email') or '—'}")

            acoes1, acoes2 = st.columns([1, 1])

            with acoes1:
                with st.form(f"form_reset_senha_{u['id']}"):
                    nova_senha_admin = st.text_input(
                        "nova senha",
                        type="password",
                        placeholder="mínimo 6 caracteres",
                        key=f"nova_senha_admin_{u['id']}"
                    )
                    if st.form_submit_button("🔑 redefinir senha", use_container_width=True):
                        if len(nova_senha_admin) < 6:
                            st.error("mínimo 6 caracteres.")
                        else:
                            alterar_senha(u['id'], nova_senha_admin)
                            st.success(f"senha de '{u['username']}' redefinida.")

            with acoes2:
                if u['id'] != user_id_atual:
                    st.markdown("")
                    st.markdown("""
                    <div class="danger-zone">
                      <p style="color:#f87171; font-size:0.85em; margin:0 0 8px;">⚠️ zona de risco</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(
                        f"🗑️ deletar '{u['username']}'",
                        key=f"del_user_{u['id']}",
                        use_container_width=True,
                        type="secondary"
                    ):
                        deletar_usuario(u['id'])
                        st.warning(f"usuário '{u['username']}' removido.")
                        st.rerun()
                else:
                    st.info("você não pode deletar sua própria conta.", icon="ℹ️")

    st.divider()

    # ── criar usuário ──────────────────────────────────────────────────────
    st.markdown("#### ➕ criar novo usuário")

    with st.form("form_criar_usuario"):
        cu1, cu2 = st.columns(2)
        with cu1:
            novo_username = st.text_input("username", placeholder="login único (sem espaços)")
            novo_nome = st.text_input("nome completo", placeholder="opcional")
        with cu2:
            novo_email = st.text_input("e-mail", placeholder="opcional")
            nova_senha_novo = st.text_input("senha inicial", type="password", placeholder="mínimo 6 caracteres")

        novo_admin = st.checkbox("conceder permissão de administrador")

        if st.form_submit_button("✅ criar usuário", use_container_width=True, type="primary"):
            if not novo_username.strip():
                st.error("informe um username.")
            elif len(nova_senha_novo) < 6:
                st.error("a senha deve ter pelo menos 6 caracteres.")
            else:
                ok = criar_usuario(
                    novo_username.strip(),
                    nova_senha_novo,
                    nome=novo_nome,
                    email=novo_email,
                    is_admin=novo_admin
                )
                if ok:
                    st.success(f"✅ usuário '{novo_username}' criado com sucesso!")
                    st.rerun()
                else:
                    st.error(f"username '{novo_username}' já existe. escolha outro.")

    st.divider()

    # ── informações do sistema ─────────────────────────────────────────────
    st.markdown("#### 🖥️ informações do sistema")

    try:
        from database.supabase_client import get_supabase
        import pandas as pd
        sb = get_supabase()
        tabelas_conhecidas = [
            'users', 'watchlists', 'watchlist_items', 'portfolios',
            'portfolio_positions', 'health_scores', 'fundamentals_cache',
            'decision_log', 'report_history', 'alerts', 'ai_analysis_cache',
            'saved_comparisons', 'health_score_history',
        ]
        tamanhos = []
        for tabela in tabelas_conhecidas:
            try:
                res = sb.table(tabela).select('id', count='exact').execute()
                count = res.count if res.count is not None else len(res.data)
                tamanhos.append({'tabela': tabela, 'registros': count})
            except Exception:
                tamanhos.append({'tabela': tabela, 'registros': '—'})
        df_tabelas = pd.DataFrame(tamanhos)
        st.dataframe(df_tabelas, use_container_width=True, hide_index=True)
        st.caption("banco de dados: **Supabase (PostgreSQL)** — nuvem")
    except Exception as e:
        st.warning(f"não foi possível carregar informações do banco: {e}")

    st.divider()

    # ── limpeza de cache ───────────────────────────────────────────────────
    st.markdown("#### 🧹 manutenção")

    manut1, manut2 = st.columns(2)

    with manut1:
        if st.button("🧹 limpar cache do Streamlit", use_container_width=True):
            st.cache_data.clear()
            st.success("cache limpo com sucesso!")

    with manut2:
        if st.button("🗑️ limpar cache de IA (análises antigas)", use_container_width=True):
            try:
                from database.db import limpar_cache_ia_antigo
                removidos = limpar_cache_ia_antigo(dias=30)
                st.success(f"{removidos} análise(s) antiga(s) removida(s).")
            except Exception as e:
                st.error(f"erro: {e}")
