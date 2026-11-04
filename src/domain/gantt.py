"""Cronoprogramma (Gantt) di progetto — logica pura, condivisa con MAIC tasks.

Il Gantt è il PIANO (WP, task, deliverable, milestone con date o mesi di
progetto M1..Mn, come nelle proposte europee/PNRR); i task operativi dell'app
sono l'ESECUZIONE. I due si collegano: un task (o deliverable) può puntare a
una voce di Gantt, e il Gantt mostra l'avanzamento reale calcolato dai task
collegati (completati/totali, ritardi, slittamenti oltre la fine prevista).

Formati di import:
  * Excel (.xlsx) o CSV, oppure righe copiate da Excel e incollate (TSV);
    intestazioni riconosciute in italiano o inglese (codice/code/WBS,
    titolo/name, tipo/type, inizio/start, fine/finish, mese inizio/start
    month, mese fine/end month, durata/duration, responsabile/lead, padre/parent);
  * MS Project XML (File → Salva con nome → XML), anche da ProjectLibre/
    GanttProject esportati in formato MS Project.

Stesso file (a parte i messaggi) in `maic-tasks/utils/gantt.py`: tenerli
allineati.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

KINDS = ("wp", "task", "deliverable", "milestone")
KIND_LABEL = {"wp": "WP", "task": "Task", "deliverable": "Deliverable",
              "milestone": "Milestone"}

MSG = {
    "no_rows": "Nessuna riga riconosciuta: servono almeno le colonne codice e titolo.",
    "no_title_col": "Colonna del titolo non trovata (titolo / name / attività).",
    "dup": "codice {code} ripetuto (righe {a} e {b}): i codici devono essere univoci.",
    "bad_date": "riga {row} ({code}): data '{v}' non valida.",
    "bad_month": "riga {row} ({code}): mese '{v}' non valido (usa 1, 2… o M1, M2…).",
    "end_before": "{code}: la fine ({end}) precede l'inizio ({start}).",
    "no_parent": "{code}: padre '{p}' non presente nel file: la voce resta senza padre.",
    "no_timing": "{code}: nessuna data né mese: comparirà senza barra.",
    "months_no_start": ("Il file usa i mesi di progetto (M1…) ma l'iniziativa non ha "
                        "data di inizio: impostala per calcolare le date."),
    "xml_bad": "XML non leggibile: {e}.",
    "xml_not_project": "Il file XML non sembra un progetto MS Project (manca <Tasks>).",
}


# ── tipi ──────────────────────────────────────────────────────────────────────

@dataclass
class GanttRow:
    code: str
    title: str
    kind: str = "task"
    parent_code: str | None = None
    start: _dt.date | None = None
    end: _dt.date | None = None
    start_month: int | None = None
    end_month: int | None = None
    lead: str | None = None
    order: int = 0
    line: int = 0  # riga del file (per i messaggi)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "code", "title", "kind", "parent_code", "start", "end", "start_month",
            "end_month", "lead", "order")}


@dataclass
class ParseResult:
    rows: list[GanttRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and bool(self.rows)


# ── normalizzazione ───────────────────────────────────────────────────────────

def _norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s if s is not None else ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w]+", " ", s.casefold())
    return " ".join(s.split())


_COLS = {
    "code": ["code", "codice", "id", "wbs", "ref", "outline number", "numero",
             "n", "nr", "task id", "cod"],
    "title": ["title", "titolo", "name", "nome", "task name", "nome attivita",
              "attivita", "activity", "task", "descrizione", "description",
              "denominazione", "work package title"],
    "kind": ["type", "tipo", "kind", "categoria", "livello", "level"],
    "start": ["start", "inizio", "start date", "data inizio", "begin", "dal",
              "from", "data di inizio", "inizio previsto"],
    "end": ["end", "fine", "finish", "end date", "data fine", "al", "to", "due",
            "scadenza", "data di fine", "fine prevista"],
    "start_month": ["start month", "mese inizio", "month start", "m start",
                    "sm", "from month", "mese di inizio", "inizio mese",
                    "start m", "inizio m"],
    "end_month": ["end month", "mese fine", "month end", "m end", "em",
                  "to month", "mese di fine", "fine mese", "end m", "fine m",
                  "delivery month", "mese consegna", "due month"],
    "duration": ["duration", "durata", "durata mesi", "duration months",
                 "months", "mesi"],
    "lead": ["lead", "responsabile", "owner", "leader", "partner",
             "lead partner", "resp", "beneficiario", "lead beneficiary"],
    "parent": ["parent", "padre", "wp", "work package", "parent code"],
}


def _match_columns(header: list[Any]) -> dict[str, int]:
    """{campo: indice colonna} riconosciuti nell'intestazione."""
    out: dict[str, int] = {}
    normed = [_norm(h) for h in header]
    for fld, aliases in _COLS.items():
        for i, h in enumerate(normed):
            if h and h in aliases and i not in out.values():
                out[fld] = i
                break
    # «WP» come colonna padre solo se c'è già un codice diverso
    if "parent" in out and "code" not in out:
        out["code"] = out.pop("parent")
    return out


def normalize_code(v: Any) -> str:
    s = str(v if v is not None else "").strip()
    if re.fullmatch(r"\d+\.0", s):  # 3.0 letto da Excel come float
        s = s[:-2]
    s = re.sub(r"\s+", "", s)
    return s.upper()


def infer_kind(code: str, title: str = "", explicit: Any = None) -> str:
    if explicit not in (None, ""):
        e = _norm(explicit)
        for k, words in {
            "wp": ("wp", "work package", "workpackage", "pacchetto"),
            "deliverable": ("deliverable", "d", "del", "prodotto", "rapporto"),
            "milestone": ("milestone", "ms", "m", "traguardo", "pietra miliare"),
            "task": ("task", "t", "attivita", "activity", "sottoattivita", "subtask"),
        }.items():
            if e in words or e.startswith(words[0]):
                return k
    c = code.upper()
    if re.match(r"^WP\d", c):
        return "wp"
    if re.match(r"^(D|DEL)\d", c):
        return "deliverable"
    if re.match(r"^(MS|M)\d", c):
        return "milestone"
    if re.match(r"^(T|A|TASK)\d", c):
        return "task"
    t = _norm(title)
    if t.startswith("work package") or t.startswith("wp "):
        return "wp"
    if t.startswith("milestone"):
        return "milestone"
    return "task"


def infer_parent(code: str, kind: str, known: set[str]) -> str | None:
    """Padre implicito dal codice: T1.2 / D1.3 → WP1; 1.2.3 → 1.2; T1.2.1 → T1.2."""
    c = code.upper()
    m = re.match(r"^(?:T|A|TASK|D|DEL|MS|M)(\d+)((?:\.\d+)*)$", c)
    if m and kind != "wp":
        if m.group(2) and m.group(2).count(".") >= 2:  # T1.2.1 → T1.2
            pref = re.match(r"^[A-Z]+", c).group(0)
            cand = pref + m.group(1) + m.group(2).rsplit(".", 1)[0]
            if cand in known:
                return cand
        if m.group(2):
            wp = f"WP{m.group(1)}"
            if wp in known:
                return wp
        return None
    if re.fullmatch(r"\d+(\.\d+)+", c):
        cand = c.rsplit(".", 1)[0]
        return cand if cand in known else None
    return None


def parse_month(v: Any) -> int | None:
    """3, '3', 'M3', 'm03', 3.0 → 3; vuoto → None; altro → ValueError."""
    if v is None or (isinstance(v, float) and v != v):
        return None
    s = str(v).strip().upper()
    if not s:
        return None
    m = re.fullmatch(r"M?\s*0*(\d+)(?:\.0+)?", s)
    if not m or int(m.group(1)) < 1:
        raise ValueError(s)
    return int(m.group(1))


def parse_date(v: Any) -> _dt.date | None:
    if v is None or (isinstance(v, float) and v != v):
        return None
    if hasattr(v, "to_pydatetime"):  # pandas Timestamp
        if str(v) == "NaT":
            return None
        v = v.to_pydatetime()
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    s = str(v).strip()
    if not s or s.lower() in ("nat", "nan", "none", "-", "—"):
        return None
    s = s.split("T")[0].split(" ")[0]
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return _dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ValueError(s)


def add_months(d: _dt.date, n: int) -> _dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28, 31, 30, 31,
            30, 31, 31, 30, 31, 30, 31][m - 1]
    return _dt.date(y, m, min(d.day, last))


def month_start(project_start: _dt.date, m: int) -> _dt.date:
    """Primo giorno del mese di progetto Mm (M1 = data di inizio)."""
    return add_months(project_start, m - 1)


def month_end(project_start: _dt.date, m: int) -> _dt.date:
    """Ultimo giorno del mese di progetto Mm."""
    return add_months(project_start, m) - _dt.timedelta(days=1)


def month_of(project_start: _dt.date, d: _dt.date) -> int:
    """Mese di progetto (1-based) che contiene la data `d`."""
    m = (d.year - project_start.year) * 12 + (d.month - project_start.month) + 1
    if d.day < project_start.day:
        m -= 1
    return max(1, m)


# ── lettura tabelle ───────────────────────────────────────────────────────────

def read_table(rows: list[list[Any]]) -> ParseResult:
    """Righe di una tabella (la prima riga utile è l'intestazione)."""
    res = ParseResult()
    hdr_i, cols = None, {}
    for i, r in enumerate(rows[:15]):  # l'intestazione può non essere la prima riga
        c = _match_columns(list(r))
        if "title" in c and len(c) >= 2:
            hdr_i, cols = i, c
            break
    if hdr_i is None:
        res.errors.append(MSG["no_title_col"])
        return res
    seen: dict[str, int] = {}
    auto = 0
    for n, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 2):
        r = list(r) + [None] * (max(cols.values()) + 1 - len(r))

        def cell(f: str) -> Any:
            return r[cols[f]] if f in cols else None

        title = str(cell("title") or "").strip()
        if not title or title.lower() == "nan":
            continue
        code = normalize_code(cell("code")) if "code" in cols else ""
        if not code or code == "NAN":
            auto += 1
            code = f"G{auto}"
        if code in seen:
            res.errors.append(MSG["dup"].format(code=code, a=seen[code], b=n))
            continue
        seen[code] = n
        row = GanttRow(code=code, title=title, line=n, order=len(res.rows))
        row.kind = infer_kind(code, title, cell("kind"))
        for f, attr in (("start", "start"), ("end", "end")):
            try:
                setattr(row, attr, parse_date(cell(f)))
            except ValueError as exc:
                res.errors.append(MSG["bad_date"].format(row=n, code=code, v=exc))
        for f, attr in (("start_month", "start_month"), ("end_month", "end_month")):
            try:
                setattr(row, attr, parse_month(cell(f)))
            except ValueError as exc:
                res.errors.append(MSG["bad_month"].format(row=n, code=code, v=exc))
        try:
            dur = parse_month(cell("duration"))
        except ValueError:
            dur = None
        if dur and row.start_month and not row.end_month:
            row.end_month = row.start_month + dur - 1
        if row.kind in ("milestone", "deliverable") and row.end_month and not row.start_month:
            row.start_month = row.end_month
        if row.kind in ("milestone", "deliverable") and row.start_month and not row.end_month:
            row.end_month = row.start_month
        lead = cell("lead")
        row.lead = str(lead).strip() if lead not in (None, "") and str(lead) != "nan" else None
        par = cell("parent")
        if par not in (None, "") and str(par) != "nan":
            p = normalize_code(par)
            row.parent_code = p if p != code else None
        res.rows.append(row)
    if not res.rows and not res.errors:
        res.errors.append(MSG["no_rows"])
    _link_parents(res)
    return res


def _link_parents(res: ParseResult) -> None:
    known = {r.code for r in res.rows}
    for r in res.rows:
        if r.parent_code and r.parent_code not in known:
            # «1» nella colonna WP → WP1
            if f"WP{r.parent_code}" in known:
                r.parent_code = f"WP{r.parent_code}"
            else:
                res.warnings.append(MSG["no_parent"].format(code=r.code, p=r.parent_code))
                r.parent_code = None
        if not r.parent_code:
            r.parent_code = infer_parent(r.code, r.kind, known)


def parse_text(text: str) -> ParseResult:
    """Testo incollato: TSV (copia da Excel), CSV con ; o ,."""
    text = (text or "").strip("\n")
    if not text.strip():
        return ParseResult(errors=[MSG["no_rows"]])
    sample = text[:2000]
    delim = "\t" if "\t" in sample else (";" if sample.count(";") > sample.count(",") else ",")
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    return read_table(rows)


def parse_xlsx(data: bytes, sheet: int | str = 0) -> ParseResult:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    return read_table(rows)


def sheet_names(data: bytes) -> list[str]:
    import openpyxl

    return openpyxl.load_workbook(io.BytesIO(data), read_only=True).sheetnames


def parse_msproject_xml(data: bytes) -> ParseResult:
    res = ParseResult()
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        res.errors.append(MSG["xml_bad"].format(e=exc))
        return res
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    tasks = root.find(f"{ns}Tasks")
    if tasks is None:
        res.errors.append(MSG["xml_not_project"])
        return res

    def txt(el: ET.Element, tag: str) -> str | None:
        x = el.find(f"{ns}{tag}")
        return x.text.strip() if x is not None and x.text else None

    by_outline: dict[str, str] = {}
    for el in tasks.findall(f"{ns}Task"):
        if txt(el, "UID") == "0" or txt(el, "IsNull") == "1":
            continue  # riga di riepilogo del progetto / vuota
        name = txt(el, "Name")
        if not name:
            continue
        outline = txt(el, "OutlineNumber") or txt(el, "WBS") or txt(el, "ID") or ""
        code = normalize_code(txt(el, "WBS") or outline)
        level = int(txt(el, "OutlineLevel") or 1)
        is_ms = txt(el, "Milestone") == "1"
        is_sum = txt(el, "Summary") == "1"
        kind = infer_kind(code, name)
        if kind == "task":
            kind = "milestone" if is_ms else ("wp" if is_sum and level == 1 else "task")
        r = GanttRow(code=code, title=name, kind=kind, order=len(res.rows),
                     line=len(res.rows) + 1)
        for tag, attr in (("Start", "start"), ("Finish", "end")):
            try:
                setattr(r, attr, parse_date(txt(el, tag)))
            except ValueError:
                pass
        if outline and "." in outline:
            r.parent_code = by_outline.get(outline.rsplit(".", 1)[0])
        by_outline[outline] = code
        res.rows.append(r)
    codes = [r.code for r in res.rows]
    for c in {c for c in codes if codes.count(c) > 1}:
        res.errors.append(MSG["dup"].format(code=c, a="?", b="?"))
    if not res.rows:
        res.errors.append(MSG["no_rows"])
    return res


def parse_file(name: str, data: bytes) -> ParseResult:
    n = (name or "").lower()
    if n.endswith(".xml"):
        return parse_msproject_xml(data)
    if n.endswith((".xlsx", ".xlsm")):
        return parse_xlsx(data)
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return parse_text(data.decode(enc))
        except UnicodeDecodeError:
            continue
    return ParseResult(errors=[MSG["no_rows"]])


# ── risoluzione date/mesi ─────────────────────────────────────────────────────

def resolve(res: ParseResult, project_start: _dt.date | None) -> ParseResult:
    """Completa date e mesi a vicenda (serve l'inizio del progetto), deriva il
    periodo delle WP dai figli e controlla la coerenza. Modifica `res`."""
    if project_start is None and any(r.start_month or r.end_month for r in res.rows) \
            and not all(r.start or r.end for r in res.rows):
        res.warnings.append(MSG["months_no_start"])
    for r in res.rows:
        if project_start:
            if r.start is None and r.start_month:
                r.start = month_start(project_start, r.start_month)
            if r.end is None and r.end_month:
                r.end = month_end(project_start, r.end_month)
            if r.start and r.start_month is None:
                r.start_month = month_of(project_start, r.start)
            if r.end and r.end_month is None:
                r.end_month = month_of(project_start, r.end)
        if r.kind in ("milestone", "deliverable"):
            if r.end and not r.start:
                r.start = r.end
            if r.start and not r.end:
                r.end = r.start
    # WP (e ogni padre) senza periodo: min/max dei figli
    children: dict[str, list[GanttRow]] = {}
    for r in res.rows:
        if r.parent_code:
            children.setdefault(r.parent_code, []).append(r)
    for r in res.rows:
        kids = children.get(r.code) or []
        if kids and not (r.start and r.end):
            starts = [k.start for k in kids if k.start]
            ends = [k.end for k in kids if k.end]
            r.start = r.start or (min(starts) if starts else None)
            r.end = r.end or (max(ends) if ends else None)
            if project_start:
                r.start_month = r.start_month or (month_of(project_start, r.start) if r.start else None)
                r.end_month = r.end_month or (month_of(project_start, r.end) if r.end else None)
    for r in res.rows:
        if r.start and r.end and r.end < r.start:
            res.errors.append(MSG["end_before"].format(code=r.code, start=r.start, end=r.end))
        elif r.start_month and r.end_month and r.end_month < r.start_month:
            res.errors.append(MSG["end_before"].format(code=r.code, start=f"M{r.start_month}",
                                                       end=f"M{r.end_month}"))
        if not (r.start or r.end or r.start_month or r.end_month):
            res.warnings.append(MSG["no_timing"].format(code=r.code))
    return res


# ── avanzamento ───────────────────────────────────────────────────────────────

CLOSED = ("completato", "annullato", "Completed", "Cancelled")
DONE = ("completato", "Completed")


def progress(items: list[dict], linked: list[dict], today: _dt.date | None = None) -> dict:
    """Avanzamento di ogni voce dai task collegati.

    items: [{id, parent_id, start, end}] (chiavi neutre)
    linked: [{gantt_id, status, due}] task collegati (non archiviati)
    → {id: {n, done, pct, late, slip}} — le voci padre aggregano i figli.
      late = finita la voce (oggi > end) con lavoro ancora aperto;
      slip = qualche task collegato scade dopo la fine della voce.
    """
    today = today or _dt.date.today()
    own: dict[Any, list[dict]] = {}
    for t in linked:
        own.setdefault(t.get("gantt_id"), []).append(t)
    kids: dict[Any, list[Any]] = {}
    for it in items:
        if it.get("parent_id"):
            kids.setdefault(it["parent_id"], []).append(it["id"])
    by_id = {it["id"]: it for it in items}
    memo: dict[Any, list[dict]] = {}

    def tasks_of(i: Any, stack: tuple = ()) -> list[dict]:
        if i in memo:
            return memo[i]
        if i in stack:  # ciclo di padri: non dovrebbe succedere
            return []
        out = list(own.get(i, []))
        for k in kids.get(i, []):
            out += tasks_of(k, stack + (i,))
        memo[i] = out
        return out

    out = {}
    for i, it in by_id.items():
        ts = [t for t in tasks_of(i) if t.get("status") != "annullato" and t.get("status") != "Cancelled"]
        n = len(ts)
        done = sum(1 for t in ts if t.get("status") in DONE)
        end = it.get("end")
        late = bool(end and today > end and n and done < n)
        slip = bool(end and any(t.get("due") and t["due"] > end and t.get("status") not in CLOSED
                                for t in ts))
        out[i] = {"n": n, "done": done, "pct": (done / n) if n else None,
                  "late": late, "slip": slip}
    return out
