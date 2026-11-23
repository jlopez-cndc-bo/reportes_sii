"""Fuentes configurables de tablas/vistas (dossier de migración, sección 6).

Las queries de SisFalla no siempre apuntan a la tabla física: según el
entorno pueden pasar por una vista crosswalk (p.ej. QUANTUM.VW_SISFALLA_COMPONENTE).
Son nombres de tabla, nunca binds, así que se validan como identificador SQL
antes de interpolarlos.
"""
import re

from ..config import get_settings

_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)?$")



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
