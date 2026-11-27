"""Temperatura de zonas térmicas: resumen del día y correlación con la punta."""
from datetime import datetime

import pytest

from app.reports.temperatura import correlacion, validar_rango


def test_correlacion_pide_10_pares_y_variacion():
    xs = [float(i) for i in range(12)]
    assert correlacion(xs, [2 * x + 1 for x in xs]) == 1.0
    assert correlacion(xs[:9], xs[:9]) is None
    assert correlacion([1.0] * 12, xs) is None


def test_rango_maximo():
    with pytest.raises(ValueError):
        validar_rango(datetime(2025, 1, 1), datetime(2026, 6, 1))


def test_consulta_horas_en_columnas_filas_por_fecha_y_zona(monkeypatch):
    from app.reports import temperatura as T
    monkeypatch.setattr(T, "_zonas_activas", lambda: [{"id": "ZTGCH01", "zona": "GUARACACHI"},
                                                      {"id": "ZTKNK01", "zona": "KENKO"}])
    d1, d2 = datetime(2026, 11, 19), datetime(2026, 11, 20)
    lect = [{"id": z, "fecha": d, "hora": h, "valor": base + h, "consolidado": 1}
            for d in (d1, d2) for z, base in (("ZTGCH01", 20), ("ZTKNK01", 5)) for h in range(24)]
    monkeypatch.setattr(T, "_lecturas", lambda ids, f1, f2: [x for x in lect if x["id"] in ids])
    r = T.consulta(d1, d2, [])
    assert [(x["fecha"], x["zona"]) for x in r["rows"]] == [
        ("19/11/2026", "Guaracachi"), ("19/11/2026", "Kenko"),
        ("20/11/2026", "Guaracachi"), ("20/11/2026", "Kenko")]
    assert r["rows"][0]["h14"] == 34.0
    assert (r["rows"][0]["maxima"], r["rows"][0]["hora_max"], r["rows"][0]["minima"]) == (43.0, "23:00", 20.0)
    assert [x["zona"] for x in T.consulta(d1, d1, ["ZTKNK01"])["rows"]] == ["Kenko"]
    with pytest.raises(ValueError):
        T.consulta(d1, datetime(2028, 1, 1), [])


def test_excel_plano_como_el_envio(monkeypatch):
    import openpyxl

    from app.reports import temperatura as T
    monkeypatch.setattr(T, "_zonas_activas", lambda: [{"id": "ZTWAR01", "zona": "WARNES"}, {"id": "ZTARJ01", "zona": "SUCRE"}])
    d = datetime(2024, 1, 1)
    lect = [{"id": z, "fecha": d, "hora": h, "valor": 10.0 + h, "consolidado": 1}
            for z in ("ZTWAR01", "ZTARJ01") for h in range(16)]
    monkeypatch.setattr(T, "_lecturas", lambda ids, f1, f2: [x for x in lect if x["id"] in ids])
    ws = openpyxl.load_workbook(T.excel_plano(d, d, [])).active
    filas = list(ws.iter_rows(values_only=True))
    assert filas[0][:4] == ("ZONA TÉRMICA", "FECHA", "00:00", "01:00") and len(filas[0]) == 26
    assert [f[0] for f in filas[1:]] == ["Sucre", "Warnes"]
    assert filas[1][1] == d and filas[1][2] == 10.0 and filas[1][25] is None
    assert ws.freeze_panes == "A2"


def test_interpolar_curva_y_promedio_horario():
    from app.reports.potencia_temperatura import (
        _codigo_curva,
        interpolar,
        promedio_horario,
    )
    curva = [(5.0, 70.0), (25.0, 62.0), (45.0, 53.0)]
    assert interpolar(curva, 26) == pytest.approx(61.55)
    assert interpolar(curva, 0) == 70.0 and interpolar(curva, 50) == 53.0
    assert _codigo_curva("ERI30") == ["CCERI30", "ERI30"] and _codigo_curva("GCH09") == ["GCH9COM", "GCH09"]
    assert _codigo_curva("ERI31") == ["ERI31"]
    h = promedio_horario({1: 1000, 2: 2000, 3: 3000, 4: 2000, 5: 1000})
    assert h[0] == 2.0 and h[1] is None


def test_efectiva_proxima_fuera_de_vigencia():
    from datetime import date

    from app.potencia_efectiva import efectiva, efectiva_proxima
    assert efectiva("GCH11", date(2019, 6, 1)) is None
    assert efectiva_proxima("GCH11", date(2019, 6, 1)) == efectiva("GCH11", date(2020, 11, 10))


def test_sin_excel_no_pesan_unidades_que_aun_no_existian(monkeypatch):
    # Enero 2019: AGU01 entra en OBJETOS el 06/07/2019; la vigencia más próxima (nov-2020) sí la trae.
    from datetime import date

    from app.potencia_efectiva import efectiva_proxima
    from app.reports import potencia_temperatura as PT

    def fake_query(sql, params=None):
        assert "objetos" in sql.lower() and params["dia"] == date(2019, 1, 15)
        return [{"codigo_objeto": "AGU01"}]
    monkeypatch.setattr(PT, "query", fake_query)
    pef, oficial = PT.efectiva_dia(["AGU01", "COR01"], date(2019, 1, 15))
    assert oficial is False and pef["AGU01"] is None
    assert pef["COR01"] == efectiva_proxima("COR01", date(2019, 1, 15))
