"""LV-367 (fase 2): la franja «Entorno hoy» en tarjetas y la cabecera sin «Situación del día».

Se fija, con el contraste CALCULADO (no leído de un navegador): los tres niveles (● cian, ▲ ámbar, ◆ naranja
propio, nunca el rojo de «crítico») llegan a 4,5:1 en claro y oscuro; el filete de 4 px de cada tarjeta y el
borde de 2 px de ◆ llegan a 3:1 contra la tarjeta; `.env-section` y `.env-strip` llevan EXACTAMENTE los mismos
tokens (claro y oscuro); la geometría de la línea de 24 h (`day_geometry`) coincide con `windows_between`,
incluso con el cambio de hora; y el SVG de la banda es `role="img"` con título, descripción, sin `style=""` y
con la ventana también impresa en texto.
"""

# ruff: noqa: F811  (los fixtures se importan de test_lv358_strip y se usan como argumentos)
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from apps.core import weather as weather_client
from apps.core.test_lv367_visual_base import _contrast, _resolve, _theme_tokens
from apps.core.testing import login_as
from apps.environment import gnss_day
from apps.environment.templatetags import gnss_charts
from apps.environment.test_lv358_strip import (  # noqa: F401  (fixtures compartidos)
    EVENTS,
    IDENTITY,
    STRIP,
    VIEW,
    calls,
    english,
    forecast,
    no_network,
    on,
    _city,
    _get,
    _strip,
)
from apps.weather import gnss

SANTIAGO = ZoneInfo("America/Santiago")
LEVELS = ("info", "attention", "strong")
THEMES = ("light", "dark")
DARK_BLOCK = '[data-theme="dark"] .env-section,\n[data-theme="dark"] .env-strip {'


def _block(selector):
    match = re.search(rf"(?m)^{re.escape(selector)} \{{([^}}]*)\}}", IDENTITY)
    assert match, selector
    return dict(re.findall(r"(--id-env-[\w-]+)\s*:\s*([^;]+);", match.group(1)))


def _dark_override():
    text = IDENTITY.replace("\r\n", "\n")
    assert DARK_BLOCK in text
    body = text.split(DARK_BLOCK)[1].split("}")[0]
    return dict(re.findall(r"(--id-env-[\w-]+)\s*:\s*([^;]+);", body))


def _levels(theme, selector=".env-section"):
    """Los tokens de nivel efectivos en `theme`: los del bloque y, en oscuro, el override."""
    tokens = _theme_tokens(theme)
    decl = dict(_block(selector))
    if theme == "dark":
        decl.update(_dark_override())
    return {k: _resolve(v, tokens) for k, v in decl.items()}


class TestTheLevelColours:
    @pytest.mark.parametrize("selector", [".env-section", ".env-strip"])
    @pytest.mark.parametrize("theme", THEMES)
    @pytest.mark.parametrize("level", LEVELS)
    def test_text_reaches_4_5_on_the_chip(self, selector, theme, level):
        v = _levels(theme, selector)
        assert _contrast(v[f"--id-env-{level}-fg"], v[f"--id-env-{level}-bg"]) >= 4.5

    @pytest.mark.parametrize("theme", THEMES)
    @pytest.mark.parametrize("level", LEVELS)
    def test_the_stripe_reaches_3_to_1_against_the_tile_and_the_card(
        self, theme, level
    ):
        tokens = _theme_tokens(theme)
        stripe = _levels(theme)[f"--id-env-{level}-fg"]
        for surface in ("--id-tile", "--ac-surface"):
            assert _contrast(stripe, _resolve(tokens[surface], tokens)) >= 3, surface

    @pytest.mark.parametrize("theme", THEMES)
    def test_the_strong_border_reaches_3_to_1_against_the_tile(self, theme):
        tokens = _theme_tokens(theme)
        border = _levels(theme)["--id-env-strong-bd"]
        assert _contrast(border, _resolve(tokens["--id-tile"], tokens)) >= 3

    def test_info_is_cyan_not_the_nominal_grey(self):
        block = _block(".env-section")
        assert block["--id-env-info-fg"] == "var(--sev-advisory-text)"
        assert "nominal" not in " ".join(block.values())

    def test_attention_and_strong_are_not_the_same_colours(self):
        for theme in THEMES:
            v = _levels(theme)
            assert v["--id-env-attention-fg"] != v["--id-env-strong-fg"]
            assert v["--id-env-attention-bg"] != v["--id-env-strong-bg"]

    def test_strip_and_section_carry_exactly_the_same_tokens_in_both_themes(self):
        assert _block(".env-section") == _block(".env-strip")
        for theme in THEMES:
            assert _levels(theme, ".env-section") == _levels(theme, ".env-strip")

    def test_the_dark_override_names_both_containers_and_only_the_strong_level(self):
        assert set(_dark_override()) == {
            "--id-env-strong-bg",
            "--id-env-strong-fg",
            "--id-env-strong-bd",
        }

    def test_the_block_has_no_red_no_transition_and_no_foreign_tokens(self):
        block = IDENTITY[
            IDENTITY.index("/* E7: sección") : IDENTITY.index("/* == F: ilustración")
        ]
        assert not re.search(r"critical|danger|red\b", block, re.I)
        assert not re.search(r"animation|@keyframes|translate|transition", block)
        defined = set(re.findall(r"(?m)^\s*(--[\w-]+)\s*:", block))
        assert defined and all(name.startswith("--id-env-") for name in defined)

    def test_the_tile_uses_the_edge_token_and_the_tile_surface(self):
        cell = re.search(r"(?m)^\.env-cell \{([^}]*)\}", IDENTITY).group(1)
        assert "border: 1px solid var(--id-edge)" in cell
        assert "background: var(--id-tile)" in cell
        assert "border-left: 4px solid" in cell


@pytest.mark.django_db
class TestTheTiles:
    def _cell(self, html, name):
        return html.split(f"env-cell--{name}")[1].split("env-cell env-cell--")[0]

    def test_three_tiles_each_with_its_own_level_stripe(self, on, monkeypatch):
        monkeypatch.setattr(weather_client, "regional_events", lambda f: EVENTS)
        client = login_as(VIEW, "view_airspacefeature", "view_flightpermission")
        _city(client)
        html = _strip(client)
        for name in ("weather", "gnss", "airspace"):
            assert f"env-cell env-cell--{name} env-cell--" in html, name
        # El evento principal es «fuerte»: la tarjeta del tiempo lleva el filete fuerte y su chip.
        assert "env-cell--weather env-cell--strong" in html
        assert "env-lvl--strong" in self._cell(html, "weather")
        # El centelleo está activo a las 21:30: ▲ con chip.
        assert "env-cell--gnss env-cell--attention" in html
        assert "env-lvl--attention" in self._cell(html, "gnss")

    def test_a_quiet_tile_has_no_info_chip_and_says_so_with_an_icon(
        self, on, monkeypatch
    ):
        monkeypatch.setattr(weather_client, "regional_events", lambda f: [])
        client = login_as(VIEW)
        _city(client)
        html = _strip(client)
        weather = self._cell(html, "weather")
        assert "env-cell--weather env-cell--info" in html
        assert "env-lvl" not in weather
        assert "icon-check" in weather and "env-cell-calm" in weather

    def test_the_tiles_have_no_inline_style_and_the_icons_are_hidden_from_readers(
        self, on
    ):
        client = login_as(VIEW)
        _city(client)
        html = _strip(client)
        # La nube parcial de `weather/_icons.html` trae un `style` heredado (LV-347): no es de esta fase.
        assert "style=" not in html.split("env-cell--gnss")[1]
        for use in re.findall(r'<svg class="nav-icon"[^>]*>', html):
            assert 'aria-hidden="true"' in use

    def test_the_weather_icon_keeps_its_hidden_wrapper_and_the_temperature(self, on):
        client = login_as(VIEW)
        _city(client)
        html = _strip(client)
        assert 'class="env-cell-ico" aria-hidden="true"' in html and "14°" in html

    def test_the_header_link_is_the_only_link_to_the_hub(self, on):
        client = login_as(VIEW, "view_airspacefeature", "view_flightpermission")
        _city(client)
        html = _strip(client)
        assert html.count(f'href="{reverse("environment-hub")}"') == 1

    def test_the_airspace_big_number_is_decorative_and_the_sentence_carries_it(
        self, on
    ):
        client = login_as(VIEW, "view_airspacefeature", "view_flightpermission")
        _city(client)
        html = _strip(client)
        cell = self._cell(html, "airspace")
        # Sin foto importada no hay cifra grande: sólo la frase.
        assert "env-cell-big" not in cell
        assert "No airspace snapshot has been imported yet" in cell

    def test_the_spanish_strip_is_translated(self, on):
        client = login_as(VIEW)
        _city(client)
        html = client.get(STRIP, headers={"Accept-Language": "es"}).content.decode()
        assert "Ventana típica:" in html
        assert "Typical window" not in html


@pytest.mark.django_db
class TestTheHeader:
    def test_the_repeated_situation_of_the_day_is_gone(self, on):
        client = login_as(VIEW)
        _city(client)
        for url in (reverse("environment-weather"), reverse("environment-gnss")):
            html = _get(client, url).content.decode()
            assert "Situation of the day" not in html and "env-lines" not in html
            assert 'class="env-line' not in html

    def test_it_keeps_city_time_and_sun_each_with_an_icon_and_its_text(self, on):
        client = login_as(VIEW)
        _city(client)
        html = _get(client, reverse("environment-weather")).content.decode()
        header = html.split('class="env-header"')[1].split("</section>")[0]
        for icon in ("icon-clock", "icon-sunrise", "icon-sunset"):
            assert icon in header, icon
        for word in ("Chile time", "Sunrise", "Sunset"):
            assert word in header, word

    def test_the_referential_text_is_still_once_and_carries_an_icon(self, on):
        client = login_as(VIEW)
        _city(client)
        html = _get(client, reverse("environment-gnss")).content.decode()
        assert html.count("Information only. It is not a flight condition") == 1
        assert "icon-info" in html

    def test_the_gnss_tab_still_tells_the_live_state(self, on):
        client = login_as(VIEW)
        _city(client)
        html = _get(client, reverse("environment-gnss")).content.decode()
        assert "Typical higher-scintillation window: now, until 03:00" in html


class TestTheDayGeometry:
    FIXED = gnss.params_from_settings()

    def _day(self, now, sunsets=None, sunrises=None):
        return gnss_day.day_geometry(now, sunsets, sunrises, self.FIXED)

    def test_the_span_runs_noon_to_noon(self):
        evening = datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO)
        morning = datetime(2026, 10, 20, 9, 0, tzinfo=SANTIAGO)
        assert gnss_day.span_start(evening) == datetime(
            2026, 10, 19, 12, tzinfo=SANTIAGO
        )
        assert gnss_day.span_start(morning) == datetime(
            2026, 10, 19, 12, tzinfo=SANTIAGO
        )
        assert gnss_day.span_start(
            datetime(2026, 10, 19, 12, tzinfo=SANTIAGO)
        ) == datetime(2026, 10, 19, 12, tzinfo=SANTIAGO)

    def test_fixed_hours_put_the_window_from_21_to_03_with_the_peak_at_midnight(self):
        day = self._day(datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO))
        assert day["window"] == [(9 / 24, 15 / 24)]
        assert day["peak"] == [12 / 24]
        assert day["now"] == pytest.approx(9.5 / 24)
        assert day["now_label"] == "21:30"
        assert day["window_label"] == "21:00 - 03:00"

    def test_the_window_is_the_one_windows_between_returns(self):
        now = datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO)
        sunset = datetime(2026, 10, 19, 19, 30, tzinfo=SANTIAGO)
        sunsets = {sunset.date(): sunset}
        day = self._day(now, sunsets)
        found = gnss.windows_between(
            gnss_day.span_start(now),
            gnss_day.span_start(now) + gnss_day.SPAN,
            None,
            sunsets,
        )
        assert len(found) == 1
        start, end = found[0]
        assert start == datetime(2026, 10, 19, 20, 30, tzinfo=SANTIAGO)  # puesta + 60
        assert day["window"] == [
            (8.5 / 24, (end - gnss_day.span_start(now)) / gnss_day.SPAN)
        ]

    def test_the_night_runs_from_sunset_to_the_next_sunrise(self):
        now = datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO)
        sunsets = {now.date(): datetime(2026, 10, 19, 19, 30, tzinfo=SANTIAGO)}
        sunrises = {
            datetime(2026, 10, 20).date(): datetime(
                2026, 10, 20, 7, 30, tzinfo=SANTIAGO
            )
        }
        day = self._day(now, sunsets, sunrises)
        assert day["night"] == [(7.5 / 24, 19.5 / 24)]

    def test_without_a_forecast_there_is_no_night_track(self):
        day = self._day(datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO))
        assert day["night"] == []

    def test_out_of_season_nothing_is_invented(self):
        day = self._day(datetime(2026, 6, 15, 21, 30, tzinfo=SANTIAGO))
        assert day["window"] == [] and day["peak"] == [] and day["window_label"] == ""

    def test_the_clock_change_shifts_the_axis_labels_not_the_span(self):
        # El salto de septiembre: 5 -> 6 de septiembre de 2026 pasa de las 24:00 a las 01:00.
        day = self._day(datetime(2026, 9, 5, 18, 0, tzinfo=SANTIAGO))
        assert [label for _x, label in day["ticks"]] == ["12", "18", "01", "07", "13"]
        assert [round(x, 4) for x, _l in day["ticks"]] == [0.0, 0.25, 0.5, 0.75, 1.0]
        utc = ZoneInfo("UTC")
        assert (
            day["end"].astimezone(utc) - day["begin"].astimezone(utc) == gnss_day.SPAN
        )

    def test_the_marker_never_leaves_the_span(self):
        day = self._day(datetime(2026, 10, 19, 12, 0, tzinfo=SANTIAGO))
        assert 0 <= day["now"] <= 1


class TestTheBandSvg:
    DAY = gnss_day.day_geometry(
        datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO),
        None,
        None,
        gnss.params_from_settings(),
    )

    def _svg(self, day=None):
        return gnss_charts.render_day_band(day or self.DAY, "gx")

    def test_it_is_an_image_with_title_description_and_no_inline_style(self):
        svg = self._svg()
        assert 'role="img"' in svg and 'aria-labelledby="gx-t gx-d"' in svg
        assert re.search(r'<title id="gx-t">[^<]+</title>', svg)
        assert re.search(r'<desc id="gx-d">[^<]+</desc>', svg)
        assert "style=" not in svg and "<script" not in svg

    def test_the_description_says_the_window_and_the_time_and_that_it_is_not_a_measurement(
        self,
    ):
        desc = re.search(r'<desc id="gx-d">([^<]+)</desc>', self._svg()).group(1)
        assert "21:00 - 03:00" in desc and "21:30" in desc
        assert "not a measurement" in desc

    def test_the_window_is_hatched_so_it_is_not_only_colour(self):
        svg = self._svg()
        assert 'fill="url(#gx-h)"' in svg and '<pattern id="gx-h"' in svg

    def test_a_missing_window_says_so_and_draws_no_window(self):
        svg = self._svg({**self.DAY, "window": [], "peak": [], "window_label": ""})
        assert "id-gx-win" not in svg
        assert "No typical window in these 24 hours" in svg

    def test_the_geometry_is_attributes_and_the_axis_has_five_labels(self):
        svg = self._svg()
        assert svg.count('class="id-gx-tick"') == 5
        assert 'class="id-gx-now"' in svg and 'class="id-gx-now-dot"' in svg

    def test_it_never_prints_an_intensity(self):
        svg = self._svg().lower()
        for word in ("s4", "roti", "tec", "kp ", "intensity", "índice"):
            assert word not in svg, word


@pytest.mark.django_db
class TestTheStripBand:
    def test_the_gnss_tile_draws_the_band_and_prints_the_window_beside_it(self, on):
        client = login_as(VIEW)
        _city(client)
        html = _strip(client)
        cell = html.split("env-cell--gnss")[1]
        assert 'role="img"' in cell and 'id="env-gx-strip-t"' in cell
        assert re.search(r"Typical window: \d\d:\d\d - \d\d:\d\d", cell)

    def test_the_tile_reads_the_same_window_as_the_header_text(self, on):
        client = login_as(VIEW)
        _city(client)
        html = _strip(client)
        assert "Typical higher-scintillation window: now, until 03:00" in html
        label = re.search(r"Typical window: \d\d:\d\d - (\d\d:\d\d)", html).group(1)
        assert label == "03:00"

    def test_the_weather_only_person_still_gets_no_airspace_tile(self, on):
        html = _strip(login_as(VIEW))
        assert "env-cell--airspace" not in html
