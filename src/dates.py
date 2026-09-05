"""Leitura de datas vindas da planilha."""
from __future__ import annotations

import pandas as pd


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
