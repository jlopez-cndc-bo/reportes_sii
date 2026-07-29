"""Utilidades para traducir los filtros de la UI a binds Oracle.

Reproduce la técnica del código original: cada tipo de operación tiene un
bind (:opn, :opl, :ip, :inf, :op, :ore) que vale su ID si está activo, o 0
si no lo está (así el IN(...) no lo incluye).
"""
from dataclasses import dataclass

from .constants import TipoComponente, TipoOperacion


@dataclass
class TiposOperacion:
    """Flags de tipos de operación tal como los expone la UI."""

    op_normal: bool = False      # 152  "Opn"
    pot_limitada: bool = False   # 153  "opl"
    programada: bool = False     # 155  "ip"
    forzada: bool = False        # 156  "inf"
    prueba: bool = False         # 158  "op"
    reprogramacion: bool = False  # 192  "ore"

    def binds(self) -> dict[str, int]:
        return {
            "opn": TipoOperacion.OP_NORMAL if self.op_normal else 0,
            "opl": TipoOperacion.POT_LIMITADA if self.pot_limitada else 0,
            "ip": TipoOperacion.PROGRAMADA if self.programada else 0,
            "inf": TipoOperacion.FORZADA if self.forzada else 0,
            "op": TipoOperacion.PRUEBA if self.prueba else 0,
            "ore": TipoOperacion.REPROGRAMACION if self.reprogramacion else 0,
        }

    def activos(self) -> list[int]:
        return [v for v in self.binds().values() if v != 0]


def componentes_binds(flags: TipoComponente) -> dict[str, str]:
    """Binds de cte_elemento para el filtro de tipos de componente del árbol."""
    def on(bit: TipoComponente, value: str) -> str:
        return value if (flags & bit) else ""

    return {
        "alimenta": on(TipoComponente.ALIMENTA, "ALIMENTA"),
        "autotran": on(TipoComponente.AUTOTRAN, "AUTOTRAN"),
        "cap_serie": on(TipoComponente.CAP_SERIE, "CAP-SERIE"),
        "cap_shunt": on(TipoComponente.CAP_SHUNT, "CAP-SHUNT"),
        "generador": on(TipoComponente.GENERADOR, "GENERADOR"),
        "linea": on(TipoComponente.LINEA, "LINEA"),
        "reactor": on(TipoComponente.REACTOR, "REACTOR"),
        "transfor": on(TipoComponente.TRANSFOR, "TRANSFOR"),
    }
