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
    return _to_numeric(_read("cartao"), ["Valor"])


def save_credit_card(df: pd.DataFrame) -> None:
    _overwrite("cartao", df)
    load_credit_card.clear()


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
    return _to_numeric(_read("custos_fixos"), ["Valor"])


def save_fixed_costs(df: pd.DataFrame) -> None:
    _overwrite("custos_fixos", df)
    load_fixed_costs.clear()


# ---------------------------------------------------------------------------
# Backup do extrato bancário (Pluggy)
# ---------------------------------------------------------------------------

def save_bank_extract(df: pd.DataFrame) -> None:
    _overwrite("extrato_bancario", df)
