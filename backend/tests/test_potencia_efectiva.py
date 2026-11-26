"""La tabla de potencia efectiva cuadra con los totales del archivo semestral."""
from datetime import date

from app.potencia_efectiva import CENTRAL, EFECTIVA, efectiva

T = EFECTIVA[date(2026, 11, 1)]


def _suma(codigos):
    return round(sum(T[c] for c in codigos), 2)


def test_totales_por_tecnologia_igual_al_archivo():
    hidro = [c for c, cen in CENTRAL.items() if cen in {
        "Miguilla", "Angostura", "Choquetanga", "Carabuco", "Zongo", "Tiquimani", "Botijlaca",
        "Cuticucho", "Santa Rosa LH", "Santa Rosa HH", "Sainani", "Chururaqui", "Harca", "Cahua",
        "Huaji", "Chojlla", "Yanacachi", "Corani", "Santa Isabel", "San José I", "San José II",
        "Kanata", "Quehata", "San Jacinto", "Misicuni"}]
    assert len(hidro) == 54
    assert abs(_suma(hidro) - 715.81) < 0.01
    eolicas = [c for c, cen in CENTRAL.items() if cen in {"Qollpana I", "Qollpana II", "Warnes I", "San Julián", "El Dorado"}]
    assert len(eolicas) == 40 and abs(_suma(eolicas) - 135) < 0.01
    solares = [c for c, cen in CENTRAL.items() if cen.startswith("Solar")]
    assert len(solares) == 62 and abs(_suma(solares) - 167.58) < 0.01
    bagazo = ["GBE01", "IAG01", "UNA01", "AGU01", "AGU02", "AGU03", "SBU01"]
    assert abs(_suma(bagazo) - 177.09) < 0.01


def test_toda_unidad_con_central_tiene_potencia():
    assert set(CENTRAL) <= set(T)


def test_vigencia():
    assert efectiva("COR01", date(2026, 11, 15)) == 12.91
    assert efectiva("COR01", date(2026, 10, 31)) == EFECTIVA[date(2026, 5, 1)]["COR01"]
    assert efectiva("COR01", date(2020, 10, 31)) is None
    assert efectiva("COR01", date(2027, 5, 1)) is None


def test_revisiones_rigen_desde_su_fecha():
    # Nov20–Abr21: la primera revisión (19/02/2021) rige desde el inicio del semestre.
    assert min(EFECTIVA) == date(2020, 11, 1)
    assert date(2021, 3, 17) in EFECTIVA
    # Nov25–Abr26 dice «Vigente desde 01/12/2025»: noviembre 2025 sigue con May–Oct25.
    assert efectiva("COR01", date(2025, 11, 15)) == EFECTIVA[date(2025, 5, 1)]["COR01"]


def test_ciclos_combinados_suman_el_total_de_la_central():
    for central, total in [("Entre Ríos", 526.77), ("Termoeléctrica del Sur", 505.83),
                           ("Central Warnes", 570.57)]:
        assert _suma([c for c, cen in CENTRAL.items() if cen == central]) == total


def test_estados_de_bloque_identifican_su_central():
    from app.potencia_efectiva import central_de
    assert central_de("ERI31") == "Entre Ríos" and "ERI31" not in CENTRAL
    assert central_de("WAR42") == "Central Warnes"
    assert central_de("SUR21") == "Termoeléctrica del Sur"
    assert central_de("LIN-X") is None


def test_proxima_fuera_de_rango_usa_la_vigencia_mas_cercana():
    from app.potencia_efectiva import efectiva_proxima, vigencia_proxima
    ultima, primera = max(EFECTIVA), min(EFECTIVA)
    despues, antes = date(2027, 6, 1), date(2019, 1, 1)
    assert vigencia_proxima(despues)[0] == ultima and vigencia_proxima(despues)[2] is False
    assert efectiva_proxima("COR01", despues) == EFECTIVA[ultima]["COR01"]
    assert vigencia_proxima(antes)[0] == primera
    assert efectiva_proxima("COR01", antes) == EFECTIVA[primera]["COR01"]
    assert vigencia_proxima(date(2026, 11, 15)) == (date(2026, 11, 1), date(2027, 4, 30), True)
