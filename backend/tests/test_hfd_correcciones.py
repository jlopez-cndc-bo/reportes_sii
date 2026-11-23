"""Correcciones HFD: sesión de editores (AD), guardar, propuesta SMEC y marcas."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import oracledb
import pytest
from fastapi import Response

from app import sesion
from app.config import get_settings
from app.hfd import correcciones as K
from app.hfd import registros as R

AYER = date.today() - timedelta(days=1)


@pytest.fixture(autouse=True)
def editores(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "hfd_editores", {"jlopez", "wbarron"})
    monkeypatch.setattr(s, "session_secret", "secreto-de-prueba")
    monkeypatch.setattr(s, "session_minutes", 60)


# ───────────────────────────── sesión ─────────────────────────────

@pytest.mark.parametrize("entrada", ["jlopez", "JLopez", "CNDC\\jlopez", "jlopez@cndc.bo", " jlopez "])
def test_normalizar_usuario(entrada):
    assert sesion.normalizar_usuario(entrada) == "jlopez"


def test_token_valido_alterado_vencido_y_revocado(monkeypatch):
    t = sesion.crear_token("jlopez")
    assert sesion.leer_token(t) == "jlopez"
    assert sesion.leer_token(t[:-4] + "AAAA") is None            # alterado
    assert sesion.leer_token("basura") is None
    assert sesion.leer_token(t, ahora=datetime.now().timestamp() + 61 * 60) is None  # vencido
    monkeypatch.setattr(get_settings(), "hfd_editores", {"wbarron"})
    assert sesion.leer_token(t) is None                           # sacado de la lista


def test_iniciar_rechaza_caracteres_y_no_autorizados(monkeypatch):
    llamado = []
    monkeypatch.setattr(sesion, "verificar_ad", lambda u, p: llamado.append(u))
    with pytest.raises(sesion.CredencialesInvalidas):
        sesion.iniciar("jlopez)(|(cn=*", "x", Response())          # inyección LDAP
    assert llamado == []
    with pytest.raises(sesion.NoAutorizado):
        sesion.iniciar("otro", "x", Response())
    r = Response()
    assert sesion.iniciar("CNDC\\wbarron", "x", r) == "wbarron"
    assert "hfd_sesion=" in r.headers["set-cookie"] and "httponly" in r.headers["set-cookie"].lower()


def test_contrasena_vacia_nunca_llega_al_directorio():
    with pytest.raises(sesion.CredencialesInvalidas):
        sesion.verificar_ad("jlopez", "")


# ──────────────────────────── guardar ────────────────────────────

@pytest.mark.parametrize("kw,msg", [
    ({"fecha": date.today()}, "días cerrados"),
    ({"fecha": date.today() - timedelta(days=40)}, "últimos"),
    ({"motivo": "corto"}, "motivo"),
    ({"archivo": "transferencias"}, "Generadores"),
    ({"el": "U"}, "Magnitud"),
    ({"cambios": [{"intervalo": 96, "valor": 1.0}]}, "Intervalo"),
    ({"cambios": [{"intervalo": 5, "valor": 1.0}, {"intervalo": 5, "valor": 2.0}]}, "repetido"),
    ({"cambios": []}, "No hay valores"),
])
def test_guardar_valida(kw, msg):
    args = {"usuario": "jlopez", "archivo": "generadores", "id_obj": 8134, "el": "P", "fecha": AYER,
            "cambios": [{"intervalo": 56, "valor": 1.4}], "motivo": "señal congelada en SCADA"}
    args.update(kw)
    with pytest.raises(ValueError, match=msg):
        K.guardar(**args)


class CursorFalso:
    def __init__(self, actual, vigentes):
        self.lotes = [list(actual.items()), list(vigentes.items())]
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.lotes.pop(0)


def test_guardar_anula_e_inserta_con_el_valor_original_del_hfd(monkeypatch):
    # Intervalo 56 ya corregido (la tabla TDM tiene el corregido 1.4; el HFD traía 0.3);
    # intervalo 57 sin corregir (la tabla TDM tiene el del HFD, 0.3).
    cur = CursorFalso(actual={56: 1.4, 57: 0.3}, vigentes={56: 0.3})

    @contextmanager
    def transaccion():
        yield cur
    monkeypatch.setattr(K, "transaccion", transaccion)

    n = K.guardar("jlopez", "generadores", 8134, "P", AYER,
                  [{"intervalo": 56, "valor": 1.5, "fuente": "SMEC"},
                   {"intervalo": 57, "valor": 1.2, "fuente": "MANUAL"},
                   {"intervalo": 58, "valor": None}], "QOL01 congelada desde el 16-nov")
    assert n == 3
    inserts = [p for s, p in cur.sql if s.startswith("INSERT")]
    updates = [p for s, p in cur.sql if s.startswith("UPDATE")]
    assert len(updates) == 3                       # cada intervalo anula la vigente anterior
    assert [(p["i"], p["vo"], p["v"], p["fu"]) for p in inserts] == [
        (56, 0.3, 1.5, "SMEC"),                    # el original es el del HFD, no el corregido
        (57, 0.3, 1.2, "MANUAL"),
    ]                                              # el 58 (valor None) sólo se anula
    assert all(p["u"] == "jlopez" for p in updates + inserts)


# ─────────────────────── SMEC, marcas y recarga ───────────────────────

def test_propuesta_smec_convierte_kw_a_mw_aplica_factor_y_alinea(monkeypatch):
    monkeypatch.setattr(K, "query", lambda sql, p: [{"codigo_objeto": "1011"}] if "objetos" in sql else
                        [{"intervalo": 1, "potencia": 2900.0}, {"intervalo": 96, "potencia": 1000.0}])
    r = K.propuesta_smec(8134, AYER)
    assert r["medidor"] == 8159 and r["codigo"] == "1011"
    assert r["valores"][0] == 1.45 and r["valores"][95] == 0.5 and r["valores"][1] is None


def test_propuesta_smec_sin_medidor():
    assert K.propuesta_smec(1, AYER) == {"medidor": None, "valores": None}


def test_vigentes_sin_tabla_no_rompe_los_reportes(monkeypatch):
    def falla(sql, p):
        raise oracledb.DatabaseError("ORA-00942: table or view does not exist")
    monkeypatch.setattr(K, "query", falla)
    assert K.vigentes("generadores", AYER, AYER) == {}
    assert K.vigentes("tensiones", AYER, AYER) == {}


def test_registros_marca_las_celdas_corregidas(monkeypatch):
    fila = {"fecha": datetime.combine(AYER, datetime.min.time()), "estacion": "QOLLPANA", "tension": "25",
            "elemento": "GE01_", "magnitud": "P", "id": 8134, **{f"p{i}": 0.3 for i in range(96)}}
    monkeypatch.setattr(R, "query", lambda sql, p=None: [] if "all_tables" in sql else [fila])
    corr = {"valor": 1.4, "valor_original": 0.3, "fuente": "SMEC", "motivo": "congelada",
            "usuario": "jlopez", "fecha_registro": datetime(2026, 11, 20, 9, 14)}
    monkeypatch.setattr(K, "vigentes", lambda a, d, h: {(AYER.isoformat(), 8134, "P", 56): corr})
    row = R.registros("generadores", "P", AYER, AYER)["rows"][0]
    assert list(row["_corr"]) == ["p56"]
    assert "jlopez" in row["_corr"]["p56"] and "0,30" in row["_corr"]["p56"]


def test_recargar_sin_etl_avisa_y_cierra(monkeypatch):
    monkeypatch.setattr(get_settings(), "rs7_reprocess_url", "http://127.0.0.1:9/api/reprocess")
    eventos = list(K.recargar_dia(AYER))
    assert eventos[0].startswith("data: ✗ No se pudo contactar el ETL")
    assert eventos[-1] == "data: [FIN]\n\n"
