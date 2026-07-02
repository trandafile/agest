"""Ottieni UNA VOLTA SOLA il refresh token per l'upload su Google Drive.

Serve per la modalità OAuth (senza chiavi service account).

Prerequisiti su Google Cloud (progetto antecnica-gestionale):
  1. API «Google Drive» abilitata.
  2. Un OAuth 2.0 Client ID di tipo «Desktop app» (Credenziali → Crea → ID client
     OAuth → Applicazione desktop). Scarica il JSON oppure copiane client_id e
     client_secret.
  3. Nella schermata consenso OAuth, se è «Internal» (Workspace @antecnica.it)
     nessuna verifica serve; aggiungi lo scope .../auth/drive.file.

Uso:
    python scripts/gdrive_oauth.py --client-id XXX --client-secret YYY
oppure con il file scaricato:
    python scripts/gdrive_oauth.py --client-secrets client_secret_xxx.json

Si apre il browser: accedi con luigi.boccia@antecnica.it e acconsenti.
Lo script stampa il blocco [gdrive] da incollare nei Secrets di Streamlit.
"""

from __future__ import annotations

import argparse
import json
import sys

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--client-id")
    ap.add_argument("--client-secret")
    ap.add_argument(
        "--client-secrets", help="Path al JSON scaricato da Google Cloud (Desktop app)"
    )
    args = ap.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ModuleNotFoundError:
        print(
            "Manca google-auth-oauthlib. Installa con:\n"
            "    pip install google-auth-oauthlib",
            file=sys.stderr,
        )
        return 1

    if args.client_secrets:
        flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, SCOPES)
    elif args.client_id and args.client_secret:
        cfg = {
            "installed": {
                "client_id": args.client_id,
                "client_secret": args.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(cfg, SCOPES)
    else:
        print(
            "Fornisci --client-secrets <file.json> "
            "oppure --client-id e --client-secret.",
            file=sys.stderr,
        )
        return 2

    # access_type=offline + prompt=consent -> garantisce il refresh_token
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        print(
            "Nessun refresh token ricevuto. Revoca l'accesso su "
            "https://myaccount.google.com/permissions e riprova.",
            file=sys.stderr,
        )
        return 3

    blocco = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "folder_estratti": "<INCOLLA_QUI_ID_CARTELLA_DRIVE>",
    }
    print("\n✅ Refresh token ottenuto. Incolla questo nei Secrets di Streamlit:\n")
    print("[gdrive]")
    for k, v in blocco.items():
        print(f'{k} = "{v}"')
    print("\n(JSON grezzo, se preferisci:)")
    print(json.dumps(blocco, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
