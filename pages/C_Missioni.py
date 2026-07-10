"""Missioni (trasferte) — richiesta, autorizzazione admin, spese, rimborso.

Flusso: bozza → richiesta → autorizzata (admin) → spese → richiedi rimborso
→ liquidato (admin). Ognuno vede tutte le missioni; modifica le proprie
(l'admin tutte). Le missioni restano elencate anche per progetto.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_login
from src.data import iniziativa_repo, missione_repo, persona_repo
from src.domain.models import (
    CATEGORIA_SPESA_ICONA,
    CATEGORIE_SPESA_MISSIONE,
    STATO_MISSIONE_BADGE,
    STATO_RIMBORSO_BADGE,
    RuoloSistema,
)
from src.lib.labels import etichetta_con_tag
from src.lib.missioni import riepilogo
from src.ui.commenti_ui import blocco_commenti

persona = require_login()
is_admin = persona.ruolo_sistema == RuoloSistema.admin
UTENTE = st.session_state.get("user_email")

st.title("Missioni")
st.caption(
    "Trasferte: dove, quando, per quale progetto e con che obiettivo. "
    "L'admin autorizza; le spese si registrano a consuntivo e il totale è automatico."
)

persone = persona_repo.list_persone(solo_attivi=True)
nomi = {p.id: p.nome_completo for p in persona_repo.list_persone()}
iniziative = iniziativa_repo.list_iniziative()
titoli_ini = {i.id: etichetta_con_tag(i) for i in iniziative}


def _puo_modificare(m) -> bool:
    return is_admin or m.persona_id == persona.id


# =====================================================================
# Nuova missione
# =====================================================================
with st.expander("➕ Nuova missione"):
    with st.form("nuova_missione", clear_on_submit=True):
        c1, c2 = st.columns([2, 2])
        destinazione = c1.text_input("Dove si va *", placeholder="Milano, Politecnico")
        ini = c2.selectbox(
            "Progetto associato",
            [None] + iniziative,
            format_func=lambda i: "— (nessuno)" if i is None else titoli_ini[i.id],
        )
        c3, c4, c5 = st.columns(3)
        d_ini = c3.date_input("Dal *", value=date.today())
        d_fin = c4.date_input("Al *", value=date.today())
        prevista = c5.number_input(
            "Spesa prevista (€)", min_value=0.0, step=50.0, format="%.2f"
        )
        chi = st.selectbox(
            "Chi va in missione",
            persone,
            index=next((i for i, p in enumerate(persone) if p.id == persona.id), 0),
            format_func=lambda p: p.nome_completo,
            disabled=not is_admin,
            help="Solo l'admin può creare missioni per altri.",
        )
        obiettivo = st.text_area("Obiettivo della missione")
        if st.form_submit_button("Crea missione", type="primary"):
            if not destinazione.strip():
                st.error("La destinazione è obbligatoria.")
            elif d_fin < d_ini:
                st.error("La data di fine non può precedere quella di inizio.")
            else:
                missione_repo.create_missione(
                    persona_id=(chi.id if is_admin else persona.id),
                    destinazione=destinazione,
                    data_inizio=d_ini,
                    data_fine=d_fin,
                    iniziativa_id=ini.id if ini else None,
                    obiettivo=obiettivo or None,
                    spesa_prevista=prevista or None,
                )
                st.rerun()

# =====================================================================
# Filtri + elenco
# =====================================================================
f1, f2, f3 = st.columns(3)
filtro_ini = f1.selectbox(
    "Progetto",
    [None] + iniziative,
    format_func=lambda i: "(tutti)" if i is None else titoli_ini[i.id],
)
filtro_persona = f2.selectbox(
    "Persona",
    [None] + persone,
    format_func=lambda p: "(tutte)" if p is None else p.nome_completo,
)
solo_mie = f3.checkbox("Solo le mie missioni", value=False)

missioni = missione_repo.list_missioni(
    iniziativa_id=filtro_ini.id if filtro_ini else None,
    persona_id=(
        persona.id if solo_mie else (filtro_persona.id if filtro_persona else None)
    ),
)
totali = missione_repo.totali_per_missione([str(m.id) for m in missioni])

if is_admin:
    da_autorizzare = [m for m in missioni if m.stato == "richiesta"]
    da_liquidare = [m for m in missioni if m.rimborso_stato == "richiesto"]
    if da_autorizzare or da_liquidare:
        st.warning(
            f"📋 In attesa di te: **{len(da_autorizzare)}** da autorizzare, "
            f"**{len(da_liquidare)}** rimborsi da liquidare."
        )

if not missioni:
    st.info("Nessuna missione con i filtri scelti.")
    st.stop()


@st.dialog("Dettagli missione", width="large")
def missione_dialog(m) -> None:
    spese = missione_repo.list_spese(m.id)
    r = riepilogo(m, spese)
    can_edit = _puo_modificare(m)

    st.markdown(f"### 📍 {m.destinazione}")
    st.caption(
        f"{m.periodo} ({m.giorni} gg) · 👤 {nomi.get(m.persona_id, '—')} · "
        f"📁 {titoli_ini.get(m.iniziativa_id, '— nessun progetto')}"
    )
    st.markdown(
        f"{STATO_MISSIONE_BADGE.get(m.stato, m.stato)} · "
        f"{STATO_RIMBORSO_BADGE.get(m.rimborso_stato, '')}"
    )
    if m.obiettivo:
        st.markdown(f"**Obiettivo:** {m.obiettivo}")
    if m.note_autorizzazione:
        st.info(f"Nota dell'admin: {m.note_autorizzazione}")

    k1, k2, k3 = st.columns(3)
    k1.metric("Spesa prevista", f"{float(m.spesa_prevista or 0):,.2f} €")
    k2.metric("Totale speso", f"{float(r['totale']):,.2f} €")
    if r["scostamento"] is not None:
        s = float(r["scostamento"])
        k3.metric(
            "Scostamento", f"{s:,.2f} €", delta=f"{s:,.2f}", delta_color="inverse"
        )

    st.divider()

    # --- Modifica dati (solo se bozza/respinta) ---
    if can_edit and m.modificabile:
        with st.expander("✏️ Modifica dati missione"):
            with st.form(f"edit_m_{m.id}"):
                e1, e2 = st.columns(2)
                dest = e1.text_input("Destinazione", value=m.destinazione)
                e_ini = e2.selectbox(
                    "Progetto",
                    [None] + iniziative,
                    index=next(
                        (
                            i + 1
                            for i, x in enumerate(iniziative)
                            if x.id == m.iniziativa_id
                        ),
                        0,
                    ),
                    format_func=lambda i: "—" if i is None else titoli_ini[i.id],
                )
                e3, e4, e5 = st.columns(3)
                di = e3.date_input("Dal", value=m.data_inizio)
                df = e4.date_input("Al", value=m.data_fine)
                sp = e5.number_input(
                    "Spesa prevista (€)",
                    min_value=0.0,
                    value=float(m.spesa_prevista or 0),
                    step=50.0,
                    format="%.2f",
                )
                ob = st.text_area("Obiettivo", value=m.obiettivo or "")
                if st.form_submit_button("💾 Salva", type="primary"):
                    if df < di:
                        st.error("Date incoerenti.")
                    else:
                        missione_repo.update_missione(
                            m.id,
                            destinazione=dest,
                            iniziativa_id=e_ini.id if e_ini else None,
                            data_inizio=di,
                            data_fine=df,
                            spesa_prevista=sp or None,
                            obiettivo=ob or None,
                        )
                        st.rerun()

    # --- Flusso autorizzazione ---
    st.markdown("#### Autorizzazione")
    if m.stato in ("bozza", "respinta"):
        if can_edit and st.button("📨 Invia richiesta di autorizzazione"):
            missione_repo.invia_richiesta(m.id)
            st.rerun()
        else:
            st.caption("In bozza: invia la richiesta quando i dati sono completi.")
    elif m.stato == "richiesta":
        if is_admin:
            note = st.text_input("Nota (opzionale)", key=f"nota_{m.id}")
            a1, a2 = st.columns(2)
            if a1.button("✅ Autorizza", type="primary", use_container_width=True):
                missione_repo.autorizza(m.id, persona.id, note or None, UTENTE)
                st.rerun()
            if a2.button("❌ Respingi", use_container_width=True):
                missione_repo.respingi(m.id, persona.id, note or None, UTENTE)
                st.rerun()
        else:
            st.info("In attesa di autorizzazione da parte dell'admin.")
    else:
        chi = nomi.get(m.autorizzata_da, "—")
        quando = f"{m.autorizzata_il:%d/%m/%Y}" if m.autorizzata_il else "—"
        st.success(f"Autorizzata da {chi} il {quando}.")

    # --- Spese sostenute ---
    st.divider()
    st.markdown("#### Spese sostenute")
    if spese:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Data": f"{s.data:%d/%m/%Y}",
                        "Categoria": f"{CATEGORIA_SPESA_ICONA.get(s.categoria, '')} "
                        f"{s.categoria}",
                        "Descrizione": s.descrizione or "",
                        "Importo €": float(s.importo),
                    }
                    for s in spese
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.markdown(f"**Totale automatico: {float(r['totale']):,.2f} €**")
        if can_edit and m.rimborso_stato == "non_richiesto":
            da_eliminare = st.selectbox(
                "Elimina una spesa",
                [None] + spese,
                format_func=lambda s: (
                    "—" if s is None else f"{s.data:%d/%m} · {float(s.importo):,.2f} €"
                ),
                key=f"del_sp_{m.id}",
            )
            if da_eliminare and st.button("🗑 Elimina spesa", key=f"btn_sp_{m.id}"):
                missione_repo.delete_spesa(da_eliminare.id)
                st.rerun()
    else:
        st.caption("Nessuna spesa registrata.")

    if can_edit and m.autorizzata and m.rimborso_stato == "non_richiesto":
        with st.form(f"nuova_spesa_{m.id}", clear_on_submit=True):
            s1, s2, s3 = st.columns(3)
            s_data = s1.date_input("Data", value=m.data_inizio, key=f"sd_{m.id}")
            s_cat = s2.selectbox(
                "Categoria",
                CATEGORIE_SPESA_MISSIONE,
                format_func=lambda c: f"{CATEGORIA_SPESA_ICONA[c]} {c}",
                key=f"sc_{m.id}",
            )
            s_imp = s3.number_input(
                "Importo (€)", min_value=0.0, step=10.0, format="%.2f", key=f"si_{m.id}"
            )
            s_desc = st.text_input("Descrizione", key=f"sx_{m.id}")
            if st.form_submit_button("➕ Aggiungi spesa"):
                if s_imp <= 0:
                    st.error("L'importo deve essere maggiore di zero.")
                else:
                    missione_repo.add_spesa(m.id, s_data, s_cat, s_imp, s_desc or None)
                    st.rerun()
    elif not m.autorizzata:
        st.caption("Le spese si registrano dopo l'autorizzazione.")

    # --- Rimborso ---
    st.divider()
    st.markdown("#### Rimborso")
    if r["rimborsabile"] and can_edit:
        if st.button("💸 Richiedi rimborso", type="primary"):
            missione_repo.richiedi_rimborso(m.id)
            st.rerun()
    elif m.rimborso_stato == "richiesto":
        st.info(f"Rimborso richiesto per **{float(r['totale']):,.2f} €**.")
        if is_admin and st.button("✅ Liquida rimborso", type="primary"):
            missione_repo.liquida_rimborso(m.id, UTENTE)
            st.rerun()
    elif m.rimborso_stato == "liquidato":
        quando = (
            f"{m.rimborso_liquidato_il:%d/%m/%Y}" if m.rimborso_liquidato_il else "—"
        )
        st.success(f"Rimborsato il {quando}.")
    else:
        st.caption("Rimborso richiedibile dopo l'autorizzazione e con spese inserite.")

    # --- Commenti + eliminazione ---
    st.divider()
    blocco_commenti("missione", m.id, persona, is_admin, nomi)

    if is_admin:
        st.divider()
        if st.checkbox("Confermo l'eliminazione", key=f"cf_{m.id}") and st.button(
            "🗑 Elimina missione"
        ):
            missione_repo.delete_missione(m.id)
            st.rerun()


for m in missioni:
    tot = float(totali.get(str(m.id), 0) or 0)
    c1, c2 = st.columns([8.5, 1.5])
    c1.markdown(
        f"**📍 {m.destinazione}** · {STATO_MISSIONE_BADGE.get(m.stato, m.stato)}  \n"
        f"<small>{m.periodo} · 👤 {nomi.get(m.persona_id, '—')}"
        + (f" · 📁 {titoli_ini[m.iniziativa_id]}" if m.iniziativa_id else "")
        + f" · 💰 previsto {float(m.spesa_prevista or 0):,.2f} € / speso {tot:,.2f} €"
        + (
            f" · {STATO_RIMBORSO_BADGE[m.rimborso_stato]}"
            if m.rimborso_stato != "non_richiesto"
            else ""
        )
        + "</small>",
        unsafe_allow_html=True,
    )
    if c2.button("Dettagli", key=f"m_{m.id}", use_container_width=True):
        missione_dialog(m)
