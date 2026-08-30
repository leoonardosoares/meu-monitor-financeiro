"""Página: Cartão de Crédito — múltiplos cartões, faturas e pagamentos."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import components, credit_card as cc, repository
from src.config import Colors, ConfigKeys, DEFAULT_CARD_NAME
from src.format import brl
from src.sidebar import ALL_MONTHS

_ALL_CARDS = "Todos os cartões"


def render(*, df_credit_card: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           categories: list[str], selected_month: str) -> None:
    components.page_header(
        "Cartão de Crédito",
        "Cadastre seus cartões, acompanhe cada fatura separadamente e pague "
        "parcial ou integralmente.",
    )

    df_cards = repository.load_cards()
    df_payments = repository.load_card_payments()
    names = cc.list_card_names(df_cards, df_credit_card)

    if not names:
        _first_card_setup()
        return

    escolha = st.selectbox("Cartão:", [_ALL_CARDS] + names)
    card = None if escolha == _ALL_CARDS else escolha
    st.divider()

    if card is None:
        _all_cards_overview(df_cards, df_credit_card, df_payments, names)
    else:
        _single_card_view(df_cards, df_credit_card, df_payments, card)

    st.divider()
    _payment_section(df_credit_card, df_payments, names, card)
    st.divider()
    _purchase_form(df_cards, df_credit_card, names, categories, card)
    st.divider()
    _cards_registry(df_cards, names)
    st.divider()
    _extract_section(df_credit_card, df_credit_card_period, names,
                     selected_month, card)


# ---------------------------------------------------------------------------
# Primeiro acesso
# ---------------------------------------------------------------------------

def _first_card_setup() -> None:
    st.info(
        "Nenhum cartão cadastrado ainda. Cadastre o primeiro abaixo — as "
        "configurações que você já usava viram os valores iniciais."
    )
    with st.form("first_card"):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome do cartão", value=DEFAULT_CARD_NAME,
                             placeholder="Ex.: Nubank")
        inst = c2.text_input("Instituição", placeholder="Ex.: Nu Pagamentos")
        c3, c4, c5 = st.columns(3)
        limite = c3.number_input(
            "Limite (R$)", min_value=0.0, step=100.0,
            value=repository.load_config(ConfigKeys.LIMITE_CARTAO, 2000.0),
        )
        fech = c4.number_input(
            "Dia de fechamento", min_value=1, max_value=31, step=1,
            value=int(repository.load_config(ConfigKeys.DIA_FECHAMENTO, 8)),
        )
        venc = c5.number_input(
            "Dia de vencimento", min_value=1, max_value=31, step=1,
            value=int(repository.load_config(ConfigKeys.DIA_VENCIMENTO, 15)),
        )
        if st.form_submit_button("Cadastrar cartão"):
            if not nome.strip():
                st.error("Informe um nome.")
            else:
                repository.save_cards(pd.DataFrame([{
                    "Nome": nome.strip(), "Instituição": inst.strip(),
                    "Limite": limite, "Dia Fechamento": fech,
                    "Dia Vencimento": venc,
                }]))
                st.success(f"'{nome.strip()}' cadastrado.")
                st.rerun()


# ---------------------------------------------------------------------------
# Visões
# ---------------------------------------------------------------------------

def _all_cards_overview(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                        df_pay: pd.DataFrame, names: list[str]) -> None:
    st.subheader("Visão consolidada")

    total_limite = total_disp = total_saldo = 0.0
    rows = []
    for name in names:
        limite, disp = cc.available_limit(df_cards, df_tx, df_pay, name)
        abertas = cc.open_invoices(df_tx, df_pay, card=name)
        saldo = sum(i.balance for i in abertas)
        adiantado = sum(i.advances for i in abertas)
        total_limite += limite
        total_disp += disp
        total_saldo += saldo
        rows.append({
            "Cartão": name,
            "Limite": limite,
            "Em aberto": saldo,
            "Já adiantado": adiantado,
            "Disponível": disp,
            "Uso": (saldo / limite * 100) if limite else 0.0,
            "Faturas abertas": len(abertas),
        })

    c1, c2, c3 = st.columns(3)
    c1.metric("Limite total", brl(total_limite))
    c2.metric("Em aberto", brl(total_saldo),
              delta=f"{len(names)} cartão(ões)", delta_color="off")
    c3.metric("Disponível", brl(total_disp),
              delta_color="normal" if total_disp >= 0 else "inverse")

    df = pd.DataFrame(rows)
    display = df.copy()
    for col in ("Limite", "Em aberto", "Já adiantado", "Disponível"):
        display[col] = display[col].apply(brl)
    display["Uso"] = df["Uso"].apply(lambda v: f"{v:.0f}%")
    st.dataframe(display, hide_index=True, use_container_width=True)

    st.markdown("**Próximas faturas por cartão**")
    abertas = cc.open_invoices(df_tx, df_pay)
    if not abertas:
        st.success("Nenhuma fatura em aberto.")
        return
    inv_rows = [{
        "Cartão": i.card, "Mês": i.month, "Total": brl(i.total),
        "Adiantado": brl(i.advances), "Falta pagar": brl(i.balance),
        "Status": i.status,
    } for i in abertas]
    st.dataframe(pd.DataFrame(inv_rows), hide_index=True,
                 use_container_width=True)


def _single_card_view(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                      df_pay: pd.DataFrame, card: str) -> None:
    settings = cc.card_settings(df_cards, card)
    limite, disp = cc.available_limit(df_cards, df_tx, df_pay, card)
    abertas = cc.open_invoices(df_tx, df_pay, card=card)
    saldo = sum(i.balance for i in abertas)

    titulo = card + (f" · {settings['instituicao']}"
                     if settings["instituicao"] else "")
    st.subheader(titulo)
    st.caption(
        f"Fecha todo dia {settings['fechamento']} · "
        f"vence dia {settings['vencimento']}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Limite", brl(limite))
    c2.metric("Em aberto", brl(saldo))
    c3.metric("Disponível", brl(disp),
              delta_color="normal" if disp >= 0 else "inverse")
    uso = (saldo / limite * 100) if limite else 0.0
    c4.metric("Uso do limite", f"{uso:.0f}%",
              delta="acima de 80%" if uso > 80 else "confortável",
              delta_color="inverse" if uso > 80 else "normal")
    if limite > 0:
        st.progress(min(uso / 100, 1.0))

    if not abertas:
        st.success("Nenhuma fatura em aberto neste cartão.")
        return

    st.markdown("**Faturas em aberto**")
    for i in abertas:
        icone = {"Aberta": "🔵", "Parcial": "🟡", "Paga": "🟢"}[i.status]
        with st.expander(
            f"{icone} {i.month} — falta pagar {brl(i.balance)} "
            f"(total {brl(i.total)})"
        ):
            m1, m2, m3 = st.columns(3)
            m1.metric("Total da fatura", brl(i.total))
            m2.metric("Já adiantado", brl(i.advances))
            m3.metric("Falta pagar", brl(i.balance))
            if i.advances > 0:
                st.progress(min(i.paid_pct / 100, 1.0))
                st.caption(f"{i.paid_pct:.0f}% da fatura já foi adiantado.")
            compras = _invoice_lines(df_tx, i.card, i.month)
            if not compras.empty:
                st.dataframe(compras, hide_index=True,
                             use_container_width=True)


def _invoice_lines(df_tx: pd.DataFrame, card: str, month: str) -> pd.DataFrame:
    if df_tx.empty:
        return pd.DataFrame()
    cards = df_tx["Cartão"].astype(str).str.strip() \
        if "Cartão" in df_tx.columns else pd.Series(DEFAULT_CARD_NAME, index=df_tx.index)
    mask = (cards == card) & (df_tx["Mês da Fatura"].astype(str).str.strip() == month)
    cols = [c for c in ("Data Compra", "Descrição", "Categoria", "Parcela",
                        "Valor", "Status") if c in df_tx.columns]
    out = df_tx.loc[mask, cols].copy()
    if "Valor" in out.columns:
        out["Valor"] = out["Valor"].apply(brl)
    return out


# ---------------------------------------------------------------------------
# Pagamentos
# ---------------------------------------------------------------------------

def _payment_section(df_tx: pd.DataFrame, df_pay: pd.DataFrame,
                     names: list[str], card: str | None) -> None:
    st.subheader("Pagar fatura")
    abertas = cc.open_invoices(df_tx, df_pay, card=card)
    if not abertas:
        st.success("Nada a pagar por aqui.")
        return

    rotulos = {
        f"{i.card} · {i.month} — falta {brl(i.balance)}": i for i in abertas
    }
    escolhido = st.selectbox("Fatura:", list(rotulos))
    inv = rotulos[escolhido]

    aba_parcial, aba_total = st.tabs(
        ["💵 Pagamento parcial", "✅ Dar baixa total"]
    )

    with aba_parcial:
        st.caption(
            "Para adiantar um valor e liberar limite antes do fechamento. A "
            "fatura continua aberta e o valor sai do seu saldo na hora."
        )
        with st.form("partial_payment", clear_on_submit=True):
            c1, c2 = st.columns(2)
            data_pg = c1.date_input("Data", value=date.today(),
                                    format="DD/MM/YYYY")
            valor = c2.number_input(
                "Valor a pagar (R$)", min_value=0.01,
                max_value=float(inv.balance) if inv.balance > 0 else None,
                value=min(25.0, float(inv.balance)) if inv.balance > 0 else 0.01,
                format="%.2f",
            )
            obs = st.text_input("Observação (opcional)",
                                placeholder="Ex.: liberar limite")
            if st.form_submit_button("Registrar pagamento parcial"):
                repository.append_card_payment({
                    "Data": data_pg, "Cartão": inv.card,
                    "Mês da Fatura": inv.month, "Valor": valor,
                    "Observação": obs.strip(),
                })
                repository.append_transaction({
                    "Data": data_pg,
                    "Descrição": f"Pagamento parcial {inv.card} ({inv.month})",
                    "Categoria": "Cartão de Crédito",
                    "Valor": valor, "Tipo": "Saída",
                })
                st.success(
                    f"{brl(valor)} pagos em {inv.card}. "
                    f"Faltam {brl(inv.balance - valor)} nessa fatura."
                )
                st.rerun()

    with aba_total:
        st.caption(
            "Quita a fatura inteira. Só o **saldo restante** vai para o fluxo "
            "de caixa — o que você já adiantou não é cobrado de novo."
        )
        c1, c2 = st.columns(2)
        c1.metric("Falta pagar", brl(inv.balance))
        c2.metric("Já adiantado", brl(inv.advances))
        data_baixa = st.date_input("Data do pagamento", value=date.today(),
                                   format="DD/MM/YYYY", key="settle_date")
        if st.button("✅ Confirmar baixa total", type="primary"):
            novo_tx, novo_pay, a_lancar = cc.settle_invoice(
                df_tx, df_pay, inv.card, inv.month,
            )
            repository.save_credit_card(novo_tx)
            repository.save_card_payments(novo_pay)
            if a_lancar > 0:
                repository.append_transaction({
                    "Data": data_baixa,
                    "Descrição": f"Fatura {inv.card} ({inv.month})",
                    "Categoria": "Cartão de Crédito",
                    "Valor": a_lancar, "Tipo": "Saída",
                })
            st.success(
                f"Fatura de {inv.card} ({inv.month}) quitada. "
                f"Lançado no caixa: {brl(a_lancar)}."
            )
            st.rerun()

    if not df_pay.empty:
        with st.expander("Histórico de pagamentos parciais"):
            hist = df_pay.copy()
            if card:
                hist = hist[hist["Cartão"].astype(str).str.strip() == card]
            if hist.empty:
                st.caption("Nenhum pagamento parcial registrado.")
            else:
                with st.form("edit_card_payments"):
                    edited = st.data_editor(
                        hist, num_rows="dynamic", hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Cartão": st.column_config.SelectboxColumn(
                                "Cartão", options=names, required=True),
                            "Valor": st.column_config.NumberColumn(
                                "Valor (R$)", min_value=0.01, format="%.2f"),
                        },
                    )
                    if st.form_submit_button("💾 Salvar pagamentos"):
                        if hist.equals(edited):
                            st.info("Nada a salvar — sem alterações.")
                        else:
                            untouched = df_pay.drop(hist.index, errors="ignore")
                            repository.save_card_payments(pd.concat(
                                [untouched, edited], ignore_index=True))
                            st.success("Pagamentos atualizados.")
                            st.rerun()
                st.caption(
                    "Apagar um pagamento aqui **não** remove o lançamento "
                    "correspondente em Entradas e Saídas."
                )


# ---------------------------------------------------------------------------
# Lançamento de compras
# ---------------------------------------------------------------------------

def _purchase_form(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                   names: list[str], categories: list[str],
                   card: str | None) -> None:
    st.subheader("Lançar compra")
    with st.form("new_card_purchase", clear_on_submit=True):
        c1, c2 = st.columns([1, 2])
        cartao = c1.selectbox(
            "Cartão", names,
            index=names.index(card) if card in names else 0,
        )
        desc = c2.text_input("Descrição")
        c3, c4 = st.columns(2)
        data_compra = c3.date_input("Data da compra", format="DD/MM/YYYY")
        categoria = c4.selectbox("Categoria", categories)
        c5, c6 = st.columns(2)
        valor = c5.number_input("Valor total (R$)", min_value=0.01,
                                format="%.2f")
        parcelas = c6.number_input("Parcelas", min_value=1, max_value=48,
                                   value=1, step=1)

        fech = cc.card_settings(df_cards, cartao)["fechamento"]
        st.caption(
            f"**{cartao}** fecha dia {fech}: compras a partir desse dia caem "
            "na fatura do mês corrente; antes, na do mês anterior."
        )

        if st.form_submit_button("Lançar compra"):
            if not desc.strip():
                st.error("Informe uma descrição.")
            else:
                linhas = cc.installments_for_purchase(
                    purchase_date=data_compra, description=desc.strip(),
                    category=categoria, total_amount=valor,
                    installments=int(parcelas), closing_day=int(fech),
                )
                for linha in linhas:
                    linha["Cartão"] = cartao
                repository.save_credit_card(pd.concat(
                    [df_tx, pd.DataFrame(linhas)], ignore_index=True))
                st.success(
                    f"Compra lançada em {cartao} — primeira parcela na fatura "
                    f"{linhas[0]['Mês da Fatura']}."
                )
                st.rerun()


# ---------------------------------------------------------------------------
# Cadastro de cartões
# ---------------------------------------------------------------------------

def _cards_registry(df_cards: pd.DataFrame, names: list[str]) -> None:
    with st.expander("🛠️ Meus cartões"):
        st.caption(
            "Cada cartão tem limite e datas próprias — elas definem em qual "
            "fatura cada compra cai."
        )
        with st.form("edit_cards"):
            edited = st.data_editor(
                df_cards, num_rows="dynamic", hide_index=True,
                use_container_width=True,
                column_config={
                    "Limite": st.column_config.NumberColumn(
                        "Limite (R$)", min_value=0.0, format="%.2f"),
                    "Dia Fechamento": st.column_config.NumberColumn(
                        "Dia Fechamento", min_value=1, max_value=31),
                    "Dia Vencimento": st.column_config.NumberColumn(
                        "Dia Vencimento", min_value=1, max_value=31),
                },
            )
            if st.form_submit_button("💾 Salvar cartões"):
                if df_cards.equals(edited):
                    st.info("Nada a salvar — sem alterações.")
                else:
                    repository.save_cards(edited)
                    st.success("Cartões atualizados.")
                    st.rerun()
        st.caption(
            "Renomear um cartão aqui **não** renomeia as compras já "
            "lançadas — elas continuam apontando para o nome antigo. Ajuste "
            "a coluna *Cartão* no extrato se precisar."
        )


# ---------------------------------------------------------------------------
# Extrato
# ---------------------------------------------------------------------------

def _extract_section(df_tx: pd.DataFrame, df_period: pd.DataFrame,
                     names: list[str], selected_month: str,
                     card: str | None) -> None:
    label = f" ({selected_month})" if selected_month != ALL_MONTHS else ""
    st.subheader(f"Gastos por categoria{label}")

    view = df_period
    if card and not view.empty and "Cartão" in view.columns:
        view = view[view["Cartão"].astype(str).str.strip() == card]
    if view.empty:
        st.info("Nenhuma compra neste período.")
    else:
        grouped = view.groupby("Categoria")["Valor"].sum().reset_index()
        components.vertical_bar(grouped, x="Categoria", y="Valor",
                                color=Colors.INVESTMENT)

    st.divider()
    st.subheader("Extrato completo")
    st.caption("Edite as linhas livremente e clique em salvar.")

    editable = df_tx
    if card and not editable.empty and "Cartão" in editable.columns:
        editable = editable[editable["Cartão"].astype(str).str.strip() == card]
    if editable.empty:
        st.info("Sem compras lançadas.")
        return

    with st.form("edit_credit_card"):
        edited = st.data_editor(
            editable, num_rows="dynamic", use_container_width=True,
            hide_index=True,
            column_config={
                "Cartão": st.column_config.SelectboxColumn(
                    "Cartão", options=names, required=True),
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=["Pendente", "Pago"], required=True),
                "Valor": st.column_config.NumberColumn(
                    "Valor (R$)", min_value=0.0, format="%.2f"),
            },
        )
        if st.form_submit_button("💾 Salvar alterações"):
            if editable.equals(edited):
                st.info("Nada a salvar — sem alterações.")
            else:
                untouched = df_tx.drop(editable.index, errors="ignore")
                repository.save_credit_card(pd.concat(
                    [untouched, edited], ignore_index=True))
                st.success("Extrato salvo.")
                st.rerun()
