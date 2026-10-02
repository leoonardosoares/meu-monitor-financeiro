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


# Onde a razão social começa: daí em diante, nada interessa.
_JURIDICO = ("s.a.", "s.a", "s/a", "ltda", "ltda.", "sociedade",
             "instituicao", "instituição", "me", "eireli")


def short_name(texto: str) -> str:
    """Nome legível a partir do que o banco envia.

    "CDB - NU FINANCEIRA S.A. - SOCIEDADE DE CREDITO, FINANCIAMENTO E
    INVESTIMENTO" vira "CDB · Nu Financeira"; "Nu Pagamentos S.A. -
    Instituição de Pagamento" vira "Nu Pagamentos". A razão social
    inteira quebrava em três linhas em cada cartão do painel.
    """
    partes = [p.strip() for p in str(texto or "").split(" - ") if p.strip()]
    if not partes:
        return ""

    def limpa(p: str) -> str:
        palavras = []
        for w in p.replace(",", " ").split():
            if w.casefold() in _JURIDICO:
                break
            palavras.append(w)
        nome = " ".join(palavras[:3])
        if nome.isupper() and len(nome) > 4:
            return nome.title()
        return nome[:1].upper() + nome[1:] if nome.islower() else nome

    primeiro = limpa(partes[0]) or partes[0]
    if len(partes) > 1 and len(primeiro) <= 12:
        emissor = limpa(partes[1])
        if emissor and emissor.casefold() != primeiro.casefold():
            return f"{primeiro} · {emissor}"
    return primeiro
