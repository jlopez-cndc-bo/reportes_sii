"""Constantes de dominio del módulo de indisponibilidades.

Los IDs de tipo de operación provienen de la tabla dc_eventos.id_tipo_operacion
tal como se usaban en el código original (INDISP).
"""
from enum import IntEnum, IntFlag


class TipoOperacion(IntEnum):
    OP_NORMAL = 152      # ONO  - Operación Normal            (parámetro "Opn")
    POT_LIMITADA = 153   # POT LIM - Potencia Limitada        (parámetro "opl")
    PROGRAMADA = 155     # PROG - Indisponibilidad Programada (parámetro "ip")
    FORZADA = 156        # FOR  - Indisponibilidad Forzada    (parámetro "inf")
    PRUEBA = 158         # PRUE - Prueba                       (parámetro "op")
    REPROGRAMACION = 192  # REE  - Reprogramación / Reenganche (parámetro "ore")


# Etiquetas cortas usadas en encabezados (como en el DataGrid original).
# Encabezado de columna en Horas por tipo de operación (columnas «Una por tipo»);
# mismos nombres que las casillas del frontend.
TIPO_OP_LABEL = {
    152: "Operación normal",
    153: "Potencia limitada",
    155: "Programada",
    156: "Forzada",
    158: "Prueba",
    192: "Reprogramación",
}

# Etiqueta larga (usada en Horas de No Disponibilidad).
TIPO_OP_LABEL_LARGO = {
    152: "Op. Normal",
    153: "Pot. Lim",
    155: "Prog",
    156: "Forz",
}


class TipoComponente(IntFlag):
    ALIMENTA = 1
    AUTOTRAN = 2
    CAP_SERIE = 4
    CAP_SHUNT = 8
    GENERADOR = 16
    LINEA = 32
    REACTOR = 64
    TRANSFOR = 128
    TODOS = 255


# cte_elemento en Oracle para cada bit del flag TipoComponente.
COMPONENTE_CTE = {
    TipoComponente.ALIMENTA: "AL",
    TipoComponente.AUTOTRAN: "AUTOTRAN",
    TipoComponente.CAP_SERIE: "CAP-SERIE",
    TipoComponente.CAP_SHUNT: "CAP-SHUNT",
    TipoComponente.GENERADOR: "GENERADOR",
    TipoComponente.LINEA: "LINEA",
    TipoComponente.REACTOR: "REACTOR",
    TipoComponente.TRANSFOR: "TRANSFOR",
}

