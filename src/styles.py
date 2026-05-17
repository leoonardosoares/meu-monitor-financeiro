"""CSS global injetado no app para um visual consistente e profissional."""
from __future__ import annotations

import streamlit as st

from src.config import Colors


_CSS = f"""
<style>
    /* ────── Tipografia ────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
    }}
    h1, h2, h3 {{
        font-weight: 700;
        letter-spacing: -0.02em;
    }}
    h1 {{ font-size: 1.9rem; }}
    h2 {{ font-size: 1.4rem; }}
    h3 {{ font-size: 1.15rem; }}

    /* ────── Espaçamento da página ────── */
    section.main > div.block-container {{
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }}

    /* ────── Botões ────── */
    div.stButton > button:first-child,
    div.stForm button[kind="secondaryFormSubmit"],
    div.stForm button[kind="primaryFormSubmit"] {{
        background-color: {Colors.PRIMARY} !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.55rem 1.1rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }}
    div.stButton > button:first-child:hover,
    div.stForm button[kind="secondaryFormSubmit"]:hover,
    div.stForm button[kind="primaryFormSubmit"]:hover {{
        filter: brightness(0.93);
        transform: translateY(-1px);
        box-shadow: 0 4px 10px rgba(15, 23, 42, 0.12);
    }}
    div.stButton > button:first-child:active {{
        transform: translateY(0);
    }}

    /* ────── Cards de métrica ────── */
    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        transition: box-shadow 0.2s ease;
    }}
    div[data-testid="stMetric"]:hover {{
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
    }}
    div[data-testid="stMetricLabel"] {{
        color: {Colors.NEUTRAL};
        font-weight: 500;
        text-transform: uppercase;
        font-size: 0.72rem;
        letter-spacing: 0.04em;
    }}
    div[data-testid="stMetricValue"] {{
        font-weight: 700;
        font-size: 1.55rem;
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

    /* ────── Tabs ────── */
    div[data-baseweb="tab-list"] {{
        gap: 1rem;
        border-bottom: 1px solid #E2E8F0;
    }}
    button[data-baseweb="tab"] {{
        font-weight: 600;
        font-size: 0.95rem;
    }}

    /* ────── Tabelas / data editor ────── */
    div[data-testid="stDataFrame"] table tbody tr:nth-child(even),
    div[data-testid="stDataEditor"] table tbody tr:nth-child(even) {{
        background: rgba(241, 245, 249, 0.5);
    }}
    div[data-testid="stDataFrame"] table tbody tr:hover,
    div[data-testid="stDataEditor"] table tbody tr:hover {{
        background: rgba(37, 99, 235, 0.05);
    }}

    /* ────── Sidebar ────── */
    section[data-testid="stSidebar"] {{
        background-color: #F8FAFC;
        border-right: 1px solid #E2E8F0;
    }}
    section[data-testid="stSidebar"] h3 {{
        font-size: 1rem;
        color: #1E293B;
    }}

    /* ────── Containers com borda ────── */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 12px !important;
        border-color: #E2E8F0 !important;
    }}

    /* ────── Inputs ────── */
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div {{
        border-radius: 8px;
    }}

    /* ────── Esconde menu/footer padrão ────── */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}

    /* ────── Insight callouts: mais discretos ────── */
    div[data-baseweb="notification"] {{
        border-radius: 10px;
        padding: 0.7rem 1rem;
    }}
</style>
"""


def inject() -> None:
    """Aplica o CSS global. Chamar uma vez por rerun, no app.py."""
    st.markdown(_CSS, unsafe_allow_html=True)
