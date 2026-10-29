"""Tests de funciones puras del módulo SISFALLA (sin BD)."""
from datetime import datetime

import pytest

from app.sisfalla import reportes as R
from app.sisfalla.cod_falla import descomponer_cod_falla, resolver_cod_falla
from app.sisfalla.fuentes import componentes_source, personas_source


def test_descomponer_cod_falla_compuesto():
    # 262345 -> gestión 2026, nro 2345
    r = descomponer_cod_falla(262345)
    assert r == {"codFalla": 262345, "codFallaTexto": "2345/2026", "gestion": 2026, "nroFalla": 2345}


def test_descomponer_cod_falla_float_de_oracle():
    # oracledb puede devolver PK_COD_FALLA como float sin escala fija.
    r = descomponer_cod_falla(262345.0)
    assert r["codFalla"] == 262345
    assert r["codFallaTexto"] == "2345/2026"


def test_descomponer_cod_falla_corto_sin_gestion_inferida():
    # 4 dígitos o menos: no hay suficiente para inferir gestión.
    r = descomponer_cod_falla(2345)
    assert r["gestion"] is None
    assert r["nroFalla"] == 2345
    assert r["codFallaTexto"] == "2345"


def test_descomponer_cod_falla_con_gestion_explicita():
    r = descomponer_cod_falla(2345, gestion=26)
    assert r["gestion"] == 2026
    assert r["codFallaTexto"] == "2345/2026"


def test_descomponer_cod_falla_cero_no_es_vacio():
    r = descomponer_cod_falla(0)
    assert r["codFalla"] == 0
    assert r["nroFalla"] == 0


def test_descomponer_cod_falla_none():
    r = descomponer_cod_falla(None)
    assert r == {"codFalla": None, "codFallaTexto": "", "gestion": None, "nroFalla": None}


def test_resolver_cod_falla_formato_visible_barra():
    assert resolver_cod_falla("247/2026") == 260247


def test_resolver_cod_falla_formato_visible_guion_gestion_corta():
    assert resolver_cod_falla("0247-26") == 260247


def test_resolver_cod_falla_round_trip_con_descomponer():
    compuesto = resolver_cod_falla("3/2025")
    assert descomponer_cod_falla(compuesto)["codFallaTexto"] == "3/2025"


def test_resolver_cod_falla_codigo_compuesto_directo():
    # Compatibilidad con scripts internos que ya mandaban el PK_COD_FALLA.
    assert resolver_cod_falla("262345") == 262345
    assert resolver_cod_falla(262345) == 262345


def test_resolver_cod_falla_vacio():
    assert resolver_cod_falla(None) is None
    assert resolver_cod_falla("") is None


def test_buscar_fallas_codigo_exacto_por_formato_visible(monkeypatch):
    capturado = {}

    def fake_query(sql, params):
        capturado["sql"] = sql
        capturado["params"] = params
        return [{"pk_cod_falla": 260247, "fec_inicio": datetime(2026, 10, 1), "descripcion": "Desconexión"}]

    monkeypatch.setattr(R, "query", fake_query)
    rows = R.buscar_fallas("247/2026")
    assert capturado["params"] == {"q_cod": 260247}
    assert rows[0]["codFallaTexto"] == "247/2026"


def test_buscar_fallas_texto_libre_cuando_no_es_codigo_valido(monkeypatch):
    capturado = {}

    def fake_query(sql, params):
        capturado["params"] = params
        return []

    monkeypatch.setattr(R, "query", fake_query)
    # "corte-general" tiene '-' pero no es un código válido (no son números).
    R.buscar_fallas("corte-general")
    assert capturado["params"] == {"q_pct": "%corte-general%"}


def test_buscar_fallas_vacio_no_filtra(monkeypatch):
    capturado = {}

    def fake_query(sql, params):
        capturado["params"] = params
        return []

    monkeypatch.setattr(R, "query", fake_query)
    R.buscar_fallas("")
    assert capturado["params"] == {}


def test_agregar_filtro_hasta_medianoche_incluye_dia_completo():
    # Desde=Hasta en el mismo día (preset "Hoy"/"Ayer" o date picker) no debe
    # excluir ese día entero del rango "< hasta".
    params = {}
    hasta = datetime(2026, 10, 12)
    sql = R._agregar_filtro_hasta("SELECT 1 WHERE 1=1", params, "col < :hasta", hasta)
    assert params["hasta"] == datetime(2026, 10, 13)
    assert "col < :hasta" in sql


def test_agregar_filtro_hasta_con_hora_no_se_toca():
    params = {}
    hasta = datetime(2026, 10, 12, 15, 30)
    R._agregar_filtro_hasta("SELECT 1 WHERE 1=1", params, "col < :hasta", hasta)
    assert params["hasta"] == hasta


def test_fuentes_default(monkeypatch):
    assert personas_source() == "F_AP_PERSONA"
    assert componentes_source() == "QUANTUM.VW_SISFALLA_COMPONENTE"


def test_fuentes_identificador_invalido(monkeypatch):
    from app import config

    monkeypatch.setattr(config.get_settings(), "sisfalla_personas_source", "DROP TABLE x")
    with pytest.raises(ValueError):
        personas_source()


def test_norm_dominio():
    from app.sisfalla.dominios import _norm

    assert _norm("Rectificatorio") == "RECTIFICATORIO"
    assert _norm("En Elaboración") == "EN ELABORACION"
    assert _norm(None) == ""
