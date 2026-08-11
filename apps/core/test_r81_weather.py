"""R8.1: the project's only outgoing HTTP call, and every way it can fail.

No test here touches the network: `_fetch` is monkeypatched throughout. A test
that really called Open-Meteo would be slow, flaky, and would fail in CI with
no connectivity -- exactly the conditions the module is written to survive.
"""

from datetime import date

import pytest

from apps.core import weather


@pytest.fixture(autouse=True)
def clear_weather_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def enabled(settings):
    settings.WEATHER_ENABLED = True
    settings.WEATHER_API_URL = "https://api.example.test/v1/forecast"
    return settings


def _payload(**overrides):
    payload = {
        "daily": {
            "time": ["2026-08-20"],
            "wind_speed_10m_max": [18.4],
            "wind_gusts_10m_max": [31.0],
            "precipitation_sum": [0.0],
            "precipitation_probability_max": [5],
        },
        "daily_units": {"wind_speed_10m_max": "km/h", "precipitation_sum": "mm"},
    }
    payload.update(overrides)
    return payload


class TestDisabledByDefault:
    def test_returns_none_and_never_calls_out_when_disabled(
        self, settings, monkeypatch
    ):
        """The zero-outgoing-calls property must hold for any deployment that
        does not opt in -- not merely 'the result is ignored'."""
        settings.WEATHER_ENABLED = False
        called = []
        monkeypatch.setattr(weather, "_fetch", lambda *a: called.append(a))

        assert weather.forecast_for(-33.45, -70.66, date(2026, 8, 20)) is None
        assert called == []


class TestHappyPath:
    def test_parses_the_requested_day(self, enabled, monkeypatch):
        monkeypatch.setattr(weather, "_fetch", lambda *a: _payload())

        result = weather.forecast_for(-33.45, -70.66, date(2026, 8, 20))

        assert result["wind_speed_10m_max"] == 18.4
        assert result["wind_gusts_10m_max"] == 31.0
        assert result["precipitation_probability_max"] == 5
        assert result["units"]["wind_speed_10m_max"] == "km/h"
        assert result["date"] == "2026-08-20"

    def test_picks_the_right_index_from_a_multi_day_payload(self, enabled, monkeypatch):
        """The provider may return more days than asked for; the value must be
        read by matching the date, not by assuming index 0."""
        payload = {
            "daily": {
                "time": ["2026-08-19", "2026-08-20", "2026-08-21"],
                "wind_speed_10m_max": [1.0, 22.2, 3.0],
                "wind_gusts_10m_max": [1.0, 44.4, 3.0],
                "precipitation_sum": [1.0, 2.0, 3.0],
                "precipitation_probability_max": [10, 20, 30],
            }
        }
        monkeypatch.setattr(weather, "_fetch", lambda *a: payload)

        result = weather.forecast_for(-33.45, -70.66, date(2026, 8, 20))

        assert result["wind_speed_10m_max"] == 22.2
        assert result["precipitation_probability_max"] == 20


class TestDegradation:
    """Every failure path returns None -- a provider problem must never break
    the page that renders this."""

    def test_unreachable_provider(self, enabled, monkeypatch):
        monkeypatch.setattr(weather, "_fetch", lambda *a: None)
        assert weather.forecast_for(-33.45, -70.66, date(2026, 8, 20)) is None

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"daily": None},
            {"daily": {}},
            {"daily": {"time": "not-a-list"}},
            # The requested day simply is not in the response.
            {"daily": {"time": ["2026-01-01"], "wind_speed_10m_max": [5.0]}},
            # Right shape, but every value is null.
            {
                "daily": {
                    "time": ["2026-08-20"],
                    "wind_speed_10m_max": [None],
                    "wind_gusts_10m_max": [None],
                    "precipitation_sum": [None],
                    "precipitation_probability_max": [None],
                }
            },
            # A series shorter than the time array (index would be out of range).
            {"daily": {"time": ["2026-08-20"], "wind_speed_10m_max": []}},
            # A string where a number belongs.
            {
                "daily": {
                    "time": ["2026-08-20"],
                    "wind_speed_10m_max": ["strong"],
                    "wind_gusts_10m_max": ["gusty"],
                    "precipitation_sum": ["wet"],
                    "precipitation_probability_max": ["likely"],
                }
            },
        ],
    )
    def test_malformed_payloads_return_none(self, enabled, monkeypatch, payload):
        monkeypatch.setattr(weather, "_fetch", lambda *a: payload)
        assert weather.forecast_for(-33.45, -70.66, date(2026, 8, 20)) is None

    def test_non_numeric_coordinates_return_none(self, enabled, monkeypatch):
        monkeypatch.setattr(weather, "_fetch", lambda *a: _payload())
        assert weather.forecast_for("north", "west", date(2026, 8, 20)) is None

    @pytest.mark.parametrize(
        "bad_url",
        [
            "file:///etc/passwd",
            "file://C:/Windows/win.ini",
            "ftp://example.test/forecast",
            "gopher://example.test/",
            "/etc/passwd",
        ],
    )
    def test_a_non_http_api_url_is_refused_without_opening_it(
        self, enabled, bad_url, monkeypatch
    ):
        """urlopen would happily read a local file, so a fat-fingered
        WEATHER_API_URL must be refused rather than followed. `_fetch` is NOT
        patched here -- this exercises the real scheme guard."""
        enabled.WEATHER_API_URL = bad_url
        opened = []
        monkeypatch.setattr(
            weather.urllib.request, "urlopen", lambda *a, **kw: opened.append(a)
        )

        assert weather.forecast_for(-33.45, -70.66, date(2026, 8, 20)) is None
        assert opened == []


class TestCaching:
    def test_a_second_call_does_not_hit_the_provider_again(self, enabled, monkeypatch):
        calls = []

        def fetch(*args):
            calls.append(args)
            return _payload()

        monkeypatch.setattr(weather, "_fetch", fetch)
        target = date(2026, 8, 20)

        first = weather.forecast_for(-33.45, -70.66, target)
        second = weather.forecast_for(-33.45, -70.66, target)

        assert first == second
        assert len(calls) == 1

    def test_a_failure_is_cached_too(self, enabled, monkeypatch):
        """Without this, a provider that is down gets one request per page
        view -- the opposite of what a cache is for."""
        calls = []

        def fetch(*args):
            calls.append(args)
            return None

        monkeypatch.setattr(weather, "_fetch", fetch)
        target = date(2026, 8, 20)

        assert weather.forecast_for(-33.45, -70.66, target) is None
        assert weather.forecast_for(-33.45, -70.66, target) is None
        assert len(calls) == 1

    def test_nearby_coordinates_share_a_cache_entry(self, enabled, monkeypatch):
        """Rounded to ~1 km, so two plans over the same site do not each cost
        a request."""
        calls = []

        def fetch(*args):
            calls.append(args)
            return _payload()

        monkeypatch.setattr(weather, "_fetch", fetch)
        target = date(2026, 8, 20)

        weather.forecast_for(-33.4512, -70.6634, target)
        weather.forecast_for(-33.4514, -70.6631, target)

        assert len(calls) == 1

    def test_a_different_day_is_a_different_entry(self, enabled, monkeypatch):
        calls = []

        def fetch(*args):
            calls.append(args)
            return _payload()

        monkeypatch.setattr(weather, "_fetch", fetch)

        weather.forecast_for(-33.45, -70.66, date(2026, 8, 20))
        weather.forecast_for(-33.45, -70.66, date(2026, 8, 21))

        assert len(calls) == 2


class TestBboxCentroid:
    def test_returns_the_middle_of_the_box(self):
        version = type(
            "V",
            (),
            {
                "bbox_west": -71.0,
                "bbox_south": -34.0,
                "bbox_east": -70.0,
                "bbox_north": -33.0,
            },
        )()

        assert weather.bbox_centroid(version) == (-33.5, -70.5)

    def test_none_version_or_incomplete_bbox_returns_none(self):
        assert weather.bbox_centroid(None) is None
        partial = type(
            "V",
            (),
            {
                "bbox_west": -71.0,
                "bbox_south": None,
                "bbox_east": -70.0,
                "bbox_north": -33.0,
            },
        )()
        assert weather.bbox_centroid(partial) is None
