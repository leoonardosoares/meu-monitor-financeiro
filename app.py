import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, timedelta
import plotly.express as px
import requests
import streamlit.components.v1 as components

# 1. CONFIGURAÇÃO INICIAL E ESTILO CUSTOMIZADO
st.set_page_config(page_title="Meu App Financeiro", layout="wide")

st.markdown("""
<style>
    div.stButton > button:first-child {
        background-color: #2ECC71 !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: bold !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #27AE60 !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1) !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

SENHA_DO_APP = "admin123"

if 'logado' not in st.session_state:
    st.session_state['logado'] = False

if not st.session_state['logado']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Acesso Restrito")
        st.write("Insira a senha para acessar seu Monitor Financeiro na Nuvem.")
        senha_digitada = st.text_input("Senha de Acesso:", type="password")
        if st.button("Entrar", use_container_width=True):
            if senha_digitada == SENHA_DO_APP:
                st.session_state['logado'] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
else:
    if st.sidebar.button("🚪 Sair / Logout", use_container_width=True):
        st.session_state['logado'] = False
        st.rerun()
        
    st.sidebar.divider()
    st.title("💸 Meu Monitor Financeiro (Sincronizado ☁️)")

    # --- 2. CONEXÃO COM O GOOGLE SHEETS OTIMIZADA ---
    @st.cache_resource 
    def conectar_google():
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_JSON"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("Banco_Monitor_Financeiro")

    try:
        planilha = conectar_google()
    except Exception as e:
        st.error(f"Erro ao conectar na planilha: {e}")
        st.stop()

    @st.cache_resource
    def carregar_abas():
        try:
            todas_abas = planilha.worksheets()
            titulos_existentes = {aba.title: aba for aba in todas_abas}
            
            def obter_ou_criar(nome, colunas):
                if nome in titulos_existentes:
                    return titulos_existentes[nome]
                else:
                    aba = planilha.add_worksheet(title=nome, rows="1000", cols="20")
                    aba.append_row(colunas)
                    return aba

            return {
                "financeiro": obter_ou_criar("financeiro", ['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo']),
                "cartao": obter_ou_criar("cartao", ['Data Compra', 'Mês da Fatura', 'Descrição', 'Categoria', 'Parcela', 'Valor', 'Status']),
                "configuracoes": obter_ou_criar("configuracoes", ['chave', 'valor']),
                "categorias": obter_ou_criar("categorias", ['Categoria']),
                "orcamentos": obter_ou_criar("orcamentos", ['Categoria', 'Limite']),
                "custos_fixos": obter_ou_criar("custos_fixos", ['Descrição', 'Valor']),
                "extrato_bancario": obter_ou_criar("extrato_bancario", ['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo', 'Conta'])
            }
        except Exception as e:
            st.error(f"Erro de comunicação com o Google: {e}")
            st.stop()

    abas_planilha = carregar_abas()
    aba_financeiro = abas_planilha["financeiro"]
    aba_cartao = abas_planilha["cartao"]
    aba_config = abas_planilha["configuracoes"]
    aba_categorias = abas_planilha["categorias"]
    aba_orcamentos = abas_planilha["orcamentos"]
    aba_custos = abas_planilha["custos_fixos"]
    aba_extrato = abas_planilha["extrato_bancario"]

    # --- FUNÇÕES DE CARREGAR E SALVAR ---
    @st.cache_data(ttl=60)
    def carregar_dados():
        dados = aba_financeiro.get_all_records()
        return pd.DataFrame(dados) if dados else pd.DataFrame(columns=['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo'])

    def salvar_dados(df):
        aba_financeiro.clear()
        dados_limpos = json.loads(df.fillna("").astype(str).to_json(orient='values'))
        aba_financeiro.update(values=[df.columns.tolist()] + dados_limpos)
        carregar_dados.clear()

    @st.cache_data(ttl=60)
    def carregar_cartao():
        dados = aba_cartao.get_all_records()
        if dados: 
            df = pd.DataFrame(dados)
            df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce') 
            return df
        return pd.DataFrame(columns=['Data Compra', 'Mês da Fatura', 'Descrição', 'Categoria', 'Parcela', 'Valor', 'Status'])

    def salvar_cartao(df):
        aba_cartao.clear()
        dados_limpos = json.loads(df.fillna("").astype(str).to_json(orient='values'))
        aba_cartao.update(values=[df.columns.tolist()] + dados_limpos)
        carregar_cartao.clear()

    def salvar_extrato_bancario_google(df):
        aba_extrato.clear()
        dados_limpos = json.loads(df.fillna("").astype(str).to_json(orient='values'))
        aba_extrato.update(values=[df.columns.tolist()] + dados_limpos)

    @st.cache_data(ttl=60)
    def carregar_valor(chave, padrao):
        dados = aba_config.get_all_records()
        df = pd.DataFrame(dados) if dados else pd.DataFrame(columns=['chave', 'valor'])
        if not df.empty and chave in df['chave'].values: return float(df.loc[df['chave'] == chave, 'valor'].iloc[0])
        return padrao

    def salvar_valor(chave, valor):
        dados = aba_config.get_all_records()
        df = pd.DataFrame(dados) if dados else pd.DataFrame(columns=['chave', 'valor'])
        if chave in df['chave'].values: df.loc[df['chave'] == chave, 'valor'] = valor
        else: df = pd.concat([df, pd.DataFrame([{'chave': chave, 'valor': valor}])], ignore_index=True)
        aba_config.clear()
        dados_limpos = json.loads(df.fillna("").astype(str).to_json(orient='values'))
        aba_config.update(values=[df.columns.tolist()] + dados_limpos)
        carregar_valor.clear()

    @st.cache_data(ttl=60)
    def carregar_categorias():
        dados = aba_categorias.get_all_records()
        if dados: return pd.DataFrame(dados)
        df_padrao = pd.DataFrame([{"Categoria": c} for c in ["Aluguel", "Supermercado", "Lazer", "Saúde", "Outros"]])
        salvar_categorias(df_padrao)
        return df_padrao

    def salvar_categorias(df):
        aba_categorias.clear()
        dados_limpos = json.loads(df.fillna("").astype(str).to_json(orient='values'))
        aba_categorias.update(values=[df.columns.tolist()] + dados_limpos)
        carregar_categorias.clear()

    @st.cache_data(ttl=60)
    def carregar_orcamentos():
        dados = aba_orcamentos.get_all_records()
        if dados: 
            df = pd.DataFrame(dados)
            df['Limite'] = pd.to_numeric(df['Limite'], errors='coerce')
            return df
        return pd.DataFrame(columns=['Categoria', 'Limite'])

    def salvar_orcamentos(df):
        aba_orcamentos.clear()
        dados_limpos = json.loads(df.fillna("").astype(str).to_json(orient='values'))
        aba_orcamentos.update(values=[df.columns.tolist()] + dados_limpos)
        carregar_orcamentos.clear()

    @st.cache_data(ttl=60)
    def carregar_custos():
        dados = aba_custos.get_all_records()
        if dados: 
            df = pd.DataFrame(dados)
            df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
            return df
        return pd.DataFrame(columns=['Descrição', 'Valor'])

    def salvar_custos(df):
        aba_custos.clear()
        dados_limpos = json.loads(df.fillna("").astype(str).to_json(orient='values'))
        aba_custos.update(values=[df.columns.tolist()] + dados_limpos)
        carregar_custos.clear()

    # --- O MOTOR DE EXTRAÇÃO PLUGGY ---
    def obter_api_key_pluggy():
        client_id = st.secrets.get("PLUGGY_CLIENT_ID")
        client_secret = st.secrets.get("PLUGGY_CLIENT_SECRET")
        if not client_id or not client_secret: return None
        url = "https://api.pluggy.ai/auth"
        response = requests.post(url, json={"clientId": client_id, "clientSecret": client_secret}, headers={"accept": "application/json", "content-type": "application/json"})
        if response.status_code == 200: return response.json().get("apiKey")
        return None

    def obter_connect_token(api_key):
        url = "https://api.pluggy.ai/connect_token"
        response = requests.post(url, json={}, headers={"accept": "application/json", "content-type": "application/json", "X-API-KEY": api_key})
        if response.status_code == 200: return response.json().get("accessToken")
        return None

    def extrair_dados_do_banco(api_key):
        headers = {"accept": "application/json", "X-API-KEY": api_key}
        try:
            req_items = requests.get("https://api.pluggy.ai/items", headers=headers)
            items = req_items.json().get("results", [])
            
            if not items: return None, None
            
            lista_contas = []
            lista_transacoes = []
            
            for item in items:
                item_id = item["id"]
                req_acc = requests.get(f"https://api.pluggy.ai/accounts?itemId={item_id}", headers=headers)
                accounts = req_acc.json().get("results", [])
                
                for acc in accounts:
                    lista_contas.append({"Conta": acc["name"], "Tipo": acc["type"], "Saldo": float(acc["balance"])})
                    
                    req_tx = requests.get(f"https://api.pluggy.ai/transactions?accountId={acc['id']}", headers=headers)
                    transactions = req_tx.json().get("results", [])
                    
                    for tx in transactions:
                        data_formatada = pd.to_datetime(tx["date"]).strftime('%d/%m/%Y')
                        valor = float(tx["amount"])
                        lista_transacoes.append({
                            "Data": data_formatada, "Descrição": tx["description"],
                            "Categoria": tx.get("category", "Outros"), "Valor": valor,
                            "Tipo": "Entrada" if valor > 0 else "Saída", "Conta": acc["name"],
                            "Data_DT": pd.to_datetime(tx["date"]).tz_localize(None)
                        })
                        
            return lista_contas, lista_transacoes
        except Exception as e:
            st.error(f"Erro no motor de extração: {e}")
            return None, None

    # Lendo tudo do banco Google
    df_dados = carregar_dados()
    df_dados['Valor'] = pd.to_numeric(df_dados['Valor'], errors='coerce') 
    df_dados['Data_DT'] = pd.to_datetime(df_dados['Data'], errors='coerce')
    df_dados['Mes_Ano'] = df_dados['Data_DT'].dt.strftime('%m/%Y').fillna("Sem Data")
    
    df_cartao = carregar_cartao()
    df_categorias = carregar_categorias()
    df_orcamentos = carregar_orcamentos()
    df_custos = carregar_custos()

    LISTA_CATEGORIAS = df_categorias['Categoria'].dropna().unique().tolist()
    for cat_sistema in ["Cartão de Crédito", "Investimento", "Receita/Salário", "Outros"]:
        if cat_sistema not in LISTA_CATEGORIAS: LISTA_CATEGORIAS.append(cat_sistema)

    # --- 3. MENU LATERAL E FILTRO DE TEMPO ---
    st.sidebar.subheader("📅 Filtro de Mês")
    todos_meses = set(df_dados['Mes_Ano'].unique().tolist() + df_cartao['Mês da Fatura'].unique().tolist())
    if "Sem Data" in todos_meses: todos_meses.remove("Sem Data")
    lista_meses = sorted(list(todos_meses), reverse=True)
    
    mes_selecionado = st.sidebar.selectbox("Período:", ["Todos os Meses"] + lista_meses)
    st.sidebar.divider()
    
    menu = st.sidebar.selectbox("Escolha uma opção:", [
        "Dashboard Automático 🤖", 
        "Dashboard (Manual)", 
        "Entradas e Saídas", 
        "Cartão de Crédito", 
        "Investimentos", 
        "Configurações e Orçamento"
    ])

    if mes_selecionado != "Todos os Meses":
        df_dados_filtro = df_dados[df_dados['Mes_Ano'] == mes_selecionado]
        df_cartao_filtro = df_cartao[df_cartao['Mês da Fatura'] == mes_selecionado]
    else:
        df_dados_filtro = df_dados
        df_cartao_filtro = df_cartao

    total_entradas_global = df_dados[df_dados['Tipo'] == 'Entrada']['Valor'].sum() if not df_dados.empty else 0.0
    total_saidas_global = df_dados[df_dados['Tipo'] == 'Saída']['Valor'].sum() if not df_dados.empty else 0.0
    saldo_bancario_global = total_entradas_global - total_saidas_global
    total_investido_global = df_dados[(df_dados['Categoria'] == 'Investimento') & (df_dados['Tipo'] == 'Saída')]['Valor'].sum() if not df_dados.empty else 0.0
    patrimonio_total = saldo_bancario_global + total_investido_global

    # --- 4. LÓGICA DAS TELAS ---
    if menu == "Dashboard (Manual)":
        texto_filtro = f"({mes_selecionado})" if mes_selecionado != "Todos os Meses" else "(Todo o Período)"
        st.header(f"📊 Resumo do Mês {texto_filtro}")
        total_entradas_filtro = df_dados_filtro[df_dados_filtro['Tipo'] == 'Entrada']['Valor'].sum() if not df_dados_filtro.empty else 0.0
        total_saidas_filtro = df_dados_filtro[df_dados_filtro['Tipo'] == 'Saída']['Valor'].sum() if not df_dados_filtro.empty else 0.0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Receitas do Período", f"R$ {total_entradas_filtro:.2f}")
        col2.metric("Despesas do Período", f"R$ {total_saidas_filtro:.2f}")
        col3.metric("Saldo Bancário Total", f"R$ {saldo_bancario_global:.2f}")
        col4.metric("Patrimônio Total 💎", f"R$ {patrimonio_total:.2f}")
        st.divider()
        
        st.subheader("📉 Análise Gráfica do Período")
        col_dash1, col_dash2 = st.columns([1, 1.2])
        with col_dash1:
            df_saidas_grafico = df_dados_filtro[df_dados_filtro['Tipo'] == 'Saída']
            if not df_saidas_grafico.empty:
                df_pizza = df_saidas_grafico.groupby('Categoria')['Valor'].sum().reset_index()
                fig_pizza = px.pie(df_pizza, values='Valor', names='Categoria', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_pizza.update_traces(textinfo='percent+label', textposition='inside')
                fig_pizza.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
                st.plotly_chart(fig_pizza, use_container_width=True, config={'displayModeBar': False})
            else: st.info("Nenhuma despesa para exibir.")
                
        with col_dash2:
            if not df_dados_filtro.empty:
                df_linha = df_dados_filtro.copy()
                df_linha['Data_Formatada'] = pd.to_datetime(df_linha['Data'], errors='coerce').dt.strftime('%d/%m')
                df_linha = df_linha.groupby(['Data_Formatada', 'Tipo'])['Valor'].sum().reset_index()
                fig_linha = px.line(df_linha, x='Data_Formatada', y='Valor', color='Tipo', markers=True, line_shape='spline', color_discrete_map={"Entrada": "#2ECC71", "Saída": "#E74C3C"})
                fig_linha.update_layout(xaxis_title="Dias", yaxis_title="R$", margin=dict(t=10, b=10, l=10, r=10), hovermode="x unified", legend_title_text="")
                st.plotly_chart(fig_linha, use_container_width=True, config={'displayModeBar': False})
            else: st.info("Nenhuma movimentação para exibir.")

    elif menu == "Dashboard Automático 🤖":
        col_tit1, col_tit2 = st.columns([2, 1])
        with col_tit1: st.header("🤖 Inteligência Financeira Automática")
        with col_tit2:
            st.write("") 
            if st.button("🔄 Puxar Extrato do Banco Agora", type="primary", use_container_width=True):
                with st.spinner("Extraindo dados da Pluggy... (Pode levar alguns segundos)"):
                    api_key = obter_api_key_pluggy()
                    if api_key:
                        contas_reais, transacoes_reais = extrair_dados_do_banco(api_key)
                        if contas_reais and transacoes_reais:
                            st.session_state['contas_reais'] = contas_reais
                            st.session_state['transacoes_reais'] = transacoes_reais
                            
                            df_backup = pd.DataFrame(transacoes_reais).drop(columns=['Data_DT'])
                            salvar_extrato_bancario_google(df_backup)
                            st.success("✅ Extrato puxado e salvo na nuvem com sucesso!")
                        else:
                            st.warning("⚠️ Conta conectada, mas o banco de testes ainda não gerou as transações. Aguarde 30 segundos e clique novamente!")
                    else:
                        st.error("Erro ao conectar com a API.")
        st.write("Visão unificada sincronizada via Open Finance.")

        if 'transacoes_reais' in st.session_state and 'contas_reais' in st.session_state:
            df_contas = pd.DataFrame(st.session_state['contas_reais'])
            df_tx = pd.DataFrame(st.session_state['transacoes_reais'])
            df_tx = df_tx.sort_values(by='Data_DT', ascending=False)
            
            saldo_total = df_contas['Saldo'].sum()
            entradas_reais = df_tx[df_tx['Tipo'] == 'Entrada']['Valor'].sum()
            saidas_reais = abs(df_tx[df_tx['Tipo'] == 'Saída']['Valor'].sum())
            
            df_tx_grafico = df_tx.copy()
            df_tx_grafico['Data_Curta'] = df_tx_grafico['Data_DT'].dt.strftime('%d/%m')
            df_agrupado = df_tx_grafico.groupby('Data_Curta')['Valor'].sum().cumsum().reset_index()
            df_agrupado.rename(columns={'Valor': 'Saldo_R$'}, inplace=True)
            df_agrupado['Saldo_R$'] = df_agrupado['Saldo_R$'] + saldo_total 
            
            gastos_consolidados = df_tx[df_tx['Tipo'] == 'Saída'].copy()
            gastos_consolidados['Valor'] = abs(gastos_consolidados['Valor'])
            df_pizza_real = gastos_consolidados.groupby('Categoria')['Valor'].sum().reset_index()
            df_banco_view = df_tx.drop(columns=['Data_DT'])
            eh_real = True
            
        else:
            st.info("👇 Estes são dados de demonstração. Clique no botão verde acima para carregar as transações do banco conectado.")
            saldo_total = 3800.00
            entradas_reais = 5045.00
            saidas_reais = 1245.00
            df_agrupado = pd.DataFrame({"Data_Curta": ["01/04", "02/04", "03/04", "04/04", "05/04", "06/04"], "Saldo_R$": [1000, 6000, 5650, 5605, 5525, 4800]})
            df_pizza_real = pd.DataFrame({"Categoria": ["Supermercado", "Lazer", "Transporte"], "Valor": [350.0, 250.0, 295.0]})
            df_banco_view = pd.DataFrame({"Data": ["09/04/2026"], "Descrição": ["PIX TESTE"], "Categoria": ["Outros"], "Valor": [100.0], "Tipo": ["Entrada"], "Conta": ["Mock"]})
            eh_real = False

        st.subheader("💡 Indicadores Sincronizados (KPIs)")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Saldo Consolidado (Hoje)", f"R$ {saldo_total:,.2f}", "+ Atualizado agora" if eh_real else "+ R$ 5.045,00 (Salário Entrou)")
        
        fatura_pendente = df_cartao[df_cartao['Status'] == 'Pendente']['Valor'].sum() if not df_cartao.empty else 0.0
        kpi2.metric("Fatura em Aberto (Cartão)", f"R$ {fatura_pendente:,.2f}" if fatura_pendente > 0 else "R$ 0,00", "⚠️ Fatura do mês" if fatura_pendente > 0 else "Nenhuma fatura pendente", delta_color="off" if fatura_pendente > 0 else "normal")
        
        kpi3.metric("Saídas (Extrato)", f"R$ {saidas_reais:,.2f}", "- Calculado pelo banco", delta_color="inverse")
        
        receita_base = carregar_valor("receita_prevista", 5000.0) 
        comprometimento = (saidas_reais / receita_base * 100) if receita_base > 0 else 0
        texto_comp = "Renda Segura (< 50%)" if comprometimento < 50 else "Atenção (Acima de 50%)"
        kpi4.metric("Comprometimento", f"{comprometimento:.0f}%" if eh_real else "40%", texto_comp if eh_real else "Renda Segura (< 50%)", delta_color="normal" if comprometimento < 50 else "inverse")
        
        st.divider()
        col_graf1, col_graf2 = st.columns([1.2, 1])
        with col_graf1:
            st.subheader("📈 Saldo Evolutivo")
            fig_area = px.area(df_agrupado, x="Data_Curta", y="Saldo_R$", title="", markers=True, line_shape="spline", color_discrete_sequence=["#2ECC71"])
            fig_area.update_layout(xaxis_title="Dias", yaxis_title="Saldo (R$)", margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
            st.plotly_chart(fig_area, use_container_width=True, config={'displayModeBar': False})
            
        with col_graf2:
            st.subheader("🍩 Para onde o dinheiro foi?")
            fig_bar = px.bar(df_pizza_real.sort_values('Valor', ascending=True), x='Valor', y='Categoria', orientation='h', color_discrete_sequence=["#E74C3C"])
            fig_bar.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="")
            st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})
            
        st.divider()

        st.subheader("🔗 Gerenciar Conexões Bancárias")
        modo_sandbox = st.checkbox("⚙️ Modo de Teste (Sandbox Ativado)", value=True, help="Desmarque esta opção APENAS quando a Pluggy aprovar seu acesso a dados reais no painel deles.")
        
        if "mostrar_pluggy" not in st.session_state: st.session_state["mostrar_pluggy"] = False
        if st.button("🏦 Conectar Nova Conta", key="btn_nova_conta"): st.session_state["mostrar_pluggy"] = True
            
        if st.session_state["mostrar_pluggy"]:
            api_key = obter_api_key_pluggy()
            if api_key:
                connect_token = obter_connect_token(api_key)
                sandbox_str = "true" if modo_sandbox else "false" 
                html_code = f"""
                <!DOCTYPE html><html><head><meta charset="utf-8"></head>
                <body style="margin: 0; padding: 0;">
                    <div id="pluggy-connect-container" style="height: 700px; width: 100%;"></div>
                    <script>
                        function initPluggy() {{
                            const pluggyConnect = new window.PluggyConnect({{
                                connectToken: '{connect_token}',
                                includeSandbox: {sandbox_str},
                                container: 'pluggy-connect-container',
                                onSuccess: (itemData) => {{ alert("Sucesso! Banco Conectado!"); }},
                            }});
                            pluggyConnect.init();
                        }}
                        var script = document.createElement('script');
                        script.src = "https://cdn.pluggy.ai/pluggy-connect/v1.3.0/pluggy-connect.js";
                        script.onload = initPluggy;
                        document.head.appendChild(script);
                    </script>
                </body></html>
                """
                st.write("---")
                if modo_sandbox: st.info("🔐 **Ambiente de Testes:** Procure por 'Pluggy Sandbox'.")
                else: st.warning("⚠️ **Ambiente Real:** Você só verá os bancos reais (Nubank, Itaú, etc) se tiver solicitado Acesso de Produção no site da Pluggy.")
                components.html(html_code, height=750, scrolling=True)

        st.divider()
        st.subheader("📋 Tabela de Transações Sincronizadas")
        def estilo_valor(val):
            try: return 'color: green; font-weight: bold' if float(val) > 0 else 'color: red; font-weight: bold'
            except: return ''

        st.dataframe(df_banco_view.style.map(estilo_valor, subset=['Valor']), use_container_width=True, hide_index=True)

    elif menu == "Entradas e Saídas":
        st.header("💰 Entradas e Saídas")
        with st.form("form_registro", clear_on_submit=True):
            data = st.date_input("Data", format="DD/MM/YYYY")
            descricao = st.text_input("Descrição")
            categoria = st.selectbox("Categoria", LISTA_CATEGORIAS)
            valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
            tipo = st.selectbox("É uma Entrada ou Saída?", ["Entrada", "Saída"])
            if st.form_submit_button("Salvar Registro"):
                df_dados = pd.concat([df_dados, pd.DataFrame([{'Data': data, 'Descrição': descricao, 'Categoria': categoria, 'Valor': valor, 'Tipo': tipo}])], ignore_index=True)
                salvar_dados(df_dados)
                st.success("Salvo com sucesso na nuvem!")
                st.rerun()
                
        st.divider()
        st.subheader("✏️ Seus Registros (Todos os Meses)")
        st.write("A tabela abaixo mostra todos os registros para permitir edições e exclusões seguras. Clique no botão abaixo para salvar as mudanças.")
        with st.form("form_tabela_dados"):
            df_editado = st.data_editor(df_dados.drop(columns=['Data_DT', 'Mes_Ano']), num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 Salvar Alterações na Tabela"):
                if not df_dados.drop(columns=['Data_DT', 'Mes_Ano']).equals(df_editado):
                    salvar_dados(df_editado)
                    st.success("Alterações salvas!")
                    st.rerun()

    elif menu == "Cartão de Crédito":
        st.header("💳 Cartão de Crédito")
        dia_fechamento = int(carregar_valor("dia_fechamento", 8))
        dia_vencimento = int(carregar_valor("dia_vencimento", 15))
        
        col_lim_esq, col_lim_dir = st.columns([1, 2])
        with col_lim_esq:
            limite_atual = carregar_valor("limite_cartao", 2000.0)
            novo_limite = st.number_input("Limite Total (R$):", min_value=0.0, value=limite_atual, step=100.0)
            if novo_limite != limite_atual: salvar_valor("limite_cartao", novo_limite)
        with col_lim_dir:
            gastos_pendentes = df_cartao[df_cartao['Status'] == 'Pendente']['Valor'].sum() if not df_cartao.empty else 0.0
            st.metric("Limite Disponível", f"R$ {novo_limite - gastos_pendentes:.2f}")

        st.divider()
        st.subheader("💲 Pagar Fatura")
        faturas_pendentes = df_cartao[df_cartao['Status'] == 'Pendente']['Mês da Fatura'].unique() if not df_cartao.empty else []
        
        if len(faturas_pendentes) > 0:
            faturas_pendentes = sorted(faturas_pendentes)
            col_pag1, col_pag2, col_pag3 = st.columns([2, 2, 2])
            with col_pag1: fatura_selecionada = st.selectbox("Selecione a fatura:", faturas_pendentes)
            with col_pag2:
                total_fatura_pagar = df_cartao[(df_cartao['Mês da Fatura'] == fatura_selecionada) & (df_cartao['Status'] == 'Pendente')]['Valor'].sum()
                st.metric("Valor a Pagar", f"R$ {total_fatura_pagar:.2f}")
            with col_pag3:
                st.write(""); st.write("")
                if st.button("✅ Confirmar Pagamento"):
                    df_cartao.loc[(df_cartao['Mês da Fatura'] == fatura_selecionada) & (df_cartao['Status'] == 'Pendente'), 'Status'] = 'Pago'
                    salvar_cartao(df_cartao)
                    df_dados = pd.concat([df_dados, pd.DataFrame([{'Data': date.today(), 'Descrição': f"Fatura ({fatura_selecionada})", 'Categoria': "Cartão de Crédito", 'Valor': total_fatura_pagar, 'Tipo': "Saída"}])], ignore_index=True)
                    salvar_dados(df_dados)
                    st.success("Fatura paga!")
                    st.rerun()
        else:
            st.success("🎉 Nenhuma fatura pendente!")

        st.divider()
        st.subheader("🗓️ Resumo das Próximas Faturas")
        hoje = pd.Timestamp(date.today())
        
        faturas_pendentes_ativas = df_cartao[df_cartao['Status'] == 'Pendente']['Mês da Fatura'].unique()
        
        if len(faturas_pendentes_ativas) > 0:
            faturas_dt = pd.to_datetime(faturas_pendentes_ativas, format='%m/%Y')
            mes_base = faturas_dt.min()
        else:
            if hoje.day < dia_fechamento:
                mes_base = hoje - pd.DateOffset(months=1)
            else:
                mes_base = hoje
                
        lista_6_meses = [(mes_base + pd.DateOffset(months=i)).strftime('%m/%Y') for i in range(6)]
        
        colunas_fatura = st.columns(6)
        for i, mes_str in enumerate(lista_6_meses):
            total_mes = df_cartao[(df_cartao['Mês da Fatura'] == mes_str) & (df_cartao['Status'] == 'Pendente')]['Valor'].sum() if not df_cartao.empty else 0.0
            label = f"Fatura {mes_str}"
            
            if i == 0: 
                if hoje.day < dia_fechamento:
                    label += " (Aberta)"
                elif dia_fechamento <= hoje.day <= dia_vencimento:
                    label += " (Fechada)"
                else:
                    label += " (Aberta)"
                    
            colunas_fatura[i].metric(label=label, value=f"R$ {total_mes:.2f}")

        st.divider()
        col_graf, col_form = st.columns([1, 1])
        with col_graf:
            texto_filtro_cc = f"({mes_selecionado})" if mes_selecionado != "Todos os Meses" else ""
            st.subheader(f"📉 Gastos por Categoria {texto_filtro_cc}")
            if not df_cartao_filtro.empty: st.bar_chart(df_cartao_filtro.groupby('Categoria')['Valor'].sum())
            else: st.info("Nenhuma compra de cartão registrada neste período.")
                
        with col_form:
            st.subheader("🛒 Lançar Compra")
            with st.form("form_cartao", clear_on_submit=True):
                data_compra = st.date_input("Data da Compra", format="DD/MM/YYYY")
                desc_compra = st.text_input("O que comprou?")
                categoria_cartao = st.selectbox("Categoria", LISTA_CATEGORIAS)
                col4, col5 = st.columns(2)
                valor_total_compra = col4.number_input("Valor Total (R$)", min_value=0.01, format="%.2f")
                parcelas = col5.number_input("Parcelas", min_value=1, max_value=48, value=1, step=1)
                
                if st.form_submit_button("Lançar"):
                    data_dt = pd.to_datetime(data_compra)
                    
                    if data_dt.day < dia_fechamento:
                        mes_inicio = data_dt - pd.DateOffset(months=1)
                    else:
                        mes_inicio = data_dt
                        
                    valor_parcela = valor_total_compra / parcelas
                    novos_registros = []
                    for i in range(parcelas):
                        mes_fatura = (mes_inicio + pd.DateOffset(months=i)).strftime('%m/%Y')
                        novos_registros.append({
                            'Data Compra': data_compra, 'Mês da Fatura': mes_fatura, 
                            'Descrição': desc_compra, 'Categoria': categoria_cartao,
                            'Parcela': f"{i+1}/{parcelas}", 'Valor': valor_parcela, 'Status': 'Pendente'
                        })
                    df_cartao = pd.concat([df_cartao, pd.DataFrame(novos_registros)], ignore_index=True)
                    salvar_cartao(df_cartao)
                    
                    st.success(f"Compra Lançada! (1ª parcela caiu na fatura {mes_inicio.strftime('%m/%Y')})")
                    st.rerun()
                
        st.divider()
        st.subheader("🧾 Extrato Geral do Cartão")
        st.write("Edite as linhas livremente. Quando terminar, clique no botão para salvar.")
        with st.form("form_tabela_cartao"):
            df_cartao_editado = st.data_editor(df_cartao, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 Salvar Alterações no Extrato"):
                if not df_cartao.equals(df_cartao_editado):
                    salvar_cartao(df_cartao_editado)
                    st.success("Extrato salvo!")
                    st.rerun()

    elif menu == "Investimentos":
        st.header("📈 Meus Investimentos")
        aba1, aba2 = st.tabs(["🎯 Metas e Aportes", "🔮 Simulador do Futuro"])
        
        with aba1:
            st.subheader("Reserva de Emergência e Transbordo")
            meta_atual = carregar_valor("meta_reserva", 10000.0)
            nova_meta = st.number_input("Defina a Meta da sua Reserva (R$):", min_value=100.0, value=meta_atual, step=500.0)
            if nova_meta != meta_atual: salvar_valor("meta_reserva", nova_meta)
            
            valor_reserva = total_investido_global if total_investido_global <= nova_meta else nova_meta
            valor_outros = 0.0 if total_investido_global <= nova_meta else total_investido_global - nova_meta
                
            col_inv1, col_inv2, col_inv3 = st.columns(3)
            col_inv1.metric("Total Investido", f"R$ {total_investido_global:.2f}")
            col_inv2.metric("Fundo de Emergência", f"R$ {valor_reserva:.2f}")
            col_inv3.metric("Outros Investimentos", f"R$ {valor_outros:.2f}")
            
            progresso = min(valor_reserva / nova_meta, 1.0)
            st.write(f"**Progresso da Reserva ({progresso * 100:.1f}%)**")
            st.progress(progresso)
            if progresso == 1.0: st.success("Reserva completa! Novos aportes irão para 'Outros Investimentos'.")
                
            st.divider()
            st.subheader("💸 Realizar Novo Aporte")
            with st.form("form_investimento", clear_on_submit=True):
                data_aporte = st.date_input("Data do Aporte", format="DD/MM/YYYY")
                valor_aporte = st.number_input("Valor a Investir (R$)", min_value=0.01, format="%.2f")
                if st.form_submit_button("Investir Agora"):
                    df_dados = pd.concat([df_dados, pd.DataFrame([{'Data': data_aporte, 'Descrição': "Aporte de Investimento", 'Categoria': "Investimento", 'Valor': valor_aporte, 'Tipo': "Saída"}])], ignore_index=True)
                    salvar_dados(df_dados)
                    st.success("Aporte registrado na Nuvem!")
                    st.rerun()

        with aba2:
            st.subheader("Mágica dos Juros Compostos")
            col_sim1, col_sim2 = st.columns(2)
            anos = col_sim1.slider("Tempo (em Anos):", min_value=1, max_value=30, value=5)
            taxa_anual = col_sim2.number_input("Taxa de Rendimento Anual estimada (%):", min_value=0.0, value=10.0, step=0.5)
            
            if total_investido_global > 0:
                dados_tabela = []
                valor_acumulado = total_investido_global
                for ano in range(1, anos + 1):
                    rendimento_do_ano = valor_acumulado * (taxa_anual / 100)
                    valor_acumulado += rendimento_do_ano
                    dados_tabela.append({"Ano": ano, "Rendimento no Ano (R$)": rendimento_do_ano, "Patrimônio Acumulado (R$)": valor_acumulado})
                df_projecao = pd.DataFrame(dados_tabela).set_index("Ano")
                st.bar_chart(df_projecao['Patrimônio Acumulado (R$)'])
            else:
                st.warning("Faça seu primeiro aporte para usar o simulador.")

    elif menu == "Configurações e Orçamento":
        st.header("⚙️ Configurações e Orçamento")
        
        aba_cat, aba_orc, aba_cartao_cfg, aba_proj = st.tabs(["🏷️ Categorias", "🎯 Orçamento", "💳 Regras do Cartão", "🔮 Projeção Fixa"])
        
        with aba_cat:
            st.subheader("Minhas Categorias")
            st.write("Adicione, edite ou apague as categorias e clique em Salvar.")
            with st.form("form_tabela_cat"):
                df_cat_editado = st.data_editor(df_categorias, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Categorias"):
                    if not df_categorias.equals(df_cat_editado):
                        salvar_categorias(df_cat_editado)
                        st.success("Categorias atualizadas!")
                        st.rerun()
                
        with aba_orc:
            st.subheader("Teto de Gastos por Categoria")
            st.write("Defina um limite de gastos. Coloque `0` para categorias sem limite.")
            col_orc1, col_orc2 = st.columns([1, 1.5])
            
            with col_orc1:
                with st.form("form_tabela_orc"):
                    df_orc_editado = st.data_editor(df_orcamentos, num_rows="dynamic", use_container_width=True)
                    if st.form_submit_button("💾 Salvar Orçamentos"):
                        if not df_orcamentos.equals(df_orc_editado):
                            salvar_orcamentos(df_orc_editado)
                            st.success("Orçamentos salvos!")
                            st.rerun()
                    
            with col_orc2:
                if mes_selecionado == "Todos os Meses":
                    st.info("⚠️ Selecione um Mês no filtro lateral para ver a barra de progresso do orçamento.")
                else:
                    st.subheader(f"📊 Progresso em {mes_selecionado}")
                    gastos_banco = df_dados_filtro[(df_dados_filtro['Tipo'] == 'Saída') & (df_dados_filtro['Categoria'] != 'Cartão de Crédito')]
                    gastos_banco_agrupado = gastos_banco.groupby('Categoria')['Valor'].sum()
                    gastos_cartao_agrupado = df_cartao_filtro.groupby('Categoria')['Valor'].sum()
                    tem_orcamento_valido = False
                    
                    for index, row in df_orcamentos.iterrows():
                        cat = row['Categoria']
                        limite = float(row['Limite']) if pd.notna(row['Limite']) else 0.0
                        if limite > 0:
                            tem_orcamento_valido = True
                            gasto_total = gastos_banco_agrupado.get(cat, 0.0) + gastos_cartao_agrupado.get(cat, 0.0)
                            percentual = gasto_total / limite
                            if percentual >= 1.0:
                                st.error(f"🚨 **{cat}**: R$ {gasto_total:.2f} / R$ {limite:.2f} (Estourou!)")
                                st.progress(1.0)
                            elif percentual >= 0.8:
                                st.warning(f"⚠️ **{cat}**: R$ {gasto_total:.2f} / R$ {limite:.2f} (Quase lá!)")
                                st.progress(percentual)
                            else:
                                st.success(f"✅ **{cat}**: R$ {gasto_total:.2f} / R$ {limite:.2f} (Tranquilo)")
                                st.progress(percentual)
                    if not tem_orcamento_valido:
                        st.write("Adicione categorias e limites maiores que zero na tabela ao lado para ver os gráficos.")

        with aba_cartao_cfg:
            st.subheader("Datas Importantes")
            st.write("Defina aqui os dias de corte do seu cartão. Isso afeta em qual mês suas compras vão cair.")
            dia_fechamento_atual = int(carregar_valor("dia_fechamento", 8))
            dia_vencimento_atual = int(carregar_valor("dia_vencimento", 15))
            
            col_dias1, col_dias2 = st.columns(2)
            novo_dia_fechamento = col_dias1.number_input("Dia de Fechamento (Melhor dia de compra):", min_value=1, max_value=31, value=dia_fechamento_atual, step=1)
            novo_dia_vencimento = col_dias2.number_input("Dia de Vencimento da Fatura:", min_value=1, max_value=31, value=dia_vencimento_atual, step=1)
            
            if novo_dia_fechamento != dia_fechamento_atual:
                salvar_valor("dia_fechamento", novo_dia_fechamento)
                st.success("Dia de fechamento atualizado na nuvem!")
                st.rerun()
            if novo_dia_vencimento != dia_vencimento_atual:
                salvar_valor("dia_vencimento", novo_dia_vencimento)
                st.success("Dia de vencimento atualizado na nuvem!")
                st.rerun()
                
        with aba_proj:
            st.subheader("Receita Base do Mês")
            receita_atual = carregar_valor("receita_prevista", 0.0)
            nova_receita = st.number_input("Qual o seu Salário / Receita fixa esperada? (R$):", min_value=0.0, value=receita_atual, step=100.0)
            if nova_receita != receita_atual:
                salvar_valor("receita_prevista", nova_receita)
                st.success("Receita prevista atualizada na nuvem!")
                st.rerun()
                
            st.divider()
            st.subheader("Custos Fixos Mensais")
            st.write("Adicione ou edite seus custos e depois clique em Salvar.")
            with st.form("form_tabela_custos"):
                df_custos_editado = st.data_editor(df_custos, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Custos Fixos"):
                    if not df_custos.equals(df_custos_editado):
                        try:
                            salvar_custos(df_custos_editado)
                            st.success("Custos fixos salvos na nuvem!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar: {e}")
