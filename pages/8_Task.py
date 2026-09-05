"""Task — vista ad albero Progetto → Deliverable → Task → Subtask
(struttura MAIC tasks). Visibilità: tutti vedono; modifica owner/supervisor/admin.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_login
from src.data import (
    deliverable_repo,
    etichetta_repo,
    iniziativa_repo,
    persona_repo,
    task_repo,
)
from src.domain.models import (
    STATO_TASK_BADGE,
    TIPI_DELIVERABLE,
    TIPO_DELIVERABLE_BADGE,
    RuoloSistema,
)
from src.lib.labels import etichetta_con_tag, etichetta_progetto
from src.ui.task_ui import (
    KANBAN_STATI,
    STATO_BADGE_D,
    card_kanban,
    form_nuovo_task,
    riga_settimana,
    riga_task,
)

persona = require_login()
is_admin = persona.ruolo_sistema == RuoloSistema.admin
puo_gestire_deliv = persona.ruolo_sistema in (RuoloSistema.admin, RuoloSistema.pm)

st.title("Task e deliverable")

persone = persona_repo.list_persone(solo_attivi=True)
nomi = {p.id: p.nome_completo for p in persona_repo.list_persone()}
iniziative = iniziativa_repo.list_iniziative()
titoli_ini = {i.id: etichetta_con_tag(i) for i in iniziative}

vista = st.radio(
    "Vista",
    ["🌳 Albero per progetto", "📋 Elenco", "📌 Kanban", "🗓 La mia settimana"],
    horizontal=True,
)

with st.expander("📄 Esporta report attività"):
    from src.lib.report_attivita import report_markdown, tasks_xlsx

    _tutti_task = task_repo.list_tasks(include_archiviati=False)
    _deliv_by_ini = {i.id: deliverable_repo.list_deliverables(i.id) for i in iniziative}
    md = report_markdown(
        iniziative, _deliv_by_ini, _tutti_task, nomi, etichetta_progetto
    )
    e1, e2 = st.columns(2)
    e1.download_button(
        "⬇️ Report Markdown",
        md.encode("utf-8"),
        "report_attivita.md",
        "text/markdown",
    )
    e2.download_button(
        "⬇️ Task XLSX",
        tasks_xlsx(_tutti_task, nomi, titoli_ini),
        "report_task.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with st.expander("➕ Nuovo task"):
    form_nuovo_task(persone, iniziative, default_owner=persona)

# --- Filtri -----------------------------------------------------------------
f1, f2, f3, f4 = st.columns(4)
filtro_stato = f1.multiselect(
    "Stato",
    options=list(STATO_TASK_BADGE),
    default=["da_fare", "in_corso", "bloccato"],
    format_func=lambda s: STATO_TASK_BADGE[s],
)
filtro_ini = f2.selectbox(
    "Progetto",
    [None] + iniziative,
    format_func=lambda i: "(tutti)" if i is None else titoli_ini[i.id],
)
filtro_persona = f3.selectbox(
    "Persona (owner)",
    [None] + persone,
    format_func=lambda p: "(tutte)" if p is None else p.nome_completo,
)
mostra_archiviati = f4.checkbox("Mostra archiviati", value=False)

tasks_all = task_repo.list_tasks(include_archiviati=True)
by_id = {t.id: t for t in tasks_all}

# Conteggio dei subtask per task padre: calcolato su TUTTI i task non
# archiviati, così non dipende dai filtri di stato applicati alla vista.
_conta_sub: dict = {}
for _t in tasks_all:
    if _t.parent_task_id and not _t.archiviato:
        _c = _conta_sub.setdefault(_t.parent_task_id, [0, 0])
        _c[1] += 1
        if _t.stato == "completato":
            _c[0] += 1


def _sub(t) -> tuple[int, int] | None:
    """(subtask completati, totali) del task, o None se non ne ha."""
    c = _conta_sub.get(t.id)
    return (c[0], c[1]) if c else None


tasks = task_repo.list_tasks(include_archiviati=mostra_archiviati)
if filtro_stato:
    tasks = [t for t in tasks if t.stato in filtro_stato]
if filtro_ini:
    tasks = [t for t in tasks if t.iniziativa_id == filtro_ini.id]
if filtro_persona:
    tasks = [t for t in tasks if t.owner_id == filtro_persona.id]

_key = lambda x: (x.scadenza or date(9999, 12, 31), x.titolo)  # noqa: E731


_et_map = etichetta_repo.etichette_by_task()


def _render_task_con_figli(t, prefix, indent=False):
    figli = [s for s in tasks if s.parent_task_id == t.id]
    riga_task(
        t,
        nomi,
        titoli_ini,
        persona,
        is_admin,
        key_prefix=prefix,
        indent=indent,
        etichette_map=_et_map,
        subtask=_sub(t),
    )
    for s in sorted(figli, key=_key):
        riga_task(
            s,
            nomi,
            titoli_ini,
            persona,
            is_admin,
            key_prefix=f"{prefix}_s",
            indent=True,
            etichette_map=_et_map,
        )


# =====================================================================
# VISTA AD ALBERO: Progetto -> Deliverable -> Task -> Subtask
# =====================================================================
if vista.startswith("🌳"):
    progetti_da_mostrare = [filtro_ini] if filtro_ini else iniziative
    task_per_ini: dict = {}
    for t in tasks:
        task_per_ini.setdefault(t.iniziativa_id, []).append(t)
    senza_progetto = [t for t in tasks if t.iniziativa_id is None]

    for ini in progetti_da_mostrare:
        ini_tasks = task_per_ini.get(ini.id, [])
        delivs = deliverable_repo.list_deliverables(
            ini.id, include_archiviati=mostra_archiviati
        )
        # I progetti senza contenuti restano visibili: è da qui che si creano
        # il primo deliverable e i primi task.
        vuoto = not ini_tasks and not delivs
        etichetta_exp = f"📁 {titoli_ini[ini.id]}" + (" · (vuoto)" if vuoto else "")
        with st.expander(etichetta_exp, expanded=bool(filtro_ini)):
            if vuoto:
                st.caption(
                    "Nessun deliverable né task: comincia creando un "
                    "deliverable (prototipo, report o paper) e poi i task che "
                    "servono a produrlo."
                )
            if puo_gestire_deliv:
                with st.expander("➕ Nuovo deliverable"):
                    with st.form(f"nd_{ini.id}", clear_on_submit=True):
                        dc1, dc2, dc3 = st.columns([3, 1, 1])
                        d_tit = dc1.text_input("Titolo deliverable")
                        d_tipo = dc2.selectbox(
                            "Tipo",
                            TIPI_DELIVERABLE,
                            format_func=lambda t: TIPO_DELIVERABLE_BADGE[t],
                            key=f"dtipo_{ini.id}",
                        )
                        d_scad = dc3.date_input("Scadenza", value=None)
                        d_own = st.selectbox(
                            "Owner",
                            [None] + persone,
                            format_func=lambda p: "—" if p is None else p.nome_completo,
                            key=f"down_{ini.id}",
                        )
                        if st.form_submit_button("Crea deliverable") and d_tit:
                            deliverable_repo.create_deliverable(
                                ini.id,
                                d_tit,
                                tipo=d_tipo or None,
                                scadenza=d_scad,
                                owner_id=d_own.id if d_own else None,
                            )
                            st.rerun()

            with st.expander("➕ Nuovo task in questo progetto"):
                form_nuovo_task(
                    persone,
                    iniziative,
                    default_owner=persona,
                    iniziativa_fissa=ini,
                    key=f"ntp_{ini.id}",
                )

            # deliverable con i loro task
            deliv_ids = set()
            for d in delivs:
                deliv_ids.add(d.id)
                icona = STATO_BADGE_D.get(d.stato, d.stato)
                scad = f" · 📅 {d.scadenza:%d/%m/%Y}" if d.scadenza else ""
                own = nomi.get(d.owner_id, "")
                st.markdown(
                    f"### 📦 {d.titolo}  \n"
                    f"<small>{icona}"
                    + (
                        f" · {TIPO_DELIVERABLE_BADGE.get(d.tipo, d.tipo)}"
                        if d.tipo
                        else ""
                    )
                    + scad
                    + (f" · 👤 {own}" if own else "")
                    + "</small>",
                    unsafe_allow_html=True,
                )
                d_tasks = [
                    t
                    for t in ini_tasks
                    if t.deliverable_id == d.id and not t.parent_task_id
                ]
                for t in sorted(d_tasks, key=_key):
                    _render_task_con_figli(t, f"d{d.id}")
                dcol1, dcol2 = st.columns([3, 1])
                with dcol1.expander(f"➕ task nel deliverable «{d.titolo}»"):
                    form_nuovo_task(
                        persone,
                        iniziative,
                        default_owner=persona,
                        iniziativa_fissa=ini,
                        deliverable_fissa=d,
                        key=f"ntd_{d.id}",
                    )
                if is_admin and dcol2.button("🗄 archivia", key=f"arch_d_{d.id}"):
                    deliverable_repo.update_deliverable(d.id, archiviato=True)
                    st.rerun()

            # task del progetto SENZA deliverable
            liberi = [
                t for t in ini_tasks if not t.deliverable_id and not t.parent_task_id
            ]
            if liberi:
                st.markdown("**Task senza deliverable**")
                for t in sorted(liberi, key=_key):
                    _render_task_con_figli(t, f"free{ini.id}")

    if senza_progetto and not filtro_ini:
        with st.expander("📌 Task senza progetto", expanded=False):
            for t in sorted(
                [x for x in senza_progetto if not x.parent_task_id], key=_key
            ):
                _render_task_con_figli(t, "nop")

# =====================================================================
# VISTA KANBAN: una colonna per stato, spostamento con ◀ ▶
# =====================================================================
elif vista.startswith("📌"):
    colonne = st.columns(len(KANBAN_STATI))
    for col, stato in zip(colonne, KANBAN_STATI, strict=True):
        in_col = [t for t in tasks if t.stato == stato]
        with col:
            st.markdown(f"**{STATO_BADGE_D[stato]}** · {len(in_col)}")
            for t in sorted(in_col, key=_key):
                card_kanban(t, nomi, titoli_ini, persona, is_admin, subtask=_sub(t))
    st.caption(
        "I task completati compaiono solo se lo stato «completato» è fra i filtri."
    )

# =====================================================================
# VISTA «LA MIA SETTIMANA»: aggiornamento in linea (My Week di MAIC tasks)
# =====================================================================
elif vista.startswith("🗓"):
    miei = [
        t
        for t in task_repo.list_tasks(include_archiviati=False)
        if t.stato in ("da_fare", "in_corso", "bloccato")
        and (
            t.owner_id == persona.id
            or (is_admin and filtro_persona and t.owner_id == filtro_persona.id)
        )
    ]
    if is_admin and filtro_persona:
        miei = [t for t in miei if t.owner_id == filtro_persona.id]
    try:
        from src.data import task_storico_repo

        _ultimo = task_storico_repo.ultimo_aggiornamento_per_task()
        fermo = {t.id: task_storico_repo.giorni_fermo(t, _ultimo) for t in miei}
    except Exception:  # noqa: BLE001 — migrazione 0015 non ancora applicata
        fermo = {}
    oggi_ = date.today()
    _prio = {"urgente": 0, "alta": 1, "media": 2, "bassa": 3, "nessuna": 4}

    def _ordine(t):
        scaduto = bool(t.scadenza and t.scadenza < oggi_)
        return (
            0 if t.stato == "bloccato" else 1,
            0 if scaduto else 1,
            -(fermo.get(t.id) or 0),
            t.scadenza or date(9999, 12, 31),
            _prio.get(t.priorita, 4),
        )

    st.caption(
        "Tutti i tuoi task attivi in una pagina: cambia lo stato o aggiungi una "
        "nota di avanzamento senza aprire i dettagli. Ordine: bloccati → scaduti → "
        "fermi da più tempo → scadenza → priorità."
    )
    soglia = st.slider("Mostra solo task fermi da almeno (giorni)", 0, 60, 0)
    miei = [t for t in miei if (fermo.get(t.id) or 0) >= soglia]
    if not miei:
        st.info("Nessun task attivo con questi criteri.")
    for t in sorted(miei, key=_ordine):
        riga_settimana(t, nomi, titoli_ini, persona, fermo.get(t.id), subtask=_sub(t))

# =====================================================================
# VISTA ELENCO (piatta)
# =====================================================================
else:
    # Deliverable (elenco) — filtrati per progetto se selezionato
    delivs_el = []
    for ini in [filtro_ini] if filtro_ini else iniziative:
        for d in deliverable_repo.list_deliverables(
            ini.id, include_archiviati=mostra_archiviati
        ):
            delivs_el.append((ini, d))
    if delivs_el:
        st.markdown("**📦 Deliverable**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Progetto": titoli_ini[ini.id],
                        "Deliverable": d.titolo,
                        "Tipo": d.tipo or "",
                        "Stato": STATO_BADGE_D.get(d.stato, d.stato),
                        "Scadenza": (f"{d.scadenza:%d/%m/%Y}" if d.scadenza else ""),
                        "Owner": nomi.get(d.owner_id, ""),
                    }
                    for ini, d in delivs_el
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.divider()

    if not tasks:
        st.info("Nessun task con i filtri scelti.")
        st.stop()
    radici = [t for t in tasks if not t.parent_task_id]
    subtasks = [t for t in tasks if t.parent_task_id]
    st.caption(
        f"{len(tasks)} task ({len(radici)} principali, {len(subtasks)} subtask). "
        "I subtask si aggiungono anche da «Dettagli» di un task, in qualsiasi vista."
    )
    for t in sorted(radici, key=_key):
        _render_task_con_figli(t, "lst")
        if task_repo.puo_modificare(t, persona.id, is_admin):
            with st.expander(f"↳ aggiungi subtask a «{t.titolo}»", expanded=False):
                form_nuovo_task(
                    persone,
                    iniziative,
                    default_owner=persona,
                    parent=t,
                    key=f"sub_{t.id}",
                )
    orfani = [s for s in subtasks if s.parent_task_id not in {t.id for t in radici}]
    if orfani:
        st.markdown("**Subtask (task padre non nei filtri):**")
        for s in sorted(orfani, key=_key):
            riga_task(
                s,
                nomi,
                titoli_ini,
                persona,
                is_admin,
                key_prefix="orf",
                indent=True,
            )
