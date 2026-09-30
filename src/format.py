"""Formatação de números e datas no padrão brasileiro."""
from __future__ import annotations


def brl(value: float | int | None) -> str:
    """Formata como moeda brasileira: 1234.5 -> "R$ 1.234,50"."""
    if value is None:
        return "R$ 0,00"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def md(texto: str) -> str:
    """Texto com valores em reais, seguro para o markdown do Streamlit.

    O Streamlit interpreta `$...$` como LaTeX. Dois valores em reais na
    mesma frase transformam tudo entre eles numa fórmula: os cifrões
    somem, o **negrito** para de funcionar e o texto aparece em fonte de
    código. Escapar o cifrão desarma isso.
    """
    return str(texto).replace("$", "\\$")
