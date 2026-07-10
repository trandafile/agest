"""Componenti UI riusabili per i task (Dashboard + pagina Task)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.data import task_repo
from src.domain.models import (
    PRIORITA_BADGE,
    PRIORITA_TASK,
    STATI_TASK,
    STATO_TASK_BADGE,
    Persona,
    Task,
)
from src.lib.labels import etichetta_con_tag
from src.ui.commenti_ui import blocco_commenti

STATO_BADGE_D = {
    "da_fare": "⚪ Da fare",
    "in_corso": "🔵 In corso",
    "bloccato": "🔴 Bloccato",
    "completato": "🟢 Completato",
    "annullato": "⚫ Annullato",
}


def scadenza_chip(scadenza: date | None) -> str:
    """Etichetta scadenza con evidenza ritardo/imminenza (stile MAIC tasks)."""
    if not scadenza:
        return "📅 —"
    delta = (scadenza - date.today()).days
    label = f"{scadenza:%d/%m/%Y}"
    if delta < 0:
        return f"📅 {label} 🔴 (in ritardo di {abs(delta)}g)"
    if delta <= 7:
        return f"📅 {label} 🟠 (tra {delta}g)"
    return f"📅 {label}"


def riga_task(
    task: Task,
    nomi: dict,
    titoli_iniziative: dict,
    persona: Persona,
    is_admin: bool,
    key_prefix: str,
    indent: bool = False,
    etichette_map: dict | None = None,
) -> None:
    """Riga compatta di un task con bottone Dettagli.

    `etichette_map` opzionale: {task_id: [{nome, colore}]} per i chip etichetta.
    """
    c1, c2 = st.columns([8.5, 1.5])
    prefisso = "&nbsp;&nbsp;&nbsp;↳ " if indent else ""
    owner = nomi.get(task.owner_id, "—")
    sup = nomi.get(task.supervisor_id)
    persone_txt = f"👤 {owner}" + (f" · 👁 {sup}" if sup and sup != owner else "")
    chips = ""
    for e in (etichette_map or {}).get(str(task.id), []):
        chips += (
            f"<span style='background:{e['colore']}22;color:{e['colore']};"
            "border-radius:4px;padding:1px 6px;font-size:10px;margin-right:3px'>"
            f"{e['nome']}</span>"
        )
    c1.markdown(
        f"{prefisso}**{task.titolo}** · "
        f"{STATO_TASK_BADGE.get(task.stato, task.stato)} · "
        f"{PRIORITA_BADGE.get(task.priorita, '')} · {scadenza_chip(task.scadenza)}  \n"
        f"{prefisso}<small>{persone_txt}"
        + (
            f" · 📁 {titoli_iniziative.get(task.iniziativa_id, '')}"
            if task.iniziativa_id
            else ""
        )
        + (f" &nbsp;{chips}" if chips else "")
        + "</small>",
        unsafe_allow_html=True,
    )
    if c2.button("Dettagli", key=f"{key_prefix}_{task.id}", use_container_width=True):
        task_dialog(task, nomi, titoli_iniziative, persona, is_admin)


@st.dialog("Dettagli task", width="large")
def task_dialog(
    task: Task,
    nomi: dict,
    titoli_iniziative: dict,
    persona: Persona,
    is_admin: bool,
) -> None:
    can_edit = task_repo.puo_modificare(task, persona.id, is_admin)
    st.markdown(f"### {task.titolo}")
    if task.descrizione:
        st.markdown(task.descrizione)
    st.caption(
        f"Owner: {nomi.get(task.owner_id, '—')} · "
        f"Supervisor: {nomi.get(task.supervisor_id, '—')} · "
        f"Progetto: {titoli_iniziative.get(task.iniziativa_id, '—')}"
    )
    if task.scadenza:
        from src.lib.calendario import link_google_calendar

        gcal = link_google_calendar(f"✅ {task.titolo}", task.scadenza)
        st.markdown(f"[➕ Aggiungi a Google Calendar]({gcal})")
    if not can_edit:
        st.info(
            "Sola lettura: puoi modificare solo i task di cui sei owner/supervisor."
        )
        st.divider()
        blocco_commenti("task", task.id, persona, is_admin, nomi)
        return

    c1, c2, c3 = st.columns(3)
    stato = c1.selectbox(
        "Stato",
        STATI_TASK,
        index=STATI_TASK.index(task.stato),
        format_func=lambda s: STATO_TASK_BADGE[s],
    )
    prio = c2.selectbox(
        "Priorità",
        PRIORITA_TASK,
        index=PRIORITA_TASK.index(task.priorita),
        format_func=lambda p: PRIORITA_BADGE[p],
    )
    scad = c3.date_input("Scadenza", value=task.scadenza)

    # riassegnazione a un deliverable del progetto del task
    deliverable_id = task.deliverable_id
    if task.iniziativa_id:
        from src.data import deliverable_repo

        delivs = deliverable_repo.list_deliverables(task.iniziativa_id)
        opzioni = [None] + delivs
        idx = next(
            (i for i, d in enumerate(opzioni) if d and d.id == task.deliverable_id),
            0,
        )
        d_sel = st.selectbox(
            "Deliverable",
            opzioni,
            index=idx,
            format_func=lambda d: "— (nessuno)" if d is None else d.titolo,
        )
        deliverable_id = d_sel.id if d_sel else None

    # etichette (label)
    from src.data import etichetta_repo

    etichette = etichetta_repo.list_etichette()
    et_by_id = {str(e["id"]): e for e in etichette}
    et_scelte = st.multiselect(
        "Etichette",
        options=list(et_by_id),
        default=etichetta_repo.etichette_task(task.id),
        format_func=lambda i: et_by_id[i]["nome"],
    )

    # dipendenze: questo task dipende da…
    altri = [
        t for t in task_repo.list_tasks(include_archiviati=False) if t.id != task.id
    ]
    dip_by_id = {str(t.id): t for t in altri}
    dip_scelte = st.multiselect(
        "Dipende da (task che devono precedere)",
        options=list(dip_by_id),
        default=etichetta_repo.dipendenze_task(task.id),
        format_func=lambda i: dip_by_id[i].titolo,
    )

    note = st.text_area("Descrizione / note", value=task.descrizione or "")
    b1, b2 = st.columns(2)
    if b1.button("💾 Salva", type="primary", use_container_width=True):
        task_repo.update_task(
            task.id,
            stato=stato,
            priorita=prio,
            scadenza=scad,
            deliverable_id=deliverable_id,
            descrizione=note or None,
        )
        etichetta_repo.set_etichette_task(task.id, et_scelte)
        etichetta_repo.set_dipendenze_task(task.id, dip_scelte)
        st.rerun()
    if b2.button("🗂 Archivia", use_container_width=True):
        task_repo.update_task(task.id, archiviato=True)
        st.rerun()

    st.divider()
    blocco_commenti("task", task.id, persona, is_admin, nomi)


def form_nuovo_task(
    persone: list[Persona],
    iniziative: list,
    default_owner: Persona,
    parent: Task | None = None,
    key: str = "nuovo_task",
    iniziativa_fissa=None,
    deliverable_fissa=None,
) -> None:
    """Form di creazione task.

    - `parent`: crea un subtask sotto `parent`.
    - `iniziativa_fissa`: progetto già scelto (nascondi il selettore).
    - `deliverable_fissa`: deliverable già scelto (il task ci finisce dentro).
    """
    with st.form(key, clear_on_submit=True):
        titolo = st.text_input("Titolo *")
        f1, f2, f3 = st.columns(3)
        owner = f1.selectbox(
            "Owner",
            persone,
            index=next(
                (i for i, p in enumerate(persone) if p.id == default_owner.id), 0
            ),
            format_func=lambda p: p.nome_completo,
        )
        sup = f2.selectbox(
            "Supervisor",
            [None] + persone,
            format_func=lambda p: "—" if p is None else p.nome_completo,
        )
        prio = f3.selectbox(
            "Priorità",
            PRIORITA_TASK,
            index=4,
            format_func=lambda p: PRIORITA_BADGE[p],
        )
        f4, f5 = st.columns(2)
        if parent is not None:
            ini = None
            f4.markdown(f"Subtask di: **{parent.titolo}**")
        elif iniziativa_fissa is not None:
            ini = iniziativa_fissa
            contesto = etichetta_con_tag(iniziativa_fissa)
            if deliverable_fissa is not None:
                contesto += f" · 📦 {deliverable_fissa.titolo}"
            f4.markdown(f"In: **{contesto}**")
        else:
            ini = f4.selectbox(
                "Progetto (opz.)",
                [None] + iniziative,
                format_func=lambda i: ("—" if i is None else etichetta_con_tag(i)),
            )
        scad = f5.date_input("Scadenza (opz.)", value=None)
        desc = st.text_area("Descrizione (opz.)")
        if st.form_submit_button("Crea task", type="primary"):
            if not titolo:
                st.error("Il titolo è obbligatorio.")
            else:
                task_repo.create_task(
                    titolo=titolo,
                    owner_id=owner.id,
                    supervisor_id=sup.id if sup else None,
                    iniziativa_id=(
                        parent.iniziativa_id if parent else (ini.id if ini else None)
                    ),
                    deliverable_id=(
                        deliverable_fissa.id if deliverable_fissa else None
                    ),
                    parent_task_id=parent.id if parent else None,
                    descrizione=desc or None,
                    priorita=prio,
                    scadenza=scad,
                )
                st.rerun()
