# Meu Monitor Financeiro

Aplicativo de controle financeiro pessoal construído em **Streamlit**, com dados
sincronizados em **Google Sheets**.

## Funcionalidades

- **Dashboard inteligente** — KPIs com comparação mês-a-mês, taxa de poupança,
  independência financeira, projeção de fluxo do mês, Sankey de fluxo
  financeiro, visão anual (últimos 12 meses) e insights automáticos.
- **Entradas e Saídas** — lançamentos manuais com busca, filtros e
  auto-sugestão de categoria a partir do histórico.
- **Cartão de Crédito** — controle de faturas com parcelamento e regras de
  fechamento/vencimento configuráveis.
- **Investimentos** — reserva de emergência, posição real (rendimento total),
  carteira por classe de ativo (alocação atual × meta) e simulador de juros
  compostos com aportes mensais e desconto de IR.
- **Configurações e Orçamento** — categorias, tetos por categoria, regras do
  cartão, custos fixos com **geração automática** de lançamentos mensais.

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
    ├── repository.py         # CRUD por aba (transações, cartão, etc.)
    ├── finance.py            # Cálculos financeiros (KPIs, séries temporais)
    ├── insights.py           # Geração de insights em linguagem natural
    ├── credit_card.py        # Regras de fatura/parcela
    ├── components.py         # Widgets reusáveis (cards, gráficos)
    ├── sidebar.py            # Sidebar (logout, filtros, menu)
    └── pages/
        ├── dashboard.py
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
   # edite o arquivo com a senha do app e o JSON da Service Account
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
