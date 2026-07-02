"""Presenze — registrazione ingresso/uscita e ore giornaliere."""

from __future__ import annotations

from datetime import date, time

import pandas as pd
import streamlit as st

from src.auth.session import require_login, sidebar_utente
from src.data import persona_repo, presenze_repo
from src.domain.models import RuoloSistema

st.set_page_config(page_title="Presenze — ANTECNICA", page_icon="⏱️", layout="wide")
persona = require_login()
sidebar_utente(persona)

st.title("Presenze")

oggi = date.today()
c1, c2, c3 = st.columns([2, 1, 1])
if persona.ruolo_sistema == RuoloSistema.admin:
    persone = persona_repo.list_persone(solo_attivi=True)
elif persona.ruolo_sistema == RuoloSistema.pm:
    # il pm vede sé stesso + le persone assegnate alle sue iniziative (§3)
    assegnate = persona_repo.list_persone_assegnate_a_pm(persona.id)
    persone = [persona] + [p for p in assegnate if p.id != persona.id]
else:
    persone = []

if persone:
    sel = c1.selectbox(
        "Persona",
        options=persone,
        index=next((i for i, p in enumerate(persone) if p.id == persona.id), 0),
        format_func=lambda p: p.nome_completo,
    )
else:
    sel = persona
    c1.markdown(f"**Persona:** {persona.nome_completo}")
anno = c2.selectbox("Anno", options=range(oggi.year - 2, oggi.year + 2), index=2)
mese = c3.selectbox(
    "Mese",
    options=range(1, 13),
    index=oggi.month - 1,
    format_func=lambda m: f"{m:02d}",
)

puo_scrivere = sel.id == persona.id or persona.ruolo_sistema == RuoloSistema.admin

# --- Nuova presenza ---------------------------------------------------------
if puo_scrivere:
    with st.expander("➕ Registra presenza", expanded=False):
        with st.form("nuova_presenza", clear_on_submit=True):
            f1, f2, f3, f4 = st.columns(4)
            giorno = f1.date_input("Giorno", value=oggi)
            ingresso = f2.time_input("Ingresso", value=time(9, 0))
            uscita = f3.time_input("Uscita", value=time(18, 0))
            tipo = f4.selectbox("Tipo", ["ufficio", "remoto", "trasferta"])
            note = st.text_input("Note (opzionale)")
            if st.form_submit_button("Registra", type="primary"):
                try:
                    presenze_repo.registra_presenza(
                        sel.id, giorno, ingresso, uscita, tipo, note or None
                    )
                    st.success("Presenza registrata.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Errore: {exc}")

# --- Elenco mese -------------------------------------------------------------
presenze = presenze_repo.list_presenze(sel.id, anno, mese)
if not presenze:
    st.info("Nessuna presenza registrata in questo mese.")
else:
    df = pd.DataFrame(
        [
            {
                "Giorno": f"{p.data:%d/%m/%Y}",
                "Ingresso": p.ora_ingresso.strftime("%H:%M") if p.ora_ingresso else "",
                "Uscita": p.ora_uscita.strftime("%H:%M") if p.ora_uscita else "",
                "Ore": float(p.ore_totali) if p.ore_totali is not None else None,
                "Tipo": p.tipo,
                "Note": p.note or "",
            }
            for p in presenze
        ]
    )
    st.dataframe(df, hide_index=True, use_container_width=True)
    tot = sum(float(p.ore_totali or 0) for p in presenze)
    st.caption(f"Totale ore mese: **{tot:g} h** su {len(presenze)} registrazioni")

    if puo_scrivere:
        da_canc = st.selectbox(
            "Elimina registrazione",
            options=[None] + presenze,
            format_func=lambda p: (
                "—"
                if p is None
                else f"{p.data:%d/%m} {p.tipo} "
                f"({p.ora_ingresso or ''}-{p.ora_uscita or ''})"
            ),
        )
        if da_canc is not None and st.button("Elimina", type="secondary"):
            presenze_repo.delete_presenza(da_canc.id)
            st.rerun()
