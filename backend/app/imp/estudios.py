"""Estudios de mediano plazo: carpetas AAAA-MM bajo IMP_DATA_DIR."""
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..config import get_settings

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_ID = re.compile(r"^(\d{4})-(05|11)$")
ANIOS = 4  # el mediano plazo cubre siempre 4 años eléctricos


@dataclass(frozen=True)
class Estudio:
    id: str
    carpeta: Path

    @property
    def inicio(self) -> date:
        a, m = self.id.split("-")
        return date(int(a), int(m), 1)

    @property
    def fin(self) -> date:
        """Último mes del periodo (día 1)."""
        i = self.inicio
        meses = i.year * 12 + i.month - 1 + ANIOS * 12 - 1
        return date(meses // 12, meses % 12 + 1, 1)

    @property
    def periodo(self) -> str:
        """«nov/26 - oct/30», como en el encabezado de los anexos."""
        f = lambda d: f"{MESES[d.month - 1]}/{d.year % 100:02d}"
        return f"{f(self.inicio)} - {f(self.fin)}"


def raiz() -> Path:
    r = get_settings().imp_data_dir
    if not r:
        raise LookupError("IMP_DATA_DIR no está configurado en el servidor.")
    return Path(r)


def listar(base: Path | None = None) -> list[Estudio]:
    """Estudios disponibles, el más reciente primero."""
    base = base or raiz()
    if not base.is_dir():
        return []
    return sorted((Estudio(p.name, p) for p in base.iterdir() if p.is_dir() and _ID.match(p.name)),
                  key=lambda e: e.id, reverse=True)


def obtener(id_: str, base: Path | None = None) -> tuple[Estudio, list[Estudio]]:
    """El estudio pedido y los anteriores (más reciente primero). id validado: nada de rutas libres."""
    if not _ID.match(id_ or ""):
        raise ValueError(f"Estudio inválido: «{id_}». Formato AAAA-MM con mes 05 u 11.")
    todos = listar(base)
    for i, e in enumerate(todos):
        if e.id == id_:
            return e, todos[i + 1:]
    raise LookupError(f"No existe la carpeta del estudio {id_}.")
