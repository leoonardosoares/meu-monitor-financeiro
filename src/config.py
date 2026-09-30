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
        "Parcela", "Valor", "Status", "ID Pluggy", "Origem",
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
    "posicao_real": ["Data", "Origem", "Nome", "Classe", "Valor",
                     "Chave"],
    # Faturas como o banco as reporta. Existe para o app mostrar o
    # total que a instituição informa, em vez de somar as linhas que
    # tem — que só coincidem se nenhuma compra faltar.
    "faturas_banco": ["Cartão", "Mês", "Total", "Fechamento", "Vencimento",
                      "Situação", "Lido em"],
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
    "Ajuste",
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
# "Ajuste" entra junto: o lançamento de conciliação existe para o saldo
# derivado reproduzir o do banco, e contá-lo como receita ou despesa
# inventaria um ganho ou um gasto que nunca aconteceu.
TRANSFER_CATEGORIES = ["Investimento", "Transferência", "Ajuste"]

# Quem trouxe cada linha do cartão. Guardar isso não é enfeite: é o que
# separa o que o banco cobrou do que o app deduziu. Uma parcela projetada
# pode ser substituída quando o banco a lançar de verdade; uma linha do
# extrato, nunca — apagá-la tira da fatura uma cobrança real.
ORIGEM_BANCO = "banco"
ORIGEM_MANUAL = "manual"
ORIGEM_PROJECAO = "projeção"
CATEGORIA_TRANSFERENCIA = "Transferência"
CATEGORIA_INVESTIMENTO = "Investimento"
CATEGORIA_AJUSTE = "Ajuste"

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
    TEMA = "tema"

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

    # Aliases do tema ativo — preenchidos por `apply_theme`. Mantidos
    # como atributos de classe para o resto do app continuar lendo
    # `Colors.TEXT` sem saber que existe troca de tema.
    @classmethod
    def use(cls, mode: str) -> None:
        for chave, valor in PALETTES.get(mode, PALETTES["dark"]).items():
            setattr(cls, chave, valor)

    # Séries de gráfico, em ordem fixa. Nunca cicle nem gere uma sétima:
    # o que não couber vira "Outros". O valor abaixo é só o inicial —
    # `use()` troca a lista pela do modo ativo.
    SERIES = [
        "#3CA368",  # verde
        "#528ED9",  # azul
        "#BA7F14",  # âmbar
        "#A474C7",  # roxo
        "#CF6963",  # vermelho
        "#00A4A4",  # teal
    ]


# Duas paletas completas. "Completa" aqui é requisito, não elegância: o
# CSS lê cada nome como variável, e um nome que falta num modo vira
# `var(--x)` sem valor — a regra é descartada pelo navegador e o elemento
# volta ao visual nativo do Streamlit. Foi assim que a etiqueta de
# multiselect ficou sem fundo: `--primary-soft` era usada e nunca
# definida. O teste `run_theme` confirma que os dois modos declaram o
# mesmo conjunto de chaves e que o CSS não cita nenhuma fora dele.
#
# As duas paletas não são uma a inversão da outra. No escuro, o que
# separa um cartão do fundo é a borda; no claro, é a sombra — um cartão
# branco delimitado só por um traço de 1px lê como formulário, não como
# painel. Por isso SHADOW muda de peso e não só de cor.
PALETTES = {
    "dark": {
        "SCHEME": "dark",
        "BG": "#0D1117", "SURFACE": "#161B22", "SURFACE_2": "#1C232B",
        "BORDER": "#26303B", "BORDER_HOVER": "#36424F",
        "TEXT": "#E6EDF3", "TEXT_MUTED": "#8B949E",
        "TEXT_FAINT": "#7D8590", "SIDEBAR": "#0A0E13",
        "PRIMARY": "#52BF90", "PRIMARY_HOVER": "#6FD0A6",
        "PRIMARY_SOFT": "#2A4A3D", "INCOME": "#52BF90",
        "INVESTMENT": "#4ADECD", "EXPENSE": "#F85149", "WARNING": "#D29922",
        "INFO": "#528ED9",
        "NEUTRAL": "#8B949E", "ON_PRIMARY": "#06251A",
        "GRID": "rgba(230,237,243,0.06)", "AXIS": "rgba(230,237,243,0.10)",
        # Trilha de barra e de progresso: o "vazio" que a cor preenche.
        "TRACK": "#232C36",
        "SHADOW": "0 1px 2px rgba(0,0,0,.28)",
        "SHADOW_LIFT": "0 8px 24px rgba(0,0,0,.36)",
        "GLOW": "0 6px 18px rgba(82,191,144,.22)",
        # Tintas de alerta: a cor semântica diluída a 8% no cartão. A
        # 14% davam uma faixa chapada — o aviso virava um verde-oliva
        # sujo atravessando a tela. O que identifica o alerta é a barra
        # colorida à esquerda; a tinta só aquece o fundo.
        "OK_SOFT": "#1B282B", "OK_LINE": "#2A5347",
        "WARN_SOFT": "#252522", "WARN_LINE": "#564622",
        "ERR_SOFT": "#281F25", "ERR_LINE": "#632D2F",
        "INFO_SOFT": "#1B2431", "INFO_LINE": "#2A4260",
        "SERIES": ["#3CA368", "#528ED9", "#BA7F14",
                   "#A474C7", "#CF6963", "#00A4A4"],
    },
    "light": {
        "SCHEME": "light",
        # A página é mais profunda que o cartão, e não quase igual: com
        # #F7F9FC o cartão branco ficava a 1,055:1 do fundo — degrau que
        # não se percebe em monitor comum, então nada delimitava nada e a
        # tela lia como uma folha só. Em #EEF2F7 a separação vai a
        # 1,124:1, acima da que o modo escuro tem (1,094:1), e o texto
        # sobre a página continua em 15,9:1.
        "BG": "#EEF2F7", "SURFACE": "#FFFFFF", "SURFACE_2": "#F1F5F9",
        "BORDER": "#E2E8F0", "BORDER_HOVER": "#CBD5E1",
        "TEXT": "#0F172A", "TEXT_MUTED": "#475569",
        "TEXT_FAINT": "#64748B", "SIDEBAR": "#FFFFFF",
        # O hover anterior (#317256) estava a 1,10:1 do próprio primário:
        # mudança que não se vê é hover quebrado. Este está a 1,51:1.
        "PRIMARY": "#2C7A5B", "PRIMARY_HOVER": "#1F5C43",
        "PRIMARY_SOFT": "#DCF2E7", "INCOME": "#2C7A5B",
        "INVESTMENT": "#0E7490", "EXPENSE": "#C62828", "WARNING": "#A16207",
        # Um tom abaixo do azul da série: INFO também rotula texto, e o
        # azul da série para em 3,99:1 sobre o branco — abaixo do piso.
        "INFO": "#3C76C0",
        "NEUTRAL": "#64748B", "ON_PRIMARY": "#FFFFFF",
        "GRID": "rgba(15,23,42,0.06)", "AXIS": "rgba(15,23,42,0.12)",
        "TRACK": "#E2E8F0",
        "SHADOW": "0 1px 2px rgba(15,23,42,.04), 0 2px 8px rgba(15,23,42,.05)",
        "SHADOW_LIFT": "0 2px 4px rgba(15,23,42,.05), "
                       "0 12px 28px rgba(15,23,42,.10)",
        "GLOW": "0 6px 18px rgba(44,122,91,.20)",
        "OK_SOFT": "#F2F7F5", "OK_LINE": "#C4DAD1",
        "WARN_SOFT": "#F9F6F0", "WARN_LINE": "#E5D3BA",
        "ERR_SOFT": "#FCF2F2", "ERR_LINE": "#EFC3C3",
        "INFO_SOFT": "#F3F7FB", "INFO_LINE": "#CBDCF1",
        # Os mesmos seis hues, escurecidos até todos darem ~3,6:1 sobre a
        # superfície interna clara. A série do escuro fica entre 2,80 e
        # 3,59:1 no claro — três abaixo do piso de 3:1 para objeto
        # gráfico, e é isso que fazia o gráfico parecer desbotado. Aqui a
        # amplitude é de 0,06, então nenhuma cor grita mais que a outra.
        "SERIES": ["#309159", "#4581CC", "#AF7409",
                   "#9D6CC1", "#C9605A", "#008F8F"],
    },
}

TEMA_PADRAO = "dark"

# TTL (segundos) do cache de leitura. Reduz chamadas à API do Google
# mas garante atualização razoável quando outro usuário edita a planilha.
CACHE_TTL_SECONDS = 60
