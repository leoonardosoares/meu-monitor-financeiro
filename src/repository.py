"""Repositórios — leitura/escrita de DataFrames nas abas do Google Sheets.

Toda a comunicação com a planilha (leitura cacheada e escrita destrutiva
do tipo "limpa e regrava") passa por aqui. O resto do app trabalha com
DataFrames pandas, sem saber que existe uma planilha por trás.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.config import (
    CACHE_TTL_SECONDS,
    DEFAULT_CARD_NAME,
    DEFAULT_USER_CATEGORIES,
    SHEETS_SCHEMA,
)
from src.sheets import get_sheet


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _empty_df(sheet_name: str) -> pd.DataFrame:
    return pd.DataFrame(columns=SHEETS_SCHEMA[sheet_name])


def _read(sheet_name: str) -> pd.DataFrame:
    rows = get_sheet(sheet_name).get_all_records()
    return pd.DataFrame(rows) if rows else _empty_df(sheet_name)


def _overwrite(sheet_name: str, df: pd.DataFrame) -> None:
    """Limpa a aba e regrava o DataFrame inteiro.

    Usamos esta estratégia porque é simples e atômica para volumes
    pequenos. Para volumes maiores, valeria migrar para append/update
    incremental.
    """
    ws = get_sheet(sheet_name)
    ws.clear()
    rows = json.loads(df.fillna("").astype(str).to_json(orient="values"))
    ws.update(values=[df.columns.tolist()] + rows)


def _to_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Transações manuais (`financeiro`)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_transactions() -> pd.DataFrame:
    df = _to_numeric(_read("financeiro"), ["Valor"])
    df["Data_DT"] = pd.to_datetime(df.get("Data"), errors="coerce")
    df["Mes_Ano"] = df["Data_DT"].dt.strftime("%m/%Y").fillna("Sem Data")
    return df


def save_transactions(df: pd.DataFrame) -> None:
    df = df.drop(columns=[c for c in ("Data_DT", "Mes_Ano") if c in df.columns])
    _overwrite("financeiro", df)
    load_transactions.clear()


def append_transaction(row: dict) -> None:
    df = load_transactions().drop(columns=["Data_DT", "Mes_Ano"], errors="ignore")
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_transactions(df)


# ---------------------------------------------------------------------------
# Cartão de crédito
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_credit_card() -> pd.DataFrame:
    df = _to_numeric(_read("cartao"), ["Valor"])
    # Migração suave: compras lançadas antes do cadastro de cartões não têm
    # a coluna, e ficariam órfãs. Elas passam a pertencer ao cartão padrão.
    if "Cartão" not in df.columns:
        df["Cartão"] = DEFAULT_CARD_NAME
    else:
        vazio = df["Cartão"].isna() | (
            df["Cartão"].astype(str).str.strip() == ""
        )
        df.loc[vazio, "Cartão"] = DEFAULT_CARD_NAME
    return df


def save_credit_card(df: pd.DataFrame) -> None:
    _overwrite("cartao", df)
    load_credit_card.clear()


# ---------------------------------------------------------------------------
# Cadastro de cartões e pagamentos parciais de fatura
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_cards() -> pd.DataFrame:
    return _to_numeric(
        _read("cartoes"), ["Limite", "Dia Fechamento", "Dia Vencimento"],
    )


def save_cards(df: pd.DataFrame) -> None:
    _overwrite("cartoes", df)
    load_cards.clear()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_card_payments() -> pd.DataFrame:
    return _to_numeric(_read("cartao_pagamentos"), ["Valor"])


def save_card_payments(df: pd.DataFrame) -> None:
    _overwrite("cartao_pagamentos", df)
    load_card_payments.clear()


def append_card_payment(row: dict) -> None:
    df = pd.concat(
        [load_card_payments(), pd.DataFrame([row])], ignore_index=True,
    )
    save_card_payments(df)


# ---------------------------------------------------------------------------
# Configurações chave/valor
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _load_config_df() -> pd.DataFrame:
    return _read("configuracoes")


def load_config(key: str, default: float) -> float:
    df = _load_config_df()
    if df.empty or key not in df["chave"].values:
        return default
    raw = df.loc[df["chave"] == key, "valor"].iloc[0]
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def save_config(key: str, value: float) -> None:
    df = _load_config_df().copy()
    if not df.empty and key in df["chave"].values:
        df.loc[df["chave"] == key, "valor"] = value
    else:
        df = pd.concat(
            [df, pd.DataFrame([{"chave": key, "valor": value}])],
            ignore_index=True,
        )
    _overwrite("configuracoes", df)
    _load_config_df.clear()


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_categories() -> pd.DataFrame:
    df = _read("categorias")
    if df.empty:
        df = pd.DataFrame([{"Categoria": c} for c in DEFAULT_USER_CATEGORIES])
        _overwrite("categorias", df)
    return df


def save_categories(df: pd.DataFrame) -> None:
    _overwrite("categorias", df)
    load_categories.clear()


# ---------------------------------------------------------------------------
# Orçamentos
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_budgets() -> pd.DataFrame:
    return _to_numeric(_read("orcamentos"), ["Limite"])


def save_budgets(df: pd.DataFrame) -> None:
    _overwrite("orcamentos", df)
    load_budgets.clear()


# ---------------------------------------------------------------------------
# Custos fixos
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_fixed_costs() -> pd.DataFrame:
    df = _to_numeric(_read("custos_fixos"), ["Valor"])
    # Migração suave: planilhas antigas não tinham Categoria.
    if "Categoria" not in df.columns:
        df["Categoria"] = "Outros"
    # Garante ordem das colunas esperada pelo editor.
    columns = ["Descrição", "Categoria", "Valor"]
    for col in columns:
        if col not in df.columns:
            df[col] = "" if col != "Valor" else 0.0
    return df[columns]


def save_fixed_costs(df: pd.DataFrame) -> None:
    _overwrite("custos_fixos", df)
    load_fixed_costs.clear()


# ---------------------------------------------------------------------------
# Posições de investimento (snapshots manuais do saldo bruto na corretora)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_investment_positions() -> pd.DataFrame:
    df = _to_numeric(_read("posicao_investimentos"), ["Valor"])
    df["Data_DT"] = pd.to_datetime(df.get("Data"), errors="coerce")
    return df


def save_investment_positions(df: pd.DataFrame) -> None:
    df = df.drop(columns=[c for c in ("Data_DT",) if c in df.columns])
    _overwrite("posicao_investimentos", df)
    load_investment_positions.clear()


def append_investment_position(row: dict) -> None:
    df = load_investment_positions().drop(columns=["Data_DT"], errors="ignore")
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_investment_positions(df)


# ---------------------------------------------------------------------------
# Carteira por ativo: cadastro + movimentações
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_assets() -> pd.DataFrame:
    return _to_numeric(_read("investimentos"), ["Taxa"])


def save_assets(df: pd.DataFrame) -> None:
    _overwrite("investimentos", df)
    load_assets.clear()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_asset_moves() -> pd.DataFrame:
    return _to_numeric(_read("investimento_movimentacoes"), ["Valor"])


def save_asset_moves(df: pd.DataFrame) -> None:
    _overwrite("investimento_movimentacoes", df)
    load_asset_moves.clear()


def append_asset_move(row: dict) -> None:
    df = pd.concat([load_asset_moves(), pd.DataFrame([row])], ignore_index=True)
    save_asset_moves(df)


# ---------------------------------------------------------------------------
# Posição real por ativo (snapshots do valor bruto na corretora)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_asset_snapshots() -> pd.DataFrame:
    return _to_numeric(_read("posicao_ativos"), ["Valor"])


def save_asset_snapshots(df: pd.DataFrame) -> None:
    _overwrite("posicao_ativos", df)
    load_asset_snapshots.clear()


def append_asset_snapshot(row: dict) -> None:
    df = pd.concat(
        [load_asset_snapshots(), pd.DataFrame([row])], ignore_index=True,
    )
    save_asset_snapshots(df)


# ---------------------------------------------------------------------------
# Alocação de investimentos por classe
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_investment_allocation() -> pd.DataFrame:
    return _to_numeric(
        _read("alocacao_investimentos"), ["Valor", "Meta (%)"],
    )


def save_investment_allocation(df: pd.DataFrame) -> None:
    _overwrite("alocacao_investimentos", df)
    load_investment_allocation.clear()
