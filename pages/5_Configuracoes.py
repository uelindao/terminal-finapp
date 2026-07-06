import streamlit as st

from utils.auth   import require_auth, get_current_user, render_user_badge, logout
from utils.style  import aplicar_tema
from utils.components import (
    page_header, section_title, metric_card, status_card, empty_state, topbar,
    portfolio_kpis, info_box, inject_keyboard_shortcuts,
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
inject_keyboard_shortcuts()
try:
    from utils.themes import render_theme_switcher_sidebar
    render_theme_switcher_sidebar()
except Exception:
    pass
# Busca global de ativo — navegação de qualquer página para o deep dive (UX).
from utils.components import busca_global_sidebar
busca_global_sidebar()

user          = get_current_user()
user_id_atual = get_user_id()
is_admin      = st.session_state.get('is_admin', False)

_user_top_cfg = get_current_user() or {}
topbar(
    breadcrumb_itens=[("⚡ finterminal", "/"), ("configurações", None)],
    user_name=_user_top_cfg.get('username', '') or _user_top_cfg.get('nome', '') or 'usuário',
    sync_label="ao vivo",
)
page_header("⚙️ configurações", "conta · watchlists · portfólios · ia · administração")

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
# LAZY RENDERING (P4-1): seletor persistente no lugar de st.tabs — renderiza só a
# seção ativa. Abas independentes (verificado por AST: sem vazamento de variável).
_SECOES_C = ["👤 minha conta", "⭐ watchlists", "💼 portfólios", "🔔 alertas",
             "🤖 minha ia", "🎨 aparência", "🗄️ backfill", "👑 administração"]
if hasattr(st, "segmented_control"):
    _secao_c = st.segmented_control(
        "seção", _SECOES_C, default=_SECOES_C[0],
        key="config_secao", label_visibility="collapsed",
    ) or st.session_state.get("config_secao") or _SECOES_C[0]
else:
    _secao_c = st.radio("seção", _SECOES_C, index=0, horizontal=True,
                        key="config_secao", label_visibility="collapsed")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MINHA CONTA
# ══════════════════════════════════════════════════════════════════════════════
if _secao_c == "👤 minha conta":
    section_title("informações da conta")

    if user:
        _is_admin = bool(user.get('is_admin'))
        portfolio_kpis([
            {
                "nome":     "usuário",
                "valor":    user['username'],
                "sublabel": "login do sistema",
                "tone":     "info",
                "icone":    "👤",
            },
            {
                "nome":     "nome",
                "valor":    user['nome'] or "—",
                "sublabel": "nome completo cadastrado",
                "tone":     "info",
                "icone":    "📝",
            },
            {
                "nome":     "perfil",
                "valor":    "administrador" if _is_admin else "usuário",
                "sublabel": "acesso ao painel admin" if _is_admin else "acesso padrão",
                "tone":     "accent" if _is_admin else "muted",
                "icone":    "🛡" if _is_admin else "👁",
            },
        ])

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

    wl_padrao_id   = get_watchlist_padrao()
    wls_all        = listar_watchlists()
    nome_wl_padrao = next((w['nome'] for w in wls_all if w['id'] == wl_padrao_id), "—")
    pf_padrao_id   = get_portfolio_padrao()
    pfs_all        = listar_portfolios()
    nome_pf_padrao = next((p['nome'] for p in pfs_all if p['id'] == pf_padrao_id), "—")

    portfolio_kpis([
        {
            "nome":     "user id",
            "valor":    f"#{user_id_atual}",
            "sublabel": "identificador único",
            "tone":     "muted",
            "icone":    "🆔",
        },
        {
            "nome":     "watchlist padrão",
            "valor":    nome_wl_padrao,
            "sublabel": "abre por padrão na home",
            "tone":     "info",
            "icone":    "⭐",
        },
        {
            "nome":     "portfólio padrão",
            "valor":    nome_pf_padrao,
            "sublabel": "carteira ativa nos cálculos",
            "tone":     "info",
            "icone":    "💼",
        },
    ])

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚪 encerrar sessão", type="secondary"):
        logout()  # revoga token no banco e limpa session_state


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — WATCHLISTS
# ══════════════════════════════════════════════════════════════════════════════
if _secao_c == "⭐ watchlists":
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
if _secao_c == "💼 portfólios":
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
if _secao_c == "🔔 alertas":
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
            _df_al_s = df_al[show_cols]
            _mn_al = 'var(--font-mono,monospace)'
            _hdrs_al = "".join(
                f'<th style="padding:7px 10px;text-align:{"right" if c=="threshold" else "left"};'
                f'font-size:0.66rem;color:var(--text-muted);text-transform:uppercase;'
                f'border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
                for c in _df_al_s.columns
            )
            _rows_al = ""
            for _, row in _df_al_s.iterrows():
                _cells_al = ""
                for col in _df_al_s.columns:
                    _v = row[col]
                    _align = "right" if col == "threshold" else "left"
                    if col == "ticker":
                        _url_al = f"/Research?research_ticker={_v}"
                        _cells_al += (f'<td style="padding:7px 10px;"><a href="{_url_al}" target="_blank" '
                                      f'style="color:var(--accent);font-family:{_mn_al};font-weight:600;'
                                      f'font-size:0.8rem;text-decoration:none;" '
                                      f'onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'
                                      f'{str(_v).replace(".SA","")}</a></td>')
                    else:
                        _cells_al += (f'<td style="padding:7px 10px;text-align:{_align};">'
                                      f'<span style="font-family:{_mn_al};font-size:0.8rem;">{_v}</span></td>')
                _rows_al += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                             f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                             f'onmouseout="this.style.background=\'transparent\'">{_cells_al}</tr>')
            st.markdown(
                f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
                f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                f'<thead><tr>{_hdrs_al}</tr></thead><tbody>{_rows_al}</tbody></table></div>',
                unsafe_allow_html=True,
            )
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
if _secao_c == "🤖 minha ia":
    section_title("⚡ modo de análise ia")

    settings     = get_user_settings(user_id_atual) if user else {}
    _modo_atual  = st.session_state.get('ai_modo_atual')
    if _modo_atual is None:
        _modo_atual = 'pro' if settings.get('ai_api_key', '').strip() else 'free'
        st.session_state['ai_modo_atual'] = _modo_atual

    _col_t1, _col_t2 = st.columns(2)

    with _col_t1:
        _borda_free = "var(--accent)" if _modo_atual == 'free' else "var(--border-subtle)"
        st.markdown(
            f'<div style="background:var(--bg-surface);border:2px solid '
            f'{_borda_free};border-radius:6px;padding:16px;'
            f'text-align:center;">'
            f'<div style="font-size:1.2rem;">🆓</div>'
            f'<div style="font-family:var(--font-ui,sans-serif);color:var(--accent);'
            f'font-weight:700;margin:4px 0;">tier gratuito</div>'
            f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.7rem;'
            f'color:var(--text-muted);">gemini 2.0 flash · sem chave necessária</div>'
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
        _borda_pro = "var(--accent)" if _modo_atual == 'pro' else "var(--border-subtle)"
        st.markdown(
            f'<div style="background:var(--bg-surface);border:2px solid '
            f'{_borda_pro};border-radius:6px;padding:16px;'
            f'text-align:center;">'
            f'<div style="font-size:1.2rem;">⚡</div>'
            f'<div style="font-family:var(--font-ui,sans-serif);color:var(--accent);'
            f'font-weight:700;margin:4px 0;">tier pro</div>'
            f'<div style="font-family:var(--font-ui,sans-serif);font-size:0.7rem;'
            f'color:var(--text-muted);">deepseek v4 / openai · chave pessoal</div>'
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
        _prov_rows = [
            {'provider': k, 'nome': v['label'], 'modelo padrão': v['model_default'], 'secret': v['secret_key']}
            for k, v in PROVIDERS.items()
        ]
        _mn_pv = 'var(--font-mono,monospace)'
        _prov_cols = ['provider', 'nome', 'modelo padrão', 'secret']
        _hdrs_pv = "".join(
            f'<th style="padding:7px 10px;text-align:left;font-size:0.66rem;color:var(--text-muted);'
            f'text-transform:uppercase;border-bottom:1px solid var(--border-subtle);white-space:nowrap;">{c}</th>'
            for c in _prov_cols
        )
        _rows_pv = ""
        for row in _prov_rows:
            _cells_pv = "".join(
                f'<td style="padding:7px 10px;"><span style="font-family:{_mn_pv};font-size:0.78rem;">{row[c]}</span></td>'
                for c in _prov_cols
            )
            _rows_pv += (f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                         f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                         f'onmouseout="this.style.background=\'transparent\'">{_cells_pv}</tr>')
        st.markdown(
            f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
            f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
            f'<thead><tr>{_hdrs_pv}</tr></thead><tbody>{_rows_pv}</tbody></table></div>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — APARÊNCIA / TEMAS
# ══════════════════════════════════════════════════════════════════════════════
if _secao_c == "🎨 aparência":
    section_title("🎨 tema visual")

    try:
        from utils.themes import TEMAS, TEMAS_ORDER, TEMAS_META, get_tema_ativo, set_tema

        ativo = get_tema_ativo()

        st.markdown(
            '<div style="font-size:.82rem;color:var(--text-secondary);margin-bottom:20px;">'
            'Escolha a paleta de cores do terminal. A escolha persiste enquanto a sessão estiver ativa '
            'e pode ser salva via URL (<code>?theme=nome</code>).'
            '</div>',
            unsafe_allow_html=True,
        )

        from utils.themes import TEMAS_FONTES_DEFAULT, FONTES_TITULO as _FT, FONTES_UI as _FU, FONTES_DATA as _FD

        def _render_tema_card(col, tid, ativo):
            tema   = TEMAS[tid]
            _vars  = tema["vars"]
            _bg    = _vars["--bg-surface"]
            _acc   = _vars["--accent"]
            _bull  = _vars["--bull"]
            _bear  = _vars["--bear"]
            _txt   = _vars["--text-primary"]
            _brd   = _vars["--border-normal"]
            _light = tema.get("is_light", False)
            _shadow = "rgba(0,0,0,.08)" if _light else "rgba(0,0,0,.3)"
            _is_active = (tid == ativo)
            _border_w  = "2px" if _is_active else "1px"
            _border_c  = _acc if _is_active else _brd
            _selected_badge = (
                f'<span style="font-size:.55rem;background:{_acc};'
                f'color:{"#fff" if _light else "#000"};'
                f'padding:1px 5px;border-radius:3px;font-weight:700;">ATIVO</span>'
                if _is_active else ""
            )
            _fdef = TEMAS_FONTES_DEFAULT.get(tid, TEMAS_FONTES_DEFAULT["dark"])
            _font_titulo_name = _FT.get(_fdef["titulo"], {}).get("nome", "—")
            _font_ui_name     = _FU.get(_fdef["ui"],     {}).get("nome", "—")
            _font_data_name   = _FD.get(_fdef["data"],   {}).get("nome", "—")

            col.markdown(
                f'''<div style="background:{_bg};border:{_border_w} solid {_border_c};
                    border-radius:12px;padding:16px;margin-bottom:8px;
                    box-shadow:0 4px 16px {_shadow};transition:all .15s ease;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                        <span style="font-size:1.2rem">{tema['emoji']}</span>
                        {_selected_badge}
                    </div>
                    <div style="font-family:'Inter',system-ui;font-size:.78rem;
                        font-weight:600;color:{_txt};margin-bottom:3px;">{tema['nome']}</div>
                    <div style="font-family:'Inter',system-ui;font-size:.62rem;
                        color:{_vars['--text-muted']};margin-bottom:10px;">{tema['desc']}</div>
                    <div style="display:flex;gap:5px;margin-bottom:10px;">
                        <div style="width:18px;height:18px;border-radius:50%;background:{_acc};
                            border:1px solid rgba(0,0,0,.1);" title="acento"></div>
                        <div style="width:18px;height:18px;border-radius:50%;background:{_bull};
                            border:1px solid rgba(0,0,0,.1);" title="alta"></div>
                        <div style="width:18px;height:18px;border-radius:50%;background:{_bear};
                            border:1px solid rgba(0,0,0,.1);" title="baixa"></div>
                        <div style="width:18px;height:18px;border-radius:50%;background:{_vars['--info']};
                            border:1px solid rgba(0,0,0,.1);" title="info"></div>
                        <div style="width:18px;height:18px;border-radius:50%;background:{_vars['--amber']};
                            border:1px solid rgba(0,0,0,.1);" title="alerta"></div>
                    </div>
                    <div style="font-family:'Inter',system-ui;font-size:.57rem;
                        color:{_vars['--text-muted']};border-top:1px solid {_brd};
                        padding-top:8px;display:flex;flex-direction:column;gap:2px;">
                        <span>H · <em>{_font_titulo_name}</em></span>
                        <span>UI · <em>{_font_ui_name}</em></span>
                        <span>## · <em>{_font_data_name}</em></span>
                    </div>
                </div>''',
                unsafe_allow_html=True,
            )
            if col.button(
                "✓ aplicar" if _is_active else "aplicar",
                key=f"_tema_cfg_{tid}",
                type="primary" if _is_active else "secondary",
                use_container_width=True,
            ):
                set_tema(tid)
                st.rerun()

        # Grade agrupada — Escuros (3+2) e Claros (2)
        _escuros = [t for t in TEMAS_ORDER if not TEMAS[t].get("is_light")]
        _claros  = [t for t in TEMAS_ORDER if TEMAS[t].get("is_light")]

        st.markdown(
            '<div style="font-size:.62rem;text-transform:uppercase;letter-spacing:.08em;'
            'color:var(--text-muted);font-family:var(--font-ui);margin:8px 0 6px;">🌙 temas escuros</div>',
            unsafe_allow_html=True,
        )
        for row_tids in [_escuros[:3], _escuros[3:6], _escuros[6:]]:
            if not row_tids:
                continue
            _cols = st.columns(len(row_tids))
            for _col, tid in zip(_cols, row_tids):
                _render_tema_card(_col, tid, ativo)

        st.markdown(
            '<div style="font-size:.62rem;text-transform:uppercase;letter-spacing:.08em;'
            'color:var(--text-muted);font-family:var(--font-ui);margin:16px 0 6px;">☀️ temas claros</div>',
            unsafe_allow_html=True,
        )
        _cols_claros = st.columns(len(_claros))
        for _col, tid in zip(_cols_claros, _claros):
            _render_tema_card(_col, tid, ativo)

        # ── Tipografia personalizável ─────────────────────────────────────────
        st.markdown("---")
        section_title("🔤 tipografia")

        from utils.themes import (FONTES_TITULO, FONTES_UI, FONTES_DATA,
                                   get_fontes_ativas, resetar_fontes,
                                   TEMAS_FONTES_DEFAULT)

        fontes_ativas = get_fontes_ativas()
        defaults_tema = TEMAS_FONTES_DEFAULT.get(ativo, TEMAS_FONTES_DEFAULT["dark"])

        st.markdown(
            '<div style="font-size:.82rem;color:var(--text-secondary);margin-bottom:16px;">'
            'Escolha as fontes independentemente das cores do tema. '
            'Fontes de <strong>título</strong> aplicam em h1/h2/h3 e no logotipo. '
            'Fontes de <strong>interface</strong> aplicam em labels, botões e texto corrido. '
            'Fontes de <strong>dados</strong> aplicam em números, preços e código monospace.'
            '</div>',
            unsafe_allow_html=True,
        )

        col_ft, col_fu, col_fd = st.columns(3)

        with col_ft:
            st.markdown(
                '<div style="font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;'
                'color:var(--text-muted);margin-bottom:4px;">Títulos / Display</div>',
                unsafe_allow_html=True,
            )
            keys_titulo = list(FONTES_TITULO.keys())
            idx_t = keys_titulo.index(fontes_ativas["titulo"]) if fontes_ativas["titulo"] in keys_titulo else 0
            st.selectbox(
                "Fonte de títulos",
                options=keys_titulo,
                format_func=lambda k: FONTES_TITULO[k]["nome"],
                index=idx_t,
                label_visibility="collapsed",
                key="_font_titulo",
            )
            st.markdown(
                f'<div style="font-family:{FONTES_TITULO.get(st.session_state.get("_font_titulo", fontes_ativas["titulo"]), FONTES_TITULO[fontes_ativas["titulo"]])["css"]};'
                f'font-size:1.05rem;font-weight:700;color:var(--text-primary);margin-top:6px;">'
                f'Terminal Financeiro</div>'
                f'<div style="font-family:{FONTES_TITULO.get(st.session_state.get("_font_titulo", fontes_ativas["titulo"]), FONTES_TITULO[fontes_ativas["titulo"]])["css"]};'
                f'font-size:.72rem;color:var(--text-muted);">Preview do título</div>',
                unsafe_allow_html=True,
            )

        with col_fu:
            st.markdown(
                '<div style="font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;'
                'color:var(--text-muted);margin-bottom:4px;">Interface / Corpo</div>',
                unsafe_allow_html=True,
            )
            keys_ui = list(FONTES_UI.keys())
            idx_u = keys_ui.index(fontes_ativas["ui"]) if fontes_ativas["ui"] in keys_ui else 0
            st.selectbox(
                "Fonte de interface",
                options=keys_ui,
                format_func=lambda k: FONTES_UI[k]["nome"],
                index=idx_u,
                label_visibility="collapsed",
                key="_font_ui",
            )
            st.markdown(
                f'<div style="font-family:{FONTES_UI.get(st.session_state.get("_font_ui", fontes_ativas["ui"]), FONTES_UI[fontes_ativas["ui"]])["css"]};'
                f'font-size:.85rem;color:var(--text-secondary);margin-top:6px;">'
                f'Labels, botões e texto corrido</div>'
                f'<div style="font-family:{FONTES_UI.get(st.session_state.get("_font_ui", fontes_ativas["ui"]), FONTES_UI[fontes_ativas["ui"]])["css"]};'
                f'font-size:.70rem;text-transform:uppercase;letter-spacing:.06em;'
                f'color:var(--text-muted);">Preview de label</div>',
                unsafe_allow_html=True,
            )

        with col_fd:
            st.markdown(
                '<div style="font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;'
                'color:var(--text-muted);margin-bottom:4px;">Dados / Números</div>',
                unsafe_allow_html=True,
            )
            keys_data = list(FONTES_DATA.keys())
            idx_d = keys_data.index(fontes_ativas["data"]) if fontes_ativas["data"] in keys_data else 0
            st.selectbox(
                "Fonte de dados",
                options=keys_data,
                format_func=lambda k: FONTES_DATA[k]["nome"],
                index=idx_d,
                label_visibility="collapsed",
                key="_font_data",
            )
            st.markdown(
                f'<div style="font-family:{FONTES_DATA.get(st.session_state.get("_font_data", fontes_ativas["data"]), FONTES_DATA[fontes_ativas["data"]])["css"]};'
                f'font-size:1.1rem;font-weight:700;color:var(--text-primary);margin-top:6px;">'
                f'+12.48%  R$38,90</div>'
                f'<div style="font-family:{FONTES_DATA.get(st.session_state.get("_font_data", fontes_ativas["data"]), FONTES_DATA[fontes_ativas["data"]])["css"]};'
                f'font-size:.72rem;color:var(--text-muted);">Preview de número</div>',
                unsafe_allow_html=True,
            )

        # Botão reset
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("↺ padrão do tema", key="_reset_fonts", use_container_width=True):
                resetar_fontes()
                st.rerun()
        with c2:
            ft_nome = FONTES_TITULO.get(fontes_ativas["titulo"], {}).get("nome", "—")
            fu_nome = FONTES_UI.get(fontes_ativas["ui"],         {}).get("nome", "—")
            fd_nome = FONTES_DATA.get(fontes_ativas["data"],     {}).get("nome", "—")
            padroes = defaults_tema
            eh_padrao = (
                fontes_ativas["titulo"] == padroes["titulo"] and
                fontes_ativas["ui"]     == padroes["ui"]     and
                fontes_ativas["data"]   == padroes["data"]
            )
            cor_status = "var(--bull)" if eh_padrao else "var(--accent)"
            icone = "✓" if eh_padrao else "✎"
            st.markdown(
                f'<div style="font-size:.72rem;color:{cor_status};padding:6px 0;">'
                f'{icone}  {ft_nome} · {fu_nome} · {fd_nome}'
                f'{"  (padrão do tema)" if eh_padrao else ""}</div>',
                unsafe_allow_html=True,
            )

    except Exception as e:
        st.error(f"erro ao carregar temas: {e}")

    st.markdown("---")
    section_title("⌨️ atalhos de teclado")
    st.markdown("""
| Atalho | Ação |
|--------|------|
| `Ctrl+K` | Abre o command palette (busca tickers e páginas) |
| `Alt+1` | Home |
| `Alt+2` | Research |
| `Alt+3` | Discovery |
| `Alt+4` | Macro |
| `Alt+5` | Portfolio |
| `Alt+6` | Configurações |
| `↑ ↓` | Navegar no command palette |
| `Enter` | Selecionar item / confirmar |
| `Esc` | Fechar command palette |
""")

    st.markdown("---")
    section_title("📊 tipo de gráfico padrão")
    st.info(
        "O toggle de linha/barras aparece acima de cada gráfico compatível. "
        "A escolha é por seção e persiste durante a sessão atual.",
        icon="ℹ️",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — ADMINISTRAÇÃO (apenas admins)
# ══════════════════════════════════════════════════════════════════════════════
if _secao_c == "🗄️ backfill":
    if not is_admin:
        st.markdown(
            '<div style="text-align:center; padding:60px 24px;">'
            '<div style="font-size:2.4rem; opacity:0.25; margin-bottom:14px;">🔒</div>'
            '<div style="font-family:var(--font-ui); font-size:0.85rem;'
            ' color:var(--text-muted);">acesso restrito a administradores.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        try:
            from utils.backfill_view import render as _render_backfill
            _render_backfill()
        except Exception as _e_bf:
            st.error(f"falha ao carregar o painel de backfill: {_e_bf}")


if _secao_c == "👑 administração":
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

    # ── QUALIDADE DOS DADOS (P2-2) ────────────────────────────────────────
    section_title("qualidade dos dados — fundamentals_cache")
    try:
        from database.db import get_todos_fundamentos_cache
        from utils.data_quality import calcular_cobertura, CAMPOS_CRITICOS
        _cache_dq = get_todos_fundamentos_cache() or {}
        _cov = calcular_cobertura(_cache_dq, top_piores=25)
        st.caption(
            f"{_cov['total']} tickers no cache. cobertura = % com o campo preenchido; "
            "campos não aplicáveis por mercado (p/l de fii, ev/ebitda de banco) são ignorados."
        )

        _mkts = [m for m in ("BR", "US", "FII") if m in _cov["por_mercado"]]
        if _mkts:
            _cols_dq = st.columns(len(_mkts))
            for _col_dq, _m in zip(_cols_dq, _mkts):
                _d = _cov["por_mercado"][_m]
                _tone = ("bull" if _d["cobertura_media"] >= 85
                         else "amber" if _d["cobertura_media"] >= 60 else "bear")
                with _col_dq:
                    metric_card(f"{_m} — cobertura média",
                                f"{_d['cobertura_media']:.0f}%",
                                f"{_d['n']} tickers", _tone)

            # Tabela campo × mercado
            _mn_dq = 'var(--font-mono,monospace)'
            _hdr = '<th style="padding:6px 10px;text-align:left;font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;border-bottom:1px solid var(--border-subtle);">campo</th>'
            for _m in _mkts:
                _hdr += f'<th style="padding:6px 10px;text-align:right;font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;border-bottom:1px solid var(--border-subtle);">{_m}</th>'
            _rows_dq = ""
            for _campo in CAMPOS_CRITICOS:
                _cells = f'<td style="padding:6px 10px;font-family:{_mn_dq};font-size:0.78rem;color:var(--text-secondary);">{_campo}</td>'
                for _m in _mkts:
                    _pct = _cov["por_mercado"][_m]["campos"].get(_campo)
                    if _pct is None:
                        _cells += '<td style="padding:6px 10px;text-align:right;color:var(--text-muted);">n/a</td>'
                    else:
                        _c = ("#2ecc71" if _pct >= 85 else "#f39c12" if _pct >= 60 else "#e74c3c")
                        _cells += f'<td style="padding:6px 10px;text-align:right;font-family:{_mn_dq};font-size:0.78rem;color:{_c};">{_pct:.0f}%</td>'
                _rows_dq += f'<tr style="border-bottom:1px solid var(--border-subtle);">{_cells}</tr>'
            st.markdown(
                f'<div style="overflow-x:auto;margin:8px 0;"><table style="width:100%;border-collapse:collapse;'
                f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
                f'<thead><tr>{_hdr}</tr></thead><tbody>{_rows_dq}</tbody></table></div>',
                unsafe_allow_html=True,
            )

        # Piores tickers (mais campos faltando)
        if _cov["piores"]:
            with st.expander(f"🔎 {len(_cov['piores'])} tickers com mais campos faltando", expanded=False):
                for _p in _cov["piores"]:
                    _q = _p["quality"]
                    _q_str = f"{_q:.0f}%" if isinstance(_q, (int, float)) else "—"
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;gap:12px;'
                        f'padding:3px 0;border-bottom:1px solid var(--border-subtle);font-size:0.75rem;">'
                        f'<span style="font-family:var(--font-mono,monospace);color:var(--accent);">'
                        f'{_p["ticker"]} <span style="color:var(--text-muted);">[{_p["mercado"]}·{_p["fonte"]}·q{_q_str}]</span></span>'
                        f'<span style="color:var(--bear);">faltando: {", ".join(_p["faltando"])}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # Estado dos disjuntores de provedores
        try:
            from utils.market_data import provider_health
            _ph = provider_health()
            _yf = _ph.get("yfinance_info", {})
            _ab = _yf.get("aberto")
            _cor_ph = "var(--bear)" if _ab else "var(--bull)"
            st.markdown(
                f'<div style="font-size:0.72rem;color:var(--text-muted);margin-top:8px;">'
                f'circuit breaker yfinance.info: '
                f'<span style="color:{_cor_ph};">{"ABERTO (rate-limit)" if _ab else "fechado (ok)"}</span> · '
                f'falhas consecutivas: {_yf.get("falhas_consecutivas", 0)}'
                f'{" · cooldown " + str(_yf.get("cooldown_restante_s", 0)) + "s" if _ab else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )
        except Exception:
            pass
    except Exception as _e_dq:
        st.info(f"cobertura de dados indisponível: {_e_dq}")

    st.markdown("<br>", unsafe_allow_html=True)
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
        _mn_db = 'var(--font-mono,monospace)'
        _hdrs_db = (
            f'<th style="padding:7px 10px;text-align:left;font-size:0.66rem;color:var(--text-muted);'
            f'text-transform:uppercase;border-bottom:1px solid var(--border-subtle);">tabela</th>'
            f'<th style="padding:7px 10px;text-align:right;font-size:0.66rem;color:var(--text-muted);'
            f'text-transform:uppercase;border-bottom:1px solid var(--border-subtle);">registros</th>'
        )
        _rows_db = ""
        for r in rows:
            _cnt = r['registros']
            _cnt_color = "var(--text-primary)" if isinstance(_cnt, int) and _cnt > 0 else "var(--text-muted)"
            _rows_db += (
                f'<tr style="border-bottom:1px solid var(--border-subtle);" '
                f'onmouseover="this.style.background=\'var(--bg-hover,rgba(255,255,255,0.04))\'" '
                f'onmouseout="this.style.background=\'transparent\'">'
                f'<td style="padding:7px 10px;"><span style="font-family:{_mn_db};font-size:0.8rem;">{r["tabela"]}</span></td>'
                f'<td style="padding:7px 10px;text-align:right;"><span style="font-family:{_mn_db};font-size:0.8rem;color:{_cnt_color};">{_cnt}</span></td>'
                f'</tr>'
            )
        st.markdown(
            f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
            f'font-family:var(--font-ui,sans-serif);background:var(--bg-surface);">'
            f'<thead><tr>{_hdrs_db}</tr></thead><tbody>{_rows_db}</tbody></table></div>',
            unsafe_allow_html=True,
        )
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
