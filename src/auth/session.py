"""Sessione utente e guardie Streamlit (Opzione A: OIDC nativo Streamlit).

Flusso:
- `st.login()` avvia l'OIDC Google; `st.user` espone email/nome/is_logged_in.
- Consentiamo solo email `@antecnica.it` (oltre alla consent screen Internal).
- Mappiamo l'email -> `persona` per ottenere `ruolo_sistema`.
- `require_login()` / `require_role(...)` proteggono ogni pagina.
"""

from __future__ import annotations

import streamlit as st

from src.auth.guards import can_access, is_allowed_email
from src.data.persona_repo import get_persona_by_email
from src.domain.models import Persona, RuoloSistema


def _allowed_domain() -> str:
    return st.secrets.get("app", {}).get("allowed_email_domain", "antecnica.it")


def current_email() -> str | None:
    """Email dell'utente loggato, o None se non autenticato."""
    user = getattr(st, "user", None)
    if user is None or not getattr(user, "is_logged_in", False):
        return None
    return getattr(user, "email", None)


def current_persona() -> Persona | None:
    """`Persona` corrispondente all'utente loggato (cache in sessione)."""
    email = current_email()
    if not email:
        return None
    cached = st.session_state.get("_persona")
    if isinstance(cached, Persona) and cached.email == email.lower():
        return cached
    persona = get_persona_by_email(email)
    st.session_state["_persona"] = persona
    return persona


def require_login() -> Persona:
    """Blocca la pagina se non loggato / dominio non valido / non anagrafato.

    Ritorna la `Persona` autenticata.
    """
    email = current_email()
    if not email:
        st.title("ANTECNICA Gestionale")
        st.info("Accedi con il tuo account Google aziendale @antecnica.it.")
        st.button("Accedi con Google", type="primary", on_click=st.login)
        st.stop()

    if not is_allowed_email(email, _allowed_domain()):
        st.error("Accesso consentito solo agli account @antecnica.it.")
        st.button("Esci", on_click=st.logout)
        st.stop()

    persona = current_persona()
    if persona is None:
        st.error(
            "Utente non presente in anagrafica. Contatta l'amministratore per "
            "essere aggiunto come persona."
        )
        st.button("Esci", on_click=st.logout)
        st.stop()

    if not persona.attivo:
        st.error("Utente disattivato. Contatta l'amministratore.")
        st.button("Esci", on_click=st.logout)
        st.stop()

    return persona


def require_role(*roles: RuoloSistema) -> Persona:
    """Come `require_login` + verifica che il ruolo sia tra quelli richiesti."""
    persona = require_login()
    if not can_access(persona.ruolo_sistema, roles):
        st.error("Accesso negato: non hai i permessi per questa pagina.")
        st.stop()
    return persona


def sidebar_utente(persona: Persona) -> None:
    """Riquadro utente + logout nella sidebar."""
    with st.sidebar:
        st.caption(f"{persona.nome_completo}")
        st.caption(f"Ruolo: {persona.ruolo_sistema.value}")
        st.button("Esci", on_click=st.logout, use_container_width=True)
