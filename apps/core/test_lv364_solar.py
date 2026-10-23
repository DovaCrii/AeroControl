"""LV-364: amanecer y puesta calculados en local (NOAA/Meeus), sin red ni dependencias.

Valores de referencia capturados UNA vez de la API de amanecer de MET Norway
(`api.met.no/weatherapi/sunrise/3.0/sun`, 2026-10-23, hora de pared con el desfase indicado). El
módulo NOAA con refracción 0,833° queda a ±1 min de esa fuente; el test tolera 1 minuto y ni uno
más. Las horas se comparan como instantes, así que el cambio de hora de Chile queda cubierto.
"""

import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.core.cache import cache

from apps.core import solar, weather

# (día, latitud, longitud, zona, amanecer MET, puesta MET)
REFERENCE = [
    # Santiago con horario de verano (cambio el 6 de septiembre de 2026).
    (
        date(2026, 9, 15),
        -33.45,
        -70.67,
        "America/Santiago",
        "2026-09-15T07:41-03:00",
        "2026-09-15T19:34-03:00",
    ),
    # Santiago tras volver al horario de invierno (4 de abril de 2026).
    (
        date(2026, 4, 15),
        -33.45,
        -70.67,
        "America/Santiago",
        "2026-04-15T07:04-04:00",
        "2026-04-15T18:19-04:00",
    ),
    (
        date(2026, 6, 21),
        -33.45,
        -70.67,
        "America/Santiago",
        "2026-06-21T07:46-04:00",
        "2026-06-21T17:42-04:00",
    ),
    (
        date(2026, 12, 21),
        -53.16,
        -70.91,
        "America/Punta_Arenas",
        "2026-12-21T05:12-03:00",
        "2026-12-21T22:10-03:00",
    ),
    (
        date(2026, 6, 21),
        -53.16,
        -70.91,
        "America/Punta_Arenas",
        "2026-06-21T09:59-03:00",
        "2026-06-21T17:31-03:00",
    ),
    # Isla de Pascua: en marzo aún rige el horario de verano (-05:00 = 07:21 -06:00 + 1 h).
    (
        date(2026, 3, 20),
        -27.11,
        -109.35,
        "Pacific/Easter",
        "2026-03-20T08:21-05:00",
        "2026-03-20T20:28-05:00",
    ),
]


@pytest.mark.parametrize("day,lat,lon,zone,rise,sett", REFERENCE)
def test_matches_met_norway_reference_within_one_minute(
    day, lat, lon, zone, rise, sett
):
    got = solar.sun_times(day, lat, lon, zone)
    assert got is not None
    for mine, ref in zip(got, (rise, sett), strict=True):
        delta = abs(mine - datetime.fromisoformat(ref))
        assert delta <= timedelta(minutes=1), (mine, ref)
        assert mine.tzinfo is not None


def test_wall_clock_follows_chile_dst():
    """El desfase de la hora de pared cambia entre abril y septiembre."""
    april = solar.sun_times(date(2026, 4, 15), -33.45, -70.67, "America/Santiago")
    september = solar.sun_times(date(2026, 9, 15), -33.45, -70.67, "America/Santiago")
    assert april[0].utcoffset() == timedelta(hours=-4)
    assert september[0].utcoffset() == timedelta(hours=-3)


def test_polar_and_out_of_range_never_invent_an_hour():
    assert solar.sun_times(date(2026, 6, 21), 80.0, 10.0, "UTC") is None
    assert solar.sun_times(date(2026, 6, 21), -85.0, 10.0, "UTC") is None
    assert solar.sun_times(date(2026, 6, 21), "x", 10.0, "UTC") is None
    assert solar.sun_times(date(2026, 6, 21), float("nan"), 10.0, "UTC") is None
    assert solar.sun_times(date(2026, 6, 21), -33.0, 200.0, "UTC") is None


def test_day_rows_get_local_hours_and_input_is_not_mutated():
    rows = [{"time": "2026-09-15", "sunrise": "provider"}, {"time": "garbage"}]
    out = solar.day_rows_with_sun(rows, -33.45, -70.67, "America/Santiago")
    assert out[0]["sunrise"].startswith("2026-09-15T07:4")
    assert out[0]["sunset"].startswith("2026-09-15T19:3")
    assert "sunrise" not in out[1]
    assert rows[0]["sunrise"] == "provider"


def test_polar_day_row_has_none_not_a_made_up_time():
    out = solar.day_rows_with_sun([{"time": "2026-06-21"}], 80.0, 10.0, "UTC")
    assert out[0]["sunrise"] is None and out[0]["sunset"] is None


def test_is_daylight_at_noon_and_midnight():
    noon = datetime(2026, 9, 15, 16, 0, tzinfo=dt_timezone.utc)  # 13:00 -03:00
    night = datetime(2026, 9, 15, 5, 0, tzinfo=dt_timezone.utc)  # 02:00 -03:00
    assert solar.is_daylight(noon, -33.45, -70.67, "America/Santiago") is True
    assert solar.is_daylight(night, -33.45, -70.67, "America/Santiago") is False
    assert solar.is_daylight(noon, 80.0, 10.0, "UTC") is None


def test_panel_forecast_uses_local_sun_not_the_provider_hours(settings, monkeypatch):
    """El pronóstico del panel lleva el sol local aunque el proveedor diga otra cosa."""
    cache.clear()
    settings.WEATHER_ENABLED = True
    settings.WEATHER_API_URL = "https://api.example.test/v1/forecast"
    settings.WEATHER_PROVIDER = "open_meteo"
    fixture = json.loads(
        (weather._FAKE_DIR / "weather_panel_forecast.json").read_text("utf-8")
    )
    fixture["daily"]["sunrise"] = ["2000-01-01T00:00"] * len(fixture["daily"]["time"])

    class Response:
        status = 200

        def read(self, limit=-1):
            return json.dumps(fixture).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        weather.urllib.request, "urlopen", lambda request, timeout=None: Response()
    )
    forecast = weather.panel_forecast(-33.45, -70.67)
    first = forecast["daily"][0]
    assert first["sunrise"].startswith(first["time"][:10])
    assert first["sunrise"] != "2000-01-01T00:00"
    assert first["sunrise"] < first["sunset"]
    cache.clear()
