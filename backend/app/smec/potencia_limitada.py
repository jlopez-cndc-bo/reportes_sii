"""Potencia limitada (eventos 153) frente a la potencia efectiva y a lo medido.

Sólo se compara con datos concretos: la potencia efectiva por unidad del
archivo semestral del CNDC (no está en Oracle) y el medidor propio de la
unidad en SMEC. Si falta alguno, la celda queda vacía.
"""
from datetime import datetime, timedelta
from typing import Any

from ..db import query
from ..potencia_efectiva import efectiva
from ..sqlutil import in_clause


def _max_medido(muestras: list[tuple[datetime, float]], desde: datetime,
                hasta: datetime) -> float | None:
    """Máximo (kW) de las muestras de 15 min que se superponen con [desde, hasta)."""
    vals = [p for ini, p in muestras
            if p is not None and ini < hasta and ini + timedelta(minutes=15) > desde]
    return max(vals) if vals else None


def potencia_limitada(f1: datetime, f2: datetime) -> dict[str, Any]:
    fin = datetime.combine(f2.date() + timedelta(days=1), datetime.min.time())
    eventos = query("""
        SELECT e.id_elemento, u.codigo_objeto unidad,
               (SELECT MAX(c.codigo_objeto) FROM objetos_objetos oo, objetos c
                 WHERE oo.ob_id_objeto_primario = e.id_elemento
                   AND oo.cte_elemento_primario = 'GENERADOR'
                   AND oo.cte_elemento_secundario = 'CENTRAL'
                   AND c.id_objeto = oo.ob_id_objeto_secundario) central,
               e.fecha, e.hora_ingreso, e.hora_salida, e.potencia_limitada, e.causa
          FROM dc_eventos e, objetos u
         WHERE e.id_tipo_operacion = 153
           AND e.fecha >= TRUNC(:f1) AND e.fecha < :fin
           AND u.id_objeto = e.id_elemento
         ORDER BY central, unidad, e.hora_ingreso""", {"f1": f1, "fin": fin})

    # Medidor propio de cada unidad (relación MEDIDOR→GENERADOR) y sus muestras.
    ids = sorted({e["id_elemento"] for e in eventos})
    medidor: dict[int, int] = {}
    muestras: dict[int, list[tuple[datetime, float]]] = {}
    if ids:
        sql_ids, b = in_clause(ids)
        for r in query(f"""SELECT oo.ob_id_objeto_secundario uni, MIN(oo.ob_id_objeto_primario) med
                             FROM objetos_objetos oo
                            WHERE oo.ob_id_objeto_secundario IN {sql_ids}
                              AND oo.cte_elemento_primario = 'MEDIDOR'
                            GROUP BY oo.ob_id_objeto_secundario
                           HAVING COUNT(*) = 1""", b):
            medidor[r["uni"]] = r["med"]
    if medidor:
        sql_m, b = in_clause(sorted(set(medidor.values())))
        b.update({"f1": f1, "fin": fin})
        for r in query(f"""SELECT id, fecha, intervalo, potencia FROM smec.sm_potencia_med_intervalo
                            WHERE id IN {sql_m} AND fecha >= TRUNC(:f1) AND fecha < :fin""", b):
            ini = r["fecha"] + timedelta(minutes=15 * (r["intervalo"] - 1))
            muestras.setdefault(r["id"], []).append((ini, r["potencia"]))

    out = []
    for e in eventos:
        desde = e["hora_ingreso"]
        hasta = e["hora_salida"] or min(fin, datetime.now())
        lim = e["potencia_limitada"]
        pe = efectiva(e["unidad"], e["fecha"].date())
        med = medidor.get(e["id_elemento"])
        mx = _max_medido(muestras.get(med, []), desde, hasta) if med else None
        out.append({
            "central": e["central"], "unidad": e["unidad"],
            "desde": desde, "hasta": e["hora_salida"],
            "horas": round((hasta - desde).total_seconds() / 3600, 2),
            "limite": lim, "efectiva": pe,
            "reduccion": round(pe - lim, 6) if pe is not None and lim is not None else None,
            "pct_efectiva": round(lim * 100 / pe, 10) if pe and lim is not None else None,
            "medido": round(mx / 1000, 6) if mx is not None else None,
            "causa": e["causa"],
        })
    columns = [
        {"key": "central", "label": "Central"},
        {"key": "unidad", "label": "Unidad"},
        {"key": "desde", "label": "Desde", "format": "datetime"},
        {"key": "hasta", "label": "Hasta", "format": "datetime"},
        {"key": "horas", "label": "Horas", "format": "0.00"},
        {"key": "efectiva", "label": "Pot. efectiva (MW)", "format": "num", "sinTotal": True},
        {"key": "limite", "label": "Límite (MW)", "format": "num", "sinTotal": True},
        {"key": "reduccion", "label": "Reducción (MW)", "format": "num", "sinTotal": True},
        {"key": "pct_efectiva", "label": "Límite (% efectiva)", "format": "0.0", "sinTotal": True},
        {"key": "medido", "label": "Máx. medido (MW)", "format": "num", "sinTotal": True},
        {"key": "causa", "label": "Causa"},
    ]
    return {"table": "POT_LIMITADA", "columns": columns, "rows": out,
            "aviso": "Pot. efectiva: tabla semestral del CNDC (desde 01/11/2026). "
                     "Máx. medido: medidor propio de la unidad en SMEC, convertido a MW; "
                     "se mide en bloques de 15 min, así que en eventos cortos incluye "
                     "minutos de antes o después del evento. "
                     "Sin dato concreto, la celda muestra «-». "
                     "El TOTAL de Horas suma las horas de todos los eventos."}
