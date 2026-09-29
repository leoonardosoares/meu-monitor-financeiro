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

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src import credit_card as cc
from src.dates import parse_dates

# Onde cada conta da Pluggy pode desaguar.
DESTINO_IGNORAR = "Ignorar"
DESTINO_BANCO = "Entradas e Saídas"


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
                  sugerir=None) -> tuple[list[Pendente], list[str]]:
    """Monta as pendências a partir do que a API devolveu.

    `accounts` é uma lista de (conta da Pluggy, destino escolhido).
    `transactions` mapeia id da conta -> lançamentos.
    Devolve (pendências, avisos).
    """
    pendentes: list[Pendente] = []
    avisos: list[str] = []
    vistos: set[str] = set()

    for conta, destino in accounts:
        if destino in ("", DESTINO_IGNORAR):
            continue
        chave = account_key(conta)
        rotulo = account_label(conta)
        e_cartao = destino != DESTINO_BANCO

        fechamento = None
        if e_cartao:
            fechamento = int(cc.card_settings(df_cards, destino)["fechamento"])

        for tx in transactions.get(chave, []):
            pid = str(tx.get("id") or "").strip()
            if not pid:
                avisos.append(f"{rotulo}: um lançamento veio sem id e foi "
                              "ignorado (não teria como evitar duplicar).")
                continue
            if pid in ja_importados or pid in vistos:
                continue
            quando = _data(tx)
            if quando is None:
                avisos.append(f"{rotulo}: lançamento {pid} veio sem data "
                              "legível e ficou de fora.")
                continue
            valor, tipo = _valor_e_tipo(tx, cartao=e_cartao)
            if valor <= 0:
                continue

            descricao = str(tx.get("description") or "").strip() or "(sem descrição)"
            mes = ""
            if e_cartao:
                mes = cc.invoice_month_for_purchase(
                    quando, fechamento).strftime("%m/%Y")

            vistos.add(pid)
            pendentes.append(Pendente(
                pluggy_id=pid, data=quando, descricao=descricao,
                valor=valor, tipo=tipo, destino=destino, conta=rotulo,
                categoria=(sugerir(descricao) if sugerir else None) or "Outros",
                mes_fatura=mes,
                categoria_pluggy=str(tx.get("category") or "").strip(),
            ))

    pendentes.sort(key=lambda p: (p.data, p.descricao))
    return pendentes, avisos


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
                "Parcela": "1/1",
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
