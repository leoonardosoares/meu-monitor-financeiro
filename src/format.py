"""Formatação de números e datas no padrão brasileiro."""
from __future__ import annotations


def brl(value: float | int | None) -> str:
    """Formata como moeda brasileira: 1234.5 -> "R$ 1.234,50"."""
    if value is None:
        return "R$ 0,00"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
