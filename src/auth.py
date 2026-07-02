"""Autenticação simples por senha (lida de st.secrets)."""
from __future__ import annotations

import streamlit as st

from src.config import APP_TITLE


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

    st.markdown(
        """
        <style>
            /* Aproxima o card de login do centro vertical da tela */
            [data-testid="stMainBlockContainer"] {
                padding-top: 10vh !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        with st.container(border=True):
            st.markdown(
                f"""
                <div style="text-align:center; padding: 0.6rem 0 0.2rem 0;">
                    <div style="font-size: 2.6rem; line-height: 1;">💸</div>
                    <div style="font-size: 1.35rem; font-weight: 700;
                                letter-spacing: -0.02em; color: #0F172A;
                                margin-top: 0.5rem;">
                        {APP_TITLE}
                    </div>
                    <div style="font-size: 0.85rem; color: #64748B;
                                margin-top: 0.25rem;">
                        Suas finanças, organizadas e seguras.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.form("login_form", clear_on_submit=False):
                password = st.text_input(
                    "Senha de acesso", type="password",
                    placeholder="Digite sua senha",
                )
                submitted = st.form_submit_button(
                    "Entrar", use_container_width=True,
                )
            if submitted:
                if password == expected:
                    st.session_state[_SESSION_KEY] = True
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
        st.markdown(
            """
            <div style="text-align:center; font-size: 0.75rem;
                        color: #94A3B8; margin-top: 0.8rem;">
                🔒 Acesso protegido por senha · dados no seu Google Sheets
            </div>
            """,
            unsafe_allow_html=True,
        )
