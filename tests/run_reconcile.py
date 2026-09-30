"""Conciliação: remover duplicata e fechar a diferença que sobra.

    python tests/run_reconcile.py

São duas ferramentas para dois problemas, e usar a errada esconde o
defeito. Duplicata se apaga; diferença residual se ajusta. Os testes
aqui guardam essa distinção e a aritmética de cada uma.
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

from src import reconcile as rc  # noqa: E402
from src.config import TRANSFER_CATEGORIES  # noqa: E402
from src.finance import compute_wealth  # noqa: E402

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


def parcelas(repetir: int = 2) -> pd.DataFrame:
    """As 6 parcelas do Link de Fotos, cada uma lançada `repetir` vezes."""
    linhas = []
    for i in range(6):
        mes = 8 + i
        linha = {
            "Data Compra": "2026-08-22",
            "Mês da Fatura": f"{mes if mes < 13 else mes - 12:02d}/"
                             f"{2026 if mes < 13 else 2027}",
            "Cartão": "Cartão Itaú", "Descrição": "Link de Fotos",
            "Categoria": "Formatura", "Parcela": f"{i+1}/6",
            "Valor": 266.67, "Status": "Pendente",
        }
        linhas += [dict(linha) for _ in range(repetir)]
    return pd.DataFrame(linhas)


# O identificador da Pluggy decide o que é repetição. Sem ele, duas
# compras iguais no mesmo dia eram fundidas numa só — dinheiro de
# verdade sumindo, e a fatura ficando abaixo da do banco.
print("  O identificador separa repetição de coincidência")
_base = {"Cartão": "P", "Mês da Fatura": "10/2026", "Descrição": "Cafe",
         "Parcela": "1/1", "Valor": 5.0, "Data Compra": "2026-09-20"}


def _par(a, b):
    return pd.DataFrame([dict(_base, **{"ID Pluggy": a}),
                         dict(_base, **{"ID Pluggy": b})])


check("ids diferentes são compras diferentes",
      len(rc.duplicates(_par("a", "b"), rc.CHAVES_CARTAO)), 0)
check("o mesmo id é a mesma compra",
      len(rc.duplicates(_par("a", "a"), rc.CHAVES_CARTAO)), 1)
check("duas manuais idênticas: sobra uma",
      len(rc.duplicates(_par("", ""), rc.CHAVES_CARTAO)), 1)

# Entre a digitada e a importada, fica a rastreável.
for ordem in (("", "a"), ("a", "")):
    _df = _par(*ordem)
    _fora = rc.duplicates(_df, rc.CHAVES_CARTAO)
    check(f"manual sai, importada fica {ordem}", len(_fora), 1)
    check("sobrevivente tem id",
          _df.drop(index=_fora)["ID Pluggy"].iloc[0], "a")

check("sem a coluna de id, compara por campos",
      len(rc.duplicates(pd.DataFrame([_base, dict(_base)]),
                        rc.CHAVES_CARTAO)), 1)

print("  Compra lançada duas vezes: sobra uma")
df = parcelas(2)
idx = rc.duplicates(df, rc.CHAVES_CARTAO)
check("metade é cópia", len(idx), 6)
check("sobram as 6 originais", len(df) - len(idx), 6)
check("o total cai pela metade",
      round(df.drop(index=idx)["Valor"].sum(), 2), 1600.02)

print("  Lançada três vezes: ainda sobra uma")
df3 = parcelas(3)
check("apaga duas de cada", len(rc.duplicates(df3, rc.CHAVES_CARTAO)), 12)

print("  Sem repetição, não apaga nada")
check("nada a remover", len(rc.duplicates(parcelas(1), rc.CHAVES_CARTAO)), 0)
check("prévia vazia",
      rc.duplicate_preview(parcelas(1), rc.CHAVES_CARTAO).empty, True)

print("  Parcelas diferentes não são duplicata uma da outra")
# 2/6 e 3/6 têm mesmo valor e mesma descrição de propósito.
check("as 6 parcelas sobrevivem",
      len(parcelas(1)) - len(rc.duplicates(parcelas(1), rc.CHAVES_CARTAO)), 6)

print("  Espaço sobrando não engana o comparador")
sujo = parcelas(1).copy()
extra = sujo.iloc[[0]].copy()
extra["Descrição"] = " Link de Fotos "
check("reconhece como a mesma",
      len(rc.duplicates(pd.concat([sujo, extra], ignore_index=True),
                        rc.CHAVES_CARTAO)), 1)

print("  Planilha vazia ou sem as colunas")
check("vazia", len(rc.duplicates(pd.DataFrame(), rc.CHAVES_CARTAO)), 0)
check("sem as colunas",
      len(rc.duplicates(pd.DataFrame({"X": [1, 1]}), rc.CHAVES_CARTAO)), 0)

# ---------------------------------------------------------------------------
print("  O ajuste faz a planilha reproduzir o banco")
base = pd.DataFrame([
    {"Data": "2026-09-02", "Descrição": "Salário",
     "Categoria": "Receita/Salário", "Valor": 5000.0, "Tipo": "Entrada"},
    {"Data": "2026-09-03", "Descrição": "Aporte",
     "Categoria": "Investimento", "Valor": 3192.70, "Tipo": "Saída"},
    {"Data": "2026-09-04", "Descrição": "Gastos",
     "Categoria": "Outros", "Valor": 1918.16, "Tipo": "Saída"},
])
antes = compute_wealth(base, base)
check("ponto de partida",
      (round(antes.bank_balance, 2), round(antes.invested, 2)),
      (-110.86, 3192.70))

ajustes = rc.adjustments(
    saldo_real=222.69, saldo_planilha=antes.bank_balance,
    investido_real=9891.34, investido_planilha=antes.invested,
    quando=date(2026, 9, 30))
depois_df = pd.concat(
    [base, pd.DataFrame([a.to_row() for a in ajustes])], ignore_index=True)
depois = compute_wealth(depois_df, depois_df)
check("saldo passa a bater", round(depois.bank_balance, 2), 222.69)
check("investido passa a bater", round(depois.invested, 2), 9891.34)

# O ajuste existe para reproduzir o banco, não para inventar um ganho.
check("receita do período não muda",
      round(depois.total_income, 2), round(antes.total_income, 2))
check("despesa do período não muda",
      round(depois.total_expense, 2), round(antes.total_expense, 2))
for a in ajustes:
    check(f"{a.categoria!r} é neutra", a.categoria in TRANSFER_CATEGORIES, True)

print("  A ordem dos dois ajustes importa")
# O ajuste de investimento é uma Saída: ele mexe no saldo derivado.
# Calculado na ordem errada, o saldo sobraria errado pelo valor dele.
check("investimento vem primeiro",
      [a.categoria for a in ajustes], ["Investimento", "Ajuste"])

print("  Falta de aporte vira Saída; sobra vira Entrada")
menos = rc.adjustments(saldo_real=0, saldo_planilha=0,
                       investido_real=100.0, investido_planilha=0.0,
                       quando=date(2026, 9, 30))
check("aporte que faltou", (menos[0].tipo, menos[0].valor), ("Saída", 100.0))
mais = rc.adjustments(saldo_real=0, saldo_planilha=0,
                      investido_real=0.0, investido_planilha=100.0,
                      quando=date(2026, 9, 30))
check("resgate que faltou", (mais[0].tipo, mais[0].valor), ("Entrada", 100.0))

print("  Quando já bate, não cria lançamento")
check("nada a fazer",
      rc.adjustments(saldo_real=222.69, saldo_planilha=222.69,
                     investido_real=10.0, investido_planilha=10.0,
                     quando=date(2026, 9, 30)), [])
check("centavo de diferença é ruído",
      rc.adjustments(saldo_real=222.69, saldo_planilha=222.695,
                     investido_real=10.0, investido_planilha=10.0,
                     quando=date(2026, 9, 30)), [])

print("  A linha gerada tem o formato da aba financeiro")
linha = ajustes[0].to_row()
check("colunas", sorted(linha),
      ["Categoria", "Data", "Descrição", "Tipo", "Valor"])
check("valor sempre positivo", linha["Valor"] > 0, True)
check("data em ISO", linha["Data"], "2026-09-30")


# ---------------------------------------------------------------------------
# O lançamento manual parcelado cria N linhas futuras de uma vez, todas
# com a mesma data de compra e sem identificador. A importação traz cada
# parcela no mês em que o banco a cobra. Convivendo, a mesma parcela
# existe duas vezes — e como a data difere, o comparador de duplicatas
# não as reconhece. É o que enche o app de faturas até 2028.
# ---------------------------------------------------------------------------
from src import credit_card as _cc  # noqa: E402

print("  Parcelas projetadas à mão são reconhecidas")
_manuais = _cc.installments_for_purchase(
    purchase_date=date(2026, 8, 22), description="Compra antiga",
    category="Outros", total_amount=2400.0, installments=24, closing_day=8)
_df_manual = pd.DataFrame(
    [dict(m, **{"Cartão": "Principal", "ID Pluggy": ""}) for m in _manuais])
check("24 parcelas alcançam 2028",
      (_df_manual["Mês da Fatura"].iloc[0],
       _df_manual["Mês da Fatura"].iloc[-1]), ("09/2026", "08/2028"))

_idx = rc.manual_future_rows(_df_manual, today=date(2026, 9, 30))
check("as futuras são apontadas", len(_idx), 23)
check("a do mês corrente fica",
      sorted(set(_df_manual.drop(index=_idx)["Mês da Fatura"])), ["09/2026"])

print("  O que veio do banco nunca é removido")
_importadas = _df_manual.copy()
_importadas["ID Pluggy"] = ["p" + str(i) for i in range(len(_importadas))]
check("nenhuma linha com id é tocada",
      len(rc.manual_future_rows(_importadas, today=date(2026, 9, 30))), 0)

# Se o banco confirmou aquele parcelamento, o grupo inteiro fica — mesmo
# as linhas sem id. Uma parcela que veio do banco é prova de que a compra
# realmente foi parcelada; apagar as irmãs sem identificador tiraria da
# fatura uma cobrança que vai chegar. O que sobra de repetido é trabalho
# do comparador de duplicatas, que sabe qual das duas linhas é a do banco.
_misto = pd.concat([_df_manual, _importadas], ignore_index=True)
check("grupo confirmado pelo banco fica inteiro",
      len(rc.manual_future_rows(_misto, today=date(2026, 9, 30))), 0)

# Só o grupo confirmado é poupado: outra compra, projetada à mão, continua
# sendo removida na mesma planilha.
_outra = _cc.installments_for_purchase(
    purchase_date=date(2026, 8, 22), description="Outra compra",
    category="Outros", total_amount=1200.0, installments=12, closing_day=8)
_dois_grupos = pd.concat(
    [_importadas,
     pd.DataFrame([dict(m, **{"Cartão": "Principal", "ID Pluggy": ""})
                   for m in _outra])],
    ignore_index=True)
_idx_dois = rc.manual_future_rows(_dois_grupos, today=date(2026, 9, 30))
check("a projeção sem respaldo sai", len(_idx_dois), 11)
check("e só ela", sorted(set(_dois_grupos.loc[_idx_dois, "Descrição"])),
      ["Outra compra"])

print("  Passado e mês corrente ficam intactos")
_passado = pd.DataFrame([
    {"Cartão": "P", "Mês da Fatura": "01/2026", "ID Pluggy": "",
     "Valor": 10.0},
    {"Cartão": "P", "Mês da Fatura": "09/2026", "ID Pluggy": "",
     "Valor": 10.0},
])
check("nada a remover",
      len(rc.manual_future_rows(_passado, today=date(2026, 9, 30))), 0)
check("planilha vazia",
      len(rc.manual_future_rows(pd.DataFrame(), today=date(2026, 9, 30))), 0)

print("  Sequência de parcelas com buraco é denunciada")
_furado = pd.DataFrame([
    {"Cartão": "P", "Descrição": "TV", "Parcela": "1/4",
     "Mês da Fatura": "10/2026", "Valor": 100},
    {"Cartão": "P", "Descrição": "TV", "Parcela": "2/4",
     "Mês da Fatura": "11/2026", "Valor": 100},
    {"Cartão": "P", "Descrição": "TV", "Parcela": "4/4",
     "Mês da Fatura": "02/2027", "Valor": 100},
])
_falhas = rc.parcel_gaps(_furado)
check("um parcelamento acusado", len(_falhas), 1)
check("aponta a parcela e o mês esperado",
      "parcela 4/4 em 02/2027, esperada em 12/2026" in
      _falhas["Problema"].iloc[0], True)

_certo = pd.DataFrame([
    {"Cartão": "P", "Descrição": "TV", "Parcela": f"{i}/3",
     "Mês da Fatura": f"{9 + i:02d}/2026", "Valor": 100}
    for i in range(1, 4)])
check("sequência correta não acusa", rc.parcel_gaps(_certo).empty, True)
check("compra à vista não entra", rc.parcel_gaps(pd.DataFrame([
    {"Cartão": "P", "Descrição": "x", "Parcela": "1/1",
     "Mês da Fatura": "10/2026", "Valor": 1}])).empty, True)
check("planilha vazia", rc.parcel_gaps(pd.DataFrame()).empty, True)

# O banco só entrega o que já cobrou. Uma compra em 10x tem as parcelas
# seguintes contratadas e invisíveis — e sem elas a projeção do próximo
# ano fica vazia justamente onde existe compromisso.
print("  Parcelas contratadas que o banco ainda não lançou")
_serie = pd.DataFrame([
    {"Cartão": "Principal", "Descrição": "Mercadolivre", "Parcela": "4/10",
     "Mês da Fatura": "11/2026", "Valor": 235.29,
     "Data Compra": "2026-10-31", "Categoria": "Compras",
     "ID Pluggy": "a"},
    {"Cartão": "Principal", "Descrição": "Mercadolivre", "Parcela": "5/10",
     "Mês da Fatura": "12/2026", "Valor": 235.29,
     "Data Compra": "2026-11-30", "Categoria": "Compras",
     "ID Pluggy": "b"},
])
_novas = rc.project_installments(_serie, today=date(2026, 9, 30))
check("completa a série", len(_novas), 5)
check("meses consecutivos", [n["Mês da Fatura"] for n in _novas],
      ["01/2027", "02/2027", "03/2027", "04/2027", "05/2027"])
check("numeração continua", [n["Parcela"] for n in _novas],
      ["6/10", "7/10", "8/10", "9/10", "10/10"])
check("mesmo valor", {n["Valor"] for n in _novas}, {235.29})
check("marcadas como projeção", {n["Origem"] for n in _novas},
      {rc.ORIGEM_PROJECAO})
check("sem id do banco", {n["ID Pluggy"] for n in _novas}, {""})

print("  Série completa não gera nada")
_fim = pd.DataFrame([
    {"Cartão": "P", "Descrição": "KaBuM", "Parcela": f"{i}/3",
     "Mês da Fatura": f"{9 + i:02d}/2026", "Valor": 490.95,
     "Data Compra": "2026-10-09", "Categoria": "x", "ID Pluggy": "c"}
    for i in range(1, 4)])
check("nada a projetar", rc.project_installments(_fim,
                                                 today=date(2026, 9, 30)), [])
check("compra à vista não projeta",
      rc.project_installments(pd.DataFrame([
          {"Cartão": "P", "Descrição": "x", "Parcela": "1/1",
           "Mês da Fatura": "10/2026", "Valor": 10.0,
           "Data Compra": "2026-09-20", "Categoria": "x",
           "ID Pluggy": "z"}]), today=date(2026, 9, 30)), [])
check("planilha vazia",
      rc.project_installments(pd.DataFrame(), today=date(2026, 9, 30)), [])

print("  Não se projeta o passado")
_antiga = pd.DataFrame([
    {"Cartão": "P", "Descrição": "Velha", "Parcela": "1/5",
     "Mês da Fatura": "01/2026", "Valor": 100.0,
     "Data Compra": "2025-12-20", "Categoria": "x", "ID Pluggy": "v"}])
_proj = rc.project_installments(_antiga, today=date(2026, 9, 30))
check("só as que ainda vão ser cobradas",
      [n["Mês da Fatura"] for n in _proj], [])

print("  Rodar de novo não duplica")
_com = pd.concat([_serie, pd.DataFrame(_novas)], ignore_index=True)
check("série completa depois de incluir",
      rc.project_installments(_com, today=date(2026, 9, 30)), [])



# ---------------------------------------------------------------------------
# Projeção substituída pela cobrança real
# ---------------------------------------------------------------------------
#
# A parcela projetada é palpite sobre cobrança que ainda não chegou.
# Quando ela chega, a projeção tem de sair — e o comparador de duplicatas
# não dá conta: ele exige seis campos iguais, e a última parcela costuma
# vir com alguns centavos de diferença por arredondamento.
print("  Projeção sai quando o banco cobra de verdade")
from src.config import ORIGEM_BANCO, ORIGEM_PROJECAO  # noqa: E402


def _linha(parcela, mes, valor, ident, origem, desc="Notebook"):
    return {"Data Compra": "2026-06-22", "Mês da Fatura": mes,
            "Cartão": "Nubank", "Descrição": desc, "Categoria": "Outros",
            "Parcela": parcela, "Valor": valor, "Status": "Pendente",
            "ID Pluggy": ident, "Origem": origem}


_proj = pd.DataFrame([
    _linha("4/10", "10/2026", 235.29, "b4", ORIGEM_BANCO),
    _linha("5/10", "11/2026", 235.29, "b5", ORIGEM_BANCO),
    _linha("5/10", "11/2026", 235.29, "", ORIGEM_PROJECAO),
    _linha("6/10", "12/2026", 235.29, "", ORIGEM_PROJECAO),
])
_fora = rc.supersede_projections(_proj)
check("só a projeção com substituta sai", len(_fora), 1)
check("e é a projetada, não a do banco",
      (_proj.loc[_fora[0], "Origem"], _proj.loc[_fora[0], "Parcela"]),
      (ORIGEM_PROJECAO, "5/10"))

# O caso que o comparador de duplicatas perde: mesma parcela, centavos
# diferentes. Sem isto a fatura conta a parcela duas vezes.
_centavos = pd.DataFrame([
    _linha("10/10", "04/2027", 235.34, "b10", ORIGEM_BANCO),
    _linha("10/10", "04/2027", 235.29, "", ORIGEM_PROJECAO),
])
check("duplicata não pega a diferença de centavos",
      len(rc.duplicates(_centavos, rc.CHAVES_CARTAO)), 0)
check("mas a substituição pega",
      len(rc.supersede_projections(_centavos)), 1)
_limpo = _centavos.drop(index=rc.supersede_projections(_centavos))
check("e a fatura fica com o valor do banco",
      round(float(_limpo["Valor"].sum()), 2), 235.34)

# Mês da fatura diferente também não impede: se o banco cobrou aquela
# parcela, a projeção dela está obsoleta onde quer que tenha caído.
_mes_errado = pd.DataFrame([
    _linha("7/10", "01/2027", 235.29, "b7", ORIGEM_BANCO),
    _linha("7/10", "12/2026", 235.29, "", ORIGEM_PROJECAO),
])
check("mês diferente não salva a projeção",
      len(rc.supersede_projections(_mes_errado)), 1)

print("  O que não é projeção nunca sai")
_manual = pd.DataFrame([
    _linha("5/10", "11/2026", 235.29, "b5", ORIGEM_BANCO),
    _linha("5/10", "11/2026", 235.29, "", "manual"),
])
check("linha manual fica", len(rc.supersede_projections(_manual)), 0)

_so_proj = pd.DataFrame([
    _linha("6/10", "12/2026", 235.29, "", ORIGEM_PROJECAO),
    _linha("7/10", "01/2027", 235.29, "", ORIGEM_PROJECAO),
])
check("sem cobrança do banco, nada sai",
      len(rc.supersede_projections(_so_proj)), 0)

check("outra compra não interfere",
      len(rc.supersede_projections(pd.DataFrame([
          _linha("5/10", "11/2026", 235.29, "b5", ORIGEM_BANCO),
          _linha("5/10", "11/2026", 99.0, "", ORIGEM_PROJECAO, desc="Geladeira"),
      ]))), 0)

check("planilha vazia", len(rc.supersede_projections(pd.DataFrame())), 0)
check("planilha sem a coluna Origem",
      len(rc.supersede_projections(
          pd.DataFrame([{"Cartão": "N", "Descrição": "x", "Parcela": "1/2"}]))),
      0)

# Rodar duas vezes não pode remover a mais: depois da primeira, não há
# projeção com substituta.
_uma_vez = _proj.drop(index=rc.supersede_projections(_proj))
check("idempotente", len(rc.supersede_projections(_uma_vez)), 0)


# ---------------------------------------------------------------------------
# O banco escreve a parcela dentro da descrição
# ---------------------------------------------------------------------------
#
# A mesma compra chega como "Amo Atendimento Medi 1/3" num mês e
# "Amo Atendimento Medi 2/3" no outro. Agrupando pela descrição crua,
# cada parcela virava uma compra e projetava a série inteira a partir de
# si mesma: a 1/3 gerava 2/3 e 3/3, a 2/3 gerava outra 3/3. Era o que
# enchia a tela de parcela repetida até 2027.
print("  Parcela escrita na descrição não vira compra nova")
check("o sufixo sai da identidade",
      rc.purchase_identity("Amo Atendimento Medi 1/3"),
      rc.purchase_identity("Amo Atendimento Medi 2/3"))
check("descrição sem sufixo não é alterada",
      rc.purchase_identity("Mercado Livre"), "mercado livre")
check("número no meio do nome fica",
      rc.purchase_identity("Posto 24/7 Centro"), "posto 24/7 centro")


def _compra(desc, parc, mes, valor, ident="x"):
    return {"Data Compra": "2026-08-10", "Mês da Fatura": mes,
            "Cartão": "Principal", "Descrição": desc, "Categoria": "Outros",
            "Parcela": parc, "Valor": valor, "Status": "Pendente",
            "ID Pluggy": ident, "Origem": ORIGEM_BANCO}


_duas = pd.DataFrame([
    _compra("Amo Atendimento Medi 1/3", "1/3", "09/2026", 133.34, "a1"),
    _compra("Amo Atendimento Medi 2/3", "2/3", "10/2026", 133.33, "a2"),
])
_proj = rc.project_installments(_duas, today=date(2026, 9, 30))
check("só falta a 3/3", [(p["Parcela"], p["Mês da Fatura"]) for p in _proj],
      [("3/3", "11/2026")])
check("e a descrição sai sem o marcador",
      _proj[0]["Descrição"], "Amo Atendimento Medi")

# O caso descrito pelo usuário: fatura de setembro com a 2/3.
_kabum = pd.DataFrame([_compra("KaBuM 2/3", "2/3", "09/2026", 100.0, "k2")])
check("KaBuM 2/3 em setembro deduz a 3/3 em outubro",
      [(p["Parcela"], p["Mês da Fatura"])
       for p in rc.project_installments(_kabum, today=date(2026, 9, 30))],
      [("3/3", "10/2026")])

print("  Não se projeta em fatura que o banco já emitiu")
# O total daquele mês é o que a instituição informou; acrescentar linha
# ali afasta o app do banco em vez de aproximar.
_longa = pd.DataFrame([
    _compra("Mercadolivre 1/10", "1/10", "08/2026", 235.31, "m1")])
check("sem filtro, completa a série",
      len(rc.project_installments(_longa, today=date(2026, 9, 30))), 9)
check("com duas faturas já emitidas, pula as duas",
      len(rc.project_installments(
          _longa, today=date(2026, 9, 30),
          faturadas={("Principal", "09/2026"), ("Principal", "10/2026")})), 7)

print("  A substituição continua casando com a descrição do banco")
# A projeção nasce sem o "N/M" e a linha do banco tem o marcador:
# comparar texto cru faria a parcela ser contada duas vezes.
_mistura = pd.DataFrame([
    _compra("KaBuM 3/3", "3/3", "10/2026", 100.0, "k3"),
    {**_compra("KaBuM", "3/3", "10/2026", 100.0, ""),
     "Origem": ORIGEM_PROJECAO},
])
check("a projeção sai quando o banco cobra",
      len(rc.supersede_projections(_mistura)), 1)

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)