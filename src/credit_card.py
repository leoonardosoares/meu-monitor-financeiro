"""Regras específicas do cartão de crédito (faturas, parcelas)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.config import DEFAULT_CARD_NAME
from src.dates import parse_dates


def invoice_month_for_purchase(purchase_date: date, closing_day: int) -> pd.Timestamp:
    """Retorna o Timestamp do MÊS de fatura em que a compra cai.

    A "Fatura de [mês]" é a que FECHA no `closing_day` desse mês — a
    mesma convenção que o banco usa. Ela cobre o ciclo que começa no dia
    seguinte ao fechamento do mês anterior e termina no fechamento deste.
    O vencimento pode cair no mês seguinte sem mudar o nome da fatura
    (ex.: fecha 30/08, vence 07/09, e ainda é a fatura de 08/2026).

    - Compras com `day <= closing_day` entram na fatura do mês corrente
      (22/08 com fechamento dia 30 → fatura de 08/2026).
    - Compras com `day > closing_day` já perderam o fechamento e caem na
      fatura seguinte (31/08 com fechamento dia 30 → fatura de 09/2026).
    """
    dt = pd.Timestamp(purchase_date)
    if dt.day > closing_day:
        return dt + pd.DateOffset(months=1)
    return dt


def _day_in_month(anchor: pd.Timestamp, day: int) -> pd.Timestamp:
    """`day` dentro do mês de `anchor`, limitado ao último dia real dele.

    Fechamento no dia 31 em mês de 30 dias vira dia 30, como no banco.
    """
    ultimo = anchor.days_in_month
    return pd.Timestamp(anchor.year, anchor.month, min(int(day), ultimo))


def invoice_dates(month: str, closing_day: int,
                  due_day: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Datas reais de fechamento e vencimento da fatura de `month`.

    O vencimento é sempre DEPOIS do fechamento — é o prazo para pagar o
    que já fechou. Então, quando o dia do vencimento é menor ou igual ao
    do fechamento, ele só pode cair no mês seguinte: fecha 30/08 e vence
    07/09, e isso não muda o nome da fatura, que continua sendo a de
    agosto. Quando o dia do vencimento é maior, os dois ficam no mesmo
    mês: fecha 08/09 e vence 15/09.
    """
    anchor = pd.Timestamp(f"{month[3:]}-{month[:2]}-01")
    fechamento = _day_in_month(anchor, closing_day)
    vencimento = _day_in_month(anchor, due_day)
    # A comparação é entre as datas já ajustadas ao tamanho do mês, e não
    # entre os números dos dias: fechamento 30 e vencimento 31 empatam em
    # junho, e o pagamento também tem que ir para o mês seguinte.
    if vencimento <= fechamento:
        vencimento = _day_in_month(anchor + pd.DateOffset(months=1), due_day)
    return fechamento, vencimento


def invoice_window(month: str, closing_day: int,
                   ) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Primeiro e último dia de compra que entram na fatura de `month`.

    A janela termina no fechamento do próprio mês e começa no dia
    seguinte ao fechamento do mês anterior. O vencimento não participa:
    ele é o prazo para PAGAR o que já fechou, não para continuar
    comprando dentro da fatura.
    """
    fim, _ = invoice_dates(month, closing_day, closing_day)
    anterior, _ = invoice_dates(
        (pd.Timestamp(f"{month[3:]}-{month[:2]}-01") - pd.DateOffset(months=1))
        .strftime("%m/%Y"),
        closing_day, closing_day,
    )
    return anterior + pd.Timedelta(days=1), fim


def _parcel_index(value) -> int:
    """Índice 0-based da parcela a partir do rótulo "i/n"."""
    try:
        return max(int(str(value).split("/")[0].strip()) - 1, 0)
    except (TypeError, ValueError):
        return 0


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
    else:
        base = invoice_month_for_purchase(today, closing_day)

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
    """Devolve um sufixo legível sobre a fatura corrente.

    "Fechada" = já fechou e ainda está dentro do prazo de pagamento.
    Quando o vencimento é anterior ao fechamento no calendário, o
    pagamento cai no mês seguinte (fecha dia 30, vence dia 7), então a
    janela dá a volta na virada do mês.
    """
    day = today.day
    if due_day > closing_day:          # fecha e vence no mesmo mês
        return "Fechada" if closing_day <= day <= due_day else "Aberta"
    return "Fechada" if (day > closing_day or day <= due_day) else "Aberta"


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
    """Coluna Cartão normalizada, com fallback para o cartão padrão.

    O `fillna` vem ANTES do `astype(str)` de propósito: no pandas 3 o
    `astype(str)` preserva NaN em vez de convertê-lo para a string "nan",
    então converter primeiro deixaria as compras antigas (sem cartão
    preenchido) fora de qualquer fatura.
    """
    if "Cartão" not in df.columns:
        return pd.Series([DEFAULT_CARD_NAME] * len(df), index=df.index)
    s = df["Cartão"].fillna(DEFAULT_CARD_NAME).astype(str).str.strip()
    return s.replace({
        "": DEFAULT_CARD_NAME, "nan": DEFAULT_CARD_NAME,
        "None": DEFAULT_CARD_NAME,
    })


def card_series(df: pd.DataFrame) -> pd.Series:
    """Versão pública de `_card_series`, para as telas filtrarem por cartão."""
    return _card_series(df)


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


def invoice_month_drift(df_credit_card: pd.DataFrame, df_cards: pd.DataFrame,
                        card: str, *,
                        only_pending: bool = True) -> dict[int, tuple[str, str]]:
    """Parcelas cujo "Mês da Fatura" gravado discorda do dia de fechamento.

    O mês da fatura é gravado na planilha no momento do lançamento. Se o
    dia de fechamento do cartão for corrigido depois, as compras antigas
    continuam com o rótulo antigo — esta função mostra quais mudariam.

    Devolve ``{índice da linha: (mês gravado, mês recalculado)}``, só com
    as linhas que realmente mudam.
    """
    if df_credit_card.empty or "Data Compra" not in df_credit_card.columns:
        return {}

    closing = int(card_settings(df_cards, card)["fechamento"])
    mask = _card_series(df_credit_card) == card
    if only_pending and "Status" in df_credit_card.columns:
        mask &= df_credit_card["Status"].astype(str).str.strip() == "Pendente"
    if not mask.any():
        return {}

    datas = parse_dates(df_credit_card.loc[mask, "Data Compra"])
    out: dict[int, tuple[str, str]] = {}
    for idx, compra in datas.items():
        if pd.isna(compra):
            continue
        parcela = df_credit_card.at[idx, "Parcela"] \
            if "Parcela" in df_credit_card.columns else "1/1"
        base = invoice_month_for_purchase(compra, closing)
        novo = (base + pd.DateOffset(months=_parcel_index(parcela))) \
            .strftime("%m/%Y")
        atual = str(df_credit_card.at[idx, "Mês da Fatura"]).strip()
        if novo != atual:
            out[idx] = (atual, novo)
    return out


def apply_invoice_month_drift(df_credit_card: pd.DataFrame,
                              df_payments: pd.DataFrame,
                              card: str,
                              drift: dict[int, tuple[str, str]],
                              ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Grava os meses recalculados e leva os pagamentos parciais junto.

    Um adiantamento aponta para o par (cartão, mês da fatura). Se as
    parcelas mudam de mês e o pagamento fica para trás, o dinheiro
    adiantado some da fatura e ela volta a parecer integralmente em
    aberto — por isso o mesmo remapeamento é aplicado aos dois.
    """
    df = df_credit_card.copy()
    for idx, (_antigo, novo) in drift.items():
        df.at[idx, "Mês da Fatura"] = novo

    pay = df_payments.copy()
    remap = {antigo: novo for antigo, novo in drift.values()}
    if remap and not pay.empty and \
            {"Cartão", "Mês da Fatura"}.issubset(pay.columns):
        alvo = pay["Cartão"].astype(str).str.strip() == str(card).strip()
        meses = pay.loc[alvo, "Mês da Fatura"].astype(str).str.strip()
        pay.loc[alvo, "Mês da Fatura"] = meses.map(lambda m: remap.get(m, m))
    return df, pay


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


def rename_card(df_cards: pd.DataFrame, df_credit_card: pd.DataFrame,
                df_payments: pd.DataFrame, old: str, new: str
                ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Renomeia um cartão e leva junto compras e pagamentos.

    Compras e pagamentos referenciam o cartão pelo nome; renomear só no
    cadastro deixaria a fatura órfã e o limite voltaria a parecer livre.
    Compras sem a coluna preenchida (lançadas antes do cadastro de cartões)
    contam como do cartão padrão e também acompanham a troca.
    """
    old, new = str(old).strip(), str(new).strip()

    cards = df_cards.copy()
    if not cards.empty and "Nome" in cards.columns:
        cards["Nome"] = cards["Nome"].astype(str).str.strip().replace({old: new})

    tx = df_credit_card.copy()
    if not tx.empty:
        atual = _card_series(tx)
        tx["Cartão"] = atual.replace({old: new})

    pay = df_payments.copy()
    if not pay.empty and "Cartão" in pay.columns:
        pay["Cartão"] = pay["Cartão"].astype(str).str.strip().replace({old: new})

    return cards, tx, pay


def delete_card(df_cards: pd.DataFrame, df_credit_card: pd.DataFrame,
                df_payments: pd.DataFrame, card: str, *,
                move_to: str | None = None
                ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Remove um cartão do cadastro.

    `move_to` transfere as compras e pagamentos para outro cartão; sem ele,
    compras e pagamentos são apagados junto. Em nenhum caso os lançamentos
    do fluxo de caixa são tocados.
    """
    card = str(card).strip()

    cards = df_cards.copy()
    if not cards.empty and "Nome" in cards.columns:
        cards = cards[cards["Nome"].astype(str).str.strip() != card]

    tx = df_credit_card.copy()
    pay = df_payments.copy()

    if move_to:
        destino = str(move_to).strip()
        if not tx.empty:
            tx["Cartão"] = _card_series(tx).replace({card: destino})
        if not pay.empty and "Cartão" in pay.columns:
            pay["Cartão"] = pay["Cartão"].astype(str).str.strip().replace(
                {card: destino}
            )
    else:
        if not tx.empty:
            tx = tx[_card_series(tx) != card]
        if not pay.empty and "Cartão" in pay.columns:
            pay = pay[pay["Cartão"].astype(str).str.strip() != card]

    return cards, tx, pay


def orphan_card_names(df_cards: pd.DataFrame,
                      df_credit_card: pd.DataFrame) -> list[str]:
    """Cartões que aparecem em compras mas não estão cadastrados."""
    if df_credit_card.empty:
        return []
    cadastrados = set()
    if not df_cards.empty and "Nome" in df_cards.columns:
        cadastrados = set(df_cards["Nome"].dropna().astype(str).str.strip())
    usados = set(_card_series(df_credit_card).unique())
    return sorted(n for n in usados if n and n not in cadastrados)
