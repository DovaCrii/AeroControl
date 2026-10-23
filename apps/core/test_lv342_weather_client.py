"""LV-342: informative weather card client -- no test touches the network.

A guard monkeypatches `urllib.request.urlopen` to fail the test if it is
called without an explicit fake, so a test that forgets to stub cannot reach
Open-Meteo (slow, flaky, and impossible in CI without connectivity).
"""

import json
import logging
import urllib.error
from datetime import date
from pathlib import Path

import pytest
from django.core.cache import cache

from apps.core import solar, weather

TESTDATA = Path(weather.__file__).parent / "testdata"
SECRET = "sk-test-secret-123"


def _fixture():
    return json.loads((TESTDATA / "weather_panel_forecast.json").read_text("utf-8"))


class FakeResponse:
    def __init__(self, body, status=200):
        self.status = status
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self, limit=-1):
        return self._body[:limit] if limit >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("network call in a test without an explicit fake")

    monkeypatch.setattr(weather.urllib.request, "urlopen", boom)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def enabled(settings):
    settings.WEATHER_ENABLED = True
    settings.WEATHER_API_URL = "https://api.example.test/v1/forecast"
    settings.WEATHER_GEOCODING_URL = "https://geo.example.test/v1/search"
    settings.WEATHER_API_KEY = ""
    return settings


def _serve(monkeypatch, response):
    """Replace urlopen; returns the list of requested URLs."""
    urls = []

    def fake(request, timeout=None):
        urls.append(request.full_url)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(weather.urllib.request, "urlopen", fake)
    return urls


class TestPanelForecast:
    def test_happy_path_parses_one_request(self, enabled, monkeypatch):
        urls = _serve(monkeypatch, FakeResponse(_fixture()))
        result = weather.panel_forecast(-33.4569, -70.6483)
        assert len(urls) == 1
        assert "forecast_hours=48" in urls[0] and "wind_speed_unit=ms" in urls[0]
        assert result["current"]["temperature_2m"] == 14.2
        assert len(result["hourly"]) == 48 and len(result["daily"]) == 7
        # LV-364: the sun is computed locally, not read from the provider.
        first = result["daily"][0]
        expected = solar.sun_times(
            date.fromisoformat(first["time"]), -33.46, -70.65, "America/Santiago"
        )
        assert first["sunrise"] == expected[0].strftime("%Y-%m-%dT%H:%M")
        assert result["fetched_at"]

    def test_second_call_is_served_from_cache(self, enabled, monkeypatch):
        urls = _serve(monkeypatch, FakeResponse(_fixture()))
        weather.panel_forecast(-33.451, -70.661)
        weather.panel_forecast(-33.449, -70.659)  # rounds to the same key
        assert len(urls) == 1

    def test_failure_is_cached_as_unavailable(self, enabled, monkeypatch):
        urls = _serve(monkeypatch, FakeResponse({}, status=500))
        assert weather.panel_forecast(-33.45, -70.66) is None
        assert weather.panel_forecast(-33.45, -70.66) is None
        assert len(urls) == 1

    @pytest.mark.parametrize(
        "response",
        [
            TimeoutError("slow"),
            urllib.error.URLError("down"),
            FakeResponse({}, status=500),
            FakeResponse(b"{not json"),
            FakeResponse({"unrelated": 1}),
        ],
    )
    def test_any_failure_returns_none(self, enabled, monkeypatch, response):
        _serve(monkeypatch, response)
        assert weather.panel_forecast(-33.45, -70.66) is None

    def test_file_scheme_is_rejected_without_any_request(self, enabled):
        enabled.WEATHER_API_URL = "file:///etc/passwd"
        assert weather.panel_forecast(-33.45, -70.66) is None

    @pytest.mark.parametrize(
        "lat,lon", [(91, 0), (-91, 0), (0, 181), (0, -181), ("x", 0), (None, 0)]
    )
    def test_out_of_range_coordinates_make_no_request(self, enabled, lat, lon):
        assert weather.panel_forecast(lat, lon) is None  # guard fails if called

    def test_disabled_makes_no_request(self, settings):
        settings.WEATHER_ENABLED = False
        assert weather.panel_forecast(-33.45, -70.66) is None
        assert weather.search_places("Santiago") is None

    def test_api_key_is_sent_but_never_logged(self, enabled, monkeypatch, caplog):
        enabled.WEATHER_API_KEY = SECRET
        urls = _serve(monkeypatch, urllib.error.URLError(f"apikey={SECRET}"))
        with caplog.at_level(logging.DEBUG, logger="aerocontrol.weather"):
            assert weather.panel_forecast(-33.45, -70.66) is None
        assert f"apikey={SECRET}" in urls[0]  # sent in the request only
        assert SECRET not in caplog.text
        assert all(SECRET not in str(r.__dict__) for r in caplog.records)

    def test_no_key_means_no_apikey_parameter(self, enabled, monkeypatch):
        urls = _serve(monkeypatch, FakeResponse(_fixture()))
        weather.panel_forecast(-33.45, -70.66)
        assert "apikey" not in urls[0]


class TestSearchPlaces:
    PAYLOAD = {
        "results": [
            {
                "name": "Santiago",
                "latitude": -33.45694,
                "longitude": -70.64827,
                "country": "Chile",
                "admin1": "Región Metropolitana",
                "timezone": "America/Santiago",
            },
            {"name": "Broken", "latitude": 999, "longitude": 0},
        ]
    }

    def test_results_are_normalised_and_cached(self, enabled, monkeypatch):
        urls = _serve(monkeypatch, FakeResponse(self.PAYLOAD))
        first = weather.search_places("  Santiago ")
        assert weather.search_places("santiago") == first
        assert len(urls) == 1 and "count=8" in urls[0]
        assert [p["name"] for p in first] == ["Santiago"]  # invalid coords dropped
        assert first[0]["latitude"] == -33.46

    def test_no_results_is_an_empty_list(self, enabled, monkeypatch):
        _serve(monkeypatch, FakeResponse({"generationtime_ms": 0.3}))
        assert weather.search_places("Zzzzzz") == []

    @pytest.mark.parametrize("query", ["", "a", " b ", "x" * 81, None])
    def test_short_or_long_query_makes_no_request(self, enabled, query):
        assert weather.search_places(query) == []

    def test_boundaries_do_query(self, enabled, monkeypatch):
        urls = _serve(monkeypatch, FakeResponse({}))
        weather.search_places("ab")
        weather.search_places("x" * 80)
        assert len(urls) == 2

    def test_failure_returns_none(self, enabled, monkeypatch):
        _serve(monkeypatch, TimeoutError())
        assert weather.search_places("Santiago") is None


class TestFakeFixture:
    def test_serves_bundled_json_without_network_in_debug(self, enabled, settings):
        settings.DEBUG = True
        settings.WEATHER_FAKE_FIXTURE = True
        assert len(weather.panel_forecast(-33.45, -70.66)["hourly"]) == 48
        assert weather.search_places("Santiago")[0]["name"] == "Santiago"

    def test_ignored_with_warning_without_debug(
        self, enabled, settings, monkeypatch, caplog
    ):
        settings.DEBUG = False
        settings.WEATHER_FAKE_FIXTURE = True
        urls = _serve(monkeypatch, FakeResponse({"unrelated": 1}))
        with caplog.at_level(logging.WARNING, logger="aerocontrol.weather"):
            assert weather.panel_forecast(-33.45, -70.66) is None
        assert len(urls) == 1  # went to the (fake) network, not the fixture
        assert "weather_fake_fixture_ignored_without_debug" in caplog.text


def _forecast(**series):
    """48-hour forecast in km/h with calm defaults; `series` overrides columns."""
    base = {
        "wind_speed_10m": 5.0,
        "wind_gusts_10m": 10.0,
        "temperature_2m": 15.0,
        "precipitation": 0.0,
        "visibility": 24000,
        "weather_code": 1,
    }
    hours = []
    for i in range(48):
        row = {
            "time": f"2026-10-19T{i % 24:02d}:00"
            if i < 24
            else f"2026-10-20T{i % 24:02d}:00"
        }
        for field, default in base.items():
            value = series.get(field, default)
            row[field] = value(i) if callable(value) else value
        hours.append(row)
    return {"hourly": hours, "units": {"wind_speed_10m": "km/h"}}


def _only(events, kind):
    found = [e for e in events if e["type"] == kind]
    assert len(found) == 1, events
    return found[0]


def _at(index, value, default):
    return lambda i: value if i == index else default


class TestRegionalEvents:
    def test_calm_forecast_has_no_events(self):
        assert weather.regional_events(_forecast()) == []

    def test_garbage_input_has_no_events(self):
        assert weather.regional_events(None) == []
        assert weather.regional_events({}) == []
        assert weather.regional_events({"hourly": "x"}) == []

    @pytest.mark.parametrize(
        "field,kind,exact,below,level_hi",
        [
            ("wind_speed_10m", "wind", 40.0, 39.9, 60.0),
            ("wind_gusts_10m", "gusts", 60.0, 59.9, 90.0),
        ],
    )
    def test_wind_and_gusts_thresholds(self, field, kind, exact, below, level_hi):
        assert weather.regional_events(_forecast(**{field: _at(5, below, 5.0)})) == []
        event = _only(
            weather.regional_events(_forecast(**{field: _at(5, exact, 5.0)})), kind
        )
        assert event["level"] == "attention"
        assert event["value"] == exact and event["unit"] == "km/h"
        assert event["start"] == event["end"] == "2026-10-19T05:00"
        strong = _only(
            weather.regional_events(_forecast(**{field: _at(5, level_hi, 5.0)})), kind
        )
        assert strong["level"] == "strong"

    def test_wind_in_ms_is_converted_to_kmh(self):
        forecast = _forecast(wind_speed_10m=_at(2, 11.2, 1.0))  # 40.3 km/h
        forecast["units"] = {"wind_speed_10m": "m/s"}
        assert _only(weather.regional_events(forecast), "wind")["value"] == 40.3

    def test_window_spans_first_to_last_hour(self):
        forecast = _forecast(wind_speed_10m=lambda i: 50.0 if i in (3, 7) else 5.0)
        event = _only(weather.regional_events(forecast), "wind")
        assert (event["start"], event["end"]) == (
            "2026-10-19T03:00",
            "2026-10-19T07:00",
        )

    def test_hours_beyond_48_are_ignored(self):
        forecast = _forecast()
        forecast["hourly"].append({**forecast["hourly"][0], "wind_speed_10m": 99.0})
        assert weather.regional_events(forecast) == []

    def test_accumulated_rain_threshold(self):
        # 20 mm spread over 20 hours at 1 mm/h: exactly the threshold.
        exact = _forecast(precipitation=lambda i: 1.0 if i < 20 else 0.0)
        assert (
            _only(weather.regional_events(exact), "rain_accumulated")["value"] == 20.0
        )
        below = _forecast(precipitation=lambda i: 0.99 if i < 20 else 0.0)
        assert weather.regional_events(below) == []
        strong = _forecast(precipitation=lambda i: 2.0 if i < 20 else 0.0)
        assert (
            _only(weather.regional_events(strong), "rain_accumulated")["level"]
            == "strong"
        )

    def test_heavy_hourly_rain(self):
        assert weather.regional_events(_forecast(precipitation=_at(4, 7.9, 0.0))) == []
        event = _only(
            weather.regional_events(_forecast(precipitation=_at(4, 8.0, 0.0))),
            "heavy_rain",
        )
        assert event["unit"] == "mm/h"

    @pytest.mark.parametrize(
        "code,kinds",
        [
            (95, {"thunderstorm"}),
            (96, {"thunderstorm", "hail"}),
            (99, {"thunderstorm", "hail"}),
            (80, set()),
        ],
    )
    def test_thunderstorm_and_hail_by_wmo_code(self, code, kinds):
        events = weather.regional_events(_forecast(weather_code=_at(9, code, 1)))
        assert {e["type"] for e in events} == kinds
        if "hail" in kinds:
            assert _only(events, "hail")["level"] == "strong"
            assert events[0]["type"] == "hail"  # strongest first

    @pytest.mark.parametrize(
        "code,level", [(71, "info"), (73, "attention"), (75, "strong")]
    )
    def test_snow_levels(self, code, level):
        event = _only(
            weather.regional_events(_forecast(weather_code=_at(3, code, 1))), "snow"
        )
        assert event["level"] == level

    def test_frost_threshold_is_at_or_below(self):
        assert (
            weather.regional_events(_forecast(temperature_2m=_at(2, 0.1, 15.0))) == []
        )
        event = _only(
            weather.regional_events(_forecast(temperature_2m=_at(2, 0.0, 15.0))),
            "frost",
        )
        assert event["level"] == "attention"
        deep = weather.regional_events(_forecast(temperature_2m=_at(2, -5.0, 15.0)))
        assert _only(deep, "frost")["level"] == "strong"

    def test_heat_threshold(self):
        assert (
            weather.regional_events(_forecast(temperature_2m=_at(2, 34.9, 15.0))) == []
        )
        event = _only(
            weather.regional_events(_forecast(temperature_2m=_at(2, 35.0, 15.0))),
            "heat",
        )
        assert event["level"] == "attention"
        hot = weather.regional_events(_forecast(temperature_2m=_at(2, 52.5, 15.0)))
        assert _only(hot, "heat")["level"] == "strong"

    def test_visibility_is_strictly_below_threshold(self):
        assert weather.regional_events(_forecast(visibility=_at(2, 1000, 24000))) == []
        event = _only(
            weather.regional_events(_forecast(visibility=_at(2, 999, 24000))),
            "low_visibility",
        )
        assert event["level"] == "attention" and event["unit"] == "m"
        dense = weather.regional_events(_forecast(visibility=_at(2, 150, 24000)))
        assert _only(dense, "low_visibility")["level"] == "strong"

    @pytest.mark.parametrize("code", [45, 48])
    def test_fog_code_alone_is_informational(self, code):
        event = _only(
            weather.regional_events(_forecast(weather_code=_at(6, code, 1))),
            "low_visibility",
        )
        assert event["level"] == "info"

    def test_thresholds_are_configurable(self, settings):
        settings.WEATHER_EVENT_WIND_KMH = 20
        forecast = _forecast(wind_speed_10m=_at(1, 25.0, 5.0))
        assert _only(weather.regional_events(forecast), "wind")["level"] == "attention"

    def test_fake_fixture_end_to_end(self, enabled, settings):
        settings.DEBUG = True
        settings.WEATHER_FAKE_FIXTURE = True
        events = weather.regional_events(weather.panel_forecast(-33.45, -70.66))
        assert {e["type"] for e in events} == {"gusts", "thunderstorm"}
