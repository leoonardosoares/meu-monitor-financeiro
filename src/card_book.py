"""Livro de faturas: o cartão como o banco o vê, montado num lugar só.

Por que este módulo existe
--------------------------
A tela do cartão juntava três fontes — o saldo da conta de cartão, o
total da fatura emitida e a soma das linhas da planilha — e por cima
delas um punhado de heurísticas de correção, cada uma decidindo um
pedaço. As fontes nunca concordavam entre si, e cada remendo acrescentava
uma quarta opinião. O resultado era o número que não batia com o banco.

Aqui há uma hierarquia única, aplicada sempre na mesma ordem:

1. **O que o banco informa vence o que o app deduz.** O total, o
   fechamento e o vencimento de uma fatura emitida vêm de `/bills`. As
   datas da fatura aberta vêm de `creditData` da conta. Limite e
   disponível também.
2. **As compras gravadas explicam o total, não o substituem.** Quando o
   banco emitiu a fatura, a soma das compras é só o detalhamento — e a
   diferença aparece como "compras que não chegaram", em vez de mudar o
   número.
3. **Sem fatura emitida, o total é a soma das compras**, mais as parcelas
   contratadas que ainda vão cair ali.
4. **Parcela futura é derivada, nunca gravada.** Ela é recalculada a cada
   desenho a partir das parcelas que o banco já cobrou. Gravá-la criava
   uma linha que precisava ser apagada quando a cobrança real chegasse —
   e cada falha nessa limpeza contava a parcela duas vezes.
5. **Fatura vencida é fatura paga.** O app não tem como ver o pagamento
   (ele sai do extrato da conta, não do cartão), e toda vez que tentou
   inferir dívida vencida pela data, errou. Se alguma fatura de fato não
   foi paga, o limite usado que o banco informa acusa a diferença — e a
   tela mostra essa diferença com o valor.

Nada aqui lê planilha nem desenha tela: entra DataFrame, sai estrutura.
É isso que permite testar cada regra contra o caso real que a quebrou.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from src import credit_card as cc
from src import reconcile
from src.config import ORIGEM_PROJECAO
from src.dates import month_label, parse_month_label

# Situações, na ordem em que importam para quem vai pagar.
ABERTA = "Aberta"
A_PAGAR = "A pagar"
FUTURA = "Futura"
PAGA = "Paga"

FONTE_BANCO = "banco"
FONTE_COMPRAS = "compras"

# Diferença abaixo disto é arredondamento, IOF de centavos, ou compra
# ainda autorizando — não vale um aviso.
TOLERANCIA = 1.0


@dataclass(frozen=True)
class Fatura:
    """Uma fatura de um cartão, com a origem de cada número declarada."""
    cartao: str
    mes: str                         # "MM/AAAA", o mês em que ela fecha
    fechamento: date
    vencimento: date
    total: float                     # o que vai ser cobrado
    fonte: str                       # FONTE_BANCO | FONTE_COMPRAS
    situacao: str
    compras: pd.DataFrame            # linhas gravadas desta fatura
    projetadas: tuple[dict, ...]     # parcelas deduzidas que caem aqui
    datas_do_banco: bool             # fechamento/vencimento informados

    @property
    def soma_compras(self) -> float:
        if self.compras.empty or "Valor" not in self.compras.columns:
            return 0.0
        return float(pd.to_numeric(self.compras["Valor"],
                                   errors="coerce").fillna(0).sum())

    @property
    def soma_projetadas(self) -> float:
        return float(sum(p["Valor"] for p in self.projetadas))

    @property
    def nao_chegaram(self) -> float:
        """Quanto do total do banco não tem compra correspondente aqui.

        Só faz sentido quando o total veio do banco: é a parte da fatura
        que a importação ainda não trouxe. Positivo = falta compra;
        negativo = sobra (compra repetida ou no mês errado).
        """
        if self.fonte != FONTE_BANCO:
            return 0.0
        return round(self.total - self.soma_compras - self.soma_projetadas, 2)


@dataclass(frozen=True)
class CartaoLivro:
    """Um cartão inteiro: limites, faturas e a conferência com o banco."""
    nome: str
    instituicao: str
    limite: float | None
    disponivel: float | None
    usado_banco: float | None        # limite usado, segundo o banco
    limites_do_banco: bool
    publica_faturas: bool            # o banco devolve /bills deste cartão
    datas_estimadas: bool            # sem datas do banco nem do cadastro
    faturas: tuple[Fatura, ...]
    ilegiveis: tuple[str, ...] = field(default_factory=tuple)

    def _com(self, situacao: str) -> list[Fatura]:
        return [f for f in self.faturas if f.situacao == situacao]

    @property
    def atual(self) -> Fatura | None:
        abertas = self._com(ABERTA)
        return abertas[0] if abertas else None

    @property
    def a_pagar(self) -> list[Fatura]:
        return self._com(A_PAGAR)

    @property
    def futuras(self) -> list[Fatura]:
        return self._com(FUTURA)

    @property
    def pagas(self) -> list[Fatura]:
        return sorted(self._com(PAGA), key=lambda f: f.fechamento,
                      reverse=True)

    @property
    def proxima_a_vencer(self) -> Fatura | None:
        """A primeira que vai sair da conta: fechada a pagar, ou a aberta."""
        candidatas = self.a_pagar + ([self.atual] if self.atual else [])
        return min(candidatas, key=lambda f: f.vencimento, default=None)

    @property
    def compromisso(self) -> float:
        """Tudo que ainda vai ser cobrado: a pagar, aberta e futuras."""
        return round(sum(f.total for f in self.faturas
                         if f.situacao != PAGA), 2)

    @property
    def diferenca_banco(self) -> float | None:
        """Limite usado do banco menos o que as faturas explicam.

        É a conferência que fecha o livro. O limite usado inclui tudo que
        está comprometido — parcelas futuras também —, então deve bater
        com a soma das faturas não pagas. Positivo: o banco cobra algo que
        o app não tem (compra que não chegou, ou fatura de fato não paga).
        Negativo: o app tem algo que o banco não cobra.
        """
        if self.usado_banco is None:
            return None
        return round(self.usado_banco - self.compromisso, 2)


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------

def _datas(valor) -> date | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    lida = pd.to_datetime(str(valor).strip(), errors="coerce")
    return None if pd.isna(lida) else lida.date()


def bills_by_month(df_bills: pd.DataFrame, card: str) -> dict[str, dict]:
    """{mês: fatura do banco} de um cartão, a leitura mais recente de cada."""
    if df_bills is None or df_bills.empty or "Cartão" not in df_bills.columns:
        return {}
    base = df_bills[df_bills["Cartão"].astype(str).str.strip()
                    == str(card).strip()].copy()
    if base.empty:
        return {}
    if "Lido em" in base.columns:
        base = base.sort_values("Lido em", kind="stable")
    out: dict[str, dict] = {}
    for _, linha in base.iterrows():
        mes = cc._month_key(linha.get("Mês"))
        if parse_month_label(mes) is None:
            continue
        total = pd.to_numeric(linha.get("Total"), errors="coerce")
        out[mes] = {
            "total": 0.0 if pd.isna(total) else float(total),
            "fechamento": _datas(linha.get("Fechamento")),
            "vencimento": _datas(linha.get("Vencimento")),
        }
    return out


def facts_only(df: pd.DataFrame) -> pd.DataFrame:
    """As linhas que são fato: tira projeções gravadas por versões antigas.

    O app gravava parcelas deduzidas na planilha. Agora elas são
    calculadas na hora, e uma gravada contaria a mesma parcela duas vezes
    — a gravada e a recalculada.
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    if "Origem" not in df.columns:
        return df
    origem = df["Origem"].astype(str).str.strip().str.casefold()
    return df[origem != ORIGEM_PROJECAO.casefold()]


def build_card(*, card: str, compras: pd.DataFrame, df_bills: pd.DataFrame,
               df_cards: pd.DataFrame, conta=None, today: date) -> CartaoLivro:
    """Monta um cartão: as faturas, cada uma com sua situação e fonte.

    `conta` é a conta da Pluggy deste cartão (ver
    `positions.card_accounts`), com limite, disponível e as datas da
    fatura aberta. Pode faltar: o cartão funciona só com o cadastro, e a
    tela diz que os números são deduzidos.
    """
    hoje = pd.Timestamp(today).normalize().date()
    settings = cc.card_settings(df_cards, card)
    cadastrado = cc.has_registered_dates(df_cards, card)

    base = facts_only(compras)
    if not base.empty and "Cartão" in base.columns:
        base = base[cc._card_series(base) == str(card).strip()]
    else:
        base = base.iloc[0:0] if not base.empty else pd.DataFrame()

    meses_linhas = (cc._month_series(base) if not base.empty
                    else pd.Series(dtype=str))
    ilegiveis = sorted({
        str(m) for m in meses_linhas if parse_month_label(m) is None})
    if not base.empty:
        base = base.assign(_mes=meses_linhas)
        base = base[base["_mes"].map(parse_month_label).notna()]

    do_banco = bills_by_month(df_bills, card)
    projetadas = reconcile.project_installments(
        base.drop(columns=["_mes"], errors="ignore") if not base.empty
        else base,
        today=hoje, faturadas={(card, m) for m in do_banco})

    # A fatura aberta segundo o banco: o `balanceCloseDate` da conta é o
    # fechamento real deste ciclo, inclusive quando um feriado o tira do
    # dia cadastrado.
    aberta_fecha = _datas(getattr(conta, "fecha", "")) if conta else None
    aberta_vence = _datas(getattr(conta, "vence", "")) if conta else None
    mes_aberta_banco = (month_label(pd.Timestamp(aberta_fecha))
                        if aberta_fecha else None)

    meses = set(do_banco) | {p["Mês da Fatura"] for p in projetadas}
    if not base.empty:
        meses |= set(base["_mes"])
    if mes_aberta_banco:
        meses.add(mes_aberta_banco)

    faturas: list[Fatura] = []
    for mes in meses:
        conta_banco = do_banco.get(mes)
        fech = venc = None
        datas_banco = False
        if conta_banco and conta_banco["fechamento"] and conta_banco["vencimento"]:
            fech, venc = conta_banco["fechamento"], conta_banco["vencimento"]
            datas_banco = True
        elif mes == mes_aberta_banco and aberta_fecha and aberta_vence:
            fech, venc = aberta_fecha, aberta_vence
            datas_banco = True
        else:
            try:
                f, v = cc.invoice_dates(mes, int(settings["fechamento"]),
                                        int(settings["vencimento"]))
            except ValueError:
                ilegiveis.append(mes)
                continue
            fech, venc = f.date(), v.date()

        compras_mes = (base[base["_mes"] == mes].drop(columns=["_mes"])
                       if not base.empty else pd.DataFrame())
        proj_mes = tuple(p for p in projetadas if p["Mês da Fatura"] == mes)

        if conta_banco is not None:
            total, fonte = conta_banco["total"], FONTE_BANCO
        else:
            soma = (float(pd.to_numeric(compras_mes["Valor"], errors="coerce")
                          .fillna(0).sum())
                    if not compras_mes.empty else 0.0)
            total = soma + sum(p["Valor"] for p in proj_mes)
            fonte = FONTE_COMPRAS

        # Mês sem nada — nem total do banco, nem compra, nem parcela — não
        # é fatura. Só entra se for a aberta que o banco indicou, para a
        # tela poder dizer "nada nesta fatura ainda" com as datas certas.
        if (abs(total) < 0.005 and compras_mes.empty and not proj_mes
                and mes != mes_aberta_banco):
            continue

        faturas.append(Fatura(
            cartao=card, mes=mes, fechamento=fech, vencimento=venc,
            total=round(float(total), 2), fonte=fonte, situacao="",
            compras=compras_mes, projetadas=proj_mes,
            datas_do_banco=datas_banco,
        ))

    faturas = _classificar(faturas, hoje)
    # A aberta que o banco indicou entra mesmo vazia, para as datas
    # certas aparecerem. Mas se outra fatura com compras ficou com o
    # papel de aberta (o rótulo calculado e o fechamento do banco caíram
    # em meses diferentes), a vazia empurrada para "futura" é só ruído.
    faturas = [f for f in faturas
               if not (f.situacao == FUTURA and abs(f.total) < 0.005
                       and f.compras.empty and not f.projetadas)]

    limite = getattr(conta, "limite", None) if conta else None
    disponivel = getattr(conta, "disponivel", None) if conta else None
    limites_do_banco = limite is not None and disponivel is not None
    if limite is None:
        limite = float(settings["limite"]) if settings["limite"] else None
    usado = conta.usado if (conta is not None and limites_do_banco) else None
    if disponivel is None and limite is not None:
        compromisso = sum(f.total for f in faturas if f.situacao != PAGA)
        disponivel = limite - compromisso

    return CartaoLivro(
        nome=card, instituicao=settings["instituicao"],
        limite=limite, disponivel=disponivel, usado_banco=usado,
        limites_do_banco=limites_do_banco,
        publica_faturas=bool(do_banco),
        datas_estimadas=not cadastrado and not do_banco and not aberta_fecha,
        faturas=tuple(faturas), ilegiveis=tuple(sorted(set(ilegiveis))),
    )


def _classificar(faturas: list[Fatura], hoje: date) -> list[Fatura]:
    """Dá a cada fatura a sua situação, pelas datas.

    - venceu → **Paga**. O app não vê o pagamento; o limite usado do banco
      é quem acusa uma fatura que de fato ficou para trás.
    - fechou e não venceu → **A pagar**.
    - ainda não fechou → a primeira é a **Aberta**; as seguintes,
      **Futuras**. "Primeira" pelo fechamento, por cartão.
    """
    ordenadas = sorted(faturas, key=lambda f: f.fechamento)
    aberta_marcada = False
    out: list[Fatura] = []
    for f in ordenadas:
        if f.vencimento < hoje:
            situacao = PAGA
        elif f.fechamento < hoje:
            situacao = A_PAGAR
        elif not aberta_marcada:
            situacao = ABERTA
            aberta_marcada = True
        else:
            situacao = FUTURA
        out.append(_com_situacao(f, situacao))
    return out


def _com_situacao(f: Fatura, situacao: str) -> Fatura:
    return Fatura(
        cartao=f.cartao, mes=f.mes, fechamento=f.fechamento,
        vencimento=f.vencimento, total=f.total, fonte=f.fonte,
        situacao=situacao, compras=f.compras, projetadas=f.projetadas,
        datas_do_banco=f.datas_do_banco,
    )


def build(*, compras: pd.DataFrame, df_bills: pd.DataFrame,
          df_cards: pd.DataFrame, contas: dict | None = None,
          today: date) -> list[CartaoLivro]:
    """Todos os cartões: os cadastrados e os que aparecem nas compras."""
    nomes = cc.list_card_names(df_cards, facts_only(compras))
    contas = contas or {}
    return [build_card(card=n, compras=compras, df_bills=df_bills,
                       df_cards=df_cards, conta=contas.get(n), today=today)
            for n in nomes]


# ---------------------------------------------------------------------------
# Para o resto do app
# ---------------------------------------------------------------------------

def due_through(livros: list[CartaoLivro], ate: date) -> list[Fatura]:
    """Faturas não pagas que vencem até `ate` — o que sai da conta até lá.

    É a pergunta do "próximo mês": quanto das faturas sai do dinheiro que
    está na conta hoje. Inclui a aberta e as fechadas, e as futuras só se
    vencerem dentro do prazo.
    """
    return sorted(
        (f for c in livros for f in c.faturas
         if f.situacao != PAGA and f.vencimento <= ate),
        key=lambda f: f.vencimento)


def load(*, df_credit_card: pd.DataFrame, df_cards: pd.DataFrame,
         today: date | None = None) -> list[CartaoLivro]:
    """O livro montado com o que está guardado: a única porta de entrada.

    Cartão e Dashboard chamam esta mesma função. Antes cada tela montava
    os seus números por um caminho próprio, e os dois caminhos davam
    valores diferentes para a mesma fatura.
    """
    # Importados aqui para o resto do módulo continuar puro e importável
    # nos testes sem credenciais.
    from src import positions, repository
    from src import pluggy_import as pi
    from src.config import ConfigKeys

    posicao = positions.from_rows(repository.load_positions())
    mapa = pi.parse_mapping(repository.load_config_text(ConfigKeys.PLUGGY_MAPA))
    return build(compras=df_credit_card, df_bills=repository.load_bank_bills(),
                 df_cards=df_cards,
                 contas=positions.card_accounts(posicao, mapa),
                 today=today or date.today())


def read_at() -> str:
    """Quando a posição foi lida do banco pela última vez (ISO), ou vazio."""
    from src import positions, repository
    return positions.from_rows(repository.load_positions()).quando
