"""Índices de desempeño de generadores: FOR, EFOR y EFORd.

Fórmulas y variables del documento de Operaciones (correo «Variables para cálculo de índices»,
24/11/2026), sobre los eventos de dc_eventos: 152 operación normal, 153 potencia limitada,
155 programada, 156 forzada. La unidad está «parada» (reserva) cuando no tiene ninguno de esos
eventos. Los eventos vienen partidos por día: los tramos seguidos del mismo estado se unen para
contar una sola salida o un solo arranque.

  FOR    = FOH / (FOH + SH)
  EFOR   = (FOH + EFDH) / (FOH + SH + EFDHRS)
  EFDH   = Σ(Plimitada · t) / Pefectiva + Hrs.ind.res / RSH;   EFDHRS = Hrs.ind.res / RSH
  EFORd  = (f·FOH + fp·EFDH) / (SH + f·FOH);   fp = SH / AH;   AH = SH + RSH
  f      = (1/r + 1/T) / (1/r + 1/T + 1/D);   r = FOH/salidas, T = RSH/intentos, D = SH/exitosos

Las causas que clasifican una forzada (salida forzada o arranque fallido) están en indices.json.
"""
import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..constants import TipoOperacion as T
from ..db import query
from ..potencia_efectiva import efectiva_proxima
from ..sqlutil import in_clause
from ..tablero.periodos import ahora

_CONFIG = Path(__file__).with_name("indices.json")
MAX_DIAS = 3660
_LOOKBACK = timedelta(days=2)   # para conocer el estado previo de lo que empieza el primer día
_TOL = timedelta(minutes=1)     # tramos «seguidos»: el siguiente empieza donde termina el anterior
_SERVICIO = {T.OP_NORMAL, T.POT_LIMITADA}


def _cfg() -> dict[str, list[str]]:
    return json.loads(_CONFIG.read_text(encoding="utf-8"))


def _empieza(causa: str | None, prefijos: list[str]) -> bool:
    if not prefijos:
        return True
    c = (causa or "").strip().casefold()
    return any(c.startswith(p.casefold()) for p in prefijos)


def _horas(a: datetime, b: datetime, ini: datetime, fin: datetime) -> float:
    """Horas de [a, b) dentro de [ini, fin)."""
    return max((min(b, fin) - max(a, ini)).total_seconds(), 0) / 3600


def _categoria(tipo: int) -> str:
    return "S" if tipo in _SERVICIO else ("F" if tipo == T.FORZADA else "P")


def variables(segs: list[dict], ini: datetime, fin: datetime, cfg: dict[str, list[str]],
              efectiva: Callable[[date], float | None]) -> dict[str, Any]:
    """Variables de una unidad en [ini, fin). Pura.

    segs: eventos {tipo, ini, fin, causa, plim} ordenados por ini, ya cerrados, incluyendo los
    días previos a `ini` para saber de qué estado viene lo que empieza al inicio del rango.
    """
    # Corridas: tramos seguidos de la misma categoría (servicio, programada, forzada).
    corridas: list[dict] = []
    for s in segs:
        cat = _categoria(s["tipo"])
        ult = corridas[-1] if corridas else None
        if ult and ult["cat"] == cat and s["ini"] - ult["fin"] <= _TOL:
            ult["fin"] = max(ult["fin"], s["fin"])
            ult["segs"].append(s)
        else:
            previo = ult["cat"] if ult and s["ini"] - ult["fin"] <= _TOL else "parada"
            corridas.append({"cat": cat, "ini": s["ini"], "fin": s["fin"], "causa": s["causa"],
                             "previo": previo, "segs": [s]})

    v = {"sh": 0.0, "rsh": 0.0, "foh": 0.0, "ind_res": 0.0, "sin_clasificar": 0.0,
         "salidas": 0, "intentos": 0, "exitosos": 0, "plim_eq": 0.0, "sin_efectiva": False}
    for c in corridas:
        horas = sum(_horas(s["ini"], s["fin"], ini, fin) for s in c["segs"])
        empieza_en_rango = ini <= c["ini"] < fin
        if c["cat"] == "S":
            v["sh"] += horas
            v["exitosos"] += empieza_en_rango and c["previo"] == "parada"
        elif c["cat"] == "F":
            if c["previo"] == "S" and _empieza(c["causa"], cfg["causa_salida_forzada"]):
                v["foh"] += horas
                v["salidas"] += empieza_en_rango
            elif c["previo"] == "parada" and _empieza(c["causa"], cfg["causa_arranque_fallido"]):
                v["ind_res"] += horas
                v["intentos"] += empieza_en_rango
            else:
                v["sin_clasificar"] += horas
        for s in c["segs"]:
            if s["tipo"] == T.POT_LIMITADA and s["plim"] is not None:
                h = _horas(s["ini"], s["fin"], ini, fin)
                pef = efectiva(s["ini"].date()) if h else None
                if pef:
                    v["plim_eq"] += s["plim"] * h / pef
                elif h:
                    v["sin_efectiva"] = True

    # Reserva: lo que no cubre ningún evento dentro del rango.
    cubierto, hasta = 0.0, ini
    for s in sorted(segs, key=lambda s: s["ini"]):
        a, b = max(s["ini"], hasta), min(s["fin"], fin)
        if b > a:
            cubierto += (b - a).total_seconds() / 3600
            hasta = b
    v["rsh"] = (fin - ini).total_seconds() / 3600 - cubierto
    return v


def indices(v: dict[str, Any]) -> dict[str, float | None]:
    """FOR, EFOR y EFORd (en %) a partir de las variables. Pura."""
    sh, rsh, foh = v["sh"], v["rsh"], v["foh"]
    efdhrs = v["ind_res"] / rsh if rsh else 0.0
    efdh = v["plim_eq"] + efdhrs
    inv_r = v["salidas"] / foh if foh else 0.0
    inv_t = v["intentos"] / rsh if rsh else 0.0
    inv_d = v["exitosos"] / sh if sh else 0.0
    den_f = inv_r + inv_t + inv_d
    f = (inv_r + inv_t) / den_f if den_f else None
    ah = sh + rsh
    fp = sh / ah if ah else None
    efor_den = foh + sh + efdhrs
    efordd = None
    if f is not None and fp is not None and sh + f * foh:
        efordd = (f * foh + fp * efdh) / (sh + f * foh) * 100
    return {
        "ah": ah, "efdh": efdh, "efdhrs": efdhrs, "f": f, "fp": fp,
        "for": foh / (foh + sh) * 100 if foh + sh else None,
        "efor": (foh + efdh) / efor_den * 100 if efor_den else None,
        "eford": efordd,
    }


_SQL = """
SELECT e.id_elemento, o.codigo_objeto cod, e.id_tipo_operacion tipo, e.hora_ingreso ini,
       e.hora_salida fin, e.causa, e.potencia_limitada plim
  FROM dc_eventos e JOIN objetos o ON o.id_objeto = e.id_elemento
 WHERE e.fecha >= :f1 AND e.fecha < :f2
   AND e.id_tipo_operacion IN (:opn, :opl, :pro, :forz)
   AND o.cte_elemento = 'GENERADOR'
   AND e.id_elemento IN {in_sql}
 ORDER BY e.id_elemento, e.hora_ingreso
"""

_COLUMNAS = [
    ("codigo", "Unidad", None),
    ("for", "FOR (%)", "0.00"), ("efor", "EFOR (%)", "0.00"), ("eford", "EFORd (%)", "0.00"),
    ("f", "f", "0.0000"), ("fp", "fp", "0.0000"),
    ("sh", "SH (h)", "0.00"), ("rsh", "RSH (h)", "0.00"), ("ah", "AH (h)", "0.00"),
    ("foh", "FOH (h)", "0.00"), ("ind_res", "Ind. en reserva (h)", "0.00"),
    ("sin_clasificar", "Forzada s/clasif. (h)", "0.00"),
    ("efdh", "EFDH (h)", "0.00"), ("efdhrs", "EFDHRS (h)", "0.0000"),
    ("salidas", "N° salidas forzadas", "num"), ("intentos", "N° arranques intentados", "num"),
    ("exitosos", "N° arranques exitosos", "num"),
]
_SIN_TOTAL = {"for", "efor", "eford", "efdhrs", "f", "fp"}


_HORIZONTE = timedelta(days=400)   # tamaño de cada tramo al buscar el inicio de una forzada larga
_MAX_TRAMOS = 30                    # ~33 años: en la práctica, hasta el comienzo de los datos


def _eventos(unidades: list[int], f1: datetime, f2: datetime) -> dict[str, list[dict]]:
    in_sql, binds = in_clause(unidades)
    filas = query(_SQL.format(in_sql=in_sql), {
        **binds, "f1": f1, "f2": f2,
        "opn": T.OP_NORMAL, "opl": T.POT_LIMITADA, "pro": T.PROGRAMADA, "forz": T.FORZADA})
    por_unidad: dict[str, list[dict]] = {}
    for r in filas:
        por_unidad.setdefault(r["cod"], []).append({
            "id": int(r["id_elemento"]), "tipo": int(r["tipo"]), "ini": r["ini"],
            "fin": r["fin"] or ahora(), "causa": r["causa"],
            "plim": float(r["plim"]) if r["plim"] is not None else None})
    return por_unidad


def origen(previos: list[dict], hasta: datetime) -> list[dict]:
    """De los eventos anteriores a `hasta` (ordenados), la cadena de forzadas seguidas que termina
    en `hasta` más el evento que la precede sin hueco (su estado previo). Pura."""
    cadena: list[dict] = []
    borde = hasta
    for s in reversed(previos):
        if abs(s["fin"] - borde) > _TOL:
            break
        cadena.insert(0, s)
        if s["tipo"] != T.FORZADA:
            break
        borde = s["ini"]
    return cadena


def _cadena_previa(id_: int, cod: str, hasta: datetime) -> tuple[list[dict], bool]:
    """Busca hacia atrás, de a tramos de _HORIZONTE, el inicio de la forzada abierta en `hasta`,
    aunque quede fuera de la ventana. Devuelve (cadena, se encontró el inicio)."""
    cadena: list[dict] = []
    for _ in range(_MAX_TRAMOS):
        tramo = origen(_eventos([id_], hasta - _HORIZONTE, hasta).get(cod, []), hasta)
        cadena = tramo + cadena
        if not tramo or tramo[0]["tipo"] != T.FORZADA or tramo[0]["ini"] > hasta - _HORIZONTE:
            return cadena, True
        hasta = tramo[0]["ini"]
    return cadena, False


def reporte(f1: datetime, f2: datetime, unidades: list[int]) -> dict[str, Any]:
    if not unidades:
        raise ValueError("Marque al menos un generador en el árbol.")
    ini = datetime.combine(f1.date(), datetime.min.time())
    fin = min(datetime.combine(f2.date(), datetime.min.time()) + timedelta(days=1), ahora())
    if (fin - ini).days > MAX_DIAS:
        raise ValueError(f"El rango máximo es de {MAX_DIAS} días.")
    cfg = _cfg()
    desde = ini - _LOOKBACK
    por_unidad = _eventos(unidades, desde, fin)
    # Forzadas que ya venían de antes de la ventana: sólo el primer día lleva el clasificador
    # («Disparo, …»), así que se busca hacia atrás el inicio de la cadena y su estado previo.
    abiertas = {segs[0]["id"]: cod for cod, segs in por_unidad.items()
                if segs[0]["tipo"] == T.FORZADA and segs[0]["ini"] <= desde}
    sin_origen = []
    for id_, cod in abiertas.items():
        cadena, completa = _cadena_previa(id_, cod, desde)
        if not completa:
            sin_origen.append(cod)
        por_unidad[cod] = cadena + por_unidad[cod]
    rows, sin_efectiva = [], []
    for cod in sorted(por_unidad):
        v = variables(por_unidad[cod], ini, fin, cfg, lambda d, c=cod: efectiva_proxima(c, d))
        if v.pop("sin_efectiva"):
            sin_efectiva.append(cod)
        rows.append({"codigo": cod, **v, **indices(v)})
    columns = [{"key": k, "label": lbl, **({"format": fmt} if fmt else {}),
                **({"sinTotal": True} if k in _SIN_TOTAL else {})} for k, lbl, fmt in _COLUMNAS]
    aviso = " ".join(filter(None, [
        "Cálculo provisional (documento de Operaciones del 24/11/2026, pendiente de validación).",
        (f"Causas usadas: salida forzada {_lista(cfg['causa_salida_forzada'])}, "
         f"arranque fallido {_lista(cfg['causa_arranque_fallido'])}."),
        sin_efectiva and f"Sin potencia efectiva (su potencia limitada no entra en EFDH): {', '.join(sin_efectiva)}.",
        sin_origen and f"Forzada sin inicio encontrado en los datos: {', '.join(sin_origen)}.",
        len(rows) < len(unidades) and f"{len(unidades) - len(rows)} unidad(es) marcadas sin eventos "
                                      "en el rango no se muestran.",
    ]))
    return {"table": "INDICES", "columns": columns, "rows": rows, "aviso": aviso}


def _lista(prefijos: list[str]) -> str:
    return " o ".join(f"«{p}»" for p in prefijos) if prefijos else "cualquier causa"
