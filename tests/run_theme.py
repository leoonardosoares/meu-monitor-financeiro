"""Tema claro e escuro.

    python tests/run_theme.py

O risco aqui é silencioso: uma cor que não troca de modo vira texto
invisível — foi o que aconteceu com o título da tela de login, escrito
em #0F172A sobre fundo quase preto.
"""
from __future__ import annotations

import os
import re
import sys
import types

_st = types.ModuleType("streamlit")
_st.cache_data = _st.cache_resource = lambda *a, **k: (lambda f: f)
_st.markdown = _st.plotly_chart = lambda *a, **k: None
_st.secrets = {}
sys.modules["streamlit"] = _st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotly.io as pio  # noqa: E402

from src import components as cp, styles  # noqa: E402
from src.config import Colors, PALETTES, TEMA_PADRAO  # noqa: E402

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


print("  As duas paletas definem as mesmas chaves")
check("mesmas chaves", set(PALETTES["dark"]), set(PALETTES["light"]))
check("padrão existe", TEMA_PADRAO in PALETTES, True)

print("  Trocar de modo troca superfície e texto")
Colors.use("light")
claro = (Colors.BG, Colors.TEXT, Colors.PRIMARY)
Colors.use("dark")
escuro = (Colors.BG, Colors.TEXT, Colors.PRIMARY)
check("fundo muda", claro[0] != escuro[0], True)
check("texto muda", claro[1] != escuro[1], True)
check("verde se adapta", claro[2] != escuro[2], True)

print("  Texto e fundo nunca coincidem — a falha do login")


def contraste(a: str, b: str) -> float:
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    def lum(h):
        r, g, bl = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(bl)

    x, y = lum(a) + 0.05, lum(b) + 0.05
    return max(x, y) / min(x, y)


for modo, paleta in PALETTES.items():
    for chave, minimo in (("TEXT", 7.0), ("TEXT_MUTED", 4.5),
                          ("TEXT_FAINT", 4.0), ("PRIMARY", 4.5),
                          ("EXPENSE", 4.0)):
        razao = contraste(paleta[chave], paleta["SURFACE"])
        if razao < minimo:
            _fail.append(f"{modo}/{chave}: contraste {razao:.2f} < {minimo}")
        else:
            _ok += 1

print("  O CSS sai com as cores do modo pedido")
styles.inject("light")
css_claro = styles._css()
styles.inject("dark")
css_escuro = styles._css()
check("fundo claro no CSS claro", PALETTES["light"]["BG"] in css_claro, True)
check("fundo escuro no CSS escuro", PALETTES["dark"]["BG"] in css_escuro, True)
check("os dois CSS diferem", css_claro != css_escuro, True)

print("  Nenhuma cor fixa sobrou nas telas")
# Um hex escrito à mão não acompanha a troca de tema e fica invisível
# num dos modos. As cores permitidas vêm das paletas.
permitidas = {v.upper() for p in PALETTES.values() for v in p.values()
              if isinstance(v, str) and v.startswith("#")}
permitidas |= {c.upper() for c in Colors.SERIES}
raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
suspeitos = []
for pasta, _, arquivos in os.walk(os.path.join(raiz, "src")):
    if "__pycache__" in pasta:
        continue
    for nome in arquivos:
        if not nome.endswith(".py") or nome in ("config.py", "styles.py"):
            continue
        caminho = os.path.join(pasta, nome)
        with open(caminho, encoding="utf-8") as fh:
            for n, linha in enumerate(fh, 1):
                for hexa in re.findall(r"#[0-9A-Fa-f]{6}\b", linha):
                    if hexa.upper() not in permitidas:
                        rel = os.path.relpath(caminho, raiz)
                        suspeitos.append(f"{rel}:{n} {hexa}")
check("sem hex fora da paleta", suspeitos, [])

# O Streamlit lê `$...$` como LaTeX: dois valores em reais na mesma
# frase viram fórmula, o "R$" some e o **negrito** para de funcionar.
print("  Dinheiro em texto markdown passa por md()")
from src.format import brl, md  # noqa: E402

exemplo = f"**{brl(2119.44)} em fatura** — venceu, {brl(10.0)} de multa."
check("md escapa os cifrões", md(exemplo).count("\\$"), 2)
check("sem md, o Streamlit veria dois delimitadores",
      exemplo.count("$"), 2)

ALVOS = ("st.warning(", "st.caption(", "st.info(", "st.error(",
         "st.success(", "st.markdown(")
desprotegidos = []
for pasta, _, arquivos in os.walk(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")):
    if "__pycache__" in pasta:
        continue
    for nome in sorted(arquivos):
        if not nome.endswith(".py"):
            continue
        caminho = os.path.join(pasta, nome)
        texto = open(caminho, encoding="utf-8").read()
        for alvo in ALVOS:
            pos = 0
            while (pos := texto.find(alvo, pos)) != -1:
                abre = pos + len(alvo)
                prof, k = 1, abre
                while k < len(texto) and prof:
                    prof += (texto[k] == "(") - (texto[k] == ")")
                    k += 1
                corpo = texto[abre:k - 1]
                if "brl(" in corpo and not corpo.lstrip().startswith("md("):
                    linha = texto[:pos].count("\n") + 1
                    desprotegidos.append(f"{nome}:{linha} {alvo}")
                pos = k
check("nenhuma mensagem com dinheiro fora de md()", desprotegidos, [])

print("  O template do Plotly segue o tema")
cp.use_theme("light")
check("claro", pio.templates.default, "plotly_white+monitor")
cp.use_theme("dark")
check("escuro", pio.templates.default, "plotly_dark+monitor")
check("modo desconhecido cai no escuro",
      (Colors.use("inexistente"), Colors.BG)[1], PALETTES["dark"]["BG"])

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
