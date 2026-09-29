"""Página: Configurações e Orçamento."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as components_html

from src import components, pluggy, repository
from src.config import ConfigKeys
from src.format import brl
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

    tabs = st.tabs(["Categorias", "Orçamento", "Custos Fixos", "Open Finance"])

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
