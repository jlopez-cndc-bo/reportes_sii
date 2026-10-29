"""Punto de entrada FastAPI del backend de indisponibilidades."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import close_pool, init_pool, pool_ready
from .routers import export, reports, sisfalla, smec
from .security import require_auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    yield
    close_pool()


app = FastAPI(
    title="Reportes SII — Indisponibilidades",
    description="API de reportes de indisponibilidad de equipos (migración web del módulo INDISP).",
    version="0.1.0",
    lifespan=lifespan,
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


@app.get("/health")
def health():
    return {"status": "ok", "oracle": "conectado" if pool_ready() else "sin configurar"}


# Servir el frontend compilado (web/frontend/dist) si existe: una sola URL.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
