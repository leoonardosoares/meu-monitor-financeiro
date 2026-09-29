"""Cliente da API da Pluggy (Open Finance).

Só leitura: autentica, lista as conexões que o usuário autorizou e baixa
contas, lançamentos, faturas de cartão e investimentos. Nada aqui grava
na Pluggy nem na planilha — a gravação é decidida na tela de triagem,
depois de o usuário conferir.

As credenciais vivem em `st.secrets` e nunca aparecem em mensagem de
erro: um traceback de requests exibiria a URL inteira, então os erros
são reescritos antes de subir para a tela.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import requests
import streamlit as st

BASE_URL = "https://api.pluggy.ai"
TIMEOUT = 30

# A chave dura 2 horas; renovar com folga evita o 401 no meio de uma
# sincronização longa, que deixaria metade dos lançamentos importados.
_TOKEN_TTL = 5400


class PluggyError(RuntimeError):
    """Falha ao falar com a Pluggy, já sem credencial na mensagem."""


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str


def credentials() -> Credentials | None:
    """Credenciais dos secrets, ou `None` se não estiverem configuradas."""
    try:
        cid = str(st.secrets.get("PLUGGY_CLIENT_ID", "")).strip()
        secret = str(st.secrets.get("PLUGGY_CLIENT_SECRET", "")).strip()
    except Exception:
        return None
    if not cid or not secret:
        return None
    return Credentials(cid, secret)


def is_configured() -> bool:
    return credentials() is not None


@st.cache_data(ttl=_TOKEN_TTL, show_spinner=False)
def _api_key(client_id: str, client_secret: str) -> str:
    """Troca client id + secret por uma chave temporária."""
    try:
        resp = requests.post(
            f"{BASE_URL}/auth",
            json={"clientId": client_id, "clientSecret": client_secret},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PluggyError(f"Não consegui falar com a Pluggy: {type(exc).__name__}")
    if resp.status_code != 200:
        raise PluggyError(
            "A Pluggy recusou as credenciais "
            f"(HTTP {resp.status_code}). Confira PLUGGY_CLIENT_ID e "
            "PLUGGY_CLIENT_SECRET nos secrets."
        )
    key = resp.json().get("apiKey")
    if not key:
        raise PluggyError("A Pluggy respondeu sem apiKey.")
    return str(key)


def _get(path: str, params: dict | None = None) -> dict:
    """GET autenticado. A documentação não fixa o nome do header, então
    tenta `X-API-KEY` e cai para `Authorization: Bearer` se for recusado.
    """
    creds = credentials()
    if creds is None:
        raise PluggyError("Credenciais da Pluggy não configuradas.")
    key = _api_key(creds.client_id, creds.client_secret)

    for header in ({"X-API-KEY": key}, {"Authorization": f"Bearer {key}"}):
        try:
            resp = requests.get(
                f"{BASE_URL}{path}", headers=header, params=params or {},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise PluggyError(
                f"Não consegui falar com a Pluggy: {type(exc).__name__}")
        if resp.status_code in (401, 403):
            continue          # tenta o outro formato de header
        if resp.status_code != 200:
            raise PluggyError(f"GET {path} devolveu HTTP {resp.status_code}.")
        return resp.json()

    raise PluggyError(
        f"GET {path} foi recusado por falta de autorização. Se as conexões "
        "foram feitas no Meu Pluggy, pode faltar autorizar esta aplicação "
        "como app parceiro."
    )


def _paginate(path: str, params: dict | None = None,
              limit: int = 500) -> list[dict]:
    """Percorre um endpoint paginado por cursor, juntando os resultados."""
    out: list[dict] = []
    cursor: str | None = None
    for _ in range(50):                     # teto de segurança
        page = dict(params or {}, pageSize=limit)
        if cursor:
            page["cursor"] = cursor
        data = _get(path, page)
        out.extend(data.get("results") or [])
        cursor = data.get("nextCursor")
        if not cursor:
            break
    return out


# ---------------------------------------------------------------------------
# Leituras
# ---------------------------------------------------------------------------

def list_items() -> list[dict]:
    """Conexões (bancos) que o usuário autorizou.

    É o que dispensa o usuário de caçar o `itemId` na interface da
    Pluggy: a própria API diz quais conexões existem.
    """
    return _paginate("/v2/items")


def list_accounts(item_id: str) -> list[dict]:
    """Contas de uma conexão — corrente, poupança e cartões."""
    return (_get("/accounts", {"itemId": item_id}).get("results") or [])


def list_transactions(account_id: str, *,
                      since: date | None = None) -> list[dict]:
    params: dict = {"accountId": account_id}
    if since is not None:
        params["from"] = since.isoformat()
    return _paginate("/v2/transactions", params)


def list_bills(account_id: str) -> list[dict]:
    """Faturas de um cartão, com data de fechamento e vencimento."""
    return (_get("/bills", {"accountId": account_id}).get("results") or [])


def list_investments(item_id: str) -> list[dict]:
    return (_get("/investments", {"itemId": item_id}).get("results") or [])
