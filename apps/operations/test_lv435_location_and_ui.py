"""LV-435: ubicación del despegue (comuna, provincia y región), fechas legibles, chips y avisos con
los tokens del tema y gráficos con la última etiqueta del eje X dentro del dibujo.

Datos sintéticos; la coordenada es la Plaza de Armas de Santiago (lugar público) y el nombre de la
comuna se compara contra `locate(...)`, no se teclea.
"""

# ruff: noqa: F811 - las fixtures se importan de otras pruebas
import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.geo.administrative import locate
from apps.operations.flightlog import charts
from apps.operations.flightlog.location import flight_place, place_note
from apps.operations.flightlog.types import FlightTrack
from apps.operations.models import FlightLogAnalysis

from .test_lv427_flight_log_analysis import (  # noqa: F401 - fixtures compartidas
    centre,
    isolated_storage,
)
from .test_lv429_dji_adapter import SERIAL, fake  # noqa: F401
from .test_lv431_flight_logs_section import VIEW, _doc, drone  # noqa: F401

SANTIAGO = (-33.4378, -70.6505)
STARTED = "2030-01-15T10:00:00-03:00"


def _analysis(centre, drone, lat, lon):
    track = {
        "summary": {
            "started_at": STARTED,
            "started_at_utc": "2030-01-15T13:00:00Z",
            "timezone": "America/Santiago",
            "duration_s": 250,
            "distance_m": 1234.4,
            "max_height_m": 101,
            "takeoff": [lat, lon],
            "landing": [lat, lon],
        },
        "points": [
            {"t": 0, "lat": lat, "lon": lon, "height_m": 0, "battery_pct": 90},
            {"t": 125, "lat": lat, "lon": lon, "height_m": 50, "battery_pct": 50},
            {"t": 250, "lat": lat, "lon": lon, "height_m": 10, "battery_pct": 13},
        ],
        "events": [
            {
                "t": 100,
                "level": "warning",
                "code": "warn:low_battery_rth",
                "raw_text": "",
                "explanation": "",
            }
        ],
        "aircraft": {"serial": SERIAL},
    }
    return FlightLogAnalysis.objects.create(
        cost_center=centre,
        aircraft=drone,
        document=_doc(drone),
        status="ok",
        result=track,
    )


def _page(analysis, name="flight-analysis"):
    return login_as(VIEW).get(reverse(name, args=[analysis.pk])).content.decode()


@pytest.fixture
def inside(centre, drone):
    return _analysis(centre, drone, *SANTIAGO)


@pytest.fixture
def outside(centre, drone):
    return _analysis(centre, drone, 0.0, 0.0)


class TestLocation:
    def test_the_fixture_point_is_inside_a_commune(self):
        assert locate(*SANTIAGO) is not None
        assert locate(0.0, 0.0) is None

    def test_flight_place_reads_the_takeoff(self, inside):
        track = FlightTrack.from_dict(inside.result)

        assert flight_place(track) == locate(*SANTIAGO)
        assert flight_place(FlightTrack()) is None

    def test_the_analysis_shows_commune_province_region_and_the_note(self, inside):
        place = locate(*SANTIAGO)

        html = _page(inside)

        card = html.split('id="fa-place"', 1)[1].split("</div>", 1)[0]
        assert f"{place['comuna']}, {place['provincia']}" in card
        assert place["region"] in card
        assert 'id="fa-place-note"' in html and place_note()[:30] in html

    def test_without_a_commune_the_card_is_hidden_but_the_note_says_so(self, outside):
        html = _page(outside)

        assert 'id="fa-place"' not in html
        assert 'id="fa-place-note"' in html

    def test_the_report_has_the_sentence_the_card_and_the_note(self, inside):
        place = locate(*SANTIAGO)

        html = _page(inside, "flight-analysis-report")

        sentence = html.split('id="fr-place"', 1)[1].split("</p>", 1)[0]
        for part in (place["comuna"], place["provincia"], place["region"]):
            assert part in sentence
        assert "%(" not in html
        assert 'id="fr-place-card"' in html and 'id="fr-place-note"' in html

    def test_the_report_without_a_commune_has_no_sentence(self, outside):
        html = _page(outside, "flight-analysis-report")

        assert 'id="fr-place"' not in html and 'id="fr-place-card"' not in html
        assert 'id="fr-place-note"' in html

    def test_the_kml_takeoff_description_names_the_commune(self, inside):
        place = locate(*SANTIAGO)

        kml = (
            login_as(VIEW)
            .get(reverse("flight-analysis-kml", args=[inside.pk]))
            .content.decode()
        )

        assert place["comuna"] in kml


class TestDates:
    def test_the_summary_dates_are_d_m_y_not_raw_iso(self, inside):
        html = _page(inside)

        assert "15-01-2030 10:00:00 (America/Santiago)" in html
        assert "15-01-2030 13:00:00 (UTC)" in html
        assert "2030-01-15T10:00:00" not in html


class TestChipsAndNotices:
    def test_the_verdict_chip_uses_the_analysis_font_not_the_identity_one(self, inside):
        html = _page(inside)

        verdict = html.split('id="fa-comp-verdict"', 1)[0].rsplit("<span", 1)[1]
        assert "fa-chip" in verdict and "id-chip" not in verdict
        assert (
            "id-chip"
            not in html.split('id="fa-compliance"', 1)[1].split("</section>", 1)[0]
        )

    def test_the_report_uses_the_same_chip(self, inside):
        html = _page(inside, "flight-analysis-report")

        assert "fa-chip fa-chip--" in html and "id-chip" not in html

    def test_notices_use_the_theme_tokens_not_bootstrap_yellow(self, inside):
        html = _page(inside)

        assert "alert-warning" not in html
        battery = html.split('id="fa-low-battery"', 1)[0].rsplit("<div", 1)[1]
        assert "fa-notice fa-notice--warning" in battery
        css = open("static/css/flight-analysis.css", encoding="utf-8").read()
        assert "var(--sev-warning-bg)" in css and "border-left-width: 4px" in css

    def test_the_event_levels_are_small_chips(self, inside):
        html = _page(inside)

        row = html.split('id="fa-events"', 1)[1]
        assert "fa-chip fa-chip--sm fa-chip--warning" in row


class TestCharts:
    SERIES = [(0, 1.0), (30, 5.0), (1700, 2.0)]

    def test_the_x_axis_anchors_first_start_and_last_end(self):
        svg = str(charts.line_chart(self.SERIES, "Height (m)", "Time"))

        ticks = [part for part in svg.split("<text") if 'class="fa-tick"' in part]
        x_ticks = [part for part in ticks if 'y="170"' in part]
        assert [t.split('text-anchor="')[1].split('"')[0] for t in x_ticks] == [
            "start",
            "middle",
            "end",
        ]

    def test_the_line_has_a_soft_area_and_uses_the_css_variable(self):
        svg = str(charts.line_chart(self.SERIES, "Height (m)", "Time"))
        css = open("static/css/flight-analysis.css", encoding="utf-8").read()

        assert 'class="fa-area"' in svg
        assert svg.index("fa-area") < svg.index("fa-line")
        assert "stroke: var(--fa-line)" in css
        assert "--fa-line: #1E418C" in css and "--fa-line: #60C4F5" in css
