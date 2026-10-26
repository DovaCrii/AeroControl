"""LV-372 (F-08, fase 3): la alta manual de alertas valida y acota `object_id`.

`AlertForm.object_id` era un UUID libre: se aceptaba uno inexistente o el de un registro de
otra empresa, y la alerta quedaba colgada de un objeto ajeno. Datos ficticios.
"""

import uuid
from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.forms import AlertForm
from apps.compliance.models import Alert, AlertRule
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def world(db):
    data = {}
    for key in ("a", "b"):
        tenant = OperationalTenant.objects.create(
            name=f"Empresa {key}", slug=f"emp-{key}"
        )
        center = CostCenter.objects.create(
            code=f"CC-{key.upper()}", name=f"Faena {key}", tenant=tenant
        )
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{key.upper()}1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=center,
            tenant=tenant,
            status="active",
            insurance_expiry=TODAY + timedelta(days=10),
        )
        rule = AlertRule.objects.create(
            name=f"Regla {key}",
            entity_type="registry.aircraft",
            field_to_watch="insurance_expiry",
            days_before_expiry=30,
            tenant=tenant,
        )
        data[key] = {"tenant": tenant, "aircraft": aircraft, "rule": rule}
    return data


def _payload(world, key, object_id):
    return {
        "alert_rule": world[key]["rule"].pk,
        "content_type": ContentType.objects.get_for_model(Aircraft).pk,
        "object_id": str(object_id),
        "message": "Aviso manual",
    }


def _client(world, *codenames):
    return login_as(*codenames, member_of=world["a"]["tenant"])


@pytest.mark.django_db
class TestAlertCreate:
    def test_an_object_of_the_own_tenant_is_accepted(self, world):
        client = _client(world, "add_alert")
        response = client.post(
            reverse("alert-create"), _payload(world, "a", world["a"]["aircraft"].pk)
        )
        assert response.status_code == 302
        assert Alert.objects.get().object_id == world["a"]["aircraft"].pk

    def test_an_object_of_another_tenant_is_rejected(self, world):
        client = _client(world, "add_alert")
        response = client.post(
            reverse("alert-create"), _payload(world, "a", world["b"]["aircraft"].pk)
        )
        assert response.status_code == 200
        assert "object_id" in response.context["form"].errors
        assert not Alert.objects.exists()

    def test_a_missing_object_is_rejected(self, world):
        client = _client(world, "add_alert")
        response = client.post(
            reverse("alert-create"), _payload(world, "a", uuid.uuid4())
        )
        assert response.status_code == 200
        assert "object_id" in response.context["form"].errors
        assert not Alert.objects.exists()

    def test_without_the_permission_it_is_forbidden(self, world):
        client = _client(world, "view_alert")
        response = client.post(
            reverse("alert-create"), _payload(world, "a", world["a"]["aircraft"].pk)
        )
        assert response.status_code == 403
        assert not Alert.objects.exists()


@pytest.mark.django_db
class TestAlertFormAlone:
    def test_without_a_user_the_record_only_has_to_exist(self, world):
        form = AlertForm(data=_payload(world, "a", world["b"]["aircraft"].pk))
        assert form.is_valid(), form.errors
        missing = AlertForm(data=_payload(world, "a", uuid.uuid4()))
        assert not missing.is_valid()
