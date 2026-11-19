"""LV-455: los operadores también se acotan por centro de costo en el permiso.

Con LV-453 desplegado, la flota se acotaba y los operadores no: casi ninguno
tiene `cost_center` en su ficha. Ahora un operador es de una faena por su ficha,
por ser su responsable o por figurar en un permiso reciente de esa faena.
"""

from datetime import date, timedelta

import pytest

from apps.operations.forms import (
    OPERATOR_PERMIT_LOOKBACK_DAYS,
    FlightPermissionForm,
    operator_cost_centers,
)
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter, Operator

TODAY = date(2026, 11, 15)


@pytest.fixture
def world(db):
    home = CostCenter.objects.create(code="CC100", name="Faena demo")
    other = CostCenter.objects.create(code="CC200", name="Otra faena")
    pilot = Operator.objects.create(employee_id="E-1", full_name="Piloto Demo")
    return {"home": home, "other": other, "pilot": pilot}


def _permit(cost_center, operator, **kwargs):
    permit = FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="inspection",
        location="Sitio demo",
        area_type="rural",
        status=kwargs.pop("status", FlightPermission.STATUS_REQUESTED),
        **kwargs,
    )
    permit.operators.add(operator)
    return permit


def _ccs(world):
    found = operator_cost_centers(Operator.objects.all(), TODAY)
    return set(found.get(str(world["pilot"].pk), "").split())


class TestOperatorCostCenters:
    def test_a_permit_of_the_cost_center_counts(self, world):
        _permit(world["home"], world["pilot"])

        assert _ccs(world) == {str(world["home"].pk)}

    def test_the_record_and_the_permits_add_up(self, world):
        Operator.objects.filter(pk=world["pilot"].pk).update(cost_center=world["other"])
        _permit(world["home"], world["pilot"])

        assert _ccs(world) == {str(world["home"].pk), str(world["other"].pk)}

    def test_the_responsible_operator_counts(self, world):
        CostCenter.objects.filter(pk=world["home"].pk).update(
            responsible_operator=world["pilot"]
        )

        assert _ccs(world) == {str(world["home"].pk)}

    def test_an_old_permit_does_not_count(self, world):
        end = TODAY - timedelta(days=OPERATOR_PERMIT_LOOKBACK_DAYS + 1)
        _permit(
            world["home"],
            world["pilot"],
            status=FlightPermission.STATUS_REQUESTED,
            valid_from=end - timedelta(days=30),
            valid_until=end,
        )

        assert _ccs(world) == set()

    def test_a_denied_or_archived_permit_does_not_count(self, world):
        _permit(world["home"], world["pilot"], status=FlightPermission.STATUS_DENIED)
        archived = _permit(world["other"], world["pilot"])
        FlightPermission.objects.filter(pk=archived.pk).update(is_active=False)

        assert _ccs(world) == set()


def test_the_form_marks_the_operator_with_the_permit_cost_center(world):
    _permit(world["home"], world["pilot"])

    html = str(FlightPermissionForm()["operators"])

    assert f'data-roster-cc="{world["home"].pk}"' in html
