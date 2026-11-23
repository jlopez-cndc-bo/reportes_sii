"""Consolidados del HFD con drill-down hasta la medida.

Generación por tipo: Tipo → Central → Unidad, sobre TDM_GE30 (P, MW). La
clasificación sale de los datos y no de listas de ids escritas a mano:
`data_raw_objet_sp7.aux` (BAGAZO/EOL/HID/SOLAR) y, si no hay, `objetos.tipo_obj`
(TG/TDF → termo, HID, INT → renovable sin clasificar, ARG → exportación).
La central es la relación CENTRAL de `objetos_objetos` (igual que
desa.get_central_generador). Los negativos (consumo propio) cuentan como 0,
como en las matrices V_TDM_GE30_M*.

Demanda por departamento: Departamento → Elemento, con
`demanda_departamento_conf` vigente en el día (type_c 1 = TDM_GE30, 2 =
TDM_TD30, valor × signo), igual que matricial_transferencias96 pero respetando
fecha_inicio/fecha_fin.

Intervalos como el archivo HFD: p0..p95 = 00:00 … 23:45 de fecha_sng.
"""
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from ..db import query
from . import registros as R

# (código, etiqueta) en el orden en que se muestran.
TIPOS = [
    ("TERMO", "Termoeléctrica"),
    ("HIDRO", "Hidroeléctrica"),
    ("EOL", "Eólica"),
    ("SOLAR", "Solar"),
    ("BAGAZO", "Biomasa (bagazo)"),
    ("RENO", "Renovable sin clasificar"),
    ("EXPORT", "Exportación"),
    ("SIN_CLASIF", "Sin clasificar"),
]
_ETIQUETA = dict(TIPOS)
_ORDEN = {k: i for i, (k, _) in enumerate(TIPOS)}

_P = [f"p{i}" for i in range(96)]
_AVISO_TOTAL_SIN = "La fila TOTAL es la generación del SIN: no incluye Exportación."
_LABELS = [R.etiqueta_intervalo(i) for i in range(96)]


def clasificar(aux: str | None, tipo_obj: str | None) -> str:
    """Tipo de generación de una unidad: primero `aux` del catálogo HFD, luego tipo_obj."""
    por_aux = {"BAGAZO": "BAGAZO", "EOL": "EOL", "SOLAR": "SOLAR", "HID": "HIDRO"}
    if aux and aux.strip().upper() in por_aux:
        return por_aux[aux.strip().upper()]
    return {"TG": "TERMO", "TDF": "TERMO", "HID": "HIDRO", "INT": "RENO",
            "ARG": "EXPORT"}.get((tipo_obj or "").strip().upper(), "SIN_CLASIF")


def sumar(series: Iterable[list[float | None]]) -> list[float | None]:
    """Suma intervalo a intervalo; None sólo si ningún sumando tiene dato."""
    out: list[float | None] = [None] * 96
    for s in series:
        for i, v in enumerate(s):
            if v is not None:
                out[i] = round((out[i] or 0) + v, 6)
    return out


def _indicadores(vals: list[float | None]) -> dict[str, Any]:
    con = [(v, i) for i, v in enumerate(vals) if v is not None]
    if not con:
        return {"maximo": None, "hora_max": None, "energia": None}
    vmax, imax = max(con, key=lambda t: t[0])
    return {"maximo": vmax, "hora_max": _LABELS[imax],
            # MWh = MW × 0,25 h por lectura de 15 min.
            "energia": round(sum(v for v, _ in con) * 0.25, 6)}


_COLS_IND = [
    {"key": "maximo", "label": "Máx", "format": "num", "resumen": True, "sinTotal": True},
    {"key": "hora_max", "label": "Hora máx", "resumen": True},
    {"key": "energia", "label": "Energía (MWh)", "format": "0.00", "resumen": True},
]


def _validar_dia(fecha: date) -> None:
    if fecha > date.today():
        raise ValueError("La fecha no puede ser futura.")


# ───────────────────────── Generación por tecnología ──────────────────────────

def _unidades() -> dict[int, dict[str, Any]]:
    """Catálogo de unidades GE30: tipo, central y nombres (sólo ids vigentes, > 0)."""
    filas = query("""
        SELECT d.id_obj id,
               MAX(CASE WHEN TRIM(d.el) = 'P' THEN d.aux END) aux,
               MIN(TRIM(d.b1)) KEEP (DENSE_RANK FIRST ORDER BY d.ta) estacion,
               o.tipo_obj, o.codigo_objeto unidad, c.codigo_objeto central
          FROM spectrum.data_raw_objet_sp7 d
          LEFT JOIN objetos o ON o.id_objeto = d.id_obj
          LEFT JOIN (SELECT ob_id_objeto_primario id, MAX(ob_id_objeto_secundario) central
                       FROM objetos_objetos
                      WHERE cte_elemento_secundario = 'CENTRAL'
                      GROUP BY ob_id_objeto_primario) oc ON oc.id = d.id_obj
          LEFT JOIN objetos c ON c.id_objeto = oc.central
         WHERE d.type = 'TDM_GE30_SP7' AND d.id_obj > 0
         GROUP BY d.id_obj, o.tipo_obj, o.codigo_objeto, c.codigo_objeto
    """)
    return {
        int(f["id"]): {
            "tipo": clasificar(f["aux"], f["tipo_obj"]),
            "central": f["central"] or f"Sin central ({f['estacion'] or '?'})",
            "unidad": f["unidad"] or f"id {int(f['id'])}",
            "estacion": f["estacion"] or "",
        }
        for f in filas
    }


def _lecturas(archivo: str, desde: date, hasta: date) -> list[dict[str, Any]]:
    return query(f"SELECT * FROM ({R.fuente(archivo)})",
                 {"magnitud": "P", "desde": desde, "hasta": hasta})


def _arbol(hojas: list[tuple[tuple[str, ...], dict[str, Any]]], valores_de) -> list[dict[str, Any]]:
    """Filas planas en orden de árbol con `_nivel` (formato de drill de ResultsTable).

    `hojas`: (ruta de nombres de nivel 0..n-1, datos de la hoja). `valores_de(lista
    de hojas)` devuelve el dict de columnas de un nodo a partir de sus hojas.
    """
    out: list[dict[str, Any]] = []

    def nodo(prefijo: tuple[str, ...], grupo):
        nivel = len(prefijo)
        hijos: dict[str, list] = {}
        for ruta, h in grupo:
            hijos.setdefault(ruta[nivel], []).append((ruta, h))
        for nombre, sub in hijos.items():
            hoja = len(sub[0][0]) == nivel + 1
            out.append({"nombre": nombre, "_nivel": nivel, **valores_de([h for _, h in sub])})
            if not hoja:
                nodo(prefijo + (nombre,), sub)

    nodo((), hojas)
    return out


def generacion_tipo(fecha: date) -> dict[str, Any]:
    """Un día, 96 lecturas: Tipo → Central → Unidad (MW, negativos como 0)."""
    _validar_dia(fecha)
    unidades = _unidades()
    hojas = []
    sin_catalogo = 0
    for r in _lecturas("generadores", fecha, fecha):
        u = unidades.get(int(r["id"]))
        if u is None:
            sin_catalogo += 1
            continue
        vals = [None if r[p] is None else max(float(r[p]), 0.0) for p in _P]
        hojas.append(((_ETIQUETA[u["tipo"]], u["central"], f"{u['unidad']} · {u['estacion']}"),
                      {"tipo": u["tipo"], "vals": vals}))
    hojas.sort(key=lambda t: (_ORDEN[t[1]["tipo"]], t[0][1], t[0][2]))

    def valores(hs):
        vals = sumar(h["vals"] for h in hs)
        # Exportación se muestra pero no suma en la fila TOTAL (total = SIN).
        return {**dict(zip(_P, vals)), **_indicadores(vals),
                "_sinTotal": all(h["tipo"] == "EXPORT" for h in hs)}

    columns = [{"key": "nombre", "label": "Tecnología / Central / Unidad"},
               *({"key": p, "label": lab, "format": "num"} for p, lab in zip(_P, _LABELS)),
               *_COLS_IND]
    aviso = " ".join(filter(None, [
        _aviso_hoy(fecha, "generadores"),
        sin_catalogo and f"{sin_catalogo} medida(s) sin unidad en el catálogo HFD no se incluyen."])) or None
    return {"table": "HFD_GEN_TIPO", "columns": columns, "rows": _arbol(hojas, valores),
            "aviso": aviso, "aviso_total": _AVISO_TOTAL_SIN}


def energia_tipo(desde: date, hasta: date) -> dict[str, Any]:
    """Energía diaria (MWh) por Tipo → Central → Unidad en un rango, con participación."""
    R.validar_rango(desde, hasta)
    unidades = _unidades()
    dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
    por_unidad: dict[int, dict[str, float]] = {}
    for r in _lecturas("generadores", desde, hasta):
        if int(r["id"]) not in unidades:
            continue
        vals = [max(float(r[p]), 0.0) for p in _P if r[p] is not None]
        if vals:
            k = r["fecha"].date().isoformat()
            por_unidad.setdefault(int(r["id"]), {})[k] = round(sum(vals) * 0.25, 6)

    hojas = []
    for uid, energias in por_unidad.items():
        u = unidades[uid]
        hojas.append(((_ETIQUETA[u["tipo"]], u["central"], f"{u['unidad']} · {u['estacion']}"),
                      {"tipo": u["tipo"], "e": energias}))
    hojas.sort(key=lambda t: (_ORDEN[t[1]["tipo"]], t[0][1], t[0][2]))
    total_sin = sum(v for _, h in hojas if h["tipo"] != "EXPORT" for v in h["e"].values()) or None

    def valores(hs):
        fila: dict[str, Any] = {}
        for d in dias:
            k = d.isoformat()
            vs = [h["e"][k] for h in hs if k in h["e"]]
            fila[f"d{k}"] = round(sum(vs), 6) if vs else None
        tot = sum(v for v in fila.values() if v is not None)
        fila["total"] = round(tot, 6)
        exporta = all(h["tipo"] == "EXPORT" for h in hs)
        fila["part"] = None if exporta or not total_sin else round(100 * tot / total_sin, 2)
        fila["_sinTotal"] = exporta
        return fila

    columns = [{"key": "nombre", "label": "Tecnología / Central / Unidad"},
               *({"key": f"d{d.isoformat()}", "label": d.strftime("%d/%m"), "format": "0.00"} for d in dias),
               {"key": "total", "label": "Total", "format": "0.00", "resumen": True},
               {"key": "part", "label": "Part. %", "format": "0.0", "resumen": True, "sinTotal": True}]
    return {"table": "HFD_ENERGIA_TIPO", "columns": columns, "rows": _arbol(hojas, valores),
            "aviso": " ".join(filter(None, [_aviso_hoy(hasta, "generadores"),
                                            "La participación es sobre el SIN: no incluye Exportación."])),
            "aviso_total": _AVISO_TOTAL_SIN}


# ─────────────────────────── Demanda por departamento ──────────────────────────

def _conf_departamentos(fecha: date) -> list[dict[str, Any]]:
    return query("""
        SELECT c.id_area, a.codigo_objeto area, c.id_elemento, c.signo, c.type_c
          FROM spectrum.demanda_departamento_conf c
          LEFT JOIN objetos a ON a.id_objeto = c.id_area
         WHERE c.fecha_inicio <= :f AND (c.fecha_fin IS NULL OR c.fecha_fin >= :f)
    """, {"f": fecha})


def _nombres_td30(ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    filas = query("""
        SELECT id_obj id, MIN(TRIM(b1) || ' / ' || TRIM(b2) || ' / ' || TRIM(b3))
                          KEEP (DENSE_RANK FIRST ORDER BY ta) nombre
          FROM spectrum.data_raw_objet_sp7
         WHERE type = 'TDM_TD30_SP7' AND TRIM(el) = 'P' AND id_obj > 0
         GROUP BY id_obj
    """)
    return {int(f["id"]): f["nombre"] for f in filas if int(f["id"]) in ids}


def demanda_departamento(fecha: date) -> dict[str, Any]:
    """Un día, 96 lecturas: Departamento → Elemento (MW, valor × signo de la configuración)."""
    _validar_dia(fecha)
    conf = _conf_departamentos(fecha)
    gen = {int(r["id"]): r for r in _lecturas("generadores", fecha, fecha)}
    tra = {int(r["id"]): r for r in _lecturas("transferencias", fecha, fecha)}
    unidades = _unidades()
    nombres_td = _nombres_td30({int(c["id_elemento"]) for c in conf if c["type_c"] == 2})

    hojas = []
    for c in conf:
        eid, signo = int(c["id_elemento"]), int(c["signo"])
        fuente = gen if c["type_c"] == 1 else tra
        r = fuente.get(eid)
        if c["type_c"] == 1:
            u = unidades.get(eid)
            nombre = f"{u['unidad']} · {u['estacion']}" if u else f"id {eid}"
            origen = "Generación"
        else:
            nombre = nombres_td.get(eid, f"id {eid}")
            origen = "Transferencia"
        vals = [None if r is None or r[p] is None else signo * float(r[p]) for p in _P]
        hojas.append(((c["area"] or f"Área {c['id_area']}",
                       f"{nombre} ({origen}, {'entra' if signo > 0 else 'sale'})"), {"vals": vals}))
    hojas.sort(key=lambda t: t[0])

    def valores(hs):
        vals = sumar(h["vals"] for h in hs)
        return {**dict(zip(_P, vals)), **_indicadores(vals)}

    columns = [{"key": "nombre", "label": "Departamento / Elemento"},
               *({"key": p, "label": lab, "format": "num"} for p, lab in zip(_P, _LABELS)),
               *_COLS_IND]
    aviso = ("Cada elemento suma con el signo de la configuración: «entra» suma al departamento, "
             "«sale» resta. Elementos sin lectura en el día quedan vacíos.")
    return {"table": "HFD_DEMANDA_DEPTO", "columns": columns, "rows": _arbol(hojas, valores),
            "aviso": " ".join(filter(None, [_aviso_hoy(fecha, "transferencias"), aviso]))}


def _aviso_hoy(fecha: date, archivo: str) -> str | None:
    if fecha >= date.today():
        return f"{R.ARCHIVOS[archivo][2]}: el día de hoy está incompleto (se carga cada 10 minutos)."
    return None
