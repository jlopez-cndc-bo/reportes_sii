"""Resolución en runtime de los códigos de tipo/estado de informe.

Dossier de migración §3a: los códigos de `P_DEF_DOMINIOS` para tipo de informe
(PRELIMINAR/FINAL/RECTIFICATORIO) y estado (ENVIADO/APROBADO/...) difieren
entre entornos Oracle — no se hardcodean. Se resuelven por **uso real** en
`F_GF_INFORMEFALLA` (evita ambigüedad: la base tiene descripciones repetidas
como "ENVIADO", que también existe como estado de notificación) y, para
completar códigos que el dominio define pero que los datos de este entorno
aún no usaron, por el dominio completo filtrado por `D_COD_TIPO`. Cacheado
por proceso: estos códigos son estables mientras el proceso vive.

Confirmado empíricamente contra el Oracle que lee ReportesSII (2026-10-08):
PRELIMINAR=20, FINAL=21, RECTIFICATORIO=22 (NO 3593/3594/3595, que son los
valores de otro entorno). El dominio D_COD_ESTADO_INF en este entorno sólo
tiene EN_ELABORACION/ELABORADO/ENVIADO/ENVIADO_ERROR — no existe "APROBADO"
en absoluto (ni en los datos ni en el dominio completo), a diferencia de
SisFalla original.
"""
import unicodedata
from dataclasses import dataclass

from ..db import query


def _norm(texto) -> str:
    if texto is None:
        return ""
    d = unicodedata.normalize("NFKD", str(texto))
    d = "".join(c for c in d if not unicodedata.combining(c))
    return " ".join(d.upper().split())


def _por_uso(columna: str, tabla: str) -> dict[str, int]:
    rows = query(
        f"""
        SELECT DISTINCT t.{columna} AS cod, d.descripcion_dominio AS desc_dom
        FROM {tabla} t
        JOIN p_def_dominios d ON d.cod_dominio = t.{columna}
        WHERE t.{columna} IS NOT NULL
        """
    )
    mapa: dict[str, int] = {}
    for r in rows:
        mapa.setdefault(_norm(r["desc_dom"]), int(r["cod"]))
    return mapa


def _por_dominio(d_cod_tipo: str) -> dict[str, int]:
    rows = query(
        "SELECT cod_dominio, descripcion_dominio FROM p_def_dominios WHERE d_cod_tipo = :t",
        {"t": d_cod_tipo},
    )
    return {_norm(r["descripcion_dominio"]): int(r["cod_dominio"]) for r in rows}


@dataclass(frozen=True)
class CodigosInforme:
    tipo_preliminar: int
    tipo_final: int
    tipo_rectificatorio: int
    estado_enviado: int
    # -1 (no coincide con ningún código real) si este entorno no tiene un
    # estado "APROBADO" — confirmado que es el caso en orcl.cndc.bo.
    estado_aprobado: int


_cache: CodigosInforme | None = None


def codigos() -> CodigosInforme:
    """Códigos resueltos (cacheados). Lanza RuntimeError si no puede resolver
    los imprescindibles (FINAL/RECTIFICATORIO/ENVIADO) — una falla visible es
    preferible a filtrar informes con un código adivinado y mal."""
    global _cache
    if _cache is not None:
        return _cache
    tipos = _por_uso("PK_D_COD_TIPOINFORME", "F_GF_INFORMEFALLA")
    estados = {
        **_por_dominio("D_COD_ESTADO_INF"),
        **_por_uso("D_COD_ESTADO_INF", "F_GF_INFORMEFALLA"),
    }
    faltan = [k for k in ("PRELIMINAR", "FINAL", "RECTIFICATORIO") if k not in tipos]
    if faltan or "ENVIADO" not in estados:
        raise RuntimeError(
            "No se pudieron resolver los códigos de tipo/estado de informe en "
            f"P_DEF_DOMINIOS: faltan {faltan or ['ENVIADO']}."
        )
    _cache = CodigosInforme(
        tipo_preliminar=tipos["PRELIMINAR"],
        tipo_final=tipos["FINAL"],
        tipo_rectificatorio=tipos["RECTIFICATORIO"],
        estado_enviado=estados["ENVIADO"],
        estado_aprobado=estados.get("APROBADO", -1),
    )
    return _cache


def reset_codigos() -> None:
    """Limpia la caché (para tests)."""
    global _cache
    _cache = None
