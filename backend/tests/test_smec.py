"""Tests de funciones puras del módulo SMEC (sin BD)."""
from app.smec import reportes as R


def test_interval_labels_15min():
    labs = R._interval_labels(96)
    assert labs[0] == "00:00"
    assert labs[1] == "00:15"
    assert labs[-1] == "23:45"
    assert len(labs) == 96


def test_interval_labels_hora():
    labs = R._interval_labels(24)
    assert labs[0] == "00:00"
    assert labs[1] == "01:00"
    assert len(labs) == 24


def test_target_direccion():
    assert R._target("iny") == -1
    assert R._target("ret") == 1


def test_idx():
    cols = ["AGENTE", "DIR", "I1", "I2"]
    assert R._idx(cols, "DIR") == 1
    assert R._idx(cols, "NOPE") == -1


def test_csv():
    assert R._csv([3, 9, 1]) == "3, 9, 1" or R._csv([3, 9, 1]) == "3,9,1"
    assert R._csv([]) is None


def test_filtrar_dir():
    cols = ["AGENTE", "DIR", "I1"]
    rows = [("A", -1, 10), ("B", 1, 20), ("C", -1, 30)]
    iny = R._filtrar_dir(cols, rows, "iny")
    assert [r[0] for r in iny] == ["A", "C"]
    ret = R._filtrar_dir(cols, rows, "ret")
    assert [r[0] for r in ret] == ["B"]
