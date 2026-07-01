"""Timesheet — placeholder (Fase 2)."""

from __future__ import annotations

import streamlit as st

from src.auth.session import require_login, sidebar_utente

st.set_page_config(page_title="Timesheet — ANTECNICA", page_icon="🗓️", layout="wide")
persona = require_login()
sidebar_utente(persona)

st.title("Timesheet")
st.info("Modulo in arrivo nella **Fase 2** (griglia mensile con regole e CONFERMA).")
