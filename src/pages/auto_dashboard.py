"""Página: Dashboard Automático (sincronização via Pluggy)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as st_components

from src import components, pluggy, repository
from src.config import Colors, ConfigKeys
from src.format import brl


# ---------------------------------------------------------------------------
# Sample data (demo) — exibido enquanto não há sincronização real.
# ---------------------------------------------------------------------------

def _sample_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    today = date.today()
    days_full = [(today - timedelta(days=i)).strftime("%d/%m/%Y") for i in range(10)]
    days_short = [(today - timedelta(days=i)).strftime("%d/%m") for i in range(9, -1, -1)]

    df_bank = pd.DataFrame({
        "Data": days_full,
        "Descrição": ["Salário", "Pix Mercado", "Uber", "Ifood", "Pix João",
                      "Conta de Luz", "Netflix", "Gasolina",
                      "Rendimento CDI", "Restaurante"],
        "Categoria": ["Receita", "Supermercado", "Transporte", "Lazer", "Outros",
                      "Moradia", "Lazer", "Transporte", "Investimento", "Lazer"],
        "Valor": [5000.0, -350.0, -45.0, -80.0, -150.0, -200.0, -50.0,
                  -250.0, 45.0, -120.0],
        "Tipo": ["Entrada", "Saída", "Saída", "Saída", "Saída", "Saída",
                 "Saída", "Saída", "Entrada", "Saída"],
        "Conta": ["Itaú"] * 10,
    })
    df_card = pd.DataFrame({
        "Data": days_full[:5],
        "Descrição": ["Amazon", "Mercado Livre", "Farmácia",
                      "Assinatura Software", "Passagem Aérea"],
        "Categoria": ["Compras", "Compras", "Saúde", "Outros", "Viagem"],
        "Valor": [150.0, 89.9, 45.0, 25.0, 450.0],
        "Cartão": ["Nubank Final 1234"] * 5,
    })
    df_balance = pd.DataFrame({
        "Data_Curta": days_short,
        "Saldo_R$": [1000, 6000, 5650, 5605, 5525, 5375, 5175, 5125, 4875, 4800],
    })
    df_pie = pd.DataFrame({
        "Categoria": ["Supermercado", "Lazer", "Transporte",
                      "Moradia", "Compras", "Viagem"],
        "Valor": [350.0, 250.0, 295.0, 200.0, 239.9, 450.0],
    })
    return df_bank, df_card, df_balance, df_pie


# ---------------------------------------------------------------------------

def render(*, df_credit_card: pd.DataFrame) -> None:
    title_col, action_col = st.columns([2, 1])
    with title_col:
        components.page_header(
            "🤖 Inteligência Financeira",
            "Visão unificada de contas e cartões via Open Finance.",
        )
    with action_col:
        st.write("")
        if st.button("🔄 Puxar extrato agora",
                     type="primary", use_container_width=True):
            _sync_with_pluggy()

    is_real, df_bank, df_card, df_balance, df_pie = _resolve_data()

    _kpis_section(df_credit_card=df_credit_card, df_bank=df_bank, is_real=is_real)
    st.divider()

    chart_left, chart_right = st.columns([1.2, 1])
    with chart_left:
        st.subheader("📈 Fluxo de caixa diário (últimos 10 dias)")
        components.area_balance(df_balance, x="Data_Curta", y="Saldo_R$")
    with chart_right:
        st.subheader("🍩 Concentração de gastos")
        components.horizontal_bar_expenses(df_pie)

    st.divider()
    _connect_section()
    st.divider()

    st.subheader("📋 Últimas transações sincronizadas")
    bank_tab, card_tab = st.tabs(
        ["🏦 Conta corrente", "💳 Cartão de crédito"],
    )
    with bank_tab:
        st.dataframe(
            df_bank.style.map(_value_style, subset=["Valor"]),
            use_container_width=True, hide_index=True,
        )
    with card_tab:
        st.dataframe(df_card, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------

def _resolve_data() -> tuple[bool, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Devolve (is_real, df_bank, df_card, df_balance, df_pie).

    Se já temos dados reais sincronizados em st.session_state, usamos eles.
    Caso contrário, devolvemos dados de exemplo.
    """
    accounts = st.session_state.get("pluggy_accounts")
    transactions = st.session_state.get("pluggy_transactions")

    if not accounts or not transactions:
        df_bank_s, df_card_s, df_balance_s, df_pie_s = _sample_data()
        return False, df_bank_s, df_card_s, df_balance_s, df_pie_s

    df_accounts = pd.DataFrame(accounts)
    df_tx = pd.DataFrame(transactions).sort_values("Data_DT", ascending=False)
    total_balance = float(df_accounts["Saldo"].sum())

    df_balance = (
        df_tx.assign(Data_Curta=lambda d: d["Data_DT"].dt.strftime("%d/%m"))
        .groupby("Data_Curta")["Valor"].sum().cumsum().reset_index()
        .rename(columns={"Valor": "Saldo_R$"})
    )
    df_balance["Saldo_R$"] = df_balance["Saldo_R$"] + total_balance

    expenses = df_tx[df_tx["Tipo"] == "Saída"].copy()
    expenses["Valor"] = expenses["Valor"].abs()
    df_pie = expenses.groupby("Categoria")["Valor"].sum().reset_index()

    df_bank = df_tx.drop(columns=["Data_DT"])
    return True, df_bank, pd.DataFrame(), df_balance, df_pie


def _sync_with_pluggy() -> None:
    if not pluggy.is_configured():
        st.error("Credenciais Pluggy não configuradas em `secrets.toml`.")
        return
    with st.spinner("Extraindo dados da Pluggy... (pode levar alguns segundos)"):
        api_key = pluggy.get_api_key()
        if not api_key:
            st.error("Erro ao autenticar na API da Pluggy.")
            return
        accounts, transactions = pluggy.fetch_bank_data(api_key)
        if not accounts or not transactions:
            st.warning(
                "⚠️ Conta conectada, mas ainda sem transações. "
                "Aguarde 30s e tente novamente."
            )
            return
        st.session_state["pluggy_accounts"] = accounts
        st.session_state["pluggy_transactions"] = transactions
        backup = pd.DataFrame(transactions).drop(columns=["Data_DT"])
        repository.save_bank_extract(backup)
        st.success("✅ Extrato sincronizado e salvo na nuvem.")


def _kpis_section(*, df_credit_card: pd.DataFrame,
                   df_bank: pd.DataFrame, is_real: bool) -> None:
    st.subheader("💡 Indicadores chave")
    k1, k2, k3, k4 = st.columns(4)

    if is_real:
        income = float(df_bank.loc[df_bank["Tipo"] == "Entrada", "Valor"].sum())
        outflow = float(df_bank.loc[df_bank["Tipo"] == "Saída", "Valor"].abs().sum())
        balance = income - outflow

        if df_credit_card.empty:
            invoice = 0.0
        else:
            invoice = float(df_credit_card.loc[
                df_credit_card["Status"] == "Pendente", "Valor"
            ].sum())

        income_base = repository.load_config(ConfigKeys.RECEITA_PREVISTA, 5000.0)
        commitment = (outflow / income_base * 100) if income_base > 0 else 0
        commitment_label = ("Renda Segura (< 50%)" if commitment < 50
                            else "Atenção (acima de 50%)")

        k1.metric("Saldo no período", brl(balance), f"+ {brl(income)} (entradas)")
        k2.metric("Saídas (banco)", brl(outflow), delta_color="inverse")
        k3.metric(
            "Fatura em aberto",
            brl(invoice) if invoice > 0 else "R$ 0,00",
            "Pagar até o vencimento" if invoice > 0 else "Sem pendências",
            delta_color="off",
        )
        k4.metric(
            "Comprometimento da renda",
            f"{commitment:.0f}%",
            commitment_label,
            delta_color="inverse" if commitment >= 50 else "normal",
        )
    else:
        k1.metric("Saldo no período", "R$ 3.800,00", "+ R$ 5.045,00")
        k2.metric("Saídas (banco)", "R$ 1.245,00",
                  "- 15% vs mês passado", delta_color="inverse")
        k3.metric("Fatura em aberto", "R$ 759,90",
                  "⚠️ Fecha em 3 dias", delta_color="off")
        k4.metric("Comprometimento da renda", "40%",
                  "Renda Segura (< 50%)", delta_color="normal")


def _connect_section() -> None:
    st.subheader("🔗 Gerenciar conexões bancárias")
    sandbox = st.checkbox(
        "⚙️ Modo de teste (Sandbox ativado)", value=True,
        help="Desmarque apenas quando a Pluggy aprovar acesso a dados reais.",
    )
    st.session_state.setdefault("show_pluggy_widget", False)
    if st.button("🏦 Conectar nova conta bancária"):
        st.session_state["show_pluggy_widget"] = True

    if not st.session_state["show_pluggy_widget"]:
        return

    with st.spinner("Gerando ambiente seguro..."):
        api_key = pluggy.get_api_key()
        if not api_key:
            st.error("Falha ao obter API Key — verifique os secrets.")
            return
        connect_token = pluggy.get_connect_token(api_key)
        if not connect_token:
            st.error("Falha ao gerar Connect Token.")
            return

    if sandbox:
        st.info("🔐 Ambiente de testes — procure por 'Pluggy Sandbox'.")
    else:
        st.warning(
            "⚠️ Ambiente real — só verá bancos reais com Acesso de Produção liberado."
        )
    st_components.html(
        _pluggy_widget_html(connect_token, sandbox),
        height=750, scrolling=True,
    )


def _pluggy_widget_html(connect_token: str, sandbox: bool) -> str:
    sandbox_str = "true" if sandbox else "false"
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f8fafc;">
<div id="pluggy-connect-container"
     style="height:700px;width:100%;border-radius:12px;overflow:hidden;
            box-shadow:0 4px 12px rgba(15,23,42,0.08);"></div>
<script>
function initPluggy() {{
  try {{
    const widget = new window.PluggyConnect({{
      connectToken: '{connect_token}',
      includeSandbox: {sandbox_str},
      container: 'pluggy-connect-container',
      onSuccess: (itemData) => {{
        document.getElementById('pluggy-connect-container').innerHTML =
          "<div style='padding:40px;color:#10B981;font-family:sans-serif;text-align:center;'>" +
          "<h2>🎉 Banco conectado!</h2><p>Você já pode fechar esta tela.</p></div>";
      }},
      onError: (error) => {{
        document.getElementById('pluggy-connect-container').innerHTML =
          "<div style='padding:20px;color:#EF4444;font-family:sans-serif;'>" +
          "<strong>Erro:</strong> " + error.message + "</div>";
      }}
    }});
    widget.init();
  }} catch (e) {{
    document.getElementById('pluggy-connect-container').innerHTML =
      "<div style='padding:20px;color:#EF4444;font-family:sans-serif;'>" +
      "<strong>Erro ao inicializar:</strong> " + e.message + "</div>";
  }}
}}
const s = document.createElement('script');
s.src = "https://cdn.pluggy.ai/pluggy-connect/v1.3.0/pluggy-connect.js";
s.onload = initPluggy;
document.head.appendChild(s);
</script>
</body>
</html>
"""


def _value_style(val) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    color = Colors.INCOME if v > 0 else Colors.EXPENSE
    return f"color: {color}; font-weight: 600"
