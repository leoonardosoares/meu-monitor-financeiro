"""
Monitor Financeiro — v2.0
Refatorado com boas práticas: segurança, performance, UX profissional.
"""

import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit.components.v1 as components

# ══════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURAÇÃO INICIAL
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Monitor Financeiro",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS Global ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Fonte e fundo geral */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }

    /* Esconde o menu hamburger padrão do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f2027, #203a43, #2c5364);
    }
    [data-testid="stSidebar"] * {
        color: #e0e0e0 !important;
    }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stRadio label {
        color: #a0b0c0 !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Botões — verde escuro profissional */
    div.stButton > button:first-child {
        background: linear-gradient(135deg, #1a7a4a, #21a663) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.2rem !important;
        transition: all 0.25s ease !important;
        letter-spacing: 0.02em;
    }
    div.stButton > button:first-child:hover {
        background: linear-gradient(135deg, #21a663, #27c97a) !important;
        box-shadow: 0 4px 14px rgba(33,166,99,0.35) !important;
        transform: translateY(-1px) !important;
    }

    /* Cards de métricas */
    [data-testid="metric-container"] {
        background: #1e2a38;
        border: 1px solid #2a3a4a;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    [data-testid="metric-container"] label {
        color: #7a9ab5 !important;
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #e8f4ff !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: #12202e;
        border-radius: 10px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px !important;
        color: #7a9ab5 !important;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: #21a663 !important;
        color: white !important;
    }

    /* Divisor */
    hr {
        border-color: #2a3a4a !important;
    }

    /* Títulos de seção */
    h1 { color: #e8f4ff !important; font-weight: 700; }
    h2 { color: #c8dff0 !important; font-weight: 600; }
    h3 { color: #a0c0d8 !important; font-weight: 600; }

    /* DataEditor / DataFrame */
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

    /* Forms */
    [data-testid="stForm"] {
        border: 1px solid #2a3a4a !important;
        border-radius: 12px !important;
        padding: 1.2rem !important;
        background: #182430 !important;
    }

    /* Inputs */
    .stTextInput input, .stNumberInput input, .stDateInput input {
        background: #1e2a38 !important;
        border: 1px solid #2a3a4a !important;
        color: #e0e8f0 !important;
        border-radius: 8px !important;
    }

    /* Alertas */
    .stAlert {
        border-radius: 10px !important;
    }

    /* Progress bar */
    .stProgress > div > div {
        background: linear-gradient(90deg, #1a7a4a, #21a663) !important;
        border-radius: 4px !important;
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# 2. AUTENTICAÇÃO  (senha no st.secrets — nunca no código!)
# ══════════════════════════════════════════════════════════════════════════════

def _check_login():
    """Exibe tela de login se o usuário não estiver autenticado."""
    if st.session_state.get("logado"):
        return True

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("## 🔒 Monitor Financeiro")
        st.markdown("Insira a senha para acessar.")
        senha = st.text_input("Senha de acesso:", type="password", key="senha_input")
        if st.button("Entrar", use_container_width=True):
            # ⚠️  Adicione  APP_PASSWORD = "sua_senha"  no arquivo secrets.toml
            senha_correta = st.secrets.get("APP_PASSWORD", "admin123")
            if senha == senha_correta:
                st.session_state["logado"] = True
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")
    return False


if not _check_login():
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# 3. CONEXÃO GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════════════════════

COLUNAS_ABAS = {
    "financeiro":      ["Data", "Descrição", "Categoria", "Valor", "Tipo"],
    "cartao":          ["Data Compra", "Mês da Fatura", "Descrição", "Categoria", "Parcela", "Valor", "Status"],
    "configuracoes":   ["chave", "valor"],
    "categorias":      ["Categoria"],
    "orcamentos":      ["Categoria", "Limite"],
    "custos_fixos":    ["Descrição", "Valor"],
    "extrato_bancario":["Data", "Descrição", "Categoria", "Valor", "Tipo", "Conta"],
}


@st.cache_resource
def _conectar_google():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(st.secrets["GOOGLE_JSON"]), scope
    )
    client = gspread.authorize(creds)
    return client.open("Banco_Monitor_Financeiro")


@st.cache_resource
def _carregar_abas():
    planilha = _conectar_google()
    existentes = {ws.title: ws for ws in planilha.worksheets()}
    abas = {}
    for nome, colunas in COLUNAS_ABAS.items():
        if nome in existentes:
            abas[nome] = existentes[nome]
        else:
            ws = planilha.add_worksheet(title=nome, rows="1000", cols="20")
            ws.append_row(colunas)
            abas[nome] = ws
    return abas


try:
    ABAS = _carregar_abas()
except Exception as e:
    st.error(f"❌ Falha ao conectar no Google Sheets: {e}")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# 4. FUNÇÕES GENÉRICAS DE LEITURA / ESCRITA
# ══════════════════════════════════════════════════════════════════════════════

def _aba(nome: str):
    return ABAS[nome]


def _salvar_aba(nome: str, df: pd.DataFrame):
    """
    Regrava a aba inteira com o DataFrame fornecido.
    Limpa o cache de leitura correspondente após salvar.
    """
    ws = _aba(nome)
    ws.clear()
    payload = json.loads(df.fillna("").astype(str).to_json(orient="values"))
    ws.update(values=[df.columns.tolist()] + payload)
    # Invalida o cache de leitura
    _ler_aba.clear()


@st.cache_data(ttl=60)
def _ler_aba(nome: str, colunas_numericas: tuple = ()) -> pd.DataFrame:
    """Lê uma aba e garante colunas numéricas corretamente tipadas."""
    dados = _aba(nome).get_all_records()
    if not dados:
        return pd.DataFrame(columns=COLUNAS_ABAS[nome])
    df = pd.DataFrame(dados)
    for col in colunas_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _append_aba(nome: str, linha: dict):
    """Adiciona uma única linha sem reescrever a planilha inteira (mais rápido)."""
    ws = _aba(nome)
    ws.append_row([str(linha.get(c, "")) for c in COLUNAS_ABAS[nome]])
    _ler_aba.clear()


# ── Helpers de configuração ────────────────────────────────────────────────────

def carregar_config(chave: str, padrao):
    df = _ler_aba("configuracoes")
    if not df.empty and chave in df["chave"].values:
        return float(df.loc[df["chave"] == chave, "valor"].iloc[0])
    return padrao


def salvar_config(chave: str, valor):
    df = _ler_aba("configuracoes")
    if not df.empty and chave in df["chave"].values:
        df.loc[df["chave"] == chave, "valor"] = valor
    else:
        df = pd.concat(
            [df, pd.DataFrame([{"chave": chave, "valor": valor}])],
            ignore_index=True,
        )
    _salvar_aba("configuracoes", df)


# ══════════════════════════════════════════════════════════════════════════════
# 5. UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════════════════

def fmt_br(valor: float) -> str:
    """Formata valor no padrão brasileiro: R$ 1.234,56"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#c8d8e8",
    margin=dict(t=20, b=20, l=10, r=10),
    legend_title_text="",
)

COR_ENTRADA = "#21a663"
COR_SAIDA   = "#e05252"
COR_AZUL    = "#3b9fe8"
COR_ROXO    = "#9b72e8"


# ══════════════════════════════════════════════════════════════════════════════
# 6. PLUGGY — OPEN FINANCE
# ══════════════════════════════════════════════════════════════════════════════

def _pluggy_api_key():
    cid = st.secrets.get("PLUGGY_CLIENT_ID")
    csec = st.secrets.get("PLUGGY_CLIENT_SECRET")
    if not (cid and csec):
        return None
    r = requests.post(
        "https://api.pluggy.ai/auth",
        json={"clientId": cid, "clientSecret": csec},
        headers={"accept": "application/json", "content-type": "application/json"},
        timeout=10,
    )
    return r.json().get("apiKey") if r.status_code == 200 else None


def _pluggy_connect_token(api_key: str):
    r = requests.post(
        "https://api.pluggy.ai/connect_token",
        json={},
        headers={"accept": "application/json", "content-type": "application/json", "X-API-KEY": api_key},
        timeout=10,
    )
    return r.json().get("accessToken") if r.status_code == 200 else None


def _pluggy_extrair(api_key: str):
    headers = {"accept": "application/json", "X-API-KEY": api_key}
    try:
        items = requests.get("https://api.pluggy.ai/items", headers=headers, timeout=10).json().get("results", [])
        if not items:
            return None, None

        contas, transacoes = [], []
        for item in items:
            accs = requests.get(
                f"https://api.pluggy.ai/accounts?itemId={item['id']}", headers=headers, timeout=10
            ).json().get("results", [])
            for acc in accs:
                contas.append({"Conta": acc["name"], "Tipo": acc["type"], "Saldo": float(acc["balance"])})
                txs = requests.get(
                    f"https://api.pluggy.ai/transactions?accountId={acc['id']}", headers=headers, timeout=10
                ).json().get("results", [])
                for tx in txs:
                    valor = float(tx["amount"])
                    transacoes.append({
                        "Data":      pd.to_datetime(tx["date"]).strftime("%d/%m/%Y"),
                        "Descrição": tx["description"],
                        "Categoria": tx.get("category", "Outros"),
                        "Valor":     valor,
                        "Tipo":      "Entrada" if valor > 0 else "Saída",
                        "Conta":     acc["name"],
                        "Data_DT":   pd.to_datetime(tx["date"]).tz_localize(None),
                    })
        return contas, transacoes
    except Exception as e:
        st.error(f"Erro no motor de extração Pluggy: {e}")
        return None, None


# ══════════════════════════════════════════════════════════════════════════════
# 7. SIDEBAR — NAVEGAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    # Logo / título
    st.markdown("""
    <div style="text-align:center; padding: 1rem 0 0.5rem;">
        <div style="font-size:2.2rem;">💸</div>
        <div style="font-weight:700; font-size:1.1rem; color:#e8f4ff; letter-spacing:0.04em;">
            Monitor Financeiro
        </div>
        <div style="font-size:0.72rem; color:#5a8a9f; margin-top:2px;">
            Sincronizado na Nuvem ☁️
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown('<p style="font-size:0.75rem;color:#5a8a9f;text-transform:uppercase;letter-spacing:0.07em;">Período</p>', unsafe_allow_html=True)

    # Carrega meses disponíveis
    df_dados_raw    = _ler_aba("financeiro", ("Valor",))
    df_cartao_raw   = _ler_aba("cartao", ("Valor",))
    df_categorias   = _ler_aba("categorias")
    df_orcamentos   = _ler_aba("orcamentos", ("Limite",))
    df_custos       = _ler_aba("custos_fixos", ("Valor",))

    # Prepara dados principais
    df_dados = df_dados_raw.copy()
    if not df_dados.empty:
        df_dados["Data_DT"]  = pd.to_datetime(df_dados["Data"], errors="coerce")
        df_dados["Mes_Ano"]  = df_dados["Data_DT"].dt.strftime("%m/%Y").fillna("Sem Data")
    else:
        df_dados["Data_DT"]  = pd.Series(dtype="datetime64[ns]")
        df_dados["Mes_Ano"]  = pd.Series(dtype=str)

    df_cartao = df_cartao_raw.copy()

    todos_meses = set()
    if "Mes_Ano" in df_dados.columns:
        todos_meses.update(df_dados["Mes_Ano"].unique().tolist())
    if not df_cartao.empty and "Mês da Fatura" in df_cartao.columns:
        todos_meses.update(df_cartao["Mês da Fatura"].unique().tolist())
    todos_meses.discard("Sem Data")
    lista_meses = sorted(todos_meses, reverse=True)

    mes_selecionado = st.selectbox("Período:", ["Todos os Meses"] + lista_meses)

    st.divider()

    PAGINAS = {
        "📊  Dashboard":           "Dashboard",
        "🤖  Inteligência Financeira": "Dashboard Automático",
        "💰  Entradas e Saídas":   "Entradas e Saídas",
        "💳  Cartão de Crédito":   "Cartão de Crédito",
        "📈  Investimentos":        "Investimentos",
        "⚙️  Configurações":        "Configurações",
    }
    pagina_label = st.radio("Navegação", list(PAGINAS.keys()), label_visibility="collapsed")
    menu = PAGINAS[pagina_label]

    st.divider()
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state["logado"] = False
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# 8. PREPARAÇÃO DOS DADOS FILTRADOS
# ══════════════════════════════════════════════════════════════════════════════

if mes_selecionado != "Todos os Meses":
    df_dados_filtro  = df_dados[df_dados["Mes_Ano"] == mes_selecionado]
    df_cartao_filtro = df_cartao[df_cartao["Mês da Fatura"] == mes_selecionado] if not df_cartao.empty else df_cartao
else:
    df_dados_filtro  = df_dados
    df_cartao_filtro = df_cartao

LISTA_CATEGORIAS = df_categorias["Categoria"].dropna().unique().tolist() if not df_categorias.empty else []
for cat in ["Cartão de Crédito", "Investimento", "Receita/Salário", "Outros"]:
    if cat not in LISTA_CATEGORIAS:
        LISTA_CATEGORIAS.append(cat)

# Totais globais
total_entradas_global = df_dados[df_dados["Tipo"] == "Entrada"]["Valor"].sum() if not df_dados.empty else 0.0
total_saidas_global   = df_dados[df_dados["Tipo"] == "Saída"]["Valor"].sum()   if not df_dados.empty else 0.0
saldo_bancario_global = total_entradas_global - total_saidas_global

inv_aportes           = df_dados[(df_dados["Categoria"] == "Investimento") & (df_dados["Tipo"] == "Saída")]["Valor"].sum()  if not df_dados.empty else 0.0
inv_saques            = df_dados[(df_dados["Categoria"] == "Investimento") & (df_dados["Tipo"] == "Entrada")]["Valor"].sum() if not df_dados.empty else 0.0
total_investido       = inv_aportes - inv_saques
patrimonio_total      = saldo_bancario_global + total_investido


# ══════════════════════════════════════════════════════════════════════════════
# 9. PÁGINAS
# ══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
#  9.1  DASHBOARD PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
if menu == "Dashboard":
    texto_filtro = f"— {mes_selecionado}" if mes_selecionado != "Todos os Meses" else "— Todo o Período"
    st.markdown(f"## 📊 Resumo Financeiro {texto_filtro}")

    total_ent  = df_dados_filtro[df_dados_filtro["Tipo"] == "Entrada"]["Valor"].sum() if not df_dados_filtro.empty else 0.0
    total_sai  = df_dados_filtro[df_dados_filtro["Tipo"] == "Saída"]["Valor"].sum()   if not df_dados_filtro.empty else 0.0
    saldo_per  = total_ent - total_sai

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 Receitas do Período",  fmt_br(total_ent))
    c2.metric("🔴 Despesas do Período",  fmt_br(total_sai))
    c3.metric("🏦 Saldo Bancário Total", fmt_br(saldo_bancario_global), delta=fmt_br(saldo_per))
    c4.metric("💎 Patrimônio Total",     fmt_br(patrimonio_total))

    st.divider()

    # ── Projeção do próximo mês ────────────────────────────────────────────
    st.markdown("### 🔮 Projeção do Próximo Mês")

    if mes_selecionado != "Todos os Meses":
        hoje_proj = pd.to_datetime(mes_selecionado, format="%m/%Y")
    else:
        hoje_proj = pd.Timestamp(date.today())

    mes_atual_str  = hoje_proj.strftime("%m/%Y")
    proximo_mes_str = (hoje_proj + pd.DateOffset(months=1)).strftime("%m/%Y")

    receita_prevista   = carregar_config("receita_prevista", 0.0)
    total_custos_fixos = df_custos["Valor"].sum() if not df_custos.empty else 0.0
    fatura_abater      = (
        df_cartao[(df_cartao["Mês da Fatura"] == mes_atual_str) & (df_cartao["Status"] == "Pendente")]["Valor"].sum()
        if not df_cartao.empty else 0.0
    )
    saldo_projetado = receita_prevista - total_custos_fixos - fatura_abater

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Receita Prevista",    fmt_br(receita_prevista))
    p2.metric("Custos Fixos",        fmt_br(total_custos_fixos))
    p3.metric(f"Fatura {mes_atual_str}", fmt_br(fatura_abater))
    p4.metric(
        f"💰 Saldo Livre em {proximo_mes_str}",
        fmt_br(saldo_projetado),
        delta="✅ Positivo" if saldo_projetado >= 0 else "⚠️ Negativo",
        delta_color="normal" if saldo_projetado >= 0 else "inverse",
    )

    st.divider()

    # ── Gráficos ──────────────────────────────────────────────────────────
    st.markdown("### 📉 Análise Gráfica")

    # Pizza (despesas variáveis)
    col_g1, col_g2 = st.columns([1, 1.3])
    with col_g1:
        st.markdown("**Despesas por Categoria**")
        df_sai_m = df_dados_filtro[df_dados_filtro["Tipo"] == "Saída"][["Categoria", "Valor"]].copy()
        df_sai_c = df_cartao_filtro[["Categoria", "Valor"]].copy() if not df_cartao_filtro.empty else pd.DataFrame(columns=["Categoria","Valor"])
        df_pizza = pd.concat([df_sai_m, df_sai_c])
        df_pizza = df_pizza[~df_pizza["Categoria"].isin(["Aluguel", "Condomínio", "Cartão de Crédito"])]

        if not df_pizza.empty and df_pizza["Valor"].sum() > 0:
            df_pizza_ag = df_pizza.groupby("Categoria")["Valor"].sum().reset_index()
            fig = px.pie(
                df_pizza_ag, values="Valor", names="Categoria", hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Pastel2,
            )
            fig.update_traces(textinfo="percent+label", textposition="inside")
            fig.update_layout(**PLOTLY_LAYOUT, showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Nenhuma despesa variável no período.")

    # Linha: evolução diária
    with col_g2:
        st.markdown("**Evolução Diária — Entradas x Saídas**")
        df_temp = df_dados_filtro.copy()
        if not df_temp.empty:
            df_temp["Data_DT"] = pd.to_datetime(df_temp["Data"], errors="coerce")
            df_temp = df_temp.dropna(subset=["Data_DT"])

        if not df_temp.empty:
            df_pivot = df_temp.pivot_table(index="Data_DT", columns="Tipo", values="Valor", aggfunc="sum", fill_value=0)
            for col in ["Entrada", "Saída"]:
                if col not in df_pivot.columns:
                    df_pivot[col] = 0.0
            df_pivot = df_pivot.reindex(pd.date_range(df_pivot.index.min(), df_pivot.index.max()), fill_value=0.0)
            df_melt = df_pivot.reset_index().rename(columns={"index":"Data_DT"}).melt(
                id_vars="Data_DT", value_vars=["Entrada","Saída"], var_name="Tipo", value_name="Valor"
            )
            df_melt["Dia"] = df_melt["Data_DT"].dt.strftime("%d/%m")
            fig2 = px.line(
                df_melt, x="Dia", y="Valor", color="Tipo", markers=True, line_shape="spline",
                color_discrete_map={"Entrada": COR_ENTRADA, "Saída": COR_SAIDA},
            )
            fig2.update_traces(mode="lines+markers")
            fig2.update_layout(**PLOTLY_LAYOUT, xaxis_title="Dias", yaxis_title="R$", hovermode="x unified")
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Nenhuma movimentação para exibir.")

    # Barra horizontal — totais por categoria
    st.markdown("**Totais por Categoria (Conta + Cartão)**")
    df_tot = pd.concat([
        df_dados_filtro[df_dados_filtro["Tipo"] == "Saída"][["Categoria","Valor"]],
        df_cartao_filtro[["Categoria","Valor"]] if not df_cartao_filtro.empty else pd.DataFrame(columns=["Categoria","Valor"]),
    ])
    if not df_tot.empty:
        df_tot_ag = df_tot.groupby("Categoria")["Valor"].sum().reset_index()
        df_tot_ag["Label"] = df_tot_ag["Valor"].apply(fmt_br)
        fig3 = px.bar(
            df_tot_ag.sort_values("Valor"), x="Valor", y="Categoria", orientation="h",
            text="Label", color_discrete_sequence=[COR_SAIDA],
        )
        fig3.update_traces(textposition="outside")
        fig3.update_layout(**PLOTLY_LAYOUT, xaxis_title="", yaxis_title="")
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Nenhuma despesa registrada no período.")


# ─────────────────────────────────────────────────────────────────────────────
#  9.2  DASHBOARD AUTOMÁTICO (PLUGGY)
# ─────────────────────────────────────────────────────────────────────────────
elif menu == "Dashboard Automático":
    st.markdown("## 🤖 Inteligência Financeira — Open Finance")
    st.caption("Sincronização automática via Pluggy · Dados em tempo real")

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("🔄 Sincronizar Extrato Agora", use_container_width=True):
            with st.spinner("Conectando à Pluggy..."):
                api_key = _pluggy_api_key()
                if api_key:
                    contas, txs = _pluggy_extrair(api_key)
                    if contas and txs:
                        st.session_state["contas_reais"]     = contas
                        st.session_state["transacoes_reais"] = txs
                        df_bkp = pd.DataFrame(txs).drop(columns=["Data_DT"])
                        _salvar_aba("extrato_bancario", df_bkp)
                        st.success("✅ Extrato sincronizado e salvo!")
                    else:
                        st.warning("Conta conectada, mas sem transações. Aguarde e tente novamente.")
                else:
                    st.error("Erro ao autenticar na Pluggy. Verifique as credenciais.")

    st.divider()

    # ── Dados reais ou demo ───────────────────────────────────────────────
    eh_real = "transacoes_reais" in st.session_state and "contas_reais" in st.session_state

    if eh_real:
        df_contas = pd.DataFrame(st.session_state["contas_reais"])
        df_tx     = pd.DataFrame(st.session_state["transacoes_reais"]).sort_values("Data_DT", ascending=False)
        saldo_total   = df_contas["Saldo"].sum()
        entradas_real = df_tx[df_tx["Tipo"] == "Entrada"]["Valor"].sum()
        saidas_real   = abs(df_tx[df_tx["Tipo"] == "Saída"]["Valor"].sum())
        df_banco_view = df_tx.drop(columns=["Data_DT"])
        df_cartao_view = pd.DataFrame()

        gastos_real = df_tx[df_tx["Tipo"] == "Saída"].copy()
        gastos_real["Valor"] = gastos_real["Valor"].abs()
        df_pizza_real = gastos_real.groupby("Categoria")["Valor"].sum().reset_index()

        df_tx["Dia"] = df_tx["Data_DT"].dt.strftime("%d/%m")
        df_agrupado  = df_tx.groupby("Dia")["Valor"].sum().cumsum().reset_index()
        df_agrupado.rename(columns={"Valor": "Saldo_R$"}, inplace=True)
        df_agrupado["Saldo_R$"] += saldo_total

        fatura_pendente = df_cartao[df_cartao["Status"] == "Pendente"]["Valor"].sum() if not df_cartao.empty else 0.0
        receita_base    = carregar_config("receita_prevista", 5000.0)
        comprometimento = (saidas_real / receita_base * 100) if receita_base > 0 else 0
    else:
        hoje_d = date.today()
        dias_e = [(hoje_d - timedelta(days=i)).strftime("%d/%m/%Y") for i in range(10)]
        dias_g = [(hoje_d - timedelta(days=i)).strftime("%d/%m")   for i in range(9, -1, -1)]
        df_banco_view = pd.DataFrame({
            "Data": dias_e,
            "Descrição": ["Salário","Mercado","Uber","Ifood","Pix","Luz","Netflix","Gasolina","CDI","Rest."],
            "Categoria": ["Receita","Supermercado","Transporte","Lazer","Outros","Moradia","Lazer","Transporte","Investimento","Lazer"],
            "Valor": [5000,-350,-45,-80,-150,-200,-50,-250,45,-120],
            "Tipo":  ["Entrada","Saída","Saída","Saída","Saída","Saída","Saída","Saída","Entrada","Saída"],
            "Conta": ["Demo"] * 10,
        })
        df_cartao_view = pd.DataFrame({
            "Data": dias_e[:5],
            "Descrição": ["Amazon","Mercado Livre","Farmácia","Software","Passagem"],
            "Categoria": ["Compras","Compras","Saúde","Outros","Viagem"],
            "Valor": [150,89.9,45,25,450],
            "Cartão": ["Nubank *1234"] * 5,
        })
        saldo_total     = 3800.0
        entradas_real   = 5045.0
        saidas_real     = 1245.0
        fatura_pendente = 759.9
        comprometimento = 40.0
        df_agrupado  = pd.DataFrame({"Dia": dias_g, "Saldo_R$": [1000,6000,5650,5605,5525,5375,5175,5125,4875,4800]})
        df_pizza_real = pd.DataFrame({"Categoria":["Supermercado","Lazer","Transporte","Moradia","Compras","Viagem"],"Valor":[350,250,295,200,240,450]})

    # ── KPIs ──────────────────────────────────────────────────────────────
    st.markdown("### 💡 Indicadores-Chave")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Saldo em Conta",       fmt_br(saldo_total),      f"↑ {fmt_br(entradas_real)}")
    k2.metric("Saídas do Mês",        fmt_br(saidas_real),      "- 15% vs mês passado",  delta_color="inverse")
    k3.metric("Fatura em Aberto",     fmt_br(fatura_pendente),  "⚠️ Verifique o vencimento", delta_color="off")
    k4.metric("Comprometimento",      f"{comprometimento:.0f}%",
              "Seguro (< 50%)" if comprometimento < 50 else "Atenção (> 50%)",
              delta_color="normal" if comprometimento < 50 else "inverse")

    if not eh_real:
        st.info("📊 Exibindo dados de demonstração. Clique em **Sincronizar** para ver seus dados reais.")

    st.divider()

    # ── Gráficos ──────────────────────────────────────────────────────────
    cg1, cg2 = st.columns([1.3, 1])
    with cg1:
        st.markdown("**Fluxo de Caixa Diário**")
        df_agrupado["Label"] = df_agrupado["Saldo_R$"].apply(fmt_br)
        fig_a = px.area(df_agrupado, x="Dia", y="Saldo_R$", text="Label", markers=True,
                        line_shape="spline", color_discrete_sequence=[COR_ENTRADA])
        fig_a.update_traces(mode="lines+markers+text", textposition="top center")
        fig_a.update_layout(**PLOTLY_LAYOUT, xaxis_title="Dias", yaxis_title="Saldo (R$)", hovermode="x unified")
        st.plotly_chart(fig_a, use_container_width=True, config={"displayModeBar": False})

    with cg2:
        st.markdown("**Concentração de Gastos**")
        df_pizza_real["Label"] = df_pizza_real["Valor"].apply(fmt_br)
        fig_b = px.bar(df_pizza_real.sort_values("Valor"), x="Valor", y="Categoria",
                       orientation="h", text="Label", color_discrete_sequence=[COR_SAIDA])
        fig_b.update_traces(textposition="outside")
        fig_b.update_layout(**PLOTLY_LAYOUT, xaxis_title="", yaxis_title="")
        st.plotly_chart(fig_b, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # ── Conexão bancária ──────────────────────────────────────────────────
    st.markdown("### 🔗 Gerenciar Conexões Bancárias")
    modo_sandbox = st.checkbox("⚙️ Modo Sandbox (Testes)", value=True)

    if st.button("🏦 Conectar Nova Conta"):
        st.session_state["mostrar_pluggy"] = True

    if st.session_state.get("mostrar_pluggy"):
        with st.spinner("Gerando ambiente seguro..."):
            api_key = _pluggy_api_key()
            if api_key:
                token = _pluggy_connect_token(api_key)
                if token:
                    sb = "true" if modo_sandbox else "false"
                    html_code = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
                    <body style="margin:0;padding:0;background:#12202e;">
                    <div id="pluggy-connect-container" style="height:700px;width:100%;border-radius:10px;overflow:hidden;"></div>
                    <script>
                        function initPluggy(){{
                            try{{
                                const pc=new window.PluggyConnect({{
                                    connectToken:'{token}',includeSandbox:{sb},
                                    container:'pluggy-connect-container',
                                    onSuccess:(d)=>{{document.getElementById('pluggy-connect-container').innerHTML='<div style="padding:40px;color:#21a663;font-family:sans-serif;text-align:center;"><h2>🎉 Conta Conectada!</h2></div>';}},
                                    onError:(e)=>{{document.getElementById('pluggy-connect-container').innerHTML='<div style="color:red;padding:20px;">'+e.message+'</div>';}}
                                }});pc.init();
                            }}catch(e){{document.getElementById('pluggy-connect-container').innerHTML='<div style="color:red;padding:20px;">'+e.message+'</div>';}}
                        }}
                        var s=document.createElement('script');
                        s.src='https://cdn.pluggy.ai/pluggy-connect/v1.3.0/pluggy-connect.js';
                        s.onload=initPluggy;document.head.appendChild(s);
                    </script></body></html>"""
                    st.info("🔐 Procure por **'Pluggy Sandbox'** na lista.") if modo_sandbox else st.warning("⚠️ Ambiente real — use somente com acesso de produção aprovado.")
                    components.html(html_code, height=750, scrolling=True)
                else:
                    st.error("Falha ao gerar token de conexão.")
            else:
                st.error("Credenciais Pluggy não configuradas.")

    st.divider()

    # ── Extratos ──────────────────────────────────────────────────────────
    st.markdown("### 📋 Últimas Transações")
    tab_banco, tab_cc = st.tabs(["🏦 Conta Corrente", "💳 Cartão de Crédito"])

    def _estilo_valor(v):
        try: return "color:#21a663;font-weight:bold" if float(v) > 0 else "color:#e05252;font-weight:bold"
        except: return ""

    with tab_banco:
        st.dataframe(df_banco_view.style.map(_estilo_valor, subset=["Valor"]), use_container_width=True, hide_index=True)
    with tab_cc:
        if not df_cartao_view.empty if isinstance(df_cartao_view, pd.DataFrame) else True:
            st.dataframe(df_cartao_view if isinstance(df_cartao_view, pd.DataFrame) and not df_cartao_view.empty
                         else df_cartao, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
#  9.3  ENTRADAS E SAÍDAS
# ─────────────────────────────────────────────────────────────────────────────
elif menu == "Entradas e Saídas":
    st.markdown("## 💰 Entradas e Saídas")

    col_form, col_table = st.columns([1, 2])

    with col_form:
        with st.form("form_lancamento", clear_on_submit=True):
            st.markdown("**Novo Lançamento**")
            data       = st.date_input("Data", format="DD/MM/YYYY")
            descricao  = st.text_input("Descrição")
            categoria  = st.selectbox("Categoria", LISTA_CATEGORIAS)
            valor      = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
            tipo       = st.selectbox("Tipo", ["Saída", "Entrada"])
            submitted  = st.form_submit_button("💾 Salvar", use_container_width=True)

        if submitted:
            if not descricao.strip():
                st.warning("Preencha a descrição.")
            else:
                with st.spinner("Salvando..."):
                    _append_aba("financeiro", {
                        "Data": data.strftime("%Y-%m-%d"),
                        "Descrição": descricao,
                        "Categoria": categoria,
                        "Valor": valor,
                        "Tipo": tipo,
                    })
                st.success("✅ Lançamento salvo!")
                st.rerun()

    with col_table:
        st.markdown("**Todos os Lançamentos**")
        df_edit_view = df_dados.drop(columns=["Data_DT","Mes_Ano"], errors="ignore")
        with st.form("form_tabela_dados"):
            df_editado = st.data_editor(df_edit_view, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 Salvar Alterações"):
                with st.spinner("Salvando..."):
                    _salvar_aba("financeiro", df_editado)
                st.success("Tabela atualizada!")
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  9.4  CARTÃO DE CRÉDITO
# ─────────────────────────────────────────────────────────────────────────────
elif menu == "Cartão de Crédito":
    st.markdown("## 💳 Cartão de Crédito")

    dia_fechamento  = int(carregar_config("dia_fechamento", 8))
    dia_vencimento  = int(carregar_config("dia_vencimento", 15))
    limite_atual    = carregar_config("limite_cartao", 2000.0)
    gastos_pend     = df_cartao[df_cartao["Status"] == "Pendente"]["Valor"].sum() if not df_cartao.empty else 0.0

    # Cabeçalho com limite
    ca, cb, cc = st.columns(3)
    novo_limite = ca.number_input("Limite Total (R$):", min_value=0.0, value=limite_atual, step=100.0)
    if novo_limite != limite_atual:
        salvar_config("limite_cartao", novo_limite)
    cb.metric("Limite Disponível", fmt_br(novo_limite - gastos_pend))
    cc.metric("Fatura em Aberto",  fmt_br(gastos_pend))

    st.divider()

    # ── Pagar fatura ──────────────────────────────────────────────────────
    st.markdown("### 💲 Pagar Fatura")
    faturas_pend = (
        sorted(df_cartao[df_cartao["Status"] == "Pendente"]["Mês da Fatura"].unique())
        if not df_cartao.empty else []
    )

    if faturas_pend:
        fp1, fp2, fp3 = st.columns([2, 2, 2])
        fatura_sel = fp1.selectbox("Selecionar fatura:", faturas_pend)
        total_fatura = df_cartao[
            (df_cartao["Mês da Fatura"] == fatura_sel) & (df_cartao["Status"] == "Pendente")
        ]["Valor"].sum()
        fp2.metric("Valor a Pagar", fmt_br(total_fatura))
        fp3.write(""); fp3.write("")
        if fp3.button("✅ Confirmar Pagamento"):
            with st.spinner("Registrando pagamento..."):
                df_cartao.loc[
                    (df_cartao["Mês da Fatura"] == fatura_sel) & (df_cartao["Status"] == "Pendente"), "Status"
                ] = "Pago"
                _salvar_aba("cartao", df_cartao)
                _append_aba("financeiro", {
                    "Data": date.today().strftime("%Y-%m-%d"),
                    "Descrição": f"Pagamento Fatura {fatura_sel}",
                    "Categoria": "Cartão de Crédito",
                    "Valor": total_fatura,
                    "Tipo": "Saída",
                })
            st.success(f"✅ Fatura {fatura_sel} paga!")
            st.rerun()
    else:
        st.success("🎉 Nenhuma fatura pendente!")

    st.divider()

    # ── Próximas 6 faturas ────────────────────────────────────────────────
    st.markdown("### 🗓️ Próximas Faturas")
    hoje = pd.Timestamp(date.today())
    pend_ativas = df_cartao[df_cartao["Status"] == "Pendente"]["Mês da Fatura"].unique() if not df_cartao.empty else []

    if len(pend_ativas):
        mes_base = pd.to_datetime(pend_ativas, format="%m/%Y").min()
    else:
        mes_base = hoje - pd.DateOffset(months=1) if hoje.day < dia_fechamento else hoje

    cols_fat = st.columns(6)
    for i in range(6):
        mes_str = (mes_base + pd.DateOffset(months=i)).strftime("%m/%Y")
        total   = df_cartao[(df_cartao["Mês da Fatura"] == mes_str) & (df_cartao["Status"] == "Pendente")]["Valor"].sum() if not df_cartao.empty else 0.0
        cols_fat[i].metric(f"📅 {mes_str}", fmt_br(total))

    st.divider()

    # ── Gráfico + formulário de lançamento ────────────────────────────────
    cg, cf = st.columns([1, 1])

    with cf:
        st.markdown("**🛒 Nova Compra**")
        with st.form("form_cartao", clear_on_submit=True):
            data_c  = st.date_input("Data da Compra", format="DD/MM/YYYY")
            desc_c  = st.text_input("Descrição")
            cat_c   = st.selectbox("Categoria", LISTA_CATEGORIAS)
            v1, v2  = st.columns(2)
            valor_c = v1.number_input("Valor Total (R$)", min_value=0.01, format="%.2f")
            parcelas= v2.number_input("Parcelas", min_value=1, max_value=48, value=1)

            if st.form_submit_button("Lançar Compra", use_container_width=True):
                with st.spinner("Registrando..."):
                    data_dt    = pd.to_datetime(data_c)
                    mes_inicio = data_dt - pd.DateOffset(months=1) if data_dt.day < dia_fechamento else data_dt
                    val_parc   = valor_c / parcelas
                    novos      = []
                    for i in range(parcelas):
                        mes_fat = (mes_inicio + pd.DateOffset(months=i)).strftime("%m/%Y")
                        novos.append({
                            "Data Compra": str(data_c), "Mês da Fatura": mes_fat,
                            "Descrição": desc_c, "Categoria": cat_c,
                            "Parcela": f"{i+1}/{parcelas}", "Valor": val_parc, "Status": "Pendente",
                        })
                    df_novos  = pd.DataFrame(novos)
                    df_cartao = pd.concat([df_cartao, df_novos], ignore_index=True)
                    _salvar_aba("cartao", df_cartao)
                st.success(f"✅ Compra lançada! 1ª parcela na fatura {mes_inicio.strftime('%m/%Y')}")
                st.rerun()

    with cg:
        st.markdown(f"**📉 Gastos por Categoria{' — ' + mes_selecionado if mes_selecionado != 'Todos os Meses' else ''}**")
        if not df_cartao_filtro.empty:
            df_ag = df_cartao_filtro.groupby("Categoria")["Valor"].sum().reset_index()
            df_ag["Label"] = df_ag["Valor"].apply(fmt_br)
            fig_cc = px.bar(df_ag, x="Categoria", y="Valor", text="Label", color_discrete_sequence=[COR_ROXO])
            fig_cc.update_traces(textposition="outside")
            fig_cc.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig_cc, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Nenhuma compra neste período.")

    st.divider()

    st.markdown("### 🧾 Extrato do Cartão")
    with st.form("form_extrato_cartao"):
        df_cc_ed = st.data_editor(df_cartao, num_rows="dynamic", use_container_width=True)
        if st.form_submit_button("💾 Salvar Alterações"):
            with st.spinner("Salvando..."):
                _salvar_aba("cartao", df_cc_ed)
            st.success("Extrato salvo!")
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  9.5  INVESTIMENTOS
# ─────────────────────────────────────────────────────────────────────────────
elif menu == "Investimentos":
    st.markdown("## 📈 Investimentos")
    aba_metas, aba_simulador = st.tabs(["🎯 Metas e Aportes", "🔮 Simulador de Juros Compostos"])

    with aba_metas:
        meta_atual = carregar_config("meta_reserva", 10000.0)
        nova_meta  = st.number_input("Meta da Reserva de Emergência (R$):", min_value=100.0, value=meta_atual, step=500.0)
        if nova_meta != meta_atual:
            salvar_config("meta_reserva", nova_meta)

        val_reserva = min(total_investido, nova_meta)
        val_outros  = max(0.0, total_investido - nova_meta)

        m1, m2, m3 = st.columns(3)
        m1.metric("💰 Total Investido",       fmt_br(total_investido))
        m2.metric("🛡️ Fundo de Emergência",   fmt_br(val_reserva))
        m3.metric("📊 Outros Investimentos",  fmt_br(val_outros))

        progresso = min(val_reserva / nova_meta, 1.0) if nova_meta > 0 else 0.0
        st.markdown(f"**Progresso da Reserva: {progresso*100:.1f}%**")
        st.progress(progresso)
        if progresso >= 1.0:
            st.success("🎉 Reserva completa! Novos aportes vão para Outros Investimentos.")

        st.divider()

        ca, cs = st.columns(2)
        with ca:
            with st.form("form_aporte", clear_on_submit=True):
                st.markdown("**🟢 Novo Aporte**")
                dt_a  = st.date_input("Data", format="DD/MM/YYYY", key="dt_aporte")
                val_a = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", key="val_aporte")
                if st.form_submit_button("Investir", use_container_width=True):
                    with st.spinner("Registrando..."):
                        _append_aba("financeiro", {
                            "Data": str(dt_a), "Descrição": "Aporte de Investimento",
                            "Categoria": "Investimento", "Valor": val_a, "Tipo": "Saída",
                        })
                    st.success("Aporte registrado!")
                    st.rerun()

        with cs:
            with st.form("form_saque", clear_on_submit=True):
                st.markdown("**🔴 Resgatar**")
                dt_s  = st.date_input("Data", format="DD/MM/YYYY", key="dt_saque")
                val_s = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", key="val_saque")
                if st.form_submit_button("Sacar", use_container_width=True):
                    if val_s > total_investido:
                        st.error("Saldo insuficiente!")
                    else:
                        with st.spinner("Registrando..."):
                            _append_aba("financeiro", {
                                "Data": str(dt_s), "Descrição": "Resgate de Investimento",
                                "Categoria": "Investimento", "Valor": val_s, "Tipo": "Entrada",
                            })
                        st.success("Saque realizado!")
                        st.rerun()

    with aba_simulador:
        st.markdown("### 🧮 Simulação de Juros Compostos")
        sc1, sc2 = st.columns(2)
        anos      = sc1.slider("Horizonte (anos):", 1, 30, 5)
        taxa_anual= sc2.number_input("Taxa anual estimada (%):", 0.0, 50.0, 10.0, 0.5)

        if total_investido > 0:
            rows = []
            acum = total_investido
            for ano in range(1, anos + 1):
                rend = acum * (taxa_anual / 100)
                acum += rend
                rows.append({"Ano": str(ano), "Rendimento no Ano": rend, "Patrimônio": acum})
            df_proj = pd.DataFrame(rows)
            df_proj["Label"] = df_proj["Patrimônio"].apply(fmt_br)

            fig_inv = go.Figure()
            fig_inv.add_bar(x=df_proj["Ano"], y=df_proj["Rendimento no Ano"],
                            name="Rendimento", marker_color=COR_AZUL)
            fig_inv.add_scatter(x=df_proj["Ano"], y=df_proj["Patrimônio"],
                                name="Patrimônio", mode="lines+markers",
                                line=dict(color=COR_ENTRADA, width=2))
            fig_inv.update_layout(**PLOTLY_LAYOUT, barmode="overlay",
                                  xaxis_title="Ano", yaxis_title="R$", hovermode="x unified")
            st.plotly_chart(fig_inv, use_container_width=True, config={"displayModeBar": False})

            with st.expander("📋 Ver tabela detalhada"):
                df_proj["Rendimento no Ano"] = df_proj["Rendimento no Ano"].apply(fmt_br)
                df_proj["Patrimônio"]        = df_proj["Label"]
                st.dataframe(df_proj.drop(columns=["Label"]), use_container_width=True, hide_index=True)
        else:
            st.warning("Faça seu primeiro aporte para usar o simulador.")


# ─────────────────────────────────────────────────────────────────────────────
#  9.6  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────────────────
elif menu == "Configurações":
    st.markdown("## ⚙️ Configurações e Orçamento")
    aba_cat, aba_orc, aba_cc_cfg, aba_proj = st.tabs([
        "🏷️ Categorias", "🎯 Orçamento", "💳 Regras do Cartão", "🔮 Projeção Fixa"
    ])

    with aba_cat:
        st.markdown("**Adicione, edite ou remova categorias e salve.**")
        with st.form("form_cat"):
            df_cat_ed = st.data_editor(df_categorias, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 Salvar Categorias"):
                with st.spinner("Salvando..."):
                    _salvar_aba("categorias", df_cat_ed)
                st.success("Categorias atualizadas!")
                st.rerun()

    with aba_orc:
        oc1, oc2 = st.columns([1, 1.5])
        with oc1:
            st.markdown("**Defina limites por categoria (0 = sem limite).**")
            with st.form("form_orc"):
                df_orc_ed = st.data_editor(df_orcamentos, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Orçamentos"):
                    with st.spinner("Salvando..."):
                        _salvar_aba("orcamentos", df_orc_ed)
                    st.success("Orçamentos salvos!")
                    st.rerun()

        with oc2:
            if mes_selecionado == "Todos os Meses":
                st.info("Selecione um mês no filtro lateral para ver o progresso do orçamento.")
            else:
                st.markdown(f"**📊 Progresso em {mes_selecionado}**")
                gastos_banco = df_dados_filtro[
                    (df_dados_filtro["Tipo"] == "Saída") & (df_dados_filtro["Categoria"] != "Cartão de Crédito")
                ].groupby("Categoria")["Valor"].sum()
                gastos_cc = df_cartao_filtro.groupby("Categoria")["Valor"].sum() if not df_cartao_filtro.empty else pd.Series(dtype=float)

                tem_valido = False
                for _, row in df_orcamentos.iterrows():
                    cat, lim = row["Categoria"], float(row["Limite"]) if pd.notna(row.get("Limite")) else 0.0
                    if lim <= 0:
                        continue
                    tem_valido = True
                    gasto = gastos_banco.get(cat, 0.0) + gastos_cc.get(cat, 0.0)
                    pct   = gasto / lim
                    label = f"**{cat}**: {fmt_br(gasto)} / {fmt_br(lim)}"
                    if pct >= 1.0:
                        st.error(f"🚨 {label} — Estourou!")
                        st.progress(1.0)
                    elif pct >= 0.8:
                        st.warning(f"⚠️ {label} — Atenção!")
                        st.progress(pct)
                    else:
                        st.success(f"✅ {label}")
                        st.progress(pct)

                if not tem_valido:
                    st.info("Adicione categorias com limites maiores que zero.")

    with aba_cc_cfg:
        st.markdown("**Configure as datas do seu cartão de crédito.**")
        d1, d2 = st.columns(2)
        dia_f_atual = int(carregar_config("dia_fechamento", 8))
        dia_v_atual = int(carregar_config("dia_vencimento", 15))

        novo_dia_f = d1.number_input("Dia de Fechamento:", 1, 31, dia_f_atual)
        novo_dia_v = d2.number_input("Dia de Vencimento:", 1, 31, dia_v_atual)

        if novo_dia_f != dia_f_atual:
            salvar_config("dia_fechamento", novo_dia_f)
            st.success("Dia de fechamento salvo!")
            st.rerun()
        if novo_dia_v != dia_v_atual:
            salvar_config("dia_vencimento", novo_dia_v)
            st.success("Dia de vencimento salvo!")
            st.rerun()

    with aba_proj:
        st.markdown("**Receita mensal esperada (base para projeções).**")
        receita_at = carregar_config("receita_prevista", 0.0)
        nova_rec   = st.number_input("Salário / Receita Fixa (R$):", min_value=0.0, value=receita_at, step=100.0)
        if nova_rec != receita_at:
            salvar_config("receita_prevista", nova_rec)
            st.success("Receita prevista salva!")
            st.rerun()

        st.divider()
        st.markdown("**Custos Fixos Mensais**")
        with st.form("form_custos"):
            df_cust_ed = st.data_editor(df_custos, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 Salvar Custos Fixos"):
                with st.spinner("Salvando..."):
                    _salvar_aba("custos_fixos", df_cust_ed)
                st.success("Custos fixos salvos!")
                st.rerun()
