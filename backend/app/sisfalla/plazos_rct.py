"""Plazos del Reglamento de Calidad de Transmisión (RCT) para informes de falla.

Igual que SisFalla_30X64/Web/SisFallaApiPy/core/plazos_rct.py: informe
preliminar a 48 horas de la falla y final a 8 días hábiles (lunes a viernes;
no hay tabla de feriados, así que un feriado entre semana no se descuenta).
"""
from datetime import date, datetime, timedelta

MARGEN_PRELIMINAR = timedelta(hours=12)  # último cuarto de las 48 h
MARGEN_FINAL = timedelta(days=2)


def plazo_preliminar(inicio: datetime) -> datetime:
    return inicio + timedelta(hours=48)


def plazo_final(inicio: datetime) -> datetime:
    dia: date = inicio.date()
    habiles = 0
    while habiles < 8:
        dia += timedelta(days=1)
        habiles += dia.weekday() < 5
    return datetime(dia.year, dia.month, dia.day, 23, 59, 59)


def estado(plazo: datetime, enviado: datetime | None, ahora: datetime,
           margen: timedelta = MARGEN_PRELIMINAR) -> str:
    if enviado is not None:
        return "Enviado a tiempo" if enviado <= plazo else "Enviado con retraso"
    if ahora > plazo:
        return "Vencido"
    return "Por vencer" if plazo - ahora <= margen else "En plazo"
