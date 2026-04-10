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

    # --- FUNÇÕES DE CARREGAR E SALVAR COM CACHE ---
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

    # --- O MOTOR DE EXTRAÇÃO PLUGGY (NOVO!) ---
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
            # 1. Pega as conexões
            req_items = requests.get("https://api.pluggy.ai/items", headers=headers)
            items = req_items.json().get("results", [])
            
            if not items:
                return None, None
                
            lista_contas = []
            lista_transacoes = []
            
            for item in items:
                item_id = item["id"]
                # 2. Pega as Contas Correntes e Cartões
                req_acc = requests.get(f"https://api.pluggy.ai/accounts?itemId={item_id}", headers=headers)
                accounts = req_acc.json().get("results", [])
                
                for acc in accounts:
                    lista_contas.append({
                        "Conta": acc["name"],
                        "Tipo": acc["type"],
                        "Saldo": float(acc["balance"])
                    })
                    
                    # 3. Pega o Extrato
                    req_tx = requests.get(f"https://api.pluggy.ai/transactions?accountId={acc['id']}", headers=headers)
                    transactions = req_tx.json().get("results", [])
                    
                    for tx in transactions:
                        data_formatada = pd.to_datetime(tx["date"]).strftime('%d/%m/%Y')
                        valor = float(tx["amount"])
                        lista_transacoes.append({
                            "Data": data_formatada,
                            "Descrição": tx["description"],
                            "Categoria": tx.get("category", "Outros"),
                            "Valor": valor,
                            "Tipo": "Entrada" if valor > 0 else "Saída",
                            "Conta": acc["name"],
                            "Data_DT": pd.to_datetime(tx["date"]).tz_localize(None) # Para ordenação interna
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

    # --- A TELA PRINCIPAL AGORA É O DASHBOARD AUTOMÁTICO RECHEADO ---
    elif menu == "Dashboard Automático 🤖":
        col_tit1, col_tit2 = st.columns([2, 1])
        with col_tit1: st.header("🤖 Inteligência Financeira Automática")
        with col_tit2:
            st.write("") # Espaçamento
            if st.button("🔄 Puxar Extrato do Banco Agora", type="primary", use_container_width=True):
                with st.spinner("Extraindo dados milionários do banco de testes..."):
                    api_key = obter_api_key_pluggy()
                    if api_key:
                        contas_reais, transacoes_reais = extrair_dados_do_banco(api_key)
                        if contas_reais and transacoes_reais:
                            st.session_state['contas_reais'] = contas_reais
                            st.session_state['transacoes_reais'] = transacoes_reais
                            
                            # SALVANDO O BACKUP NO GOOGLE SHEETS!
                            df_backup = pd.DataFrame(transacoes_reais).drop(columns=['Data_DT'])
                            salvar_extrato_bancario_google(df_backup)
                            
                            st.success("✅ Extrato puxado e salvo na nuvem com sucesso!")
                        else:
                            st.warning("A conexão funcionou, mas não encontrei transações. Você logou no banco de testes?")
                    else:
                        st.error("Erro ao conectar com a API.")
        st.write("Visão unificada sincronizada via Open Finance.")

        # --- LÓGICA DE DADOS REAIS VS MOCKUP ---
        if 'transacoes_reais' in st.session_state and 'contas_reais' in st.session_state:
            df_contas = pd.DataFrame(st.session_state['contas_reais'])
            df_tx = pd.DataFrame(st.session_state['transacoes_reais'])
            df_tx = df_tx.sort_values(by='Data_DT', ascending=False) # Ordena do mais recente para o mais antigo
            
            saldo_total = df_contas['Saldo'].sum()
            entradas_reais = df_tx[df_tx['Tipo'] == 'Entrada']['Valor'].sum()
            saidas_reais = abs(df_tx[df_tx['Tipo'] == 'Saída']['Valor'].sum())
            
            # Gráfico Diário Real
            df_tx_grafico = df_tx.copy()
            df_tx_grafico['Data_Curta'] = df_tx_grafico['Data_DT'].dt.strftime('%d/%m')
            # Agrupa o saldo acumulado (Simplificado)
            df_agrupado = df_tx_grafico.groupby('Data_Curta')['Valor'].sum().cumsum().reset_index()
            df_agrupado.rename(columns={'Valor': 'Saldo_R$'}, inplace=True)
            df_agrupado['Saldo_R$'] = df_agrupado['Saldo_R$'] + saldo_total # Ajuste de linha de base
            
            # Gráfico Pizza Real
            gastos_consolidados = df_tx[df_tx['Tipo'] == 'Saída'].copy()
            gastos_consolidados['Valor'] = abs(gastos_consolidados['Valor'])
            df_pizza_real = gastos_consolidados.groupby('Categoria')['Valor'].sum().reset_index()
            
            df_banco_view = df_tx.drop(columns=['Data_DT'])
            
            eh_real = True
            
        else:
            # DADOS DE MENTIRA (Mock) SE AINDA NÃO CLICOU NO BOTÃO
            st.info("👇 Estes são dados de demonstração. Clique no botão verde 'Puxar Extrato do Banco Agora' acima para carregar sua conta.")
            saldo_total = 3800.00
            entradas_reais = 5045.00
            saidas_reais = 1245.00
            df_agrupado = pd.DataFrame({"Data_Curta": ["01/04", "02/04", "03/04", "04/04", "05/04", "06/04"], "Saldo_R$": [1000, 6000, 5650, 5605, 5525, 4800]})
            df_pizza_real = pd.DataFrame({"Categoria": ["Supermercado", "Lazer", "Transporte"], "Valor": [350.0, 250.0, 295.0]})
            df_banco_view = pd.DataFrame({"Data": ["09/04/2026"], "Descrição": ["PIX TESTE"], "Categoria": ["Outros"], "Valor": [100.0], "Tipo": ["Entrada"], "Conta": ["Mock"]})
            eh_real = False

        # DESENHANDO A TELA COM OS DADOS (Reais ou Falsos)
        st.subheader("💡 Indicadores Sincronizados (KPIs)")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Saldo Consolidado (Hoje)", f"R$ {saldo_total:,.2f}")
        kpi2.metric("Entradas (Extrato)", f"R$ {entradas_reais:,.2f}")
        kpi3.metric("Saídas (Extrato)", f"R$ {saidas_reais:,.2f}", "- Calculado pelo banco", delta_color="inverse")
        kpi4.metric("Status da Base", "ATUALIZADA" if eh_real else "DEMO", "Online" if eh_real else "Offline", delta_color="normal")
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

        # BLOCO DE CONEXÃO
        st.subheader("🔗 Gerenciar Conexões Bancárias")
        if "mostrar_pluggy" not in st.session_state: st.session_state["mostrar_pluggy"] = False
        if st.button("🏦 Conectar Nova Conta (Sandbox)", key="btn_nova_conta"): st.session_state["mostrar_pluggy"] = True
            
        if st.session_state["mostrar_pluggy"]:
            api_key = obter_api_key_pluggy()
            if api_key:
                connect_token = obter_connect_token(api_key)
                html_code = f"""
                <!DOCTYPE html><html><head><meta charset="utf-8"></head>
                <body style="margin: 0; padding: 0;">
                    <div id="pluggy-connect-container" style="height: 700px; width: 100%;"></div>
                    <script>
                        function initPluggy() {{
                            const pluggyConnect = new window.PluggyConnect({{
                                connectToken: '{connect_token}',
                                includeSandbox: true,
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
                components.html(html_code, height=750, scrolling=True)

        st.divider()
        st.subheader("📋 Tabela de Transações Sincronizadas")
        def estilo_valor(val):
            try: return 'color: green; font-weight: bold' if float(val) > 0 else 'color: red; font-weight: bold'
            except: return ''

        st.dataframe(df_banco_view.style.map(estilo_valor, subset=['Valor']), use_container_width=True, hide_index=True)

    elif menu == "Entradas e Saídas":
        # ... (CÓDIGO DE ENTRADAS MANUAIS MANTIDO EXATAMENTE IGUAL) ...
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
        with st.form("form_tabela_dados"):
            df_editado = st.data_editor(df_dados.drop(columns=['Data_DT', 'Mes_Ano']), num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 Salvar Alterações na Tabela"):
                if not df_dados.drop(columns=['Data_DT', 'Mes_Ano']).equals(df_editado):
                    salvar_dados(df_editado)
                    st.success("Alterações salvas!")
                    st.rerun()

    elif menu == "Cartão de Crédito":
        # ... (CÓDIGO DE CARTÃO MANTIDO) ...
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
        st.subheader("🧾 Extrato Geral do Cartão")
        with st.form("form_tabela_cartao"):
            df_cartao_editado = st.data_editor(df_cartao, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 Salvar Alterações no Extrato"):
                if not df_cartao.equals(df_cartao_editado):
                    salvar_cartao(df_cartao_editado)
                    st.success("Extrato salvo!")
                    st.rerun()

    elif menu == "Investimentos":
        # ... (CÓDIGO DE INVESTIMENTOS MANTIDO) ...
        st.header("📈 Meus Investimentos")
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
        # ... (CÓDIGO DE CONFIGURAÇÃO MANTIDO) ...
        st.header("⚙️ Configurações e Orçamento")
        st.subheader("Teto de Gastos por Categoria")
        with st.form("form_tabela_orc"):
            df_orc_editado = st.data_editor(df_orcamentos, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 Salvar Orçamentos"):
                if not df_orcamentos.equals(df_orc_editado):
                    salvar_orcamentos(df_orc_editado)
                    st.success("Orçamentos salvos!")
                    st.rerun()
