"""LV-301: la lista de permisos abre con los últimos generados primero.

Pedido del usuario (2026-10-13): *«al ingresar a los permisos, que siempre me muestre
primero los últimos generados»*. Sin un orden elegido la lista salía por número
ascendente y el permiso recién creado quedaba en la última página.
"""

from datetime import date

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter


@pytest.fixture
def three_permits(db):
    centre = CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)
    return [
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            permission_number=number,
            location="Calama",
            area_type="unpopulated",
            valid_from=date(2026, 9, 1),
            valid_until=date(2026, 11, 1),
        )
        for number in ("P-AAA", "P-BBB", "P-CCC")
    ]


def _order(response):
    html = response.content.decode()
    return sorted(
        ("P-AAA", "P-BBB", "P-CCC"), key=lambda marker: html.index(f"DGAC: {marker}")
    )


@pytest.mark.django_db
class TestNewestFirst:
    def test_the_list_opens_with_the_last_created_first(self, three_permits):
        client = login_as("view_flightpermission")

        response = client.get(reverse("permission-list"))

        assert _order(response) == ["P-CCC", "P-BBB", "P-AAA"]

    def test_filtering_does_not_change_the_default_order(self, three_permits):
        client = login_as("view_flightpermission")

        response = client.get(reverse("permission-list"), {"status": "requested"})

        assert _order(response) == ["P-CCC", "P-BBB", "P-AAA"]

    def test_a_chosen_sort_still_wins(self, three_permits):
        client = login_as("view_flightpermission")

        response = client.get(
            reverse("permission-list"), {"sort": "number", "dir": "asc"}
        )

        assert _order(response) == ["P-AAA", "P-BBB", "P-CCC"]

    def test_the_status_sort_is_untouched(self, three_permits):
        client = login_as("view_flightpermission")

        response = client.get(
            reverse("permission-list"), {"sort": "status", "dir": "asc"}
        )

        assert response.status_code == 200
