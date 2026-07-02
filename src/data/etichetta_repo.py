"""Accesso dati per etichette (label), dipendenze task, milestone↔deliverable."""

from __future__ import annotations

from uuid import UUID

from src.lib import db

# --- Etichette --------------------------------------------------------------


def list_etichette() -> list[dict]:
    return db.query("select * from etichetta order by nome")


def create_etichetta(nome: str, colore: str = "#888888") -> None:
    db.execute(
        "insert into etichetta (nome, colore) values (%s, %s) "
        "on conflict (nome) do nothing",
        (nome.strip(), colore),
    )


def delete_etichetta(etichetta_id: UUID | str) -> None:
    db.execute("delete from etichetta where id = %s", (str(etichetta_id),))


def etichette_task(task_id: UUID | str) -> list[str]:
    rows = db.query(
        "select etichetta_id from task_etichetta where task_id = %s",
        (str(task_id),),
    )
    return [str(r["etichetta_id"]) for r in rows]


def set_etichette_task(task_id: UUID | str, etichetta_ids: list[str]) -> None:
    db.execute("delete from task_etichetta where task_id = %s", (str(task_id),))
    for eid in etichetta_ids:
        db.execute(
            "insert into task_etichetta (task_id, etichetta_id) values (%s, %s) "
            "on conflict do nothing",
            (str(task_id), eid),
        )


def etichette_by_task() -> dict[str, list[dict]]:
    """{task_id: [{nome, colore}]} per il rendering veloce."""
    rows = db.query("""
        select te.task_id, e.nome, e.colore
        from task_etichetta te join etichetta e on e.id = te.etichetta_id
        """)
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r["task_id"]), []).append(
            {"nome": r["nome"], "colore": r["colore"]}
        )
    return out


# --- Dipendenze tra task ----------------------------------------------------


def dipendenze_task(task_id: UUID | str) -> list[str]:
    rows = db.query(
        "select dipende_da from task_dipendenza where task_id = %s",
        (str(task_id),),
    )
    return [str(r["dipende_da"]) for r in rows]


def set_dipendenze_task(task_id: UUID | str, dipende_da_ids: list[str]) -> None:
    db.execute("delete from task_dipendenza where task_id = %s", (str(task_id),))
    for did in dipende_da_ids:
        if str(did) == str(task_id):
            continue
        db.execute(
            "insert into task_dipendenza (task_id, dipende_da) values (%s, %s) "
            "on conflict do nothing",
            (str(task_id), did),
        )


# --- Milestone ↔ Deliverable ------------------------------------------------


def deliverable_di_milestone(milestone_id: UUID | str) -> list[str]:
    rows = db.query(
        "select deliverable_id from milestone_deliverable where milestone_id = %s",
        (str(milestone_id),),
    )
    return [str(r["deliverable_id"]) for r in rows]


def set_deliverable_milestone(
    milestone_id: UUID | str, deliverable_ids: list[str]
) -> None:
    db.execute(
        "delete from milestone_deliverable where milestone_id = %s",
        (str(milestone_id),),
    )
    for did in deliverable_ids:
        db.execute(
            "insert into milestone_deliverable (milestone_id, deliverable_id) "
            "values (%s, %s) on conflict do nothing",
            (str(milestone_id), did),
        )
