"""Página: Entradas e Saídas (lançamentos manuais)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import components, repository


def render(*, df_transactions: pd.DataFrame, categories: list[str]) -> None:
    components.page_header(
        "💰 Entradas e Saídas",
        "Registre lançamentos manuais e edite o histórico em tabela.",
    )

    st.subheader("➕ Novo lançamento")
    with st.form("new_transaction", clear_on_submit=True):
        c1, c2 = st.columns(2)
        date_value = c1.date_input("Data", format="DD/MM/YYYY")
        kind = c2.selectbox("Tipo", ["Entrada", "Saída"])
        description = st.text_input("Descrição")
        c3, c4 = st.columns(2)
        category = c3.selectbox("Categoria", categories)
        amount = c4.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        if st.form_submit_button("Salvar lançamento"):
            repository.append_transaction({
                "Data": date_value,
                "Descrição": description,
                "Categoria": category,
                "Valor": amount,
                "Tipo": kind,
            })
            st.success("Lançamento salvo na nuvem!")
            st.rerun()

    st.divider()
    st.subheader("✏️ Histórico completo")
    st.caption("Edite valores diretamente na tabela e clique em salvar.")
    editable = df_transactions.drop(
        columns=[c for c in ("Data_DT", "Mes_Ano") if c in df_transactions.columns]
    )
    with st.form("edit_transactions"):
        edited = st.data_editor(editable, num_rows="dynamic", use_container_width=True)
        if st.form_submit_button("💾 Salvar alterações"):
            if not editable.equals(edited):
                repository.save_transactions(edited)
                st.success("Alterações salvas.")
                st.rerun()
            else:
                st.info("Nada a salvar — sem alterações.")
