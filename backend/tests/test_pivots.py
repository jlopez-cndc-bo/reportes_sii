"""Tests de la lógica de pivoteo y transformación (funciones puras, sin BD)."""
from datetime import datetime

from app.constants import TipoComponente
from app.filters import TiposOperacion, componentes_binds
from app.reports import horas_no_disponibilidad as hnd
from app.reports import horas_tipo_operacion as hto
from app.sqlutil import in_clause
from app.tree import build_tree

# ---------------------------------------------------------------- sqlutil

def test_in_clause_no_agrega_centinela():
    sql, binds = in_clause([5, 9])
    assert sql == "(:u0, :u1)"
    assert binds == {"u0": 5, "u1": 9}


def test_in_clause_mas_de_1000_no_arma_lista_plana():
    # ORA-01795: una lista IN admite 1000 expresiones; con «Todos» (1368) daba Error 500.
    sql, binds = in_clause(list(range(1368)))
    assert len(binds) == 1368
    assert sql.startswith("(SELECT :u0 FROM dual UNION ALL ")
    assert sql.count(":u") == 1368


def test_in_clause_vacio():
    sql, binds = in_clause([])
    assert sql == "(NULL)"
    assert binds == {}


# ------------------------------------------------ unir eventos (rpt 4)

def test_unir_eventos_fusiona_contiguos():
    rows = [
        {"id_elemento": 1, "hora_ingreso": "a", "hora_salida": "b", "hora_desconectadas": 2},
        {"id_elemento": 1, "hora_ingreso": "b", "hora_salida": "c", "hora_desconectadas": 3},
        {"id_elemento": 1, "hora_ingreso": "x", "hora_salida": "y", "hora_desconectadas": 1},
    ]
    out = hnd._unir_eventos(rows)
    assert len(out) == 2
    assert out[0]["hora_salida"] == "c"
    assert out[0]["hora_desconectadas"] == 5
    assert out[1]["hora_ingreso"] == "x"


def test_unir_eventos_separa_por_elemento():
    rows = [
        {"id_elemento": 1, "hora_ingreso": "a", "hora_salida": "b", "hora_desconectadas": 1},
        {"id_elemento": 2, "hora_ingreso": "b", "hora_salida": "c", "hora_desconectadas": 1},
    ]
    out = hnd._unir_eventos(rows)
    assert len(out) == 2


# ------------------------------------------------ buckets tipo operación

def test_iter_buckets_dia():
    b = list(hto._iter_buckets("dia", datetime(2025, 1, 1), datetime(2025, 1, 3)))
    assert [d.day for d in b] == [1, 2, 3]


def test_iter_buckets_mes():
    b = list(hto._iter_buckets("mes", datetime(2025, 1, 15), datetime(2025, 3, 2)))
    assert [(d.year, d.month) for d in b] == [(2025, 1), (2025, 2), (2025, 3)]


def test_iter_buckets_anio():
    b = list(hto._iter_buckets("anio", datetime(2023, 6, 1), datetime(2025, 2, 1)))
    assert [d.year for d in b] == [2023, 2024, 2025]


# ------------------------------------------------ árbol

def test_build_tree_jerarquia():
    rows = [
        {"cte_elemento": "GENERADOR", "id_agente": 100, "agente": "AG1",
         "id_central": 200, "central": "CEN1", "id_elemento": 300, "codigo_objeto": "U1"},
        {"cte_elemento": "GENERADOR", "id_agente": 100, "agente": "AG1",
         "id_central": 200, "central": "CEN1", "id_elemento": 301, "codigo_objeto": "U2"},
    ]
    tree = build_tree(rows)
    assert len(tree) == 1
    raiz = tree[0]
    assert raiz["tipo"] == "raiz" and raiz["label"] == "GENERADOR"
    ag = raiz["children"][0]
    assert ag["tipo"] == "agente" and ag["id_objeto"] == 100
    cen = ag["children"][0]
    assert cen["tipo"] == "central" and cen["id_objeto"] == 200
    assert len(cen["children"]) == 2  # dos unidades bajo la central


def test_build_tree_sin_central_cuelga_de_agente():
    rows = [
        {"cte_elemento": "GENERADOR", "id_agente": 100, "agente": "AG1",
         "id_central": None, "central": None, "id_elemento": 300, "codigo_objeto": "U1"},
    ]
    tree = build_tree(rows)
    ag = tree[0]["children"][0]
    assert ag["children"][0]["tipo"] == "componente"
    assert ag["children"][0]["id_objeto"] == 300


def test_build_tree_modo_todos_propaga_flags():
    rows = [
        {"cte_elemento": "LINEA", "id_agente": 100, "agente": "AG1",
         "id_central": None, "central": None, "id_elemento": 300,
         "codigo_objeto": "L1", "vigente": 1, "con_eventos": 0},
        {"cte_elemento": "LINEA", "id_agente": 100, "agente": "AG1",
         "id_central": None, "central": None, "id_elemento": 301,
         "codigo_objeto": "L2", "vigente": 0, "con_eventos": 1},
    ]
    tree = build_tree(rows)
    hojas = tree[0]["children"][0]["children"]
    assert hojas[0]["vigente"] is True and hojas[0]["con_eventos"] is False
    assert hojas[1]["vigente"] is False and hojas[1]["con_eventos"] is True


def test_build_tree_modo_eventos_sin_flags():
    rows = [
        {"cte_elemento": "GENERADOR", "id_agente": 100, "agente": "AG1",
         "id_central": None, "central": None, "id_elemento": 300, "codigo_objeto": "U1"},
    ]
    tree = build_tree(rows)
    hoja = tree[0]["children"][0]["children"][0]
    assert "vigente" not in hoja  # el frontend trata ausente como vigente


# ------------------------------------------------ programación (fase 2)

from app.reports import programacion as prog


def test_ajustar_periodo_semanal_ancla_sabado():
    f, dias = prog._ajustar_periodo(datetime(2026, 7, 8), "semanal")
    assert f.weekday() == 5 and dias == 7  # retrocede al sábado anterior
    assert f <= datetime(2026, 7, 8)
    f2, _ = prog._ajustar_periodo(f, "semanal")
    assert f2 == f  # un sábado no se mueve


def test_ajustar_periodo_mensual():
    f, dias = prog._ajustar_periodo(datetime(2026, 2, 15), "mensual")
    assert f == datetime(2026, 2, 1) and dias == 27  # feb-2026: 28 días - 1


def test_fusionar_eventos_contiguos():
    a, b, c = (datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 10),
               datetime(2026, 1, 1, 12))
    rows = [
        {"id_objeto": 5, "ingreso_real": a, "salida_real": b},
        {"id_objeto": 5, "ingreso_real": b, "salida_real": c},
        {"id_objeto": 6, "ingreso_real": a, "salida_real": b},
    ]
    out = prog._fusionar_eventos(rows)
    assert len(out) == 2
    assert out[0]["salida_real"] == c  # los contiguos del objeto 5 se unen
    assert out[1]["id_objeto"] == 6


# ------------------------------------------------ factor de carga

def test_factor_formula():
    from app.smec.reportes import _factor
    assert _factor(1000, 100, 10) == 1.0
    assert _factor(-500, 100, 10) == 0.5    # valor absoluto
    assert _factor(129, 100, 10) == 0.12    # TRUNC a 2 decimales, sin redondeo
    assert _factor(1000, 0, 10) == 0
    assert _factor(1000, 100, 0) == 0
    assert _factor(None, 100, 10) == 0


# ------------------------------------------------ filtros

def test_tipos_operacion_binds():
    t = TiposOperacion(programada=True, forzada=True)
    b = t.binds()
    assert b["ip"] == 155 and b["inf"] == 156
    assert b["opn"] == 0 and b["op"] == 0
    assert t.activos() == [155, 156]


def test_componentes_binds_generador():
    b = componentes_binds(TipoComponente.GENERADOR)
    assert b["generador"] == "GENERADOR"
    assert b["linea"] == ""


def test_componentes_binds_alimenta_es_al():
    # Los alimentadores con eventos son cte_elemento 'AL'; 'ALIMENTA' sólo tiene eventos de 2012.
    assert componentes_binds(TipoComponente.ALIMENTA)["alimenta"] == "AL"
