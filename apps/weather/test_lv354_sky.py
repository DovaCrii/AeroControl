"""LV-354: estado del cielo de la tarjeta del tiempo y cruce del centelleo GNSS con la puesta de sol.

`sky_state` es una función pura: se prueba con tablas. Las fechas de los datos están FIJAS (el
fixture del pronóstico es del 2026-10-19) y la hora se fija con `pin_now`; sin red.
"""

import json
import socket
import urllib.request
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from apps.core import weather as weather_client
from apps.core.testing import login_as, pin_now
from apps.weather import gnss, sky
from apps.weather import panel as panel_module
from apps.weather.templatetags import gnss_tags

SANTIAGO = ZoneInfo("America/Santiago")
FIXTURE = Path(weather_client.__file__).parent / "testdata/weather_panel_forecast.json"
DAY = "2026-10-19"
DAILY = [{"time": DAY, "sunrise": f"{DAY}T06:40", "sunset": f"{DAY}T19:50"}]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("el cielo no puede salir a la red")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def at(hour, minute=0, day=(2026, 10, 19)):
    return datetime(*day, hour, minute)


def state(moment, daily=DAILY, slug="clear", is_day=True):
    return sky.sky_state(moment, daily, is_day, slug, SANTIAGO)


class TestPhases:
    # amanecer 06:40, puesta 19:50, mediodía solar 13:15. Intervalos [inicio, fin).
    @pytest.mark.parametrize(
        "moment, phase",
        [
            (at(0), "night"),
            (at(5, 54), "night"),
            (at(5, 55), "dawn"),
            (at(7, 39), "dawn"),
            (at(7, 40), "morning"),
            (at(11, 44), "morning"),
            (at(11, 45), "midday"),
            (at(14, 44), "midday"),
            (at(14, 45), "afternoon"),
            (at(18, 49), "afternoon"),
            (at(18, 50), "sunset"),
            (at(19, 49), "sunset"),
            (at(19, 50), "twilight"),
            (at(20, 34), "twilight"),
            (at(20, 35), "night"),
            (at(23, 59), "night"),
        ],
    )
    def test_the_edges_belong_to_the_later_phase(self, moment, phase):
        assert state(moment)["phase"] == phase

    def test_the_phases_follow_the_forecast_not_a_fixed_clock(self):
        winter = [{"time": DAY, "sunrise": f"{DAY}T08:10", "sunset": f"{DAY}T17:30"}]
        # puesta 17:30: a las 18:00 es crepúsculo; con la puesta de las 19:50 sería tarde
        assert state(at(18, 0), winter)["phase"] == "twilight"
        assert state(at(18, 0))["phase"] == "afternoon"

    def test_the_fallback_is_flagged_and_uses_fixed_hours(self):
        for daily in (
            [],
            None,
            [{"time": "2026-10-18", "sunrise": "x", "sunset": "y"}],
        ):
            result = state(at(12, 0), daily)
            assert result["fallback"] is True
            assert result["sunrise"].hour == 7 and result["sunset"].hour == 20
        # Mediodía de respaldo: 13:30 +- 90 min, así que las 12:00 ya son mediodía.
        assert state(at(11, 59), [])["phase"] == "morning"
        assert state(at(12, 0), [])["phase"] == "midday"

    def test_a_broken_sunset_also_falls_back(self):
        bad = [{"time": DAY, "sunrise": f"{DAY}T20:00", "sunset": f"{DAY}T07:00"}]
        assert state(at(12), bad)["fallback"] is True
        assert state(at(12))["fallback"] is False

    def test_aware_input_is_converted_to_the_zone(self):
        utc = datetime(2026, 10, 19, 15, 0, tzinfo=dt_timezone.utc)  # 12:00 -03
        assert state(utc)["phase"] == "midday"


class TestSunAndMoonPositions:
    def test_the_sun_goes_from_the_left_edge_to_the_right_along_an_arc(self):
        rise, noon, set_ = state(at(6, 40)), state(at(13, 15)), state(at(19, 50))
        assert (rise["p"], rise["sun"]["x"], rise["sun"]["y"]) == (0.0, 40.0, 120.0)
        assert noon["p"] == 0.5 and noon["sun"]["x"] == 320.0
        assert noon["sun"]["y"] == 30.0
        assert set_["sun"]["visible"] is False and set_["sun"]["x"] == 600.0
        assert rise["sun"]["visible"] is True and noon["sun"]["visible"] is True

    def test_the_moon_shows_only_while_the_sun_is_down(self):
        assert state(at(12))["moon"]["visible"] is False
        night = state(at(23, 0))
        assert night["moon"]["visible"] is True and night["sun"]["visible"] is False
        # el arco de la luna va de la puesta al amanecer siguiente: a las 23:00 aún sube
        assert 40 < night["moon"]["x"] < 320

    def test_the_moon_arc_follows_real_time_across_the_september_clock_change(self):
        # Santiago se adelanta a las 24:00 del 5 de septiembre de 2026 (00:00 no existe).
        daily = [
            {
                "time": "2026-09-06",
                "sunrise": "2026-09-06T07:20",
                "sunset": "2026-09-06T19:25",
            }
        ]
        result = state(datetime(2026, 9, 6, 1, 0), daily, is_day=False)
        start = datetime(2026, 9, 5, 19, 25, tzinfo=SANTIAGO)
        end = datetime(2026, 9, 6, 7, 20, tzinfo=SANTIAGO)
        now = datetime(2026, 9, 6, 1, 0, tzinfo=SANTIAGO)
        # restar dos datetimes de la MISMA zona usa el reloj de pared: se resta en UTC
        utc = dt_timezone.utc
        expected = (now.astimezone(utc) - start.astimezone(utc)) / (
            end.astimezone(utc) - start.astimezone(utc)
        )
        assert abs(result["moon"]["x"] - (40 + 560 * expected)) < 0.2
        # Con reloj de pared (sin cambio de hora) saldría 5h35/11h55: otro valor.
        wall = (5 * 60 + 35) / (11 * 60 + 55)
        assert abs(result["moon"]["x"] - (40 + 560 * wall)) > 5

    def test_the_repeated_hour_of_april_does_not_break(self):
        daily = [
            {
                "time": "2026-04-04",
                "sunrise": "2026-04-04T07:35",
                "sunset": "2026-04-04T19:10",
            }
        ]
        result = state(datetime(2026, 4, 4, 23, 30), daily)
        assert result["phase"] == "night" and result["moon"]["visible"] is True


class TestMoonPhase:
    def test_the_reference_new_moon_is_new(self):
        result = sky.moon_phase(sky.NEW_MOON_REF)
        assert result["age"] == 0 and result["name"] == "new"
        assert result["illumination"] == 0

    def test_a_known_full_moon_is_full(self):
        full = datetime(2000, 1, 21, 4, 40, tzinfo=dt_timezone.utc)
        result = sky.moon_phase(full)
        assert result["name"] == "full" and result["illumination"] > 0.99

    def test_a_known_recent_new_moon_is_almost_dark(self):
        new = datetime(2026, 10, 10, 15, 50, tzinfo=dt_timezone.utc)
        assert sky.moon_phase(new)["illumination"] < 0.02

    def test_the_quarters_are_named_and_the_cycle_wraps(self):
        first = sky.NEW_MOON_REF + timedelta(days=sky.SYNODIC_DAYS / 4)
        assert sky.moon_phase(first)["name"] == "first_quarter"
        last = sky.NEW_MOON_REF + timedelta(days=sky.SYNODIC_DAYS * 3 / 4)
        assert sky.moon_phase(last)["name"] == "last_quarter"
        wrapped = sky.NEW_MOON_REF + timedelta(days=sky.SYNODIC_DAYS * 40)
        assert sky.moon_phase(wrapped)["name"] == "new"


class TestWeatherCategory:
    @pytest.mark.parametrize(
        "slug, clouds, precip, fog, lightning",
        [
            ("clear", 0, None, False, False),
            ("partly", 1, None, False, False),
            ("cloudy", 2, None, False, False),
            ("fog", 2, None, True, False),
            ("rain", 3, "rain", False, False),
            ("snow", 2, "snow", False, False),
            ("storm", 3, "rain", False, True),
            ("wind", 1, None, False, False),
            ("unknown", 2, None, False, False),
        ],
    )
    def test_each_category_says_what_to_draw(
        self, slug, clouds, precip, fog, lightning
    ):
        result = state(at(12), slug=slug)
        assert (result["clouds"], result["precip"]) == (clouds, precip)
        assert (result["fog"], result["lightning"]) == (fog, lightning)


@pytest.fixture
def forecast():
    return weather_client._parse_panel(json.loads(FIXTURE.read_text("utf-8")))


class TestPanelWiring:
    def test_the_card_context_carries_the_sky(self, monkeypatch, forecast):
        monkeypatch.setattr(panel_module, "_local_now", lambda f: at(21, 0))
        location = type("L", (), {"label": "Santiago"})()
        card = panel_module.build_card(location, forecast, [])
        assert card["state"] == "ok"
        assert card["sky"]["phase"] == "night" and card["sky"]["fallback"] is False
        assert card["sky"]["sunset"].strftime("%H:%M") == "19:50"
        assert card["sky"]["slug"] == card["slug"]

    def test_fake_now_works_with_debug_and_the_fake_fixture(self, settings):
        settings.DEBUG = True
        settings.WEATHER_FAKE_FIXTURE = True
        settings.WEATHER_FAKE_NOW = "2026-10-19T19:30"
        assert panel_module._local_now({"timezone": "America/Santiago"}) == at(19, 30)

    def test_fake_now_with_an_offset_is_converted_to_the_zone(self, settings):
        settings.DEBUG = True
        settings.WEATHER_FAKE_FIXTURE = True
        settings.WEATHER_FAKE_NOW = "2026-10-19T22:30:00+00:00"
        assert panel_module._local_now({"timezone": "America/Santiago"}) == at(19, 30)

    def test_fake_now_is_ignored_without_debug(self, settings, monkeypatch):
        real = datetime(2026, 1, 15, 12, 0, tzinfo=SANTIAGO)
        pin_now(monkeypatch, real)
        settings.DEBUG = False
        settings.WEATHER_FAKE_FIXTURE = True
        settings.WEATHER_FAKE_NOW = "2026-10-19T19:30"
        assert panel_module._local_now({"timezone": "America/Santiago"}) == datetime(
            2026, 1, 15, 12, 0
        )

    def test_fake_now_is_ignored_without_the_fake_fixture(self, settings, monkeypatch):
        pin_now(monkeypatch, datetime(2026, 1, 15, 12, 0, tzinfo=SANTIAGO))
        settings.DEBUG = True
        settings.WEATHER_FAKE_FIXTURE = False
        settings.WEATHER_FAKE_NOW = "2026-10-19T19:30"
        assert panel_module._local_now({"timezone": "America/Santiago"}).month == 1

    def test_a_garbled_fake_now_is_ignored(self, settings, monkeypatch):
        pin_now(monkeypatch, datetime(2026, 1, 15, 12, 0, tzinfo=SANTIAGO))
        settings.DEBUG = True
        settings.WEATHER_FAKE_FIXTURE = True
        settings.WEATHER_FAKE_NOW = "mañana"
        assert panel_module._local_now({"timezone": "America/Santiago"}).month == 1


PARAMS = gnss.GnssParams(
    months=frozenset({9, 10, 11, 12, 1, 2, 3, 4}),
    night_start=21,
    night_end=3,
    peak_hour=0,
    year_from=2025,
    year_to=2028,
    source_url="",
    portal_url="",
    sunset_offset_min=60,
)


def sun(day, hour, minute):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=SANTIAGO)


class TestGnssFollowsTheSunset:
    D1, D2 = date(2026, 10, 19), date(2026, 12, 21)

    def test_the_window_starts_an_offset_after_the_forecast_sunset(self):
        sunsets = {self.D1: sun(self.D1, 19, 50)}
        before = datetime(2026, 10, 19, 20, 49, tzinfo=SANTIAGO)
        inside = datetime(2026, 10, 19, 20, 50, tzinfo=SANTIAGO)
        assert gnss.window_state(before, PARAMS, sunsets)["active"] is False
        assert gnss.window_state(inside, PARAMS, sunsets)["active"] is True
        # sin pronóstico sigue valiendo las 21:00 de siempre
        assert gnss.window_state(inside, PARAMS)["active"] is False

    def test_a_later_sunset_moves_the_start_later(self):
        sunsets = {self.D1: sun(self.D1, 19, 50), self.D2: sun(self.D2, 20, 55)}
        first = gnss.window_state(
            datetime(2026, 10, 19, 12, 0, tzinfo=SANTIAGO), PARAMS, sunsets
        )
        assert first["next_start"] == sun(self.D1, 20, 50)
        dec = gnss.window_state(
            datetime(2026, 12, 21, 12, 0, tzinfo=SANTIAGO), PARAMS, sunsets
        )
        assert dec["next_start"] == sun(self.D2, 21, 55)

    def test_the_offset_comes_from_the_setting(self, settings):
        settings.GNSS_SCINT_SUNSET_OFFSET_MIN = 30
        assert gnss.params_from_settings().sunset_offset_min == 30
        del settings.GNSS_SCINT_SUNSET_OFFSET_MIN
        assert gnss.params_from_settings().sunset_offset_min == 60

    def test_the_end_does_not_change(self):
        sunsets = {self.D1: sun(self.D1, 19, 50)}
        now = datetime(2026, 10, 19, 23, 0, tzinfo=SANTIAGO)
        assert gnss.window_state(now, PARAMS, sunsets)["next_end"] == datetime(
            2026, 10, 20, 3, 0, tzinfo=SANTIAGO
        )

    def test_a_day_without_a_sunset_falls_back_to_the_fixed_hour(self):
        sunsets = {self.D1: sun(self.D1, 19, 50)}
        state_ = gnss.window_state(
            datetime(2026, 10, 20, 12, 0, tzinfo=SANTIAGO), PARAMS, sunsets
        )
        assert state_["next_start"] == sun(date(2026, 10, 20), 21, 0)


class TestGnssCardIsPure:
    """LV-358: `build_gnss_card(now, sunsets, city)` no pide pronóstico: se lo pasan."""

    def test_the_card_shows_sunset_and_nightfall_with_the_city(self, forecast):
        sunsets, _zone = gnss.sunsets_from_forecast(forecast)
        moment = datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO)
        card = gnss_tags.build_gnss_card(moment, sunsets, "Santiago")
        assert card["status"] == "on"
        assert (card["sunset"], card["dusk"], card["sunset_city"]) == (
            "19:50",
            "20:50",
            "Santiago",
        )

    def test_without_sunsets_it_uses_the_fixed_hours_and_hides_the_line(self):
        moment = datetime(2026, 10, 19, 20, 55, tzinfo=SANTIAGO)
        card = gnss_tags.build_gnss_card(moment, {}, "")
        assert card["status"] == "off" and card["sunset"] is None
        assert card["next_start"].strftime("%H:%M") == "21:00"

    def test_an_unreadable_forecast_gives_no_sunsets_and_never_raises(self):
        assert gnss.sunsets_from_forecast(None)[0] == {}
        broken = {"timezone": "Nowhere/Land", "daily": [{"time": "x", "sunset": "y"}]}
        assert gnss.sunsets_from_forecast(broken)[0] == {}

    def test_the_module_cannot_reach_the_network(self):
        # La salida a la red del panel (hallazgo de LV-358) nacía de que este módulo importaba el
        # cliente del tiempo; sin el import no hay forma de llamarlo.
        assert not hasattr(gnss_tags, "weather_client")
        assert not hasattr(gnss_tags, "forecast_sunsets")


@pytest.mark.django_db
class TestThePanelAsksForNoForecast:
    """LV-358: armar el panel no pide el pronóstico; la franja «Entorno hoy» lo pide por htmx, aparte."""

    def test_the_dashboard_renders_without_calling_the_forecast(self, monkeypatch):
        def boom(lat, lon):
            raise AssertionError("armar el panel no puede pedir el pronóstico")

        pin_now(monkeypatch, datetime(2026, 10, 19, 20, 55, tzinfo=SANTIAGO))
        monkeypatch.setattr(weather_client, "panel_forecast", boom)
        content = (
            login_as("view_userweatherlocation")
            .get(reverse("dashboard"), headers={"Accept-Language": "en"})
            .content.decode()
        )
        # El hueco de la franja está, pero vacío: el pronóstico se pide cuando el navegador lo carga.
        assert 'id="env-strip"' in content and 'id="gnss-card"' not in content
        assert "nightfall" not in content
