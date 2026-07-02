"""Accesso a PostgreSQL (Neon) via psycopg 3, con connection pool.

Il DSN vive solo nei segreti lato server, mai in UI. Risoluzione:
  1. `st.secrets["database"]["dsn"]`  (Streamlit Cloud e secrets.toml locale)
  2. variabile d'ambiente `DATABASE_URL` (sviluppo locale, caricata da `.env`)
Per il serverless di Neon usare l'endpoint POOLED (host `...-pooler...`).

Helper minimi: `query` / `query_one` (SELECT) e `execute` (INSERT/UPDATE/DELETE,
opzionalmente con RETURNING). Le righe tornano come dict (dict_row).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import streamlit as st
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

try:  # in locale carica .env; in cloud il pacchetto puo' non esserci ed e' ok
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:  # pragma: no cover
    pass


def _resolve_dsn() -> str:
    try:
        dsn = st.secrets["database"]["dsn"]  # type: ignore[index]
        if dsn:
            return dsn
    except Exception:  # nessun secrets.toml / chiave assente: prova l'env
        pass
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    raise RuntimeError(
        "DSN del database mancante: configura [database].dsn nei secrets "
        "oppure DATABASE_URL (.env)."
    )


@st.cache_resource(show_spinner=False)
def get_pool() -> ConnectionPool:
    """Pool condiviso (cache_resource = singleton per processo Streamlit)."""
    return ConnectionPool(
        conninfo=_resolve_dsn(),
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
        check=ConnectionPool.check_connection,  # scarta connessioni morte (Neon idle)
        open=True,
    )


def query(sql: str, params: Sequence[Any] | None = None) -> list[dict]:
    """Esegue una SELECT e ritorna tutte le righe come dict."""
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def query_one(sql: str, params: Sequence[Any] | None = None) -> dict | None:
    """Come `query`, ma ritorna la prima riga (o None)."""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(
    sql: str,
    params: Sequence[Any] | None = None,
    user_email: str | None = None,
) -> list[dict]:
    """Esegue INSERT/UPDATE/DELETE. Con RETURNING ritorna le righe; commit auto.

    `user_email`, se fornita, viene impostata come GUC `app.current_email`
    (SET LOCAL, vale solo per questa transazione): usata dall'audit a DB.
    """
    with get_pool().connection() as conn, conn.cursor() as cur:
        if user_email:
            cur.execute(
                "select set_config('app.current_email', %s, true)", (user_email,)
            )
        cur.execute(sql, params or ())
        if cur.description is not None:
            return cur.fetchall()
        return []
