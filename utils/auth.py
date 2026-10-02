import streamlit as st
import secrets as _pysecrets
from utils.style import aplicar_tema
from utils.components import page_header, empty_state
from database.db import (
    autenticar_usuario, criar_usuario, listar_usuarios, alterar_senha, deletar_usuario,
    criar_sessao, validar_sessao, revogar_sessao,
)

_SESSION_PARAM = "s"   # query param que carrega o token de sessão
# Reduzido de 7 dias para 24h — token vaza em URL/screenshots/Referer,
# janela curta + sliding window (estende a cada uso) limita exposição.
_SESSION_HOURS = 24


def _login_por_sessao(token: str) -> bool:
    """Valida token no Supabase e preenche session_state. Retorna True se OK."""
    user = validar_sessao(token)
    if not user:
        return False
    st.session_state['autenticado']   = True
    st.session_state['user_id']       = user['id']
    st.session_state['username']      = user['username']
    st.session_state['nome']          = user.get('nome') or user['username']
    st.session_state['is_admin']      = bool(user.get('is_admin', False))
    st.session_state['session_token'] = token
    return True


def _token_na_url() -> str | None:
    """Lê ?s=TOKEN da URL atual."""
    try:
        return st.query_params.get(_SESSION_PARAM)
    except Exception:
        return None


def _fixar_token_na_url(token: str):
    """Garante que ?s=TOKEN está na URL — sem sobrescrever outros params."""
    try:
        if st.query_params.get(_SESSION_PARAM) != token:
            st.query_params[_SESSION_PARAM] = token
    except Exception:
        pass


def get_current_user() -> dict | None:
    """retorna o utilizador logado ou none."""
    if st.session_state.get('autenticado', False):
        return {
            'user_id':  st.session_state.get('user_id'),
            'username': st.session_state.get('username'),
            'nome':     st.session_state.get('nome'),
            'is_admin': st.session_state.get('is_admin', False),
        }
    return None


def logout():
    """Revoga o token no Supabase, remove da URL e limpa a sessão."""
    token = st.session_state.get('session_token')
    if token:
        revogar_sessao(token)
    try:
        st.query_params.pop(_SESSION_PARAM, None)
    except Exception:
        pass
    for key in ['autenticado', 'user_id', 'username', 'nome', 'is_admin',
                'password_correct', 'logged_in_user', 'session_token']:
        st.session_state.pop(key, None)
    st.rerun()


def require_auth() -> bool:
    """
    Verifica autenticação em 3 camadas:
    1. session_state (aba já logada)
    2. ?s=TOKEN na URL (nova aba com link de sessão)
    3. tela de login
    """
    # 1. Já autenticado nesta aba — garante token na URL para links cross-tab
    if st.session_state.get('autenticado', False):
        _fixar_token_na_url(st.session_state.get('session_token', ''))
        return True

    # 2. Token na URL (nova aba aberta via link ou cópia de URL)
    token = _token_na_url()
    if token and _login_por_sessao(token):
        return True

    # 3. Tela de login
    _render_tela_login()
    return False

def _render_tela_login():
    """renderiza a tela de login centralizada."""
    aplicar_tema()

    st.markdown('<div class="ft-login-brand">FIN<span style="color:var(--accent)"> / </span>TERMINAL</div>', unsafe_allow_html=True)
    intro, gap, col = st.columns([1.2, .15, 1], vertical_alignment="center")
    with intro:
        st.markdown('<div class="ft-login-art"><div class="ft-page-eyebrow">Inteligência financeira pessoal</div>'
                    '<h1>Mais contexto.<br><em>Melhores decisões.</em></h1>'
                    '<p>Conecte fundamentos, cenário econômico e sua carteira em um único espaço de análise.</p>'
                    '<div class="ft-login-index"><span>01 / MERCADO</span><span>02 / ANÁLISE</span><span>03 / CARTEIRA</span></div></div>', unsafe_allow_html=True)
    with col:
        st.markdown('<div class="ft-login-heading">Acesse seu terminal</div><div class="ft-login-caption">Entre com sua conta para continuar suas análises.</div>', unsafe_allow_html=True)
        with st.container():
            with st.form("form_login"):
                usuario_input = st.text_input(
                    "Usuário",
                    placeholder="Seu nome de usuário",
                    key="login_username"
                )
                senha_input = st.text_input(
                    "Senha",
                    type="password",
                    placeholder="••••••••",
                    key="login_password"
                )

                if st.form_submit_button("Entrar no terminal", type="primary", use_container_width=True):
                    if usuario_input and senha_input:
                        usuario = autenticar_usuario(usuario_input, senha_input)

                        if usuario:
                            # 256-bit URL-safe token (vs 128-bit do uuid4 anterior)
                            token = _pysecrets.token_urlsafe(32)
                            criar_sessao(usuario['id'], token, horas=_SESSION_HOURS)

                            st.session_state['autenticado']       = True
                            st.session_state['user_id']           = usuario['id']
                            st.session_state['username']          = usuario['username']
                            st.session_state['nome']              = usuario['nome'] or usuario['username']
                            st.session_state['is_admin']          = bool(usuario['is_admin'])
                            st.session_state['password_correct']  = True
                            st.session_state['logged_in_user']    = usuario['username']
                            st.session_state['session_token']     = token
                            # fixa o token na URL imediatamente (cross-tab session)
                            st.query_params[_SESSION_PARAM] = token
                            st.rerun()
                        else:
                            st.error("⚠️ usuário ou senha incorretos.")
                    else:
                        st.warning("preencha usuário e senha.")

        st.markdown('<div class="ft-login-footer">Acesso pessoal · Seus dados ficam vinculados à sua conta.</div>', unsafe_allow_html=True)


def render_user_badge():
    """Shell compartilhado com navegação nativa e conta em divulgação progressiva."""
    user = get_current_user()
    if not user:
        return
    from html import escape
    with st.sidebar:
        st.markdown('<div class="ft-nav-heading"><div class="ft-login-brand">FIN<span style="color:var(--accent)"> / </span>TERMINAL</div></div>', unsafe_allow_html=True)
        for path, label, icon in [
            ("Home.py", "Visão geral", "space_dashboard"),
            ("pages/3_Macro.py", "Cenário macro", "public"),
            ("pages/2_Discovery.py", "Oportunidades", "travel_explore"),
            ("pages/1_Research.py", "Análise de ativos", "query_stats"),
            ("pages/4_Portfolio.py", "Carteira", "account_balance_wallet"),
            ("pages/5_Configuracoes.py", "Configurações", "tune"),
        ]:
            st.page_link(path, label=label, icon=f":material/{icon}:", use_container_width=True)
        name = str(user.get("nome") or user.get("username") or "Usuário")
        role = "Administrador" if user.get("is_admin") else "Conta pessoal"
        st.markdown(f'<div class="ft-account"><span class="ft-account-avatar">{escape(name[:1].upper())}</span>'
                    f'<div><div class="ft-account-name">{escape(name)}</div><div class="ft-account-role">{role}</div></div></div>', unsafe_allow_html=True)
        with st.expander("Minha sessão", expanded=False):
            st.caption(f"Conectado como {user['username']}.")
            if st.button("Encerrar sessão", key="btn_logout", use_container_width=True):
                logout()


def render_painel_admin():
    """renderiza o painel de gestão de utilizadores (apenas para admins)."""
    user = get_current_user()
    if not user or not user['is_admin']:
        return

    with st.expander("⚙️ painel de administração", expanded=False):
        st.markdown("##### gestão de usuários")

        usuarios = listar_usuarios()
        if usuarios:
            for u in usuarios:
                c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                c1.text(u['username'])
                c2.text(u['nome'] or '—')
                c3.text(f"admin: {'sim' if u['is_admin'] else 'não'}")
                if c4.button("✕", key=f"del_user_{u['id']}", disabled=(u['id'] == user['user_id'])):
                    deletar_usuario(u['id'])
                    st.success(f"usuário {u['username']} removido.")
                    st.rerun()
        else:
            empty_state("👥", "sem usuários", "nenhum usuário encontrado.")

        st.markdown("---")
        st.markdown("##### criar novo usuário")
        with st.form("form_novo_usuario", clear_on_submit=True):
            nc1, nc2 = st.columns(2)
            with nc1:
                novo_user = st.text_input("username:")
                novo_nome = st.text_input("nome completo:")
            with nc2:
                nova_senha = st.text_input("senha:", type="password")
                novo_email = st.text_input("email (opcional):")
            novo_admin = st.checkbox("permissão de administrador")

            if st.form_submit_button("criar usuário", type="primary"):
                if novo_user and nova_senha:
                    ok = criar_usuario(novo_user, nova_senha, novo_nome, novo_email, novo_admin)
                    if ok:
                        st.success(f"✅ usuário '{novo_user}' criado!")
                    else:
                        st.error("usuário já existe.")
                else:
                    st.warning("username e senha são obrigatórios.")

        st.markdown("---")
        st.markdown("##### alterar senha")
        with st.form("form_alterar_senha", clear_on_submit=True):
            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                user_ids = {u['username']: u['id'] for u in usuarios}
                sel_user = st.selectbox("usuário:", list(user_ids.keys()))
            with ac2:
                nova_senha_alt = st.text_input("nova senha:", type="password")
            with ac3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.form_submit_button("alterar", type="primary"):
                    if nova_senha_alt:
                        alterar_senha(user_ids[sel_user], nova_senha_alt)
                        st.success("senha alterada com sucesso.")