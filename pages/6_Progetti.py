"""Progetti — esecuzione post-award (spec §7): baseline vs consuntivo, quote.

Vista economica riservata: admin (scrittura) e pm (lettura dei propri).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from src.auth.session import require_role, sidebar_utente
from src.data import iniziativa_repo, progetti_repo
from src.domain.economia import (
    PianoPersona,
    consuntivo_personale,
    quote_rimanenti,
    rollup_personale,
)
from src.domain.models import RuoloSistema

st.set_page_config(page_title="Progetti — ANTECNICA", page_icon="📊", layout="wide")
persona = require_role(RuoloSistema.admin, RuoloSistema.pm)
sidebar_utente(persona)
is_admin = persona.ruolo_sistema == RuoloSistema.admin

st.title("Progetti")

progetti = iniziativa_repo.list_iniziative(tipo="progetto")
if not is_admin:
    progetti = [p for p in progetti if p.responsabile_id == persona.id]

if not progetti:
    st.info("Nessun progetto. I progetti nascono dall'approvazione delle proposte.")
    st.stop()

st.dataframe(
    pd.DataFrame(
        [
            {
                "Codice": p.codice or "",
                "Titolo": p.titolo,
                "Controparte": p.controparte or "",
                "Stato": "🟢 attivo" if p.stato == "attivo" else "⚫ chiuso",
                "Inizio": f"{p.data_inizio:%d/%m/%Y}" if p.data_inizio else "",
                "Fine": f"{p.data_fine:%d/%m/%Y}" if p.data_fine else "",
                "Budget €": float(p.budget_totale or 0),
            }
            for p in progetti
        ]
    ),
    hide_index=True,
    use_container_width=True,
)

sel = st.selectbox(
    "Dettaglio progetto",
    options=progetti,
    format_func=lambda p: f"[{p.stato}] {p.codice or ''} {p.titolo}",
)
alla_data = sel.data_inizio or date.today()

# --- Dati economici -----------------------------------------------------------
piani_rows = progetti_repo.piani_iniziativa(sel.id)
piani = [
    PianoPersona(
        persona_id=str(r["persona_id"]),
        nome=r["nome"],
        tipo_attivita=r["tipo_attivita"],
        ore=Decimal(r["ore_pianificate"] or 0),
        work_package=r["work_package"],
    )
    for r in piani_rows
]
tariffe = progetti_repo.tariffe_by_persona([p.persona_id for p in piani] or None)
roll = rollup_personale(piani, tariffe, alla_data)
ore_cons = progetti_repo.ore_consuntivo(sel.id)
costo_cons_personale = consuntivo_personale(ore_cons, tariffe)
budget_cat = progetti_repo.budget_per_categoria(sel.id)
speso_cat = progetti_repo.speso_per_categoria(sel.id)

# baseline personale: voce esplicita se presente, altrimenti roll-up pianificato
if "personale" not in budget_cat and roll["totale"] > 0:
    budget_cat["personale"] = roll["totale"]

quote = quote_rimanenti(
    budget=budget_cat,
    impegnato={},
    speso={
        **speso_cat,
        "personale": speso_cat.get("personale", Decimal("0")) + costo_cons_personale,
    },
)

# --- Riepilogo -----------------------------------------------------------------
tot_budget = sum(q["budget"] for q in quote.values())
tot_speso = sum(q["speso"] for q in quote.values())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Budget (baseline)", f"{tot_budget:,.2f} €")
c2.metric("Speso (consuntivo)", f"{tot_speso:,.2f} €")
c3.metric(
    "Quota rimanente",
    f"{tot_budget - tot_speso:,.2f} €",
    delta=None,
)
c4.metric(
    "Avanzamento spesa",
    f"{(tot_speso / tot_budget * 100):.0f}%" if tot_budget else "—",
)
ore_tot_cons = sum(o for (_, _, o) in ore_cons)
st.caption(
    f"Ore a timesheet: **{ore_tot_cons} h** → costo personale consuntivo "
    f"**{costo_cons_personale:,.2f} €** (tariffe vigenti alla data)."
)

tab_quote, tab_ms, tab_stato = st.tabs(
    ["💶 Budget vs consuntivo", "🎯 Milestone", "🚦 Stato"]
)

with tab_quote:
    if quote:
        df_q = pd.DataFrame(
            [
                {
                    "Categoria": cat,
                    "Budget €": float(v["budget"]),
                    "Speso €": float(v["speso"]),
                    "Rimanente €": float(v["rimanente"]),
                    "": "🔴" if v["rimanente"] < 0 else "🟢",
                }
                for cat, v in sorted(quote.items())
            ]
        )
        st.dataframe(df_q, hide_index=True, use_container_width=True)
        for cat, v in quote.items():
            if v["rimanente"] < 0:
                st.error(
                    f"⚠️ Overrun sulla categoria «{cat}»: "
                    f"{float(v['rimanente']):,.2f} €"
                )
    else:
        st.info("Nessuna voce di budget: aggiungile dalla proposta/progetto.")
    if roll["per_persona"]:
        st.markdown("**Baseline personale per persona** (pianificato)")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Persona": k, "Costo pianificato €": float(v)}
                    for k, v in roll["per_persona"].items()
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )

with tab_ms:
    ms = progetti_repo.list_milestones(sel.id)
    if is_admin:
        with st.form("nuova_ms", clear_on_submit=True):
            f1, f2, f3 = st.columns(3)
            titolo = f1.text_input("Titolo *")
            quando = f2.date_input("Data prevista", value=date.today())
            incasso = f3.number_input("Incasso previsto €", min_value=0.0, step=500.0)
            if st.form_submit_button("Aggiungi milestone") and titolo:
                progetti_repo.create_milestone(sel.id, titolo, quando, incasso or None)
                st.rerun()
    if ms:
        icone = {"prevista": "⏳", "completata": "✅", "slittata": "🔶"}
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Milestone": m.titolo,
                        "Prevista": (
                            f"{m.data_prevista:%d/%m/%Y}" if m.data_prevista else ""
                        ),
                        "Incasso €": float(m.importo_incasso or 0) or None,
                        "Stato": f"{icone[m.stato]} {m.stato}",
                    }
                    for m in ms
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        incassi_previsti = sum(float(m.importo_incasso or 0) for m in ms)
        incassi_maturati = sum(
            float(m.importo_incasso or 0) for m in ms if m.stato == "completata"
        )
        st.caption(
            f"Incassi previsti da milestone: **{incassi_previsti:,.2f} €**, "
            f"maturati (completate): **{incassi_maturati:,.2f} €**"
        )
        if is_admin:
            m_sel = st.selectbox(
                "Aggiorna stato milestone",
                options=[None] + ms,
                format_func=lambda m: "—" if m is None else m.titolo,
            )
            if m_sel:
                nuovo = st.selectbox(
                    "Nuovo stato",
                    ["prevista", "completata", "slittata"],
                    index=["prevista", "completata", "slittata"].index(m_sel.stato),
                )
                if st.button("Aggiorna"):
                    progetti_repo.set_stato_milestone(m_sel.id, nuovo)
                    st.rerun()
    else:
        st.info("Nessuna milestone.")

with tab_stato:
    if is_admin:
        if sel.stato == "attivo":
            if st.button("⚫ Chiudi progetto"):
                iniziativa_repo.update_iniziativa(sel.id, stato="chiuso")
                st.rerun()
        else:
            if st.button("🟢 Riapri progetto"):
                iniziativa_repo.update_iniziativa(sel.id, stato="attivo")
                st.rerun()
    else:
        st.info("Solo l'admin può cambiare lo stato del progetto.")
