"""Página: Cartão de Crédito — múltiplos cartões, faturas e pagamentos."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import (
    components, credit_card as cc, positions, reconcile, repository,
)
from src import pluggy_import as pi
from src.config import (Colors, ConfigKeys, DEFAULT_CARD_NAME, ORIGEM_BANCO,
                        ORIGEM_MANUAL, ORIGEM_PROJECAO)
from src.dates import parse_month_label
from src.format import brl, md
from src.sidebar import ALL_MONTHS

_ALL_CARDS = "Todos os cartões"


def render(*, df_credit_card: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           categories: list[str], selected_month: str) -> None:
    """A página do cartão em quatro abas, por pergunta.

    Era um rolo único: visão consolidada, três ferramentas de limpeza
    abertas de saída, quatro tabelas de fatura, pagamento, cadastro,
    formulário de compra e extrato — tudo um abaixo do outro, separado por
    divisores do mesmo peso. O que se quer saber ao abrir ("quanto devo,
    quando vence") ficava disputando espaço com a manutenção.

    Agora cada aba responde uma coisa, e a manutenção só chama atenção
    quando tem trabalho: o número no rótulo da aba **Ajustes** é quanta
    pendência existe. Zero pendências, rótulo limpo.
    """
    df_cards = repository.load_cards()
    df_payments = repository.load_card_payments()
    names = cc.list_card_names(df_cards, df_credit_card)

    if not names:
        _first_card_setup()
        return

    components.page_header(
        "Cartão de Crédito",
        "As compras chegam sozinhas pela importação. Aqui você acompanha "
        "as faturas e dá baixa.",
    )

    pendencias = _pendencias()
    rotulo_ajustes = ("🛠 Ajustes" if not pendencias
                      else f"🛠 Ajustes ({pendencias})")
    aba_faturas, aba_pagar, aba_extrato, aba_ajustes = st.tabs(
        ["💳 Faturas", "✅ Pagar", "📄 Extrato", rotulo_ajustes])

    with aba_faturas:
        escolha = st.selectbox(
            "Cartão", [_ALL_CARDS] + names,
            help="Escolha um cartão para ver limite, uso e fatura a fatura.")
        card = None if escolha == _ALL_CARDS else escolha
        if card is None:
            _all_cards_overview(df_cards, df_credit_card, df_payments, names)
        else:
            _single_card_view(df_cards, df_credit_card, df_payments, card)

    with aba_pagar:
        _payment_section(df_credit_card, df_payments, names, None)

    with aba_extrato:
        _extract_section(df_credit_card, df_credit_card_period, names,
                         selected_month, None)

    with aba_ajustes:
        _adjustments_tab(df_cards, df_credit_card, df_payments, names,
                         categories)


def _pendencias() -> int:
    """Quantas coisas a aba de ajustes tem para resolver.

    Vira número no rótulo da aba. Sem isso, esconder as ferramentas de
    limpeza numa aba significaria esconder também o aviso de que há uma
    compra em dobro — e o total continuaria errado sem ninguém saber por
    quê.
    """
    df_tx = repository.load_credit_card()
    if df_tx.empty:
        return 0
    quantas = 0
    previa = reconcile.duplicate_preview(df_tx, reconcile.CHAVES_CARTAO)
    if not previa.empty:
        quantas += 1
    if len(reconcile.manual_future_rows(df_tx, today=date.today())):
        quantas += 1
    if reconcile.project_installments(df_tx, today=date.today()):
        quantas += 1
    if not reconcile.parcel_gaps(df_tx).empty:
        quantas += 1
    return quantas


def _adjustments_tab(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
                     df_pay: pd.DataFrame, names: list[str],
                     categories: list[str]) -> None:
    """Manutenção: o que só se mexe quando algo não bate."""
    components.section(
        "Ajustes e manutenção",
        "Com a importação ligada, quase nada aqui é necessário no dia a "
        "dia. Se a fatura não está batendo, é aqui que se resolve.",
        eyebrow="Cartão de crédito",
    )

    _remover_duplicatas()
    _parcelas_projetadas()
    _completar_parcelamentos()

    st.write("")
    _cards_registry(df_cards, df_tx, df_pay, names)

    # A compra digitada à mão virou exceção — e lançar aqui algo que o
    # banco também traz cria linha duplicada, porque a importada tem id
    # e esta não.
    with st.expander("➕ Lançar uma compra que não veio do banco"):
        st.caption(
            "Só para o que a importação não traz. O que passa no cartão "
            "chega sozinho pela aba **Importar do banco**."
        )
        _purchase_form(df_cards, df_tx, names, categories, None)


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
        md(f"🧹 {len(idx)} parcela(s) lançada(s) à mão de uma vez — "
           f"{brl(total)}"),
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
        components.table(pd.DataFrame([{
            "Cartão": r.get("Cartão"), "Fatura": r.get("Mês da Fatura"),
            "Descrição": r.get("Descrição"), "Parcela": r.get("Parcela"),
            "Valor": brl(float(pd.to_numeric(r.get("Valor"),
                                             errors="coerce") or 0)),
        } for _, r in alvo.iterrows()]), align_right=("Valor",),
            max_rows=40)

        if st.button(f"🧹 Remover {len(idx)} linha(s) criada(s) à mão",
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
            components.table(falhas)


def _completar_parcelamentos() -> None:
    """Deduz as parcelas contratadas que o banco ainda não lançou.

    A Pluggy só entrega o que já foi cobrado; uma compra em 10x tem as
    parcelas seguintes acordadas mas invisíveis. Como o valor e a
    quantidade já estão fechados, deduzi-las é honesto — e sem elas a
    projeção do próximo ano fica vazia justamente onde há compromisso.
    """
    df_tx = repository.load_credit_card()
    # Nos meses cuja fatura o banco já emitiu, o total é o dele: deduzir
    # linha ali afasta o app do banco em vez de aproximar.
    novas = reconcile.project_installments(
        df_tx, today=date.today(), faturadas=set(_faturas_do_banco()))
    if not novas:
        return

    total = sum(n["Valor"] for n in novas)
    # Por data, não por texto: "MM/AAAA" ordenado como string põe
    # 01/2027 antes de 12/2026, e a faixa saía invertida na tela.
    meses = sorted({n["Mês da Fatura"] for n in novas},
                   key=lambda m: parse_month_label(m) or pd.Timestamp.max)
    with st.expander(
        md(f"➕ {len(novas)} parcela(s) contratada(s) que o banco ainda "
           f"não cobrou — {brl(total)}")
    ):
        st.caption(
            "Deduzidas do parcelamento: se a fatura de setembro tem a "
            "parcela 2/3, falta só a 3/3 em outubro. Elas entram "
            "marcadas como **projeção**, para você saber que não vieram "
            "do extrato."
        )
        components.table(pd.DataFrame([{
            "Cartão": n["Cartão"], "Fatura": n["Mês da Fatura"],
            "Descrição": n["Descrição"], "Parcela": n["Parcela"],
            "Valor": brl(n["Valor"]),
        } for n in novas]), align_right=("Valor",))
        st.caption(md(f"De {meses[0]} a {meses[-1]}."))

        if st.button(f"➕ Incluir {len(novas)} parcela(s) que faltam",
                     type="primary", key="projetar_parcelas"):
            repository.save_credit_card(pd.concat(
                [df_tx, pd.DataFrame(novas)], ignore_index=True))
            st.success(md(f"{len(novas)} parcela(s) incluída(s) — "
                          f"{brl(total)}."))
            st.rerun()


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
    do_banco = _saldo_do_banco()
    banco_faturas = _faturas_do_banco()

    total_limite = total_banco = total_linhas = 0.0
    por_cartao = []
    for name in names:
        limite = float(cc.card_settings(df_cards, name)["limite"])
        abertas = cc.open_invoices(df_tx, df_pay, card=name)
        soma = sum(i.balance for i in abertas)
        saldo = do_banco.get(name)
        devido = saldo if saldo is not None else soma

        total_limite += limite
        total_banco += devido
        total_linhas += soma
        por_cartao.append({
            "nome": name,
            "sub": (f"{devido / limite * 100:.0f}% de {brl(limite)}"
                    if limite else "sem limite cadastrado"),
            "valor": brl(devido),
            "divida": True,
        })

    # O que se deve e o que ainda se pode gastar, lado a lado. Eram três
    # métricas e uma tabela de seis colunas dizendo a mesma coisa duas
    # vezes; o cartão já mostra o total e a abertura por cartão.
    disponivel = total_limite - total_banco
    esq, dir_ = st.columns(2)
    with esq:
        components.stat_card(
            label="Devendo agora, segundo o banco", value=total_banco,
            divida=True,
            bar=(total_banco / total_limite) if total_limite else None,
            bar_label=(f"{total_banco / total_limite * 100:.0f}% do limite "
                       f"de {brl(total_limite)}" if total_limite else ""),
            rows=por_cartao,
        )
    with dir_:
        components.stat_card(
            label="Disponível para gastar", value=disponivel,
            rows=[
                {"nome": "Limite total", "valor": brl(total_limite),
                 "bruto": total_limite},
                {"nome": "Comprometido", "valor": f"− {brl(total_banco)}",
                 "divida": True},
                {"nome": "Cartões", "valor": str(len(names)),
                 "classe": "mf-mut"},
            ],
        )

    if not do_banco:
        st.info(md(
            "Ainda não li a dívida nas instituições — os números acima "
            "são a soma das suas linhas. Vá ao **Dashboard** e clique em "
            "**Atualizar**."
        ))

    _confronto_de_linhas(total_banco, total_linhas, bool(do_banco))
    _duas_medidas(total_banco, banco_faturas, do_banco)
    _faturas(df_cards, df_tx, df_pay, names, banco_faturas)


def _duas_medidas(saldo_agora: float, banco_faturas: dict, do_banco: dict
                  ) -> None:
    """Explica por que o cartão do topo não soma as faturas de baixo.

    São duas leituras diferentes da instituição, e a tela mostrava as
    duas com a mesma autoridade e nenhuma palavra sobre a diferença:

    - o cartão do topo é o **saldo da conta de cartão** na Pluggy: o que
      se deve neste instante;
    - os totais das faturas vêm de `/bills`: o valor de cada fatura que o
      banco **emitiu**.

    Somar as faturas nunca dá o saldo, porque as futuras ainda não foram
    cobradas e a atual ainda está recebendo compras. Quem compara os dois
    números sem saber disso conclui, com razão, que o app está errado —
    e era a principal causa de "as faturas não estão certas".
    """
    if not do_banco or not banco_faturas:
        return
    st.caption(md(
        f"O {brl(saldo_agora)} acima é o saldo da sua conta de cartão "
        "agora. Os totais das faturas abaixo são o valor de cada fatura "
        "emitida. Somar as faturas não dá esse número: as futuras ainda "
        "não foram cobradas e a atual continua recebendo compras."
    ))


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


def _baixa_pendente(agendadas: list, situacao: dict,
                    liquidadas: set[tuple[str, str]]) -> None:
    """Oferece acertar na planilha o que o banco já deu por pago.

    A tela passa a mostrar essas faturas como pagas assim que a
    instituição as reporta, mas as linhas continuam Pendente na
    planilha — e é delas que saem o total do cartão, a média de gastos e
    a projeção do próximo mês. Um clique alinha as duas coisas; deixar
    para a próxima importação mantém o número inflado até lá.
    """
    alvo = [i for i in agendadas
            if (i.card, i.month) in liquidadas and i.balance > 1e-6]
    if not alvo:
        return
    total = sum(i.balance for i in alvo)
    meses = ", ".join(f"{i.card} {i.month}" for i in alvo[:4])
    st.info(md(
        f"O banco já recebeu {len(alvo)} fatura(s) que a planilha ainda "
        f"tem como pendente ({meses}"
        + ("…" if len(alvo) > 4 else "")
        + f") — {brl(total)}. Aqui elas já aparecem como pagas; o botão "
        "acerta a planilha."
    ))
    if st.button(f"✅ Dar baixa em {len(alvo)} fatura(s)",
                 key="baixa_faturas_banco"):
        atual = repository.load_credit_card()
        vencimentos = {}
        df_bills = repository.load_bank_bills()
        for _, linha in df_bills.iterrows():
            venc = pd.to_datetime(str(linha.get("Vencimento") or "").strip(),
                                  errors="coerce")
            if not pd.isna(venc):
                vencimentos[(str(linha["Cartão"]).strip(),
                             str(linha["Mês"]).strip())] = venc.date()
        novo, quantas = cc.settle_closed_bills(atual, vencimentos,
                                               today=date.today())
        if quantas:
            repository.save_credit_card(novo)
            st.success(f"{quantas} linha(s) marcada(s) como paga(s).")
            st.rerun()
        else:
            st.warning("Nada mudou — as linhas já estavam em dia.")


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
    agendadas, ilegiveis = cc.schedule_invoices(df_tx, df_pay, df_cards,
                                                today=hoje)
    agendadas = [i for i in agendadas if i.card in names]
    # `schedule_invoices` devolve as faturas de mês ilegível justamente
    # para a tela poder avisar. Descartá-las calado era pior que um erro:
    # elas somem desta lista mas continuam contadas no total do topo, e a
    # divergência ficava sem nenhuma explicação na tela.
    if ilegiveis:
        st.warning(
            f"⚠️ {len(ilegiveis)} fatura(s) não entram na lista abaixo "
            f"porque o mês está ilegível: {', '.join(ilegiveis[:5])}"
            + ("…" if len(ilegiveis) > 5 else "")
            + ". Corrija o campo **Mês da Fatura** no extrato — o formato "
            "é MM/AAAA."
        )
    if not agendadas:
        st.success("Nenhuma fatura em aberto.")
        return

    # O banco só publica fatura fechada, e uma fechada cujo vencimento
    # passou já foi paga. Sem isso a tela decidia pela data e inventava
    # dívida vencida que a instituição não cobra mais.
    liquidadas = cc.settled_by_bank(repository.load_bank_bills(), today=hoje)
    situacao = cc.situations(agendadas, hoje, liquidadas)
    _baixa_pendente(agendadas, situacao, liquidadas)

    # A ordem é a da urgência, não a do calendário: uma lista por mês
    # misturava dívida de hoje com compromisso de 2027, e era isso que
    # fazia o total parecer absurdo.
    ordem = ["Vencida", "Atual", "Fechada · a pagar", "Futura"]
    titulos = {
        "Vencida": "Vencidas e não pagas",
        "Atual": "Fatura atual",
        "Fechada · a pagar": "Fechadas, aguardando pagamento",
        "Futura": "Ainda vão fechar",
    }
    legendas = {
        "Vencida": "Já passou do vencimento — dê baixa na aba Pagar.",
        "Atual": "Ainda aberta: compras novas continuam entrando nela.",
        "Fechada · a pagar": "O banco fechou o valor; falta o pagamento.",
        "Futura": "Parcelas contratadas que só serão cobradas nos "
                  "próximos meses.",
    }
    cores = {
        "Vencida": Colors.EXPENSE,
        "Atual": Colors.INFO,
        "Fechada · a pagar": Colors.WARNING,
        "Futura": Colors.NEUTRAL,
    }
    etiquetas = {
        "Vencida": "Vencida",
        "Atual": "Aberta",
        "Fechada · a pagar": "A pagar",
        "Futura": "Futura",
    }

    st.write("")
    for estado in ordem:
        grupo = [i for i in agendadas
                 if situacao[(i.card, i.month)] == estado]
        if not grupo:
            continue
        grupo.sort(key=lambda i: i.due)
        total = sum(_valor_da_fatura(i, banco) for i in grupo)
        components.section(f"{titulos[estado]} — {brl(total)}",
                           legendas[estado])
        # As futuras são muitas e cada uma importa pouco: ficam recolhidas
        # para não empurrar a fatura de hoje fora da tela.
        if estado == "Futura" and len(grupo) > 3:
            with st.expander(f"Ver {len(grupo)} fatura(s) futura(s)"):
                _lista_de_faturas(grupo, banco, cores[estado],
                                  etiquetas[estado])
        else:
            _lista_de_faturas(grupo, banco, cores[estado], etiquetas[estado])

    if any((i.card, i.month) not in banco for i in agendadas):
        st.caption(
            "Onde diz *soma das linhas*, o banco ainda não emitiu a "
            "fatura e o valor é a soma das compras que chegaram."
        )


def _lista_de_faturas(grupo: list, banco: dict[tuple[str, str], float],
                      cor: str, etiqueta: str) -> None:
    """Um cartão por fatura, na ordem de vencimento."""
    for i in grupo:
        do_banco = (i.card, i.month) in banco
        components.invoice_card(
            card=i.card, month=i.month,
            value=brl(_valor_da_fatura(i, banco)),
            state=etiqueta, accent=cor, negative=True,
            dates=(f"fecha {i.closing:%d/%m} · vence {i.due:%d/%m/%Y}"),
            source="do banco" if do_banco else "soma das linhas",
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
        components.table(previa, max_rows=30)
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
    """Um cartão, com o mesmo número que a visão consolidada mostra.

    Esta tela somava as linhas da planilha e nunca consultava o banco,
    enquanto a consolidada logo ao lado lia `positions.card_balances`. O
    mesmo cartão aparecia com dois valores conforme o seletor — e quem
    abre um cartão para conferir contra o print do aplicativo estava
    vendo justamente a versão que não fala com a instituição.
    """
    settings = cc.card_settings(df_cards, card)
    limite, disp_linhas = cc.available_limit(df_cards, df_tx, df_pay, card)
    abertas = cc.open_invoices(df_tx, df_pay, card=card)
    soma_linhas = sum(i.balance for i in abertas)

    do_banco = _saldo_do_banco().get(card)
    saldo = do_banco if do_banco is not None else soma_linhas
    disp = limite - saldo if do_banco is not None else disp_linhas

    if int(settings["vencimento"]) > int(settings["fechamento"]):
        quando = "vence dia {} do mesmo mês".format(settings["vencimento"])
    else:
        quando = "vence dia {} do mês seguinte".format(settings["vencimento"])
    components.section(
        card, f"Fecha todo dia {settings['fechamento']} · {quando}",
        eyebrow=settings["instituicao"] or "Cartão",
    )

    _drift_warning(df_cards, df_tx, card)

    uso = (saldo / limite * 100) if limite else 0.0
    esq, dir_ = st.columns(2)
    with esq:
        components.stat_card(
            label="Devendo agora", value=saldo, divida=True,
            bar=(saldo / limite) if limite else None,
            bar_label=(f"{uso:.0f}% do limite de {brl(limite)}"
                       if limite else "sem limite cadastrado"),
            rows=[{"nome": "Fonte",
                   "valor": "banco" if do_banco is not None
                            else "soma das linhas",
                   "classe": "mf-mut"}],
        )
    with dir_:
        components.stat_card(
            label="Disponível", value=disp,
            rows=[
                {"nome": "Limite", "valor": brl(limite), "bruto": limite},
                {"nome": "Uso do limite", "valor": f"{uso:.0f}%",
                 "classe": "mf-neg" if uso > 80 else "mf-pos",
                 "sub": "acima de 80%" if uso > 80 else "confortável"},
            ],
        )

    if do_banco is not None and abs(do_banco - soma_linhas) >= 1.0:
        _confronto_de_linhas(do_banco, soma_linhas, True)

    if not abertas:
        st.success("Nenhuma fatura em aberto neste cartão.")
        return

    # A mesma lista da consolidada, filtrada neste cartão: vencida,
    # atual, fechada e futura. Antes eram expanders por fatura, sem
    # situação nenhuma — duas telas para a mesma pergunta.
    _faturas(df_cards, df_tx, df_pay, [card], _faturas_do_banco())
    st.write("")
    components.section("Compras de cada fatura",
                       "Abra uma para ver o que a compõe.")

    st.write("")
    components.section("Faturas em aberto",
                       "Abra uma para ver as compras que a compõem.")
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
                components.table(compras, align_right=("Valor",))


def _invoice_lines(df_tx: pd.DataFrame, card: str, month: str) -> pd.DataFrame:
    if df_tx.empty:
        return pd.DataFrame()
    mask = (cc.card_series(df_tx) == card) & (
        df_tx["Mês da Fatura"].astype(str).str.strip() == month
    )
    cols = [c for c in ("Data Compra", "Descrição", "Categoria", "Parcela",
                        "Valor", "Status", "Origem") if c in df_tx.columns]
    out = df_tx.loc[mask, cols].copy()
    if "Valor" in out.columns:
        out["Valor"] = out["Valor"].apply(brl)
    # A origem existia no dado e nunca chegava à tela: uma parcela que o
    # app deduziu ficava indistinguível de uma que o banco cobrou. Como é
    # justamente o que o usuário precisa saber para conferir a fatura, a
    # coluna vira texto legível em vez do marcador interno.
    if "Origem" in out.columns:
        out["Origem"] = out["Origem"].map(_ORIGEM_LEGIVEL).fillna("do banco")
    return out


# Como cada origem se chama na tela. O valor gravado é interno; o que o
# usuário lê tem de dizer se pode confiar naquela linha.
_ORIGEM_LEGIVEL = {
    ORIGEM_BANCO: "do banco",
    ORIGEM_PROJECAO: "deduzida",
    ORIGEM_MANUAL: "digitada",
    "": "do banco",
}


# ---------------------------------------------------------------------------
# Pagamentos
# ---------------------------------------------------------------------------

def _payment_section(df_tx: pd.DataFrame, df_pay: pd.DataFrame,
                     names: list[str], card: str | None) -> None:
    components.section(
        "Pagar fatura",
        "Adiantar um valor ou dar baixa total. A baixa lança a saída em "
        "Entradas e Saídas pelo valor que faltava.",
        eyebrow="Cartão de crédito",
    )
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
    components.section(
        "Meus cartões",
        "Nome, limite e as datas de fechamento e vencimento de cada um.",
    )

    orfaos = cc.orphan_card_names(df_cards, df_tx)
    if orfaos:
        st.warning(
            "⚠️ Há compras em cartões que não estão cadastrados: **"
            + "**, **".join(orfaos)
            + "**. Cadastre-os abaixo para definir limite e datas."
        )

    # Cada um abre o seu próprio bloco recolhível. Antes vinham os quatro
    # empilhados e separados por divisores do mesmo peso: só o cadastro é
    # rotina, o resto é exceção e não precisa ocupar a tela até ser
    # pedido.
    _card_settings_form(df_cards, df_tx, df_pay, names)
    _new_card_form(names)
    _reschedule_section(df_cards, df_tx, df_pay, names)
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
        components.table(preview)

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
    periodo = (selected_month if selected_month != ALL_MONTHS
               else "todo o período")
    components.section(
        "Gastos por categoria",
        f"O que o cartão consumiu em {periodo}, por categoria.",
        eyebrow="Extrato",
    )

    view = df_period
    if card and not view.empty:
        view = view[cc.card_series(view) == card]
    if view.empty:
        st.info("Nenhuma compra neste período.")
    else:
        grouped = view.groupby("Categoria")["Valor"].sum().reset_index()
        components.vertical_bar(grouped, x="Categoria", y="Valor",
                                color=Colors.INVESTMENT)

    st.write("")
    components.section("Extrato completo",
                       "Edite as linhas livremente e clique em salvar.")

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
                # Duas colunas internas ficavam como texto livre. O
                # "ID Pluggy" é o que impede a mesma compra de entrar
                # duas vezes e o que diz ao removedor de duplicatas qual
                # linha veio do banco: digitar nele quebra as duas
                # coisas em silêncio. Ficam visíveis, porque explicam a
                # linha, e travadas, porque não são para editar.
                "ID Pluggy": st.column_config.TextColumn(
                    "ID do banco", disabled=True,
                    help="Vem da importação. Não edite: é o que impede a "
                         "compra de entrar duas vezes."),
                "Origem": st.column_config.TextColumn(
                    "Origem", disabled=True,
                    help="Quem trouxe a linha: o banco, uma dedução de "
                         "parcelamento ou digitação manual."),
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
