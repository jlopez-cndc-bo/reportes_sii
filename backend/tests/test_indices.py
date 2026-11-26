from datetime import datetime

import pytest

from app.reports.indices import indices, variables

D = datetime(2026, 11, 20)
CFG = {"causa_salida_forzada": ["Disparo"], "causa_arranque_fallido": ["Falla en el arranque"]}


def seg(tipo, h1, h2, causa=None, plim=None, dia=D):
    base = dia.replace(hour=0, minute=0)
    return {"tipo": tipo, "ini": base + _td(h1), "fin": base + _td(h2), "causa": causa, "plim": plim}


def _td(h):
    from datetime import timedelta
    return timedelta(hours=h)


def test_variables_un_dia():
    segs = [seg(152, 6, 10), seg(156, 10, 12, "Disparo, protección."),
            seg(156, 14, 14.5, "Falla en el arranque."), seg(153, 14.5, 18.5, plim=30)]
    v = variables(segs, D, D.replace(day=21), CFG, lambda d: 60.0)
    assert (v["sh"], v["foh"], v["ind_res"], v["rsh"]) == (8, 2, 0.5, 13.5)
    # el arranque desde parada cuenta; 153 tras la forzada no es arranque
    assert (v["salidas"], v["intentos"], v["exitosos"]) == (1, 1, 1)
    assert v["plim_eq"] == pytest.approx(30 * 4 / 60)
    r = indices(v)
    assert r["for"] == pytest.approx(20)
    efdhrs = 0.5 / 13.5
    assert r["efor"] == pytest.approx((2 + 2 + efdhrs) / (2 + 8 + efdhrs) * 100)
    f = (1 / 2 + 1 / 13.5) / (1 / 2 + 1 / 13.5 + 1 / 8)
    fp = 8 / 21.5
    assert r["eford"] == pytest.approx((f * 2 + fp * (2 + efdhrs)) / (8 + f * 2) * 100)


def test_forzada_partida_por_dia_es_una_salida_y_otras_causas_sin_clasificar():
    ayer = D.replace(day=19)
    segs = [seg(152, 0, 20, dia=ayer), seg(156, 20, 24, "Disparo, x", dia=ayer),
            seg(156, 0, 3, "Disparo, x"), seg(156, 5, 6, "Falla de comunicación.")]
    v = variables(segs, D, D.replace(day=21), CFG, lambda d: None)
    assert (v["foh"], v["salidas"], v["sin_clasificar"]) == (3, 0, 1)   # la salida empezó ayer
    assert v["rsh"] == 20


def test_sin_eventos_contables_no_inventa_indices():
    v = variables([], D, D.replace(day=21), CFG, lambda d: None)
    r = indices(v)
    assert v["rsh"] == 24
    assert (r["for"], r["f"], r["eford"]) == (None, None, None)
    assert r["efor"] is None or r["efor"] == 0


def test_continuacion_sin_clasificador_hereda_el_origen():
    # 19/11 «Disparo, …»; el 20/11 sólo el complemento: es la misma salida forzada.
    ayer = D.replace(day=19)
    segs = [seg(152, 0, 22, dia=ayer), seg(156, 22, 24, "Disparo, desconexión de la línea X.", dia=ayer),
            seg(156, 0, 4, "Desconexión de la línea X.")]
    v = variables(segs, D, D.replace(day=21), CFG, lambda d: None)
    assert (v["foh"], v["sin_clasificar"]) == (4, 0)


def test_origen_busca_el_inicio_de_la_cadena_y_su_estado_previo():
    from app.reports.indices import origen
    d17, d18, d19 = (D.replace(day=x) for x in (17, 18, 19))
    previos = [seg(152, 0, 5, dia=d17), seg(152, 6, 20, dia=d17),
               seg(156, 20, 24, "Disparo, x", dia=d17), seg(156, 0, 24, "X", dia=d18),
               seg(156, 0, 24, "X", dia=d19)]
    cadena = origen(previos, D)
    assert [(s["tipo"], s["ini"].day) for s in cadena] == [(152, 17), (156, 17), (156, 18), (156, 19)]
    assert origen([seg(152, 0, 5, dia=d19)], D) == []   # no termina en el borde: no hay cadena
