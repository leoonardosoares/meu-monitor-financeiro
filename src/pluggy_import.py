"""Traz lançamentos do Open Finance para a planilha.

Separado de `pluggy.py` de propósito: lá é só o cliente HTTP, aqui é a
tradução para o modelo do app — e é a tradução que precisa de teste, já
que nenhuma das duas pontas pode ser exercitada de verdade daqui.

A regra que sustenta tudo: **nada é gravado sem o usuário conferir**. A
sincronização só monta uma lista de pendências; a gravação acontece na
tela de triagem, depois do aceite. Assim um erro de sinal ou de
categoria vira um ajuste na tela, e não uma linha errada na planilha.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

import pandas as pd

from src import credit_card as cc
from src.config import CATEGORIA_TRANSFERENCIA
from src.dates import month_label, parse_dates

# Onde cada conta da Pluggy pode desaguar.
DESTINO_IGNORAR = "Ignorar"
DESTINO_BANCO = "Entradas e Saídas"

# Saídas do banco que NÃO são despesa nova. O pagamento da fatura é o
# caso perigoso: as compras já entram pelo cartão, então importar o
# débito como gasto contaria o mesmo dinheiro duas vezes. O app já trata
# a categoria "Cartão de Crédito" como quitação e a exclui do orçamento
# — basta classificar assim na entrada. Aporte de investimento segue a
# mesma lógica: é transferência entre contas do mesmo dono.
_TRANSFERENCIAS = (
    ("Cartão de Crédito", re.compile(
        r"pagamento.*(fatura|cartao)|fatura.*(cartao|paga)|"
        r"pgto.*(fatura|cartao)|credit.?card.?payment")),
    ("Investimento", re.compile(
        r"\b(aplicacao|aplicac|resgate|cdb|lci|lca|tesouro|poupanca|"
        r"investiment)\b")),
)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", str(texto)) \
        .encode("ascii", "ignore").decode().lower()


# Juros, rendimento e dividendo não são transferência: é patrimônio que
# cresceu. Tratá-los como movimentação entre contas sumiria com o
# rendimento da sua receita — justamente o que o investimento produziu.
_RENDIMENTO = re.compile(r"\b(rendiment|juros|dividend|provento|remunerac)")


def transfer_category(descricao: str, categoria_pluggy: str = "") -> str | None:
    """Categoria de transferência, quando o lançamento é uma.

    `None` quando é despesa ou receita de verdade.
    """
    alvo = _sem_acento(descricao) + " " + _sem_acento(categoria_pluggy)
    if _RENDIMENTO.search(alvo):
        return None
    for categoria, padrao in _TRANSFERENCIAS:
        if padrao.search(alvo):
            return categoria
    return None


# Campos em que a data de fechamento pode vir, na ordem de preferência.
# Varia por instituição, e adivinhar um nome só zeraria o mapa.
# `billClosingDate` é o nome que a Pluggy usa de fato — descoberto
# olhando a resposta, depois de a coluna "Fecha" vir vazia por eu ter
# apostado nos outros nomes. Os demais ficam como alternativas.
_CAMPOS_FECHAMENTO = ("billClosingDate", "closeDate", "closingDate",
                      "billDate", "periodEnd", "endDate", "referenceDate")
_CAMPOS_VENCIMENTO = ("dueDate", "paymentDueDate", "due_date")


def _primeira_data(bruto: dict, campos: tuple[str, ...]) -> date | None:
    for campo in campos:
        if campo not in bruto:
            continue
        serie = parse_dates(pd.Series([bruto.get(campo)]))
        valor = serie.iloc[0]
        if not pd.isna(valor):
            return valor.date()
    return None


def bill_month(bill: dict, *, closing_day: int, due_day: int) -> str | None:
    """Rótulo "MM/AAAA" da fatura, a partir do que o banco informou.

    A convenção do app é nomear a fatura pelo mês em que ela FECHA —
    confirmada contra o banco do usuário. Quando o fechamento vem na
    resposta, é ele que manda. Quando só há vencimento, descobre-se o
    mês testando os candidatos: aquele cujo vencimento calculado bate
    com o informado é o mês certo, o que dispensa supor se o pagamento
    cai no próprio mês ou no seguinte.
    """
    fechamento = _primeira_data(bill, _CAMPOS_FECHAMENTO)
    if fechamento is not None:
        return month_label(pd.Timestamp(fechamento))

    vencimento = _primeira_data(bill, _CAMPOS_VENCIMENTO)
    if vencimento is None:
        return None

    alvo = pd.Timestamp(vencimento)
    for deslocamento in (0, -1, 1):
        candidato = month_label(alvo + pd.DateOffset(months=deslocamento))
        try:
            _, venc = cc.invoice_dates(candidato, closing_day, due_day)
        except ValueError:
            continue
        if venc.date() == vencimento:
            return candidato
    # Sem casar, o mês do vencimento é o palpite menos ruim — e some
    # do caminho assim que a instituição informar o fechamento.
    return month_label(alvo)


def bill_index(bills: list[dict], *, closing_day: int,
               due_day: int) -> dict[str, str]:
    """{id da fatura: "MM/AAAA"}, para casar com o `billId` da compra."""
    out: dict[str, str] = {}
    for bill in bills or []:
        ident = str(bill.get("id") or "").strip()
        if not ident:
            continue
        mes = bill_month(bill, closing_day=closing_day, due_day=due_day)
        if mes:
            out[ident] = mes
    return out


_CAMPOS_TOTAL = ("totalAmount", "total", "amount", "balance", "value")


def bill_rows(bills: list[dict], *, cartao: str, closing_day: int,
              due_day: int, lido_em: date) -> list[dict]:
    """Faturas do banco em linhas, para a planilha guardar.

    Guarda o total que a instituição informa. Somar as linhas que o app
    tem só dá o mesmo número quando nenhuma compra faltou — e uma compra
    que não chegou é invisível justamente na soma.
    """
    out: list[dict] = []
    for bill in bills or []:
        mes = bill_month(bill, closing_day=closing_day, due_day=due_day)
        if not mes:
            continue
        total = 0.0
        for campo in _CAMPOS_TOTAL:
            if campo in bill:
                valor = pd.to_numeric(bill.get(campo), errors="coerce")
                if not pd.isna(valor) and float(valor):
                    total = abs(float(valor))
                    break
        fechamento = _primeira_data(bill, _CAMPOS_FECHAMENTO)
        vencimento = _primeira_data(bill, _CAMPOS_VENCIMENTO)
        out.append({
            "Cartão": cartao,
            "Mês": mes,
            "Total": round(total, 2),
            "Fechamento": fechamento.isoformat() if fechamento else "",
            "Vencimento": vencimento.isoformat() if vencimento else "",
            "Situação": str(bill.get("status") or ""),
            "Lido em": lido_em.isoformat(),
        })
    return out


def _dia_mais_comum(datas: list[date]) -> int | None:
    """Dia do mês que mais se repete — o ciclo do cartão é mensal.

    No empate fica o MENOR dia. Vencimento que cai em fim de semana ou
    feriado é empurrado para frente, nunca para trás, então o dia menor
    é o nominal e o maior é a exceção daquele mês.
    """
    if not datas:
        return None
    contagem: dict[int, int] = {}
    for d in datas:
        contagem[d.day] = contagem.get(d.day, 0) + 1
    return min(contagem.items(), key=lambda x: (-x[1], x[0]))[0]


def infer_card_days(bills: list[dict],
                    transactions: list[dict]) -> tuple[int | None, int | None]:
    """(dia de fechamento, dia de vencimento) deduzidos do banco.

    O **vencimento** vem direto: é o dia das datas de vencimento das
    faturas. O **fechamento** a Pluggy não informa, mas o extrato o
    denuncia — a última compra de cada fatura cai no dia em que ela
    fechou, ou perto dele. Tomar o dia mais frequente entre essas
    últimas compras erra pouco e não depende de o usuário lembrar.

    Devolve `None` para o que não der para deduzir, em vez de chutar:
    um dia inventado desloca fatura inteira.
    """
    vencimentos = [d for d in
                   (_primeira_data(b, _CAMPOS_VENCIMENTO) for b in bills or [])
                   if d is not None]
    dia_venc = _dia_mais_comum(vencimentos)

    # Quando a instituição informa o fechamento, ele é a resposta — não
    # há por que deduzir do extrato o que veio escrito.
    fechamentos = [d for d in
                   (_primeira_data(b, _CAMPOS_FECHAMENTO) for b in bills or [])
                   if d is not None]
    if fechamentos:
        return _dia_mais_comum(fechamentos), dia_venc

    # Sem ele, a última compra de cada fatura denuncia onde ela fechou.
    ultimas: dict[str, date] = {}
    for tx in transactions or []:
        ident = bill_id(tx)
        if not ident:
            continue
        quando = _data(tx)
        if quando is None:
            continue
        if ident not in ultimas or quando > ultimas[ident]:
            ultimas[ident] = quando
    dia_fech = _dia_mais_comum(list(ultimas.values()))

    return dia_fech, dia_venc


def bill_id(tx: dict) -> str:
    """Fatura a que a compra pertence, segundo o banco."""
    meta = tx.get("creditCardMetadata") or {}
    for campo in ("billId", "bill_id"):
        valor = meta.get(campo) or tx.get(campo)
        if valor:
            return str(valor).strip()
    return ""


def installment_label(tx: dict) -> str:
    """"3/6" a partir do que a Pluggy informa; "1/1" quando não é parcelada.

    Sem isso toda compra importada apareceria como parcela única, e o
    extrato do cartão perderia a informação que explica por que o mesmo
    nome reaparece nos meses seguintes.
    """
    meta = tx.get("creditCardMetadata") or {}
    atual = pd.to_numeric(meta.get("installmentNumber"), errors="coerce")
    total = pd.to_numeric(meta.get("totalInstallments"), errors="coerce")
    if pd.isna(atual) or pd.isna(total) or int(total) < 1:
        return "1/1"
    return f"{max(int(atual), 1)}/{int(total)}"


@dataclass
class Pendente:
    """Um lançamento novo, ainda não gravado."""
    pluggy_id: str
    data: date
    descricao: str
    valor: float                 # sempre positivo
    tipo: str                    # "Entrada" ou "Saída"
    destino: str                 # DESTINO_BANCO ou o nome de um cartão
    conta: str                   # conta de origem, para o usuário conferir
    categoria: str = "Outros"
    mes_fatura: str = ""         # só para cartão
    parcela: str = "1/1"         # só para cartão
    categoria_pluggy: str = ""   # o palpite do banco, como referência

    @property
    def is_cartao(self) -> bool:
        return self.destino not in (DESTINO_BANCO, DESTINO_IGNORAR)


def parse_mapping(raw: str) -> dict[str, str]:
    """"conta=destino;conta=destino" -> dicionário."""
    out: dict[str, str] = {}
    for par in str(raw or "").split(";"):
        if "=" in par:
            chave, _, valor = par.partition("=")
            if chave.strip():
                out[chave.strip()] = valor.strip()
    return out


def format_mapping(mapa: dict[str, str]) -> str:
    return ";".join(f"{k}={v}" for k, v in sorted(mapa.items()) if k)


def account_key(account: dict) -> str:
    """Chave estável de uma conta da Pluggy.

    O `id` da conta é o que não muda de nome; o rótulo bonito serve só
    para a tela. Reconectar um banco cria contas novas, então o mapa
    pode precisar de ajuste — melhor isso do que casar por nome e
    importar para o cartão errado em silêncio.
    """
    return str(account.get("id") or "").strip()


def account_label(account: dict) -> str:
    nome = str(account.get("name") or "conta").strip()
    numero = str(account.get("number") or "").strip()
    return f"{nome} · {numero}" if numero else nome


def _valor_e_tipo(tx: dict, *, cartao: bool) -> tuple[float, str]:
    """Valor absoluto e se é entrada ou saída.

    O campo `type` é usado antes do sinal porque é o que a Pluggy
    documenta; o sinal entra só como desempate quando `type` vem vazio.
    Em cartão, "DEBIT" é compra — o que para o dono do cartão é despesa.
    """
    bruto = pd.to_numeric(tx.get("amount"), errors="coerce")
    valor = 0.0 if pd.isna(bruto) else float(bruto)
    tipo_api = str(tx.get("type") or "").strip().upper()

    if tipo_api == "CREDIT":
        entrada = True
    elif tipo_api == "DEBIT":
        entrada = False
    else:
        entrada = valor > 0

    if cartao:
        # Numa fatura, o que volta como crédito é estorno/pagamento; o
        # app não modela isso como receita, então só a compra entra.
        return abs(valor), "Entrada" if entrada else "Saída"
    return abs(valor), "Entrada" if entrada else "Saída"


def _data(tx: dict) -> date | None:
    serie = parse_dates(pd.Series([tx.get("date")]))
    valor = serie.iloc[0]
    return None if pd.isna(valor) else valor.date()


def build_pending(*, accounts: list[tuple[dict, str]],
                  transactions: dict[str, list[dict]],
                  ja_importados: set[str],
                  df_cards: pd.DataFrame,
                  desde: date | None = None,
                  bills: dict[str, list[dict]] | None = None,
                  sugerir=None) -> tuple[list[Pendente], list[str]]:
    """Monta as pendências a partir do que a API devolveu.

    `accounts` é uma lista de (conta da Pluggy, destino escolhido).
    `transactions` mapeia id da conta -> lançamentos.
    Devolve (pendências, avisos).
    """
    pendentes: list[Pendente] = []
    avisos: list[str] = []
    vistos: set[str] = set()
    creditos = 0
    antigos = 0
    deduzidas = 0

    for conta, destino in accounts:
        if destino in ("", DESTINO_IGNORAR):
            continue
        chave = account_key(conta)
        rotulo = account_label(conta)
        e_cartao = destino != DESTINO_BANCO

        fechamento = vencimento = None
        faturas: dict[str, str] = {}
        if e_cartao:
            settings = cc.card_settings(df_cards, destino)
            fechamento = int(settings["fechamento"])
            vencimento = int(settings["vencimento"])
            faturas = bill_index((bills or {}).get(chave, []),
                                 closing_day=fechamento, due_day=vencimento)

        for tx in transactions.get(chave, []):
            pid = str(tx.get("id") or "").strip()
            if not pid:
                avisos.append(f"{rotulo}: um lançamento veio sem id e foi "
                              "ignorado (não teria como evitar duplicar).")
                continue
            if pid in ja_importados or pid in vistos:
                continue
            quando = _data(tx)
            if quando is not None and desde is not None and quando < desde:
                antigos += 1
                continue
            if quando is None:
                avisos.append(f"{rotulo}: lançamento {pid} veio sem data "
                              "legível e ficou de fora.")
                continue
            valor, tipo = _valor_e_tipo(tx, cartao=e_cartao)
            if valor <= 0:
                continue


            # Crédito numa fatura — "Pagamento recebido", "Pagamento
            # antecipado", estorno — abate o que se deve, e é assim que
            # o banco monta o total: gasto do mês menos os créditos.
            # Entra com valor negativo para a soma reproduzir a fatura;
            # descartá-lo deixava o app acima do banco pelo valor de
            # cada pagamento feito antes do fechamento.
            if e_cartao and tipo == "Entrada":
                valor = -valor
                creditos += 1

            descricao = str(tx.get("description") or "").strip() or "(sem descrição)"
            mes = ""
            if e_cartao:
                # A fatura informada pelo banco tem prioridade sobre
                # qualquer regra nossa: ela é a resposta, não uma
                # estimativa. A dedução pelo dia de fechamento só entra
                # quando a instituição não diz a qual fatura a compra
                # pertence.
                mes = faturas.get(bill_id(tx), "")
                if not mes:
                    deduzidas += 1
                    mes = cc.invoice_month_for_purchase(
                        quando, fechamento).strftime("%m/%Y")

            cat_pluggy = str(tx.get("category") or "").strip()
            # A transferência tem prioridade sobre o histórico: acertar
            # que é quitação de fatura importa mais do que repetir a
            # categoria que o usuário deu a um gasto parecido.
            categoria = (transfer_category(descricao, cat_pluggy)
                         or (sugerir(descricao) if sugerir else None)
                         or "Outros")

            vistos.add(pid)
            pendentes.append(Pendente(
                pluggy_id=pid, data=quando, descricao=descricao,
                valor=valor, tipo=tipo, destino=destino, conta=rotulo,
                categoria=categoria, mes_fatura=mes,
                parcela=installment_label(tx) if e_cartao else "1/1",
                categoria_pluggy=cat_pluggy,
            ))

    if deduzidas:
        avisos.append(
            f"{deduzidas} compra(s) de cartão não vieram com a fatura "
            "informada pelo banco; para essas, o mês foi deduzido pelo "
            "dia de fechamento cadastrado."
        )
    if antigos:
        avisos.append(
            f"{antigos} lançamento(s) anteriores a "
            f"{desde:%d/%m/%Y} ficaram de fora."
        )
    if creditos:
        avisos.append(
            f"{creditos} crédito(s) em fatura (pagamento antecipado, "
            "estorno) entraram com valor negativo — é assim que eles "
            "abatem a fatura, como no extrato do banco."
        )

    pendentes.sort(key=lambda p: (p.data, p.descricao))

    pares = match_transfers(pendentes)
    if pares:
        avisos.append(
            f"{pares} par(es) de transferência entre suas contas foram "
            "marcados como **Transferência** — dinheiro mudando de lugar "
            "não conta como receita nem como despesa."
        )
    return pendentes, avisos


def match_transfers(pendentes: list[Pendente], *,
                    janela_dias: int = 3) -> int:
    """Marca como transferência o dinheiro que anda entre contas suas.

    Uma saída de uma conta conectada que reaparece como entrada de mesmo
    valor em OUTRA conta conectada, poucos dias depois, é a mesma nota
    mudando de lugar — não é receita nem despesa. Casar por valor, por
    direção oposta e por conta diferente é forte o bastante porque as
    duas pontas vêm do mesmo extrato; a janela de dias existe porque TED
    e Pix agendado não caem no mesmo instante.

    Altera os pendentes no lugar e devolve quantos pares achou. Um falso
    positivo custa um clique na triagem; um falso negativo infla a
    receita do mês em silêncio.
    """
    saidas = [p for p in pendentes
              if not p.is_cartao and p.tipo == "Saída"]
    entradas = [p for p in pendentes
                if not p.is_cartao and p.tipo == "Entrada"]
    if not saidas or not entradas:
        return 0

    usadas: set[int] = set()
    pares = 0
    for saida in saidas:
        melhor, distancia = None, None
        for i, entrada in enumerate(entradas):
            if i in usadas or entrada.conta == saida.conta:
                continue
            if round(entrada.valor, 2) != round(saida.valor, 2):
                continue
            dias = abs((entrada.data - saida.data).days)
            if dias > janela_dias:
                continue
            if distancia is None or dias < distancia:
                melhor, distancia = i, dias
        if melhor is None:
            continue
        usadas.add(melhor)
        saida.categoria = CATEGORIA_TRANSFERENCIA
        entradas[melhor].categoria = CATEGORIA_TRANSFERENCIA
        pares += 1
    return pares


def to_rows(pendentes: list[Pendente]) -> tuple[list[dict], list[dict], list[dict]]:
    """Traduz as pendências aceitas em linhas das três abas.

    Devolve (linhas de `financeiro`, linhas de `cartao`, linhas de
    `importacoes`). A terceira é o que impede a próxima sincronização de
    trazer tudo de novo, e por isso é gravada junto, nunca depois.
    """
    banco, cartao, registro = [], [], []
    hoje = date.today().isoformat()

    for p in pendentes:
        if p.is_cartao:
            cartao.append({
                "Data Compra": p.data.isoformat(),
                "Mês da Fatura": p.mes_fatura,
                "Cartão": p.destino,
                "Descrição": p.descricao,
                "Categoria": p.categoria,
                "Parcela": p.parcela,
                "Valor": p.valor,
                "Status": "Pendente",
            })
        else:
            banco.append({
                "Data": p.data.isoformat(),
                "Descrição": p.descricao,
                "Categoria": p.categoria,
                "Valor": p.valor,
                "Tipo": p.tipo,
            })
        registro.append({
            "ID Pluggy": p.pluggy_id,
            "Data": p.data.isoformat(),
            "Descrição": p.descricao,
            "Valor": p.valor,
            "Destino": p.destino,
            "Importado em": hoje,
        })
    return banco, cartao, registro
