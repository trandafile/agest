"""Portfolio pluriennale — regole pure (testabili senza DB).

Copre la vista «una riga per progetto/proposta, estesa per anno»:
  * distribuzione pro-rata di ore/importi sugli anni coperti da un intervallo;
  * carico ore per persona e anno (piano esplicito `piano_ore_anno` oppure
    pro-rata di `assegnazione.ore_pianificate`);
  * disponibilità annua di una persona (monte ore × frazione di contratto);
  * saturazione per persona/anno con distinzione fra ore IMPEGNATE (progetti
    attivi) e POTENZIALI (proposte, pesate per probabilità);
  * ricavi attesi per anno dal portafoglio (progetti + pipeline pesata).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

STATI_PROPOSTA_VIVA = ("bozza", "inviata")
CENT = Decimal("0.01")
DEC1 = Decimal("0.1")


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def giorni_per_anno(inizio: date | None, fine: date | None) -> dict[int, int]:
    """Giorni (estremi inclusi) dell'intervallo che cadono in ciascun anno.

    Intervallo incompleto o invertito -> {}.
    """
    if not inizio or not fine or fine < inizio:
        return {}
    out: dict[int, int] = {}
    for anno in range(inizio.year, fine.year + 1):
        a = max(inizio, date(anno, 1, 1))
        b = min(fine, date(anno, 12, 31))
        out[anno] = (b - a).days + 1
    return out


def quota_per_anno(
    inizio: date | None, fine: date | None, totale, decimali: Decimal = CENT
) -> dict[int, Decimal]:
    """Pro-rata di `totale` sugli anni dell'intervallo, in base ai giorni.

    L'ultimo anno assorbe l'arrotondamento, così la somma torna esattamente
    `totale`. Senza date valide -> {}.
    """
    giorni = giorni_per_anno(inizio, fine)
    tot = _dec(totale)
    if not giorni or tot == 0:
        return {a: Decimal("0") for a in giorni}
    n = sum(giorni.values())
    out: dict[int, Decimal] = {}
    residuo = tot
    anni = sorted(giorni)
    for anno in anni[:-1]:
        q = (tot * giorni[anno] / n).quantize(decimali, rounding=ROUND_HALF_UP)
        out[anno] = q
        residuo -= q
    out[anni[-1]] = residuo.quantize(decimali, rounding=ROUND_HALF_UP)
    return out


def quota_per_mese(
    inizio: date | None, fine: date | None, totale
) -> dict[tuple[int, int], Decimal]:
    """Pro-rata di `totale` sui mesi (anno, mese) dell'intervallo, per giorni."""
    if not inizio or not fine or fine < inizio:
        return {}
    tot = _dec(totale)
    giorni: dict[tuple[int, int], int] = {}
    d = inizio
    while d <= fine:
        k = (d.year, d.month)
        giorni[k] = giorni.get(k, 0) + 1
        d += timedelta(days=1)
    n = sum(giorni.values())
    out: dict[tuple[int, int], Decimal] = {}
    residuo = tot
    chiavi = sorted(giorni)
    for k in chiavi[:-1]:
        q = (tot * giorni[k] / n).quantize(CENT, rounding=ROUND_HALF_UP)
        out[k] = q
        residuo -= q
    out[chiavi[-1]] = residuo.quantize(CENT, rounding=ROUND_HALF_UP)
    return out


@dataclass(frozen=True)
class RigaCarico:
    """Ore di una persona su un'iniziativa in un anno."""

    persona_id: str
    nome: str
    iniziativa_id: str
    etichetta: str
    tipo: str  # 'proposta' | 'progetto'
    stato: str
    probabilita: Decimal  # 1 per i progetti
    anno: int
    ore: Decimal
    esplicito: bool  # True se da piano_ore_anno, False se pro-rata


def carico_per_anno(
    assegnazioni: list[dict],
    piani: dict[tuple[str, int], Decimal] | None = None,
) -> list[RigaCarico]:
    """Ore per persona/iniziativa/anno.

    `assegnazioni`: [{assegnazione_id, persona_id, nome, iniziativa_id,
    etichetta, tipo, stato, probabilita, data_inizio, data_fine,
    ore_pianificate}]. `piani`: {(assegnazione_id, anno): ore} da
    `piano_ore_anno`; quando presenti per un'assegnazione, vincono sul
    pro-rata.
    """
    piani = piani or {}
    out: list[RigaCarico] = []
    for a in assegnazioni:
        aid = str(a["assegnazione_id"])
        tipo = a.get("tipo") or "progetto"
        prob = (_dec(a.get("probabilita")) if tipo == "proposta" else Decimal("1")) or (
            Decimal("0") if tipo == "proposta" else Decimal("1")
        )
        espliciti = {an: ore for (k, an), ore in piani.items() if k == aid}
        if espliciti:
            quote = {an: _dec(o) for an, o in espliciti.items()}
            esplicito = True
        else:
            quote = quota_per_anno(
                a.get("data_inizio"), a.get("data_fine"), a.get("ore_pianificate"), DEC1
            )
            esplicito = False
        for anno, ore in sorted(quote.items()):
            if ore == 0:
                continue
            out.append(
                RigaCarico(
                    persona_id=str(a["persona_id"]),
                    nome=a.get("nome") or "",
                    iniziativa_id=str(a["iniziativa_id"]),
                    etichetta=a.get("etichetta") or "",
                    tipo=tipo,
                    stato=a.get("stato") or "",
                    probabilita=prob,
                    anno=anno,
                    ore=ore,
                    esplicito=esplicito,
                )
            )
    return out


def disponibilita_anno(
    monte_ore_annuo,
    anno: int,
    contratto_inizio: date | None = None,
    contratto_fine: date | None = None,
) -> Decimal:
    """Ore disponibili nell'anno = monte ore × frazione dell'anno coperta dal
    contratto (nessuna data = tutto l'anno)."""
    monte = _dec(monte_ore_annuo)
    if monte <= 0:
        return Decimal("0")
    a0, a1 = date(anno, 1, 1), date(anno, 12, 31)
    da = max(a0, contratto_inizio) if contratto_inizio else a0
    al = min(a1, contratto_fine) if contratto_fine else a1
    if al < da:
        return Decimal("0")
    giorni_anno = (a1 - a0).days + 1
    frazione = Decimal((al - da).days + 1) / Decimal(giorni_anno)
    return (monte * frazione).quantize(DEC1, rounding=ROUND_HALF_UP)


def tabella_saturazione(
    righe: list[RigaCarico],
    persone: list[dict],
    anni: list[int],
) -> list[dict]:
    """Per persona e anno: ore impegnate (progetti attivi), potenziali
    (proposte vive × probabilità), disponibili e saturazione %.

    `persone`: [{id, nome, monte_ore_annuo, contratto_data_inizio,
    contratto_data_fine}].
    """
    acc: dict[tuple[str, int], dict] = {}
    for r in righe:
        k = (r.persona_id, r.anno)
        cella = acc.setdefault(
            k, {"impegnate": Decimal("0"), "potenziali": Decimal("0")}
        )
        if r.tipo == "progetto" and r.stato == "attivo":
            cella["impegnate"] += r.ore
        elif r.tipo == "proposta" and r.stato in STATI_PROPOSTA_VIVA:
            cella["potenziali"] += (r.ore * r.probabilita).quantize(DEC1)
    out = []
    for p in persone:
        pid = str(p["id"])
        for anno in anni:
            cella = acc.get(
                (pid, anno), {"impegnate": Decimal("0"), "potenziali": Decimal("0")}
            )
            disp = disponibilita_anno(
                p.get("monte_ore_annuo"),
                anno,
                p.get("contratto_data_inizio"),
                p.get("contratto_data_fine"),
            )
            tot = cella["impegnate"] + cella["potenziali"]
            sat = (tot / disp * 100).quantize(Decimal("1")) if disp > 0 else None
            out.append(
                {
                    "persona_id": pid,
                    "nome": p.get("nome") or "",
                    "anno": anno,
                    "impegnate": cella["impegnate"],
                    "potenziali": cella["potenziali"],
                    "disponibili": disp,
                    "libere": disp - tot,
                    "saturazione": sat,
                    "sovrallocata": bool(disp > 0 and tot > disp),
                }
            )
    return out


def ricavi_per_anno(iniziative: list[dict], pesati: bool = True) -> list[dict]:
    """Importo atteso per iniziativa e anno (pro-rata sui giorni).

    `iniziative`: [{id, etichetta, tipo, stato, importo, probabilita,
    data_inizio, data_fine, tipo_ricavo, controparte}]. Le proposte vive sono
    pesate per probabilità se `pesati`; proposte rifiutate/approvate e
    progetti chiusi contano per intero solo se `stato` lo consente.
    """
    out = []
    for i in iniziative:
        tipo = i.get("tipo") or "progetto"
        stato = i.get("stato") or ""
        if tipo == "proposta" and stato not in STATI_PROPOSTA_VIVA:
            continue
        peso = Decimal("1")
        if tipo == "proposta" and pesati:
            peso = _dec(i.get("probabilita"))
        for anno, q in quota_per_anno(
            i.get("data_inizio"), i.get("data_fine"), i.get("importo")
        ).items():
            out.append(
                {
                    "iniziativa_id": str(i.get("id")),
                    "etichetta": i.get("etichetta") or "",
                    "tipo": tipo,
                    "stato": stato,
                    "tipo_ricavo": i.get("tipo_ricavo") or "agevolato",
                    "controparte": i.get("controparte") or "",
                    "anno": anno,
                    "importo": (q * peso).quantize(CENT),
                    "importo_pieno": q,
                    "probabilita": peso,
                }
            )
    return out


def anni_portfolio(iniziative: list[dict], oggi: date | None = None) -> list[int]:
    """Anni coperti dal portafoglio (min inizio .. max fine), sempre includendo
    l'anno corrente."""
    oggi = oggi or date.today()
    anni = {oggi.year}
    for i in iniziative:
        for d in (i.get("data_inizio"), i.get("data_fine")):
            if d:
                anni.add(d.year)
    return list(range(min(anni), max(anni) + 1))
