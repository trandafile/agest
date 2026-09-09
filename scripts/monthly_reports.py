"""Monthly report schedulato: genera il file .md del mese precedente per i
progetti che lo richiedono e avvisa il responsabile via e-mail (allegato).

Pensato per GitHub Actions (`.github/workflows/monthly-reports.yml`, ogni
giorno: la deduplica è a DB, quindi genera e notifica una sola volta per
progetto/mese) ma eseguibile anche a mano:

    python scripts/monthly_reports.py             # genera (se manca) + notifica
    python scripts/monthly_reports.py --dry-run   # nessuna e-mail

Variabili: DATABASE_URL (Neon), SMTP_* e APP_URL come per send_reminders.py.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:  # pragma: no cover
    pass

from src.data import monthly_repo  # noqa: E402
from src.lib.monthly_pack import assicura_mese_precedente  # noqa: E402
from src.lib.monthly_report import nome_file  # noqa: E402
from src.lib.notifiche import ConfigSMTP  # noqa: E402
from src.lib.notifiche_app import notifica_monthly_pronto  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dry_run = "--dry-run" in sys.argv[1:]
    cfg = ConfigSMTP.da_ambiente()
    if dry_run:
        cfg = ConfigSMTP(app_url=cfg.app_url, attive=False)

    creati = assicura_mese_precedente()
    logging.info("Report generati: %d", len(creati))

    inviati = 0
    for r in monthly_repo.da_notificare():
        etichetta = r["acronimo"] or r["codice"] or r["titolo"]
        if not r.get("email"):
            logging.warning("%s: nessun responsabile con e-mail, salto.", etichetta)
            continue
        ok = notifica_monthly_pronto(
            cfg,
            r["email"],
            r["nome"] or "",
            etichetta,
            r["anno"],
            r["mese"],
            r["contenuto_md"],
            nome_file(r["acronimo"], r["anno"], r["mese"]),
        )
        if ok:
            monthly_repo.segna_notificato(r["id"])
            inviati += 1
        else:
            logging.info(
                "[dry-run/non configurato] %s %d-%02d -> %s",
                etichetta,
                r["anno"],
                r["mese"],
                r["email"],
            )
    logging.info("E-mail inviate: %d", inviati)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
