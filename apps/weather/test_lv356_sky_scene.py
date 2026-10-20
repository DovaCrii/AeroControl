"""LV-356: escena animada del cielo en la tarjeta del tiempo (`weather/_sky.html`).

Se fija: el parcial dibuja cada fase y cada clima sin `defs` ni `id`, decorativo (`aria-hidden`) y
liviano; la fase lunar; que la CSS sólo define tokens `--id-sky-*`, anima dentro del único bloque
`no-preference` y bajo `[data-ambient]`, sin `translateX` y con pocos nodos; el contraste calculado
del texto sobre el velo en cada fase y tema; el guiño del centelleo GNSS, y que la vista previa de
24 h exista sin JS en línea y respete el movimiento reducido. Fechas fijas, sin red.
"""

import json
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core import weather as weather_client
from apps.core.testing import login_as
from apps.dashboard.test_lv312_hero import _contrast, _luminance
from apps.weather import panel as panel_module
from apps.weather import scene, sky
from apps.weather.models import UserWeatherLocation

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
PREVIEW_JS = (ROOT / "static/js/sky-preview.js").read_text(encoding="utf-8")
SANTIAGO = ZoneInfo("America/Santiago")
FIXTURE = ROOT / "apps/core/testdata/weather_panel_forecast.json"
DAY = "2026-10-19"
DAILY = [{"time": DAY, "sunrise": f"{DAY}T06:40", "sunset": f"{DAY}T19:50"}]
PHASES = {
    "night": (2, 0),
    "dawn": (7, 0),
    "morning": (9, 0),
    "midday": (13, 0),
    "afternoon": (16, 0),
    "sunset": (19, 0),
    "twilight": (20, 10),
}
SLUGS = ("clear", "partly", "cloudy", "fog", "rain", "snow", "storm", "wind")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("la escena del cielo no puede salir a la red")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def _state(hour, minute, slug="clear"):
    return sky.sky_state(
        datetime(2026, 10, 19, hour, minute),
        DAILY,
        hour in range(7, 20),
        slug,
        SANTIAGO,
    )


def _render(phase="midday", slug="clear", scintillation=False):
    hour, minute = PHASES[phase]
    state = _state(hour, minute, slug)
    assert state["phase"] == phase
    local = datetime(2026, 10, 19, hour, minute)
    context = {
        "sky": state,
        "scene": scene.scene_context(state, local, scintillation),
    }
    return render_to_string("weather/_sky.html", context)


class TestThePartial:
    @pytest.mark.parametrize("phase", PHASES)
    @pytest.mark.parametrize("slug", SLUGS)
    def test_every_phase_and_weather_renders_a_light_decorative_svg(self, phase, slug):
        html = _render(phase, slug)
        assert html.lstrip().startswith("<svg") and html.rstrip().endswith("</svg>")
        assert 'viewBox="0 0 640 160"' in html
        assert 'aria-hidden="true"' in html
        assert not re.search(r"\sid=", html) and "<defs" not in html
        assert "Gradient" not in html and "<style" not in html and "style=" not in html
        assert "<script" not in html and "onload" not in html
        assert len(html.encode("utf-8")) <= 20_000, (phase, slug)

    def test_the_sun_shows_by_day_and_the_moon_by_night(self):
        assert 'data-sun="on" data-moon="off"' in _render("midday")
        assert 'data-sun="off" data-moon="on"' in _render("night")
        assert 'data-sun="off" data-moon="on"' in _render("twilight")

    def test_the_sun_is_placed_with_the_context_position(self):
        state = _state(13, 0)
        html = _render("midday")
        assert f"translate({state['sun']['x']} {state['sun']['y']})" in html

    @pytest.mark.parametrize("slug", SLUGS)
    def test_the_clouds_follow_the_level(self, slug):
        state = _state(13, 0, slug)
        html = _render("midday", slug)
        assert (
            len(re.findall(r'class="sky-cloud sky-cloud--\d', html)) == state["clouds"]
        )

    def test_rain_snow_and_fog_appear_only_with_their_weather(self):
        assert 'class="sky-rain"' in _render("midday", "rain")
        assert 'class="sky-rain"' in _render("midday", "storm")
        assert 'class="sky-snow"' in _render("midday", "snow")
        assert 'class="sky-fog"' in _render("midday", "fog")
        for slug in ("clear", "partly", "cloudy", "wind"):
            html = _render("midday", slug)
            assert not re.search(r'class="sky-(rain|snow|fog)', html), slug
        assert 'class="sky-snow"' not in _render("midday", "rain")

    def test_a_storm_has_no_flash_layer(self):
        html = _render("midday", "storm")
        assert "flash" not in html and "lightning" not in html and "bolt" not in html
        assert "flash" not in IDENTITY.split("/* F3c: cielo")[1]

    def test_the_stars_are_a_fixed_small_count(self):
        html = _render("night")
        dots = re.search(r'sky-star--s" d="([^"]*)"', html).group(1).count("h0")
        big = re.search(r'sky-star--b" d="([^"]*)"', html).group(1).count("h0")
        assert 0 < dots + big <= 24
        assert _render("night") == _render("night")  # sin azar

    def test_twinkling_stars_only_with_a_scintillation_window(self):
        assert "sky-star--tw" not in _render("night")
        html = _render("night", scintillation=True)
        assert len(re.findall(r'class="sky-star sky-star--tw ', html)) == 4

    @pytest.mark.parametrize("slug", SLUGS)
    @pytest.mark.parametrize("scintillation", [False, True])
    def test_at_most_twelve_nodes_are_animated(self, slug, scintillation):
        html = _render("night", slug, scintillation)
        animated = len(
            re.findall(
                r'class="(?:sky-cloud sky-cloud--\d|sky-star sky-star--tw |'
                r'sky-rain|sky-snow|sky-fog")',
                html,
            )
        )
        assert animated <= 8, (slug, animated)


class TestTheMoon:
    def test_a_new_moon_has_no_lit_part(self):
        assert scene.moon_path(0.0, True) == ""

    def test_a_crescent_is_lit_on_the_left_in_the_southern_hemisphere(self):
        # creciente: iluminada por la izquierda (arco de limbo con sweep 0) y sin espejo
        assert scene.moon_path(0.2, True).startswith("M0 -9A9 9 0 0 0 0 9")
        ctx = scene.scene_context(
            {
                **_state(2, 0),
                "moon": {**_state(2, 0)["moon"], "fraction": 0.8},
                "clouds": 0,
                "precip": None,
            },
            datetime(2026, 10, 19, 2, 0),
        )
        assert ctx["moon_flip"] is True

    def test_gibbous_and_full_use_different_terminators(self):
        crescent = scene.moon_path(0.25, True)
        gibbous = scene.moon_path(0.75, True)
        assert crescent != gibbous
        assert crescent.endswith("1 0 -9Z") and gibbous.endswith("0 0 -9Z")
        assert (
            scene.moon_path(1.0, True).count("A9 9") == 2
        )  # dos medias circunferencias


def _f3c():
    start = IDENTITY.index("/* F3c: cielo (LV-356)")
    return IDENTITY[start : IDENTITY.index("/* ── Movimiento", start)]


def _motion_block():
    marker = "@media (prefers-reduced-motion: no-preference) {"
    start = IDENTITY.index(marker)
    depth = 0
    for index in range(start + len(marker) - 1, len(IDENTITY)):
        depth += {"{": 1, "}": -1}.get(IDENTITY[index], 0)
        if depth == 0:
            return IDENTITY[start:index]
    raise AssertionError("bloque sin cerrar")


class TestTheStyles:
    def test_the_static_section_defines_only_sky_tokens_and_has_no_animation(self):
        static = _f3c()
        assert "animation" not in static and "@keyframes" not in static
        names = set(re.findall(r"(?<![\w-])(--[\w-]+)\s*:", static))
        assert names and all(n.startswith("--id-sky-") for n in names), names
        assert not re.search(r"--(?:ac|sev)-[\w-]+\s*:", static)

    def test_every_token_is_declared_for_light_and_dark(self):
        static = _f3c()
        for token in ("top", "bot", "sun", "cloud", "ridge"):
            for phase in PHASES:
                for dark in (False, True):
                    prefix = re.escape('[data-theme="dark"] ') if dark else ""
                    rule = (
                        prefix
                        + rf'\.wx-head\[data-sky="{phase}"\] \{{[^}}]*--id-sky-{token}:'
                    )
                    assert re.search(rule, static), (token, phase, dark)
        assert "--id-sky-scrim" in static and "--id-sky-ink" in static
        assert '[data-theme="dark"] .wx-head--sky { --id-sky-scrim' in static

    def test_there_is_a_single_no_preference_block_and_every_sky_animation_is_in_it(
        self,
    ):
        assert IDENTITY.count("prefers-reduced-motion: no-preference") <= 2
        block = _motion_block()
        outside = IDENTITY.replace(block, "")
        assert not re.search(r"\.sky-[\w-]+[^{]*\{[^}]*(animation|transition)", outside)
        assert "@keyframes sky-" in block and "/* F3c: cielo." in block

    def test_nothing_uses_translatex(self):
        assert "translateX" not in IDENTITY

    def test_infinite_only_under_data_ambient_and_slow(self):
        seen = 0
        for line in IDENTITY.splitlines():
            if "sky-" in line and "infinite" in line:
                seen += 1
                assert "[data-ambient]" in line, line
                assert float(re.search(r"\s([\d.]+)s\s", line).group(1)) >= 6, line
        assert seen >= 6

    def test_only_transform_and_opacity_are_animated(self):
        found = re.findall(r"@keyframes sky-[\w-]+ \{(.*)\}", _motion_block())
        assert len(found) == 4
        for keyframes in found:
            props = set(re.findall(r"([\w-]+):", keyframes))
            assert props <= {"transform", "opacity"}, props

    def test_the_animated_selectors_stay_within_twelve_nodes(self):
        selectors = re.findall(r"\[data-ambient\] (\.sky-[\w-]+) \{", _motion_block())
        # tres nubes, cuatro estrellas, lluvia, nieve y niebla (lluvia, nieve y niebla no coinciden)
        assert len(set(selectors)) <= 12

    def test_the_reduced_motion_scene_is_complete_without_the_motion_block(self):
        static = IDENTITY.replace(_motion_block(), "")
        for needle in (
            ".sky-sun",
            ".sky-moon",
            ".sky-cloud",
            ".sky-ridge",
            ".sky-city",
        ):
            assert needle in static
        assert not re.search(r"\.sky-[\w-]+[^{]*\{[^}]*animation", static)


def _hex_tokens(theme, phase):
    static = _f3c()
    prefix = r'\[data-theme="dark"\] ' if theme == 1 else ""
    body = re.search(
        rf'(?m)^{prefix}\.wx-head\[data-sky="{phase}"\] \{{([^}}]*)\}}', static
    ).group(1)
    return dict(re.findall(r"--id-sky-(\w+):\s*(#[0-9a-fA-F]{6})", body))


def _app_token(name, theme):
    found = re.findall(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", APP_CSS)
    assert len(found) == 2, name
    return found[theme]


def _over(scrim, background):
    """El color que se ve al poner `scrim` (#rrggbbaa) sobre `background` (#rrggbb)."""
    alpha = int(scrim[7:9], 16) / 255
    return "#%02x%02x%02x" % tuple(
        round(
            int(scrim[i : i + 2], 16) * alpha
            + int(background[i : i + 2], 16) * (1 - alpha)
        )
        for i in (1, 3, 5)
    )


def _mix(a, b, share):
    return "#%02x%02x%02x" % tuple(
        round(int(a[i : i + 2], 16) * share + int(b[i : i + 2], 16) * (1 - share))
        for i in (1, 3, 5)
    )


class TestTheTextStaysReadable:
    @pytest.mark.parametrize("theme", [0, 1], ids=["light", "dark"])
    @pytest.mark.parametrize("phase", PHASES)
    def test_header_text_on_the_scrim_over_every_sky_colour(self, theme, phase):
        static = _f3c()
        base = _hex_tokens(theme, phase)
        scrim = re.search(
            r'(?m)^\[data-theme="dark"\] \.wx-head--sky \{ --id-sky-scrim: (#[0-9a-f]{8})'
            if theme
            else r"--id-sky-scrim: (#[0-9a-f]{8})",
            static,
        ).group(1)
        moon = re.search(r"--id-sky-moon: (#[0-9a-f]{6})", static).group(1)
        ink = _app_token("ac-text", theme)
        backgrounds = {
            **base,
            "moon": moon,
            "heavy": _mix(base["cloud"], base["ridge"], 0.62),
        }
        for name, colour in backgrounds.items():
            ratio = _contrast(_luminance(ink), _luminance(_over(scrim, colour)))
            assert ratio >= 4.5, (phase, theme, name, round(ratio, 2))

    def test_the_veil_is_the_opposite_of_the_text_in_each_theme(self):
        light_ink, dark_ink = _app_token("ac-text", 0), _app_token("ac-text", 1)
        assert _luminance(light_ink) < 0.2 < 0.6 < _luminance(dark_ink)
        static = _f3c()
        assert "--id-sky-scrim: #ffffffb3" in static  # velo claro bajo el texto oscuro
        assert "--id-sky-scrim: #0b1430b3" in static  # velo oscuro bajo el texto claro
        assert "--id-sky-ink: var(--ac-text)" in static


VIEW = "view_userweatherlocation"


@pytest.fixture
def enabled(settings, monkeypatch):
    settings.WEATHER_ENABLED = True
    settings.WEATHER_DEFAULT_LABEL = ""
    forecast = weather_client._parse_panel(json.loads(FIXTURE.read_text("utf-8")))
    monkeypatch.setattr(weather_client, "panel_forecast", lambda lat, lon: forecast)
    monkeypatch.setattr(
        panel_module, "_local_now", lambda f: datetime(2026, 10, 19, 22, 0)
    )
    return forecast


def _city(client):
    return UserWeatherLocation.objects.create(
        user=client.user,
        label="Santiago",
        latitude="-33.4489",
        longitude="-70.6693",
        timezone="America/Santiago",
        source="search",
    )


@pytest.mark.django_db
class TestTheCard:
    def test_403_without_permission_and_404_when_switched_off(self, enabled, settings):
        assert login_as().get(reverse("weather-panel")).status_code == 403
        settings.WEATHER_ENABLED = False
        client = login_as(VIEW)
        _city(client)
        assert client.get(reverse("weather-panel")).status_code == 404

    def test_the_card_draws_the_scene_in_the_header(self, enabled):
        client = login_as(VIEW)
        _city(client)
        content = client.get(reverse("weather-panel")).content.decode()
        header = content.split('<header class="wx-head')[1].split("</header>")[0]
        assert "sky-scene" in header and 'data-sky="night"' in header
        assert (
            'tabindex="0"' in header
            and 'data-sr="' in header
            and "data-hour=" in header
        )
        assert "data-ambient" in content.split("<header")[0]
        assert "<script" not in content and "onmouseover" not in content

    def test_the_sky_in_the_card_is_the_one_in_the_context(self, enabled):
        location = SimpleNamespace(label="Santiago")
        context = panel_module.build_card(location, enabled, [])
        assert context["scene"]["sunrise_h"] == round(
            context["sky"]["sunrise"].hour + context["sky"]["sunrise"].minute / 60, 2
        )
        assert context["scene"]["hour_now"] == 22.0

    def test_the_band_retires_the_wink(self, enabled):
        # LV-358 (E3): a las 22:00 de octubre la ventana está activa, pero la banda GNSS de la franja
        # de 24 h ya dice lo mismo: las estrellas no titilan (sería el mismo dato dos veces).
        client = login_as(VIEW)
        _city(client)
        content = client.get(reverse("weather-panel")).content.decode()
        assert "wx-gnss-band" in content
        assert "sky-star--tw" not in content

    def test_without_a_band_the_window_still_makes_four_stars_twinkle(self, enabled):
        # Sin horas en el pronóstico no hay franja ni banda: queda el guiño de siempre.
        location = SimpleNamespace(label="Santiago")
        bare = {**enabled, "hourly": []}
        context = panel_module.build_card(location, bare, [])
        assert context["gnss_band"] is None
        html = render_to_string("weather/_panel_card.html", context)
        assert "wx-gnss-band" not in html and html.count("sky-star--tw ") == 4

    def test_no_window_no_twinkling(self, enabled, monkeypatch):
        monkeypatch.setattr(
            panel_module, "_local_now", lambda f: datetime(2026, 10, 19, 13, 0)
        )
        client = login_as(VIEW)
        _city(client)
        assert (
            "sky-star--tw" not in client.get(reverse("weather-panel")).content.decode()
        )

    def test_the_wink_never_breaks_the_card(self, enabled, monkeypatch, settings):
        def boom(*args, **kwargs):
            raise RuntimeError("sin ventana")

        monkeypatch.setattr(panel_module.gnss_module, "window_state", boom)
        assert (
            panel_module._scintillation_active(enabled, datetime(2026, 10, 19, 22))
            is False
        )
        monkeypatch.undo()
        settings.GNSS_SCINTILLATION_ENABLED = False
        assert (
            panel_module._scintillation_active(enabled, datetime(2026, 10, 19, 22))
            is False
        )

    def test_the_weather_tab_loads_the_preview_script_when_enabled(
        self, enabled, settings
    ):
        # LV-358 (E2): la escena animada vive en la pestaña Tiempo, no en el panel.
        client = login_as(VIEW)
        content = client.get(reverse("environment-weather")).content.decode()
        assert "js/sky-preview.js" in content and "js/ambient-motion.js" in content
        settings.WEATHER_ENABLED = False
        assert client.get(reverse("environment-weather")).status_code == 404

    def test_the_dashboard_does_not_load_the_preview_script(self, enabled):
        content = login_as(VIEW).get(reverse("dashboard")).content.decode()
        assert "sky-preview.js" not in content


class TestThePreviewScript:
    def test_it_respects_reduced_motion_and_stays_inert_without_it(self):
        assert "prefers-reduced-motion: reduce" in PREVIEW_JS
        assert "allowed()" in PREVIEW_JS and "start(head)" in PREVIEW_JS
        assert "if (!allowed()" in PREVIEW_JS

    def test_it_listens_on_the_document_for_hover_focus_and_htmx(self):
        for event in (
            "mouseover",
            "mouseout",
            "focusin",
            "focusout",
            "htmx:beforeSwap",
        ):
            assert f'"{event}"' in PREVIEW_JS, event

    def test_it_writes_no_markup(self):
        assert "innerHTML" not in PREVIEW_JS and "eval(" not in PREVIEW_JS
        assert "fetch(" not in PREVIEW_JS and "XMLHttpRequest" not in PREVIEW_JS

    @pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
    @pytest.mark.parametrize("hour", [x / 2 for x in range(0, 48)])
    def test_its_phases_match_the_server_ones(self, hour):
        source = re.search(r"function phaseFor\(.*?\n  \}\n", PREVIEW_JS, re.S).group(0)
        script = f"{source}\nconsole.log(phaseFor({hour}, 6 + 40/60, 19 + 50/60));"
        out = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=True
        ).stdout.strip()
        state = sky.sky_state(
            datetime(2026, 10, 19, int(hour), int(round((hour % 1) * 60))),
            DAILY,
            True,
            "clear",
            SANTIAGO,
        )
        assert out == state["phase"], hour
