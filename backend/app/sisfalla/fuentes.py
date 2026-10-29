"""Fuentes configurables de tablas/vistas (dossier de migración, sección 6).

Las queries de SisFalla no siempre apuntan a la tabla física: según el
entorno pueden pasar por una vista crosswalk (p.ej. QUANTUM.VW_SISFALLA_COMPONENTE).
Son nombres de tabla, nunca binds, así que se validan como identificador SQL
antes de interpolarlos.
"""
import re

from ..config import get_settings
from ..db import query

_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)?$")

_cache_columnas: dict[str, set[str]] = {}


def tiene_columna(tabla: str, columna: str) -> bool:
    """Divergencias de esquema entre entornos (confirmado: `F_GF_REGFALLA`
    no tiene `FK_COD_SUPERVISOR2` en el Oracle que lee ReportesSII, aunque sí
    la tiene el SisFalla original) obligan a no asumir columnas opcionales.
    Cacheado por tabla: `all_tab_columns` no cambia durante la vida del proceso.
    """
    cols = _cache_columnas.get(tabla.upper())
    if cols is None:
        rows = query(
            "SELECT column_name FROM all_tab_columns WHERE table_name = :t",
            {"t": tabla.upper()},
        )
        cols = {r["column_name"].upper() for r in rows}
        _cache_columnas[tabla.upper()] = cols
    return columna.upper() in cols


def _validar(source: str, nombre: str) -> str:
    source = source.strip()
    if not _SQL_IDENTIFIER_RE.fullmatch(source):
        raise ValueError(f"Fuente de {nombre} inválida: {source}")
    return source.upper()


def personas_source() -> str:
    return _validar(get_settings().sisfalla_personas_source, "personas")


def componentes_source() -> str:
    return _validar(get_settings().sisfalla_componentes_source, "componentes")


def componentes_atributos_source() -> str:
    return _validar(get_settings().sisfalla_componentes_atributos_source, "atributos de componentes")


def componentes_sti_source() -> str:
    return _validar(get_settings().sisfalla_componentes_sti_source, "STI de componentes")
