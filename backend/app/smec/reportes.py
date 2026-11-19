"""Reportes SMEC: Potencia (intervalo/máximos) y Energía.

Portado de PotenciaRepository + PotenciaReportService del proyecto moderno.
La lógica vive en el paquete Oracle SMEC_POTENCIA_API (ref cursors); aquí sólo
se invoca, se filtra por dirección (Inyección=-1 / Retiro=+1) y se da forma.
"""
from datetime import datetime, timedelta
from typing import Any

from ..db import call_proc

PKG = "SMEC_POTENCIA_API"

# dw_relaciones tiene una fila por medidor (hasta 34 por central): al unir
# contra sm_energia_cen_dia hay que colapsarla o la energía se multiplica.
# (El proc oficial P_GET_ENERGIA_DIA no multiplica; verificado 2026-07-14.)
_REL = ("(SELECT DISTINCT niv4, dir, niv5, orden_agentes FROM dw_relaciones)")


def _idx(cols: list[str], name: str) -> int:
    return cols.index(name) if name in cols else -1


def _csv(ids: list[int]) -> str | None:
    return ",".join(str(int(i)) for i in ids) if ids else None


def _total(valores: list) -> float | None:
    """Suma de la fila ignorando vacíos; None si no hay datos. round(…, 6) sólo
    limpia ruido de punto flotante (la base trae ≤ 4 decimales; con 10 el ruido
    sobrevivía en totales de cientos de millones)."""
    vs = [v for v in valores if v is not None]
    return round(sum(vs), 6) if vs else None


# Indicadores por fila de potencia. "resumen": el gráfico no los usa como
# período; "sinTotal": la fila TOTAL no los suma (máximos no coincidentes).
_COLS_INDICADORES = [
    {"key": "pot_max", "label": "Máx", "format": "num", "resumen": True, "sinTotal": True},
    {"key": "hora_max", "label": "Hora máx", "resumen": True},
    {"key": "pot_min", "label": "Mín", "format": "num", "resumen": True, "sinTotal": True},
    {"key": "hora_min", "label": "Hora mín", "resumen": True},
    {"key": "promedio", "label": "Promedio", "format": "num", "resumen": True},
    {"key": "completitud", "label": "Completitud %", "format": "0.0", "resumen": True, "sinTotal": True},
    {"key": "energia_bruta", "label": "Energía bruta (kWh)", "format": "num", "resumen": True},
    {"key": "servicio_local", "label": "Servicio local (kWh)", "format": "num", "resumen": True},
    {"key": "energia_neta", "label": "Energía neta (kWh)", "format": "num", "resumen": True},
    {"key": "horas_servicio", "label": "Horas en servicio", "format": "0.00", "resumen": True, "sinTotal": True},
    {"key": "arranques", "label": "Arranques", "format": "num", "resumen": True},
    {"key": "rampa_max", "label": "Rampa máx", "format": "num", "resumen": True, "sinTotal": True},
    {"key": "hora_rampa", "label": "Hora rampa", "resumen": True},
]


def _indicadores(fila: dict, keys: list[str], labels: list[str]) -> None:
    """Indicadores de una fila de potencia (kW) sobre intervalos de 24h/len(keys).

    Máx/Mín con signo (negativo = consumo de servicio local) y la hora del
    primer intervalo en que ocurren; promedio sobre intervalos con dato.
    Energía = potencia × duración del intervalo; bruta = parte positiva,
    servicio local = parte negativa. Arranque = paso de ≤0 a >0 entre
    intervalos con dato. Rampa = mayor variación (con signo) entre dos
    intervalos contiguos con dato; su hora es la del intervalo de llegada.
    """
    vals = [fila.get(k) for k in keys]
    pares = [(v, lab) for v, lab in zip(vals, labels) if v is not None]
    if not pares:
        fila.update({c["key"]: None for c in _COLS_INDICADORES})
        return
    dt = 24 / len(keys)
    # Sólo limpia ruido de punto flotante: la base trae ≤ 4 decimales y ×0,25 h
    # suma 2; con 10 el ruido sobrevivía en energías de millones (como _total).
    r10 = lambda x: round(x, 6)  # noqa: E731
    vmax, hmax = max(pares, key=lambda p: p[0])
    vmin, hmin = min(pares, key=lambda p: p[0])
    bruta = sum(v for v, _ in pares if v > 0) * dt
    local = sum(v for v, _ in pares if v < 0) * dt
    arranques = sum(1 for (a, _), (b, _) in zip(pares, pares[1:]) if a <= 0 < b)
    rampa, hrampa = None, None
    for i in range(1, len(vals)):
        if vals[i] is not None and vals[i - 1] is not None:
            d = vals[i] - vals[i - 1]
            if rampa is None or abs(d) > abs(rampa):
                rampa, hrampa = round(d, 6), labels[i]
    fila.update(
        pot_max=vmax, hora_max=hmax, pot_min=vmin, hora_min=hmin,
        promedio=r10(sum(v for v, _ in pares) / len(pares)),
        completitud=r10(len(pares) * 100 / len(keys)),
        energia_bruta=r10(bruta), servicio_local=r10(local), energia_neta=r10(bruta + local),
        horas_servicio=r10(sum(1 for v, _ in pares if v > 0) * dt),
        arranques=arranques,
        rampa_max=None if rampa is None else r10(rampa), hora_rampa=hrampa,
    )


# ───────────────────── Energía: participación y comparación ───────────────────

def _desplazar(f: datetime, comparar: str) -> datetime:
    if comparar == "semana":
        return f - timedelta(days=7)
    try:
        return f.replace(year=f.year - 1)
    except ValueError:  # 29/02 → 28/02
        return f.replace(year=f.year - 1, day=28)


def energia_enriquecida(fn, f1: datetime, f2: datetime, ids: list[int],
                        direccion: str, comparar: str = "ninguno",
                        tecnologias: dict[str, str] | None = None) -> dict[str, Any]:
    """Corre un reporte de energía (con columna `total`) y agrega Part. % y,
    si se pide, el total del mismo período desplazado (semana / año) y Var. %.
    Con `tecnologias` (código de central → tecnología) agrega esa columna
    después de Central."""
    res = fn(f1, f2, ids, direccion)
    rows = res["rows"]
    if tecnologias is not None:
        for r in rows:
            r["tecnologia"] = tecnologias.get(r.get("central"), "Sin clasificar")
        i = next(i for i, c in enumerate(res["columns"]) if c["key"] == "central") + 1
        res["columns"] = (res["columns"][:i] + [{"key": "tecnologia", "label": "Tecnología"}]
                          + res["columns"][i:])
    suma = sum(r["total"] for r in rows if r.get("total") is not None)
    for r in rows:
        t = r.get("total")
        r["part"] = round(t * 100 / suma, 10) if suma and t is not None else None
    cols = [{"key": "part", "label": "Part. %", "format": "0.0", "resumen": True, "sinTotal": True}]
    if comparar in ("semana", "anio"):
        prev = fn(_desplazar(f1, comparar), _desplazar(f2, comparar), ids, direccion)
        ant = {(p.get("agente"), p.get("central")): p.get("total") for p in prev["rows"]}
        for r in rows:
            a, t = ant.get((r.get("agente"), r.get("central"))), r.get("total")
            r["total_ant"] = a
            r["var"] = round((t - a) * 100 / abs(a), 10) if a and t is not None else None
        cols += [
            {"key": "total_ant", "label": "Total ant.", "format": "num", "resumen": True},
            {"key": "var", "label": "Var. %", "format": "0.0", "resumen": True, "sinTotal": True},
        ]
    res["columns"] = res["columns"] + cols
    return res


def _target(direccion: str) -> int:
    return -1 if direccion == "iny" else 1


def _interval_labels(n: int) -> list[str]:
    step = 24 * 60 / n if n else 15
    out = []
    for i in range(n):
        m = int(round(i * step))
        out.append(f"{m // 60:02d}:{m % 60:02d}")
    return out


# ───────────────────────────── Potencia por intervalo ─────────────────────────

_PROC_NIVEL = {
    "agente": "P_GET_POTENCIA_AGENTE",
    "central": "P_GET_POTENCIA_CENTRAL",
    "medidor": "P_GET_POTENCIA_MEDIDOR",
}
_NOMBRE_NIVEL = {"agente": "AGENTE", "central": "CENTRAL", "medidor": "MEDIDOR"}


def potencia_intervalo(fecha: datetime, ids: list[int], resolucion: str,
                       direccion: str, nivel: str) -> dict[str, Any]:
    if nivel == "drill":
        return potencia_drill(fecha, ids, resolucion, direccion)
    suf = "_HORA" if resolucion == "hora" else ""
    idscsv = _csv(ids)
    cols, rows = call_proc(f"{PKG}.{_PROC_NIVEL[nivel]}{suf}", [fecha, idscsv])

    icols = [c for c in cols if c.startswith("I") and c[1:].isdigit()]
    iidx = [cols.index(c) for c in icols]
    tgt = _target(direccion)

    if nivel in ("agente", "central"):
        di = _idx(cols, "DIR")
        if di >= 0:
            rows = [r for r in rows if r[di] == tgt]
    else:  # medidor: no trae DIR → filtrar por la dirección de su central
        ccols, crows = call_proc(f"{PKG}.P_GET_POTENCIA_CENTRAL{suf}", [fecha, idscsv])
        cdi, ccc = _idx(ccols, "DIR"), _idx(ccols, "COD_CENTRAL")
        permitidas = {r[ccc] for r in crows if r[cdi] == tgt}
        mcc = _idx(cols, "COD_CENTRAL")
        rows = [r for r in rows if r[mcc] in permitidas]

    ni = _idx(cols, _NOMBRE_NIVEL[nivel])
    labels = _interval_labels(len(icols))
    columns = [{"key": "nombre", "label": _NOMBRE_NIVEL[nivel].capitalize()}]
    for k, lab in zip(icols, labels):
        columns.append({"key": k, "label": lab, "format": "num"})
    columns += _COLS_INDICADORES

    out = []
    for r in rows:
        fila = {"nombre": r[ni]}
        for k, ix in zip(icols, iidx):
            fila[k] = r[ix]
        _indicadores(fila, icols, labels)
        out.append(fila)
    return {"table": f"POT_{nivel.upper()}", "columns": columns, "rows": out}


def potencia_drill(fecha: datetime, ids: list[int], resolucion: str,
                   direccion: str) -> dict[str, Any]:
    """Potencia jerárquica Agente→Central→Medidor en una sola grilla.

    Combina los tres procs de nivel; devuelve filas planas en orden de árbol
    con `_nivel` (0=agente, 1=central, 2=medidor). Enlaces: COD_AGENTE
    (central→agente) y COD_CENTRAL (medidor→central). El proc de medidor no
    trae DIR, así que hereda la dirección de su central.
    """
    suf = "_HORA" if resolucion == "hora" else ""
    idscsv = _csv(ids)
    tgt = _target(direccion)

    acols, arows = call_proc(f"{PKG}.P_GET_POTENCIA_AGENTE{suf}", [fecha, idscsv])
    ccols, crows = call_proc(f"{PKG}.P_GET_POTENCIA_CENTRAL{suf}", [fecha, idscsv])
    mcols, mrows = call_proc(f"{PKG}.P_GET_POTENCIA_MEDIDOR{suf}", [fecha, idscsv])

    icols = [c for c in acols if c.startswith("I") and c[1:].isdigit()]
    labels = _interval_labels(len(icols))

    def fila(cols: list[str], r: tuple, nombre_col: str, nivel: int) -> dict:
        out = {"nombre": r[cols.index(nombre_col)], "_nivel": nivel}
        for k in icols:
            out[k] = r[cols.index(k)] if k in cols else None
        _indicadores(out, icols, labels)
        return out

    adi, acod = acols.index("DIR"), acols.index("COD_AGENTE")
    cdi, cca, ccc = (ccols.index("DIR"), ccols.index("COD_AGENTE"),
                     ccols.index("COD_CENTRAL"))
    mcc = mcols.index("COD_CENTRAL")

    arows = [r for r in arows if r[adi] == tgt]
    crows = [r for r in crows if r[cdi] == tgt]
    med_por_central: dict = {}
    for m in mrows:
        med_por_central.setdefault(m[mcc], []).append(m)

    rows = []
    for a in arows:
        rows.append(fila(acols, a, "AGENTE", 0))
        for c in crows:
            if c[cca] != a[acod]:
                continue
            rows.append(fila(ccols, c, "CENTRAL", 1))
            for m in med_por_central.get(c[ccc], []):
                rows.append(fila(mcols, m, "MEDIDOR", 2))

    columns = [{"key": "nombre", "label": "Agente / Central / Medidor"}]
    for k, lab in zip(icols, labels):
        columns.append({"key": k, "label": lab, "format": "num"})
    columns += _COLS_INDICADORES
    return {"table": "POT_DRILL", "columns": columns, "rows": rows}


# ───────────────────────────── Potencia máximos ───────────────────────────────

def _filtrar_dir(cols, rows, direccion):
    di = _idx(cols, "DIR")
    tgt = _target(direccion)
    return [r for r in rows if di < 0 or r[di] == tgt]


def maximo_periodo(f1: datetime, f2: datetime, ids: list[int],
                   direccion: str) -> dict[str, Any]:
    cols, rows = call_proc(f"{PKG}.P_GET_MAXIMO_PERIODO", [f1, f2, _csv(ids)])
    rows = _filtrar_dir(cols, rows, direccion)
    ia, ic = _idx(cols, "AGENTE"), _idx(cols, "CENTRAL")
    daycols = [c for c in cols if len(c) == 9 and c[0] == "D" and c[1:].isdigit()]
    columns = [{"key": "agente", "label": "Agente"},
               {"key": "central", "label": "Central"}]
    for c in daycols:
        dt = datetime.strptime(c[1:], "%Y%m%d")
        columns.append({"key": c, "label": dt.strftime("%d/%m"), "format": "num"})
    out = []
    for r in rows:
        fila = {"agente": r[ia], "central": r[ic]}
        for c in daycols:
            fila[c] = r[cols.index(c)]
        out.append(fila)
    return {"table": "MAX_PERIODO", "columns": columns, "rows": out}


def maximo_entre_fechas(f1: datetime, f2: datetime, ids: list[int],
                        direccion: str) -> dict[str, Any]:
    cols, rows = call_proc(f"{PKG}.P_GET_MAXIMO_ENTREFECHAS", [f1, f2, _csv(ids)])
    rows = _filtrar_dir(cols, rows, direccion)
    ia, ic = _idx(cols, "AGENTE"), _idx(cols, "CENTRAL")
    ip, ifch = _idx(cols, "POT_MAX"), _idx(cols, "FECHA")
    columns = [{"key": "agente", "label": "Agente"},
               {"key": "central", "label": "Central"},
               {"key": "pot_max", "label": "Potencia Máx", "format": "num"},
               {"key": "fecha", "label": "Fecha/Hora", "format": "datetime"}]
    out = [{"agente": r[ia], "central": r[ic], "pot_max": r[ip], "fecha": r[ifch]}
           for r in rows]
    return {"table": "MAX_ENTRE_FECHAS", "columns": columns, "rows": out}


# ───────────────────────────── Energía ────────────────────────────────────────

def energia_dia(f1: datetime, f2: datetime, ids: list[int],
                direccion: str) -> dict[str, Any]:
    dias = (f2.date() - f1.date()).days + 1
    cols, rows = call_proc(f"{PKG}.P_GET_ENERGIA_DIA", [f1, dias, _csv(ids)])
    rows = _filtrar_dir(cols, rows, direccion)
    ia, ic = _idx(cols, "NOMBRE_AGENTE"), _idx(cols, "NOMBRE_CENTRAL")
    # El proc devuelve D0..D<dias> (un día de más, verificado 2026-11-19 contra
    # sm_energia_cen_dia): se descarta lo que cae fuera del rango pedido.
    daycols = [c for c in cols if c[0] == "D" and c[1:].isdigit() and int(c[1:]) < dias]
    columns = [{"key": "agente", "label": "Agente"},
               {"key": "central", "label": "Central"}]
    for c in daycols:
        n = int(c[1:])
        columns.append({"key": c, "label": (f1 + timedelta(days=n)).strftime("%d/%m"),
                        "format": "num"})
    columns.append({"key": "total", "label": "Total", "format": "num", "resumen": True})
    out = []
    for r in rows:
        fila = {"agente": r[ia], "central": r[ic]}
        for c in daycols:
            fila[c] = r[cols.index(c)]
        fila["total"] = _total([fila[c] for c in daycols])
        out.append(fila)
    return {"table": "ENERGIA_DIA", "columns": columns, "rows": out}


def energia_mes(f1: datetime, f2: datetime, ids: list[int],
                direccion: str) -> dict[str, Any]:
    """Energía por mes.

    NOTA: se replica la consulta de SMEC_POTENCIA_API.P_GET_ENERGIA_MES en vez
    de llamar al proc, porque el proc tiene un bug (SQL dinámico con 4
    placeholders y sólo 3 valores en el USING → ORA-01008). Aquí se usan binds
    por nombre, que reutilizan el mismo valor, evitando el error.
    """
    import calendar
    from datetime import date

    from ..db import query

    if not ids:
        return {"table": "ENERGIA_MES",
                "columns": [{"key": "central", "label": "Central"}], "rows": []}

    f_ini = date(f1.year, f1.month, 1)
    # número de meses entre trunc(f2,'MM') y f_ini
    num_meses = (f2.year - f_ini.year) * 12 + (f2.month - f_ini.month)
    pivot = ", ".join(f"{i} AS m{i}" for i in range(num_meses + 1))
    centrales = ", ".join(str(int(i)) for i in ids)

    sql = f"""
        SELECT pkg_objetos.get_codigo_objeto(p.agente)     nombre_agente,
               pkg_objetos.get_codigo_objeto(p.id_central) nombre_central,
               p.*
          FROM (SELECT SUM(c.energia) energia_total, c.id id_central, r.dir,
                       r.niv5 agente, r.orden_agentes,
                       TRUNC(MONTHS_BETWEEN(TRUNC(c.fecha,'MM'), :f_ini)) offset_mes
                  FROM sm_energia_cen_dia c
                  JOIN {_REL} r ON r.niv4 = c.id
                 WHERE c.fecha >= :f_ini
                   AND c.fecha <= :f_fin
                   AND c.id IN ({centrales})
                 GROUP BY c.id, r.dir, r.niv5, r.orden_agentes,
                          TRUNC(MONTHS_BETWEEN(TRUNC(c.fecha,'MM'), :f_ini)))
         PIVOT (SUM(energia_total) FOR offset_mes IN ({pivot})) p
         ORDER BY p.orden_agentes
    """
    ultimo = calendar.monthrange(f2.year, f2.month)[1]
    filas = query(sql, {"f_ini": f_ini, "f_fin": date(f2.year, f2.month, ultimo)})
    tgt = _target(direccion)
    filas = [r for r in filas if r.get("dir") == tgt]

    columns = [{"key": "agente", "label": "Agente"},
               {"key": "central", "label": "Central"}]
    for i in range(num_meses + 1):
        mes = f_ini.month - 1 + i
        y = f_ini.year + mes // 12
        columns.append({"key": f"m{i}", "label": f"{mes % 12 + 1:02d}/{y}",
                        "format": "num"})
    columns.append({"key": "total", "label": "Total", "format": "num", "resumen": True})
    out = []
    for r in filas:
        fila = {"agente": r.get("nombre_agente"), "central": r.get("nombre_central")}
        for i in range(num_meses + 1):
            fila[f"m{i}"] = r.get(f"m{i}")
        fila["total"] = _total([fila[f"m{i}"] for i in range(num_meses + 1)])
        out.append(fila)
    return {"table": "ENERGIA_MES", "columns": columns, "rows": out}


def energia_anio(f1: datetime, f2: datetime, ids: list[int],
                 direccion: str) -> dict[str, Any]:
    """Energía por año. No existe proc dedicado en Oracle; se agrega
    sm_energia_cen_dia por año (misma técnica que energia_mes)."""
    from datetime import date

    from ..db import query

    if not ids:
        return {"table": "ENERGIA_ANIO",
                "columns": [{"key": "central", "label": "Central"}], "rows": []}

    f_ini = date(f1.year, 1, 1)
    num = f2.year - f1.year
    pivot = ", ".join(f"{i} AS a{i}" for i in range(num + 1))
    centrales = ", ".join(str(int(i)) for i in ids)
    sql = f"""
        SELECT pkg_objetos.get_codigo_objeto(p.agente)     nombre_agente,
               pkg_objetos.get_codigo_objeto(p.id_central) nombre_central,
               p.*
          FROM (SELECT SUM(c.energia) energia_total, c.id id_central, r.dir,
                       r.niv5 agente, r.orden_agentes,
                       TRUNC(MONTHS_BETWEEN(TRUNC(c.fecha,'YYYY'), :f_ini) / 12) offset_anio
                  FROM sm_energia_cen_dia c
                  JOIN {_REL} r ON r.niv4 = c.id
                 WHERE c.fecha >= :f_ini
                   AND c.fecha <= :f_fin
                   AND c.id IN ({centrales})
                 GROUP BY c.id, r.dir, r.niv5, r.orden_agentes,
                          TRUNC(MONTHS_BETWEEN(TRUNC(c.fecha,'YYYY'), :f_ini) / 12))
         PIVOT (SUM(energia_total) FOR offset_anio IN ({pivot})) p
         ORDER BY p.orden_agentes
    """
    filas = query(sql, {"f_ini": f_ini, "f_fin": date(f2.year, 12, 31)})
    tgt = _target(direccion)
    filas = [r for r in filas if r.get("dir") == tgt]
    columns = [{"key": "agente", "label": "Agente"},
               {"key": "central", "label": "Central"}]
    for i in range(num + 1):
        columns.append({"key": f"a{i}", "label": str(f_ini.year + i), "format": "num"})
    columns.append({"key": "total", "label": "Total", "format": "num", "resumen": True})
    out = []
    for r in filas:
        fila = {"agente": r.get("nombre_agente"), "central": r.get("nombre_central")}
        for i in range(num + 1):
            fila[f"a{i}"] = r.get(f"a{i}")
        fila["total"] = _total([fila[f"a{i}"] for i in range(num + 1)])
        out.append(fila)
    return {"table": "ENERGIA_ANIO", "columns": columns, "rows": out}


# ───────────────────────────── Factor de carga ────────────────────────────────

def _factor(energia, pot_max, horas) -> float:
    """Fórmula de SMEC.CALCULATE_FACTOR: TRUNC(suma/(max*horas), 2), 0 si el
    máximo o las horas son 0. Se usan valores absolutos porque el signo de la
    energía/potencia depende de la orientación del medidor."""
    import math

    if not pot_max or not horas or energia is None:
        return 0.0
    f = abs(energia) / (abs(pot_max) * horas)
    return math.trunc(f * 100) / 100


def factor_carga(f1: datetime, f2: datetime, ids: list[int],
                 direccion: str) -> dict[str, Any]:
    """Factor de carga por central: |energía del período| /
    (|potencia máxima del período| × horas). No existe proc Oracle de reporte;
    se combina sm_energia_cen_dia con P_GET_MAXIMO_ENTREFECHAS usando la
    fórmula de SMEC.CALCULATE_FACTOR (fuente verificada en all_source)."""
    from ..db import query

    if not ids:
        return {"table": "FACTOR",
                "columns": [{"key": "central", "label": "Central"}], "rows": []}

    tgt = _target(direccion)
    horas = ((f2.date() - f1.date()).days + 1) * 24
    centrales = ", ".join(str(int(i)) for i in ids)

    energias = query(f"""
        SELECT pkg_objetos.get_codigo_objeto(r.niv5) agente,
               pkg_objetos.get_codigo_objeto(c.id)  central,
               r.dir, r.orden_agentes, SUM(c.energia) energia
          FROM sm_energia_cen_dia c
          JOIN {_REL} r ON r.niv4 = c.id
         WHERE c.fecha BETWEEN TRUNC(:f1) AND TRUNC(:f2)
           AND c.id IN ({centrales})
         GROUP BY r.niv5, c.id, r.dir, r.orden_agentes
         ORDER BY r.orden_agentes
    """, {"f1": f1, "f2": f2})
    energias = [e for e in energias if e["dir"] == tgt]

    mcols, mrows = call_proc(f"{PKG}.P_GET_MAXIMO_ENTREFECHAS",
                             [f1, f2, centrales])
    mdi, mc, mp = _idx(mcols, "DIR"), _idx(mcols, "CENTRAL"), _idx(mcols, "POT_MAX")
    pot_por_central = {r[mc]: r[mp] for r in mrows if mdi < 0 or r[mdi] == tgt}

    out = []
    for e in energias:
        p = pot_por_central.get(e["central"])
        out.append({
            "agente": e["agente"],
            "central": e["central"],
            "energia": e["energia"],
            "pot_max": p,
            "horas": horas,
            "factor": _factor(e["energia"], p, horas),
        })
    columns = [
        {"key": "agente", "label": "Agente"},
        {"key": "central", "label": "Central"},
        {"key": "energia", "label": "Energía (kWh)", "format": "num"},
        {"key": "pot_max", "label": "Pot. Máx (kW)", "format": "num"},
        {"key": "horas", "label": "Horas"},
        {"key": "factor", "label": "Factor de carga", "format": "0.00"},
    ]
    aviso = ("Factor = |Energía| / (|Pot. Máx| × horas del período) — "
             "fórmula de SMEC.CALCULATE_FACTOR.")
    if any(r["factor"] and r["factor"] > 1 for r in out):
        aviso += (" Un factor > 1 indica que la potencia máxima registrada no "
                  "es representativa para esa central (convención de signo "
                  "del medidor).")
    return {"table": "FACTOR", "columns": columns, "rows": out, "aviso": aviso}
