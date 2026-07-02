"""Presenze — foglio mensile: una riga per giorno, con note e task lavorati.

Registro informativo di ingressi/uscite: NON alimenta i timesheet.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_login
from src.data import persona_repo, presenze_repo, task_repo
from src.domain.models import RuoloSistema
from src.domain.timesheet import GIORNI_IT, giorni_del_mese, is_lavorativo

persona = require_login()

st.title("Presenze")
st.caption(
    "Foglio mensile con una riga per giorno. Le presenze sono un registro "
    "informativo e **non fanno fede per i timesheet**."
)

oggi = date.today()
c1, c2, c3 = st.columns([2, 1, 1])
if persona.ruolo_sistema == RuoloSistema.admin:
    persone = persona_repo.list_persone(solo_attivi=True)
elif persona.ruolo_sistema == RuoloSistema.pm:
    assegnate = persona_repo.list_persone_assegnate_a_pm(persona.id)
    persone = [persona] + [p for p in assegnate if p.id != persona.id]
else:
    persone = []

if persone:
    sel = c1.selectbox(
        "Persona",
        options=persone,
        index=next((i for i, p in enumerate(persone) if p.id == persona.id), 0),
        format_func=lambda p: p.nome_completo,
    )
else:
    sel = persona
    c1.markdown(f"**Persona:** {persona.nome_completo}")
anno = c2.selectbox("Anno", options=range(oggi.year - 2, oggi.year + 2), index=2)
mese = c3.selectbox(
    "Mese",
    options=range(1, 13),
    index=oggi.month - 1,
    format_func=lambda m: f"{m:02d}",
)

puo_scrivere = sel.id == persona.id or persona.ruolo_sistema == RuoloSistema.admin

# --- Foglio mensile -----------------------------------------------------------
giorni = giorni_del_mese(anno, mese)
festivita = presenze_repo.festivita_set(anno)
esistenti = presenze_repo.presenze_mese_map(sel.id, anno, mese)
task_map = presenze_repo.tasks_mese_map(sel.id, anno, mese)
tutti_task = {str(t.id): t for t in task_repo.list_tasks(include_archiviati=True)}


def _etichetta(g: date) -> str:
    segno = "" if is_lavorativo(g, festivita) else " 🔸"
    return f"{g.day:02d} {GIORNI_IT[g.isoweekday() - 1]}{segno}"


righe = []
for g in giorni:
    p = esistenti.get(g)
    n_task = len(task_map.get(g, []))
    righe.append(
        {
            "Giorno": _etichetta(g),
            "Ingresso": p.ora_ingresso if p else None,
            "Uscita": p.ora_uscita if p else None,
            "Ore": float(p.ore_totali) if p and p.ore_totali is not None else None,
            "Tipo": (p.tipo if p else None),
            "Note": (p.note or "") if p else "",
            "Task": f"🗂 {n_task}" if n_task else "",
        }
    )

df = pd.DataFrame(righe).set_index("Giorno")
df_edit = st.data_editor(
    df,
    column_config={
        "Ingresso": st.column_config.TimeColumn("Ingresso", format="HH:mm"),
        "Uscita": st.column_config.TimeColumn("Uscita", format="HH:mm"),
        "Ore": st.column_config.NumberColumn("Ore", disabled=True, format="%.2f"),
        "Tipo": st.column_config.SelectboxColumn(
            "Tipo", options=["ufficio", "remoto", "trasferta"]
        ),
        "Note": st.column_config.TextColumn("Note", width="large"),
        "Task": st.column_config.TextColumn("Task", disabled=True, width="small"),
    },
    disabled=not puo_scrivere,
    use_container_width=True,
    height=min(38 * (len(giorni) + 1), 900),
    key=f"presenze_{sel.id}_{anno}_{mese}",
)

tot_ore = sum(float(p.ore_totali or 0) for p in esistenti.values())
n_giorni_reg = len(esistenti)
st.caption(f"Registrati **{n_giorni_reg}** giorni, totale **{tot_ore:g} h**.")

if puo_scrivere and st.button("💾 Salva presenze del mese", type="primary"):
    salvate = 0
    for g in giorni:
        riga = df_edit.loc[_etichetta(g)]
        ingresso = riga["Ingresso"] if pd.notna(riga["Ingresso"]) else None
        uscita = riga["Uscita"] if pd.notna(riga["Uscita"]) else None
        tipo = riga["Tipo"] if pd.notna(riga["Tipo"]) else None
        note = (riga["Note"] or "").strip() or None
        if ingresso or uscita or note or tipo:
            presenze_repo.upsert_presenza_giorno(
                sel.id, g, ingresso, uscita, tipo or "ufficio", note
            )
            salvate += 1
        elif g in esistenti and not task_map.get(g):
            presenze_repo.delete_presenza(esistenti[g].id)
    st.success(f"Salvate {salvate} giornate.")
    st.rerun()

# --- Task lavorati (popup) -------------------------------------------------------
st.divider()
st.markdown("**Task lavorati** (informativo, per giorno)")


@st.dialog("Task lavorati nel giorno")
def _dialog_task(giorno: date) -> None:
    p = presenze_repo.presenze_mese_map(sel.id, anno, mese).get(giorno)
    attuali = presenze_repo.tasks_presenza(p.id) if p else []
    opzioni = {tid: t for tid, t in tutti_task.items() if t.attivo or tid in attuali}
    scelti = st.multiselect(
        f"Task su cui hai lavorato il {giorno:%d/%m/%Y}",
        options=list(opzioni),
        default=[tid for tid in attuali if tid in opzioni],
        format_func=lambda tid: opzioni[tid].titolo,
    )
    if st.button("Salva", type="primary"):
        if p is None:
            p = presenze_repo.upsert_presenza_giorno(
                sel.id, giorno, None, None, "ufficio", None
            )
        presenze_repo.set_tasks_presenza(p.id, scelti)
        st.rerun()


d1, d2 = st.columns([1, 2])
giorno_sel = d1.selectbox(
    "Giorno",
    giorni,
    index=(
        min(oggi.day - 1, len(giorni) - 1)
        if (anno, mese) == (oggi.year, oggi.month)
        else 0
    ),
    format_func=lambda g: f"{g:%d/%m/%Y}",
)
if d2.button("🗂 Seleziona task del giorno…", disabled=not puo_scrivere):
    _dialog_task(giorno_sel)

per_giorno = task_map.get(giorno_sel, [])
if per_giorno:
    st.markdown(
        "\n".join(
            f"- {tutti_task[tid].titolo}" for tid in per_giorno if tid in tutti_task
        )
    )
