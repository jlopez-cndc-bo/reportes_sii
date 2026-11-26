"""Lógica pura de potencia limitada (sin BD)."""
from datetime import date, datetime

from app.smec.potencia_limitada import _max_medido, efectiva


def test_efectiva_por_vigencia_y_sin_dato_concreto():
    assert efectiva("WAR21", date(2026, 11, 15)) == 64.04   # ciclo combinado: valor CC
    assert efectiva("WAR05", date(2026, 11, 15)) == 44.33   # = Warnes 51
    assert efectiva("GCH12", date(2026, 11, 15)) is None    # vapor: depende del estado
    assert efectiva("WAR21", date(2026, 10, 31)) == 64.04   # vigencia may–oct 2026
    assert efectiva("WAR21", date(2020, 10, 31)) is None    # antes de la primera vigencia
    assert efectiva("WAR21", date(2027, 5, 1)) is None      # semestre no cargado


def test_max_medido_solo_intervalos_que_se_superponen():
    m = [(datetime(2026, 11, 10, 10, 0), 100.0), (datetime(2026, 11, 10, 10, 15), 300.0),
         (datetime(2026, 11, 10, 10, 30), 900.0)]
    # [10:17, 10:30) toca sólo el intervalo 10:15-10:30
    assert _max_medido(m, datetime(2026, 11, 10, 10, 17), datetime(2026, 11, 10, 10, 30)) == 300.0
    assert _max_medido(m, datetime(2026, 11, 10, 12, 0), datetime(2026, 11, 10, 13, 0)) is None
