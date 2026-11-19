"""LV-453: en el permiso, el centro de costo va primero y acota drones y operadores.

Pedido del usuario: *"primero se ponga el CC […] luego se filtren los drones
disponibles de ese centro de costo solamente y un botón […] para continuar si es
un equipo distinto"*, y lo mismo con los operadores.

El filtro corre en el navegador (`roster-filter.js`); lo que el servidor garantiza
es que cada casilla lleve **sus** centros de costo en `data-roster-cc`, y que no se
bloquee guardar un equipo de otra faena: ése es el caso del botón.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.operations.forms import FlightPermissionForm, cost_centers_by_resource
from apps.registry.models import (
    Aircraft,
    AircraftAssignment,
    CostCenter,
    Operator,
    OperatorAssignment,
)

SCRIPT = Path(settings.BASE_DIR) / "static" / "js" / "roster-filter.js"


@pytest.fixture
def world(db):
    today = timezone.localdate()
    home = CostCenter.objects.create(code="CC100", name="Faena demo")
    other = CostCenter.objects.create(code="CC200", name="Otra faena")
    own = Aircraft.objects.create(
        registration="RPA-0001",
        type="Multirotor",
        model="M4E",
        manufacturer="DJI",
        cost_center=home,
    )
    lent = Aircraft.objects.create(
        registration="RPA-0002", type="Multirotor", model="M4E", manufacturer="DJI"
    )
    AircraftAssignment.objects.create(
        aircraft=lent, cost_center=other, start_date=today - timedelta(days=5)
    )
    pilot = Operator.objects.create(employee_id="E-1", full_name="Piloto Demo")
    OperatorAssignment.objects.create(
        operator=pilot, cost_center=home, start_date=today - timedelta(days=1)
    )
    return {
        "today": today,
        "home": home,
        "other": other,
        "own": own,
        "lent": lent,
        "pilot": pilot,
    }


class TestCostCentersByResource:
    def test_the_record_and_the_assignment_both_reach_the_map(self, world):
        found = cost_centers_by_resource(Aircraft.objects.all())

        assert found[str(world["own"].pk)] == str(world["home"].pk)
        # Asignada por «Asignaciones de aeronave»: la señal llena `cost_center`.
        assert found[str(world["lent"].pk)] == str(world["other"].pk)

    def test_an_ended_assignment_releases_the_resource(self, world):
        assignment = OperatorAssignment.objects.get(operator=world["pilot"])
        assignment.status = "ended"
        assignment.end_date = world["today"]
        assignment.save()

        found = cost_centers_by_resource(Operator.objects.all())
        assert str(world["pilot"].pk) not in found


def _input_for(html, pk):
    """La etiqueta `<input …>` completa de la casilla con ese valor."""
    match = re.search(rf'<input[^>]*value="{pk}"[^>]*>', html)
    assert match, pk
    return match.group(0)


class TestTheCheckboxesCarryTheirCostCenters:
    def test_each_option_says_its_cost_center(self, world):
        html = str(FlightPermissionForm()["aircraft_fleet"])

        assert f'data-roster-cc="{world["home"].pk}"' in _input_for(
            html, world["own"].pk
        )
        assert f'data-roster-cc="{world["other"].pk}"' in _input_for(
            html, world["lent"].pk
        )

    def test_an_unassigned_resource_has_an_empty_marker(self, world):
        loose = Operator.objects.create(employee_id="E-2", full_name="Sin Faena")

        html = str(FlightPermissionForm()["operators"])
        assert 'data-roster-cc=""' in _input_for(html, loose.pk)


class TestThePage:
    def test_the_cost_center_comes_before_who_flies(self, world):
        client = login_as("add_flightpermission")

        page = client.get(reverse("permission-create")).content.decode()

        assert page.index('name="cost_center"') < page.index('name="aircraft_fleet"')
        assert page.index('name="aircraft_fleet"') < page.index('name="operators"')
        assert page.count('data-roster-scope-from="#id_cost_center"') == 2

    def test_a_resource_from_another_cost_center_is_not_refused(self, world):
        """El botón «Ver los de otros centros de costo» tiene que poder guardar."""
        form = FlightPermissionForm(
            data={
                "status": "requested",
                "operators": [world["pilot"].pk],
                "aircraft_fleet": [world["lent"].pk],
                "cost_center": world["home"].pk,
                "purpose": "inspection",
                "location": "Sitio demo",
                "area_type": "rural",
            }
        )
        form.is_valid()
        assert "aircraft_fleet" not in form.errors
        assert "operators" not in form.errors


def test_the_script_scopes_by_cost_center_and_keeps_the_checked_ones():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "data-roster-cc" in script
    assert "rosterScopeFrom" in script
    # Lo marcado se ve siempre y la búsqueda recorre todo.
    assert "isChecked ||" in script
    assert "needle ||" in script
