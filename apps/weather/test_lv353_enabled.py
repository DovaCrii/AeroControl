"""LV-353: la tarjeta del tiempo vuelve encendida por omisión, con Santiago como ciudad.

Se fija el interruptor de punta a punta (ajuste -> etiqueta -> hueco -> vistas -> cliente -> caché),
la ciudad por omisión, que una petición fallida no deje el esqueleto para siempre (`weather-card.js`)
y que sin salida a Internet salga el estado de error con UNA advertencia por ventana de caché.
Sin red: `conftest.py` hace fallar `urlopen`; aquí se sustituye por uno que lanza `URLError`.
"""

import logging
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils.translation import gettext

from apps.core import weather as weather_client
from apps.core.testing import login_as
from apps.weather import panel as panel_module

ROOT = Path(__file__).resolve().parents[2]
BASE_SETTINGS = (ROOT / "config/settings/base.py").read_text(encoding="utf-8")
JS = (ROOT / "static/js/weather-card.js").read_text(encoding="utf-8")
VIEW = "view_userweatherlocation"


def _setting_default(name):
    match = re.search(
        rf'^{name} = config\(\s*"{name}",\s*default=([^,)\n]+)', BASE_SETTINGS, re.M
    )
    assert match, name
    return match.group(1).strip()


class TestDefaults:
    def test_the_switch_is_on_by_default(self):
        assert _setting_default("WEATHER_ENABLED") == "True"

    def test_the_default_city_is_santiago(self):
        assert _setting_default("WEATHER_DEFAULT_LABEL") == '"Santiago"'
        assert _setting_default("WEATHER_DEFAULT_LAT") == '"-33.4489"'
        assert _setting_default("WEATHER_DEFAULT_LON") == '"-70.6693"'
        assert _setting_default("WEATHER_DEFAULT_TZ") == '"America/Santiago"'

    @pytest.mark.django_db
    def test_someone_without_a_city_gets_santiago(self, settings, monkeypatch):
        settings.WEATHER_ENABLED = True  # los WEATHER_DEFAULT_* quedan los reales
        seen = {}

        def fake(lat, lon):
            seen["at"] = (lat, lon)

        monkeypatch.setattr(weather_client, "panel_forecast", fake)
        response = login_as(VIEW).get(reverse("weather-panel"))
        assert response.status_code == 200
        assert seen["at"] == (-33.4489, -70.6693)


@pytest.mark.django_db
class TestSwitchEndToEnd:
    @pytest.mark.parametrize(
        "name", ["weather-panel", "weather-location", "weather-search"]
    )
    def test_off_means_404_for_every_route_even_with_permission(self, settings, name):
        settings.WEATHER_ENABLED = False
        assert login_as(VIEW).get(reverse(name)).status_code == 404

    def test_off_means_404_before_login_too(self, settings, client):
        settings.WEATHER_ENABLED = False
        assert client.get(reverse("weather-panel")).status_code == 404

    def test_off_makes_no_outgoing_call_and_no_slot(self, settings, monkeypatch):
        settings.WEATHER_ENABLED = False
        assert weather_client.panel_forecast(-33.4, -70.6) is None
        assert weather_client.search_places("Santiago") is None
        content = login_as(VIEW).get(reverse("dashboard")).content.decode()
        assert "wx-card" not in content and "weather-card.js" not in content

    def test_on_without_permission_draws_no_slot(self, settings):
        settings.WEATHER_ENABLED = True
        content = login_as().get(reverse("dashboard")).content.decode()
        assert "wx-card" not in content and "weather-card.js" not in content

    def test_on_with_permission_draws_the_slot_and_loads_the_script(self, settings):
        settings.WEATHER_ENABLED = True
        content = login_as(VIEW).get(reverse("dashboard")).content.decode()
        assert f'hx-get="{reverse("weather-panel")}"' in content
        assert "data-wx-error" in content
        assert "js/weather-card.js" in content
        assert "hx-request=" in content  # tiempo máximo del lado del navegador

    def test_one_function_decides(self, settings):
        for value in (True, False):
            settings.WEATHER_ENABLED = value
            assert panel_module.weather_enabled() is value


class TestFailedRequestsDoNotLeaveTheSkeleton:
    def test_the_script_listens_to_the_three_failure_events(self):
        for event in ("htmx:responseError", "htmx:sendError", "htmx:timeout"):
            assert f'"{event}"' in JS

    def test_the_script_swaps_in_the_error_template_and_reprocesses_it(self):
        assert "template[data-wx-error]" in JS
        assert "replaceWith" in JS and "htmx.process" in JS

    def test_the_script_has_no_inline_handlers_or_network_of_its_own(self):
        assert "fetch(" not in JS and "XMLHttpRequest" not in JS and "eval(" not in JS

    @pytest.mark.django_db
    def test_the_error_partial_exists_with_an_accessible_retry(self, settings):
        from django.template.loader import render_to_string

        html = render_to_string("weather/_panel_card.html", {"state": "error"})
        assert (
            gettext(
                "The weather is not available right now. It will be tried again shortly."
            )
            in html
        )
        assert 'role="status"' in html
        assert "data-wx-retry" in html and "hx-get=" in html
        assert f">{gettext('Retry')}</button>" in html
        assert "onclick" not in html and "hx-on" not in html


@pytest.mark.django_db
class TestNoInternetOnTheServer:
    @pytest.fixture(autouse=True)
    def _offline(self, settings, monkeypatch):
        settings.WEATHER_ENABLED = True
        settings.WEATHER_FAKE_FIXTURE = False
        cache.clear()
        self.calls = 0

        def unreachable(*args, **kwargs):
            self.calls += 1
            raise urllib.error.URLError("secret-host.example")

        monkeypatch.setattr(urllib.request, "urlopen", unreachable)
        yield
        cache.clear()

    def test_the_card_shows_the_error_state_with_retry(self):
        client = login_as(VIEW)
        response = client.get(reverse("weather-panel"))
        content = response.content.decode()
        assert response.status_code == 200
        assert (
            gettext(
                "The weather is not available right now. It will be tried again shortly."
            )
            in content
        )
        assert "data-wx-retry" in content
        assert "wx-hours" not in content

    def test_one_warning_per_cache_window_without_url_or_data(self, caplog):
        with caplog.at_level(logging.WARNING, logger="apps.core.weather"):
            for _ in range(5):
                assert weather_client.panel_forecast(-33.4489, -70.6693) is None
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1 and self.calls == 1
        text = warnings[0].getMessage() + str(warnings[0].__dict__)
        assert (
            "secret-host" not in text
            and "open-meteo" not in text
            and "-33.4" not in text
        )

    def test_a_new_window_warns_again(self, caplog):
        with caplog.at_level(logging.WARNING, logger="apps.core.weather"):
            weather_client.panel_forecast(-33.4489, -70.6693)
            cache.clear()  # vence la ventana
            weather_client.panel_forecast(-33.4489, -70.6693)
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2

    def test_the_wait_is_bounded(self, settings):
        assert settings.WEATHER_TIMEOUT_SECONDS <= 4
