"""Autenticação simples por senha (lida de st.secrets)."""
from __future__ import annotations

import streamlit as st


_SESSION_KEY = "_auth_logged_in"


def is_logged_in() -> bool:
    return bool(st.session_state.get(_SESSION_KEY))


def logout() -> None:
    st.session_state[_SESSION_KEY] = False
    st.rerun()


def _expected_password() -> str | None:
    return st.secrets.get("APP_PASSWORD")


def render_login() -> None:
    """Renderiza a tela de login. Não retorna nada — define a sessão."""
    expected = _expected_password()
    if not expected:
        st.error(
            "⚠️ A senha do app não está configurada. "
            "Defina `APP_PASSWORD` em `.streamlit/secrets.toml`."
        )
        st.stop()

    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.title("🔒 Acesso Restrito")
        st.caption("Entre com sua senha para acessar o Monitor Financeiro.")
        with st.form("login_form", clear_on_submit=False):
            password = st.text_input("Senha:", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
        if submitted:
            if password == expected:
                st.session_state[_SESSION_KEY] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
