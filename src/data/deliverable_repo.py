"""Accesso dati per i deliverable (livello progetto→deliverable→task)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from src.domain.models import Deliverable
from src.lib import db

_UPDATABLE = {
    "iniziativa_id",
    "titolo",
    "tipo",
    "stato",
    "scadenza",
    "owner_id",
    "supervisor_id",
    "descrizione",
    "archiviato",
}


def _to_deliverable(row: dict) -> Deliverable:
    return Deliverable.model_validate(row)


def list_deliverables(
    iniziativa_id: UUID | str | None = None, include_archiviati: bool = False
) -> list[Deliverable]:
    sql = "select * from deliverable"
    cond, params = [], []
    if iniziativa_id:
        cond.append("iniziativa_id = %s")
        params.append(str(iniziativa_id))
    if not include_archiviati:
        cond.append("archiviato = false")
    if cond:
        sql += " where " + " and ".join(cond)
    sql += " order by scadenza nulls last, titolo"
    return [_to_deliverable(r) for r in db.query(sql, params)]


def get_deliverable(deliverable_id: UUID | str) -> Deliverable | None:
    row = db.query_one(
        "select * from deliverable where id = %s", (str(deliverable_id),)
    )
    return _to_deliverable(row) if row else None


def avanzamento_task() -> dict[str, dict]:
    """{deliverable_id: {totali, completati, in_ritardo}} sui task non archiviati.

    Serve alle barre di avanzamento: un deliverable "vale" i task che lo
    compongono.
    """
    rows = db.query("""
        select deliverable_id,
               count(*) as totali,
               count(*) filter (where stato = 'completato') as completati,
               count(*) filter (
                   where stato in ('da_fare','in_corso','bloccato')
                     and scadenza < current_date
               ) as in_ritardo
        from task
        where deliverable_id is not null and not archiviato
        group by 1
        """)
    return {
        str(r["deliverable_id"]): {
            "totali": int(r["totali"]),
            "completati": int(r["completati"]),
            "in_ritardo": int(r["in_ritardo"]),
        }
        for r in rows
    }


def puo_modificare(deliverable, persona_id, is_admin: bool) -> bool:
    """Regola MAIC tasks: modifica owner/supervisor (o admin)."""
    return is_admin or persona_id in (deliverable.owner_id, deliverable.supervisor_id)


def create_deliverable(
    iniziativa_id: UUID | str,
    titolo: str,
    tipo: str | None = None,
    scadenza: date | None = None,
    owner_id: UUID | str | None = None,
    supervisor_id: UUID | str | None = None,
    descrizione: str | None = None,
) -> Deliverable:
    row = db.execute(
        """
        insert into deliverable
            (iniziativa_id, titolo, tipo, scadenza, owner_id, supervisor_id,
             descrizione)
        values (%s, %s, %s, %s, %s, %s, %s)
        returning *
        """,
        (
            str(iniziativa_id),
            titolo,
            tipo,
            scadenza,
            str(owner_id) if owner_id else None,
            str(supervisor_id) if supervisor_id else None,
            descrizione,
        ),
    )[0]
    return _to_deliverable(row)


def update_deliverable(deliverable_id: UUID | str, **campi) -> Deliverable:
    campi = {k: v for k, v in campi.items() if k in _UPDATABLE}
    if not campi:
        raise ValueError("Nessun campo aggiornabile fornito.")
    set_clause = ", ".join(f"{k} = %s" for k in campi)
    params = [str(v) if isinstance(v, UUID) else v for v in campi.values()]
    params.append(str(deliverable_id))
    row = db.execute(
        f"update deliverable set {set_clause} where id = %s returning *", params
    )[0]
    return _to_deliverable(row)


def delete_deliverable(deliverable_id: UUID | str) -> None:
    from src.data import commento_repo

    commento_repo.delete_commenti_di("deliverable", deliverable_id)
    db.execute("delete from deliverable where id = %s", (str(deliverable_id),))
