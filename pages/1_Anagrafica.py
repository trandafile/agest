"""Anagrafica personale — CRUD persona + tariffe versionate. SOLO admin."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.auth.session import require_role
from src.data import persona_repo, tariffa_repo
from src.domain.models import TIPO_CONTRATTO_LABEL, RuoloSistema, TipoContratto
from src.lib.labels import getf
from src.ui.tables import persone_dataframe, tariffe_dataframe

persona = require_role(RuoloSistema.admin)

_CONTRATTI = [None] + list(TipoContratto)


def _fmt_contratto(t) -> str:
    return "—" if t is None else TIPO_CONTRATTO_LABEL[t.value]


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
        st.markdown("**Contratto**")
        k1, k2, k3 = st.columns(3)
        n_tipo = k1.selectbox("Tipologia", _CONTRATTI, format_func=_fmt_contratto)
        n_inizio = k2.date_input("Data inizio", value=None)
        n_fine = k3.date_input("Data fine (solo tempo determinato)", value=None)
        if st.form_submit_button("Crea persona", type="primary"):
            if not (nome and cognome and email):
                st.error("Nome, cognome ed email sono obbligatori.")
            elif n_tipo == TipoContratto.tempo_determinato and not (
                n_inizio and n_fine
            ):
                st.error("Tempo determinato: servono data inizio e data fine.")
            else:
                try:
                    fine = n_fine if n_tipo == TipoContratto.tempo_determinato else None
                    persona_repo.create_persona(
                        nome=nome,
                        cognome=cognome,
                        email=email,
                        ruolo_sistema=ruolo,
                        matricola=matricola or None,
                        tipo_contratto=n_tipo,
                        contratto_data_inizio=n_inizio,
                        contratto_data_fine=fine,
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
            c5, c6 = st.columns(2)
            m_cf = c5.text_input(
                "Codice fiscale", value=getf(sel, "codice_fiscale") or ""
            )
            m_monte = c6.number_input(
                "Monte ore annuo",
                min_value=0,
                step=10,
                value=int(getf(sel, "monte_ore_annuo", 1720) or 1720),
            )
            m_ruolo = st.selectbox(
                "Ruolo",
                options=list(RuoloSistema),
                index=list(RuoloSistema).index(sel.ruolo_sistema),
                format_func=lambda r: r.value,
            )
            st.markdown("**Contratto**")
            k1, k2, k3 = st.columns(3)
            idx_c = (
                _CONTRATTI.index(getf(sel, "tipo_contratto"))
                if getf(sel, "tipo_contratto") in _CONTRATTI
                else 0
            )
            m_tipo = k1.selectbox(
                "Tipologia", _CONTRATTI, index=idx_c, format_func=_fmt_contratto
            )
            m_inizio = k2.date_input(
                "Data inizio", value=getf(sel, "contratto_data_inizio")
            )
            m_fine = k3.date_input(
                "Data fine (solo tempo determinato)",
                value=getf(sel, "contratto_data_fine"),
            )
            if st.form_submit_button("Salva modifiche", type="primary"):
                if m_tipo == TipoContratto.tempo_determinato and not (
                    m_inizio and m_fine
                ):
                    st.error("Tempo determinato: servono data inizio e data fine.")
                else:
                    fine = m_fine if m_tipo == TipoContratto.tempo_determinato else None
                    try:
                        persona_repo.update_persona(
                            sel.id,
                            nome=m_nome,
                            cognome=m_cognome,
                            matricola=m_matricola or None,
                            attivo=m_attivo,
                            ruolo_sistema=m_ruolo,
                            codice_fiscale=m_cf or None,
                            monte_ore_annuo=m_monte or None,
                            tipo_contratto=m_tipo,
                            contratto_data_inizio=m_inizio,
                            contratto_data_fine=fine,
                        )
                        st.success("Modifiche salvate.")
                        st.session_state.pop("_persona", None)
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Errore: {exc}")

        # --- Zona pericolosa: eliminazione persona --------------------------
        st.divider()
        with st.expander("🗑️ Elimina persona (definitivo)"):
            if sel.id == persona.id:
                st.warning("Non puoi eliminare il tuo account.")
            else:
                dip = persona_repo.riepilogo_dipendenze(sel.id)
                st.markdown(
                    f"Eliminando **{sel.nome_completo}** verranno rimossi anche i "
                    "suoi dati collegati:"
                )
                st.markdown(
                    f"- {dip['tariffe']} tariffe · {dip['assegnazioni']} assegnazioni\n"
                    f"- {dip['ore_timesheet']} righe timesheet "
                    f"({dip['mesi_confermati']} mesi **confermati**)\n"
                    f"- {dip['presenze']} presenze · {dip['assenze']} assenze"
                )
                if dip["progetti_responsabile"] or dip["task"]:
                    st.info(
                        f"Su {dip['progetti_responsabile']} progetti (come "
                        f"responsabile) e {dip['task']} task il riferimento verrà "
                        "azzerato, non cancellato."
                    )
                if dip["mesi_confermati"]:
                    st.warning(
                        "⚠️ Ci sono mesi di timesheet CONFERMATI (dati di "
                        "rendicontazione). Valuta invece di **disattivare** la "
                        "persona (togli la spunta «Attivo» e salva)."
                    )
                conferma = st.checkbox(
                    f"Confermo l'eliminazione definitiva di {sel.nome_completo}"
                )
                if st.button(
                    "Elimina definitivamente",
                    type="primary",
                    disabled=not conferma,
                ):
                    try:
                        persona_repo.elimina_persona(
                            sel.id, eseguito_da=st.session_state.get("user_email")
                        )
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
