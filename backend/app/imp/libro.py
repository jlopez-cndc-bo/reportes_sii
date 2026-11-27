"""Helpers openpyxl para armar los anexos sobre la plantilla del estudio anterior."""
import csv
import re
from copy import copy
from datetime import datetime
from pathlib import Path

from openpyxl.drawing.image import Image
from openpyxl.worksheet.pagebreak import Break, RowBreak

ENCABEZADO = "Informe de la Programación de Mediano Plazo"
_FECHA = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_NUM = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")  # «1,270.30»: coma de miles
_PCT = re.compile(r"^-?\d+(\.\d+)?%$")


def leer_csv(path: Path) -> list[list[str]]:
    """CSV de Excel en español: cp1252 casi siempre; UTF-8 si viene de otra herramienta."""
    raw = path.read_bytes()
    try:
        texto = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = raw.decode("cp1252")
    return [fila for fila in csv.reader(texto.splitlines())]


def valor(s: str):
    """Texto del CSV → valor de celda (fecha dd/mm/aaaa, número, porcentaje o texto)."""
    s = s.strip()
    if not s:
        return None
    if _FECHA.match(s):
        d, m, a = s.split("/")
        return datetime(int(a), int(m), int(d))
    if _NUM.match(s):
        s = s.replace(",", "")
        return int(s) if "." not in s else float(s)
    if _PCT.match(s):
        return float(s[:-1]) / 100
    return s


def copiar_estilo(src, dst) -> None:
    if src.has_style:
        dst.font, dst.border, dst.fill = copy(src.font), copy(src.border), copy(src.fill)
        dst.number_format, dst.alignment = src.number_format, copy(src.alignment)
        dst.protection = copy(src.protection)


def estilos_fila(ws, fila: int) -> dict:
    """Foto del estilo de una fila de la plantilla (antes de limpiarla)."""
    return {"celdas": {c.column: c for c in ws[fila]}, "alto": ws.row_dimensions[fila].height}


def aplicar_fila(ws, fila: int, foto: dict, desde_col: int = 1) -> None:
    for col, src in foto["celdas"].items():
        if col >= desde_col:
            copiar_estilo(src, ws.cell(fila, col))
    if foto["alto"]:
        ws.row_dimensions[fila].height = foto["alto"]


def limpiar_desde(ws, fila: int) -> None:
    """Borra celdas, combinaciones y saltos desde `fila` hacia abajo (la plantilla queda arriba)."""
    for rango in [r for r in ws.merged_cells.ranges if r.max_row >= fila]:
        ws.unmerge_cells(str(rango))
    if ws.max_row >= fila:
        ws.delete_rows(fila, ws.max_row - fila + 1)
    for r in list(ws.row_dimensions):
        if r >= fila:
            del ws.row_dimensions[r]
    ws.row_breaks = RowBreak()


def extender_area(ws, ultima_fila: int) -> None:
    """Conserva el área de impresión de la plantilla (inicio y columnas: los títulos se repiten
    por página) y sólo mueve la última fila a la de los datos nuevos."""
    area = ws.print_area
    if not area:
        return
    ref = (area[0] if isinstance(area, (list, tuple)) else area).split("!")[-1].replace("$", "")
    ws.print_area = re.sub(r"\d+$", str(ultima_fila), ref)


def salto(ws, fila: int) -> None:
    """Salto de página después de `fila`."""
    ws.row_breaks.append(Break(id=fila))


def actualizar_encabezado(wb, periodo: str) -> None:
    for ws in wb.worksheets:
        for fila in ws.iter_rows(max_row=3):
            for c in fila:
                if isinstance(c.value, str) and c.value.strip().startswith(ENCABEZADO):
                    c.value = f"{ENCABEZADO} {periodo}"


def quitar_vinculos(wb) -> None:
    """Las plantillas de la GP traen vínculos a otros libros (MB de caché y el aviso «actualizar
    vínculos» al abrir) y nombres rotos. El anexo sólo lleva valores: se quitan."""
    wb._external_links = []
    malos = lambda dn: "[" in (dn.attr_text or "") or "#REF!" in (dn.attr_text or "")
    for nombres in [wb.defined_names, *(ws.defined_names for ws in wb.worksheets)]:
        for k in [k for k, dn in nombres.items() if malos(dn)]:
            del nombres[k]


def copiar_hoja(src, dst) -> None:
    """Copia valores (ya calculados) y formato del área de impresión de `src` en `dst` vacía."""
    area = src.print_area
    max_r, max_c = src.max_row, src.max_column
    if area:
        ref = (area[0] if isinstance(area, (list, tuple)) else area).split("!")[-1].replace("$", "")
        from openpyxl.utils.cell import range_boundaries
        _, _, max_c, max_r = range_boundaries(ref)
    for fila in src.iter_rows(max_row=max_r, max_col=max_c):
        for c in fila:
            if c.value is None and not c.has_style:
                continue
            d = dst.cell(c.row, c.column, c.value)
            copiar_estilo(c, d)
    for rango in src.merged_cells.ranges:
        if rango.max_row <= max_r and rango.max_col <= max_c:
            dst.merge_cells(str(rango))
    for k, dim in src.column_dimensions.items():
        dst.column_dimensions[k].width = dim.width
        dst.column_dimensions[k].hidden = dim.hidden
    for k, dim in src.row_dimensions.items():
        if k <= max_r:
            dst.row_dimensions[k].height = dim.height
            dst.row_dimensions[k].hidden = dim.hidden
    dst.page_setup.orientation = src.page_setup.orientation
    dst.page_setup.paperSize = src.page_setup.paperSize
    dst.page_setup.scale = src.page_setup.scale
    dst.page_setup.fitToWidth, dst.page_setup.fitToHeight = src.page_setup.fitToWidth, src.page_setup.fitToHeight
    dst.sheet_properties.pageSetUpPr = copy(src.sheet_properties.pageSetUpPr)
    dst.page_margins = copy(src.page_margins)
    dst.print_options = copy(src.print_options)
    dst.sheet_view.showGridLines = src.sheet_view.showGridLines
    if area:
        dst.print_area = (area[0] if isinstance(area, (list, tuple)) else area).split("!")[-1]
    if src.print_title_rows:
        dst.print_title_rows = src.print_title_rows
    for b in src.row_breaks.brk:
        if b.id <= max_r:
            salto(dst, b.id)


def reemplazar_hoja(wb, titulo: str, src) -> None:
    """La hoja `titulo` de la plantilla pasa a ser una copia de `src` (mismo lugar en el libro)."""
    idx = wb.index(wb[titulo])
    wb.remove(wb[titulo])
    copiar_hoja(src, wb.create_sheet(titulo, idx))


def poner_imagen(ws, path: Path, ancla: str = "A7", max_ancho: int = 875, max_alto: int = 900) -> None:
    """Reemplaza las imágenes de la hoja por `path`, escalada a la caja que ocupaba en la plantilla."""
    ws._images = []
    img = Image(str(path))
    k = min(max_ancho / img.width, max_alto / img.height)
    img.width, img.height = int(img.width * k), int(img.height * k)
    ws.add_image(img, ancla)
