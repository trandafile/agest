"""Accesso dati per il cronoprogramma (Gantt) di un'iniziativa (migrazione 0019).

Logica pura (parsing, mesi↔date, avanzamento) in `src/domain/gantt.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from src.domain.gantt import GanttRow
from src.lib import db


def disponibile() -> bool:
    """True se la migrazione 0019 è applicata."""
    try:
        db.query("select 1 from gantt_voce limit 1")
        return True
    except Exception:  # noqa: BLE001
        return False


def list_voci(iniziativa_id: UUID | str) -> list[dict]:
    return db.query(
        "select * from gantt_voce where iniziativa_id = %s order by ordine, codice",
        (str(iniziativa_id),),
    )


def get_voce(voce_id: UUID | str) -> dict | None:
    return db.query_one("select * from gantt_voce where id = %s", (str(voce_id),))


def iniziative_con_gantt() -> dict[str, int]:
    """{iniziativa_id: numero voci}."""
    return {
        str(r["iniziativa_id"]): r["n"]
        for r in db.query(
            "select iniziativa_id, count(*) as n from gantt_voce group by 1"
        )
    }


def lavoro_collegato(iniziativa_id: UUID | str) -> list[dict]:
    """Task (non archiviati) collegati a una voce del Gantt dell'iniziativa."""
    return db.query(
        """
        select t.id, t.titolo, t.stato, t.scadenza, t.owner_id, t.gantt_voce_id,
               t.parent_task_id, t.deliverable_id
        from task t
        join gantt_voce g on g.id = t.gantt_voce_id
        where g.iniziativa_id = %s and not t.archiviato
        """,
        (str(iniziativa_id),),
    )


def deliverable_collegati(iniziativa_id: UUID | str) -> list[dict]:
    return db.query(
        """
        select d.id, d.titolo, d.stato, d.scadenza, d.gantt_voce_id
        from deliverable d
        join gantt_voce g on g.id = d.gantt_voce_id
        where g.iniziativa_id = %s and not d.archiviato
        """,
        (str(iniziativa_id),),
    )


def importa(
    iniziativa_id: UUID | str,
    righe: list[GanttRow],
    rimuovi_mancanti: bool = False,
) -> dict[str, int]:
    """Inserisce/aggiorna le voci per codice (una transazione).

    Le voci esistenti non presenti nel file restano, salvo `rimuovi_mancanti`
    (i task collegati perdono solo il collegamento: FK on delete set null).
    """
    iid = str(iniziativa_id)
    conta = {"inserite": 0, "aggiornate": 0, "rimosse": 0}
    with db.transaction() as cur:
        cur.execute(
            "select id, codice from gantt_voce where iniziativa_id = %s", (iid,)
        )
        esistenti = {r["codice"]: str(r["id"]) for r in cur.fetchall()}
        ids: dict[str, str] = {}
        for r in righe:
            vals = (
                r.title, r.kind, r.start, r.end, r.start_month, r.end_month,
                r.lead, r.order,
            )
            if r.code in esistenti:
                cur.execute(
                    """update gantt_voce set titolo = %s, tipo = %s, data_inizio = %s,
                           data_fine = %s, mese_inizio = %s, mese_fine = %s,
                           responsabile = %s, ordine = %s
                       where id = %s""",
                    (*vals, esistenti[r.code]),
                )
                ids[r.code] = esistenti[r.code]
                conta["aggiornate"] += 1
            else:
                cur.execute(
                    """insert into gantt_voce (iniziativa_id, codice, titolo, tipo,
                           data_inizio, data_fine, mese_inizio, mese_fine,
                           responsabile, ordine)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                    (iid, r.code, *vals),
                )
                ids[r.code] = str(cur.fetchone()["id"])
                conta["inserite"] += 1
        for r in righe:
            cur.execute(
                "update gantt_voce set parent_id = %s where id = %s",
                (ids.get(r.parent_code) if r.parent_code else None, ids[r.code]),
            )
        if rimuovi_mancanti:
            via = [v for c, v in esistenti.items() if c not in ids]
            if via:
                cur.execute("delete from gantt_voce where id = any(%s::uuid[])", (via,))
                conta["rimosse"] = len(via)
    return conta


def elimina_gantt(iniziativa_id: UUID | str) -> None:
    db.execute("delete from gantt_voce where iniziativa_id = %s", (str(iniziativa_id),))


def collega(tabella: str, id_: UUID | str, voce_id: UUID | str | None) -> None:
    if tabella not in ("task", "deliverable"):
        raise ValueError(tabella)
    db.execute(
        f"update {tabella} set gantt_voce_id = %s where id = %s",
        (str(voce_id) if voce_id else None, str(id_)),
    )


def collega_molti(tabella: str, coppie: list[tuple[Any, Any]]) -> int:
    """[(id, voce_id|None)] in una transazione."""
    if tabella not in ("task", "deliverable"):
        raise ValueError(tabella)
    with db.transaction() as cur:
        for id_, voce in coppie:
            cur.execute(
                f"update {tabella} set gantt_voce_id = %s where id = %s",
                (str(voce) if voce else None, str(id_)),
            )
    return len(coppie)


def trasferisci(
    iniziativa_id: UUID | str,
    voci: list[dict],
    owner_per_voce: dict[str, Any],
    deliverable_id: UUID | str | None,
    supervisor_id: UUID | str | None,
    prefisso_codice: bool,
    eseguito_da: str | None,
) -> dict[str, int]:
    """Crea nel lavoro operativo le voci scelte, collegate al Gantt.

    task → task (scadenza = fine voce, nel deliverable scelto o senza);
    deliverable → deliverable; wp → work package (se manca, per codice);
    milestone → milestone di progetto (data prevista = fine voce).
    Tutto in una transazione.
    """
    iid = str(iniziativa_id)
    conta = {"task": 0, "deliverable": 0, "wp": 0, "milestone": 0}
    with db.transaction(user_email=eseguito_da) as cur:
        for v in voci:
            titolo = f"{v['codice']} {v['titolo']}" if prefisso_codice else v["titolo"]
            fine: date | None = v.get("data_fine")
            owner = owner_per_voce.get(str(v["id"]))
            if v["tipo"] == "task":
                cur.execute(
                    """insert into task (iniziativa_id, deliverable_id, titolo, owner_id,
                           supervisor_id, scadenza, gantt_voce_id, descrizione)
                       values (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        iid,
                        str(deliverable_id) if deliverable_id else None,
                        titolo,
                        str(owner) if owner else None,
                        str(supervisor_id) if supervisor_id else None,
                        fine,
                        str(v["id"]),
                        _descr(v),
                    ),
                )
                conta["task"] += 1
            elif v["tipo"] == "deliverable":
                cur.execute(
                    """insert into deliverable (iniziativa_id, titolo, tipo, scadenza,
                           owner_id, supervisor_id, gantt_voce_id, descrizione)
                       values (%s, %s, 'report', %s, %s, %s, %s, %s)""",
                    (
                        iid,
                        titolo,
                        fine,
                        str(owner) if owner else None,
                        str(supervisor_id) if supervisor_id else None,
                        str(v["id"]),
                        _descr(v),
                    ),
                )
                conta["deliverable"] += 1
            elif v["tipo"] == "wp":
                cur.execute(
                    "select id from work_package where iniziativa_id = %s and codice = %s",
                    (iid, v["codice"]),
                )
                r = cur.fetchone()
                if r is None:
                    cur.execute(
                        """insert into work_package (iniziativa_id, codice, titolo)
                           values (%s, %s, %s) returning id""",
                        (iid, v["codice"], v["titolo"]),
                    )
                    r = cur.fetchone()
                    conta["wp"] += 1
                cur.execute(
                    "update gantt_voce set work_package_id = %s where id = %s",
                    (str(r["id"]), str(v["id"])),
                )
            elif v["tipo"] == "milestone":
                cur.execute(
                    """insert into milestone (iniziativa_id, titolo, data_prevista)
                       values (%s, %s, %s)""",
                    (iid, titolo, fine),
                )
                conta["milestone"] += 1
    return conta


def _descr(v: dict) -> str:
    bits = [f"Dal cronoprogramma: {v['codice']}"]
    if v.get("mese_inizio") and v.get("mese_fine"):
        bits.append(f"M{v['mese_inizio']}–M{v['mese_fine']}")
    if v.get("responsabile"):
        bits.append(f"responsabile: {v['responsabile']}")
    return " · ".join(bits)
