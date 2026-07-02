"""Task — elenco completo (visibilità MAIC tasks: tutti vedono tutto,
modifica solo owner/supervisor o admin)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.auth.session import require_login
from src.data import iniziativa_repo, persona_repo, task_repo
from src.domain.models import STATO_TASK_BADGE, RuoloSistema
from src.ui.task_ui import form_nuovo_task, riga_task

persona = require_login()
is_admin = persona.ruolo_sistema == RuoloSistema.admin

st.title("Task")

persone = persona_repo.list_persone(solo_attivi=True)
nomi = {p.id: p.nome_completo for p in persona_repo.list_persone()}
iniziative = iniziativa_repo.list_iniziative()
titoli_ini = {i.id: i.etichetta for i in iniziative}

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
    format_func=lambda i: "(tutte)" if i is None else titoli_ini[i.id],
)
filtro_persona = f3.selectbox(
    "Persona (owner)",
    [None] + persone,
    format_func=lambda p: "(tutte)" if p is None else p.nome_completo,
)
mostra_archiviati = f4.checkbox("Mostra archiviati", value=False)

tasks = task_repo.list_tasks(include_archiviati=mostra_archiviati)
if filtro_stato:
    tasks = [t for t in tasks if t.stato in filtro_stato]
if filtro_ini:
    tasks = [t for t in tasks if t.iniziativa_id == filtro_ini.id]
if filtro_persona:
    tasks = [t for t in tasks if t.owner_id == filtro_persona.id]

if not tasks:
    st.info("Nessun task con i filtri scelti.")
    st.stop()

by_id = {t.id: t for t in task_repo.list_tasks(include_archiviati=True)}
radici = [t for t in tasks if not t.parent_task_id]
subtasks = [t for t in tasks if t.parent_task_id]

st.caption(f"{len(tasks)} task ({len(radici)} principali, {len(subtasks)} subtask)")

for t in sorted(radici, key=lambda x: (x.scadenza or date(9999, 12, 31), x.titolo)):
    riga_task(t, nomi, titoli_ini, persona, is_admin, key_prefix="lst")
    figli = [s for s in subtasks if s.parent_task_id == t.id]
    for s in sorted(figli, key=lambda x: (x.scadenza or date(9999, 12, 31), x.titolo)):
        riga_task(
            s, nomi, titoli_ini, persona, is_admin, key_prefix="lst_s", indent=True
        )
    if task_repo.puo_modificare(t, persona.id, is_admin):
        with st.expander(f"↳ aggiungi subtask a «{t.titolo}»", expanded=False):
            form_nuovo_task(
                persone,
                iniziative,
                default_owner=persona,
                parent=t,
                key=f"sub_{t.id}",
            )

# subtask orfani (padre filtrato fuori): mostrali comunque
orfani = [s for s in subtasks if s.parent_task_id not in {t.id for t in radici}]
if orfani:
    st.markdown("**Subtask (task padre non nei filtri):**")
    for s in orfani:
        riga_task(s, nomi, titoli_ini, persona, is_admin, key_prefix="orf", indent=True)
