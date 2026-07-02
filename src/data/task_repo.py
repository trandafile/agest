"""Accesso dati per i task (stile MAIC tasks).

Visibilita' come MAIC tasks: tutti gli autenticati vedono tutto; la modifica
spetta a owner/supervisor (o admin) — enforcement nelle pagine (Opzione A).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from src.domain.models import Task
from src.lib import db

_UPDATABLE = {
    "iniziativa_id",
    "deliverable_id",
    "parent_task_id",
    "titolo",
    "descrizione",
    "owner_id",
    "supervisor_id",
    "stato",
    "priorita",
    "ore_stimate",
    "scadenza",
    "completato_il",
    "archiviato",
}


def _to_task(row: dict) -> Task:
    return Task.model_validate(row)


def list_tasks(
    include_archiviati: bool = False,
    iniziativa_id: UUID | str | None = None,
) -> list[Task]:
    sql = "select * from task"
    cond, params = [], []
    if not include_archiviati:
        cond.append("archiviato = false")
    if iniziativa_id:
        cond.append("iniziativa_id = %s")
        params.append(str(iniziativa_id))
    if cond:
        sql += " where " + " and ".join(cond)
    sql += " order by scadenza nulls last, created_at"
    return [_to_task(r) for r in db.query(sql, params)]


def get_task(task_id: UUID | str) -> Task | None:
    row = db.query_one("select * from task where id = %s", (str(task_id),))
    return _to_task(row) if row else None


def create_task(
    titolo: str,
    owner_id: UUID | str | None = None,
    supervisor_id: UUID | str | None = None,
    iniziativa_id: UUID | str | None = None,
    deliverable_id: UUID | str | None = None,
    parent_task_id: UUID | str | None = None,
    descrizione: str | None = None,
    priorita: str = "nessuna",
    scadenza: date | None = None,
    ore_stimate: float | None = None,
) -> Task:
    row = db.execute(
        """
        insert into task (titolo, owner_id, supervisor_id, iniziativa_id,
                          deliverable_id, parent_task_id, descrizione, priorita,
                          scadenza, ore_stimate)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning *
        """,
        (
            titolo,
            str(owner_id) if owner_id else None,
            str(supervisor_id) if supervisor_id else None,
            str(iniziativa_id) if iniziativa_id else None,
            str(deliverable_id) if deliverable_id else None,
            str(parent_task_id) if parent_task_id else None,
            descrizione,
            priorita,
            scadenza,
            ore_stimate,
        ),
    )[0]
    return _to_task(row)


def update_task(task_id: UUID | str, **campi) -> Task:
    campi = {k: v for k, v in campi.items() if k in _UPDATABLE}
    if not campi:
        raise ValueError("Nessun campo aggiornabile fornito.")
    # completamento: traccia la data
    if campi.get("stato") == "completato" and "completato_il" not in campi:
        campi["completato_il"] = date.today()
    if campi.get("stato") in ("da_fare", "in_corso", "bloccato"):
        campi.setdefault("completato_il", None)
    set_clause = ", ".join(f"{k} = %s" for k in campi)
    params = [str(v) if isinstance(v, UUID) else v for v in campi.values()]
    params.append(str(task_id))
    row = db.execute(f"update task set {set_clause} where id = %s returning *", params)[
        0
    ]
    return _to_task(row)


def delete_task(task_id: UUID | str) -> None:
    db.execute("delete from task where id = %s", (str(task_id),))


def puo_modificare(task: Task, persona_id: UUID, is_admin: bool) -> bool:
    """Regola MAIC tasks: modifica owner/supervisor (o admin)."""
    return is_admin or persona_id in (task.owner_id, task.supervisor_id)


def carico_per_persona() -> list[dict]:
    """Analisi del carico di lavoro per persona (task attivi come owner).

    Ritorna: nome, task attivi, ore stimate totali, task in ritardo,
    completati negli ultimi 30 giorni.
    """
    return db.query("""
        select p.id as persona_id, p.nome || ' ' || p.cognome as nome,
               count(*) filter (
                   where t.stato in ('da_fare','in_corso','bloccato')
                     and not t.archiviato
               ) as attivi,
               coalesce(sum(t.ore_stimate) filter (
                   where t.stato in ('da_fare','in_corso','bloccato')
                     and not t.archiviato
               ), 0) as ore_stimate,
               count(*) filter (
                   where t.stato in ('da_fare','in_corso','bloccato')
                     and not t.archiviato and t.scadenza < current_date
               ) as in_ritardo,
               count(*) filter (
                   where t.stato = 'completato'
                     and t.completato_il >= current_date - 30
               ) as completati_30
        from persona p
        left join task t on t.owner_id = p.id
        where p.attivo
        group by p.id, p.nome, p.cognome
        having count(t.id) > 0
        order by attivi desc, ore_stimate desc
        """)


def tasks_per_calendario() -> list[dict]:
    """Task attivi con scadenza, per il calendario/agenda."""
    return db.query("""
        select t.id, t.titolo, t.scadenza, t.stato, t.priorita,
               t.owner_id, i.acronimo, i.titolo as progetto
        from task t
        left join iniziativa i on i.id = t.iniziativa_id
        where t.scadenza is not null and not t.archiviato
          and t.stato in ('da_fare','in_corso','bloccato')
        order by t.scadenza
        """)
