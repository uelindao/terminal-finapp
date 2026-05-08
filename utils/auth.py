import streamlit as st
import hmac
from utils.style import aplicar_tema

def check_password():
    """retorna true se o usuário digitou a senha correta."""
    
    # aplica o tema escuro na tela de login também
    aplicar_tema()
    
    def password_entered():
        """verifica se a senha digitada bate com o secrets.toml."""
        if hmac.compare_digest(st.session_state["password"], st.secrets["admin"]["password"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # apaga a senha da memória por segurança
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    # desenha a tela de login centralizada se não estiver logado
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<h2 style='text-align: center; color: #FF9900;'>🔒 acesso restrito</h2>", unsafe_allow_html=True)
        st.write("esta é uma área privada do selva vision. insira a credencial de administrador para continuar.")
        
        st.text_input(
            "senha de acesso:", 
            type="password", 
            on_change=password_entered, 
            key="password"
        )
        
        if "password_correct" in st.session_state:
            st.error("⚠️ senha incorreta. acesso negado.")
            
    return False