"""Timesheet — griglia mensile (spec §5): righe = assegnazioni, colonne = giorni.

Salvataggio SOLO alla CONFERMA (che blocca il mese). Regole validate sia
client-side (feedback immediato) sia dai trigger a DB (enforcement).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_login
from src.data import iniziativa_repo, persona_repo, presenze_repo, timesheet_repo
from src.domain.models import RuoloSistema
from src.domain.timesheet import (
    autofill_mese,
    etichetta_giorno,
    giorni_del_mese,
    is_lavorativo,
    riga_valida,
    valida_griglia,
)
from src.lib.labels import getf
from src.lib.rendiconto_xlsx import build_rendiconto_xlsx, nome_file

persona = require_login()

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

# valori esistenti dal DB, eventualmente sovrascritti dall'autofill
val0 = {(str(o.assegnazione_id), o.data): o.ore for o in ore_db}
chiave_af = f"autofill_{sel_persona.id}_{anno}_{mese}"
if stato != "bozza":
    st.session_state.pop(chiave_af, None)
if chiave_af in st.session_state:
    val0 = st.session_state[chiave_af]
nonce = st.session_state.get(f"{chiave_af}_nonce", 0)
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
caz1, caz2 = st.columns([2, 1])
forza = caz1.checkbox(
    "Consenti ore su weekend/festività (flag esplicito)",
    value=False,
    disabled=stato == "confermato",
)
if caz2.button(
    "🪄 Autofill mese (8h/giorno sui giorni lavorativi)",
    disabled=stato == "confermato" or not editabile_da_utente,
    use_container_width=True,
):
    st.session_state[chiave_af] = autofill_mese(anno, mese, info_by_id, festivita)
    st.session_state[f"{chiave_af}_nonce"] = nonce + 1
    st.rerun()

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
    key=f"griglia_{sel_persona.id}_{anno}_{mese}_{nonce}",
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
            "Ore progetto": (
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
            st.session_state.pop(chiave_af, None)
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

# --- Export XLSX per rendicontazione (formato SAL) ---------------------------
st.divider()
with st.expander("📤 Export XLSX per rendicontazione (per progetto)"):
    dettaglio = timesheet_repo.ore_mese_dettaglio(sel_persona.id, anno, mese)
    if not dettaglio:
        st.info("Nessuna ora registrata nel mese: conferma prima il timesheet.")
    else:
        progetti_mese = {}
        for r in dettaglio:
            progetti_mese.setdefault(
                str(r["iniziativa_id"]),
                {
                    "titolo": r["titolo"],
                    "cup": r["cup"],
                    "tipo_desc": r["tipo_progetto_desc"],
                },
            )
        scelta = st.selectbox(
            "Progetto da rendicontare",
            options=list(progetti_mese),
            format_func=lambda k: progetti_mese[k]["titolo"],
        )
        if stato != "confermato":
            st.warning("Il mese è ancora in bozza: l'export riflette i dati salvati.")
        info_p = progetti_mese[scelta]
        ore_ri: dict[int, int] = {}
        ore_ss: dict[int, int] = {}
        ore_altri: dict[int, int] = {}
        for r in dettaglio:
            g = r["data"].day
            if str(r["iniziativa_id"]) == scelta:
                dest = ore_ri if r["tipo_attivita"] == "RI" else ore_ss
                dest[g] = dest.get(g, 0) + int(r["ore"])
            else:
                ore_altri[g] = ore_altri.get(g, 0) + int(r["ore"])
        logo_info = iniziativa_repo.get_logo(scelta)
        contenuto = build_rendiconto_xlsx(
            anno=anno,
            mese=mese,
            cognome=sel_persona.cognome,
            nome=sel_persona.nome,
            codice_fiscale=getf(sel_persona, "codice_fiscale"),
            cup=info_p["cup"],
            soggetto_attuatore=st.secrets.get("app", {}).get(
                "ragione_sociale", "ANTECNICA SRLS"
            ),
            titolo_progetto=info_p["titolo"],
            tipo_progetto=info_p["tipo_desc"],
            monte_ore_annuo=getf(sel_persona, "monte_ore_annuo", 1720),
            ore_ri=ore_ri,
            ore_ss=ore_ss,
            ore_altri_progetti=ore_altri,
            logo=logo_info[0] if logo_info else None,
        )
        st.download_button(
            "⬇️ Scarica XLSX",
            contenuto,
            nome_file(sel_persona.cognome, anno, mese),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        if not info_p["cup"]:
            st.caption("ℹ️ CUP mancante: impostalo in Progetti → Rendicontazione.")
