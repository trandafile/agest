"""Assemblaggio dei «pack» per le presentazioni (v3).

Legge dai repository e produce dizionari puri consumati da
`src/lib/pptx_report.py`. Tre pack: attività, finanziario, progetto.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.data import (
    calendario_repo,
    deliverable_repo,
    finanza_repo,
    iniziativa_repo,
    persona_repo,
    portfolio_repo,
    progetti_repo,
    task_repo,
)
from src.domain.economia import (
    PianoPersona,
    consuntivo_personale,
    quote_rimanenti,
    rollup_personale,
)
from src.domain.portfolio import anni_portfolio, quota_per_anno, ricavi_per_anno
from src.lib.labels import etichetta_progetto, getf

ATTIVI = ("da_fare", "in_corso", "bloccato")


def _categoria(i) -> str:
    if i.tipo == "progetto":
        return "Progetto attivo" if i.stato == "attivo" else "Progetto chiuso"
    return "Proposta inviata" if i.stato == "inviata" else "Proposta in bozza"


def _meta(persona) -> str:
    return (
        f"ANTECNICA · {date.today():%d/%m/%Y} · generato da agest per "
        f"{persona.nome_completo}"
    )


def _gantt(iniziative, con_milestone: bool = True) -> tuple[list[dict], list[int]]:
    righe = []
    for i in sorted(iniziative, key=lambda x: (x.data_inizio or date.max, x.titolo)):
        if not (i.data_inizio and i.data_fine):
            continue
        ms = []
        if con_milestone and i.tipo == "progetto":
            ms = [
                m.data_prevista
                for m in progetti_repo.list_milestones(i.id)
                if m.data_prevista
            ]
        righe.append(
            {
                "etichetta": etichetta_progetto(i),
                "inizio": i.data_inizio,
                "fine": i.data_fine,
                "categoria": _categoria(i),
                "milestone": ms,
            }
        )
    anni = anni_portfolio(
        [{"data_inizio": i.data_inizio, "data_fine": i.data_fine} for i in iniziative]
    )
    return righe, anni


def _albero(ini_id, tasks, nomi, delivs) -> tuple[list[dict], list[dict]]:
    """(deliverables con task/subtask, task liberi) di un'iniziativa."""
    figli: dict = {}
    for t in tasks:
        if t.parent_task_id:
            figli.setdefault(t.parent_task_id, []).append(t)

    def _t(t) -> dict:
        return {
            "titolo": t.titolo,
            "stato": t.stato,
            "scadenza": t.scadenza,
            "owner": nomi.get(t.owner_id, "—"),
            "subtasks": [
                {
                    "titolo": s.titolo,
                    "stato": s.stato,
                    "scadenza": s.scadenza,
                    "owner": nomi.get(s.owner_id, "—"),
                }
                for s in sorted(
                    figli.get(t.id, []), key=lambda x: (x.scadenza or date.max)
                )
            ],
        }

    ini_tasks = [t for t in tasks if t.iniziativa_id == ini_id and not t.parent_task_id]
    out_d = []
    for d in delivs:
        out_d.append(
            {
                "titolo": d.titolo,
                "tipo": d.tipo,
                "stato": d.stato,
                "scadenza": d.scadenza,
                "owner": nomi.get(d.owner_id, "—"),
                "tasks": [
                    _t(t)
                    for t in sorted(
                        (x for x in ini_tasks if x.deliverable_id == d.id),
                        key=lambda x: (x.scadenza or date.max),
                    )
                ],
            }
        )
    liberi = [
        _t(t)
        for t in sorted(
            (x for x in ini_tasks if not x.deliverable_id),
            key=lambda x: (x.scadenza or date.max),
        )
    ]
    return out_d, liberi


def pack_attivita(persona, solo_mie: bool = False, periodo_giorni: int = 30) -> dict:
    """Report attività: portafoglio, progetti (albero), persone, scadenze."""
    oggi = date.today()
    da = oggi - timedelta(days=periodo_giorni)
    persone = persona_repo.list_persone()
    nomi = {p.id: p.nome_completo for p in persone}
    iniziative = iniziativa_repo.list_iniziative()
    vive = [
        i
        for i in iniziative
        if (i.tipo == "progetto" and i.stato == "attivo")
        or (i.tipo == "proposta" and i.stato in ("bozza", "inviata"))
    ]
    tasks = task_repo.list_tasks(include_archiviati=False)
    if solo_mie:
        miei = {t.id for t in tasks if persona.id in (t.owner_id, t.supervisor_id)}
        # includi i padri dei miei subtask e i figli dei miei task
        tasks = [
            t
            for t in tasks
            if t.id in miei
            or t.parent_task_id in miei
            or any(x.parent_task_id == t.id for x in tasks if x.id in miei)
        ]
    attivi = [t for t in tasks if t.stato in ATTIVI]
    in_ritardo = [t for t in attivi if t.scadenza and t.scadenza < oggi]
    completati = [
        t
        for t in tasks
        if t.stato == "completato" and t.completato_il and t.completato_il >= da
    ]
    try:
        from src.data import task_storico_repo

        cont = task_storico_repo.contatori(periodo_giorni)
        avviati = cont["avviati"]
    except Exception:  # noqa: BLE001 — migrazione 0015 non ancora applicata
        avviati = 0
    delivs_all = {i.id: deliverable_repo.list_deliverables(i.id) for i in vive}
    aperti = sum(1 for ds in delivs_all.values() for d in ds if d.stato in ATTIVI)
    eventi = calendario_repo.eventi()
    scadenze = [
        e for e in eventi if e["data"] and e["data"] <= oggi + timedelta(days=60)
    ]
    if solo_mie:
        scadenze = [e for e in scadenze if e.get("owner_id") == persona.id]

    gantt, anni = _gantt(vive)
    progetti = []
    for i in vive:
        ds, liberi = _albero(i.id, tasks, nomi, delivs_all.get(i.id, []))
        milestone = [
            {"titolo": m.titolo, "data": m.data_prevista, "stato": m.stato}
            for m in (
                progetti_repo.list_milestones(i.id) if i.tipo == "progetto" else []
            )
        ]
        if not ds and not liberi and (solo_mie or not milestone):
            continue  # niente da mostrare: evita slide vuote
        progetti.append(
            {
                "etichetta": etichetta_progetto(i),
                "controparte": i.controparte,
                "stato": (
                    ("attivo" if i.stato == "attivo" else i.stato)
                    if i.tipo == "progetto"
                    else f"proposta {i.stato}"
                ),
                "inizio": i.data_inizio,
                "fine": i.data_fine,
                "milestone": milestone,
                "deliverables": ds,
                "task_liberi": liberi,
            }
        )

    persone_out = []
    for p in persone if not solo_mie else [persona]:
        miei = [t for t in tasks if t.owner_id == p.id]
        if not miei:
            continue
        att = [t for t in miei if t.stato in ATTIVI]
        rit = [t for t in att if t.scadenza and t.scadenza < oggi]
        blocc = [t for t in att if t.stato == "bloccato"]
        comp = [
            t
            for t in miei
            if t.stato == "completato" and t.completato_il and t.completato_il >= da
        ]
        con_scad = [
            t
            for t in miei
            if t.stato == "completato" and t.completato_il and t.scadenza
        ]
        punt = sum(1 for t in con_scad if t.completato_il <= t.scadenza)
        in_corso = [t for t in att if t.stato == "in_corso" and t not in rit]
        persone_out.append(
            {
                "nome": p.nome_completo,
                "attivi": len(att),
                "in_ritardo": len(rit),
                "bloccati": len(blocc),
                "completati_periodo": len(comp),
                "puntualita": f"{punt / len(con_scad) * 100:.0f}%" if con_scad else "—",
                "completati": [t.titolo for t in comp],
                "in_corso": [t.titolo for t in in_corso],
                "ritardo": [f"{t.titolo} ({t.scadenza:%d/%m})" for t in rit],
                "bloccati_lista": [t.titolo for t in blocc if t not in rit],
                "altri_sx": max(len(comp) + len(in_corso) - 12, 0),
                "altri_dx": max(len(rit) + len(blocc) - 12, 0),
            }
        )

    return {
        "titolo": (
            "Report attività"
            if not solo_mie
            else f"Le mie attività — {persona.nome_completo}"
        ),
        "sottotitolo": "Stato di progetti, deliverable e task"
        + ("" if not solo_mie else " (task di cui sono owner/supervisor)"),
        "meta": _meta(persona),
        "oggi": oggi,
        "periodo_giorni": periodo_giorni,
        "anni": anni,
        "gantt": gantt,
        "sintesi": {
            "progetti_attivi": sum(1 for i in vive if i.tipo == "progetto"),
            "deliverable_aperti": aperti,
            "task_attivi": len(attivi),
            "in_ritardo": len(in_ritardo),
            "bloccati": sum(1 for t in attivi if t.stato == "bloccato"),
            "completati_periodo": len(completati),
            "avviati_periodo": avviati,
            "scadenze_30": sum(
                1 for e in scadenze if oggi <= e["data"] <= oggi + timedelta(days=30)
            ),
        },
        "progetti": progetti,
        "persone": persone_out,
        "scadenze": [
            {
                "data": e["data"],
                "tipo": e["tipo"],
                "titolo": e["titolo"],
                "progetto": e.get("progetto") or "",
                "owner": nomi.get(e.get("owner_id"), ""),
            }
            for e in scadenze
        ],
    }


def pack_finanziario(
    persona, anno: int, n_mesi: int = 24, base_scelta: str | None = None
) -> dict:
    """Report finanziario (solo amministratore) dal calcolo condiviso."""
    from src.lib.sostenibilita_calc import calcola

    c = calcola(anno, n_mesi, base_scelta)
    cf = finanza_repo.cash_flow_mensile(anno)
    iniziative = iniziativa_repo.list_iniziative()
    vive = [
        i
        for i in iniziative
        if (i.tipo == "progetto" and i.stato == "attivo")
        or (i.tipo == "proposta" and i.stato in ("bozza", "inviata"))
    ]
    ric = ricavi_per_anno(
        [
            {
                "id": i.id,
                "etichetta": etichetta_progetto(i),
                "tipo": i.tipo,
                "stato": i.stato,
                "importo": getf(i, "importo_riferimento"),
                "probabilita": i.probabilita_successo,
                "data_inizio": i.data_inizio,
                "data_fine": i.data_fine,
            }
            for i in vive
        ]
    )
    anni_r = sorted({r["anno"] for r in ric if r["anno"] >= anno})[:5]
    serie: dict[str, list] = {}
    for r in ric:
        if r["anno"] in anni_r:
            serie.setdefault(r["etichetta"], [0.0] * len(anni_r))[
                anni_r.index(r["anno"])
            ] += float(r["importo"])
    scad = finanza_repo.scadenzario()
    return {
        "anno": anno,
        "titolo": "Report finanziario",
        "sottotitolo": (
            f"Sostenibilità economica {anno} — riservato all'amministrazione"
        ),
        "meta": _meta(persona),
        "kpi": [
            {
                "nome": k.nome,
                "valore_txt": k.valore_txt,
                "allarme": k.allarme,
                "target": k.target,
                "stato": k.stato,
                "descrizione": k.descrizione,
            }
            for k in c["kpis"]
        ],
        "saldo": c["saldo"],
        "saldo_nota": (
            "verificato" if c["saldo_verificato"] else "da movimenti importati"
        ),
        "costi_mensili": c["costi_mensili"],
        "base_costi": c["opzioni_base"][c["base_scelta"]].split(" (")[0],
        "backlog": c["backlog_tot"],
        "pipeline_pesata": sum(c["pipe_pesata"].values(), Decimal("0")),
        "cash_flow": {
            "mesi": [f"{r['mese']:02d}" for r in cf],
            "entrate": [float(r["entrate"]) for r in cf],
            "uscite": [float(r["uscite"]) for r in cf],
        },
        "scenari": {
            "mesi": [f"{a}-{m:02d}" for (a, m) in c["mesi"]],
            **{k: [float(r["saldo"]) for r in v] for k, v in c["scenari"].items()},
        },
        "scenari_nota": f"Base costi: {c['opzioni_base'][c['base_scelta']]}.",
        "totali_anno": c["totali_anno"],
        "storico_anni": [
            r
            for r in __import__(
                "src.data.sostenibilita_repo", fromlist=["x"]
            ).entrate_uscite_per_anno()
            if r["anno"] >= anno - 4
        ],
        "backlog_det": c["backlog_det"],
        "pnl": finanza_repo.pnl_per_progetto(),
        "ricavi_anno": (
            {"anni": [str(a) for a in anni_r], "serie": serie} if serie else None
        ),
        "stima": c["stima"],
        "scadenzario": [
            {
                "scadenza": s["data_scadenza"] or s["data"],
                "tipo": s["tipo"],
                "numero": s["numero"] or "",
                "controparte": s["controparte"] or "",
                "importo": s["importo"],
                "stato": s["stato_incasso_pagamento"],
            }
            for s in scad[:14]
        ],
    }


def pack_progetto(persona, iniziativa, economia: bool) -> dict:
    """Report di un singolo progetto (SAL); importi solo se `economia`."""
    oggi = date.today()
    nomi = {p.id: p.nome_completo for p in persona_repo.list_persone()}
    tasks = task_repo.list_tasks(include_archiviati=False, iniziativa_id=iniziativa.id)
    delivs = deliverable_repo.list_deliverables(iniziativa.id)
    ds, liberi = _albero(iniziativa.id, tasks, nomi, delivs)
    ms = progetti_repo.list_milestones(iniziativa.id)
    attivi = [t for t in tasks if t.stato in ATTIVI]

    piani_rows = progetti_repo.piani_iniziativa(iniziativa.id)
    ore_cons = progetti_repo.ore_consuntivo(iniziativa.id)
    cons_per_persona: dict[str, int] = {}
    for pid, _d, ore in ore_cons:
        cons_per_persona[pid] = cons_per_persona.get(pid, 0) + ore
    piani_anno = (
        portfolio_repo.piani_ore_anno(iniziativa.id)
        if _tabella_esiste("piano_ore_anno")
        else {}
    )
    anni_ore = (
        list(range(iniziativa.data_inizio.year, iniziativa.data_fine.year + 1))
        if iniziativa.data_inizio and iniziativa.data_fine
        else []
    )
    ore_persone = []
    for r in piani_rows:
        esplicito = {a: piani_anno.get((str(r["id"]), a)) for a in anni_ore}
        if any(v is not None for v in esplicito.values()):
            per_anno = {a: float(v or 0) for a, v in esplicito.items()}
        else:
            q = quota_per_anno(
                iniziativa.data_inizio,
                iniziativa.data_fine,
                r["ore_pianificate"],
                Decimal("0.1"),
            )
            per_anno = {a: float(q.get(a, 0)) for a in anni_ore}
        ore_persone.append(
            {
                "nome": r["nome"],
                "pianificate": float(r["ore_pianificate"] or 0),
                "anni": per_anno,
                "consuntivo": cons_per_persona.get(str(r["persona_id"]), 0),
            }
        )

    pack = {
        "etichetta": etichetta_progetto(iniziativa),
        "titolo": iniziativa.titolo,
        "meta": _meta(persona),
        "oggi": oggi,
        "economia": economia,
        "controparte": iniziativa.controparte,
        "cup": f"CUP {iniziativa.cup}" if getf(iniziativa, "cup") else None,
        "inizio": iniziativa.data_inizio,
        "fine": iniziativa.data_fine,
        "ore_timesheet": sum(o for (_, _, o) in ore_cons),
        "deliverable_completati": sum(1 for d in delivs if d.stato == "completato"),
        "deliverable_totali": len(delivs),
        "task_completati": sum(1 for t in tasks if t.stato == "completato"),
        "task_totali": len(tasks),
        "in_ritardo": sum(1 for t in attivi if t.scadenza and t.scadenza < oggi),
        "gantt": _gantt([iniziativa])[0],
        "anni": anni_ore or [oggi.year],
        "milestone": [
            {
                "titolo": m.titolo,
                "data": m.data_prevista,
                "stato": m.stato,
                "pagamento": bool(getf(m, "genera_pagamento")),
                "importo": m.importo_incasso,
            }
            for m in ms
        ],
        "deliverables": ds,
        "task_liberi": liberi,
        "ore_persone": ore_persone,
        "anni_ore": anni_ore,
    }
    if economia:
        piani = [
            PianoPersona(
                persona_id=str(r["persona_id"]),
                nome=r["nome"],
                tipo_attivita=r["tipo_attivita"],
                ore=Decimal(r["ore_pianificate"] or 0),
                work_package=r["work_package"],
            )
            for r in piani_rows
        ]
        tariffe = progetti_repo.tariffe_by_persona(
            [p.persona_id for p in piani] or None
        )
        roll = rollup_personale(piani, tariffe, iniziativa.data_inizio or oggi)
        costo_cons = consuntivo_personale(ore_cons, tariffe)
        budget_cat = progetti_repo.budget_per_categoria(iniziativa.id)
        speso_cat = progetti_repo.speso_per_categoria(iniziativa.id)
        if "personale" not in budget_cat and roll["totale"] > 0:
            budget_cat["personale"] = roll["totale"]
        quote = quote_rimanenti(
            budget=budget_cat,
            impegnato={},
            speso={
                **speso_cat,
                "personale": speso_cat.get("personale", Decimal("0")) + costo_cons,
            },
        )
        tot_b = sum(q["budget"] for q in quote.values())
        tot_s = sum(q["speso"] for q in quote.values())
        pack.update(
            {
                "budget": tot_b,
                "speso": tot_s,
                "rimanente": tot_b - tot_s,
                "avanzamento_pct": float(tot_s / tot_b * 100) if tot_b else 0.0,
                "quote": [{"categoria": k, **v} for k, v in sorted(quote.items())],
                "flussi": [
                    {
                        "descrizione": f["descrizione"],
                        "segno": f["segno"],
                        "importo": f["importo"],
                        "data": f["data_attesa"],
                        "completata": f["completata"],
                    }
                    for f in finanza_repo.list_movimenti_previsti(iniziativa.id)
                ],
            }
        )
    return pack


def _tabella_esiste(nome: str) -> bool:
    from src.lib import db

    try:
        row = db.query_one("select to_regclass(%s) as r", (f"public.{nome}",))
        return bool(row and row["r"])
    except Exception:  # noqa: BLE001
        return False
