"""% por central ponderado por potencia efectiva (sin BD: query y report simulados)."""
from datetime import datetime

from app.reports import horas_disponibilidad as hd


def test_pondera_por_potencia_y_cuenta_unidades_sin_eventos(monkeypatch):
    # Marcado: COR01. Corani tiene COR01..05; sólo COR01 tuvo 24 h fuera en 2 días (48 h).
    def fake_query(sql, params=None):
        if "DISTINCT codigo_objeto" in sql:
            return [{"codigo_objeto": "COR01"}]
        return [{"id_objeto": i} for i in range(1, 6)]
    monkeypatch.setattr(hd, "query", fake_query)
    monkeypatch.setattr(hd, "report", lambda *a, **k: {"rows": [
        {"codigo_objeto": "COR01", "hora_desconectadas": 24.0, "total": 48}]})
    res = hd.report_central(datetime(2026, 11, 1), datetime(2026, 11, 2), [1])
    fila = res["rows"][0]
    pesos = {"COR01": 12.91, "COR02": 12.79, "COR03": 13.25, "COR04": 13.31, "COR05": 12.99}
    esperado = round((12.91 * 24 + sum(pesos.values()) * 48 - 12.91 * 48)
                     / (48 * sum(pesos.values())) * 100, 2)
    assert fila["central"] == "Corani" and fila["unidades"] == 5
    assert fila["disponibilidad"] == esperado          # ≈ 90,1 % (no 50 % ni 80 %)
    assert "vigencia 01/11/2026 al 30/04/2027" in res["aviso"]


def test_sin_vigencia_usa_la_mas_proxima_y_avisa(monkeypatch):
    monkeypatch.setattr(hd, "query", lambda sql, params=None: (
        [{"codigo_objeto": "COR01"}] if "DISTINCT" in sql else [{"id_objeto": 1}]))
    monkeypatch.setattr(hd, "report", lambda *a, **k: {"rows": []})
    res = hd.report_central(datetime(2019, 1, 1), datetime(2019, 1, 31), [1])
    assert res["rows"][0]["disponibilidad"] == 100.0
    assert "vigencia 01/11/2020" in res["aviso"] and "más próxima" in res["aviso"]


def test_unidades_que_no_existian_no_pesan(monkeypatch):
    # Aguaí en 2021: sólo AGU01 figura en la vigencia; AGU02/03 aún no existían.
    monkeypatch.setattr(hd, "query", lambda sql, params=None: (
        [{"codigo_objeto": "AGU01"}] if "DISTINCT" in sql else [{"id_objeto": 1}]))
    monkeypatch.setattr(hd, "report", lambda *a, **k: {"rows": [
        {"codigo_objeto": "AGU01", "hora_desconectadas": 24.0, "total": 48}]})
    fila = hd.report_central(datetime(2021, 1, 1), datetime(2021, 1, 2), [1])["rows"][0]
    assert fila["unidades"] == 1 and fila["disponibilidad"] == 50.0
