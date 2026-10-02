"""Componentes/widgets reutilizáveis do Streamlit + Plotly."""
from __future__ import annotations

from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from src.config import Colors, TEMA_PADRAO
from src.format import brl, md
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
            # Fundo da paleta, não transparente: o transparente deixava
            # aparecer o fundo nativo do Streamlit, que era escuro mesmo
            # no modo claro. O gráfico é desenhado como cartão (ver CSS
            # de stPlotlyChart), então o fundo é o da superfície.
            paper_bgcolor=Colors.SURFACE,
            plot_bgcolor=Colors.SURFACE,
            colorway=Colors.SERIES,
            # Decimal com vírgula e milhar com ponto: "R$ 4.000", não
            # "R$ 4,000".
            separators=",.",
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


def _com_fundo_do_tema(plotar):
    """Envolve `st.plotly_chart` para gravar o fundo NA figura.

    O Streamlit pinta o fundo do gráfico com a cor secundária do tema
    nativo e ignora o que vem do template — o miolo do gráfico ficava de
    outra cor dentro do cartão. Com o fundo gravado no layout da própria
    figura, ele vale em todo gráfico do app, sem lembrar disso em cada um.
    """
    if getattr(plotar, "_com_fundo", False):
        return plotar

    def _plotar(fig, *args, **kwargs):
        try:
            fig.update_layout(paper_bgcolor=Colors.SURFACE,
                              plot_bgcolor=Colors.SURFACE)
        except Exception:                                 # noqa: BLE001
            pass
        return plotar(fig, *args, **kwargs)
    _plotar._com_fundo = True
    return _plotar


st.plotly_chart = _com_fundo_do_tema(st.plotly_chart)


# ---------------------------------------------------------------------------
# Cartões no estilo painel financeiro
# ---------------------------------------------------------------------------

def _classe(valor: float, *, divida: bool) -> str:
    """Verde para o que é seu, vermelho para o que você deve.

    Zero não é dívida: "nada a pagar" em vermelho alarmava à toa. E um
    valor de dívida negativo é crédito a seu favor, então fica verde.
    """
    if abs(valor) < 0.005:
        return "mf-mut"
    if divida:
        return "mf-neg" if valor > 0 else "mf-pos"
    return "mf-pos" if valor >= 0 else "mf-neg"


def _texto(valor) -> str:
    """Texto vindo do banco ou da planilha, seguro dentro de HTML.

    Escapa tudo e depois devolve o negrito e o itálico do markdown, que
    os cabeçalhos usam: dentro de um bloco HTML o Streamlit não processa
    markdown, e os asteriscos apareciam literais na tela.
    """
    import re
    t = escape(str(valor or ""))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    return t


def hero(*, label: str, value: float, note: str = "",
         parts: list[tuple[str, float, bool]] | None = None) -> None:
    """O número principal de uma tela, grande, com as partes que o formam.

    `parts` é [(rótulo, valor, é_dívida)]. Dívida aparece com o sinal de
    menos, porque é o que ela faz com o total.
    """
    classe = _classe(value, divida=False)
    html = ['<div class="mf-hero">',
            f'<div class="mf-hero__label">{_texto(label)}</div>',
            f'<div class="mf-hero__value {classe}">{brl(value)}</div>']
    if note:
        html.append(f'<div class="mf-hero__note">{_texto(note)}</div>')
    if parts:
        html.append('<div class="mf-hero__parts">')
        for rotulo, valor, divida in parts:
            texto = f"− {brl(abs(valor))}" if divida else brl(valor)
            cor = _classe(valor, divida=divida)
            html.append(
                f'<div class="mf-hero__part"><span>{_texto(rotulo)}</span>'
                f'<b class="{cor}">{texto}</b></div>')
        html.append("</div>")
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


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
    texto = brl(abs(value)) if divida and value > 0 else brl(value)
    html = [
        '<div class="mf-card">',
        f'<div class="mf-card__label">{_texto(label)}</div>',
        f'<div class="mf-card__value {classe}">{texto}</div>',
    ]
    if bar is not None:
        pct = max(0.0, min(bar, 1.0)) * 100
        cor = Colors.EXPENSE if pct >= 80 else Colors.PRIMARY
        html.append(
            f'<div class="mf-row__sub">{_texto(bar_label)}</div>'
            f'<div class="mf-bar"><span style="width:{pct:.0f}%;'
            f'background:{cor}"></span></div>'
        )
    for linha in rows or []:
        sub = (f'<div class="mf-row__sub">{_texto(linha.get("sub"))}</div>'
               if linha.get("sub") else "")
        # Cada linha é colorida pelo próprio valor: herdar a cor do
        # total pintaria "Em conta R$ 222,69" de vermelho só porque o
        # patrimônio ficou negativo.
        cor = linha.get("classe") or _classe(
            linha.get("bruto", 0.0), divida=bool(linha.get("divida")))
        html.append(
            '<div class="mf-row"><div>'
            f'<div class="mf-row__name">{_texto(linha.get("nome"))}</div>{sub}'
            f'</div><div class="mf-row__val {cor}">'
            f'{_texto(linha.get("valor"))}</div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def tint(color: str, alpha: float) -> str:
    """Um hex da paleta como `rgba(...)`, para preenchimento de área.

    Existe para o preenchimento seguir o tema: escrito à mão, ele fica
    com a cor de um modo só — havia um verde e um vermelho fixos que não
    tinham relação com a paleta ativa.
    """
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def area_trend(df: pd.DataFrame, x: str, y: str, *, color: str | None = None,
               height: int = 220) -> None:
    """Linha com preenchimento em degradê, para série temporal.

    Uma série só, então sem legenda: o título já diz o que é. Sem
    marcador em cada ponto — a forma da curva é o dado, não os pontos.
    """
    if df.empty or len(df) < 2:
        return
    cor = color or Colors.PRIMARY
    # Sem preencher até o zero: com o patrimônio na casa dos milhares, a
    # área até o zero achatava a curva numa linha reta no topo.
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="lines+markers",
        line=dict(color=cor, width=2.5, shape="spline"),
        marker=dict(size=7, color=cor),
        hovertemplate="%{x|%d/%m}<br><b>R$ %{y:,.2f}</b><extra></extra>",
    ))
    fig.update_layout(height=height, margin=dict(t=18, b=34, l=16, r=22),
                      hovermode="x unified", showlegend=False)
    fig.update_yaxes(showgrid=True, tickprefix="R$ ", separatethousands=True)
    # Um ponto por dia: o eixo mostra dias, não "00:00 / 12:00".
    fig.update_xaxes(showgrid=False, type="date", tickformat="%d/%m",
                     dtick=86400000 if len(df) <= 14 else None)
    st.plotly_chart(fig, use_container_width=True, theme=None,
                    config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def page_header(title: str, subtitle: str | None = None) -> None:
    """Cabeçalho da página, um degrau acima de qualquer seção dentro dela.

    Emitia `### `, que é o mesmo `h3` do `st.subheader` — então o nome da
    página tinha exatamente o peso de cada bloco nela, e a tela não tinha
    começo. Com os cabeçalhos de seção em 1,15rem a hierarquia chegou a
    ficar invertida: a seção maior que a página. Aqui o título é maior que
    tudo que vem depois, e a linha de contexto fica junto dele em vez de
    virar um parágrafo solto seguido de divisor.
    """
    partes = [
        '<div class="mf-page">',
        f'<div class="mf-page__title">{_texto(title)}</div>',
    ]
    if subtitle:
        partes.append(f'<div class="mf-page__sub">{_texto(subtitle)}</div>')
    partes.append("</div>")
    st.markdown("".join(partes), unsafe_allow_html=True)


def section(title: str, sub: str | None = None, *,
            eyebrow: str | None = None) -> None:
    """Cabeçalho de seção: sobrancelha, título e uma linha de contexto.

    Substitui o trio `subheader` + `caption` + `divider` que se repetia
    em cada bloco. Nove seções separadas por divisor viram nove faixas do
    mesmo peso, e a página perde o começo: nada indica o que é a resposta
    e o que é o detalhe. Aqui a hierarquia está no tipo, não no traço.
    """
    partes = ['<div class="mf-sec">']
    if eyebrow:
        partes.append(f'<div class="mf-sec__eyebrow">{_texto(eyebrow)}</div>')
    partes.append(f'<div class="mf-sec__title">{_texto(title)}</div>')
    if sub:
        partes.append(f'<div class="mf-sec__sub">{_texto(sub)}</div>')
    partes.append("</div>")
    st.markdown("".join(partes), unsafe_allow_html=True)


def table(df: pd.DataFrame, *, align_right: tuple[str, ...] = (),
          empty_msg: str = "Nada para mostrar.", max_rows: int = 200) -> None:
    """Tabela de leitura em HTML, com as cores do tema.

    `st.dataframe` é desenhado num canvas e segue o tema nativo do
    Streamlit, que é lido do `config.toml` na inicialização e não muda.
    Num app claro ele aparecia como um retângulo preto de texto branco no
    meio da página — e nenhuma folha de estilo alcança aquilo, porque não
    é HTML.

    Esta serve só para tabela de leitura. Onde o usuário edita, o
    `st.data_editor` continua sendo a peça certa.

    Dinheiro aqui NÃO passa por `md()`. A regra do `$` que vira LaTeX
    vale para texto markdown; num bloco de HTML o Streamlit repassa o
    conteúdo sem processar inline, e o cartão de estatística já prova
    isso na prática — ele imprime quatro valores em reais no mesmo bloco
    e todos aparecem certos. Escapar aqui produziria uma barra invertida
    visível antes de cada cifrão.
    """
    if df is None or df.empty:
        st.caption(empty_msg)
        return

    recorte = df.head(max_rows)
    # A descrição vem do banco e entra num bloco com `unsafe_allow_html`:
    # sem escapar, um "<" no nome de um estabelecimento quebra a tabela
    # inteira, e o resto da página junto.
    cabecalho = "".join(
        f'<th class="{"mf-tbl--num" if c in align_right else ""}">'
        f"{escape(str(c))}</th>"
        for c in recorte.columns)
    corpo = []
    for _, linha in recorte.iterrows():
        celulas = "".join(
            f'<td class="{"mf-tbl--num" if c in align_right else ""}">'
            f'{"" if pd.isna(linha[c]) else escape(str(linha[c]))}</td>'
            for c in recorte.columns)
        corpo.append(f"<tr>{celulas}</tr>")
    st.markdown(
        f'<div class="mf-tbl-wrap"><table class="mf-tbl">'
        f"<thead><tr>{cabecalho}</tr></thead>"
        f'<tbody>{"".join(corpo)}</tbody></table></div>',
        unsafe_allow_html=True,
    )
    if len(df) > max_rows:
        st.caption(f"…e mais {len(df) - max_rows} linha(s).")


def invoice_card(*, card: str, month: str, value: str, state: str,
                 accent: str, dates: str = "", source: str = "",
                 negative: bool = False) -> None:
    """Uma fatura como bloco, não como linha de tabela.

    A lista de faturas eram quatro dataframes empilhados, um por
    situação, cada um com título em negrito e legenda: seis colunas para
    dizer três coisas. Aqui cada fatura é um cartão com a situação numa
    etiqueta colorida, as datas embaixo do nome e o valor à direita — que
    é a ordem em que se lê.
    """
    numero = pd.to_numeric(str(value).replace("R$", "").replace(".", "")
                           .replace(",", ".").strip(), errors="coerce")
    classe = ("mf-pos" if not negative or (not pd.isna(numero) and numero < 0)
              else "mf-neg")
    html = [
        f'<div class="mf-inv" style="--accent:{accent}">',
        "<div>",
        f'<span class="mf-tag" style="color:{accent}">{_texto(state)}</span>',
        f'<div class="mf-inv__who">{_texto(card)} · {_texto(month)}</div>',
    ]
    if dates:
        html.append(f'<div class="mf-inv__when">{_texto(dates)}</div>')
    html.append("</div><div>")
    html.append(f'<div class="mf-inv__val {classe}">{value}</div>')
    if source:
        html.append(f'<div class="mf-inv__src" style="text-align:right">'
                    f'{_texto(source)}</div>')
    html.append("</div></div>")
    st.markdown("".join(html), unsafe_allow_html=True)


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
                             color: str | None = None,
                             empty_msg: str = "Sem despesas.") -> None:
    if df.empty:
        st.info(empty_msg)
        return
    df = df.sort_values("Valor", ascending=True).copy()
    df["Label"] = df["Valor"].apply(brl)
    fig = px.bar(
        df, x="Valor", y="Categoria", orientation="h", text="Label",
        color_discrete_sequence=[color or Colors.EXPENSE],
    )
    fig.update_traces(textposition="outside")
    _apply_layout(fig)
    fig.update_xaxes(tickprefix="R$ ", gridcolor=Colors.GRID)
    st.plotly_chart(fig, use_container_width=True, theme=None, config=_PLOT_CONFIG)


def vertical_bar(df: pd.DataFrame, x: str, y: str, *,
                 color: str | None = None,
                 empty_msg: str = "Sem dados.") -> None:
    if df.empty:
        st.info(empty_msg)
        return
    df = df.copy()
    df["Label"] = df[y].apply(brl)
    fig = px.bar(df, x=x, y=y, text="Label",
                 color_discrete_sequence=[color or Colors.INVESTMENT])
    fig.update_traces(textposition="outside")
    _apply_layout(fig)
    st.plotly_chart(fig, use_container_width=True, theme=None, config=_PLOT_CONFIG)


def area_balance(df: pd.DataFrame, x: str, y: str, *,
                 color: str | None = None,
                 y_title: str = "Saldo (R$)") -> None:
    df = df.copy()
    df["Label"] = df[y].apply(brl)
    fig = px.area(df, x=x, y=y, text="Label", markers=True,
                  line_shape="spline",
                  color_discrete_sequence=[color or Colors.INCOME])
    fig.update_traces(textposition="top center", mode="lines+markers+text")
    _apply_layout(fig, x_title="Dia", y_title=y_title)
    st.plotly_chart(fig, use_container_width=True, theme=None, config=_PLOT_CONFIG)


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

    # Trilha: o "vazio" que a barra preenche, na cor de trilha do tema.
    # Estava fixa num cinza-gelo claro, invisível no modo escuro.
    fig.add_trace(go.Bar(
        x=[100] * len(df), y=df["Categoria"], orientation="h",
        marker=dict(color=Colors.TRACK, line=dict(width=0)),
        hoverinfo="skip", showlegend=False, width=0.55,
    ))

    # Barra principal: gasto real, colorida por status
    fig.add_trace(go.Bar(
        x=df["Pct_capped"], y=df["Categoria"], orientation="h",
        marker=dict(color=bar_colors, line=dict(width=0)),
        text=labels, textposition="outside",
        textfont=dict(size=13, color=Colors.TEXT, family="Inter, sans-serif"),
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
        xaxis=dict(
            title=dict(text="% do orçamento consumido",
                       font=dict(size=12, color=Colors.NEUTRAL)),
            ticksuffix="%",
            range=[0, max(145, df["Pct_capped"].max() * 1.12)],
            tickfont=dict(size=12, color=Colors.NEUTRAL),
            gridcolor=Colors.GRID, showgrid=True, zeroline=False,
        ),
        yaxis=dict(
            tickfont=dict(size=13, color=Colors.TEXT,
                          family="Inter, sans-serif"),
            showgrid=False, zeroline=False,
        ),
        legend=dict(
            orientation="h", y=-0.22 if n > 4 else -0.32,
            x=0.5, xanchor="center",
            font=dict(size=12, color=Colors.NEUTRAL),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    st.plotly_chart(fig, use_container_width=True, theme=None, config=_PLOT_CONFIG)


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
    fig.update_yaxes(tickprefix="R$ ", gridcolor=Colors.GRID)
    st.plotly_chart(fig, use_container_width=True, theme=None, config=_PLOT_CONFIG)


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
    fig.update_yaxes(tickprefix="R$ ", gridcolor=Colors.GRID)
    st.plotly_chart(fig, use_container_width=True, theme=None, config=_PLOT_CONFIG)

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
        # md(): dois valores em reais na mesma frase viravam fórmula
        # LaTeX — "(R 230,00 vs R 4.035,64)" em fonte de código.
        texto = md(f"{insight.icon} {insight.message}")
        if insight.severity == "critico":
            st.error(texto)
        elif insight.severity == "alerta":
            st.warning(texto)
        elif insight.severity == "positivo":
            st.success(texto)
        else:
            st.info(texto)


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
