"""Accesso dati per `persona` (nessuna query sparsa nelle pagine)."""

from __future__ import annotations

from uuid import UUID

from src.domain.models import Persona, RuoloSistema
from src.lib import db

_COLS = (
    "id, nome, cognome, matricola, email, ruolo_sistema, attivo, "
    "created_at, updated_at"
)
# Colonne aggiornabili via update_persona (whitelist: no nomi colonna dall'esterno)
_UPDATABLE = {"nome", "cognome", "matricola", "email", "ruolo_sistema", "attivo"}


def _to_persona(row: dict) -> Persona:
    return Persona.model_validate(row)


def list_persone(solo_attivi: bool = False) -> list[Persona]:
    sql = f"select {_COLS} from persona"
    if solo_attivi:
        sql += " where attivo = true"
    sql += " order by cognome, nome"
    return [_to_persona(r) for r in db.query(sql)]


def get_persona(persona_id: UUID | str) -> Persona | None:
    row = db.query_one(f"select {_COLS} from persona where id = %s", (str(persona_id),))
    return _to_persona(row) if row else None


def get_persona_by_email(email: str) -> Persona | None:
    row = db.query_one(
        f"select {_COLS} from persona where email = %s", (email.strip().lower(),)
    )
    return _to_persona(row) if row else None


def create_persona(
    nome: str,
    cognome: str,
    email: str,
    ruolo_sistema: RuoloSistema,
    matricola: str | None = None,
    attivo: bool = True,
) -> Persona:
    row = db.execute(
        f"""insert into persona (nome, cognome, email, ruolo_sistema, matricola, attivo)
            values (%s, %s, %s, %s, %s, %s)
            returning {_COLS}""",
        (
            nome.strip(),
            cognome.strip(),
            email.strip().lower(),
            RuoloSistema(ruolo_sistema).value,
            matricola or None,
            attivo,
        ),
    )[0]
    return _to_persona(row)


def update_persona(persona_id: UUID | str, **campi) -> Persona:
    campi = {k: v for k, v in campi.items() if k in _UPDATABLE}
    if not campi:
        raise ValueError("Nessun campo aggiornabile fornito.")
    if "ruolo_sistema" in campi:
        campi["ruolo_sistema"] = RuoloSistema(campi["ruolo_sistema"]).value
    if "email" in campi and isinstance(campi["email"], str):
        campi["email"] = campi["email"].strip().lower()
    set_clause = ", ".join(f"{k} = %s" for k in campi)
    params = [*campi.values(), str(persona_id)]
    row = db.execute(
        f"update persona set {set_clause} where id = %s returning {_COLS}", params
    )[0]
    return _to_persona(row)


def delete_persona(persona_id: UUID | str) -> None:
    db.execute("delete from persona where id = %s", (str(persona_id),))
