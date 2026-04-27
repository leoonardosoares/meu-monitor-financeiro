# Meu Monitor Financeiro

Aplicativo de controle financeiro pessoal construído em **Streamlit**, com dados
sincronizados em **Google Sheets** e integração opcional com **Open Finance**
via [Pluggy](https://pluggy.ai).

## Funcionalidades

- **Dashboard** — receitas, despesas, saldo, patrimônio e projeção do próximo mês.
- **Dashboard Automático** — extrato real do banco via Pluggy (Open Finance).
- **Entradas e Saídas** — lançamentos manuais com edição em tabela.
- **Cartão de Crédito** — controle de faturas, parcelas e pagamento.
- **Investimentos** — reserva de emergência e simulador de juros compostos.
- **Configurações e Orçamento** — categorias, tetos, regras do cartão e custos fixos.

## Estrutura do projeto

```
meu-monitor-financeiro/
├── app.py                    # Entry point: page config, autenticação, roteamento
├── requirements.txt
├── .streamlit/
│   ├── config.toml           # Tema do app
│   └── secrets.toml.example  # Modelo de credenciais
└── src/
    ├── config.py             # Constantes e defaults
    ├── auth.py               # Tela de login
    ├── styles.py             # CSS e paleta
    ├── format.py             # Formatação BR (R$, datas)
    ├── sheets.py             # Conexão com Google Sheets
    ├── repository.py         # CRUD genérico por aba
    ├── pluggy.py             # Cliente da API Pluggy
    ├── finance.py            # Cálculos financeiros
    ├── components.py         # Widgets reusáveis
    ├── sidebar.py            # Sidebar (logout, filtros, menu)
    └── pages/
        ├── dashboard.py
        ├── auto_dashboard.py
        ├── transactions.py
        ├── credit_card.py
        ├── investments.py
        └── settings.py
```

## Como rodar localmente

1. **Crie um virtualenv e instale as dependências:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate    # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure as credenciais:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   # edite o arquivo com a senha do app, JSON da Service Account e (opcional) Pluggy
   ```

3. **Compartilhe a planilha do Google Sheets** com o `client_email` da Service
   Account (permissão de Editor).

4. **Inicie o app:**
   ```bash
   streamlit run app.py
   ```

## Deploy no Streamlit Cloud

1. Faça push deste repositório no GitHub.
2. Em [share.streamlit.io](https://share.streamlit.io), crie um novo app
   apontando para `app.py`.
3. Em **Settings → Secrets**, cole o conteúdo de `.streamlit/secrets.toml`.
4. Pronto.

## Segurança

- **Nunca** comite `.streamlit/secrets.toml` (já está no `.gitignore`).
- A senha do app fica em `APP_PASSWORD` nos secrets — **não** no código.
- A planilha só é acessada pela Service Account compartilhada.
