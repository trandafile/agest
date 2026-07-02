"""Accesso dati per `persona` (nessuna query sparsa nelle pagine)."""

from __future__ import annotations

from uuid import UUID

from src.domain.models import Persona, RuoloSistema
from src.lib import db

_COLS = (
    "id, nome, cognome, matricola, email, ruolo_sistema, attivo, "
    "codice_fiscale, monte_ore_annuo, tipo_contratto, contratto_data_inizio, "
    "contratto_data_fine, created_at, updated_at"
)
# Colonne aggiornabili via update_persona (whitelist: no nomi colonna dall'esterno)
_UPDATABLE = {
    "nome",
    "cognome",
    "matricola",
    "email",
    "ruolo_sistema",
    "attivo",
    "codice_fiscale",
    "monte_ore_annuo",
    "tipo_contratto",
    "contratto_data_inizio",
    "contratto_data_fine",
}


def _to_persona(row: dict) -> Persona:
    return Persona.model_validate(row)


def list_persone(solo_attivi: bool = False) -> list[Persona]:
    sql = f"select {_COLS} from persona"
    if solo_attivi:
        sql += " where attivo = true"
    sql += " order by cognome, nome"
    return [_to_persona(r) for r in db.query(sql)]


def list_persone_assegnate_a_pm(pm_id: UUID | str) -> list[Persona]:
    """Persone con assegnazioni su iniziative di cui il pm e' responsabile
    (spec §3: il pm vede i timesheet delle persone assegnate, sola lettura).
    """
    rows = db.query(
        f"""
        select {_COLS} from persona
        where id in (
            select a.persona_id
            from assegnazione a
            join iniziativa i on i.id = a.iniziativa_id
            where i.responsabile_id = %s
        )
        order by cognome, nome
        """,
        (str(pm_id),),
    )
    return [_to_persona(r) for r in rows]


def get_persona(persona_id: UUID | str) -> Persona | None:
    row = db.query_one(f"select {_COLS} from persona where id = %s", (str(persona_id),))
    return _to_persona(row) if row else None


def get_persona_by_email(email: str) -> Persona | None:
    row = db.query_one(
        f"select {_COLS} from persona where email = %s", (email.strip().lower(),)
    )
    return _to_persona(row) if row else None


def _norm_str(v: object) -> object:
    """Enum StrEnum -> valore stringa; il resto invariato."""
    from enum import Enum

    return v.value if isinstance(v, Enum) else v


def create_persona(
    nome: str,
    cognome: str,
    email: str,
    ruolo_sistema: RuoloSistema,
    matricola: str | None = None,
    attivo: bool = True,
    tipo_contratto=None,
    contratto_data_inizio=None,
    contratto_data_fine=None,
) -> Persona:
    row = db.execute(
        f"""insert into persona
                (nome, cognome, email, ruolo_sistema, matricola, attivo,
                 tipo_contratto, contratto_data_inizio, contratto_data_fine)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning {_COLS}""",
        (
            nome.strip(),
            cognome.strip(),
            email.strip().lower(),
            RuoloSistema(ruolo_sistema).value,
            matricola or None,
            attivo,
            _norm_str(tipo_contratto),
            contratto_data_inizio,
            contratto_data_fine,
        ),
    )[0]
    return _to_persona(row)


def update_persona(persona_id: UUID | str, **campi) -> Persona:
    campi = {k: v for k, v in campi.items() if k in _UPDATABLE}
    if not campi:
        raise ValueError("Nessun campo aggiornabile fornito.")
    if "ruolo_sistema" in campi:
        campi["ruolo_sistema"] = RuoloSistema(campi["ruolo_sistema"]).value
    if "tipo_contratto" in campi:
        campi["tipo_contratto"] = _norm_str(campi["tipo_contratto"])
    if "email" in campi and isinstance(campi["email"], str):
        campi["email"] = campi["email"].strip().lower()
    set_clause = ", ".join(f"{k} = %s" for k in campi)
    params = [*campi.values(), str(persona_id)]
    row = db.execute(
        f"update persona set {set_clause} where id = %s returning {_COLS}", params
    )[0]
    return _to_persona(row)


def riepilogo_dipendenze(persona_id: UUID | str) -> dict:
    """Conteggio dei dati collegati alla persona (per l'eliminazione sicura)."""
    return db.query_one(
        """
        select
          (select count(*) from assegnazione
             where persona_id = %(id)s) as assegnazioni,
          (select count(*) from timesheet_ora
             where persona_id = %(id)s) as ore_timesheet,
          (select count(*) from timesheet_mese
             where persona_id = %(id)s and stato = 'confermato') as mesi_confermati,
          (select count(*) from presenza
             where persona_id = %(id)s) as presenze,
          (select count(*) from assenza
             where persona_id = %(id)s) as assenze,
          (select count(*) from tariffa_oraria
             where persona_id = %(id)s) as tariffe,
          (select count(*) from iniziativa
             where responsabile_id = %(id)s) as progetti_responsabile,
          (select count(*) from task
             where owner_id = %(id)s or supervisor_id = %(id)s) as task
        """,
        {"id": str(persona_id)},
    )


def elimina_persona(persona_id: UUID | str, eseguito_da: str | None = None) -> None:
    """Eliminazione sicura e atomica (funzione DB): azzera i riferimenti
    RESTRICT, traccia in audit e rimuove la persona (cascade sui dati propri)."""
    db.execute("select elimina_persona(%s)", (str(persona_id),), user_email=eseguito_da)


def delete_persona(persona_id: UUID | str) -> None:
    """Alias storico -> eliminazione sicura."""
    elimina_persona(persona_id)
