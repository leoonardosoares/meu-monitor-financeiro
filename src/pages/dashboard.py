"""Página: Dashboard principal."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import components, repository
from src.config import FIXED_EXPENSE_CATEGORIES, ConfigKeys
from src.finance import (
    compute_wealth, daily_flow, expenses_by_category,
)
from src.format import brl
from src.sidebar import ALL_MONTHS


def render(*, df_transactions: pd.DataFrame, df_credit_card: pd.DataFrame,
           df_transactions_period: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           df_fixed_costs: pd.DataFrame,
           selected_month: str) -> None:
    period_label = (f"({selected_month})" if selected_month != ALL_MONTHS
                    else "(Todo o Período)")
    components.page_header(
        f"📊 Resumo {period_label}",
        "Visão consolidada do seu mês e do patrimônio acumulado.",
    )

    wealth = compute_wealth(df_transactions, df_transactions_period)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Receitas do Período", brl(wealth.total_income))
    c2.metric("Despesas do Período", brl(wealth.total_expense))
    c3.metric("Saldo Bancário Total", brl(wealth.bank_balance))
    c4.metric("Patrimônio Total 💎", brl(wealth.net_worth))

    st.divider()

    _projection_section(
        df_credit_card=df_credit_card,
        df_fixed_costs=df_fixed_costs,
        selected_month=selected_month,
    )

    st.divider()
    st.subheader("📉 Análise Gráfica do Período")

    df_daily, df_cumulative = daily_flow(df_transactions_period)
    col1, col2 = st.columns([1, 1.2])
    with col1:
        st.markdown("**Despesas variáveis (rosca)**")
        df_pie = expenses_by_category(
            df_transactions_period, df_credit_card_period,
            exclude=FIXED_EXPENSE_CATEGORIES,
        )
        components.donut_by_category(
            df_pie, empty_msg="Nenhuma despesa variável neste período.",
        )
    with col2:
        st.markdown("**Evolução diária de entradas e saídas**")
        components.line_income_vs_expense(df_daily)

    st.markdown("**🌊 Volume acumulado: receitas × despesas**")
    components.area_cumulative(df_cumulative)

    st.markdown("**🍩 Despesas por categoria (banco + cartão)**")
    df_total = expenses_by_category(df_transactions_period, df_credit_card_period)
    components.horizontal_bar_expenses(df_total)


def _projection_section(*, df_credit_card: pd.DataFrame,
                        df_fixed_costs: pd.DataFrame,
                        selected_month: str) -> None:
    st.subheader("🔮 Visão do Próximo Mês")

    if selected_month != ALL_MONTHS:
        anchor = pd.to_datetime(selected_month, format="%m/%Y")
    else:
        anchor = pd.Timestamp(date.today())

    current_str = anchor.strftime("%m/%Y")
    next_str = (anchor + pd.DateOffset(months=1)).strftime("%m/%Y")

    expected_income = repository.load_config(ConfigKeys.RECEITA_PREVISTA, 0.0)
    fixed_total = float(df_fixed_costs["Valor"].sum()) if not df_fixed_costs.empty else 0.0

    if df_credit_card.empty:
        invoice_total = 0.0
    else:
        mask = (df_credit_card["Mês da Fatura"] == current_str) & \
               (df_credit_card["Status"] == "Pendente")
        invoice_total = float(df_credit_card.loc[mask, "Valor"].sum())

    projected = expected_income - fixed_total - invoice_total
    st.caption(
        f"Projeção para **{next_str}** abatendo a fatura pendente de **{current_str}**."
    )

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Receita Prevista (+)", brl(expected_income))
    p2.metric("Custos Fixos (−)", brl(fixed_total))
    p3.metric("Fatura do Cartão (−)", brl(invoice_total))
    label = "💰 Saldo Livre" if projected >= 0 else "⚠️ Saldo Livre"
    p4.metric(label, brl(projected))
