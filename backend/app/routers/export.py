"""Endpoints de exportación a Excel (.xlsx) server-side."""
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..constants import Resolucion
from ..export_excel import build_workbook
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
)
from .reports import (MAX_DIAS_DIARIO, MAX_DIAS_EVENTOS, _guard, _tipos,
                      _validar, _validar_tipo_prog)

router = APIRouter(prefix="/api/exportar", tags=["export"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(result: dict, label: str, f1, f2) -> StreamingResponse:
    ini, fin = f1.date().isoformat(), f2.date().isoformat()
    titulo = f"{label} — {ini} a {fin}"
    buf = build_workbook(result, titulo)
    fname = f"{label.replace(' ', '_')}_{ini}_{fin}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"
    }
    return StreamingResponse(buf, media_type=_XLSX, headers=headers)


@router.post(
    "/potencias-disponibles",
    summary="Reporte 1 (Potencias Disponibles), como archivo .xlsx",
)
def exp_potencias_disponibles(req: PotenciasDisponiblesRequest):
    _validar(req.fecha_inicio, req.fecha_fin)
    res = _guard(potencias_disponibles.report, req.nivel,
                 req.fecha_inicio, req.fecha_fin, req.unidades)
    return _xlsx_response(res, "Potencias Disponibles", req.fecha_inicio, req.fecha_fin)


@router.post(
    "/potencias-indisponibles",
    summary="Reporte 2 (Potencias Indisponibles), como archivo .xlsx",
)
def exp_potencias_indisponibles(req: PotenciasIndisponiblesRequest):
    _validar(req.fecha_inicio, req.fecha_fin)
    if req.resolucion == "hora":
        tipo, intervalo = Resolucion.HORA, req.horas * 60
    else:
        tipo, intervalo = Resolucion.INTERVALO, req.intervalo_minutos
    res = _guard(potencias_indisponibles.report, req.fecha_inicio, req.fecha_fin,
                 tipo, intervalo, req.unidades, req.ip, req.inf)
    return _xlsx_response(res, "Potencias Indisponibles", req.fecha_inicio, req.fecha_fin)


@router.post(
    "/horas-disponibilidad",
    summary="Reporte 3 (Horas de Disponibilidad), como archivo .xlsx",
)
def exp_horas_disponibilidad(req: HorasDisponibilidadRequest):
    _validar(req.fecha_inicio, req.fecha_fin, MAX_DIAS_EVENTOS)
    res = _guard(horas_disponibilidad.report, req.fecha_inicio, req.fecha_fin,
                 req.unidades, req.ip, req.inf)
    return _xlsx_response(res, "Horas de Disponibilidad", req.fecha_inicio, req.fecha_fin)


@router.post(
    "/horas-no-disponibilidad",
    summary="Reporte 4 (Horas de No Disponibilidad), como archivo .xlsx",
)
def exp_horas_no_disponibilidad(req: HorasNoDisponibilidadRequest):
    _validar(req.fecha_inicio, req.fecha_fin, MAX_DIAS_EVENTOS)
    res = _guard(horas_no_disponibilidad.report, req.fecha_inicio, req.fecha_fin,
                 req.unidades, req.ip, req.inf, req.opn, req.plim, req.agregado)
    return _xlsx_response(res, "Horas de No Disponibilidad", req.fecha_inicio, req.fecha_fin)


@router.post("/programacion-mantenimiento")
def exp_programacion(req: ProgramacionRequest):
    _validar_tipo_prog(req.tipo)
    res = _guard(programacion.programacion, req.fecha, req.tipo)
    return _xlsx_response(res, "Programación de Mantenimiento", req.fecha, req.fecha)


@router.post("/comparacion-programada")
def exp_comparacion(req: ProgramacionRequest):
    _validar_tipo_prog(req.tipo)
    res = _guard(programacion.comparacion, req.fecha, req.tipo)
    return _xlsx_response(res, "Comparación Programado vs Real", req.fecha, req.fecha)


@router.post(
    "/horas-tipo-operacion",
    summary="Reporte 5 (Horas por Tipo de Operación), como archivo .xlsx",
)
def exp_horas_tipo_operacion(req: HorasTipoOperacionRequest):
    _validar(req.fecha_inicio, req.fecha_fin,
             MAX_DIAS_DIARIO if req.periodo == "dia" else None)
    res = _guard(horas_tipo_operacion.report, req.periodo, req.modo,
                 req.fecha_inicio, req.fecha_fin, req.unidades,
                 _tipos(req.tipos_operacion))
    return _xlsx_response(res, "Horas por Tipo de Operación", req.fecha_inicio, req.fecha_fin)
