"""Presentazioni automatiche (.pptx) sul template ANTECNICA 2026 (v3).

Disciplina (stessa di MAIC tasks): **usare il template, non aggiungere
grafica propria**. Titoli, sezioni e corpi vanno nei PLACEHOLDER dei layout
del template (`assets/antecnica_template_2026.pptx`):

  TITLE (102 titolo, 103 sottotitolo, 104 meta) · SECTION (101 numero,
  102 titolo, 103 sottotitolo) · CONTENT / CONTENT_DARK (100 titolo, 101
  corpo) · TWO_COLUMNS (100, 101, 102) · TITLE_ONLY (100) · CLOSING (102).

Le uniche forme disegnate sono le card KPI (replicano la slide «Measured
performance» del template), le tabelle native, i grafici NATIVI PowerPoint
(mai immagini) e il GANTT del portafoglio, che non ha un layout equivalente.

Tre deck, costruiti da dizionari («pack») così da essere testabili senza DB:
  * build_report_attivita   — stato progetti/deliverable/task e persone;
  * build_report_finanziario — cruscotto di sostenibilità (solo admin);
  * build_report_progetto   — SAL di un singolo progetto.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

TEMPLATE = (
    Path(__file__).resolve().parents[2] / "assets" / "antecnica_template_2026.pptx"
)

# --- Palette del template (theme1.xml) ----------------------------------------------
AZZURRO = RGBColor(0x2E, 0x8F, 0xC0)  # accent1
CIELO = RGBColor(0x66, 0xCC, 0xFF)  # accent3
ANTRACITE = RGBColor(0x0B, 0x0F, 0x14)  # dk1
GRIGIO = RGBColor(0x45, 0x53, 0x5F)  # accent4
GRIGIO_CHIARO = RGBColor(0x9B, 0xAB, 0xBA)  # accent5
NEBBIA = RGBColor(0xE1, 0xE6, 0xEA)  # accent6
FONDO = RGBColor(0xF4, 0xF6, 0xF8)  # lt2
BIANCO = RGBColor(0xFF, 0xFF, 0xFF)
VERDE = RGBColor(0x2E, 0x9E, 0x6B)
AMBRA = RGBColor(0xE0, 0xA0, 0x20)
ROSSO = RGBColor(0xD9, 0x53, 0x4F)
PALETTE = [AZZURRO, GRIGIO, CIELO, VERDE, AMBRA, GRIGIO_CHIARO, ROSSO, ANTRACITE]

COLORE_CATEGORIA = {
    "Progetto attivo": AZZURRO,
    "Progetto chiuso": GRIGIO_CHIARO,
    "Proposta inviata": AMBRA,
    "Proposta in bozza": CIELO,
}
COLORE_STATO = {
    "completato": VERDE,
    "in_corso": AZZURRO,
    "bloccato": ROSSO,
    "da_fare": GRIGIO,
    "annullato": GRIGIO_CHIARO,
    "prevista": GRIGIO,
    "completata": VERDE,
    "slittata": AMBRA,
}
STATO_TXT = {
    "completato": "Completato",
    "in_corso": "In corso",
    "bloccato": "Bloccato",
    "da_fare": "Da fare",
    "annullato": "Annullato",
    "prevista": "Prevista",
    "completata": "Completata",
    "slittata": "Slittata",
}

# geometria dell'area contenuto (in pollici, slide 13.33 × 7.5)
X0, Y0, W, H = 0.6, 1.5, 12.13, 4.9


def _fmt_data(d) -> str:
    return f"{d:%d/%m/%Y}" if isinstance(d, date) else (str(d) if d else "—")


def _fmt_eur(v) -> str:
    try:
        return f"{float(v):,.0f} €".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


class Deck:
    """Wrapper minimale del template: una funzione per tipo di slide."""

    def __init__(self, template: Path | None = None):
        self.prs = Presentation(str(template or TEMPLATE))
        self._rimuovi_slide_esistenti()
        self.n_slide = 0

    # --- infrastruttura -------------------------------------------------------------
    def _rimuovi_slide_esistenti(self) -> None:
        lst = self.prs.slides._sldIdLst  # noqa: SLF001 (API interna, come MAIC tasks)
        for sld in list(lst):
            self.prs.part.drop_rel(sld.rId)
            lst.remove(sld)

    def _layout(self, nome: str):
        for lay in self.prs.slide_layouts:
            if lay.name == nome:
                return lay
        return self.prs.slide_layouts[3]  # CONTENT

    def _add(self, nome: str):
        self.n_slide += 1
        return self.prs.slides.add_slide(self._layout(nome))

    @staticmethod
    def _ph(slide, idx: int):
        for ph in slide.placeholders:
            if ph.placeholder_format.idx == idx:
                return ph
        return None

    def _set(
        self,
        slide,
        idx: int,
        testo,
        size: int | None = None,
        bold: bool | None = None,
        color=None,
    ) -> None:
        ph = self._ph(slide, idx)
        if ph is None:
            return
        tf = ph.text_frame
        tf.text = "" if testo is None else str(testo)
        if size or bold is not None or color is not None:
            for p in tf.paragraphs:
                for r in p.runs:
                    if size:
                        r.font.size = Pt(size)
                    if bold is not None:
                        r.font.bold = bold
                    if color is not None:
                        r.font.color.rgb = color

    @staticmethod
    def _tidy(slide) -> None:
        """Rimuove i placeholder rimasti vuoti (niente «Click to add»)."""
        for ph in list(slide.placeholders):
            if ph.has_text_frame and not ph.text_frame.text.strip():
                ph._element.getparent().remove(ph._element)  # noqa: SLF001

    @staticmethod
    def _bullets(ph, punti) -> None:
        tf = ph.text_frame
        tf.text = ""
        primo = True
        for p in punti:
            livello, testo = p if isinstance(p, tuple) else (0, p)
            par = tf.paragraphs[0] if primo else tf.add_paragraph()
            primo = False
            par.text = str(testo)
            par.level = int(livello)

    def _testo(
        self,
        slide,
        x,
        y,
        w,
        h,
        testo,
        size=10,
        bold=False,
        color=ANTRACITE,
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    ):
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.04)
        tf.margin_top = tf.margin_bottom = Inches(0.02)
        tf.vertical_anchor = anchor
        p = tf.paragraphs[0]
        p.alignment = align
        r = p.add_run()
        r.text = str(testo)
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        return tb

    def _rett(self, slide, x, y, w, h, fill, line=None, rounded=False):
        forma = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
            Inches(x),
            Inches(y),
            Inches(w),
            Inches(h),
        )
        forma.fill.solid()
        forma.fill.fore_color.rgb = fill
        if line is None:
            forma.line.fill.background()
        else:
            forma.line.color.rgb = line
            forma.line.width = Pt(0.75)
        forma.shadow.inherit = False
        if rounded:
            forma.adjustments[0] = 0.06
        forma.text_frame.text = ""
        return forma

    def _nota(self, slide, testo: str, scuro: bool = False) -> None:
        if testo:
            self._testo(
                slide,
                X0,
                6.45,
                W,
                0.4,
                testo,
                size=9,
                color=(NEBBIA if scuro else GRIGIO),
            )

    # --- slide ----------------------------------------------------------------
    def titolo(self, titolo: str, sottotitolo: str = "", meta: str = "") -> None:
        s = self._add("TITLE")
        self._set(s, 102, titolo)
        self._set(s, 103, sottotitolo)
        self._set(s, 104, meta)
        self._tidy(s)

    def sezione(self, numero: int, titolo: str, sottotitolo: str = "") -> None:
        s = self._add("SECTION")
        self._set(s, 101, f"{numero:02d}")
        self._set(s, 102, titolo)
        self._set(s, 103, sottotitolo)
        self._tidy(s)

    def contenuto(self, titolo: str, punti: list, scuro: bool = False) -> None:
        s = self._add("CONTENT_DARK" if scuro else "CONTENT")
        self._set(s, 100, titolo)
        ph = self._ph(s, 101)
        if ph is not None:
            self._bullets(ph, punti or ["—"])
        self._tidy(s)

    def due_colonne(
        self, titolo: str, sinistra: tuple[str, list], destra: tuple[str, list]
    ) -> None:
        s = self._add("TWO_COLUMNS")
        self._set(s, 100, titolo)
        for idx, (intestazione, voci) in ((101, sinistra), (102, destra)):
            ph = self._ph(s, idx)
            if ph is None:
                continue
            tf = ph.text_frame
            tf.text = ""
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = intestazione
            r.font.bold = True
            r.font.color.rgb = AZZURRO
            for v in voci or ["—"]:
                livello, testo = v if isinstance(v, tuple) else (0, v)
                par = tf.add_paragraph()
                par.text = str(testo)
                par.level = int(livello)
        self._tidy(s)

    def kpi(self, titolo: str, tiles: list[tuple], nota: str = "") -> None:
        """Card KPI: tiles = [(valore, etichetta, sotto-testo[, colore])], max 8."""
        s = self._add("TITLE_ONLY")
        self._set(s, 100, titolo)
        tiles = tiles[:8]
        per_riga = 4 if len(tiles) > 4 else max(len(tiles), 1)
        righe = (len(tiles) + per_riga - 1) // per_riga
        gap = 0.2
        cw = (W - gap * (per_riga - 1)) / per_riga
        ch = 3.4 if righe == 1 else 2.35
        for n, t in enumerate(tiles):
            valore, etichetta, sotto = t[0], t[1], (t[2] if len(t) > 2 else "")
            colore = t[3] if len(t) > 3 and t[3] is not None else AZZURRO
            x = X0 + (n % per_riga) * (cw + gap)
            y = 1.7 + (n // per_riga) * (ch + gap)
            self._rett(s, x, y, cw, ch, FONDO, NEBBIA, rounded=True)
            self._testo(
                s,
                x + 0.25,
                y + 0.3,
                cw - 0.5,
                1.0,
                valore,
                size=30 if righe == 1 else 24,
                bold=True,
                color=colore,
            )
            self._testo(
                s,
                x + 0.25,
                y + (1.5 if righe == 1 else 1.25),
                cw - 0.5,
                0.45,
                etichetta,
                size=12,
                bold=True,
            )
            self._testo(
                s,
                x + 0.25,
                y + (2.0 if righe == 1 else 1.65),
                cw - 0.5,
                0.6,
                sotto,
                size=9,
                color=GRIGIO,
            )
        self._nota(s, nota)
        self._tidy(s)

    def tabella(
        self,
        titolo: str,
        header: list[str],
        righe: list[list],
        larghezze: list[float] | None = None,
        nota: str = "",
        max_righe: int = 14,
        font: int = 10,
    ) -> None:
        """Tabella nativa, paginata («(cont.)»). Cella = testo oppure
        (testo, RGBColor) per colorare il testo."""
        if not righe:
            righe = [["—"] + [""] * (len(header) - 1)]
        pagine = [righe[i : i + max_righe] for i in range(0, len(righe), max_righe)]
        for n_pag, blocco in enumerate(pagine):
            s = self._add("TITLE_ONLY")
            self._set(s, 100, titolo + (" (cont.)" if n_pag else ""))
            rh = 0.31
            shape = s.shapes.add_table(
                len(blocco) + 1,
                len(header),
                Inches(X0),
                Inches(Y0),
                Inches(W),
                Inches(rh * (len(blocco) + 1)),
            )
            tbl = shape.table
            tbl.first_row = True
            tbl.horz_banding = False
            if larghezze:
                tot = sum(larghezze)
                for j, lw in enumerate(larghezze):
                    tbl.columns[j].width = Inches(W * lw / tot)
            for j, h in enumerate(header):
                self._cella(
                    tbl.cell(0, j), h, size=font, bold=True, color=BIANCO, fill=AZZURRO
                )
            for i, riga in enumerate(blocco, start=1):
                fill = FONDO if i % 2 == 0 else BIANCO
                for j in range(len(header)):
                    v = riga[j] if j < len(riga) else ""
                    if isinstance(v, tuple):
                        testo, colore = v[0], (v[1] or ANTRACITE)
                    else:
                        testo, colore = v, ANTRACITE
                    self._cella(
                        tbl.cell(i, j), testo, size=font, color=colore, fill=fill
                    )
            for i in range(len(blocco) + 1):
                tbl.rows[i].height = Inches(rh)
            self._nota(s, nota if n_pag == len(pagine) - 1 else "")
            self._tidy(s)

    @staticmethod
    def _cella(cell, testo, size=10, bold=False, color=ANTRACITE, fill=None) -> None:
        cell.text = "" if testo is None else str(testo)
        cell.margin_left = cell.margin_right = Inches(0.06)
        cell.margin_top = cell.margin_bottom = Inches(0.02)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(size)
                r.font.bold = bold
                r.font.color.rgb = color
        if fill is not None:
            cell.fill.solid()
            cell.fill.fore_color.rgb = fill

    def grafico(
        self,
        titolo: str,
        categorie: list[str],
        serie: dict[str, list],
        tipo: str = "colonne",
        scuro: bool = True,
        nota: str = "",
        formato: str = "#,##0",
    ) -> None:
        """Grafico NATIVO PowerPoint: tipo in colonne | colonne_impilate |
        linee | barre."""
        s = self._add("CONTENT_DARK" if scuro else "TITLE_ONLY")
        self._set(s, 100, titolo)
        ph = self._ph(s, 101)
        if ph is not None:
            ph._element.getparent().remove(ph._element)  # noqa: SLF001
        cd = CategoryChartData()
        cd.categories = [str(c) for c in categorie]
        for nome, valori in serie.items():
            cd.add_series(nome, [float(v or 0) for v in valori])
        xl = {
            "colonne": XL_CHART_TYPE.COLUMN_CLUSTERED,
            "colonne_impilate": XL_CHART_TYPE.COLUMN_STACKED,
            "linee": XL_CHART_TYPE.LINE_MARKERS,
            "barre": XL_CHART_TYPE.BAR_CLUSTERED,
        }[tipo]
        gf = s.shapes.add_chart(xl, Inches(X0), Inches(Y0), Inches(W), Inches(4.8), cd)
        ch = gf.chart
        testo = BIANCO if scuro else ANTRACITE
        ch.font.size = Pt(11)
        ch.font.color.rgb = testo
        ch.has_legend = len(serie) > 1
        if ch.has_legend:
            ch.legend.position = XL_LEGEND_POSITION.BOTTOM
            ch.legend.include_in_layout = False
            ch.legend.font.color.rgb = testo
        ch.value_axis.tick_labels.number_format = formato
        ch.value_axis.tick_labels.number_format_is_linked = False
        ch.value_axis.tick_labels.font.color.rgb = testo
        ch.category_axis.tick_labels.font.color.rgb = testo
        ch.value_axis.major_gridlines.format.line.color.rgb = (
            GRIGIO if scuro else NEBBIA
        )
        ch.value_axis.format.line.color.rgb = GRIGIO_CHIARO
        ch.category_axis.format.line.color.rgb = GRIGIO_CHIARO
        plot = ch.plots[0]
        if tipo in ("colonne", "colonne_impilate", "barre"):
            plot.gap_width = 60
            if tipo == "colonne_impilate":
                plot.overlap = 100
        for n, serie_xl in enumerate(plot.series):
            colore = PALETTE[n % len(PALETTE)]
            if tipo == "linee":
                serie_xl.format.line.color.rgb = colore
                serie_xl.format.line.width = Pt(2.5)
                serie_xl.smooth = False
                serie_xl.marker.format.fill.solid()
                serie_xl.marker.format.fill.fore_color.rgb = colore
            else:
                serie_xl.format.fill.solid()
                serie_xl.format.fill.fore_color.rgb = colore
        self._nota(s, nota, scuro=scuro)
        self._tidy(s)

    def gantt(
        self,
        titolo: str,
        righe: list[dict],
        anni: list[int],
        oggi: date | None = None,
        nota: str = "",
        max_righe: int = 11,
    ) -> None:
        """GANTT disegnato: righe = [{etichetta, inizio, fine, categoria}]."""
        if not righe or not anni:
            return
        oggi = oggi or date.today()
        pagine = [righe[i : i + max_righe] for i in range(0, len(righe), max_righe)]
        lw = 3.3  # colonna etichette
        tx0, tw = X0 + lw + 0.1, W - lw - 0.1
        d0, d1 = date(anni[0], 1, 1), date(anni[-1], 12, 31)
        tot_giorni = (d1 - d0).days + 1

        def xpos(d: date) -> float:
            d = min(max(d, d0), d1 + timedelta(days=1))
            return tx0 + tw * ((d - d0).days / tot_giorni)

        for n_pag, blocco in enumerate(pagine):
            s = self._add("TITLE_ONLY")
            self._set(s, 100, titolo + (" (cont.)" if n_pag else ""))
            # intestazione anni
            wy = tw / len(anni)
            for k, a in enumerate(anni):
                x = tx0 + k * wy
                self._rett(s, x, Y0, wy, 0.32, FONDO if k % 2 == 0 else NEBBIA)
                self._testo(
                    s,
                    x,
                    Y0,
                    wy,
                    0.32,
                    str(a),
                    size=10,
                    bold=True,
                    color=GRIGIO,
                    align=PP_ALIGN.CENTER,
                    anchor=MSO_ANCHOR.MIDDLE,
                )
            rh = min(0.42, (6.3 - (Y0 + 0.4)) / max(len(blocco), 1))
            for i, r in enumerate(blocco):
                y = Y0 + 0.4 + i * rh
                if i % 2 == 1:
                    self._rett(s, X0, y, W, rh, FONDO)
                self._testo(
                    s, X0, y, lw, rh, r["etichetta"], size=9, anchor=MSO_ANCHOR.MIDDLE
                )
                ini, fine = r.get("inizio"), r.get("fine")
                if isinstance(ini, date) and isinstance(fine, date) and fine >= ini:
                    xa, xb = xpos(ini), xpos(fine + timedelta(days=1))
                    colore = COLORE_CATEGORIA.get(r.get("categoria", ""), AZZURRO)
                    barra = self._rett(
                        s,
                        xa,
                        y + rh * 0.22,
                        max(xb - xa, 0.05),
                        rh * 0.56,
                        colore,
                        rounded=True,
                    )
                    if r.get("testo_barra"):
                        tf = barra.text_frame
                        tf.margin_left = Inches(0.04)
                        p = tf.paragraphs[0]
                        run = p.add_run()
                        run.text = str(r["testo_barra"])
                        run.font.size = Pt(7)
                        run.font.color.rgb = (
                            BIANCO
                            if colore not in (NEBBIA, GRIGIO_CHIARO)
                            else ANTRACITE
                        )
                    for m in r.get("milestone", []) or []:
                        if isinstance(m, date):
                            xm = xpos(m)
                            rombo = s.shapes.add_shape(
                                MSO_SHAPE.DIAMOND,
                                Inches(xm - 0.07),
                                Inches(y + rh * 0.28),
                                Inches(0.14),
                                Inches(rh * 0.44),
                            )
                            rombo.fill.solid()
                            rombo.fill.fore_color.rgb = ROSSO
                            rombo.line.color.rgb = BIANCO
                            rombo.shadow.inherit = False
            # separatori anni + oggi
            y_fine = Y0 + 0.4 + len(blocco) * rh
            for k in range(1, len(anni)):
                x = tx0 + k * wy
                ln = s.shapes.add_connector(
                    1, Inches(x), Inches(Y0 + 0.32), Inches(x), Inches(y_fine)
                )
                ln.line.color.rgb = NEBBIA
                ln.line.width = Pt(0.75)
            if d0 <= oggi <= d1:
                xo = xpos(oggi)
                ln = s.shapes.add_connector(
                    1, Inches(xo), Inches(Y0), Inches(xo), Inches(y_fine)
                )
                ln.line.color.rgb = AZZURRO
                ln.line.width = Pt(1.5)
                self._testo(
                    s,
                    xo - 0.4,
                    y_fine + 0.02,
                    0.8,
                    0.25,
                    "oggi",
                    size=8,
                    color=AZZURRO,
                    align=PP_ALIGN.CENTER,
                )
            # legenda
            lx = X0
            for nome, colore in COLORE_CATEGORIA.items():
                self._rett(s, lx, 6.55, 0.22, 0.16, colore, rounded=True)
                self._testo(s, lx + 0.26, 6.48, 1.6, 0.3, nome, size=8, color=GRIGIO)
                lx += 1.9
            self._rett(s, lx, 6.55, 0.14, 0.16, ROSSO)
            self._testo(s, lx + 0.2, 6.48, 1.2, 0.3, "milestone", size=8, color=GRIGIO)
            self._nota(s, nota if n_pag == len(pagine) - 1 else "")
            self._tidy(s)

    def chiusura(self, testo: str = "Grazie") -> None:
        s = self._add("CLOSING")
        self._set(s, 102, testo)
        self._tidy(s)

    def bytes(self) -> bytes:
        buf = BytesIO()
        self.prs.save(buf)
        return buf.getvalue()


# =====================================================================================
# Builders
# =====================================================================================


def _riga_albero(
    livello: int, titolo: str, stato: str, scadenza, owner: str, oggi: date
) -> list:
    prefissi = {0: "▸ ", 1: "   • ", 2: "      › "}
    stato_txt = STATO_TXT.get(stato, stato or "")
    colore = COLORE_STATO.get(stato, ANTRACITE)
    scad_txt = _fmt_data(scadenza)
    in_ritardo = (
        isinstance(scadenza, date)
        and scadenza < oggi
        and stato not in ("completato", "annullato", "completata")
    )
    return [
        prefissi.get(livello, "") + (titolo or ""),
        (stato_txt, colore),
        (scad_txt, ROSSO if in_ritardo else ANTRACITE),
        owner or "—",
    ]


def build_report_attivita(pack: dict) -> bytes:
    """Deck «Report attività»: portafoglio, progetti (albero), persone, scadenze."""
    oggi = pack.get("oggi") or date.today()
    d = Deck()
    d.titolo(
        pack.get("titolo", "Report attività"),
        pack.get("sottotitolo", ""),
        pack.get("meta", ""),
    )

    # 01 — Portafoglio
    d.sezione(1, "Portafoglio", "Progetti in essere e proposte in corso, per anno")
    if pack.get("gantt"):
        d.gantt(
            "Linea temporale del portafoglio",
            pack["gantt"],
            pack.get("anni") or [oggi.year],
            oggi=oggi,
        )
    sintesi = pack.get("sintesi", {})
    d.kpi(
        "Attività in sintesi",
        [
            (str(sintesi.get("progetti_attivi", 0)), "Progetti attivi", ""),
            (str(sintesi.get("deliverable_aperti", 0)), "Deliverable aperti", ""),
            (str(sintesi.get("task_attivi", 0)), "Task attivi", ""),
            (
                str(sintesi.get("in_ritardo", 0)),
                "In ritardo",
                "task oltre scadenza",
                ROSSO if sintesi.get("in_ritardo") else VERDE,
            ),
            (
                str(sintesi.get("bloccati", 0)),
                "Bloccati",
                "",
                ROSSO if sintesi.get("bloccati") else GRIGIO,
            ),
            (
                str(sintesi.get("completati_periodo", 0)),
                "Completati",
                f"ultimi {pack.get('periodo_giorni', 30)} giorni",
                VERDE,
            ),
            (
                str(sintesi.get("avviati_periodo", 0)),
                "Avviati",
                f"ultimi {pack.get('periodo_giorni', 30)} giorni",
            ),
            (
                str(sintesi.get("scadenze_30", 0)),
                "Scadenze",
                "prossimi 30 giorni",
                AMBRA,
            ),
        ],
    )

    # 02 — Progetti
    d.sezione(2, "Progetti", "Deliverable, task e subtask per progetto")
    for prog in pack.get("progetti", []):
        righe: list[list] = []
        for m in prog.get("milestone", []):
            righe.append(
                [
                    "◆ " + m["titolo"],
                    (
                        STATO_TXT.get(m.get("stato"), m.get("stato", "")),
                        COLORE_STATO.get(m.get("stato"), ANTRACITE),
                    ),
                    _fmt_data(m.get("data")),
                    "milestone",
                ]
            )
        for dv in prog.get("deliverables", []):
            righe.append(
                _riga_albero(
                    0,
                    "📦 "
                    + dv["titolo"]
                    + (f" ({dv['tipo']})" if dv.get("tipo") else ""),
                    dv.get("stato"),
                    dv.get("scadenza"),
                    dv.get("owner"),
                    oggi,
                )
            )
            for t in dv.get("tasks", []):
                righe.append(
                    _riga_albero(
                        1,
                        t["titolo"],
                        t.get("stato"),
                        t.get("scadenza"),
                        t.get("owner"),
                        oggi,
                    )
                )
                for s_ in t.get("subtasks", []):
                    righe.append(
                        _riga_albero(
                            2,
                            s_["titolo"],
                            s_.get("stato"),
                            s_.get("scadenza"),
                            s_.get("owner"),
                            oggi,
                        )
                    )
        for t in prog.get("task_liberi", []):
            righe.append(
                _riga_albero(
                    1,
                    t["titolo"],
                    t.get("stato"),
                    t.get("scadenza"),
                    t.get("owner"),
                    oggi,
                )
            )
            for s_ in t.get("subtasks", []):
                righe.append(
                    _riga_albero(
                        2,
                        s_["titolo"],
                        s_.get("stato"),
                        s_.get("scadenza"),
                        s_.get("owner"),
                        oggi,
                    )
                )
        sotto = " · ".join(
            x
            for x in (
                prog.get("controparte"),
                f"{_fmt_data(prog.get('inizio'))} → {_fmt_data(prog.get('fine'))}",
                prog.get("stato"),
            )
            if x
        )
        d.tabella(
            prog["etichetta"],
            ["Elemento", "Stato", "Scadenza", "Owner"],
            righe,
            larghezze=[6.5, 1.6, 1.6, 2.4],
            nota=sotto,
            max_righe=13,
        )

    # 03 — Persone
    persone = pack.get("persone", [])
    if persone:
        d.sezione(3, "Persone", "Carico e avanzamento per persona")
        d.tabella(
            "Carico di lavoro",
            [
                "Persona",
                "Attivi",
                "In ritardo",
                "Bloccati",
                f"Completati ({pack.get('periodo_giorni', 30)}g)",
                "Puntualità",
            ],
            [
                [
                    p["nome"],
                    str(p.get("attivi", 0)),
                    (
                        str(p.get("in_ritardo", 0)),
                        ROSSO if p.get("in_ritardo") else ANTRACITE,
                    ),
                    str(p.get("bloccati", 0)),
                    (str(p.get("completati_periodo", 0)), VERDE),
                    p.get("puntualita") or "—",
                ]
                for p in persone
            ],
            larghezze=[3.5, 1.2, 1.4, 1.2, 2.0, 1.4],
        )
        for p in persone:
            sx = [f"✓ {t}" for t in p.get("completati", [])[:6]] + [
                f"→ {t}" for t in p.get("in_corso", [])[:6]
            ]
            dx = [f"⚠ {t}" for t in p.get("ritardo", [])[:6]] + [
                f"■ {t}" for t in p.get("bloccati_lista", [])[:6]
            ]
            if p.get("altri_sx"):
                sx.append(f"… e altri {p['altri_sx']}")
            if p.get("altri_dx"):
                dx.append(f"… e altri {p['altri_dx']}")
            d.due_colonne(
                p["nome"], ("Completati e in corso", sx), ("In ritardo e bloccati", dx)
            )

    # 04 — Prossime scadenze
    scad = pack.get("scadenze", [])
    d.sezione(4, "Prossime scadenze", "Task, deliverable e milestone")
    d.tabella(
        "Scadenze in arrivo",
        ["Data", "Tipo", "Titolo", "Progetto", "Owner"],
        [
            [
                (
                    _fmt_data(s_["data"]),
                    (
                        ROSSO
                        if isinstance(s_["data"], date) and s_["data"] < oggi
                        else ANTRACITE
                    ),
                ),
                s_.get("tipo", ""),
                s_.get("titolo", ""),
                s_.get("progetto", ""),
                s_.get("owner", ""),
            ]
            for s_ in scad[:28]
        ],
        larghezze=[1.4, 1.4, 5.0, 2.6, 1.8],
    )
    d.chiusura(pack.get("chiusura", "Grazie"))
    return d.bytes()


def build_report_finanziario(pack: dict) -> bytes:
    """Deck «Report finanziario» (solo amministratore)."""
    anno = pack.get("anno", date.today().year)
    d = Deck()
    d.titolo(
        pack.get("titolo", "Report finanziario"),
        pack.get("sottotitolo", f"Sostenibilità economica {anno}"),
        pack.get("meta", ""),
    )

    d.sezione(
        1, "Cruscotto di sostenibilità", "Indicatori del Piano strategico 2026-2030"
    )
    kpi = pack.get("kpi", [])
    colori = {"ok": VERDE, "attenzione": AMBRA, "allarme": ROSSO, "nd": GRIGIO_CHIARO}
    d.kpi(
        "Indicatori chiave",
        [
            (
                k["valore_txt"],
                k["nome"],
                f"allarme {k['allarme']} · target {k['target']}",
                colori.get(k.get("stato"), AZZURRO),
            )
            for k in kpi
        ],
        nota=(
            "Verde: sopra target · ambra: fra allarme e target · "
            "rosso: sotto la soglia d'allarme."
        ),
    )
    d.tabella(
        "Indicatori: definizione e soglie",
        ["Indicatore", "Valore", "Allarme", "Target", "Definizione"],
        [
            [
                k["nome"],
                (k["valore_txt"], colori.get(k.get("stato"), ANTRACITE)),
                k["allarme"],
                k["target"],
                k.get("descrizione", ""),
            ]
            for k in kpi
        ],
        larghezze=[2.6, 1.1, 1.3, 1.9, 5.2],
        font=9,
    )
    d.kpi(
        "Cassa, costi e backlog",
        [
            (_fmt_eur(pack.get("saldo")), "Saldo di cassa", pack.get("saldo_nota", "")),
            (
                _fmt_eur(pack.get("costi_mensili")),
                "Costi mensili strutturali",
                pack.get("base_costi", ""),
            ),
            (
                _fmt_eur(pack.get("backlog")),
                "Backlog contratti firmati",
                "finanziamento − incassato",
            ),
            (
                _fmt_eur(pack.get("pipeline_pesata")),
                "Pipeline pesata",
                "proposte × probabilità",
            ),
        ],
    )

    d.sezione(2, "Flussi di cassa", "Consuntivo e proiezione a scenari")
    cf = pack.get("cash_flow")
    if cf and cf.get("mesi"):
        d.grafico(
            f"Cash flow {anno} per mese",
            cf["mesi"],
            {"Entrate": cf["entrate"], "Uscite": cf["uscite"]},
            tipo="colonne",
            scuro=True,
        )
    sc = pack.get("scenari")
    if sc and sc.get("mesi"):
        d.grafico(
            "Proiezione del saldo a scenari",
            sc["mesi"],
            {
                "Solo contratti firmati": sc["firmato"],
                "+ pipeline pesata": sc["pesato"],
                "+ pipeline intera": sc["ottimista"],
            },
            tipo="linee",
            scuro=True,
            nota=pack.get("scenari_nota", ""),
        )
    if pack.get("totali_anno"):
        d.tabella(
            "Totali per anno (scenario pesato)",
            ["Anno", "Entrate", "Uscite", "Saldo a fine anno"],
            [
                [
                    str(t["anno"]),
                    _fmt_eur(t["entrate"]),
                    _fmt_eur(t["uscite"]),
                    (
                        _fmt_eur(t["saldo_fine"]),
                        ROSSO if float(t["saldo_fine"]) < 0 else VERDE,
                    ),
                ]
                for t in pack["totali_anno"]
            ],
            larghezze=[1.5, 3, 3, 3],
        )
    if pack.get("storico_anni"):
        st_ = pack["storico_anni"]
        d.grafico(
            "Entrate e uscite per anno (consuntivo)",
            [str(r["anno"]) for r in st_],
            {
                "Entrate": [r["entrate"] for r in st_],
                "Uscite": [r["uscite"] for r in st_],
            },
            tipo="colonne",
            scuro=False,
        )

    d.sezione(3, "Progetti e contratti", "Backlog, P&L per progetto, ricavi attesi")
    d.tabella(
        "Backlog dei contratti firmati",
        [
            "Progetto",
            "Controparte",
            "Tipo ricavo",
            "Importo",
            "Incassato",
            "Residuo",
            "Fine",
        ],
        [
            [
                b["etichetta"],
                b.get("controparte", ""),
                b.get("tipo_ricavo", ""),
                _fmt_eur(b["importo"]),
                _fmt_eur(b["incassato"]),
                _fmt_eur(b["residuo"]),
                _fmt_data(b.get("data_fine")),
            ]
            for b in pack.get("backlog_det", [])
        ],
        larghezze=[3.4, 2.0, 1.3, 1.5, 1.5, 1.5, 1.2],
        font=9,
    )
    if pack.get("pnl"):
        d.tabella(
            "P&L per progetto (movimenti riconciliati)",
            ["Progetto", "Entrate", "Uscite", "Saldo"],
            [
                [
                    p["progetto"],
                    _fmt_eur(p["entrate"]),
                    _fmt_eur(p["uscite"]),
                    (_fmt_eur(p["saldo"]), ROSSO if float(p["saldo"]) < 0 else VERDE),
                ]
                for p in pack["pnl"]
            ],
            larghezze=[5, 2.3, 2.3, 2.3],
        )
    ra = pack.get("ricavi_anno")
    if ra and ra.get("anni"):
        d.grafico(
            "Ricavi attesi per anno dal portafoglio",
            ra["anni"],
            ra["serie"],
            tipo="colonne_impilate",
            scuro=True,
            nota=(
                "Finanziamento/budget pro-rata sugli anni; "
                "proposte pesate per probabilità."
            ),
        )

    d.sezione(4, f"Esercizio {anno}", "Stima gestionale di utile e imposte")
    stima = pack.get("stima") or {}
    if stima:
        d.kpi(
            f"Stima utile e tasse {anno}",
            [
                (_fmt_eur(stima.get("entrate")), "Entrate", "consuntivo + previste"),
                (_fmt_eur(stima.get("uscite")), "Uscite", "consuntivo + previste"),
                (
                    _fmt_eur(stima.get("utile_lordo")),
                    "Utile lordo",
                    "",
                    VERDE if float(stima.get("utile_lordo", 0)) >= 0 else ROSSO,
                ),
                (
                    _fmt_eur(stima.get("tasse_stimate")),
                    "Imposte stimate",
                    f"aliquota {float(stima.get('aliquota', 0)) * 100:.1f}%",
                ),
                (
                    _fmt_eur(stima.get("utile_netto")),
                    "Utile netto stimato",
                    "",
                    VERDE if float(stima.get("utile_netto", 0)) >= 0 else ROSSO,
                ),
            ],
            nota="Stima gestionale sui flussi di cassa: non sostituisce il bilancio.",
        )
    if pack.get("scadenzario"):
        d.tabella(
            "Scadenzario (documenti non saldati)",
            ["Scadenza", "Tipo", "Numero", "Controparte", "Importo", "Stato"],
            [
                [
                    _fmt_data(s_["scadenza"]),
                    s_["tipo"],
                    s_.get("numero", ""),
                    s_.get("controparte", ""),
                    _fmt_eur(s_["importo"]),
                    s_.get("stato", ""),
                ]
                for s_ in pack["scadenzario"]
            ],
            larghezze=[1.4, 1.1, 1.6, 4.0, 1.8, 1.4],
        )
    d.chiusura(pack.get("chiusura", "Grazie"))
    return d.bytes()


def build_report_progetto(pack: dict) -> bytes:
    """Deck «Report progetto» (SAL): stato, milestone, albero attività, ore."""
    oggi = pack.get("oggi") or date.today()
    d = Deck()
    d.titolo(
        pack.get("etichetta", "Progetto"), pack.get("titolo", ""), pack.get("meta", "")
    )
    tiles = []
    if pack.get("economia"):
        tiles += [
            (_fmt_eur(pack.get("budget")), "Budget (baseline)", ""),
            (_fmt_eur(pack.get("speso")), "Speso (consuntivo)", ""),
            (
                _fmt_eur(pack.get("rimanente")),
                "Quota rimanente",
                "",
                ROSSO if float(pack.get("rimanente") or 0) < 0 else VERDE,
            ),
            (f"{pack.get('avanzamento_pct', 0):.0f}%", "Avanzamento spesa", ""),
        ]
    tiles += [
        (str(pack.get("ore_timesheet", 0)), "Ore a timesheet", ""),
        (
            f"{pack.get('deliverable_completati', 0)}/"
            f"{pack.get('deliverable_totali', 0)}",
            "Deliverable completati",
            "",
        ),
        (
            f"{pack.get('task_completati', 0)}/{pack.get('task_totali', 0)}",
            "Task completati",
            "",
        ),
        (
            str(pack.get("in_ritardo", 0)),
            "In ritardo",
            "",
            ROSSO if pack.get("in_ritardo") else VERDE,
        ),
    ]
    d.kpi(
        "Stato del progetto",
        tiles,
        nota=" · ".join(
            x
            for x in (
                pack.get("controparte"),
                pack.get("cup"),
                f"{_fmt_data(pack.get('inizio'))} → {_fmt_data(pack.get('fine'))}",
            )
            if x
        ),
    )
    if pack.get("gantt"):
        d.gantt(
            "Cronoprogramma", pack["gantt"], pack.get("anni") or [oggi.year], oggi=oggi
        )
    if pack.get("economia") and pack.get("quote"):
        d.tabella(
            "Budget vs consuntivo per categoria",
            ["Categoria", "Budget", "Speso", "Rimanente"],
            [
                [
                    q["categoria"],
                    _fmt_eur(q["budget"]),
                    _fmt_eur(q["speso"]),
                    (
                        _fmt_eur(q["rimanente"]),
                        ROSSO if float(q["rimanente"]) < 0 else VERDE,
                    ),
                ]
                for q in pack["quote"]
            ],
            larghezze=[4, 2.5, 2.5, 2.5],
        )
    if pack.get("milestone"):
        d.tabella(
            "Milestone",
            ["Milestone", "Data prevista", "Stato", "Pagamento"],
            [
                [
                    m["titolo"],
                    _fmt_data(m.get("data")),
                    (
                        STATO_TXT.get(m.get("stato"), m.get("stato", "")),
                        COLORE_STATO.get(m.get("stato"), ANTRACITE),
                    ),
                    (
                        ("💰 " + _fmt_eur(m.get("importo")))
                        if m.get("pagamento") and pack.get("economia")
                        else ("💰" if m.get("pagamento") else "")
                    ),
                ]
                for m in pack["milestone"]
            ],
            larghezze=[6, 2, 2, 2],
        )
    righe: list[list] = []
    for dv in pack.get("deliverables", []):
        righe.append(
            _riga_albero(
                0,
                "📦 " + dv["titolo"] + (f" ({dv['tipo']})" if dv.get("tipo") else ""),
                dv.get("stato"),
                dv.get("scadenza"),
                dv.get("owner"),
                oggi,
            )
        )
        for t in dv.get("tasks", []):
            righe.append(
                _riga_albero(
                    1,
                    t["titolo"],
                    t.get("stato"),
                    t.get("scadenza"),
                    t.get("owner"),
                    oggi,
                )
            )
            for s_ in t.get("subtasks", []):
                righe.append(
                    _riga_albero(
                        2,
                        s_["titolo"],
                        s_.get("stato"),
                        s_.get("scadenza"),
                        s_.get("owner"),
                        oggi,
                    )
                )
    for t in pack.get("task_liberi", []):
        righe.append(
            _riga_albero(
                1, t["titolo"], t.get("stato"), t.get("scadenza"), t.get("owner"), oggi
            )
        )
    if righe:
        d.tabella(
            "Deliverable, task e subtask",
            ["Elemento", "Stato", "Scadenza", "Owner"],
            righe,
            larghezze=[6.5, 1.6, 1.6, 2.4],
            max_righe=13,
        )
    if pack.get("economia") and pack.get("flussi"):
        d.tabella(
            "Calendario dei movimenti previsti",
            ["Descrizione", "Tipo", "Importo", "Data attesa", "Stato"],
            [
                [
                    f["descrizione"] or "—",
                    "entrata" if f["segno"] == "entrata" else "uscita",
                    _fmt_eur(f["importo"]),
                    _fmt_data(f.get("data")),
                    (
                        ("completato", VERDE)
                        if f.get("completata")
                        else ("previsto", GRIGIO)
                    ),
                ]
                for f in pack["flussi"]
            ],
            larghezze=[5, 1.5, 2, 2, 1.6],
        )
    if pack.get("ore_persone"):
        anni = pack.get("anni_ore", [])
        header = ["Persona", "Pianificate"] + [str(a) for a in anni] + ["Consuntivo"]
        d.tabella(
            "Ore per persona (piano per anno vs consuntivo)",
            header,
            [
                [p["nome"], f"{p.get('pianificate', 0):g}"]
                + [f"{p.get('anni', {}).get(a, 0):g}" for a in anni]
                + [f"{p.get('consuntivo', 0):g}"]
                for p in pack["ore_persone"]
            ],
        )
    d.chiusura(pack.get("chiusura", "Grazie"))
    return d.bytes()


def build_report_personale(pack: dict) -> bytes:
    """Deck «Le mie attività»: struttura pensata perché una persona presenti
    il proprio lavoro (equivalente del «My status» di MAIC tasks).

    Sequenza: sintesi → cosa ho completato → su cosa sto lavorando (per
    progetto) → i miei deliverable → cosa mi blocca e cosa scade.
    """
    oggi = pack.get("oggi") or date.today()
    giorni = pack.get("periodo_giorni", 90)
    d = Deck()
    d.titolo(
        pack.get("titolo", "Le mie attività"),
        pack.get("sottotitolo", ""),
        pack.get("meta", ""),
    )
    s = pack.get("sintesi", {})
    d.kpi(
        "In sintesi",
        [
            (str(s.get("attivi", 0)), "Task attivi", "assegnati a me"),
            (
                str(s.get("completati_periodo", 0)),
                "Completati",
                f"ultimi {giorni} giorni",
                VERDE,
            ),
            (
                str(s.get("in_ritardo", 0)),
                "In ritardo",
                "oltre la scadenza",
                ROSSO if s.get("in_ritardo") else VERDE,
            ),
            (s.get("puntualita") or "—", "Puntualità", "completati entro la scadenza"),
            (f"{s.get('ore_stimate', 0):g} h", "Ore stimate", "sui task attivi"),
            (str(s.get("deliverable", 0)), "Deliverable", "di cui sono responsabile"),
            (
                str(s.get("bloccati", 0)),
                "Bloccati",
                "in attesa di qualcosa",
                AMBRA if s.get("bloccati") else GRIGIO,
            ),
            (str(s.get("supervisionati", 0)), "Supervisionati", "task di altri"),
        ],
    )

    d.sezione(1, "Cosa ho completato", f"Ultimi {giorni} giorni")
    d.tabella(
        "Task completati",
        ["Task", "Progetto", "Deliverable", "Chiuso il", "Esito"],
        [
            [
                t["titolo"],
                t.get("progetto", ""),
                t.get("deliverable", "—"),
                _fmt_data(t.get("completato_il")),
                (
                    ("in tempo", VERDE)
                    if t.get("in_tempo") is True
                    else (("in ritardo", ROSSO) if t.get("in_tempo") is False else "—")
                ),
            ]
            for t in pack.get("completati", [])
        ],
        larghezze=[5.0, 2.2, 2.4, 1.3, 1.3],
        nota=pack.get("nota_completati", ""),
    )

    d.sezione(2, "Su cosa sto lavorando", "Task attivi, per progetto")
    progetti = pack.get("progetti", [])
    if not progetti:
        d.contenuto("Task attivi", ["Nessun task attivo assegnato."])
    for prog in progetti:
        d.tabella(
            prog["etichetta"],
            ["Task", "Stato", "Scadenza", "Deliverable"],
            [
                [
                    ("   ↳ " if t.get("subtask") else "") + t["titolo"],
                    (
                        STATO_TXT.get(t.get("stato"), t.get("stato", "")),
                        COLORE_STATO.get(t.get("stato"), ANTRACITE),
                    ),
                    (
                        _fmt_data(t.get("scadenza")),
                        (
                            ROSSO
                            if isinstance(t.get("scadenza"), date)
                            and t["scadenza"] < oggi
                            else ANTRACITE
                        ),
                    ),
                    t.get("deliverable", "—"),
                ]
                for t in prog.get("task", [])
            ],
            larghezze=[5.6, 1.7, 1.7, 3.2],
            nota=prog.get("nota", ""),
        )

    d.sezione(3, "I miei deliverable", "Prototipi, report e paper che devo produrre")
    d.tabella(
        "Deliverable di cui sono responsabile",
        ["Deliverable", "Tipo", "Progetto", "Stato", "Scadenza", "Avanzamento"],
        [
            [
                x["titolo"],
                x.get("tipo", "—"),
                x.get("progetto", ""),
                (
                    STATO_TXT.get(x.get("stato"), x.get("stato", "")),
                    COLORE_STATO.get(x.get("stato"), ANTRACITE),
                ),
                (
                    _fmt_data(x.get("scadenza")),
                    (
                        ROSSO
                        if isinstance(x.get("scadenza"), date) and x["scadenza"] < oggi
                        else ANTRACITE
                    ),
                ),
                x.get("avanzamento", "—"),
            ]
            for x in pack.get("deliverables", [])
        ],
        larghezze=[3.8, 1.3, 2.2, 1.5, 1.4, 2.0],
    )

    d.sezione(4, "Blocchi e prossime scadenze", "Dove serve una decisione")
    d.due_colonne(
        "Cosa mi blocca · cosa scade",
        ("Da sbloccare", pack.get("bloccati", []) or ["Nessun task bloccato."]),
        (
            "Prossime scadenze",
            pack.get("scadenze", []) or ["Nessuna scadenza nei prossimi 60 giorni."],
        ),
    )
    d.chiusura(pack.get("chiusura", "Grazie"))
    return d.bytes()
