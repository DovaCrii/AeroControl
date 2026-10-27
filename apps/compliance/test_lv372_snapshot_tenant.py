"""LV-372 (F-08, fase 1): `snapshot_compliance` escribe por empresa.

Antes el comando sumaba todas las empresas en **una** fila consolidada bajo la empresa por
defecto y resolvía la faena por `code`, que sólo es único dentro de una empresa: con dos
empresas la consolidada se mezclaba y la fila por faena podía quedar atribuida a la otra.
Datos ficticios.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import ComplianceSnapshot
from apps.compliance.reports import latest_snapshot_before
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture
def world(db):
    """Dos empresas con la **misma** faena `FAENA-01`; la B tiene dos seguros vencidos."""
    data = {}
    for key, expiries in (
        ("a", [TODAY + timedelta(days=200)]),
        ("b", [TODAY - timedelta(days=3)] * 2),
    ):
        tenant = OperationalTenant.objects.create(
            name=f"Empresa {key}", slug=f"emp-{key}"
        )
        center = CostCenter.objects.create(
            code="FAENA-01", name=f"Faena {key}", tenant=tenant
        )
        for index, expiry in enumerate(expiries):
            Aircraft.objects.create(
                registration=f"RPA-{key.upper()}{index}",
                type="RPA",
                model="M3",
                manufacturer="DJI",
                cost_center=center,
                tenant=tenant,
                status="active",
                insurance_expiry=expiry,
            )
        data[key] = {"tenant": tenant, "center": center}
    return data


def _consolidated(tenant):
    return ComplianceSnapshot.objects.get(
        tenant=tenant, cost_center=None, date=YESTERDAY
    )


def _run():
    call_command("snapshot_compliance", "--date", YESTERDAY.isoformat())


@pytest.mark.django_db
class TestSnapshotWritesPerTenant:
    def test_each_center_row_carries_its_own_center_and_tenant(self, world):
        _run()
        for key in ("a", "b"):
            row = ComplianceSnapshot.objects.get(
                cost_center=world[key]["center"], date=YESTERDAY
            )
            assert row.tenant == world[key]["tenant"]
        # Mismo código, dos faenas, dos filas: ninguna se perdió ni se pisó.
        assert (
            ComplianceSnapshot.objects.filter(
                date=YESTERDAY, cost_center__code="FAENA-01"
            ).count()
            == 2
        )

    def test_one_consolidated_row_per_tenant_with_its_own_totals(self, world):
        _run()
        a, b = _consolidated(world["a"]["tenant"]), _consolidated(world["b"]["tenant"])
        assert (a.total, a.valid, a.expired) == (1, 1, 0)
        assert (b.total, b.valid, b.expired) == (2, 0, 2)

    def test_rerunning_does_not_duplicate(self, world):
        _run()
        before = ComplianceSnapshot.objects.count()
        _run()
        assert ComplianceSnapshot.objects.count() == before

    def test_a_tenant_without_centers_still_gets_its_consolidated_row(self, world):
        empty = OperationalTenant.objects.create(name="Vacia", slug="vacia")
        _run()
        assert _consolidated(empty).total == 0


@pytest.mark.django_db
class TestLatestSnapshotBefore:
    def test_a_person_of_a_gets_the_base_of_a(self, world):
        _run()
        user = login_as("view_document", member_of=world["a"]["tenant"]).user
        snapshot = latest_snapshot_before(TODAY, user=user)
        assert (snapshot.total, snapshot.expired) == (1, 0)

    def test_a_superuser_gets_the_sum_of_every_tenant(self, world):
        _run()
        root = User.objects.create_superuser("root372", password="pw")  # nosec B106
        snapshot = latest_snapshot_before(TODAY, user=root)
        assert (snapshot.total, snapshot.expired) == (3, 2)
        assert snapshot.valid_pct == 33.3

    def test_a_missing_row_for_a_visible_tenant_means_no_base(self, world):
        _run()
        _consolidated(world["b"]["tenant"]).delete()
        root = User.objects.create_superuser("root372", password="pw")  # nosec B106
        assert latest_snapshot_before(TODAY, user=root) is None
        # La persona de A no depende de B: conserva su base.
        user = login_as("view_document", member_of=world["a"]["tenant"]).user
        assert latest_snapshot_before(TODAY, user=user) is not None

    def test_the_per_center_base_is_scoped_to_the_visible_tenants(self, world):
        _run()
        user = login_as("view_document", member_of=world["a"]["tenant"]).user
        assert (
            latest_snapshot_before(TODAY, cost_center=world["b"]["center"], user=user)
            is None
        )
        assert (
            latest_snapshot_before(TODAY, cost_center=world["a"]["center"], user=user)
            is not None
        )


@pytest.mark.django_db
class TestReportView:
    def _baseline(self, client):
        response = client.get(
            reverse("compliance-report"),
            {"start": TODAY.isoformat(), "end": TODAY.isoformat()},
        )
        assert response.status_code == 200
        return response.context["comparison_baseline"]

    def test_the_report_of_a_uses_the_base_of_a(self, world):
        _run()
        client = login_as("view_document", member_of=world["a"]["tenant"])
        baseline = self._baseline(client)
        assert baseline.total == 1

    def test_a_superuser_sees_the_sum(self, world):
        _run()
        root = User.objects.create_superuser("root372", password="pw")  # nosec B106
        client = Client()
        client.force_login(root)
        assert self._baseline(client).total == 3

    def test_without_permission_it_is_forbidden(self, world):
        client = login_as(member_of=world["a"]["tenant"])
        assert client.get(reverse("compliance-report")).status_code == 403
