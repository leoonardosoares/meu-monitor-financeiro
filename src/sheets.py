"""Conexão com o Google Sheets e acesso às abas (worksheets).

Tudo que envolve credenciais, autenticação OAuth e descoberta/criação
de abas mora aqui. O resto do app só conhece um dicionário de worksheets.
"""
from __future__ import annotations

import json

import gspread
import streamlit as st
from gspread.worksheet import Worksheet
from oauth2client.service_account import ServiceAccountCredentials

from src.config import (
    DEFAULT_SPREADSHEET_NAME,
    GOOGLE_SCOPES,
    SHEETS_SCHEMA,
)


@st.cache_resource(show_spinner="Conectando ao Google Sheets...")
def _get_workbook() -> gspread.Spreadsheet:
    creds_dict = json.loads(st.secrets["GOOGLE_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, GOOGLE_SCOPES)
    client = gspread.authorize(creds)
    name = st.secrets.get("SPREADSHEET_NAME", DEFAULT_SPREADSHEET_NAME)
    return client.open(name)


@st.cache_resource(show_spinner="Carregando abas da planilha...")
def get_worksheets() -> dict[str, Worksheet]:
    """Retorna todas as worksheets, criando as que não existirem."""
    workbook = _get_workbook()
    existing = {ws.title: ws for ws in workbook.worksheets()}

    worksheets: dict[str, Worksheet] = {}
    for name, columns in SHEETS_SCHEMA.items():
        if name in existing:
            worksheets[name] = existing[name]
        else:
            ws = workbook.add_worksheet(title=name, rows="1000", cols="20")
            ws.append_row(columns)
            worksheets[name] = ws
    return worksheets


def get_sheet(name: str) -> Worksheet:
    """Atalho para obter uma aba específica pelo nome.

    O dicionário de abas é `cache_resource`, e o Streamlit recarrega o
    código sem reiniciar o processo — então uma aba acrescentada ao
    esquema depois fica de fora do cache montado antes dela, e o acesso
    estoura com `KeyError`. Aqui o cache é refeito uma vez antes de
    desistir, o que também cria a aba nova na planilha.
    """
    worksheets = get_worksheets()
    if name not in worksheets:
        # `.clear()` some quando o módulo é recarregado sem o processo
        # reiniciar: aí o atributo do cache não existe mais no objeto.
        limpar = getattr(get_worksheets, "clear", None)
        if callable(limpar):
            limpar()
        worksheets = get_worksheets()
    if name not in worksheets:
        raise KeyError(
            f"A aba '{name}' não existe na planilha e não pôde ser criada. "
            "Confira se a conta de serviço tem permissão de edição."
        )
    return worksheets[name]
