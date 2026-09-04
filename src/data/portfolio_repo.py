"""Accesso dati per il portfolio pluriennale (v3): assegnazioni con contesto
iniziativa, piano ore per anno, persone con dati contrattuali."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.lib import db


def assegnazioni_portfolio() -> list[dict]:
    """Tutte le assegnazioni su proposte vive e progetti (attivi e chiusi), con
    i dati dell'iniziativa necessari al pro-rata per anno."""
    rows = db.query("""
        select a.id as assegnazione_id, a.persona_id, a.ore_pianificate,
               p.nome || ' ' || p.cognome as nome,
               i.id as iniziativa_id, i.tipo, i.stato, i.probabilita_successo,
               i.data_inizio, i.data_fine, i.acronimo, i.codice, i.titolo
        from assegnazione a
        join persona p on p.id = a.persona_id
        join iniziativa i on i.id = a.iniziativa_id
        where (i.tipo = 'proposta' and i.stato in ('bozza','inviata'))
           or i.tipo = 'progetto'
        order by i.data_inizio nulls last, p.cognome
        """)
    out = []
    for r in rows:
        prefisso = r["acronimo"] or r["codice"]
        out.append(
            {
                "assegnazione_id": str(r["assegnazione_id"]),
                "persona_id": str(r["persona_id"]),
                "nome": r["nome"],
                "iniziativa_id": str(r["iniziativa_id"]),
                "etichetta": f"{prefisso} · {r['titolo']}" if prefisso else r["titolo"],
                "tipo": r["tipo"],
                "stato": r["stato"],
                "probabilita": r["probabilita_successo"],
                "data_inizio": r["data_inizio"],
                "data_fine": r["data_fine"],
                "ore_pianificate": r["ore_pianificate"],
            }
        )
    return out


def piani_ore_anno(
    iniziativa_id: UUID | str | None = None,
) -> dict[tuple[str, int], Decimal]:
    """{(assegnazione_id, anno): ore} da `piano_ore_anno` (tutti o di una
    iniziativa)."""
    sql = """
        select p.assegnazione_id, p.anno, p.ore
        from piano_ore_anno p
        join assegnazione a on a.id = p.assegnazione_id
    """
    params: list = []
    if iniziativa_id:
        sql += " where a.iniziativa_id = %s"
        params.append(str(iniziativa_id))
    return {
        (str(r["assegnazione_id"]), int(r["anno"])): Decimal(r["ore"])
        for r in db.query(sql, params)
    }


def salva_piano_ore(
    assegnazione_id: UUID | str, piano: dict[int, Decimal | float | None]
) -> None:
    """Sostituisce il piano per anno di un'assegnazione (upsert + rimozione
    degli anni a zero/None)."""
    for anno, ore in piano.items():
        if ore is None or float(ore) <= 0:
            db.execute(
                "delete from piano_ore_anno where assegnazione_id = %s and anno = %s",
                (str(assegnazione_id), int(anno)),
            )
        else:
            db.execute(
                """
                insert into piano_ore_anno (assegnazione_id, anno, ore)
                values (%s, %s, %s)
                on conflict (assegnazione_id, anno)
                do update set ore = excluded.ore
                """,
                (str(assegnazione_id), int(anno), float(ore)),
            )


def persone_capacity() -> list[dict]:
    """Persone attive con monte ore e date contratto (per la disponibilità)."""
    return [
        {
            "id": str(r["id"]),
            "nome": r["nome"],
            "monte_ore_annuo": r["monte_ore_annuo"],
            "contratto_data_inizio": r["contratto_data_inizio"],
            "contratto_data_fine": r["contratto_data_fine"],
        }
        for r in db.query("""
            select id, nome || ' ' || cognome as nome, monte_ore_annuo,
                   contratto_data_inizio, contratto_data_fine
            from persona where attivo order by cognome, nome
            """)
    ]


def ore_consuntivo_per_anno() -> dict[tuple[str, str, int], Decimal]:
    """Ore a timesheet per (persona, iniziativa, anno) — confronto piano vs
    consuntivo nel portfolio."""
    rows = db.query("""
        select t.persona_id, a.iniziativa_id,
               extract(year from t.data)::int as anno, sum(t.ore) as ore
        from timesheet_ora t
        join assegnazione a on a.id = t.assegnazione_id
        group by 1, 2, 3
        """)
    return {
        (str(r["persona_id"]), str(r["iniziativa_id"]), int(r["anno"])): Decimal(
            r["ore"]
        )
        for r in rows
    }
