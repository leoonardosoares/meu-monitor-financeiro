"""Recomeçar do zero, mantendo uma cópia do que foi apagado.

Enquanto a planilha misturar lançamentos digitados à mão com importados,
o saldo derivado nunca vai igualar o do banco: o que foi digitado não
tem identificador para o app reconhecer, e o que foi importado começa
numa data escolhida. Zerar e deixar o Open Finance preencher desde o
início do mês resolve isso de uma vez.

O que se apaga é copiado antes. O usuário pediu para perder o histórico,
mas arquivar não custa nada e apagar não tem volta — se ele quiser
mesmo sumir com a cópia, basta excluir a aba na planilha.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

# aba de origem -> aba de arquivo (None = some sem cópia)
ARQUIVOS = {
    "financeiro": "arquivo_financeiro",
    "cartao": "arquivo_cartao",
    "cartao_pagamentos": None,
    # Precisa ir junto: ela guarda os ids já importados, e mantê-la
    # impediria o Open Finance de trazer de volta o mês que se quer
    # reconstruir.
    "importacoes": None,
}


@dataclass(frozen=True)
class Plano:
    """O que será apagado, contado antes de qualquer gravação."""
    contagem: dict[str, int]
    arquivar: dict[str, str]

    @property
    def total(self) -> int:
        return sum(self.contagem.values())


def plan(dfs: dict[str, pd.DataFrame]) -> Plano:
    """Quantas linhas cada aba perde, para a tela avisar antes."""
    return Plano(
        contagem={nome: 0 if df is None or df.empty else len(df)
                  for nome, df in dfs.items()},
        arquivar={k: v for k, v in ARQUIVOS.items() if v},
    )


def stamp(df: pd.DataFrame, *, quando: date) -> pd.DataFrame:
    """Marca a cópia com a data do arquivamento."""
    copia = df.copy()
    copia["Arquivado em"] = quando.isoformat()
    return copia


def cutoff(hoje: date) -> date:
    """Primeiro dia do mês corrente.

    É a data a partir da qual o Open Finance reconstrói. Começar no dia
    1 mantém o mês inteiro coerente; começar hoje deixaria um pedaço do
    mês sem nada e o orçamento do período sairia errado.
    """
    return hoje.replace(day=1)
