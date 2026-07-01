"""Finanza — placeholder (Fase 4). SOLO admin."""

from __future__ import annotations

import streamlit as st

from src.auth.session import require_role, sidebar_utente
from src.domain.models import RuoloSistema

st.set_page_config(page_title="Finanza — ANTECNICA", page_icon="💶", layout="wide")
persona = require_role(RuoloSistema.admin)
sidebar_utente(persona)

st.title("Finanza")
st.info("Modulo in arrivo nella **Fase 4** (import, riconciliazione, reporting).")
