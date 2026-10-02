"""Sincronização: os passos que deixam a planilha igual ao banco sozinhos.

    python tests/run_sync.py

O mais importante aqui é o realinhamento: a compra importada antes de a
fatura fechar ganhava o mês por dedução e nunca mais era revista. Também
se testa o `run` inteiro com a Pluggy e a planilha dubladas, porque a
ordem dos passos importa — a baixa precisa ver as linhas recém-gravadas.
"""
from __future__ import annotations

import os
import sys
import types
from datetime import date, datetime

import pandas as pd

_st = types.ModuleType("streamlit")
_st.cache_data = _st.cache_resource = lambda *a, **k: (lambda f: f)
_st.secrets = {}
sys.modules["streamlit"] = _st
for _mod in ("gspread", "gspread.worksheet", "oauth2client",
             "oauth2client.service_account"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))
sys.modules["gspread"].worksheet = sys.modules["gspread.worksheet"]
sys.modules["gspread.worksheet"].Worksheet = object
sys.modules["oauth2client"].service_account = \
    sys.modules["oauth2client.service_account"]
sys.modules["oauth2client.service_account"].ServiceAccountCredentials = object
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import card_book as cb, sync  # noqa: E402
from src.config import (ConfigKeys, ORIGEM_BANCO,  # noqa: E402
                        ORIGEM_PROJECAO, SHEETS_SCHEMA)

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


HOJE = date(2026, 10, 2)


def compra(mes, desc, valor, ident="", parcela="1/1", origem=None,
           data="2026-09-05", cartao="Principal"):
    return {"Data Compra": data, "Mês da Fatura": mes, "Cartão": cartao,
            "Descrição": desc, "Categoria": "Outros", "Parcela": parcela,
            "Valor": valor, "Status": "Pendente", "ID Pluggy": ident,
            "Origem": origem or (ORIGEM_BANCO if ident else "manual")}


print("O mês que o banco informa corrige o que foi deduzido")
# A compra de 07/09 foi importada com a fatura aberta: o app deduziu
# 10/2026 pelo dia de fechamento. O banco fechou a fatura de setembro em
# 08/09 e diz que ela pertence a 09/2026.
_bills = [{"id": "b-set", "closeDate": "2026-09-08T00:00:00.000Z",
           "dueDate": "2026-09-15T00:00:00.000Z", "totalAmount": 300}]
_txs = [
    {"id": "t1", "creditCardMetadata": {"billId": "b-set"}},
    {"id": "t2", "creditCardMetadata": {}},            # fatura aberta
]
_meses = sync.bank_months(_txs, _bills, closing_day=8, due_day=15)
check("só a compra ligada a fatura entra", _meses, {"t1": "09/2026"})

_df = pd.DataFrame([compra("10/2026", "Loja", 100.0, "t1"),
                    compra("10/2026", "Bar", 50.0, "t2"),
                    compra("10/2026", "Digitado", 10.0)])
_novo, _n = sync.realign_months(_df, _meses)
check("uma compra mudou de fatura", _n, 1)
check("e foi para a do banco", _novo.loc[0, "Mês da Fatura"], "09/2026")
check("a da fatura aberta não foi tocada",
      _novo.loc[1, "Mês da Fatura"], "10/2026")
check("rodar de novo não muda nada", sync.realign_months(_novo, _meses)[1], 0)
check("sem mapa, nada", sync.realign_months(_df, {})[1], 0)

print("A arrumação tira o que não é fato, sem perder o que foi digitado")
_lixo = pd.DataFrame([
    compra("10/2026", "Loja", 100.0, "t1", data="2026-09-20"),
    # cópia digitada da mesma compra
    compra("10/2026", "Loja", 100.0, "", data="2026-09-20"),
    # projeção gravada por versão antiga
    compra("11/2026", "KaBuM", 50.0, "", "3/3", ORIGEM_PROJECAO),
    # duas compras digitadas iguais: podem ser dois cafés de verdade
    compra("10/2026", "Café", 8.0, "", data="2026-09-21"),
    compra("10/2026", "Café", 8.0, "", data="2026-09-21"),
])
_arr = sync.housekeeping(_lixo, today=HOJE)
check("a projeção gravada sai", _arr.projecoes, 1)
check("a cópia digitada da compra do banco vai para o arquivo", _arr.copias, 1)
check("os dois cafés ficam",
      int((_arr.manter["Descrição"] == "Café").sum()), 2)
check("a linha do banco fica",
      list(_arr.manter.loc[_arr.manter["Descrição"] == "Loja", "ID Pluggy"]),
      ["t1"])
check("o arquivado é a digitada", list(_arr.arquivar["ID Pluggy"]), [""])

# Parcelamento digitado: a compra explodida em 6 meses de uma vez.
_explosao = pd.DataFrame([
    compra(m, "Geladeira", 300.0, "", f"{i}/6", data="2026-08-20")
    for i, m in enumerate(["09/2026", "10/2026", "11/2026", "12/2026",
                           "01/2027", "02/2027"], 1)])
# Arquivar as futuras não mudaria total nenhum (o livro deduz de novo as
# mesmas parcelas), então a sincronização não mexe nelas.
_arr2 = sync.housekeeping(_explosao, today=HOJE)
check("o parcelamento digitado fica inteiro", len(_arr2.manter), 6)
check("nada vai para o arquivo", len(_arr2.arquivar), 0)

check("planilha vazia", sync.housekeeping(pd.DataFrame(), today=HOJE).mudou,
      False)

print("Compra de fatura vencida vira Pago")
_cartoes = pd.DataFrame([{"Nome": "Principal", "Instituição": "Nubank",
                          "Limite": 5000, "Dia Fechamento": 8,
                          "Dia Vencimento": 15}])
_df3 = pd.DataFrame([compra("09/2026", "Antiga", 10.0, "x1"),
                     compra("10/2026", "Atual", 20.0, "x2")])
_livros = cb.build(compras=_df3, df_bills=pd.DataFrame(), df_cards=_cartoes,
                   today=HOJE)
_pago, _nb = sync.settle_status(_df3, _livros)
check("só a de setembro (venceu 15/09)", _nb, 1)
check("status", list(_pago["Status"]), ["Pago", "Pendente"])
check("idempotente", sync.settle_status(_pago, _livros)[1], 0)

print("Data de corte padrão não traz o histórico inteiro")
# A sincronização roda sozinha; sem data salva, trazer os 12 meses da
# Pluggy duplicaria tudo que foi digitado à mão.
check("sem data salva: 1º do mês", sync.cutoff("", today=HOJE),
      date(2026, 10, 1))
check("data salva vale", sync.cutoff("2026-08-15", today=HOJE),
      date(2026, 8, 15))
check("data torta cai no 1º do mês", sync.cutoff("ontem", today=HOJE),
      date(2026, 10, 1))

print("A mesma compra do banco gravada duas vezes fica uma")
_dupid = pd.DataFrame([compra("10/2026", "Loja", 100.0, "t1"),
                       compra("10/2026", "Loja", 100.0, "t1")])
_arr3 = sync.housekeeping(_dupid, today=HOJE)
check("uma sai para o arquivo", (len(_arr3.manter), len(_arr3.arquivar)),
      (1, 1))

print("Falha não se passa por sucesso")
_r = sync.Resultado(erros=["Nubank: timeout"])
check("tudo falhou: o resumo diz", _r.resumo().startswith("Não consegui"),
      True)
_r2 = sync.Resultado(novos_cartao=2, erros=["Itaú: timeout"])
check("falha parcial é contada", "conexão(ões) com erro" in _r2.resumo(),
      True)
_r3 = sync.Resultado(retidos=[1, 2, 3])
check("lote retido é avisado", "aguardando confirmação" in _r3.resumo(),
      True)

print("Compra mudada ou cancelada no banco é atualizada")
_vals, _desde = sync.bank_card_values([
    {"id": "t1", "date": "2026-09-20T10:00:00Z", "amount": 187.40,
     "type": "DEBIT"},
    {"id": "t5", "date": "2026-09-22T10:00:00Z", "amount": 50.0,
     "type": "CREDIT"},
])
check("valor com sinal: compra positiva, crédito negativo",
      (_vals["t1"][0], _vals["t5"][0]), (187.40, -50.0))
_atual = pd.DataFrame([
    compra("10/2026", "Posto (pré-autorização)", 1.0, "t1",
           data="2026-09-20"),
    compra("10/2026", "Hotel pendente", 300.0, "t9", data="2026-09-21"),
    compra("08/2026", "Antiga, fora da janela", 10.0, "t0",
           data="2026-08-01"),
    compra("10/2026", "Digitada", 10.0, "", data="2026-09-25"),
])
_ref, _n, _foi = sync.refresh_from_bank(_atual, "Principal", _vals, _desde)
check("o posto ficou com o valor abastecido", _ref.loc[0, "Valor"], 187.40)
check("um valor corrigido", _n, 1)
check("o hotel cancelado é apontado; antiga e digitada não",
      list(_atual.loc[_foi, "Descrição"]), ["Hotel pendente"])
check("sem resposta do banco, nada muda",
      sync.refresh_from_bank(_atual, "Principal", {}, _desde)[1:], (0, []))

print("Saber quando sincronizar de novo")
_agora = datetime(2026, 10, 2, 12, 0)
check("nunca sincronizou", sync.stale("", hours=6, now=_agora), True)
check("há 2 horas", sync.stale("2026-10-02T10:00", hours=6, now=_agora), False)
check("há 7 horas", sync.stale("2026-10-02T05:00", hours=6, now=_agora), True)
check("carimbo torto", sync.stale("ontem", hours=6, now=_agora), True)


# ---------------------------------------------------------------------------
# O run inteiro, com Pluggy e planilha dubladas
# ---------------------------------------------------------------------------
print("A sincronização inteira, de ponta a ponta")
from src import pluggy, positions, repository  # noqa: E402

_planilha: dict[str, pd.DataFrame] = {
    "financeiro": pd.DataFrame(columns=SHEETS_SCHEMA["financeiro"]),
    "cartao": pd.DataFrame([
        # importada com a fatura aberta, mês deduzido errado
        compra("10/2026", "Loja", 100.0, "t1", data="2026-09-07"),
        # projeção antiga gravada
        compra("11/2026", "KaBuM", 50.0, "", "3/3", ORIGEM_PROJECAO),
    ]),
    "cartoes": _cartoes,
    "importacoes": pd.DataFrame([{"ID Pluggy": "t1", "Data": "2026-09-07",
                                  "Descrição": "Loja", "Valor": 100.0,
                                  "Destino": "Principal",
                                  "Importado em": "2026-09-07"}]),
    "faturas_banco": pd.DataFrame(columns=SHEETS_SCHEMA["faturas_banco"]),
    "posicao_real": pd.DataFrame(columns=SHEETS_SCHEMA["posicao_real"]),
    "arquivo_cartao": pd.DataFrame(),
}
_config = {ConfigKeys.PLUGGY_MAPA: "acc-nu=Principal;acc-cc=Entradas e Saídas",
           ConfigKeys.PLUGGY_DESDE: "2026-09-01"}


def _ler(aba):
    return lambda: _planilha[aba].copy()


def _gravar(aba):
    def _f(df):
        _planilha[aba] = df.copy()
    return _f


repository.load_transactions = lambda: _planilha["financeiro"].assign(
    Data_DT=pd.NaT, Mes_Ano="")
repository.save_transactions = _gravar("financeiro")
repository.load_credit_card = _ler("cartao")
repository.save_credit_card = _gravar("cartao")
repository.load_cards = _ler("cartoes")
repository.save_cards = _gravar("cartoes")
repository.load_imports = _ler("importacoes")
repository.save_imports = _gravar("importacoes")
repository.imported_ids = lambda: set(
    _planilha["importacoes"]["ID Pluggy"].astype(str))
repository.load_bank_bills = _ler("faturas_banco")


def _merge(rows):
    _planilha["faturas_banco"] = pd.DataFrame(rows)


repository.merge_bank_bills = _merge
repository.append_position = lambda rows: _planilha.__setitem__(
    "posicao_real", pd.DataFrame(rows))
repository.save_archive = lambda aba, df: _planilha.__setitem__(aba, df)
repository.load_config_text = lambda k, d="": _config.get(k, d)
repository.save_config_text = lambda k, v: _config.__setitem__(k, v)

_contas = [
    {"id": "acc-nu", "type": "CREDIT", "name": "Nubank", "balance": -180,
     "creditData": {"creditLimit": 5000, "availableCreditLimit": 4820,
                    "balanceCloseDate": "2026-10-08",
                    "balanceDueDate": "2026-10-15"}},
    {"id": "acc-cc", "type": "BANK", "name": "Conta", "balance": 1234.5},
]
pluggy.item = lambda i: {"id": i, "connector": {"name": "Nubank"}}
pluggy.list_accounts = lambda i: [dict(c) for c in _contas]
pluggy.list_investments = lambda i: []
pluggy.list_bills = lambda acc: _bills
pluggy.list_transactions = lambda acc: {
    "acc-nu": [
        {"id": "t1", "date": "2026-09-07T12:00:00Z", "description": "Loja",
         "amount": 100.0, "type": "DEBIT",
         "creditCardMetadata": {"billId": "b-set"}},
        {"id": "t3", "date": "2026-09-25T12:00:00Z",
         "description": "Mercado", "amount": 80.0, "type": "DEBIT",
         "creditCardMetadata": {}},
    ],
    "acc-cc": [
        {"id": "c1", "date": "2026-09-30T12:00:00Z",
         "description": "Salário", "amount": 5000.0, "type": "CREDIT"},
    ],
}[acc]

_res = sync.run(ids=["item-1"], today=HOJE)
check("sem erros", _res.erros, [])
check("um novo na conta, um no cartão", (_res.novos_conta, _res.novos_cartao),
      (1, 1))
check("a compra de 07/09 foi para setembro, como o banco diz",
      _planilha["cartao"].set_index("ID Pluggy").loc["t1", "Mês da Fatura"],
      "09/2026")
check("a projeção gravada sumiu",
      (_planilha["cartao"]["Origem"] == ORIGEM_PROJECAO).sum(), 0)
check("setembro venceu: a compra está paga",
      _planilha["cartao"].set_index("ID Pluggy").loc["t1", "Status"], "Pago")
check("a fatura do banco foi guardada",
      list(_planilha["faturas_banco"]["Mês"]), ["09/2026"])
check("a posição foi lida com o limite do cartão",
      positions.from_rows(_planilha["posicao_real"]).contas[0].limite, 5000.0)
check("a conta ganhou a linha do salário com id",
      list(_planilha["financeiro"]["ID Pluggy"]), ["c1"])
check("o carimbo foi gravado", bool(_config.get(ConfigKeys.PLUGGY_ULTIMA_SYNC)),
      True)

_res2 = sync.run(ids=["item-1"], today=HOJE)
check("a segunda rodada não traz nada de novo",
      (_res2.novos_conta, _res2.novos_cartao, _res2.realinhadas, _res2.baixas),
      (0, 0, 0, 0))
check("nem duplica linhas", len(_planilha["cartao"]), 2)

print("Lote grande demais espera confirmação")
_config[ConfigKeys.PLUGGY_ULTIMA_SYNC] = "carimbo-anterior"
_antes = sync.LOTE_SUSPEITO
sync.LOTE_SUSPEITO = 0
_planilha["importacoes"] = _planilha["importacoes"].iloc[0:0]
_res3 = sync.run(ids=["item-1"], today=HOJE)
check("nada gravado", (_res3.novos_conta, _res3.novos_cartao), (0, 0))
check("mas os retidos ficam à mão", len(_res3.retidos) > 0, True)
check("e o carimbo não avança: a próxima abertura tenta de novo",
      _config[ConfigKeys.PLUGGY_ULTIMA_SYNC], "carimbo-anterior")

print("Conexão que falha não apaga o cartão do retrato")
_bom = _planilha["posicao_real"].copy()
_item_ok = pluggy.item
def _quebra(i):
    raise pluggy.PluggyError("fora do ar")
pluggy.item = _quebra
_res4 = sync.run(ids=["item-1"], today=HOJE)
pluggy.item = _item_ok
check("o erro aparece", bool(_res4.erros), True)
check("o cartão continua com o limite do retrato anterior",
      next((c.limite for c in positions.from_rows(
          _planilha["posicao_real"]).contas if c.chave == "acc-nu"), None),
      5000.0)
sync.LOTE_SUSPEITO = _antes

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
