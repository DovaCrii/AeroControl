"""LV-280: la lista de Permisos se ordena haciendo clic en el encabezado.

Pedido del usuario (2026-10-06, captura de Permisos): poder ordenar ascendente y
descendente desde el encabezado, en toda la app. `SortableColumnsMixin` ya existía
(UX-07) y Permisos no lo usaba.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


def _permit(centre, days):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        location="Sector",
        area_type="unpopulated",
        valid_from=TODAY - timedelta(days=30),
        valid_until=TODAY + timedelta(days=days),
    )


@pytest.fixture
def permits(db):
    centre = CostCenter.objects.create(code="CC100", name="Uno", operates_flights=True)
    return {days: _permit(centre, days) for days in (50, 10, 30)}


def _order(client, **params):
    response = client.get(reverse("permission-list"), params)
    return [permit.valid_until for permit in response.context["objects"]]


def test_validity_sorts_ascending_and_descending(client, admin_user, permits):
    client.force_login(admin_user)

    ascending = _order(client, sort="validity", dir="asc")
    descending = _order(client, sort="validity", dir="desc")

    assert ascending == sorted(ascending)
    assert descending == sorted(ascending, reverse=True)


def test_the_headers_carry_the_sort_links(client, admin_user, permits):
    client.force_login(admin_user)

    body = client.get(reverse("permission-list")).content.decode()

    assert "sort=validity&amp;dir=asc" in body or "sort=validity&dir=asc" in body
    # Operadores es una relación: no hay valor propio que ordene la fila.
    assert "sort=operators" not in body


def test_a_column_outside_the_allow_list_is_ignored(client, admin_user, permits):
    """`?sort=` llega a `order_by`: un campo no declarado ni ordena ni revienta."""
    client.force_login(admin_user)

    response = client.get(reverse("permission-list"), {"sort": "operators__full_name"})

    assert response.status_code == 200
