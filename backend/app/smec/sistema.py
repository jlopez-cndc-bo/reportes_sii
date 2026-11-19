"""Reportes SMEC del SIN completo (grupo «SIN» del rail).

Se calculan siempre con TODAS las centrales de la dirección; el árbol sólo
elige qué centrales se desglosan (pico del SIN).
"""
from datetime import datetime, timedelta
from typing import Any

from ..db import call_proc
from . import estructura
from .reportes import PKG, _idx, _interval_labels, energia_dia

_INY = -1  # DIR de inyección en los procs de potencia/energía SMEC


def _dias(f1: datetime, f2: datetime) -> list[datetime]:
    return [f1 + timedelta(days=i) for i in range((f2.date() - f1.date()).days + 1)]


def _pico_del_dia(cols: list[str], rows: list[tuple]) -> dict[str, Any] | None:
    """Intervalo de 15 min con la mayor inyección total y el aporte de cada
    central en él. Pura (sin BD) para poder probarla."""
    icols = [c for c in cols if c.startswith("I") and c[1:].isdigit()]
    iidx = [cols.index(c) for c in icols]
    di, ic = _idx(cols, "DIR"), _idx(cols, "COD_CENTRAL")
    iny = [r for r in rows if r[di] == _INY]
    totales = [sum(r[j] or 0 for r in iny) if any(r[j] is not None for r in iny) else None
               for j in iidx]
    if not any(t is not None for t in totales):
        return None
    k = max((i for i, t in enumerate(totales) if t is not None), key=lambda i: totales[i])
    j = iidx[k]
    return {"hora": _interval_labels(len(icols))[k], "total": round(totales[k], 6),
            "aporte": {r[ic]: r[j] for r in iny}}


def pico_sin(f1: datetime, f2: datetime, ids: list[int], pct: bool = False) -> dict[str, Any]:
    """Una fila por día: hora del pico del SIN (máxima inyección total en
    15 min), total y aporte de cada central marcada; «Resto» = las demás."""
    sel = list(dict.fromkeys(ids))
    nombres: dict[int, str] = {}
    out = []
    for d in _dias(f1, f2):
        cols, rows = call_proc(f"{PKG}.P_GET_POTENCIA_CENTRAL", [d, None])
        ic, nc = _idx(cols, "COD_CENTRAL"), _idx(cols, "CENTRAL")
        nombres.update({r[ic]: r[nc] for r in rows})
        p = _pico_del_dia(cols, rows)
        fila: dict[str, Any] = {"fecha": d.strftime("%d/%m/%Y")}
        if p is None:
            out.append(fila)
            continue
        tot = p["total"]
        conv = (lambda v: round(v * 100 / tot, 10) if v is not None and tot else None) if pct \
            else (lambda v: v)
        fila.update(hora=p["hora"], total=tot)
        resto = tot
        for c in sel:
            v = p["aporte"].get(c)
            fila[f"c{c}"] = conv(v)
            resto -= v or 0
        fila["resto"] = conv(round(resto, 6))
        out.append(fila)
    fmt = "0.0" if pct else "num"
    columns = [{"key": "fecha", "label": "Fecha"},
               {"key": "hora", "label": "Hora pico"},
               {"key": "total", "label": "Total SIN (kW)", "format": "num", "sinTotal": True}]
    # Sumar picos de días distintos no tiene sentido: sin fila TOTAL.
    suf = " %" if pct else ""
    columns += [{"key": f"c{c}", "label": nombres.get(c, str(c)) + suf, "format": fmt, "sinTotal": True}
                for c in sel]
    columns.append({"key": "resto", "label": "Resto" + suf, "format": fmt, "sinTotal": True})
    return {"table": "PICO_SIN", "columns": columns, "rows": out}


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
