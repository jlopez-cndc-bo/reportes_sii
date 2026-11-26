"""Esquemas Pydantic para requests/responses de la API.

Estos modelos son el contrato público de la API (ver /docs): además de la UI
React, los consume directamente cualquier script interno que quiera
automatizar la obtención de estos reportes, por eso cada campo documenta su
significado y valores válidos.
"""
from datetime import date, datetime
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
    # Indicador por fila (Total, Máx, Part. %…): no es un período del gráfico.
    resumen: bool = False
    # La fila TOTAL no lo suma (máximos, porcentajes, factores).
    sinTotal: bool = False


class ReportResponse(BaseModel):
    """Forma común de todos los reportes: tabla pivoteada lista para render."""

    table: str = Field(..., description="Identificador interno del shape de la tabla.")
    columns: list[ReportColumn]
    rows: list[dict[str, Any]]
    aviso: str | None = Field(
        None, description="Advertencia no bloqueante (p.ej. datos parciales u omitidos)."
    )
    aviso_total: str | None = Field(
        None, description="Aclaración sobre la fila TOTAL; la UI la muestra sólo con Totales activo."
    )


class TemperaturaRequest(BaseModel):
    """Rango de fechas para la relación entre potencia de punta y temperatura."""

    fecha_inicio: datetime = Field(..., examples=["2026-11-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-11-30T00:00:00"])


class PotenciaTemperaturaRequest(BaseModel):
    """Potencia efectiva de las térmicas a la temperatura horaria de su zona."""

    fecha_inicio: datetime = Field(..., examples=["2026-11-20T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-11-20T00:00:00"])
    nivel: str = Field("zona", description="'unidad' | 'zona'.")
    smec: bool = Field(False, description="Comparar con lo medido por el medidor propio de cada unidad en SMEC.")


class IndicesRequest(BaseModel):
    """Índices de desempeño (FOR, EFOR, EFORd) de los generadores elegidos."""

    fecha_inicio: datetime = Field(..., examples=["2026-01-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-10-31T00:00:00"])
    unidades: list[int] = Field(..., min_length=1, description="IDs de generador.")


class TemperaturaConsultaRequest(BaseModel):
    """Consulta de temperaturas por zona térmica."""

    fecha_inicio: datetime = Field(..., examples=["2026-11-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-11-30T00:00:00"])
    zonas: list[str] = Field(default_factory=list, description="id_universal de zona (ZTGCH01…); vacío = todas.")


class HorasDisponibilidadRequest(BaseModel):
    """Disponibilidad por componente o por central, en el rango dado."""

    fecha_inicio: datetime = Field(..., examples=["2026-06-01T00:00:00"])
    fecha_fin: datetime = Field(..., examples=["2026-06-30T23:59:59"])
    unidades: list[int] = Field(default_factory=list, description="IDs de componente; vacío = todos.")
    ip: bool = Field(True, description="Incluir indisponibilidad Programada (155).")
    inf: bool = Field(True, description="Incluir indisponibilidad Forzada (156).")
    nivel: str = Field(
        "componente",
        description="'componente' (una fila por componente con eventos) o 'central' "
                    "(% por central ponderado por la potencia efectiva oficial).",
    )


class HorasNoDisponibilidadRequest(BaseModel):
    """Eventos: detalle de eventos por componente."""

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
    """Horas por tipo de operación, agregadas o desglosadas por tipo."""

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
            "'energia_anio', 'factor_dia', 'factor_periodo', 'capacidad_sistema', "
            "'mix_tecnologia', 'pico_sin', 'generacion_demanda', 'conciliacion', 'potencia_limitada'."
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
    comparar: str = Field(
        "ninguno",
        description=(
            "Sólo energia_*: agrega 'Total ant.' y 'Var. %' contra el mismo período "
            "desplazado. 'ninguno' | 'semana' (7 días antes; sólo energia_dia) | "
            "'anio' (un año antes)."
        ),
    )
    porcentaje: bool = Field(
        False, description="Sólo pico_sin: aporte de cada central en % del total del SIN.")


# ─────────────────────────────── SISFALLA ───────────────────────────────

class SeguimientoInformesRequest(BaseModel):
    """Plazos y estado de seguimiento de informes, por falla y agente."""

    cod_falla: CodFalla = Field(None, description="Falla puntual: 'nro/gestión' (ej. 247/2026) o código interno PK_COD_FALLA.")
    agente: str | None = Field(None, description="Texto libre, busca por sigla o nombre del agente.")
    agente_exacto: bool = Field(
        False, description="true = `agente` es una sigla (combo de la UI) y se filtra por igualdad exacta; false = búsqueda por texto.",
    )
    desde: datetime | None = Field(None, description="Filtra por PLAZO >= desde.")
    hasta: datetime | None = Field(None, description="Filtra por PLAZO <= hasta (día completo, inclusive).")
    limite: int = Field(500, ge=1, le=2000, description="Tope de filas (máx. 2000).")


class DetalleInformesRequest(BaseModel):
    """Operaciones registradas sobre informes, por falla/agente/usuario."""

    cod_falla: CodFalla = Field(None, description="Falla puntual: 'nro/gestión' (ej. 247/2026) o código interno PK_COD_FALLA.")
    agente: str | None = Field(None, description="Texto libre, busca por sigla del agente.")
    agente_exacto: bool = Field(
        False, description="true = `agente` es una sigla (combo de la UI) y se filtra por igualdad exacta; false = búsqueda por texto.",
    )
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
    agente_exacto: bool = Field(
        False, description="true = `agente` es una sigla (combo de la UI) y se filtra por igualdad exacta; false = búsqueda por texto.",
    )
    desde: datetime | None = Field(None, description="Filtra por fecha de apertura >= desde.")
    hasta: datetime | None = Field(None, description="Filtra por fecha de apertura <= hasta (día completo, inclusive).")


class EdacRequest(BaseModel):
    """Componentes con parámetros EDAC configurados por agente."""

    agente: str | None = Field(None, description="Texto libre, busca por sigla o nombre del propietario.")
    agente_exacto: bool = Field(
        False, description="true = `agente` es una sigla (combo de la UI) y se filtra por igualdad exacta; false = búsqueda por texto.",
    )
    desde: datetime | None = Field(None, description="Filtra por fecha de inicio de vigencia >= desde.")
    hasta: datetime | None = Field(None, description="Filtra por fecha de inicio de vigencia <= hasta (día completo, inclusive).")


class SisfallaExportRequest(BaseModel):
    """Filtros para exportar cualquier reporte SISFALLA a Excel (POST /api/sisfalla/exportar/{id}).

    Cada reporte usa sólo los campos que le aplican (ver su endpoint JSON
    equivalente en /api/sisfalla/reportes/{id}) e ignora el resto."""

    cod_falla: CodFalla = None
    agente: str | None = None
    agente_exacto: bool = False
    desde: datetime | None = None
    hasta: datetime | None = None
    gestion: int | None = None
    limite: int = Field(500, ge=1, le=2000)


class HfdRegistrosRequest(BaseModel):
    """SCADA HFD: registros crudos por día (96 intervalos de 15 min por medida)."""

    archivo: str = Field(..., description="generadores | transferencias | tensiones | embalses | taps")
    magnitud: str = Field(..., description="Valor de `type` en el HFD: P, Q, U, COTA_EMB, TAP…")
    desde: date
    hasta: date
    estacion: str | None = Field(None, description="Coincidencia parcial con la estación (b1).")


class HfdConsolidadoRequest(BaseModel):
    """SCADA HFD consolidados: `fecha` para los de 15 min; `desde`/`hasta` para energía."""

    fecha: date | None = None
    desde: date | None = None
    hasta: date | None = None


class HfdLoginRequest(BaseModel):
    """Login de editores de correcciones HFD (usuario del dominio CNDC)."""

    usuario: str = Field(..., max_length=64)
    password: str = Field(..., max_length=256)


class HfdCambio(BaseModel):
    intervalo: int = Field(..., ge=0, le=95, description="0..95 = 00:00..23:45")
    valor: float | None = Field(None, description="MW; null anula la corrección vigente")
    fuente: str = Field("MANUAL", description="SMEC | MANUAL")


class HfdCorreccionRequest(BaseModel):
    """Correcciones de una señal HFD en un día cerrado."""

    archivo: str = Field("generadores")
    id_obj: int
    el: str = Field(..., description="P | Q")
    fecha: date
    cambios: list[HfdCambio] = Field(..., min_length=1, max_length=96)
    motivo: str = Field(..., max_length=400)
