"""R8.4: temperature, wind in m/s, and the day's condition.

Same rule as R8.1's tests: nothing here touches the network. What is being
checked is the *contract* -- which parameters go out, and how the answer is
read -- because a wrong unit or a made-up sky icon next to a real date is how a
go/no-go call gets made on bad information.
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


def _payload(**daily):
    base = {
        "time": ["2026-08-20"],
        "temperature_2m_max": [17.4],
        "temperature_2m_min": [3.9],
        "wind_speed_10m_max": [8.1],
        "wind_gusts_10m_max": [12.7],
        "precipitation_sum": [0.0],
        "precipitation_probability_max": [5],
        "weather_code": [3],
    }
    base.update(daily)
    return {
        "daily": base,
        "daily_units": {
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "wind_speed_10m_max": "m/s",
        },
    }


class TestTemperature:
    def test_both_ends_of_the_day_are_read(self, enabled, monkeypatch):
        monkeypatch.setattr(weather, "_fetch", lambda *a: _payload())

        result = weather.forecast_for(-33.45, -70.66, date(2026, 8, 20))

        assert result["temperature_2m_max"] == 17.4
        assert result["temperature_2m_min"] == 3.9
        assert result["units"]["temperature_2m_max"] == "°C"

    def test_it_costs_no_extra_call(self, enabled, monkeypatch):
        """Temperature rides along in the same response as the wind -- if this
        ever became a second request the panel would double its outgoing
        traffic for two numbers."""
        calls = []

        def fetch(*args):
            calls.append(args)
            return _payload()

        monkeypatch.setattr(weather, "_fetch", fetch)

        result = weather.forecast_for(-33.45, -70.66, date(2026, 8, 20))

        assert result["temperature_2m_max"] is not None
        assert result["wind_speed_10m_max"] is not None
        assert len(calls) == 1


class TestWindUnit:
    def test_the_request_asks_for_metres_per_second(self, enabled, monkeypatch):
        """The aircraft are specified in m/s, so the forecast must be too --
        this asserts the parameter actually goes out, not just that a constant
        exists. `_fetch` is NOT patched here; urlopen is."""
        opened = []

        class _Response:
            status = 200

            def read(self, _size):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def urlopen(request, timeout=None):
            opened.append(request.full_url)
            return _Response()

        monkeypatch.setattr(weather.urllib.request, "urlopen", urlopen)

        weather.forecast_for(-33.45, -70.66, date(2026, 8, 20))

        assert len(opened) == 1
        assert "wind_speed_unit=ms" in opened[0]
        assert "temperature_2m_max" in opened[0]
        assert "weather_code" in opened[0]

    def test_changing_the_unit_does_not_serve_the_old_numbers(
        self, enabled, monkeypatch
    ):
        """The unit is part of the cache key. Without that, flipping it would
        keep showing km/h figures labelled m/s until the entry expired -- a
        wrong number in front of a pilot, with the right-looking label."""
        calls = []

        def fetch(*args):
            calls.append(args)
            return _payload()

        monkeypatch.setattr(weather, "_fetch", fetch)
        target = date(2026, 8, 20)

        weather.forecast_for(-33.45, -70.66, target)
        monkeypatch.setattr(weather, "WIND_SPEED_UNIT", "kmh")
        weather.forecast_for(-33.45, -70.66, target)

        assert len(calls) == 2


class TestCondition:
    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            (0, "clear"),
            (1, "partly_cloudy"),
            (2, "partly_cloudy"),
            (3, "cloudy"),
            (45, "fog"),
            (53, "drizzle"),
            (65, "rain"),
            (81, "rain"),
            (75, "snow"),
            (95, "thunderstorm"),
        ],
    )
    def test_wmo_codes_map_to_a_slug(self, code, expected):
        assert weather.condition_for(code) == expected

    @pytest.mark.parametrize("value", [None, "rain", 999, True, False, [61]])
    def test_anything_unknown_is_no_condition_rather_than_a_guess(self, value):
        """Returning a catch-all "cloudy" would draw a sky the provider never
        reported. `True` is in here on purpose: bool is an int in Python, and
        `True == 1` would otherwise silently mean "partly cloudy"."""
        assert weather.condition_for(value) is None

    def test_the_forecast_carries_the_slug(self, enabled, monkeypatch):
        monkeypatch.setattr(weather, "_fetch", lambda *a: _payload(weather_code=[61]))

        result = weather.forecast_for(-33.45, -70.66, date(2026, 8, 20))

        assert result["condition"] == "rain"

    def test_a_missing_code_leaves_the_numbers_intact(self, enabled, monkeypatch):
        payload = _payload()
        del payload["daily"]["weather_code"]
        monkeypatch.setattr(weather, "_fetch", lambda *a: payload)

        result = weather.forecast_for(-33.45, -70.66, date(2026, 8, 20))

        assert result["condition"] is None
        assert result["wind_speed_10m_max"] == 8.1

    def test_a_code_with_no_measurements_is_not_a_forecast(self, enabled, monkeypatch):
        """A condition code is not a measurement, so it must not on its own
        make an empty response look like an answer."""
        monkeypatch.setattr(
            weather,
            "_fetch",
            lambda *a: {"daily": {"time": ["2026-08-20"], "weather_code": [3]}},
        )

        assert weather.forecast_for(-33.45, -70.66, date(2026, 8, 20)) is None
