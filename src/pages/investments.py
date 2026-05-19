"""Página: Investimentos (reserva, aportes/saques, posição, carteira, simulador)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from src import components, repository
from src.config import Colors, ConfigKeys
from src.finance import compute_wealth, cumulative_invested_at
from src.format import brl


def render(*, df_transactions: pd.DataFrame) -> None:
    components.page_header(
        "Meus Investimentos",
        "Reserva de emergência, aportes/saques, rendimento real, carteira "
        "por classe de ativo e simulador de juros compostos.",
    )

    tabs = st.tabs([
        "🎯 Metas e Aportes",
        "💎 Posição Atual",
        "🧩 Carteira por Classe",
        "🔮 Simulador",
    ])

    wealth = compute_wealth(df_transactions, df_transactions)
    invested = wealth.invested

    with tabs[0]:
        _goals_tab(df_transactions=df_transactions, invested=invested)
    with tabs[1]:
        _position_tab(invested=invested, df_transactions=df_transactions)
    with tabs[2]:
        _portfolio_tab()
    with tabs[3]:
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


def _position_tab(*, invested: float, df_transactions: pd.DataFrame) -> None:
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
            st.markdown("**📈 Evolução**")

            chart_mode = st.radio(
                "Visualizar:",
                ["Posição total", "Rendimento acumulado", "Comparar (posição × aportes)"],
                horizontal=True,
                key="position_chart_mode",
            )

            df_chart = df_sorted.copy()
            df_chart["Aportado"] = df_chart["Data_DT"].apply(
                lambda d: cumulative_invested_at(df_transactions, d)
            )
            df_chart["Rendimento"] = df_chart["Valor"] - df_chart["Aportado"]
            df_chart["Data_Formatada"] = df_chart["Data_DT"].dt.strftime("%d/%m/%y")

            if chart_mode == "Posição total":
                components.area_balance(
                    df_chart, x="Data_Formatada", y="Valor",
                    color=Colors.PRIMARY, y_title="Valor atual (R$)",
                )
            elif chart_mode == "Rendimento acumulado":
                latest_return = float(df_chart["Rendimento"].iloc[-1])
                color = Colors.INCOME if latest_return >= 0 else Colors.EXPENSE
                components.area_balance(
                    df_chart, x="Data_Formatada", y="Rendimento",
                    color=color, y_title="Rendimento (R$)",
                )
                st.caption(
                    "Rendimento = valor atual no dia − total aportado até o dia. "
                    "Pode ser negativo se a posição estiver abaixo do que foi aportado."
                )
            else:  # Comparar
                df_long = df_chart.melt(
                    id_vars=["Data_Formatada"],
                    value_vars=["Valor", "Aportado"],
                    var_name="Série", value_name="R$",
                )
                df_long["Série"] = df_long["Série"].map({
                    "Valor": "Posição (real)",
                    "Aportado": "Total aportado",
                })
                fig = px.line(
                    df_long, x="Data_Formatada", y="R$", color="Série",
                    markers=True, line_shape="spline",
                    color_discrete_map={
                        "Posição (real)": Colors.PRIMARY,
                        "Total aportado": Colors.NEUTRAL,
                    },
                )
                fig.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10),
                    xaxis_title="Dia", yaxis_title="R$",
                    legend_title_text="", hovermode="x unified",
                )
                fig.update_yaxes(tickprefix="R$ ")
                st.plotly_chart(
                    fig, use_container_width=True,
                    config={"displayModeBar": False},
                )
                st.caption(
                    "O espaço entre as duas linhas é o **rendimento** "
                    "acumulado em cada data."
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


def _portfolio_tab() -> None:
    st.subheader("Alocação por classe de ativo")
    st.caption(
        "Distribua seus investimentos entre classes (Renda Fixa, Ações, FIIs, "
        "Cripto, etc.) e defina uma meta de alocação ideal. O app calcula o "
        "desvio entre real e meta e avisa quando algo está fora do alvo."
    )

    df_alloc = repository.load_investment_allocation()
    default_classes = ["Renda Fixa", "Ações", "FIIs", "Cripto", "Internacional"]
    if df_alloc.empty:
        df_alloc = pd.DataFrame(
            {"Classe": default_classes,
             "Valor": [0.0] * len(default_classes),
             "Meta (%)": [0.0] * len(default_classes)}
        )

    with st.form("edit_allocation"):
        edited = st.data_editor(
            df_alloc, num_rows="dynamic", use_container_width=True,
            hide_index=True,
            column_config={
                "Valor": st.column_config.NumberColumn(
                    "Valor (R$)", min_value=0.0, format="%.2f",
                ),
                "Meta (%)": st.column_config.NumberColumn(
                    "Meta (%)", min_value=0.0, max_value=100.0, format="%.0f",
                ),
            },
        )
        if st.form_submit_button("💾 Salvar carteira"):
            repository.save_investment_allocation(edited)
            st.success("Carteira salva.")
            st.rerun()

    clean = edited.dropna(subset=["Classe"]).copy() if not edited.empty else edited
    clean = clean[clean["Classe"].astype(str).str.strip() != ""] if not clean.empty else clean
    clean["Valor"] = pd.to_numeric(clean.get("Valor"), errors="coerce").fillna(0)
    clean["Meta (%)"] = pd.to_numeric(clean.get("Meta (%)"), errors="coerce").fillna(0)

    total = float(clean["Valor"].sum())
    meta_total = float(clean["Meta (%)"].sum())

    if total <= 0:
        st.info("Preencha os valores de cada classe para ver gráficos e alertas.")
        return

    st.divider()
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("**Distribuição atual**")
        fig = px.pie(
            clean[clean["Valor"] > 0], values="Valor", names="Classe", hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_traces(textinfo="percent+label", textposition="inside")
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with c2:
        st.markdown("**Atual × Meta**")
        clean["% Atual"] = clean["Valor"] / total * 100
        comparison = clean.melt(
            id_vars="Classe", value_vars=["% Atual", "Meta (%)"],
            var_name="Tipo", value_name="Percentual",
        )
        fig2 = px.bar(
            comparison, x="Percentual", y="Classe", color="Tipo", barmode="group",
            orientation="h",
            color_discrete_map={"% Atual": Colors.PRIMARY, "Meta (%)": Colors.NEUTRAL},
        )
        fig2.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            legend_title_text="",
            xaxis_title="%", yaxis_title="",
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    # Alertas de desvio (só se a meta total bate 100%)
    if abs(meta_total - 100) > 1:
        st.warning(
            f"As metas somam **{meta_total:.0f}%** — ajuste para somar 100% "
            "para receber recomendações de rebalanceamento."
        )
        return

    st.markdown("**Recomendações de rebalanceamento**")
    deviations = []
    for _, row in clean.iterrows():
        target_value = total * row["Meta (%)"] / 100
        diff = row["Valor"] - target_value
        if abs(diff) < total * 0.02:  # ignora desvios menores que 2%
            continue
        deviations.append((row["Classe"], diff))

    if not deviations:
        st.success("✅ Sua carteira está dentro do alvo. Mantenha o ritmo.")
        return
    for classe, diff in sorted(deviations, key=lambda x: -abs(x[1])):
        if diff > 0:
            st.warning(
                f"📉 **{classe}**: {brl(diff)} acima da meta. "
                "Considere direcionar próximos aportes para outras classes."
            )
        else:
            st.info(
                f"📈 **{classe}**: {brl(abs(diff))} abaixo da meta. "
                "Vale aportar mais nessa classe."
            )
