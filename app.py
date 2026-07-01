"""ANTECNICA Gestionale — entrypoint Streamlit (Fase 1).

Home dopo il login. Le singole pagine sono in /pages e ciascuna applica la
propria guardia di ruolo (src/auth). La sidebar multipage e' nativa Streamlit.
"""

from __future__ import annotations

import streamlit as st

from src.auth.session import require_login, sidebar_utente
from src.domain.models import RuoloSistema

st.set_page_config(page_title="ANTECNICA Gestionale", page_icon="🗂️", layout="wide")


def main() -> None:
    persona = require_login()
    sidebar_utente(persona)

    st.title("ANTECNICA Gestionale")
    st.write(f"Ciao **{persona.nome}**, benvenuto/a.")

    st.subheader("Moduli")
    if persona.ruolo_sistema == RuoloSistema.admin:
        st.markdown(
            "- **Anagrafica personale** — gestione persone e tariffe (admin)\n"
            "- *Timesheet, Presenze, Ferie* — in arrivo (Fase 2)\n"
            "- *Proposte, Progetti* — in arrivo (Fase 3)\n"
            "- *Finanza* — in arrivo (Fase 4)"
        )
    else:
        st.markdown(
            "- *Timesheet, Presenze, Ferie* — in arrivo (Fase 2)\n\n"
            "Usa il menu a sinistra per navigare tra le pagine disponibili."
        )

    st.info(
        "Fase 1 (Fondamenta) attiva: autenticazione, ruoli, anagrafica personale "
        "e tariffe versionate.",
        icon="✅",
    )


if __name__ == "__main__":
    main()
