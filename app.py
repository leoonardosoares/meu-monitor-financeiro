"""Meu Monitor Financeiro — entry point.

Este arquivo intencionalmente contém apenas o mínimo:
    1. configuração da página + tema/CSS
    2. autenticação (login gate)
    3. carregamento dos DataFrames principais
    4. roteamento entre as páginas em `src/pages/`

Toda a lógica de negócio mora em `src/`.

Estratégia de carregamento: transações e cartão são sempre lidos (o
filtro de mês da sidebar precisa deles); o restante (categorias,
orçamentos, custos fixos) é lido sob demanda pela página ativa. Cada
leitura evitada é uma ida a menos à API do Google Sheets.
"""
from __future__ import annotations

import streamlit as st

from src import auth, components, pluggy, repository, sidebar, styles, sync
from src.config import (
    APP_ICON, APP_TITLE, ConfigKeys, SYSTEM_CATEGORIES, TEMA_PADRAO,
)
from src.finance import filter_by_month, list_months
from src.pages import (
    credit_card, dashboard, import_page, investments, settings,
    transactions,
)
from src.sidebar import PAGES


def _bootstrap_categories() -> list[str]:
    """Lista usada nos selects: categorias do usuário + as do sistema."""
    df_categories = repository.load_categories()
    user_categories = df_categories["Categoria"].dropna().unique().tolist()
    return user_categories + [
        c for c in SYSTEM_CATEGORIES if c not in user_categories
    ]


def _sincronizar_se_preciso() -> None:
    """Sincroniza quando a última passou de 6 horas.

    O Streamlit reexecuta o script a cada clique, então há uma trava por
    sessão: no máximo uma tentativa a cada 30 minutos. Sem ela, uma
    conexão fora do ar faria cada clique ir ao banco; com uma trava de
    "uma vez por sessão", uma aba aberta por dias nunca sincronizava.
    """
    import time
    if not pluggy.is_configured():
        return
    ultima = st.session_state.get("sync_tentado_em", 0)
    if st.session_state.get("sync_tentado") is False:
        ultima = 0                       # o "Recomeçar" pediu agora
    if time.time() - ultima < 30 * 60:
        return
    st.session_state["sync_tentado_em"] = time.time()
    st.session_state["sync_tentado"] = True
    ids = import_page.item_ids()
    carimbo = repository.load_config_text(ConfigKeys.PLUGGY_ULTIMA_SYNC)
    if not ids or not sync.stale(carimbo, hours=6):
        return
    import_page.executar(ids, repository.load_transactions())
    res = st.session_state.get("sync_resultado")
    texto = (f"⚠️ Não consegui sincronizar: {res}" if isinstance(res, str)
             else f"🔄 {res.resumo()}" if res is not None else "")
    if texto:
        # Há versões do Streamlit em que o toast estoura neste ponto da
        # página; o aviso não vale derrubar o app.
        try:
            st.toast(texto)
        except Exception:                                 # noqa: BLE001
            st.caption(texto)


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    # O tema é lido antes de tudo: o CSS precisa sair junto com a
    # primeira renderização, senão a tela pisca clara antes de escurecer.
    tema = st.session_state.get("tema") or repository.load_config_text(
        ConfigKeys.TEMA, TEMA_PADRAO)
    st.session_state["tema"] = tema
    styles.inject(tema)
    components.use_theme(tema)

    if not auth.is_logged_in():
        auth.render_login()
        return


    # Antes de qualquer tela ler a planilha: se a última sincronização
    # passou de 6 horas, ela roda agora. Depois disso, o que cada página
    # lê já é o que o banco diz — sem botão para lembrar de clicar.
    _sincronizar_se_preciso()

    # Sempre carregados: o filtro de mês da sidebar depende dos dois.
    df_transactions = repository.load_transactions()
    df_credit_card = repository.load_credit_card()

    months = list_months(df_transactions, df_credit_card)
    state = sidebar.render(months)

    df_transactions_period, df_credit_card_period = filter_by_month(
        df_transactions, df_credit_card, state.selected_month,
    )

    # Daqui pra baixo, cada página carrega apenas o que usa.
    page = state.selected_page
    if page == PAGES[0]:  # Dashboard
        dashboard.render(
            df_transactions=df_transactions,
            df_credit_card=df_credit_card,
            df_transactions_period=df_transactions_period,
            df_credit_card_period=df_credit_card_period,
            df_fixed_costs=repository.load_fixed_costs(),
            df_budgets=repository.load_budgets(),
            df_cards=repository.load_cards(),
            df_card_payments=repository.load_card_payments(),
            selected_month=state.selected_month,
        )
    elif page == PAGES[1]:  # Entradas e Saídas
        transactions.render(
            df_transactions=df_transactions,
            categories=_bootstrap_categories(),
        )
    elif page == PAGES[2]:  # Cartão de Crédito
        credit_card.render(
            df_credit_card=df_credit_card,
            df_credit_card_period=df_credit_card_period,
            categories=_bootstrap_categories(),
            selected_month=state.selected_month,
        )
    elif page == PAGES[3]:  # Investimentos
        investments.render(df_transactions=df_transactions)
    elif page == PAGES[4]:  # Sincronização
        import_page.render(
            df_transactions=df_transactions,
            df_credit_card=df_credit_card,
            df_cards=repository.load_cards(),
            categories=_bootstrap_categories(),
        )
    elif page == PAGES[5]:  # Configurações e Orçamento
        settings.render(
            df_categories=repository.load_categories(),
            df_budgets=repository.load_budgets(),
            df_fixed_costs=repository.load_fixed_costs(),
            df_transactions_period=df_transactions_period,
            df_credit_card_period=df_credit_card_period,
            categories=_bootstrap_categories(),
            selected_month=state.selected_month,
        )


if __name__ == "__main__":
    main()
