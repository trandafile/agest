"""ANTECNICA Gestionale — entrypoint Streamlit.

Login Google (stile MAIC tasks) + navigation a blocchi con visibilita' per
ruolo (st.navigation). Le pagine mantengono le proprie guardie di ruolo come
difesa aggiuntiva.
"""

from __future__ import annotations

import streamlit as st

from src.auth.session import require_login, sidebar_utente
from src.domain.models import RuoloSistema
from src.lib.labels import versione_app

st.set_page_config(page_title="ANTECNICA Gestionale", page_icon="🗂️", layout="wide")


def main() -> None:
    persona = require_login()

    admin = persona.ruolo_sistema == RuoloSistema.admin
    admin_pm = persona.ruolo_sistema in (RuoloSistema.admin, RuoloSistema.pm)

    dashboard = st.Page(
        "pages/0_Dashboard.py", title="Dashboard", icon="🏠", default=True
    )

    blocco_personale = [
        st.Page("pages/2_Timesheet.py", title="Timesheet", icon="🗓️"),
        st.Page("pages/3_Presenze.py", title="Presenze", icon="⏱️"),
        st.Page("pages/4_Ferie.py", title="Ferie / Permessi", icon="🏖️"),
    ]

    blocco_attivita = [
        st.Page("pages/8_Task.py", title="Task", icon="✅"),
        st.Page("pages/A_Calendario.py", title="Calendario", icon="📅"),
    ]
    if admin_pm:
        blocco_attivita.append(
            st.Page("pages/5_Proposte.py", title="Proposte", icon="📝")
        )

    blocco_gestione: list[st.Page] = []
    if admin_pm:
        blocco_gestione.append(
            st.Page("pages/6_Progetti.py", title="Progetti", icon="📊")
        )
    if admin:
        blocco_gestione.append(
            st.Page("pages/1_Anagrafica.py", title="Anagrafica", icon="👤")
        )

    nav: dict[str, list[st.Page]] = {"": [dashboard]}
    nav["Personale"] = blocco_personale
    nav["Attività"] = blocco_attivita
    if blocco_gestione:
        nav["Gestione"] = blocco_gestione
    if admin:
        nav["Finanza"] = [
            st.Page("pages/7_Finanza.py", title="Finanza", icon="💶"),
            st.Page("pages/9_ImportBanca.py", title="Import banca", icon="🏦"),
        ]

    pagina = st.navigation(nav, position="sidebar", expanded=True)
    sidebar_utente(persona)

    versione = versione_app()
    if versione:
        with st.sidebar:
            st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)
            st.caption(f"versione {versione}")

    pagina.run()


if __name__ == "__main__":
    main()
