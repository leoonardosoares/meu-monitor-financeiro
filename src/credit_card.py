"""Regras específicas do cartão de crédito (faturas, parcelas)."""
from __future__ import annotations

from datetime import date

import pandas as pd


def invoice_month_for_purchase(purchase_date: date, closing_day: int) -> pd.Timestamp:
    """Retorna o Timestamp do MÊS de fatura em que a compra cai.

    A "Fatura de [mês]" cobre o ciclo que abre no `closing_day` desse mês
    e vai até o dia anterior ao `closing_day` do mês seguinte. Logo:

    - Compras com `day >= closing_day` entram na fatura do mês corrente
      (ex.: 08/06 com fechamento dia 8 → fatura de 06/2026).
    - Compras com `day < closing_day` entram na fatura do mês anterior,
      que ainda está aberta (ex.: 07/06 com fechamento dia 8 → fatura
      de 05/2026).
    """
    dt = pd.Timestamp(purchase_date)
    if dt.day < closing_day:
        return dt - pd.DateOffset(months=1)
    return dt


def installments_for_purchase(*, purchase_date: date, description: str,
                              category: str, total_amount: float,
                              installments: int, closing_day: int) -> list[dict]:
    """Gera as linhas de parcela para uma compra parcelada."""
    first_invoice = invoice_month_for_purchase(purchase_date, closing_day)
    per_installment = total_amount / installments
    rows = []
    for i in range(installments):
        invoice = (first_invoice + pd.DateOffset(months=i)).strftime("%m/%Y")
        rows.append({
            "Data Compra": purchase_date,
            "Mês da Fatura": invoice,
            "Descrição": description,
            "Categoria": category,
            "Parcela": f"{i + 1}/{installments}",
            "Valor": per_installment,
            "Status": "Pendente",
        })
    return rows


def upcoming_invoices(df_credit_card: pd.DataFrame, *, today: pd.Timestamp,
                      closing_day: int, months: int = 6) -> list[tuple[str, float]]:
    """Lista (mes, total_pendente) das próximas N faturas."""
    if df_credit_card.empty:
        pending_months: list[str] = []
    else:
        pending_months = (
            df_credit_card[df_credit_card["Status"] == "Pendente"]["Mês da Fatura"]
            .dropna().unique().tolist()
        )

    if pending_months:
        base = pd.to_datetime(pending_months, format="%m/%Y").min()
    elif today.day < closing_day:
        base = today - pd.DateOffset(months=1)
    else:
        base = today

    out: list[tuple[str, float]] = []
    for i in range(months):
        month = (base + pd.DateOffset(months=i)).strftime("%m/%Y")
        if df_credit_card.empty:
            total = 0.0
        else:
            mask = (df_credit_card["Mês da Fatura"] == month) & \
                   (df_credit_card["Status"] == "Pendente")
            total = float(df_credit_card.loc[mask, "Valor"].sum())
        out.append((month, total))
    return out


def invoice_phase(today: pd.Timestamp, closing_day: int,
                  due_day: int) -> str:
    """Devolve um sufixo legível sobre a fatura corrente."""
    if today.day < closing_day:
        return "Aberta"
    if closing_day <= today.day <= due_day:
        return "Fechada"
    return "Aberta"


def pending_total(df_credit_card: pd.DataFrame) -> float:
    if df_credit_card.empty:
        return 0.0
    return float(df_credit_card.loc[df_credit_card["Status"] == "Pendente", "Valor"].sum())


def pending_invoices(df_credit_card: pd.DataFrame) -> list[str]:
    if df_credit_card.empty:
        return []
    return sorted(
        df_credit_card.loc[df_credit_card["Status"] == "Pendente", "Mês da Fatura"]
        .dropna().unique().tolist()
    )


def pay_invoice(df_credit_card: pd.DataFrame, month: str) -> tuple[pd.DataFrame, float]:
    """Marca todas as parcelas pendentes de `month` como pagas.

    Retorna (df_atualizado, total_pago).
    """
    df = df_credit_card.copy()
    mask = (df["Mês da Fatura"] == month) & (df["Status"] == "Pendente")
    total = float(df.loc[mask, "Valor"].sum())
    df.loc[mask, "Status"] = "Pago"
    return df, total
