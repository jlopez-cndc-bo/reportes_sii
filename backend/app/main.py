"""Punto de entrada FastAPI del backend de Reportes CNDC."""
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import close_pool, init_pool, pool_ready
from .routers import export, hfd, reports, sisfalla, smec, tablero
from .security import require_auth
from .tablero.servicio import precalentar


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    if pool_ready():
        threading.Thread(target=precalentar, daemon=True).start()
    yield
    close_pool()


_DESCRIPTION = """
API de reportes del CNDC (Reporte de la Operación + SMEC + Sistema de Fallas + SCADA HFD). Además de
alimentar la UI web, está pensada para que sistemas internos consuman estos
mismos datos y automaticen sus propios procesos: todos los endpoints bajo
`/api` devuelven JSON (o un .xlsx en `/api/exportar/*`, `/api/smec/exportar`
y `/api/sisfalla/exportar/{id}`), documentados abajo con sus parámetros y
valores válidos — "Try it out" sirve para probar un pedido antes de
integrarlo.

Sin autenticación (red interna de solo lectura). No hay límite de tasa: se
asume un número reducido de consumidores conocidos: evitar loops ajustados
contra Oracle.
"""

_TAGS_METADATA = [
    {
        "name": "indisponibilidades",
        "description": "Reporte de la Operación (antes Indisponibilidades, módulo INDISP): disponibilidad, no disponibilidad y horas por tipo de operación de cada componente, programación de mantenimiento y árbol de componentes.",
    },
    {
        "name": "smec",
        "description": "Potencia, energía y factor de carga (módulo SMEC) + árbol de la estructura eléctrica.",
    },
    {
        "name": "export",
        "description": "Los reportes del Reporte de la Operación, como archivo .xlsx descargable.",
    },
    {
        "name": "tablero",
        "description": "Tablero «Monitores»: indicadores por periodo con comparaciones, tendencia, fuente y fecha del dato; «Ahora» con HFD, unidades indisponibles y alertas.",
    },
    {
        "name": "sisfalla",
        "description": (
            "Sistema de Fallas: los 14 "
            "reportes tabulares de solo lectura. Excluidos por decisión del usuario "
            "(datos de contacto personal, no operativos): agente-contactos y "
            "notificacion-falla; también fuera de alcance el informe PDF puntual "
            "informe-falla."
        ),
    },
]

app = FastAPI(
    title="Reportes CNDC",
    description=_DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=_TAGS_METADATA,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoints protegidos por auth opcional (no-op si no hay credenciales configuradas).
app.include_router(reports.router, dependencies=[Depends(require_auth)])
app.include_router(export.router, dependencies=[Depends(require_auth)])
app.include_router(smec.router, dependencies=[Depends(require_auth)])
app.include_router(sisfalla.router, dependencies=[Depends(require_auth)])
app.include_router(hfd.router, dependencies=[Depends(require_auth)])
app.include_router(tablero.router, dependencies=[Depends(require_auth)])


@app.get("/health")
def health():
    return {"status": "ok", "oracle": "conectado" if pool_ready() else "sin configurar"}


# Servir el frontend compilado (web/frontend/dist) si existe: una sola URL.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
