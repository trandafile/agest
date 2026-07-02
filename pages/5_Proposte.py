"""Proposte — pianificazione pre-award (spec §6): builder, pipeline, capacity.

Vista economica riservata: admin (scrittura) e pm (lettura delle proprie).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from src.auth.session import require_role, sidebar_utente
from src.data import iniziativa_repo, persona_repo, progetti_repo
from src.domain.economia import (
    PianoPersona,
    capacity_per_persona,
    rollup_personale,
    valore_atteso,
)
from src.domain.models import CATEGORIE_BUDGET, RuoloSistema

st.set_page_config(page_title="Proposte — ANTECNICA", page_icon="📝", layout="wide")
persona = require_role(RuoloSistema.admin, RuoloSistema.pm)
sidebar_utente(persona)
is_admin = persona.ruolo_sistema == RuoloSistema.admin

st.title("Proposte")

# --- Pipeline pesata ---------------------------------------------------------
proposte = iniziativa_repo.list_iniziative(tipo="proposta")
if not is_admin:
    proposte = [p for p in proposte if p.responsabile_id == persona.id]

if proposte:
    pipe = pd.DataFrame(
        [
            {
                "Codice": p.codice or "",
                "Titolo": p.titolo,
                "Controparte": p.controparte or "",
                "Stato": p.stato,
                "Budget €": float(p.budget_totale or 0),
                "P(successo)": float(p.probabilita_successo or 0),
                "Valore atteso €": float(
                    valore_atteso(p.budget_totale, p.probabilita_successo)
                ),
            }
            for p in proposte
        ]
    )
    st.dataframe(pipe, hide_index=True, use_container_width=True)
    vive = [p for p in proposte if p.stato in ("bozza", "inviata")]
    tot_atteso = sum(
        valore_atteso(p.budget_totale, p.probabilita_successo) for p in vive
    )
    st.caption(
        f"Pipeline attiva (bozza+inviata): **{len(vive)}** proposte, "
        f"valore atteso **{tot_atteso:,.2f} €**"
    )
else:
    st.info("Nessuna proposta.")

# --- Nuova proposta ------------------------------------------------------------
if is_admin:
    with st.expander("➕ Nuova proposta"):
        with st.form("nuova_proposta", clear_on_submit=True):
            c1, c2 = st.columns(2)
            titolo = c1.text_input("Titolo *")
            codice = c2.text_input("Codice (opzionale)")
            c3, c4, c5 = st.columns(3)
            controparte = c3.text_input("Controparte / ente")
            inizio = c4.date_input("Inizio previsto", value=date.today())
            fine = c5.date_input("Fine prevista", value=date.today())
            c6, c7 = st.columns(2)
            budget = c6.number_input("Budget totale €", min_value=0.0, step=1000.0)
            prob = c7.slider("Probabilità di successo", 0.0, 1.0, 0.5, 0.05)
            persone = persona_repo.list_persone(solo_attivi=True)
            resp = st.selectbox(
                "Responsabile (PM)",
                options=[None] + persone,
                format_func=lambda p: "—" if p is None else p.nome_completo,
            )
            if st.form_submit_button("Crea proposta", type="primary"):
                if not titolo:
                    st.error("Il titolo è obbligatorio.")
                else:
                    iniziativa_repo.create_iniziativa(
                        tipo="proposta",
                        stato="bozza",
                        titolo=titolo,
                        codice=codice or None,
                        controparte=controparte or None,
                        data_inizio=inizio,
                        data_fine=fine,
                        budget_totale=budget or None,
                        probabilita_successo=prob,
                        responsabile_id=resp.id if resp else None,
                    )
                    st.success("Proposta creata.")
                    st.rerun()

# --- Dettaglio proposta -----------------------------------------------------------
if proposte:
    st.divider()
    sel = st.selectbox(
        "Dettaglio proposta",
        options=proposte,
        format_func=lambda p: f"[{p.stato}] {p.codice or ''} {p.titolo}",
    )
    alla_data = sel.data_inizio or date.today()

    tab_piano, tab_budget, tab_wp, tab_stato = st.tabs(
        ["👥 Assegnazioni", "💶 Budget", "📦 Work package", "🚦 Stato"]
    )

    # ---- Assegnazioni (builder) --------------------------------------------
    with tab_piano:
        piani_rows = progetti_repo.piani_iniziativa(sel.id)
        wps = progetti_repo.list_work_packages(sel.id)
        if is_admin:
            with st.form("nuova_assegnazione", clear_on_submit=True):
                f1, f2, f3, f4, f5 = st.columns([2, 1, 1, 1, 1])
                persone = persona_repo.list_persone(solo_attivi=True)
                pp = f1.selectbox(
                    "Persona", options=persone, format_func=lambda p: p.nome_completo
                )
                ta = f2.selectbox("Tipo", ["RI", "SS", "altro"])
                ore_p = f3.number_input("Ore pianificate", min_value=0.0, step=8.0)
                tetto = f4.number_input("Max mese (h)", min_value=0.0, step=8.0)
                wp = f5.selectbox(
                    "WP (opz.)",
                    options=[None] + wps,
                    format_func=lambda w: "—" if w is None else w.titolo,
                )
                if st.form_submit_button("Aggiungi assegnazione"):
                    try:
                        iniziativa_repo.create_assegnazione(
                            sel.id,
                            pp.id,
                            tipo_attivita=ta,
                            ore_pianificate=ore_p or None,
                            tetto_ore_mese=tetto or None,
                            work_package_id=wp.id if wp else None,
                        )
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Errore: {exc}")

        if piani_rows:
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
            tariffe = progetti_repo.tariffe_by_persona([p.persona_id for p in piani])
            roll = rollup_personale(piani, tariffe, alla_data)
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Persona": r["nome"],
                            "Tipo": r["tipo_attivita"],
                            "WP": r["work_package"] or "—",
                            "Ore pianificate": float(r["ore_pianificate"] or 0),
                            "Max mese": float(r["tetto_ore_mese"] or 0) or None,
                        }
                        for r in piani_rows
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
            c1, c2 = st.columns(2)
            c1.markdown("**Costo per persona** (tariffa vigente)")
            c1.dataframe(
                pd.DataFrame(
                    [
                        {"Persona": k, "Costo €": float(v)}
                        for k, v in roll["per_persona"].items()
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
            c2.markdown("**Costo per WP**")
            c2.dataframe(
                pd.DataFrame(
                    [{"WP": k, "Costo €": float(v)} for k, v in roll["per_wp"].items()]
                ),
                hide_index=True,
                use_container_width=True,
            )
            st.metric("Totale personale pianificato", f"{roll['totale']:,.2f} €")
            if roll["senza_tariffa"]:
                st.warning(
                    "Senza tariffa vigente alla data: "
                    + ", ".join(roll["senza_tariffa"])
                )
            if is_admin:
                da_rim = st.selectbox(
                    "Rimuovi assegnazione",
                    options=[None] + piani_rows,
                    format_func=lambda r: (
                        "—" if r is None else f"{r['nome']} [{r['tipo_attivita']}]"
                    ),
                )
                if da_rim and st.button("Rimuovi", key="rm_ass"):
                    iniziativa_repo.delete_assegnazione(da_rim["id"])
                    st.rerun()
        else:
            st.info("Nessuna assegnazione pianificata.")

        # Capacity check globale (proposte vive + progetti attivi)
        st.divider()
        st.markdown(
            "**Capacity check** (ore pianificate su proposte + progetti attivi)"
        )
        cap = capacity_per_persona(progetti_repo.ore_pianificate_attive())
        if cap:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Persona": r["nome"],
                            "Ore pianificate": float(r["ore"]),
                            "Soglia FTE": float(r["soglia"]),
                            "Sovrallocata": "🔴" if r["sovrallocata"] else "🟢",
                        }
                        for r in cap
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
            for r in cap:
                if r["sovrallocata"]:
                    st.error(
                        f"⚠️ {r['nome']} sovrallocata: {r['ore']:g} h "
                        f"pianificate (> {r['soglia']:g} h FTE)."
                    )

    # ---- Budget non-personale ------------------------------------------------
    with tab_budget:
        voci = progetti_repo.list_voci_budget(sel.id)
        if is_admin:
            with st.form("nuova_voce", clear_on_submit=True):
                f1, f2, f3 = st.columns(3)
                cat = f1.selectbox("Categoria", CATEGORIE_BUDGET)
                imp = f2.number_input("Importo €", min_value=0.0, step=100.0)
                desc = f3.text_input("Descrizione")
                if st.form_submit_button("Aggiungi voce"):
                    progetti_repo.create_voce_budget(sel.id, cat, imp, desc or None)
                    st.rerun()
        if voci:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Categoria": v.categoria,
                            "Descrizione": v.descrizione or "",
                            "Importo €": float(v.importo),
                        }
                        for v in voci
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
            st.metric(
                "Totale voci di budget",
                f"{sum(float(v.importo) for v in voci):,.2f} €",
            )
            if is_admin:
                da_rim = st.selectbox(
                    "Rimuovi voce",
                    options=[None] + voci,
                    format_func=lambda v: (
                        "—" if v is None else f"{v.categoria} {float(v.importo):,.2f}€"
                    ),
                )
                if da_rim and st.button("Rimuovi", key="rm_voce"):
                    progetti_repo.delete_voce_budget(da_rim.id)
                    st.rerun()
        else:
            st.info("Nessuna voce di budget (oltre al personale).")

    # ---- Work package (opzionali) ---------------------------------------------
    with tab_wp:
        st.caption("I WP sono OPZIONALI: una proposta può farne a meno.")
        wps = progetti_repo.list_work_packages(sel.id)
        if is_admin:
            with st.form("nuovo_wp", clear_on_submit=True):
                f1, f2, f3, f4 = st.columns(4)
                w_cod = f1.text_input("Codice", placeholder="WP1")
                w_tit = f2.text_input("Titolo *")
                w_ore = f3.number_input("Budget ore", min_value=0.0, step=8.0)
                w_cst = f4.number_input("Budget costo €", min_value=0.0, step=500.0)
                if st.form_submit_button("Aggiungi WP") and w_tit:
                    progetti_repo.create_work_package(
                        sel.id, w_tit, w_cod or None, w_ore or None, w_cst or None
                    )
                    st.rerun()
        if wps:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Codice": w.codice or "",
                            "Titolo": w.titolo,
                            "Budget ore": float(w.budget_ore or 0) or None,
                            "Budget €": float(w.budget_costo or 0) or None,
                        }
                        for w in wps
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )

    # ---- Stato + conversione ----------------------------------------------------
    with tab_stato:
        if is_admin:
            c1, c2 = st.columns(2)
            nuovo_stato = c1.selectbox(
                "Stato",
                ["bozza", "inviata", "approvata", "rifiutata"],
                index=["bozza", "inviata", "approvata", "rifiutata"].index(sel.stato),
            )
            nuova_prob = c2.slider(
                "Probabilità",
                0.0,
                1.0,
                float(sel.probabilita_successo or 0.5),
                0.05,
            )
            if st.button("Salva stato"):
                iniziativa_repo.update_iniziativa(
                    sel.id, stato=nuovo_stato, probabilita_successo=nuova_prob
                )
                st.rerun()
            st.divider()
            st.markdown(
                "**Approva → Progetto**: la proposta diventa progetto attivo; "
                "WP, assegnazioni e budget restano come **baseline**."
            )
            if st.button("🚀 Approva proposta e converti in progetto", type="primary"):
                try:
                    iniziativa_repo.approva_proposta(
                        sel.id, eseguito_da=st.session_state.get("user_email")
                    )
                    st.success("Proposta convertita in progetto attivo.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Errore: {exc}")
        else:
            st.info("Solo l'admin può modificare stato e convertire la proposta.")
