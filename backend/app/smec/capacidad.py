"""Capacidad efectiva (SPECTRUM.CAP_EFECTIVA) frente a la energía SMEC.

La capacidad efectiva se registra por *sistema* (agrupación de la empresa,
p. ej. "Corani" = CH COR + CH SIS + CH SJE), no por generador ni por central, y
en la base no hay relación sistema→central: sólo coinciden los nombres. Por eso
la relación vive aquí, validada por el usuario el 2026-11-19 comparando la
capacidad de cada sistema con la potencia máxima inyectada en 2026 (Corani
280,36 MW = 64,9 + 90,7 + 125,1 MW).

shortcut: la relación es fija en código; si aparece una central o un sistema
nuevo hay que agregarlo en GRUPOS (sin par → «Sin clasificar» / factor "-").
"""
from datetime import datetime
from typing import Any

from ..db import query
from ..sqlutil import in_clause

# (sistemas de CAP_EFECTIVA, centrales SMEC = dw_relaciones.niv4). Un grupo
# puede tener varios sistemas (Aguaí) o varias centrales (Corani, Zongo…).
GRUPOS: list[tuple[tuple[int, ...], tuple[int, ...]]] = [
    ((20121,), (3397, 3398, 8992)),         # Corani: CH COR + CH SIS + CH SJE
    ((20124,), (4027, 9105, 8392)),         # Zongo: CH SZON + CHSZONHUA + CH SCUM
    ((20146,), (7373, 20256)),              # Entre Rios: CT ERI + CT ERD
    ((20134, 20225, 9812), (9453,)),        # Aguaí + Aguaí 02 + Aguaí 03: CT AGU
    ((20130,), (9071, 180069)),             # Uyuni: CSF UYU + CSF UYU II
    ((20132,), (4261,)),                    # Guaracachi: CT GCH
    ((20148,), (8196,)),                    # Del Sur: CT SUR
    ((20147,), (8346,)),                    # Warnes: CT WAR
    ((20141,), (3457,)),                    # Carrasco: CT CAR
    ((20143,), (3468,)),                    # Bulo Bulo: CT BUL
    ((20137,), (3445,)),                    # Aranjuez: CT ARJ
    ((20139,), (3447,)),                    # Valle Hermoso: CT VHE
    ((20133,), (7206,)),                    # Santa Cruz: CT SCZ
    ((20138,), (7780,)),                    # Moxos: CT MOS
    ((20142,), (7931,)),                    # El Alto: CT ALT
    ((20127,), (8871,)),                    # Misicuni: CH MIS
    ((20119,), (4037,)),                    # Taquesi: CH STAQ
    ((20123,), (4025,)),                    # Miguillas: CH SMIG
    ((20120,), (3442,)),                    # Kanata: CH KAN
    ((20125,), (6113,)),                    # Quehata: CH QUE
    ((20126,), (8247,)),                    # San Jacinto: CH SJA
    ((20131,), (9491,)),                    # Oruro: CSF ORU
    ((20129,), (8906,)),                    # Yunchará: CSF YUN
    ((20128,), (8132,)),                    # Qollpana: CE QOL
    ((20216,), (20259,)),                   # El Dorado: CE EDO
    ((20215,), (20258,)),                   # San Julian: CE SJU
    ((20214,), (20257,)),                   # Warnes 1: CE EWA
    ((20145,), (6255,)),                    # Guabirá: CT GBE
    ((20136,), (8278,)),                    # Unagro: CT UNA
    ((20135,), (8726,)),                    # San Buenaventura: CT SBU
]
# Sin par: sistema IAGSA (20144); centrales CH SYUR, CT KAR, CT KEN, CT RRE,
# CT SBO, CT TRD, CT YUC (sin inyección en 2026).

TECNOLOGIAS = {"TER": "Térmica", "HID": "Hidroeléctrica", "SOL": "Solar",
               "EOL": "Eólica", "BIO": "Biomasa"}
SIN_CLASIFICAR = "Sin clasificar"
_GRUPO_DE_CENTRAL = {c: i for i, (_, cens) in enumerate(GRUPOS) for c in cens}


def _sistemas(f2: datetime) -> dict[int, dict]:
    """Capacidad y tecnología de cada sistema, vigentes a la fecha final."""
    filas = query("""
        SELECT c.id_sistema, o.descripcion_conv nombre, o.tipo_obj tipo, c.cap_efec
          FROM spectrum.cap_efectiva c
          JOIN objetos o ON o.id_objeto = c.id_sistema
         WHERE c.fecha_vigencia = (SELECT MAX(fecha_vigencia) FROM spectrum.cap_efectiva
                                    WHERE TRUNC(fecha_vigencia) <= TRUNC(:f2))
    """, {"f2": f2})
    return {r["id_sistema"]: r for r in filas}


def _energia(f1: datetime, f2: datetime, ids: list[int]) -> dict[int, dict]:
    """Energía (kWh) por central en el período, sin pasar por dw_relaciones
    (que tiene una fila por medidor y multiplicaría la suma)."""
    in_sql, binds = in_clause(ids)
    binds.update({"f1": f1, "f2": f2})
    filas = query(f"""
        SELECT o.id_objeto id, o.codigo_objeto cod, SUM(c.energia) energia
          FROM objetos o
          LEFT JOIN sm_energia_cen_dia c
            ON c.id = o.id_objeto AND c.fecha BETWEEN TRUNC(:f1) AND TRUNC(:f2)
         WHERE o.id_objeto IN {in_sql}
         GROUP BY o.id_objeto, o.codigo_objeto
    """, binds)
    return {r["id"]: r for r in filas}


def _centrales(ids: list[int]) -> list[int]:
    return ids or [c for _, cens in GRUPOS for c in cens]


def _factor(energia, cap_mw, horas) -> float | None:
    if not cap_mw or energia is None:
        return None
    return round(energia / (cap_mw * 1000 * horas), 4)


def _tecnologia(tipos: set) -> str:
    return " / ".join(sorted(TECNOLOGIAS.get(t, t) for t in tipos if t)) or SIN_CLASIFICAR


def _filas_grupo(f1: datetime, f2: datetime, ids: list[int]):
    """Una fila por grupo con al menos una central pedida + centrales sin grupo."""
    ids = _centrales(ids)
    sistemas = _sistemas(f2)
    energia = _energia(f1, f2, ids)
    horas = ((f2.date() - f1.date()).days + 1) * 24
    pedidas = set(ids)
    filas, parciales = [], []
    for sis, cens in GRUPOS:
        elegidas = [c for c in cens if c in pedidas]
        if not elegidas:
            continue
        if len(elegidas) < len(cens):
            parciales.append(" + ".join(sistemas[s]["nombre"].strip() for s in sis if s in sistemas))
        caps = [sistemas[s]["cap_efec"] for s in sis if s in sistemas]
        cap = sum(caps) if caps else None
        e = [energia[c]["energia"] for c in elegidas if energia.get(c, {}).get("energia") is not None]
        e = round(sum(e), 6) if e else None
        filas.append({
            "sistema": " + ".join(sistemas[s]["nombre"].strip() for s in sis if s in sistemas) or "-",
            "centrales": " + ".join(energia[c]["cod"] for c in elegidas if c in energia),
            "tecnologia": _tecnologia({sistemas[s]["tipo"] for s in sis if s in sistemas}),
            "cap_efec": cap, "energia": e, "factor": _factor(e, cap, horas),
        })
    for c in ids:
        if c not in _GRUPO_DE_CENTRAL and c in energia:
            filas.append({"sistema": "-", "centrales": energia[c]["cod"],
                          "tecnologia": SIN_CLASIFICAR, "cap_efec": None,
                          "energia": energia[c]["energia"], "factor": None})
    avisos = []
    if not sistemas:
        avisos.append("No hay capacidad efectiva vigente para el período (la "
                      "tabla SPECTRUM.CAP_EFECTIVA empieza en dic-2025).")
    if parciales:
        avisos.append("Selección parcial: el factor de " + ", ".join(parciales) +
                      " considera sólo las centrales marcadas, pero la capacidad "
                      "de todo el sistema.")
    return filas, avisos


def _resultado(table, columns, rows, avisos, direccion):
    if direccion != "iny":
        rows, avisos = [], ["La capacidad efectiva sólo aplica a centrales de Inyección."]
    out = {"table": table, "columns": columns, "rows": rows}
    if avisos:
        out["aviso"] = " ".join(avisos)
    return out


_COL_CAP = {"key": "cap_efec", "label": "Cap. efectiva (MW)", "format": "0.00"}
_COL_ENERGIA = {"key": "energia", "label": "Energía (kWh)", "format": "num"}
_COL_FACTOR = {"key": "factor", "label": "Factor de planta", "format": "0.00", "sinTotal": True}


def capacidad_sistema(f1: datetime, f2: datetime, ids: list[int],
                      direccion: str) -> dict[str, Any]:
    """Factor de planta por sistema: energía / (capacidad efectiva × horas)."""
    filas, avisos = _filas_grupo(f1, f2, ids)
    columns = [{"key": "sistema", "label": "Sistema"},
               {"key": "centrales", "label": "Centrales"},
               {"key": "tecnologia", "label": "Tecnología"},
               _COL_CAP, _COL_ENERGIA, _COL_FACTOR]
    return _resultado("CAPACIDAD_SISTEMA", columns, filas, avisos, direccion)


def mix_tecnologia(f1: datetime, f2: datetime, ids: list[int],
                   direccion: str) -> dict[str, Any]:
    """Capacidad, energía, participación y factor de planta por tecnología."""
    filas, avisos = _filas_grupo(f1, f2, ids)
    horas = ((f2.date() - f1.date()).days + 1) * 24
    acc: dict[str, dict] = {}
    for f in filas:
        a = acc.setdefault(f["tecnologia"], {"tecnologia": f["tecnologia"],
                                             "cap_efec": None, "energia": None})
        if f["cap_efec"] is not None:
            a["cap_efec"] = (a["cap_efec"] or 0) + f["cap_efec"]
        if f["energia"] is not None:
            a["energia"] = (a["energia"] or 0) + f["energia"]
    total = sum(a["energia"] for a in acc.values() if a["energia"] is not None)
    rows = []
    for a in sorted(acc.values(), key=lambda a: (a["tecnologia"] == SIN_CLASIFICAR,
                                                 -(a["energia"] or 0))):
        e = None if a["energia"] is None else round(a["energia"], 6)
        rows.append({**a, "energia": e,
                     "cap_efec": None if a["cap_efec"] is None else round(a["cap_efec"], 6),
                     "part": round(e * 100 / total, 10) if total and e is not None else None,
                     "factor": _factor(e, a["cap_efec"], horas)})
    columns = [{"key": "tecnologia", "label": "Tecnología"}, _COL_CAP, _COL_ENERGIA,
               {"key": "part", "label": "Part. %", "format": "0.0", "sinTotal": True},
               _COL_FACTOR]
    return _resultado("MIX_TECNOLOGIA", columns, rows, avisos, direccion)


def tecnologia_por_codigo() -> dict[str, str]:
    """Código de central SMEC → tecnología (según su sistema de capacidad)."""
    ids = _centrales([])
    in_sql, binds = in_clause(ids)
    cods = {r["id_objeto"]: r["codigo_objeto"] for r in query(
        f"SELECT id_objeto, codigo_objeto FROM objetos WHERE id_objeto IN {in_sql}", binds)}
    sis_ids = sorted({s for sis, _ in GRUPOS for s in sis})
    in_s, bs = in_clause(sis_ids, "s")
    tipos = {r["id_objeto"]: r["tipo_obj"] for r in query(
        f"SELECT id_objeto, tipo_obj FROM objetos WHERE id_objeto IN {in_s}", bs)}
    out = {}
    for sis, cens in GRUPOS:
        t = _tecnologia({tipos.get(s) for s in sis})
        for c in cens:
            if c in cods:
                out[cods[c]] = t
    return out
