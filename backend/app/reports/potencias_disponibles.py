"""Reporte 1: Potencias / Disponibilidad por Unidad, Central o Agente.

Traduce INDISP.PotenciasDisponibles. Usa las funciones PL/SQL:
  ri_disponibilidad_unidad(f1, f2, gen), ri_get_potencia_unidad(f1, f2, gen),
  ri_get_central(id), ri_get_AGENTE(id).

Resiliencia: varias funciones PL/SQL de la base fallan con ORA-06503 para
ciertos generadores nuevos. Los tres niveles intentan primero la consulta
rápida (idéntica al original) y, si falla, recalculan generador por generador
omitiendo los que rompen, para no tumbar todo el reporte.
"""
from datetime import datetime
from typing import Any

import oracledb

from ..db import query
from ..sqlutil import in_clause


def _rango(f1: datetime, f2: datetime) -> tuple[datetime, datetime]:
    ini = f1.replace(hour=0, minute=0, second=0, microsecond=0)
    fin = f2.replace(hour=23, minute=59, second=59, microsecond=0)
    return ini, fin


def _dispo_pot(ini: datetime, fin: datetime, gen: int) -> tuple[Any, Any] | None:
    """Disponibilidad y potencia de un generador. None si la función PL/SQL falla."""
    try:
        r = query(
            """SELECT ROUND(ri_disponibilidad_unidad(:f1, :f2, :g), 2) d,
                      ROUND(ri_get_potencia_unidad(:f1, :f2, :g), 2) p
                 FROM dual""",
            {"f1": ini, "f2": fin, "g": gen},
        )
        return r[0]["d"], r[0]["p"]
    except oracledb.DatabaseError:
        return None


# ---------------------------------------------------------------- UNIDAD

_SQL_UNIDAD = """
    SELECT ROUND(ri_disponibilidad_unidad(:f1, :f2, id_objeto), 2) disponibilidad,
           ROUND(ri_get_potencia_unidad(:f1, :f2, id_objeto), 2)   potencia,
           codigo_objeto,
           ri_get_central(id_objeto) cen,
           ri_get_agente(id_objeto)  ag
      FROM objetos
     WHERE id_objeto IN {in_sql}
"""

_COLS_UNIDAD = [
    {"key": "ag", "label": "Agente"},
    {"key": "cen", "label": "Central"},
    {"key": "codigo_objeto", "label": "Unidad"},
    {"key": "disponibilidad", "label": "Disponibilidad (%)", "format": "0.00"},
    {"key": "potencia", "label": "Potencia (MW)", "format": "0.00"},
]


def report_unidad(f1: datetime, f2: datetime, unidades: list[int]) -> dict[str, Any]:
    ini, fin = _rango(f1, f2)
    in_sql, binds = in_clause(unidades)
    binds.update({"f1": ini, "f2": fin})
    try:
        rows = query(_SQL_UNIDAD.format(in_sql=in_sql), binds)
        return {"table": "UNIDAD", "columns": _COLS_UNIDAD, "rows": rows}
    except oracledb.DatabaseError:
        pass

    # Fallback fila por fila: se listan TODAS las unidades. Si una función
    # PL/SQL falla (ORA-06503), esa unidad aparece igual con '-' en los campos
    # que no se pudieron calcular, en vez de omitirla.
    rows: list[dict[str, Any]] = []
    sin_dato = 0
    for e in unidades:
        base = query("SELECT codigo_objeto FROM objetos WHERE id_objeto = :e", {"e": e})
        codigo = base[0]["codigo_objeto"] if base else str(e)
        disp = pot = None
        try:
            r = query(
                """SELECT ROUND(ri_disponibilidad_unidad(:f1, :f2, :e), 2) d,
                          ROUND(ri_get_potencia_unidad(:f1, :f2, :e), 2)   p
                     FROM dual""",
                {"f1": ini, "f2": fin, "e": e},
            )
            disp, pot = r[0]["d"], r[0]["p"]
        except oracledb.DatabaseError:
            sin_dato += 1
        cen = ag = None
        try:
            x = query("SELECT ri_get_central(:e) cen, ri_get_agente(:e) ag FROM dual", {"e": e})
            cen, ag = x[0]["cen"], x[0]["ag"]
        except oracledb.DatabaseError:
            pass
        rows.append({"ag": ag, "cen": cen, "codigo_objeto": codigo,
                     "disponibilidad": disp, "potencia": pot})
    result = {"table": "UNIDAD", "columns": _COLS_UNIDAD, "rows": rows}
    if sin_dato:
        result["aviso"] = (
            f"{sin_dato} unidad(es) se listan sin disponibilidad/potencia: una "
            f"función PL/SQL de la base falló (ORA-06503) al calcularlas."
        )
    return result


# --------------------------------------------------- CENTRAL / AGENTE (comunes)

def _agregar_por_central(mapping: list[dict[str, Any]], ini: datetime, fin: datetime):
    """Promedio ponderado de disponibilidad por central, generador a generador.

    mapping: filas {gen, cen}. Devuelve (acc, omitidas) donde acc[cen] = [Σdp, Σpot].
    """
    acc: dict[Any, list[float]] = {}
    omitidas = 0
    for m in mapping:
        res = _dispo_pot(ini, fin, int(m["gen"]))
        if res is None:
            omitidas += 1
            continue
        d, p = res
        if d is None or p is None:
            continue
        a = acc.setdefault(m["cen"], [0.0, 0.0])
        a[0] += d * p
        a[1] += p
    return acc, omitidas


def _nombres_central(cen_ids: list[int]) -> dict[int, dict[str, Any]]:
    """codigo_objeto y agente (guardado) por id de central."""
    if not cen_ids:
        return {}
    in_sql, binds = in_clause(cen_ids, prefix="c")
    rows = query(
        f"SELECT id_objeto, codigo_objeto FROM objetos WHERE id_objeto IN {in_sql}",
        binds,
    )
    info: dict[int, dict[str, Any]] = {}
    for r in rows:
        cid = int(r["id_objeto"])
        agente = None
        try:
            ag = query("SELECT ri_get_agente(:c) a FROM dual", {"c": cid})
            agente = ag[0]["a"]
        except oracledb.DatabaseError:
            agente = None
        info[cid] = {"codigo_objeto": r["codigo_objeto"], "agente": agente}
    return info


def _resultado_central(acc, omitidas, con_agente: bool, tabla: str) -> dict[str, Any]:
    cen_ids = [int(c) for c in acc.keys()]
    nombres = _nombres_central(cen_ids)
    rows = []
    for cen, (sdp, spot) in acc.items():
        cid = int(cen)
        n = nombres.get(cid, {})
        fila = {
            "codigo_objeto": n.get("codigo_objeto"),
            "dp": round(sdp / spot, 2) if spot else None,
        }
        if con_agente:
            fila["agente"] = n.get("agente")
        rows.append(fila)
    rows.sort(key=lambda x: (x.get("agente") or "", x.get("codigo_objeto") or ""))
    columns = []
    if con_agente:
        columns.append({"key": "agente", "label": "Agente"})
    columns += [
        {"key": "codigo_objeto", "label": "Central"},
        {"key": "dp", "label": "Disponibilidad (%)", "format": "0.00"},
    ]
    result = {"table": tabla, "columns": columns, "rows": rows}
    if omitidas:
        result["aviso"] = (
            f"{omitidas} generador(es) omitido(s) del promedio: una función PL/SQL "
            f"de la base falló (ORA-06503)."
        )
    return result


def report_central(f1: datetime, f2: datetime, unidades: list[int]) -> dict[str, Any]:
    ini, fin = _rango(f1, f2)
    in_sql, binds = in_clause(unidades)
    binds.update({"f1": ini, "f2": fin})
    sql = f"""
        SELECT dp, codigo_objeto, ri_get_agente(id_objeto) agente
          FROM (SELECT ROUND(SUM(dispo * pot) / SUM(pot), 2) dp, cen
                  FROM (SELECT ROUND(ri_disponibilidad_unidad(:f1, :f2, gen), 2) dispo,
                               ROUND(ri_get_potencia_unidad(:f1, :f2, gen), 2)  pot,
                               codigo_objeto, cen, id_objeto
                          FROM (SELECT DISTINCT (ob_id_objeto_primario) gen,
                                                ob_id_objeto_secundario cen
                                  FROM objetos_objetos
                                 WHERE ob_id_objeto_secundario IN {in_sql}
                                   AND cte_elemento_primario = 'GENERADOR'),
                               objetos
                         WHERE id_objeto = gen AND cte_equival = 'REAL') w
                 GROUP BY cen) w,
               objetos o
         WHERE w.cen = o.id_objeto
    """
    try:
        rows = query(sql, binds)
        columns = [
            {"key": "agente", "label": "Agente"},
            {"key": "codigo_objeto", "label": "Central"},
            {"key": "dp", "label": "Disponibilidad (%)", "format": "0.00"},
        ]
        return {"table": "CENTRAL", "columns": columns, "rows": rows}
    except oracledb.DatabaseError:
        pass

    map_sql, mb = in_clause(unidades)
    mapping = query(
        f"""SELECT DISTINCT oo.ob_id_objeto_primario gen, oo.ob_id_objeto_secundario cen
              FROM objetos_objetos oo, objetos g
             WHERE oo.ob_id_objeto_secundario IN {map_sql}
               AND oo.cte_elemento_primario = 'GENERADOR'
               AND g.id_objeto = oo.ob_id_objeto_primario
               AND g.cte_equival = 'REAL'""",
        mb,
    )
    acc, omit = _agregar_por_central(mapping, ini, fin)
    return _resultado_central(acc, omit, con_agente=True, tabla="CENTRAL")


def report_agente(f1: datetime, f2: datetime, unidades: list[int]) -> dict[str, Any]:
    ini, fin = _rango(f1, f2)
    in_sql, binds = in_clause(unidades)
    binds.update({"f1": ini, "f2": fin})
    sql = f"""
        SELECT dp, codigo_objeto
          FROM (SELECT ROUND(SUM(dispo * pot) / SUM(pot), 2) dp, cen
                  FROM (SELECT ROUND(ri_disponibilidad_unidad(:f1, :f2, gen), 2) dispo,
                               ROUND(ri_get_potencia_unidad(:f1, :f2, gen), 2)  pot,
                               codigo_objeto, cen, id_objeto
                          FROM (SELECT DISTINCT (cen.ob_id_objeto_primario) gen,
                                                ag.ob_id_objeto_secundario cen
                                  FROM objetos_objetos cen, objetos_objetos ag
                                 WHERE ag.ob_id_objeto_secundario IN {in_sql}
                                   AND ag.cte_elemento_primario = 'CENTRAL'
                                   AND cen.cte_elemento_primario = 'GENERADOR'
                                   AND cen.ob_id_objeto_secundario = ag.ob_id_objeto_primario),
                               objetos
                         WHERE id_objeto = gen AND cte_equival = 'REAL') w
                 GROUP BY cen) w,
               objetos o
         WHERE w.cen = o.id_objeto
    """
    try:
        rows = query(sql, binds)
        columns = [
            {"key": "codigo_objeto", "label": "Central"},
            {"key": "dp", "label": "Disponibilidad (%)", "format": "0.00"},
        ]
        return {"table": "AGENTE", "columns": columns, "rows": rows}
    except oracledb.DatabaseError:
        pass

    map_sql, mb = in_clause(unidades)
    mapping = query(
        f"""SELECT DISTINCT cen.ob_id_objeto_primario gen, ag.ob_id_objeto_secundario cen
              FROM objetos_objetos cen, objetos_objetos ag, objetos g
             WHERE ag.ob_id_objeto_secundario IN {map_sql}
               AND ag.cte_elemento_primario = 'CENTRAL'
               AND cen.cte_elemento_primario = 'GENERADOR'
               AND cen.ob_id_objeto_secundario = ag.ob_id_objeto_primario
               AND g.id_objeto = cen.ob_id_objeto_primario
               AND g.cte_equival = 'REAL'""",
        mb,
    )
    acc, omit = _agregar_por_central(mapping, ini, fin)
    return _resultado_central(acc, omit, con_agente=False, tabla="AGENTE")


def report(nivel: str, f1: datetime, f2: datetime, unidades: list[int]) -> dict[str, Any]:
    nivel = nivel.lower()
    if nivel == "central":
        return report_central(f1, f2, unidades)
    if nivel == "agente":
        return report_agente(f1, f2, unidades)
    return report_unidad(f1, f2, unidades)
