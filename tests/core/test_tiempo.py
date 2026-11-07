"""Hora de Bolivia: UTC−4 fijo."""

from datetime import UTC, datetime, timedelta

from autoevalpsi.core import tiempo
from autoevalpsi.core.tiempo import ZONA_BOLIVIA, a_bolivia, ahora_bolivia, hoy_bolivia


def test_bolivia_es_utc_menos_4():
    assert ZONA_BOLIVIA.utcoffset(None) == timedelta(hours=-4)
    assert ahora_bolivia().utcoffset() == timedelta(hours=-4)


def test_a_bolivia_convierte_y_conserva_el_instante():
    utc = datetime(2026, 11, 8, 2, 35, tzinfo=UTC)
    local = a_bolivia(utc)
    assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 11, 7, 22, 35)
    assert local == utc  # es el mismo instante


def test_sin_zona_se_toma_como_hora_de_bolivia():
    local = a_bolivia(datetime(2026, 11, 7, 9, 0))
    assert local.hour == 9 and local.utcoffset() == timedelta(hours=-4)


def test_hoy_es_el_dia_de_bolivia_no_el_de_utc(monkeypatch):
    # 02:35 UTC del 8 es todavía el 7 a las 22:35 en Bolivia
    monkeypatch.setattr(
        tiempo, "ahora_bolivia", lambda: a_bolivia(datetime(2026, 11, 8, 2, 35, tzinfo=UTC))
    )
    assert hoy_bolivia().isoformat() == "2026-11-07"
