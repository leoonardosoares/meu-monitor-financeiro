"""Constantes globais e nomes de chaves usadas em todo o app."""
from __future__ import annotations

APP_TITLE = "Meu Monitor Financeiro"
APP_ICON = "💸"

DEFAULT_SPREADSHEET_NAME = "Banco_Monitor_Financeiro"

GOOGLE_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Estrutura das abas da planilha (nome -> colunas obrigatórias).
SHEETS_SCHEMA: dict[str, list[str]] = {
    "financeiro": ["Data", "Descrição", "Categoria", "Valor", "Tipo"],
    "cartao": [
        "Data Compra", "Mês da Fatura", "Descrição", "Categoria",
        "Parcela", "Valor", "Status",
    ],
    "configuracoes": ["chave", "valor"],
    "categorias": ["Categoria"],
    "orcamentos": ["Categoria", "Limite"],
    "custos_fixos": ["Descrição", "Categoria", "Valor"],
    "posicao_investimentos": ["Data", "Valor"],
    "alocacao_investimentos": ["Classe", "Valor", "Meta (%)"],
}

# Categorias automáticas que sempre aparecem nos selects, mesmo que o
# usuário não as tenha cadastrado manualmente.
SYSTEM_CATEGORIES = [
    "Cartão de Crédito",
    "Investimento",
    "Receita/Salário",
    "Outros",
]

DEFAULT_USER_CATEGORIES = [
    "Aluguel", "Supermercado", "Lazer", "Saúde", "Outros", "Condomínio",
]

# Categorias ignoradas no gráfico de "Despesas Variáveis" (são fixas).
FIXED_EXPENSE_CATEGORIES = ["Aluguel", "Condomínio", "Cartão de Crédito"]

# Categorias que NÃO entram nas Receitas/Despesas do período — são
# transferências entre contas (conta corrente ↔ conta de investimento)
# e não afetam o patrimônio, só o local onde o dinheiro está parado.
TRANSFER_CATEGORIES = ["Investimento"]

# Chaves de configuração persistidas na aba `configuracoes`.
class ConfigKeys:
    DIA_FECHAMENTO = "dia_fechamento"
    DIA_VENCIMENTO = "dia_vencimento"
    LIMITE_CARTAO = "limite_cartao"
    META_RESERVA = "meta_reserva"
    RECEITA_PREVISTA = "receita_prevista"

# Defaults para configurações.
DEFAULTS = {
    ConfigKeys.DIA_FECHAMENTO: 8,
    ConfigKeys.DIA_VENCIMENTO: 15,
    ConfigKeys.LIMITE_CARTAO: 2000.0,
    ConfigKeys.META_RESERVA: 10000.0,
    ConfigKeys.RECEITA_PREVISTA: 0.0,
}

# Paleta de cores usada nos gráficos e KPIs.
class Colors:
    PRIMARY = "#2563EB"      # azul confiança
    INCOME = "#10B981"       # verde esmeralda
    EXPENSE = "#EF4444"      # vermelho
    INVESTMENT = "#8B5CF6"   # roxo
    WARNING = "#F59E0B"      # âmbar
    NEUTRAL = "#64748B"      # cinza

# TTL (segundos) do cache de leitura. Reduz chamadas à API do Google
# mas garante atualização razoável quando outro usuário edita a planilha.
CACHE_TTL_SECONDS = 60
