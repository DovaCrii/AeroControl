"""LV-368 fase 0: el plan geoespacial y el permiso no cruzan de tenant (F-08).

Tres puertas por las que un plan o un permiso de otro tenant podía alcanzarse y
que se comprobaron con estas pruebas antes de arreglarlas:

1. el selector `source_plan` del formulario del permiso ofrecía planes ajenos;
2. vincular/desvincular resolvía el permiso por `pk` solo;
3. la API de planes resolvía el plan por `pk` solo.

Y el espejo en los modelos de la regla «un plan alimenta un permiso de su misma
faena», que hasta hoy sólo vivía en el formulario (el admin o un import la
evadían). Datos ficticios.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.geo.models import GeoPlan
from apps.operations.forms import FlightPermissionForm
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def tenants(db):
    return (
        OperationalTenant.objects.create(name="Alfa", slug="alfa"),
        OperationalTenant.objects.create(name="Beta", slug="beta"),
    )


@pytest.fixture
def world(tenants):
    """Un centro de costo, un permiso y un plan por tenant."""
    alfa, beta = tenants
    author = User.objects.create_user("autor-368", password="pw")  # nosec B106
    data = {}
    for key, tenant in (("a", alfa), ("b", beta)):
        center = CostCenter.objects.create(
            code=f"CC-{key.upper()}", name=f"Faena {key}", tenant=tenant
        )
        permit = FlightPermission.objects.create(
            internal_folio=f"JEJ-2026-36{key}",
            cost_center=center,
            purpose="patrol",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=30),
            location="Sitio ficticio",
            area_type="unpopulated",
        )
        plan = GeoPlan.objects.create(
            title=f"Plan {key}", cost_center=center, created_by=author
        )
        data[key] = {"tenant": tenant, "center": center, "permit": permit, "plan": plan}
    return data


def _form_user(tenant):
    client = login_as("add_flightpermission", "change_geoplan", member_of=tenant)
    return client.user


@pytest.mark.django_db
class TestSelectorOffersOnlyOwnTenantPlans:
    def test_other_tenant_plan_is_not_offered(self, world):
        form = FlightPermissionForm(user=_form_user(world["a"]["tenant"]))
        offered = set(form.fields["source_plan"].queryset)
        assert world["a"]["plan"] in offered
        assert world["b"]["plan"] not in offered

    def test_other_tenant_plan_is_rejected_on_submit(self, world):
        form = FlightPermissionForm(
            data={
                "purpose": "patrol",
                "location": "x",
                # El centro de costo es el del plan ajeno a propósito: así la
                # regla «mismo centro» no tapa la brecha del selector.
                "cost_center": str(world["b"]["center"].pk),
                "source_plan": str(world["b"]["plan"].pk),
            },
            user=_form_user(world["a"]["tenant"]),
        )
        assert not form.is_valid()
        assert "source_plan" in form.errors


@pytest.mark.django_db
class TestLinkAndUnlinkAreTenantScoped:
    def test_linking_a_permit_of_another_tenant_is_404(self, world):
        client = login_as("change_geoplan", member_of=world["a"]["tenant"])
        # El plan es del tenant de la persona; el permiso no.
        response = client.post(
            reverse("permission-link-plan", args=[world["b"]["permit"].pk]),
            {"plan": str(world["a"]["plan"].pk)},
        )
        assert response.status_code == 404
        world["a"]["plan"].refresh_from_db()
        assert world["a"]["plan"].flight_permission_id is None

    def test_unlinking_a_permit_of_another_tenant_is_404(self, world):
        plan = world["b"]["plan"]
        plan.flight_permission = world["b"]["permit"]
        plan.save()
        client = login_as("change_geoplan", member_of=world["a"]["tenant"])
        response = client.post(
            reverse("permission-unlink-plan", args=[world["b"]["permit"].pk]),
            {"plan": str(plan.pk)},
        )
        assert response.status_code == 404
        plan.refresh_from_db()
        assert plan.flight_permission_id == world["b"]["permit"].pk

    def test_own_tenant_still_links_and_unlinks(self, world):
        client = login_as("change_geoplan", member_of=world["a"]["tenant"])
        permit, plan = world["a"]["permit"], world["a"]["plan"]
        client.post(
            reverse("permission-link-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )
        plan.refresh_from_db()
        assert plan.flight_permission_id == permit.pk
        client.post(
            reverse("permission-unlink-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )
        plan.refresh_from_db()
        assert plan.flight_permission_id is None


@pytest.mark.django_db
class TestPlanApiIsTenantScoped:
    @pytest.mark.parametrize(
        "name,args",
        [
            ("api-v1-geo-plan", []),
            ("api-v1-geo-plan-versions", []),
        ],
    )
    def test_reading_a_plan_of_another_tenant_is_404(self, world, name, args):
        client = login_as("view_geoplan", member_of=world["a"]["tenant"])
        other = client.get(reverse(name, args=[world["b"]["plan"].pk, *args]))
        assert other.status_code == 404
        own = client.get(reverse(name, args=[world["a"]["plan"].pk, *args]))
        assert own.status_code == 200

    def test_exporting_a_plan_of_another_tenant_is_404(self, world):
        client = login_as("view_geoplan", member_of=world["a"]["tenant"])
        response = client.post(
            reverse("api-v1-geo-plan-export", args=[world["b"]["plan"].pk]),
            {"format": "kml"},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_committing_to_a_plan_of_another_tenant_is_404(self, world):
        client = login_as("change_geoplan", member_of=world["a"]["tenant"])
        response = client.post(
            reverse("api-v1-geo-plan-versions", args=[world["b"]["plan"].pk]),
            {"base_version": 0, "content": {}},
            content_type="application/json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestSameCostCenterMirrorInModels:
    """El vínculo plan-permiso exige la misma faena también fuera del formulario."""

    def test_geoplan_clean_rejects_a_permit_of_another_cost_center(self, world):
        plan = world["a"]["plan"]
        plan.flight_permission = world["b"]["permit"]
        with pytest.raises(ValidationError) as caught:
            plan.full_clean(exclude=["folio"])
        assert "flight_permission" in caught.value.message_dict

    def test_geoplan_clean_accepts_the_same_cost_center(self, world):
        plan = world["a"]["plan"]
        plan.flight_permission = world["a"]["permit"]
        plan.full_clean(exclude=["folio"])

    def test_permission_clean_rejects_changing_to_another_cost_center(self, world):
        permit = world["a"]["permit"]
        plan = world["a"]["plan"]
        plan.flight_permission = permit
        plan.save()
        permit.cost_center = world["b"]["center"]
        with pytest.raises(ValidationError) as caught:
            permit.clean()
        assert "cost_center" in caught.value.message_dict

    def test_permission_clean_ignores_archived_plans(self, world):
        permit = world["a"]["permit"]
        plan = world["a"]["plan"]
        plan.flight_permission = permit
        plan.is_active = False
        plan.save()
        permit.cost_center = world["b"]["center"]
        permit.clean()
