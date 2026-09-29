"""Acesso às abas da planilha.

    python tests/run_sheets.py

Cobre o defeito que derrubou a sincronização: uma aba declarada no
esquema depois que o cache de abas foi montado ficava fora dele, e o
acesso estourava com KeyError em vez de criar a aba.
"""
from __future__ import annotations

import os
import sys
import types

_st = types.ModuleType("streamlit")


def _cache(*a, **k):
    def deco(f):
        f.clear = lambda: None
        return f
    return deco


_st.cache_data = _cache
_st.cache_resource = _cache
_st.secrets = {}
sys.modules["streamlit"] = _st
for _m in ("gspread", "gspread.worksheet", "oauth2client",
           "oauth2client.service_account"):
    sys.modules.setdefault(_m, types.ModuleType(_m))
sys.modules["gspread"].worksheet = sys.modules["gspread.worksheet"]
sys.modules["gspread.worksheet"].Worksheet = object
sys.modules["oauth2client"].service_account = \
    sys.modules["oauth2client.service_account"]
sys.modules["oauth2client.service_account"].ServiceAccountCredentials = object

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import sheets  # noqa: E402

_ok = 0
_fail: list[str] = []


def check(label, got, want):
    global _ok
    if got == want:
        _ok += 1
    else:
        _fail.append(f"{label}: obtive {got!r}, esperava {want!r}")


# Cache "montado" antes de a aba existir, como acontece quando o
# Streamlit recarrega o código sem reiniciar o processo.
estado = {"abas": {"financeiro": "ws-financeiro"}, "montagens": 0}


def falso_get_worksheets():
    estado["montagens"] += 1
    estado["abas"] = dict(estado["abas"], importacoes="ws-importacoes")
    return estado["abas"]


falso_get_worksheets.clear = lambda: estado.update(
    abas={"financeiro": "ws-financeiro"})

print("  Aba existente é devolvida sem refazer o cache")
sheets.get_worksheets = lambda: {"financeiro": "ws-financeiro"}
check("acha direto", sheets.get_sheet("financeiro"), "ws-financeiro")

print("  Aba nova refaz o cache em vez de estourar")
estado["montagens"] = 0
sheets.get_worksheets = falso_get_worksheets
sheets.get_worksheets()          # primeira montagem, como no boot
estado["abas"].pop("importacoes")  # o cache ficou sem ela
check("devolve a aba nova", sheets.get_sheet("importacoes"), "ws-importacoes")

print("  Aba que não pode ser criada dá erro explicativo")
sheets.get_worksheets = lambda: {"financeiro": "ws"}
sheets.get_worksheets.clear = lambda: None
try:
    sheets.get_sheet("inexistente")
    _fail.append("deveria levantar KeyError")
except KeyError as exc:
    _ok += 1
    check("explica o que fazer", "permissão de edição" in str(exc), True)

print("  Toda aba do esquema é alcançável")
from src.config import SHEETS_SCHEMA  # noqa: E402
sheets.get_worksheets = lambda: {n: f"ws-{n}" for n in SHEETS_SCHEMA}
sheets.get_worksheets.clear = lambda: None
faltando = [n for n in SHEETS_SCHEMA if sheets.get_sheet(n) != f"ws-{n}"]
check("nenhuma falta", faltando, [])
check("importacoes está no esquema", "importacoes" in SHEETS_SCHEMA, True)
check("com as colunas certas", SHEETS_SCHEMA["importacoes"][0], "ID Pluggy")

print()
for _linha in _fail:
    print(f"  FALHOU {_linha}")
print(f"{_ok} passaram, {len(_fail)} falharam")
sys.exit(1 if _fail else 0)
