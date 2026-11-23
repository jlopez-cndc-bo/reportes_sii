"""Endpoints de exportación a Excel (.xlsx) server-side."""
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..export_excel import build_workbook
from ..reports import (
    horas_no_disponibilidad,
    horas_tipo_operacion,
    programacion,
)
from ..schemas import (
    HorasDisponibilidadRequest,
    HorasNoDisponibilidadRequest,
    HorasTipoOperacionRequest,
    ProgramacionRequest,
)
from .reports import (
    MAX_DIAS_DIARIO,
    MAX_DIAS_EVENTOS,
    _guard,
    _tipos,
    _validar,
    _validar_tipo_prog,
    disponibilidad_fn,
)

router = APIRouter(prefix="/api/exportar", tags=["export"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(result: dict, label: str, f1, f2) -> StreamingResponse:
    ini, fin = f1.date().isoformat(), f2.date().isoformat()
    titulo = f"Reporte de la Operación · {label} — {ini} a {fin}"
    buf = build_workbook(result, titulo)
    fname = f"Operacion_{label.replace(' ', '_')}_{ini}_{fin}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"
    }
    return StreamingResponse(buf, media_type=_XLSX, headers=headers)


@router.post(
    "/horas-disponibilidad",
    summary="Disponibilidad por componente o central, como archivo .xlsx",
)
def exp_horas_disponibilidad(req: HorasDisponibilidadRequest):
    _validar(req.fecha_inicio, req.fecha_fin, MAX_DIAS_EVENTOS)
    res = _guard(disponibilidad_fn(req.nivel), req.fecha_inicio, req.fecha_fin,
                 req.unidades, req.ip, req.inf)
    label = "Disponibilidad por central" if req.nivel == "central" else "Disponibilidad por componente"
    return _xlsx_response(res, label, req.fecha_inicio, req.fecha_fin)


@router.post(
    "/horas-no-disponibilidad",
    summary="Eventos, como archivo .xlsx",
)
def exp_horas_no_disponibilidad(req: HorasNoDisponibilidadRequest):
    _validar(req.fecha_inicio, req.fecha_fin, MAX_DIAS_EVENTOS)
    res = _guard(horas_no_disponibilidad.report, req.fecha_inicio, req.fecha_fin,
                 req.unidades, req.ip, req.inf, req.opn, req.plim, req.agregado)
    return _xlsx_response(res, "Eventos", req.fecha_inicio, req.fecha_fin)


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
    summary="Horas por tipo de operación, como archivo .xlsx",
)
def exp_horas_tipo_operacion(req: HorasTipoOperacionRequest):
    _validar(req.fecha_inicio, req.fecha_fin,
             MAX_DIAS_DIARIO if req.periodo == "dia" else None)
    res = _guard(horas_tipo_operacion.report, req.periodo, req.modo,
                 req.fecha_inicio, req.fecha_fin, req.unidades,
                 _tipos(req.tipos_operacion))
    return _xlsx_response(res, "Horas por tipo de operación", req.fecha_inicio, req.fecha_fin)
