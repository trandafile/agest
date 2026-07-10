"""Accesso dati per le missioni (trasferte) e le loro spese."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from src.domain.models import Missione, MissioneSpesa
from src.lib import db

_UPDATABLE = {
    "iniziativa_id",
    "persona_id",
    "destinazione",
    "data_inizio",
    "data_fine",
    "obiettivo",
    "spesa_prevista",
    "stato",
}


def _to_missione(row: dict) -> Missione:
    return Missione.model_validate(row)


# --- Missioni ---------------------------------------------------------------


def list_missioni(
    iniziativa_id: UUID | str | None = None,
    persona_id: UUID | str | None = None,
    stati: list[str] | None = None,
) -> list[Missione]:
    sql = "select * from missione"
    cond, params = [], []
    if iniziativa_id:
        cond.append("iniziativa_id = %s")
        params.append(str(iniziativa_id))
    if persona_id:
        cond.append("persona_id = %s")
        params.append(str(persona_id))
    if stati:
        cond.append("stato = any(%s)")
        params.append(list(stati))
    if cond:
        sql += " where " + " and ".join(cond)
    sql += " order by data_inizio desc, destinazione"
    return [_to_missione(r) for r in db.query(sql, params)]


def get_missione(missione_id: UUID | str) -> Missione | None:
    row = db.query_one("select * from missione where id = %s", (str(missione_id),))
    return _to_missione(row) if row else None


def create_missione(
    persona_id: UUID | str,
    destinazione: str,
    data_inizio: date,
    data_fine: date,
    iniziativa_id: UUID | str | None = None,
    obiettivo: str | None = None,
    spesa_prevista: Decimal | float | None = None,
) -> Missione:
    row = db.execute(
        """
        insert into missione
            (persona_id, destinazione, data_inizio, data_fine,
             iniziativa_id, obiettivo, spesa_prevista)
        values (%s, %s, %s, %s, %s, %s, %s)
        returning *
        """,
        (
            str(persona_id),
            destinazione.strip(),
            data_inizio,
            data_fine,
            str(iniziativa_id) if iniziativa_id else None,
            obiettivo,
            spesa_prevista,
        ),
    )[0]
    return _to_missione(row)


def update_missione(missione_id: UUID | str, **campi) -> Missione:
    campi = {k: v for k, v in campi.items() if k in _UPDATABLE}
    if not campi:
        raise ValueError("Nessun campo aggiornabile fornito.")
    set_clause = ", ".join(f"{k} = %s" for k in campi)
    params = [str(v) if isinstance(v, UUID) else v for v in campi.values()]
    params.append(str(missione_id))
    row = db.execute(
        f"update missione set {set_clause} where id = %s returning *", params
    )[0]
    return _to_missione(row)


def delete_missione(missione_id: UUID | str) -> None:
    """Elimina la missione (le spese cadono in cascata) e i suoi commenti."""
    from src.data import commento_repo

    commento_repo.delete_commenti_di("missione", missione_id)
    db.execute("delete from missione where id = %s", (str(missione_id),))


# --- Flusso di autorizzazione ----------------------------------------------


def invia_richiesta(missione_id: UUID | str) -> Missione:
    """Bozza/respinta -> richiesta (in attesa dell'autorizzazione admin)."""
    row = db.execute(
        """
        update missione set stato = 'richiesta',
               autorizzata_da = null, autorizzata_il = null
        where id = %s and stato in ('bozza','respinta')
        returning *
        """,
        (str(missione_id),),
    )
    if not row:
        raise ValueError("La missione non e' in stato bozza/respinta.")
    return _to_missione(row[0])


def autorizza(
    missione_id: UUID | str,
    admin_id: UUID | str,
    note: str | None = None,
    eseguito_da: str | None = None,
) -> Missione:
    row = db.execute(
        """
        update missione
           set stato = 'autorizzata', autorizzata_da = %s,
               autorizzata_il = now(), note_autorizzazione = %s
         where id = %s and stato = 'richiesta'
        returning *
        """,
        (str(admin_id), note, str(missione_id)),
        user_email=eseguito_da,
    )
    if not row:
        raise ValueError("Solo una missione 'richiesta' puo' essere autorizzata.")
    return _to_missione(row[0])


def respingi(
    missione_id: UUID | str,
    admin_id: UUID | str,
    note: str | None = None,
    eseguito_da: str | None = None,
) -> Missione:
    row = db.execute(
        """
        update missione
           set stato = 'respinta', autorizzata_da = %s,
               autorizzata_il = now(), note_autorizzazione = %s
         where id = %s and stato = 'richiesta'
        returning *
        """,
        (str(admin_id), note, str(missione_id)),
        user_email=eseguito_da,
    )
    if not row:
        raise ValueError("Solo una missione 'richiesta' puo' essere respinta.")
    return _to_missione(row[0])


def richiedi_rimborso(missione_id: UUID | str) -> Missione:
    row = db.execute(
        """
        update missione set rimborso_stato = 'richiesto',
               rimborso_richiesto_il = now()
         where id = %s and stato in ('autorizzata','conclusa')
           and rimborso_stato = 'non_richiesto'
           and exists (select 1 from missione_spesa where missione_id = %s)
        returning *
        """,
        (str(missione_id), str(missione_id)),
    )
    if not row:
        raise ValueError(
            "Rimborso richiedibile solo su missione autorizzata, con spese "
            "inserite e non gia' richiesto."
        )
    return _to_missione(row[0])


def liquida_rimborso(
    missione_id: UUID | str, eseguito_da: str | None = None
) -> Missione:
    row = db.execute(
        """
        update missione set rimborso_stato = 'liquidato',
               rimborso_liquidato_il = now(), stato = 'conclusa'
         where id = %s and rimborso_stato = 'richiesto'
        returning *
        """,
        (str(missione_id),),
        user_email=eseguito_da,
    )
    if not row:
        raise ValueError("Nessun rimborso in attesa di liquidazione.")
    return _to_missione(row[0])


# --- Spese ------------------------------------------------------------------


def list_spese(missione_id: UUID | str) -> list[MissioneSpesa]:
    rows = db.query(
        "select * from missione_spesa where missione_id = %s order by data, categoria",
        (str(missione_id),),
    )
    return [MissioneSpesa.model_validate(r) for r in rows]


def add_spesa(
    missione_id: UUID | str,
    data: date,
    categoria: str,
    importo: Decimal | float,
    descrizione: str | None = None,
) -> MissioneSpesa:
    row = db.execute(
        """
        insert into missione_spesa (missione_id, data, categoria, importo, descrizione)
        values (%s, %s, %s, %s, %s)
        returning *
        """,
        (str(missione_id), data, categoria, importo, descrizione),
    )[0]
    return MissioneSpesa.model_validate(row)


def delete_spesa(spesa_id: UUID | str) -> None:
    db.execute("delete from missione_spesa where id = %s", (str(spesa_id),))


def totali_per_missione(missione_ids: list[str] | None = None) -> dict[str, Decimal]:
    """{missione_id: totale speso} — per le liste, senza N+1 query."""
    if missione_ids is not None and not missione_ids:
        return {}
    sql = "select missione_id, sum(importo) as tot from missione_spesa"
    params: list = []
    if missione_ids:
        sql += " where missione_id = any(%s)"
        params.append([str(i) for i in missione_ids])
    sql += " group by missione_id"
    return {str(r["missione_id"]): r["tot"] for r in db.query(sql, params)}
