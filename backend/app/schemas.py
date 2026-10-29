"""Esquemas Pydantic para requests/responses de la API."""
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from .sisfalla.cod_falla import resolver_cod_falla

CodFalla = Annotated[int | None, BeforeValidator(resolver_cod_falla)]


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


# ─────────────────────────────── SISFALLA ───────────────────────────────

class SeguimientoInformesRequest(BaseModel):
    """Plazos y estado de seguimiento de informes, por falla y agente."""

    cod_falla: CodFalla = Field(None, description="Falla puntual: 'nro/gestión' (ej. 247/2026) o código interno PK_COD_FALLA.")
    agente: str | None = Field(None, description="Texto libre, busca por sigla o nombre del agente.")
    desde: datetime | None = Field(None, description="Filtra por PLAZO >= desde.")
    hasta: datetime | None = Field(None, description="Filtra por PLAZO <= hasta (día completo, inclusive).")
    limite: int = Field(500, ge=1, le=2000, description="Tope de filas (máx. 2000).")


class DetalleInformesRequest(BaseModel):
    """Operaciones registradas sobre informes, por falla/agente/usuario."""

    cod_falla: CodFalla = Field(None, description="Falla puntual: 'nro/gestión' (ej. 247/2026) o código interno PK_COD_FALLA.")
    agente: str | None = Field(None, description="Texto libre, busca por sigla del agente.")
    desde: datetime | None = Field(None, description="Filtra por fecha de transacción >= desde.")
    hasta: datetime | None = Field(None, description="Filtra por fecha de transacción <= hasta (día completo, inclusive).")
    gestion: int | None = Field(
        None,
        description="Año (p.ej. 2026 o 26); sólo se aplica si no se da `cod_falla`, y reemplaza desde/hasta.",
    )
    limite: int = Field(500, ge=1, le=2000, description="Tope de filas (máx. 2000).")


class DetalleSupervisorRequest(BaseModel):
    """Fallas con supervisor y operador asignados."""

    desde: datetime | None = Field(None, description="Filtra por FEC_INICIO >= desde (truncado a día).")
    hasta: datetime | None = Field(None, description="Filtra por FEC_INICIO <= hasta (truncado a día, inclusive).")


class ResumenAgentesRequest(BaseModel):
    """Cantidad de fallas con informe registrado por cada agente del SIN."""

    desde: datetime | None = Field(None, description="Filtra por FEC_INICIO >= desde (truncado a día).")
    hasta: datetime | None = Field(None, description="Filtra por FEC_INICIO <= hasta (truncado a día, inclusive).")


class FallaFiltroRequest(BaseModel):
    """Filtro común a los reportes de detalle de falla del CNDC (componentes/
    elementos comprometidos, alimentadores, interruptores, relés operados).
    Todos se acotan a fallas cuyo informe FINAL o RECTIFICATORIO del CNDC ya
    fue emitido — un rango sin fallas en ese estado devuelve 0 filas aunque
    el filtro funcione."""

    cod_falla: CodFalla = Field(None, description="Falla puntual: 'nro/gestión' (ej. 247/2026) o código interno PK_COD_FALLA.")
    agente: str | None = Field(None, description="Texto libre, busca por sigla o nombre del propietario del componente.")
    desde: datetime | None = Field(None, description="Filtra por fecha de apertura >= desde.")
    hasta: datetime | None = Field(None, description="Filtra por fecha de apertura <= hasta (día completo, inclusive).")


class EdacRequest(BaseModel):
    """Componentes con parámetros EDAC configurados por agente."""

    agente: str | None = Field(None, description="Texto libre, busca por sigla o nombre del propietario.")
    desde: datetime | None = Field(None, description="Filtra por fecha de inicio de vigencia >= desde.")
    hasta: datetime | None = Field(None, description="Filtra por fecha de inicio de vigencia <= hasta (día completo, inclusive).")


class SisfallaExportRequest(BaseModel):
    """Filtros para exportar cualquier reporte SISFALLA a Excel (POST /api/sisfalla/exportar/{id}).

    Cada reporte usa sólo los campos que le aplican (ver su endpoint JSON
    equivalente en /api/sisfalla/reportes/{id}) e ignora el resto."""

    cod_falla: CodFalla = None
    agente: str | None = None
    desde: datetime | None = None
    hasta: datetime | None = None
    gestion: int | None = None
    limite: int = Field(500, ge=1, le=2000)
