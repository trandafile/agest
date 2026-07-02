"""Calendario — scadenze di task, deliverable e milestone (stile MAIC tasks)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.auth.session import require_login
from src.data import calendario_repo, iniziativa_repo, persona_repo
from src.domain.models import RuoloSistema
from src.domain.timesheet import GIORNI_IT
from src.lib.calendario import (
    TIPO_ICONA,
    build_ics,
    eventi_per_giorno,
    link_google_calendar,
    settimane_mese,
)
from src.lib.labels import etichetta_con_tag

persona = require_login()

st.title("Calendario")

# --- Filtri -----------------------------------------------------------------
oggi = date.today()
c1, c2, c3, c4 = st.columns([1, 1, 2, 2])
anno = c1.selectbox("Anno", range(oggi.year - 1, oggi.year + 3), index=1)
mese = c2.selectbox(
    "Mese", range(1, 13), index=oggi.month - 1, format_func=lambda m: f"{m:02d}"
)
tipi = c3.multiselect(
    "Tipo",
    ["task", "deliverable", "milestone"],
    default=["task", "deliverable", "milestone"],
    format_func=lambda t: f"{TIPO_ICONA[t]} {t}",
)
persone = persona_repo.list_persone()
nomi = {p.id: p.nome_completo for p in persone}
solo_mie = persona.ruolo_sistema == RuoloSistema.dipendente
if not solo_mie:
    filtro_p = c4.selectbox(
        "Persona",
        [None] + persone,
        format_func=lambda p: "(tutte)" if p is None else p.nome_completo,
    )
else:
    filtro_p = persona
    c4.markdown(f"**Persona:** {persona.nome_completo}")

iniziative = iniziativa_repo.list_iniziative()
filtro_prog = st.selectbox(
    "Progetto",
    [None] + iniziative,
    format_func=lambda i: "(tutti)" if i is None else etichetta_con_tag(i),
)

tutti = calendario_repo.eventi()
eventi = [e for e in tutti if e["tipo"] in tipi]
if filtro_p is not None:
    eventi = [e for e in eventi if e["owner_id"] == filtro_p.id]
if filtro_prog is not None:
    etichette_prog = {
        (filtro_prog.acronimo or "").strip(),
        (filtro_prog.titolo or "").strip(),
    }
    eventi = [e for e in eventi if (e.get("progetto") or "") in etichette_prog]

# --- Griglia mensile ---------------------------------------------------------
del_mese = [e for e in eventi if e["data"].year == anno and e["data"].month == mese]
per_giorno = eventi_per_giorno(del_mese)

_MESI = [
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
]
st.markdown(f"### {_MESI[mese - 1]} {anno}")
intest = st.columns(7)
for i, g in enumerate(GIORNI_IT):
    intest[i].markdown(f"**{g}**")

for settimana in settimane_mese(anno, mese):
    cols = st.columns(7)
    for i, giorno in enumerate(settimana):
        with cols[i]:
            if giorno is None:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                continue
            oggi_mark = "🔵 " if giorno == oggi else ""
            st.markdown(f"{oggi_mark}**{giorno.day}**")
            for e in per_giorno.get(giorno, []):
                ic = TIPO_ICONA.get(e["tipo"], "")
                pag = " 💰" if e.get("pagamento") else ""
                ritardo = "🔴" if giorno < oggi else ""
                st.caption(
                    f"{ritardo}{ic} {e['titolo'][:22]}{pag}"
                    + (f" · {e['progetto']}" if e.get("progetto") else "")
                )

# --- Agenda + export ---------------------------------------------------------
st.divider()
col_a, col_b = st.columns([3, 1])
col_a.subheader("Agenda (prossime scadenze)")
futuri = sorted([e for e in eventi if e["data"] >= oggi], key=lambda e: e["data"])[:40]
if futuri:
    for e in futuri:
        ic = TIPO_ICONA.get(e["tipo"], "")
        pag = " 💰" if e.get("pagamento") else ""
        delta = (e["data"] - oggi).days
        quando = "oggi" if delta == 0 else (f"tra {delta}g" if delta > 0 else "")
        titolo_ev = f"{ic} {e['titolo']}" + (
            f" [{e['progetto']}]" if e.get("progetto") else ""
        )
        gcal = link_google_calendar(titolo_ev, e["data"])
        col_a.markdown(
            f"- **{e['data']:%d/%m/%Y}** ({quando}) {ic} {e['titolo']}{pag}"
            + (f" · _{e['progetto']}_" if e.get("progetto") else "")
            + (f" · 👤 {nomi.get(e['owner_id'], '')}" if e.get("owner_id") else "")
            + f" · [➕ Google Calendar]({gcal})"
        )
else:
    col_a.info("Nessuna scadenza futura con i filtri scelti.")

ics = build_ics(sorted(eventi, key=lambda e: e["data"]))
col_b.download_button(
    "📅 Esporta .ics",
    ics.encode("utf-8"),
    "antecnica_calendario.ics",
    "text/calendar",
    help="Importabile in Google Calendar / Outlook.",
)
