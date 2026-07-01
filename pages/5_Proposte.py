"""Proposte — placeholder (Fase 3). Vista economica: admin/pm."""

from __future__ import annotations

import streamlit as st

from src.auth.session import require_role, sidebar_utente
from src.domain.models import RuoloSistema

st.set_page_config(page_title="Proposte — ANTECNICA", page_icon="📝", layout="wide")
persona = require_role(RuoloSistema.admin, RuoloSistema.pm)
sidebar_utente(persona)

st.title("Proposte")
st.info("Modulo in arrivo nella **Fase 3** (pianificazione ore/costi, pipeline).")
