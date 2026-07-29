"""Esquemas Pydantic para requests/responses de la API."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TiposOperacionFlags(BaseModel):
    op_normal: bool = False
    pot_limitada: bool = False
    programada: bool = True
    forzada: bool = True
    prueba: bool = False
    reprogramacion: bool = False


class TreeRequest(BaseModel):
    fecha_inicio: datetime
    fecha_fin: datetime
    tipos_operacion: TiposOperacionFlags = TiposOperacionFlags()
    # Bitmask de TIPOS_COMPONENTES (16 = GENERADOR por defecto).
    componentes: int = 16
    # "eventos": sólo componentes con eventos en el rango (comportamiento
    # original). "todos": todos los del sistema, con flags vigente/con_eventos.
    modo: str = "eventos"


class TreeNode(BaseModel):
    key: str
    tipo: str
    id_objeto: int | None
    label: str
    children: list["TreeNode"] = []
    # Sólo en modo "todos" (en hojas): vigencia del objeto en el rango y si
    # registró eventos.
    vigente: bool | None = None
    con_eventos: bool | None = None


class ReportColumn(BaseModel):
    key: str
    label: str
    format: str | None = None
    hidden: bool = False


class ReportResponse(BaseModel):
    table: str
    columns: list[ReportColumn]
    rows: list[dict[str, Any]]
    aviso: str | None = None


class PotenciasDisponiblesRequest(BaseModel):
    fecha_inicio: datetime
    fecha_fin: datetime
    unidades: list[int] = Field(default_factory=list)
    nivel: str = "unidad"  # unidad | central | agente


class PotenciasIndisponiblesRequest(BaseModel):
    fecha_inicio: datetime
    fecha_fin: datetime
    unidades: list[int] = Field(default_factory=list)
    resolucion: str = "minuto"  # minuto | hora
    intervalo_minutos: int = 15  # minutos (minuto) u horas*60 se calcula abajo
    horas: int = 1              # usado si resolucion == hora
    ip: bool = True
    inf: bool = True


class HorasDisponibilidadRequest(BaseModel):
    fecha_inicio: datetime
    fecha_fin: datetime
    unidades: list[int] = Field(default_factory=list)
    ip: bool = True
    inf: bool = True


class HorasNoDisponibilidadRequest(BaseModel):
    fecha_inicio: datetime
    fecha_fin: datetime
    unidades: list[int] = Field(default_factory=list)
    ip: bool = True
    inf: bool = True
    opn: bool = False
    plim: bool = False
    agregado: bool = False


class HorasTipoOperacionRequest(BaseModel):
    fecha_inicio: datetime
    fecha_fin: datetime
    unidades: list[int] = Field(default_factory=list)
    periodo: str = "dia"        # dia | mes | anio
    modo: str = "agregado"      # agregado | desagregado
    tipos_operacion: TiposOperacionFlags = TiposOperacionFlags(
        op_normal=True, pot_limitada=True, programada=True,
        forzada=True, prueba=True, reprogramacion=True,
    )


class ProgramacionRequest(BaseModel):
    """Programación de mantenimiento / comparación programado vs real."""
    fecha: datetime
    tipo: str = "diario"  # diario | semanal | mensual


TreeNode.model_rebuild()


# ─────────────────────────────── SMEC ───────────────────────────────

class SmecReporteRequest(BaseModel):
    tipo: str  # potencia_15min|potencia_hora|potencia_max_diario|
               # potencia_max_entre_fechas|energia_dia|energia_mes|energia_anio|
               # factor_dia|factor_periodo
    fecha_inicio: datetime
    fecha_fin: datetime | None = None
    unidades: list[int] = Field(default_factory=list)   # ids de central
    direccion: str = "iny"      # iny | ret
    nivel: str = "central"      # agente | central | medidor (solo intervalos)
