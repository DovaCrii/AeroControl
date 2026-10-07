"""LV-278 (bloque B): la hoja sigue el orden y los rótulos del portal de SIGO.

El usuario envió las cuatro capturas del formulario el 2026-10-06. Lo que muestran:

- **Punto Centro:** Latitud y Longitud (Grados, Minutos, Segundos) y «Radio / Ancho».
- **Punto Corredor:** sólo **Punto Inicio** y **Punto Término**, sin radio ni ancho.
- **Triangular / Cuadricular:** «Vértice 1, 2, 3 (y 4)», cada uno con Latitud y Longitud.
- **Todas:** Altura (metros o pies), Hora Desde/Hasta, el mapa KMZ y «Tiempo
  aproximado de vuelo (minutos)».

Y de ahí dos correcciones al bloque A: el corredor no tiene N vértices sino dos, y
faltaba la última casilla del formulario.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.geo.test_lv278_modalities import (
    SQUARE_CCW,
    TRIANGLE_CCW,
    _at,
    _document,
    _line,
    _polygon,
)
from apps.operations.flight_requests import create_requests_from_plan, sigo_sheet
from apps.operations.forms import FlightRequestForm
from apps.operations.test_lv278_a2_modalities import _publish
from apps.operations.test_r108_enclosing_row import plan  # noqa: F401

CORRIDOR = [_at(0, 0), _at(100, 0), _at(100, 300)]


@pytest.fixture
def admin(client, db):
    user = User.objects.create_superuser("b1", "b1@test.com", "pw")  # nosec B106
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestThePlanSheetFollowsThePortal:
    def _body(self, admin, plan, *placemarks):  # noqa: F811
        _publish(plan, _document(*placemarks))
        return admin.get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

    def test_a_corridor_has_a_start_and_an_end_point_and_nothing_else(
        self,
        admin,
        plan,  # noqa: F811
    ):
        body = self._body(admin, plan, _line("Camino", [_at(0, 0), _at(500, 0)]))

        assert "Punto Inicio (Corredor)" in body
        assert "Punto Término (Corredor)" in body
        assert "Vértice" not in body
        assert 'sigo-field-label">Radio (m)' not in body

    def test_a_triangle_has_three_vertices(self, admin, plan):  # noqa: F811
        body = self._body(admin, plan, _polygon("Tri", TRIANGLE_CCW))

        assert "Vértice 1" in body and "Vértice 3" in body
        assert "Vértice 4" not in body
        assert "Punto Inicio" not in body

    def test_a_quadrilateral_has_four_vertices(self, admin, plan):  # noqa: F811
        body = self._body(admin, plan, _polygon("Cuad", SQUARE_CCW))

        assert "Vértice 4" in body
        assert "Vértice 5" not in body

    def test_the_vertex_boxes_have_three_per_axis_and_no_hemisphere_box(
        self,
        admin,
        plan,  # noqa: F811
    ):
        """El portal no tiene casilla de hemisferio: va en el rótulo, no en una
        caja que haya que llenar."""
        body = self._body(admin, plan, _polygon("Tri", TRIANGLE_CCW))

        # Tres vértices x dos ejes x (grados, minutos, segundos) = 18 casillas.
        assert body.count('sigo-field-label">Grados') == 6
        assert body.count('sigo-field-label">Minutos') == 6
        assert body.count('sigo-field-label">Segundos') == 6
        assert 'sigo-field-label">Hemisferio' not in body
        assert "Latitud · S" in body and "Longitud · W" in body

    def test_the_centre_used_for_the_aerodrome_is_stated_not_boxed(
        self,
        admin,
        plan,  # noqa: F811
    ):
        body = self._body(admin, plan, _polygon("Tri", TRIANGLE_CCW))

        assert "Centro desde el que se midió el aeródromo" in body

    def test_a_circle_keeps_its_centre_boxes_and_radius(self, admin, plan):  # noqa: F811
        from apps.geo.test_lv278_modalities import _circle, _point

        body = self._body(admin, plan, _circle("Anillo", 150), _point("Circulo", 0, 0))

        assert 'sigo-field-label">Radio (m)' in body
        assert "Vértice" not in body
        assert "Punto Inicio" not in body


@pytest.mark.django_db
class TestACorridorIsDeclaredByItsEnds:
    def test_a_request_keeps_exactly_the_start_and_end(self, plan):  # noqa: F811
        _publish(plan, _document(_line("Camino", CORRIDOR)))

        (request,), _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )

        assert request.area_modality == "corridor"
        assert request.vertices == [CORRIDOR[0], CORRIDOR[-1]]
        request.clean()

    def test_the_preview_warns_that_the_points_in_between_are_not_declared(
        self,
        admin,
        plan,  # noqa: F811
    ):
        _publish(plan, _document(_line("Camino", CORRIDOR)))

        body = admin.get(reverse("geo-plan-split", args=[plan.pk])).content.decode()

        assert "Corredor simplificado" in body

    def test_a_straight_corridor_gets_no_such_warning(self, admin, plan):  # noqa: F811
        _publish(plan, _document(_line("Recta", [_at(0, 0), _at(500, 0)])))

        body = admin.get(reverse("geo-plan-split", args=[plan.pk])).content.decode()

        assert "Corredor simplificado" not in body

    def test_the_request_page_shows_start_and_end_with_their_boxes(
        self,
        admin,
        plan,  # noqa: F811
    ):
        _publish(plan, _document(_line("Camino", CORRIDOR)))
        (request,), _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )

        body = admin.get(request.get_absolute_url()).content.decode()

        assert "Punto Inicio (Corredor)" in body
        assert "Punto Término (Corredor)" in body
        assert "Vértice" not in body
        assert "Radio (m)" not in body


@pytest.mark.django_db
class TestTheLastBoxOfTheForm:
    def test_the_request_stores_the_approximate_flight_time(self, plan):  # noqa: F811
        _publish(plan, _document(_polygon("Tri", TRIANGLE_CCW)))
        (request,), _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )

        assert request.approx_flight_minutes == 0  # lo que el portal trae por omisión

    def test_it_is_editable_in_the_form(self):
        """Un campo del modelo que el formulario no ofrece se queda en su valor
        por omisión para siempre; acá la persona lo decide."""
        assert "approx_flight_minutes" in FlightRequestForm.Meta.fields

    def test_the_sheet_carries_it_and_the_height_in_both_units(self, plan):  # noqa: F811
        _publish(plan, _document(_polygon("Tri", TRIANGLE_CCW)))
        (request,), _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )
        request.approx_flight_minutes = 45
        request.altitude_m = 100
        request.save()

        sheet = sigo_sheet(request)

        assert sheet["approx_flight_minutes"] == 45
        assert sheet["altitude_m"] == 100
        assert sheet["altitude_ft"] == 328  # 100 m = 328,08 ft, cerrado

    def test_the_request_page_shows_the_box(self, admin, plan):  # noqa: F811
        _publish(plan, _document(_polygon("Tri", TRIANGLE_CCW)))
        (request,), _sections = create_requests_from_plan(
            plan, created_by=plan.created_by
        )
        request.approx_flight_minutes = 45
        request.save()

        body = admin.get(request.get_absolute_url()).content.decode()

        assert "Tiempo aproximado de vuelo (minutos)" in body
        assert "<td>45</td>" in body
