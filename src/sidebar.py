"""Sidebar com logout, filtro de mês e menu de navegação."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import streamlit as st

from src import repository
from src.auth import logout
from src.config import ConfigKeys, TEMA_PADRAO

ALL_MONTHS = "Todos os Meses"

PAGES = [
    "Dashboard",
    "Entradas e Saídas",
    "Cartão de Crédito",
    "Investimentos",
    "Importar do banco",
    "Configurações e Orçamento",
]


@dataclass(frozen=True)
class SidebarState:
    selected_month: str
    selected_page: str
    tema: str = TEMA_PADRAO


def render(months: list[str]) -> SidebarState:
    """Renderiza a sidebar e retorna o estado escolhido pelo usuário."""
    st.sidebar.markdown("### 💸 Monitor Financeiro")
    st.sidebar.caption("Controle total das suas finanças.")
    st.sidebar.divider()

    if st.sidebar.button("Sair", use_container_width=True):
        logout()

    st.sidebar.divider()
    st.sidebar.subheader("Filtro de mês")
    current_month = date.today().strftime("%m/%Y")
    # Garante que o mês atual sempre apareça no select, mesmo que ainda
    # não haja lançamentos.
    available = sorted(set(months) | {current_month}, reverse=True)
    options = [ALL_MONTHS, *available]
    default_idx = options.index(current_month)
    month = st.sidebar.selectbox("Período:", options, index=default_idx)

    st.sidebar.divider()
    st.sidebar.subheader("Navegação")
    page = st.sidebar.radio("Escolha uma seção:", PAGES, label_visibility="collapsed")

    st.sidebar.divider()
    escuro = st.sidebar.toggle(
        "🌙 Modo escuro", value=st.session_state.get("tema", TEMA_PADRAO) == "dark",
        help="A preferência fica salva na sua planilha.",
    )
    tema = "dark" if escuro else "light"
    if tema != st.session_state.get("tema"):
        st.session_state["tema"] = tema
        repository.save_config_text(ConfigKeys.TEMA, tema)
        st.rerun()

    return SidebarState(selected_month=month, selected_page=page, tema=tema)
