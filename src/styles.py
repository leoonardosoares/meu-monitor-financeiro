"""CSS injetado no app para um visual consistente e profissional."""
from __future__ import annotations

import streamlit as st

from src.config import Colors

_CSS = f"""
<style>
    /* Tipografia mais clean */
    html, body, [class*="css"] {{
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }}

    /* Botões primários: azul de marca, com hover suave */
    div.stButton > button:first-child {{
        background-color: {Colors.PRIMARY};
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.55rem 1.1rem;
        transition: all 0.2s ease;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }}
    div.stButton > button:first-child:hover {{
        filter: brightness(0.92);
        transform: translateY(-1px);
        box-shadow: 0 4px 10px rgba(15, 23, 42, 0.12);
        color: white;
    }}
    div.stButton > button:first-child:active {{
        transform: translateY(0);
    }}

    /* Botões secundários (form_submit_button etc.) */
    div.stForm button[kind="secondaryFormSubmit"] {{
        background-color: {Colors.PRIMARY} !important;
        color: white !important;
        border: none !important;
    }}

    /* Cards de métrica com leve sombra/borda */
    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
    div[data-testid="stMetricLabel"] {{
        color: {Colors.NEUTRAL};
        font-weight: 500;
    }}
    div[data-testid="stMetricValue"] {{
        font-weight: 700;
        font-size: 1.55rem;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: break-word;
        line-height: 1.2;
    }}
    /* Caixa interna do valor: alguns temas aplicam ellipsis aqui também. */
    div[data-testid="stMetricValue"] > div {{
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }}

    /* Tabs com mais respiro */
    button[data-baseweb="tab"] {{
        font-weight: 600;
    }}

    /* Sidebar com fundo levemente diferente */
    section[data-testid="stSidebar"] {{
        background-color: #F8FAFC;
        border-right: 1px solid #E2E8F0;
    }}

    /* Esconde o menu/footer padrão do Streamlit em produção */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
</style>
"""


def inject() -> None:
    """Aplica o CSS global. Chamar uma vez por rerun, no app.py."""
    st.markdown(_CSS, unsafe_allow_html=True)
