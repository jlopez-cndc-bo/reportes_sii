"""Registros del HFD de SCADA: una fila por medida y día, 96 valores de 15 min.

Fuente (esquema SPECTRUM, cargado por rs7_core8): tablas verticales *_SP7
(id, fecha_sng, intervalo 0..95, type, valor). Desde sql/007-009 de rs7_core8
los días cerrados también están en tablas horizontales *_DIA (P0..P95); si la
tabla horizontal existe, los días que ya tiene se leen de ahí y el resto
(p. ej. hoy) se pivotea de la vertical.

Convención: la del archivo HFD (YYYYMMDD-900.*.csv), decidida por el usuario el
2026-11-19. Una fila por (fecha_sng, medida); P0..P95 = intervalos 0..95 = columnas
00:00 … 23:45 del archivo. Los valores van crudos: sin recortar negativos y vacíos
donde no hay dato.
"""
from datetime import date
from typing import Any

from ..db import query
from . import correcciones

MAX_DIAS = 31

# id de la API -> (tabla vertical, tabla horizontal, nombre visible)
ARCHIVOS: dict[str, tuple[str, str, str]] = {
    "generadores": ("TDM_GE30_SP7", "TDM_GE30_DIA", "Generadores"),
    "transferencias": ("TDM_TD30_SP7", "TDM_TD30_DIA", "Transferencias"),
    "tensiones": ("TDM_V30_SP7", "TDM_V30_DIA", "Tensiones"),
    "embalses": ("TDM_H30_SP7", "TDM_H30_DIA", "Embalses"),
    "taps": ("TAP__1MM_SP7", "TAP__1MM_DIA", "Taps de transformadores"),
}

# Confirmadas por el usuario (2026-11-19); embalses y taps sin confirmar.
UNIDADES = {"P": "MW", "Q": "MVAr", "U": "kV", "Uab": "kV", "Ubc": "kV", "Uac": "kV"}

_P = [f"p{i}" for i in range(96)]


def etiqueta_intervalo(i: int) -> str:
    """Intervalo 0 -> '00:00' … 95 -> '23:45', como las columnas del archivo HFD."""
    m = i * 15
    return f"{m // 60:02d}:{m % 60:02d}"


def _archivo(archivo: str) -> tuple[str, str, str]:
    if archivo not in ARCHIVOS:
        raise ValueError(f"Archivo HFD desconocido: {archivo}. Opciones: {', '.join(ARCHIVOS)}")
    return ARCHIVOS[archivo]


def validar_rango(desde: date, hasta: date) -> None:
    if hasta < desde:
        raise ValueError("La fecha «hasta» es anterior a «desde».")
    if (hasta - desde).days + 1 > MAX_DIAS:
        raise ValueError(f"El rango no puede superar {MAX_DIAS} días.")


def catalogo() -> list[dict[str, Any]]:
    """Archivos HFD con sus magnitudes (columna `el` de data_raw_objet_sp7)."""
    rows = query(
        "SELECT type, el, COUNT(*) n FROM spectrum.data_raw_objet_sp7 "
        "WHERE type IS NOT NULL GROUP BY type, el ORDER BY type, el"
    )
    por_tabla: dict[str, list[str]] = {}
    for r in rows:
        # El ETL dejó algún `el` numérico suelto (p. ej. '1965.70' en H30): no es magnitud.
        if r["el"] and not r["el"][0].isdigit():
            por_tabla.setdefault(r["type"], []).append(r["el"])
    return [
        {"id": k, "label": label, "magnitudes": por_tabla.get(vert, [])}
        for k, (vert, _, label) in ARCHIVOS.items()
    ]


def _horizontal_existe(tabla: str) -> bool:
    return bool(query(
        "SELECT 1 FROM all_tables WHERE owner = 'SPECTRUM' AND table_name = :t", {"t": tabla}
    ))


def fuente_sql(vert: str, horiz: str | None) -> str:
    """Subconsulta (fecha, id, type, p0..p95) para :magnitud entre :desde y :hasta.

    Si hay tabla horizontal, los días que ya tiene salen de ahí y el resto de la
    vertical pivoteada (sin duplicar días). `vert`/`horiz` vienen de ARCHIVOS.
    """
    cols = ", ".join(_P)
    pivot_in = ", ".join(f"{i} AS p{i}" for i in range(96))
    vertical = f"""
        SELECT fecha, id, type, {cols} FROM (
            SELECT fecha_sng fecha, id, type, valor, intervalo
              FROM spectrum.{vert}
             WHERE type = :magnitud
               AND fecha_sng BETWEEN :desde AND :hasta
        ) PIVOT (MAX(valor) FOR intervalo IN ({pivot_in}))
        {f"WHERE fecha NOT IN (SELECT fecha FROM spectrum.{horiz} WHERE fecha BETWEEN :desde AND :hasta)" if horiz else ""}
    """
    return vertical if not horiz else f"""
        SELECT fecha, id, type, {cols} FROM spectrum.{horiz}
         WHERE type = :magnitud AND fecha BETWEEN :desde AND :hasta
        UNION ALL {vertical}"""


def fuente(archivo: str) -> str:
    """fuente_sql del archivo, usando la horizontal sólo si ya existe en la base."""
    vert, horiz, _ = _archivo(archivo)
    return fuente_sql(vert, horiz if _horizontal_existe(horiz) else None)


def _sql(vert: str, horiz: str | None) -> str:
    fuente = fuente_sql(vert, horiz)
    # Nombre de la medida: un id puede tener más de un nombre histórico (remapeos);
    # KEEP toma uno consistente (b1/b2/b3 de la misma fila).
    return f"""
        SELECT r.fecha, n.b1 estacion, n.b2 tension, n.b3 elemento, r.type magnitud, r.id, {", ".join("r." + p for p in _P)}
          FROM ({fuente}) r
          LEFT JOIN (
              SELECT id_obj, el,
                     MIN(TRIM(b1)) KEEP (DENSE_RANK FIRST ORDER BY ta) b1,
                     MIN(TRIM(b2)) KEEP (DENSE_RANK FIRST ORDER BY ta) b2,
                     MIN(TRIM(b3)) KEEP (DENSE_RANK FIRST ORDER BY ta) b3
                FROM spectrum.data_raw_objet_sp7
               WHERE type = :tabla
               GROUP BY id_obj, el
          ) n ON n.id_obj = r.id AND n.el = r.type
         WHERE (:estacion IS NULL OR UPPER(n.b1) LIKE '%' || UPPER(:estacion) || '%')
         ORDER BY r.fecha, n.b1, n.b2, n.b3, r.id
    """


def registros(archivo: str, magnitud: str, desde: date, hasta: date,
              estacion: str | None = None) -> dict[str, Any]:
    vert, horiz, label = _archivo(archivo)
    validar_rango(desde, hasta)
    if not magnitud:
        raise ValueError("Falta la magnitud.")
    estacion = (estacion or "").strip() or None

    params = {"magnitud": magnitud, "desde": desde, "hasta": hasta,
              "tabla": vert, "estacion": estacion}
    filas = query(_sql(vert, horiz if _horizontal_existe(horiz) else None), params)

    rows = [
        {
            "fecha": r["fecha"].date().isoformat(),
            "estacion": r["estacion"] or "",
            "tension": r["tension"] or "",
            "elemento": r["elemento"] or "",
            "magnitud": r["magnitud"],
            "id": int(r["id"]),
            **{p: r[p] for p in _P},
        }
        for r in filas
    ]
    # Celdas corregidas por operadores (HFD_CORRECCION): {"p56": "Corregido por …"}.
    corr = correcciones.vigentes(archivo, desde, hasta) if rows else {}
    if corr:
        for row in rows:
            marcas = {f"p{i}": correcciones.nota(c) for (f, idv, el, i), c in corr.items()
                      if f == row["fecha"] and idv == row["id"] and el == row["magnitud"]}
            if marcas:
                row["_corr"] = marcas
    # Sólo la generación se puede sumar entre medidas; tensiones, cotas y taps no, y en
    # transferencias cada línea se mide en sus dos extremos (se contaría dos veces).
    sin_total = archivo != "generadores"
    columns = [
        # Estación primero: es la columna fija al desplazarse por los 96 intervalos.
        {"key": "estacion", "label": "Estación"},
        {"key": "tension", "label": "Tensión kV", "sinTotal": True},
        {"key": "elemento", "label": "Elemento"},
        {"key": "magnitud", "label": "Magnitud"},
        {"key": "fecha", "label": "Fecha", "sinTotal": True},
        {"key": "id", "label": "Id", "hidden": True, "sinTotal": True},
        *({"key": f"p{i}", "label": etiqueta_intervalo(i), "format": "num", "sinTotal": sin_total}
          for i in range(96)),
    ]

    aviso = None
    if hasta >= date.today():
        aviso = f"{label}: el día de hoy está incompleto (se carga cada 10 minutos)."
    return {"table": "HFD_REGISTROS", "columns": columns, "rows": rows, "aviso": aviso}
