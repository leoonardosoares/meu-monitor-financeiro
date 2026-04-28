"""Cliente da API Pluggy (Open Finance).

Encapsula auth, listagem de items/contas/transações, e disponibiliza
funções que devolvem listas Python prontas para virarem DataFrame.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import requests
import streamlit as st

API_BASE = "https://api.pluggy.ai"
TIMEOUT = 30


def _credentials() -> tuple[str, str] | None:
    client_id = st.secrets.get("PLUGGY_CLIENT_ID")
    client_secret = st.secrets.get("PLUGGY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def is_configured() -> bool:
    return _credentials() is not None


def get_api_key() -> str | None:
    creds = _credentials()
    if creds is None:
        return None
    client_id, client_secret = creds
    resp = requests.post(
        f"{API_BASE}/auth",
        json={"clientId": client_id, "clientSecret": client_secret},
        headers={"accept": "application/json", "content-type": "application/json"},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        return None
    return resp.json().get("apiKey")


def get_connect_token(api_key: str) -> str | None:
    resp = requests.post(
        f"{API_BASE}/connect_token",
        json={},
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": api_key,
        },
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        return None
    return resp.json().get("accessToken")


def _get(path: str, api_key: str) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"accept": "application/json", "X-API-KEY": api_key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_bank_data(api_key: str) -> tuple[list[dict], list[dict]]:
    """Devolve (contas, transações) de todos os items conectados.

    Retorna ([], []) se nenhuma conta tiver sido conectada ainda.
    """
    items = _get("/items", api_key)
    if not items:
        return [], []

    accounts: list[dict] = []
    transactions: list[dict] = []

    for item in items:
        item_accounts = _get(f"/accounts?itemId={item['id']}", api_key)
        for acc in item_accounts:
            accounts.append({
                "Conta": acc["name"],
                "Tipo": acc["type"],
                "Saldo": float(acc["balance"]),
            })

            tx_list = _get(f"/transactions?accountId={acc['id']}", api_key)
            for tx in tx_list:
                amount = float(tx["amount"])
                tx_date = pd.to_datetime(tx["date"]).tz_localize(None)
                transactions.append({
                    "Data": tx_date.strftime("%d/%m/%Y"),
                    "Descrição": tx["description"],
                    "Categoria": tx.get("category") or "Outros",
                    "Valor": amount,
                    "Tipo": "Entrada" if amount > 0 else "Saída",
                    "Conta": acc["name"],
                    "Data_DT": tx_date,
                })

    return accounts, transactions
