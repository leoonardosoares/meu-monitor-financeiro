"""Página: Entradas e Saídas — histórico do que entrou e saiu da conta.

Desde que o Open Finance alimenta o app, esta página é de leitura: os
lançamentos chegam pela importação e aqui se confere e se corrige a
categoria. O lançamento manual continua existindo, recolhido no fim,
porque nem todo dinheiro passa por conta conectada — dinheiro vivo,
empréstimo a um amigo, conta de outro banco.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import components, repository
from src.finance import suggest_category
from src.format import brl


_DRAFT_KEY = "transaction_draft"


def render(*, df_transactions: pd.DataFrame, categories: list[str]) -> None:
    components.page_header(
        "Entradas e Saídas",
        "Tudo que entrou e saiu da sua conta. Chega sozinho pela "
        "importação — aqui você confere e ajusta a categoria.",
    )

    _summary(df_transactions)
    _history_section(df_transactions)
    st.divider()
    with st.expander("➕ Lançar algo que não passou pelo banco"):
        st.caption(
            "Dinheiro vivo, empréstimo a um amigo, conta de um banco que "
            "você não conectou. O que passa pelas contas conectadas chega "
            "sozinho pela aba **Importar do banco** — não lance aqui, ou "
            "vai ficar duplicado."
        )
        _new_transaction_form(df_transactions, categories)


def _summary(df: pd.DataFrame) -> None:
    """Três números do que está na tela, para dar escala ao histórico."""
    if df.empty:
        st.info(
            "Nenhum lançamento ainda. Vá em **Importar do banco** para "
            "trazer os seus."
        )
        return
    valores = pd.to_numeric(df.get("Valor"), errors="coerce").fillna(0)
    tipos = df.get("Tipo", pd.Series("", index=df.index)).astype(str)
    entradas = float(valores[tipos == "Entrada"].sum())
    saidas = float(valores[tipos == "Saída"].sum())
    sem_categoria = int(
        (df.get("Categoria", pd.Series("", index=df.index))
         .fillna("").astype(str).str.strip().isin(["", "Outros"])).sum()
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lançamentos", len(df))
    c2.metric("Entradas", brl(entradas))
    c3.metric("Saídas", brl(saidas))
    c4.metric(
        "Sem categoria", sem_categoria,
        delta="revisar" if sem_categoria else "tudo categorizado",
        delta_color="inverse" if sem_categoria else "normal",
    )


# ---------------------------------------------------------------------------
# Formulário com auto-sugestão de categoria
# ---------------------------------------------------------------------------

def _new_transaction_form(df_transactions: pd.DataFrame,
                           categories: list[str]) -> None:
    components.section("Novo lançamento")
    st.caption(
        "Após salvar, se sua descrição combinar com lançamentos anteriores "
        "categorizados de outra forma, o app te dá uma dica."
    )

    with st.form("new_transaction", clear_on_submit=True):
        description = st.text_input(
            "Descrição",
            placeholder="Ex.: Mercado, Uber, Salário...",
        )
        c1, c2 = st.columns(2)
        date_value = c1.date_input("Data", format="DD/MM/YYYY")
        kind = c2.selectbox("Tipo", ["Saída", "Entrada"])
        c3, c4 = st.columns(2)
        category = c3.selectbox("Categoria", categories)
        amount = c4.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        submitted = st.form_submit_button("Salvar lançamento")

    if not submitted:
        return
    if not description.strip():
        st.error("Informe uma descrição.")
        return

    repository.append_transaction({
        "Data": date_value,
        "Descrição": description.strip(),
        "Categoria": category,
        "Valor": amount,
        "Tipo": kind,
    })

    st.success("Lançamento salvo na nuvem.")
    suggested = suggest_category(description, df_transactions)
    if suggested and suggested in categories and suggested != category:
        st.info(
            f"💡 Dica: '{description}' costuma ser categorizado como "
            f"**{suggested}**. Ajuste no histórico se quiser."
        )
    # Sem st.rerun() / st.toast — em algumas combinações Streamlit/Python 3.14
    # eles disparam StreamlitAPIException. A tabela abaixo atualiza no próximo
    # clique do usuário (o cache já foi invalidado por save_transactions).


# ---------------------------------------------------------------------------
# Histórico com busca/filtros + editor
# ---------------------------------------------------------------------------

def _history_section(df_transactions: pd.DataFrame) -> None:
    components.section(
        "Histórico completo",
        "Use os filtros para encontrar registros, depois edite ou apague.")

    editable_full = df_transactions.drop(
        columns=[c for c in ("Data_DT", "Mes_Ano") if c in df_transactions.columns]
    )

    filtered = _render_filters(editable_full)
    if filtered.empty:
        st.info("Nenhum lançamento bate com os filtros.")
        return

    st.caption(
        f"Exibindo **{len(filtered)}** de **{len(editable_full)}** lançamentos."
    )

    with st.form("edit_transactions"):
        edited = st.data_editor(
            filtered, num_rows="dynamic", use_container_width=True,
            hide_index=True,
        )
        if st.form_submit_button("💾 Salvar alterações"):
            _save_filtered_edits(
                full=editable_full, filtered_before=filtered, edited=edited,
            )


def _render_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    text = c1.text_input("🔎 Buscar na descrição", value="")
    categories = ["Todas"] + sorted(df["Categoria"].dropna().unique().tolist())
    cat = c2.selectbox("Categoria", categories)
    types = ["Todos", "Entrada", "Saída"]
    tipo = c3.selectbox("Tipo", types)
    values_series = pd.to_numeric(df["Valor"], errors="coerce").fillna(0)
    max_value = float(values_series.max() or 0)
    min_value = c4.number_input(
        "Valor mínimo (R$)", min_value=0.0, max_value=max(max_value, 0.01),
        value=0.0, step=10.0,
    )

    mask = pd.Series(True, index=df.index)
    if text.strip():
        mask &= df["Descrição"].fillna("").astype(str).str.contains(
            text.strip(), case=False, na=False,
        )
    if cat != "Todas":
        mask &= df["Categoria"] == cat
    if tipo != "Todos":
        mask &= df["Tipo"] == tipo
    if min_value > 0:
        mask &= values_series >= min_value
    return df[mask]


def _save_filtered_edits(*, full: pd.DataFrame, filtered_before: pd.DataFrame,
                          edited: pd.DataFrame) -> None:
    """Aplica edições feitas em uma visão filtrada de volta ao dataset completo.

    Estratégia: substituímos as linhas que estavam visíveis (mesmo índice)
    pelas editadas, e concatenamos com o resto não-filtrado. Adições e
    remoções dentro do filtro são respeitadas.
    """
    if filtered_before.equals(edited):
        st.info("Nada a salvar — sem alterações.")
        return
    untouched = full.drop(filtered_before.index, errors="ignore")
    new_df = pd.concat([untouched, edited], ignore_index=True)
    repository.save_transactions(new_df)
    st.success("Alterações salvas.")
    st.rerun()
