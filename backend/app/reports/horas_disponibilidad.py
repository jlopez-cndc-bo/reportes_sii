"""Reporte 3: Horas de Disponibilidad (% disponibilidad agregado por componente).

Traduce INDISP.HorasDisponibilidad. El rango va de TRUNC(f1) a TRUNC(f2)+1 día.
Sólo considera indisponibilidades programadas (155) y forzadas (156).
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
       total
  FROM (SELECT id_elemento,
               SUM(tipo_ind) t1,
               (TRUNC(:f2) - TRUNC(:f1)) * 24 total
          FROM (SELECT id_elemento,
                       (NVL(hora_salida, :f2) - hora_ingreso) * 24 tipo_ind
                  FROM dc_eventos e
                 WHERE fecha BETWEEN TRUNC(:f1) AND TRUNC(:f2) - 1
                   AND e.id_tipo_operacion IN (:pro, :forz)
                   AND id_elemento IN {in_sql})
         GROUP BY id_elemento) k,
       objetos o
 WHERE o.id_objeto = k.id_elemento
 ORDER BY codigo_objeto
"""


def report(
    f1: datetime,
    f2: datetime,
    unidades: list[int],
    ip: bool = True,
    inf: bool = True,
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
        }
    )
    rows = query(sql, binds)
    columns = [
        {"key": "codigo_objeto", "label": "Componente"},
        {"key": "horas", "label": "Disponibilidad (%)", "format": "0.0"},
        {"key": "hora_desconectadas", "label": "Horas Desconectadas", "format": "0.0"},
        {"key": "total", "label": "Horas Periodo", "format": "0.0"},
    ]
    return {"table": "DIA", "columns": columns, "rows": rows}
