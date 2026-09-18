"""Página: Dashboard principal."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import components, credit_card as cc, insights, repository
from src.config import ConfigKeys
from src.finance import (
    avg_monthly_expense, budget_status, compute_wealth, expenses_by_category,
    financial_independence_months, fixed_costs_split,
    monthly_investment_contributions, monthly_summary, pct_change,
    previous_month, projection_target, savings_rate, spending_velocity,
)
from src.format import brl
from src.sidebar import ALL_MONTHS


def render(*, df_transactions: pd.DataFrame, df_credit_card: pd.DataFrame,
           df_transactions_period: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           df_fixed_costs: pd.DataFrame,
           df_budgets: pd.DataFrame,
           df_cards: pd.DataFrame,
           df_card_payments: pd.DataFrame,
           selected_month: str) -> None:
    period_label = (f"({selected_month})" if selected_month != ALL_MONTHS
                    else "(todo o período)")
    components.page_header(
        f"Resumo {period_label}",
        "Visão consolidada do mês, comparação com o mês anterior e "
        "projeção do próximo período.",
    )

    # ── Insights automáticos ────────────────────────────────────────────────
    auto_insights = insights.generate(
        df_transactions=df_transactions,
        df_credit_card=df_credit_card,
        df_budgets=df_budgets,
        selected_month=selected_month,
    )
    if auto_insights:
        components.insight_chips(auto_insights)
        st.write("")

    # ── Velocidade de gasto (só se o mês corrente está selecionado) ────────
    _spending_velocity_section(df_transactions_period, df_budgets)

    # ── KPIs principais com delta MoM ──────────────────────────────────────
    _kpi_section(df_transactions, df_transactions_period, selected_month)

    # ── Indicadores de saúde financeira ────────────────────────────────────
    _health_section(df_transactions, df_transactions_period)

    st.divider()

    # ── Visão anual: últimos 12 meses ──────────────────────────────────────
    st.subheader("Visão anual (últimos 12 meses)")
    df_annual = monthly_summary(df_transactions, months=12)
    components.annual_bars(df_annual)

    st.divider()

    # ── Projeção próximo mês ───────────────────────────────────────────────
    _projection_section(
        df_credit_card=df_credit_card,
        df_card_payments=df_card_payments,
        df_cards=df_cards,
        df_fixed_costs=df_fixed_costs,
        df_transactions=df_transactions,
        selected_month=selected_month,
    )

    st.divider()

    # ── Status do orçamento por categoria ──────────────────────────────────
    st.subheader("Status do orçamento")
    period_label = (
        selected_month if selected_month != ALL_MONTHS else "todo o período"
    )
    st.caption(
        f"Quanto cada categoria já consumiu do limite definido em "
        f"Configurações ({period_label}). A linha tracejada marca os 100%."
    )
    df_budget_status = budget_status(
        df_budgets, df_transactions_period, df_credit_card_period,
    )
    components.budget_overview(df_budget_status)

    st.divider()

    # ── Aportes mensais em investimento (12 meses) ─────────────────────────
    st.subheader("Aportes em investimento")
    st.caption(
        "Quanto entrou na sua conta de investimento por mês nos últimos 12 meses."
    )
    df_contrib = monthly_investment_contributions(df_transactions, months=12)
    components.monthly_contributions_bars(df_contrib)

    st.divider()

    # ── Despesas por categoria (banco + cartão) ────────────────────────────
    st.subheader("Despesas por categoria")
    st.caption("Soma das saídas do banco com o cartão, agrupadas por categoria.")
    df_total = expenses_by_category(df_transactions_period, df_credit_card_period)
    components.horizontal_bar_expenses(df_total)


# ---------------------------------------------------------------------------
# Seções internas
# ---------------------------------------------------------------------------

def _spending_velocity_section(df_period: pd.DataFrame, df_budgets: pd.DataFrame) -> None:
    velocity = spending_velocity(df_period)
    if velocity is None:
        return
    days_remaining = max(velocity.days_in_month - velocity.days_passed, 0)
    total_budget = float(df_budgets["Limite"].fillna(0).sum()) if not df_budgets.empty else 0.0
    over_budget = velocity.projected_month_end - total_budget if total_budget > 0 else None

    with st.container(border=True):
        cols = st.columns([3, 2, 2])
        with cols[0]:
            st.markdown("**⏱️ Ritmo do mês**")
            st.caption(
                f"{velocity.days_passed} de {velocity.days_in_month} dias passados — "
                f"restam {days_remaining} dias."
            )
        cols[1].metric("Gasto até hoje", brl(velocity.spent_so_far),
                       delta=f"{brl(velocity.daily_avg)}/dia",
                       delta_color="off")
        if over_budget is not None and over_budget > 0:
            cols[2].metric("Projeção de fim do mês",
                           brl(velocity.projected_month_end),
                           delta=f"+{brl(over_budget)} acima do orçamento",
                           delta_color="inverse")
        else:
            cols[2].metric("Projeção de fim do mês",
                           brl(velocity.projected_month_end))


def _kpi_section(df_all: pd.DataFrame, df_period: pd.DataFrame,
                  selected_month: str) -> None:
    wealth_current = compute_wealth(df_all, df_period)

    # Comparação com mês anterior (só se um mês específico está selecionado)
    if selected_month != ALL_MONTHS:
        prev = previous_month(selected_month)
        df_prev = df_all[df_all["Mes_Ano"] == prev]
        wealth_prev = compute_wealth(df_all, df_prev)
        prev_income = wealth_prev.total_income
        prev_expense = wealth_prev.total_expense
    else:
        prev_income = None
        prev_expense = None

    c1, c2, c3, c4 = st.columns(4)
    components.metric_with_delta(
        c1, label="Receitas do período",
        value=wealth_current.total_income, previous=prev_income,
        higher_is_better=True,
    )
    components.metric_with_delta(
        c2, label="Despesas do período",
        value=wealth_current.total_expense, previous=prev_expense,
        higher_is_better=False,
    )
    c3.metric("Saldo bancário", brl(wealth_current.bank_balance))
    c4.metric("Patrimônio total 💎", brl(wealth_current.net_worth))


def _health_section(df_all: pd.DataFrame, df_period: pd.DataFrame) -> None:
    # compute_wealth já exclui transferências (aportes/saques de
    # investimento) de total_income/total_expense — reusar aqui garante
    # que todos os KPIs do dashboard contem a mesma história.
    wealth_period = compute_wealth(df_all, df_period)
    income = wealth_period.total_income
    expense = wealth_period.total_expense
    rate = savings_rate(income, expense)

    avg_expense = avg_monthly_expense(df_all, months=6)
    # Reserva de emergência: aportes na meta da reserva, limitado pela meta
    reserve_goal = repository.load_config(ConfigKeys.META_RESERVA, 10000.0)
    reserve_value = min(wealth_period.invested, reserve_goal)
    fi_months = financial_independence_months(reserve_value, avg_expense)

    # Comprometimento da renda (despesas / receitas globais, sem transferências)
    wealth_global = compute_wealth(df_all, df_all)
    commitment = (
        wealth_global.total_expense / wealth_global.total_income * 100
        if wealth_global.total_income > 0 else 0.0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Taxa de poupança",
        f"{rate:.0f}%",
        delta=("Ideal ≥ 20%" if rate >= 20 else
               ("Abaixo do ideal" if rate >= 0 else "Déficit")),
        delta_color="normal" if rate >= 20 else "inverse",
    )
    c2.metric(
        "Independência financeira",
        f"{fi_months:.1f} meses" if avg_expense > 0 else "—",
        delta="Quanto sua reserva cobre",
        delta_color="off",
        help="Reserva atual ÷ despesa mensal média (últimos 6 meses).",
    )
    c3.metric(
        "Fluxo líquido do período",
        brl(float(income) - float(expense)),
        delta=("Sobrou" if float(income) >= float(expense) else "Faltou"),
        delta_color="normal" if float(income) >= float(expense) else "inverse",
    )
    c4.metric(
        "Comprometimento da renda",
        f"{commitment:.0f}%",
        delta="< 50% recomendado",
        delta_color="normal" if commitment < 50 else "inverse",
    )


def _projection_section(*, df_credit_card: pd.DataFrame,
                        df_card_payments: pd.DataFrame,
                        df_cards: pd.DataFrame,
                        df_fixed_costs: pd.DataFrame,
                        df_transactions: pd.DataFrame,
                        selected_month: str) -> None:
    st.subheader("Visão do próximo mês")

    hoje = date.today()
    alvo, veio_do_filtro = projection_target(selected_month, today=hoje)

    agendadas, ilegiveis = cc.schedule_invoices(
        df_credit_card, df_card_payments, df_cards, today=hoje,
    )
    do_mes = cc.invoices_due_in(agendadas, alvo)
    atrasadas = cc.overdue_invoices(agendadas)

    invoice_total = sum(i.balance for i in do_mes)
    expected_income = repository.load_config(ConfigKeys.RECEITA_PREVISTA, 0.0)
    fixed_total, fixed_card = fixed_costs_split(df_fixed_costs, bool(do_mes))
    projected = expected_income - fixed_total - invoice_total

    if veio_do_filtro:
        st.caption(f"Projeção para **{alvo}**, o mês escolhido no filtro.")
    else:
        st.caption(
            f"Projeção para **{alvo}**. Esta seção não segue o filtro da "
            "sidebar — ela sempre olha para frente."
        )

    _projection_warnings(atrasadas, agendadas, ilegiveis)

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Receita prevista (+)", brl(expected_income))
    p2.metric("Custos fixos (−)", brl(fixed_total))
    abertas = [i for i in do_mes if not i.closed]
    p3.metric(
        f"Faturas que vencem em {alvo} (−)", brl(invoice_total),
        delta=(f"mínimo — {len(abertas)} ainda não fechou(aram)"
               if abertas else "valor já fechado"),
        delta_color="off",
    )
    label = "Saldo livre" if projected >= 0 else "Saldo livre (negativo)"
    p4.metric(label, brl(projected),
              delta_color="normal" if projected >= 0 else "inverse")

    _projection_footnotes(
        df_transactions=df_transactions, projected=projected,
        fixed_card=fixed_card, do_mes=do_mes, alvo=alvo,
    )


def _projection_warnings(atrasadas: list, agendadas: list,
                         ilegiveis: list[str]) -> None:
    if atrasadas:
        linhas = " · ".join(
            f"{i.card} {i.month} ({brl(i.balance)}, venceu {i.due:%d/%m})"
            for i in atrasadas
        )
        st.warning(
            f"⚠️ **{brl(sum(i.balance for i in atrasadas))} em fatura "
            f"vencida e não paga** — {linhas}. Esse valor é dívida "
            "acumulada, não despesa do mês, então fica **fora** da conta "
            "abaixo. Dê baixa na aba Cartão de Crédito."
        )

    estimados = sorted({i.card for i in agendadas if i.estimated})
    if estimados:
        st.warning(
            "⚠️ Sem dia de fechamento e vencimento cadastrados em **"
            + "**, **".join(estimados)
            + "**, o app chuta fecha dia 8 / vence dia 15 — o que pode jogar "
            "a fatura para o mês errado. Cadastre em Cartão de Crédito → "
            "Meus cartões."
        )

    if ilegiveis:
        st.warning(
            f"⚠️ {len(ilegiveis)} fatura(s) com mês ilegível ficaram de fora "
            f"da conta: {', '.join(ilegiveis)}. Corrija o campo "
            "**Mês da Fatura** no extrato — o formato é MM/AAAA."
        )


def _projection_footnotes(*, df_transactions: pd.DataFrame, projected: float,
                          fixed_card: float, do_mes: list, alvo: str) -> None:
    variavel = avg_monthly_expense(df_transactions, months=6)
    if variavel > 0:
        st.caption(
            f"O saldo livre conta apenas receita, custos fixos e faturas. "
            f"Seu gasto variável no banco tem média de **{brl(variavel)}/mês** "
            f"nos últimos 6 meses; descontando isso, sobrariam "
            f"**{brl(projected - variavel)}**."
        )
    if fixed_card > 0:
        st.caption(
            f"{brl(fixed_card)} de custos fixos na categoria *Cartão de "
            "Crédito* foram excluídos para não descontar a fatura duas vezes."
        )

    if not do_mes:
        st.caption(f"Nenhuma fatura vence em {alvo}.")
        return

    with st.expander("Como cheguei nesse número"):
        st.dataframe(pd.DataFrame([{
            "Cartão": i.card,
            "Fatura": i.month,
            "Fecha": f"{i.closing:%d/%m/%Y}",
            "Vence": f"{i.due:%d/%m/%Y}",
            "Total": brl(i.total),
            "Já quitado": brl(i.settled),
            "Já adiantado": brl(i.advances),
            "Falta pagar": brl(i.balance),
        } for i in do_mes]), hide_index=True, use_container_width=True)
        abertas = [i for i in do_mes if not i.closed]
        if abertas:
            dias = min((i.closing.date() - date.today()).days for i in abertas)
            st.caption(
                f"É um piso: {len(abertas)} fatura(s) ainda não fecharam — a "
                f"primeira fecha em {dias} dia(s), e tudo que for comprado até "
                "lá entra nesse valor."
            )
        st.caption(
            f"Aqui só entra o que vence em {alvo}. O **Em aberto** da página "
            "Cartão de Crédito soma todas as faturas abertas, inclusive "
            "parcelas de meses futuros — por isso os dois números diferem."
        )
