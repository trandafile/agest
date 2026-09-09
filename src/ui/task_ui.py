"""Componenti UI riusabili per i task (Dashboard + pagina Task)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.data import persona_repo, task_repo
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
    subtask: tuple[int, int] | None = None,
) -> None:
    """Riga compatta di un task con bottone Dettagli.

    `etichette_map` opzionale: {task_id: [{nome, colore}]} per i chip etichetta.
    `subtask` opzionale: (completati, totali) da mostrare come «↳ 1/3».
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
        + (f" · ↳ {subtask[0]}/{subtask[1]} subtask" if subtask and subtask[1] else "")
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
        blocco_subtask(task, nomi, persona, is_admin, can_edit=False)
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

    o1, o2 = st.columns(2)
    ore_st = o1.number_input(
        "Ore stimate",
        min_value=0.0,
        step=0.5,
        value=float(task.ore_stimate or 0),
        help="Stima dell'impegno (alimenta il carico per persona).",
    )
    ore_eff = o2.number_input(
        "Ore effettive",
        min_value=0.0,
        step=0.5,
        value=float(getattr(task, "ore_effettive", None) or 0),
        help=(
            "Ore realmente spese (informativo: il timesheet resta la fonte "
            "ufficiale)."
        ),
    )
    note = st.text_area(
        "Descrizione e note del task",
        value=task.descrizione or "",
        help=(
            "Testo libero (Markdown). Le note datate «**gg/mm/aaaa** — …» in coda "
            "sono la cronaca del task: alimentano «La mia settimana» e il monthly "
            "report."
        ),
    )
    nota_nuova = st.text_input(
        "➕ Nota di avanzamento (opz.)",
        placeholder="es. inviata la bozza al project officer",
        help="Viene accodata alle note con la data di oggi.",
    )
    b1, b2 = st.columns(2)
    if b1.button("💾 Salva", type="primary", use_container_width=True):
        descrizione_finale = (note or "").rstrip()
        if nota_nuova.strip():
            riga = f"**{date.today():%d/%m/%Y}** — {nota_nuova.strip()}"
            descrizione_finale = (
                f"{descrizione_finale}\n\n{riga}" if descrizione_finale else riga
            )
        task_repo.update_task(
            task.id,
            eseguito_da=persona.email,
            stato=stato,
            priorita=prio,
            scadenza=scad,
            deliverable_id=deliverable_id,
            descrizione=descrizione_finale or None,
            ore_stimate=ore_st or None,
            ore_effettive=ore_eff or None,
        )
        etichetta_repo.set_etichette_task(task.id, et_scelte)
        etichetta_repo.set_dipendenze_task(task.id, dip_scelte)
        st.rerun()
    if b2.button("🗂 Archivia", use_container_width=True):
        task_repo.update_task(task.id, eseguito_da=persona.email, archiviato=True)
        st.rerun()

    blocco_subtask(task, nomi, persona, is_admin, can_edit=True)
    _storico_stati(task)
    st.divider()
    blocco_commenti("task", task.id, persona, is_admin, nomi)


def _storico_stati(task: Task) -> None:
    """Cambi di stato (tabella `task_storico`, v3): tollerante se la
    migrazione 0015 non è ancora applicata."""
    try:
        from src.data import task_storico_repo

        righe = task_storico_repo.storico_task(task.id)
    except Exception:  # noqa: BLE001
        return
    if not righe:
        return
    with st.expander(f"🕓 Storico stati ({len(righe)})"):
        for r in righe:
            prec = STATO_TASK_BADGE.get(r["stato_prec"], r["stato_prec"] or "creato")
            nuovo = STATO_TASK_BADGE.get(r["stato_nuovo"], r["stato_nuovo"])
            chi = f" · {r['cambiato_da']}" if r.get("cambiato_da") else ""
            st.caption(f"{r['cambiato_il']:%d/%m/%Y %H:%M} — {prec} → {nuovo}{chi}")


def _notifica_assegnazione(task: Task, owner, da_chi: Persona, progetto) -> None:
    """E-mail all'owner (se diverso da chi crea); mai bloccante."""
    try:
        from src.lib.notifiche_app import notifica_task_assegnato

        notifica_task_assegnato(task, owner, da_chi, progetto=progetto)
    except Exception:  # noqa: BLE001
        pass


def blocco_subtask(
    task: Task,
    nomi: dict,
    persona: Persona,
    is_admin: bool,
    can_edit: bool,
) -> None:
    """Subtask del task: elenco con stato e scadenza + creazione.

    Sta nel dialog dei dettagli, quindi è raggiungibile da OGNI vista
    (albero, elenco, kanban, la mia settimana, pagina Deliverable).
    La gerarchia è volutamente a due livelli: un subtask non ha figli.
    """
    st.divider()
    if task.parent_task_id:
        st.caption(
            "Questo è un subtask: la gerarchia si ferma a due livelli "
            "(task → subtask)."
        )
        return

    figli = [
        t
        for t in task_repo.list_tasks(include_archiviati=False)
        if t.parent_task_id == task.id
    ]
    fatti = sum(1 for t in figli if t.stato == "completato")
    st.markdown(f"**Subtask** ({fatti}/{len(figli)} completati)")
    if figli:
        for s_ in sorted(figli, key=lambda x: (x.scadenza or date.max, x.titolo)):
            st.markdown(
                f"- {STATO_TASK_BADGE.get(s_.stato, s_.stato)} **{s_.titolo}** · "
                f"{scadenza_chip(s_.scadenza)} · 👤 {nomi.get(s_.owner_id, '—')}"
            )
    else:
        st.caption("Nessun subtask: spezza il task in passi più piccoli se serve.")

    if not can_edit:
        return
    with st.expander("➕ Aggiungi subtask"):
        with st.form(f"nuovo_sub_{task.id}", clear_on_submit=True):
            titolo = st.text_input("Titolo del subtask *")
            c1, c2, c3 = st.columns(3)
            persone = persona_repo.list_persone(solo_attivi=True)
            idx_own = next(
                (i for i, p in enumerate(persone) if p.id == task.owner_id), None
            )
            owner = c1.selectbox(
                "Owner",
                persone,
                index=idx_own if idx_own is not None else 0,
                format_func=lambda p: p.nome_completo,
                key=f"sub_own_{task.id}",
            )
            scad = c2.date_input(
                "Scadenza (opz.)", value=None, key=f"sub_scad_{task.id}"
            )
            ore = c3.number_input(
                "Ore stimate (opz.)", min_value=0.0, step=0.5, key=f"sub_ore_{task.id}"
            )
            if st.form_submit_button("Crea subtask", type="primary"):
                if not titolo:
                    st.error("Il titolo è obbligatorio.")
                else:
                    nuovo = task_repo.create_task(
                        titolo=titolo,
                        owner_id=owner.id if owner else None,
                        supervisor_id=task.supervisor_id,
                        iniziativa_id=task.iniziativa_id,
                        deliverable_id=task.deliverable_id,
                        parent_task_id=task.id,
                        scadenza=scad,
                        ore_stimate=ore or None,
                        priorita=task.priorita,
                        eseguito_da=persona.email,
                    )
                    _notifica_assegnazione(nuovo, owner, persona, None)
                    st.rerun()


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
        f6, f7 = st.columns([1, 3])
        ore_st = f6.number_input("Ore stimate (opz.)", min_value=0.0, step=0.5)
        desc = f7.text_area("Descrizione (opz.)")
        if st.form_submit_button("Crea task", type="primary"):
            if not titolo:
                st.error("Il titolo è obbligatorio.")
            else:
                nuovo = task_repo.create_task(
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
                    ore_stimate=ore_st or None,
                    eseguito_da=default_owner.email,
                )
                _notifica_assegnazione(
                    nuovo,
                    owner,
                    default_owner,
                    (
                        etichetta_con_tag(ini or iniziativa_fissa)
                        if (ini or iniziativa_fissa) is not None
                        else None
                    ),
                )
                st.rerun()


def riga_settimana(
    task: Task,
    nomi: dict,
    titoli_iniziative: dict,
    persona: Persona,
    giorni_fermo: int | None,
    key_prefix: str = "wk",
    subtask: tuple[int, int] | None = None,
) -> None:
    """«La mia settimana» (My Week di MAIC tasks): stato modificabile IN LINEA
    e nota di avanzamento, senza aprire il dialog."""
    c1, c2, c3, c4 = st.columns([4.2, 1.6, 3, 1.2])
    fermo = (
        f" · ⏸ fermo da {giorni_fermo}g" if giorni_fermo and giorni_fermo >= 14 else ""
    )
    conta = f" · ↳ {subtask[0]}/{subtask[1]} subtask" if subtask and subtask[1] else ""
    c1.markdown(
        f"**{task.titolo}** · {PRIORITA_BADGE.get(task.priorita, '')} · "
        f"{scadenza_chip(task.scadenza)}  \n<small>📁 "
        f"{titoli_iniziative.get(task.iniziativa_id, '—')}{fermo}{conta}</small>",
        unsafe_allow_html=True,
    )
    stati = [s for s in STATI_TASK if s != "annullato"]
    nuovo = c2.selectbox(
        "Stato",
        stati,
        index=stati.index(task.stato) if task.stato in stati else 0,
        format_func=lambda s: STATO_TASK_BADGE[s],
        key=f"{key_prefix}_st_{task.id}",
        label_visibility="collapsed",
    )
    nota = c3.text_input(
        "Nota",
        placeholder="nota di avanzamento (opz.)",
        key=f"{key_prefix}_nt_{task.id}",
        label_visibility="collapsed",
    )
    if c4.button(
        "Aggiorna", key=f"{key_prefix}_ok_{task.id}", use_container_width=True
    ):
        if nuovo == task.stato and not nota.strip():
            st.toast("Niente da aggiornare.")
        else:
            task_repo.aggiorna_rapido(
                task.id,
                stato=nuovo if nuovo != task.stato else None,
                nota=nota,
                descrizione_attuale=task.descrizione,
                eseguito_da=persona.email,
            )
            st.rerun()


KANBAN_STATI = ("da_fare", "in_corso", "bloccato", "completato")


def card_kanban(
    task: Task,
    nomi: dict,
    titoli_iniziative: dict,
    persona: Persona,
    is_admin: bool,
    key_prefix: str = "kb",
    subtask: tuple[int, int] | None = None,
) -> None:
    """Card compatta per la vista kanban con spostamento fra colonne."""
    with st.container(border=True):
        sub_ = "↳ " if task.parent_task_id else ""
        conta = (
            f" · ↳ {subtask[0]}/{subtask[1]} subtask" if subtask and subtask[1] else ""
        )
        st.markdown(
            f"{sub_}**{task.titolo}**  \n<small>"
            f"{PRIORITA_BADGE.get(task.priorita, '')} · "
            f"{scadenza_chip(task.scadenza)}  \n👤 {nomi.get(task.owner_id, '—')} · 📁 "
            f"{titoli_iniziative.get(task.iniziativa_id, '—')}{conta}</small>",
            unsafe_allow_html=True,
        )
        if task_repo.puo_modificare(task, persona.id, is_admin):
            i = KANBAN_STATI.index(task.stato) if task.stato in KANBAN_STATI else 0
            b1, b2, b3 = st.columns(3)
            if i > 0 and b1.button(
                "◀",
                key=f"{key_prefix}_prev_{task.id}",
                help=STATO_TASK_BADGE[KANBAN_STATI[i - 1]],
            ):
                task_repo.update_task(
                    task.id, eseguito_da=persona.email, stato=KANBAN_STATI[i - 1]
                )
                st.rerun()
            if b2.button("⋯", key=f"{key_prefix}_det_{task.id}", help="Dettagli"):
                task_dialog(task, nomi, titoli_iniziative, persona, is_admin)
            if i < len(KANBAN_STATI) - 1 and b3.button(
                "▶",
                key=f"{key_prefix}_next_{task.id}",
                help=STATO_TASK_BADGE[KANBAN_STATI[i + 1]],
            ):
                task_repo.update_task(
                    task.id, eseguito_da=persona.email, stato=KANBAN_STATI[i + 1]
                )
                st.rerun()
        elif st.button("⋯", key=f"{key_prefix}_det_{task.id}", help="Dettagli"):
            task_dialog(task, nomi, titoli_iniziative, persona, is_admin)
