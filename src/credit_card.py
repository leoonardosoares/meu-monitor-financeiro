"""Regras específicas do cartão de crédito (faturas, parcelas)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.config import DEFAULT_CARD_NAME


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


# ---------------------------------------------------------------------------
# Múltiplos cartões e pagamento parcial de fatura
# ---------------------------------------------------------------------------
#
# Modelo de fatura por (cartão, mês):
#
#   total       = todas as parcelas do mês
#   quitado     = parcelas já marcadas como "Pago" (baixa geral)
#   em aberto   = total - quitado
#   adiantado   = pagamentos parciais registrados para essa fatura
#   saldo       = em aberto - adiantado   <- o que ainda falta pagar
#
# O pagamento parcial existe porque liberar limite antes do fechamento é
# comum ("paguei R$ 25 para liberar limite"). Ele sai do caixa na hora, mas
# não fecha a fatura. Na baixa geral, os adiantamentos são absorvidos: as
# parcelas viram "Pago" e só o SALDO restante vai para o caixa, para o
# dinheiro não ser contado duas vezes.


@dataclass(frozen=True)
class Invoice:
    card: str
    month: str
    total: float
    settled: float      # parcelas já marcadas como Pago
    outstanding: float  # parcelas ainda não marcadas
    advances: float     # pagamentos parciais já feitos
    balance: float      # o que falta pagar

    @property
    def status(self) -> str:
        if self.outstanding <= 1e-6:
            return "Paga"
        if self.advances > 1e-6:
            return "Parcial"
        return "Aberta"

    @property
    def paid_pct(self) -> float:
        if self.outstanding <= 0:
            return 100.0
        return min(self.advances / self.outstanding * 100, 100.0)


def _card_series(df: pd.DataFrame) -> pd.Series:
    """Coluna Cartão normalizada, com fallback para o cartão padrão."""
    if "Cartão" not in df.columns:
        return pd.Series([DEFAULT_CARD_NAME] * len(df), index=df.index)
    s = df["Cartão"].astype(str).str.strip()
    return s.replace({"": DEFAULT_CARD_NAME, "nan": DEFAULT_CARD_NAME})


def list_card_names(df_cards: pd.DataFrame,
                    df_credit_card: pd.DataFrame) -> list[str]:
    """Cartões cadastrados, mais os que aparecem em compras sem cadastro."""
    names: list[str] = []
    if not df_cards.empty and "Nome" in df_cards.columns:
        names = [
            n for n in df_cards["Nome"].dropna().astype(str).str.strip()
            if n
        ]
    seen = set(names)
    if not df_credit_card.empty:
        for n in _card_series(df_credit_card).unique():
            if n and n not in seen:
                names.append(n)
                seen.add(n)
    return names


def card_settings(df_cards: pd.DataFrame, card: str, *,
                  default_limit: float = 2000.0,
                  default_closing: int = 8,
                  default_due: int = 15) -> dict:
    """Limite e datas de um cartão, com defaults quando não cadastrado."""
    out = {
        "limite": default_limit,
        "fechamento": default_closing,
        "vencimento": default_due,
        "instituicao": "",
    }
    if df_cards.empty or "Nome" not in df_cards.columns:
        return out
    match = df_cards[df_cards["Nome"].astype(str).str.strip() == str(card).strip()]
    if match.empty:
        return out
    row = match.iloc[0]
    for key, col, cast in (
        ("limite", "Limite", float),
        ("fechamento", "Dia Fechamento", int),
        ("vencimento", "Dia Vencimento", int),
    ):
        raw = pd.to_numeric(row.get(col), errors="coerce")
        if pd.notna(raw):
            out[key] = cast(raw)
    out["instituicao"] = str(row.get("Instituição") or "")
    return out


def _advances_for(df_payments: pd.DataFrame, card: str, month: str) -> float:
    if df_payments.empty:
        return 0.0
    needed = {"Cartão", "Mês da Fatura", "Valor"}
    if not needed.issubset(df_payments.columns):
        return 0.0
    mask = (
        (df_payments["Cartão"].astype(str).str.strip() == str(card).strip())
        & (df_payments["Mês da Fatura"].astype(str).str.strip() == str(month).strip())
    )
    valores = pd.to_numeric(df_payments.loc[mask, "Valor"], errors="coerce")
    return float(valores.fillna(0).sum())


def invoice_for(df_credit_card: pd.DataFrame, df_payments: pd.DataFrame,
                card: str, month: str) -> Invoice:
    """Situação da fatura de um cartão num mês."""
    if df_credit_card.empty:
        return Invoice(card, month, 0.0, 0.0, 0.0, 0.0, 0.0)
    cards = _card_series(df_credit_card)
    mask = (
        (cards == str(card).strip())
        & (df_credit_card["Mês da Fatura"].astype(str).str.strip()
           == str(month).strip())
    )
    subset = df_credit_card[mask]
    valores = pd.to_numeric(subset.get("Valor"), errors="coerce").fillna(0) \
        if not subset.empty else pd.Series(dtype=float)
    total = float(valores.sum())
    if subset.empty:
        settled = 0.0
    else:
        pago_mask = subset["Status"].astype(str).str.strip() == "Pago"
        settled = float(valores[pago_mask.values].sum())
    outstanding = total - settled
    advances = _advances_for(df_payments, card, month)
    return Invoice(
        card=str(card).strip(), month=str(month).strip(), total=total,
        settled=settled, outstanding=outstanding, advances=advances,
        balance=max(outstanding - advances, 0.0),
    )


def open_invoices(df_credit_card: pd.DataFrame, df_payments: pd.DataFrame, *,
                  card: str | None = None) -> list[Invoice]:
    """Faturas com parcelas em aberto, ordenadas por mês."""
    if df_credit_card.empty:
        return []
    cards = _card_series(df_credit_card)
    df = df_credit_card.assign(_card=cards)
    if card is not None:
        df = df[df["_card"] == str(card).strip()]
    if df.empty:
        return []
    pendentes = df[df["Status"].astype(str).str.strip() != "Pago"]
    if pendentes.empty:
        return []
    pares = pendentes[["_card", "Mês da Fatura"]].drop_duplicates()
    out = [
        invoice_for(df_credit_card, df_payments, row["_card"],
                    row["Mês da Fatura"])
        for _, row in pares.iterrows()
    ]
    return sorted(
        out, key=lambda i: pd.to_datetime(i.month, format="%m/%Y",
                                          errors="coerce"),
    )


def available_limit(df_cards: pd.DataFrame, df_credit_card: pd.DataFrame,
                    df_payments: pd.DataFrame, card: str) -> tuple[float, float]:
    """(limite total, limite disponível) de um cartão.

    O limite volta conforme a fatura é paga — inclusive parcialmente, que é
    justamente o motivo de alguém adiantar R$ 25 antes do fechamento.
    """
    settings = card_settings(df_cards, card)
    usado = sum(i.balance for i in open_invoices(df_credit_card, df_payments,
                                                 card=card))
    return settings["limite"], settings["limite"] - usado


def outstanding_for_month(df_credit_card: pd.DataFrame,
                          df_payments: pd.DataFrame, month: str, *,
                          card: str | None = None) -> float:
    """Saldo a pagar de um mês, somando cartões (ou de um só).

    É o número que o Dashboard abate na projeção do próximo mês: já
    desconta os adiantamentos, porque esse dinheiro saiu da conta.
    """
    invoices = open_invoices(df_credit_card, df_payments, card=card)
    return sum(i.balance for i in invoices if i.month == str(month).strip())


def settle_invoice(df_credit_card: pd.DataFrame, df_payments: pd.DataFrame,
                   card: str, month: str
                   ) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Dá baixa geral numa fatura.

    Retorna (compras atualizadas, pagamentos atualizados, valor a lançar no
    caixa). O valor lançado é apenas o SALDO — os adiantamentos já saíram da
    conta quando foram feitos, e seus registros são absorvidos aqui para não
    serem contados de novo.
    """
    invoice = invoice_for(df_credit_card, df_payments, card, month)

    df_tx = df_credit_card.copy()
    if not df_tx.empty:
        cards = _card_series(df_tx)
        mask = (
            (cards == invoice.card)
            & (df_tx["Mês da Fatura"].astype(str).str.strip() == invoice.month)
            & (df_tx["Status"].astype(str).str.strip() != "Pago")
        )
        df_tx.loc[mask, "Status"] = "Pago"

    df_pay = df_payments.copy()
    if not df_pay.empty and {"Cartão", "Mês da Fatura"}.issubset(df_pay.columns):
        absorver = (
            (df_pay["Cartão"].astype(str).str.strip() == invoice.card)
            & (df_pay["Mês da Fatura"].astype(str).str.strip() == invoice.month)
        )
        df_pay = df_pay[~absorver]

    return df_tx, df_pay, invoice.balance
