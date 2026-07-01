"""Accesso dati per `tariffa_oraria` (versionata)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from src.domain.models import TariffaOraria
from src.lib import db

_COLS = "id, persona_id, valido_da, valido_al, importo_orario, created_at, updated_at"
_UPDATABLE = {"valido_da", "valido_al", "importo_orario"}


def _to_tariffa(row: dict) -> TariffaOraria:
    return TariffaOraria.model_validate(row)


def list_tariffe(persona_id: UUID | str) -> list[TariffaOraria]:
    rows = db.query(
        f"""select {_COLS} from tariffa_oraria
            where persona_id = %s
            order by valido_da desc""",
        (str(persona_id),),
    )
    return [_to_tariffa(r) for r in rows]


def create_tariffa(
    persona_id: UUID | str,
    valido_da: date,
    importo_orario: Decimal | float | str,
    valido_al: date | None = None,
) -> TariffaOraria:
    row = db.execute(
        f"""insert into tariffa_oraria
                (persona_id, valido_da, valido_al, importo_orario)
            values (%s, %s, %s, %s)
            returning {_COLS}""",
        (str(persona_id), valido_da, valido_al, str(importo_orario)),
    )[0]
    return _to_tariffa(row)


def update_tariffa(tariffa_id: UUID | str, **campi) -> TariffaOraria:
    campi = {k: v for k, v in campi.items() if k in _UPDATABLE}
    if not campi:
        raise ValueError("Nessun campo aggiornabile fornito.")
    if "importo_orario" in campi:
        campi["importo_orario"] = str(campi["importo_orario"])
    set_clause = ", ".join(f"{k} = %s" for k in campi)
    params = [*campi.values(), str(tariffa_id)]
    row = db.execute(
        f"update tariffa_oraria set {set_clause} where id = %s returning {_COLS}",
        params,
    )[0]
    return _to_tariffa(row)


def delete_tariffa(tariffa_id: UUID | str) -> None:
    db.execute("delete from tariffa_oraria where id = %s", (str(tariffa_id),))
