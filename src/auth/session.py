"""Sessione utente e guardie Streamlit — login Google stile MAIC tasks.

Flusso (come Mtasks/core/auth.py, senza st.login):
- Bottone `st.link_button` verso l'URL di autorizzazione Google (OAuth 2.0).
- Google rimanda all'app (redirect_uri = URL base) con `?code=...`.
- `handle_oauth_callback` scambia il code per il token (requests) e legge
  l'userinfo; niente librerie Google pesanti.
- Solo email `@antecnica.it`; mappatura email -> `persona` per il ruolo.
- Stato in `st.session_state` (perso alla chiusura della scheda: by design).

Segreti (secrets.toml o variabili d'ambiente):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
  [database].dsn, [app].allowed_email_domain.
"""

from __future__ import annotations

import os
import urllib.parse

import requests
import streamlit as st

from src.auth.guards import can_access, is_allowed_email
from src.data.persona_repo import get_persona_by_email
from src.domain.models import Persona, RuoloSistema

_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def get_secret(key: str, default: str | None = None) -> str | None:
    """Legge un segreto da env o st.secrets (piatto o in sezione [app])."""
    val = os.environ.get(key)
    if val is not None:
        return val
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default


def _allowed_domain() -> str:
    try:
        dom = st.secrets.get("app", {}).get("allowed_email_domain")
        if dom:
            return dom
    except Exception:
        pass
    return get_secret("ALLOWED_EMAIL_DOMAIN", "antecnica.it") or "antecnica.it"


def _redirect_uri() -> str:
    return get_secret("GOOGLE_REDIRECT_URI", "http://localhost:8501") or ""


def login_button() -> None:
    """Bottone di login (stile MAIC tasks): link diretto all'auth Google."""
    client_id = get_secret("GOOGLE_CLIENT_ID")
    if not client_id:
        st.warning(
            "⚠️ In attesa delle credenziali Google OAuth "
            "(GOOGLE_CLIENT_ID nei secrets)."
        )
        # Fallback di sviluppo finche' i secrets non sono compilati.
        mock_email = st.text_input(
            "Mock Login (Dev)", placeholder="luigi.boccia@antecnica.it"
        )
        if st.button("Simula Login (MOCK)", type="primary") and mock_email:
            _process_login(mock_email)
        return

    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account",
        "access_type": "online",
    }
    auth_url = _AUTH_URL + "?" + urllib.parse.urlencode(params)
    st.link_button("🔑 Accedi con Google", auth_url, type="primary")


def handle_oauth_callback() -> None:
    """Gestisce il ritorno da Google (`?code=...`) e apre la sessione."""
    if "code" not in st.query_params:
        return
    code = st.query_params["code"]
    del st.query_params["code"]

    client_id = get_secret("GOOGLE_CLIENT_ID")
    client_secret = get_secret("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return
    try:
        tok = requests.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        tok.raise_for_status()
        access_token = tok.json()["access_token"]
        info = requests.get(
            _USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        info.raise_for_status()
        email = info.json().get("email")
        if email:
            _process_login(email)
        else:
            st.error("Impossibile leggere l'email dall'account Google.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Errore durante l'autenticazione Google: {exc}")


def _process_login(email: str) -> None:
    """Valida dominio e anagrafica, poi apre la sessione."""
    email = email.strip().lower()
    if not is_allowed_email(email, _allowed_domain()):
        st.session_state["_login_error"] = (
            f"Accesso consentito solo agli account @{_allowed_domain()}."
        )
        st.rerun()
    persona = get_persona_by_email(email)
    if persona is None:
        st.session_state["_login_error"] = (
            "Utente non presente in anagrafica. Contatta l'amministratore."
        )
        st.rerun()
    if not persona.attivo:
        st.session_state["_login_error"] = (
            "Utente disattivato. Contatta l'amministratore."
        )
        st.rerun()
    st.session_state["logged_in"] = True
    st.session_state["user_email"] = email
    st.session_state["_persona"] = persona
    st.session_state.pop("_login_error", None)
    st.rerun()


def current_persona() -> Persona | None:
    """`Persona` autenticata in sessione, o None."""
    if not st.session_state.get("logged_in"):
        return None
    p = st.session_state.get("_persona")
    return p if isinstance(p, Persona) else None


def require_login() -> Persona:
    """Blocca la pagina se non autenticato. Ritorna la `Persona`."""
    persona = current_persona()
    if persona is not None:
        return persona

    handle_oauth_callback()
    persona = current_persona()
    if persona is not None:
        return persona

    st.title("ANTECNICA Gestionale")
    err = st.session_state.pop("_login_error", None)
    if err:
        st.error(err)
    st.info("Accedi con il tuo account Google aziendale @antecnica.it.")
    login_button()
    st.stop()
    raise RuntimeError("unreachable")  # per il type checker


def require_role(*roles: RuoloSistema) -> Persona:
    """Come `require_login` + verifica che il ruolo sia tra quelli richiesti."""
    persona = require_login()
    if not can_access(persona.ruolo_sistema, roles):
        st.error("Accesso negato: non hai i permessi per questa pagina.")
        st.stop()
    return persona


def logout() -> None:
    """Chiude la sessione."""
    for k in ("logged_in", "user_email", "_persona", "_login_error"):
        st.session_state.pop(k, None)
    st.rerun()


def sidebar_utente(persona: Persona) -> None:
    """Riquadro utente + logout nella sidebar."""
    with st.sidebar:
        st.caption(f"{persona.nome_completo}")
        st.caption(f"Ruolo: {persona.ruolo_sistema.value}")
        if st.button("Esci", use_container_width=True):
            logout()
