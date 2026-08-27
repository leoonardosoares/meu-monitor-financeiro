"""Motor de investimentos: posição por ativo, tributação (IOF/IR) e projeção.

Funções puras — sem Streamlit, sem I/O. Toda a matemática tributária e de
rentabilidade mora aqui para poder ser testada isoladamente.

Convenções adotadas
-------------------
* **Dias úteis**: taxas de renda fixa no Brasil (CDI, Selic, prefixados) são
  cotadas na base 252 dias úteis. Aproximamos dias úteis a partir de dias
  corridos pela razão 252/365 — suficiente para projeções, e evita depender
  de calendário de feriados.
* **IOF**: incide sobre o *rendimento* em resgates com menos de 30 dias
  corridos, conforme tabela regressiva. Zera a partir do 30º dia.
* **IR**: incide sobre o rendimento **já líquido de IOF** (o IOF é abatido
  antes). Tabela regressiva por prazo para renda fixa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd


# ---------------------------------------------------------------------------
# Vocabulário de domínio
# ---------------------------------------------------------------------------

class Indexador:
    PREFIXADO = "Prefixado (% a.a.)"
    CDI = "% do CDI"
    IPCA = "IPCA + spread"
    SELIC = "Selic + spread"
    POUPANCA = "Poupança"
    SEM_TAXA = "Sem taxa definida"


INDEXADORES = [
    Indexador.PREFIXADO, Indexador.CDI, Indexador.IPCA,
    Indexador.SELIC, Indexador.POUPANCA, Indexador.SEM_TAXA,
]

CLASSES = [
    "Renda Fixa", "Tesouro Direto", "Fundos", "Ações",
    "FIIs", "Cripto", "Internacional", "Poupança",
]

# Produtos e se são isentos de IR para pessoa física.
PRODUTOS_ISENTOS_IR = {
    "LCI", "LCA", "CRI", "CRA", "LIG",
    "Debênture Incentivada", "Poupança",
}

PRODUTOS = [
    "CDB", "LCI", "LCA", "CRI", "CRA", "LIG", "RDB",
    "Debênture", "Debênture Incentivada",
    "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+",
    "Fundo DI", "Fundo Multimercado", "Fundo Curto Prazo",
    "Ação", "BDR", "FII", "ETF", "Cripto", "Poupança", "Outro",
]

# Fundos classificados como CURTO PRAZO (prazo médio da carteira <= 365 dias)
# só têm duas faixas de IR: 22,5% até 180 dias e 20% acima — nunca 17,5% ou
# 15% (IN RFB 1.585/2015, art. 6º).
PRODUTOS_CURTO_PRAZO = {"Fundo Curto Prazo"}

# Papéis com carência legal mínima acima de 30 dias (Resolução CMN 5.119/2024
# e alterações de 2025): o resgate antes de 30 dias é impossível, então o IOF
# regressivo nunca chega a incidir. Poupança tem regra própria (aniversário).
PRODUTOS_SEM_IOF = {"LCI", "LCA", "CRI", "CRA", "LIG", "Poupança"}

# Classes de renda variável: IR incide sobre ganho de capital na venda,
# com alíquota fixa (não regressiva por prazo) e sem IOF.
CLASSES_RENDA_VARIAVEL = {"Ações", "FIIs", "Cripto", "Internacional"}

IR_RENDA_VARIAVEL = {
    "Ações": 0.15,
    "FIIs": 0.20,
    "Cripto": 0.15,
    "Internacional": 0.15,
}

DIAS_UTEIS_ANO = 252
DIAS_CORRIDOS_ANO = 365


# ---------------------------------------------------------------------------
# IOF — tabela regressiva (Decreto 6.306/2007, Anexo I)
# ---------------------------------------------------------------------------

# Índice = dias corridos desde a aplicação (1 a 30). Percentual incidente
# sobre o RENDIMENTO. A partir do 30º dia não há IOF.
_IOF_TABLE = [
    96, 93, 90, 86, 83, 80, 76, 73, 70, 66,
    63, 60, 56, 53, 50, 46, 43, 40, 36, 33,
    30, 26, 23, 20, 16, 13, 10, 6, 3, 0,
]


def iof_rate(days: int, *, classe: str = "Renda Fixa",
             produto: str = "") -> float:
    """Alíquota de IOF sobre o rendimento, em fração (0.96 = 96%).

    Não incide em: renda variável (ações, FIIs, cripto — alíquota zero do
    IOF-TVM) nem em papéis com carência legal mínima superior a 30 dias
    (LCI, LCA, CRI, CRA, LIG), onde o resgate antecipado é impossível.
    """
    if classe in CLASSES_RENDA_VARIAVEL:
        return 0.0
    if produto in PRODUTOS_SEM_IOF:
        return 0.0
    if days <= 0:
        return _IOF_TABLE[0] / 100
    if days >= 30:
        return 0.0
    return _IOF_TABLE[days - 1] / 100


# ---------------------------------------------------------------------------
# IR — tabela regressiva de renda fixa
# ---------------------------------------------------------------------------

def ir_rate_renda_fixa(days: int) -> float:
    """Alíquota de IR da renda fixa por prazo, em fração.

    Faixas da Lei 11.033/2004 (limites inclusivos): 180 dias ainda é 22,5%,
    181 já é 20%; 360 é 20%, 361 é 17,5%; 720 é 17,5%, 721 é 15%.
    """
    if days <= 180:
        return 0.225
    if days <= 360:
        return 0.20
    if days <= 720:
        return 0.175
    return 0.15


def ir_rate_fundo_curto_prazo(days: int) -> float:
    """Fundos de curto prazo: só duas faixas, piso de 20%."""
    return 0.225 if days <= 180 else 0.20


def ir_rate(days: int, *, classe: str = "Renda Fixa",
            isento: bool = False, produto: str = "") -> float:
    """Alíquota de IR aplicável, em fração.

    * Produto isento (LCI/LCA/CRI/CRA/LIG/poupança/deb. incentivada) → 0.
    * Renda variável → alíquota fixa da classe.
    * Fundo de curto prazo → tabela de duas faixas.
    * Demais → tabela regressiva de quatro faixas.
    """
    if isento:
        return 0.0
    if classe in CLASSES_RENDA_VARIAVEL:
        return IR_RENDA_VARIAVEL.get(classe, 0.15)
    if produto in PRODUTOS_CURTO_PRAZO:
        return ir_rate_fundo_curto_prazo(days)
    return ir_rate_renda_fixa(days)


def is_isento_ir(produto: str) -> bool:
    """Se o produto é isento de IR para pessoa física."""
    return produto in PRODUTOS_ISENTOS_IR


_ISENTO_SIM = {"sim", "s", "true", "verdadeiro", "1", "x", "y", "yes",
               "isento", "isenta", "✓"}
_ISENTO_NAO = {"nao", "não", "n", "false", "falso", "0", "-", "tributado"}


def parse_isento(raw, produto: str) -> bool:
    """Interpreta a coluna "Isento IR", caindo no produto quando ambíguo.

    Reconhecer só um conjunto fechado de "sins" fazia qualquer outra grafia
    (inclusive "Isento") virar `False` e tributar uma LCI em 22,5%. Agora
    ambos os lados são reconhecidos e o que não for entendido volta para a
    regra do produto, que é a fonte legal.
    """
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().lower()
    if text in _ISENTO_SIM:
        return True
    if text in _ISENTO_NAO:
        return False
    return is_isento_ir(produto)


# ---------------------------------------------------------------------------
# Projeção de valor futuro
# ---------------------------------------------------------------------------

def business_days(days_corridos: int) -> float:
    """Aproxima dias úteis a partir de dias corridos (base 252/365)."""
    return max(days_corridos, 0) * DIAS_UTEIS_ANO / DIAS_CORRIDOS_ANO


@dataclass(frozen=True)
class MarketRates:
    """Premissas de mercado usadas na projeção.

    `cdi`, `selic` e `ipca` em % ao ano; `tr` em % ao mês (a TR é sempre
    divulgada mensalizada). Defaults refletem o cenário de agosto/2026 e
    são editáveis na tela.
    """
    cdi: float = 13.90      # BCB SGS 4389
    selic: float = 14.00    # meta Copom, BCB SGS 432
    ipca: float = 4.44      # acumulado 12 meses, BCB SGS 13522
    tr: float = 0.1709      # % ao mês, BCB SGS 226

    @property
    def poupanca_annual(self) -> float:
        """Rendimento anual da poupança pela Lei 12.703/2012.

        Selic > 8,5% a.a. → 0,5% ao mês + TR.
        Selic <= 8,5% a.a. → 70% da Selic + TR.
        A composição com a TR é multiplicativa, não soma.
        """
        tr_m = self.tr / 100
        if self.selic > 8.5:
            monthly = (1 + 0.005) * (1 + tr_m) - 1
        else:
            base_monthly = (1 + 0.70 * self.selic / 100) ** (1 / 12) - 1
            monthly = (1 + base_monthly) * (1 + tr_m) - 1
        return ((1 + monthly) ** 12 - 1) * 100


def annual_rate(indexador: str, taxa: float, rates: MarketRates) -> float:
    """Converte (indexador, taxa) na taxa anual efetiva em fração.

    * Prefixado: `taxa` já é a taxa anual.
    * % do CDI: aplica o percentual sobre o fator diário do CDI e recompõe.
    * IPCA+ / Selic+: composição do índice com o spread.
    * Poupança: regra da poupança.
    * Sem taxa: 0 (o ativo é avaliado pelo valor informado, não projetado).
    """
    if indexador == Indexador.PREFIXADO:
        return taxa / 100
    if indexador == Indexador.CDI:
        cdi = rates.cdi / 100
        daily = (1 + cdi) ** (1 / DIAS_UTEIS_ANO) - 1
        effective_daily = daily * (taxa / 100)
        return (1 + effective_daily) ** DIAS_UTEIS_ANO - 1
    if indexador == Indexador.IPCA:
        return (1 + rates.ipca / 100) * (1 + taxa / 100) - 1
    if indexador == Indexador.SELIC:
        return (1 + rates.selic / 100) * (1 + taxa / 100) - 1
    if indexador == Indexador.POUPANCA:
        return rates.poupanca_annual / 100
    return 0.0


def project_value(principal: float, *, indexador: str, taxa: float,
                  days: int, rates: MarketRates) -> float:
    """Valor bruto projetado de um capital após `days` dias corridos."""
    if principal <= 0 or days <= 0:
        return max(principal, 0.0)
    annual = annual_rate(indexador, taxa, rates)
    if annual == 0:
        return principal
    if annual <= -1:
        # Capital totalmente consumido; evita base negativa com expoente
        # fracionário (que produziria número complexo).
        return 0.0
    du = business_days(days)
    # Taxa negativa (deflação no IPCA+, spread negativo) precisa aparecer como
    # perda — devolver o principal esconderia o cenário adverso.
    return principal * (1 + annual) ** (du / DIAS_UTEIS_ANO)


# ---------------------------------------------------------------------------
# Tributação de um resgate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaxBreakdown:
    principal: float       # capital aplicado
    gross: float           # valor bruto na data do resgate
    yield_gross: float     # rendimento bruto (gross - principal)
    iof: float             # IOF em R$
    ir: float              # IR em R$
    net: float             # líquido a receber
    iof_pct: float         # alíquota aplicada (fração)
    ir_pct: float          # alíquota aplicada (fração)
    days: int              # prazo em dias corridos

    @property
    def yield_net(self) -> float:
        return self.net - self.principal


def compute_taxes(*, principal: float, gross: float, days: int,
                  classe: str = "Renda Fixa",
                  isento: bool = False,
                  produto: str = "") -> TaxBreakdown:
    """Calcula IOF e IR de um resgate.

    Ordem: o IOF incide primeiro sobre o rendimento; o IR incide sobre o
    rendimento já líquido de IOF. Prejuízo (rendimento negativo) não gera
    imposto.
    """
    yield_gross = gross - principal
    if yield_gross <= 0:
        return TaxBreakdown(
            principal=principal, gross=gross, yield_gross=yield_gross,
            iof=0.0, ir=0.0, net=gross, iof_pct=0.0, ir_pct=0.0, days=days,
        )

    iof_pct = iof_rate(days, classe=classe, produto=produto)
    iof_value = yield_gross * iof_pct

    taxable = yield_gross - iof_value
    ir_pct = ir_rate(days, classe=classe, isento=isento, produto=produto)
    ir_value = taxable * ir_pct

    return TaxBreakdown(
        principal=principal, gross=gross, yield_gross=yield_gross,
        iof=iof_value, ir=ir_value, net=gross - iof_value - ir_value,
        iof_pct=iof_pct, ir_pct=ir_pct, days=days,
    )


# ---------------------------------------------------------------------------
# Lotes: cada aporte carrega seu próprio "relógio" fiscal
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Lot:
    """Um aporte remanescente: valor ainda aplicado + data de entrada."""
    application_date: date
    amount: float


APORTE = "Aporte"
RESGATE = "Resgate"

_REQUIRED_MOVE_COLUMNS = ("Data", "Investimento", "Tipo", "Valor")


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


def normalize_move_type(raw) -> str | None:
    """Normaliza o Tipo da movimentação; `None` se não for reconhecido.

    Aceita variações de caixa e espaços ("aporte", " APORTE "), porque a
    planilha aceita digitação livre. Valores desconhecidos devolvem `None`
    para que o chamador os descarte em vez de tratá-los como resgate.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip().lower()
    if text in {"aporte", "aportes", "aplicação", "aplicacao", "compra"}:
        return APORTE
    if text in {"resgate", "resgates", "saque", "venda", "retirada"}:
        return RESGATE
    return None


def _clean_moves(df_moves: pd.DataFrame) -> pd.DataFrame:
    """Movimentações válidas, com Tipo normalizado, valor e data utilizáveis."""
    if df_moves.empty:
        return pd.DataFrame(columns=[*_REQUIRED_MOVE_COLUMNS, "_dt", "_tipo"])
    missing = [c for c in _REQUIRED_MOVE_COLUMNS if c not in df_moves.columns]
    if missing:
        return pd.DataFrame(columns=[*_REQUIRED_MOVE_COLUMNS, "_dt", "_tipo"])

    moves = df_moves.copy()
    moves["_dt"] = parse_dates(moves["Data"])
    moves["_tipo"] = moves["Tipo"].map(normalize_move_type)
    moves["_valor"] = pd.to_numeric(moves["Valor"], errors="coerce")
    return moves.dropna(subset=["_dt", "_tipo", "_valor"])


def invalid_moves(df_moves: pd.DataFrame) -> pd.DataFrame:
    """Linhas que `build_lots` descarta — data, tipo ou valor inutilizáveis.

    Exposto na tela para que capital sumido nunca fique silencioso.
    """
    if df_moves.empty:
        return df_moves
    missing = [c for c in _REQUIRED_MOVE_COLUMNS if c not in df_moves.columns]
    if missing:
        return df_moves
    valid_idx = _clean_moves(df_moves).index
    return df_moves.drop(valid_idx, errors="ignore")


def build_lots(df_moves: pd.DataFrame, investment: str) -> list[Lot]:
    """Reconstrói os lotes abertos de um investimento consumindo por FIFO.

    Aportes criam lotes; resgates consomem os lotes mais antigos primeiro
    (regra usual e a que minimiza a alíquota de IR remanescente).

    Linhas com tipo irreconhecível são DESCARTADAS, nunca tratadas como
    resgate: um "aporte" com caixa diferente jamais deve subtrair capital.
    """
    moves = _clean_moves(df_moves)
    if moves.empty:
        return []
    target = str(investment).strip()
    moves = moves[moves["Investimento"].astype(str).str.strip() == target]
    if moves.empty:
        return []
    moves = moves.sort_values("_dt")

    lots, _ = _run_fifo(moves)
    return [Lot(application_date=d, amount=v) for d, v in lots]


def _run_fifo(moves: pd.DataFrame) -> tuple[list[list], float]:
    """Executa o FIFO e devolve (lotes abertos, resgate não coberto).

    O excedente é devolvido em vez de descartado: um resgate maior que o
    capital aplicado significa dado errado, e sumir com ele em silêncio
    fazia a carteira mostrar capital que não existe.
    """
    lots: list[list] = []  # [data, valor restante] — mutável durante o FIFO
    unmatched = 0.0
    for _, row in moves.iterrows():
        value = float(row["_valor"])
        if value <= 0:
            continue
        if row["_tipo"] == APORTE:
            lots.append([row["_dt"].date(), value])
        else:  # Resgate consome do lote mais antigo
            remaining = value
            for lot in lots:
                if remaining <= 0:
                    break
                take = min(lot[1], remaining)
                lot[1] -= take
                remaining -= take
            lots = [lot for lot in lots if lot[1] > 1e-9]
            if remaining > 1e-6:
                unmatched += remaining
    return lots, unmatched


def unmatched_redemptions(df_moves: pd.DataFrame) -> dict[str, float]:
    """Por ativo, quanto de resgate não encontrou capital aplicado.

    Sinaliza lançamentos impossíveis (resgate maior que o aportado, ou
    resgate anterior ao aporte) que antes evaporavam sem aviso.
    """
    moves = _clean_moves(df_moves)
    if moves.empty:
        return {}
    out: dict[str, float] = {}
    for name, group in moves.groupby(
        moves["Investimento"].astype(str).str.strip()
    ):
        _, unmatched = _run_fifo(group.sort_values("_dt"))
        if unmatched > 1e-6:
            out[str(name)] = unmatched
    return out


# ---------------------------------------------------------------------------
# Posição consolidada de um investimento
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Position:
    name: str
    classe: str
    produto: str
    instituicao: str
    indexador: str
    taxa: float
    isento: bool
    maturity: date | None
    principal: float          # capital ainda aplicado
    gross_today: float        # valor bruto estimado hoje
    net_today: float          # líquido se resgatasse hoje
    iof_today: float
    ir_today: float
    lots: list[Lot]
    # Última posição real informada pela corretora, quando existe. Quando
    # presente, ela — e não a projeção — define o valor de hoje.
    real_value: float | None = None
    real_date: date | None = None
    projected_today: float = 0.0

    @property
    def has_real(self) -> bool:
        return self.real_value is not None

    @property
    def real_vs_projected(self) -> float:
        """Quanto a posição real está acima (+) ou abaixo (−) da projeção."""
        if self.real_value is None:
            return 0.0
        return self.real_value - self.projected_today

    @property
    def yield_gross_today(self) -> float:
        return self.gross_today - self.principal

    @property
    def yield_net_today(self) -> float:
        return self.net_today - self.principal

    @property
    def days_to_maturity(self) -> int | None:
        if self.maturity is None:
            return None
        return (self.maturity - date.today()).days


def value_at(position_lots: list[Lot], *, indexador: str, taxa: float,
             rates: MarketRates, target: date) -> tuple[float, float]:
    """(principal, valor bruto) de um conjunto de lotes em `target`."""
    principal = 0.0
    gross = 0.0
    for lot in position_lots:
        principal += lot.amount
        days = (target - lot.application_date).days
        gross += project_value(
            lot.amount, indexador=indexador, taxa=taxa, days=days, rates=rates,
        )
    return principal, gross


def taxes_at(position_lots: list[Lot], *, indexador: str, taxa: float,
             rates: MarketRates, target: date, classe: str,
             isento: bool, produto: str,
             gross_override: float | None = None) -> TaxBreakdown:
    """Tributação agregada de todos os lotes resgatados em `target`.

    Cada lote é tributado com o prazo próprio (o IR regressivo depende da
    data de cada aporte), e os resultados são somados.

    `produto` é obrigatório de propósito: um default silencioso já fez a
    tela de cenários de resgate calcular IOF em papel isento e IR de 15%
    em fundo de curto prazo (piso 20%), divergindo do resto do app.
    """
    # Com um bruto real informado pela corretora, ele manda: rateamos entre
    # os lotes na proporção do valor projetado de cada um, para que o IR
    # regressivo continue usando o prazo próprio de cada aporte.
    projected = [
        project_value(
            lot.amount, indexador=indexador, taxa=taxa,
            days=max((target - lot.application_date).days, 0), rates=rates,
        )
        for lot in position_lots
    ]
    total_projected = sum(projected)
    shares: list[float] | None = None
    if gross_override is not None and total_projected > 0:
        shares = [pv / total_projected for pv in projected]
    elif gross_override is not None:
        total_principal = sum(lot.amount for lot in position_lots)
        shares = [
            (lot.amount / total_principal) if total_principal > 0 else 0.0
            for lot in position_lots
        ]

    principal = gross = iof = ir = 0.0
    weighted_days = 0.0
    for i, lot in enumerate(position_lots):
        days = max((target - lot.application_date).days, 0)
        if shares is not None:
            lot_gross = gross_override * shares[i]
        else:
            lot_gross = projected[i]
        bd = compute_taxes(
            principal=lot.amount, gross=lot_gross, days=days,
            classe=classe, isento=isento, produto=produto,
        )
        principal += bd.principal
        gross += bd.gross
        iof += bd.iof
        ir += bd.ir
        weighted_days += days * lot.amount

    avg_days = int(weighted_days / principal) if principal > 0 else 0
    yield_gross = gross - principal
    return TaxBreakdown(
        principal=principal, gross=gross, yield_gross=yield_gross,
        iof=iof, ir=ir, net=gross - iof - ir,
        iof_pct=(iof / yield_gross) if yield_gross > 0 else 0.0,
        ir_pct=(ir / (yield_gross - iof)) if (yield_gross - iof) > 0 else 0.0,
        days=avg_days,
    )


def latest_snapshots(df_snapshots: pd.DataFrame) -> dict[str, tuple[date, float]]:
    """Última posição real informada por ativo: {nome: (data, valor bruto)}."""
    if df_snapshots.empty:
        return {}
    needed = {"Data", "Investimento", "Valor"}
    if not needed.issubset(df_snapshots.columns):
        return {}
    df = df_snapshots.copy()
    df["_dt"] = parse_dates(df["Data"])
    df["_valor"] = pd.to_numeric(df["Valor"], errors="coerce")
    df = df.dropna(subset=["_dt", "_valor"])
    if df.empty:
        return {}
    df["_nome"] = df["Investimento"].astype(str).str.strip()
    df = df.sort_values("_dt")
    out: dict[str, tuple[date, float]] = {}
    for name, group in df.groupby("_nome"):
        row = group.iloc[-1]
        out[str(name)] = (row["_dt"].date(), float(row["_valor"]))
    return out


def snapshot_history(df_snapshots: pd.DataFrame, name: str) -> pd.DataFrame:
    """Histórico ordenado das posições reais de um ativo (Data, Valor)."""
    empty = pd.DataFrame(columns=["Data", "Valor"])
    if df_snapshots.empty:
        return empty
    needed = {"Data", "Investimento", "Valor"}
    if not needed.issubset(df_snapshots.columns):
        return empty
    df = df_snapshots.copy()
    df["Data"] = parse_dates(df["Data"])
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")
    df = df.dropna(subset=["Data", "Valor"])
    df = df[df["Investimento"].astype(str).str.strip() == str(name).strip()]
    return df[["Data", "Valor"]].sort_values("Data").reset_index(drop=True)


def valuation_date(target: date, maturity: date | None) -> date:
    """Data efetiva de avaliação: um papel não rende depois de vencer.

    Quem paga o rendimento é o emissor, e ele para na data de vencimento —
    o dinheiro fica parado até o resgate. Avaliar um papel vencido em
    `today` faria a posição crescer para sempre.
    """
    if maturity is None:
        return target
    return min(target, maturity)


def duplicate_asset_names(df_assets: pd.DataFrame) -> list[str]:
    """Nomes cadastrados mais de uma vez (comparação sem espaços extras).

    Como as movimentações apontam para o ativo pelo nome, duplicatas são
    ambíguas: `build_positions` mantém apenas a primeira ocorrência.
    """
    if df_assets.empty or "Nome" not in df_assets.columns:
        return []
    names = df_assets["Nome"].dropna().astype(str).str.strip()
    names = names[names != ""]
    counts = names.value_counts()
    return counts[counts > 1].index.tolist()


def build_positions(df_assets: pd.DataFrame, df_moves: pd.DataFrame,
                    rates: MarketRates, *,
                    df_snapshots: pd.DataFrame | None = None,
                    today: date | None = None) -> list[Position]:
    """Consolida cadastro + movimentações em posições avaliadas hoje.

    Se houver posição real informada para o ativo (`df_snapshots`), ela
    substitui a projeção no valor de hoje — inclusive na base de cálculo
    dos impostos, que passam a incidir sobre o rendimento que existe de
    fato, e não sobre o estimado.
    """
    today = today or date.today()
    if df_assets.empty:
        return []
    snapshots = latest_snapshots(
        df_snapshots if df_snapshots is not None else pd.DataFrame()
    )

    positions: list[Position] = []
    seen_names: set[str] = set()
    for _, row in df_assets.iterrows():
        name = str(row.get("Nome") or "").strip()
        if not name:
            continue
        # As movimentações referenciam o ativo pelo nome. Dois cadastros com
        # o mesmo nome receberiam os mesmos lotes e dobrariam a carteira —
        # só o primeiro vale. `duplicate_asset_names` avisa o usuário.
        if name in seen_names:
            continue
        seen_names.add(name)
        lots = build_lots(df_moves, name)
        if not lots:
            continue

        classe = str(row.get("Classe") or "Renda Fixa")
        produto = str(row.get("Produto") or "Outro")
        indexador = str(row.get("Indexador") or Indexador.SEM_TAXA)
        # `float(x or 0)` deixava NaN passar (NaN é truthy e float(NaN) não
        # levanta), e a NaN contaminava annual_rate -> project_value -> toda a
        # carteira, inclusive os outros ativos.
        taxa_raw = pd.to_numeric(row.get("Taxa"), errors="coerce")
        taxa = float(taxa_raw) if pd.notna(taxa_raw) and math.isfinite(taxa_raw) else 0.0

        isento = parse_isento(row.get("Isento IR"), produto)

        maturity_raw = pd.to_datetime(row.get("Vencimento"), errors="coerce")
        maturity = maturity_raw.date() if pd.notna(maturity_raw) else None

        effective = valuation_date(today, maturity)
        projected = taxes_at(
            lots, indexador=indexador, taxa=taxa, rates=rates,
            target=effective, classe=classe, isento=isento, produto=produto,
        )

        snap = snapshots.get(name)
        real_value = real_date = None
        bd = projected
        if snap is not None:
            real_date, real_value = snap
            bd = taxes_at(
                lots, indexador=indexador, taxa=taxa, rates=rates,
                target=effective, classe=classe, isento=isento,
                produto=produto, gross_override=real_value,
            )

        positions.append(Position(
            name=name, classe=classe, produto=produto,
            instituicao=str(row.get("Instituição") or ""),
            indexador=indexador, taxa=taxa, isento=isento, maturity=maturity,
            principal=bd.principal, gross_today=bd.gross, net_today=bd.net,
            iof_today=bd.iof, ir_today=bd.ir, lots=lots,
            real_value=real_value, real_date=real_date,
            projected_today=projected.gross,
        ))
    return positions


# ---------------------------------------------------------------------------
# Projeção temporal (para gráficos e decisão de resgate)
# ---------------------------------------------------------------------------

def anchored_gross(position: Position, rates: MarketRates,
                   target: date) -> float | None:
    """Bruto projetado a partir da última posição REAL informada.

    Sem âncora (ou para datas anteriores a ela), devolve None e o chamador
    projeta desde os aportes. Com âncora, o rendimento futuro cresce a
    partir do valor que a corretora mostra hoje — projetar desde o aporte
    original ignoraria a diferença já observada entre estimativa e real.
    """
    if position.real_value is None or position.real_date is None:
        return None
    if target < position.real_date:
        return None
    days = (target - position.real_date).days
    return project_value(
        position.real_value, indexador=position.indexador,
        taxa=position.taxa, days=days, rates=rates,
    )


def projection_curve(position: Position, rates: MarketRates, *,
                     months: int = 36,
                     today: date | None = None) -> pd.DataFrame:
    """Curva mensal Bruto × Líquido de um investimento.

    Colunas: Data, Bruto, Líquido, IOF, IR, Principal, Dias, Aliquota IR (%).
    Se o ativo tem vencimento, a curva não passa dele.
    """
    today = today or date.today()
    rows = []
    for i in range(months + 1):
        target = (pd.Timestamp(today) + pd.DateOffset(months=i)).date()
        if position.maturity and target > position.maturity:
            break
        bd = taxes_at(
            position.lots, indexador=position.indexador, taxa=position.taxa,
            rates=rates, target=target, classe=position.classe,
            isento=position.isento, produto=position.produto,
            gross_override=anchored_gross(position, rates, target),
        )
        rows.append({
            "Data": target,
            "Principal": bd.principal,
            "Bruto": bd.gross,
            "IOF": bd.iof,
            "IR": bd.ir,
            "Líquido": bd.net,
            "Dias": bd.days,
            "Aliquota IR (%)": bd.ir_pct * 100,
        })

    # Garante o ponto exato do vencimento, que raramente cai num aniversário
    # mensal — é a data que mais interessa para decidir o resgate. Só entra
    # se estiver DENTRO do horizonte pedido: anexá-lo de um vencimento em
    # 2031 num gráfico de 6 meses criaria um salto sem sentido.
    horizon_end = (pd.Timestamp(today) + pd.DateOffset(months=months)).date()
    if position.maturity and today < position.maturity <= horizon_end:
        if not rows or rows[-1]["Data"] < position.maturity:
            bd = taxes_at(
                position.lots, indexador=position.indexador,
                taxa=position.taxa, rates=rates, target=position.maturity,
                classe=position.classe, isento=position.isento,
                produto=position.produto,
                gross_override=anchored_gross(
                    position, rates, position.maturity,
                ),
            )
            rows.append({
                "Data": position.maturity,
                "Principal": bd.principal,
                "Bruto": bd.gross,
                "IOF": bd.iof,
                "IR": bd.ir,
                "Líquido": bd.net,
                "Dias": bd.days,
                "Aliquota IR (%)": bd.ir_pct * 100,
            })
    return pd.DataFrame(rows)


def portfolio_curve(positions: list[Position], rates: MarketRates, *,
                    months: int = 36,
                    today: date | None = None) -> pd.DataFrame:
    """Soma as curvas de todos os ativos numa projeção da carteira."""
    today = today or date.today()
    if not positions:
        return pd.DataFrame()

    rows = []
    for i in range(months + 1):
        target = (pd.Timestamp(today) + pd.DateOffset(months=i)).date()
        principal = gross = iof = ir = net = 0.0
        for p in positions:
            effective = valuation_date(target, p.maturity)
            bd = taxes_at(
                p.lots, indexador=p.indexador, taxa=p.taxa, rates=rates,
                target=effective, classe=p.classe, isento=p.isento,
                produto=p.produto,
                gross_override=anchored_gross(p, rates, effective),
            )
            principal += bd.principal
            gross += bd.gross
            iof += bd.iof
            ir += bd.ir
            net += bd.net
        rows.append({
            "Data": target, "Principal": principal, "Bruto": gross,
            "IOF": iof, "IR": ir, "Líquido": net,
        })
    return pd.DataFrame(rows)


def next_ir_step(position: Position, *,
                 today: date | None = None) -> tuple[date, float, float] | None:
    """Próxima data em que a alíquota efetiva da posição CAI, e as alíquotas.

    Retorna (data, alíquota_hoje, alíquota_na_data), ambas ponderadas pelo
    capital de cada lote, ou None se não há degrau à frente, se o produto é
    isento ou se é renda variável.

    Antes esta função olhava só o lote MAIS RECENTE, o que produzia dois
    erros: anunciava uma data muito posterior à real (ignorando lotes mais
    antigos prestes a mudar de faixa) e citava alíquotas de um único aporte
    como se fossem "sua alíquota" — que podia até estar SUBINDO na data
    anunciada, por causa do reequilíbrio entre os lotes.
    """
    if position.isento or position.classe in CLASSES_RENDA_VARIAVEL:
        return None
    today = today or date.today()
    if not position.lots:
        return None
    total = sum(lot.amount for lot in position.lots)
    if total <= 0:
        return None

    curto = position.produto in PRODUTOS_CURTO_PRAZO
    rate_fn = ir_rate_fundo_curto_prazo if curto else ir_rate_renda_fixa
    thresholds = (180,) if curto else (180, 360, 720)

    # Toda data futura em que ALGUM lote troca de faixa.
    candidates: set[date] = set()
    for lot in position.lots:
        held = (today - lot.application_date).days
        for threshold in thresholds:
            if held <= threshold:
                candidates.add(
                    lot.application_date + timedelta(days=threshold + 1)
                )
    future = sorted(d for d in candidates if d > today)
    if not future:
        return None

    def weighted_rate(at: date) -> float:
        return sum(
            lot.amount * rate_fn(max((at - lot.application_date).days, 0))
            for lot in position.lots
        ) / total

    current = weighted_rate(today)
    for step_date in future:
        nxt = weighted_rate(step_date)
        if nxt < current - 1e-12:
            return step_date, current, nxt
    return None


# ---------------------------------------------------------------------------
# Ponte com o razão de caixa (aba `financeiro`, Categoria=Investimento)
# ---------------------------------------------------------------------------
#
# Os dois registros são dimensões complementares do MESMO evento, não
# duplicatas:
#
#   financeiro (Categoria=Investimento)  -> o dinheiro saiu da conta corrente.
#       É o que alimenta saldo bancário, patrimônio e o gráfico de aportes
#       mensais do Dashboard. Continua sendo a fonte da verdade do caixa.
#
#   investimento_movimentacoes           -> em QUAL ativo aquele dinheiro
#       entrou. Alimenta a carteira, a tributação e a projeção.
#
# Quando a atribuição está completa, os totais das duas coincidem — e a
# diferença vira uma conferência automática exibida na tela.

# financeiro "Saída" = dinheiro saindo da conta para investir = Aporte.
# financeiro "Entrada" = dinheiro voltando do investimento = Resgate.
_LEDGER_TO_MOVE = {"Saída": "Aporte", "Entrada": "Resgate"}
_MOVE_TO_LEDGER = {v: k for k, v in _LEDGER_TO_MOVE.items()}


def ledger_investment_flows(df_transactions: pd.DataFrame) -> pd.DataFrame:
    """Lançamentos de investimento do razão de caixa, com a data parseada.

    Acrescenta `Movimento` (Aporte/Resgate) e `Data_DT`.
    """
    empty = pd.DataFrame(
        columns=["Data", "Descrição", "Valor", "Tipo", "Movimento", "Data_DT"]
    )
    if df_transactions.empty or "Categoria" not in df_transactions.columns:
        return empty
    df = df_transactions[df_transactions["Categoria"] == "Investimento"].copy()
    if df.empty:
        return empty
    df["Data_DT"] = parse_dates(df["Data"])
    df = df.dropna(subset=["Data_DT"])
    if df.empty:
        return empty
    df["Movimento"] = df["Tipo"].map(_LEDGER_TO_MOVE)
    df = df.dropna(subset=["Movimento"])
    return df[["Data", "Descrição", "Valor", "Tipo", "Movimento", "Data_DT"]]


def unattributed_flows(df_transactions: pd.DataFrame,
                       df_moves: pd.DataFrame) -> pd.DataFrame:
    """Lançamentos do razão de caixa ainda sem ativo atribuído.

    O pareamento é por (data, valor, natureza) e consome uma movimentação
    por lançamento — assim dois aportes iguais no mesmo dia exigem duas
    movimentações para ficarem quitados.
    """
    ledger = ledger_investment_flows(df_transactions)
    if ledger.empty:
        return ledger.drop(columns=["Data_DT"], errors="ignore")

    available: dict[tuple, int] = {}
    if not df_moves.empty and "Data" in df_moves.columns:
        moves = df_moves.copy()
        moves["Data_DT"] = parse_dates(moves["Data"])
        moves = moves.dropna(subset=["Data_DT"])
        for _, row in moves.iterrows():
            value_raw = pd.to_numeric(row.get("Valor"), errors="coerce")
            tipo = normalize_move_type(row.get("Tipo"))
            if pd.isna(value_raw) or tipo is None:
                continue
            key = (row["Data_DT"].date(), round(float(value_raw), 2), tipo)
            available[key] = available.get(key, 0) + 1

    pending = []
    for idx, row in ledger.iterrows():
        try:
            value = round(float(row["Valor"] or 0), 2)
        except (TypeError, ValueError):
            continue
        key = (row["Data_DT"].date(), value, row["Movimento"])
        if available.get(key, 0) > 0:
            available[key] -= 1
        else:
            pending.append(idx)

    return ledger.loc[pending].drop(columns=["Data_DT"])


def allocation_summary(df_transactions: pd.DataFrame,
                       df_moves: pd.DataFrame) -> dict[str, float]:
    """Confronta o razão de caixa com a alocação por ativo.

    Retorna: `caixa` (aportes − resgates no financeiro), `alocado` (idem nas
    movimentações) e `diferenca` (o que ainda falta atribuir).
    """
    ledger = ledger_investment_flows(df_transactions)
    if ledger.empty:
        caixa = 0.0
    else:
        valores = pd.to_numeric(ledger["Valor"], errors="coerce").fillna(0)
        aportes = float(valores[ledger["Movimento"] == "Aporte"].sum())
        resgates = float(valores[ledger["Movimento"] == "Resgate"].sum())
        caixa = aportes - resgates

    if df_moves.empty or "Tipo" not in df_moves.columns:
        alocado = 0.0
    else:
        # Mesma normalização de `build_lots`: sem isso, uma linha digitada
        # como "aporte" contava na carteira mas valia zero aqui, e o painel
        # convidava a atribuir um lançamento já atribuído — duplicando capital.
        valores = pd.to_numeric(df_moves["Valor"], errors="coerce").fillna(0)
        tipos = df_moves["Tipo"].map(normalize_move_type)
        aportes = float(valores[tipos == APORTE].sum())
        resgates = float(valores[tipos == RESGATE].sum())
        alocado = aportes - resgates

    # "Falta atribuir" vem das MESMAS linhas que a tela de atribuição lista,
    # e não do agregado — assim painel e lista não podem se contradizer.
    pending = unattributed_flows(df_transactions, df_moves)
    if pending.empty:
        pendente = 0.0
    else:
        pv = pd.to_numeric(pending["Valor"], errors="coerce").fillna(0)
        pendente = float(pv[pending["Movimento"] == APORTE].sum()) \
            - float(pv[pending["Movimento"] == RESGATE].sum())

    return {
        "caixa": caixa, "alocado": alocado,
        "diferenca": pendente, "descasamento": caixa - alocado,
    }


def ledger_row_for_move(*, data, valor: float, tipo: str,
                        investimento: str) -> dict:
    """Lançamento equivalente no razão de caixa para uma movimentação nova."""
    descricao = (
        f"Aporte — {investimento}" if tipo == "Aporte"
        else f"Resgate — {investimento}"
    )
    return {
        "Data": data,
        "Descrição": descricao,
        "Categoria": "Investimento",
        "Valor": valor,
        "Tipo": _MOVE_TO_LEDGER[tipo],
    }


# ---------------------------------------------------------------------------
# Manutenção do cadastro (renomear / excluir em cascata)
# ---------------------------------------------------------------------------

def rename_asset(df_assets: pd.DataFrame, df_moves: pd.DataFrame,
                 old: str, new: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Renomeia um ativo e leva junto as movimentações que apontam para ele.

    As movimentações referenciam o ativo pelo nome; renomear só no cadastro
    deixaria o histórico órfão e a posição sumiria da carteira.
    """
    assets = df_assets.copy()
    moves = df_moves.copy()
    if not assets.empty and "Nome" in assets.columns:
        assets["Nome"] = assets["Nome"].astype(str).str.strip().replace(
            {old: new}
        )
    if not moves.empty and "Investimento" in moves.columns:
        moves["Investimento"] = moves["Investimento"].astype(str).str.strip() \
            .replace({old: new})
    return assets, moves


def delete_asset(df_assets: pd.DataFrame, df_moves: pd.DataFrame, name: str, *,
                 drop_moves: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove um ativo do cadastro e, por padrão, suas movimentações.

    Manter as movimentações (`drop_moves=False`) deixa o histórico gravado
    mas órfão — ele não aparece em nenhuma carteira até que um ativo com o
    mesmo nome seja cadastrado de novo.
    """
    assets = df_assets.copy()
    moves = df_moves.copy()
    if not assets.empty and "Nome" in assets.columns:
        assets = assets[assets["Nome"].astype(str).str.strip() != name]
    if drop_moves and not moves.empty and "Investimento" in moves.columns:
        moves = moves[moves["Investimento"].astype(str).str.strip() != name]
    return assets, moves


def orphan_moves(df_assets: pd.DataFrame,
                 df_moves: pd.DataFrame) -> pd.DataFrame:
    """Movimentações que apontam para um ativo que não existe no cadastro."""
    if df_moves.empty or "Investimento" not in df_moves.columns:
        return df_moves
    known = set()
    if not df_assets.empty and "Nome" in df_assets.columns:
        known = set(df_assets["Nome"].dropna().astype(str).str.strip())
    names = df_moves["Investimento"].astype(str).str.strip()
    return df_moves[~names.isin(known)]
