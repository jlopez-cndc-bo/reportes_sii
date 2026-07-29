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
        columns.append({"key": k, "label": lab, "format": "0.0"})

    out = []
    for r in rows:
        fila = {"nombre": r[ni]}
        for k, ix in zip(icols, iidx):
            fila[k] = r[ix]
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

    def fila(cols: list[str], r: tuple, nombre_col: str, nivel: int) -> dict:
        out = {"nombre": r[cols.index(nombre_col)], "_nivel": nivel}
        for k in icols:
            out[k] = r[cols.index(k)] if k in cols else None
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

    labels = _interval_labels(len(icols))
    columns = [{"key": "nombre", "label": "Agente / Central / Medidor"}]
    for k, lab in zip(icols, labels):
        columns.append({"key": k, "label": lab, "format": "0.0"})
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
        columns.append({"key": c, "label": dt.strftime("%d/%m"), "format": "0.0"})
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
               {"key": "pot_max", "label": "Potencia Máx", "format": "0.0"},
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
    daycols = [c for c in cols if c[0] == "D" and c[1:].isdigit()]
    columns = [{"key": "agente", "label": "Agente"},
               {"key": "central", "label": "Central"}]
    for c in daycols:
        n = int(c[1:])
        columns.append({"key": c, "label": (f1 + timedelta(days=n)).strftime("%d/%m"),
                        "format": "0.0"})
    out = []
    for r in rows:
        fila = {"agente": r[ia], "central": r[ic]}
        for c in daycols:
            fila[c] = r[cols.index(c)]
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
                        "format": "0.0"})
    out = []
    for r in filas:
        fila = {"agente": r.get("nombre_agente"), "central": r.get("nombre_central")}
        for i in range(num_meses + 1):
            fila[f"m{i}"] = r.get(f"m{i}")
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
        columns.append({"key": f"a{i}", "label": str(f_ini.year + i), "format": "0.0"})
    out = []
    for r in filas:
        fila = {"agente": r.get("nombre_agente"), "central": r.get("nombre_central")}
        for i in range(num + 1):
            fila[f"a{i}"] = r.get(f"a{i}")
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
        {"key": "energia", "label": "Energía (kWh)", "format": "0.0"},
        {"key": "pot_max", "label": "Pot. Máx (kW)", "format": "0.0"},
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
