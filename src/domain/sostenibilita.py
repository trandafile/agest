"""Sostenibilità economica — regole pure (testabili senza DB).

Riferimenti: Piano strategico ANTECNICA 2026-2030 §6 «Indicatori di
sostenibilità economica» (backlog coverage, ricavi ricorrenti, concentrazione
clienti, quota ricavi da mercato, EBITDA margin, rapporto tariffa/costo pieno)
e i fogli di gestione oggi tenuti a mano («Disponibilità in cassa», «stima
utile e tasse», «Costo Personale»).

Contiene:
  * espansione delle spese periodiche nei mesi futuri;
  * costo del personale previsto per mese (tariffa vigente × monte ore/12);
  * entrate della pipeline (proposte vive) pro-rata e pesate;
  * proiezione di cassa multi-scenario (firmato / +pipeline pesata / +tutta);
  * KPI con soglie di allarme e target;
  * stima utile e tasse dell'esercizio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from src.domain.finanza import proiezione_cassa
from src.domain.portfolio import quota_per_mese
from src.domain.tariffe import tariffa_vigente

CENT = Decimal("0.01")

# Periodicità riconosciute (foglio «Spese periodiche»): etichetta -> mesi
PERIODICITA_MESI = {
    "mensile": 1,
    "mese": 1,
    "bimestrale": 2,
    "trimestrale": 3,
    "quadrimestrale": 4,
    "semestrale": 6,
    "annuale": 12,
    "annua": 12,
    "anno": 12,
}


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def mesi_periodicita(label: str | None) -> int | None:
    """'Mensile' -> 1, 'Trimestrale' -> 3, ... ; None se non riconosciuta."""
    if not label:
        return None
    s = str(label).strip().lower()
    for k, v in PERIODICITA_MESI.items():
        if s.startswith(k):
            return v
    return None


def _add_mesi(anno: int, mese: int, n: int) -> tuple[int, int]:
    m0 = anno * 12 + (mese - 1) + n
    return m0 // 12, m0 % 12 + 1


def espandi_spese_periodiche(
    spese: list[dict], mesi: list[tuple[int, int]]
) -> tuple[dict[tuple[int, int], Decimal], list[dict]]:
    """Proietta le spese ricorrenti sui mesi richiesti.

    `spese`: [{descrizione, importo, periodicita, dal, al}]. Ricorrenza a
    partire da `dal` (o dal primo mese richiesto) ogni k mesi fino ad `al`.
    Ritorna (uscite per mese, spese con periodicità NON riconosciuta).
    """
    out: dict[tuple[int, int], Decimal] = {}
    ignorate: list[dict] = []
    if not mesi:
        return out, ignorate
    primo, ultimo = mesi[0], mesi[-1]
    richiesti = set(mesi)
    for s in spese:
        k = mesi_periodicita(s.get("periodicita"))
        imp = _dec(s.get("importo"))
        if k is None or imp <= 0:
            ignorate.append(s)
            continue
        dal: date | None = s.get("dal")
        al: date | None = s.get("al")
        a, m = (dal.year, dal.month) if dal else primo
        # porta la prima occorrenza dentro/avanti fino al primo mese richiesto
        while (a, m) < primo:
            a, m = _add_mesi(a, m, k)
        while (a, m) <= ultimo:
            if al and (a, m) > (al.year, al.month):
                break
            if (a, m) in richiesti:
                out[(a, m)] = out.get((a, m), Decimal("0")) + imp
            a, m = _add_mesi(a, m, k)
    return out, ignorate


def costo_personale_mese(
    persone: list[dict], tariffe_by_persona: dict, anno: int, mese: int
) -> Decimal:
    """Costo del personale previsto nel mese = Σ tariffa vigente × monte ore/12
    per le persone attive il cui contratto copre il mese (date assenti =
    sempre in forza)."""
    riferimento = date(anno, mese, 15)
    tot = Decimal("0")
    for p in persone:
        if p.get("attivo") is False:
            continue
        da, al = p.get("contratto_data_inizio"), p.get("contratto_data_fine")
        if da and riferimento < date(da.year, da.month, 1):
            continue
        if al and riferimento > al:
            continue
        t = tariffa_vigente(tariffe_by_persona.get(str(p["id"]), []), riferimento)
        if t is None:
            continue
        monte = _dec(p.get("monte_ore_annuo") or 1720)
        tot += t.importo_orario * monte / 12
    return tot.quantize(CENT, rounding=ROUND_HALF_UP)


def entrate_pipeline_mensili(
    proposte: list[dict], mesi: list[tuple[int, int]], pesate: bool = True
) -> dict[tuple[int, int], Decimal]:
    """Entrate attese dalle proposte vive, pro-rata sui mesi e (se `pesate`)
    moltiplicate per la probabilità di successo.

    `proposte`: [{importo, probabilita, data_inizio, data_fine, stato}].
    """
    out: dict[tuple[int, int], Decimal] = {}
    richiesti = set(mesi)
    for p in proposte:
        if p.get("stato") not in ("bozza", "inviata"):
            continue
        peso = _dec(p.get("probabilita")) if pesate else Decimal("1")
        if peso <= 0:
            continue
        # pro-rata dell'importo GIÀ pesato: l'ultimo mese assorbe l'arrotondamento
        importo_pesato = (_dec(p.get("importo")) * peso).quantize(CENT)
        for k, q in quota_per_mese(
            p.get("data_inizio"), p.get("data_fine"), importo_pesato
        ).items():
            if k in richiesti:
                out[k] = out.get(k, Decimal("0")) + q
    return out


def _somma(*dizionari: dict) -> dict[tuple[int, int], Decimal]:
    out: dict[tuple[int, int], Decimal] = {}
    for d in dizionari:
        for k, v in d.items():
            out[k] = out.get(k, Decimal("0")) + _dec(v)
    return out


def proiezione_scenari(
    saldo_iniziale,
    mesi: list[tuple[int, int]],
    entrate_firmate: dict,
    uscite_programmate: dict,
    uscite_base: dict | Decimal,
    pipeline_pesata: dict,
    pipeline_intera: dict,
) -> dict[str, list[dict]]:
    """Tre scenari di cassa sullo stesso orizzonte.

    * `firmato`: solo contratti/documenti/milestone già certi;
    * `pesato`:  + proposte vive × probabilità;
    * `ottimista`: + proposte vive per intero.
    `uscite_base` è la spesa mensile strutturale (costi fissi, personale,
    spese periodiche): dict per mese oppure importo costante.
    """
    if isinstance(uscite_base, dict):
        uscite_tot = _somma(uscite_programmate, uscite_base)
        costante = Decimal("0")
    else:
        uscite_tot = dict(uscite_programmate)
        costante = _dec(uscite_base)
    saldo0 = _dec(saldo_iniziale)
    return {
        "firmato": proiezione_cassa(
            saldo0, mesi, entrate_firmate, uscite_tot, costante
        ),
        "pesato": proiezione_cassa(
            saldo0, mesi, _somma(entrate_firmate, pipeline_pesata), uscite_tot, costante
        ),
        "ottimista": proiezione_cassa(
            saldo0, mesi, _somma(entrate_firmate, pipeline_intera), uscite_tot, costante
        ),
    }


def primo_mese_negativo(righe: list[dict]) -> tuple[int, int] | None:
    for r in righe:
        if r["saldo"] < 0:
            return (r["anno"], r["mese"])
    return None


def saldo_minimo(righe: list[dict]) -> tuple[Decimal, tuple[int, int]] | None:
    if not righe:
        return None
    r = min(righe, key=lambda x: x["saldo"])
    return r["saldo"], (r["anno"], r["mese"])


def totali_per_anno(righe: list[dict]) -> list[dict]:
    """Aggrega una proiezione mensile per anno (entrate, uscite, saldo fine)."""
    acc: dict[int, dict] = {}
    for r in righe:
        a = acc.setdefault(
            r["anno"],
            {"anno": r["anno"], "entrate": Decimal("0"), "uscite": Decimal("0")},
        )
        a["entrate"] += _dec(r["entrate"])
        a["uscite"] += _dec(r["uscite"])
        a["saldo_fine"] = _dec(r["saldo"])
    return [acc[k] for k in sorted(acc)]


# ---------------------------------------------------------------------------
# KPI di sostenibilità
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KPI:
    chiave: str
    nome: str
    valore: Decimal | None
    unita: str  # 'mesi' | '%' | 'x' | '€'
    allarme: str  # descrizione soglia d'allarme
    target: str  # descrizione target
    stato: str  # 'ok' | 'attenzione' | 'allarme' | 'nd'
    descrizione: str

    @property
    def semaforo(self) -> str:
        return {"ok": "🟢", "attenzione": "🟠", "allarme": "🔴"}.get(self.stato, "⚪")

    @property
    def valore_txt(self) -> str:
        if self.valore is None:
            return "n.d."
        if self.unita == "%":
            return f"{self.valore:.0f}%"
        if self.unita == "x":
            return f"{self.valore:.2f}×"
        if self.unita == "€":
            return f"{self.valore:,.0f} €"
        return f"{self.valore:.1f} {self.unita}"


def _stato_min(valore: Decimal | None, allarme: Decimal, ok: Decimal) -> str:
    """Più alto è meglio: sotto `allarme` -> allarme, sotto `ok` -> attenzione."""
    if valore is None:
        return "nd"
    if valore < allarme:
        return "allarme"
    if valore < ok:
        return "attenzione"
    return "ok"


def _stato_max(valore: Decimal | None, allarme: Decimal, ok: Decimal) -> str:
    """Più basso è meglio: sopra `allarme` -> allarme, sopra `ok` -> attenzione."""
    if valore is None:
        return "nd"
    if valore > allarme:
        return "allarme"
    if valore > ok:
        return "attenzione"
    return "ok"


def _pct(num: Decimal, den: Decimal) -> Decimal | None:
    if den <= 0:
        return None
    return (num / den * 100).quantize(Decimal("0.1"))


def kpi_autonomia(saldo, costi_mensili) -> KPI:
    s, c = _dec(saldo), _dec(costi_mensili)
    val = (s / c).quantize(Decimal("0.1")) if c > 0 else None
    return KPI(
        "autonomia",
        "Autonomia di cassa",
        val,
        "mesi",
        "< 6 mesi",
        "≥ 12 mesi",
        _stato_min(val, Decimal("6"), Decimal("12")),
        "Saldo attuale / costi mensili strutturali, senza nuove entrate.",
    )


def kpi_backlog_coverage(residuo_contratti, costi_mensili) -> KPI:
    r, c = _dec(residuo_contratti), _dec(costi_mensili)
    val = (r / c).quantize(Decimal("0.1")) if c > 0 else None
    return KPI(
        "backlog",
        "Backlog coverage",
        val,
        "mesi",
        "< 9 mesi",
        "12–15 mesi",
        _stato_min(val, Decimal("9"), Decimal("12")),
        "Mesi di costi coperti dal residuo dei contratti firmati "
        "(finanziamento − incassato).",
    )


def kpi_concentrazione_clienti(ricavi_per_controparte: dict[str, Decimal]) -> KPI:
    tot = sum((_dec(v) for v in ricavi_per_controparte.values()), Decimal("0"))
    top3 = sum(
        sorted((_dec(v) for v in ricavi_per_controparte.values()), reverse=True)[:3],
        Decimal("0"),
    )
    val = _pct(top3, tot)
    return KPI(
        "concentrazione",
        "Concentrazione clienti (top 3)",
        val,
        "%",
        "> 80%",
        "≤ 60%",
        _stato_max(val, Decimal("80"), Decimal("60")),
        "Peso dei primi tre committenti sui ricavi del periodo.",
    )


def kpi_quota_mercato(ricavi_per_tipo: dict[str, Decimal]) -> KPI:
    tot = sum((_dec(v) for v in ricavi_per_tipo.values()), Decimal("0"))
    mercato = _dec(ricavi_per_tipo.get("mercato")) + _dec(
        ricavi_per_tipo.get("ricorrente")
    )
    val = _pct(mercato, tot)
    return KPI(
        "quota_mercato",
        "Quota ricavi da mercato",
        val,
        "%",
        "< 40%",
        "≥ 70% (2030)",
        _stato_min(val, Decimal("40"), Decimal("70")),
        "Ricavi non derivanti da finanza agevolata sul totale.",
    )


def kpi_ricorrenti(ricavi_per_tipo: dict[str, Decimal]) -> KPI:
    tot = sum((_dec(v) for v in ricavi_per_tipo.values()), Decimal("0"))
    val = _pct(_dec(ricavi_per_tipo.get("ricorrente")), tot)
    return KPI(
        "ricorrenti",
        "Ricavi ricorrenti",
        val,
        "%",
        "< 10%",
        "≥ 40% (2030)",
        _stato_min(val, Decimal("10"), Decimal("40")),
        "Quota di canoni, manutenzioni e licensing sul totale.",
    )


def kpi_margine(entrate, uscite) -> KPI:
    e, u = _dec(entrate), _dec(uscite)
    val = _pct(e - u, e)
    return KPI(
        "margine",
        "Margine operativo (proxy EBITDA)",
        val,
        "%",
        "< 0%",
        "≥ 10% (2028) · ≥ 20% (2030)",
        _stato_min(val, Decimal("0"), Decimal("10")),
        "(Entrate − uscite operative) / entrate, da movimenti di cassa.",
    )


def kpi_tariffa_costo(tariffa_media, costo_pieno_ora) -> KPI:
    t, c = _dec(tariffa_media), _dec(costo_pieno_ora)
    val = (t / c).quantize(Decimal("0.01")) if c > 0 and t > 0 else None
    return KPI(
        "tariffa_costo",
        "Tariffa media / costo pieno FTE",
        val,
        "x",
        "< 1,6×",
        "≥ 1,6×",
        _stato_min(val, Decimal("1.6"), Decimal("1.6")),
        "Sotto 1,6× l'azienda sussidia i clienti con i grant.",
    )


def costo_pieno_orario(
    costo_personale_annuo, costi_indiretti_annui, teste_dirette, ore_vendibili_fte
) -> Decimal | None:
    """Costo pieno €/h = (personale + indiretti) / (FTE × ore vendibili)
    (schema del foglio «Costo Personale»: Gross Hourly Rate)."""
    fte, ore = _dec(teste_dirette), _dec(ore_vendibili_fte)
    if fte <= 0 or ore <= 0:
        return None
    tot = _dec(costo_personale_annuo) + _dec(costi_indiretti_annui)
    if tot <= 0:
        return None
    return (tot / (fte * ore)).quantize(CENT)


def tariffa_media_progetti(progetti: list[dict]) -> Decimal | None:
    """Tariffa media implicita = Σ finanziamento / Σ ore pianificate sui
    progetti che hanno entrambi i dati."""
    fin = Decimal("0")
    ore = Decimal("0")
    for p in progetti:
        f, o = _dec(p.get("importo")), _dec(p.get("ore"))
        if f > 0 and o > 0:
            fin += f
            ore += o
    return (fin / ore).quantize(CENT) if ore > 0 else None


def stima_utile_tasse(
    entrate_consuntive,
    uscite_consuntive,
    entrate_previste,
    uscite_previste,
    aliquota,
) -> dict:
    """Stima dell'utile d'esercizio (consuntivo + residuo previsto) e delle
    imposte (aliquota stimata, es. IRES 24% + IRAP 3,9%)."""
    e = _dec(entrate_consuntive) + _dec(entrate_previste)
    u = _dec(uscite_consuntive) + _dec(uscite_previste)
    utile = e - u
    tasse = (utile * _dec(aliquota)).quantize(CENT) if utile > 0 else Decimal("0")
    return {
        "entrate": e.quantize(CENT),
        "uscite": u.quantize(CENT),
        "utile_lordo": utile.quantize(CENT),
        "tasse_stimate": tasse,
        "utile_netto": (utile - tasse).quantize(CENT),
        "aliquota": _dec(aliquota),
    }
