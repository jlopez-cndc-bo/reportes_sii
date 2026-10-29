"""Esquemas Pydantic para requests/responses de la API.

Estos modelos son el contrato público de la API (ver /docs): además de la UI
React, los consume directamente cualquier script interno que quiera
automatizar la obtención de estos reportes, por eso cada campo documenta su
significado y valores válidos.
"""
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from .sisfalla.cod_falla import resolver_cod_falla

CodFalla = Annotated[int | None, BeforeValidator(resolver_cod_falla)]


class TiposOperacionFlags(BaseModel):
    """Tipos de operación de `dc_eventos.id_tipo_operacion` a incluir."""

    op_normal: bool = Field(False, description="152 - Operación Normal (ONO).")
    pot_limitada: bool = Field(False, description="153 - Potencia Limitada (POT LIM).")
    programada: bool = Field(True, description="155 - Indisponibilidad Programada (PROG).")
    forzada: bool = Field(True, description="156 - Indisponibilidad Forzada (FOR).")
    prueba: bool = Field(False, description="158 - Prueba (PRUE).")
    reprogramacion: bool = Field(False, description="192 - Reprogramación / Reenganche (REE).")


class TreeRequest(BaseModel):
    """Árbol de componentes Agente→Central→Unidad para elegir `unidades`."""

    fecha_inicio: datetime = Field(..., description="Inicio del rango a evaluar.", examples=["2026-06-01T00:00:00"])
    fecha_fin: datetime = Field(..., description="Fin del rango a evaluar.", examples=["2026-06-30T23:59:59"])
    tipos_operacion: TiposOperacionFlags = TiposOperacionFlags()
    componentes: int = Field(
        16,
        description=(
            "Bitmask de tipo de componente: ALIMENTA=1, AUTOTRAN=2, "
            "CAP_SERIE=4, CAP_SHUNT=8, GENERADOR=16, LINEA=32, REACTOR=64, "
            "TRANSFOR=128, TODOS=255. Combinable por suma (p.ej. 48 = "
            "GENERADOR+LINEA)."
        ),
    )
    modo: str = Field(
        "eventos",
        description=(
            "'eventos': sólo componentes con eventos en el rango (árbol "
            "acotado). 'todos': todos los componentes del sistema, con "
            "flags `vigente`/`con_eventos` por hoja."
        ),
    )


class TreeNode(BaseModel):
    key: str
    tipo: str
    id_objeto: int | None
    label: str
    children: list["TreeNode"] = []
    vigente: bool | None = Field(
        None, description="Sólo en modo 'todos': vigente en el rango consultado."
    )
    con_eventos: bool | None = Field(
        None, description="Sólo en modo 'todos': registró eventos en el rango."
    )


class ReportColumn(BaseModel):
    key: str
    label: str
    format: str | None = None
    hidden: bool = False


class ReportResponse(BaseModel):
    """Forma común de todos los reportes: tabla pivoteada lista para render."""

    table: str = Field(..., description="Identificador interno del shape de la tabla.")
    columns: list[ReportColumn]
    rows: list[dict[str, Any]]
    aviso: str | None = Field(
        None, description="Advertencia no bloqueante (p.ej. datos parciales u omitidos)."
    )


class PotenciasDisponiblesRequest(BaseModel):
    """Reporte 1: Potencias Disponibles, agregadas por unidad/central/agente."""

    fecha_inicio: datetime = Field(..., examples=["2026-06-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-06-30T23:59:59"])
    unidades: list[int] = Field(
        default_factory=list,
        description="IDs de objeto (unidad generadora) a incluir; vacío = todas.",
    )
    nivel: str = Field(
        "unidad", description="Nivel de agregación: 'unidad' | 'central' | 'agente'."
    )


class PotenciasIndisponiblesRequest(BaseModel):
    """Reporte 2: Potencias Indisponibles, pivoteadas en columnas por intervalo."""

    fecha_inicio: datetime = Field(..., examples=["2026-06-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-06-01T23:59:59"])
    unidades: list[int] = Field(default_factory=list, description="IDs de unidad; vacío = todas.")
    resolucion: str = Field(
        "minuto",
        description="'minuto': columnas de `intervalo_minutos` minutos. 'hora': columnas de `horas` horas.",
    )
    intervalo_minutos: int = Field(15, description="Tamaño del intervalo en minutos (si resolucion='minuto').")
    horas: int = Field(1, description="Horas por columna (si resolucion='hora').")
    ip: bool = Field(True, description="Incluir indisponibilidad Programada (155).")
    inf: bool = Field(True, description="Incluir indisponibilidad Forzada (156).")


class HorasDisponibilidadRequest(BaseModel):
    """Reporte 3: Horas de Disponibilidad por componente, en el rango dado."""

    fecha_inicio: datetime = Field(..., examples=["2026-06-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-06-30T23:59:59"])
    unidades: list[int] = Field(default_factory=list, description="IDs de componente; vacío = todos.")
    ip: bool = Field(True, description="Incluir indisponibilidad Programada (155).")
    inf: bool = Field(True, description="Incluir indisponibilidad Forzada (156).")


class HorasNoDisponibilidadRequest(BaseModel):
    """Reporte 4: Horas de No Disponibilidad (detalle de eventos por componente)."""

    fecha_inicio: datetime = Field(..., examples=["2026-06-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-06-30T23:59:59"])
    unidades: list[int] = Field(default_factory=list, description="IDs de componente; vacío = todos.")
    ip: bool = Field(True, description="Incluir indisponibilidad Programada (155).")
    inf: bool = Field(True, description="Incluir indisponibilidad Forzada (156).")
    opn: bool = Field(False, description="Incluir Operación Normal (152).")
    plim: bool = Field(False, description="Incluir Potencia Limitada (153).")
    agregado: bool = Field(
        False, description="Fusiona eventos consecutivos contiguos del mismo componente."
    )


class HorasTipoOperacionRequest(BaseModel):
    """Reporte 5: Horas por Tipo de Operación, agregadas o desglosadas por tipo."""

    fecha_inicio: datetime = Field(..., examples=["2026-01-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-06-30T23:59:59"])
    unidades: list[int] = Field(default_factory=list, description="IDs de componente; vacío = todos.")
    periodo: str = Field(
        "dia", description="Granularidad de las columnas pivoteadas: 'dia' | 'mes' | 'anio'."
    )
    modo: str = Field(
        "agregado",
        description="'agregado': suma todos los tipos activos. 'desagregado': una columna por tipo.",
    )
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
    """Reporte SMEC único, despachado por `tipo` (ver POST /api/smec/reporte)."""

    tipo: str = Field(
        ...,
        description=(
            "Uno de: 'potencia_15min', 'potencia_hora', 'potencia_max_diario', "
            "'potencia_max_entre_fechas', 'energia_dia', 'energia_mes', "
            "'energia_anio', 'factor_dia', 'factor_periodo'."
        ),
        examples=["potencia_hora"],
    )
    fecha_inicio: datetime = Field(..., examples=["2026-06-01T00:00:00"])
    fecha_fin: datetime | None = Field(
        None, description="Requerido salvo en reportes de un solo día (potencia_*, factor_dia).",
        examples=["2026-06-30T23:59:59"],
    )
    unidades: list[int] = Field(
        default_factory=list, description="IDs de objeto (central) a incluir; vacío = todas."
    )
    direccion: str = Field("iny", description="'iny' (inyección) | 'ret' (retiro).")
    nivel: str = Field(
        "central",
        description=(
            "Nivel de agregación de potencia: 'agente' | 'central' | 'medidor' "
            "(sólo con tipo potencia_15min/potencia_hora) | 'drill' (árbol "
            "Agente→Central→Medidor en una sola respuesta plana, con `_nivel` "
            "0/1/2 por fila; sólo potencia_15min/potencia_hora)."
        ),
    )


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
