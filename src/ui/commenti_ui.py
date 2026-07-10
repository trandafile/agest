"""Blocco commenti riusabile su qualunque modulo (stile MAIC tasks).

Uso tipico dentro un dialog o una pagina:

    from src.ui.commenti_ui import blocco_commenti
    blocco_commenti("task", task.id, persona, is_admin, nomi)
"""

from __future__ import annotations

import streamlit as st

from src.data import commento_repo
from src.domain.models import Persona


def _quando(c) -> str:
    if not c.created_at:
        return ""
    txt = f"{c.created_at:%d/%m/%Y %H:%M}"
    return f"{txt} · modificato" if c.modificato else txt


def blocco_commenti(
    entita: str,
    entita_id,
    persona: Persona,
    is_admin: bool = False,
    nomi: dict | None = None,
    titolo: str = "💬 Commenti",
) -> None:
    """Elenco commenti + form di inserimento; l'autore (o admin) può modificare.

    `nomi` è la mappa {persona_id: nome_completo} già caricata dalla pagina.
    """
    nomi = nomi or {}
    commenti = commento_repo.list_commenti(entita, entita_id)
    st.markdown(f"**{titolo}** ({len(commenti)})")

    if not commenti:
        st.caption("Nessun commento. Scrivine uno qui sotto.")

    for c in commenti:
        autore = nomi.get(c.autore_id, "—")
        mio = c.autore_id == persona.id
        with st.container(border=True):
            st.markdown(
                f"<small>👤 **{autore}** · {_quando(c)}</small>",
                unsafe_allow_html=True,
            )
            key = f"edit_{entita}_{c.id}"
            if st.session_state.get(key):
                nuovo = st.text_area(
                    "Modifica",
                    value=c.testo,
                    key=f"txt_{c.id}",
                    label_visibility="collapsed",
                )
                e1, e2 = st.columns(2)
                if e1.button("💾 Salva", key=f"save_{c.id}", use_container_width=True):
                    if nuovo.strip():
                        commento_repo.update_commento(c.id, nuovo)
                        st.session_state[key] = False
                        st.rerun()
                    else:
                        st.error("Il commento non può essere vuoto.")
                if e2.button("Annulla", key=f"undo_{c.id}", use_container_width=True):
                    st.session_state[key] = False
                    st.rerun()
            else:
                st.markdown(c.testo)
                if mio or is_admin:
                    a1, a2, _ = st.columns([1, 1, 6])
                    if a1.button("✏️", key=f"e_{c.id}", help="Modifica"):
                        st.session_state[key] = True
                        st.rerun()
                    if a2.button("🗑", key=f"d_{c.id}", help="Elimina"):
                        commento_repo.delete_commento(c.id)
                        st.rerun()

    with st.form(f"nuovo_commento_{entita}_{entita_id}", clear_on_submit=True):
        testo = st.text_area("Scrivi un commento", label_visibility="collapsed")
        if st.form_submit_button("💬 Commenta", type="primary"):
            if testo.strip():
                commento_repo.add_commento(entita, entita_id, testo, persona.id)
                st.rerun()
            else:
                st.error("Scrivi qualcosa prima di inviare.")


def badge_commenti(n: int) -> str:
    """Chip da appendere alle righe di elenco: '' se non ci sono commenti."""
    return f" · 💬 {n}" if n else ""
