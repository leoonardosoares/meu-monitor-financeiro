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
    if annual <= 0:
        return principal
    du = business_days(days)
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


def build_lots(df_moves: pd.DataFrame, investment: str) -> list[Lot]:
    """Reconstrói os lotes abertos de um investimento consumindo por FIFO.

    Aportes criam lotes; resgates consomem os lotes mais antigos primeiro
    (regra usual e a que minimiza a alíquota de IR remanescente).
    """
    if df_moves.empty:
        return []
    moves = df_moves[df_moves["Investimento"] == investment].copy()
    if moves.empty:
        return []
    moves["_dt"] = pd.to_datetime(moves["Data"], errors="coerce")
    moves = moves.dropna(subset=["_dt"]).sort_values("_dt")

    lots: list[list] = []  # [data, valor restante] — mutável durante o FIFO
    for _, row in moves.iterrows():
        value = float(row["Valor"] or 0)
        if value <= 0:
            continue
        if row["Tipo"] == "Aporte":
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
    return [Lot(application_date=d, amount=v) for d, v in lots]


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
             isento: bool, produto: str = "") -> TaxBreakdown:
    """Tributação agregada de todos os lotes resgatados em `target`.

    Cada lote é tributado com o prazo próprio (o IR regressivo depende da
    data de cada aporte), e os resultados são somados.
    """
    principal = gross = iof = ir = 0.0
    weighted_days = 0.0
    for lot in position_lots:
        days = max((target - lot.application_date).days, 0)
        lot_gross = project_value(
            lot.amount, indexador=indexador, taxa=taxa, days=days, rates=rates,
        )
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


def build_positions(df_assets: pd.DataFrame, df_moves: pd.DataFrame,
                    rates: MarketRates, *,
                    today: date | None = None) -> list[Position]:
    """Consolida cadastro + movimentações em posições avaliadas hoje."""
    today = today or date.today()
    if df_assets.empty:
        return []

    positions: list[Position] = []
    for _, row in df_assets.iterrows():
        name = str(row.get("Nome") or "").strip()
        if not name:
            continue
        lots = build_lots(df_moves, name)
        if not lots:
            continue

        classe = str(row.get("Classe") or "Renda Fixa")
        produto = str(row.get("Produto") or "Outro")
        indexador = str(row.get("Indexador") or Indexador.SEM_TAXA)
        try:
            taxa = float(row.get("Taxa") or 0)
        except (TypeError, ValueError):
            taxa = 0.0

        isento_raw = row.get("Isento IR")
        if isinstance(isento_raw, str) and isento_raw.strip():
            isento = isento_raw.strip().lower() in {"sim", "true", "1", "s"}
        elif isinstance(isento_raw, bool):
            isento = isento_raw
        else:
            isento = is_isento_ir(produto)

        maturity_raw = pd.to_datetime(row.get("Vencimento"), errors="coerce")
        maturity = maturity_raw.date() if pd.notna(maturity_raw) else None

        bd = taxes_at(
            lots, indexador=indexador, taxa=taxa, rates=rates,
            target=today, classe=classe, isento=isento, produto=produto,
        )
        positions.append(Position(
            name=name, classe=classe, produto=produto,
            instituicao=str(row.get("Instituição") or ""),
            indexador=indexador, taxa=taxa, isento=isento, maturity=maturity,
            principal=bd.principal, gross_today=bd.gross, net_today=bd.net,
            iof_today=bd.iof, ir_today=bd.ir, lots=lots,
        ))
    return positions


# ---------------------------------------------------------------------------
# Projeção temporal (para gráficos e decisão de resgate)
# ---------------------------------------------------------------------------

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
    # mensal — é a data que mais interessa para decidir o resgate.
    if position.maturity and position.maturity > today:
        if not rows or rows[-1]["Data"] < position.maturity:
            bd = taxes_at(
                position.lots, indexador=position.indexador,
                taxa=position.taxa, rates=rates, target=position.maturity,
                classe=position.classe, isento=position.isento,
                produto=position.produto,
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
            # Após o vencimento, o dinheiro é considerado resgatado e parado
            # (não continua rendendo à taxa do papel vencido).
            effective = min(target, p.maturity) if p.maturity else target
            bd = taxes_at(
                p.lots, indexador=p.indexador, taxa=p.taxa, rates=rates,
                target=effective, classe=p.classe, isento=p.isento,
                produto=p.produto,
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
    """Próxima data em que a alíquota de IR cai, e as alíquotas envolvidas.

    Retorna (data, aliquota_atual, proxima_aliquota) ou None se já está na
    menor faixa, se o produto é isento ou se é renda variável.
    """
    if position.isento or position.classe in CLASSES_RENDA_VARIAVEL:
        return None
    today = today or date.today()
    if not position.lots:
        return None

    # O lote mais recente é o que ainda tem degraus a percorrer.
    newest = max(lot.application_date for lot in position.lots)
    days_held = (today - newest).days
    curto = position.produto in PRODUTOS_CURTO_PRAZO
    rate_fn = ir_rate_fundo_curto_prazo if curto else ir_rate_renda_fixa
    thresholds = (180,) if curto else (180, 360, 720)
    for threshold in thresholds:
        if days_held <= threshold:
            step_date = newest + timedelta(days=threshold + 1)
            current = rate_fn(days_held)
            nxt = rate_fn(threshold + 1)
            if nxt < current:
                return step_date, current, nxt
    return None
