"""Prueba de humo contra Oracle: árbol + los 5 reportes.

Uso (desde web/backend, con .env configurado):
    .venv/Scripts/python.exe smoke_test.py --inicio 2025-01-01 --fin 2025-01-07
"""
import argparse
from datetime import datetime

from app.constants import Resolucion, TipoComponente
from app.db import init_pool, pool_ready
from app.filters import TiposOperacion
from app.reports import (
    horas_disponibilidad,
    horas_no_disponibilidad,
    horas_tipo_operacion,
    potencias_disponibles,
    potencias_indisponibles,
)
from app.tree import get_component_rows, get_tree


def _ids_desde_arbol(nodes, tipo, acc):
    for n in nodes:
        if n["tipo"] == tipo and n["id_objeto"] is not None:
            acc.append(n["id_objeto"])
        _ids_desde_arbol(n["children"], tipo, acc)
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", required=True)
    ap.add_argument("--fin", required=True)
    ap.add_argument("--limite", type=int, default=10, help="máx. unidades a probar")
    args = ap.parse_args()

    f1 = datetime.fromisoformat(args.inicio)
    f2 = datetime.fromisoformat(args.fin)

    init_pool()
    if not pool_ready():
        print("[X] Oracle no configurado. Complete el archivo .env.")
        return

    tops = TiposOperacion(op_normal=True, programada=True, forzada=True)
    print(f"== Árbol de componentes {args.inicio}..{args.fin} ==")
    filas = get_component_rows(f1, f2, tops, TipoComponente.GENERADOR)
    print(f"   filas planas: {len(filas)}")
    tree = get_tree(f1, f2, tops, TipoComponente.GENERADOR)
    print(f"   raíces: {len(tree)}")

    unidades = _ids_desde_arbol(tree, "componente", [])[: args.limite]
    centrales = _ids_desde_arbol(tree, "central", [])[: args.limite]
    print(f"   unidades de prueba: {unidades}")

    if not unidades:
        print("[!] No hay unidades con eventos en el rango; pruebe otras fechas.")
        return

    def show(nombre, res):
        print(f"== {nombre} ==")
        print(f"   tabla={res['table']} columnas={len(res['columns'])} filas={len(res['rows'])}")
        if res["rows"]:
            print(f"   ejemplo: {res['rows'][0]}")

    show("Potencias Disponibles (unidad)",
         potencias_disponibles.report("unidad", f1, f2, unidades))
    if centrales:
        show("Potencias Disponibles (central)",
             potencias_disponibles.report("central", f1, f2, centrales))
    show("Potencias Indisponibles (15 min)",
         potencias_indisponibles.report(f1, f2, Resolucion.INTERVALO, 15, unidades, True, True))
    show("Horas de Disponibilidad",
         horas_disponibilidad.report(f1, f2, unidades, True, True))
    show("Horas de No Disponibilidad",
         horas_no_disponibilidad.report(f1, f2, unidades, True, True, False, False, False))
    show("Horas por Tipo de Operación (día/agregado)",
         horas_tipo_operacion.report("dia", "agregado", f1, f2, unidades, tops))
    print("\n[OK] Smoke test finalizado.")


if __name__ == "__main__":
    main()
