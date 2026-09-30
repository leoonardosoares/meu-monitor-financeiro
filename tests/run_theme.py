"""Tema claro e escuro.

    python tests/run_theme.py

O risco aqui é silencioso: uma cor que não troca de modo vira texto
invisível — foi o que aconteceu com o título da tela de login, escrito
em #0F172A sobre fundo quase preto.
"""
from __future__ import annotations

import ast
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

# ---------------------------------------------------------------------------
# As duas paletas têm de ser completas
# ---------------------------------------------------------------------------
#
# Uma `var(--x)` sem valor não dá erro: o navegador descarta a regra em
# silêncio e o elemento volta ao visual nativo do Streamlit — que é
# exatamente o que o CSS estava tentando trocar. Era o caso de
# `--primary-soft`, citada na etiqueta do multiselect e nunca definida,
# então a etiqueta ficava sem fundo nos dois modos.
print("  Nenhuma variável CSS fica sem valor")
check("as paletas declaram tudo que o CSS mapeia", styles.palette_gaps(), {})
for _modo in PALETTES:
    Colors.use(_modo)
    check(f"{_modo}: variáveis órfãs", styles.missing_vars(), set())

# ---------------------------------------------------------------------------
# Nenhuma cor literal fora da paleta
# ---------------------------------------------------------------------------
#
# É a regra que a revisão no olho não pega: um hex escrito à mão fica
# certo no tema em que se desenvolveu e errado no outro. O gráfico de
# orçamento tinha o texto em #0F172A, invisível no escuro; a trilha em
# cinza-gelo, invisível no claro; e quatro grades em rgba(200,200,200)
# que ignoravam a paleta nos dois.
print("  Nenhuma cor literal fora do config")
_RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "src")
_LITERAL = re.compile(r"#[0-9A-Fa-f]{3,8}\b|rgba?\([0-9]")
# O `rgba(0,0,0,0)` do Plotly é transparência, não cor: é o que faz o
# gráfico sentar dentro do cartão em qualquer tema.
_PERMITIDO = ("rgba(0,0,0,0)", "rgba(0, 0, 0, 0)")
_vazadas = []
for _pasta, _, _arqs in os.walk(_RAIZ):
    if "__pycache__" in _pasta:
        continue
    for _nome in sorted(_arqs):
        # config.py é onde as cores moram; styles.py monta o CSS a partir
        # delas e só escreve literal em sombra, que já vem da paleta.
        if not _nome.endswith(".py") or _nome in ("config.py", "styles.py"):
            continue
        _caminho = os.path.join(_pasta, _nome)
        for _n, _linha in enumerate(open(_caminho, encoding="utf-8"), 1):
            _corpo = _linha.split("#", 1)[0] if _linha.lstrip().startswith("#") else _linha
            if not _LITERAL.search(_corpo):
                continue
            if any(p in _corpo for p in _PERMITIDO):
                continue
            _vazadas.append(f"{_nome}:{_n} {_linha.strip()[:60]}")
check("nenhum hex nem rgba fora da paleta", _vazadas, [])

# ---------------------------------------------------------------------------
# Cor não pode ser capturada em valor padrão de argumento
# ---------------------------------------------------------------------------
#
# `def f(cor=Colors.EXPENSE)` é avaliado no import, com a paleta que
# estava ativa então — o modo claro herdava as cores saturadas do escuro,
# e era essa a "falta de harmonia": as barras continuavam com a cor
# calibrada para fundo preto.
print("  Nenhuma cor presa em valor padrão")
# Pelo AST, e não por regex: `= Colors.X` aparece em atribuição comum e
# em argumento de chamada, e só o valor padrão de assinatura é o defeito.
_presas = []
for _pasta, _, _arqs in os.walk(_RAIZ):
    if "__pycache__" in _pasta:
        continue
    for _nome in sorted(_arqs):
        if not _nome.endswith(".py") or _nome == "config.py":
            continue
        _arvore = ast.parse(open(os.path.join(_pasta, _nome),
                                 encoding="utf-8").read())
        for _no in ast.walk(_arvore):
            if not isinstance(_no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            _padroes = [p for p in
                        (_no.args.defaults + list(_no.args.kw_defaults)) if p]
            for _p in _padroes:
                if (isinstance(_p, ast.Attribute)
                        and isinstance(_p.value, ast.Name)
                        and _p.value.id in ("Colors", "C")):
                    _presas.append(f"{_nome}:{_p.lineno} {_no.name}")
check("nenhum argumento com cor padrão", _presas, [])

# ---------------------------------------------------------------------------
# A série de gráfico serve ao fundo de cada modo
# ---------------------------------------------------------------------------
#
# Uma cor precisa de 3:1 contra o fundo para funcionar como objeto
# gráfico. A série do escuro dá 2,80 a 3,59:1 sobre o cartão claro — três
# das seis abaixo do piso. Por isso cada modo tem a sua.
print("  A série de cada modo passa no contraste do seu fundo")


def _lum(h):
    h = h.lstrip("#")
    canais = []
    for _i in (0, 2, 4):
        _c = int(h[_i:_i + 2], 16) / 255
        canais.append(_c / 12.92 if _c <= 0.03928
                      else ((_c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def _razao(a, b):
    _la, _lb = _lum(a), _lum(b)
    return (max(_la, _lb) + 0.05) / (min(_la, _lb) + 0.05)


for _modo, _cores in PALETTES.items():
    _fundo = _cores["SURFACE_2"]
    _fracas = [c for c in _cores["SERIES"] if _razao(c, _fundo) < 3.0]
    check(f"{_modo}: séries abaixo de 3:1 sobre a superfície", _fracas, [])
    # Uma família: se uma cor destaca muito mais que as outras, ela vira
    # a protagonista do gráfico sem que o dado tenha pedido isso.
    _banda = [_razao(c, _fundo) for c in _cores["SERIES"]]
    check(f"{_modo}: amplitude da banda de contraste abaixo de 1,5",
          round(max(_banda) - min(_banda), 2) < 1.5, True)

print("  Tabela de leitura não usa o widget nativo")
# `st.dataframe` é desenhado num canvas e segue o tema do config.toml,
# que é lido na inicialização e não muda: no modo claro virava um
# retângulo preto de texto branco no meio da página, e folha de estilo
# nenhuma alcança aquilo. Onde o usuário só lê, a tabela é HTML.
# `st.data_editor` continua valendo: ali ele edita.
_nativas = []
for _pasta, _, _arqs in os.walk(_RAIZ):
    if "__pycache__" in _pasta:
        continue
    for _nome in sorted(_arqs):
        if not _nome.endswith(".py"):
            continue
        for _n, _l in enumerate(
                open(os.path.join(_pasta, _nome), encoding="utf-8"), 1):
            if "st.dataframe(" in _l:
                _nativas.append(f"{_nome}:{_n}")
check("nenhum st.dataframe nas telas", _nativas, [])

print("  O título da página é maior que o de seção")
# Os dois eram h3: o nome da página tinha o peso de cada bloco dentro
# dela, e a tela não tinha começo. Depois de dar 1,15rem à seção, a
# hierarquia chegou a ficar invertida — seção maior que página.
_css_atual = styles._css()


def _tamanho(classe: str) -> float:
    """font-size da regra daquela classe, em rem.

    Pela abertura da regra (`.classe {`), e não pela primeira menção ao
    nome: um comentário que cita `.mf-sec__title` casava antes da regra.
    """
    _bloco = re.search(
        r"\." + re.escape(classe) + r"\s*\{([^}]*)\}", _css_atual)
    return float(re.search(r"font-size:\s*([\d.]+)rem", _bloco.group(1)).group(1))


_pagina, _secao = _tamanho("mf-page__title"), _tamanho("mf-sec__title")
check("página acima de seção", _pagina > _secao, True)
check("e com degrau perceptível (>= 15%)",
      round(_pagina / _secao, 2) >= 1.15, True)

print("  A escada de superfícies separa página, cartão e campo")
# O que delimita um bloco do outro é o degrau entre as superfícies. No
# claro ele era de 1,055:1 entre a página e o cartão — imperceptível, e
# por isso a tela lia como uma folha só, sem nada delimitando nada.
for _modo, _cores in PALETTES.items():
    _degrau = _razao(_cores["BG"], _cores["SURFACE"])
    check(f"{_modo}: página e cartão se distinguem",
          round(_degrau, 3) >= 1.09, True)
    # O campo tem de se separar do cartão em que está, senão o input
    # desaparece dentro dele.
    check(f"{_modo}: campo se separa do cartão",
          round(_razao(_cores["SURFACE_2"], _cores["SURFACE"]), 3) >= 1.05,
          True)
    # E o texto do corpo tem de passar nas três.
    for _superficie in ("BG", "SURFACE", "SURFACE_2"):
        check(f"{_modo}: texto sobre {_superficie} >= 7:1",
              round(_razao(_cores["TEXT"], _cores[_superficie]), 2) >= 7.0,
              True)

print("  Nenhum gráfico com paleta própria")
# A pizza de alocação usava px.colors.qualitative.Set2 — o único gráfico
# do app que ignorava a série do tema, e as fatias não combinavam com
# nenhuma outra tela.
_proprias = []
for _pasta, _, _arqs in os.walk(_RAIZ):
    if "__pycache__" in _pasta:
        continue
    for _nome in sorted(_arqs):
        if not _nome.endswith(".py"):
            continue
        _txt = open(os.path.join(_pasta, _nome), encoding="utf-8").read()
        for _marca in ("px.colors.", "plotly.colors", "colors.qualitative",
                       "colors.sequential"):
            if _marca in _txt:
                _proprias.append(f"{_nome}: {_marca}")
check("nenhuma paleta do Plotly no lugar da do tema", _proprias, [])

# PRIMARY_SOFT é fundo de realce (#2A4A3D no escuro). Como cor de traço
# ela desaparece contra o cartão — estava em duas séries de gráfico.
print("  Cor de fundo não é usada como cor de traço")
_tracos = []
for _pasta, _, _arqs in os.walk(_RAIZ):
    if "__pycache__" in _pasta:
        continue
    for _nome in sorted(_arqs):
        if not _nome.endswith(".py"):
            continue
        for _n, _l in enumerate(
                open(os.path.join(_pasta, _nome), encoding="utf-8"), 1):
            if "PRIMARY_SOFT" in _l and ("line=" in _l or "line_color" in _l):
                _tracos.append(f"{_nome}:{_n}")
check("PRIMARY_SOFT não aparece como traço", _tracos, [])

print("  O hover do primário é visível")
for _modo, _cores in PALETTES.items():
    # 1,10:1 era o caso do claro: mudança que não se percebe.
    check(f"{_modo}: hover separado do primário",
          round(_razao(_cores["PRIMARY"], _cores["PRIMARY_HOVER"]), 2) >= 1.2,
          True)

print("  O texto passa no contraste sobre o cartão de cada modo")
for _modo, _cores in PALETTES.items():
    for _chave in ("TEXT", "TEXT_MUTED", "TEXT_FAINT", "PRIMARY", "EXPENSE",
                   "WARNING", "INVESTMENT", "NEUTRAL", "INFO"):
        _r = _razao(_cores[_chave], _cores["SURFACE"])
        check(f"{_modo}.{_chave} >= 4.5:1", round(_r, 2) >= 4.5, True)
    # A tinta de alerta tem de deixar o texto do corpo legível.
    for _tinta in ("OK_SOFT", "WARN_SOFT", "ERR_SOFT", "INFO_SOFT"):
        check(f"{_modo}.{_tinta} sob o texto >= 7:1",
              round(_razao(_cores["TEXT"], _cores[_tinta]), 2) >= 7.0, True)

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
