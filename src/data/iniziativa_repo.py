"""Accesso dati per iniziative (proposte/progetti) e assegnazioni."""

from __future__ import annotations

from uuid import UUID

from src.domain.models import Assegnazione, Iniziativa
from src.lib import db

_UPD_INIZIATIVA = {
    "tipo",
    "stato",
    "codice",
    "titolo",
    "controparte",
    "responsabile_id",
    "tipo_attivita_default",
    "data_inizio",
    "data_fine",
    "ore_totali",
    "budget_totale",
    "probabilita_successo",
    "note",
}
_UPD_ASSEGNAZIONE = {
    "work_package_id",
    "tipo_attivita",
    "ore_pianificate",
    "tetto_ore_mese",
}


def _to_iniziativa(row: dict) -> Iniziativa:
    return Iniziativa.model_validate(row)


def list_iniziative(
    tipo: str | None = None, stati: list[str] | None = None
) -> list[Iniziativa]:
    sql = "select * from iniziativa"
    cond, params = [], []
    if tipo:
        cond.append("tipo = %s")
        params.append(tipo)
    if stati:
        cond.append("stato = any(%s)")
        params.append(stati)
    if cond:
        sql += " where " + " and ".join(cond)
    sql += " order by created_at desc"
    return [_to_iniziativa(r) for r in db.query(sql, params)]


def get_iniziativa(iniziativa_id: UUID | str) -> Iniziativa | None:
    row = db.query_one("select * from iniziativa where id = %s", (str(iniziativa_id),))
    return _to_iniziativa(row) if row else None


def create_iniziativa(**campi) -> Iniziativa:
    campi = {k: v for k, v in campi.items() if k in _UPD_INIZIATIVA}
    cols = ", ".join(campi)
    marks = ", ".join(["%s"] * len(campi))
    row = db.execute(
        f"insert into iniziativa ({cols}) values ({marks}) returning *",
        [str(v) if isinstance(v, UUID) else v for v in campi.values()],
    )[0]
    return _to_iniziativa(row)


def update_iniziativa(iniziativa_id: UUID | str, **campi) -> Iniziativa:
    campi = {k: v for k, v in campi.items() if k in _UPD_INIZIATIVA}
    if not campi:
        raise ValueError("Nessun campo aggiornabile fornito.")
    set_clause = ", ".join(f"{k} = %s" for k in campi)
    params = [str(v) if isinstance(v, UUID) else v for v in campi.values()] + [
        str(iniziativa_id)
    ]
    row = db.execute(
        f"update iniziativa set {set_clause} where id = %s returning *", params
    )[0]
    return _to_iniziativa(row)


def delete_iniziativa(iniziativa_id: UUID | str) -> None:
    db.execute("delete from iniziativa where id = %s", (str(iniziativa_id),))


def approva_proposta(
    iniziativa_id: UUID | str, eseguito_da: str | None = None
) -> Iniziativa:
    """Conversione proposta -> progetto (stessa entita', spec §6).

    WP, assegnazioni e voci di budget restano collegati: diventano la baseline.
    """
    row = db.execute(
        """
        update iniziativa
           set tipo = 'progetto', stato = 'attivo', probabilita_successo = null
         where id = %s and tipo = 'proposta'
        returning *
        """,
        (str(iniziativa_id),),
        user_email=eseguito_da,
    )
    if not row:
        raise ValueError("Iniziativa non trovata o non è una proposta.")
    return _to_iniziativa(row[0])


# --- Assegnazioni ---------------------------------------------------------


def list_assegnazioni(iniziativa_id: UUID | str) -> list[Assegnazione]:
    rows = db.query(
        "select * from assegnazione where iniziativa_id = %s order by created_at",
        (str(iniziativa_id),),
    )
    return [Assegnazione.model_validate(r) for r in rows]


def list_assegnazioni_persona(persona_id: UUID | str) -> list[Assegnazione]:
    rows = db.query(
        "select * from assegnazione where persona_id = %s", (str(persona_id),)
    )
    return [Assegnazione.model_validate(r) for r in rows]


def create_assegnazione(
    iniziativa_id: UUID | str,
    persona_id: UUID | str,
    tipo_attivita: str = "altro",
    ore_pianificate: float | None = None,
    tetto_ore_mese: float | None = None,
    work_package_id: UUID | str | None = None,
) -> Assegnazione:
    row = db.execute(
        """
        insert into assegnazione
            (iniziativa_id, persona_id, tipo_attivita, ore_pianificate,
             tetto_ore_mese, work_package_id)
        values (%s, %s, %s, %s, %s, %s)
        returning *
        """,
        (
            str(iniziativa_id),
            str(persona_id),
            tipo_attivita,
            ore_pianificate,
            tetto_ore_mese,
            str(work_package_id) if work_package_id else None,
        ),
    )[0]
    return Assegnazione.model_validate(row)


def update_assegnazione(assegnazione_id: UUID | str, **campi) -> Assegnazione:
    campi = {k: v for k, v in campi.items() if k in _UPD_ASSEGNAZIONE}
    if not campi:
        raise ValueError("Nessun campo aggiornabile fornito.")
    set_clause = ", ".join(f"{k} = %s" for k in campi)
    params = [str(v) if isinstance(v, UUID) else v for v in campi.values()] + [
        str(assegnazione_id)
    ]
    row = db.execute(
        f"update assegnazione set {set_clause} where id = %s returning *", params
    )[0]
    return Assegnazione.model_validate(row)


def delete_assegnazione(assegnazione_id: UUID | str) -> None:
    db.execute("delete from assegnazione where id = %s", (str(assegnazione_id),))
