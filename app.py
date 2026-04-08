import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date

# 1. CONFIGURAÇÃO INICIAL
st.set_page_config(page_title="Meu App Financeiro", layout="wide")

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

    # --- 2. CONEXÃO COM O GOOGLE SHEETS E NOVAS ABAS ---
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

    def obter_aba(nome, colunas):
        try: return planilha.worksheet(nome)
        except:
            aba = planilha.add_worksheet(title=nome, rows="1000", cols="20")
            aba.append_row(colunas)
            return aba

    aba_financeiro = obter_aba("financeiro", ['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo'])
    aba_cartao = obter_aba("cartao", ['Data Compra', 'Mês da Fatura', 'Descrição', 'Categoria', 'Parcela', 'Valor', 'Status'])
    aba_config = obter_aba("configuracoes", ['chave', 'valor'])
    aba_categorias = obter_aba("categorias", ['Categoria']) # Nova aba
    aba_orcamentos = obter_aba("orcamentos", ['Categoria', 'Limite']) # Nova aba

    # Funções de Carregar e Salvar
    def carregar_dados():
        dados = aba_financeiro.get_all_records()
        return pd.DataFrame(dados) if dados else pd.DataFrame(columns=['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo'])

    def salvar_dados(df):
        aba_financeiro.clear()
        aba_financeiro.update(values=[df.columns.values.tolist()] + df.astype(str).values.tolist())

    def carregar_cartao():
        dados = aba_cartao.get_all_records()
        if dados: 
            df = pd.DataFrame(dados)
            df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce') 
            return df
        return pd.DataFrame(columns=['Data Compra', 'Mês da Fatura', 'Descrição', 'Categoria', 'Parcela', 'Valor', 'Status'])

    def salvar_cartao(df):
        aba_cartao.clear()
        aba_cartao.update(values=[df.columns.values.tolist()] + df.astype(str).values.tolist())

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
        aba_config.update(values=[df.columns.values.tolist()] + df.astype(str).values.tolist())

    def carregar_categorias():
        dados = aba_categorias.get_all_records()
        if dados: return pd.DataFrame(dados)
        # Se não tiver, cria um padrão
        df_padrao = pd.DataFrame([{"Categoria": c} for c in ["Aluguel", "Supermercado", "Lazer", "Saúde", "Outros"]])
        salvar_categorias(df_padrao)
        return df_padrao

    def salvar_categorias(df):
        aba_categorias.clear()
        aba_categorias.update(values=[df.columns.values.tolist()] + df.astype(str).values.tolist())

    def carregar_orcamentos():
        dados = aba_orcamentos.get_all_records()
        if dados: 
            df = pd.DataFrame(dados)
            df['Limite'] = pd.to_numeric(df['Limite'], errors='coerce')
            return df
        return pd.DataFrame(columns=['Categoria', 'Limite'])

    def salvar_orcamentos(df):
        aba_orcamentos.clear()
        aba_orcamentos.update(values=[df.columns.values.tolist()] + df.astype(str).values.tolist())

    # Lendo tudo do banco
    df_dados = carregar_dados()
    df_dados['Valor'] = pd.to_numeric(df_dados['Valor'], errors='coerce') 
    
    # Criando a coluna de Mês/Ano para o filtro
    df_dados['Data_DT'] = pd.to_datetime(df_dados['Data'], errors='coerce')
    df_dados['Mes_Ano'] = df_dados['Data_DT'].dt.strftime('%m/%Y').fillna("Sem Data")
    
    df_cartao = carregar_cartao()
    df_categorias = carregar_categorias()
    df_orcamentos = carregar_orcamentos()

    # Prepara a Lista de Categorias do Sistema
    LISTA_CATEGORIAS = df_categorias['Categoria'].dropna().unique().tolist()
    # Protegendo categorias cruciais do sistema
    for cat_sistema in ["Cartão de Crédito", "Investimento", "Receita/Salário", "Outros"]:
        if cat_sistema not in LISTA_CATEGORIAS: LISTA_CATEGORIAS.append(cat_sistema)

    # --- 3. MENU LATERAL E FILTRO DE TEMPO ---
    st.sidebar.subheader("📅 Filtro de Mês")
    # Pega todos os meses que existem no banco e no cartão
    todos_meses = set(df_dados['Mes_Ano'].unique().tolist() + df_cartao['Mês da Fatura'].unique().tolist())
    if "Sem Data" in todos_meses: todos_meses.remove("Sem Data")
    lista_meses = sorted(list(todos_meses), reverse=True)
    
    mes_selecionado = st.sidebar.selectbox("Período:", ["Todos os Meses"] + lista_meses)
    st.sidebar.divider()
    
    menu = st.sidebar.selectbox("Escolha uma opção:", ["Dashboard", "Entradas e Saídas", "Cartão de Crédito", "Investimentos", "Configurações e Orçamento"])

    # Filtra as tabelas com base no mês selecionado
    if mes_selecionado != "Todos os Meses":
        df_dados_filtro = df_dados[df_dados['Mes_Ano'] == mes_selecionado]
        df_cartao_filtro = df_cartao[df_cartao['Mês da Fatura'] == mes_selecionado]
    else:
        df_dados_filtro = df_dados
        df_cartao_filtro = df_cartao

    # Cálculos Globais (Estes não mudam com o filtro para o Saldo Patrimonial ficar certo)
    total_entradas_global = df_dados[df_dados['Tipo'] == 'Entrada']['Valor'].sum() if not df_dados.empty else 0.0
    total_saidas_global = df_dados[df_dados['Tipo'] == 'Saída']['Valor'].sum() if not df_dados.empty else 0.0
    saldo_bancario_global = total_entradas_global - total_saidas_global
    total_investido_global = df_dados[(df_dados['Categoria'] == 'Investimento') & (df_dados['Tipo'] == 'Saída')]['Valor'].sum() if not df_dados.empty else 0.0
    patrimonio_total = saldo_bancario_global + total_investido_global


    # --- 4. LÓGICA DAS TELAS ---
    if menu == "Dashboard":
        texto_filtro = f"({mes_selecionado})" if mes_selecionado != "Todos os Meses" else "(Todo o Período)"
        st.header(f"📊 Resumo do Mês {texto_filtro}")
        
        # Métrica do filtro
        total_entradas_filtro = df_dados_filtro[df_dados_filtro['Tipo'] == 'Entrada']['Valor'].sum() if not df_dados_filtro.empty else 0.0
        total_saidas_filtro = df_dados_filtro[df_dados_filtro['Tipo'] == 'Saída']['Valor'].sum() if not df_dados_filtro.empty else 0.0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Receitas do Período", f"R$ {total_entradas_filtro:.2f}")
        col2.metric("Despesas do Período", f"R$ {total_saidas_filtro:.2f}")
        # O Saldo Bancário e Patrimônio são globais para você não achar que sumiu dinheiro!
        col3.metric("Saldo Bancário Total", f"R$ {saldo_bancario_global:.2f}")
        col4.metric("Patrimônio Total 💎", f"R$ {patrimonio_total:.2f}")
        
        st.divider()
        st.subheader("📉 Despesas por Categoria")
        df_saidas_grafico = df_dados_filtro[df_dados_filtro['Tipo'] == 'Saída']
        if not df_saidas_grafico.empty: st.bar_chart(df_saidas_grafico.groupby('Categoria')['Valor'].sum())
        else: st.info("Nenhuma despesa registrada para este período.")

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
        st.write("A tabela abaixo mostra todos os registros para permitir edições e exclusões seguras.")
        df_editado = st.data_editor(df_dados.drop(columns=['Data_DT', 'Mes_Ano']), num_rows="dynamic", use_container_width=True)
        if not df_dados.drop(columns=['Data_DT', 'Mes_Ano']).equals(df_editado):
            salvar_dados(df_editado)

    elif menu == "Cartão de Crédito":
        st.header("💳 Cartão de Crédito")
        
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

        # --- BLOCO DA PREVISÃO DE FATURAS ---
        st.subheader("🗓️ Resumo das Próximas Faturas")
        hoje = pd.Timestamp(date.today())
        
        if hoje.day <= 8: mes_base = hoje; status_fatura_atual = "Aberta"
        elif hoje.day <= 15: mes_base = hoje; status_fatura_atual = "Fechada"
        else: mes_base = hoje + pd.DateOffset(months=1); status_fatura_atual = "Aberta"
            
        lista_6_meses = [(mes_base + pd.DateOffset(months=i)).strftime('%m/%Y') for i in range(6)]
        
        colunas_fatura = st.columns(6)
        for i, mes_str in enumerate(lista_6_meses):
            total_mes = df_cartao[(df_cartao['Mês da Fatura'] == mes_str) & (df_cartao['Status'] == 'Pendente')]['Valor'].sum() if not df_cartao.empty else 0.0
            label = f"Fatura {mes_str}"
            if i == 0: label += f" ({status_fatura_atual})" 
            colunas_fatura[i].metric(label=label, value=f"R$ {total_mes:.2f}")

        st.divider()
        # ------------------------------------
        
        col_graf, col_form = st.columns([1, 1])
        with col_graf:
            texto_filtro_cc = f"({mes_selecionado})" if mes_selecionado != "Todos os Meses" else ""
            st.subheader(f"📉 Gastos por Categoria {texto_filtro_cc}")
            # Grafico usando o Filtro de Mês!
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
                    mes_inicio = data_dt if data_dt.day <= 8 else data_dt + pd.DateOffset(months=1)
                    valor_parcela = valor_total_compra / parcelas
                    novos_registros = []
                    for i in range(parcelas):
                        novos_registros.append({
                            'Data Compra': data_compra, 'Mês da Fatura': (mes_inicio + pd.DateOffset(months=i)).strftime('%m/%Y'), 
                            'Descrição': desc_compra, 'Categoria': categoria_cartao,
                            'Parcela': f"{i+1}/{parcelas}", 'Valor': valor_parcela, 'Status': 'Pendente'
                        })
                    df_cartao = pd.concat([df_cartao, pd.DataFrame(novos_registros)], ignore_index=True)
                    salvar_cartao(df_cartao)
                    st.success("Compra Lançada na Nuvem!")
                    st.rerun()
                
        st.divider()
        st.subheader("🧾 Extrato Geral do Cartão")
        st.write("A tabela mostra todos os meses para edição.")
        df_cartao_editado = st.data_editor(df_cartao, num_rows="dynamic", use_container_width=True)
        if not df_cartao.equals(df_cartao_editado):
            salvar_cartao(df_cartao_editado)

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
        
        aba_cat, aba_orc = st.tabs(["🏷️ Editar Categorias", "🎯 Orçamento Mensal"])
        
        with aba_cat:
            st.subheader("Minhas Categorias")
            st.write("Adicione, edite ou apague as categorias que aparecerão nos formulários.")
            df_cat_editado = st.data_editor(df_categorias, num_rows="dynamic", use_container_width=True)
            if not df_categorias.equals(df_cat_editado):
                salvar_categorias(df_cat_editado)
                st.success("Categorias atualizadas!")
                st.rerun()
                
        with aba_orc:
            st.subheader("Teto de Gastos por Categoria")
            st.write("Defina um limite de gastos. Coloque `0` para categorias sem limite.")
            
            col_orc1, col_orc2 = st.columns([1, 1.5])
            
            with col_orc1:
                df_orc_editado = st.data_editor(df_orcamentos, num_rows="dynamic", use_container_width=True)
                if not df_orcamentos.equals(df_orc_editado):
                    salvar_orcamentos(df_orc_editado)
                    st.success("Orçamentos salvos!")
                    st.rerun()
                    
            with col_orc2:
                if mes_selecionado == "Todos os Meses":
                    st.info("⚠️ Selecione um Mês no filtro lateral para ver a barra de progresso do orçamento.")
                else:
                    st.subheader(f"📊 Progresso em {mes_selecionado}")
                    
                    # Agrupa os gastos do banco e do cartão do MÊS SELECIONADO
                    gastos_banco = df_dados_filtro[(df_dados_filtro['Tipo'] == 'Saída') & (df_dados_filtro['Categoria'] != 'Cartão de Crédito')]
                    gastos_banco_agrupado = gastos_banco.groupby('Categoria')['Valor'].sum()
                    gastos_cartao_agrupado = df_cartao_filtro.groupby('Categoria')['Valor'].sum()
                    
                    tem_orcamento_valido = False
                    
                    for index, row in df_orcamentos.iterrows():
                        cat = row['Categoria']
                        limite = float(row['Limite']) if pd.notna(row['Limite']) else 0.0
                        
                        if limite > 0:
                            tem_orcamento_valido = True
                            # Soma banco + cartão
                            gasto_total = gastos_banco_agrupado.get(cat, 0.0) + gastos_cartao_agrupado.get(cat, 0.0)
                            
                            percentual = gasto_total / limite
                            
                            if percentual >= 1.0:
                                st.error(f"🚨 **{cat}**: R$ {gasto_total:.2f} / R$ {limite:.2f} (Estourou!)")
                                st.progress(1.0) # Trava em 100%
                            elif percentual >= 0.8:
                                st.warning(f"⚠️ **{cat}**: R$ {gasto_total:.2f} / R$ {limite:.2f} (Quase lá!)")
                                st.progress(percentual)
                            else:
                                st.success(f"✅ **{cat}**: R$ {gasto_total:.2f} / R$ {limite:.2f} (Tranquilo)")
                                st.progress(percentual)
                                
                    if not tem_orcamento_valido:
                        st.write("Adicione categorias e limites maiores que zero na tabela ao lado para ver os gráficos.")
