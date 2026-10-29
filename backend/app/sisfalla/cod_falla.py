"""Composición/descomposición de PK_COD_FALLA (código compuesto año+número).

`descomponer_cod_falla` está portada tal cual de SisFalla_30X64
(core/cod_falla.py) — mismo formato que usa el resto del sistema
(PK_COD_FALLA = (gestión-2000)*10000 + nroFalla).
"""
from typing import Any


def descomponer_cod_falla(cod_falla: Any, gestion: int | None = None) -> dict:
    if cod_falla is None:
        texto = ""
    else:
        # int() normaliza float/Decimal (oracledb puede devolver PK_COD_FALLA
        # sin escala fija) truncando la parte fraccionaria antes de extraer
        # dígitos; también evita que cod_falla=0 (falsy) se trate como vacío.
        try:
            texto = str(int(cod_falla))
        except (TypeError, ValueError):
            texto = str(cod_falla).strip()

    digitos = "".join(ch for ch in texto if ch.isdigit())
    if not digitos:
        return {
            "codFalla": cod_falla,
            "codFallaTexto": texto,
            "gestion": gestion,
            "nroFalla": None,
        }

    gestion_inferida = None
    if len(digitos) > 4:
        gestion_inferida = 2000 + int(digitos[:-4])

    gestion_full = gestion_inferida
    if gestion_full is None and gestion is not None:
        gestion_full = 2000 + int(gestion) if int(gestion) < 100 else int(gestion)

    nro_falla = int(digitos[-4:]) if len(digitos) >= 4 else int(digitos)
    cod_falla_texto = f"{nro_falla}/{gestion_full}" if gestion_full else texto
    return {
        "codFalla": int(digitos),
        "codFallaTexto": cod_falla_texto,
        "gestion": gestion_full,
        "nroFalla": nro_falla,
    }


def resolver_cod_falla(valor: Any) -> int | None:
    """Acepta el formato visible ('247/2026', '0247-26') además del código
    compuesto directo, y devuelve siempre PK_COD_FALLA. Usado como validador
    de entrada en los schemas de la API: el usuario ve/escribe nro+gestión
    (igual que SisFallaV3), no el código interno."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, int):
        return valor
    texto = str(valor).strip()
    if not texto:
        return None
    for sep in ("/", "-"):
        if sep in texto:
            nro_str, gestion_str = texto.split(sep, 1)
            nro = int(nro_str.strip())
            gestion = int(gestion_str.strip())
            gestion_full = gestion + 2000 if gestion < 100 else gestion
            return (gestion_full - 2000) * 10000 + nro
    # Sin separador: ya es el código compuesto (compatibilidad con scripts
    # internos existentes que mandaban el PK_COD_FALLA directo).
    return int(texto)
