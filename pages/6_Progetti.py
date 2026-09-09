"""Progetti — esecuzione post-award (spec §7): baseline vs consuntivo, quote.

Due livelli (spec §13.1): l'amministratore vede la vista ECONOMICA (budget,
consuntivo, flussi); il pm vede solo la vista OPERATIVA dei propri progetti
(milestone, missioni, commenti, stato, anagrafica) senza importi.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from src.auth.session import require_role
from src.auth.visibilita import vede_economia
from src.data import (
    deliverable_repo,
    etichetta_repo,
    finanza_repo,
    iniziativa_repo,
    missione_repo,
    persona_repo,
    progetti_repo,
)
from src.domain.economia import (
    PianoPersona,
    consuntivo_personale,
    quote_rimanenti,
    rollup_personale,
)
from src.domain.models import (
    STATO_MISSIONE_BADGE,
    STATO_RIMBORSO_BADGE,
    RuoloSistema,
)
from src.lib.errori import messaggio_errore_db
from src.lib.labels import etichetta_progetto, getf
from src.ui.commenti_ui import blocco_commenti

persona = require_role(RuoloSistema.admin, RuoloSistema.pm)
is_admin = persona.ruolo_sistema == RuoloSistema.admin
economia = vede_economia(persona.ruolo_sistema)

st.title("Progetti")

progetti = iniziativa_repo.list_iniziative(tipo="progetto")
if not is_admin:
    progetti = [p for p in progetti if p.responsabile_id == persona.id]

if not progetti:
    st.info("Nessun progetto. I progetti nascono dall'approvazione delle proposte.")
    st.stop()

# --- Elenco progetti con azioni per riga --------------------------------------


@st.dialog("Modifica progetto", width="large")
def _dialog_modifica(prog) -> None:
    """Modifica i dati anagrafici ed economici del progetto."""
    persone_att = persona_repo.list_persone(solo_attivi=True)
    with st.form(f"mod_prog_{prog.id}"):
        m1, m2, m3 = st.columns([2, 1, 1])
        n_tit = m1.text_input("Titolo *", value=prog.titolo)
        n_acr = m2.text_input("Acronimo", value=getf(prog, "acronimo") or "")
        n_cod = m3.text_input("Identificativo / Codice", value=prog.codice or "")
        m4, m5, m6 = st.columns(3)
        n_ente = m4.text_input(
            "Ente finanziatore / Cliente", value=prog.controparte or ""
        )
        n_ini = m5.date_input("Inizio", value=prog.data_inizio)
        n_fine = m6.date_input("Fine", value=prog.data_fine)
        m7, m8, m9 = st.columns(3)
        n_budget = m7.number_input(
            "Budget totale €",
            min_value=0.0,
            step=1000.0,
            value=float(prog.budget_totale or 0),
        )
        n_costo = m8.number_input(
            "Costo complessivo €",
            min_value=0.0,
            step=1000.0,
            value=float(getf(prog, "costo_complessivo") or 0),
        )
        n_fin = m9.number_input(
            "Finanziamento complessivo €",
            min_value=0.0,
            step=1000.0,
            value=float(getf(prog, "finanziamento_complessivo") or 0),
        )
        m10, m11 = st.columns(2)
        idx_r = next(
            (i for i, x in enumerate(persone_att) if x.id == prog.responsabile_id),
            None,
        )
        n_resp = m10.selectbox(
            "Responsabile (PM)",
            [None] + persone_att,
            index=(idx_r + 1) if idx_r is not None else 0,
            format_func=lambda x: "—" if x is None else x.nome_completo,
        )
        _tipi_ric = ["agevolato", "mercato", "ricorrente"]
        n_ric = m11.selectbox(
            "Tipo di ricavo",
            _tipi_ric,
            index=_tipi_ric.index(
                getf(prog, "tipo_ricavo", "agevolato") or "agevolato"
            ),
            help="Per i KPI di sostenibilità (quota ricavi da mercato/ricorrenti).",
        )
        if st.form_submit_button("💾 Salva modifiche", type="primary"):
            if not n_tit:
                st.error("Il titolo è obbligatorio.")
            elif n_ini and n_fine and n_fine < n_ini:
                st.error("La data di fine non può precedere quella di inizio.")
            else:
                try:
                    iniziativa_repo.update_iniziativa(
                        prog.id,
                        titolo=n_tit,
                        acronimo=n_acr or None,
                        codice=n_cod or None,
                        controparte=n_ente or None,
                        data_inizio=n_ini,
                        data_fine=n_fine,
                        budget_totale=n_budget or None,
                        costo_complessivo=n_costo or None,
                        finanziamento_complessivo=n_fin or None,
                        responsabile_id=n_resp.id if n_resp else None,
                        tipo_ricavo=n_ric,
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(messaggio_errore_db(exc))
                else:
                    st.session_state["_msg_progetti"] = "Progetto aggiornato."
                    st.rerun()
    st.caption(
        "CUP, tipo di progetto e logo si impostano nella scheda "
        "«📄 Rendicontazione»."
    )


@st.dialog("Elimina progetto")
def _dialog_elimina(prog) -> None:
    """Eliminazione con riepilogo dei dati collegati e conferma esplicita."""
    dip = iniziativa_repo.riepilogo_dipendenze(prog.id)
    st.markdown(f"Stai per eliminare **{etichetta_progetto(prog)}**.")
    eliminati = {
        "Assegnazioni": dip["assegnazioni"],
        "Ore a timesheet": dip["ore_timesheet"],
        "Task": dip["task"],
        "Deliverable": dip["deliverable"],
        "Milestone": dip["milestone"],
        "Work package": dip["work_package"],
        "Voci di budget": dip["voci_budget"],
        "Movimenti previsti": dip["movimenti_previsti"],
    }
    scollegati = {
        "Movimenti bancari": dip["movimenti_bancari"],
        "Documenti fiscali": dip["documenti"],
        "Spese": dip["spese"],
        "Missioni": dip["missioni"],
        "File in archivio": dip["file_archivio"],
    }
    d1, d2 = st.columns(2)
    d1.markdown("**Eliminati con il progetto**")
    d1.markdown("\n".join(f"- {k}: **{v:g}**" for k, v in eliminati.items()))
    d2.markdown("**Conservati, ma scollegati**")
    d2.markdown("\n".join(f"- {k}: **{v:g}**" for k, v in scollegati.items()))
    if dip["ore_timesheet"]:
        st.error(
            f"⚠️ Ci sono **{dip['ore_timesheet']:g} ore** già registrate a "
            "timesheet: eliminando il progetto si perdono i dati di "
            "rendicontazione. Valuta invece «⚫ Chiudi progetto» nella scheda "
            "Stato."
        )
    else:
        st.warning("L'operazione è irreversibile.")
    conferma = st.checkbox(f"Confermo l'eliminazione di «{prog.titolo}»")
    b1, b2 = st.columns(2)
    if b1.button(
        "🗑 Elimina definitivamente",
        type="primary",
        disabled=not conferma,
        use_container_width=True,
    ):
        try:
            iniziativa_repo.delete_iniziativa(prog.id)
        except Exception as exc:  # noqa: BLE001
            st.error(messaggio_errore_db(exc))
        else:
            st.session_state["_msg_progetti"] = f"Progetto «{prog.titolo}» eliminato."
            st.rerun()
    if b2.button("Annulla", use_container_width=True):
        st.rerun()


_msg = st.session_state.pop("_msg_progetti", None)
if _msg:
    st.success(_msg)

_pesi = (
    [1.1, 3.0, 1.6, 1.0, 1.9]
    + ([1.2] if economia else [])
    + ([0.6, 0.6] if is_admin else [])
)
_intestazioni = (
    ["Acronimo", "Titolo", "Ente finanziatore", "Stato", "Periodo"]
    + (["Budget €"] if economia else [])
    + (["", ""] if is_admin else [])
)
for _col, _txt in zip(st.columns(_pesi), _intestazioni, strict=True):
    _col.markdown(f"<small><b>{_txt}</b></small>", unsafe_allow_html=True)
for p in progetti:
    _c = st.columns(_pesi, vertical_alignment="center")
    _c[0].markdown(getf(p, "acronimo") or getf(p, "codice") or "—")
    _c[1].markdown(p.titolo)
    _c[2].markdown(getf(p, "controparte") or "—")
    _c[3].markdown("🟢 attivo" if p.stato == "attivo" else "⚫ chiuso")
    _periodo = (
        f"{p.data_inizio:%d/%m/%Y} → {p.data_fine:%d/%m/%Y}"
        if p.data_inizio and p.data_fine
        else "—"
    )
    _c[4].markdown(f"<small>{_periodo}</small>", unsafe_allow_html=True)
    _i = 5
    if economia:
        _c[_i].markdown(f"{float(p.budget_totale or 0):,.0f}")
        _i += 1
    if is_admin:
        if _c[_i].button("✏️", key=f"ed_{p.id}", help="Modifica i dati del progetto"):
            _dialog_modifica(p)
        if _c[_i + 1].button(
            "🗑", key=f"del_{p.id}", help="Elimina il progetto (con conferma)"
        ):
            _dialog_elimina(p)

if is_admin:
    st.caption(
        "Accanto a ogni riga: **✏️** modifica i dati del progetto, **🗑** lo "
        "elimina (con riepilogo dei dati collegati e conferma)."
    )
st.divider()

sel = st.selectbox(
    "Dettaglio progetto",
    options=progetti,
    format_func=lambda p: f"[{p.stato}] {etichetta_progetto(p)}",
    help=(
        "Scegli il progetto di cui vedere le schede sottostanti: budget, "
        "flussi, milestone, rendicontazione, missioni, commenti e stato."
    ),
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

if economia:
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

if economia:
    tab_quote, tab_fin, tab_ms, tab_rend, tab_miss, tab_comm, tab_stato, tab_mr = (
        st.tabs(
            [
                "💶 Budget vs consuntivo",
                "💰 Flussi finanziari",
                "🎯 Milestone",
                "📄 Rendicontazione",
                "✈️ Missioni",
                "💬 Commenti",
                "🚦 Stato",
                "📆 Monthly report",
            ]
        )
    )
else:
    tab_quote = tab_fin = None
    tab_ms, tab_rend, tab_miss, tab_comm, tab_stato, tab_mr = st.tabs(
        [
            "🎯 Milestone",
            "📄 Anagrafica",
            "✈️ Missioni",
            "💬 Commenti",
            "🚦 Stato",
            "📆 Monthly report",
        ]
    )

with tab_comm:
    blocco_commenti(
        "iniziativa",
        sel.id,
        persona,
        is_admin,
        {p.id: p.nome_completo for p in persona_repo.list_persone()},
    )

with tab_miss:
    missioni_p = missione_repo.list_missioni(iniziativa_id=sel.id)
    if not missioni_p:
        st.info("Nessuna missione associata a questo progetto.")
    else:
        tot_miss = missione_repo.totali_per_missione([str(m.id) for m in missioni_p])
        nomi_p = {p.id: p.nome_completo for p in persona_repo.list_persone()}
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Destinazione": m.destinazione,
                        "Periodo": m.periodo,
                        "Persona": nomi_p.get(m.persona_id, "—"),
                        "Stato": STATO_MISSIONE_BADGE.get(m.stato, m.stato),
                        **(
                            {
                                "Previsto €": float(m.spesa_prevista or 0),
                                "Speso €": float(tot_miss.get(str(m.id), 0) or 0),
                            }
                            if economia
                            else {}
                        ),
                        "Rimborso": STATO_RIMBORSO_BADGE.get(m.rimborso_stato, ""),
                    }
                    for m in missioni_p
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        speso_miss = sum(float(tot_miss.get(str(m.id), 0) or 0) for m in missioni_p)
        prev_miss = sum(float(m.spesa_prevista or 0) for m in missioni_p)
        m1, m2, m3 = st.columns(3)
        m1.metric("Missioni", len(missioni_p))
        if economia:
            m2.metric("Preventivato", f"{prev_miss:,.2f} €")
            m3.metric("Speso", f"{speso_miss:,.2f} €")
    st.caption("Le missioni si creano e gestiscono nella pagina **Missioni**.")

if economia:
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
                if (
                    st.form_submit_button("➕ Aggiungi movimento previsto")
                    and pv_imp > 0
                ):
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
            r1, r2, r3 = st.columns(3)
            n_cup = r1.text_input("CUP del progetto", value=getf(sel, "cup") or "")
            _tipi_ric = ["agevolato", "mercato", "ricorrente"]
            n_ricavo = r3.selectbox(
                "Tipo di ricavo",
                _tipi_ric,
                index=_tipi_ric.index(
                    getf(sel, "tipo_ricavo", "agevolato") or "agevolato"
                ),
                help="Per i KPI di sostenibilità: agevolato, mercato, ricorrente.",
            )
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
                    tipo_ricavo=n_ricavo,
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

if economia:
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
            genera_pag = st.checkbox(
                "💰 Milestone di pagamento (determina un incasso previsto)",
                value=False,
                help="Se attiva, l'incasso entra nella proiezione di cassa.",
            )
            if st.form_submit_button("Aggiungi milestone") and titolo:
                progetti_repo.create_milestone(
                    sel.id,
                    titolo,
                    quando,
                    incasso or None,
                    genera_pagamento=genera_pag,
                )
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
                        **(
                            {"Incasso €": float(m.importo_incasso or 0) or None}
                            if economia
                            else {}
                        ),
                        "Pagamento": "💰" if getf(m, "genera_pagamento") else "",
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
        if economia:
            st.caption(
                f"Incassi previsti da milestone: **{incassi_previsti:,.2f} €**, "
                f"maturati (completate): **{incassi_maturati:,.2f} €**"
            )
        if is_admin:
            m_sel = st.selectbox(
                "Gestisci milestone",
                options=[None] + ms,
                format_func=lambda m: "—" if m is None else m.titolo,
            )
            if m_sel:
                gc1, gc2 = st.columns([2, 1])
                nuovo = gc1.selectbox(
                    "Nuovo stato",
                    ["prevista", "completata", "slittata"],
                    index=["prevista", "completata", "slittata"].index(m_sel.stato),
                )
                if gc1.button("Aggiorna stato"):
                    progetti_repo.set_stato_milestone(m_sel.id, nuovo)
                    st.rerun()
                if gc2.button("🗑 Elimina milestone", type="secondary"):
                    progetti_repo.delete_milestone(m_sel.id)
                    st.rerun()

                # associazione deliverable del progetto alla milestone
                delivs = deliverable_repo.list_deliverables(sel.id)
                if delivs:
                    attuali = etichetta_repo.deliverable_di_milestone(m_sel.id)
                    scelti = st.multiselect(
                        "Deliverable raccolti da questa milestone",
                        options=[str(d.id) for d in delivs],
                        default=[a for a in attuali],
                        format_func=lambda i: next(
                            (d.titolo for d in delivs if str(d.id) == i), i
                        ),
                    )
                    if st.button("Salva deliverable milestone"):
                        etichetta_repo.set_deliverable_milestone(m_sel.id, scelti)
                        st.success("Associazione salvata.")
                        st.rerun()
                else:
                    st.caption(
                        "Nessun deliverable nel progetto: creali nella pagina Task."
                    )
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


# --- Monthly report -------------------------------------------------------------
with tab_mr:
    from src.data import monthly_repo
    from src.lib.monthly_pack import genera_e_salva
    from src.lib.monthly_report import (
        ISTRUZIONI_DEFAULT,
        etichetta_mese,
        mese_precedente,
        nome_file,
    )

    st.caption(
        "Per i progetti che lo richiedono, la piattaforma raccoglie ogni mese in un "
        "file **.md** i dati del mese (deliverable, task con note, cambi di stato e "
        "commenti, ore, missioni) insieme al **prompt** per generare il monthly "
        "report con ChatGPT o Claude. Il responsabile riceve l'avviso in Dashboard "
        "e via e-mail a inizio mese."
    )
    puo_mr = is_admin or sel.responsabile_id == persona.id
    with st.form("mr_impostazioni"):
        mr_flag = st.checkbox(
            "Questo progetto richiede un monthly report",
            value=bool(getf(sel, "monthly_report")),
        )
        mr_istr = st.text_area(
            "Istruzioni per l'assistente AI (lingua, formato, destinatario, "
            "sezioni richieste dal finanziatore)",
            value=getf(sel, "monthly_report_istruzioni") or "",
            placeholder=ISTRUZIONI_DEFAULT,
            height=90,
        )
        if st.form_submit_button("💾 Salva impostazioni", disabled=not puo_mr):
            iniziativa_repo.update_iniziativa(
                sel.id,
                monthly_report=mr_flag,
                monthly_report_istruzioni=mr_istr.strip() or None,
            )
            st.rerun()
    if not puo_mr:
        st.info(
            "Solo il responsabile del progetto o l'amministratore può gestire il "
            "monthly report."
        )

    _oggi = date.today()
    _mesi = []
    _a, _m = _oggi.year, _oggi.month
    for _ in range(18):
        _mesi.append((_a, _m))
        _m -= 1
        if _m == 0:
            _a, _m = _a - 1, 12
    _prec = mese_precedente(_oggi)
    g1, g2 = st.columns([2, 1.4])
    mr_mese = g1.selectbox(
        "Mese",
        _mesi,
        index=_mesi.index(_prec) if _prec in _mesi else 0,
        format_func=lambda am: etichetta_mese(*am),
    )
    if g2.button(
        "⚙️ Genera / rigenera il file .md",
        type="primary",
        disabled=not puo_mr,
        use_container_width=True,
    ):
        try:
            genera_e_salva(sel, mr_mese[0], mr_mese[1])
        except Exception as exc:  # noqa: BLE001
            st.error(messaggio_errore_db(exc))
        else:
            st.success(
                f"File del monthly report di {etichetta_mese(*mr_mese)} generato."
            )
            st.rerun()

    _report = []
    try:
        _report = monthly_repo.list_report(sel.id)
    except Exception:  # noqa: BLE001 — migrazione 0017 non ancora applicata
        st.warning("Tabella monthly_report assente: applica la migrazione 0017.")
    if not _report:
        st.info("Nessun file generato per questo progetto.")
    for r in _report:
        with st.container(border=True):
            h1, h2, h3, h4 = st.columns([3, 1.4, 1.4, 1])
            stato_ic = "✅ completato" if r["stato"] == "completato" else "🟡 pronto"
            h1.markdown(
                f"**{etichetta_mese(r['anno'], r['mese'])}** · {stato_ic} · "
                f"generato il "
                f"{r['generato_il']:%d/%m/%Y}"
                + (
                    f" · e-mail inviata il {r['notificato_il']:%d/%m/%Y}"
                    if r["notificato_il"]
                    else ""
                )
            )
            rep = monthly_repo.get_report(sel.id, r["anno"], r["mese"])
            if rep:
                h2.download_button(
                    "⬇️ Scarica .md",
                    rep["contenuto_md"].encode("utf-8"),
                    nome_file(sel.acronimo, r["anno"], r["mese"]),
                    "text/markdown",
                    key=f"mr_dl_{r['id']}",
                    use_container_width=True,
                )
            if puo_mr:
                if r["stato"] == "pronto":
                    if h3.button(
                        "✅ Completato",
                        key=f"mr_ok_{r['id']}",
                        use_container_width=True,
                    ):
                        monthly_repo.segna_completato(r["id"])
                        st.rerun()
                elif h3.button(
                    "↩️ Riapri", key=f"mr_re_{r['id']}", use_container_width=True
                ):
                    monthly_repo.riapri(r["id"])
                    st.rerun()
                if is_admin and h4.button(
                    "🗑", key=f"mr_del_{r['id']}", help="Elimina il file"
                ):
                    monthly_repo.elimina_report(r["id"])
                    st.rerun()
            if rep:
                with st.expander("Anteprima"):
                    st.markdown(rep["contenuto_md"])
