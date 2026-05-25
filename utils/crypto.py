"""
utils/crypto.py
Criptografia simétrica para API keys de usuários.
Usa Fernet com chave derivada do APP_SECRET configurado em secrets.toml.
"""
from __future__ import annotations

import base64
import hashlib

from utils.logger import get_logger

logger = get_logger(__name__)


def _get_fernet():
    """
    Cria instância Fernet usando APP_SECRET do secrets.toml.
    A chave de 32 bytes é derivada deterministicamente do secret,
    garantindo que a mesma secret sempre gere a mesma chave.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "pacote 'cryptography' não encontrado. "
            "adicione 'cryptography>=41.0.0' ao requirements.txt."
        ) from exc

    try:
        import streamlit as st
        try:
            app_secret = st.secrets["APP_SECRET"]
        except (KeyError, AttributeError):
            app_secret = "finterminal_default_secret_2026"
    except Exception:
        app_secret = "finterminal_default_secret_2026"

    key_bytes = hashlib.sha256(app_secret.encode()).digest()
    key_b64   = base64.urlsafe_b64encode(key_bytes)
    return Fernet(key_b64)


def encrypt_key(api_key: str) -> str:
    """
    Criptografa uma API key para armazenar no banco.
    Retorna string vazia se a entrada for vazia ou ocorrer erro.
    """
    if not api_key or not api_key.strip():
        return ""
    try:
        f = _get_fernet()
        return f.encrypt(api_key.strip().encode()).decode()
    except Exception as e:
        logger.error(f"[crypto] falha ao criptografar chave: {e}")
        return ""


def decrypt_key(encrypted: str) -> str:
    """
    Descriptografa uma API key do banco.
    Retorna string vazia se a entrada for vazia ou a descriptografia falhar
    (chave inválida, APP_SECRET diferente do original, etc.).
    """
    if not encrypted or not encrypted.strip():
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(encrypted.strip().encode()).decode()
    except Exception as e:
        logger.warning(f"[crypto] falha ao descriptografar chave: {e}")
        return ""
