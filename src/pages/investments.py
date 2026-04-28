"""Página: Investimentos (reserva, aportes/saques, simulador)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import components, repository
from src.config import Colors, ConfigKeys
from src.finance import compute_wealth
from src.format import brl


def render(*, df_transactions: pd.DataFrame) -> None:
    components.page_header(
        "📈 Meus Investimentos",
        "Reserva de emergência, aportes/saques e simulador de juros compostos.",
    )

    tab_goals, tab_simulator = st.tabs(["🎯 Metas e Aportes", "🔮 Simulador"])

    wealth = compute_wealth(df_transactions, df_transactions)
    invested = wealth.invested

    with tab_goals:
        _goals_tab(df_transactions=df_transactions, invested=invested)

    with tab_simulator:
        _simulator_tab(invested=invested)


def _goals_tab(*, df_transactions: pd.DataFrame, invested: float) -> None:
    st.subheader("Reserva de Emergência")
    current_goal = repository.load_config(ConfigKeys.META_RESERVA, 10000.0)
    new_goal = st.number_input(
        "Meta da reserva (R$):", min_value=100.0, value=current_goal, step=500.0,
    )
    if new_goal != current_goal:
        repository.save_config(ConfigKeys.META_RESERVA, new_goal)

    reserve = min(invested, new_goal)
    extra = max(invested - new_goal, 0.0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total investido", brl(invested))
    c2.metric("Fundo de emergência", brl(reserve))
    c3.metric("Outros investimentos", brl(extra))

    progress = min(reserve / new_goal, 1.0) if new_goal > 0 else 0.0
    st.write(f"**Progresso da reserva ({progress * 100:.1f}%)**")
    st.progress(progress)
    if progress >= 1.0:
        st.success("Reserva completa. Novos aportes vão para 'Outros investimentos'.")

    st.divider()
    st.subheader("💸 Movimentar")

    col_in, col_out = st.columns(2)
    with col_in:
        with st.form("invest_deposit", clear_on_submit=True):
            st.markdown("**🟢 Novo aporte**")
            d = st.date_input("Data", format="DD/MM/YYYY", key="dep_date")
            v = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", key="dep_v")
            if st.form_submit_button("Investir"):
                repository.append_transaction({
                    "Data": d, "Descrição": "Aporte de Investimento",
                    "Categoria": "Investimento", "Valor": v, "Tipo": "Saída",
                })
                st.success("Aporte registrado!")
                st.rerun()

    with col_out:
        with st.form("invest_withdraw", clear_on_submit=True):
            st.markdown("**🏧 Resgate / saque**")
            d = st.date_input("Data", format="DD/MM/YYYY", key="wd_date")
            v = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", key="wd_v")
            if st.form_submit_button("Sacar"):
                if v > invested:
                    st.error("Saldo insuficiente nos investimentos.")
                else:
                    repository.append_transaction({
                        "Data": d, "Descrição": "Resgate de Investimento",
                        "Categoria": "Investimento", "Valor": v, "Tipo": "Entrada",
                    })
                    st.success("Saque realizado.")
                    st.rerun()


def _simulator_tab(*, invested: float) -> None:
    st.subheader("Mágica dos juros compostos")

    c1, c2 = st.columns(2)
    years = c1.slider("Tempo (anos):", min_value=1, max_value=30, value=5)
    monthly_contribution = c2.number_input(
        "Aporte mensal (R$):", min_value=0.0, value=0.0, step=50.0,
        help="Quanto você pretende investir todo mês durante o período.",
    )

    c3, c4 = st.columns(2)
    annual_rate = c3.number_input(
        "Taxa anual bruta estimada (%):",
        min_value=0.0, value=10.0, step=0.5,
        help="Rendimento anual antes de descontar imposto.",
    )
    apply_ir = c4.checkbox(
        "Descontar IR de 15% (renda fixa, +720 dias)",
        value=True,
        help="IR regressivo da Renda Fixa: 15% sobre o ganho para resgates "
             "após 720 dias. Para LCI/LCA isentas, desmarque.",
    )

    if invested <= 0 and monthly_contribution <= 0:
        st.warning(
            "Faça seu primeiro aporte ou defina um aporte mensal para simular."
        )
        return

    # Converte taxa anual em mensal equivalente (juros compostos).
    monthly_rate = (1 + annual_rate / 100) ** (1 / 12) - 1

    rows = []
    balance = invested
    invested_total = invested
    for year in range(1, years + 1):
        for _ in range(12):
            # Rendimento aplicado primeiro, aporte ao fim do mês.
            balance = balance * (1 + monthly_rate) + monthly_contribution
            invested_total += monthly_contribution

        gross_gain = max(balance - invested_total, 0.0)
        ir = gross_gain * 0.15 if apply_ir else 0.0
        net_balance = balance - ir

        rows.append({
            "Ano": str(year),
            "Total Investido (R$)": invested_total,
            "Patrimônio Bruto (R$)": balance,
            "IR (R$)": ir,
            "Patrimônio Líquido (R$)": net_balance,
        })

    df_proj = pd.DataFrame(rows)
    final = df_proj.iloc[-1]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total investido", brl(final["Total Investido (R$)"]))
    m2.metric("Patrimônio bruto", brl(final["Patrimônio Bruto (R$)"]))
    m3.metric("IR estimado", brl(final["IR (R$)"]))
    m4.metric("Patrimônio líquido 💎", brl(final["Patrimônio Líquido (R$)"]))

    components.vertical_bar(
        df_proj, x="Ano", y="Patrimônio Líquido (R$)", color=Colors.PRIMARY,
    )
