"""Lógica pura del grupo «Sistema» (sin BD)."""
from datetime import datetime

from app.smec.sistema import _conciliar, _pico_del_dia

_COLS = ["CENTRAL", "COD_CENTRAL", "DIR", "I1", "I2", "I3"]


def test_pico_toma_el_intervalo_de_maximo_retiro_y_desglosa_la_generacion():
    rows = [("A", 1, -1, 10.0, 30.0, 20.0),
            ("B", 2, -1, 5.0, -2.0, 15.0),   # consumo propio: resta de la generación
            ("R", 3, 1, 14.0, 40.0, 33.0)]   # retiro: define la punta (no coincide con la máx. inyección)
    p = _pico_del_dia(_COLS, rows)
    assert p["total"] == 40.0 and p["hora"] == "08:00"
    assert p["generacion"] == 28.0 and p["aporte"] == {1: 30.0, 2: -2.0}


def test_pico_sin_datos():
    assert _pico_del_dia(_COLS, [("A", 1, -1, 1.0, 2.0, 3.0), ("R", 3, 1, None, None, None)]) is None


def test_conciliacion_diferencia_y_porcentaje():
    dias = [datetime(2026, 10, 1), datetime(2026, 10, 2)]
    filas = _conciliar({"D0": 1000.0, "D1": None}, {"D0": 970.0, "D1": 5.0}, dias)
    assert filas[0] == {"fecha": "01/10/2026", "iny": 1000.0, "ret": 970.0, "dif": 30.0, "pct": 3.0}
    assert filas[1]["dif"] is None and filas[1]["pct"] is None


def test_curvas_generacion_demanda_por_direccion_e_intervalo():
    from app.smec.sistema import _curvas
    c = _curvas([{"dir": -1, "intervalo": 1, "potencia": 10.5}, {"dir": 1, "intervalo": 96, "potencia": 9},
                 {"dir": 1, "intervalo": 97, "potencia": 1}, {"dir": 0, "intervalo": 1, "potencia": 1}])
    assert c[-1][0] == 10.5 and c[-1][1] is None
    assert c[1][95] == 9.0 and len(c[1]) == 96
