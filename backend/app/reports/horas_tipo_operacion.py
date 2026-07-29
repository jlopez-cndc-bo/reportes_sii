"""Reporte 5: Horas por Tipo de Operación.

Traduce INDISP.HorasPorTipodeOperacion. Soporta:
  - período: día / mes / año
  - modo: agregado (suma todos los tipos) o desagregado (columna por tipo)

El original construía SQL con cientos de columnas DECODE; aquí traemos los
datos agrupados y pivoteamos en Python, que es equivalente y más robusto.
"""
from datetime import date, datetime
from typing import Any, Iterable

from ..constants import TIPO_OP_LABEL
from ..db import query
from ..filters import TiposOperacion
from ..sqlutil import in_clause

# Modelos de truncado/formato Oracle y de rango, por período.
_PERIODO = {
    "dia": {"trunc": "DD", "fmt": "ddmmyyyy", "py": "%d%m%Y", "hdr": "%d/%m/%Y",
            "rango": "TRUNC(:f1) AND TRUNC(:f2)"},
    "mes": {"trunc": "MM", "fmt": "mmyyyy", "py": "%m%Y", "hdr": "%m/%Y",
            "rango": "TRUNC(:f1, 'MM') AND LAST_DAY(TRUNC(:f2, 'MM'))"},
    "anio": {"trunc": "YYYY", "fmt": "yyyy", "py": "%Y", "hdr": "%Y",
             "rango": "TRUNC(:f1, 'YYYY') AND LAST_DAY(TRUNC(:f2, 'YYYY'))"},
}

_SQL_AGREGADO = """
SELECT o.codigo_objeto, o.cte_elemento, a.id_elemento, a.fecha_key, a.tiempo
  FROM (SELECT id_elemento,
               TO_CHAR(TRUNC(fecha, :pmodel), :pfmt) fecha_key,
               ROUND(SUM(tiempo) * 24, 2) tiempo
          FROM (SELECT id_elemento, fecha,
                       (NVL(hora_salida, SYSDATE) - hora_ingreso) tiempo
                  FROM dc_eventos
                 WHERE fecha BETWEEN {rango}
                   AND id_tipo_operacion IN (:opn, :opl, :ip, :inf, :op, :ore)
                   AND id_elemento IN {in_sql})
         GROUP BY id_elemento, TRUNC(fecha, :pmodel)) a,
       objetos o
 WHERE a.id_elemento = o.id_objeto
 ORDER BY o.cte_elemento, o.codigo_objeto
"""

_SQL_DESAGREGADO = """
SELECT o.codigo_objeto, o.cte_elemento, a.id_elemento, a.fecha_key,
       a.tipo_op, a.tiempo
  FROM (SELECT id_elemento,
               TO_CHAR(TRUNC(fecha, :pmodel), :pfmt) fecha_key,
               id_tipo_operacion tipo_op,
               ROUND(SUM(tiempo) * 24, 2) tiempo
          FROM (SELECT id_elemento, fecha, id_tipo_operacion,
                       (NVL(hora_salida, SYSDATE) - hora_ingreso) tiempo
                  FROM dc_eventos
                 WHERE fecha BETWEEN {rango}
                   AND id_tipo_operacion IN (:opn, :opl, :ip, :inf, :op, :ore)
                   AND id_elemento IN {in_sql})
         GROUP BY id_elemento, TRUNC(fecha, :pmodel), id_tipo_operacion) a,
       objetos o
 WHERE a.id_elemento = o.id_objeto
 ORDER BY o.cte_elemento, o.codigo_objeto
"""


def _iter_buckets(periodo: str, f1: datetime, f2: datetime) -> Iterable[date]:
    d1, d2 = f1.date(), f2.date()
    if periodo == "dia":
        cur = d1
        while cur <= d2:
            yield cur
            cur = date.fromordinal(cur.toordinal() + 1)
    elif periodo == "mes":
        y, m = d1.year, d1.month
        while (y, m) <= (d2.year, d2.month):
            yield date(y, m, 1)
            m += 1
            if m > 12:
                m = 1
                y += 1
    else:  # anio
        for y in range(d1.year, d2.year + 1):
            yield date(y, 1, 1)


def report(
    periodo: str,
    modo: str,
    f1: datetime,
    f2: datetime,
    unidades: list[int],
    tipos_op: TiposOperacion,
) -> dict[str, Any]:
    periodo = periodo.lower()
    if periodo not in _PERIODO:
        raise ValueError(f"Período inválido: {periodo}")
    cfg = _PERIODO[periodo]
    desagregado = modo.lower() == "desagregado"

    in_sql, binds = in_clause(unidades)
    tmpl = _SQL_DESAGREGADO if desagregado else _SQL_AGREGADO
    sql = tmpl.format(rango=cfg["rango"], in_sql=in_sql)
    binds.update({"f1": f1, "f2": f2, "pmodel": cfg["trunc"], "pfmt": cfg["fmt"]})
    binds.update(tipos_op.binds())
    rows = query(sql, binds)

    # Buckets de fecha (columnas), en orden.
    buckets = list(_iter_buckets(periodo, f1, f2))
    bucket_keys = [b.strftime(cfg["py"]) for b in buckets]
    tipos_activos = tipos_op.activos()  # ids en orden opn,opl,ip,inf,op,ore

    # Acumular por componente.
    comps: dict[Any, dict[str, Any]] = {}
    for r in rows:
        cid = r["id_elemento"]
        comp = comps.get(cid)
        if comp is None:
            comp = {"codigo_objeto": r["codigo_objeto"], "_vals": {}}
            comps[cid] = comp
        if desagregado:
            colkey = f"{r['fecha_key']}:{int(r['tipo_op'])}"
        else:
            colkey = r["fecha_key"]
        comp["_vals"][colkey] = r["tiempo"]

    # Definir columnas.
    columns: list[dict[str, Any]] = [{"key": "codigo_objeto", "label": "Componente"}]
    col_defs: list[tuple[str, str]] = []  # (colkey, header)
    for b, key in zip(buckets, bucket_keys):
        hdr = b.strftime(cfg["hdr"])
        if desagregado:
            for tid in tipos_activos:
                col = f"{key}:{tid}"
                col_defs.append((col, f"{hdr}:{TIPO_OP_LABEL.get(tid, tid)}"))
        else:
            col_defs.append((key, hdr))
    for col, hdr in col_defs:
        columns.append({"key": col, "label": hdr, "format": "0.0"})

    # Armar filas rellenando 0 donde no hay dato.
    filas: list[dict[str, Any]] = []
    for comp in comps.values():
        fila = {"codigo_objeto": comp["codigo_objeto"]}
        for col, _ in col_defs:
            fila[col] = comp["_vals"].get(col, 0)
        filas.append(fila)

    return {"table": periodo.upper(), "columns": columns, "rows": filas}
