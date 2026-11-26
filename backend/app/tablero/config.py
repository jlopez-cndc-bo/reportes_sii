"""Lee y valida la configuración del tablero (tablero.json); la relee si cambió el archivo."""
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator

_DEFAULT = Path(__file__).with_name("tablero.json")


class NivelDato(BaseModel):
    id: str
    rotulo: str
    es_oficial: bool
    descripcion: str = ""


class Dominio(BaseModel):
    id: str
    nombre: str
    modulo: str          # módulo de la app donde está el detalle


class Indicador(BaseModel):
    id: str
    dominio_id: str
    nombre: str
    descripcion: str
    unidad: str
    decimales: int
    direccion: Literal["up", "down"]
    comparar: Literal["relativa", "puntos"]
    nivel_dato_id: str
    metrica: str
    parametros: dict = {}
    fuente: str
    maximo_historico: bool = False
    responsable: str = "Por definir"


class Umbral(BaseModel):
    kpi_id: str
    vigente_desde: str
    meta: float
    verde: float      # límite de verde (según dirección)
    ambar: float      # límite de ámbar
    aprobado_por: str


class Monitor(BaseModel):
    dominio_id: str
    principal: str
    secundarios: list[str] = []


class Inicio(BaseModel):
    monitores: list[Monitor]
    meses_tendencia: int = 12


class Limites(BaseModel):
    hfd_congelada_lecturas: int
    hfd_atrasado_min: int
    smec_atrasado_dias: int
    pef_aviso_dias: int


class Config(BaseModel):
    niveles_dato: list[NivelDato]
    dominios: list[Dominio]
    indicadores: list[Indicador]
    umbrales: list[Umbral] = []
    inicio: Inicio
    limites: Limites

    @model_validator(mode="after")
    def _referencias(self):
        from .fuentes import METRICAS  # import tardío: fuentes depende de la BD

        niveles = {n.id for n in self.niveles_dato}
        dominios = {d.id for d in self.dominios}
        ids = [i.id for i in self.indicadores]
        if len(ids) != len(set(ids)):
            raise ValueError("Hay indicadores con id repetido.")
        for i in self.indicadores:
            if i.nivel_dato_id not in niveles:
                raise ValueError(f"{i.id}: nivel de dato desconocido «{i.nivel_dato_id}».")
            if i.dominio_id not in dominios:
                raise ValueError(f"{i.id}: dominio desconocido «{i.dominio_id}».")
            if i.metrica not in METRICAS:
                raise ValueError(f"{i.id}: métrica desconocida «{i.metrica}».")
        for u in self.umbrales:
            if u.kpi_id not in ids:
                raise ValueError(f"Umbral para un indicador inexistente: {u.kpi_id}.")
        for m in self.inicio.monitores:
            if m.dominio_id not in dominios:
                raise ValueError(f"Monitor con dominio desconocido «{m.dominio_id}».")
            for k in [m.principal, *m.secundarios]:
                if k not in ids:
                    raise ValueError(f"Monitor {m.dominio_id}: indicador inexistente {k}.")
        return self

    def indicador(self, kpi: str) -> Indicador:
        return next(i for i in self.indicadores if i.id == kpi)


_cache: tuple[float, Config] | None = None


def ruta() -> Path:
    return Path(os.getenv("TABLERO_CONFIG") or _DEFAULT)


def cargar() -> Config:
    """Config vigente; se relee cuando cambia la fecha del archivo."""
    global _cache
    p = ruta()
    mtime = p.stat().st_mtime
    if _cache is None or _cache[0] != mtime:
        _cache = (mtime, Config.model_validate(json.loads(p.read_text(encoding="utf-8"))))
    return _cache[1]
