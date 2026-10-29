"""Endpoints REST del módulo SISFALLA (reportes de fallas del sistema eléctrico).

Los 15 reportes tabulares del catálogo original (ver dossier de migración
2026-10-08) están portados. `agente-contactos` y `notificacion-falla` quedan
excluidos por decisión del usuario (datos de contacto personal, no
operativos); `informe-falla` (informe PDF puntual) queda fuera de alcance.
"""
from datetime import datetime
from typing import Callable
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..export_excel import build_workbook
from ..schemas import (
    DetalleInformesRequest,
    DetalleSupervisorRequest,
    EdacRequest,
    FallaFiltroRequest,
    ReportResponse,
    ResumenAgentesRequest,
    SeguimientoInformesRequest,
    SisfallaExportRequest,
)
from ..sisfalla import reportes as R

router = APIRouter(prefix="/api/sisfalla", tags=["sisfalla"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post(
    "/reportes/seguimiento-informes",
    response_model=ReportResponse,
    summary="Seguimiento de informes",
)
def rpt_seguimiento_informes(req: SeguimientoInformesRequest):
    return _guard(
        R.seguimiento_informes,
        req.cod_falla, req.agente, req.desde, req.hasta, req.limite,
    )


@router.get(
    "/fallas/buscar",
    summary="Buscar fallas por código o descripción (para un selector)",
    description="`q` vacío trae las más recientes. Código exacto si `q` tiene formato "
                "'nro/gestión' o 'nro-gestión'; si no, coincidencia parcial en código o descripción.",
)
def rpt_buscar_fallas(q: str | None = None, limite: int = 30):
    return _guard(R.buscar_fallas, q, max(1, min(limite, 100)))


@router.post(
    "/reportes/detalle-informes",
    response_model=ReportResponse,
    summary="Detalle de informes creados",
    description="Sin columna de usuario que operó: ese dato de auditoría sólo existe con sesión CNDC en el sistema origen.",
)
def rpt_detalle_informes(req: DetalleInformesRequest):
    return _guard(
        R.detalle_informes,
        req.cod_falla, req.agente, req.desde, req.hasta, req.gestion, req.limite,
    )


@router.post(
    "/reportes/detalle-supervisor",
    response_model=ReportResponse,
    summary="Detalle por supervisor/operador",
)
def rpt_detalle_supervisor(req: DetalleSupervisorRequest):
    return _guard(R.detalle_supervisor, req.desde, req.hasta)


@router.get(
    "/reportes/agentes",
    response_model=ReportResponse,
    summary="Catálogo de agentes del SIN",
    description="Todos los agentes registrados, tengan o no contacto de correo configurado.",
)
def rpt_agentes():
    return _guard(R.agentes)


@router.post(
    "/reportes/resumen-agentes",
    response_model=ReportResponse,
    summary="Resumen de fallas por agente",
    description="Cantidad de fallas con informe registrado por cada agente, incluidos los que no tuvieron ninguna en el rango.",
)
def rpt_resumen_agentes(req: ResumenAgentesRequest):
    return _guard(R.resumen_agentes, req.desde, req.hasta)


@router.post(
    "/reportes/componentes-comprometidos",
    response_model=ReportResponse,
    summary="Componentes comprometidos (CNDC)",
)
def rpt_componentes_comprometidos(req: FallaFiltroRequest):
    return _guard(R.componentes_comprometidos, req.cod_falla, req.agente, req.desde, req.hasta)


@router.post(
    "/reportes/elementos-comprometidos",
    response_model=ReportResponse,
    summary="Elementos comprometidos (CNDC)",
)
def rpt_elementos_comprometidos(req: FallaFiltroRequest):
    return _guard(R.elementos_comprometidos, req.cod_falla, req.agente, req.desde, req.hasta)


@router.post(
    "/reportes/falla-alimentadores",
    response_model=ReportResponse,
    summary="Fallas de alimentadores (CNDC)",
)
def rpt_falla_alimentadores(req: FallaFiltroRequest):
    return _guard(R.falla_alimentadores, req.cod_falla, req.agente, req.desde, req.hasta)


@router.post(
    "/reportes/det-interruptores",
    response_model=ReportResponse,
    summary="Detalle de interruptores (CNDC)",
)
def rpt_det_interruptores(req: FallaFiltroRequest):
    return _guard(R.det_interruptores, req.cod_falla, req.agente, req.desde, req.hasta)


@router.post(
    "/reportes/reles-operados",
    response_model=ReportResponse,
    summary="Relés operados (CNDC)",
)
def rpt_reles_operados(req: FallaFiltroRequest):
    return _guard(R.reles_operados, req.cod_falla, req.agente, req.desde, req.hasta)


@router.post(
    "/reportes/edac",
    response_model=ReportResponse,
    summary="Consulta EDAC (solo lectura)",
)
def rpt_edac(req: EdacRequest):
    return _guard(R.edac, req.agente, req.desde, req.hasta)


@router.post(
    "/reportes/detalle-desconexiones",
    response_model=ReportResponse,
    summary="Detalle de desconexiones (CNDC)",
    description="Sólo líneas, autotransformadores y transformadores de empresas transmisoras.",
)
def rpt_detalle_desconexiones(req: FallaFiltroRequest):
    return _guard(R.detalle_desconexiones, req.cod_falla, req.agente, req.desde, req.hasta)


@router.get(
    "/reportes/edac-analisis",
    response_model=ReportResponse,
    summary="EDAC para análisis",
    description="Configuración EDAC vigente (fecha más reciente disponible), agrupada por categoría y etapa.",
)
def rpt_edac_analisis():
    return _guard(R.edac_analisis)


@router.post(
    "/reportes/operacion-edac",
    response_model=ReportResponse,
    summary="Operación EDAC",
)
def rpt_operacion_edac(req: FallaFiltroRequest):
    return _guard(R.operacion_edac, req.cod_falla, req.agente, req.desde, req.hasta)


# ─────────────────────────── Exportar a Excel ───────────────────────────
# Un único endpoint dinámico por `id` de reporte (en vez de 15 endpoints casi
# idénticos): cada reporte ignora los campos de `SisfallaExportRequest` que no
# use (todos son opcionales en el schema).

_EXPORTABLES: dict[str, tuple[str, Callable[["SisfallaExportRequest"], dict]]] = {
    "seguimiento-informes": (
        "Seguimiento de Informes",
        lambda r: R.seguimiento_informes(r.cod_falla, r.agente, r.desde, r.hasta, r.limite),
    ),
    "detalle-informes": (
        "Detalle de Informes",
        lambda r: R.detalle_informes(r.cod_falla, r.agente, r.desde, r.hasta, r.gestion, r.limite),
    ),
    "detalle-supervisor": ("Detalle por Supervisor", lambda r: R.detalle_supervisor(r.desde, r.hasta)),
    "agentes": ("Catálogo de Agentes", lambda r: R.agentes()),
    "resumen-agentes": ("Resumen de Fallas por Agente", lambda r: R.resumen_agentes(r.desde, r.hasta)),
    "componentes-comprometidos": (
        "Componentes Comprometidos",
        lambda r: R.componentes_comprometidos(r.cod_falla, r.agente, r.desde, r.hasta),
    ),
    "elementos-comprometidos": (
        "Elementos Comprometidos",
        lambda r: R.elementos_comprometidos(r.cod_falla, r.agente, r.desde, r.hasta),
    ),
    "falla-alimentadores": (
        "Fallas de Alimentadores",
        lambda r: R.falla_alimentadores(r.cod_falla, r.agente, r.desde, r.hasta),
    ),
    "det-interruptores": (
        "Detalle de Interruptores",
        lambda r: R.det_interruptores(r.cod_falla, r.agente, r.desde, r.hasta),
    ),
    "reles-operados": ("Relés Operados", lambda r: R.reles_operados(r.cod_falla, r.agente, r.desde, r.hasta)),
    "edac": ("Consulta EDAC", lambda r: R.edac(r.agente, r.desde, r.hasta)),
    "detalle-desconexiones": (
        "Detalle de Desconexiones",
        lambda r: R.detalle_desconexiones(r.cod_falla, r.agente, r.desde, r.hasta),
    ),
    "edac-analisis": ("EDAC para Análisis", lambda r: R.edac_analisis()),
    "operacion-edac": (
        "Operación EDAC",
        lambda r: R.operacion_edac(r.cod_falla, r.agente, r.desde, r.hasta),
    ),
}


@router.post(
    "/exportar/{id}",
    summary="Cualquier reporte SISFALLA, como archivo .xlsx",
    description="`id` es el mismo identificador usado en /reportes/{id}.",
)
def exportar(id: str, req: SisfallaExportRequest):
    if id not in _EXPORTABLES:
        raise HTTPException(status_code=404, detail=f"Reporte SISFALLA desconocido: {id}")
    label, fn = _EXPORTABLES[id]
    res = _guard(fn, req)

    rango = ""
    if req.desde:
        ini = req.desde.date().isoformat()
        fin = (req.hasta or req.desde).date().isoformat()
        rango = f" — {ini} a {fin}"
    titulo = f"{label}{rango}"
    buf = build_workbook(res, titulo)
    fname = f"Sisfalla_{label.replace(' ', '_')}{rango.replace(' ', '').replace('—', '_')}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    return StreamingResponse(buf, media_type=_XLSX, headers=headers)
