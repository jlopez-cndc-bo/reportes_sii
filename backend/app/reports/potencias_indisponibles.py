"""Reporte 2: Potencias Indisponibles pivoteadas por intervalo de tiempo.

Traduce INDISP.Potencias_Indisponibles (Get_SQL + ToInterval + GetTableStyle).
El SQL devuelve eventos con su intervalo de ingreso/salida (índices absolutos
desde f1) y ToInterval los "pinta" en columnas I0..I(n-1).

Resiliencia: algunas funciones PL/SQL de la base (ri_get_potencia →
ri_potencia_hidro) fallan con ORA-06503 para ciertos generadores. Para no
tumbar todo el reporte se intenta primero la consulta rápida y, si falla, se
resuelve la potencia unidad por unidad omitiendo las que la función rompe.
"""
from datetime import datetime, timedelta
from typing import Any

import oracledb

from ..constants import Resolucion, TipoOperacion
from ..db import query
from ..sqlutil import in_clause

# Límite de columnas para evitar reportes gigantes (como el guard de la UI).
MAX_COLUMNAS = 1500

# Expresiones de índice de intervalo reutilizadas (ingreso / salida).
#
# El resto de minutos usa CEIL (no TRUNC): el intervalo de 15' que contiene el
# minuto exacto de ingreso/salida no cuenta como indisponible salvo que el
# evento lo cubra desde su propio inicio. Con TRUNC, un ingreso a las 09:02
# marcaba desde las 09:00 (adelantado) y una salida a las 11:40 cortaba en
# las 11:15 (recortado); con CEIL marcan 09:15 y 11:30 respectivamente,
# verificado contra SII con los eventos reales de ANG02/AGU01 (2026-10-12).
# Un ingreso/salida ya alineado a un múltiplo de 15' (resto 0) no se desplaza
# (CEIL(0/n) = 0).
_INTER = """
       TRUNC(((24 * 60 / :intervalo) * (TRUNC(hora_ingreso) - TRUNC(:f1)))
             + (TO_CHAR(hora_ingreso, 'HH24') * (60 / :intervalo))
             + CEIL((TO_CHAR(hora_ingreso, 'mi')) / :intervalo)) inter_ingreso,
       TRUNC(((24 * 60 / :intervalo) * (TRUNC(NVL(hora_salida, SYSDATE)) - TRUNC(:f1)))
             + (TO_CHAR(NVL(hora_salida, SYSDATE), 'HH24') * (60 / :intervalo))
             + CEIL((TO_CHAR(NVL(hora_salida, SYSDATE), 'mi')) / :intervalo)) intersalida
"""

_SUBQ = """
  FROM (SELECT id_elemento, fecha, id_tipo_operacion,
               NVL(e.hora_salida, SYSDATE) hora_salida, e.hora_ingreso,
               (NVL(e.hora_salida, SYSDATE) - e.hora_ingreso) * 1440 / :intervalo delta
          FROM dc_eventos e
         WHERE fecha BETWEEN TRUNC(:f1) AND TRUNC(:f2)
           AND e.id_tipo_operacion IN (:pro, :forz)
           AND id_elemento IN {in_sql}) k,
       objetos o
 WHERE o.id_objeto = k.id_elemento
   AND o.cte_elemento = 'GENERADOR'
   AND delta >= 1
 ORDER BY codigo_objeto, hora_ingreso
"""

# Camino rápido: potencia calculada en la misma consulta.
_SQL_RAPIDO = """
SELECT id_elemento,
       ri_get_potencia(fecha, id_elemento) potencia,
       o.codigo_objeto,
       fecha,
""" + _INTER + _SUBQ

# Camino resiliente: eventos sin la función de potencia.
_SQL_EVENTOS = """
SELECT id_elemento,
       o.codigo_objeto,
       fecha,
""" + _INTER + _SUBQ


def _num_columnas(f1: datetime, f2: datetime, tipo: Resolucion, intervalo: int) -> int:
    dias = abs((f2.date() - f1.date()).days) + 1
    if tipo == Resolucion.INTERVALO:
        return round(dias * 24 * 60 / intervalo)
    if tipo == Resolucion.HORA:
        h = round(intervalo / 60)
        return round(dias * 24 / max(h, 1))
    return round(dias / max(intervalo, 1))  # DIA


def _resolver_potencia(binds: dict[str, Any], unidades: list[int]) -> tuple[dict, list[int]]:
    """Potencia por (id_elemento, fecha), resuelta unidad por unidad.

    Devuelve (mapa, unidades_omitidas). Las unidades cuya función PL/SQL falla
    se omiten (su potencia queda desconocida → None).
    """
    potmap: dict[tuple[int, Any], Any] = {}
    omitidas: list[int] = []
    base = {"f1": binds["f1"], "f2": binds["f2"],
            "pro": binds["pro"], "forz": binds["forz"]}
    for e in unidades:
        try:
            rows = query(
                """SELECT fecha, ri_get_potencia(fecha, :e) pot
                     FROM (SELECT DISTINCT fecha FROM dc_eventos
                            WHERE id_elemento = :e
                              AND fecha BETWEEN TRUNC(:f1) AND TRUNC(:f2)
                              AND id_tipo_operacion IN (:pro, :forz))""",
                {**base, "e": e},
            )
            for r in rows:
                potmap[(e, r["fecha"])] = r["pot"]
        except oracledb.DatabaseError:
            omitidas.append(e)
    return potmap, omitidas


def _pivot(rows: list[dict[str, Any]], n_cols: int) -> list[dict[str, Any]]:
    """Reproduce ToInterval: una fila por generador con celdas I0..I(n-1)."""
    salida: list[dict[str, Any]] = []
    actual_id: Any = None
    fila: dict[str, Any] | None = None

    for r in rows:
        rid = r["id_elemento"]
        if rid != actual_id:
            if fila is not None:
                salida.append(fila)
            actual_id = rid
            fila = {"codigo_objeto": r["codigo_objeto"]}
            for i in range(n_cols):
                fila[f"I{i}"] = 0

        ini = r.get("inter_ingreso")
        fin = r.get("intersalida")
        if ini is not None and fin is not None and fila is not None:
            pot = r.get("potencia")
            for i in range(int(ini), int(fin)):
                if 0 <= i < n_cols:
                    fila[f"I{i}"] = pot

    if fila is not None:
        salida.append(fila)
    return salida


def _columnas(f1: datetime, n_cols: int, intervalo: int) -> list[dict[str, Any]]:
    cols: list[dict[str, Any]] = [{"key": "codigo_objeto", "label": "Generador"}]
    t = f1.replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(n_cols):
        muestra_fecha = (t - timedelta(minutes=intervalo)).day != t.day
        label = t.strftime("%d/%m/%Y %H:%M") if muestra_fecha else t.strftime("%H:%M")
        cols.append({"key": f"I{i}", "label": label, "format": "0.0"})
        t += timedelta(minutes=intervalo)
    return cols


def report(
    f1: datetime,
    f2: datetime,
    tipo: Resolucion,
    intervalo: int,
    unidades: list[int],
    ip: bool = True,
    inf: bool = True,
) -> dict[str, Any]:
    n_cols = _num_columnas(f1, f2, tipo, intervalo)
    if n_cols > MAX_COLUMNAS:
        raise ValueError(
            f"El reporte solicitaría {n_cols} columnas. Reduzca el rango de fechas "
            f"o aumente el intervalo (máx {MAX_COLUMNAS})."
        )

    in_sql, binds = in_clause(unidades)
    binds.update(
        {
            "f1": f1.replace(hour=0, minute=0, second=0, microsecond=0),
            "f2": f2.replace(hour=0, minute=0, second=0, microsecond=0),
            "intervalo": intervalo,
            "pro": TipoOperacion.PROGRAMADA if ip else 0,
            "forz": TipoOperacion.FORZADA if inf else 0,
        }
    )

    aviso: str | None = None
    try:
        rows = query(_SQL_RAPIDO.format(in_sql=in_sql), binds)
    except oracledb.DatabaseError:
        # Fallback resiliente: eventos + potencia unidad por unidad.
        rows = query(_SQL_EVENTOS.format(in_sql=in_sql), binds)
        potmap, omitidas = _resolver_potencia(binds, unidades)
        for r in rows:
            r["potencia"] = potmap.get((r["id_elemento"], r["fecha"]))
        if omitidas:
            aviso = (
                f"{len(omitidas)} generador(es) sin potencia disponible "
                f"(función ri_get_potencia falló en la base); se muestran como '-'."
            )

    filas = _pivot(rows, n_cols)
    columns = _columnas(f1, n_cols, intervalo)
    result = {"table": "DIA", "columns": columns, "rows": filas}
    if aviso:
        result["aviso"] = aviso
    return result
