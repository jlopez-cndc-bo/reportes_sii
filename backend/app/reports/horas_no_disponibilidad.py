"""Reporte 4: Horas de No Disponibilidad (detalle de eventos por componente).

Traduce INDISP.HorasNoDisponibilidad (Get_SQL + UnirEventor opcional).
Muestra cada evento con ingreso/salida, tipo, causa, restricción de gas y
potencia limitada. Con `agregado=True` fusiona eventos consecutivos contiguos.
"""
from datetime import datetime, timedelta
from typing import Any

from ..constants import TipoOperacion
from ..db import query
from ..sqlutil import in_clause

_SQL = """
SELECT id_elemento,
       o.codigo_objeto,
       ROUND(((total - t1) / total) * 100, 2) horas,
       ROUND(t1, 2)                            hora_desconectadas,
       total,
       hora_ingreso,
       NVL(hora_salida, :f2) hora_salida,
       DECODE(id_tipo_operacion, 155, 'Prog', 156, 'Forz', 152, 'Op. Normal',
              'Pot. Lim') id_tipo_operacion,
       causa,
       potencia_limitada,
       DECODE(restric_gas, 0, 'NO', 1, 'SI', '-') restric_gas
  FROM (SELECT id_elemento,
               SUM(tipo_ind) t1,
               (TRUNC(:f2) - TRUNC(:f1)) * 24 total,
               hora_ingreso, hora_salida, id_tipo_operacion, causa,
               potencia_limitada, restric_gas
          FROM (SELECT id_elemento,
                       (NVL(hora_salida, :f2) - hora_ingreso) * 24 tipo_ind,
                       hora_ingreso, hora_salida, id_tipo_operacion, causa,
                       potencia_limitada, restric_gas
                  FROM dc_eventos e
                 WHERE fecha BETWEEN TRUNC(:f1) AND TRUNC(:f2) - 1
                   AND e.id_tipo_operacion IN (:pro, :forz, :opn, :plim)
                   AND id_elemento IN {in_sql})
         GROUP BY id_elemento,
                  (TRUNC(:f2) - TRUNC(:f1)) * 24,
                  hora_ingreso, hora_salida, id_tipo_operacion, causa,
                  potencia_limitada, restric_gas) k,
       objetos o
 WHERE o.id_objeto = k.id_elemento
 ORDER BY cte_elemento, codigo_objeto, hora_ingreso
"""


def _unir_eventos(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reproduce UnirEventor: fusiona eventos contiguos del mismo componente."""
    salida: list[dict[str, Any]] = []
    actual: dict[str, Any] | None = None
    for r in rows:
        if actual is None:
            actual = dict(r)
        elif actual["id_elemento"] != r["id_elemento"]:
            salida.append(actual)
            actual = dict(r)
        elif actual["hora_salida"] == r["hora_ingreso"]:
            actual["hora_salida"] = r["hora_salida"]
            actual["hora_desconectadas"] = (
                (actual.get("hora_desconectadas") or 0)
                + (r.get("hora_desconectadas") or 0)
            )
        else:
            salida.append(actual)
            actual = dict(r)
    if actual is not None:
        salida.append(actual)
    return salida


def report(
    f1: datetime,
    f2: datetime,
    unidades: list[int],
    ip: bool = True,
    inf: bool = True,
    opn: bool = False,
    plim: bool = False,
    agregado: bool = False,
) -> dict[str, Any]:
    in_sql, binds = in_clause(unidades)
    sql = _SQL.format(in_sql=in_sql)
    ini = f1.replace(hour=0, minute=0, second=0, microsecond=0)
    fin = f2.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    binds.update(
        {
            "f1": ini,
            "f2": fin,
            "pro": TipoOperacion.PROGRAMADA if ip else 0,
            "forz": TipoOperacion.FORZADA if inf else 0,
            "opn": TipoOperacion.OP_NORMAL if opn else 0,
            "plim": TipoOperacion.POT_LIMITADA if plim else 0,
        }
    )
    rows = query(sql, binds)
    if agregado:
        rows = _unir_eventos(rows)
    columns = [
        {"key": "codigo_objeto", "label": "Componente"},
        {"key": "hora_ingreso", "label": "Hora Ingreso", "format": "datetime"},
        {"key": "hora_salida", "label": "Hora Salida", "format": "datetime"},
        {"key": "id_tipo_operacion", "label": "Tipo Operación"},
        {"key": "hora_desconectadas", "label": "Horas Desconectadas", "format": "0.0"},
        {"key": "causa", "label": "Causa"},
        {"key": "restric_gas", "label": "Restric Gas?"},
        {"key": "potencia_limitada", "label": "Pot. Lim", "format": "0.0"},
        {"key": "horas", "label": "Disponibilidad (%)", "format": "0.0", "hidden": True},
        {"key": "total", "label": "Horas Periodo", "format": "0.0", "hidden": True},
    ]
    return {"table": "DIA", "columns": columns, "rows": rows}
