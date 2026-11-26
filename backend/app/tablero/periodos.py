"""Periodos del tablero: qué rango cubre cada opción del selector y contra qué se compara.

Todo es puro (sin BD). Los rangos son [desde, hasta) y `hasta` nunca pasa de `ahora`:
el mes en curso termina en este momento, no a fin de mes.
"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

# Bolivia no tiene horario de verano: UTC-4 todo el año. El servidor corre en UTC
# y los datos de Oracle están en hora local.
_BO = timezone(timedelta(hours=-4))

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def ahora() -> datetime:
    """Hora local de Bolivia, sin zona (como las fechas de Oracle)."""
    return datetime.now(_BO).replace(tzinfo=None, microsecond=0)


def mes_txt(d: date) -> str:
    return f"{MESES[d.month - 1]}-{d.year}"


def _mes(d: date, k: int) -> date:
    """Primer día del mes desplazado k meses."""
    m = d.year * 12 + d.month - 1 + k
    return date(m // 12, m % 12 + 1, 1)


def _desplazar(d: datetime, meses: int) -> datetime:
    """Misma fecha y hora `meses` meses antes/después; el día se recorta al largo del mes."""
    base = _mes(d.date(), meses)
    dia = min(d.day, monthrange(base.year, base.month)[1])
    return datetime(base.year, base.month, dia, d.hour, d.minute, d.second)


@dataclass(frozen=True)
class Rango:
    desde: datetime
    hasta: datetime   # excluido
    etiqueta: str

    @property
    def horas(self) -> float:
        return (self.hasta - self.desde).total_seconds() / 3600

    def dias(self) -> int:
        """Días calendario tocados por el rango."""
        ultimo = (self.hasta - timedelta(microseconds=1)).date()
        return (ultimo - self.desde.date()).days + 1


@dataclass(frozen=True)
class Periodo:
    id: str
    rango: Rango
    en_curso: bool                       # el rango llega hasta ahora: cifras preliminares
    comparaciones: list[tuple[str, Rango]]


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def resolver(periodo: str | None, now: datetime) -> Periodo:
    """`ayer` · `mes_en_curso` · `anio` · `AAAA-MM`. Sin valor: último mes completo."""
    hoy = datetime(now.year, now.month, now.day)
    if periodo in (None, "", "ultimo_mes"):
        periodo = _mes(hoy.date(), -1).strftime("%Y-%m")

    if periodo == "ayer":
        d = hoy - timedelta(days=1)
        r = Rango(d, hoy, f"Ayer, {_fmt(d)}")
        comps = [("día anterior", Rango(d - timedelta(days=1), d, _fmt(d - timedelta(days=1)))),
                 ("mismo día del año anterior",
                  Rango(_desplazar(d, -12), _desplazar(d, -12) + timedelta(days=1),
                        _fmt(_desplazar(d, -12))))]
        return Periodo("ayer", r, False, comps)

    if periodo == "mes_en_curso":
        ini = hoy.replace(day=1)
        r = Rango(ini, now, f"{mes_txt(ini)} al {now:%d/%m %H:%M} (preliminar)")
        # Mismo tramo del mes: del 1 al mismo día y hora.
        comps = [(f"mismo tramo de {mes_txt(_mes(ini.date(), -1))}",
                  Rango(_desplazar(ini, -1), _desplazar(now, -1), mes_txt(_mes(ini.date(), -1)))),
                 (f"mismo tramo de {mes_txt(_mes(ini.date(), -12))}",
                  Rango(_desplazar(ini, -12), _desplazar(now, -12), mes_txt(_mes(ini.date(), -12))))]
        return Periodo("mes_en_curso", r, True, comps)

    if periodo == "anio":
        ini = hoy.replace(month=1, day=1)
        r = Rango(ini, now, f"{ini.year} al {now:%d/%m} (preliminar)")
        ant = ini.replace(year=ini.year - 1)
        comps = [(f"mismo tramo de {ant.year}", Rango(ant, _desplazar(now, -12), str(ant.year)))]
        return Periodo("anio", r, True, comps)

    try:
        ini = datetime.strptime(periodo, "%Y-%m")
    except ValueError:
        raise ValueError(f"Periodo no válido: «{periodo}». Use ayer, mes_en_curso, anio o AAAA-MM.")
    fin = datetime.combine(_mes(ini.date(), 1), datetime.min.time())
    if ini > hoy:
        raise ValueError("El periodo no puede ser futuro.")
    en_curso = fin > now
    r = Rango(ini, min(fin, now), mes_txt(ini.date()) + (" (preliminar)" if en_curso else ""))
    comps = []
    for k, nombre in ((-1, "mes anterior"), (-12, "mismo mes del año anterior")):
        a = datetime.combine(_mes(ini.date(), k), datetime.min.time())
        b = _desplazar(r.hasta, k) if en_curso else datetime.combine(_mes(ini.date(), k + 1), datetime.min.time())
        comps.append((f"{nombre} ({mes_txt(a.date())})", Rango(a, b, mes_txt(a.date()))))
    return Periodo(periodo, r, en_curso, comps)


def ultimos_meses(fin: datetime, n: int, now: datetime) -> list[Rango]:
    """Los n meses que terminan en el mes de `fin` (el último puede estar en curso)."""
    ultimo = (fin - timedelta(microseconds=1)).date()
    out = []
    for k in range(n - 1, -1, -1):
        a = _mes(ultimo, -k)
        b = datetime.combine(_mes(a, 1), datetime.min.time())
        out.append(Rango(datetime.combine(a, datetime.min.time()), min(b, now), mes_txt(a)))
    return out


def unir(tramos: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Une tramos solapados o contiguos (un 155 y un 156 a la vez no cuentan doble)."""
    out: list[list[datetime]] = []
    for a, b in sorted(tramos):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def recortar(a: datetime, b: datetime, r: Rango) -> float:
    """Horas del tramo [a, b) dentro del rango."""
    return max((min(b, r.hasta) - max(a, r.desde)).total_seconds() / 3600, 0.0)
