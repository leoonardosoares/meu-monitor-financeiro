"""Página: Importar (Open Finance).

O trabalho mensal do usuário vive aqui: sincronizar e categorizar. A
configuração da conexão fica em Configurações → Open Finance, porque é
feita uma vez por ano; esta página é a que se abre toda semana.

Nada é gravado pela sincronização. Ela só monta a lista; a gravação
acontece quando o usuário aceita, e as três abas (`financeiro`, `cartao`
e `importacoes`) são gravadas na mesma ação — se o registro de
importação ficasse para depois, uma falha no meio traria tudo de novo na
próxima vez.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from src import components, credit_card as cc, pluggy, repository
from src import pluggy_import as pi
from src.config import ConfigKeys
from src.finance import suggest_category
from src.format import brl


def render(*, df_transactions: pd.DataFrame, df_credit_card: pd.DataFrame,
           df_cards: pd.DataFrame, categories: list[str]) -> None:
    components.page_header(
        "Importar do banco",
        "Traz os lançamentos das contas conectadas. Você confere e "
        "categoriza antes de qualquer coisa ir para a planilha.",
    )

    if not pluggy.is_configured():
        st.info(
            "Nenhum banco conectado ainda. Vá em **Configurações e "
            "Orçamento → Open Finance** para conectar."
        )
        return

    ids = [i.strip() for i in
           repository.load_config_text(ConfigKeys.PLUGGY_ITEMS).split(",")
           if i.strip()]
    if not ids:
        st.info(
            "As credenciais existem, mas nenhuma conexão foi informada. "
            "Termine o passo 2 em **Configurações e Orçamento → Open "
            "Finance**."
        )
        return

    contas, avisos = _load_accounts(ids)
    for aviso in avisos:
        st.warning(f"⚠️ {aviso}")
    if not contas:
        return

    destinos = _mapping_section(contas, df_cards, df_credit_card)
    st.divider()
    _sync_section(
        contas=contas, destinos=destinos, df_cards=df_cards,
        df_transactions=df_transactions, df_credit_card=df_credit_card,
        categories=categories,
    )


@st.cache_data(ttl=300, show_spinner="Consultando seus bancos…")
def _load_accounts(ids: list[str]) -> tuple[list[dict], list[str]]:
    """Contas de todas as conexões, com aviso por conexão que falhar.

    Em cache curto: a página recarrega a cada clique do Streamlit, e sem
    isso cada interação viraria uma ida à API.
    """
    contas, avisos = [], []
    for item_id in ids:
        try:
            item = pluggy.item(item_id)
            for conta in pluggy.list_accounts(item_id):
                conta["_conexao"] = (item.get("connector") or {}).get(
                    "name") or item_id[:8]
                conta["_status"] = item.get("status")
                contas.append(conta)
        except pluggy.PluggyError as exc:
            avisos.append(f"Conexão {item_id[:8]}…: {exc}")
    return contas, avisos


def _mapping_section(contas: list[dict], df_cards: pd.DataFrame,
                     df_credit_card: pd.DataFrame) -> dict[str, str]:
    """Para onde cada conta da Pluggy é importada."""
    st.subheader("Para onde vai cada conta")
    st.caption(
        "Diga uma vez e o app lembra. Sem isso ele não teria como saber "
        "que o *platinum* da Pluggy é o seu cartão cadastrado aqui — e "
        "criaria um cartão novo a cada importação."
    )

    cartoes = cc.list_card_names(df_cards, df_credit_card)
    opcoes = [pi.DESTINO_BANCO, *cartoes, pi.DESTINO_IGNORAR]
    salvo = pi.parse_mapping(
        repository.load_config_text(ConfigKeys.PLUGGY_MAPA))

    with st.form("mapa_contas"):
        escolhas: dict[str, str] = {}
        for conta in contas:
            chave = pi.account_key(conta)
            rotulo = pi.account_label(conta)
            tipo = str(conta.get("type") or "").upper()
            # Um palpite razoável na primeira vez: conta corrente vai
            # para o caixa, cartão espera o usuário dizer qual é.
            padrao = salvo.get(
                chave, pi.DESTINO_BANCO if tipo == "BANK" else pi.DESTINO_IGNORAR)
            indice = opcoes.index(padrao) if padrao in opcoes else len(opcoes) - 1
            c1, c2 = st.columns([2, 1])
            c1.markdown(
                f"**{rotulo}** · {conta.get('_conexao')} · {tipo or '—'} · "
                f"saldo {brl(float(conta.get('balance') or 0))}"
            )
            escolhas[chave] = c2.selectbox(
                "Destino", opcoes, index=indice, key=f"dest_{chave}",
                label_visibility="collapsed",
            )
        if st.form_submit_button("💾 Salvar destinos"):
            repository.save_config_text(
                ConfigKeys.PLUGGY_MAPA, pi.format_mapping(escolhas))
            st.success("Destinos salvos.")
            st.rerun()

    return {**salvo, **escolhas}


def _sync_section(*, contas: list[dict], destinos: dict[str, str],
                  df_cards: pd.DataFrame, df_transactions: pd.DataFrame,
                  df_credit_card: pd.DataFrame,
                  categories: list[str]) -> None:
    st.subheader("Sincronizar")
    ativas = [c for c in contas
              if destinos.get(pi.account_key(c), "") not in
              ("", pi.DESTINO_IGNORAR)]
    if not ativas:
        st.info("Escolha ao menos um destino acima para poder sincronizar.")
        return

    st.caption(
        f"{len(ativas)} conta(s) serão consultadas. Esta etapa **não grava "
        "nada** — ela só monta a lista para você conferir."
    )

    # A proteção contra duplicata só conhece os ids que ESTE app já
    # importou. O que você digitou à mão não tem id nenhum, então trazer
    # o histórico inteiro duplicaria meses de lançamentos manuais.
    padrao = repository.load_config_text(ConfigKeys.PLUGGY_DESDE)
    try:
        inicial = date.fromisoformat(padrao) if padrao else date.today()
    except ValueError:
        inicial = date.today()
    desde = st.date_input(
        "Trazer lançamentos a partir de", value=inicial, format="DD/MM/YYYY",
        help=("A Pluggy guarda 12 meses. Como os seus lançamentos manuais "
              "não têm identificador, o app não consegue reconhecê-los — "
              "trazer período que você já digitou cria linha repetida."),
    )
    if str(desde) != padrao:
        repository.save_config_text(ConfigKeys.PLUGGY_DESDE, str(desde))
    # Busca sozinho quando a última foi há mais de meio dia: a ideia é
    # o usuário abrir o app e já encontrar a lista pronta, em vez de ter
    # de lembrar de clicar. O carimbo evita repetir a cada rerun do
    # Streamlit, que acontece a cada clique em qualquer lugar da página.
    automatico = (st.session_state.get("pluggy_pendentes") is None
                  and _stale(hours=12))
    c1, c2 = st.columns([1, 2])
    manual = c1.button("🔄 Buscar lançamentos novos", type="primary")
    if automatico:
        c2.caption("Buscando sozinho — faz isso quando passa de 12 horas.")
    if manual or automatico:
        _fetch_into_state(ativas, destinos, df_cards, df_transactions,
                          desde=desde)
        repository.save_config_text(
            ConfigKeys.PLUGGY_ULTIMA_SYNC, date.today().isoformat() + "T"
            + datetime.now().strftime("%H:%M"))

    pendentes = st.session_state.get("pluggy_pendentes")
    if pendentes is None:
        return
    for aviso in st.session_state.get("pluggy_avisos", []):
        st.warning(f"⚠️ {aviso}")
    if not pendentes:
        # "Em dia" só é verdade quando as contas realmente responderam.
        # Dizer isso depois de todas falharem esconderia a falha.
        if st.session_state.get("pluggy_falhou"):
            st.error(
                "Nenhuma conta pôde ser consultada — os avisos acima "
                "explicam por quê. Isto **não** significa que está em dia."
            )
        else:
            st.success("Nada novo — sua planilha já está em dia.")
        return

    _triage(pendentes, categories, df_credit_card, df_transactions)


def _stale(*, hours: int) -> bool:
    """Se a última busca é antiga o bastante para valer outra."""
    carimbo = repository.load_config_text(ConfigKeys.PLUGGY_ULTIMA_SYNC)
    if not carimbo:
        return True
    try:
        quando = datetime.fromisoformat(carimbo)
    except ValueError:
        return True
    return (datetime.now() - quando).total_seconds() >= hours * 3600


def _fetch_into_state(ativas, destinos, df_cards, df_transactions,
                      *, desde) -> None:
    transacoes: dict[str, list[dict]] = {}
    faturas: dict[str, list[dict]] = {}
    avisos: list[str] = []
    with st.spinner("Buscando lançamentos…"):
        for conta in ativas:
            chave = pi.account_key(conta)
            try:
                transacoes[chave] = pluggy.list_transactions(chave)
            except pluggy.PluggyError as exc:
                avisos.append(f"{pi.account_label(conta)}: {exc}")
            # As faturas dizem a qual delas cada compra pertence, o que
            # dispensa deduzir pelo dia de fechamento cadastrado.
            if str(conta.get("type") or "").upper() == "CREDIT":
                try:
                    faturas[chave] = pluggy.list_bills(chave)
                except pluggy.PluggyError as exc:
                    avisos.append(
                        f"{pi.account_label(conta)} (faturas): {exc}")

        pendentes, mais = pi.build_pending(
            accounts=[(c, destinos.get(pi.account_key(c), "")) for c in ativas],
            transactions=transacoes,
            ja_importados=repository.imported_ids(),
            df_cards=df_cards, desde=desde, bills=faturas,
            sugerir=lambda d: suggest_category(d, df_transactions),
        )
    # As faturas do banco são guardadas mesmo que nada novo entre: elas
    # são o total que a tela do cartão precisa para se conferir.
    linhas_fatura: list[dict] = []
    for conta in ativas:
        chave = pi.account_key(conta)
        destino = destinos.get(chave, "")
        if chave not in faturas or destino in ("", pi.DESTINO_BANCO,
                                               pi.DESTINO_IGNORAR):
            continue
        settings = cc.card_settings(df_cards, destino)
        linhas_fatura += pi.bill_rows(
            faturas[chave], cartao=destino,
            closing_day=int(settings["fechamento"]),
            due_day=int(settings["vencimento"]), lido_em=date.today())
    if linhas_fatura:
        repository.merge_bank_bills(linhas_fatura)
    _aprender_datas(ativas, destinos, transacoes, faturas, df_cards)

    st.session_state["pluggy_pendentes"] = pendentes
    st.session_state["pluggy_avisos"] = avisos + mais
    st.session_state["pluggy_falhou"] = bool(avisos) and not transacoes


def _aprender_datas(ativas, destinos, transacoes, faturas,
                    df_cards: pd.DataFrame) -> None:
    """Grava no cadastro o fechamento e o vencimento deduzidos do banco.

    O usuário não deveria precisar saber esses dias de cor — e errar um
    deles deslocava fatura inteira. Só escreve quando o valor deduzido
    difere do cadastrado, para não gravar na planilha a cada busca.
    """
    cards = repository.load_cards()
    mudou = False
    avisos: list[str] = []

    for conta in ativas:
        chave = pi.account_key(conta)
        destino = destinos.get(chave, "")
        if (str(conta.get("type") or "").upper() != "CREDIT"
                or destino in ("", pi.DESTINO_BANCO, pi.DESTINO_IGNORAR)):
            continue
        fech, venc = pi.infer_card_days(
            faturas.get(chave, []), transacoes.get(chave, []))
        atual = cc.card_settings(df_cards, destino)
        novos = {}
        if fech and fech != int(atual["fechamento"]):
            novos["Dia Fechamento"] = fech
        if venc and venc != int(atual["vencimento"]):
            novos["Dia Vencimento"] = venc
        if not novos:
            continue
        if cards.empty or "Nome" not in cards.columns:
            continue
        alvo = cards["Nome"].astype(str).str.strip() == destino
        if not alvo.any():
            continue
        for coluna, valor in novos.items():
            cards.loc[alvo, coluna] = valor
        mudou = True
        avisos.append(
            f"**{destino}**: " + ", ".join(
                f"{'fechamento' if 'Fech' in k else 'vencimento'} dia {v}"
                for k, v in novos.items()))

    if mudou:
        repository.save_cards(cards)
        st.info(
            "📆 Datas atualizadas a partir do banco — " + " · ".join(avisos)
        )


def _triage(pendentes: list, categories: list[str],
            df_credit_card: pd.DataFrame,
            df_transactions: pd.DataFrame) -> None:
    st.markdown(f"**{len(pendentes)} lançamento(s) novo(s)**")
    if len(pendentes) > 150:
        st.warning(
            f"⚠️ São **{len(pendentes)}** lançamentos — muito para uma "
            "sincronização de rotina. Se este período já foi digitado à "
            "mão, importar agora vai **duplicar** tudo. Ajuste a data "
            "acima para depois do seu último lançamento manual."
        )
    st.caption(
        "Ajuste a categoria e desmarque o que não quiser importar. A "
        "coluna *Palpite do banco* é o que a Pluggy achou que era — "
        "serve de referência, não entra na planilha."
    )

    tabela = pd.DataFrame([{
        "Importar": True,
        "Data": p.data,
        "Descrição": p.descricao,
        "Valor": p.valor,
        "Tipo": p.tipo,
        "Destino": p.destino,
        "Fatura": p.mes_fatura,
        "Categoria": p.categoria,
        "Palpite do banco": p.categoria_pluggy,
    } for p in pendentes])

    editada = st.data_editor(
        tabela, hide_index=True, use_container_width=True,
        disabled=["Data", "Descrição", "Valor", "Tipo", "Destino", "Fatura",
                  "Palpite do banco"],
        column_config={
            "Importar": st.column_config.CheckboxColumn("Importar"),
            "Valor": st.column_config.NumberColumn("Valor", format="%.2f"),
            "Categoria": st.column_config.SelectboxColumn(
                "Categoria", options=categories, required=True),
        },
        key="triagem",
    )

    aceitos = [p for p, (_, linha) in zip(pendentes, editada.iterrows())
               if bool(linha["Importar"])]
    for p, (_, linha) in zip(pendentes, editada.iterrows()):
        p.categoria = str(linha["Categoria"])

    entradas = sum(p.valor for p in aceitos if p.tipo == "Entrada"
                   and not p.is_cartao)
    saidas = sum(p.valor for p in aceitos if p.tipo == "Saída"
                 and not p.is_cartao)
    cartao = sum(p.valor for p in aceitos if p.is_cartao)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selecionados", len(aceitos))
    c2.metric("Entradas", brl(entradas))
    c3.metric("Saídas", brl(saidas))
    c4.metric("Cartão", brl(cartao))

    if not aceitos:
        st.info("Nada selecionado.")
        return

    if st.button(f"✅ Importar {len(aceitos)} lançamento(s)", type="primary"):
        _commit(aceitos, df_transactions, df_credit_card)


def _commit(aceitos: list, df_transactions: pd.DataFrame,
            df_credit_card: pd.DataFrame) -> None:
    """Grava as três abas.

    O registro de importação é gravado por último de propósito: se algo
    falhar antes dele, a próxima sincronização traz os mesmos
    lançamentos de volta — repetir é recuperável, marcar como importado
    o que não foi gravado não é.
    """
    banco, cartao, registro = pi.to_rows(aceitos)

    if banco:
        base = df_transactions.drop(columns=["Data_DT", "Mes_Ano"],
                                    errors="ignore")
        repository.save_transactions(
            pd.concat([base, pd.DataFrame(banco)], ignore_index=True))
    if cartao:
        repository.save_credit_card(
            pd.concat([df_credit_card, pd.DataFrame(cartao)],
                      ignore_index=True))
    repository.save_imports(
        pd.concat([repository.load_imports(), pd.DataFrame(registro)],
                  ignore_index=True))

    st.session_state["pluggy_pendentes"] = None
    st.success(
        f"{len(banco)} em Entradas e Saídas e {len(cartao)} no cartão. "
        "Eles não voltarão na próxima sincronização."
    )
    st.rerun()
