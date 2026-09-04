"""Accesso dati per il cruscotto di sostenibilità (v3, solo admin)."""

from __future__ import annotations

from decimal import Decimal

from src.lib import db

# --- Parametri annuali ----------------------------------------------------------


def get_parametri(anno: int) -> dict:
    """Parametri finanziari dell'anno (default se assenti)."""
    row = db.query_one("select * from parametri_finanziari where anno = %s", (anno,))
    return row or {
        "anno": anno,
        "costi_fissi_mensili": None,
        "costo_personale_annuo": None,
        "costi_indiretti_annui": None,
        "teste_dirette": None,
        "ore_vendibili_fte": 1620,
        "aliquota_fiscale": Decimal("0.279"),
        "saldo_iniziale": None,
        "note": None,
    }


def salva_parametri(anno: int, **campi) -> None:
    ammessi = {
        "costi_fissi_mensili",
        "costo_personale_annuo",
        "costi_indiretti_annui",
        "teste_dirette",
        "ore_vendibili_fte",
        "aliquota_fiscale",
        "saldo_iniziale",
        "note",
    }
    campi = {k: v for k, v in campi.items() if k in ammessi}
    cols = ", ".join(campi)
    marks = ", ".join(["%s"] * len(campi))
    upd = ", ".join(f"{k} = excluded.{k}" for k in campi)
    db.execute(
        f"""
        insert into parametri_finanziari (anno, {cols}) values (%s, {marks})
        on conflict (anno) do update set {upd}
        """,
        [anno, *campi.values()],
    )


# --- Consuntivi -----------------------------------------------------------------


def entrate_uscite_anno(anno: int) -> dict:
    row = db.query_one(
        """
        select coalesce(sum(importo) filter (where segno = 'entrata'), 0) as entrate,
               coalesce(sum(importo) filter (where segno = 'uscita'), 0) as uscite
        from movimento_bancario
        where extract(year from data)::int = %s
        """,
        (anno,),
    )
    return {"entrate": Decimal(row["entrate"]), "uscite": Decimal(row["uscite"])}


def entrate_uscite_per_anno() -> list[dict]:
    return [
        {
            "anno": int(r["anno"]),
            "entrate": Decimal(r["entrate"]),
            "uscite": Decimal(r["uscite"]),
        }
        for r in db.query("""
            select extract(year from data)::int as anno,
                   coalesce(sum(importo) filter (where segno = 'entrata'), 0)
                       as entrate,
                   coalesce(sum(importo) filter (where segno = 'uscita'), 0) as uscite
            from movimento_bancario
            group by 1 order by 1
            """)
    ]


def ricavi_per_controparte(anno: int) -> dict[str, Decimal]:
    """Entrate dell'anno per controparte: la controparte dell'iniziativa
    riconciliata se c'è, altrimenti quella del movimento."""
    rows = db.query(
        """
        select coalesce(nullif(i.controparte, ''), nullif(m.controparte, ''),
                        '(sconosciuta)') as controparte,
               sum(m.importo) as tot
        from movimento_bancario m
        left join iniziativa i on i.id = m.iniziativa_id
        where m.segno = 'entrata' and extract(year from m.data)::int = %s
        group by 1
        """,
        (anno,),
    )
    return {r["controparte"]: Decimal(r["tot"]) for r in rows}


def ricavi_per_tipo(anno: int) -> dict[str, Decimal]:
    """Entrate dell'anno per tipo di ricavo dell'iniziativa riconciliata
    (non riconciliate -> 'agevolato', ipotesi prudenziale)."""
    rows = db.query(
        """
        select coalesce(i.tipo_ricavo, 'agevolato') as tipo, sum(m.importo) as tot
        from movimento_bancario m
        left join iniziativa i on i.id = m.iniziativa_id
        where m.segno = 'entrata' and extract(year from m.data)::int = %s
        group by 1
        """,
        (anno,),
    )
    return {r["tipo"]: Decimal(r["tot"]) for r in rows}


def incassato_per_iniziativa() -> dict[str, Decimal]:
    rows = db.query("""
        select iniziativa_id, sum(importo) as tot
        from movimento_bancario
        where segno = 'entrata' and iniziativa_id is not null
        group by 1
        """)
    return {str(r["iniziativa_id"]): Decimal(r["tot"]) for r in rows}


def residuo_contratti_firmati() -> tuple[Decimal, list[dict]]:
    """Backlog = Σ (finanziamento − incassato) sui progetti attivi.

    Ritorna (totale, dettaglio per progetto)."""
    incassato = incassato_per_iniziativa()
    rows = db.query("""
        select id, acronimo, codice, titolo, controparte, tipo_ricavo,
               coalesce(finanziamento_complessivo, budget_totale) as importo,
               data_inizio, data_fine
        from iniziativa
        where tipo = 'progetto' and stato = 'attivo'
        order by data_fine nulls last
        """)
    dettaglio = []
    tot = Decimal("0")
    for r in rows:
        imp = Decimal(r["importo"] or 0)
        inc = incassato.get(str(r["id"]), Decimal("0"))
        residuo = max(imp - inc, Decimal("0"))
        tot += residuo
        prefisso = r["acronimo"] or r["codice"]
        dettaglio.append(
            {
                "iniziativa_id": str(r["id"]),
                "etichetta": f"{prefisso} · {r['titolo']}" if prefisso else r["titolo"],
                "controparte": r["controparte"] or "",
                "tipo_ricavo": r["tipo_ricavo"] or "agevolato",
                "importo": imp,
                "incassato": inc,
                "residuo": residuo,
                "data_fine": r["data_fine"],
            }
        )
    return tot, dettaglio


def progetti_tariffa_implicita() -> list[dict]:
    """Per la KPI tariffa media: importo e ore pianificate dei progetti attivi."""
    return [
        {"importo": Decimal(r["importo"] or 0), "ore": Decimal(r["ore"] or 0)}
        for r in db.query("""
            select coalesce(i.finanziamento_complessivo, i.budget_totale) as importo,
                   coalesce(nullif(i.ore_totali, 0),
                            (select sum(a.ore_pianificate) from assegnazione a
                              where a.iniziativa_id = i.id)) as ore
            from iniziativa i
            where i.tipo = 'progetto' and i.stato = 'attivo'
            """)
    ]


def iniziative_pipeline() -> list[dict]:
    """Proposte vive con importo/probabilità/date (per gli scenari)."""
    return [
        {
            "id": str(r["id"]),
            "etichetta": (r["acronimo"] or r["codice"] or r["titolo"]),
            "importo": Decimal(r["importo"] or 0),
            "probabilita": Decimal(r["probabilita_successo"] or 0),
            "data_inizio": r["data_inizio"],
            "data_fine": r["data_fine"],
            "stato": r["stato"],
            "controparte": r["controparte"] or "",
            "tipo_ricavo": r["tipo_ricavo"] or "agevolato",
        }
        for r in db.query("""
            select id, acronimo, codice, titolo, controparte, tipo_ricavo, stato,
                   coalesce(finanziamento_complessivo, budget_totale) as importo,
                   probabilita_successo, data_inizio, data_fine
            from iniziativa
            where tipo = 'proposta' and stato in ('bozza','inviata')
            """)
    ]


def persone_costo() -> list[dict]:
    """Persone (attive) con monte ore e contratto per il costo mensile previsto."""
    return [
        {
            "id": str(r["id"]),
            "nome": r["nome"],
            "attivo": r["attivo"],
            "monte_ore_annuo": r["monte_ore_annuo"],
            "contratto_data_inizio": r["contratto_data_inizio"],
            "contratto_data_fine": r["contratto_data_fine"],
        }
        for r in db.query("""
            select id, nome || ' ' || cognome as nome, attivo, monte_ore_annuo,
                   contratto_data_inizio, contratto_data_fine
            from persona where attivo
            """)
    ]


def uscite_previste_residuo_anno(
    anno: int, mesi_previsti: dict, entrate_previste: dict
) -> dict:
    """Somma dei mesi dell'anno ancora da venire in due dizionari {(a,m): €}."""
    from datetime import date

    oggi = date.today()
    e = sum(
        (
            v
            for (a, m), v in entrate_previste.items()
            if a == anno and (a, m) >= (oggi.year, oggi.month)
        ),
        Decimal("0"),
    )
    u = sum(
        (
            v
            for (a, m), v in mesi_previsti.items()
            if a == anno and (a, m) >= (oggi.year, oggi.month)
        ),
        Decimal("0"),
    )
    return {"entrate": e, "uscite": u}
