"""Cenário de referência: dois cartões com ciclos bem diferentes.

É o caso real que quebrou a projeção — o Principal fecha no começo do
mês e vence no mesmo mês; o Itaú fecha no fim e vence no seguinte. A
fatura paga em outubro chama-se 10/2026 num e 09/2026 no outro, e é
justamente isso que nenhum filtro por rótulo de mês consegue pegar.
"""
from __future__ import annotations

import pandas as pd

CARDS = pd.DataFrame([
    {"Nome": "Principal", "Instituição": "", "Limite": 5000.0,
     "Dia Fechamento": 8, "Dia Vencimento": 15},
    {"Nome": "Cartão Itaú", "Instituição": "Itaú", "Limite": 1600.0,
     "Dia Fechamento": 30, "Dia Vencimento": 7},
])


def _linha(data, mes, cartao, desc, cat, parcela, valor, status):
    return {"Data Compra": data, "Mês da Fatura": mes, "Cartão": cartao,
            "Descrição": desc, "Categoria": cat, "Parcela": parcela,
            "Valor": valor, "Status": status}


TX = pd.DataFrame([
    # Itaú: compra de 22/08 em 6x. Fecha dia 30, então a 1a parcela é 08/2026.
    *[_linha("2026-08-22",
             ["08/2026", "09/2026", "10/2026", "11/2026", "12/2026", "01/2027"][i],
             "Cartão Itaú", "Link de Fotos", "Formatura", f"{i+1}/6",
             266.67, "Pendente")
      for i in range(6)],

    # Principal — fatura 09/2026 (fecha 08/09, vence 15/09): já paga.
    _linha("2026-09-05", "09/2026", "Principal", "API Claude", "Assinatura",
           "1/1", 27.59, "Pago"),
    _linha("2026-09-06", "09/2026", "Principal", "API CLaude", "Assinatura",
           "1/1", 27.58, "Pago"),
    _linha("2026-09-08", "09/2026", "Principal", "Claude", "Assinatura",
           "1/1", 117.47, "Pago"),
    _linha("2026-09-08", "09/2026", "Principal", "Supermercado", "Supermercado",
           "1/1", 300.16, "Pago"),

    # Principal — fatura 10/2026 (fecha 08/10, vence 15/10): em aberto.
    _linha("2026-09-11", "10/2026", "Principal", "Bolo", "Lanches",
           "1/1", 22.00, "Pendente"),
    _linha("2026-09-12", "10/2026", "Principal", "Bar do Cabelo", "Lazer",
           "1/1", 127.20, "Pendente"),
])

PAY = pd.DataFrame(columns=["Data", "Cartão", "Mês da Fatura", "Valor",
                            "Observação"])

# O que sai da conta em outubro/2026:
#   Principal   fatura 10/2026, vence 15/10 -> 22,00 + 127,20 = 149,20
#   Cartão Itaú fatura 09/2026, vence 07/10 ->                   266,67
ESPERADO_OUTUBRO = 415.87

# O app mostrava só as faturas rotuladas 09/2026 em aberto.
MOSTRAVA_ANTES = 266.67

HOJE = __import__("datetime").date(2026, 9, 18)
