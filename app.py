"""Meu Monitor Financeiro — entry point.

Este arquivo intencionalmente contém apenas o mínimo:
    1. configuração da página + tema/CSS
    2. autenticação (login gate)
    3. carregamento dos DataFrames principais
    4. roteamento entre as páginas em `src/pages/`

Toda a lógica de negócio mora em `src/`.
"""
from __future__ import annotations

import streamlit as st

from src import auth, repository, sidebar, styles
from src.config import APP_ICON, APP_TITLE, SYSTEM_CATEGORIES
from src.finance import filter_by_month, list_months
from src.pages import (
    auto_dashboard, credit_card, dashboard, investments, settings, transactions,
)
from src.sidebar import PAGES


def _bootstrap_categories(categories_df) -> list[str]:
    """Lista usada nos selects: categorias do usuário + as do sistema."""
    user_categories = categories_df["Categoria"].dropna().unique().tolist()
    return user_categories + [
        c for c in SYSTEM_CATEGORIES if c not in user_categories
    ]


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    styles.inject()

    if not auth.is_logged_in():
        auth.render_login()
        return

    st.title(f"{APP_ICON} {APP_TITLE}")
    st.caption("Sincronizado com Google Sheets ☁️")

    # Carregamento único por rerun (cacheado em repository).
    df_transactions = repository.load_transactions()
    df_credit_card = repository.load_credit_card()
    df_categories = repository.load_categories()
    df_budgets = repository.load_budgets()
    df_fixed_costs = repository.load_fixed_costs()

    months = list_months(df_transactions, df_credit_card)
    state = sidebar.render(months)

    df_transactions_period, df_credit_card_period = filter_by_month(
        df_transactions, df_credit_card, state.selected_month,
    )
    categories = _bootstrap_categories(df_categories)

    page = state.selected_page
    if page == PAGES[0]:  # Dashboard
        dashboard.render(
            df_transactions=df_transactions,
            df_credit_card=df_credit_card,
            df_transactions_period=df_transactions_period,
            df_credit_card_period=df_credit_card_period,
            df_fixed_costs=df_fixed_costs,
            selected_month=state.selected_month,
        )
    elif page == PAGES[1]:  # Dashboard Automático 🤖
        auto_dashboard.render(df_credit_card=df_credit_card)
    elif page == PAGES[2]:  # Entradas e Saídas
        transactions.render(
            df_transactions=df_transactions, categories=categories,
        )
    elif page == PAGES[3]:  # Cartão de Crédito
        credit_card.render(
            df_credit_card=df_credit_card,
            df_credit_card_period=df_credit_card_period,
            categories=categories,
            selected_month=state.selected_month,
        )
    elif page == PAGES[4]:  # Investimentos
        investments.render(df_transactions=df_transactions)
    elif page == PAGES[5]:  # Configurações e Orçamento
        settings.render(
            df_categories=df_categories,
            df_budgets=df_budgets,
            df_fixed_costs=df_fixed_costs,
            df_transactions_period=df_transactions_period,
            df_credit_card_period=df_credit_card_period,
            selected_month=state.selected_month,
        )


if __name__ == "__main__":
    main()
