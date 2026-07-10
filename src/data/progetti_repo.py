"""Accesso dati per WP, voci di budget, milestone e query economiche."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from src.domain.models import Milestone, TariffaOraria, VoceBudget, WorkPackage
from src.lib import db

# --- Work package (OPZIONALI) ---------------------------------------------


def list_work_packages(iniziativa_id: UUID | str) -> list[WorkPackage]:
    rows = db.query(
        "select * from work_package where iniziativa_id = %s order by codice, titolo",
        (str(iniziativa_id),),
    )
    return [WorkPackage.model_validate(r) for r in rows]


def create_work_package(
    iniziativa_id: UUID | str,
    titolo: str,
    codice: str | None = None,
    budget_ore: float | None = None,
    budget_costo: float | None = None,
) -> WorkPackage:
    row = db.execute(
        """
        insert into work_package
            (iniziativa_id, titolo, codice, budget_ore, budget_costo)
        values (%s, %s, %s, %s, %s) returning *
        """,
        (str(iniziativa_id), titolo, codice, budget_ore, budget_costo),
    )[0]
    return WorkPackage.model_validate(row)


def delete_work_package(wp_id: UUID | str) -> None:
    db.execute("delete from work_package where id = %s", (str(wp_id),))


# --- Voci di budget ----------------------------------------------------------


def list_voci_budget(iniziativa_id: UUID | str) -> list[VoceBudget]:
    rows = db.query(
        "select * from voce_budget where iniziativa_id = %s order by categoria",
        (str(iniziativa_id),),
    )
    return [VoceBudget.model_validate(r) for r in rows]


def create_voce_budget(
    iniziativa_id: UUID | str,
    categoria: str,
    importo: float,
    descrizione: str | None = None,
    work_package_id: UUID | str | None = None,
) -> VoceBudget:
    row = db.execute(
        """
        insert into voce_budget
            (iniziativa_id, categoria, importo, descrizione, work_package_id)
        values (%s, %s, %s, %s, %s) returning *
        """,
        (
            str(iniziativa_id),
            categoria,
            importo,
            descrizione,
            str(work_package_id) if work_package_id else None,
        ),
    )[0]
    return VoceBudget.model_validate(row)


def delete_voce_budget(voce_id: UUID | str) -> None:
    db.execute("delete from voce_budget where id = %s", (str(voce_id),))


def budget_per_categoria(iniziativa_id: UUID | str) -> dict[str, Decimal]:
    rows = db.query(
        """
        select categoria, sum(importo) as tot
        from voce_budget where iniziativa_id = %s group by categoria
        """,
        (str(iniziativa_id),),
    )
    return {r["categoria"]: Decimal(r["tot"]) for r in rows}


# --- Milestone ----------------------------------------------------------------


def list_milestones(iniziativa_id: UUID | str) -> list[Milestone]:
    rows = db.query(
        "select * from milestone where iniziativa_id = %s "
        "order by data_prevista nulls last",
        (str(iniziativa_id),),
    )
    return [Milestone.model_validate(r) for r in rows]


def create_milestone(
    iniziativa_id: UUID | str,
    titolo: str,
    data_prevista: date | None = None,
    importo_incasso: float | None = None,
    work_package_id: UUID | str | None = None,
    genera_pagamento: bool = False,
) -> Milestone:
    row = db.execute(
        """
        insert into milestone
            (iniziativa_id, titolo, data_prevista, importo_incasso,
             work_package_id, genera_pagamento)
        values (%s, %s, %s, %s, %s, %s) returning *
        """,
        (
            str(iniziativa_id),
            titolo,
            data_prevista,
            importo_incasso,
            str(work_package_id) if work_package_id else None,
            genera_pagamento,
        ),
    )[0]
    return Milestone.model_validate(row)


def set_stato_milestone(milestone_id: UUID | str, stato: str) -> None:
    db.execute(
        "update milestone set stato = %s where id = %s",
        (stato, str(milestone_id)),
    )


def delete_milestone(milestone_id: UUID | str) -> None:
    from src.data import commento_repo

    commento_repo.delete_commenti_di("milestone", milestone_id)
    db.execute("delete from milestone where id = %s", (str(milestone_id),))


# --- Query economiche -----------------------------------------------------------


def tariffe_by_persona(
    persona_ids: list[str] | None = None,
) -> dict[str, list[TariffaOraria]]:
    """Tariffe versionate raggruppate per persona (per i calcoli di dominio)."""
    if persona_ids:
        rows = db.query(
            "select * from tariffa_oraria where persona_id = any(%s)",
            ([str(p) for p in persona_ids],),
        )
    else:
        rows = db.query("select * from tariffa_oraria")
    out: dict[str, list[TariffaOraria]] = {}
    for r in rows:
        out.setdefault(str(r["persona_id"]), []).append(TariffaOraria.model_validate(r))
    return out


def piani_iniziativa(iniziativa_id: UUID | str) -> list[dict]:
    """Assegnazioni pianificate con nome persona ed etichetta WP."""
    return db.query(
        """
        select a.id, a.persona_id, a.tipo_attivita, a.ore_pianificate,
               a.tetto_ore_mese,
               p.nome || ' ' || p.cognome as nome,
               w.titolo as work_package
        from assegnazione a
        join persona p on p.id = a.persona_id
        left join work_package w on w.id = a.work_package_id
        where a.iniziativa_id = %s
        order by p.cognome, a.tipo_attivita
        """,
        (str(iniziativa_id),),
    )


def ore_pianificate_attive() -> list[tuple[str, str, Decimal]]:
    """Capacity check: (persona_id, nome, ore) su proposte vive e progetti attivi."""
    rows = db.query("""
        select a.persona_id, p.nome || ' ' || p.cognome as nome,
               coalesce(a.ore_pianificate, 0) as ore
        from assegnazione a
        join persona p on p.id = a.persona_id
        join iniziativa i on i.id = a.iniziativa_id
        where (i.tipo = 'proposta' and i.stato in ('bozza','inviata'))
           or (i.tipo = 'progetto' and i.stato = 'attivo')
        """)
    return [(str(r["persona_id"]), r["nome"], Decimal(r["ore"])) for r in rows]


def ore_consuntivo(iniziativa_id: UUID | str) -> list[tuple[str, date, int]]:
    """Ore registrate a timesheet sull'iniziativa: (persona_id, data, ore)."""
    rows = db.query(
        """
        select t.persona_id, t.data, t.ore
        from timesheet_ora t
        join assegnazione a on a.id = t.assegnazione_id
        where a.iniziativa_id = %s
        """,
        (str(iniziativa_id),),
    )
    return [(str(r["persona_id"]), r["data"], int(r["ore"])) for r in rows]


def speso_per_categoria(iniziativa_id: UUID | str) -> dict[str, Decimal]:
    """Spese consuntive per categoria (tabella `spesa`, Fase 4)."""
    rows = db.query(
        """
        select categoria, sum(importo) as tot
        from spesa where iniziativa_id = %s group by categoria
        """,
        (str(iniziativa_id),),
    )
    return {r["categoria"]: Decimal(r["tot"]) for r in rows}
