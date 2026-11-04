"""Accesso dati per l'import YAML/JSON di deliverable/task/subtask.

La logica (parsing, validazione, anteprima) è pura in
`src/domain/task_import.py`; qui solo lettura dell'istantanea e scrittura
del piano in UNA transazione (o tutto o niente).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.domain.task_import import ETICHETTA_AZIONE, Op, Piano
from src.lib import db

_COLS_DELIV = (
    "id", "iniziativa_id", "titolo", "tipo", "stato", "scadenza", "owner_id",
    "supervisor_id", "descrizione", "archiviato",
)
_COLS_TASK = (
    "id", "iniziativa_id", "deliverable_id", "parent_task_id", "titolo",
    "descrizione", "owner_id", "supervisor_id", "stato", "priorita",
    "ore_stimate", "scadenza", "completato_il", "archiviato",
)
# colonne che un Op può scrivere (whitelist: i nomi colonna non arrivano mai
# dal file importato)
_SCRIVIBILI = {
    "deliverable": {"iniziativa_id", "titolo", "tipo", "stato", "scadenza",
                    "owner_id", "supervisor_id", "descrizione", "gantt_voce_id"},
    "task": {"iniziativa_id", "deliverable_id", "parent_task_id", "titolo",
             "descrizione", "owner_id", "supervisor_id", "stato", "priorita",
             "ore_stimate", "scadenza", "completato_il", "gantt_voce_id"},
}


def istantanea(iniziativa_id: UUID | str) -> dict:
    """Tutti i deliverable e i task (subtask inclusi) dell'iniziativa,
    archiviati compresi."""
    iid = str(iniziativa_id)
    ds = db.query(
        f"select {', '.join(_COLS_DELIV)} from deliverable where iniziativa_id = %s "
        "order by created_at",
        (iid,),
    )
    ts = db.query(
        f"select {', '.join(_COLS_TASK)} from task where iniziativa_id = %s "
        "order by created_at",
        (iid,),
    )
    return {"deliverables": ds, "tasks": ts}


def persone_attive() -> list[dict]:
    return db.query(
        "select id, nome, cognome, email from persona where attivo "
        "order by cognome, nome"
    )


def voci_gantt(iniziativa_id: UUID | str) -> list[dict]:
    """Voci del Gantt dell'iniziativa ([] se la migrazione 0019 manca)."""
    try:
        return db.query(
            "select id, codice, titolo, tipo, data_inizio, data_fine "
            "from gantt_voce where iniziativa_id = %s order by ordine, codice",
            (str(iniziativa_id),),
        )
    except Exception:  # noqa: BLE001 — tabella non ancora creata
        return []


def _insert(cur: Any, tabella: str, campi: dict) -> str:
    cols = list(campi)
    cur.execute(
        f"insert into {tabella} ({', '.join(cols)}) "
        f"values ({', '.join(['%s'] * len(cols))}) returning id",
        [campi[c] for c in cols],
    )
    return str(cur.fetchone()["id"])


def _update(cur: Any, tabella: str, id_: Any, campi: dict) -> None:
    if not campi:
        return
    cols = list(campi)
    cur.execute(
        f"update {tabella} set {', '.join(f'{c} = %s' for c in cols)} "
        "where id = %s",
        [*(campi[c] for c in cols), str(id_)],
    )
    if cur.rowcount != 1:
        raise RuntimeError(f"{tabella} {id_}: nessuna riga aggiornata")


def applica_piano(piano: Piano, eseguito_da: str | None = None) -> tuple[list[str], list[dict]]:
    """Scrive il piano in un'unica transazione.

    Ritorna (righe di resoconto, task creati [{id, titolo, owner_id,
    scadenza}]) — i task creati servono alle notifiche, inviate DOPO il commit.
    Solleva l'eccezione del DB se qualcosa fallisce: in quel caso non è stato
    scritto nulla.
    """
    if not piano.ok:
        raise ValueError("Il piano contiene errori: niente da scrivere.")
    ids: dict[int, str] = {}
    fatto: list[str] = []
    creati: list[dict] = []

    def db_id(op: Op | None) -> str | None:
        if op is None or op.loose:
            return None
        return str(op.row["id"]) if op.row else ids.get(id(op))

    def scrivi(cur: Any, op: Op, tabella: str, extra: dict) -> None:
        tipo = "deliverable" if tabella == "deliverable" else "task"
        campi = {k: v for k, v in {**op.fields, **extra}.items()
                 if k in _SCRIVIBILI[tipo]}
        if op.action == "create":
            ids[id(op)] = _insert(cur, tabella, campi)
            if tipo == "task":
                creati.append({"id": ids[id(op)], **campi})
        elif campi:
            _update(cur, tabella, op.row["id"], campi)
            if op.kind == "task" and op.action == "move":
                # i subtask seguono il task nel nuovo deliverable
                cur.execute(
                    "update task set deliverable_id = %s where parent_task_id = %s",
                    (campi.get("deliverable_id"), str(op.row["id"])),
                )
        else:
            return
        rif = f" {op.ref}" if op.row else ""
        fatto.append(f"{ETICHETTA_AZIONE.get(op.action, op.action)} {op.kind}{rif} — {op.title}")

    with db.transaction(user_email=eseguito_da) as cur:
        for op in piano.ops:
            if op.kind == "deliverable" and not op.loose:
                scrivi(cur, op, "deliverable", {})
        for op in piano.ops:
            if op.kind == "task":
                extra = {}
                if op.action in ("create", "move"):
                    extra["deliverable_id"] = db_id(op.parent)
                scrivi(cur, op, "task", extra)
        for op in piano.ops:
            if op.kind == "subtask":
                extra = {}
                if op.action in ("create", "move"):
                    extra["parent_task_id"] = db_id(op.parent)
                    # il subtask segue il deliverable del task padre
                    padre = op.parent
                    extra["deliverable_id"] = (
                        padre.final.get("deliverable_id")
                        if padre and padre.action not in ("create", "move")
                        else db_id(padre.parent) if padre else None
                    )
                scrivi(cur, op, "task", extra)
    return fatto, creati
