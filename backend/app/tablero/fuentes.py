"""Métricas del tablero: cada una lee UNA fuente (un nivel de dato) para un rango.

Firma: f(rango, **parametros) -> Punto, donde
    Punto = {"valor": float | None, "fecha_dato": iso | None,
             "calidad": "completo" | "parcial" | "sin_dato", "nota": str | None, "detalle": dict}

Las consultas nuevas usan binds y sólo leen.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from ..db import query
from ..hfd import consolidados as C
from ..potencia_efectiva import CENTRAL, ESTADOS_CC, central_de, efectiva, vigencia
from ..reports import potencia_temperatura as POT
from ..reports import temperatura as TEMP
from ..sisfalla.cndc_final import CNDC_FINAL_SUBQUERY, cndc_final_binds
from ..sisfalla.reportes import falla_alimentadores
from .periodos import Rango, recortar, unir

PROGRAMADA, FORZADA = 155, 156

# Retiros SMEC (DIR = 1 en dw_relaciones): de ahí salen las cifras oficiales del CNDC.
# Verificado 2026-11-24 contra cndc.bo, gestión 2025: Demanda de Energía 11.175,8 GWh
# (publicado 11.176,2) y Potencia de Punta 1.759,7 MW el 26/09/2025 19:00 (publicado 1.759,7).
# La inyección (DIR = -1) da 11.413 GWh y 1.803,9 MW: no es la demanda.
_RET = "(SELECT DISTINCT niv4 FROM dw_relaciones WHERE dir = 1)"


def _punto(valor, fecha_dato=None, calidad="completo", nota=None, **detalle) -> dict[str, Any]:
    if valor is None and calidad == "completo":
        calidad = "sin_dato"
    return {"valor": valor, "fecha_dato": fecha_dato.isoformat() if fecha_dato else None,
            "calidad": calidad, "nota": nota, "detalle": detalle}


def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _corte(r: Rango):
    """Hasta cuándo cubre el registro: un fin de medianoche es el día anterior completo."""
    return (r.hasta - timedelta(days=1)).date() if r.hasta.time() == datetime.min.time() else r.hasta


def _intervalo(fecha: datetime, intervalo: int) -> datetime:
    """SMEC numera los intervalos 1..96; el 1 empieza a las 00:00."""
    return fecha + timedelta(minutes=15 * (int(intervalo) - 1))


def _calidad_smec(dias_con_dato: int, r: Rango) -> tuple[str, str | None]:
    if dias_con_dato >= r.dias():
        return "completo", None
    return "parcial", f"SMEC tiene {dias_con_dato} de {r.dias()} días cargados."


# ─────────────────────────────── SIN · SMEC ───────────────────────────────

def smec_potencia_punta(r: Rango) -> dict[str, Any]:
    f = query(f"""
        SELECT MAX(tot) KEEP (DENSE_RANK LAST ORDER BY tot) v,
               MAX(fecha) KEEP (DENSE_RANK LAST ORDER BY tot) f,
               MAX(intervalo) KEEP (DENSE_RANK LAST ORDER BY tot) i,
               COUNT(DISTINCT fecha) dias, MAX(fecha) ultimo
          FROM (SELECT c.fecha, c.intervalo, SUM(c.potencia) tot
                  FROM smec.sm_potencia_cen_intervalo c
                  JOIN {_RET} r ON r.niv4 = c.id
                 WHERE c.fecha >= TRUNC(:d1) AND c.fecha < :d2
                 GROUP BY c.fecha, c.intervalo)""", {"d1": r.desde, "d2": r.hasta})[0]
    if f["v"] is None:
        return _punto(None, nota="SMEC sin datos en el periodo.")
    cal, nota = _calidad_smec(f["dias"], r)
    # kW → MW: la tarjeta muestra MW; el exacto en kW va en el detalle.
    return _punto(float(f["v"]) / 1000, f["ultimo"].date(), cal, nota,
                  kw=float(f["v"]), fecha_hora=_iso(_intervalo(f["f"], f["i"])))


def smec_potencia_punta_historica() -> dict[str, Any]:
    """Máximo de toda la serie SMEC (≈5 s: se cachea largo)."""
    f = query(f"""
        SELECT MAX(tot) KEEP (DENSE_RANK LAST ORDER BY tot) v,
               MAX(fecha) KEEP (DENSE_RANK LAST ORDER BY tot) f,
               MAX(intervalo) KEEP (DENSE_RANK LAST ORDER BY tot) i,
               MIN(fecha) desde
          FROM (SELECT c.fecha, c.intervalo, SUM(c.potencia) tot
                  FROM smec.sm_potencia_cen_intervalo c
                  JOIN {_RET} r ON r.niv4 = c.id
                 GROUP BY c.fecha, c.intervalo)""")[0]
    if f["v"] is None:
        return {"valor": None}
    return {"valor": float(f["v"]) / 1000, "kw": float(f["v"]),
            "fecha_hora": _iso(_intervalo(f["f"], f["i"])), "desde": _iso(f["desde"].date())}


def smec_demanda_energia(r: Rango) -> dict[str, Any]:
    f = query(f"""
        SELECT SUM(c.energia) e, COUNT(DISTINCT c.fecha) dias, MAX(c.fecha) ultimo
          FROM smec.sm_energia_cen_dia c
          JOIN {_RET} r ON r.niv4 = c.id
         WHERE c.fecha >= TRUNC(:d1) AND c.fecha < :d2""", {"d1": r.desde, "d2": r.hasta})[0]
    if f["e"] is None:
        return _punto(None, nota="SMEC sin datos en el periodo.")
    cal, nota = _calidad_smec(f["dias"], r)
    return _punto(float(f["e"]) / 1e6, f["ultimo"].date(), cal, nota, kwh=float(f["e"]))  # kWh → GWh


def smec_ultimo_dia() -> date | None:
    f = query("SELECT MAX(fecha) f FROM smec.sm_energia_cen_dia WHERE fecha >= TRUNC(SYSDATE) - 90")[0]
    return f["f"].date() if f["f"] else None


# ───────────────────────── Reporte de la Operación ─────────────────────────

def _generadores() -> dict[int, str]:
    """id_objeto → código, de las unidades GENERADOR (incluye estados CC x1/x2)."""
    return {int(f["id_objeto"]): f["codigo_objeto"] for f in query(
        "SELECT id_objeto, codigo_objeto FROM objetos WHERE cte_elemento = 'GENERADOR'")}


def _eventos(desde: datetime, hasta: datetime, ahora: datetime) -> list[dict[str, Any]]:
    """Eventos 155/156 de generadores que tocan [desde, hasta).

    En dc_eventos cada evento está partido por día (`fecha` = día de hora_ingreso y
    ninguno cruza la medianoche: 179.151 de 179.151 desde 2021, verificado 2026-11-24),
    así que filtrar por `fecha` usa el índice sin perder bordes. Abiertos: hasta `ahora`.
    """
    filas = query("""
        SELECT e.id_elemento id, o.codigo_objeto cod, e.id_tipo_operacion tipo,
               e.hora_ingreso ini, e.hora_salida fin, e.causa
          FROM dc_eventos e
          JOIN objetos o ON o.id_objeto = e.id_elemento
         WHERE o.cte_elemento = 'GENERADOR'
           AND e.id_tipo_operacion IN (:pro, :forz)
           AND e.fecha >= TRUNC(:d1) - 1 AND e.fecha < :d2""",
                  {"pro": PROGRAMADA, "forz": FORZADA, "d1": desde, "d2": hasta})
    for f in filas:
        f["fin"] = f["fin"] or ahora
    return [f for f in filas if f["ini"] < hasta and f["fin"] > desde and f["fin"] > f["ini"]]


def _tramos(eventos, tipos: set[int]) -> dict[str, list[tuple[datetime, datetime]]]:
    por: dict[str, list] = defaultdict(list)
    for e in eventos:
        if e["tipo"] in tipos and e["cod"] in CENTRAL:
            por[e["cod"]].append((e["ini"], e["fin"]))
    return {c: unir(t) for c, t in por.items()}


def _cc_excluidos(eventos) -> int:
    return len({e["cod"] for e in eventos if e["cod"] in ESTADOS_CC})


def _nota_cc(n: int) -> str | None:
    return (f"{n} estado(s) de ciclo combinado (x1/x2) con eventos no entran al cálculo: "
            "cómo se registran está por confirmar con Operación.") if n else None


def op_disponibilidad(r: Rango, ahora: datetime) -> dict[str, Any]:
    """Σ Pef(c,día) × horas disponibles / Σ Pef(c,día) × horas, día por día."""
    dias = [r.desde.date() + timedelta(days=k) for k in range(r.dias())]
    sin_pef = [d for d in dias if vigencia(d) is None]
    if sin_pef:
        return _punto(None, nota=f"Sin potencia efectiva oficial vigente el {sin_pef[0]:%d/%m/%Y} "
                                 "(la tabla cargada rige desde 01/11/2026).")
    eventos = _eventos(r.desde, r.hasta, ahora)
    tramos = _tramos(eventos, {PROGRAMADA, FORZADA})
    num = den = mwh_ind = 0.0
    for d in dias:
        dia = Rango(max(datetime.combine(d, datetime.min.time()), r.desde),
                    min(datetime.combine(d + timedelta(days=1), datetime.min.time()), r.hasta), "")
        for cod in CENTRAL:
            p = efectiva(cod, d)
            if p is None:
                continue
            ind = sum(recortar(a, b, dia) for a, b in tramos.get(cod, []))
            num += p * (dia.horas - ind)
            den += p * dia.horas
            mwh_ind += p * ind
    if not den:
        return _punto(None, nota="Sin horas en el periodo.")
    return _punto(num / den * 100, _corte(r), nota=_nota_cc(_cc_excluidos(eventos)),
                  mwh_indisponibles=round(mwh_ind, 2), unidades=len(CENTRAL))


def op_horas(r: Rango, ahora: datetime, tipo: int) -> dict[str, Any]:
    eventos = _eventos(r.desde, r.hasta, ahora)
    tramos = _tramos(eventos, {tipo})
    h = sum(recortar(a, b, r) for t in tramos.values() for a, b in t)
    return _punto(h, _corte(r), nota=_nota_cc(_cc_excluidos(eventos)), unidades=len(tramos))


def unidades_indisponibles(ahora: datetime) -> dict[str, Any]:
    """Unidades con un evento 155/156 abierto ahora, con su MW efectivo y desde cuándo."""
    eventos = _eventos(ahora - timedelta(days=60), ahora + timedelta(seconds=1), ahora)
    abiertos = [e for e in eventos if e["ini"] <= ahora <= e["fin"]]  # abiertos: fin = ahora
    out = []
    for e in abiertos:
        # «Desde»: retrocede por los tramos diarios contiguos del mismo tipo.
        previos = sorted((x for x in eventos if x["cod"] == e["cod"] and x["tipo"] == e["tipo"]),
                         key=lambda x: x["ini"], reverse=True)
        desde = e["ini"]
        for x in previos:
            if x["ini"] < desde and x["fin"] >= desde:
                desde = x["ini"]
        out.append({"unidad": e["cod"], "central": central_de(e["cod"]),
                    "tipo": "Forzada" if e["tipo"] == FORZADA else "Programada",
                    "mw": efectiva(e["cod"], ahora.date()), "desde": _iso(desde),
                    "desde_limite": desde <= ahora - timedelta(days=59),
                    "causa": e["causa"], "estado_cc": e["cod"] in ESTADOS_CC})
    # Una fila por unidad (si tiene 155 y 156 abiertos a la vez, queda la forzada).
    unicas: dict[str, dict] = {}
    for u in sorted(out, key=lambda u: u["tipo"] != "Forzada"):
        unicas.setdefault(u["unidad"], u)
    filas = sorted(unicas.values(), key=lambda u: -(u["mw"] or 0))
    return {"unidades": filas,
            "mw": round(sum(u["mw"] or 0 for u in filas if not u["estado_cc"]), 2),
            "sin_mw": sum(1 for u in filas if u["mw"] is None),
            "fecha_dato": _iso(ahora)}


def indisponibles_dia(dia: date, ahora: datetime) -> dict[str, Any]:
    """Unidades con indisponibilidad 155/156 en un día ya pasado: horas de cada tipo y su MW."""
    r = Rango(datetime.combine(dia, datetime.min.time()),
              min(datetime.combine(dia + timedelta(days=1), datetime.min.time()), ahora), "")
    eventos = _eventos(r.desde, r.hasta, ahora)
    por: dict[str, dict] = {}
    for tipo, campo in ((FORZADA, "horas_forzada"), (PROGRAMADA, "horas_programada")):
        tramos: dict[str, list] = defaultdict(list)
        for e in eventos:
            if e["tipo"] == tipo:
                tramos[e["cod"]].append((e["ini"], e["fin"]))
        for cod, t in tramos.items():
            u = por.setdefault(cod, {"unidad": cod, "central": central_de(cod), "mw": efectiva(cod, dia),
                                     "estado_cc": cod in ESTADOS_CC, "horas_forzada": 0.0,
                                     "horas_programada": 0.0})
            u[campo] = round(sum(recortar(a, b, r) for a, b in unir(t)), 2)
    filas = sorted(por.values(), key=lambda u: -((u["mw"] or 0) * (u["horas_forzada"] + u["horas_programada"])))
    return {"unidades": filas, "fecha_dato": _iso(_corte(r))}


# ───────────────────────────── Sistema de Fallas ─────────────────────────────

def fallas_ens(r: Rango) -> dict[str, Any]:
    # falla_alimentadores suma un día a un «hasta» de medianoche (lo trata como fecha
    # inclusiva): se le pasa el día anterior para que el filtro quede en < r.hasta.
    hasta = r.hasta - timedelta(days=1) if r.hasta.time() == datetime.min.time() else r.hasta
    filas = falla_alimentadores(None, None, r.desde, hasta)["rows"]
    abiertas = sum(1 for f in filas if f["ens"] is None)
    pend = _sin_final(r)
    nota = " ".join(filter(None, [
        pend and f"{pend} falla(s) del periodo aún sin informe FINAL no suman ENS.",
        abiertas and f"{abiertas} desconexión(es) sin hora de cierre no suman ENS."])) or None
    return _punto(sum(f["ens"] or 0 for f in filas), _corte(r), nota=nota,
                  desconexiones=len(filas), fallas=len({f.get("codFallaTexto") for f in filas}))


def _conteo(r: Rango) -> dict[str, int]:
    b = cndc_final_binds()
    b.update(d1=r.desde, d2=r.hasta)
    f = query(f"""
        SELECT COUNT(*) total, COUNT(s.PK_COD_FALLA) finales
          FROM F_GF_REGFALLA x
          LEFT JOIN {CNDC_FINAL_SUBQUERY} s ON s.PK_COD_FALLA = x.PK_COD_FALLA
         WHERE x.FEC_INICIO >= :d1 AND x.FEC_INICIO < :d2""", b)[0]
    return {"total": int(f["total"]), "finales": int(f["finales"])}


def _sin_final(r: Rango) -> int:
    c = _conteo(r)
    return c["total"] - c["finales"]


def fallas_conteo(r: Rango) -> dict[str, Any]:
    f = _conteo(r)
    pend = f["total"] - f["finales"]
    nota = f"Otras {pend} falla(s) registradas aún sin informe FINAL no se cuentan." if pend else None
    return _punto(f["finales"], _corte(r), nota=nota, registradas=f["total"])


# ───────────────────────────────── SCADA HFD ─────────────────────────────────

def hfd_ahora(hoy: date, congelada_n: int) -> dict[str, Any] | None:
    """Último intervalo HFD de hoy (o de ayer, recién pasada la medianoche)."""
    for dia in (hoy, hoy - timedelta(days=1)):
        filas = [f for f in C.generacion_tipo(dia)["rows"] if f["_nivel"] == 0]
        sin = [f for f in filas if f["nombre"] != "Exportación"]
        tot = C.sumar([f.get(p) for p in C._P] for f in sin)
        con = [i for i, v in enumerate(tot) if v is not None]
        if not con:
            continue
        k = con[-1]
        imax = max(con, key=lambda i: tot[i])
        base = datetime.combine(dia, datetime.min.time())
        return {
            "fecha_dato": _iso(base + timedelta(minutes=15 * k)),
            "total": tot[k],
            "tecnologias": [{"nombre": f["nombre"], "mw": f.get(f"p{k}")} for f in sin
                            if f.get(f"p{k}")],
            "exportacion": next((f.get(f"p{k}") for f in filas if f["nombre"] == "Exportación"), None),
            "maximo": {"mw": tot[imax], "hora": _iso(base + timedelta(minutes=15 * imax))},
            "congeladas": _congeladas(dia, k, congelada_n),
        }
    return None


def hfd_dia(dia: date) -> dict[str, Any] | None:
    """Curvas del día (96 intervalos): demanda del SIN = suma de departamentos, y generación
    por fuente sin Exportación. Ambas HFD operativo: no se mezclan con SMEC."""
    filas_dem = [f for f in C.demanda_departamento(dia)["rows"] if f["_nivel"] == 0]
    demanda = C.sumar([f.get(p) for p in C._P] for f in filas_dem)
    filas_gen = [f for f in C.generacion_tipo(dia)["rows"] if f["_nivel"] == 0 and f["nombre"] != "Exportación"]
    con = [i for i, v in enumerate(demanda) if v is not None]
    if not con:
        return None
    base = datetime.combine(dia, datetime.min.time())
    def hora(i: int) -> str | None:
        return _iso(base + timedelta(minutes=15 * i))

    imax = max(con, key=lambda i: demanda[i])
    imin = min(con, key=lambda i: demanda[i])
    return {
        "etiquetas": [C.R.etiqueta_intervalo(i) for i in range(96)],
        "demanda": demanda,
        "generacion": [{"nombre": f["nombre"], "valores": [f.get(p) for p in C._P]} for f in filas_gen],
        "maxima": {"mw": demanda[imax], "hora": hora(imax)},
        "minima": {"mw": demanda[imin], "hora": hora(imin)},
        "ultima": {"mw": demanda[con[-1]], "hora": hora(con[-1])},
        "intervalos": len(con),
        "fecha_dato": hora(con[-1]),
    }


def _congeladas(dia: date, k: int, n: int) -> list[dict[str, Any]]:
    """Unidades cuya P no cambió en las últimas n lecturas hasta el intervalo k, sin estar en 0.

    Mira el valor cargado hoy (aún sin correcciones, que se hacen después sobre días cerrados).
    """
    if k + 1 < n:
        return []
    unidades = C._unidades()
    out = []
    for f in C._lecturas("generadores", dia, dia):
        vals = [f.get(f"p{i}") for i in range(k - n + 1, k + 1)]
        if None in vals or len({float(v) for v in vals}) != 1 or abs(float(vals[0])) < 0.5:
            continue
        u = unidades.get(int(f["id"]))
        if u:
            out.append({"unidad": u["unidad"], "central": u["central"], "mw": float(vals[0])})
    return sorted(out, key=lambda u: (u["central"], u["unidad"]))


def temperatura_dia(dia: date) -> list[dict[str, Any]]:
    """Temperatura horaria de cada zona térmica en el día, con su máxima y la hora."""
    zonas = TEMP._zonas_activas()
    dt = datetime.combine(dia, datetime.min.time())
    vals: dict[str, list] = {z["id"]: [None] * 24 for z in zonas}
    consolidado = True
    for f in TEMP._lecturas(list(vals), dt, dt):
        vals[f["id"]][int(f["hora"])] = float(f["valor"])
        consolidado &= f["consolidado"] == 1
    return [{"zona": z["zona"].title(), "valores": vals[z["id"]], "consolidado": consolidado,
             **TEMP.resumen_dia(vals[z["id"]])} for z in zonas if any(v is not None for v in vals[z["id"]])]


def potencia_parque(dia: date, instante: datetime, ahora: datetime) -> dict[str, Any]:
    """Potencia efectiva del parque en un instante: térmicas a la temperatura de su zona (curva),
    el resto con la potencia efectiva del Excel; menos las unidades indisponibles en ese instante.
    Analítico: combina registro de eventos, curvas y temperatura (no es una cifra oficial)."""
    h = instante.hour
    unidades = POT.potencias_dia(dia)
    eventos = _eventos(instante, instante + timedelta(seconds=1), ahora)
    fuera = {e["cod"] for e in eventos if e["ini"] <= instante < e["fin"] or (e["fin"] == ahora and e["ini"] <= instante)}
    term = [u for u in unidades if u["origen"] == "curva"]
    total = sum(u["horas"][h] or 0 for u in unidades)
    indisp = sum(u["horas"][h] or 0 for u in unidades if u["unidad"] in fuera)
    return {
        "instante": _iso(instante), "hora": f"{h:02d}:00",
        "total_excel": round(sum(u["base"] or 0 for u in unidades), 1),
        "total": round(total, 1),
        "termica_excel": round(sum(u["base"] or 0 for u in term), 1),
        "termica": round(sum(u["horas"][h] or 0 for u in term), 1),
        "indisponible": round(indisp, 1),
        "disponible": round(total - indisp, 1),
        "unidades_curva": len(term), "unidades": len(unidades),
    }


METRICAS = {
    "smec_potencia_punta": smec_potencia_punta,
    "smec_demanda_energia": smec_demanda_energia,
    "op_disponibilidad": op_disponibilidad,
    "op_horas": op_horas,
    "fallas_ens": fallas_ens,
    "fallas_conteo": fallas_conteo,
}
# Métricas que necesitan la hora actual (eventos abiertos se cierran en «ahora»).
CON_AHORA = {"op_disponibilidad", "op_horas"}
