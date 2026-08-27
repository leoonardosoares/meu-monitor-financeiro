"""Página: Investimentos — carteira por ativo, tributação, projeção e metas."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import components, investments as inv, repository
from src.config import Colors, ConfigKeys
from src.finance import (
    compute_wealth, cumulative_invested_at, monthly_investment_contributions,
)
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
        "🔮 Projeção e Resgate",
        "💎 Posição Real",
        "🎯 Metas e Aportes",
        "🧮 Simulador",
    ])

    wealth = compute_wealth(df_transactions, df_transactions)
    invested = wealth.invested

    rates = _market_rates()
    df_assets = repository.load_assets()
    df_moves = repository.load_asset_moves()
    positions = inv.build_positions(df_assets, df_moves, rates)

    with tabs[0]:
        _wallet_tab(df_assets=df_assets, positions=positions, rates=rates)
    with tabs[1]:
        _moves_tab(df_assets=df_assets, df_moves=df_moves, positions=positions)
    with tabs[2]:
        _projection_tab(positions=positions, rates=rates)
    with tabs[3]:
        _position_tab(invested=invested, df_transactions=df_transactions)
    with tabs[4]:
        _goals_tab(df_transactions=df_transactions, invested=invested)
    with tabs[5]:
        _simulator_tab(invested=invested)


def _goals_tab(*, df_transactions: pd.DataFrame, invested: float) -> None:
    st.subheader("Reserva de Emergência")
    current_goal = repository.load_config(ConfigKeys.META_RESERVA, 10000.0)
    new_goal = st.number_input(
        "Meta da reserva (R$):", min_value=100.0, value=current_goal, step=500.0,
    )
    if new_goal != current_goal:
        repository.save_config(ConfigKeys.META_RESERVA, new_goal)

    reserve = min(invested, new_goal)
    extra = max(invested - new_goal, 0.0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total investido", brl(invested))
    c2.metric("Fundo de emergência", brl(reserve))
    c3.metric("Outros investimentos", brl(extra))

    progress = min(reserve / new_goal, 1.0) if new_goal > 0 else 0.0
    st.write(f"**Progresso da reserva ({progress * 100:.1f}%)**")
    st.progress(progress)
    if progress >= 1.0:
        st.success("Reserva completa. Novos aportes vão para 'Outros investimentos'.")

    st.divider()
    st.subheader("💸 Movimentar")

    col_in, col_out = st.columns(2)
    with col_in:
        with st.form("invest_deposit", clear_on_submit=True):
            st.markdown("**🟢 Novo aporte**")
            d = st.date_input("Data", format="DD/MM/YYYY", key="dep_date")
            v = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", key="dep_v")
            if st.form_submit_button("Investir"):
                repository.append_transaction({
                    "Data": d, "Descrição": "Aporte de Investimento",
                    "Categoria": "Investimento", "Valor": v, "Tipo": "Saída",
                })
                st.success("Aporte registrado!")
                st.rerun()

    with col_out:
        with st.form("invest_withdraw", clear_on_submit=True):
            st.markdown("**🏧 Resgate / saque**")
            d = st.date_input("Data", format="DD/MM/YYYY", key="wd_date")
            v = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", key="wd_v")
            if st.form_submit_button("Sacar"):
                if v > invested:
                    st.error("Saldo insuficiente nos investimentos.")
                else:
                    repository.append_transaction({
                        "Data": d, "Descrição": "Resgate de Investimento",
                        "Categoria": "Investimento", "Valor": v, "Tipo": "Entrada",
                    })
                    st.success("Saque realizado.")
                    st.rerun()

    st.divider()
    st.subheader("📅 Aportes mensais (últimos 12 meses)")
    st.caption(
        "Visualize quanto você depositou na sua carteira de investimento mês "
        "a mês. Saques aparecem como barra vermelha apenas se existirem."
    )
    df_contrib = monthly_investment_contributions(df_transactions, months=12)
    components.monthly_contributions_bars(df_contrib)

    st.divider()
    _investment_history_section(df_transactions)


def _investment_history_section(df_transactions: pd.DataFrame) -> None:
    """Histórico editável de aportes e saques.

    É uma visão filtrada da planilha `financeiro` (Categoria=Investimento).
    Edições, exclusões e novas linhas são mescladas de volta ao histórico
    completo sem tocar nas demais transações.
    """
    st.subheader("🗂️ Histórico de aportes e saques")
    st.caption(
        "Edite datas e valores, apague registros errados ou adicione "
        "lançamentos antigos. **Tipo**: `Saída` = aporte (dinheiro foi para o "
        "investimento) · `Entrada` = saque/resgate."
    )

    full = df_transactions.drop(columns=["Data_DT", "Mes_Ano"], errors="ignore")
    inv_mask = full["Categoria"] == "Investimento"
    display_cols = ["Data", "Descrição", "Valor", "Tipo"]
    df_inv = full.loc[inv_mask, display_cols]

    if df_inv.empty:
        st.info("Nenhum aporte registrado ainda. Use o formulário acima.")
        return

    # Mais recentes primeiro (índice original preservado pro merge).
    dt = pd.to_datetime(df_inv["Data"], errors="coerce")
    df_inv = df_inv.loc[dt.sort_values(ascending=False).index]

    with st.form("edit_investment_history"):
        edited = st.data_editor(
            df_inv, num_rows="dynamic", use_container_width=True,
            hide_index=True,
            column_config={
                "Valor": st.column_config.NumberColumn(
                    "Valor (R$)", min_value=0.01, format="%.2f",
                ),
                "Tipo": st.column_config.SelectboxColumn(
                    "Tipo", options=["Saída", "Entrada"], required=True,
                    help="Saída = aporte · Entrada = saque",
                ),
            },
        )
        if st.form_submit_button("💾 Salvar histórico"):
            if df_inv.equals(edited):
                st.info("Nada a salvar — sem alterações.")
                return
            edited = edited.dropna(subset=["Valor"])
            edited["Categoria"] = "Investimento"
            edited = edited[["Data", "Descrição", "Categoria", "Valor", "Tipo"]]
            untouched = full.drop(df_inv.index, errors="ignore")
            merged = pd.concat([untouched, edited], ignore_index=True)
            repository.save_transactions(merged)
            st.success("Histórico de investimentos salvo.")
            st.rerun()


def _simulator_tab(*, invested: float) -> None:
    st.subheader("Mágica dos juros compostos")

    c1, c2 = st.columns(2)
    years = c1.slider("Tempo (anos):", min_value=1, max_value=30, value=5)
    monthly_contribution = c2.number_input(
        "Aporte mensal (R$):", min_value=0.0, value=0.0, step=50.0,
        help="Quanto você pretende investir todo mês durante o período.",
    )

    c3, c4 = st.columns(2)
    annual_rate = c3.number_input(
        "Taxa anual bruta estimada (%):",
        min_value=0.0, value=10.0, step=0.5,
        help="Rendimento anual antes de descontar imposto.",
    )
    apply_ir = c4.checkbox(
        "Descontar IR de 15% (renda fixa, +720 dias)",
        value=True,
        help="IR regressivo da Renda Fixa: 15% sobre o ganho para resgates "
             "após 720 dias. Para LCI/LCA isentas, desmarque.",
    )

    if invested <= 0 and monthly_contribution <= 0:
        st.warning(
            "Faça seu primeiro aporte ou defina um aporte mensal para simular."
        )
        return

    # Converte taxa anual em mensal equivalente (juros compostos).
    monthly_rate = (1 + annual_rate / 100) ** (1 / 12) - 1

    rows = []
    balance = invested
    invested_total = invested
    for year in range(1, years + 1):
        for _ in range(12):
            # Rendimento aplicado primeiro, aporte ao fim do mês.
            balance = balance * (1 + monthly_rate) + monthly_contribution
            invested_total += monthly_contribution

        gross_gain = max(balance - invested_total, 0.0)
        ir = gross_gain * 0.15 if apply_ir else 0.0
        net_balance = balance - ir

        rows.append({
            "Ano": str(year),
            "Total Investido (R$)": invested_total,
            "Patrimônio Bruto (R$)": balance,
            "IR (R$)": ir,
            "Patrimônio Líquido (R$)": net_balance,
        })

    df_proj = pd.DataFrame(rows)
    final = df_proj.iloc[-1]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total investido", brl(final["Total Investido (R$)"]))
    m2.metric("Patrimônio bruto", brl(final["Patrimônio Bruto (R$)"]))
    m3.metric("IR estimado", brl(final["IR (R$)"]))
    m4.metric("Patrimônio líquido 💎", brl(final["Patrimônio Líquido (R$)"]))

    components.vertical_bar(
        df_proj, x="Ano", y="Patrimônio Líquido (R$)", color=Colors.PRIMARY,
    )


def _position_tab(*, invested: float, df_transactions: pd.DataFrame) -> None:
    st.subheader("Rendimento real dos investimentos")
    st.caption(
        "Atualize aqui o saldo bruto que está hoje na sua corretora ou banco. "
        "O app compara com o total que você aportou e mostra quanto rendeu."
    )

    with st.form("new_position", clear_on_submit=True):
        c1, c2 = st.columns(2)
        position_date = c1.date_input(
            "Data da posição", value=date.today(), format="DD/MM/YYYY",
        )
        position_value = c2.number_input(
            "Valor atual (R$)", min_value=0.0, format="%.2f",
            help="Soma de todos os seus investimentos hoje, do jeito que "
                 "aparece no extrato da corretora/banco.",
        )
        if st.form_submit_button("💾 Registrar posição"):
            repository.append_investment_position({
                "Data": position_date,
                "Valor": position_value,
            })
            st.success("Posição registrada!")
            st.rerun()

    df_positions = repository.load_investment_positions()
    if df_positions.empty:
        st.info(
            "Registre sua primeira posição para começar a acompanhar o rendimento."
        )
        return

    df_sorted = df_positions.dropna(subset=["Data_DT"]).sort_values("Data_DT")
    if df_sorted.empty:
        st.warning("Datas inválidas no histórico — verifique a tabela abaixo.")
    else:
        latest = df_sorted.iloc[-1]
        current_value = float(latest["Valor"])
        latest_date = latest["Data_DT"].strftime("%d/%m/%Y")
        returns = current_value - invested
        returns_pct = (returns / invested * 100) if invested > 0 else 0.0
        delta_color = "normal" if returns >= 0 else "inverse"

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total aportado", brl(invested))
        c2.metric(f"Valor atual ({latest_date})", brl(current_value))
        c3.metric(
            "Rendimento (R$)", brl(returns),
            delta=brl(returns), delta_color=delta_color,
        )
        if invested > 0:
            c4.metric(
                "Rendimento (%)", f"{returns_pct:.2f}%",
                delta=f"{returns_pct:.2f}%", delta_color=delta_color,
            )
        else:
            c4.metric("Rendimento (%)", "—",
                      help="Necessário ter aportes registrados.")

        if len(df_sorted) >= 2:
            st.divider()
            st.markdown("**📈 Evolução**")

            chart_mode = st.radio(
                "Visualizar:",
                ["Posição total", "Rendimento acumulado", "Comparar (posição × aportes)"],
                horizontal=True,
                key="position_chart_mode",
            )

            df_chart = df_sorted.copy()
            df_chart["Aportado"] = df_chart["Data_DT"].apply(
                lambda d: cumulative_invested_at(df_transactions, d)
            )
            df_chart["Rendimento"] = df_chart["Valor"] - df_chart["Aportado"]
            df_chart["Data_Formatada"] = df_chart["Data_DT"].dt.strftime("%d/%m/%y")

            if chart_mode == "Posição total":
                components.area_balance(
                    df_chart, x="Data_Formatada", y="Valor",
                    color=Colors.PRIMARY, y_title="Valor atual (R$)",
                )
            elif chart_mode == "Rendimento acumulado":
                latest_return = float(df_chart["Rendimento"].iloc[-1])
                color = Colors.INCOME if latest_return >= 0 else Colors.EXPENSE
                components.area_balance(
                    df_chart, x="Data_Formatada", y="Rendimento",
                    color=color, y_title="Rendimento (R$)",
                )
                st.caption(
                    "Rendimento = valor atual no dia − total aportado até o dia. "
                    "Pode ser negativo se a posição estiver abaixo do que foi aportado."
                )
            else:  # Comparar
                df_long = df_chart.melt(
                    id_vars=["Data_Formatada"],
                    value_vars=["Valor", "Aportado"],
                    var_name="Série", value_name="R$",
                )
                df_long["Série"] = df_long["Série"].map({
                    "Valor": "Posição (real)",
                    "Aportado": "Total aportado",
                })
                fig = px.line(
                    df_long, x="Data_Formatada", y="R$", color="Série",
                    markers=True, line_shape="spline",
                    color_discrete_map={
                        "Posição (real)": Colors.PRIMARY,
                        "Total aportado": Colors.NEUTRAL,
                    },
                )
                fig.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10),
                    xaxis_title="Dia", yaxis_title="R$",
                    legend_title_text="", hovermode="x unified",
                )
                fig.update_yaxes(tickprefix="R$ ")
                st.plotly_chart(
                    fig, use_container_width=True,
                    config={"displayModeBar": False},
                )
                st.caption(
                    "O espaço entre as duas linhas é o **rendimento** "
                    "acumulado em cada data."
                )

    st.divider()
    st.markdown("**🗂️ Histórico de posições**")
    st.caption("Edite, corrija ou apague registros antigos.")
    editable = df_positions.drop(
        columns=[c for c in ("Data_DT",) if c in df_positions.columns]
    )
    with st.form("edit_positions"):
        edited = st.data_editor(
            editable, num_rows="dynamic", use_container_width=True,
        )
        if st.form_submit_button("💾 Salvar alterações"):
            if not editable.equals(edited):
                repository.save_investment_positions(edited)
                st.success("Histórico salvo.")
                st.rerun()
            else:
                st.info("Nada a salvar — sem alterações.")


# ---------------------------------------------------------------------------
# Aba: Carteira — cadastro dos ativos e posição consolidada
# ---------------------------------------------------------------------------

def _wallet_tab(*, df_assets: pd.DataFrame, positions: list[inv.Position],
                rates: inv.MarketRates) -> None:
    st.subheader("Minha carteira")
    st.caption(
        "Cadastre cada investimento que você tem. A posição é calculada a "
        "partir das movimentações, projetada pela taxa do papel e já "
        "descontada de IOF e IR se você resgatasse hoje."
    )

    dups = inv.duplicate_asset_names(df_assets)
    if dups:
        st.warning(
            "⚠️ Nome repetido no cadastro: **" + "**, **".join(dups) + "**. "
            "As movimentações apontam para o ativo pelo nome, então apenas o "
            "primeiro cadastro de cada nome é usado — renomeie os demais para "
            "que a carteira fique correta."
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
    c4.metric("Valor líquido hoje 💎", brl(net),
              delta=f"{brl(net - principal)} no bolso",
              delta_color="normal" if net >= principal else "inverse")


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
# ---------------------------------------------------------------------------

def _moves_tab(*, df_assets: pd.DataFrame, df_moves: pd.DataFrame,
               positions: list[inv.Position]) -> None:
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
    if not names:
        st.info("Cadastre um ativo na aba **Carteira** antes de movimentar.")
        return

    saldo = {p.name: p.principal for p in positions}

    with st.form("new_asset_move", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        ativo = c1.selectbox("Investimento", names)
        tipo = c2.selectbox("Tipo", ["Aporte", "Resgate"])
        c3, c4 = st.columns(2)
        data_mov = c3.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        valor = c4.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        obs = st.text_input("Observação (opcional)")

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
                st.success(f"{tipo} de {brl(valor)} em '{ativo}' registrado.")
                st.rerun()

    if df_moves.empty:
        st.info("Nenhuma movimentação registrada ainda.")
        return

    st.divider()
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


# ---------------------------------------------------------------------------
# Aba: Projeção e Resgate
# ---------------------------------------------------------------------------

def _projection_tab(*, positions: list[inv.Position],
                    rates: inv.MarketRates) -> None:
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
        _asset_projection(position, rates, horizonte)


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
                      months: int) -> None:
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
            isento=position.isento,
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
