"""Conciliação: fazer a planilha bater com o banco.

Duas ferramentas, para dois problemas diferentes — e usar a errada
esconde o defeito em vez de corrigi-lo.

**Duplicata** é linha repetida: a mesma compra lançada à mão e trazida
de novo pela importação. O conserto é apagar a cópia. Um lançamento de
ajuste aqui só mascararia o total, e a fatura continuaria mostrando a
compra duas vezes.

**Diferença residual** é o que sobra quando não há repetição: período
que nunca foi lançado, gasto em dinheiro, aporte antigo. Isso não tem
linha para apagar, e é aí que o ajuste é a resposta certa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.config import (CATEGORIA_AJUSTE, CATEGORIA_INVESTIMENTO,
                        ORIGEM_PROJECAO)
from src.dates import month_label, parse_month_label

# Uma compra é a mesma compra quando coincide em tudo que a descreve.
# Data e parcela entram na chave para não fundir a parcela 2/6 com a
# 3/6, que têm o mesmo valor e a mesma descrição de propósito.
CHAVES_CARTAO = ["Cartão", "Mês da Fatura", "Descrição", "Parcela",
                 "Valor", "Data Compra"]
# Identificador da Pluggy, quando a linha veio da importação.
COLUNA_ID = "ID Pluggy"
CHAVES_BANCO = ["Data", "Descrição", "Categoria", "Valor", "Tipo"]


def _chaves_validas(df: pd.DataFrame, chaves: list[str]) -> list[str]:
    return [c for c in chaves if c in df.columns]


def duplicates(df: pd.DataFrame, chaves: list[str]) -> pd.Index:
    """Índices das linhas repetidas, preservando uma de cada compra.

    Dentro de um grupo de linhas idênticas, o identificador da Pluggy
    decide o que é repetição:

    - **Ids diferentes** são compras diferentes. Dois cafés de R$ 5 no
      mesmo lugar e no mesmo dia são duas compras; apagar um comia
      dinheiro de verdade e deixava a fatura abaixo da do banco.
    - **O mesmo id** é a mesma compra trazida duas vezes.
    - **Sem id** é lançamento digitado à mão. Quando existe uma cópia
      com id, a manual é a que sai: a importada é rastreável e a outra
      não.

    Nunca sobra zero de um grupo — um excesso aparece no total, uma
    falta não aparece em lugar nenhum.
    """
    if df.empty:
        return pd.Index([])
    usadas = _chaves_validas(df, chaves)
    if not usadas:
        return pd.Index([])

    chave = (df[usadas].astype(str)
             .apply(lambda s: s.str.strip())
             .apply(tuple, axis=1))
    if COLUNA_ID in df.columns:
        ids = df[COLUNA_ID].fillna("").astype(str).str.strip()
    else:
        ids = pd.Series("", index=df.index)

    remover: list = []
    ids_vistos: dict[tuple, set[str]] = {}
    tem_id: dict[tuple, bool] = {}
    sem_id_guardado: dict[tuple, object] = {}

    for posicao, grupo in chave.items():
        tem_id[grupo] = tem_id.get(grupo, False) or bool(ids[posicao])

    for posicao, grupo in chave.items():
        ident = ids[posicao]
        if ident:
            conhecidos = ids_vistos.setdefault(grupo, set())
            if ident in conhecidos:
                remover.append(posicao)
            else:
                conhecidos.add(ident)
        elif tem_id[grupo]:
            # Existe a mesma compra vinda do banco; esta é a digitada.
            remover.append(posicao)
        elif grupo in sem_id_guardado:
            remover.append(posicao)
        else:
            sem_id_guardado[grupo] = posicao

    return pd.Index(remover)


def duplicate_preview(df: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """O que seria apagado, agrupado, para conferir antes de apagar."""
    idx = duplicates(df, chaves)
    if len(idx) == 0:
        return pd.DataFrame()
    usadas = _chaves_validas(df, chaves)
    recorte = df.loc[idx, usadas].copy()
    contagem = recorte.groupby(usadas, dropna=False).size()
    fora = contagem.reset_index()
    fora.columns = [*usadas, "Cópias a remover"]
    return fora.sort_values("Cópias a remover", ascending=False)


@dataclass(frozen=True)
class Ajuste:
    """Um lançamento de conciliação, pronto para virar linha."""
    descricao: str
    categoria: str
    valor: float
    tipo: str          # "Entrada" ou "Saída"
    data: date
    motivo: str = ""

    def to_row(self) -> dict:
        return {
            "Data": self.data.isoformat(),
            "Descrição": self.descricao,
            "Categoria": self.categoria,
            "Valor": round(abs(self.valor), 2),
            "Tipo": self.tipo,
        }


def _ajuste(descricao: str, categoria: str, delta: float, quando: date,
            motivo: str) -> Ajuste | None:
    if abs(delta) < 0.01:
        return None
    return Ajuste(descricao=descricao, categoria=categoria,
                  valor=abs(delta),
                  tipo="Entrada" if delta > 0 else "Saída",
                  data=quando, motivo=motivo)


def adjustments(*, saldo_real: float, saldo_planilha: float,
                investido_real: float, investido_planilha: float,
                quando: date) -> list[Ajuste]:
    """Lançamentos que fazem a planilha reproduzir o banco.

    A ordem importa. O ajuste de investimento é uma Saída na conta —
    ele mexe no saldo derivado. Calcular o ajuste de saldo antes dele
    deixaria a conta errada pelo valor do primeiro, e seria preciso um
    terceiro ajuste para corrigir o segundo.
    """
    out: list[Ajuste] = []

    delta_inv = investido_real - investido_planilha
    ajuste_inv = _ajuste(
        "Conciliação de investimentos", CATEGORIA_INVESTIMENTO,
        # Aporte que faltou lançar sai da conta: Saída na categoria
        # Investimento é como o app registra dinheiro indo para a
        # carteira, então o sinal é invertido em relação ao delta.
        -delta_inv, quando,
        "posição nas instituições menos o que os lançamentos somam",
    )
    if ajuste_inv:
        out.append(ajuste_inv)

    # O ajuste acima já mexeu no saldo derivado; o de conta parte de lá.
    derivado = saldo_planilha - delta_inv
    ajuste_conta = _ajuste(
        "Conciliação de saldo", CATEGORIA_AJUSTE,
        saldo_real - derivado, quando,
        "saldo do banco menos o que a planilha soma",
    )
    if ajuste_conta:
        out.append(ajuste_conta)

    return out


# ---------------------------------------------------------------------------
# Parcelas projetadas à mão
# ---------------------------------------------------------------------------
#
# O lançamento manual de uma compra parcelada cria, de uma vez, uma linha
# por parcela nos meses seguintes — todas com a mesma data de compra e
# sem identificador. A importação não faz isso: cada parcela chega como
# uma transação própria, no mês em que o banco a cobra.
#
# Convivendo, as duas projetam a mesma parcela: a linha inventada e a
# que o banco mandou. E como a data de compra difere, o comparador de
# duplicatas não as reconhece.


def manual_future_rows(df: pd.DataFrame, *, today: date) -> pd.Index:
    """Parcelas que o formulário manual projetou para os meses seguintes.

    O formulário cria, de uma vez, uma linha por parcela nos meses à
    frente — todas com a MESMA data de compra, porque nenhuma delas
    aconteceu ainda. A importação faz o oposto: cada parcela chega com a
    data em que o banco a lançou.

    É essa repetição da data que identifica a projeção manual, e não a
    falta de identificador: linhas importadas antes de o app passar a
    guardar o id também estão sem ele, e mirar nelas apagava compra de
    verdade — foi o que tirou R$ 1.139,90 de uma fatura atual.

    O mês corrente fica de fora: a fatura dele ainda é cobrada.
    """
    if df.empty or "Mês da Fatura" not in df.columns:
        return pd.Index([])
    precisa = {"Descrição", "Parcela", "Data Compra"}
    if not precisa.issubset(df.columns):
        return pd.Index([])

    base = df.copy()
    base["_total"] = base["Parcela"].map(_total_parcelas)
    base["_mes"] = base["Mês da Fatura"].map(parse_month_label)
    base["_compra"] = base["Data Compra"].astype(str).str.strip()
    base["_desc"] = base["Descrição"].astype(str).str.strip()
    if COLUNA_ID in base.columns:
        base["_id"] = base[COLUNA_ID].fillna("").astype(str).str.strip()
    else:
        base["_id"] = ""

    corte = pd.Timestamp(today).normalize().replace(day=1) + \
        pd.DateOffset(months=1)

    # A assinatura: parcelamento cuja mesma data de compra se repete em
    # mais de um mês de fatura, e sem nenhuma linha vinda do banco.
    suspeitos: list = []
    for (desc, compra, total), grupo in base[base["_total"] > 1].groupby(
            ["_desc", "_compra", "_total"], dropna=False):
        meses = {m for m in grupo["_mes"] if m is not None}
        if len(meses) < 2:
            continue                      # parcela única por data: veio do banco
        if any(grupo["_id"]):
            continue                      # o banco confirmou este parcelamento
        for idx, linha in grupo.iterrows():
            if linha["_mes"] is not None and linha["_mes"] >= corte:
                suspeitos.append(idx)

    return pd.Index(suspeitos)


def parcel_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Parcelamentos cujos meses não formam uma sequência.

    A parcela 4/10 tem de cair um mês depois da 3/10. Um buraco ou uma
    repetição aponta linha faltando ou linha inventada — e é o tipo de
    erro que o total esconde, porque a soma continua parecendo
    plausível.
    """
    vazio = pd.DataFrame(columns=["Cartão", "Descrição", "Parcelas",
                                  "Meses", "Problema"])
    precisa = {"Cartão", "Descrição", "Parcela", "Mês da Fatura"}
    if df.empty or not precisa.issubset(df.columns):
        return vazio

    base = df.copy()
    base["_n"] = base["Parcela"].map(_indice_parcela)
    base["_total"] = base["Parcela"].map(_total_parcelas)
    base = base[(base["_total"] > 1) & base["_n"].notna()]
    if base.empty:
        return vazio
    base["_mes"] = base["Mês da Fatura"].map(parse_month_label)
    base = base[base["_mes"].notna()]

    problemas = []
    for (cartao, desc, total), grupo in base.groupby(
            ["Cartão", "Descrição", "_total"], dropna=False):
        grupo = grupo.sort_values("_n")
        esperado = None
        falha = None
        for _, linha in grupo.iterrows():
            mes = linha["_mes"]
            if esperado is None:
                esperado = mes
            elif mes != esperado:
                falha = (f"parcela {int(linha['_n'])}/{int(total)} em "
                         f"{mes:%m/%Y}, esperada em {esperado:%m/%Y}")
                break
            esperado = esperado + pd.DateOffset(months=1)
        if falha:
            problemas.append({
                "Cartão": cartao, "Descrição": desc,
                "Parcelas": int(total), "Meses": len(grupo),
                "Problema": falha,
            })
    return pd.DataFrame(problemas) if problemas else vazio


def _indice_parcela(valor) -> float:
    try:
        return float(str(valor).split("/")[0].strip())
    except (TypeError, ValueError):
        return float("nan")


def _total_parcelas(valor) -> int:
    try:
        return int(str(valor).split("/")[1].strip())
    except (TypeError, ValueError, IndexError):
        return 0


# ---------------------------------------------------------------------------
# Projeção de parcelas
# ---------------------------------------------------------------------------
#
# O banco só publica fatura fechada, e a Pluggy só devolve as transações
# que ele já lançou. Uma compra em 10x tem as parcelas seguintes
# CONTRATADAS mas ainda não lançadas — elas existem, vão ser cobradas, e
# não aparecem em lugar nenhum dos dados.
#
# Elas podem ser deduzidas: se a última parcela conhecida é a 4/10 na
# fatura de 11/2026, faltam seis, de 12/2026 a 05/2027, no mesmo valor.
# O parcelamento é a única coisa do cartão em que projetar é honesto,
# porque o valor e a quantidade já foram acordados.


def project_installments(df: pd.DataFrame, *,
                         today: date) -> list[dict]:
    """Linhas das parcelas contratadas que o banco ainda não lançou.

    Parte da última parcela conhecida de cada compra e completa a
    série. Devolve linhas prontas para a aba `cartao`, marcadas na
    origem como projeção — elas são compromisso deduzido, não extrato,
    e a tela precisa poder dizer isso.
    """
    precisa = {"Cartão", "Descrição", "Parcela", "Mês da Fatura", "Valor"}
    if df.empty or not precisa.issubset(df.columns):
        return []

    base = df.copy()
    base["_n"] = base["Parcela"].map(_indice_parcela)
    base["_total"] = base["Parcela"].map(_total_parcelas)
    base = base[(base["_total"] > 1) & base["_n"].notna()]
    if base.empty:
        return []
    base["_mes"] = base["Mês da Fatura"].map(parse_month_label)
    base = base[base["_mes"].notna()]

    hoje_mes = pd.Timestamp(today).normalize().replace(day=1)
    novas: list[dict] = []

    for (cartao, desc, total), grupo in base.groupby(
            ["Cartão", "Descrição", "_total"], dropna=False):
        total = int(total)
        conhecidas = {int(n) for n in grupo["_n"]}
        if len(conhecidas) >= total:
            continue                      # a série já está completa

        ultima = grupo.loc[grupo["_n"].idxmax()]
        n_ultima = int(ultima["_n"])
        mes_ultima = ultima["_mes"]
        valor = float(pd.to_numeric(ultima["Valor"], errors="coerce") or 0)
        if valor <= 0:
            continue

        for i in range(n_ultima + 1, total + 1):
            if i in conhecidas:
                continue
            mes = mes_ultima + pd.DateOffset(months=i - n_ultima)
            if mes < hoje_mes:
                continue                  # já passou; não se projeta o passado
            novas.append({
                "Data Compra": str(ultima.get("Data Compra") or ""),
                "Mês da Fatura": month_label(mes),
                "Cartão": cartao,
                "Descrição": desc,
                "Categoria": str(ultima.get("Categoria") or "Outros"),
                "Parcela": f"{i}/{total}",
                "Valor": round(valor, 2),
                "Status": "Pendente",
                "ID Pluggy": "",
                "Origem": ORIGEM_PROJECAO,
            })
    return novas



def supersede_projections(df: pd.DataFrame) -> pd.Index:
    """Projeções que o banco já substituiu por cobrança de verdade.

    Uma parcela projetada não tem existência própria: ela é um palpite
    sobre uma cobrança que ainda não chegou. Quando o banco lança a
    parcela 5/10 daquela compra, a projeção da 5/10 tem de sair — senão a
    fatura conta a mesma parcela duas vezes.

    O comparador de duplicatas não resolve isso sozinho. Ele exige
    coincidência em seis campos, incluindo valor e data da compra, e a
    projeção acerta os dois só por sorte: a última parcela costuma
    absorver o arredondamento, e aí a 10/10 real vem alguns centavos
    diferente da projetada. Seis campos iguais viram cinco, a duplicata
    passa e a fatura dobra.

    Aqui a chave é (cartão, descrição, parcela), que é o que identifica a
    cobrança independentemente de quanto ela veio. Nenhuma linha do banco
    é tocada: só sai projeção, e só a que já tem substituta.
    """
    precisa = {"Cartão", "Descrição", "Parcela", "Origem"}
    if df.empty or not precisa.issubset(df.columns):
        return pd.Index([])

    base = df.copy()
    base["_cartao"] = base["Cartão"].astype(str).str.strip()
    base["_desc"] = base["Descrição"].astype(str).str.strip().str.casefold()
    base["_parc"] = base["Parcela"].astype(str).str.strip()
    base["_proj"] = (base["Origem"].astype(str).str.strip().str.casefold()
                     == ORIGEM_PROJECAO.casefold())

    # Uma linha vale como cobrança do banco quando carrega identificador.
    # Não basta "não ser projeção": o lançamento manual também não é, e
    # ele não é prova de que a cobrança chegou.
    if COLUNA_ID in base.columns:
        tem_id = base[COLUNA_ID].astype(str).str.strip() != ""
    else:
        tem_id = pd.Series(False, index=base.index)

    do_banco = set(
        zip(base.loc[tem_id, "_cartao"], base.loc[tem_id, "_desc"],
            base.loc[tem_id, "_parc"]))
    if not do_banco:
        return pd.Index([])

    # A lista vira Series com o mesmo índice: o pandas 3 não combina
    # Series com sequência solta, e alinhar pelo índice é o que garante
    # que a máscara aponte para as linhas certas.
    tem_substituta = pd.Series(
        [chave in do_banco
         for chave in zip(base["_cartao"], base["_desc"], base["_parc"])],
        index=base.index,
    )
    return base.index[base["_proj"] & tem_substituta]
