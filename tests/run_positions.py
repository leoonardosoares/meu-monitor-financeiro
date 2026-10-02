"""Posição real lida das instituições.

    python tests/run_positions.py

O que se verifica aqui é o dinheiro: sinal de saldo de cartão, campo de
valor que varia por produto, e a reconstrução do retrato guardado. Um
erro nesta camada mostra um patrimônio errado na primeira tela do app.
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

import pandas as pd  # noqa: E402

from src import positions as ps  # noqa: E402

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


POS = ps.Posicao(
    contas=[ps.Conta("Nu Pagamentos", "BANK", 222.68, "Nubank"),
            ps.Conta("platinum", "CREDIT", -5083.68, "Nubank"),
            ps.Conta("itau", "BANK", 0.01, "Itaú"),
            ps.Conta("ITAU VISA", "CREDIT", 1333.30, "Itaú")],
    ativos=[ps.Ativo("CDB Liquidez", "FIXED_INCOME", 12000.0, "Itaú")],
    quando="2026-09-29T20:00")

# Nubank devolveu o saldo do cartão negativo e o Itaú positivo. Somar o
# valor cru daria quase zero de dívida, e o patrimônio ficaria inflado
# em mais de dez mil reais.
print("  Dívida de cartão é positiva venha o sinal que vier")
check("em conta", round(POS.em_conta, 2), 222.69)
check("dívida somada em módulo", round(POS.em_cartao, 2), 6416.98)
check("investido", round(POS.investido, 2), 12000.0)
check("patrimônio = conta + investido − dívida",
      round(POS.patrimonio, 2), round(222.69 + 12000.0 - 6416.98, 2))

print("  Posição vazia não finge número")
vazia = ps.Posicao()
check("marcada como vazia", vazia.vazia, True)
check("tudo zero", (vazia.em_conta, vazia.investido, vazia.patrimonio),
      (0.0, 0.0, 0.0))

print("  Valor do investimento tolera o campo que a instituição usar")
for campo in ("balance", "value", "amount"):
    check(f"lê {campo}", ps._valor_do_ativo({campo: 1500.0}), 1500.0)
check("prefere balance quando há vários",
      ps._valor_do_ativo({"balance": 10.0, "value": 99.0}), 10.0)
check("pula campo zerado e usa o próximo",
      ps._valor_do_ativo({"balance": 0, "value": 77.0}), 77.0)
check("sem campo nenhum", ps._valor_do_ativo({"nome": "x"}), 0.0)
check("texto não numérico", ps._valor_do_ativo({"balance": "abc"}), 0.0)

print("  Retrato guardado volta igual")
df = pd.DataFrame(ps.to_rows(POS))
volta = ps.from_rows(df)
check("linhas gravadas", len(df), 5)
check("patrimônio preservado",
      round(volta.patrimonio, 2), round(POS.patrimonio, 2))
check("contas e ativos separados de novo",
      (len(volta.contas), len(volta.ativos)), (4, 1))
check("carimbo preservado", volta.quando, "2026-09-29T20:00")

print("  Só o retrato mais recente é usado")
antigo = ps.Posicao(contas=[ps.Conta("x", "BANK", 1.0)],
                    quando="2026-01-01T10:00")
df2 = pd.DataFrame(ps.to_rows(antigo) + ps.to_rows(POS))
check("pega o novo", round(ps.from_rows(df2).em_conta, 2), 222.69)

print("  Histórico mede patrimônio por DIA, não por clique")
h = ps.history(df2)
check("dois dias", len(h), 2)
check("eixo em datas, não horários", list(h["Data"]),
      ["2026-01-01", "2026-09-29"])
check("o antigo", round(h["Patrimônio"].iloc[0], 2), 1.0)
check("o novo", round(h["Patrimônio"].iloc[1], 2), round(POS.patrimonio, 2))

# Clicar em Atualizar várias vezes num dia não pode virar vários pontos.
manha = ps.Posicao(contas=[ps.Conta("x", "BANK", 10.0)],
                   quando="2026-09-29T09:00")
tarde = ps.Posicao(contas=[ps.Conta("x", "BANK", 99.0)],
                   quando="2026-09-29T21:45")
h2 = ps.history(pd.DataFrame(ps.to_rows(manha) + ps.to_rows(tarde)))
check("um ponto por dia", len(h2), 1)
check("vale o último do dia", round(h2["Patrimônio"].iloc[0], 2), 99.0)

# O saldo do cartão precisa chegar ao cartão certo. Casar por nome
# quebraria em silêncio no dia em que o banco renomeasse a conta.
print("  Dívida do banco chega ao cartão cadastrado")
POS_CHAVE = ps.Posicao(contas=[
    ps.Conta("platinum", "CREDIT", -5083.68, "Nubank", "acc-1"),
    ps.Conta("ITAU VISA", "CREDIT", 1333.30, "Itaú", "acc-2"),
    ps.Conta("Nu conta", "BANK", 222.68, "Nubank", "acc-3"),
])
mapa = {"acc-1": "Principal", "acc-2": "Cartão Itaú", "acc-3": "Entradas e Saídas"}
contas = ps.card_accounts(POS_CHAVE, mapa)
check("dois cartões", sorted(contas), ["Cartão Itaú", "Principal"])
check("a conta certa para cada um",
      (contas["Principal"].chave, contas["Cartão Itaú"].chave),
      ("acc-1", "acc-2"))
check("conta corrente não entra", "Entradas e Saídas" in contas, False)

check("sem mapa, nada casa", ps.card_accounts(POS_CHAVE, {}), {})
check("mapa None", ps.card_accounts(POS_CHAVE, None), {})
check("conta sem destino é ignorada",
      ps.card_accounts(POS_CHAVE, {"acc-9": "X"}), {})

# Cartão adicional: duas contas da Pluggy para o mesmo cartão daqui.
# Limite e disponível são do cartão, não somam entre titular e
# adicional — fica a conta que trouxe os dados de crédito.
dois = ps.Posicao(contas=[
    ps.Conta("titular", "CREDIT", -100.0, "Nubank", "a"),
    ps.Conta("adicional", "CREDIT", -50.0, "Nubank", "b",
             limite=3000.0, disponivel=2850.0),
])
check("fica a que tem dados de crédito",
      ps.card_accounts(dois, {"a": "Principal", "b": "Principal"})
      ["Principal"].chave, "b")

print("  Dados de crédito: o que o banco informa sobre o cartão")
_api = ps.account_from_api({
    "id": "acc-nu", "type": "CREDIT", "name": "Nubank", "balance": 5083.68,
    "creditData": {"creditLimit": 5150, "availableCreditLimit": 66.32,
                   "balanceCloseDate": "2026-10-08T03:00:00.000Z",
                   "balanceDueDate": "2026-10-15"}}, instituicao="Nubank")
check("limite e disponível", (_api.limite, _api.disponivel), (5150.0, 66.32))
check("limite em uso", round(_api.usado, 2), 5083.68)
check("datas da fatura aberta", (_api.fecha, _api.vence),
      ("2026-10-08", "2026-10-15"))
_sem = ps.account_from_api({"id": "x", "type": "BANK", "balance": 10},
                           instituicao="Itaú")
check("conta sem creditData não inventa limite",
      (_sem.limite, _sem.disponivel, _sem.usado, _sem.fecha),
      (None, None, None, ""))
_ida_volta = ps.from_rows(pd.DataFrame(ps.to_rows(
    ps.Posicao(contas=[_api, _sem], quando="2026-10-02T09:00"))))
check("os dados de crédito sobrevivem à planilha",
      next(c for c in _ida_volta.contas if c.chave == "acc-nu").usado, 5083.68)
check("e a conta comum continua sem eles",
      next(c for c in _ida_volta.contas if c.chave == "x").limite, None)
_antigo = pd.DataFrame([{"Data": "2026-09-01T10:00", "Origem": "Nubank",
                         "Nome": "Nubank", "Classe": "CREDIT",
                         "Valor": -100.0, "Chave": "acc-nu"}])
check("retrato antigo, sem as colunas novas, ainda é lido",
      ps.from_rows(_antigo).contas[0].limite, None)

# A curva da carteira responde "quanto rendeu"; misturar conta
# corrente e cartão a tornaria a curva de outra coisa.
print("  Curva da carteira exclui conta e cartão")
_a = ps.Posicao(contas=[ps.Conta("c", "BANK", 100.0),
                        ps.Conta("cc", "CREDIT", -500.0)],
                ativos=[ps.Ativo("CDB", "FIXED", 1000.0)],
                quando="2026-09-01T10:00")
_b = ps.Posicao(contas=[ps.Conta("c", "BANK", 150.0)],
                ativos=[ps.Ativo("CDB", "FIXED", 1050.0)],
                quando="2026-09-30T10:00")
_curva = ps.invested_history(pd.DataFrame(ps.to_rows(_a) + ps.to_rows(_b)))
check("dois pontos", len(_curva), 2)
check("só o investido", [round(v, 2) for v in _curva["Investido"]],
      [1000.0, 1050.0])
check("um ponto por dia", list(_curva["Data"]),
      ["2026-09-01", "2026-09-30"])
check("sem investimento, curva vazia",
      ps.invested_history(pd.DataFrame(ps.to_rows(
          ps.Posicao(contas=[ps.Conta("c", "BANK", 1.0)],
                     quando="2026-09-01T10:00")))).empty, True)
check("planilha vazia", list(ps.invested_history(pd.DataFrame()).columns),
      ["Data", "Investido"])

print("  Planilha vazia não quebra")
check("from_rows", ps.from_rows(pd.DataFrame()).vazia, True)
check("history", list(ps.history(pd.DataFrame()).columns),
      ["Data", "Patrimônio"])
check("to_rows de posição vazia", ps.to_rows(ps.Posicao()), [])

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
