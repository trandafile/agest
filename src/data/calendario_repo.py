"""Eventi per il calendario: scadenze di task, deliverable e milestone."""

from __future__ import annotations

from src.lib import db


def eventi() -> list[dict]:
    """Tutti gli eventi datati (task/deliverable/milestone) non archiviati.

    Ritorna dict con: data, titolo, tipo ('task'|'deliverable'|'milestone'),
    stato, progetto (acronimo/titolo), owner_id, pagamento (bool), importo.
    """
    return db.query("""
        select t.scadenza as data, t.titolo, 'task' as tipo, t.stato,
               coalesce(i.acronimo, i.titolo) as progetto, t.owner_id,
               false as pagamento, null::numeric as importo
        from task t
        left join iniziativa i on i.id = t.iniziativa_id
        where t.scadenza is not null and not t.archiviato
          and t.stato in ('da_fare','in_corso','bloccato')

        union all
        select d.scadenza, d.titolo, 'deliverable', d.stato,
               coalesce(i.acronimo, i.titolo), d.owner_id, false, null
        from deliverable d
        join iniziativa i on i.id = d.iniziativa_id
        where d.scadenza is not null and not d.archiviato
          and d.stato in ('da_fare','in_corso','bloccato')

        union all
        select m.data_prevista, m.titolo, 'milestone', m.stato,
               coalesce(i.acronimo, i.titolo), i.responsabile_id,
               m.genera_pagamento, m.importo_incasso
        from milestone m
        join iniziativa i on i.id = m.iniziativa_id
        where m.data_prevista is not null and m.stato <> 'completata'
        order by data
        """)
