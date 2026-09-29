"""Recomeço do zero.

    python tests/run_reset.py

É a única operação do app que apaga dados do usuário. O que se verifica
aqui é que a contagem mostrada antes corresponde ao que some, que a
cópia leva a data, e que o corte cai no dia 1 — começar no meio do mês
deixaria o orçamento do período pela metade.
"""
from __future__ import annotations

import os
import sys
import types

if "streamlit" not in sys.modules:
    _st = types.ModuleType("streamlit")
    _st.cache_data = _st.cache_resource = lambda *a, **k: (lambda f: f)
    _st.secrets = {}
    sys.modules["streamlit"] = _st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date  # noqa: E402

import pandas as pd  # noqa: E402

from src import reset  # noqa: E402
from src.config import SHEETS_SCHEMA  # noqa: E402

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


DFS = {
    "financeiro": pd.DataFrame({"Valor": [1, 2, 3]}),
    "cartao": pd.DataFrame({"Valor": [1, 2]}),
    "cartao_pagamentos": pd.DataFrame(),
    "importacoes": pd.DataFrame({"ID Pluggy": ["a"]}),
}

print("  A contagem mostrada é a que vai sumir")
plano = reset.plan(DFS)
check("por aba", plano.contagem,
      {"financeiro": 3, "cartao": 2, "cartao_pagamentos": 0,
       "importacoes": 1})
check("total", plano.total, 6)
check("vazio conta zero", reset.plan({"x": pd.DataFrame()}).total, 0)

print("  O registro de importação some junto")
# Mantê-lo faria o Open Finance pular justamente o mês que se quer
# reconstruir, e o recomeço acabaria com a planilha vazia.
check("está na lista de limpeza", "importacoes" in reset.ARQUIVOS, True)
check("sem cópia (não faz sentido guardar)",
      reset.ARQUIVOS["importacoes"], None)

print("  O que tem valor é copiado antes")
check("lançamentos", reset.ARQUIVOS["financeiro"], "arquivo_financeiro")
check("compras", reset.ARQUIVOS["cartao"], "arquivo_cartao")
for destino in ("arquivo_financeiro", "arquivo_cartao"):
    check(f"{destino} existe no esquema", destino in SHEETS_SCHEMA, True)
    check(f"{destino} tem a coluna da data",
          "Arquivado em" in SHEETS_SCHEMA[destino], True)

print("  A cópia leva a data e preserva o conteúdo")
origem = pd.DataFrame({"Descrição": ["Mercado"], "Valor": [10.0]})
copia = reset.stamp(origem, quando=date(2026, 9, 30))
check("data marcada", copia["Arquivado em"].iloc[0], "2026-09-30")
check("colunas originais mantidas",
      [c for c in copia.columns if c != "Arquivado em"], ["Descrição", "Valor"])
check("o original não é alterado", "Arquivado em" in origem.columns, False)

print("  O corte cai no dia 1 do mês")
check("meio do mês", reset.cutoff(date(2026, 9, 29)), date(2026, 9, 1))
check("primeiro dia", reset.cutoff(date(2026, 9, 1)), date(2026, 9, 1))
check("último dia", reset.cutoff(date(2026, 12, 31)), date(2026, 12, 1))
check("fevereiro", reset.cutoff(date(2028, 2, 29)), date(2028, 2, 1))

print("  Cadastros que não podem sumir ficam fora da limpeza")
for preservar in ("cartoes", "categorias", "orcamentos", "custos_fixos",
                  "investimentos", "investimento_movimentacoes",
                  "configuracoes"):
    check(f"{preservar} preservada", preservar in reset.ARQUIVOS, False)

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
