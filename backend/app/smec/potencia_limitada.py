"""Potencia limitada (eventos 153) frente a la potencia efectiva y a lo medido.

Sólo se compara con datos concretos: la potencia efectiva por unidad del
archivo semestral del CNDC (no está en Oracle) y el medidor propio de la
unidad en SMEC. Si falta alguno, la celda queda vacía.
"""
from datetime import date, datetime, timedelta
from typing import Any

from ..db import query
from ..sqlutil import in_clause

# Potencia efectiva por unidad (MW; térmicas a temperatura media), por vigencia.
# Fuente: «Potencia efectiva noviembre 2026 - abril 2027» (01_Nov26_Abr27.xlsx).
# Ciclos combinados con su valor CC (WARxy→CCWARxy, ERIxy→CCERIxy, SURxy→CCSURxy,
# GCH09/10→GCHxxCOM; las x0 son el bloque). ERI01-04 = Entre Ríos 11/12/21/22 y
# WAR05 = Warnes 51 (confirmado por Operación 2026-11-19). GCH12 (vapor) depende
# del estado de operación: sin dato.
# shortcut: tabla a mano por semestre; actualizar cada noviembre y mayo con el
# archivo nuevo (agregar una vigencia, no pisar la anterior).
EFECTIVA: dict[date, dict[str, float]] = {
    date(2026, 11, 1): {
        # Guaracachi
        "GCH01": 18.62, "GCH02": 17.62, "GCH04": 19.95, "GCH06": 20.71, "GCH11": 62.22,
        "GCH09": 102.03, "GCH10": 100.97,
        "GCH09COM": 102.03, "GCH10COM": 100.97, "GCH0910COM": 206.83,
        # Santa Cruz, Valle Hermoso, Aranjuez, Carrasco, El Alto, Bulo Bulo
        "SCZ01": 20.76, "SCZ02": 21.19,
        "VHE02": 18.81, "VHE03": 18.32, "VHE05": 10.58, "VHE06": 10.58, "VHE07": 10.58, "VHE08": 10.58,
        "ARJ01": 2.7, "ARJ02": 2.24, "ARJ03": 2.62, "ARJ08": 18.39, "ARJ09": 1.49, "ARJ11": 1.49,
        "ARJ12": 1.6, "ARJ13": 1.55, "ARJ14": 1.51, "ARJ15": 1.6,
        "CAR01": 53.65, "CAR02": 55.39, "CAR03": 24.32,
        "ALT01": 18.33, "ALT02": 31.62,
        "BUL01": 43.97, "BUL03": 48.82,
        # Entre Ríos
        "ERI01": 28.72, "ERI02": 28.04, "ERI03": 29.13, "ERI04": 28.44,
        "ERI30": 137.42, "ERI31": 68.22, "ERI32": 67.36, "ERI40": 137.56, "ERI41": 67.73,
        "ERI42": 67.56, "ERI50": 137.46, "ERI51": 67.68, "ERI52": 67.46,
        # Termoeléctrica del Sur
        "SUR10": 122.84, "SUR11": 58.31, "SUR12": 58.3, "SUR20": 122.44, "SUR21": 58.44,
        "SUR22": 58.37, "SUR30": 129.05, "SUR31": 63.39, "SUR32": 63.3, "SUR40": 131.5,
        "SUR41": 63.46, "SUR42": 64.36,
        # Warnes
        "WAR05": 44.33,
        "WAR10": 128.35, "WAR11": 64.0, "WAR12": 63.73, "WAR20": 127.5, "WAR21": 64.04,
        "WAR22": 62.91, "WAR30": 135.36, "WAR31": 66.74, "WAR32": 67.09, "WAR40": 135.03,
        "WAR41": 65.8, "WAR42": 66.52,
        # Moxos
        "MOA02": 1.28, "MOA05": 1.1, "MOA06": 1.12, "MOA07": 1.1, "MOA08": 1.1,
        # Bagazo (una unidad por central)
        "GBE01": 21.0, "IAG01": 5.0, "UNA01": 35.0, "AGU01": 4.0, "AGU02": 55.0,
        "AGU03": 52.09, "SBU01": 5.0,
        # Hidroeléctricas con eventos de limitación
        "CAH01": 13.653, "CAH02": 14.364, "HUA01": 15.1, "HUA02": 15.05, "CHJ": 38.4,
        "SIS05": 21.649, "SJA02": 3.8, "SJE02": 34.5,
    },
}
# Hasta cuándo rige la última vigencia cargada (fin del semestre del archivo).
_FIN_ULTIMA = date(2027, 4, 30)


def efectiva(codigo: str, dia: date) -> float | None:
    """Potencia efectiva vigente para la unidad ese día, o None si no hay dato."""
    vig = [v for v in EFECTIVA if v <= dia]
    if not vig or dia > _FIN_ULTIMA:
        return None
    return EFECTIVA[max(vig)].get(codigo)


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
