import streamlit as st
import hmac
from utils.style import aplicar_tema
from utils.components import page_header, empty_state
from database.db import autenticar_usuario, criar_usuario, listar_usuarios, alterar_senha, deletar_usuario

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
    """limpa a sessão e redireciona para o login."""
    for key in ['autenticado', 'user_id', 'username', 'nome', 'is_admin', 'password_correct', 'logged_in_user']:
        st.session_state.pop(key, None)
    st.rerun()

def require_auth() -> bool:
    """
    verifica autenticação. se não estiver logado, mostra a tela de login e retorna false.
    usar no topo de cada página.
    """
    if st.session_state.get('autenticado', False):
        return True

    _render_tela_login()
    return False

def _render_tela_login():
    """renderiza a tela de login centralizada."""
    aplicar_tema()

    st.markdown('<br>' * 4, unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])

    with col:
        st.markdown('''
            <div style="text-align:center; margin-bottom:32px;">
                <div style="font-family:Courier New; font-size:2rem; color:#FF9900; font-weight:bold; letter-spacing:0.15em;">
                    ⚡ finterminal
                </div>
                <div style="font-family:Courier New; font-size:0.78rem; color:#333; text-transform:uppercase; letter-spacing:0.2em; margin-top:4px;">
                    terminal de análise financeira
                </div>
            </div>
        ''', unsafe_allow_html=True)

        with st.container():
            st.markdown('''
                <div style="background:#0d0d0d; border:1px solid #1e1e1e; border-top:2px solid #FF9900; border-radius:6px; padding:24px 28px; margin-bottom:16px;">
                    <div style="font-family:Courier New; font-size:0.75rem; color:#555; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:16px;">
                        🔒 acesso restrito
                    </div>
                </div>
            ''', unsafe_allow_html=True)

            with st.form("form_login"):
                usuario_input = st.text_input(
                    "usuário",
                    placeholder="seu_usuario",
                    key="login_username",
                    label_visibility="collapsed"
                )
                senha_input = st.text_input(
                    "senha",
                    type="password",
                    placeholder="••••••••",
                    key="login_password",
                    label_visibility="collapsed"
                )

                if st.form_submit_button("entrar", type="primary", use_container_width=True):
                    if usuario_input and senha_input:
                        # a validação agora volta a ser estritamente via banco de dados
                        usuario = autenticar_usuario(usuario_input, senha_input)
                        
                        if usuario:
                            st.session_state['autenticado']  = True
                            st.session_state['user_id']      = usuario['id']
                            st.session_state['username']     = usuario['username']
                            st.session_state['nome']         = usuario['nome'] or usuario['username']
                            st.session_state['is_admin']     = bool(usuario['is_admin'])
                            st.session_state['password_correct']  = True
                            st.session_state['logged_in_user']    = usuario['username']
                            st.rerun()
                        else:
                            st.error("⚠️ usuário ou senha incorretos.")
                    else:
                        st.warning("preencha usuário e senha.")

        st.markdown(
            '<div style="font-family:Courier New; font-size:0.68rem; color:#2a2a2a; text-align:center; margin-top:20px;">'
            'finterminal — uso pessoal e restrito</div>',
            unsafe_allow_html=True
        )

def render_user_badge():
    """exibe o badge do utilizador logado na sidebar com o botão de logout."""
    user = get_current_user()
    if not user:
        return

    with st.sidebar:
        st.markdown('<div style="height:1px; background:#1e1e1e; margin:8px 0;"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-family:Courier New; font-size:0.72rem; color:#555; padding:4px 0;">👤 {user["nome"].lower()}</div>',
            unsafe_allow_html=True
        )
        if st.button("sair", key="btn_logout", use_container_width=True):
            logout()

# ──────────────────────────────────────────────────────────
# painel de administração
# ──────────────────────────────────────────────────────────

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