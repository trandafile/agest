"""Accesso a PostgreSQL (Neon) via psycopg 3, con connection pool.

Il DSN vive solo in `.streamlit/secrets.toml` lato server, mai in UI.
Per il serverless di Neon usare l'endpoint POOLED (host `...-pooler...`).

Helper minimi: `query` / `query_one` (SELECT) e `execute` (INSERT/UPDATE/DELETE,
opzionalmente con RETURNING). Le righe tornano come dict (dict_row).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


@st.cache_resource(show_spinner=False)
def get_pool() -> ConnectionPool:
    """Pool condiviso (cache_resource = singleton per processo Streamlit)."""
    dsn = st.secrets["database"]["dsn"]
    return ConnectionPool(
        conninfo=dsn,
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


def execute(sql: str, params: Sequence[Any] | None = None) -> list[dict]:
    """Esegue INSERT/UPDATE/DELETE. Con RETURNING ritorna le righe; commit auto."""
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        if cur.description is not None:
            return cur.fetchall()
        return []
