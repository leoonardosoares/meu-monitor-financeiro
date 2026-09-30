"""Página: Configurações e Orçamento."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as components_html

from src import components, pluggy, repository, reset
from src.config import ConfigKeys
from src.format import brl, md
from src.sidebar import ALL_MONTHS


def render(*, df_categories: pd.DataFrame, df_budgets: pd.DataFrame,
           df_fixed_costs: pd.DataFrame,
           df_transactions_period: pd.DataFrame,
           df_credit_card_period: pd.DataFrame,
           categories: list[str],
           selected_month: str) -> None:
    components.page_header(
        "Configurações e Orçamento",
        "Personalize categorias, orçamentos e custos fixos, e conecte seus "
        "bancos. As regras de cada cartão ficam na aba **Cartão de Crédito**.",
    )

    tabs = st.tabs(["Categorias", "Orçamento", "Custos Fixos", "Open Finance",
                    "Recomeçar"])

    with tabs[0]:
        _categories_tab(df_categories)
    with tabs[1]:
        _budgets_tab(
            df_budgets=df_budgets,
            df_transactions_period=df_transactions_period,
            df_credit_card_period=df_credit_card_period,
            selected_month=selected_month,
        )
    with tabs[2]:
        _fixed_costs_tab(df_fixed_costs, categories=categories)
    with tabs[3]:
        _open_finance_tab()
    with tabs[4]:
        _reset_tab(df_transactions_period)


def _reset_tab(_df_period) -> None:
    """Zera o histórico manual para o Open Finance reconstruir o mês.

    É a única tela do app que apaga dados, então pede confirmação
    escrita e mostra a contagem antes — um clique acidental aqui custa
    caro, e desfazer depende de o usuário achar a aba de arquivo.
    """
    st.subheader("Recomeçar do zero")
    st.caption(
        "Apaga os lançamentos e as compras de cartão, e deixa o Open "
        "Finance reconstruir a partir do dia 1 deste mês. Serve para o "
        "app bater com o banco ao centavo: enquanto houver lançamento "
        "digitado à mão misturado com importado, a soma nunca fecha."
    )

    df_tx = repository.load_transactions().drop(
        columns=["Data_DT", "Mes_Ano"], errors="ignore")
    df_cartao = repository.load_credit_card()
    df_pag = repository.load_card_payments()
    df_imp = repository.load_imports()

    plano = reset.plan({
        "financeiro": df_tx, "cartao": df_cartao,
        "cartao_pagamentos": df_pag, "importacoes": df_imp,
    })

    rotulos = {
        "financeiro": "Entradas e Saídas",
        "cartao": "Compras no cartão",
        "cartao_pagamentos": "Pagamentos de fatura",
        "importacoes": "Registro de importação",
    }
    st.dataframe(pd.DataFrame([
        {"Aba": rotulos[k], "Linhas que serão apagadas": v,
         "Cópia guardada em": reset.ARQUIVOS.get(k) or "— (não precisa)"}
        for k, v in plano.contagem.items()
    ]), hide_index=True, use_container_width=True)

    corte = reset.cutoff(date.today())
    st.info(
        f"Depois disso a importação passa a buscar desde **{corte:%d/%m/%Y}** "
        "e o registro de importação é zerado, para o mês inteiro poder "
        "voltar pelo Open Finance."
    )
    st.warning(
        "Os seus **cartões cadastrados, categorias, orçamentos, custos "
        "fixos e investimentos continuam** — só o histórico de "
        "lançamentos é zerado."
    )

    if plano.total == 0:
        st.success("Não há nada para apagar.")
        return

    st.divider()
    confirmacao = st.text_input(
        f"Para confirmar, escreva **RECOMEÇAR** — {plano.total} linha(s) "
        "serão apagadas:", placeholder="RECOMEÇAR",
    )
    if st.button("🧨 Apagar e recomeçar", type="primary",
                 disabled=confirmacao.strip().upper() != "RECOMEÇAR"):
        hoje = date.today()
        if not df_tx.empty:
            repository.save_archive("arquivo_financeiro",
                                    reset.stamp(df_tx, quando=hoje))
        if not df_cartao.empty:
            repository.save_archive("arquivo_cartao",
                                    reset.stamp(df_cartao, quando=hoje))

        repository.save_transactions(df_tx.iloc[0:0])
        repository.save_credit_card(df_cartao.iloc[0:0])
        repository.save_card_payments(df_pag.iloc[0:0])
        repository.save_imports(df_imp.iloc[0:0])
        repository.save_config_text(ConfigKeys.PLUGGY_DESDE, corte.isoformat())
        repository.save_config_text(ConfigKeys.PLUGGY_ULTIMA_SYNC, "")

        st.success(
            "Pronto. Vá em **Importar do banco** e busque os lançamentos "
            f"desde {corte:%d/%m/%Y}."
        )
        st.rerun()


def _open_finance_tab() -> None:
    """Diagnóstico da conexão com a Pluggy.

    Existe antes do importador de propósito: sem ver o que a API devolve
    para esta conta, qualquer importador seria escrito no escuro. É aqui
    que se descobre se as conexões feitas no Meu Pluggy estão visíveis
    para esta aplicação.
    """
    st.subheader("Conexão com os bancos (Open Finance)")

    if not pluggy.is_configured():
        st.info(
            "Ainda não configurado. Em **Manage app → Settings → Secrets**, "
            "acrescente ao que já está lá:"
        )
        st.code(
            'PLUGGY_CLIENT_ID = "..."\nPLUGGY_CLIENT_SECRET = "..."',
            language="toml",
        )
        st.caption(
            "Os dois valores ficam no dashboard da Pluggy, em **Aplicações**. "
            "Não é preciso informar o itemId — o app descobre sozinho."
        )
        return

    st.markdown("**1. Autorizar o app a ler suas conexões**")
    st.caption(
        "Os bancos que você ligou no Meu Pluggy pertencem a ele, não a este "
        "app — por isso a API responde que falta autorização. O botão abaixo "
        "abre a tela da Pluggy onde você entra com a sua conta do Meu Pluggy "
        "e autoriza este app a ler as mesmas conexões."
    )

    with st.expander("O que a tela de conexão vai pedir"):
        st.caption(
            "A Pluggy monta aquele formulário a partir da ficha do conector. "
            "Se o campo não aparecer na tela dela, é aqui que se descobre o "
            "que ele espera."
        )
        if st.button("Consultar o conector MeuPluggy"):
            try:
                ficha = pluggy.connector()
            except pluggy.PluggyError as exc:
                st.error(f"🚨 {exc}")
            else:
                campos = ficha.get("credentials") or []
                if campos:
                    st.dataframe(pd.DataFrame([{
                        "Campo": c.get("name"),
                        "Rótulo": c.get("label"),
                        "Tipo": c.get("type"),
                        "Formato": c.get("validation") or c.get("placeholder"),
                        "Instruções": c.get("instructions"),
                        "Opcional": c.get("optional"),
                    } for c in campos]), hide_index=True,
                        use_container_width=True)
                else:
                    st.caption("O conector não declara campos de entrada.")
                st.caption(
                    f"Tipo: {ficha.get('type')} · "
                    f"OAuth: {ficha.get('oauth')} · MFA: {ficha.get('hasMFA')}"
                )

    if st.button("🔗 Conectar um banco"):
        try:
            token = pluggy.connect_token()
        except pluggy.PluggyError as exc:
            st.error(f"🚨 {exc}")
        else:
            st.session_state["pluggy_token"] = token

    token = st.session_state.get("pluggy_token")
    if token:
        st.caption(
            "Conecte **um banco por vez**; o Meu Pluggy compartilha uma "
            "conexão por autorização. Ao final o identificador aparece na "
            "tela — copie e cole no passo 2. O link vale 30 minutos."
        )
        components_html(pluggy.connect_widget_html(token), height=640)
        st.link_button(
            "Se o widget acima não abrir, use a tela da Pluggy",
            pluggy.connect_url(token),
        )

    st.divider()
    st.markdown("**2. Informar as conexões criadas**")
    st.caption(
        "Esta conta da Pluggy não permite *listar* as conexões — a chave lê "
        "uma conexão específica, mas não enumera todas. Então os "
        "identificadores ficam guardados aqui. Pegue cada um no dashboard "
        "da Pluggy, em **Dados Financeiros → Execuções**: é o `itemId`, um "
        "código no formato `a1b2c3d4-...`."
    )
    salvos = repository.load_config_text(ConfigKeys.PLUGGY_ITEMS)
    with st.form("pluggy_items"):
        texto = st.text_area(
            "Um itemId por linha", value=salvos.replace(",", "\n"),
            placeholder="a1b2c3d4-5e6f-7890-abcd-ef1234567890",
            height=100,
        )
        if st.form_submit_button("💾 Salvar conexões"):
            ids = [linha.strip() for linha in texto.splitlines() if linha.strip()]
            repository.save_config_text(ConfigKeys.PLUGGY_ITEMS, ",".join(ids))
            st.success(f"{len(ids)} conexão(ões) salva(s).")
            st.rerun()

    st.divider()
    st.markdown("**3. Conferir o que o app enxerga**")
    st.caption("Só leitura: nada é gravado na sua planilha.")
    if not st.button("🔌 Testar conexão", type="primary"):
        return

    # A sonda usa um id real para conseguir chamar /investments e
    # /accounts, que exigem itemId.
    st.session_state["pluggy_items"] = salvos
    itens, erros = _fetch_items(salvos)

    if not itens:
        st.error(
            "Nenhuma conexão pôde ser lida. Confira se os identificadores "
            "acima estão corretos."
        )
        for e in erros:
            st.caption(f"• {e}")
        st.caption(
            "Abaixo, o que cada endpoint respondeu. Um **400** é chamada "
            "malformada; **401/403** é falta de permissão; **200** com lista "
            "vazia é vínculo ausente."
        )
        st.dataframe(pd.DataFrame(pluggy.probe()), hide_index=True,
                     use_container_width=True)
        return

    for e in erros:
        st.warning(f"⚠️ {e}")
    st.success(f"{len(itens)} conexão(ões) lida(s).")
    for it in itens:
        conector = (it.get("connector") or {}).get("name") or "Banco"
        status = it.get("status", "?")
        icone = {"UPDATED": "🟢", "UPDATING": "🔄", "CREATING": "🔄"}.get(
            status, "🟡")
        with st.expander(f"{icone} {conector} — {status}"):
            if status in ("UPDATING", "CREATING"):
                st.caption(
                    "Ainda buscando os dados na instituição. É normal na "
                    "primeira vez; volte daqui a alguns minutos."
                )
            st.caption(f"itemId: `{it.get('id')}`")
            try:
                contas = pluggy.list_accounts(str(it.get("id")))
            except pluggy.PluggyError as exc:
                st.error(f"🚨 {exc}")
                continue
            if not contas:
                st.caption("Nenhuma conta nesta conexão ainda.")
                continue
            st.dataframe(pd.DataFrame([{
                "Conta": c.get("name"),
                "Tipo": c.get("type"),
                "Número": c.get("number"),
                "Saldo": brl(float(c.get("balance") or 0)),
            } for c in contas]), hide_index=True, use_container_width=True)


def _fetch_items(salvos: str) -> tuple[list[dict], list[str]]:
    """Conexões, tentando listar e caindo para os ids guardados.

    A listagem é melhor quando funciona — pega conexões novas sem o
    usuário copiar nada. Mas ela devolve 403 nesta conta, e falhar aí
    não pode impedir a leitura das conexões que já se conhece.
    """
    try:
        itens = pluggy.list_items()
        if itens:
            return itens, []
    except pluggy.PluggyError:
        pass

    ids = [i.strip() for i in salvos.split(",") if i.strip()]
    if not ids:
        return [], ["Nenhum itemId salvo, e a Pluggy não deixa listar as "
                    "conexões nesta conta."]

    itens, erros = [], []
    for item_id in ids:
        try:
            itens.append(pluggy.item(item_id))
        except pluggy.PluggyError as exc:
            erros.append(f"{item_id}: {exc}")
    return itens, erros


def _categories_tab(df_categories: pd.DataFrame) -> None:
    st.subheader("Minhas categorias")
    st.caption("Adicione, edite ou apague categorias e clique em salvar.")
    with st.form("edit_categories"):
        edited = st.data_editor(
            df_categories, num_rows="dynamic", use_container_width=True,
            hide_index=True,
        )
        if st.form_submit_button("💾 Salvar categorias"):
            if not df_categories.equals(edited):
                repository.save_categories(edited)
                st.success("Categorias atualizadas.")
                st.rerun()


def _budgets_tab(*, df_budgets: pd.DataFrame,
                 df_transactions_period: pd.DataFrame,
                 df_credit_card_period: pd.DataFrame,
                 selected_month: str) -> None:
    st.subheader("Teto de gastos por categoria")
    st.caption("Defina um limite mensal. Use `0` para categorias sem limite.")

    left, right = st.columns([1, 1.5])

    with left:
        with st.form("edit_budgets"):
            edited = st.data_editor(
                df_budgets, num_rows="dynamic", use_container_width=True,
                hide_index=True,
            )
            if st.form_submit_button("💾 Salvar orçamentos"):
                if not df_budgets.equals(edited):
                    repository.save_budgets(edited)
                    st.success("Orçamentos salvos.")
                    st.rerun()

    with right:
        if selected_month == ALL_MONTHS:
            st.info("Selecione um mês na sidebar para ver o progresso do orçamento.")
            return
        st.subheader(f"Progresso em {selected_month}")
        _render_budget_progress(
            df_budgets=df_budgets,
            df_transactions_period=df_transactions_period,
            df_credit_card_period=df_credit_card_period,
        )


def _render_budget_progress(*, df_budgets: pd.DataFrame,
                             df_transactions_period: pd.DataFrame,
                             df_credit_card_period: pd.DataFrame) -> None:
    bank_expenses = df_transactions_period[
        (df_transactions_period["Tipo"] == "Saída") &
        (df_transactions_period["Categoria"] != "Cartão de Crédito")
    ]
    has_valid_budget = False
    for _, row in df_budgets.iterrows():
        category = row["Categoria"]
        limit = float(row["Limite"]) if pd.notna(row["Limite"]) else 0.0
        if limit <= 0:
            continue
        has_valid_budget = True

        bank_in_cat = bank_expenses[bank_expenses["Categoria"] == category]
        if df_credit_card_period.empty:
            card_in_cat = pd.DataFrame()
        else:
            card_in_cat = df_credit_card_period[
                df_credit_card_period["Categoria"] == category
            ]

        bank_total = float(bank_in_cat["Valor"].sum()) if not bank_in_cat.empty else 0.0
        card_total = float(card_in_cat["Valor"].sum()) if not card_in_cat.empty else 0.0
        spent = bank_total + card_total
        ratio = spent / limit

        if ratio >= 1.0:
            status_emoji, status_text = "🚨", "estourou"
            progress_value = 1.0
        elif ratio >= 0.8:
            status_emoji, status_text = "⚠️", "quase lá"
            progress_value = ratio
        else:
            status_emoji, status_text = "✅", "tranquilo"
            progress_value = ratio

        header = (
            f"{status_emoji}  {category}  —  {brl(spent)} / {brl(limit)}  "
            f"({ratio * 100:.0f}% · {status_text})"
        )

        with st.expander(header):
            st.progress(progress_value)
            _render_category_transactions(
                category=category,
                bank_in_cat=bank_in_cat,
                card_in_cat=card_in_cat,
                bank_total=bank_total,
                card_total=card_total,
            )

    if not has_valid_budget:
        st.write("Adicione categorias e limites maiores que zero ao lado.")


def _render_category_transactions(*, category: str,
                                   bank_in_cat: pd.DataFrame,
                                   card_in_cat: pd.DataFrame,
                                   bank_total: float,
                                   card_total: float) -> None:
    """Lista os lançamentos de uma categoria, separados por origem."""
    if bank_in_cat.empty and card_in_cat.empty:
        st.caption(f"Nenhum lançamento em **{category}** neste período.")
        return

    if not bank_in_cat.empty:
        st.markdown(md(
            f"**Banco** · {len(bank_in_cat)} lançamento(s) · "
            f"total {brl(bank_total)}"
        ))
        df = bank_in_cat[["Data", "Descrição", "Valor"]].copy()
        if "Data_DT" in bank_in_cat.columns:
            df = df.assign(_ord=bank_in_cat["Data_DT"]).sort_values(
                "_ord", ascending=False,
            ).drop(columns="_ord")
        df["Valor"] = df["Valor"].apply(brl)
        st.dataframe(df, hide_index=True, use_container_width=True)

    if not card_in_cat.empty:
        st.markdown(md(
            f"**Cartão** · {len(card_in_cat)} lançamento(s) · "
            f"total {brl(card_total)}"
        ))
        cols = [c for c in (
            "Data Compra", "Descrição", "Parcela", "Valor", "Status"
        ) if c in card_in_cat.columns]
        df = card_in_cat[cols].copy()
        if "Data Compra" in df.columns:
            df = df.sort_values("Data Compra", ascending=False)
        df["Valor"] = df["Valor"].apply(brl)
        st.dataframe(df, hide_index=True, use_container_width=True)


def _fixed_costs_tab(df_fixed_costs: pd.DataFrame, *,
                      categories: list[str]) -> None:
    st.subheader("Receita base mensal")
    current = repository.load_config(ConfigKeys.RECEITA_PREVISTA, 0.0)
    new_income = st.number_input(
        "Salário / receita fixa esperada (R$):",
        min_value=0.0, value=current, step=100.0,
    )
    if new_income != current:
        repository.save_config(ConfigKeys.RECEITA_PREVISTA, new_income)
        st.success("Receita prevista atualizada.")
        st.rerun()

    st.divider()
    st.subheader("Custos fixos mensais")
    st.caption(
        "Cadastre suas despesas recorrentes. Depois use o botão "
        "**Gerar lançamentos do mês** para criar todas as transações de uma vez."
    )

    with st.form("edit_fixed_costs"):
        edited = st.data_editor(
            df_fixed_costs, num_rows="dynamic", use_container_width=True,
            hide_index=True,
            column_config={
                "Categoria": st.column_config.SelectboxColumn(
                    "Categoria", options=categories, required=False,
                ),
                "Valor": st.column_config.NumberColumn(
                    "Valor", format="%.2f", min_value=0.0,
                ),
            },
        )
        if st.form_submit_button("💾 Salvar custos fixos"):
            if not df_fixed_costs.equals(edited):
                try:
                    repository.save_fixed_costs(edited)
                    st.success("Custos fixos salvos.")
                    st.rerun()
                except Exception as exc:
                    st.error("🚨 O Google recusou a gravação. Detalhes abaixo:")
                    if hasattr(exc, "response"):
                        st.code(exc.response.text)
                    else:
                        st.error(str(exc))

    st.divider()
    _generate_fixed_costs_section(df_fixed_costs)


def _generate_fixed_costs_section(df_fixed_costs: pd.DataFrame) -> None:
    st.subheader("Gerar lançamentos automáticos do mês")
    st.caption(
        "Cria uma transação de Saída em cada custo fixo cadastrado. "
        "Útil pra automatizar aluguel, condomínio, assinaturas, etc."
    )

    valid_costs = df_fixed_costs[
        (df_fixed_costs["Valor"].fillna(0) > 0) &
        (df_fixed_costs["Descrição"].fillna("").astype(str).str.strip() != "")
    ]
    if valid_costs.empty:
        st.info("Cadastre custos fixos acima primeiro.")
        return

    c1, c2 = st.columns([1, 2])
    lancamento_data = c1.date_input(
        "Data dos lançamentos", value=date.today(), format="DD/MM/YYYY",
    )
    total = float(valid_costs["Valor"].sum())
    c2.metric(
        f"Total a lançar ({len(valid_costs)} itens)", brl(total),
    )

    with st.expander("Pré-visualizar lançamentos"):
        preview = valid_costs.copy()
        preview["Valor (R$)"] = preview["Valor"].apply(brl)
        st.dataframe(
            preview[["Descrição", "Categoria", "Valor (R$)"]],
            use_container_width=True, hide_index=True,
        )

    if st.button("🚀 Gerar lançamentos agora", type="primary"):
        df_current = repository.load_transactions().drop(
            columns=["Data_DT", "Mes_Ano"], errors="ignore",
        )
        new_rows = []
        for _, row in valid_costs.iterrows():
            new_rows.append({
                "Data": lancamento_data,
                "Descrição": str(row["Descrição"]).strip(),
                "Categoria": row.get("Categoria") or "Outros",
                "Valor": float(row["Valor"]),
                "Tipo": "Saída",
            })
        merged = pd.concat(
            [df_current, pd.DataFrame(new_rows)], ignore_index=True,
        )
        repository.save_transactions(merged)
        st.success(f"{len(new_rows)} lançamentos criados em {lancamento_data:%d/%m/%Y}.")
        st.rerun()
