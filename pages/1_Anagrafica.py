"""Anagrafica personale — CRUD persona + tariffe versionate. SOLO admin."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.auth.session import require_role, sidebar_utente
from src.data import persona_repo, tariffa_repo
from src.domain.models import RuoloSistema
from src.ui.tables import persone_dataframe, tariffe_dataframe

st.set_page_config(page_title="Anagrafica — ANTECNICA", page_icon="👤", layout="wide")

persona = require_role(RuoloSistema.admin)
sidebar_utente(persona)

st.title("Anagrafica personale")
st.caption("Gestione persone e tariffe orarie versionate — riservata all'admin.")

# --- Elenco persone -----------------------------------------------------
persone = persona_repo.list_persone()
st.subheader("Persone")
if persone:
    st.dataframe(persone_dataframe(persone), hide_index=True, use_container_width=True)
else:
    st.info("Nessuna persona in anagrafica.")

# --- Nuova persona ------------------------------------------------------
with st.expander("➕ Nuova persona"):
    with st.form("nuova_persona", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome")
        cognome = c2.text_input("Cognome")
        c3, c4 = st.columns(2)
        email = c3.text_input("Email (@antecnica.it)")
        matricola = c4.text_input("Matricola (opzionale)")
        ruolo = st.selectbox(
            "Ruolo", options=list(RuoloSistema), format_func=lambda r: r.value
        )
        if st.form_submit_button("Crea persona", type="primary"):
            if not (nome and cognome and email):
                st.error("Nome, cognome ed email sono obbligatori.")
            else:
                try:
                    persona_repo.create_persona(
                        nome=nome,
                        cognome=cognome,
                        email=email,
                        ruolo_sistema=ruolo,
                        matricola=matricola or None,
                    )
                    st.success(f"Persona {nome} {cognome} creata.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Errore nella creazione: {exc}")

st.divider()

# --- Dettaglio persona: modifica + tariffe ------------------------------
if persone:
    st.subheader("Dettaglio persona e tariffe")
    sel = st.selectbox(
        "Seleziona una persona",
        options=persone,
        format_func=lambda p: f"{p.nome_completo} — {p.email}",
    )

    tab_dati, tab_tariffe = st.tabs(["Dati anagrafici", "Tariffe orarie"])

    with tab_dati:
        with st.form("modifica_persona"):
            c1, c2 = st.columns(2)
            m_nome = c1.text_input("Nome", value=sel.nome)
            m_cognome = c2.text_input("Cognome", value=sel.cognome)
            c3, c4 = st.columns(2)
            m_matricola = c3.text_input("Matricola", value=sel.matricola or "")
            m_attivo = c4.checkbox("Attivo", value=sel.attivo)
            m_ruolo = st.selectbox(
                "Ruolo",
                options=list(RuoloSistema),
                index=list(RuoloSistema).index(sel.ruolo_sistema),
                format_func=lambda r: r.value,
            )
            col_a, col_b = st.columns([1, 1])
            if col_a.form_submit_button("Salva modifiche", type="primary"):
                try:
                    persona_repo.update_persona(
                        sel.id,
                        nome=m_nome,
                        cognome=m_cognome,
                        matricola=m_matricola or None,
                        attivo=m_attivo,
                        ruolo_sistema=m_ruolo,
                    )
                    st.success("Modifiche salvate.")
                    st.session_state.pop("_persona", None)
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Errore: {exc}")
            if col_b.form_submit_button("Elimina persona"):
                try:
                    persona_repo.delete_persona(sel.id)
                    st.success("Persona eliminata.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Errore: {exc}")

    with tab_tariffe:
        tariffe = tariffa_repo.list_tariffe(sel.id)
        if tariffe:
            st.dataframe(
                tariffe_dataframe(tariffe),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("Nessuna tariffa per questa persona.")

        st.markdown("**Nuova tariffa** (i periodi non possono sovrapporsi)")
        with st.form("nuova_tariffa", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            t_da = c1.date_input("Valido da", value=date.today())
            aperto = c2.checkbox("Periodo aperto", value=True)
            t_al = c2.date_input("Valido al", value=date.today(), disabled=aperto)
            t_imp = c3.number_input("€/ora", min_value=0.0, step=0.5, format="%.2f")
            if st.form_submit_button("Aggiungi tariffa", type="primary"):
                try:
                    tariffa_repo.create_tariffa(
                        persona_id=sel.id,
                        valido_da=t_da,
                        valido_al=None if aperto else t_al,
                        importo_orario=t_imp,
                    )
                    st.success("Tariffa aggiunta.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Errore (periodi sovrapposti o dati non validi): {exc}")
