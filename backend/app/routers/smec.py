"""Endpoints REST del módulo SMEC (energía y potencia)."""
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..export_excel import build_workbook, build_workbook_multi
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


@router.get(
    "/estructura",
    summary="Árbol Inyección/Retiro→Agente→Central",
    description="Jerarquía de `dw_relaciones` para elegir los `unidades` (centrales) de un reporte SMEC.",
)
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


@router.post(
    "/reporte",
    response_model=ReportResponse,
    summary="Reporte SMEC (potencia / energía / factor de carga)",
    description="Un único endpoint despachado por `req.tipo`; ver la descripción de SmecReporteRequest para los valores válidos.",
)
def reporte(req: SmecReporteRequest):
    _validar(req)
    return _guard(_despachar, req)


@router.get(
    "/reporte",
    response_model=ReportResponse,
    summary="Reporte SMEC (potencia / energía / factor de carga) — por query params",
    description=(
        "Igual a POST /api/smec/reporte pero con los parámetros en la URL, pensado "
        "para consumidores que solo hacen GET (ej. el conector Web simple de Power BI)."
    ),
)
def reporte_get(
    tipo: str = Query(..., examples=["potencia_hora"]),
    fecha_inicio: datetime = Query(..., examples=["2026-06-01T00:00:00"]),
    fecha_fin: datetime | None = Query(None, examples=["2026-06-30T23:59:59"]),
    unidades: list[int] = Query(default_factory=list),
    direccion: str = Query("iny", description="'iny' (inyección) | 'ret' (retiro)."),
    nivel: str = Query("central"),
):
    req = SmecReporteRequest(
        tipo=tipo,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        unidades=unidades,
        direccion=direccion,
        nivel=nivel,
    )
    _validar(req)
    return _guard(_despachar, req)


@router.post(
    "/exportar",
    summary="Mismo reporte SMEC, como archivo .xlsx",
    description="Mismos parámetros que POST /api/smec/reporte; devuelve el workbook ya formateado como adjunto.",
)
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


_RESOLUCION_POR_TIPO = {"potencia_15min": "15min", "potencia_hora": "hora"}


@router.post(
    "/exportar-conjunto",
    summary="Potencia SMEC (Inyección + Retiro) en un mismo .xlsx, una hoja por dirección",
    description=(
        "Sólo para tipo 'potencia_15min'/'potencia_hora'. Trae TODAS las centrales "
        "de cada dirección (ignora `unidades`/`direccion` del request) con el "
        "`nivel` y fecha ya elegidos — no depende de la selección del árbol, que "
        "sólo muestra una dirección a la vez."
    ),
)
def exportar_conjunto(req: SmecReporteRequest):
    _validar(req)
    if req.tipo not in _RESOLUCION_POR_TIPO:
        raise HTTPException(
            status_code=400,
            detail="El reporte conjunto sólo aplica a 'potencia_15min' o 'potencia_hora'.",
        )
    resolucion = _RESOLUCION_POR_TIPO[req.tipo]
    label = _TITULOS.get(req.tipo, req.tipo)
    ini = req.fecha_inicio.date().isoformat()

    hojas = []
    for direccion, nombre_hoja in (("iny", "Inyección"), ("ret", "Retiro")):
        res = _guard(R.potencia_intervalo, req.fecha_inicio, [], resolucion, direccion, req.nivel)
        if res.get("table") == "POT_DRILL":
            res = {**res, "rows": [
                {**r, "nombre": "    " * r.get("_nivel", 0) + str(r.get("nombre", ""))}
                for r in res["rows"]
            ]}
        titulo = f"SMEC · {label} ({nombre_hoja}) — desde {ini}"
        hojas.append((nombre_hoja, res, titulo))

    buf = build_workbook_multi(hojas)
    fname = f"SMEC_{label.replace(' ', '_')}_Conjunto_{ini}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    return StreamingResponse(buf, media_type=_XLSX, headers=headers)
