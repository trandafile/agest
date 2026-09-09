"""Accesso dati per i monthly report (v3, spec §13.10)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from src.lib import db


def progetti_con_monthly() -> list[dict]:
    """Progetti attivi che richiedono il monthly report, con responsabile."""
    return db.query("""
        select i.id, i.acronimo, i.codice, i.titolo, i.responsabile_id,
               i.data_inizio, i.data_fine,
               p.nome || ' ' || p.cognome as responsabile, p.email as email_responsabile
        from iniziativa i
        left join persona p on p.id = i.responsabile_id
        where i.tipo = 'progetto' and i.stato = 'attivo' and i.monthly_report
        order by i.acronimo, i.titolo
        """)


def get_report(iniziativa_id: UUID | str, anno: int, mese: int) -> dict | None:
    return db.query_one(
        "select * from monthly_report "
        "where iniziativa_id = %s and anno = %s and mese = %s",
        (str(iniziativa_id), anno, mese),
    )


def list_report(iniziativa_id: UUID | str) -> list[dict]:
    return db.query(
        """
        select id, iniziativa_id, anno, mese, stato, generato_il, notificato_il,
               completato_il, note, length(contenuto_md) as dimensione
        from monthly_report where iniziativa_id = %s
        order by anno desc, mese desc
        """,
        (str(iniziativa_id),),
    )


def report_pronti_per_persona(persona_id: UUID | str, is_admin: bool) -> list[dict]:
    """Report in stato «pronto» dei progetti di cui la persona è responsabile
    (tutti, per l'amministratore)."""
    sql = """
        select r.id, r.iniziativa_id, r.anno, r.mese, r.stato, r.generato_il,
               i.acronimo, i.codice, i.titolo, i.responsabile_id
        from monthly_report r
        join iniziativa i on i.id = r.iniziativa_id
        where r.stato = 'pronto'
    """
    params: list = []
    if not is_admin:
        sql += " and i.responsabile_id = %s"
        params.append(str(persona_id))
    sql += " order by r.anno desc, r.mese desc, i.acronimo"
    return db.query(sql, params)


def salva_report(
    iniziativa_id: UUID | str, anno: int, mese: int, contenuto_md: str
) -> dict:
    """Crea o rigenera il report del mese (torna in stato «pronto»)."""
    return db.execute(
        """
        insert into monthly_report (iniziativa_id, anno, mese, contenuto_md)
        values (%s, %s, %s, %s)
        on conflict (iniziativa_id, anno, mese) do update
          set contenuto_md = excluded.contenuto_md,
              generato_il = now(),
              stato = 'pronto',
              completato_il = null
        returning *
        """,
        (str(iniziativa_id), anno, mese, contenuto_md),
    )[0]


def segna_completato(report_id: UUID | str, note: str | None = None) -> None:
    db.execute(
        """
        update monthly_report
           set stato = 'completato', completato_il = now(), note = coalesce(%s, note)
         where id = %s
        """,
        (note, str(report_id)),
    )


def riapri(report_id: UUID | str) -> None:
    db.execute(
        "update monthly_report set stato = 'pronto', completato_il = null "
        "where id = %s",
        (str(report_id),),
    )


def da_notificare() -> list[dict]:
    """Report pronti mai notificati, con e-mail del responsabile."""
    return db.query("""
        select r.id, r.iniziativa_id, r.anno, r.mese, r.contenuto_md,
               i.acronimo, i.codice, i.titolo,
               p.nome, p.email
        from monthly_report r
        join iniziativa i on i.id = r.iniziativa_id
        left join persona p on p.id = i.responsabile_id
        where r.notificato_il is null and r.stato = 'pronto'
        order by r.anno, r.mese
        """)


def segna_notificato(report_id: UUID | str) -> None:
    db.execute(
        "update monthly_report set notificato_il = now() where id = %s",
        (str(report_id),),
    )


def elimina_report(report_id: UUID | str) -> None:
    db.execute("delete from monthly_report where id = %s", (str(report_id),))


# --- Dati del mese per il pack ---------------------------------------------------


def commenti_nel_mese(iniziativa_id: UUID | str, da: date, a: date) -> list[dict]:
    """Commenti del mese su task, deliverable e progetto dell'iniziativa."""
    return db.query(
        """
        select c.entita, c.entita_id, c.testo, c.created_at as quando,
               p.nome || ' ' || p.cognome as autore
        from commento c
        left join persona p on p.id = c.autore_id
        where c.created_at >= %(da)s and c.created_at < %(a)s
          and (
            (c.entita = 'task' and c.entita_id in
                (select id from task where iniziativa_id = %(id)s))
            or (c.entita = 'deliverable' and c.entita_id in
                (select id from deliverable where iniziativa_id = %(id)s))
            or (c.entita = 'iniziativa' and c.entita_id = %(id)s)
          )
        order by c.created_at
        """,
        {"da": da, "a": a, "id": str(iniziativa_id)},
    )


def storico_nel_mese(iniziativa_id: UUID | str, da: date, a: date) -> list[dict]:
    return db.query(
        """
        select s.task_id, s.stato_prec as da, s.stato_nuovo as a,
               s.cambiato_il as quando, s.cambiato_da
        from task_storico s
        join task t on t.id = s.task_id
        where t.iniziativa_id = %s and s.cambiato_il >= %s and s.cambiato_il < %s
        order by s.cambiato_il
        """,
        (str(iniziativa_id), da, a),
    )


def ore_timesheet_mese(iniziativa_id: UUID | str, da: date, a: date) -> list[dict]:
    rows = db.query(
        """
        select p.nome || ' ' || p.cognome as persona, sum(t.ore) as ore
        from timesheet_ora t
        join assegnazione a on a.id = t.assegnazione_id
        join persona p on p.id = t.persona_id
        where a.iniziativa_id = %s and t.data >= %s and t.data < %s
        group by 1 order by 1
        """,
        (str(iniziativa_id), da, a),
    )
    return [{"persona": r["persona"], "ore": Decimal(r["ore"])} for r in rows]
