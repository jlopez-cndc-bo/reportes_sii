"""Temperatura por zona térmica y su relación con la demanda máxima.

Fuente: POSTDES.TEMPERATURA_ZONAS_TERMICAS_DET (horaria, °C, desde 2005; `consolidado` = 0 en
los días aún no consolidados) y POSTDES.TEMPERATURA (catálogo de zonas). Las unidades de cada
zona (POSTDES.TERMICAS) sólo se informan como referencia.
"""
import io
import statistics
from datetime import datetime, timedelta
from typing import Any

from ..db import query

_HORAS = list(range(24))


def _zonas_activas() -> list[dict[str, str]]:
    """Zonas en uso, en el orden de POSTDES.ORDEN_ZONAS."""
    return query("""
        SELECT z.id_universal id, z.nombre zona
          FROM postdes.temperatura z
          LEFT JOIN postdes.orden_zonas o ON o.id_universal = z.id_universal
         WHERE z.estado = 'A'
         ORDER BY o.pos NULLS LAST, z.nombre""")


def _lecturas(ids: list[str], f1: datetime, f2: datetime) -> list[dict[str, Any]]:
    binds: dict[str, Any] = {f"z{i}": z for i, z in enumerate(ids)}  # códigos de texto
    in_sql = "(" + ", ".join(f":{k}" for k in binds) + ")"
    binds.update(f1=f1, f2=f2)
    return query(f"""
        SELECT id_universal id, fecha, hora, valor, consolidado
          FROM postdes.temperatura_zonas_termicas_det
         WHERE id_universal IN {in_sql}
           AND fecha >= TRUNC(:f1) AND fecha <= TRUNC(:f2)""", binds)


def correlacion(xs: list[float], ys: list[float]) -> float | None:
    """Coeficiente de Pearson; None con menos de 10 pares o sin variación. Pura."""
    if len(xs) < 10 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return round(statistics.correlation(xs, ys), 2)


def punta_temperatura(f1: datetime, f2: datetime) -> dict[str, Any]:
    """Por día: potencia de punta del SIN (retiros SMEC) y la temperatura de cada zona a esa hora."""
    puntas = query("""
        SELECT fecha, MAX(tot) KEEP (DENSE_RANK LAST ORDER BY tot) kw,
               MAX(intervalo) KEEP (DENSE_RANK LAST ORDER BY tot) intervalo
          FROM (SELECT c.fecha, c.intervalo, SUM(c.potencia) tot
                  FROM smec.sm_potencia_cen_intervalo c
                  JOIN (SELECT DISTINCT niv4 FROM dw_relaciones WHERE dir = 1) r ON r.niv4 = c.id
                 WHERE c.fecha >= TRUNC(:f1) AND c.fecha <= TRUNC(:f2)
                 GROUP BY c.fecha, c.intervalo)
         GROUP BY fecha ORDER BY fecha""", {"f1": f1, "f2": f2})
    zonas = _zonas_activas()
    temp: dict[tuple, float] = {}
    tmax: dict[tuple, float] = {}
    for f in _lecturas([z["id"] for z in zonas], f1, f2):
        temp[(f["id"], f["fecha"], int(f["hora"]))] = float(f["valor"])
        k = (f["id"], f["fecha"])
        tmax[k] = max(tmax.get(k, float("-inf")), float(f["valor"]))
    rows = []
    for p in puntas:
        i = int(p["intervalo"]) - 1
        hora = i // 4  # la lectura horaria que contiene el intervalo de la punta
        rows.append({"fecha": p["fecha"].strftime("%d/%m/%Y"), "punta": round(float(p["kw"]) / 1000, 3),
                     "hora_punta": f"{hora:02d}:{i % 4 * 15:02d}",
                     **{f"t_{z['id']}": temp.get((z["id"], p["fecha"], hora)) for z in zonas}})
    columns = [{"key": "fecha", "label": "Fecha"},
               {"key": "punta", "label": "Potencia de punta (MW)", "format": "0.0", "sinTotal": True},
               {"key": "hora_punta", "label": "Hora de punta"},
               *({"key": f"t_{z['id']}", "label": f"{z['zona'].title()} (°C)", "format": "0.0", "sinTotal": True}
                 for z in zonas)]
    corr = []
    for z in zonas:
        pares = [(tmax[(z["id"], p["fecha"])], float(p["kw"])) for p in puntas if (z["id"], p["fecha"]) in tmax]
        r = correlacion([a for a, _ in pares], [b for _, b in pares])
        if r is not None:
            corr.append((r, z["zona"].title()))
    corr.sort(reverse=True)
    aviso = ("Potencia de punta = máximo de los retiros SMEC en 15 min (la que publica el CNDC). "
             "Cada zona muestra su temperatura en la hora de la punta. ")
    aviso += (("Correlación entre la temperatura máxima del día y la punta, en el rango: "
               + ", ".join(f"{n} {r:.2f}".replace(".", ",") for r, n in corr[:4]) + ".")
              if corr else "La correlación se calcula con 10 días o más.")
    return {"table": "PUNTA_TEMPERATURA", "columns": columns, "rows": rows, "aviso": aviso}


def validar_rango(f1: datetime, f2: datetime, max_dias: int = 366) -> None:
    if (f2.date() - f1.date()).days + 1 > max_dias:
        raise ValueError(f"El rango supera el máximo de {max_dias} días para este reporte.")
    if f1.date() > (datetime.now() + timedelta(days=1)).date():
        raise ValueError("La fecha no puede ser futura.")


def zonas() -> list[dict[str, Any]]:
    """Zonas térmicas activas con sus unidades térmicas vigentes (para elegir en la consulta)."""
    unidades: dict[str, list[str]] = {}
    for f in query("""
        SELECT z.id_universal id, t.nombre
          FROM postdes.termicas t JOIN postdes.temperatura z ON z.id = t.id_temperatura
         WHERE t.estado = 'A' GROUP BY z.id_universal, t.nombre ORDER BY t.nombre"""):
        unidades.setdefault(f["id"], []).append(f["nombre"])
    return [{"id": z["id"], "zona": z["zona"].title(), "unidades": unidades.get(z["id"], [])}
            for z in _zonas_activas()]


def resumen_dia(valores: list[float | None]) -> dict[str, Any]:
    """Máx (con su hora), mín y promedio de las 24 lecturas de un día. Pura."""
    con = [(v, h) for h, v in enumerate(valores) if v is not None]
    if not con:
        return {"maxima": None, "hora_max": None, "minima": None, "promedio": None}
    vmax, hmax = max(con, key=lambda t: t[0])
    return {"maxima": vmax, "hora_max": f"{hmax:02d}:00", "minima": min(v for v, _ in con),
            "promedio": round(sum(v for v, _ in con) / len(con), 1)}


def consulta(f1: datetime, f2: datetime, ids: list[str]) -> dict[str, Any]:
    """Temperatura de las zonas elegidas: las horas en columnas y una fila por fecha y zona,
    agrupadas por fecha."""
    validar_rango(f1, f2)
    elegidas = [z for z in _zonas_activas() if not ids or z["id"] in ids]
    if not elegidas:
        raise ValueError("Ninguna de las zonas pedidas está activa.")
    celdas: dict[tuple, list[float | None]] = {}
    sin_consolidar = 0
    for f in _lecturas([z["id"] for z in elegidas], f1, f2):
        celdas.setdefault((f["fecha"].date(), f["id"]), [None] * 24)[int(f["hora"])] = float(f["valor"])
        sin_consolidar += f["consolidado"] != 1
    dias = [f1.date() + timedelta(days=i) for i in range((f2.date() - f1.date()).days + 1)]
    rows = []
    for d in dias:
        for z in elegidas:
            vals = celdas.get((d, z["id"]))
            if vals is None:
                continue
            rows.append({"fecha": d.strftime("%d/%m/%Y"), "zona": z["zona"].title(),
                         **{f"h{h}": v for h, v in enumerate(vals)}, **resumen_dia(vals)})
    columns = [{"key": "fecha", "label": "Fecha"}, {"key": "zona", "label": "Zona térmica"},
               *({"key": f"h{h}", "label": f"{h:02d}:00", "format": "0.0", "sinTotal": True} for h in _HORAS),
               {"key": "maxima", "label": "Máx (°C)", "format": "0.0", "resumen": True, "sinTotal": True},
               {"key": "hora_max", "label": "Hora máx", "resumen": True},
               {"key": "minima", "label": "Mín (°C)", "format": "0.0", "resumen": True, "sinTotal": True},
               {"key": "promedio", "label": "Promedio (°C)", "format": "0.0", "resumen": True, "sinTotal": True}]
    aviso = " ".join(filter(None, [
        "Temperatura en °C por zona térmica (POSTDES), una fila por fecha y zona.",
        sin_consolidar and f"{sin_consolidar} lectura(s) aún sin consolidar (días recientes).",
    ]))
    return {"table": "TEMPERATURA_CONSULTA", "columns": columns, "rows": rows, "aviso": aviso}


def excel_plano(f1: datetime, f2: datetime, ids: list[str]) -> io.BytesIO:
    """Hoja plana como la que se envía hoy (temp_ene2024.xlsx): ZONA TÉRMICA (nombre), FECHA y las horas 00:00..23:00,
    una fila por zona y fecha, ordenadas por fecha y zona; horas sin lectura quedan vacías."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    validar_rango(f1, f2)
    nombres = {z["id"]: z["zona"].title() for z in _zonas_activas() if not ids or z["id"] in ids}
    elegidas = sorted(nombres)
    if not elegidas:
        raise ValueError("Ninguna de las zonas pedidas está activa.")
    celdas: dict[tuple, list[float | None]] = {}
    for f in _lecturas(elegidas, f1, f2):
        celdas.setdefault((f["fecha"], f["id"]), [None] * 24)[int(f["hora"])] = float(f["valor"])
    wb = Workbook()
    ws = wb.active
    ws.title = "Temperaturas"
    ws.append(["ZONA TÉRMICA", "FECHA", *(f"{h:02d}:00" for h in _HORAS)])
    for c in ws[1]:
        c.font = Font(bold=True)
    for (fecha, zid), vals in sorted(celdas.items(), key=lambda t: (t[0][0], nombres[t[0][1]])):
        ws.append([nombres[zid], fecha, *vals])
        ws.cell(row=ws.max_row, column=2).number_format = "dd/mm/yyyy"
    ws.freeze_panes = "A2"
    ws.column_dimensions["A"].width = 13
    ws.column_dimensions["B"].width = 12
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
