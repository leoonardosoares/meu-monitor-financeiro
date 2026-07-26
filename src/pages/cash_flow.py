"""Página: Fluxo de Caixa — projeção dos próximos meses + simulador de compras.

Responde perguntas como: "se eu comprar um monitor de R$ 2.000 em 10x hoje,
como fica meu saldo nos próximos meses?".
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import components, repository
from src.config import Colors, ConfigKeys
from src.finance import (
    card_pending_by_month, cash_flow_projection, compute_wealth,
    estimate_variable_monthly, simulated_purchases_by_month,
)
from src.format import brl

_PURCHASES_KEY = "cash_flow_simulated_purchases"


def render(*, df_transactions: pd.DataFrame, df_credit_card: pd.DataFrame,
           df_fixed_costs: pd.DataFrame) -> None:
    components.page_header(
        "Fluxo de Caixa",
        "Projeção realista dos próximos meses com base na sua receita, custos "
        "fixos e faturas já contratadas — e simulação de compras hipotéticas.",
    )

    # ── Premissas (dados reais do app) ─────────────────────────────────────
    wealth = compute_wealth(df_transactions, df_transactions)
    expected_income = repository.load_config(ConfigKeys.RECEITA_PREVISTA, 0.0)
    fixed_total = float(df_fixed_costs["Valor"].fillna(0).sum()) \
        if not df_fixed_costs.empty else 0.0
    closing_day = int(repository.load_config(ConfigKeys.DIA_FECHAMENTO, 8))
    card_pending = card_pending_by_month(df_credit_card)
    variable_estimate = estimate_variable_monthly(df_transactions, fixed_total)

    st.subheader("Premissas da projeção")
    c1, c2, c3 = st.columns(3)
    c1.metric("Saldo bancário hoje", brl(wealth.bank_balance))
    c2.metric("Receita mensal prevista", brl(expected_income),
              delta="Configurações → Custos Fixos", delta_color="off")
    c3.metric("Custos fixos mensais", brl(fixed_total))

    if expected_income <= 0:
        st.warning(
            "Defina sua **receita prevista** em Configurações e Orçamento → "
            "Custos Fixos para a projeção fazer sentido."
        )

    p1, p2 = st.columns(2)
    months = p1.slider("Horizonte da projeção (meses):",
                       min_value=3, max_value=12, value=6)
    variable_monthly = p2.number_input(
        "Gastos variáveis estimados por mês (R$):",
        min_value=0.0, value=round(variable_estimate, 2), step=50.0,
        help="Pré-preenchido com a média dos últimos 3 meses de saídas "
             "bancárias, já descontando custos fixos e pagamentos de fatura "
             "(que entram separados). Ajuste como quiser.",
    )

    st.divider()

    # ── Simulador de compras ───────────────────────────────────────────────
    st.subheader("Simular uma compra")
    st.caption(
        'Ex.: "monitor de R$ 2.000 em 10x no cartão". Parcelas caem na fatura '
        f"seguindo o dia de fechamento real do seu cartão (dia {closing_day})."
    )

    purchases: list[dict] = st.session_state.setdefault(_PURCHASES_KEY, [])

    with st.form("add_simulated_purchase", clear_on_submit=True):
        f1, f2 = st.columns([2, 1])
        desc = f1.text_input("O que você quer comprar?",
                             placeholder="Ex.: Monitor 27 polegadas")
        valor = f2.number_input("Valor total (R$)", min_value=0.01,
                                format="%.2f", value=2000.0)
        f3, f4, f5 = st.columns(3)
        forma = f3.selectbox("Forma de pagamento",
                             ["Cartão de crédito", "À vista / débito"])
        parcelas = f4.number_input("Parcelas", min_value=1, max_value=48,
                                   value=10, step=1,
                                   help="Ignorado se for à vista.")
        data_compra = f5.date_input("Data da compra", value=date.today(),
                                    format="DD/MM/YYYY")
        if st.form_submit_button("➕ Adicionar à simulação"):
            purchases.append({
                "descricao": desc.strip() or "Compra simulada",
                "valor": float(valor),
                "parcelas": int(parcelas) if forma == "Cartão de crédito" else 1,
                "forma": forma,
                "data": data_compra,
            })

    if purchases:
        st.markdown("**Compras na simulação:**")
        for i, p in enumerate(purchases):
            row = st.columns([4, 1])
            if p["forma"] == "Cartão de crédito" and p["parcelas"] > 1:
                detail = (f"{p['parcelas']}x de {brl(p['valor'] / p['parcelas'])} "
                          f"no cartão")
            else:
                detail = f"{brl(p['valor'])} à vista"
            row[0].write(
                f"🛒 **{p['descricao']}** — {detail} "
                f"(compra em {p['data']:%d/%m/%Y})"
            )
            if row[1].button("Remover", key=f"rm_purchase_{i}"):
                purchases.pop(i)
                st.rerun()
        if st.button("🗑️ Limpar simulação"):
            st.session_state[_PURCHASES_KEY] = []
            st.rerun()

    st.divider()

    # ── Projeção: baseline vs simulado ─────────────────────────────────────
    baseline = cash_flow_projection(
        months=months, start_balance=wealth.bank_balance,
        expected_income=expected_income, fixed_total=fixed_total,
        card_pending=card_pending, variable_monthly=variable_monthly,
    )
    extra = simulated_purchases_by_month(purchases, closing_day)
    simulated = cash_flow_projection(
        months=months, start_balance=wealth.bank_balance,
        expected_income=expected_income, fixed_total=fixed_total,
        card_pending=card_pending, variable_monthly=variable_monthly,
        extra_by_month=extra,
    )

    st.subheader("Projeção do saldo em conta")
    _projection_chart(baseline, simulated, has_simulation=bool(purchases))
    _impact_summary(baseline, simulated, purchases)

    with st.expander("Ver detalhamento mês a mês"):
        detail = simulated.copy()
        for col in ("Receita", "Custos Fixos", "Fatura Cartão", "Variáveis",
                    "Simulado", "Liquido", "Saldo Acumulado"):
            detail[col] = detail[col].apply(brl)
        st.dataframe(detail, hide_index=True, use_container_width=True)
        st.caption(
            "Modelo: saldo do mês = receita − custos fixos − fatura pendente "
            "do cartão − variáveis estimados − compras simuladas. Receita e "
            "custos fixos assumidos constantes."
        )


# ---------------------------------------------------------------------------

def _projection_chart(baseline: pd.DataFrame, simulated: pd.DataFrame,
                      *, has_simulation: bool) -> None:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=baseline["Mes_Ano"], y=baseline["Saldo Acumulado"],
        mode="lines+markers+text", name="Sem a compra",
        text=[brl(v) for v in baseline["Saldo Acumulado"]],
        textposition="top center", textfont=dict(size=11),
        line=dict(color=Colors.INCOME, width=3, shape="spline"),
        marker=dict(size=7),
    ))
    if has_simulation:
        fig.add_trace(go.Scatter(
            x=simulated["Mes_Ano"], y=simulated["Saldo Acumulado"],
            mode="lines+markers+text", name="Com a compra",
            text=[brl(v) for v in simulated["Saldo Acumulado"]],
            textposition="bottom center", textfont=dict(size=11),
            line=dict(color=Colors.WARNING, width=3, shape="spline",
                      dash="dot"),
            marker=dict(size=7),
        ))
    fig.add_hline(y=0, line_dash="dash", line_color=Colors.EXPENSE,
                  opacity=0.5)
    fig.update_layout(
        height=420,
        yaxis_title="Saldo em conta (R$)",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    fig.update_yaxes(tickprefix="R$ ")
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


def _impact_summary(baseline: pd.DataFrame, simulated: pd.DataFrame,
                    purchases: list[dict]) -> None:
    if not purchases:
        st.info(
            "Adicione uma compra acima para comparar os dois cenários. "
            "A linha verde mostra sua trajetória atual."
        )
        return

    total_cost = sum(p["valor"] for p in purchases)
    monthly_delta = simulated["Simulado"]
    worst_monthly = float(monthly_delta.max())
    end_diff = float(
        baseline["Saldo Acumulado"].iloc[-1]
        - simulated["Saldo Acumulado"].iloc[-1]
    )

    k1, k2, k3 = st.columns(3)
    k1.metric("Custo total simulado", brl(total_cost))
    k2.metric("Maior impacto em um mês", brl(worst_monthly),
              delta="Pico de comprometimento", delta_color="off")
    k3.metric("Diferença no fim do período", f"−{brl(end_diff)}",
              delta_color="inverse")

    negative_months = simulated.loc[
        simulated["Saldo Acumulado"] < 0, "Mes_Ano"
    ].tolist()
    tight_months = simulated.loc[
        (simulated["Liquido"] < 0) & (simulated["Saldo Acumulado"] >= 0),
        "Mes_Ano",
    ].tolist()

    if negative_months:
        st.error(
            f"🚨 Com essa compra, seu saldo em conta ficaria **negativo** em: "
            f"{', '.join(negative_months)}. Considere menos parcelas, adiar "
            f"a compra ou reduzir gastos variáveis."
        )
    elif tight_months:
        st.warning(
            f"⚠️ A compra cabe no bolso, mas nestes meses você gastaria mais "
            f"do que ganha (saldo cai): {', '.join(tight_months)}."
        )
    else:
        st.success(
            "✅ A compra cabe no seu fluxo de caixa: nenhum mês fica negativo "
            "e o saldo continua crescendo."
        )
