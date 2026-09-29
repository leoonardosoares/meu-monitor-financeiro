"""Cliente da Pluggy contra uma API fingida.

    python tests/run_pluggy.py

Separado de `run.py` porque substitui `requests` no processo inteiro.
Não faz chamada de rede — o objetivo é justamente poder verificar o
comportamento sem credencial e sem internet.
"""
from __future__ import annotations

import os
import sys
import types

_st = types.ModuleType("streamlit")
_st.cache_data = lambda *a, **k: (lambda f: f)
_st.cache_resource = lambda *a, **k: (lambda f: f)
_st.secrets = {"PLUGGY_CLIENT_ID": "cid-secreto",
               "PLUGGY_CLIENT_SECRET": "sec-secreto"}
sys.modules["streamlit"] = _st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from src import pluggy  # noqa: E402

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


class Resp:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body or {}

    def json(self):
        return self._b


chamadas: list[tuple] = []


def fake_post(url, json=None, timeout=None):
    chamadas.append(("POST", url, json))
    if (json or {}).get("clientId") == "cid-secreto":
        return Resp(200, {"apiKey": "jwt-abc"})
    return Resp(403)


def make_get(*, rejeita_xapikey=False, paginas=None):
    def fake_get(url, headers=None, params=None, timeout=None):
        chamadas.append(("GET", url, dict(headers or {}), dict(params or {})))
        if rejeita_xapikey and "X-API-KEY" in (headers or {}):
            return Resp(401)
        if paginas is not None:
            return Resp(200, paginas[(params or {}).get("cursor")])
        return Resp(200, {"results": [{"id": "item-1", "status": "UPDATED",
                                       "connector": {"name": "Nubank"}}]})
    return fake_get


print("  Autenticação e listagem de conexões")
requests.post, requests.get = fake_post, make_get()
check("lista as conexões", [i["id"] for i in pluggy.list_items()], ["item-1"])
check("tenta X-API-KEY primeiro", chamadas[1][2], {"X-API-KEY": "jwt-abc"})

# A documentação não fixa o nome do header; errar significaria falhar
# tudo com 401 sem explicação.
print("  Fallback de header quando X-API-KEY é recusado")
chamadas.clear()
requests.get = make_get(rejeita_xapikey=True)
check("ainda funciona", len(pluggy.list_items()), 1)
check("caiu para Bearer", chamadas[-1][2], {"Authorization": "Bearer jwt-abc"})

print("  Paginação por cursor")
requests.get = make_get(paginas={
    None: {"results": [{"id": "a"}], "nextCursor": "c1"},
    "c1": {"results": [{"id": "b"}], "nextCursor": "c2"},
    "c2": {"results": [{"id": "c"}], "nextCursor": None},
})
check("junta as páginas e para no fim",
      [i["id"] for i in pluggy.list_items()], ["a", "b", "c"])

# Um traceback de requests carregaria a URL inteira para a tela.
print("  Credencial não vaza em mensagem de erro")
pluggy.st.secrets = {"PLUGGY_CLIENT_ID": "errado", "PLUGGY_CLIENT_SECRET": "x"}
requests.post, requests.get = fake_post, make_get()
try:
    pluggy.list_items()
    _fail.append("credenciais erradas deveriam falhar")
except pluggy.PluggyError as exc:
    _ok += 1
    check("sem credencial na mensagem",
          any(s in str(exc) for s in ("errado", "cid-secreto", "jwt-abc")), False)

pluggy.st.secrets = {"PLUGGY_CLIENT_ID": "cid-secreto",
                     "PLUGGY_CLIENT_SECRET": "sec-secreto"}


def boom(*a, **k):
    raise requests.ConnectionError("https://api.pluggy.ai/auth?segredo=x")


requests.post = boom
try:
    pluggy.list_items()
    _fail.append("erro de rede deveria virar PluggyError")
except pluggy.PluggyError as exc:
    _ok += 1
    check("sem URL na mensagem de rede", "segredo=x" in str(exc), False)

print("  Sem credenciais configuradas")
pluggy.st.secrets = {}
check("não configurado", pluggy.is_configured(), False)
pluggy.st.secrets = {"PLUGGY_CLIENT_ID": "  ", "PLUGGY_CLIENT_SECRET": "x"}
check("valor em branco não conta", pluggy.is_configured(), False)

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
