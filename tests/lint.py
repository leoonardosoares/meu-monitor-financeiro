"""Procura nomes indefinidos e importes mortos em todo o projeto.

    python tests/lint.py

Existe por causa de um erro real: um edit removeu funções do meio de
`src/pages/settings.py` e a página quebrou com `NameError` só em
produção. `compileall` não pega isso — sintaxe continua válida — e as
suites não importam as páginas, porque elas dependem de streamlit e
plotly. Uma checagem estática pega, e em um segundo.
"""
from __future__ import annotations

import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALVOS = ["src", "app.py", "tests"]

import importlib.util

if importlib.util.find_spec("pyflakes") is None:
    print("pyflakes não instalado — pulando (pip install pyflakes)")
    sys.exit(0)

r = subprocess.run([sys.executable, "-m", "pyflakes", *ALVOS],
                   cwd=RAIZ, capture_output=True, text=True)
saida = (r.stdout + r.stderr).strip()

# Nome indefinido é quebra de verdade; importe não usado é só sujeira.
graves = [l for l in saida.splitlines() if "undefined name" in l]
resto = [l for l in saida.splitlines() if l and "undefined name" not in l]

for linha in graves:
    print(f"  GRAVE {linha}")
for linha in resto:
    print(f"  aviso {linha}")

print(f"{len(graves)} nome(s) indefinido(s), {len(resto)} aviso(s)")
sys.exit(1 if graves else 0)
