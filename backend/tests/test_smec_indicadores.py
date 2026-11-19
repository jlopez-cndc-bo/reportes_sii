from datetime import datetime

from app.smec.reportes import _desplazar, _indicadores, _total, energia_enriquecida

LABELS = ["00:00", "06:00", "12:00", "18:00"]  # 4 intervalos → 6 h cada uno


def _fila(*vals):
    f = {f"I{i}": v for i, v in enumerate(vals)}
    _indicadores(f, list(f), LABELS)
    return f


def test_indicadores_con_servicio_local_y_nulos():
    f = _fila(-2.0, 50.0, None, 10.0)
    assert (f["pot_max"], f["hora_max"]) == (50.0, "06:00")
    assert (f["pot_min"], f["hora_min"]) == (-2.0, "00:00")
    assert f["promedio"] == 19.3333333333
    assert f["completitud"] == 75.0
    assert f["energia_bruta"] == 360.0      # (50 + 10) × 6 h
    assert f["servicio_local"] == -12.0     # -2 × 6 h
    assert f["energia_neta"] == 348.0
    assert f["horas_servicio"] == 12.0
    assert f["arranques"] == 1              # -2 → 50
    # 12:00 es nulo: la única rampa contigua es 00:00→06:00
    assert (f["rampa_max"], f["hora_rampa"]) == (52.0, "06:00")


def test_arranques_y_rampa_negativa():
    f = _fila(5.0, 0.0, 8.0, 0.0)
    assert f["arranques"] == 1              # 0 → 8 (el 5 inicial ya estaba en servicio)
    assert (f["rampa_max"], f["hora_rampa"]) == (8.0, "12:00")  # empate |8|: el primero
    f = _fila(0.0, 9.0, 0.0, 0.0)
    assert (f["rampa_max"], f["hora_rampa"]) == (9.0, "06:00")


def test_indicadores_sin_datos():
    f = _fila(None, None, None, None)
    assert f["pot_max"] is None and f["energia_neta"] is None and f["arranques"] is None


def test_total():
    assert _total([0.1, 0.2, None]) == 0.3
    assert _total([None]) is None


def test_desplazar_bisiesto():
    assert _desplazar(datetime(2024, 2, 29), "anio") == datetime(2023, 2, 28)
    assert _desplazar(datetime(2026, 3, 8), "semana") == datetime(2026, 3, 1)


def test_energia_enriquecida_participacion_y_variacion():
    actual = {"columns": [], "rows": [
        {"agente": "A", "central": "X", "total": 30.0},
        {"agente": "A", "central": "Y", "total": 10.0},
        {"agente": "B", "central": "Z", "total": None},
    ]}
    previo = {"columns": [], "rows": [
        {"agente": "A", "central": "X", "total": 20.0},
        {"agente": "A", "central": "Y", "total": 0.0},
    ]}
    llamadas = []

    def fn(f1, f2, ids, d):
        llamadas.append(f1)
        return actual if len(llamadas) == 1 else previo

    res = energia_enriquecida(fn, datetime(2026, 1, 1), datetime(2026, 1, 31), [1], "iny", "anio")
    x, y, z = res["rows"]
    assert (x["part"], y["part"], z["part"]) == (75.0, 25.0, None)
    assert (x["total_ant"], x["var"]) == (20.0, 50.0)
    assert y["var"] is None                 # anterior 0: sin variación, no Infinity
    assert z["total_ant"] is None and z["var"] is None
    assert llamadas[1] == datetime(2025, 1, 1)
    assert [c["key"] for c in res["columns"]] == ["part", "total_ant", "var"]
