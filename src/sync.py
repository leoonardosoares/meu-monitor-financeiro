"""Sincronização: o banco entra na planilha sozinho, e a planilha se mantém.

Uma chamada a `run` faz tudo, sempre na mesma ordem, e pode rodar quantas
vezes for preciso — cada passo é idempotente:

1. lê saldos, limites e investimentos (posição real);
2. lê as faturas emitidas e guarda o total, o fechamento e o vencimento;
3. aprende os dias de fechamento e vencimento de cada cartão;
4. grava os lançamentos novos, já com a categoria sugerida;
5. **realinha o mês de fatura** das compras que o banco já faturou;
6. arruma a aba do cartão: tira projeções gravadas por versões antigas e
   arquiva (não apaga) cópias e parcelamentos digitados à mão que o banco
   já cobre;
7. marca como paga cada compra de fatura vencida.

Antes, os passos 5 a 7 eram botões numa aba de ajustes — e enquanto
ninguém clicava, o cartão mostrava um número que não era o do banco. O
passo 5 nem existia: o mês da fatura era decidido na importação e nunca
mais revisto. Uma compra importada antes de a fatura fechar ganhava o mês
por dedução pelo dia de fechamento; quando o banco fechava a fatura e
dizia a qual ela pertencia, o app já tinha pulado aquela compra, porque o
id estava na lista de importados. A compra ficava no mês errado para
sempre.

As funções puras ficam no topo e são testadas sem rede nem planilha; o
`run` no fim só as encadeia com a Pluggy e o repositório.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from src import card_book as cb
from src import credit_card as cc
from src import pluggy_import as pi
from src import reconcile
from src.config import ORIGEM_PROJECAO

# Um lote acima disto, numa sincronização de rotina, quase sempre é o
# período já digitado à mão voltando pela importação. Não se grava sem o
# usuário confirmar.
LOTE_SUSPEITO = 150


# ---------------------------------------------------------------------------
# Passos puros
# ---------------------------------------------------------------------------

def bank_months(transactions: list[dict], bills: list[dict], *,
                closing_day: int, due_day: int) -> dict[str, str]:
    """{id da compra: mês da fatura} segundo o banco.

    Só entra compra que o banco já ligou a uma fatura (`billId`). Compra
    da fatura ainda aberta não tem essa ligação, e para ela vale o mês
    gravado — que o banco corrige assim que fechar a fatura.
    """
    indice = pi.bill_index(bills or [], closing_day=closing_day,
                           due_day=due_day)
    if not indice:
        return {}
    out: dict[str, str] = {}
    for tx in transactions or []:
        pid = str(tx.get("id") or "").strip()
        mes = indice.get(pi.bill_id(tx))
        if pid and mes:
            out[pid] = mes
    return out


def realign_months(df: pd.DataFrame, meses: dict[str, str]
                   ) -> tuple[pd.DataFrame, int]:
    """Põe cada compra na fatura em que o banco a cobrou.

    Devolve (aba atualizada, quantas mudaram). Só toca linha com id do
    banco; o que foi digitado à mão não tem como ser casado.
    """
    if df.empty or not meses or "ID Pluggy" not in df.columns:
        return df, 0
    ids = df["ID Pluggy"].astype(str).str.strip()
    novos = ids.map(meses)
    atuais = cc._month_series(df)
    mudar = novos.notna() & (novos != atuais)
    if not mudar.any():
        return df, 0
    out = df.copy()
    out.loc[mudar, "Mês da Fatura"] = novos[mudar]
    return out, int(mudar.sum())


@dataclass
class Arrumacao:
    manter: pd.DataFrame
    arquivar: pd.DataFrame
    projecoes: int = 0
    copias: int = 0
    parcelamentos_manuais: int = 0

    @property
    def mudou(self) -> bool:
        return bool(self.projecoes or self.copias
                    or self.parcelamentos_manuais)


def housekeeping(df: pd.DataFrame, *, today: date) -> Arrumacao:
    """Separa da aba do cartão o que não é fato.

    - **Projeção gravada** (versões antigas gravavam parcela deduzida):
      sai, porque agora é recalculada a cada desenho — gravada, contaria
      duas vezes. Não vai para o arquivo; não há nada a guardar.
    - **Cópia digitada de compra que veio do banco**: vai para o arquivo.
      A do banco fica.
    - **Parcelamento digitado à mão** (a compra espalhada em N meses de
      uma vez, sem nenhuma parcela do banco no grupo): as parcelas futuras
      vão para o arquivo. O banco cobra cada uma no mês certo, e o app já
      deduz as que faltam.

    Arquivar, e não apagar: a aba `arquivo_cartao` guarda tudo com a data,
    e nada que o usuário digitou se perde por uma regra automática.
    """
    if df.empty:
        return Arrumacao(manter=df, arquivar=df.iloc[0:0])

    base = df.reset_index(drop=True)
    sair: set[int] = set()

    projecoes = 0
    if "Origem" in base.columns:
        origem = base["Origem"].astype(str).str.strip().str.casefold()
        proj = base.index[origem == ORIGEM_PROJECAO.casefold()]
        projecoes = len(proj)
        base = base.drop(index=proj).reset_index(drop=True)

    copias = _copias_de_compra_do_banco(base)
    sair |= set(copias)

    manuais = reconcile.manual_future_rows(base.drop(index=list(sair)),
                                           today=today)
    sair |= set(manuais)

    idx = sorted(sair)
    return Arrumacao(
        manter=base.drop(index=idx).reset_index(drop=True),
        arquivar=base.loc[idx].reset_index(drop=True),
        projecoes=projecoes, copias=len(copias),
        parcelamentos_manuais=len(manuais),
    )


def _copias_de_compra_do_banco(df: pd.DataFrame) -> list[int]:
    """Linhas SEM id idênticas a uma linha COM id.

    É o único caso de duplicata que se resolve sem perguntar: a linha do
    banco é a verdade, e a digitada é a mesma compra lançada de novo. Duas
    linhas sem id iguais podem ser duas compras iguais de verdade (dois
    cafés), então ficam.
    """
    if "ID Pluggy" not in df.columns:
        return []
    chaves = [c for c in reconcile.CHAVES_CARTAO if c in df.columns]
    if not chaves:
        return []
    norm = df[chaves].astype(str).apply(lambda s: s.str.strip())
    if "Valor" in norm.columns:
        norm["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").round(2)
    tem_id = df["ID Pluggy"].astype(str).str.strip() != ""
    do_banco = set(map(tuple, norm[tem_id].itertuples(index=False)))
    return [i for i, chave in zip(norm.index[~tem_id],
                                  norm[~tem_id].itertuples(index=False))
            if tuple(chave) in do_banco]


def settle_status(df: pd.DataFrame, livros: list[cb.CartaoLivro]
                  ) -> tuple[pd.DataFrame, int]:
    """Status "Pago" nas compras de fatura que já venceu.

    O livro de faturas não depende desta coluna — ele decide pela data.
    Mas outras telas (orçamento, insights) ainda a leem, e uma compra paga
    marcada como pendente infla "quanto falta pagar" em todas elas.
    """
    if df.empty or "Status" not in df.columns:
        return df, 0
    pagas = {(f.cartao, f.mes) for c in livros for f in c.pagas}
    if not pagas:
        return df, 0
    chaves = pd.Series(list(zip(cc._card_series(df), cc._month_series(df))),
                       index=df.index)
    alvo = chaves.map(lambda k: k in pagas) & ~cc._is_settled(df)
    if not alvo.any():
        return df, 0
    out = df.copy()
    out.loc[alvo, "Status"] = "Pago"
    return out, int(alvo.sum())


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass
class Resultado:
    quando: str = ""
    novos_conta: int = 0
    novos_cartao: int = 0
    realinhadas: int = 0
    arquivadas: int = 0
    projecoes_removidas: int = 0
    baixas: int = 0
    faturas_lidas: int = 0
    datas_aprendidas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    # Lote grande demais para gravar sem perguntar (ver LOTE_SUSPEITO).
    retidos: list = field(default_factory=list)

    @property
    def falhou(self) -> bool:
        return bool(self.erros) and not (
            self.novos_conta or self.novos_cartao or self.faturas_lidas)

    def resumo(self) -> str:
        partes = []
        if self.novos_conta or self.novos_cartao:
            partes.append(f"{self.novos_conta + self.novos_cartao} "
                          "lançamento(s) novo(s)")
        if self.realinhadas:
            partes.append(f"{self.realinhadas} compra(s) movida(s) para a "
                          "fatura em que o banco as cobrou")
        if self.baixas:
            partes.append(f"{self.baixas} compra(s) de faturas vencidas "
                          "marcadas como pagas")
        if self.arquivadas:
            partes.append(f"{self.arquivadas} linha(s) digitada(s) que o "
                          "banco já cobre foram para o arquivo")
        if self.projecoes_removidas:
            partes.append(f"{self.projecoes_removidas} parcela(s) projetada"
                          "(s) gravadas por versão antiga removidas")
        return " · ".join(partes) if partes else "Tudo já estava em dia."


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def run(*, ids: list[str], today: date, confirmar_lote: bool = False,
        sugerir=None) -> Resultado:
    """Sincroniza tudo com o banco. Não desenha nada.

    `confirmar_lote` libera a gravação de um lote acima de LOTE_SUSPEITO
    — o usuário viu o tamanho e disse que é isso mesmo.
    """
    # Importados aqui para o módulo continuar importável nos testes, que
    # não têm credenciais.
    from src import pluggy, positions, repository
    from src.config import ConfigKeys

    res = Resultado(quando=datetime.now().isoformat(timespec="minutes"))
    df_cards = repository.load_cards()
    mapa = pi.parse_mapping(repository.load_config_text(ConfigKeys.PLUGGY_MAPA))

    # 1. Posição: saldos, limites, datas da fatura aberta, investimentos.
    posicao = positions.fetch(ids)
    res.erros += list(posicao.erros)
    if not posicao.vazia:
        repository.append_position(positions.to_rows(posicao))

    # 2. Contas mapeadas, com transações e faturas.
    contas: list[dict] = []
    for item_id in ids:
        try:
            contas += pluggy.list_accounts(item_id)
        except pluggy.PluggyError as exc:
            res.erros.append(f"Conexão {item_id[:8]}…: {exc}")
    ativas = [c for c in contas
              if mapa.get(pi.account_key(c), "") not in ("", pi.DESTINO_IGNORAR)]

    transacoes: dict[str, list[dict]] = {}
    faturas: dict[str, list[dict]] = {}
    for conta in ativas:
        chave = pi.account_key(conta)
        try:
            transacoes[chave] = pluggy.list_transactions(chave)
        except pluggy.PluggyError as exc:
            res.erros.append(f"{pi.account_label(conta)}: {exc}")
        if str(conta.get("type") or "").upper() == "CREDIT":
            try:
                faturas[chave] = pluggy.list_bills(chave)
            except pluggy.PluggyError as exc:
                res.erros.append(f"{pi.account_label(conta)} (faturas): {exc}")

    # 3. Dias de fechamento e vencimento, aprendidos do banco.
    df_cards, res.datas_aprendidas = _aprender_datas(
        ativas, mapa, transacoes, faturas, df_cards)
    if res.datas_aprendidas:
        repository.save_cards(df_cards)

    # 4. Faturas emitidas.
    linhas_fatura: list[dict] = []
    meses_do_banco: dict[str, str] = {}
    for conta in ativas:
        chave = pi.account_key(conta)
        destino = mapa.get(chave, "")
        if chave not in faturas or destino in (pi.DESTINO_BANCO,):
            continue
        s = cc.card_settings(df_cards, destino)
        fech, venc = int(s["fechamento"]), int(s["vencimento"])
        linhas_fatura += pi.bill_rows(faturas[chave], cartao=destino,
                                      closing_day=fech, due_day=venc,
                                      lido_em=today)
        meses_do_banco.update(bank_months(
            transacoes.get(chave, []), faturas[chave],
            closing_day=fech, due_day=venc))
    if linhas_fatura:
        repository.merge_bank_bills(linhas_fatura)
        res.faturas_lidas = len(linhas_fatura)

    # 5. Lançamentos novos, gravados já com a categoria sugerida.
    desde_txt = repository.load_config_text(ConfigKeys.PLUGGY_DESDE)
    try:
        desde = date.fromisoformat(desde_txt) if desde_txt else None
    except ValueError:
        desde = None
    pendentes, avisos = pi.build_pending(
        accounts=[(c, mapa.get(pi.account_key(c), "")) for c in ativas],
        transactions=transacoes, ja_importados=repository.imported_ids(),
        df_cards=df_cards, desde=desde, bills=faturas, sugerir=sugerir)
    res.avisos += avisos

    if len(pendentes) > LOTE_SUSPEITO and not confirmar_lote:
        res.retidos = pendentes
        pendentes = []

    if pendentes:
        banco, cartao, registro = pi.to_rows(pendentes)
        if banco:
            base = repository.load_transactions().drop(
                columns=["Data_DT", "Mes_Ano"], errors="ignore")
            repository.save_transactions(
                pd.concat([base, pd.DataFrame(banco)], ignore_index=True))
        if cartao:
            repository.save_credit_card(pd.concat(
                [repository.load_credit_card(), pd.DataFrame(cartao)],
                ignore_index=True))
        # Por último: se algo falhar antes, a próxima sincronização traz
        # os mesmos lançamentos de volta. Repetir é recuperável; marcar
        # como importado o que não foi gravado, não.
        repository.save_imports(pd.concat(
            [repository.load_imports(), pd.DataFrame(registro)],
            ignore_index=True))
        res.novos_conta, res.novos_cartao = len(banco), len(cartao)

    # 6 e 7. A aba do cartão se arruma sozinha.
    df = repository.load_credit_card()
    df, res.realinhadas = realign_months(df, meses_do_banco)
    arr = housekeeping(df, today=today)
    df = arr.manter
    res.projecoes_removidas = arr.projecoes
    res.arquivadas = arr.copias + arr.parcelamentos_manuais
    if not arr.arquivar.empty:
        repository.save_archive("arquivo_cartao", arr.arquivar.assign(
            **{"Arquivado em": today.isoformat()}))

    livros = cb.build(
        compras=df, df_bills=repository.load_bank_bills(), df_cards=df_cards,
        contas=positions.card_accounts(posicao, mapa), today=today)
    df, res.baixas = settle_status(df, livros)

    if res.realinhadas or arr.mudou or res.baixas:
        repository.save_credit_card(df)

    repository.save_config_text(ConfigKeys.PLUGGY_ULTIMA_SYNC, res.quando)
    return res


def _aprender_datas(ativas, mapa, transacoes, faturas,
                    df_cards: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Fechamento e vencimento de cada cartão, deduzidos do banco.

    Devolve (cadastro atualizado, descrição do que mudou). Só muda o que
    difere, para não regravar a planilha a cada sincronização.
    """
    if df_cards.empty or "Nome" not in df_cards.columns:
        return df_cards, []
    cards = df_cards.copy()
    mudancas: list[str] = []
    for conta in ativas:
        chave = pi.account_key(conta)
        destino = mapa.get(chave, "")
        if (str(conta.get("type") or "").upper() != "CREDIT"
                or destino in ("", pi.DESTINO_BANCO, pi.DESTINO_IGNORAR)):
            continue
        fech, venc = pi.infer_card_days(faturas.get(chave, []),
                                        transacoes.get(chave, []))
        atual = cc.card_settings(cards, destino)
        alvo = cards["Nome"].astype(str).str.strip() == destino
        if not alvo.any():
            continue
        partes = []
        if fech and fech != int(atual["fechamento"]):
            cards.loc[alvo, "Dia Fechamento"] = fech
            partes.append(f"fecha dia {fech}")
        if venc and venc != int(atual["vencimento"]):
            cards.loc[alvo, "Dia Vencimento"] = venc
            partes.append(f"vence dia {venc}")
        if partes:
            mudancas.append(f"{destino}: " + ", ".join(partes))
    return cards, mudancas


def stale(carimbo: str, *, hours: float, now: datetime | None = None) -> bool:
    """Se a última sincronização é antiga o bastante para valer outra."""
    if not carimbo:
        return True
    try:
        quando = datetime.fromisoformat(carimbo)
    except ValueError:
        return True
    agora = now or datetime.now()
    return (agora - quando).total_seconds() >= hours * 3600
