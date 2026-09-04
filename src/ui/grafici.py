"""Grafici Plotly con la palette ANTECNICA (tema del template 2026).

Colori dal `theme1.xml` di `ANTECNICA_template_2026_v2.pptx`:
accent1 2E8FC0 (azzurro), dk1 0B0F14, accent3 66CCFF, accent4 45535F,
accent5 9BABBA, accent6 E1E6EA, lt2 F4F6F8.
"""

from __future__ import annotations

import plotly.graph_objects as go

AZZURRO = "#2E8FC0"
CIELO = "#66CCFF"
ANTRACITE = "#0B0F14"
GRIGIO = "#45535F"
GRIGIO_CHIARO = "#9BABBA"
NEBBIA = "#E1E6EA"
VERDE = "#2E9E6B"
AMBRA = "#E0A020"
ROSSO = "#D9534F"

PALETTE = [AZZURRO, GRIGIO, CIELO, VERDE, AMBRA, GRIGIO_CHIARO, ROSSO, ANTRACITE]

COLORE_STATO_INIZIATIVA = {
    "Progetto attivo": AZZURRO,
    "Progetto chiuso": GRIGIO_CHIARO,
    "Proposta inviata": AMBRA,
    "Proposta in bozza": CIELO,
}

COLORE_SCENARIO = {"firmato": GRIGIO, "pesato": AZZURRO, "ottimista": CIELO}
NOME_SCENARIO = {
    "firmato": "Solo contratti firmati",
    "pesato": "+ pipeline pesata (× probabilità)",
    "ottimista": "+ pipeline intera",
}


def layout_base(fig: go.Figure, altezza: int | None = None, **kw) -> go.Figure:
    """Layout sobrio e coerente per tutti i grafici dell'app."""
    fig.update_layout(
        template="plotly_white",
        colorway=PALETTE,
        font={"family": "Calibri, Segoe UI, sans-serif", "color": ANTRACITE},
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        legend={"orientation": "h", "y": -0.15, "x": 0},
        hoverlabel={"bgcolor": "white"},
        **kw,
    )
    if altezza:
        fig.update_layout(height=altezza)
    fig.update_xaxes(gridcolor=NEBBIA, zerolinecolor=GRIGIO_CHIARO)
    fig.update_yaxes(gridcolor=NEBBIA, zerolinecolor=GRIGIO_CHIARO)
    return fig
