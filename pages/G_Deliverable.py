"""Deliverable — prototipi, report e paper dei progetti (spec §13.8).

Livello intermedio della gerarchia: iniziativa → **deliverable** → task →
subtask. Visibilità come i task (regola MAIC tasks): tutti vedono, modificano
owner/supervisor/admin; creazione ed eliminazione restano ad admin/pm.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_login
from src.data import deliverable_repo, iniziativa_repo, persona_repo, task_repo
from src.domain.models import (
    STATI_TASK,
    STATO_TASK_BADGE,
    TIPI_DELIVERABLE,
    TIPO_DELIVERABLE_BADGE,
    RuoloSistema,
)
from src.lib.errori import messaggio_errore_db
from src.lib.labels import etichetta_con_tag
from src.ui.commenti_ui import blocco_commenti
from src.ui.task_ui import form_nuovo_task, riga_task, scadenza_chip

persona = require_login()
is_admin = persona.ruolo_sistema == RuoloSistema.admin
puo_gestire = persona.ruolo_sistema in (RuoloSistema.admin, RuoloSistema.pm)

st.title("Deliverable")
st.caption(
    "I risultati attesi dei progetti — **prototipi**, **report** e **paper** — "
    "con i task che servono a produrli. Gerarchia: progetto → deliverable → "
    "task → subtask."
)

persone = persona_repo.list_persone(solo_attivi=True)
nomi = {p.id: p.nome_completo for p in persona_repo.list_persone()}
iniziative = iniziativa_repo.list_iniziative()
titoli_ini = {i.id: etichetta_con_tag(i) for i in iniziative}

_msg = st.session_state.pop("_msg_deliv", None)
if _msg:
    st.success(_msg)


def _puo_modificare(d) -> bool:
    """Modifica: owner, supervisor o admin (come i task)."""
    return is_admin or persona.id in (d.owner_id, d.supervisor_id)


# --- Dialog -------------------------------------------------------------------
@st.dialog("Dettagli deliverable", width="large")
def _dialog_deliverable(d, tasks_collegati: list) -> None:
    st.markdown(f"### 📦 {d.titolo}")
    st.caption(
        f"{titoli_ini.get(d.iniziativa_id, '—')} · "
        f"{TIPO_DELIVERABLE_BADGE.get(d.tipo, '📦 —')} · "
        f"{STATO_TASK_BADGE.get(d.stato, d.stato)} · {scadenza_chip(d.scadenza)}"
    )
    if not _puo_modificare(d):
        if d.descrizione:
            st.markdown(d.descrizione)
        st.info(
            "Sola lettura: puoi modificare solo i deliverable di cui sei "
            "owner o supervisor."
        )
    else:
        with st.form(f"mod_deliv_{d.id}"):
            c1, c2, c3 = st.columns(3)
            n_tit = c1.text_input("Titolo *", value=d.titolo)
            n_tipo = c2.selectbox(
                "Tipo",
                TIPI_DELIVERABLE,
                index=(
                    TIPI_DELIVERABLE.index(d.tipo) if d.tipo in TIPI_DELIVERABLE else 0
                ),
                format_func=lambda t: TIPO_DELIVERABLE_BADGE[t],
            )
            n_scad = c3.date_input("Scadenza", value=d.scadenza)
            c4, c5, c6 = st.columns(3)
            n_stato = c4.selectbox(
                "Stato",
                STATI_TASK,
                index=STATI_TASK.index(d.stato) if d.stato in STATI_TASK else 0,
                format_func=lambda s: STATO_TASK_BADGE[s],
            )
            idx_o = next((i for i, p in enumerate(persone) if p.id == d.owner_id), None)
            n_own = c5.selectbox(
                "Owner",
                [None] + persone,
                index=(idx_o + 1) if idx_o is not None else 0,
                format_func=lambda p: "—" if p is None else p.nome_completo,
            )
            idx_s = next(
                (i for i, p in enumerate(persone) if p.id == d.supervisor_id), None
            )
            n_sup = c6.selectbox(
                "Supervisor",
                [None] + persone,
                index=(idx_s + 1) if idx_s is not None else 0,
                format_func=lambda p: "—" if p is None else p.nome_completo,
            )
            n_desc = st.text_area("Descrizione", value=d.descrizione or "")
            if st.form_submit_button("💾 Salva", type="primary"):
                if not n_tit:
                    st.error("Il titolo è obbligatorio.")
                else:
                    try:
                        deliverable_repo.update_deliverable(
                            d.id,
                            titolo=n_tit,
                            tipo=n_tipo,
                            stato=n_stato,
                            scadenza=n_scad,
                            owner_id=n_own.id if n_own else None,
                            supervisor_id=n_sup.id if n_sup else None,
                            descrizione=n_desc or None,
                        )
                    except Exception as exc:  # noqa: BLE001
                        st.error(messaggio_errore_db(exc))
                    else:
                        st.session_state["_msg_deliv"] = "Deliverable aggiornato."
                        st.rerun()

    st.divider()
    st.markdown(f"**Task collegati** ({len(tasks_collegati)})")
    if tasks_collegati:
        for t in tasks_collegati:
            st.markdown(
                f"- **{t.titolo}** · {STATO_TASK_BADGE.get(t.stato, t.stato)} · "
                f"{scadenza_chip(t.scadenza)} · 👤 {nomi.get(t.owner_id, '—')}"
            )
        st.caption("Per aprire un task usa «Dettagli» nell'elenco qui sotto o in Task.")
    else:
        st.caption("Nessun task collegato: creane uno dall'elenco qui sotto.")

    st.divider()
    blocco_commenti("deliverable", d.id, persona, is_admin, nomi)


@st.dialog("Elimina deliverable")
def _dialog_elimina(d, n_task: int) -> None:
    st.markdown(f"Stai per eliminare **📦 {d.titolo}**.")
    if n_task:
        st.warning(
            f"I **{n_task} task** collegati NON vengono eliminati: restano nel "
            "progetto, senza deliverable."
        )
    else:
        st.warning("L'operazione è irreversibile.")
    conferma = st.checkbox(f"Confermo l'eliminazione di «{d.titolo}»")
    b1, b2 = st.columns(2)
    if b1.button(
        "🗑 Elimina definitivamente",
        type="primary",
        disabled=not conferma,
        use_container_width=True,
    ):
        try:
            deliverable_repo.delete_deliverable(d.id)
        except Exception as exc:  # noqa: BLE001
            st.error(messaggio_errore_db(exc))
        else:
            st.session_state["_msg_deliv"] = f"Deliverable «{d.titolo}» eliminato."
            st.rerun()
    if b2.button("Annulla", use_container_width=True):
        st.rerun()


# --- Nuovo deliverable --------------------------------------------------------
progetti = [i for i in iniziative if i.tipo == "progetto"]
if puo_gestire:
    with st.expander("➕ Nuovo deliverable", expanded=not progetti):
        if not progetti:
            st.info("Non ci sono progetti: creane uno da Proposte → approvazione.")
        else:
            with st.form("nuovo_deliverable", clear_on_submit=True):
                f1, f2 = st.columns([3, 2])
                n_tit = f1.text_input("Titolo *", placeholder="es. D2.1 Report finale")
                n_ini = f2.selectbox(
                    "Progetto *",
                    progetti,
                    format_func=lambda i: titoli_ini[i.id],
                )
                f3, f4, f5 = st.columns(3)
                n_tipo = f3.selectbox(
                    "Tipo",
                    TIPI_DELIVERABLE,
                    format_func=lambda t: TIPO_DELIVERABLE_BADGE[t],
                )
                n_scad = f4.date_input("Scadenza", value=None)
                n_own = f5.selectbox(
                    "Owner",
                    [None] + persone,
                    format_func=lambda p: "—" if p is None else p.nome_completo,
                )
                n_desc = st.text_area("Descrizione (opz.)")
                if st.form_submit_button("Crea deliverable", type="primary"):
                    if not n_tit:
                        st.error("Il titolo è obbligatorio.")
                    else:
                        try:
                            deliverable_repo.create_deliverable(
                                n_ini.id,
                                n_tit,
                                tipo=n_tipo,
                                scadenza=n_scad,
                                owner_id=n_own.id if n_own else None,
                                descrizione=n_desc or None,
                            )
                        except Exception as exc:  # noqa: BLE001
                            st.error(messaggio_errore_db(exc))
                        else:
                            st.session_state["_msg_deliv"] = "Deliverable creato."
                            st.rerun()
else:
    st.caption(
        "I deliverable sono creati da amministratori e responsabili di progetto."
    )

# --- Filtri -------------------------------------------------------------------
f1, f2, f3, f4 = st.columns(4)
filtro_ini = f1.selectbox(
    "Progetto",
    [None] + progetti,
    format_func=lambda i: "(tutti)" if i is None else titoli_ini[i.id],
)
filtro_tipo = f2.multiselect(
    "Tipo",
    TIPI_DELIVERABLE,
    format_func=lambda t: TIPO_DELIVERABLE_BADGE[t],
)
filtro_stato = f3.multiselect(
    "Stato",
    STATI_TASK,
    default=["da_fare", "in_corso", "bloccato"],
    format_func=lambda s: STATO_TASK_BADGE[s],
)
solo_miei = f4.checkbox("Solo i miei", value=False, help="Owner o supervisor sono io.")
mostra_arch = f4.checkbox("Mostra archiviati", value=False)

tutti = deliverable_repo.list_deliverables(include_archiviati=mostra_arch)
avanz = deliverable_repo.avanzamento_task()
tasks = task_repo.list_tasks(include_archiviati=False)

delivs = tutti
if filtro_ini:
    delivs = [d for d in delivs if d.iniziativa_id == filtro_ini.id]
if filtro_tipo:
    delivs = [d for d in delivs if (d.tipo or "altro") in filtro_tipo]
if filtro_stato:
    delivs = [d for d in delivs if d.stato in filtro_stato]
if solo_miei:
    delivs = [d for d in delivs if persona.id in (d.owner_id, d.supervisor_id)]

# --- Metriche -----------------------------------------------------------------
oggi = date.today()
attivi = [d for d in tutti if d.stato in ("da_fare", "in_corso", "bloccato")]
m1, m2, m3, m4 = st.columns(4)
m1.metric("Deliverable attivi", len(attivi))
m2.metric("Completati", sum(1 for d in tutti if d.stato == "completato"))
m3.metric(
    "In ritardo",
    sum(1 for d in attivi if d.scadenza and d.scadenza < oggi),
    delta_color="inverse",
)
m4.metric(
    "In scadenza (30 gg)",
    sum(1 for d in attivi if d.scadenza and 0 <= (d.scadenza - oggi).days <= 30),
    help="Deliverable attivi con scadenza entro un mese.",
)

if not tutti:
    st.info(
        "Nessun deliverable. Creane uno con **➕ Nuovo deliverable**: i "
        "deliverable sono i risultati attesi del progetto (prototipo, report, "
        "paper) e raccolgono i task che servono a produrli."
    )
    st.stop()
if not delivs:
    st.info("Nessun deliverable con i filtri scelti.")
    st.stop()

# --- Elenco per progetto ------------------------------------------------------
per_progetto: dict = {}
for d in delivs:
    per_progetto.setdefault(d.iniziativa_id, []).append(d)

for ini_id, lista in per_progetto.items():
    st.subheader(titoli_ini.get(ini_id, "—"))
    for d in sorted(lista, key=lambda x: (x.scadenza or date(9999, 12, 31), x.titolo)):
        av = avanz.get(str(d.id), {"totali": 0, "completati": 0, "in_ritardo": 0})
        d_tasks = [t for t in tasks if t.deliverable_id == d.id]
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([5.5, 2.2, 1.1, 1.1])
            c1.markdown(
                f"**📦 {d.titolo}**  \n<small>"
                f"{TIPO_DELIVERABLE_BADGE.get(d.tipo, '📦 —')} · "
                f"{STATO_TASK_BADGE.get(d.stato, d.stato)} · "
                f"{scadenza_chip(d.scadenza)} · 👤 {nomi.get(d.owner_id, '—')}"
                + (
                    f" · 👁 {nomi.get(d.supervisor_id)}"
                    if d.supervisor_id and d.supervisor_id != d.owner_id
                    else ""
                )
                + "</small>",
                unsafe_allow_html=True,
            )
            tot, fatti = av["totali"], av["completati"]
            c2.progress(
                (fatti / tot) if tot else 0.0,
                text=f"{fatti}/{tot} task"
                + (f" · {av['in_ritardo']} in ritardo" if av["in_ritardo"] else ""),
            )
            if c3.button("Dettagli", key=f"det_{d.id}", use_container_width=True):
                _dialog_deliverable(d, d_tasks)
            if puo_gestire and c4.button(
                "🗑", key=f"del_{d.id}", help="Elimina il deliverable (con conferma)"
            ):
                _dialog_elimina(d, len(d_tasks))
            with st.expander(f"Task del deliverable ({len(d_tasks)})"):
                for t in sorted(
                    [x for x in d_tasks if not x.parent_task_id],
                    key=lambda x: (x.scadenza or date(9999, 12, 31), x.titolo),
                ):
                    _figli = [x for x in d_tasks if x.parent_task_id == t.id]
                    riga_task(
                        t,
                        nomi,
                        titoli_ini,
                        persona,
                        is_admin,
                        key_prefix=f"dl{d.id}",
                        subtask=(
                            sum(1 for x in _figli if x.stato == "completato"),
                            len(_figli),
                        ),
                    )
                    for s in sorted(
                        [x for x in d_tasks if x.parent_task_id == t.id],
                        key=lambda x: (x.scadenza or date(9999, 12, 31), x.titolo),
                    ):
                        riga_task(
                            s,
                            nomi,
                            titoli_ini,
                            persona,
                            is_admin,
                            key_prefix=f"dls{d.id}",
                            indent=True,
                        )
                ini = next((i for i in iniziative if i.id == d.iniziativa_id), None)
                if ini is not None:
                    with st.expander("➕ Nuovo task in questo deliverable"):
                        form_nuovo_task(
                            persone,
                            iniziative,
                            default_owner=persona,
                            iniziativa_fissa=ini,
                            deliverable_fissa=d,
                            key=f"ntd_{d.id}",
                        )

st.divider()
st.caption(
    f"Riepilogo: **{len(delivs)}** deliverable visualizzati su **{len(tutti)}** totali."
)
with st.expander("📋 Tabella riepilogativa"):
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Progetto": titoli_ini.get(d.iniziativa_id, ""),
                    "Deliverable": d.titolo,
                    "Tipo": TIPO_DELIVERABLE_BADGE.get(d.tipo, "—"),
                    "Stato": STATO_TASK_BADGE.get(d.stato, d.stato),
                    "Scadenza": f"{d.scadenza:%d/%m/%Y}" if d.scadenza else "",
                    "Owner": nomi.get(d.owner_id, ""),
                    "Task completati": (
                        f"{avanz.get(str(d.id), {}).get('completati', 0)}/"
                        f"{avanz.get(str(d.id), {}).get('totali', 0)}"
                    ),
                }
                for d in delivs
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
