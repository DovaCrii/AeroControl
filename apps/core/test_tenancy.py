"""Tenancy read-scoping (T3.2 Fase 1): visible_tenant_ids + isolation."""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from apps.core.models import OperationalTenant, TenantMembership
from apps.core.tenancy import get_default_tenant, visible_tenant_ids
from apps.registry.models import Aircraft, Assignment, CostCenter, Operator


class TestVisibleTenantIds:
    @pytest.mark.django_db
    def test_superuser_sees_all(self):
        user = User.objects.create_superuser("root2", "r@t.com", "pw")
        assert visible_tenant_ids(user) is None

    @pytest.mark.django_db
    def test_no_membership_falls_back_to_default(self):
        user = User.objects.create_user("plain", password="pw")
        assert visible_tenant_ids(user) == [get_default_tenant()]

    @pytest.mark.django_db
    def test_uses_the_users_memberships(self):
        user = User.objects.create_user("member", password="pw")
        tenant = OperationalTenant.objects.create(name="B", slug="b")
        TenantMembership.objects.create(tenant=tenant, user=user)
        assert visible_tenant_ids(user) == [tenant.pk]


class TestAssignmentListIsolation:
    def _default_assignment(self):
        # No tenant passed -> the FK default puts these in the default tenant.
        cc = CostCenter.objects.create(code="738", name="X")
        operator = Operator.objects.create(
            employee_id="OP1", full_name="Pilot", cost_center=cc
        )
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M",
            manufacturer="DJI",
            cost_center=cc,
        )
        return Assignment.objects.create(
            operator=operator,
            aircraft=aircraft,
            cost_center=cc,
            start_date=date(2026, 7, 1),
        )

    def _client(self, username, tenant=None):
        user = User.objects.create_user(username, password="pw")
        user.user_permissions.add(Permission.objects.get(codename="view_assignment"))
        if tenant is not None:
            TenantMembership.objects.create(tenant=tenant, user=user)
        client = Client()
        assert client.login(username=username, password="pw")
        return client

    @pytest.mark.django_db
    def test_user_without_membership_sees_the_default_tenant_assignment(self):
        self._default_assignment()
        client = self._client("plain")
        response = client.get(reverse("assignment-list"))
        assert response.status_code == 200
        assert list(response.context["objects"])  # fallback -> sees it

    @pytest.mark.django_db
    def test_user_in_another_tenant_is_isolated(self):
        self._default_assignment()
        other = OperationalTenant.objects.create(name="B", slug="b")
        client = self._client("bmember", tenant=other)
        response = client.get(reverse("assignment-list"))
        assert response.status_code == 200
        assert not list(response.context["objects"])  # isolated: sees nothing


class TestCalendarFeedIsolation:
    """Safety net (T3.2 Fase 4) for the calendar feed's tenant scoping, so the
    Fase 2 change from OR-over-FKs to a canonical path cannot regress it."""

    def _permission_in(self, tenant, number, code):
        from apps.operations.models import FlightPermission

        cc = CostCenter.objects.create(code=code, name=code, tenant=tenant)
        return FlightPermission.objects.create(
            permission_number=number,
            cost_center=cc,
            purpose="Survey",
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 7, 31),
            location="Site",
        )

    def _client(self, username, tenant=None):
        user = User.objects.create_user(username, password="pw")
        user.user_permissions.add(
            Permission.objects.get(codename="view_flightpermission")
        )
        if tenant is not None:
            TenantMembership.objects.create(tenant=tenant, user=user)
        client = Client()
        assert client.login(username=username, password="pw")
        return client

    def _feed_ids(self, client):
        response = client.get(
            reverse("calendar-events"), {"start": "2026-07-01", "end": "2026-08-01"}
        )
        assert response.status_code == 200
        return {item["id"] for item in response.json()}

    @pytest.mark.django_db
    def test_permission_is_not_visible_to_another_tenant(self):
        from apps.core.models import OperationalTenant

        tenant_a = OperationalTenant.objects.create(name="A", slug="a")
        tenant_b = OperationalTenant.objects.create(name="B", slug="b")
        permission = self._permission_in(tenant_a, "P-A", "CCA")

        a_client = self._client("amember", tenant=tenant_a)
        b_client = self._client("bmember", tenant=tenant_b)

        assert f"permission-{permission.pk}" in self._feed_ids(a_client)  # owner sees
        assert f"permission-{permission.pk}" not in self._feed_ids(b_client)  # isolated

    @pytest.mark.django_db
    def test_membershipless_user_sees_the_default_tenant_via_fallback(self):
        from apps.core.tenancy import get_default_tenant
        from apps.core.models import OperationalTenant

        default = OperationalTenant.objects.get(pk=get_default_tenant())
        permission = self._permission_in(default, "P-DEF", "CCDEF")

        client = self._client("plain")  # no membership -> default fallback
        assert f"permission-{permission.pk}" in self._feed_ids(client)
