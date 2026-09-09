"""Monthly report — raccolta dati dalla piattaforma, generazione e salvataggio.

Usato dalla pagina Progetti (generazione a richiesta), dalla Dashboard
(generazione automatica del mese precedente per i progetti che lo richiedono)
e da `scripts/monthly_reports.py` (schedulato: genera + e-mail).
"""

from __future__ import annotations

from datetime import date, datetime

from src.data import (
    deliverable_repo,
    iniziativa_repo,
    missione_repo,
    monthly_repo,
    persona_repo,
    progetti_repo,
    task_repo,
)
from src.domain.models import TIPO_DELIVERABLE_BADGE
from src.lib.monthly_report import (
    ATTIVI,
    genera_md,
    intervallo_mese,
    mese_precedente,
)


def _giorno(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    return v


def pack_monthly(iniziativa, anno: int, mese: int) -> dict:
    """Tutti i dati del mese per un progetto, pronti per `genera_md`."""
    da, a = intervallo_mese(anno, mese)
    nomi = {p.id: p.nome_completo for p in persona_repo.list_persone()}
    tasks = task_repo.list_tasks(include_archiviati=True, iniziativa_id=iniziativa.id)
    delivs = deliverable_repo.list_deliverables(iniziativa.id, include_archiviati=True)
    deliv_by_id = {d.id: d for d in delivs}
    avanz = deliverable_repo.avanzamento_task()
    commenti = monthly_repo.commenti_nel_mese(iniziativa.id, da, a)
    storico = monthly_repo.storico_nel_mese(iniziativa.id, da, a)
    storico_by_task: dict = {}
    for s in storico:
        storico_by_task.setdefault(s["task_id"], []).append(s)
    commenti_by_task: dict = {}
    commenti_progetto = []
    for c in commenti:
        if c["entita"] == "task":
            commenti_by_task.setdefault(c["entita_id"], []).append(c)
        elif c["entita"] == "iniziativa":
            commenti_progetto.append(c)
        else:  # deliverable
            commenti_progetto.append({**c, "testo": f"[deliverable] {c['testo']}"})

    def _t(t) -> dict:
        return {
            "titolo": t.titolo,
            "stato": t.stato,
            "owner": nomi.get(t.owner_id),
            "scadenza": t.scadenza,
            "completato_il": t.completato_il,
            "ore_stimate": float(t.ore_stimate) if t.ore_stimate else None,
            "ore_effettive": (
                float(t.ore_effettive) if getattr(t, "ore_effettive", None) else None
            ),
            "descrizione": t.descrizione,
            "storico": [
                {"da": s["da"], "a": s["a"], "quando": s["quando"]}
                for s in storico_by_task.get(t.id, [])
            ],
            "commenti": [
                {"autore": c["autore"], "quando": c["quando"], "testo": c["testo"]}
                for c in commenti_by_task.get(t.id, [])
            ],
            "subtask": [],
        }

    # task «attivi nel mese»: creati prima della fine del mese e ancora aperti
    # a fine mese (o completati nel mese)
    def _nel_mese(t) -> bool:
        creato = _giorno(t.created_at) or da
        if creato >= a:
            return False
        if t.archiviato and t.stato in ("completato", "annullato"):
            return bool(t.completato_il and da <= t.completato_il < a)
        if t.stato in ATTIVI:
            return True
        if t.stato == "completato":
            return bool(t.completato_il and da <= t.completato_il < a)
        return False

    rilevanti = [t for t in tasks if _nel_mese(t)]
    radici = [t for t in rilevanti if not t.parent_task_id]
    figli: dict = {}
    for t in rilevanti:
        if t.parent_task_id:
            figli.setdefault(t.parent_task_id, []).append(t)
    id_radici = {t.id for t in radici}
    # subtask il cui padre non è rilevante: promossi a radice
    for t in rilevanti:
        if t.parent_task_id and t.parent_task_id not in id_radici:
            radici.append(t)

    def _albero(t) -> dict:
        d = _t(t)
        d["subtask"] = [
            _t(s)
            for s in sorted(figli.get(t.id, []), key=lambda x: (x.scadenza or date.max))
        ]
        return d

    attivi_per_deliv: dict = {}
    completati = []
    for t in sorted(radici, key=lambda x: (x.scadenza or date.max, x.titolo)):
        nodo = _albero(t)
        if t.stato == "completato":
            completati.append(nodo)
        else:
            chiave = (
                deliv_by_id[t.deliverable_id].titolo
                if t.deliverable_id in deliv_by_id
                else None
            )
            attivi_per_deliv.setdefault(chiave, []).append(nodo)
    task_attivi = [
        {"deliverable": k, "task": v}
        for k, v in sorted(
            attivi_per_deliv.items(), key=lambda kv: (kv[0] is None, kv[0] or "")
        )
    ]

    milestone = progetti_repo.list_milestones(iniziativa.id)
    missioni = missione_repo.list_missioni(iniziativa_id=iniziativa.id)
    responsabile = nomi.get(iniziativa.responsabile_id)
    return {
        "anno": anno,
        "mese": mese,
        "generato_il": date.today(),
        "progetto": {
            "acronimo": iniziativa.acronimo,
            "codice": iniziativa.codice,
            "titolo": iniziativa.titolo,
            "controparte": iniziativa.controparte,
            "cup": getattr(iniziativa, "cup", None),
            "inizio": iniziativa.data_inizio,
            "fine": iniziativa.data_fine,
            "responsabile": responsabile,
            "stato": iniziativa.stato,
            "istruzioni": getattr(iniziativa, "monthly_report_istruzioni", None),
        },
        "deliverables": [
            {
                "titolo": d.titolo,
                "tipo": TIPO_DELIVERABLE_BADGE.get(d.tipo, d.tipo or "—").split(" ", 1)[
                    -1
                ],
                "stato": d.stato,
                "scadenza": d.scadenza,
                "owner": nomi.get(d.owner_id),
                "task_completati": avanz.get(str(d.id), {}).get("completati", 0),
                "task_totali": avanz.get(str(d.id), {}).get("totali", 0),
            }
            for d in delivs
            if not d.archiviato
        ],
        "milestone": [
            {
                "titolo": m.titolo,
                "stato": m.stato,
                "data": m.data_prevista,
                "nel_mese": bool(m.data_prevista and da <= m.data_prevista < a),
            }
            for m in milestone
        ],
        "task_attivi": task_attivi,
        "task_completati": completati,
        "ore_timesheet": monthly_repo.ore_timesheet_mese(iniziativa.id, da, a),
        "missioni": [
            {
                "persona": nomi.get(m.persona_id, "—"),
                "destinazione": m.destinazione,
                "inizio": m.data_inizio,
                "fine": m.data_fine,
                "obiettivo": m.obiettivo,
            }
            for m in missioni
            if m.data_inizio < a and m.data_fine >= da and m.stato != "respinta"
        ],
        "commenti_progetto": [
            {"autore": c["autore"], "quando": c["quando"], "testo": c["testo"]}
            for c in commenti_progetto
        ],
    }


def genera_e_salva(iniziativa, anno: int, mese: int) -> dict:
    """Genera il .md del mese e lo salva (stato «pronto»)."""
    md = genera_md(pack_monthly(iniziativa, anno, mese))
    return monthly_repo.salva_report(iniziativa.id, anno, mese, md)


def assicura_mese_precedente(oggi: date | None = None) -> list[dict]:
    """Per ogni progetto attivo con monthly report, genera il report del mese
    precedente se non esiste ancora. Ritorna i report creati."""
    oggi = oggi or date.today()
    anno, mese = mese_precedente(oggi)
    creati = []
    for r in monthly_repo.progetti_con_monthly():
        ini = iniziativa_repo.get_iniziativa(r["id"])
        if ini is None:
            continue
        # il progetto deve coprire (almeno in parte) il mese
        da, a = intervallo_mese(anno, mese)
        if ini.data_inizio and ini.data_inizio >= a:
            continue
        if ini.data_fine and ini.data_fine < da:
            continue
        if monthly_repo.get_report(ini.id, anno, mese) is None:
            creati.append(genera_e_salva(ini, anno, mese))
    return creati
