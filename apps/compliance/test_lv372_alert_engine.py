"""LV-372 (F-08, fase 4): las reglas de alerta son DE CADA EMPRESA.

`generate_alerts` recorría todas las reglas y vigilaba los registros de **todas** las empresas,
y la bandeja acota las alertas por la empresa de su regla: con dos empresas, el seguro vencido
de una aeronave de B generaba una alerta bajo la regla de A, que A veía con la matrícula de B
y B nunca. Datos ficticios.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.compliance.watchables import WATCHABLE_MODELS, resolve_model
from apps.core.models import OperationalTenant
from apps.core.tenancy import FORM_CHOICE_TENANT_PATHS, get_default_tenant
from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()
EXPIRED = TODAY - timedelta(days=3)


def _make(key, with_rule=True):
    tenant = OperationalTenant.objects.create(name=f"Empresa {key}", slug=f"emp-{key}")
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
        insurance_expiry=EXPIRED,
    )
    rule = None
    if with_rule:
        rule = AlertRule.objects.create(
            name="Seguros por vencer",
            entity_type="registry.aircraft",
            field_to_watch="insurance_expiry",
            days_before_expiry=30,
            tenant=tenant,
        )
    return {"tenant": tenant, "center": center, "aircraft": aircraft, "rule": rule}


@pytest.fixture
def world(db):
    return {"a": _make("a"), "b": _make("b")}


def _pairs():
    return set(Alert.objects.values_list("alert_rule__tenant__slug", "object_id"))


@pytest.mark.django_db
class TestEngine:
    def test_each_rule_only_watches_the_records_of_its_own_tenant(self, world):
        call_command("generate_alerts")
        assert _pairs() == {
            ("emp-a", world["a"]["aircraft"].pk),
            ("emp-b", world["b"]["aircraft"].pk),
        }

    def test_a_tenant_without_rules_generates_nothing_for_its_records(self, world):
        world["b"]["rule"].delete()
        call_command("generate_alerts")
        # La regla de A no recoge la aeronave de B, aunque B no tenga regla propia.
        assert _pairs() == {("emp-a", world["a"]["aircraft"].pk)}

    def test_the_tray_of_a_never_shows_the_registration_of_b(self, world):
        call_command("generate_alerts")
        client = login_as("view_alert", member_of=world["a"]["tenant"])
        body = client.get(reverse("alert-list")).content.decode()
        assert "RPA-A1" in body
        assert "RPA-B1" not in body

    def test_without_the_permission_the_tray_is_forbidden(self, world):
        client = login_as(member_of=world["a"]["tenant"])
        assert client.get(reverse("alert-list")).status_code == 403

    def test_a_rule_whose_model_has_no_tenant_path_is_skipped(self, world, monkeypatch):
        monkeypatch.delitem(FORM_CHOICE_TENANT_PATHS, "registry.aircraft")
        call_command("generate_alerts")
        assert not Alert.objects.exists()


def test_every_watchable_model_has_a_tenant_path(db):
    """Un modelo vigilable nuevo sin camino a su empresa dejaría de vigilarse en silencio."""
    for key in WATCHABLE_MODELS:
        assert key in FORM_CHOICE_TENANT_PATHS, key
        path = FORM_CHOICE_TENANT_PATHS[key][0]
        # El camino tiene que ser consultable en el modelo (si no, lanza FieldError).
        list(resolve_model(key).objects.filter(**{f"{path}__in": []}))


@pytest.mark.django_db
class TestAlertInvariant:
    def _alert(self, world, rule_of, object_of):
        return Alert(
            alert_rule=world[rule_of]["rule"],
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=world[object_of]["aircraft"].pk,
            message="Aviso",
        )

    def test_the_object_of_another_tenant_is_rejected(self, world):
        with pytest.raises(ValidationError) as caught:
            self._alert(world, "a", "b").full_clean()
        assert "object_id" in caught.value.message_dict

    def test_the_object_of_the_same_tenant_is_accepted(self, world):
        self._alert(world, "a", "a").full_clean()


@pytest.mark.django_db
class TestSeedPerTenant:
    def test_seeding_a_tenant_creates_its_rules_and_is_idempotent(self, world):
        AlertRule.objects.all().delete()
        call_command("seed_alert_rules", "--tenant", "emp-b")
        first = AlertRule.objects.count()
        assert first > 0
        assert set(AlertRule.objects.values_list("tenant__slug", flat=True)) == {
            "emp-b"
        }
        call_command("seed_alert_rules", "--tenant", "emp-b")
        assert AlertRule.objects.count() == first

    def test_the_same_names_in_two_tenants_are_two_rules(self, world):
        AlertRule.objects.all().delete()
        call_command("seed_alert_rules", "--tenant", "emp-a")
        call_command("seed_alert_rules", "--tenant", "emp-b")
        total = AlertRule.objects.count()
        assert total % 2 == 0
        assert (
            AlertRule.objects.filter(tenant=world["a"]["tenant"]).count() == total // 2
        )

    def test_without_the_option_the_default_tenant_is_seeded(self, world):
        AlertRule.objects.all().delete()
        call_command("seed_alert_rules")
        assert set(AlertRule.objects.values_list("tenant_id", flat=True)) == {
            get_default_tenant()
        }

    def test_an_unknown_tenant_is_an_error(self, world):
        with pytest.raises(CommandError):
            call_command("seed_alert_rules", "--tenant", "no-existe")
