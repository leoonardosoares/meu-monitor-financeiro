"""Página: Cartão de Crédito."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import components, credit_card, repository
from src.config import Colors, ConfigKeys
from src.format import brl
from src.sidebar import ALL_MONTHS


def render(*, df_credit_card: pd.DataFrame, df_credit_card_period: pd.DataFrame,
           categories: list[str], selected_month: str) -> None:
    components.page_header(
        "💳 Cartão de Crédito",
        "Acompanhe parcelas, faturas e limite disponível.",
    )

    closing_day = int(repository.load_config(ConfigKeys.DIA_FECHAMENTO, 8))
    due_day = int(repository.load_config(ConfigKeys.DIA_VENCIMENTO, 15))

    _limit_section(df_credit_card)
    st.divider()

    _pay_invoice_section(df_credit_card)
    st.divider()

    _upcoming_invoices_section(df_credit_card, closing_day, due_day)
    st.divider()

    _chart_and_form(
        df_credit_card=df_credit_card,
        df_credit_card_period=df_credit_card_period,
        categories=categories,
        selected_month=selected_month,
        closing_day=closing_day,
    )

    st.divider()
    _editor_section(df_credit_card)


# ---------------------------------------------------------------------------

def _limit_section(df_credit_card: pd.DataFrame) -> None:
    current_limit = repository.load_config(ConfigKeys.LIMITE_CARTAO, 2000.0)
    left, right = st.columns([1, 2])
    new_limit = left.number_input(
        "Limite total (R$):", min_value=0.0, value=current_limit, step=100.0,
    )
    if new_limit != current_limit:
        repository.save_config(ConfigKeys.LIMITE_CARTAO, new_limit)

    pending = credit_card.pending_total(df_credit_card)
    right.metric("Limite Disponível", brl(new_limit - pending))


def _pay_invoice_section(df_credit_card: pd.DataFrame) -> None:
    st.subheader("💲 Pagar Fatura")
    pending_months = credit_card.pending_invoices(df_credit_card)

    if not pending_months:
        st.success("🎉 Nenhuma fatura pendente.")
        return

    c1, c2, c3 = st.columns([2, 2, 2])
    selected = c1.selectbox("Selecione a fatura:", pending_months)
    mask = (df_credit_card["Mês da Fatura"] == selected) & \
           (df_credit_card["Status"] == "Pendente")
    total = float(df_credit_card.loc[mask, "Valor"].sum())
    c2.metric("Valor a pagar", brl(total))

    c3.write("")
    c3.write("")
    if c3.button("✅ Confirmar pagamento"):
        new_df, paid = credit_card.pay_invoice(df_credit_card, selected)
        repository.save_credit_card(new_df)
        repository.append_transaction({
            "Data": date.today(),
            "Descrição": f"Fatura ({selected})",
            "Categoria": "Cartão de Crédito",
            "Valor": paid,
            "Tipo": "Saída",
        })
        st.success(f"Fatura paga: {brl(paid)}.")
        st.rerun()


def _upcoming_invoices_section(df_credit_card: pd.DataFrame,
                                closing_day: int, due_day: int) -> None:
    st.subheader("🗓️ Próximas faturas")
    today = pd.Timestamp(date.today())
    upcoming = credit_card.upcoming_invoices(
        df_credit_card, today=today, closing_day=closing_day, months=6,
    )
    columns = st.columns(6)
    for i, (month, total) in enumerate(upcoming):
        suffix = ""
        if i == 0:
            suffix = f" ({credit_card.invoice_phase(today, closing_day, due_day)})"
        columns[i].metric(f"Fatura {month}{suffix}", brl(total))


def _chart_and_form(*, df_credit_card: pd.DataFrame,
                     df_credit_card_period: pd.DataFrame,
                     categories: list[str], selected_month: str,
                     closing_day: int) -> None:
    left, right = st.columns([1, 1])

    with left:
        period_label = f" ({selected_month})" if selected_month != ALL_MONTHS else ""
        st.subheader(f"📊 Gastos por categoria{period_label}")
        if df_credit_card_period.empty:
            st.info("Nenhuma compra de cartão neste período.")
        else:
            grouped = (
                df_credit_card_period.groupby("Categoria")["Valor"].sum().reset_index()
            )
            components.vertical_bar(
                grouped, x="Categoria", y="Valor", color=Colors.INVESTMENT,
            )

    with right:
        st.subheader("🛒 Lançar compra")
        with st.form("new_card_purchase", clear_on_submit=True):
            purchase_date = st.date_input("Data da compra", format="DD/MM/YYYY")
            description = st.text_input("Descrição")
            category = st.selectbox("Categoria", categories)
            c4, c5 = st.columns(2)
            total_amount = c4.number_input("Valor total (R$)", min_value=0.01, format="%.2f")
            installments = c5.number_input(
                "Parcelas", min_value=1, max_value=48, value=1, step=1,
            )
            if st.form_submit_button("Lançar"):
                rows = credit_card.installments_for_purchase(
                    purchase_date=purchase_date,
                    description=description,
                    category=category,
                    total_amount=total_amount,
                    installments=int(installments),
                    closing_day=closing_day,
                )
                new_df = pd.concat(
                    [df_credit_card, pd.DataFrame(rows)], ignore_index=True,
                )
                repository.save_credit_card(new_df)
                first_invoice = rows[0]["Mês da Fatura"]
                st.success(f"Compra lançada — primeira parcela em {first_invoice}.")
                st.rerun()


def _editor_section(df_credit_card: pd.DataFrame) -> None:
    st.subheader("🧾 Extrato completo do cartão")
    st.caption("Edite as linhas livremente e clique em salvar.")
    with st.form("edit_credit_card"):
        edited = st.data_editor(
            df_credit_card, num_rows="dynamic", use_container_width=True,
        )
        if st.form_submit_button("💾 Salvar alterações"):
            if not df_credit_card.equals(edited):
                repository.save_credit_card(edited)
                st.success("Extrato salvo.")
                st.rerun()
            else:
                st.info("Nada a salvar — sem alterações.")
