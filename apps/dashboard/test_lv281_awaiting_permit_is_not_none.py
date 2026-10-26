"""LV-281: una faena con un permiso esperando respuesta no dice «Ninguno».

Pedido del usuario (2026-10-06, captura del panel): en «Permisos de vuelo por
centro de costo», `CC684` tenía un permiso esperando y su estado seguía diciendo
«Ninguno» con el mismo color que las faenas sin nada. La fila sigue en rojo —no
puede volar hasta que lo aprueben—, pero el estado debe distinguir «no hay nada»
de «ya se pidió».
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()


def _page(client, admin_user):
    Aircraft.objects.create(
        registration="RPA-0001",
        type="RPA",
        model="M3",
        manufacturer="DJI",
        status="active",
    )
    client.force_login(admin_user)
    # LV-359 (fase 4): la tabla vive en la sección «Cumplimiento».
    content = client.get(reverse("dashboard-compliance")).content.decode()
    return content.split("Permisos de vuelo por centro de costo")[-1]


@pytest.mark.django_db
def test_a_waiting_permit_shows_awaiting_in_warning_colour(client, admin_user):
    centre = CostCenter.objects.create(
        code="CC684", name="PMCHS", operates_flights=True
    )
    FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        location="Sector",
        area_type="unpopulated",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=30),
    )

    table = _page(client, admin_user)

    # LV-376: el chip de espera es sólido (`.id-cx-state--wait`), con símbolo ◐ y la palabra completa
    assert (
        '<span class="id-cx-state id-cx-state--wait"><span aria-hidden="true">◐</span>'
        " Esperando a la DGAC</span>" in table
    )
    assert "Sin permiso" not in table.split("</thead>")[-1].split("</table>")[0]


@pytest.mark.django_db
def test_a_site_with_nothing_still_says_none(client, admin_user):
    CostCenter.objects.create(code="CC900", name="Vacia", operates_flights=True)

    table = _page(client, admin_user)

    assert "Sin permiso" in table.split("</table>")[0]
    # sólo la tabla: la guía de la sección también dibuja chips de ese tono
    assert "id-chip--warning" not in table.split("</table>")[0]
