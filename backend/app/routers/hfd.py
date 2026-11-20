"""Endpoints REST del módulo SCADA HFD (registros crudos del HFD, por día)."""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..export_excel import build_workbook
from ..hfd import consolidados as C
from ..hfd import registros as R
from ..schemas import HfdConsolidadoRequest, HfdRegistrosRequest, ReportResponse

router = APIRouter(prefix="/api/hfd", tags=["hfd"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/catalogo", summary="Archivos HFD y sus magnitudes")
def catalogo():
    return _guard(R.catalogo)


@router.post(
    "/registros",
    response_model=ReportResponse,
    summary="Registros del HFD por día (96 intervalos de 15 min por medida)",
    description=f"Máximo {R.MAX_DIAS} días. Columnas 00:00 … 23:45 (intervalos 0..95), como el archivo HFD.",
)
def registros(req: HfdRegistrosRequest):
    return _guard(R.registros, req.archivo, req.magnitud, req.desde, req.hasta, req.estacion)


@router.post("/exportar", summary="Registros del HFD como archivo .xlsx")
def exportar(req: HfdRegistrosRequest):
    res = _guard(R.registros, req.archivo, req.magnitud, req.desde, req.hasta, req.estacion)
    label = R.ARCHIVOS[req.archivo][2]
    unidad = f" ({R.UNIDADES[req.magnitud]})" if req.magnitud in R.UNIDADES else ""
    titulo = f"HFD {label} {req.magnitud}{unidad} — {req.desde.isoformat()} a {req.hasta.isoformat()}"
    fname = f"HFD_{label.replace(' ', '_')}_{req.magnitud}_{req.desde.isoformat()}_{req.hasta.isoformat()}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    return StreamingResponse(build_workbook(res, titulo), media_type=_XLSX, headers=headers)


# ─────────────── Consolidados con drill-down (hasta la medida) ───────────────
# id -> (etiqueta, función). Los de 15 min usan `fecha`; los de energía, el rango.

def _fecha(req: HfdConsolidadoRequest):
    if not req.fecha:
        raise ValueError("Falta la fecha.")
    return req.fecha


def _rango(req: HfdConsolidadoRequest):
    if not (req.desde and req.hasta):
        raise ValueError("Faltan las fechas de inicio y final.")
    return req.desde, req.hasta


_CONSOLIDADOS = {
    "generacion-tipo": ("Generación por tecnología", lambda r: C.generacion_tipo(_fecha(r))),
    "energia-tipo": ("Energía por tecnología", lambda r: C.energia_tipo(*_rango(r))),
    "demanda-departamento": ("Demanda por departamento", lambda r: C.demanda_departamento(_fecha(r))),
}


@router.post(
    "/consolidados/{id}",
    response_model=ReportResponse,
    summary="Consolidado HFD con drill-down: generacion-tipo | energia-tipo | demanda-departamento",
    description="generacion-tipo y demanda-departamento: un día (`fecha`), 96 lecturas en MW. "
                f"energia-tipo: `desde`/`hasta` (máx. {R.MAX_DIAS} días), MWh por día. "
                "Filas en orden de árbol con `_nivel` (0 = tipo/departamento).",
)
def consolidado(id: str, req: HfdConsolidadoRequest):
    if id not in _CONSOLIDADOS:
        raise HTTPException(status_code=404, detail=f"Consolidado HFD desconocido: {id}")
    return _guard(_CONSOLIDADOS[id][1], req)


@router.post("/consolidados/{id}/exportar", summary="Consolidado HFD como archivo .xlsx")
def exportar_consolidado(id: str, req: HfdConsolidadoRequest):
    if id not in _CONSOLIDADOS:
        raise HTTPException(status_code=404, detail=f"Consolidado HFD desconocido: {id}")
    label, fn = _CONSOLIDADOS[id]
    res = _guard(fn, req)
    periodo = req.fecha.isoformat() if req.fecha else f"{req.desde.isoformat()} a {req.hasta.isoformat()}"
    titulo = f"HFD {label} — {periodo}"
    fname = f"HFD_{label.replace(' ', '_')}_{periodo.replace(' a ', '_')}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    return StreamingResponse(build_workbook(res, titulo, totales=True), media_type=_XLSX, headers=headers)
