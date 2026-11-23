"""Disponibilidad por componente (% disponible y horas desconectadas).

Traduce INDISP.HorasDisponibilidad. El rango va de TRUNC(f1) a TRUNC(f2)+1 día.
Sólo considera indisponibilidades programadas (155) y forzadas (156).
"""
from datetime import datetime, timedelta
from typing import Any

from ..constants import TipoOperacion
from ..db import query
from ..potencia_efectiva import CENTRAL, central_de, efectiva, vigencia
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
        {"key": "horas", "label": "Disponibilidad (%)", "format": "0.00", "sinTotal": True},
        {"key": "hora_desconectadas", "label": "Horas Desconectadas", "format": "0.00"},
        {"key": "total", "label": "Horas Periodo", "format": "0.00", "sinTotal": True},
    ]
    return {"table": "DIA", "columns": columns, "rows": rows}


def report_central(
    f1: datetime,
    f2: datetime,
    unidades: list[int],
    ip: bool = True,
    inf: bool = True,
) -> dict[str, Any]:
    """% de disponibilidad por central, ponderado por la potencia efectiva oficial.

    Toma las centrales de los generadores marcados según la tabla semestral
    (potencia_efectiva.CENTRAL, no la jerarquía de red) y considera TODAS sus
    unidades: las que no tuvieron eventos 155/156 cuentan 100 %. Pesos de la
    vigencia que rige el día de inicio; sin vigencia cargada no se pondera.
    """
    if not (ip or inf):
        raise ValueError("Marque Programada y/o Forzada.")
    marcados = query(
        f"SELECT DISTINCT codigo_objeto FROM objetos WHERE id_objeto IN {in_clause(unidades)[0]}",
        in_clause(unidades)[1],
    ) if unidades else []
    codigos = {r["codigo_objeto"] for r in marcados}
    centrales = sorted({central_de(c) for c in codigos if central_de(c)})
    fuera = sorted(c for c in codigos if not central_de(c))

    horas_periodo = ((f2.date() - f1.date()).days + 1) * 24
    vig = vigencia(f1.date())
    columns = [
        {"key": "central", "label": "Central"},
        {"key": "unidades", "label": "Unidades", "format": "num"},
        {"key": "disponibilidad", "label": "Disponibilidad (%)", "format": "0.00", "sinTotal": True},
        {"key": "hora_desconectadas", "label": "Horas Desconectadas", "format": "0.00"},
        {"key": "total", "label": "Horas Periodo", "format": "0.00", "sinTotal": True},
    ]
    if not centrales:
        return {"table": "CENTRAL", "columns": columns, "rows": [],
                "aviso": _aviso_central(vig, fuera, f2.date())}

    unidades_central = [c for c, cen in CENTRAL.items() if cen in centrales]
    binds = {f"c{i}": c for i, c in enumerate(unidades_central)}
    ids = [r["id_objeto"] for r in query(
        "SELECT id_objeto FROM objetos WHERE cte_elemento = 'GENERADOR' AND codigo_objeto IN ("
        + ", ".join(f":{k}" for k in binds) + ")", binds)]
    # Horas desconectadas por unidad con la misma consulta del nivel Componente.
    horas = {r["codigo_objeto"]: r["hora_desconectadas"] or 0
             for r in report(f1, f2, ids, ip, inf)["rows"]}

    rows = []
    for central in centrales:
        cods = [c for c, cen in CENTRAL.items() if cen == central]
        h = sum(horas.get(c, 0) for c in cods)
        pesos = {c: efectiva(c, f1.date()) for c in cods} if vig else {}
        disp = None
        if pesos and all(p is not None for p in pesos.values()):
            total_mw = sum(pesos.values())
            disp = round(sum(p * (horas_periodo - horas.get(c, 0)) for c, p in pesos.items())
                         / (horas_periodo * total_mw) * 100, 2)
        rows.append({"central": central, "unidades": len(cods), "disponibilidad": disp,
                     "hora_desconectadas": round(h, 2), "total": horas_periodo})
    return {"table": "CENTRAL", "columns": columns, "rows": rows,
            "aviso": _aviso_central(vig, fuera, f2.date())}


def _aviso_central(vig: tuple | None, fuera: list[str], fin) -> str:
    partes = []
    if vig:
        partes.append(
            "Disponibilidad de cada central: promedio de sus unidades ponderado por la potencia "
            f"efectiva oficial del CNDC (vigencia {vig[0]:%d/%m/%Y} al {vig[1]:%d/%m/%Y}). Cuentan "
            "todas las unidades de la central; las que no tuvieron eventos suman 100 %. Horas "
            "Desconectadas suma las de todas sus unidades, por eso puede superar las Horas Periodo.")
        if fin > vig[1]:
            partes.append("Se usan los valores vigentes el día de inicio para todo el rango.")
    else:
        partes.append("No hay potencia efectiva oficial para el día de inicio (la tabla rige desde "
                      "01/11/2026): la disponibilidad por central queda en «-».")
    if fuera:
        muestra = ", ".join(fuera[:8]) + (f" y {len(fuera) - 8} más" if len(fuera) > 8 else "")
        partes.append(f"{len(fuera)} componente(s) marcado(s) fuera del cálculo (no son generadores "
                      f"o no tienen central en la tabla de potencia efectiva): {muestra}.")
    return " ".join(partes)
