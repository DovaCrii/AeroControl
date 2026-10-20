"""LV-347: tarjeta del tiempo del panel (fragmento htmx), SOLO informativa.

Se fija: 403 sin permiso, 404 apagada, estado vacío y de error, el render con el fixture
(temperatura, 24 h, 7 días, eventos con símbolo + texto + nivel, leyenda y atribución), el
escape de la ciudad, que nada hable de vuelos ni permisos, que el movimiento viva sólo bajo
`no-preference` y `data-ambient`, el contraste calculado de la cabecera y que el panel no
gane consultas. Sin red: el cliente se sustituye por el fixture y `urlopen` falla si se llama.
"""

import html
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from apps.core import weather as weather_client
from apps.core.testing import login_as
from apps.dashboard.test_lv312_hero import _contrast, _lum_rgb, _luminance
from apps.weather import panel as panel_module
from apps.weather.models import UserWeatherLocation

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "templates/dashboard/index.html").read_text(encoding="utf-8")
FIXTURE = ROOT / "apps/core/testdata/weather_panel_forecast.json"

URL = "weather-panel"
VIEW = "view_userweatherlocation"
SLUGS = ("clear", "partly", "cloudy", "fog", "rain", "snow", "storm", "wind")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("la tarjeta del tiempo no puede salir a la red en pruebas")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture
def enabled(settings, monkeypatch):
    settings.WEATHER_ENABLED = True
    settings.WEATHER_DEFAULT_LABEL = ""
    forecast = weather_client._parse_panel(json.loads(FIXTURE.read_text("utf-8")))
    monkeypatch.setattr(
        weather_client, "panel_forecast", lambda lat, lon: forecast, raising=True
    )
    # El fixture es de 2026-10-19: se fija «ahora» para que la prueba no dependa del día.
    monkeypatch.setattr(
        panel_module, "_local_now", lambda f: datetime(2026, 10, 19, 9, 30)
    )
    return forecast


def _city(client, label="Santiago"):
    return UserWeatherLocation.objects.create(
        user=client.user,
        label=label,
        latitude="-33.4489",
        longitude="-70.6693",
        timezone="America/Santiago",
        source="search",
    )


def _get(client):
    return client.get(reverse(URL))


@pytest.mark.django_db
class TestAccess:
    def test_403_without_permission(self, enabled):
        assert _get(login_as()).status_code == 403

    def test_anonymous_goes_to_login(self, client, enabled):
        assert client.get(reverse(URL)).status_code == 302

    def test_404_when_switched_off(self, settings):
        settings.WEATHER_ENABLED = False
        client = login_as(VIEW)
        _city(client)
        assert _get(client).status_code == 404

    def test_a_view_only_user_gets_the_card(self, enabled):
        client = login_as(VIEW)
        _city(client)
        assert _get(client).status_code == 200


@pytest.mark.django_db
class TestStates:
    def test_no_city_says_pick_your_city_and_links_to_the_chooser(self, enabled):
        response = _get(login_as(VIEW))
        content = response.content.decode()
        assert gettext("Pick your city") in content
        assert reverse("weather-location") in content
        assert "wx-hours" not in content

    def test_a_failed_client_shows_the_error_state(self, enabled, monkeypatch):
        monkeypatch.setattr(weather_client, "panel_forecast", lambda lat, lon: None)
        client = login_as(VIEW)
        _city(client)
        response = _get(client)
        assert response.status_code == 200
        content = response.content.decode()
        assert (
            gettext(
                "The weather is not available right now. It will be tried again shortly."
            )
            in content
        )
        assert "wx-hours" not in content


@pytest.mark.django_db
class TestTheCard:
    def _page(self, label="Santiago"):
        client = login_as(VIEW)
        _city(client, label)
        return _get(client).content.decode()

    def test_it_draws_now_24_hours_and_7_days(self, enabled):
        content = self._page()
        assert "Santiago" in content
        assert re.search(r'<p class="wx-temp">.*?14°', content, re.S)
        assert content.count('class="wx-hour"') == 24
        assert content.count('class="wx-day"') == 7
        assert "<polyline" in content
        assert 'class="wx-arrow"' in content

    def test_the_strip_starts_at_the_current_hour(self, enabled):
        content = self._page()
        first = re.search(r'<span class="wx-hour-h">(\d\d)</span>', content).group(1)
        assert first == "09"

    def test_events_carry_symbol_text_and_level(self, enabled):
        events = weather_client.regional_events(enabled)
        assert events, "el fixture debería traer al menos un evento"
        content = self._page()
        assert content.count('class="wx-event wx-event--') == len(events)
        for row in panel_module._event_rows(events):
            assert str(row["label"]) in content
            assert str(row["level_label"]) in content
            assert row["symbol"] in content

    def test_no_events_says_so(self, enabled, monkeypatch):
        monkeypatch.setattr(weather_client, "regional_events", lambda forecast: [])
        content = self._page()
        assert (
            gettext("No notable weather events expected in the next 48 hours")
            in content
        )
        assert "wx-event wx-event--" not in content

    def test_legend_attribution_and_checked_time(self, enabled):
        content = self._page()
        legend = gettext(
            "Informational only. It is not a flight condition and does not replace"
            " anyone's judgement or the DGAC"
        )
        assert legend in html.unescape(content)
        assert 'href="https://open-meteo.com/"' in content
        assert "Open-Meteo.com" in content and "CC BY 4.0" in content
        assert re.search(r"\d\d:\d\d", content.split('class="wx-credit"')[1])
        assert reverse("weather-location") in content

    def test_the_city_label_is_escaped(self, enabled):
        content = self._page("<script>alert(1)</script>")
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
        assert "<script>alert(1)" not in content

    @pytest.mark.parametrize("language", ["en", "es"])
    def test_nothing_talks_about_flying_permits_or_sites(self, enabled, language):
        with translation.override(language):
            content = self._page()
        card = re.sub(r'<p class="wx-legend">.*?</p>', "", content, flags=re.S)
        assert not re.search(
            r"\b(fly|flying|flight|permit|permits|permiso|permisos|vuelo|vuelos|faena|faenas)\b",
            card,
            re.I,
        )
        assert not re.search(r"(?i)can fly|puede volar|go / no-go", card)

    def test_the_card_is_marked_ambient_and_animates_at_most_eight_nodes(
        self, enabled, monkeypatch
    ):
        client = login_as(VIEW)
        _city(client)
        for slug in SLUGS:
            monkeypatch.setattr(
                panel_module, "condition_slug", lambda *a, s=slug, **k: s
            )
            content = _get(client).content.decode()
            assert re.search(r"<section[^>]*\bdata-ambient\b", content), slug
            animated = len(
                re.findall(
                    r'class="[^"]*\bwx-(?:spin|cloud|drop|drift)(?![\w-])', content
                )
            )
            assert animated <= 8, (slug, animated)


def _tokens(name):
    """(claro, oscuro) de un token de `app.css`: cada uno se declara una vez por tema, en ese orden."""
    found = re.findall(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", APP_CSS)
    assert len(found) == 2, name
    return found


def _mixed(token, share, theme):
    surface = _tokens("ac-surface")[theme]
    colour = _tokens(token)[theme]
    return tuple(
        round(
            int(colour[i : i + 2], 16) * share
            + int(surface[i : i + 2], 16) * (1 - share)
        )
        for i in (1, 3, 5)
    )


MIX = re.compile(r"color-mix\(in srgb, var\(--([\w-]+)\) (\d+)%, var\(--ac-surface\)\)")


def _gradients():
    """Todos los pares (a, b) de la cabecera tal como los declara identity.css, por nombre."""
    pairs = {}
    for name, body in re.findall(r"\.wx-head(--\w+)? \{([^}]*)\}", IDENTITY):
        found = MIX.findall(body)
        if len(found) == 2:
            pairs[name or "default"] = found
    night = re.search(r"\.wx-head\.is-night \{([^}]*)\}", IDENTITY).group(1)
    return pairs, MIX.findall(night)[0]


class TestTheHeaderStaysReadable:
    def test_every_slug_has_a_gradient(self):
        pairs, _ = _gradients()
        assert set(pairs) == {"default", *(f"--{s}" for s in SLUGS)}

    @pytest.mark.parametrize("theme", [0, 1], ids=["light", "dark"])
    def test_text_contrast_on_both_ends_of_every_gradient_day_and_night(self, theme):
        pairs, night_a = _gradients()
        text = _luminance(_tokens("ac-text")[theme])
        worst = 99.0
        for name, (a, b) in pairs.items():
            for stop_a in (a, night_a):
                for stop in (stop_a, b):
                    bg = _lum_rgb(_mixed(stop[0], int(stop[1]) / 100, theme))
                    ratio = _contrast(text, bg)
                    worst = min(worst, ratio)
                    assert ratio >= 4.5, (name, stop, theme, ratio)
        assert worst >= 4.5

    @pytest.mark.parametrize("theme", [0, 1], ids=["light", "dark"])
    @pytest.mark.parametrize(
        "level,family",
        [("info", "advisory"), ("attention", "warning"), ("strong", "critical")],
    )
    def test_event_text_contrast(self, theme, level, family):
        ratio = _contrast(
            _luminance(_tokens(f"sev-{family}-text")[theme]),
            _luminance(_tokens(f"sev-{family}-bg")[theme]),
        )
        assert ratio >= 4.5, (level, theme, ratio)


def _motion_block():
    marker = "@media (prefers-reduced-motion: no-preference) {"
    start = IDENTITY.index(marker)
    depth = 0
    for index in range(start + len(marker) - 1, len(IDENTITY)):
        depth += {"{": 1, "}": -1}.get(IDENTITY[index], 0)
        if depth == 0:
            return IDENTITY[start:index]
    raise AssertionError("bloque sin cerrar")


class TestMotion:
    def test_the_static_section_has_no_animation_and_redefines_no_token(self):
        static = IDENTITY[
            IDENTITY.index("/* F3: tiempo") : IDENTITY.index("/* ── Movimiento")
        ]
        assert "animation" not in static and "@keyframes" not in static
        assert not re.search(
            r"--(?:ac|sev)-[\w-]+\s*:|--id-(?!wx-|gn-|sky-)[\w-]+\s*:", static
        )

    def test_every_wx_animation_is_inside_the_single_no_preference_block(self):
        assert IDENTITY.count("prefers-reduced-motion: no-preference") <= 2
        block = _motion_block()
        outside = IDENTITY.replace(block, "")
        assert not re.search(r"\.wx-[\w-]+[^{]*\{[^}]*animation", outside)
        assert "/* F3: tiempo." in block and IDENTITY.count("/* F3: tiempo.") == 1

    def test_infinite_only_under_data_ambient_and_slow(self):
        for line in IDENTITY.splitlines():
            if "wx-" in line and "infinite" in line:
                assert "[data-ambient]" in line, line
                assert float(re.search(r"\s([\d.]+)s\s", line).group(1)) >= 6, line

    def test_only_transform_and_opacity_are_animated(self):
        for keyframes in re.findall(r"@keyframes wx-[\w-]+ \{(.*)\}", _motion_block()):
            props = set(re.findall(r"([\w-]+):", keyframes))
            assert props <= {"transform", "opacity"}, props

    def test_the_dashboard_template_stays_free_of_the_ambient_marker(self):
        assert "data-ambient" not in DASHBOARD


@pytest.mark.django_db
class TestTheCardLivesInTheWeatherTab:
    """LV-358 (E2): la tarjeta completa ya no está en el panel; su hueco htmx vive en la pestaña Tiempo.

    Es la cobertura que antes tenía el hueco del panel (pedida al cargar, nada sin permiso ni apagada),
    movida al lugar donde la tarjeta se dibuja ahora. El panel conserva sólo la franja (`test_lv358_strip`).
    """

    def test_it_is_requested_on_load_when_enabled(self, enabled):
        client = login_as(VIEW)
        content = client.get(reverse("environment-weather")).content.decode()
        assert f'hx-get="{reverse(URL)}?embed=environment"' in content
        assert 'hx-trigger="load"' in content

    def test_the_panel_no_longer_carries_the_card_or_its_request(self, enabled):
        content = login_as(VIEW).get(reverse("dashboard")).content.decode()
        assert reverse(URL) not in content and 'id="wx-card"' not in content
        assert "sky-preview.js" not in content

    def test_nothing_is_requested_when_switched_off(self, settings):
        settings.WEATHER_ENABLED = False
        client = login_as(VIEW)
        assert client.get(reverse("environment-weather")).status_code == 404
        content = client.get(reverse("dashboard")).content.decode()
        assert reverse(URL) not in content and "wx-card" not in content

    def test_nothing_is_requested_without_the_permission(self, enabled):
        client = login_as()
        assert client.get(reverse("environment-weather")).status_code == 403
        assert reverse(URL) not in client.get(reverse("dashboard")).content.decode()

    def test_the_panel_query_count_does_not_change(self, settings):
        client = login_as(VIEW)
        _city(client)
        settings.WEATHER_ENABLED = False
        client.get(reverse("dashboard"))  # calienta cachés de proceso
        with CaptureQueriesContext(connection) as off:
            client.get(reverse("dashboard"))
        settings.WEATHER_ENABLED = True
        with CaptureQueriesContext(connection) as on:
            client.get(reverse("dashboard"))
        assert len(on) == len(off)
