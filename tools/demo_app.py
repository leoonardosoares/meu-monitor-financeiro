"""App real com planilha e banco dublados, para conferir o visual.

    DEMO_TEMA=light streamlit run tools/demo_app.py
"""
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
for _m in ("gspread", "gspread.worksheet", "oauth2client",
           "oauth2client.service_account"):
    sys.modules.setdefault(_m, types.ModuleType(_m))
sys.modules["gspread"].worksheet = sys.modules["gspread.worksheet"]
sys.modules["gspread"].Spreadsheet = object
sys.modules["gspread.worksheet"].Worksheet = object
sys.modules["oauth2client"].service_account = sys.modules["oauth2client.service_account"]
sys.modules["oauth2client.service_account"].ServiceAccountCredentials = object

import pandas as pd  # noqa: E402

from src import auth, pluggy, repository  # noqa: E402
from src.config import ConfigKeys, SHEETS_SCHEMA  # noqa: E402

TEMA = os.environ.get("DEMO_TEMA", "dark")
PAGINA = os.environ.get("DEMO_PAGINA", "Dashboard")


def vazia(aba):
    return pd.DataFrame(columns=SHEETS_SCHEMA[aba])


def l(data, mes, cartao, desc, cat, valor, parc="1/1", ident="x"):
    return {"Data Compra": data, "Mês da Fatura": mes, "Cartão": cartao,
            "Descrição": desc, "Categoria": cat, "Parcela": parc,
            "Valor": valor, "Status": "Pendente", "ID Pluggy": ident,
            "Origem": "banco"}


CARTAO = pd.DataFrame([
    l("2026-08-20", "09/2026", "Principal", "Mercadolivre 1/10", "Compras", 235.31, "1/10", "a1"),
    l("2026-09-02", "09/2026", "Principal", "Supermercado Dia", "Supermercado", 412.80, ident="a2"),
    l("2026-09-05", "09/2026", "Principal", "KaBuM 2/3", "Eletrônicos", 189.90, "2/3", "a3"),
    l("2026-09-12", "10/2026", "Principal", "Mercadolivre 2/10", "Compras", 235.31, "2/10", "a4"),
    l("2026-09-14", "10/2026", "Principal", "iFood", "Restaurante", 87.40, ident="a5"),
    l("2026-09-15", "10/2026", "Principal", "Pagamento recebido", "Cartão de Crédito", -1595.64, ident="a6"),
    l("2026-09-18", "10/2026", "Principal", "Posto Shell", "Transporte", 220.00, ident="a7"),
    l("2026-09-21", "10/2026", "Principal", "Netflix", "Assinaturas", 55.90, ident="a8"),
    l("2026-09-25", "10/2026", "Principal", "Farmácia São João", "Saúde", 133.34, ident="a9"),
    l("2026-09-27", "10/2026", "Principal", "Amazon", "Compras", 349.00, ident="a10"),
    l("2026-08-28", "09/2026", "Cartão Itaú", "Padaria Real", "Supermercado", 46.70, ident="i1"),
    l("2026-09-10", "09/2026", "Cartão Itaú", "Uber", "Transporte", 32.50, ident="i2"),
    l("2026-10-01", "10/2026", "Cartão Itaú", "Cinema", "Lazer", 64.00, ident="i3"),
])
CARTOES = pd.DataFrame([
    {"Nome": "Principal", "Instituição": "Nubank", "Limite": 5150.0, "Dia Fechamento": 8, "Dia Vencimento": 15},
    {"Nome": "Cartão Itaú", "Instituição": "Itaú", "Limite": 1600.0, "Dia Fechamento": 30, "Dia Vencimento": 7},
])
FATURAS = pd.DataFrame([
    {"Cartão": "Principal", "Mês": "09/2026", "Total": 1595.64, "Fechamento": "2026-09-08",
     "Vencimento": "2026-09-15", "Situação": "CLOSED", "Lido em": "2026-10-02"},
    {"Cartão": "Principal", "Mês": "08/2026", "Total": 2281.47, "Fechamento": "2026-08-08",
     "Vencimento": "2026-08-15", "Situação": "CLOSED", "Lido em": "2026-10-02"},
])
CDB = "CDB - NU FINANCEIRA S.A. - SOCIEDADE DE CREDITO, FINANCIAMENTO E INVESTIMENTO"
POS = []
for dia, fator in (("2026-09-29T09:00", 0.97), ("2026-09-30T09:00", 0.99), ("2026-10-02T09:00", 1.0)):
    POS += [
        {"Data": dia, "Origem": "MeuPluggy", "Nome": "Nu Pagamentos S.A. - Instituição de Pagamento",
         "Classe": "BANK", "Valor": 517.16 * fator, "Chave": "acc-nu"},
        {"Data": dia, "Origem": "Itaú", "Nome": "itau", "Classe": "BANK", "Valor": 290.01, "Chave": "acc-it"},
        {"Data": dia, "Origem": "MeuPluggy", "Nome": "Nubank", "Classe": "CREDIT", "Valor": -5148.13,
         "Chave": "acc-nu-card", "Limite": 5150.0, "Disponível": 1.87,
         "Fechamento": "2026-10-08", "Vencimento": "2026-10-15"},
        {"Data": dia, "Origem": "Itaú", "Nome": "Itaú Click", "Classe": "CREDIT", "Valor": -1333.30,
         "Chave": "acc-it-card"},
        {"Data": dia, "Origem": "MeuPluggy", "Nome": "Tesouro Selic 2031", "Classe": "TREASURE", "Valor": 595.77 * fator, "Chave": ""},
    ] + [{"Data": dia, "Origem": "MeuPluggy", "Nome": CDB, "Classe": "FIXED_INCOME", "Valor": v * fator, "Chave": ""}
         for v in (0.01, 0.01, 217.69, 103.21, 189.40, 8794.47)]
POSICAO = pd.DataFrame(POS)

FIN = pd.DataFrame([
    {"Data": "2026-08-05", "Descrição": "Salário", "Categoria": "Receita/Salário", "Valor": 6200.0, "Tipo": "Entrada"},
    {"Data": "2026-08-10", "Descrição": "Aluguel", "Categoria": "Aluguel", "Valor": 1800.0, "Tipo": "Saída"},
    {"Data": "2026-08-15", "Descrição": "Pagamento fatura", "Categoria": "Cartão de Crédito", "Valor": 2281.47, "Tipo": "Saída"},
    {"Data": "2026-09-05", "Descrição": "Salário", "Categoria": "Receita/Salário", "Valor": 6200.0, "Tipo": "Entrada"},
    {"Data": "2026-09-10", "Descrição": "Aluguel", "Categoria": "Aluguel", "Valor": 1800.0, "Tipo": "Saída"},
    {"Data": "2026-09-12", "Descrição": "Condomínio", "Categoria": "Condomínio", "Valor": 640.0, "Tipo": "Saída"},
    {"Data": "2026-09-15", "Descrição": "Pagamento fatura", "Categoria": "Cartão de Crédito", "Valor": 1595.64, "Tipo": "Saída"},
    {"Data": "2026-09-20", "Descrição": "Aplicação CDB", "Categoria": "Investimento", "Valor": 800.0, "Tipo": "Saída"},
    {"Data": "2026-10-01", "Descrição": "Mercado", "Categoria": "Supermercado", "Valor": 230.0, "Tipo": "Saída"},
])
FIN["ID Pluggy"] = [f"f{i}" for i in range(len(FIN))]

TABELAS = {
    "cartao": CARTAO, "cartoes": CARTOES, "faturas_banco": FATURAS,
    "posicao_real": POSICAO, "financeiro": FIN,
    "categorias": pd.DataFrame({"Categoria": ["Aluguel", "Supermercado", "Lazer", "Saúde", "Compras",
                                              "Restaurante", "Transporte", "Assinaturas", "Eletrônicos", "Condomínio"]}),
    "orcamentos": pd.DataFrame([{"Categoria": "Supermercado", "Limite": 900}, {"Categoria": "Restaurante", "Limite": 300},
                                {"Categoria": "Lazer", "Limite": 250}, {"Categoria": "Compras", "Limite": 600}]),
    "custos_fixos": pd.DataFrame([{"Descrição": "Aluguel", "Categoria": "Aluguel", "Valor": 1800.0},
                                  {"Descrição": "Condomínio", "Categoria": "Condomínio", "Valor": 640.0}]),
    "importacoes": pd.DataFrame([{"ID Pluggy": i, "Data": "", "Descrição": "", "Valor": 0, "Destino": "",
                                  "Importado em": "2026-10-01"} for i in list(CARTAO["ID Pluggy"]) + list(FIN["ID Pluggy"])]),
}
CONFIG = {ConfigKeys.TEMA: TEMA, ConfigKeys.PLUGGY_MAPA: "acc-nu-card=Principal;acc-it-card=Cartão Itaú;acc-nu=Entradas e Saídas",
          ConfigKeys.PLUGGY_ITEMS: "item-1", ConfigKeys.PLUGGY_ULTIMA_SYNC: "2026-10-02T09:00",
          ConfigKeys.RECEITA_PREVISTA: "6200"}


def _ler(aba):
    def f():
        df = TABELAS.get(aba)
        return (df if df is not None else vazia(aba)).copy()
    return f


def _load_tx():
    df = _ler("financeiro")()
    df["Data_DT"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Mes_Ano"] = df["Data_DT"].dt.strftime("%m/%Y")
    return df


for nome, aba in [("load_credit_card", "cartao"), ("load_cards", "cartoes"),
                  ("load_bank_bills", "faturas_banco"), ("load_positions", "posicao_real"),
                  ("load_categories", "categorias"), ("load_budgets", "orcamentos"),
                  ("load_fixed_costs", "custos_fixos"), ("load_imports", "importacoes"),
                  ("load_card_payments", "cartao_pagamentos"), ("load_assets", "investimentos"),
                  ("load_asset_moves", "investimento_movimentacoes"),
                  ("load_asset_snapshots", "posicao_ativos"),
                  ("load_investment_positions", "posicao_investimentos"),
                  ("load_investment_allocation", "alocacao_investimentos")]:
    setattr(repository, nome, _ler(aba))
repository.load_transactions = _load_tx
repository.load_config_text = lambda k, d="": CONFIG.get(k, d)
repository.load_config = lambda k, d=0.0: float(CONFIG.get(k, d) or d)
repository.save_config_text = lambda k, v: CONFIG.__setitem__(k, v)
for n in [m for m in dir(repository) if m.startswith("save_")] + ["append_position"]:
    if n != "save_config_text":
        setattr(repository, n, lambda *a, **k: None)
auth.is_logged_in = lambda: True
pluggy.is_configured = lambda: False

import streamlit as st  # noqa: E402
st.session_state.setdefault("tema", TEMA)
st.session_state.setdefault("nav", PAGINA)

sys.argv = ["app"]
import app  # noqa: E402
app.main()
