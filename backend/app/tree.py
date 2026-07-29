"""Árbol de componentes: Tipo → Agente → Central → Unidad.

Traduce General.Get_Component_By_Date + LOAD_TREE del proyecto INDISP.
Devuelve una estructura anidada lista para el frontend.
"""
from datetime import datetime
from typing import Any

from .constants import TipoComponente
from .db import query
from .filters import TiposOperacion, componentes_binds

# SQL basado en General.Get_Component_By_Date, usando sólo la relación vigente
# más reciente a hoy para evitar que componentes movidos de agente/central
# aparezcan duplicados en la jerarquía.
_SQL_COMPONENTES = """
WITH rel_actual AS (
    SELECT *
      FROM (
            SELECT oo.*,
                   ROW_NUMBER() OVER (
                     PARTITION BY oo.ob_id_objeto_primario,
                                  oo.cte_elemento_secundario
                         ORDER BY oo.fecha_vigencia DESC
                   ) rn
              FROM objetos_objetos oo
             WHERE oo.fecha_vigencia <= TRUNC(SYSDATE)
           )
     WHERE rn = 1
)
SELECT id_elemento,
       o.cte_elemento,
       o.codigo_objeto,
       p.id_objeto            id_agente,
       p.codigo_objeto        agente,
       c.id_objeto            id_central,
       c.codigo_objeto_conv   central
  FROM (SELECT DISTINCT (o.id_elemento) id_elemento,
                        s.ob_id_objeto_secundario id_agente,
                        c.ob_id_objeto_secundario id_central
          FROM (SELECT DISTINCT (id_elemento) id_elemento
                  FROM dc_eventos e
                 WHERE (e.fecha BETWEEN TRUNC(:f1) AND TRUNC(:f2))
                   AND (id_tipo_operacion IN (:opn, :opl, :ip, :inf, :op, :ore))) o,
               rel_actual s,
               rel_actual c
         WHERE s.ob_id_objeto_primario = o.id_elemento
           AND s.cte_elemento_secundario = 'AGENTE'
           AND c.ob_id_objeto_primario(+) = o.id_elemento
           AND c.cte_elemento_secundario(+) = 'CENTRAL') a,
       objetos o,
       objetos p,
       objetos c
 WHERE o.cte_elemento IN (:alimenta, :autotran, :cap_serie, :cap_shunt,
                          :generador, :linea, :reactor, :transfor)
   AND (o.fecha_inicio IS NULL OR o.fecha_inicio <= TRUNC(SYSDATE))
   AND (o.fecha_cierre IS NULL OR o.fecha_cierre >= TRUNC(SYSDATE))
   AND o.id_objeto = a.id_elemento
   AND a.id_agente = p.id_objeto
   AND c.id_objeto(+) = id_central
 ORDER BY cte_elemento, p.codigo_objeto, o.codigo_objeto
"""


# Todos los componentes actualmente vigentes del sistema (con relación AGENTE),
# tengan o no eventos en el rango. `con_eventos` marca si registró eventos de
# los tipos de operación activos.
_SQL_COMPONENTES_TODOS = """
WITH rel_actual AS (
    SELECT *
      FROM (
            SELECT oo.*,
                   ROW_NUMBER() OVER (
                     PARTITION BY oo.ob_id_objeto_primario,
                                  oo.cte_elemento_secundario
                         ORDER BY oo.fecha_vigencia DESC
                   ) rn
              FROM objetos_objetos oo
             WHERE oo.fecha_vigencia <= TRUNC(SYSDATE)
           )
     WHERE rn = 1
)
SELECT DISTINCT
       o.id_objeto            id_elemento,
       o.cte_elemento,
       o.codigo_objeto,
       p.id_objeto            id_agente,
       p.codigo_objeto        agente,
       c.id_objeto            id_central,
       c.codigo_objeto_conv   central,
       CASE WHEN (o.fecha_inicio IS NULL OR o.fecha_inicio <= TRUNC(SYSDATE))
             AND (o.fecha_cierre IS NULL OR o.fecha_cierre >= TRUNC(SYSDATE))
            THEN 1 ELSE 0 END vigente,
       CASE WHEN e.id_elemento IS NULL THEN 0 ELSE 1 END con_eventos
  FROM objetos o
  JOIN rel_actual s
    ON s.ob_id_objeto_primario = o.id_objeto
   AND s.cte_elemento_secundario = 'AGENTE'
  JOIN objetos p ON p.id_objeto = s.ob_id_objeto_secundario
  LEFT JOIN rel_actual sc
    ON sc.ob_id_objeto_primario = o.id_objeto
   AND sc.cte_elemento_secundario = 'CENTRAL'
  LEFT JOIN objetos c ON c.id_objeto = sc.ob_id_objeto_secundario
  LEFT JOIN (SELECT DISTINCT id_elemento
               FROM dc_eventos
              WHERE fecha BETWEEN TRUNC(:f1) AND TRUNC(:f2)
                AND id_tipo_operacion IN (:opn, :opl, :ip, :inf, :op, :ore)) e
    ON e.id_elemento = o.id_objeto
 WHERE o.cte_elemento IN (:alimenta, :autotran, :cap_serie, :cap_shunt,
                          :generador, :linea, :reactor, :transfor)
   AND (o.fecha_inicio IS NULL OR o.fecha_inicio <= TRUNC(SYSDATE))
   AND (o.fecha_cierre IS NULL OR o.fecha_cierre >= TRUNC(SYSDATE))
 ORDER BY o.cte_elemento, agente, o.codigo_objeto
"""


def get_component_rows(
    f1: datetime,
    f2: datetime,
    tipos_op: TiposOperacion,
    componentes: TipoComponente = TipoComponente.GENERADOR,
    modo: str = "eventos",
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"f1": f1, "f2": f2}
    params.update(tipos_op.binds())
    params.update(componentes_binds(componentes))
    sql = _SQL_COMPONENTES_TODOS if modo == "todos" else _SQL_COMPONENTES
    return query(sql, params)


def build_tree(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Construye el árbol anidado a partir de las filas planas.

    Jerarquía: cte_elemento (raíz) → agente → central → unidad.
    Si la central es nula, la unidad cuelga directamente del agente
    (mismo comportamiento que Carge_Nodes con padre DBNull).
    """
    raices: dict[str, dict[str, Any]] = {}

    def child(container: dict, key: str) -> dict:
        return container["_index"].setdefault(key, None)

    def new_node(tipo: str, id_objeto, label: str, node_key: str) -> dict[str, Any]:
        return {
            "key": node_key,
            "tipo": tipo,
            "id_objeto": int(id_objeto) if id_objeto is not None else None,
            "label": label,
            "children": [],
            "_index": {},
        }

    for r in rows:
        cte = r["cte_elemento"]
        raiz = raices.get(cte)
        if raiz is None:
            raiz = new_node("raiz", None, cte, f"raiz:{cte}")
            raices[cte] = raiz

        # Agente
        ag_key = f"ag:{r['id_agente']}"
        ag = raiz["_index"].get(ag_key)
        if ag is None:
            ag = new_node("agente", r["id_agente"], r["agente"], ag_key)
            raiz["children"].append(ag)
            raiz["_index"][ag_key] = ag

        # Central (puede ser None)
        parent_for_unidad = ag
        if r.get("id_central") is not None:
            cen_key = f"cen:{r['id_central']}"
            cen = ag["_index"].get(cen_key)
            if cen is None:
                cen = new_node("central", r["id_central"], r["central"], cen_key)
                ag["children"].append(cen)
                ag["_index"][cen_key] = cen
            parent_for_unidad = cen

        # Unidad / componente
        un_key = f"un:{r['id_elemento']}"
        if parent_for_unidad["_index"].get(un_key) is None:
            un = new_node("componente", r["id_elemento"], r["codigo_objeto"], un_key)
            if "vigente" in r:
                un["vigente"] = bool(r["vigente"])
                un["con_eventos"] = bool(r.get("con_eventos"))
            parent_for_unidad["children"].append(un)
            parent_for_unidad["_index"][un_key] = un

    return [_strip_index(n) for n in raices.values()]


def _strip_index(node: dict[str, Any]) -> dict[str, Any]:
    node.pop("_index", None)
    node["children"] = [_strip_index(c) for c in node["children"]]
    return node


def get_tree(
    f1: datetime,
    f2: datetime,
    tipos_op: TiposOperacion,
    componentes: TipoComponente = TipoComponente.GENERADOR,
    modo: str = "eventos",
) -> list[dict[str, Any]]:
    return build_tree(get_component_rows(f1, f2, tipos_op, componentes, modo))
