"""Generación de archivos Excel (.xlsx) a partir del resultado de un reporte.

Reproduce el estilo del export de la app original: título combinado, encabezado
resaltado, paneles congelados y formatos numéricos/fecha por columna.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

_HEADER_FILL = PatternFill("solid", fgColor="1E4E79")
_HEADER_FONT = Font(bold=True, color="FFFFFF", name="Calibri")
_TITLE_FONT = Font(bold=True, size=13, name="Arial Narrow")


def _num_format(fmt: str | None) -> str | None:
    if fmt == "datetime":
        return "dd/mm/yyyy hh:mm"
    if fmt and fmt.startswith("0."):
        return "#,##0." + "0" * (len(fmt.split(".")[1]))
    return None


def _num_format_exacto(v: Any) -> str | None:
    """Formato para columnas "num" (valor tal cual viene de la BD): miles y
    exactamente los decimales que trae el valor, sin redondear ni rellenar.
    Se decide por celda porque un formato fijo tipo "#,##0.###" deja la coma
    decimal colgando en los enteros."""
    if isinstance(v, bool) or not isinstance(v, (int, float, Decimal)):
        return None
    try:
        # normalize(): 12.0 se muestra "12", igual que en la grilla web.
        d = Decimal(repr(v) if isinstance(v, float) else str(v))
        exp = d.normalize().as_tuple().exponent
    except InvalidOperation:
        return None
    if not isinstance(exp, int):  # NaN / infinito
        return None
    dec = max(0, -exp)
    return "#,##0" + ("." + "0" * dec if dec else "")


def _llenar_hoja(ws, result: dict[str, Any], titulo: str, totales: bool = False) -> None:
    cols = [c for c in result["columns"] if not c.get("hidden")]
    ncols = len(cols)
    # Fila 1: título combinado.
    ws.cell(row=1, column=1, value=titulo).font = _TITLE_FONT
    if ncols > 1:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)

    # El Excel siempre lleva la fila TOTAL, así que su aclaración va siempre.
    aviso = " ".join(filter(None, [result.get("aviso"), result.get("aviso_total")])) or None
    header_row = 3 if aviso else 2
    if aviso:
        ws.cell(row=2, column=1, value=f"Nota: {aviso}").font = Font(italic=True, color="B45309")
        if ncols > 1:
            ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)

    # Encabezado.
    for j, c in enumerate(cols, start=1):
        cell = ws.cell(row=header_row, column=j, value=c["label"])
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Datos.
    fmt_by_col = [_num_format(c.get("format")) for c in cols]
    r = header_row + 1
    for row in result["rows"]:
        for j, c in enumerate(cols, start=1):
            v = row.get(c["key"])
            if c.get("format") == "datetime" and isinstance(v, str):
                try:
                    v = datetime.fromisoformat(v)
                except ValueError:
                    pass
            cell = ws.cell(row=r, column=j, value=v)
            if c.get("format") == "num":
                nf = _num_format_exacto(v)
            else:
                nf = fmt_by_col[j - 1]
            if nf and v is not None:
                cell.number_format = nf
        r += 1

    # Sin columnas sumables (p. ej. potencia de punta del SIN) no hay fila TOTAL que mostrar.
    if totales and result["rows"] and any(_es_sumable(c) for c in cols[1:]):
        _fila_total(ws, cols, result["rows"], header_row + 1, r)

    # Anchos aproximados.
    for j, c in enumerate(cols, start=1):
        width = max(10, min(40, len(str(c["label"])) + 2))
        ws.column_dimensions[get_column_letter(j)].width = width

    # Congelar encabezado + primera columna.
    ws.freeze_panes = ws.cell(row=header_row + 1, column=2)


def _es_sumable(c: dict[str, Any]) -> bool:
    f = c.get("format")
    return bool(f) and f != "datetime" and not c.get("sinTotal")


def _suma_limpia(vals) -> float:
    """Suma sin ruido binario: no más decimales que el sumando que más trae
    (misma regla que sumaLimpia en el frontend)."""
    nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    dec = 0
    for v in nums:
        t = repr(float(v))
        dec = max(dec, 10 if "e" in t else len(t.split(".")[1].rstrip("0")))
    return round(sum(nums), min(dec, 10))


def _fila_total(ws, cols, rows, first: int, r: int) -> None:
    """Fila TOTAL con fórmulas SUMA, mismas reglas que la grilla web: no suma
    columnas `sinTotal` y en grillas jerárquicas (`_nivel`) sólo el nivel 0."""
    drill = rows[0].get("_nivel") is not None
    # shortcut: SUMA admite 255 argumentos; en drill son los agentes (decenas).
    filas = [first + i for i, row in enumerate(rows)
             if (not drill or row.get("_nivel") == 0) and not row.get("_sinTotal")]
    ws.cell(row=r, column=1, value="TOTAL").font = Font(bold=True)
    for j, c in enumerate(cols, start=1):
        if j == 1 or not _es_sumable(c):
            continue
        L = get_column_letter(j)
        rango = f"{L}{first}:{L}{r - 1}" if not drill else ",".join(f"{L}{i}" for i in filas)
        cell = ws.cell(row=r, column=j, value=f"=SUM({rango})")
        cell.font = Font(bold=True)
        if c.get("format") == "num":
            vals = [rows[i - first].get(c["key"]) for i in filas]
            nf = _num_format_exacto(_suma_limpia(vals))
        else:
            nf = _num_format(c.get("format"))
        if nf:
            cell.number_format = nf


def build_workbook(result: dict[str, Any], titulo: str, totales: bool = False) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = (result.get("table") or "Reporte")[:31]
    _llenar_hoja(ws, result, titulo, totales)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_workbook_multi(hojas: list[tuple[str, dict[str, Any], str]],
                         totales: bool = False) -> BytesIO:
    """Un workbook con una hoja por elemento de `hojas`: (nombre, result, titulo)."""
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, result, titulo in hojas:
        ws = wb.create_sheet(nombre[:31])
        _llenar_hoja(ws, result, titulo, totales)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
