"""Timesheet — griglia mensile (spec §5): righe = assegnazioni, colonne = giorni.

Salvataggio SOLO alla CONFERMA (che blocca il mese). Regole validate sia
client-side (feedback immediato) sia dai trigger a DB (enforcement).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_login, sidebar_utente
from src.data import persona_repo, presenze_repo, timesheet_repo
from src.domain.models import RuoloSistema
from src.domain.timesheet import (
    etichetta_giorno,
    giorni_del_mese,
    is_lavorativo,
    riga_valida,
    valida_griglia,
)

st.set_page_config(page_title="Timesheet — ANTECNICA", page_icon="🗓️", layout="wide")
persona = require_login()
sidebar_utente(persona)

st.title("Timesheet")

# --- Selettori mese/anno/persona -----------------------------------------
oggi = date.today()
c1, c2, c3 = st.columns([2, 1, 1])

if persona.ruolo_sistema == RuoloSistema.admin:
    persone = persona_repo.list_persone(solo_attivi=True)
elif persona.ruolo_sistema == RuoloSistema.pm:
    # il pm vede sé stesso + le persone assegnate alle sue iniziative (§3)
    assegnate = persona_repo.list_persone_assegnate_a_pm(persona.id)
    persone = [persona] + [p for p in assegnate if p.id != persona.id]
else:
    persone = []

if persone:
    sel_persona = c1.selectbox(
        "Persona",
        options=persone,
        index=next((i for i, p in enumerate(persone) if p.id == persona.id), 0),
        format_func=lambda p: p.nome_completo,
    )
else:
    sel_persona = persona
    c1.markdown(f"**Persona:** {persona.nome_completo}")

anno = c2.selectbox("Anno", options=range(oggi.year - 2, oggi.year + 2), index=2)
mese = c3.selectbox(
    "Mese",
    options=range(1, 13),
    index=oggi.month - 1,
    format_func=lambda m: f"{m:02d}",
)

puo_editare_altri = persona.ruolo_sistema == RuoloSistema.admin
editabile_da_utente = sel_persona.id == persona.id or puo_editare_altri

# --- Dati -----------------------------------------------------------------
assegnazioni = timesheet_repo.assegnazioni_attive(sel_persona.id, anno, mese)
stato = timesheet_repo.stato_mese(sel_persona.id, anno, mese)
festivita = presenze_repo.festivita_set(anno)
giorni = giorni_del_mese(anno, mese)
ore_db = timesheet_repo.ore_mese(sel_persona.id, anno, mese)
ore_annue = timesheet_repo.ore_annuali(sel_persona.id, anno)

m1, m2, m3 = st.columns(3)
m1.metric(f"Ore progettuali {anno}", f"{ore_annue} h")
m2.metric("Stato mese", "🔒 confermato" if stato == "confermato" else "✏️ bozza")
m3.metric("Assegnazioni attive", len(assegnazioni))

if not assegnazioni:
    st.info(
        "Nessuna assegnazione attiva in questo mese. Le assegnazioni si "
        "creano dalle pagine Proposte/Progetti (admin)."
    )
    st.stop()

# --- Griglia ---------------------------------------------------------------
info_by_id = {a.id: a for a in assegnazioni}
etichette = {a.id: f"{a.titolo} [{a.tipo_attivita}]" for a in assegnazioni}
col_giorni = [etichetta_giorno(g) for g in giorni]
giorno_by_col = dict(zip(col_giorni, giorni, strict=True))

# valori esistenti dal DB
val0 = {(str(o.assegnazione_id), o.data): o.ore for o in ore_db}
df = pd.DataFrame(
    [
        {
            "Attività": etichette[a.id],
            **{etichetta_giorno(g): val0.get((a.id, g), 0) for g in giorni},
        }
        for a in assegnazioni
    ]
).set_index("Attività")

non_lavorativi = {
    etichetta_giorno(g) for g in giorni if not is_lavorativo(g, festivita)
}
forza = st.checkbox(
    "Consenti ore su weekend/festività (flag esplicito)",
    value=False,
    disabled=stato == "confermato",
)

colcfg = {
    c: st.column_config.NumberColumn(
        c + (" 🔸" if c in non_lavorativi else ""),
        min_value=0,
        max_value=8,
        step=1,
        width="small",
        disabled=(c in non_lavorativi and not forza),
    )
    for c in col_giorni
}

editabile = stato == "bozza" and editabile_da_utente
df_edit = st.data_editor(
    df,
    column_config=colcfg,
    disabled=not editabile,
    use_container_width=True,
    key=f"griglia_{sel_persona.id}_{anno}_{mese}",
)

# --- Ricostruzione celle e riepiloghi --------------------------------------
ore: dict[tuple[str, date], int] = {}
for a in assegnazioni:
    riga = df_edit.loc[etichette[a.id]]
    for c in col_giorni:
        v = int(riga[c] or 0)
        if v > 0:
            ore[(a.id, giorno_by_col[c])] = v

tot_riga = {
    a.id: sum(v for (x, _), v in ore.items() if x == a.id) for a in assegnazioni
}
riepilogo = pd.DataFrame(
    [
        {
            "Attività": etichette[a.id],
            "Periodo": (f"{a.data_inizio:%d/%m/%y}" if a.data_inizio else "—")
            + " → "
            + (f"{a.data_fine:%d/%m/%y}" if a.data_fine else "—"),
            "Ore iniziativa": (
                f"{a.ore_totali_iniziativa:g}" if a.ore_totali_iniziativa else "—"
            ),
            "Totale mese": tot_riga[a.id],
            "Max mese": f"{a.tetto_ore_mese:g}" if a.tetto_ore_mese else "—",
            "OK": "🟢" if riga_valida(ore, a) else "🔴",
        }
        for a in assegnazioni
    ]
)
st.dataframe(riepilogo, hide_index=True, use_container_width=True)

tot_giorno_row = pd.DataFrame(
    [
        {
            c: sum(v for (_, g), v in ore.items() if g == giorno_by_col[c])
            for c in col_giorni
        }
    ],
    index=["Totale giorno"],
)
st.dataframe(tot_giorno_row, use_container_width=True)
st.caption(f"Totale mese: **{sum(ore.values())} h**")

# --- CONFERMA ----------------------------------------------------------------
if editabile:
    st.divider()
    esito = valida_griglia(
        ore, info_by_id, festivita, stato_mese=stato, forza_non_lavorativi=forza
    )
    if not esito.valido:
        for e in esito.errori:
            st.error(e)
    conferma = st.button(
        "✅ CONFERMA mese (salva e blocca)",
        type="primary",
        disabled=not esito.valido,
    )
    if conferma:
        righe = [
            {
                "assegnazione_id": aid,
                "data": g.isoformat(),
                "ore": v,
                "forzato": forza and not is_lavorativo(g, festivita),
            }
            for (aid, g), v in ore.items()
        ]
        try:
            timesheet_repo.conferma_mese(
                sel_persona.id,
                anno,
                mese,
                righe,
                eseguito_da=st.session_state.get("user_email"),
            )
            st.success(f"Mese {mese:02d}/{anno} confermato e bloccato.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Conferma rifiutata dal server: {exc}")
elif stato == "confermato":
    st.info("Mese confermato: i dati sono bloccati.")
    if persona.ruolo_sistema == RuoloSistema.admin and st.button(
        "🔓 Riapri mese (admin, tracciato in audit)"
    ):
        timesheet_repo.riapri_mese(
            sel_persona.id,
            anno,
            mese,
            eseguito_da=st.session_state.get("user_email"),
        )
        st.rerun()
