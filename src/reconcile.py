"""Conciliação: fazer a planilha bater com o banco.

Duas ferramentas, para dois problemas diferentes — e usar a errada
esconde o defeito em vez de corrigi-lo.

**Duplicata** é linha repetida: a mesma compra lançada à mão e trazida
de novo pela importação. O conserto é apagar a cópia. Um lançamento de
ajuste aqui só mascararia o total, e a fatura continuaria mostrando a
compra duas vezes.

**Diferença residual** é o que sobra quando não há repetição: período
que nunca foi lançado, gasto em dinheiro, aporte antigo. Isso não tem
linha para apagar, e é aí que o ajuste é a resposta certa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.config import CATEGORIA_AJUSTE, CATEGORIA_INVESTIMENTO

# Uma compra é a mesma compra quando coincide em tudo que a descreve.
# Data e parcela entram na chave para não fundir a parcela 2/6 com a
# 3/6, que têm o mesmo valor e a mesma descrição de propósito.
CHAVES_CARTAO = ["Cartão", "Mês da Fatura", "Descrição", "Parcela",
                 "Valor", "Data Compra"]
CHAVES_BANCO = ["Data", "Descrição", "Categoria", "Valor", "Tipo"]


def _chaves_validas(df: pd.DataFrame, chaves: list[str]) -> list[str]:
    return [c for c in chaves if c in df.columns]


def duplicates(df: pd.DataFrame, chaves: list[str]) -> pd.Index:
    """Índices das linhas repetidas, preservando a primeira de cada grupo.

    `keep="first"` é deliberado: sobra exatamente uma de cada compra,
    nunca zero. Um deduplicador que apaga o grupo inteiro transforma um
    excesso em falta, que é pior — o excesso se vê no total, a falta não.
    """
    if df.empty:
        return pd.Index([])
    usadas = _chaves_validas(df, chaves)
    if not usadas:
        return pd.Index([])
    normalizado = df[usadas].astype(str).apply(lambda s: s.str.strip())
    return df.index[normalizado.duplicated(keep="first")]


def duplicate_preview(df: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """O que seria apagado, agrupado, para conferir antes de apagar."""
    idx = duplicates(df, chaves)
    if len(idx) == 0:
        return pd.DataFrame()
    usadas = _chaves_validas(df, chaves)
    recorte = df.loc[idx, usadas].copy()
    contagem = recorte.groupby(usadas, dropna=False).size()
    fora = contagem.reset_index()
    fora.columns = [*usadas, "Cópias a remover"]
    return fora.sort_values("Cópias a remover", ascending=False)


@dataclass(frozen=True)
class Ajuste:
    """Um lançamento de conciliação, pronto para virar linha."""
    descricao: str
    categoria: str
    valor: float
    tipo: str          # "Entrada" ou "Saída"
    data: date
    motivo: str = ""

    def to_row(self) -> dict:
        return {
            "Data": self.data.isoformat(),
            "Descrição": self.descricao,
            "Categoria": self.categoria,
            "Valor": round(abs(self.valor), 2),
            "Tipo": self.tipo,
        }


def _ajuste(descricao: str, categoria: str, delta: float, quando: date,
            motivo: str) -> Ajuste | None:
    if abs(delta) < 0.01:
        return None
    return Ajuste(descricao=descricao, categoria=categoria,
                  valor=abs(delta),
                  tipo="Entrada" if delta > 0 else "Saída",
                  data=quando, motivo=motivo)


def adjustments(*, saldo_real: float, saldo_planilha: float,
                investido_real: float, investido_planilha: float,
                quando: date) -> list[Ajuste]:
    """Lançamentos que fazem a planilha reproduzir o banco.

    A ordem importa. O ajuste de investimento é uma Saída na conta —
    ele mexe no saldo derivado. Calcular o ajuste de saldo antes dele
    deixaria a conta errada pelo valor do primeiro, e seria preciso um
    terceiro ajuste para corrigir o segundo.
    """
    out: list[Ajuste] = []

    delta_inv = investido_real - investido_planilha
    ajuste_inv = _ajuste(
        "Conciliação de investimentos", CATEGORIA_INVESTIMENTO,
        # Aporte que faltou lançar sai da conta: Saída na categoria
        # Investimento é como o app registra dinheiro indo para a
        # carteira, então o sinal é invertido em relação ao delta.
        -delta_inv, quando,
        "posição nas instituições menos o que os lançamentos somam",
    )
    if ajuste_inv:
        out.append(ajuste_inv)

    # O ajuste acima já mexeu no saldo derivado; o de conta parte de lá.
    derivado = saldo_planilha - delta_inv
    ajuste_conta = _ajuste(
        "Conciliação de saldo", CATEGORIA_AJUSTE,
        saldo_real - derivado, quando,
        "saldo do banco menos o que a planilha soma",
    )
    if ajuste_conta:
        out.append(ajuste_conta)

    return out
