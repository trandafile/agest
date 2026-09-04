"""Invio headless dei reminder task (briefing settimanale + scaduti ieri).

Pensato per GitHub Actions (`.github/workflows/task-reminders.yml`) ma
eseguibile anche a mano:

    python scripts/send_reminders.py            # solo lunedì manda il briefing
    python scripts/send_reminders.py --forza    # briefing anche oggi (dedup ISO week)
    python scripts/send_reminders.py --dry-run  # nessun invio, solo log

Variabili: DATABASE_URL (Neon), SMTP_HOST/PORT/USER/PASSWORD/FROM, APP_URL,
NOTIFICHE_ATTIVE. In locale si caricano da `.env`.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:  # pragma: no cover
    pass

from src.lib.notifiche import ConfigSMTP, esegui_reminder  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = set(sys.argv[1:])
    dsn = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL")
    if not dsn:
        logging.error("DATABASE_URL mancante.")
        return 1
    cfg = ConfigSMTP.da_ambiente()
    if "--dry-run" in args:
        cfg = ConfigSMTP(app_url=cfg.app_url, attive=False)
    if not cfg.configurato:
        logging.warning("SMTP non configurato: esecuzione in dry-run (nessun invio).")
    with psycopg.connect(dsn, autocommit=False) as conn:
        esito = esegui_reminder(conn, cfg, solo_lunedi="--forza" not in args)
    logging.info("Esito: %s", esito)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
