"""As páginas desenham sem quebrar.

    python tests/run_render.py

Existe por causa de dois defeitos que chegaram em produção: uma função
apagada por engano, que só apareceu como `NameError` quando o usuário
abriu a aba, e um `st.subheader` trocado por um componente com assinatura
diferente. `compileall` passa nos dois casos; o pyflakes pega o primeiro
e não o segundo. O que pega os dois é chamar `render()`.

O Streamlit aqui é um dublê: registra o que foi pedido e devolve valores
plausíveis. Não valida aparência — valida que o caminho do código roda de
ponta a ponta, nos dois temas, com planilha vazia e com dados.
"""
from __future__ import annotations

import os
import sys
import types
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# O dublê do Streamlit
# ---------------------------------------------------------------------------

class _Ctx:
    """Serve de coluna, aba, expander, container e formulário."""

    def __init__(self, registro: list):
        self._registro = registro

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __getattr__(self, nome):
        def _chamada(*a, **k):
            self._registro.append(nome)
            return _RETORNOS.get(nome, lambda *_a, **_k: None)(*a, **k)
        return _chamada


def _colunas(spec, **_k):
    quantas = spec if isinstance(spec, int) else len(spec)
    return [_Ctx(CHAMADAS) for _ in range(quantas)]


def _abas(rotulos, **_k):
    # Toda aba é entrada: o defeito que se procura está dentro da aba que
    # ninguém abriu.
    return [_Ctx(CHAMADAS) for _ in rotulos]


def _editor(df=None, *a, **k):
    return df if df is not None else pd.DataFrame()


_RETORNOS = {
    "columns": _colunas,
    "tabs": _abas,
    "expander": lambda *a, **k: _Ctx(CHAMADAS),
    "container": lambda *a, **k: _Ctx(CHAMADAS),
    "form": lambda *a, **k: _Ctx(CHAMADAS),
    "sidebar": lambda *a, **k: _Ctx(CHAMADAS),
    "button": lambda *a, **k: False,
    "form_submit_button": lambda *a, **k: False,
    "download_button": lambda *a, **k: False,
    "checkbox": lambda *a, **k: False,
    "toggle": lambda *a, **k: False,
    "text_input": lambda *a, **k: "",
    "text_area": lambda *a, **k: "",
    "number_input": lambda *a, **k: k.get("value", 0) or 0,
    "date_input": lambda *a, **k: k.get("value") or date(2026, 9, 30),
    "selectbox": lambda rotulo=None, opcoes=(), *a, **k: (
        list(opcoes)[k.get("index", 0)] if len(list(opcoes)) else None),
    "radio": lambda rotulo=None, opcoes=(), *a, **k: (
        list(opcoes)[0] if len(list(opcoes)) else None),
    "multiselect": lambda *a, **k: [],
    "slider": lambda *a, **k: k.get("value", 0),
    "data_editor": _editor,
    "file_uploader": lambda *a, **k: None,
    "spinner": lambda *a, **k: _Ctx(CHAMADAS),
    "empty": lambda *a, **k: _Ctx(CHAMADAS),
}

CHAMADAS: list[str] = []


class _Secrets(dict):
    def __getattr__(self, _nome):
        raise KeyError("sem secrets no teste")


def _monta_streamlit() -> types.ModuleType:
    st = types.ModuleType("streamlit")
    st.cache_data = st.cache_resource = lambda *a, **k: (lambda f: f)
    st.secrets = _Secrets()
    st.session_state = {}
    st.set_page_config = lambda *a, **k: None
    st.stop = lambda: (_ for _ in ()).throw(_Parou())
    st.rerun = lambda *a, **k: (_ for _ in ()).throw(_Parou())
    st.column_config = types.SimpleNamespace(
        TextColumn=lambda *a, **k: None, NumberColumn=lambda *a, **k: None,
        SelectboxColumn=lambda *a, **k: None, DateColumn=lambda *a, **k: None,
        CheckboxColumn=lambda *a, **k: None,
    )

    for nome, funcao in _RETORNOS.items():
        setattr(st, nome, _grava(nome, funcao))
    for nome in ("write", "markdown", "caption", "metric", "dataframe",
                 "plotly_chart", "info", "warning", "error", "success",
                 "divider", "subheader", "header", "title", "progress",
                 "json", "code", "table", "image", "altair_chart",
                 "bar_chart", "line_chart", "area_chart", "link_button",
                 "badge", "html", "latex", "pyplot", "map", "toast",
                 "balloons", "snow", "audio", "video", "switch_page"):
        setattr(st, nome, _grava(nome, lambda *a, **k: None))

    componentes = types.ModuleType("streamlit.components")
    v1 = types.ModuleType("streamlit.components.v1")
    v1.html = _grava("components.html", lambda *a, **k: None)
    v1.iframe = _grava("components.iframe", lambda *a, **k: None)
    componentes.v1 = v1
    st.components = componentes
    sys.modules["streamlit.components"] = componentes
    sys.modules["streamlit.components.v1"] = v1
    return st


def _grava(nome, funcao):
    def _dentro(*a, **k):
        CHAMADAS.append(nome)
        return funcao(*a, **k)
    return _dentro


class _Parou(Exception):
    """`st.stop()` e `st.rerun()` cortam o script no Streamlit real."""


sys.modules["streamlit"] = _monta_streamlit()

# O acesso ao Google não é o que se testa aqui, e importar o de verdade
# exigiria credencial: o repositório é trocado por tabelas em memória
# logo abaixo, então o cliente só precisa existir para o import passar.
for _mod in ("gspread", "gspread.worksheet", "oauth2client",
             "oauth2client.service_account"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))
sys.modules["gspread"].worksheet = sys.modules["gspread.worksheet"]
sys.modules["gspread.worksheet"].Worksheet = object
sys.modules["oauth2client"].service_account = \
    sys.modules["oauth2client.service_account"]
sys.modules["oauth2client.service_account"].ServiceAccountCredentials = object

from src import components, repository  # noqa: E402
from src.config import (ConfigKeys, PALETTES,  # noqa: E402
                        SHEETS_SCHEMA)
from src.finance import filter_by_month  # noqa: E402
from src.pages import (  # noqa: E402
    credit_card as pg_cartao, dashboard as pg_painel,
    import_page as pg_import, investments as pg_inv,
    settings as pg_config, transactions as pg_tx,
)

_ok = 0
_fail: list[str] = []


def check(label, condicao):
    global _ok
    if condicao:
        _ok += 1
    else:
        _fail.append(label)


# ---------------------------------------------------------------------------
# A planilha, também dublada
# ---------------------------------------------------------------------------

def _vazia(aba: str) -> pd.DataFrame:
    return pd.DataFrame(columns=SHEETS_SCHEMA[aba])


def _dados_cartao() -> pd.DataFrame:
    """Um parcelamento em curso, uma compra à vista e uma fatura paga."""
    return pd.DataFrame([
        {"Data Compra": "2026-09-10", "Mês da Fatura": "09/2026",
         "Cartão": "Nubank", "Descrição": "Mercado", "Categoria": "Supermercado",
         "Parcela": "", "Valor": 320.5, "Status": "Pendente",
         "ID Pluggy": "a1", "Origem": "banco"},
        {"Data Compra": "2026-08-22", "Mês da Fatura": "09/2026",
         "Cartão": "Nubank", "Descrição": "Notebook", "Categoria": "Outros",
         "Parcela": "2/10", "Valor": 235.29, "Status": "Pendente",
         "ID Pluggy": "a2", "Origem": "banco"},
        {"Data Compra": "2026-08-22", "Mês da Fatura": "10/2026",
         "Cartão": "Nubank", "Descrição": "Notebook", "Categoria": "Outros",
         "Parcela": "3/10", "Valor": 235.29, "Status": "Pendente",
         "ID Pluggy": "a3", "Origem": "banco"},
        {"Data Compra": "2026-07-15", "Mês da Fatura": "08/2026",
         "Cartão": "Itaú", "Descrição": "Farmácia", "Categoria": "Saúde",
         "Parcela": "", "Valor": 89.9, "Status": "Paga",
         "ID Pluggy": "a4", "Origem": "banco"},
    ])


def _dados_financeiro() -> pd.DataFrame:
    return pd.DataFrame([
        {"Data": "2026-09-05", "Descrição": "Salário",
         "Categoria": "Receita/Salário", "Valor": 6000.0, "Tipo": "Entrada"},
        {"Data": "2026-09-08", "Descrição": "Aluguel",
         "Categoria": "Aluguel", "Valor": 1800.0, "Tipo": "Saída"},
        {"Data": "2026-09-12", "Descrição": "Aporte",
         "Categoria": "Investimento", "Valor": 1000.0, "Tipo": "Saída"},
        {"Data": "2026-08-05", "Descrição": "Salário",
         "Categoria": "Receita/Salário", "Valor": 6000.0, "Tipo": "Entrada"},
        {"Data": "2026-08-20", "Descrição": "Mercado",
         "Categoria": "Supermercado", "Valor": 640.0, "Tipo": "Saída"},
    ])


def _dados_cartoes() -> pd.DataFrame:
    return pd.DataFrame([
        {"Nome": "Nubank", "Instituição": "Nu Pagamentos", "Limite": 3000.0,
         "Dia Fechamento": 8, "Dia Vencimento": 15},
        {"Nome": "Itaú", "Instituição": "Itaú", "Limite": 5000.0,
         "Dia Fechamento": 30, "Dia Vencimento": 7},
    ])


def _posicao_real() -> pd.DataFrame:
    """O retrato lido das instituições: conta, cartão e investimento.

    Sem ele, `_saldo_do_banco()` devolve vazio e metade da tela do cartão
    — justamente a metade que consulta o banco — nunca roda no teste.
    """
    quando = "2026-09-30T09:00"
    return pd.DataFrame([
        {"Data": quando, "Origem": "Itaú", "Nome": "Conta corrente",
         "Classe": "BANK", "Valor": 4210.55, "Chave": "acc-itau"},
        {"Data": quando, "Origem": "Nu Pagamentos", "Nome": "Nubank",
         "Classe": "CREDIT", "Valor": -2679.04, "Chave": "acc-nu-card",
         "Limite": 3000.0, "Disponível": 320.96,
         "Fechamento": "2026-10-08", "Vencimento": "2026-10-15"},
        {"Data": quando, "Origem": "Nu Pagamentos", "Nome": "Caixinha",
         "Classe": "INVESTIMENTO", "Valor": 12350.0, "Chave": ""},
    ])


def _faturas_banco() -> pd.DataFrame:
    """Faturas como a instituição as reporta, incluindo uma já vencida."""
    return pd.DataFrame([
        {"Cartão": "Nubank", "Mês": "09/2026", "Total": 2281.47,
         "Fechamento": "2026-09-08", "Vencimento": "2026-09-15",
         "Situação": "CLOSED", "Lido em": "2026-09-30"},
        {"Cartão": "Nubank", "Mês": "10/2026", "Total": 2679.04,
         "Fechamento": "2026-10-08", "Vencimento": "2026-10-15",
         "Situação": "OPEN", "Lido em": "2026-09-30"},
    ])


def _instala_repositorio(*, com_dados: bool, com_banco: bool = False) -> None:
    """Troca cada leitura da planilha por tabela em memória."""
    tabelas = {
        "financeiro": _dados_financeiro() if com_dados else _vazia("financeiro"),
        "cartao": _dados_cartao() if com_dados else _vazia("cartao"),
        "cartoes": _dados_cartoes() if com_dados else _vazia("cartoes"),
        "posicao_real": (_posicao_real() if com_banco
                         else _vazia("posicao_real")),
        "faturas_banco": (_faturas_banco() if com_banco
                          else _vazia("faturas_banco")),
    }
    vazias = {
        "load_card_payments": "cartao_pagamentos",
        "load_categories": "categorias",
        "load_budgets": "orcamentos",
        "load_fixed_costs": "custos_fixos",
        "load_investment_positions": "posicao_investimentos",
        "load_investment_allocation": "alocacao_investimentos",
        "load_assets": "investimentos",
        "load_asset_moves": "investimento_movimentacoes",
        "load_asset_snapshots": "posicao_ativos",
        "load_imports": "importacoes",
    }
    repository.load_transactions = lambda: tabelas["financeiro"].copy()
    repository.load_credit_card = lambda: tabelas["cartao"].copy()
    repository.load_cards = lambda: tabelas["cartoes"].copy()
    repository.load_positions = lambda: tabelas["posicao_real"].copy()
    repository.load_bank_bills = lambda: tabelas["faturas_banco"].copy()
    for metodo, aba in vazias.items():
        setattr(repository, metodo,
                (lambda _aba=aba: _vazia(_aba).copy()))
    repository.load_config = lambda chave, padrao=0.0: padrao
    def _config_text(chave, padrao=""):
        if com_banco and chave == ConfigKeys.PLUGGY_MAPA:
            return "acc-nu-card=Nubank"
        if com_banco and chave == ConfigKeys.PLUGGY_ITEMS:
            return "item-1"
        return padrao
    repository.load_config_text = _config_text
    for metodo in [m for m in dir(repository) if m.startswith("save_")]:
        setattr(repository, metodo, lambda *a, **k: None)
    repository.append_position = lambda *a, **k: None
    repository.save_archive = lambda *a, **k: None


# ---------------------------------------------------------------------------
# As execuções
# ---------------------------------------------------------------------------

def _com_derivadas(df: pd.DataFrame) -> pd.DataFrame:
    """As colunas que `repository.load_transactions` sempre acrescenta.

    Reproduzi-las aqui não é detalhe: metade das páginas lê `Mes_Ano`, e
    um dublê sem ela testaria um estado que o app nunca tem.
    """
    df = df.copy()
    df["Data_DT"] = pd.to_datetime(df.get("Data"), errors="coerce")
    df["Mes_Ano"] = df["Data_DT"].dt.strftime("%m/%Y").fillna("Sem Data")
    return df


def _desenha(nome: str, funcao, **kwargs) -> None:
    """Chama o render e registra o que estourou."""
    CHAMADAS.clear()
    try:
        funcao(**kwargs)
    except _Parou:
        pass                      # st.stop()/st.rerun() são fim normal
    except Exception as erro:     # noqa: BLE001 — é o que se quer capturar
        _fail.append(f"{nome}: {type(erro).__name__}: {erro}")
        return
    check(f"{nome} desenhou algo", len(CHAMADAS) > 0)


def _roda_tudo(rotulo: str, *, com_dados: bool, mes: str,
               com_banco: bool = False) -> None:
    """Chama cada página com os mesmos argumentos que o `app.py` passa."""
    _instala_repositorio(com_dados=com_dados, com_banco=com_banco)
    df_tx = _com_derivadas(repository.load_transactions())
    df_cc = repository.load_credit_card()
    categorias = ["Outros", "Supermercado", "Aluguel"]

    # Pelo filtro de verdade, e não por um recorte próprio: é ele que
    # decide o que cada página recebe.
    df_tx_mes, df_cc_mes = filter_by_month(df_tx, df_cc, mes)

    _desenha(f"{rotulo} · dashboard", pg_painel.render,
             df_transactions=df_tx, df_credit_card=df_cc,
             df_transactions_period=df_tx_mes,
             df_credit_card_period=df_cc_mes,
             df_fixed_costs=repository.load_fixed_costs(),
             df_budgets=repository.load_budgets(),
             df_cards=repository.load_cards(),
             df_card_payments=repository.load_card_payments(),
             selected_month=mes)

    _desenha(f"{rotulo} · cartão", pg_cartao.render,
             df_credit_card=df_cc, df_credit_card_period=df_cc_mes,
             categories=categorias, selected_month=mes)

    _desenha(f"{rotulo} · entradas e saídas", pg_tx.render,
             df_transactions=df_tx, categories=categorias)

    _desenha(f"{rotulo} · investimentos", pg_inv.render,
             df_transactions=df_tx)

    _desenha(f"{rotulo} · importar", pg_import.render,
             df_transactions=df_tx, df_credit_card=df_cc,
             df_cards=repository.load_cards(), categories=categorias)

    _desenha(f"{rotulo} · configurações", pg_config.render,
             df_categories=repository.load_categories(),
             df_budgets=repository.load_budgets(),
             df_fixed_costs=repository.load_fixed_costs(),
             df_transactions_period=df_tx_mes,
             df_credit_card_period=df_cc_mes,
             categories=categorias, selected_month=mes)


# Antes de desenhar: o estado "banco" precisa realmente acionar as duas
# leituras da instituição. Se `load_positions` ou o mapa de contas saírem
# de sincronia, as funções devolvem vazio, a tela cai no caminho "soma das
# linhas" e o teste passaria sem nunca exercitar o que interessa.
print("O estado com dados do banco aciona as leituras da instituição")
_instala_repositorio(com_dados=True, com_banco=True)
from src import card_book as _cb  # noqa: E402
_livro_nu = next(c for c in _cb.load(
    df_credit_card=repository.load_credit_card(),
    df_cards=repository.load_cards()) if c.nome == "Nubank")
check("limite e disponível chegam do banco",
      (_livro_nu.limite, _livro_nu.disponivel) == (3000.0, 320.96))
check("a fatura emitida chega do banco com o total dele",
      next(f.total for f in _livro_nu.faturas if f.mes == "10/2026")
      == 2679.04)

print("Cada página desenha nos dois temas, com e sem dados")
for _tema in PALETTES:
    components.use_theme(_tema)
    print(f"  tema {_tema}")
    for _mes in ("09/2026", "Todos os Meses"):
        _roda_tudo(f"{_tema}/vazio/{_mes}", com_dados=False, mes=_mes)
        _roda_tudo(f"{_tema}/dados/{_mes}", com_dados=True, mes=_mes)
        # Com a posição e as faturas lidas do banco: é o estado real do
        # usuário, e o único em que metade da tela do cartão roda.
        _roda_tudo(f"{_tema}/banco/{_mes}", com_dados=True, mes=_mes,
                   com_banco=True)

# O componente novo tem de aceitar o que as páginas passam para ele: era
# `st.subheader(titulo)` e virou `section(titulo, sub, eyebrow=...)`.
print("  Os componentes de layout aceitam as formas usadas nas páginas")
for _args, _kwargs in [
        (("Só título",), {}),
        (("Título", "subtítulo"), {}),
        (("Título", "subtítulo"), {"eyebrow": "Seção"}),
        (("Título",), {"eyebrow": "Seção"}),
]:
    try:
        components.section(*_args, **_kwargs)
        _ok += 1
    except Exception as _e:                                  # noqa: BLE001
        _fail.append(f"section{_args}{_kwargs}: {_e}")

try:
    components.invoice_card(card="Nubank", month="10/2026", value="R$ 1,00",
                            state="Aberta", accent="#000000",
                            dates="fecha 08/10", source="do banco",
                            negative=True)
    _ok += 1
except Exception as _e:                                      # noqa: BLE001
    _fail.append(f"invoice_card: {_e}")

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
