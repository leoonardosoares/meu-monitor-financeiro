"""Componentes/widgets reutilizáveis do Streamlit + Plotly."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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


def _apply_layout(fig, *, x_title: str = "", y_title: str = "") -> None:
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis_title=x_title,
        yaxis_title=y_title,
        legend_title_text="",
        hovermode="x unified",
    )


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


def budget_overview(df_status: pd.DataFrame, *,
                    empty_msg: str = "Defina orçamentos em Configurações para acompanhar aqui.") -> None:
    """Barras horizontais "trilha + preenchimento": cada categoria tem uma
    pista cinza (0–100%) e por cima a barra colorida que indica o quanto
    foi consumido. Espaçamento generoso para não esmagar as barras.
    """
    if df_status.empty:
        st.info(empty_msg)
        return

    df = df_status.copy().sort_values("Pct", ascending=True).reset_index(drop=True)
    df["Pct_capped"] = df["Pct"].clip(upper=130)

    status_color = {
        "ok": Colors.INCOME,
        "alerta": Colors.WARNING,
        "estourado": Colors.EXPENSE,
    }
    bar_colors = [status_color[s] for s in df["Status"]]
    labels = [
        f"R$ {g:,.0f} / R$ {l:,.0f}  ·  {p:.0f}%".replace(",", ".")
        for g, l, p in zip(df["Gasto"], df["Limite"], df["Pct"])
    ]

    fig = go.Figure()

    # Trilha: barra cinza clara representando 0–100% como referência
    fig.add_trace(go.Bar(
        x=[100] * len(df), y=df["Categoria"], orientation="h",
        marker=dict(color="rgba(226, 232, 240, 0.55)", line=dict(width=0)),
        hoverinfo="skip", showlegend=False, width=0.55,
    ))

    # Barra principal: gasto real, colorida por status
    fig.add_trace(go.Bar(
        x=df["Pct_capped"], y=df["Categoria"], orientation="h",
        marker=dict(color=bar_colors, line=dict(width=0)),
        text=labels, textposition="outside",
        textfont=dict(size=13, color="#0F172A", family="Inter, sans-serif"),
        hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
        cliponaxis=False, showlegend=False, width=0.55,
    ))

    # Legenda manual (3 entradas fixas via traces invisíveis)
    legend_items = [
        ("Tranquilo (< 80%)", Colors.INCOME),
        ("Quase no limite (80–100%)", Colors.WARNING),
        ("Estourou (> 100%)", Colors.EXPENSE),
    ]
    for name, color in legend_items:
        fig.add_trace(go.Bar(
            x=[None], y=[None], name=name,
            marker=dict(color=color, line=dict(width=0)),
            showlegend=True,
        ))

    # Linha pontilhada no 100% como referência visual
    fig.add_vline(
        x=100, line_dash="dash", line_color=Colors.NEUTRAL, opacity=0.5,
    )

    n = len(df)
    height = max(360, 56 * n + 110)  # 56px por categoria + margens

    fig.update_layout(
        barmode="overlay",
        height=height,
        margin=dict(t=20, b=80, l=10, r=80),
        plot_bgcolor="white",
        xaxis=dict(
            title=dict(text="% do orçamento consumido",
                       font=dict(size=12, color=Colors.NEUTRAL)),
            ticksuffix="%",
            range=[0, max(145, df["Pct_capped"].max() * 1.12)],
            tickfont=dict(size=12, color=Colors.NEUTRAL),
            gridcolor="rgba(226, 232, 240, 0.7)", showgrid=True, zeroline=False,
        ),
        yaxis=dict(
            tickfont=dict(size=13, color="#0F172A", family="Inter, sans-serif"),
            showgrid=False, zeroline=False,
        ),
        legend=dict(
            orientation="h", y=-0.22 if n > 4 else -0.32,
            x=0.5, xanchor="center",
            font=dict(size=12, color=Colors.NEUTRAL),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
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
