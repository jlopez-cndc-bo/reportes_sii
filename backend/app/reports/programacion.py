"""Fase 2 Indisp: programación de mantenimiento (dc_prog_mant, solo lectura).

Portado de INDISP/progMant.cs (consulta) y INDISP/Reporte_compracion.cs
(comparación programado vs real). Tipos de programación: 1=diaria,
2=semanal (semana anclada en sábado, como el legacy), 4=mensual.
"""
from datetime import datetime, timedelta
from typing import Any

from ..db import query

TIPO_PROG = {"diario": 1, "semanal": 2, "mensual": 4}


def _ajustar_periodo(fecha: datetime, tipo: str) -> tuple[datetime, int]:
    """Fecha efectiva y días del período, replicando el legacy.

    Semanal: VB Weekday (dom=1..sáb=7); si no es sábado retrocede al sábado
    anterior. Mensual: primer día del mes, días del mes - 1.
    """
    fecha = datetime(fecha.year, fecha.month, fecha.day)
    if tipo == "diario":
        return fecha, 1
    if tipo == "semanal":
        vb = (fecha.weekday() + 1) % 7 + 1  # lun=2 .. sáb=7, dom=1
        if vb != 7:
            fecha -= timedelta(days=vb)
        return fecha, 7
    # mensual
    fecha = fecha.replace(day=1)
    siguiente = (fecha.replace(day=28) + timedelta(days=4)).replace(day=1)
    return fecha, (siguiente - fecha).days - 1


def _periodo_aviso(fecha: datetime, dias: int, tipo: str) -> str:
    fin = fecha + timedelta(days=dias)
    return (f"Programación {tipo}: período {fecha.strftime('%d/%m/%Y')} – "
            f"{fin.strftime('%d/%m/%Y')}")


# ─────────────────────── Consulta de programación ───────────────────────

_SQL_PROG = """
SELECT o.codigo_objeto,
       o.cte_elemento,
       d.fecha,
       d.hora_inicio,
       d.hora_final,
       DECODE(d.tipo_indisp, 155, 'Programada (Mantenimiento)', 'Forzada') tipo_indisp,
       d.causa,
       d.timestamp ts
  FROM dc_prog_mant d, objetos o
 WHERE d.id_objeto = o.id_objeto
   AND d.fecha = TRUNC(:p_fecha)
   AND d.tipo_prog = :p_tipo
 ORDER BY d.hora_inicio, o.codigo_objeto
"""


def programacion(fecha: datetime, tipo: str) -> dict[str, Any]:
    f, dias = _ajustar_periodo(fecha, tipo)
    rows = query(_SQL_PROG, {"p_fecha": f, "p_tipo": TIPO_PROG[tipo]})
    columns = [
        {"key": "codigo_objeto", "label": "Unidad"},
        {"key": "cte_elemento", "label": "Tipo componente"},
        {"key": "hora_inicio", "label": "Inicio programado", "format": "datetime"},
        {"key": "hora_final", "label": "Fin programado", "format": "datetime"},
        {"key": "tipo_indisp", "label": "Tipo"},
        {"key": "causa", "label": "Causa"},
        {"key": "ts", "label": "Registrado", "format": "datetime"},
    ]
    return {"table": "PROG_MANT", "columns": columns, "rows": rows,
            "aviso": _periodo_aviso(f, dias, tipo)}


# ─────────────────────── Comparación programado vs real ───────────────────────
# SQL portado tal cual de Reporte_compracion.cs: tres bloques
#   1 = programado con evento(s) real(es) dentro de la ventana programada
#   2 = programado sin ejecución
#   3 = evento real (155/156) del período que no estaba programado

_SQL_COMPARACION = """
SELECT orden, o.codigo_objeto, s.id_objeto, hora_inicio, hora_final, causa,
       tipo_indisp_prog, ingreso_real, tipo_indisp_real, salida_real,
       causa_real, cte_elemento
  FROM (SELECT 1 orden, p1.id_objeto, p1.hora_inicio, p1.hora_final, p1.causa,
               DECODE(p1.tipo_indisp, 155, 'Prog', 156, 'Forzada',
                      153, 'Pot. Lim.') tipo_indisp_prog,
               r1.hora_ingreso ingreso_real,
               DECODE(r1.id_tipo_operacion, 155, 'Prog', 156, 'Forzada',
                      153, 'Pot. Lim.') tipo_indisp_real,
               NVL(r1.hora_salida, SYSDATE) salida_real,
               UPPER(r1.causa) causa_real
          FROM dc_prog_mant p1, dc_eventos r1
         WHERE p1.fecha = TRUNC(:p_fecha)
           AND r1.hora_ingreso BETWEEN p1.hora_inicio AND p1.hora_final
           AND NVL(r1.hora_salida, SYSDATE) BETWEEN p1.hora_inicio AND p1.hora_final
           AND p1.tipo_prog = :p_tipo
           AND r1.id_tipo_operacion IN (155, 156)
           AND r1.id_elemento = p1.id_objeto
        UNION
        SELECT 2 orden, id_objeto, hora_inicio, hora_final, causa,
               DECODE(tipo_indisp, 155, 'Prog', 156, 'Forzada',
                      153, 'Pot. Lim.') tipo_indisp_prog,
               NULL ingreso_real, NULL tipo_indisp_real, NULL salida_real,
               NULL causa_real
          FROM dc_prog_mant
         WHERE fecha = TRUNC(:p_fecha)
           AND tipo_prog = :p_tipo
           AND (id_objeto, hora_inicio, hora_final) NOT IN (
               SELECT p1.id_objeto, p1.hora_inicio, p1.hora_final
                 FROM dc_prog_mant p1, dc_eventos r1
                WHERE p1.fecha = TRUNC(:p_fecha)
                  AND r1.hora_ingreso BETWEEN p1.hora_inicio AND p1.hora_final
                  AND NVL(r1.hora_salida, SYSDATE) BETWEEN p1.hora_inicio AND p1.hora_final
                  AND p1.tipo_prog = :p_tipo
                  AND r1.id_tipo_operacion IN (155, 156)
                  AND r1.id_elemento = p1.id_objeto)
        UNION
        SELECT 3 orden, cx1.id_elemento id_objeto, NULL hora_inicio,
               NULL hora_final, NULL causa, NULL tipo_indisp_prog,
               cx1.hora_ingreso ingreso_real,
               DECODE(cx1.id_tipo_operacion, 155, 'Prog', 156, 'Forzada',
                      153, 'Pot. Lim.') tipo_indisp_real,
               NVL(cx1.hora_salida, SYSDATE) salida_real, cx1.causa causa_real
          FROM dc_eventos cx1
         WHERE cx1.fecha BETWEEN :p_fecha AND :p_fecha + :dias
           AND cx1.id_tipo_operacion IN (155, 156)
           AND (id_elemento, hora_ingreso, NVL(hora_salida, SYSDATE)) NOT IN (
               SELECT p1.id_objeto, r1.hora_ingreso,
                      NVL(r1.hora_salida, SYSDATE) hora_salida
                 FROM dc_prog_mant p1, dc_eventos r1
                WHERE p1.fecha = TRUNC(:p_fecha)
                  AND r1.hora_ingreso BETWEEN p1.hora_inicio AND p1.hora_final
                  AND NVL(r1.hora_salida, SYSDATE) BETWEEN p1.hora_inicio AND p1.hora_final
                  AND p1.tipo_prog = :p_tipo
                  AND r1.id_tipo_operacion IN (155, 156)
                  AND r1.id_elemento = p1.id_objeto)) s,
       objetos o
 WHERE s.id_objeto = o.id_objeto
 ORDER BY orden, hora_inicio, id_objeto, hora_final, ingreso_real,
          salida_real NULLS LAST
"""

_SECCION = {1: "Programado y ejecutado", 2: "Programado sin ejecución",
            3: "Ejecutado no programado"}


def _fusionar_eventos(rows: list[dict]) -> list[dict]:
    """Une eventos reales contiguos por objeto (JoinEvents del legacy):
    si la salida real de la fila acumulada coincide con el ingreso real de la
    siguiente, se extiende la salida; si no, se emite una fila nueva."""
    out: list[dict] = []
    cur: dict | None = None
    actual = object()
    for r in rows:
        if r["id_objeto"] != actual:
            actual = r["id_objeto"]
            if cur is not None:
                out.append(cur)
            cur = dict(r)
        else:
            if r["salida_real"] is None:
                continue
            if cur is not None and cur["salida_real"] == r["ingreso_real"]:
                cur["salida_real"] = r["salida_real"]
            else:
                if cur is not None:
                    out.append(cur)
                cur = dict(r)
    if cur is not None:
        out.append(cur)
    return out


def comparacion(fecha: datetime, tipo: str) -> dict[str, Any]:
    f, dias = _ajustar_periodo(fecha, tipo)
    rows = query(_SQL_COMPARACION,
                 {"p_fecha": f, "p_tipo": TIPO_PROG[tipo], "dias": dias})
    rows = _fusionar_eventos(rows)
    for r in rows:
        r["seccion"] = _SECCION.get(r.get("orden"), "")
    columns = [
        {"key": "seccion", "label": "Sección"},
        {"key": "codigo_objeto", "label": "Unidad"},
        {"key": "cte_elemento", "label": "Tipo componente"},
        {"key": "hora_inicio", "label": "Inicio prog.", "format": "datetime"},
        {"key": "hora_final", "label": "Fin prog.", "format": "datetime"},
        {"key": "tipo_indisp_prog", "label": "Tipo prog."},
        {"key": "causa", "label": "Causa prog."},
        {"key": "ingreso_real", "label": "Ingreso real", "format": "datetime"},
        {"key": "salida_real", "label": "Salida real", "format": "datetime"},
        {"key": "tipo_indisp_real", "label": "Tipo real"},
        {"key": "causa_real", "label": "Causa real"},
    ]
    return {"table": "COMPARACION_PROG", "columns": columns, "rows": rows,
            "aviso": _periodo_aviso(f, dias, tipo)}
