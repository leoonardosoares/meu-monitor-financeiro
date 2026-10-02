"""Livro de faturas: cada regra contra o caso real que a quebrou.

    python tests/run_book.py

Os cenários são os do dono do app: Nubank ("Principal") fechando dia 8 e
vencendo dia 15, publicando faturas; Itaú fechando dia 30 e vencendo dia 7
do mês seguinte, sem publicar faturas.
"""
from __future__ import annotations

import os
import sys
import types
from datetime import date

import pandas as pd

_st = types.ModuleType("streamlit")
_st.cache_data = _st.cache_resource = lambda *a, **k: (lambda f: f)
_st.secrets = {}
sys.modules["streamlit"] = _st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import card_book as cb  # noqa: E402
from src.config import ORIGEM_BANCO, ORIGEM_PROJECAO  # noqa: E402
from src.positions import Conta  # noqa: E402

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


HOJE = date(2026, 10, 2)

CARTOES = pd.DataFrame([
    {"Nome": "Principal", "Instituição": "Nubank", "Limite": 5150.0,
     "Dia Fechamento": 8, "Dia Vencimento": 15},
    {"Nome": "Cartão Itaú", "Instituição": "Itaú", "Limite": 1600.0,
     "Dia Fechamento": 30, "Dia Vencimento": 7},
])


def compra(cartao, mes, desc, valor, parcela="1/1", ident="x", origem=None,
           data="2026-09-10"):
    return {"Data Compra": data, "Mês da Fatura": mes, "Cartão": cartao,
            "Descrição": desc, "Categoria": "Outros", "Parcela": parcela,
            "Valor": valor, "Status": "Pendente", "ID Pluggy": ident,
            "Origem": origem or ORIGEM_BANCO}


def fatura_banco(mes, total, fecha, vence):
    return {"Cartão": "Principal", "Mês": mes, "Total": total,
            "Fechamento": fecha, "Vencimento": vence, "Situação": "CLOSED",
            "Lido em": "2026-10-02"}


BILLS = pd.DataFrame([
    fatura_banco("06/2026", 2678.77, "2026-06-08", "2026-06-15"),
    fatura_banco("07/2026", 3371.12, "2026-07-08", "2026-07-15"),
    fatura_banco("09/2026", 2281.47, "2026-09-08", "2026-09-15"),
])

COMPRAS = pd.DataFrame([
    # Fatura de setembro (emitida pelo banco): duas compras só, de 2.281,47.
    compra("Principal", "09/2026", "Mercado", 1500.00, ident="a1"),
    compra("Principal", "09/2026", "KaBuM 2/3", 100.00, "2/3", "a2"),
    # Fatura aberta de outubro.
    compra("Principal", "10/2026", "Farmácia", 89.90, ident="a3"),
    compra("Principal", "10/2026", "Restaurante", 210.10, ident="a4"),
    # Itaú: agosto (venceu 07/09), setembro (vence 07/10), outubro (aberta).
    compra("Cartão Itaú", "08/2026", "Posto", 266.70, ident="i1"),
    compra("Cartão Itaú", "09/2026", "Padaria", 50.00, ident="i2"),
    compra("Cartão Itaú", "10/2026", "Cinema", 80.00, ident="i3"),
    # Lixo de versão antiga: uma parcela projetada GRAVADA.
    compra("Principal", "10/2026", "KaBuM", 100.00, "3/3", "",
           ORIGEM_PROJECAO),
])

CONTA_NU = Conta(nome="Nubank", tipo="CREDIT", saldo=-5083.68,
                 instituicao="Nubank", chave="nu", limite=5150.0,
                 disponivel=4750.0, fecha="2026-10-08", vence="2026-10-15")

livros = cb.build(compras=COMPRAS, df_bills=BILLS, df_cards=CARTOES,
                  contas={"Principal": CONTA_NU}, today=HOJE)
nu = next(c for c in livros if c.nome == "Principal")
itau = next(c for c in livros if c.nome == "Cartão Itaú")

print("Fatura vencida é fatura paga")
# O dono viu três "vencidas" que o banco não cobra. O app não vê o
# pagamento; quem acusa dívida de verdade é o limite usado do banco.
check("junho, julho e setembro do Nubank estão pagas",
      sorted(f.mes for f in nu.pagas), ["06/2026", "07/2026", "09/2026"])
check("nenhuma fatura do Nubank a pagar", nu.a_pagar, [])
check("agosto do Itaú venceu dia 07/09: paga",
      [f.mes for f in itau.pagas], ["08/2026"])

print("A fatura aberta é a do banco, com as datas do banco")
check("a aberta do Nubank é outubro", nu.atual.mes, "10/2026")
check("fecha quando o banco diz", nu.atual.fechamento, date(2026, 10, 8))
check("datas vieram do banco", nu.atual.datas_do_banco, True)
check("sem fatura emitida, o total é a soma das compras + a 3/3 deduzida",
      nu.atual.total, round(89.90 + 210.10 + 100.00, 2))
check("a fonte declarada é compras", nu.atual.fonte, cb.FONTE_COMPRAS)

print("Parcela futura é derivada, nunca a gravada")
# A projeção gravada por versão antiga não pode somar junto com a
# recalculada: seriam duas KaBuM 3/3.
kabum = [p for p in nu.atual.projetadas if p["Parcela"] == "3/3"]
check("uma única KaBuM 3/3", len(kabum), 1)
check("a gravada ficou de fora das compras",
      (nu.atual.compras["Origem"] == ORIGEM_PROJECAO).sum(), 0)

print("O total do banco manda; as compras explicam")
setembro = next(f for f in nu.faturas if f.mes == "09/2026")
check("setembro tem o total do banco", setembro.total, 2281.47)
check("e a fonte é o banco", setembro.fonte, cb.FONTE_BANCO)
check("o que não chegou aparece como diferença",
      setembro.nao_chegaram, round(2281.47 - 1600.00, 2))

print("Cartão sem faturas publicadas usa as compras e o cadastro")
check("Itaú não publica", itau.publica_faturas, False)
check("setembro do Itaú fecha 30/09 e vence 07/10: a pagar",
      [f.mes for f in itau.a_pagar], ["09/2026"])
check("outubro do Itaú é a aberta", itau.atual.mes, "10/2026")
check("a próxima a vencer do Itaú é setembro",
      itau.proxima_a_vencer.mes, "09/2026")

print("Limite e disponível vêm do banco quando ele informa")
check("limite do banco", nu.limite, 5150.0)
check("disponível do banco", nu.disponivel, 4750.0)
check("limite usado = limite − disponível", nu.usado_banco, 400.0)
check("os limites estão marcados como do banco", nu.limites_do_banco, True)
check("compromisso = aberta (não há a pagar nem futuras)",
      nu.compromisso, 400.0)
check("o livro fecha com o banco", nu.diferenca_banco, 0.0)
check("Itaú sem conta: disponível = limite − compromisso",
      itau.disponivel, round(1600.0 - 50.0 - 80.0, 2))
check("e sem conferência possível", itau.diferenca_banco, None)

print("A diferença com o banco acusa compra que falta")
# Banco diz 1.000 usados; o app só explica 400.
CONTA_FALTA = Conta(nome="Nubank", tipo="CREDIT", saldo=-1000,
                    instituicao="Nubank", chave="nu", limite=5150.0,
                    disponivel=4150.0, fecha="2026-10-08",
                    vence="2026-10-15")
nu2 = cb.build_card(card="Principal", compras=COMPRAS, df_bills=BILLS,
                    df_cards=CARTOES, conta=CONTA_FALTA, today=HOJE)
check("faltam 600", nu2.diferenca_banco, 600.0)

print("Parcelas futuras somam no compromisso e no mês certo")
longa = pd.DataFrame([
    compra("Principal", "10/2026", "Mercadolivre 2/10", 235.31, "2/10", "m2"),
])
nu3 = cb.build_card(card="Principal", compras=longa, df_bills=BILLS,
                    df_cards=CARTOES, conta=CONTA_NU, today=HOJE)
check("oito futuras, de 11/2026 a 06/2027",
      [f.mes for f in nu3.futuras][:1] + [f.mes for f in nu3.futuras][-1:],
      ["11/2026", "06/2027"])
check("cada futura com uma parcela", {len(f.projetadas) for f in nu3.futuras},
      {1})
check("compromisso = 9 × 235,31", nu3.compromisso, round(9 * 235.31, 2))

print("Faturas que vencem até uma data")
ate = cb.due_through(livros, date(2026, 10, 31))
check("outubro: Itaú setembro, Nubank outubro, Itaú outubro? (vence 07/11 não)",
      [(f.cartao, f.mes) for f in ate],
      [("Cartão Itaú", "09/2026"), ("Principal", "10/2026")])

print("Mês ilegível não some calado")
torto = pd.DataFrame([compra("Principal", "set/26", "Algo", 10.0)])
nu4 = cb.build_card(card="Principal", compras=torto, df_bills=pd.DataFrame(),
                    df_cards=CARTOES, conta=None, today=HOJE)
check("vira aviso", nu4.ilegiveis, ("set/26",))

print("Fechamento do banco em mês diferente do rótulo não cria fatura fantasma")
# Itaú cadastrado para fechar dia 30; o banco diz que este ciclo fecha
# 01/11 (30/10 caiu num sábado). As compras estão rotuladas 10/2026.
CONTA_ITAU = Conta(nome="Itaú", tipo="CREDIT", saldo=-130, instituicao="Itaú",
                   chave="it", limite=1600.0, disponivel=1470.0,
                   fecha="2026-11-01", vence="2026-11-09")
it2 = cb.build_card(card="Cartão Itaú", compras=COMPRAS, df_bills=pd.DataFrame(),
                    df_cards=CARTOES, conta=CONTA_ITAU, today=HOJE)
check("nenhuma futura vazia", [f.mes for f in it2.futuras
                               if f.total == 0 and f.compras.empty], [])
check("a aberta é a que tem as compras", it2.atual.mes, "10/2026")

print("Planilha vazia")
vazio = cb.build(compras=pd.DataFrame(), df_bills=pd.DataFrame(),
                 df_cards=CARTOES, contas={}, today=HOJE)
check("os cartões cadastrados aparecem, sem faturas",
      [(c.nome, len(c.faturas)) for c in vazio],
      [("Principal", 0), ("Cartão Itaú", 0)])

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
