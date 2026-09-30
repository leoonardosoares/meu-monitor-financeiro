"""CSS global do app, gerado a partir da paleta do modo ativo.

O alvo é o visual de app financeiro: fundo calmo, cartões com hierarquia
clara, rótulo pequeno em maiúscula e o número grande como protagonista.
Verde para o que é seu, vermelho para o que você deve.

Duas regras ao mexer aqui:

1. **Nenhuma cor literal.** Toda cor sai de `var(--algo)`, e todo
   `--algo` sai da paleta. Um hex escrito à mão fica certo num modo e
   errado no outro — foi o que deixou a borda de hover cinza-chumbo num
   app claro e o texto do gráfico de orçamento invisível no escuro.
2. **O bloco de Material Symbols não é decorativo.** Sem ele o Streamlit
   perde a fonte de ícones e os chevrons de expander viram as palavras
   "arrow_right" na tela.
"""
from __future__ import annotations

import re

import streamlit as st

from src.config import Colors as C, PALETTES, TEMA_PADRAO

# Nome da paleta -> nome da variável CSS. Gerar as duas coisas da mesma
# lista é o que garante que não exista variável citada sem valor.
_VARS = {
    "BG": "bg", "SURFACE": "surface", "SURFACE_2": "surface-2",
    "BORDER": "border", "BORDER_HOVER": "border-hover",
    "TEXT": "text", "TEXT_MUTED": "muted", "TEXT_FAINT": "faint",
    "SIDEBAR": "sidebar",
    "PRIMARY": "green", "PRIMARY_HOVER": "green-hover",
    "PRIMARY_SOFT": "green-soft", "ON_PRIMARY": "on-primary",
    "INCOME": "income", "INVESTMENT": "investment",
    "EXPENSE": "red", "WARNING": "amber", "INFO": "blue",
    "NEUTRAL": "neutral", "TRACK": "track",
    "SHADOW": "shadow", "SHADOW_LIFT": "shadow-lift", "GLOW": "glow",
    "OK_SOFT": "ok-soft", "OK_LINE": "ok-line",
    "WARN_SOFT": "warn-soft", "WARN_LINE": "warn-line",
    "ERR_SOFT": "err-soft", "ERR_LINE": "err-line",
    "INFO_SOFT": "info-soft", "INFO_LINE": "info-line",
}


def _root() -> str:
    """Bloco `:root` com uma variável por cor da paleta ativa."""
    linhas = [f"        --{css}: {getattr(C, chave)};"
              for chave, css in _VARS.items()]
    # Diz ao navegador qual é o esquema, para scrollbar, seleção de texto
    # e controles nativos seguirem o tema em vez de ficarem escuros num
    # app claro. Vem da paleta: deduzir do hex do fundo quebra no dia em
    # que o fundo mudar de tom.
    linhas.append(f"        color-scheme: {C.SCHEME};")
    linhas.append("        --radius: 14px;")
    linhas.append("        --radius-sm: 10px;")
    return ":root {\n" + "\n".join(linhas) + "\n    }"


def _css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    __ROOT__

    html, body, .stApp {
        font-family: 'Inter', 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
        background: var(--bg);
        color: var(--text);
    }

    /* A fonte de ícones do Streamlit precisa sobreviver à troca global de
       família acima; sem isto os ícones viram texto literal. */
    [class*="material-symbols"], [class*="material-icons"],
    .material-symbols-outlined, .material-symbols-rounded, .material-icons,
    [data-testid="stIconMaterial"], [data-testid="stExpanderIcon"],
    [data-testid="stExpanderToggleIcon"],
    button[data-testid="stBaseButton-headerNoPadding"] span {
        font-family: 'Material Symbols Outlined', 'Material Symbols Rounded',
                     'Material Icons', sans-serif !important;
        font-feature-settings: 'liga' !important;
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24 !important;
    }

    /* ── Tipografia ─────────────────────────────────────────────────────
       Escala fechada e com contraste entre degraus. Antes h2 e h3 estavam
       a 0,25rem um do outro, então subtítulo e sub-subtítulo pareciam o
       mesmo nível e a página perdia hierarquia. */
    h1, h2, h3, h4, h5, h6 {
        color: var(--text);
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    h1 { font-size: 1.85rem; line-height: 1.2; }
    h2 { font-size: 1.4rem;  margin-top: .2rem; }
    h3 { font-size: 1.05rem; }
    h4, h5, h6 { font-size: .95rem; font-weight: 600; }

    /* A barra do topo e a decoração são do Streamlit e seguem o tema
       nativo, que é fixo. Sem forçar aqui, elas ficam pretas num app
       claro — foi o que deixou o topo escuro no modo claro. */
    .stApp > header, [data-testid="stHeader"] {
        background: var(--bg) !important;
    }
    [data-testid="stHeader"] * { color: var(--muted) !important; }
    [data-testid="stDecoration"] { display: none; }
    [data-testid="stToolbar"] { background: transparent !important; }
    .block-container { padding-top: 2rem; max-width: 1240px; }

    /* Espaçamento vertical: o divisor separava tanto quanto o próprio
       bloco, e a página virava uma pilha de faixas iguais. */
    hr, [data-testid="stDivider"] {
        border-color: var(--border) !important;
        margin: 1.6rem 0 1.2rem !important;
    }

    /* ── Cabeçalho de página (components.page_header) ───────────────────
       Um degrau acima de .mf-sec__title, e separado por espaço e por uma
       linha, não por um divisor do mesmo peso dos que separam seções. */
    .mf-page {
        margin: 0 0 1.4rem;
        padding-bottom: .9rem;
        border-bottom: 1px solid var(--border);
    }
    .mf-page__title {
        color: var(--text);
        font-size: 1.55rem;
        font-weight: 700;
        letter-spacing: -.028em;
        line-height: 1.2;
    }
    .mf-page__sub {
        color: var(--muted);
        font-size: .88rem;
        margin-top: .3rem;
        max-width: 72ch;
    }

    /* ── Cabeçalho de seção (components.section) ───────────────────────── */
    .mf-sec { margin: .2rem 0 .9rem; }
    .mf-sec__eyebrow {
        color: var(--faint);
        font-size: .68rem;
        font-weight: 700;
        letter-spacing: .12em;
        text-transform: uppercase;
        margin-bottom: .25rem;
    }
    .mf-sec__title {
        color: var(--text);
        font-size: 1.15rem;
        font-weight: 700;
        letter-spacing: -.02em;
        line-height: 1.25;
    }
    .mf-sec__sub {
        color: var(--muted);
        font-size: .85rem;
        margin-top: .2rem;
        max-width: 62ch;
    }

    /* ── Métrica como cartão ────────────────────────────────────────────
       É o elemento mais repetido do app; tratá-lo como cartão é o que dá
       o ar de painel financeiro sem precisar de HTML próprio em cada tela. */
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.05rem 1.2rem;
        box-shadow: var(--shadow);
        transition: border-color .18s ease, transform .18s ease,
                    box-shadow .18s ease;
    }
    [data-testid="stMetric"]:hover {
        border-color: var(--border-hover);
        box-shadow: var(--shadow-lift);
        transform: translateY(-2px);
    }
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {
        color: var(--faint) !important;
        font-size: .71rem !important;
        font-weight: 600 !important;
        letter-spacing: .08em;
        text-transform: uppercase;
    }
    [data-testid="stMetricValue"] {
        color: var(--text) !important;
        /* Encolhe conforme a coluna aperta: cinco métricas lado a lado
           cortavam o valor, e um saldo pela metade é pior que feio. */
        font-size: clamp(1.05rem, 2.1vw, 1.7rem) !important;
        font-weight: 700 !important;
        letter-spacing: -.02em;
        white-space: normal !important;
        overflow: visible !important;
    }
    /* O delta precisa de cor legível nos dois modos, mas SEM `!important`
       na cor: forçando-a, todo `delta_color` da página morria junto —
       "Disponível" negativo não ficava vermelho e "acima de 80%" não
       ficava vermelho tampouco, porque o cinza vencia o que o Streamlit
       define. Aqui o cinza é só o padrão, e a semântica passa na frente. */
    [data-testid="stMetricDelta"] {
        font-size: .75rem !important;
        font-weight: 600 !important;
        color: var(--muted);
    }
    /* E quando o Streamlit marca a direção, a cor é a da paleta, não a do
       tema nativo dele — que está fixo no escuro. */
    [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) {
        color: var(--green) !important;
    }
    [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) {
        color: var(--red) !important;
    }
    [data-testid="stMetricDelta"] svg { fill: currentColor !important; }

    /* ── Contêineres com borda viram cartão ── */
    [data-testid="stVerticalBlockBorderWrapper"] > div:has(> [data-testid="stVerticalBlock"]) {
        background: var(--surface);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
    }

    /* ── Botões ── */
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        background: var(--surface);
        color: var(--text);
        font-weight: 600;
        padding: .5rem 1.1rem;
        box-shadow: var(--shadow);
        transition: all .18s ease;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover,
    .stDownloadButton > button:hover {
        border-color: var(--green);
        color: var(--green);
        transform: translateY(-1px);
    }
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
        background: var(--green);
        border-color: var(--green);
        color: var(--on-primary);
    }
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        background: var(--green-hover);
        border-color: var(--green-hover);
        color: var(--on-primary);
        box-shadow: var(--glow);
    }

    /* ── Campos ──────────────────────────────────────────────────────
       Os widgets vêm do BaseWeb e seguem o tema nativo do Streamlit,
       que é lido na inicialização e não muda. Sem forçar cada peça, o
       seletor de período aparecia como uma caixa preta num app claro. */
    [data-baseweb="select"] > div,
    [data-baseweb="select"] div[role="button"],
    [data-baseweb="input"], [data-baseweb="base-input"],
    [data-baseweb="textarea"], [data-baseweb="datepicker"] input {
        background: var(--surface-2) !important;
        border-color: var(--border) !important;
        color: var(--text) !important;
    }
    [data-baseweb="select"] *, [data-baseweb="input"] * {
        color: var(--text) !important;
    }
    [data-baseweb="select"] svg { fill: var(--muted) !important; }
    /* A lista que abre é renderizada fora da árvore do componente. */
    [data-baseweb="popover"] [role="listbox"],
    [data-baseweb="menu"], [data-baseweb="calendar"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        box-shadow: var(--shadow-lift) !important;
    }
    [role="option"], [data-baseweb="menu"] li {
        background: var(--surface) !important;
        color: var(--text) !important;
    }
    [role="option"]:hover, [data-baseweb="menu"] li:hover {
        background: var(--surface-2) !important;
    }
    /* A etiqueta do multiselect citava uma variável que não existia e
       ficava sem fundo nenhum. */
    [data-baseweb="tag"] {
        background: var(--green-soft) !important;
        color: var(--text) !important;
        border-color: transparent !important;
    }
    [data-baseweb="tag"] span, [data-baseweb="tag"] svg {
        color: var(--text) !important;
        fill: var(--text) !important;
    }

    .stTextInput input, .stNumberInput input, .stDateInput input,
    .stSelectbox [data-baseweb="select"] > div, .stTextArea textarea {
        background: var(--surface-2) !important;
        border-color: var(--border) !important;
        color: var(--text) !important;
        border-radius: var(--radius-sm) !important;
    }
    [data-testid="stWidgetLabel"] p, .stCheckbox label p, .stRadio label p {
        color: var(--muted) !important;
        font-size: .85rem;
    }

    /* ── Abas: controle segmentado ──────────────────────────────────────
       O bloco verde atrás da aba escolhida ficava sujo — um retângulo de
       cor chapada em volta do texto. Aqui a lista inteira é uma calha
       afundada e a aba escolhida é a única pastilha ERGUIDA dentro dela:
       o destaque vem do relevo, não de um fundo colorido. */
    .stTabs [data-baseweb="tab-list"] {
        gap: .2rem;
        background: var(--surface-2);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: .25rem;
        margin-bottom: 1rem;
        display: inline-flex;
        flex-wrap: wrap;
    }
    .stTabs [data-baseweb="tab"] {
        color: var(--muted) !important;
        font-weight: 600;
        font-size: .875rem;
        padding: .45rem .95rem !important;
        border-radius: 9px;
        border: 1px solid transparent;
        transition: background .16s ease, color .16s ease,
                    box-shadow .16s ease;
    }
    .stTabs [data-baseweb="tab"] p {
        color: inherit !important;
        font-weight: 600;
    }
    .stTabs [data-baseweb="tab"]:hover { color: var(--text) !important; }
    .stTabs [aria-selected="true"] {
        background: var(--surface);
        border-color: var(--border);
        color: var(--green) !important;
        box-shadow: var(--shadow);
    }
    .stTabs [aria-selected="true"] p { color: var(--green) !important; }
    /* O sublinhado do BaseWeb competia com a pastilha. */
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] {
        background: transparent !important;
        height: 0 !important;
    }

    /* ── Tabela de leitura (components.table) ───────────────────────────
       `st.dataframe` é desenhado num canvas e segue o tema nativo do
       Streamlit, fixo no config.toml: num app claro virava um retângulo
       preto no meio da página, e folha de estilo nenhuma alcança aquilo.
       Estas são HTML de verdade, então seguem o tema. */
    .mf-tbl-wrap {
        border: 1px solid var(--border);
        border-radius: var(--radius);
        overflow-x: auto;
        background: var(--surface);
        box-shadow: var(--shadow);
        margin-bottom: .5rem;
    }
    .mf-tbl {
        width: 100%;
        border-collapse: collapse;
        font-size: .86rem;
    }
    .mf-tbl thead th {
        background: var(--surface-2);
        color: var(--faint);
        font-size: .7rem;
        font-weight: 700;
        letter-spacing: .06em;
        text-transform: uppercase;
        text-align: left;
        padding: .6rem .85rem;
        white-space: nowrap;
        border-bottom: 1px solid var(--border);
    }
    .mf-tbl tbody td {
        color: var(--text);
        padding: .55rem .85rem;
        border-top: 1px solid var(--border);
        white-space: nowrap;
    }
    .mf-tbl tbody tr:first-child td { border-top: 0; }
    .mf-tbl tbody tr:hover td { background: var(--surface-2); }
    .mf-tbl--num { text-align: right !important; font-variant-numeric: tabular-nums; }

    /* ── Expander ───────────────────────────────────────────────────────
       O cabeçalho vinha do tema nativo e aparecia como uma barra preta
       num app claro. O fundo é forçado em cada camada: o Streamlit pinta
       tanto o <details> quanto o <summary> quanto o <div> interno. */
    [data-testid="stExpander"] {
        background: var(--surface) !important;
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        overflow: hidden;
    }
    [data-testid="stExpander"] details,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] > div,
    [data-testid="stExpanderDetails"] {
        background: var(--surface) !important;
        border-color: var(--border) !important;
    }
    [data-testid="stExpander"] summary {
        color: var(--text) !important;
        font-weight: 600;
    }
    [data-testid="stExpander"] summary p { color: var(--text) !important; }
    [data-testid="stExpander"] summary:hover,
    [data-testid="stExpander"] summary:hover p { color: var(--green) !important; }

    /* ── O que o tema nativo ainda pinta ────────────────────────────────
       O `base` do config.toml é lido uma vez, na inicialização, e não
       muda: no modo claro sobravam caixas pretas onde o Streamlit aplica
       a própria cor. Cada uma é reafirmada aqui.

       Onde isso não alcança é o `st.dataframe`, desenhado num canvas —
       e é por isso que as tabelas de leitura passaram a ser HTML
       (components.table). */
    .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stMain"], [data-testid="stBottomBlockContainer"] {
        background: var(--bg) !important;
    }
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
    [data-testid="stNumberInput"] div, [data-testid="stTextInput"] div,
    [data-testid="stDateInput"] div[data-baseweb="input"] {
        background: var(--surface) !important;
        border-color: var(--border) !important;
    }
    [data-testid="stNumberInput"] button {
        background: var(--surface-2) !important;
        color: var(--text) !important;
        border-color: var(--border) !important;
    }
    [data-testid="stForm"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius);
    }
    /* O editor de tabela é canvas, mas a moldura é HTML. */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"],
    [data-testid="stDataFrameResizable"] {
        background: var(--surface) !important;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: var(--sidebar);
        border-right: 1px solid var(--border);
    }
    /* O texto da sidebar não herdava a cor do tema e sumia no claro. */
    [data-testid="stSidebar"] *:not([class*="material"]):not([data-testid="stIconMaterial"]) {
        color: var(--text);
    }
    [data-testid="stSidebar"] label p,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        color: var(--muted) !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: var(--text) !important; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: var(--faint) !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        padding: .45rem .7rem;
        border-radius: 9px;
        transition: background .15s ease, color .15s ease;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background: var(--surface-2);
        color: var(--green);
    }

    /* ── Tabelas ── */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        border: 1px solid var(--border);
        border-radius: var(--radius);
        overflow: hidden;
    }

    /* ── Avisos ─────────────────────────────────────────────────────────
       O Streamlit pinta os alertas com a paleta nativa dele, que é fixa:
       no modo claro vinham quatro azuis e vermelhos de outra família,
       sem relação com as cores do app. Cada um recebe a tinta calculada
       da sua própria cor semântica. */
    /* O aviso era uma faixa inteira de cor — no escuro dava um verde-oliva
       sujo atravessando a tela. Agora o fundo é o próprio cartão e a cor
       fica só numa barra à esquerda: o alerta é reconhecível pela cor sem
       pintar o texto inteiro por trás. */
    [data-testid="stAlert"] {
        border-radius: 12px;
        box-shadow: none;
    }
    [data-testid="stAlert"] p, [data-testid="stAlert"] li,
    [data-testid="stAlert"] strong {
        color: var(--text) !important;
    }
    [data-testid="stAlert"] > div,
    [data-testid="stAlertContentSuccess"],
    [data-testid="stAlertContentWarning"],
    [data-testid="stAlertContentError"],
    [data-testid="stAlertContentInfo"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-left: 3px solid var(--neutral) !important;
        border-radius: 12px !important;
        box-shadow: var(--shadow) !important;
    }
    [data-testid="stAlertContentSuccess"] {
        border-left-color: var(--green) !important;
        background: var(--ok-soft) !important;
    }
    [data-testid="stAlertContentWarning"] {
        border-left-color: var(--amber) !important;
        background: var(--warn-soft) !important;
    }
    [data-testid="stAlertContentError"] {
        border-left-color: var(--red) !important;
        background: var(--err-soft) !important;
    }
    [data-testid="stAlertContentInfo"] {
        border-left-color: var(--blue) !important;
        background: var(--info-soft) !important;
    }
    [data-testid="stAlert"] [data-testid="stIconMaterial"] {
        color: var(--muted) !important;
    }

    /* Legenda e texto auxiliar precisam de cor própria: o padrão do
       Streamlit é calculado a partir do tema nativo, que está fixo. */
    [data-testid="stCaptionContainer"] p {
        color: var(--muted) !important;
        font-size: .82rem;
    }
    .stMarkdown p, .stMarkdown li { color: var(--text); }
    code {
        background: var(--surface-2) !important;
        color: var(--green) !important;
        border-radius: 5px;
        padding: .1rem .35rem;
    }

    /* Barra de progresso: a trilha nativa é cinza fixo. */
    [data-testid="stProgress"] > div > div { background: var(--track) !important; }
    [data-testid="stProgress"] > div > div > div > div {
        background: var(--green) !important;
    }

    /* ── Cartão de conta (HTML próprio, ver components.stat_card) ── */
    .mf-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.15rem 1.25rem;
        box-shadow: var(--shadow);
        height: 100%;
    }
    .mf-card__label {
        color: var(--faint);
        font-size: .71rem;
        font-weight: 700;
        letter-spacing: .09em;
        text-transform: uppercase;
        margin-bottom: .35rem;
    }
    .mf-card__value {
        font-size: 1.85rem;
        font-weight: 700;
        letter-spacing: -.025em;
        margin-bottom: .2rem;
    }
    .mf-pos { color: var(--green); }
    .mf-neg { color: var(--red); }
    .mf-mut { color: var(--muted); }
    .mf-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: .75rem;
        padding: .6rem 0;
        border-top: 1px solid var(--border);
    }
    .mf-row__name { font-weight: 600; font-size: .9rem; color: var(--text); }
    .mf-row__sub { color: var(--faint); font-size: .75rem; }
    .mf-row__val { font-weight: 700; font-size: .92rem; white-space: nowrap; }
    .mf-bar {
        height: 6px;
        border-radius: 999px;
        background: var(--track);
        overflow: hidden;
        margin: .45rem 0 .1rem;
    }
    .mf-bar > span { display: block; height: 100%; border-radius: 999px; }

    /* ── Fatura como cartão (components.invoice_card) ───────────────────
       Substitui a pilha de dataframes: cada fatura é um bloco com estado,
       datas e valor, e o estado é uma etiqueta colorida em vez de um
       emoji no meio de um texto em negrito. */
    .mf-inv {
        background: var(--surface);
        border: 1px solid var(--border);
        border-left: 3px solid var(--accent, var(--border));
        border-radius: var(--radius);
        padding: .85rem 1.1rem;
        margin-bottom: .55rem;
        box-shadow: var(--shadow);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .mf-inv__who { font-weight: 700; font-size: .95rem; color: var(--text); }
    .mf-inv__when { color: var(--faint); font-size: .76rem; margin-top: .15rem; }
    .mf-inv__val {
        font-weight: 700;
        font-size: 1.15rem;
        letter-spacing: -.02em;
        white-space: nowrap;
        text-align: right;
    }
    .mf-inv__src { color: var(--faint); font-size: .7rem; font-weight: 500; }
    .mf-tag {
        display: inline-block;
        font-size: .67rem;
        font-weight: 700;
        letter-spacing: .07em;
        text-transform: uppercase;
        padding: .16rem .5rem;
        border-radius: 999px;
        border: 1px solid currentColor;
        margin-bottom: .3rem;
    }
    </style>
    """.replace("__ROOT__", _root())


def missing_vars() -> set[str]:
    """Variáveis citadas no CSS que a paleta não define.

    Existe para o teste: uma `var(--x)` sem valor não dá erro nenhum — o
    navegador descarta a regra em silêncio e o elemento volta ao visual
    nativo do Streamlit, que é justamente o que se está tentando trocar.
    """
    css = _css()
    corpo = css.split("}", 1)[1] if "}" in css else css
    citadas = set(re.findall(r"var\(--([a-z0-9-]+)", corpo))
    definidas = set(_VARS.values()) | {"radius", "radius-sm", "accent"}
    return citadas - definidas


def inject(mode: str = TEMA_PADRAO) -> None:
    """Aplica a paleta do modo e injeta o CSS.

    A troca acontece por variável CSS, e não por tema do Streamlit: o
    tema nativo só é lido na inicialização do processo, então mudar ali
    exigiria reiniciar o app para ver a cor mudar.
    """
    C.use(mode)
    st.markdown(_css(), unsafe_allow_html=True)


# Cada paleta tem de declarar tudo que `_VARS` mapeia; um nome que falta
# num modo vira variável vazia só naquele modo, que é o defeito mais
# difícil de ver — o app fica certo no tema em que você desenvolveu.
def palette_gaps() -> dict[str, set[str]]:
    """{modo: chaves que faltam} — vazio quando as paletas estão completas."""
    exigidas = set(_VARS) | {"SCHEME", "SERIES"}
    return {modo: exigidas - set(cores)
            for modo, cores in PALETTES.items()
            if exigidas - set(cores)}
