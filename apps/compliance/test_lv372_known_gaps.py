"""LV-372: fugas de aislamiento por empresa **fuera del alcance** de la fila, demostradas.

Al auditar `geo`, el panel y los vencimientos con dos empresas aparecieron listados y acciones de
**otras apps** que tampoco acotan por tenant. No se arreglan aquí (la fila lo prohíbe: otra app,
otro bloque); se dejan **demostradas** con `xfail(strict=True)`: cada caso afirma lo correcto
(la otra empresa no aparece / es 404) y hoy falla. Cuando alguien acote la vista, el caso pasa,
`strict` lo convierte en error y obliga a quitar la marca: la deuda no se puede cerrar sin que
esta prueba lo note. Ver `MASTER_PLAN.md`, fila LV-372. Datos ficticios.
"""

from datetime import time

import pytest
from django.urls import reverse

from apps.compliance.test_lv372_tenant_scope import TODAY, _client, world  # noqa: F401
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightRecord, FlightRequest

LIST_PERMS = (
    "view_maintenancerecord",
    "view_flightpermission",
    "view_flightrequest",
    "view_flightrecord",
    "view_alertrule",
    "view_document",
)

# (nombre de la ruta de lista, texto que sólo existe en la fila de la OTRA empresa)
LEAKING_LISTS = [
    ("maintenance-list", "RPA-B1"),
    ("permission-list", "JEJ-2026-B"),
    ("flight-request-list", "Solicitud B"),
    ("record-list", "RPA-B1"),
    ("alertrule-list", "Regla b"),
    ("document-list", "Documento B"),
]


@pytest.fixture
def other_tenant_rows(world):  # noqa: F811
    MaintenanceRecord.objects.create(
        aircraft=world["b"]["aircraft"], maintenance_type="to_be_defined"
    )
    FlightRequest.objects.create(
        title="Solicitud B",
        cost_center=world["b"]["center"],
        center_lat=-31.7,
        center_lon=-70.6,
        status="filed",
        filed_on=TODAY,
    )
    FlightRecord.objects.create(
        permission=world["b"]["permit"],
        actual_date=TODAY,
        departure_time=time(9),
        arrival_time=time(10),
        pilot=world["b"]["operator"],
        aircraft=world["b"]["aircraft"],
    )
    return world


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,needle", LEAKING_LISTS)
@pytest.mark.xfail(
    strict=True, reason="LV-372: lista fuera de alcance sin acotar por tenant"
)
def test_list_hides_the_other_tenant(other_tenant_rows, url_name, needle):
    client = _client(other_tenant_rows, *LIST_PERMS)
    response = client.get(reverse(url_name))
    assert response.status_code == 200
    assert needle not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.xfail(
    strict=True, reason="LV-372: StatusTransitionView sin tenant_scope fuera de geo"
)
def test_maintenance_transition_of_the_other_tenant_is_404(other_tenant_rows):
    record = MaintenanceRecord.objects.get(aircraft=other_tenant_rows["b"]["aircraft"])
    client = _client(other_tenant_rows, "change_maintenancerecord")
    assert (
        client.post(reverse("maintenance-start", args=[record.pk])).status_code == 404
    )


@pytest.mark.django_db
@pytest.mark.xfail(
    strict=True, reason="LV-372: StatusTransitionView sin tenant_scope fuera de geo"
)
def test_permit_transition_of_the_other_tenant_is_404(other_tenant_rows):
    permit = other_tenant_rows["b"]["permit"]
    client = _client(other_tenant_rows, "change_flightpermission")
    assert client.post(reverse("permission-deny", args=[permit.pk])).status_code == 404
