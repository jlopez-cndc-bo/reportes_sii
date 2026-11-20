"""Tests de generación de workbooks (sin BD)."""
from openpyxl import load_workbook

from app.export_excel import build_workbook, build_workbook_multi

_RESULT = {
    "table": "DEMO",
    "columns": [{"key": "a", "label": "A"}, {"key": "b", "label": "B", "format": "0.0"}],
    "rows": [{"a": "x", "b": 1.5}, {"a": "y", "b": 2.25}],
}


def test_build_workbook_hoja_unica():
    buf = build_workbook(_RESULT, "Título")
    wb = load_workbook(buf)
    assert wb.sheetnames == ["DEMO"]
    ws = wb["DEMO"]
    assert ws.cell(row=1, column=1).value == "Título"
    assert ws.cell(row=2, column=1).value == "A"
    assert ws.cell(row=3, column=1).value == "x"


def test_formato_fijo_se_mantiene():
    ws = load_workbook(build_workbook(_RESULT, "T"))["DEMO"]
    assert ws.cell(row=4, column=2).value == 2.25
    assert ws.cell(row=4, column=2).number_format == "#,##0.0"


def test_formato_num_muestra_el_valor_sin_redondear():
    result = {
        "table": "SMEC",
        "columns": [{"key": "n", "label": "N"}, {"key": "v", "label": "V", "format": "num"}],
        "rows": [{"n": "a", "v": 1234.5678}, {"n": "b", "v": 45}, {"n": "c", "v": 12.0},
                 {"n": "d", "v": 1e-07}, {"n": "e", "v": None}],
    }
    ws = load_workbook(build_workbook(result, "T"))["SMEC"]
    celdas = [ws.cell(row=r, column=2) for r in range(3, 8)]
    assert [c.value for c in celdas[:4]] == [1234.5678, 45, 12, 1e-07]
    assert [c.number_format for c in celdas] == [
        "#,##0.0000", "#,##0", "#,##0", "#,##0.0000000", "General"]


def test_build_workbook_multi_una_hoja_por_direccion():
    buf = build_workbook_multi([
        ("Inyección", _RESULT, "Título Iny"),
        ("Retiro", _RESULT, "Título Ret"),
    ])
    wb = load_workbook(buf)
    assert wb.sheetnames == ["Inyección", "Retiro"]
    assert wb["Inyección"].cell(row=1, column=1).value == "Título Iny"
    assert wb["Retiro"].cell(row=1, column=1).value == "Título Ret"
    # Cada hoja arranca de cero (no hereda la hoja 'Sheet' por defecto).
    assert wb["Inyección"].cell(row=3, column=1).value == "x"


def test_fila_total_suma_por_periodo_y_respeta_sin_total():
    res = {"table": "E", "columns": [
        {"key": "c", "label": "Central"},
        {"key": "d0", "label": "01/10", "format": "num"},
        {"key": "p", "label": "Part. %", "format": "0.0", "sinTotal": True}],
        "rows": [{"c": "A", "d0": 1.5, "p": 60.0}, {"c": "B", "d0": 1, "p": 40.0}]}
    ws = load_workbook(build_workbook(res, "T", totales=True))["E"]
    assert ws.cell(row=5, column=1).value == "TOTAL"
    assert ws.cell(row=5, column=2).value == "=SUM(B3:B4)"
    assert ws.cell(row=5, column=3).value is None
    # Sin totales pedidos (INDISP/SISFALLA) no hay fila extra.
    ws = load_workbook(build_workbook(res, "T"))["E"]
    assert ws.cell(row=5, column=1).value is None


def test_fila_total_drill_suma_solo_nivel_0():
    res = {"table": "POT_DRILL", "columns": [
        {"key": "n", "label": "Nombre"}, {"key": "h0", "label": "00:15", "format": "num"}],
        "rows": [{"n": "AG1", "h0": 10, "_nivel": 0}, {"n": "C1", "h0": 10, "_nivel": 1},
                 {"n": "AG2", "h0": 5, "_nivel": 0}]}
    ws = load_workbook(build_workbook(res, "T", totales=True))["POT_DRILL"]
    assert ws.cell(row=6, column=2).value == "=SUM(B3,B5)"


def test_fila_total_drill_omite_filas_sin_total():
    # HFD: Exportación se muestra en nivel 0 pero no suma en el TOTAL del SIN.
    res = {"table": "HFD", "columns": [
        {"key": "n", "label": "Nombre"}, {"key": "h0", "label": "00:00", "format": "num"}],
        "rows": [{"n": "Termo", "h0": 10, "_nivel": 0}, {"n": "Exportación", "h0": 5, "_nivel": 0, "_sinTotal": True}]}
    ws = load_workbook(build_workbook(res, "T", totales=True))["HFD"]
    assert ws.cell(row=5, column=2).value == "=SUM(B3)"


def test_suma_limpia_sin_ruido_en_millones():
    from app.export_excel import _suma_limpia
    assert _suma_limpia([11011701.555, 11011701.555, 11011701.555]) == 33035104.665
    assert _suma_limpia([1, 2, None, "x"]) == 3


def test_sin_columnas_sumables_no_hay_fila_total():
    res = {"table": "P", "columns": [{"key": "f", "label": "Fecha"},
                                     {"key": "t", "label": "Total", "format": "num", "sinTotal": True}],
           "rows": [{"f": "01/10", "t": 5}]}
    ws = load_workbook(build_workbook(res, "T", totales=True))["P"]
    assert ws.max_row == 3


def test_aviso_total_siempre_va_en_el_excel():
    res = {**_RESULT, "aviso": "Hoy incompleto.", "aviso_total": "TOTAL = SIN."}
    ws = load_workbook(build_workbook(res, "T"))["DEMO"]
    assert ws.cell(row=2, column=1).value == "Nota: Hoy incompleto. TOTAL = SIN."
