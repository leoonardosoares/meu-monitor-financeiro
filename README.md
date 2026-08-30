# Meu Monitor Financeiro

Aplicativo de controle financeiro pessoal construído em **Streamlit**, com dados
sincronizados em **Google Sheets**.

## Funcionalidades

- **Dashboard inteligente** — KPIs com comparação mês-a-mês, taxa de poupança,
  independência financeira, ritmo de gasto do mês, visão anual (12 meses),
  status dos orçamentos, aportes mensais e insights automáticos.
- **Entradas e Saídas** — lançamentos manuais com busca, filtros e
  auto-sugestão de categoria a partir do histórico.
- **Cartão de Crédito** — vários cartões, cada um com limite e datas
  próprias. Faturas acompanhadas separadamente, com **pagamento parcial**
  (adiantar um valor para liberar limite antes do fechamento) e baixa
  total. Tudo consolidado no Dashboard.
- **Investimentos** — carteira ativo a ativo com tributação real: posição
  líquida de IOF e IR, posição real informada por ativo (real × projetado)
  com desempenho individual e consolidado, projeção bruto × líquido no
  tempo, cenários de resgate e alerta de queda da alíquota. A aba de metas
  acompanha a reserva de emergência.
- **Configurações e Orçamento** — categorias, tetos por categoria, regras do
  cartão, custos fixos com **geração automática** de lançamentos mensais.

## Tributação de investimentos

O módulo `src/investments.py` implementa as regras brasileiras vigentes,
conferidas contra fontes primárias:

- **IOF** — tabela regressiva do Decreto 6.306/2007 (96% no 1º dia a 0% no
  30º), incidente sobre o **rendimento**. Não se aplica a renda variável nem
  a papéis com carência legal acima de 30 dias (LCI, LCA, CRI, CRA, LIG).
- **IR** — tabela regressiva da Lei 11.033/2004 (22,5% / 20% / 17,5% / 15%)
  por prazo em dias corridos, com limites inclusivos. Fundos de curto prazo
  param em 20%. Isentos: LCI, LCA, CRI, CRA, LIG, debêntures incentivadas e
  poupança. Renda variável: ações 15%, FIIs 20%.
- **Ordem** — o IOF é abatido do rendimento primeiro; o IR incide sobre o
  rendimento já líquido de IOF.
- **Lotes** — cada aporte tem seu próprio prazo fiscal; resgates consomem
  lotes por FIFO. É o que faz a alíquota regressiva ficar correta quando há
  aportes em datas diferentes.
- **Projeção** — base 252 dias úteis. `% do CDI` multiplica o fator diário
  (não a taxa anual) e `IPCA+` compõe multiplicativamente (Fisher) — os dois
  erros mais comuns em calculadoras caseiras.
- **Posição real** — ao informar o valor bruto que a corretora mostra, ele
  passa a valer no lugar da projeção, inclusive como base dos impostos, e a
  curva futura cresce a partir dele. O rateio entre lotes preserva o IR
  regressivo por data de aporte.

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
    ├── investments.py        # Tributação (IOF/IR), lotes e projeção de ativos
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
