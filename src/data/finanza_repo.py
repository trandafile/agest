"""Accesso dati per il modulo Finanza (solo admin, guardia applicativa)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from src.lib import db

# --- Movimenti bancari -------------------------------------------------------


def list_movimenti(anno: int | None = None) -> list[dict]:
    if anno:
        return db.query(
            "select * from movimento_bancario "
            "where extract(year from data)::int = %s order by data desc",
            (anno,),
        )
    return db.query("select * from movimento_bancario order by data desc")


def import_movimenti(righe: list[dict], eseguito_da: str | None = None) -> int:
    n = 0
    for r in righe:
        db.execute(
            """
            insert into movimento_bancario
                (data, importo, segno, descrizione, controparte)
            values (%s, %s, %s, %s, %s)
            """,
            (r["data"], r["importo"], r["segno"], r["descrizione"], r["controparte"]),
            user_email=eseguito_da,
        )
        n += 1
    return n


def riconcilia_movimento(
    movimento_id: UUID | str,
    iniziativa_id: UUID | str | None,
    eseguito_da: str | None = None,
) -> None:
    db.execute(
        "update movimento_bancario set iniziativa_id = %s where id = %s",
        (str(iniziativa_id) if iniziativa_id else None, str(movimento_id)),
        user_email=eseguito_da,
    )


# --- Documenti fiscali ---------------------------------------------------------


def list_documenti(anno: int | None = None) -> list[dict]:
    if anno:
        return db.query(
            "select * from documento_fiscale "
            "where extract(year from data)::int = %s order by data desc",
            (anno,),
        )
    return db.query("select * from documento_fiscale order by data desc")


def import_documenti(righe: list[dict], eseguito_da: str | None = None) -> int:
    n = 0
    for r in righe:
        db.execute(
            """
            insert into documento_fiscale
                (tipo, numero, data, importo, controparte,
                 stato_incasso_pagamento, data_scadenza)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                r["tipo"],
                r["numero"],
                r["data"],
                r["importo"],
                r["controparte"],
                r["stato_incasso_pagamento"],
                r["data_scadenza"],
            ),
            user_email=eseguito_da,
        )
        n += 1
    return n


def riconcilia_documento(
    documento_id: UUID | str,
    iniziativa_id: UUID | str | None,
    eseguito_da: str | None = None,
) -> None:
    db.execute(
        "update documento_fiscale set iniziativa_id = %s where id = %s",
        (str(iniziativa_id) if iniziativa_id else None, str(documento_id)),
        user_email=eseguito_da,
    )


# --- Spese ------------------------------------------------------------------------


def list_spese(iniziativa_id: UUID | str | None = None) -> list[dict]:
    if iniziativa_id:
        return db.query(
            "select * from spesa where iniziativa_id = %s order by data desc",
            (str(iniziativa_id),),
        )
    return db.query("select * from spesa order by data desc")


def create_spesa(
    categoria: str,
    importo: float,
    giorno: date,
    iniziativa_id: UUID | str | None = None,
    descrizione: str | None = None,
    riferimento_documento: str | None = None,
    eseguito_da: str | None = None,
) -> None:
    db.execute(
        """
        insert into spesa
            (categoria, importo, data, iniziativa_id, descrizione,
             riferimento_documento)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (
            categoria,
            importo,
            giorno,
            str(iniziativa_id) if iniziativa_id else None,
            descrizione,
            riferimento_documento,
        ),
        user_email=eseguito_da,
    )


def delete_spesa(spesa_id: UUID | str, eseguito_da: str | None = None) -> None:
    db.execute(
        "delete from spesa where id = %s", (str(spesa_id),), user_email=eseguito_da
    )


# --- Dashboard -----------------------------------------------------------------------


def cash_flow_mensile(anno: int) -> list[dict]:
    """Entrate/uscite per mese dell'anno."""
    return db.query(
        """
        select extract(month from data)::int as mese,
               sum(case when segno = 'entrata' then importo else 0 end) as entrate,
               sum(case when segno = 'uscita'  then importo else 0 end) as uscite
        from movimento_bancario
        where extract(year from data)::int = %s
        group by 1 order by 1
        """,
        (anno,),
    )


def pnl_per_progetto() -> list[dict]:
    """P&L per iniziativa dai movimenti riconciliati."""
    return db.query("""
        select coalesce(i.titolo, '(non riconciliato)') as progetto,
               sum(case when m.segno = 'entrata' then m.importo else 0 end) as entrate,
               sum(case when m.segno = 'uscita'  then m.importo else 0 end) as uscite,
               sum(case when m.segno = 'entrata' then m.importo
                        else -m.importo end) as saldo
        from movimento_bancario m
        left join iniziativa i on i.id = m.iniziativa_id
        group by 1 order by saldo desc
        """)


def scadenzario() -> list[dict]:
    """Documenti non saldati, ordinati per scadenza (poi data)."""
    return db.query("""
        select tipo, numero, data, data_scadenza, importo, controparte,
               stato_incasso_pagamento
        from documento_fiscale
        where stato_incasso_pagamento <> 'saldato'
        order by coalesce(data_scadenza, data)
        """)


# --- Export rendicontazione --------------------------------------------------


def ore_per_rendicontazione(
    iniziativa_id: UUID | str | None,
    persona_id: UUID | str | None,
    dal: date,
    al: date,
) -> list[dict]:
    """Ore a timesheet nel periodo, con persona e iniziativa (per l'export §8)."""
    sql = """
        select t.persona_id, p.nome || ' ' || p.cognome as persona,
               i.titolo as iniziativa, a.tipo_attivita, t.data, t.ore
        from timesheet_ora t
        join assegnazione a on a.id = t.assegnazione_id
        join iniziativa i on i.id = a.iniziativa_id
        join persona p on p.id = t.persona_id
        where t.data between %s and %s
    """
    params: list = [dal, al]
    if iniziativa_id:
        sql += " and i.id = %s"
        params.append(str(iniziativa_id))
    if persona_id:
        sql += " and t.persona_id = %s"
        params.append(str(persona_id))
    sql += " order by p.cognome, t.data"
    return db.query(sql, params)


def audit_recenti(limite: int = 200) -> list[dict]:
    return db.query(
        "select * from audit_log order by eseguito_il desc limit %s", (limite,)
    )
