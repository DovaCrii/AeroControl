"""LV-378 fase 4: la renovación 45/30/15 no vigila permisos de faenas sin operación.

`generate_alerts` sólo excluía registros terminales y salidos de la empresa; un
permiso aprobado de una faena cerrada, que no vuela o archivada seguía generando
«Permisos de vuelo por vencer» aunque no se va a renovar. Ahora se usa la misma
definición de «con operación» que la cobertura y el informe
(`operating_cost_centers`).
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter


def _permit(centre, number):
    today = timezone.localdate()
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="Survey",
        location="Sitio ficticio",
        status="approved",
        permission_number=number,
        valid_from=today - timedelta(days=60),
        valid_until=today + timedelta(days=10),
    )


@pytest.fixture
def rule():
    return AlertRule.objects.create(
        name="Permisos de vuelo por vencer",
        entity_type="operations.flightpermission",
        field_to_watch="valid_until",
        days_before_expiry=45,
    )


def _alerted():
    return set(Alert.objects.values_list("object_id", flat=True))


@pytest.mark.django_db
def test_an_operating_centre_still_alerts(rule):
    permit = _permit(CostCenter.objects.create(code="CC921", name="Opera"), "P-1")

    call_command("generate_alerts")

    assert _alerted() == {permit.pk}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kwargs",
    [
        {"contract_status": "closed"},
        {"operates_flights": False},
        {"is_active": False},
    ],
    ids=["closed", "does-not-fly", "archived"],
)
def test_a_centre_out_of_operation_does_not_alert(rule, kwargs):
    operating = _permit(CostCenter.objects.create(code="CC922", name="Opera"), "P-2")
    out = _permit(
        CostCenter.objects.create(code="CC923", name="Fuera", **kwargs), "P-3"
    )

    call_command("generate_alerts")

    assert _alerted() == {operating.pk}
    assert out.pk not in _alerted()


@pytest.mark.django_db
def test_the_exclusion_is_only_for_permits(rule):
    """Una póliza o un documento de una faena cerrada no se tocan acá."""
    from apps.registry.models import Aircraft

    closed = CostCenter.objects.create(
        code="CC924", name="Cerrada", contract_status="closed"
    )
    aircraft = Aircraft.objects.create(
        registration="RPA-924",
        type="RPAS",
        model="Mavic",
        manufacturer="DJI",
        cost_center=closed,
        insurance_expiry=timezone.localdate() + timedelta(days=5),
    )
    AlertRule.objects.create(
        name="Seguros",
        entity_type="registry.aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
    )
    call_command("generate_alerts")

    assert aircraft.pk in _alerted()
