"""LV-278 (A-2): las solicitudes y las pantallas conocen las cuatro modalidades.

Pedido del usuario (2026-10-06): *«cuando se cargue el tipo de KMZ, indicar lo que
traerá»*, y que lo que se declara sea lo que el portal de SIGO pide. Acá se prueba
la mitad de las solicitudes y las pantallas; el motor que reconoce las formas está
en `apps/geo/test_lv278_modalities.py`.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.geo.models import GeoPlanVersion
from apps.geo.sections import split_sections
from apps.geo.test_lv278_modalities import (
    SQUARE_CCW,
    TRIANGLE_CCW,
    _circle,
    _document,
    _line,
    _point,
    _polygon,
)
from apps.operations.flight_requests import (
    create_requests_from_plan,
    plan_sections,
    sigo_sheet,
)
from apps.operations.models import FlightPermission, FlightRequest
from apps.operations.test_r108_enclosing_row import plan  # noqa: F401


def _publish(geo_plan, document):
    version = GeoPlanVersion.objects.create(
        plan=geo_plan,
        version_number=1,
        content=document,
        content_checksum="x" * 64,
        source="import",
        created_by=geo_plan.created_by,
    )
    geo_plan.current_version = version
    geo_plan.save(update_fields=["current_version", "updated_at"])
    return geo_plan


def _mixed_document():
    return _document(
        _circle("Anillo", 150),
        _point("Circulo", 0, 0),
        _polygon("Tri", TRIANGLE_CCW),
        _polygon("Cuad", SQUARE_CCW),
        _line("Corr", [[-68.9, -22.3], [-68.9, -22.299], [-68.899, -22.299]]),
    )


@pytest.mark.django_db
class TestRequestsKeepTheirModality:
    def test_each_area_becomes_a_request_with_its_modality_and_vertices(
        self,
        plan,  # noqa: F811
    ):
        _publish(plan, _mixed_document())

        requests, _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )

        by_title = {request.title: request for request in requests}
        assert by_title["Circulo"].area_modality == "center_point"
        assert by_title["Circulo"].vertices == []
        assert by_title["Circulo"].radius_m == pytest.approx(150, abs=3)
        assert by_title["Tri"].area_modality == "triangle"
        assert len(by_title["Tri"].vertices) == 3
        assert by_title["Cuad"].area_modality == "quadrilateral"
        assert len(by_title["Cuad"].vertices) == 4
        assert by_title["Corr"].area_modality == "corridor"
        assert len(by_title["Corr"].vertices) == 3

    def test_only_the_circle_has_a_radius(self, plan):  # noqa: F811
        _publish(plan, _mixed_document())

        requests, _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )

        radii = {r.title: r.radius_m for r in requests}
        assert radii["Tri"] is None
        assert radii["Cuad"] is None
        assert radii["Corr"] is None
        assert radii["Circulo"] is not None

    def test_every_request_has_a_centre_and_an_aerodrome_measured_from_it(
        self,
        plan,  # noqa: F811
    ):
        """Respuesta del usuario: *«siempre debe generar un punto central para
        que lo calcule»*. Sin punto dibujado, el centro es el calculado."""
        _publish(plan, _document(_polygon("Tri", TRIANGLE_CCW)))

        (request,), (section,) = create_requests_from_plan(
            plan, created_by=plan.created_by
        )

        assert request.center_lat == Decimal(f"{section.center[0]:.6f}")
        assert request.center_lon == Decimal(f"{section.center[1]:.6f}")
        assert request.amc is not None
        assert request.amc_distance_km is not None

    def test_the_stored_vertices_match_what_the_engine_found(self, plan):  # noqa: F811
        document = _document(_polygon("Tri", TRIANGLE_CCW))
        _publish(plan, document)

        (request,), _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )

        assert request.vertices == split_sections(document)[0].vertices


@pytest.mark.django_db
class TestTheModelGuardsTheModality:
    def _request(self, cost_center, **overrides):
        values = {
            "title": "Area",
            "cost_center": cost_center,
            "center_lat": Decimal("-22.3"),
            "center_lon": Decimal("-68.9"),
        }
        values.update(overrides)
        return FlightRequest(**values)

    @pytest.fixture
    def centre(self, plan):  # noqa: F811
        return plan.cost_center

    def test_a_value_outside_the_four_modalities_cannot_be_saved(self, centre):
        request = self._request(centre, area_modality="hexagon")

        with pytest.raises(IntegrityError), transaction.atomic():
            request.save()

    @pytest.mark.parametrize(
        ("modality", "vertices"),
        [
            ("center_point", []),
            ("triangle", [[0, 0], [1, 0], [0, 1]]),
            ("quadrilateral", [[0, 0], [1, 0], [1, 1], [0, 1]]),
            ("corridor", [[0, 0], [1, 1]]),
            ("corridor", [[0, 0], [1, 1], [2, 0], [3, 3]]),
        ],
    )
    def test_the_right_number_of_vertices_is_valid(self, centre, modality, vertices):
        self._request(centre, area_modality=modality, vertices=vertices).clean()

    @pytest.mark.parametrize(
        ("modality", "vertices"),
        [
            ("center_point", [[0, 0]]),
            ("triangle", [[0, 0], [1, 0]]),
            ("triangle", [[0, 0], [1, 0], [0, 1], [1, 1]]),
            ("quadrilateral", [[0, 0], [1, 0], [0, 1]]),
            ("corridor", [[0, 0]]),
            ("corridor", []),
        ],
    )
    def test_the_wrong_number_of_vertices_is_rejected(self, centre, modality, vertices):
        request = self._request(centre, area_modality=modality, vertices=vertices)

        with pytest.raises(ValidationError) as error:
            request.clean()

        assert "vertices" in error.value.error_dict

    @pytest.mark.parametrize("vertices", [{"a": 1}, "x", [[1], [2], [3]], [None] * 3])
    def test_vertices_that_are_not_coordinates_are_rejected(self, centre, vertices):
        request = self._request(centre, area_modality="triangle", vertices=vertices)

        with pytest.raises(ValidationError) as error:
            request.clean()

        assert "vertices" in error.value.error_dict

    def test_requests_from_before_lv278_are_circles(self, centre):
        request = self._request(centre)
        request.save()

        request.refresh_from_db()

        assert request.area_modality == "center_point"
        assert request.vertices == []


@pytest.mark.django_db
class TestTheSheetsShowTheModality:
    def _triangle_request(self, plan):  # noqa: F811
        _publish(plan, _document(_polygon("Tri", TRIANGLE_CCW)))
        (request,), _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )
        return request

    def test_the_request_sheet_carries_the_vertices_in_whole_numbers(
        self,
        plan,  # noqa: F811
    ):
        request = self._triangle_request(plan)

        sheet = sigo_sheet(request)

        assert sheet["area_modality"] == "triangle"
        assert len(sheet["vertices"]) == 3
        for vertex in sheet["vertices"]:
            assert isinstance(vertex["dms_lat"]["seconds"], int)
            assert "." not in vertex["lat_readable"]
        assert sheet["radius_m"] is None

    def test_the_plan_sheet_lists_the_vertices_and_drops_the_radius_box(
        self,
        plan,  # noqa: F811
        client,
    ):
        _publish(plan, _document(_polygon("Tri", TRIANGLE_CCW)))
        admin = User.objects.create_superuser("a2", "a2@test.com", "pw")  # nosec B106
        client.force_login(admin)

        body = client.get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

        assert "Vértices del área" in body
        assert "sentido horario" in body
        assert "Triangular" in body
        # La casilla «Radio (m)» es de la modalidad Punto Centro.
        assert 'sigo-field-label">Radio (m)' not in body

    def test_a_circle_sheet_is_unchanged(self, plan, client):  # noqa: F811
        _publish(plan, _document(_circle("Circulo", 150), _point("Centro", 0, 0)))
        admin = User.objects.create_superuser("a2c", "a2c@test.com", "pw")  # nosec B106
        client.force_login(admin)

        body = client.get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

        assert 'sigo-field-label">Radio (m)' in body
        assert "Vértices del área" not in body

    def test_the_request_page_shows_modality_and_vertices(self, plan, client):  # noqa: F811
        request = self._triangle_request(plan)
        admin = User.objects.create_superuser("a2d", "a2d@test.com", "pw")  # nosec B106
        client.force_login(admin)

        body = client.get(request.get_absolute_url()).content.decode()

        assert "Modalidad del área" in body
        assert "Triangular" in body
        assert "Vértices del área" in body
        assert "1. " in body and "3. " in body


@pytest.mark.django_db
class TestTheKmzPreview:
    """La pantalla «qué traerá este KMZ»."""

    @pytest.fixture
    def preview(self, plan, client):  # noqa: F811
        _publish(plan, _mixed_document())
        admin = User.objects.create_superuser("a2e", "a2e@test.com", "pw")  # nosec B106
        client.force_login(admin)
        return client.get(reverse("geo-plan-split", args=[plan.pk]))

    def test_it_says_which_modalities_the_kmz_has(self, preview):
        summary = {e["label"]: e["count"] for e in preview.context["summary"]}

        assert [str(label) for label in summary] == [
            "Punto Centro",
            "Triangular",
            "Cuadricular",
            "Punto Corredor",
        ]
        assert set(summary.values()) == {1}

    def test_it_lists_what_each_area_brings_and_what_is_missing(self, preview):
        rows = {r["section"].name: r for r in preview.context["sections"]}

        assert "Vértices del área" in rows["Tri"]["brings"]
        assert "Radio (m)" in rows["Circulo"]["brings"]
        assert "Radio (m)" not in rows["Tri"]["brings"]
        for row in rows.values():
            assert row["missing"] == ["Altura (m)", "Horario"]

    def test_a_calculated_centre_is_told_apart_from_a_drawn_one(self, preview):
        rows = {r["section"].name: r for r in preview.context["sections"]}

        assert "Punto centro (calculado)" in rows["Tri"]["brings"]
        assert "Punto centro (calculado)" not in rows["Circulo"]["brings"]

    def test_the_page_draws_the_new_columns(self, preview):
        body = preview.content.decode()

        assert "Qué trae el KMZ" in body
        assert "Falta completar" in body
        assert "Punto Corredor" in body

    def test_the_old_one_circle_per_request_claim_is_gone(self, preview):
        """SIGO ya no acepta sólo «una circunferencia con su punto central»."""
        assert "una circunferencia con su punto central" not in preview.content.decode()

    def test_it_still_needs_the_add_permission(self, plan, client):  # noqa: F811
        _publish(plan, _mixed_document())
        nobody = User.objects.create_user("a2f", "a2f@test.com", "pw")  # nosec B106
        client.force_login(nobody)

        response = client.get(reverse("geo-plan-split", args=[plan.pk]))

        assert response.status_code == 403


@pytest.mark.django_db
class TestPermitFromAShapeWithoutRadius:
    def test_a_triangle_fills_the_centre_and_leaves_the_radius_empty(
        self,
        plan,  # noqa: F811
    ):
        from apps.operations.views import fill_permission_from_plan

        _publish(plan, _document(_polygon("Tri", TRIANGLE_CCW)))
        permit = FlightPermission.objects.create(
            cost_center=plan.cost_center,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            location="Sector",
            area_type="unpopulated",
        )

        filled = fill_permission_from_plan(plan, permit)
        permit.refresh_from_db()

        assert permit.latitude is not None
        assert permit.radius_km is None
        assert "radius_km" not in filled
        assert plan_sections(plan)[0]["radius_m"] is None
