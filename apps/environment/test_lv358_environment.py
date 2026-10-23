"""LV-358 (E1): la sección «Entorno». Sin red: el pronóstico es el fixture del 2026-10-19 y la hora se fija.

Se fija: 403 por pestaña y concentrador «cualquiera de»; que no haya enlace a una pestaña no permitida (ni a
una cuya ruta no existe todavía); una sola ciudad/zona/pronóstico para amanecer, puesta y ventana; que el
resumen sean hechos (palabras prohibidas, sin rojo); un solo texto «Referencial»; el contraste de los niveles
calculado; y que la etiqueta del centelleo ya no sale a la red al armar una página.
"""

import json
import re
import socket
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import translation

from apps.core import weather as weather_client
from apps.core.test_lv315_identity_foundation import (
    IDENTITY,
    _contrast,
    _declarations,
    _resolve,
    _theme_tokens,
)
from apps.core.testing import login_as, pin_now
from apps.environment import levels, tabs
from apps.environment.summary import build_summary, season_label
from apps.weather import gnss
from apps.weather import panel as panel_module
from apps.weather.models import UserWeatherLocation

SANTIAGO = ZoneInfo("America/Santiago")
FIXTURE = Path(weather_client.__file__).parent / "testdata/weather_panel_forecast.json"
VIEW = "view_userweatherlocation"
NIGHT = datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO)  # dentro de la ventana
EVENING = datetime(2026, 10, 19, 20, 0, tzinfo=SANTIAGO)  # antes de la ventana

IDENTITY_PATH = Path(__file__).resolve().parents[2] / "static" / "css" / "identity.css"

HUB, WEATHER, GNSS = (
    reverse("environment-hub"),
    reverse("environment-weather"),
    reverse("environment-gnss"),
)


@pytest.fixture(autouse=True)
def english():
    """Las cadenas se comparan en inglés (la fuente); las pruebas de español se activan aparte."""
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("la sección Entorno no puede salir a la red en pruebas")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def forecast():
    return weather_client._parse_panel(json.loads(FIXTURE.read_text("utf-8")))


@pytest.fixture
def calls():
    return []


@pytest.fixture
def on(settings, monkeypatch, forecast, calls):
    settings.WEATHER_ENABLED = True
    settings.GNSS_SCINTILLATION_ENABLED = True
    settings.WEATHER_DEFAULT_LABEL = ""

    def fake(lat, lon, zone=None):
        calls.append((round(float(lat), 3), round(float(lon), 3)))
        return forecast

    monkeypatch.setattr(weather_client, "panel_forecast", fake)
    pin_now(monkeypatch, NIGHT)
    return forecast


def _city(client, label="Santiago", lat="-33.4489", lon="-70.6693"):
    return UserWeatherLocation.objects.create(
        user=client.user,
        label=label,
        latitude=lat,
        longitude=lon,
        timezone="America/Santiago",
        source="search",
    )


def _get(client, url, **extra):
    return client.get(url, headers={"Accept-Language": "en"}, **extra)


def _section(html):
    """Sólo la sección: el menú de al lado tiene su propio vocabulario (el contador rojo de alertas)."""
    body = html.split('class="env-section"')[1]
    return body.split('class="env-legend"')[0]


@pytest.mark.django_db
class TestAccess:
    @pytest.mark.parametrize("url", [WEATHER, GNSS])
    def test_each_tab_gives_403_without_its_permission(self, on, url):
        assert _get(login_as(), url).status_code == 403

    @pytest.mark.parametrize("url", [HUB, WEATHER, GNSS])
    def test_anonymous_goes_to_login(self, client, on, url):
        assert client.get(url).status_code == 302

    def test_each_tab_opens_with_the_permission(self, on):
        client = login_as(VIEW)
        _city(client)
        assert _get(client, WEATHER).status_code == 200
        assert _get(client, GNSS).status_code == 200

    def test_the_hub_goes_to_the_first_allowed_tab(self, on):
        response = _get(login_as(VIEW), HUB)
        assert response.status_code == 302 and response.url == WEATHER

    def test_the_hub_is_403_without_any_tab_permission(self, on):
        assert _get(login_as(), HUB).status_code == 403

    def test_the_hub_skips_a_tab_that_is_switched_off(self, on, settings):
        settings.WEATHER_ENABLED = False
        client = login_as(VIEW)
        response = _get(client, HUB)
        assert response.status_code == 302 and response.url == GNSS
        assert _get(client, WEATHER).status_code == 404

    def test_everything_off_is_403_on_the_hub_and_404_on_the_tabs(self, on, settings):
        settings.WEATHER_ENABLED = False
        settings.GNSS_SCINTILLATION_ENABLED = False
        client = login_as(VIEW)
        assert _get(client, HUB).status_code == 403
        assert _get(client, WEATHER).status_code == 404
        assert _get(client, GNSS).status_code == 404

    def test_the_environment_has_no_tenant_and_reads_only_the_callers_row(self, on):
        """Sin tenant en esta app: la ciudad es la de `request.user`, nunca la de otra persona."""
        other = login_as(VIEW, "view_aircraft")
        _city(other, "Antofagasta", "-23.65", "-70.4")
        mine = login_as(VIEW)
        _city(mine, "Punta Arenas", "-53.16", "-70.91")
        content = _get(mine, WEATHER).content.decode()
        assert "Punta Arenas" in content and "Antofagasta" not in content


@pytest.mark.django_db
class TestTheTabsShownAreTheOnesYouCanOpen:
    def _links(self, content):
        return set(re.findall(r'<a href="([^"]+)" class="env-tab', content))

    def test_a_person_sees_only_the_allowed_tabs(self, on):
        client = login_as(VIEW)
        _city(client)
        assert self._links(_get(client, WEATHER).content.decode()) == {WEATHER, GNSS}

    def test_a_tab_switched_off_has_no_link(self, on, settings):
        settings.GNSS_SCINTILLATION_ENABLED = False
        client = login_as(VIEW)
        _city(client)
        assert self._links(_get(client, WEATHER).content.decode()) == {WEATHER}

    def test_the_airspace_tab_shows_once_its_route_exists_and_with_its_permission(
        self, on
    ):
        """LV-357 (F3) registró `airspace-map`: la pestaña declarada en E1 aparece sola, con `view_airspacefeature`."""
        client = login_as()
        client.user.is_superuser = True
        client.user.save()
        keys = [tab["key"] for tab in tabs.tabs_for(client.user)]
        assert keys == ["weather", "gnss", "airspace"]
        assert "/environment/airspace/" in _get(client, WEATHER).content.decode()
        weather_only = login_as(VIEW).user
        assert "airspace" not in [tab["key"] for tab in tabs.tabs_for(weather_only)]
        airspace_only = login_as("view_airspacefeature").user
        assert [tab["key"] for tab in tabs.tabs_for(airspace_only)] == ["airspace"]

    def test_a_registered_route_makes_a_declared_tab_appear(self, on, monkeypatch):
        extra = tabs.Tab("extra", "health", "Extra", "weather.view_userweatherlocation")
        monkeypatch.setattr(tabs, "TABS", tabs.TABS + (extra,))
        user = login_as(VIEW).user
        assert [t["key"] for t in tabs.tabs_for(user)] == ["weather", "gnss", "extra"]

    def test_a_tab_whose_permission_is_missing_is_not_listed(self, on, monkeypatch):
        extra = tabs.Tab("extra", "health", "Extra", "registry.view_aircraft")
        monkeypatch.setattr(tabs, "TABS", tabs.TABS + (extra,))
        user = login_as(VIEW).user
        assert "extra" not in [t["key"] for t in tabs.tabs_for(user)]


@pytest.mark.django_db
class TestTheMenuEntry:
    def test_one_entry_when_a_tab_is_allowed(self, on):
        content = _get(login_as(VIEW), reverse("dashboard")).content.decode()
        assert content.count('icon-environment"') == 1
        assert f'href="{WEATHER}"' in content

    def test_no_entry_without_any_tab_permission(self, on):
        content = _get(login_as(), reverse("dashboard")).content.decode()
        assert "icon-environment" not in content

    def test_no_entry_when_every_tab_is_off(self, on, settings):
        settings.WEATHER_ENABLED = False
        settings.GNSS_SCINTILLATION_ENABLED = False
        content = _get(login_as(VIEW), reverse("dashboard")).content.decode()
        assert "icon-environment" not in content


@pytest.mark.django_db
class TestOneCityOneZoneOneForecast:
    def test_the_header_and_the_window_use_the_same_forecast_for_the_persons_city(
        self, on, calls
    ):
        client = login_as(VIEW)
        _city(client, "Punta Arenas", "-53.16", "-70.91")
        weather = _get(client, WEATHER).content.decode()
        gnss_tab = _get(client, GNSS).content.decode()
        # Toda consulta fue por la ciudad de la persona; ninguna por la de omisión (Santiago).
        assert set(calls) == {(-53.16, -70.91)}
        assert "Sunset</dt><dd>19:50" in weather
        assert "Sunset 19:50 · nightfall 20:50 (per the forecast for Punta Arenas)" in (
            gnss_tab
        )

    def test_the_summary_window_starts_from_the_same_sunset_it_shows(self, forecast):
        summary = build_summary(EVENING, forecast, [], "Santiago")
        assert summary.sunset_text == "19:50"
        assert summary.gnss["sunset"] == summary.sunset_text
        assert summary.gnss["next_start"].strftime("%H:%M") == "20:50"
        # Sin pronóstico la ventana vuelve a las horas fijas, y la puesta no se inventa.
        bare = build_summary(EVENING, None, [], "")
        assert bare.sunset_text == "" and bare.gnss["next_start"].hour == 21

    def test_the_panel_card_never_asks_for_a_forecast(self, monkeypatch, settings):
        def boom(lat, lon, zone=None):
            raise AssertionError("el panel no puede pedir el pronóstico")

        settings.GNSS_SCINTILLATION_ENABLED = True
        monkeypatch.setattr(weather_client, "panel_forecast", boom)
        client = login_as()
        assert _get(client, reverse("dashboard")).status_code == 200


class TestTheSummaryIsFactsNotAVerdict:
    FORBIDDEN = (
        "puede volar",
        "no puede volar",
        "apto",
        "go/no-go",
        "no-go",
        "can fly",
        "cannot fly",
        "safe to fly",
        "cleared to fly",
    )
    EVENTS = [
        {
            "type": "gusts",
            "level": "strong",
            "start": "2026-10-19T14:00",
            "end": "2026-10-19T18:00",
        },
        {
            "type": "thunderstorm",
            "level": "attention",
            "start": "2026-10-19T16:00",
            "end": "2026-10-19T17:00",
        },
    ]

    def _texts(self, forecast):
        out = []
        for moment in (NIGHT, EVENING, datetime(2026, 6, 1, 12, tzinfo=SANTIAGO)):
            for events in ([], self.EVENTS):
                summary = build_summary(moment, forecast, events, "Santiago")
                out += [f"{line.text} {line.level_label}" for line in summary.lines]
        out += [line.text for line in build_summary(NIGHT, None, [], "").lines]
        return out

    @pytest.mark.parametrize("language", ["en", "es"])
    def test_no_line_says_whether_a_flight_can_happen(self, forecast, language):
        with translation.override(language):
            for text in self._texts(forecast):
                for word in self.FORBIDDEN:
                    assert word not in text.lower(), (language, word, text)

    def test_there_is_one_event_line_and_one_gnss_line(self, forecast):
        lines = build_summary(NIGHT, forecast, self.EVENTS, "Santiago").lines
        assert [line.level for line in lines] == ["strong", "attention"]
        assert "2 weather events expected in 48 hours: Gusts, Thunderstorm" in (
            lines[0].text
        )

    def test_a_quiet_day_says_so_in_facts(self, forecast):
        lines = build_summary(EVENING, forecast, [], "Santiago").lines
        assert lines[0].level == "info"
        assert (
            "No notable weather events expected in the next 48 hours" in lines[0].text
        )
        assert lines[1].text.startswith("Typical scintillation window: next on")

    @pytest.mark.django_db
    def test_the_rendered_section_never_uses_the_critical_red(self, on, monkeypatch):
        strong = [dict(self.EVENTS[0], value=80, unit="km/h")]
        monkeypatch.setattr(weather_client, "regional_events", lambda f: strong)
        client = login_as(VIEW)
        _city(client)
        for url in (WEATHER, GNSS):
            html = _section(_get(client, url).content.decode())
            assert "env-lvl--strong" in html or url == GNSS
            assert not re.search(r"critical|danger|\bred\b", html, re.I), url

    def test_the_stylesheet_block_has_no_red_no_motion_and_no_foreign_tokens(self):
        block = IDENTITY[
            IDENTITY.index("/* E7: sección") : IDENTITY.index("/* == F: ilustración")
        ]
        assert not re.search(r"critical|danger|red\b", block, re.I)
        assert not re.search(r"animation|@keyframes|translateX|transition", block)
        defined = set(re.findall(r"(?m)^\s*(--[\w-]+)\s*:", block))
        assert defined and all(name.startswith("--id-env-") for name in defined)


class TestLevels:
    def test_the_weather_events_use_the_common_levels(self):
        assert panel_module.LEVEL_LABELS is levels.LEVEL_LABELS

    def test_symbols_and_order(self):
        assert [levels.level_info(k)[0] for k in levels.LEVEL_ORDER] == ["●", "▲", "◆"]
        assert levels.highest(["info", "strong", "attention"]) == "strong"
        assert levels.highest([]) == "info" and levels.highest(["nope"]) == "info"
        assert levels.level_info("nope") == levels.LEVEL_LABELS["info"]


class TestContrast:
    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize("level", ["info", "attention", "strong"])
    def test_every_level_reaches_4_5_to_1_on_its_background(self, theme, level):
        tokens = _theme_tokens(theme)
        decl = _declarations(IDENTITY, r"\.env-section")
        fg = _resolve(decl[f"--id-env-{level}-fg"], tokens)
        bg = _resolve(decl[f"--id-env-{level}-bg"], tokens)
        assert _contrast(fg, bg) >= 4.5, (level, theme, fg, bg)

    @pytest.mark.parametrize("theme", [0, 1], ids=["light", "dark"])
    def test_the_stale_source_line_reads_on_the_card_surface(self, theme):
        """`app.css` declara cada token una vez por tema, en ese orden (como lo lee `test_lv352`)."""
        app = (Path(IDENTITY_PATH).parent / "app.css").read_text(encoding="utf-8")

        def token(name):
            found = re.findall(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", app)
            assert len(found) == 2, name
            return found[theme]

        assert _contrast(token("sev-warning-text"), token("ac-surface")) >= 4.5


@pytest.mark.django_db
class TestOneReferentialText:
    TEXT = "Information only. It is not a flight condition"

    def test_the_tab_pages_carry_it_once(self, on):
        client = login_as(VIEW)
        _city(client)
        for url in (WEATHER, GNSS):
            content = _get(client, url).content.decode()
            assert content.count(self.TEXT) == 1, url
            assert "gn-ref" not in content and "wx-legend" not in content

    def test_the_embedded_card_drops_its_own_warning_but_the_panel_card_keeps_it(
        self, on
    ):
        client = login_as(VIEW)
        _city(client)
        panel = reverse("weather-panel")
        assert "wx-legend" in _get(client, panel).content.decode()
        embedded = _get(client, panel + "?embed=environment").content.decode()
        assert "wx-legend" not in embedded and 'id="wx-card"' in embedded

    def test_the_weather_tab_loads_the_card_by_htmx_as_the_panel_does(self, on):
        client = login_as(VIEW)
        _city(client)
        content = _get(client, WEATHER).content.decode()
        assert f'hx-get="{reverse("weather-panel")}?embed=environment"' in content
        assert "js/weather-card.js" in content and "js/sky-preview.js" in content

    def test_a_failed_card_retries_inside_the_environment(self, on, monkeypatch):
        monkeypatch.setattr(
            weather_client, "panel_forecast", lambda lat, lon, zone=None: None
        )
        client = login_as(VIEW)
        _city(client)
        retry = _get(client, reverse("weather-panel") + "?embed=environment")
        assert "weather/panel/?embed=environment" in retry.content.decode()


@pytest.mark.django_db
class TestTheGnssTabExplains:
    def test_it_explains_and_declares_the_assumption(self, on):
        client = login_as(VIEW)
        _city(client)
        content = _get(client, GNSS).content.decode()
        for fragment in (
            "Scintillation is a disturbance of satellite signals",
            "September to April",
            "are our interpretation of",
            "Real-time data: see portal",
            "GEOCOM / Trimble",
        ):
            assert fragment in content, fragment

    def test_the_live_state_comes_from_the_common_header(self, on):
        client = login_as(VIEW)
        _city(client)
        content = _get(client, GNSS).content.decode()
        assert "Typical higher-scintillation window: now, until 03:00" in content
        assert 'id="gnss-card"' not in content

    def test_without_a_city_it_still_renders_with_the_fixed_hours(self, on):
        content = _get(login_as(VIEW), GNSS).content.decode()
        assert "Pick your city" in content and "Fixed hours: 21:00 to 03:00." in content

    @translation.override("en")
    def test_the_season_label_follows_the_settings(self, settings):
        assert season_label(gnss.params_from_settings()) == "September to April"
        settings.GNSS_SCINT_MONTHS = "1,2,3"
        assert season_label(gnss.params_from_settings()) == "January to March"
        settings.GNSS_SCINT_MONTHS = "1,3"
        assert season_label(gnss.params_from_settings()) == "January, March"
