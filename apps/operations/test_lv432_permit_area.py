"""LV-432: área y altura autorizadas del permiso contra el log de vuelo.

Todo sintético: un cuadrado de 200 m x 200 m cerca de (10, 20) y trayectorias inventadas. Los
metros se miden con la misma proyección local que usa el cálculo, así que las cifras son exactas.
"""

# ruff: noqa: F811 - las fixtures se importan de las pruebas de LV-427
import json
import math
import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.translation import gettext

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.geo.test_lv278_modalities import _closed_line, _document, _polygon
from apps.operations.flightlog.compliance import (
    AREA_TOLERANCE_M,
    authorized_area,
    check_flight,
    distance_outside_m,
    _rings,
)
from apps.operations.flightlog.types import FlightTrack, TrackPoint
from apps.operations.models import FlightLogAnalysis
from apps.registry.models import CostCenter

from .test_lv427_flight_log_analysis import (  # noqa: F401 - fixtures compartidas
    READ,
    centre,
    isolated_storage,
    permit,
)
from .test_lv431_flight_logs_section import _doc

LAT0, LON0 = 10.0, 20.0
K = 6_371_000.0 * math.pi / 180  # metros por grado, como `compliance._local`
PLANS = "view_geoplan"
CHANGE = "change_flightloganalysis"


def at(east_m, north_m):
    """`[lon, lat, 0]` de un punto a (este, norte) metros del origen."""
    return [
        LON0 + east_m / (K * math.cos(math.radians(LAT0))),
        LAT0 + north_m / K,
        0,
    ]


SQUARE = [at(0, 0), at(200, 0), at(200, 200), at(0, 200)]


def _track(positions, heights=None, step=10.0):
    heights = heights or [None] * len(positions)
    points = []
    for i, ((east, north), height) in enumerate(zip(positions, heights)):
        lon, lat, _z = at(east, north)
        points.append(TrackPoint(t=i * step, lat=lat, lon=lon, height_m=height))
    return FlightTrack(points=points)


def _line(eastings, north=100):
    return [(e, north) for e in eastings]


EAST_OUT = _line(
    [*range(50, 200, 20), 205, 230, 250]
)  # 230 y 250 quedan fuera (> 10 m)


def _plan(permit, document):
    author = get_user_model().objects.create_user("autor-432", password="pw")  # nosec B106
    plan = GeoPlan.objects.create(
        title="Plan ficticio",
        cost_center=permit.cost_center,
        flight_permission=permit,
        created_by=author,
    )
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=document,
        content_checksum="x" * 64,
        source="import",
        created_by=author,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


@pytest.fixture
def square_permit(permit):
    permit.max_altitude_m = 120
    permit.save(update_fields=["max_altitude_m"])
    _plan(permit, _document(_polygon("Area", SQUARE)))
    return permit


def _analysis(permit, track, **extra):
    return FlightLogAnalysis.objects.create(
        permission=permit,
        cost_center=permit.cost_center,
        aircraft=permit._aircraft,
        document=_doc(permit._aircraft),
        status=FlightLogAnalysis.STATUS_OK,
        result=track.to_dict(),
        **extra,
    )


def _page(analysis, *perms):
    client = login_as(*(perms or (*READ, PLANS)))
    return client.get(reverse("flight-analysis", args=[analysis.pk]))


def _map_data(response):
    raw = re.search(
        r'<script id="fa-map-data" type="application/json">(.*?)</script>',
        response.content.decode(),
        re.S,
    ).group(1)
    return json.loads(raw)


# ── geometría ────────────────────────────────────────────────────────────────


class TestGeometry:
    @staticmethod
    def polygons():
        return _rings([{"type": "Polygon", "coordinates": [[*SQUARE, SQUARE[0]]]}])

    def test_inside_is_zero_and_outside_is_the_distance_to_the_edge(self):
        polys = self.polygons()
        inside = at(100, 100)
        outside = at(230, 100)
        assert distance_outside_m(inside[1], inside[0], polys) == 0.0
        assert distance_outside_m(outside[1], outside[0], polys) == pytest.approx(
            30, abs=0.01
        )

    def test_a_corner_is_measured_to_the_corner(self):
        polys = self.polygons()
        p = at(230, 240)  # 30 m al este y 40 m al norte de la esquina
        assert distance_outside_m(p[1], p[0], polys) == pytest.approx(50, abs=0.01)

    def test_a_hole_is_outside(self):
        hole = [at(80, 80), at(120, 80), at(120, 120), at(80, 120)]
        polys = _rings(
            [
                {
                    "type": "Polygon",
                    "coordinates": [[*SQUARE, SQUARE[0]], [*hole, hole[0]]],
                }
            ]
        )
        centre_ = at(100, 100)
        assert distance_outside_m(centre_[1], centre_[0], polys) == pytest.approx(
            20, abs=0.01
        )

    def test_the_tolerance_is_ten_metres(self):
        assert AREA_TOLERANCE_M == 10.0
        # A 5 m del borde (círculo de 100 m) es ruido de GPS; a 30 m ya es salir.
        near = check_flight(_track(_line([100, 205])), _FakePermit(), False)
        far = check_flight(_track(_line([100, 230])), _FakePermit(), False)
        assert near["segments"] == [] and len(far["segments"]) == 1

    def test_a_trimble_closed_linestring_is_the_area(self, permit):
        _plan(permit, _document(_closed_line("Circulo", SQUARE)))
        area = authorized_area(permit, with_plans=True)
        assert area.kind == "plan"
        p = at(300, 100)
        assert area.distance_outside(p[1], p[0]) == pytest.approx(
            100, abs=0.5
        )  # el KMZ se redondea a 6 decimales


class _FakePermit:
    """Un permiso con un cuadrado vía círculo no sirve: se usa el área ya armada."""

    max_altitude_m = None
    latitude = LAT0 + 100 / K
    longitude = LON0 + 100 / (K * math.cos(math.radians(LAT0)))
    radius_km = 0.1  # círculo de 100 m de radio alrededor del centro del cuadrado
    geo_plans = None


# ── el cálculo ───────────────────────────────────────────────────────────────


class TestCompliance:
    def test_a_stretch_outside_is_measured_in_seconds_and_metres(self, square_permit):
        result = check_flight(_track(EAST_OUT), square_permit, True)
        assert result["available"] and result["level"] == "critical"
        (segment,) = result["segments"]
        assert segment["kind"] == "area"
        assert (segment["start"], segment["end"]) == (90.0, 100.0)
        # Dos puntos, el último con medio paso de cada lado: 5 + 5 + 5 s.
        assert segment["seconds"] == 15.0
        assert segment["peak"] == pytest.approx(50, abs=0.1)
        assert result["area"]["outside_s"] == 15.0
        assert "15 s" in result["lines"][0] and "50 m" in result["lines"][0]

    def test_a_short_blip_is_a_warning_not_critical(self, square_permit):
        track = _track(_line([100, 100, 230, 100, 100]), step=2.0)
        result = check_flight(track, square_permit, True)
        assert result["level"] == "warning"
        assert result["segments"][0]["seconds"] == 2.0

    def test_height_above_the_limit_is_measured(self, square_permit):
        heights = [0, 50, 100, 130, 140, 135, 100, 50, 10, 0, 0]
        track = _track(_line(range(50, 160, 10)), heights)
        result = check_flight(track, square_permit, True)
        (segment,) = result["segments"]
        assert segment["kind"] == "height"
        assert (segment["start"], segment["end"]) == (30.0, 50.0)
        assert segment["seconds"] == 30.0 and segment["peak"] == 140.0
        assert result["height"]["limit_m"] == 120
        assert result["level"] == "critical"

    def test_a_flight_entirely_inside_is_ok(self, square_permit):
        heights = [10, 40, 80, 100, 80, 40, 10, 0, 0, 0, 0]
        track = _track(_line(range(50, 160, 10)), heights)
        result = check_flight(track, square_permit, True)
        assert result["level"] == "ok" and result["segments"] == []
        assert result["verdict"] == gettext(
            "Inside the area and under the height for the whole flight"
        )

    def test_the_caveats_always_travel_with_the_result(self, square_permit):
        text = " ".join(check_flight(_track(EAST_OUT), square_permit, True)["caveats"])
        assert "punto de despegue" in text and "GPS" in text

    def test_without_a_permit_there_is_nothing_to_compare(self):
        result = check_flight(_track(EAST_OUT), None, True)
        assert not result["available"] and result["level"] == "info"
        assert result["verdict"] == gettext("No authorized area to compare")
        assert result["reasons"] == [
            gettext("The flight log is not linked to a permit.")
        ]

    def test_a_permit_without_geometry_says_why(self, permit):
        result = check_flight(_track(EAST_OUT), permit, True)
        assert not result["available"]
        assert (
            gettext(
                "The permit has no area geometry (no KMZ plan and no centre with radius)."
            )
            in result["reasons"]
        )

    def test_the_circle_of_the_permit_is_the_fallback_without_a_plan(self, permit):
        permit.latitude, permit.longitude = _FakePermit.latitude, _FakePermit.longitude
        permit.radius_km = 0.1
        permit.save(update_fields=["latitude", "longitude", "radius_km"])
        area = authorized_area(permit, with_plans=True)
        assert area.kind == "circle"
        result = check_flight(_track(_line([100, 250])), permit, True)
        (segment,) = result["segments"]
        assert segment["peak"] == pytest.approx(50, abs=0.5)  # 150 m del centro - 100 m

    def test_without_the_geo_plan_permission_the_plan_is_not_used(self, square_permit):
        assert authorized_area(square_permit, with_plans=False).kind is None


# ── pantalla y reporte ───────────────────────────────────────────────────────


class TestScreen:
    def test_the_map_data_carries_the_area_and_the_breaches(self, square_permit):
        analysis = _analysis(square_permit, _track(EAST_OUT))
        data = _map_data(_page(analysis))["compliance"]
        assert data["area"]["kind"] == "plan"
        assert len(data["area"]["polygons"][0][0]) >= 4
        assert len(data["outside"]) == 1 and data["over"] == []

    def test_the_block_shows_the_verdict_and_the_caveats(self, square_permit):
        analysis = _analysis(square_permit, _track(EAST_OUT))
        html = _page(analysis).content.decode()
        block = html.split('id="fa-compliance"', 1)[1].split("</section>", 1)[0]
        assert "id-chip--critical" in block
        assert 'id="fa-comp-caveats"' in block and "GPS" in block

    def test_without_a_plan_permission_the_area_is_not_exposed(self, square_permit):
        analysis = _analysis(square_permit, _track(EAST_OUT))
        data = _map_data(_page(analysis, *READ))["compliance"]
        assert data["area"] is None

    def test_no_permit_shows_the_reason(self, permit):
        analysis = _analysis(permit, _track(EAST_OUT))
        FlightLogAnalysis.objects.filter(pk=analysis.pk).update(permission=None)
        html = _page(analysis).content.decode()
        assert 'id="fa-comp-reason"' in html
        assert "id-chip--info" in html

    def test_it_is_still_403_without_permission_and_404_across_tenants(
        self, square_permit
    ):
        analysis = _analysis(square_permit, _track(EAST_OUT))
        url = reverse("flight-analysis", args=[analysis.pk])
        assert login_as().get(url).status_code == 403
        other = OperationalTenant.objects.create(name="Otra", slug="otra-432")
        assert login_as(*READ, member_of=other).get(url).status_code == 404


class TestReport:
    def test_the_printable_report_has_the_block_before_the_map(self, square_permit):
        analysis = _analysis(square_permit, _track(EAST_OUT))
        client = login_as(*READ, PLANS)
        html = client.get(
            reverse("flight-analysis-report", args=[analysis.pk])
        ).content.decode()
        assert html.index('id="fr-comp-h"') < html.index('id="fr-map-h"')
        assert html.index('id="fr-sum-h"') < html.index('id="fr-comp-h"')
        assert 'id="fa-comp-verdict"' in html and "id-chip--critical" in html

    def test_the_timeline_marks_the_stretch_outside(self, square_permit):
        analysis = _analysis(square_permit, _track(EAST_OUT))
        client = login_as(*READ, PLANS)
        html = client.get(
            reverse("flight-analysis-report", args=[analysis.pk])
        ).content.decode()
        svg = html.split('id="fr-timeline"', 1)[1].split("</div>", 1)[0]
        assert len(re.findall(r'data-flag="area"', svg)) == 1

    def test_an_inside_flight_has_no_red_band(self, square_permit):
        analysis = _analysis(square_permit, _track(_line(range(50, 160, 10))))
        client = login_as(*READ, PLANS)
        html = client.get(
            reverse("flight-analysis-report", args=[analysis.pk])
        ).content.decode()
        assert "data-flag=" not in html and "id-chip--ok" in html


# ── vincular el permiso desde el análisis ────────────────────────────────────


class TestLinkPermit:
    def _unlinked(self, permit):
        analysis = _analysis(permit, _track(EAST_OUT))
        FlightLogAnalysis.objects.filter(pk=analysis.pk).update(permission=None)
        return analysis

    def _post(self, analysis, permit_pk, *perms):
        client = login_as(*(perms or (*READ, CHANGE)))
        return client.post(
            reverse("flight-analysis", args=[analysis.pk]),
            {"permission": str(permit_pk)},
        )

    def test_it_links_a_permit_of_the_same_cost_center(self, permit):
        analysis = self._unlinked(permit)
        assert self._post(analysis, permit.pk).status_code == 302
        analysis.refresh_from_db()
        assert analysis.permission_id == permit.pk

    def test_it_needs_the_change_permission(self, permit):
        analysis = self._unlinked(permit)
        assert self._post(analysis, permit.pk, *READ).status_code == 403
        analysis.refresh_from_db()
        assert analysis.permission_id is None

    def test_a_permit_of_another_cost_center_is_not_accepted(self, permit):
        from apps.operations.models import FlightPermission

        analysis = self._unlinked(permit)
        other_cc = CostCenter.objects.create(
            code="CC903", name="Otra", operates_flights=True
        )
        foreign = FlightPermission.objects.create(
            cost_center=other_cc,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="DGAC-0903",
            location="Sector 3",
            area_type="unpopulated",
            valid_from=permit.valid_from,
            valid_until=permit.valid_until,
        )
        assert self._post(analysis, foreign.pk).status_code == 404

    def test_the_selector_is_only_shown_to_who_can_change(self, permit):
        analysis = self._unlinked(permit)
        shown = _page(analysis, *READ, CHANGE).content.decode()
        hidden = _page(analysis, *READ).content.decode()
        assert 'id="fa-permit-form"' in shown and 'id="fa-permit-form"' not in hidden
