"""Lógica pura del grupo «Sistema» (sin BD)."""
from datetime import datetime

from app.smec.sistema import _conciliar, _pico_del_dia

_COLS = ["CENTRAL", "COD_CENTRAL", "DIR", "I1", "I2", "I3"]


def test_pico_toma_el_intervalo_de_maxima_inyeccion_e_ignora_retiro():
    rows = [("A", 1, -1, 10.0, 30.0, 20.0),
            ("B", 2, -1, 5.0, -2.0, 15.0),   # consumo propio: resta del total
            ("R", 3, 1, 999.0, 999.0, 999.0)]  # retiro: no cuenta
    p = _pico_del_dia(_COLS, rows)
    assert p["total"] == 35.0 and p["hora"] == "16:00"
    assert p["aporte"] == {1: 20.0, 2: 15.0}


def test_pico_sin_datos():
    assert _pico_del_dia(_COLS, [("A", 1, -1, None, None, None)]) is None


def test_conciliacion_diferencia_y_porcentaje():
    dias = [datetime(2026, 10, 1), datetime(2026, 10, 2)]
    filas = _conciliar({"D0": 1000.0, "D1": None}, {"D0": 970.0, "D1": 5.0}, dias)
    assert filas[0] == {"fecha": "01/10/2026", "iny": 1000.0, "ret": 970.0, "dif": 30.0, "pct": 3.0}
    assert filas[1]["dif"] is None and filas[1]["pct"] is None
