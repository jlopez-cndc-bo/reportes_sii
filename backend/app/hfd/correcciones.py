"""Correcciones de señales HFD por operadores SCADA (tabla SPECTRUM.HFD_CORRECCION).

No se edita TDM_*_SP7: rs7 recargaría el día y borraría la edición. Aquí sólo se
registran las correcciones (auditadas) y rs7 las aplica al cargar; por eso, tras
guardar, se pide a rs7 la recarga del día (ver recargar_dia).

Convención de intervalos: la del archivo HFD (0..95 = 00:00..23:45).
"""
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import oracledb

from ..config import get_settings
from ..db import query, transaccion

TABLA_TDM = {"generadores": "TDM_GE30_SP7"}  # por ahora sólo generación
MAGNITUDES = {"P", "Q"}
MAX_DIAS_ATRAS = 31
MOTIVO_MIN = 10

# Señal HFD -> (medidor SMEC, factor). QOL01/QOL02 (Qollpana fase I) comparten el
# medidor 1011 (objetos 8159): mitad cada una. Agregar aquí otras señales con medidor.
MEDIDOR_SMEC: dict[int, tuple[int, float]] = {
    8134: (8159, 0.5),
    8135: (8159, 0.5),
}


def validar_dia(fecha: date, hoy: date | None = None) -> None:
    hoy = hoy or date.today()
    if fecha >= hoy:
        raise ValueError("Sólo se corrigen días cerrados (anteriores a hoy).")
    if fecha < hoy - timedelta(days=MAX_DIAS_ATRAS):
        raise ValueError(f"Sólo se corrigen los últimos {MAX_DIAS_ATRAS} días.")


def _tabla(archivo: str) -> str:
    if archivo not in TABLA_TDM:
        raise ValueError("Por ahora sólo se corrigen valores de Generadores.")
    return TABLA_TDM[archivo]


def vigentes(archivo: str, desde: date, hasta: date) -> dict[tuple, dict[str, Any]]:
    """{(fecha iso, id, el, intervalo): corrección vigente} para marcar celdas."""
    if archivo not in TABLA_TDM:
        return {}
    try:
        filas = query("""
            SELECT fecha_sng, id_obj, el, intervalo, valor, valor_original, fuente, motivo,
                   usuario, fecha_registro
              FROM spectrum.hfd_correccion
             WHERE type = :t AND fecha_sng BETWEEN :d AND :h AND anulada_por IS NULL""",
            {"t": TABLA_TDM[archivo], "d": desde, "h": hasta})
    except oracledb.DatabaseError as e:
        if "ORA-00942" in str(e):  # 014 todavía sin ejecutar: reportes sin marcas
            return {}
        raise
    return {(r["fecha_sng"].date().isoformat(), int(r["id_obj"]), r["el"], int(r["intervalo"])): r
            for r in filas}


def nota(c: dict[str, Any]) -> str:
    """Texto de la marca de una celda corregida."""
    orig = "-" if c["valor_original"] is None else f"{c['valor_original']:.2f}".replace(".", ",")
    return (f"Corregido por {c['usuario']} el {c['fecha_registro']:%d/%m/%Y %H:%M} "
            f"({c['fuente']}). Valor original: {orig}. Motivo: {c['motivo']}")


def propuesta_smec(id_obj: int, fecha: date) -> dict[str, Any]:
    """96 valores (MW) desde el medidor SMEC de la señal; None donde no hay dato.

    SMEC es el promedio de 15 min en kW; su intervalo k (1..96) cubre
    [(k-1)·15, k·15) min, igual que en Potencia limitada → intervalo HFD k-1.
    """
    if id_obj not in MEDIDOR_SMEC:
        return {"medidor": None, "valores": None}
    medidor, factor = MEDIDOR_SMEC[id_obj]
    valores: list[float | None] = [None] * 96
    for r in query("""SELECT intervalo, potencia FROM smec.sm_potencia_med_intervalo
                       WHERE id = :m AND fecha >= :d AND fecha < :d + 1""", {"m": medidor, "d": fecha}):
        k = int(r["intervalo"]) - 1
        if 0 <= k < 96 and r["potencia"] is not None:
            valores[k] = round(float(r["potencia"]) / 1000 * factor, 4)
    # El operador conoce el medidor por su código (p. ej. «1011»), no por el id interno.
    cod = query("SELECT codigo_objeto FROM objetos WHERE id_objeto = :m", {"m": medidor})
    return {"medidor": medidor, "codigo": cod[0]["codigo_objeto"] if cod else str(medidor),
            "factor": factor, "valores": valores}


def guardar(usuario: str, archivo: str, id_obj: int, el: str, fecha: date,
            cambios: list[dict[str, Any]], motivo: str) -> int:
    """Registra las correcciones de una señal y un día. Devuelve cuántas se aplicaron.

    cambios: [{"intervalo": 0..95, "valor": float | None, "fuente": "SMEC"|"MANUAL"}];
    valor None anula la corrección vigente (vuelve al valor del HFD).
    """
    tabla = _tabla(archivo)
    if el not in MAGNITUDES:
        raise ValueError("Magnitud inválida.")
    validar_dia(fecha)
    motivo = (motivo or "").strip()
    if len(motivo) < MOTIVO_MIN:
        raise ValueError(f"El motivo es obligatorio (al menos {MOTIVO_MIN} caracteres).")
    if not cambios:
        raise ValueError("No hay valores para corregir.")
    vistos = set()
    for c in cambios:
        i = c.get("intervalo")
        if not isinstance(i, int) or not 0 <= i <= 95 or i in vistos:
            raise ValueError(f"Intervalo inválido o repetido: {i}.")
        vistos.add(i)
        if c.get("valor") is not None and not isinstance(c["valor"], (int, float)):
            raise ValueError(f"Valor inválido en el intervalo {i}.")
        if c.get("fuente", "MANUAL") not in ("SMEC", "MANUAL"):
            raise ValueError("Fuente inválida.")

    clave = {"t": tabla, "id": id_obj, "el": el, "f": fecha}
    with transaccion() as cur:
        # Valor del HFD por intervalo: si ya hay corrección vigente, su valor_original
        # (la tabla TDM ya tiene el corregido); si no, lo que hay en la tabla.
        cur.execute(f"""SELECT intervalo, valor FROM spectrum.{tabla.lower()}
                         WHERE id = :id AND type = :el AND fecha_sng = :f""",
                    {k: clave[k] for k in ("id", "el", "f")})
        actual = {int(i): v for i, v in cur.fetchall()}
        cur.execute("""SELECT intervalo, valor_original FROM spectrum.hfd_correccion
                        WHERE type = :t AND id_obj = :id AND el = :el AND fecha_sng = :f
                          AND anulada_por IS NULL""", clave)
        original = {**actual, **{int(i): v for i, v in cur.fetchall()}}

        for c in cambios:
            p = {**clave, "i": c["intervalo"]}
            cur.execute("""UPDATE spectrum.hfd_correccion
                              SET anulada_por = :u, fecha_anulacion = SYSDATE
                            WHERE type = :t AND id_obj = :id AND el = :el AND fecha_sng = :f
                              AND intervalo = :i AND anulada_por IS NULL""", {**p, "u": usuario})
            if c.get("valor") is not None:
                cur.execute("""INSERT INTO spectrum.hfd_correccion
                                 (type, id_obj, el, fecha_sng, intervalo, valor_original, valor,
                                  fuente, motivo, usuario)
                               VALUES (:t, :id, :el, :f, :i, :vo, :v, :fu, :m, :u)""",
                            {**p, "vo": original.get(c["intervalo"]), "v": float(c["valor"]),
                             "fu": c.get("fuente", "MANUAL"), "m": motivo, "u": usuario})
    return len(cambios)


def recargar_dia(fecha: date) -> Iterator[str]:
    """Pide a rs7 (rspectrum7.Web) la recarga forzada del día y reenvía su avance (SSE)."""
    validar_dia(fecha)
    s = get_settings()
    url = s.rs7_reprocess_url + "?" + urllib.parse.urlencode(
        {"from": fecha.isoformat(), "to": fecha.isoformat(), "force": "true"})
    req = urllib.request.Request(url, headers={"X-Rs7-Token": s.rs7_reprocess_token} if s.rs7_reprocess_token else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            for raw in resp:
                linea = raw.decode("utf-8", "replace").rstrip("\r\n")
                if linea:
                    yield linea + "\n\n"
    except OSError as e:
        yield f"data: ✗ No se pudo contactar el ETL (rs7): {e}\n\n"
        yield "data: [FIN]\n\n"
