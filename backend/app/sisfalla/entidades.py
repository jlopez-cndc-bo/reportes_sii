"""Resolución en runtime de PKs de empresa por sigla (dossier §3c).

A diferencia de los códigos de dominio (`dominios.py`), estos PKs sólo se
usan como filtro/etiqueta de reportes sobre datos vivos de
`componentes_atributos_source()` — es seguro resolverlos por sigla (clave de
negocio estable) en cada entorno en vez de hardcodear la numeración de
producción de SisFalla original.

**Divergencia confirmada con SisFalla original (2026-10-08):** acá
`F_AC_COMPONENTE_DET` no existe (`ORA-00942`), así que no se puede replicar
el resolver original tal cual. En cambio, `F_AP_PERSONA.SIGLA` sí funciona
bien en este entorno (al contrario del bug que SisFalla documenta para su
propio DESA, donde esa columna devuelve el literal `'SIGLA'`) — se resuelve
directo contra `F_AP_PERSONA`.

Varias siglas tienen más de un PK candidato (duplicados de datos: la misma
empresa con dos registros de persona, uno "vivo" y uno huérfano). Se
desambigua por cuál PK aparece realmente como `PROPIETARIO` de componentes:
confirmado con datos reales que el de más componentes coincide siempre con
el PK que SisFalla documenta como el de producción, salvo ERE/ERESA — que
hoy no tiene ningún componente en este entorno (no afecta resultados:
cualquiera de los dos PK candidatos contribuye 0 filas al filtro).
"""
from dataclasses import dataclass

from ..db import query
from .fuentes import componentes_atributos_source

# Cada tupla: siglas candidatas para la misma empresa, en orden de
# preferencia (confirmadas contra producción real de SisFalla 2026-09-16,
# ver core/entidades_codigos.py de SisFalla_30X64).
_GRUPO_TRANSMISORAS: list[tuple[str, ...]] = [
    ("ENDET", "ENDE TRANSMISIÓN", "ENDE T"),
    ("ISABOL",),
    ("TESA",),
    ("ENDE",),
    ("ERE", "ERESA"),
]

_ORDEN_EDAC_ANALISIS: list[tuple[tuple[str, ...], int]] = [
    (("CRE",), 1),
    (("DELAPAZ",), 2),
    (("ELFEC",), 3),
    (("ENDE DEORURO",), 4),
    (("CESSA",), 5),
    (("SEPSA",), 6),
    (("MSCR", "EMSC"), 7),
    (("CMVINTO", "EMVINTO"), 8),
    (("COBOCE",), 9),
    (("EMIRSA",), 10),
    (("ENDED", "ENDE D"), 11),
    (("SETAR",), 12),
    (("SETARV",), 13),
    (("SETARY",), 14),
]


@dataclass(frozen=True)
class EntidadesResueltas:
    pks_transmisoras: tuple[int, ...]
    orden_edac_por_pk: dict[int, int]


_cache: EntidadesResueltas | None = None


def _todas_las_siglas() -> list[str]:
    siglas: list[str] = []
    for candidatas in _GRUPO_TRANSMISORAS:
        siglas.extend(candidatas)
    for candidatas, _orden in _ORDEN_EDAC_ANALISIS:
        siglas.extend(candidatas)
    return list(dict.fromkeys(siglas))


def _pk_por_sigla_mapa() -> dict[str, list[tuple[int, int]]]:
    """sigla (normalizada a mayúsculas) -> [(pk, n_componentes), ...]."""
    siglas = _todas_las_siglas()
    binds = {f"s{i}": sigla for i, sigla in enumerate(siglas)}
    placeholders = ", ".join(f":{k}" for k in binds)
    rows = query(
        f"""
        SELECT p.SIGLA,
               p.PK_COD_PERSONA,
               (SELECT COUNT(*) FROM {componentes_atributos_source()} fc
                 WHERE fc.PROPIETARIO = p.PK_COD_PERSONA) AS N_COMPONENTES
        FROM F_AP_PERSONA p
        WHERE UPPER(p.SIGLA) IN ({placeholders})
        """,
        binds,
    )
    mapa: dict[str, list[tuple[int, int]]] = {}
    for r in rows:
        mapa.setdefault(r["sigla"].upper(), []).append((int(r["pk_cod_persona"]), int(r["n_componentes"])))
    return mapa


def _primera_pk(candidatas: tuple[str, ...], mapa: dict[str, list[tuple[int, int]]]) -> int | None:
    for sigla in candidatas:
        opciones = mapa.get(sigla.upper())
        if opciones:
            # Más de un PK con la misma sigla (duplicado de datos): se queda
            # con el que realmente tiene componentes a su nombre.
            return max(opciones, key=lambda o: o[1])[0]
    return None


def entidades() -> EntidadesResueltas:
    global _cache
    if _cache is not None:
        return _cache
    mapa = _pk_por_sigla_mapa()
    pks_transmisoras = tuple(
        pk for pk in (_primera_pk(c, mapa) for c in _GRUPO_TRANSMISORAS) if pk is not None
    )
    orden_edac_por_pk = {
        pk: orden
        for candidatas, orden in _ORDEN_EDAC_ANALISIS
        if (pk := _primera_pk(candidatas, mapa)) is not None
    }
    if not pks_transmisoras or not orden_edac_por_pk:
        raise RuntimeError(
            "No se pudieron resolver los PKs de empresa por sigla contra F_AP_PERSONA."
        )
    _cache = EntidadesResueltas(pks_transmisoras=pks_transmisoras, orden_edac_por_pk=orden_edac_por_pk)
    return _cache


def reset_entidades() -> None:
    global _cache
    _cache = None
