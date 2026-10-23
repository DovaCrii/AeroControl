"""LV-367 (fase 3): la pestaña Centelleo como infografía de servidor.

Se fija: la línea de 24 h coincide con `windows_between` (también en el cambio de hora), el calendario de
temporada sale de `GNSS_SCINT_*`, el SVG es `role="img"` con título y descripción, sin `style=""`, con las
cifras escritas al lado, y NUNCA muestra una intensidad: la fuente no publica ningún índice y aquí no se
inventa ninguno. Las horas y la hora pico se rotulan como interpretación nuestra.
"""

# ruff: noqa: F811  (los fixtures se importan de test_lv358_strip y se usan como argumentos)
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.environment import gnss_day
from apps.environment.templatetags import gnss_charts
from apps.environment.test_lv358_strip import (  # noqa: F401
    VIEW,
    calls,
    english,
    forecast,
    no_network,
    on,
    _city,
    _get,
)
from apps.weather import gnss

SANTIAGO = ZoneInfo("America/Santiago")
PARAMS = gnss.params_from_settings()
GNSS = reverse("environment-gnss")
EVENING = datetime(2026, 10, 19, 21, 30, tzinfo=SANTIAGO)


def _day(now=EVENING, sunsets=None, sunrises=None):
    return gnss_day.day_geometry(now, sunsets, sunrises, PARAMS)


def _with_night():
    sunsets = {EVENING.date(): datetime(2026, 10, 19, 19, 30, tzinfo=SANTIAGO)}
    sunrises = {
        (EVENING + timedelta(days=1)).date(): datetime(
            2026, 10, 20, 7, 30, tzinfo=SANTIAGO
        )
    }
    return _day(EVENING, sunsets, sunrises)


class TestTheWindowIsTheOneOfTheHeader:
    def test_across_the_september_clock_change_the_window_is_the_real_span(self):
        now = datetime(2026, 9, 5, 22, 0, tzinfo=SANTIAGO)
        day = _day(now)
        begin = gnss_day.span_start(now)
        raw = gnss.windows_between(begin, begin + gnss_day.SPAN, PARAMS, None)
        assert len(raw) == 1 and len(day["window"]) == 1
        start, end = raw[0]
        utc = ZoneInfo("UTC")
        width = (end.astimezone(utc) - start.astimezone(utc)) / gnss_day.SPAN
        x0, x1 = day["window"][0]
        # 21:00 (-04) a 03:00 (-03): la hora 00:00-01:00 no existe, así que son 5 h reales y no 6.
        assert x1 - x0 == pytest.approx(width) and width == pytest.approx(5 / 24)

    def test_across_the_april_clock_change_the_window_is_six_plus_one_hours(self):
        now = datetime(2027, 4, 3, 22, 0, tzinfo=SANTIAGO)
        day = _day(now)
        begin = gnss_day.span_start(now)
        raw = gnss.windows_between(begin, begin + gnss_day.SPAN, PARAMS, None)
        assert len(raw) == 1 and len(day["window"]) == 1
        start, end = raw[0]
        utc = ZoneInfo("UTC")
        width = (end.astimezone(utc) - start.astimezone(utc)) / gnss_day.SPAN
        assert day["window"][0][1] - day["window"][0][0] == pytest.approx(width)

    def test_the_peak_only_shows_inside_a_window(self):
        assert _day()["peak"] == [0.5]
        assert _day(datetime(2026, 6, 15, 21, 30, tzinfo=SANTIAGO))["peak"] == []

    def test_labels_for_night_and_peak(self):
        day = _with_night()
        assert day["night_label"] == "19:30 - 07:30"
        assert day["peak_label"] == "00:00"
        assert _day()["night_label"] == ""


class TestTheSeasonCalendar:
    def test_it_starts_in_september_so_the_filled_months_are_contiguous(self):
        season = gnss_day.season_geometry(EVENING, PARAMS)
        months = season["months"]
        assert [m["month"] for m in months][:3] == [9, 10, 11]
        assert [m["active"] for m in months] == [True] * 8 + [False] * 4
        assert len(months) == 12

    def test_only_the_current_month_is_marked(self):
        season = gnss_day.season_geometry(EVENING, PARAMS)
        assert [m["month"] for m in season["months"] if m["current"]] == [10]
        assert season["current_active"] is True
        june = gnss_day.season_geometry(datetime(2026, 6, 1, tzinfo=SANTIAGO), PARAMS)
        assert june["current_active"] is False

    def test_the_months_follow_the_settings(self, settings):
        settings.GNSS_SCINT_MONTHS = "1,2,3"
        season = gnss_day.season_geometry(EVENING)
        assert [m["month"] for m in season["months"]][:3] == [1, 2, 3]
        assert [m["active"] for m in season["months"]][:4] == [True, True, True, False]

    def test_all_year_or_nothing_still_gives_twelve_boxes(self, settings):
        settings.GNSS_SCINT_MONTHS = ",".join(str(m) for m in range(1, 13))
        assert len(gnss_day.season_geometry(EVENING)["months"]) == 12
        settings.GNSS_SCINT_MONTHS = ""
        season = gnss_day.season_geometry(EVENING)
        assert len(season["months"]) == 12 and not any(
            m["active"] for m in season["months"]
        )

    def test_the_year_rule_cites_the_source_for_the_peak(self):
        years = gnss_day.season_geometry(EVENING, PARAMS)["years"]
        assert [y["year"] for y in years] == [2025, 2026, 2027, 2028]
        assert [y["year"] for y in years if y["peak"]] == [gnss_day.SOURCE_PEAK_YEAR]
        assert [y["year"] for y in years if y["end"]] == [2028]
        assert [y["year"] for y in years if y["current"]] == [2026]


class TestTheFullChart:
    def _svg(self, day=None):
        return gnss_charts.render_day_chart(day or _with_night(), "gx")

    def test_it_is_an_image_with_title_description_no_style_and_no_script(self):
        svg = self._svg()
        assert 'role="img"' in svg and 'aria-labelledby="gx-t gx-d"' in svg
        assert re.search(r'<title id="gx-t">[^<]+</title>', svg)
        assert re.search(r'<desc id="gx-d">[^<]+</desc>', svg)
        assert "style=" not in svg and "<script" not in svg

    def test_the_description_carries_every_figure_that_is_drawn(self):
        desc = re.search(r'<desc id="gx-d">([^<]+)</desc>', self._svg()).group(1)
        for fragment in (
            "Night: 19:30 - 07:30.",
            "Typical window: 20:",
            "Peak hour: 00:00 (our interpretation).",
            "21:30",
            "not a measurement",
        ):
            assert fragment in desc, fragment

    def test_each_track_has_its_label_and_the_window_is_hatched(self):
        svg = self._svg()
        assert ">Night</text>" in svg and ">Typical window</text>" in svg
        assert 'fill="url(#gx-h)"' in svg and svg.count('class="id-gx-track"') == 2
        assert 'class="id-gx-night"' in svg and 'class="id-gx-now"' in svg

    def test_the_peak_is_labelled_as_our_interpretation(self):
        assert "00:00 · peak hour (our interpretation)" in self._svg()

    def test_without_a_forecast_there_is_no_night_track(self):
        svg = self._svg(_day())
        assert ">Night</text>" not in svg and "id-gx-night" not in svg
        assert svg.count('class="id-gx-track"') == 1

    def test_out_of_season_there_is_no_window_and_no_peak(self):
        svg = self._svg(_day(datetime(2026, 6, 15, 21, 30, tzinfo=SANTIAGO)))
        assert "id-gx-win" not in svg and "id-gx-peak" not in svg
        assert "No typical window in these 24 hours." in svg

    def test_the_peak_label_anchors_inward_near_the_edges(self):
        edge = {**_with_night(), "peak": [0.05]}
        assert 'text-anchor="start"' in self._svg(edge).split("id-gx-label--peak")[1]
        edge = {**_with_night(), "peak": [0.95]}
        assert 'text-anchor="end"' in self._svg(edge).split("id-gx-label--peak")[1]

    def test_it_never_draws_or_names_an_intensity(self):
        svg = self._svg().lower()
        for word in ("s4", "roti", "tec", "kp ", "intensity", "scale", "índice"):
            assert word not in svg, word

    def test_the_geometry_is_inside_the_canvas(self):
        svg = self._svg()
        width = gnss_charts.WIDTH
        for x, w in re.findall(
            r'<rect class="id-gx-(?:win|night)" x="([\d.]+)" y="\d+" width="([\d.]+)"',
            svg,
        ):
            assert 0 <= float(x) and float(x) + float(w) <= width + 0.01


@pytest.mark.django_db
class TestTheTab:
    def _tab(self, **extra):
        client = login_as(VIEW)
        _city(client)
        return _get(client, GNSS, **extra).content.decode()

    def test_it_draws_the_chart_the_calendar_and_prints_the_same_figures(self, on):
        html = self._tab()
        assert 'id="env-gx-day-t"' in html
        assert html.count('class="id-gx-month') >= 12
        for fragment in (
            "Night",
            "Typical window",
            "Peak hour (our interpretation)",
            "Now",
        ):
            assert f"<dt>{fragment}</dt>" in html, fragment
        assert re.search(r"<dt>Night</dt><dd>\d\d:\d\d - \d\d:\d\d</dd>", html)
        assert "<dd>21:30</dd>" in html

    def test_exactly_one_month_says_today_and_the_season_is_filled(self, on):
        html = self._tab()
        assert html.count('<b class="id-gx-today">today</b>') == 1
        assert html.count("id-gx-month is-on") == 8

    def test_the_year_rule_is_written_out_as_text(self, on):
        html = self._tab()
        assert "Peak 2025 (according to the source)" in html
        assert "Effects until 2028" in html

    def test_it_says_there_is_no_scale_and_never_shows_a_value(self, on):
        html = self._tab()
        assert (
            "No measurement: statistical reference from the GEOCOM criterion." in html
        )
        assert "the source publishes no intensity scale" in html
        assert not re.search(r"\bS4\b|\bROTI\b|\bTEC\b|\bKp\b", html)

    def test_the_glossary_has_an_icon_and_a_text_for_each_term(self, on):
        html = self._tab()
        glossary = html.split("id-gx-glossary")[1].split("</dl>")[0]
        for icon in ("satellite", "check", "moon", "clock", "info"):
            assert f"#icon-{icon}" in glossary, icon
        for term in (
            "Scintillation",
            "RTK and PPK",
            "Night",
            "Typical window",
            "Our interpretation",
        ):
            assert f"</svg>{term}</dt>" in glossary, term

    def test_the_assumption_and_the_single_referential_stay(self, on):
        html = self._tab()
        assert "are our interpretation of" in html
        assert html.count("Information only. It is not a flight condition") == 1

    def test_without_a_city_it_still_renders_with_fixed_hours_and_no_night(self, on):
        html = _get(login_as(VIEW), GNSS).content.decode()
        assert "Fixed hours: 21:00 to 03:00." in html
        assert "<dt>Night</dt><dd>" not in html

    def test_the_spanish_tab_is_translated(self, on):
        client = login_as(VIEW)
        _city(client)
        html = client.get(GNSS, headers={"Accept-Language": "es"}).content.decode()
        for text in (
            "Sin medición: referencia estadística del criterio de GEOCOM.",
            "Hora pico (interpretación nuestra)",
            "Máximo 2025 (según la fuente)",
            "Lo que esta pantalla no muestra",
        ):
            assert text in html, text
        assert "Peak hour" not in html

    def test_a_person_without_the_permission_gets_403(self, on):
        assert _get(login_as(), GNSS).status_code == 403

    def test_the_sprite_has_no_orphan_symbol_left(self):
        from apps.core import test_lv367_visual_base as base

        assert base.PENDING == set()
