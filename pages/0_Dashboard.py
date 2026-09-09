"""Dashboard personale — copia lo schema di MAIC tasks:

metriche personali + tab "I miei task" / "Supervisionati", raggruppati per
iniziativa e ordinati per urgenza (scadenza più vicina prima).
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.auth.session import require_login
from src.data import iniziativa_repo, persona_repo, task_repo
from src.domain.models import RuoloSistema, Task
from src.lib.labels import etichetta_progetto
from src.ui.task_ui import riga_task

persona = require_login()
is_admin = persona.ruolo_sistema == RuoloSistema.admin

st.title("Dashboard")
st.markdown(f"Ciao **{persona.nome}** — i task più urgenti su cui lavorare.")

tutti = task_repo.list_tasks(include_archiviati=True)
persone = persona_repo.list_persone()
nomi = {p.id: p.nome_completo for p in persone}
iniziative = iniziativa_repo.list_iniziative()
titoli_ini = {i.id: etichetta_progetto(i) for i in iniziative}

# --- Metriche personali (come MAIC tasks) -----------------------------------
miei_tutti = [t for t in tutti if t.owner_id == persona.id and t.stato != "annullato"]
oggi = date.today()
attivi = [t for t in miei_tutti if t.attivo]
in_ritardo = [t for t in attivi if t.scadenza and t.scadenza < oggi]
completati_30 = [
    t
    for t in miei_tutti
    if t.stato == "completato"
    and t.completato_il
    and t.completato_il >= oggi - timedelta(days=30)
]
completati_con_scadenza = [
    t for t in miei_tutti if t.stato == "completato" and t.completato_il and t.scadenza
]
puntuali = [t for t in completati_con_scadenza if t.completato_il <= t.scadenza]
ritardi = [
    (t.completato_il - t.scadenza).days
    for t in completati_con_scadenza
    if t.completato_il > t.scadenza
]

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Task attivi", len(attivi))
m2.metric(
    "In ritardo",
    len(in_ritardo),
    delta=-len(in_ritardo) if in_ritardo else None,
    delta_color="inverse" if in_ritardo else "off",
)
m3.metric("Completati (30g)", len(completati_30))
m4.metric(
    "Puntualità",
    (
        f"{len(puntuali) / len(completati_con_scadenza) * 100:.0f}%"
        if completati_con_scadenza
        else "—"
    ),
    help="Task completati entro la scadenza / completati con scadenza.",
)
m5.metric(
    "Ritardo medio",
    f"{sum(ritardi) / len(ritardi):.0f}g" if ritardi else "—",
    help="Ritardo medio dei task completati oltre la scadenza.",
)

st.divider()

# --- Tab Miei / Supervisionati -------------------------------------------------
attivi_tutti = [t for t in tutti if t.attivo]
by_id = {t.id: t for t in tutti}


def _radice(t: Task) -> Task:
    """Il task radice (per raggruppare i subtask sotto il padre)."""
    while t.parent_task_id and t.parent_task_id in by_id:
        t = by_id[t.parent_task_id]
    return t


def _render_scope(selezionati: list[Task], key_prefix: str) -> None:
    if not selezionati:
        st.info("Nessun task attivo in questa vista. ✅")
        return

    # raggruppa per iniziativa, ordina per scadenza minima
    gruppi: dict = {}
    for t in selezionati:
        gruppi.setdefault(t.iniziativa_id, []).append(t)

    def urgenza(tasks: list[Task]) -> date:
        scadenze = [t.scadenza for t in tasks if t.scadenza]
        return min(scadenze) if scadenze else date(9999, 12, 31)

    ordinati = sorted(gruppi.items(), key=lambda kv: urgenza(kv[1]))
    for idx, (ini_id, tasks) in enumerate(ordinati):
        titolo = titoli_ini.get(ini_id, "📌 Senza progetto")
        with st.expander(f"📁 {titolo} ({len(tasks)})", expanded=idx == 0):
            radici: dict = {}
            for t in tasks:
                r = _radice(t)
                radici.setdefault(r.id, {"radice": r, "diretti": []})
                if t.id != r.id:
                    radici[r.id]["diretti"].append(t)

            def chiave(nodo):
                r = nodo["radice"]
                return (r.scadenza or date(9999, 12, 31), r.titolo)

            for nodo in sorted(radici.values(), key=chiave):
                r = nodo["radice"]
                riga_task(
                    r,
                    nomi,
                    titoli_ini,
                    persona,
                    is_admin,
                    key_prefix=f"{key_prefix}_r",
                )
                for sub in sorted(
                    nodo["diretti"],
                    key=lambda s: (s.scadenza or date(9999, 12, 31), s.titolo),
                ):
                    riga_task(
                        sub,
                        nomi,
                        titoli_ini,
                        persona,
                        is_admin,
                        key_prefix=f"{key_prefix}_s",
                        indent=True,
                    )


miei = [t for t in attivi_tutti if t.owner_id == persona.id]
supervisionati = [
    t
    for t in attivi_tutti
    if t.supervisor_id == persona.id and t.owner_id != persona.id
]

tab1, tab2 = st.tabs(
    [f"I miei task ({len(miei)})", f"Supervisionati ({len(supervisionati)})"]
)
with tab1:
    _render_scope(miei, "miei")
with tab2:
    st.caption("Task e subtask di cui sei supervisor.")
    _render_scope(supervisionati, "sup")

# --- Monthly report pronti (responsabile di progetto / admin) ------------------
try:
    from src.data import monthly_repo
    from src.lib.monthly_pack import assicura_mese_precedente
    from src.lib.monthly_report import etichetta_mese, nome_file

    assicura_mese_precedente()  # genera il mese precedente se manca (idempotente)
    _pronti = monthly_repo.report_pronti_per_persona(persona.id, is_admin)
except Exception:  # noqa: BLE001 — migrazione 0017 non ancora applicata
    _pronti = []
if _pronti:
    st.divider()
    st.subheader("📆 Monthly report da preparare")
    st.warning(
        f"Ci sono **{len(_pronti)}** file pronti per i monthly report. Scarica il "
        "file .md, compila le «Note del responsabile», incollalo in ChatGPT o "
        "Claude per ottenere la bozza del report, poi segnalo come completato "
        "in **Progetti → 📆 Monthly report**."
    )
    for r in _pronti:
        c1, c2 = st.columns([4, 1.4])
        etich = r["acronimo"] or r["codice"] or r["titolo"]
        c1.markdown(
            f"**{etich}** — {etichetta_mese(r['anno'], r['mese'])} · file generato il "
            f"{r['generato_il']:%d/%m/%Y}"
        )
        rep = monthly_repo.get_report(r["iniziativa_id"], r["anno"], r["mese"])
        if rep:
            c2.download_button(
                "⬇️ Scarica .md",
                rep["contenuto_md"].encode("utf-8"),
                nome_file(r["acronimo"], r["anno"], r["mese"]),
                "text/markdown",
                key=f"mr_dl_{r['id']}",
                use_container_width=True,
            )

# --- Proposte/progetti di cui sono responsabile -----------------------------
mie_iniziative = [i for i in iniziative if i.responsabile_id == persona.id]
if mie_iniziative:
    st.divider()
    st.subheader("📌 Progetti/proposte di cui sei responsabile")
    for i in mie_iniziative:
        tag = "📝 Proposta" if i.tipo == "proposta" else "📊 Progetto"
        st.markdown(
            f"- {tag} · **{etichetta_progetto(i)}** — stato: {i.stato}"
            + (f" · budget {float(i.budget_totale):,.0f} €" if i.budget_totale else "")
        )

# --- Analisi carico di lavoro (admin/pm) ------------------------------------
if persona.ruolo_sistema in (RuoloSistema.admin, RuoloSistema.pm):
    st.divider()
    st.subheader("👥 Carico di lavoro per persona")
    carico = task_repo.carico_per_persona()
    if carico:
        import pandas as pd

        df_c = pd.DataFrame(
            [
                {
                    "Persona": r["nome"],
                    "Task attivi": int(r["attivi"]),
                    "Ore stimate": float(r["ore_stimate"] or 0),
                    "In ritardo": int(r["in_ritardo"]),
                    "Completati (30g)": int(r["completati_30"]),
                }
                for r in carico
            ]
        )
        st.dataframe(df_c, hide_index=True, use_container_width=True)
        st.bar_chart(df_c.set_index("Persona")["Task attivi"])
        sovraccarichi = [r for r in carico if int(r["in_ritardo"]) > 0]
        for r in sovraccarichi:
            st.warning(
                f"⚠️ {r['nome']}: {int(r['in_ritardo'])} task in ritardo "
                f"(su {int(r['attivi'])} attivi)."
            )
    else:
        st.info("Nessun task assegnato al momento.")
