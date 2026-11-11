"""LV-430: reporte de vuelo imprimible (formato J.E.J.), KML y CSV.

Todo sale de datos sintéticos: el mismo log DJI simulado de LV-429 (coordenadas y serie
inventadas). La impresión real del mapa en un navegador no se prueba acá.
"""

# ruff: noqa: F811 - las fixtures se importan de las pruebas de LV-427 y LV-429
import csv
import io
import re
import xml.etree.ElementTree as ET  # noqa: S405  # nosec B405 - sólo lee la salida propia
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core import branding
from apps.core.exports import neutralize
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.operations.flightlog.report import _readings, csv_cell
from apps.operations.flightlog.timeline import phase_segments
from apps.operations.flightlog.types import (
    FlightEvent,
    FlightTrack,
    TrackPoint,
)
from apps.operations.models import FlightLogAnalysis
from apps.registry.models import Aircraft

from .test_lv427_flight_log_analysis import (  # noqa: F401 - fixtures compartidas
    READ,
    centre,
    isolated_storage,
    permit,
)
from .test_lv429_dji_adapter import (  # noqa: F401 - fixtures compartidas
    _ROWS,
    SERIAL,
    TIP_RTH,
    _attach_dji,
    fake,
)

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "static" / "img" / "brand"
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}
URLS = ("flight-analysis-report", "flight-analysis-kml", "flight-analysis-csv")


@pytest.fixture
def analysis(fake, permit):
    return FlightLogAnalysis.objects.get(document=_attach_dji(permit))


def _get(name, analysis, *perms, **kwargs):
    client = login_as(*(perms or READ), **kwargs)
    return client.get(reverse(name, args=[analysis.pk]))


def _region(html, marker, until="</section>"):
    return html.split(marker, 1)[1].split(until, 1)[0]


@pytest.fixture
def page(analysis):
    return _get("flight-analysis-report", analysis).content.decode()


def _ramp_track(heights, leg=None):
    return FlightTrack(
        points=[
            TrackPoint(t=float(i * 10), lat=1.0 + i * 1e-4, lon=2.0, height_m=h)
            for i, h in enumerate(heights)
        ],
        return_leg=leg,
    )


# ── la vista imprimible ──────────────────────────────────────────────────────


class TestPrintableReport:
    def test_header_has_the_company_logo_and_the_area_seal(self, page):
        assert re.search(r'<img class="fr-logo" src="[^"]*jej-logo-blue\.png', page)
        assert re.search(
            r'<img class="fr-seal" src="[^"]*img/brand/LD_sello_claro\.svg', page
        )
        # La firma de área no reemplaza al logo de la empresa: están los dos.
        assert page.index("fr-logo") < page.index("fr-seal")
        assert "<h1" in page and "Reporte de vuelo" in page

    def test_four_kpis_with_their_units(self, page):
        strip = _region(page, 'id="fr-kpis"', "</section>")
        cells = re.findall(
            r'<span class="fr-kpi-value">(.*?)</span>\s*</div>', strip, re.S
        )
        assert len(cells) == 4
        values = [re.sub(r"<small>.*", "", c) for c in cells]
        units = [re.search(r"<small>(.*?)</small>", c).group(1) for c in cells]
        assert values == ["4:10", "500", "101", "13"]
        assert units == ["min:s", "m", "m", "%"]

    def test_summary_and_the_low_battery_notice(self, page):
        assert 'id="fa-narrative"' in page and "El vuelo duró" in page
        assert 'id="fa-low-battery"' in page

    def test_timeline_shows_phases_and_one_mark_per_warning(self, page, analysis):
        svg = _region(page, 'id="fr-timeline"', "</div>")
        phases = set(re.findall(r'data-phase="(\w+)"', svg))
        assert {"takeoff", "work", "return"} <= phases
        track = FlightTrack.from_dict(analysis.result)
        warnings = [e for e in track.events if e.level in ("warning", "critical")]
        assert warnings
        assert len(re.findall(r'data-level="(warning|critical)"', svg)) == len(warnings)
        assert "fr-legend" in page

    def test_three_charts_each_with_a_reading(self, page):
        for key in ("height", "speed", "battery"):
            block = _region(page, f'id="fa-chart-{key}"', "</figure>")
            assert '<svg class="fa-chart"' in block
            assert 'class="fr-reading"' in block
        assert "de 90% a 13%" in page or "90% a 13%" in page

    def test_events_table_keeps_the_original_log_text(self, page):
        table = _region(page, 'id="fa-events"', "</table>")
        assert TIP_RTH.split(".")[0] in table
        assert 'class="fr-raw"' in table

    def test_operation_data_and_traceability(self, page, analysis):
        operation = _region(page, 'id="fr-operation"', "</dl>")
        # Sin cruce con el registro: lo que dice el log, marcado como tal.
        assert "Mavic 3 Enterprise" in operation and SERIAL in operation
        assert operation.count("según el log") == 2
        assert "DGAC-0900" in operation and "Faena X" in operation
        trace = _region(page, 'id="fr-trace"', "</dl>")
        assert analysis.document.title in trace
        assert "dji-1" in trace and "dji" in trace

    def test_registry_data_replaces_the_log_when_the_serial_matches(self, fake, permit):
        Aircraft.objects.create(
            registration="RPA-9100",
            serial_number=SERIAL,
            type="RPA",
            model="Registro M3E",
            manufacturer="DJI",
            cost_center=permit.cost_center,
        )
        analysis = FlightLogAnalysis.objects.get(document=_attach_dji(permit))
        html = _get("flight-analysis-report", analysis).content.decode()
        operation = _region(html, 'id="fr-operation"', "</dl>")
        assert "RPA-9100" in operation and "Registro M3E" in operation
        assert "según el log" not in operation

    def test_footer_and_the_print_button(self, page):
        assert 'id="fr-print"' in page and "flight-report.js" in page
        assert 'href="/' in page and "flight-report.css" in page
        assert "Generado por AeroControl" in page and "Impreso" in page

    def test_the_analysis_screen_links_to_the_three_downloads(self, analysis):
        html = (
            login_as(*READ)
            .get(reverse("flight-analysis", args=[analysis.pk]))
            .content.decode()
        )
        for name, ident in zip(URLS, ("report", "kml", "csv")):
            url = reverse(name, args=[analysis.pk])
            assert f'href="{url}"' in html and f'id="fa-{ident}-link"' in html


# ── fases de la línea de tiempo ──────────────────────────────────────────────


class TestPhases:
    def test_takeoff_work_return_and_landing_in_order(self):
        track = _ramp_track(
            [0, 20, 60, 60, 60, 60, 40, 20, 5, 0],
            leg=[40.0, 70.0],
        )
        names = [p for p, _a, _b in phase_segments(track)]
        assert names == ["takeoff", "work", "return", "landing"]
        spans = [(a, b) for _p, a, b in phase_segments(track)]
        assert spans[0][0] == 0 and spans[-1][1] == 90
        assert all(x[1] == y[0] for x, y in zip(spans, spans[1:]))

    def test_without_height_the_whole_flight_is_work(self):
        track = _ramp_track([None, None, None])
        assert [p for p, *_x in phase_segments(track)] == ["work"]

    def test_everything_after_the_return_is_landing(self):
        track = _ramp_track([0, 30, 30, 30, 30, 30], leg=[20.0, 30.0])
        assert phase_segments(track)[-1][0] == "landing"

    def test_too_few_points_draw_nothing(self):
        assert phase_segments(FlightTrack()) == []


class TestReadings:
    def test_the_battery_reading_names_the_warning_and_what_was_left(self):
        track = _ramp_track([1, 2, 3, 4])
        for point, level in zip(track.points, (90, 60, 30, 20)):
            point.battery_pct = level
        track.events = [
            FlightEvent(
                t=20.0,
                level="warning",
                code="tip:low_battery_rth",
                raw_text="x",
                explanation="",
            )
        ]
        text = _readings(track)["battery"]
        assert "90%" in text and "20%" in text and "0:20" in text and "30%" in text

    def test_no_data_means_no_sentence(self):
        assert _readings(FlightTrack()) == {"height": "", "speed": "", "battery": ""}


# ── KML ──────────────────────────────────────────────────────────────────────


class TestKml:
    def test_it_is_valid_and_has_the_path_and_the_marks(self, analysis):
        response = _get("flight-analysis-kml", analysis)

        assert response.status_code == 200
        assert response["Content-Type"].startswith(
            "application/vnd.google-earth.kml+xml"
        )
        root = ET.fromstring(response.content)  # noqa: S314  # nosec B314
        line = root.find(".//k:LineString", KML_NS)
        coords = line.find("k:coordinates", KML_NS).text.split()
        assert len(coords) == len(_ROWS)
        lon, lat, alt = (float(x) for x in coords[2].split(","))
        assert (lat, lon, alt) == (10.001, 20.0, 60.0)
        assert line.find("k:altitudeMode", KML_NS).text == "relativeToGround"
        names = [n.text for n in root.findall(".//k:Placemark/k:name", KML_NS)]
        assert len(names) >= 4  # trayectoria, despegue, aterrizaje y avisos
        track = FlightTrack.from_dict(analysis.result)
        warnings = [e for e in track.events if e.level in ("warning", "critical")]
        assert len(names) == 3 + len(warnings)

    def test_the_file_name_has_the_date_and_the_aircraft(self, analysis):
        disposition = _get("flight-analysis-kml", analysis)["Content-Disposition"]
        assert disposition.startswith("attachment;")
        assert "flight-2030-01-15-mavic-3-enterprise.kml" in disposition

    def test_a_log_without_height_is_clamped_to_the_ground(self, analysis):
        result = analysis.result
        for point in result["points"]:
            point["height_m"] = None
        analysis.result = result
        analysis.save()

        root = ET.fromstring(_get("flight-analysis-kml", analysis).content)  # noqa: S314  # nosec B314
        assert root.find(".//k:altitudeMode", KML_NS).text == "clampToGround"


# ── CSV ──────────────────────────────────────────────────────────────────────


class TestCsv:
    def test_header_and_one_row_per_saved_point(self, analysis):
        response = _get("flight-analysis-csv", analysis)

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert response["Content-Disposition"].endswith('.csv"')
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        assert rows[0] == [
            "t_s",
            "lat",
            "lon",
            "height_m",
            "speed_ms",
            "battery_pct",
            "satellites",
        ]
        assert len(rows) - 1 == len(_ROWS)
        assert rows[3][:4] == ["60.0", "10.001", "20.0", "60.0"]

    def test_text_cells_are_neutralised_and_numbers_stay_numbers(self):
        assert csv_cell("=1+1") == neutralize("=1+1") == "'=1+1"
        assert csv_cell("@SUM(A1)").startswith("'")
        # Una latitud sur no es una fórmula: con apóstrofo dejaría de ser un número.
        assert csv_cell(-33.4) == -33.4
        assert csv_cell(None) == ""


# ── permisos ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", URLS)
class TestAccess:
    def test_view_flightrecord_is_required(self, name, analysis):
        assert _get(name, analysis, "view_flightpermission").status_code == 403
        client = login_as()
        assert client.get(reverse(name, args=[analysis.pk])).status_code == 403

    def test_another_tenant_gets_a_404(self, name, analysis):
        other = OperationalTenant.objects.create(name="Otra", slug="otra-430")
        assert _get(name, analysis, *READ, member_of=other).status_code == 404

    def test_an_analysis_with_an_error_has_no_report(self, name, analysis):
        FlightLogAnalysis.objects.filter(pk=analysis.pk).update(
            status="error", error_code="incomplete", result={}
        )
        assert _get(name, analysis).status_code == 404


# ── marca y hojas de estilo ──────────────────────────────────────────────────

LD_SVGS = ("LD_sello_claro", "LD_sello_oscuro", "LD_icono_claro", "LD_icono_oscuro")
FORBIDDEN = re.compile(
    r"<script|onload\s*=|onclick\s*=|href\s*=\s*[\"']https?:|xlink:href|<foreignObject"
    r"|@import|<image",
    re.IGNORECASE,
)


class TestBrandAssets:
    def test_only_the_four_area_svgs_are_there(self):
        assert sorted(p.name for p in BRAND.iterdir()) == sorted(
            f"{n}.svg" for n in LD_SVGS
        )

    @pytest.mark.parametrize("name", LD_SVGS)
    def test_no_svg_carries_code_or_external_links(self, name):
        text = (BRAND / f"{name}.svg").read_text(encoding="utf-8")
        assert not FORBIDDEN.search(text)
        assert "<script" not in text and 'href="http' not in text
        assert "<title>Levantamiento Digital</title>" in text
        assert len(text.encode()) <= 10_000


def _lf_size(path):
    return len(path.read_bytes().replace(b"\r\n", b"\n"))


class TestStylesheet:
    css = ROOT / "static" / "css" / "flight-report.css"

    def test_it_has_its_own_ceiling_and_the_big_sheets_were_not_touched(self):
        assert _lf_size(self.css) <= 10 * 1024
        for name in ("app.css", "identity.css"):
            sheet = (ROOT / "static" / "css" / name).read_text(encoding="utf-8")
            assert "fr-kpi" not in sheet and "fr-timeline" not in sheet

    def test_the_palette_is_the_brand_manuals(self):
        text = self.css.read_text(encoding="utf-8").lower()
        for colour in (
            branding.BLUE,
            branding.CYAN,
            branding.GRAY_DARK,
            branding.GRAY_LIGHT,
        ):
            assert colour.lower() in text
        assert "helvetica" in text

    def test_it_prints_on_a_portrait_a4_and_hides_the_toolbar(self):
        text = self.css.read_text(encoding="utf-8")
        assert "A4 portrait" in text and "@media print" in text
        assert ".fr-noprint { display: none" in text
        assert "print-color-adjust: exact" in text

    def test_the_seal_prints_at_least_25_mm(self):
        text = self.css.read_text(encoding="utf-8")
        match = re.search(r"\.fr-seal \{ width: (\d+)mm", text)
        assert match and int(match.group(1)) >= 25


def test_the_map_script_leaves_the_map_for_the_print_script():
    assert "_fa = {" in (ROOT / "static/js/flight-analysis.js").read_text(
        encoding="utf-8"
    )
    printer = (ROOT / "static/js/flight-report.js").read_text(encoding="utf-8")
    assert "invalidateSize" in printer and "fitBounds" in printer
    assert "window.print()" in printer
