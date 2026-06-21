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

from src.config import TRANSFER_CATEGORIES


@dataclass(frozen=True)
class WealthSummary:
    """Resumo do patrimônio em um instante."""
    total_income: float            # entradas no período filtrado
    total_expense: float           # saídas no período filtrado
    bank_balance: float            # saldo bancário (entradas - saídas globais)
    invested: float                # aportes - saques de investimento
    net_worth: float               # bank_balance + invested


def _sum_by(df: pd.DataFrame, *, tipo: str | None = None,
            categoria: str | None = None,
            exclude_categorias: list[str] | None = None) -> float:
    if df.empty:
        return 0.0
    mask = pd.Series(True, index=df.index)
    if tipo is not None:
        mask &= df["Tipo"] == tipo
    if categoria is not None:
        mask &= df["Categoria"] == categoria
    if exclude_categorias:
        mask &= ~df["Categoria"].isin(exclude_categorias)
    valor = df.loc[mask, "Valor"]
    return float(valor.sum()) if not valor.empty else 0.0


def _drop_transfers(df: pd.DataFrame) -> pd.DataFrame:
    """Remove movimentações de transferência (aporte/saque de investimento)."""
    if df.empty or "Categoria" not in df.columns:
        return df
    return df[~df["Categoria"].isin(TRANSFER_CATEGORIES)]


def compute_wealth(df_all: pd.DataFrame, df_period: pd.DataFrame) -> WealthSummary:
    """Calcula KPIs principais.

    `df_all` = histórico completo (usado para saldo bancário e investido).
    `df_period` = subset filtrado pelo mês selecionado (usado para
    receitas/despesas do período).

    Aporte / saque de investimento NÃO são receita ou despesa de verdade:
    é dinheiro indo de um bucket pra outro do mesmo dono. Por isso, são
    excluídos dos KPIs `total_income` e `total_expense` do período.
    O `bank_balance` continua somando tudo (incluindo aportes/saques)
    porque eles afetam o saldo da conta corrente.
    """
    income_global = _sum_by(df_all, tipo="Entrada")
    expense_global = _sum_by(df_all, tipo="Saída")
    bank_balance = income_global - expense_global

    aportes = _sum_by(df_all, tipo="Saída", categoria="Investimento")
    saques = _sum_by(df_all, tipo="Entrada", categoria="Investimento")
    invested = aportes - saques

    return WealthSummary(
        total_income=_sum_by(
            df_period, tipo="Entrada", exclude_categorias=TRANSFER_CATEGORIES,
        ),
        total_expense=_sum_by(
            df_period, tipo="Saída", exclude_categorias=TRANSFER_CATEGORIES,
        ),
        bank_balance=bank_balance,
        invested=invested,
        net_worth=bank_balance + invested,
    )


def expenses_by_category(df_transactions: pd.DataFrame,
                         df_credit_card: pd.DataFrame,
                         *, exclude: list[str] | None = None) -> pd.DataFrame:
    """Soma despesas (banco + cartão) agrupadas por categoria.

    Sempre exclui categorias de transferência (Investimento), porque
    aportes não são despesas reais. `exclude` adicional pode ser passado
    para casos como "Despesas Variáveis" (ignora fixos como Aluguel).
    """
    expenses_bank = (
        df_transactions[df_transactions["Tipo"] == "Saída"][["Categoria", "Valor"]]
        if not df_transactions.empty else pd.DataFrame(columns=["Categoria", "Valor"])
    )
    expenses_card = (
        df_credit_card[["Categoria", "Valor"]]
        if not df_credit_card.empty else pd.DataFrame(columns=["Categoria", "Valor"])
    )
    combined = pd.concat([expenses_bank, expenses_card])
    all_exclude = list(TRANSFER_CATEGORIES) + list(exclude or [])
    combined = combined[~combined["Categoria"].isin(all_exclude)]
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
    """Despesa mensal média dos últimos N meses (com data válida).

    Aportes/saques de investimento NÃO entram (são transferências).
    """
    if df_transactions.empty:
        return 0.0
    df = _drop_transfers(df_transactions)
    df = df[df["Tipo"] == "Saída"].copy()
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
    df = _drop_transfers(df_transactions_period)
    df = df[df["Tipo"] == "Saída"].copy()
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
        _drop_transfers(df_transactions)
        .groupby(["Mes_Ano", "Tipo"])["Valor"].sum().unstack(fill_value=0)
    )
    for m in month_starts:
        income = float(grouped.at[m, "Entrada"]) if (m in grouped.index and "Entrada" in grouped.columns) else 0.0
        expense = float(grouped.at[m, "Saída"]) if (m in grouped.index and "Saída" in grouped.columns) else 0.0
        rows.append({"Mes_Ano": m, "Receitas": income, "Despesas": expense})
    return pd.DataFrame(rows)


def monthly_investment_contributions(df_transactions: pd.DataFrame, *,
                                      months: int = 12,
                                      today: date | None = None) -> pd.DataFrame:
    """Aportes (Tipo=Saída) e saques (Tipo=Entrada) de Investimento por mês.

    Retorna DataFrame com Mes_Ano, Aportes, Saques, Liquido (Aportes − Saques).
    Inclui os últimos N meses, preenchendo com zero os meses sem movimentação.
    """
    today = today or date.today()
    anchor = pd.Timestamp(year=today.year, month=today.month, day=1)
    month_starts = [
        (anchor - pd.DateOffset(months=i)).strftime("%m/%Y")
        for i in range(months)
    ][::-1]

    empty = pd.DataFrame([
        {"Mes_Ano": m, "Aportes": 0.0, "Saques": 0.0, "Liquido": 0.0}
        for m in month_starts
    ])
    if df_transactions.empty or "Mes_Ano" not in df_transactions.columns:
        return empty
    inv = df_transactions[df_transactions["Categoria"] == "Investimento"]
    if inv.empty:
        return empty

    grouped = inv.groupby(["Mes_Ano", "Tipo"])["Valor"].sum().unstack(fill_value=0)
    rows = []
    for m in month_starts:
        aportes = float(grouped.at[m, "Saída"]) \
            if m in grouped.index and "Saída" in grouped.columns else 0.0
        saques = float(grouped.at[m, "Entrada"]) \
            if m in grouped.index and "Entrada" in grouped.columns else 0.0
        rows.append({
            "Mes_Ano": m, "Aportes": aportes, "Saques": saques,
            "Liquido": aportes - saques,
        })
    return pd.DataFrame(rows)


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


def budget_status(df_budgets: pd.DataFrame,
                  df_transactions_period: pd.DataFrame,
                  df_credit_card_period: pd.DataFrame) -> pd.DataFrame:
    """Para cada categoria com Limite > 0, devolve gasto, limite e %.

    Retorna DataFrame ordenado por % desc com:
    Categoria, Gasto, Limite, Pct, Status ("ok" | "alerta" | "estourado").
    Categorias com Limite <= 0 ou NaN são ignoradas.
    """
    if df_budgets.empty:
        return pd.DataFrame(columns=["Categoria", "Gasto", "Limite", "Pct", "Status"])

    if df_transactions_period.empty:
        bank_by_cat = pd.Series(dtype=float)
    else:
        bank = df_transactions_period[
            (df_transactions_period["Tipo"] == "Saída") &
            (df_transactions_period["Categoria"] != "Cartão de Crédito")
        ]
        bank_by_cat = (
            bank.groupby("Categoria")["Valor"].sum() if not bank.empty
            else pd.Series(dtype=float)
        )

    if df_credit_card_period.empty:
        card_by_cat = pd.Series(dtype=float)
    else:
        card_by_cat = df_credit_card_period.groupby("Categoria")["Valor"].sum()

    rows = []
    for _, row in df_budgets.iterrows():
        category = row.get("Categoria")
        limit_raw = row.get("Limite")
        try:
            limit = float(limit_raw) if pd.notna(limit_raw) else 0.0
        except (TypeError, ValueError):
            continue
        if limit <= 0 or not isinstance(category, str) or not category.strip():
            continue
        spent = float(bank_by_cat.get(category, 0.0)) + \
                float(card_by_cat.get(category, 0.0))
        pct = (spent / limit) * 100
        if pct >= 100:
            status = "estourado"
        elif pct >= 80:
            status = "alerta"
        else:
            status = "ok"
        rows.append({
            "Categoria": category, "Gasto": spent, "Limite": limit,
            "Pct": pct, "Status": status,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Pct", ascending=False).reset_index(drop=True)
    return df


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
