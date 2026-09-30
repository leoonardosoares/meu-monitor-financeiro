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
                contas.append(Conta(
                    nome=str(bruto.get("name") or "conta"),
                    tipo=str(bruto.get("type") or "").upper(),
                    saldo=_num(bruto.get("balance")),
                    instituicao=rotulo,
                    chave=str(bruto.get("id") or "").strip(),
                ))
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

COLUNAS = ["Data", "Origem", "Nome", "Classe", "Valor", "Chave"]


def card_balances(posicao: Posicao, mapa: dict[str, str]) -> dict[str, float]:
    """{cartão cadastrado: dívida informada pela instituição}.

    Casa pelo id da conta na Pluggy, que é o que o mapa de destinos
    guarda. Casar por nome quebraria no dia em que o banco renomeasse
    "platinum" — e quebraria em silêncio, mostrando dívida zero.

    Dois cartões da Pluggy apontando para o mesmo cartão aqui somam,
    que é o certo quando alguém tem cartão adicional.
    """
    out: dict[str, float] = {}
    for conta in posicao.contas:
        if conta.tipo != TIPO_CARTAO:
            continue
        destino = (mapa or {}).get(conta.chave)
        if destino:
            out[destino] = out.get(destino, 0.0) + abs(conta.saldo)
    return out


def to_rows(posicao: Posicao) -> list[dict]:
    quando = posicao.quando or datetime.now().isoformat(timespec="minutes")
    linhas = [{
        "Data": quando, "Origem": c.instituicao, "Nome": c.nome,
        "Classe": c.tipo, "Valor": c.saldo, "Chave": c.chave,
    } for c in posicao.contas]
    linhas += [{
        "Data": quando, "Origem": a.instituicao, "Nome": a.nome,
        "Classe": a.classe or "INVESTIMENTO", "Valor": a.valor,
        "Chave": "",
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
            contas.append(Conta(nome, classe, valor, origem,
                                str(linha.get("Chave") or "").strip()))
        else:
            ativos.append(Ativo(nome, classe, valor, origem))
    return Posicao(contas=contas, ativos=ativos, quando=str(ultima))


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
