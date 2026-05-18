"""Página: Entradas e Saídas (lançamentos manuais)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import components, repository
from src.finance import suggest_category


_DRAFT_KEY = "transaction_draft"


def render(*, df_transactions: pd.DataFrame, categories: list[str]) -> None:
    components.page_header(
        "Entradas e Saídas",
        "Registre lançamentos manuais, busque registros antigos e edite "
        "valores diretamente na tabela.",
    )

    _new_transaction_form(df_transactions, categories)
    st.divider()
    _history_section(df_transactions)


# ---------------------------------------------------------------------------
# Formulário com auto-sugestão de categoria
# ---------------------------------------------------------------------------

def _new_transaction_form(df_transactions: pd.DataFrame,
                           categories: list[str]) -> None:
    st.subheader("Novo lançamento")

    # Streamlit não permite resetar o valor de um widget via session_state
    # depois que ele foi renderizado. Pra limpar o campo de descrição após
    # salvar, mantemos um contador que faz parte da `key` do widget — ao
    # incrementar, a próxima renderização cria um widget novo (vazio).
    if "_tx_form_gen" not in st.session_state:
        st.session_state["_tx_form_gen"] = 0
    gen = st.session_state["_tx_form_gen"]

    # Auto-sugestão é renderizada FORA do form porque depende da descrição
    # digitada e queremos atualizar a categoria sugerida em tempo real.
    description = st.text_input(
        "Descrição",
        key=f"new_tx_description_{gen}",
        placeholder="Ex.: Mercado, Uber, Salário...",
    )
    suggestion = suggest_category(description, df_transactions)
    default_idx = 0
    if suggestion and suggestion in categories:
        default_idx = categories.index(suggestion)
        st.caption(
            f"💡 Sugestão automática: **{suggestion}** "
            f"(baseada em lançamentos parecidos)."
        )

    with st.form("new_transaction", clear_on_submit=True):
        c1, c2 = st.columns(2)
        date_value = c1.date_input("Data", format="DD/MM/YYYY")
        kind = c2.selectbox("Tipo", ["Saída", "Entrada"])
        c3, c4 = st.columns(2)
        category = c3.selectbox("Categoria", categories, index=default_idx)
        amount = c4.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        if st.form_submit_button("Salvar lançamento"):
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
            # Incrementa o contador pra que o text_input seja recriado vazio
            # na próxima renderização (não é um widget — pode ser alterado).
            st.session_state["_tx_form_gen"] = gen + 1
            st.success("Lançamento salvo na nuvem.")
            st.rerun()


# ---------------------------------------------------------------------------
# Histórico com busca/filtros + editor
# ---------------------------------------------------------------------------

def _history_section(df_transactions: pd.DataFrame) -> None:
    st.subheader("Histórico completo")
    st.caption("Use os filtros para encontrar registros — depois edite ou apague.")

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
