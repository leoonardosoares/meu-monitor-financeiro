"""Geração de insights em linguagem natural sobre as finanças do mês.

Estratégia: regras simples, sem ML. Cada gerador devolve `None` quando não
tem o que dizer. O agregador filtra os Nones e retorna a lista ordenada
por severidade.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.finance import pct_change, previous_month
from src.format import brl


Severity = Literal["positivo", "alerta", "critico", "neutro"]


@dataclass(frozen=True)
class Insight:
    severity: Severity
    message: str

    @property
    def icon(self) -> str:
        return {
            "positivo": "🟢",
            "alerta": "🟡",
            "critico": "🔴",
            "neutro": "🔵",
        }[self.severity]


def _expense_total(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(df.loc[df["Tipo"] == "Saída", "Valor"].sum())


def _income_total(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(df.loc[df["Tipo"] == "Entrada", "Valor"].sum())


def _expense_by_category(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    return df[df["Tipo"] == "Saída"].groupby("Categoria")["Valor"].sum()


# ---------------------------------------------------------------------------
# Geradores individuais
# ---------------------------------------------------------------------------

def _insight_total_expense_mom(curr: pd.DataFrame, prev: pd.DataFrame) -> Insight | None:
    curr_total = _expense_total(curr)
    prev_total = _expense_total(prev)
    delta = pct_change(curr_total, prev_total)
    if delta is None or abs(delta) < 5:  # ignora variações pequenas
        return None
    if delta < 0:
        return Insight("positivo",
                       f"Despesas caíram {abs(delta):.0f}% vs o mês anterior "
                       f"({brl(curr_total)} vs {brl(prev_total)}).")
    severity: Severity = "critico" if delta >= 30 else "alerta"
    return Insight(severity,
                   f"Despesas subiram {delta:.0f}% vs o mês anterior "
                   f"({brl(curr_total)} vs {brl(prev_total)}).")


def _insight_category_jump(curr: pd.DataFrame, prev: pd.DataFrame) -> Insight | None:
    curr_by_cat = _expense_by_category(curr)
    prev_by_cat = _expense_by_category(prev)
    if curr_by_cat.empty or prev_by_cat.empty:
        return None
    common = curr_by_cat.index.intersection(prev_by_cat.index)
    biggest_jump_pct = 0.0
    biggest_cat: str | None = None
    biggest_curr = 0.0
    biggest_prev = 0.0
    for cat in common:
        cur, prv = float(curr_by_cat[cat]), float(prev_by_cat[cat])
        if prv < 50 or cur < 50:  # ignora categorias irrisórias
            continue
        delta = pct_change(cur, prv)
        if delta is None:
            continue
        if delta > biggest_jump_pct:
            biggest_jump_pct = delta
            biggest_cat = cat
            biggest_curr = cur
            biggest_prev = prv
    if biggest_cat is None or biggest_jump_pct < 30:
        return None
    severity: Severity = "critico" if biggest_jump_pct >= 80 else "alerta"
    return Insight(severity,
                   f"**{biggest_cat}** subiu {biggest_jump_pct:.0f}% "
                   f"({brl(biggest_prev)} → {brl(biggest_curr)}).")


def _insight_budget_pressure(curr: pd.DataFrame,
                              df_budgets: pd.DataFrame,
                              df_card_period: pd.DataFrame) -> Insight | None:
    if df_budgets.empty:
        return None
    curr_bank = curr[(curr["Tipo"] == "Saída") &
                     (curr["Categoria"] != "Cartão de Crédito")] \
        .groupby("Categoria")["Valor"].sum()
    curr_card = (
        df_card_period.groupby("Categoria")["Valor"].sum()
        if not df_card_period.empty else pd.Series(dtype=float)
    )

    worst: tuple[str, float, float] | None = None
    for _, row in df_budgets.iterrows():
        cat = row["Categoria"]
        limit = float(row.get("Limite") or 0)
        if limit <= 0:
            continue
        spent = float(curr_bank.get(cat, 0.0)) + float(curr_card.get(cat, 0.0))
        ratio = spent / limit
        if ratio < 0.8:
            continue
        if worst is None or ratio > worst[2]:
            worst = (cat, spent, ratio)

    if worst is None:
        return None
    cat, spent, ratio = worst
    severity: Severity = "critico" if ratio >= 1.0 else "alerta"
    pct = ratio * 100
    if ratio >= 1.0:
        return Insight(severity,
                       f"Orçamento de **{cat}** estourou ({pct:.0f}% — {brl(spent)} gastos).")
    return Insight(severity,
                   f"**{cat}** já consumiu {pct:.0f}% do orçamento.")


def _insight_savings_rate(curr: pd.DataFrame) -> Insight | None:
    income = _income_total(curr)
    if income <= 0:
        return None
    expense = _expense_total(curr)
    rate = (income - expense) / income * 100
    if rate >= 20:
        return Insight("positivo",
                       f"Taxa de poupança do mês: **{rate:.0f}%** — ótimo trabalho.")
    if rate < 0:
        return Insight("critico",
                       f"Despesas maiores que receitas no período (déficit de {brl(expense - income)}).")
    if rate < 10:
        return Insight("alerta",
                       f"Taxa de poupança do mês: {rate:.0f}% (ideal ≥ 20%).")
    return None


# ---------------------------------------------------------------------------
# Agregador
# ---------------------------------------------------------------------------

def generate(*, df_transactions: pd.DataFrame, df_credit_card: pd.DataFrame,
             df_budgets: pd.DataFrame, selected_month: str) -> list[Insight]:
    """Retorna a lista de insights aplicáveis ao mês selecionado.

    Ignora se `selected_month` for "Todos os Meses" — comparações MoM e
    pressão de orçamento só fazem sentido sobre um mês específico.
    """
    if selected_month == "Todos os Meses":
        return []

    curr = df_transactions[df_transactions["Mes_Ano"] == selected_month]
    prev_month = previous_month(selected_month)
    prev = df_transactions[df_transactions["Mes_Ano"] == prev_month]
    card_period = (
        df_credit_card[df_credit_card["Mês da Fatura"] == selected_month]
        if not df_credit_card.empty else df_credit_card
    )

    candidates = [
        _insight_total_expense_mom(curr, prev),
        _insight_category_jump(curr, prev),
        _insight_budget_pressure(curr, df_budgets, card_period),
        _insight_savings_rate(curr),
    ]
    severity_order = {"critico": 0, "alerta": 1, "positivo": 2, "neutro": 3}
    return sorted(
        [i for i in candidates if i is not None],
        key=lambda x: severity_order.get(x.severity, 9),
    )
