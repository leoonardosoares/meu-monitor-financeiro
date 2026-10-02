"""Regras de calendário e cadastro do cartão de crédito.

O que sobrou aqui é o que o livro de faturas (`card_book.py`) usa como
peça: em que fatura uma compra cai, as datas de uma fatura pelo
cadastro, a leitura tolerante de rótulos e colunas da planilha, e o
cadastro de cartões. Montar fatura, decidir situação e somar valores é
trabalho do livro — antes havia aqui um segundo motor fazendo o mesmo
por outro caminho, e os dois davam números diferentes.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.config import DEFAULT_CARD_NAME
from src.dates import month_label, parse_month_label


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
    return pd.Timestamp(
        anchor.year, anchor.month, min(max(int(day), 1), ultimo))


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
    anchor = parse_month_label(month)
    if anchor is None:
        raise ValueError(f"mês de fatura ilegível: {month!r}")
    fechamento = _day_in_month(anchor, closing_day)

    # Quem decide se o pagamento é no mês seguinte é o par de dias CRU, não
    # as datas já cortadas pelo tamanho do mês. Comparar as datas cortadas
    # fazia fechamento 30 / vencimento 31 empatar em abril e o vencimento
    # pular para maio — abril ficava sem fatura nenhuma e maio com duas.
    if int(due_day) <= int(closing_day):
        return fechamento, _day_in_month(
            anchor + pd.DateOffset(months=1), due_day)

    vencimento = _day_in_month(anchor, due_day)
    if vencimento <= fechamento:
        # Os dois dias caíram no mesmo fim de mês curto. A intenção
        # cadastrada é pagar no próprio mês, então quem recua é o
        # fechamento — empurrar o vencimento mudaria o mês da fatura.
        fechamento = vencimento - pd.Timedelta(days=1)
    return fechamento, vencimento


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


def _month_key(value) -> str:
    """Chave canônica de um rótulo de fatura, para casar os dois lados.

    Compras, adiantamentos e o cadastro são digitados em momentos
    diferentes, então o mesmo mês aparece como "09/2026", " 09/2026 " ou
    "9/2026". Casar por texto cru fazia o adiantamento não encontrar a
    fatura: o dinheiro já tinha saído do banco e a dívida continuava
    cheia. O que não for legível cai no texto sem espaços, para não
    fundir rótulos distintos por acidente.
    """
    ts = parse_month_label(value)
    return month_label(ts) if ts is not None else str(value).strip()


def _month_series(df: pd.DataFrame) -> pd.Series:
    """Coluna "Mês da Fatura" canonizada; vazia se a coluna não existir."""
    if "Mês da Fatura" not in df.columns:
        return pd.Series("", index=df.index, dtype=object)
    return df["Mês da Fatura"].map(_month_key)


def _is_settled(df: pd.DataFrame) -> pd.Series:
    """Máscara das parcelas já quitadas.

    A comparação é sem diferenciar maiúsculas porque a planilha é editada
    à mão: um "pago" minúsculo era lido como parcela em aberto e a dívida
    reaparecia no mês seguinte, já tendo saído da conta.
    """
    if "Status" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Status"].astype(str).str.strip().str.casefold() == "pago"


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
    """Limite e datas de um cartão, com defaults quando não cadastrado.

    Um dia fora de 1..31 é tratado como não cadastrado, não como valor
    válido: `pd.Timestamp(ano, mes, 0)` levanta exceção, e essa exceção
    era capturada lá na frente como "mês da fatura ilegível" — mensagem
    que culpa o campo errado enquanto todas as faturas do cartão somem
    da conta. Caindo no default, `has_registered_dates` marca o cartão
    como estimado e a tela avisa no lugar certo.
    """
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
    raw_limite = pd.to_numeric(row.get("Limite"), errors="coerce")
    if pd.notna(raw_limite):
        out["limite"] = float(raw_limite)
    for key, col in (("fechamento", "Dia Fechamento"),
                     ("vencimento", "Dia Vencimento")):
        raw = pd.to_numeric(row.get(col), errors="coerce")
        if pd.notna(raw) and 1 <= int(raw) <= 31:
            out[key] = int(raw)
    out["instituicao"] = str(row.get("Instituição") or "")
    return out


# ---------------------------------------------------------------------------
# Agenda de pagamento: qual fatura sai da conta em qual mês
# ---------------------------------------------------------------------------
#
# Somar faturas pelo RÓTULO do mês só funciona quando todos os cartões têm o
# mesmo ciclo. Com fechamentos diferentes, a fatura paga em outubro chama-se
# "10/2026" num cartão que fecha dia 8 e "09/2026" num que fecha dia 30. Quem
# manda é a data de vencimento, e ela depende do cadastro de cada cartão.


def has_registered_dates(df_cards: pd.DataFrame, card: str) -> bool:
    """Se o cartão tem fechamento E vencimento realmente cadastrados.

    `card_settings` preenche default por CAMPO: um cartão cadastrado com
    fechamento 30 e vencimento em branco recebe 15 sem reclamar, e a
    fatura muda de mês inteiro em silêncio. `orphan_card_names` não pega
    esse caso, porque o cartão está cadastrado — só que pela metade.
    """
    if df_cards.empty or "Nome" not in df_cards.columns:
        return False
    match = df_cards[df_cards["Nome"].astype(str).str.strip() == str(card).strip()]
    if match.empty:
        return False
    row = match.iloc[0]
    for col in ("Dia Fechamento", "Dia Vencimento"):
        raw = pd.to_numeric(row.get(col), errors="coerce")
        if pd.isna(raw) or not 1 <= int(raw) <= 31:
            return False
    return True


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
