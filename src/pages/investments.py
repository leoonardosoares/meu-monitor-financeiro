"""Página: Investimentos (reserva, aportes/saques, posição atual, simulador)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import components, repository
from src.config import Colors, ConfigKeys
from src.finance import compute_wealth
from src.format import brl


def render(*, df_transactions: pd.DataFrame) -> None:
    components.page_header(
        "📈 Meus Investimentos",
        "Reserva de emergência, aportes/saques, rendimento real e simulador.",
    )

    tab_goals, tab_position, tab_simulator = st.tabs([
        "🎯 Metas e Aportes",
        "💎 Posição Atual",
        "🔮 Simulador",
    ])

    wealth = compute_wealth(df_transactions, df_transactions)
    invested = wealth.invested

    with tab_goals:
        _goals_tab(df_transactions=df_transactions, invested=invested)

    with tab_position:
        _position_tab(invested=invested)

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


def _position_tab(*, invested: float) -> None:
    st.subheader("Rendimento real dos investimentos")
    st.caption(
        "Atualize aqui o saldo bruto que está hoje na sua corretora ou banco. "
        "O app compara com o total que você aportou e mostra quanto rendeu."
    )

    with st.form("new_position", clear_on_submit=True):
        c1, c2 = st.columns(2)
        position_date = c1.date_input(
            "Data da posição", value=date.today(), format="DD/MM/YYYY",
        )
        position_value = c2.number_input(
            "Valor atual (R$)", min_value=0.0, format="%.2f",
            help="Soma de todos os seus investimentos hoje, do jeito que "
                 "aparece no extrato da corretora/banco.",
        )
        if st.form_submit_button("💾 Registrar posição"):
            repository.append_investment_position({
                "Data": position_date,
                "Valor": position_value,
            })
            st.success("Posição registrada!")
            st.rerun()

    df_positions = repository.load_investment_positions()
    if df_positions.empty:
        st.info(
            "Registre sua primeira posição para começar a acompanhar o rendimento."
        )
        return

    df_sorted = df_positions.dropna(subset=["Data_DT"]).sort_values("Data_DT")
    if df_sorted.empty:
        st.warning("Datas inválidas no histórico — verifique a tabela abaixo.")
    else:
        latest = df_sorted.iloc[-1]
        current_value = float(latest["Valor"])
        latest_date = latest["Data_DT"].strftime("%d/%m/%Y")
        returns = current_value - invested
        returns_pct = (returns / invested * 100) if invested > 0 else 0.0
        delta_color = "normal" if returns >= 0 else "inverse"

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total aportado", brl(invested))
        c2.metric(f"Valor atual ({latest_date})", brl(current_value))
        c3.metric(
            "Rendimento (R$)", brl(returns),
            delta=brl(returns), delta_color=delta_color,
        )
        if invested > 0:
            c4.metric(
                "Rendimento (%)", f"{returns_pct:.2f}%",
                delta=f"{returns_pct:.2f}%", delta_color=delta_color,
            )
        else:
            c4.metric("Rendimento (%)", "—",
                      help="Necessário ter aportes registrados.")

        if len(df_sorted) >= 2:
            st.divider()
            st.markdown("**📈 Evolução da posição**")
            df_chart = df_sorted.assign(
                Data_Formatada=lambda d: d["Data_DT"].dt.strftime("%d/%m/%y")
            )
            components.area_balance(
                df_chart, x="Data_Formatada", y="Valor", color=Colors.PRIMARY,
            )

    st.divider()
    st.markdown("**🗂️ Histórico de posições**")
    st.caption("Edite, corrija ou apague registros antigos.")
    editable = df_positions.drop(
        columns=[c for c in ("Data_DT",) if c in df_positions.columns]
    )
    with st.form("edit_positions"):
        edited = st.data_editor(
            editable, num_rows="dynamic", use_container_width=True,
        )
        if st.form_submit_button("💾 Salvar alterações"):
            if not editable.equals(edited):
                repository.save_investment_positions(edited)
                st.success("Histórico salvo.")
                st.rerun()
            else:
                st.info("Nada a salvar — sem alterações.")
