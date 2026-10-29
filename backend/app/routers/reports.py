"""Endpoints REST del módulo de indisponibilidades."""
from fastapi import APIRouter, HTTPException

from ..constants import Resolucion, TipoComponente
from ..filters import TiposOperacion
from ..reports import (
    horas_disponibilidad,
    horas_no_disponibilidad,
    horas_tipo_operacion,
    potencias_disponibles,
    potencias_indisponibles,
    programacion,
)
from ..schemas import (
    HorasDisponibilidadRequest,
    HorasNoDisponibilidadRequest,
    HorasTipoOperacionRequest,
    PotenciasDisponiblesRequest,
    PotenciasIndisponiblesRequest,
    ProgramacionRequest,
    ReportResponse,
    TiposOperacionFlags,
    TreeRequest,
)
from ..tree import get_tree

router = APIRouter(prefix="/api", tags=["indisponibilidades"])

# Tope de días para reportes de detalle/agregado por componente (horas-disponibilidad,
# horas-no-disponibilidad). La consulta no pivotea por día — una fila por evento o por
# componente — así que el volumen crece con la cantidad de eventos, no con el rango en
# días. Se deja un tope generoso sólo como red de seguridad ante selecciones de muchas
# unidades a la vez.
MAX_DIAS_EVENTOS = 3650

# Tope de días para horas-tipo-operacion con periodo="dia": ese reporte pivotea una
# columna por día (y por tipo de operación en modo desagregado), así que el número de
# columnas sí crece linealmente con el rango — aquí el límite evita tablas de miles de
# columnas.
MAX_DIAS_DIARIO = 750


def _validar(f1, f2, max_dias: int | None = None) -> None:
    if f2 < f1:
        raise HTTPException(
            status_code=400,
            detail="La fecha final no puede ser anterior a la inicial.",
        )
    if max_dias is not None:
        dias = (f2.date() - f1.date()).days + 1
        if dias > max_dias:
            raise HTTPException(
                status_code=400,
                detail=f"El rango ({dias} días) supera el máximo de {max_dias} "
                f"días para este reporte. Reduzca el período.",
            )


def _tipos(flags: TiposOperacionFlags) -> TiposOperacion:
    return TiposOperacion(
        op_normal=flags.op_normal,
        pot_limitada=flags.pot_limitada,
        programada=flags.programada,
        forzada=flags.forzada,
        prueba=flags.prueba,
        reprogramacion=flags.reprogramacion,
    )


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/arbol")
def arbol(req: TreeRequest):
    _validar(req.fecha_inicio, req.fecha_fin)
    return _guard(
        get_tree,
        req.fecha_inicio,
        req.fecha_fin,
        _tipos(req.tipos_operacion),
        TipoComponente(req.componentes),
        req.modo,
    )


@router.post("/reportes/potencias-disponibles", response_model=ReportResponse)
def rpt_potencias_disponibles(req: PotenciasDisponiblesRequest):
    _validar(req.fecha_inicio, req.fecha_fin)
    return _guard(
        potencias_disponibles.report,
        req.nivel, req.fecha_inicio, req.fecha_fin, req.unidades,
    )


@router.post("/reportes/potencias-indisponibles", response_model=ReportResponse)
def rpt_potencias_indisponibles(req: PotenciasIndisponiblesRequest):
    _validar(req.fecha_inicio, req.fecha_fin)
    if req.resolucion == "hora":
        tipo = Resolucion.HORA
        intervalo = req.horas * 60
    else:
        tipo = Resolucion.INTERVALO
        intervalo = req.intervalo_minutos
    return _guard(
        potencias_indisponibles.report,
        req.fecha_inicio, req.fecha_fin, tipo, intervalo, req.unidades,
        req.ip, req.inf,
    )


@router.post("/reportes/horas-disponibilidad", response_model=ReportResponse)
def rpt_horas_disponibilidad(req: HorasDisponibilidadRequest):
    _validar(req.fecha_inicio, req.fecha_fin, MAX_DIAS_EVENTOS)
    return _guard(
        horas_disponibilidad.report,
        req.fecha_inicio, req.fecha_fin, req.unidades, req.ip, req.inf,
    )


@router.post("/reportes/horas-no-disponibilidad", response_model=ReportResponse)
def rpt_horas_no_disponibilidad(req: HorasNoDisponibilidadRequest):
    _validar(req.fecha_inicio, req.fecha_fin, MAX_DIAS_EVENTOS)
    return _guard(
        horas_no_disponibilidad.report,
        req.fecha_inicio, req.fecha_fin, req.unidades,
        req.ip, req.inf, req.opn, req.plim, req.agregado,
    )


def _validar_tipo_prog(tipo: str) -> None:
    if tipo not in programacion.TIPO_PROG:
        raise HTTPException(status_code=400,
                            detail=f"Tipo de programación inválido: {tipo}")


@router.post("/reportes/programacion-mantenimiento", response_model=ReportResponse)
def rpt_programacion(req: ProgramacionRequest):
    _validar_tipo_prog(req.tipo)
    return _guard(programacion.programacion, req.fecha, req.tipo)


@router.post("/reportes/comparacion-programada", response_model=ReportResponse)
def rpt_comparacion(req: ProgramacionRequest):
    _validar_tipo_prog(req.tipo)
    return _guard(programacion.comparacion, req.fecha, req.tipo)


@router.post("/reportes/horas-tipo-operacion", response_model=ReportResponse)
def rpt_horas_tipo_operacion(req: HorasTipoOperacionRequest):
    # Sólo el desglose diario necesita tope; mes/año generan pocas columnas.
    _validar(req.fecha_inicio, req.fecha_fin,
             MAX_DIAS_DIARIO if req.periodo == "dia" else None)
    return _guard(
        horas_tipo_operacion.report,
        req.periodo, req.modo, req.fecha_inicio, req.fecha_fin,
        req.unidades, _tipos(req.tipos_operacion),
    )
