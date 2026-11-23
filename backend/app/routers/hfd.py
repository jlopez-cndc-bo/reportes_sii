"""Endpoints REST del módulo SCADA HFD (registros crudos del HFD, por día)."""
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from .. import sesion
from ..export_excel import build_workbook
from ..hfd import consolidados as C
from ..hfd import correcciones as K
from ..hfd import registros as R
from ..schemas import (
    HfdConsolidadoRequest,
    HfdCorreccionRequest,
    HfdLoginRequest,
    HfdRegistrosRequest,
    ReportResponse,
)

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


# ───────────── Correcciones de operadores SCADA (única escritura de la app) ─────────────

@router.post("/sesion", summary="Iniciar sesión de editor (usuario del dominio CNDC)")
def iniciar_sesion(req: HfdLoginRequest, response: Response):
    try:
        return {"usuario": sesion.iniciar(req.usuario, req.password, response)}
    except sesion.CredencialesInvalidas:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    except sesion.NoAutorizado:
        raise HTTPException(status_code=403, detail="Su usuario no está autorizado para corregir valores.")
    except sesion.DirectorioNoDisponible:
        raise HTTPException(status_code=503, detail="No se pudo contactar al directorio (Active Directory).")


@router.get("/sesion", summary="Usuario de la sesión de editor, o null")
def ver_sesion(hfd_sesion: str | None = Cookie(default=None)):
    return {"usuario": sesion.leer_token(hfd_sesion)}


@router.delete("/sesion", summary="Cerrar la sesión de editor")
def cerrar_sesion(response: Response):
    sesion.cerrar(response)
    return {"usuario": None}


@router.get("/correcciones/propuesta-smec", summary="Valores propuestos desde el medidor SMEC (MW)")
def propuesta_smec(id_obj: int, fecha: date, _u: str = Depends(sesion.requiere_editor)):
    return _guard(K.propuesta_smec, id_obj, fecha)


@router.post("/correcciones", summary="Guardar correcciones de una señal y un día")
def guardar_correcciones(req: HfdCorreccionRequest, usuario: str = Depends(sesion.requiere_editor)):
    n = _guard(K.guardar, usuario, req.archivo, req.id_obj, req.el, req.fecha,
               [c.model_dump() for c in req.cambios], req.motivo)
    return {"guardadas": n}


@router.get("/correcciones/recargar", summary="Recargar el día en rs7 (avance en vivo, SSE)")
def recargar(fecha: date, _u: str = Depends(sesion.requiere_editor)):
    _guard(K.validar_dia, fecha)
    return StreamingResponse(K.recargar_dia(fecha), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
