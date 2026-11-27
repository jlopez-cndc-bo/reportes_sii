"""Generadores de los anexos del IMP (2, 4, 5 y 6; el 3 queda para la base IMP en Oracle).

Cada anexo parte de la plantilla ANEXOn.xlsx del estudio más reciente que la tenga (formato
exacto de la GP) y reemplaza los datos con los archivos del estudio. Sólo se genera el .xlsx:
nunca se escribe en la carpeta del estudio.
"""
import fnmatch
import io
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import openpyxl

from . import libro
from .estudios import Estudio


@dataclass(frozen=True)
class Requisito:
    etiqueta: str          # lo que se muestra si falta
    patrones: tuple        # glob sin distinguir mayúsculas, dentro de la carpeta AnexoN
    opcional: bool = False


ANEXOS = {
    2: {"contenido": "2A mapa del Sistema Troncal · 2B diagrama unifilar", "reqs": (
        Requisito("Anexo2/Mapa_*.jpeg|jpg|png", ("mapa_*.jpeg", "mapa_*.jpg", "mapa_*.png")),
        Requisito("Anexo2/Anexo2B.png|jpg", ("anexo2b.png", "anexo2b.jpg", "anexo2b.jpeg")),
    )},
    4: {"contenido": "4A diferencias entre declaraciones · 4B transmisión simulada · 4C consumos propios y pérdidas", "reqs": (
        Requisito("Anexo4/ANEXO4A.csv", ("anexo4a.csv",)),
        Requisito("Anexo4/Anexo4B.png|jpg", ("anexo4b.png", "anexo4b.jpg", "anexo4b.jpeg")),
        Requisito("Anexo4/ANEXO4C.csv", ("anexo4c.csv",)),
    )},
    5: {"contenido": "5A programa de mantenimientos ≥ 4 días · 5B estadística de desconexión < 4 días", "reqs": (
        Requisito("Anexo5/ListadoFinaldeMantenimientos.csv", ("listadofinaldemantenimientos.csv",)),
        Requisito("Anexo5/PorcentajeMenor4Dias.csv", ("porcentajemenor4dias.csv",)),
    )},
    6: {"contenido": "6A/6B hidroeléctricas · 6C temperaturas · 6D capacidad térmica · 6E régimen · 6F características · 6G reserva rotante", "reqs": (
        Requisito("Anexo6/Anexo6A_6B.xlsx", ("anexo6a_6b.xlsx",)),
        Requisito("Anexo6/Anexo6C.xlsx", ("anexo6c.xlsx",)),
        Requisito("Anexo6/TempMedia<año>.csv", ("tempmedia*.csv",), opcional=True),
        Requisito("Anexo6/Anexo6D.xlsx", ("anexo6d.xlsx",)),
        Requisito("Anexo6/RegimenOper.csv", ("regimenoper.csv",)),
        Requisito("Anexo6/Anexo6F.xlsx", ("anexo6f.xlsx",)),
        Requisito("Anexo6/FactTermp.csv", ("facttermp.csv",)),
    )},
}


def buscar(carpeta: Path, patrones) -> Path | None:
    """Primer archivo que calza (sin distinguir mayúsculas: el servidor es Linux). El último en
    orden alfabético, para que TempMedia2026 gane a TempMedia2025."""
    if not carpeta.is_dir():
        return None
    hits = sorted(p for p in carpeta.iterdir() if p.is_file() and not p.name.startswith("~$")
                  and any(fnmatch.fnmatch(p.name.lower(), pat) for pat in patrones))
    return hits[-1] if hits else None


def plantilla(n: int, estudio: Estudio, anteriores: list[Estudio]) -> Path | None:
    for e in [estudio, *anteriores]:
        p = buscar(e.carpeta / f"Anexo{n}", (f"anexo{n}.xlsx",))
        if p:
            return p
    return None


def estado(n: int, estudio: Estudio, anteriores: list[Estudio]) -> dict:
    """Qué falta para generar el anexo n (sin abrir los archivos)."""
    carpeta = estudio.carpeta / f"Anexo{n}"
    faltan, avisos = [], []
    tpl = plantilla(n, estudio, anteriores)
    if tpl is None:
        faltan.append(f"Anexo{n}/ANEXO{n}.xlsx (plantilla, en este estudio o en uno anterior)")
    elif tpl.parent.parent != estudio.carpeta:
        avisos.append(f"Formato tomado del estudio {tpl.parent.parent.name}.")
    for r in ANEXOS[n]["reqs"]:
        if not buscar(carpeta, r.patrones):
            (avisos if r.opcional else faltan).append(
                f"Sin {r.etiqueta}: la hoja queda como en la plantilla." if r.opcional else r.etiqueta)
    return {"anexo": n, "contenido": ANEXOS[n]["contenido"], "faltan": faltan, "avisos": avisos}


@dataclass
class Contexto:
    estudio: Estudio
    carpeta: Path
    avisos: list = field(default_factory=list)

    def archivo(self, n_req: int) -> Path | None:
        n = int(self.carpeta.name[-1])
        return buscar(self.carpeta, ANEXOS[n]["reqs"][n_req].patrones)


def generar(n: int, estudio: Estudio, anteriores: list[Estudio]) -> tuple[bytes, list[str]]:
    est = estado(n, estudio, anteriores)
    if est["faltan"]:
        raise FileNotFoundError("Faltan archivos: " + "; ".join(est["faltan"]))
    wb = openpyxl.load_workbook(plantilla(n, estudio, anteriores))
    ctx = Contexto(estudio, estudio.carpeta / f"Anexo{n}", list(est["avisos"]))
    _GENERADORES[n](wb, ctx)
    libro.actualizar_encabezado(wb, estudio.periodo)
    libro.quitar_vinculos(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), ctx.avisos


# ---------------------------------------------------------------- Anexo 2 y 4B: imágenes

def _anexo2(wb, ctx: Contexto) -> None:
    libro.poner_imagen(wb["ANEXO2A"], ctx.archivo(0))
    libro.poner_imagen(wb["ANEXO2B"], ctx.archivo(1))


# ---------------------------------------------------------------- Anexo 4: CSV = área B4

def _tipo(vals: list) -> str:
    llenas = [v for v in vals if v not in (None, "")]
    if not llenas:
        return "vacia"
    if any(isinstance(v, str) and ("gina " in v or v.startswith("Pag")) for v in llenas):
        return "pagina"
    if len(llenas) == 1 and vals[0] not in (None, ""):
        return "titulo"
    return "dato"


def csv_en_hoja(ws, filas: list[list[str]], fila0: int = 4, col0: int = 2) -> None:
    """El CSV es la hoja exportada desde la celda B4: se reescribe esa área con el formato de la
    plantilla, tomando el estilo de la misma fila si es del mismo tipo (encabezados) o, si no,
    de la primera fila de ese tipo en el cuerpo."""
    ancho = max(len(f) for f in filas)
    tpl, primero = {}, {}
    for r in range(fila0, ws.max_row + 1):
        t = _tipo([ws.cell(r, c).value for c in range(col0, col0 + ancho)])
        tpl[r] = (t, libro.estilos_fila(ws, r))
    cuerpo = next((r for r, (t, _) in tpl.items() if t == "dato"), fila0)
    for r, (t, foto) in tpl.items():
        if r >= cuerpo:
            primero.setdefault(t, foto)
    libro.limpiar_desde(ws, fila0)
    paginas = 0
    for i, fila in enumerate(filas):
        r = fila0 + i
        vals = [libro.valor(s) for s in fila]
        t = _tipo(vals)
        mismo = tpl.get(r)
        foto = mismo[1] if mismo and mismo[0] == t and r < cuerpo else primero.get(t, mismo[1] if mismo else None)
        if foto:
            libro.aplicar_fila(ws, r, foto)
        if mismo:  # mismo alto que la plantilla en esa fila: la paginación queda igual
            ws.row_dimensions[r].height = mismo[1]["alto"]
        for j, v in enumerate(vals):
            if v is None:
                continue
            c = ws.cell(r, col0 + j, v)
            if isinstance(v, float) and fila[j].strip().endswith("%"):
                c.number_format = "0.00%"
            elif isinstance(v, datetime):
                c.number_format = "dd/mm/yyyy"
        if t == "pagina":
            paginas += 1
            if paginas > 1:
                libro.salto(ws, r - 1)
    ultima = fila0 + len(filas) - 1
    libro.extender_area(ws, ultima)


def _anexo4(wb, ctx: Contexto) -> None:
    csv_en_hoja(wb["ANEXO4A"], libro.leer_csv(ctx.archivo(0)))
    libro.poner_imagen(wb["ANEXO4B"], ctx.archivo(1))
    csv_en_hoja(wb["ANEXO4C"], libro.leer_csv(ctx.archivo(2)))


# ---------------------------------------------------------------- Anexo 5

def mantenimientos_por_anio(filas: list[list[str]], desde: int, hasta: int) -> dict[int, list]:
    """Cada mantenimiento recortado a cada año calendario que toca: (unidad, inicio, fin, días)."""
    tramos: dict[str, list] = {}
    for f in filas[1:]:
        if len(f) < 3 or not f[0].strip():
            continue
        u, ini, fin = f[0].strip(), libro.valor(f[1]), libro.valor(f[2])
        if not isinstance(ini, datetime) or not isinstance(fin, datetime) or fin < ini:
            raise ValueError(f"ListadoFinaldeMantenimientos.csv: fechas inválidas en {','.join(f)}")
        tramos.setdefault(u, []).append([ini, fin])
    unidos = []
    for u, ts in tramos.items():  # tramos superpuestos de una unidad = un solo mantenimiento (como la GP)
        ts.sort()
        actual = ts[0]
        for t in ts[1:]:
            if t[0] <= actual[1]:
                actual[1] = max(actual[1], t[1])
            else:
                unidos.append((u, *actual))
                actual = t
        unidos.append((u, *actual))
    out = {a: [] for a in range(desde, hasta + 1)}
    for u, ini, fin in unidos:
        for a in range(max(ini.year, desde), min(fin.year, hasta) + 1):
            i, x = max(ini, datetime(a, 1, 1)), min(fin, datetime(a, 12, 31))
            out[a].append((u, i, x, (x - i).days + 1))
    for items in out.values():
        items.sort(key=lambda t: (t[1], t[0]))  # a igual inicio la GP ordena a mano; acá, por unidad
    return out


def _anexo5a(ws, ctx: Contexto, filas) -> None:
    fpag = next(c.row for fila in ws.iter_rows() for c in fila
                if isinstance(c.value, str) and c.value.strip().startswith("Página"))
    cpag = next(c.column for c in ws[fpag] if isinstance(c.value, str) and c.value.strip().startswith("Página"))
    fotos = {k: libro.estilos_fila(ws, fpag + k) for k in range(5)}  # página, títulos, blanco, año, dato
    titulos = [(c.column, c.value) for c in ws[fpag + 1] if c.value is not None]
    bloques = [col for col, v in titulos if str(v).strip().upper() == "UNIDAD"]
    merges = [(r.min_row - fpag, r.min_col, r.max_row - fpag, r.max_col) for r in ws.merged_cells.ranges
              if fpag <= r.min_row <= fpag + 1]
    por_anio = mantenimientos_por_anio(filas, ctx.estudio.inicio.year, ctx.estudio.fin.year)
    anios = list(por_anio)
    paginas = [anios[i:i + 2] for i in range(0, len(anios), 2)]  # dos años por página, como la GP
    libro.limpiar_desde(ws, fpag)
    r = fpag
    for p, grupo in enumerate(paginas, 1):
        if p > 1:
            libro.salto(ws, r - 1)
        for k in range(3):
            libro.aplicar_fila(ws, r + k, fotos[k])
        ws.cell(r, cpag, f"Página {p} de {len(paginas)}")
        for col, v in titulos:
            ws.cell(r + 1, col, v)
        for dr, c1, dr2, c2 in merges:
            ws.merge_cells(start_row=r + dr, start_column=c1, end_row=r + dr2, end_column=c2)
        r += 3
        for a in grupo:
            libro.aplicar_fila(ws, r, fotos[3])
            ws.cell(r, 1, a)
            items = por_anio[a]
            alto = max(1, math.ceil(len(items) / len(bloques)))
            for k in range(alto):
                libro.aplicar_fila(ws, r + 1 + k, fotos[4])
            for i, (u, ini, fin, dias) in enumerate(items):
                fila, col = r + 1 + i % alto, bloques[i // alto]
                for j, v in enumerate((u, ini, fin, dias)):
                    ws.cell(fila, col + j, v)
            r += 1 + alto
    libro.extender_area(ws, r - 1)


def _norm_unidad(u: str) -> str:
    """GCH01 (CSV) ≡ GCH1 (encabezado de 5B)."""
    m = re.match(r"^([A-Z]+)0*(\d+)$", u.strip().upper())
    return f"{m.group(1)}{m.group(2)}" if m else u.strip().upper()


def _anexo5b4(ws, ctx: Contexto, filas) -> None:
    fhead = next(c.row for c in ws["B"] if isinstance(c.value, str) and c.value.strip().upper() == "UNIDAD")
    cols = {_norm_unidad(c.value): c.column for c in ws[fhead] if isinstance(c.value, str) and c.column > 2}
    meses = [libro.valor(s) for s in filas[0][1:13]]
    fila_de = {c.value: c.row for c in ws["B"] if isinstance(c.value, datetime)}
    faltan = [m for m in meses if m not in fila_de]
    if faltan:  # año nuevo: 12 filas más al final del histórico, con el formato de la última
        ultima = max(fila_de.values())
        foto = libro.estilos_fila(ws, ultima)
        bajo = [r for r in ws.merged_cells.ranges if r.min_row > ultima]
        for r in bajo:
            ws.unmerge_cells(str(r))
        ws.insert_rows(ultima + 1, len(faltan))
        for r in bajo:
            ws.merge_cells(start_row=r.min_row + len(faltan), start_column=r.min_col,
                           end_row=r.max_row + len(faltan), end_column=r.max_col)
        for k, m in enumerate(faltan):
            libro.aplicar_fila(ws, ultima + 1 + k, foto)
            ws.cell(ultima + 1 + k, 2, m)
            fila_de[m] = ultima + 1 + k
        ctx.avisos.append(f"5B4: se agregaron {len(faltan)} meses nuevos al histórico.")
    fila_txt = {str(c.value).strip().upper(): c.row for c in ws["B"] if isinstance(c.value, str)}
    sin_columna = []
    for f in filas[1:]:
        if not f or not f[0].strip():
            continue
        col = cols.get(_norm_unidad(f[0]))
        if col is None:
            sin_columna.append(f[0].strip())
            continue
        for m, s in zip(meses, f[1:13]):
            ws.cell(fila_de[m], col, libro.valor(s))
        for etiqueta, s in (("TOTAL", f[13] if len(f) > 13 else ""), ("TASA ANUAL", f[14] if len(f) > 14 else "")):
            if etiqueta in fila_txt and s.strip():
                ws.cell(fila_txt[etiqueta], col, libro.valor(s))
    if sin_columna:
        ctx.avisos.append("5B4: unidades del CSV sin columna en la hoja: " + ", ".join(sin_columna))


def _anexo5(wb, ctx: Contexto) -> None:
    _anexo5a(wb["ANEXO5A"], ctx, libro.leer_csv(ctx.archivo(0)))
    _anexo5b4(wb["ANEXO5B4"], ctx, libro.leer_csv(ctx.archivo(1)))


# ---------------------------------------------------------------- Anexo 6

# Columna de TempMedia<año>.csv → bloque de la hoja 6C.
TEMP_BLOQUES = {"GCH": "GUARACACHI", "CAR": "CARRASCO", "VHE": "VALLE HERMOSO", "KEN": "KENKO",
                "ARJ": "ARANJUEZ", "TRD": "TRINIDAD", "YAG": "YAGUACUA", "WAR": "WARNES"}


_AVERAGE = re.compile(r"^=\+?AVERAGE\(\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)\)$", re.IGNORECASE)


def _promedios(ws_formulas) -> dict:
    """Celdas «Promedio» con el rango de su fórmula AVERAGE: (fila, col) → [r1, c1, r2, c2].
    Se respeta el rango de la GP (p. ej. el primer año incompleto queda fuera)."""
    from openpyxl.utils import column_index_from_string as ci
    out = {}
    for fila in ws_formulas.iter_rows():
        for c in fila:
            m = _AVERAGE.match(str(c.value or "").replace(" ", ""))
            if m:
                out[(c.row, c.column)] = [int(m[2]), ci(m[1]), int(m[4]), ci(m[3])]
    return out


def _anexo6c(ws, ws_formulas, ctx: Contexto, path: Path) -> None:
    filas = libro.leer_csv(path)
    m = re.search(r"(\d{4})", path.stem)
    if not m:
        ctx.avisos.append(f"6C: {path.name} no dice el año en el nombre; la hoja queda como en Anexo6C.xlsx.")
        return
    anio = int(m.group(1))
    meses = [f[1:] for f in filas[1:13]]
    proms = _promedios(ws_formulas)
    for j, code in enumerate(filas[0][1:]):
        nombre = TEMP_BLOQUES.get(code.strip().upper())
        r0 = next((c.row for c in ws["A"] if nombre and isinstance(c.value, str) and c.value.strip().upper() == nombre), None)
        if r0 is None:
            ctx.avisos.append(f"6C: la columna {code} de {path.name} no tiene bloque en la hoja.")
            continue
        prom = next(r for r in range(r0, ws.max_row + 1) if str(ws.cell(r, 2).value).strip() == "Promedio")
        fila = next((r for r in range(r0, prom) if ws.cell(r, 2).value == anio), None)
        if fila is None:  # año nuevo: va después del último año del bloque
            ultimo = max(r for r in range(r0, prom) if isinstance(ws.cell(r, 2).value, int))
            foto = libro.estilos_fila(ws, ultimo)
            ws.insert_rows(ultimo + 1)
            for b in ws.row_breaks.brk:
                if b.id > ultimo:
                    b.id += 1
            nuevos = {}
            for (r, c), rng in proms.items():
                rng[0] += rng[0] > ultimo
                rng[2] += rng[2] >= ultimo  # el rango que terminaba en el último año incluye el nuevo
                nuevos[(r + (r > ultimo), c)] = rng
            proms = nuevos
            fila = ultimo + 1
            libro.aplicar_fila(ws, fila, foto)
            ws.cell(fila, 2, anio)
        for k in range(12):
            ws.cell(fila, 3 + k, libro.valor(meses[k][j]) if j < len(meses[k]) else None)
    # Los promedios eran fórmulas: se recalculan como valor sobre el rango original.
    for (r, c), (r1, c1, r2, c2) in proms.items():
        vs = [ws.cell(rr, cc).value for rr in range(r1, r2 + 1) for cc in range(c1, c2 + 1)
              if isinstance(ws.cell(rr, cc).value, (int, float))]
        ws.cell(r, c, sum(vs) / len(vs) if vs else None)


def _anexo6e(ws, filas) -> None:
    fhead = next(c.row for c in ws["B"] if isinstance(c.value, str) and c.value.strip().upper() == "UNIDAD")
    fper, f0 = fhead + 1, fhead + 3
    cols = [c.column for c in ws[fper] if c.value is not None and c.column > 2]
    foto = libro.estilos_fila(ws, f0)
    for col, per in zip(cols, filas[0][1:]):
        ws.cell(fper, col, per.strip())
    libro.limpiar_desde(ws, f0)
    r = f0
    for f in filas[1:]:
        if not f or not f[0].strip():
            continue
        libro.aplicar_fila(ws, r, foto)
        ws.cell(r, 2, f[0].strip())
        for col, s in zip(cols, f[1:]):
            ws.cell(r, col, s.strip() or None)
        r += 1
    libro.extender_area(ws, r - 1)


def _anexo6g(ws, filas) -> None:
    """Bloques de 6 filas (unidad + 5 bloques horarios) en 3 columnas por página."""
    fpag = next(c.row for fila in ws.iter_rows() for c in fila
                if isinstance(c.value, str) and c.value.strip().startswith("Página"))
    cpag = next(c.column for c in ws[fpag] if isinstance(c.value, str) and c.value.strip().startswith("Página"))
    fhead = fpag + 1
    cols = [c.column for c in ws[fhead] if isinstance(c.value, str) and c.value.strip().startswith("Unidad")]
    titulos = [(c.column, c.value) for c in ws[fhead] if c.value is not None]
    merges = [(r.min_col, r.max_col) for r in ws.merged_cells.ranges if r.min_row == fhead]
    f0 = next(r for r in range(fhead + 1, ws.max_row + 1) if ws.cell(r, cols[0]).value)
    fotos = {"pag": libro.estilos_fila(ws, fpag), "head": libro.estilos_fila(ws, fhead),
             "unidad": libro.estilos_fila(ws, f0), "dato": libro.estilos_fila(ws, f0 + 1)}
    unidades, actual = [], None
    for f in filas:
        if not f or not f[0].strip():
            actual = None
            continue
        if actual is None:
            actual = [[libro.valor(s) for s in f[:4]]]
            unidades.append(actual)
        else:
            actual.append([libro.valor(s) for s in f[:4]])
    alto = 7  # 6 filas + separación
    por_col = 13
    por_pag = por_col * len(cols)
    paginas = [unidades[i:i + por_pag] for i in range(0, len(unidades), por_pag)] or [[]]
    libro.limpiar_desde(ws, fpag)
    r = fpag
    for p, grupo in enumerate(paginas, 1):
        if p > 1:
            libro.salto(ws, r - 1)
        libro.aplicar_fila(ws, r, fotos["pag"])
        ws.cell(r, cpag, f"Página {p} de {len(paginas)}")
        libro.aplicar_fila(ws, r + 1, fotos["head"])
        for col, v in titulos:
            ws.cell(r + 1, col, v)
        for c1, c2 in merges:
            ws.merge_cells(start_row=r + 1, start_column=c1, end_row=r + 1, end_column=c2)
        base = r + 1 + (f0 - fhead)
        filas_usadas = math.ceil(len(grupo) / len(cols)) if grupo else 0
        for i, bloque in enumerate(grupo):
            # columna por columna (como la GP): primero baja por la columna A
            fila0 = base + (i % max(1, filas_usadas)) * alto
            col = cols[i // max(1, filas_usadas)]
            for k, vals in enumerate(bloque):
                foto = fotos["unidad"] if k == 0 else fotos["dato"]
                for c, src in foto["celdas"].items():
                    if col <= c < col + 4:
                        libro.copiar_estilo(src, ws.cell(fila0 + k, c))
                for j, v in enumerate(vals):
                    ws.cell(fila0 + k, col + j, v)
        r = base + filas_usadas * alto
    libro.extender_area(ws, r - 2)


def _anexo6(wb, ctx: Contexto) -> None:
    ab = openpyxl.load_workbook(ctx.archivo(0), data_only=True)
    for dst, src in (("ANEXO6A1", "ANEXO6A_1"), ("ANEXO6A2", "ANEXO6A_2"),
                     ("ANEXO6B1", "ANEXO6B_1"), ("ANEXO6B2", "ANEXO6B_2")):
        libro.reemplazar_hoja(wb, dst, ab[src])
    c = openpyxl.load_workbook(ctx.archivo(1), data_only=True)
    temp = ctx.archivo(2)
    if temp:
        _anexo6c(c.active, openpyxl.load_workbook(ctx.archivo(1)).active, ctx, temp)
    libro.reemplazar_hoja(wb, "ANEXO6C", c.active)
    d = openpyxl.load_workbook(ctx.archivo(3), data_only=True)
    for s in ("ANEXO6D1", "ANEXO6D2"):
        libro.reemplazar_hoja(wb, s, d[s])
    _anexo6e(wb["ANEXO6E"], libro.leer_csv(ctx.archivo(4)))
    f = openpyxl.load_workbook(ctx.archivo(5), data_only=True)
    hojas_f = ("ANEXO6F1", "ANEXO6F2", "ANEXO6F3", "ANEXO6F4", "ANEXO6F5")
    for s in hojas_f:
        libro.reemplazar_hoja(wb, s, f[s])
    # El libro de trabajo numera sus páginas a su manera: se renumeran las del anexo final.
    marcas = [c for s in hojas_f for fila in wb[s].iter_rows() for c in fila
              if isinstance(c.value, str) and re.match(r"^\s*P[áa]gina \d+ de \d+", c.value)]
    for i, c in enumerate(marcas, 1):
        c.value = f"Página {i} de {len(marcas)}"
    _anexo6g(wb["ANEXO6G"], libro.leer_csv(ctx.archivo(6)))


_GENERADORES = {2: _anexo2, 4: _anexo4, 5: _anexo5, 6: _anexo6}
