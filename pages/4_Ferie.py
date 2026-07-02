"""Ferie / Permessi — richiesta del dipendente + approvazione admin/pm."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_login, sidebar_utente
from src.data import persona_repo, presenze_repo
from src.domain.models import RuoloSistema

st.set_page_config(page_title="Ferie — ANTECNICA", page_icon="🏖️", layout="wide")
persona = require_login()
sidebar_utente(persona)

st.title("Ferie / Permessi")

STATO_ICONA = {"richiesta": "⏳", "approvata": "✅", "rifiutata": "⛔"}

# --- Nuova richiesta ---------------------------------------------------------
with st.expander("➕ Nuova richiesta", expanded=False):
    with st.form("nuova_assenza", clear_on_submit=True):
        f1, f2, f3, f4 = st.columns(4)
        tipo = f1.selectbox("Tipo", ["ferie", "permesso", "malattia"])
        inizio = f2.date_input("Dal", value=date.today())
        fine = f3.date_input("Al", value=date.today())
        ore_g = f4.number_input(
            "Ore o giorni (opz.)", min_value=0.0, step=0.5, value=0.0
        )
        note = st.text_input("Note (opzionale)")
        if st.form_submit_button("Invia richiesta", type="primary"):
            if fine < inizio:
                st.error("La data di fine precede quella di inizio.")
            else:
                presenze_repo.richiedi_assenza(
                    persona.id,
                    tipo,
                    inizio,
                    fine,
                    ore_o_giorni=ore_g or None,
                    note=note or None,
                )
                st.success("Richiesta inviata.")
                st.rerun()

# --- Le mie richieste ----------------------------------------------------------
st.subheader("Le mie richieste")
mie = presenze_repo.list_assenze(persona.id)
if mie:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Tipo": a.tipo,
                    "Dal": f"{a.data_inizio:%d/%m/%Y}",
                    "Al": f"{a.data_fine:%d/%m/%Y}",
                    "Ore/giorni": float(a.ore_o_giorni) if a.ore_o_giorni else None,
                    "Stato": f"{STATO_ICONA[a.stato]} {a.stato}",
                    "Note": a.note or "",
                }
                for a in mie
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("Nessuna richiesta.")

# --- Approvazioni (admin/pm) ----------------------------------------------------
if persona.ruolo_sistema in (RuoloSistema.admin, RuoloSistema.pm):
    st.divider()
    st.subheader("Richieste da approvare")
    pendenti = [
        a
        for a in presenze_repo.list_assenze(solo_richieste=True)
        if a.persona_id != persona.id
    ]
    if persona.ruolo_sistema == RuoloSistema.pm:
        # il pm approva solo le richieste delle persone assegnate (§3)
        ammesse = {p.id for p in persona_repo.list_persone_assegnate_a_pm(persona.id)}
        pendenti = [a for a in pendenti if a.persona_id in ammesse]
    if not pendenti:
        st.info("Nessuna richiesta in attesa.")
    else:
        nomi = {p.id: p.nome_completo for p in persona_repo.list_persone()}
        for a in pendenti:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(
                    f"**{nomi.get(a.persona_id, '?')}** — {a.tipo} "
                    f"dal {a.data_inizio:%d/%m/%Y} al {a.data_fine:%d/%m/%Y}"
                    + (f" ({a.ore_o_giorni:g} ore/gg)" if a.ore_o_giorni else "")
                    + (f" — _{a.note}_" if a.note else "")
                )
                if c2.button("✅ Approva", key=f"ok_{a.id}"):
                    presenze_repo.decidi_assenza(
                        a.id,
                        True,
                        persona.id,
                        eseguito_da=st.session_state.get("user_email"),
                    )
                    st.rerun()
                if c3.button("⛔ Rifiuta", key=f"no_{a.id}"):
                    presenze_repo.decidi_assenza(
                        a.id,
                        False,
                        persona.id,
                        eseguito_da=st.session_state.get("user_email"),
                    )
                    st.rerun()
