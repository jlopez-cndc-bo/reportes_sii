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
TIPO_OP_LABEL = {
    152: "ONO",
    153: "POT LIM",
    155: "PROG",
    156: "FOR",
    158: "PRUE",
    192: "REE",
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
    TipoComponente.ALIMENTA: "ALIMENTA",
    TipoComponente.AUTOTRAN: "AUTOTRAN",
    TipoComponente.CAP_SERIE: "CAP-SERIE",
    TipoComponente.CAP_SHUNT: "CAP-SHUNT",
    TipoComponente.GENERADOR: "GENERADOR",
    TipoComponente.LINEA: "LINEA",
    TipoComponente.REACTOR: "REACTOR",
    TipoComponente.TRANSFOR: "TRANSFOR",
}


class NivelReporte(str):
    """Nivel de agrupación de Potencias Disponibles."""


# Resolución temporal para reportes pivoteados (Potencias Indisponibles).
class Resolucion(IntEnum):
    INTERVALO = 1  # columnas por intervalo de N minutos
    HORA = 2       # columnas por hora
    DIA = 3        # columnas por día
