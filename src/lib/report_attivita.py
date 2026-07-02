"""Report attività (task/deliverable) — Markdown ed export XLSX. Pure/testabile."""

from __future__ import annotations

import io
from datetime import date

from src.domain.models import STATO_TASK_BADGE


def _scad(d: date | None) -> str:
    return f"{d:%d/%m/%Y}" if d else "—"


def report_markdown(
    iniziative: list,
    deliverables_by_ini: dict,
    tasks: list,
    nomi: dict,
    etichetta,
) -> str:
    """Report ad albero Progetto → Deliverable → Task → Subtask in Markdown.

    `etichetta(i)` -> label del progetto; `nomi` {id: nome persona}.
    """
    figli_by_parent: dict = {}
    for t in tasks:
        if t.parent_task_id:
            figli_by_parent.setdefault(t.parent_task_id, []).append(t)

    def riga_task(t, livello: int) -> str:
        ind = "  " * livello
        owner = nomi.get(t.owner_id, "—")
        stato = STATO_TASK_BADGE.get(t.stato, t.stato)
        return (
            f"{ind}- **{t.titolo}** — {stato} · owner {owner} · "
            f"scad {_scad(t.scadenza)}"
            + (f" · {t.ore_stimate:g}h" if t.ore_stimate else "")
        )

    out = ["# Report attività ANTECNICA", ""]
    for ini in iniziative:
        ini_tasks = [t for t in tasks if t.iniziativa_id == ini.id]
        delivs = deliverables_by_ini.get(ini.id, [])
        if not ini_tasks and not delivs:
            continue
        out.append(f"## 📁 {etichetta(ini)}")
        for d in delivs:
            out.append(
                f"### 📦 {d.titolo}"
                + (f" ({d.tipo})" if d.tipo else "")
                + f" — scad {_scad(d.scadenza)}"
            )
            for t in [
                x
                for x in ini_tasks
                if x.deliverable_id == d.id and not x.parent_task_id
            ]:
                out.append(riga_task(t, 0))
                for s in figli_by_parent.get(t.id, []):
                    out.append(riga_task(s, 1))
        liberi = [t for t in ini_tasks if not t.deliverable_id and not t.parent_task_id]
        if liberi:
            out.append("### (senza deliverable)")
            for t in liberi:
                out.append(riga_task(t, 0))
                for s in figli_by_parent.get(t.id, []):
                    out.append(riga_task(s, 1))
        out.append("")
    return "\n".join(out)


def tasks_xlsx(tasks: list, nomi: dict, titoli_ini: dict) -> bytes:
    """Export tabellare piatto dei task in XLSX."""
    from openpyxl import Workbook

    by_id = {t.id: t for t in tasks}
    wb = Workbook()
    ws = wb.active
    ws.title = "Task"
    header = [
        "Progetto",
        "Task",
        "Padre",
        "Owner",
        "Supervisor",
        "Stato",
        "Priorità",
        "Scadenza",
        "Ore stimate",
        "Completato il",
    ]
    ws.append(header)
    for t in tasks:
        padre = by_id.get(t.parent_task_id)
        ws.append(
            [
                titoli_ini.get(t.iniziativa_id, ""),
                t.titolo,
                padre.titolo if padre else "",
                nomi.get(t.owner_id, ""),
                nomi.get(t.supervisor_id, ""),
                t.stato,
                t.priorita,
                _scad(t.scadenza),
                float(t.ore_stimate) if t.ore_stimate else None,
                _scad(t.completato_il) if t.completato_il else "",
            ]
        )
    for i, _ in enumerate(header, start=1):
        ws.column_dimensions[chr(64 + i)].width = 20
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
