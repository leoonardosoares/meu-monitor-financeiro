"""Página: Dashboard principal."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from src import (
    components, credit_card as cc, insights, positions, repository,
)
from src.config import ConfigKeys
from src.finance import (
    avg_monthly_expense, budget_status, compute_wealth, expenses_by_category,
    financial_independence_months, fixed_costs_split,
    monthly_investment_contributions, monthly_summary, previous_month,
    projection_target, savings_rate, spending_velocity,
)
from src.format import brl, md
from src.sidebar import ALL_MONTHS


def render(*, df_transactions: pd.DataFrame, df_credit_card: pd.DataFrame,
           df_transactions_period: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           df_fixed_costs: pd.DataFrame,
           df_budgets: pd.DataFrame,
           df_cards: pd.DataFrame,
           df_card_payments: pd.DataFrame,
           selected_month: str) -> None:
    """O Dashboard em quatro abas, da pergunta mais imediata à mais ampla.

    Eram nove seções numa coluna só, separadas por divisores idênticos:
    posição real, insights, ritmo, quatro KPIs, quatro indicadores de
    saúde, barras do ano, projeção, orçamento, aportes e despesas por
    categoria. Dezessete cartões de número na mesma tela não formam um
    painel — formam uma parede, e nada nela indica onde começar.

    As abas separam por horizonte: **Agora** é o que existe neste
    instante, lido do banco; **Mês** é o desempenho do período filtrado;
    **Próximo mês** é a projeção; **Histórico** é a série longa.
    """
    period_label = (selected_month if selected_month != ALL_MONTHS
                    else "todo o período")
    components.page_header(
        "Resumo",
        f"Período em análise: {period_label}. A aba **Próximo mês** "
        "sempre olha para frente, independente do filtro.",
    )

    # Os insights ficam acima das abas: são avisos, e um aviso escondido
    # numa aba que não se abriu não é aviso.
    auto_insights = insights.generate(
        df_transactions=df_transactions,
        df_credit_card=df_credit_card,
        df_budgets=df_budgets,
        selected_month=selected_month,
    )
    if auto_insights:
        components.insight_chips(auto_insights)

    aba_agora, aba_mes, aba_proximo, aba_hist = st.tabs(
        ["💰 Agora", "📊 O mês", "🔭 Próximo mês", "📈 Histórico"])

    with aba_agora:
        _real_position_section(df_transactions)

    with aba_mes:
        _spending_velocity_section(df_transactions_period, df_budgets)
        components.section(
            "Receitas, despesas e patrimônio",
            f"Números de {period_label}, com a variação sobre o mês "
            "anterior quando há um mês selecionado.",
            eyebrow="Desempenho do período",
        )
        _kpi_section(df_transactions, df_transactions_period, selected_month)
        st.write("")
        components.section(
            "Saúde financeira",
            "Quanto você guarda, quanto tempo a reserva cobre e quanto da "
            "renda já está comprometida.",
        )
        _health_section(df_transactions, df_transactions_period)

        st.write("")
        components.section(
            "Status do orçamento",
            f"Quanto cada categoria consumiu do limite definido em "
            f"Configurações ({period_label}). A linha tracejada marca "
            "os 100%.",
        )
        components.budget_overview(budget_status(
            df_budgets, df_transactions_period, df_credit_card_period))

        st.write("")
        components.section(
            "Despesas por categoria",
            "Soma das saídas do banco com as compras do cartão.")
        components.horizontal_bar_expenses(expenses_by_category(
            df_transactions_period, df_credit_card_period))

    with aba_proximo:
        _projection_section(
            df_credit_card=df_credit_card,
            df_card_payments=df_card_payments,
            df_cards=df_cards,
            df_fixed_costs=df_fixed_costs,
            df_transactions=df_transactions,
            selected_month=selected_month,
        )

    with aba_hist:
        components.section(
            "Receitas e despesas mês a mês",
            "Últimos 12 meses. Barras lado a lado para comparar o que "
            "entrou com o que saiu.",
            eyebrow="Histórico",
        )
        components.annual_bars(monthly_summary(df_transactions, months=12))

        st.write("")
        components.section(
            "Aportes em investimento",
            "Quanto entrou na sua conta de investimento por mês.")
        components.monthly_contributions_bars(
            monthly_investment_contributions(df_transactions, months=12))


# ---------------------------------------------------------------------------
# Seções internas
# ---------------------------------------------------------------------------

def _real_position_section(df_transactions: pd.DataFrame) -> None:
    """O que os bancos dizem que você tem, agora.

    Fica acima de tudo porque é a resposta à pergunta que se faz ao
    abrir o app. Os números derivados da planilha continuam logo abaixo,
    para o período — é o que a planilha sabe fazer bem.
    """
    ids = [i.strip() for i in
           repository.load_config_text(ConfigKeys.PLUGGY_ITEMS).split(",")
           if i.strip()]
    if not ids:
        return

    guardada = positions.from_rows(repository.load_positions())

    cabecalho, botao = st.columns([4, 1])
    with cabecalho:
        components.section(
            "Onde seu dinheiro está agora",
            "Lido direto das instituições. Estes são os valores do banco, "
            "não uma soma de lançamentos.",
            eyebrow="Posição real",
        )
    if botao.button("🔄 Atualizar", use_container_width=True):
        nova = positions.fetch(ids)
        for erro in nova.erros:
            st.warning(f"⚠️ {erro}")
        if not nova.vazia:
            repository.append_position(positions.to_rows(nova))
            st.rerun()

    if guardada.vazia:
        st.info(
            "Ainda não li a sua posição. Clique em **Atualizar** para "
            "buscar saldos e investimentos direto das instituições."
        )
        return

    st.caption(f"Última leitura: {_quando(guardada.quando)}.")

    esq, dir_ = st.columns(2)
    with esq:
        components.stat_card(
            label="🏦 Contas bancárias", value=guardada.em_conta,
            rows=[{"nome": c.instituicao, "sub": c.nome,
                   "valor": brl(c.saldo), "bruto": c.saldo}
                  for c in guardada.contas
                  if c.tipo == positions.TIPO_BANCO],
        )
    with dir_:
        limite = _limite_total()
        components.stat_card(
            label="💳 Cartões de crédito", value=guardada.em_cartao,
            divida=True,
            bar=(guardada.em_cartao / limite) if limite else None,
            bar_label=(
                f"{guardada.em_cartao / limite * 100:.0f}% utilizado · "
                f"limite {brl(limite)}" if limite else ""),
            rows=[{"nome": c.nome, "sub": c.instituicao,
                   "valor": brl(abs(c.saldo)), "divida": True}
                  for c in guardada.contas
                  if c.tipo == positions.TIPO_CARTAO],
        )

    st.write("")
    esq, dir_ = st.columns(2)
    with esq:
        components.stat_card(
            label="📈 Investimentos", value=guardada.investido,
            rows=[{"nome": a.nome, "sub": a.instituicao,
                   "valor": brl(a.valor), "bruto": a.valor}
                  for a in guardada.ativos[:6]],
        )
    with dir_:
        components.stat_card(
            label="💎 Patrimônio", value=guardada.patrimonio,
            rows=[
                {"nome": "Em conta", "valor": brl(guardada.em_conta),
                 "bruto": guardada.em_conta},
                {"nome": "Investido", "valor": brl(guardada.investido),
                 "bruto": guardada.investido},
                {"nome": "Cartões a pagar",
                 "valor": f"− {brl(guardada.em_cartao)}", "divida": True},
            ],
        )

    _reconciliation(guardada, df_transactions)

    with st.expander("Ver conta a conta"):
        linhas = [{
            "Instituição": c.instituicao, "Conta": c.nome,
            "Tipo": "Cartão" if c.tipo == positions.TIPO_CARTAO else "Conta",
            "Valor": brl(abs(c.saldo)),
        } for c in guardada.contas]
        linhas += [{
            "Instituição": a.instituicao, "Conta": a.nome,
            "Tipo": "Investimento", "Valor": brl(a.valor),
        } for a in guardada.ativos]
        components.table(pd.DataFrame(linhas))
        if not guardada.ativos:
            st.caption(
                "Nenhum investimento veio das conexões. Nem toda "
                "instituição publica isso no Open Finance; os ativos "
                "cadastrados à mão continuam na aba Investimentos."
            )

    historico = positions.history(repository.load_positions())
    if len(historico) > 1:
        st.write("")
        components.section(
            "Evolução do patrimônio",
            "Um ponto por dia em que a posição foi lida.")
        components.area_trend(historico, x="Data", y="Patrimônio")


def _limite_total() -> float:
    """Soma dos limites cadastrados, para a barra de uso do cartão."""
    df = repository.load_cards()
    if df.empty or "Limite" not in df.columns:
        return 0.0
    return float(pd.to_numeric(df["Limite"], errors="coerce").fillna(0).sum())


def _quando(carimbo: str) -> str:
    """Carimbo ISO em texto legível, sem quebrar se vier torto."""
    try:
        return datetime.fromisoformat(str(carimbo)).strftime("%d/%m/%Y às %H:%M")
    except ValueError:
        return str(carimbo) or "—"


def _reconciliation(posicao, df_transactions: pd.DataFrame) -> None:
    """Quanto a planilha difere do banco, e por quê.

    A diferença não é defeito a esconder: ela mede exatamente o que
    falta lançar. Mostrá-la é o que transforma "não está batendo" numa
    pergunta com resposta.
    """
    derivado = compute_wealth(df_transactions, df_transactions).bank_balance
    diferenca = posicao.em_conta - derivado
    if abs(diferenca) < 0.01:
        st.success("A planilha bate com o banco, ao centavo.")
        return

    with st.expander(
        f"⚖️ A planilha difere do banco em {brl(abs(diferenca))}"
    ):
        c1, c2, c3 = st.columns(3)
        c1.metric("Banco diz", brl(posicao.em_conta))
        c2.metric("Planilha soma", brl(derivado))
        c3.metric("Diferença", brl(diferenca),
                  delta="falta lançar" if diferenca > 0 else "lançado a mais",
                  delta_color="off")
        st.caption(
            "A soma da planilha só igualaria o banco se ela contivesse "
            "toda a sua história, sem falha nem repetição. Se você "
            "importou a partir de uma data, o que veio antes está fora "
            "— e a diferença é justamente isso. **Os números acima, do "
            "banco, são os corretos**; a planilha serve para explicar "
            "para onde o dinheiro foi, não para dizer quanto você tem."
        )

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


def _totais_do_banco() -> dict[tuple[str, str], float]:
    """{(cartão, mês): total que a instituição informa para a fatura}."""
    df = repository.load_bank_bills()
    if df.empty or not {"Cartão", "Mês", "Total"}.issubset(df.columns):
        return {}
    out: dict[tuple[str, str], float] = {}
    for _, linha in df.iterrows():
        valor = pd.to_numeric(linha.get("Total"), errors="coerce")
        if not pd.isna(valor):
            out[(str(linha["Cartão"]).strip(),
                 str(linha["Mês"]).strip())] = abs(float(valor))
    return out


def _valor_a_pagar(fatura, banco: dict[tuple[str, str], float]) -> float:
    """Quanto essa fatura tira da conta.

    O total do banco manda quando existe: ele conhece compras que ainda
    não foram importadas. A soma das linhas entra só quando a fatura
    ainda não foi emitida — parcela futura, que o banco não faturou.
    """
    do_banco = banco.get((fatura.card, fatura.month))
    if do_banco is None:
        return fatura.balance
    return max(do_banco - fatura.advances, 0.0)


def _projection_section(*, df_credit_card: pd.DataFrame,
                        df_card_payments: pd.DataFrame,
                        df_cards: pd.DataFrame,
                        df_fixed_costs: pd.DataFrame,
                        df_transactions: pd.DataFrame,
                        selected_month: str) -> None:
    """Com quanto você fica ao fim do próximo mês.

    Parte do dinheiro que existe hoje — lido do banco, não somado de
    lançamentos — e tira tudo que vence daqui até lá. É a pergunta que
    se faz olhando o mês seguinte; "quanto sobra do salário" responde
    outra coisa e some com o que já está na conta.
    """
    hoje = date.today()
    alvo, veio_do_filtro = projection_target(selected_month, today=hoje)

    agendadas, ilegiveis = cc.schedule_invoices(
        df_credit_card, df_card_payments, df_cards, today=hoje)
    banco_totais = _totais_do_banco()
    a_pagar = cc.invoices_due_through(agendadas, alvo)
    faturas = sum(_valor_a_pagar(i, banco_totais) for i in a_pagar)

    posicao = positions.from_rows(repository.load_positions())
    saldo_hoje = posicao.em_conta
    receita = repository.load_config(ConfigKeys.RECEITA_PREVISTA, 0.0)
    fixos, fixos_cartao = fixed_costs_split(
        df_fixed_costs, {i.card for i in a_pagar})
    sobra = saldo_hoje + receita - fixos - faturas

    components.section(
        f"Com quanto você fica ao fim de {alvo}",
        ("O mês do filtro." if veio_do_filtro else
         "Esta aba não segue o filtro da sidebar — ela sempre olha para "
         "frente."),
        eyebrow="Projeção",
    )

    # O resultado primeiro, num cartão; a conta que leva a ele nas linhas
    # abaixo. Eram cinco métricas do mesmo tamanho em fila, e a última —
    # a única que responde a pergunta — não se distinguia das quatro que
    # são só parcelas dela.
    esq, dir_ = st.columns([1, 1])
    with esq:
        components.stat_card(
            label=f"Sobra ao fim de {alvo}", value=sobra,
            rows=[
                {"nome": "Saldo hoje no banco", "valor": brl(saldo_hoje),
                 "bruto": saldo_hoje},
                {"nome": "Receita prevista", "valor": f"+ {brl(receita)}",
                 "bruto": receita},
                {"nome": "Custos fixos", "valor": f"− {brl(fixos)}",
                 "divida": True},
                {"nome": "Faturas a pagar", "valor": f"− {brl(faturas)}",
                 "sub": f"{len(a_pagar)} fatura(s) até o fim de {alvo}",
                 "divida": True},
            ],
        )
    with dir_:
        entra = saldo_hoje + receita
        sai = fixos + faturas
        components.stat_card(
            label="Quanto sai até lá", value=sai, divida=True,
            bar=(sai / entra) if entra > 0 else None,
            bar_label=(f"{sai / entra * 100:.0f}% do que você tem e espera "
                       f"receber" if entra > 0 else ""),
            rows=[
                {"nome": "Faturas de cartão", "valor": brl(faturas),
                 "divida": True},
                {"nome": "Custos fixos", "valor": brl(fixos),
                 "divida": True},
            ],
        )

    if posicao.vazia:
        st.info(md(
            "O saldo de hoje está zerado porque ainda não li as "
            "instituições. Vá ao topo do Dashboard e clique em "
            "**Atualizar**."
        ))

    _projection_warnings(agendadas, ilegiveis)
    _detalhe_projecao(a_pagar, banco_totais, saldo_hoje, receita, fixos,
                      faturas, sobra, alvo, fixos_cartao, df_transactions)


def _detalhe_projecao(a_pagar, banco_totais, saldo_hoje, receita, fixos,
                      faturas, sobra, alvo, fixos_cartao,
                      df_transactions) -> None:
    """A conta aberta, linha a linha, para poder ser conferida."""
    with st.expander("Como cheguei nesse número"):
        components.table(pd.DataFrame([
            {"Linha": "Saldo em conta hoje", "Valor": brl(saldo_hoje)},
            {"Linha": "Receita prevista", "Valor": brl(receita)},
            {"Linha": "Custos fixos", "Valor": f"− {brl(fixos)}"},
            {"Linha": "Faturas a pagar", "Valor": f"− {brl(faturas)}"},
            {"Linha": f"Sobra ao fim de {alvo}", "Valor": brl(sobra)},
        ]))

        if a_pagar:
            st.markdown("**As faturas que entram na conta**")
            components.table(pd.DataFrame([{
                "Cartão": i.card, "Fatura": i.month,
                "Vence": f"{i.due:%d/%m/%Y}",
                "Valor": brl(_valor_a_pagar(i, banco_totais)),
                "Fonte": ("banco"
                          if (i.card, i.month) in banco_totais
                          else "soma das linhas"),
                "Situação": "vencida" if i.overdue else "a vencer",
            } for i in a_pagar]))
            st.caption(
                "Entra tudo que sai da conta daqui até o fim do mês: o "
                "que venceu e não foi pago, o que ainda vence neste mês "
                "e o do mês projetado."
            )

        if fixos_cartao > 0:
            st.caption(md(
                f"{brl(fixos_cartao)} de custos fixos na categoria "
                "*Cartão de Crédito* foram excluídos: a fatura já entra "
                "pelo seu próprio valor."
            ))

        variavel = avg_monthly_expense(df_transactions, months=6,
                                       exclude_card_invoices=True)
        if variavel > 0:
            st.caption(md(
                f"Esta conta não inclui gasto variável no banco, que tem "
                f"média de {brl(variavel)}/mês nos últimos 6 meses. "
                f"Descontando, sobrariam {brl(sobra - variavel)}."
            ))


def _projection_warnings(agendadas: list, ilegiveis: list[str]) -> None:
    atrasadas = cc.overdue_invoices(agendadas)
    if atrasadas:
        linhas = " · ".join(
            f"{i.card} {i.month} ({brl(i.balance)}, venceu {i.due:%d/%m})"
            for i in atrasadas
        )
        st.warning(md(
            f"⚠️ **{brl(sum(i.balance for i in atrasadas))} em fatura "
            f"vencida e não paga** — {linhas}. Já está incluída nas "
            "faturas a pagar acima, porque esse dinheiro sai da conta de "
            "qualquer forma. Dê baixa na aba Cartão de Crédito."
        ))

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

