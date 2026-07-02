"""Query aggregate per i report per dipendente (carico, ferie, presenze, ore)."""

from __future__ import annotations

from src.lib import db


def task_stats(anno: int) -> dict[str, dict]:
    """Per persona (owner): task attivi, completati nell'anno, in ritardo,
    puntualità (% completati entro scadenza), ore stimate attive."""
    rows = db.query(
        """
        select owner_id,
          count(*) filter (
              where stato in ('da_fare','in_corso','bloccato') and not archiviato
          ) as attivi,
          count(*) filter (
              where stato = 'completato'
                and extract(year from completato_il)::int = %(a)s
          ) as completati_anno,
          count(*) filter (
              where stato in ('da_fare','in_corso','bloccato')
                and not archiviato and scadenza < current_date
          ) as in_ritardo,
          coalesce(sum(ore_stimate) filter (
              where stato in ('da_fare','in_corso','bloccato') and not archiviato
          ), 0) as ore_stimate,
          count(*) filter (
              where stato = 'completato' and completato_il is not null
                and scadenza is not null
          ) as compl_con_scad,
          count(*) filter (
              where stato = 'completato' and completato_il is not null
                and scadenza is not null and completato_il <= scadenza
          ) as compl_puntuali
        from task
        where owner_id is not null
        group by owner_id
        """,
        {"a": anno},
    )
    out = {}
    for r in rows:
        con = int(r["compl_con_scad"])
        out[str(r["owner_id"])] = {
            "attivi": int(r["attivi"]),
            "completati_anno": int(r["completati_anno"]),
            "in_ritardo": int(r["in_ritardo"]),
            "ore_stimate": float(r["ore_stimate"] or 0),
            "puntualita": (int(r["compl_puntuali"]) / con * 100) if con else None,
        }
    return out


def ferie_permessi(anno: int) -> dict[str, dict]:
    """Per persona: giorni lavorativi di ferie/malattia e ore di permesso
    (assenze APPROVATE che intersecano l'anno)."""
    giorni = db.query(
        """
        select persona_id, tipo, count(*) as gg
        from (
            select a.persona_id, a.tipo, gs::date as g
            from assenza a,
                 generate_series(
                     greatest(a.data_inizio, make_date(%(a)s, 1, 1)),
                     least(a.data_fine, make_date(%(a)s, 12, 31)),
                     interval '1 day'
                 ) gs
            where a.stato = 'approvata' and a.tipo in ('ferie','malattia')
        ) x
        where extract(isodow from g) < 6
        group by persona_id, tipo
        """,
        {"a": anno},
    )
    permessi = db.query(
        """
        select persona_id, coalesce(sum(ore_o_giorni), 0) as ore
        from assenza
        where stato = 'approvata' and tipo = 'permesso'
          and extract(year from data_inizio)::int = %(a)s
        group by persona_id
        """,
        {"a": anno},
    )
    out: dict[str, dict] = {}
    for r in giorni:
        d = out.setdefault(
            str(r["persona_id"]), {"ferie": 0, "malattia": 0, "permessi_h": 0.0}
        )
        d[r["tipo"]] = int(r["gg"])
    for r in permessi:
        d = out.setdefault(
            str(r["persona_id"]), {"ferie": 0, "malattia": 0, "permessi_h": 0.0}
        )
        d["permessi_h"] = float(r["ore"] or 0)
    return out


def presenze_stats(anno: int) -> dict[str, dict]:
    """Per persona: giorni di presenza registrati, ore totali, ore medie/giorno."""
    rows = db.query(
        """
        select persona_id, count(*) as giorni,
               coalesce(sum(ore_totali), 0) as ore_tot,
               coalesce(avg(ore_totali) filter (where ore_totali is not null), 0)
                   as ore_medie
        from presenza
        where extract(year from data)::int = %(a)s
        group by persona_id
        """,
        {"a": anno},
    )
    return {
        str(r["persona_id"]): {
            "giorni": int(r["giorni"]),
            "ore_tot": float(r["ore_tot"] or 0),
            "ore_medie": float(r["ore_medie"] or 0),
        }
        for r in rows
    }


def timesheet_ore(anno: int) -> dict[str, float]:
    """Per persona: ore progettuali totali a timesheet nell'anno."""
    rows = db.query(
        """
        select persona_id, coalesce(sum(ore), 0) as ore
        from timesheet_ora
        where extract(year from data)::int = %(a)s
        group by persona_id
        """,
        {"a": anno},
    )
    return {str(r["persona_id"]): float(r["ore"] or 0) for r in rows}


def report_dipendenti(anno: int, persone: list) -> list[dict]:
    """Riga di report per ciascuna persona attiva, con tutte le metriche."""
    ts = task_stats(anno)
    fp = ferie_permessi(anno)
    pr = presenze_stats(anno)
    to = timesheet_ore(anno)
    out = []
    for p in persone:
        pid = str(p.id)
        t = ts.get(pid, {})
        f = fp.get(pid, {})
        pre = pr.get(pid, {})
        out.append(
            {
                "persona": p.nome_completo,
                "task_attivi": t.get("attivi", 0),
                "completati_anno": t.get("completati_anno", 0),
                "in_ritardo": t.get("in_ritardo", 0),
                "ore_stimate": t.get("ore_stimate", 0.0),
                "puntualita": t.get("puntualita"),
                "ferie_gg": f.get("ferie", 0),
                "malattia_gg": f.get("malattia", 0),
                "permessi_h": f.get("permessi_h", 0.0),
                "presenze_gg": pre.get("giorni", 0),
                "ore_medie_gg": pre.get("ore_medie", 0.0),
                "ore_progettuali": to.get(pid, 0.0),
            }
        )
    return out
