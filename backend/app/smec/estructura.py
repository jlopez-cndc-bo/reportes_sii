"""Estructura/árbol SMEC: Inyección/Retiro → Agente → Central.

Portado de SmecEstructuraRepository + SmecTreeHelper del proyecto moderno.
Fuente: tabla dw_relaciones + paquete pkg_objetos.
Dirección: en dw_relaciones se usa -1*dir; aquí Dir==1 => INYECCIÓN, Dir==-1 => RETIRO
(igual que SmecTreeHelper.BuildEstructura). Las hojas (centrales) son las
seleccionables; su id_objeto es el id_central que consumen los procedimientos.
"""
from typing import Any

from ..db import query

_SQL = """
SELECT -1 * a.dir                                     dir,
       niv5                                           id_agente,
       pkg_objetos.get_codigo_objeto(niv5)            nombre_agente,
       niv4                                           id_central,
       DECODE(dir, 1,
              pkg_objetos.get_codigo_objeto_conv(niv4),
              pkg_objetos.get_descripcion_objeto(niv4)) central
  FROM (SELECT niv4, niv5, MAX(dir) dir, MAX(orden) orden,
               MAX(orden_central) orden_central
          FROM dw_relaciones
         GROUP BY niv4, niv5
         ORDER BY dir, niv4, niv5) a
 ORDER BY orden, orden_central
"""


def get_estructura() -> list[dict[str, Any]]:
    rows = query(_SQL)
    # Dos raíces fijas.
    raices = {
        1: {"key": "iny", "tipo": "raiz", "id_objeto": None,
            "label": "INYECCIÓN", "direccion": "iny", "children": [], "_ag": {}},
        -1: {"key": "ret", "tipo": "raiz", "id_objeto": None,
             "label": "RETIRO", "direccion": "ret", "children": [], "_ag": {}},
    }
    for r in rows:
        d = int(r["dir"])
        raiz = raices.get(1 if d == 1 else -1)
        pref = raiz["direccion"]
        idag = int(r["id_agente"])
        ag = raiz["_ag"].get(idag)
        if ag is None:
            ag = {"key": f"{pref}:ag:{idag}", "tipo": "agente", "id_objeto": idag,
                  "label": r["nombre_agente"], "children": [], "_cen": set()}
            raiz["children"].append(ag)
            raiz["_ag"][idag] = ag
        idc = int(r["id_central"]) if r["id_central"] is not None else None
        if idc is not None and idc not in ag["_cen"]:
            ag["children"].append({
                "key": f"{pref}:cen:{idc}", "tipo": "central", "id_objeto": idc,
                "label": r["central"], "children": [],
            })
            ag["_cen"].add(idc)

    salida = []
    for raiz in (raices[1], raices[-1]):
        raiz.pop("_ag", None)
        for ag in raiz["children"]:
            ag.pop("_cen", None)
        salida.append(raiz)
    return salida
