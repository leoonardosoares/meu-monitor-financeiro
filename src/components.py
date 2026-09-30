"""Componentes/widgets reutilizáveis do Streamlit + Plotly."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from src.config import Colors, TEMA_PADRAO
from src.format import brl
from src.insights import Insight


# ---------------------------------------------------------------------------
# Template global do Plotly — todo gráfico do app herda tipografia Inter,
# fundo transparente (integra com o wash verde da página), grid discreto
# e o colorway da paleta da marca. Registrado uma vez na importação.
# ---------------------------------------------------------------------------

def _template() -> go.layout.Template:
    """Template do Plotly com as cores do tema ativo."""
    return go.layout.Template(
        layout=go.Layout(
            font=dict(
                family="Inter, 'Segoe UI', sans-serif",
                size=13,
                color=Colors.TEXT_MUTED,
            ),
            # Transparente para o gráfico sentar dentro do cartão, sem um
            # retângulo mais claro denunciando onde o Plotly começa.
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=Colors.SERIES,
            hoverlabel=dict(
                bgcolor=Colors.SURFACE_2,
                bordercolor=Colors.BORDER,
                font=dict(family="Inter, 'Segoe UI', sans-serif", size=13,
                          color=Colors.TEXT),
            ),
            # Grade quase invisível: ela orienta, não compete com o dado.
            xaxis=dict(gridcolor=Colors.GRID, zeroline=False,
                       linecolor=Colors.AXIS,
                       tickfont=dict(color=Colors.TEXT_FAINT, size=11)),
            yaxis=dict(gridcolor=Colors.GRID, zeroline=False,
                       linecolor=Colors.AXIS,
                       tickfont=dict(color=Colors.TEXT_FAINT, size=11)),
            legend=dict(font=dict(size=12, color=Colors.TEXT_MUTED),
                        bgcolor="rgba(0,0,0,0)"),
            margin=dict(t=10, b=10, l=10, r=10),
        )
    )
def use_theme(mode: str) -> None:
    """Refaz o template com a paleta do modo.

    Precisa ser chamado a cada render: o template é global do processo e
    o modo é escolha do usuário, então deixá-lo fixo na importação faria
    o gráfico ficar escuro num app claro.
    """
    Colors.use(mode)
    pio.templates["monitor"] = _template()
    pio.templates.default = (
        "plotly_dark+monitor" if mode == "dark" else "plotly_white+monitor")


use_theme(TEMA_PADRAO)


# ---------------------------------------------------------------------------
# Cartões no estilo painel financeiro
# ---------------------------------------------------------------------------

def _classe(valor: float, *, divida: bool) -> str:
    """Verde para o que é seu, vermelho para o que você deve."""
    if divida:
        return "mf-neg"
    return "mf-pos" if valor >= 0 else "mf-neg"


def stat_card(*, label: str, value: float, rows: list[dict] | None = None,
              divida: bool = False, bar: float | None = None,
              bar_label: str = "") -> None:
    """Cartão com rótulo pequeno, número grande e linhas por conta.

    É a peça que dá o ar de app de banco: o número responde a pergunta
    e as linhas abaixo mostram de onde ele vem, sem exigir um clique.

    O sinal do total é preservado. Só o cartão de dívida mostra valor
    absoluto, porque ali o rótulo já diz que é o que se deve — em
    qualquer outro, esconder o menos faz um patrimônio negativo parecer
    positivo, que é o erro mais caro que esta tela pode cometer.
    """
    classe = _classe(value, divida=divida)
    texto = brl(abs(value)) if divida else brl(value)
    html = [
        '<div class="mf-card">',
        f'<div class="mf-card__label">{label}</div>',
        f'<div class="mf-card__value {classe}">{texto}</div>',
    ]
    if bar is not None:
        pct = max(0.0, min(bar, 1.0)) * 100
        cor = Colors.EXPENSE if pct >= 80 else Colors.PRIMARY
        html.append(
            f'<div class="mf-row__sub">{bar_label}</div>'
            f'<div class="mf-bar"><span style="width:{pct:.0f}%;'
            f'background:{cor}"></span></div>'
        )
    for linha in rows or []:
        sub = f'<div class="mf-row__sub">{linha.get("sub", "")}</div>' \
            if linha.get("sub") else ""
        # Cada linha é colorida pelo próprio valor: herdar a cor do
        # total pintaria "Em conta R$ 222,69" de vermelho só porque o
        # patrimônio ficou negativo.
        cor = linha.get("classe") or _classe(
            linha.get("bruto", 0.0), divida=bool(linha.get("divida")))
        html.append(
            '<div class="mf-row"><div>'
            f'<div class="mf-row__name">{linha.get("nome", "")}</div>{sub}'
            f'</div><div class="mf-row__val {cor}">'
            f'{linha.get("valor", "")}</div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def area_trend(df: pd.DataFrame, x: str, y: str, *, color: str | None = None,
               height: int = 220) -> None:
    """Linha com preenchimento em degradê, para série temporal.

    Uma série só, então sem legenda: o título já diz o que é. Sem
    marcador em cada ponto — a forma da curva é o dado, não os pontos.
    """
    if df.empty or len(df) < 2:
        return
    cor = color or Colors.PRIMARY
    r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="lines", line=dict(color=cor, width=2),
        fill="tozeroy", fillcolor=f"rgba({r},{g},{b},0.16)",
        hovertemplate="%{x}<br><b>%{y:,.2f}</b><extra></extra>",
    ))
    fig.update_layout(height=height, margin=dict(t=6, b=6, l=6, r=6),
                      hovermode="x unified", showlegend=False)
    fig.update_yaxes(showgrid=True)
    fig.update_xaxes(showgrid=False)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


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
        plot_bgcolor="rgba(0,0,0,0)",
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


def monthly_contributions_bars(df_monthly: pd.DataFrame, *,
                                show_summary: bool = True,
                                empty_msg: str = "Nenhum aporte registrado nos últimos meses.") -> None:
    """Aportes (verde) e saques (vermelho) de investimento por mês.

    Se não houver nenhum saque no período, mostra só a série de aportes
    pra deixar a leitura mais limpa.
    """
    if df_monthly.empty or df_monthly["Aportes"].sum() == 0 and df_monthly["Saques"].sum() == 0:
        st.info(empty_msg)
        return

    has_saques = bool((df_monthly["Saques"] > 0).any())

    if has_saques:
        df_long = df_monthly.melt(
            id_vars="Mes_Ano", value_vars=["Aportes", "Saques"],
            var_name="Tipo", value_name="Valor",
        )
        fig = px.bar(
            df_long, x="Mes_Ano", y="Valor", color="Tipo", barmode="group",
            color_discrete_map={
                "Aportes": Colors.INVESTMENT, "Saques": Colors.EXPENSE,
            },
        )
        fig.update_traces(hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>")
    else:
        df = df_monthly.copy()
        df["Label"] = df["Aportes"].apply(lambda v: brl(v) if v > 0 else "")
        fig = px.bar(
            df, x="Mes_Ano", y="Aportes", text="Label",
            color_discrete_sequence=[Colors.INVESTMENT],
        )
        fig.update_traces(
            textposition="outside", cliponaxis=False,
            hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>",
        )

    _apply_layout(fig, x_title="", y_title="R$")
    fig.update_yaxes(tickprefix="R$ ", gridcolor="rgba(200,200,200,0.2)")
    st.plotly_chart(fig, use_container_width=True, config=_PLOT_CONFIG)

    if show_summary:
        total_aportes = float(df_monthly["Aportes"].sum())
        total_saques = float(df_monthly["Saques"].sum())
        meses_com_aporte = int((df_monthly["Aportes"] > 0).sum())
        media = total_aportes / meses_com_aporte if meses_com_aporte else 0.0

        c1, c2, c3 = st.columns(3)
        c1.metric("Total aportado", brl(total_aportes))
        c2.metric(
            "Média por mês com aporte",
            brl(media) if meses_com_aporte else "—",
            delta=f"{meses_com_aporte} mês(es) com aporte",
            delta_color="off",
        )
        c3.metric(
            "Saques no período", brl(total_saques),
            delta_color="off" if total_saques == 0 else "inverse",
        )


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
