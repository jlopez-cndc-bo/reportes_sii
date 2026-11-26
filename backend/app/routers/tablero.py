"""Endpoints del tablero «Monitores» (sólo lectura)."""
from fastapi import APIRouter, HTTPException, Query

from ..tablero import servicio
from ..tablero.config import cargar

router = APIRouter(prefix="/api/tablero", tags=["tablero"])


@router.get("/inicio", summary="Monitores del inicio para un periodo")
def inicio(periodo: str | None = Query(
        None, description="ayer · mes_en_curso · anio · AAAA-MM. Sin valor: último mes completo.")):
    try:
        return servicio.inicio(periodo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ahora", summary="Generación HFD del último intervalo, unidades indisponibles y alertas")
def ahora():
    return servicio.ahora_sistema()


@router.get("/dia", summary="Operación de un día: curvas HFD, punta SMEC e indisponibilidades")
def dia(fecha: str | None = Query(None, description="AAAA-MM-DD. Sin valor: hoy.")):
    try:
        return servicio.dia(fecha)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config", summary="Configuración vigente del tablero (indicadores, niveles, umbrales)")
def config():
    return cargar().model_dump()
