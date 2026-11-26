"""Genera app/potencia_efectiva.json desde los Excel semestrales de potencia efectiva del CNDC.

Uso (desde web/backend):
    python tools/cargar_potencia_efectiva.py E:\\efectiva [más carpetas o archivos...]

Lee la hoja PotenciaEfectiva de cada archivo (formato 2020–2026; los viejos traen
eólicas/solares sólo como total por central y el bagazo en la columna de térmicas).
Cada revisión rige desde su fecha (decisión del usuario, 2026-11-26):
- «Vigente desde <fecha>»: desde esa fecha.
- «Actualizado <fecha>»: desde esa fecha, salvo la primera revisión del semestre,
  que rige desde el inicio del semestre (01-nov / 01-may).
Una revisión con fecha fuera de su semestre se descarta (se informa).

Reglas de códigos (validadas por el usuario, ver docstring de app/potencia_efectiva.py):
térmicas a T media; ciclos combinados con su valor CC (CCERIxy→ERIxy, CCSURxy→SURxy,
CCWARxy→WARxy; GCH09/10 toman GCH09COM/GCH10COM); eólicas/solares = MW de la central
repartido por unidad; bagazo una unidad equivalente por central.
"""
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

SALIDA = Path(__file__).resolve().parents[1] / "app" / "potencia_efectiva.json"
FIN_ULTIMA = "2027-04-30"  # fin del último semestre cargado

MESES = {"NOVIEMBRE": 11, "MAYO": 5}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)|\(\*+\)|\*", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _serie(pref: str, desde: int, hasta: int) -> list[str]:
    return [f"{pref}{i:02d}" for i in range(desde, hasta + 1)]


# ── Hidro: nombre por unidad (columna B, MW en C) ──
_HIDRO_N = {"miguilla": "MIG", "angostura": "ANG", "choquetanga": "CHO", "botijlaca": "BOT",
            "cuticucho": "CUT", "chururaqui": "CHU", "harca": "HAR", "cahua": "CAH", "huaji": "HUA",
            "kilpani": "KIL", "landara": "LAN", "corani": "COR", "santa isabel": "SIS",
            "quehata": "QUE", "san jacinto": "SJA", "misicuni": "MIS", "santa rosa": "SRO"}
_HIDRO_1 = {"carabuco": "CRB", "zongo": "ZON", "tiquimani": "TIQ", "sainani": "SAI",
            "chojlla": "CHJ", "yanacachi": "YAN", "kanata": "KAN", "punutuma": "PUN"}


def _hidro(n: str) -> str | None:
    if n in _HIDRO_1:
        return _HIDRO_1[n]
    if m := re.fullmatch(r"san jose (i|ii)_(\d)", n):
        return f"{'SJS' if m[1] == 'i' else 'SJE'}{int(m[2]):02d}"
    if m := re.fullmatch(r"(.+?) (\d+)", n):
        pref = _HIDRO_N.get(m[1])
        return f"{pref}{int(m[2]):02d}" if pref else None
    return None


# ── Térmicas: columna G (y columnas extra con unidades sueltas), T media a la derecha ──
_TERM_N = {"guaracachi": "GCH", "santa cruz": "SCZ", "valle hermoso": "VHE", "aranjuez": "ARJ",
           "carrasco": "CAR", "el alto": "ALT", "bulo bulo": "BUL"}
_ERI_CC = {"11": "ERI01", "12": "ERI02", "21": "ERI03", "22": "ERI04"}
_BAGAZO_G = {"guabira": "GBE01", "iag": "IAG01", "iagsa": "IAG01", "unagro": "UNA01",
             "aguai": "AGU01", "san buenaventura": "SBU01"}


def _termica(n: str) -> tuple[str, bool] | None:
    """(código, es_cc). es_cc: el valor de ciclo combinado pisa al de ciclo abierto."""
    n = n.replace(" ", "") if re.fullmatch(r"[a-z]+ ?\d+com", n) else n
    if m := re.fullmatch(r"gch(\d\d)com", n):
        return f"GCH{m[1]}", True
    if m := re.fullmatch(r"gch0910com", n):
        return "GCH0910COM", False
    if m := re.fullmatch(r"cc(eri|sur|war)(\d\d)", n):
        return f"{m[1].upper()}{m[2]}", True
    if m := re.fullmatch(r"(moa|mos|rre|say|sbo|sim|yuc) ?(\d+)", n):
        return f"{m[1].upper()}{int(m[2]):02d}", False
    if m := re.fullmatch(r"entre rios ?(\d+)", n):
        d = m[1]
        return (_ERI_CC[d] if d in _ERI_CC else f"ERI{int(d):02d}"), False
    if m := re.fullmatch(r"sur ?(\d+)", n):
        return f"SUR{int(m[1]):02d}", False
    if m := re.fullmatch(r"warnes ?(\d+)", n):
        d = m[1]
        return ("WAR05" if d in ("51", "05") else f"WAR{int(d):02d}"), False
    if n in _BAGAZO_G:
        return _BAGAZO_G[n], False
    if m := re.fullmatch(r"(.+?) (\d+)", n):
        pref = _TERM_N.get(m[1])
        return (f"{pref}{int(m[2]):02d}", False) if pref else None
    return None


# ── Bagazo (sección propia en columna B, MW en D) ──
_BAGAZO_B = {"guabira": "GBE01", "iagsa": "IAG01", "unagro": "UNA01", "aguai": "AGU01",
             "aguai 01": "AGU01", "aguai 02": "AGU02", "aguai 03": "AGU03",
             "san buenaventura": "SBU01"}

# ── Eólicas y solares (columna B, MW de la central en D): unidades y peso relativo ──
_RENOV: dict[str, list[tuple[list[str], float]]] = {
    "qollpana i": [(["QOL01", "QOL02"], 3)],
    "qollpana ii": [(_serie("QOL", 3, 10), 24)],
    "eolico qollpana": [(["QOL01", "QOL02"], 3), (_serie("QOL", 3, 10), 24)],
    "warnes i": [(_serie("EWA", 1, 4), 1)], "eolico warnes 01": [(_serie("EWA", 1, 4), 1)],
    "san julian": [(_serie("SJU", 1, 11), 1)], "eolico san julian": [(_serie("SJU", 1, 11), 1)],
    "el dorado": [(_serie("EDO", 1, 15), 1)], "eolico el dorado": [(_serie("EDO", 1, 15), 1)],
    "solar fotovoltaico oruro fase 1": [(_serie("ORU", 1, 19), 1)],
    "solar fotovoltaico oruro fase 2": [(_serie("ORU", 20, 38), 1)],
    "solar fotovoltaico oruro": [(_serie("ORU", 1, 38), 1)],
    "solar fotovoltaico yunchara": [(["YUN01", "YUN02"], 1)],
    "solar fotovoltaico uyuni": [(_serie("UYU", 1, 21), 1)],
    "solar fotovoltaico uyuni fase 2": [(["UYU22"], 1)],
}


def _repartir(grupos: list[tuple[list[str], float]], mw: float) -> dict[str, float]:
    """Reparte el MW de la central: entre grupos según su peso, y en partes iguales dentro."""
    peso_total = sum(p for _, p in grupos)
    return {c: round(mw * p / peso_total / len(cods), 4) for cods, p in grupos for c in cods}


def leer(path: Path) -> dict:
    """{'semestre': date, 'fecha': date|None, 'tipo': 'vigente'|'actualizado', 'valores': {...}}."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["PotenciaEfectiva"] if "PotenciaEfectiva" in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    cel = lambda r, c: rows[r][c] if r < len(rows) and c < len(rows[r]) else None

    titulo = " ".join(str(c) for c in rows[0] if c)
    m = re.search(r"(NOVIEMBRE|MAYO)\D*?(\d{2,4})", titulo.upper())
    anio = int(m[2]) if len(m[2]) == 4 else 2000 + int(m[2])
    semestre = date(anio, MESES[m[1]], 1)
    fecha, tipo = None, "actualizado"
    for r in range(4):
        for c, v in enumerate(rows[r] if r < len(rows) else []):
            if isinstance(v, datetime):
                fecha = v.date()
                tipo = "vigente" if "vigente" in _norm(cel(r, c - 1) or "") else "actualizado"

    vals: dict[str, float] = {}
    cc: dict[str, float] = {}
    t_media: dict[str, float] = {}  # temperatura media de la unidad, del nombre «(26/37 °C)»
    # Hidro (columna B) hasta «Total Hidroeléctricas»
    for r in range(4, len(rows)):
        n = _norm(cel(r, 1) or "")
        if n.startswith("total hidro"):
            break
        if (cod := _hidro(n)) and (v := _num(cel(r, 2))) is not None:
            vals[cod] = v
    # Térmicas: columna G hasta «Total Termoeléctricas» + columnas extra (P) con unidades sueltas
    for col in (6, 15):
        for r in range(4, len(rows)):
            n = _norm(cel(r, col) or "")
            if n.startswith("total termo"):
                break
            if (t := _termica(n)) and (v := _num(cel(r, col + 1))) is not None:
                (cc if t[1] else vals)[t[0]] = v
                mt = re.search(r"\((\d+(?:[.,]\d+)?)\s*/", str(cel(r, col)))
                if mt and (t[1] or t[0] not in t_media):
                    t_media[t[0]] = float(mt[1].replace(",", "."))
    # Bagazo (sección en columna B) y renovables (columna B, MW en D)
    en_bagazo = False
    for r in range(4, len(rows)):
        n = _norm(cel(r, 1) or "")
        if n.startswith("termicas a bagazo"):
            en_bagazo = True
            continue
        if n.startswith("total termicas a bagazo"):
            en_bagazo = False
        v = _num(cel(r, 3))
        if v is None:
            continue
        if en_bagazo and n in _BAGAZO_B:
            vals[_BAGAZO_B[n]] = v
        elif n in _RENOV:
            vals.update(_repartir(_RENOV[n], v))
        elif n.startswith("solar fotovoltaico oruro") and "etapa" in n:
            vals.update(_repartir(_RENOV["solar fotovoltaico oruro"], v))
    vals.update(cc)  # el valor de ciclo combinado pisa al de ciclo abierto
    if "GCH09" in cc:  # mismos códigos COM que la carga manual de nov-2026
        vals["GCH09COM"], vals["GCH10COM"] = cc["GCH09"], cc.get("GCH10")
    return {"semestre": semestre, "fecha": fecha, "tipo": tipo, "t_media": t_media,
            "valores": {k: round(v, 4) for k, v in vals.items() if v is not None}}


def _fin_semestre(s: date) -> date:
    return date(s.year + 1, 4, 30) if s.month == 11 else date(s.year, 10, 31)


def vigencias(archivos: list[Path]) -> tuple[dict[date, dict], dict[date, str], list[str], dict]:
    avisos: list[str] = []
    leidos = []
    for f in archivos:
        d = leer(f)
        if d["fecha"] is None:
            avisos.append(f"sin fecha, descartado: {f.name}")
            continue
        if not (d["semestre"] <= d["fecha"] <= _fin_semestre(d["semestre"])) and d["tipo"] != "vigente":
            avisos.append(f"fecha {d['fecha']} fuera del semestre {d['semestre']}, descartado: {f.name}")
            continue
        leidos.append((d, f))
    # Primera revisión «Actualizado» de cada semestre: desde el inicio del semestre
    primeras: dict[date, date] = {}
    for d, _ in leidos:
        if d["tipo"] == "actualizado":
            primeras[d["semestre"]] = min(primeras.get(d["semestre"], d["fecha"]), d["fecha"])
    out: dict[date, dict] = {}
    fuente: dict[date, str] = {}
    # Temperatura media de la revisión más antigua: referencia para fechas sin Excel (curvas de la base).
    t_inicial = min(leidos, key=lambda x: x[0]["fecha"])[0]["t_media"] if leidos else {}
    for d, f in sorted(leidos, key=lambda x: (x[0]["fecha"], x[1].name)):
        desde = d["fecha"]
        if d["tipo"] == "actualizado" and primeras.get(d["semestre"]) == d["fecha"]:
            desde = d["semestre"]
        if desde in out:
            avisos.append(f"{desde}: {f.name} reemplaza a {fuente[desde]}")
        out[desde], fuente[desde] = d["valores"], f.name
    return dict(sorted(out.items())), fuente, avisos, t_inicial


def main(rutas: list[str]) -> None:
    archivos = sorted({p for r in rutas for p in ([Path(r)] if r.endswith(".xlsx")
                       else Path(r).rglob("*.xlsx")) if not p.name.startswith("~$")})
    out, fuente, avisos, t_inicial = vigencias(archivos)
    SALIDA.write_text(json.dumps({
        "fin_ultima": FIN_ULTIMA,
        "t_media_inicial": dict(sorted(t_inicial.items())),
        "vigencias": {d.isoformat(): {"archivo": fuente[d], "mw": dict(sorted(v.items()))}
                      for d, v in out.items()},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for d in out:
        print(d, len(out[d]), fuente[d])
    for a in avisos:
        print("AVISO:", a)


if __name__ == "__main__":
    main(sys.argv[1:])
