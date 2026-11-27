"""Informe de Mediano Plazo: reglas puras y comparación contra el estudio real nov/26 - oct/30."""
import io
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

from app.imp import anexos, libro
from app.imp.estudios import Estudio, listar, obtener

DOCS = Path(__file__).resolve().parents[3] / "docs" / "ModuloIMP"


def test_periodo_del_estudio():
    assert Estudio("2026-11", Path(".")).periodo == "nov/26 - oct/30"
    assert Estudio("2027-05", Path(".")).periodo == "may/27 - abr/31"


def test_id_de_estudio_no_admite_rutas(tmp_path):
    (tmp_path / "2026-11").mkdir()
    with pytest.raises(ValueError):
        obtener("../2026-11", tmp_path)
    with pytest.raises(LookupError):
        obtener("2027-05", tmp_path)
    e, anteriores = obtener("2026-11", tmp_path)
    assert e.id == "2026-11" and anteriores == []


def test_valor_csv():
    assert libro.valor("02/07/2026") == datetime(2026, 7, 2)
    assert libro.valor("1,270.30") == 1270.3
    assert libro.valor("3.40%") == pytest.approx(0.034)
    assert libro.valor("2026") == 2026
    assert libro.valor("1.5628 / 9.9236") == "1.5628 / 9.9236"
    assert libro.valor(" ") is None


def test_mantenimientos_se_unen_y_recortan_por_anio():
    filas = [["Unidad", "Inicio", "Fin", "Días"],
             ["GCH10", "01/01/2028", "17/01/2028", "17"],
             ["GCH10", "17/01/2028", "24/01/2028", "8"],      # se superpone: un solo mantenimiento
             ["AGU01", "27/12/2025", "15/06/2026", "171"],    # empieza antes del primer año
             ["AGU01", "01/11/2030", "30/04/2031", "181"]]    # termina después del último
    out = anexos.mantenimientos_por_anio(filas, 2026, 2030)
    assert out[2028] == [("GCH10", datetime(2028, 1, 1), datetime(2028, 1, 24), 24)]
    assert out[2026] == [("AGU01", datetime(2026, 1, 1), datetime(2026, 6, 15), 166)]
    assert out[2030] == [("AGU01", datetime(2030, 11, 1), datetime(2030, 12, 31), 61)]


def test_unidad_normalizada():
    assert anexos._norm_unidad("GCH01") == anexos._norm_unidad("GCH1") == "GCH1"
    assert anexos._norm_unidad("CCERI51") == "CCERI51"


# ------------------------------------------------------------ estudio real (docs/ModuloIMP)

@pytest.fixture(scope="module")
def estudio(tmp_path_factory):
    if not DOCS.is_dir():
        pytest.skip("Sin docs/ModuloIMP (datos reales del estudio nov/26 - oct/30)")
    from PIL import Image
    base = tmp_path_factory.mktemp("imp")
    for n in (2, 4, 5, 6):
        d = base / "2026-11" / f"Anexo{n}"
        d.mkdir(parents=True)
        for f in (DOCS / f"Anexo{n}").iterdir():
            if f.suffix.lower() in (".csv", ".xlsx", ".jpeg", ".png") and not f.name.startswith("~$"):
                shutil.copy(f, d)
    for p in ("Anexo2/Anexo2B.png", "Anexo4/Anexo4B.png"):
        Image.new("RGB", (80, 60), "white").save(base / "2026-11" / p)
    return listar(base)[0]


def _generar(estudio, n):
    data, avisos = anexos.generar(n, estudio, [])
    got = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    exp = openpyxl.load_workbook(DOCS / f"Anexo{n}" / f"ANEXO{n}.xlsx", data_only=True)
    assert got.sheetnames == exp.sheetnames
    return got, exp, avisos


def _difs(a, b):
    norm = lambda v: (" ".join(v.split()) or None) if isinstance(v, str) else v
    out = []
    for r in range(1, max(a.max_row, b.max_row) + 1):
        for c in range(1, max(a.max_column, b.max_column) + 1):
            x, y = norm(a.cell(r, c).value), norm(b.cell(r, c).value)
            # los CSV traen los valores redondeados a la vista de Excel
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and abs(x - y) <= max(0.051, abs(y) * 1e-3):
                continue
            if x != y:
                out.append((a.cell(r, c).coordinate, x, y))
    return out


@pytest.mark.parametrize("n,hojas", [
    (2, ["ANEXO2A", "ANEXO2B"]),
    (4, ["ANEXO4A", "ANEXO4B", "ANEXO4C"]),
    (5, ["ANEXO5B1", "ANEXO5B2", "ANEXO5B3", "ANEXO5B4"]),
    (6, ["ANEXO6A1", "ANEXO6A2", "ANEXO6C", "ANEXO6D1", "ANEXO6E", "ANEXO6F5"]),
])
def test_hojas_identicas_al_informe(estudio, n, hojas):
    got, exp, _ = _generar(estudio, n)
    for h in hojas:
        assert _difs(got[h], exp[h]) == [], h


def test_6c_avisa_columna_sin_bloque(estudio):
    _, _, avisos = _generar(estudio, 6)
    assert any("KAR" in a for a in avisos)


def test_5a_mismos_mantenimientos_por_anio(estudio):
    got, exp, _ = _generar(estudio, 5)

    def items(ws):
        out, anio = {}, None
        for r in ws.iter_rows(values_only=True):
            anio = r[0] if isinstance(r[0], int) else anio
            for b in (1, 6, 11, 16):
                if anio and isinstance(r[b], str) and r[b] != "UNIDAD":
                    out.setdefault(anio, set()).add((r[b], r[b + 1], r[b + 2], r[b + 3]))
        return out

    # En el informe la GP renombró a mano estas unidades del CSV (pendiente de confirmar).
    renombre = {"ERI01": "ERI11", "ERI02": "ERI12", "ERI03": "ERI21", "ERI04": "ERI22", "WAR05": "WAR51"}
    g, x = items(got["ANEXO5A"]), items(exp["ANEXO5A"])
    assert set(g) == set(x) == {2026, 2027, 2028, 2029, 2030}
    for a in g:
        assert {(renombre.get(u, u), *rest) for u, *rest in g[a]} == x[a], a


def test_6g_valores_por_unidad(estudio):
    got, exp, _ = _generar(estudio, 6)

    def bloques(ws):
        out = {}
        for col in (1, 6, 11):
            for r in range(1, ws.max_row + 1):
                v = ws.cell(r, col).value
                if isinstance(v, str) and v.strip()[-1:].isdigit():
                    out[v.strip()] = [[ws.cell(r + k, col + j).value or 0 for j in (1, 2, 3)] for k in range(1, 6)]
        return out

    g, x = bloques(got["ANEXO6G"]), bloques(exp["ANEXO6G"])
    assert set(x) <= set(g)  # el informe de ejemplo omitió unidades; el generador pone todas las del CSV
    for u in x:
        assert g[u] == [pytest.approx(f, abs=0.006) for f in x[u]], u  # el CSV trae de 2 a 5 decimales


def test_encabezado_con_periodo(estudio):
    got, _, _ = _generar(estudio, 4)
    assert got["ANEXO4A"]["I1"].value == "Informe de la Programación de Mediano Plazo nov/26 - oct/30"


def test_faltante_bloquea(tmp_path):
    (tmp_path / "2026-11" / "Anexo4").mkdir(parents=True)
    e = listar(tmp_path)[0]
    est = anexos.estado(4, e, [])
    assert any("ANEXO4.xlsx" in f for f in est["faltan"]) and "Anexo4/ANEXO4C.csv" in est["faltan"]
    with pytest.raises(FileNotFoundError):
        anexos.generar(4, e, [])


def test_sin_vinculos_externos(estudio):
    import zipfile
    data, _ = anexos.generar(5, estudio, [])
    nombres = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert not [n for n in nombres if "externalLink" in n]
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert not [k for k, d in wb.defined_names.items() if "[" in (d.attr_text or "")]
