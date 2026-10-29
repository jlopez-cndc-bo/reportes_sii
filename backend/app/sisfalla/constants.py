"""Constantes de dominio de SisFalla confirmadas contra Oracle (2026-10-08).

Verificadas empíricamente contra la misma cuenta de solo lectura que usa este
backend (no asumidas del código fuente de SisFalla_30X64, que resuelve
algunas de éstas en runtime porque pueden variar entre entornos Oracle — acá
se confirmó que coinciden en el entorno que lee ReportesSII).
"""

# F_AP_PERSONA.PK_COD_PERSONA del CNDC (sigla 'CNDC').
PK_COD_CNDC = 7

# F_AP_PERSONA.D_COD_TIPO_PERSONA para agentes del SIN. El dominio en
# P_DEF_DOMINIOS dice literalmente "PERSONA JURIDICA", no "Agente" — pero es
# consistente con que los agentes del SIN se registran como personas
# jurídicas (confirmado: 42 filas con este código).
TIPO_PERSONA_AGENTE = 19

# P_DEF_DOMINIOS.D_COD_TIPO_OPERACION de F_GF_OP_INTERRUPTOR (apertura/cierre
# de interruptor). Confirmados MANUAL/AUTOMATICO/REMOTA.
TIPO_OPER_MANUAL = 79
TIPO_OPER_AUTOMATICO = 80
TIPO_OPER_REMOTA = 81
