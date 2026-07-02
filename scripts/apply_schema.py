"""Applica le migrazioni (e opzionalmente il seed) a un DB PostgreSQL (Neon).

Il DDL usa preferibilmente l'endpoint DIRETTO di Neon. DSN, in ordine:
  1. variabile d'ambiente DATABASE_URL_DIRECT (endpoint diretto)
  2. variabile d'ambiente DATABASE_URL
  3. `.streamlit/secrets.toml` -> [database].dsn
Le variabili si caricano anche da `.env` (python-dotenv), se presente.

Uso:
    python scripts/apply_schema.py            # solo migrazioni
    python scripts/apply_schema.py --seed     # migrazioni + seed di sviluppo
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

import psycopg

try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    pass

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "db" / "migrations"
SEED_FILE = ROOT / "db" / "seed.sql"


def get_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.exists():
        data = tomllib.loads(secrets.read_text(encoding="utf-8"))
        try:
            return data["database"]["dsn"]
        except KeyError:
            pass
    raise SystemExit(
        "DSN non trovato. Imposta DATABASE_URL_DIRECT/DATABASE_URL (.env) "
        "oppure compila [database].dsn in .streamlit/secrets.toml"
    )


def main() -> None:
    apply_seed = "--seed" in sys.argv[1:]
    dsn = get_dsn()
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(f"Nessuna migrazione in {MIGRATIONS_DIR}")

    with psycopg.connect(dsn, autocommit=False) as conn:
        for f in files:
            print(f"[migrate] {f.name}")
            conn.execute(f.read_text(encoding="utf-8"))  # multi-statement (no params)
        conn.commit()
        if apply_seed:
            if not SEED_FILE.exists():
                raise SystemExit(f"Seed non trovato: {SEED_FILE}")
            print(f"[seed]    {SEED_FILE.name}")
            conn.execute(SEED_FILE.read_text(encoding="utf-8"))
            conn.commit()

    print("Schema applicato.")


if __name__ == "__main__":
    main()
