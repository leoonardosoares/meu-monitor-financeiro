"""Verificações da matemática do dinheiro.

Roda sem pytest e sem rede:

    python tests/run.py

Só exercita os módulos puros (`credit_card`, `finance`, `dates`), que é
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

from src import credit_card as cc  # noqa: E402
from src.dates import parse_month_label  # noqa: E402
from src.finance import (  # noqa: E402
    avg_monthly_expense, fixed_costs_split, projection_target,
)
from tests.fixture import (  # noqa: E402
    CARDS, ESPERADO_OUTUBRO, HOJE, MOSTRAVA_ANTES, PAY, TX,
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


def total_em(mes, tx=TX, pay=PAY, cards=CARDS, hoje=HOJE):
    ag, _ = cc.schedule_invoices(tx, pay, cards, today=hoje)
    return round(sum(i.balance for i in cc.invoices_due_in(ag, mes)), 2)


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

check("parcelamento parte da fatura certa",
      [l["Mês da Fatura"] for l in cc.installments_for_purchase(
          purchase_date=date(2026, 8, 22), description="x", category="y",
          total_amount=1600.0, installments=6, closing_day=30)],
      ["08/2026", "09/2026", "10/2026", "11/2026", "12/2026", "01/2027"])


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

_gap = None
for c in (1, 6, 15, 28, 30, 31):
    fim_anterior = None
    for m in [f"{x:02d}/2026" for x in range(1, 13)]:
        ini, fim = cc.invoice_window(m, c)
        if fim_anterior is not None and ini != fim_anterior + timedelta(days=1):
            _gap = f"fech={c} em {m}"
            break
        fim_anterior = fim
check("as janelas ladrilham o calendário sem buraco nem sobreposição", _gap, None)

_fora = None
for c in (1, 6, 30, 31):
    d = date(2026, 1, 1)
    while d <= date(2026, 12, 31):
        m = cc.invoice_month_for_purchase(d, c).strftime("%m/%Y")
        ini, fim = cc.invoice_window(m, c)
        if not ini.date() <= d <= fim.date():
            _fora = f"fech={c} {d}"
            break
        d += timedelta(days=1)
check("toda data cai em exatamente uma janela", _fora, None)

check("fecha 30 vence 7: 'Fechada' na virada do mês",
      cc.invoice_phase(pd.Timestamp("2026-09-05"), 30, 7), "Fechada")
check("e 'Aberta' no meio do ciclo",
      cc.invoice_phase(pd.Timestamp("2026-09-20"), 30, 7), "Aberta")


# ---------------------------------------------------------------------------
# O caso que originou tudo: somar por rótulo de mês nunca pega os dois
# cartões, porque a fatura paga em outubro tem nome diferente em cada um.
# ---------------------------------------------------------------------------
section("Projeção: o que realmente sai da conta no mês-alvo")

check("outubro soma os dois cartões", total_em("10/2026"), ESPERADO_OUTUBRO)
check("é mais do que o rótulo 09/2026 sozinho",
      MOSTRAVA_ANTES < ESPERADO_OUTUBRO, True)

_ag, _ileg = cc.schedule_invoices(TX, PAY, CARDS, today=HOJE)
check("nenhum rótulo ilegível", _ileg, [])
check("quais faturas vencem em outubro",
      sorted((i.card, i.month) for i in cc.invoices_due_in(_ag, "10/2026")),
      [("Cartão Itaú", "09/2026"), ("Principal", "10/2026")])
check("a vencida fica de fora, mas é reportada",
      [(i.card, i.month, i.balance) for i in cc.overdue_invoices(_ag)],
      [("Cartão Itaú", "08/2026", 266.67)])

# Os três baldes precisam particionar o que está em aberto: nada some,
# nada é contado duas vezes. Entre hoje e o primeiro dia do alvo existia
# uma janela cega em que a fatura prestes a ser paga não aparecia.
_dup = None
for _dia in (1, 8, 15, 18, 25, 30):
    _hoje = date(2026, 9, _dia)
    _a, _ = cc.schedule_invoices(TX, PAY, CARDS, today=_hoje)
    _alvo, _ = projection_target("x", today=_hoje)
    _b = (cc.overdue_invoices(_a) + cc.invoices_due_before(_a, _alvo)
          + cc.invoices_due_in(_a, _alvo))
    _k = [(i.card, i.month) for i in _b]
    if len(_k) != len(set(_k)):
        _dup = f"duplicata em {_hoje}"
        break
check("baldes disjuntos em qualquer dia do mês", _dup, None)

check("a fatura que vence antes do alvo não some",
      [(i.card, i.month) for i in cc.invoices_due_before(
          cc.schedule_invoices(TX, PAY, CARDS, today=date(2026, 9, 1))[0],
          "10/2026")],
      [("Cartão Itaú", "08/2026")])


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
      cc.schedule_invoices(_tx_ruim, PAY, CARDS, today=HOJE)[1],
      ["Principal · 09/26"])
check("e não contamina o total", total_em("10/2026", tx=_tx_ruim),
      ESPERADO_OUTUBRO)

_misto = pd.DataFrame([
    {"Data Compra": "2026-10-01", "Mês da Fatura": "10/2026", "Cartão": "Principal",
     "Descrição": "a", "Categoria": "x", "Parcela": "1/1", "Valor": 100.0,
     "Status": "Pago"},
    {"Data Compra": "2026-10-02", "Mês da Fatura": "10/2026", "Cartão": "Principal",
     "Descrição": "b", "Categoria": "x", "Parcela": "1/1", "Valor": 50.0,
     "Status": "pago"},
    {"Data Compra": "2026-10-03", "Mês da Fatura": "10/2026", "Cartão": "Principal",
     "Descrição": "c", "Categoria": "x", "Parcela": "1/1", "Valor": 30.0,
     "Status": "Pendente"},
])
_i = cc.invoice_for(_misto, PAY, "Principal", "10/2026")
check("'pago' minúsculo conta como quitado", (_i.settled, _i.outstanding),
      (150.0, 30.0))

_dupmes = pd.DataFrame([
    {"Data Compra": "2026-10-01", "Mês da Fatura": " 11/2026", "Cartão": "Principal",
     "Descrição": "a", "Categoria": "x", "Parcela": "1/1", "Valor": 150.0,
     "Status": "Pendente"},
    {"Data Compra": "2026-10-02", "Mês da Fatura": "11/2026", "Cartão": "Principal",
     "Descrição": "b", "Categoria": "x", "Parcela": "1/1", "Valor": 0.0,
     "Status": "Pendente"},
])
check("rótulo com espaço não vira duas faturas",
      len(cc.open_invoices(_dupmes, PAY)), 1)
check("nem dobra a dívida", total_em("11/2026", tx=_dupmes), 150.0)

for _rot in ("10/2026", " 10/2026 ", "10 /2026", "10-2026"):
    _p = pd.DataFrame([{"Data": "2026-09-20", "Cartão": "Principal",
                        "Mês da Fatura": _rot, "Valor": 22.0, "Observação": "x"}])
    check(f"adiantamento com rótulo {_rot!r} encontra a fatura",
          round(cc.invoice_for(TX, _p, "Principal", "10/2026").advances, 2), 22.0)


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
    _a, _il = cc.schedule_invoices(TX, PAY, _ruim, today=HOJE)
    check(f"dia {_dia}: não vira 'mês ilegível'", _il, [])
    check(f"dia {_dia}: cartão marcado como estimado",
          sorted({i.card for i in _a if i.estimated}), ["Cartão Itaú"])
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


# ---------------------------------------------------------------------------
# Adiantamento: sai do caixa na hora e é absorvido na baixa, para o
# dinheiro não ser contado duas vezes.
# ---------------------------------------------------------------------------
section("Pagamento parcial de fatura")

_pay1 = pd.DataFrame([{"Data": "2026-09-20", "Cartão": "Principal",
                       "Mês da Fatura": "10/2026", "Valor": 49.20,
                       "Observação": "liberar limite"}])
check("abate do mês", total_em("10/2026", pay=_pay1),
      round(ESPERADO_OUTUBRO - 49.20, 2))
_p = [i for i in cc.schedule_invoices(TX, _pay1, CARDS, today=HOJE)[0]
      if i.card == "Principal"][0]
check("total - quitado - adiantado = falta pagar",
      round(_p.total - _p.settled - _p.advances, 2), round(_p.balance, 2))

_tx2, _pay2, _caixa = cc.settle_invoice(TX, _pay1, "Principal", "10/2026")
check("na baixa, só o saldo vai para o caixa", round(_caixa, 2),
      round(149.20 - 49.20, 2))
check("e o adiantamento é absorvido", len(_pay2), 0)
check("as parcelas viram Pago",
      total_em("10/2026", tx=_tx2, pay=_pay2),
      round(ESPERADO_OUTUBRO - 149.20, 2))


# ---------------------------------------------------------------------------
# Recálculo do mês gravado, depois de corrigir o dia de fechamento.
# ---------------------------------------------------------------------------
section("Recálculo das faturas já gravadas")

check("com o cadastro certo, nada a corrigir",
      len(cc.invoice_month_drift(TX, CARDS, "Cartão Itaú")), 0)
_c1 = pd.DataFrame([{"Nome": "Cartão Itaú", "Instituição": "Itaú",
                     "Limite": 1600.0, "Dia Fechamento": 1,
                     "Dia Vencimento": 7}])
_d = cc.invoice_month_drift(TX, _c1, "Cartão Itaú")
check("fechamento errado denuncia as 6 parcelas", len(_d), 6)
_tx3, _pay3 = cc.apply_invoice_month_drift(TX, PAY, "Cartão Itaú", _d)
check("aplicar é idempotente",
      len(cc.invoice_month_drift(_tx3, _c1, "Cartão Itaú")), 0)
_pago = TX.copy()
_pago["Status"] = "Pago"
check("fatura paga não é remexida sem opt-in",
      len(cc.invoice_month_drift(_pago, _c1, "Cartão Itaú")), 0)
check("com opt-in, é",
      len(cc.invoice_month_drift(_pago, _c1, "Cartão Itaú",
                                 only_pending=False)), 6)


# A projeção do próximo mês parte do dinheiro que existe hoje e tira
# tudo que vence até lá — incluindo o que já venceu e não foi pago, que
# sai da mesma conta.
section("Tudo que sai da conta até o fim do mês-alvo")
_ag, _ = cc.schedule_invoices(TX, PAY, CARDS, today=date(2026, 9, 30))
_ate = cc.invoices_due_through(_ag, "10/2026")
check("inclui a vencida, a deste mês e a do alvo",
      [(i.card, i.month) for i in _ate],
      [("Cartão Itaú", "08/2026"), ("Cartão Itaú", "09/2026"),
       ("Principal", "10/2026")])
check("soma", round(sum(i.balance for i in _ate), 2), 682.54)
check("não alcança o mês seguinte ao alvo",
      [(i.card, i.month) for i in cc.invoices_due_through(_ag, "09/2026")],
      [("Cartão Itaú", "08/2026")])
check("mês ilegível devolve vazio", cc.invoices_due_through(_ag, "lixo"), [])

# O balde do alvo é subconjunto do que sai até lá: quem some de um tem
# de aparecer no outro.
_no_alvo = {(i.card, i.month) for i in cc.invoices_due_in(_ag, "10/2026")}
_ate_chaves = {(i.card, i.month) for i in _ate}
check("o que vence no alvo está contido no que sai até lá",
      _no_alvo <= _ate_chaves, True)
check("e a vencida entra só no segundo",
      ("Cartão Itaú", "08/2026") in _ate_chaves - _no_alvo, True)

# São os estados que o app do cartão mostra. "Aberta" para tudo
# escondia a diferença entre dever agora e dever em 2027.
section("Faturas classificadas como o banco classifica")
_hoje = date(2026, 9, 30)
_ag2, _ = cc.schedule_invoices(TX, PAY, CARDS, today=_hoje)
_sit = cc.situations(_ag2, _hoje)
check("a que passou do vencimento", _sit[("Cartão Itaú", "08/2026")],
      "Vencida")
check("a que ainda não fechou", _sit[("Cartão Itaú", "09/2026")], "Atual")
check("as seguintes são futuras",
      {_sit[("Cartão Itaú", m)] for m in
       ("10/2026", "11/2026", "12/2026", "01/2027")}, {"Futura"})
check("cada cartão tem a sua atual", _sit[("Principal", "10/2026")], "Atual")

# Uma fatura atual por cartão: sem olhar a sequência, toda parcela dos
# próximos meses passaria por atual.
_atuais = [k for k, v in _sit.items() if v == "Atual"]
check("uma por cartão", sorted(c for c, _ in _atuais),
      ["Cartão Itaú", "Principal"])

# Fatura ainda não baixada, mas já coberta por adiantamento: o saldo
# zera e ela deixa de ser cobrança.
_adiantada = pd.DataFrame([{
    "Data": "2026-09-20", "Cartão": "Principal", "Mês da Fatura": "10/2026",
    "Valor": 149.20, "Observação": "quitou antes do fechamento"}])
_ag3, _ = cc.schedule_invoices(TX, _adiantada, CARDS, today=_hoje)
check("coberta por adiantamento aparece como paga",
      cc.situations(_ag3, _hoje).get(("Principal", "10/2026")), "Paga")

# Uma fatura totalmente quitada não chega a aparecer: `open_invoices`
# só devolve pares com parcela em aberto.
_paga = TX.copy()
_paga.loc[_paga["Cartão"] == "Principal", "Status"] = "Pago"
_ag4, _ = cc.schedule_invoices(_paga, PAY, CARDS, today=_hoje)
check("quitada some da lista",
      ("Principal", "10/2026") in cc.situations(_ag4, _hoje), False)
check("sem faturas", cc.situations([], _hoje), {})

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
