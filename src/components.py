"""Componentes/widgets reutilizáveis do Streamlit + Plotly."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import Colors
from src.format import brl
from src.insights import Insight


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def page_header(title: str, subtitle: str | None = None) -> None:
    """Cabeçalho padronizado das páginas."""
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)
    st.divider()


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

_PLOT_CONFIG = {"displayModeBar": False}
_TIPO_COLORS = {"Entrada": Colors.INCOME, "Saída": Colors.EXPENSE}


def _apply_layout(fig, *, x_title: str = "", y_title: str = "") -> None:
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis_title=x_title,
        yaxis_title=y_title,
        legend_title_text="",
        hovermode="x unified",
    )


def donut_by_category(df: pd.DataFrame, *, empty_msg: str = "Sem dados.") -> None:
    """Gráfico de rosca: Categoria x Valor."""
    if df.empty or df["Valor"].sum() <= 0:
        st.info(empty_msg)
        return
    fig = px.pie(
        df, values="Valor", names="Categoria", hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig.update_traces(textinfo="percent+label", textposition="inside")
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True, config=_PLOT_CONFIG)


def line_income_vs_expense(df_daily: pd.DataFrame, *,
                           empty_msg: str = "Sem movimentações.") -> None:
    if df_daily.empty:
        st.info(empty_msg)
        return
    df = df_daily.copy()
    df["Label"] = df["Valor"].apply(lambda v: brl(v) if v > 0 else "")
    fig = px.line(
        df, x="Data_Formatada", y="Valor", color="Tipo",
        text="Label", markers=True, line_shape="spline",
        color_discrete_map=_TIPO_COLORS,
    )
    fig.update_traces(textposition="top center", mode="lines+markers+text")
    _apply_layout(fig, x_title="Dia", y_title="R$")
    st.plotly_chart(fig, use_container_width=True, config=_PLOT_CONFIG)


def area_cumulative(df_cumulative: pd.DataFrame, *,
                    empty_msg: str = "Sem movimentações.") -> None:
    if df_cumulative.empty:
        st.info(empty_msg)
        return
    fig = px.area(
        df_cumulative, x="Data_Formatada", y="Valor", color="Tipo",
        line_shape="spline", color_discrete_map=_TIPO_COLORS,
    )
    fig.update_traces(stackgroup=None, fill="tozeroy", opacity=0.55, mode="lines")
    _apply_layout(fig, x_title="Dia", y_title="R$ (acumulado)")
    st.plotly_chart(fig, use_container_width=True, config=_PLOT_CONFIG)


def horizontal_bar_expenses(df: pd.DataFrame, *,
                             color: str = Colors.EXPENSE,
                             empty_msg: str = "Sem despesas.") -> None:
    if df.empty:
        st.info(empty_msg)
        return
    df = df.sort_values("Valor", ascending=True).copy()
    df["Label"] = df["Valor"].apply(brl)
    fig = px.bar(
        df, x="Valor", y="Categoria", orientation="h", text="Label",
        color_discrete_sequence=[color],
    )
    fig.update_traces(textposition="outside")
    _apply_layout(fig)
    fig.update_xaxes(tickprefix="R$ ", gridcolor="rgba(200,200,200,0.2)")
    st.plotly_chart(fig, use_container_width=True, config=_PLOT_CONFIG)


def vertical_bar(df: pd.DataFrame, x: str, y: str, *,
                 color: str = Colors.INVESTMENT,
                 empty_msg: str = "Sem dados.") -> None:
    if df.empty:
        st.info(empty_msg)
        return
    df = df.copy()
    df["Label"] = df[y].apply(brl)
    fig = px.bar(df, x=x, y=y, text="Label", color_discrete_sequence=[color])
    fig.update_traces(textposition="outside")
    _apply_layout(fig)
    st.plotly_chart(fig, use_container_width=True, config=_PLOT_CONFIG)


def area_balance(df: pd.DataFrame, x: str, y: str, *,
                 color: str = Colors.INCOME,
                 y_title: str = "Saldo (R$)") -> None:
    df = df.copy()
    df["Label"] = df[y].apply(brl)
    fig = px.area(df, x=x, y=y, text="Label", markers=True,
                  line_shape="spline", color_discrete_sequence=[color])
    fig.update_traces(textposition="top center", mode="lines+markers+text")
    _apply_layout(fig, x_title="Dia", y_title=y_title)
    st.plotly_chart(fig, use_container_width=True, config=_PLOT_CONFIG)


def annual_bars(df_monthly: pd.DataFrame, *,
                empty_msg: str = "Sem histórico para o período.") -> None:
    """Barras agrupadas: receitas vs despesas por mês."""
    if df_monthly.empty:
        st.info(empty_msg)
        return
    df_long = df_monthly.melt(
        id_vars="Mes_Ano", value_vars=["Receitas", "Despesas"],
        var_name="Tipo", value_name="Valor",
    )
    fig = px.bar(
        df_long, x="Mes_Ano", y="Valor", color="Tipo", barmode="group",
        color_discrete_map={"Receitas": Colors.INCOME, "Despesas": Colors.EXPENSE},
    )
    fig.update_traces(hovertemplate="%{x}<br>%{y:,.2f}")
    _apply_layout(fig, x_title="", y_title="R$")
    fig.update_yaxes(tickprefix="R$ ", gridcolor="rgba(200,200,200,0.2)")
    st.plotly_chart(fig, use_container_width=True, config=_PLOT_CONFIG)




# ---------------------------------------------------------------------------
# Insights e métricas com delta MoM
# ---------------------------------------------------------------------------

def insight_chips(insights: list[Insight]) -> None:
    """Renderiza insights como linhas com ícone + mensagem."""
    if not insights:
        return
    for insight in insights:
        if insight.severity == "critico":
            st.error(f"{insight.icon} {insight.message}")
        elif insight.severity == "alerta":
            st.warning(f"{insight.icon} {insight.message}")
        elif insight.severity == "positivo":
            st.success(f"{insight.icon} {insight.message}")
        else:
            st.info(f"{insight.icon} {insight.message}")


def metric_with_delta(container, *, label: str, value: float,
                      previous: float | None,
                      higher_is_better: bool = True,
                      format_fn=brl) -> None:
    """Card de métrica com delta percentual e cor semântica."""
    delta_str = None
    delta_color = "off"
    if previous is not None and previous > 0:
        pct = (value - previous) / previous * 100
        delta_str = f"{pct:+.1f}% vs mês anterior"
        if abs(pct) < 1:
            delta_color = "off"
        elif (pct > 0) == higher_is_better:
            delta_color = "normal"
        else:
            delta_color = "inverse"
    container.metric(label, format_fn(value), delta=delta_str, delta_color=delta_color)
