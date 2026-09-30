"""CSS global do tema escuro.

O alvo é o visual de app financeiro: fundo quase preto, cartões com
contorno discreto, rótulo pequeno em maiúscula e o número grande como
protagonista. Verde para o que é seu, vermelho para o que você deve.

Cuidado ao mexer: o bloco de Material Symbols não é decorativo. Sem ele
o Streamlit perde a fonte de ícones e os chevrons de expander viram as
palavras "arrow_right" na tela.
"""
from __future__ import annotations

import streamlit as st

from src.config import Colors as C, TEMA_PADRAO


def _css() -> str:
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {{
        --bg: {C.BG};
        --surface: {C.SURFACE};
        --surface-2: {C.SURFACE_2};
        --border: {C.BORDER};
        --text: {C.TEXT};
        --muted: {C.TEXT_MUTED};
        --faint: {C.TEXT_FAINT};
        --green: {C.PRIMARY};
        --green-hover: {C.PRIMARY_HOVER};
        --red: {C.EXPENSE};
        --amber: {C.WARNING};
        --sidebar: {C.SIDEBAR};
        --on-primary: {C.ON_PRIMARY};
        --radius: 14px;
    }}

    /* Diz ao navegador qual é o esquema, para scrollbar, seleção de
       texto e controles nativos seguirem o tema em vez de ficarem
       escuros num app claro. */
    :root {{ color-scheme: {"dark" if C.BG == "#0D1117" else "light"}; }}

    html, body, .stApp {{
        font-family: 'Inter', 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
        background: var(--bg);
        color: var(--text);
    }}

    /* A fonte de ícones do Streamlit precisa sobreviver à troca global de
       família acima; sem isto os ícones viram texto literal. */
    [class*="material-symbols"], [class*="material-icons"],
    .material-symbols-outlined, .material-symbols-rounded, .material-icons,
    [data-testid="stIconMaterial"], [data-testid="stExpanderIcon"],
    [data-testid="stExpanderToggleIcon"],
    button[data-testid="stBaseButton-headerNoPadding"] span {{
        font-family: 'Material Symbols Outlined', 'Material Symbols Rounded',
                     'Material Icons', sans-serif !important;
        font-feature-settings: 'liga' !important;
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24 !important;
    }}

    h1, h2, h3, h4 {{
        color: var(--text);
        font-weight: 700;
        letter-spacing: -0.02em;
    }}
    h1 {{ font-size: 1.9rem; }}
    h2 {{ font-size: 1.35rem; }}
    h3 {{ font-size: 1.1rem; }}

    /* A barra do topo e a decoração são do Streamlit e seguem o tema
       nativo, que é fixo. Sem forçar aqui, elas ficam pretas num app
       claro — foi o que deixou o topo escuro no modo claro. */
    .stApp > header, [data-testid="stHeader"] {{
        background: var(--bg) !important;
    }}
    [data-testid="stHeader"] * {{ color: var(--muted) !important; }}
    [data-testid="stDecoration"] {{ display: none; }}
    [data-testid="stToolbar"] {{ background: transparent !important; }}
    .block-container {{ padding-top: 2.2rem; max-width: 1240px; }}

    /* ── Métrica como cartão ────────────────────────────────────────────
       É o elemento mais repetido do app; tratá-lo como cartão é o que dá
       o ar de painel financeiro sem precisar de HTML próprio em cada tela. */
    [data-testid="stMetric"] {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.1rem 1.25rem;
        transition: border-color .18s ease, transform .18s ease;
    }}
    [data-testid="stMetric"]:hover {{
        border-color: #36424F;
        transform: translateY(-2px);
    }}
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {{
        color: var(--faint) !important;
        font-size: .72rem !important;
        font-weight: 600 !important;
        letter-spacing: .08em;
        text-transform: uppercase;
    }}
    [data-testid="stMetricValue"] {{
        color: var(--text) !important;
        /* Encolhe conforme a coluna aperta: cinco métricas lado a lado
           cortavam o valor, e um saldo pela metade é pior que feio. */
        font-size: clamp(1.05rem, 2.1vw, 1.75rem) !important;
        font-weight: 700 !important;
        letter-spacing: -.02em;
        /* O valor precisa caber inteiro: um saldo truncado é pior que feio. */
        white-space: normal !important;
        overflow: visible !important;
    }}
    /* O delta é uma pilha cinza sobre cinza no tema nativo; sem cor
       própria ele fica ilegível nos dois modos. */
    [data-testid="stMetricDelta"] {{
        font-size: .76rem !important;
        font-weight: 600 !important;
        color: var(--muted) !important;
    }}
    [data-testid="stMetricDelta"] svg {{ fill: currentColor !important; }}

    /* ── Contêineres com borda viram cartão ── */
    [data-testid="stVerticalBlockBorderWrapper"] > div:has(> [data-testid="stVerticalBlock"]) {{
        background: var(--surface);
        border-radius: var(--radius);
    }}

    /* ── Botões ── */
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
        border-radius: 10px;
        border: 1px solid var(--border);
        background: var(--surface-2);
        color: var(--text);
        font-weight: 600;
        padding: .5rem 1.1rem;
        transition: all .18s ease;
    }}
    .stButton > button:hover, .stFormSubmitButton > button:hover {{
        border-color: var(--green);
        color: var(--green);
        transform: translateY(-1px);
    }}
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
        background: var(--green);
        border-color: var(--green);
        color: var(--on-primary);
    }}
    .stButton > button[kind="primary"]:hover {{
        background: var(--green-hover);
        border-color: var(--green-hover);
        color: var(--on-primary);
        box-shadow: 0 6px 18px rgba(82,191,144,.22);
    }}

    /* ── Campos ──────────────────────────────────────────────────────
       Os widgets vêm do BaseWeb e seguem o tema nativo do Streamlit,
       que é lido na inicialização e não muda. Sem forçar cada peça, o
       seletor de período aparecia como uma caixa preta num app claro. */
    [data-baseweb="select"] > div,
    [data-baseweb="select"] div[role="button"],
    [data-baseweb="input"], [data-baseweb="base-input"],
    [data-baseweb="textarea"], [data-baseweb="datepicker"] input {{
        background: var(--surface-2) !important;
        border-color: var(--border) !important;
        color: var(--text) !important;
    }}
    [data-baseweb="select"] *, [data-baseweb="input"] * {{
        color: var(--text) !important;
    }}
    [data-baseweb="select"] svg {{ fill: var(--muted) !important; }}
    /* A lista que abre é renderizada fora da árvore do componente. */
    [data-baseweb="popover"] [role="listbox"],
    [data-baseweb="menu"], [data-baseweb="calendar"] {{
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
    }}
    [role="option"], [data-baseweb="menu"] li {{
        background: var(--surface) !important;
        color: var(--text) !important;
    }}
    [role="option"]:hover, [data-baseweb="menu"] li:hover {{
        background: var(--surface-2) !important;
    }}
    [data-baseweb="tag"] {{
        background: var(--primary-soft) !important;
        color: var(--text) !important;
    }}

    /* ── Campos ── */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    .stSelectbox [data-baseweb="select"] > div, .stTextArea textarea {{
        background: var(--surface-2) !important;
        border-color: var(--border) !important;
        color: var(--text) !important;
        border-radius: 10px !important;
    }}

    /* ── Abas ── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: .35rem;
        border-bottom: 1px solid var(--border);
    }}
    .stTabs [data-baseweb="tab"] {{
        color: var(--muted);
        font-weight: 600;
        padding: .55rem .95rem;
    }}
    .stTabs [aria-selected="true"] {{ color: var(--green) !important; }}

    /* ── Expander ── */
    [data-testid="stExpander"] {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
    }}
    [data-testid="stExpander"] summary {{ color: var(--text); font-weight: 600; }}

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {{
        background: var(--sidebar);
        border-right: 1px solid var(--border);
    }}
    /* O texto da sidebar não herdava a cor do tema e sumia no claro. */
[data-testid="stSidebar"] *:not([class*="material"]):not([data-testid="stIconMaterial"]) {{
    color: var(--text);
}}
[data-testid="stSidebar"] label p,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
    color: var(--muted) !important;
}}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ color: var(--text) !important; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
    color: var(--faint) !important;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] label {{
        padding: .45rem .7rem;
        border-radius: 9px;
        transition: background .15s ease, color .15s ease;
    }}
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
        background: var(--surface-2);
        color: var(--green);
    }}

    /* ── Tabelas ── */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
        border: 1px solid var(--border);
        border-radius: var(--radius);
        overflow: hidden;
    }}

    /* ── Avisos ── */
    [data-testid="stAlert"] {{
    border-radius: 12px;
    border: 1px solid var(--border);
}}
[data-testid="stAlert"] p, [data-testid="stAlert"] li {{
    color: var(--text) !important;
}}
/* Legenda e texto auxiliar precisam de cor própria: o padrão do
   Streamlit é calculado a partir do tema nativo, que está fixo. */
[data-testid="stCaptionContainer"] p {{ color: var(--muted) !important; }}
.stMarkdown p, .stMarkdown li {{ color: var(--text); }}
code {{
    background: var(--surface-2) !important;
    color: var(--green) !important;
    border-radius: 5px;
    padding: .1rem .35rem;
}}

    /* ── Cartão de conta (HTML próprio, ver components.account_rows) ── */
    .mf-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.15rem 1.25rem;
    }}
    .mf-card__label {{
        color: var(--faint);
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .09em;
        text-transform: uppercase;
        margin-bottom: .4rem;
    }}
    .mf-card__value {{
        font-size: 1.9rem;
        font-weight: 700;
        letter-spacing: -.02em;
        margin-bottom: .2rem;
    }}
    .mf-pos {{ color: var(--green); }}
    .mf-neg {{ color: var(--red); }}
    .mf-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: .75rem;
        padding: .65rem 0;
        border-top: 1px solid var(--border);
    }}
    .mf-row__name {{ font-weight: 600; font-size: .93rem; }}
    .mf-row__sub {{ color: var(--faint); font-size: .76rem; }}
    .mf-row__val {{ font-weight: 700; font-size: .95rem; white-space: nowrap; }}
    .mf-bar {{
        height: 6px;
        border-radius: 999px;
        background: var(--surface-2);
        overflow: hidden;
        margin: .45rem 0 .1rem;
    }}
    .mf-bar > span {{ display: block; height: 100%; border-radius: 999px; }}
    </style>
    """


def inject(mode: str = TEMA_PADRAO) -> None:
    """Aplica a paleta do modo e injeta o CSS.

    A troca acontece por variável CSS, e não por tema do Streamlit: o
    tema nativo só é lido na inicialização do processo, então mudar ali
    exigiria reiniciar o app para ver a cor mudar.
    """
    C.use(mode)
    st.markdown(_css(), unsafe_allow_html=True)
