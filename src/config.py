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
        "Data Compra", "Mês da Fatura", "Cartão", "Descrição", "Categoria",
        "Parcela", "Valor", "Status",
    ],
    # Cadastro dos cartões: cada um com limite e datas próprias.
    "cartoes": [
        "Nome", "Instituição", "Limite", "Dia Fechamento", "Dia Vencimento",
    ],
    # Pagamentos parciais (adiantamentos) sobre uma fatura ainda aberta.
    "cartao_pagamentos": [
        "Data", "Cartão", "Mês da Fatura", "Valor", "Observação",
    ],
    "configuracoes": ["chave", "valor"],
    "categorias": ["Categoria"],
    "orcamentos": ["Categoria", "Limite"],
    "custos_fixos": ["Descrição", "Categoria", "Valor"],
    "posicao_investimentos": ["Data", "Valor"],
    "alocacao_investimentos": ["Classe", "Valor", "Meta (%)"],
    # Cadastro de cada ativo da carteira.
    "investimentos": [
        "Nome", "Instituição", "Classe", "Produto", "Indexador",
        "Taxa", "Data Aplicação", "Vencimento", "Isento IR", "Observações",
    ],
    # Movimentações (aporte/resgate) por ativo cadastrado.
    "investimento_movimentacoes": [
        "Data", "Investimento", "Tipo", "Valor", "Observação",
    ],
    # Valor bruto real de cada ativo, informado pela corretora/banco.
    "posicao_ativos": ["Data", "Investimento", "Valor"],
    # Cópias guardadas antes de um recomeço. Arquivar custa nada e
    # apagar não tem volta — o usuário decide depois se quer excluir.
    "arquivo_financeiro": ["Data", "Descrição", "Categoria", "Valor", "Tipo",
                           "Arquivado em"],
    "arquivo_cartao": ["Data Compra", "Mês da Fatura", "Cartão", "Descrição",
                       "Categoria", "Parcela", "Valor", "Status",
                       "Arquivado em"],
    # Retratos da posição real lida das instituições. É o que faz o app
    # mostrar o saldo do banco em vez de uma soma de lançamentos.
    "posicao_real": ["Data", "Origem", "Nome", "Classe", "Valor"],
    # Lançamentos já trazidos do Open Finance. A coluna "ID Pluggy" é o
    # que impede a mesma compra de entrar duas vezes a cada sincronização.
    "importacoes": ["ID Pluggy", "Data", "Descrição", "Valor", "Destino",
                    "Importado em"],
}

# Categorias automáticas que sempre aparecem nos selects, mesmo que o
# usuário não as tenha cadastrado manualmente.
SYSTEM_CATEGORIES = [
    "Cartão de Crédito",
    "Investimento",
    "Transferência",
    "Receita/Salário",
    "Outros",
]

DEFAULT_USER_CATEGORIES = [
    "Aluguel", "Supermercado", "Lazer", "Saúde", "Outros", "Condomínio",
]

# Cartão usado para as compras lançadas antes de existir cadastro de cartões.
DEFAULT_CARD_NAME = "Principal"

# Categorias que NÃO entram nas Receitas/Despesas do período — são
# transferências entre contas (conta corrente ↔ conta de investimento)
# e não afetam o patrimônio, só o local onde o dinheiro está parado.
# "Transferência" cobre o dinheiro que anda entre contas suas: o salário
# que cai no Itaú e vai para o Nubank aparece como saída num extrato e
# entrada no outro. Sem neutralizar, um mês de R$ 5.000 vira R$ 10.000
# de receita e R$ 5.000 de despesa — o saldo continua certo, porque é
# lido do banco, mas taxa de poupança e orçamento saem todos errados.
TRANSFER_CATEGORIES = ["Investimento", "Transferência"]
CATEGORIA_TRANSFERENCIA = "Transferência"

# Chaves de configuração persistidas na aba `configuracoes`.
class ConfigKeys:
    DIA_FECHAMENTO = "dia_fechamento"
    DIA_VENCIMENTO = "dia_vencimento"
    LIMITE_CARTAO = "limite_cartao"
    META_RESERVA = "meta_reserva"
    RECEITA_PREVISTA = "receita_prevista"
    # Premissas de mercado usadas na projeção de investimentos (% a.a.).
    TAXA_CDI = "taxa_cdi"
    TAXA_SELIC = "taxa_selic"
    TAXA_IPCA = "taxa_ipca"
    TAXA_TR = "taxa_tr"
    # Conexões do Open Finance (UUIDs separados por vírgula). Ficam na
    # planilha, e não nos secrets, porque mudam a cada reconexão — e o
    # usuário consegue editá-los sem mexer na configuração do deploy.
    PLUGGY_ITEMS = "pluggy_item_ids"
    # Para onde cada conta da Pluggy é importada: "conta da Pluggy=destino",
    # separados por ponto e vírgula. Sem isso, o importador criaria cartões
    # novos em vez de somar nos que já existem.
    PLUGGY_MAPA = "pluggy_mapa_contas"
    # Quando a última busca rodou (ISO). Evita ir à API a cada clique do
    # Streamlit, que recarrega a página inteira a cada interação.
    PLUGGY_ULTIMA_SYNC = "pluggy_ultima_sync"
    # Data de corte da importação. Existe porque o que foi digitado à
    # mão não tem identificador da Pluggy, então o app não consegue
    # reconhecê-lo e traria linha repetida.
    PLUGGY_DESDE = "pluggy_importar_desde"

# Defaults para configurações.
DEFAULTS = {
    ConfigKeys.DIA_FECHAMENTO: 8,
    ConfigKeys.DIA_VENCIMENTO: 15,
    ConfigKeys.LIMITE_CARTAO: 2000.0,
    ConfigKeys.META_RESERVA: 10000.0,
    ConfigKeys.RECEITA_PREVISTA: 0.0,
    ConfigKeys.TAXA_CDI: 13.90,
    ConfigKeys.TAXA_SELIC: 14.00,
    ConfigKeys.TAXA_IPCA: 4.44,
    ConfigKeys.TAXA_TR: 0.1709,
}

# Paleta de cores — verde "carteira premium" (gradiente do mais claro
# pro mais escuro). Verdes funcionais (income) e cores semânticas
# (vermelho pra despesa, âmbar pra alerta) ficam intactas.
class Colors:
    """Paleta do tema escuro.

    As seis cores de série foram escolhidas por cálculo, não por gosto:
    passam nas checagens de banda de luminância, piso de croma, separação
    para daltonismo e contraste sobre o fundo escuro. Trocar uma delas no
    olho quebra a que você não está olhando — refaça a validação.
    """
    # Superfícies
    BG = "#0D1117"            # fundo da página
    SURFACE = "#161B22"       # cartões
    SURFACE_2 = "#1C232B"     # linhas dentro do cartão
    BORDER = "#26303B"        # contorno discreto

    # Texto
    TEXT = "#E6EDF3"          # 14.6:1 sobre o cartão
    TEXT_MUTED = "#8B949E"    # 5.6:1
    TEXT_FAINT = "#6E7681"    # rótulos maiúsculos

    # Semântica de dinheiro
    PRIMARY = "#52BF90"       # verde da marca — saldo, positivo (7.6:1)
    PRIMARY_HOVER = "#6FD0A6"
    PRIMARY_SOFT = "#2A4A3D"  # fundo de realce
    INCOME = "#52BF90"
    INVESTMENT = "#4ADECD"
    EXPENSE = "#F85149"       # dívida, negativo (5.2:1)
    WARNING = "#D29922"
    NEUTRAL = "#8B949E"

    # Séries de gráfico, em ordem fixa. Nunca cicle nem gere uma sétima:
    # o que não couber vira "Outros".
    SERIES = [
        "#3CA368",  # verde
        "#528ED9",  # azul
        "#BA7F14",  # âmbar
        "#A474C7",  # roxo
        "#CF6963",  # vermelho
        "#00A4A4",  # teal
    ]


# TTL (segundos) do cache de leitura. Reduz chamadas à API do Google
# mas garante atualização razoável quando outro usuário edita a planilha.
CACHE_TTL_SECONDS = 60
