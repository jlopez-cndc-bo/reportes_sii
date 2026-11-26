"""Reportes SMEC del SIN completo (grupo «SIN» del rail).

Se calculan siempre con TODAS las centrales de la dirección; el árbol sólo
elige qué centrales se desglosan (potencia de punta del SIN).
"""
from datetime import datetime, timedelta
from typing import Any

from ..db import call_proc, query
from . import estructura
from .reportes import PKG, _idx, _interval_labels, energia_dia

_INY = -1  # DIR de inyección en los procs de potencia/energía SMEC
_RET = 1  # DIR de retiro


def _dias(f1: datetime, f2: datetime) -> list[datetime]:
    return [f1 + timedelta(days=i) for i in range((f2.date() - f1.date()).days + 1)]


def _pico_del_dia(cols: list[str], rows: list[tuple]) -> dict[str, Any] | None:
    """Intervalo de 15 min con el mayor retiro total (la punta que publica el
    CNDC), la generación total en él y la de cada central. Pura (sin BD)."""
    icols = [c for c in cols if c.startswith("I") and c[1:].isdigit()]
    iidx = [cols.index(c) for c in icols]
    di, ic = _idx(cols, "DIR"), _idx(cols, "COD_CENTRAL")
    iny = [r for r in rows if r[di] == _INY]
    ret = [r for r in rows if r[di] == _RET]

    def total(filas, j):
        return sum(r[j] or 0 for r in filas) if any(r[j] is not None for r in filas) else None

    puntas = [total(ret, j) for j in iidx]
    if not any(t is not None for t in puntas):
        return None
    k = max((i for i, t in enumerate(puntas) if t is not None), key=lambda i: puntas[i])
    j = iidx[k]
    gen = total(iny, j)
    return {"hora": _interval_labels(len(icols))[k], "total": round(puntas[k], 6),
            "generacion": round(gen, 6) if gen is not None else None,
            "aporte": {r[ic]: r[j] for r in iny}}


def pico_sin(f1: datetime, f2: datetime, ids: list[int], pct: bool = False) -> dict[str, Any]:
    """Una fila por día: hora y valor de la punta del SIN (máximo retiro total
    en 15 min), la generación en ese intervalo y la de cada central marcada;
    «Resto» = la generación de las demás (centrales + Resto = generación)."""
    sel = list(dict.fromkeys(ids))
    nombres: dict[int, str] = {}
    out = []
    for d in _dias(f1, f2):
        cols, rows = call_proc(f"{PKG}.P_GET_POTENCIA_CENTRAL", [d, None])
        ic, nc, di = _idx(cols, "COD_CENTRAL"), _idx(cols, "CENTRAL"), _idx(cols, "DIR")
        nombres.update({r[ic]: r[nc] for r in rows if r[di] == _INY})
        p = _pico_del_dia(cols, rows)
        fila: dict[str, Any] = {"fecha": d.strftime("%d/%m/%Y")}
        if p is None:
            out.append(fila)
            continue
        gen = p["generacion"]
        conv = (lambda v, gen=gen: round(v * 100 / gen, 10) if v is not None and gen else None) if pct             else (lambda v: v)
        fila.update(hora=p["hora"], total=p["total"], generacion=gen)
        if gen is not None:
            resto = gen
            for c in sel:
                v = p["aporte"].get(c)
                fila[f"c{c}"] = conv(v)
                resto -= v or 0
            fila["resto"] = conv(round(resto, 6))
        out.append(fila)
    fmt = "0.0" if pct else "num"
    columns = [{"key": "fecha", "label": "Fecha"},
               {"key": "total", "label": "Potencia de punta (retiros, kW)", "format": "num", "sinTotal": True},
               {"key": "hora", "label": "Hora de punta"},
               {"key": "generacion", "label": "Generación en ese intervalo (kW)", "format": "num", "sinTotal": True}]
    # Sumar puntas de días distintos no tiene sentido: sin fila TOTAL.
    suf = " %" if pct else ""
    columns += [{"key": f"c{c}", "label": nombres.get(c, str(c)) + suf, "format": fmt, "sinTotal": True}
                for c in sel]
    columns.append({"key": "resto", "label": "Resto" + suf, "format": fmt, "sinTotal": True})
    return {"table": "PICO_SIN", "columns": columns, "rows": out,
            "aviso": "Las centrales y «Resto» suman la generación del intervalo, no la punta "
                     "(diferencia: pérdidas y desbalance de medición)."}


def _conciliar(iny: dict[str, float | None], ret: dict[str, float | None],
               dias: list[datetime]) -> list[dict[str, Any]]:
    """Filas de conciliación por día. Pura (sin BD) para poder probarla."""
    out = []
    for i, d in enumerate(dias):
        a, b = iny.get(f"D{i}"), ret.get(f"D{i}")
        dif = round(a - b, 6) if a is not None and b is not None else None
        out.append({"fecha": d.strftime("%d/%m/%Y"), "iny": a, "ret": b, "dif": dif,
                    "pct": round(dif * 100 / a, 10) if dif is not None and a else None})
    return out


def conciliacion(f1: datetime, f2: datetime) -> dict[str, Any]:
    """Por día: energía inyectada vs retirada en todo el SIN, diferencia
    (pérdidas y desbalance de medición) y su % sobre la inyección."""
    dias = _dias(f1, f2)

    def totales(direccion: str) -> dict[str, float | None]:
        res = energia_dia(f1, f2, estructura.ids_por_direccion(direccion), direccion)
        keys = [c["key"] for c in res["columns"] if c["key"].startswith("D")]
        return {k: (round(sum(r[k] for r in res["rows"] if r.get(k) is not None), 6)
                    if any(r.get(k) is not None for r in res["rows"]) else None)
                for k in keys}

    columns = [{"key": "fecha", "label": "Fecha"},
               {"key": "iny", "label": "Inyección (kWh)", "format": "num"},
               {"key": "ret", "label": "Retiro (kWh)", "format": "num"},
               {"key": "dif", "label": "Diferencia (kWh)", "format": "num"},
               {"key": "pct", "label": "Diferencia %", "format": "0.00", "sinTotal": True}]
    return {"table": "CONCILIACION", "columns": columns,
            "rows": _conciliar(totales("iny"), totales("ret"), dias),
            "aviso": "Diferencia = inyección − retiro: pérdidas y desbalance de medición."}


def _curvas(filas: list[dict[str, Any]]) -> dict[int, list[float | None]]:
    """{dir: 96 valores} desde filas (dir, intervalo 1..96, potencia). Pura."""
    out: dict[int, list[float | None]] = {-1: [None] * 96, 1: [None] * 96}
    for f in filas:
        i = int(f["intervalo"]) - 1
        if int(f["dir"]) in out and 0 <= i < 96 and f["potencia"] is not None:
            out[int(f["dir"])][i] = float(f["potencia"])
    return out


def generacion_demanda(fecha: datetime) -> dict[str, Any]:
    """Curva de un día cada 15 min: generación (inyección) y demanda (retiros) del SIN, y su
    diferencia. La demanda es la que publica el CNDC (la punta del día es su máximo)."""
    if fecha.date() > datetime.now().date():
        raise ValueError("La fecha no puede ser futura.")
    filas = query("""
        SELECT r.dir, c.intervalo, SUM(c.potencia) potencia
          FROM smec.sm_potencia_cen_intervalo c
          JOIN (SELECT DISTINCT niv4, dir FROM dw_relaciones) r ON r.niv4 = c.id
         WHERE c.fecha = TRUNC(:f)
         GROUP BY r.dir, c.intervalo""", {"f": fecha})
    c = _curvas(filas)
    gen, dem = c[_INY], c[1]
    dif = [round(g - d, 6) if g is not None and d is not None else None for g, d in zip(gen, dem)]
    labels = _interval_labels(96)

    def fila(nombre: str, vals: list[float | None]) -> dict[str, Any]:
        con = [(v, i) for i, v in enumerate(vals) if v is not None]
        vmax, imax = max(con) if con else (None, None)
        return {"nombre": nombre, **{f"i{i}": v for i, v in enumerate(vals)},
                "maximo": vmax, "hora_max": labels[imax] if con else None}

    columns = [{"key": "nombre", "label": "Curva"},
               *({"key": f"i{i}", "label": lab, "format": "num", "sinTotal": True}
                 for i, lab in enumerate(labels)),
               {"key": "maximo", "label": "Máx", "format": "num", "resumen": True, "sinTotal": True},
               {"key": "hora_max", "label": "Hora máx", "resumen": True}]
    rows = [] if not any(v is not None for v in gen + dem) else [
        fila("Generación (inyección)", gen), fila("Demanda (retiros)", dem),
        fila("Diferencia (pérdidas y desbalance)", dif)]
    return {"table": "GENERACION_DEMANDA", "columns": columns, "rows": rows,
            "aviso": "Demanda = retiros SMEC: su máximo es la potencia de punta del día que publica el "
                     "CNDC. Diferencia = generación − demanda (pérdidas y desbalance de medición)."}
