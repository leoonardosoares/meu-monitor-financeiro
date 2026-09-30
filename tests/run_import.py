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


import pandas as pd  # noqa: E402

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


def montar(contas, transacoes, ja=None, sugerir=None, desde=None):
    return pi.build_pending(
        accounts=contas, transactions=transacoes,
        ja_importados=ja or set(), df_cards=CARDS, sugerir=sugerir,
        desde=desde)


def _corte(quando):
    return montar(
        [(CONTA_BANCO, pi.DESTINO_BANCO)],
        {"acc-banco": [
            tx("v1", "2025-10-09", "Antigo", -33.5, "DEBIT"),
            tx("v2", "2026-09-17", "Véspera", -10.0, "DEBIT"),
            tx("v3", "2026-09-18", "No corte", -20.0, "DEBIT"),
            tx("v4", "2026-09-25", "Depois", -30.0, "DEBIT"),
        ]}, desde=quando)


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
from src.config import SHEETS_SCHEMA as _ESQUEMA  # noqa: E402
check("colunas do cartão batem com a aba", sorted(cartao[0]),
      sorted(_ESQUEMA["cartao"]))
# O id acompanha a linha: é ele que impede o removedor de duplicatas de
# fundir duas compras iguais feitas no mesmo dia.
check("a linha do cartão leva o id da Pluggy", cartao[0]["ID Pluggy"], "c1")
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

# As compras do cartão já entram pelo cartão. Importar o débito do
# pagamento da fatura como despesa contaria o mesmo dinheiro duas vezes.
print("  Pagamento de fatura é quitação, não despesa nova")
for desc in ("Pagamento de fatura", "PAGAMENTO FATURA CARTAO",
             "Pgto fatura Nubank", "pagamento cartão de crédito"):
    check(f"{desc!r}", pi.transfer_category(desc), "Cartão de Crédito")
check("pela categoria da Pluggy",
      pi.transfer_category("NU PAGAMENTOS", "Credit card payment"),
      "Cartão de Crédito")

print("  Aporte e resgate são transferência, não gasto")
for desc in ("Aplicação CDB", "Resgate Tesouro Selic", "APLICACAO POUPANCA"):
    check(f"{desc!r}", pi.transfer_category(desc), "Investimento")

# Juros e rendimento aumentam o patrimônio: tratá-los como
# transferência esconderia justamente o que o investimento rendeu.
print("  Rendimento é receita, não movimentação entre contas")
for desc in ("Rendimentos", "Rendimento CDB", "Juros da poupança",
             "Dividendos ITSA4", "Remuneração da conta"):
    check(f"{desc!r} não é transferência", pi.transfer_category(desc), None)

print("  Mas aporte e resgate continuam sendo")
for desc in ("Resgate CDB", "Resgate Tesouro Selic", "Aplicação CDB",
             "APLICACAO AUTOMATICA", "Resgate RDB"):
    check(f"{desc!r}", pi.transfer_category(desc), "Investimento")

print("  Gasto de verdade não é confundido com transferência")
for desc in ("Supermercado Extra", "Uber trip", "Farmácia São Paulo",
             "Cartorio", "Pagamento de aluguel"):
    check(f"{desc!r}", pi.transfer_category(desc), None)

print("  A transferência vence o palpite do histórico")
p, _ = montar([(CONTA_BANCO, pi.DESTINO_BANCO)],
              {"acc-banco": [tx("f1", "2026-09-10", "Pagamento de fatura",
                                -1983.53, "DEBIT")]},
              sugerir=lambda d: "Lazer")
check("classificada como quitação", p[0].categoria, "Cartão de Crédito")

print("  Parcela vem do que a Pluggy informa")
def tx_parcela(id_, atual, total):
    t = tx(id_, "2026-09-05", "Link de Fotos", -266.67, "DEBIT")
    t["creditCardMetadata"] = {"installmentNumber": atual,
                               "totalInstallments": total}
    return t

check("3 de 6", pi.installment_label(tx_parcela("x", 3, 6)), "3/6")
check("sem metadados", pi.installment_label(tx("y", "2026-09-05", "z", -1.0)),
      "1/1")
check("metadados incompletos",
      pi.installment_label(tx_parcela("x", None, 6)), "1/1")
check("total zero não vira divisão estranha",
      pi.installment_label(tx_parcela("x", 1, 0)), "1/1")

p, _ = montar([(CONTA_CARTAO, "Principal")],
              {"acc-cartao": [tx_parcela("p1", 3, 6)]})
_, cartao, _ = pi.to_rows(p)
check("chega na linha do cartão", cartao[0]["Parcela"], "3/6")

print("  Lançamento de banco nunca ganha parcela de cartão")
p, _ = montar([(CONTA_BANCO, pi.DESTINO_BANCO)],
              {"acc-banco": [tx_parcela("b9", 3, 6)]})
check("fica 1/1", p[0].parcela, "1/1")

# O banco monta a fatura como gasto do mês menos os créditos —
# "Pagamento antecipado" de R$ 75,01 numa fatura de R$ 2.356,48 dá os
# R$ 2.281,47 cobrados. Descartar o crédito deixava o app acima do
# banco pelo valor de cada pagamento feito antes do fechamento.
print("  Crédito em fatura abate, como no extrato do banco")
p, avisos = montar(
    [(CONTA_CARTAO, "Principal")],
    {"acc-cartao": [
        tx("k1", "2026-09-05", "Padaria", -20.0, "DEBIT"),
        tx("k2", "2026-09-05", "Pagamento recebido", 1380.0, "CREDIT"),
        tx("k3", "2026-09-05", "Crédito de parcelamento", 46.29, "CREDIT"),
    ]})
check("compra e créditos entram", len(p), 3)
check("a compra é positiva",
      next(x.valor for x in p if x.descricao == "Padaria"), 20.0)
check("o pagamento entra negativo",
      next(x.valor for x in p if x.descricao == "Pagamento recebido"),
      -1380.0)
check("o estorno também",
      next(x.valor for x in p if x.descricao == "Crédito de parcelamento"),
      -46.29)
# A soma é a fatura: gasto menos crédito, como o banco mostra.
check("a soma reproduz a fatura", round(sum(x.valor for x in p), 2),
      round(20.0 - 1380.0 - 46.29, 2))
check("os créditos são reportados",
      sum("crédito(s) em fatura" in a for a in avisos), 1)
check("o aviso explica o abatimento",
      any("abatem a fatura" in a for a in avisos), True)

print("  No banco, crédito continua sendo receita")
p, avisos = montar(
    [(CONTA_BANCO, pi.DESTINO_BANCO)],
    {"acc-banco": [tx("k4", "2026-09-05", "Salário", 5000.0, "CREDIT")]})
check("entra normalmente", [(x.descricao, x.tipo) for x in p],
      [("Salário", "Entrada")])
check("sem aviso", avisos, [])

# 12 meses de histórico colidiriam com o que foi digitado à mão, que
# não tem identificador nenhum para o app reconhecer.
print("  Corte por data acontece no app")
from datetime import date as _date
p, avisos = montar(
    [(CONTA_BANCO, pi.DESTINO_BANCO)],
    {"acc-banco": [
        tx("v1", "2025-10-09", "Antigo", -33.5, "DEBIT"),
        tx("v2", "2026-09-17", "Véspera", -10.0, "DEBIT"),
        tx("v3", "2026-09-18", "No corte", -20.0, "DEBIT"),
        tx("v4", "2026-09-25", "Depois", -30.0, "DEBIT"),
    ]})
check("sem corte, vem tudo", len(p), 4)

p, avisos = _corte(_date(2026, 9, 18))
check("o dia do corte entra", [x.descricao for x in p],
      ["No corte", "Depois"])
check("os antigos viram aviso", len(avisos), 1)
check("o aviso diz quantos e desde quando",
      ("2 lançamento" in avisos[0] and "18/09/2026" in avisos[0]), True)

# Salário cai no Itaú e vai para o Nubank: a Pluggy devolve as duas
# pontas. Sem casar, o mês de R$ 5.000 vira R$ 10.000 de receita.
print("  Dinheiro andando entre suas contas não é receita nem despesa")
ITAU = {"id": "i", "name": "itau", "number": "1", "type": "BANK"}
NU = {"id": "n", "name": "Nu", "number": "2", "type": "BANK"}


def dois_bancos(itau_txs, nu_txs):
    return montar([(ITAU, pi.DESTINO_BANCO), (NU, pi.DESTINO_BANCO)],
                  {"i": itau_txs, "n": nu_txs})


p, avisos = dois_bancos(
    [tx("s1", "2026-09-05", "Salário", 5000.0, "CREDIT"),
     tx("s2", "2026-09-06", "Pix enviado", -5000.0, "DEBIT")],
    [tx("s3", "2026-09-06", "Pix recebido", 5000.0, "CREDIT")])
categorias = {x.descricao: x.categoria for x in p}
check("as duas pontas viram Transferência",
      (categorias["Pix enviado"], categorias["Pix recebido"]),
      ("Transferência", "Transferência"))
check("o salário não é tocado", categorias["Salário"], "Outros")
check("o par é reportado", "1 par(es)" in avisos[-1], True)

print("  E some das receitas e despesas do período")
banco, _, _ = pi.to_rows(p)
from src.finance import compute_wealth  # noqa: E402
_df = pd.DataFrame(banco)
_w = compute_wealth(_df, _df)
check("receita é só o salário", round(_w.total_income, 2), 5000.0)
check("despesa é zero", round(_w.total_expense, 2), 0.0)

print("  O que não é par continua sendo gasto de verdade")
p, _ = dois_bancos(
    [tx("a1", "2026-09-06", "Pix para o aluguel", -1500.0, "DEBIT")],
    [tx("a2", "2026-09-06", "Pix recebido", 900.0, "CREDIT")])
check("valores diferentes não casam",
      {x.categoria for x in p}, {"Outros"})

p, _ = dois_bancos(
    [tx("b1", "2026-09-01", "Pix enviado", -300.0, "DEBIT")],
    [tx("b2", "2026-09-20", "Pix recebido", 300.0, "CREDIT")])
check("fora da janela de dias não casa",
      {x.categoria for x in p}, {"Outros"})

p, _ = montar([(ITAU, pi.DESTINO_BANCO)],
              {"i": [tx("c1", "2026-09-06", "Saiu", -300.0, "DEBIT"),
                     tx("c2", "2026-09-06", "Entrou", 300.0, "CREDIT")]})
check("na MESMA conta não é transferência entre contas",
      {x.categoria for x in p}, {"Outros"})

print("  Uma entrada não pode quitar duas saídas")
p, avisos = dois_bancos(
    [tx("d1", "2026-09-06", "Pix 1", -300.0, "DEBIT"),
     tx("d2", "2026-09-06", "Pix 2", -300.0, "DEBIT")],
    [tx("d3", "2026-09-06", "Pix recebido", 300.0, "CREDIT")])
check("só um par", sum(1 for x in p
                       if x.categoria == "Transferência"), 2)
check("a outra saída continua despesa",
      sum(1 for x in p if x.categoria == "Outros"), 1)

print("  Duas transferências iguais geram dois pares")
p, _ = dois_bancos(
    [tx("e1", "2026-09-06", "Pix 1", -300.0, "DEBIT"),
     tx("e2", "2026-09-07", "Pix 2", -300.0, "DEBIT")],
    [tx("e3", "2026-09-06", "Recebido 1", 300.0, "CREDIT"),
     tx("e4", "2026-09-07", "Recebido 2", 300.0, "CREDIT")])
check("todos marcados",
      sum(1 for x in p if x.categoria == "Transferência"), 4)

print("  Compra no cartão nunca vira transferência")
p, _ = montar([(ITAU, pi.DESTINO_BANCO), (CONTA_CARTAO, "Principal")],
              {"i": [tx("f1", "2026-09-06", "Pix enviado", -50.0, "DEBIT")],
               "acc-cartao": [tx("f2", "2026-09-06", "Padaria", -50.0, "DEBIT")]})
check("nenhuma marcada",
      sum(1 for x in p if x.categoria == "Transferência"), 0)

print("  A categoria é reconhecida como transferência pelo app")
from src.config import TRANSFER_CATEGORIES, SYSTEM_CATEGORIES  # noqa: E402
check("neutralizada nos KPIs", "Transferência" in TRANSFER_CATEGORIES, True)
check("aparece nos selects", "Transferência" in SYSTEM_CATEGORIES, True)

# A fatura informada pelo banco é resposta, não estimativa. Deduzir
# pelo dia de fechamento foi a origem de várias idas e vindas: bastava
# o dia cadastrado estar errado para a compra cair no mês errado.
print("  A fatura vem do banco, não da nossa regra")

CARTAO_PLUGGY = {"id": "acc-cartao", "name": "platinum", "number": "9366",
                 "type": "CREDIT"}


def com_fatura(id_, bill, faturas, cartao="Cartão Itaú"):
    t = tx(id_, "2026-09-25", "Padaria", -20.0, "DEBIT")
    if bill:
        t["creditCardMetadata"] = {"billId": bill}
    return pi.build_pending(
        accounts=[(CARTAO_PLUGGY, cartao)], transactions={"acc-cartao": [t]},
        ja_importados=set(), df_cards=CARDS, bills={"acc-cartao": faturas})


# Mesmo vencimento em outubro, rótulos diferentes: o Itaú fecha dia 30 e
# vence no mês seguinte, o Principal fecha dia 8 e vence no próprio mês.
p, _ = com_fatura("b1", "x", [{"id": "x", "dueDate": "2026-10-07"}])
check("Itaú: vence 07/10 -> fatura 09/2026", p[0].mes_fatura, "09/2026")
p, _ = com_fatura("b2", "y", [{"id": "y", "dueDate": "2026-10-15"}],
                  cartao="Principal")
check("Principal: vence 15/10 -> fatura 10/2026", p[0].mes_fatura, "10/2026")

# Faturas reais do Nubank, com os nomes e o formato que a Pluggy usa.
print("  Faturas reais do banco, campo por campo")
from datetime import date as _d  # noqa: E402
REAIS = [
    {"id": "8739f2ec", "dueDate": "2026-09-15T00:00:00.000Z",
     "billClosingDate": "2026-09-08T00:00:00.000Z",
     "totalAmount": 2281.4697},
    {"id": "7f051f1f", "dueDate": "2026-08-17T00:00:00.000Z",
     "billClosingDate": "2026-08-08T00:00:00.000Z",
     "totalAmount": 2081.7916},
]
_linhas = pi.bill_rows(REAIS, cartao="Principal", closing_day=8, due_day=15,
                       lido_em=_d(2026, 9, 30))
check("mês pelo fechamento", [x["Mês"] for x in _linhas],
      ["09/2026", "08/2026"])
check("total arredondado como o app do banco mostra",
      _linhas[0]["Total"], 2281.47)
check("fechamento preservado", _linhas[0]["Fechamento"], "2026-09-08")
check("vencimento preservado", _linhas[0]["Vencimento"], "2026-09-15")
# Vencimento 15 num mês e 17 no outro. No empate fica o menor: o dia
# maior é feriado empurrando para frente, nunca o contrário.
check("dias deduzidos do próprio banco",
      pi.infer_card_days(REAIS, []), (8, 15))
check("com o 15 dominando, não muda",
      pi.infer_card_days(REAIS + [dict(REAIS[0], id="c",
                                       dueDate="2026-07-15T00:00:00.000Z",
                                       billClosingDate="2026-07-08T00:00:00.000Z")],
                         []), (8, 15))

print("  Data de fechamento informada manda sobre tudo")
p, _ = com_fatura("b3", "z", [{"id": "z", "closeDate": "2026-08-30",
                               "dueDate": "2026-10-07"}])
check("usa o fechamento", p[0].mes_fatura, "08/2026")
for campo in ("closingDate", "billDate", "periodEnd", "endDate"):
    p, _ = com_fatura("b4", "w", [{"id": "w", campo: "2026-07-30"}])
    check(f"aceita {campo}", p[0].mes_fatura, "07/2026")

print("  Sem a fatura do banco, deduz e avisa")
p, avisos = com_fatura("b5", None, [{"id": "z", "dueDate": "2026-10-07"}])
check("caiu na dedução", p[0].mes_fatura, "09/2026")
check("avisou", any("deduzido" in a for a in avisos), True)

p, avisos = com_fatura("b6", "nao-existe",
                       [{"id": "z", "dueDate": "2026-10-07"}])
check("billId desconhecido também deduz",
      any("deduzido" in a for a in avisos), True)

print("  Com a fatura do banco, nenhum aviso de dedução")
p, avisos = com_fatura("b7", "z", [{"id": "z", "dueDate": "2026-10-07"}])
check("silêncio", any("deduzido" in a for a in avisos), False)

print("  O índice de faturas ignora o que não dá para usar")
idx = pi.bill_index(
    [{"id": "a", "dueDate": "2026-10-07"}, {"id": "", "dueDate": "2026-10-07"},
     {"dueDate": "2026-10-07"}, {"id": "b"}],
    closing_day=30, due_day=7)
check("só a fatura completa entra", idx, {"a": "09/2026"})
check("lista vazia", pi.bill_index([], closing_day=8, due_day=15), {})
check("None", pi.bill_index(None, closing_day=8, due_day=15), {})

print("  O billId é lido de onde a Pluggy o coloca")
check("em creditCardMetadata",
      pi.bill_id({"creditCardMetadata": {"billId": "b"}}), "b")
check("em bill_id", pi.bill_id({"creditCardMetadata": {"bill_id": "b"}}), "b")
check("na raiz", pi.bill_id({"billId": "b"}), "b")
check("ausente", pi.bill_id({"id": "t"}), "")

# Somar as linhas que chegaram só dá o total certo se nenhuma compra
# faltou — e uma compra que não chegou é invisível justamente na soma.
print("  O total da fatura vem do banco, não da soma das linhas")
from datetime import date as _d  # noqa: E402

FATURAS = [
    {"id": "b1", "dueDate": "2026-10-15", "totalAmount": 2679.04,
     "status": "OPEN"},
    {"id": "b2", "dueDate": "2026-09-15", "totalAmount": 333.48,
     "status": "CLOSED"},
]
linhas = pi.bill_rows(FATURAS, cartao="Principal", closing_day=8,
                      due_day=15, lido_em=_d(2026, 9, 30))
check("uma linha por fatura", len(linhas), 2)
check("meses certos", sorted(x["Mês"] for x in linhas),
      ["09/2026", "10/2026"])
check("total da aberta",
      next(x["Total"] for x in linhas if x["Mês"] == "10/2026"), 2679.04)
check("guarda o vencimento",
      next(x["Vencimento"] for x in linhas if x["Mês"] == "10/2026"),
      "2026-10-15")
check("e a situação",
      next(x["Situação"] for x in linhas if x["Mês"] == "10/2026"), "OPEN")

print("  Total negativo vira dívida positiva")
check("sinal normalizado",
      pi.bill_rows([{"id": "x", "dueDate": "2026-10-15",
                     "totalAmount": -500.0}],
                   cartao="P", closing_day=8, due_day=15,
                   lido_em=_d(2026, 9, 30))[0]["Total"], 500.0)

print("  Campo de total varia por instituição")
for campo in ("totalAmount", "total", "amount", "balance"):
    r = pi.bill_rows([{"id": "x", "dueDate": "2026-10-15", campo: 10.0}],
                     cartao="P", closing_day=8, due_day=15,
                     lido_em=_d(2026, 9, 30))
    check(f"lê {campo}", r[0]["Total"], 10.0)

print("  Fatura sem mês legível fica de fora")
check("sem datas", pi.bill_rows([{"id": "x"}], cartao="P", closing_day=8,
                                due_day=15, lido_em=_d(2026, 9, 30)), [])
check("lista vazia", pi.bill_rows([], cartao="P", closing_day=8, due_day=15,
                                  lido_em=_d(2026, 9, 30)), [])
check("None", pi.bill_rows(None, cartao="P", closing_day=8, due_day=15,
                           lido_em=_d(2026, 9, 30)), [])

print("  As colunas batem com a aba da planilha")
from src.config import SHEETS_SCHEMA as _SS  # noqa: E402
check("mesmo formato", sorted(linhas[0]), sorted(_SS["faturas_banco"]))

# O usuário não deveria precisar saber esses dias de cor, e errar um
# deles deslocava fatura inteira. O banco não informa o fechamento, mas
# o extrato o denuncia: a última compra de cada fatura cai nele.
print("  Fechamento e vencimento deduzidos do banco")


def ciclo(dia_fecha: int, dia_vence: int, meses=range(4, 10)):
    faturas = [{"id": f"b{m}", "dueDate": f"2026-{m:02d}-{dia_vence:02d}"}
               for m in meses]
    txs = []
    for m in meses:
        txs += [
            tx(f"t{m}a", f"2026-{m:02d}-02", "cedo", -1.0, "DEBIT"),
            tx(f"t{m}b", f"2026-{m:02d}-{dia_fecha:02d}", "tarde", -1.0,
               "DEBIT"),
        ]
        for t in txs[-2:]:
            t["creditCardMetadata"] = {"billId": f"b{m}"}
    return faturas, txs


f, t = ciclo(8, 15)
check("Principal: fecha 8, vence 15", pi.infer_card_days(f, t), (8, 15))
f, t = ciclo(30, 7)
check("Itaú: fecha 30, vence 7", pi.infer_card_days(f, t), (30, 7))

print("  Sem dado, devolve None em vez de chutar")
check("nada", pi.infer_card_days([], []), (None, None))
check("só faturas", pi.infer_card_days(ciclo(8, 15)[0], []), (None, 15))
check("compras sem billId não deduzem fechamento",
      pi.infer_card_days([], [tx("x", "2026-09-08", "y", -1.0, "DEBIT")]),
      (None, None))

print("  Um mês fora do padrão não desloca a dedução")
f, t = ciclo(8, 15)
# Uma fatura venceu num feriado e foi empurrada para o dia 17.
f.append({"id": "bx", "dueDate": "2026-10-17"})
t.append(dict(tx("tx1", "2026-10-09", "atípica", -1.0, "DEBIT"),
              creditCardMetadata={"billId": "bx"}))
check("fica com o dia mais frequente", pi.infer_card_days(f, t), (8, 15))

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
