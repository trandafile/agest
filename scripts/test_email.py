"""Prova la configurazione SMTP inviando UNA e-mail di test.

    python scripts/test_email.py tuo.nome@antecnica.it

Legge la configurazione come l'app: sezione `[smtp]` di
`.streamlit/secrets.toml` (o chiavi SMTP_* al primo livello), altrimenti le
variabili d'ambiente / `.env`. Stampa cosa ha trovato (senza la password) e
l'esito dell'invio. Non tocca il database.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:  # pragma: no cover
    pass

from src.lib.notifiche import invia  # noqa: E402
from src.lib.notifiche_app import config_smtp  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2 or "@" not in sys.argv[1]:
        print("Uso: python scripts/test_email.py destinatario@antecnica.it")
        return 2
    destinatario = sys.argv[1]
    cfg = config_smtp()
    print(
        f"host={cfg.host or '(vuoto)'} port={cfg.port} user={cfg.user or '(vuoto)'} "
        f"from={cfg.mittente or '(vuoto)'} password={'impostata' if cfg.password else 'MANCANTE'} "
        f"attive={cfg.attive}"
    )
    if not cfg.configurato:
        print("SMTP non configurato: compila [smtp] nei secrets o le variabili SMTP_*.")
        return 1
    quando = f"{datetime.now():%d/%m/%Y %H:%M}"
    try:
        invia(
            cfg,
            destinatario,
            "[ANTECNICA] Prova SMTP",
            f"<p>Configurazione SMTP di ANTECNICA Gestionale funzionante ({quando}).</p>",
            f"Configurazione SMTP di ANTECNICA Gestionale funzionante ({quando}).",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE di invio: {type(exc).__name__}: {exc}")
        print(
            "Con Gmail/Workspace: usa smtp.gmail.com porta 587, l'indirizzo completo "
            "come user e una PASSWORD PER LE APP (non quella normale)."
        )
        return 1
    print(f"E-mail di prova inviata a {destinatario}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
