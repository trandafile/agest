"""Report per dipendente — carico task, ferie, presenze, ore. SOLO admin/pm."""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_role
from src.data import persona_repo, report_repo
from src.domain.models import RuoloSistema

require_role(RuoloSistema.admin, RuoloSistema.pm)

st.title("Report per dipendente")

oggi = date.today()
anno = st.selectbox(
    "Anno", range(oggi.year - 2, oggi.year + 1), index=2, key="rep_anno"
)

persone = persona_repo.list_persone(solo_attivi=True)
righe = report_repo.report_dipendenti(anno, persone)

df = pd.DataFrame(
    [
        {
            "Persona": r["persona"],
            "Task attivi": r["task_attivi"],
            "Completati": r["completati_anno"],
            "In ritardo": r["in_ritardo"],
            "Ore stimate": r["ore_stimate"],
            "Puntualità %": (
                round(r["puntualita"], 0) if r["puntualita"] is not None else None
            ),
            "Ferie (gg)": r["ferie_gg"],
            "Malattia (gg)": r["malattia_gg"],
            "Permessi (h)": r["permessi_h"],
            "Presenze (gg)": r["presenze_gg"],
            "Ore medie/gg": round(r["ore_medie_gg"], 2),
            "Ore progettuali": r["ore_progettuali"],
        }
        for r in righe
    ]
)

st.dataframe(df, hide_index=True, use_container_width=True)

st.divider()
c1, c2 = st.columns(2)
c1.subheader("Carico task (attivi)")
c1.bar_chart(df.set_index("Persona")["Task attivi"])
c2.subheader("Ore medie / giorno lavorativo")
c2.bar_chart(df.set_index("Persona")["Ore medie/gg"])

st.subheader("Ore progettuali (timesheet) vs stimate sui task")
st.bar_chart(df.set_index("Persona")[["Ore progettuali", "Ore stimate"]])

# --- Alert ------------------------------------------------------------------
for r in righe:
    if r["in_ritardo"] > 0:
        st.warning(
            f"⚠️ {r['persona']}: {r['in_ritardo']} task in ritardo "
            f"(su {r['task_attivi']} attivi)."
        )

# --- Export -----------------------------------------------------------------
buf = io.BytesIO()
df.to_excel(buf, index=False, sheet_name=f"Report {anno}")
st.download_button(
    "⬇️ Esporta report XLSX",
    buf.getvalue(),
    f"report_dipendenti_{anno}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)

st.caption(
    "Ferie/malattia: giorni **lavorativi** (lun-ven) da assenze approvate. "
    "Ore medie/gg: media delle ore registrate nei giorni di presenza. "
    "Puntualità: task completati entro la scadenza / completati con scadenza."
)
