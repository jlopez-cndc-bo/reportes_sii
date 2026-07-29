"""Endpoints REST del módulo SMEC (energía y potencia)."""
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..export_excel import build_workbook
from ..schemas import ReportResponse, SmecReporteRequest
from ..smec import estructura
from ..smec import reportes as R

router = APIRouter(prefix="/api/smec", tags=["smec"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_TITULOS = {
    "potencia_15min": "Potencia - 15 minutos",
    "potencia_hora": "Potencia - Horaria",
    "potencia_max_diario": "Potencia - Máxima diaria",
    "potencia_max_entre_fechas": "Potencia - Máxima entre fechas",
    "energia_dia": "Energía - Día",
    "energia_mes": "Energía - Mes",
    "energia_anio": "Energía - Año",
    "factor_dia": "Factor de carga - Día",
    "factor_periodo": "Factor de carga - Periodo",
}


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/estructura")
def estructura_arbol():
    return _guard(estructura.get_estructura)


def _despachar(req: SmecReporteRequest):
    f1 = req.fecha_inicio
    f2 = req.fecha_fin or req.fecha_inicio
    ids = req.unidades
    d = req.direccion
    t = req.tipo
    if t == "potencia_15min":
        return R.potencia_intervalo(f1, ids, "15min", d, req.nivel)
    if t == "potencia_hora":
        return R.potencia_intervalo(f1, ids, "hora", d, req.nivel)
    if t == "potencia_max_diario":
        return R.maximo_periodo(f1, f2, ids, d)
    if t == "potencia_max_entre_fechas":
        return R.maximo_entre_fechas(f1, f2, ids, d)
    if t == "energia_dia":
        return R.energia_dia(f1, f2, ids, d)
    if t == "energia_mes":
        return R.energia_mes(f1, f2, ids, d)
    if t == "energia_anio":
        return R.energia_anio(f1, f2, ids, d)
    if t == "factor_dia":
        return R.factor_carga(f1, f1, ids, d)
    if t == "factor_periodo":
        return R.factor_carga(f1, f2, ids, d)
    raise ValueError(f"Tipo de reporte SMEC desconocido: {t}")


def _validar(req: SmecReporteRequest):
    if req.fecha_fin and req.fecha_fin < req.fecha_inicio:
        raise HTTPException(status_code=400,
                            detail="La fecha final no puede ser anterior a la inicial.")


@router.post("/reporte", response_model=ReportResponse)
def reporte(req: SmecReporteRequest):
    _validar(req)
    return _guard(_despachar, req)


@router.post("/exportar")
def exportar(req: SmecReporteRequest):
    _validar(req)
    res = _guard(_despachar, req)
    if res.get("table") == "POT_DRILL":
        # Sangría por nivel para que la jerarquía se lea en Excel.
        res = {**res, "rows": [
            {**r, "nombre": "    " * r.get("_nivel", 0) + str(r.get("nombre", ""))}
            for r in res["rows"]
        ]}
    ini = req.fecha_inicio.date().isoformat()
    dir_lbl = "Inyeccion" if req.direccion == "iny" else "Retiro"
    label = _TITULOS.get(req.tipo, req.tipo)
    titulo = f"SMEC · {label} ({dir_lbl}) — desde {ini}"
    buf = build_workbook(res, titulo)
    fname = f"SMEC_{label.replace(' ', '_')}_{dir_lbl}_{ini}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    return StreamingResponse(buf, media_type=_XLSX, headers=headers)
