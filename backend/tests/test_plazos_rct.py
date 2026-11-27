from datetime import datetime

from app.sisfalla.plazos_rct import estado, plazo_final, plazo_preliminar

FALLA = datetime(2026, 11, 20, 23, 23)  # viernes


def test_plazo_preliminar_48_horas():
    assert plazo_preliminar(FALLA) == datetime(2026, 11, 22, 23, 23)


def test_plazo_final_8_dias_habiles_hasta_fin_del_dia():
    # lun 23 … vie 27 (5) + lun 30, mar 1, mié 2 (8)
    assert plazo_final(FALLA) == datetime(2026, 12, 2, 23, 59, 59)


def test_estado():
    p = datetime(2026, 11, 22, 12, 0)
    assert estado(p, datetime(2026, 11, 22, 11, 0), ahora=p) == "Enviado a tiempo"
    assert estado(p, datetime(2026, 11, 22, 13, 0), ahora=p) == "Enviado con retraso"
    assert estado(p, None, ahora=datetime(2026, 11, 22, 13, 0)) == "Vencido"
    assert estado(p, None, ahora=datetime(2026, 11, 21, 12, 0)) == "En plazo"
    assert estado(p, None, ahora=datetime(2026, 11, 22, 3, 0)) == "Por vencer"
