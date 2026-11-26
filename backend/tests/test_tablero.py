"""Tablero «Monitores»: periodos, uniones de tramos, semáforo, comparaciones, config y disponibilidad."""
import json
from datetime import date, datetime

import pytest

from app.potencia_efectiva import CENTRAL, efectiva
from app.tablero import config as cfgmod
from app.tablero import fuentes as F
from app.tablero import servicio as S
from app.tablero.periodos import Rango, recortar, resolver, ultimos_meses, unir

NOW = datetime(2026, 11, 24, 9, 30)


def test_por_defecto_ultimo_mes_completo_con_comparaciones():
    p = resolver(None, NOW)
    assert (p.id, p.en_curso) == ("2026-10", False)
    assert (p.rango.desde, p.rango.hasta) == (datetime(2026, 10, 1), datetime(2026, 11, 1))
    (_, ant), (_, anio) = p.comparaciones
    assert (ant.desde, ant.hasta) == (datetime(2026, 9, 1), datetime(2026, 10, 1))
    assert (anio.desde, anio.hasta) == (datetime(2025, 10, 1), datetime(2025, 11, 1))


def test_mes_en_curso_termina_ahora_y_compara_el_mismo_tramo():
    p = resolver("mes_en_curso", NOW)
    assert p.en_curso and p.rango.hasta == NOW
    (_, ant), (_, anio) = p.comparaciones
    assert (ant.desde, ant.hasta) == (datetime(2026, 10, 1), datetime(2026, 10, 24, 9, 30))
    assert anio.hasta == datetime(2025, 11, 24, 9, 30)


def test_ayer_y_tramo_recortado_al_largo_del_mes():
    p = resolver("ayer", datetime(2026, 3, 31, 8))
    assert (p.rango.desde, p.rango.hasta) == (datetime(2026, 3, 30), datetime(2026, 3, 31))
    # 31/03 en curso → mismo tramo de febrero termina el 28/02.
    q = resolver("mes_en_curso", datetime(2026, 3, 31, 8))
    assert q.comparaciones[0][1].hasta == datetime(2026, 2, 28, 8)


@pytest.mark.parametrize("malo", ["2026-13", "hoy", "2027-01"])
def test_periodo_invalido_o_futuro(malo):
    with pytest.raises(ValueError):
        resolver(malo, NOW)


def test_ultimos_meses_el_ultimo_puede_estar_en_curso():
    m = ultimos_meses(NOW, 12, NOW)
    assert len(m) == 12 and m[0].etiqueta == "dic-2025" and m[-1].etiqueta == "nov-2026"
    assert m[-1].hasta == NOW


def test_unir_no_cuenta_doble_y_recorta_al_rango():
    a, b, c = datetime(2026, 1, 1, 0), datetime(2026, 1, 1, 6), datetime(2026, 1, 1, 12)
    assert unir([(b, c), (a, b), (a, datetime(2026, 1, 1, 8))]) == [(a, c)]
    r = Rango(datetime(2026, 1, 1, 3), datetime(2026, 1, 1, 9), "")
    assert recortar(a, c, r) == 6
    assert recortar(datetime(2026, 1, 2), datetime(2026, 1, 3), r) == 0


def _cfg(**cambios):
    base = json.loads(cfgmod._DEFAULT.read_text(encoding="utf-8"))
    base.update(cambios)
    return cfgmod.Config.model_validate(base)


def test_config_del_repo_es_valida():
    cfg = cfgmod.cargar()
    assert cfg.indicador("SIN-01").nombre == "Potencia de punta"
    assert cfg.umbrales == []  # D-H: arranca sin metas


def test_config_rechaza_metrica_o_referencia_inexistente():
    base = json.loads(cfgmod._DEFAULT.read_text(encoding="utf-8"))
    base["indicadores"][0]["metrica"] = "no_existe"
    with pytest.raises(ValueError, match="métrica desconocida"):
        cfgmod.Config.model_validate(base)
    with pytest.raises(ValueError, match="inexistente"):
        _cfg(umbrales=[{"kpi_id": "X-1", "vigente_desde": "2027-01-01", "meta": 1, "verde": 1,
                        "ambar": 0, "aprobado_por": "Gerencia"}])


def test_semaforo_sin_umbral_es_meta_por_definir_y_con_umbral_respeta_direccion():
    cfg = _cfg()
    assert S.semaforo(99.0, cfg.indicador("OP-01"), cfg, date(2027, 2, 1)) is None
    cfg = _cfg(umbrales=[
        {"kpi_id": "OP-01", "vigente_desde": "2027-01-01", "meta": 95, "verde": 95, "ambar": 90,
         "aprobado_por": "Gerencia de Operaciones"},
        {"kpi_id": "RF-01", "vigente_desde": "2027-01-01", "meta": 50, "verde": 50, "ambar": 80,
         "aprobado_por": "Gerencia de Operaciones"}])
    op, rf = cfg.indicador("OP-01"), cfg.indicador("RF-01")
    assert S.semaforo(92.0, op, cfg, date(2027, 2, 1))["estado"] == "ambar"
    assert S.semaforo(92.0, op, cfg, date(2026, 12, 1)) is None  # umbral aún no vigente
    assert S.semaforo(40.0, rf, cfg, date(2027, 2, 1))["estado"] == "verde"
    assert S.semaforo(90.0, rf, cfg, date(2027, 2, 1))["estado"] == "rojo"


def test_comparar_relativa_puntos_y_sentido():
    cfg = _cfg()
    assert S.comparar(110, 100, cfg.indicador("SIN-02")) == {"delta": 10.0, "mejor": True}
    assert S.comparar(110, 100, cfg.indicador("RF-01"))["mejor"] is False
    assert S.comparar(90.5, 92.0, cfg.indicador("OP-01")) == {"delta": -1.5, "mejor": False}
    assert S.comparar(5, 0, cfg.indicador("RF-01")) is None
    assert S.comparar(None, 3, cfg.indicador("RF-01")) is None


def test_alertas_hfd_atrasado_y_pef_por_vencer():
    cfg = _cfg()
    hfd = {"fecha_dato": "2026-11-24T08:30:00", "congeladas": [{"unidad": "QOL01"}]}
    textos = [a["texto"] for a in S.alertas(hfd, date(2026, 11, 23), datetime(2026, 11, 24, 9, 30), cfg)]
    assert any("atrasada" in t and "45 min" in t for t in textos)
    assert any("1 señal" in t for t in textos)
    textos = [a["texto"] for a in S.alertas(None, date(2027, 4, 9), datetime(2027, 4, 10, 9), cfg)]
    assert any("vence el 30/04/2027" in t for t in textos)


def test_disponibilidad_pondera_por_potencia_efectiva(monkeypatch):
    d = datetime(2026, 11, 10)
    ev = [{"cod": "GCH11", "tipo": F.FORZADA, "ini": d, "fin": d.replace(hour=12), "causa": ""},
          # Un 155 superpuesto en la misma unidad no cuenta doble.
          {"cod": "GCH11", "tipo": F.PROGRAMADA, "ini": d.replace(hour=6), "fin": d.replace(hour=12),
           "causa": ""},
          {"cod": "ERI31", "tipo": F.FORZADA, "ini": d, "fin": d.replace(hour=1), "causa": ""}]
    monkeypatch.setattr(F, "_eventos", lambda *a: ev)
    r = Rango(d, d.replace(day=11), "")
    p = F.op_disponibilidad(r, NOW)
    total = sum(efectiva(c, d.date()) or 0 for c in CENTRAL)
    esperado = (1 - efectiva("GCH11", d.date()) * 12 / (total * 24)) * 100
    assert p["valor"] == pytest.approx(esperado)
    assert "1 estado(s) de ciclo combinado" in p["nota"]


def test_disponibilidad_sin_potencia_efectiva_vigente_es_guion():
    p = F.op_disponibilidad(Rango(datetime(2026, 10, 1), datetime(2026, 11, 1), ""), NOW)
    assert p["valor"] is None and "01/10/2026" in p["nota"]


def test_indisponibles_dia_suma_por_tipo_sin_contar_doble(monkeypatch):
    d = datetime(2026, 11, 20)
    ev = [{"cod": "GCH11", "tipo": F.FORZADA, "ini": d.replace(hour=2), "fin": d.replace(hour=5), "causa": ""},
          {"cod": "GCH11", "tipo": F.FORZADA, "ini": d.replace(hour=4), "fin": d.replace(hour=6), "causa": ""},
          {"cod": "GCH11", "tipo": F.PROGRAMADA, "ini": d.replace(hour=10), "fin": d.replace(hour=11), "causa": ""}]
    monkeypatch.setattr(F, "_eventos", lambda *a: ev)
    u = F.indisponibles_dia(d.date(), NOW)["unidades"]
    assert len(u) == 1
    assert (u[0]["horas_forzada"], u[0]["horas_programada"]) == (4.0, 1.0)
    assert u[0]["mw"] == efectiva("GCH11", d.date())


def test_dia_rechaza_fecha_futura_o_mal_escrita():
    with pytest.raises(ValueError):
        S.dia("2999-01-01")
    with pytest.raises(ValueError):
        S.dia("20-11-2026")
