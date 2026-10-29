"""Reportes tabulares de SisFalla (fallas del sistema eléctrico, CNDC).

Los 15 reportes tabulares del catálogo original, portados de
SisFalla_30X64/Web/SisFallaApiPy/routers/reportes.py — SQL verbatim, mismos
nombres de salida, sin filtro de fila por agente/propietario (confirmado en
el dossier de migración 2026-10-08: ningún reporte de este módulo restringe
filas por agente; los 3 casos que sí acotan columnas/acceso según sesión
—`agente-contactos`, `notificacion-falla`, la columna `usuarioTransaccion`
de `detalle-informes`— se resolvieron excluyendo los dos primeros del tab y
omitiendo esa columna en el tercero, por no haber sesión de usuario).
"""
from datetime import datetime, time, timedelta
from typing import Any

from ..db import query
from ..sqlutil import limitar_top_n
from .cndc_final import CNDC_FINAL_SUBQUERY, cndc_final_binds
from .cod_falla import descomponer_cod_falla, resolver_cod_falla
from .constants import PK_COD_CNDC, TIPO_PERSONA_AGENTE
from .dominios import codigos
from .entidades import entidades
from .fuentes import (
    componentes_atributos_source,
    componentes_sti_source,
    personas_source,
    tiene_columna,
)

MAX_LIMITE = 2000


def _filtro_cod_falla_agente(
    sql: str, params: dict, *, falla_col: str, agente_expr: str,
    cod_falla: int | None, agente: str | None,
) -> str:
    """Mismo patrón que `_aplicar_filtros_reporte` del SisFalla original."""
    if cod_falla is not None:
        sql += f" AND {falla_col} = :cod_falla"
        params["cod_falla"] = cod_falla
    if agente:
        sql += f" AND UPPER({agente_expr}) LIKE UPPER(:agente)"
        params["agente"] = f"%{agente}%"
    return sql


def _agregar_filtro(sql: str, params: dict, condicion: str, nombre: str, valor: Any) -> str:
    params[nombre] = valor
    return sql + f" AND {condicion}"


def _agregar_filtro_hasta(sql: str, params: dict, condicion: str, hasta: datetime) -> str:
    """Como `_agregar_filtro`, pero fijando 'hasta' al final de ese día.

    Los presets de fecha (incl. "Hoy"/"Ayer") y el date picker mandan la
    misma fecha en desde y hasta a medianoche; como el filtro compara con
    '<', sin este ajuste un rango de un solo día nunca matchea nada.
    """
    if hasta.time() == time.min:
        hasta = hasta + timedelta(days=1)
    return _agregar_filtro(sql, params, condicion, "hasta", hasta)


# ──────────────────────── 1. Seguimiento de informes ────────────────────────

def seguimiento_informes(
    cod_falla: int | None,
    agente: str | None,
    desde: datetime | None,
    hasta: datetime | None,
    limite: int = 500,
) -> dict[str, Any]:
    sql = f"""
        SELECT a.PK_COD_FALLA,
               a.PK_COD_PERSONA,
               NVL(p.SIGLA, '') AS SIGLA_AGENTE,
               NVL(p.NOM_PERSONA, '') AS NOM_AGENTE,
               a.PLAZO,
               a.D_COD_SEGUIMIENTO_INF,
               NVL(d.DESCRIPCION_DOMINIO, '') AS SEGUIMIENTO
        FROM F_GF_REG_INFORMEFALLA a
        LEFT JOIN {personas_source()} p ON p.PK_COD_PERSONA = a.PK_COD_PERSONA
        LEFT JOIN P_DEF_DOMINIOS d ON d.COD_DOMINIO = a.D_COD_SEGUIMIENTO_INF
        WHERE 1 = 1
    """
    params: dict[str, Any] = {}
    if cod_falla is not None:
        sql = _agregar_filtro(sql, params, "a.PK_COD_FALLA = :cod_falla", "cod_falla", cod_falla)
    if agente:
        sql = _agregar_filtro(
            sql, params,
            "(UPPER(p.SIGLA) LIKE UPPER(:agente) OR UPPER(p.NOM_PERSONA) LIKE UPPER(:agente))",
            "agente", f"%{agente}%",
        )
    if desde:
        sql = _agregar_filtro(sql, params, "a.PLAZO >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "a.PLAZO < :hasta", hasta)
    # PK_COD_FALLA primero (codifica año+número, siempre confiable); PLAZO
    # como desempate puede estar mal poblado en registros viejos.
    sql += " ORDER BY a.PK_COD_FALLA DESC, a.PLAZO DESC, p.SIGLA"
    sql, _ = limitar_top_n(sql, limite, MAX_LIMITE)

    rows = [
        {
            **descomponer_cod_falla(r["pk_cod_falla"]),
            "pkCodPersona": r["pk_cod_persona"],
            "siglaAgente": r.get("sigla_agente") or "",
            "nomAgente": r.get("nom_agente") or "",
            "plazo": r.get("plazo"),
            "codSeguimiento": r.get("d_cod_seguimiento_inf"),
            "seguimiento": r.get("seguimiento") or str(r.get("d_cod_seguimiento_inf") or ""),
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "siglaAgente", "label": "Agente"},
        {"key": "nomAgente", "label": "Nombre agente"},
        {"key": "plazo", "label": "Plazo", "format": "datetime"},
        {"key": "seguimiento", "label": "Seguimiento"},
    ]
    return {"table": "SEGUIMIENTO_INFORMES", "columns": columns, "rows": rows}


# ──────────────────────── 2. Detalle de informes ────────────────────────

def detalle_informes(
    cod_falla: int | None,
    agente: str | None,
    desde: datetime | None,
    hasta: datetime | None,
    gestion: int | None,
    limite: int = 500,
) -> dict[str, Any]:
    sql = f"""
        SELECT o.ID_OPERACION AS COD_OPERACION,
               NVL(def.NOMBRE_OPERACION, '') AS TIPO_OPERACION,
               o.PK_COD_FALLA,
               o.PK_COD_ORIGEN_INFORME AS ORIGEN,
               NVL(p.SIGLA, '') AS AGENTE,
               l.FECHA_TRANSACCION
        FROM F_GF_OPERACION o
        LEFT JOIN P_GF_DEF_OPERACION def ON def.ID_OPERACION = o.ID_OPERACION
        LEFT JOIN F_SEC_LOG l ON l.COD_SEC_LOG = o.SEC_LOG
        LEFT JOIN {personas_source()} p ON p.PK_COD_PERSONA = o.PK_COD_ORIGEN_INFORME
        WHERE 1 = 1
    """
    params: dict[str, Any] = {}
    gestion_full = None
    if gestion and cod_falla is None:
        gestion_full = gestion + 2000 if gestion < 100 else gestion
        desde = None
        hasta = None
    if cod_falla is not None:
        sql = _agregar_filtro(sql, params, "o.PK_COD_FALLA = :cod_falla", "cod_falla", cod_falla)
    elif gestion_full is not None:
        base = (gestion_full - 2000) * 10000
        sql += " AND o.PK_COD_FALLA BETWEEN :gestion_desde AND :gestion_hasta"
        params["gestion_desde"] = base
        params["gestion_hasta"] = base + 9999
    if agente:
        sql = _agregar_filtro(sql, params, "UPPER(p.SIGLA) LIKE UPPER(:agente)", "agente", f"%{agente}%")
    if desde:
        sql = _agregar_filtro(sql, params, "l.FECHA_TRANSACCION >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "l.FECHA_TRANSACCION < :hasta", hasta)
    # F_GF_OPERACION no tiene el subquery de "informes finales CNDC" que
    # acota a los demás reportes de este módulo — sin límite trae 185k+ filas.
    sql += " ORDER BY l.FECHA_TRANSACCION DESC, o.PK_COD_FALLA DESC"
    sql, _ = limitar_top_n(sql, limite, MAX_LIMITE)

    rows = [
        {
            "codOperacion": r.get("cod_operacion"),
            "tipoOperacion": r.get("tipo_operacion") or str(r.get("cod_operacion") or ""),
            **descomponer_cod_falla(r.get("pk_cod_falla")),
            "origen": r.get("origen"),
            "agente": r.get("agente") or "",
            "fechaTransaccion": r.get("fecha_transaccion"),
        }
        for r in query(sql, params)
    ]
    # Nota (dossier §1): en SisFalla el login de quien operó
    # (`usuarioTransaccion`) sólo se muestra a sesiones CNDC. ReportesSII no
    # tiene sesión de usuario, así que ese dato de auditoría interna no se
    # incluye en absoluto en este reporte portado.
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "agente", "label": "Agente"},
        {"key": "tipoOperacion", "label": "Operación"},
        {"key": "fechaTransaccion", "label": "Fecha", "format": "datetime"},
    ]
    return {"table": "DETALLE_INFORMES", "columns": columns, "rows": rows}


# ──────────────────────── Buscador de fallas (para un selector) ────────────────────────

def buscar_fallas(q: str | None, limite: int = 30) -> list[dict[str, Any]]:
    """Búsqueda liviana de fallas para un selector tipo autocompletar.

    Si `q` trae separador ('/' o '-') se interpreta como código exacto visible
    (igual que `resolver_cod_falla`); si no, busca coincidencia parcial en el
    código o en la descripción corta. Fuente: F_GF_REGFALLA (registro base de
    fallas, una fila por falla — no requiere informe ya emitido).
    """
    sql = """
        SELECT PK_COD_FALLA, FEC_INICIO, NVL(DESCRIPCION_CORTA_FALLA, '') AS DESCRIPCION
          FROM F_GF_REGFALLA
         WHERE 1 = 1
    """
    params: dict[str, Any] = {}
    q = (q or "").strip()
    if q:
        cod_exacto = None
        if any(sep in q for sep in ("/", "-")):
            try:
                cod_exacto = resolver_cod_falla(q)
            except ValueError:
                pass  # no era un código válido; se busca como texto libre más abajo
        if cod_exacto is not None:
            sql += " AND PK_COD_FALLA = :q_cod"
            params["q_cod"] = cod_exacto
        else:
            sql += """ AND (
                TO_CHAR(PK_COD_FALLA) LIKE :q_pct
                OR UPPER(NVL(DESCRIPCION_CORTA_FALLA, '')) LIKE UPPER(:q_pct)
            )"""
            params["q_pct"] = f"%{q}%"
    sql += " ORDER BY PK_COD_FALLA DESC"
    sql, _ = limitar_top_n(sql, limite, MAX_LIMITE)

    return [
        {
            **descomponer_cod_falla(r["pk_cod_falla"]),
            "fecInicio": r.get("fec_inicio"),
            "descripcion": r.get("descripcion") or "",
        }
        for r in query(sql, params)
    ]


# ──────────────────────── 3. Detalle por supervisor/operador ────────────────────────

def detalle_supervisor(desde: datetime | None, hasta: datetime | None) -> dict[str, Any]:
    # FK_COD_SUPERVISOR2 no existe en todos los entornos (confirmado: falta
    # en el Oracle que lee ReportesSII, aunque sí existe en SisFalla original)
    # — se omite el join/columna si la tabla no la tiene, en vez de fallar.
    con_sup2 = tiene_columna("F_GF_REGFALLA", "FK_COD_SUPERVISOR2")
    sup2_select = "sup2.NOM_PERSONA AS SUPERVISOR2," if con_sup2 else "NULL AS SUPERVISOR2,"
    sup2_join = (
        f"LEFT JOIN {personas_source()} sup2 ON r.FK_COD_SUPERVISOR2 = sup2.PK_COD_PERSONA"
        if con_sup2 else ""
    )
    sql = f"""
        SELECT
            r.PK_COD_FALLA,
            r.FEC_INICIO,
            NVL(r.DESCRIPCION_CORTA_FALLA, '') AS DESCRIPCION,
            sup.NOM_PERSONA AS SUPERVISOR,
            {sup2_select}
            oper.NOM_PERSONA AS OPERADOR
        FROM F_GF_REGFALLA r
        INNER JOIN {personas_source()} sup ON r.FK_COD_SUPERVISOR = sup.PK_COD_PERSONA
        {sup2_join}
        INNER JOIN {personas_source()} oper ON r.FK_COD_OPERADOR = oper.PK_COD_PERSONA
        WHERE 1 = 1
    """
    params: dict[str, Any] = {}
    if desde:
        sql = _agregar_filtro(sql, params, "TRUNC(r.FEC_INICIO) >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "TRUNC(r.FEC_INICIO) < :hasta", hasta)
    sql += " ORDER BY r.PK_COD_FALLA ASC"

    rows = [
        {
            **descomponer_cod_falla(r["pk_cod_falla"]),
            "fecInicio": r.get("fec_inicio"),
            "descripcion": r.get("descripcion") or "",
            "supervisor": r.get("supervisor") or "",
            "supervisor2": r.get("supervisor2") or "",
            "operador": r.get("operador") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "fecInicio", "label": "Fecha inicio", "format": "datetime"},
        {"key": "descripcion", "label": "Descripción"},
        {"key": "supervisor", "label": "Supervisor"},
        {"key": "supervisor2", "label": "Supervisor 2"},
        {"key": "operador", "label": "Operador"},
    ]
    aviso = None if con_sup2 else "Supervisor 2 no está disponible en este Oracle (columna inexistente)."
    return {"table": "DETALLE_SUPERVISOR", "columns": columns, "rows": rows, "aviso": aviso}


# ──────────────────────── 4. Catálogo de agentes ────────────────────────

def agentes() -> dict[str, Any]:
    sql = """
        SELECT PK_COD_PERSONA, NVL(SIGLA, '') AS SIGLA, NOM_PERSONA,
               NVL(DIRECCION, '') AS DIRECCION, NVL(TELEFONO, '') AS TELEFONO,
               NVL(IDENTIFICACION, '') AS IDENTIFICACION
        FROM F_AP_PERSONA
        WHERE D_COD_TIPO_PERSONA = :tipo_persona
          AND NVL(D_COD_ESTADO, '1') = '1'
        ORDER BY SIGLA, NOM_PERSONA
    """
    rows = [
        {
            "pkCodPersona": int(r["pk_cod_persona"]),
            "sigla": r.get("sigla") or "",
            "nomPersona": r.get("nom_persona") or "",
            "direccion": r.get("direccion") or "",
            "telefono": r.get("telefono") or "",
            "identificacion": r.get("identificacion") or "",
        }
        for r in query(sql, {"tipo_persona": TIPO_PERSONA_AGENTE})
    ]
    columns = [
        {"key": "sigla", "label": "Sigla"},
        {"key": "nomPersona", "label": "Nombre"},
        {"key": "direccion", "label": "Dirección"},
        {"key": "telefono", "label": "Teléfono"},
        {"key": "identificacion", "label": "Identificación"},
    ]
    return {"table": "AGENTES", "columns": columns, "rows": rows}


# ──────────────────────── 5. Resumen de fallas por agente ────────────────────────

def resumen_agentes(desde: datetime | None, hasta: datetime | None) -> dict[str, Any]:
    sql = """
        SELECT p.PK_COD_PERSONA, NVL(p.SIGLA, '') AS SIGLA, p.NOM_PERSONA,
               COUNT(DISTINCT sub.PK_COD_FALLA) AS TOTAL_FALLAS
        FROM F_AP_PERSONA p
        LEFT JOIN (
            SELECT i.PK_ORIGEN_INFORME, i.PK_COD_FALLA
            FROM F_GF_INFORMEFALLA i
            JOIN F_GF_REGFALLA r ON r.PK_COD_FALLA = i.PK_COD_FALLA
            WHERE 1 = 1
    """
    params: dict[str, Any] = {}
    if desde is not None:
        sql = _agregar_filtro(sql, params, "TRUNC(r.FEC_INICIO) >= :desde", "desde", desde)
    if hasta is not None:
        sql = _agregar_filtro_hasta(sql, params, "TRUNC(r.FEC_INICIO) < :hasta", hasta)
    sql += """
        ) sub ON sub.PK_ORIGEN_INFORME = p.PK_COD_PERSONA
        WHERE p.D_COD_TIPO_PERSONA = :tipo_persona
          AND NVL(p.D_COD_ESTADO, '1') = '1'
          AND p.PK_COD_PERSONA != :cod_cndc
          AND UPPER(NVL(p.SIGLA, '')) != 'AE'
        GROUP BY p.PK_COD_PERSONA, p.SIGLA, p.NOM_PERSONA
        ORDER BY TOTAL_FALLAS DESC, SIGLA
    """
    # CNDC y AE administran/gestionan los informes de los demás agentes, no
    # son agentes reportantes: se excluyen del ranking.
    params["tipo_persona"] = TIPO_PERSONA_AGENTE
    params["cod_cndc"] = PK_COD_CNDC

    rows = [
        {
            "pkCodPersona": int(r["pk_cod_persona"]),
            "sigla": r.get("sigla") or "",
            "nomPersona": r.get("nom_persona") or "",
            "totalFallas": int(r.get("total_fallas") or 0),
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "sigla", "label": "Sigla"},
        {"key": "nomPersona", "label": "Nombre"},
        {"key": "totalFallas", "label": "Total de fallas"},
    ]
    return {"table": "RESUMEN_AGENTES", "columns": columns, "rows": rows}


# ──────────────────────── 7. Componentes comprometidos (CNDC) ────────────────────────

def componentes_comprometidos(
    cod_falla: int | None, agente: str | None,
    desde: datetime | None, hasta: datetime | None,
) -> dict[str, Any]:
    sql = f"""
        SELECT
            rc.PK_COD_FALLA,
            rc.FEC_APERTURA,
            NVL(c.NOMBRE_COMPONENTE, '') AS COD_COMPONENTE,
            NVL(c.DESCRIPCION_COMPONENTE, '') AS DESCRIP_COMPONENTE,
            NVL(rc.POTENCIA_DESCONECTADA, 0) AS POT_DESC,
            NVL(rc.TIEMPO_INDISPONIBILIDAD, 0)
                + NVL(rc.TIEMPO_PRECONEXION, 0)
                + NVL(rc.TIEMPO_CONEXION, 0) AS TTOTAL_DESCONEXION,
            NVL(p_respo.SIGLA, '') AS SIGLA_RESPONSABLE,
            NVL(resp.TIEMPO_RESPONSABILIDAD, 0) AS TRESPONSABILIDAD,
            NVL(p_prop.SIGLA, '') AS SIGLA_PROPIETARIO,
            NVL(dom_orig.DESCRIPCION_DOMINIO, '') AS ORIGEN,
            NVL(dom_td.DESCRIPCION_DOMINIO, '') AS CAUSA,
            NVL(dom_causa.DESCRIPCION_DOMINIO, '') AS ESPECIFICACION,
            NVL(tc.DESCRIPCION_TIPO, '') AS TIPO_COMPONENTE,
            -- RptCompoComprometidos.cs: SI cuando el total desconexión es 0 y no
            -- hubo tiempo de responsabilidad asignado (reconexión automática sin
            -- intervención); NO si hubo desconexión; en blanco si el total es 0
            -- pero sí hubo responsabilidad asignada.
            DECODE(
                NVL(rc.TIEMPO_INDISPONIBILIDAD, 0) + NVL(rc.TIEMPO_PRECONEXION, 0) + NVL(rc.TIEMPO_CONEXION, 0),
                0, DECODE(NVL(resp.TIEMPO_RESPONSABILIDAD, 0), 0, 'SI'),
                'NO'
            ) AS RECONEX_AUTO
        FROM F_GF_RREGFALLA_COMPONENTE rc
        LEFT JOIN F_GF_RESPONSABILIDAD resp
            ON resp.PK_COD_FALLA = rc.PK_COD_FALLA
            AND resp.PK_ORIGEN_INFORME = rc.PK_ORIGEN_INFORME
            AND resp.PK_D_COD_TIPOINFORME = rc.PK_D_COD_TIPOINFORME
            AND resp.PK_COD_COMPONENTE = rc.PK_COD_COMPONENTE
            AND resp.FEC_APERTURA = rc.FEC_APERTURA
        LEFT JOIN {componentes_atributos_source()} c ON c.PK_COD_COMPONENTE = rc.PK_COD_COMPONENTE
        LEFT JOIN F_AP_PERSONA p_respo ON p_respo.PK_COD_PERSONA = resp.PK_COD_PERSONA_RESPONSABLE
        LEFT JOIN P_AC_TIPOCOMPONENTE tc
            ON tc.PK_COD_TIPO_COMPONENTE = c.D_TIPO_COMPONENTE
            AND tc.PK_COD_TIPO_COMPONENTE != 0
        LEFT JOIN F_AP_PERSONA p_prop ON p_prop.PK_COD_PERSONA = c.PROPIETARIO
        INNER JOIN F_GF_INFORMEFALLA inf
            ON inf.PK_COD_FALLA = rc.PK_COD_FALLA
            AND inf.PK_ORIGEN_INFORME = rc.PK_ORIGEN_INFORME
            AND inf.PK_D_COD_TIPOINFORME = rc.PK_D_COD_TIPOINFORME
        LEFT JOIN P_DEF_DOMINIOS dom_orig ON dom_orig.COD_DOMINIO = inf.D_COD_ORIGEN
        LEFT JOIN P_DEF_DOMINIOS dom_td ON dom_td.COD_DOMINIO = inf.D_COD_TIPO_DESCONEXION
        LEFT JOIN P_DEF_DOMINIOS dom_causa ON dom_causa.COD_DOMINIO = inf.D_COD_CAUSA
        WHERE rc.PK_ORIGEN_INFORME = {PK_COD_CNDC}
          AND (rc.PK_COD_FALLA, rc.PK_D_COD_TIPOINFORME) IN (
              SELECT s.PK_COD_FALLA, s.MAX_TIPO FROM {CNDC_FINAL_SUBQUERY} s
          )
    """
    params = cndc_final_binds()
    sql = _filtro_cod_falla_agente(
        sql, params, falla_col="rc.PK_COD_FALLA",
        agente_expr="NVL(p_prop.SIGLA, '') || ' ' || NVL(p_prop.NOM_PERSONA, '')",
        cod_falla=cod_falla, agente=agente,
    )
    if desde:
        sql = _agregar_filtro(sql, params, "rc.FEC_APERTURA >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "rc.FEC_APERTURA < :hasta", hasta)
    sql += " ORDER BY rc.PK_COD_FALLA DESC, rc.FEC_APERTURA"

    rows = [
        {
            **descomponer_cod_falla(r["pk_cod_falla"]),
            "fecApertura": r.get("fec_apertura"),
            "codComponente": r.get("cod_componente") or "",
            "descripComponente": r.get("descrip_componente") or "",
            "potDesc": float(r.get("pot_desc") or 0),
            "tTotalDesconexion": float(r.get("ttotal_desconexion") or 0),
            "siglaResponsable": r.get("sigla_responsable") or "",
            "tResponsabilidad": float(r.get("tresponsabilidad") or 0),
            "siglaPropietario": r.get("sigla_propietario") or "",
            "origen": r.get("origen") or "",
            "causa": r.get("causa") or "",
            "especificacion": r.get("especificacion") or "",
            "tipoComponente": r.get("tipo_componente") or "",
            "reconexAuto": r.get("reconex_auto") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "fecApertura", "label": "Apertura", "format": "datetime"},
        {"key": "codComponente", "label": "Componente"},
        {"key": "siglaPropietario", "label": "Propietario"},
        {"key": "potDesc", "label": "Pot. desconectada", "format": "0.00"},
        {"key": "tTotalDesconexion", "label": "Tiempo total (min)", "format": "0.00"},
        {"key": "siglaResponsable", "label": "Responsable"},
        {"key": "causa", "label": "Causa"},
        {"key": "reconexAuto", "label": "Reconexión automática"},
    ]
    return {"table": "COMPONENTES_COMPROMETIDOS", "columns": columns, "rows": rows}


# ──────────────────────── 8. Elementos comprometidos (CNDC) ────────────────────────

def elementos_comprometidos(
    cod_falla: int | None, agente: str | None,
    desde: datetime | None, hasta: datetime | None,
) -> dict[str, Any]:
    sql = f"""
        SELECT
            NVL(c.NOMBRE_COMPONENTE, '') AS COMPONENTE,
            NVL(c.DESCRIPCION_COMPONENTE, '') AS DESCRIPCION_COMPONENTE,
            rc.PK_COD_FALLA,
            rc.FEC_APERTURA,
            -- RptEleCompometidos.cs: invierte el signo si el flujo es reverso.
            DECODE(UPPER(rc.FLUJO_N1_N2), 'NEGATIVO', -1, 1) * NVL(rc.POTENCIA_DESCONECTADA, 0) AS POT_DESC,
            NVL(rc.TIEMPO_INDISPONIBILIDAD, 0) AS INDISP,
            NVL(rc.TIEMPO_PRECONEXION, 0) AS PRECONEX,
            NVL(rc.TIEMPO_CONEXION, 0) AS CONEX,
            NVL(rc.TIEMPO_INDISPONIBILIDAD, 0)
                + NVL(rc.TIEMPO_PRECONEXION, 0)
                + NVL(rc.TIEMPO_CONEXION, 0) AS TTOTAL_DESCONEXION,
            NVL(p.SIGLA, '') AS AGENTE,
            NVL(tc.DESCRIPCION_TIPO, '') AS TIPO_COMPONENTE
        FROM F_GF_RREGFALLA_COMPONENTE rc
        LEFT JOIN {componentes_atributos_source()} c ON c.PK_COD_COMPONENTE = rc.PK_COD_COMPONENTE
        LEFT JOIN F_AP_PERSONA p ON p.PK_COD_PERSONA = c.PROPIETARIO
        LEFT JOIN P_AC_TIPOCOMPONENTE tc
            ON tc.PK_COD_TIPO_COMPONENTE = c.D_TIPO_COMPONENTE
            AND tc.PK_COD_TIPO_COMPONENTE != 0
        WHERE rc.PK_ORIGEN_INFORME = {PK_COD_CNDC}
          AND (rc.PK_COD_FALLA, rc.PK_D_COD_TIPOINFORME) IN (
              SELECT s.PK_COD_FALLA, s.MAX_TIPO FROM {CNDC_FINAL_SUBQUERY} s
          )
    """
    params = cndc_final_binds()
    sql = _filtro_cod_falla_agente(
        sql, params, falla_col="rc.PK_COD_FALLA",
        agente_expr="NVL(p.SIGLA, '') || ' ' || NVL(p.NOM_PERSONA, '')",
        cod_falla=cod_falla, agente=agente,
    )
    if desde:
        sql = _agregar_filtro(sql, params, "rc.FEC_APERTURA >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "rc.FEC_APERTURA < :hasta", hasta)
    sql += " ORDER BY rc.PK_COD_FALLA DESC, rc.FEC_APERTURA"

    rows = [
        {
            **descomponer_cod_falla(r["pk_cod_falla"]),
            "componente": r.get("componente") or "",
            "descripcionComponente": r.get("descripcion_componente") or "",
            "fecApertura": r.get("fec_apertura"),
            "potDesc": float(r.get("pot_desc") or 0),
            "indisponibilidad": float(r.get("indisp") or 0),
            "preconexion": float(r.get("preconex") or 0),
            "conexion": float(r.get("conex") or 0),
            "tTotalDesconexion": float(r.get("ttotal_desconexion") or 0),
            "agente": r.get("agente") or "",
            "tipoComponente": r.get("tipo_componente") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "componente", "label": "Componente"},
        {"key": "agente", "label": "Agente"},
        {"key": "fecApertura", "label": "Apertura", "format": "datetime"},
        {"key": "potDesc", "label": "Pot. desconectada", "format": "0.00"},
        {"key": "tTotalDesconexion", "label": "Tiempo total (min)", "format": "0.00"},
        {"key": "tipoComponente", "label": "Tipo"},
    ]
    return {"table": "ELEMENTOS_COMPROMETIDOS", "columns": columns, "rows": rows}


# ──────────────────────── 9. Fallas de alimentadores (CNDC) ────────────────────────

def falla_alimentadores(
    cod_falla: int | None, agente: str | None,
    desde: datetime | None, hasta: datetime | None,
) -> dict[str, Any]:
    sql = f"""
        SELECT
            NVL(c.NOMBRE_COMPONENTE, '') AS ALIMENTADOR,
            NVL(c.DESCRIPCION_COMPONENTE, '') AS DESC_ALIMENTADOR,
            a.PK_COD_FALLA,
            DECODE(a.RELE_OPERADO, 0, 'NO', 1, 'SI', '-') AS RELE_OPERADO,
            a.FECHA_APERTURA,
            a.FECHA_CIERRE,
            NVL(a.POT_DESC, 0) AS POT_DESC,
            CASE
                WHEN a.FECHA_CIERRE IS NOT NULL THEN
                    ROUND((CAST(a.FECHA_CIERRE AS DATE) - CAST(a.FECHA_APERTURA AS DATE)) * 24 * 60, 2)
            END AS TIEMPO_DESC,
            NVL(p.SIGLA, '') AS AGENTE,
            NVL(edac.TIPO_EDAC, '') AS TIPO_EDAC,
            -- Paridad WinForms (FormAlimentador.CalcularTiempoTotalDesc) y Crystal
            -- Report original: ENS = (minutos desconexión / 60) * MW, con el mismo
            -- doble redondeo intermedio — no simplificar o no calzará con el histórico.
            CASE
                WHEN a.FECHA_CIERRE IS NOT NULL THEN
                    ROUND(
                        ROUND(
                            ROUND((CAST(a.FECHA_CIERRE AS DATE) - CAST(a.FECHA_APERTURA AS DATE)) * 24 * 60, 2)
                            * NVL(a.POT_DESC, 0),
                            2
                        ) / 60,
                        2
                    )
            END AS ENS
        FROM F_GF_OP_ALIMENTADOR a
        LEFT JOIN {componentes_atributos_source()} c ON c.PK_COD_COMPONENTE = a.PK_COD_COMPONENTE
        LEFT JOIN F_AP_PERSONA p ON p.PK_COD_PERSONA = c.PROPIETARIO
        LEFT JOIN F_GF_PARAM_EDAC edac ON edac.PK_COD_EDAC = a.COD_EDAC
        WHERE a.PK_ORIGEN_INFORME = {PK_COD_CNDC}
          AND (a.PK_COD_FALLA, a.PK_D_COD_TIPOINFORME) IN (
              SELECT s.PK_COD_FALLA, s.MAX_TIPO FROM {CNDC_FINAL_SUBQUERY} s
          )
    """
    params = cndc_final_binds()
    sql = _filtro_cod_falla_agente(
        sql, params, falla_col="a.PK_COD_FALLA",
        agente_expr="NVL(p.SIGLA, '') || ' ' || NVL(p.NOM_PERSONA, '')",
        cod_falla=cod_falla, agente=agente,
    )
    if desde:
        sql = _agregar_filtro(sql, params, "a.FECHA_APERTURA >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "a.FECHA_APERTURA < :hasta", hasta)
    sql += " ORDER BY a.PK_COD_FALLA DESC, a.FECHA_APERTURA"

    rows = [
        {
            **descomponer_cod_falla(r["pk_cod_falla"]),
            "alimentador": r.get("alimentador") or "",
            "descAlimentador": r.get("desc_alimentador") or "",
            "releOperado": r.get("rele_operado") or "-",
            "fechaApertura": r.get("fecha_apertura"),
            "fechaCierre": r.get("fecha_cierre"),
            "potDesc": float(r.get("pot_desc") or 0),
            "tiempoDesc": float(r.get("tiempo_desc") or 0) if r.get("fecha_cierre") else None,
            "ens": float(r["ens"]) if r.get("ens") is not None else None,
            "agente": r.get("agente") or "",
            "tipoEdac": r.get("tipo_edac") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "alimentador", "label": "Alimentador"},
        {"key": "agente", "label": "Agente"},
        {"key": "fechaApertura", "label": "Apertura", "format": "datetime"},
        {"key": "fechaCierre", "label": "Cierre", "format": "datetime"},
        {"key": "releOperado", "label": "Relé operado"},
        {"key": "potDesc", "label": "Pot. desconectada", "format": "0.00"},
        {"key": "tiempoDesc", "label": "Tiempo (min)", "format": "0.00"},
        {"key": "ens", "label": "ENS (MWh)", "format": "0.00"},
        {"key": "tipoEdac", "label": "EDAC"},
    ]
    return {"table": "FALLA_ALIMENTADORES", "columns": columns, "rows": rows}


# ──────────────────────── 10. Detalle de interruptores (CNDC) ────────────────────────

def det_interruptores(
    cod_falla: int | None, agente: str | None,
    desde: datetime | None, hasta: datetime | None,
) -> dict[str, Any]:
    # Códigos 79/80/81 (Manual/Automático/Remota) confirmados estables en este
    # entorno (verificado contra P_DEF_DOMINIOS, 2026-10-08).
    sql = f"""
        SELECT
            NVL(c.NOMBRE_COMPONENTE, '') AS INTERRUPTOR,
            NVL(c.DESCRIPCION_COMPONENTE, '') AS DESCRIPCION_INTERRUP,
            i.PK_COD_FALLA,
            i.FECHA_APERTURA,
            DECODE(i.PK_D_COD_TIPO_OPER_APER, 79, 'M', 80, 'A', 81, 'R', '-') AS TIPO_APERTURA,
            i.FECHA_CIERRE,
            DECODE(i.PK_D_COD_TIPO_OPER_CIERRE, 79, 'M', 80, 'A', 81, 'R', '-') AS TIPO_CIERRE,
            DECODE(i.PK_D_COD_TIPO_OPER_CIERRE,
                79, 'NO',
                80, DECODE(i.PK_D_COD_TIPO_OPER_APER, 80, 'SI', 'NO'),
                81, 'NO', '-') AS RECONECTADO,
            NVL(p.SIGLA, '') AS AGENTE,
            NVL(tc.DESCRIPCION_TIPO, '') AS TIPO_COMPONENTE
        FROM F_GF_OP_INTERRUPTOR i
        LEFT JOIN {componentes_atributos_source()} c ON c.PK_COD_COMPONENTE = i.PK_COD_COMPONENTE
        LEFT JOIN F_AP_PERSONA p ON p.PK_COD_PERSONA = c.PROPIETARIO
        LEFT JOIN P_AC_TIPOCOMPONENTE tc
            ON tc.PK_COD_TIPO_COMPONENTE = c.D_TIPO_COMPONENTE
            AND tc.PK_COD_TIPO_COMPONENTE != 0
        WHERE i.PK_ORIGEN_INFORME = {PK_COD_CNDC}
          AND (i.PK_COD_FALLA, i.PK_D_COD_TIPOINFORME) IN (
              SELECT s.PK_COD_FALLA, s.MAX_TIPO FROM {CNDC_FINAL_SUBQUERY} s
          )
    """
    params = cndc_final_binds()
    sql = _filtro_cod_falla_agente(
        sql, params, falla_col="i.PK_COD_FALLA",
        agente_expr="NVL(p.SIGLA, '') || ' ' || NVL(p.NOM_PERSONA, '')",
        cod_falla=cod_falla, agente=agente,
    )
    if desde:
        sql = _agregar_filtro(sql, params, "i.FECHA_APERTURA >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "i.FECHA_APERTURA < :hasta", hasta)
    sql += " ORDER BY i.PK_COD_FALLA DESC, i.FECHA_APERTURA"

    rows = [
        {
            **descomponer_cod_falla(r["pk_cod_falla"]),
            "interruptor": r.get("interruptor") or "",
            "descripcion": r.get("descripcion_interrup") or "",
            "fechaApertura": r.get("fecha_apertura"),
            "tipoApertura": r.get("tipo_apertura") or "-",
            "fechaCierre": r.get("fecha_cierre"),
            "tipoCierre": r.get("tipo_cierre") or "-",
            "reconectado": r.get("reconectado") or "-",
            "agente": r.get("agente") or "",
            "tipoComponente": r.get("tipo_componente") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "interruptor", "label": "Interruptor"},
        {"key": "agente", "label": "Agente"},
        {"key": "fechaApertura", "label": "Apertura", "format": "datetime"},
        {"key": "tipoApertura", "label": "Tipo apertura"},
        {"key": "fechaCierre", "label": "Cierre", "format": "datetime"},
        {"key": "tipoCierre", "label": "Tipo cierre"},
        {"key": "reconectado", "label": "Reconectado"},
    ]
    return {"table": "DET_INTERRUPTORES", "columns": columns, "rows": rows}


# ──────────────────────── 11. Relés operados (CNDC) ────────────────────────

def reles_operados(
    cod_falla: int | None, agente: str | None,
    desde: datetime | None, hasta: datetime | None,
) -> dict[str, Any]:
    # Base = F_GF_OP_INTERRUPTOR (no F_GF_RELES_OPER): una operación sin relé
    # asociado igual aparece, con las columnas de relé en blanco — usar la
    # tabla de relés como base perdería esas filas (nota del SisFalla original).
    sql = f"""
        SELECT
            i.PK_COD_FALLA,
            NVL(ci.NOMBRE_COMPONENTE, '') AS INTERRUPTOR,
            NVL(ci.DESCRIPCION_COMPONENTE, '') AS DESCRIPCION_INTERRUP,
            i.FECHA_APERTURA,
            r.FUNCION_RELE,
            NVL(r.TIPO_RELE, '') AS TIPO_RELE,
            NVL(r.TIEMPO_RELE, 0) AS TIEMPO_RELE,
            NVL(r.ZONA_RELE, 0) AS ZONA,
            NVL(r.DISTANCIA_RELE, 0) AS DISTANCIA,
            NVL(r.NUMERO_RELE, 0) AS NUMERO,
            NVL(p.SIGLA, '') AS AGENTE
        FROM F_GF_OP_INTERRUPTOR i
        LEFT JOIN F_GF_RELES_OPER r
            ON r.PK_COD_FALLA = i.PK_COD_FALLA
            AND r.PK_ORIGEN_INFORME = i.PK_ORIGEN_INFORME
            AND r.PK_COD_COMPONENTE = i.PK_COD_COMPONENTE
            AND r.PK_D_COD_TIPOINFORME = i.PK_D_COD_TIPOINFORME
            AND r.FEC_APERTURA = i.FECHA_APERTURA
        LEFT JOIN {componentes_atributos_source()} ci ON ci.PK_COD_COMPONENTE = i.PK_COD_COMPONENTE
        LEFT JOIN F_AP_PERSONA p ON p.PK_COD_PERSONA = ci.PROPIETARIO
        WHERE i.PK_ORIGEN_INFORME = {PK_COD_CNDC}
          AND (i.PK_COD_FALLA, i.PK_D_COD_TIPOINFORME) IN (
              SELECT s.PK_COD_FALLA, s.MAX_TIPO FROM {CNDC_FINAL_SUBQUERY} s
          )
    """
    params = cndc_final_binds()
    sql = _filtro_cod_falla_agente(
        sql, params, falla_col="i.PK_COD_FALLA",
        agente_expr="NVL(p.SIGLA, '') || ' ' || NVL(p.NOM_PERSONA, '')",
        cod_falla=cod_falla, agente=agente,
    )
    if desde:
        sql = _agregar_filtro(sql, params, "i.FECHA_APERTURA >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "i.FECHA_APERTURA < :hasta", hasta)
    sql += " ORDER BY i.PK_COD_FALLA DESC, i.FECHA_APERTURA, r.FUNCION_RELE"

    rows = [
        {
            **descomponer_cod_falla(r["pk_cod_falla"]),
            "interruptor": r.get("interruptor") or "",
            "descripcion": r.get("descripcion_interrup") or "",
            "fechaApertura": r.get("fecha_apertura"),
            "funcion": r.get("funcion_rele") or "",
            "tipoRele": r.get("tipo_rele") or "",
            "tiempo": float(r.get("tiempo_rele") or 0),
            "zona": float(r.get("zona") or 0),
            "distancia": float(r.get("distancia") or 0),
            "numero": float(r.get("numero") or 0),
            "agente": r.get("agente") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "interruptor", "label": "Interruptor"},
        {"key": "agente", "label": "Agente"},
        {"key": "fechaApertura", "label": "Apertura", "format": "datetime"},
        {"key": "funcion", "label": "Función"},
        {"key": "tipoRele", "label": "Tipo de relé"},
        {"key": "tiempo", "label": "Tiempo (ms)", "format": "0.00"},
        {"key": "zona", "label": "Zona"},
        {"key": "distancia", "label": "Distancia", "format": "0.00"},
    ]
    return {"table": "RELES_OPERADOS", "columns": columns, "rows": rows}


# ──────────────────────── 12. Consulta EDAC (solo lectura) ────────────────────────

def edac(agente: str | None, desde: datetime | None, hasta: datetime | None) -> dict[str, Any]:
    sql = f"""
        SELECT
            c.PK_COD_COMPONENTE,
            NVL(c.CODIGO_COMPONENTE, '') AS CODIGO_COMPONENTE,
            NVL(c.NOMBRE_COMPONENTE, '') AS ALIMENTADOR,
            NVL(c.DESCRIPCION_COMPONENTE, '') AS DESCRIPCION_COMPONENTE,
            e.TIPO_EDAC,
            TO_CHAR(e.AJUSTE_EDAC, '90.99') || '[Hz]' AS AJUSTE_EDAC,
            e.ETAPA_EDAC,
            rc.FECHA_INICIO,
            NVL(p.SIGLA, '') AS AGENTE
        FROM {componentes_atributos_source()} c
        INNER JOIN F_GF_RCOMPONENTE_EDAC rc ON rc.PK_COD_COMPONENTE = c.PK_COD_COMPONENTE
        INNER JOIN F_GF_PARAM_EDAC e ON e.PK_COD_EDAC = rc.PK_COD_EDAC
        LEFT JOIN F_AP_PERSONA p ON p.PK_COD_PERSONA = c.PROPIETARIO
        WHERE 1 = 1
    """
    params: dict[str, Any] = {}
    if agente:
        sql = _agregar_filtro(
            sql, params,
            "UPPER(NVL(p.SIGLA, '') || ' ' || NVL(p.NOM_PERSONA, '')) LIKE UPPER(:agente)",
            "agente", f"%{agente}%",
        )
    if desde:
        sql = _agregar_filtro(sql, params, "rc.FECHA_INICIO >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "rc.FECHA_INICIO < :hasta", hasta)
    sql += " ORDER BY rc.FECHA_INICIO DESC, c.NOMBRE_COMPONENTE ASC"

    rows = [
        {
            "pkCodComponente": int(r["pk_cod_componente"]) if r.get("pk_cod_componente") else None,
            "codigoComponente": r.get("codigo_componente") or "",
            "alimentador": r.get("alimentador") or "",
            "descripcionComponente": r.get("descripcion_componente") or "",
            "tipoEdac": r.get("tipo_edac") or "",
            "ajusteEdac": r.get("ajuste_edac") or "",
            "etapaEdac": r.get("etapa_edac") or "",
            "fechaInicio": r.get("fecha_inicio"),
            "agente": r.get("agente") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "alimentador", "label": "Componente"},
        {"key": "agente", "label": "Agente"},
        {"key": "tipoEdac", "label": "Tipo EDAC"},
        {"key": "ajusteEdac", "label": "Ajuste"},
        {"key": "etapaEdac", "label": "Etapa"},
        {"key": "fechaInicio", "label": "Vigente desde", "format": "datetime"},
    ]
    return {"table": "EDAC", "columns": columns, "rows": rows}


# ──────────────────────── 13. Detalle de desconexiones (CNDC) ────────────────────────

def detalle_desconexiones(
    cod_falla: int | None, agente: str | None,
    desde: datetime | None, hasta: datetime | None,
) -> dict[str, Any]:
    c = codigos()
    pks = ",".join(str(pk) for pk in entidades().pks_transmisoras)
    sql = f"""
        SELECT DISTINCT
            rc.PK_COD_COMPONENTE AS CODIGO,
            rc.FEC_APERTURA,
            NVL(comp.NOMBRE_COMPONENTE, '') AS COD_COMPONENTE,
            NVL(comp.DESCRIPCION_COMPONENTE, '') AS DESC_COMPONENTE,
            NVL(resp.TIEMPO_RESPONSABILIDAD, 0) AS TIEMPO_RESPONSABILIDAD,
            NVL(rc.TIEMPO_INDISPONIBILIDAD, 0)
                + NVL(rc.TIEMPO_PRECONEXION, 0)
                + NVL(rc.TIEMPO_CONEXION, 0) AS TTOTAL_DESCONEXION,
            NVL(respo.SIGLA, '') AS SIGLA_RESPONSABLE,
            CASE
                WHEN NVL(resp.TIEMPO_RESPONSABILIDAD, 0)
                     + NVL(rc.TIEMPO_INDISPONIBILIDAD, 0)
                     + NVL(rc.TIEMPO_PRECONEXION, 0)
                     + NVL(rc.TIEMPO_CONEXION, 0) = 0
                THEN NVL(propie.SIGLA, '')
                ELSE NVL(respo.SIGLA, '')
            END AS RESPONSABLE,
            NVL(dom_causa.DESCRIPCION_DOMINIO, '') AS DESC_CAUSA,
            CASE
                WHEN NVL(resp.TIEMPO_RESPONSABILIDAD, 0)
                     + NVL(rc.TIEMPO_INDISPONIBILIDAD, 0)
                     + NVL(rc.TIEMPO_PRECONEXION, 0)
                     + NVL(rc.TIEMPO_CONEXION, 0) = 0
                     AND comp.D_TIPO_COMPONENTE = 1
                THEN 'AUTOMATICA'
                ELSE ''
            END AS RECONEXION,
            rc.PK_COD_FALLA,
            NVL(propie.SIGLA, '') AS SIGLA_PROPIE,
            NVL(rc.TIEMPO_INDISPONIBILIDAD, 0) AS TIEMPO_INDISPONIBILIDAD,
            NVL(rc.TIEMPO_PRECONEXION, 0) AS TIEMPO_PRECONEXION,
            NVL(rc.TIEMPO_CONEXION, 0) AS TIEMPO_CONEXION,
            NVL(rc.TIEMPO_SISTEMA, 0) AS TIEMPO_SISTEMA,
            NVL(rc.TIEMPO_P_SIST, 0) AS TIEMPO_PSISTEMA,
            NVL(rc.TIEMPO_P_OPER, 0) AS TIEMPO_POPERACION,
            DECODE(comp.D_TIPO_COMPONENTE, 1, 'LINEAS', 9, 'AUTOTRANFORMADORES', 2, 'TRANSFORMADORES', '') AS TIPO_COMPONENTE,
            CASE
                WHEN rc.PK_D_COD_TIPOINFORME = :tipo_preliminar THEN 'PRELIMINAR'
                WHEN rc.PK_D_COD_TIPOINFORME IN (:tipo_final, :tipo_rectificatorio) THEN 'FINAL'
                ELSE TO_CHAR(rc.PK_D_COD_TIPOINFORME)
            END AS TIPO_INFORME,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM {componentes_sti_source()} sti
                    WHERE sti.PK_COD_COMPONENTE = rc.PK_COD_COMPONENTE
                      AND sti.FECHA_FIN IS NULL
                ) THEN 'DENTRO STI'
                ELSE 'FUERA STI'
            END AS AMBITO_STI
        FROM F_GF_RREGFALLA_COMPONENTE rc
        LEFT JOIN F_GF_RESPONSABILIDAD resp
            ON resp.PK_COD_FALLA = rc.PK_COD_FALLA
            AND resp.PK_ORIGEN_INFORME = rc.PK_ORIGEN_INFORME
            AND resp.PK_D_COD_TIPOINFORME = rc.PK_D_COD_TIPOINFORME
            AND resp.PK_COD_COMPONENTE = rc.PK_COD_COMPONENTE
            AND resp.FEC_APERTURA = rc.FEC_APERTURA
        LEFT JOIN {componentes_atributos_source()} comp ON comp.PK_COD_COMPONENTE = rc.PK_COD_COMPONENTE
        LEFT JOIN F_AP_PERSONA respo ON respo.PK_COD_PERSONA = resp.PK_COD_PERSONA_RESPONSABLE
        LEFT JOIN F_GF_INFORMEFALLA inf
            ON inf.PK_COD_FALLA = rc.PK_COD_FALLA
            AND inf.PK_ORIGEN_INFORME = rc.PK_ORIGEN_INFORME
            AND inf.PK_D_COD_TIPOINFORME = rc.PK_D_COD_TIPOINFORME
        LEFT JOIN P_DEF_DOMINIOS dom_causa ON dom_causa.COD_DOMINIO = inf.D_COD_CAUSA
        LEFT JOIN F_AP_PERSONA propie ON propie.PK_COD_PERSONA = comp.PROPIETARIO
        WHERE comp.D_TIPO_COMPONENTE IN (1, 9, 2)
          AND comp.PROPIETARIO IN ({pks})
          AND rc.PK_ORIGEN_INFORME = {PK_COD_CNDC}
          AND (
                rc.PK_D_COD_TIPOINFORME = :tipo_preliminar
                OR (rc.PK_COD_FALLA, rc.PK_D_COD_TIPOINFORME) IN (
                    SELECT s.PK_COD_FALLA, s.MAX_TIPO FROM {CNDC_FINAL_SUBQUERY} s
                )
          )
    """
    params = {
        **cndc_final_binds(),
        "tipo_preliminar": c.tipo_preliminar,
        "tipo_final": c.tipo_final,
        "tipo_rectificatorio": c.tipo_rectificatorio,
    }
    sql = _filtro_cod_falla_agente(
        sql, params, falla_col="rc.PK_COD_FALLA",
        agente_expr=(
            "NVL(respo.SIGLA, '') || ' ' || NVL(respo.NOM_PERSONA, '') || ' ' || "
            "NVL(propie.SIGLA, '') || ' ' || NVL(propie.NOM_PERSONA, '')"
        ),
        cod_falla=cod_falla, agente=agente,
    )
    if desde:
        sql = _agregar_filtro(sql, params, "rc.FEC_APERTURA >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "rc.FEC_APERTURA < :hasta", hasta)
    sql += " ORDER BY rc.PK_COD_COMPONENTE ASC, rc.PK_COD_FALLA ASC"

    rows = [
        {
            "pkCodComponente": r.get("codigo"),
            "fechaApertura": r.get("fec_apertura"),
            "codComponente": r.get("cod_componente") or "",
            "descComponente": r.get("desc_componente") or "",
            "tiempoResponsabilidad": float(r.get("tiempo_responsabilidad") or 0),
            "tTotalDesconexion": float(r.get("ttotal_desconexion") or 0),
            "siglaResponsable": r.get("sigla_responsable") or "",
            "responsable": r.get("responsable") or "",
            "causa": r.get("desc_causa") or "",
            "reconexion": r.get("reconexion") or "",
            **descomponer_cod_falla(r.get("pk_cod_falla")),
            "siglaPropietario": r.get("sigla_propie") or "",
            "tiempoIndisponibilidad": float(r.get("tiempo_indisponibilidad") or 0),
            "tiempoPreconexion": float(r.get("tiempo_preconexion") or 0),
            "tiempoConexion": float(r.get("tiempo_conexion") or 0),
            "tiempoSistema": float(r.get("tiempo_sistema") or 0),
            "tiempoPSistema": float(r.get("tiempo_psistema") or 0),
            "tiempoPOperacion": float(r.get("tiempo_poperacion") or 0),
            "tipoComponente": r.get("tipo_componente") or "",
            "tipoInforme": r.get("tipo_informe") or "",
            "ambitoSti": r.get("ambito_sti") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "codComponente", "label": "Componente"},
        {"key": "siglaPropietario", "label": "Propietario"},
        {"key": "fechaApertura", "label": "Apertura", "format": "datetime"},
        {"key": "tTotalDesconexion", "label": "Tiempo total (min)", "format": "0.00"},
        {"key": "responsable", "label": "Responsable"},
        {"key": "causa", "label": "Causa"},
        {"key": "reconexion", "label": "Reconexión"},
        {"key": "tipoInforme", "label": "Tipo informe"},
        {"key": "ambitoSti", "label": "Ámbito STI"},
    ]
    return {"table": "DETALLE_DESCONEXIONES", "columns": columns, "rows": rows}


# ──────────────────────── 14. EDAC para análisis ────────────────────────

def edac_analisis() -> dict[str, Any]:
    fecha_max_rows = query("SELECT MAX(TRUNC(FECHA_INICIO)) AS FECHAMAX FROM F_GF_RCOMPONENTE_EDAC")
    fecha_max = fecha_max_rows[0]["fechamax"] if fecha_max_rows else None
    columns = [
        {"key": "categoria", "label": "Categoría"},
        {"key": "fechaInicio", "label": "Fecha inicio", "format": "datetime"},
        {"key": "etapas", "label": "Etapas"},
        {"key": "frecuencia", "label": "Frecuencia (Hz)", "format": "0.00"},
        {"key": "ordenPlan", "label": "Orden"},
        {"key": "nombreComponente", "label": "Componente"},
        {"key": "sigla", "label": "Agente"},
    ]
    if not fecha_max:
        return {"table": "EDAC_ANALISIS", "columns": columns, "rows": []}

    decode_orden = ",".join(f"{pk},{orden}" for pk, orden in entidades().orden_edac_por_pk.items())
    sql = f"""
        SELECT
            CASE
                WHEN dom.ORDEN BETWEEN 100 AND 199 THEN '1'
                WHEN dom.ORDEN BETWEEN 200 AND 299 THEN '2'
                ELSE '3'
            END AS CAT,
            TRUNC(a.FECHA_INICIO) AS FEC_INICIO,
            TO_NUMBER(SUBSTR(e.TIPO_EDAC, 3, 2), '99') AS ETAPAS,
            e.AJUSTE_EDAC AS FRECUENCIA,
            TO_CHAR(e.ETAPA_EDAC) AS TIEMPO,
            e.ETAPA_EDAC AS T_FORMATO,
            DECODE(comp.PROPIETARIO,{decode_orden}, NULL) AS ORD_PLAN,
            NVL(comp.NOMBRE_COMPONENTE, '') AS NOMBRE_COMPONENTE,
            NVL(p.SIGLA, '') AS SIGLA
        FROM F_GF_RCOMPONENTE_EDAC a
        INNER JOIN {componentes_atributos_source()} comp ON comp.PK_COD_COMPONENTE = a.PK_COD_COMPONENTE
        INNER JOIN F_GF_PARAM_EDAC e ON e.PK_COD_EDAC = a.PK_COD_EDAC
        INNER JOIN P_DEF_DOMINIOS dom ON dom.DESCRIPCION_DOMINIO = e.TIPO_EDAC
        LEFT JOIN F_AP_PERSONA p ON p.PK_COD_PERSONA = comp.PROPIETARIO
        WHERE TRUNC(a.FECHA_INICIO) = :fecha_max
        ORDER BY CAT, FEC_INICIO, ETAPAS, FRECUENCIA, T_FORMATO, NOMBRE_COMPONENTE
    """
    rows = [
        {
            "categoria": r.get("cat") or "",
            "fechaInicio": r.get("fec_inicio"),
            "etapas": int(r.get("etapas") or 0),
            "frecuencia": float(r.get("frecuencia") or 0),
            "tiempo": r.get("tiempo") or "",
            "tiempoFormato": r.get("t_formato"),
            "ordenPlan": int(r.get("ord_plan") or 0),
            "nombreComponente": r.get("nombre_componente") or "",
            "sigla": r.get("sigla") or "",
        }
        for r in query(sql, {"fecha_max": fecha_max})
    ]
    return {"table": "EDAC_ANALISIS", "columns": columns, "rows": rows}


# ──────────────────────── 15. Operación EDAC ────────────────────────

def operacion_edac(
    cod_falla: int | None, agente: str | None,
    desde: datetime | None, hasta: datetime | None,
) -> dict[str, Any]:
    sql = f"""
        SELECT
            a.PK_COD_FALLA,
            NVL(p.SIGLA, '') AS AGENTE,
            NVL(comp.NOMBRE_COMPONENTE, '') AS ALIMENTADOR,
            a.FECHA_APERTURA AS FECHA_TOTAL,
            TRUNC(a.FECHA_APERTURA) AS FECHA,
            TO_CHAR(a.FECHA_APERTURA, 'HH24:MI') AS HORA,
            e.TIPO_EDAC AS ETAPA,
            e.AJUSTE_EDAC AS FREC,
            NVL(a.POT_DESC, 0) AS POTENCIA,
            NVL(dom_etapa.ORDEN, 0) AS ETAPA_EDAC,
            NVL(doc.CAUSA, '') AS CAUSA,
            NVL(doc.DESCONEXION_COMPONENTE, '') AS DESCONEX_DE,
            NVL(doc.OBSERVACIONES, '') AS OBSERVACIONES,
            NVL(dom_origen.DESCRIPCION_DOMINIO, '') AS CAUSA_TIPO
        FROM F_GF_OP_ALIMENTADOR a
        INNER JOIN {componentes_atributos_source()} comp ON comp.PK_COD_COMPONENTE = a.PK_COD_COMPONENTE
        INNER JOIN F_GF_PARAM_EDAC e ON e.PK_COD_EDAC = a.COD_EDAC
        INNER JOIN F_AP_PERSONA p ON p.PK_COD_PERSONA = comp.PROPIETARIO
        INNER JOIN F_GF_INFORMEFALLA inf
            ON inf.PK_COD_FALLA = a.PK_COD_FALLA
            AND inf.PK_ORIGEN_INFORME = a.PK_ORIGEN_INFORME
            AND inf.PK_D_COD_TIPOINFORME = a.PK_D_COD_TIPOINFORME
        LEFT JOIN P_DEF_DOMINIOS dom_etapa ON dom_etapa.DESCRIPCION_DOMINIO = e.TIPO_EDAC
        LEFT JOIN P_DEF_DOMINIOS dom_origen ON dom_origen.COD_DOMINIO = inf.D_COD_ORIGEN
        -- F_GF_DOC_ANALISIS es por (falla, origen, tipo): se une al mismo informe
        -- CNDC elegido (a.*) para no multiplicar filas por cada informe.
        LEFT JOIN F_GF_DOC_ANALISIS doc
            ON doc.PK_COD_FALLA = a.PK_COD_FALLA
            AND doc.PK_ORIGEN_INFORME = a.PK_ORIGEN_INFORME
            AND doc.PK_D_COD_TIPOINFORME = a.PK_D_COD_TIPOINFORME
        WHERE a.PK_ORIGEN_INFORME = {PK_COD_CNDC}
          AND (a.PK_COD_FALLA, a.PK_D_COD_TIPOINFORME) IN (
              SELECT s.PK_COD_FALLA, s.MAX_TIPO FROM {CNDC_FINAL_SUBQUERY} s
          )
    """
    params = cndc_final_binds()
    sql = _filtro_cod_falla_agente(
        sql, params, falla_col="a.PK_COD_FALLA",
        agente_expr="NVL(p.SIGLA, '') || ' ' || NVL(p.NOM_PERSONA, '')",
        cod_falla=cod_falla, agente=agente,
    )
    if desde:
        sql = _agregar_filtro(sql, params, "a.FECHA_APERTURA >= :desde", "desde", desde)
    if hasta:
        sql = _agregar_filtro_hasta(sql, params, "a.FECHA_APERTURA < :hasta", hasta)
    sql += " ORDER BY FECHA, HORA, ETAPA_EDAC, AGENTE"

    rows = [
        {
            **descomponer_cod_falla(r.get("pk_cod_falla")),
            "agente": r.get("agente") or "",
            "alimentador": r.get("alimentador") or "",
            "fechaTotal": r.get("fecha_total"),
            "fecha": r.get("fecha"),
            "hora": r.get("hora") or "",
            "etapa": r.get("etapa") or "",
            "frecuencia": float(r.get("frec") or 0),
            "potencia": float(r.get("potencia") or 0),
            "etapaEdac": int(r.get("etapa_edac") or 0),
            "causa": r.get("causa") or "",
            "desconexionDe": r.get("desconex_de") or "",
            "observaciones": r.get("observaciones") or "",
            "causaTipo": r.get("causa_tipo") or "",
        }
        for r in query(sql, params)
    ]
    columns = [
        {"key": "codFallaTexto", "label": "Falla"},
        {"key": "agente", "label": "Agente"},
        {"key": "alimentador", "label": "Alimentador"},
        {"key": "fecha", "label": "Fecha", "format": "datetime"},
        {"key": "hora", "label": "Hora"},
        {"key": "etapa", "label": "Etapa EDAC"},
        {"key": "frecuencia", "label": "Frecuencia (Hz)", "format": "0.00"},
        {"key": "potencia", "label": "Potencia (MW)", "format": "0.00"},
        {"key": "causa", "label": "Causa"},
        {"key": "causaTipo", "label": "Origen"},
    ]
    return {"table": "OPERACION_EDAC", "columns": columns, "rows": rows}
