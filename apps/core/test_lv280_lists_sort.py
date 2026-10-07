"""LV-280: toda lista con columnas propias se ordena desde su encabezado.

Pedido del usuario (2026-10-06): *"poder ordenarlas clickeando desde algún lado
para que sea ascendente y descendente, aplicable a toda la app"*. La mecánica
(`SortableColumnsMixin` + `{% worktable_th %}`) existe desde UX-07; este archivo
vigila que (1) cada columna declarada ordena sin reventar, en los dos sentidos y
sobre datos de verdad, y (2) el encabezado dibuja exactamente las columnas que la
vista declara: ni un enlace a algo que la lista blanca ignora, ni una columna
declarada que nadie puede pulsar.
"""

import re

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.registry.models import Aircraft, CostCenter, Operator

LISTS = [
    "permission-list",
    "record-list",
    "flight-request-list",
    "maintenance-list",
    "operator-list",
    "aircraft-list",
    "costcenter-list",
    # Segunda tanda: asignaciones y las listas genéricas (Nombre / Creado / Estado).
    "operatorassignment-list",
    "aircraftassignment-list",
    "documenttype-list",
    "alertrule-list",
    "qualificationtype-list",
    "label-list",
]


@pytest.fixture
def some_data(db):
    CostCenter.objects.create(code="CC2", name="Dos", operates_flights=True)
    CostCenter.objects.create(code="CC110", name="Ciento diez", operates_flights=True)
    Aircraft.objects.create(
        registration="RPA-0002", type="RPA", model="M3", manufacturer="DJI"
    )
    Aircraft.objects.create(
        registration="RPA-0001", type="RPA", model="M3", manufacturer="DJI"
    )
    Operator.objects.create(employee_id="E1", full_name="Zoe Alfa", surnames="Alfa")
    Operator.objects.create(employee_id="E2", full_name="Ana Zeta", surnames="Zeta")


def _declared_and_drawn(client, name):
    response = client.get(reverse(name))
    assert response.status_code == 200, name
    declared = set(response.context["worktable_sort"]["columns"])
    body = response.content.decode()
    drawn = set(re.findall(r"sort=(\w+)(?:&amp;|&)dir=", body))
    return declared, drawn


@pytest.mark.parametrize("name", LISTS)
def test_the_header_draws_exactly_the_declared_columns(
    client, admin_user, some_data, name
):
    client.force_login(admin_user)

    declared, drawn = _declared_and_drawn(client, name)

    assert declared, f"{name} no declara columnas ordenables"
    assert drawn == declared, name


@pytest.mark.parametrize("name", LISTS)
def test_every_declared_column_sorts_both_ways(client, admin_user, some_data, name):
    client.force_login(admin_user)
    declared, _ = _declared_and_drawn(client, name)

    for column in declared:
        for direction in ("asc", "desc"):
            response = client.get(reverse(name), {"sort": column, "dir": direction})
            assert response.status_code == 200, (name, column, direction)


def test_aircraft_sort_is_not_overridden_by_the_default_order(
    client, admin_user, some_data
):
    """La vista fijaba `order_by("registration")` encima de lo que dejaba el mixin:
    el clic en el encabezado no cambiaba nada, y ninguna prueba lo miraba."""
    client.force_login(admin_user)

    def registrations(direction):
        response = client.get(
            reverse("aircraft-list"), {"sort": "registration", "dir": direction}
        )
        return [a.registration for a in response.context["object_list"]]

    assert registrations("asc") == ["RPA-0001", "RPA-0002"]
    assert registrations("desc") == ["RPA-0002", "RPA-0001"]


def test_cost_centre_codes_sort_by_number_not_by_text(client, admin_user, some_data):
    """Por texto, CC110 queda antes que CC2: es lo que R3.2 ya evitaba."""
    client.force_login(admin_user)

    response = client.get(reverse("costcenter-list"), {"sort": "code", "dir": "asc"})

    assert [c.code for c in response.context["object_list"]] == ["CC2", "CC110"]


def test_operator_sort_is_not_overridden_by_the_surname_order(
    client, admin_user, some_data
):
    client.force_login(admin_user)

    def names(direction):
        response = client.get(
            reverse("operator-list"), {"sort": "name", "dir": direction}
        )
        return [o.full_name for o in response.context["object_list"]]

    assert names("asc") == ["Ana Zeta", "Zoe Alfa"]
    assert names("desc") == ["Zoe Alfa", "Ana Zeta"]


def test_today_is_a_date():
    """Ancla para que el módulo no dependa del reloj: ninguna prueba lo usa."""
    assert timezone.localdate()
