"""Potencia efectiva oficial por unidad (MW) y su central, del archivo semestral del CNDC.

No está en Oracle: se carga a mano desde «Potencia efectiva <semestre>»
(hoy 01_Nov26_Abr27.xlsx, hoja PotenciaEfectiva). La usan SMEC (Potencia
limitada) y Reporte de la Operación (% por central, MW indisponibles).

- Térmicas a temperatura media. Ciclos combinados con su valor CC
  (WARxy→CCWARxy, ERIxy→CCERIxy, SURxy→CCSURxy, GCH09/10→GCHxxCOM; las x0 son
  el bloque). ERI01-04 = Entre Ríos 11/12/21/22, WAR05 = Warnes 51 (Operación,
  2026-11-19). GCH12 (vapor) depende del estado de operación: sin dato.
- Hidroeléctricas por unidad tal cual el archivo.
- Eólicas y solares: el archivo sólo trae MW y número de unidades por central;
  por unidad = MW ÷ unidades. Bagazo: una unidad equivalente por central.
- Equivalencias nombre del archivo → código validadas por el usuario 2026-11-23.
- La central sale del archivo, no de OBJETOS_OBJETOS (jerarquía de red no confiable).

shortcut: tabla a mano por semestre; actualizar cada noviembre y mayo con el
archivo nuevo (agregar una vigencia, no pisar la anterior). A futuro: Quantum.
"""
from datetime import date, timedelta


def _iguales(codigos: list[str], mw_central: float) -> dict[str, float]:
    """Reparte la potencia de una central entre unidades iguales."""
    return {c: round(mw_central / len(codigos), 4) for c in codigos}


def _serie(prefijo: str, desde: int, hasta: int) -> list[str]:
    return [f"{prefijo}{i:02d}" for i in range(desde, hasta + 1)]


EFECTIVA: dict[date, dict[str, float]] = {
    date(2026, 11, 1): {
        # ── Termoeléctricas (temperatura media) ──
        "GCH01": 18.62, "GCH02": 17.62, "GCH04": 19.95, "GCH06": 20.71, "GCH11": 62.22,
        "GCH09": 102.03, "GCH10": 100.97,
        "GCH09COM": 102.03, "GCH10COM": 100.97, "GCH0910COM": 206.83,
        "SCZ01": 20.76, "SCZ02": 21.19,
        "VHE02": 18.81, "VHE03": 18.32, "VHE05": 10.58, "VHE06": 10.58, "VHE07": 10.58, "VHE08": 10.58,
        "ARJ01": 2.7, "ARJ02": 2.24, "ARJ03": 2.62, "ARJ08": 18.39, "ARJ09": 1.49, "ARJ11": 1.49,
        "ARJ12": 1.6, "ARJ13": 1.55, "ARJ14": 1.51, "ARJ15": 1.6,
        "CAR01": 53.65, "CAR02": 55.39, "CAR03": 24.32,
        "ALT01": 18.33, "ALT02": 31.62,
        "BUL01": 43.97, "BUL03": 48.82,
        "ERI01": 28.72, "ERI02": 28.04, "ERI03": 29.13, "ERI04": 28.44,
        "ERI30": 137.42, "ERI31": 68.22, "ERI32": 67.36, "ERI40": 137.56, "ERI41": 67.73,
        "ERI42": 67.56, "ERI50": 137.46, "ERI51": 67.68, "ERI52": 67.46,
        "SUR10": 122.84, "SUR11": 58.31, "SUR12": 58.3, "SUR20": 122.44, "SUR21": 58.44,
        "SUR22": 58.37, "SUR30": 129.05, "SUR31": 63.39, "SUR32": 63.3, "SUR40": 131.5,
        "SUR41": 63.46, "SUR42": 64.36,
        "WAR05": 44.33,
        "WAR10": 128.35, "WAR11": 64.0, "WAR12": 63.73, "WAR20": 127.5, "WAR21": 64.04,
        "WAR22": 62.91, "WAR30": 135.36, "WAR31": 66.74, "WAR32": 67.09, "WAR40": 135.03,
        "WAR41": 65.8, "WAR42": 66.52,
        "MOA02": 1.28, "MOA05": 1.1, "MOA06": 1.12, "MOA07": 1.1, "MOA08": 1.1,
        # ── Bagazo (una unidad equivalente por central) ──
        "GBE01": 21.0, "IAG01": 5.0, "UNA01": 35.0, "AGU01": 4.0, "AGU02": 55.0,
        "AGU03": 52.09, "SBU01": 5.0,
        # ── Hidroeléctricas (54 unidades) ──
        "MIG01": 1.31, "MIG02": 1.24,
        "ANG01": 2.22, "ANG02": 1.27, "ANG03": 2.74,
        "CHO01": 1.91, "CHO02": 2.45, "CHO03": 1.84,
        "CRB": 6.13,
        "ZON": 11.04, "TIQ": 9.72,
        "BOT01": 1.9, "BOT02": 1.47, "BOT03": 3.44,
        "CUT01": 2.5, "CUT02": 2.38, "CUT03": 2.3, "CUT04": 1.49, "CUT05": 14.3,
        "SRO01": 6.9, "SRO02": 10.69,
        "SAI": 10.5,
        "CHU01": 13.18, "CHU02": 12.21,
        "HAR01": 13.53, "HAR02": 12.32,
        "CAH01": 13.653, "CAH02": 14.364,
        "HUA01": 15.1, "HUA02": 15.05,
        "CHJ": 38.4, "YAN": 50.785,
        "COR01": 12.91, "COR02": 12.79, "COR03": 13.25, "COR04": 13.31, "COR05": 12.99,
        "SIS01": 17.652, "SIS02": 16.923, "SIS03": 17.159, "SIS04": 17.722, "SIS05": 21.649,
        "SJS01": 27.5, "SJS02": 27.5,
        "SJE01": 34.5, "SJE02": 34.5,
        "KAN": 7.54,
        "QUE01": 0.979, "QUE02": 0.993,
        "SJA01": 3.8, "SJA02": 3.8,
        "MIS01": 40.0, "MIS02": 40.0, "MIS03": 40.0,
        # ── Eólicas (MW de la central ÷ unidades) ──
        **_iguales(["QOL01", "QOL02"], 3),                 # Qollpana I
        **_iguales(_serie("QOL", 3, 10), 24),              # Qollpana II
        **_iguales(_serie("EWA", 1, 4), 14.4),             # Warnes I
        **_iguales(_serie("SJU", 1, 11), 39.6),            # San Julián
        **_iguales(_serie("EDO", 1, 15), 54),              # El Dorado
        # ── Solares fotovoltaicas (MW de la central ÷ unidades) ──
        **_iguales(_serie("ORU", 1, 19), 50.01),           # Oruro Fase 1
        **_iguales(_serie("ORU", 20, 38), 50.01),          # Oruro Fase 2
        **_iguales(["YUN01", "YUN02"], 5),                 # Yunchará
        **_iguales(_serie("UYU", 1, 21), 60.06),           # Uyuni
        "UYU22": 2.5,                                      # Uyuni Fase 2
    },
}
# Hasta cuándo rige la última vigencia cargada (fin del semestre del archivo).
_FIN_ULTIMA = date(2027, 4, 30)


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
    vig = vigencia(dia)
    if vig:
        return EFECTIVA[vig[0]].get(codigo)
    inicios = sorted(EFECTIVA)
    cercana = min(inicios, key=lambda v: abs((v - dia).days) if dia < v else abs((dia - _FIN_ULTIMA).days))
    return EFECTIVA[cercana].get(codigo)
