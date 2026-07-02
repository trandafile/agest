"""Upload opzionale su Google Drive.

Due modalità alternative (basta configurarne UNA nei Secrets):

① OAuth2 con refresh token (CONSIGLIATA — non richiede chiavi service account,
   utile se l'organizzazione blocca `iam.disableServiceAccountKeyCreation`).
   I file finiscono nel TUO Drive. Ottieni il refresh token una volta sola con
   l'OAuth Playground o `python scripts/gdrive_oauth.py`, poi:
     [gdrive]
     refresh_token   = "1//..."
     folder_estratti = "<id cartella Drive>"
   client_id/client_secret sono riusati dal login (GOOGLE_CLIENT_ID /
   GOOGLE_CLIENT_SECRET); mettili in [gdrive] solo se usi un client diverso.

② Service account (JSON key):
     [gdrive]
     service_account = '''{...json...}'''
     folder_estratti = "<id cartella Drive>"

Restituisce sempre None (senza sollevare) se non configurato o in errore,
così l'app non si rompe mai.
"""

from __future__ import annotations

import json
import os

import streamlit as st

_SCOPE = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _secrets() -> dict:
    try:
        return dict(st.secrets.get("gdrive", {}))
    except Exception:
        return {}


def _get(name: str):
    """Legge un valore da env o st.secrets (piatto o in sezione [app])."""
    v = os.environ.get(name)
    if v:
        return v
    try:
        if name in st.secrets:
            return st.secrets[name]
        return st.secrets.get("app", {}).get(name)
    except Exception:
        return None


def _client_creds(g: dict) -> tuple:
    """client_id/secret: da [gdrive], altrimenti quelli del login Google."""
    cid = g.get("client_id") or _get("GOOGLE_CLIENT_ID")
    csec = g.get("client_secret") or _get("GOOGLE_CLIENT_SECRET")
    return cid, csec


def configurato() -> bool:
    g = _secrets()
    if not g.get("folder_estratti"):
        return False
    cid, csec = _client_creds(g)
    oauth = g.get("refresh_token") and cid and csec
    return bool(oauth or g.get("service_account"))


def _credenziali(g: dict):
    """Costruisce le credenziali: prima OAuth refresh token, poi service account."""
    cid, csec = _client_creds(g)
    if g.get("refresh_token") and cid and csec:
        from google.oauth2.credentials import Credentials

        return Credentials(
            token=None,
            refresh_token=g["refresh_token"],
            token_uri=_TOKEN_URI,
            client_id=cid,
            client_secret=csec,
            scopes=_SCOPE,
        )
    info = g.get("service_account")
    if info:
        from google.oauth2 import service_account

        if isinstance(info, str):
            info = json.loads(info)
        return service_account.Credentials.from_service_account_info(
            info, scopes=_SCOPE
        )
    return None


def salva_su_drive(
    nome: str, contenuto: bytes, mime: str = "application/pdf"
) -> str | None:
    """Carica il file nella cartella Drive configurata; ritorna il link o None."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
    except ModuleNotFoundError:
        return None
    try:
        g = _secrets()
        folder = g.get("folder_estratti")
        creds = _credenziali(g)
        if not folder or creds is None:
            return None
        service = build("drive", "v3", credentials=creds)
        media = MediaInMemoryUpload(contenuto, mimetype=mime or "application/pdf")
        f = (
            service.files()
            .create(
                body={"name": nome, "parents": [folder]},
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        return f.get("webViewLink")
    except Exception:  # noqa: BLE001 — non deve mai rompere l'app
        return None
