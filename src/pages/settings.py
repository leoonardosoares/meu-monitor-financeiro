"""Página: Configurações e Orçamento."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import components, repository
from src.config import ConfigKeys
from src.format import brl
from src.sidebar import ALL_MONTHS


def render(*, df_categories: pd.DataFrame, df_budgets: pd.DataFrame,
           df_fixed_costs: pd.DataFrame,
           df_transactions_period: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           categories: list[str],
           selected_month: str) -> None:
    components.page_header(
        "Configurações e Orçamento",
        "Personalize categorias, orçamentos, regras do cartão e custos fixos.",
    )

    tabs = st.tabs([
        "Categorias", "Orçamento", "Regras do Cartão", "Custos Fixos",
    ])

    with tabs[0]:
        _categories_tab(df_categories)
    with tabs[1]:
        _budgets_tab(
            df_budgets=df_budgets,
            df_transactions_period=df_transactions_period,
            df_credit_card_period=df_credit_card_period,
            selected_month=selected_month,
        )
    with tabs[2]:
        _card_rules_tab()
    with tabs[3]:
        _fixed_costs_tab(df_fixed_costs, categories=categories)


def _categories_tab(df_categories: pd.DataFrame) -> None:
    st.subheader("Minhas categorias")
    st.caption("Adicione, edite ou apague categorias e clique em salvar.")
    with st.form("edit_categories"):
        edited = st.data_editor(
            df_categories, num_rows="dynamic", use_container_width=True,
            hide_index=True,
        )
        if st.form_submit_button("💾 Salvar categorias"):
            if not df_categories.equals(edited):
                repository.save_categories(edited)
                st.success("Categorias atualizadas.")
                st.rerun()


def _budgets_tab(*, df_budgets: pd.DataFrame,
                 df_transactions_period: pd.DataFrame,
                 df_credit_card_period: pd.DataFrame,
                 selected_month: str) -> None:
    st.subheader("Teto de gastos por categoria")
    st.caption("Defina um limite mensal. Use `0` para categorias sem limite.")

    left, right = st.columns([1, 1.5])

    with left:
        with st.form("edit_budgets"):
            edited = st.data_editor(
                df_budgets, num_rows="dynamic", use_container_width=True,
                hide_index=True,
            )
            if st.form_submit_button("💾 Salvar orçamentos"):
                if not df_budgets.equals(edited):
                    repository.save_budgets(edited)
                    st.success("Orçamentos salvos.")
                    st.rerun()

    with right:
        if selected_month == ALL_MONTHS:
            st.info("Selecione um mês na sidebar para ver o progresso do orçamento.")
            return
        st.subheader(f"Progresso em {selected_month}")
        _render_budget_progress(
            df_budgets=df_budgets,
            df_transactions_period=df_transactions_period,
            df_credit_card_period=df_credit_card_period,
        )


def _render_budget_progress(*, df_budgets: pd.DataFrame,
                             df_transactions_period: pd.DataFrame,
                             df_credit_card_period: pd.DataFrame) -> None:
    bank_expenses = df_transactions_period[
        (df_transactions_period["Tipo"] == "Saída") &
        (df_transactions_period["Categoria"] != "Cartão de Crédito")
    ]
    bank_grouped = bank_expenses.groupby("Categoria")["Valor"].sum()
    card_grouped = (
        df_credit_card_period.groupby("Categoria")["Valor"].sum()
        if not df_credit_card_period.empty else pd.Series(dtype=float)
    )

    has_valid_budget = False
    for _, row in df_budgets.iterrows():
        category = row["Categoria"]
        limit = float(row["Limite"]) if pd.notna(row["Limite"]) else 0.0
        if limit <= 0:
            continue
        has_valid_budget = True

        spent = float(bank_grouped.get(category, 0.0)) + \
                float(card_grouped.get(category, 0.0))
        ratio = spent / limit
        line = f"**{category}**: {brl(spent)} / {brl(limit)}"

        if ratio >= 1.0:
            st.error(f"🚨 {line} (estourou)")
            st.progress(1.0)
        elif ratio >= 0.8:
            st.warning(f"⚠️ {line} (quase lá)")
            st.progress(ratio)
        else:
            st.success(f"{line} (tranquilo)")
            st.progress(ratio)

    if not has_valid_budget:
        st.write("Adicione categorias e limites maiores que zero ao lado.")


def _card_rules_tab() -> None:
    st.subheader("Datas importantes do cartão")
    st.caption("Definem em qual mês cada compra entra.")

    closing = int(repository.load_config(ConfigKeys.DIA_FECHAMENTO, 8))
    due = int(repository.load_config(ConfigKeys.DIA_VENCIMENTO, 15))

    c1, c2 = st.columns(2)
    new_closing = c1.number_input(
        "Dia de fechamento (melhor dia de compra):",
        min_value=1, max_value=31, value=closing, step=1,
    )
    new_due = c2.number_input(
        "Dia de vencimento da fatura:",
        min_value=1, max_value=31, value=due, step=1,
    )

    if new_closing != closing:
        repository.save_config(ConfigKeys.DIA_FECHAMENTO, new_closing)
        st.success("Dia de fechamento atualizado.")
        st.rerun()
    if new_due != due:
        repository.save_config(ConfigKeys.DIA_VENCIMENTO, new_due)
        st.success("Dia de vencimento atualizado.")
        st.rerun()


def _fixed_costs_tab(df_fixed_costs: pd.DataFrame, *,
                      categories: list[str]) -> None:
    st.subheader("Receita base mensal")
    current = repository.load_config(ConfigKeys.RECEITA_PREVISTA, 0.0)
    new_income = st.number_input(
        "Salário / receita fixa esperada (R$):",
        min_value=0.0, value=current, step=100.0,
    )
    if new_income != current:
        repository.save_config(ConfigKeys.RECEITA_PREVISTA, new_income)
        st.success("Receita prevista atualizada.")
        st.rerun()

    st.divider()
    st.subheader("Custos fixos mensais")
    st.caption(
        "Cadastre suas despesas recorrentes. Depois use o botão "
        "**Gerar lançamentos do mês** para criar todas as transações de uma vez."
    )

    with st.form("edit_fixed_costs"):
        edited = st.data_editor(
            df_fixed_costs, num_rows="dynamic", use_container_width=True,
            hide_index=True,
            column_config={
                "Categoria": st.column_config.SelectboxColumn(
                    "Categoria", options=categories, required=False,
                ),
                "Valor": st.column_config.NumberColumn(
                    "Valor", format="%.2f", min_value=0.0,
                ),
            },
        )
        if st.form_submit_button("💾 Salvar custos fixos"):
            if not df_fixed_costs.equals(edited):
                try:
                    repository.save_fixed_costs(edited)
                    st.success("Custos fixos salvos.")
                    st.rerun()
                except Exception as exc:
                    st.error("🚨 O Google recusou a gravação. Detalhes abaixo:")
                    if hasattr(exc, "response"):
                        st.code(exc.response.text)
                    else:
                        st.error(str(exc))

    st.divider()
    _generate_fixed_costs_section(df_fixed_costs)


def _generate_fixed_costs_section(df_fixed_costs: pd.DataFrame) -> None:
    st.subheader("Gerar lançamentos automáticos do mês")
    st.caption(
        "Cria uma transação de Saída em cada custo fixo cadastrado. "
        "Útil pra automatizar aluguel, condomínio, assinaturas, etc."
    )

    valid_costs = df_fixed_costs[
        (df_fixed_costs["Valor"].fillna(0) > 0) &
        (df_fixed_costs["Descrição"].fillna("").astype(str).str.strip() != "")
    ]
    if valid_costs.empty:
        st.info("Cadastre custos fixos acima primeiro.")
        return

    c1, c2 = st.columns([1, 2])
    lancamento_data = c1.date_input(
        "Data dos lançamentos", value=date.today(), format="DD/MM/YYYY",
    )
    total = float(valid_costs["Valor"].sum())
    c2.metric(
        f"Total a lançar ({len(valid_costs)} itens)", brl(total),
    )

    with st.expander("Pré-visualizar lançamentos"):
        preview = valid_costs.copy()
        preview["Valor (R$)"] = preview["Valor"].apply(brl)
        st.dataframe(
            preview[["Descrição", "Categoria", "Valor (R$)"]],
            use_container_width=True, hide_index=True,
        )

    if st.button("🚀 Gerar lançamentos agora", type="primary"):
        df_current = repository.load_transactions().drop(
            columns=["Data_DT", "Mes_Ano"], errors="ignore",
        )
        new_rows = []
        for _, row in valid_costs.iterrows():
            new_rows.append({
                "Data": lancamento_data,
                "Descrição": str(row["Descrição"]).strip(),
                "Categoria": row.get("Categoria") or "Outros",
                "Valor": float(row["Valor"]),
                "Tipo": "Saída",
            })
        merged = pd.concat(
            [df_current, pd.DataFrame(new_rows)], ignore_index=True,
        )
        repository.save_transactions(merged)
        st.success(f"{len(new_rows)} lançamentos criados em {lancamento_data:%d/%m/%Y}.")
        st.rerun()
