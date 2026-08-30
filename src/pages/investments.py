"""Página: Investimentos — carteira por ativo, tributação, projeção e metas."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import components, investments as inv, repository
from src.config import Colors, ConfigKeys
from src.finance import compute_wealth, monthly_investment_contributions
from src.format import brl


def _market_rates() -> inv.MarketRates:
    """Premissas de mercado salvas nas configurações."""
    return inv.MarketRates(
        cdi=repository.load_config(ConfigKeys.TAXA_CDI, 13.90),
        selic=repository.load_config(ConfigKeys.TAXA_SELIC, 14.00),
        ipca=repository.load_config(ConfigKeys.TAXA_IPCA, 4.44),
        tr=repository.load_config(ConfigKeys.TAXA_TR, 0.1709),
    )


def render(*, df_transactions: pd.DataFrame) -> None:
    components.page_header(
        "Meus Investimentos",
        "Cadastre cada ativo, acompanhe a posição líquida de impostos e "
        "projete o melhor momento para resgatar.",
    )

    tabs = st.tabs([
        "🧾 Carteira",
        "💸 Movimentações",
        "📌 Posição Atual",
        "🔮 Projeção e Resgate",
        "🎯 Metas",
    ])

    wealth = compute_wealth(df_transactions, df_transactions)
    invested = wealth.invested

    rates = _market_rates()
    df_assets = repository.load_assets()
    df_moves = repository.load_asset_moves()
    df_snapshots = repository.load_asset_snapshots()
    positions = inv.build_positions(
        df_assets, df_moves, rates, df_snapshots=df_snapshots,
    )

    with tabs[0]:
        _wallet_tab(df_assets=df_assets, df_moves=df_moves,
                    positions=positions, rates=rates)
    with tabs[1]:
        _moves_tab(df_assets=df_assets, df_moves=df_moves,
                   positions=positions, df_transactions=df_transactions)
    with tabs[2]:
        _position_tab(positions=positions, df_snapshots=df_snapshots)
    with tabs[3]:
        _projection_tab(positions=positions, rates=rates,
                        df_snapshots=df_snapshots)
    with tabs[4]:
        _goals_tab(df_transactions=df_transactions, invested=invested,
                   positions=positions)


def _goals_tab(*, df_transactions: pd.DataFrame, invested: float,
               positions: list[inv.Position]) -> None:
    """Visão das metas — sem formulários: aportes e resgates agora são
    registrados por ativo na aba Movimentações."""
    st.subheader("Reserva de emergência")
    current_goal = repository.load_config(ConfigKeys.META_RESERVA, 10000.0)
    new_goal = st.number_input(
        "Meta da reserva (R$):", min_value=100.0, value=current_goal, step=500.0,
    )
    if new_goal != current_goal:
        repository.save_config(ConfigKeys.META_RESERVA, new_goal)

    # Se há carteira montada, o valor líquido real é a melhor medida do que
    # você teria em mãos ao resgatar; senão cai no total aportado.
    liquido = sum(p.net_today for p in positions) if positions else invested
    base_label = ("valor líquido da carteira" if positions
                  else "total aportado (sem ativos cadastrados)")

    reserve = min(liquido, new_goal)
    extra = max(liquido - new_goal, 0.0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Patrimônio investido", brl(liquido),
              delta=base_label, delta_color="off")
    c2.metric("Fundo de emergência", brl(reserve))
    c3.metric("Acima da meta", brl(extra))

    progress = min(reserve / new_goal, 1.0) if new_goal > 0 else 0.0
    st.write(f"**Progresso da reserva ({progress * 100:.1f}%)**")
    st.progress(progress)
    if progress >= 1.0:
        st.success(
            "Reserva completa. O que passar da meta aparece em "
            "'Acima da meta' e pode ir para objetivos de prazo mais longo."
        )
    else:
        falta = new_goal - reserve
        st.info(f"Faltam **{brl(falta)}** para completar a reserva.")

    st.divider()
    st.subheader("Aportes mensais (últimos 12 meses)")
    st.caption(
        "Quanto entrou na carteira mês a mês, segundo os lançamentos de "
        "investimento em Entradas e Saídas."
    )
    components.monthly_contributions_bars(
        monthly_investment_contributions(df_transactions, months=12)
    )

    st.caption(
        "Para registrar um aporte ou resgate, use a aba **Movimentações** — "
        "lá o lançamento fica vinculado ao ativo e vai para o fluxo de caixa "
        "de uma vez só."
    )


def _wallet_tab(*, df_assets: pd.DataFrame, df_moves: pd.DataFrame,
                positions: list[inv.Position],
                rates: inv.MarketRates) -> None:
    st.subheader("Minha carteira")
    st.caption(
        "Cadastre cada investimento que você tem. A posição é calculada a "
        "partir das movimentações, projetada pela taxa do papel e já "
        "descontada de IOF e IR se você resgatasse hoje."
    )

    orphans = inv.orphan_moves(df_assets, df_moves)
    if not orphans.empty:
        nomes = sorted(set(orphans["Investimento"].astype(str).str.strip()))
        st.warning(
            "⚠️ Há movimentações apontando para ativos que não existem mais "
            "no cadastro: **" + "**, **".join(nomes) + "**. Cadastre um ativo "
            "com esse nome para recuperá-las, ou apague-as na aba "
            "**Movimentações**."
        )

    dups = inv.duplicate_asset_names(df_assets)
    if dups:
        st.warning(
            "⚠️ Nome repetido no cadastro: **" + "**, **".join(dups) + "**. "
            "As movimentações apontam para o ativo pelo nome, então apenas o "
            "primeiro cadastro de cada nome é usado — renomeie os demais para "
            "que a carteira fique correta."
        )

    vencidos = [
        p for p in positions
        if p.days_to_maturity is not None and p.days_to_maturity < 0
    ]
    if vencidos:
        linhas = "\n".join(
            f"- **{p.name}** — venceu em "
            f"{p.maturity.strftime('%d/%m/%Y')}, valor parado: {brl(p.net_today)}"
            for p in vencidos
        )
        st.warning(
            "⏰ **Papéis vencidos.** O emissor parou de pagar rendimento na "
            "data de vencimento, então o valor abaixo está congelado e o "
            "dinheiro está parado. Registre o resgate na aba "
            "**Movimentações** para reinvestir.\n\n" + linhas
        )

    if positions:
        _wallet_kpis(positions)
        st.divider()
        _wallet_table(positions)
        st.divider()
        _wallet_allocation(positions)
        st.divider()
    else:
        st.info(
            "Nenhum ativo com movimentação ainda. Cadastre um investimento "
            "abaixo e registre o primeiro aporte na aba **Movimentações**."
        )

    _market_assumptions(rates)
    st.divider()
    _new_asset_form()
    st.divider()
    _assets_editor(df_assets)
    _manage_asset_section(df_assets, df_moves)


def _wallet_kpis(positions: list[inv.Position]) -> None:
    principal = sum(p.principal for p in positions)
    gross = sum(p.gross_today for p in positions)
    net = sum(p.net_today for p in positions)
    taxes = sum(p.iof_today + p.ir_today for p in positions)
    yield_pct = ((gross - principal) / principal * 100) if principal else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capital aplicado", brl(principal))
    c2.metric("Valor bruto hoje", brl(gross),
              delta=f"+{yield_pct:.2f}% de rendimento",
              delta_color="normal" if gross >= principal else "inverse")
    c3.metric("Impostos se resgatar hoje", brl(taxes),
              delta="IOF + IR", delta_color="off")
    com_real = sum(1 for p in positions if p.has_real)
    c4.metric("Valor líquido hoje 💎", brl(net),
              delta=f"{brl(net - principal)} no bolso",
              delta_color="normal" if net >= principal else "inverse")
    if com_real:
        st.caption(
            f"📌 {com_real} de {len(positions)} ativo(s) usam a **posição real** "
            "informada por você; os demais usam a projeção pela taxa contratada."
        )


def _wallet_table(positions: list[inv.Position]) -> None:
    st.markdown("**Posição por ativo**")
    rows = []
    for p in positions:
        venc = p.maturity.strftime("%d/%m/%Y") if p.maturity else "Sem vencimento"
        dias = p.days_to_maturity
        if dias is not None and dias < 0:
            venc += " (vencido)"
        elif dias is not None:
            venc += f" ({dias}d)"
        rows.append({
            "Ativo": p.name,
            "Classe": p.classe,
            "Remuneração": _rate_label(p),
            "Aplicado": p.principal,
            "Bruto hoje": p.gross_today,
            "Fonte": "📌 real" if p.has_real else "projeção",
            "Impostos": p.iof_today + p.ir_today,
            "Líquido hoje": p.net_today,
            "Rende (líq.)": p.yield_net_today,
            "Vencimento": venc,
        })
    df = pd.DataFrame(rows).sort_values("Líquido hoje", ascending=False)
    display = df.copy()
    for col in ("Aplicado", "Bruto hoje", "Impostos", "Líquido hoje",
                "Rende (líq.)"):
        display[col] = display[col].apply(brl)
    st.dataframe(display, hide_index=True, use_container_width=True)


def _rate_label(p: inv.Position) -> str:
    """Descrição curta da remuneração ('110% do CDI', 'IPCA + 6,0%')."""
    if p.indexador == inv.Indexador.CDI:
        return f"{p.taxa:.0f}% do CDI"
    if p.indexador == inv.Indexador.IPCA:
        return f"IPCA + {p.taxa:.2f}%".replace(".", ",")
    if p.indexador == inv.Indexador.SELIC:
        return f"Selic + {p.taxa:.2f}%".replace(".", ",")
    if p.indexador == inv.Indexador.PREFIXADO:
        return f"{p.taxa:.2f}% a.a.".replace(".", ",")
    if p.indexador == inv.Indexador.POUPANCA:
        return "Poupança"
    return "—"


def _wallet_allocation(positions: list[inv.Position]) -> None:
    st.markdown("**Alocação da carteira**")
    df = pd.DataFrame([
        {"Classe": p.classe, "Valor": p.net_today, "Ativo": p.name}
        for p in positions
    ])
    if df.empty or df["Valor"].sum() <= 0:
        st.info("Sem valores para exibir.")
        return

    c1, c2 = st.columns(2)
    with c1:
        by_class = df.groupby("Classe")["Valor"].sum().reset_index()
        fig = px.pie(by_class, values="Valor", names="Classe", hole=0.5,
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_traces(textinfo="percent+label", textposition="inside")
        fig.update_layout(showlegend=False, height=320,
                          margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
        st.caption("Por classe de ativo")
    with c2:
        by_asset = df.sort_values("Valor", ascending=True)
        fig2 = px.bar(by_asset, x="Valor", y="Ativo", orientation="h",
                      text=[brl(v) for v in by_asset["Valor"]],
                      color_discrete_sequence=[Colors.INVESTMENT])
        fig2.update_traces(textposition="outside", cliponaxis=False)
        fig2.update_layout(height=320, xaxis_title="", yaxis_title="",
                           margin=dict(t=10, b=10, l=10, r=70))
        fig2.update_xaxes(tickprefix="R$ ")
        st.plotly_chart(fig2, use_container_width=True,
                        config={"displayModeBar": False})
        st.caption("Por ativo (valor líquido)")


def _market_assumptions(rates: inv.MarketRates) -> None:
    with st.expander("⚙️ Premissas de mercado usadas nas projeções"):
        st.caption(
            "Estes índices alimentam a projeção dos papéis pós-fixados e "
            "indexados. Atualize quando o cenário mudar."
        )
        c1, c2, c3, c4 = st.columns(4)
        cdi = c1.number_input("CDI (% a.a.)", min_value=0.0, max_value=100.0,
                              value=float(rates.cdi), step=0.25)
        selic = c2.number_input("Selic (% a.a.)", min_value=0.0, max_value=100.0,
                                value=float(rates.selic), step=0.25)
        ipca = c3.number_input("IPCA (% a.a.)", min_value=0.0, max_value=100.0,
                               value=float(rates.ipca), step=0.25)
        tr = c4.number_input("TR (% ao mês)", min_value=0.0, max_value=5.0,
                             value=float(rates.tr), step=0.01, format="%.4f",
                             help="Taxa Referencial — entra no cálculo da poupança.")
        if st.button("Salvar premissas"):
            repository.save_config(ConfigKeys.TAXA_CDI, cdi)
            repository.save_config(ConfigKeys.TAXA_SELIC, selic)
            repository.save_config(ConfigKeys.TAXA_IPCA, ipca)
            repository.save_config(ConfigKeys.TAXA_TR, tr)
            st.success("Premissas atualizadas.")
            st.rerun()
        st.caption(
            f"Poupança pela regra da Lei 12.703/2012: "
            f"**{rates.poupanca_annual:.2f}% a.a.** "
            f"(Selic {'>' if rates.selic > 8.5 else '≤'} 8,5% → "
            f"{'0,5% a.m.' if rates.selic > 8.5 else '70% da Selic'} + TR)."
        )
        st.caption(
            "⚠️ A projeção mantém estes índices **constantes** por todo o "
            "horizonte. Em projeções de vários anos isso tende a "
            "superestimar papéis pós-fixados se o mercado espera queda de "
            "juros — considere usar uma taxa média do período."
        )


def _new_asset_form() -> None:
    st.markdown("**➕ Cadastrar novo investimento**")
    with st.form("new_asset", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        nome = c1.text_input("Nome do ativo",
                             placeholder="Ex.: CDB Banco Inter 110% CDI")
        instituicao = c2.text_input("Instituição", placeholder="Ex.: Inter")

        c3, c4, c5 = st.columns(3)
        classe = c3.selectbox("Classe", inv.CLASSES)
        produto = c4.selectbox("Produto", inv.PRODUTOS)
        indexador = c5.selectbox("Remuneração", inv.INDEXADORES)

        c6, c7, c8 = st.columns(3)
        taxa = c6.number_input(
            "Taxa (%)", min_value=0.0, value=100.0, step=0.5,
            help="Prefixado → % ao ano · % do CDI → percentual do CDI · "
                 "IPCA+/Selic+ → spread anual acima do índice.",
        )
        aplicacao = c7.date_input("Data de aplicação", value=date.today(),
                                  format="DD/MM/YYYY")
        tem_vencimento = c8.checkbox("Tem vencimento?", value=True)

        vencimento = st.date_input(
            "Data de vencimento", value=date.today(), format="DD/MM/YYYY",
            disabled=not tem_vencimento,
            help="Desmarque acima para ativos de liquidez diária "
                 "(Tesouro Selic, fundos, ações).",
        )
        obs = st.text_input("Observações (opcional)")

        if st.form_submit_button("Cadastrar ativo"):
            if not nome.strip():
                st.error("Informe o nome do ativo.")
            else:
                repository.save_assets(pd.concat([
                    repository.load_assets(),
                    pd.DataFrame([{
                        "Nome": nome.strip(),
                        "Instituição": instituicao.strip(),
                        "Classe": classe,
                        "Produto": produto,
                        "Indexador": indexador,
                        "Taxa": taxa,
                        "Data Aplicação": aplicacao,
                        "Vencimento": vencimento if tem_vencimento else "",
                        "Isento IR": "Sim" if inv.is_isento_ir(produto) else "Não",
                        "Observações": obs.strip(),
                    }]),
                ], ignore_index=True))
                st.success(
                    f"'{nome.strip()}' cadastrado. Registre o aporte na aba "
                    "**Movimentações** para ele aparecer na carteira."
                )
                st.rerun()


def _assets_editor(df_assets: pd.DataFrame) -> None:
    if df_assets.empty:
        return
    with st.expander("✏️ Editar cadastro dos ativos"):
        st.caption(
            "**Isento IR**: marque `Sim` para LCI, LCA, CRI, CRA, LIG, "
            "debêntures incentivadas e poupança."
        )
        with st.form("edit_assets"):
            edited = st.data_editor(
                df_assets, num_rows="dynamic", use_container_width=True,
                hide_index=True,
                column_config={
                    "Classe": st.column_config.SelectboxColumn(
                        "Classe", options=inv.CLASSES),
                    "Produto": st.column_config.SelectboxColumn(
                        "Produto", options=inv.PRODUTOS),
                    "Indexador": st.column_config.SelectboxColumn(
                        "Remuneração", options=inv.INDEXADORES),
                    "Isento IR": st.column_config.SelectboxColumn(
                        "Isento IR", options=["Sim", "Não"]),
                    "Taxa": st.column_config.NumberColumn(
                        "Taxa (%)", format="%.2f"),
                },
            )
            if st.form_submit_button("💾 Salvar cadastro"):
                if df_assets.equals(edited):
                    st.info("Nada a salvar — sem alterações.")
                else:
                    repository.save_assets(edited)
                    st.success("Cadastro atualizado.")
                    st.rerun()


# ---------------------------------------------------------------------------
# Aba: Movimentações — aportes e resgates por ativo
def _moves_tab(*, df_assets: pd.DataFrame, df_moves: pd.DataFrame,
               positions: list[inv.Position],
               df_transactions: pd.DataFrame) -> None:
    st.subheader("Movimentações por ativo")
    st.caption(
        "Cada aporte vira um lote com data própria — é o que permite calcular "
        "o IR regressivo corretamente, já que a alíquota depende de há quanto "
        "tempo aquele dinheiro específico está aplicado."
    )

    names = (
        df_assets["Nome"].dropna().astype(str).str.strip().tolist()
        if not df_assets.empty else []
    )
    names = [n for n in names if n]

    excedentes = inv.unmatched_redemptions(df_moves)
    if excedentes:
        linhas = "\n".join(
            f"- **{nome}**: {brl(v)} de resgate sem capital aplicado que o cubra"
            for nome, v in excedentes.items()
        )
        st.error(
            "🚨 **Resgates maiores que o capital aplicado.** O excedente "
            "abaixo está sendo ignorado no cálculo da carteira. Verifique se "
            "o valor foi digitado errado ou se falta registrar um aporte "
            "anterior.\n\n" + linhas
        )

    invalidas = inv.invalid_moves(df_moves)
    if not invalidas.empty:
        st.error(
            f"🚨 {len(invalidas)} movimentação(ões) estão sendo **ignoradas** "
            "por terem data, tipo ou valor inválidos — o capital delas não "
            "aparece na carteira. O campo **Tipo** precisa ser exatamente "
            "`Aporte` ou `Resgate`."
        )
        with st.expander("Ver linhas ignoradas"):
            st.dataframe(invalidas, hide_index=True, use_container_width=True)

    _reconciliation_panel(df_transactions, df_moves)

    if not names:
        st.info("Cadastre um ativo na aba **Carteira** antes de movimentar.")
        return

    st.divider()
    _attribution_section(df_transactions, df_moves, names)

    st.divider()
    st.markdown("**➕ Nova movimentação**")
    _new_move_form(names, positions)

    if df_moves.empty:
        return

    st.divider()
    _moves_history(df_moves, names)


def _reconciliation_panel(df_transactions: pd.DataFrame,
                          df_moves: pd.DataFrame) -> None:
    """Confronta o razão de caixa (Dashboard) com a alocação por ativo."""
    summary = inv.allocation_summary(df_transactions, df_moves)
    caixa, alocado = summary["caixa"], summary["alocado"]
    pendente, descasamento = summary["diferenca"], summary["descasamento"]

    with st.container(border=True):
        st.markdown("**🔗 Conferência com o Dashboard**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Investido (Dashboard)", brl(caixa),
                  delta="lançamentos em Entradas e Saídas", delta_color="off")
        c2.metric("Alocado em ativos", brl(alocado),
                  delta="soma das movimentações", delta_color="off")
        c3.metric("Falta atribuir", brl(pendente),
                  delta_color="off" if abs(pendente) < 0.01 else "inverse")

        if abs(pendente) < 0.01:
            st.success(
                "✅ Tudo conciliado — cada lançamento de investimento está "
                "atribuído a um ativo."
            )
        else:
            st.info(
                f"Há **{brl(abs(pendente))}** em lançamentos de investimento "
                "sem ativo atribuído. Use a seção abaixo para vinculá-los."
            )

        # Descasamento de totais com tudo pareado significa movimentação sem
        # lançamento de caixa — esperado para dinheiro já aplicado antes do app.
        if abs(pendente) < 0.01 and abs(descasamento) > 0.01:
            if descasamento < 0:
                st.caption(
                    f"As movimentações somam {brl(abs(descasamento))} a mais "
                    "que o razão de caixa. É o esperado para investimentos que "
                    "já estavam aplicados antes de você usar o app "
                    "(registrados sem marcar *Lançar também em Entradas e "
                    "Saídas*)."
                )
            else:
                st.caption(
                    f"O razão de caixa soma {brl(descasamento)} a mais que as "
                    "movimentações, mas cada linha já tem par. Costuma ser "
                    "diferença entre principal resgatado e valor creditado "
                    "após impostos."
                )
        st.caption(
            "O Dashboard continua lendo os lançamentos de **Entradas e "
            "Saídas** (categoria Investimento) para saldo bancário, "
            "patrimônio e gráfico de aportes. As movimentações por ativo "
            "servem à carteira, à tributação e à projeção."
        )


def _attribution_section(df_transactions: pd.DataFrame,
                         df_moves: pd.DataFrame, names: list[str]) -> None:
    """Atribui lançamentos antigos do razão de caixa a um ativo cadastrado."""
    pending = inv.unattributed_flows(df_transactions, df_moves)
    st.markdown("**📎 Atribuir lançamentos antigos a um ativo**")

    if pending.empty:
        st.caption(
            "Nenhum lançamento pendente — todos os aportes e resgates já "
            "estão vinculados a um ativo."
        )
        return

    st.caption(
        f"{len(pending)} lançamento(s) de investimento feitos em Entradas e "
        "Saídas ainda sem ativo. Escolha o destino de cada um e confirme — "
        "isso **não** cria lançamento novo no caixa, apenas informa em qual "
        "ativo o dinheiro entrou."
    )

    editor = pending.copy()
    editor["Atribuir a"] = "— não atribuir —"
    editor = editor[["Data", "Descrição", "Movimento", "Valor", "Atribuir a"]]

    with st.form("attribute_flows"):
        edited = st.data_editor(
            editor, hide_index=True, use_container_width=True,
            disabled=["Data", "Descrição", "Movimento", "Valor"],
            column_config={
                "Valor": st.column_config.NumberColumn(
                    "Valor (R$)", format="%.2f"),
                "Movimento": st.column_config.TextColumn(
                    "Natureza", help="Aporte = saiu da conta · Resgate = voltou"),
                "Atribuir a": st.column_config.SelectboxColumn(
                    "Atribuir a", options=["— não atribuir —"] + names,
                    required=True),
            },
        )
        if st.form_submit_button("🔗 Vincular selecionados"):
            chosen = edited[edited["Atribuir a"] != "— não atribuir —"]
            if chosen.empty:
                st.warning("Escolha ao menos um ativo de destino.")
            else:
                novas = [{
                    "Data": row["Data"],
                    "Investimento": row["Atribuir a"],
                    "Tipo": row["Movimento"],
                    "Valor": float(row["Valor"]),
                    "Observação": "Atribuído do histórico",
                } for _, row in chosen.iterrows()]
                repository.save_asset_moves(pd.concat(
                    [df_moves, pd.DataFrame(novas)], ignore_index=True,
                ))
                st.success(f"{len(novas)} lançamento(s) vinculado(s).")
                st.rerun()


def _new_move_form(names: list[str], positions: list[inv.Position]) -> None:
    saldo = {p.name: p.principal for p in positions}
    with st.form("new_asset_move", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        ativo = c1.selectbox("Investimento", names)
        tipo = c2.selectbox("Tipo", ["Aporte", "Resgate"])
        c3, c4 = st.columns(2)
        data_mov = c3.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        valor = c4.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        obs = st.text_input("Observação (opcional)")
        lancar_caixa = st.checkbox(
            "Lançar também em Entradas e Saídas (afeta saldo bancário e Dashboard)",
            value=True,
            help="Deixe marcado quando o dinheiro realmente saiu ou entrou na "
                 "conta corrente agora. Desmarque ao cadastrar um "
                 "investimento antigo que já estava aplicado — assim o "
                 "Dashboard não conta o aporte duas vezes.",
        )

        if st.form_submit_button("Registrar movimentação"):
            aplicado = saldo.get(ativo, 0.0)
            if tipo == "Resgate" and valor > aplicado + 1e-9:
                st.error(
                    f"Resgate maior que o capital aplicado em '{ativo}' "
                    f"({brl(aplicado)}). Ajuste o valor."
                )
            else:
                repository.append_asset_move({
                    "Data": data_mov, "Investimento": ativo,
                    "Tipo": tipo, "Valor": valor, "Observação": obs.strip(),
                })
                if lancar_caixa:
                    repository.append_transaction(inv.ledger_row_for_move(
                        data=data_mov, valor=valor, tipo=tipo,
                        investimento=ativo,
                    ))
                destino = " e no fluxo de caixa" if lancar_caixa else ""
                st.success(
                    f"{tipo} de {brl(valor)} em '{ativo}' registrado{destino}."
                )
                st.rerun()


def _moves_history(df_moves: pd.DataFrame, names: list[str]) -> None:
    st.markdown("**Histórico de movimentações**")

    filtro = st.selectbox("Filtrar por ativo:", ["Todos"] + names)
    view = df_moves if filtro == "Todos" else \
        df_moves[df_moves["Investimento"] == filtro]
    if view.empty:
        st.info(f"Sem movimentações em '{filtro}'.")
        return

    dt = pd.to_datetime(view["Data"], errors="coerce")
    view = view.loc[dt.sort_values(ascending=False).index]

    with st.form("edit_asset_moves"):
        edited = st.data_editor(
            view, num_rows="dynamic", use_container_width=True,
            hide_index=True,
            column_config={
                "Investimento": st.column_config.SelectboxColumn(
                    "Investimento", options=names, required=True),
                "Tipo": st.column_config.SelectboxColumn(
                    "Tipo", options=["Aporte", "Resgate"], required=True),
                "Valor": st.column_config.NumberColumn(
                    "Valor (R$)", min_value=0.01, format="%.2f"),
            },
        )
        if st.form_submit_button("💾 Salvar movimentações"):
            if view.equals(edited):
                st.info("Nada a salvar — sem alterações.")
            else:
                untouched = df_moves.drop(view.index, errors="ignore")
                merged = pd.concat([untouched, edited], ignore_index=True)
                repository.save_asset_moves(merged)
                st.success("Movimentações salvas.")
                st.rerun()
    st.caption(
        "Apagar uma movimentação aqui **não** apaga o lançamento "
        "correspondente em Entradas e Saídas — ele volta a aparecer como "
        "pendente de atribuição."
    )

# ---------------------------------------------------------------------------
# Aba: Projeção e Resgate
# ---------------------------------------------------------------------------

def _projection_tab(*, positions: list[inv.Position],
                    rates: inv.MarketRates,
                    df_snapshots: pd.DataFrame) -> None:
    st.subheader("Projeção e melhor momento de resgate")
    st.caption(
        "Quanto cada ativo vale ao longo do tempo, bruto e já líquido de IOF "
        "e IR. Use para decidir se vale esperar o próximo degrau da tabela "
        "regressiva antes de resgatar."
    )

    if not positions:
        st.info(
            "Cadastre ativos e registre movimentações para ver as projeções."
        )
        return

    c1, c2 = st.columns([2, 1])
    escolha = c1.selectbox(
        "O que projetar:",
        ["Carteira inteira"] + [p.name for p in positions],
    )
    horizonte = c2.slider("Horizonte (meses):", min_value=6, max_value=120,
                          value=36, step=6)

    if escolha == "Carteira inteira":
        _portfolio_projection(positions, rates, horizonte)
    else:
        position = next(p for p in positions if p.name == escolha)
        _asset_projection(position, rates, horizonte, df_snapshots)


def _portfolio_projection(positions: list[inv.Position],
                          rates: inv.MarketRates, months: int) -> None:
    curve = inv.portfolio_curve(positions, rates, months=months)
    if curve.empty:
        st.info("Sem dados para projetar.")
        return

    final = curve.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capital aplicado", brl(final["Principal"]))
    c2.metric("Bruto projetado", brl(final["Bruto"]))
    c3.metric("Impostos estimados", brl(final["IOF"] + final["IR"]),
              delta="IOF + IR", delta_color="off")
    c4.metric("Líquido projetado 💎", brl(final["Líquido"]),
              delta=f"+{brl(final['Líquido'] - final['Principal'])}",
              delta_color="normal")

    _gross_net_chart(curve, title="Carteira: bruto × líquido")

    with st.expander("Ver projeção mês a mês"):
        detail = curve.copy()
        detail["Data"] = pd.to_datetime(detail["Data"]).dt.strftime("%m/%Y")
        for col in ("Principal", "Bruto", "IOF", "IR", "Líquido"):
            detail[col] = detail[col].apply(brl)
        st.dataframe(detail, hide_index=True, use_container_width=True)


def _asset_projection(position: inv.Position, rates: inv.MarketRates,
                      months: int,
                      df_snapshots: pd.DataFrame | None = None) -> None:
    _asset_summary(position)

    curve = inv.projection_curve(position, rates, months=months)
    if curve.empty:
        if position.maturity and position.maturity < date.today():
            st.warning(
                f"Este papel venceu em "
                f"**{position.maturity.strftime('%d/%m/%Y')}** — não há mais "
                "o que projetar. Registre o resgate na aba **Movimentações** "
                "para tirá-lo da carteira."
            )
        else:
            st.info("Sem dados para projetar este ativo.")
        return

    _gross_net_chart(curve, title=f"{position.name}: bruto × líquido")
    if df_snapshots is not None and not df_snapshots.empty:
        st.divider()
        _real_vs_projected_chart(position, df_snapshots, curve)
    st.divider()
    _redemption_scenarios(position, rates)
    st.divider()
    _tax_composition(position, rates, curve)


def _asset_summary(position: inv.Position) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aplicado", brl(position.principal))
    c2.metric("Bruto hoje", brl(position.gross_today))
    c3.metric("Líquido hoje", brl(position.net_today),
              delta=brl(position.yield_net_today),
              delta_color="normal" if position.yield_net_today >= 0 else "inverse")
    if position.maturity:
        dias = position.days_to_maturity or 0
        c4.metric("Vencimento", position.maturity.strftime("%d/%m/%Y"),
                  delta=f"faltam {dias} dias" if dias >= 0 else "vencido",
                  delta_color="off")
    else:
        c4.metric("Vencimento", "Liquidez diária",
                  delta="sem carência", delta_color="off")

    if position.isento:
        st.success(
            f"✅ **{position.produto}** é isento de Imposto de Renda — o "
            "rendimento líquido é igual ao bruto (após IOF, se houver)."
        )

    step = inv.next_ir_step(position)
    if step:
        step_date, current, nxt = step
        dias = (step_date - date.today()).days
        if dias > 0:
            st.info(
                f"📉 Sua alíquota de IR cai de **{current*100:.1f}%** para "
                f"**{nxt*100:.1f}%** em **{step_date.strftime('%d/%m/%Y')}** "
                f"(faltam {dias} dias). Esperar até lá aumenta o valor líquido."
            )


def _gross_net_chart(curve: pd.DataFrame, *, title: str) -> None:
    fig = go.Figure()
    x = pd.to_datetime(curve["Data"])

    fig.add_trace(go.Scatter(
        x=x, y=curve["Principal"], name="Capital aplicado",
        mode="lines", line=dict(color=Colors.NEUTRAL, width=2, dash="dot"),
        hovertemplate="Aplicado: R$ %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=curve["Bruto"], name="Valor bruto",
        mode="lines", line=dict(color=Colors.PRIMARY_SOFT, width=3),
        hovertemplate="Bruto: R$ %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=curve["Líquido"], name="Valor líquido (após IOF/IR)",
        mode="lines", line=dict(color=Colors.PRIMARY, width=3),
        fill="tonexty", fillcolor="rgba(239, 68, 68, 0.10)",
        hovertemplate="Líquido: R$ %{y:,.2f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=430, hovermode="x unified",
        yaxis_title="Valor (R$)", xaxis_title="",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        margin=dict(t=60, b=20, l=10, r=10),
    )
    fig.update_yaxes(tickprefix="R$ ")
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})
    st.caption(
        "A área avermelhada entre as linhas é o quanto os impostos consomem "
        "do rendimento em cada data."
    )


def _redemption_scenarios(position: inv.Position,
                          rates: inv.MarketRates) -> None:
    st.markdown("**Cenários de resgate**")
    today = date.today()
    scenarios: list[tuple[str, date]] = [
        ("Hoje", today),
        ("Em 3 meses", (pd.Timestamp(today) + pd.DateOffset(months=3)).date()),
        ("Em 6 meses", (pd.Timestamp(today) + pd.DateOffset(months=6)).date()),
        ("Em 1 ano", (pd.Timestamp(today) + pd.DateOffset(years=1)).date()),
        ("Em 2 anos", (pd.Timestamp(today) + pd.DateOffset(years=2)).date()),
    ]
    step = inv.next_ir_step(position)
    if step:
        scenarios.append(("Próximo degrau de IR", step[0]))
    if position.maturity:
        scenarios.append(("No vencimento", position.maturity))
        scenarios = [(l, d) for l, d in scenarios if d <= position.maturity]

    seen: set[date] = set()
    rows = []
    for label, target in scenarios:
        if target < today or target in seen:
            continue
        seen.add(target)
        bd = inv.taxes_at(
            position.lots, indexador=position.indexador, taxa=position.taxa,
            rates=rates, target=target, classe=position.classe,
            isento=position.isento, produto=position.produto,
        )
        rows.append({
            "Cenário": label,
            "Data": target.strftime("%d/%m/%Y"),
            "Bruto": bd.gross,
            "IOF": bd.iof,
            "IR": bd.ir,
            "Alíq. IR": f"{bd.ir_pct*100:.1f}%",
            "Líquido": bd.net,
            "Ganho líquido": bd.yield_net,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Sem cenários futuros para este ativo.")
        return

    best = df.loc[df["Líquido"].idxmax()]
    display = df.copy()
    for col in ("Bruto", "IOF", "IR", "Líquido", "Ganho líquido"):
        display[col] = display[col].apply(brl)
    st.dataframe(display, hide_index=True, use_container_width=True)
    st.caption(
        f"Maior valor líquido: **{best['Cenário']}** "
        f"({best['Data']}) — {brl(best['Líquido'])}. Projeção assume que a "
        "taxa contratada se mantém e que não há novos aportes."
    )


def _tax_composition(position: inv.Position, rates: inv.MarketRates,
                     curve: pd.DataFrame) -> None:
    st.markdown("**Para onde vai o rendimento no fim do período**")
    final = curve.iloc[-1]
    principal = float(final["Principal"])
    net = float(final["Líquido"])
    iof = float(final["IOF"])
    ir = float(final["IR"])
    ganho_liquido = max(net - principal, 0.0)

    parts = [
        ("Capital aplicado", principal, Colors.NEUTRAL),
        ("Ganho líquido", ganho_liquido, Colors.INCOME),
        ("IR", ir, Colors.EXPENSE),
        ("IOF", iof, Colors.WARNING),
    ]
    parts = [(n, v, c) for n, v, c in parts if v > 0.01]
    df = pd.DataFrame({
        "Componente": [n for n, _, _ in parts],
        "Valor": [v for _, v, _ in parts],
    })
    fig = px.pie(
        df, values="Valor", names="Componente", hole=0.55,
        color="Componente",
        color_discrete_map={n: c for n, _, c in parts},
    )
    fig.update_traces(textinfo="percent+label", textposition="inside")
    fig.update_layout(height=340, showlegend=False,
                      margin=dict(t=10, b=10, l=10, r=10))

    c1, c2 = st.columns([1, 1])
    with c1:
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
    with c2:
        data = pd.to_datetime(final["Data"]).strftime("%d/%m/%Y")
        st.write(f"Projeção para **{data}**:")
        st.write(f"- Capital aplicado: **{brl(principal)}**")
        st.write(f"- Valor bruto: **{brl(float(final['Bruto']))}**")
        st.write(f"- IOF: **{brl(iof)}**")
        st.write(f"- IR: **{brl(ir)}**")
        st.write(f"- **Líquido: {brl(net)}**")
        if principal > 0:
            rent = (net - principal) / principal * 100
            st.write(f"- Rentabilidade líquida: **{rent:.2f}%**")


def _manage_asset_section(df_assets: pd.DataFrame,
                          df_moves: pd.DataFrame) -> None:
    """Renomear (em cascata) ou excluir um ativo cadastrado.

    Renomear pelo editor de tabela quebraria o vínculo com as movimentações,
    que referenciam o ativo pelo nome — por isso a operação tem lugar próprio.
    """
    if df_assets.empty or "Nome" not in df_assets.columns:
        return
    names = sorted({
        n for n in df_assets["Nome"].dropna().astype(str).str.strip() if n
    })
    if not names:
        return

    with st.expander("🛠️ Renomear ou excluir um ativo"):
        alvo = st.selectbox("Ativo:", names, key="manage_asset_target")
        vinculadas = (
            df_moves[df_moves["Investimento"].astype(str).str.strip() == alvo]
            if not df_moves.empty and "Investimento" in df_moves.columns
            else pd.DataFrame()
        )
        st.caption(f"**{alvo}** tem {len(vinculadas)} movimentação(ões) vinculada(s).")

        st.markdown("**Renomear**")
        with st.form("rename_asset"):
            novo = st.text_input("Novo nome", value=alvo)
            st.caption(
                "As movimentações são atualizadas junto, então o histórico e "
                "a posição são preservados."
            )
            if st.form_submit_button("Renomear ativo"):
                novo_limpo = novo.strip()
                if not novo_limpo:
                    st.error("Informe um nome.")
                elif novo_limpo == alvo:
                    st.info("O nome é o mesmo — nada a fazer.")
                elif novo_limpo in names:
                    st.error(
                        f"Já existe um ativo chamado '{novo_limpo}'. "
                        "Escolha outro nome."
                    )
                else:
                    assets, moves = inv.rename_asset(
                        df_assets, df_moves, alvo, novo_limpo,
                    )
                    repository.save_assets(assets)
                    repository.save_asset_moves(moves)
                    st.success(
                        f"'{alvo}' renomeado para '{novo_limpo}' "
                        f"({len(vinculadas)} movimentação(ões) atualizada(s))."
                    )
                    st.rerun()

        st.divider()
        st.markdown("**Excluir**")
        manter = st.checkbox(
            "Manter as movimentações no histórico",
            value=False,
            help="Marcado: as movimentações continuam gravadas, mas ficam "
                 "órfãs até você cadastrar um ativo com o mesmo nome. "
                 "Desmarcado: são apagadas junto.",
            key="delete_keep_moves",
        )
        confirmar = st.text_input(
            f"Para confirmar, digite o nome do ativo ({alvo}):",
            key="delete_confirm_name",
        )
        if st.button("🗑️ Excluir ativo", key="delete_asset_btn"):
            if confirmar.strip() != alvo:
                st.error("O nome digitado não confere. Exclusão cancelada.")
            else:
                assets, moves = inv.delete_asset(
                    df_assets, df_moves, alvo, drop_moves=not manter,
                )
                repository.save_assets(assets)
                repository.save_asset_moves(moves)
                st.success(
                    f"'{alvo}' excluído"
                    + ("; movimentações mantidas no histórico."
                       if manter else
                       f" junto com {len(vinculadas)} movimentação(ões).")
                )
                st.rerun()
        st.caption(
            "Excluir um ativo **não** apaga os lançamentos de Entradas e "
            "Saídas — seu saldo bancário e o patrimônio do Dashboard "
            "permanecem intactos."
        )


def _position_tab(*, positions: list[inv.Position],
                  df_snapshots: pd.DataFrame) -> None:
    """Lançamento da posição real por ativo + desempenho individual e total."""
    st.subheader("Posição atual dos investimentos")
    st.caption(
        "Informe o valor bruto que a corretora mostra para cada ativo. Ele "
        "substitui a projeção — inclusive na base dos impostos — e a curva "
        "futura passa a crescer a partir dele."
    )

    if not positions:
        st.info(
            "Cadastre ativos na aba **Carteira** e registre as movimentações "
            "para poder lançar a posição atual."
        )
        return

    _total_performance(positions)
    st.divider()

    names = [p.name for p in positions]
    by_name = {p.name: p for p in positions}

    with st.form("new_asset_snapshot", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        ativo = c1.selectbox("Ativo", names, key="snap_asset")
        data_snap = c2.date_input("Data", value=date.today(),
                                  format="DD/MM/YYYY", key="snap_date")
        alvo = by_name[ativo]
        valor = c3.number_input(
            "Valor bruto (R$)", min_value=0.0, format="%.2f",
            value=float(round(alvo.projected_today, 2)),
            help="Pré-preenchido com o valor projetado — troque pelo que "
                 "aparece no seu extrato.",
            key="snap_value",
        )
        if st.form_submit_button("📌 Registrar posição"):
            repository.append_asset_snapshot({
                "Data": data_snap, "Investimento": ativo, "Valor": valor,
            })
            st.success(f"Posição de '{ativo}' atualizada para {brl(valor)}.")
            st.rerun()

    com_real = [p for p in positions if p.has_real]
    if com_real:
        st.markdown("**Real × projetado**")
        rows = []
        for p in com_real:
            desvio_pct = (
                (p.real_vs_projected / p.projected_today * 100)
                if p.projected_today else 0.0
            )
            rows.append({
                "Ativo": p.name,
                "Atualizado em": p.real_date.strftime("%d/%m/%Y"),
                "Projetado": brl(p.projected_today),
                "Real": brl(p.real_value or 0),
                "Diferença": brl(p.real_vs_projected),
                "Desvio": f"{desvio_pct:+.2f}%",
                "Rendimento real (líq.)": brl(p.yield_net_today),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)
        st.caption(
            "Desvio positivo: o ativo rendeu **mais** que a taxa presumida. "
            "Negativo: rendeu menos — vale revisar a taxa cadastrada ou as "
            "premissas de mercado."
        )

    sem_real = [p.name for p in positions if not p.has_real]
    if sem_real:
        st.caption(
            "Ainda sem posição real (usando projeção): "
            + ", ".join(f"**{n}**" for n in sem_real)
        )

    if not df_snapshots.empty:
        with st.expander("🗂️ Histórico de posições informadas"):
            hist = df_snapshots.copy()
            dt = inv.parse_dates(hist["Data"]) if "Data" in hist.columns else None
            if dt is not None:
                hist = hist.loc[dt.sort_values(ascending=False).index]
            with st.form("edit_asset_snapshots"):
                edited = st.data_editor(
                    hist, num_rows="dynamic", use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Investimento": st.column_config.SelectboxColumn(
                            "Investimento", options=names, required=True),
                        "Valor": st.column_config.NumberColumn(
                            "Valor bruto (R$)", min_value=0.0, format="%.2f"),
                    },
                )
                if st.form_submit_button("💾 Salvar histórico de posições"):
                    if hist.equals(edited):
                        st.info("Nada a salvar — sem alterações.")
                    else:
                        repository.save_asset_snapshots(edited)
                        st.success("Histórico atualizado.")
                        st.rerun()


def _real_vs_projected_chart(position: inv.Position,
                             df_snapshots: pd.DataFrame,
                             curve: pd.DataFrame) -> None:
    """Sobrepõe as posições reais já informadas à curva projetada."""
    hist = inv.snapshot_history(df_snapshots, position.name)
    if hist.empty:
        return

    st.markdown("**Posições reais já registradas**")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(curve["Data"]), y=curve["Bruto"],
        name="Projetado", mode="lines",
        line=dict(color=Colors.PRIMARY_SOFT, width=3),
        hovertemplate="Projetado: R$ %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=hist["Data"], y=hist["Valor"],
        name="Real informado", mode="lines+markers",
        line=dict(color=Colors.INVESTMENT, width=3),
        marker=dict(size=9, symbol="diamond"),
        hovertemplate="Real: R$ %{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        height=360, hovermode="x unified",
        yaxis_title="Valor bruto (R$)", xaxis_title="",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        margin=dict(t=40, b=20, l=10, r=10),
    )
    fig.update_yaxes(tickprefix="R$ ")
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    if len(hist) >= 2:
        primeiro, ultimo = hist.iloc[0], hist.iloc[-1]
        dias = (ultimo["Data"] - primeiro["Data"]).days
        var = ultimo["Valor"] - primeiro["Valor"]
        if primeiro["Valor"] > 0 and dias > 0:
            pct = var / primeiro["Valor"] * 100
            ao_ano = ((1 + pct / 100) ** (365 / dias) - 1) * 100
            st.caption(
                f"Entre {primeiro['Data']:%d/%m/%Y} e {ultimo['Data']:%d/%m/%Y} "
                f"({dias} dias) a posição variou {brl(var)} ({pct:+.2f}%), "
                f"o equivalente a **{ao_ano:+.2f}% ao ano** — compare com a "
                f"taxa contratada ({_rate_label(position)})."
            )


def _total_performance(positions: list[inv.Position]) -> None:
    """Desempenho consolidado da carteira e ranking por ativo."""
    principal = sum(p.principal for p in positions)
    bruto = sum(p.gross_today for p in positions)
    liquido = sum(p.net_today for p in positions)
    impostos = sum(p.iof_today + p.ir_today for p in positions)
    rend_bruto = bruto - principal
    rend_liquido = liquido - principal
    pct_bruto = (rend_bruto / principal * 100) if principal else 0.0
    pct_liquido = (rend_liquido / principal * 100) if principal else 0.0

    st.markdown("**Desempenho total da carteira**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capital aplicado", brl(principal))
    c2.metric("Valor bruto", brl(bruto),
              delta=f"{pct_bruto:+.2f}%",
              delta_color="normal" if rend_bruto >= 0 else "inverse")
    c3.metric("Impostos", brl(impostos), delta="IOF + IR", delta_color="off")
    c4.metric("Valor líquido 💎", brl(liquido),
              delta=f"{brl(rend_liquido)} ({pct_liquido:+.2f}%)",
              delta_color="normal" if rend_liquido >= 0 else "inverse")

    com_real = [p for p in positions if p.has_real]
    if com_real:
        mais_antigo = min(p.real_date for p in com_real)
        st.caption(
            f"{len(com_real)} de {len(positions)} ativo(s) com posição real "
            f"informada (a mais antiga em {mais_antigo.strftime('%d/%m/%Y')}). "
            "Os demais aparecem pela projeção."
        )
    else:
        st.caption(
            "Nenhuma posição real informada ainda — todos os valores acima "
            "vêm da projeção pela taxa contratada."
        )

    st.markdown("**Desempenho por ativo**")
    rows = []
    for p in positions:
        rend = p.yield_net_today
        pct = (rend / p.principal * 100) if p.principal else 0.0
        rows.append({
            "Ativo": p.name,
            "Fonte": "📌 real" if p.has_real else "projeção",
            "Aplicado": p.principal,
            "Bruto": p.gross_today,
            "Líquido": p.net_today,
            "Rendimento líq.": rend,
            "%": pct,
        })
    df = pd.DataFrame(rows).sort_values("%", ascending=False)

    display = df.copy()
    for col in ("Aplicado", "Bruto", "Líquido", "Rendimento líq."):
        display[col] = display[col].apply(brl)
    display["%"] = df["%"].apply(lambda v: f"{v:+.2f}%")
    st.dataframe(display, hide_index=True, use_container_width=True)

    if len(df) >= 2:
        fig = px.bar(
            df.sort_values("%"), x="%", y="Ativo", orientation="h",
            text=[f"{v:+.2f}%" for v in df.sort_values("%")["%"]],
            color=["ganho" if v >= 0 else "perda"
                   for v in df.sort_values("%")["%"]],
            color_discrete_map={"ganho": Colors.INCOME, "perda": Colors.EXPENSE},
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(
            height=max(240, 46 * len(df)), showlegend=False,
            xaxis_title="Rentabilidade líquida sobre o aplicado",
            yaxis_title="", margin=dict(t=10, b=10, l=10, r=60),
        )
        fig.update_xaxes(ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
