"""LV-358 (E2): la franja «Entorno hoy» del panel. Sin red: el pronóstico es el fixture del 2026-10-19.

Se fija: 403/404 del fragmento; que cada celda exista sólo con el permiso de su fuente y su interruptor;
que la franja use la MISMA ciudad, zona y pronóstico que la cabecera de «Entorno»; un solo texto
«Referencial»; el estado de error con «Reintentar»; que el panel no salga a la red ni gane consultas
(`test_lv237` sigue en 49/50) y que la franja tenga su techo propio; que sean hechos y nunca un veredicto
(palabras prohibidas, sin rojo); y que `env-row`, la tarjeta GNSS en línea y la escena del cielo ya no estén
en el panel.
"""

import json
import re
import socket
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.core import weather as weather_client
from apps.core.test_lv315_identity_foundation import IDENTITY
from apps.core.testing import login_as, pin_now
from apps.dashboard import test_lv237_panel_query_budget as budget
from apps.environment import strip as strip_module
from apps.environment.templatetags import environment_tags
from apps.weather import panel as panel_module
from apps.weather.models import UserWeatherLocation

SANTIAGO = ZoneInfo("America/Santiago")
FIXTURE = Path(weather_client.__file__).parent / "testdata/weather_panel_forecast.json"
VIEW = "view_userweatherlocation"
NIGHT = datetime(
    2026, 10, 19, 21, 30, tzinfo=SANTIAGO
)  # dentro de la ventana de centelleo
STRIP = reverse("environment-strip")
DASHBOARD = reverse("dashboard")

# Techo propio de la franja, MEDIDO con el proceso caliente y TODAS las celdas (tiempo, centelleo y espacio
# aéreo): 13. Es lo que paga el fragmento y NO el panel (que sólo dibuja el hueco, sin una consulta).
#
# Nueve son la franja del tiempo y el centelleo (`STRIP_QUERY_BUDGET_WITHOUT_AIRSPACE`, medido el
# 2026-10-20): ocho las paga CUALQUIER petición con sesión (sesión, persona, permisos de usuario y de grupo,
# grupos y el guardado de la sesión con su savepoint) y UNA es de la franja, la fila de
# `UserWeatherLocation`. **Cuatro más el 2026-10-20 (LV-358, E3) por la celda de espacio aéreo**: la foto
# vigente, los tenants de la persona, los permisos vigentes y las zonas P/R/D. Son cuatro **sin importar
# cuántas faenas haya** (una sola consulta de permisos y una de zonas; la distancia se calcula en memoria con
# el bbox como prefiltro). Si sube, se sube acá a propósito y se dice por qué: el pronóstico sale de la
# caché, no de la base.
STRIP_QUERY_BUDGET = 13
STRIP_QUERY_BUDGET_WITHOUT_AIRSPACE = 9

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
        "value": 80,
        "unit": "km/h",
    },
    {
        "type": "thunderstorm",
        "level": "attention",
        "start": "2026-10-19T16:00",
        "end": "2026-10-19T17:00",
    },
    {
        "type": "wind",
        "level": "attention",
        "start": "2026-10-19T12:00",
        "end": "2026-10-19T13:00",
    },
]


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("la franja no puede salir a la red en pruebas")

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
    # El fixture es de 2026-10-19: se fija «ahora» para que nada dependa del día en que se corre.
    monkeypatch.setattr(
        panel_module, "_local_now", lambda f: datetime(2026, 10, 19, 21, 30)
    )
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


def _get(client, url=STRIP):
    return client.get(url, headers={"Accept-Language": "en"})


def _strip(client):
    response = _get(client)
    assert response.status_code == 200
    return response.content.decode()


@pytest.mark.django_db
class TestAccess:
    def test_403_without_the_permission_of_any_source(self, on):
        assert _get(login_as()).status_code == 403

    def test_anonymous_goes_to_login(self, client, on):
        assert client.get(STRIP).status_code == 302

    def test_it_opens_with_the_permission(self, on):
        client = login_as(VIEW)
        _city(client)
        assert 'id="env-strip"' in _strip(client)

    def test_every_switch_off_leaves_the_weather_person_without_a_cell(
        self, on, settings
    ):
        # LV-358 (E3): la celda de espacio aéreo no tiene interruptor, así que ya no hay un 404 «todo
        # apagado»; quien sólo tiene el permiso del tiempo no tiene ninguna celda y recibe 403.
        settings.WEATHER_ENABLED = False
        settings.GNSS_SCINTILLATION_ENABLED = False
        assert _get(login_as(VIEW)).status_code == 403

    def test_the_fragment_reads_only_the_callers_city(self, on, calls):
        other = login_as(VIEW, "view_aircraft")
        _city(other, "Antofagasta", "-23.65", "-70.4")
        mine = login_as(VIEW)
        _city(mine, "Punta Arenas", "-53.16", "-70.91")
        content = _strip(mine)
        assert "Punta Arenas" in content and "Antofagasta" not in content
        assert set(calls) == {(-53.16, -70.91)}


@pytest.mark.django_db
class TestTheCells:
    def test_both_cells_with_the_permission_and_both_switches(self, on):
        client = login_as(VIEW)
        _city(client)
        content = _strip(client)
        assert "env-cell--weather" in content and "env-cell--gnss" in content
        assert "14°" in content  # la temperatura actual del fixture
        assert "Typical higher-scintillation window: now, until 03:00" in content

    def test_the_airspace_cell_needs_both_permissions(self, on):
        # El detalle de la celda (cifras, foto, tenant) se prueba en test_lv358_airspace_cell.
        only_weather = login_as(VIEW)
        _city(only_weather)
        assert "env-cell--airspace" not in _strip(only_weather)
        client = login_as(VIEW, "view_airspacefeature", "view_flightpermission")
        _city(client)
        assert "env-cell--airspace" in _strip(client)

    def test_the_weather_switch_off_leaves_only_the_gnss_cell_and_no_forecast_call(
        self, on, settings, calls
    ):
        settings.WEATHER_ENABLED = False
        client = login_as(VIEW)
        _city(client)
        content = _strip(client)
        assert "env-cell--gnss" in content and "env-cell--weather" not in content
        assert calls == []

    def test_the_gnss_switch_off_leaves_only_the_weather_cell(self, on, settings):
        settings.GNSS_SCINTILLATION_ENABLED = False
        client = login_as(VIEW)
        _city(client)
        content = _strip(client)
        assert "env-cell--weather" in content and "env-cell--gnss" not in content

    def test_without_a_city_the_weather_cell_asks_for_one_and_gnss_still_shows(
        self, on, calls
    ):
        content = _strip(login_as(VIEW))
        assert "Pick your city" in content and reverse("weather-location") in content
        assert "env-cell--gnss" in content
        assert calls == []

    def test_a_missing_forecast_says_so_with_a_retry_and_keeps_the_gnss_cell(
        self, on, monkeypatch
    ):
        monkeypatch.setattr(
            weather_client, "panel_forecast", lambda lat, lon, zone=None: None
        )
        client = login_as(VIEW)
        _city(client)
        content = _strip(client)
        assert "The weather is not available right now" in content
        assert 'data-wx-retry hx-get="' + STRIP in content
        assert "env-cell--gnss" in content

    def test_the_main_event_is_the_strongest_then_the_earliest(self, on, monkeypatch):
        monkeypatch.setattr(weather_client, "regional_events", lambda f: EVENTS)
        client = login_as(VIEW)
        _city(client)
        content = _strip(client)
        cell = content.split("env-cell--weather")[1].split("env-cell--gnss")[0]
        assert "env-lvl--strong" in cell and "Gusts" in cell
        assert "+2 more events" in cell
        assert "Thunderstorm" not in cell

    def test_a_quiet_day_says_so_in_facts(self, on, monkeypatch):
        monkeypatch.setattr(weather_client, "regional_events", lambda f: [])
        client = login_as(VIEW)
        _city(client)
        cell = _strip(client).split("env-cell--weather")[1].split("env-cell--gnss")[0]
        assert "No notable weather events expected in the next 48 hours" in cell
        assert "more event" not in cell

    def test_main_event_picks_level_then_start(self):
        def e(level, start):
            return {"level": level, "start": start}

        early, late = datetime(2026, 10, 19, 8), datetime(2026, 10, 19, 20)
        assert strip_module.main_event([]) is None
        picked = strip_module.main_event(
            [e("attention", early), e("strong", late), e("strong", None)]
        )
        assert picked == e("strong", late)
        assert strip_module.main_event([e("info", late), e("info", early)]) == e(
            "info", early
        )


@pytest.mark.django_db
class TestOneCityOneZoneOneForecast:
    def test_the_strip_says_what_the_header_says(self, on, calls):
        client = login_as(VIEW)
        _city(client, "Punta Arenas", "-53.16", "-70.91")
        in_strip = _strip(client)
        header = _get(client, reverse("environment-gnss")).content.decode()
        text = "Typical higher-scintillation window: now, until 03:00"
        assert text in in_strip and text in header
        assert set(calls) == {(-53.16, -70.91)}  # nunca Santiago por omisión

    def test_the_strip_and_the_full_card_agree_on_the_current_conditions(
        self, forecast, on
    ):
        location = type("L", (), {"label": "Santiago"})()
        card = panel_module.build_card(location, forecast, [])
        now = panel_module.current_conditions(forecast)
        assert now["slug"] == card["slug"] and now["temp"] == card["temp"]
        assert now["feels"] == card["feels"] and now["is_night"] == card["is_night"]


@pytest.mark.django_db
class TestOneReferentialText:
    def test_the_strip_carries_it_once_and_no_other_warning(self, on):
        client = login_as(VIEW)
        _city(client)
        content = _strip(client)
        assert content.count("Information only. It is not a flight condition") == 1
        assert "gn-ref" not in content and "wx-legend" not in content


@pytest.mark.django_db
class TestFactsNotAVerdict:
    @pytest.mark.parametrize("language", ["en", "es"])
    @pytest.mark.parametrize("events", [[], EVENTS], ids=["quiet", "events"])
    def test_nothing_says_whether_a_flight_can_happen(
        self, on, monkeypatch, language, events
    ):
        monkeypatch.setattr(weather_client, "regional_events", lambda f: events)
        client = login_as(VIEW)
        _city(client)
        with translation.override(language):
            text = client.get(STRIP).content.decode().lower()
        for word in FORBIDDEN:
            assert word not in text, (language, word)

    def test_it_never_uses_the_critical_red(self, on, monkeypatch):
        monkeypatch.setattr(weather_client, "regional_events", lambda f: EVENTS)
        client = login_as(VIEW)
        _city(client)
        assert not re.search(r"critical|danger|\bred\b", _strip(client), re.I)

    def test_the_spanish_strip_is_translated(self, on):
        client = login_as(VIEW)
        _city(client)
        content = client.get(STRIP, headers={"Accept-Language": "es"}).content.decode()
        assert "Entorno hoy" in content and "Ver entorno" in content
        assert "Environment today" not in content


class TestTheErrorState:
    def test_the_error_partial_has_an_accessible_retry_to_the_same_fragment(self):
        html = render_to_string("environment/_strip.html", {"state": "error"})
        assert "The environment is not available right now" in html
        assert 'role="status"' in html and 'id="env-strip"' in html
        assert "data-wx-retry" in html and f'hx-get="{STRIP}"' in html
        assert 'hx-target="#env-strip"' in html
        assert "onclick" not in html and "hx-on" not in html


@pytest.mark.django_db
class TestThePanel:
    def test_the_hole_is_requested_on_load_with_its_skeleton_and_error_state(self, on):
        content = login_as(VIEW).get(DASHBOARD).content.decode()
        assert f'hx-get="{STRIP}"' in content and 'hx-trigger="load"' in content
        assert 'aria-busy="true"' in content and "data-wx-error" in content
        assert "hx-request=" in content
        assert content.count("js/weather-card.js") == 1

    def test_the_old_row_the_inline_gnss_card_and_the_sky_are_gone(self, on):
        content = login_as(VIEW).get(DASHBOARD).content.decode()
        for gone in ("env-row", "gnss-card", 'id="wx-card"', "sky-preview.js"):
            assert gone not in content, gone
        assert "Environment conditions" not in content

    @pytest.mark.parametrize(
        "perms,weather,gnss",
        [((), True, True), ((VIEW,), False, False), ((), False, False)],
        ids=["no-permission", "both-switches-off", "neither"],
    )
    def test_no_cell_means_no_hole_no_request_no_script(
        self, on, settings, perms, weather, gnss
    ):
        settings.WEATHER_ENABLED = weather
        settings.GNSS_SCINTILLATION_ENABLED = gnss
        content = login_as(*perms).get(DASHBOARD).content.decode()
        assert "env-strip" not in content and STRIP not in content
        assert "weather-card.js" not in content

    def test_a_single_cell_is_enough_for_the_hole(self, on, settings):
        settings.WEATHER_ENABLED = False
        content = login_as(VIEW).get(DASHBOARD).content.decode()
        assert STRIP in content

    def test_building_the_panel_never_reaches_the_forecast(self, on, monkeypatch):
        def boom(lat, lon, zone=None):
            raise AssertionError("armar el panel no puede pedir el pronóstico")

        monkeypatch.setattr(weather_client, "panel_forecast", boom)
        client = login_as(VIEW)
        _city(client)
        assert client.get(DASHBOARD).status_code == 200

    def test_the_panel_budget_is_untouched(self):
        assert budget.PANEL_QUERY_BUDGET == 49
        assert budget.PANEL_FILTERED_QUERY_BUDGET == 50

    def test_the_hole_costs_the_panel_no_query(self, on, settings):
        client = login_as(VIEW)
        _city(client)
        settings.WEATHER_ENABLED = settings.GNSS_SCINTILLATION_ENABLED = False
        client.get(DASHBOARD)  # calienta cachés de proceso
        with CaptureQueriesContext(connection) as without:
            client.get(DASHBOARD)
        settings.WEATHER_ENABLED = settings.GNSS_SCINTILLATION_ENABLED = True
        with CaptureQueriesContext(connection) as with_hole:
            client.get(DASHBOARD)
        assert len(with_hole) == len(without)


@pytest.mark.django_db
class TestTheStripsOwnQueryBudget:
    def test_the_fragment_stays_within_its_ceiling(self, on, django_assert_num_queries):
        client = login_as(VIEW)
        _city(client)
        client.get(STRIP)  # calienta cachés de proceso (ContentType, permisos)
        with django_assert_num_queries(STRIP_QUERY_BUDGET_WITHOUT_AIRSPACE):
            assert client.get(STRIP).status_code == 200


@pytest.mark.django_db
class TestTheTag:
    def _enabled(self, user):
        request = type("R", (), {"user": user})()
        return environment_tags.environment_strip_enabled({"request": request})

    def test_it_follows_permission_and_switches(self, on, settings):
        allowed = login_as(VIEW).user
        assert self._enabled(allowed) is True
        assert self._enabled(login_as().user) is False
        settings.WEATHER_ENABLED = settings.GNSS_SCINTILLATION_ENABLED = False
        assert self._enabled(allowed) is False

    def test_it_is_false_without_a_request(self):
        assert environment_tags.environment_strip_enabled({}) is False


class TestTheStylesheet:
    @staticmethod
    def _tokens(selector):
        match = re.search(rf"(?m)^{re.escape(selector)} \{{([^}}]*)\}}", IDENTITY)
        assert match, selector
        return dict(re.findall(r"(--id-env-[\w-]+)\s*:\s*([^;]+);", match.group(1)))

    def test_the_strip_uses_exactly_the_section_level_tokens(self):
        """Vive fuera de `.env-section`, así que repite los tokens: que no se separen."""
        section, strip = self._tokens(".env-section"), self._tokens(".env-strip")
        assert strip and strip == section

    def test_the_strip_has_no_motion(self):
        block = IDENTITY[
            IDENTITY.index("/* E7b:") : IDENTITY.index("/* == F: ilustración")
        ]
        assert not re.search(r"animation|@keyframes|transition|translate", block)
