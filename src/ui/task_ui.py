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
from src.lib.labels import etichetta_progetto

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
) -> None:
    """Riga compatta di un task con bottone Dettagli."""
    c1, c2 = st.columns([8.5, 1.5])
    prefisso = "&nbsp;&nbsp;&nbsp;↳ " if indent else ""
    owner = nomi.get(task.owner_id, "—")
    sup = nomi.get(task.supervisor_id)
    persone_txt = f"👤 {owner}" + (f" · 👁 {sup}" if sup and sup != owner else "")
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
    if not can_edit:
        st.info(
            "Sola lettura: puoi modificare solo i task di cui sei owner/supervisor."
        )
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
        st.rerun()
    if b2.button("🗂 Archivia", use_container_width=True):
        task_repo.update_task(task.id, archiviato=True)
        st.rerun()


def form_nuovo_task(
    persone: list[Persona],
    iniziative: list,
    default_owner: Persona,
    parent: Task | None = None,
    key: str = "nuovo_task",
) -> None:
    """Form di creazione task (o subtask se `parent` è valorizzato)."""
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
        if parent is None:
            ini = f4.selectbox(
                "Progetto (opz.)",
                [None] + iniziative,
                format_func=lambda i: ("—" if i is None else etichetta_progetto(i)),
            )
        else:
            ini = None
            f4.markdown(f"Subtask di: **{parent.titolo}**")
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
                    parent_task_id=parent.id if parent else None,
                    descrizione=desc or None,
                    priorita=prio,
                    scadenza=scad,
                )
                st.rerun()
