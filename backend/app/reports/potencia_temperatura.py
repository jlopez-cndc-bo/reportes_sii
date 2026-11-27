"""Potencia efectiva de cada unidad a la temperatura real de su zona, hora por hora.

- Térmicas con curva en POSTDES.GAS (potencia vs temperatura, versión mensual: la de `fecha` más
  reciente que no pase del día): potencia interpolada a la temperatura horaria de su zona térmica
  (POSTDES.TERMICAS → TEMPERATURA). Verificado 2026-11-24: cada curva da la potencia efectiva del
  Excel semestral en la temperatura media de su zona (GCH11 62,22 a 26 °C; ARJ08 18,39 a 15 °C).
- Ciclos combinados: la curva está con el código del archivo (ERI30 → CCERI30, GCH09 → GCH9COM),
  la misma equivalencia que usa potencia_efectiva.
- El resto (hidro, eólica, solar, bagazo y térmicas sin curva): potencia efectiva del Excel de la
  vigencia más próxima (cambia poco; decisión del usuario 2026-11-24).
"""
from bisect import bisect_left
from datetime import date, datetime, timedelta
from typing import Any

from ..db import query
from ..potencia_efectiva import (
    CENTRAL,
    T_MEDIA_INICIAL,
    central_de,
    efectiva,
    efectiva_proxima,
    vigencia,
)
from . import temperatura as TEMP

# Código de la curva en GAS cuando no es el de la unidad (bloques CC y Guaracachi combinado).
_CURVA_ALIAS = {"GCH09": "GCH9COM", "GCH10": "GCH10COM"}
_CC = ("ERI", "SUR", "WAR")


def interpolar(curva: list[tuple[float, float]], t: float) -> float:
    """Potencia a la temperatura t sobre puntos (temp, MW) ordenados; fuera de rango, el extremo."""
    temps = [c[0] for c in curva]
    if t <= temps[0]:
        return curva[0][1]
    if t >= temps[-1]:
        return curva[-1][1]
    i = bisect_left(temps, t)
    (t0, p0), (t1, p1) = curva[i - 1], curva[i]
    return p0 if t1 == t0 else p0 + (p1 - p0) * (t - t0) / (t1 - t0)


def _codigo_curva(cod: str) -> list[str]:
    """Códigos a probar en TERMICAS/GAS para la curva de una unidad, en orden."""
    out = [cod]
    if cod in _CURVA_ALIAS:
        out.insert(0, _CURVA_ALIAS[cod])
    elif cod[:3] in _CC and cod[3:].isdigit() and cod.endswith("0"):
        out.insert(0, "CC" + cod)
    return out


def _termicas(dia: date, codigos: list[str]) -> dict[str, dict[str, Any]]:
    """Fila vigente de TERMICAS (la de fecha más reciente ≤ día) por nombre, sólo en estado A."""
    binds: dict[str, Any] = {f"c{i}": c for i, c in enumerate(codigos)}
    binds["dia"] = dia
    filas = query(f"""
        SELECT t.nombre,
               MAX(t.id_universal) KEEP (DENSE_RANK LAST ORDER BY t.fecha) iu,
               MAX(t.estado) KEEP (DENSE_RANK LAST ORDER BY t.fecha) estado,
               MAX(z.id_universal) KEEP (DENSE_RANK LAST ORDER BY t.fecha) zona_id,
               MAX(z.nombre) KEEP (DENSE_RANK LAST ORDER BY t.fecha) zona
          FROM postdes.termicas t
          LEFT JOIN postdes.temperatura z ON z.id = t.id_temperatura
         WHERE t.fecha <= :dia AND t.nombre IN ({", ".join(f":c{i}" for i in range(len(codigos)))})
         GROUP BY t.nombre""", binds)
    return {f["nombre"]: f for f in filas if f["estado"] == "A"}


def _curvas(dia: date, ius: list[str]) -> dict[str, list[tuple[float, float]]]:
    """Curva vigente al día de cada id_universal (sólo las de 2 o más temperaturas)."""
    if not ius:
        return {}
    binds: dict[str, Any] = {f"u{i}": u for i, u in enumerate(ius)}
    binds["dia"] = dia
    filas = query(f"""
        SELECT g.id_universal iu, g.temperatura t, MAX(g.potencia) p
          FROM postdes.gas g
          JOIN (SELECT id_universal, MAX(fecha) f FROM postdes.gas
                 WHERE fecha <= :dia AND id_universal IN ({", ".join(f":u{i}" for i in range(len(ius)))})
                 GROUP BY id_universal) v ON v.id_universal = g.id_universal AND v.f = g.fecha
         GROUP BY g.id_universal, g.temperatura
         ORDER BY g.id_universal, g.temperatura""", binds)
    out: dict[str, list] = {}
    for f in filas:
        if f["p"] is not None:
            out.setdefault(f["iu"], []).append((float(f["t"]), float(f["p"])))
    return {k: v for k, v in out.items() if len({t for t, _ in v}) >= 2}


def _fuera_de_servicio(dia: date, codigos: list[str]) -> set[str]:
    """Generadores que según OBJETOS aún no entraban o ya habían cerrado ese día.

    Los que no están en OBJETOS (estados de ciclo combinado…) no se descartan. Sólo para fechas sin
    Excel: desde nov-2020 hay unidades en el Excel antes de su fecha_inicio (ORU20-38, EDO03).
    """
    if not codigos:
        return set()
    binds: dict[str, Any] = {f"c{i}": c for i, c in enumerate(codigos)}
    binds.update(dia=dia, gen="GENERADOR")
    filas = query(f"""
        SELECT codigo_objeto FROM objetos
         WHERE cte_elemento = :gen
           AND codigo_objeto IN ({", ".join(f":c{i}" for i in range(len(codigos)))})
           AND (fecha_inicio > :dia OR fecha_cierre < :dia)""", binds)
    return {f["codigo_objeto"] for f in filas}


def efectiva_dia(codigos: list[str], dia: date) -> tuple[dict[str, float | None], bool]:
    """(potencia efectiva de cada unidad ese día, oficial).

    Con vigencia oficial: el Excel (oficial=True). Sin ella (antes de nov-2020): las térmicas con
    curva en POSTDES.GAS se evalúan a su temperatura media del primer archivo (verificado: el
    01/11/2020 las 45 con curva dan el valor del Excel); el resto, la vigencia más próxima. Las
    unidades que según OBJETOS aún no existían (o ya cerraron) quedan en None: no pesan.
    """
    if vigencia(dia):
        return {c: efectiva(c, dia) for c in codigos}, True
    fuera = _fuera_de_servicio(dia, codigos)
    out = {c: None if c in fuera else efectiva_proxima(c, dia) for c in codigos}
    termicas = [c for c in codigos if c in T_MEDIA_INICIAL]
    if termicas:
        term = _termicas(dia, sorted({c for cod in termicas for c in _codigo_curva(cod)}))
        curvas = _curvas(dia, sorted({t["iu"] for t in term.values()}))
        for cod in termicas:
            if cod in fuera:
                continue
            for c in _codigo_curva(cod):
                if c in term and term[c]["iu"] in curvas:
                    out[cod] = round(interpolar(curvas[term[c]["iu"]], T_MEDIA_INICIAL[cod]), 2)
                    break
    return out, False


NOTA_SIN_OFICIAL = ("Sin potencia efectiva oficial (Excel) para la fecha: las térmicas usan su curva "
                    "de POSTDES.GAS a la temperatura media y el resto la vigencia más próxima. "
                    "Sólo se consideran unidades vigentes en el SII.")


def potencias_dia(dia: date) -> list[dict[str, Any]]:
    """Por unidad del parque (tabla de potencia efectiva): potencia de cada hora del día, su base
    (Excel) y de dónde sale ('curva' o 'efectiva')."""
    codigos = list(CENTRAL)
    candidatos = sorted({c for cod in codigos for c in _codigo_curva(cod)})
    term = _termicas(dia, candidatos)
    curvas = _curvas(dia, sorted({t["iu"] for t in term.values()}))
    zonas_ids = sorted({t["zona_id"] for t in term.values() if t["zona_id"]})
    dt = datetime.combine(dia, datetime.min.time())
    temps: dict[str, list[float | None]] = {z: [None] * 24 for z in zonas_ids}
    for f in TEMP._lecturas(zonas_ids, dt, dt) if zonas_ids else []:
        temps[f["id"]][int(f["hora"])] = float(f["valor"])
    out = []
    for cod in codigos:
        base = efectiva_proxima(cod, dia)
        fila = {"unidad": cod, "central": central_de(cod), "base": base, "zona": None,
                "origen": "efectiva", "horas": [base] * 24, "temperaturas": [None] * 24}
        for c in _codigo_curva(cod):
            t = term.get(c)
            if t and t["iu"] in curvas and t["zona_id"]:
                curva, tz = curvas[t["iu"]], temps.get(t["zona_id"], [None] * 24)
                # Hora sin lectura de temperatura: se queda con la potencia efectiva del Excel.
                fila.update(zona=t["zona"].title(), origen="curva", temperaturas=tz,
                            horas=[round(interpolar(curva, v), 3) if v is not None else base for v in tz])
                break
        out.append(fila)
    return out


def _medidores(codigos: list[str]) -> dict[str, int]:
    """Medidor propio SMEC de cada unidad (relación MEDIDOR→GENERADOR única, como Potencia limitada)."""
    if not codigos:
        return {}
    binds = {f"c{i}": c for i, c in enumerate(codigos)}
    filas = query(f"""
        SELECT g.codigo_objeto cod, MIN(oo.ob_id_objeto_primario) med
          FROM objetos g
          JOIN objetos_objetos oo ON oo.ob_id_objeto_secundario = g.id_objeto
                                 AND oo.cte_elemento_primario = 'MEDIDOR'
         WHERE g.cte_elemento = 'GENERADOR'
           AND g.codigo_objeto IN ({", ".join(f":c{i}" for i in range(len(codigos)))})
         GROUP BY g.codigo_objeto
        HAVING COUNT(DISTINCT oo.ob_id_objeto_primario) = 1""", binds)
    return {f["cod"]: int(f["med"]) for f in filas}


def promedio_horario(intervalos: dict[int, float]) -> list[float | None]:
    """MW promedio de cada hora a partir de {intervalo 1..96: kW}; None si falta algún intervalo."""
    out: list[float | None] = []
    for h in range(24):
        v = [intervalos.get(4 * h + k) for k in range(1, 5)]
        out.append(round(sum(v) / 4 / 1000, 3) if None not in v else None)
    return out


def _medido_dia(dia: date, medidores: list[int]) -> dict[int, list[float | None]]:
    if not medidores:
        return {}
    binds: dict[str, Any] = {f"m{i}": m for i, m in enumerate(medidores)}
    binds["dia"] = dia
    por: dict[int, dict[int, float]] = {}
    for f in query(f"""
        SELECT id, intervalo, potencia FROM smec.sm_potencia_med_intervalo
         WHERE fecha = :dia AND id IN ({", ".join(f":m{i}" for i in range(len(medidores)))})""", binds):
        if f["potencia"] is not None:
            por.setdefault(int(f["id"]), {})[int(f["intervalo"])] = float(f["potencia"])
    return {m: promedio_horario(v) for m, v in por.items()}


def _suma(series: list[list[float | None]]) -> list[float | None]:
    return [None if any(s[h] is None for s in series) else round(sum(s[h] for s in series), 3)
            for h in range(24)]


def reporte(f1: datetime, f2: datetime, nivel: str, smec: bool = False) -> dict[str, Any]:
    """Potencia efectiva por hora (00:00..23:00): por unidad térmica con curva, o por zona térmica.
    Con `smec`: sólo unidades con medidor propio, y filas con lo medido y el margen."""
    if nivel not in ("unidad", "zona"):
        raise ValueError("Nivel debe ser 'unidad' o 'zona'.")
    if (f2.date() - f1.date()).days + 1 > 31:
        raise ValueError("El rango supera el máximo de 31 días para este reporte.")
    rows = []
    fuera: set[str] = set()
    sin_medicion: set[str] = set()
    for k in range((f2.date() - f1.date()).days + 1):
        dia = f1.date() + timedelta(days=k)
        termicas = [u for u in potencias_dia(dia) if u["origen"] == "curva"]
        medido: dict[str, list] = {}
        if smec:
            meds = _medidores([u["unidad"] for u in termicas])
            fuera |= {u["unidad"] for u in termicas if u["unidad"] not in meds}
            termicas = [u for u in termicas if u["unidad"] in meds]
            por_med = _medido_dia(dia, sorted(set(meds.values())))
            medido = {u["unidad"]: por_med.get(meds[u["unidad"]], [None] * 24) for u in termicas}
            # Medidor sin datos ese día (p. ej. reemplazado): la unidad no entra a la comparación.
            vacias = {c for c, v in medido.items() if all(x is None for x in v)}
            sin_medicion |= {f"{c} ({dia:%d/%m})" for c in vacias}
            termicas = [u for u in termicas if u["unidad"] not in vacias]
        if nivel == "unidad":
            grupos = [(u["unidad"], u["central"], u["zona"], [u]) for u in termicas]
        else:
            por: dict[str, list] = {}
            for u in termicas:
                por.setdefault(u["zona"], []).append(u)
            grupos = [(f"{len(us)} unidades", None, z, us) for z, us in sorted(por.items())]
        for nombre, central, zona, us in grupos:
            horas = [round(sum(u["horas"][h] for u in us), 3) for h in range(24)]
            base = round(sum(u["base"] or 0 for u in us), 3)
            comun = {"fecha": dia.strftime("%d/%m/%Y"), "zona": zona, "unidad": nombre, "central": central}
            series = [("Potencia por temperatura", horas, base)]
            if smec:
                med = _suma([medido[u["unidad"]] for u in us])
                series += [("Medido SMEC", med, None),
                           ("Margen (potencia − medido)",
                            [None if m is None else round(p - m, 3) for p, m in zip(horas, med)], None)]
            for serie, vals, b in series:
                con = [v for v in vals if v is not None]
                rows.append({**comun, "serie": serie, "base": b, **{f"h{h}": v for h, v in enumerate(vals)},
                             "minima": min(con, default=None), "maxima": max(con, default=None),
                             "dif_min": round(min(con) - b, 3) if con and b is not None else None})
    columns = [{"key": "fecha", "label": "Fecha"}, {"key": "zona", "label": "Zona térmica"},
               {"key": "unidad", "label": "Unidad" if nivel == "unidad" else "Unidades"},
               *([{"key": "central", "label": "Central"}] if nivel == "unidad" else []),
               {"key": "serie", "label": "Serie"},
               {"key": "base", "label": "Pot. efectiva (Excel, MW)", "format": "0.00"},
               *({"key": f"h{h}", "label": f"{h:02d}:00", "format": "0.00"} for h in range(24)),
               {"key": "minima", "label": "Mín (MW)", "format": "0.00", "resumen": True, "sinTotal": True},
               {"key": "maxima", "label": "Máx (MW)", "format": "0.00", "resumen": True, "sinTotal": True},
               {"key": "dif_min", "label": "Mín − Excel (MW)", "format": "0.00", "resumen": True}]
    aviso = ("Potencia de las unidades térmicas a la temperatura horaria de su zona (curva vigente de "
             "POSTDES.GAS). La columna Excel es la potencia efectiva oficial a temperatura media; la curva "
             "la reproduce en esa temperatura. Horas sin lectura de temperatura usan el valor del Excel.")
    if smec:
        aviso += (" Medido SMEC: promedio de los 4 intervalos de cada hora del medidor propio de la unidad, "
                  "en MW (vacío si falta algún intervalo). Margen = potencia por temperatura − medido.")
        if sin_medicion:
            aviso += (" Sin medición SMEC en el día (su medidor no registró): "
                      + ", ".join(sorted(sin_medicion)[:12]) + (" y más." if len(sin_medicion) > 12 else "."))
        if fuera:
            aviso += (f" {len(fuera)} unidad(es) térmica(s) sin medidor propio en SMEC no entran: "
                      + ", ".join(sorted(fuera)) + ".")
    return {"table": "POTENCIA_TEMPERATURA", "columns": columns, "rows": rows, "aviso": aviso}
