"""Import una-tantum del file contabile ANTECNICA (Libro Cassa) su Neon.

Uso:
    python scripts/import_libro_cassa.py "<path .xlsx>" [--clear] [--dry-run]

--clear   svuota prima movimenti bancari/previsti/spese periodiche/log import.
--dry-run analizza e stampa il riepilogo senza scrivere nulla.

Usa la stessa logica della UI (finanza_repo.importa_libro_cassa): crea/aggiorna
i progetti dai fogli per-acronimo, importa calendari (previsti), spese
periodiche e Libri Cassa (movimenti bancari, riconciliati per acronimo).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import finanza_repo  # noqa: E402
from src.lib.import_contabile import leggi_workbook, riepilogo, saldo  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit("Serve il path del file .xlsx")
    path = args[0]
    do_clear = "--clear" in args
    dry = "--dry-run" in args

    sez = leggi_workbook(Path(path).read_bytes())
    print("Riepilogo file:", riepilogo(sez))
    for anno, movs in sorted(sez["libri"].items(), key=lambda x: (x[0] or 0)):
        print(f"  Libro {anno}: {len(movs)} movimenti, saldo {saldo(movs):,.2f} EUR")
    if dry:
        print("[dry-run] nessuna scrittura.")
        return

    esiti = finanza_repo.importa_libro_cassa(
        sez, clear=do_clear, eseguito_da="import-libro-cassa"
    )
    if esiti["clear"]:
        print("Svuotato:", esiti["clear"])
    print(
        f"FATTO: {esiti['movimenti']} movimenti, {esiti['progetti']} progetti, "
        f"{esiti['previsti']} previsti, {esiti['spese_periodiche']} spese periodiche."
    )


if __name__ == "__main__":
    main()
