"""Página: Cartão de Crédito.

Tudo que esta tela mostra sai do livro de faturas (`src/card_book.py`).
Ela não calcula nada: pergunta ao livro e desenha. Por isso cada número
tem uma origem só, e a mesma fatura vale o mesmo aqui e no Dashboard.

Três abas, por pergunta:

- **Faturas** — quanto vou pagar e quando: a aberta, as fechadas a
  pagar, as próximas (com as parcelas que ainda vão cair) e o histórico.
- **Compras** — o que compõe cada fatura, e a categoria de cada compra.
- **Cartões** — nome, limite e datas; só se mexe aqui uma vez.

Não há aba de ajustes nem botão de manutenção. Realinhar mês de fatura,
dar baixa no que venceu, tirar cópia e projeção antiga — a sincronização
faz sozinha, a cada vez (ver `src/sync.py`).
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from src import card_book as cb
from src import components, credit_card as cc, repository
from src.config import (Colors, ConfigKeys, DEFAULT_CARD_NAME, ORIGEM_BANCO,
                        ORIGEM_MANUAL, ORIGEM_PROJECAO)
from src.format import brl, md

# Como cada origem de linha se chama na tela.
_ORIGEM = {ORIGEM_BANCO: "do banco", ORIGEM_PROJECAO: "parcela a cair",
           ORIGEM_MANUAL: "digitada", "": "do banco"}

_COR = {cb.ABERTA: Colors.INFO, cb.A_PAGAR: Colors.WARNING,
        cb.FUTURA: Colors.NEUTRAL, cb.PAGA: Colors.PRIMARY}


def render(*, df_credit_card: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           categories: list[str], selected_month: str) -> None:
    df_cards = repository.load_cards()
    if df_cards.empty and (df_credit_card is None or df_credit_card.empty):
        components.page_header("Cartão de Crédito")
        _primeiro_cartao()
        return

    livros = cb.load(df_credit_card=df_credit_card, df_cards=df_cards)
    components.page_header("Cartão de Crédito", _origem_dos_numeros())

    _resumo(livros)
    _conferencia(livros)

    aba_fat, aba_compras, aba_cartoes = st.tabs(
        ["💳 Faturas", "🧾 Compras", "⚙️ Cartões"])
    with aba_fat:
        _faturas(livros)
    with aba_compras:
        _compras(df_credit_card, livros, categories, selected_month)
    with aba_cartoes:
        _cartoes(df_cards, df_credit_card, livros, categories)


def _origem_dos_numeros() -> str:
    lido = cb.read_at()
    sync = repository.load_config_text(ConfigKeys.PLUGGY_ULTIMA_SYNC)
    quando = _hora(sync or lido)
    if not quando:
        return ("Ainda não houve sincronização com o banco: os números "
                "abaixo são a soma das compras lançadas.")
    return (f"Sincronizado com o banco em {quando}. Total, fechamento e "
            "vencimento das faturas vêm da instituição sempre que ela "
            "informa.")


def _hora(carimbo: str) -> str:
    if not carimbo:
        return ""
    try:
        return datetime.fromisoformat(carimbo).strftime("%d/%m às %H:%M")
    except ValueError:
        return carimbo


# ---------------------------------------------------------------------------
# Resumo: um cartão por cartão
# ---------------------------------------------------------------------------

def _resumo(livros: list[cb.CartaoLivro]) -> None:
    """Para cada cartão: a fatura aberta, a próxima a pagar e o limite.

    Um número grande por cartão — a fatura aberta, que é o que o app do
    banco mostra primeiro — e logo abaixo o que vem antes dela sair da
    conta. Saldo devedor, soma de linhas e limite usado não aparecem lado
    a lado aqui: eram três medidas diferentes com a mesma cara, e
    compará-las era o que fazia o app parecer errado.
    """
    colunas = st.columns(min(len(livros), 3) or 1)
    for i, livro in enumerate(livros):
        with colunas[i % len(colunas)]:
            _cartao_resumo(livro)


def _cartao_resumo(livro: cb.CartaoLivro) -> None:
    """O número grande é a próxima fatura a sair da conta.

    É a fechada a pagar, se houver; senão, a aberta. As outras entram
    como linhas, sem repetir a que já está no título.
    """
    proxima = livro.proxima_a_vencer
    linhas: list[dict] = []
    for f in sorted(livro.a_pagar + ([livro.atual] if livro.atual else []),
                    key=lambda f: f.vencimento):
        if f is proxima:
            continue
        linhas.append({
            "nome": ("Fatura aberta" if f.situacao == cb.ABERTA
                     else f"Fechada {f.mes}"),
            "sub": (f"fecha {f.fechamento:%d/%m} · vence "
                    f"{f.vencimento:%d/%m}"
                    + ("" if f.datas_do_banco else " (pelo cadastro)")),
            "valor": brl(f.total), "divida": True,
        })
    if livro.limite:
        disp = livro.disponivel if livro.disponivel is not None else 0.0
        linhas.append({
            "nome": "Limite disponível",
            "sub": (f"de {brl(livro.limite)}"
                    + (" · do banco" if livro.limites_do_banco
                       else " · pelo cadastro")),
            "valor": brl(disp), "bruto": disp,
        })

    valor = proxima.total if proxima else 0.0
    if proxima is None:
        rotulo = f"{livro.nome} · nada a pagar"
    else:
        estado = ("fatura aberta" if proxima.situacao == cb.ABERTA
                  else f"fechada {proxima.mes}")
        rotulo = (f"{livro.nome} · {estado}, vence "
                  f"{proxima.vencimento:%d/%m}")
    usado = (livro.limite - livro.disponivel
             if livro.limite and livro.disponivel is not None else None)
    components.stat_card(
        label=rotulo, value=valor, divida=True, rows=linhas,
        bar=(usado / livro.limite) if usado is not None and livro.limite
        else None,
        bar_label=(f"{usado / livro.limite * 100:.0f}% do limite em uso"
                   if usado is not None and livro.limite else ""),
    )


def _conferencia(livros: list[cb.CartaoLivro]) -> None:
    """O livro fecha com o banco? Se não, quanto e por quê.

    Uma frase por cartão, só quando há diferença. Substitui os três
    avisos antigos que comparavam medidas diferentes entre si.
    """
    for livro in livros:
        if livro.ilegiveis:
            st.warning(md(
                f"⚠️ **{livro.nome}**: compras com o mês da fatura ilegível "
                f"({', '.join(livro.ilegiveis[:4])}) ficaram de fora. Corrija "
                "o campo **Mês da Fatura** em Compras — o formato é MM/AAAA."))
        if livro.datas_estimadas:
            st.info(md(
                f"**{livro.nome}** não tem datas do banco nem do cadastro: "
                "o app supõe fechamento dia 8 e vencimento dia 15. "
                "Cadastre as datas certas na aba **Cartões**."))

        diff = livro.diferenca_banco
        if diff is None or abs(diff) <= cb.TOLERANCIA:
            continue
        if diff > 0:
            st.info(md(
                f"**{livro.nome}**: o banco informa {brl(livro.usado_banco)} "
                f"de limite em uso; as faturas em aberto e as parcelas que "
                f"ainda vão cair somam {brl(livro.compromisso)}. Faltam "
                f"**{brl(diff)}** — quase sempre é compra que ainda não "
                "chegou pela sincronização, ou parcelamento antigo cujas "
                "parcelas o banco não detalha."))
        else:
            st.info(md(
                f"**{livro.nome}**: as faturas em aberto e as parcelas a "
                f"cair somam **{brl(-diff)} a mais** que o limite em uso "
                f"informado pelo banco ({brl(livro.usado_banco)}). Costuma "
                "ser compra digitada à mão que o banco também trouxe, ou "
                "parcelamento antecipado."))


# ---------------------------------------------------------------------------
# Faturas
# ---------------------------------------------------------------------------

def _escolher(livros: list[cb.CartaoLivro], chave: str) -> cb.CartaoLivro:
    if len(livros) == 1:
        return livros[0]
    nome = st.radio("Cartão", [c.nome for c in livros], horizontal=True,
                    key=chave, label_visibility="collapsed")
    return next(c for c in livros if c.nome == nome)


def _faturas(livros: list[cb.CartaoLivro]) -> None:
    if not livros:
        st.info("Nenhum cartão ainda.")
        return
    livro = _escolher(livros, "fat_cartao")

    if livro.atual:
        f = livro.atual
        components.section(
            "Fatura aberta",
            "Ainda recebe compras. O total sobe até o fechamento.",
            eyebrow=livro.nome)
        _bloco(f)
        _composicao(f, aberta=True)

    if livro.a_pagar:
        st.write("")
        components.section(
            "Fechadas, a pagar",
            "O banco já fechou o valor; falta o vencimento chegar.")
        for f in livro.a_pagar:
            _bloco(f)
            with st.expander(f"Compras da fatura {f.mes}"):
                _composicao(f)

    if livro.futuras:
        st.write("")
        total = sum(f.total for f in livro.futuras)
        components.section(
            f"Próximas faturas — {brl(total)}",
            "Parcelas já contratadas que vão cair nos próximos meses. "
            "Entram na projeção do Dashboard.")
        components.table(pd.DataFrame([{
            "Fatura": f.mes,
            "Fecha": f"{f.fechamento:%d/%m/%Y}",
            "Vence": f"{f.vencimento:%d/%m/%Y}",
            "Parcelas": len(f.compras) + len(f.projetadas),
            "Total": brl(f.total),
        } for f in livro.futuras]), align_right=("Parcelas", "Total"))
        with st.expander("Ver as parcelas de cada mês"):
            components.table(_linhas(livro.futuras),
                             align_right=("Valor",))

    pagas = livro.pagas[:12]
    if pagas:
        st.write("")
        with st.expander(f"Histórico — {len(pagas)} fatura(s) paga(s)"):
            components.table(pd.DataFrame([{
                "Fatura": f.mes,
                "Venceu": f"{f.vencimento:%d/%m/%Y}",
                "Total": brl(f.total),
                "Valor de": ("banco" if f.fonte == cb.FONTE_BANCO
                             else "soma das compras"),
            } for f in pagas]), align_right=("Total",))

    if not livro.faturas:
        st.info("Nenhuma fatura neste cartão ainda.")


def _bloco(f: cb.Fatura) -> None:
    fonte = ("total informado pelo banco" if f.fonte == cb.FONTE_BANCO
             else "soma das compras")
    components.invoice_card(
        card=f.cartao, month=f.mes, value=brl(f.total),
        state=f.situacao, accent=_COR.get(f.situacao, Colors.NEUTRAL),
        dates=(f"fecha {f.fechamento:%d/%m/%Y} · vence "
               f"{f.vencimento:%d/%m/%Y}"
               + ("" if f.datas_do_banco else " · datas pelo cadastro")),
        source=fonte, negative=True)
    falta = f.nao_chegaram
    if abs(falta) > cb.TOLERANCIA:
        if falta > 0:
            st.caption(md(
                f"{brl(falta)} desta fatura ainda não chegou como compra. "
                "O total acima é o do banco; a lista abaixo é o que já foi "
                "importado."))
        else:
            st.caption(md(
                f"As compras desta fatura somam {brl(-falta)} a mais que o "
                "total do banco — confira se há compra digitada repetida."))


def _linhas(faturas: list[cb.Fatura]) -> pd.DataFrame:
    """Compras gravadas + parcelas a cair, numa tabela só, por fatura."""
    linhas = []
    for f in faturas:
        if not f.compras.empty:
            for _, r in f.compras.iterrows():
                valor = pd.to_numeric(r.get("Valor"), errors="coerce")
                linhas.append({
                    "Fatura": f.mes,
                    "Data": str(r.get("Data Compra") or "")[:10],
                    "Descrição": r.get("Descrição"),
                    "Parcela": r.get("Parcela") or "",
                    "Categoria": r.get("Categoria") or "",
                    "Valor": brl(0.0 if pd.isna(valor) else float(valor)),
                    "Origem": _ORIGEM.get(str(r.get("Origem") or "").strip(),
                                          "do banco"),
                })
        for p in f.projetadas:
            linhas.append({
                "Fatura": f.mes, "Data": str(p.get("Data Compra") or "")[:10],
                "Descrição": p["Descrição"], "Parcela": p["Parcela"],
                "Categoria": p.get("Categoria") or "",
                "Valor": brl(p["Valor"]), "Origem": _ORIGEM[ORIGEM_PROJECAO],
            })
    return pd.DataFrame(linhas)


def _composicao(f: cb.Fatura, *, aberta: bool = False) -> None:
    tabela = _linhas([f]).drop(columns=["Fatura"], errors="ignore")
    if tabela.empty:
        st.caption("Nenhuma compra nesta fatura ainda.")
        return
    components.table(tabela, align_right=("Valor",))
    if not f.quitacoes.empty:
        pago = float(pd.to_numeric(f.quitacoes["Valor"],
                                   errors="coerce").fillna(0).sum())
        st.caption(md(
            f"O pagamento de {brl(abs(pago))} feito nesta fatura quitou a "
            "fatura anterior — no banco ele cancela o saldo anterior, então "
            "não entra no total desta."))
    if f.projetadas:
        st.caption(
            f"{len(f.projetadas)} linha(s) marcada(s) como *parcela a cair* "
            "são parcelas de compras anteriores que o banco ainda não "
            "lançou. O app as deduz das parcelas já cobradas e troca pela "
            "cobrança real quando ela chega.")


# ---------------------------------------------------------------------------
# Compras
# ---------------------------------------------------------------------------

def _compras(df_tx: pd.DataFrame, livros: list[cb.CartaoLivro],
             categories: list[str], selected_month: str) -> None:
    components.section(
        "Compras e categorias",
        "Escolha uma fatura para ver o que a compõe e ajustar as "
        "categorias. Só a categoria é editável: valor, data e fatura vêm "
        "do banco.", eyebrow="Compras")

    if df_tx is None or df_tx.empty:
        st.info(md("Nenhuma compra ainda. A **Sincronização** traz as do "
                   "banco sozinha."))
        _compra_manual(livros, categories)
        return

    livro = _escolher(livros, "compras_cartao")
    meses = [f.mes for f in sorted(livro.faturas, key=lambda f: f.fechamento,
                                   reverse=True)
             if not f.compras.empty]
    if not meses:
        st.caption("Este cartão não tem compras gravadas.")
        _compra_manual(livros, categories)
        return
    padrao = (livro.atual.mes if livro.atual and livro.atual.mes in meses
              else meses[0])
    if selected_month in meses:
        padrao = selected_month
    mes = st.selectbox("Fatura", meses, index=meses.index(padrao),
                       key="compras_mes")

    mascara = ((cc.card_series(df_tx) == livro.nome)
               & (cc._month_series(df_tx) == mes))
    origem = (df_tx["Origem"].astype(str).str.strip()
              if "Origem" in df_tx.columns
              else pd.Series("", index=df_tx.index))
    mascara &= origem != ORIGEM_PROJECAO
    recorte = df_tx[mascara]

    por_categoria = (recorte.assign(Valor=pd.to_numeric(recorte["Valor"],
                                                        errors="coerce"))
                     .groupby("Categoria")["Valor"].sum().reset_index())
    por_categoria = por_categoria[por_categoria["Valor"] > 0]
    if not por_categoria.empty:
        components.horizontal_bar_expenses(por_categoria)

    vistas = [c for c in ("Data Compra", "Descrição", "Parcela", "Valor",
                          "Categoria") if c in recorte.columns]
    opcoes = sorted(set(categories)
                    | set(recorte["Categoria"].dropna().astype(str)))
    with st.form("compras_categorias"):
        editada = st.data_editor(
            recorte[vistas], hide_index=True, use_container_width=True,
            disabled=[c for c in vistas if c != "Categoria"],
            column_config={
                "Valor": st.column_config.NumberColumn("Valor",
                                                       format="R$ %.2f"),
                "Categoria": st.column_config.SelectboxColumn(
                    "Categoria", options=opcoes, required=True),
            },
            key="compras_editor",
        )
        if st.form_submit_button("💾 Salvar categorias"):
            mudou = (editada["Categoria"].astype(str)
                     != recorte["Categoria"].astype(str))
            if not mudou.any():
                st.info("Nenhuma categoria mudou.")
            else:
                novo = df_tx.copy()
                novo.loc[editada.index[mudou], "Categoria"] = \
                    editada.loc[mudou, "Categoria"]
                repository.save_credit_card(novo)
                st.success(f"{int(mudou.sum())} categoria(s) salva(s).")
                st.rerun()

    _compra_manual(livros, categories)


def _compra_manual(livros: list[cb.CartaoLivro], categories: list[str]) -> None:
    """Lançar o que não passa pelo banco — exceção, não rotina.

    Grava UMA linha, a primeira parcela, como o banco faz. As parcelas
    seguintes o livro deduz sozinho. Espalhar a compra em N linhas de uma
    vez, como a versão antiga fazia, criava parcelas que depois brigavam
    com as cobranças reais.
    """
    if not livros:
        return
    with st.expander("➕ Lançar uma compra que não veio do banco"):
        st.caption(md(
            "Só para o que a sincronização não traz. O que passa no cartão "
            "conectado chega sozinho — lançar aqui também duplicaria."))
        with st.form("compra_manual", clear_on_submit=True):
            c1, c2 = st.columns(2)
            cartao = c1.selectbox("Cartão", [c.nome for c in livros])
            quando = c2.date_input("Data da compra", value=date.today(),
                                   format="DD/MM/YYYY")
            desc = st.text_input("Descrição")
            c3, c4, c5 = st.columns(3)
            valor = c3.number_input("Valor da parcela (R$)", min_value=0.01,
                                    step=10.0, value=10.0)
            parcelas = c4.number_input("Parcelas", min_value=1, max_value=48,
                                       step=1, value=1)
            categoria = c5.selectbox("Categoria", categories)
            if st.form_submit_button("Lançar"):
                if not desc.strip():
                    st.error("Informe uma descrição.")
                    return
                livro = next(c for c in livros if c.nome == cartao)
                mes = _mes_da_compra(livro, quando)
                atual = repository.load_credit_card()
                repository.save_credit_card(pd.concat([atual, pd.DataFrame([{
                    "Data Compra": quando.isoformat(), "Mês da Fatura": mes,
                    "Cartão": cartao, "Descrição": desc.strip(),
                    "Categoria": categoria,
                    "Parcela": f"1/{int(parcelas)}", "Valor": float(valor),
                    "Status": "Pendente", "ID Pluggy": "",
                    "Origem": ORIGEM_MANUAL,
                }])], ignore_index=True))
                st.success(f"Lançada na fatura {mes}"
                           + (f"; as outras {int(parcelas) - 1} parcelas o "
                              "app deduz sozinho." if parcelas > 1 else "."))
                st.rerun()


def _mes_da_compra(livro: cb.CartaoLivro, quando: date) -> str:
    """A fatura em que uma compra cai: a primeira que fecha depois dela.

    Usa as datas do livro — que são as do banco quando ele informa — e só
    recorre à regra do dia de fechamento cadastrado se nenhuma fatura
    conhecida fechar depois da compra.
    """
    candidatas = sorted((f for f in livro.faturas if f.fechamento >= quando),
                        key=lambda f: f.fechamento)
    if candidatas:
        return candidatas[0].mes
    settings = cc.card_settings(repository.load_cards(), livro.nome)
    return cc.invoice_month_for_purchase(
        quando, int(settings["fechamento"])).strftime("%m/%Y")


# ---------------------------------------------------------------------------
# Cartões
# ---------------------------------------------------------------------------

def _cartoes(df_cards: pd.DataFrame, df_tx: pd.DataFrame,
             livros: list[cb.CartaoLivro], categories: list[str]) -> None:
    components.section(
        "Seus cartões",
        "Nome e, para cartão que o banco não detalha, limite e datas. "
        "Quando o banco informa, os números dele têm prioridade e o "
        "cadastro vira só a reserva.", eyebrow="Cartões")

    nomes = [c.nome for c in livros]
    if not nomes:
        _primeiro_cartao()
        return
    alvo = st.selectbox("Cartão", nomes, key="cfg_cartao")
    livro = next(c for c in livros if c.nome == alvo)
    s = cc.card_settings(df_cards, alvo)

    if livro.limites_do_banco or (livro.atual and livro.atual.datas_do_banco):
        partes = []
        if livro.limites_do_banco:
            partes.append(f"limite {brl(livro.limite)}")
        if livro.atual and livro.atual.datas_do_banco:
            partes.append(f"fatura aberta fecha "
                          f"{livro.atual.fechamento:%d/%m} e vence "
                          f"{livro.atual.vencimento:%d/%m}")
        st.caption(md("O banco informa: " + ", ".join(partes) + "."))

    with st.form("cfg_cartao_form"):
        c1, c2 = st.columns(2)
        novo_nome = c1.text_input("Nome", value=alvo)
        inst = c2.text_input("Instituição", value=s["instituicao"])
        c3, c4, c5 = st.columns(3)
        limite = c3.number_input("Limite (R$)", min_value=0.0, step=100.0,
                                 value=float(s["limite"]))
        fech = c4.number_input("Dia de fechamento", min_value=1,
                               max_value=31, step=1,
                               value=int(s["fechamento"]))
        venc = c5.number_input("Dia de vencimento", min_value=1,
                               max_value=31, step=1,
                               value=int(s["vencimento"]))
        if st.form_submit_button("💾 Salvar"):
            _salvar_cartao(df_cards, df_tx, alvo, novo_nome.strip(),
                           inst.strip(), limite, fech, venc, nomes)

    with st.expander("➕ Cadastrar outro cartão"):
        _formulario_novo(nomes)

    with st.expander("🗑️ Excluir este cartão"):
        compras = (int((cc.card_series(df_tx) == alvo).sum())
                   if df_tx is not None and not df_tx.empty else 0)
        st.caption(f"{alvo} tem {compras} compra(s) gravada(s); elas serão "
                   "apagadas junto. Entradas e Saídas não é afetada.")
        confirmar = st.text_input(f"Digite {alvo} para confirmar",
                                  key="cfg_excluir")
        if st.button("Excluir cartão", key="cfg_excluir_btn"):
            if confirmar.strip() != alvo:
                st.error("O nome não confere.")
            else:
                cards, tx, pay = cc.delete_card(
                    df_cards, df_tx, repository.load_card_payments(), alvo,
                    move_to=None)
                repository.save_cards(cards)
                repository.save_credit_card(tx)
                repository.save_card_payments(pay)
                st.success(f"{alvo} excluído.")
                st.rerun()


def _salvar_cartao(df_cards, df_tx, alvo, novo, inst, limite, fech, venc,
                   nomes) -> None:
    if not novo:
        st.error("Informe um nome.")
        return
    if novo != alvo and novo in nomes:
        st.error(f"Já existe um cartão chamado {novo}.")
        return
    cards = df_cards
    if novo != alvo:
        cards, tx, pay = cc.rename_card(df_cards, df_tx,
                                        repository.load_card_payments(),
                                        alvo, novo)
        repository.save_credit_card(tx)
        repository.save_card_payments(pay)
    if cards.empty or "Nome" not in cards.columns or \
            novo not in set(cards["Nome"].astype(str).str.strip()):
        cards = pd.concat([cards, pd.DataFrame([{"Nome": novo}])],
                          ignore_index=True)
    m = cards["Nome"].astype(str).str.strip() == novo
    cards.loc[m, "Instituição"] = inst
    cards.loc[m, "Limite"] = limite
    cards.loc[m, "Dia Fechamento"] = fech
    cards.loc[m, "Dia Vencimento"] = venc
    repository.save_cards(cards)
    st.success(f"{novo} salvo.")
    st.rerun()


def _formulario_novo(nomes: list[str], *, chave: str = "novo_cartao",
                     padrao: str = "") -> None:
    with st.form(chave, clear_on_submit=True):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome do cartão", value=padrao,
                             placeholder="Ex.: Nubank")
        inst = c2.text_input("Instituição")
        c3, c4, c5 = st.columns(3)
        limite = c3.number_input("Limite (R$)", min_value=0.0, step=100.0,
                                 value=1000.0)
        fech = c4.number_input("Dia de fechamento", min_value=1,
                               max_value=31, value=8, step=1)
        venc = c5.number_input("Dia de vencimento", min_value=1,
                               max_value=31, value=15, step=1)
        if st.form_submit_button("Cadastrar"):
            limpo = nome.strip()
            if not limpo:
                st.error("Informe um nome.")
            elif limpo in nomes:
                st.error(f"{limpo} já existe.")
            else:
                repository.save_cards(pd.concat([
                    repository.load_cards(), pd.DataFrame([{
                        "Nome": limpo, "Instituição": inst.strip(),
                        "Limite": limite, "Dia Fechamento": fech,
                        "Dia Vencimento": venc}])], ignore_index=True))
                st.success(f"{limpo} cadastrado.")
                st.rerun()


def _primeiro_cartao() -> None:
    st.info("Nenhum cartão cadastrado ainda. Cadastre o primeiro — depois "
            "é só ligar a conta dele em **Sincronização → Contas "
            "conectadas**.")
    _formulario_novo([], chave="primeiro_cartao", padrao=DEFAULT_CARD_NAME)

