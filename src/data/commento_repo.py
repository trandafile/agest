"""Accesso dati per i commenti generici (task, deliverable, milestone, ...)."""

from __future__ import annotations

from uuid import UUID

from src.domain.models import ENTITA_COMMENTABILI, Commento
from src.lib import db


def _check(entita: str) -> str:
    if entita not in ENTITA_COMMENTABILI:
        raise ValueError(f"Entita' non commentabile: {entita}")
    return entita


def list_commenti(entita: str, entita_id: UUID | str) -> list[Commento]:
    rows = db.query(
        """
        select * from commento
        where entita = %s and entita_id = %s
        order by created_at
        """,
        (_check(entita), str(entita_id)),
    )
    return [Commento.model_validate(r) for r in rows]


def add_commento(
    entita: str,
    entita_id: UUID | str,
    testo: str,
    autore_id: UUID | str | None = None,
) -> Commento | None:
    """Aggiunge un commento; ignora i testi vuoti (ritorna None)."""
    testo = (testo or "").strip()
    if not testo:
        return None
    row = db.execute(
        """
        insert into commento (entita, entita_id, autore_id, testo)
        values (%s, %s, %s, %s)
        returning *
        """,
        (
            _check(entita),
            str(entita_id),
            str(autore_id) if autore_id else None,
            testo,
        ),
    )[0]
    return Commento.model_validate(row)


def update_commento(commento_id: UUID | str, testo: str) -> None:
    testo = (testo or "").strip()
    if not testo:
        raise ValueError("Il commento non puo' essere vuoto.")
    db.execute(
        "update commento set testo = %s where id = %s",
        (testo, str(commento_id)),
    )


def delete_commento(commento_id: UUID | str) -> None:
    db.execute("delete from commento where id = %s", (str(commento_id),))


def delete_commenti_di(entita: str, entita_id: UUID | str) -> None:
    """Pulizia quando si elimina l'entita' commentata (niente FK a DB)."""
    db.execute(
        "delete from commento where entita = %s and entita_id = %s",
        (_check(entita), str(entita_id)),
    )


def conta_commenti(entita: str, ids: list[str] | None = None) -> dict[str, int]:
    """{entita_id: n_commenti} per mostrare il badge 💬 nelle liste."""
    _check(entita)
    if ids is not None and not ids:
        return {}
    sql = "select entita_id, count(*) as n from commento where entita = %s"
    params: list = [entita]
    if ids:
        sql += " and entita_id = any(%s)"
        params.append([str(i) for i in ids])
    sql += " group by entita_id"
    return {str(r["entita_id"]): r["n"] for r in db.query(sql, params)}
