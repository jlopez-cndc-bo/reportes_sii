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
