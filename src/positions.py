"""Posição real: o que os bancos dizem que você tem, agora.

O app sempre derivou o saldo somando os lançamentos da planilha. Isso só
bate com o banco se a planilha contiver a história inteira, sem falha e
sem duplicata — coisa que nenhuma planilha mantida à mão contém. Como a
Pluggy devolve o saldo de cada conta, a posição passa a ser **lida**, e
os lançamentos voltam a ser o que sabem ser: a explicação do que mudou,
não a fonte do quanto se tem.

Os dois números continuam existindo lado a lado de propósito. A
diferença entre eles não é defeito a esconder: é exatamente o quanto
falta lançar (ou o quanto foi lançado a mais), e é a única forma de o
usuário saber onde procurar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from src import pluggy

# Tipos de conta que a Pluggy usa.
TIPO_BANCO = "BANK"
TIPO_CARTAO = "CREDIT"


@dataclass(frozen=True)
class Conta:
    nome: str
    tipo: str
    saldo: float
    instituicao: str = ""
    # Id da conta na Pluggy. É o que permite casar o saldo com o cartão
    # cadastrado aqui, já que o mapa de destinos é guardado por id — o
    # nome muda de "platinum" para outra coisa sem aviso.
    chave: str = ""
    # Só para cartão, e só quando a instituição informa (`creditData`).
    # São as respostas que o app antes deduzia: o limite e o disponível
    # vêm prontos, e as datas são as da fatura que está aberta AGORA — o
    # fechamento real deste ciclo, inclusive quando feriado ou fim de
    # semana o empurra para fora do dia cadastrado.
    limite: float | None = None
    disponivel: float | None = None
    fecha: str = ""               # ISO, fechamento da fatura aberta
    vence: str = ""               # ISO, vencimento da fatura aberta

    @property
    def usado(self) -> float | None:
        """Limite usado segundo o banco: tudo que está comprometido.

        Inclui as parcelas futuras — comprar em 10x tira o valor inteiro
        do limite de uma vez. É por isso que serve de conferência para a
        soma das faturas em aberto mais as parcelas que ainda vão vir.
        Só existe quando o banco informa limite e disponível; o `saldo`
        sozinho não é usado aqui porque cada instituição o preenche com
        um conceito diferente.
        """
        if self.limite is None or self.disponivel is None:
            return None
        return max(self.limite - self.disponivel, 0.0)


@dataclass(frozen=True)
class Ativo:
    nome: str
    classe: str
    valor: float
    instituicao: str = ""


@dataclass(frozen=True)
class Posicao:
    """Retrato do patrimônio num instante, direto das instituições."""
    contas: list[Conta] = field(default_factory=list)
    ativos: list[Ativo] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    quando: str = ""

    @property
    def em_conta(self) -> float:
        return sum(c.saldo for c in self.contas if c.tipo == TIPO_BANCO)

    @property
    def em_cartao(self) -> float:
        """Dívida de cartão, positiva quando se deve."""
        return sum(abs(c.saldo) for c in self.contas if c.tipo == TIPO_CARTAO)

    @property
    def investido(self) -> float:
        return sum(a.valor for a in self.ativos)

    @property
    def patrimonio(self) -> float:
        return self.em_conta + self.investido - self.em_cartao

    @property
    def vazia(self) -> bool:
        return not self.contas and not self.ativos


def _num(valor) -> float:
    n = pd.to_numeric(valor, errors="coerce")
    return 0.0 if pd.isna(n) else float(n)


def _valor_do_ativo(bruto: dict) -> float:
    """Valor de um investimento, tolerando os nomes que a API usa.

    A resposta traz `balance`, `value` e `amount` conforme o produto, e
    qual deles vem preenchido varia por instituição. Pegar o primeiro
    que existir evita zerar a carteira por causa do nome do campo.
    """
    for campo in ("balance", "value", "amount", "quantity"):
        if campo in bruto:
            valor = _num(bruto.get(campo))
            if valor:
                return valor
    return 0.0


def _opcional(valor) -> float | None:
    n = pd.to_numeric(valor, errors="coerce")
    return None if pd.isna(n) else float(n)


def _data_iso(valor) -> str:
    """Data da API em "AAAA-MM-DD", ou vazio se não houver."""
    if not valor:
        return ""
    lida = pd.to_datetime(str(valor), errors="coerce", utc=True)
    return "" if pd.isna(lida) else lida.date().isoformat()


def account_from_api(bruto: dict, *, instituicao: str) -> Conta:
    """Uma conta da Pluggy, com os dados de crédito quando houver.

    `creditData` traz `creditLimit`, `availableCreditLimit`,
    `balanceCloseDate` e `balanceDueDate`. Antes eram descartados, e o
    app deduzia limite, disponível e datas a partir do cadastro manual —
    três números que o banco já entregava prontos.
    """
    credito = bruto.get("creditData") or {}
    return Conta(
        nome=str(bruto.get("name") or "conta"),
        tipo=str(bruto.get("type") or "").upper(),
        saldo=_num(bruto.get("balance")),
        instituicao=instituicao,
        chave=str(bruto.get("id") or "").strip(),
        limite=_opcional(credito.get("creditLimit")),
        disponivel=_opcional(credito.get("availableCreditLimit")),
        fecha=_data_iso(credito.get("balanceCloseDate")),
        vence=_data_iso(credito.get("balanceDueDate")),
    )


def fetch(item_ids: list[str]) -> Posicao:
    """Lê contas e investimentos de todas as conexões.

    Uma conexão que falha vira erro na lista, e não exceção: uma
    instituição fora do ar não pode apagar da tela o que as outras
    responderam.
    """
    contas: list[Conta] = []
    ativos: list[Ativo] = []
    erros: list[str] = []

    for item_id in item_ids:
        rotulo = item_id[:8]
        try:
            item = pluggy.item(item_id)
            rotulo = (item.get("connector") or {}).get("name") or rotulo
        except pluggy.PluggyError as exc:
            erros.append(f"{rotulo}: {exc}")
            continue

        try:
            for bruto in pluggy.list_accounts(item_id):
                contas.append(account_from_api(bruto, instituicao=rotulo))
        except pluggy.PluggyError as exc:
            erros.append(f"{rotulo} (contas): {exc}")

        try:
            for bruto in pluggy.list_investments(item_id):
                valor = _valor_do_ativo(bruto)
                if not valor:
                    continue
                ativos.append(Ativo(
                    nome=str(bruto.get("name") or "investimento"),
                    classe=str(bruto.get("type") or bruto.get("subtype") or ""),
                    valor=valor,
                    instituicao=rotulo,
                ))
        except pluggy.PluggyError as exc:
            erros.append(f"{rotulo} (investimentos): {exc}")

    return Posicao(contas=contas, ativos=ativos, erros=erros,
                   quando=datetime.now().isoformat(timespec="minutes"))


# ---------------------------------------------------------------------------
# Persistência: o último retrato fica guardado
# ---------------------------------------------------------------------------
#
# Guardar serve a duas coisas: a tela abre instantânea em vez de esperar
# a API, e a série histórica permite ver o patrimônio crescer — algo que
# a leitura ao vivo, sozinha, nunca daria.

COLUNAS = ["Data", "Origem", "Nome", "Classe", "Valor", "Chave",
           "Limite", "Disponível", "Fechamento", "Vencimento"]


def carry_forward(nova: Posicao, anterior: Posicao) -> Posicao:
    """Completa um retrato parcial com o que o anterior tinha.

    Contas que não vieram (a conexão delas falhou) são copiadas do
    retrato anterior pela chave; investimentos, pela instituição que não
    respondeu nada desta vez.
    """
    chaves = {c.chave for c in nova.contas if c.chave}
    contas = list(nova.contas) + [c for c in anterior.contas
                                  if c.chave and c.chave not in chaves]
    com_ativos = {a.instituicao for a in nova.ativos}
    ativos = list(nova.ativos) + [a for a in anterior.ativos
                                  if a.instituicao not in com_ativos
                                  and a.instituicao not in
                                  {c.instituicao for c in nova.contas}]
    return Posicao(contas=contas, ativos=ativos, erros=nova.erros,
                   quando=nova.quando)


def card_accounts(posicao: Posicao, mapa: dict[str, str]) -> dict[str, Conta]:
    """{cartão cadastrado: conta da Pluggy}, com os dados de crédito.

    Quando duas contas apontam para o mesmo cartão (adicional), fica a
    primeira com dados de crédito: limite e disponível são do cartão, não
    somam entre titular e adicional.
    """
    out: dict[str, Conta] = {}
    for conta in posicao.contas:
        if conta.tipo != TIPO_CARTAO:
            continue
        destino = (mapa or {}).get(conta.chave)
        if not destino:
            continue
        if destino not in out or (out[destino].limite is None
                                  and conta.limite is not None):
            out[destino] = conta
    return out


def to_rows(posicao: Posicao) -> list[dict]:
    quando = posicao.quando or datetime.now().isoformat(timespec="minutes")
    linhas = [{
        "Data": quando, "Origem": c.instituicao, "Nome": c.nome,
        "Classe": c.tipo, "Valor": c.saldo, "Chave": c.chave,
        "Limite": "" if c.limite is None else c.limite,
        "Disponível": "" if c.disponivel is None else c.disponivel,
        "Fechamento": c.fecha, "Vencimento": c.vence,
    } for c in posicao.contas]
    linhas += [{
        "Data": quando, "Origem": a.instituicao, "Nome": a.nome,
        "Classe": a.classe or "INVESTIMENTO", "Valor": a.valor,
        "Chave": "", "Limite": "", "Disponível": "", "Fechamento": "",
        "Vencimento": "",
    } for a in posicao.ativos]
    return linhas


def from_rows(df: pd.DataFrame) -> Posicao:
    """Reconstrói a posição a partir do retrato mais recente guardado."""
    if df.empty or "Data" not in df.columns:
        return Posicao()
    ultima = df["Data"].astype(str).max()
    recorte = df[df["Data"].astype(str) == ultima]

    contas, ativos = [], []
    for _, linha in recorte.iterrows():
        classe = str(linha.get("Classe") or "").upper()
        valor = _num(linha.get("Valor"))
        nome = str(linha.get("Nome") or "")
        origem = str(linha.get("Origem") or "")
        if classe in (TIPO_BANCO, TIPO_CARTAO):
            contas.append(Conta(
                nome, classe, valor, origem,
                str(linha.get("Chave") or "").strip(),
                limite=_opcional(linha.get("Limite")),
                disponivel=_opcional(linha.get("Disponível")),
                fecha=_data_iso(linha.get("Fechamento")),
                vence=_data_iso(linha.get("Vencimento")),
            ))
        else:
            ativos.append(Ativo(nome, classe, valor, origem))
    return Posicao(contas=contas, ativos=ativos, quando=str(ultima))


def invested_history(df: pd.DataFrame) -> pd.DataFrame:
    """Posição investida por dia, para ver a carteira crescer.

    Separado do patrimônio: aqui não entram conta corrente nem cartão,
    só o que está aplicado. É a curva que responde "quanto minha
    carteira rendeu", e misturá-la com saldo em conta a tornaria uma
    curva de outra coisa.
    """
    vazio = pd.DataFrame(columns=["Data", "Investido"])
    if df.empty or "Data" not in df.columns:
        return vazio
    base = df.copy()
    base["_carimbo"] = base["Data"].astype(str)
    base["_dia"] = base["_carimbo"].str.slice(0, 10)
    ultimo = base.groupby("_dia")["_carimbo"].transform("max")
    base = base[base["_carimbo"] == ultimo]

    classe = base["Classe"].astype(str).str.upper()
    base = base[~classe.isin([TIPO_BANCO, TIPO_CARTAO])]
    if base.empty:
        return vazio
    base["Valor"] = pd.to_numeric(base["Valor"], errors="coerce").fillna(0)

    fora = base.groupby("_dia")["Valor"].sum().reset_index()
    fora.columns = ["Data", "Investido"]
    return fora.sort_values("Data")


def history(df: pd.DataFrame) -> pd.DataFrame:
    """Patrimônio por DIA, para o gráfico de evolução.

    Um retrato por clique em Atualizar encheria o eixo de horários —
    "21:40, 21:45, 21:50" — o que não é a pergunta que o gráfico
    responde. Fica o último retrato de cada dia: o patrimônio ao fim
    daquele dia, que é o que se quer comparar com o dia seguinte.
    """
    vazio = pd.DataFrame(columns=["Data", "Patrimônio"])
    if df.empty or "Data" not in df.columns:
        return vazio
    base = df.copy()
    base["Valor"] = pd.to_numeric(base["Valor"], errors="coerce").fillna(0)
    base["_carimbo"] = base["Data"].astype(str)
    base["_dia"] = base["_carimbo"].str.slice(0, 10)

    # Dentro de um dia, só o retrato mais recente conta.
    ultimo = base.groupby("_dia")["_carimbo"].transform("max")
    base = base[base["_carimbo"] == ultimo]
    if base.empty:
        return vazio

    classe = base["Classe"].astype(str).str.upper()
    # Cartão é dívida: entra negativo no patrimônio.
    peso = classe.map(lambda c: -1 if c == TIPO_CARTAO else 1)
    base = base.assign(_val=base["Valor"].abs() * peso)

    fora = base.groupby("_dia")["_val"].sum().reset_index()
    fora.columns = ["Data", "Patrimônio"]
    return fora.sort_values("Data")
