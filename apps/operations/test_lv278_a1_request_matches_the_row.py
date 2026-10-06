"""LV-278 (A-1): la solicitud creada guarda lo mismo que la hoja muestra.

Al preparar las modalidades de SIGO se encontró un desacuerdo viejo: sobre un
área irregular, la fila «Datos para SIGO» del plan es la del **círculo que la
encierra** (`LV-132`), pero `create_requests_from_plan` guardaba el **punto
dibujado** y el **radio promedio** de lo dibujado. Dos pantallas del mismo plan
daban dos solicitudes distintas, y la que se presenta es la segunda.

Y el radio redondeaba con `round()`, que lleva `.5` al par (30.5 → 30): el resto
de la hoja usa `whole()` (`.5` hacia arriba). Con respuesta del usuario del
2026-10-06 —*«al más cercano»*— el radio usa el mismo redondeo que todo lo demás.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.geo.sections import whole
from apps.operations.flight_requests import create_requests_from_plan, plan_sections
from apps.operations.test_r108_enclosing_row import _document, _row, plan  # noqa: F401

# Un área alargada de **cinco** vértices (no un rectángulo: con las modalidades,
# un cuadrilátero deja de ser «círculo envolvente»), con el punto en una punta.
IRREGULAR = [(0, 0), (0.5, 0), (0.5, 0.02), (0.25, 0.03), (0, 0.02)]


@pytest.mark.django_db
def test_the_request_stores_the_enclosing_circle_like_the_row(plan):  # noqa: F811
    document = _document(IRREGULAR, with_point_at=(0, 0))
    row = _row(plan, document)
    assert row["is_enclosing"] is True

    (request,), _sections = create_requests_from_plan(plan, created_by=plan.created_by)

    assert float(request.center_lat) == pytest.approx(row["lat"], abs=1e-6)
    assert float(request.center_lon) == pytest.approx(row["lon"], abs=1e-6)
    assert request.radius_m == row["radius_m"]
    assert request.amc == row["amc"]
    assert whole(request.amc_distance_km) == row["amc_distance_km"]


@pytest.mark.django_db
def test_the_radius_rounds_half_up_like_the_rest_of_the_sheet(plan, monkeypatch):  # noqa: F811
    """`round(30.5)` es 30 en Python. La hoja declara 31."""
    from apps.geo import sections as sections_module

    real = sections_module.split_sections

    def with_half_radius(document):
        found = real(document)
        for section in found:
            section.radius_m = 30.5
            section.enclosing = None
        return found

    monkeypatch.setattr(
        "apps.operations.flight_requests.split_sections", with_half_radius
    )
    row = _row(plan, _document(IRREGULAR, with_point_at=(0, 0)))

    (request,), _sections = create_requests_from_plan(plan, created_by=plan.created_by)

    assert row["radius_m"] == 31
    assert request.radius_m == 31


@pytest.mark.django_db
def test_the_split_preview_shows_what_will_be_declared(plan, client):  # noqa: F811
    """La vista previa armaba sus filas con `split_sections` crudo: mostraba el
    punto dibujado, no el centro que la solicitud va a declarar."""
    _row(plan, _document(IRREGULAR, with_point_at=(0, 0)))
    declared = plan_sections(plan)[0]
    admin = User.objects.create_superuser("a1", "a1@test.com", "pw")  # nosec B106
    client.force_login(admin)

    response = client.get(reverse("geo-plan-split", args=[plan.pk]))

    assert response.status_code == 200
    shown = response.context["sections"][0]
    assert shown["lat"] == declared["lat_readable"]
    assert shown["radius_m"] == declared["radius_m"]
    assert f"{declared['radius_m']} m" in response.content.decode()
