"""Cálculos financeiros puros.

Funções aqui não tocam em Streamlit nem em I/O — só transformam DataFrames
e retornam números/DataFrames. Isso permite testar e reusar em qualquer
contexto.
"""
from __future__ import annotations

from dataclasses import dataclass

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
