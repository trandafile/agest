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


def import_movimenti(
    righe: list[dict],
    eseguito_da: str | None = None,
    anno_riferimento: int | None = None,
) -> int:
    """Import movimenti; se `progetto_label` combacia con acronimo/codice/titolo
    di un'iniziativa, riconcilia automaticamente. `anno_riferimento` (l'anno del
    foglio Libro Cassa d'origine) è usato per l'aggregazione dell'export."""
    iniziative = db.query("select id, codice, acronimo, titolo from iniziativa")
    per_label: dict[str, str] = {}
    for i in iniziative:
        for campo in ("acronimo", "codice", "titolo"):
            if i[campo]:
                per_label[i[campo].strip().lower()] = str(i["id"])

    n = 0
    for r in righe:
        label = (r.get("progetto_label") or "").strip()
        ini_id = per_label.get(label.lower()) if label else None
        anno = anno_riferimento or (r["data"].year if r.get("data") else None)
        db.execute(
            """
            insert into movimento_bancario
                (data, importo, segno, descrizione, controparte, categoria,
                 n_fattura, persona_contatto, note, progetto_label,
                 iniziativa_id, anno_riferimento)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                r["data"],
                r["importo"],
                r["segno"],
                r.get("descrizione"),
                r.get("controparte"),
                r.get("categoria"),
                r.get("n_fattura"),
                r.get("persona_contatto"),
                r.get("note"),
                label or None,
                ini_id,
                anno,
            ),
            user_email=eseguito_da,
        )
        n += 1
    return n


def saldo_attuale() -> float:
    row = db.query_one("""
        select coalesce(sum(case when segno = 'entrata' then importo
                                 else -importo end), 0) as saldo
        from movimento_bancario
        """)
    return float(row["saldo"])


def uscite_ricorrenti_stima(n_mesi: int = 3) -> float:
    """Media mensile delle uscite negli ultimi `n_mesi` mesi pieni."""
    row = db.query_one(
        """
        with mesi as (
            select date_trunc('month', data) as m, sum(importo) as uscite
            from movimento_bancario
            where segno = 'uscita'
              and data >= date_trunc('month', now()) - make_interval(months => %s)
              and data <  date_trunc('month', now())
            group by 1
        )
        select coalesce(avg(uscite), 0) as media from mesi
        """,
        (n_mesi,),
    )
    return float(row["media"])


def uscite_per_categoria(anno: int) -> list[dict]:
    return db.query(
        """
        select coalesce(categoria, '(senza categoria)') as categoria,
               sum(importo) as tot
        from movimento_bancario
        where segno = 'uscita' and extract(year from data)::int = %s
        group by 1 order by tot desc
        """,
        (anno,),
    )


def entrate_programmate_mensili() -> list[dict]:
    """Incassi attesi per mese: documenti attivi aperti + milestone previste."""
    return db.query("""
        select extract(year from scad)::int as anno,
               extract(month from scad)::int as mese, sum(importo) as tot
        from (
            select coalesce(data_scadenza, data) as scad, importo
            from documento_fiscale
            where tipo = 'attiva' and stato_incasso_pagamento <> 'saldato'
            union all
            select data_prevista, importo_incasso
            from milestone
            where stato = 'prevista' and genera_pagamento
              and importo_incasso is not null and data_prevista is not null
        ) x
        where scad >= date_trunc('month', now())
        group by 1, 2 order by 1, 2
        """)


def uscite_programmate_mensili() -> list[dict]:
    """Pagamenti attesi per mese: documenti passivi aperti."""
    return db.query("""
        select extract(year from coalesce(data_scadenza, data))::int as anno,
               extract(month from coalesce(data_scadenza, data))::int as mese,
               sum(importo) as tot
        from documento_fiscale
        where tipo = 'passiva' and stato_incasso_pagamento <> 'saldato'
          and coalesce(data_scadenza, data) >= date_trunc('month', now())
        group by 1, 2 order by 1, 2
        """)


def hash_gia_importato(file_hash: str) -> bool:
    return (
        db.query_one(
            "select 1 as x from import_bancario where file_hash = %s", (file_hash,)
        )
        is not None
    )


def registra_import(
    anno: int,
    mese: int,
    file_name: str,
    file_hash: str,
    n_movimenti: int,
    caricato_da: str | None,
) -> None:
    db.execute(
        """
        insert into import_bancario
            (anno, mese, file_name, file_hash, n_movimenti, caricato_da)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (anno, mese, file_name, file_hash, n_movimenti, caricato_da),
        user_email=caricato_da,
    )


def list_import_bancari() -> list[dict]:
    return db.query("select * from import_bancario order by caricato_il desc limit 50")


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


# --- Movimenti previsti (calendario per progetto) --------------------------------


def list_movimenti_previsti(iniziativa_id: UUID | str) -> list[dict]:
    return db.query(
        "select * from movimento_previsto where iniziativa_id = %s "
        "order by data_attesa nulls last",
        (str(iniziativa_id),),
    )


def create_movimento_previsto(
    iniziativa_id: UUID | str,
    segno: str,
    importo: float,
    descrizione: str | None = None,
    data_attesa: date | None = None,
    completata: bool = False,
) -> None:
    db.execute(
        """
        insert into movimento_previsto
            (iniziativa_id, segno, importo, descrizione, data_attesa, completata)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (str(iniziativa_id), segno, importo, descrizione, data_attesa, completata),
    )


def toggle_previsto_completato(mov_id: UUID | str, completata: bool) -> None:
    db.execute(
        "update movimento_previsto set completata = %s where id = %s",
        (completata, str(mov_id)),
    )


def delete_movimento_previsto(mov_id: UUID | str) -> None:
    db.execute("delete from movimento_previsto where id = %s", (str(mov_id),))


def previsti_programmati_mensili() -> list[dict]:
    """Movimenti previsti NON completati, aggregati per mese e segno.

    Alimentano la proiezione di cassa insieme ai documenti fiscali aperti.
    """
    return db.query("""
        select extract(year from data_attesa)::int as anno,
               extract(month from data_attesa)::int as mese, segno,
               sum(importo) as tot
        from movimento_previsto
        where not completata and data_attesa is not null
          and data_attesa >= date_trunc('month', now())
        group by 1, 2, 3 order by 1, 2
        """)


# --- Spese periodiche ----------------------------------------------------------------


def list_spese_periodiche() -> list[dict]:
    return db.query("select * from spesa_periodica order by descrizione")


def create_spesa_periodica(
    descrizione: str,
    importo: float | None = None,
    tipologia: str | None = None,
    periodicita: str | None = None,
    iniziativa_id: UUID | str | None = None,
    progetto_label: str | None = None,
    dal: date | None = None,
    al: date | None = None,
) -> None:
    db.execute(
        """
        insert into spesa_periodica
            (descrizione, importo, tipologia, periodicita, iniziativa_id,
             progetto_label, dal, al)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            descrizione,
            importo,
            tipologia,
            periodicita,
            str(iniziativa_id) if iniziativa_id else None,
            progetto_label,
            dal,
            al,
        ),
    )


def delete_spesa_periodica(sp_id: UUID | str) -> None:
    db.execute("delete from spesa_periodica where id = %s", (str(sp_id),))


# --- Manutenzione / import una-tantum ------------------------------------------------


def importa_libro_cassa(
    sezioni: dict, clear: bool = False, eseguito_da: str | None = None
) -> dict:
    """Importa le sezioni di `import_contabile.leggi_workbook` (progetti,
    calendari, spese periodiche, libri cassa) nel DB. Ritorna i conteggi.

    Crea/aggiorna i progetti per acronimo, importa i movimenti previsti, le
    spese periodiche e i movimenti bancari (riconciliati per acronimo).
    """
    from src.data import iniziativa_repo  # lazy: evita import circolare

    esiti = {
        "clear": None,
        "progetti": 0,
        "previsti": 0,
        "spese_periodiche": 0,
        "movimenti": 0,
    }
    if clear:
        esiti["clear"] = svuota_dati_contabili(eseguito_da=eseguito_da)

    id_by_acr: dict[str, str] = {}
    for acr, dati in sezioni["progetti"].items():
        info = dati["info"]
        campi = dict(
            acronimo=acr,
            titolo=info.get("nome_esteso") or acr,
            codice=acr,
            controparte=info.get("ente_finanziatore"),
            costo_complessivo=info.get("costo_complessivo"),
            finanziamento_complessivo=info.get("finanziamento_complessivo"),
            data_inizio=info.get("data_inizio"),
            data_fine=info.get("data_fine"),
        )
        esistente = iniziativa_repo.get_by_acronimo(acr)
        ini = (
            iniziativa_repo.update_iniziativa(esistente.id, **campi)
            if esistente
            else iniziativa_repo.create_iniziativa(
                tipo="progetto", stato="attivo", **campi
            )
        )
        id_by_acr[acr.lower()] = str(ini.id)
        esiti["progetti"] += 1
        for m in dati["calendario"]:
            create_movimento_previsto(
                ini.id,
                segno=m["segno"],
                importo=float(m["importo"]),
                descrizione=m["descrizione"],
                data_attesa=m["data_attesa"],
                completata=m["completata"],
            )
            esiti["previsti"] += 1

    for s in sezioni["spese_periodiche"]:
        ini_id = id_by_acr.get((s.get("progetto_label") or "").lower())
        create_spesa_periodica(
            descrizione=s["descrizione"] or "-",
            importo=float(s["importo"]) if s["importo"] is not None else None,
            tipologia=s["tipologia"],
            periodicita=s["periodicita"],
            iniziativa_id=ini_id,
            progetto_label=s["progetto_label"],
            dal=s["dal"],
            al=s["al"],
        )
        esiti["spese_periodiche"] += 1

    for anno, movs in sezioni["libri"].items():
        n = import_movimenti(movs, eseguito_da=eseguito_da, anno_riferimento=anno)
        registra_import(
            anno or 0,
            12,
            f"Libro Cassa {anno}",
            f"libro-cassa-{anno}",
            n,
            eseguito_da,
        )
        esiti["movimenti"] += n
    return esiti


def movimenti_per_anno() -> dict:
    """{anno: [movimento dict]} per l'export Libro Cassa.

    Usa `anno_riferimento` (foglio d'origine) con fallback all'anno della data.
    """
    rows = db.query("select * from movimento_bancario order by data")
    out: dict = {}
    for r in rows:
        anno = r.get("anno_riferimento") or r["data"].year
        out.setdefault(anno, []).append(r)
    return out


def acronimi_by_iniziativa() -> dict:
    """{iniziativa_id(str): acronimo} per la colonna Progetto dell'export."""
    rows = db.query(
        "select id, acronimo, codice from iniziativa where acronimo is not null"
    )
    return {str(r["id"]): r["acronimo"] for r in rows}


def svuota_dati_contabili(eseguito_da: str | None = None) -> dict:
    """Cancella movimenti bancari, previsti, spese periodiche e log import.

    Ritorna i conteggi eliminati. Operazione distruttiva: la UI deve chiedere
    conferma esplicita.
    """
    conteggi = {}
    for tabella in (
        "movimento_bancario",
        "movimento_previsto",
        "spesa_periodica",
        "import_bancario",
    ):
        n = db.query_one(f"select count(*) as n from {tabella}")["n"]
        conteggi[tabella] = n
        db.execute(f"delete from {tabella}", user_email=eseguito_da)
    return conteggi
