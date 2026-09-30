"""Página: Cartão de Crédito — múltiplos cartões, faturas e pagamentos."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import (
    components, credit_card as cc, positions, reconcile, repository,
)
from src import pluggy_import as pi
from src.config import Colors, ConfigKeys, DEFAULT_CARD_NAME
from src.format import brl, md
from src.sidebar import ALL_MONTHS

_ALL_CARDS = "Todos os cartões"


def render(*, df_credit_card: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           categories: list[str], selected_month: str) -> None:
    components.page_header(
        "Cartão de Crédito",
        "Suas faturas, uma a uma. As compras chegam sozinhas pela "
        "importação — aqui você acompanha e dá baixa.",
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
    st.markdown("###### Ajustes")
    st.caption(
        "Com a importação ligada, quase nada aqui é necessário no dia a "
        "dia: nome e limite dos cartões, e as exceções."
    )
    _cards_registry(df_cards, df_credit_card, df_payments, names)
    # A compra digitada à mão virou exceção — e lançar aqui algo que o
    # banco também traz cria linha duplicada, porque a importada tem id
    # e esta não.
    with st.expander("➕ Lançar uma compra que não veio do banco"):
        st.caption(
            "Só para o que a importação não traz. O que passa no cartão "
            "chega sozinho pela aba **Importar do banco**."
        )
        _purchase_form(df_cards, df_credit_card, names, categories, card)
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

def _saldo_do_banco() -> dict[str, float]:
    """{cartão cadastrado: dívida informada pela instituição}.

    Casa pelo id da conta na Pluggy, guardado quando o usuário escolheu
    o destino de cada uma. Casar por nome quebraria no dia em que o
    banco renomeasse "platinum" para outra coisa.
    """
    return positions.card_balances(
        positions.from_rows(repository.load_positions()),
        pi.parse_mapping(
            repository.load_config_text(ConfigKeys.PLUGGY_MAPA)),
    )


def _parcelas_projetadas() -> None:
    """Remove as parcelas futuras que o lançamento manual inventou.

    O formulário manual cria, de uma vez, uma linha por parcela nos
    meses seguintes. A importação não faz isso — cada parcela chega no
    mês em que o banco a cobra. Convivendo, a mesma parcela existe duas
    vezes, e como a data de compra difere o comparador de duplicatas
    não as reconhece. É o que enche o app de faturas até 2028.
    """
    df_tx = repository.load_credit_card()
    idx = reconcile.manual_future_rows(df_tx, today=date.today())
    if len(idx) == 0:
        return

    alvo = df_tx.loc[idx]
    total = float(pd.to_numeric(alvo["Valor"], errors="coerce").fillna(0).sum())
    meses = sorted({str(m) for m in alvo["Mês da Fatura"]})

    with st.expander(
        md(f"📐 {len(idx)} parcela(s) projetada(s) à mão — {brl(total)}"),
        expanded=True,
    ):
        st.caption(
            "Linhas de meses futuros que **não vieram do banco**: foram "
            "criadas pelo lançamento manual parcelado, que espalha a "
            "compra pelos meses seguintes de uma vez. O banco cobra "
            "essas parcelas no mês certo e a importação as traz — "
            "manter as duas conta a mesma parcela duas vezes."
        )
        st.caption(md(
            f"Vão de **{meses[0]}** a **{meses[-1]}**. A fatura do mês "
            "corrente não é tocada."
        ))
        st.dataframe(pd.DataFrame([{
            "Cartão": r.get("Cartão"), "Fatura": r.get("Mês da Fatura"),
            "Descrição": r.get("Descrição"), "Parcela": r.get("Parcela"),
            "Valor": brl(float(pd.to_numeric(r.get("Valor"),
                                             errors="coerce") or 0)),
        } for _, r in alvo.head(40).iterrows()]), hide_index=True,
            use_container_width=True)
        if len(alvo) > 40:
            st.caption(f"…e mais {len(alvo) - 40} linha(s).")

        if st.button(f"🧹 Remover {len(idx)} parcela(s) projetada(s)",
                     type="primary", key="limpar_projetadas"):
            repository.save_credit_card(
                df_tx.drop(index=idx).reset_index(drop=True))
            st.success(md(f"{len(idx)} linha(s) removida(s) — {brl(total)}."))
            st.rerun()

    falhas = reconcile.parcel_gaps(df_tx)
    if not falhas.empty:
        with st.expander(
            f"⚠️ {len(falhas)} parcelamento(s) com mês fora de sequência"
        ):
            st.caption(
                "A parcela 4/10 tem de cair um mês depois da 3/10. Um "
                "buraco aponta linha faltando; uma repetição, linha "
                "inventada."
            )
            st.dataframe(falhas, hide_index=True, use_container_width=True)


def _faturas_do_banco() -> dict[tuple[str, str], float]:
    """{(cartão, mês): total informado pela instituição}."""
    df = repository.load_bank_bills()
    if df.empty or not {"Cartão", "Mês", "Total"}.issubset(df.columns):
        return {}
    out: dict[tuple[str, str], float] = {}
    for _, linha in df.iterrows():
        valor = pd.to_numeric(linha.get("Total"), errors="coerce")
        if pd.isna(valor):
            continue
        out[(str(linha["Cartão"]).strip(),
             str(linha["Mês"]).strip())] = float(valor)
    return out


def _all_cards_overview(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                        df_pay: pd.DataFrame, names: list[str]) -> None:
    """Visão consolidada, com a dívida lida das instituições.

    Somar as linhas da planilha dá o total certo só quando nenhuma
    compra falta e nenhuma sobra — e as duas coisas acontecem. O banco
    sabe quanto se deve, então é dele que vem o número; a soma das
    linhas vira conferência, não fonte.
    """
    st.subheader("Visão consolidada")

    do_banco = _saldo_do_banco()
    banco_faturas = _faturas_do_banco()

    total_limite = total_banco = total_linhas = 0.0
    linhas = []
    for name in names:
        limite = float(cc.card_settings(df_cards, name)["limite"])
        abertas = cc.open_invoices(df_tx, df_pay, card=name)
        soma = sum(i.balance for i in abertas)
        saldo = do_banco.get(name)
        devido = saldo if saldo is not None else soma

        total_limite += limite
        total_banco += devido
        total_linhas += soma
        linhas.append({
            "Cartão": name,
            "Limite": brl(limite),
            "Em aberto": brl(devido),
            "Fonte": "banco" if saldo is not None else "soma das linhas",
            "Disponível": brl(limite - devido),
            "Uso": f"{(devido / limite * 100) if limite else 0:.0f}%",
        })

    c1, c2, c3 = st.columns(3)
    c1.metric("Limite total", brl(total_limite))
    c2.metric("Em aberto", brl(total_banco),
              delta=f"{len(names)} cartão(ões)", delta_color="off")
    disponivel = total_limite - total_banco
    c3.metric("Disponível", brl(disponivel),
              delta_color="normal" if disponivel >= 0 else "inverse")

    if do_banco:
        st.caption(
            "Valores lidos das instituições. Atualize no **Dashboard** "
            "para buscar de novo."
        )
    else:
        st.info(md(
            "Ainda não li a dívida nas instituições — os números acima "
            "são a soma das suas linhas. Vá ao **Dashboard** e clique em "
            "**Atualizar**."
        ))

    st.dataframe(pd.DataFrame(linhas), hide_index=True,
                 use_container_width=True)

    _confronto_de_linhas(total_banco, total_linhas, bool(do_banco))
    _remover_duplicatas()
    _parcelas_projetadas()
    _faturas(df_cards, df_tx, df_pay, names, banco_faturas)


def _confronto_de_linhas(total_banco: float, total_linhas: float,
                         tem_banco: bool) -> None:
    """Quanto a planilha difere do banco, e o que isso significa.

    O sinal diz a causa: a mais é compra repetida, a menos é compra que
    não chegou. Sem separar os dois, o usuário não sabe se limpa ou se
    importa.
    """
    if not tem_banco:
        return
    diferenca = total_linhas - total_banco
    if abs(diferenca) < 1.0:
        st.success(md(f"As linhas somam o mesmo que o banco: "
                      f"{brl(total_banco)}."))
        return
    if diferenca > 0:
        st.warning(md(
            f"As suas linhas somam {brl(diferenca)} **a mais** que o "
            "banco. Isso é compra lançada duas vezes — use o removedor "
            "de duplicatas abaixo."
        ))
    else:
        st.info(md(
            f"As suas linhas somam {brl(abs(diferenca))} **a menos** que "
            "o banco. Falta importar: vá em **Importar do banco** e "
            "confira a data de corte."
        ))


def _faturas(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
             df_pay: pd.DataFrame, names: list[str],
             banco: dict[tuple[str, str], float]) -> None:
    """As faturas como o app do banco as mostra.

    Um bloco por situação, na ordem em que importam: o que está
    atrasado, o que está aberto agora, e o que ainda vai fechar. Uma
    lista única ordenada por mês misturava dívida de hoje com
    compromisso de 2027, que é o que fazia o total parecer absurdo.
    """
    hoje = date.today()
    agendadas, _ = cc.schedule_invoices(df_tx, df_pay, df_cards, today=hoje)
    agendadas = [i for i in agendadas if i.card in names]
    if not agendadas:
        st.success("Nenhuma fatura em aberto.")
        return
    situacao = cc.situations(agendadas, hoje)

    ordem = ["Vencida", "Atual", "Fechada · a pagar", "Futura"]
    titulos = {
        "Vencida": "🔴 Vencidas",
        "Atual": "🔵 Fatura atual",
        "Fechada · a pagar": "🟡 Fechadas, aguardando pagamento",
        "Futura": "⚪ Futuras",
    }
    legendas = {
        "Atual": "Ainda aberta — compras novas continuam entrando nela.",
        "Futura": "Compras parceladas que só virão nos próximos meses.",
    }

    for estado in ordem:
        grupo = [i for i in agendadas
                 if situacao[(i.card, i.month)] == estado]
        if not grupo:
            continue
        grupo.sort(key=lambda i: i.due)
        total = sum(_valor_da_fatura(i, banco) for i in grupo)
        st.markdown(md(f"**{titulos[estado]} — {brl(total)}**"))
        if estado in legendas:
            st.caption(legendas[estado])
        st.dataframe(pd.DataFrame([{
            "Cartão": i.card,
            "Fatura": i.month,
            "Fecha": f"{i.closing:%d/%m/%Y}",
            "Vence": f"{i.due:%d/%m/%Y}",
            "Valor": brl(_valor_da_fatura(i, banco)),
            "Fonte": "banco" if (i.card, i.month) in banco else "linhas",
        } for i in grupo]), hide_index=True, use_container_width=True)

    if any(v == "linhas" for v in
           ("banco" if (i.card, i.month) in banco else "linhas"
            for i in agendadas)):
        st.caption(
            "**Fonte** diz de onde veio o valor. *banco* é o total que a "
            "instituição informou; *linhas* é a soma das compras que "
            "chegaram — usado enquanto o banco não emite a fatura."
        )


def _valor_da_fatura(fatura, banco: dict[tuple[str, str], float]) -> float:
    """O que se deve nessa fatura, preferindo o total do banco."""
    do_banco = banco.get((fatura.card, fatura.month))
    if do_banco is None:
        return fatura.balance
    return max(do_banco - fatura.advances, 0.0)


def _remover_duplicatas() -> None:
    """Apaga a cópia de compras lançadas duas vezes.

    É o conserto certo quando a planilha soma o dobro do banco: existem
    duas linhas para a mesma compra, uma digitada e outra importada.
    Mantém sempre uma de cada — apagar o grupo inteiro trocaria um
    excesso por uma falta, que é pior, porque excesso aparece no total
    e falta não aparece em lugar nenhum.
    """
    df_tx = repository.load_credit_card()
    previa = reconcile.duplicate_preview(df_tx, reconcile.CHAVES_CARTAO)
    if previa.empty:
        return

    quantas = int(previa["Cópias a remover"].sum())
    valor = float(pd.to_numeric(
        df_tx.loc[reconcile.duplicates(df_tx, reconcile.CHAVES_CARTAO),
                  "Valor"], errors="coerce").fillna(0).sum())

    with st.expander(
        f"🧹 {quantas} compra(s) repetida(s) — {brl(valor)}", expanded=True
    ):
        st.caption(
            "Linhas idênticas em cartão, fatura, descrição, parcela, "
            "valor e data da compra. Uma de cada fica."
        )
        st.dataframe(previa.head(30), hide_index=True,
                     use_container_width=True)
        if len(previa) > 30:
            st.caption(f"…e mais {len(previa) - 30} grupo(s).")
        if st.button(f"🧹 Remover {quantas} cópia(s)", type="primary",
                     key="dedup_cartao"):
            limpo = df_tx.drop(
                index=reconcile.duplicates(df_tx, reconcile.CHAVES_CARTAO))
            repository.save_credit_card(limpo.reset_index(drop=True))
            st.success(md(f"{quantas} cópia(s) removida(s) — {brl(valor)}."))
            st.rerun()


def _drift_warning(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                   card: str) -> None:
    """Avisa quando o mês gravado de alguma parcela discorda do fechamento.

    O mês da fatura é congelado na planilha no lançamento. Sem este
    aviso, uma compra antiga com rótulo defasado fica indistinguível de
    uma compra recém-lançada, e o extrato parece contraditório: duas
    compras do mesmo ciclo aparecem em faturas diferentes.
    """
    # Quando o banco informa as faturas, é ele quem decide o mês — e o
    # aviso de divergência contra o dia de fechamento vira ruído, porque
    # a regra deixou de ser a autoridade.
    if any(c == card for c, _ in _faturas_do_banco()):
        return

    todas = cc.invoice_month_drift(df_tx, df_cards, card, only_pending=False)
    if not todas:
        return
    pendentes = cc.invoice_month_drift(df_tx, df_cards, card)
    pagas = len(todas) - len(pendentes)

    exemplos = ", ".join(
        f"{antigo} → {novo}" for antigo, novo in sorted(set(todas.values()))[:3]
    )
    # As pagas são contadas à parte: elas só mudam com o opt-in explícito,
    # então omiti-las faria o aviso sumir antes de o histórico estar certo.
    if pendentes and pagas:
        quanto = f"{len(pendentes)} parcela(s) pendente(s) e {pagas} já paga(s)"
    elif pendentes:
        quanto = f"{len(pendentes)} parcela(s) pendente(s)"
    else:
        quanto = f"{pagas} parcela(s) já paga(s)"

    st.warning(
        f"⚠️ {quanto} deste cartão estão gravadas em um mês que não "
        f"corresponde ao fechamento no dia "
        f"{int(cc.card_settings(df_cards, card)['fechamento'])} ({exemplos}). "
        "Corrija em **Meus cartões → 🔄 Recalcular o mês das faturas** — "
        "dá para ver a prévia antes de aplicar."
        + (" Para as já pagas, marque a caixa que libera o histórico."
           if pagas else "")
    )


def _single_card_view(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                      df_pay: pd.DataFrame, card: str) -> None:
    settings = cc.card_settings(df_cards, card)
    limite, disp = cc.available_limit(df_cards, df_tx, df_pay, card)
    abertas = cc.open_invoices(df_tx, df_pay, card=card)
    saldo = sum(i.balance for i in abertas)

    titulo = card + (f" · {settings['instituicao']}"
                     if settings["instituicao"] else "")
    st.subheader(titulo)
    if int(settings["vencimento"]) > int(settings["fechamento"]):
        quando = "vence dia {} do mesmo mês".format(settings["vencimento"])
    else:
        quando = "vence dia {} do mês seguinte".format(settings["vencimento"])
    st.caption(f"Fecha todo dia {settings['fechamento']} · {quando}")

    _drift_warning(df_cards, df_tx, card)

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
            # Sem a guarda, um "Mês da Fatura" ilegível derrubaria a página
            # inteira — justamente a página para onde o aviso manda o
            # usuário vir corrigir. A fatura continua pagável sem as datas.
            try:
                fechamento, vencimento = cc.invoice_dates(
                    i.month, int(settings["fechamento"]),
                    int(settings["vencimento"]),
                )
            except ValueError:
                st.caption(
                    f"⚠️ Não consegui ler o mês **{i.month}** nem as datas "
                    "deste cartão. Corrija o **Mês da Fatura** no extrato "
                    "(formato MM/AAAA) ou as datas em Meus cartões."
                )
            else:
                st.caption(
                    f"Fecha em {fechamento:%d/%m/%Y} · "
                    f"vence em {vencimento:%d/%m/%Y}"
                )
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
    mask = (cc.card_series(df_tx) == card) & (
        df_tx["Mês da Fatura"].astype(str).str.strip() == month
    )
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
                st.success(md(
                    f"{brl(valor)} pagos em {inv.card}. "
                    f"Faltam {brl(inv.balance - valor)} nessa fatura."
                ))
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
            st.success(md(
                f"Fatura de {inv.card} ({inv.month}) quitada. "
                f"Lançado no caixa: {brl(a_lancar)}."
            ))
            st.rerun()

    if not df_pay.empty:
        with st.expander("Histórico de pagamentos parciais"):
            hist = df_pay.copy()
            if card:
                hist = hist[hist["Cartão"].fillna("").astype(str).str.strip() == card]
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

        fech = int(cc.card_settings(df_cards, cartao)["fechamento"])
        atual = cc.invoice_month_for_purchase(date.today(), fech).strftime("%m/%Y")
        ini, fim = cc.invoice_window(atual, fech)
        st.caption(
            f"**{cartao}** fecha dia {fech}. A fatura de **{atual}** pega "
            f"compras de {ini:%d/%m/%Y} até {fim:%d/%m/%Y} — depois disso a "
            "compra já vai para a fatura seguinte, mesmo que esta ainda não "
            "tenha vencido."
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

def _cards_registry(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                    df_pay: pd.DataFrame, names: list[str]) -> None:
    st.subheader("Meus cartões")

    orfaos = cc.orphan_card_names(df_cards, df_tx)
    if orfaos:
        st.warning(
            "⚠️ Há compras em cartões que não estão cadastrados: **"
            + "**, **".join(orfaos)
            + "**. Cadastre-os abaixo para definir limite e datas."
        )

    _card_settings_form(df_cards, df_tx, df_pay, names)
    st.divider()
    _reschedule_section(df_cards, df_tx, df_pay, names)
    st.divider()
    _new_card_form(names)
    st.divider()
    _card_danger_zone(df_cards, df_tx, df_pay, names)


def _card_settings_form(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                        df_pay: pd.DataFrame, names: list[str]) -> None:
    """Nome, instituição, limite e datas de um cartão.

    Renomear leva junto compras e pagamentos — sem isso a fatura ficaria
    órfã e o limite voltaria a parecer livre.
    """
    alvo = st.selectbox("Editar cartão:", names, key="card_edit_target")
    settings = cc.card_settings(df_cards, alvo)
    compras = int((cc.card_series(df_tx) == alvo).sum()) if not df_tx.empty else 0

    with st.form("edit_card_settings"):
        c1, c2 = st.columns(2)
        novo_nome = c1.text_input("Nome", value=alvo)
        inst = c2.text_input("Instituição", value=settings["instituicao"])
        c3, c4, c5 = st.columns(3)
        limite = c3.number_input(
            "Limite (R$)", min_value=0.0, step=100.0,
            value=float(settings["limite"]),
            help="O limite real do cartão. É a base do 'disponível'.",
        )
        fech = c4.number_input(
            "Dia de fechamento", min_value=1, max_value=31, step=1,
            value=int(settings["fechamento"]),
            help=(
                "O dia em que a fatura do mês FECHA. Compras até esse dia "
                "entram nela; depois dele, vão para a fatura do mês seguinte."
            ),
        )
        venc = c5.number_input(
            "Dia de vencimento", min_value=1, max_value=31, step=1,
            value=int(settings["vencimento"]),
            help=(
                "O dia do pagamento. Pode ser no mês seguinte ao fechamento "
                "(fecha dia 30, vence dia 7) sem mudar o nome da fatura."
            ),
        )
        st.caption(
            f"**{alvo}** tem {compras} compra(s) lançada(s). Renomear atualiza "
            "todas elas e os pagamentos junto."
        )
        if st.form_submit_button("💾 Salvar cartão"):
            limpo = novo_nome.strip()
            if not limpo:
                st.error("Informe um nome.")
            elif limpo != alvo and limpo in names:
                st.error(f"Já existe um cartão chamado '{limpo}'.")
            else:
                cards, tx, pay = (df_cards, df_tx, df_pay)
                if limpo != alvo:
                    cards, tx, pay = cc.rename_card(
                        df_cards, df_tx, df_pay, alvo, limpo,
                    )
                    repository.save_credit_card(tx)
                    repository.save_card_payments(pay)

                if cards.empty or "Nome" not in cards.columns or \
                        limpo not in set(cards["Nome"].astype(str).str.strip()):
                    cards = pd.concat([cards, pd.DataFrame([{"Nome": limpo}])],
                                      ignore_index=True)
                mask = cards["Nome"].astype(str).str.strip() == limpo
                cards.loc[mask, "Instituição"] = inst.strip()
                cards.loc[mask, "Limite"] = limite
                cards.loc[mask, "Dia Fechamento"] = fech
                cards.loc[mask, "Dia Vencimento"] = venc
                repository.save_cards(cards)

                if limpo != alvo:
                    st.success(
                        f"'{alvo}' renomeado para '{limpo}' — {compras} "
                        "compra(s) e os pagamentos acompanharam."
                    )
                else:
                    st.success(f"'{limpo}' atualizado.")
                st.rerun()


def _reschedule_section(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                        df_pay: pd.DataFrame, names: list[str]) -> None:
    """Realinha faturas antigas depois de corrigir o dia de fechamento.

    O mês da fatura é congelado na planilha quando a compra é lançada.
    Mudar o dia de fechamento não reescreve o passado sozinho — de
    propósito, para não mexer em fatura já conferida sem o usuário pedir.
    """
    with st.expander("🔄 Recalcular o mês das faturas"):
        st.caption(
            "Use depois de corrigir o dia de fechamento de um cartão. "
            "Por padrão só mexe em parcelas **pendentes**, preservando o "
            "histórico já conferido."
        )
        alvo = st.selectbox("Cartão:", names, key="card_reschedule_target")
        fech = int(cc.card_settings(df_cards, alvo)["fechamento"])
        incluir_pagas = st.checkbox(
            "Corrigir também as faturas já pagas",
            key="card_reschedule_paid",
            help=(
                "Marque se o mês foi gravado errado desde o começo. Isso "
                "reescreve o histórico do cartão — o total de cada fatura "
                "passada muda, e com ele os gráficos do Dashboard."
            ),
        )
        drift = cc.invoice_month_drift(
            df_tx, df_cards, alvo, only_pending=not incluir_pagas,
        )

        if not drift:
            escopo = "" if incluir_pagas else "pendentes "
            st.success(
                f"Tudo certo: as parcelas {escopo}de **{alvo}** já batem "
                f"com o fechamento no dia {fech}."
            )
            return

        preview = pd.DataFrame(
            [{"De": antigo, "Para": novo} for antigo, novo in drift.values()]
        ).value_counts().reset_index(name="Parcelas")
        st.warning(
            f"**{len(drift)}** parcela(s) pendente(s) de **{alvo}** estão em "
            f"um mês que não corresponde ao fechamento no dia {fech}."
        )
        st.dataframe(preview, hide_index=True, use_container_width=True)

        if st.button(f"Aplicar em {alvo}", type="primary",
                     key="card_reschedule_apply"):
            tx, pay = cc.apply_invoice_month_drift(df_tx, df_pay, alvo, drift)
            repository.save_credit_card(tx)
            if not pay.equals(df_pay):
                repository.save_card_payments(pay)
            st.success(f"{len(drift)} parcela(s) remanejada(s).")
            st.rerun()


def _new_card_form(names: list[str]) -> None:
    with st.expander("➕ Adicionar outro cartão"):
        with st.form("new_card", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome do cartão", placeholder="Ex.: Nubank")
            inst = c2.text_input("Instituição")
            c3, c4, c5 = st.columns(3)
            limite = c3.number_input("Limite (R$)", min_value=0.0,
                                     value=1000.0, step=100.0)
            fech = c4.number_input("Dia de fechamento", min_value=1,
                                   max_value=31, value=8, step=1)
            venc = c5.number_input("Dia de vencimento", min_value=1,
                                   max_value=31, value=15, step=1)
            if st.form_submit_button("Cadastrar cartão"):
                limpo = nome.strip()
                if not limpo:
                    st.error("Informe um nome.")
                elif limpo in names:
                    st.error(f"Já existe um cartão chamado '{limpo}'.")
                else:
                    repository.save_cards(pd.concat([
                        repository.load_cards(),
                        pd.DataFrame([{
                            "Nome": limpo, "Instituição": inst.strip(),
                            "Limite": limite, "Dia Fechamento": fech,
                            "Dia Vencimento": venc,
                        }]),
                    ], ignore_index=True))
                    st.success(f"'{limpo}' cadastrado.")
                    st.rerun()


def _card_danger_zone(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                      df_pay: pd.DataFrame, names: list[str]) -> None:
    with st.expander("🗑️ Excluir um cartão"):
        alvo = st.selectbox("Cartão a excluir:", names, key="card_delete_target")
        compras = int((cc.card_series(df_tx) == alvo).sum()) if not df_tx.empty else 0
        st.caption(f"**{alvo}** tem {compras} compra(s) lançada(s).")

        outros = [n for n in names if n != alvo]
        destino = None
        if compras and outros:
            mover = st.radio(
                "O que fazer com as compras?",
                ["Transferir para outro cartão", "Apagar junto"],
                key="card_delete_mode",
            )
            if mover == "Transferir para outro cartão":
                destino = st.selectbox("Transferir para:", outros,
                                       key="card_delete_dest")
        elif compras:
            st.caption("Sem outro cartão para transferir — serão apagadas.")

        confirmar = st.text_input(
            f"Para confirmar, digite o nome do cartão ({alvo}):",
            key="card_delete_confirm",
        )
        if st.button("🗑️ Excluir cartão", key="card_delete_btn"):
            if confirmar.strip() != alvo:
                st.error("O nome digitado não confere. Exclusão cancelada.")
            else:
                cards, tx, pay = cc.delete_card(
                    df_cards, df_tx, df_pay, alvo, move_to=destino,
                )
                repository.save_cards(cards)
                repository.save_credit_card(tx)
                repository.save_card_payments(pay)
                st.success(
                    f"'{alvo}' excluído"
                    + (f"; compras transferidas para '{destino}'."
                       if destino else
                       f" junto com {compras} compra(s).")
                )
                st.rerun()
        st.caption(
            "Excluir um cartão **não** apaga os lançamentos de Entradas e "
            "Saídas — seu saldo bancário permanece intacto."
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
    if card and not view.empty:
        view = view[cc.card_series(view) == card]
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
    if card and not editable.empty:
        editable = editable[cc.card_series(editable) == card]
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
