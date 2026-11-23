"""Tests de funciones puras del módulo SCADA HFD (sin BD)."""
from datetime import date

import pytest

from app.hfd import registros as R


def test_etiquetas_como_el_archivo_hfd():
    assert R.etiqueta_intervalo(0) == "00:00"
    assert R.etiqueta_intervalo(4) == "01:00"
    assert R.etiqueta_intervalo(95) == "23:45"


def test_validar_rango_limites():
    R.validar_rango(date(2026, 11, 1), date(2026, 11, 1))  # un solo día
    R.validar_rango(date(2026, 10, 1), date(2026, 10, 31))  # 31 días: justo el máximo
    with pytest.raises(ValueError, match="31 días"):
        R.validar_rango(date(2026, 10, 1), date(2026, 11, 1))
    with pytest.raises(ValueError, match="anterior"):
        R.validar_rango(date(2026, 11, 2), date(2026, 11, 1))


def test_archivo_desconocido():
    with pytest.raises(ValueError, match="desconocido"):
        R.registros("ge30; DROP TABLE x", "P", date(2026, 11, 1), date(2026, 11, 1))


def test_sql_sin_horizontal_lee_solo_la_vertical():
    sql = R._sql("TDM_GE30_SP7", None)
    assert "TDM_GE30_DIA" not in sql
    assert "UNION ALL" not in sql
    # Formato del archivo HFD: el día es fecha_sng y el intervalo 0 es su 00:00.
    assert "DECODE" not in sql
    assert "FOR intervalo IN (0 AS p0," in sql and "95 AS p95)" in sql


def test_sql_con_horizontal_no_duplica_dias():
    sql = R._sql("TDM_GE30_SP7", "TDM_GE30_DIA")
    assert "UNION ALL" in sql
    assert "fecha NOT IN (SELECT fecha FROM spectrum.TDM_GE30_DIA" in sql


def test_sql_usa_binds_y_no_valores():
    sql = R._sql("TDM_TD30_SP7", None)
    for b in (":magnitud", ":desde", ":hasta", ":tabla", ":estacion"):
        assert b in sql


def test_totales_solo_en_generadores(monkeypatch):
    monkeypatch.setattr(R, "_horizontal_existe", lambda t: False)
    monkeypatch.setattr(R, "query", lambda sql, p=None: [])
    d = date(2026, 11, 17)
    gen = R.registros("generadores", "P", d, d)["columns"]
    tra = R.registros("transferencias", "P", d, d)["columns"]
    assert not any(c.get("sinTotal") for c in gen if c["key"].startswith("p"))
    assert all(c.get("sinTotal") for c in tra if c["key"].startswith("p"))
    assert gen[0]["key"] == "estacion"  # columna fija al desplazarse


def test_columnas_00_a_2345():
    import app.hfd.registros as M
    M_query, M_h = M.query, M._horizontal_existe
    try:
        M.query = lambda sql, p=None: []
        M._horizontal_existe = lambda t: False
        cols = [c["label"] for c in M.registros("generadores", "P", date(2026, 11, 17), date(2026, 11, 17))["columns"]
                if c["key"].startswith("p")]
    finally:
        M.query, M._horizontal_existe = M_query, M_h
    assert len(cols) == 96 and cols[0] == "00:00" and cols[-1] == "23:45"


# ───────────────────────────── consolidados ─────────────────────────────
from app.hfd import consolidados as C


def test_clasificar_prioriza_aux_y_cae_a_tipo_obj():
    assert C.clasificar("BAGAZO", "TG") == "BAGAZO"   # Aguaí: TG en objetos, bagazo en HFD
    assert C.clasificar("EOL", "INT") == "EOL"
    assert C.clasificar("HID", "HID") == "HIDRO"
    assert C.clasificar(None, "TG") == "TERMO"
    assert C.clasificar(None, "TDF") == "TERMO"
    assert C.clasificar(None, "INT") == "RENO"
    assert C.clasificar(None, "ARG") == "EXPORT"
    assert C.clasificar(None, None) == "SIN_CLASIF"


def test_sumar_respeta_vacios():
    a = [None] * 96
    b = [None] * 96
    a[0], b[0], b[1] = 1.5, 2.0, -1.0
    s = C.sumar([a, b])
    assert s[0] == 3.5 and s[1] == -1.0 and s[2] is None


def test_arbol_en_orden_con_niveles():
    hojas = [(("TERMO", "CT A", "U1"), {"v": 1}), (("TERMO", "CT A", "U2"), {"v": 2}),
             (("HIDRO", "CH B", "U3"), {"v": 4})]
    filas = C._arbol(hojas, lambda hs: {"v": sum(h["v"] for h in hs)})
    assert [(f["nombre"], f["_nivel"], f["v"]) for f in filas] == [
        ("TERMO", 0, 3), ("CT A", 1, 3), ("U1", 2, 1), ("U2", 2, 2),
        ("HIDRO", 0, 4), ("CH B", 1, 4), ("U3", 2, 4)]


def test_indicadores_energia_mwh():
    vals = [None] * 96
    vals[10], vals[11] = 100.0, 200.0
    ind = C._indicadores(vals)
    assert ind["maximo"] == 200.0 and ind["hora_max"] == "02:45" and ind["energia"] == 75.0


def test_bancos_no_suma_en_total(monkeypatch):
    monkeypatch.setattr(R, "_horizontal_existe", lambda t: False)
    monkeypatch.setattr(R, "query", lambda sql, p=None: [])
    d = date(2026, 11, 17)
    cols = R.registros("bancos", "CB", d, d)["columns"]
    assert all(c.get("sinTotal") for c in cols if c["key"].startswith("p"))


def test_tabla_sin_cargar_da_mensaje_claro(monkeypatch):
    import oracledb

    def falla(sql, p=None):
        raise oracledb.DatabaseError("ORA-00942: table or view does not exist")
    monkeypatch.setattr(R, "_horizontal_existe", lambda t: False)
    monkeypatch.setattr(R, "query", falla)
    d = date(2026, 11, 17)
    with pytest.raises(ValueError, match="todavía no hay datos"):
        R.registros("bancos", "CB", d, d)
