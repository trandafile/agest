"""Import di deliverable, task e subtask in UNA iniziativa da YAML/JSON
incollato (schema `agest-import/v1`, gemello di `maic-tasks-import/v1`).

    parse_payload()  testo -> dati
    validate()       dati + istantanea dell'iniziativa -> Piano (non scrive)
    (scrittura)      src/data/task_import_repo.applica_piano(), in UNA
                     transazione: o tutto o niente.

Logica pura: nessuna dipendenza da DB o Streamlit (testabile).

Regole (come MAIC tasks, adattate al modello ANTECNICA)
* Tutto vive nell'iniziativa da cui l'import è aperto.
* Gli elementi esistenti si indicano con ``ref`` — l'identificativo breve
  ``#xxxxxxxx`` mostrato nel prompt — e si confermano con ``match_title``:
  se il titolo non corrisponde il file è invalido (non si tocca l'elemento
  sbagliato). Senza ``ref`` basta ``match_title`` se è univoco fra i fratelli.
* Le persone si scrivono per nome e si risolvono sull'anagrafica attiva;
  un nome ambiguo o sconosciuto rende il file invalido.
* Niente si cancella: ``cancel`` porta lo stato ad «annullato».
* Duplicati: un elemento citato due volte, due create con lo stesso titolo
  sotto lo stesso padre, o una create il cui titolo esiste già lì rendono il
  file invalido (salvo ``consenti_duplicati``): incollare due volte lo stesso
  file non raddoppia il lavoro.
* Le chiavi e i valori di MAIC tasks (inglese) sono accettati, insieme agli
  equivalenti italiani: un prompt scritto per un'app funziona anche nell'altra.
"""

from __future__ import annotations

import datetime as _dt
import difflib
import json
import re
import unicodedata
from typing import Any

SCHEMA_ID = "agest-import/v1"
SCHEMI_COMPATIBILI = ("maic-tasks-import/v1",)

STATI = ("da_fare", "in_corso", "bloccato", "completato", "annullato")
PRIORITA = ("urgente", "alta", "media", "bassa", "nessuna")
TIPI = ("prototipo", "report", "paper", "altro")
CHIUSI = ("completato", "annullato")

_ALIAS_STATO = {
    # italiano
    "da fare": "da_fare", "dafare": "da_fare", "nuovo": "da_fare",
    "pianificato": "da_fare", "aperto": "da_fare",
    "in corso": "in_corso", "incorso": "in_corso", "avviato": "in_corso",
    "bloccato": "bloccato", "sospeso": "bloccato", "in attesa": "bloccato",
    "completato": "completato", "fatto": "completato", "chiuso": "completato",
    "concluso": "completato", "terminato": "completato",
    "annullato": "annullato", "cancellato": "annullato",
    # inglese (MAIC tasks)
    "not started": "da_fare", "todo": "da_fare", "to do": "da_fare",
    "open": "da_fare", "new": "da_fare", "planned": "da_fare",
    "working on": "in_corso", "in progress": "in_corso", "working": "in_corso",
    "ongoing": "in_corso", "wip": "in_corso", "started": "in_corso",
    "blocked": "bloccato", "on hold": "bloccato",
    "completed": "completato", "complete": "completato", "done": "completato",
    "closed": "completato", "finished": "completato",
    "cancelled": "annullato", "canceled": "annullato", "dropped": "annullato",
}
_ALIAS_PRIORITA = {
    "urgente": "urgente", "urgent": "urgente", "critical": "urgente",
    "critica": "urgente", "highest": "urgente",
    "alta": "alta", "high": "alta",
    "media": "media", "medium": "media", "normal": "media", "normale": "media",
    "med": "media",
    "bassa": "bassa", "low": "bassa", "lowest": "bassa",
    "nessuna": "nessuna", "none": "nessuna", "": "nessuna",
}
_ALIAS_TIPO = {
    "prototipo": "prototipo", "prototype": "prototipo", "demo": "prototipo",
    "demonstrator": "prototipo", "layout": "prototipo",
    "report": "report", "relazione": "report", "documento": "report",
    "rapporto": "report", "deliverable": "report",
    "paper": "paper", "articolo": "paper", "pubblicazione": "paper",
    "publication": "paper",
    "altro": "altro", "other": "altro",
}

# Chiavi accettate -> chiave canonica (inglese, come MAIC tasks)
_ALIAS_CHIAVI = {
    "azione": "action", "titolo": "title", "nome": "title", "name": "title",
    "stato": "status", "scadenza": "due", "deadline": "due",
    "responsabile": "owner", "assegnatario": "assignee",
    "descrizione": "description", "note": "description", "notes": "description",
    "nota": "description_append", "aggiungi_descrizione": "description_append",
    "priorita": "priority", "priorità": "priority", "tipo": "type",
    "ore_stimate": "estimate_hours", "ore": "estimate_hours",
    "da": "from", "verifica_titolo": "match_title",
    "sottotask": "subtasks", "subtask": "subtasks",
}
_ALIAS_TOP = {"progetto": "project", "default": "defaults", "predefiniti": "defaults"}

AZIONI = {
    "deliverable": ("create", "update", "complete", "cancel", "keep"),
    "task": ("create", "update", "move", "complete", "cancel", "keep"),
    "subtask": ("create", "update", "move", "complete", "cancel", "keep"),
}
_ALIAS_AZIONE = {
    "crea": "create", "nuovo": "create", "aggiorna": "update", "modifica": "update",
    "sposta": "move", "completa": "complete", "chiudi": "complete",
    "annulla": "cancel", "mantieni": "keep", "lascia": "keep",
}
_COMUNI = {"action", "ref", "key", "match_title", "from", "title", "status", "due",
           "supervisor", "description", "description_append", "gantt"}
CHIAVI = {
    "deliverable": _COMUNI | {"type", "owner", "tasks"},
    "task": _COMUNI | {"priority", "assignee", "owner", "estimate_hours", "subtasks"},
    "subtask": _COMUNI | {"assignee", "owner", "estimate_hours"},
}
_CHIAVI_CAMPO = {"title", "type", "status", "owner", "assignee", "supervisor", "due",
                 "priority", "description", "description_append", "estimate_hours",
                 "gantt"}
TOP_KEYS = {"schema", "project", "defaults", "deliverables"}
DEFAULT_KEYS = {"supervisor", "status", "priority", "subtask_assignee", "owner"}

TITLE_MATCH = 0.85  # match_title vs titolo reale
DUP_MATCH = 0.90    # una create che somiglia a un fratello esistente
SENZA_DELIVERABLE = ("0", "#0", "e.0", "none", "nessuno", "senza deliverable")


# ── testo ─────────────────────────────────────────────────────────────────────

def _norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w]+", " ", s.casefold())
    return " ".join(s.split())


def similarity(a: Any, b: Any) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def ref_breve(id_: Any) -> str:
    """Identificativo breve mostrato nel prompt: «#» + 8 cifre esadecimali."""
    return "#" + str(id_).replace("-", "")[:8]


def _fmt_data(iso: Any) -> str:
    if not iso:
        return "—"
    try:
        return _dt.date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)


# ── parsing ───────────────────────────────────────────────────────────────────

def parse_payload(text: str) -> tuple[Any, str | None]:
    """(dati, errore). JSON se sembra JSON, altrimenti YAML."""
    text = (text or "").strip()
    if not text:
        return None, "Incolla prima un contenuto YAML o JSON."
    fence = re.match(r"^```[\w-]*\s*\n(.*?)\n```\s*$", text, re.S)
    if fence:  # blocchi di codice copiati da una chat
        text = fence.group(1)
    if text[:1] in "{[":
        try:
            return json.loads(text), None
        except json.JSONDecodeError as exc:
            return None, (f"JSON non valido (riga {exc.lineno}, colonna {exc.colno}): "
                          f"{exc.msg}.")
    try:
        import yaml
    except ImportError:
        return None, "Il supporto YAML (pyyaml) non è installato: incolla JSON."
    try:
        return yaml.safe_load(text), None
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        dove = f" (riga {mark.line + 1}, colonna {mark.column + 1})" if mark else ""
        prob = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        return None, f"YAML non valido{dove}: {prob}."


def _canon(d: Any, alias: dict) -> Any:
    """Rinomina le chiavi di un mapping secondo `alias` (senza perdere quelle
    sconosciute, che la validazione segnalerà)."""
    if not isinstance(d, dict):
        return d
    out: dict = {}
    for k, v in d.items():
        kk = str(k).strip()
        out[alias.get(kk.casefold(), alias.get(kk, kk))] = v
    return out


# ── persone ───────────────────────────────────────────────────────────────────

class Persone:
    """Nomi scritti nel file -> id delle persone attive in anagrafica.

    `persone`: lista di dict {id, nome, cognome, email}."""

    def __init__(self, persone: list[dict], me: Any = None):
        self.persone = [p for p in (persone or []) if p.get("id")]
        self.me = me
        self._by_id = {str(p["id"]): p for p in self.persone}
        self._by_email = {str(p.get("email") or "").casefold(): p
                          for p in self.persone if p.get("email")}

    @staticmethod
    def _nome(p: dict) -> str:
        return f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip()

    def nome(self, id_: Any) -> str:
        if not id_:
            return "—"
        p = self._by_id.get(str(id_))
        return self._nome(p) if p else str(id_)

    def _token(self, p: dict) -> list[str]:
        local = str(p.get("email") or "").split("@")[0]
        return _norm(self._nome(p)).split() + _norm(local.replace(".", " ")).split()

    def risolvi(self, testo: Any) -> tuple[Any, str | None, str | None]:
        """(id, errore, nota). La nota dice come è stato letto un nome breve."""
        raw = str(testo or "").strip()
        if not raw:
            return None, "nome vuoto", None
        if raw.casefold() in ("me", "myself", "io", "me stesso"):
            return self.me, None, None
        if "@" in raw:
            p = self._by_email.get(raw.casefold())
            if p:
                return p["id"], None, None
            return None, f"'{raw}': nessuna persona con questa e-mail", None
        q = _norm(raw)
        esatti = [p for p in self.persone if _norm(self._nome(p)) == q
                  or _norm(f"{p.get('cognome') or ''} {p.get('nome') or ''}") == q]
        if len(esatti) == 1:
            return esatti[0]["id"], None, None
        qt = q.split()
        cand = [p for p in self.persone
                if all(any(nt.startswith(t) for nt in self._token(p)) for t in qt)]
        if len(cand) == 1:
            return cand[0]["id"], None, f"'{raw}' → {self._nome(cand[0])}"
        if len(cand) > 1:
            nomi = ", ".join(sorted(self._nome(p) for p in cand))
            return None, f"'{raw}' è ambiguo ({nomi}): scrivi nome e cognome", None
        fuzzy = [p for p in self.persone
                 if all(any(difflib.SequenceMatcher(None, t, nt).ratio() >= 0.8
                            for nt in self._token(p)) for t in qt)]
        if len(fuzzy) == 1:
            return fuzzy[0]["id"], None, f"'{raw}' → {self._nome(fuzzy[0])} (approssimato)"
        if len(fuzzy) > 1:
            nomi = ", ".join(sorted(self._nome(p) for p in fuzzy))
            return None, f"'{raw}' è ambiguo ({nomi}): scrivi nome e cognome", None
        vicini = difflib.get_close_matches(
            raw, [self._nome(p) for p in self.persone], n=3, cutoff=0.5)
        hint = f" — forse {', '.join(vicini)}?" if vicini else ""
        return None, f"'{raw}': nessuna persona con questo nome{hint}", None


# ── piano ─────────────────────────────────────────────────────────────────────

class Op:
    """Una modifica. ``parent`` è l'Op deliverable di un task (l'Op «0» per i
    task senza deliverable) o l'Op task di un subtask."""

    def __init__(self, kind: str, action: str, row: dict | None = None,
                 parent: "Op | None" = None, label: str = ""):
        self.kind, self.action, self.row, self.parent = kind, action, row, parent
        self.label = label
        self.fields: dict = {}
        self.changes: list[tuple[str, str, str]] = []
        self.loose = False          # il contenitore «senza deliverable»
        self.key: str | None = None
        self.gantt_code: str | None = None

    @property
    def final(self) -> dict:
        return {**(self.row or {}), **self.fields}

    @property
    def title(self) -> str:
        return self.final.get("titolo") or ""

    @property
    def ident(self) -> tuple:
        if self.loose:
            return ("loose",)
        return ("id", str(self.row["id"])) if self.row else ("new", id(self))

    @property
    def ref(self) -> str:
        if self.loose:
            return "0"
        return ref_breve(self.row["id"]) if self.row else "(nuovo)"


class Piano:
    def __init__(self) -> None:
        self.ops: list[Op] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def changes(self) -> list[Op]:
        """Le voci che scrivono davvero (un update senza differenze non conta)."""
        return [o for o in self.ops if not o.loose and (o.action == "create" or o.fields)]

    def counts(self) -> dict:
        out: dict = {}
        for o in self.changes():
            out[(o.kind, o.action)] = out.get((o.kind, o.action), 0) + 1
        return out


# ── valori ────────────────────────────────────────────────────────────────────

def _stato(v: Any) -> tuple[str | None, str | None]:
    if v is None:
        return None, "lo stato è vuoto"
    k = _norm(v).replace("_", " ")
    s = _ALIAS_STATO.get(k) or _ALIAS_STATO.get(k.replace(" ", ""))
    if s:
        return s, None
    return None, f"stato '{v}' non valido ({', '.join(STATI)})"


def _priorita(v: Any) -> tuple[str | None, str | None]:
    p = _ALIAS_PRIORITA.get(_norm(v))
    if p:
        return p, None
    return None, f"priorità '{v}' non valida ({', '.join(PRIORITA)})"


def _data(v: Any) -> tuple[str | None, str | None]:
    """(iso | None, errore). None/'' azzera la data."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None, None
    if isinstance(v, _dt.datetime):
        v = v.date()
    if isinstance(v, _dt.date):
        return v.isoformat(), None
    s = str(v).strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return _dt.datetime.strptime(s, f).date().isoformat(), None
        except ValueError:
            pass
    return None, f"data '{v}' non valida (usa AAAA-MM-GG)"


def _ore(v: Any) -> tuple[float | None, str | None]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None, None
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        return None, f"ore stimate '{v}' non valide"
    if x < 0:
        return None, f"ore stimate '{v}' negative"
    return round(x, 1), None


# ── validazione ───────────────────────────────────────────────────────────────

def validate(data: Any, iniziativa: dict, snap: dict, persone: list[dict], me: Any,
             consenti_duplicati: bool = False,
             gantt_codici: dict | None = None) -> Piano:
    """Costruisce il piano senza scrivere nulla.

    iniziativa: {id, acronimo, codice, titolo}
    snap: {"deliverables": [...], "tasks": [...]} (archiviati inclusi; i
          subtask sono task con `parent_task_id`)
    persone: [{id, nome, cognome, email}] attive
    gantt_codici: {codice_voce: id} del Gantt dell'iniziativa (facoltativo)
    """
    piano = Piano()
    E, W = piano.errors.append, piano.warnings.append
    people = Persone(persone, me)
    gantt_codici = {str(k).casefold(): v for k, v in (gantt_codici or {}).items()}
    iid = iniziativa.get("id")

    if not isinstance(data, dict):
        E("Il contenuto deve essere un mapping con schema, project, defaults e "
          "deliverables.")
        return piano
    data = _canon(data, _ALIAS_TOP)
    for k in data:
        if k not in TOP_KEYS:
            E(f"Chiave di primo livello sconosciuta '{k}' "
              f"(ammesse: {', '.join(sorted(TOP_KEYS))}).")
    schema = data.get("schema")
    if schema is None:
        W(f"Nessuna riga 'schema': letto come {SCHEMA_ID}.")
    elif str(schema).strip() in SCHEMI_COMPATIBILI:
        W(f"schema '{schema}' (MAIC tasks) letto come {SCHEMA_ID}: i ref in forma "
          "E.1.2 non esistono qui, usa match_title o i #ref del prompt.")
    elif str(schema).strip() != SCHEMA_ID:
        E(f"schema '{schema}' non supportato (atteso {SCHEMA_ID}).")

    # ── l'iniziativa: tutto deve appartenere a quella da cui si importa
    acr = iniziativa.get("acronimo") or iniziativa.get("codice") or ""
    tit = iniziativa.get("titolo") or ""
    proj = _canon(data.get("project"), {"acronimo": "code", "codice": "code",
                                        "titolo": "name", "nome": "name"})
    if not isinstance(proj, dict) or not (proj.get("code") or proj.get("name")):
        E("'project' deve indicare l'acronimo (code) e/o il titolo (name) di questa "
          "iniziativa.")
    else:
        code = str(proj.get("code") or "").strip()
        if code and _norm(code) not in (_norm(acr), _norm(tit),
                                        _norm(iniziativa.get("codice"))):
            E(f"project.code '{code}' non è questa iniziativa ({acr or tit}): un "
              "import tocca solo l'iniziativa da cui è aperto.")
        name = proj.get("name")
        if name and max(similarity(name, acr), similarity(name, tit),
                        similarity(name, f"{acr} {tit}")) < TITLE_MATCH \
                and _norm(name) not in _norm(f"{acr} {tit}"):
            E(f"project.name '{name}' non corrisponde a questa iniziativa "
              f"({acr} · {tit}).")

    # ── defaults
    dfl = _canon(data.get("defaults") or {}, {**_ALIAS_CHIAVI,
                                              "subtask_owner": "subtask_assignee"})
    if not isinstance(dfl, dict):
        E("'defaults' deve essere un mapping.")
        dfl = {}
    for k in dfl:
        if k not in DEFAULT_KEYS:
            E(f"defaults: chiave sconosciuta '{k}' "
              f"(ammesse: {', '.join(sorted(DEFAULT_KEYS))}).")

    def persona(value: Any, where: str, allow_none: bool = False) -> Any:
        if value is None or (allow_none and _norm(value) in ("none", "nobody", "nessuno", "")):
            return None
        pid, err, nota = people.risolvi(value)
        if err:
            E(f"{where}: {err}.")
            return None
        if nota and nota not in piano.notes:
            piano.notes.append(nota)
        return pid

    d_sup = persona(dfl.get("supervisor"), "defaults.supervisor", allow_none=True)
    d_owner = persona(dfl.get("owner"), "defaults.owner") if dfl.get("owner") else me
    d_stato = "da_fare"
    if dfl.get("status") is not None:
        d_stato, err = _stato(dfl.get("status"))
        if err:
            E(f"defaults: {err}.")
            d_stato = "da_fare"
    d_prio = "media"
    if dfl.get("priority") is not None:
        d_prio, err = _priorita(dfl.get("priority"))
        if err:
            E(f"defaults: {err}.")
            d_prio = "media"
    sub_eredita, sub_default = True, None
    sa = dfl.get("subtask_assignee", "inherit")
    if sa is not None and _norm(sa) not in ("inherit", "eredita"):
        sub_eredita, sub_default = False, persona(sa, "defaults.subtask_assignee")

    # ── cosa esiste
    ds = snap.get("deliverables", [])
    tutti = snap.get("tasks", [])
    ts = [t for t in tutti if not t.get("parent_task_id")]
    ss = [t for t in tutti if t.get("parent_task_id")]
    by_ref = {
        "deliverable": {ref_breve(d["id"]): d for d in ds},
        "task": {ref_breve(t["id"]): t for t in ts},
        "subtask": {ref_breve(s["id"]): s for s in ss},
    }
    by_full = {k: {str(r["id"]): r for r in v.values()} for k, v in by_ref.items()}

    toccati: dict = {}
    chiavi_viste: dict = {}
    creati: dict = {}

    def cerca(kind: str, code: str) -> dict | None:
        c = code.strip()
        if c.startswith("#"):
            return by_ref[kind].get(c[:9].lower())
        if re.fullmatch(r"[0-9a-fA-F-]{32,36}", c):
            return by_full[kind].get(c.lower())
        if re.fullmatch(r"[0-9a-fA-F]{8}", c):
            return by_ref[kind].get("#" + c.lower())
        return None

    def fratelli(kind: str, parent: Op | None) -> list[tuple[str, dict]]:
        """[(ref, riga)] degli elementi attivi sotto `parent`."""
        if kind == "deliverable":
            return [(ref_breve(d["id"]), d) for d in ds if not d.get("archiviato")]
        if parent is None or (parent.row is None and not parent.loose):
            return []
        if kind == "task":
            pid_ = None if parent.loose else str(parent.row["id"])
            return [(ref_breve(t["id"]), t) for t in ts if not t.get("archiviato")
                    and (str(t["deliverable_id"]) if t.get("deliverable_id") else None) == pid_]
        return [(ref_breve(s["id"]), s) for s in ss if not s.get("archiviato")
                and str(s.get("parent_task_id")) == str(parent.row["id"])]

    # ── una voce (deliverable, task o subtask) ──────────────────────────────
    def entry_op(kind: str, e: Any, where: str, parent: Op | None) -> Op | None:
        if not isinstance(e, dict):
            E(f"{where}: deve essere un mapping.")
            return None
        for k in e:
            if k not in CHIAVI[kind]:
                E(f"{where}: chiave sconosciuta '{k}'.")
        if e.get("key") is not None:
            kk = str(e["key"]).strip()
            if kk in chiavi_viste:
                E(f"{where}: key '{kk}' già usata in {chiavi_viste[kk]}.")
            chiavi_viste[kk] = where
        ref = str(e["ref"]).strip() if e.get("ref") not in (None, "") else None
        frm = str(e["from"]).strip() if e.get("from") not in (None, "") else None
        action = str(e.get("action") or "").strip().lower()
        action = _ALIAS_AZIONE.get(action, action)
        if not action:
            if ref or frm or e.get("match_title"):
                E(f"{where}: manca 'action' (per gli elementi esistenti: update, move, "
                  "complete, cancel o keep).")
                return None
            action = "create"
        if action not in AZIONI[kind]:
            E(f"{where}: azione '{action}' non valida per un {kind} "
              f"({', '.join(AZIONI[kind])}).")
            return None

        # il contenitore dei task senza deliverable
        if kind == "deliverable" and ref is not None and ref.casefold() in SENZA_DELIVERABLE:
            if action != "keep":
                E(f"{where}: il contenitore «0» (task senza deliverable) accetta solo "
                  "action: keep.")
            extra = sorted(k for k in e if k in _CHIAVI_CAMPO)
            if extra:
                E(f"{where}: il contenitore «0» non ha campi da modificare "
                  f"({', '.join(extra)}).")
            op = Op(kind, "keep", None, None, where)
            op.loose = True
            return op

        if frm and action != "move":
            E(f"{where}: 'from' si usa solo con action: move.")
            return None

        if action == "create":
            if ref:
                E(f"{where}: una create non ha ref — l'identificativo lo assegna il "
                  "database.")
                return None
            title = str(e.get("title") or "").strip()
            if not title:
                E(f"{where}: per creare un {kind} serve il titolo (title).")
                return None
            op = Op(kind, "create", None, parent, where)
            op.key = e.get("key")
            pkey = parent.ident if parent else ("progetto",)
            miei = creati.setdefault((kind, pkey), [])
            for nt, w in miei:
                if similarity(nt, title) >= DUP_MATCH:
                    E(f"{where}: '{title}' è creato due volte sotto lo stesso padre "
                      f"(anche in {w}).")
            miei.append((title, where))
            for sref, sib in fratelli(kind, parent):
                if similarity(sib.get("titolo"), title) >= DUP_MATCH:
                    msg = (f"{where}: '{title}' esiste già come {sref} "
                           f"'{sib.get('titolo')}' — usa action update/keep con ref: "
                           f"{sref}")
                    (W if consenti_duplicati else E)(
                        msg + (" (creato comunque)." if consenti_duplicati else "."))
            return op

        # un elemento esistente
        hint = e.get("match_title")
        if not hint:
            E(f"{where}: match_title è obbligatorio per gli elementi esistenti "
              "(conferma il ref).")
            return None
        code = frm if (action == "move" and frm) else ref
        if code:
            row = cerca(kind, code)
            if row is None:
                altro = next((k for k in by_ref if k != kind and cerca(k, code)), None)
                extra = f" (è un {altro})" if altro else ""
                E(f"{where}: {code} non esiste fra i {kind} di questa iniziativa{extra}.")
                return None
        else:
            if action == "move":
                E(f"{where}: move richiede ref (o from) dell'elemento da spostare.")
                return None
            cands = [(c, r) for c, r in fratelli(kind, parent)
                     if similarity(r.get("titolo"), hint) >= TITLE_MATCH]
            if not cands:
                E(f"{where}: nessun {kind} intitolato '{hint}' qui — indica il ref.")
                return None
            if len(cands) > 1:
                E(f"{where}: '{hint}' corrisponde a {', '.join(c for c, _ in cands)} "
                  "— indica il ref.")
                return None
            code, row = cands[0]
        rref = ref_breve(row["id"])
        if row.get("archiviato"):
            E(f"{where}: {rref} è archiviato e non può essere modificato da un import.")
            return None
        sc = similarity(row.get("titolo"), hint)
        if sc < TITLE_MATCH:
            E(f"{where}: {rref} è '{row.get('titolo')}', non '{hint}' (match_title).")
            return None
        if sc < 1.0:
            W(f"{where}: match_title '{hint}' letto come {rref} '{row.get('titolo')}'.")
        tkey = (kind, str(row["id"]))
        if tkey in toccati:
            E(f"{where}: {rref} è già citato in {toccati[tkey]} — una voce per "
              "elemento.")
            return None
        toccati[tkey] = where
        op = Op(kind, action, row, parent, where)
        op.key = e.get("key")
        if kind == "deliverable":
            return op
        if kind == "task":
            cur = ("id", str(row["deliverable_id"])) if row.get("deliverable_id") else ("loose",)
        else:
            cur = ("id", str(row["parent_task_id"]))
        if action == "move":
            if parent and parent.ident == cur:
                E(f"{where}: {rref} è già sotto {parent.ref} — niente da spostare.")
                return None
        elif parent and parent.ident != cur:
            E(f"{where}: {rref} non è sotto {parent.ref} — per spostarlo usa "
              f"action: move, ref: {rref}.")
            return None
        return op

    # ── campi di una voce ────────────────────────────────────────────────────
    def campi(op: Op, e: dict, where: str) -> None:
        kind, row = op.kind, op.row or {}
        create = op.action == "create"
        out: dict = {}
        ch = op.changes

        def put(col: str, new: Any, label: str, show=lambda v: v if v not in (None, "") else "—"):
            old = row.get(col)
            if isinstance(old, _dt.date):
                old = old.isoformat()
            if create:
                out[col] = new
            elif not _uguali(old, new):
                out[col] = new
                ch.append((label, str(show(old)), str(show(new))))

        if op.action == "keep":
            extra = sorted(k for k in e if k in _CHIAVI_CAMPO)
            if extra:
                E(f"{where}: keep non cambia nulla ({', '.join(extra)} indicati) — "
                  "usa update.")
            return
        if "title" in e and str(e.get("title") or "").strip():
            put("titolo", str(e["title"]).strip(), "titolo")
        elif "title" in e and not create:
            E(f"{where}: il titolo non può essere vuoto.")

        if kind == "deliverable" and ("type" in e or create):
            raw = e.get("type")
            if raw is None:
                if create:
                    put("tipo", None, "tipo")
            else:
                hit = _ALIAS_TIPO.get(_norm(raw))
                if hit:
                    put("tipo", hit, "tipo")
                else:
                    E(f"{where}: tipo '{raw}' non valido ({', '.join(TIPI)}).")

        stato = None
        if "status" in e:
            stato, err = _stato(e.get("status"))
            if err:
                E(f"{where}: {err}.")
        if op.action in ("complete", "cancel"):
            forzato = "completato" if op.action == "complete" else "annullato"
            if stato and stato != forzato:
                E(f"{where}: action {op.action} in conflitto con lo stato '{stato}'.")
            stato = forzato
        if create and stato is None:
            stato = d_stato
        if stato is not None:
            put("stato", stato, "stato")
            if kind != "deliverable" and (create or row.get("stato") != stato):
                if stato == "completato":
                    out["completato_il"] = _dt.date.today().isoformat()
                elif row.get("stato") == "completato":
                    out["completato_il"] = None

        if kind != "deliverable" and ("priority" in e or create):
            if e.get("priority") is not None:
                p, err = _priorita(e.get("priority"))
                if err:
                    E(f"{where}: {err}.")
                else:
                    put("priorita", p, "priorità")
            elif create:
                put("priorita", d_prio, "priorità")

        # persone (owner o assignee: sono la stessa colonna owner_id)
        chi = e.get("owner") if e.get("owner") is not None else e.get("assignee")
        if chi is not None:
            pid = persona(chi, f"{where}.owner")
            if pid:
                put("owner_id", str(pid), "owner", people.nome)
        elif create:
            if kind == "subtask":
                pid = ((op.parent.final.get("owner_id") if sub_eredita and op.parent else None)
                       or sub_default or d_owner)
            else:
                pid = d_owner
            put("owner_id", str(pid) if pid else None, "owner", people.nome)
        if "supervisor" in e:
            pid = persona(e.get("supervisor"), f"{where}.supervisor", allow_none=True)
            if pid or _norm(e.get("supervisor")) in ("none", "nobody", "nessuno", ""):
                put("supervisor_id", str(pid) if pid else None, "supervisor", people.nome)
        elif create:
            sup = d_sup
            if kind == "subtask" and op.parent:
                sup = op.parent.final.get("supervisor_id") or d_sup
            put("supervisor_id", str(sup) if sup else None, "supervisor", people.nome)

        if "due" in e:
            iso, err = _data(e.get("due"))
            if err:
                E(f"{where}: {err}.")
            else:
                put("scadenza", iso, "scadenza", _fmt_data)

        if kind != "deliverable" and "estimate_hours" in e:
            ore, err = _ore(e.get("estimate_hours"))
            if err:
                E(f"{where}: {err}.")
            else:
                put("ore_stimate", ore, "ore stimate")

        if "description" in e and "description_append" in e:
            E(f"{where}: indica description oppure description_append, non entrambi.")
        elif "description" in e:
            put("descrizione", str(e.get("description") or "").strip() or None,
                "descrizione",
                lambda v: (str(v)[:40] + "…") if v and len(str(v)) > 40 else (v or "—"))
        elif e.get("description_append"):
            add = str(e["description_append"]).strip()
            old = (row.get("descrizione") or "").rstrip()
            out["descrizione"] = f"{old}\n\n{add}" if old else add
            if not create:
                ch.append(("descrizione", "", f"+ {add[:40]}{'…' if len(add) > 40 else ''}"))

        if "gantt" in e:
            g = e.get("gantt")
            if g in (None, "", "none", "nessuno"):
                put("gantt_voce_id", None, "gantt")
            else:
                gid = gantt_codici.get(str(g).strip().casefold())
                if gid is None:
                    E(f"{where}: voce Gantt '{g}' inesistente in questa iniziativa.")
                else:
                    op.gantt_code = str(g).strip()
                    put("gantt_voce_id", str(gid), "gantt", lambda v: op.gantt_code if v else "—")

        op.fields.update(out)

    # ── visita ───────────────────────────────────────────────────────────────
    delivs = data.get("deliverables")
    if not isinstance(delivs, list) or not delivs:
        E("'deliverables' deve essere una lista non vuota.")
        return piano

    def label(base: str, e: Any) -> str:
        if not isinstance(e, dict):
            return base
        e = _canon(e, _ALIAS_CHIAVI)
        nome = e.get("title") or e.get("match_title") or e.get("from") or e.get("ref")
        return base + (f" '{nome}'" if nome else "")

    for i, de in enumerate(delivs):
        w = label(f"deliverables[{i + 1}]", de)
        de = _canon(de, _ALIAS_CHIAVI)
        dop = entry_op("deliverable", de, w, None)
        if dop is None:
            continue
        if not dop.loose:
            campi(dop, de, w)
            if dop.action == "create":
                dop.fields["iniziativa_id"] = str(iid)
        piano.ops.append(dop)
        tasks = de.get("tasks") or []
        if not isinstance(tasks, list):
            E(f"{w}: 'tasks' deve essere una lista.")
            continue
        for j, te in enumerate(tasks):
            tw = label(f"{w} › tasks[{j + 1}]", te)
            te = _canon(te, _ALIAS_CHIAVI)
            top = entry_op("task", te, tw, dop)
            if top is None:
                continue
            campi(top, te, tw)
            if top.action in ("create", "move"):
                top.fields["iniziativa_id"] = str(iid)
            if top.action == "move":
                top.changes.insert(0, ("spostato da", _dove(top.row, ds), ""))
            piano.ops.append(top)
            subs = te.get("subtasks") or []
            if not isinstance(subs, list):
                E(f"{tw}: 'subtasks' deve essere una lista.")
                continue
            for k, se in enumerate(subs):
                sw = label(f"{tw} › subtasks[{k + 1}]", se)
                se = _canon(se, _ALIAS_CHIAVI)
                sop = entry_op("subtask", se, sw, top)
                if sop is None:
                    continue
                campi(sop, se, sw)
                if sop.action in ("create", "move"):
                    sop.fields["iniziativa_id"] = str(iid)
                if sop.action == "move":
                    sop.changes.insert(0, ("spostato da", ref_breve(sop.row["parent_task_id"]), ""))
                piano.ops.append(sop)

    _verifica_chiusure(piano, snap)
    if piano.ok and not piano.changes():
        W("Niente da cambiare: ogni voce è keep o già aggiornata.")
    for op in piano.ops:
        if op.kind == "task" and op.action == "create":
            for r in ts:
                if not r.get("archiviato") and similarity(r.get("titolo"), op.title) >= DUP_MATCH \
                        and str(r.get("deliverable_id")) != str((op.parent.row or {}).get("id")):
                    W(f"{op.label}: esiste già un task con questo titolo "
                      f"({ref_breve(r['id'])}, in un altro deliverable).")
                    break
    return piano


def _uguali(a: Any, b: Any) -> bool:
    """Confronto tollerante fra valore a DB e valore del file (UUID/str,
    Decimal/float, date/iso)."""
    vuoto = (None, "")
    if a in vuoto or b in vuoto:
        return a in vuoto and b in vuoto
    if isinstance(a, (int, float)) or isinstance(b, (int, float)) or \
            type(a).__name__ == "Decimal" or type(b).__name__ == "Decimal":
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            pass
    return str(a) == str(b)


def _dove(task_row: dict, ds: list[dict]) -> str:
    did = task_row.get("deliverable_id")
    if not did:
        return "0 (senza deliverable)"
    d = next((x for x in ds if str(x["id"]) == str(did)), None)
    return f"{ref_breve(did)} {d.get('titolo') if d else ''}".strip()


def _verifica_chiusure(piano: Piano, snap: dict) -> None:
    """Un deliverable non si completa né si annulla finché uno dei suoi task o
    subtask resta aperto — dopo l'import. Completare un task con subtask aperti
    è solo un avviso (l'app lo consente)."""
    top_ops = {str(o.row["id"]): o for o in piano.ops if o.kind == "task" and o.row}
    sub_ops = {str(o.row["id"]): o for o in piano.ops if o.kind == "subtask" and o.row}
    tutti = snap.get("tasks", [])

    tasks = []  # (ident deliverable, ident task, stato finale, titolo)
    for t in tutti:
        if t.get("parent_task_id") or t.get("archiviato") or str(t["id"]) in top_ops:
            continue
        d = ("id", str(t["deliverable_id"])) if t.get("deliverable_id") else ("loose",)
        tasks.append((d, ("id", str(t["id"])), t.get("stato") or "da_fare", t.get("titolo")))
    for o in piano.ops:
        if o.kind == "task":
            tasks.append((o.parent.ident, o.ident, o.final.get("stato") or "da_fare", o.title))
    subs = []  # (ident task, stato finale, titolo)
    for s in tutti:
        if not s.get("parent_task_id") or s.get("archiviato") or str(s["id"]) in sub_ops:
            continue
        subs.append((("id", str(s["parent_task_id"])), s.get("stato") or "da_fare",
                     s.get("titolo")))
    for o in piano.ops:
        if o.kind == "subtask":
            subs.append((o.parent.ident, o.final.get("stato") or "da_fare", o.title))

    for o in piano.ops:
        if o.kind == "deliverable" and not o.loose \
                and o.final.get("stato") in CHIUSI \
                and (o.row or {}).get("stato") != o.final.get("stato"):
            miei = [t for t in tasks if t[0] == o.ident]
            t_ids = {t[1] for t in miei}
            aperti_t = [t[3] for t in miei if t[2] not in CHIUSI]
            aperti_s = [s[2] for s in subs if s[0] in t_ids and s[1] not in CHIUSI]
            if aperti_t or aperti_s:
                nomi = ", ".join((aperti_t + aperti_s)[:4]) + (
                    "…" if len(aperti_t + aperti_s) > 4 else "")
                verbo = "completare" if o.final.get("stato") == "completato" else "annullare"
                piano.errors.append(
                    f"{o.label}: impossibile {verbo} {o.ref} — dopo l'import restano "
                    f"aperti {len(aperti_t)} task e {len(aperti_s)} subtask ({nomi}). "
                    "Completali o annullali nello stesso file.")
        if o.kind == "task" and o.final.get("stato") == "completato" \
                and (o.row or {}).get("stato") != "completato":
            aperti_s = [s[2] for s in subs if s[0] == o.ident and s[1] not in CHIUSI]
            if aperti_s:
                piano.warnings.append(
                    f"{o.label}: completato con {len(aperti_s)} subtask aperti.")


# ── anteprima ─────────────────────────────────────────────────────────────────

ETICHETTA_AZIONE = {"create": "＋ crea", "update": "✎ aggiorna", "move": "→ sposta",
                    "complete": "✓ completa", "cancel": "✕ annulla", "keep": "· mantieni"}


def righe_anteprima(piano: Piano, persone: Persone) -> list[dict]:
    rows = []
    for o in piano.ops:
        if o.loose:
            rows.append({"Ref": "0", "Azione": "· mantieni",
                         "Elemento": "Task senza deliverable", "Modifiche": ""})
            continue
        rientro = {"deliverable": "", "task": "  ", "subtask": "      › "}[o.kind]
        f = o.final
        if o.action == "create":
            bits = [f.get("stato") or "", persone.nome(f.get("owner_id"))]
            if f.get("supervisor_id"):
                bits.append("sup " + persone.nome(f.get("supervisor_id")))
            if f.get("scadenza"):
                bits.append("scad. " + _fmt_data(f.get("scadenza")))
            if o.kind == "deliverable" and f.get("tipo"):
                bits.insert(0, f.get("tipo"))
            if o.kind != "deliverable" and f.get("priorita"):
                bits.append(f.get("priorita"))
            if f.get("ore_stimate"):
                bits.append(f"{f['ore_stimate']} h")
            if o.gantt_code:
                bits.append(f"Gantt {o.gantt_code}")
            modifiche = " · ".join(b for b in bits if b)
        else:
            modifiche = "; ".join(f"{lab}: {a} → {b}" if a and b else f"{lab} {a or b}"
                                  for lab, a, b in o.changes)
        rows.append({
            "Ref": o.ref,
            "Azione": ETICHETTA_AZIONE.get(o.action, o.action),
            "Elemento": rientro + (o.title or ""),
            "Modifiche": modifiche,
        })
    return rows


# ── guida e prompt ────────────────────────────────────────────────────────────

GUIDA_MD = """
**Come funziona l'import**

1. **Prepara il contenuto.** Copia il prompt qui sotto in un LLM (Claude,
   ChatGPT, Gemini…), aggiungi in fondo cosa vuoi organizzare — appunti di una
   riunione, una e-mail, un piano di lavoro — e chiedi lo YAML. Oppure scrivilo
   a mano.
2. **Incollalo** (YAML o JSON) e premi **Verifica**. Non viene scritto nulla.
3. **Leggi l'anteprima.** Ogni riga mostra l'azione e cosa cambia. I nomi sono
   risolti sull'anagrafica (*Mario* → *Mario Rossi*). Qualsiasi errore — nome
   ambiguo, ref che non corrisponde al titolo, duplicato — rende il file
   invalido: correggilo e verifica di nuovo.
4. **Importa.** Tutto in un'unica transazione: o entra tutto o niente.

**Azioni:** `create`, `update` (solo i campi indicati), `move` (con `ref`),
`complete`, `cancel`, `keep` (nessuna modifica: serve a raggiungere i task
interni). `description_append` accoda alla descrizione, `description` la
sostituisce. Niente viene cancellato: `cancel` porta lo stato ad *annullato*.
Lo stesso formato di MAIC tasks: chiavi in inglese o in italiano.
"""

SCHEMA_YAML = """schema: agest-import/v1
project: {code: <acronimo>, name: <titolo>}   # deve essere QUESTA iniziativa
defaults:                         # facoltativo; vale per gli elementi creati
  supervisor: <nome>              # oppure none
  status: da_fare                 # da_fare | in_corso | bloccato | completato | annullato
  priority: media                 # urgente | alta | media | bassa | nessuna
  subtask_assignee: inherit       # inherit (owner del task) oppure un nome
  owner: <nome>                   # owner quando non indicato (default: chi importa)
deliverables:
  - action: create|update|complete|cancel|keep
    ref: "#1a2b3c4d"              # solo deliverable esistenti (ref del prompt)
    match_title: <titolo attuale> # obbligatorio per gli esistenti: conferma il ref
    title: <nuovo titolo>
    type: prototipo|report|paper|altro
    status: <stato>
    owner: <nome>
    supervisor: <nome>|none
    due: AAAA-MM-GG
    gantt: <codice voce Gantt, es. T2.1>   # facoltativo
    description: <testo>          # sostituisce | description_append: <testo> accoda
    tasks:
      - action: create|update|move|complete|cancel|keep
        ref: "#5e6f7a8b"          # task esistente, sotto QUESTO deliverable
        match_title: <titolo attuale>
        title, priority, status, owner, supervisor, due, estimate_hours, gantt,
        description | description_append
        subtasks:
          - action: create|update|move|complete|cancel|keep   # default create
            ref, match_title, title, status, owner, supervisor, due, estimate_hours
  # task senza deliverable: una voce  {action: keep, ref: "0", tasks: [...]}"""


def costruisci_prompt(iniziativa: dict, snap: dict, persone: list[dict],
                      gantt: list[dict] | None = None) -> str:
    """Il prompt da incollare in un LLM: istruzioni, schema, valori ammessi,
    team e stato attuale dell'iniziativa (ref + titoli)."""
    acr = iniziativa.get("acronimo") or iniziativa.get("codice") or ""
    tit = iniziativa.get("titolo") or ""
    pp = Persone(persone)
    ds = [d for d in snap.get("deliverables", []) if not d.get("archiviato")]
    tutti = [t for t in snap.get("tasks", []) if not t.get("archiviato")]
    ts = [t for t in tutti if not t.get("parent_task_id")]
    ss = [t for t in tutti if t.get("parent_task_id")]

    def riga(r: dict) -> str:
        bits = [r.get("stato") or "da_fare", f"owner: {pp.nome(r.get('owner_id'))}"]
        if r.get("scadenza"):
            bits.append(f"scad. {str(r['scadenza'])[:10]}")
        return f"{ref_breve(r['id'])}  \"{r.get('titolo')}\"  ({', '.join(bits)})"

    def blocco_task(t: dict, ind: str) -> list[str]:
        out = [ind + riga(t)]
        for s in [s for s in ss if str(s.get("parent_task_id")) == str(t["id"])]:
            out.append(ind + "    " + riga(s))
        return out

    stato = []
    for d in ds:
        stato.append(riga(d) + f"  [tipo: {d.get('tipo') or '—'}]")
        for t in [t for t in ts if str(t.get("deliverable_id")) == str(d["id"])]:
            stato += blocco_task(t, "    ")
    sciolti = [t for t in ts if not t.get("deliverable_id")]
    if sciolti:
        stato.append("0  (task senza deliverable)")
        for t in sciolti:
            stato += blocco_task(t, "    ")
    team = ", ".join(sorted(Persone._nome(p) for p in persone))
    g_txt = ""
    if gantt:
        g_txt = "\nGANTT DELL'INIZIATIVA (codici utilizzabili nel campo gantt)\n" + "\n".join(
            f"{g.get('codice')}  \"{g.get('titolo')}\"  ({g.get('tipo')}, "
            f"{_fmt_data(g.get('data_inizio'))} → {_fmt_data(g.get('data_fine'))})"
            for g in gantt) + "\n"
    ref_proj = acr or tit

    return f"""Organizzi il lavoro di un progetto ANTECNICA in deliverable, task e subtask per il gestionale ANTECNICA.
Rispondi con UN SOLO documento YAML conforme allo schema seguente, e nient'altro (niente commenti né spiegazioni).

REGOLE
- Tutto appartiene all'iniziativa {ref_proj} ({tit}): scrivi project: {{code: {ref_proj}, name: {tit}}}.
- Azioni: create, update (solo i campi indicati), move (con ref), complete, cancel, keep (nessuna modifica; serve a raggiungere i task dentro un deliverable esistente).
- Elementi esistenti: indica ref (il loro #codice, es. #1a2b3c4d, copiato dallo stato qui sotto) E match_title (il titolo attuale). Mai inventare ref.
- Elementi nuovi: action create, senza ref.
- Non creare un elemento che esiste già: aggiornalo o mantienilo. Una sola voce per elemento esistente.
- Un task elencato sotto un deliverable deve trovarsi già lì; per portarlo da un altro deliverable usa action: move, ref: <il suo #codice>.
- I task senza deliverable vanno in una voce {{action: keep, ref: "0", tasks: [...]}}.
- description_append accoda alla descrizione; description la sostituisce.
- I defaults (supervisor, status, priority) valgono per gli elementi creati; i subtask senza owner ereditano quello del task.
- Mai cancellare: per eliminare un elemento usa cancel.
- Un deliverable si completa solo se tutti i suoi task e subtask risultano completati o annullati.
- Date: AAAA-MM-GG. Persone: usa i nomi del team (nome e cognome è la scelta più sicura).
- Stato: da_fare | in_corso | bloccato | completato | annullato. Priorità: urgente | alta | media | bassa | nessuna.
- Tipi di deliverable: prototipo | report | paper | altro.

SCHEMA
{SCHEMA_YAML}

ESEMPIO
schema: agest-import/v1
project: {{code: {ref_proj}, name: {tit}}}
defaults: {{supervisor: <persona del team>, status: da_fare, priority: media, subtask_assignee: inherit}}
deliverables:
  - action: create
    title: Prototipo dimostratore
    type: prototipo
    owner: <persona del team>
    due: 2027-03-31
    tasks:
      - title: Progetto della rete di alimentazione
        owner: <persona del team>
        due: 2027-01-15
        estimate_hours: 40
        subtasks:
          - title: Simulazione EM della transizione
  - action: keep
    ref: "#1a2b3c4d"
    match_title: <titolo attuale di #1a2b3c4d>
    tasks:
      - action: update
        ref: "#5e6f7a8b"
        match_title: <titolo attuale di #5e6f7a8b>
        status: in_corso
        description_append: Misure programmate la prossima settimana.

TEAM
{team}
{g_txt}
STATO ATTUALE DELL'INIZIATIVA {ref_proj}  (#ref  "titolo"  (stato, persone, scadenza))
{chr(10).join(stato) if stato else '(iniziativa vuota)'}

LA MIA RICHIESTA
<descrivi qui cosa aggiungere o cambiare, oppure incolla gli appunti / il piano di lavoro>
"""
