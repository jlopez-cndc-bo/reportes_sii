from datetime import datetime

from app.smec import capacidad as C
from app.smec.reportes import energia_enriquecida

F1, F2 = datetime(2026, 10, 1), datetime(2026, 10, 1)  # 1 día = 24 h


def test_relacion_sin_duplicados():
    centrales = [c for _, cens in C.GRUPOS for c in cens]
    sistemas = [s for sis, _ in C.GRUPOS for s in sis]
    assert len(centrales) == len(set(centrales))
    assert len(sistemas) == len(set(sistemas))


def _fake(monkeypatch):
    monkeypatch.setattr(C, "GRUPOS", [((1,), (10, 11)), ((2, 3), (20,))])
    monkeypatch.setattr(C, "_GRUPO_DE_CENTRAL", {10: 0, 11: 0, 20: 1})
    monkeypatch.setattr(C, "_sistemas", lambda f2: {
        1: {"nombre": "Corani", "tipo": "HID", "cap_efec": 100.0},
        2: {"nombre": "Aguaí", "tipo": "BIO", "cap_efec": 10.0},
        3: {"nombre": "Aguaí 02", "tipo": "BIO", "cap_efec": 40.0},
    })
    monkeypatch.setattr(C, "_energia", lambda f1, f2, ids: {
        10: {"cod": "CH A", "energia": 1_200_000.0},
        11: {"cod": "CH B", "energia": 1_200_000.0},
        20: {"cod": "CT C", "energia": 600_000.0},
        99: {"cod": "CT X", "energia": 50.0},
    })


def test_capacidad_por_sistema(monkeypatch):
    _fake(monkeypatch)
    r = C.capacidad_sistema(F1, F2, [10, 11, 20, 99], "iny")
    cor, agu, sin = r["rows"]
    assert (cor["sistema"], cor["centrales"], cor["tecnologia"]) == ("Corani", "CH A + CH B", "Hidroeléctrica")
    assert cor["factor"] == 1.0                      # 2.400.000 kWh / (100 MW × 1000 × 24 h)
    assert (agu["sistema"], agu["cap_efec"], agu["factor"]) == ("Aguaí + Aguaí 02", 50.0, 0.5)
    assert (sin["tecnologia"], sin["factor"]) == ("Sin clasificar", None)
    assert "aviso" not in r


def test_seleccion_parcial_y_retiro(monkeypatch):
    _fake(monkeypatch)
    r = C.capacidad_sistema(F1, F2, [10], "iny")
    assert r["rows"][0]["centrales"] == "CH A" and "Corani" in r["aviso"]
    assert C.capacidad_sistema(F1, F2, [10], "ret")["rows"] == []


def test_mix(monkeypatch):
    _fake(monkeypatch)
    rows = C.mix_tecnologia(F1, F2, [10, 11, 20, 99], "iny")["rows"]
    assert [r["tecnologia"] for r in rows] == ["Hidroeléctrica", "Biomasa", "Sin clasificar"]
    assert rows[0]["part"] == round(2_400_000 * 100 / 3_000_050, 10)
    assert rows[2]["cap_efec"] is None and rows[2]["factor"] is None


def test_columna_tecnologia_despues_de_central():
    res = {"columns": [{"key": "agente"}, {"key": "central"}, {"key": "total"}],
           "rows": [{"agente": "A", "central": "CT GCH", "total": 1.0},
                    {"agente": "A", "central": "CT ???", "total": 1.0}]}
    out = energia_enriquecida(lambda *a: res, F1, F2, [], "iny", "ninguno", {"CT GCH": "Térmica"})
    assert [c["key"] for c in out["columns"]][:3] == ["agente", "central", "tecnologia"]
    assert [r["tecnologia"] for r in out["rows"]] == ["Térmica", "Sin clasificar"]
