"""Tradução do que a Pluggy devolve para as linhas da planilha.

    python tests/run_import.py

Nem a API nem a planilha podem ser exercitadas de verdade aqui, então é
esta camada que precisa estar coberta: é ela que decide se um lançamento
vira despesa ou receita, em que fatura cai, e se entra duas vezes.
"""
from __future__ import annotations

import os
import sys
import types

if "streamlit" not in sys.modules:
    _st = types.ModuleType("streamlit")
    _st.cache_data = lambda *a, **k: (lambda f: f)
    _st.cache_resource = lambda *a, **k: (lambda f: f)
    _st.secrets = {}
    sys.modules["streamlit"] = _st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from src import pluggy_import as pi  # noqa: E402
from tests.fixture import CARDS  # noqa: E402

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


CONTA_BANCO = {"id": "acc-banco", "name": "Nu Pagamentos S.A.",
               "number": "61296355-2", "type": "BANK"}
CONTA_CARTAO = {"id": "acc-cartao", "name": "platinum", "number": "9366",
                "type": "CREDIT"}


def tx(id_, data, desc, amount, tipo=None, cat=""):
    t = {"id": id_, "date": data, "description": desc, "amount": amount}
    if tipo:
        t["type"] = tipo
    if cat:
        t["category"] = cat
    return t


def montar(contas, transacoes, ja=None, sugerir=None):
    return pi.build_pending(
        accounts=contas, transactions=transacoes,
        ja_importados=ja or set(), df_cards=CARDS, sugerir=sugerir)


print("  Entrada e saída vêm do campo `type`, não do sinal")
p, avisos = montar(
    [(CONTA_BANCO, pi.DESTINO_BANCO)],
    {"acc-banco": [
        tx("t1", "2026-09-10", "Salário", 5000.0, "CREDIT"),
        tx("t2", "2026-09-11", "Mercado", -300.0, "DEBIT"),
        tx("t3", "2026-09-12", "Uber", -25.0),          # sem type: usa o sinal
        tx("t4", "2026-09-13", "Estorno", 40.0),        # sem type: usa o sinal
    ]})
check("quatro pendências", len(p), 4)
check("sem avisos", avisos, [])
check("valores sempre positivos", [x.valor for x in p],
      [5000.0, 300.0, 25.0, 40.0])
check("tipos", [x.tipo for x in p],
      ["Entrada", "Saída", "Saída", "Entrada"])

print("  Compra de cartão cai na fatura pelo dia de fechamento do cartão")
p, _ = montar(
    [(CONTA_CARTAO, "Principal")],           # Principal fecha dia 8
    {"acc-cartao": [
        tx("c1", "2026-09-08", "Padaria", -20.0, "DEBIT"),
        tx("c2", "2026-09-09", "Bar", -50.0, "DEBIT"),
    ]})
check("dia do fechamento fica no mês", p[0].mes_fatura, "09/2026")
check("o dia seguinte já é a próxima", p[1].mes_fatura, "10/2026")
check("vai para o cartão certo", {x.destino for x in p}, {"Principal"})
check("é reconhecido como cartão", [x.is_cartao for x in p], [True, True])

print("  O que já foi importado não volta")
ja = {"t1", "t2"}
p, _ = montar(
    [(CONTA_BANCO, pi.DESTINO_BANCO)],
    {"acc-banco": [
        tx("t1", "2026-09-10", "Salário", 5000.0, "CREDIT"),
        tx("t2", "2026-09-11", "Mercado", -300.0, "DEBIT"),
        tx("t9", "2026-09-12", "Novo", -10.0, "DEBIT"),
    ]}, ja=ja)
check("só o novo", [x.pluggy_id for x in p], ["t9"])

print("  Nem duplicata dentro da mesma leva")
p, _ = montar(
    [(CONTA_BANCO, pi.DESTINO_BANCO)],
    {"acc-banco": [tx("dup", "2026-09-10", "X", -10.0, "DEBIT"),
                   tx("dup", "2026-09-10", "X", -10.0, "DEBIT")]})
check("uma só", len(p), 1)

print("  Conta marcada para ignorar não entra")
p, _ = montar(
    [(CONTA_BANCO, pi.DESTINO_IGNORAR), (CONTA_CARTAO, "")],
    {"acc-banco": [tx("t1", "2026-09-10", "X", -10.0, "DEBIT")],
     "acc-cartao": [tx("c1", "2026-09-10", "Y", -10.0, "DEBIT")]})
check("nada", p, [])

print("  Lançamento sem id ou sem data é reportado, não engolido")
p, avisos = montar(
    [(CONTA_BANCO, pi.DESTINO_BANCO)],
    {"acc-banco": [
        tx("", "2026-09-10", "Sem id", -10.0, "DEBIT"),
        tx("t5", "data-invalida", "Sem data", -10.0, "DEBIT"),
        tx("t6", "2026-09-10", "Boa", -10.0, "DEBIT"),
    ]})
check("só a boa entra", [x.pluggy_id for x in p], ["t6"])
check("dois avisos", len(avisos), 2)
check("o aviso explica o risco", "duplicar" in avisos[0], True)

print("  Valor ilegível ou zero não vira linha")
p, _ = montar(
    [(CONTA_BANCO, pi.DESTINO_BANCO)],
    {"acc-banco": [tx("z1", "2026-09-10", "Zero", 0.0, "DEBIT"),
                   tx("z2", "2026-09-10", "Nulo", None, "DEBIT"),
                   tx("z3", "2026-09-10", "Texto", "abc", "DEBIT")]})
check("nenhuma", p, [])

print("  Descrição vazia não some")
p, _ = montar([(CONTA_BANCO, pi.DESTINO_BANCO)],
              {"acc-banco": [tx("d1", "2026-09-10", "  ", -10.0, "DEBIT")]})
check("marcada", p[0].descricao, "(sem descrição)")

print("  A sugestão de categoria é aplicada, com Outros como reserva")
p, _ = montar([(CONTA_BANCO, pi.DESTINO_BANCO)],
              {"acc-banco": [tx("s1", "2026-09-10", "Mercado", -10.0, "DEBIT"),
                             tx("s2", "2026-09-10", "Zzz", -10.0, "DEBIT")]},
              sugerir=lambda d: "Supermercado" if "Mercado" in d else None)
check("sugeriu", p[0].categoria, "Supermercado")
check("caiu para Outros", p[1].categoria, "Outros")

print("  Tradução para as linhas das três abas")
p, _ = montar(
    [(CONTA_BANCO, pi.DESTINO_BANCO), (CONTA_CARTAO, "Principal")],
    {"acc-banco": [tx("b1", "2026-09-10", "Salário", 5000.0, "CREDIT")],
     "acc-cartao": [tx("c1", "2026-09-05", "Padaria", -20.0, "DEBIT")]})
banco, cartao, registro = pi.to_rows(p)
check("uma linha de banco", len(banco), 1)
check("uma de cartão", len(cartao), 1)
check("e duas no registro de importação", len(registro), 2)
check("colunas do banco", sorted(banco[0]),
      ["Categoria", "Data", "Descrição", "Tipo", "Valor"])
check("colunas do cartão", sorted(cartao[0]),
      ["Cartão", "Categoria", "Data Compra", "Descrição", "Mês da Fatura",
       "Parcela", "Status", "Valor"])
check("o registro guarda o id", sorted(x["ID Pluggy"] for x in registro),
      ["b1", "c1"])
check("cartão entra como pendente", cartao[0]["Status"], "Pendente")
check("e como parcela única", cartao[0]["Parcela"], "1/1")

print("  Mapa de contas vai e volta sem perder nada")
mapa = {"acc-1": "Principal", "acc-2": pi.DESTINO_BANCO,
        "acc-3": pi.DESTINO_IGNORAR}
check("ida e volta", pi.parse_mapping(pi.format_mapping(mapa)), mapa)
check("texto vazio", pi.parse_mapping(""), {})
check("lixo é ignorado", pi.parse_mapping("sem-igual;;a=b"), {"a": "b"})
check("chave da conta é o id", pi.account_key(CONTA_CARTAO), "acc-cartao")
check("rótulo legível", pi.account_label(CONTA_CARTAO), "platinum · 9366")
check("sem número", pi.account_label({"name": "itau"}), "itau")

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
