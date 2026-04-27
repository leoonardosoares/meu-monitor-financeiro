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
    """Atalho para obter uma aba específica pelo nome."""
    return get_worksheets()[name]
