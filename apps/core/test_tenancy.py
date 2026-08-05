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


class TestRegistryListIsolation:
    """T3.2 Fase 2: the registry lists (CostCenter/Operator/Aircraft), which did
    not scope by tenant before, now only show the user's tenant."""

    def _client(self, username, codename, tenant=None):
        user = User.objects.create_user(username, password="pw")
        user.user_permissions.add(Permission.objects.get(codename=codename))
        if tenant is not None:
            TenantMembership.objects.create(tenant=tenant, user=user)
        client = Client()
        assert client.login(username=username, password="pw")
        return client

    @pytest.mark.django_db
    def test_cost_center_list_is_scoped(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        cc = CostCenter.objects.create(code="CCA", name="A", tenant=a)
        a_client = self._client("a_cc", "view_costcenter", tenant=a)
        b_client = self._client("b_cc", "view_costcenter", tenant=b)
        assert cc in list(a_client.get(reverse("costcenter-list")).context["objects"])
        assert cc not in list(
            b_client.get(reverse("costcenter-list")).context["objects"]
        )

    @pytest.mark.django_db
    def test_operator_list_is_scoped(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        op = Operator.objects.create(employee_id="OA", full_name="Op A", tenant=a)
        a_client = self._client("a_op", "view_operator", tenant=a)
        b_client = self._client("b_op", "view_operator", tenant=b)
        assert op in list(a_client.get(reverse("operator-list")).context["objects"])
        assert op not in list(b_client.get(reverse("operator-list")).context["objects"])

    @pytest.mark.django_db
    def test_aircraft_list_is_scoped(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        ac = Aircraft.objects.create(
            registration="RPA-A", type="RPA", model="M", manufacturer="DJI", tenant=a
        )
        a_client = self._client("a_ac", "view_aircraft", tenant=a)
        b_client = self._client("b_ac", "view_aircraft", tenant=b)
        assert ac in list(a_client.get(reverse("aircraft-list")).context["objects"])
        assert ac not in list(b_client.get(reverse("aircraft-list")).context["objects"])


class TestTenantUniqueConstraints:
    """T3.2 Fase 3: cost-center code and employee id are unique per tenant,
    not globally -- two organizations may reuse them, one may not."""

    @pytest.mark.django_db
    def test_two_tenants_can_reuse_a_cost_center_code(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        CostCenter.objects.create(code="CC1", tenant=a)
        CostCenter.objects.create(code="CC1", tenant=b)
        assert CostCenter.objects.filter(code="CC1").count() == 2

    @pytest.mark.django_db
    def test_same_tenant_cannot_reuse_a_cost_center_code(self):
        from django.db import IntegrityError, transaction

        a = OperationalTenant.objects.create(name="A", slug="a")
        CostCenter.objects.create(code="CC1", tenant=a)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CostCenter.objects.create(code="CC1", tenant=a)

    @pytest.mark.django_db
    def test_two_tenants_can_reuse_an_employee_id(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        Operator.objects.create(employee_id="E1", full_name="A", tenant=a)
        Operator.objects.create(employee_id="E1", full_name="B", tenant=b)
        assert Operator.objects.filter(employee_id="E1").count() == 2

    @pytest.mark.django_db
    def test_same_tenant_cannot_reuse_an_employee_id(self):
        from django.db import IntegrityError, transaction

        a = OperationalTenant.objects.create(name="A", slug="a")
        Operator.objects.create(employee_id="E1", full_name="A", tenant=a)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Operator.objects.create(employee_id="E1", full_name="dup", tenant=a)


class TestObjectLevelIsolation:
    """F-03/F-06: a detail/edit/archive view must not open another tenant's
    record by URL -- the T3.2 Fase 2 scoping only guarded the lists."""

    def _client(self, username, codename, tenant=None):
        user = User.objects.create_user(username, password="pw")
        user.user_permissions.add(Permission.objects.get(codename=codename))
        if tenant is not None:
            TenantMembership.objects.create(tenant=tenant, user=user)
        client = Client()
        assert client.login(username=username, password="pw")
        return client

    @pytest.mark.django_db
    def test_aircraft_detail_is_visible_to_owner_but_404_to_another_tenant(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        aircraft = Aircraft.objects.create(
            registration="RPA-A", type="RPA", model="M", manufacturer="DJI", tenant=a
        )
        owner = self._client("a_det", "view_aircraft", tenant=a)
        intruder = self._client("b_det", "view_aircraft", tenant=b)
        url = reverse("aircraft-detail", args=[aircraft.pk])
        assert owner.get(url).status_code == 200
        assert intruder.get(url).status_code == 404

    @pytest.mark.django_db
    def test_cost_center_edit_is_404_for_another_tenant(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        cost_center = CostCenter.objects.create(code="CCA", name="A", tenant=a)
        intruder = self._client("b_edit", "change_costcenter", tenant=b)
        url = reverse("costcenter-update", args=[cost_center.pk])
        assert intruder.get(url).status_code == 404

    @pytest.mark.django_db
    def test_operator_archive_is_404_for_another_tenant(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        operator = Operator.objects.create(
            employee_id="OA2", full_name="Op A", tenant=a
        )
        intruder = self._client("b_arch", "delete_operator", tenant=b)
        response = intruder.post(reverse("operator-archive", args=[operator.pk]))
        assert response.status_code == 404
        operator.refresh_from_db()
        assert operator.is_active  # untouched

    @pytest.mark.django_db
    def test_document_detail_is_404_for_another_tenant(self):
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.models import Document, DocumentType

        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        cc = CostCenter.objects.create(code="CCA", tenant=a)
        document = Document.objects.create(
            title="Secret",
            doc_type=DocumentType.objects.create(code="c", name="C"),
            content_type=ContentType.objects.get_for_model(CostCenter),
            object_id=cc.pk,
            file_path="x.pdf",
            issue_date=date(2026, 1, 1),
            tenant=a,
        )
        intruder = self._client("b_doc", "view_document", tenant=b)
        url = reverse("document-detail", args=[document.pk])
        assert intruder.get(url).status_code == 404

    @pytest.mark.django_db
    def test_permission_detail_is_404_for_another_tenant(self):
        from apps.operations.models import FlightPermission

        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        cc = CostCenter.objects.create(code="CCA", tenant=a)
        permission = FlightPermission.objects.create(
            permission_number="P1",
            cost_center=cc,
            purpose="x",
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 7, 2),
            location="S",
        )
        intruder = self._client("b_perm", "view_flightpermission", tenant=b)
        url = reverse("permission-detail", args=[permission.pk])
        assert intruder.get(url).status_code == 404

    @pytest.mark.django_db
    def test_maintenance_detail_is_404_for_another_tenant(self):
        from apps.maintenance.models import MaintenanceRecord

        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        aircraft = Aircraft.objects.create(
            registration="RPA-A", type="RPA", model="M", manufacturer="DJI", tenant=a
        )
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="c",
            scheduled_date=date(2026, 7, 20),
        )
        intruder = self._client("b_maint", "view_maintenancerecord", tenant=b)
        url = reverse("maintenance-detail", args=[record.pk])
        assert intruder.get(url).status_code == 404


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
