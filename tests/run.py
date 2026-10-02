"""Verificações da matemática do dinheiro.

Roda sem pytest e sem rede:

    python tests/run.py

Só exercita os módulos puros (`credit_card`, `card_book`, `finance`,
`dates`), que é
onde mora o dinheiro. As páginas dependem de streamlit e plotly e não
entram aqui de propósito: o objetivo é poder rodar isto em qualquer
lugar, inclusive antes de um commit.

Cada bloco corresponde a um defeito que já aconteceu de verdade neste
app. O comentário diz qual, para ninguém "simplificar" o teste sem saber
o que está desfazendo.
"""
from __future__ import annotations

import os
import sys
import types
from datetime import date, timedelta

# streamlit é importado indiretamente por alguns módulos; stub antes de tudo.
if "streamlit" not in sys.modules:
    _st = types.ModuleType("streamlit")
    _st.cache_data = lambda *a, **k: (lambda f: f)
    _st.cache_resource = lambda *a, **k: (lambda f: f)
    _st.secrets = {}
    sys.modules["streamlit"] = _st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from src import card_book as cb  # noqa: E402
from src import credit_card as cc  # noqa: E402
from src.dates import parse_dates, parse_month_label  # noqa: E402
from src.finance import (  # noqa: E402
    avg_monthly_expense, fixed_costs_split, projection_target,
)
from tests.fixture import (  # noqa: E402
    CARDS, ESPERADO_OUTUBRO, HOJE, MOSTRAVA_ANTES, TX,
)

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


def section(title):
    print(f"  {title}")


def livros(tx=TX, cards=CARDS, hoje=HOJE, bills=None):
    return cb.build(compras=tx, df_bills=bills if bills is not None
                    else pd.DataFrame(), df_cards=cards, today=hoje)


def total_em(mes, tx=TX, cards=CARDS, hoje=HOJE):
    """O que sai da conta no mês: faturas não pagas que vencem nele."""
    ini = parse_month_label(mes)
    if ini is None:
        return 0.0
    fim = (ini + pd.offsets.MonthEnd(0)).date()
    return round(sum(
        f.total for c in livros(tx, cards, hoje) for f in c.faturas
        if f.situacao != cb.PAGA and ini.date() <= f.vencimento <= fim), 2)


def chaves(faturas):
    return sorted((f.cartao, f.mes) for f in faturas)


# ---------------------------------------------------------------------------
# A convenção: a fatura leva o nome do mês em que FECHA.
# Confirmado contra o banco do usuário: a fatura que fecha em 08/10 é a
# que o Nubank chama de "Outubro".
# ---------------------------------------------------------------------------
section("Mês da fatura vem do fechamento, não da abertura")


def inv(d, c):
    return cc.invoice_month_for_purchase(d, c).strftime("%m/%Y")


check("22/08 com fechamento 30 -> 08/2026", inv(date(2026, 8, 22), 30), "08/2026")
check("30/08 (dia do fechamento) -> 08/2026", inv(date(2026, 8, 30), 30), "08/2026")
check("31/08 já perdeu o fechamento", inv(date(2026, 8, 31), 30), "09/2026")
check("31/12 vira o ano", inv(date(2026, 12, 31), 30), "01/2027")
check("08/09 com fechamento 8 -> 09/2026", inv(date(2026, 9, 8), 8), "09/2026")
check("09/09 já é a seguinte", inv(date(2026, 9, 9), 8), "10/2026")
check("30/06 com fechamento 31 (mês curto)", inv(date(2026, 6, 30), 31), "06/2026")


# ---------------------------------------------------------------------------
# O vencimento é sempre depois do fechamento. Comparar as datas já
# cortadas pelo tamanho do mês fazia fechamento 30 / vencimento 31
# empatar em abril: abril ficava sem fatura e maio com duas.
# ---------------------------------------------------------------------------
section("Fechamento e vencimento no calendário")

check("Itaú: fatura 08/2026 fecha 30/08 e vence 07/09",
      "{:%d/%m/%Y}|{:%d/%m/%Y}".format(*cc.invoice_dates("08/2026", 30, 7)),
      "30/08/2026|07/09/2026")
check("virada de ano", "{:%d/%m/%Y}".format(cc.invoice_dates("12/2026", 30, 7)[1]),
      "07/01/2027")
check("fevereiro curto", "{:%d/%m/%Y}".format(cc.invoice_dates("02/2027", 30, 7)[0]),
      "28/02/2027")
check("Principal: fecha e vence no mesmo mês",
      "{:%d/%m/%Y}|{:%d/%m/%Y}".format(*cc.invoice_dates("09/2026", 8, 15)),
      "08/09/2026|15/09/2026")

check("fecha 30 / vence 31: cada fatura no seu mês",
      [cc.invoice_dates(f"{m:02d}/2026", 30, 31)[1].strftime("%m/%Y")
       for m in range(1, 13)],
      [f"{m:02d}/2026" for m in range(1, 13)])

_bad = next(
    (f"fech={c} venc={v} {m}"
     for c in range(1, 32) for v in range(1, 32)
     for m in ("02/2026", "02/2028", "04/2026", "12/2026")
     if not cc.invoice_dates(m, c, v)[1] > cc.invoice_dates(m, c, v)[0]),
    None,
)
check("vencimento sempre depois do fechamento, em 31x31 pares", _bad, None)

_fora = None
for c in (1, 6, 30, 31):
    d = date(2026, 1, 1)
    while d <= date(2026, 12, 31):
        m = cc.invoice_month_for_purchase(d, c).strftime("%m/%Y")
        fech, _ = cc.invoice_dates(m, c, 15 if c < 15 else 7)
        anterior = parse_month_label(m) - pd.DateOffset(months=1)
        fech_ant, _ = cc.invoice_dates(f"{anterior:%m/%Y}", c,
                                       15 if c < 15 else 7)
        if not (fech_ant.date() < d <= fech.date()):
            _fora = f"fech={c} {d}"
            break
        d += timedelta(days=1)
check("toda compra cai entre o fechamento anterior e o da sua fatura",
      _fora, None)


# ---------------------------------------------------------------------------
# O caso que originou tudo: somar por rótulo de mês nunca pega os dois
# cartões, porque a fatura paga em outubro tem nome diferente em cada um.
# ---------------------------------------------------------------------------
section("Projeção: o que realmente sai da conta no mês-alvo")

check("outubro soma os dois cartões", total_em("10/2026"), ESPERADO_OUTUBRO)
check("é mais do que o rótulo 09/2026 sozinho",
      MOSTRAVA_ANTES < ESPERADO_OUTUBRO, True)

_l = livros()
check("nenhum rótulo ilegível", [c.ilegiveis for c in _l], [(), ()])
check("quais faturas vencem em outubro",
      chaves(cb.due_through(_l, date(2026, 10, 31))),
      [("Cartão Itaú", "09/2026"), ("Principal", "10/2026")])

# Cada fatura entra uma vez só, em qualquer dia do mês: entre hoje e o
# primeiro dia do alvo existia uma janela cega em que a fatura prestes a
# ser paga não aparecia — e em outra versão, aparecia duas vezes.
_dup = None
for _dia in (1, 8, 15, 18, 25, 30):
    _hoje = date(2026, 9, _dia)
    _alvo, _ = projection_target("x", today=_hoje)
    _fim = (parse_month_label(_alvo) + pd.offsets.MonthEnd(0)).date()
    _k = [(f.cartao, f.mes) for f in cb.due_through(livros(hoje=_hoje), _fim)]
    if len(_k) != len(set(_k)):
        _dup = f"duplicata em {_hoje}"
        break
check("nenhuma fatura contada duas vezes em qualquer dia do mês", _dup, None)

check("no dia 1º, a fatura do Itaú que vence dia 7 ainda entra",
      chaves(cb.due_through(livros(hoje=date(2026, 9, 1)),
                            date(2026, 9, 30))),
      [("Cartão Itaú", "08/2026"), ("Principal", "09/2026")])


# ---------------------------------------------------------------------------
# A projeção nunca olha para trás: receita prevista e custos fixos são
# valores únicos, sem vigência. Ancorar no filtro fazia uma fatura já
# vencida entrar como despesa futura.
# ---------------------------------------------------------------------------
section("Âncora da projeção")

check("mês passado", projection_target("03/2026", today=HOJE), ("10/2026", False))
check("mês corrente", projection_target("09/2026", today=HOJE), ("10/2026", False))
check("sem filtro", projection_target("Todos os Meses", today=HOJE),
      ("10/2026", False))
check("mês futuro é respeitado", projection_target("12/2026", today=HOJE),
      ("12/2026", True))
check("virada de ano", projection_target("x", today=date(2026, 12, 20)),
      ("01/2027", False))
check("com filtro no passado, a vencida continua fora",
      total_em(projection_target("08/2026", today=HOJE)[0]), ESPERADO_OUTUBRO)


# ---------------------------------------------------------------------------
# Planilha editada à mão: rótulo torto, caixa diferente, espaço sobrando.
# Cada um destes já fez dinheiro sumir ou ser cobrado duas vezes.
# ---------------------------------------------------------------------------
section("Dados sujos da planilha")

check("9/2026 sem zero à esquerda", parse_month_label("9/2026"),
      pd.Timestamp(2026, 9, 1))
check("espaços nas pontas", parse_month_label("  09/2026 "),
      pd.Timestamp(2026, 9, 1))
check("ano de 2 dígitos é recusado (virava 2001)",
      parse_month_label("09/26"), None)
check("ordem invertida é recusada", parse_month_label("2026-10"), None)
check("mês 13 é recusado", parse_month_label("13/2026"), None)
check("lixo é recusado", parse_month_label("abacaxi"), None)
for _sep in ("10 / 2026", "10-2026", "10.2026"):
    check(f"separador {_sep!r} é aceito",
          "{:%m/%Y}".format(cc.invoice_dates(_sep, 8, 15)[1]), "10/2026")

_tx_ruim = pd.concat([TX, pd.DataFrame([{
    "Data Compra": "2026-09-20", "Mês da Fatura": "09/26", "Cartão": "Principal",
    "Descrição": "Torta", "Categoria": "Lanches", "Parcela": "1/1",
    "Valor": 99.0, "Status": "Pendente"}])], ignore_index=True)
check("rótulo ilegível é reportado em vez de sumir calado",
      [c.ilegiveis for c in livros(tx=_tx_ruim) if c.nome == "Principal"],
      [("09/26",)])
check("e não contamina o total", total_em("10/2026", tx=_tx_ruim),
      ESPERADO_OUTUBRO)

_misto = pd.DataFrame([
    {"Status": "Pago"}, {"Status": "pago"}, {"Status": " PAGO "},
    {"Status": "Pendente"}, {"Status": None},
])
check("'pago' em qualquer grafia conta como quitado",
      list(cc._is_settled(_misto)), [True, True, True, False, False])

_dupmes = pd.DataFrame([
    {"Data Compra": "2026-10-01", "Mês da Fatura": " 11/2026", "Cartão": "Principal",
     "Descrição": "a", "Categoria": "x", "Parcela": "1/1", "Valor": 150.0,
     "Status": "Pendente"},
    {"Data Compra": "2026-10-02", "Mês da Fatura": "11/2026", "Cartão": "Principal",
     "Descrição": "b", "Categoria": "x", "Parcela": "1/1", "Valor": 0.0,
     "Status": "Pendente"},
])
_nov = [f for c in livros(tx=_dupmes) for f in c.faturas if f.mes == "11/2026"]
check("rótulo com espaço não vira duas faturas", len(_nov), 1)
check("nem dobra a dívida", total_em("11/2026", tx=_dupmes), 150.0)


# ---------------------------------------------------------------------------
# Cadastro do cartão incompleto ou inválido. card_settings preenche
# default por CAMPO, então um cartão "cadastrado" pode ter data chutada.
# ---------------------------------------------------------------------------
section("Cadastro de cartão pela metade")

_meio = pd.DataFrame([{"Nome": "Cartão Itaú", "Instituição": "Itaú",
                       "Limite": 1600.0, "Dia Fechamento": 30,
                       "Dia Vencimento": None}])
check("vencimento em branco é 'não cadastrado'",
      cc.has_registered_dates(_meio, "Cartão Itaú"), False)
check("cadastro completo passa",
      cc.has_registered_dates(CARDS, "Cartão Itaú"), True)
check("cartão inexistente", cc.has_registered_dates(CARDS, "Fantasma"), False)

for _dia in (0, -3, 32, 99):
    _ruim = pd.DataFrame([
        {"Nome": "Cartão Itaú", "Instituição": "Itaú", "Limite": 1600.0,
         "Dia Fechamento": _dia, "Dia Vencimento": 7},
        {"Nome": "Principal", "Instituição": "", "Limite": 5000.0,
         "Dia Fechamento": 8, "Dia Vencimento": 15},
    ])
    _lr = {c.nome: c for c in livros(cards=_ruim)}
    check(f"dia {_dia}: não vira 'mês ilegível'",
          [c.ilegiveis for c in _lr.values()], [(), ()])
    check(f"dia {_dia}: cartão marcado como estimado",
          sorted(n for n, c in _lr.items() if c.datas_estimadas),
          ["Cartão Itaú"])
    check(f"dia {_dia}: nenhuma fatura some",
          total_em("10/2026", cards=_ruim), ESPERADO_OUTUBRO)


# ---------------------------------------------------------------------------
# Dupla contagem: a fatura já entra por conta própria na projeção.
# ---------------------------------------------------------------------------
section("Custo fixo e gasto variável não descontam a fatura de novo")

_fx = pd.DataFrame([
    {"Descrição": "Aluguel", "Categoria": "Aluguel", "Valor": 1500.0},
    {"Descrição": "Fatura Cartão Itaú", "Categoria": "Cartão de Crédito",
     "Valor": 800.0},
    {"Descrição": "Fatura Nubank", "Categoria": "Cartao de Credito",
     "Valor": 300.0},
])
check("exclui só o cartão que vence no mês",
      fixed_costs_split(_fx, {"Cartão Itaú"}), (1800.0, 800.0))
check("os dois vencendo", fixed_costs_split(_fx, {"Cartão Itaú", "Nubank"}),
      (1500.0, 1100.0))
check("sem fatura no mês, nada é excluído",
      fixed_costs_split(_fx, set()), (2600.0, 0.0))
check("sem custos fixos", fixed_costs_split(pd.DataFrame(), {"x"}), (0.0, 0.0))

for _grafia in ("Cartão de Crédito", "Cartao de Credito", "cartao de credito",
                "CARTÃO DE CRÉDITO", " Cartões de Crédito "):
    check(f"grafia {_grafia!r} é reconhecida",
          fixed_costs_split(
              pd.DataFrame([{"Descrição": "Fatura", "Categoria": _grafia,
                             "Valor": 500.0}]), {"Principal"}),
          (0.0, 500.0))

_txv = pd.DataFrame([
    {"Data": "2026-08-10", "Descrição": "Mercado", "Categoria": "Supermercado",
     "Valor": 800.0, "Tipo": "Saída"},
    {"Data": "2026-08-16", "Descrição": "Fatura", "Categoria": "Cartão de Crédito",
     "Valor": 450.0, "Tipo": "Saída"},
])
check("o pagamento de fatura sai da média variável",
      round(avg_monthly_expense(_txv, months=6)
            - avg_monthly_expense(_txv, months=6, exclude_card_invoices=True), 2),
      75.0)
check("mas o default não muda (reserva de emergência conta tudo)",
      round(avg_monthly_expense(_txv, months=6), 2), round(1250.0 / 6, 2))


# A projeção do próximo mês parte do dinheiro que existe hoje e tira
# tudo que vence até lá. Fatura que já venceu NÃO entra: o app não vê o
# pagamento, e toda vez que tratou fatura vencida como dívida estava
# errado — o banco não cobrava mais. Se uma fatura de fato ficou para
# trás, é o limite em uso informado pelo banco que acusa (ver run_book).
section("Tudo que sai da conta até o fim do mês-alvo")
_l30 = livros(hoje=date(2026, 9, 30))
_ate = cb.due_through(_l30, date(2026, 10, 31))
check("a deste mês e a do alvo; a vencida não",
      chaves(_ate), [("Cartão Itaú", "09/2026"), ("Principal", "10/2026")])
check("soma", round(sum(f.total for f in _ate), 2), ESPERADO_OUTUBRO)
check("não alcança o mês seguinte ao alvo",
      chaves(cb.due_through(_l30, date(2026, 9, 30))), [])


# A Pluggy envia "2026-09-08T00:00:00.000Z" e a planilha envia
# "2026-09-08". Misturar os dois estourava com "Cannot compare tz-naive
# and tz-aware", e inferir um formato do primeiro valor fazia o outro
# virar NaT — a fatura sumia por causa do fuso.
section("Datas do banco e da planilha convivem")
_mix = parse_dates(pd.Series([
    "2026-09-08T00:00:00.000Z", "2026-09-08", "08/09/2026",
    "2026-09-08T12:30:00-03:00", "2026-2-3", None, "lixo",
]))
check("com fuso Z", _mix.iloc[0], pd.Timestamp(2026, 9, 8))
check("ISO simples ao lado do com fuso", _mix.iloc[1], pd.Timestamp(2026, 9, 8))
check("brasileiro na mesma leva", _mix.iloc[2], pd.Timestamp(2026, 9, 8))
check("fuso negativo vira hora UTC",
      _mix.iloc[3], pd.Timestamp(2026, 9, 8, 15, 30))
check("sem zero à esquerda", _mix.iloc[4], pd.Timestamp(2026, 2, 3))
check("nulo e lixo viram NaT",
      [bool(pd.isna(v)) for v in _mix.iloc[5:]], [True, True])


# São os estados que o app do cartão mostra. "Aberta" para tudo
# escondia a diferença entre dever agora e dever em 2027.
section("Faturas classificadas como o banco classifica")
_c = {c.nome: c for c in livros(hoje=date(2026, 9, 30))}
_sit = {f.mes: f.situacao for f in _c["Cartão Itaú"].faturas}
check("a que passou do vencimento está paga", _sit["08/2026"], cb.PAGA)
check("a que fecha hoje ainda é a aberta", _sit["09/2026"], cb.ABERTA)
check("as seguintes são futuras",
      {_sit[m] for m in ("10/2026", "11/2026", "12/2026", "01/2027")},
      {cb.FUTURA})
check("cada cartão tem a sua aberta",
      sorted((n, c.atual.mes) for n, c in _c.items()),
      [("Cartão Itaú", "09/2026"), ("Principal", "10/2026")])
check("no dia seguinte ao fechamento, ela vira 'a pagar'",
      [f.mes for f in {c.nome: c for c in livros(
          hoje=date(2026, 10, 1))}["Cartão Itaú"].a_pagar], ["09/2026"])

section("Carteira vazia e meses sem fatura")
check("mês sem nada", total_em("07/2027"), 0.0)
check("sem compras", total_em("10/2026", tx=TX.iloc[0:0]), 0.0)
check("compras sem cartão preenchido caem no padrão",
      int((cc.card_series(TX.assign(**{"Cartão": None})) == "Principal").sum()),
      len(TX))


print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
