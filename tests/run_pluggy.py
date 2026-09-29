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

# Um 400 é chamada malformada; trocar de header esconderia o erro real,
# e engolir o corpo da resposta esconderia a única pista concreta.
print("  Erro HTTP preserva a explicação da Pluggy")

# O bloco anterior deixou as credenciais em branco de propósito; daqui
# em diante os testes precisam de credenciais válidas de novo.
pluggy.st.secrets = {"PLUGGY_CLIENT_ID": "cid-secreto",
                     "PLUGGY_CLIENT_SECRET": "sec-secreto"}


def make_status(code, body=None, text=""):
    vistos = []

    def fake_get(url, headers=None, params=None, timeout=None):
        vistos.append(dict(headers or {}))
        r = Resp(code, body)
        r.text = text
        if body is None:
            r.json = lambda: (_ for _ in ()).throw(ValueError("no json"))
        return r
    return fake_get, vistos


requests.post = fake_post
_g, _vistos = make_status(400, {"message": "pageSize must not exceed 100"})
requests.get = _g
try:
    pluggy.list_items()
    _fail.append("HTTP 400 deveria levantar")
except pluggy.PluggyError as exc:
    _ok += 1
    check("o corpo da Pluggy chega à tela",
          "pageSize must not exceed 100" in str(exc), True)
    check("400 não troca de header", len(_vistos), 1)

_g, _vistos = make_status(403, {"message": "forbidden"})
requests.get = _g
try:
    pluggy.list_items()
    _fail.append("HTTP 403 deveria levantar")
except pluggy.PluggyError as exc:
    _ok += 1
    check("403 tenta os dois headers", len(_vistos), 2)
    check("e sugere o app parceiro", "app parceiro" in str(exc), True)

_g, _ = make_status(500, None, "<html>Internal Server Error</html>")
requests.get = _g
try:
    pluggy.list_items()
    _fail.append("HTTP 500 deveria levantar")
except pluggy.PluggyError as exc:
    _ok += 1
    check("corpo não-JSON não quebra o cliente",
          "Internal Server Error" in str(exc), True)

print("  Sondagem de endpoints")


def _varia(url, headers=None, params=None, timeout=None):
    if "/connectors" in url:
        return Resp(200, {"results": [{"id": 1}]})
    if "/v2/items" in url:
        if (params or {}).get("pageSize"):
            return Resp(200, {"results": [{"id": "i1"}], "nextCursor": None})
        return Resp(400, {"message": "pageSize is required"})
    return Resp(404, {"message": "not found"})


requests.get = _varia
_p = pluggy.probe()
check("sonda cinco chamadas", len(_p), 5)
check("e nunca levanta", all("Chamada" in r for r in _p), True)
check("distingue 200 de 400 de 404",
      [r["HTTP"] for r in _p], [200, 400, 200, 404, 404])

print("  Criação da conexão (connect token e URL)")

requests.post = lambda url, json=None, timeout=None, headers=None: (
    Resp(200, {"apiKey": "k"}) if url.endswith("/auth")
    else Resp(200, {"accessToken": "tok-123"}))
check("token de conexão", pluggy.connect_token(), "tok-123")

_url = pluggy.connect_url("tok-123")
check("aponta para a página hospedada",
      _url.startswith("https://connect.pluggy.ai/?"), True)
check("leva o token no parâmetro que a página lê",
      "connect_token=tok-123" in _url, True)
check("restringe ao conector do Meu Pluggy",
      "connectorIds=200" in _url, True)
check("sem connector, não restringe",
      "connectorIds" in pluggy.connect_url("t", connector_id=None), False)
check("reconectar um item existente",
      "updateItem=abc" in pluggy.connect_url("t", item_id="abc"), True)
# Sem isso, autorizar o segundo banco atualizaria a conexão do primeiro
# em vez de criar outra, e o primeiro sairia do ar sem aviso.
check("cada autorização cria uma conexão nova",
      "avoidDuplicates=false" in _url, True)
check("mas reconectar não duplica",
      "avoidDuplicates" in pluggy.connect_url("t", item_id="abc"), False)

requests.post = lambda url, json=None, timeout=None, headers=None: (
    Resp(200, {"apiKey": "k"}) if url.endswith("/auth") else Resp(200, {}))
try:
    pluggy.connect_token()
    _fail.append("resposta sem accessToken deveria levantar")
except pluggy.PluggyError:
    _ok += 1

# /v2/items recusa pageSize, e a validação roda ANTES da autenticação:
# mandar o parâmetro esconderia o 403 real atrás de um 400.
print("  /v2/items é chamado sem pageSize")
_params_vistos = []


def _sem_pagesize(url, headers=None, params=None, timeout=None):
    _params_vistos.append(dict(params or {}))
    if "pageSize" in (params or {}):
        return Resp(400, {"message": "property pageSize should not exist"})
    return Resp(200, {"results": [{"id": "i1"}], "nextCursor": None})


requests.post = fake_post
requests.get = _sem_pagesize
check("lista sem estourar", [i["id"] for i in pluggy.list_items()], ["i1"])
check("nenhuma chamada levou pageSize",
      any("pageSize" in p for p in _params_vistos), False)

# O mesmo 400 apareceu depois em /v2/transactions: nenhum endpoint /v2
# aceita o parâmetro, então o padrão é não mandar.
_params_vistos.clear()
check("transações também vêm sem pageSize",
      [t["id"] for t in pluggy.list_transactions("acc-1")], ["i1"])
check("e nenhuma levou pageSize",
      any("pageSize" in p for p in _params_vistos), False)
check("mas o filtro de conta vai junto",
      _params_vistos[0].get("accountId"), "acc-1")

# O endpoint recusou `pageSize` e depois `from`; o recorte por data é
# feito no app, então nenhum parâmetro além da conta deve ser enviado.
check("só accountId vai no pedido",
      sorted(_params_vistos[0]), ["accountId"])

print("  Ficha do conector")


def _ficha(url, headers=None, params=None, timeout=None):
    if url.endswith("/connectors/200"):
        return Resp(200, {"id": 200, "name": "MeuPluggy", "type": "PERSONAL_BANK",
                          "credentials": [{"name": "token", "label": "Token",
                                           "type": "text", "optional": False}]})
    return Resp(404, {"message": "not found"})


requests.post, requests.get = fake_post, _ficha
check("lê a ficha do MeuPluggy por padrão",
      pluggy.connector()["name"], "MeuPluggy")
check("expõe os campos pedidos",
      [c["name"] for c in pluggy.connector()["credentials"]], ["token"])
try:
    pluggy.connector(999)
    _fail.append("conector inexistente deveria levantar")
except pluggy.PluggyError:
    _ok += 1

# A conta do usuário recusa listar conexões (403), mas lê cada uma pelo
# id. Sem este caminho, o app ficaria cego mesmo com tudo autorizado.
print("  Ler uma conexão pelo id quando a listagem é negada")


def _so_por_id(url, headers=None, params=None, timeout=None):
    if url.endswith("/v2/items") or url.endswith("/items"):
        return Resp(403, {"code": 403,
                          "codeDescription": "API_KEY_MISSING_OR_INVALID"})
    if "/items/" in url:
        uid = url.rsplit("/", 1)[-1]
        if uid == "bom":
            return Resp(200, {"id": "bom", "status": "UPDATED",
                              "connector": {"name": "Nubank"}})
        return Resp(404, {"message": "item not found"})
    return Resp(400, {"message": "itemId should not be null"})


requests.post, requests.get = fake_post, _so_por_id
try:
    pluggy.list_items()
    _fail.append("listagem deveria levantar")
except pluggy.PluggyError:
    _ok += 1
check("mas a conexão é lida pelo id", pluggy.item("bom")["connector"]["name"],
      "Nubank")
check("espaços em volta do id não atrapalham",
      pluggy.item("  bom  ")["id"], "bom")
try:
    pluggy.item("ruim")
    _fail.append("id inexistente deveria levantar")
except pluggy.PluggyError as exc:
    _ok += 1
    check("e diz o motivo", "item not found" in str(exc), True)

# A tela hospedada conecta mas não revela o id criado, e esta conta não
# lista conexões — sem o id o app fica cego mesmo com tudo autorizado.
print("  Widget embutido revela o itemId")

_h = pluggy.connect_widget_html("tok-xyz")
check("carrega o SDK", "pluggy-connect-sdk@2.14.2/+esm" in _h, True)
check("leva o token", "tok-xyz" in _h, True)
check("restringe ao conector do Meu Pluggy", '"connectorIds": [200]' in _h, True)
check("pede conexão nova", '"avoidDuplicates": true' in _h, True)
check("trata o sucesso", "onSuccess" in _h, True)
check("e o erro", "onError" in _h, True)
# Import estático falha ANTES de qualquer try, e dentro de um iframe
# isso não aparece em lugar nenhum — a tela fica só em branco.
check("import é dinâmico", "await import(" in _h, True)
check("captura erro solto", 'window.addEventListener("error"' in _h, True)
check("captura promessa rejeitada", "unhandledrejection" in _h, True)
check("mostra estado antes de carregar", "Carregando o widget" in _h, True)
check("um único bloco de script",
      (_h.count("<script"), _h.count("</script>")), (1, 1))

_h2 = pluggy.connect_widget_html("t", item_id="abc")
check("modo reconexão", '"updateItem": "abc"' in _h2, True)
check("reconectar não duplica", '"avoidDuplicates": false' in _h2, True)
check("sem conector não restringe",
      "connectorIds" in pluggy.connect_widget_html("t", connector_id=None),
      False)

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
