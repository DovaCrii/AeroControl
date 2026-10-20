"""LV-352 fase 1: la ventana estadística del centelleo GNSS (`apps/weather/gnss.py`).

Función pura y sin red: toda hora se FIJA en la prueba (el verde no depende del día) y se pasa
`now` directo. Se cubren los bordes de la noche (21:00 / 03:00), el cruce de medianoche, a qué mes
pertenece la madrugada, los límites del período, los cambios de hora de 2026 y los parámetros por
entorno. Las mutaciones comprobadas a mano van al final del módulo.
"""

import urllib.request
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

import pytest

from apps.core.testing import pin_now
from apps.weather import gnss

SANTIAGO = ZoneInfo("America/Santiago")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("la ventana GNSS no puede salir a la red")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=SANTIAGO)


def real(moment):
    """El instante real: dos datetimes de la MISMA zona se restan por reloj de pared."""
    return moment.astimezone(dt_timezone.utc)


def active(*args):
    return gnss.window_state(at(*args))["active"]


class TestNightEdges:
    def test_21_00_starts_and_20_59_does_not(self):
        assert active(2026, 1, 15, 20, 59) is False
        assert active(2026, 1, 15, 21, 0) is True

    def test_03_00_ends_and_02_59_is_still_in(self):
        assert active(2026, 1, 16, 2, 59) is True
        assert active(2026, 1, 16, 3, 0) is False

    def test_midnight_is_inside(self):
        assert active(2026, 1, 16, 0, 0) is True

    def test_midday_is_never_in(self):
        assert active(2026, 1, 15, 12, 0) is False


class TestWhichMonthTheNightBelongsTo:
    def test_the_early_morning_of_1_may_is_an_april_night(self):
        assert active(2026, 4, 30, 23, 59) is True
        assert active(2026, 5, 1, 0, 30) is True
        assert active(2026, 5, 1, 2, 59) is True

    def test_1_may_evening_is_out_and_the_next_window_is_1_september(self):
        state = gnss.window_state(at(2026, 5, 1, 21, 0))
        assert state["active"] is False
        assert state["next_start"] == at(2026, 9, 1, 21, 0)

    def test_the_early_morning_of_1_september_is_an_august_night_and_does_not_count(
        self,
    ):
        assert active(2026, 9, 1, 0, 30) is False
        assert active(2026, 8, 31, 23, 0) is False

    def test_1_september_evening_counts(self):
        assert active(2026, 9, 1, 21, 0) is True

    def test_january_counts(self):
        assert active(2026, 1, 10, 22, 0) is True

    def test_a_winter_night_never_counts(self):
        for month in (5, 6, 7, 8):
            assert active(2026, month, 15, 23, 0) is False


class TestThePeriod:
    def test_31_dec_2024_is_before_the_period(self):
        state = gnss.window_state(at(2024, 12, 31, 23, 0))
        assert state["active"] is False
        assert state["in_period"] is False and state["period_over"] is False
        assert state["next_start"] == at(2025, 1, 1, 21, 0)

    def test_the_first_covered_night_is_1_january_2025(self):
        assert active(2025, 1, 1, 22, 0) is True

    def test_30_april_2028_is_still_covered(self):
        state = gnss.window_state(at(2028, 4, 30, 23, 0))
        assert state["active"] is True and state["in_period"] is True

    def test_may_2028_is_outside_the_period_and_invents_no_window(self):
        state = gnss.window_state(at(2028, 5, 15, 22, 0))
        assert state["active"] is False
        assert state["in_period"] is False and state["period_over"] is True
        assert state["next_start"] is None and state["next_end"] is None

    def test_late_2028_and_later_invent_nothing(self):
        for moment in (at(2028, 10, 1, 23, 0), at(2030, 1, 1, 23, 0)):
            state = gnss.window_state(moment)
            assert state["active"] is False and state["period_over"] is True
            assert state["next_start"] is None

    def test_the_last_window_of_the_period_has_no_next_one(self):
        state = gnss.window_state(at(2028, 4, 30, 23, 0))
        assert state["next_start"] is None
        assert state["next_end"] == at(2028, 5, 1, 3, 0)

    def test_next_window_during_the_day_gives_start_and_end(self):
        state = gnss.window_state(at(2026, 1, 15, 12, 0))
        assert state["next_start"] == at(2026, 1, 15, 21, 0)
        assert state["next_end"] == at(2026, 1, 16, 3, 0)

    def test_while_active_the_end_is_the_current_one(self):
        state = gnss.window_state(at(2026, 1, 15, 23, 0))
        assert state["next_start"] is None
        assert state["next_end"] == at(2026, 1, 16, 3, 0)


class TestTheLocalZoneIsUsedNeverUtc:
    def test_the_same_instant_is_read_in_santiago_not_in_utc(self):
        # 2026-01-16 00:30 UTC es 2026-01-15 21:30 en Santiago (-03): dentro de la ventana.
        utc_moment = datetime(2026, 1, 16, 0, 30, tzinfo=dt_timezone.utc)
        assert gnss.window_state(utc_moment)["active"] is True
        # 2026-01-15 23:30 UTC es 20:30 en Santiago: todavía no (en UTC ya sería de noche).
        assert (
            gnss.window_state(datetime(2026, 1, 15, 23, 30, tzinfo=dt_timezone.utc))[
                "active"
            ]
            is False
        )

    def test_the_project_zone_is_santiago(self, settings):
        assert settings.TIME_ZONE == "America/Santiago"


class TestDaylightSavingChanges:
    def test_september_2026_the_midnight_that_does_not_exist(self):
        # La noche del sábado 5 al domingo 6: a las 24:00 el reloj salta a las 01:00.
        assert at(2026, 9, 6, 1, 30).utcoffset() == timedelta(hours=-3)
        assert active(2026, 9, 5, 23, 30) is True
        assert active(2026, 9, 6, 1, 30) is True
        # El inicio sigue a las 21:00 locales (-04) y el fin a las 03:00 locales (-03).
        state = gnss.window_state(at(2026, 9, 5, 12, 0))
        assert state["next_start"] == at(2026, 9, 5, 21, 0)
        assert state["next_end"] == at(2026, 9, 6, 3, 0)
        assert state["next_start"].utcoffset() == timedelta(hours=-4)
        assert state["next_end"].utcoffset() == timedelta(hours=-3)
        assert active(2026, 9, 6, 2, 59) is True
        assert active(2026, 9, 6, 3, 0) is False

    def test_a_start_hour_inside_the_september_gap_moves_forward(self, settings):
        settings.GNSS_SCINT_NIGHT_START = 0
        settings.GNSS_SCINT_NIGHT_END = 3
        # 00:00 del 6 de septiembre no existe: la ventana de esa noche empieza a la 01:00.
        zone_start = gnss._local(SANTIAGO, date(2026, 9, 6), 0)
        assert (zone_start.hour, zone_start.utcoffset()) == (
            1,
            timedelta(hours=-3),
        )

    def test_april_2026_the_repeated_hour_uses_the_first_occurrence(self):
        # Sábado 4 de abril: a las 24:00 (-03) el reloj vuelve a las 23:00 (-04).
        first = at(2026, 4, 4, 23, 30)
        second = first.replace(fold=1)
        assert first.utcoffset() == timedelta(hours=-3)
        assert second.utcoffset() == timedelta(hours=-4)
        assert gnss.window_state(first)["active"] is True
        assert gnss.window_state(second)["active"] is True
        state = gnss.window_state(at(2026, 4, 4, 12, 0))
        assert state["next_start"] == at(2026, 4, 4, 21, 0)
        # Una hora real más larga: 03:00 del domingo ya está en -04.
        assert state["next_end"].utcoffset() == timedelta(hours=-4)
        assert real(state["next_end"]) - real(state["next_start"]) == timedelta(hours=7)
        assert active(2026, 4, 5, 2, 59) is True
        assert active(2026, 4, 5, 3, 0) is False

    def test_the_september_window_is_one_hour_shorter(self):
        state = gnss.window_state(at(2026, 9, 5, 12, 0))
        assert real(state["next_end"]) - real(state["next_start"]) == timedelta(hours=5)


class TestEnvironmentParameters:
    def test_defaults_are_the_source_values(self):
        params = gnss.params_from_settings()
        assert params.months == frozenset({9, 10, 11, 12, 1, 2, 3, 4})
        assert (params.night_start, params.night_end, params.peak_hour) == (21, 3, 0)
        assert (params.year_from, params.year_to) == (2025, 2028)
        assert params.portal_url == "https://centelleo.geocom.cl"
        assert params.source_url.startswith("https://www.geocom.cl/blogs/news/")

    def test_the_night_hours_come_from_the_environment(self, settings):
        settings.GNSS_SCINT_NIGHT_START = 22
        settings.GNSS_SCINT_NIGHT_END = 4
        assert active(2026, 1, 15, 21, 30) is False
        assert active(2026, 1, 15, 22, 0) is True
        assert active(2026, 1, 16, 3, 30) is True
        assert active(2026, 1, 16, 4, 0) is False

    def test_the_months_come_from_the_environment(self, settings):
        settings.GNSS_SCINT_MONTHS = "6,7"
        assert active(2026, 6, 15, 23, 0) is True
        assert active(2026, 1, 15, 23, 0) is False

    def test_the_years_come_from_the_environment(self, settings):
        settings.GNSS_SCINT_YEARS = "2026"
        assert gnss.window_state(at(2025, 6, 1, 12, 0))["in_period"] is False
        assert active(2026, 2, 10, 23, 0) is True
        assert gnss.window_state(at(2027, 1, 10, 23, 0))["period_over"] is True

    def test_pin_now_fixes_the_instant(self, monkeypatch):
        from django.utils import timezone

        moment = pin_now(monkeypatch, at(2026, 1, 15, 21, 0))
        assert timezone.now() == moment
        assert gnss.window_state(timezone.now())["active"] is True
