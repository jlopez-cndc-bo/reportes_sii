"""Potencia efectiva oficial por unidad (MW) y su central, del archivo semestral del CNDC.

No está en Oracle: sale de los Excel semestrales «Potencia efectiva <semestre>»
(hoja PotenciaEfectiva), de nov-2020 en adelante, generados a potencia_efectiva.json
con tools/cargar_potencia_efectiva.py. Cada revisión rige desde su fecha (la primera
de cada semestre, desde el inicio del semestre). La usan SMEC (Potencia limitada) y
Reporte de la Operación (% por central, MW indisponibles).

- Térmicas a temperatura media. Ciclos combinados con su valor CC
  (WARxy→CCWARxy, ERIxy→CCERIxy, SURxy→CCSURxy, GCH09/10→GCHxxCOM; las x0 son
  el bloque). ERI01-04 = Entre Ríos 11/12/21/22, WAR05 = Warnes 51 (Operación,
  2026-11-19). GCH12 (vapor) depende del estado de operación: sin dato.
- Hidroeléctricas por unidad tal cual el archivo.
- Eólicas y solares: el archivo sólo trae MW y número de unidades por central;
  por unidad = MW ÷ unidades. Bagazo: una unidad equivalente por central.
- Equivalencias nombre del archivo → código validadas por el usuario 2026-11-23.
- La central sale del archivo, no de OBJETOS_OBJETOS (jerarquía de red no confiable).

shortcut: Excel por semestre; cada noviembre y mayo agregar el archivo nuevo a la
carpeta, correr el script y subir FIN_ULTIMA. A futuro: Quantum.
"""
import json
from datetime import date, timedelta
from pathlib import Path


def _serie(prefijo: str, desde: int, hasta: int) -> list[str]:
    return [f"{prefijo}{i:02d}" for i in range(desde, hasta + 1)]


_DATOS = json.loads(Path(__file__).with_name("potencia_efectiva.json").read_text(encoding="utf-8"))
EFECTIVA: dict[date, dict[str, float]] = {
    date.fromisoformat(d): v["mw"] for d, v in _DATOS["vigencias"].items()}
# Hasta cuándo rige la última vigencia cargada (fin del semestre del archivo).
_FIN_ULTIMA = date.fromisoformat(_DATOS["fin_ultima"])
# Temperatura media (°C) de cada térmica en el primer archivo (nov-2020): con ella se evalúa la
# curva de POSTDES.GAS en fechas sin Excel (ver reports.potencia_temperatura.efectiva_dia).
T_MEDIA_INICIAL: dict[str, float] = _DATOS["t_media_inicial"]


def _centrales(**grupos: list[str]) -> dict[str, str]:
    return {codigo: central for central, codigos in grupos.items() for codigo in codigos}


# Central de cada unidad, con los nombres del archivo; sirve para ponderar por
# central y su suma reproduce el total de la central en el archivo. Ciclos
# combinados: CCxx0/xx1/xx2 son estados operativos del mismo bloque (usuario,
# 2026-11-23); la central cuenta el bloque una vez con el estado completo (x0),
# así que x1/x2 no van acá (siguen en EFECTIVA para Potencia limitada). Los
# códigos combinados de Guaracachi (GCH09COM…) tampoco: GCH09/10 ya llevan su
# valor combinado y son los que tienen eventos.
CENTRAL: dict[str, str] = {
    **_centrales(**{
        "Guaracachi": ["GCH01", "GCH02", "GCH04", "GCH06", "GCH09", "GCH10", "GCH11"],
        "Santa Cruz": ["SCZ01", "SCZ02"],
        "Valle Hermoso": ["VHE02", "VHE03", "VHE05", "VHE06", "VHE07", "VHE08"],
        "Aranjuez": ["ARJ01", "ARJ02", "ARJ03", "ARJ08", "ARJ09", "ARJ11", "ARJ12", "ARJ13",
                     "ARJ14", "ARJ15"],
        "Carrasco": ["CAR01", "CAR02", "CAR03"],
        "El Alto": ["ALT01", "ALT02"],
        "Bulo Bulo": ["BUL01", "BUL03"],
        "Entre Ríos": ["ERI01", "ERI02", "ERI03", "ERI04", "ERI30", "ERI40", "ERI50"],
        "Termoeléctrica del Sur": ["SUR10", "SUR20", "SUR30", "SUR40"],
        "Central Warnes": ["WAR05", "WAR10", "WAR20", "WAR30", "WAR40"],
        "Central Moxos": ["MOA02", "MOA05", "MOA06", "MOA07", "MOA08"],
        "Guabirá": ["GBE01"], "Iagsa": ["IAG01"], "Unagro": ["UNA01"],
        "Aguaí": ["AGU01", "AGU02", "AGU03"], "San Buenaventura": ["SBU01"],
        "Miguilla": ["MIG01", "MIG02"], "Angostura": ["ANG01", "ANG02", "ANG03"],
        "Choquetanga": ["CHO01", "CHO02", "CHO03"], "Carabuco": ["CRB"],
        "Zongo": ["ZON"], "Tiquimani": ["TIQ"], "Botijlaca": ["BOT01", "BOT02", "BOT03"],
        "Cuticucho": _serie("CUT", 1, 5),
        "Santa Rosa LH": ["SRO01"], "Santa Rosa HH": ["SRO02"], "Sainani": ["SAI"],
        "Chururaqui": ["CHU01", "CHU02"], "Harca": ["HAR01", "HAR02"],
        "Cahua": ["CAH01", "CAH02"], "Huaji": ["HUA01", "HUA02"],
        "Chojlla": ["CHJ"], "Yanacachi": ["YAN"],
        "Corani": _serie("COR", 1, 5), "Santa Isabel": _serie("SIS", 1, 5),
        "San José I": ["SJS01", "SJS02"], "San José II": ["SJE01", "SJE02"],
        "Kanata": ["KAN"], "Quehata": ["QUE01", "QUE02"], "San Jacinto": ["SJA01", "SJA02"],
        "Misicuni": _serie("MIS", 1, 3),
        "Qollpana I": ["QOL01", "QOL02"], "Qollpana II": _serie("QOL", 3, 10),
        "Warnes I": _serie("EWA", 1, 4), "San Julián": _serie("SJU", 1, 11),
        "El Dorado": _serie("EDO", 1, 15),
        "Solar Oruro Fase 1": _serie("ORU", 1, 19), "Solar Oruro Fase 2": _serie("ORU", 20, 38),
        "Solar Yunchará": ["YUN01", "YUN02"],
        "Solar Uyuni": _serie("UYU", 1, 21), "Solar Uyuni Fase 2": ["UYU22"],
    }),
}


# Estados parciales de los bloques (x1/x2): no ponderan, pero si se marcan
# identifican su central igual que el bloque.
ESTADOS_CC: dict[str, str] = {
    f"{pref}{b}{e}": central
    for pref, central, bloques in [("ERI", "Entre Ríos", (3, 4, 5)),
                                   ("SUR", "Termoeléctrica del Sur", (1, 2, 3, 4)),
                                   ("WAR", "Central Warnes", (1, 2, 3, 4))]
    for b in bloques for e in (1, 2)
}


def central_de(codigo: str) -> str | None:
    """Central de una unidad o de un estado de bloque; None si no está en la tabla."""
    return CENTRAL.get(codigo) or ESTADOS_CC.get(codigo)


def vigencia(dia: date) -> tuple[date, date] | None:
    """(desde, hasta) de la vigencia que rige ese día, o None si no hay ninguna."""
    inicios = sorted(EFECTIVA)
    previos = [v for v in inicios if v <= dia]
    if not previos or dia > _FIN_ULTIMA:
        return None
    desde = previos[-1]
    siguientes = [v for v in inicios if v > desde]
    hasta = siguientes[0] - timedelta(days=1) if siguientes else _FIN_ULTIMA
    return desde, hasta


def efectiva(codigo: str, dia: date) -> float | None:
    """Potencia efectiva vigente para la unidad ese día, o None si no hay dato."""
    vig = vigencia(dia)
    return EFECTIVA[vig[0]].get(codigo) if vig else None


def efectiva_proxima(codigo: str, dia: date) -> float | None:
    """Potencia efectiva de la vigencia que rige el día o, si ninguna rige, de la más próxima.

    Para valores que cambian poco (hidro, eólica, solar…) cuando se necesita una referencia aun
    fuera de las vigencias cargadas; los cálculos oficiales siguen usando `efectiva`.
    """
    return EFECTIVA[vigencia_proxima(dia)[0]].get(codigo)


def vigencia_proxima(dia: date) -> tuple[date, date, bool]:
    """(desde, hasta, oficial): la vigencia que rige el día o, si ninguna rige, la más próxima.

    Las vigencias cargadas son contiguas, así que fuera de ellas la más próxima es la primera
    (antes del inicio) o la última (después del fin). oficial=False → el reporte debe avisarlo.
    """
    vig = vigencia(dia)
    if vig:
        return (*vig, True)
    inicios = sorted(EFECTIVA)
    return (*vigencia(inicios[0] if dia < inicios[0] else inicios[-1]), False)
