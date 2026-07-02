"""Accesso dati per timesheet (mese, ore) e assegnazioni attive."""

from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from src.domain.models import TimesheetOra
from src.domain.timesheet import AssegnazioneInfo
from src.lib import db


def assegnazioni_attive(
    persona_id: UUID | str, anno: int, mese: int
) -> list[AssegnazioneInfo]:
    """Assegnazioni della persona valide nel mese (righe della griglia).

    Solo iniziative di tipo 'progetto' non chiuse o proposte approvate:
    a timesheet si registrano ore su progetti reali.
    """
    primo = date(anno, mese, 1)
    ultimo = date(anno + 1, 1, 1) if mese == 12 else date(anno, mese + 1, 1)
    rows = db.query(
        """
        select a.id, a.tipo_attivita, a.tetto_ore_mese,
               i.titolo, i.data_inizio, i.data_fine, i.ore_totali
        from assegnazione a
        join iniziativa i on i.id = a.iniziativa_id
        where a.persona_id = %s
          and i.tipo = 'progetto' and i.stato = 'attivo'
          and (i.data_inizio is null or i.data_inizio < %s)
          and (i.data_fine  is null or i.data_fine  >= %s)
        order by i.titolo, a.tipo_attivita
        """,
        (str(persona_id), ultimo, primo),
    )
    return [
        AssegnazioneInfo(
            id=str(r["id"]),
            titolo=r["titolo"],
            tipo_attivita=r["tipo_attivita"],
            tetto_ore_mese=(
                float(r["tetto_ore_mese"]) if r["tetto_ore_mese"] is not None else None
            ),
            data_inizio=r["data_inizio"],
            data_fine=r["data_fine"],
            ore_totali_iniziativa=(
                float(r["ore_totali"]) if r["ore_totali"] is not None else None
            ),
        )
        for r in rows
    ]


def ore_mese(persona_id: UUID | str, anno: int, mese: int) -> list[TimesheetOra]:
    rows = db.query(
        """
        select id, persona_id, assegnazione_id, data, ore, forzato
        from timesheet_ora
        where persona_id = %s
          and extract(year from data)::int = %s
          and extract(month from data)::int = %s
        order by data
        """,
        (str(persona_id), anno, mese),
    )
    return [TimesheetOra.model_validate(r) for r in rows]


def ore_mese_dettaglio(persona_id: UUID | str, anno: int, mese: int) -> list[dict]:
    """Ore del mese con iniziativa e tipo attivita' (per l'export XLSX)."""
    return db.query(
        """
        select t.data, t.ore, a.tipo_attivita, a.iniziativa_id,
               i.titolo, i.cup, i.tipo_progetto_desc
        from timesheet_ora t
        join assegnazione a on a.id = t.assegnazione_id
        join iniziativa i on i.id = a.iniziativa_id
        where t.persona_id = %s
          and extract(year from t.data)::int = %s
          and extract(month from t.data)::int = %s
        order by t.data
        """,
        (str(persona_id), anno, mese),
    )


def stato_mese(persona_id: UUID | str, anno: int, mese: int) -> str:
    row = db.query_one(
        """
        select stato from timesheet_mese
        where persona_id = %s and anno = %s and mese = %s
        """,
        (str(persona_id), anno, mese),
    )
    return row["stato"] if row else "bozza"


def ore_annuali(persona_id: UUID | str, anno: int) -> int:
    """Contatore annuale di ore progettuali (testata griglia)."""
    row = db.query_one(
        """
        select coalesce(sum(ore), 0) as tot
        from timesheet_ora
        where persona_id = %s and extract(year from data)::int = %s
        """,
        (str(persona_id), anno),
    )
    return int(row["tot"]) if row else 0


def conferma_mese(
    persona_id: UUID | str,
    anno: int,
    mese: int,
    righe: list[dict],
    eseguito_da: str | None = None,
) -> None:
    """Salva e blocca il mese in un'unica transazione (funzione DB).

    `righe`: [{"assegnazione_id","data" iso,"ore","forzato"}].
    Le regole del §5 sono rivalidate dai trigger: un errore annulla tutto.
    """
    db.execute(
        "select conferma_timesheet(%s, %s, %s, %s::jsonb)",
        (str(persona_id), anno, mese, json.dumps(righe)),
        user_email=eseguito_da,
    )


def riapri_mese(
    persona_id: UUID | str, anno: int, mese: int, eseguito_da: str | None = None
) -> None:
    """Riapre un mese confermato (solo admin, guardia applicativa). Audit a DB."""
    db.execute(
        "select riapri_timesheet(%s, %s, %s)",
        (str(persona_id), anno, mese),
        user_email=eseguito_da,
    )
