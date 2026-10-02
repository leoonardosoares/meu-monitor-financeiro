"""Sidebar com logout, filtro de mês e menu de navegação."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from src import repository
from src.auth import logout
from src.config import ConfigKeys, TEMA_PADRAO
from src.dates import parse_month_label

ALL_MONTHS = "Todos os Meses"

PAGES = [
    "Dashboard",
    "Entradas e Saídas",
    "Cartão de Crédito",
    "Investimentos",
    "Sincronização",
    "Configurações e Orçamento",
]


@dataclass(frozen=True)
class SidebarState:
    selected_month: str
    selected_page: str
    tema: str = TEMA_PADRAO


def render(months: list[str]) -> SidebarState:
    """Renderiza a sidebar e retorna o estado escolhido pelo usuário."""
    st.sidebar.markdown(
        '<div class="mf-brand"><span class="mf-brand__logo">💸</span>'
        '<div><div class="mf-brand__name">Monitor Financeiro</div>'
        '<div class="mf-brand__sub">suas contas, do banco para cá</div>'
        '</div></div>', unsafe_allow_html=True)

    st.sidebar.markdown('<div class="mf-side-label">Menu</div>',
                        unsafe_allow_html=True)
    page = st.sidebar.radio("Escolha uma seção:", PAGES,
                            label_visibility="collapsed", key="nav")

    st.sidebar.markdown('<div class="mf-side-label">Período</div>',
                        unsafe_allow_html=True)
    current_month = date.today().strftime("%m/%Y")
    # Garante que o mês atual sempre apareça no select, mesmo que ainda
    # não haja lançamentos.
    available = sorted(set(months) | {current_month},
                       key=lambda m: parse_month_label(m) or pd.Timestamp.min,
                       reverse=True)
    options = [ALL_MONTHS, *available]
    default_idx = options.index(current_month)
    month = st.sidebar.selectbox("Período", options, index=default_idx,
                                 label_visibility="collapsed")

    st.sidebar.markdown('<div class="mf-side-label">Aparência</div>',
                        unsafe_allow_html=True)
    escuro = st.sidebar.toggle(
        "🌙 Modo escuro", value=st.session_state.get("tema", TEMA_PADRAO) == "dark",
        help="A preferência fica salva na sua planilha.",
    )
    tema = "dark" if escuro else "light"
    if tema != st.session_state.get("tema"):
        st.session_state["tema"] = tema
        repository.save_config_text(ConfigKeys.TEMA, tema)
        st.rerun()

    st.sidebar.markdown('<div class="mf-side-gap"></div>',
                        unsafe_allow_html=True)
    if st.sidebar.button("Sair", use_container_width=True):
        logout()

    return SidebarState(selected_month=month, selected_page=page, tema=tema)
