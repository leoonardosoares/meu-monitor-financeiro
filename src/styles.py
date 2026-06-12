"""CSS global injetado no app para um visual consistente e profissional."""
from __future__ import annotations

import streamlit as st

from src.config import Colors


_CSS = f"""
<style>
    /* ────── Tipografia ────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], [class*="st-"], [class*="stApp"] {{
        font-family: 'Inter', 'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }}
    h1, h2, h3 {{
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #0F172A;
    }}
    h1 {{ font-size: 1.95rem; }}
    h2 {{ font-size: 1.4rem; }}
    h3 {{ font-size: 1.15rem; }}

    /* ────── Background da página (gradiente sutil verde-creme) ────── */
    .stApp {{
        background:
            radial-gradient(ellipse at 80% 0%, rgba(82, 191, 144, 0.08), transparent 50%),
            radial-gradient(ellipse at 0% 100%, rgba(49, 114, 86, 0.05), transparent 50%),
            #FAFCFB !important;
    }}

    /* ────── Espaçamento do container principal ────── */
    section.main > div.block-container,
    [data-testid="stMainBlockContainer"] {{
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        max-width: 1400px !important;
    }}

    /* ────────────────────────────────────────────────────────────
       BOTÕES — gradiente verde, hover com lift, todos os testids
       ──────────────────────────────────────────────────────────── */
    .stButton > button,
    .stDownloadButton > button,
    [data-testid="stBaseButton-secondary"],
    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stBaseButton-primaryFormSubmit"],
    [data-testid="stFormSubmitButton"] button,
    div[data-testid="stForm"] button,
    button[kind="primary"],
    button[kind="secondary"],
    button[kind="secondaryFormSubmit"],
    button[kind="primaryFormSubmit"] {{
        background: linear-gradient(180deg, {Colors.PRIMARY_HOVER} 0%, {Colors.PRIMARY} 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(49, 114, 86, 0.35) !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em !important;
        padding: 0.62rem 1.3rem !important;
        transition: transform 0.18s cubic-bezier(0.2, 0.8, 0.2, 1),
                    box-shadow 0.18s cubic-bezier(0.2, 0.8, 0.2, 1),
                    background 0.18s ease,
                    filter 0.18s ease !important;
        box-shadow:
            0 1px 2px rgba(49, 114, 86, 0.22),
            inset 0 1px 0 rgba(255, 255, 255, 0.20) !important;
    }}
    .stButton > button:hover,
    .stDownloadButton > button:hover,
    [data-testid="stBaseButton-secondary"]:hover,
    [data-testid="stBaseButton-primary"]:hover,
    [data-testid="stBaseButton-secondaryFormSubmit"]:hover,
    [data-testid="stBaseButton-primaryFormSubmit"]:hover,
    [data-testid="stFormSubmitButton"] button:hover,
    div[data-testid="stForm"] button:hover,
    button[kind="primary"]:hover,
    button[kind="secondary"]:hover,
    button[kind="secondaryFormSubmit"]:hover,
    button[kind="primaryFormSubmit"]:hover {{
        background: linear-gradient(180deg, {Colors.INCOME} 0%, {Colors.PRIMARY_HOVER} 100%) !important;
        color: #FFFFFF !important;
        transform: translateY(-1px);
        box-shadow:
            0 8px 18px rgba(49, 114, 86, 0.32),
            inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
    }}
    .stButton > button:active,
    [data-testid="stBaseButton-secondary"]:active,
    [data-testid="stBaseButton-primary"]:active,
    [data-testid="stFormSubmitButton"] button:active,
    div[data-testid="stForm"] button:active {{
        transform: translateY(0);
        background: linear-gradient(180deg, {Colors.PRIMARY} 0%, #2A624A 100%) !important;
        box-shadow:
            0 1px 2px rgba(49, 114, 86, 0.18),
            inset 0 2px 4px rgba(0, 0, 0, 0.12) !important;
    }}
    .stButton > button:focus-visible,
    [data-testid="stBaseButton-secondary"]:focus-visible,
    [data-testid="stBaseButton-primary"]:focus-visible {{
        outline: 2px solid {Colors.PRIMARY_SOFT};
        outline-offset: 2px;
    }}

    /* ────────────────────────────────────────────────────────────
       SIDEBAR — gradiente verde + nav cards
       ──────────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"],
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #F0F8F3 0%, #E6F2EC 100%) !important;
        border-right: 1px solid rgba(49, 114, 86, 0.18) !important;
        box-shadow: inset -1px 0 0 rgba(49, 114, 86, 0.04);
    }}
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{
        color: {Colors.PRIMARY} !important;
        font-weight: 700;
    }}
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    section[data-testid="stSidebar"] small {{
        color: {Colors.NEUTRAL};
    }}
    section[data-testid="stSidebar"] hr {{
        border-color: rgba(49, 114, 86, 0.15) !important;
        margin: 0.7rem 0 !important;
    }}

    /* Nav cards — estiliza os radio buttons da sidebar como menu */
    section[data-testid="stSidebar"] div[role="radiogroup"] {{
        gap: 0.35rem;
        display: flex;
        flex-direction: column;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] label {{
        background: rgba(255, 255, 255, 0.65);
        border: 1px solid rgba(49, 114, 86, 0.12);
        border-radius: 10px;
        padding: 0.7rem 0.85rem !important;
        cursor: pointer;
        transition: all 0.16s cubic-bezier(0.2, 0.8, 0.2, 1);
        margin: 0 !important;
        font-weight: 500;
        color: #0F172A;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
        background: rgba(82, 191, 144, 0.12);
        border-color: rgba(49, 114, 86, 0.25);
        transform: translateX(2px);
    }}
    /* Esconde o círculo do radio */
    section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {{
        display: none;
    }}
    /* Item ativo (radio checado) — verde forte */
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
        background: linear-gradient(135deg, {Colors.PRIMARY_HOVER} 0%, {Colors.PRIMARY} 100%) !important;
        border-color: {Colors.PRIMARY} !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 12px rgba(49, 114, 86, 0.28);
        font-weight: 600;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) * {{
        color: #FFFFFF !important;
    }}

    /* Botão "Sair" da sidebar fica branco com borda verde, contraste */
    section[data-testid="stSidebar"] .stButton > button {{
        background: rgba(255, 255, 255, 0.85) !important;
        color: {Colors.PRIMARY} !important;
        border: 1px solid rgba(49, 114, 86, 0.3) !important;
    }}
    section[data-testid="stSidebar"] .stButton > button:hover {{
        background: linear-gradient(180deg, {Colors.PRIMARY_HOVER} 0%, {Colors.PRIMARY} 100%) !important;
        color: #FFFFFF !important;
        border-color: {Colors.PRIMARY} !important;
    }}

    /* Selectbox da sidebar com bordinha verde sutil */
    section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
        border-color: rgba(49, 114, 86, 0.25) !important;
        background: rgba(255, 255, 255, 0.85) !important;
        border-radius: 9px !important;
    }}

    /* ────────────────────────────────────────────────────────────
       CARDS DE MÉTRICA — borda verde sutil, hover elevado
       ──────────────────────────────────────────────────────────── */
    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid rgba(49, 114, 86, 0.12);
        border-left: 3px solid {Colors.PRIMARY};
        border-radius: 12px;
        padding: 1rem 1.1rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        transition: all 0.22s ease;
    }}
    div[data-testid="stMetric"]:hover {{
        box-shadow: 0 8px 22px rgba(49, 114, 86, 0.10);
        transform: translateY(-1px);
        border-left-color: {Colors.INCOME};
    }}
    div[data-testid="stMetricLabel"] {{
        color: {Colors.NEUTRAL};
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.72rem;
        letter-spacing: 0.05em;
    }}
    div[data-testid="stMetricValue"] {{
        font-weight: 700;
        font-size: 1.55rem;
        color: #0F172A;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: break-word;
        line-height: 1.2;
        margin-top: 0.25rem;
    }}
    div[data-testid="stMetricValue"] > div {{
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }}
    div[data-testid="stMetricDelta"] {{
        font-size: 0.85rem;
        font-weight: 500;
    }}

    /* ────────────────────────────────────────────────────────────
       TABS — destaque verde no ativo
       ──────────────────────────────────────────────────────────── */
    div[data-baseweb="tab-list"] {{
        gap: 1.2rem;
        border-bottom: 1px solid rgba(49, 114, 86, 0.15);
    }}
    button[data-baseweb="tab"] {{
        font-weight: 600;
        font-size: 0.95rem;
        color: {Colors.NEUTRAL};
        transition: color 0.18s ease;
    }}
    button[data-baseweb="tab"]:hover {{
        color: {Colors.PRIMARY};
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {Colors.PRIMARY} !important;
    }}
    div[data-baseweb="tab-highlight"] {{
        background-color: {Colors.PRIMARY} !important;
        height: 3px !important;
        border-radius: 3px 3px 0 0 !important;
    }}

    /* ────────────────────────────────────────────────────────────
       TABELAS / data editor — hover verde
       ──────────────────────────────────────────────────────────── */
    div[data-testid="stDataFrame"] table tbody tr:nth-child(even),
    div[data-testid="stDataEditor"] table tbody tr:nth-child(even) {{
        background: rgba(240, 248, 243, 0.5);
    }}
    div[data-testid="stDataFrame"] table tbody tr:hover,
    div[data-testid="stDataEditor"] table tbody tr:hover {{
        background: rgba(82, 191, 144, 0.12);
    }}

    /* ────────────────────────────────────────────────────────────
       EXPANDERS / CONTAINERS COM BORDA — accent verde
       ──────────────────────────────────────────────────────────── */
    div[data-testid="stExpander"] {{
        border: 1px solid rgba(49, 114, 86, 0.15) !important;
        border-radius: 10px !important;
        background: #FFFFFF;
        transition: border-color 0.18s ease, box-shadow 0.18s ease;
    }}
    div[data-testid="stExpander"]:hover {{
        border-color: rgba(49, 114, 86, 0.35) !important;
        box-shadow: 0 4px 12px rgba(49, 114, 86, 0.08);
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 12px !important;
        border-color: rgba(49, 114, 86, 0.15) !important;
    }}

    /* ────────────────────────────────────────────────────────────
       INPUTS — radius padronizado
       ──────────────────────────────────────────────────────────── */
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    div[data-baseweb="textarea"] > div {{
        border-radius: 8px !important;
    }}
    div[data-baseweb="input"]:focus-within > div,
    div[data-baseweb="select"]:focus-within > div {{
        border-color: {Colors.PRIMARY} !important;
        box-shadow: 0 0 0 3px rgba(82, 191, 144, 0.18);
    }}

    /* ────────────────────────────────────────────────────────────
       PROGRESS BAR — verde tema
       ──────────────────────────────────────────────────────────── */
    div[data-testid="stProgress"] > div > div > div > div {{
        background: linear-gradient(90deg, {Colors.PRIMARY_SOFT} 0%, {Colors.PRIMARY} 100%) !important;
    }}

    /* ────────────────────────────────────────────────────────────
       ALERTS / NOTIFICATIONS — bordas arredondadas
       ──────────────────────────────────────────────────────────── */
    div[data-baseweb="notification"],
    div[data-testid="stAlert"] {{
        border-radius: 10px !important;
        padding: 0.75rem 1rem !important;
    }}

    /* ────────────────────────────────────────────────────────────
       ESCONDE menu/footer/header padrão do Streamlit
       ──────────────────────────────────────────────────────────── */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    header[data-testid="stHeader"] {{
        background: transparent !important;
    }}
</style>
"""


def inject() -> None:
    """Aplica o CSS global. Chamar uma vez por rerun, no app.py."""
    st.markdown(_CSS, unsafe_allow_html=True)
