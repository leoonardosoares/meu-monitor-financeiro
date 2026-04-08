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
        try: 
            return planilha.worksheet(nome)
        except Exception as e:
            if "WorksheetNotFound" in str(type(e)):
                aba = planilha.add_worksheet(title=nome, rows="1000", cols="20")
                aba.append_row(colunas)
                return aba
            else:
                st.error("O Google pediu para aguardarmos 1 minuto. Tente recarregar a página em instantes!")
                st.stop()

    @st.cache_resource
    def carregar_abas():
        return {
            "financeiro": obter_aba("financeiro", ['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo']),
            "cartao": obter_aba("cartao", ['Data Compra', 'Mês da Fatura', 'Descrição', 'Categoria', 'Parcela', 'Valor', 'Status']),
            "configuracoes": obter_aba("configuracoes", ['chave', 'valor']),
            "categorias": obter_aba("categorias", ['Categoria']),
            "orcamentos": obter_aba("orcamentos", ['Categoria', 'Limite']),
            "custos_fixos": obter_aba("custos_fixos", ['Descrição', 'Valor'])
        }

    abas_planilha = carregar_abas()
    aba_financeiro = abas_planilha["financeiro"]
    aba_cartao = abas_planilha["cartao"]
    aba_config = abas_planilha["configuracoes"]
    aba_categorias = abas_planilha["categorias"]
    aba_orcamentos = abas_planilha["orcamentos"]
    aba_custos = abas_planilha["custos_fixos"]

    # Funções de Carregar e Salvar
    @st.cache_data(ttl=60)
    def carregar_dados():
        dados = aba
