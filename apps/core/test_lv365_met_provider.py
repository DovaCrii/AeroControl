"""LV-365: MET Norway como proveedor por omisión (la API gratuita de Open-Meteo es no comercial).

Sin red: `urlopen` se sustituye y la respuesta es INVENTADA con la forma real de
`locationforecast/2.0/complete` (medida el 2026-10-23: 88 pasos, horarios las primeras ~60 h y cada
6 h después, sin ráfagas, probabilidad de precipitación ni visibilidad fuera de los países nórdicos).
"""

import json
import logging
import urllib.error
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from email.message import Message
from email.utils import format_datetime

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.core import solar, weather, weather_met

UA = "test-agent (test-contact)"
START = datetime(2026, 10, 23, 11, 0, tzinfo=dt_timezone.utc)
SYMBOLS = (
    "clearsky_day",
    "partlycloudy_day",
    "cloudy",
    "lightrain",
    "rain",
    "fair_night",
)


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def met_payload(wind=3.0, gusts=None, probability=None):
    """88 pasos como los reales: 61 horarios y 27 de 6 h. Valores inventados y deterministas."""
    steps = []
    moment = START
    for index in range(88):
        hourly = index <= 60
        instant = {
            "air_pressure_at_sea_level": 1015.0,
            "air_temperature": 10.0 + (index % 12),
            "apparent_air_temperature": 9.0 + (index % 12),
            "cloud_area_fraction": float((index * 7) % 100),
            "relative_humidity": 60.0,
            "ultraviolet_index_clear_sky": 5.0,
            "wind_from_direction": 220.0,
            "wind_speed": wind,
        }
        if gusts is not None:
            instant["wind_speed_of_gust"] = gusts
        data = {"instant": {"details": instant}}
        symbol = SYMBOLS[index % len(SYMBOLS)]
        if hourly:
            details = {"precipitation_amount": 0.5 if index % 5 == 0 else 0.0}
            if probability is not None:
                details["probability_of_precipitation"] = probability
            data["next_1_hours"] = {
                "summary": {"symbol_code": symbol},
                "details": details,
            }
        if index % 6 == 0 or not hourly:
            data["next_6_hours"] = {
                "summary": {"symbol_code": symbol},
                "details": {
                    "air_temperature_max": 25.0,
                    "air_temperature_min": 5.0,
                    "precipitation_amount": 2.0,
                },
            }
        steps.append({"time": _iso(moment), "data": data})
        moment += timedelta(hours=1) if hourly else timedelta(hours=6)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-70.67, -33.45, 547]},
        "properties": {
            "meta": {"updated_at": "2026-10-23T09:17:51Z"},
            "timeseries": steps,
        },
    }


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self, limit=-1):
        return self._body[:limit] if limit >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code):
    return urllib.error.HTTPError("https://x.test", code, "msg", Message(), None)


@pytest.fixture(autouse=True)
def met(settings):
    cache.clear()
    settings.WEATHER_ENABLED = True
    settings.WEATHER_PROVIDER = "met_norway"
    settings.WEATHER_USER_AGENT = UA
    settings.WEATHER_API_KEY = ""
    settings.WEATHER_API_URL = "https://api.example.test/locationforecast/complete"
    settings.WEATHER_PANEL_CACHE_SECONDS = 1800
    yield settings
    cache.clear()


def serve(monkeypatch, *replies):
    """Reemplaza urlopen: devuelve (o lanza) las respuestas en orden. Registra las peticiones."""
    sent = []
    queue = list(replies)

    def fake(request, timeout=None):
        sent.append(request)
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(weather.urllib.request, "urlopen", fake)
    return sent


def ok(payload=None, **headers):
    return FakeResponse(payload or met_payload(), headers=headers)


class TestSymbols:
    @pytest.mark.parametrize(
        "symbol,code",
        [
            ("clearsky_day", 0),
            ("clearsky_night", 0),
            ("fair_polartwilight", 1),
            ("partlycloudy_day", 2),
            ("cloudy", 3),
            ("fog", 45),
            ("lightrain", 61),
            ("rain", 63),
            ("heavyrain", 65),
            ("rainshowers_day", 81),
            ("lightsnow", 71),
            ("snow", 73),
            ("heavysnow", 75),
            ("rainandthunder", 95),
            ("heavysnowshowersandthunder_night", 95),
        ],
    )
    def test_symbol_to_wmo(self, symbol, code):
        assert weather_met.wmo_for_symbol(symbol) == code

    @pytest.mark.parametrize("symbol", [None, "", "unicorn_day", 7])
    def test_unknown_is_none_never_a_guess(self, symbol):
        assert weather_met.wmo_for_symbol(symbol) is None

    def test_every_mapped_code_belongs_to_a_known_condition(self):
        for code in weather_met.SYMBOL_TO_WMO.values():
            assert weather.condition_for(code) is not None


class TestZone:
    def test_a_valid_hint_wins(self):
        assert weather_met.zone_for(-33.4, -70.6, "Europe/Oslo") == "Europe/Oslo"

    @pytest.mark.parametrize(
        "lat,lon,zone",
        [
            (-33.45, -70.67, "America/Santiago"),
            (-53.16, -70.91, "America/Punta_Arenas"),
            (-27.11, -109.35, "Pacific/Easter"),
            (59.9, 10.7, "UTC"),
        ],
    )
    def test_chile_by_coordinates_else_utc(self, lat, lon, zone):
        assert weather_met.zone_for(lat, lon, "not-a-zone") == zone


@pytest.mark.django_db
class TestAdapter:
    def forecast(self, monkeypatch, **kw):
        serve(monkeypatch, ok(met_payload(**kw)))
        return weather.panel_forecast(-33.45, -70.67, "America/Santiago")

    def test_it_has_the_same_shape_as_the_open_meteo_parse(self, monkeypatch):
        parsed = self.forecast(monkeypatch)
        assert {"current", "hourly", "daily", "units", "timezone", "fetched_at"} <= set(
            parsed
        )
        assert parsed["timezone"] == "America/Santiago"
        assert len(parsed["hourly"]) == 48 and len(parsed["daily"]) == 7
        assert set(parsed["hourly"][0]) == set(weather.PANEL_HOURLY_FIELDS) | {"time"}
        assert set(parsed["daily"][0]) == set(weather.PANEL_DAILY_FIELDS) | {"time"}
        assert set(parsed["current"]) == set(weather.PANEL_CURRENT_FIELDS)
        assert parsed["units"]["wind_speed_10m"] == "m/s"
        assert parsed["provider"] == "met_norway"

    def test_utc_becomes_local_wall_clock(self, monkeypatch):
        first = self.forecast(monkeypatch)["hourly"][0]
        # 11:00 UTC del 23 de octubre de 2026 = 08:00 en Santiago (horario de verano, -03:00).
        assert first["time"] == "2026-10-23T08:00"

    def test_what_met_does_not_give_stays_none_and_is_declared(self, monkeypatch):
        parsed = self.forecast(monkeypatch)
        assert all(h["wind_gusts_10m"] is None for h in parsed["hourly"])
        assert all(h["visibility"] is None for h in parsed["hourly"])
        assert all(h["precipitation_probability"] is None for h in parsed["hourly"])
        assert all(d["wind_gusts_10m_max"] is None for d in parsed["daily"])
        assert all(d["precipitation_probability_max"] is None for d in parsed["daily"])
        assert all(d["uv_index_max"] is None for d in parsed["daily"])
        assert parsed["current"]["wind_gusts_10m"] is None
        assert parsed["unavailable"] == ["gusts", "visibility", "rain_probability"]

    def test_nordic_extras_are_used_when_present(self, monkeypatch):
        parsed = self.forecast(monkeypatch, gusts=11.0, probability=40.0)
        assert parsed["hourly"][0]["wind_gusts_10m"] == 11.0
        assert parsed["hourly"][0]["precipitation_probability"] == 40.0
        assert parsed["daily"][0]["wind_gusts_10m_max"] == 11.0
        assert parsed["unavailable"] == ["visibility"]

    def test_the_sun_comes_from_the_solar_module(self, monkeypatch):
        parsed = self.forecast(monkeypatch)
        day = parsed["daily"][1]
        rise, sett = solar.sun_times(
            datetime.fromisoformat(day["time"]).date(),
            -33.45,
            -70.67,
            "America/Santiago",
        )
        assert day["sunrise"] == rise.strftime("%Y-%m-%dT%H:%M")
        assert day["sunset"] == sett.strftime("%Y-%m-%dT%H:%M")
        assert parsed["current"]["is_day"] in (0, 1)

    def test_current_reads_the_first_step(self, monkeypatch):
        current = self.forecast(monkeypatch)["current"]
        assert current["temperature_2m"] == 10.0
        assert current["apparent_temperature"] == 9.0
        assert current["wind_direction_10m"] == 220.0
        assert current["weather_code"] == 0
        assert current["precipitation"] == 0.5

    def test_daily_precipitation_counts_each_period_once(self, monkeypatch):
        parsed = self.forecast(monkeypatch)
        # Primer día local (hora de Santiago, -03:00): de 08:00 a 24:00 locales = 16 pasos
        # horarios (índices 0..15); 0,5 mm en los índices 0, 5, 10 y 15 = 2,0 mm. Los pasos de 6 h
        # que caen en la zona horaria no se suman encima de la lluvia horaria.
        assert parsed["daily"][0]["precipitation_sum"] == 2.0

    def test_the_daily_code_is_the_most_severe_one(self, monkeypatch):
        parsed = self.forecast(monkeypatch)
        assert (
            parsed["daily"][0]["weather_code"] == 63
        )  # «rain» es el mayor de la serie

    def test_a_payload_that_is_not_a_forecast_is_unavailable(self, monkeypatch):
        serve(monkeypatch, FakeResponse({"properties": {"timeseries": []}}))
        assert weather.panel_forecast(-33.45, -70.67) is None


@pytest.mark.django_db
class TestRules:
    def test_without_a_user_agent_it_does_not_call(self, met, monkeypatch, caplog):
        met.WEATHER_USER_AGENT = ""
        sent = serve(monkeypatch, ok())
        with caplog.at_level(logging.WARNING, logger="aerocontrol.weather"):
            assert weather.panel_forecast(-33.45, -70.67) is None
            assert weather.panel_forecast(-33.45, -70.67) is None
        assert sent == []
        assert [r.message for r in caplog.records].count(
            "weather_user_agent_missing"
        ) == 1

    def test_the_request_carries_the_agent_and_short_coordinates(
        self, met, monkeypatch
    ):
        met.WEATHER_API_KEY = "must-not-travel"
        sent = serve(monkeypatch, ok())
        weather.panel_forecast(-33.456789, -70.676789)
        assert len(sent) == 1
        request = sent[0]
        assert request.get_header("User-agent") == UA
        assert "lat=-33.46&lon=-70.68" in request.full_url
        assert "must-not-travel" not in request.full_url
        assert "apikey" not in request.full_url

    def test_open_meteo_still_takes_its_key(self, met, monkeypatch):
        met.WEATHER_PROVIDER = "open_meteo"
        met.WEATHER_API_KEY = "paid-key"
        sent = serve(monkeypatch, FakeResponse({}))
        weather.panel_forecast(-33.45, -70.67)
        assert "apikey=paid-key" in sent[0].full_url
        assert sent[0].get_header("User-agent") != UA

    def test_203_is_accepted_with_a_warning(self, met, monkeypatch, caplog):
        serve(monkeypatch, FakeResponse(met_payload(), status=203))
        with caplog.at_level(logging.WARNING, logger="aerocontrol.weather"):
            assert weather.panel_forecast(-33.45, -70.67) is not None
        assert "weather_deprecated_product" in [r.message for r in caplog.records]

    def test_the_second_call_is_served_from_cache(self, monkeypatch):
        sent = serve(monkeypatch, ok())
        weather.panel_forecast(-33.451, -70.671)
        weather.panel_forecast(-33.449, -70.669)
        assert len(sent) == 1

    def test_ttl_is_the_greater_of_the_setting_and_expires(self, met, monkeypatch):
        ttls = []

        class Spy:
            def __getattr__(self, name):
                return getattr(cache, name)

            def set(self, key, value, timeout=None):
                ttls.append((key, timeout))
                return cache.set(key, value, timeout)

        monkeypatch.setattr(weather, "cache", Spy())
        expires = format_datetime(timezone.now() + timedelta(hours=2), usegmt=True)
        serve(monkeypatch, ok(Expires=expires))
        weather.panel_forecast(-33.45, -70.67)
        panel_ttl = next(t for k, t in ttls if k.startswith("weather:panel:met:"))
        assert 7000 <= panel_ttl <= 7200  # 2 h > 1800 s del setting
        cache.clear()
        ttls.clear()
        serve(monkeypatch, ok())  # sin Expires: manda el setting
        weather.panel_forecast(-33.45, -70.67)
        assert next(t for k, t in ttls if k.startswith("weather:panel:met:")) == 1800

    def test_a_304_reuses_the_copy_and_refreshes_the_stamp(self, monkeypatch):
        last = "Fri, 23 Oct 2026 11:12:47 GMT"
        sent = serve(monkeypatch, ok(**{"Last-Modified": last}), http_error(304))
        first = weather.panel_forecast(-33.45, -70.67, "America/Santiago")
        cache.delete("weather:panel:met:-33.45:-70.67:America/Santiago")
        second = weather.panel_forecast(-33.45, -70.67, "America/Santiago")
        assert len(sent) == 2
        assert sent[0].get_header("If-modified-since") is None
        assert sent[1].get_header("If-modified-since") == last
        assert second is not None and second["hourly"] == first["hourly"]
        assert second["fetched_at"] >= first["fetched_at"]

    def test_a_429_stops_asking_and_serves_the_old_copy_honestly(self, monkeypatch):
        sent = serve(monkeypatch, ok(), http_error(429))
        first = weather.panel_forecast(-33.45, -70.67, "America/Santiago")
        key = "weather:panel:met:-33.45:-70.67:America/Santiago"
        cache.delete(key)
        stale = weather.panel_forecast(-33.45, -70.67, "America/Santiago")
        assert len(sent) == 2
        assert stale is not None and stale["fetched_at"] == first["fetched_at"]
        cache.delete(key)
        weather.panel_forecast(-33.45, -70.67, "America/Santiago")
        assert len(sent) == 2  # frenado: ni una petición más

    def test_a_429_without_a_copy_is_unavailable_and_backs_off(self, monkeypatch):
        sent = serve(monkeypatch, http_error(429))
        assert weather.panel_forecast(-33.45, -70.67) is None
        cache.delete("weather:panel:met:-33.45:-70.67:America/Santiago")
        assert weather.panel_forecast(-33.45, -70.67) is None
        assert len(sent) == 1

    def test_a_network_failure_is_unavailable(self, monkeypatch):
        serve(monkeypatch, urllib.error.URLError("down"))
        assert weather.panel_forecast(-33.45, -70.67) is None

    def test_the_body_limit_is_enough_for_the_measured_response(self):
        assert weather.MAX_BODY_BYTES >= 4 * 60_888

    def test_an_unknown_provider_falls_back_to_met(self, met):
        met.WEATHER_PROVIDER = "other"
        assert weather.provider() == "met_norway"

    def test_geocoding_of_open_meteo_is_only_for_open_meteo(self, monkeypatch):
        sent = serve(monkeypatch, FakeResponse({"results": []}))
        assert weather.search_places("Santiago") is None
        assert sent == []


@pytest.mark.django_db
class TestFacts:
    def test_gusts_and_low_visibility_events_are_not_invented(self, monkeypatch):
        serve(monkeypatch, ok(met_payload(wind=30.0)))  # 108 km/h sostenidos
        parsed = weather.panel_forecast(-33.45, -70.67, "America/Santiago")
        kinds = {e["type"] for e in weather.regional_events(parsed)}
        assert "wind" in kinds
        assert "gusts" not in kinds and "low_visibility" not in kinds

    def test_forecast_for_takes_the_day_row_of_the_same_forecast(self, monkeypatch):
        sent = serve(monkeypatch, ok())
        first = weather.forecast_for(-33.45, -70.67, datetime(2026, 10, 24).date())
        second = weather.forecast_for(-33.45, -70.67, datetime(2026, 10, 25).date())
        assert len(sent) == 1  # una llamada por ubicación
        assert first["date"] == "2026-10-24" and second["date"] == "2026-10-25"
        assert first["temperature_2m_max"] is not None
        assert first["daylight"]["sunrise"] < first["daylight"]["sunset"]
        assert first["wind_gusts_10m_max"] is None
        assert (
            weather.forecast_for(-33.45, -70.67, datetime(2026, 12, 1).date()) is None
        )
