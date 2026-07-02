"""Progetti — esecuzione post-award (spec §7): baseline vs consuntivo, quote.

Vista economica riservata: admin (scrittura) e pm (lettura dei propri).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from src.auth.session import require_role
from src.data import finanza_repo, iniziativa_repo, progetti_repo
from src.domain.economia import (
    PianoPersona,
    consuntivo_personale,
    quote_rimanenti,
    rollup_personale,
)
from src.domain.models import RuoloSistema
from src.lib.labels import etichetta_progetto, getf

persona = require_role(RuoloSistema.admin, RuoloSistema.pm)
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
                "Acronimo": getf(p, "acronimo") or "",
                "Identificativo": getf(p, "codice") or "",
                "Titolo": p.titolo,
                "Ente finanziatore": getf(p, "controparte") or "",
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
    format_func=lambda p: f"[{p.stato}] {etichetta_progetto(p)}",
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

tab_quote, tab_fin, tab_ms, tab_rend, tab_stato = st.tabs(
    [
        "💶 Budget vs consuntivo",
        "💰 Flussi finanziari",
        "🎯 Milestone",
        "📄 Rendicontazione",
        "🚦 Stato",
    ]
)

with tab_fin:
    st.markdown("**Info generali finanziarie**")
    g1, g2, g3 = st.columns(3)
    g1.metric(
        "Costo complessivo",
        (
            f"{float(getf(sel, 'costo_complessivo') or 0):,.0f} €"
            if getf(sel, "costo_complessivo")
            else "—"
        ),
    )
    g2.metric(
        "Finanziamento",
        (
            f"{float(getf(sel, 'finanziamento_complessivo') or 0):,.0f} €"
            if getf(sel, "finanziamento_complessivo")
            else "—"
        ),
    )
    # saldo movimenti bancari riconciliati a questo progetto
    _mov = [
        m
        for m in finanza_repo.list_movimenti()
        if str(m["iniziativa_id"]) == str(sel.id)
    ]
    _saldo_mov = sum(
        float(m["importo"]) * (1 if m["segno"] == "entrata" else -1) for m in _mov
    )
    g3.metric("Saldo movimenti riconciliati", f"{_saldo_mov:,.2f} €")

    if is_admin:
        with st.form("info_fin", clear_on_submit=False):
            f1, f2 = st.columns(2)
            n_costo = f1.number_input(
                "Costo complessivo €",
                min_value=0.0,
                step=1000.0,
                value=float(getf(sel, "costo_complessivo") or 0),
            )
            n_finanz = f2.number_input(
                "Finanziamento complessivo €",
                min_value=0.0,
                step=1000.0,
                value=float(getf(sel, "finanziamento_complessivo") or 0),
            )
            if st.form_submit_button("Salva info finanziarie"):
                iniziativa_repo.update_iniziativa(
                    sel.id,
                    costo_complessivo=n_costo or None,
                    finanziamento_complessivo=n_finanz or None,
                )
                st.rerun()

    st.divider()
    st.markdown("**Calendario movimenti previsti** (flussi attesi del progetto)")
    previsti = finanza_repo.list_movimenti_previsti(sel.id)
    if previsti:
        tot_e = sum(
            float(p["importo"])
            for p in previsti
            if p["segno"] == "entrata" and not p["completata"]
        )
        tot_u = sum(
            float(p["importo"])
            for p in previsti
            if p["segno"] == "uscita" and not p["completata"]
        )
        st.caption(
            f"Da incassare: **{tot_e:,.2f} €** · da pagare: **{tot_u:,.2f} €** "
            "(voci non completate)"
        )
        for p in previsti:
            c1, c2, c3 = st.columns([5, 1.4, 1.1])
            segno_ic = "🟢" if p["segno"] == "entrata" else "🔴"
            quando = f"{p['data_attesa']:%d/%m/%Y}" if p["data_attesa"] else "—"
            imp = f"{float(p['importo']):,.2f}"
            c1.markdown(
                f"{segno_ic} {p['descrizione'] or '—'} · **{imp} €** · 📅 {quando}"
            )
            if is_admin:
                fatto = c2.checkbox(
                    "completata", value=p["completata"], key=f"pv_{p['id']}"
                )
                if fatto != p["completata"]:
                    finanza_repo.toggle_previsto_completato(p["id"], fatto)
                    st.rerun()
                if c3.button("🗑", key=f"pvdel_{p['id']}"):
                    finanza_repo.delete_movimento_previsto(p["id"])
                    st.rerun()
            else:
                c2.markdown("✅" if p["completata"] else "⏳")
    else:
        st.info("Nessun movimento previsto per questo progetto.")

    if is_admin:
        with st.form("nuovo_previsto", clear_on_submit=True):
            n1, n2, n3, n4 = st.columns([3, 1, 1, 1.3])
            pv_desc = n1.text_input("Descrizione")
            pv_segno = n2.selectbox("Tipo", ["entrata", "uscita"])
            pv_imp = n3.number_input("Importo €", min_value=0.0, step=100.0)
            pv_data = n4.date_input("Data attesa", value=None)
            if st.form_submit_button("➕ Aggiungi movimento previsto") and pv_imp > 0:
                finanza_repo.create_movimento_previsto(
                    sel.id,
                    segno=pv_segno,
                    importo=pv_imp,
                    descrizione=pv_desc or None,
                    data_attesa=pv_data,
                )
                st.rerun()

with tab_rend:
    st.caption(
        "Anagrafica del progetto (campi allineati a MAIC tasks) e dati per "
        "l'export XLSX del timesheet (CUP, tipo progetto, logo)."
    )
    if is_admin:
        with st.form("dati_rendicontazione"):
            a1, a2, a3 = st.columns(3)
            n_acr = a1.text_input(
                "Acronimo", value=sel.acronimo or "", placeholder="es. SHIFT"
            )
            n_cod = a2.text_input("Identificativo / Codice", value=sel.codice or "")
            n_ente = a3.text_input(
                "Ente finanziatore / Cliente", value=sel.controparte or ""
            )
            r1, r2 = st.columns(2)
            n_cup = r1.text_input("CUP del progetto", value=getf(sel, "cup") or "")
            n_tipo = r2.text_input(
                "Tipo del progetto",
                value=getf(sel, "tipo_progetto_desc") or "",
                placeholder="es. Ricerca Industriale e Sviluppo Sperimentale",
            )
            if st.form_submit_button("Salva dati", type="primary"):
                iniziativa_repo.update_iniziativa(
                    sel.id,
                    acronimo=n_acr or None,
                    codice=n_cod or None,
                    controparte=n_ente or None,
                    cup=n_cup or None,
                    tipo_progetto_desc=n_tipo or None,
                )
                st.rerun()
        st.caption(
            "ℹ️ L'**acronimo** è anche la chiave usata per riconciliare "
            "automaticamente i movimenti bancari (colonna «Progetto» del foglio)."
        )
        logo_att = iniziativa_repo.get_logo(sel.id)
        if logo_att:
            st.image(logo_att[0], caption="Logo attuale", width=180)
            if st.button("Rimuovi logo"):
                iniziativa_repo.set_logo(sel.id, None, None)
                st.rerun()
        nuovo_logo = st.file_uploader(
            "Carica logo progetto (PNG/JPG)", type=["png", "jpg", "jpeg"]
        )
        if nuovo_logo is not None and st.button("Salva logo", type="primary"):
            iniziativa_repo.set_logo(sel.id, nuovo_logo.getvalue(), nuovo_logo.type)
            st.success("Logo salvato.")
            st.rerun()
    else:
        st.markdown(
            f"**CUP:** {getf(sel, 'cup') or '—'}  \n"
            f"**Tipo progetto:** {getf(sel, 'tipo_progetto_desc') or '—'}"
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
