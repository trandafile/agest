"""Storico dei cambi di stato dei task (v3): alimenta il report «cosa è
cambiato» (come il meeting deck di MAIC tasks) e i briefing."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from src.lib import db


def cambiamenti(giorni: int = 30) -> list[dict]:
    """Cambi di stato negli ultimi `giorni` giorni, con titolo task/progetto."""
    return db.query(
        """
        select s.task_id, s.stato_prec, s.stato_nuovo, s.cambiato_da, s.cambiato_il,
               t.titolo, t.owner_id, i.acronimo, i.titolo as progetto
        from task_storico s
        join task t on t.id = s.task_id
        left join iniziativa i on i.id = t.iniziativa_id
        where s.cambiato_il >= now() - make_interval(days => %s)
        order by s.cambiato_il desc
        """,
        (giorni,),
    )


def contatori(giorni: int = 30) -> dict[str, int]:
    """Completati / avviati / bloccati / creati nel periodo (task distinti)."""
    row = db.query_one(
        """
        select count(distinct task_id) filter (where stato_nuovo = 'completato')
                   as completati,
               count(distinct task_id) filter (where stato_nuovo = 'in_corso')
                   as avviati,
               count(distinct task_id) filter (where stato_nuovo = 'bloccato')
                   as bloccati,
               count(distinct task_id) filter (where stato_prec is null) as creati
        from task_storico
        where cambiato_il >= now() - make_interval(days => %s)
        """,
        (giorni,),
    )
    return {
        k: int(row[k] or 0) for k in ("completati", "avviati", "bloccati", "creati")
    }


def storico_task(task_id: UUID | str) -> list[dict]:
    return db.query(
        "select stato_prec, stato_nuovo, cambiato_da, cambiato_il from task_storico "
        "where task_id = %s order by cambiato_il",
        (str(task_id),),
    )


def ultimo_aggiornamento_per_task() -> dict[str, date]:
    """{task_id: data ultimo cambio di stato} — per la «staleness» (giorni
    senza aggiornamenti), come My Week di MAIC tasks."""
    rows = db.query(
        "select task_id, max(cambiato_il)::date as quando from task_storico group by 1"
    )
    return {str(r["task_id"]): r["quando"] for r in rows}


def giorni_fermo(task, ultimo: dict[str, date], oggi: date | None = None) -> int:
    """Giorni dall'ultimo aggiornamento (storico stati, poi updated_at, poi
    created_at)."""
    oggi = oggi or date.today()
    q = ultimo.get(str(task.id))
    if q is None:
        ts = task.updated_at or task.created_at
        q = ts.date() if ts else oggi - timedelta(days=0)
    return max((oggi - q).days, 0)
