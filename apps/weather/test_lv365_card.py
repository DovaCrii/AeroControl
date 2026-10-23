"""LV-365: la tarjeta con datos de MET Norway dice lo que no tiene y atribuye a quien corresponde.

Sin red: `urlopen` devuelve una respuesta de MET inventada con la forma real.
"""

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from apps.core import weather
from apps.core.test_lv365_met_provider import FakeResponse, met_payload
from apps.core.testing import login_as
from apps.weather.models import UserWeatherLocation

VIEW = "view_userweatherlocation"


@pytest.fixture
def met_card(settings, monkeypatch):
    cache.clear()
    settings.WEATHER_ENABLED = True
    settings.WEATHER_PROVIDER = "met_norway"
    settings.WEATHER_USER_AGENT = "test-agent (test-contact)"
    settings.WEATHER_API_URL = "https://api.example.test/locationforecast/complete"
    settings.WEATHER_DEFAULT_LABEL = ""
    monkeypatch.setattr(
        weather.urllib.request,
        "urlopen",
        lambda request, timeout=None: FakeResponse(met_payload()),
    )
    yield
    cache.clear()


def _page(settings=None):
    client = login_as(VIEW)
    UserWeatherLocation.objects.create(
        user=client.user,
        label="Santiago",
        latitude="-33.4489",
        longitude="-70.6693",
        timezone="America/Santiago",
        source="search",
    )
    return client.get(reverse("weather-panel")).content.decode()


@pytest.mark.django_db
class TestMetCard:
    def test_it_credits_met_norway_and_the_licence(self, met_card):
        content = _page()
        assert gettext("Based on data from") in content
        assert 'href="https://www.met.no/en"' in content and "MET Norway" in content
        assert "https://creativecommons.org/licenses/by/4.0/" in content
        assert "open-meteo" not in content.lower()

    def test_it_names_what_the_source_does_not_give(self, met_card):
        content = _page()
        assert gettext("Not available from this source") in content
        assert content.count(gettext("Not available")) >= 2  # ráfagas y visibilidad
        assert gettext("Chance of rain") in content

    def test_no_events_is_not_a_false_calm(self, met_card):
        content = _page()
        assert "wx-events" not in content or "wx-none" in content
        assert (
            gettext(
                "No notable weather events in the available data for the next 48 hours"
            )
            in content
        )
        assert (
            gettext("No notable weather events expected in the next 48 hours")
            not in content
        )

    def test_the_spanish_card_is_translated(self, met_card):
        with translation.override("es"):
            content = _page()
        assert "Basado en datos de" in content
        assert "No disponible en esta fuente" in content

    def test_without_a_user_agent_the_card_says_not_available(self, met_card, settings):
        settings.WEATHER_USER_AGENT = ""
        content = _page()
        assert (
            gettext(
                "The weather is not available right now. It will be tried again shortly."
            )
            in content
        )
        assert "wx-hours" not in content

    def test_open_meteo_forecast_keeps_its_credit_and_no_limits(
        self, met_card, settings, monkeypatch
    ):
        cache.clear()
        settings.WEATHER_PROVIDER = "open_meteo"
        monkeypatch.setattr(
            weather.urllib.request,
            "urlopen",
            lambda request, timeout=None: FakeResponse(
                (weather._FAKE_DIR / "weather_panel_forecast.json").read_bytes()
            ),
        )
        content = _page()
        assert "Open-Meteo.com" in content
        assert gettext("Not available from this source") not in content
