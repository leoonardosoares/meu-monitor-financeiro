"""Página: Sincronização com os bancos.

A sincronização roda sozinha ao abrir o app (ver `app.py`) e grava tudo
com a categoria sugerida. Esta página é para as três coisas que sobram
para o usuário:

1. **categorizar** o que chegou — a única tarefa recorrente;
2. ver o que a última sincronização fez, e forçar outra;
3. dizer, uma vez, para onde vai cada conta da Pluggy.

Antes a gravação esperava uma triagem: até o usuário abrir esta página e
clicar, o cartão ficava sem as compras novas e não batia com o banco.
Agora o cartão está sempre completo, e categorizar é arrumar depois — o
que é seguro, porque a categoria não muda nenhum total de fatura.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import components, credit_card as cc, pluggy, repository, sync
from src import pluggy_import as pi
from src.config import ConfigKeys
from src.format import brl, md

# Quanto tempo uma linha importada fica na caixa de categorização.
JANELA_DIAS = 30


def render(*, df_transactions: pd.DataFrame, df_credit_card: pd.DataFrame,
           df_cards: pd.DataFrame, categories: list[str]) -> None:
    components.page_header(
        "Sincronização",
        "Os lançamentos chegam sozinhos. Aqui você categoriza o que "
        "chegou e diz para onde vai cada conta.",
    )

    if not pluggy.is_configured():
        st.info(md(
            "Nenhum banco conectado ainda. Vá em **Configurações e "
            "Orçamento → Open Finance** para conectar."
        ))
        return

    ids = item_ids()
    if not ids:
        st.info(md(
            "As credenciais existem, mas nenhuma conexão foi informada. "
            "Termine o passo 2 em **Configurações e Orçamento → Open "
            "Finance**."
        ))
        return

    _status(ids, df_transactions)
    _lote_retido(ids, df_transactions)

    aba_cat, aba_contas = st.tabs(["🏷️ Categorizar", "🔗 Contas conectadas"])
    with aba_cat:
        _categorizar(df_transactions, df_credit_card, categories)
    with aba_contas:
        _mapa_de_contas(ids, df_cards, df_credit_card)


def item_ids() -> list[str]:
    return [i.strip() for i in
            repository.load_config_text(ConfigKeys.PLUGGY_ITEMS).split(",")
            if i.strip()]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def _status(ids: list[str], df_transactions: pd.DataFrame) -> None:
    carimbo = repository.load_config_text(ConfigKeys.PLUGGY_ULTIMA_SYNC)
    res = st.session_state.get("sync_resultado")

    esq, dir_ = st.columns([3, 1])
    with esq:
        components.section(
            "Última sincronização",
            (f"{_legivel(carimbo)}. Ela roda sozinha ao abrir o app quando "
             "passa de 6 horas." if carimbo else
             "Ainda não houve nenhuma."),
            eyebrow="Status",
        )
    if dir_.button("🔄 Sincronizar agora", type="primary",
                   use_container_width=True):
        executar(ids, df_transactions)
        st.rerun()

    if res is None:
        return
    if isinstance(res, str):
        st.error(f"A sincronização falhou: {res}")
        return
    st.success(res.resumo())
    if res.datas_aprendidas:
        st.info("📆 Datas atualizadas a partir do banco — "
                + " · ".join(res.datas_aprendidas))
    for aviso in res.avisos:
        st.caption(f"ℹ️ {aviso}")
    for erro in res.erros:
        st.warning(f"⚠️ {erro}")


def _legivel(carimbo: str) -> str:
    try:
        from datetime import datetime
        return datetime.fromisoformat(carimbo).strftime("%d/%m às %H:%M")
    except ValueError:
        return carimbo


def executar(ids: list[str], df_transactions: pd.DataFrame, *,
             confirmar_lote: bool = False) -> None:
    """Roda a sincronização e guarda o resultado para a tela mostrar.

    Exceção não sobe: uma instituição fora do ar não pode derrubar o app
    inteiro. O texto do erro fica guardado e aparece aqui.
    """
    from src.finance import suggest_category
    with st.spinner("Sincronizando com seus bancos…"):
        try:
            res = sync.run(
                ids=ids, today=date.today(), confirmar_lote=confirmar_lote,
                sugerir=lambda d: suggest_category(d, df_transactions))
        except Exception as exc:                          # noqa: BLE001
            st.session_state["sync_resultado"] = str(exc)
            return
    st.session_state["sync_resultado"] = res
    st.session_state["sync_retidos"] = len(res.retidos)
    _limpar_caches()


def _limpar_caches() -> None:
    """A sincronização grava direto: o que a tela leu antes está velho."""
    for fn in (repository.load_transactions, repository.load_credit_card,
               repository.load_cards, repository.load_bank_bills,
               repository.load_positions, repository.load_imports):
        limpar = getattr(fn, "clear", None)
        if callable(limpar):
            limpar()


def _lote_retido(ids: list[str], df_transactions: pd.DataFrame) -> None:
    """Lote grande demais para gravar sem confirmação."""
    retidos = st.session_state.get("sync_retidos") or 0
    if not retidos:
        return
    st.warning(md(
        f"⚠️ A última sincronização encontrou **{retidos}** lançamentos "
        "novos de uma vez e não gravou nada. Isso costuma ser um período "
        "que você já digitou à mão voltando pela importação — gravar "
        "agora duplicaria tudo. Confira a **data de corte** na aba "
        "*Contas conectadas* antes de confirmar."
    ))
    if st.button(f"Gravar os {retidos} lançamentos mesmo assim"):
        executar(ids, df_transactions, confirmar_lote=True)
        st.session_state["sync_retidos"] = 0
        st.rerun()


# ---------------------------------------------------------------------------
# Categorizar
# ---------------------------------------------------------------------------

def _recentes() -> set[str]:
    """Ids importados nos últimos JANELA_DIAS dias."""
    df = repository.load_imports()
    if df.empty or not {"ID Pluggy", "Importado em"}.issubset(df.columns):
        return set()
    quando = pd.to_datetime(df["Importado em"], errors="coerce")
    corte = pd.Timestamp(date.today() - timedelta(days=JANELA_DIAS))
    return set(df.loc[quando >= corte, "ID Pluggy"].astype(str).str.strip())


def _categorizar(df_transactions: pd.DataFrame, df_credit_card: pd.DataFrame,
                 categories: list[str]) -> None:
    components.section(
        "O que chegou e precisa de categoria",
        f"Os lançamentos dos últimos {JANELA_DIAS} dias, com os de "
        "categoria *Outros* primeiro. Mudar a categoria não altera nenhum "
        "total — só para onde o gasto conta no orçamento.",
    )
    ids = _recentes()
    if not ids:
        st.caption("Nada importado recentemente.")
        return

    _editor_de_categoria(
        rotulo="Cartão", chave="cat_cartao", df=df_credit_card, ids=ids,
        colunas=["Data Compra", "Descrição", "Cartão", "Mês da Fatura",
                 "Valor"],
        categories=categories, salvar=repository.save_credit_card)
    st.write("")
    base = df_transactions.drop(columns=["Data_DT", "Mes_Ano"],
                                errors="ignore")
    _editor_de_categoria(
        rotulo="Conta", chave="cat_conta", df=base, ids=ids,
        colunas=["Data", "Descrição", "Tipo", "Valor"],
        categories=categories, salvar=repository.save_transactions)


def _editor_de_categoria(*, rotulo: str, chave: str, df: pd.DataFrame,
                         ids: set[str], colunas: list[str],
                         categories: list[str], salvar) -> None:
    if df.empty or "ID Pluggy" not in df.columns:
        return
    mascara = df["ID Pluggy"].astype(str).str.strip().isin(ids)
    recorte = df[mascara]
    if recorte.empty:
        return
    vistas = [c for c in colunas if c in recorte.columns] + ["Categoria"]
    tabela = recorte[vistas].copy()
    tabela["_ordem"] = (tabela["Categoria"].astype(str) != "Outros").astype(int)
    tabela = tabela.sort_values(["_ordem"] + vistas[:1], ascending=[True, False])
    tabela = tabela.drop(columns=["_ordem"])
    pendentes = int((tabela["Categoria"].astype(str) == "Outros").sum())

    opcoes = sorted(set(categories) | set(tabela["Categoria"].astype(str)))
    st.markdown(f"**{rotulo}** — {len(tabela)} lançamento(s)"
                + (f", {pendentes} sem categoria" if pendentes else ""))
    with st.form(chave):
        editada = st.data_editor(
            tabela, hide_index=True, use_container_width=True,
            disabled=[c for c in vistas if c != "Categoria"],
            column_config={
                "Valor": st.column_config.NumberColumn("Valor",
                                                       format="R$ %.2f"),
                "Categoria": st.column_config.SelectboxColumn(
                    "Categoria", options=opcoes, required=True),
            },
            key=f"{chave}_editor",
        )
        if st.form_submit_button("💾 Salvar categorias"):
            mudou = editada["Categoria"].astype(str) != \
                tabela["Categoria"].astype(str)
            if not mudou.any():
                st.info("Nenhuma categoria mudou.")
            else:
                novo = df.copy()
                novo.loc[editada.index[mudou], "Categoria"] = \
                    editada.loc[mudou, "Categoria"]
                salvar(novo)
                st.success(f"{int(mudou.sum())} categoria(s) salva(s).")
                st.rerun()


# ---------------------------------------------------------------------------
# Contas conectadas
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner="Consultando seus bancos…")
def _load_accounts(ids: list[str]) -> tuple[list[dict], list[str]]:
    contas, avisos = [], []
    for item_id in ids:
        try:
            item = pluggy.item(item_id)
            for conta in pluggy.list_accounts(item_id):
                conta["_conexao"] = (item.get("connector") or {}).get(
                    "name") or item_id[:8]
                contas.append(conta)
        except pluggy.PluggyError as exc:
            avisos.append(f"Conexão {item_id[:8]}…: {exc}")
    return contas, avisos


def _mapa_de_contas(ids: list[str], df_cards: pd.DataFrame,
                    df_credit_card: pd.DataFrame) -> None:
    components.section(
        "Para onde vai cada conta",
        "Diga uma vez e o app lembra. É o que liga o cartão da Pluggy ao "
        "seu cartão cadastrado aqui.",
    )
    contas, avisos = _load_accounts(ids)
    for aviso in avisos:
        st.warning(f"⚠️ {aviso}")
    if not contas:
        return

    cartoes = cc.list_card_names(df_cards, df_credit_card)
    opcoes = [pi.DESTINO_BANCO, *cartoes, pi.DESTINO_IGNORAR]
    salvo = pi.parse_mapping(
        repository.load_config_text(ConfigKeys.PLUGGY_MAPA))

    with st.form("mapa_contas"):
        escolhas: dict[str, str] = {}
        for conta in contas:
            chave = pi.account_key(conta)
            tipo = str(conta.get("type") or "").upper()
            padrao = salvo.get(
                chave, pi.DESTINO_BANCO if tipo == "BANK" else pi.DESTINO_IGNORAR)
            indice = opcoes.index(padrao) if padrao in opcoes else len(opcoes) - 1
            c1, c2 = st.columns([2, 1])
            c1.markdown(md(
                f"**{pi.account_label(conta)}** · {conta.get('_conexao')} · "
                f"{'cartão' if tipo == 'CREDIT' else 'conta'}"))
            escolhas[chave] = c2.selectbox(
                "Destino", opcoes, index=indice, key=f"dest_{chave}",
                label_visibility="collapsed")

        padrao_desde = repository.load_config_text(ConfigKeys.PLUGGY_DESDE)
        try:
            inicial = (date.fromisoformat(padrao_desde) if padrao_desde
                       else date.today())
        except ValueError:
            inicial = date.today()
        desde = st.date_input(
            "Trazer lançamentos a partir de", value=inicial,
            format="DD/MM/YYYY",
            help=("O que você digitou à mão não tem identificador do banco, "
                  "então trazer um período já digitado cria linha "
                  "repetida."))

        if st.form_submit_button("💾 Salvar"):
            repository.save_config_text(
                ConfigKeys.PLUGGY_MAPA, pi.format_mapping(escolhas))
            repository.save_config_text(ConfigKeys.PLUGGY_DESDE, str(desde))
            st.success("Salvo. A próxima sincronização já usa isto.")
            st.rerun()

    st.caption(md(
        "Saldo das contas na última leitura: " + " · ".join(
            f"{pi.account_label(c)} {brl(float(c.get('balance') or 0))}"
            for c in contas)))
