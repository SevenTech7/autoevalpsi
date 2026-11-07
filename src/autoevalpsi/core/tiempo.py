"""Hora de Bolivia (America/La_Paz): UTC−4 todo el año, sin horario de verano.

Es un desfase fijo a propósito: así no depende de la base de zonas horarias del sistema (Windows
no la trae para Python) y la hora no cambia según dónde esté la laptop. Solo biblioteca estándar.
"""

from datetime import date, datetime, timedelta, timezone

ZONA_BOLIVIA = timezone(timedelta(hours=-4), "Bolivia")


def ahora_bolivia() -> datetime:
    """El momento actual en hora de Bolivia (con zona)."""
    return datetime.now(ZONA_BOLIVIA)


def hoy_bolivia() -> date:
    """La fecha de hoy en Bolivia (no la de UTC: después de las 20:00 serían días distintos)."""
    return ahora_bolivia().date()


def a_bolivia(momento: datetime) -> datetime:
    """`momento` en hora de Bolivia; si no trae zona se toma como ya dada en Bolivia."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=ZONA_BOLIVIA)
    return momento.astimezone(ZONA_BOLIVIA)
