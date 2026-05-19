"""Cálculos financeiros puros.

Funções aqui não tocam em Streamlit nem em I/O — só transformam DataFrames
e retornam números/DataFrames. Isso permite testar e reusar em qualquer
contexto.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class WealthSummary:
    """Resumo do patrimônio em um instante."""
    total_income: float            # entradas no período filtrado
    total_expense: float           # saídas no período filtrado
    bank_balance: float            # saldo bancário (entradas - saídas globais)
    invested: float                # aportes - saques de investimento
    net_worth: float               # bank_balance + invested


def _sum_by(df: pd.DataFrame, *, tipo: str | None = None,
            categoria: str | None = None) -> float:
    if df.empty:
        return 0.0
    mask = pd.Series(True, index=df.index)
    if tipo is not None:
        mask &= df["Tipo"] == tipo
    if categoria is not None:
        mask &= df["Categoria"] == categoria
    valor = df.loc[mask, "Valor"]
    return float(valor.sum()) if not valor.empty else 0.0


def compute_wealth(df_all: pd.DataFrame, df_period: pd.DataFrame) -> WealthSummary:
    """Calcula KPIs principais.

    `df_all` = histórico completo (usado para saldo bancário e investido).
    `df_period` = subset filtrado pelo mês selecionado (usado para
    receitas/despesas do período).
    """
    income_global = _sum_by(df_all, tipo="Entrada")
    expense_global = _sum_by(df_all, tipo="Saída")
    bank_balance = income_global - expense_global

    aportes = _sum_by(df_all, tipo="Saída", categoria="Investimento")
    saques = _sum_by(df_all, tipo="Entrada", categoria="Investimento")
    invested = aportes - saques

    return WealthSummary(
        total_income=_sum_by(df_period, tipo="Entrada"),
        total_expense=_sum_by(df_period, tipo="Saída"),
        bank_balance=bank_balance,
        invested=invested,
        net_worth=bank_balance + invested,
    )


def daily_flow(df_period: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Constrói os DataFrames diário e acumulado para os gráficos.

    Retorna (df_daily, df_cumulative). Cada linha tem Data_DT, Tipo
    (Entrada/Saída), Valor e Data_Formatada (%d/%m).
    """
    if df_period.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = df_period.copy()
    df["Data_DT"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data_DT"])
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    pivot = df.pivot_table(
        index="Data_DT", columns="Tipo", values="Valor",
        aggfunc="sum", fill_value=0,
    )
    for col in ("Entrada", "Saída"):
        if col not in pivot.columns:
            pivot[col] = 0.0

    full_idx = pd.date_range(pivot.index.min(), pivot.index.max())
    pivot = pivot.reindex(full_idx, fill_value=0.0)

    daily = (
        pivot.reset_index()
        .rename(columns={"index": "Data_DT"})
        .melt(id_vars="Data_DT", value_vars=["Entrada", "Saída"],
              var_name="Tipo", value_name="Valor")
        .assign(Data_Formatada=lambda d: d["Data_DT"].dt.strftime("%d/%m"))
        .sort_values("Data_DT")
    )

    cumulative_pivot = pivot.cumsum()
    cumulative = (
        cumulative_pivot.reset_index()
        .rename(columns={"index": "Data_DT"})
        .melt(id_vars="Data_DT", value_vars=["Entrada", "Saída"],
              var_name="Tipo", value_name="Valor")
        .assign(Data_Formatada=lambda d: d["Data_DT"].dt.strftime("%d/%m"))
        .sort_values("Data_DT")
    )

    return daily, cumulative


def expenses_by_category(df_transactions: pd.DataFrame,
                         df_credit_card: pd.DataFrame,
                         *, exclude: list[str] | None = None) -> pd.DataFrame:
    """Soma despesas (banco + cartão) agrupadas por categoria."""
    expenses_bank = (
        df_transactions[df_transactions["Tipo"] == "Saída"][["Categoria", "Valor"]]
        if not df_transactions.empty else pd.DataFrame(columns=["Categoria", "Valor"])
    )
    expenses_card = (
        df_credit_card[["Categoria", "Valor"]]
        if not df_credit_card.empty else pd.DataFrame(columns=["Categoria", "Valor"])
    )
    combined = pd.concat([expenses_bank, expenses_card])
    if exclude:
        combined = combined[~combined["Categoria"].isin(exclude)]
    if combined.empty:
        return combined
    return combined.groupby("Categoria")["Valor"].sum().reset_index()


def list_months(df_transactions: pd.DataFrame,
                df_credit_card: pd.DataFrame) -> list[str]:
    """Lista MM/YYYY presentes em transações ou cartão (mais recente primeiro)."""
    months: set[str] = set()
    if "Mes_Ano" in df_transactions.columns:
        months.update(df_transactions["Mes_Ano"].dropna().unique().tolist())
    if "Mês da Fatura" in df_credit_card.columns:
        months.update(df_credit_card["Mês da Fatura"].dropna().unique().tolist())
    months.discard("Sem Data")
    months.discard("")
    return sorted(months, reverse=True)


def filter_by_month(df_transactions: pd.DataFrame,
                    df_credit_card: pd.DataFrame,
                    month: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica o filtro de mês. `month=None` (ou "Todos os Meses") = sem filtro."""
    if not month or month == "Todos os Meses":
        return df_transactions, df_credit_card
    df_t = df_transactions[df_transactions["Mes_Ano"] == month]
    df_c = df_credit_card[df_credit_card["Mês da Fatura"] == month] \
        if not df_credit_card.empty else df_credit_card
    return df_t, df_c


# ---------------------------------------------------------------------------
# Indicadores de saúde financeira
# ---------------------------------------------------------------------------

def savings_rate(income: float, expense: float) -> float:
    """Taxa de poupança em %: quanto da renda sobrou.

    Ex.: income=5000, expense=3500 -> 30.0
    Retorna 0.0 se a renda for zero (evita divisão por zero).
    """
    if income <= 0:
        return 0.0
    return (income - expense) / income * 100


def avg_monthly_expense(df_transactions: pd.DataFrame, *, months: int = 6) -> float:
    """Despesa mensal média dos últimos N meses (com data válida)."""
    if df_transactions.empty:
        return 0.0
    df = df_transactions[df_transactions["Tipo"] == "Saída"].copy()
    if df.empty:
        return 0.0
    df["Data_DT"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data_DT"])
    if df.empty:
        return 0.0
    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(months=months)
    recent = df[df["Data_DT"] >= cutoff]
    if recent.empty:
        return 0.0
    return float(recent["Valor"].sum()) / months


def financial_independence_months(emergency_fund: float,
                                  avg_monthly_expense_value: float) -> float:
    """Quantos meses o fundo de emergência cobre as despesas médias."""
    if avg_monthly_expense_value <= 0:
        return 0.0
    return emergency_fund / avg_monthly_expense_value


# ---------------------------------------------------------------------------
# Comparação mês-a-mês
# ---------------------------------------------------------------------------

def previous_month(month_str: str) -> str:
    """'05/2026' -> '04/2026'. Funciona com virada de ano."""
    dt = pd.to_datetime(month_str, format="%m/%Y")
    prev = dt - pd.DateOffset(months=1)
    return prev.strftime("%m/%Y")


def pct_change(current: float, previous: float) -> float | None:
    """Variação percentual. Retorna None se o anterior for zero ou negativo."""
    if previous is None or previous <= 0:
        return None
    return (current - previous) / previous * 100


# ---------------------------------------------------------------------------
# Velocidade de gasto do mês corrente
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpendingVelocity:
    days_passed: int
    days_in_month: int
    spent_so_far: float
    daily_avg: float
    projected_month_end: float


def spending_velocity(df_transactions_period: pd.DataFrame, *,
                      today: date | None = None) -> SpendingVelocity | None:
    """Análise de ritmo de gastos do mês corrente.

    Retorna `None` se não houver transações suficientes ou se o período
    selecionado não for o mês atual.
    """
    if df_transactions_period.empty:
        return None

    today = today or date.today()
    df = df_transactions_period[df_transactions_period["Tipo"] == "Saída"].copy()
    if df.empty:
        return None
    df["Data_DT"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data_DT"])
    if df.empty:
        return None

    # Só faz sentido projetar se o período é o mês atual.
    if not (df["Data_DT"].dt.month == today.month).any() or \
       not (df["Data_DT"].dt.year == today.year).any():
        return None

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_passed = max(today.day, 1)
    spent = float(df["Valor"].sum())
    daily_avg = spent / days_passed
    projected = daily_avg * days_in_month

    return SpendingVelocity(
        days_passed=days_passed,
        days_in_month=days_in_month,
        spent_so_far=spent,
        daily_avg=daily_avg,
        projected_month_end=projected,
    )


# ---------------------------------------------------------------------------
# Visão anual (últimos 12 meses)
# ---------------------------------------------------------------------------

def monthly_summary(df_transactions: pd.DataFrame, *,
                    months: int = 12,
                    today: date | None = None) -> pd.DataFrame:
    """Receitas e despesas agregadas dos últimos N meses.

    Inclui meses sem movimentação (preenche com zero). Útil pro gráfico
    de barras anuais.
    """
    today = today or date.today()
    anchor = pd.Timestamp(year=today.year, month=today.month, day=1)
    month_starts = [
        (anchor - pd.DateOffset(months=i)).strftime("%m/%Y")
        for i in range(months)
    ][::-1]

    rows = []
    if df_transactions.empty or "Mes_Ano" not in df_transactions.columns:
        for m in month_starts:
            rows.append({"Mes_Ano": m, "Receitas": 0.0, "Despesas": 0.0})
        return pd.DataFrame(rows)

    grouped = (
        df_transactions.groupby(["Mes_Ano", "Tipo"])["Valor"].sum().unstack(fill_value=0)
    )
    for m in month_starts:
        income = float(grouped.at[m, "Entrada"]) if (m in grouped.index and "Entrada" in grouped.columns) else 0.0
        expense = float(grouped.at[m, "Saída"]) if (m in grouped.index and "Saída" in grouped.columns) else 0.0
        rows.append({"Mes_Ano": m, "Receitas": income, "Despesas": expense})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sankey: fontes de renda -> categorias de despesa
# ---------------------------------------------------------------------------

def sankey_data(df_transactions_period: pd.DataFrame,
                df_credit_card_period: pd.DataFrame) -> dict | None:
    """Monta dados para o gráfico Sankey (Plotly go.Sankey).

    Estrutura: cada categoria de Entrada alimenta o nó central "Receitas",
    que por sua vez se distribui entre cada categoria de Saída (banco +
    cartão). Se sobrar dinheiro, vai pro nó "Não Gasto". Categorias são
    ordenadas pelo valor (maiores primeiro) pra leitura ficar agradável.

    Retorna `None` se não houver dados.
    """
    if df_transactions_period.empty:
        return None

    income_by_cat = (
        df_transactions_period[df_transactions_period["Tipo"] == "Entrada"]
        .groupby("Categoria")["Valor"].sum()
    )
    expense_by_cat = (
        df_transactions_period[df_transactions_period["Tipo"] == "Saída"]
        .groupby("Categoria")["Valor"].sum()
    )
    if not df_credit_card_period.empty:
        card = df_credit_card_period.groupby("Categoria")["Valor"].sum()
        expense_by_cat = expense_by_cat.add(card, fill_value=0)

    incomes = income_by_cat[income_by_cat > 0].sort_values(ascending=False)
    expenses = expense_by_cat[expense_by_cat > 0].sort_values(ascending=False)
    total_income = float(incomes.sum())
    total_expense = float(expenses.sum())
    if total_income == 0 and total_expense == 0:
        return None

    central = "Receitas Totais"
    node_labels = list(incomes.index) + [central] + list(expenses.index)
    node_values = list(incomes.values) + [total_income] + list(expenses.values)

    surplus = total_income - total_expense
    if surplus > 0:
        node_labels.append("Não Gasto")
        node_values.append(surplus)

    central_idx = len(incomes)
    sources: list[int] = []
    targets: list[int] = []
    values: list[float] = []

    for i, value in enumerate(incomes.values):
        sources.append(i)
        targets.append(central_idx)
        values.append(float(value))
    for j, value in enumerate(expenses.values):
        sources.append(central_idx)
        targets.append(central_idx + 1 + j)
        values.append(float(value))
    if surplus > 0:
        sources.append(central_idx)
        targets.append(len(node_labels) - 1)
        values.append(float(surplus))

    return {
        "nodes": node_labels,
        "node_values": node_values,
        "sources": sources,
        "targets": targets,
        "values": values,
    }


# ---------------------------------------------------------------------------
# Auto-sugestão de categoria
# ---------------------------------------------------------------------------

def suggest_category(description: str, df_transactions: pd.DataFrame) -> str | None:
    """Sugere uma categoria baseada no histórico de descrições parecidas.

    Estratégia simples (e suficientemente útil): procura por descrições que
    contenham o trecho digitado (case-insensitive). Se achar, retorna a
    categoria mais frequente entre os matches. Sem match → None.
    """
    if not description or df_transactions.empty:
        return None
    needle = description.strip().lower()
    if len(needle) < 3:
        return None
    if "Descrição" not in df_transactions.columns:
        return None
    descs = df_transactions["Descrição"].fillna("").astype(str).str.lower()
    matches = df_transactions[descs.str.contains(needle, na=False)]
    if matches.empty:
        return None
    return matches["Categoria"].mode().iloc[0] if not matches["Categoria"].mode().empty else None


def cumulative_invested_at(df_transactions: pd.DataFrame,
                           until: pd.Timestamp) -> float:
    """Aportes − saques de investimento até `until` (inclusive).

    Usado para calcular o rendimento real em cada snapshot da posição:
    rendimento = valor_atual_no_dia − total_aportado_até_o_dia.
    """
    if df_transactions.empty:
        return 0.0
    df = df_transactions[df_transactions["Categoria"] == "Investimento"].copy()
    if df.empty:
        return 0.0
    df["Data_DT"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data_DT"])
    df = df[df["Data_DT"] <= until]
    aportes = float(df.loc[df["Tipo"] == "Saída", "Valor"].sum() or 0)
    saques = float(df.loc[df["Tipo"] == "Entrada", "Valor"].sum() or 0)
    return aportes - saques
