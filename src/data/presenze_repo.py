"""Accesso dati per presenze, assenze e calendario festivita'."""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from src.domain.models import Assenza, Festivita, Presenza
from src.lib import db

# --- Presenze -----------------------------------------------------------


def list_presenze(persona_id: UUID | str, anno: int, mese: int) -> list[Presenza]:
    rows = db.query(
        """
        select * from presenza
        where persona_id = %s
          and extract(year from data)::int = %s
          and extract(month from data)::int = %s
        order by data, ora_ingresso
        """,
        (str(persona_id), anno, mese),
    )
    return [Presenza.model_validate(r) for r in rows]


def registra_presenza(
    persona_id: UUID | str,
    giorno: date,
    ora_ingresso: time | None,
    ora_uscita: time | None,
    tipo: str = "ufficio",
    note: str | None = None,
) -> Presenza:
    ore = None
    if ora_ingresso and ora_uscita:
        delta = (
            ora_uscita.hour * 60
            + ora_uscita.minute
            - ora_ingresso.hour * 60
            - ora_ingresso.minute
        )
        ore = round(max(delta, 0) / 60, 2)
    row = db.execute(
        """
        insert into presenza
            (persona_id, data, ora_ingresso, ora_uscita, ore_totali, tipo, note)
        values (%s, %s, %s, %s, %s, %s, %s)
        returning *
        """,
        (str(persona_id), giorno, ora_ingresso, ora_uscita, ore, tipo, note),
    )[0]
    return Presenza.model_validate(row)


def delete_presenza(presenza_id: UUID | str) -> None:
    db.execute("delete from presenza where id = %s", (str(presenza_id),))


# --- Assenze (ferie/permessi/malattia) -----------------------------------


def list_assenze(
    persona_id: UUID | str | None = None, solo_richieste: bool = False
) -> list[Assenza]:
    sql = "select * from assenza"
    cond, params = [], []
    if persona_id:
        cond.append("persona_id = %s")
        params.append(str(persona_id))
    if solo_richieste:
        cond.append("stato = 'richiesta'")
    if cond:
        sql += " where " + " and ".join(cond)
    sql += " order by data_inizio desc"
    return [Assenza.model_validate(r) for r in db.query(sql, params)]


def richiedi_assenza(
    persona_id: UUID | str,
    tipo: str,
    data_inizio: date,
    data_fine: date,
    ore_o_giorni: float | None = None,
    note: str | None = None,
) -> Assenza:
    row = db.execute(
        """
        insert into assenza
            (persona_id, tipo, data_inizio, data_fine, ore_o_giorni, note)
        values (%s, %s, %s, %s, %s, %s)
        returning *
        """,
        (str(persona_id), tipo, data_inizio, data_fine, ore_o_giorni, note),
    )[0]
    return Assenza.model_validate(row)


def decidi_assenza(
    assenza_id: UUID | str,
    approva: bool,
    approvatore_id: UUID | str,
    eseguito_da: str | None = None,
) -> Assenza:
    row = db.execute(
        """
        update assenza
           set stato = %s, approvato_da = %s
         where id = %s
        returning *
        """,
        (
            "approvata" if approva else "rifiutata",
            str(approvatore_id),
            str(assenza_id),
        ),
        user_email=eseguito_da,
    )[0]
    return Assenza.model_validate(row)


# --- Festivita' -----------------------------------------------------------


def list_festivita(anno: int | None = None) -> list[Festivita]:
    if anno:
        rows = db.query(
            "select * from calendario_festivita "
            "where extract(year from data)::int = %s order by data",
            (anno,),
        )
    else:
        rows = db.query("select * from calendario_festivita order by data")
    return [Festivita.model_validate(r) for r in rows]


def festivita_set(anno: int) -> set[date]:
    return {f.data for f in list_festivita(anno)}


def add_festivita(giorno: date, descrizione: str) -> None:
    db.execute(
        """
        insert into calendario_festivita (data, descrizione)
        values (%s, %s) on conflict (data) do nothing
        """,
        (giorno, descrizione),
    )


def delete_festivita(festivita_id: UUID | str) -> None:
    db.execute("delete from calendario_festivita where id = %s", (str(festivita_id),))
