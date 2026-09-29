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

import json
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
import streamlit as st

from src.config import Colors

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


def _request(path: str, params: dict | None = None,
             ) -> tuple[int, str, dict | None]:
    """GET autenticado cru: devolve (status, corpo, json) sem levantar.

    A documentação não fixa o nome do header, então tenta `X-API-KEY` e
    só cai para `Authorization: Bearer` quando o primeiro é recusado por
    autorização — um 400 não é motivo para trocar de header, e tentar de
    novo só esconderia o erro real.
    """
    creds = credentials()
    if creds is None:
        raise PluggyError("Credenciais da Pluggy não configuradas.")
    key = _api_key(creds.client_id, creds.client_secret)

    ultimo: tuple[int, str, dict | None] = (0, "", None)
    for header in ({"X-API-KEY": key}, {"Authorization": f"Bearer {key}"}):
        try:
            resp = requests.get(
                f"{BASE_URL}{path}", headers=header, params=params or {},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise PluggyError(
                f"Não consegui falar com a Pluggy: {type(exc).__name__}")
        try:
            corpo = resp.json()
            texto = str(corpo)
        except ValueError:
            corpo, texto = None, resp.text[:400]
        ultimo = (resp.status_code, texto, corpo)
        if resp.status_code not in (401, 403):
            return ultimo
    return ultimo


def _get(path: str, params: dict | None = None) -> dict:
    status, texto, corpo = _request(path, params)
    if status == 200 and corpo is not None:
        return corpo
    if status in (401, 403):
        raise PluggyError(
            f"GET {path} foi recusado por falta de autorização (HTTP "
            f"{status}). Se as conexões foram feitas no Meu Pluggy, pode "
            f"faltar autorizar esta aplicação como app parceiro. "
            f"Resposta: {texto}"
        )
    # O corpo é a descrição do erro da própria Pluggy — não carrega
    # credencial e é a única pista concreta do que está errado.
    raise PluggyError(f"GET {path} devolveu HTTP {status}. Resposta: {texto}")


def probe() -> list[dict]:
    """Bate em vários endpoints e relata o que cada um respondeu.

    Serve para descobrir, numa tentativa só, qual caminho esta conta
    aceita: a API tem variantes (`/items` e `/v2/items`) e nomes de
    parâmetro que mudaram entre versões, e cada combinação errada
    devolve o mesmo 400 opaco.
    """
    tentativas = [
        ("GET /connectors", "/connectors", {"pageSize": 1}),
        ("GET /v2/items", "/v2/items", None),
        ("GET /connectors (todos)", "/connectors", None),
        ("GET /items", "/items", None),
        ("GET /accounts", "/accounts", None),
    ]
    out = []
    for rotulo, path, params in tentativas:
        try:
            status, texto, _ = _request(path, params)
        except PluggyError as exc:
            out.append({"Chamada": rotulo, "HTTP": "—",
                        "Resposta": str(exc)[:300]})
            continue
        out.append({"Chamada": rotulo, "HTTP": status,
                    "Resposta": texto[:300]})
    return out


def _paginate(path: str, params: dict | None = None,
              page_size: int | None = None) -> list[dict]:
    """Percorre um endpoint paginado por cursor, juntando os resultados.

    O padrão é NÃO mandar `pageSize`: os endpoints `/v2` recusam o
    parâmetro com "property pageSize should not exist" — visto em
    `/v2/items` e de novo em `/v2/transactions`. Como a validação roda
    antes da autenticação, mandá-lo esconde qualquer outro erro atrás de
    um 400. Quem precisa de tamanho de página passa explicitamente.
    """
    out: list[dict] = []
    cursor: str | None = None
    for _ in range(50):                     # teto de segurança
        page = dict(params or {})
        if page_size is not None:
            page["pageSize"] = page_size
        if cursor:
            page["cursor"] = cursor
        data = _get(path, page)
        out.extend(data.get("results") or [])
        cursor = data.get("nextCursor")
        if not cursor:
            break
    return out


# ---------------------------------------------------------------------------
# Criar a conexão (item)
# ---------------------------------------------------------------------------
#
# Os bancos ligados no Meu Pluggy pertencem ao Meu Pluggy, não a esta
# aplicação — por isso `/v2/items` responde que não há autorização. O elo
# é feito criando um item com o conector "MeuPluggy", que a API lista
# como o único disponível para esta aplicação: o usuário entra com a
# conta do Meu Pluggy e autoriza, e as conexões dele passam a ser
# visíveis aqui.

MEU_PLUGGY_CONNECTOR = 200
CONNECT_URL = "https://connect.pluggy.ai/"


def connector(connector_id: int = MEU_PLUGGY_CONNECTOR) -> dict:
    """Ficha de um conector, incluindo os campos que ele pede.

    A tela de conexão da Pluggy monta o formulário a partir daqui. Se o
    campo não aparece — ou aparece e não se sabe o que preencher — é esta
    lista que diz o nome, o rótulo e o formato esperado.
    """
    return _get(f"/connectors/{connector_id}")


def connect_token() -> str:
    """Token de curta duração (30 min) que autoriza a tela de conexão."""
    creds = credentials()
    if creds is None:
        raise PluggyError("Credenciais da Pluggy não configuradas.")
    key = _api_key(creds.client_id, creds.client_secret)
    try:
        resp = requests.post(
            f"{BASE_URL}/connect_token", json={},
            headers={"X-API-KEY": key}, timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PluggyError(f"Não consegui falar com a Pluggy: {type(exc).__name__}")
    if resp.status_code != 200:
        raise PluggyError(
            f"POST /connect_token devolveu HTTP {resp.status_code}. "
            f"Resposta: {str(resp.text)[:300]}"
        )
    token = (resp.json() or {}).get("accessToken")
    if not token:
        raise PluggyError("A Pluggy respondeu sem accessToken.")
    return str(token)


# O widget roda num iframe próprio e não enxerga as variáveis CSS do
# app, então as cores vão literais — as duas saíram da paleta validada.
COR_ERRO = Colors.SERIES[4]
COR_OK = Colors.SERIES[0]

CONNECT_SDK = "https://cdn.jsdelivr.net/npm/pluggy-connect-sdk@2.14.2/+esm"


def connect_widget_html(token: str, *,
                        connector_id: int | None = MEU_PLUGGY_CONNECTOR,
                        item_id: str | None = None) -> str:
    """Página que roda o widget da Pluggy e mostra o `itemId` no fim.

    A página hospedada da Pluggy conecta, mas não diz qual identificador
    foi criado — e esta conta não permite listar conexões, então sem o
    identificador o app fica cego mesmo com tudo autorizado. Aqui o
    `onSuccess` do widget recebe esse valor e o imprime na tela para
    copiar. Nada é enviado para fora: o valor só aparece.
    """
    opcoes = {
        "connectToken": token,
        "includeSandbox": False,
        "avoidDuplicates": item_id is None,
    }
    if connector_id is not None:
        opcoes["connectorIds"] = [connector_id]
    if item_id:
        opcoes["updateItem"] = item_id

    return """
<div style="font-family:system-ui">
  <div id="estado" style="padding:10px;border-radius:8px;background:#f1f5f9">
    Carregando o widget da Pluggy…
  </div>
  <div id="saida" style="padding:10px"></div>
</div>
<script type="module">
const estado = document.getElementById("estado");
const saida = document.getElementById("saida");

const caixa = (cor, titulo, corpo) =>
  '<div style="border:2px solid ' + cor + ';border-radius:10px;padding:16px">' +
  '<b>' + titulo + '</b><div style="margin-top:8px">' + corpo + '</div></div>';

// Erro dentro de um iframe não aparece em lugar nenhum, então tudo que
// pode falhar é capturado e escrito na própria caixa.
window.addEventListener("error", (e) =>
  estado.innerHTML = caixa(COR_ERRO, "Erro no widget", String(e.message)));
window.addEventListener("unhandledrejection", (e) =>
  estado.innerHTML = caixa(COR_ERRO, "Erro no widget", String(e.reason)));

try {
  // `import()` dinâmico, e não estático: a falha de um import estático
  // acontece antes de qualquer try e deixaria a área em branco.
  const mod = await import("%s");
  const PluggyConnect = mod.default || mod.PluggyConnect;
  if (!PluggyConnect) throw new Error("SDK carregou sem a classe esperada");

  estado.textContent = "Widget carregado. Abrindo…";
  const pluggy = new PluggyConnect(Object.assign(%s, {
    onSuccess: (data) => {
      const item = (data && data.item) || {};
      const nome = (item.connector && item.connector.name) || "banco";
      estado.style.display = "none";
      saida.innerHTML = caixa(COR_OK, "Conectado: " + nome,
        'Copie este identificador e cole no passo 2:' +
        '<div style="margin-top:8px;font-family:monospace;font-size:18px;' +
        'user-select:all;background:#f1f5f9;padding:12px;border-radius:6px">' +
        (item.id || "(sem id)") + '</div>');
    },
    onError: (err) => {
      estado.innerHTML = caixa(COR_ERRO, "Não deu certo",
        (err && (err.message || err.code)) || JSON.stringify(err));
    },
    onEvent: (evento) => {
      if (evento && evento.event === "LOAD_SUCCESS")
        estado.textContent = "Widget aberto — siga os passos na janela.";
    },
  }));
  pluggy.init();
} catch (e) {
  estado.innerHTML = caixa(COR_ERRO, "Não consegui carregar o widget",
    String(e && e.message ? e.message : e) +
    '<br><br>Use o botão abaixo para abrir a tela da Pluggy.');
}
</script>
""".replace("COR_ERRO", f'"{COR_ERRO}"').replace("COR_OK", f'"{COR_OK}"') % (CONNECT_SDK, json.dumps(opcoes))


def connect_url(token: str, *, connector_id: int | None = MEU_PLUGGY_CONNECTOR,
                item_id: str | None = None) -> str:
    """URL da tela de conexão hospedada pela Pluggy.

    Abrir a página hospedada evita embutir o widget JavaScript dentro do
    Streamlit, que não tem como devolver o `itemId` para o Python.

    O Meu Pluggy deixa compartilhar um banco por autorização, então
    conectar o segundo exige repetir o processo. `avoidDuplicates=false`
    é o que permite isso: sem ele, a segunda autorização com o mesmo
    conector atualizaria a conexão existente em vez de criar outra, e o
    primeiro banco sairia do ar em silêncio.
    """
    params = {"connect_token": token, "avoidDuplicates": "false"}
    if connector_id is not None:
        params["connectorIds"] = str(connector_id)
    if item_id:                       # reconectar um item existente
        params["updateItem"] = item_id
        params.pop("avoidDuplicates")
    return CONNECT_URL + "?" + urlencode(params)



# ---------------------------------------------------------------------------
# Leituras
# ---------------------------------------------------------------------------

def item(item_id: str) -> dict:
    """Uma conexão pelo id.

    Existe porque listar conexões (`/v2/items`) devolve 403 nesta conta:
    a chave tem permissão para ler uma conexão específica e as contas
    dela, mas não para enumerar todas. Guardar os ids é o contorno.
    """
    return _get(f"/items/{str(item_id).strip()}")


def list_items() -> list[dict]:
    """Conexões (bancos) que o usuário autorizou.

    É o que dispensa o usuário de caçar o `itemId` na interface da
    Pluggy: a própria API diz quais conexões existem.
    """
    return _paginate("/v2/items")


def list_accounts(item_id: str) -> list[dict]:
    """Contas de uma conexão — corrente, poupança e cartões."""
    return (_get("/accounts", {"itemId": item_id}).get("results") or [])


def list_transactions(account_id: str) -> list[dict]:
    """Todos os lançamentos de uma conta.

    Sem filtro de data de propósito. O endpoint recusou `pageSize` e
    depois `from`, cada recusa custando um deploy para descobrir; o
    recorte por data é feito no app, onde não depende de adivinhar o
    nome do parâmetro. São 12 meses no máximo — volume que não justifica
    continuar tentando.
    """
    return _paginate("/v2/transactions", {"accountId": account_id})


def list_bills(account_id: str) -> list[dict]:
    """Faturas de um cartão, com data de fechamento e vencimento."""
    return (_get("/bills", {"accountId": account_id}).get("results") or [])


def list_investments(item_id: str) -> list[dict]:
    return (_get("/investments", {"itemId": item_id}).get("results") or [])
