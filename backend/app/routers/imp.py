"""Informe de Mediano Plazo: estudios disponibles y descarga de anexos (.xlsx)."""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..imp import anexos, estudios

router = APIRouter(prefix="/api/imp", tags=["imp"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/estudios", summary="Estudios (carpetas AAAA-MM) y qué falta para cada anexo")
def listar():
    try:
        todos = estudios.listar()
    except LookupError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return [{
        "id": e.id,
        "periodo": e.periodo,
        "anexos": [anexos.estado(n, e, todos[i + 1:]) for n in anexos.ANEXOS],
    } for i, e in enumerate(todos)]


class AnexoRequest(BaseModel):
    estudio: str
    anexo: int


@router.post("/anexo", summary="Genera ANEXOn.xlsx del estudio con el formato final")
def anexo(req: AnexoRequest):
    if req.anexo not in anexos.ANEXOS:
        raise HTTPException(status_code=400, detail=f"Anexo {req.anexo} no disponible (2, 4, 5 o 6).")
    try:
        e, anteriores = estudios.obtener(req.estudio)
        data, avisos = anexos.generar(req.anexo, e, anteriores)
    except ValueError as ex:  # id inválido o archivo con datos que no se pueden leer
        raise HTTPException(status_code=422, detail=str(ex))
    except (LookupError, FileNotFoundError) as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    fname = f"ANEXO{req.anexo}_{e.id}.xlsx"
    return Response(data, media_type=XLSX, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}",
        # Avisos de generación (p. ej. columna sin bloque en 6C): la UI los muestra tras descargar.
        "X-Avisos": quote(" | ".join(avisos)),
    })
