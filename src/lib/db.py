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
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
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


# ---------------------------------------------------------------------------
# Cache delle letture
# ---------------------------------------------------------------------------
# Ogni clic rieseguiva tutte le query della pagina (decine di round-trip verso
# Neon). Le SELECT passano ora da `st.cache_data`, con chiave
# (epoca, sql, parametri): QUALSIASI scrittura fatta dall'app (`execute`,
# `transaction`) avanza l'epoca e rende vecchie tutte le voci, così dopo una
# modifica si legge sempre il dato aggiornato — anche le tabelle toccate dai
# trigger o dalle cascate. Il TTL copre solo le scritture fatte FUORI
# dall'app (script cron, SQL a mano, altre istanze): al massimo CACHE_TTL
# secondi di ritardo, azzerabili con «Aggiorna dati» nella barra laterale.
# La cache è condivisa fra le sessioni dello stesso processo: la chiave
# contiene la query esatta con i suoi parametri, quindi ognuno ottiene solo i
# risultati delle query che il codice eseguirebbe comunque per lui.
CACHE_TTL = 120
_EPOCA = [time.time_ns()]  # nuova a ogni avvio/ricarica del modulo


def invalida_cache() -> None:
    """Rende vecchie tutte le letture in cache (dopo ogni scrittura)."""
    _EPOCA[0] += 1


def epoca() -> int:
    """Epoca corrente dei dati: cambia a ogni scrittura fatta dall'app."""
    return _EPOCA[0]


@st.cache_data(ttl=CACHE_TTL, max_entries=200, show_spinner=False)
def _file_in_cache(epoca_: int, nome: str, firma: str, _crea: Any) -> bytes:
    out = _crea()
    if hasattr(out, "getvalue"):
        out = out.getvalue()
    return out.encode("utf-8") if isinstance(out, str) else bytes(out)


def file_in_cache(nome: str, firma: Any, crea: Any) -> bytes:
    """Bytes di `crea()` (export, report) ricostruiti solo quando cambiano i
    dati (epoca) o `firma` — non a ogni rerun della pagina."""
    return _file_in_cache(_EPOCA[0], nome, repr(firma), crea)


def _chiave(params: Any) -> str:
    if params is None:
        return "()"
    if isinstance(params, dict):
        return repr(sorted(params.items()))
    return repr(tuple(params))


def _esegui_select(sql: str, params: Sequence[Any] | None) -> list[dict]:
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


@st.cache_data(ttl=CACHE_TTL, max_entries=5000, show_spinner=False)
def _select_in_cache(epoca: int, sql: str, chiave: str, _params: Any) -> list[dict]:
    return _esegui_select(sql, _params)


def query(
    sql: str, params: Sequence[Any] | None = None, cache: bool = True
) -> list[dict]:
    """Esegue una SELECT e ritorna tutte le righe come dict.

    Con `cache=True` (default) il risultato viene dalla cache finché nessuna
    scrittura dell'app la invalida (vedi sopra); `cache=False` legge sempre
    dal database. Le righe restituite sono copie: modificarle non tocca la
    cache.
    """
    if not cache:
        return _esegui_select(sql, params)
    return _select_in_cache(_EPOCA[0], sql, _chiave(params), params)


def query_one(
    sql: str, params: Sequence[Any] | None = None, cache: bool = True
) -> dict | None:
    """Come `query`, ma ritorna la prima riga (o None)."""
    rows = query(sql, params, cache=cache)
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
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            if user_email:
                cur.execute(
                    "select set_config('app.current_email', %s, true)", (user_email,)
                )
            cur.execute(sql, params or ())
            if cur.description is not None:
                return cur.fetchall()
            return []
    finally:
        invalida_cache()  # anche se fallisce: una parte può essere già scritta


@contextmanager
def transaction(user_email: str | None = None) -> Iterator[Any]:
    """Cursore dentro UNA transazione: commit all'uscita, rollback se
    un'eccezione attraversa il blocco (import multi-riga: tutto o niente).

    `user_email` come in `execute` (GUC `app.current_email` per audit/storico).
    """
    try:
        with get_pool().connection() as conn, conn.transaction(), conn.cursor() as cur:
            if user_email:
                cur.execute(
                    "select set_config('app.current_email', %s, true)", (user_email,)
                )
            yield cur
    finally:
        invalida_cache()
