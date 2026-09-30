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

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
