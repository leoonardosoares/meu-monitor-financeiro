"""Leitura de datas vindas da planilha."""
from __future__ import annotations

import re

import pandas as pd

# Aceita os separadores que aparecem quando o rótulo é digitado à mão
# ("10 / 2026", "10-2026", "10.2026") sem reabrir a porta para os dois
# casos que eram lidos errado em silêncio: ano de dois dígitos ("09/26",
# que virava 2001) e ordem invertida ("2026-10").
_MONTH_LABEL = re.compile(r"^\s*(\d{1,2})\s*[/.\-]+\s*(\d{4})\s*$")


def parse_month_label(label) -> pd.Timestamp | None:
    """Primeiro dia do mês de um rótulo "MM/AAAA"; `None` se ilegível.

    O rótulo vem de uma planilha que o usuário edita à mão, então chega
    torto: `"9/2026"` sem zero à esquerda, `"09/26"` com ano de dois
    dígitos, espaços nas pontas. Fatiar por posição — `label[3:]` e
    `label[:2]` — lia `"9/2026"` como ano 26 e `"09/26"` como ano 2001,
    ambos sem erro nenhum, e a fatura simplesmente sumia das somas.
    Aqui o formato é validado: o que não casar volta `None` para o
    chamador avisar, em vez de virar uma data absurda em silêncio.
    """
    m = _MONTH_LABEL.match(str(label))
    if not m:
        return None
    mes, ano = int(m.group(1)), int(m.group(2))
    if not 1 <= mes <= 12:
        return None
    return pd.Timestamp(ano, mes, 1)


def month_label(ts) -> str:
    """Rótulo canônico "MM/AAAA" de um Timestamp."""
    return pd.Timestamp(ts).strftime("%m/%Y")


def parse_dates(series: pd.Series) -> pd.Series:
    """Converte datas tolerando os dois formatos que convivem na planilha.

    O app grava ISO (``2026-01-10``); o usuário digita à mão no Google
    Sheets no formato brasileiro (``10/01/2026``). Aplicar ``dayfirst`` a
    tudo corromperia o ISO — ``2026-02-20`` viraria "dia 2 do mês 20" e
    seria descartado. Então o formato é detectado por linha: ISO é lido
    literalmente, o resto assume dia antes do mês.
    """
    s = pd.Series(series)
    if s.empty:
        return pd.to_datetime(s, errors="coerce")
    iso_like = s.astype(str).str.strip().str.match(r"^\d{4}-\d{1,2}-\d{1,2}")
    iso_like = iso_like.fillna(False)

    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if iso_like.any():
        out.loc[iso_like] = pd.to_datetime(s[iso_like], errors="coerce")
    if (~iso_like).any():
        out.loc[~iso_like] = pd.to_datetime(
            s[~iso_like], errors="coerce", dayfirst=True,
        )
    return out
