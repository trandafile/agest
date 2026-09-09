"""Monthly report — generazione del file .md «prompt + dati» (v3, spec §13.10).

Regole pure, testabili senza DB. Il file prodotto ha tre parti:
  1. istruzioni per l'assistente AI (ChatGPT, Claude…) con struttura e vincoli
     del report, più le istruzioni specifiche del progetto;
  2. spazio per le note del responsabile (da compilare prima di generare);
  3. dati raccolti dalla piattaforma per il mese: progetto, deliverable,
     milestone, task attivi con note/note datate/cambi di stato/commenti,
     task completati, ore a timesheet, missioni.

Il responsabile incolla il file nel proprio assistente (creazione OFF-LINE
del report) e ottiene la bozza da rifinire.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

MESI_IT = [
    "",
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
]
ATTIVI = ("da_fare", "in_corso", "bloccato")
STATO_TXT = {
    "da_fare": "da fare",
    "in_corso": "in corso",
    "bloccato": "bloccato",
    "completato": "completato",
    "annullato": "annullato",
    "prevista": "prevista",
    "completata": "completata",
    "slittata": "slittata",
}

ISTRUZIONI_DEFAULT = (
    "Lingua del report: inglese. Destinatario: il project officer dell'ente "
    "finanziatore. Lunghezza: massimo due pagine."
)

# «**05/09/2026** — testo» prodotto da «La mia settimana» e dal dialog task
_NOTA_DATATA = re.compile(r"^\*\*(\d{2})/(\d{2})/(\d{4})\*\*\s*[—-]\s*(.+)$")


def mese_precedente(oggi: date) -> tuple[int, int]:
    """(anno, mese) del mese precedente a `oggi`."""
    primo = oggi.replace(day=1)
    prec = primo - timedelta(days=1)
    return prec.year, prec.month


def intervallo_mese(anno: int, mese: int) -> tuple[date, date]:
    """(primo giorno, primo giorno del mese successivo)."""
    inizio = date(anno, mese, 1)
    fine = date(anno + (mese == 12), 1 if mese == 12 else mese + 1, 1)
    return inizio, fine


def etichetta_mese(anno: int, mese: int) -> str:
    return f"{MESI_IT[mese]} {anno}"


def nome_file(acronimo: str | None, anno: int, mese: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", acronimo or "progetto").strip("_")
    return f"monthly_report_{base}_{anno}-{mese:02d}.md"


def note_datate_nel_mese(descrizione: str | None, anno: int, mese: int) -> list[str]:
    """Estrae dalla descrizione del task le note datate («**gg/mm/aaaa** — …»)
    che cadono nel mese."""
    if not descrizione:
        return []
    out = []
    for riga in descrizione.splitlines():
        m = _NOTA_DATATA.match(riga.strip())
        if not m:
            continue
        g, mm, aa, testo = m.groups()
        if int(aa) == anno and int(mm) == mese:
            out.append(f"{g}/{mm}/{aa}: {testo.strip()}")
    return out


def descrizione_senza_note(descrizione: str | None) -> str:
    """La descrizione senza le righe di note datate."""
    if not descrizione:
        return ""
    righe = [r for r in descrizione.splitlines() if not _NOTA_DATATA.match(r.strip())]
    return "\n".join(righe).strip()


def _fmt(d) -> str:
    if isinstance(d, datetime):
        return f"{d:%d/%m/%Y}"
    if isinstance(d, date):
        return f"{d:%d/%m/%Y}"
    return "—"


def _task_md(t: dict, anno: int, mese: int, livello: int = 0) -> list[str]:
    ind = "  " * livello
    stato = STATO_TXT.get(t.get("stato"), t.get("stato") or "")
    riga = f"{ind}- **{t['titolo']}** — {stato}"
    if t.get("owner"):
        riga += f" · owner {t['owner']}"
    if t.get("scadenza"):
        riga += f" · scadenza {_fmt(t['scadenza'])}"
    if t.get("completato_il"):
        riga += f" · completato il {_fmt(t['completato_il'])}"
    ore = []
    if t.get("ore_stimate"):
        ore.append(f"stimate {t['ore_stimate']:g} h")
    if t.get("ore_effettive"):
        ore.append(f"effettive {t['ore_effettive']:g} h")
    if ore:
        riga += " · " + ", ".join(ore)
    out = [riga]
    desc = descrizione_senza_note(t.get("descrizione"))
    if desc:
        out.append(f"{ind}  - Note del task: " + desc.replace("\n", " ").strip())
    for n in note_datate_nel_mese(t.get("descrizione"), anno, mese):
        out.append(f"{ind}  - Nota del {n}")
    for s in t.get("storico", []):
        if not s.get("da"):
            out.append(f"{ind}  - Creato il {_fmt(s['quando'])}")
            continue
        out.append(
            f"{ind}  - Cambio di stato il {_fmt(s['quando'])}: "
            f"{STATO_TXT.get(s.get('da'), s.get('da'))} → "
            f"{STATO_TXT.get(s.get('a'), s.get('a'))}"
        )
    for c in t.get("commenti", []):
        out.append(
            f"{ind}  - Commento di {c.get('autore') or '—'} ({_fmt(c.get('quando'))}): "
            + str(c.get("testo") or "").replace("\n", " ").strip()
        )
    for sub in t.get("subtask", []):
        out += _task_md(sub, anno, mese, livello + 1)
    return out


def genera_md(pack: dict) -> str:
    """Il file .md completo a partire dal pack (vedi `monthly_pack`)."""
    anno, mese = pack["anno"], pack["mese"]
    p = pack["progetto"]
    inizio, fine = intervallo_mese(anno, mese)
    ultimo = fine - timedelta(days=1)
    mese_txt = etichetta_mese(anno, mese)
    generato = pack.get("generato_il") or date.today()

    righe: list[str] = []
    a = righe.append
    a(f"# Monthly report — {p.get('acronimo') or p.get('titolo')} — {mese_txt}")
    a("")
    a(
        f"> File generato automaticamente da ANTECNICA Gestionale il {_fmt(generato)}. "
        "Compila la sezione «Note del responsabile», poi incolla l'intero file in "
        "ChatGPT o Claude (o allegalo) e chiedi di produrre il monthly report "
        "seguendo le istruzioni qui sotto."
    )
    a("")
    a("## Istruzioni per l'assistente AI")
    a("")
    a(
        f"Sei l'assistente del responsabile del progetto **{p.get('titolo')}** "
        f"({p.get('acronimo') or '—'}). Usando ESCLUSIVAMENTE i dati riportati in "
        "questo file (sezione «Dati raccolti dalla piattaforma») e le «Note del "
        f"responsabile», scrivi il monthly report di **{mese_txt}** "
        f"(periodo {_fmt(inizio)} – {_fmt(ultimo)})."
    )
    a("")
    a("Requisiti:")
    a("")
    a("1. Struttura del report:")
    a("   1. Executive summary (massimo cinque righe).")
    a("   2. Attività svolte nel mese, raggruppate per deliverable / work package.")
    a("   3. Stato di deliverable e milestone (completati, in corso, in ritardo).")
    a("   4. Problemi, rischi e punti bloccanti, con l'azione prevista.")
    a("   5. Piano per il mese successivo.")
    a("   6. Risorse impiegate (ore/persona), se disponibili.")
    a(
        "2. Non inventare attività, risultati o numeri non presenti nei dati; dove "
        "manca un'informazione scrivi «[DA VERIFICARE]»."
    )
    a("3. Tono tecnico e sobrio, frasi brevi; formato Markdown.")
    a(
        "4. Le note datate, i cambi di stato e i commenti sono la cronaca del mese: "
        "usali per descrivere COSA è stato fatto e PERCHÉ."
    )
    a("")
    a("Istruzioni specifiche del progetto:")
    a("")
    a(f"> {p.get('istruzioni') or ISTRUZIONI_DEFAULT}")
    a("")
    a("## Note del responsabile (da compilare prima di generare)")
    a("")
    a("- Risultati principali del mese: …")
    a("- Problemi, rischi, decisioni prese: …")
    a("- Piano per il prossimo mese: …")
    a("- Altre informazioni (riunioni, interazioni con l'ente, missioni): …")
    a("")
    a("## Dati raccolti dalla piattaforma")
    a("")
    a("### Progetto")
    a("")
    a(f"- Acronimo: {p.get('acronimo') or '—'}")
    a(f"- Titolo: {p.get('titolo') or '—'}")
    a(f"- Identificativo: {p.get('codice') or '—'}")
    a(f"- Ente finanziatore / cliente: {p.get('controparte') or '—'}")
    a(f"- CUP: {p.get('cup') or '—'}")
    a(f"- Periodo del progetto: {_fmt(p.get('inizio'))} – {_fmt(p.get('fine'))}")
    a(f"- Responsabile: {p.get('responsabile') or '—'}")
    a(f"- Stato: {p.get('stato') or '—'}")
    a(f"- Mese di riferimento: {mese_txt} ({_fmt(inizio)} – {_fmt(ultimo)})")
    a("")

    a("### Deliverable (stato a fine mese)")
    a("")
    delivs = pack.get("deliverables", [])
    if delivs:
        a("| Deliverable | Tipo | Stato | Scadenza | Owner | Task completati/totali |")
        a("|---|---|---|---|---|---|")
        for d in delivs:
            a(
                f"| {d['titolo']} | {d.get('tipo') or '—'} | "
                f"{STATO_TXT.get(d.get('stato'), d.get('stato') or '')} | "
                f"{_fmt(d.get('scadenza'))} | {d.get('owner') or '—'} | "
                f"{d.get('task_completati', 0)}/{d.get('task_totali', 0)} |"
            )
    else:
        a("Nessun deliverable registrato.")
    a("")

    a("### Milestone")
    a("")
    ms = pack.get("milestone", [])
    if ms:
        for m in ms:
            a(
                f"- {m['titolo']} — "
                f"{STATO_TXT.get(m.get('stato'), m.get('stato') or '')}"
                f" · prevista {_fmt(m.get('data'))}"
                + (" · **nel mese**" if m.get("nel_mese") else "")
            )
    else:
        a("Nessuna milestone registrata.")
    a("")

    a("### Task attivi nel mese")
    a("")
    attivi = pack.get("task_attivi", [])
    if attivi:
        for gruppo in attivi:
            a(f"#### {gruppo['deliverable'] or 'Senza deliverable'}")
            a("")
            for t in gruppo["task"]:
                righe += _task_md(t, anno, mese)
            a("")
    else:
        a("Nessun task attivo nel mese.")
        a("")

    a("### Task completati nel mese")
    a("")
    comp = pack.get("task_completati", [])
    if comp:
        for t in comp:
            righe += _task_md(t, anno, mese)
    else:
        a("Nessun task completato nel mese.")
    a("")

    a("### Ore a timesheet nel mese")
    a("")
    ore = pack.get("ore_timesheet", [])
    if ore:
        a("| Persona | Ore |")
        a("|---|---|")
        tot = 0.0
        for r in ore:
            a(f"| {r['persona']} | {float(r['ore']):g} |")
            tot += float(r["ore"])
        a(f"| **Totale** | **{tot:g}** |")
    else:
        a("Nessuna ora registrata a timesheet per il progetto nel mese.")
    a("")

    a("### Missioni nel mese")
    a("")
    miss = pack.get("missioni", [])
    if miss:
        for m in miss:
            a(
                f"- {m['persona']} — {m['destinazione']} "
                f"({_fmt(m.get('inizio'))} – {_fmt(m.get('fine'))})"
                + (f": {m['obiettivo']}" if m.get("obiettivo") else "")
            )
    else:
        a("Nessuna missione nel mese.")
    a("")

    a("### Commenti sul progetto nel mese")
    a("")
    cp = pack.get("commenti_progetto", [])
    if cp:
        for c in cp:
            a(f"- {c.get('autore') or '—'} ({_fmt(c.get('quando'))}): {c['testo']}")
    else:
        a("Nessun commento a livello di progetto.")
    a("")
    a("---")
    a(
        "*Dati estratti da ANTECNICA Gestionale · "
        f"{calendar.monthrange(anno, mese)[1]} "
        f"giorni nel mese · generato il {_fmt(generato)}.*"
    )
    return "\n".join(righe) + "\n"
